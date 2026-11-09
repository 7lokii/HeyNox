# Voz

Pipeline: `áudio -> VAD -> STT -> LLM -> TTS -> áudio`.

| Etapa | Extra | Biblioteca | Estado |
|---|---|---|---|
| Captura | `audio` | sounddevice | contrato + `FakeSource` |
| Wake word | `wake` | openwakeword | contrato + duplos |
| VAD | `vad` | silero-vad | contrato + `EnergyVad` |
| STT | `stt` | faster-whisper | **funcional** |
| TTS | `tts` | piper | **funcional** |

Instalar tudo: `pip install -e ".[voice]"`.

Sem os extras, o Nox arranca em modo texto e `nox --check` indica o que falta.
Nenhum áudio sai do PC sem confirmação explícita.

## Testar sem microfone

```bash
nox --speak "Bom dia. Eu sou o Nox."          # grava WAV e diz onde
nox --speak "Bom dia." --out data/bom.wav     # destino à escolha
nox --transcribe data/bom.wav                 # devolve o texto
```

O `--speak` grava por omissão em `%LOCALAPPDATA%\HeyNox\out\nox.wav`.

## Modelos

| Modelo | Tamanho | Onde fica | Quando é descarregado |
|---|---|---|---|
| Piper `pt_PT-tugão-medium` | ~60 MB | `%LOCALAPPDATA%\HeyNox\models\piper\` | no primeiro `--speak` |
| Whisper `small` | ~480 MB | cache do Hugging Face | no primeiro `--transcribe` |

O download da voz é feito por `nox/models.py`, não pelo `piper-tts`: o
download oficial não faz URL-encoding e rebenta com `UnicodeEncodeError` em
`pt_PT-tugão-medium`.

### Downloads do Hugging Face pendurados

Em algumas redes o `hf_xet` (transferência por chunks) fica parado a 0 MB/s.
Sintoma: o primeiro `--transcribe` nunca acaba. Solução:

```bash
HF_HUB_DISABLE_XET=1 nox --transcribe audio.wav
```

Com esta variável, o modelo `small` (~480 MB) desce em cerca de dois minutos.

## Qualidade medida (CPU, `small`, int8)

Ida e volta com a voz `pt_PT-tugão-medium`:

| Dito | Ouvido |
|---|---|
| “O Nox está a ouvir muito bem.” | “O Nox está ouvindo muito bem.” |
| “São duas e quarenta e três.” | “São duas e quarenta e três.” |
| “São duas e quarenta e três da manhã.” | “São 2h40 e 3h da manhã.” |
| “São catorze e trinta e dois.” | “São 14,32.” |

Três coisas a reter:

- **Sem `initial_prompt` o nome falha.** “Nox” saía como “nosso”, “Morse” ou
  “Não resta”. O prompt é gerado a partir de `nox.name` e `nox.wake_word`.
- **O Whisper de português pende para o Brasil.** Aparece “ouvindo” onde se
  disse “a ouvir”. Com `beam_size: 3` acerta mais vezes; com 1 escolhe sempre
  a forma brasileira.
- **Números e horas são frágeis.** Frases curtas saem certas; com mais contexto
  o modelo inventa dígitos. Para comandos chega, para ditado não.

Latência: ~2,5 s para transcrever 2 s de áudio neste CPU. O modelo `medium`
melhora os números, mas triplica o tempo. Uma GPU muda a equação.

## Porque Piper e não Kokoro

O Kokoro só tem vozes de português do Brasil, e o `config.yaml` antigo apontava
`voice: "pt-PT-male"`, que não é um id válido. O Piper tem
`pt_PT-tugão-medium`, é ONNX, corre em CPU e não arrasta PyTorch.

O STT também não usa PyTorch: o faster-whisper assenta em CTranslate2. Com
Piper + faster-whisper, o `torch` só é preciso para o Silero VAD.

## Decisões pendentes

**Wake word.** O openWakeWord não traz um modelo "hey nox" — os modelos prontos
são alexa, hey jarvis, hey mycroft. É preciso treinar um modelo custom (notebook
oficial, treina com voz sintética, ~1h).

A alternativa seria o Porcupine da Picovoice, mas não é gratuito: o console
oferece um teste de 7 dias e a partir daí o licenciamento é comercial, negociado
com vendas. Além disso, exige uma AccessKey validada periodicamente com os
servidores da Picovoice, o que quebra o modo offline. Fica como plano B: dá para
usar os 7 dias para comparar a taxa de falsos positivos com o modelo treinado.

A opção local mantém o princípio local-first: Apache 2.0, sem chave, sem rede.

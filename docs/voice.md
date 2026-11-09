# Voz

Pipeline: `áudio -> VAD -> STT -> LLM -> TTS -> áudio`.

| Etapa | Extra | Biblioteca | Estado |
|---|---|---|---|
| Captura | `audio` | sounddevice | **funcional** |
| Wake word | `wake` | openwakeword | contrato + duplos |
| VAD | `vad` | webrtcvad | **funcional** |
| STT | `stt` | faster-whisper | **funcional** |
| TTS | `tts` | piper | **funcional** |
| TTS online | `edge` | edge-tts | **funcional** |

Instalar tudo: `pip install -e ".[voice]"`.

Sem os extras, o Nox arranca em modo texto e `nox --check` indica o que falta.
Nenhum áudio sai do PC sem confirmação explícita.

## Conversa por voz

```bash
nox --voice                   # microfone
nox --voice --input a.wav     # o mesmo pipeline, a partir de um ficheiro
nox --devices                 # lista as entradas de áudio
```

O loop é: microfone -> `Segmenter` (WebRTC VAD) -> faster-whisper -> agente ->
Piper -> altifalante. Sem wake word, o Nox ouve sempre: `--voice` é conversa
contínua até Ctrl+C.

`--input` existe para testar sem falar ao computador. Um WAV com 0,5 s de
silêncio antes e 1 s depois atravessa o pipeline todo e produz a resposta falada.

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

## Vozes disponíveis

| Provider | Vozes | Onde corre | Como soa |
|---|---|---|---|
| `piper` | `pt_PT-tugão-medium` | local (ONNX) | seca, robótica, mas honesta |
| `edge` | `pt-PT-DuarteNeural`, `pt-PT-RaquelNeural` | rede (Microsoft) | natural, com respiração e entoação |

Para trocar, duas linhas no `config.yaml`:

```yaml
tts:
  provider: "edge"
  voice: "pt-PT-RaquelNeural"
```

O `edge` manda o texto do Nox para a Microsoft — não é local-first. É a opção
para quem quer a melhor voz e aceita a rede; o Piper é a opção offline. O
`pt-PT-DuarteNeural` é masculino, o `pt-PT-RaquelNeural` feminino.

## Porque Piper e não Kokoro

O Kokoro só tem vozes de português do Brasil, e o `config.yaml` antigo apontava
`voice: "pt-PT-male"`, que não é um id válido. O Piper tem
`pt_PT-tugão-medium`, é ONNX, corre em CPU e não arrasta PyTorch.

O STT também não usa PyTorch: o faster-whisper assenta em CTranslate2. Com
Piper + faster-whisper, o `torch` só é preciso para o Silero VAD — e o VAD por
omissão é o do WebRTC, que também não precisa.

## Latência do loop completo

Medido neste CPU (i5/Ryzen, `small` int8), por turno: ~0,7 s de silêncio para o
`Segmenter` fechar a frase, ~2,5 s de transcrição, ~1 s de modelo (quando não é
resposta local) e ~1,5 s de síntese. Dá cerca de **5 segundos** entre acabar de
falar e ouvir a resposta. É o próximo alvo a atacar: streaming do STT e frases
curtas do TTS.

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

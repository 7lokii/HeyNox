# Voz

Pipeline: `áudio -> VAD -> STT -> LLM -> TTS -> áudio`.

| Etapa | Extra | Biblioteca prevista | Estado |
|---|---|---|---|
| Captura | `audio` | sounddevice | contrato + `FakeSource` |
| Wake word | `wake` | openwakeword | contrato + duplos |
| VAD | `vad` | silero-vad | contrato + `EnergyVad` |
| STT | `stt` | faster-whisper | contrato + `ScriptedTranscriber` |
| TTS | `tts` | kokoro | contrato + `NullSynthesizer` |

Instalar tudo: `pip install -e ".[voice]"`.

Sem os extras, o Nox arranca em modo texto e `nox --check` indica o que falta.
Nenhum áudio sai do PC sem confirmação explícita.

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

**TTS em pt-PT.** O Kokoro só tem vozes de português do Brasil, e o
`config.yaml` aponta `voice: "pt-PT-male"`, que não é um id válido do Kokoro.
Para pt-PT a alternativa é o Piper (`pt_PT-tugão-medium`). Enquanto não se
decidir, o modo texto não usa TTS.

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
oficial, treina com voz sintética, ~1h) ou trocar para o Porcupine da Picovoice,
que exige chave e é serviço externo. A opção local mantém o princípio local-first.

**TTS em pt-PT.** O Kokoro só tem vozes de português do Brasil, e o
`config.yaml` aponta `voice: "pt-PT-male"`, que não é um id válido do Kokoro.
Para pt-PT a alternativa é o Piper (`pt_PT-tugão-medium`). Enquanto não se
decidir, o modo texto não usa TTS.

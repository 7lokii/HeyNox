# Voz

Pipeline: `áudio -> VAD -> STT -> LLM -> TTS -> áudio`.

| Etapa | Extra | Biblioteca prevista |
|---|---|---|
| Captura | `audio` | sounddevice |
| Wake word | `wake` | openwakeword |
| VAD | `vad` | silero-vad |
| STT | `stt` | faster-whisper |
| TTS | `tts` | kokoro |

Instalar tudo: `pip install -e ".[voice]"`.

Sem os extras, o Nox arranca em modo texto e `nox --check` indica o que falta.
Nenhum áudio sai do PC sem confirmação explícita.

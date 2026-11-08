# Arquitetura

```text
Microfone -> Wake word ("Hey Nox") -> VAD -> STT -> Orquestrador -> TTS -> Altifalante
                                                        |
                                                        +-> memória, router LLM, ferramentas
```

## Decisões da Fase 0

- **Núcleo sem dependências pesadas.** Em `pyproject.toml`, áudio, wake word, VAD, STT e
  TTS vivem em extras (`audio`, `wake`, `vad`, `stt`, `tts`, `voice`). `nox.optional`
  faz o import lazy e explica qual extra instalar quando falta um módulo.
- **Configuração tipada.** `nox/config.py` valida o `config.yaml` com pydantic.
  Erros de configuração dão mensagem clara e código de saída 2, não stack trace.
- **Segredos fora do código.** `.env` é carregado com `python-dotenv` sem sobrepor
  variáveis já definidas no ambiente; o `.gitignore` bloqueia `.env*`.
- **Estado de arranque observável.** `nox --check` valida config + ambiente e lista
  o que falta para o modo voz.

## Próxima fase

Fase 1 liga os módulos `audio/`, `speech/`, `brain/` através de interfaces
propostas com implementações fake para testes sem hardware.

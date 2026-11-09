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

## Decisões da Fase 1

- **Áudio é `bytes`, não `numpy`.** `nox.audio.types.Pcm` é PCM 16 bits mono
  little-endian. O núcleo continua sem dependências; os adaptadores reais
  convertem à entrada e à saída. Consequência: os testes correm sem microfone.
- **Contratos antes de implementações.** `AudioSource`, `WakeWordDetector`,
  `VoiceActivityDetector`, `Transcriber` e `Synthesizer` são Protocols. Cada um
  tem um duplo determinístico (`FakeSource`, `AlwaysAwake`, `EnergyVad`,
  `ScriptedTranscriber`, `NullSynthesizer`) para testar o loop completo.
- **`Segmenter` fecha as frases.** Junta blocos entre a primeira fala e 700 ms de
  silêncio, guarda 300 ms de pré-roll para não cortar a primeira sílaba e
  descarta ruídos com menos de 300 ms.
- **Respostas locais antes do modelo.** `Agent.local_answer` responde a horas,
  data e agradecimentos sem rede. Só enunciados com até cinco palavras passam
  por aqui, para não responder à hora errada a perguntas como "a que horas é o
  jantar?".
- **Sem chave, o Nox não morre.** `UnconfiguredLlm` deixa o arranque e as
  respostas locais a funcionar; o erro só aparece quando o modelo é necessário.

## Próxima fase

Fase 1 liga os módulos `audio/`, `speech/`, `brain/` através de interfaces
propostas com implementações fake para testes sem hardware.

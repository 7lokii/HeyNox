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
- **STT e TTS sem PyTorch.** faster-whisper corre em CTranslate2 e o Piper em
  ONNX Runtime. O `torch` fica só para o Silero VAD, o que tira ~2 GB ao
  instalador.
- **O ciclo fecha sem microfone.** `--speak` grava WAV, `--transcribe` lê WAV e
  `nox/audio/wav.py` converte entre os dois. O teste de ida e volta
  (TTS -> WAV -> STT) valida o pipeline antes de existir hardware.
- **Reamostragem em Python.** `nox.audio.types.resample` faz interpolação
  linear: o Piper produz 22,05 kHz e o Whisper quer 16 kHz.
- **VAD do WebRTC, não do Silero.** `webrtcvad` é 10 KB e não puxa PyTorch. O
  Silero fica no extra `silero` para quem quiser comparar.
- **`VoiceLoop` com peças injectáveis.** Fonte, segmentador, transcritor,
  sintetizador e altifalante entram no construtor, por isso o loop testa-se com
  duplos e sem hardware (`tests/test_voice.py`).
- **`WavSource` fecha o ciclo.** `nox --voice --input a.wav` corre o pipeline
  todo a partir de um ficheiro — foi assim que o loop foi validado antes de
  alguém falar ao microfone.
- **`Step` em vez de booleano.** Ler um bloco devolve `IDLE`, `TURN` ou `END`:
  uma fonte de ficheiro tem fim, um microfone não.
- **Filler em paralelo com o STT.** As frases de espera são sintetizadas no
  arranque e tocadas numa thread enquanto a transcrição corre noutra. Em série
  somavam 0,7 s ao turno; em paralelo escondem esse tempo.
- **TTS por frases.** `split_sentences` parte a resposta e a síntese da frase
  seguinte sobrepõe-se à reprodução da atual.
- **Memória em SQLite, não em Chroma.** Duas tabelas e um índice FTS5. A
  pesquisa semântica custaria dependências e um modelo de embeddings para
  ganhar pouco numa base de dezenas de factos.
- **Extração por regras, não por LLM.** Uma chamada ao modelo por turno para
  apanhar "chamo-me X" custaria latência e dinheiro; as regras apanham o que é
  dito de forma explícita e o resto fica para um extrator semântico.
- **Uma ligação SQLite por thread.** A interface serve pedidos em várias threads
  e o SQLite recusa ligações partilhadas.
- **Espectro do áudio real, não simulado.** `nox/audio/levels.py` calcula 48
  bandas por FFT e emite-as ao ritmo da reprodução; a página desenha-as em
  canvas, espelhadas no eixo vertical. Se o Nox não estiver a falar, o anel
  respira devagar em vez de fingir dados.
- **Réplica sem repetir a palavra.** Depois de responder, o Nox continua armado
  durante `wake.follow_up_s` (6 s). Uma pergunta de seguimento não obriga a
  dizer "Hey Nox" outra vez — ideia tirada do M.I.L.E.S.
- **Interface em stdlib.** `ThreadingHTTPServer` e uma página estática, sem
  framework nem build. Ouve em 127.0.0.1: não há autenticação porque quem chega
  ao porto já está na máquina. O motor corre numa thread e publica estado
  (`on_turn`/`on_status`) que a página consulta por polling.
- **Memória em SQLite, não em Chroma.** Duas tabelas e um índice FTS5. A
  pesquisa semântica custaria dependências e um modelo de embeddings para
  ganhar pouco numa base de dezenas de factos.
- **Extração por regras, não por LLM.** Uma chamada ao modelo por turno para
  apanhar "chamo-me X" custaria latência e dinheiro; as regras apanham o que é
  dito de forma explícita e o resto fica para um extrator semântico.
- **Uma ligação SQLite por thread.** A interface serve pedidos em várias threads
  e o SQLite recusa ligações partilhadas.
- **Espectro do áudio real, não simulado.** `nox/audio/levels.py` calcula 48
  bandas por FFT e emite-as ao ritmo da reprodução; a página desenha-as em
  canvas, espelhadas no eixo vertical. Se o Nox não estiver a falar, o anel
  respira devagar em vez de fingir dados.
- **Réplica sem repetir a palavra.** Depois de responder, o Nox continua armado
  durante `wake.follow_up_s` (6 s). Uma pergunta de seguimento não obriga a
  dizer "Hey Nox" outra vez — ideia tirada do M.I.L.E.S.
- **Interface em stdlib.** `ThreadingHTTPServer` e uma página estática, sem
  framework nem build. Ouve em 127.0.0.1: não há autenticação porque quem chega
  ao porto já está na máquina. O motor corre numa thread e publica estado
  (`on_turn`/`on_status`) que a página consulta por polling.
- **Barge-in com dois sinais.** O VAD e o limiar de energia têm de concordar
  durante 300 ms; um só dispara com o eco do próprio Nox. A flag está desligada
  por omissão e o áudio já lido entra no segmentador, para não perder a
  primeira palavra.
- **Memória em SQLite, não em Chroma.** Duas tabelas e um índice FTS5. A
  pesquisa semântica custaria dependências e um modelo de embeddings para
  ganhar pouco numa base de dezenas de factos.
- **Extração por regras, não por LLM.** Uma chamada ao modelo por turno para
  apanhar "chamo-me X" custaria latência e dinheiro; as regras apanham o que é
  dito de forma explícita e o resto fica para um extrator semântico.
- **Uma ligação SQLite por thread.** A interface serve pedidos em várias threads
  e o SQLite recusa ligações partilhadas.
- **Espectro do áudio real, não simulado.** `nox/audio/levels.py` calcula 48
  bandas por FFT e emite-as ao ritmo da reprodução; a página desenha-as em
  canvas, espelhadas no eixo vertical. Se o Nox não estiver a falar, o anel
  respira devagar em vez de fingir dados.
- **Réplica sem repetir a palavra.** Depois de responder, o Nox continua armado
  durante `wake.follow_up_s` (6 s). Uma pergunta de seguimento não obriga a
  dizer "Hey Nox" outra vez — ideia tirada do M.I.L.E.S.
- **Interface em stdlib.** `ThreadingHTTPServer` e uma página estática, sem
  framework nem build. Ouve em 127.0.0.1: não há autenticação porque quem chega
  ao porto já está na máquina. O motor corre numa thread e publica estado
  (`on_turn`/`on_status`) que a página consulta por polling.
- **Memória em SQLite, não em Chroma.** Duas tabelas e um índice FTS5. A
  pesquisa semântica custaria dependências e um modelo de embeddings para
  ganhar pouco numa base de dezenas de factos.
- **Extração por regras, não por LLM.** Uma chamada ao modelo por turno para
  apanhar "chamo-me X" custaria latência e dinheiro; as regras apanham o que é
  dito de forma explícita e o resto fica para um extrator semântico.
- **Uma ligação SQLite por thread.** A interface serve pedidos em várias threads
  e o SQLite recusa ligações partilhadas.
- **Espectro do áudio real, não simulado.** `nox/audio/levels.py` calcula 48
  bandas por FFT e emite-as ao ritmo da reprodução; a página desenha-as em
  canvas, espelhadas no eixo vertical. Se o Nox não estiver a falar, o anel
  respira devagar em vez de fingir dados.
- **Réplica sem repetir a palavra.** Depois de responder, o Nox continua armado
  durante `wake.follow_up_s` (6 s). Uma pergunta de seguimento não obriga a
  dizer "Hey Nox" outra vez — ideia tirada do M.I.L.E.S.
- **Interface em stdlib.** `ThreadingHTTPServer` e uma página estática, sem
  framework nem build. Ouve em 127.0.0.1: não há autenticação porque quem chega
  ao porto já está na máquina. O motor corre numa thread e publica estado
  (`on_turn`/`on_status`) que a página consulta por polling.
- **Barge-in com dois sinais.** O VAD e o limiar de energia têm de concordar
  durante 300 ms; um só dispara com o eco do próprio Nox. A flag está desligada
  por omissão e o áudio já lido entra no segmentador, para não perder a
  primeira palavra.
- **Wake word por Vosk, não por openWakeWord.** Não existe modelo "hey nox"
  treinado e treinar um exige GPU e horas. O Vosk transcreve localmente e o
  detector procura a palavra ("Nox" sai como "inox"). Só corre quando o VAD
  ouve fala, com 1,5 s de tolerância.

## Próxima fase

Fase 1 liga os módulos `audio/`, `speech/`, `brain/` através de interfaces
propostas com implementações fake para testes sem hardware.

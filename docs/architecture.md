# Arquitetura

```text
Microfone -> Wake word ("Hey Nox") -> VAD -> STT -> Agente -> TTS -> Altifalante
                                                     |
                                                     +-> memória (SQLite/FTS5)
                                                     +-> LLM (config.yaml)
                                                     +-> ferramentas + aprovações

Browser (HUD) <-> HTTP 127.0.0.1:8765 <-> NoxApp  (texto, voz, rotinas, aprovações)
                                            ^
                                            +-> bandeja (pystray) no HeyNox.exe
```

## Mapa das pastas

| Pasta | Responsabilidade | Doc |
|---|---|---|
| `nox/main.py` | CLI `nox`, todos os `--flags` | README, `docs/packaging.md` |
| `nox/config.py` | `config.yaml` tipado com pydantic | — |
| `nox/audio/` | Microfone, wake word, VAD, denoise, WAV, espectro, voz | `docs/voice.md` |
| `nox/speech/` | STT (local + Groq) e TTS (Piper + edge-tts) | `docs/voice.md` |
| `nox/brain/` | `Agent`, LLM (Anthropic/OpenAI), prompt, mensagens | `docs/voice.md` |
| `nox/memory/` | SQLite + FTS5, extração de factos | `docs/memory.md` |
| `nox/tools/` | Uma ferramenta por ficheiro + registo | `docs/tools.md` |
| `nox/safety/` | Aprovações, sandbox de caminhos, audit log | `docs/security.md` |
| `nox/integrations/` | `gh` CLI (GitHub) | `docs/tools.md` |
| `nox/automation/` | Agendador de rotinas | `docs/automation.md` |
| `nox/mcp/` | Cliente MCP por stdio | `docs/automation.md` |
| `nox/desktop/` | Janelas, captura, OCR, rato/teclado, emergência | `docs/desktop.md` |
| `nox/ui/` | Servidor HTTP, HUD (`index.html`), estado, bandeja | `docs/packaging.md` |
| `nox/skills.py` | Skills em Markdown (projeto e utilizador) | `docs/automation.md` |
| `installer/` | `.spec` gerados, hooks, Inno Setup, `build.ps1` | `docs/packaging.md` |
| `scripts/` | Pontos de entrada dos `.exe` e ferramentas de diagnóstico | — |
| `tests/fixtures/` | Amostras de voz e capturas do HUD (não são dados de execução) | — |

## Decisões transversais

- **Núcleo sem dependências pesadas.** Em `pyproject.toml`, áudio, wake word,
  VAD, STT, TTS, browser, desktop e bandeja vivem em extras (`audio`, `wake`,
  `vad`, `stt`, `tts`, `voice`, `browser`, `desktop`, `tray`). `nox.optional`
  faz o import lazy e explica qual extra instalar quando falta um módulo.
- **Configuração tipada.** `nox/config.py` valida o `config.yaml` com pydantic.
  Erros de configuração dão mensagem clara e código de saída 2, não stack trace.
- **Segredos fora do código.** `.env` é carregado com `python-dotenv` sem sobrepor
  variáveis já definidas no ambiente; o `.gitignore` bloqueia `.env*`.
- **Estado de arranque observável.** `nox --check` valida config + ambiente e lista
  o que falta para o modo voz, desktop e OCR.
- **Dados de execução fora do repo.** Notas, capturas, memória e rotinas vão
  para `%LOCALAPPDATA%\HeyNox` ou `data/` (ignorado). As amostras que servem
  os testes e o `bench_stt.py` vivem em `tests/fixtures/samples/`.

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
  data, agradecimentos e às ordens de emergência sem rede. Só enunciados com
  até cinco palavras passam por aqui, para não responder à hora errada a
  perguntas como "a que horas é o jantar?".
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
- **Réplica sem repetir a palavra.** Depois de responder, o Nox continua armado
  durante `wake.follow_up_s` (6 s). Uma pergunta de seguimento não obriga a
  dizer "Hey Nox" outra vez.
- **Barge-in com dois sinais.** O VAD e o limiar de energia têm de concordar
  durante 300 ms; um só dispara com o eco do próprio Nox. A flag está desligada
  por omissão e o áudio já lido entra no segmentador, para não perder a
  primeira palavra.
- **Wake word por Vosk, não por openWakeWord.** Não existe modelo "hey nox"
  treinado e treinar um exige GPU e horas. O Vosk transcreve localmente e o
  detector procura a palavra ("Nox" sai como "inox"). Só corre quando o VAD
  ouve fala, com 1,5 s de tolerância.

## Decisões da Fase 2 (memória e interface)

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
- **Interface sem framework.** `ThreadingHTTPServer` (stdlib) e uma página
  estática, sem build. Ouve em `127.0.0.1`: não há autenticação porque quem
  chega ao porto já está na máquina. O motor corre numa thread e publica
  estado (`on_turn`/`on_status`) que a página consulta por polling.

## Decisões das Fases 3–6 (ferramentas, automação e PC)

Cada uma está detalhada no respetivo documento; em resumo:

- **Aprovações na interface** (`nox/safety/approvals.py`): a ferramenta bloqueia
  à espera, a página mostra o resumo/diff, a decisão expira. Ver `docs/security.md`.
- **Uma ferramenta por ficheiro em `nox/tools/`**, todas a passar pelo mesmo
  registo e pelos mesmos limites (sandbox de caminhos, audit log). A tabela
  completa está em `docs/tools.md`.
- **GitHub pelo `gh` autenticado**, não por API própria: reutiliza as
  credenciais e as regras do utilizador.
- **Sub-agentes em `ThreadPoolExecutor`**, com contexto limpo e sem
  `spawn_agent` (sem recursão). Ver `docs/automation.md`.
- **MCP por stdio**, com ferramentas expostas como `mcp_<servidor>_<ferramenta>`
  e desligado por omissão. Ver `docs/automation.md`.
- **Desktop com allowlist e emergência**: um `EMERGENCY` por processo corta
  todas as ações (incluindo capturas). Ver `docs/desktop.md`.

## Decisões do empacotamento

- **`HeyNox.exe` windowed** abre a interface; sem consola, avisos e erros vão
  para `%LOCALAPPDATA%\HeyNox\logs\nox.log` e as exceções fatais para uma caixa
  nativa.
- **Bandeja em vez de processo invisível**: o `.exe` não tem janela, por isso o
  `pystray` dá-lhe «Abrir interface», «Ouvir» e «Sair».
- **Instância única** pelo `ui.port` guardado, para um segundo clique reabrir o
  browser em vez de subir outro servidor.
- **Python 3.11 no build** (combinação validada de torch/ctranslate2/piper/winrt).
  Ver `docs/packaging.md`.

# Roadmap

Segue o `spec.md` (§12). Estado atual:

- [x] **Fase 0 — Fundações.** Estrutura de pastas, config validado, import lazy dos
  extras, `.env.example`, `.gitignore`, `README.md`, testes, GitHub Actions.
- [ ] **Fase 1 — Voz básica.** Em curso.
  - [x] Contratos do pipeline + duplos de teste sem hardware.
  - [x] Modo texto (`nox --text`, `nox --say`) com LLM configurável.
  - [x] Respostas locais para horas, data e agradecimentos.
  - [x] STT local (faster-whisper) — `nox --transcribe`.
  - [x] TTS local (Piper `pt_PT-tugão-medium`) e opção neural (`edge-tts`).
  - [x] Captura de microfone real (sounddevice) — `nox --voice`.
  - [x] VAD WebRTC + loop de conversação completo.
  - [x] Wake word "Nox" / "Ei Nox" / "Hey Nox" (Vosk, ver `docs/voice.md`).
  - [x] Portão de ruído adaptativo e corte espectral antes do STT.
  - [x] Latência: filler, TTS por frases, silêncio de 500 ms.
  - [x] Interrupção da fala (barge-in), opcional.
  - [x] Interface web local (`nox --ui`, aberta pelo `HeyNox.exe`).
  - [x] HUD com espectro do áudio real e réplica sem repetir a palavra.
- [x] **Fase 2 — Memória.** SQLite + FTS5, ver `docs/memory.md`.
  - [x] Memória de conversa (retomada entre sessões).
  - [x] Factos duradouros (nome, preferências, notas) por regras.
  - [x] Recall por palavra (FTS5) injetado no system prompt.
  - [x] Comandos: "o que sabes sobre mim", "esquece X", "esquece tudo".
  - [x] Exportar/importar JSON e `--memory-reset`.
  - [ ] Memória semântica (Chroma) — adiada, ver `docs/memory.md`.
- [ ] **Fase 3 — Ferramentas seguras.**
- [ ] **Fase 4 — GitHub.**
- [ ] **Fase 5 — Automação avançada.**
- [ ] **Fase 6 — Controlo do PC.**

## Notas

- Repositório remoto `7lokii/HeyNox` ainda não criado nem ligado (decisão: só local).
- A versão 0.1 do spec (§19) inclui etapas das Fases 1 a 4.

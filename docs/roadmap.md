# Roadmap

Segue o `spec.md` (§12). Estado atual:

- [x] **Fase 0 — Fundações.** Estrutura de pastas, config validado, import lazy dos
  extras, `.env.example`, `.gitignore`, `README.md`, testes, GitHub Actions.
- [ ] **Fase 1 — Voz básica.** Em curso.
  - [x] Contratos do pipeline + duplos de teste sem hardware.
  - [x] Modo texto (`nox --text`, `nox --say`) com LLM configurável.
  - [x] Respostas locais para horas, data e agradecimentos.
  - [x] STT local (faster-whisper) — `nox --transcribe`.
  - [x] TTS local (Piper `pt_PT-tugão-medium`) — `nox --speak`.
  - [ ] Captura de microfone real (sounddevice).
  - [ ] Wake word "Hey Nox" — modelo treinado, ver `docs/voice.md`.
  - [ ] Interrupção da fala.
- [ ] **Fase 2 — Memória.**
- [ ] **Fase 3 — Ferramentas seguras.**
- [ ] **Fase 4 — GitHub.**
- [ ] **Fase 5 — Automação avançada.**
- [ ] **Fase 6 — Controlo do PC.**

## Notas

- Repositório remoto `7lokii/HeyNox` ainda não criado nem ligado (decisão: só local).
- A versão 0.1 do spec (§19) inclui etapas das Fases 1 a 4.

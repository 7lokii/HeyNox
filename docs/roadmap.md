# Roadmap

Segue o `spec.md` (§12). Estado atual:

- [x] **Fase 0 — Fundações.** Estrutura de pastas, config validado, import lazy dos
  extras, `.env.example`, `.gitignore`, `README.md`, testes, GitHub Actions.
- [x] **Fase 1 — Voz básica.**
  - [x] Contratos do pipeline + duplos de teste sem hardware.
  - [x] Modo texto (`nox --text`, `nox --say`) com LLM configurável.
  - [x] Respostas locais para horas, data e agradecimentos.
  - [x] STT local (faster-whisper) — `nox --transcribe`.
  - [x] TTS local (Piper `pt_PT-tugão-medium`) e opção neural (`edge-tts`).
  - [x] Captura de microfone real (sounddevice) — `nox --voice`.
  - [x] VAD WebRTC + loop de conversação completo.
  - [x] Wake word "Nox" / "Ei Nox" / "Hey Nox" (Vosk, ver `docs/voice.md`).
  - [x] Portão de ruído adaptativo e corte espectral antes do STT.
  - [x] Impressão vocal com vários perfis (opcional).
  - [x] Vocabulário restrito: "Nox" sozinho passa a ser reconhecido.
  - [x] Latência: filler, TTS por frases, silêncio de 500 ms.
  - [x] STT na cloud (Groq) com fallback local automático.
  - [x] Interrupção da fala (barge-in), opcional.
  - [x] HUD em TypeScript (`ui/`, Vite + React) servido pelo motor.
  - [x] Janela de desktop própria (`nox --desktop`, pywebview + WebView2);
    `nox --ui` fica como via de diagnóstico no browser.
  - [x] HUD com espectro do áudio real e réplica sem repetir a palavra.
- [x] **Fase 2 — Memória.** SQLite + FTS5, ver `docs/memory.md`.
  - [x] Memória de conversa (retomada entre sessões).
  - [x] Factos duradouros (nome, preferências, notas) por regras.
  - [x] Recall por palavra (FTS5) injetado no system prompt.
  - [x] Comandos: "o que sabes sobre mim", "esquece X", "esquece tudo".
  - [x] Exportar/importar JSON e `--memory-reset`.
  - [ ] Memória semântica (Chroma) — adiada, ver `docs/memory.md`.
- [x] **Fase 3 — Ferramentas seguras.** Ver `docs/tools.md`.
  - [x] Ler ficheiros e listar pastas dentro da sandbox.
  - [x] Shell seguro por allowlist, sem `shell=True`.
  - [x] Audit log em JSONL.
  - [x] Loop de tool_use (até 6 passos).
  - [x] Escrever e editar ficheiros com diff.
  - [x] Sistema de aprovações na interface (com expiração).
  - [x] Pesquisa web e leitura de páginas.
  - [x] Browser com Playwright (texto, links, captura).
  - [x] Notas (além dos factos da memória).
- [x] **Fase 4 — GitHub.** Via `gh` autenticado, ver `docs/tools.md`.
  - [x] Autenticação GitHub (reutiliza `gh auth`).
  - [x] Clonar e atualizar repositórios.
  - [x] Criar branches e mudar de branch.
  - [x] Criar commits.
  - [x] Correr testes antes do push.
  - [x] Abrir pull requests.
  - [x] Ler issues.
  - [x] Criar issues.
  - [x] Responder a comentários em PRs e issues.
- [x] **Fase 5 — Automação avançada.** Ver `docs/automation.md`.
  - [x] Tarefas agendadas e rotinas diárias (`daily`, `every`, `once`).
  - [x] Sub-agentes com contexto limpo e sem recursão.
  - [x] Skills personalizadas em Markdown (projeto e utilizador).
  - [x] Integração MCP por stdio (servidores e ferramentas `mcp_*`).
  - [x] Plugins através de servidores MCP.
  - [x] Browser com click/fill, com aprovação.
- [x] **Fase 6 — Controlo do PC.** Ver `docs/desktop.md`.
  - [x] Deteção de janelas (listar e focar).
  - [x] Controlo de apps (allowlist de executáveis).
  - [x] Controlo de teclado e rato, com aprovação por ação.
  - [x] Visão do ecrã (capturas em `data/screenshots/`).
  - [x] OCR com o motor do Windows (Português).
  - [x] Confirmação por ação.
  - [x] Sandbox (allowlist, validação de teclas, limites).
  - [x] Modo de emergência (botão, voz e ferramenta).
- [x] **Empacotamento e distribuição.** Ver `docs/packaging.md`.
  - [x] `dist\HeyNox` (agente completo) e `dist\nox` (CLI de diagnóstico).
  - [x] Instalador Inno Setup `HeyNox-Setup.exe`.
  - [x] Ícone na bandeja com «Abrir interface», «Ouvir» e «Sair».
  - [x] Instância única (um segundo arranque reabre a janela ou o browser).
  - [ ] Revalidar o loop de ferramentas via LLM dentro do `.exe` (Selora esteve
    em manutenção durante o build).
  - [ ] Instalação silenciosa do `Setup.exe` (precisa de UAC interactivo).
  - [ ] Assinatura Authenticode.
  - [ ] Build Linux/macOS (`build.sh`).
- [ ] **Versão 1.0** (`spec.md` §20). Falta sobretudo:
  - [ ] Memória semântica (Chroma) — adiada, ver `docs/memory.md`.
  - [ ] Router multi-modelo.
  - [ ] Telemetria local opcional.
  - [ ] Interface web completa (o HUD atual cobre conversa, voz, aprovações,
    memória, rotinas e emergência).

## Notas

- **Tauri ficou de fora.** O pedido era TypeScript + Tauri. Falta a toolchain
  Rust e o MSVC + Windows SDK para ligar o binário; as duas ocupam 6 a 8 GB e
  o `C:` tem 6,1 GB livres. A janela é feita com `pywebview`, que usa o
  WebView2 já instalado. O HUD em `ui/` é o mesmo nos dois caminhos.

- Repositório remoto `7lokii/HeyNox` ainda não criado nem ligado (decisão: só local).
- A versão 0.1 do spec (§19) inclui etapas das Fases 1 a 4.
- Contagem de testes: 379 (3 saltam sem rede/modelos; ver `NOX_SLOW_TESTS`).
- Validação da janela: `windows-latest` no CI compila `ui/dist` antes do
  PyInstaller. Localmente, `nox --desktop` abre a janela e o HUD desenha.

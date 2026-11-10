# HeyNox

**HeyNox** é um assistente pessoal de IA local-first chamado **Nox**.

O Nox ouve por “Hey Nox”, transcreve a fala, compreende pedidos,
executa ferramentas seguras, guarda memória e pode ajudar em projetos
GitHub através de branches, testes e pull requests.

## Funcionalidades

- Wake word “Hey Nox”, VAD, barge-in e réplica sem repetir a palavra
- Voz bidirecional (Piper offline ou `edge-tts` neural)
- Transcrição na cloud (Groq) com fallback local
- Memória de longo prazo (SQLite + FTS5) e perfis de voz
- Ferramentas de ficheiros, shell, web, browser e notas, com aprovações e diff
- GitHub pelo `gh`: clone, branches, commit, testes antes do push, PRs e issues
- Rotinas agendadas, sub-agentes, skills em Markdown e servidores MCP
- Controlo do PC: janelas, OCR, rato e teclado, com emergência
- Janela própria de desktop (HUD), não um separador do browser, e ícone na bandeja
- Auditoria de todas as ferramentas em JSONL
- Instalador Windows com `HeyNox.exe` e `nox.exe`

## Estado

Todas as fases do [`roadmap`](docs/roadmap.md) (0 a 6) estão fechadas e o
projeto está empacotado. O que falta para a 1.0 está listado no roadmap;
resumindo: memória semântica, router multi-modelo, telemetria local opcional e
build Linux/macOS.

A transcrição usa `whisper-large-v3-turbo` na Groq (~0,4 s); sem rede cai
sozinha para o faster-whisper local.

A interface está em TypeScript (`ui/`) e corre dentro de uma janela nativa
sobre o WebView2 do Windows. O motor é Python e não mudou. Ver
[`docs/interface.md`](docs/interface.md).

## Abrir o Nox (Windows)

Três formas, as três abrem a mesma janela:

| Forma | Como | Quando |
|---|---|---|
| Comando | `nox --desktop` | tens o projeto instalado em Python; é o caminho de desenvolvimento |
| Instalador | `HeyNox-Setup.exe`, depois o atalho do menu Iniciar | uso normal, com desinstalador e atalhos |
| Portátil | extrair `HeyNox-<versao>-windows-x64-portable.zip` e correr `HeyNox\HeyNox.exe` | sem instalar nada, por exemplo numa pen |

Os dois artefactos saem do mesmo build:

```powershell
powershell -ExecutionPolicy Bypass -File installeruild.ps1
# dist\HeyNox-Setup.exe
# dist\HeyNox-<versao>-windows-x64-portable.zip
```

O portátil guarda os dados em `%LOCALAPPDATA%\HeyNox`, igual ao instalado.
Apagar a pasta não apaga a memória; para isso existe `nox --memory-reset`.

## Uso

```bash
nox --desktop                # janela própria do HeyNox (é o que o .exe faz)
nox --ui                     # o mesmo HUD no browser, para diagnóstico
nox --check                  # configuração e ambiente
nox --text                   # conversa por texto
nox --voice                  # conversa por voz: diz "Hey Nox"
nox --voice --no-wake        # ouve sempre, sem palavra de ativação
nox --voice --input a.wav    # o mesmo pipeline, a partir de um ficheiro
nox --devices                # lista os microfones disponíveis
nox --say "que horas são?"   # uma resposta e sai
nox --speak "Bom dia."       # sintetiza para WAV
nox --transcribe audio.wav   # transcreve um WAV

nox --enroll                 # inscreve a tua voz (3 amostras)
nox --enroll-files a.wav b.wav c.wav   # o mesmo, a partir de ficheiros
nox --voiceprint             # vê os perfis de voz
nox --forget-voice --name eu # apaga um perfil
nox --test-stt 4             # grava 4 s e mostra o que o STT ouviu

nox --routines               # lista as rotinas e o estado
nox --memory                 # o que o Nox sabe sobre ti
nox --forget Rui             # esquece o que contiver "Rui"
nox --memory-reset           # apaga factos e histórico
nox --memory-export a.json   # exporta / --memory-import para importar
```

Perguntas simples — horas, data, agradecimentos — são respondidas localmente,
sem rede e sem custo. Tudo o resto vai ao modelo configurado no `config.yaml`;
a chave fica em `NOX_LLM_API_KEY`, no `.env`.

## Interface

A interface local (aberta pelo `HeyNox.exe`) é um HUD: o nome no centro, um anel
com o **espectro real** do áudio que está a sair, a conversa à direita e a
memória por baixo. Não é uma animação: os níveis vêm do PCM que o altifalante
está a reproduzir (`/api/levels`, 48 bandas a 25 fps).

Abrir o `HeyNox.exe` outra vez não cria uma segunda instância: reabre o browser
na que já está a correr. Para fechar, usa **Sair** no ícone `HeyNox` da
bandeja — o mesmo menu tem «Ouvir» para ligar/desligar a voz.

## Instalação

```bash
git clone https://github.com/7lokii/HeyNox.git
cd HeyNox
python -m venv .venv
```

Ativar o ambiente (Windows PowerShell):

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Instalar o núcleo (sem modelos nem áudio) ou com os extras que quiseres:

```bash
pip install -e ".[dev]"        # núcleo + ferramentas de desenvolvimento
pip install -e ".[voice]"      # microfone, wake word, VAD, STT e TTS local
pip install -e ".[browser]"    # Playwright (falta o Chromium, ver docs/tools.md)
pip install -e ".[desktop]"    # rato, teclado, capturas e OCR do Windows
pip install -e ".[tray]"       # ícone na bandeja (pystray)
```

Configurar e verificar:

```bash
cp .env.example .env         # Windows: copy .env.example .env
nox --check
```

Na app (`.exe`), não há ficheiros para editar: o primeiro arranque abre um ecrã
de configuração dentro da própria janela, onde se escolhe o fornecedor do
modelo, se cola a chave, se testa e se escolhe o microfone. Fica gravado em
`%LOCALAPPDATA%\HeyNox`. Depois, a engrenagem no topo abre as mesmas opções e
mais três coisas: **acesso total**, **atualizações** e onde estão os dados.

## Acesso total e atualizações

**Acesso total** (Definições → Acesso total) desliga os pedidos de aprovação:
o Nox passa a escrever ficheiros, correr comandos e mexer no rato sem
perguntar. Tudo o que faz nesse modo fica no `logs/audit.jsonl`, e o botão
**Parar** do topo continua a bloquear o controlo do PC. Desligado por omissão.

**Atualizações** vêm de `releases/latest.json`. A app verifica no arranque (e a
pedido), compara versões e, na versão portátil, descarrega o zip novo, confere
o `sha256` do manifesto e troca a pasta quando a app fecha. Sem `sha256` no
manifesto, nada é aplicado. Instalações em `Program Files` não se trocam
sozinhas: mostram a versão nova e o caminho do instalador.

## Instalador Windows

O build gera `dist\HeyNox-Setup.exe` (Inno Setup) com `HeyNox.exe`, `nox.exe` e
arranque opcional. Ver [`docs/packaging.md`](docs/packaging.md).

```powershell
winget install astral-sh.uv JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```

## Estrutura

```text
nox/
├── main.py        CLI `nox`: todos os argumentos
├── config.py      config.yaml tipado (pydantic)
├── optional.py    Import lazy das dependências pesadas (extras)
├── paths.py       Caminhos do projeto, do pacote e dos dados do utilizador
├── audio/         Microfone, wake word, VAD, WAV, espectro, voz
├── speech/        STT (local e Groq) e TTS (Piper e edge-tts)
├── brain/         Agente, cliente LLM e prompts
├── memory/        Memória SQLite + FTS5
├── tools/         Uma ferramenta por ficheiro (ficheiros, shell, web, GitHub…)
├── safety/        Aprovações, sandbox e audit log
├── integrations/  GitHub (gh CLI)
├── automation/    Rotinas agendadas
├── mcp/           Cliente MCP (stdio)
├── desktop/       Janelas, captura, OCR e controlo do PC
├── ui/            Servidor local, HUD, janela nativa e ícone da bandeja
└── skills.py      Skills em Markdown

ui/                HUD em TypeScript (Vite + React); compila para ui/dist
installer/         PyInstaller (.spec gerados, hooks) e Inno Setup
scripts/           Pontos de entrada dos .exe e bench_stt.py
tests/             Suite (pytest) e fixtures/ com amostras de voz
docs/              Um documento por área (ver abaixo)
```

Documentação: [`roadmap.md`](docs/roadmap.md),
[`architecture.md`](docs/architecture.md), [`voice.md`](docs/voice.md),
[`memory.md`](docs/memory.md), [`tools.md`](docs/tools.md),
[`security.md`](docs/security.md), [`automation.md`](docs/automation.md),
[`desktop.md`](docs/desktop.md) e [`packaging.md`](docs/packaging.md).

## Segurança

O Nox não acede a `.env`/`.git`, não sai de `security.allowed_paths`, não corre
comandos fora da allowlist sem aprovação e pede confirmação antes de escrever
ficheiros, controlar o PC ou abrir PRs. Tudo fica no audit log em JSONL.
Ver [`docs/security.md`](docs/security.md).

## Licença

MIT, se confirmado pelo autor.

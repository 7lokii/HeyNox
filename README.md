# HeyNox

**HeyNox** é um assistente pessoal de IA local-first chamado **Nox**.

O Nox ouve por “Hey Nox”, transcreve a fala, compreende pedidos,
executa ferramentas seguras, guarda memória e pode ajudar em projetos
GitHub através de branches, testes e pull requests.

## Funcionalidades planeadas

- Wake word “Hey Nox”
- Voz bidirecional
- Transcrição na cloud (Groq) com fallback local
- Memória de longo prazo
- Ferramentas de ficheiros, shell e browser
- Integração GitHub
- Pull requests com revisão humana
- Auditoria de ações
- Modo offline parcial
- Interface web local

## Estado

Projeto em desenvolvimento. Fase 0 (fundações) concluída: estrutura,
configuração validada, CLI de verificação de ambiente, testes e CI.
O instalador Windows também já está pronto.

A Fase 1 está fechada: pipeline de voz completo, wake word "Nox"/"Ei Nox"/
"Hey Nox", VAD, barge-in e HUD. A Fase 2 também: memória em SQLite com FTS5.

A Fase 3 está fechada: lê, escreve e edita ficheiros, corre comandos permitidos,
pesquisa na web, abre páginas num browser real e guarda notas. Tudo o que é
sensível pede aprovação na interface, com diff. Ver `docs/tools.md`.

A Fase 4 também: clona repositórios, cria branches, faz commits e push (com
testes antes), abre e comenta PRs e issues, através do `gh` já autenticado.

A Fase 5 está fechada: rotinas agendadas, sub-agentes, skills em Markdown e
servidores MCP. Ver `docs/automation.md`.

A Fase 6 também: o Nox lista janelas, captura o ecrã, lê texto com OCR e pode
clicar, escrever e abrir apps — sempre com aprovação e um botão de emergência.
Ver `docs/desktop.md`.

A transcrição usa `whisper-large-v3-turbo` na Groq (~0,4 s); sem rede cai
sozinha para o faster-whisper local.

## Uso

```bash
nox --ui                     # interface web local (o .exe abre isto)
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
nox --voiceprint            # vê ou apaga o perfil de voz

nox --enroll                 # inscreve a tua voz (3 amostras)
nox --voiceprint            # vê ou apaga o perfil de voz

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

Instalar o núcleo (sem modelos nem áudio) ou com os extras de voz:

```bash
pip install -e ".[dev]"      # núcleo + ferramentas de desenvolvimento
pip install -e ".[voice]"    # microfone, wake word, VAD, STT e TTS local
```

Configurar e verificar:

```bash
cp .env.example .env         # Windows: copy .env.example .env
nox --check
```

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
├── main.py        Ponto de entrada (CLI `nox`)
├── config.py      Carregamento e validação do config.yaml
├── optional.py    Import lazy das dependências pesadas
├── audio/         Microfone, wake word, VAD, gravador
├── speech/        STT e TTS
├── brain/         Agente, router LLM, memória, prompts, planner
├── tools/         Ficheiros, shell, browser, GitHub, notas, etc.
├── integrations/  Fornecedores LLM
├── ui/            Interface web local
└── safety/        Permissões, sandbox, segredos, audit log

installer/         Build Windows: PyInstaller + Inno Setup
scripts/           Pontos de entrada dos .exe
```

## Segurança

O Nox não faz push direto para `main`, não acede a segredos sem
permissão e pede confirmação antes de ações destrutivas.

## Licença

MIT, se confirmado pelo autor.

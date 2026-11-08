# HeyNox

**HeyNox** é um assistente pessoal de IA local-first chamado **Nox**.

O Nox ouve por “Hey Nox”, transcreve a fala, compreende pedidos,
executa ferramentas seguras, guarda memória e pode ajudar em projetos
GitHub através de branches, testes e pull requests.

## Funcionalidades planeadas

- Wake word “Hey Nox”
- Voz bidirecional
- Transcrição local
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
O pipeline de voz chega na Fase 1.

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
```

## Segurança

O Nox não faz push direto para `main`, não acede a segredos sem
permissão e pede confirmação antes de ações destrutivas.

## Licença

MIT, se confirmado pelo autor.

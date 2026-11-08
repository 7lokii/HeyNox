# HeyNox — Especificação do Produto e Plano Técnico

**Produto:** HeyNox  
**Agente:** Nox  
**Autor:** 7lokii  
**Perfil GitHub:** https://github.com/7lokii  
**Repositório previsto:** https://github.com/7lokii/HeyNox  
**Idioma principal:** Português de Portugal  
**Objetivo:** Criar um assistente pessoal de IA local-first, com voz, wake word, memória, ferramentas seguras, automação do PC e integração GitHub.

## 1. Visão do produto

HeyNox é um assistente pessoal chamado **Nox** que funciona no computador do utilizador.

O Nox deve conseguir:

- Ouvir continuamente pelo microfone.
- Ativar-se com a expressão **“Hey Nox”**.
- Transcrever voz para texto.
- Compreender pedidos em português de Portugal.
- Executar tarefas através de ferramentas seguras.
- Responder por voz e por texto.
- Guardar memória de curto e longo prazo.
- Trabalhar em projetos locais e no GitHub.
- Criar branches, commits, testes e pull requests.
- Automatizar tarefas repetitivas no browser e no sistema.
- Controlar aplicações do PC apenas quando autorizado.

O Nox não deve ser um chatbot simples. Deve ser um agente com ferramentas, memória, permissões, auditoria e capacidade de execução.

## 2. Identidade do Nox

| Campo | Valor |
|---|---|
| Nome do agente | Nox |
| Nome do projeto | HeyNox |
| Wake word principal | “Hey Nox” |
| Idioma padrão | Português de Portugal |
| Estilo | Calmo, direto, útil, profissional, ligeiramente futurista |
| Tom de voz | Curto ao falar; detalhado no ecrã |
| Comportamento | Pergunta antes de ações destrutivas ou irreversíveis |

### Exemplos de interação

**Utilizador:** “Hey Nox, que horas são?”  
**Nox:** “São 23:11.”

**Utilizador:** “Hey Nox, abre o meu projeto.”  
**Nox:** “A abrir o projeto autorizado.”

**Utilizador:** “Hey Nox, corrige o teste que está a falhar.”  
**Nox:** “Vou analisar o repositório, criar uma branch e propor alterações. Quer que abra um pull request quando os testes passarem?”

**Utilizador:** “Hey Nox, apaga a pasta temporária.”  
**Nox:** “Isto é irreversível. Confirma que quero apagar a pasta X?”

**Utilizador:** “Hey Nox, para.”  
**Nox:** “A parar a tarefa atual.”

## 3. Princípios de produto

1. **Local-first:** wake word, VAD, transcrição e memória devem funcionar localmente sempre que possível.
2. **Privacidade por defeito:** nenhum áudio, ficheiro ou segredo sai do PC sem autorização explícita.
3. **Mínimo privilégio:** o Nox só acede ao que precisa para a tarefa atual.
4. **Human-in-the-loop:** ações destrutivas, compras, envios, push para main e alterações de sistema exigem confirmação.
5. **Auditabilidade:** toda a ação é registada num log com timestamp, comando, resultado e ficheiros alterados.
6. **Modularidade:** cada capacidade é um módulo substituível.
7. **Resiliência:** falhas de rede, API, microfone ou modelo não devem bloquear todo o sistema.
8. **Extensibilidade:** novas skills, ferramentas e integrações devem poder ser adicionadas sem reescrever o núcleo.

## 4. Arquitetura geral

```text
Microfone
   |
   v
Wake Word: “Hey Nox”
   |
   v
VAD: deteção de atividade de voz
   |
   v
STT: fala -> texto
   |
   v
Orquestrador do Nox
   |
   +--> Memória de curto prazo
   +--> Memória de longo prazo
   +--> Router de modelos LLM
   +--> Ferramentas
   |       |-- Ficheiros
   |       |-- Shell seguro
   |       |-- Browser / Playwright
   |       |-- GitHub
   |       |-- Notas / calendário
   |       |-- Pesquisa web
   |       `-- Controlo do PC (fase avançada)
   |
   v
Resposta em texto
   |
   v
TTS
   |
   v
Altifalante
```

### Pipeline de voz

A camada de voz deve seguir um pipeline em tempo real:

```text
áudio -> VAD -> STT -> LLM -> TTS -> áudio
```

O sistema deve suportar:

- Deteção de início e fim de fala.
- Interrupção do Nox enquanto ele fala.
- Cancelamento de eco.
- Baixa latência.
- Fallback para modo texto se o microfone falhar.
- Modo silencioso: o Nox responde por texto, mas continua a executar tarefas.

**Referência técnica:** LiveKit Agents é uma framework open source para agentes multimodais em tempo real e implementa um pipeline de voz com STT, LLM e TTS. [LiveKit Agents](https://github.com/livekit/agents)

## 5. Stack tecnológica recomendada

| Camada | Recomendação principal | Alternativas |
|---|---|---|
| Linguagem principal | Python 3.11+ | TypeScript para interface web |
| Wake word | OpenWakeWord | Porcupine |
| VAD | Silero VAD ou WebRTC VAD | LiveKit VAD |
| STT local | faster-whisper | Whisper, Deepgram, OpenAI Whisper API |
| LLM | Router multi-provider | OpenAI-compatible, Anthropic, Google, Groq, OpenRouter |
| TTS | Kokoro, Piper ou ElevenLabs | OpenAI TTS, Azure TTS |
| Memória | SQLite + embeddings | Chroma, Qdrant, LanceDB |
| Browser automation | Playwright | Selenium |
| GitHub | GitHub CLI + GitHub API + MCP | PyGithub |
| Interface web | FastAPI + React/Next.js ou HTMX | Streamlit para protótipo |
| Execução de código | Subprocessos isolados | Docker, containers |
| Logs | SQLite + ficheiros JSONL | Loki, Grafana |
| Testes | pytest | unittest |
| CI/CD | GitHub Actions | GitLab CI |

## 6. Estrutura inicial do projeto

```text
HeyNox/
├── nox/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── microphone.py
│   │   ├── wake_word.py
│   │   ├── vad.py
│   │   └── recorder.py
│   ├── speech/
│   │   ├── __init__.py
│   │   ├── stt.py
│   │   └── tts.py
│   ├── brain/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── router.py
│   │   ├── memory.py
│   │   ├── prompts.py
│   │   └── planner.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base_tool.py
│   │   ├── files.py
│   │   ├── shell.py
│   │   ├── browser.py
│   │   ├── github.py
│   │   ├── notes.py
│   │   ├── calendar.py
│   │   ├── web_search.py
│   │   └── desktop.py
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── openai_compatible.py
│   │   ├── anthropic.py
│   │   ├── google.py
│   │   ├── groq.py
│   │   ├── openrouter.py
│   │   └── ollama.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── web.py
│   │   ├── status.py
│   │   └── approvals.py
│   └── safety/
│       ├── __init__.py
│       ├── permissions.py
│       ├── sandbox.py
│       ├── secrets.py
│       └── audit_log.py
├── tests/
│   ├── test_wake_word.py
│   ├── test_stt.py
│   ├── test_memory.py
│   ├── test_tools.py
│   └── test_github.py
├── docs/
│   ├── architecture.md
│   ├── security.md
│   ├── voice.md
│   └── roadmap.md
├── .github/
│   └── workflows/
│       └── tests.yml
├── config.yaml
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── LICENSE
└── README.md
```

## 7. Módulos obrigatórios

### 7.1 Áudio

O módulo de áudio deve:

- Listar dispositivos de entrada.
- Selecionar microfone predefinido.
- Capturar áudio em tempo real.
- Normalizar volume.
- Reduzir ruído se possível.
- Detetar voz com VAD.
- Ativar o Nox apenas com “Hey Nox”.
- Guardar gravações apenas se o utilizador ativar essa opção.
- Nunca enviar áudio para a cloud sem confirmação explícita.

### 7.2 Wake word

O wake word deve:

- Funcionar offline.
- Ter baixo consumo de CPU.
- Permitir personalizar a frase de ativação.
- Suportar “Hey Nox”, “Nox” e possivelmente “Hey Nox, …”.
- Evitar falsos positivos.
- Permitir sensibilidade configurável.
- Funcionar mesmo sem internet.

**Recomendação:** começar com OpenWakeWord. Usar Porcupine apenas se a qualidade/latência justificar a licença comercial.

### 7.3 STT

O módulo de transcrição deve:

- Suportar português de Portugal.
- Funcionar localmente com faster-whisper.
- Suportar modelos pequeno, base, small, medium e large.
- Permitir escolher entre CPU, CUDA e CPU com quantização.
- Devolver texto, idioma detetado, confiança e duração.
- Suportar transcrição contínua.
- Suportar fallback para API quando disponível.

### 7.4 LLM / cérebro

O Nox deve suportar vários fornecedores:

- OpenAI-compatible.
- Anthropic.
- Google Gemini.
- Groq.
- OpenRouter.
- Ollama local.
- LM Studio local.

O router deve escolher o modelo conforme:

- Complexidade da tarefa.
- Privacidade exigida.
- Custo.
- Latência.
- Disponibilidade da API.
- Preferência do utilizador.

### 7.5 Memória

A memória deve ter três níveis:

| Tipo | Finalidade | Persistência |
|---|---|---|
| Contexto de conversa | Histórico recente | Sessão |
| Memória de trabalho | Tarefa atual, ficheiros, plano | Sessão |
| Memória de longo prazo | Preferências, factos, projetos, decisões | Persistente |

A memória de longo prazo deve guardar:

- Nome e preferências do utilizador.
- Projetos e caminhos autorizados.
- Ferramentas preferidas.
- Decisões técnicas anteriores.
- Padrões de trabalho.
- Restrições de segurança.
- Histórico de tarefas concluídas.

### 7.6 Ferramentas

O Nox deve ter ferramentas modulares:

- **Ficheiros:** ler, criar, editar, mover, procurar e listar ficheiros.
- **Shell seguro:** executar comandos numa whitelist.
- **Browser:** navegar, pesquisar, preencher formulários e extrair dados com Playwright.
- **GitHub:** clonar, fazer pull, criar branch, commit, testes, PR e consultar issues.
- **Notas:** criar e consultar notas locais.
- **Calendário:** consultar e criar eventos, mediante permissão.
- **Pesquisa web:** pesquisa segura e citação de fontes.
- **Desktop:** abrir apps, controlar janelas, rato e teclado apenas em fase avançada.

### 7.7 Segurança

O sistema deve ter:

- Lista de pastas autorizadas.
- Lista de comandos permitidos e proibidos.
- Confirmação obrigatória para ações destrutivas.
- Auditoria completa.
- Sandbox quando possível.
- Limites de tempo e recursos.
- Bloqueio de acesso a `.env`, chaves, credenciais e ficheiros privados.
- Bloqueio de push direto para `main`.
- Modo de emergência para parar todas as tarefas.

## 8. Permissões

| Nível | Capacidade | Confirmação |
|---|---|---|
| 0 — Leitura | Ler ficheiros autorizados, consultar estado | Não |
| 1 — Escrita local | Criar/editar ficheiros autorizados | Não, se dentro da sandbox |
| 2 — Execução segura | Comandos whitelist | Não, se dentro da whitelist |
| 3 — Rede | Pesquisa web, APIs | Configurável |
| 4 — GitHub | Branch, commit, testes, PR | Configurável |
| 5 — Sistema | Instalar apps, alterar definições | Sempre |
| 6 — Destrutivo | Apagar, substituir, force push, enviar email, comprar | Sempre |
| 7 — Desktop físico | Rato, teclado, ecrã, apps | Sempre |

### Regras fixas

- Nunca apagar ficheiros fora da pasta autorizada.
- Nunca ler `.env`, `.git`, credenciais, chaves SSH ou ficheiros privados sem permissão explícita.
- Nunca enviar segredos para APIs.
- Nunca fazer push para `main`.
- Nunca fazer force push sem confirmação explícita.
- Nunca instalar pacotes globalmente sem confirmação.
- Nunca controlar rato/teclado sem confirmação explícita.
- Nunca executar ações em cadeia sem limite de passos.
- Nunca continuar após erro crítico sem perguntar ao utilizador.

## 9. Integração GitHub

### Repositório principal

- Perfil: https://github.com/7lokii
- Repositório: https://github.com/7lokii/HeyNox
- Nome: `HeyNox`
- Visibilidade: `public`
- Descrição: `HeyNox — assistente pessoal de IA com voz, wake word, memória, ferramentas seguras e integração GitHub.`

### Regras de criação

Antes de criar o repositório, o Nox deve:

1. Verificar se `7lokii/HeyNox` já existe.
2. Se existir, perguntar se o utilizador quer usar, renomear ou escolher outro nome.
3. Mostrar nome, visibilidade, descrição e licença.
4. Esperar confirmação explícita.
5. Criar o repositório apenas após confirmação.
6. Inicializar Git localmente.
7. Criar README, `.gitignore`, `.env.example`, `config.yaml` e estrutura inicial.
8. Fazer o primeiro commit.
9. Fazer push apenas após confirmação.
10. Configurar proteção de branch em `main`.

### Regras de trabalho no repositório

- Criar uma branch por funcionalidade.
- Nunca fazer push direto para `main`.
- Correr testes antes de abrir PR.
- Abrir pull request com descrição clara.
- Esperar revisão humana antes de merge.
- Nunca apagar branches sem confirmação.
- Nunca alterar secrets, workflows ou permissões sem confirmação.

### Convenção de branches

```text
main
├── feature/wake-word
├── feature/stt
├── feature/tts
├── feature/memory
├── feature/tools
├── feature/github-integration
├── feature/web-ui
├── feature/desktop-control
└── fix/audio-latency
```

### Convenção de commits

```text
feat: adiciona wake word Hey Nox
feat: adiciona transcrição local com faster-whisper
feat: adiciona memória persistente
fix: corrige deteção de fim de fala
docs: adiciona instruções de instalação
test: adiciona testes do módulo de áudio
chore: atualiza dependências
refactor: separa router de modelos
security: adiciona auditoria de comandos
```

## 10. Interface

### Interface de voz

- Indicador de estado: parado, à escuta, a processar, a falar, a executar.
- Histórico da conversa.
- Transcrição em tempo real.
- Botão para interromper.
- Botão para parar todas as ações.
- Indicador de microfone ativo.
- Indicador de modelo ativo.
- Indicador de permissões ativas.

### Interface web local

A interface web deve permitir:

- Conversar por texto.
- Ver histórico.
- Gerir memória.
- Ver ferramentas disponíveis.
- Aprovar ou recusar ações.
- Ver logs de auditoria.
- Configurar wake word, microfone, voz e modelos.
- Ver estado do repositório GitHub.
- Ver PRs abertos.
- Ver tarefas agendadas.

## 11. Comandos de voz iniciais

### Sistema

- “Hey Nox, que horas são?”
- “Hey Nox, abre o meu projeto.”
- “Hey Nox, que podes fazer?”
- “Hey Nox, modo silencioso.”
- “Hey Nox, para.”
- “Hey Nox, cancela.”
- “Hey Nox, repetiste?”
- “Hey Nox, desliga-te.”

### Ficheiros

- “Hey Nox, procura o ficheiro X.”
- “Hey Nox, resume este documento.”
- “Hey Nox, cria uma nota sobre…”
- “Hey Nox, organiza os ficheiros desta pasta.”
- “Hey Nox, mostra os ficheiros alterados recentemente.”

### GitHub

- “Hey Nox, resume o repositório.”
- “Hey Nox, cria uma branch para corrigir o login.”
- “Hey Nox, corre os testes.”
- “Hey Nox, abre um pull request.”
- “Hey Nox, mostra os issues abertos.”
- “Hey Nox, implementa a issue número X.”
- “Hey Nox, revê as alterações pendentes.”

### Automação

- “Hey Nox, pesquisa X e resume.”
- “Hey Nox, abre o browser.”
- “Hey Nox, abre esta página.”
- “Hey Nox, preenche este formulário.”
- “Hey Nox, tira um screenshot.”
- “Hey Nox, abre esta aplicação.”

## 12. Roadmap

### Fase 0 — Fundações

- Criar repositório `7lokii/HeyNox`.
- Criar estrutura de pastas.
- Configurar ambiente Python.
- Criar `README.md`.
- Criar `.gitignore`.
- Criar `.env.example`.
- Criar `config.yaml`.
- Criar testes iniciais.
- Configurar GitHub Actions.

**Entrega:** projeto inicial funcional e versionado.

### Fase 1 — Voz básica

- Captura de microfone.
- Wake word “Hey Nox”.
- VAD.
- STT local.
- LLM.
- TTS.
- Resposta falada.
- Interrupção da fala.
- Modo texto.

**Entrega:** “Hey Nox, que horas são?” funciona por voz.

### Fase 2 — Memória

- Memória de conversa.
- Memória de longo prazo.
- Memória semântica.
- Preferências do utilizador.
- Comandos para apagar memória.
- Exportar/importar memória.

**Entrega:** o Nox lembra-se de preferências e contexto entre sessões.

### Fase 3 — Ferramentas seguras

- Ficheiros.
- Shell seguro.
- Notas.
- Pesquisa web.
- Browser com Playwright.
- Sistema de aprovações.
- Audit log.

**Entrega:** o Nox consegue executar tarefas locais e web com supervisão.

### Fase 4 — GitHub

- Autenticação GitHub.
- Clonar e atualizar repositórios.
- Criar branches.
- Criar commits.
- Correr testes.
- Abrir pull requests.
- Ler issues.
- Criar issues.
- Responder a comentários em PRs.

**Entrega:** o Nox consegue trabalhar no repositório e propor PRs.

### Fase 5 — Automação avançada

- Tarefas agendadas.
- Rotinas diárias.
- Sub-agentes.
- Skills personalizadas.
- Integração MCP.
- Plugins.
- Automação de browser mais avançada.

**Entrega:** o Nox executa rotinas recorrentes.

### Fase 6 — Controlo do PC

- Deteção de janelas.
- Controlo de apps.
- Controlo de teclado e rato.
- Visão do ecrã.
- OCR.
- Confirmação por ação.
- Sandbox.
- Modo de emergência.

**Entrega:** o Nox consegue operar o PC, mas apenas com permissões explícitas.

## 13. Testes

### Testes obrigatórios

- Wake word reconhece “Hey Nox”.
- Wake word não ativa com ruído ou conversa normal.
- VAD deteta início e fim de fala.
- STT transcreve português corretamente.
- LLM responde em português de Portugal.
- TTS produz áudio audível.
- Interrupção funciona.
- Memória persiste entre reinícios.
- Ficheiros só são acedidos dentro da pasta autorizada.
- Comandos perigosos são bloqueados.
- GitHub nunca faz push direto para `main`.
- Audit log regista todas as ações.
- Interface web mostra estado e aprovações.

### Testes de segurança

- Tentar ler `.env` deve falhar sem permissão.
- Tentar apagar fora da sandbox deve falhar.
- Tentar executar `rm -rf /` deve ser bloqueado.
- Tentar fazer push para `main` deve ser bloqueado.
- Tentar enviar segredo para API deve ser bloqueado.
- Tentar instalar pacote global deve pedir confirmação.
- Tentar controlar rato/teclado deve pedir confirmação.

## 14. Configuração inicial

### `config.yaml`

```yaml
nox:
  name: "Nox"
  language: "pt-PT"
  persona: "calm, direct, helpful, futuristic"
  wake_word: "hey nox"
  wake_word_sensitivity: 0.7
  voice_enabled: true
  text_enabled: true

audio:
  input_device: "default"
  sample_rate: 16000
  channels: 1
  vad:
    provider: "silero"
    sensitivity: 0.5

stt:
  provider: "faster-whisper"
  model: "small"
  device: "auto"
  language: "pt"
  fallback_provider: "openai"

llm:
  default_provider: "openai_compatible"
  router:
    simple_tasks: "groq"
    coding_tasks: "anthropic"
    private_tasks: "ollama"
    fallback: "openai_compatible"

tts:
  provider: "kokoro"
  voice: "pt-PT-male"
  speed: 1.0

memory:
  sqlite_path: "data/nox.db"
  vector_store: "chroma"
  embedding_provider: "local"

github:
  default_repo: "7lokii/HeyNox"
  default_branch: "main"
  allow_push_to_main: false
  require_pr: true
  require_tests: true

security:
  allowed_paths:
    - "./projects"
    - "./data"
  blocked_paths:
    - ".env"
    - ".git"
    - "credentials"
  allowed_commands:
    - "git status"
    - "git diff"
    - "pytest"
    - "python -m pytest"
  require_confirmation:
    - "delete"
    - "force_push"
    - "install"
    - "system_change"
    - "send_email"
    - "purchase"
```

### `.env.example`

```env
# Nunca commitar o ficheiro .env real

OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
ELEVENLABS_API_KEY=
DEEPGRAM_API_KEY=

GITHUB_TOKEN=
GITHUB_USERNAME=7lokii

OLLAMA_BASE_URL=http://localhost:11434
NOX_DATA_DIR=./data
NOX_ALLOWED_PROJECTS=./projects
```

## 15. README inicial sugerido

```markdown
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

Projeto em desenvolvimento.

## Instalação

```bash
git clone https://github.com/7lokii/HeyNox.git
cd HeyNox
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m nox.main
```

## Segurança

O Nox não faz push direto para `main`, não acede a segredos sem
permissão e pede confirmação antes de ações destrutivas.

## Licença

MIT, se confirmado pelo autor.
```

## 16. Critérios de sucesso

O HeyNox estará funcional na versão 0.1 quando:

- O utilizador diz “Hey Nox”.
- O Nox ativa-se.
- O utilizador fala em português.
- O Nox transcreve corretamente.
- O Nox responde por voz.
- O utilizador consegue interromper o Nox.
- O Nox guarda pelo menos uma preferência.
- O Nox executa pelo menos uma ferramenta segura.
- O Nox cria uma branch e um PR no repositório.
- O Nox nunca faz push direto para `main`.
- Todas as ações ficam registadas no audit log.

## 17. Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Falsos positivos do wake word | Ativações indesejadas | Sensibilidade configurável, VAD e confirmação |
| Comandos perigosos | Perda de dados | Whitelist, sandbox e confirmação |
| Vazamento de segredos | Compromisso de contas | `.env`, secret manager e bloqueio de leitura |
| Push acidental para main | Quebra do repositório | Branch protection e PR obrigatório |
| Alucinações do LLM | Ações erradas | Planeamento, testes e revisão humana |
| Latência de voz | Experiência fraca | Pipeline local, streaming e modelos rápidos |
| Dependência de API | Falha offline | Ollama, faster-whisper e TTS local |
| Controlo do rato/teclado | Ações indesejadas | Última fase, sandbox e confirmação |
| Custo de API | Gastos inesperados | Router, limites diários e cache |

## 18. Ordem de implementação recomendada

1. Criar repositório `7lokii/HeyNox`.
2. Criar estrutura e ambiente Python.
3. Implementar captura de microfone.
4. Implementar wake word “Hey Nox”.
5. Implementar VAD.
6. Implementar STT local.
7. Implementar router LLM.
8. Implementar TTS.
9. Implementar loop de conversação.
10. Implementar memória.
11. Implementar ferramentas de ficheiros.
12. Implementar shell seguro.
13. Implementar GitHub.
14. Implementar interface web.
15. Implementar browser automation.
16. Implementar tarefas agendadas.
17. Implementar controlo do PC.
18. Adicionar telemetria local opcional.
19. Publicar release inicial.

## 19. Definição de “versão 0.1”

A versão 0.1 do HeyNox deve incluir:

- Wake word “Hey Nox”.
- Captura de microfone.
- VAD.
- STT local.
- LLM configurável.
- TTS.
- Memória básica.
- Ferramenta de ficheiros.
- Ferramenta de shell seguro.
- Integração GitHub básica.
- Criação de branch, commit, testes e PR.
- Interface web simples.
- Audit log.
- Testes automatizados.
- README e documentação.

## 20. Definição de “versão 1.0”

A versão 1.0 deve incluir:

- Voz fluida e interrompível.
- Memória persistente avançada.
- Multi-modelo com router.
- Skills personalizáveis.
- Sub-agentes.
- Browser automation robusta.
- Integração GitHub completa.
- Tarefas agendadas.
- Interface web completa.
- Controlo do PC com permissões granulares.
- Sandbox real.
- Telemetria local opcional.
- Instalador ou script de instalação.
- Documentação completa.
- Testes de segurança.

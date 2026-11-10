# Segurança

Os níveis de permissão e as regras fixas estão no `spec.md` (§8). Este documento
diz o que está implementado e como se comporta na prática.

## Em vigor

| Controlo | Onde |
|---|---|
| `.env` e variantes fora do controlo de versões | `.gitignore` |
| Segredos só via ambiente/`.env`, nunca no YAML | `nox/config.py` |
| Caminhos confinados a `security.allowed_paths` | `safety/sandbox.py` |
| `.env`, `.git` e `credentials` sempre bloqueados | `safety/sandbox.py` |
| Comandos só por prefixo permitido, sem `shell=True` | `safety/sandbox.py`, `tools/shell.py` |
| Comandos destrutivos bloqueados **mesmo com aprovação** | `safety/sandbox.py` |
| Aprovação humana para escrita e comandos fora da lista | `safety/approvals.py` |
| Registo JSONL de todas as chamadas | `safety/audit.py` |
| Push para `main` desligado por omissão | `GithubConfig` |
| Neste projeto: push direto para `main` autorizado, force-push sempre bloqueado | `config.yaml` |
| Testes correm antes do push (`github.require_tests`) | `integrations/github.py` |
| GitHub via `gh` autenticado, sem tokens em ficheiros ou argumentos | `integrations/github.py` |
| Rotinas sem permissões extra; ações continuam sujeitas a aprovação | `automation/routines.py` |
| Sub-agente sem `spawn_agent` (sem cadeias) | `tools/subagent.py` |
| Click/fill no browser pedem aprovação | `tools/browser.py` |
| MCP desligado por omissão e só com servidores escolhidos | `mcp/client.py` |
| Controlo do PC desligado por omissão; cada ação pede aprovação | `tools/desktop.py` |
| Modo de emergência corta todas as ações de desktop | `desktop/guard.py` |
| Apps só de `desktop.allowed_apps`, sem shell | `tools/desktop.py` |
| OCR e capturas ficam no disco local | `desktop/screen.py` |

## Como uma ação é aprovada

1. O modelo pede `write_file`, `edit_file` ou um comando fora da lista.
2. A ferramenta calcula o diff (ou o comando completo) e **bloqueia**.
3. O pedido aparece na interface, no painel âmbar, com o diff.
4. O utilizador carrega em **Aprovar** ou **Recusar**.
5. Sem decisão em `tools.approval_timeout_s` (45 s), a ação é recusada.

O silêncio nunca vale como aprovação. Sem interface aberta, a ferramenta recusa
e diz porquê — não há forma de aprovar por omissão.

O que uma aprovação **não** faz:

- não desbloqueia `.env`, `.git` ou caminhos fora da sandbox;
- não permite `;`, `|`, `&`, `>` ou crases (não há shell pelo meio);
- não permite `rm -rf`, `format`, `shutdown`, `reg delete`, etc.

## Escrever ficheiros

`write_file` substitui o ficheiro inteiro; `edit_file` troca um trecho exato e
exige que ele apareça uma só vez. Ambos mostram o diff antes de tocar no disco.
`tools.confirm_writes: false` desliga o pedido de aprovação — só para quem
confia no modelo e na sandbox.

## Comandos

`security.allowed_commands` corre sem perguntar (por omissão: leitura de git,
`git add`/`commit`, pytest e ruff). Tudo o resto pede aprovação. Os prefixos são
comparados com o comando normalizado, e o comando é dividido com `shlex` e
executado como processo direto.

## Rede

`web_search`, `fetch_url` e `browser` só aceitam `http`/`https` e recusam
destinos de rede local (`localhost`, `127.0.0.1`, `10/8`, `172.16/12`,
`192.168/16`, link-local, `*.local`). Cada redirecionamento é validado antes de
ser seguido — um endereço público não pode saltar para a rede interna. Só são
aceites tipos de texto, até 1,5 MB.

O conteúdo de uma página é tratado como dados, nunca como instruções. Como as
ferramentas de escrita exigem aprovação, uma página maliciosa não ganha mãos.

## GitHub

As operações passam pelo `gh` já autenticado na máquina — não há token no
`config.yaml`, no `.env` nem nos argumentos do processo. Se o `gh` não estiver
autenticado, a ferramenta recusa e diz para correr `gh auth login`.

- O repositório tem de estar dentro da sandbox.
- **Force-push não existe**: a ferramenta não expõe `--force`.
- Push para a branch principal só com `github.allow_push_to_main: true`
  (neste projeto está ligado, por decisão do utilizador).
- Com `github.require_tests: true`, o `push` corre `pytest` e recusa enviar se
  falhar.
- O Nox abre PRs e comenta, mas não faz merge sem pedido explícito.

## Automação e MCP

- As rotinas disparam sozinhas, mas não ganham permissões: tudo o que fazem
  passa pelas mesmas ferramentas, sandbox e aprovações.
- Um sub-agente vê as ferramentas todas menos `spawn_agent`; não há cadeias.
- **Servidores MCP correm fora da sandbox**, com os privilégios do utilizador.
  `mcp.enabled` é falso por omissão e só deves ligar servidores em que confias.
  As ferramentas aparecem como `mcp_<servidor>_<ferramenta>` e ficam na
  auditoria como as restantes.
- `click` e `fill` no browser pedem aprovação antes de tocar na página.

## Controlo do PC

O `desktop` está desligado no código (`DesktopConfig.enabled = False`). Neste
projeto está ligado por decisão do utilizador, com `confirm_actions: true`.

- Ler o ecrã (janelas, captura, OCR) não pede aprovação; mexer no rato, no
  teclado ou abrir apps pede, sempre, com coordenadas/texto no pedido.
- O modo de emergência (botão **Parar**, "para tudo", `action: "stop"`) recusa
  todas as ações de desktop até ser retomado. Não afeta as outras ferramentas.
- Abrir apps só a partir de `desktop.allowed_apps`, com `shell=False`.
- Teclas validadas, texto limitado a 2000 caracteres, coordenadas não negativas.
- `pyautogui.FAILSAFE` ativo: rato no canto superior esquerdo aborta.
- Capturas e OCR ficam no disco; nada é enviado para fora.

## Auditoria

Cada chamada — aprovada ou não — fica em
`%LOCALAPPDATA%\HeyNox\logs\audit.jsonl`, com ferramenta, argumentos, duração e
resultado (primeiros 200 caracteres). O ficheiro é append-only.

## Testes

`tests/test_tools.py`, `tests/test_approvals.py`, `tests/test_web.py`,
`tests/test_notes.py`, `tests/test_browser.py`, `tests/test_github.py`,
`tests/test_routines.py`, `tests/test_skills.py`, `tests/test_subagent.py`,
`tests/test_mcp.py` e `tests/test_desktop.py` cobrem:

- ler e escrever fora da sandbox falha;
- `.env` é recusado para leitura e escrita;
- escrita recusada não altera o ficheiro;
- `edit_file` recusa texto ambíguo ou inexistente;
- comando não aprovado não corre;
- `rm -rf /` é bloqueado mesmo com aprovação;
- sem interface, a ação é recusada com explicação;
- o pedido de aprovação expira em silêncio como "não";
- `localhost`, `192.168.x` e `file://` são recusados na pesquisa e no browser;
- push para `main` é recusado quando a flag está desligada;
- os testes falham o push quando não passam;
- branches com nomes inválidos (`--force`, `a..b`) são recusadas;
- um PR com a mesma branch de origem e destino é recusado;
- uma rotina criada depois da hora não dispara nesse dia;
- o sub-agente não recebe `spawn_agent`;
- um servidor MCP que não arranca é ignorado sem derrubar o Nox;
- com o controlo do PC desligado, nenhuma ação corre;
- clique, escrita e foco sem aprovação não acontecem;
- apps fora da allowlist não abrem;
- o modo de emergência recusa tudo até ser retomado.

A interface também está coberta (`tests/test_ui.py`): aprovações pelo HTTP,
botão de emergência, API de memória e o erro da voz a chegar ao HUD.

## Pendente

- Níveis de permissão por ferramenta (ler / escrever / sistema) declarados no
  `config.yaml`, em vez da tabela fixa da docstring de cada ferramenta.
- Limite de pedidos por minuto para o modelo não entrar em ciclo.
- Bloqueio de rede por lista de destinos: hoje qualquer URL pública pode ser
  pedida (`web_search`, `fetch_url`, `browser`); só localhost e IPs privados
  são recusados.
- Assinatura de código do instalador (Authenticode) — ver `docs/packaging.md`.

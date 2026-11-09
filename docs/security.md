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
| Push para `main` desligado por defeito | `GithubConfig` |

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

## Auditoria

Cada chamada — aprovada ou não — fica em
`%LOCALAPPDATA%\HeyNox\logs\audit.jsonl`, com ferramenta, argumentos, duração e
resultado (primeiros 200 caracteres). O ficheiro é append-only.

## Testes

`tests/test_tools.py` e `tests/test_approvals.py` cobrem:

- ler e escrever fora da sandbox falha;
- `.env` é recusado para leitura e escrita;
- escrita recusada não altera o ficheiro;
- `edit_file` recusa texto ambíguo ou inexistente;
- comando não aprovado não corre;
- `rm -rf /` é bloqueado mesmo com aprovação;
- sem interface, a ação é recusada com explicação;
- o pedido de aprovação expira em silêncio como "não".

## Pendente

- `safety/permissions.py` — níveis por ferramenta (ler / escrever / sistema).
- Limite de pedidos por minuto para o modelo não entrar em ciclo.
- Aprovação para apagar ficheiros (ainda não existe ferramenta de apagar).

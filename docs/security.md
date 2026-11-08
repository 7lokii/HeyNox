# Segurança

Os níveis de permissão e as regras fixas estão no `spec.md` (§8). Este documento
diz o que já está implementado e o que falta.

## Implementado (Fase 0)

| Controlo | Onde |
|---|---|
| `.env` e variantes fora do controlo de versões | `.gitignore` |
| Segredos só via ambiente/`.env`, nunca no YAML | `nox/config.py` |
| Push para `main` desligado por defeito (`allow_push_to_main: false`) | `GithubConfig` |
| Lista de caminhos bloqueados e confirmações obrigatórias na config | `SecurityConfig` |
| Config inválida falha no arranque em vez de correr insegura | `load_config` |

## Pendente

- `safety/permissions.py` — verificação de nível por ferramenta.
- `safety/sandbox.py` — confinamento de caminhos e subprocessos.
- `safety/audit_log.py` — registo JSONL + SQLite de todas as ações.
- Testes de segurança do §13 (leitura de `.env`, `rm -rf /`, push para `main`, etc.).

# Arquitetura

O HeyNox é um motor Python com um HUD React. Desde 2026-11-23 é um serviço do
homelab; o painel NoxSec e a APK são as únicas interfaces.

```text
                        HTTPS admin.noxsec.site
                                  |
                                  v
                 +-------------------------------+
                 | NoxSec API :8730 (loopback)   |
                 |  sessão admin / ticket 60 s   |
                 +---------------+---------------+
                                 | /heynox/
                                 | HTTP, 127.0.0.1
                                 v
                 +-------------------------------+
                 | heynox.service :8765          |
                 |  NoxApp, HUD, API, rotinas    |
                 +---------------+---------------+
                                 |
                                 v
                        /var/lib/heynox
                    config, .env, nox.db, logs
```

O Cloudflare Tunnel é a única entrada exterior do NoxSec. O HeyNox não tem
entrada própria: `heynox.service` ouve em `127.0.0.1:8765`, e `noxsec.service`
faz o proxy autenticado em `/heynox/`.

## Componentes

| Caminho | Função |
|---|---|
| `nox/main.py` | CLI; `--check`, `--serve`, `--ui`, voz, memória e diagnóstico |
| `nox/config.py` | `config.yaml` tipado com pydantic; validação e caminhos |
| `nox/brain/` | agente, cliente LLM, prompts e ferramentas |
| `nox/memory/` | SQLite + FTS5; histórico e factos |
| `nox/tools/` | ficheiros, shell, web, GitHub, browser e desktop |
| `nox/safety/` | sandbox, aprovações e audit JSONL |
| `nox/integrations/whatsapp.py` | dispositivo ligado por QR, histórico e grupos |
| `nox/ui/server.py` | servidor HTTP stdlib, endpoints e ciclo de vida |
| `nox/ui/static.py` | resolução do HUD compilado |
| `nox/ui/settings.py` | configuração e segredos pela interface |
| `ui/` | HUD React/Vite; build em `ui/dist` |
| `deploy/` | unit systemd, config do serviço e instalador |

## Arranque do serviço

O systemd corre:

```text
/opt/heynox/.venv/bin/nox --serve --config /var/lib/heynox/config.yaml
```

Com:

- `HEYNOX_DATA_DIR=/var/lib/heynox`;
- `NOX_DATA_DIR=/var/lib/heynox` para rotinas e utilitários que usam o caminho
  histórico;
- `ProtectSystem=strict`, `ProtectHome`, `NoNewPrivileges`;
- `ReadWritePaths=/var/lib/heynox`;
- `Restart=always`.

O `--serve` falha se o porto 8765 estiver ocupado (`strict_port=True`) em vez de
escolher 8766 em silêncio; o proxy não pode falar com um processo antigo. Não
abre browser.

O arranque cria `nox.db` e `logs/` se faltarem. Se não houver chave do modelo,
continua a responder a perguntas locais (horas, data, agradecimentos) e o HUD
mostra a configuração inicial.

## Autenticação e proxy

- **Browser:** o iframe usa a sessão admin do NoxSec; não há segundo login.
- **APK:** `GET /api/heynox/ticket` exige a sessão admin do cliente HTTP.
  O ticket é de uso único e vale 60 s.
- `GET /heynox/?ticket=...` responde 303 e define
  `noxsec_heynox_session` com `Path=/heynox`, `HttpOnly`, `Secure`,
  `SameSite=Lax`, 12 h.
- O proxy encaminha métodos GET/POST/PUT/PATCH/DELETE, query e corpo, e só
  permite `index.html`, `favicon.svg`, `assets/` e `api/`.
- `Set-Cookie` do upstream não atravessa; o HeyNox não tem autenticação própria.

O `NoxSec` mantém `X-Frame-Options: DENY` em todo o lado exceto `/heynox`, onde
usa `SAMEORIGIN` e `frame-ancestors 'self'`.

## Interface

O HUD usa `base: "./"` no Vite e `document.baseURI` no cliente. O mesmo build
serve `/` e `/heynox/`. O painel só define o `src` do iframe quando a aba é
aberta e limpa-o no logout.

## Dados e configuração

- Config inicial: `deploy/config.yaml`.
- Config em execução: `/var/lib/heynox/config.yaml`.
- Segredos: `/var/lib/heynox/.env`, modo 600, nunca no repositório.
- Memória: `/var/lib/heynox/nox.db`.
- Auditoria: `/var/lib/heynox/logs/audit.jsonl`.
- Caminhos permitidos pela sandbox: apenas `/var/lib/heynox`.
- Voz e controlo do PC desligados no serviço. O WhatsApp é instalado pelo
  extra `[whatsapp]` e usa o mesmo diretório de dados.

## Removido em 2026-11-23

- `installer/`, `releases/`, workflow de release e scripts dos `.exe`.
- PyInstaller, Inno Setup, o pacote portátil e o auto-update (`nox/ui/update.py`).
- Janela nativa (`nox/ui/window.py`), bandeja (`nox/ui/tray.py`) e os extras
  `tray`/`shell`.
- Dispatching por `--desktop`; o argumento devolve erro e código 2.

O núcleo, a voz (opcional), as ferramentas, a memória, o WhatsApp e as rotinas
continuam no motor. O desktop é uma ferramenta do motor, não uma distribuição:
no serviço está desligado.

## Testes

A suíte do motor tem **408 testes que passam e 3 saltos** que precisam de rede ou
modelos (`NOX_SLOW_TESTS`). A API NoxSec tem **105**. O build do HUD e o build
release da APK são validados na publicação; a app tem 27 testes Flutter.

## Publicação

`scripts/publicar-release.ps1`:

1. compila o painel;
2. copia-o para `dist.novo`, sem o servir;
3. sobe a versão da APK;
4. compila e publica a APK assinada;
5. exige que `/api/apk/info` devolva a mesma versão e tamanho;
6. só então troca `dist.novo` por `dist`.

A release actual é `v0.9.0+36`; painel e APK são publicados como uma unidade.

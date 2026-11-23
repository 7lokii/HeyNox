# HeyNox

**HeyNox** é o assistente pessoal **Nox**: conversa, ferramentas, memória,
WhatsApp e rotinas. O motor é Python; o HUD é TypeScript/React.

Desde 2026-11-23 corre como **serviço systemd no homelab**, em loopback. A única
forma de o usar é pelo **painel NoxSec** (`/heynox/`) ou pela **APK**. As versões
Windows, desktop e portátil, o instalador, a bandeja e a auto-atualização foram
removidos.

## Onde corre

```text
browser / APK
     |
     | HTTPS admin.noxsec.site
     v
NoxSec API (127.0.0.1:8730) ---- /heynox/ ----> HeyNox (127.0.0.1:8765)
     |                                              |
     | sessão admin ou ticket de uso único          | /var/lib/heynox
     v                                              v
painel web / WebView da APK                    memória, config, chaves
```

- `heynox.service`, utilizador `heynox`.
- Código em `/opt/heynox`; o `ui/dist` é servido ao lado de `nox/`.
- Dados, configuração e `.env` em `/var/lib/heynox`; nada de segredos no repo.
- O HeyNox **não** abre portas para a rede. O NoxSec é a única entrada.
- `voice_enabled: false` e `desktop.enabled: false` na configuração do serviço.

## Usar

1. Abre <https://admin.noxsec.site> e inicia sessão.
2. Escolhe **HeyNox** na navegação lateral. O HUD carrega num iframe
   autenticado pela sessão admin.
3. No primeiro arranque aparece a configuração: escolhe o fornecedor, cola a
   chave do modelo e guarda. A chave fica em `/var/lib/heynox/.env`.
4. Na APK, a gaveta tem **Painel / HeyNox / Diagnóstico / Settings**. A app pede
   um ticket de uso único e o WebView recebe apenas o cookie `/heynox`.

O HUD também funciona em `nox --ui` numa máquina local, para diagnóstico. Não é
uma aplicação desktop: abre no browser e não tem janela, bandeja ou atualização
automática.

## Instalar no homelab

O instalador é idempotente e corre como root. A cópia de origem tem de ter
`nox/`, `ui/dist` já construído e `deploy/`.

```bash
cd /tmp/heynox-install
bash deploy/instalar.sh
```

O script cria o utilizador, instala o venv, copia o serviço, ativa
`heynox.service` e espera por `GET /api/health`.

```bash
systemctl status heynox.service
journalctl -u heynox.service -n 50 --no-pager
curl -fsS http://127.0.0.1:8765/api/health
```

### Atualizar o serviço

1. `cd HeyNox/ui && npm run build`
2. Enviar `nox/`, `ui/dist`, `pyproject.toml`, `README.md` e `deploy/`.
3. Na cópia extraída no servidor, correr `bash deploy/instalar.sh`.
4. Confirmar `heynox.service` ativo e o health.

O instalador preserva `/var/lib/heynox/config.yaml` e `.env` entre atualizações.

## CLI

O CLI continua disponível para diagnóstico e para os comandos locais:

```bash
nox --check
nox --serve                  # modo do systemd, loopback, sem browser
nox --ui                     # HUD local no browser, diagnóstico
nox --say "que horas são?"
nox --text                   # conversa por texto
nox --voice                  # requer as dependências de voz
nox --devices
nox --memory
nox --memory-reset
nox --routines
nox --transcribe audio.wav
```

`--desktop` já não abre uma janela; devolve um erro e o código 2.

## Painel NoxSec

O painel não tem token do HeyNox. Para o browser, usa a sessão admin existente.
Para o WebView da APK:

```text
GET /api/heynox/ticket         (sessão admin ou Bearer)
GET /heynox/?ticket=...        303 + Set-Cookie noxsec_heynox_session
```

O ticket vale 60 segundos e só pode ser usado uma vez. O cookie vale 12 horas,
é `HttpOnly`, `Secure`, `SameSite=Lax` e tem `Path=/heynox`; não cobre `/api` do
painel. O iframe só é permitido no mesmo domínio (`frame-ancestors 'self'` e
`X-Frame-Options: SAMEORIGIN`).

## Desenvolvimento

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e ".[dev,whatsapp]"
cd ui && npm install && npm run build
```

Testes:

```bash
.venv/Scripts/python.exe -m pytest -q          # Windows
.venv/bin/python -m pytest -q                  # Linux
```

O estado actual: **408 testes passam, 3 são saltados** sem rede/modelos
(`NOX_SLOW_TESTS`). O NoxSec API tem 105. A app Flutter compila e a release
`v0.9.0+36` está publicada no painel e no servidor.

## Configuração

`deploy/config.yaml` é o ponto de partida do serviço. Pontos importantes:

```yaml
nox:
  voice_enabled: false
memory:
  sqlite_path: /var/lib/heynox/nox.db
desktop:
  enabled: false
security:
  allowed_paths:
    - /var/lib/heynox
```

O resto (fornecedor, modelo, chave) pode ser mudado no ecrã de configuração do
HUD. As alterações são gravadas em `/var/lib/heynox/config.yaml` e `.env`.

## Segurança

- O motor não é exposto na rede; só o proxy autenticado do NoxSec lhe chega.
- A sessão admin do browser não é copiada para o WebView da APK.
- O cookie do HeyNox é limitado a `/heynox`; o ticket é de uso único e curto.
- O serviço corre com `ProtectSystem=strict`, `ProtectHome`, `NoNewPrivileges` e
  só pode escrever em `/var/lib/heynox`.
- A allowlist de caminhos do serviço é `/var/lib/heynox`; não vê o resto do PVE.
- `.env`, `.git` e credenciais continuam bloqueados pela sandbox.

## Estrutura

```text
nox/             motor, CLI, ferramentas, memória, voz e integrações
ui/              HUD React/Vite; o build vive em ui/dist
deploy/          unit systemd, config do serviço e instalador
tests/           pytest; fixtures de voz em tests/fixtures/samples
docs/            documentação por área
```

Documentação: [`architecture.md`](docs/architecture.md),
[`interface.md`](docs/interface.md), [`security.md`](docs/security.md),
[`whatsapp.md`](docs/whatsapp.md) e [`roadmap.md`](docs/roadmap.md).

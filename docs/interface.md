# Interface

O HeyNox já não tem janela nativa, bandeja nem instalador. O HUD é uma aplicação
web servida pelo próprio motor em `127.0.0.1:8765` e exposta apenas pelo NoxSec.

## Três caminhos, uma interface

| Cliente | Entrada | Autenticação |
|---|---|---|
| Browser do painel | `https://admin.noxsec.site` → `GET /heynox/` | cookie de sessão admin do NoxSec |
| APK Android | WebView em `https://admin.noxsec.site/heynox/` | ticket de uso único → cookie `noxsec_heynox_session` |
| Diagnóstico local | `nox --ui` → `http://127.0.0.1:8765/` | nenhuma; só loopback |

O `--serve`, usado pelo systemd, não abre browser. O `--ui` é o único caminho que
abre uma página localmente e serve para desenvolvimento.

## Como o painel o mostra

`NoxSec-Dashboard` tem a aba **HeyNox**. O iframe nasce com
`data-src="/heynox/"` e só recebe `src` na primeira vez que a aba é aberta; ao
sair da sessão, o `src` é removido. Isto evita manter o HUD a fazer polling
enquanto a aba está fechada.

O caminho `/heynox` é o único onde o CSP do NoxSec permite ser embutido:

```text
frame-ancestors 'self'
X-Frame-Options: SAMEORIGIN
```

Nas restantes rotas continua `frame-ancestors 'none'` e `DENY`.

## Como a APK o mostra

O cliente HTTP do Dart tem a sessão admin, mas o WebView não a herda. O fluxo é:

1. a app chama `GET /api/heynox/ticket` com a sessão admin;
2. recebe um ticket de 60 segundos e abre
   `https://admin.noxsec.site/heynox/?ticket=...`;
3. o servidor consome o ticket e responde 303 com
   `noxsec_heynox_session`, `Path=/heynox`, `HttpOnly`, `Secure`,
   `SameSite=Lax`, 12 horas;
4. o WebView segue para `/heynox/` e o HUD usa caminhos relativos.

O ticket não pode ser reutilizado. O cookie não cobre `/api` do painel, e a app
nunca entrega ao WebView o cookie `noxsec_admin_session`.

A página `lib/ecras/heynox.dart` só é criada na primeira abertura da aba. O
`WebViewController` bloqueia navegação para outro host.

## Caminhos relativos

O build do Vite usa `base: "./"` e o cliente da API resolve pedidos a partir de
`document.baseURI`. O mesmo `ui/dist` funciona em `/` (modo local) e em
`/heynox/` (atrás do proxy), sem um build separado para cada um.

## Endpoints do HUD

| Rota | Método | Para quê |
|---|---|---|
| `/api/health` | GET | liveness do serviço; usado pelo systemd/scripts |
| `/api/state` | GET | conversa, voz, níveis, aprovações, emergência |
| `/api/say` | POST | enviar uma mensagem |
| `/api/voice` | POST | ligar/desligar a voz (desligada no serviço) |
| `/api/levels` | GET | espectro de saída e entrada |
| `/api/devices` | GET | microfones visíveis |
| `/api/settings` | GET/POST | configuração e segredos mascarados |
| `/api/settings/test` | POST | testar a chave do modelo |
| `/api/memory` | GET | factos guardados |
| `/api/memory/forget` | POST | esquecer por padrão |
| `/api/approvals` | POST | aprovar/recusar uma ação |
| `/api/emergency` | POST | parar/retomar o controlo do PC |
| `/api/whatsapp` e subrotas | GET/POST | estado, grupo e modo do WhatsApp |

Os antigos `/api/update*` já não existem. Não há atualização automática dentro
da app: a release é publicada pelo desktop com `scripts/publicar-release.ps1`.

## Ficheiros e dados

- `ui/dist/index.html` e `ui/dist/assets/*`: HUD compilado.
- `/var/lib/heynox/config.yaml`: configuração do serviço.
- `/var/lib/heynox/.env`: chaves; modo 600.
- `/var/lib/heynox/nox.db`: memória SQLite.
- `/var/lib/heynox/logs/audit.jsonl`: auditoria.

O `nox/ui/index.html` antigo continua apenas como fallback de desenvolvimento, se
o build do Vite não existir. Em produção o `ui/dist` é obrigatório.

## CSP e isolamento

O proxy do NoxSec não copia `Set-Cookie` do upstream, não aceita caminhos com
`..` e só encaminha `index.html`, `favicon.svg`, `assets/` e `api/`. O browser
nunca fala diretamente com o porto 8765; esse porto está ligado apenas a
`127.0.0.1`.

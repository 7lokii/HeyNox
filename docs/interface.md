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

## Ecrã pequeno e APK

O HUD não tem uma segunda página para o telemóvel: o mesmo build adapta-se. Abaixo
de 620 px de largura, ou em ecrãs baixos, o palco passa a uma coluna com o reactor
curto, a conversa e os painéis opcionais. A página usa `100dvh` e mantém
`overflow: hidden`; só os painéis internos rolam, com as barras escondidas. O
WebView da APK usa este modo sem precisar de uma versão própria do binário.

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
| `/api/voice` | POST | ligar/desligar a voz do serviço (CLI; o HUD já não usa) |
| `/api/voice/turn` | POST | PCM 16 bits do microfone do HUD; devolve texto, resposta e MP3 |
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

O HUD não usa `/api/voice`: o homelab não tem placa de som, por isso a voz é
capturada no dispositivo que abriu a página. O HUD abre o microfone sozinho
quando carrega; se o browser mantiver o áudio bloqueado, o primeiro toque no
ecrã desbloqueia-o e o estado passa a «a ouvir». Depois deteta o fim da frase
por energia e envia PCM mono a 16 kHz
para `/api/voice/turn`. O servidor transcreve com o STT configurado, passa pelo
agente e devolve a resposta em texto e MP3 em base64, que o browser toca. O
turno só chega ao agente se o Vosk local ouvir uma das `wake.phrases`
(`Nox`, opcionalmente depois de «ei», «hey» ou «olá») no
início do PCM. Se não ouvir, o áudio não chega ao Whisper nem à cloud. Depois
disso, o Whisper transcreve o pedido e a palavra é retirada do início quando
aparece; o STT pode não a repetir. Uma menção a meio da frase não ativa o Nox. Sem ela, o microfone continua ativo, mas o HUD fica em «Diz Nox»
em vez de voltar a «a ouvir», e não grava um
turno. Dizer só “Nox” abre uma janela de `wake.timeout_s` (15 s desde 2026-11-26)
para o pedido seguinte. O HUD retoma o microfone **sem espera** depois de
reconhecer a ativação: os 1,1 s de temporizador que aqui estavam engoliam o
início do pedido, e a pausa de silêncio que fecha a gravação subiu de 850 ms
para 1 200 ms. Sem ela, pensar a meio da frase cortava-a; cada novo pedido exige a palavra outra vez. Com
`wake.provider: off`, o filtro desliga-se. O anel tem tres cores desde
2026-11-26: **branco** calado, **azul** enquanto grava o pedido e **vermelho**
enquanto o Nox fala. A cor segue o **passo** do ciclo de voz (`wait`/`record`
em `voice.ts`), nao os niveis do microfone: pintado pelos niveis, o ruido da sala
mantinha o anel azul em repouso e a fala piscava-o de branco. O vermelho segue o MP3 que toca no
dispositivo; o serviço não tem placa de som e não pode medir essa saída. O `Permissions-Policy` do NoxSec tem
de permitir `microphone=(self)`, e o iframe do painel leva
`allow="microphone"`.

**So depois da palavra.** O HUD grava sempre que ha som (e preciso ouvir para
reconhecer o «Nox»), mas o anel e o texto so passam a `a ouvir` quando o
servidor confirma a ativacao. O anel fica azul **no instante em que ha fala** (o VAD demora ~120 ms), sem
esperar pela confirmacao do servidor (Vosk + Whisper, ~1,5 s). Se o servidor
recusar, volta a branco e o estado diz `diz «Nox»`. Com a ativacao confirmada, o
estado passa a `ouve o pedido` e a janela de 15 s mantem o azul ate ao pedido
seguinte. Um `armedAte` local de 15 s acompanha o
`wake.timeout_s`. Antes disto, qualquer ruido da sala — o clique de um reload,
uma televisao — punha o HUD a "ouvir" sem ninguem ter chamado o Nox.

**Estado em repouso.** O primeiro texto e `diz «Nox»` desde o primeiro frame (o
estado inicial era `a ligar`, que se lia como "a ouvir" durante o primeiro
segundo). Com o microfone ligado e sem ninguem a falar, o HUD diz
`diz «Nox»`, nao `a ouvir`: dizer "a ouvir" assim que o audio arranca fazia
parecer que o Nox ja estava a atender. `a ouvir` aparece quando a gravacao do
pedido comeca, e `diz «Nox»` volta depois de responder ou de falhar.

Se o microfone falhar, o HUD mostra um aviso persistente acima do rodapé com
«Microfone bloqueado» ou «Voz indisponível» e «Tentar de novo». O aviso só
desaparece quando o microfone abre com sucesso; a permissão tem de ser reposta
nas definições do browser ou da app. Um `NotReadableError` no WebView da APK é
apresentado como falha de abertura do WebView, com a permissão Android e outras
apps como ações; no browser, o mesmo erro continua a ser descrito como
microfone ocupado.

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

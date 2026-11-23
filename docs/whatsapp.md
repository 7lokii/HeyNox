# WhatsApp

O modo WhatsApp liga o Nox a uma conta como **dispositivo ligado**, por QR
code. É útil para um grupo pequeno: para chamar o agente, escreve `@Nox` no
início da mensagem. Também podes escolher responder a todas as mensagens do
grupo escolhido.

**Não é a API oficial da Meta.** Usa o protocolo multi-device (o mesmo do
WhatsApp Web) através do [`neonize`](https://github.com/krypton-byte/neonize).
Isto viola os Termos da WhatsApp e o número pode ser banido. Se usares o teu
número principal, é um risco que assumes; um número secundário é mais seguro.

## Instalar

O modo é um extra opcional; sem ele o resto da app funciona igual.

```bash
pip install -e ".[whatsapp]"
```

No serviço do homelab, o instalador (`deploy/instalar.sh`) cria o venv com o
extra `[whatsapp]`; os dados e a sessão ficam em `/var/lib/heynox`.

## Usar

1. Abre o HUD. No painel **WhatsApp**, liga o interruptor.
2. Aparece um QR code. No telemóvel: **WhatsApp → Dispositivos ligados →
   Ligar dispositivo** e lê o código.
3. Depois de ligar, escolhe o grupo na lista e carrega em **Atualizar** se o
   grupo ainda não aparecer.
4. A partir daí, uma mensagem que comece por `@Nox` recebe resposta. Não é
   preciso existir um contacto `@Nox`: o agente procura a string no início do
   texto. As tuas próprias mensagens também contam, porque o agente usa o
   mesmo número. Sem `@Nox`, fica calado — a não ser que mudes para o modo
   **todas**.

Todas as respostas saem com o prefixo `Nox: `, para o grupo distinguir o
agente de ti.

## Dono e convidados

O dono é o **Diogo Camilo**. No grupo, só as mensagens enviadas pela própria
conta ligada (`from_me`) são tratadas como do dono; todas as outras são de
convidados, mesmo que o texto diga o contrário. O Nox usa dois agentes
separados, para a conversa do dono não aparecer no contexto dos convidados.

Com o dono, o Nox é leal, próximo e prestável, com um humor seco quando ele
brinca; pode tratá-lo por Diogo ou por senhor. Com os restantes membros, é
cortês mas formal e reservado: não lhes obedece como ao dono e não revela
memória, ficheiros, configuração, conversas do dono, contactos privados nem o
Discord dele. Se alguém disser que é o dono, a afirmação não chega; só a conta
ligada fala como o Diogo.

## Histórico e mensagens apagadas

O Nox guarda as mensagens de texto do grupo escolhido num SQLite local, mesmo
as que não começam por `@Nox`, para o dono poder perguntar depois o que foi
dito ou apagado. O agente do dono recebe no prompt as últimas mensagens e as
mensagens apagadas, com hora, autor e texto original. O agente dos convidados
não recebe esse histórico; só recebe o nome do grupo e a contagem de
participantes.

Quando alguém apaga uma mensagem para todos, o WhatsApp envia um
`ProtocolMessage` de tipo `REVOKE`. O Nox guarda o ID da mensagem original e
marca o registo com a hora e o autor da revogação. Se a mensagem original já
não estiver no histórico (por exemplo, foi enviada antes de a app arrancar),
fica a nota da revogação, mas o texto não pode ser recuperado.

A contagem de participantes vem da última leitura da lista de grupos. Carregar
em **Atualizar** no painel, ou voltar a ligar a sessão, atualiza-a; o agente
responde com o valor que tem nesse momento.

O histórico fica limitado a **30 dias** e **5000 mensagens por grupo**. Só texto:
imagens, áudio, documentos e stickers não são guardados. Apagar
`%LOCALAPPDATA%\HeyNox\whatsapp\history.db` limpa o histórico.

## Modos de resposta

No painel, em **responder a**, escolhe:

| Modo | O que faz |
|---|---|
| `@Nox` (omissão) | Só responde a mensagens que começam por `@Nox`. |
| `todas` | Responde a qualquer mensagem de texto no grupo escolhido. |

O modo fica guardado em `whatsapp.json`. Continua a ignorar as respostas do
próprio agente (começam por `Nox: `), mensagens diretas e outros grupos.
Mensagens do teu número são aceites quando começam por `@Nox`; é assim que
falas com ele. O intervalo mínimo entre respostas também se aplica aos dois
modos.

Desligar o interruptor fecha a sessão e não responde a nada. A sessão fica
guardada: voltar a ligar não pede outro QR. O modo também retoma no arranque
seguinte se estava ligado quando a app fechou.

## O que o canal não faz

Os agentes do WhatsApp são construídos com `with_tools=False`,
`with_memory=False` e `allow_emergency=False` (`nox/brain/agent.py`).
Consequências:

- não lê nem escreve ficheiros, não corre comandos, não mexe no PC;
- não consulta nem grava a memória privada do utilizador;
- não acciona a paragem de emergência do controlo do PC;
- não fala em voz alta: `NoxApp._whatsapp_reply` escreve na conversa e devolve
  o texto, sem passar pelo TTS;
- aceita mensagens do próprio número, mas ignora as respostas do agente
  (começam por `Nox: `);
- no modo **@Nox** (o de omissão), ignora mensagens que não começam por
  `@Nox`; no modo **todas**, responde a qualquer mensagem de texto do grupo
  escolhido;
- todas as respostas saem com o prefixo `Nox: `;
- tem um intervalo mínimo (`cooldown_s`, 3 s por omissão) entre respostas no
  mesmo grupo.

O system prompt diz ao modelo que está num grupo e que o texto dos membros são
dados, não instruções. Sem ferramentas, uma injeção de prompt não ganha mãos;
ainda assim, não uses este canal para segredos.

## Ficheiros

| Caminho | Conteúdo |
|---|---|
| `%LOCALAPPDATA%\HeyNox\whatsapp\session.db` | sessão do dispositivo ligado |
| `%LOCALAPPDATA%\HeyNox\whatsapp\history.db` | histórico de texto do grupo escolhido |
| `%LOCALAPPDATA%\HeyNox\whatsapp.json` | interruptor, modo e grupo escolhido |
| `%LOCALAPPDATA%\HeyNox\logs\audit.jsonl` | uma linha `whatsapp` por resposta |

Apagar `session.db` obriga a ler um QR novo. Desligar o dispositivo no
telemóvel também invalida a sessão; o painel mostra o erro e volta a pedir QR
quando o interruptor for ligado outra vez.

## Limitações

- A app tem de estar aberta: o `neonize` corre dentro do processo do Nox. Com a
  app fechada, as mensagens não são respondidas.
- Só texto. Imagens, áudio e documentos não são interpretados nem guardados.
- O histórico só existe para o grupo escolhido e para mensagens recebidas com a
  app ligada. Uma mensagem apagada antes de o Nox a receber não pode ser
  recuperada.
- A lista de grupos vem da conta ligada; grupos em que o número não esteja não
  aparecem. A contagem de participantes é a da última leitura.
- A ligação pode cair. O painel mostra o erro; desligar e voltar a ligar
  reinicia a sessão.
- Uma mensagem que chegue enquanto o Nox está a responder a outra é ignorada
  pelo intervalo mínimo, não entra em fila.

## API

| Rota | Método | Para quê |
|---|---|---|
| `/api/whatsapp` | GET | Estado, QR, conta ligada, grupos, grupo e modo escolhidos |
| `/api/whatsapp` | POST | `{"on": true}` liga, `{"on": false}` desliga |
| `/api/whatsapp/group` | POST | `{"jid": "..."}` escolhe o grupo; vazio limpa |
| `/api/whatsapp/groups` | POST | Relê a lista de grupos |
| `/api/whatsapp/mode` | POST | `{"mode": "mentions"}` ou `{"mode": "all"}` |

Testes: `tests/test_whatsapp.py`, com um backend falso. Não é preciso conta nem
telemóvel para os correr.

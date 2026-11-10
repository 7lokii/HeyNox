# Interface

O HeyNox é uma **app de desktop** com HUD próprio. Não abre um separador do
browser: abre uma janela com ícone, barra de título e ciclo de vida próprio.
Fechar a janela fecha a app e o motor.

O motor continua a ser Python. A janela é a única coisa que mudou.

## Duas gerações de HUD

| Onde | O que é | Quando é usado |
|---|---|---|
| `ui/` (Vite + React + TypeScript) | O HUD atual, compilado para `ui/dist` | Sempre que existe um build |
| `nox/ui/index.html` | O HUD original de ficheiro único | Só como rede de segurança, sem build |

`nox/ui/static.py` procura por esta ordem: `NOX_UI_DIST`, `ui/dist` no
repositório, `ui/dist` embutido pelo PyInstaller, e por fim o `index.html`
legado. Sem build o `.exe` abre o que abria antes, em vez de rebentar.

## A janela

`nox/ui/window.py`, sobre o WebView2 que já vem com o Windows.

```bash
nox --desktop      # janela própria (é o que o HeyNox.exe faz)
nox --ui           # o mesmo HUD, no browser: diagnóstico e desenvolvimento
```

- Tamanho 1280x820, mínimo 980x640, fundo `#04070d` (sem flash branco a abrir).
- O servidor local (127.0.0.1:8765) arranca primeiro; a janela abre depois.
- `--ui` continua a existir e a abrir o browser. É a via de diagnóstico e o
  caminho quando o extra `shell` não está instalado.

Precisa do extra:

```bash
pip install -e ".[shell]"     # pywebview
```

Sem o extra, `--desktop` escreve um aviso e abre no browser. Não falha.

## Desenvolvimento

Duas metades, dois processos.

```bash
# terminal 1: o motor
nox --ui

# terminal 2: o HUD com recarregar automático
cd ui && npm install && npm run dev     # http://localhost:5173
```

O Vite faz proxy de `/api` para `127.0.0.1:8765`, por isso os componentes falam
com os mesmos caminhos do pacote. O porto do motor é configurável:

```bash
NOX_API=http://127.0.0.1:8766 npm run dev
```

Para ver o HUD com dados sem gastar LLM nem voz:

```bash
.venv/Scripts/python.exe ui/scripts/mock-api.py 8765
```

## Build

```bash
cd ui && npm run build        # ui/dist/index.html + assets
```

O PyInstaller embute `ui/dist` (`installer/pyinstaller.py` gera a entrada de
`datas`). O workflow `release.yml` compila o HUD antes de compilar o `.exe`;
sem esse passo o pacote sairia com o HUD legado.

`ui/dist` fica fora do git. É artefacto.

## Contrato com o backend

O HUD não conhece Python: fala HTTP com o motor local.

| Rota | Método | Para quê |
|---|---|---|
| `/` | GET | O HUD |
| `/api/state` | GET | Turnos, estado, voz, aprovações, emergência |
| `/api/levels` | GET | Espectro de saída e de entrada (48 bandas) |
| `/api/memory` | GET | Factos guardados |
| `/api/say` | POST | Uma pergunta por texto |
| `/api/voice` | POST | Ligar/desligar a voz |
| `/api/memory/forget` | POST | Esquecer o que contenha o texto |
| `/api/approvals` | POST | Aprovar ou recusar um pedido |
| `/api/emergency` | POST | Travar/retomar o controlo do PC |
| `/api/settings` | GET | Presets, valores, chaves mascaradas, caminhos, versão |
| `/api/settings` | POST | Gravar `.env` e `config.yaml` e passar a usá-los |
| `/api/settings/test` | POST | Pedido mínimo ao fornecedor para validar a chave |
| `/api/devices` | GET | Microfones visíveis |
| `/api/update` | GET | Último resultado da verificação de versão |
| `/api/update/check` | POST | Verificar agora, sem esperar o intervalo |
| `/api/update/apply` | POST | Descarregar, conferir o `sha256` e trocar a pasta |

O estado vem por polling (900 ms o estado, 2500 ms a memória, 90 ms o
espectro). O servidor é stdlib e não tem websockets.

Os estáticos são servidos só de dentro de `ui/dist` ou de `nox/ui/`: um `..` no
caminho devolve 404 e não lê o disco.

## Porque não Tauri

O pedido original era TypeScript + Tauri. Tauri precisa de duas coisas que este
PC não tem:

- toolchain Rust (`cargo`, `rustc`);
- MSVC + Windows SDK para ligar o binário. Há `Windows Kits\10` mas sem `Lib\um`,
  e não há Visual Studio com a carga C++.

Instalar as duas ocupa entre 6 e 8 GB e o `C:` tem 6,1 GB livres. Ficou de fora
por agora, com a janela a ser feita pelo `pywebview`, que usa o WebView2 já
instalado e não acrescenta um segundo motor de render.

O HUD em `ui/` é o mesmo nos dois caminhos: se o Rust e o SDK aparecerem, a
troca é a shell, não a interface.

## Configuração dentro da app

Primeiro arranque: `GET /api/state` traz `setup_required: true` enquanto não
houver chave para o fornecedor configurado. O HUD não aparece; aparece o ecrã de
configuração (`ui/src/screens/Setup.tsx`), com fornecedor, chave, modelo,
microfone e palavra de ativação. O botão de concluir só liga com uma chave, ou
com um fornecedor local que não precise dela (Ollama).

O que fica gravado, e onde (`nox/ui/settings.py`):

| Ficheiro | Conteúdo |
|---|---|
| `%LOCALAPPDATA%\HeyNox\.env` | chaves, uma linha por chave, nada mais |
| `%LOCALAPPDATA%\HeyNox\config.yaml` | cópia do `config.yaml` embutido com as alterações por cima |

A cópia é o que impede o ecrã de apagar o que não mostra: secções como `memory`,
`github`, `automation` e `stt` sobrevivem a cada gravação.

As chaves nunca voltam ao HUD. `GET /api/settings` devolve `{"set": true,
"preview": "...c123"}`: o sufixo serve para reconhecer a chave, o resto não sai
do processo. O teste de chave também nunca escreve a chave em log.

## Acesso total

`tools.full_access` liga-se nas definições e aplica-se sem reiniciar: o
`ApprovalBroker` devolve `True` de imediato e escreve uma linha
`aprovação:auto:<ação>` no `logs/audit.jsonl`. Ainda assim há dois limites: a
paragem de emergência continua a travar o controlo do PC, e nada disto contorna
o `Sandbox` de caminhos.

Também vale fora da interface: sem `full_access`, um comando fora da lista era
recusado em `nox --voice` por não haver quem aprovasse. Com o interruptor
ligado, o `build_agent` cria o broker sozinho.

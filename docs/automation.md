# Automação

Rotinas, sub-agentes, skills e MCP. O objetivo é o Nox fazer trabalho sem alguém
a carregar em botões, sem perder os travões.

## Rotinas

Um prompt guardado com uma agenda. Corre enquanto a interface (`nox --ui`)
estiver aberta; sem interface fica guardado mas não dispara.

```bash
nox --routines                       # lista
```

O Nox cria-as por voz ou por texto: "todos os dias às 9h resume as notícias".
Por baixo, a ferramenta `routine` com `action: "create"`.

| Agenda | Quando corre |
|---|---|
| `daily@09:00` | Todos os dias a essa hora. Criada depois da hora, estreia-se no dia seguinte; criada antes, corre nesse dia. |
| `every@2h` | A cada 2 horas, desde a criação ou da última execução. |
| `once@2026-11-10T09:00` | Uma vez, e fica desligada. |

Detalhes que evitam surpresas:

- Se o Nox estiver fechado à hora marcada, a rotina corre no arranque seguinte
  (recuperação), uma vez só por dia.
- `last_run` é gravado **antes** de executar: uma rotina que rebente não entra
  em ciclo.
- A resposta aparece na conversa como `(rotina) …` e é falada se a voz estiver
  ligada.
- As rotinas não têm permissões extra: escrever ficheiros e comandos fora da
  lista continuam a pedir aprovação.

Ficheiro: `%LOCALAPPDATA%\HeyNox\routines.json`.

## Sub-agentes

A ferramenta `spawn_agent` entrega uma tarefa a um agente novo, com o mesmo
modelo e as mesmas ferramentas — **menos** `spawn_agent`, para não haver cadeias
infinitas. Começa sem histórico e sem memória; devolve só o resultado final.

Serve para trabalho longo ou para não encher a conversa principal com passos
intermédios. Limite de 90 segundos por omissão (5 a 300 configuráveis no
pedido). O sub-agente não fala: a resposta volta como texto da ferramenta.

## Skills

Playbooks em Markdown que ensinam o Nox a fazer uma tarefa de uma forma
específica. O índice (nome + descrição) entra no system prompt; o corpo só é
carregado quando o modelo chama a ferramenta `skill`.

Locais, por ordem (o utilizador ganha):

1. `skills/` na pasta do projeto;
2. `%LOCALAPPDATA%\HeyNox\skills\`.

Formato:

```markdown
---
name: resumo-diario
description: Como resumir o dia em três pontos
---
1. Lê as notas de hoje.
2. Escolhe três coisas que mudaram o estado do projeto.
3. Escreve uma frase por cada, sem adjetivos.
```

Sem frontmatter, ou sem nome/corpo, o ficheiro é ignorado.

## MCP

Servidores MCP por stdio (JSON-RPC 2.0). Desligado por omissão: arrancar
processos externos é uma decisão explícita.

```yaml
mcp:
  enabled: true
  timeout_s: 20
  servers:
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "./projects"]
```

No arranque, cada servidor recebe `initialize` e `tools/list`; as ferramentas
aparecem no agente como `mcp_<servidor>_<ferramenta>`, com a descrição e o
schema originais. Um servidor que falhe é ignorado com um aviso, sem impedir o
Nox de arrancar.

Limites:

- **As ferramentas MCP não passam pela sandbox do Nox.** O servidor corre com
  os teus privilégios e faz o que quiser. Só liga servidores em que confias.
- Sem `enabled: true` nada é lançado.
- O processo é terminado quando o Nox fecha.

## Browser

Além de ler, o browser pode `click` e `fill`. Estas duas ações **pedem
aprovação** na interface, com a página e o seletor; sem aprovação não há clique.

```
browser(url="https://exemplo.pt", action="click", selector="#comprar")
browser(url="https://exemplo.pt", action="fill", selector="#email", text="...")
```

Continuam a ser ações num browser headless: não veem a tua sessão normal nem os
teus cookies.

# Memória

O Nox guarda duas coisas: **a conversa** e **factos** sobre o utilizador.

```text
%LOCALAPPDATA%\HeyNox\data\nox.db     (configurável em memory.sqlite_path)
```

O caminho é relativo ao diretório de dados do utilizador de propósito: a pasta
de instalação não é escrita e a memória sobrevive a atualizações.

## Esquema

| Tabela | Para quê |
|---|---|
| `turns` | cada mensagem trocada, com sessão e data |
| `facts` | o que o Nox decidiu guardar (nome, preferências, notas) |
| `facts_fts` | índice FTS5 sobre `facts`, mantido por triggers |

O FTS5 já vem no SQLite e resolve o caso real — "lembra-te do projeto X". A
pesquisa semântica (Chroma + embeddings) fica para quando houver razões de peso:
acrescenta dependências e um modelo, para ganhar pouco sobre pesquisa por palavra
numa base de dezenas de factos.

## O que o Nox aprende

Por regras, não por LLM. Uma chamada ao modelo por turno custaria latência e
dinheiro para apanhar "chamo-me X".

| Disseste | Guardado |
|---|---|
| "Chamo-me Rui e prefiro respostas curtas." | dois factos: nome e preferência |
| "Não gosto de ruído de fundo." | desgosto |
| "lembra-te que o projeto é local-first" | nota |
| "guarda isto: reunião às quintas" | nota |

A frase é cortada onde começa outra coisa que também interessa, senão
"chamo-me Rui e prefiro X" virava um facto comprido e mal formado.

## Como é usado

1. **No arranque**, os últimos `memory.history_turns` turnos voltam para a
   conversa — o Nox retoma o fio onde ficou.
2. **A cada resposta**, os factos mais recentes e os que casam com a pergunta
   entram no system prompt (máximo oito, para não encher o contexto).
3. **No fim de cada turno**, a frase do utilizador passa pelas regras e o que
   for durável fica guardado.

## Comandos

```bash
nox --memory                       # o que sabe
nox --forget Rui                   # esquece o que contiver "Rui"
nox --memory-reset                 # apaga factos e histórico
nox --memory-export memoria.json   # exporta tudo
nox --memory-import memoria.json   # importa (sem duplicar factos)
```

Por voz ou texto:

- "o que sabes sobre mim?" — lista os factos, sem passar pelo modelo
- "esquece X" — apaga o que contiver X
- "esquece tudo" — apaga os factos (o histórico de conversa fica)

## Detalhes que deram trabalho

- **Uma ligação SQLite por thread.** A interface serve pedidos em várias threads
  e o SQLite recusa ligações partilhadas. `check_same_thread=False` sozinho não
  chegava — cada thread precisa da sua ligação.
- **WAL ligado.** Permite ler enquanto se escreve, o que importa quando a
  interface consulta a memória enquanto o motor guarda um turno.
- **Factos duplicados são ignorados** (comparação sem distinção de maiúsculas),
  senão dizer o nome duas vezes enchia a lista.

## Limites conhecidos

- Só apanha o que é dito de forma explícita. "Vivo em Lisboa" não é guardado.
- Não há pesquisa semântica: procurar "cidade" não encontra "Lisboa".
- Uma memória por máquina, sem sessões separadas por utilizador.

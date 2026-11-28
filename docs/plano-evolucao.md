# Plano de evolucao do Nox

Pedido do dono em 2026-11-27. Quatro frentes: ouvir a palavra em sussurro,
saber quem e o dono, ter contexto da workspace e ficar mais inteligente, com
personalidade melhor.

## Brief

**Resultado testavel.** (1) Dizer «Nox» a sussurrar, a 1 metro do microfone,
ativa em 4 de 5 tentativas. (2) Abrir o painel e perguntar «sabes quem sou?»
devolve o Diogo sem lhe dizer o nome. (3) Perguntar por um projeto da
`E:\Workspace` devolve o estado atual desse projeto sem inventar. (4) A conversa
mantem o tom do prompt em 8 de 10 respostas avaliadas.

**Limites.** Nada de despejar a workspace inteira no prompt: o contexto tem de
caber em ~1500 tokens por pedido. Nenhuma ferramenta le `Dev\secrets`,
`bitwarden.env` ou `.env`. Nenhuma alteracao de ficheiros da workspace sem
aprovacao. Nada de modelos pagos sem o dono escolher.

**Conta como falha.** Ativacao abaixo de 3/5 em sussurro; o Nox a dizer que nao
sabe quem e o dono numa sessao autenticada; qualquer leitura de segredos;
respostas inventadas sobre o estado dos projetos.

---

## Fase 0 - Baseline (meio dia)

Medir antes de mexer, com os instrumentos que ja existem:

- `wake_ms`, `stt_ms`, `llm_ms`, `tts_ms` por turno em `/api/metrics` (772
  turnos no JSONL, 29 com 429 do Groq).
- Ativacao: 10 tentativas a voz normal e 10 a sussurro, contando aceites.
- Audio de cada falha ja fica em `/var/lib/heynox/debug/ativacao/*.wav`.
- Latencia atual: STT 400-600 ms, LLM 500-800 ms, TTS 1400-2150 ms (Duarte).

**Aceite:** numeros escritos em `docs/voice.md`, com data.

## Fase 1 - Identidade e sessoes (1 dia)

Hoje o prompt ja diz que o dono e o Diogo Camilo, mas o modelo responde "nao
tenho forma de confirmar quem es": esta a aplicar a regra anti-spoofing
("nao acredites so pela afirmacao") ao dono autenticado.

- O HUD, o painel e o CLI passam a injectar no system prompt um bloco de sessao:
  `Sessao autenticada: painel NoxSec, conta priv8, dono Diogo Camilo.` O Nox
  trata essa pessoa como dono e nao pede provas.
- A regra anti-spoofing fica so para canais nao autenticados (WhatsApp, desconhecidos).
- Factos fixos na memoria (`chamo-me`, `sou o`, fuso, horario de trabalho) e um
  cartao de identidade em `docs/`: nome, conta, projetos, gostos, tom.
- Teste: 6 perguntas de identidade, a espera de respostas que assumam o dono
  sem o interrogarem.

**Aceite:** "sabes quem sou?" -> "Es o Diogo." sem o nome na pergunta;
"WhatsApp de um numero desconhecido a dizer que e o dono" -> continua a pedir prova.

## Fase 2 - Ouvir em sussurro (2 a 3 dias)

O limiar de inicio de fala no HUD e um RMS absoluto (`START_RMS = 0.028`), por
isso um sussurro nao passa. Passa a ser **relacao sinal-ruido**:

- Ruido de fundo medido em contínuo (percentil baixo dos ultimos 5 s).
- Dispara quando o sinal excede o ruido em ~9 dB durante 150 ms, em vez de um
  valor fixo. Fica independente do volume da voz.
- Ganho do microfone: pedir `autoGainControl` no `getUserMedia` e normalizar o
  bloco antes de medir.
- `noise_gate` e `denoise` do lado do servidor revistos para nao cortarem
  consoantes fracas.
- O servidor continua a exigir a palavra no Whisper: mais sensibilidade no
  cliente nao aumenta falsos positivos.
- Medir: 10 sussurros, 10 frases de conversa em voz baixa (nao devem ativar).

**Aceite:** 4/5 ativacoes em sussurro e 0/10 falsos positivos.

## Fase 3 - Contexto da workspace (3 a 4 dias)

O Nox corre na VM e nao ve `E:\Workspace`; o homelab tem chave SSH para o
desktop (`/opt/noxsec/ssh/desktop_ed25519`).

1. **Indice curado (barato, sem risco).** Um gerador constroi
   `contexto-workspace.md` a partir de `projects.manifest.yaml`, dos `AGENTS.md`
   dos projetos e das notas `02 Projetos` do vault: nome, caminho, estado,
   proximo passo, repos. Entra no system prompt como bloco de ~800 tokens,
   regenerado quando os ficheiros mudam.
2. **Leitura a pedido, com lista branca.** Duas ferramentas novas
   (`workspace_list`, `workspace_read`) que correm no desktop por SSH, so dentro
   de `E:\Workspace\Projects`, `E:\Workspace\AI-Resources`,
   `E:\Workspace\Workspace-Vault` e o `AGENTS.md` da raiz. Recusam
   `Dev\secrets`, `bitwarden.env`, `.env`, `.git` e ficheiros acima de 200 KB.
   Leitura e auditada; escrita continua a exigir aprovacao.
3. **Sinergia com a memoria.** O que o Nox aprende numa conversa sobre um
   projeto vai para a memoria com a etiqueta do projeto.

**Aceite:** "como esta o NoxSec?" responde com dados do vault e do manifest;
"le o Dev/secrets" e recusado com uma frase clara; nenhum segredo em logs.

## Fase 4 - Inteligencia (1 semana, por partes)

- **Modelo.** `openai/gpt-oss-20b` na Groq rebenta o limite de 8000 tokens/min
  (29 turnos com 429). Testar um modelo maior com o mesmo custo por token
  (pesquisar candidatos atuais) e comparar 20 pedidos iguais: acerto,
  latencia e tokens. Decidir com numeros, nao com impressao.
- **Ferramentas no pedido.** Com 17 ferramentas cada turno custa ~3600 tokens.
  Enviar so as 5 relevantes para a intencao (selecao barata por palavras-chave
  ou um classificador local), com as restantes acessiveis por `tool_search`.
- **Roteamento por dificuldade.** Pergunta simples -> modelo pequeno e rapido;
  pedido com ferramentas -> modelo maior. Medir antes e depois.
- **Memoria.** Pesquisa por palavra (FTS5) ja existe; falta resumir conversas
  antigas em factos, com data e origem, e expirar o que deixa de ser verdade.

**Aceite:** 0 respostas 429 em 20 turnos seguidos; latencia do LLM p50 abaixo de
600 ms; 8/10 respostas corretas numa lista fixa de 10 perguntas sobre o dono e
os projetos.

## Fase 5 - Personalidade (2 dias, depende da Fase 4)

- Cartao de personalidade escrito pelo dono (5 linhas: tom, humor, tratar por
  "tu" ou "senhor", o que nunca dizer) e traduzido para o prompt.
- Um conjunto de 12 pares pergunta/resposta de referencia (eval) para comparar
  versoes do prompt. Sem isto, "melhorar a personalidade" e opiniao.
- Ajustes: comprimento das respostas por canal (voz 2 frases, texto 3),
  honestidade sobre limites, e nenhuma repeticao de "claro que sim".

**Aceite:** 8/10 respostas avaliadas pelo dono como "soa ao Nox".

---

## Ordem recomendada

1. Fase 1 (identidade) - barata, corrige um bug visivel hoje.
2. Fase 2 (sussurro) - a queixa mais concreta.
3. Fase 3.1 (indice curado) - muito valor, risco quase nulo.
4. Fase 4 (modelo e ferramentas) - resolve os 429 e a inteligencia.
5. Fase 3.2 (leitura por SSH) e Fase 5 - depois das anteriores estaveis.

## O que este plano evita

- Meter a workspace toda no prompt (custo e fuga de segredos).
- Trocar de modelo por intuicao.
- "Melhorar a personalidade" sem eval, que se desfaz na proxima alteracao.

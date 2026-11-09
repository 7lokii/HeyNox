# Voz

Pipeline: `áudio -> VAD -> STT -> LLM -> TTS -> áudio`.

| Etapa | Extra | Biblioteca | Estado |
|---|---|---|---|
| Captura | `audio` | sounddevice | **funcional** |
| Wake word | `wake` | vosk | **funcional** |
| VAD | `vad` | webrtcvad | **funcional** |
| STT | `stt` | faster-whisper | **funcional** |
| TTS | `tts` | piper | **funcional** |
| TTS online | `edge` | edge-tts | **funcional** |

Instalar tudo: `pip install -e ".[voice]"`.

Sem os extras, o Nox arranca em modo texto e `nox --check` indica o que falta.
Nenhum áudio sai do PC sem confirmação explícita.

## Conversa por voz

```bash
nox --voice                   # microfone
nox --voice --input a.wav     # o mesmo pipeline, a partir de um ficheiro
nox --devices                 # lista as entradas de áudio
```

O loop é: microfone -> `Segmenter` (WebRTC VAD) -> faster-whisper -> agente ->
Piper -> altifalante. Sem wake word, o Nox ouve sempre: `--voice` é conversa
contínua até Ctrl+C.

`--input` existe para testar sem falar ao computador. Um WAV com 0,5 s de
silêncio antes e 1 s depois atravessa o pipeline todo e produz a resposta falada.

## Testar sem microfone

```bash
nox --speak "Bom dia. Eu sou o Nox."          # grava WAV e diz onde
nox --speak "Bom dia." --out data/bom.wav     # destino à escolha
nox --transcribe data/bom.wav                 # devolve o texto
```

O `--speak` grava por omissão em `%LOCALAPPDATA%\HeyNox\out\nox.wav`.

## Modelos

| Modelo | Tamanho | Onde fica | Quando é descarregado |
|---|---|---|---|
| Piper `pt_PT-tugão-medium` | ~60 MB | `%LOCALAPPDATA%\HeyNox\models\piper\` | no primeiro `--speak` |
| Whisper `small` | ~480 MB | cache do Hugging Face | no primeiro `--transcribe` |

O download da voz é feito por `nox/models.py`, não pelo `piper-tts`: o
download oficial não faz URL-encoding e rebenta com `UnicodeEncodeError` em
`pt_PT-tugão-medium`.

### Downloads do Hugging Face pendurados

Em algumas redes o `hf_xet` (transferência por chunks) fica parado a 0 MB/s.
Sintoma: o primeiro `--transcribe` nunca acaba. Solução:

```bash
HF_HUB_DISABLE_XET=1 nox --transcribe audio.wav
```

Com esta variável, o modelo `small` (~480 MB) desce em cerca de dois minutos.

## Qualidade medida (CPU, `small`, int8)

Ida e volta com a voz `pt_PT-tugão-medium`:

| Dito | Ouvido |
|---|---|
| “O Nox está a ouvir muito bem.” | “O Nox está ouvindo muito bem.” |
| “São duas e quarenta e três.” | “São duas e quarenta e três.” |
| “São duas e quarenta e três da manhã.” | “São 2h40 e 3h da manhã.” |
| “São catorze e trinta e dois.” | “São 14,32.” |

Três coisas a reter:

- **Sem `initial_prompt` o nome falha.** “Nox” saía como “nosso”, “Morse” ou
  “Não resta”. O prompt é gerado a partir de `nox.name` e `nox.wake_word`.
- **O Whisper de português pende para o Brasil.** Aparece “ouvindo” onde se
  disse “a ouvir”. Com `beam_size: 3` acerta mais vezes; com 1 escolhe sempre
  a forma brasileira.
- **Números e horas são frágeis.** Frases curtas saem certas; com mais contexto
  o modelo inventa dígitos. Para comandos chega, para ditado não.

Latência: ~2,5 s para transcrever 2 s de áudio neste CPU. O modelo `medium`
melhora os números, mas triplica o tempo. Uma GPU muda a equação.

## Vozes disponíveis

| Provider | Vozes | Onde corre | Como soa |
|---|---|---|---|
| `piper` | `pt_PT-tugão-medium` | local (ONNX) | seca, robótica, mas honesta |
| `edge` | `pt-PT-DuarteNeural`, `pt-PT-RaquelNeural` | rede (Microsoft) | natural, com respiração e entoação |

Para trocar, duas linhas no `config.yaml`:

```yaml
tts:
  provider: "edge"
  voice: "pt-PT-RaquelNeural"
```

O `edge` manda o texto do Nox para a Microsoft — não é local-first. É a opção
para quem quer a melhor voz e aceita a rede; o Piper é a opção offline. O
`pt-PT-DuarteNeural` é masculino, o `pt-PT-RaquelNeural` feminino.

## Porque Piper e não Kokoro

O Kokoro só tem vozes de português do Brasil, e o `config.yaml` antigo apontava
`voice: "pt-PT-male"`, que não é um id válido. O Piper tem
`pt_PT-tugão-medium`, é ONNX, corre em CPU e não arrasta PyTorch.

O STT também não usa PyTorch: o faster-whisper assenta em CTranslate2. Com
Piper + faster-whisper, o `torch` só é preciso para o Silero VAD — e o VAD por
omissão é o do WebRTC, que também não precisa.

## Latência do loop completo

CPU sem GPU, `small` int8, voz `edge`, pergunta de 3 s:

| | Antes | Agora |
|---|---|---|
| Silêncio até haver som | 4,2 s | 0 s (filler) |
| A resposta começa | 4,2 s | 3,4 s |
| Fim do turno | 4,0 s | 4,0 s |

O que mexeu:

- **Filler pré-sintetizado.** "Hmm." / "Deixa-me ver." são gerados no arranque
  (em paralelo) e tocados assim que a frase fecha, enquanto o STT corre noutra
  thread. Cobre o silêncio *sem* lhe somar tempo — em série, atrasava.
- **Silêncio do segmentador 700 → 500 ms** (`audio.vad.silence_ms`).
- **TTS por frases**, com a síntese da seguinte a sobrepor-se à reprodução.

O que **não** mexeu, e porquê:

- **Cortar o silêncio antes do STT** poupa 2,4 s de áudio e 0 s de tempo: o
  Whisper codifica sempre uma janela de 30 s. Fica por limpeza do sinal, não
  por velocidade.
- **`base` em vez de `small`** é 2× mais rápido mas inventa — "Que horas são?"
  saiu "Eora-seu." e uma vez repetiu o próprio prompt. Fica `small`.
- **`beam_size` e `without_timestamps`** valem <0,1 s. O encoder domina, não o
  descodificador.
- **GPU** não há nesta máquina; com CUDA o STT deixaria de ser o gargalo.

O piso atual é o STT: ~2,3 s por frase, quase tudo codificação. Para baixar
disto sem GPU só com um modelo acústico mais leve (Vosk, sherpa-onnx) ou
transcrição incremental enquanto se fala.

## Wake word

Três formas ativam o Nox: **"Nox"**, **"Ei Nox"** e **"Hey Nox"**. O detetor
procura a palavra distintiva, por isso "hey"/"ei" são opcionais:

```yaml
wake:
  phrases: ["nox", "ei nox", "hey nox"]
```

### Porque é que "Nox" sozinho não era reconhecido

**"nox" não existe no dicionário do modelo português.** O Vosk não pode
devolver uma palavra que não conhece, por isso escrevia "inox" — e um "Nox"
curto virava "bom", "no" ou nada.

A solução é **vocabulário restrito** (`wake.grammar`): em vez de reconhecer
qualquer coisa, o descodificador escolhe entre três hipóteses.

```yaml
wake:
  grammar: ["inox", "ei inox", "[unk]"]
```

Medido com duas vozes e ruído branco adicionado:

| Ruído | "Nox" | "Hey Nox" | "Ei Nox" | Conversa normal |
|---|---|---|---|---|
| 0 | ✅ | ✅ | ✅ | não dispara |
| 400 | ✅ | ✅ | ✅ | não dispara |
| 800 | ✅ | ✅ | ✅ | não dispara |

Sem gramática, o mesmo "Nox" saía como "bom" numa das vozes.

Há ainda um **cooldown de 2 s** depois de disparar: sem ele, a cauda da palavra
voltava a armar o detetor e disparava duas vezes.

### Impressão vocal: várias vozes, ou só a tua

O Vosk não aprende com a tua voz — é um reconhecedor genérico. O que se pode
fazer, e está feito, é **confirmar quem falou** depois de a palavra ser detetada.
Está **desligado por omissão**: sem perfis, qualquer voz ativa o Nox.

```bash
nox --enroll --name rui            # grava 3 amostras pelo microfone
nox --enroll --name ana            # outra pessoa, mesmo Nox
nox --voiceprint                   # lista os perfis
nox --forget-voice --name rui      # apaga um
nox --forget-voice                 # apaga todos
```

Vários perfis convivem: a frase passa se bater com **qualquer um** deles. Para
ligar a verificação, `wake.voiceprint: true`.

Cada amostra vira um embedding de 256 dimensões (WeSpeaker ResNet34, ONNX,
25 MB) e o perfil é a média. Na ativação, a frase é comparada por cosseno:
abaixo de `wake.voiceprint_threshold` (0,35) o Nox ignora.

Medido com duas vozes sintéticas distintas:

| | Semelhança com o perfil |
|---|---|
| mesma voz, frase diferente | 0,46 ✅ |
| outra voz | 0,19 ❌ |

**Porque não MFCC:** a primeira tentativa usou média e desvio de MFCC. Uma voz
masculina e uma feminina deram **0,989** de semelhança — mede o canal e o texto,
não a pessoa. Foi descartada.

Limites: com 3 amostras de 2 s o perfil é frágil; quanto mais amostras, melhor.
O limiar 0,35 é conservador de propósito — é preferível não acordar do que
acordar com a voz de outra pessoa.

## Wake word (detalhe técnico)

O openWakeWord não traz modelo "hey nox" — os prontos são alexa, hey jarvis, hey
mycroft — e treinar um de raiz exige horas de GPU e vários GB de dados de
negativos. A solução foi **reconhecimento contínuo com o Vosk** (`vosk-model-small-pt-0.3`,
30 MB): o Nox transcreve localmente e procura a palavra no texto parcial.

O que se aprendeu por medição:

- **O reconhecedor pt escreve "Nox" como "inox".** "Hey Nox", "Ei Nox" e "Olá
  Nox" deram todos `a inox` / `olá inox`. A procura é por substring, por isso
  apanha as três. Exigir "hey" não funcionava — saía como "a".
- **Comparação por substring, não por distância de edição.** Com distância 1,
  a palavra "no" (comum demais) passaria por "nox".
- **O Vosk custa ~25% de um núcleo** a reconhecer. Por isso só é alimentado
  quando o VAD do WebRTC ouve fala, com 1,5 s de tolerância para não cortar a
  pausa entre "hey" e "nox". Em 5 s de silêncio: **zero** chamadas ao Vosk.

Custo: um falso positivo se alguém disser mesmo "inox". Aceitável.

### Ruído de fundo

Duas defesas, medidas com ruído branco adicionado:

| Ruído (RMS) | "Nox" | "Ei Nox" | "Hey Nox" | "Bom dia, tudo bem?" |
|---|---|---|---|---|
| 0 | ✅ | ✅ | ✅ | — |
| 300 | — | ✅ | ✅ | — |
| 600 | — | — | — | — |

- **Portão adaptativo** (`audio.noise_gate`): aprende o piso de ruído e só deixa
  passar o que está 2,5× acima. É o que impede o Vosk de correr num escritório
  ruidoso — e o que garante que uma conversa normal nunca acorda o Nox.
- **Subtração espectral em fluxo** (`audio.denoise_wake`, desligada por
  omissão): ajuda "Hey Nox" a 600 de ruído, mas estraga palavras curtas como
  "Nox". Experimental.

Acima de ~600 de ruído branco contínuo o reconhecedor deixa de ouvir a palavra.
É o limite do modelo pequeno, não do portão.

## Krisp e outros supressores

O SDK da Krisp existe, mas é comercial: entrada por candidatura, sem preço
público, e o binário é fechado. Não é algo que se meta num projeto MIT sem
contrato.

A via prática é a app de secretária da Krisp, que instala um **microfone
virtual**. Para o Nox, isso é só escolher o dispositivo:

```yaml
audio:
  input_device: "Krisp"
```

O `sounddevice` aceita o nome (ou parte dele) e o resto do pipeline não muda.
O mesmo serve para o NVIDIA Broadcast, o Voicemeeter ou qualquer supressor que
exponha um dispositivo de entrada.

Custo: a Krisp tem 7 dias de teste e depois ~8 €/mês. E acrescenta latência ao
caminho do áudio.

## Krisp e outros supressores

O SDK da Krisp existe, mas é comercial: entrada por candidatura, sem preço
público, e o binário é fechado. Não é algo que se meta num projeto MIT sem
contrato.

A via prática é a app de secretária da Krisp, que instala um **microfone
virtual**. Para o Nox, isso é só escolher o dispositivo:

```yaml
audio:
  input_device: "Krisp"
```

O `sounddevice` aceita o nome (ou parte dele) e o resto do pipeline não muda.
O mesmo serve para o NVIDIA Broadcast, o Voicemeeter ou qualquer supressor que
exponha um dispositivo de entrada.

Custo: a Krisp tem 7 dias de teste e depois ~8 €/mês. E acrescenta latência ao
caminho do áudio.

## Microfone preferido (Bluetooth)

```yaml
audio:
  input_device: "Mi TW"      # parte do nome chega
  input_fallback: "default"
```

O Nox procura o dispositivo pelo nome em cada arranque. Se estiver ligado, usa-o;
se não estiver, cai para a omissão sem reclamar. Se desaparecer a meio (headset
desligado), reabre no preferido ou na omissão.

Duas armadilhas resolvidas por medição:

- **WDM-KS não suporta a API bloqueante.** Headsets Bluetooth expõem-se muitas
  vezes só por WDM-KS, e `stream.read()` falha com "Blocking API not supported
  yet". A captura passou a usar callback + fila.
- **Taxas nativas diferentes.** O mesmo headset declara 8 kHz; o pipeline quer
  16 kHz. A fonte negocia a taxa e reamostra à saída.

`nox --devices` mostra qual seria escolhido, com `<-`.

## O anel da interface

Dois anéis, dois donos:

- **Exterior, ciano** — a voz do Nox, calculada sobre o áudio que está a sair.
- **Interior, verde** — o teu microfone, calculado bloco a bloco enquanto falas.
  Cresce para dentro para não se confundir com o outro.

O microfone é medido no `VoiceLoop`, com `MicMeter`: 48 bandas por bloco de
30 ms, com ataque rápido e decaimento lento, para o anel não tremer.

## Microfone preferido (Bluetooth)

```yaml
audio:
  input_device: "Mi TW"      # parte do nome chega
  input_fallback: "default"
```

O Nox procura o dispositivo pelo nome em cada arranque. Se estiver ligado, usa-o;
se não estiver, cai para a omissão sem reclamar. Se desaparecer a meio (headset
desligado), reabre no preferido ou na omissão.

Duas armadilhas resolvidas por medição:

- **WDM-KS não suporta a API bloqueante.** Headsets Bluetooth expõem-se muitas
  vezes só por WDM-KS, e `stream.read()` falha com "Blocking API not supported
  yet". A captura passou a usar callback + fila.
- **Taxas nativas diferentes.** O mesmo headset declara 8 kHz; o pipeline quer
  16 kHz. A fonte negocia a taxa e reamostra à saída.

`nox --devices` mostra qual seria escolhido, com `<-`.

## O anel da interface

Dois anéis, dois donos:

- **Exterior, ciano** — a voz do Nox, calculada sobre o áudio que está a sair.
- **Interior, verde** — o teu microfone, calculado bloco a bloco enquanto falas.
  Cresce para dentro para não se confundir com o outro.

O microfone é medido no `VoiceLoop`, com `MicMeter`: 48 bandas por bloco de
30 ms, com ataque rápido e decaimento lento, para o anel não tremer.

## Quando ele percebe outra coisa

O gargalo é o reconhecedor, não o modelo de linguagem. Três formas de atacar,
por ordem de custo:

**1. Ver o que ele ouviu.** Antes de mexer em nada:

```bash
nox --test-stt        # grava 4 s e mostra o texto tal como saiu do STT
nox --test-stt 6      # seis segundos
```

Se o texto sair errado, o problema é o STT. Se sair certo, o problema é o prompt.

**2. Modelo maior, local.** `stt.model: "medium"` (~1,5 GB, 3× mais lento). É a
opção que mantém tudo no PC.

**3. STT na cloud.** `stt.provider: "openai"` com `GROQ_API_KEY`. É o que o
FreeFlow faz: `whisper-large-v3` em ~0,4 s, muito mais preciso em português. O
áudio sai do PC — só tu podes decidir se aceitas.

## Ruído na transcrição

Antes do Whisper, a frase passa por `spectral_gate` (`stt.denoise`). Medido:

| Ruído | Sem limpeza | Com limpeza |
|---|---|---|
| 600 | "Que horas são?" | "Que horas são?" |
| 1200 | "E oração." | "E horas são." |

Em ruído moderado não muda nada; em ruído forte evita a transcrição inventada.

### Ruído de fundo

Duas defesas, medidas com ruído branco adicionado:

| Ruído (RMS) | "Nox" | "Ei Nox" | "Hey Nox" | "Bom dia, tudo bem?" |
|---|---|---|---|---|
| 0 | ✅ | ✅ | ✅ | — |
| 300 | — | ✅ | ✅ | — |
| 600 | — | — | — | — |

- **Portão adaptativo** (`audio.noise_gate`): aprende o piso de ruído e só deixa
  passar o que está 2,5× acima. É o que impede o Vosk de correr num escritório
  ruidoso — e o que garante que uma conversa normal nunca acorda o Nox.
- **Subtração espectral em fluxo** (`audio.denoise_wake`, desligada por
  omissão): ajuda "Hey Nox" a 600 de ruído, mas estraga palavras curtas como
  "Nox". Experimental.

Acima de ~600 de ruído branco contínuo o reconhecedor deixa de ouvir a palavra.
É o limite do modelo pequeno, não do portão.

## Krisp e outros supressores

O SDK da Krisp existe, mas é comercial: entrada por candidatura, sem preço
público, e o binário é fechado. Não é algo que se meta num projeto MIT sem
contrato.

A via prática é a app de secretária da Krisp, que instala um **microfone
virtual**. Para o Nox, isso é só escolher o dispositivo:

```yaml
audio:
  input_device: "Krisp"
```

O `sounddevice` aceita o nome (ou parte dele) e o resto do pipeline não muda.
O mesmo serve para o NVIDIA Broadcast, o Voicemeeter ou qualquer supressor que
exponha um dispositivo de entrada.

Custo: a Krisp tem 7 dias de teste e depois ~8 €/mês. E acrescenta latência ao
caminho do áudio.

## Krisp e outros supressores

O SDK da Krisp existe, mas é comercial: entrada por candidatura, sem preço
público, e o binário é fechado. Não é algo que se meta num projeto MIT sem
contrato.

A via prática é a app de secretária da Krisp, que instala um **microfone
virtual**. Para o Nox, isso é só escolher o dispositivo:

```yaml
audio:
  input_device: "Krisp"
```

O `sounddevice` aceita o nome (ou parte dele) e o resto do pipeline não muda.
O mesmo serve para o NVIDIA Broadcast, o Voicemeeter ou qualquer supressor que
exponha um dispositivo de entrada.

Custo: a Krisp tem 7 dias de teste e depois ~8 €/mês. E acrescenta latência ao
caminho do áudio.

## Microfone preferido (Bluetooth)

```yaml
audio:
  input_device: "Mi TW"      # parte do nome chega
  input_fallback: "default"
```

O Nox procura o dispositivo pelo nome em cada arranque. Se estiver ligado, usa-o;
se não estiver, cai para a omissão sem reclamar. Se desaparecer a meio (headset
desligado), reabre no preferido ou na omissão.

Duas armadilhas resolvidas por medição:

- **WDM-KS não suporta a API bloqueante.** Headsets Bluetooth expõem-se muitas
  vezes só por WDM-KS, e `stream.read()` falha com "Blocking API not supported
  yet". A captura passou a usar callback + fila.
- **Taxas nativas diferentes.** O mesmo headset declara 8 kHz; o pipeline quer
  16 kHz. A fonte negocia a taxa e reamostra à saída.

`nox --devices` mostra qual seria escolhido, com `<-`.

## O anel da interface

Dois anéis, dois donos:

- **Exterior, ciano** — a voz do Nox, calculada sobre o áudio que está a sair.
- **Interior, verde** — o teu microfone, calculado bloco a bloco enquanto falas.
  Cresce para dentro para não se confundir com o outro.

O microfone é medido no `VoiceLoop`, com `MicMeter`: 48 bandas por bloco de
30 ms, com ataque rápido e decaimento lento, para o anel não tremer.

## Microfone preferido (Bluetooth)

```yaml
audio:
  input_device: "Mi TW"      # parte do nome chega
  input_fallback: "default"
```

O Nox procura o dispositivo pelo nome em cada arranque. Se estiver ligado, usa-o;
se não estiver, cai para a omissão sem reclamar. Se desaparecer a meio (headset
desligado), reabre no preferido ou na omissão.

Duas armadilhas resolvidas por medição:

- **WDM-KS não suporta a API bloqueante.** Headsets Bluetooth expõem-se muitas
  vezes só por WDM-KS, e `stream.read()` falha com "Blocking API not supported
  yet". A captura passou a usar callback + fila.
- **Taxas nativas diferentes.** O mesmo headset declara 8 kHz; o pipeline quer
  16 kHz. A fonte negocia a taxa e reamostra à saída.

`nox --devices` mostra qual seria escolhido, com `<-`.

## O anel da interface

Dois anéis, dois donos:

- **Exterior, ciano** — a voz do Nox, calculada sobre o áudio que está a sair.
- **Interior, verde** — o teu microfone, calculado bloco a bloco enquanto falas.
  Cresce para dentro para não se confundir com o outro.

O microfone é medido no `VoiceLoop`, com `MicMeter`: 48 bandas por bloco de
30 ms, com ataque rápido e decaimento lento, para o anel não tremer.

## Quando ele percebe outra coisa

O gargalo é o reconhecedor, não o modelo de linguagem. Três formas de atacar,
por ordem de custo:

**1. Ver o que ele ouviu.** Antes de mexer em nada:

```bash
nox --test-stt        # grava 4 s e mostra o texto tal como saiu do STT
nox --test-stt 6      # seis segundos
```

Se o texto sair errado, o problema é o STT. Se sair certo, o problema é o prompt.

**2. Modelo maior, local.** `stt.model: "medium"` (~1,5 GB, 3× mais lento). É a
opção que mantém tudo no PC.

**3. STT na cloud.** `stt.provider: "openai"` com `GROQ_API_KEY`. É o que o
FreeFlow faz: `whisper-large-v3` em ~0,4 s, muito mais preciso em português. O
áudio sai do PC — só tu podes decidir se aceitas.

## Ruído na transcrição

Antes do Whisper, a frase passa por `spectral_gate` (`stt.denoise`). Medido:

| Ruído | Sem limpeza | Com limpeza |
|---|---|---|
| 600 | "Que horas são?" | "Que horas são?" |
| 1200 | "E oração." | "E horas são." |

Em ruído moderado não muda nada; em ruído forte evita a transcrição inventada.

```yaml
wake:
  provider: "vosk"     # ou "off" para ouvir sempre
  model: "vosk-model-small-pt-0.3"
  timeout_s: 8         # segundos à espera do pedido depois da palavra
```

`nox --voice --no-wake` desliga a exigência da palavra; `--input` desliga-a
sempre, porque um ficheiro já é o pedido.

### Porque não o Porcupine

Não é gratuito: o console oferece um teste de 7 dias e a partir daí o
licenciamento é comercial, negociado com vendas. Além disso, exige uma
AccessKey validada periodicamente com os servidores da Picovoice, o que quebra
o modo offline.

## Interrupção da fala

`audio.barge_in: true` faz o Nox calar-se quando começas a falar. Está
**desligado por omissão**, e por uma razão concreta: sem cancelamento de eco, o
microfone ouve o próprio Nox pelos altifalantes e ele interrompe-se sozinho.

O que dispara a interrupção é fala sustentada durante `barge_in_ms` (300 ms) e
acima de `barge_in_threshold` (800 de energia) — o VAD sozinho deixa passar o
eco. Com auscultadores funciona bem; com altifalantes, aumenta o limiar ou
deixa desligado.

O início da frase que interrompeu já foi lido do microfone, por isso esses
blocos entram no segmentador: não se perde a primeira palavra.

## Decisões pendentes

- **Modelo dedicado de wake word.** O Vosk resolve, mas gasta CPU e depende da
  transcrição. Um modelo openWakeWord treinado para "hey nox" seria mais leve
  (1 MB, ~3% de CPU) e mais preciso. Fica para quando houver tempo de treino.
- **Cancelamento de eco (AEC).** É o que tornaria o barge-in fiável com
  altifalantes.

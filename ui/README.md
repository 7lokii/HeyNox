# HUD do HeyNox

A cara do Nox, em TypeScript. Compila para `ui/dist`, que o motor Python serve à
janela nativa (`nox --desktop`) ou ao browser (`nox --ui`).

O motor não está aqui. Isto fala HTTP com `127.0.0.1:8765`.

## Comandos

```bash
npm install
npm run dev      # HUD com recarregar automático, proxy de /api para o motor
npm run build    # ui/dist (é o que o pacote leva)
npm run lint     # oxlint
```

Durante o desenvolvimento o motor tem de estar a correr: `nox --ui` noutro
terminal, ou o servidor falso, que não gasta LLM nem voz:

```bash
python scripts/mock-api.py 8765
```

Se o motor estiver noutro porto:

```bash
NOX_API=http://127.0.0.1:8766 npm run dev
```

## Estrutura

```
src/
  api.ts        Cliente dos endpoints
  types.ts      Contratos do backend (espelham nox/ui/state.py e server.py)
  voice.ts      Microfone local, VAD e reprodução da resposta
  App.tsx       Polling e composição
  components/   TopBar, Spectrum, ConversationLog, Approvals, MemoryPanel, Composer
  styles/       base.css (tokens, topo, palco) e panels.css (lateral, rodapé)
```

`components/Spectrum.tsx` desenha o anel em canvas a 60 fps e lê o espectro real
de `/api/levels` a cada 90 ms. O Nox fala a vermelho e, enquanto fala, o acento
do HUD acompanha; o microfone desenha ondas azuis. Em ecrãs estreitos (o WebView
da APK) o HUD passa a uma coluna compacta: reactor curto, conversa e painéis com
scroll interno e sem barras de página.

A voz é a do dispositivo, não a do serviço: o homelab não tem placa de som. O
`voice.ts` abre `getUserMedia`, mede a energia para começar e fechar a frase,
envia PCM 16 kHz a `/api/voice/turn` e toca o MP3 devolvido. O WebView da APK
pede a permissão Android pela ponte `NoxSec` quando se toca em **Ouvir**; no
browser é o pedido normal do Chrome. Sem permissão, o botão volta a Ouvir e o
HUD mostra um aviso persistente acima do rodapé, com «Tentar de novo»; o aviso
só desaparece quando o microfone abre com sucesso.

## Regras

- O visual é o do HUD original (`nox/ui/index.html`). Os valores das cores e das
  medidas estão afinados: mudar sem ver não é mudança, é risco.
- Nada de estado do motor aqui: a fonte da verdade é o Python. O HUD pede,
  desenha e volta a pedir.
- Uma falha de rede aparece como «sem ligação» no estado, nunca em branco.

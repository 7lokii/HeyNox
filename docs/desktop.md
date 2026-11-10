# Controlo do PC

A fase mais sensível: o Nox pode ver o ecrã e mexer no rato e no teclado. Por
isso está desligado por omissão no código, cada ação pede aprovação e há um
travão único.

## Ligar

```yaml
desktop:
  enabled: true
  confirm_actions: true
  allowed_apps:
    - "notepad.exe"
    - "calc.exe"
    - "explorer.exe"
  screenshot_dir: "data/screenshots"
```

Dependências:

```bash
pip install -e ".[desktop]"
```

`pyautogui` para rato/teclado, `mss` para capturas e o `winrt` para o OCR do
Windows. As janelas são lidas pela API do Windows (`ctypes`), sem dependência
extra. O instalador `.exe` precisa de ser reconstruído com este extra para a
funcionalidade existir lá dentro.

## Ações

| Ação | O que faz | Aprovação |
|---|---|---|
| `windows` | Lista janelas visíveis, com tamanho e ativa | não |
| `screenshot` | Guarda o ecrã em `data/screenshots/` | não |
| `ocr` | Lê o texto de uma imagem (ou de uma captura nova) | não |
| `focus` | Traz uma janela para a frente | **sim** |
| `move` | Move o rato para (x, y) | **sim** |
| `click` | Clica em (x, y), botão esquerdo/direito/meio | **sim** |
| `type` | Escreve texto (via clipboard, para acentos) | **sim** |
| `key` | Atalho, ex.: `ctrl+s` | **sim** |
| `open` | Abre uma app de `allowed_apps` | **sim** |
| `stop` | Ativa o modo de emergência | não |

Ler o ecrã não pede aprovação porque não altera nada — mas continua a ser
informação privada: as capturas ficam no teu disco, não saem do PC.

## Emergência

Três formas de parar:

1. Botão **Parar** no canto superior direito do HUD (fica **Retomar** quando
   está ativo).
2. Dizer **"para tudo"**, "emergência" ou "aborta o controlo".
3. Ferramenta `desktop` com `action: "stop"`.

Enquanto estiver ativo, **todas** as ações de desktop são recusadas, incluindo
capturas e listagens. Para voltar: dizer "retoma o controlo" ou carregar em
Retomar.

O modo de emergência não desliga o resto do Nox — a conversa, a memória e as
outras ferramentas continuam. É um travão do controlo do PC, não do assistente.

Para fechar o Nox (processo incluído), usa **Sair** no ícone da bandeja; o
botão Parar não termina o programa. Ver `docs/packaging.md`.

## OCR

Usa `Windows.Media.Ocr`, que já vem com o Windows e reconhece a língua do
perfil (neste caso, Português de Portugal). Não precisa de Tesseract nem de
modelos externos. Se o perfil não tiver OCR configurado, a ferramenta diz isso.

Limite: 6000 caracteres por leitura; o texto é normalizado (espaços colapsados)
e não guarda coordenadas das palavras.

## Limites

- **Não abre executáveis arbitrários**: só os de `allowed_apps`, comparados sem
  distinção de maiúsculas.
- Não há `shell=True`, nem comandos compostos.
- Texto limitado a 2000 caracteres; teclas validadas contra uma lista.
- `pyautogui.FAILSAFE`: atirar o rato para o canto superior esquerdo aborta a
  ação em curso.
- Cada ação é pontual. Não há gravação contínua do ecrã nem monitorização de
  teclas.
- As ações aparecem na auditoria (`audit.jsonl`) como qualquer ferramenta.

## O que ainda não faz

- Fechar aplicações (só abrir e focar).
- Arrastar e largar, scroll e duplo clique com botão direito.
- Visão contínua ou OCR em tempo real.
- Automação por coordenadas relativas a uma janela (as coordenadas são do ecrã
  inteiro; usa `screenshot` + `ocr` para as descobrir).

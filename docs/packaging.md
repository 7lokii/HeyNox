# Empacotamento e distribuição

Alvo: **Windows x64** compilado e testado; **macOS** (arm64 e x64) e **Linux**
(x64) compilados no CI. O código separa caminhos por plataforma em
`nox/paths.py` e o controlo do PC degrada onde não há `winrt`.

O empacotamento por sistema vive em `installer/<sistema>/` e a matriz completa
está em `docs/releases.md`.

## O que o instalador entrega

| Ficheiro | Pasta | Console | Conteúdo |
|---|---|---|---|
| `HeyNox.exe` | `dist\HeyNox\` | não | Agente completo: voz (torch, faster-whisper, piper, vosk, edge-tts), browser (Playwright), controlo do PC (pyautogui, mss, OCR winrt) e bandeja (pystray) |
| `nox.exe` | `dist\nox\` | sim | Núcleo e CLI para diagnóstico (`nox.exe --check`) |
| `HeyNox-Setup.exe` | `dist\` | — | Instalador Inno Setup com atalhos, desinstalador e arranque opcional |

Os modelos (Whisper, Piper, Vosk) **não** vão no instalador; são descarregados
na primeira utilização para `%LOCALAPPDATA%\HeyNox`.

Os **browsers** do Playwright também não vão: o Chromium vive em
`%LOCALAPPDATA%\ms-playwright`. Numa máquina nova, a ferramenta `browser` avisa
que falta e é preciso correr `python -m playwright install chromium` uma vez
(ou copiar essa pasta). O OCR não precisa de nada: usa o motor do Windows.

## Porque é que o build usa Python 3.11

A build usa 3.11 porque é a combinação já validada de torch, ctranslate2,
piper-tts e winrt no Windows. O `installer/build.ps1` cria um venv 3.11 próprio
com `uv` (`.build-venv/`) e não toca no Python do sistema.

## Como compilar

Pré-requisitos:

- `uv` (`winget install astral-sh.uv`)
- Inno Setup 6 (`winget install JRSoftware.InnoSetup`) — o script instala se faltar

```powershell
powershell -ExecutionPolicy Bypass -File installer\build.ps1
powershell -ExecutionPolicy Bypass -File installer\build.ps1 -SkipInstaller   # só os .exe
```

O script cria o venv com `uv` mas instala os extras com **pip**:
`pip install -e ".[voice,browser,desktop,tray]" pyinstaller`. O `uv` falhava a
compilar sdists antigos (`pygetwindow`, `pytweening`) porque a limpeza da cache
de build colide com o guard de deleções em massa desta máquina.

Existe um hook próprio em `installer\hooks\hook-webrtcvad.py`: o hook de contrib
procura metadados de `webrtcvad`, mas a distribuição chama-se
`webrtcvad-wheels` e o build morria com `PackageNotFoundError`.

Ficheiros gerados (não versionados): `installer\*.spec`, `build\`, `dist\`,
`.build-venv\`.

O script termina com erro se `nox.exe` ou `HeyNox.exe` não existirem em `dist\`
e corre `nox.exe --check` no executável compilado antes de gerar o instalador.

### Testar sem instalar

```powershell
dist\nox\nox.exe --check
dist\HeyNox\HeyNox.exe --check
```

O `HeyNox.exe` respeita os argumentos: sem nenhum abre a interface; com
`--check` faz o diagnóstico e sai. Sem consola, o resultado vai para
`%LOCALAPPDATA%\HeyNox\logs\nox.log`.

Para testar as ferramentas de desktop/browser dentro do executável é preciso
uma chave de modelo: `%LOCALAPPDATA%\HeyNox\.env` (o instalador não a copia).

### Instalação silenciosa (para testar)

```powershell
$T = "$env:TEMP\heynox-test"
Start-Process dist\HeyNox-Setup.exe -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/DIR=$T" -Wait
& "$T\nox.exe" --check        # avisa que faltam deps de voz (esperado: é o núcleo)
& "$T\HeyNox.exe" --check     # não deve avisar
# Abrir pelo atalho: ícone na bandeja. «Sair» fecha o processo inteiro.
& "$T\unins000.exe" /VERYSILENT
```

Nota: não correr o setup a partir do Git Bash — converte `/VERYSILENT` em
caminho e o setup abre interativo.

## Configuração no cliente

- Na instalação, `config.yaml` é copiado para a pasta da app **apenas se ainda
  não existir** e o desinstalador não o apaga.
- Um `config.yaml` em `%LOCALAPPDATA%\HeyNox\config.yaml` tem prioridade sobre o
  instalado; o mesmo para `.env`.
- Sem consola, erros vão para `%LOCALAPPDATA%\HeyNox\logs\nox.log`.
- Se o arranque falhar por uma exceção, sem consola aparece também uma caixa
  de erro com a última linha e o caminho do log.

## Bandeja e segunda instância

O `HeyNox.exe` não tem janela própria. Sem bandeja, fechar o browser deixava
o processo sem forma de ser reaberto ou fechado.

- O `.exe` abre uma janela própria (`--desktop`, pywebview sobre WebView2), não
  um separador do browser. O HUD vem de `ui/dist`, compilado pelo Vite antes do
  PyInstaller; sem esse build o pacote cai no `nox/ui/index.html` legado.
- O ícone `HeyNox` fica na bandeja: duplo clique (ou «Abrir interface») abre
  o HUD; o menu tem «Ouvir» (liga/desliga a voz) e «Sair».
- O porto aberto é guardado em `%LOCALAPPDATA%\HeyNox\ui.port` e apagado ao
  sair. Um segundo `HeyNox.exe` encontra esta instância pelo porto, reabre o
  browser e sai, em vez de subir outro servidor em 8766.
- A bandeja só existe no modo `--ui` sem consola: em `--desktop` quem manda no
  ciclo de vida é a janela. Precisa do extra `tray` (`pystray` + `Pillow`);
  se faltar, a UI continua e o aviso vai para o log.
- `multiprocessing.freeze_support()` no `scripts/heynox_app.py`: sem ele, um
  processo filho do torch voltava a arrancar a interface em vez de fazer o
  trabalho pedido.

## Notas

- Tamanho medido em Windows, build sem torch: `dist\HeyNox` 676 MB,
  `dist\nox` 578 MB, setup 240 MB, portable `.zip` 277 MB. Antes, com o torch
  empacotado, eram 1,1 GB e 339 MB.
- O `torch` saiu do `.spec`: só o Silero VAD o usava e o VAD por omissão é o
  `webrtcvad`. Volta com `build.ps1 -Silero` ou `HEYNOX_WITH_SILERO=1`.
- Ainda no pacote e a pesar: `playwright` 103 MB, `av` 63 MB, `ctranslate2`
  62 MB, `vosk` 52 MB, `scipy` 50 MB, `transformers` 47 MB. O `scipy` e o
  `transformers` entram por arrasto de dependências e são o próximo alvo.
- Assinatura de código (Authenticode) ainda não configurada; o SmartScreen vai
  mostrar aviso até haver certificado. No macOS, o `.app` é assinado ad-hoc,
  o que não substitui Developer ID nem notarização.

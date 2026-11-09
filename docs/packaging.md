# Empacotamento e distribuição

Alvo atual: **Windows x64**. O código já separa caminhos por plataforma
(`nox/paths.py`), mas Linux e macOS ainda não têm build validado.

## O que o instalador entrega

| Ficheiro | Pasta | Console | Conteúdo |
|---|---|---|---|
| `HeyNox.exe` | `dist\HeyNox\` | não | Agente completo, incluindo voz (torch, faster-whisper, kokoro, openwakeword, silero-vad) |
| `nox.exe` | `dist\nox\` | sim | Núcleo e CLI para diagnóstico (`nox.exe --check`) |
| `HeyNox-Setup.exe` | `dist\` | — | Instalador Inno Setup com atalhos, desinstalador e arranque opcional |

Os modelos (Whisper, Kokoro, openWakeWord) **não** vão no instalador; são
descarregados na primeira utilização para `%LOCALAPPDATA%\HeyNox`.

## Porque é que o build usa Python 3.11

`kokoro` declara `requires_python <3.13`, e no Windows as dependências de voz
resolvem-se sem compilador apenas em 3.11. O `installer/build.ps1` cria um venv
3.11 próprio com `uv` (`.build-venv/`) e não toca no Python do sistema.

## Como compilar

Pré-requisitos:

- `uv` (`winget install astral-sh.uv`)
- Inno Setup 6 (`winget install JRSoftware.InnoSetup`) — o script instala se faltar

```powershell
powershell -ExecutionPolicy Bypass -File installer\build.ps1
powershell -ExecutionPolicy Bypass -File installer\build.ps1 -SkipInstaller   # só os .exe
```

Ficheiros gerados (não versionados): `installer\*.spec`, `build\`, `dist\`,
`.build-venv\`.

O script termina com erro se `nox.exe` ou `HeyNox.exe` não existirem em `dist\`
e corre `nox.exe --check` no executável compilado antes de gerar o instalador.

### Testar sem instalar

```powershell
dist\nox\nox.exe --check
dist\HeyNox\HeyNox.exe --check
```

O `--check` do `HeyNox.exe` (sem consola) escreve em
`%LOCALAPPDATA%\HeyNox\logs\nox.log`.

### Instalação silenciosa (para testar)

```powershell
$T = "$env:TEMP\heynox-test"
Start-Process dist\HeyNox-Setup.exe -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/DIR=$T" -Wait
& "$T\nox.exe" --check        # avisa que faltam deps de voz (esperado: é o núcleo)
& "$T\HeyNox.exe" --check     # não deve avisar
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

## Notas

- Tamanho esperado: ~1 GB instalado (dominado por `torch`).
- Assinatura de código (Authenticode) ainda não configurada; o SmartScreen vai
  mostrar aviso até haver certificado.
- Linux/macOS: gerar o mesmo `.spec` noutra plataforma e alterar
  `build.ps1` para `build.sh`. Ainda não testado.

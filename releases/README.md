# Releases

Artefactos prontos a distribuir, um diretório por versão. Esta pasta não entra
no git: cada build pesa 300 a 500 MB e o git não é sítio para binários. A
distribuição pública é o GitHub Releases; esta pasta é a cópia local e a fonte
do `latest.json`.

```
releases/
  README.md
  latest.json
  0.1.0/
    SHA256SUMS
    windows/
    macos/
    linux/
```

## Nomes dos ficheiros

`HeyNox-<versao>-<plataforma>-<arch>-<variante>.<ext>`

| Plataforma | Arch | Variante | Extensão | Conteúdo |
|---|---|---|---|---|
| windows | x64 | setup | `.exe` | Inno Setup, atalhos, desinstalador |
| windows | x64 | portable | `.zip` | `HeyNox/` do PyInstaller, sem instalação |
| macos | arm64, x64 | setup | `.dmg` | `HeyNox.app` arrastável para Applications |
| macos | arm64, x64 | portable | `.tar.gz` | `HeyNox.app` |
| linux | x64 | setup | `.AppImage` | execução direta, sem instalação |
| linux | x64 | setup | `.deb` | integração com o sistema, menu e ícone |
| linux | x64 | portable | `.tar.gz` | diretório `HeyNox/` |

Exemplo: `HeyNox-0.1.0-windows-x64-portable.zip`.

## Setup e portable

As duas variantes correm o mesmo núcleo e leem os mesmos dados. A diferença é
onde ficam os binários.

- **Setup**: regista a aplicação no sistema (instalador, menu, desinstalador).
- **Portable**: um diretório que se copia e se apaga à mão. Sem registo no
  sistema, sem atalhos automáticos.

Os dados do utilizador ficam sempre fora do diretório da aplicação, em
`nox.paths.user_data_dir()`: `%LOCALAPPDATA%\HeyNox` no Windows,
`~/Library/Application Support/HeyNox` no macOS, `~/.local/share/HeyNox` no
Linux. É isto que torna o portable verdadeiramente portátil: apagar a pasta não
apaga memória, configuração nem perfis de voz.

## Integridade

Cada versão leva um `SHA256SUMS` com uma linha por ficheiro:

```bash
sha256sum -c SHA256SUMS          # Linux e macOS
Get-FileHash *.exe, *.zip -Algorithm SHA256   # Windows
```

## O que não vai nos artefactos

- Chaves de API. Vivem em `.env`, que o instalador não copia.
- Modelos (Whisper, Piper, Vosk). Descarregam na primeira utilização.
- Browsers do Playwright. Instalam-se com `python -m playwright install chromium`.

## latest.json

Aponta para a versão publicada mais recente e serve o verificador de
atualizações do Tauri. Formato:

```json
{
  "version": "0.1.0",
  "date": "2026-11-10",
  "platforms": {
    "windows-x64": { "setup": "0.1.0/windows/HeyNox-0.1.0-windows-x64-setup.exe" },
    "macos-arm64": { "setup": "0.1.0/macos/HeyNox-0.1.0-macos-arm64-setup.dmg" },
    "linux-x64": { "setup": "0.1.0/linux/HeyNox-0.1.0-linux-x64-setup.AppImage" }
  }
}
```

## Como se gera

Os builds correm no CI, um runner por sistema: PyInstaller e Tauri não
compilam para outra plataforma a partir do Windows. Ver
`docs/releases.md` para a matriz e os comandos.

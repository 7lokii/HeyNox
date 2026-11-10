# Releases e compilação por plataforma

Cada artefacto nasce no seu sistema. PyInstaller e Tauri não fazem
cross-compile: um `.dmg` só se monta em macOS e um `.AppImage` só se monta em
Linux. Por isso os três sistemas saem do CI, não desta máquina.

## Matriz

| Runner | Plataforma | Setup | Portable |
|---|---|---|---|
| `windows-latest` | windows-x64 | Inno Setup `.exe` | `.zip` |
| `macos-13` | macos-x64 | `.dmg` | `.tar.gz` |
| `macos-14` | macos-arm64 | `.dmg` | `.tar.gz` |
| `ubuntu-22.04` | linux-x64 | `.AppImage` e `.deb` | `.tar.gz` |

`ubuntu-22.04` e não `24.04` por causa da glibc: um binário compilado em 22.04
corre em 24.04, o contrário não. `macos-14` é arm64 e `macos-13` é x64, o que
cobre Apple Silicon e Intel.

## Como se dispara

```bash
git tag v0.1.0
git push origin v0.1.0
```

Ou manualmente, em Actions, workflow `release`, com a versão à mão. O workflow
`.github/workflows/release.yml` compila, corre `--check` no binário gerado,
escreve `SHA256SUMS` e publica no GitHub Releases.

## O que corre em cada runner

1. Python 3.11 e `pip install -e ".[voice,browser,...]" pyinstaller`, com
   `desktop` e `tray` só onde fazem sentido.
2. `python -m nox.main --check`, antes de empacotar.
3. `python -m installer.pyinstaller` gera os dois `.spec`.
4. `pyinstaller installer/HeyNox.spec` produz `dist/HeyNox/`.
5. Script de empacotamento da plataforma, em `installer/<sistema>/`.
6. `--check` no binário compilado, que falha o build se o pacote estiver quebrado.

## O torch ficou fora do pacote

O `torch` era 378 MB de 1,0 GB e só servia ao Silero VAD. O VAD por omissão é o
`webrtcvad`, que pesa 10 KB. O `.spec` passa a excluir `torch`, `torchaudio` e
`silero_vad`.

Para voltar a incluir:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build.ps1 -Silero
```

```bash
HEYNOX_WITH_SILERO=1 python -m installer.pyinstaller
```

O extra `silero` do `pyproject.toml` continua a existir para desenvolvimento.

## Assinatura de código

Sem certificado, os builds funcionam mas avisam:

| Sistema | Sintoma | Resolve |
|---|---|---|
| Windows | SmartScreen e aviso do Defender | Certificado EV ou OV, ou reputação acumulada |
| macOS | Gatekeeper recusa; no arm64 o `.app` tem de estar assinado | Developer ID (99 USD/ano) e notarização com `notarytool` |
| Linux | Nenhum | Não aplicável |

O script de macOS faz assinatura ad-hoc (`codesign --sign -`), o mínimo para o
binário arm64 arrancar. Isso não substitui o Developer ID: sem notarização, o
utilizador tem de abrir com botão direito, Abrir.

## Portable, medido

O portable só é portátil porque os dados ficam fora do diretório da aplicação,
em `nox.paths.user_data_dir()`:

| Sistema | Dados |
|---|---|
| Windows | `%LOCALAPPDATA%\HeyNox` |
| macOS | `~/Library/Application Support/HeyNox` |
| Linux | `~/.local/share/HeyNox` |

Copiar a pasta para outro sítio, ou apagá-la, não toca em memória, perfis de
voz, rotinas nem chaves.

## Limites conhecidos

- `winrt`, `mss` e `pyautogui` são Windows-only. Em macOS o controlo do PC tem
  menos funções (sem OCR do sistema). Em Linux precisa de `xdotool` e de um
  servidor X, e Wayland limita a captura de ecrã.
- Sem chave de modelo nos artefactos. O `.env` é do utilizador.
- Modelos (Whisper, Piper, Vosk) e browsers do Playwright descarregam-se na
  primeira utilização. Um primeiro arranque offline fica sem voz.

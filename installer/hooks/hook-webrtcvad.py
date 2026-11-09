"""Substitui o hook de contrib do webrtcvad.

O pacote instalado chama-se `webrtcvad-wheels`, mas o hook do
`pyinstaller-hooks-contrib` procura metadados de `webrtcvad` e rebenta com
PackageNotFoundError. Aqui tentamos os dois nomes e, em último caso, seguimos
sem metadados — o módulo em si é incluído na mesma.
"""

from PyInstaller.utils.hooks import copy_metadata  # pyright: ignore[reportMissingModuleSource]

try:
    datas = copy_metadata("webrtcvad")
except Exception:  # noqa: BLE001 — o nome varia com a distribuição
    try:
        datas = copy_metadata("webrtcvad-wheels")
    except Exception:  # noqa: BLE001
        datas = []

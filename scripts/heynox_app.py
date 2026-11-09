"""Ponto de entrada do HeyNox.exe (sem consola, lançador de desktop)."""

import sys

from nox.main import main

# Sem argumentos, abre a interface. Com argumentos (ex.: --check), respeita-os
# para o executável poder ser diagnosticado como o nox.exe.
args = sys.argv[1:] or ["--ui"]
raise SystemExit(main(args))

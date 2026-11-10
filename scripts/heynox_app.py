"""Ponto de entrada do HeyNox.exe (sem consola, lançador de desktop)."""

import multiprocessing
import sys

from nox.main import main

# O torch e o PyInstaller: sem isto os processos filhos re-executam o .exe
# e abrem outra interface em vez de fazer o trabalho pedido.
multiprocessing.freeze_support()

# Sem argumentos, abre a interface. Com argumentos (ex.: --check), respeita-os
# para o executável poder ser diagnosticado como o nox.exe.
args = sys.argv[1:] or ["--ui"]
raise SystemExit(main(args))

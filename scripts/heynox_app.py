"""Ponto de entrada do HeyNox.exe (sem consola, lançador de desktop)."""

from nox.main import main

# Sem consola não há nada para mostrar: o executável abre a interface local.
raise SystemExit(main(["--ui"]))

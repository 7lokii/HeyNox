"""Compara modelos com o prompt real do Nox.

Corre no homelab, com o venv do servico:
    HEYNOX_DATA_DIR=/var/lib/heynox /opt/heynox/.venv/bin/python scripts/comparar-modelos.py

Medido a 2026-11-28: o `gpt-oss-20b` (o atual) foi o unico que respondeu a tudo;
o `120b` levou 429 e 10,5 s; o `qwen3.8-27b` levou 429 em 3 de 4. O limite
gratuito da Groq e por modelo e por minuto, e os maiores gastam-no depressa.
"""
import io, os, sys, time
sys.path.insert(0, "/opt/heynox")
os.environ["HEYNOX_DATA_DIR"] = "/var/lib/heynox"
import yaml
from nox.config import Config
from nox.brain.agent import build_agent
from nox.brain.prompt import session_block

base = yaml.safe_load(io.open("/var/lib/heynox/config.yaml", encoding="utf-8").read())
PERGUNTAS = ["quem te criou?", "quem sou eu?", "o que é um tunel da Cloudflare?", "tenho 8 GB e 4 nucleos, cabe o Proxmox com 6 VMs?"]
for modelo in ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"):
    dados = dict(base)
    dados["llm"] = dict(base["llm"], model=modelo)
    cfg = Config.model_validate(dados)
    print(f"\n=== {modelo}")
    for p in PERGUNTAS:
        agente = build_agent(cfg, identity=session_block(owner=cfg.nox.owner, account=cfg.nox.owner_account))
        t0 = time.monotonic()
        try:
            r = agente.reply(p)
        except Exception as e:
            r = f"ERRO {e}"
        print(f"  [{round((time.monotonic()-t0)*1000):5d} ms] {p}")
        print(f"    -> {r[:150]}")

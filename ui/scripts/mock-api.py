"""Servidor falso do backend do Nox, só para verificar a UI.

Não faz parte do produto. Serve `nox/ui/server.py` com dados fixos: dois turnos,
uma aprovação pendente, três factos e espectro animado.

    python ui/scripts/mock-api.py [porto]
"""

from __future__ import annotations

import json
import math
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BANDS = 48
facts = [
    {"id": 1, "kind": "nome", "text": "o utilizador chama-se Rui"},
    {"id": 2, "kind": "preferencia", "text": "prefere respostas curtas"},
    {"id": 3, "kind": "nota", "text": "trabalha em E:\\Workspace"},
]
turns = [
    {"role": "user", "text": "que horas são?", "at": time.time() - 20},
    {
        "role": "assistant",
        "text": "São 19:04. Queres que trate de mais alguma coisa?",
        "at": time.time() - 18,
    },
]
approvals = [
    {
        "id": "ap-1",
        "summary": "Executar comando no shell",
        "detail": "git status --short\n(cwd: E:\\Workspace\\Projects\\HeyNox)",
        "action": "shell:git status --short",
    }
]

start = time.time()


def levels(offset: float) -> list[float]:
    t = time.time() - start + offset
    out = []
    for i in range(BANDS):
        band = i if i < BANDS / 2 else BANDS - 1 - i
        value = 0.55 + 0.45 * math.sin(t * 4.0 + band * 0.55)
        out.append(max(0.0, value))
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/state":
            self._json(
                {
                    "status": "a falar",
                    "voice": True,
                    "levels": levels(0),
                    "input_levels": levels(1.7),
                    "source": "nox",
                    "turns": turns,
                    "approvals": approvals,
                    "emergency": False,
                    "voice_error": "",
                }
            )
        elif self.path == "/api/levels":
            self._json(
                {
                    "levels": levels(0),
                    "input": levels(1.7),
                    "source": "nox",
                    "status": "a falar",
                }
            )
        elif self.path == "/api/memory":
            self._json({"facts": facts})
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        reply = {"answer": "ok", "voice": True, "removed": 0, "decided": True, "emergency": False}
        self._json(reply)

    def _json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"mock api em http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

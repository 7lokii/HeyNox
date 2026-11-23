#!/usr/bin/env bash
# Instala o HeyNox como serviço no homelab. Correr como root a partir do
# checkout extraído em /tmp/heynox-install (ou de qualquer cópia com nox/ e
# ui/dist já construídos).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "corre como root" >&2
  exit 1
fi

raiz="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
destino=/opt/heynox
dados=/var/lib/heynox
usuario=heynox
servico=heynox.service

test -f "$raiz/nox/main.py"
test -f "$raiz/ui/dist/index.html"

if ! id "$usuario" >/dev/null 2>&1; then
  useradd --system --home "$dados" --shell /usr/sbin/nologin "$usuario"
fi

install -d -m 0755 -o root -g root "$destino"
install -d -m 0750 -o "$usuario" -g "$usuario" "$dados"

# Só o código e o HUD compilado. Dados, .env e .venv ficam fora desta cópia.
rm -rf "$destino/nox" "$destino/ui"
install -d -m 0755 -o root -g root "$destino/ui"
tar -C "$raiz" -cf - nox ui/dist pyproject.toml README.md \
  | tar -C "$destino" -xf -
test -f "$destino/ui/dist/index.html"

if [ ! -f "$dados/config.yaml" ]; then
  install -m 0640 -o "$usuario" -g "$usuario" "$raiz/deploy/config.yaml" "$dados/config.yaml"
fi
if [ ! -f "$dados/.env" ]; then
  install -m 0600 -o "$usuario" -g "$usuario" /dev/null "$dados/.env"
fi

if [ ! -x "$destino/.venv/bin/python" ]; then
  python3 -m venv "$destino/.venv"
fi
"$destino/.venv/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
# WhatsApp e edge-tts. A voz do microfone do servidor fica desligada (o
# hardware não tem placa de som); o edge é para o HUD remoto devolver MP3.
"$destino/.venv/bin/pip" install --no-cache-dir -e "$destino[whatsapp,edge]"

install -m 0644 "$raiz/deploy/heynox.service" "/etc/systemd/system/$servico"
chown -R root:root "$destino"
chown -R "$usuario:$usuario" "$dados"
systemctl daemon-reload
systemctl enable "$servico"
systemctl restart "$servico"

ok=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8765/api/health >/dev/null; then
    ok=1
    break
  fi
  sleep 1
done
if [ "$ok" -ne 1 ]; then
  echo "o HeyNox não respondeu; últimas linhas do journal:" >&2
  journalctl -u "$servico" -n 40 --no-pager >&2 || true
  exit 1
fi

echo "HeyNox ativo em http://127.0.0.1:8765"
echo "Dados: $dados"
echo "Chave do modelo: $dados/.env (NOX_LLM_API_KEY)"

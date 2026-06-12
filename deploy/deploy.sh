#!/usr/bin/env bash
# deploy.sh - Actualiza tvbot y reinicia servicios. Uso (en la VM): bash /opt/tvbot/deploy/deploy.sh
set -euo pipefail
APP_DIR="/opt/tvbot"
PY="${APP_DIR}/.venv/bin/python"

cd "$APP_DIR"
echo "=== TVBOT DEPLOY - $(TZ=America/Lima date '+%Y-%m-%d %H:%M') Lima ==="
echo "[1/4] git pull..."
sudo -u "$(stat -c '%U' .)" git pull --ff-only
echo "[2/4] dependencias..."
"$PY" -m pip install --quiet -r requirements.txt || true
echo "[3/4] verificacion de imports..."
"$PY" -c "import config; from tvbot import engine, orchestrator; from tvbot.api import app" || { echo "IMPORT FALLO - no se reinicia"; exit 1; }
echo "[4/4] reiniciando servicios..."
sudo systemctl restart tvbot tvbot-api
sleep 2
sudo systemctl --no-pager status tvbot | head -3
sudo systemctl --no-pager status tvbot-api | head -3
echo "OK"

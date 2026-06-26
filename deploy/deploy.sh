#!/usr/bin/env bash
# deploy.sh - Actualiza tvbot y reinicia servicios. Uso (en la VM): bash /opt/tvbot/deploy/deploy.sh
set -euo pipefail
APP_DIR="/opt/tvbot"
PY="${APP_DIR}/.venv/bin/python"

cd "$APP_DIR"
echo "=== TVBOT DEPLOY - $(TZ=America/Lima date '+%Y-%m-%d %H:%M') Lima ==="
echo "[1/4] git pull..."
# -H carga el HOME del dueño (opc) para que git/ssh encuentren ~/.ssh/config + la deploy key
# (remote por SSH). Sin -H, al invocar el script con sudo el pull buscaba la key en /root/.ssh y fallaba.
sudo -H -u "$(stat -c '%U' .)" git pull --ff-only
echo "[2/4] dependencias..."
"$PY" -m pip install --quiet -r requirements.txt || true
echo "[3/4] verificacion de imports..."
"$PY" -c "import config; from tvbot import engine, orchestrator, backup, watchdog, notify; from tvbot.api import app" || { echo "IMPORT FALLO - no se reinicia"; exit 1; }
echo "[4/4] actualizando units systemd + reiniciando servicios..."
sudo cp "$APP_DIR"/deploy/tvbot.service "$APP_DIR"/deploy/tvbot-api.service \
        "$APP_DIR"/deploy/tvbot-backup.service "$APP_DIR"/deploy/tvbot-backup.timer \
        "$APP_DIR"/deploy/tvbot-watchdog.service "$APP_DIR"/deploy/tvbot-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart tvbot tvbot-api
sudo systemctl enable --now tvbot-backup.timer tvbot-watchdog.timer
sleep 2
sudo systemctl --no-pager status tvbot | head -3
sudo systemctl --no-pager status tvbot-api | head -3
echo "timers:" && systemctl --no-pager list-timers 'tvbot-*' | head -4
echo "OK"

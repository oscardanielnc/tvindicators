#!/usr/bin/env bash
# setup_vm.sh - Instala tvbot en la VM Oracle (ejecutar UNA sola vez, con sudo).
# Antes: sudo git clone https://github.com/oscardanielnc/tvindicators.git /opt/tvbot
# Uso:   cd /opt/tvbot && sudo bash deploy/setup_vm.sh
set -euo pipefail

APP_DIR="/opt/tvbot"
VENV="${APP_DIR}/.venv"
OWNER="${SUDO_USER:-opc}"

echo "=== TVBOT - SETUP VM (primera vez) ==="

echo "[1/5] venv + dependencias..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "[2/5] verificacion de imports..."
cd "$APP_DIR"
"$VENV/bin/python" -c "import config; from tvbot import engine, orchestrator; from tvbot.api import app; from tvbot.strategies import STRATEGIES; print(f'  OK - {len(STRATEGIES)} estrategias')"

echo "[3/5] servicios systemd (bot, api, backup, watchdog)..."
cp "$APP_DIR"/deploy/tvbot.service "$APP_DIR"/deploy/tvbot-api.service \
   "$APP_DIR"/deploy/tvbot-backup.service "$APP_DIR"/deploy/tvbot-backup.timer \
   "$APP_DIR"/deploy/tvbot-watchdog.service "$APP_DIR"/deploy/tvbot-watchdog.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable tvbot tvbot-api
systemctl enable --now tvbot-backup.timer tvbot-watchdog.timer
echo "  (alertas opcionales: crea /opt/tvbot/.env con TVBOT_NTFY_URL=https://ntfy.sh/<topico>"
echo "   y/o TVBOT_TG_TOKEN=... TVBOT_TG_CHAT=... para recibir avisos del watchdog)"

echo "[4/5] abriendo puerto 8090 (dashboard)..."
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port=8090/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi
echo "  AVISO: abre tambien el 8090 en la consola Oracle (VCN / Security List), como con el 8080 de kepler"

echo "[5/5] permisos + arranque..."
chown -R "$OWNER":"$OWNER" "$APP_DIR"
systemctl start tvbot tvbot-api
sleep 3
systemctl --no-pager -l status tvbot | head -5
systemctl --no-pager -l status tvbot-api | head -5

IP=$(curl -s -m 5 ifconfig.me || echo "<IP>")
echo ""
echo "=== LISTO ==="
echo "API:    http://${IP}:8090/api/health"
echo "Logs:   journalctl -u tvbot -f"

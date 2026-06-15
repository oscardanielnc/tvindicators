"""Watchdog: avisa si el bot dejó de latir o si saltó el circuit breaker.
El heartbeat es el último equity_snapshot (se escribe cada ciclo, 15m). Si no hay snapshot
reciente, el bot/VM/servicio probablemente está caído y se están perdiendo trades.
Uso: python -m tvbot.watchdog   (programar cada ~10 min por cron/systemd timer en la VM)."""
import sqlite3
from datetime import datetime, timedelta

import config
from . import notify


def run(max_age_min=40):
    c = sqlite3.connect(config.DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    now = datetime.now(config.LIMA_TZ)
    row = c.execute("SELECT ts FROM equity_snapshots ORDER BY ts DESC LIMIT 1").fetchone()
    if not row:
        notify.notify("⚠ tvbot: aún sin snapshots de equity (¿arrancó el bucle?)")
        print("sin snapshots")
        return
    last = datetime.fromisoformat(row["ts"])
    age = (now - last).total_seconds() / 60
    if age > max_age_min:
        notify.notify(f"⚠ tvbot SIN LATIR: último ciclo hace {age:.0f} min (límite {max_age_min}). "
                      f"¿VM o servicio caídos? Revisar systemctl status tvbot.")
        print(f"ALERTA: sin latir hace {age:.0f} min")
    else:
        print(f"OK: último ciclo hace {age:.0f} min")
    cutoff = (now - timedelta(hours=1)).isoformat()
    cb = c.execute("SELECT ts FROM events WHERE category='circuit_breaker' AND ts > ? "
                   "ORDER BY ts DESC LIMIT 1", (cutoff,)).fetchone()
    if cb:
        notify.notify(f"⚠ tvbot: circuit breaker activado ({cb['ts']}) — errores consecutivos.")
    c.close()


if __name__ == "__main__":
    run()

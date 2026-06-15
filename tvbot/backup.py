"""Backup consistente de la DB (la DB ES todo el track record).
Usa la API de backup de SQLite (segura con WAL activo), rota y avisa si falla.
Uso: python -m tvbot.backup   (programar diario por cron/systemd timer en la VM)."""
import sqlite3
from datetime import datetime

import config
from . import db, notify


def run(keep=14):
    bdir = config.DATA_DIR / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(config.LIMA_TZ).strftime("%Y%m%d_%H%M")
    dst = bdir / f"tvbot_{ts}.db"
    try:
        src = sqlite3.connect(config.DB_PATH, timeout=30)
        out = sqlite3.connect(str(dst))
        with out:
            src.backup(out)               # copia consistente aunque el bot esté escribiendo
        out.close(); src.close()
    except Exception as e:
        notify.notify(f"⚠ BACKUP DE DB FALLÓ: {e}")
        db.log_event("error", "backup", f"backup falló: {e}")
        raise
    olds = sorted(bdir.glob("tvbot_*.db"))
    for f in olds[:-keep]:
        try:
            f.unlink()
        except OSError:
            pass
    kb = dst.stat().st_size // 1024
    db.log_event("info", "backup", f"backup ok -> {dst.name} ({kb} KB), conservados {min(len(olds), keep)}")
    print(f"backup OK -> {dst} ({kb} KB)")
    return dst


if __name__ == "__main__":
    run()

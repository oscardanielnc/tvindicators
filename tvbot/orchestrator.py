"""Bucle principal: corre 20s despues de cada cierre de vela 15m; evalua 1h en cada hora.
Resiliente: errores no tumban el proceso; circuit breaker pausa tras errores consecutivos."""
import logging
import time
from datetime import datetime, timezone

import config
from . import db, notify
from .engine import PaperEngine
from .strategies import STRATEGIES

log = logging.getLogger("tvbot")


def next_quarter(now_s):
    period = 15 * 60
    return (int(now_s) // period + 1) * period + config.CYCLE_OFFSET_S


def due_timeframes(ts):
    dt = datetime.fromtimestamp(ts - config.CYCLE_OFFSET_S, tz=timezone.utc)
    due = ["15m"]
    if dt.minute == 0:
        due.append("1h")
    return due


def main():
    engine = PaperEngine()
    db.log_event("info", "system", "tvbot iniciado",
                 {"capital": config.CAPITAL_INICIAL, "leverage": config.LEVERAGE,
                  "margin_pct": config.MARGIN_PCT})
    log.info("tvbot iniciado - paper trading, capital $%.0f", config.CAPITAL_INICIAL)
    notify.notify(f"tvbot iniciado · paper ${config.CAPITAL_INICIAL:.0f} · {len(STRATEGIES)} estrategias")
    errors = 0
    while True:
        target = next_quarter(time.time())
        wait = max(0, target - time.time())
        log.info("durmiendo %.0fs hasta el proximo ciclo", wait)
        time.sleep(wait)
        due = due_timeframes(target)
        try:
            t0 = time.time()
            engine.run_cycle(due)
            errors = 0
            log.info("ciclo ok (%s) en %.1fs", "+".join(due), time.time() - t0)
        except Exception as e:
            errors += 1
            log.exception("ciclo fallo (%d consecutivos)", errors)
            db.log_event("error", "cycle", f"ciclo fallo: {e}", {"consecutivos": errors})
            if errors >= config.CIRCUIT_BREAKER_ERRORS:
                db.log_event("warn", "circuit_breaker",
                             f"pausa {config.CIRCUIT_BREAKER_PAUSE_S}s tras {errors} errores")
                notify.notify(f"⚠ tvbot circuit breaker: {errors} errores consecutivos, "
                              f"pausa {config.CIRCUIT_BREAKER_PAUSE_S}s. Último: {e}")
                log.warning("circuit breaker: pausa %ds", config.CIRCUIT_BREAKER_PAUSE_S)
                time.sleep(config.CIRCUIT_BREAKER_PAUSE_S)
                errors = 0

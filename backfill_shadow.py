"""Rellena `shadow_exits` en los trades YA cerrados (contrafactuales de salida).

Re-descarga las velas del periodo de cada trade y aplica `tvbot/shadow.py` — el mismo código que
usa el motor en vivo, así el histórico y lo nuevo son comparables.

AVISO METODOLÓGICO: lo que rellene este script es IN-SAMPLE. Son los mismos trades que se
miraron para formular la hipótesis de que los stops de 2×ATR devuelven demasiado; si una variante
gana aquí, eso NO es evidencia de que gane mañana. El valor de este backfill es distinto:
  1) valida el simulador (la variante 'base' debe reproducir el retorno real de cada trade), y
  2) da un punto de partida sobre el que comparar los datos OOS que empiecen a llegar hoy.
La decisión sobre stops se toma con los trades posteriores al despliegue, no con estos.

Uso:  python backfill_shadow.py [--dry]
"""
import json
import sqlite3
import sys
from datetime import datetime

import pandas as pd

import config
from tvbot import data, shadow
from tvbot.engine import _TF_S, _view
from tvbot.strategies import BY_ID
from tvbot.strategies_tradfi import BY_ID_TRADFI

BY = {**BY_ID, **BY_ID_TRADFI}
DRY = "--dry" in sys.argv
LIMIT = 1500                       # máximo de velas por petición (cubre ~2 meses en 1h)


def main():
    c = sqlite3.connect(config.DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    trades = [dict(r) for r in c.execute(
        "SELECT * FROM trades WHERE status='closed' AND shadow_exits IS NULL "
        "AND stop_px IS NOT NULL ORDER BY t_entry")]
    print(f"{len(trades)} trades cerrados sin shadow")

    cache = {}
    done = skipped = 0
    fid = []                                   # fidelidad: base(shadow) - real, en bps
    for tr in trades:
        strat = BY.get(tr["strategy_id"])
        if strat is None:
            skipped += 1
            continue
        key = (tr["symbol"], tr["tf"])
        if key not in cache:
            try:
                cache[key] = data.retry(lambda k=key: data.fetch_bars(k[0], k[1], limit=LIMIT))[0]
            except Exception as e:
                print(f"  sin datos {key}: {e}")
                cache[key] = None
        raw_df = cache[key]
        if raw_df is None:
            skipped += 1
            continue
        df = _view(strat, raw_df)
        tf_s = _TF_S[tr["tf"]]
        entry_t = datetime.fromisoformat(tr["t_entry"])
        entry_bar = int(entry_t.timestamp() // tf_s) * tf_s
        starts = ((df.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy()
        if entry_bar < starts[0]:              # el trade es más viejo que la ventana descargada
            skipped += 1
            continue
        i0 = int(starts.searchsorted(entry_bar))
        if i0 >= len(df):
            skipped += 1
            continue
        op, hi, lo, cl = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
        side = 1 if tr["side"] == "long" else -1
        has_timeout = strat.exit_mode in ("atrstop", "meanrev")
        to_bars = (strat.timeout_h or config.TIMEOUT_HOURS) * 3600 // tf_s if has_timeout else None
        flip = strat.exit_array(df) if strat.exit_mode in ("flip", "meanrev") else None
        if strat.exit_mode == "orb":
            et = df.index.tz_convert(data._ET)
            et_mod = (et.hour * 60 + et.minute).to_numpy()
            close_slot = 16 * 60 - tf_s // 60
        else:
            et_mod = close_slot = None
        sh = shadow.compute(side, tr["entry_px"], tr["stop_px"], (op, hi, lo, cl), i0,
                            to_bars, flip, et_mod, close_slot, float(cl[-1]))
        if not sh:
            skipped += 1
            continue
        if "base" in sh and tr["ret_pct_nolev"] is not None:
            fid.append(sh["base"] - tr["ret_pct_nolev"] * 100)
        if not DRY:
            c.execute("UPDATE trades SET shadow_exits=? WHERE id=?", (json.dumps(sh), tr["id"]))
        done += 1
    if not DRY:
        c.commit()
    print(f"rellenados {done} | saltados {skipped} (sin velas en ventana / sin stop)")
    if fid:
        fid.sort()
        big = sum(1 for x in fid if abs(x) > 25)
        print(f"FIDELIDAD del simulador (base - real, bps): mediana {fid[len(fid)//2]:+.1f} "
              f"| p5 {fid[len(fid)//20]:+.1f} p95 {fid[-len(fid)//20]:+.1f} "
              f"| {big}/{len(fid)} trades con desvío >25bps")
        print("  (desvíos esperables: funding excluido del shadow y re-descarga de velas;"
              " si la mediana no está cerca de 0, el simulador NO es fiable)")


if __name__ == "__main__":
    main()

"""Validacion de la replica S/D 1m contra las capturas del stream (14/06/2026).
Confirma que la ENTRADA inferida dispara donde el stream disparo, antes de backtestear.
Uso: python valida_sd.py
"""
import numpy as np
import pandas as pd

import sd_replica as R

pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 60)

# Capturas (hora Lima -> UTC = +5h):
#   BTC SHORT ~07:31 Lima = 12:31 UTC  (ruptura 64,431 -> 64,289)
#   ETH LONG  ~14:15 Lima = 19:15 UTC  (entrada ~1,662, TP zona oferta ~1,666)
FRAMES = [
    ("BTC", -1, "2026-06-14 12:20", "2026-06-14 12:45"),
    ("ETH", +1, "2026-06-14 19:05", "2026-06-14 19:30"),
]


def check_window(df, longs, shorts, tr, t0, t1):
    w = (df.index >= pd.Timestamp(t0, tz="UTC")) & (df.index <= pd.Timestamp(t1, tz="UTC"))
    return pd.DataFrame({
        "close": df["close"].values[w].round(2),
        "trend": tr[w],
        "LONG": longs[w].astype(int),
        "SHORT": shorts[w].astype(int),
    }, index=df.index[w])


def run(trend_len=50, entry_look=10):
    print(f"\n{'='*70}\nPARAMS: trend_len={trend_len}  entry_look={entry_look}\n{'='*70}")
    for coin, want_side, t0, t1 in FRAMES:
        df = R.load(coin)
        longs, shorts, tr = R.entries(df, trend_len, entry_look)
        sub = check_window(df, longs, shorts, tr, t0, t1)
        fired = sub.index[(sub["LONG"] == 1) | (sub["SHORT"] == 1)]
        want = "LONG" if want_side > 0 else "SHORT"
        hit = any((sub.loc[t, want] == 1) for t in fired) if len(fired) else False
        n_all = int(longs.sum() + shorts.sum())
        print(f"\n--- {coin}  (esperado: {want})  [total senales en dataset: {n_all}] ---")
        print(sub.to_string())
        print(f"  >> disparos en ventana: {[str(t)[11:16] for t in fired]}  | calza {want}: "
              f"{'SI' if hit else 'NO'}")


if __name__ == "__main__":
    for tl, el in [(50, 10), (50, 5), (100, 15), (30, 20)]:
        run(tl, el)

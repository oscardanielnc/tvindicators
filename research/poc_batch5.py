"""Batch 5: sistemas de tendencia/momentum NO usados aún (busco sobre todo LONGS).
Motor de continuación (ATR-stop 2× + timeout 48h), sweep 52 monedas, filtros, OOS integrado.

Señales:
  - Ichimoku: cruce Tenkan/Kijun + precio del lado correcto de la nube (sistema de tendencia distinto).
  - KST (Pring): cruce de la KST con su señal (momentum suavizado, baja frecuencia).
  - TSI (True Strength Index): cruce TSI/señal (momentum doble-suavizado).
  - AO (Awesome Oscillator): cruce de cero de SMA(hl2,5)-SMA(hl2,34).

Gate = full(exp>0,PF>=1.4,n>=40,años+ tol1) Y OOS>=2025(exp>0,n>=12). Uso: python poc_batch5.py
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/poc_indicadores_nuevos.py"), encoding="utf-8").read()
exec(src.split("def main(")[0])  # I, DATA, run_f, met, filt_arrays, load_fund, all_coins, FILTER_SETS


def _cross_events(a, b):
    """(a cruza arriba de b, a cruza debajo de b) como eventos booleanos."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    above = a > b
    up = above & ~np.roll(above, 1); dn = (~above) & np.roll(above, 1)
    up[0] = dn[0] = False
    return up, dn


def ichimoku(df):
    h, l, c = df["high"], df["low"], df["close"]
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    spanA = ((tenkan + kijun) / 2).shift(26)
    spanB = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    cloud_top = pd.concat([spanA, spanB], axis=1).max(axis=1).values
    cloud_bot = pd.concat([spanA, spanB], axis=1).min(axis=1).values
    tkup, tkdn = _cross_events(tenkan.values, kijun.values)
    cv = c.values
    longe = tkup & (cv > cloud_top)
    shorte = tkdn & (cv < cloud_bot)
    return longe, shorte


def _roc(c, n):
    return 100 * (c / c.shift(n) - 1)


def kst(df):
    c = df["close"]
    r1 = _roc(c, 10).rolling(10).mean(); r2 = _roc(c, 15).rolling(10).mean()
    r3 = _roc(c, 20).rolling(10).mean(); r4 = _roc(c, 30).rolling(15).mean()
    k = r1 * 1 + r2 * 2 + r3 * 3 + r4 * 4
    sig = k.rolling(9).mean()
    return _cross_events(k.values, sig.values)


def tsi(df, long_=25, short_=13, sig_=13):
    c = df["close"]; pc = c.diff()
    ds = I.pine_ema(I.pine_ema(pc, long_), short_)
    das = I.pine_ema(I.pine_ema(pc.abs(), long_), short_)
    t = 100 * ds / das
    sig = I.pine_ema(t, sig_)
    return _cross_events(t.values, sig.values)


def ao(df):
    hl2 = (df["high"] + df["low"]) / 2
    a = (hl2.rolling(5).mean() - hl2.rolling(34).mean()).values
    return _cross_events(a, np.zeros(len(a)))


SIGNALS = {"ICHI": ichimoku, "KST": kst, "TSI": tsi, "AO": ao}


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return None, None
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def main():
    coins = all_coins()
    print(f"Universo: {len(coins)} monedas · TF 1h · {', '.join(SIGNALS)}", flush=True)
    survivors = []
    for ci, coin in enumerate(coins, 1):
        try:
            df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
        except Exception:
            continue
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        try:
            ft, fr = load_fund(coin)
        except Exception:
            continue
        up, dn, _ = I.st_flips(df); flips = (up, dn)
        for sname, fn in SIGNALS.items():
            longe, shorte = fn(df)
            for side, evt, tag in ((+1, longe, "L"), (-1, shorte, "S")):
                if not np.asarray(evt).any():
                    continue
                fa = filt_arrays(df, side)
                best = None
                for fs in FILTER_SETS:
                    mask = np.ones(len(df), bool)
                    for f in fs:
                        mask &= fa[f]
                    tr = run_f(df, side, "atrstop", None, np.asarray(evt) & mask, flips, "1h", ft, fr)
                    m = met(tr)
                    if not m or m["n"] < 40 or m["exp"] <= 0 or m["pf"] < 1.4 or m["ypos"] < m["ytot"] - 1:
                        continue
                    mi, mo = split_met(tr)
                    if not mo or mo["exp"] <= 0 or mo["n"] < 12 or not mi or mi["exp"] <= 0:
                        continue   # exijo IS>0 tambien (gate mas duro que batch 4)
                    if best is None or mo["exp"] > best[1]["exp"]:
                        best = (fs, mo, m, mi)
                if best:
                    fs, mo, m, mi = best
                    survivors.append((coin, f"{sname}-{tag}", fs, m, mi, mo))
        print(f"  [{ci}/{len(coins)}] {coin}", end="\r", flush=True)

    print(" " * 50)
    print(f"{'='*110}")
    print(f"SUPERVIVIENTES BATCH 5 (full + IS>0 + OOS>0; gate duro)")
    print(f"{'coin':6}{'señal':9}{'filtros':18}{'n':>5}{'WR%':>5}{'exp':>6}{'PF':>6}{'años+':>7}"
          f"{'IS_exp':>8}{'OOS_exp':>9}{'OOS_PF':>8}")
    print(f"{'-'*110}")
    for coin, sg, fs, m, mi, mo in sorted(survivors, key=lambda x: x[5]["exp"], reverse=True):
        print(f"{coin:6}{sg:9}{('+'.join(fs) or 'ninguno'):18}{m['n']:5}{m['wr']:5.0f}{m['exp']:6.0f}"
              f"{m['pf']:6.2f}{m['ypos']:4}/{m['ytot']:<2}{mi['exp']:8.0f}{mo['exp']:9.0f}{mo['pf']:8.2f}")
    bycls = {}
    for s in survivors:
        k = "-".join(s[1].split("-")[:2])
        bycls[k] = bycls.get(k, 0) + 1
    nl = sum(1 for s in survivors if s[1].endswith("-L"))
    print(f"\n{len(survivors)} setups (IS>0 y OOS>0). Longs: {nl}, Shorts: {len(survivors)-nl}. Por clase: {bycls}")


if __name__ == "__main__":
    main()

"""Batch 6: Zero Lag Trend Signals (AlgoAlpha). Réplica Pine-fiel + sweep 52 monedas.

Indicador: ZLEMA = ema(close + (close - close[lag]), length), lag=floor((length-1)/2).
Banda = highest(ATR(length), length*3) * mult. Estado 'trend':
  crossover(close, ZLEMA+banda) -> trend=+1 ; crossunder(close, ZLEMA-banda) -> trend=-1 (persiste).
Dos señales:
  - ZLflip:  trend cruza 0 (cambio de tendencia)  -> long/short.
  - ZLentry: close re-cruza la ZLEMA en la dirección de la tendencia ya establecida (pullback).
Ambas direccionales -> motor de continuación (ATR-stop 2× + timeout 48h).
Gate DURO: full(exp>0,PF>=1.4,n>=40,años+ tol1) Y OOS>=2025(exp>0,n>=12) Y IS<2025 exp>0.
Uso: python poc_batch6.py
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/poc_indicadores_nuevos.py"), encoding="utf-8").read()
exec(src.split("def main(")[0])  # I, DATA, run_f, met, filt_arrays, load_fund, all_coins, FILTER_SETS


def zlsignals(df, length=70, mult=1.2):
    c = df["close"]; lag = (length - 1) // 2
    zlema = I.pine_ema(c + (c - c.shift(lag)), length).values
    tr = pd.concat([df["high"] - df["low"], (df["high"] - c.shift()).abs(),
                    (df["low"] - c.shift()).abs()], axis=1).max(axis=1)
    vol = (I.pine_rma(tr, length).rolling(length * 3).max() * mult).values
    cv = c.values; up = zlema + vol; dn = zlema - vol
    n = len(cv); trend = np.zeros(n); cur = 0
    for i in range(1, n):
        if cv[i] > up[i] and cv[i - 1] <= up[i - 1]:
            cur = 1
        elif cv[i] < dn[i] and cv[i - 1] >= dn[i - 1]:
            cur = -1
        trend[i] = cur
    return zlema, trend


def zl_flip(df, length=70, mult=1.2):
    zlema, trend = zlsignals(df, length, mult); tp = np.roll(trend, 1)
    lo = (trend == 1) & (tp <= 0); sh = (trend == -1) & (tp >= 0)
    lo[0] = sh[0] = False
    return lo, sh


def zl_entry(df, length=70, mult=1.2):
    zlema, trend = zlsignals(df, length, mult); tp = np.roll(trend, 1)
    cv = df["close"].values; above = cv > zlema
    cu = above & ~np.roll(above, 1); cd = (~above) & np.roll(above, 1)
    lo = cu & (trend == 1) & (tp == 1); sh = cd & (trend == -1) & (tp == -1)
    lo[0] = sh[0] = False
    return lo, sh


SIGNALS = {"ZLflip": zl_flip, "ZLentry": zl_entry}


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return None, None
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def main():
    coins = all_coins()
    print(f"Universo: {len(coins)} monedas · TF 1h · Zero Lag Trend Signals ({', '.join(SIGNALS)})", flush=True)
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
                    if not mo or not mi or mo["exp"] <= 0 or mo["n"] < 12 or mi["exp"] <= 0:
                        continue
                    if best is None or mo["exp"] > best[1]["exp"]:
                        best = (fs, mo, m, mi)
                if best:
                    fs, mo, m, mi = best
                    survivors.append((coin, f"{sname}-{tag}", fs, m, mi, mo))
        print(f"  [{ci}/{len(coins)}] {coin}", end="\r", flush=True)

    print(" " * 50)
    print(f"{'='*110}")
    print(f"SUPERVIVIENTES BATCH 6 — Zero Lag (full + IS>0 + OOS>0)")
    print(f"{'coin':6}{'señal':11}{'filtros':18}{'n':>5}{'WR%':>5}{'exp':>6}{'PF':>6}{'años+':>7}"
          f"{'IS_exp':>8}{'OOS_exp':>9}{'OOS_PF':>8}")
    print(f"{'-'*110}")
    for coin, sg, fs, m, mi, mo in sorted(survivors, key=lambda x: x[5]["exp"], reverse=True):
        print(f"{coin:6}{sg:11}{('+'.join(fs) or 'ninguno'):18}{m['n']:5}{m['wr']:5.0f}{m['exp']:6.0f}"
              f"{m['pf']:6.2f}{m['ypos']:4}/{m['ytot']:<2}{mi['exp']:8.0f}{mo['exp']:9.0f}{mo['pf']:8.2f}")
    bycls = {}
    for s in survivors:
        bycls["-".join(s[1].split("-")[:2])] = bycls.get("-".join(s[1].split("-")[:2]), 0) + 1
    nl = sum(1 for s in survivors if s[1].endswith("-L"))
    print(f"\n{len(survivors)} setups (IS>0 y OOS>0). Longs {nl} / Shorts {len(survivors)-nl}. Por clase: {bycls}")


if __name__ == "__main__":
    main()

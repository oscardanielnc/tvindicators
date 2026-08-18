"""Batch 7a: KVO (Klinger Volume Oscillator) + S/R High Volume Boxes (ChartPrime).
Baja convicción — evaluación honesta. Motor de continuación (ATR-stop 2× + timeout 48h),
sweep 52 monedas, gate DURO (full + IS>0 + OOS>0). Uso: python poc_batch7.py
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/poc_indicadores_nuevos.py"), encoding="utf-8").read()
exec(src.split("def main(")[0])  # I, DATA, run_f, met, filt_arrays, load_fund, all_coins, FILTER_SETS


def _cross(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ab = a > b
    up = ab & ~np.roll(ab, 1); dn = (~ab) & np.roll(ab, 1); up[0] = dn[0] = False
    return up, dn


def kvo(df, fast=34, slow=55, trig=13):
    """Klinger Volume Oscillator. (long, short) = cruce KVO/Trigger."""
    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
    xt = pd.Series(np.where(hlc3 > hlc3.shift(1), df["volume"] * 100, -df["volume"] * 100), index=df.index)
    k = I.pine_ema(xt, fast) - I.pine_ema(xt, slow)
    t = I.pine_ema(k, trig)
    return _cross(k.values, t.values)


def _pivots(s, L=20, R=20):
    arr = s.values; n = len(arr); ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    for t in range(L + R, n):
        c = t - R; win = arr[t - L - R:t + 1]
        if arr[c] == win.max():
            ph[t] = arr[c]
        if arr[c] == win.min():
            pl[t] = arr[c]
    return ph, pl


def srbreak(df, lookback=20, vol_len=2, box_w=1.0):
    """S/R High Volume Boxes (ChartPrime). (long, short) = ruptura de S/R confirmada por volumen.
    long = ruptura de resistencia (low cruza arriba res+width); short = ruptura de soporte."""
    c, o, h, l, v = df["close"], df["open"], df["high"], df["low"], df["volume"]
    sv = pd.Series(np.where(c > o, v, np.where(c < o, -v, 0.0)), index=df.index)  # delta vol firmado
    vol_hi = (sv / 2.5).rolling(vol_len).max().values
    vol_lo = (sv / 2.5).rolling(vol_len).min().values
    svv = sv.values
    ph, pl = _pivots(c, lookback, lookback)
    atr = I.atr14(df).values * 0 + (I.pine_rma(pd.concat([h - l, (h - c.shift()).abs(),
          (l - c.shift()).abs()], axis=1).max(axis=1), 200)).values  # atr(200)
    width = atr * box_w
    n = len(c); lo_arr, hi_arr = l.values, h.values
    resL = supL = res1 = sup1 = np.nan
    brk_res = np.zeros(n, bool); brk_sup = np.zeros(n, bool)
    p_low = p_high = np.nan
    for t in range(1, n):
        # actualizar niveles en pivote confirmado con volumen
        if not np.isnan(pl[t]) and svv[t] > vol_hi[t]:
            supL = pl[t]; sup1 = supL - width[t]
        if not np.isnan(ph[t]) and svv[t] < vol_lo[t]:
            resL = ph[t]; res1 = resL + width[t]
        # rupturas (crossover low>res1 ; crossunder high<sup1)
        if not np.isnan(res1) and lo_arr[t] > res1 and lo_arr[t - 1] <= res1:
            brk_res[t] = True
        if not np.isnan(sup1) and hi_arr[t] < sup1 and hi_arr[t - 1] >= sup1:
            brk_sup[t] = True
    return brk_res, brk_sup     # (long, short)


SIGNALS = {"KVO": kvo, "SRB": srbreak}


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return None, None
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def main():
    coins = all_coins()
    print(f"Universo: {len(coins)} monedas · TF 1h · KVO + S/R High Volume Boxes", flush=True)
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
                fa = filt_arrays(df, side); best = None
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
    print(f"{'='*108}\nSUPERVIVIENTES BATCH 7a (KVO + SRB) — full + IS>0 + OOS>0")
    print(f"{'coin':6}{'señal':9}{'filtros':18}{'n':>5}{'WR%':>5}{'exp':>6}{'PF':>6}{'años+':>7}{'IS':>7}{'OOS':>7}{'OOS_PF':>8}")
    print(f"{'-'*108}")
    for coin, sg, fs, m, mi, mo in sorted(survivors, key=lambda x: x[5]["exp"], reverse=True):
        print(f"{coin:6}{sg:9}{('+'.join(fs) or 'ninguno'):18}{m['n']:5}{m['wr']:5.0f}{m['exp']:6.0f}"
              f"{m['pf']:6.2f}{m['ypos']:4}/{m['ytot']:<2}{mi['exp']:7.0f}{mo['exp']:7.0f}{mo['pf']:8.2f}")
    bycls = {}
    for s in survivors:
        bycls["-".join(s[1].split("-")[:2])] = bycls.get("-".join(s[1].split("-")[:2]), 0) + 1
    print(f"\n{len(survivors)} setups (IS>0 y OOS>0). Por clase: {bycls}")


if __name__ == "__main__":
    main()

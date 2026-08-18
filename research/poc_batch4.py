"""Batch 4: dimensión NUEVA = VOLUMEN/flujo (el roster casi no lo usa) + ciclo.
Motor de continuación (ATR-stop 2× + timeout 48h), sweep 52 monedas, filtros, OOS integrado.

Señales:
  - OBV vs EMA(20): On-Balance Volume cruza su media (volumen confirmando tendencia).
  - CMF(20) cruce cero: Chaikin Money Flow (acumulación/distribución).
  - Force Index EMA(13) cruce cero: (Δprecio × volumen) suavizado.
  - STC: Schaff Trend Cycle cruza 25 (long) / 75 (short) — ciclo-momentum.

Gate = full(exp>0,PF>=1.4,n>=40,años+ tol1) Y OOS>=2025(exp>0,n>=12).
Uso: python poc_batch4.py
"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_indicadores_nuevos.py", encoding="utf-8").read()
exec(src.split("def main(")[0])  # I, DATA, run_f, met, filt_arrays, load_fund, all_coins, FILTER_SETS, WARM


def obv_sig(df):
    c, v = df["close"], df["volume"]
    obv = (np.sign(c.diff().fillna(0)) * v).cumsum()
    e = obv.ewm(span=20, adjust=False).mean()
    above = (obv > e).values
    l = above & ~np.roll(above, 1); s = (~above) & np.roll(above, 1)
    l[0] = s[0] = False
    return l, s


def cmf_sig(df, n=20):
    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]
    rng = (h - l).replace(0, np.nan)
    mfv = (((c - l) - (h - c)) / rng).fillna(0) * v
    cmf = (mfv.rolling(n).sum() / v.rolling(n).sum().replace(0, np.nan)).values
    pos = cmf > 0
    lo = pos & ~np.roll(pos, 1); sh = (~pos) & np.roll(pos, 1)
    lo[0] = sh[0] = False
    return lo, sh


def fi_sig(df, n=13):
    c, v = df["close"], df["volume"]
    fi = ((c - c.shift(1)) * v).ewm(span=n, adjust=False).mean().values
    pos = fi > 0
    l = pos & ~np.roll(pos, 1); s = (~pos) & np.roll(pos, 1)
    l[0] = s[0] = False
    return l, s


def _stoch(x, n):
    lo = x.rolling(n).min(); hi = x.rolling(n).max()
    return (100 * (x - lo) / (hi - lo).replace(0, np.nan)).ffill()


def stc_sig(df, fast=23, slow=50, cyc=10):
    c = df["close"]
    macd = c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()
    k = _stoch(macd, cyc); d = k.ewm(span=3, adjust=False).mean()
    kk = _stoch(d, cyc); stc = kk.ewm(span=3, adjust=False).mean().values
    s1 = np.roll(stc, 1)
    up = (stc > 25) & (s1 <= 25); dn = (stc < 75) & (s1 >= 75)
    up[0] = dn[0] = False
    return up, dn


SIGNALS = {"OBV": obv_sig, "CMF": cmf_sig, "FI": fi_sig, "STC": stc_sig}


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return None, None
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def main():
    coins = all_coins()
    print(f"Universo: {len(coins)} monedas · TF 1h · VOLUMEN/flujo + ciclo: {', '.join(SIGNALS)}", flush=True)
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
                    if not mo or mo["exp"] <= 0 or mo["n"] < 12:
                        continue
                    if best is None or mo["exp"] > best[1]["exp"]:
                        best = (fs, mo, m, mi)
                if best:
                    fs, mo, m, mi = best
                    survivors.append((coin, f"{sname}-{tag}", fs, m, mi, mo))
        print(f"  [{ci}/{len(coins)}] {coin}", end="\r", flush=True)

    print(" " * 50)
    print(f"{'='*110}")
    print(f"SUPERVIVIENTES BATCH 4 (full: exp>0/PF>=1.4/n>=40/años+  Y  OOS: exp>0/n>=12)")
    print(f"{'coin':6}{'señal':8}{'filtros':18}{'n':>5}{'WR%':>5}{'exp':>6}{'PF':>6}{'años+':>7}"
          f"{'IS_exp':>8}{'OOS_exp':>9}{'OOS_PF':>8}")
    print(f"{'-'*110}")
    for coin, sg, fs, m, mi, mo in sorted(survivors, key=lambda x: x[5]["exp"], reverse=True):
        print(f"{coin:6}{sg:8}{('+'.join(fs) or 'ninguno'):18}{m['n']:5}{m['wr']:5.0f}{m['exp']:6.0f}"
              f"{m['pf']:6.2f}{m['ypos']:4}/{m['ytot']:<2}{mi['exp']:8.0f}{mo['exp']:9.0f}{mo['pf']:8.2f}")
    bycls = {}
    for s in survivors:
        k = s[1].split("-")[0] + "-" + s[1].split("-")[1]
        bycls[k] = bycls.get(k, 0) + 1
    print(f"\n{len(survivors)} setups full+OOS. Por clase-lado: {bycls}")


if __name__ == "__main__":
    main()

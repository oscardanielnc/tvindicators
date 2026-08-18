"""Batch 3: más indicadores de EDGE GRUESO / baja frecuencia (filosofía del proyecto).
Motor de continuación (ATR-stop 2× + timeout 48h), sweep 52 monedas, filtros de convicción,
OOS integrado. Gate = full(exp>0,PF>=1.4,n>=40,años+ tol1) Y OOS>=2025(exp>0,n>=12).

Señales nuevas:
  - Fisher Transform (turn): giro del Fisher desde extremo (evento de cambio de momentum).
  - KAMA cross: close cruza la Kaufman Adaptive MA (tendencia adaptada a la volatilidad).
  - ADX/DMI: cruce DI+/DI- con ADX>umbral (fuerza de tendencia).
  - VTX-L y SQZ-S: los LADOS que el batch 1 no usó (Vortex en long, Squeeze en short).

Uso: python poc_batch3.py
"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_indicadores_nuevos.py", encoding="utf-8").read()
exec(src.split("def main(")[0])  # I, DATA, MAKER/TAKER/SLIP, WARM, run_f, met, filt_arrays, load_fund, all_coins, FILTER_SETS, squeeze_momentum, vortex, roster_pnl_daily


# ---------- indicadores nuevos batch 3 ----------
def fisher(df, n=9):
    """Fisher Transform (Ehlers). Eventos: giro alcista desde valle / bajista desde pico."""
    hl2 = ((df["high"] + df["low"]) / 2).values
    mn = pd.Series(hl2).rolling(n).min().values
    mx = pd.Series(hl2).rolling(n).max().values
    rng = np.where((mx - mn) == 0, 1e-9, mx - mn)
    v = np.zeros(len(hl2)); fish = np.zeros(len(hl2))
    for i in range(1, len(hl2)):
        if np.isnan(mn[i]):
            continue
        v[i] = 0.66 * ((hl2[i] - mn[i]) / rng[i] - 0.5) + 0.67 * v[i - 1]
        v[i] = min(max(v[i], -0.999), 0.999)
        fish[i] = 0.5 * np.log((1 + v[i]) / (1 - v[i])) + 0.5 * fish[i - 1]
    f1, f2 = np.roll(fish, 1), np.roll(fish, 2)
    longe = (fish > f1) & (f1 < f2) & (f1 < 0)    # valle bajo cero girando arriba
    shorte = (fish < f1) & (f1 > f2) & (f1 > 0)   # pico sobre cero girando abajo
    longe[:2] = shorte[:2] = False
    return longe, shorte


def kama(df, n=10, fast=2, slow=30):
    """Kaufman Adaptive MA. Evento: close cruza la KAMA (slope-adaptado a la volatilidad)."""
    c = df["close"].values
    change = np.abs(c - np.roll(c, n))
    vol = pd.Series(np.abs(c - np.roll(c, 1))).rolling(n).sum().values
    er = np.where(vol == 0, 0, change / np.where(vol == 0, 1e-9, vol))
    sc = (er * (2 / (fast + 1) - 2 / (slow + 1)) + 2 / (slow + 1)) ** 2
    k = np.zeros(len(c)); k[:n] = c[:n]
    for i in range(n, len(c)):
        k[i] = k[i - 1] + sc[i] * (c[i] - k[i - 1])
    above = c > k
    longe = above & ~np.roll(above, 1)
    shorte = (~above) & np.roll(above, 1)
    longe[0] = shorte[0] = False
    return longe, shorte


def adx_dmi(df, n=14, thr=25):
    """ADX/DMI. Evento: cruce DI+/DI- con ADX>umbral (tendencia con fuerza)."""
    h, l, c = df["high"], df["low"], df["close"]
    up = h.diff(); dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = I.pine_rma(tr, n)
    pdi = 100 * I.pine_rma(pd.Series(plus_dm, index=c.index), n) / atr
    mdi = 100 * I.pine_rma(pd.Series(minus_dm, index=c.index), n) / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = I.pine_rma(dx.fillna(0), n).values
    p, m = pdi.values, mdi.values
    pc, mc = np.roll(p, 1), np.roll(m, 1)
    longe = (p > m) & (pc <= mc) & (adx > thr)
    shorte = (m > p) & (mc <= pc) & (adx > thr)
    longe[0] = shorte[0] = False
    return longe, shorte


def vtx_only(df):   # Vortex: solo el lado LONG (el batch 1 usó short)
    up, dn = vortex(df); return up, np.zeros(len(up), bool)


def sqz_only(df):   # Squeeze: solo el lado SHORT (el batch 1 usó long)
    le, se = squeeze_momentum(df); return np.zeros(len(se), bool), se


SIGNALS = {"FISHER": fisher, "KAMA": kama, "ADX": adx_dmi, "VTX-long": vtx_only, "SQZ-short": sqz_only}


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return None, None
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def main():
    coins = all_coins()
    print(f"Universo: {len(coins)} monedas · TF 1h · señales: {', '.join(SIGNALS)}", flush=True)
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
                if not evt.any():
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
    print(f"{'='*108}")
    print(f"SUPERVIVIENTES BATCH 3 (full: exp>0/PF>=1.4/n>=40/años+  Y  OOS: exp>0/n>=12)")
    print(f"{'coin':6}{'señal':11}{'filtros':18}{'n':>5}{'WR%':>5}{'exp':>6}{'PF':>6}{'años+':>7}"
          f"{'IS_exp':>8}{'OOS_exp':>9}{'OOS_PF':>8}")
    print(f"{'-'*108}")
    for coin, sg, fs, m, mi, mo in sorted(survivors, key=lambda x: x[5]["exp"], reverse=True):
        print(f"{coin:6}{sg:11}{('+'.join(fs) or 'ninguno'):18}{m['n']:5}{m['wr']:5.0f}{m['exp']:6.0f}"
              f"{m['pf']:6.2f}{m['ypos']:4}/{m['ytot']:<2}{mi['exp']:8.0f}{mo['exp']:9.0f}{mo['pf']:8.2f}")
    bycls = {}
    for s in survivors:
        bycls[s[1].split("-")[0]] = bycls.get(s[1].split("-")[0], 0) + 1
    print(f"\n{len(survivors)} setups pasan full+OOS. Por clase: {bycls}")


if __name__ == "__main__":
    main()

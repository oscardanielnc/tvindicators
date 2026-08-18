"""POC — Squeeze Momentum [LazyBear] + MACD [ChrisMoody]: solos y COMBINADOS, cripto + tradfi.
Tesis: Squeeze = CUÁNDO (compresión->expansión), MACD = HACIA DÓNDE (momentum). La confluencia
debería brillar más que cada uno solo. Ports fieles al Pine pegado por el usuario.
Salida atrstop 2xATR + timeout 48. Gate: exp>0 & PF>1.15 en total Y OOS. Uso: python poc_sqz_macd.py
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from poc_smc import load_crypto, load_equity, atr14, sim, CRYPTO, EQ, TIMEOUT_BARS
from tvbot import indicators as I

IS_C = pd.Timestamp("2024-09-01", tz="UTC")
IS_E = pd.Timestamp("2024-01-01", tz="UTC")


def rising(x):
    return x & ~np.r_[False, x[:-1]]


def _linreg_end(y, n):
    y = pd.Series(np.asarray(y, float)).reset_index(drop=True)
    t = np.arange(len(y), dtype=float)
    Sy = y.rolling(n).sum(); Spy = (pd.Series(t) * y).rolling(n).sum()
    oldest = t - (n - 1); Sky = Spy - oldest * Sy
    Sk = n*(n-1)/2.0; Skk = (n-1)*n*(2*n-1)/6.0; den = n*Skk - Sk*Sk
    slope = (n*Sky - Sk*Sy)/den; intercept = (Sy - slope*Sk)/n
    return (intercept + slope*(n-1)).values


def squeeze(df, length=20, multKC=1.5, lengthKC=20):
    """LazyBear SQZMOM fiel: BB usa multKC (quirk del código). Devuelve sqzOn, sqzOff, val."""
    c, h, l = df["close"], df["high"], df["low"]
    basis = c.rolling(length).mean(); dev = multKC * c.rolling(length).std(ddof=0)
    upBB, loBB = basis + dev, basis - dev
    pc = c.shift(1); tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    ma = c.rolling(lengthKC).mean(); rangema = tr.rolling(lengthKC).mean()
    upKC, loKC = ma + rangema*multKC, ma - rangema*multKC
    sqzOn = ((loBB > loKC) & (upBB < upKC)).values
    sqzOff = ((loBB < loKC) & (upBB > upKC)).values
    hh = h.rolling(lengthKC).max(); ll = l.rolling(lengthKC).min()
    src = c - ((hh+ll)/2.0 + c.rolling(lengthKC).mean())/2.0
    val = _linreg_end(src, lengthKC)
    return sqzOn, sqzOff, val


def macd_cm(df, fast=12, slow=26, sig=9):
    """ChrisMoody MACD fiel: macd=ema12-ema26, signal=SMA(macd,9), hist=macd-signal + estados."""
    c = df["close"]
    macd = (I.pine_ema(c, fast) - I.pine_ema(c, slow))
    signal = pd.Series(macd).rolling(sig).mean().values
    macd = np.asarray(macd); hist = macd - signal
    hp = np.r_[np.nan, hist[:-1]]
    histA_up = (hist > hp) & (hist > 0)         # acelera al alza sobre cero (bull fuerte)
    histB_dn = (hist < hp) & (hist <= 0)        # acelera a la baja bajo cero (bear fuerte)
    above = macd >= signal
    xL = above & ~np.r_[False, above[:-1]]       # cruce alcista macd/signal
    xS = (~above) & np.r_[False, above[:-1]]     # cruce bajista
    return dict(macd=macd, signal=signal, hist=hist, histA_up=histA_up, histB_dn=histB_dn,
                above=above, xL=xL, xS=xS)


def build_signals(df):
    sqzOn, sqzOff, val = squeeze(df)
    M = macd_cm(df)
    release = np.r_[False, (sqzOn[:-1] & ~sqzOn[1:])]            # squeeze terminó ESTA barra
    valpos = val > 0; valneg = val < 0
    above = M["above"]
    # recién liberado (<=6 barras)
    rel_recent = pd.Series(release).rolling(6, min_periods=1).max().astype(bool).values

    S = {}
    # --- baselines ---
    S["SQZ_rel"]      = (rising(release & valpos), rising(release & valneg))
    S["MACD_cross"]   = (M["xL"], M["xS"])
    S["MACD_histAccel"] = (rising(M["histA_up"]), rising(M["histB_dn"]))
    # --- combinaciones ---
    S["C1_rel+macdDir"]  = (rising(release & valpos & above), rising(release & valneg & ~above))
    S["C2_rel+histAccel"] = (rising(release & M["histA_up"]), rising(release & M["histB_dn"]))
    S["C3_cross+inSqz"]  = (M["xL"] & sqzOn, M["xS"] & sqzOn)
    S["C4_cross+recentRel"] = (M["xL"] & rel_recent & valpos, M["xS"] & rel_recent & valneg)
    S["C5_macdAbove+rel"] = (rising(release & above), rising(release & ~above))
    return S


def stats(T, is_end):
    if len(T) < 15:
        return None
    T = T.copy(); T["t"] = pd.to_datetime(T["t"], utc=True)
    net = T["net"].values; pf = net[net > 0].sum()/max(-net[net < 0].sum(), 1e-9)
    oos = T[T["t"] >= is_end]["net"].values
    return dict(n=len(T), exp=net.mean()*1e4, pf=pf,
                oexp=oos.mean()*1e4 if len(oos) >= 5 else np.nan,
                opf=(oos[oos > 0].sum()/max(-oos[oos < 0].sum(), 1e-9)) if len(oos) >= 5 else np.nan)


def evaluate(name, loader, syms, is_end):
    print(f"\n{'#'*88}\n# {name}\n{'#'*88}")
    agg = {}
    for cs in syms:
        try:
            df = loader(cs)
        except Exception:
            continue
        if len(df) < 600:
            continue
        atr = atr14(df); S = build_signals(df)
        for nm, (bull, bear) in S.items():
            ent = np.asarray(bull) | np.asarray(bear)
            side = np.where(np.asarray(bull), 1, np.where(np.asarray(bear), -1, 0)).astype(np.int8)
            agg.setdefault(nm, []).append(sim(df, ent, side, atr))
    print(f"  {'señal':20} {'n':>6} {'exp':>8} {'PF':>6}   {'OOS exp':>8} {'OOS PF':>6}")
    for nm, lst in agg.items():
        s = stats(pd.concat(lst, ignore_index=True), is_end)
        if s is None:
            print(f"  {nm:20} <15"); continue
        star = "★" if (s["exp"] > 0 and s["pf"] > 1.15 and not np.isnan(s["oexp"]) and s["oexp"] > 0 and s["opf"] > 1.1) else " "
        print(f" {star}{nm:20} {s['n']:>6} {s['exp']:>+7.0f}bp {s['pf']:>6.2f}   {s['oexp']:>+7.0f}bp {s['opf']:>6.2f}")


def main():
    print("SQZ[LazyBear] + MACD[ChrisMoody] · solos y combinados · SL2xATR+to48 · ★=exp>0&PF>1.15 total Y OOS")
    evaluate("CRIPTO 1h", load_crypto, CRYPTO, IS_C)
    evaluate("EQUITIES 1h", load_equity, EQ, IS_E)


if __name__ == "__main__":
    main()

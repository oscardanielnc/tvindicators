"""Promoción S/R[LuxAlgo]+Supertrend (variante ST_flip+SRrec) a tradfi.
Paso 1: verifica que los tickers existen como perp Binance (para señal viva).
Paso 2: PnL diario por ticker + correlación vs el roster tradfi existente (portfolio_multi) -> diversifica?
Imprime el roster S/R+ST elegido para cablear. Uso: python promote_sr_st.py
"""
from __future__ import annotations
import sys, os
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tradfi"))
from poc_smc import load_equity, atr14, sim
import poc_sr_supertrend as K

COMBO = "ST_flip+SRrec"
CANDS = ["NVDA", "TSLA", "AMD", "MU", "AAPL"]
IS_END = pd.Timestamp("2024-01-01")


def check_perps():
    try:
        import ccxt
        ex = ccxt.binanceusdm({"enableRateLimit": True}); ex.load_markets()
        out = {}
        for c in CANDS:
            out[c] = f"{c}/USDT:USDT" in ex.markets
        return out
    except Exception as e:
        print(f"  (no se pudo verificar perps: {str(e)[:60]})")
        return {c: None for c in CANDS}


def srst_daily(cs):
    df = load_equity(cs); atr = atr14(df)
    bull, bear = K.signals(df)[COMBO]
    ent = np.asarray(bull) | np.asarray(bear)
    side = np.where(np.asarray(bull), 1, np.where(np.asarray(bear), -1, 0)).astype(np.int8)
    t = sim(df, ent, side, atr)
    if len(t) < 10:
        return None, None
    s = t.set_index("t")["net"].sort_index()
    s.index = pd.to_datetime(s.index, utc=True).tz_localize(None).normalize()
    return t, s.groupby(s.index).sum()


def main():
    print(f"PROMOCIÓN S/R+Supertrend ({COMBO}) a tradfi\n")
    perps = check_perps()
    print("[1] ¿Existen como perp Binance?  " + " · ".join(f"{c}:{'sí' if v else ('no' if v is False else '?')}" for c, v in perps.items()))

    print("\n[2] PnL por ticker + gate (exp>0, PF>=1.2, n>=30):")
    series = {}; chosen = []; trades = {}
    for cs in CANDS:
        t, s = srst_daily(cs)
        if t is None:
            print(f"  {cs}: <10 trades"); continue
        net = t["net"].values; pf = net[net > 0].sum()/max(-net[net < 0].sum(), 1e-9)
        oos = t[pd.to_datetime(t["t"], utc=True) >= IS_END.tz_localize("UTC")]["net"]
        ok = (net.mean() > 0 and pf >= 1.2 and len(t) >= 30)
        print(f"  {'★' if ok else ' '}{cs:5} n={len(t):4} exp={net.mean()*1e4:+5.0f}bp PF={pf:.2f} "
              f"OOSexp={oos.mean()*1e4 if len(oos) else 0:+5.0f}bp")
        if ok and perps.get(cs):
            chosen.append(cs); series[cs] = s; trades[cs] = t

    # correlación vs roster tradfi existente
    print("\n[3] Correlación de PnL diario vs roster tradfi existente (portfolio_multi):")
    try:
        import portfolio_multi as PM
        roster = {k: f() for k, f in PM.ROSTER.items()}
        for k, s in roster.items():
            s.index = pd.to_datetime(s.index).tz_localize(None).normalize() if getattr(s.index, "tz", None) else pd.to_datetime(s.index).normalize()
        R = pd.concat(roster, axis=1).fillna(0.0).sum(axis=1)
        for cs in chosen:
            al = pd.concat([series[cs].rename("x"), R.rename("R")], axis=1).fillna(0.0)
            print(f"  {cs:5} corr vs roster tradfi: {al['x'].corr(al['R']):+.2f}")
    except Exception as e:
        print(f"  (no se pudo correlacionar vs roster: {str(e)[:80]})")

    # correlación entre los elegidos
    if len(chosen) >= 2:
        M = pd.concat({c: series[c] for c in chosen}, axis=1).fillna(0.0)
        cc = M.corr(); off = cc.values[np.triu_indices(len(chosen), 1)]
        print(f"\n  correlación media entre los elegidos: {np.nanmean(off):+.2f}")

    print(f"\nROSTER S/R+ST sugerido para cablear: {chosen}")
    print("Refs (exp bp, PF):")
    for cs in chosen:
        net = trades[cs]["net"].values
        print(f"  {cs}: ({net.mean()*1e4:+.0f}, {net[net>0].sum()/max(-net[net<0].sum(),1e-9):.2f})")


if __name__ == "__main__":
    main()

"""Validación a fondo de sBOS (SMC Swing BOS) LONG-only en equity, para promoción a tradfi.
Costos equity reales (5+4bp). Anti-beta POR TICKER (long vs random-long mismo horizonte) -> promover
solo los que tengan alpha real (no beta de momentum). OOS por ticker. Uso: python validate_sbos_equity_long.py
"""
from __future__ import annotations
import sys, math
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import smc
from poc_smc import load_equity, atr14, EQ

TAKER_E, SLIP_E = 0.0005, 0.0004
TIMEOUT = 48; H = 48
IS_END = pd.Timestamp("2024-01-01", tz="UTC")


def sbos_long_trades(df, atr):
    bull = smc.compute(df)["sbos_bull"]
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    n = len(df); rows = []; i = 5
    while i < n - 1:
        if not bull[i]:
            i += 1; continue
        e = i + 1; epx = o[e]; stop = epx - 2 * atr[i]; exit_px = None
        for j in range(e, min(e + TIMEOUT, n)):
            if l[j] <= stop:
                exit_px = min(o[j], stop) * (1 - SLIP_E); co = TAKER_E + SLIP_E; break
        if exit_px is None:
            j = min(e + TIMEOUT, n - 1); exit_px = c[j]; co = TAKER_E
        rows.append((df.index[e], exit_px / epx - 1 - TAKER_E - co)); i = j + 1
    return pd.DataFrame(rows, columns=["t", "net"])


def random_long(df, k, reps=20):
    o, c = df["open"].values, df["close"].values; n = len(df)
    if n < H + 10 or k < 1:
        return np.nan
    return np.mean([(c[(idx := np.random.RandomState(r).randint(5, n-H-1, k))+H]/o[idx+1]-1-2*TAKER_E).mean()
                    for r in range(reps)])


def main():
    print(f"VALIDACIÓN sBOS LONG-only equity · costos {TAKER_E*1e4:.0f}+{SLIP_E*1e4:.0f}bp · SL2xATR+to{TIMEOUT} · "
          f"anti-beta vs random-long H={H} · OOS>={IS_END.date()}")
    print(f"  gate promoción: alpha>+5bp & exp>0 & PF>=1.2 & n>=30\n")
    keep = []
    for cs in EQ:
        try:
            df = load_equity(cs)
        except Exception:
            continue
        if len(df) < 600:
            continue
        atr = atr14(df); t = sbos_long_trades(df, atr)
        if len(t) < 15:
            print(f"  {cs:5} n={len(t)} <15"); continue
        net = t["net"].values; pf = net[net > 0].sum()/max(-net[net < 0].sum(), 1e-9)
        exp = net.mean()*1e4
        rb = random_long(df, len(t))*1e4
        oos = t[pd.to_datetime(t["t"], utc=True) >= IS_END]["net"]
        ok = (exp - rb > 5 and exp > 0 and pf >= 1.2 and len(t) >= 30)
        print(f"  {'★' if ok else ' '}{cs:5} n={len(t):4} exp={exp:+5.0f}bp PF={pf:.2f} randomLong={rb:+.0f}bp "
              f"alpha={exp-rb:+5.0f}bp OOSexp={oos.mean()*1e4 if len(oos) else 0:+5.0f}bp")
        if ok:
            keep.append((cs, round(exp), round(pf, 2)))
    print(f"\nPROMOVER sBOS-L (ticker, exp_bp, PF): {keep}")


if __name__ == "__main__":
    main()

"""Validación PROFUNDA de UNH 30m ADX (el único candidato sobreviviente): robustez antes de decidir.
  1) Walk-forward: varios puntos de corte IS/OOS -> ¿OOS consistentemente positivo?
  2) Año a año (todo el histórico).
  3) Sensibilidad de parámetros ADX (n, thr) -> ¿edge robusto o config con suerte?
  4) PSR(0) del OOS + chequeo del lado SHORT.
Uso: python deep_unh.py"""
import sys
import os
import math
from statistics import NormalDist
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import validate_indicators as V
from indicator_probe import load_tf
from tvbot import indicators as I

N01 = NormalDist()
df = load_tf("UNH", "30m")
st = I.st_flips(df)[2]


def metr(rets, years):
    r = np.asarray(rets, float)
    if len(r) < 8:
        return None
    sd = r.std(ddof=1); tpy = len(r) / years
    g = r[r > 0].sum(); l = -r[r < 0].sum()
    return dict(n=len(r), wr=(r > 0).mean(), exp=r.mean(), pf=(g / l if l > 0 else 99),
                sharpe=(r.mean() / sd * math.sqrt(tpy) if sd > 0 else 0))


def split(le, side, is_end):
    tr = V.backtest_dated(df, le, side, st)
    isr = [(d, n) for d, n in tr if d.date() < is_end]
    oosr = [(d, n) for d, n in tr if d.date() >= is_end]
    yr = lambda x: max((x[-1][0] - x[0][0]).days / 365.25, 0.5) if x else 1
    return (metr([n for _, n in isr], yr(isr)) if isr else None,
            metr([n for _, n in oosr], yr(oosr)) if oosr else None, tr)


def main():
    le = np.asarray(I.adx_dmi(df, 14, 25)[0])     # config default (la que sobrevivió)

    print("=" * 78 + "\nUNH 30m ADX — validación profunda\n" + "=" * 78)
    print(f"datos: {df.index[0].date()} -> {df.index[-1].date()}\n")

    print("[1] WALK-FORWARD (varios cortes IS/OOS) — ¿OOS robusto?")
    for ie in ("2024-07-01", "2025-01-01", "2025-07-01"):
        mi, mo, _ = split(le, 1, pd.Timestamp(ie).date())
        if mi and mo:
            print(f"  corte {ie}: IS Sharpe {mi['sharpe']:+.2f}/PF {mi['pf']:.2f} · "
                  f"OOS Sharpe {mo['sharpe']:+.2f}/PF {mo['pf']:.2f}/exp {mo['exp']*1e4:+.0f}bp/n {mo['n']}")

    print("\n[2] AÑO A AÑO (todos los trades)")
    tr = V.backtest_dated(df, le, 1, st)
    A = pd.DataFrame(tr, columns=["dt", "ret"]); A["y"] = pd.to_datetime(A["dt"]).dt.year
    for y, g in A.groupby("y"):
        r = g["ret"]; pf = r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)
        print(f"  {y}: n={len(r):3} · exp {r.mean()*1e4:+5.0f}bp · PF {pf:.2f} · cum {((1+r).prod()-1)*100:+.0f}%")

    print("\n[3] SENSIBILIDAD ADX (n, thr) — OOS>=2025 (¿robusto o suerte de 1 config?)")
    pos = 0; tot = 0
    for n in (10, 14, 20):
        row = []
        for thr in (20, 25, 30):
            le2 = np.asarray(I.adx_dmi(df, n, thr)[0])
            _, mo, _ = split(le2, 1, pd.Timestamp("2025-01-01").date())
            tot += 1
            if mo:
                pos += 1 if mo["exp"] > 0 else 0
                row.append(f"thr{thr}:Sh{mo['sharpe']:+.2f}/exp{mo['exp']*1e4:+.0f}")
        print(f"  ADX n={n}: " + " · ".join(row))
    print(f"  -> {pos}/{tot} configs con exp OOS>0 ({'robusto' if pos>=tot*0.7 else 'frágil'})")

    print("\n[4] PSR(0) del OOS + lado SHORT")
    _, mo, _ = split(le, 1, pd.Timestamp("2025-01-01").date())
    oos = [n for d, n in V.backtest_dated(df, le, 1, st) if d.date() >= pd.Timestamp("2025-01-01").date()]
    o = np.asarray(oos, float)
    if len(o) > 8 and o.std() > 0:
        sr = o.mean() / o.std(ddof=1); z = (o - o.mean()) / o.std(ddof=1)
        psr = N01.cdf(sr * math.sqrt(len(o) - 1) / math.sqrt(max(1e-9, 1 - float((z**3).mean()) * sr + ((float((z**4).mean()) - 1) / 4) * sr**2)))
        print(f"  PSR(0) P(Sharpe OOS>0): {psr*100:.0f}%  (n={len(o)})")
    se = np.asarray(I.adx_dmi(df, 14, 25)[1])
    _, mos, _ = split(se, -1, pd.Timestamp("2025-01-01").date())
    print(f"  SHORT OOS: {'exp '+format(mos['exp']*1e4,'+.0f')+'bp PF '+format(mos['pf'],'.2f') if mos else 'pocos'}  (esperado: pierde)")


if __name__ == "__main__":
    main()

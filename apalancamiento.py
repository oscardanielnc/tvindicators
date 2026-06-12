# Apalancamiento por anclaje de maxDD (metodo kepler: biseccion) sobre el portafolio de 9
import io, sys
import numpy as np
import pandas as pd

buf = io.StringIO()
old = sys.stdout; sys.stdout = buf
exec(open(r"C:\Users\LENOVO\tvindicators\portafolio.py", encoding="utf-8").read())
sys.stdout = old
# disponibles: D (retornos diarios por estrategia), w (pesos), port (retorno diario portafolio), stats

def maxdd_lev(L):
    eq = (1 + L * port).cumprod()
    return ((eq / eq.cummax()) - 1).min()

def lev_for_dd(target):
    lo, hi = 0.5, 20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if maxdd_lev(mid) < -target: hi = mid
        else: lo = mid
    return (lo + hi) / 2

CAP = 1000.0
print("=== APALANCAMIENTO ANCLADO A MAXDD (biseccion, metodo kepler) ===")
for target, label in [(0.30, "OBJETIVO PEDIDO -30%"), (0.20, "conservador -20%"), (0.15, "muy conservador -15%")]:
    L = lev_for_dd(target)
    eqL = (1 + L * port).cumprod()
    mddL = maxdd_lev(L)
    yrs = (port.index[-1] - port.index[0]).days / 365
    cagrL = eqL.iloc[-1] ** (1 / yrs) - 1
    mL = eqL.resample("ME").last().pct_change().dropna()
    ymL = (1 + L * port).groupby(port.index.year).prod() - 1
    print(f"\n--- {label}: leverage = {L:.2f}x ---")
    print(f"  CAGR: {cagrL*100:+.1f}%  maxDD: {mddL*100:.1f}%  media mensual: {mL.mean()*100:+.2f}% (${mL.mean()*CAP:+.1f} sobre $1000)")
    print(f"  Peor mes: {mL.min()*100:+.1f}%  Mejor: {mL.max()*100:+.1f}%  Meses+: {(mL>0).mean()*100:.0f}%")
    print(f"  Por anno: " + "  ".join(f"{y}: {v*100:+.0f}%" for y, v in ymL.items()))
    print(f"  $1000 -> ${eqL.iloc[-1]*CAP:,.0f} en 33 meses")

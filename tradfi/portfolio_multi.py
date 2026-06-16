"""Cartera MULTI-ESTRATEGIA tradfi: combina los mejores candidatos validados (holdout+anti-beta)
con pesos vol-parity (1/σ, fijados en IS). Mide Sharpe IS/OOS combinado + matriz de correlación
(la diversificación es el payoff: distinto mecanismo/ticker/TF => Sharpe sube por √N, como roster cripto).

Roster inicial (todos LONG, OOS Sharpe>0 y ganan al beta):
  TSLA-ORB (ruptura apertura) · NVDA-Supertrend-30m · NVDA-AO-30m · NVDA-Squeeze-15m · TSLA-ADX-15m
Uso: python portfolio_multi.py
"""
import os
import sys
import math
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sweep_orb as S
from improve_orb_tsla import detect_long, simulate, IS_END
from indicator_probe import load_tf, signals
from validate_indicators import backtest_dated
from tvbot import indicators as I

ANN = math.sqrt(252)


def orb_daily(ticker):
    df = S.load(ticker)
    trades = [d for _, g in df.groupby(df.index.date) if (d := detect_long(g, 15)) is not None]
    is_or = [d["or_pct"] for d in trades if d["date"] < IS_END]
    thr = np.quantile(is_or, 0.70)
    rows = [(pd.Timestamp(d["date"]), simulate(d, 1.0)[0]) for d in trades if d["or_pct"] >= thr]
    s = pd.Series(dict(rows)).sort_index()
    return s


def ind_daily(ticker, tf, ind):
    df = load_tf(ticker, tf); st = I.st_flips(df)[2]
    le, _ = signals(ind, df)
    tr = backtest_dated(df, le, 1, st)
    s = pd.Series([n for _, n in tr], index=[pd.Timestamp(d) for d, _ in tr])
    s = s.groupby(s.index.normalize()).sum()                 # varios trades/día -> PnL diario
    s.index = s.index.tz_localize(None) if s.index.tz is not None else s.index
    return s


ROSTER = {
    "TSLA-ORB":        lambda: orb_daily("TSLA"),
    "NVDA-ST-30m":     lambda: ind_daily("NVDA", "30m", "Supertrend"),
    "NVDA-AO-30m":     lambda: ind_daily("NVDA", "30m", "AO"),
    "NVDA-SQZ-15m":    lambda: ind_daily("NVDA", "15m", "Squeeze"),
    "TSLA-ADX-15m":    lambda: ind_daily("TSLA", "15m", "ADX"),
}


def sharpe(p):
    return p.mean() / p.std(ddof=1) * ANN if p.std(ddof=1) > 0 else 0


def seg(M, is_seg):
    mask = M.index < pd.Timestamp(IS_END)
    return M[mask] if is_seg else M[~mask]


def main():
    print("=" * 88)
    print("CARTERA MULTI-ESTRATEGIA TRADFI — vol-parity (1/σ, pesos fijados en IS)")
    print("=" * 88)
    series = {k: f() for k, f in ROSTER.items()}
    for k, s in series.items():
        n = len(s); yrs = max((s.index[-1] - s.index[0]).days / 365.25, 0.5)
        print(f"  {k:14} {n:5} trades · {n/yrs:4.0f}/año · {s.index[0].date()}->{s.index[-1].date()}")

    M = pd.concat(series, axis=1).sort_index().fillna(0.0)    # días sin trade = 0
    is_M, oos_M = seg(M, True), seg(M, False)

    # vol-parity con σ de IS (sin lookahead)
    sig = is_M.std(ddof=1).replace(0, np.nan)
    w = (1 / sig); w = (w / w.sum())
    print(f"\nPesos vol-parity (IS): " + " · ".join(f"{k} {v*100:.0f}%" for k, v in w.items()))

    port = (M * w).sum(axis=1)
    is_p, oos_p = port[M.index < pd.Timestamp(IS_END)], port[M.index >= pd.Timestamp(IS_END)]

    def block(name, dfp):
        eq = (1 + dfp).cumprod(); dd = (eq / eq.cummax() - 1).min()
        print(f"  {name:18} Sharpe {sharpe(dfp):+.2f} · ret/día {dfp.mean()*1e4:+.1f}bp · "
              f"días+ {(dfp>0).mean()*100:.0f}% · maxDD {dd*100:.1f}% · cum {(eq.iloc[-1]-1)*100:+.0f}%")

    print(f"\n[CARTERA combinada]")
    block("IS  (2018-2023)", is_p)
    block("OOS (2024-2026)", oos_p)

    # comparación: cartera vs mejor estrategia sola (en OOS)
    solo = {k: sharpe(oos_M[k][oos_M[k] != 0]) for k in ROSTER}   # sharpe por-trade-días
    best_solo = max(solo, key=solo.get)
    print(f"\n  Sharpe OOS cartera {sharpe(oos_p):+.2f}  vs mejor sola ({best_solo}) {solo[best_solo]:+.2f}")
    print(f"  -> {'la cartera MEJORA por diversificación ★' if sharpe(oos_p) > solo[best_solo] else 'sin ganancia clara'}")

    # correlación OOS (clave: cuanto más baja, más sube el Sharpe combinado)
    print(f"\n[Correlación OOS de PnL diario] (baja = diversifica)")
    corr = oos_M.corr()
    print("  " + "      ".join(f"{k[:9]:>9}" for k in ROSTER))
    for k in ROSTER:
        print(f"  {k[:12]:12} " + " ".join(f"{corr.loc[k, j]:+.2f}     " for j in ROSTER))
    off = corr.values[np.triu_indices(len(ROSTER), 1)]
    print(f"  correlación media entre pares: {np.nanmean(off):+.2f}")

    # frecuencia y por año
    tot_tr = sum((series[k] != 0).sum() for k in ROSTER)
    yrs = (M.index[-1] - M.index[0]).days / 365.25
    print(f"\n  Trades/año TOTAL cartera: ~{tot_tr/yrs:.0f} (suma de las 5) · vs ~38 de TSLA-ORB sola")
    by = oos_p.groupby(oos_p.index.year).apply(lambda g: (1 + g).prod() - 1)
    print(f"  Cartera OOS por año: " + " · ".join(f"{y}:{v*100:+.0f}%" for y, v in by.items()))

    print("\n" + "=" * 88)
    print("Nota: Sharpe en convención DIARIA (√252, serie con ceros) = Sharpe de cartera honesto (estilo fondo).")
    print("Para añadir un candidato: valídalo con validate_indicators/validate_orb y agrégalo a ROSTER.")


if __name__ == "__main__":
    main()

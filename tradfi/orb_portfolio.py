"""Cartera ORB long-only multi-ticker. Empieza con TSLA (el edge validado) y se le suman tickers.
Cada ticker usa la config keeper: OR=15min, solo-long, filtro or_pct>=p70 (umbral fijado SOLO en IS),
stop OR-low, salida cierre. Combina por igual-riesgo por día. Reporta IS/OOS por ticker y de la cartera,
para decidir QUÉ tickers merecen entrar (los que aportan Sharpe OOS / diversifican, no solo beta).

Añadir tickers: edita TICKERS. Validar antes con validate_orb_tsla.py el candidato.
Uso: python orb_portfolio.py [T1 T2 ...]   (def: las 6 disponibles)
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

TICKERS = sys.argv[1:] if len(sys.argv) > 1 else ["TSLA", "NVDA", "AMD", "AAPL", "MU", "LITE"]
N_MIN = 15
IS_QUANTILE = 0.70           # umbral de filtro de volatilidad, fijado en IS por ticker


def ticker_series(t):
    """Serie diaria (date->net) del ORB long-only con filtro vol fijado en IS. None si pocos trades."""
    df = S.load(t)
    trades = [d for _, g in df.groupby(df.index.date)
              if (d := detect_long(g, N_MIN)) is not None]
    if len(trades) < 50:
        return None
    is_or = [d["or_pct"] for d in trades if d["date"] < IS_END]
    if len(is_or) < 20:
        return None
    thr = np.quantile(is_or, IS_QUANTILE)
    rows = [(d["date"], simulate(d, stop_frac=1.0)[0]) for d in trades if d["or_pct"] >= thr]
    s = pd.Series({pd.Timestamp(dt): n for dt, n in rows}).sort_index()
    return s


def m(net, years):
    net = np.asarray(net, float)
    if len(net) < 10:
        return None
    sd = net.std(ddof=1); wr = (net > 0).mean()
    g = net[net > 0].sum(); l = -net[net < 0].sum()
    tpy = len(net) / years
    return dict(n=len(net), tpy=tpy, wr=wr, exp=net.mean(), pf=(g / l if l > 0 else np.inf),
                sharpe=(net.mean() / sd * math.sqrt(tpy) if sd > 0 else 0), cum=(1 + pd.Series(net)).prod() - 1)


def seg_years(s):
    return max((s.index[-1] - s.index[0]).days / 365.25, 0.5)


def show(tag, mm):
    if mm is None:
        print(f"  {tag:26} <10 trades"); return
    print(f"  {tag:26} n={mm['n']:5} t/año={mm['tpy']:4.0f} WR={mm['wr']*100:3.0f}% exp={mm['exp']*1e4:+5.0f}bp "
          f"PF={mm['pf']:.2f} Sharpe={mm['sharpe']:+.2f} cum={mm['cum']*100:+.0f}%")


def main():
    print("=" * 92)
    print("CARTERA ORB LONG-ONLY MULTI-TICKER — OR=15min, filtro vol p70(IS), stop OR-low, salida cierre")
    print("=" * 92)
    series = {}
    print("\n[POR TICKER] standalone (IS<2024 / OOS>=2024):")
    for t in TICKERS:
        s = ticker_series(t)
        if s is None:
            print(f"  {t}: insuficiente"); continue
        series[t] = s
        is_s = s[s.index.normalize().map(lambda d: d.date() < IS_END)]
        oos_s = s[s.index.normalize().map(lambda d: d.date() >= IS_END)]
        print(f"  --- {t} ---")
        show(f"{t} IS", m(is_s.values, seg_years(is_s)) if len(is_s) else None)
        show(f"{t} OOS", m(oos_s.values, seg_years(oos_s)) if len(oos_s) else None)

    if not series:
        print("\nSin series. Fin."); return

    # --- cartera: igual-riesgo por día (media de los tickers que operan ese día) ---
    M = pd.DataFrame(series)
    port = M.mean(axis=1)            # cada día: promedio de los tickers con trade (NaN ignorado)
    port = port.dropna()
    is_p = port[port.index.map(lambda d: d.date() < IS_END)]
    oos_p = port[port.index.map(lambda d: d.date() >= IS_END)]

    print("\n[CARTERA] igual-riesgo por día (combina los tickers que operan cada día):")
    show("CARTERA IS", m(is_p.values, seg_years(is_p)))
    show("CARTERA OOS", m(oos_p.values, seg_years(oos_p)))

    # diversificación: Sharpe cartera OOS vs media de Sharpes standalone OOS
    oos_sh = []
    for t, s in series.items():
        o = s[s.index.map(lambda d: d.date() >= IS_END)]
        mm = m(o.values, seg_years(o)) if len(o) else None
        if mm:
            oos_sh.append(mm["sharpe"])
    if oos_sh:
        mc = m(oos_p.values, seg_years(oos_p))
        print(f"\n  Sharpe OOS cartera {mc['sharpe']:+.2f} vs media standalone {np.mean(oos_sh):+.2f} "
              f"-> {'diversifica ★' if mc['sharpe'] > np.mean(oos_sh) + 0.1 else 'sin ganancia de diversificación'}")
        print(f"  Trades/año cartera: {mc['tpy']:.0f} (vs ~30 de TSLA sola) · días operados OOS: {len(oos_p)}")
        by = oos_p.groupby(oos_p.index.year).apply(lambda g: (1 + g).prod() - 1)
        print(f"  Cartera OOS por año: " + " · ".join(f"{y}:{v*100:+.0f}%" for y, v in by.items()))

    print("\n" + "=" * 92)
    print("Decisión de roster: un ticker entra si su OOS standalone es positivo Y/O mejora el Sharpe de")
    print("cartera (diversifica). Igual que el roster cripto: por contribución, no por nombre. TSLA es el ancla.")


if __name__ == "__main__":
    main()

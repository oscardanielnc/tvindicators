"""Auditoría de robustez (2ª revisión) — ¿es real el Sharpe 4.07 o un artefacto?
Mide los modos típicos de inflar el Sharpe de backtest:
  1) Significancia estadística por estrategia (t-stat del expectancy dado n).
  2) Dependencia de régimen: Sharpe por año y excluyendo 2024 (el año fuerte).
  3) Estrés de correlación: corr media entre estrategias en días normales vs días malos del portafolio.
  4) Cola: peor mes, peor trimestre, maxDD, CVaR 5%.
  5) Sesgo de selección: cuántas estrategias serían significativas tras corregir por nº de pruebas.
Uso: python audit_robustez.py
"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\gen_summary.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # tr_for, STRAT, ...

from tvbot import strategies as STRAT


def main():
    daily = {}; tstats = []
    for s in STRAT.STRATEGIES:
        tr = tr_for(s.sid)
        if tr is None or len(tr) < 5:
            continue
        r = tr["ret"].values
        t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if r.std() > 0 else 0
        tstats.append((s.sid, len(r), r.mean() * 1e4, t))
        daily[s.sid] = tr.set_index("t_in")["ret"].resample("1D").sum()

    # 1) significancia por estrategia
    sig2 = sum(1 for _, _, _, t in tstats if t > 2.0)     # ~95%
    sig3 = sum(1 for _, _, _, t in tstats if t > 3.0)
    # Bonferroni aprox: con ~185 candidatos evaluados, umbral t ~ 3.0-3.3
    print(f"{'='*72}\n1) SIGNIFICANCIA POR ESTRATEGIA (t-stat del expectancy)")
    print(f"  {len(tstats)} estrategias · t>2 (indiv. 95%): {sig2} · t>3 (corrige multi-test): {sig3}")
    print(f"  Mediana t-stat: {np.median([t for *_,t in tstats]):.2f}")
    weak = [sid for sid, n, e, t in tstats if t < 2.0]
    print(f"  Con t<2 (edge no distinguible de ruido aún): {len(weak)} -> {weak[:12]}")

    # portafolio vol-parity
    M = pd.concat(daily.values(), axis=1).fillna(0)
    sig = M.std().replace(0, np.nan); w = (1 / sig); w = (w / w.sum()).values
    port = (M * w).sum(axis=1)
    def sharpe(p): return p.mean() / p.std() * np.sqrt(365) if p.std() > 0 else 0

    print(f"\n2) DEPENDENCIA DE RÉGIMEN")
    print(f"  Sharpe full: {sharpe(port):.2f}")
    by_year = {y: sharpe(port[port.index.year == y]) for y in sorted(set(port.index.year))}
    print("  Sharpe por año: " + " · ".join(f"{y}:{v:.2f}" for y, v in by_year.items()))
    ex24 = port[port.index.year != 2024]
    print(f"  Sharpe EXCLUYENDO 2024 (el año fuerte): {sharpe(ex24):.2f}  ({sharpe(ex24)/sharpe(port)*100:.0f}% del full)")

    # 3) estrés de correlación
    corr_all = M.corr().values
    offall = corr_all[np.triu_indices(len(corr_all), 1)]
    bad_days = port < port.quantile(0.10)            # peores 10% de días del portafolio
    corr_bad = M[bad_days].corr().values
    offbad = corr_bad[np.triu_indices(len(corr_bad), 1)]
    print(f"\n3) ESTRÉS DE CORRELACIÓN (clave para el Sharpe de cartera)")
    print(f"  corr media entre estrategias — días normales: {np.nanmean(offall):.3f}")
    print(f"  corr media — peores 10% días del portafolio: {np.nanmean(offbad):.3f}")
    print(f"  -> si sube fuerte en días malos, la diversificación se evapora justo cuando importa")

    # 4) cola
    monthly = port.resample("ME").sum()
    quarterly = port.resample("QE").sum()
    eq = (1 + port).cumprod(); dd = (eq / eq.cummax() - 1)
    cvar5 = port[port <= port.quantile(0.05)].mean()
    print(f"\n4) COLA / DRAWDOWN (1×, sin apalancar)")
    print(f"  peor mes {monthly.min()*100:+.1f}% · peor trimestre {quarterly.min()*100:+.1f}% · maxDD {dd.min()*100:.1f}%")
    print(f"  CVaR 5% diario {cvar5*100:.2f}% · días negativos {(port<0).mean()*100:.0f}%")
    # racha de DD
    underwater = (dd < 0)
    print(f"  % del tiempo en drawdown: {underwater.mean()*100:.0f}%")

    print(f"\n5) LECTURA HONESTA")
    print(f"  - El Sharpe alto viene de combinar muchas estrategias poco correlacionadas (efecto √N).")
    print(f"  - Si la corr en días malos >> normal, el Sharpe vivo será MUCHO menor que el backtest.")
    print(f"  - Estrategias con t<2 ({len(weak)}) aún no tienen edge estadísticamente distinguible -> el")
    print(f"    paper trading en vivo es el juez real, no el backtest.")


if __name__ == "__main__":
    main()

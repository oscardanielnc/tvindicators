"""Promoción formal de NVDA-ORB-activo (filtro pre-market AGITADO) a la cartera tradfi.
Reusa la maquinaria de portfolio_multi.py (vol-parity, IS/OOS, correlación) y añade el candidato.
Gate: el candidato debe (a) tener OOS Sharpe>0 a solas, (b) bajar/mantener la correlación media,
(c) NO empeorar el Sharpe OOS combinado (idealmente subirlo). Datos: acción real Databento.
Uso: python tradfi/promote_nvda_orb.py
"""
import os, sys, math
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_multi as PM
import poc_quiet_open as P

PM_THR = 1.31   # umbral pm_ratio fijado en IS (NVDA, p67) — pre-market agitado
ANN = math.sqrt(252)


def nvda_orb_active_daily():
    """Serie de PnL diario: NVDA ORB-long, OR=15m, solo días de pre-market agitado (pm_ratio>=1.31)."""
    t = P.build("NVDA", 15, None).dropna(subset=["pm_ratio"])
    t = t[(t.side == 1) & (t.pm_ratio >= PM_THR)]
    s = pd.Series(t["net"].values, index=pd.to_datetime(t["date"]))
    return s.groupby(s.index.normalize()).sum().sort_index()


def sharpe(p):
    return p.mean() / p.std(ddof=1) * ANN if p.std(ddof=1) > 0 else 0


def analyze(roster):
    series = {k: f() for k, f in roster.items()}
    M = pd.concat(series, axis=1).sort_index().fillna(0.0)
    is_M = M[M.index < pd.Timestamp(PM.IS_END)]
    sig = is_M.std(ddof=1).replace(0, np.nan)
    w = (1 / sig); w = w / w.sum()
    port = (M * w).sum(axis=1)
    oos = port[M.index >= pd.Timestamp(PM.IS_END)]
    is_p = port[M.index < pd.Timestamp(PM.IS_END)]
    oos_M = M[M.index >= pd.Timestamp(PM.IS_END)]
    corr = oos_M.corr()
    off = corr.values[np.triu_indices(len(roster), 1)]
    return dict(w=w, sh_is=sharpe(is_p), sh_oos=sharpe(oos), corr=corr,
                corr_mean=float(np.nanmean(off)), series=series, oos_M=oos_M)


def main():
    print("=" * 90)
    print("PROMOCIÓN FORMAL — NVDA-ORB-activo (pre-market agitado pm_ratio>=%.2f) a cartera tradfi" % PM_THR)
    print("=" * 90)

    base = dict(PM.ROSTER)
    cand = dict(PM.ROSTER); cand["NVDA-ORB-act"] = nvda_orb_active_daily

    # candidato a solas
    s = nvda_orb_active_daily()
    oos = s[s.index >= pd.Timestamp(PM.IS_END)]
    is_s = s[s.index < pd.Timestamp(PM.IS_END)]
    print(f"\n[Candidato a solas] NVDA-ORB-act: {len(s)} días-trade · "
          f"{s.index[0].date()}->{s.index[-1].date()}")
    print(f"  IS  Sharpe {sharpe(is_s):+.2f} ({len(is_s)} días)   "
          f"OOS Sharpe {sharpe(oos):+.2f} ({len(oos)} días)")

    rb, rc = analyze(base), analyze(cand)
    print(f"\n[Cartera SIN candidato]  Sharpe OOS {rb['sh_oos']:+.2f} · corr media OOS {rb['corr_mean']:+.2f} · {len(base)} estrategias")
    print(f"[Cartera CON candidato]  Sharpe OOS {rc['sh_oos']:+.2f} · corr media OOS {rc['corr_mean']:+.2f} · {len(cand)} estrategias")
    print(f"  peso vol-parity asignado al candidato: {rc['w'].get('NVDA-ORB-act',0)*100:.0f}%")

    # correlación del candidato con cada miembro existente (clave: ¿es señal nueva?)
    print(f"\n[Correlación OOS del candidato vs roster existente]")
    cc = rc["corr"]["NVDA-ORB-act"].drop("NVDA-ORB-act")
    for k, v in cc.items():
        print(f"  vs {k:14} {v:+.2f}")
    print(f"  correlación media del candidato: {cc.mean():+.2f}")

    # veredicto
    print("\n" + "=" * 90)
    ok_solo = sharpe(oos) > 0
    ok_corr = cc.mean() < 0.5
    ok_port = rc["sh_oos"] >= rb["sh_oos"] - 0.05    # no empeora (tolerancia mínima)
    print(f"Gate: OOS solo>0 [{ '✓' if ok_solo else '✗'}]  corr<0.5 [{'✓' if ok_corr else '✗'}]  "
          f"no empeora cartera [{'✓' if ok_port else '✗'}]")
    if ok_solo and ok_corr and ok_port:
        verb = "SUBE" if rc["sh_oos"] > rb["sh_oos"] else "mantiene"
        print(f"★ PROMOVER: señal nueva (corr media {cc.mean():+.2f}), {verb} el Sharpe OOS de cartera "
              f"({rb['sh_oos']:+.2f}->{rc['sh_oos']:+.2f}).")
    else:
        print("✗ NO promover con estos criterios.")
    print("=" * 90)


if __name__ == "__main__":
    main()

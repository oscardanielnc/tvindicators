"""Exprimir el edge TSLA-long ORB: diagnosticar dónde se fuga el dinero (+49bp captados de +283bp/día)
y probar mejoras de gestión (stop/breakeven/trailing/target) con DISCIPLINA: calibrar en IS, validar OOS.

Config base validada: OR=15min, solo-long, filtro or_pct>=2.25% (fijado en IS), salida cierre.
Simulador de salida flexible (sin lookahead): stop inicial a stop_frac·R bajo la entrada; opción de mover
a breakeven tras +be_R; trailing a trail_R·R bajo el máximo; target take-profit a tp_R·R.
Uso: python improve_orb_tsla.py [TICKER]
"""
import sys
import math
from statistics import NormalDist
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import sweep_orb as S

TICKER = sys.argv[1] if len(sys.argv) > 1 else "TSLA"
N_MIN = 15
OR_FILTER = 2.25          # % del precio (umbral fijado en IS en validate_orb_tsla)
IS_END = pd.Timestamp("2024-01-01").date()
N01 = NormalDist()
COST = 2 * S.TAKER        # ida y vuelta


def detect_long(g, n_min):
    """Detecta la entrada LONG (1ª ruptura del OR-high antes de CUTOFF). Devuelve dict o None."""
    if len(g) < n_min + 10:
        return None
    t = g.index.time
    in_or = np.array([(x.hour * 60 + x.minute) < (9 * 60 + 30 + n_min) for x in t])
    orw = g[in_or]
    if len(orw) < max(1, n_min // 2):
        return None
    orh, orl = orw["high"].max(), orw["low"].min()
    R = orh - orl
    if R <= 0:
        return None
    rest = g[~in_or]
    hi, lo, cl = rest["high"].values, rest["low"].values, rest["close"].values
    times = rest.index.time
    for k in range(len(rest)):
        if times[k] >= S.CUTOFF:
            break
        if hi[k] >= orh:                          # primera ruptura al alza
            if lo[k] <= orl and cl[k] < orh:      # barra que tocó ambos y cerró abajo: no long
                continue
            entry = orh * (1 + S.SLIP)
            return dict(date=g.index[0].date(), entry=entry, orh=orh, orl=orl, R=R,
                        e_i=k, hi=hi, lo=lo, cl=cl, or_pct=R / orh * 100)
    return None


def simulate(d, stop_frac=1.0, be_R=None, trail_R=None, tp_R=None):
    """Simula la salida desde la entrada. Devuelve (net, reason, mfe_R, mae_R)."""
    entry, R, e_i = d["entry"], d["R"], d["e_i"]
    hi, lo, cl = d["hi"], d["lo"], d["cl"]
    stop = entry - stop_frac * R                   # stop inicial
    be_done = False
    peak = entry
    mfe = mae = 0.0
    exit_px = reason = None
    for k in range(e_i, len(cl)):
        peak = max(peak, hi[k])
        mfe = max(mfe, (hi[k] - entry) / R)
        mae = min(mae, (lo[k] - entry) / R)
        # breakeven: tras alcanzar +be_R, sube el stop a la entrada
        if be_R is not None and not be_done and hi[k] >= entry + be_R * R:
            stop = max(stop, entry); be_done = True
        # trailing: stop = max(stop, peak - trail_R*R)
        if trail_R is not None:
            stop = max(stop, peak - trail_R * R)
        # ¿toca stop?
        if lo[k] <= stop:
            exit_px, reason = stop * (1 - S.SLIP), "stop"; break
        # ¿toca target?
        if tp_R is not None and hi[k] >= entry + tp_R * R:
            exit_px, reason = entry + tp_R * R, "target"; break
    if exit_px is None:
        exit_px, reason = cl[-1], "close"
    net = (exit_px / entry - 1) - COST
    return net, reason, mfe, mae


def build(df, n_min):
    out = []
    for _, g in df.groupby(df.index.date):
        d = detect_long(g, n_min)
        if d and d["or_pct"] >= OR_FILTER:
            out.append(d)
    return out


def metr(nets):
    nets = np.asarray(nets, float)
    if len(nets) < 10:
        return None
    sd = nets.std(ddof=1)
    wr = (nets > 0).mean(); g = nets[nets > 0].sum(); l = -nets[nets < 0].sum()
    sr = nets.mean() / sd if sd > 0 else 0
    return dict(n=len(nets), wr=wr, exp=nets.mean(), pf=(g / l if l > 0 else np.inf),
                sharpe=sr * math.sqrt(252), cum=(1 + pd.Series(nets)).prod() - 1)


def show(tag, mm):
    if mm is None:
        print(f"  {tag:34} <10"); return
    print(f"  {tag:34} n={mm['n']:4} WR={mm['wr']*100:3.0f}% exp={mm['exp']*1e4:+5.0f}bp "
          f"PF={mm['pf']:.2f} Sharpe={mm['sharpe']:+.2f} cum={mm['cum']*100:+.0f}%")


def seg(trades, nets, want):
    return [n for d, n in zip(trades, nets) if (d["date"] < IS_END) == (want == "IS")]


def main():
    print("=" * 88)
    print(f"EXPRIMIR {TICKER}-LONG ORB — diagnóstico + mejoras de gestión (IS calibra, OOS valida)")
    print("=" * 88)
    df = S.load(TICKER)
    trades = build(df, N_MIN)
    print(f"{len(trades)} días-trade (OR={N_MIN}min, or_pct>={OR_FILTER}%)\n")

    # ---- DIAGNÓSTICO con la config base (salida cierre, stop OR-low = 1R) ----
    base = [simulate(d, stop_frac=1.0) for d in trades]
    nets0 = [b[0] for b in base]; reasons = [b[1] for b in base]
    mfes = [b[2] for b in base]; maes = [b[3] for b in base]
    print("[DIAGNÓSTICO] config base (stop=OR-low=1R, salida cierre):")
    show("BASE total", metr(nets0))
    import collections
    rc = collections.Counter(reasons)
    print(f"  salidas: {dict(rc)}")
    stopped = [m for m, r in zip(mfes, reasons) if r == "stop"]
    print(f"  MFE medio antes de stopear: {np.mean(stopped):.2f}R  "
          f"(de los stops, % que llegó a +1R antes de revertir: {np.mean([s>=1 for s in stopped])*100:.0f}%)")
    print(f"  MFE medio TODOS: {np.mean(mfes):.2f}R · MAE medio: {np.mean(maes):.2f}R")
    print(f"  -> si muchos stops tuvieron MFE alto, breakeven/trailing recupera ese dinero.\n")

    # ---- MEJORAS: calibrar en IS, validar en OOS ----
    variants = {
        "base (1R stop, cierre)":        dict(stop_frac=1.0),
        "stop 0.5R":                     dict(stop_frac=0.5),
        "breakeven tras +1R":            dict(stop_frac=1.0, be_R=1.0),
        "trailing 1.5R":                 dict(stop_frac=1.0, trail_R=1.5),
        "trailing 1R":                   dict(stop_frac=1.0, trail_R=1.0),
        "0.5R stop + BE +1R":            dict(stop_frac=0.5, be_R=1.0),
        "0.5R stop + trail 1.5R":        dict(stop_frac=0.5, trail_R=1.5),
        "target 3R + BE +1R":            dict(stop_frac=1.0, be_R=1.0, tp_R=3.0),
    }
    print("[IS] calibración (2018-2023) — Sharpe IS por variante:")
    is_scores = {}
    allnets = {}
    for name, kw in variants.items():
        nets = [simulate(d, **kw)[0] for d in trades]
        allnets[name] = nets
        mm = metr(seg(trades, nets, "IS"))
        is_scores[name] = mm["sharpe"] if mm else -9
        show(name + " [IS]", mm)
    best = max(is_scores, key=is_scores.get)
    print(f"\n  -> mejor en IS: '{best}' (Sharpe IS {is_scores[best]:+.2f})")

    print(f"\n[OOS] validación (2024-2026) — comparar base vs mejor variante (holdout):")
    show("BASE [OOS]", metr(seg(trades, allnets["base (1R stop, cierre)"], "OOS")))
    moos = metr(seg(trades, allnets[best], "OOS"))
    show(f"MEJOR '{best}' [OOS]", moos)

    # PSR del mejor OOS
    no = np.asarray(seg(trades, allnets[best], "OOS"), float)
    if len(no) >= 10 and no.std(ddof=1) > 0:
        z = (no - no.mean()) / no.std(ddof=1)
        sr = no.mean() / no.std(ddof=1)
        p0 = N01.cdf(sr * math.sqrt(len(no) - 1) /
                     math.sqrt(max(1e-9, 1 - float((z**3).mean()) * sr + ((float((z**4).mean()) - 1) / 4) * sr**2)))
        print(f"  PSR(0) del mejor OOS: {p0*100:.1f}% · ({len(variants)} variantes probadas -> trata IS como inflado)")
    print("\n" + "=" * 88)
    print("Honesto: la 'mejor' variante se eligió en IS; el número que vale es el OOS. Si OOS≈base, la")
    print("gestión extra no aporta (no fuerces complejidad). Si OOS>base de forma estable, es mejora real.")


if __name__ == "__main__":
    main()

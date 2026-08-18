"""Optimizador de roster (conservador: marca, NO quita).

Resuelve dos sesgos del armado por orden de llegada:
  1) Redundancia intra-roster: dos estrategias con PnL muy correlacionado = la misma apuesta.
  2) Sesgo de antigüedad: se descartó una moneda Z (pariente de X) solo por "X ya es titular",
     aunque Z sea mejor para esa señal.

Principio: el roster se arma por CONTRIBUCIÓN MARGINAL al Sharpe del portafolio, con la
correlación de PnL como árbitro — no por antigüedad ni nombre de indicador.

Qué hace:
  - Reconstruye el PnL diario de las 48 incumbentes.
  - Genera un pool de CHALLENGERS: barre las familias de señal de los batches (SQZ, VTX, ADX,
    CMF, FI, KST, AO, TSI, ZeroLag) sobre las 52 monedas, gate duro (full+OOS+IS).
  - Selección greedy por Sharpe marginal sobre incumbentes ∪ challengers (sin ventaja de incumbencia).
  - Reporta: incumbentes dominados (redundantes), challengers que entrarían (mejores monedas
    no promovidas), y clusters de correlación. Escribe roster_optimizer_REPORT.md.

Uso: python roster_optimizer.py
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/gen_summary.py"), encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # tr_for, getdf, I, DATA, run_f, met, filt_arrays, load_fund, all_coins, FILTER_SETS, STRAT

CORR_REDUND = 0.50     # corr de PnL >= esto = misma apuesta
FAM = {"SQZ": I.squeeze_momentum, "VTX": I.vortex, "ADX": I.adx_dmi, "CMF": I.cmf,
       "FI": I.force_index, "KST": I.kst, "AO": I.awesome_osc, "TSI": I.tsi, "ZL": I.zero_lag_entry}


def _split(tr, cut="2025-01-01"):
    if tr is None:
        return None, None
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def gather_incumbents():
    out = {}
    for s in STRAT.STRATEGIES:
        tr = tr_for(s.sid)
        if tr is not None and len(tr):
            out[s.sid] = dict(label=f"{s.sid}·{s.coin}·{'L' if s.side>0 else 'S'}", coin=s.coin,
                              side=s.side, kind="incumbente",
                              daily=tr.set_index("t_in")["ret"].resample("1D").sum())
    return out


def gather_challengers():
    out = {}
    coins = all_coins()
    for ci, coin in enumerate(coins, 1):
        try:
            df = getdf(coin); ft, fr = load_fund(coin)
        except Exception:
            continue
        up, dn, _ = I.st_flips(df); flips = (up, dn)
        for fam, fn in FAM.items():
            le, se = fn(df)
            for side, ev, tag in ((+1, le, "L"), (-1, se, "S")):
                if not np.asarray(ev).any():
                    continue
                fa = filt_arrays(df, side); best = None
                for fs in FILTER_SETS:
                    mask = np.ones(len(df), bool)
                    for f in fs:
                        mask &= fa[f]
                    tr = run_f(df, side, "atrstop", None, np.asarray(ev) & mask, flips, "1h", ft, fr)
                    m = met(tr)
                    if not m or m["n"] < 40 or m["exp"] <= 0 or m["pf"] < 1.4 or m["ypos"] < m["ytot"] - 1:
                        continue
                    mi, mo = _split(tr)
                    if not mo or not mi or mo["exp"] <= 0 or mo["n"] < 12 or mi["exp"] <= 0:
                        continue
                    if best is None or mo["exp"] > best[1]:
                        best = (tr, mo["exp"])
                if best:
                    key = f"{coin}-{fam}-{tag}"
                    out[key] = dict(label=key, coin=coin, side=side, kind=f"challenger·{fam}",
                                    daily=best[0].set_index("t_in")["ret"].resample("1D").sum())
        print(f"  challengers [{ci}/{len(coins)}] {coin}", end="\r", flush=True)
    print(" " * 60)
    return out


def vp_port(D, cols):
    sub = D[cols]; sig = sub.std().replace(0, np.nan); w = (1 / sig); w = (w / w.sum()).values
    return (sub * w).sum(axis=1)


def sharpe(port):
    return port.mean() / port.std() * np.sqrt(365) if port.std() > 0 else 0


def greedy(D, keys):
    """Forward selection maximizando Sharpe marginal. Devuelve orden de selección + sharpe acumulado."""
    selected, order = [], []
    remaining = list(keys)
    cur_sh = 0
    while remaining:
        best_k, best_sh = None, -1e9
        for k in remaining:
            sh = sharpe(vp_port(D, selected + [k]))
            if sh > best_sh:
                best_sh, best_k = sh, k
        gain = best_sh - cur_sh
        order.append((best_k, best_sh, gain))
        selected.append(best_k); remaining.remove(best_k); cur_sh = best_sh
        if len(selected) >= min(len(keys), 60) and gain < 0.005:
            break
    return order


def main():
    print("Reconstruyendo incumbentes (48)…", flush=True)
    inc = gather_incumbents()
    print(f"  {len(inc)} incumbentes con trades.\nGenerando challengers (52 monedas × 9 familias)…", flush=True)
    chal = gather_challengers()
    print(f"  {len(chal)} challengers OOS-robustos.")

    pool = {**inc, **chal}
    D = pd.concat({k: v["daily"] for k, v in pool.items()}, axis=1).fillna(0)
    D.columns = list(pool.keys())

    # --- 1) redundancia entre INCUMBENTES (corr de PnL) ---
    inc_keys = list(inc.keys())
    C = D[inc_keys].corr()
    pairs = []
    for i in range(len(inc_keys)):
        for jx in range(i + 1, len(inc_keys)):
            c = C.iloc[i, jx]
            if c >= CORR_REDUND:
                pairs.append((inc[inc_keys[i]]["label"], inc[inc_keys[jx]]["label"], round(c, 2)))
    pairs.sort(key=lambda x: -x[2])

    # --- 2) selección greedy sobre TODO el pool (sin ventaja de incumbencia) ---
    order = greedy(D, list(pool.keys()))
    sel_keys = [k for k, _, _ in order]
    sel_set = set(sel_keys)
    N = len(inc)  # comparar el top-N (tamaño del roster actual)
    top = sel_keys[:N]
    inc_out = [inc[k]["label"] for k in inc_keys if k not in set(top)]          # incumbentes fuera del top-N
    chal_in = [(k, pool[k]) for k in top if k in chal]                          # challengers que entran al top-N

    # para cada challenger que entra: ¿reemplaza a un incumbente correlacionado del mismo lado?
    chal_better = []
    for k, info in chal_in:
        coin, side = info["coin"], info["side"]
        # mejor corr con un incumbente del MISMO lado (posible 'X vs Z')
        best_inc, best_c = None, 0
        for ik in inc_keys:
            if inc[ik]["side"] != side:
                continue
            c = D[k].corr(D[ik])
            if c > best_c:
                best_c, best_inc = c, inc[ik]["label"]
        chal_better.append((k, round(best_c, 2), best_inc))

    # --- reporte ---
    L = []
    L.append("# Reporte del optimizador de roster (conservador — marca, no quita)\n")
    L.append(f"Pool: {len(inc)} incumbentes + {len(chal)} challengers OOS-robustos = {len(pool)} candidatos.")
    L.append(f"Selección greedy por Sharpe marginal (vol-parity). Umbral de redundancia: corr ≥ {CORR_REDUND}.\n")
    L.append(f"## 1) Pares de INCUMBENTES redundantes (corr de PnL ≥ {CORR_REDUND}) → revisar, quedarse con el mejor")
    if pairs:
        for a, b, c in pairs:
            L.append(f"- {a}  ↔  {b}   corr **{c}**")
    else:
        L.append("- Ninguno. El roster actual no tiene pares redundantes (buena señal).")
    L.append(f"\n## 2) Incumbentes FUERA del top-{N} óptimo (dominados / aporte marginal bajo) → observación")
    L.append("> No se quitan (fase paper); se marcan para vigilar si en vivo no aportan.")
    L.append("- " + (", ".join(inc_out) if inc_out else "ninguno — todas las incumbentes están en el óptimo."))
    L.append(f"\n## 3) Challengers que ENTRARÍAN al top-{N} (mejores candidatos NO promovidos)")
    L.append("> El caso 'moneda Z mejor que X' o mejor combo no probado. Candidatos a evaluar/promover.")
    if chal_better:
        for k, c, bi in sorted(chal_better, key=lambda x: x[1]):
            rel = f"corr {c} con {bi}" if bi else "sin incumbente correlacionado"
            tag = "ALTERNATIVA a " if c >= CORR_REDUND else "NUEVA apuesta (descorrelacionada) · "
            L.append(f"- **{k}** — {tag}{rel}")
    else:
        L.append("- Ninguno: el roster actual ya captura lo mejor del pool.")
    L.append(f"\n## Resumen")
    L.append(f"- Sharpe del portafolio óptimo (greedy, {len(sel_keys)} sel.): **{order[-1][1]:.2f}**")
    L.append(f"- Incumbentes redundantes (pares): {len(pairs)} · fuera del top: {len(inc_out)} · challengers a revisar: {len(chal_better)}")
    open("roster_optimizer_REPORT.md", "w", encoding="utf-8").write("\n".join(L))

    print("\n".join(L[:4]))
    print(f"\nPares redundantes incumbentes: {len(pairs)}")
    for a, b, c in pairs[:8]:
        print(f"  {a} ↔ {b}  corr {c}")
    print(f"\nIncumbentes fuera del top-{N}: {len(inc_out)} -> {inc_out[:12]}")
    print(f"\nChallengers que entran al top-{N}: {len(chal_in)}")
    for k, c, bi in sorted(chal_better, key=lambda x: x[1])[:15]:
        print(f"  {k:18} corr_max_incumbente {c}  ({'alternativa a '+bi if c>=CORR_REDUND else 'NUEVA · '+str(bi)})")
    print("\n-> roster_optimizer_REPORT.md")


if __name__ == "__main__":
    main()

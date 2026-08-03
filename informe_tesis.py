"""Informe de fase de medición: desempeño por TESIS + salidas alternativas.

Es la vista que responde la única pregunta de esta etapa: ¿qué apuesta es rentable de verdad?
No mira el balance (el sizing es plano justamente para que el balance no distorsione), mira
la expectancia en bps sobre nocional, su t-stat y cuántos trades faltan para poder decidir.

Uso:  python informe_tesis.py
"""
import json
import math
import sqlite3
import statistics as st
from collections import defaultdict

import config
from tvbot import theses
from tvbot.strategies import STRATEGIES
from tvbot.strategies_tradfi import STRATEGIES_TRADFI

ALL = STRATEGIES + STRATEGIES_TRADFI


def main():
    c = sqlite3.connect(config.DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute(
        "SELECT strategy_id, ret_pct_nolev, pnl_usd, shadow_exits FROM trades "
        "WHERE status='closed' AND ret_pct_nolev IS NOT NULL")]
    tid_of = {s.sid: theses.thesis_of(s) for s in ALL}
    name_of = {s.sid: s.name for s in ALL}

    by_t = defaultdict(list)
    for r in rows:
        by_t[tid_of.get(r["strategy_id"], "?")].append(r)

    print("=" * 96)
    print("DESEMPEÑO POR TESIS  (bps netos sobre nocional — independiente del sizing)")
    print(f"gate: n>={config.GATE_THESIS_MIN_TRADES}, t>={config.GATE_THESIS_MIN_T}, "
          f"PF>={config.GATE_THESIS_MIN_PF} | sizing={config.SIZING_MODE}")
    print("=" * 96)
    aggs = [theses.aggregate(t, rs) for t, rs in by_t.items()]
    for a in sorted(aggs, key=lambda d: -(d.get("t_stat") or -99)):
        if a["n"] < 2:
            print(f"\n{a['label']:32s} n={a['n']}  (sin datos)")
            continue
        print(f"\n{a['label']:32s} n={a['n']:4d}  exp={a['exp_bps']:+7.1f} bps  "
              f"t={a['t_stat']:+5.2f}  IC95=[{a['ci95_bps'][0]:+.0f},{a['ci95_bps'][1]:+.0f}]  "
              f"WR={a['wr']}%  PF={a['pf']}")
        print(f"  {a['verdict_label']}", end="")
        nn = a.get("n_para_significancia")
        if nn and nn > config.THESIS_N_INVIABLE:
            print(f" — harían falta ~{nn:,} trades para confirmarla (~{nn/160/12:.0f} años a este "
                  f"ritmo): el edge es demasiado fino, hay que engordarlo, no esperar")
        elif nn:
            falta = nn - a["n"]
            print(f" — con este tamaño de edge harían falta ~{nn} trades "
                  f"({'faltan ~%d' % falta if falta > 0 else 'ya alcanzado'})")
        else:
            print(" — expectancia <=0: no hay tamaño de muestra que la salve, hay que arreglar la idea")
        det = []
        for sid in {r["strategy_id"] for r in by_t[a["thesis"]]}:
            rs = [r["ret_pct_nolev"] * 100 for r in by_t[a["thesis"]] if r["strategy_id"] == sid]
            det.append((sum(rs) / len(rs), len(rs), sid))
        det.sort()
        if det:
            peor, mejor = det[0], det[-1]
            print(f"  arrastra: {peor[2]} {name_of.get(peor[2],'')[:28]:28s} "
                  f"n={peor[1]:2d} {peor[0]:+7.0f} bps   |   "
                  f"tira: {mejor[2]} {name_of.get(mejor[2],'')[:28]:28s} n={mejor[1]:2d} {mejor[0]:+7.0f} bps")

    # ---- salidas alternativas ----
    sh_rows = [r for r in rows if r["shadow_exits"]]
    if not sh_rows:
        print("\n(sin datos de shadow todavía — corre backfill_shadow.py o espera a los trades nuevos)")
        return
    print("\n" + "=" * 96)
    print(f"SALIDAS ALTERNATIVAS EN LA SOMBRA  (n={len(sh_rows)} trades con contrafactual)")
    print("=" * 96)
    acc = defaultdict(list); real = []
    for r in sh_rows:
        try:
            sh = json.loads(r["shadow_exits"])
        except Exception:
            continue
        real.append(r["ret_pct_nolev"] * 100)
        for k, v in sh.items():
            acc[k].append(v)
    base = acc.get("base", [])
    print(f"real (ejecutado) : {st.mean(real):+7.1f} bps/trade")
    if base:
        print(f"'base' simulado  : {st.mean(base):+7.1f} bps/trade   "
              f"<- fidelidad del simulador, debe pegarse al real\n")
    print(f"{'variante':12s} {'n':>5s} {'exp bps':>9s} {'delta':>8s} {'t(delta)':>9s}")
    out = []
    for k, v in acc.items():
        d = [a - b for a, b in zip(v, base)] if len(base) == len(v) else []
        t_d = (st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))) if len(d) >= 2 and st.stdev(d) > 0 else None
        out.append((st.mean(v), k, len(v), st.mean(d) if d else None, t_d))
    for m, k, n, d, t_d in sorted(out, reverse=True):
        print(f"{k:12s} {n:5d} {m:+9.1f} "
              f"{('%+8.1f' % d) if d is not None else '       -':>8s} "
              f"{('%+9.2f' % t_d) if t_d is not None else '        -':>9s}")
    print("\nLeer con cuidado: sobre trades ANTERIORES al despliegue esto es IN-SAMPLE (la hipótesis")
    print("salió de mirar estos mismos trades). Sirve para validar el simulador y fijar la línea")
    print("base; la decisión se toma cuando haya suficientes trades POSTERIORES al despliegue.")


if __name__ == "__main__":
    main()

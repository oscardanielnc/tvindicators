"""TESIS: la unidad de decisión en fase de medición.

Problema que resuelve. El gate de producción pide n>=20 trades cerrados POR ESTRATEGIA. Con 79
estrategias y ~160 trades/mes en total, eso son ~8-10 meses antes de poder decidir nada — y aun
entonces, n=20 no distingue una expectancia de +50bps del ruido. Peor: probar 79 hipótesis
independientes garantiza ~4 "ganadoras" por puro azar (auditoría 03/08/2026: 0 estrategias con
t>+2 y 4 con t<-2, exactamente lo que predice el ruido).

Qué se hace en su lugar. Se agrupan las estrategias por TESIS — la apuesta económica que
comparten, no el indicador ni la moneda. Todas las estrategias de una tesis son réplicas de la
misma idea sobre distintos símbolos, así que sus trades se pueden juntar: 'shorts de alts en 1h'
ya tiene n=159 hoy contra n<=16 de la mejor estrategia suelta. La estrategia individual pasa a
ser DIAGNÓSTICO (¿cuál arrastra a la tesis?), no la unidad de aprobación.

Esto no es un truco para aprobar antes: el gate por tesis es más exigente en potencia (pide
t-stat, no solo PnL>0) y reduce el problema de comparaciones múltiples de 79 hipótesis a 6.
"""
import math
import statistics as st

import config

# id -> (etiqueta, descripción de la apuesta)
THESES = {
    "cripto-short-1h": ("Shorts de alts 1h",
                        "vender rupturas/agotamiento en alts de media cap, barra de 1h"),
    "cripto-long":     ("Longs de cripto",
                        "comprar continuación en alts (gateado por régimen BTC desde 25/06)"),
    "cripto-intra":    ("Cripto intradía 15m/30m",
                        "señales rápidas en cripto por debajo de 1h"),
    "tradfi-orb":      ("ORB de acciones",
                        "ruptura del rango de apertura en perps de acciones, cierre en sesión"),
    "tradfi-long":     ("Longs de acciones (swing)",
                        "continuación alcista en perps de acciones, 30m/1h"),
    "tradfi-short":    ("Shorts de acciones",
                        "ventas en perps de acciones (bloque pequeño, en observación)"),
}


def thesis_of(s):
    """Estrategia -> id de tesis. Se decide por la APUESTA (clase, lado, horizonte)."""
    if s.asset_class == "stocks":
        if s.exit_mode == "orb":
            return "tradfi-orb"
        return "tradfi-long" if s.side > 0 else "tradfi-short"
    if s.side < 0:
        return "cripto-short-1h" if s.tf == "1h" else "cripto-intra"
    return "cripto-long" if s.tf == "1h" else "cripto-intra"


def aggregate(tid, rows):
    """rows: dicts con ret_pct_nolev (%) y pnl_usd de los trades cerrados de la tesis.
    Todo se mide en BPS SOBRE NOCIONAL — independiente del sizing, que es lo que se compara
    contra el backtest. El PnL en dólares queda como dato secundario."""
    rets = [r["ret_pct_nolev"] * 100 for r in rows if r["ret_pct_nolev"] is not None]
    n = len(rets)
    label, desc = THESES.get(tid, (tid, ""))
    out = {"thesis": tid, "label": label, "desc": desc, "n": n}
    if n < 2:
        return {**out, "verdict": "none", "verdict_label": "Sin datos"}
    exp = st.mean(rets)
    sd = st.stdev(rets)
    se = sd / math.sqrt(n)
    t = exp / se if se else 0.0
    wins = [x for x in rets if x > 0]
    losses = [x for x in rets if x <= 0]
    pf = round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) < 0 else None
    # nº de trades que harían falta para que ESTE tamaño de edge sea significativo (t=2)
    n_need = int(math.ceil((2 * sd / exp) ** 2)) if exp > 0 else None
    if exp <= 0:
        vc, vl = ("fail", "Negativa") if t <= -2 else ("watch", "Sin edge todavía")
    elif n < config.GATE_THESIS_MIN_TRADES:
        vc, vl = "collect", f"Acumulando ({n}/{config.GATE_THESIS_MIN_TRADES})"
    elif t >= config.GATE_THESIS_MIN_T and pf and pf >= config.GATE_THESIS_MIN_PF:
        vc, vl = "pass", "Confirmada ✓ (rentable con significancia)"
    else:
        vc, vl = "ok", "Positiva pero no significativa"
    return {**out,
            "exp_bps": round(exp, 1), "sd_bps": round(sd, 1), "t_stat": round(t, 2),
            "ci95_bps": [round(exp - 1.96 * se, 1), round(exp + 1.96 * se, 1)],
            "wr": round(len(wins) / n * 100), "pf": pf,
            "pnl_usd": round(sum((r["pnl_usd"] or 0) for r in rows), 2),
            "n_para_significancia": n_need,
            "verdict": vc, "verdict_label": vl}

"""Salidas alternativas EN LA SOMBRA — contrafactuales exactos, no cotas.

No cambia NADA de la ejecución. Por cada trade cerrado se re-recorren las MISMAS velas que
usó el motor y se calcula qué habría rendido ese trade bajo otras reglas de salida (stops más
apretados/anchos, objetivos, breakeven, trailing). El resultado se guarda en la columna
`shadow_exits` (JSON, bps netos por variante).

Por qué: en la auditoría del 03/08/2026 el MFE medio vivo fue +1.50R contra un MAE de −0.84R
(el 50% de los trades tocó +1R y el 35% de esos cerró en rojo) → hay una hipótesis real de que
los stops de 2×ATR + timeout de 48h devuelven demasiado. Pero ajustar esa perilla sobre los
mismos 272 trades ya vistos es exactamente el retrofit que produjo un edge de papel que no
transfirió. El shadow-logging separa las dos cosas: se registra el contrafactual desde hoy y se
decide con datos OOS, sin tocar la ejecución mientras tanto.

Es EXACTO (recorre el camino vela a vela) y no un bound como estimar desde MAE/MFE agregados.
Dentro de una misma vela, si el objetivo y el stop caben los dos, se asume que salta el STOP
(criterio conservador — es lo que hace un backtest honesto sin datos de tick).

Se excluye el funding del cálculo (es el mismo orden de magnitud para todas las variantes:
−5.5 USD sobre 272 trades en el histórico vivo). Los fees sí se modelan igual que el motor.
"""
import config

# variante -> parámetros. sl/tp/be/trail se expresan en R = distancia al stop REAL del trade.
#   sl    : multiplica la distancia del stop (1.0 = el stop real de la estrategia)
#   tp    : objetivo fijo en R (None = sin objetivo, se sale por timeout/flip como hoy)
#   be    : mover el stop a breakeven cuando el precio toque +be R
#   trail : una vez superado +trail R, el stop persigue al máximo favorable a trail R de distancia
VARIANTS = {
    "base":       {},                       # replica la salida real (control de fidelidad)
    "sl0.5R":     {"sl": 0.5},
    "sl0.75R":    {"sl": 0.75},
    "sl1.5R":     {"sl": 1.5},
    "tp1R":       {"tp": 1.0},
    "tp1.5R":     {"tp": 1.5},
    "tp2R":       {"tp": 2.0},
    "tp3R":       {"tp": 3.0},
    "be1R":       {"be": 1.0},
    "trail1R":    {"trail": 1.0},
    "tp2R_be1R":  {"tp": 2.0, "be": 1.0},
}


def _net_bps(side, entry_px, exit_px, reason):
    """bps netos sobre nocional, con el mismo modelo de costos que el motor."""
    gross = side * (float(exit_px) / entry_px - 1)
    cost_out = config.TAKER_FEE + config.SLIPPAGE if reason in ("SL", "TP") else config.MAKER_FEE
    # float() explícito: los arrays vienen de numpy y json.dumps no serializa np.float64
    return round(float(gross - config.MAKER_FEE - cost_out) * 1e4, 1)


def _run(side, entry_px, stop_dist, bars, i0, to_bars, flip, et_mod, close_slot,
         live_open, sl=1.0, tp=None, be=None, trail=None):
    """Recorre las velas desde i0 con una regla de salida alternativa. Devuelve (bps, motivo)."""
    op, hi, lo, cl = bars
    stop = entry_px - side * sl * stop_dist * entry_px     # side=+1 long -> stop debajo
    tp_px = entry_px + side * tp * stop_dist * entry_px if tp else None
    best = 0.0                                            # mejor excursión favorable en R

    for k in range(i0, len(cl)):
        # --- stop (incluye gaps: se sale al peor entre open y stop, como el motor) ---
        hit_sl = lo[k] <= stop if side > 0 else hi[k] >= stop
        hit_tp = (hi[k] >= tp_px if side > 0 else lo[k] <= tp_px) if tp_px else False
        if hit_sl:                                        # conservador: el stop manda si caben ambos
            px = min(op[k], stop) if side > 0 else max(op[k], stop)
            return _net_bps(side, entry_px, px, "SL"), "SL"
        if hit_tp:
            px = max(op[k], tp_px) if side > 0 else min(op[k], tp_px)
            return _net_bps(side, entry_px, px, "TP"), "TP"
        # --- salidas no-precio: idénticas al motor ---
        if et_mod is not None and et_mod[k] >= close_slot:
            return _net_bps(side, entry_px, cl[k], "session_close"), "session_close"
        if flip is not None and flip[k]:
            px = op[k + 1] if k + 1 < len(op) else (live_open if live_open else cl[k])
            return _net_bps(side, entry_px, px, "flip"), "flip"
        if to_bars and k - i0 + 1 >= to_bars:
            px = op[k + 1] if k + 1 < len(op) else (live_open if live_open else cl[k])
            return _net_bps(side, entry_px, px, "timeout"), "timeout"
        # --- ajuste del stop para la vela SIGUIENTE (breakeven / trailing) ---
        fav = (hi[k] - entry_px if side > 0 else entry_px - lo[k]) / (stop_dist * entry_px)
        best = max(best, fav)
        if be and best >= be:
            stop = max(stop, entry_px) if side > 0 else min(stop, entry_px)
        if trail and best >= trail:
            t_px = entry_px + side * (best - trail) * stop_dist * entry_px
            stop = max(stop, t_px) if side > 0 else min(stop, t_px)
    return None, "open"                                   # no cerró dentro de las velas disponibles


def compute(side, entry_px, stop_px, bars, i0, to_bars, flip=None,
            et_mod=None, close_slot=None, live_open=None):
    """Devuelve {variante: bps_netos} para un trade ya cerrado. None si falta el stop."""
    if not stop_px or not entry_px:
        return None
    stop_dist = abs(entry_px - stop_px) / entry_px
    if stop_dist <= 0:
        return None
    out = {}
    for name, kw in VARIANTS.items():
        try:
            bps, _ = _run(side, entry_px, stop_dist, bars, i0, to_bars, flip,
                          et_mod, close_slot, live_open, **kw)
        except Exception:
            bps = None
        if bps is not None:
            out[name] = bps
    return out or None

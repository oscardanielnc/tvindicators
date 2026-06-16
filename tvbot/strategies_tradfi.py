"""Estrategias TRADFI (acciones) — validadas con holdout IS/OOS + anti-beta (ver tradfi/validate_*.py
y la cartera tradfi/portfolio_multi.py: OOS Sharpe +2.61, corr media 0.11). Reusan los indicadores
del bot (tvbot/indicators.py). asset_class='stocks'; símbolo = ticker plano; sesión regular ET.

Roster inicial (todas LONG; los shorts pierden en TODO -> confirmado por 2 métodos):
  T1 TSLA-ORB        ruptura de apertura en días volátiles (OR-low stop, salida al cierre)
  T2 NVDA-ST-30m     Supertrend flip (salida: ST contrario + stop 3·ATR)
  T3 NVDA-AO-30m     Awesome Oscillator cruce
  T4 NVDA-SQZ-15m    Squeeze Momentum
  T5 TSLA-ADX-15m    ADX/DMI direccional

Para AÑADIR un candidato: valídalo (validate_indicators/validate_orb), define su entry scalar y
agrégalo a STRATEGIES_TRADFI. El motor lo recoge por asset_class='stocks' (durante la sesión ET).
"""
from datetime import time as _time

import numpy as np

from . import indicators as I
from .strategies import Strategy

ET = "America/New_York"
ATR_STOP = 3.0            # stop de seguridad para las de indicador (igual que el probe/validación)
ORB_NMIN = 15            # ventana del rango de apertura (min)
ORB_THR = 0.0225         # filtro: operar solo si el OR >= 2.25% del precio (umbral fijado en IS, TSLA)
ORB_CUTOFF = _time(12, 0)  # solo rupturas antes del mediodía ET


# ---------- entradas de indicador (señal en la ÚLTIMA vela cerrada, como en el backtest) ----------
def _st_long(df):
    up, _, _ = I.st_flips(df); return bool(np.asarray(up)[-1])

def _ao_long(df):
    le, _ = I.awesome_osc(df); return bool(np.asarray(le)[-1])

def _sqz_long(df):
    le, _ = I.squeeze_momentum(df); return bool(np.asarray(le)[-1])

def _adx_long(df):
    le, _ = I.adx_dmi(df); return bool(np.asarray(le)[-1])

def _st_against_long(df):
    """Array de salida 'flip' para LONG: Supertrend en dirección contraria (dir == -1)."""
    return np.asarray(I.st_flips(df)[2]) == -1


# ---------- ORB (ruptura de apertura) — entrada y stop con lógica de sesión ----------
def _session_today(df):
    """Barras de HOY en la sesión regular ET (09:30-16:00). Devuelve (sub_df, et_index)."""
    et = df.index.tz_convert(ET)
    day = et[-1].date()
    sel = (et.date == day) & (et.time >= _time(9, 30)) & (et.time < _time(16, 0))
    return df[sel], et[sel]


def _orb_levels(df, n_min=ORB_NMIN):
    """(orh, orl, or_pct) del rango de apertura de hoy, o None si aún no se forma."""
    g, et = _session_today(df)
    if len(g) < 1:
        return None
    in_or = et.time < _time(9, 30 + n_min)
    orw = g[in_or]
    if len(orw) < 1:
        return None
    orh, orl = float(orw["high"].max()), float(orw["low"].min())
    if orh <= orl:
        return None
    return orh, orl, (orh - orl) / orh


def _orb_long(df):
    """Señal LONG: OR formado, ancho >= umbral, última vela cerrada rompe OR-high, antes del corte."""
    lv = _orb_levels(df)
    if lv is None:
        return False
    orh, orl, or_pct = lv
    if or_pct < ORB_THR:
        return False
    g, et = _session_today(df)
    lt = et[-1].time()
    if lt < _time(9, 30 + ORB_NMIN) or lt >= ORB_CUTOFF:   # ya pasó el OR y antes del mediodía
        return False
    return bool(float(g["high"].iloc[-1]) >= orh)


def _orb_stop(df, entry_px):
    """Stop del ORB = OR-low de hoy."""
    lv = _orb_levels(df)
    return lv[1] if lv else None


# ---------- roster ----------
# TITULARES (role 1.0, session 'us'): validados con AÑOS de datos de acción real en sesión US regular.
#   Corren sobre el perp Binance PERO solo en horario de sesión US (donde perp≈acción por arbitraje).
# SUPLENTES (role 0.5): aún validándose en vivo (ORB experimental en perp; versiones 24/7 con solo ~40d).
STRATEGIES_TRADFI = [
    # --- titulares: trend-following validado (perp en sesión US) ---
    Strategy("T2", "NVDA-L Supertrend 30m", "NVDA", "30m", +1, "flip", _st_long,
             flip_exit_fn=_st_against_long, safety_atr=ATR_STOP, asset_class="stocks", session="us",
             role=1.0, indicators=["Supertrend"], exit_desc="ST contrario + stop 3·ATR",
             note="titular · acción real OOS Sharpe 1.29 vs B&H 0.46 (gana al beta)"),
    Strategy("T3", "NVDA-L Awesome Oscillator 30m", "NVDA", "30m", +1, "flip", _ao_long,
             flip_exit_fn=_st_against_long, safety_atr=ATR_STOP, asset_class="stocks", session="us",
             role=1.0, indicators=["Awesome Oscillator"], exit_desc="ST contrario + stop 3·ATR",
             note="titular · acción real OOS Sharpe 1.19"),
    Strategy("T4", "NVDA-L Squeeze Momentum 15m", "NVDA", "15m", +1, "flip", _sqz_long,
             flip_exit_fn=_st_against_long, safety_atr=ATR_STOP, asset_class="stocks", session="us",
             role=1.0, indicators=["Squeeze Momentum"], exit_desc="ST contrario + stop 3·ATR",
             note="titular · acción real OOS Sharpe 1.13, 82 trades/año"),
    Strategy("T5", "TSLA-L ADX/DMI 15m", "TSLA", "15m", +1, "flip", _adx_long,
             flip_exit_fn=_st_against_long, safety_atr=ATR_STOP, asset_class="stocks", session="us",
             role=1.0, indicators=["ADX/DMI"], exit_desc="ST contrario + stop 3·ATR",
             note="titular · acción real OOS Sharpe 1.06, PF 1.86"),
    # --- suplente experimental ---
    Strategy("T1", "TSLA-L ORB apertura volátil 15m", "TSLA", "15m", +1, "orb", _orb_long,
             asset_class="stocks", session="us", role=0.5, entry_stop_fn=_orb_stop,
             indicators=["Opening Range Breakout"],
             exit_desc="stop OR-low + salida al cierre de sesión (16:00 ET)",
             note="SUPLENTE experimental · OR del perp no es subasta fresca; validar en vivo"),
]

BY_ID_TRADFI = {s.sid: s for s in STRATEGIES_TRADFI}

# Referencia de backtest (OOS) para comparar live-vs-backtest, igual que BACKTEST_REF de cripto.
# (exp en bps de nominal por trade, profit factor OOS).
BACKTEST_REF_TRADFI = {
    "T1": (40, 1.45), "T2": (87, 1.64), "T3": (58, 1.62), "T4": (37, 1.53), "T5": (50, 1.86),
}

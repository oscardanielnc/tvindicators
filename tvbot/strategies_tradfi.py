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
import pandas as pd

from . import indicators as I
from .strategies import Strategy

ET = "America/New_York"
ATR_STOP = 3.0            # stop de seguridad para las de indicador (igual que el probe/validación)
ORB_NMIN = 15            # ventana del rango de apertura (min)
ORB_THR = 0.0225         # filtro: operar solo si el OR >= 2.25% del precio (umbral fijado en IS, TSLA)
ORB_CUTOFF = _time(12, 0)  # solo rupturas antes del mediodía ET
# --- filtro "pre-market agitado" (NVDA, validado IS/OOS+anti-beta, ver tradfi/validate_active_open.py
#     y tradfi/promote_nvda_orb.py): operar el breakout SOLO si el rango pre-market (08:00-09:30 ET)
#     fue >= PM_RATIO_THR veces su mediana reciente. Umbral fijado en IS (p67). ---
PM_START_MIN, PM_END_MIN = 8 * 60, 9 * 60 + 30     # ventana pre-market 08:00-09:30 ET
PM_RATIO_THR = 1.31      # hoy_pm_range / mediana_reciente >= 1.31 (fijado en IS, NVDA)
PM_LOOKBACK_DAYS = 20    # mediana sobre hasta 20 días previos de pre-market
PM_MIN_DAYS = 6          # mínimo de días previos para calcular baseline (si no, NO opera: degradación segura)


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


# ---------- ORB con filtro PRE-MARKET AGITADO (NVDA) ----------
def _pm_ratio_today(df):
    """rango pre-market de HOY (08:00-09:30 ET) / mediana de días previos. None si no hay base.
    Sin look-ahead: a la hora del breakout (>=09:45 ET) el pre-market ya cerró; la mediana usa SOLO
    días anteriores. Requiere ver el df 24/7 (NO la vista 'us', que recorta el pre-market)."""
    et = df.index.tz_convert(ET)
    mins = (et.hour * 60 + et.minute).to_numpy()
    pm = (mins >= PM_START_MIN) & (mins < PM_END_MIN)
    dates = np.array([d for d in et.date])
    rng_by_day = {}
    for d in pd.unique(dates):
        sel = pm & (dates == d)
        if sel.sum() < 3:
            continue
        sub = df[sel]
        ref = float(sub["close"].iloc[-1])
        if ref > 0:
            rng_by_day[d] = (float(sub["high"].max()) - float(sub["low"].min())) / ref * 100
    today = et[-1].date()
    if today not in rng_by_day:
        return None
    prior = [rng_by_day[d] for d in sorted(rng_by_day) if d < today]
    if len(prior) < PM_MIN_DAYS:
        return None
    base = float(np.median(prior[-PM_LOOKBACK_DAYS:]))
    return rng_by_day[today] / base if base > 0 else None


def _smc_sbos_long(df):
    """SMC Swing Break of Structure (LuxAlgo), lado largo. Import perezoso de smc (motor compartido)."""
    import smc
    return bool(smc.compute(df)["sbos_bull"][-1])


def _srst_long(df):
    """S/R[LuxAlgo]+Supertrend: flip alcista de Supertrend + ruptura de resistencia (volumen) reciente (<=10)."""
    up, _, _ = I.st_flips(df)
    brkL, _ = I.sr_break_lux(df)
    rec = pd.Series(brkL).rolling(10, min_periods=1).max().fillna(0).astype(bool).values
    return bool(np.asarray(up)[-1] and rec[-1])


def _srst_short(df):
    _, dn, _ = I.st_flips(df)
    _, brkS = I.sr_break_lux(df)
    rec = pd.Series(brkS).rolling(10, min_periods=1).max().fillna(0).astype(bool).values
    return bool(np.asarray(dn)[-1] and rec[-1])


def _orb_long_active(df):
    """Señal LONG NVDA: OR formado + última vela rompe OR-high + pre-market AGITADO (pm_ratio>=thr),
    dentro de la sesión y antes del corte. Auto-gating (session='24/7' para poder ver el pre-market)."""
    lv = _orb_levels(df)
    if lv is None:
        return False
    orh, _orl, _or_pct = lv
    g, et = _session_today(df)
    lt = et[-1].time()
    if lt < _time(9, 30 + ORB_NMIN) or lt >= ORB_CUTOFF:    # ya formó el OR y antes del mediodía
        return False
    pr = _pm_ratio_today(df)
    if pr is None or pr < PM_RATIO_THR:                      # sin base o pre-market tranquilo -> no opera
        return False
    return bool(float(g["high"].iloc[-1]) >= orh)


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
    # --- suplentes experimentales ---
    Strategy("T1", "TSLA-L ORB apertura volátil 15m", "TSLA", "15m", +1, "orb", _orb_long,
             asset_class="stocks", session="us", role=0.5, entry_stop_fn=_orb_stop,
             indicators=["Opening Range Breakout"],
             exit_desc="stop OR-low + salida al cierre de sesión (16:00 ET)",
             note="SUPLENTE experimental · OR del perp no es subasta fresca; validar en vivo"),
    # NVDA ORB con filtro PRE-MARKET AGITADO (validado IS/OOS+anti-beta: OOS Sharpe +2.89, PF 1.72,
    # gana al beta; promoción formal en cartera tradfi OK, corr +0.12). session='24/7' para VER el
    # pre-market (la vista 'us' lo recorta); auto-gating por hora dentro de la entrada.
    Strategy("T6", "NVDA-L ORB pre-market agitado 15m", "NVDA", "15m", +1, "orb", _orb_long_active,
             asset_class="stocks", session="24/7", role=0.5, entry_stop_fn=_orb_stop,
             indicators=["Opening Range Breakout", "Pre-market range filter"],
             exit_desc="stop OR-low + salida al cierre de sesión (15:45 ET)",
             note="SUPLENTE experimental · filtro validado en ACCIÓN real; el pre-market del PERP es "
                  "proxy (poca arbitraje fuera de sesión) y baseline live ~9d vs 20d backtest -> validar en vivo"),
    # --- S/R Breaks [LuxAlgo] + Supertrend (ST_flip+SRrec): validado tradfi líquido, anti-beta por
    #     (ticker,lado) -> solo los pares con alpha real; corr ~0 con T1-T6 y entre sí. exit atrstop=lo
    #     backtesteado. session 24/7 (backtest sobre equity extended-hours; perp es proxy -> validar vivo). ---
    Strategy("T7", "TSLA-L S/R+Supertrend 1h",  "TSLA", "1h", +1, "atrstop", _srst_long,
             asset_class="stocks", session="24/7", role=0.5,
             indicators=["S/R Levels with Breaks (LuxAlgo)", "Supertrend"], exit_desc="SL 2×ATR + timeout 48h",
             note="suplente experimental · ST flip + ruptura S/R(vol) reciente · alpha +153bp vs deriva"),
    Strategy("T8", "AAPL-L S/R+Supertrend 1h",  "AAPL", "1h", +1, "atrstop", _srst_long,
             asset_class="stocks", session="24/7", role=0.5,
             indicators=["S/R Levels with Breaks (LuxAlgo)", "Supertrend"], exit_desc="SL 2×ATR + timeout 48h",
             note="suplente experimental · alpha +81bp vs deriva"),
    Strategy("T9", "NVDA-L S/R+Supertrend 1h",  "NVDA", "1h", +1, "atrstop", _srst_long,
             asset_class="stocks", session="24/7", role=0.5,
             indicators=["S/R Levels with Breaks (LuxAlgo)", "Supertrend"], exit_desc="SL 2×ATR + timeout 48h",
             note="suplente experimental · alpha +60bp vs deriva"),
    Strategy("T10", "MU-S S/R+Supertrend 1h",   "MU",   "1h", -1, "atrstop", _srst_short,
             asset_class="stocks", session="24/7", role=0.5,
             indicators=["S/R Levels with Breaks (LuxAlgo)", "Supertrend"], exit_desc="SL 2×ATR + timeout 48h",
             note="suplente experimental · short vence a su deriva, alpha +139bp"),
    Strategy("T11", "AMD-S S/R+Supertrend 1h",  "AMD",  "1h", -1, "atrstop", _srst_short,
             asset_class="stocks", session="24/7", role=0.5,
             indicators=["S/R Levels with Breaks (LuxAlgo)", "Supertrend"], exit_desc="SL 2×ATR + timeout 48h",
             note="suplente experimental · short vence a su deriva, alpha +106bp"),
    # --- SMC Swing BOS LONG-only en equity (en cripto fue bidireccional → S57-S64; en acciones solo
    #     el largo tiene edge). Validado anti-beta por-ticker (alpha real, no momentum-beta); corr <0.5
    #     vs S/R+ST mismo ticker (señal distinta). exit atrstop=lo backtesteado, role 0.5, session 24/7. ---
    Strategy("T12", "NVDA-L SMC SwingBOS 1h", "NVDA", "1h", +1, "atrstop", _smc_sbos_long,
             asset_class="stocks", session="24/7", role=0.5,
             indicators=["Smart Money Concepts — Swing Break of Structure (LuxAlgo)"],
             exit_desc="SL 2×ATR + timeout 48h", note="suplente experimental · alpha +128bp vs deriva (OOS +224)"),
    Strategy("T13", "TSLA-L SMC SwingBOS 1h", "TSLA", "1h", +1, "atrstop", _smc_sbos_long,
             asset_class="stocks", session="24/7", role=0.5,
             indicators=["Smart Money Concepts — Swing Break of Structure (LuxAlgo)"],
             exit_desc="SL 2×ATR + timeout 48h", note="suplente experimental · alpha +98bp (OOS +14, flojo)"),
    Strategy("T14", "AAPL-L SMC SwingBOS 1h", "AAPL", "1h", +1, "atrstop", _smc_sbos_long,
             asset_class="stocks", session="24/7", role=0.5,
             indicators=["Smart Money Concepts — Swing Break of Structure (LuxAlgo)"],
             exit_desc="SL 2×ATR + timeout 48h", note="suplente experimental · alpha +60bp vs deriva"),
    Strategy("T15", "MU-L SMC SwingBOS 1h",   "MU",   "1h", +1, "atrstop", _smc_sbos_long,
             asset_class="stocks", session="24/7", role=0.5,
             indicators=["Smart Money Concepts — Swing Break of Structure (LuxAlgo)"],
             exit_desc="SL 2×ATR + timeout 48h", note="suplente experimental · alpha +41bp vs deriva (OOS +208)"),
]

BY_ID_TRADFI = {s.sid: s for s in STRATEGIES_TRADFI}

# Referencia de backtest (OOS) para comparar live-vs-backtest, igual que BACKTEST_REF de cripto.
# (exp en bps de nominal por trade, profit factor OOS).
BACKTEST_REF_TRADFI = {
    "T1": (40, 1.45), "T2": (87, 1.64), "T3": (58, 1.62), "T4": (37, 1.53), "T5": (50, 1.86),
    "T6": (45, 1.72),    # NVDA ORB pre-market agitado: OOS exp +45bp/trade, PF 1.72 (acción real)
    # S/R[LuxAlgo]+Supertrend (ST_flip+SRrec), exp bp + PF del backtest de selección por (ticker,lado)
    "T7": (164, 2.12), "T8": (98, 2.29), "T9": (72, 1.68), "T10": (63, 1.43), "T11": (23, 1.14),
    # SMC Swing BOS long-only equity (exp bp, PF del backtest anti-beta por-ticker)
    "T12": (146, 2.80), "T13": (124, 1.91), "T14": (75, 2.31), "T15": (86, 1.67),
}

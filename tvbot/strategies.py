"""Las 9 estrategias validadas (CONSOLIDADO.md). Cada una expone:
- entry(df) -> bool en la ULTIMA vela cerrada
- exit_mode: 'atrstop' (SL 2xATR + timeout 48h) o 'flip' (Supertrend contrario)
- flip_exit(df) -> bool (solo para exit_mode='flip')
"""
import numpy as np
from . import indicators as I


def _last(arr):
    return bool(arr[-1])


# --- filtros de conviccion (validados OOS 14/06/2026; ver roster-upgrades-validados) ---

def _trend(df, side):
    return bool(I.ema_trend_ok(df["close"], side)[-1])

def _vol(df):
    return bool(I.vol_ok(df)[-1])

def _regime(df, side):
    _, _, regup, regdn = I.bx_parts(df["close"])
    return bool(regup[-1] if side > 0 else regdn[-1])

def _sweep(df, side, F=6):
    sL, sS = I.liquidity_sweeps(df)
    return bool(I.sweep_recent(sL if side > 0 else sS, F)[-1])


class Strategy:
    def __init__(self, sid, name, coin, tf, side, exit_mode, entry_fn, flip_exit_fn=None,
                 role=1.0, safety_atr=None, indicators=(), exit_desc=""):
        self.sid = sid
        self.name = name
        self.coin = coin
        self.symbol = f"{coin}/USDT:USDT"
        self.tf = tf
        self.side = side                # +1 long / -1 short
        self.exit_mode = exit_mode      # 'atrstop' | 'flip'
        self._entry = entry_fn
        self._flip_exit = flip_exit_fn
        self.role = role                # 1.0 titular / 0.5 suplente (informativo por ahora)
        self.safety_atr = safety_atr    # SL de seguridad (xATR) para exit_mode='flip'
        self.indicators = list(indicators)   # nombres COMPLETOS de los indicadores usados
        self.exit_desc = exit_desc

    def entry_signal(self, df):
        return self._entry(df)

    def exit_array(self, df):
        """Array booleano de senal de salida por vela (solo exit_mode='flip')."""
        if self.exit_mode != "flip":
            return None
        return self._flip_exit(df)


# --- entradas ---

def s1_entry(df):       # TRX 1h L: B-X verde + barrido<=6 + regimen + tendencia (upgrade OOS)
    gl, _, _, _ = I.bx_parts(df["close"])
    return _last(gl) and _sweep(df, +1, 6) and _regime(df, +1) and _trend(df, +1)

def s2_entry(df):       # TRX 1h L: Trend Meter alinea verde
    return _last(I.tm_align_edge(df["close"]))

def s3_entry(df):       # TRX 15m L: ST flip up + HACOLT=1 + Ribbon>=8
    up, _, _ = I.st_flips(df)
    if not _last(up): return False
    hc = I.hacolt(df["open"], df["high"], df["low"], df["close"])
    if hc[-1] != 1: return False
    sl, _ = I.ribbon_strength(df["close"], df["high"], df["low"])
    return sl[-1] >= 8

def s4_entry(df):       # SUI 1h S: circulo rojo B-X T3>0 + regimen<0
    _, rs, _, regdn = I.bx_parts(df["close"])
    return _last(rs) and _last(regdn)

def s5_entry(df):       # LTC 1h S: ST flip down + Donchian=-1
    _, dn, _ = I.st_flips(df)
    if not _last(dn): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    return don[-1] == -1

def s6_entry(df):       # XRP 1h L: ST flip up + HACOLT=1 + tendencia (upgrade OOS)
    up, _, _ = I.st_flips(df)
    if not _last(up): return False
    hc = I.hacolt(df["open"], df["high"], df["low"], df["close"])
    if hc[-1] != 1: return False
    return _trend(df, +1)

def s7_entry(df):       # AVAX 15m L: ST flip up + Donchian=1 + HACOLT=1
    up, _, _ = I.st_flips(df)
    if not _last(up): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    if don[-1] != 1: return False
    hc = I.hacolt(df["open"], df["high"], df["low"], df["close"])
    return hc[-1] == 1

def s8_entry(df):       # ETH 1h S: B-X rojo + Donchian=-1 + tendencia + vol (upgrade OOS)
    _, rs, _, _ = I.bx_parts(df["close"])
    if not _last(rs): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    if don[-1] != -1: return False
    return _trend(df, -1) and _vol(df)

# --- suplentes nuevos (validados OOS 14/06/2026, role 0.5, corr ~0 con roster) ---

def s10_entry(df):      # DOT 1h S: B-X rojo + Donchian=-1 + barrido<=6
    _, rs, _, _ = I.bx_parts(df["close"])
    if not _last(rs): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    if don[-1] != -1: return False
    return _sweep(df, -1, 6)

def s11_entry(df):      # ADA 1h S: B-X rojo + regimen<0 + tendencia + vol
    _, rs, _, regdn = I.bx_parts(df["close"])
    if not (_last(rs) and bool(regdn[-1])): return False
    return _trend(df, -1) and _vol(df)

def s12_entry(df):      # ADA 1h S: B-X rojo + Donchian=-1 + barrido<=6
    _, rs, _, _ = I.bx_parts(df["close"])
    if not _last(rs): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    if don[-1] != -1: return False
    return _sweep(df, -1, 6)

def s13_entry(df):      # DOT 1h S: ST flip down + Donchian=-1 + tendencia
    _, dn, _ = I.st_flips(df)
    if not _last(dn): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    if don[-1] != -1: return False
    return _trend(df, -1)

def s9_entry(df):       # BTC 1h L: Ribbon completa 10/10 (evento) + BXreg>0 + ST up
    sl, _ = I.ribbon_strength(df["close"], df["high"], df["low"])
    full = sl == 10
    if not (full[-1] and not full[-2]): return False
    _, _, regup, _ = I.bx_parts(df["close"])
    if not _last(regup): return False
    _, _, sd = I.st_flips(df)
    return sd[-1] == 1

# --- salidas flip (devuelven el ARRAY completo; el motor evalua cualquier vela) ---

def flip_dn_exit(df):
    _, dn, _ = I.st_flips(df)
    return dn

def flip_up_exit(df):
    up, _, _ = I.st_flips(df)
    return up

def tm_align_red_exit(df):
    """Salida S2 (upgrade 12/06/2026): los 3 Trend Meters se alinean ROJOS (evento).
    Validado en test_salidas.py: PF 1.40->1.62, +274%->+454%, con SL seguridad 3xATR."""
    c = df["close"]
    fmacd = I.pine_ema(c, 8) - I.pine_ema(c, 21)
    fhist = (fmacd - I.pine_ema(fmacd, 5)) > 0
    neg = ((~fhist) & (I.pine_rsi(c, 13) < 50) & (I.pine_rsi(c, 5) < 50)).values
    import numpy as np
    return neg & ~np.roll(neg, 1)


# nombres completos de los indicadores (para el frontend)
BX = "B-Xtrender (@Puppytherapy)"
BXREG = "B-Xtrender — línea de régimen (@Puppytherapy)"
TM = "Trend Meter (Lij_MC)"
ST = "Supertrend (ATR 10, factor 3.0)"
HAC = "HACOLT — Vervoort LongTerm Heiken-Ashi Candlestick Oscillator (LazyBear)"
RIB = "Donchian Trend Ribbon (LonesomeTheBlue)"
DON = "Donchian Trend (LonesomeTheBlue)"

SL_TO = "SL 2×ATR + timeout 48h"
FLIP = "flip contrario del Supertrend"

STRATEGIES = [
    Strategy("S1", "TRX-L B-Xtrender 1h",      "TRX",  "1h",  +1, "atrstop", s1_entry,
             indicators=[BX], exit_desc=SL_TO),
    Strategy("S2", "TRX-L TrendMeter 1h",      "TRX",  "1h",  +1, "flip",    s2_entry,
             tm_align_red_exit, safety_atr=3.0, indicators=[TM],
             exit_desc="Trend Meter alinea rojo + SL seguridad 3×ATR"),
    Strategy("S3", "TRX-L ST+HAC+RIB 15m",     "TRX",  "15m", +1, "flip",    s3_entry,
             flip_dn_exit, indicators=[ST, HAC, RIB], exit_desc=FLIP),
    Strategy("S4", "SUI-S BX+regimen 1h",      "SUI",  "1h",  -1, "atrstop", s4_entry,
             indicators=[BX, BXREG], exit_desc=SL_TO),
    Strategy("S5", "LTC-S ST+Donchian 1h",     "LTC",  "1h",  -1, "atrstop", s5_entry,
             indicators=[ST, DON], exit_desc=SL_TO),
    Strategy("S6", "XRP-L ST+HACOLT 1h",       "XRP",  "1h",  +1, "flip",    s6_entry,
             flip_dn_exit, indicators=[ST, HAC], exit_desc=FLIP),
    Strategy("S7", "AVAX-L ST+Don+HACOLT 15m", "AVAX", "15m", +1, "flip",    s7_entry,
             flip_dn_exit, indicators=[ST, DON, HAC], exit_desc=FLIP),
    Strategy("S8", "ETH-S BX+Donchian 1h",     "ETH",  "1h",  -1, "atrstop", s8_entry,
             role=0.5, indicators=[BX, DON], exit_desc=SL_TO),
    Strategy("S9", "BTC-L RIB+BXreg+ST 1h",    "BTC",  "1h",  +1, "atrstop", s9_entry,
             role=0.5, indicators=[RIB, BXREG, ST], exit_desc=SL_TO),
    # --- suplentes nuevos (validados OOS 14/06/2026, descorrelacionados del roster) ---
    Strategy("S10", "DOT-S BX+Don+barrido 1h",  "DOT",  "1h",  -1, "atrstop", s10_entry,
             role=0.5, indicators=[BX, DON], exit_desc=SL_TO + " + barrido liquidez"),
    Strategy("S11", "ADA-S BX+reg+tend+vol 1h",  "ADA",  "1h",  -1, "atrstop", s11_entry,
             role=0.5, indicators=[BX, BXREG], exit_desc=SL_TO + " + tendencia/vol"),
    Strategy("S12", "ADA-S BX+Don+barrido 1h",   "ADA",  "1h",  -1, "atrstop", s12_entry,
             role=0.5, indicators=[BX, DON], exit_desc=SL_TO + " + barrido liquidez"),
    Strategy("S13", "DOT-S ST+Don+tendencia 1h", "DOT",  "1h",  -1, "atrstop", s13_entry,
             role=0.5, indicators=[ST, DON], exit_desc=SL_TO + " + tendencia"),
]

BY_ID = {s.sid: s for s in STRATEGIES}

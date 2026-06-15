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
                 role=1.0, safety_atr=None, indicators=(), exit_desc="", timeout_h=None):
        self.sid = sid
        self.name = name
        self.coin = coin
        self.symbol = f"{coin}/USDT:USDT"
        self.tf = tf
        self.side = side                # +1 long / -1 short
        self.exit_mode = exit_mode      # 'atrstop' | 'flip' | 'meanrev'
        self._entry = entry_fn
        self._flip_exit = flip_exit_fn  # 'flip': ST contrario · 'meanrev': vuelta a la media
        self.role = role                # 1.0 titular / 0.5 suplente (informativo por ahora)
        self.safety_atr = safety_atr    # SL de seguridad (xATR) para exit_mode 'flip'/'meanrev'
        self.indicators = list(indicators)   # nombres COMPLETOS de los indicadores usados
        self.exit_desc = exit_desc
        self.timeout_h = timeout_h      # timeout propio (None -> config.TIMEOUT_HOURS); meanrev=24

    def entry_signal(self, df):
        return self._entry(df)

    def exit_array(self, df):
        """Array booleano de senal de salida por vela (exit_mode 'flip' o 'meanrev')."""
        if self.exit_mode not in ("flip", "meanrev"):
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

# --- suplentes de expansión (validados OOS + tuneados 14/06/2026, role 0.5) ---

def s14_entry(df):      # XLM 1h L: TM align verde + regimen + tendencia + vol
    if not _last(I.tm_align_edge(df["close"])): return False
    return _regime(df, +1) and _trend(df, +1) and _vol(df)

def s15_entry(df):      # RUNE 1h L: ST up + Don=1 + HACOLT=1 + regimen + tendencia
    up, _, _ = I.st_flips(df)
    if not _last(up): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    hc = I.hacolt(df["open"], df["high"], df["low"], df["close"])
    if not (don[-1] == 1 and hc[-1] == 1): return False
    return _regime(df, +1) and _trend(df, +1)

def s16_entry(df):      # IMX 1h L: ST up + Don=1 + HACOLT=1 + tendencia + vol
    up, _, _ = I.st_flips(df)
    if not _last(up): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    hc = I.hacolt(df["open"], df["high"], df["low"], df["close"])
    if not (don[-1] == 1 and hc[-1] == 1): return False
    return _trend(df, +1) and _vol(df)

def s17_entry(df):      # FLOW 1h L: ST up + HACOLT=1 + tendencia + vol
    up, _, _ = I.st_flips(df)
    if not _last(up): return False
    hc = I.hacolt(df["open"], df["high"], df["low"], df["close"])
    if hc[-1] != 1: return False
    return _trend(df, +1) and _vol(df)

def s18_entry(df):      # EGLD 1h S: BX rojo + regimen<0 + barrido<=6
    _, rs, _, regdn = I.bx_parts(df["close"])
    if not (_last(rs) and bool(regdn[-1])): return False
    return _sweep(df, -1, 6)

def s19_entry(df):      # FET 1h S: BX rojo + Don=-1 + barrido<=12
    _, rs, _, _ = I.bx_parts(df["close"])
    if not _last(rs): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    if don[-1] != -1: return False
    return _sweep(df, -1, 12)

def s20_entry(df):      # APT 1h S: ST down + Don=-1 + regimen<0 + tendencia
    _, dn, _ = I.st_flips(df)
    if not _last(dn): return False
    don = I.dch_trend(df["close"], df["high"], df["low"], 20)
    if don[-1] != -1: return False
    return _regime(df, -1) and _trend(df, -1)

def s21_entry(df):      # GRT 1h S: BX rojo + regimen<0 + barrido<=6 + tendencia
    _, rs, _, regdn = I.bx_parts(df["close"])
    if not (_last(rs) and bool(regdn[-1])): return False
    return _sweep(df, -1, 6) and _trend(df, -1)

# --- batch 1 indicadores nuevos (Squeeze Momentum + Vortex, validados OOS 15/06/2026, role 0.5) ---

def s22_entry(df):      # ENA 1h L: Squeeze release alcista + regimen
    le, _ = I.squeeze_momentum(df)
    return _last(le) and _regime(df, +1)

def s23_entry(df):      # SAND 1h S: Vortex cruce bajista + regimen
    _, se = I.vortex(df)
    return _last(se) and _regime(df, -1)

def s24_entry(df):      # WIF 1h L: Squeeze release alcista + regimen
    le, _ = I.squeeze_momentum(df)
    return _last(le) and _regime(df, +1)

def s25_entry(df):      # SEI 1h S: Vortex bajista + barrido<=6 + tendencia
    _, se = I.vortex(df)
    return _last(se) and _sweep(df, -1, 6) and _trend(df, -1)

def s26_entry(df):      # ARB 1h S: Vortex bajista + barrido<=6 + tendencia
    _, se = I.vortex(df)
    return _last(se) and _sweep(df, -1, 6) and _trend(df, -1)

def s27_entry(df):      # RUNE 1h S: Vortex bajista + barrido<=6 + tendencia
    _, se = I.vortex(df)
    return _last(se) and _sweep(df, -1, 6) and _trend(df, -1)

def s28_entry(df):      # AVAX 1h S: Vortex bajista + barrido<=6
    _, se = I.vortex(df)
    return _last(se) and _sweep(df, -1, 6)

def s29_entry(df):      # BNB 1h L: Squeeze release alcista + tendencia + vol
    le, _ = I.squeeze_momentum(df)
    return _last(le) and _trend(df, +1) and _vol(df)

# --- batch 2 reversion a la media (motor meanrev, validado OOS 15/06/2026, role 0.5) ---

def s30_entry(df):      # INJ 1h L: BB%b reversion (close<banda inferior) en tendencia alcista SMA200
    # evento sobre la condicion COMBINADA (paridad exacta con poc_meanrev.signals)
    c = df["close"]
    basis = c.rolling(20).mean(); dev = 2.0 * c.rolling(20).std(ddof=0)
    cond = (c < (basis - dev)) & (c > c.rolling(200).mean())
    ev = cond.values & ~np.roll(cond.values, 1); ev[0] = False
    return bool(ev[-1])

def meanrev_up_exit(df):  # salida reversion long: close recupera la SMA(20)
    return I.sma_revert(df["close"], +1, 20)

# --- batch 3: ADX/DMI shorts + Squeeze shorts (edge grueso, validados OOS 15/06/2026, role 0.5) ---

def s31_entry(df):      # ARB 1h S: ADX/DMI cruce bajista (ADX>25) + tendencia + vol
    _, se = I.adx_dmi(df)
    return _last(se) and _trend(df, -1) and _vol(df)

def s32_entry(df):      # EGLD 1h S: Squeeze release bajista + barrido<=6
    _, se = I.squeeze_momentum(df)
    return _last(se) and _sweep(df, -1, 6)

def s33_entry(df):      # DOT 1h S: ADX/DMI bajista + barrido<=6
    _, se = I.adx_dmi(df)
    return _last(se) and _sweep(df, -1, 6)

def s34_entry(df):      # HBAR 1h S: ADX/DMI bajista + barrido<=6
    _, se = I.adx_dmi(df)
    return _last(se) and _sweep(df, -1, 6)

def s35_entry(df):      # FLOW 1h S: Squeeze release bajista + barrido<=6
    _, se = I.squeeze_momentum(df)
    return _last(se) and _sweep(df, -1, 6)

def s36_entry(df):      # AVAX 1h S: ADX/DMI bajista + barrido<=6
    _, se = I.adx_dmi(df)
    return _last(se) and _sweep(df, -1, 6)

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
SQZM = "Squeeze Momentum (LazyBear)"
VTX = "Vortex Indicator (VI+/VI−)"
BBR = "Bollinger Bands %b (reversión a la media)"
ADX = "ADX / DMI (Wilder, DI+/DI−, ADX>25)"

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
    # --- suplentes de expansión (38 perps → 8 robustos OOS+tuneados) ---
    Strategy("S14", "XLM-L TM+reg+tend+vol 1h",  "XLM",  "1h",  +1, "flip",    s14_entry,
             flip_dn_exit, safety_atr=3.0, role=0.5, indicators=[TM], exit_desc="flip ST + SL 3×ATR"),
    Strategy("S15", "RUNE-L ST+Don+HAC 1h",      "RUNE", "1h",  +1, "flip",    s15_entry,
             flip_dn_exit, role=0.5, indicators=[ST, DON, HAC], exit_desc=FLIP),
    Strategy("S16", "IMX-L ST+Don+HAC+vol 1h",   "IMX",  "1h",  +1, "flip",    s16_entry,
             flip_dn_exit, role=0.5, indicators=[ST, DON, HAC], exit_desc=FLIP),
    Strategy("S17", "FLOW-L ST+HAC+vol 1h",      "FLOW", "1h",  +1, "flip",    s17_entry,
             flip_dn_exit, role=0.5, indicators=[ST, HAC], exit_desc=FLIP),
    Strategy("S18", "EGLD-S BX+barrido 1h",      "EGLD", "1h",  -1, "atrstop", s18_entry,
             role=0.5, indicators=[BX, BXREG], exit_desc=SL_TO + " + barrido"),
    Strategy("S19", "FET-S BX+Don+barrido 1h",   "FET",  "1h",  -1, "atrstop", s19_entry,
             role=0.5, indicators=[BX, DON], exit_desc=SL_TO + " + barrido"),
    Strategy("S20", "APT-S ST+Don+tendencia 1h", "APT",  "1h",  -1, "atrstop", s20_entry,
             role=0.5, indicators=[ST, DON], exit_desc=SL_TO + " + tendencia"),
    Strategy("S21", "GRT-S BX+barrido+tend 1h",  "GRT",  "1h",  -1, "atrstop", s21_entry,
             role=0.5, indicators=[BX, BXREG], exit_desc=SL_TO + " + barrido/tendencia"),
    # --- batch 1 indicadores nuevos: Squeeze Momentum (longs) + Vortex (shorts), validados OOS ---
    Strategy("S22", "ENA-L Squeeze+regimen 1h",  "ENA",  "1h",  +1, "atrstop", s22_entry,
             role=0.5, indicators=[SQZM, BXREG], exit_desc=SL_TO + " + régimen"),
    Strategy("S23", "SAND-S Vortex+regimen 1h",  "SAND", "1h",  -1, "atrstop", s23_entry,
             role=0.5, indicators=[VTX, BXREG], exit_desc=SL_TO + " + régimen"),
    Strategy("S24", "WIF-L Squeeze+regimen 1h",  "WIF",  "1h",  +1, "atrstop", s24_entry,
             role=0.5, indicators=[SQZM, BXREG], exit_desc=SL_TO + " + régimen"),
    Strategy("S25", "SEI-S Vortex+barr+tend 1h", "SEI",  "1h",  -1, "atrstop", s25_entry,
             role=0.5, indicators=[VTX], exit_desc=SL_TO + " + barrido/tendencia"),
    Strategy("S26", "ARB-S Vortex+barr+tend 1h", "ARB",  "1h",  -1, "atrstop", s26_entry,
             role=0.5, indicators=[VTX], exit_desc=SL_TO + " + barrido/tendencia"),
    Strategy("S27", "RUNE-S Vortex+barr+tend 1h","RUNE", "1h",  -1, "atrstop", s27_entry,
             role=0.5, indicators=[VTX], exit_desc=SL_TO + " + barrido/tendencia"),
    Strategy("S28", "AVAX-S Vortex+barrido 1h",  "AVAX", "1h",  -1, "atrstop", s28_entry,
             role=0.5, indicators=[VTX], exit_desc=SL_TO + " + barrido"),
    Strategy("S29", "BNB-L Squeeze+tend+vol 1h", "BNB",  "1h",  +1, "atrstop", s29_entry,
             role=0.5, indicators=[SQZM], exit_desc=SL_TO + " + tendencia/vol"),
    # --- batch 2 reversion a la media (clase nueva, edge fino: 1 representante, peso bajo) ---
    Strategy("S30", "INJ-L BB%b reversión 1h",   "INJ",  "1h",  +1, "meanrev", s30_entry,
             meanrev_up_exit, safety_atr=3.0, timeout_h=24, role=0.5, indicators=[BBR],
             exit_desc="vuelta a SMA20 (media) + SL 3×ATR + timeout 24h"),
    # --- batch 3: ADX/DMI shorts + Squeeze shorts (edge grueso, baja frecuencia) ---
    Strategy("S31", "ARB-S ADX+tend+vol 1h",     "ARB",  "1h",  -1, "atrstop", s31_entry,
             role=0.5, indicators=[ADX], exit_desc=SL_TO + " + tendencia/vol"),
    Strategy("S32", "EGLD-S Squeeze+barrido 1h",  "EGLD", "1h",  -1, "atrstop", s32_entry,
             role=0.5, indicators=[SQZM], exit_desc=SL_TO + " + barrido"),
    Strategy("S33", "DOT-S ADX+barrido 1h",       "DOT",  "1h",  -1, "atrstop", s33_entry,
             role=0.5, indicators=[ADX], exit_desc=SL_TO + " + barrido"),
    Strategy("S34", "HBAR-S ADX+barrido 1h",      "HBAR", "1h",  -1, "atrstop", s34_entry,
             role=0.5, indicators=[ADX], exit_desc=SL_TO + " + barrido"),
    Strategy("S35", "FLOW-S Squeeze+barrido 1h",  "FLOW", "1h",  -1, "atrstop", s35_entry,
             role=0.5, indicators=[SQZM], exit_desc=SL_TO + " + barrido"),
    Strategy("S36", "AVAX-S ADX+barrido 1h",      "AVAX", "1h",  -1, "atrstop", s36_entry,
             role=0.5, indicators=[ADX], exit_desc=SL_TO + " + barrido (corr 0.39 con S28)"),
]

BY_ID = {s.sid: s for s in STRATEGIES}

# Referencia de backtest por estrategia (expectancy en bps de nominal, profit factor).
# Para comparar el desempeno LIVE vs lo validado. Titulares S1-S9 (filtros aplicados a
# S1/S6/S8); suplentes S10-S21 (validados OOS + tuneados). Ver roster-upgrades-validados.
BACKTEST_REF = {
    "S1": (142, 3.69), "S2": (44, 1.66), "S3": (19, 1.60), "S4": (69, 1.38),
    "S5": (45, 1.36), "S6": (199, 2.43), "S7": (26, 1.30), "S8": (63, 1.48),
    "S9": (48, 1.61), "S10": (79, 1.64), "S11": (66, 1.39), "S12": (53, 1.38),
    "S13": (49, 1.35), "S14": (304, 2.67), "S15": (209, 1.91), "S16": (150, 1.69),
    "S17": (145, 1.68), "S18": (121, 1.84), "S19": (100, 1.51), "S20": (97, 1.56),
    "S21": (94, 1.57),
    "S22": (248, 2.11), "S23": (72, 1.46), "S24": (204, 1.79), "S25": (103, 1.54),
    "S26": (74, 1.46), "S27": (84, 1.49), "S28": (71, 1.46), "S29": (55, 1.49),
    "S30": (54, 1.50),
    "S31": (197, 2.13), "S32": (155, 1.93), "S33": (130, 1.97), "S34": (160, 2.31),
    "S35": (126, 1.72), "S36": (224, 2.87),
}

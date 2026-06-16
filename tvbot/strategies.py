"""Las 9 estrategias validadas (CONSOLIDADO.md). Cada una expone:
- entry(df) -> bool en la ULTIMA vela cerrada
- exit_mode: 'atrstop' (SL 2xATR + timeout 48h) o 'flip' (Supertrend contrario)
- flip_exit(df) -> bool (solo para exit_mode='flip')
"""
import numpy as np
from . import indicators as I


def _last(arr):
    return bool(arr[-1])


# --- Smart Money Concepts [LuxAlgo]: Swing Break of Structure (validado cripto, bidireccional) ---
# Edge en el pivote swing de alta significancia (len=50); el motor smc.py reproduce el indicador.
# Import perezoso para no atar el import de tvbot a la raíz del repo (tests/headless).
def _sbos(df, side):
    import smc
    res = smc.compute(df)
    arr = res["sbos_bull"] if side > 0 else res["sbos_bear"]
    return bool(arr[-1])

def _sbos_long(df):
    return _sbos(df, +1)

def _sbos_short(df):
    return _sbos(df, -1)


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
                 role=1.0, safety_atr=None, indicators=(), exit_desc="", timeout_h=None, note="",
                 asset_class="crypto", entry_stop_fn=None, session="24/7"):
        self.sid = sid
        self.name = name
        self.coin = coin
        self.asset_class = asset_class  # 'crypto' | 'stocks' (perp de acción en Binance, p.ej. TSLA/USDT:USDT)
        self.symbol = f"{coin}/USDT:USDT"   # ambos son perps Binance (mismo feed ccxt)
        self.session = session          # '24/7' (cripto/suplentes) | 'us' (titulares: solo sesión US regular)
        self.tf = tf
        self.side = side                # +1 long / -1 short
        self.exit_mode = exit_mode      # 'atrstop' | 'flip' | 'meanrev' | 'orb' (stocks: OR-low + cierre sesión)
        self._entry = entry_fn
        self._flip_exit = flip_exit_fn  # 'flip': ST contrario · 'meanrev': vuelta a la media
        self.entry_stop_fn = entry_stop_fn  # callable(df, entry_px)->stop_px (ORB: OR-low); None -> ATR
        self.role = role                # 1.0 titular / 0.5 suplente (informativo por ahora)
        self.safety_atr = safety_atr    # SL de seguridad (xATR) para exit_mode 'flip'/'meanrev'
        self.indicators = list(indicators)   # nombres COMPLETOS de los indicadores usados
        self.exit_desc = exit_desc
        self.timeout_h = timeout_h      # timeout propio (None -> config.TIMEOUT_HOURS); meanrev=24
        self.note = note                # marca operativa (p.ej. redundancia con otra estrategia)

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

# --- batch 4: volumen/flujo en LONG sobre moneda nueva (ORDI), validados OOS 15/06/2026, role 0.5 ---

def s37_entry(df):      # ORDI 1h L: Chaikin Money Flow cruza a positivo + tendencia + vol
    le, _ = I.cmf(df)
    return _last(le) and _trend(df, +1) and _vol(df)

def s38_entry(df):      # ORDI 1h L: Force Index cruza a positivo + régimen
    le, _ = I.force_index(df)
    return _last(le) and _regime(df, +1)

# --- batch 5: momentum-systems (KST/AO/TSI) sobre monedas NUEVAS, validados OOS 15/06/2026, role 0.5 ---

def s39_entry(df):      # LINK 1h L: KST cruza arriba su señal + barrido<=6
    le, _ = I.kst(df)
    return _last(le) and _sweep(df, +1, 6)

def s40_entry(df):      # NEO 1h L: Awesome Osc cruza cero + barrido<=6 + tendencia
    le, _ = I.awesome_osc(df)
    return _last(le) and _sweep(df, +1, 6) and _trend(df, +1)

def s41_entry(df):      # ICP 1h S: KST cruza abajo su señal + régimen
    _, se = I.kst(df)
    return _last(se) and _regime(df, -1)

def s42_entry(df):      # NEAR 1h S: Awesome Osc cruza cero abajo + barrido<=6
    _, se = I.awesome_osc(df)
    return _last(se) and _sweep(df, -1, 6)

def s43_entry(df):      # ALGO 1h S: TSI cruza abajo su señal + barrido<=6 + tendencia
    _, se = I.tsi(df)
    return _last(se) and _sweep(df, -1, 6) and _trend(df, -1)

def s44_entry(df):      # TAO 1h S: Awesome Osc cruza cero abajo + tendencia + vol
    _, se = I.awesome_osc(df)
    return _last(se) and _trend(df, -1) and _vol(df)

# --- batch 6: Zero Lag Trend Signals (variante ENTRY), monedas nuevas, validados OOS 15/06/2026, role 0.5 ---

def s45_entry(df):      # FIL 1h L: Zero Lag entry alcista + barrido<=6
    le, _ = I.zero_lag_entry(df)
    return _last(le) and _sweep(df, +1, 6)

def s46_entry(df):      # NEO 1h S: Zero Lag entry bajista + barrido<=6 + tendencia
    _, se = I.zero_lag_entry(df)
    return _last(se) and _sweep(df, -1, 6) and _trend(df, -1)

def s47_entry(df):      # STX 1h S: Zero Lag entry bajista + barrido<=6
    _, se = I.zero_lag_entry(df)
    return _last(se) and _sweep(df, -1, 6)

def s48_entry(df):      # CRV 1h S: Zero Lag entry bajista + barrido<=6 + tendencia
    _, se = I.zero_lag_entry(df)
    return _last(se) and _sweep(df, -1, 6) and _trend(df, -1)

# --- challengers descorrelacionados del optimizador (15/06/2026): LONGS robustos OOS, role 0.5 ---

def s49_entry(df):      # TAO 1h L: Squeeze release alcista + tendencia + vol
    le, _ = I.squeeze_momentum(df)
    return _last(le) and _trend(df, +1) and _vol(df)

def s50_entry(df):      # FET 1h L: Squeeze release alcista + tendencia + vol
    le, _ = I.squeeze_momentum(df)
    return _last(le) and _trend(df, +1) and _vol(df)

def s51_entry(df):      # JUP 1h L: Awesome Osc cruza cero + tendencia + vol
    le, _ = I.awesome_osc(df)
    return _last(le) and _trend(df, +1) and _vol(df)

# --- batch 7: S/R High Volume Boxes (ruptura de S/R confirmada por volumen), validados OOS 15/06/2026, role 0.5 ---

def s52_entry(df):      # DOGE 1h L: ruptura de resistencia (volumen) + tendencia
    le, _ = I.sr_volume_break(df)
    return _last(le) and _trend(df, +1)

def s53_entry(df):      # FET 1h L: ruptura de resistencia (volumen) + vol
    le, _ = I.sr_volume_break(df)
    return _last(le) and _vol(df)

def s54_entry(df):      # ARB 1h S: ruptura de soporte (volumen) + régimen
    _, se = I.sr_volume_break(df)
    return _last(se) and _regime(df, -1)

def s55_entry(df):      # ALGO 1h L: ruptura de resistencia (volumen) + tendencia + vol
    le, _ = I.sr_volume_break(df)
    return _last(le) and _trend(df, +1) and _vol(df)

def s56_entry(df):      # INJ 1h L: ruptura de resistencia (volumen) + vol
    le, _ = I.sr_volume_break(df)
    return _last(le) and _vol(df)

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
CMF = "Chaikin Money Flow (volumen)"
FI = "Force Index (Elder, volumen)"
KST = "Know Sure Thing (Pring)"
AO = "Awesome Oscillator (Williams)"
TSI = "True Strength Index"
ZL = "Zero Lag Trend Signals (AlgoAlpha)"
SRB = "S/R High Volume Boxes (ChartPrime)"
SMC = "Smart Money Concepts — Swing Break of Structure (LuxAlgo)"

SL_TO = "SL 2×ATR + timeout 48h"
FLIP = "flip contrario del Supertrend"

STRATEGIES = [
    Strategy("S1", "TRX-L B-Xtrender 1h",      "TRX",  "1h",  +1, "atrstop", s1_entry,
             indicators=[BX], exit_desc=SL_TO),
    Strategy("S2", "TRX-L TrendMeter 1h",      "TRX",  "1h",  +1, "flip",    s2_entry,
             tm_align_red_exit, safety_atr=3.0, indicators=[TM],
             exit_desc="Trend Meter alinea rojo + SL seguridad 3×ATR",
             note="Redundante con S1 (corr PnL 0.83, misma apuesta TRX-L) — observación / candidata a reemplazo"),
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
    # --- batch 4: volumen en LONG sobre moneda nueva ORDI (balance long/short) ---
    Strategy("S37", "ORDI-L CMF+tend+vol 1h",     "ORDI", "1h",  +1, "atrstop", s37_entry,
             role=0.5, indicators=[CMF], exit_desc=SL_TO + " + tendencia/vol"),
    Strategy("S38", "ORDI-L ForceIndex+régimen 1h","ORDI", "1h",  +1, "atrstop", s38_entry,
             role=0.5, indicators=[FI], exit_desc=SL_TO + " + régimen"),
    # --- batch 5: momentum-systems sobre monedas NUEVAS (corr ~0 vs roster y entre sí) ---
    Strategy("S39", "LINK-L KST+barrido 1h",      "LINK", "1h",  +1, "atrstop", s39_entry,
             role=0.5, indicators=[KST], exit_desc=SL_TO + " + barrido"),
    Strategy("S40", "NEO-L AwesomeOsc+barr+tend 1h","NEO", "1h",  +1, "atrstop", s40_entry,
             role=0.5, indicators=[AO], exit_desc=SL_TO + " + barrido/tendencia"),
    Strategy("S41", "ICP-S KST+régimen 1h",       "ICP",  "1h",  -1, "atrstop", s41_entry,
             role=0.5, indicators=[KST], exit_desc=SL_TO + " + régimen"),
    Strategy("S42", "NEAR-S AwesomeOsc+barrido 1h","NEAR", "1h",  -1, "atrstop", s42_entry,
             role=0.5, indicators=[AO], exit_desc=SL_TO + " + barrido"),
    Strategy("S43", "ALGO-S TSI+barr+tend 1h",    "ALGO", "1h",  -1, "atrstop", s43_entry,
             role=0.5, indicators=[TSI], exit_desc=SL_TO + " + barrido/tendencia"),
    Strategy("S44", "TAO-S AwesomeOsc+tend+vol 1h","TAO",  "1h",  -1, "atrstop", s44_entry,
             role=0.5, indicators=[AO], exit_desc=SL_TO + " + tendencia/vol"),
    # --- batch 6: Zero Lag Trend Signals (variante ENTRY) sobre monedas nuevas ---
    Strategy("S45", "FIL-L ZeroLag+barrido 1h",   "FIL",  "1h",  +1, "atrstop", s45_entry,
             role=0.5, indicators=[ZL], exit_desc=SL_TO + " + barrido"),
    Strategy("S46", "NEO-S ZeroLag+barr+tend 1h",  "NEO",  "1h",  -1, "atrstop", s46_entry,
             role=0.5, indicators=[ZL], exit_desc=SL_TO + " + barrido/tendencia"),
    Strategy("S47", "STX-S ZeroLag+barrido 1h",   "STX",  "1h",  -1, "atrstop", s47_entry,
             role=0.5, indicators=[ZL], exit_desc=SL_TO + " + barrido"),
    Strategy("S48", "CRV-S ZeroLag+barr+tend 1h",  "CRV",  "1h",  -1, "atrstop", s48_entry,
             role=0.5, indicators=[ZL], exit_desc=SL_TO + " + barrido/tendencia"),
    # --- challengers del optimizador (longs robustos OOS, corr ~0; corrigen el sesgo de antigüedad) ---
    Strategy("S49", "TAO-L Squeeze+tend+vol 1h",  "TAO",  "1h",  +1, "atrstop", s49_entry,
             role=0.5, indicators=[SQZM], exit_desc=SL_TO + " + tendencia/vol"),
    Strategy("S50", "FET-L Squeeze+tend+vol 1h",  "FET",  "1h",  +1, "atrstop", s50_entry,
             role=0.5, indicators=[SQZM], exit_desc=SL_TO + " + tendencia/vol"),
    Strategy("S51", "JUP-L AwesomeOsc+tend+vol 1h","JUP",  "1h",  +1, "atrstop", s51_entry,
             role=0.5, indicators=[AO], exit_desc=SL_TO + " + tendencia/vol"),
    # --- batch 7: S/R High Volume Boxes (ruptura S/R + volumen) ---
    Strategy("S52", "DOGE-L SRBreak+tend 1h",     "DOGE", "1h",  +1, "atrstop", s52_entry,
             role=0.5, indicators=[SRB], exit_desc=SL_TO + " + tendencia"),
    Strategy("S53", "FET-L SRBreak+vol 1h",       "FET",  "1h",  +1, "atrstop", s53_entry,
             role=0.5, indicators=[SRB], exit_desc=SL_TO + " + vol"),
    Strategy("S54", "ARB-S SRBreak+régimen 1h",   "ARB",  "1h",  -1, "atrstop", s54_entry,
             role=0.5, indicators=[SRB], exit_desc=SL_TO + " + régimen"),
    Strategy("S55", "ALGO-L SRBreak+tend+vol 1h", "ALGO", "1h",  +1, "atrstop", s55_entry,
             role=0.5, indicators=[SRB], exit_desc=SL_TO + " + tendencia/vol"),
    Strategy("S56", "INJ-L SRBreak+vol 1h",       "INJ",  "1h",  +1, "atrstop", s56_entry,
             role=0.5, indicators=[SRB], exit_desc=SL_TO + " + vol"),
    # --- batch 8: SMC Swing Break of Structure (LuxAlgo) — validado cripto (anti-beta + OOS Sharpe
    #     1.47, PSR 99%; ambos lados ganan). Bidireccional, sin filtros (confluencia no aporta).
    #     Subset robusto IS+OOS, descorrelacionado (corr media +0.07). exit atrstop = lo backtesteado. ---
    Strategy("S57", "SUI-L SMC SwingBOS 1h",  "SUI",  "1h",  +1, "atrstop", _sbos_long,
             role=0.5, indicators=[SMC], exit_desc=SL_TO),
    Strategy("S58", "ARB-S SMC SwingBOS 1h",  "ARB",  "1h",  -1, "atrstop", _sbos_short,
             role=0.5, indicators=[SMC], exit_desc=SL_TO),
    Strategy("S59", "XRP-L SMC SwingBOS 1h",  "XRP",  "1h",  +1, "atrstop", _sbos_long,
             role=0.5, indicators=[SMC], exit_desc=SL_TO),
    Strategy("S60", "DOGE-L SMC SwingBOS 1h", "DOGE", "1h",  +1, "atrstop", _sbos_long,
             role=0.5, indicators=[SMC], exit_desc=SL_TO),
    Strategy("S61", "FET-S SMC SwingBOS 1h",  "FET",  "1h",  -1, "atrstop", _sbos_short,
             role=0.5, indicators=[SMC], exit_desc=SL_TO),
    Strategy("S62", "NEAR-S SMC SwingBOS 1h", "NEAR", "1h",  -1, "atrstop", _sbos_short,
             role=0.5, indicators=[SMC], exit_desc=SL_TO),
    Strategy("S63", "OP-S SMC SwingBOS 1h",   "OP",   "1h",  -1, "atrstop", _sbos_short,
             role=0.5, indicators=[SMC], exit_desc=SL_TO),
    Strategy("S64", "DOT-L SMC SwingBOS 1h",  "DOT",  "1h",  +1, "atrstop", _sbos_long,
             role=0.5, indicators=[SMC], exit_desc=SL_TO),
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
    "S37": (151, 1.46), "S38": (115, 1.47),
    "S39": (89, 1.54), "S40": (78, 1.53), "S41": (74, 1.46), "S42": (116, 1.80),
    "S43": (77, 1.54), "S44": (103, 1.45),
    "S45": (190, 2.17), "S46": (225, 3.19), "S47": (98, 1.52), "S48": (106, 1.51),
    "S49": (106, 1.46), "S50": (121, 1.44), "S51": (137, 1.52),
    "S52": (171, 1.98), "S53": (219, 1.85), "S54": (160, 1.96), "S55": (109, 1.59), "S56": (99, 1.43),
    # batch 8 SMC Swing BOS (exp bps, PF — del backtest de selección sBOS)
    "S57": (231, 2.30), "S58": (214, 2.41), "S59": (184, 2.17), "S60": (158, 1.95),
    "S61": (144, 1.85), "S62": (138, 1.84), "S63": (85, 1.37), "S64": (64, 1.33),
}

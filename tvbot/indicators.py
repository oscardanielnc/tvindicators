"""Replicas Pine validadas en backtest (identicas a sweep1-3). NO modificar sin re-validar."""
import numpy as np
import pandas as pd


def pine_ema(s, n): return s.ewm(span=n, adjust=False).mean()
def pine_sma(s, n): return s.rolling(n).mean()
def pine_rma(s, n): return s.ewm(alpha=1 / n, adjust=False).mean()


def pine_rsi(s, n):
    d = s.diff()
    return 100 - 100 / (1 + pine_rma(d.clip(lower=0), n) / pine_rma((-d).clip(lower=0), n))


def t3(s, n, b=0.7):
    e1 = pine_ema(s, n); e2 = pine_ema(e1, n); e3 = pine_ema(e2, n)
    e4 = pine_ema(e3, n); e5 = pine_ema(e4, n); e6 = pine_ema(e5, n)
    return -b**3*e6 + (3*b**2+3*b**3)*e5 + (-6*b**2-3*b-3*b**3)*e4 + (1+3*b+b**3+3*b**2)*e3


def tema(s, n):
    e1 = pine_ema(s, n); e2 = pine_ema(e1, n); e3 = pine_ema(e2, n)
    return 3 * (e1 - e2) + e3


def atr14(df):
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    return pine_rma(tr, 14)


def dch_trend(c, h, l, n):
    hh = h.rolling(n).max().shift(1); ll = l.rolling(n).min().shift(1)
    raw = np.where(c > hh, 1.0, np.where(c < ll, -1.0, np.nan))
    return pd.Series(raw, index=c.index).ffill().fillna(0.0).values


def ribbon_strength(c, h, l, dlen=20):
    """(strength_long, strength_short) 0..10: sub-trends Donchian alineados."""
    subs = np.stack([dch_trend(c, h, l, dlen - k) for k in range(10)])
    return (subs == 1).sum(axis=0), (subs == -1).sum(axis=0)


def supertrend_dir(h, l, c, period=10, factor=3.0):
    """+1 uptrend / -1 downtrend."""
    hl2 = (h + l) / 2
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = pine_rma(tr, period).values
    up = hl2.values + factor * atr; dn = hl2.values - factor * atr
    cl = c.values; n = len(cl)
    d = np.ones(n); fu, fd = up.copy(), dn.copy()
    for i in range(1, n):
        fu[i] = up[i] if (up[i] < fu[i-1] or cl[i-1] > fu[i-1]) else fu[i-1]
        fd[i] = dn[i] if (dn[i] > fd[i-1] or cl[i-1] < fd[i-1]) else fd[i-1]
        d[i] = (-1 if cl[i] < fd[i] else 1) if d[i-1] == 1 else (1 if cl[i] > fu[i] else -1)
    return d


def hacolt(o, h, l, c, length=55, ema_len=60, csf=1.1):
    """Vervoort HACOLT (LazyBear): estados +1 / 0 / -1."""
    ohlc4 = (o + h + l + c) / 4
    n = len(c)
    haOpen = np.empty(n); haOpen[0] = ohlc4.iloc[0]
    o4 = ohlc4.values
    for i in range(1, n):
        haOpen[i] = (haOpen[i-1] + o4[i]) / 2
    haClose = (haOpen + np.maximum(h.values, haOpen) + np.minimum(l.values, haOpen) + o4) / 4
    haC = pd.Series(haClose, index=c.index)
    thaC = tema(haC, length)
    thl2 = tema((h + l) / 2, length)
    haSmooth = 2 * thaC - tema(thaC, length)
    hlSmooth = 2 * thl2 - tema(thl2, length)
    cl, op_, hi, lo = c.values, o.values, h.values, l.values
    shortCandle = np.abs(cl - op_) < (hi - lo) * csf
    prev = lambda a: np.roll(a, 1)
    haUp = haClose >= haOpen
    keepn1 = (haUp & prev(haUp)) | (cl >= haClose) | (hi > prev(hi)) | (lo > prev(lo)) | (hlSmooth.values >= haSmooth.values)
    keepall1 = keepn1 | (prev(keepn1) & (cl >= op_)) | (cl >= prev(cl))
    keep13 = shortCandle & (hi >= prev(lo))
    utr = keepall1 | (prev(keepall1) & keep13)
    haDn = haClose < haOpen
    keepn2 = (haDn & prev(haDn)) | (hlSmooth.values < haSmooth.values)
    keep23 = shortCandle & (lo <= prev(hi))
    keepall2 = keepn2 | (prev(keepn2) & (cl < op_)) | (cl < prev(cl))
    dtr = keepall2 | (prev(keepall2) & keep23)
    upw = (~dtr) & prev(dtr) & utr
    dnw = (~utr) & prev(utr) & dtr
    upwOff = np.zeros(n, bool)
    for i in range(1, n):
        upwOff[i] = upw[i] if upw[i] != dnw[i] else upwOff[i-1]
    buySig = upw | ((~dnw) & upwOff)
    ltSell = cl < pine_ema(c, ema_len).values
    neutral = np.zeros(n, bool)
    for i in range(1, n):
        neutral[i] = buySig[i] or (False if ltSell[i] else neutral[i-1])
    return np.where(buySig, 1, np.where(neutral, 0, -1))


# --- bloques de senal compuestos ---

def bx_parts(c):
    """B-Xtrender: (circulo_verde&T3<0, circulo_rojo&T3>0, regimen>0, regimen<0)."""
    osc = pine_rsi(pine_ema(c, 5) - pine_ema(c, 20), 15) - 50
    reg = pine_rsi(pine_ema(c, 20), 15) - 50
    ma = t3(osc, 5)
    green = ((ma > ma.shift(1)) & (ma.shift(1) < ma.shift(2))).values
    red = ((ma < ma.shift(1)) & (ma.shift(1) > ma.shift(2))).values
    return (green & (ma < 0).values, red & (ma > 0).values,
            (reg > 0).values, (reg < 0).values)


def tm_align_edge(c):
    """Trend Meter: los 3 medidores se alinean verdes (evento)."""
    fmacd = pine_ema(c, 8) - pine_ema(c, 21)
    fhist = (fmacd - pine_ema(fmacd, 5)) > 0
    pos = (fhist & (pine_rsi(c, 13) > 50) & (pine_rsi(c, 5) > 50)).values
    return pos & ~np.roll(pos, 1)


def st_flips(df, period=10, factor=3.0):
    """(flip_up, flip_dn, dir) del Supertrend."""
    sd = supertrend_dir(df["high"], df["low"], df["close"], period, factor)
    sdp = np.roll(sd, 1); sdp[0] = sd[0]
    return (sd == 1) & (sdp == -1), (sd == -1) & (sdp == 1), sd


# --- filtros de conviccion (validados OOS; paridad con pulir_filtros/validar_combos) ---

def ema_trend_ok(c, side, n=200):
    """Precio del lado correcto de la EMA(n). Array bool."""
    ema = pine_ema(c, n).values
    return (c.values > ema) if side > 0 else (c.values < ema)


def vol_ok(df, win=500):
    """ATR% por encima de su mediana movil (evita chop muerto). Array bool."""
    atrpct = (atr14(df) / df["close"]).values
    med = pd.Series(atrpct).rolling(win, min_periods=100).median().values
    return atrpct >= med


def liquidity_sweeps(df, W=5, maxage=200, warm=300):
    """Barridos de liquidez: (sweep_long, sweep_short). Identico a poc_sweep_filter."""
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    ph = (df["high"] == df["high"].rolling(2*W+1, center=True).max()).values
    pl = (df["low"] == df["low"].rolling(2*W+1, center=True).min()).values
    sL = np.zeros(n, bool); sS = np.zeros(n, bool)
    last_sh = last_sl = np.nan; sh_age = sl_age = 10**9; sh_used = sl_used = True
    for t in range(min(warm, max(W+1, n-1)), n):
        j = t - W
        if ph[j]: last_sh, sh_age, sh_used = h[j], 0, False
        if pl[j]: last_sl, sl_age, sl_used = l[j], 0, False
        sh_age += 1; sl_age += 1
        if (not sh_used) and sh_age <= maxage and not np.isnan(last_sh) and h[t] > last_sh and c[t] < last_sh:
            sS[t] = True; sh_used = True
        if (not sl_used) and sl_age <= maxage and not np.isnan(last_sl) and l[t] < last_sl and c[t] > last_sl:
            sL[t] = True; sl_used = True
    return sL, sS


def sweep_recent(sig, F):
    """True en i si hubo barrido en [i-F+1, i]. Identico a recent() del PoC."""
    return (pd.Series(sig.astype(int)).rolling(F, min_periods=1).max() > 0).values


# --- indicadores nuevos batch 1 (validados OOS 15/06/2026; ver indicadores_nuevos_VEREDICTO.md) ---

def _true_range(df):
    h, l, pc = df["high"], df["low"], df["close"].shift(1)
    return pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)


def _linreg_end(y, n):
    """Extremo (offset 0) de la regresion lineal sobre las ultimas n barras = Pine linreg(y,n,0).
    Vectorizado con sumas rolling (k=0..n-1 dentro de la ventana)."""
    y = pd.Series(np.asarray(y, dtype=float)).reset_index(drop=True)
    t = np.arange(len(y), dtype=float)
    Sy = y.rolling(n).sum()
    Spy = (pd.Series(t) * y).rolling(n).sum()
    Sky = Spy - (t - (n - 1)) * Sy
    Sk = n * (n - 1) / 2.0
    Skk = (n - 1) * n * (2 * n - 1) / 6.0
    slope = (n * Sky - Sk * Sy) / (n * Skk - Sk * Sk)
    intercept = (Sy - slope * Sk) / n
    return (intercept + slope * (n - 1)).values


def squeeze_momentum(df, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5):
    """Squeeze Momentum (LazyBear): (long_event, short_event).
    Senal = RELEASE del squeeze (BB-dentro-de-KC termina ESTA barra) en la direccion del
    momentum val=linreg(close - avg(avg(hh,ll), sma(close))). std poblacional (ddof=0)."""
    c, h, l = df["close"], df["high"], df["low"]
    basis = c.rolling(bb_len).mean(); dev = bb_mult * c.rolling(bb_len).std(ddof=0)
    upBB, loBB = basis + dev, basis - dev
    ma = c.rolling(kc_len).mean(); rangema = _true_range(df).rolling(kc_len).mean()
    upKC, loKC = ma + rangema * kc_mult, ma - rangema * kc_mult
    sqz_on = (loBB > loKC) & (upBB < upKC)
    hh = h.rolling(kc_len).max(); ll = l.rolling(kc_len).min()
    src = c - (((hh + ll) / 2.0) + c.rolling(kc_len).mean()) / 2.0
    val = _linreg_end(src, kc_len)
    release = sqz_on.shift(1).fillna(False).values & (~sqz_on.values)
    return release & (val > 0), release & (val < 0)


def vortex(df, n=14):
    """Vortex (VI+/VI-): (long_event, short_event) = cruce de VI+ sobre/bajo VI-."""
    h, l, c = df["high"], df["low"], df["close"]
    tr = _true_range(df).rolling(n).sum()
    vip = ((h - l.shift(1)).abs().rolling(n).sum() / tr).values
    vim = ((l - h.shift(1)).abs().rolling(n).sum() / tr).values
    pvip, pvim = np.roll(vip, 1), np.roll(vim, 1)
    up = (vip > vim) & (pvip <= pvim); dn = (vip < vim) & (pvip >= pvim)
    up[0] = dn[0] = False
    return up, dn


# --- reversion a la media (batch 2; motor de salida meanrev). std poblacional (ddof=0) ---

def bb_extreme_event(c, side, n=20, k=2.0):
    """Evento: close cruza FUERA de la banda de Bollinger (long=inferior, short=superior)."""
    basis = c.rolling(n).mean(); dev = k * c.rolling(n).std(ddof=0)
    cond = (c < (basis - dev)) if side > 0 else (c > (basis + dev))
    return (cond & ~cond.shift(1).fillna(False)).values


def sma_revert(c, side, n=20):
    """Salida de reversion: close vuelve a la media SMA(n) (long: close>=SMA; short: close<=SMA)."""
    s = c.rolling(n).mean()
    return (c >= s).values if side > 0 else (c <= s).values


def sma_trend_ok(c, side, n=200):
    """Filtro de tendencia por SMA(n) (paridad con el sweep de reversion). Array bool."""
    s = c.rolling(n).mean().values
    return (c.values > s) if side > 0 else (c.values < s)


# --- batch 3 (validado OOS 15/06/2026; ver batch3_VEREDICTO.md) ---

def adx_dmi(df, n=14, thr=25):
    """ADX/DMI (Wilder). (long_event, short_event) = cruce DI+/DI- con ADX>umbral."""
    h, l, c = df["high"], df["low"], df["close"]
    up = h.diff(); dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = pine_rma(tr, n)
    pdi = 100 * pine_rma(pd.Series(plus_dm, index=c.index), n) / atr
    mdi = 100 * pine_rma(pd.Series(minus_dm, index=c.index), n) / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = pine_rma(dx.fillna(0), n).values
    p, m = pdi.values, mdi.values
    pc, mc = np.roll(p, 1), np.roll(m, 1)
    longe = (p > m) & (pc <= mc) & (adx > thr)
    shorte = (m > p) & (mc <= pc) & (adx > thr)
    longe[0] = shorte[0] = False
    return longe, shorte


# --- batch 4 (volumen/flujo; validado OOS 15/06/2026, ver batch4_VEREDICTO.md) ---

def cmf(df, n=20):
    """Chaikin Money Flow. (long_event, short_event) = cruce de cero (acum/distribución)."""
    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]
    rng = (h - l).replace(0, np.nan)
    mfv = (((c - l) - (h - c)) / rng).fillna(0) * v
    val = (mfv.rolling(n).sum() / v.rolling(n).sum().replace(0, np.nan)).values
    pos = val > 0
    lo = pos & ~np.roll(pos, 1); sh = (~pos) & np.roll(pos, 1)
    lo[0] = sh[0] = False
    return lo, sh


def force_index(df, n=13):
    """Force Index (Elder) suavizado con EMA. (long_event, short_event) = cruce de cero."""
    c, v = df["close"], df["volume"]
    fi = ((c - c.shift(1)) * v).ewm(span=n, adjust=False).mean().values
    pos = fi > 0
    l = pos & ~np.roll(pos, 1); s = (~pos) & np.roll(pos, 1)
    l[0] = s[0] = False
    return l, s

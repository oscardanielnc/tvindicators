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

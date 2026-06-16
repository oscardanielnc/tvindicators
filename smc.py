"""Port fiel a Python del motor Smart Money Concepts [LuxAlgo] (CC BY-NC-SA 4.0, © LuxAlgo).
Reproduce: detección de legs/pivots, estructura interna (len=5) y swing (len=50) con eventos
BOS/CHoCH, order blocks (filtro de volatilidad ATR200), fair value gaps, y trailing extremes para
zonas premium/discount. Trabaja sobre cualquier df OHLC (índice temporal). Sin look-ahead: los
eventos se emiten en la barra donde cierran (igual que el indicador en barras confirmadas).

Devuelve un dict de arrays alineados a df + listas de order blocks y FVGs. Uso: import smc.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

BULL, BEAR = 1, -1


def _atr(df, n=200):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().values        # RMA ≈ ta.atr


def _leg(high, low, size):
    """leg LuxAlgo: 0=bearish,1=bullish. Cambia cuando high[size]>highest(size) o low[size]<lowest(size)."""
    n = len(high)
    roll_hi = pd.Series(high).rolling(size).max().values
    roll_lo = pd.Series(low).rolling(size).min().values
    hs = pd.Series(high).shift(size).values
    ls = pd.Series(low).shift(size).values
    new_hi = hs > roll_hi          # nuevo swing HIGH detectado en la barra i-size -> empieza leg bajista
    new_lo = ls < roll_lo          # nuevo swing LOW -> empieza leg alcista
    leg = np.zeros(n, dtype=np.int8)
    cur = 0
    for i in range(n):
        if new_hi[i]:
            cur = 0
        elif new_lo[i]:
            cur = 1
        leg[i] = cur
    return leg, new_hi, new_lo


def compute(df, swing_len=50, internal_len=5, confluence=False):
    n = len(df)
    high, low, close, open_ = (df[c].values for c in ("high", "low", "close", "open"))
    atr200 = _atr(df, 200)
    vol = atr200
    high_vol = (high - low) >= 2 * vol
    parsedHigh = np.where(high_vol, low, high)
    parsedLow = np.where(high_vol, high, low)

    # legs / pivots para swing e internal
    leg_s, _, _ = _leg(high, low, swing_len)
    leg_i, _, _ = _leg(high, low, internal_len)
    chg_s = np.concatenate([[0], np.diff(leg_s)])      # +1 = pivot low (leg ->bull), -1 = pivot high
    chg_i = np.concatenate([[0], np.diff(leg_i)])

    # estado
    sH_lvl = sL_lvl = np.nan; sH_idx = sL_idx = -1; sH_cr = sL_cr = False; sTrend = 0
    iH_lvl = iL_lvl = np.nan; iH_idx = iL_idx = -1; iH_cr = iL_cr = False; iTrend = 0
    tTop = -np.inf; tBot = np.inf

    out = {k: np.zeros(n, bool) for k in
           ("ibos_bull", "ibos_bear", "ichoch_bull", "ichoch_bear",
            "sbos_bull", "sbos_bear", "schoch_bull", "schoch_bear",
            "fvg_bull", "fvg_bear")}
    iTrend_a = np.zeros(n, np.int8); sTrend_a = np.zeros(n, np.int8)
    equil = np.full(n, np.nan); disc = np.zeros(n, bool); prem = np.zeros(n, bool)
    obs = []      # order blocks: dict(idx_created, high, low, bias, internal, active, mitig_idx)
    fvgs = []     # fair value gaps: dict(idx, top, bottom, bias)

    def store_ob(piv_idx, bias, internal):
        if piv_idx < 0 or piv_idx >= i:
            return
        sl = slice(piv_idx, i + 1)
        if bias == BEAR:
            seg = parsedHigh[sl]; k = piv_idx + int(np.argmax(seg))
        else:
            seg = parsedLow[sl]; k = piv_idx + int(np.argmin(seg))
        obs.append(dict(idx=k, created=i, high=parsedHigh[k], low=parsedLow[k],
                        bias=bias, internal=internal, active=True, mitig=None))

    for i in range(n):
        # --- trailing extremes (para zonas) ---
        # update con swing pivots primero (abajo), aquí extendemos con high/low
        # --- pivots swing ---
        if chg_s[i] == 1 and i - swing_len >= 0:          # pivot LOW
            sL_lvl = low[i - swing_len]; sL_idx = i - swing_len; sL_cr = False
            tBot = sL_lvl
        elif chg_s[i] == -1 and i - swing_len >= 0:       # pivot HIGH
            sH_lvl = high[i - swing_len]; sH_idx = i - swing_len; sH_cr = False
            tTop = sH_lvl
        # --- pivots internal ---
        if chg_i[i] == 1 and i - internal_len >= 0:
            iL_lvl = low[i - internal_len]; iL_idx = i - internal_len; iL_cr = False
        elif chg_i[i] == -1 and i - internal_len >= 0:
            iH_lvl = high[i - internal_len]; iH_idx = i - internal_len; iH_cr = False

        # trailing extremes extend
        tTop = max(tTop, high[i]); tBot = min(tBot, low[i])
        if np.isfinite(tTop) and np.isfinite(tBot):
            eq = 0.5 * (tTop + tBot); equil[i] = eq
            disc[i] = close[i] < (0.525 * tBot + 0.475 * tTop)     # zona discount (mitad inferior+)
            prem[i] = close[i] > (0.525 * tTop + 0.475 * tBot)

        bull_bar = bear_bar = True
        if confluence:
            bull_bar = (high[i] - max(close[i], open_[i])) > min(close[i], open_[i]) - low[i]
            bear_bar = (high[i] - max(close[i], open_[i])) < min(close[i], open_[i]) - low[i]

        # --- estructura INTERNAL (primero, como el indicador) ---
        if not np.isnan(iH_lvl) and close[i] > iH_lvl and close[i - 1] <= iH_lvl and not iH_cr \
                and (iH_lvl != sH_lvl) and bull_bar:
            if iTrend == BEAR:
                out["ichoch_bull"][i] = True
            else:
                out["ibos_bull"][i] = True
            iH_cr = True; iTrend = BULL; store_ob(iH_idx, BULL, True)
        if not np.isnan(iL_lvl) and close[i] < iL_lvl and close[i - 1] >= iL_lvl and not iL_cr \
                and (iL_lvl != sL_lvl) and bear_bar:
            if iTrend == BULL:
                out["ichoch_bear"][i] = True
            else:
                out["ibos_bear"][i] = True
            iL_cr = True; iTrend = BEAR; store_ob(iL_idx, BEAR, True)

        # --- estructura SWING ---
        if not np.isnan(sH_lvl) and close[i] > sH_lvl and close[i - 1] <= sH_lvl and not sH_cr:
            if sTrend == BEAR:
                out["schoch_bull"][i] = True
            else:
                out["sbos_bull"][i] = True
            sH_cr = True; sTrend = BULL; store_ob(sH_idx, BULL, False)
        if not np.isnan(sL_lvl) and close[i] < sL_lvl and close[i - 1] >= sL_lvl and not sL_cr:
            if sTrend == BULL:
                out["schoch_bear"][i] = True
            else:
                out["sbos_bear"][i] = True
            sL_cr = True; sTrend = BEAR; store_ob(sL_idx, BEAR, False)

        # --- FVG (3 barras, timeframe del chart) ---
        if i >= 2:
            delta = (close[i - 1] - open_[i - 1]) / (open_[i - 1] * 100) if open_[i - 1] else 0
            if low[i] > high[i - 2] and close[i - 1] > high[i - 2] and delta > 0:
                out["fvg_bull"][i] = True
                fvgs.append(dict(idx=i, top=low[i], bottom=high[i - 2], bias=BULL))
            elif high[i] < low[i - 2] and close[i - 1] < low[i - 2] and -delta > 0:
                out["fvg_bear"][i] = True
                fvgs.append(dict(idx=i, top=low[i - 2], bottom=high[i], bias=BEAR))

        iTrend_a[i] = iTrend; sTrend_a[i] = sTrend

    out.update(itrend=iTrend_a, strend=sTrend_a, equil=equil, discount=disc, premium=prem,
               obs=obs, fvgs=fvgs, parsedHigh=parsedHigh, parsedLow=parsedLow)
    return out

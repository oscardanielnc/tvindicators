# PoC: Volume Profile (POC / VAH / VAL) — © kv4coins, decodificado a Python.
# Pregunta: ¿el precio rebota de forma PREDECIBLE en los bordes del Value Area?
# Tesis del usuario: VAL = soporte (rebote arriba), VAH = resistencia (rebote abajo).
#
# Metodologia honesta, sin look-ahead:
#   - VP en barra i se calcula SOLO con velas [i-lookback, i-1] (excluye la actual).
#   - Condicion de senal usa close[i]; ejecucion al open[i+1].
#   - Dos pruebas:
#       A) Calidad de senal: retorno FORWARD condicionado vs baseline (sin costos, mide edge crudo).
#       B) Regla operada mean-reversion neta de costos maker (ida+vuelta).
import numpy as np
import pandas as pd

COINS = ["TRX", "SUI", "LTC", "XRP", "AVAX", "ETH", "BTC"]
TF = "1h"
DATA = "C:/Users/LENOVO/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/{tf}.parquet"

LOOKBACK = 240        # 10 dias en 1h
NBINS = 80
VA_PCT = 68
STEP = 4              # recalcula VP cada 4 velas y forward-fill (VP es lento)
MAKER = 0.0002
COST_RT = 2 * MAKER   # 0.04% ida+vuelta (maker, como el backtest validado)
FWD = [6, 24, 48]     # horizontes forward (h) para test de calidad
WARM = LOOKBACK + 5


def vp_levels(low, high, vol, pmin, pmax):
    """POC, VAH, VAL de una ventana. Volumen repartido en [low,high] de cada vela
    via difference-array (vectorizado)."""
    if pmax <= pmin:
        return np.nan, np.nan, np.nan
    bw = (pmax - pmin) / NBINS
    lo_idx = np.clip(((low - pmin) / bw).astype(int), 0, NBINS - 1)
    hi_idx = np.clip(((high - pmin) / bw).astype(int), 0, NBINS - 1)
    span = hi_idx - lo_idx + 1
    w = vol / span
    delta = np.zeros(NBINS + 1)
    np.add.at(delta, lo_idx, w)
    np.add.at(delta, hi_idx + 1, -w)
    prof = np.cumsum(delta)[:NBINS]
    if prof.sum() <= 0:
        return np.nan, np.nan, np.nan
    poc_i = int(np.argmax(prof))
    # value area: expandir desde POC al lado de mayor volumen hasta VA_PCT%
    target = prof.sum() * VA_PCT / 100
    lo, hi, acc = poc_i, poc_i, prof[poc_i]
    while acc < target:
        up = prof[hi + 1] if hi < NBINS - 1 else -1
        dn = prof[lo - 1] if lo > 0 else -1
        if up < 0 and dn < 0:
            break
        if up >= dn:
            hi += 1; acc += prof[hi]
        else:
            lo -= 1; acc += prof[lo]
    price = lambda i: pmin + bw * (i + 0.5)
    return price(poc_i), price(hi), price(lo)


def compute_vp_series(df):
    low, high, vol = df["low"].values, df["high"].values, df["volume"].values
    n = len(df)
    poc = np.full(n, np.nan); vah = np.full(n, np.nan); val = np.full(n, np.nan)
    last = (np.nan, np.nan, np.nan)
    for i in range(WARM, n):
        if (i - WARM) % STEP == 0:
            sl = slice(i - LOOKBACK, i)              # [i-lookback, i-1]
            w_low, w_high = low[sl], high[sl]
            last = vp_levels(w_low, w_high, vol[sl], w_low.min(), w_high.max())
        poc[i], vah[i], val[i] = last
    return poc, vah, val


def fwd_ret(close, k):
    c = close.values
    out = np.full(len(c), np.nan)
    out[:-k] = c[k:] / c[:-k] - 1
    return out


def quality_test(df, poc, vah, val):
    """Retorno forward medio condicionado vs baseline. Edge>0 confirma la tesis."""
    close = df["close"]
    rows = []
    at_val = (close.values <= val)          # precio en/bajo borde inferior del VA
    at_vah = (close.values >= vah)          # precio en/sobre borde superior del VA
    for k in FWD:
        fr = fwd_ret(close, k)
        base = np.nanmean(fr[WARM:])
        # LONG thesis: tras tocar VAL, fwd deberia ser > baseline (rebote arriba)
        mL = at_val & ~np.isnan(fr); retL = np.nanmean(fr[mL])
        # SHORT thesis: tras tocar VAH, fwd deberia ser < baseline (rebote abajo)
        mS = at_vah & ~np.isnan(fr); retS = np.nanmean(fr[mS])
        rows.append(dict(k=f"{k}h", base=f"{base*100:+.3f}",
                         VAL_long=f"{retL*100:+.3f}", edgeL=f"{(retL-base)*100:+.3f}", nL=int(mL.sum()),
                         VAH_short=f"{retS*100:+.3f}", edgeS=f"{(base-retS)*100:+.3f}", nS=int(mS.sum())))
    return pd.DataFrame(rows)


def traded_rule(df, poc, vah, val, side):
    """Mean-reversion operada, neta de costos. side=+1 long en VAL->target POC; -1 short en VAH->POC."""
    op, close = df["open"].values, df["close"].values
    n = len(df); idx = df.index
    trades = []; pos = 0; epx = ei = None
    for i in range(WARM, n - 1):
        if np.isnan(val[i]):
            continue
        if pos == side:
            # salida: alcanza POC (target) o timeout 48 velas
            hit = (close[i] >= poc[i]) if side == 1 else (close[i] <= poc[i])
            if hit or (i - ei) >= 48:
                r = side * (op[i + 1] / epx - 1) - COST_RT
                trades.append((idx[ei], idx[i + 1], side * r, i + 1 - ei)); pos = 0
        if pos == 0:
            trig = (close[i] <= val[i]) if side == 1 else (close[i] >= vah[i])
            if trig:
                pos, epx, ei = side, op[i + 1], i
    if not trades:
        return None
    tr = pd.DataFrame(trades, columns=["t_in", "t_out", "ret", "bars"])
    return tr


def metrics(tr, label):
    if tr is None or len(tr) == 0:
        return dict(variante=label, trades=0)
    r = tr["ret"]; eq = (1 + r).cumprod()
    wins, losses = r[r > 0], r[r <= 0]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf
    return dict(variante=label, trades=len(tr), winrate=f"{(r > 0).mean():.1%}",
                PF=round(pf, 2), expect_bps=round(r.mean() * 1e4, 1),
                total_pct=round((eq.iloc[-1] - 1) * 100, 1), hold_h=round(tr["bars"].mean(), 1))


# ---------- run ----------
for coin in COINS:
    df = pd.read_parquet(DATA.format(c=coin, tf=TF))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("dt").sort_index()
    poc, vah, val = compute_vp_series(df)
    print(f"\n{'='*78}\n{coin} {TF}  ({len(df)} velas, {df.index[0].date()}->{df.index[-1].date()})")
    print("--- A) calidad de senal: retorno forward medio (%), edge>0 = tesis se cumple ---")
    print(quality_test(df, poc, vah, val).to_string(index=False))
    print("--- B) regla operada (neta costos maker 0.04% RT, target=POC, timeout 48h) ---")
    rows = [metrics(traded_rule(df, poc, vah, val, +1), "VAL->POC long"),
            metrics(traded_rule(df, poc, vah, val, -1), "VAH->POC short")]
    print(pd.DataFrame(rows).to_string(index=False))

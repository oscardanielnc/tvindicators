# PoC-L1: Barridos de liquidez (stop hunts) desde estructura de precio.
# Tesis ICT: stops retail se acumulan sobre swing highs (buy-side) y bajo swing lows
# (sell-side). El precio "barre" el pool (mecha mas alla) y REVIERTE.
#   - sweep LONG  = el precio rompe un swing low previo pero CIERRA de vuelta arriba -> rebote up
#   - sweep SHORT = el precio rompe un swing high previo pero CIERRA de vuelta abajo -> caida
#
# Sin look-ahead: pivote confirmado W barras despues; barrido usa OHLC de la barra t;
# ejecucion al open[t+1]. Costos maker 0.04% ida+vuelta. Mismo metodo que poc_volprofile.
import numpy as np
import pandas as pd

COINS = ["TRX", "SUI", "LTC", "XRP", "AVAX", "ETH", "BTC"]
TF = "1h"
DATA = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/{tf}.parquet"

W = 5                 # ancho del pivote (swing high/low = max/min de [i-W, i+W])
MAXAGE = 200          # solo pools formados en las ultimas 200 velas
MAKER = 0.0002
COST_RT = 2 * MAKER
FWD = [6, 24, 48]     # horizontes forward (h)
HOLD = 24             # regla operada: salir tras 24 velas
WARM = 300


def pivots(df):
    """is_pivot_high/low confirmados (centrados). high[i] es el max de [i-W,i+W]."""
    h, l = df["high"], df["low"]
    ph = (h == h.rolling(2 * W + 1, center=True).max()).values
    pl = (l == l.rolling(2 * W + 1, center=True).min()).values
    return ph, pl


def detect_sweeps(df):
    """Devuelve (sweep_long, sweep_short) booleanos por barra, sin look-ahead."""
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    ph, pl = pivots(df)
    n = len(df)
    sl_long = np.zeros(n, bool); sl_short = np.zeros(n, bool)
    last_sh = last_sl = np.nan          # nivel del pool vigente
    sh_age = sl_age = 10**9
    sh_used = sl_used = True
    for t in range(WARM, n):
        # pivote en t-W ya esta confirmado al llegar a t
        j = t - W
        if ph[j]:
            last_sh, sh_age, sh_used = h[j], 0, False
        if pl[j]:
            last_sl, sl_age, sl_used = l[j], 0, False
        sh_age += 1; sl_age += 1
        # sweep SHORT: mecha sobre swing high, cierra debajo
        if (not sh_used) and sh_age <= MAXAGE and not np.isnan(last_sh):
            if h[t] > last_sh and c[t] < last_sh:
                sl_short[t] = True; sh_used = True
        # sweep LONG: mecha bajo swing low, cierra arriba
        if (not sl_used) and sl_age <= MAXAGE and not np.isnan(last_sl):
            if l[t] < last_sl and c[t] > last_sl:
                sl_long[t] = True; sl_used = True
    return sl_long, sl_short


def fwd_ret(close, k):
    c = close.values; out = np.full(len(c), np.nan)
    out[:-k] = c[k:] / c[:-k] - 1
    return out


def quality_test(df, sl_long, sl_short):
    close = df["close"]; rows = []
    for k in FWD:
        fr = fwd_ret(close, k); base = np.nanmean(fr[WARM:])
        mL = sl_long & ~np.isnan(fr); retL = np.nanmean(fr[mL]) if mL.sum() else np.nan
        mS = sl_short & ~np.isnan(fr); retS = np.nanmean(fr[mS]) if mS.sum() else np.nan
        rows.append(dict(k=f"{k}h", base=f"{base*100:+.3f}",
                         sweepL=f"{retL*100:+.3f}", edgeL=f"{(retL-base)*100:+.3f}", nL=int(mL.sum()),
                         sweepS=f"{retS*100:+.3f}", edgeS=f"{(base-retS)*100:+.3f}", nS=int(mS.sum())))
    return pd.DataFrame(rows)


def traded_rule(df, sig, side):
    """Entra al open[t+1] tras sweep, sale tras HOLD velas. Neto de costos."""
    op = df["open"].values; n = len(df); idx = df.index
    trades = []; pos = 0; epx = ei = None
    for t in range(WARM, n - 1):
        if pos == side and (t - ei) >= HOLD:
            r = side * (op[t + 1] / epx - 1) - COST_RT
            trades.append((idx[ei], side * r)); pos = 0
        if pos == 0 and sig[t]:
            pos, epx, ei = side, op[t + 1], t
    if not trades:
        return None
    return pd.DataFrame(trades, columns=["t_in", "ret"])


def metrics(tr, label):
    if tr is None or len(tr) == 0:
        return dict(variante=label, trades=0)
    r = tr["ret"]; eq = (1 + r).cumprod()
    wins, losses = r[r > 0], r[r <= 0]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf
    by_year = tr.assign(y=tr["t_in"].dt.year).groupby("y")["ret"].mean() * 1e4
    yrs = " ".join(f"{y}:{v:+.0f}" for y, v in by_year.items())
    return dict(variante=label, trades=len(tr), winrate=f"{(r > 0).mean():.1%}",
                PF=round(pf, 2), expect_bps=round(r.mean() * 1e4, 1),
                total_pct=round((eq.iloc[-1] - 1) * 100, 1), bps_x_anio=yrs)


for coin in COINS:
    df = pd.read_parquet(DATA.format(c=coin, tf=TF))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    sl_long, sl_short = detect_sweeps(df)
    print(f"\n{'='*92}\n{coin} {TF}  ({len(df)} velas)  sweeps: {sl_long.sum()} long / {sl_short.sum()} short")
    print("--- A) calidad de senal: retorno forward (%), edge>0 = la reversion se cumple ---")
    print(quality_test(df, sl_long, sl_short).to_string(index=False))
    print(f"--- B) regla operada (entra post-sweep, sale {HOLD}h, neto costos 0.04%) ---")
    rows = [metrics(traded_rule(df, sl_long, +1), "sweepLow->long"),
            metrics(traded_rule(df, sl_short, -1), "sweepHigh->short")]
    print(pd.DataFrame(rows).to_string(index=False))

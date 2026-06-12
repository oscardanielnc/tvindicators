# PoC: B-Xtrender (@Puppytherapy) +/- Donchian Trend (@LonesomeTheBlue)
# BTC/USDT perp 15m, default params, real costs. Walk-forward honesto:
# señal al cierre de barra i -> ejecución al open de barra i+1.
import numpy as np
import pandas as pd

DATA = r"C:/Users/LENOVO/Oscilion/data/ohlcv/binanceusdm/BTC_USDT_USDT/15m.parquet"
FEE_SIDE = 0.00045      # taker Binance futures
SLIP_SIDE = 0.0002      # 2 bps slippage por lado
COST_RT = 2 * (FEE_SIDE + SLIP_SIDE)   # ida y vuelta = 0.13%
OOS_START = pd.Timestamp("2026-01-01")

# ---------- réplicas Pine ----------
def pine_ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def pine_rma(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()

def pine_rsi(s, n):
    d = s.diff()
    up = pine_rma(d.clip(lower=0), n)
    dn = pine_rma((-d).clip(lower=0), n)
    rs = up / dn
    return 100 - 100 / (1 + rs)

def t3(s, n, b=0.7):
    e1 = pine_ema(s, n); e2 = pine_ema(e1, n); e3 = pine_ema(e2, n)
    e4 = pine_ema(e3, n); e5 = pine_ema(e4, n); e6 = pine_ema(e5, n)
    c1 = -b**3; c2 = 3*b**2 + 3*b**3; c3 = -6*b**2 - 3*b - 3*b**3
    c4 = 1 + 3*b + b**3 + 3*b**2
    return c1*e6 + c2*e5 + c3*e4 + c4*e3

def donchian_trend(close, high, low, length, strict):
    hh = high.rolling(length).max().shift(1)
    ll = low.rolling(length).min().shift(1)
    if strict:   # dchanneltr: >= / <=
        raw = np.where(close >= hh, 1.0, np.where(close <= ll, -1.0, np.nan))
    else:        # dchannel: > / <
        raw = np.where(close > hh, 1.0, np.where(close < ll, -1.0, np.nan))
    return pd.Series(raw, index=close.index).ffill().fillna(0.0)

# ---------- carga ----------
df = pd.read_parquet(DATA)
df["dt"] = pd.to_datetime(df["ts"], unit="ms")
df = df.set_index("dt").sort_index()
close, high, low, openp = df["close"], df["high"], df["low"], df["open"]

# ---------- B-Xtrender (defaults 5,20,15 / 20,15 / T3 5) ----------
short_osc = pine_rsi(pine_ema(close, 5) - pine_ema(close, 20), 15) - 50
regime = pine_rsi(pine_ema(close, 20), 15) - 50
ma = t3(short_osc, 5)

green_circle = (ma > ma.shift(1)) & (ma.shift(1) < ma.shift(2))   # suelo -> giro arriba
red_circle = (ma < ma.shift(1)) & (ma.shift(1) > ma.shift(2))     # techo -> giro abajo
regime_up = regime > 0
regime_turn_up = regime > regime.shift(1)
t3_below0 = ma < 0
t3_above0 = ma > 0

# ---------- Donchian Trend (dlen=20) ----------
main = donchian_trend(close, high, low, 20, strict=False)
tt = np.where(main == 1, 10.0, np.where(main == -1, -10.0, 0.0))
for sub in range(11, 20):  # dlen-9 .. dlen-1
    st = donchian_trend(close, high, low, sub, strict=True)
    disagree = np.sign(st.values) != np.sign(main.values)
    tt = tt - np.where(disagree, np.sign(main.values), 0.0)
tt = pd.Series(tt, index=close.index)
don_up, don_dn = main == 1, main == -1

# ---------- motor ----------
def run(entry_l, entry_s, exit_l, exit_s, size_l=None, size_s=None):
    """Señales en barra i -> ejecutar al open de i+1. Devuelve lista de trades."""
    eL, eS = entry_l.values, entry_s.values
    xL, xS = exit_l.values, exit_s.values
    szL = size_l.values if size_l is not None else np.ones(len(df))
    szS = size_s.values if size_s is not None else np.ones(len(df))
    op = openp.values
    idx = df.index
    trades, pos = [], 0
    entry_px = entry_i = sz = None
    for i in range(300, len(df) - 1):          # warmup indicadores
        px_next = op[i + 1]
        if pos == 1 and xL[i]:
            r = (px_next / entry_px - 1) - COST_RT
            trades.append((idx[entry_i], idx[i + 1], "L", sz * r, r, i + 1 - entry_i))
            pos = 0
        elif pos == -1 and xS[i]:
            r = (entry_px / px_next - 1) - COST_RT
            trades.append((idx[entry_i], idx[i + 1], "S", sz * r, r, i + 1 - entry_i))
            pos = 0
        if pos == 0:
            if eL[i]:
                pos, entry_px, entry_i, sz = 1, px_next, i + 1, szL[i]
            elif eS[i]:
                pos, entry_px, entry_i, sz = -1, px_next, i + 1, szS[i]
    return pd.DataFrame(trades, columns=["t_in", "t_out", "side", "ret_w", "ret", "bars"])

def metrics(tr, label, days):
    if len(tr) == 0:
        return {"variante": label, "trades": 0}
    r = tr["ret_w"]
    eq = (1 + r).cumprod()
    peak = eq.cummax()
    mdd = ((eq / peak) - 1).min()
    daily = pd.Series(r.values, index=tr["t_out"].values).resample("1D").sum()
    sharpe = daily.mean() / daily.std() * np.sqrt(365) if daily.std() > 0 else np.nan
    wins, losses = r[r > 0], r[r <= 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else np.inf
    return {
        "variante": label, "trades": len(tr), "tr/dia": round(len(tr) / days, 2),
        "winrate": f"{(r > 0).mean():.1%}", "PF": round(pf, 2),
        "expect%": round(r.mean() * 100, 4), "bruto%": round((tr['ret'] + COST_RT).mean() * 100, 4),
        "total%": round((eq.iloc[-1] - 1) * 100, 1), "maxDD%": round(mdd * 100, 1),
        "sharpe": round(sharpe, 2), "hold(h)": round(tr["bars"].mean() * 0.25, 1),
    }

# ---------- variantes ----------
variants = {
    "V0 flip puro (todos los círculos)": dict(
        entry_l=green_circle, entry_s=red_circle, exit_l=red_circle, exit_s=green_circle),
    "V1 círculo + T3<0/T3>0": dict(
        entry_l=green_circle & t3_below0, entry_s=red_circle & t3_above0,
        exit_l=red_circle, exit_s=green_circle),
    "V2 = V1 + régimen B-Xtrender": dict(
        entry_l=green_circle & t3_below0 & regime_up, entry_s=red_circle & t3_above0 & ~regime_up,
        exit_l=red_circle, exit_s=green_circle),
    "V2b = V1 + régimen girando": dict(
        entry_l=green_circle & t3_below0 & regime_turn_up,
        entry_s=red_circle & t3_above0 & ~regime_turn_up,
        exit_l=red_circle, exit_s=green_circle),
    "V3 = V1 + Donchian AND": dict(
        entry_l=green_circle & t3_below0 & don_up, entry_s=red_circle & t3_above0 & don_dn,
        exit_l=red_circle, exit_s=green_circle),
    "V4 = V1 + régimen + Donchian": dict(
        entry_l=green_circle & t3_below0 & regime_up & don_up,
        entry_s=red_circle & t3_above0 & ~regime_up & don_dn,
        exit_l=red_circle, exit_s=green_circle),
    "V5 = V1, Donchian sizing 1.0/0.5": dict(
        entry_l=green_circle & t3_below0, entry_s=red_circle & t3_above0,
        exit_l=red_circle, exit_s=green_circle,
        size_l=pd.Series(np.where(don_up, 1.0, 0.5), index=df.index),
        size_s=pd.Series(np.where(don_dn, 1.0, 0.5), index=df.index)),
}

for period, lo, hi in [("IS 2023-06→2025-12", None, OOS_START),
                       ("OOS 2026 (ciego)", OOS_START, None)]:
    mask = pd.Series(True, index=df.index)
    if lo is not None: mask &= df.index >= lo
    if hi is not None: mask &= df.index < hi
    days = mask.sum() * 15 / 60 / 24
    print(f"\n=== {period}  ({days:.0f} dias) — costos {COST_RT*100:.2f}% ida+vuelta ===")
    rows = []
    for name, kw in variants.items():
        tr = run(**kw)
        sel = tr[(tr["t_in"] >= (lo or df.index[0])) & (tr["t_in"] < (hi or df.index[-1] + pd.Timedelta("1d")))]
        rows.append(metrics(sel, name, days))
    print(pd.DataFrame(rows).to_string(index=False))

# BTC buy & hold de referencia
for period, lo, hi in [("IS", None, OOS_START), ("OOS", OOS_START, None)]:
    sub = close[(close.index >= (lo or close.index[0])) & (close.index < (hi or close.index[-1]))]
    print(f"\nBTC buy&hold {period}: {(sub.iloc[-1]/sub.iloc[0]-1)*100:+.1f}%")

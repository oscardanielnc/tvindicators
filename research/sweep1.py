# Barrido 1: B-Xtrender +/- Donchian Trend
# 13 monedas x {15m,1h} x {long,short} x 4 entradas x 2 salidas. IS<=2025-12 / OOS 2026.
# Costos: entrada/salida por senal = maker 0.02%; salida por stop = taker 0.045% + slip 0.02%.
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd
import os

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT", "TRX", "LTC", "SUI"]
TFS = {"15m": 96, "1h": 24}          # barras por dia
MAKER, TAKER, SLIP = 0.0002, 0.00045, 0.0002
OOS_START = pd.Timestamp("2026-01-01")
TIMEOUT_H = 48
ATR_MULT = 2.0
WARMUP = 300

def pine_ema(s, n): return s.ewm(span=n, adjust=False).mean()
def pine_rma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()
def pine_rsi(s, n):
    d = s.diff()
    return 100 - 100 / (1 + pine_rma(d.clip(lower=0), n) / pine_rma((-d).clip(lower=0), n))
def t3(s, n, b=0.7):
    e1 = pine_ema(s, n); e2 = pine_ema(e1, n); e3 = pine_ema(e2, n)
    e4 = pine_ema(e3, n); e5 = pine_ema(e4, n); e6 = pine_ema(e5, n)
    return -b**3*e6 + (3*b**2+3*b**3)*e5 + (-6*b**2-3*b-3*b**3)*e4 + (1+3*b+b**3+3*b**2)*e3
def donch_main(c, h, l, n=20):
    hh = h.rolling(n).max().shift(1); ll = l.rolling(n).min().shift(1)
    raw = np.where(c > hh, 1.0, np.where(c < ll, -1.0, np.nan))
    return pd.Series(raw, index=c.index).ffill().fillna(0.0)

def load(coin, tf):
    p = rf"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{coin}_USDT_USDT/{tf}.parquet"
    if not os.path.exists(p): return None
    df = pd.read_parquet(p)
    df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("dt").sort_index()

def backtest(df, entry_mask, exit_mode, side, to_bars):
    """side: +1 long / -1 short. exit_mode: 'circle' (mask en df attrs) o 'atrstop'."""
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    atr = df.attrs["atr"]; exm = df.attrs["exit_circle_l"] if side > 0 else df.attrs["exit_circle_s"]
    idx = df.index
    n = len(df)
    entries = np.flatnonzero(entry_mask[WARMUP:n-2]) + WARMUP
    trades = []
    j_free = 0
    for i_sig in entries:
        if i_sig < j_free: continue
        e_i = i_sig + 1
        epx = op[e_i]
        stop = epx - side * ATR_MULT * atr[i_sig]
        j = e_i
        exit_px, cost_out, t_out = None, MAKER, None
        while j < n - 1:
            if exit_mode == "atrstop":
                hit = lo[j] <= stop if side > 0 else hi[j] >= stop
                if hit:
                    exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                    cost_out, t_out = TAKER + SLIP, j
                    break
                if j - e_i + 1 >= to_bars:
                    exit_px, t_out = op[j + 1], j + 1
                    break
            else:
                if exm[j]:
                    exit_px, t_out = op[j + 1], j + 1
                    break
            j += 1
        if exit_px is None: break          # trade abierto al final: descartar
        gross = side * (exit_px / epx - 1)
        net = gross - MAKER - cost_out
        trades.append((idx[e_i], net, (t_out - e_i)))
        j_free = t_out + 1
    return pd.DataFrame(trades, columns=["t_in", "net", "bars"])

def metr(tr, bpd):
    r = tr["net"]
    eq = (1 + r).cumprod()
    mdd = ((eq / eq.cummax()) - 1).min() if len(r) else np.nan
    pf = r[r > 0].sum() / abs(r[r <= 0].sum()) if (r <= 0).any() and r[r <= 0].sum() != 0 else np.inf
    return dict(n=len(r), wr=round((r > 0).mean(), 3), pf=round(pf, 2),
                expect=round(r.mean() * 100, 4), total=round((eq.iloc[-1] - 1) * 100, 1),
                mdd=round(mdd * 100, 1), hold_h=round(tr["bars"].mean() * 24 / bpd, 1))

rows = []
for coin in COINS:
    for tf, bpd in TFS.items():
        df = load(coin, tf)
        if df is None or len(df) < 5000:
            continue
        c, h, l = df["close"], df["high"], df["low"]
        osc = pine_rsi(pine_ema(c, 5) - pine_ema(c, 20), 15) - 50
        reg = pine_rsi(pine_ema(c, 20), 15) - 50
        ma = t3(osc, 5)
        green = ((ma > ma.shift(1)) & (ma.shift(1) < ma.shift(2))).values
        red = ((ma < ma.shift(1)) & (ma.shift(1) > ma.shift(2))).values
        below0, above0 = (ma < 0).values, (ma > 0).values
        regup, regdn = (reg > 0).values, (reg < 0).values
        don = donch_main(c, h, l).values
        tr_ = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        df.attrs["atr"] = pine_rma(tr_, 14).values
        df.attrs["exit_circle_l"], df.attrs["exit_circle_s"] = red, green
        entries = {
            "BX-min":     {1: green & below0,                    -1: red & above0},
            "BX-reg":     {1: green & below0 & regup,            -1: red & above0 & regdn},
            "BX+Don":     {1: green & below0 & (don == 1),       -1: red & above0 & (don == -1)},
            "BX-reg+Don": {1: green & below0 & regup & (don == 1), -1: red & above0 & regdn & (don == -1)},
        }
        to_bars = TIMEOUT_H * bpd // 24
        for ename, sides in entries.items():
            for side in (1, -1):
                for exname in ("circle", "atrstop"):
                    tr = backtest(df, sides[side], exname, side, to_bars)
                    if len(tr) == 0: continue
                    for per, m in [("IS", tr["t_in"] < OOS_START), ("OOS", tr["t_in"] >= OOS_START)]:
                        sub = tr[m]
                        if len(sub) < 5: continue
                        rows.append(dict(coin=coin, tf=tf, side="L" if side > 0 else "S",
                                         entry=ename, exit=exname, period=per, **metr(sub, bpd)))
    print(f"{coin} ok", flush=True)

res = pd.DataFrame(rows)
res.to_csv(str(_ROOT / "results_sweep1.csv"), index=False)
print(f"\nTotal filas: {len(res)}  (guardado en results_sweep1.csv)")

piv = res.pivot_table(index=["entry", "exit", "side", "tf"], columns="period",
                      values=["expect", "pf"], aggfunc="median")
piv[("pos_OOS", "%runs")] = res[res.period == "OOS"].groupby(["entry", "exit", "side", "tf"])["expect"] \
    .apply(lambda s: round((s > 0).mean() * 100)).reindex(piv.index)
print("\n=== AGREGADO por variante (mediana entre monedas) ===")
print(piv.round(3).to_string())

print("\n=== Por MONEDA (mediana OOS expect% entre todas las variantes) ===")
bycoin = res[res.period == "OOS"].pivot_table(index="coin", columns="side", values="expect", aggfunc="median")
print(bycoin.round(3).sort_values("L", ascending=False).to_string())

print("\n=== CANDIDATOS: IS pf>=1.05 & IS n>=60, mostrando su OOS ===")
is_ok = res[(res.period == "IS") & (res.pf >= 1.05) & (res.n >= 60)]
keys = ["coin", "tf", "side", "entry", "exit"]
oos = res[res.period == "OOS"].set_index(keys)
cand = is_ok.set_index(keys)[["n", "pf", "expect", "total", "mdd"]].add_prefix("IS_")
cand = cand.join(oos[["n", "pf", "expect", "total", "mdd"]].add_prefix("OOS_"), how="left")
cand = cand.sort_values("OOS_pf", ascending=False)
print(cand.round(3).to_string())

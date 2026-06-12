# Robustez ano-a-ano de los candidatos que ganaron en IS y OOS
import numpy as np
import pandas as pd

MAKER, TAKER, SLIP = 0.0002, 0.00045, 0.0002
ATR_MULT, WARMUP, TIMEOUT_H = 2.0, 300, 48

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

CONFIGS = [
    ("TRX", "1h", 1, "BX-min", "atrstop"),
    ("TRX", "1h", 1, "BX-reg", "atrstop"),
    ("BTC", "15m", 1, "BX+Don", "atrstop"),
    ("SUI", "1h", -1, "BX-reg", "atrstop"),
    ("ADA", "1h", -1, "BX+Don", "atrstop"),
    ("XRP", "1h", -1, "BX-reg+Don", "atrstop"),
    ("ETH", "1h", -1, "BX+Don", "atrstop"),
    ("BNB", "1h", -1, "BX-reg", "circle"),
]

rows = []
for coin, tf, side, ename, exname in CONFIGS:
    bpd = 96 if tf == "15m" else 24
    df = pd.read_parquet(rf"C:/Users/LENOVO/Oscilion/data/ohlcv/binanceusdm/{coin}_USDT_USDT/{tf}.parquet")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
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
    atr = pine_rma(tr_, 14).values
    ent = {
        ("BX-min", 1): green & below0, ("BX-min", -1): red & above0,
        ("BX-reg", 1): green & below0 & regup, ("BX-reg", -1): red & above0 & regdn,
        ("BX+Don", 1): green & below0 & (don == 1), ("BX+Don", -1): red & above0 & (don == -1),
        ("BX-reg+Don", 1): green & below0 & regup & (don == 1),
        ("BX-reg+Don", -1): red & above0 & regdn & (don == -1),
    }[(ename, side)]
    exm = red if side > 0 else green
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    idx = df.index; n = len(df)
    to_bars = TIMEOUT_H * bpd // 24
    trades, j_free = [], 0
    for i_sig in np.flatnonzero(ent[WARMUP:n-2]) + WARMUP:
        if i_sig < j_free: continue
        e_i = i_sig + 1; epx = op[e_i]
        stop = epx - side * ATR_MULT * atr[i_sig]
        j, exit_px, cost_out, t_out = e_i, None, MAKER, None
        while j < n - 1:
            if exname == "atrstop":
                hit = lo[j] <= stop if side > 0 else hi[j] >= stop
                if hit:
                    exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                    cost_out, t_out = TAKER + SLIP, j; break
                if j - e_i + 1 >= to_bars:
                    exit_px, t_out = op[j + 1], j + 1; break
            elif exm[j]:
                exit_px, t_out = op[j + 1], j + 1; break
            j += 1
        if exit_px is None: break
        net = side * (exit_px / epx - 1) - MAKER - cost_out
        trades.append((idx[e_i], net)); j_free = t_out + 1
    tr = pd.DataFrame(trades, columns=["t_in", "net"])
    tr["year"] = tr["t_in"].dt.year
    label = f"{coin} {tf} {'LONG' if side>0 else 'SHORT'} {ename}/{exname}"
    row = {"config": label}
    for y, g in tr.groupby("year"):
        r = g["net"]
        pf = r[r > 0].sum() / abs(r[r <= 0].sum()) if (r <= 0).any() and r[r <= 0].sum() != 0 else np.inf
        row[str(y)] = f"{(np.prod(1+r)-1)*100:+.0f}% pf{pf:.2f} n{len(r)}"
    rows.append(row)

print(pd.DataFrame(rows).set_index("config").fillna("-").to_string())

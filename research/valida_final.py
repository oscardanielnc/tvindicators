# Validacion final de los 3 supervivientes:
# (1) funding real por trade  (2) sensibilidad ATR {1.5,2,2.5} x timeout {24,48,72}h
import numpy as np
import pandas as pd

MAKER, TAKER, SLIP = 0.0002, 0.00045, 0.0002
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

FUNDING = {
    "TRX": (r"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/TRX_USDT_USDT.parquet", "ts"),
    "ETH": (r"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/ETH_USDT_USDT.parquet", "ts"),
    "SUI": (r"C:/Users/LENOVO/kepler/data/funding/SUIUSDT.parquet", "funding_time"),
}
def load_funding(coin):
    p, tcol = FUNDING[coin]
    f = pd.read_parquet(p)
    t = pd.to_datetime(f[tcol], unit="ms").values.astype("datetime64[ns]")
    return t, f["funding_rate"].astype(float).values

CONFIGS = [("TRX", 1, "BX-min"), ("SUI", -1, "BX-reg"), ("ETH", -1, "BX+Don")]

def prep(coin):
    df = pd.read_parquet(rf"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{coin}_USDT_USDT/1h.parquet")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    c, h, l = df["close"], df["high"], df["low"]
    osc = pine_rsi(pine_ema(c, 5) - pine_ema(c, 20), 15) - 50
    reg = pine_rsi(pine_ema(c, 20), 15) - 50
    ma = t3(osc, 5)
    green = ((ma > ma.shift(1)) & (ma.shift(1) < ma.shift(2))).values
    red = ((ma < ma.shift(1)) & (ma.shift(1) > ma.shift(2))).values
    sig = {
        ("BX-min", 1): green & (ma < 0).values,
        ("BX-reg", -1): red & (ma > 0).values & (reg < 0).values,
        ("BX+Don", -1): red & (ma > 0).values & (donch_main(c, h, l).values == -1),
    }
    tr_ = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return df, sig, pine_rma(tr_, 14).values

def run(df, ent, atrv, side, atr_mult, to_bars, ft, fr):
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    idx = df.index.values; n = len(df)
    trades, j_free = [], 0
    for i_sig in np.flatnonzero(ent[WARMUP:n-2]) + WARMUP:
        if i_sig < j_free: continue
        e_i = i_sig + 1; epx = op[e_i]
        stop = epx - side * atr_mult * atrv[i_sig]
        j, exit_px, cost_out, t_out = e_i, None, MAKER, None
        while j < n - 1:
            hit = lo[j] <= stop if side > 0 else hi[j] >= stop
            if hit:
                exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                cost_out, t_out = TAKER + SLIP, j; break
            if j - e_i + 1 >= to_bars:
                exit_px, t_out = op[j + 1], j + 1; break
            j += 1
        if exit_px is None: break
        gross = side * (exit_px / epx - 1) - MAKER - cost_out
        a, b = np.searchsorted(ft, idx[e_i]), np.searchsorted(ft, idx[t_out])
        fund = -side * fr[a:b].sum()          # long paga funding positivo, short lo cobra
        trades.append((idx[e_i], gross, fund))
        j_free = t_out + 1
    tr = pd.DataFrame(trades, columns=["t_in", "net0", "fund"])
    tr["net"] = tr["net0"] + tr["fund"]
    return tr

def yearly(tr, col="net"):
    out = {}
    for y, g in tr.groupby(pd.to_datetime(tr["t_in"]).dt.year):
        out[y] = (np.prod(1 + g[col]) - 1) * 100
    return out

print("=" * 95)
print("(1) IMPACTO DEL FUNDING — parametros default (ATR 2.0, timeout 48h), retorno anual %")
rows = []
for coin, side, ename in CONFIGS:
    df, sigs, atrv = prep(coin)
    ft, fr = load_funding(coin)
    tr = run(df, sigs[(ename, side)], atrv, side, 2.0, 48, ft, fr)
    y0, y1 = yearly(tr, "net0"), yearly(tr, "net")
    fund_pa = tr["fund"].mean() * 100
    r = {"config": f"{coin} {'L' if side>0 else 'S'} {ename}", "fund/trade%": round(fund_pa, 4)}
    for y in sorted(y1):
        r[f"{y} sin"] = round(y0[y], 1); r[f"{y} con"] = round(y1[y], 1)
    rows.append(r)
print(pd.DataFrame(rows).set_index("config").to_string())

print()
print("=" * 95)
print("(2) SENSIBILIDAD (con funding): ATR x timeout -> total% | PF | n | anos positivos de 4")
for coin, side, ename in CONFIGS:
    df, sigs, atrv = prep(coin)
    ft, fr = load_funding(coin)
    print(f"\n--- {coin} {'LONG' if side>0 else 'SHORT'} {ename} ---")
    grid = {}
    for am in (1.5, 2.0, 2.5):
        row = {}
        for to in (24, 48, 72):
            tr = run(df, sigs[(ename, side)], atrv, side, am, to, ft, fr)
            r = tr["net"]
            pf = r[r > 0].sum() / abs(r[r <= 0].sum()) if (r <= 0).any() else np.inf
            ys = yearly(tr)
            npos = sum(v > 0 for v in ys.values())
            row[f"to{to}h"] = f"{(np.prod(1+r)-1)*100:+.0f}% pf{pf:.2f} n{len(r)} {npos}/4"
        grid[f"ATR{am}"] = row
    print(pd.DataFrame(grid).T.to_string())

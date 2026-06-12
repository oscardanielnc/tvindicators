# Sensibilidad de parametros para los 5 candidatos pendientes (con funding real)
# - atrstop configs: grid ejecucion ATR{1.5,2,2.5} x TO{24,48,72}h
# - ST-based: grid indicador period{7,10,14} x factor{2.5,3,3.5}
# - TM: perturbacion RSI internos {11,13,15} x {4,5,6}
import numpy as np
import pandas as pd

MAKER, TAKER, SLIP = 0.0002, 0.00045, 0.0002
WARMUP = 300
ATRV = {}

def pine_ema(s, n): return s.ewm(span=n, adjust=False).mean()
def pine_sma(s, n): return s.rolling(n).mean()
def pine_rma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()
def pine_rsi(s, n):
    d = s.diff()
    return 100 - 100 / (1 + pine_rma(d.clip(lower=0), n) / pine_rma((-d).clip(lower=0), n))
def donch_main(c, h, l, n=20):
    hh = h.rolling(n).max().shift(1); ll = l.rolling(n).min().shift(1)
    raw = np.where(c > hh, 1.0, np.where(c < ll, -1.0, np.nan))
    return pd.Series(raw, index=c.index).ffill().fillna(0.0)
def supertrend_dir(h, l, c, period, factor):
    hl2 = (h + l) / 2
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = pine_rma(tr, period).values
    up = (hl2.values + factor * atr); dn = (hl2.values - factor * atr)
    cl = c.values; n = len(cl)
    d = np.ones(n); fu, fd = up.copy(), dn.copy()
    for i in range(1, n):
        fu[i] = up[i] if (up[i] < fu[i-1] or cl[i-1] > fu[i-1]) else fu[i-1]
        fd[i] = dn[i] if (dn[i] > fd[i-1] or cl[i-1] < fd[i-1]) else fd[i-1]
        d[i] = (-1 if cl[i] < fd[i] else 1) if d[i-1] == 1 else (1 if cl[i] > fu[i] else -1)
    return d

FUND = {c: (rf"C:/Users/LENOVO/Oscilion/data/funding/binanceusdm/{c}_USDT_USDT.parquet", "ts")
        for c in ["TRX", "ETH", "BTC", "LTC", "DOT"]}
def load_fund(coin):
    p, tcol = FUND[coin]
    f = pd.read_parquet(p)
    return pd.to_datetime(f[tcol], unit="ms").values.astype("datetime64[ns]"), f["funding_rate"].astype(float).values

def load_df(coin, tf):
    df = pd.read_parquet(rf"C:/Users/LENOVO/Oscilion/data/ohlcv/binanceusdm/{coin}_USDT_USDT/{tf}.parquet")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("dt").sort_index()

def atr14(df):
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    return pine_rma(tr, 14).values

def engine(df, ent, side, exit_mode, atr_mult, to_bars, exm, ft, fr):
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    atrv = ATRV[id(df)]; idx = df.index.values; n = len(df)
    trades, j_free = [], 0
    for i_sig in np.flatnonzero(ent[WARMUP:n-2]) + WARMUP:
        if i_sig < j_free: continue
        e_i = i_sig + 1; epx = op[e_i]
        stop = epx - side * atr_mult * atrv[i_sig]
        j, exit_px, cost_out, t_out = e_i, None, MAKER, None
        while j < n - 1:
            if exit_mode == "atrstop":
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
        a, b = np.searchsorted(ft, idx[e_i]), np.searchsorted(ft, idx[t_out])
        net = side * (exit_px / epx - 1) - MAKER - cost_out + (-side * fr[a:b].sum())
        trades.append((pd.Timestamp(idx[e_i]), net))
        j_free = t_out + 1
    return pd.DataFrame(trades, columns=["t_in", "net"])

def cell(tr):
    if len(tr) < 30: return "n<30"
    r = tr["net"]
    pf = r[r > 0].sum() / abs(r[r <= 0].sum())
    y = tr.groupby(tr["t_in"].dt.year)["net"].apply(lambda g: np.prod(1 + g) - 1)
    return f"{(np.prod(1+r)-1)*100:+.0f}% pf{pf:.2f} {int((y>0).sum())}/{len(y)}"

def tm_trigger(c, rsi_a, rsi_b):
    fmacd = pine_ema(c, 8) - pine_ema(c, 21)
    fhist = (fmacd - pine_ema(fmacd, 5)) > 0
    pos = (fhist & (pine_rsi(c, rsi_a) > 50) & (pine_rsi(c, rsi_b) > 50)).values
    return pos & ~np.roll(pos, 1)

print("=" * 90)
print("#4 TRX 1h LONG | TrendMeter solo | atrstop -- GRID A: ejecucion (RSI 13/5 fijos)")
df = load_df("TRX", "1h"); ATRV[id(df)] = atr14(df)
ft, fr = load_fund("TRX")
ent_def = tm_trigger(df["close"], 13, 5)
g = {}
for am in (1.5, 2.0, 2.5):
    g[f"ATR{am}"] = {f"to{to}h": cell(engine(df, ent_def, 1, "atrstop", am, to, None, ft, fr)) for to in (24, 48, 72)}
print(pd.DataFrame(g).T.to_string())
print("\n#4 GRID B: parametros internos TM (RSI_a x RSI_b), ejecucion default ATR2.0/48h")
g = {}
for ra in (11, 13, 15):
    g[f"RSI_a{ra}"] = {f"RSI_b{rb}": cell(engine(df, tm_trigger(df["close"], ra, rb), 1, "atrstop", 2.0, 48, None, ft, fr)) for rb in (4, 5, 6)}
print(pd.DataFrame(g).T.to_string())

print("\n" + "=" * 90)
print("#5 TRX 15m LONG | Supertrend solo | salida flip -- GRID: period x factor del ST")
df = load_df("TRX", "15m"); ATRV[id(df)] = atr14(df)
g = {}
for per in (7, 10, 14):
    row = {}
    for fac in (2.5, 3.0, 3.5):
        sd = supertrend_dir(df["high"], df["low"], df["close"], per, fac)
        sdp = np.roll(sd, 1); sdp[0] = sd[0]
        flip_up, flip_dn = (sd == 1) & (sdp == -1), (sd == -1) & (sdp == 1)
        row[f"f{fac}"] = cell(engine(df, flip_up, 1, "flip", 2.0, 0, flip_dn, ft, fr))
    g[f"per{per}"] = row
print(pd.DataFrame(g).T.to_string())

print("\n" + "=" * 90)
print("#6 BTC 1h LONG | TMWT + filtro ST | atrstop -- GRID: ejecucion")
df = load_df("BTC", "1h"); ATRV[id(df)] = atr14(df)
ft, fr = load_fund("BTC")
c, h, l = df["close"], df["high"], df["low"]
fmacd = pine_ema(c, 8) - pine_ema(c, 21)
fhist = (fmacd - pine_ema(fmacd, 5)) > 0
tm3pos = (fhist & (pine_rsi(c, 13) > 50) & (pine_rsi(c, 5) > 50)).values
ap = (h + l + c) / 3
esa = pine_ema(ap, 9); de = pine_ema((ap - esa).abs(), 9)
wt1 = pine_ema((ap - esa) / (0.015 * de), 12); wt2 = pine_sma(wt1, 3)
diff = (wt1 - wt2).values; dp = np.roll(diff, 1); dp[0] = 0
sd = supertrend_dir(h, l, c, 10, 3.0)
ent = (diff >= 0) & (dp < 0) & tm3pos & (sd == 1)
g = {}
for am in (1.5, 2.0, 2.5):
    g[f"ATR{am}"] = {f"to{to}h": cell(engine(df, ent, 1, "atrstop", am, to, None, ft, fr)) for to in (24, 48, 72)}
print(pd.DataFrame(g).T.to_string())

for coin, fil_name in [("LTC", "Don"), ("DOT", "BXreg")]:
    print("\n" + "=" * 90)
    print(f"#{7 if coin=='LTC' else 8} {coin} 1h SHORT | ST flip + {fil_name} | atrstop")
    df = load_df(coin, "1h"); ATRV[id(df)] = atr14(df)
    ft, fr = load_fund(coin)
    c, h, l = df["close"], df["high"], df["low"]
    if fil_name == "Don":
        fil = (donch_main(c, h, l).values == -1)
    else:
        fil = ((pine_rsi(pine_ema(c, 20), 15) - 50) < 0).values
    print("GRID A: ejecucion (ST 10/3.0 fijo)")
    sd = supertrend_dir(h, l, c, 10, 3.0)
    sdp = np.roll(sd, 1); sdp[0] = sd[0]
    ent = (sd == -1) & (sdp == 1) & fil
    g = {}
    for am in (1.5, 2.0, 2.5):
        g[f"ATR{am}"] = {f"to{to}h": cell(engine(df, ent, -1, "atrstop", am, to, None, ft, fr)) for to in (24, 48, 72)}
    print(pd.DataFrame(g).T.to_string())
    print("GRID B: parametros ST del gatillo (ejecucion default ATR2.0/48h)")
    g = {}
    for per in (7, 10, 14):
        row = {}
        for fac in (2.5, 3.0, 3.5):
            sd = supertrend_dir(h, l, c, per, fac)
            sdp = np.roll(sd, 1); sdp[0] = sd[0]
            ent = (sd == -1) & (sdp == 1) & fil
            row[f"f{fac}"] = cell(engine(df, ent, -1, "atrstop", 2.0, 48, None, ft, fr))
        g[f"per{per}"] = row
    print(pd.DataFrame(g).T.to_string())

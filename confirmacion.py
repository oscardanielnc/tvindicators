# Confirmacion (sensibilidad + funding) de candidatos 9-13 + 2 upgrades
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\sweep3.py", encoding="utf-8").read()
exec(src.split("def prep(")[0])   # helpers: pine_*, t3, tema, dch_trend, supertrend_dir, hacolt

MAKER, TAKER, SLIP, WARMUP = 0.0002, 0.00045, 0.0002, 300

def load_df(coin, tf):
    df = pd.read_parquet(rf"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{coin}_USDT_USDT/{tf}.parquet")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("dt").sort_index()

def load_fund(coin):
    f = pd.read_parquet(rf"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{coin}_USDT_USDT.parquet")
    return pd.to_datetime(f["ts"], unit="ms").values.astype("datetime64[ns]"), f["funding_rate"].astype(float).values

def atr14(df):
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    return pine_rma(tr, 14).values

def engine(df, atrv, ent, side, exit_mode, atr_mult, to_bars, exm, ft, fr):
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    idx = df.index.values; n = len(df)
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
    neg = r[r <= 0].sum()
    pf = r[r > 0].sum() / abs(neg) if neg != 0 else np.inf
    y = tr.groupby(tr["t_in"].dt.year)["net"].apply(lambda g: np.prod(1 + g) - 1)
    return f"{(np.prod(1+r)-1)*100:+.0f}% pf{pf:.2f} {int((y>0).sum())}/{len(y)} n{len(r)}"

def bxreg_up(c): return ((pine_rsi(pine_ema(c, 20), 15) - 50) > 0).values
def rib_strength(c, h, l, dlen=20):
    subs = np.stack([dch_trend(c, h, l, dlen - k) for k in range(10)])
    return (subs == 1).sum(axis=0), (subs == -1).sum(axis=0)

def st_grid(coin, tf, fil, side, label):
    """Grid period x factor para candidatos con ST flip como gatillo+salida."""
    df = load_df(coin, tf); atrv = atr14(df)
    ft, fr = load_fund(coin)
    print(f"\n--- {label} | GRID ST period x factor ---")
    g = {}
    for per in (7, 10, 14):
        row = {}
        for fac in (2.5, 3.0, 3.5):
            sd = supertrend_dir(df["high"], df["low"], df["close"], per, fac)
            sdp = np.roll(sd, 1); sdp[0] = sd[0]
            up, dn = (sd == 1) & (sdp == -1), (sd == -1) & (sdp == 1)
            ent = (up if side > 0 else dn) & fil(df)
            exm = dn if side > 0 else up
            row[f"f{fac}"] = cell(engine(df, atrv, ent, side, "flip", 2.0, 0, exm, ft, fr))
        g[f"per{per}"] = row
    print(pd.DataFrame(g).T.to_string())

# ---- 9. XRP 1h L: ST flip + HAC ----
def fil_xrp(df):
    return hacolt(df["open"], df["high"], df["low"], df["close"]) == 1
st_grid("XRP", "1h", fil_xrp, 1, "#9 XRP 1h LONG | ST flip + HACOLT")

# ---- 11. AVAX 15m L: ST flip + Don + HAC ----
def fil_avax(df):
    c, h, l = df["close"], df["high"], df["low"]
    return (dch_trend(c, h, l, 20) == 1) & (hacolt(df["open"], h, l, c) == 1)
st_grid("AVAX", "15m", fil_avax, 1, "#11 AVAX 15m LONG | ST flip + Don + HACOLT")

# ---- 13. ETH 15m L: ST flip + BXreg + HAC ----
def fil_eth(df):
    c = df["close"]
    return bxreg_up(c) & (hacolt(df["open"], df["high"], df["low"], c) == 1)
st_grid("ETH", "15m", fil_eth, 1, "#13 ETH 15m LONG | ST flip + BXreg + HACOLT")

# ---- U1. TRX 15m L: ST flip + HAC + RIB (upgrade del titular ST solo) ----
def fil_trx(df):
    c, h, l = df["close"], df["high"], df["low"]
    sl, _ = rib_strength(c, h, l)
    return (hacolt(df["open"], h, l, c) == 1) & (sl >= 8)
st_grid("TRX", "15m", fil_trx, 1, "U1 TRX 15m LONG | ST flip + HAC + RIB (upgrade)")

# ---- 10. BTC 1h L: RIB trigger + BXreg + ST | atrstop ----
print("\n--- #10 BTC 1h LONG | RIB trigger + BXreg + ST | GRID A: ejecucion ---")
df = load_df("BTC", "1h"); atrv = atr14(df)
ft, fr = load_fund("BTC")
c, h, l = df["close"], df["high"], df["low"]
sd = supertrend_dir(h, l, c)
def btc_ent(dlen):
    sl, _ = rib_strength(c, h, l, dlen)
    full = sl == 10
    return full & ~np.roll(full, 1) & bxreg_up(c) & (sd == 1)
ent20 = btc_ent(20)
g = {}
for am in (1.5, 2.0, 2.5):
    g[f"ATR{am}"] = {f"to{to}h": cell(engine(df, atrv, ent20, 1, "atrstop", am, to, None, ft, fr)) for to in (24, 48, 72)}
print(pd.DataFrame(g).T.to_string())
print("GRID B: largo del canal (dlen), ejecucion default ATR2.0/48h")
row = {f"dlen{d}": cell(engine(df, atrv, btc_ent(d), 1, "atrstop", 2.0, 48, None, ft, fr)) for d in (15, 20, 25)}
print(pd.DataFrame([row]).to_string(index=False))

# ---- 12. DOT 15m L: HAC trigger + BXreg | atrstop ----
print("\n--- #12 DOT 15m LONG | HACOLT trigger + BXreg | GRID A: ejecucion ---")
df = load_df("DOT", "15m"); atrv = atr14(df)
ft, fr = load_fund("DOT")
c = df["close"]
bx_up = bxreg_up(c)
def dot_ent(tl, el):
    hc = hacolt(df["open"], df["high"], df["low"], c, length=tl, ema_len=el)
    return (hc == 1) & (np.roll(hc, 1) != 1) & bx_up
ent_def = dot_ent(55, 60)
g = {}
for am in (1.5, 2.0, 2.5):
    g[f"ATR{am}"] = {f"to{to}h": cell(engine(df, atrv, ent_def, 1, "atrstop", am, to, None, ft, fr)) for to in (24, 48, 72)}
print(pd.DataFrame(g).T.to_string())
print("GRID B: params HACOLT (TEMA x EMA), ejecucion default")
g = {}
for tl in (44, 55, 66):
    g[f"TEMA{tl}"] = {f"EMA{el}": cell(engine(df, atrv, dot_ent(tl, el), 1, "atrstop", 2.0, 48, None, ft, fr)) for el in (48, 60, 72)}
print(pd.DataFrame(g).T.to_string())

# ---- U2. LTC 1h S: ST flip + RIB | atrstop (upgrade del titular Don) ----
print("\n--- U2 LTC 1h SHORT | ST flip + RIB | GRID: ejecucion ---")
df = load_df("LTC", "1h"); atrv = atr14(df)
ft, fr = load_fund("LTC")
c, h, l = df["close"], df["high"], df["low"]
sd = supertrend_dir(h, l, c)
sdp = np.roll(sd, 1); sdp[0] = sd[0]
_, ss = rib_strength(c, h, l)
ent = (sd == -1) & (sdp == 1) & (ss >= 8)
g = {}
for am in (1.5, 2.0, 2.5):
    g[f"ATR{am}"] = {f"to{to}h": cell(engine(df, atrv, ent, -1, "atrstop", am, to, None, ft, fr)) for to in (24, 48, 72)}
print(pd.DataFrame(g).T.to_string())

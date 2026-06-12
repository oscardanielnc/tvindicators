# Test de salidas: ¿el SL 2xATR mata ganadores? ¿la señal opuesta del indicador es mejor?
# 6 estrategias atrstop x 6 variantes de salida, con funding real. Datos 2023-06 -> 2026-06.
import numpy as np
import pandas as pd

src = open(r"C:\Users\LENOVO\tvindicators\sweep3.py", encoding="utf-8").read()
exec(src.split("def prep(")[0])   # helpers pine/t3/dch_trend/supertrend_dir/hacolt

MAKER, TAKER, SLIP, WARMUP = 0.0002, 0.00045, 0.0002, 300

def load_df(coin, tf):
    df = pd.read_parquet(rf"C:/Users/LENOVO/Oscilion/data/ohlcv/binanceusdm/{coin}_USDT_USDT/{tf}.parquet")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("dt").sort_index()

def load_fund(coin):
    if coin == "SUI":
        f = pd.read_parquet(r"C:/Users/LENOVO/kepler/data/funding/SUIUSDT.parquet")
        return pd.to_datetime(f["funding_time"], unit="ms").values.astype("datetime64[ns]"), f["funding_rate"].astype(float).values
    f = pd.read_parquet(rf"C:/Users/LENOVO/Oscilion/data/funding/binanceusdm/{coin}_USDT_USDT.parquet")
    return pd.to_datetime(f["ts"], unit="ms").values.astype("datetime64[ns]"), f["funding_rate"].astype(float).values

def atr14v(df):
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    return pine_rma(tr, 14).values

def engine(df, atrv, ent, side, ft, fr, atr_mult=None, to_bars=None, opp=None):
    """atr_mult=None -> sin SL. to_bars=None -> sin timeout. opp -> salida por señal opuesta."""
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    idx = df.index.values; n = len(df)
    trades, j_free, n_sl = [], 0, 0
    for i_sig in np.flatnonzero(ent[WARMUP:n-2]) + WARMUP:
        if i_sig < j_free: continue
        e_i = i_sig + 1; epx = op[e_i]
        stop = epx - side * atr_mult * atrv[i_sig] if atr_mult else None
        j, exit_px, cost_out, t_out, why = e_i, None, MAKER, None, None
        while j < n - 1:
            if stop is not None:
                hit = lo[j] <= stop if side > 0 else hi[j] >= stop
                if hit:
                    exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                    cost_out, t_out, why = TAKER + SLIP, j, "SL"; break
            if opp is not None and opp[j]:
                exit_px, t_out, why = op[j + 1], j + 1, "opp"; break
            if to_bars and j - e_i + 1 >= to_bars:
                exit_px, t_out, why = op[j + 1], j + 1, "TO"; break
            j += 1
        if exit_px is None: break
        a, b = np.searchsorted(ft, idx[e_i]), np.searchsorted(ft, idx[t_out])
        net = side * (exit_px / epx - 1) - MAKER - cost_out + (-side * fr[a:b].sum())
        if why == "SL": n_sl += 1
        trades.append((pd.Timestamp(idx[e_i]), net))
        j_free = t_out + 1
    return pd.DataFrame(trades, columns=["t_in", "net"]), n_sl

def row(tr, n_sl, label):
    if len(tr) < 20: return {"variante": label, "n": len(tr)}
    r = tr["net"]
    neg = r[r <= 0].sum()
    pf = r[r > 0].sum() / abs(neg) if neg != 0 else np.inf
    eq = (1 + r).cumprod()
    mdd = ((eq / eq.cummax()) - 1).min()
    y = tr.groupby(tr["t_in"].dt.year)["net"].apply(lambda g: np.prod(1 + g) - 1)
    return {"variante": label, "n": len(r), "%SL": f"{n_sl/len(r):.0%}",
            "PF": round(pf, 2), "expect%": round(r.mean()*100, 3),
            "total%": round((np.prod(1+r)-1)*100, 0), "maxDD%": round(mdd*100, 0),
            "anos+": f"{int((y>0).sum())}/{len(y)}"}

# ---- definicion de las 6 estrategias atrstop + su señal OPUESTA ----
def parts(df):
    c, h, l = df["close"], df["high"], df["low"]
    osc = pine_rsi(pine_ema(c, 5) - pine_ema(c, 20), 15) - 50
    reg = pine_rsi(pine_ema(c, 20), 15) - 50
    ma = t3(osc, 5)
    green = ((ma > ma.shift(1)) & (ma.shift(1) < ma.shift(2))).values
    red = ((ma < ma.shift(1)) & (ma.shift(1) > ma.shift(2))).values
    return c, h, l, green, red, ma, reg

CONFIGS = []

def cfg_s1(df):
    c, h, l, green, red, ma, reg = parts(df)
    return green & (ma < 0).values, red          # opuesta = circulo rojo (señal venta B-X)
CONFIGS.append(("S1 TRX-L BX 1h", "TRX", "1h", 1, cfg_s1))

def cfg_s2(df):
    c = df["close"]
    fmacd = pine_ema(c, 8) - pine_ema(c, 21)
    fhist = (fmacd - pine_ema(fmacd, 5)) > 0
    pos = (fhist & (pine_rsi(c, 13) > 50) & (pine_rsi(c, 5) > 50)).values
    negs = (~fhist & (pine_rsi(c, 13) < 50) & (pine_rsi(c, 5) < 50)).values
    return pos & ~np.roll(pos, 1), negs & ~np.roll(negs, 1)   # opuesta = TM alinea rojo
CONFIGS.append(("S2 TRX-L TM 1h", "TRX", "1h", 1, cfg_s2))

def cfg_s4(df):
    c, h, l, green, red, ma, reg = parts(df)
    return red & (ma > 0).values & (reg < 0).values, green    # opuesta = circulo verde
CONFIGS.append(("S4 SUI-S BX+reg 1h", "SUI", "1h", -1, cfg_s4))

def cfg_s5(df):
    c, h, l = df["close"], df["high"], df["low"]
    sd = supertrend_dir(h, l, c)
    sdp = np.roll(sd, 1); sdp[0] = sd[0]
    dn, up = (sd == -1) & (sdp == 1), (sd == 1) & (sdp == -1)
    don = dch_trend(c, h, l, 20)
    return dn & (don == -1), up                               # opuesta = ST flip up
CONFIGS.append(("S5 LTC-S ST+Don 1h", "LTC", "1h", -1, cfg_s5))

def cfg_s8(df):
    c, h, l, green, red, ma, reg = parts(df)
    don = dch_trend(c, h, l, 20)
    return red & (ma > 0).values & (don == -1), green         # opuesta = circulo verde
CONFIGS.append(("S8 ETH-S BX+Don 1h", "ETH", "1h", -1, cfg_s8))

def cfg_s9(df):
    c, h, l, green, red, ma, reg = parts(df)
    subs = np.stack([dch_trend(c, h, l, 20 - k) for k in range(10)])
    sl_ = (subs == 1).sum(axis=0)
    full = sl_ == 10
    sd = supertrend_dir(h, l, c)
    don = dch_trend(c, h, l, 20)
    don_flip_dn = (don == -1) & (np.roll(don, 1) == 1)        # opuesta = Donchian gira bajista
    return full & ~np.roll(full, 1) & (reg > 0).values & (sd == 1), don_flip_dn
CONFIGS.append(("S9 BTC-L RIB 1h", "BTC", "1h", 1, cfg_s9))

for name, coin, tf, side, builder in CONFIGS:
    df = load_df(coin, tf)
    atrv = atr14v(df)
    ft, fr = load_fund(coin)
    ent, opp = builder(df)
    rows = []
    for label, kw in [
        ("A) ATR2 + TO48  (ACTUAL)", dict(atr_mult=2.0, to_bars=48)),
        ("B) ATR3 + TO48",           dict(atr_mult=3.0, to_bars=48)),
        ("C) ATR4 + TO48",           dict(atr_mult=4.0, to_bars=48)),
        ("D) sin SL, solo TO48",     dict(to_bars=48)),
        ("E) senal OPUESTA (pura)",  dict(opp=opp)),
        ("F) ATR2 + TO72",           dict(atr_mult=2.0, to_bars=72)),
    ]:
        tr, n_sl = engine(df, atrv, ent, side, ft, fr, **kw)
        rows.append(row(tr, n_sl, label))
    print(f"\n=== {name} ===")
    print(pd.DataFrame(rows).to_string(index=False))

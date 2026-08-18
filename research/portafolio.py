# Portafolio combinado: 9 estrategias validadas, pesos vol-parity (suplentes 1/2), $1000
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/sweep3.py"), encoding="utf-8").read()
exec(src.split("def prep(")[0])   # helpers pine/t3/tema/dch_trend/supertrend_dir/hacolt

MAKER, TAKER, SLIP, WARMUP = 0.0002, 0.00045, 0.0002, 300
CAPITAL = 1000.0

def load_df(coin, tf):
    df = pd.read_parquet(rf"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{coin}_USDT_USDT/{tf}.parquet")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("dt").sort_index()

def load_fund(coin):
    if coin == "SUI":
        f = pd.read_parquet(r"C:/Users/LENOVO/kepler/data/funding/SUIUSDT.parquet")
        return pd.to_datetime(f["funding_time"], unit="ms").values.astype("datetime64[ns]"), f["funding_rate"].astype(float).values
    f = pd.read_parquet(rf"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{coin}_USDT_USDT.parquet")
    return pd.to_datetime(f["ts"], unit="ms").values.astype("datetime64[ns]"), f["funding_rate"].astype(float).values

def atr14(df):
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    return pine_rma(tr, 14).values

def engine(df, atrv, ent, side, exit_mode, exm, ft, fr, atr_mult=2.0, to_h=48):
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    idx = df.index; n = len(df)
    bpd = 96 if (idx[1] - idx[0]).seconds == 900 else 24
    to_bars = to_h * bpd // 24
    iv = idx.values
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
        a, b = np.searchsorted(ft, iv[e_i]), np.searchsorted(ft, iv[t_out])
        net = side * (exit_px / epx - 1) - MAKER - cost_out + (-side * fr[a:b].sum())
        trades.append((idx[e_i], idx[t_out], net, t_out - e_i))
        j_free = t_out + 1
    return pd.DataFrame(trades, columns=["t_in", "t_out", "net", "bars"])

def bxreg(c, up=True):
    r = pine_rsi(pine_ema(c, 20), 15) - 50
    return (r > 0).values if up else (r < 0).values

def bx_trig(c, long=True):
    osc = pine_rsi(pine_ema(c, 5) - pine_ema(c, 20), 15) - 50
    ma = t3(osc, 5)
    if long:
        return ((ma > ma.shift(1)) & (ma.shift(1) < ma.shift(2))).values & (ma < 0).values
    return ((ma < ma.shift(1)) & (ma.shift(1) > ma.shift(2))).values & (ma > 0).values

def tm_trig(c):
    fmacd = pine_ema(c, 8) - pine_ema(c, 21)
    fhist = (fmacd - pine_ema(fmacd, 5)) > 0
    pos = (fhist & (pine_rsi(c, 13) > 50) & (pine_rsi(c, 5) > 50)).values
    return pos & ~np.roll(pos, 1)

def st_flips(df):
    sd = supertrend_dir(df["high"], df["low"], df["close"])
    sdp = np.roll(sd, 1); sdp[0] = sd[0]
    return (sd == 1) & (sdp == -1), (sd == -1) & (sdp == 1), sd

def rib_str(df, dlen=20):
    c, h, l = df["close"], df["high"], df["low"]
    subs = np.stack([dch_trend(c, h, l, dlen - k) for k in range(10)])
    return (subs == 1).sum(axis=0), (subs == -1).sum(axis=0)

def build(name):
    """Devuelve trades df para cada estrategia."""
    if name == "S1 TRX-L BX 1h":
        df = load_df("TRX", "1h"); ft, fr = load_fund("TRX")
        return engine(df, atr14(df), bx_trig(df["close"]), 1, "atrstop", None, ft, fr), df
    if name == "S2 TRX-L TM 1h":
        df = load_df("TRX", "1h"); ft, fr = load_fund("TRX")
        return engine(df, atr14(df), tm_trig(df["close"]), 1, "atrstop", None, ft, fr), df
    if name == "S3 TRX-L ST+HAC+RIB 15m":
        df = load_df("TRX", "15m"); ft, fr = load_fund("TRX")
        up, dn, _ = st_flips(df)
        hc = hacolt(df["open"], df["high"], df["low"], df["close"])
        sl, _ = rib_str(df)
        return engine(df, atr14(df), up & (hc == 1) & (sl >= 8), 1, "flip", dn, ft, fr), df
    if name == "S4 SUI-S BX+reg 1h":
        df = load_df("SUI", "1h"); ft, fr = load_fund("SUI")
        ent = bx_trig(df["close"], long=False) & bxreg(df["close"], up=False)
        return engine(df, atr14(df), ent, -1, "atrstop", None, ft, fr), df
    if name == "S5 LTC-S ST+Don 1h":
        df = load_df("LTC", "1h"); ft, fr = load_fund("LTC")
        up, dn, _ = st_flips(df)
        don = dch_trend(df["close"], df["high"], df["low"], 20)
        return engine(df, atr14(df), dn & (don == -1), -1, "atrstop", None, ft, fr), df
    if name == "S6 XRP-L ST+HAC 1h":
        df = load_df("XRP", "1h"); ft, fr = load_fund("XRP")
        up, dn, _ = st_flips(df)
        hc = hacolt(df["open"], df["high"], df["low"], df["close"])
        return engine(df, atr14(df), up & (hc == 1), 1, "flip", dn, ft, fr), df
    if name == "S7 AVAX-L ST+Don+HAC 15m":
        df = load_df("AVAX", "15m"); ft, fr = load_fund("AVAX")
        up, dn, _ = st_flips(df)
        hc = hacolt(df["open"], df["high"], df["low"], df["close"])
        don = dch_trend(df["close"], df["high"], df["low"], 20)
        return engine(df, atr14(df), up & (don == 1) & (hc == 1), 1, "flip", dn, ft, fr), df
    if name == "S8 ETH-S BX+Don 1h":
        df = load_df("ETH", "1h"); ft, fr = load_fund("ETH")
        don = dch_trend(df["close"], df["high"], df["low"], 20)
        ent = bx_trig(df["close"], long=False) & (don == -1)
        return engine(df, atr14(df), ent, -1, "atrstop", None, ft, fr), df
    if name == "S9 BTC-L RIB+BXreg+ST 1h":
        df = load_df("BTC", "1h"); ft, fr = load_fund("BTC")
        sl, _ = rib_str(df)
        full = sl == 10
        _, _, sd = st_flips(df)
        ent = full & ~np.roll(full, 1) & bxreg(df["close"]) & (sd == 1)
        return engine(df, atr14(df), ent, 1, "atrstop", None, ft, fr), df

ROLES = {"S1 TRX-L BX 1h": 1.0, "S2 TRX-L TM 1h": 1.0, "S3 TRX-L ST+HAC+RIB 15m": 1.0,
         "S4 SUI-S BX+reg 1h": 1.0, "S5 LTC-S ST+Don 1h": 1.0, "S6 XRP-L ST+HAC 1h": 1.0,
         "S7 AVAX-L ST+Don+HAC 15m": 1.0, "S8 ETH-S BX+Don 1h": 0.5, "S9 BTC-L RIB+BXreg+ST 1h": 0.5}

daily, stats = {}, {}
for name in ROLES:
    tr, df = build(name)
    bpd = 96 if "15m" in name else 24
    r = tr["net"]
    d = pd.Series(r.values, index=tr["t_out"].values).resample("1D").sum()
    daily[name] = d
    months = (df.index[-1] - df.index[WARMUP]).days / 30.44
    eq = (1 + r).cumprod()
    mdd = ((eq / eq.cummax()) - 1).min()
    yrs = (df.index[-1] - df.index[WARMUP]).days / 365
    y = tr.groupby(tr["t_in"].dt.year)["net"].apply(lambda g: np.prod(1 + g) - 1)
    dd = pd.Series(r.values, index=tr["t_in"].values).resample("1D").sum()
    stats[name] = dict(
        n=len(r), tpm=len(r) / months, wr=(r > 0).mean(),
        win_h=tr.loc[r > 0, "bars"].mean() * 24 / bpd, loss_h=tr.loc[r <= 0, "bars"].mean() * 24 / bpd,
        expect=r.mean(), pf=r[r > 0].sum() / abs(r[r <= 0].sum()),
        cagr=eq.iloc[-1] ** (1 / yrs) - 1, mdd=mdd,
        sharpe=dd.mean() / dd.std() * np.sqrt(365),
        ypos=f"{(y>0).sum()}/{len(y)}", y2026=y.get(2026, np.nan))

D = pd.DataFrame(daily).fillna(0.0)
D = D[D.index >= "2023-09-01"]

print("=== CORRELACION entre estrategias (retornos diarios) ===")
corr = D.corr().round(2)
corr.index = [n[:6] for n in corr.index]; corr.columns = [n[:6] for n in corr.columns]
print(corr.to_string())

vols = D.std()
w = pd.Series({n: ROLES[n] / vols[n] for n in ROLES})
w = w / w.sum()
port = (D * w).sum(axis=1)
eq = (1 + port).cumprod()
mdd = ((eq / eq.cummax()) - 1).min()
sharpe = port.mean() / port.std() * np.sqrt(365)
yrs_p = (D.index[-1] - D.index[0]).days / 365
cagr = eq.iloc[-1] ** (1 / yrs_p) - 1
monthly = eq.resample("ME").last().pct_change().dropna()
ym = port.groupby(port.index.year).apply(lambda g: (1 + g).prod() - 1)

print("\n=== PESOS (vol-parity x rol) ===")
for n in ROLES:
    print(f"  {n:32s} w={w[n]*100:5.1f}%  -> ${w[n]*CAPITAL:.0f} de ${CAPITAL:.0f}")

print(f"\n=== PORTAFOLIO COMBINADO (sep2023->jun2026, ${CAPITAL:.0f}) ===")
print(f"CAGR: {cagr*100:+.1f}%   Sharpe: {sharpe:.2f}   MaxDD: {mdd*100:.1f}%")
print(f"Meses positivos: {(monthly>0).mean()*100:.0f}%   Mejor mes: {monthly.max()*100:+.1f}%   Peor mes: {monthly.min()*100:+.1f}%")
print(f"Por anno: " + "  ".join(f"{y}: {v*100:+.1f}%" for y, v in ym.items()))
print(f"Ganancia media mensual sobre ${CAPITAL:.0f}: ${monthly.mean()*CAPITAL:+.1f}")
print(f"Equity final de ${CAPITAL:.0f} (33 meses): ${eq.iloc[-1]*CAPITAL:,.0f}")

print("\n=== TABLA FINAL POR ESTRATEGIA ===")
rows = []
for n in ROLES:
    s = stats[n]
    alloc = w[n] * CAPITAL
    rows.append({
        "Estrategia": n, "Peso": f"{w[n]*100:.0f}%", "Asignado": f"${alloc:.0f}",
        "Tr/mes": round(s["tpm"], 1), "WR": f"{s['wr']:.0%}",
        "Hg(h)": round(s["win_h"], 1), "Hp(h)": round(s["loss_h"], 1),
        "Exp/tr": f"{s['expect']*100:+.2f}%", "PF": round(s["pf"], 2),
        "CAGR": f"{s['cagr']*100:+.0f}%", "MaxDD": f"{s['mdd']*100:.0f}%",
        "Sharpe": round(s["sharpe"], 2), "Y+": s["ypos"], "2026": f"{s['y2026']*100:+.0f}%",
        "$/trade(asig)": f"${alloc*s['expect']:+.2f}",
        "$/mes(asig)": f"${alloc*s['expect']*s['tpm']:+.1f}",
        "$/tr($1000solo)": f"${CAPITAL*s['expect']:+.2f}",
        "$/mes($1000solo)": f"${CAPITAL*s['expect']*s['tpm']:+.0f}",
    })
print(pd.DataFrame(rows).to_string(index=False))

# Barrido 3: + Donchian Trend Ribbon y HACOLT sobre el stack existente
# Gatillos nuevos {RIB, HAC} x filtros (subsets<=2 de los otros 5)
# Gatillos viejos {BX, ST, TM, TMWT} x subsets que incluyan RIB o HAC (no re-validar)
import numpy as np
import pandas as pd
from itertools import combinations

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT", "TRX", "LTC", "SUI"]
TFS = {"15m": 96, "1h": 24}
MAKER, TAKER, SLIP = 0.0002, 0.00045, 0.0002
ATR_MULT, TIMEOUT_H, WARMUP = 2.0, 48, 300

def pine_ema(s, n): return s.ewm(span=n, adjust=False).mean()
def pine_sma(s, n): return s.rolling(n).mean()
def pine_rma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()
def pine_rsi(s, n):
    d = s.diff()
    return 100 - 100 / (1 + pine_rma(d.clip(lower=0), n) / pine_rma((-d).clip(lower=0), n))
def t3(s, n, b=0.7):
    e1 = pine_ema(s, n); e2 = pine_ema(e1, n); e3 = pine_ema(e2, n)
    e4 = pine_ema(e3, n); e5 = pine_ema(e4, n); e6 = pine_ema(e5, n)
    return -b**3*e6 + (3*b**2+3*b**3)*e5 + (-6*b**2-3*b-3*b**3)*e4 + (1+3*b+b**3+3*b**2)*e3
def tema(s, n):
    e1 = pine_ema(s, n); e2 = pine_ema(e1, n); e3 = pine_ema(e2, n)
    return 3 * (e1 - e2) + e3
def dch_trend(c, h, l, n):
    hh = h.rolling(n).max().shift(1); ll = l.rolling(n).min().shift(1)
    raw = np.where(c > hh, 1.0, np.where(c < ll, -1.0, np.nan))
    return pd.Series(raw, index=c.index).ffill().fillna(0.0).values
def supertrend_dir(h, l, c, period=10, factor=3.0):
    hl2 = (h + l) / 2
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = pine_rma(tr, period).values
    up = hl2.values + factor * atr; dn = hl2.values - factor * atr
    cl = c.values; n = len(cl)
    d = np.ones(n); fu, fd = up.copy(), dn.copy()
    for i in range(1, n):
        fu[i] = up[i] if (up[i] < fu[i-1] or cl[i-1] > fu[i-1]) else fu[i-1]
        fd[i] = dn[i] if (dn[i] > fd[i-1] or cl[i-1] < fd[i-1]) else fd[i-1]
        d[i] = (-1 if cl[i] < fd[i] else 1) if d[i-1] == 1 else (1 if cl[i] > fu[i] else -1)
    return d

def hacolt(o, h, l, c, length=55, ema_len=60, csf=1.1):
    ohlc4 = (o + h + l + c) / 4
    n = len(c)
    haOpen = np.empty(n); haOpen[0] = ohlc4.iloc[0]
    o4 = ohlc4.values
    for i in range(1, n):
        haOpen[i] = (haOpen[i-1] + o4[i]) / 2
    haClose = (haOpen + np.maximum(h.values, haOpen) + np.minimum(l.values, haOpen) + o4) / 4
    haC = pd.Series(haClose, index=c.index)
    thaC = tema(haC, length)
    thl2 = tema((h + l) / 2, length)
    haSmooth = 2 * thaC - tema(thaC, length)
    hlSmooth = 2 * thl2 - tema(thl2, length)
    cl, op_, hi, lo = c.values, o.values, h.values, l.values
    shortCandle = np.abs(cl - op_) < (hi - lo) * csf
    haCl = haClose; haOp = haOpen
    prev = lambda a: np.roll(a, 1)
    haUp = haCl >= haOp
    keepn1 = (haUp & prev(haUp)) | (cl >= haCl) | (hi > prev(hi)) | (lo > prev(lo)) | (hlSmooth.values >= haSmooth.values)
    keepall1 = keepn1 | (prev(keepn1) & (cl >= op_)) | (cl >= prev(cl))
    keep13 = shortCandle & (hi >= prev(lo))
    utr = keepall1 | (prev(keepall1) & keep13)
    haDn = haCl < haOp
    keepn2 = (haDn & prev(haDn)) | (hlSmooth.values < haSmooth.values)
    keep23 = shortCandle & (lo <= prev(hi))
    keepall2 = keepn2 | (prev(keepn2) & (cl < op_)) | (cl < prev(cl))
    dtr = keepall2 | (prev(keepall2) & keep23)
    upw = (~dtr) & prev(dtr) & utr
    dnw = (~utr) & prev(utr) & dtr
    upwOff = np.zeros(n, bool)
    for i in range(1, n):
        upwOff[i] = upw[i] if upw[i] != dnw[i] else upwOff[i-1]
    buySig = upw | ((~dnw) & upwOff)
    ltSell = cl < pine_ema(c, ema_len).values
    neutral = np.zeros(n, bool)
    for i in range(1, n):
        neutral[i] = buySig[i] or (False if ltSell[i] else neutral[i-1])
    return np.where(buySig, 1, np.where(neutral, 0, -1))

def prep(coin, tf):
    df = pd.read_parquet(rf"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{coin}_USDT_USDT/{tf}.parquet")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    # B-Xtrender
    osc = pine_rsi(pine_ema(c, 5) - pine_ema(c, 20), 15) - 50
    reg = pine_rsi(pine_ema(c, 20), 15) - 50
    ma = t3(osc, 5)
    green = ((ma > ma.shift(1)) & (ma.shift(1) < ma.shift(2))).values
    red = ((ma < ma.shift(1)) & (ma.shift(1) > ma.shift(2))).values
    bx_l, bx_s = green & (ma < 0).values, red & (ma > 0).values
    # Donchian / ribbon
    don = dch_trend(c, h, l, 20)
    subs = np.stack([dch_trend(c, h, l, 20 - k) for k in range(10)])
    strength_l = (subs == 1).sum(axis=0)    # de 10
    strength_s = (subs == -1).sum(axis=0)
    rib_full_l, rib_full_s = strength_l == 10, strength_s == 10
    rib_trig_l = rib_full_l & ~np.roll(rib_full_l, 1)
    rib_trig_s = rib_full_s & ~np.roll(rib_full_s, 1)
    # Supertrend
    sd = supertrend_dir(h, l, c)
    sdp = np.roll(sd, 1); sdp[0] = sd[0]
    st_up, st_dn = (sd == 1) & (sdp == -1), (sd == -1) & (sdp == 1)
    # Trend Meter + WaveTrend
    fmacd = pine_ema(c, 8) - pine_ema(c, 21)
    fhist = (fmacd - pine_ema(fmacd, 5)) > 0
    tm3pos = (fhist & (pine_rsi(c, 13) > 50) & (pine_rsi(c, 5) > 50)).values
    tm3neg = (~fhist & (pine_rsi(c, 13) < 50) & (pine_rsi(c, 5) < 50)).values
    tm_bg_p, tm_bg_n = tm3pos & ~np.roll(tm3pos, 1), tm3neg & ~np.roll(tm3neg, 1)
    ap = (h + l + c) / 3
    esa = pine_ema(ap, 9); de = pine_ema((ap - esa).abs(), 9)
    wt1 = pine_ema((ap - esa) / (0.015 * de), 12); wt2 = pine_sma(wt1, 3)
    diff = (wt1 - wt2).values; dp = np.roll(diff, 1); dp[0] = 0
    wt_up, wt_dn = (diff >= 0) & (dp < 0), (diff <= 0) & (dp > 0)
    # HACOLT
    hc = hacolt(o, h, l, c)
    hcp = np.roll(hc, 1); hcp[0] = hc[0]
    hac_trig_l, hac_trig_s = (hc == 1) & (hcp != 1), (hc == -1) & (hcp != -1)
    # ATR
    tr_ = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atrv = pine_rma(tr_, 14).values
    triggers = {"BX": (bx_l, bx_s), "ST": (st_up, st_dn), "TM": (tm_bg_p, tm_bg_n),
                "TMWT": (wt_up & tm3pos, wt_dn & tm3neg),
                "RIB": (rib_trig_l, rib_trig_s), "HAC": (hac_trig_l, hac_trig_s)}
    regimes = {"Don": (don == 1, don == -1), "ST": (sd == 1, sd == -1),
               "TM": (tm3pos, tm3neg), "BXreg": ((reg > 0).values, (reg < 0).values),
               "RIB": (strength_l >= 8, strength_s >= 8), "HAC": (hc == 1, hc == -1)}
    return df, atrv, triggers, regimes, (st_dn, st_up)

def run(df, atrv, ent, side, exit_mode, exm=None):
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    idx = df.index; n = len(df)
    bpd = 96 if (idx[1] - idx[0]).seconds == 900 else 24
    to_bars = TIMEOUT_H * bpd // 24
    trades, j_free = [], 0
    for i_sig in np.flatnonzero(ent[WARMUP:n-2]) + WARMUP:
        if i_sig < j_free: continue
        e_i = i_sig + 1; epx = op[e_i]
        stop = epx - side * ATR_MULT * atrv[i_sig]
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
        net = side * (exit_px / epx - 1) - MAKER - cost_out
        trades.append((idx[e_i], net))
        j_free = t_out + 1
    return pd.DataFrame(trades, columns=["t_in", "net"])

OLD_FILTERS = {"BX": ["Don", "ST", "TM"], "ST": ["Don", "TM", "BXreg"],
               "TM": ["Don", "ST", "BXreg"], "TMWT": ["Don", "ST", "BXreg"]}
rows = []
for coin in COINS:
    for tf in TFS:
        df, atrv, triggers, regimes, st_exits = prep(coin, tf)
        jobs = []
        for tname in ("RIB", "HAC"):                       # gatillos nuevos
            avail = [f for f in regimes if f != tname]
            subsets = [frozenset(s) for k in (0, 1, 2) for s in combinations(avail, k)]
            jobs += [(tname, s) for s in subsets]
        for tname, olds in OLD_FILTERS.items():            # gatillos viejos + filtro nuevo
            subsets = [frozenset(["RIB"]), frozenset(["HAC"]), frozenset(["RIB", "HAC"])]
            subsets += [frozenset(["RIB", o]) for o in olds] + [frozenset(["HAC", o]) for o in olds]
            jobs += [(tname, s) for s in subsets]
        for tname, sub in jobs:
            for side in (1, -1):
                ent = (triggers[tname][0 if side > 0 else 1]).copy()
                for f in sub:
                    ent &= regimes[f][0 if side > 0 else 1]
                exits = [("atrstop", None)]
                if tname == "ST":
                    exits.append(("flip", st_exits[0] if side > 0 else st_exits[1]))
                for exname, exm in exits:
                    tr = run(df, atrv, ent, side, exname, exm)
                    if len(tr) < 40: continue
                    r = tr["net"]
                    years = tr.groupby(tr["t_in"].dt.year)["net"].apply(lambda g: np.prod(1 + g) - 1)
                    def pf_(x):
                        neg = x[x <= 0].sum()
                        return x[x > 0].sum() / abs(neg) if neg != 0 else np.inf
                    rows.append(dict(
                        coin=coin, tf=tf, side="L" if side > 0 else "S", trig=tname,
                        filt="+".join(sorted(sub)) if sub else "solo", exit=exname,
                        n=len(r), pf=round(pf_(r), 2), expect=round(r.mean()*100, 4),
                        total=round((np.prod(1+r)-1)*100, 1),
                        y_pos=int((years > 0).sum()), y_tot=len(years),
                        y2026=round(years.get(2026, np.nan)*100, 1) if 2026 in years.index else np.nan))
    print(coin, "ok", flush=True)

res = pd.DataFrame(rows)
res.to_csv(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\results_sweep3.csv", index=False)
print(f"\nTotal: {len(res)} backtests -> results_sweep3.csv")

print("\n=== Por GATILLO (mediana) ===")
print(res.groupby(["trig", "tf"]).agg(runs=("n", "size"), med_pf=("pf", "median"),
      pct_4y=("y_pos", lambda s: round((s >= 4).mean()*100))).to_string())

surv = res[(res.y_pos == res.y_tot) & (res.y_tot >= 4) & (res.n >= 100) & (res.pf >= 1.10)]
surv = surv.drop_duplicates(subset=["coin", "tf", "side", "n", "pf", "total"])  # dedupe filtros redundantes
print("\n=== SUPERVIVIENTES (todos los anos +, n>=100, PF>=1.10, dedup) ===")
print(surv.sort_values("pf", ascending=False).head(35).to_string(index=False))

near = res[(res.y_pos == res.y_tot - 1) & (res.y_tot >= 4) & (res.y2026 > 0) & (res.n >= 150) & (res.pf >= 1.20)]
near = near.drop_duplicates(subset=["coin", "tf", "side", "n", "pf", "total"])
print("\n=== Casi (3/4 con 2026+, n>=150, PF>=1.20, dedup) ===")
print(near.sort_values("pf", ascending=False).head(15).to_string(index=False))

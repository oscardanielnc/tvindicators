# Barrido 2: 4 indicadores (B-Xtrender, Donchian, Supertrend, Trend Meter)
# Gatillos x filtros de regimen (AND de subconjuntos) x 13 monedas x {15m,1h} x {L,S}
# Salida: ATR-stop 2.0 + timeout 48h (validada en sweep1). ST tambien flip-a-flip.
import numpy as np
import pandas as pd
from itertools import combinations

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT", "TRX", "LTC", "SUI"]
TFS = {"15m": 96, "1h": 24}
MAKER, TAKER, SLIP = 0.0002, 0.00045, 0.0002
OOS_START = pd.Timestamp("2026-01-01")
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
def donch_main(c, h, l, n=20):
    hh = h.rolling(n).max().shift(1); ll = l.rolling(n).min().shift(1)
    raw = np.where(c > hh, 1.0, np.where(c < ll, -1.0, np.nan))
    return pd.Series(raw, index=c.index).ffill().fillna(0.0)

def supertrend_dir(h, l, c, period=10, factor=3.0):
    """Devuelve +1 uptrend / -1 downtrend (convencion: +1 = precio sobre la banda)."""
    hl2 = (h + l) / 2
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = pine_rma(tr, period).values
    up = (hl2 + factor * pd.Series(atr, index=c.index)).values
    dn = (hl2 - factor * pd.Series(atr, index=c.index)).values
    cl = c.values
    n = len(cl)
    d = np.ones(n)
    fu, fd = up.copy(), dn.copy()
    for i in range(1, n):
        fu[i] = up[i] if (up[i] < fu[i-1] or cl[i-1] > fu[i-1]) else fu[i-1]
        fd[i] = dn[i] if (dn[i] > fd[i-1] or cl[i-1] < fd[i-1]) else fd[i-1]
        if d[i-1] == 1:
            d[i] = -1 if cl[i] < fd[i] else 1
        else:
            d[i] = 1 if cl[i] > fu[i] else -1
    return d  # +1 up, -1 down

def prep(coin, tf):
    df = pd.read_parquet(rf"C:/Users/LENOVO/Oscilion/data/ohlcv/binanceusdm/{coin}_USDT_USDT/{tf}.parquet")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    # --- B-Xtrender ---
    osc = pine_rsi(pine_ema(c, 5) - pine_ema(c, 20), 15) - 50
    reg = pine_rsi(pine_ema(c, 20), 15) - 50
    ma = t3(osc, 5)
    green = ((ma > ma.shift(1)) & (ma.shift(1) < ma.shift(2))).values
    red = ((ma < ma.shift(1)) & (ma.shift(1) > ma.shift(2))).values
    bx_l, bx_s = green & (ma < 0).values, red & (ma > 0).values
    bxreg_l, bxreg_s = (reg > 0).values, (reg < 0).values
    # --- Donchian ---
    don = donch_main(c, h, l).values
    # --- Supertrend ---
    sd = supertrend_dir(h, l, c)
    sd_prev = np.roll(sd, 1); sd_prev[0] = sd[0]
    st_flip_up = (sd == 1) & (sd_prev == -1)
    st_flip_dn = (sd == -1) & (sd_prev == 1)
    # --- Trend Meter (defaults) ---
    fmacd = pine_ema(c, 8) - pine_ema(c, 21)
    fhist = (fmacd - pine_ema(fmacd, 5)) > 0
    tm3pos = (fhist & (pine_rsi(c, 13) > 50) & (pine_rsi(c, 5) > 50)).values
    tm3neg = (~fhist & (pine_rsi(c, 13) < 50) & (pine_rsi(c, 5) < 50)).values
    tm_bg_pos = tm3pos & ~np.roll(tm3pos, 1)
    tm_bg_neg = tm3neg & ~np.roll(tm3neg, 1)
    # --- WaveTrend ---
    ap = (h + l + c) / 3
    esa = pine_ema(ap, 9)
    de = pine_ema((ap - esa).abs(), 9)
    wt1 = pine_ema((ap - esa) / (0.015 * de), 12)
    wt2 = pine_sma(wt1, 3)
    diff = (wt1 - wt2).values
    diff_prev = np.roll(diff, 1); diff_prev[0] = 0
    wt_x_up = (diff >= 0) & (diff_prev < 0)
    wt_x_dn = (diff <= 0) & (diff_prev > 0)
    # ATR para stops
    tr_ = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atrv = pine_rma(tr_, 14).values
    triggers = {
        "BX":   (bx_l, bx_s),
        "ST":   (st_flip_up, st_flip_dn),
        "TM":   (tm_bg_pos, tm_bg_neg),
        "TMWT": (wt_x_up & tm3pos, wt_x_dn & tm3neg),
    }
    regimes = {
        "Don":   (don == 1, don == -1),
        "ST":    (sd == 1, sd == -1),
        "TM":    (tm3pos, tm3neg),
        "BXreg": (bxreg_l, bxreg_s),
    }
    return df, atrv, triggers, regimes, (st_flip_dn, st_flip_up)

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

SKIP_BX = [frozenset(), frozenset(["Don"])]   # ya validados en sweep1
rows = []
for coin in COINS:
    for tf in TFS:
        df, atrv, triggers, regimes, st_exits = prep(coin, tf)
        for tname, (tl, ts_) in triggers.items():
            fil_names = [f for f in regimes if f != tname and not (tname == "TMWT" and f == "TM")
                         and not (tname == "BX" and f == "BXreg")]
            subsets = [frozenset(s) for k in range(len(fil_names) + 1) for s in combinations(fil_names, k)]
            for sub in subsets:
                if tname == "BX" and sub in SKIP_BX: continue
                for side in (1, -1):
                    ent = (tl if side > 0 else ts_).copy()
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
                        is_m = tr["t_in"] < OOS_START
                        def pf_(x):
                            neg = x[x <= 0].sum()
                            return x[x > 0].sum() / abs(neg) if neg != 0 else np.inf
                        rows.append(dict(
                            coin=coin, tf=tf, side="L" if side > 0 else "S", trig=tname,
                            filt="+".join(sorted(sub)) if sub else "solo", exit=exname,
                            n=len(r), pf=round(pf_(r), 2), expect=round(r.mean()*100, 4),
                            total=round((np.prod(1+r)-1)*100, 1),
                            is_pf=round(pf_(r[is_m]), 2) if is_m.sum() >= 30 else np.nan,
                            oos_exp=round(r[~is_m].mean()*100, 4) if (~is_m).sum() >= 5 else np.nan,
                            y_pos=int((years > 0).sum()), y_tot=len(years),
                            y2026=round(years.get(2026, np.nan)*100, 1) if 2026 in years.index else np.nan))
    print(coin, "ok", flush=True)

res = pd.DataFrame(rows)
res.to_csv(r"C:\Users\LENOVO\tvindicators\results_sweep2.csv", index=False)
print(f"\nTotal: {len(res)} backtests -> results_sweep2.csv")

print("\n=== Por GATILLO (mediana entre todos los runs) ===")
agg = res.groupby(["trig", "exit", "tf"]).agg(
    runs=("n", "size"), med_pf=("pf", "median"), med_exp=("expect", "median"),
    pct_4y=("y_pos", lambda s: round((s >= 4).mean()*100)))
print(agg.to_string())

print("\n=== SUPERVIVIENTES: positivos TODOS los anos (>=4 anos de historia), n>=100, PF>=1.10 ===")
surv = res[(res.y_pos == res.y_tot) & (res.y_tot >= 4) & (res.n >= 100) & (res.pf >= 1.10)]
surv = surv.sort_values("pf", ascending=False)
print(surv.head(40).to_string(index=False))

print("\n=== Casi-supervivientes: 3/4 anos positivos con 2026 positivo, n>=150, PF>=1.15 ===")
near = res[(res.y_pos == res.y_tot - 1) & (res.y_tot >= 4) & (res.y2026 > 0) & (res.n >= 150) & (res.pf >= 1.15)]
print(near.sort_values("pf", ascending=False).head(20).to_string(index=False))

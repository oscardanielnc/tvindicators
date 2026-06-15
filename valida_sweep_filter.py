# Validacion formal del filtro de barrido sobre S1-TRX-L y S4-SUI-S.
# Anade lo que faltaba al PoC: FUNDING real + SENSIBILIDAD de parametros (W,MAXAGE,F) +
# maxDD. Pregunta honesta: ¿el filtro bate al baseline de forma ROBUSTA (no en un solo
# parametro con suerte) una vez metido el funding? Si la mayoria de la grilla NO mejora,
# no vale la pena.
import numpy as np
import pandas as pd
from tvbot import indicators as I

OHLCV = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/1h.parquet"
FUND = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{c}_USDT_USDT.parquet"
MAKER, TAKER, SLIP = 0.0002, 0.00045, 0.0002
WARM = 300
TO_BARS = 48  # 48h en 1h

def load(coin):
    df = pd.read_parquet(OHLCV.format(c=coin)); df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("dt").sort_index()
    fd = pd.read_parquet(FUND.format(c=coin)).sort_values("ts")
    fr_ts = fd["ts"].values.astype("int64")
    cumfr = np.concatenate([[0.0], np.cumsum(fd["funding_rate"].values)])
    return df, fr_ts, cumfr

def fund_sum(fr_ts, cumfr, entry_ms, exit_ms):
    a = np.searchsorted(fr_ts, entry_ms, "right")
    b = np.searchsorted(fr_ts, exit_ms, "right")
    return cumfr[b] - cumfr[a]

def detect_sweeps(df, W, MAXAGE):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    ph = (df["high"] == df["high"].rolling(2*W+1, center=True).max()).values
    pl = (df["low"] == df["low"].rolling(2*W+1, center=True).min()).values
    n = len(df); sL = np.zeros(n, bool); sS = np.zeros(n, bool)
    last_sh = last_sl = np.nan; sh_age = sl_age = 10**9; sh_used = sl_used = True
    for t in range(WARM, n):
        j = t - W
        if ph[j]: last_sh, sh_age, sh_used = h[j], 0, False
        if pl[j]: last_sl, sl_age, sl_used = l[j], 0, False
        sh_age += 1; sl_age += 1
        if (not sh_used) and sh_age <= MAXAGE and not np.isnan(last_sh) and h[t] > last_sh and c[t] < last_sh:
            sS[t] = True; sh_used = True
        if (not sl_used) and sl_age <= MAXAGE and not np.isnan(last_sl) and l[t] < last_sl and c[t] > last_sl:
            sL[t] = True; sl_used = True
    return sL, sS

def recent(sig, F):
    out = np.zeros(len(sig), bool); s = np.where(sig)[0]
    for k in s:
        out[k:k+F] = True   # vale desde la vela del sweep hasta F-1 despues
    return out

def run(df, fr_ts, cumfr, side, entry, amult):
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    atr = I.atr14(df).values; idx = df.index; n = len(df)
    ts_ms = (idx.view("int64") // 10**6)
    trades = []; i = WARM
    while i < n - 1:
        if not entry[i]:
            i += 1; continue
        e_i = i + 1; epx = op[e_i]
        stop = epx - side * amult * atr[i]
        exit_px = cost_out = None; j = e_i
        while j < n - 1:
            hit = lo[j] <= stop if side > 0 else hi[j] >= stop
            if hit:
                exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                cost_out = TAKER + SLIP; ej = j; break
            if j - e_i + 1 >= TO_BARS:
                exit_px, cost_out, ej = op[j + 1], MAKER, j + 1; break
            j += 1
        if exit_px is None: break
        gross = side * (exit_px / epx - 1)
        fs = fund_sum(fr_ts, cumfr, ts_ms[e_i], ts_ms[ej])
        ret = gross - MAKER - cost_out - side * fs        # funding: long paga si fs>0
        trades.append((idx[e_i], ret)); i = ej + 1
    return pd.DataFrame(trades, columns=["t_in", "ret"]) if trades else None

def metrics(tr, label):
    if tr is None or len(tr) == 0: return dict(var=label, trades=0)
    r = tr["ret"]; eq = (1+r).cumprod(); mdd = ((eq/eq.cummax())-1).min()
    w, ls = r[r>0], r[r<=0]; pf = w.sum()/abs(ls.sum()) if ls.sum()!=0 else np.inf
    by = tr.assign(y=tr["t_in"].dt.year).groupby("y")["ret"].mean()*1e4
    return dict(var=label, trades=len(tr), wr=f"{(r>0).mean():.0%}", PF=round(pf,2),
                exp_bps=round(r.mean()*1e4,1), tot=f"{(eq.iloc[-1]-1)*100:+.0f}%",
                maxDD=f"{mdd*100:.0f}%", yr_ok=f"{(by>0).sum()}/{by.size}",
                yrs=" ".join(f"{y%100}:{v:+.0f}" for y,v in by.items()))

CASES = {
    "S1-TRX-L": dict(coin="TRX", side=+1, amult=2.0, grid_F=[4,6,8,12],
                     entry=lambda c,h,l: I.bx_parts(c)[0]),
    "S4-SUI-S": dict(coin="SUI", side=-1, amult=2.0, grid_F=[12,18,24,36],
                     entry=lambda c,h,l: I.bx_parts(c)[1] & I.bx_parts(c)[3]),
}
GRID_W = [3, 5, 8]; GRID_MAXAGE = [100, 200, 300]

for sid, cf in CASES.items():
    df, fr_ts, cumfr = load(cf["coin"])
    c, h, l = df["close"], df["high"], df["low"]
    entry = cf["entry"](c, h, l)
    side, amult = cf["side"], cf["amult"]
    base = run(df, fr_ts, cumfr, side, entry, amult)
    bm = metrics(base, "BASELINE (con funding)")
    print(f"\n{'='*108}\n{sid}  — validacion con funding + sensibilidad")
    print(pd.DataFrame([bm]).to_string(index=False))
    base_exp = bm["exp_bps"]
    # grilla de sensibilidad
    rows = []; beat = 0; total = 0; robust = 0
    for W in GRID_W:
        for MA in GRID_MAXAGE:
            sL, sS = detect_sweeps(df, W, MA)
            sweep = sL if side > 0 else sS
            for F in cf["grid_F"]:
                filt = entry & recent(sweep, F)
                m = metrics(run(df, fr_ts, cumfr, side, filt, amult), f"W{W} MA{MA} F{F}")
                rows.append(m); total += 1
                if m.get("trades", 0) >= 40:
                    if m["exp_bps"] > base_exp: beat += 1
                    if m["exp_bps"] > base_exp and m["yr_ok"] == "4/4": robust += 1
    print(f"\n  Sensibilidad ({total} celdas; baseline exp={base_exp} bps):")
    print(f"  -> celdas (>=40 trades) que BATEN expectativa baseline: {beat}")
    print(f"  -> celdas que ademas mantienen 4/4 anios positivos:     {robust}")
    g = pd.DataFrame([r for r in rows if r.get("trades",0) >= 40])
    print(g.sort_values("exp_bps", ascending=False).to_string(index=False))

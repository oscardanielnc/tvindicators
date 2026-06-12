# Diagnostico B-Xtrender: (A) valor predictivo puro de la senal (forward returns vs azar)
# (B) salidas largas (regimen) y escenario costos maker
import numpy as np
import pandas as pd

FEE_TAKER, FEE_MAKER, SLIP = 0.00045, 0.0002, 0.0002
COST_TAKER_RT = 2 * (FEE_TAKER + SLIP)   # 0.13%
COST_MAKER_RT = 2 * FEE_MAKER            # 0.04% (limite, sin slippage)
OOS_START = pd.Timestamp("2026-01-01")

def pine_ema(s, n): return s.ewm(span=n, adjust=False).mean()
def pine_rma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()
def pine_rsi(s, n):
    d = s.diff()
    return 100 - 100 / (1 + pine_rma(d.clip(lower=0), n) / pine_rma((-d).clip(lower=0), n))
def t3(s, n, b=0.7):
    e1 = pine_ema(s, n); e2 = pine_ema(e1, n); e3 = pine_ema(e2, n)
    e4 = pine_ema(e3, n); e5 = pine_ema(e4, n); e6 = pine_ema(e5, n)
    return -b**3*e6 + (3*b**2+3*b**3)*e5 + (-6*b**2-3*b-3*b**3)*e4 + (1+3*b+b**3+3*b**2)*e3
def donch(close, high, low, n, strict):
    hh = high.rolling(n).max().shift(1); ll = low.rolling(n).min().shift(1)
    raw = np.where(close >= hh if strict else close > hh, 1.0,
          np.where(close <= ll if strict else close < ll, -1.0, np.nan))
    return pd.Series(raw, index=close.index).ffill().fillna(0.0)

def build(tf):
    df = pd.read_parquet(rf"C:/Users/LENOVO/Oscilion/data/ohlcv/binanceusdm/BTC_USDT_USDT/{tf}.parquet")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    c, h, l = df["close"], df["high"], df["low"]
    osc = pine_rsi(pine_ema(c, 5) - pine_ema(c, 20), 15) - 50
    reg = pine_rsi(pine_ema(c, 20), 15) - 50
    ma = t3(osc, 5)
    green = (ma > ma.shift(1)) & (ma.shift(1) < ma.shift(2))
    red = (ma < ma.shift(1)) & (ma.shift(1) > ma.shift(2))
    main = donch(c, h, l, 20, False)
    return df, ma, reg, green, red, main

# ---------- (A) valor predictivo puro ----------
print("=" * 80)
print("(A) FORWARD RETURNS tras senal V2-long (verde & T3<0 & regimen>0) vs AZAR")
print("    senal en barra i -> retorno open(i+1) a open(i+1+H). t-stat aprox.")
for tf, bars_per_day in [("15m", 96), ("1h", 24)]:
    df, ma, reg, green, red, main = build(tf)
    op = df["open"]
    sigL = (green & (ma < 0) & (reg > 0)).shift(1).fillna(False)  # ejecutable en open i+1
    sigS = (red & (ma > 0) & (reg < 0)).shift(1).fillna(False)
    horizons = [4, 8, 16, 32, 64] if tf == "1h" else [16, 32, 64, 128, 256]
    rows = []
    for H in horizons:
        fwd = (op.shift(-H) / op - 1)
        base_m, base_s = fwd.mean(), fwd.std()
        for name, sig, sign in [("LONG", sigL, 1), ("SHORT", sigS, -1)]:
            r = fwd[sig.values] * sign
            edge = r.mean() - sign * base_m
            tstat = edge / (base_s / np.sqrt(len(r))) if len(r) > 2 else np.nan
            rows.append({"tf": tf, "lado": name, "H(horas)": round(H * 24 / bars_per_day, 1),
                         "n": len(r), "ret_medio%": round(r.mean()*100, 3),
                         "edge_vs_azar%": round(edge*100, 3), "t-stat": round(tstat, 2)})
    print(pd.DataFrame(rows).to_string(index=False))
    print()

# ---------- (B) salidas largas + escenario maker, 1h ----------
print("=" * 80)
print("(B) 1h, entrada V2: salida por REGIMEN (no circulo) + escenarios de costo")
df, ma, reg, green, red, main = build("1h")
op = df["open"].values; idx = df.index
entry_l = (green & (ma < 0) & (reg > 0)).values
entry_s = (red & (ma > 0) & (reg < 0)).values
exits = {
    "salida circulo opuesto": ((red).values, (green).values),
    "salida regimen cruza 0": ((reg < 0).values, (reg > 0).values),
    "salida circulo opuesto Y regimen en contra": ((red & (reg < 0)).values, (green & (reg > 0)).values),
}
rows = []
for exname, (xL, xS) in exits.items():
    trades, pos = [], 0
    for i in range(300, len(df) - 1):
        if pos == 1 and xL[i]:
            trades.append((idx[entry_i], op[i+1] / epx - 1, i + 1 - entry_i)); pos = 0
        elif pos == -1 and xS[i]:
            trades.append((idx[entry_i], epx / op[i+1] - 1, i + 1 - entry_i)); pos = 0
        if pos == 0:
            if entry_l[i]: pos, epx, entry_i = 1, op[i+1], i + 1
            elif entry_s[i]: pos, epx, entry_i = -1, op[i+1], i + 1
    tr = pd.DataFrame(trades, columns=["t_in", "gross", "bars"])
    for per, m in [("IS", tr["t_in"] < OOS_START), ("OOS", tr["t_in"] >= OOS_START)]:
        g = tr[m]["gross"]
        if len(g) == 0: continue
        for cname, cost in [("taker 0.13%", COST_TAKER_RT), ("maker 0.04%", COST_MAKER_RT)]:
            net = g - cost
            eq = (1 + net).cumprod()
            mdd = ((eq / eq.cummax()) - 1).min()
            pf = net[net > 0].sum() / abs(net[net <= 0].sum()) if (net <= 0).any() else np.inf
            rows.append({"salida": exname, "periodo": per, "costos": cname, "n": len(g),
                         "WR": f"{(net>0).mean():.0%}", "PF": round(pf, 2),
                         "expect%": round(net.mean()*100, 3), "total%": round((eq.iloc[-1]-1)*100, 1),
                         "maxDD%": round(mdd*100, 1), "hold(h)": round(tr[m]["bars"].mean(), 1)})
print(pd.DataFrame(rows).to_string(index=False))

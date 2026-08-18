"""A+B: parte el PnL del BACKTEST del roster vivo por regimen de BTC (bull/bear) y por lado.
Responde: (A) PnL por lado/regimen, (B) los longs perdedores -> ¿ganaban solo en bull?
Uso: python regime_split.py"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\gen_summary.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # trae tr_for, getdf, STRAT, DATA, etc.

# --- Regimen de BTC: close diario vs SMA200d ---
btc = getdf("BTC", "1h")["close"].resample("1D").last().dropna()
sma = btc.rolling(200).mean()
regime = pd.Series(np.where(btc > sma, "bull", "bear"), index=btc.index)
regime = regime.where(sma.notna())  # NaN antes de 200d

def reg_of(ts):
    d = ts.normalize()
    r = regime.reindex([d], method="ffill")
    return r.iloc[0] if len(r) else None

# longs perdedores en vivo segun el CSV
LOSING_LONGS = {"S22","S37","S38","S24","S51","S55","S39","S45","S14","S3"}

rows = []
for s in STRAT.STRATEGIES:
    try:
        tr = tr_for(s.sid)
    except Exception as e:
        continue
    if tr is None or len(tr) == 0:
        continue
    tr = tr.copy()
    tr["reg"] = tr["t_in"].map(reg_of)
    side = "L" if s.side > 0 else "S"
    for reg in ("bull", "bear"):
        sub = tr[tr["reg"] == reg]
        if len(sub) == 0:
            rows.append((s.sid, s.coin, side, reg, 0, np.nan, np.nan)); continue
        rows.append((s.sid, s.coin, side, reg, len(sub),
                     (sub["ret"] > 0).mean()*100, sub["ret"].mean()*1e4))

df = pd.DataFrame(rows, columns=["sid","coin","side","reg","n","wr","exp_bps"])

def agg(d):
    # exp ponderado por n
    n = d["n"].sum()
    if n == 0: return (0, np.nan, np.nan)
    w = (d["exp_bps"]*d["n"]).sum()/n
    wr = (d["wr"]*d["n"]).sum()/n
    return (n, wr, w)

print("="*72)
print("A) PnL BACKTEST por LADO x REGIMEN (exp neto en bps/trade, ponderado por n)")
print("="*72)
print(f"{'lado':6}{'regimen':9}{'n':>7}{'WR%':>7}{'exp_bps':>10}{'PnL_tot_bps':>13}")
for side in ("L","S"):
    for reg in ("bull","bear"):
        d = df[(df.side==side)&(df.reg==reg)]
        n,wr,e = agg(d)
        tot = (d["exp_bps"]*d["n"]).sum()
        lbl = "LONG" if side=="L" else "SHORT"
        print(f"{lbl:6}{reg:9}{n:>7.0f}{wr:>7.1f}{e:>10.0f}{tot:>13.0f}")
    d=df[df.side==side]; tot=(d["exp_bps"]*d["n"]).sum()
    print(f"{'  -> total '+side:24}{d['n'].sum():>7.0f}{'':7}{'':10}{tot:>13.0f}")

print("\n"+"="*72)
print("B) LONGS PERDEDORES EN VIVO: su backtest en bull vs bear")
print("="*72)
print(f"{'sid':5}{'coin':6}{'n_bull':>8}{'exp_bull':>10}{'n_bear':>8}{'exp_bear':>10}  veredicto")
for sid in sorted(LOSING_LONGS):
    db = df[(df.sid==sid)&(df.reg=="bull")]; dr = df[(df.sid==sid)&(df.reg=="bear")]
    if len(db)==0 and len(dr)==0:
        print(f"{sid:5}{'?':6}  (no backtesteable aqui)"); continue
    nb = db["n"].iloc[0] if len(db) else 0; eb = db["exp_bps"].iloc[0] if len(db) else np.nan
    nr = dr["n"].iloc[0] if len(dr) else 0; er = dr["exp_bps"].iloc[0] if len(dr) else np.nan
    coin = (db["coin"].iloc[0] if len(db) else dr["coin"].iloc[0])
    # veredicto: ¿gana en bear?
    if np.isnan(er) or nr < 5: v = "POCA muestra bear (overfit a bull?)"
    elif er < 0: v = "PIERDE en bear  <-- beta de bull"
    elif er > 0 and eb > 0: v = "gana en ambos (edge real)"
    else: v = "mixto"
    print(f"{sid:5}{coin:6}{nb:>8.0f}{eb:>10.0f}{nr:>8.0f}{er:>10.0f}  {v}")

# cobertura temporal del backtest de cada coin
print("\n"+"="*72)
print("Cobertura del backtest por moneda (¿incluye bear?)")
print("="*72)
seen=set()
for sid in sorted(LOSING_LONGS):
    s = STRAT.BY_ID.get(sid)
    if s is None or s.coin in seen: continue
    seen.add(s.coin)
    try:
        d = getdf(s.coin)
        rg = regime.reindex(d.index.normalize().unique(), method="ffill")
        pct_bear = (rg=="bear").mean()*100
        print(f"{s.coin:6} {d.index.min().date()} -> {d.index.max().date()}  bear={pct_bear:.0f}% del periodo")
    except Exception as e:
        print(s.coin, "ERR", e)

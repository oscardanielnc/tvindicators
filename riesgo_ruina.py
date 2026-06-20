"""Riesgo de ruina / peor racha del roster al sizing VIVO (10% margen x5 = 0.5x nocional
por estrategia, SIN tope agregado, margen fijo sobre capital0).
- Curva de equity historica del roster combinado -> maxDD real
- Block-bootstrap del PnL diario -> distribucion de maxDD, P(ruina)
- Concurrencia / exposicion bruta pico
- Peor racha perdedora analitica por estrategia
Uso: python riesgo_ruina.py"""
import numpy as np
import pandas as pd
import config

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\gen_summary.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])

NOTIONAL_FRAC = config.MARGIN_PCT * config.LEVERAGE  # 0.10*5 = 0.5x capital por trade
RNG = np.random.default_rng(7)

# ---- recolecta trades de TODO el roster ----
daily = {}; all_rets = []; trade_times = []; per_strat = []
for s in STRAT.STRATEGIES:
    try:
        tr = tr_for(s.sid)
    except Exception:
        continue
    if tr is None or len(tr) == 0:
        continue
    r = tr["ret"].values
    all_rets.append(r); trade_times.append(tr["t_in"])
    wr = (r > 0).mean()
    per_strat.append((s.sid, s.coin, "L" if s.side > 0 else "S", len(r), wr))
    d = tr.set_index("t_in")["ret"].resample("1D").sum() * NOTIONAL_FRAC  # delta equity (frac capital0)
    daily[s.sid] = d

M = pd.concat(daily.values(), axis=1).fillna(0)
port = M.sum(axis=1)                       # PnL diario de cartera (frac de $1000, sizing fijo)
eq = 1.0 + port.cumsum()                   # equity aditiva (margen fijo sobre capital0)
dd = eq / eq.cummax() - 1
maxDD_hist = dd.min()

# duracion del peor drawdown
peak = eq.cummax(); in_dd = eq < peak
print("="*72)
print("CURVA HISTORICA DEL ROSTER al sizing vivo (0.5x nocional/estrategia, sin tope)")
print("="*72)
yrs = (eq.index[-1]-eq.index[0]).days/365.25
print(f"Periodo: {eq.index[0].date()} -> {eq.index[-1].date()} ({yrs:.1f} anios)")
print(f"Equity final: {eq.iloc[-1]:.2f}x  ·  maxDD historico: {maxDD_hist*100:.1f}%")
print(f"Peor dia: {port.min()*100:.1f}%  ·  mejor dia: {port.max()*100:.1f}%")
print(f"Vol diaria cartera: {port.std()*100:.2f}%  ·  Sharpe~ {port.mean()/port.std()*np.sqrt(365):.2f}")

# ---- concurrencia / exposicion bruta (proxy: trades abiertos en ventana 48h timeout) ----
allt = pd.concat(trade_times).sort_values().reset_index(drop=True)
# nº de entradas en cada ventana movil de 48h = cota superior de posiciones concurrentes
w = pd.Series(1, index=pd.DatetimeIndex(allt))
conc = w.rolling("48h").sum()
print(f"\nConcurrencia (entradas en 48h, cota sup. de posiciones abiertas):")
print(f"  mediana {conc.median():.0f}  ·  p95 {conc.quantile(.95):.0f}  ·  pico {conc.max():.0f}")
print(f"  -> exposicion bruta pico ~= {conc.max()*NOTIONAL_FRAC:.1f}x el capital  (sin tope!)")

# ---- block bootstrap del PnL diario -> distribucion de maxDD sobre horizontes ----
pv = port.values
def boot_maxdd(n_days, n_sims=4000, block=10):
    res = np.empty(n_sims)
    nb = int(np.ceil(n_days/block))
    starts_all = len(pv)-block
    for k in range(n_sims):
        starts = RNG.integers(0, starts_all, nb)
        path = np.concatenate([pv[s:s+block] for s in starts])[:n_days]
        e = 1.0 + np.cumsum(path)
        cummax = np.maximum.accumulate(e)
        res[k] = (e/cummax - 1).min()
    return res

# trades/dia medio para traducir horizonte de "150 trades cartera" a dias
trades_per_day = len(allt)/ (allt.max()-allt.min()).days
print(f"\nRitmo: {trades_per_day*30:.0f} trades/mes en cartera")

print("\n"+"="*72)
print("MONTE CARLO (block-bootstrap 10d) — maxDD por horizonte, sizing vivo")
print("="*72)
for label, days in [("1 mes",30), ("3 meses",91), ("fase acumulacion ~8m",243), ("1 anio",365)]:
    r = boot_maxdd(days)
    print(f"{label:22} maxDD: mediana {np.median(r)*100:5.1f}% · p95 {np.percentile(r,5)*100:6.1f}% "
          f"· peor {r.min()*100:6.1f}%  | P(DD>20%)={np.mean(r<-0.20)*100:4.0f}% "
          f"P(DD>35%)={np.mean(r<-0.35)*100:3.0f}% P(ruina>50%)={np.mean(r<-0.50)*100:3.0f}%")

# ---- peor racha perdedora analitica por estrategia (WR -> longest losing run en N=20 y N=50) ----
print("\n"+"="*72)
print("PEOR RACHA PERDEDORA esperada por estrategia (segun su WR)")
print("="*72)
def longest_run(wr, N):
    ploss = 1-wr
    if ploss <= 0 or ploss >= 1: return 0
    return np.log(N)/np.log(1/ploss)
wr_long = np.mean([p[4] for p in per_strat if p[2]=="L"])
wr_short = np.mean([p[4] for p in per_strat if p[2]=="S"])
print(f"WR medio  long {wr_long*100:.0f}%  ·  short {wr_short*100:.0f}%")
for lbl,wr in [("long medio",wr_long),("short medio",wr_short)]:
    print(f"  {lbl}: racha perdedora esperada en 20 trades = {longest_run(wr,20):.0f}, "
          f"en 50 = {longest_run(wr,50):.0f} perdidas seguidas")
# perdida $ de una racha al sizing vivo: cada perdida ~ stop. exp_loss aprox:
losses = np.concatenate([r[r<0] for r in all_rets])
avg_loss = losses.mean()*NOTIONAL_FRAC*100
print(f"Perdida media por trade perdedor: {avg_loss:.1f}% del capital (sizing vivo)")
print(f"  -> racha de 6 perdidas seguidas en UNA estrategia = {6*avg_loss:.0f}% (solo esa estrategia)")
print(f"  -> pero varias estrategias correlacionan: ver maxDD de cartera arriba")

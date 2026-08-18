"""Calibra R (riesgo por trade, % del capital) para que el maxDD anual de cartera <= 25% al p95.
Modela sizing por RIESGO: cada trade arriesga R; un stop ~ -1R. Cartera equal-R de N estrategias.
Bootstrap por bloques de la matriz diaria conjunta (preserva correlacion real).
Uso: python calibra_R.py"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/gen_summary.py"), encoding="utf-8").read()
exec(src.split("\ndef main():")[0])
RNG = np.random.default_rng(11)

# --- construye matriz diaria en R-multiplos (stop ~ -1R) para estrategias con edge+ ---
cols = {}
for s in STRAT.STRATEGIES:
    try:
        tr = tr_for(s.sid)
    except Exception:
        continue
    if tr is None or len(tr) < 20:        # solo estrategias con muestra (proxy de "promovible")
        continue
    r = tr["ret"]
    if r.mean() <= 0:                      # solo expectativa positiva (proxy de "pasa gate")
        continue
    losses = r[r < 0]
    if len(losses) < 3:
        continue
    Lmag = -losses.mean()                  # perdida media -> define 1R
    rmult = (r / Lmag)                     # ret en R-multiplos (stop medio ~ -1R)
    cols[s.sid] = tr.assign(rm=rmult.values).set_index("t_in")["rm"].resample("1D").sum()

D = pd.concat(cols, axis=1).fillna(0.0)    # dias x estrategias, en R-multiplos
sids = list(D.columns)
print(f"Estrategias con edge+ y >=20 trades: {len(sids)}")
Dv = D.values
ndays = len(Dv)

def sim_maxdd(N, R, n_sims=3000, horizon=365, block=10):
    dds = np.empty(n_sims); rets = np.empty(n_sims)
    nb = int(np.ceil(horizon/block))
    for k in range(n_sims):
        sub = RNG.choice(len(sids), size=N, replace=False)
        # PnL diario de cartera equal-R en R-multiplos:
        port_rm = Dv[:, sub].sum(axis=1)
        starts = RNG.integers(0, ndays-block, nb)
        path = np.concatenate([port_rm[s:s+block] for s in starts])[:horizon]
        eq = 1.0 + R*np.cumsum(path)
        cummax = np.maximum.accumulate(eq)
        dds[k] = (eq/cummax - 1).min()
        rets[k] = eq[-1] - 1.0
    return dds, rets

print("\n"+"="*70)
print("maxDD anual al p95 y retorno anual mediano, por R y tamano de cartera")
print("="*70)
print(f"{'N':>3} {'R/trade':>8} {'DD_med':>8} {'DD_p95':>8} {'DD_peor':>9} {'ret_med':>9} {'P(DD>25%)':>10}")
for N in (8, 10):
    for R in (0.0025, 0.005, 0.0075, 0.01, 0.015):
        dds, rets = sim_maxdd(N, R)
        print(f"{N:>3} {R*100:>7.2f}% {np.median(dds)*100:>7.1f}% {np.percentile(dds,5)*100:>7.1f}% "
              f"{dds.min()*100:>8.1f}% {np.median(rets)*100:>8.0f}% {np.mean(dds<-0.25)*100:>9.0f}%")
    print()

# busca R tal que p95 maxDD ~= -25% para N=8
print("Busqueda fina R para DD_p95 = -25% (N=8):")
for R in np.arange(0.004, 0.013, 0.001):
    dds,_ = sim_maxdd(8, R, n_sims=2000)
    p95 = np.percentile(dds,5)
    flag = "  <== ~25%" if -0.27 < p95 < -0.23 else ""
    print(f"  R={R*100:.1f}%  DD_p95={p95*100:.1f}%{flag}")

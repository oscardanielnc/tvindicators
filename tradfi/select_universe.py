import numpy as np, pandas as pd, yfinance as yf
AVAIL = {  # ticker -> sector (35 disponibles en Binance futuros)
 "NVDA":"semis","AMD":"semis","MU":"semis","AVGO":"semis","INTC":"semis","QCOM":"semis","TSM":"semis","ASML":"semis","ARM":"semis",
 "AAPL":"megatech","MSFT":"megatech","GOOGL":"megatech","AMZN":"megatech","META":"megatech","NFLX":"megatech","ORCL":"megatech","CRM":"megatech","ADBE":"megatech",
 "TSLA":"ev","RIVN":"ev","F":"ev","JPM":"fin","V":"fin","C":"fin","LLY":"health","CVX":"energy",
 "WMT":"consumer","COST":"consumer","DIS":"consumer","UBER":"indust","COIN":"crypto","MSTR":"crypto","HOOD":"crypto","PLTR":"crypto","LITE":"optical",
}
tks = list(AVAIL)
px = yf.download(tks, start="2023-01-01", auto_adjust=True, progress=False)["Close"]
ret = px.pct_change().dropna()
corr = ret.corr()
liq = (px * yf.download(tks, start="2024-06-01", auto_adjust=True, progress=False)["Volume"]).mean().fillna(0)
# greedy: por liquidez, agregar si max corr con seleccionados < THRESH y tope por sector
THRESH, SECTOR_CAP = 0.62, 3
order = liq.sort_values(ascending=False).index
sel, seccnt = [], {}
for t in order:
    if t not in corr.columns: continue
    sec = AVAIL[t]
    if seccnt.get(sec,0) >= SECTOR_CAP: continue
    if sel and corr.loc[t, sel].max() >= THRESH: continue
    sel.append(t); seccnt[sec] = seccnt.get(sec,0)+1
print(f"SELECCIONADOS: {len(sel)} tickers (corr<{THRESH}, max {SECTOR_CAP}/sector)\n")
for t in sel:
    mc = corr.loc[t, [s for s in sel if s!=t]].max() if len(sel)>1 else 0
    print(f"  {t:6} {AVAIL[t]:9} liq=${liq[t]/1e9:5.1f}B  max_corr_intra_sel={mc:.2f}")
sub = corr.loc[sel, sel]
print(f"\nCorrelación media del subconjunto: {sub.values[np.triu_indices(len(sel),1)].mean():.2f} "
      f"(vs {corr.values[np.triu_indices(len(tks),1)].mean():.2f} del universo completo)")
print("\nlista python:", sel)

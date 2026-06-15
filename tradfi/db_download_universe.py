import os, shutil, json, databento as db
import pandas as pd
KEY = "db-qpawebQq654FynQE6JK6YuKjv3LmC"
PERM = r"C:\Users\LENOVO\market_data\databento"
DBEQ = os.path.join(PERM, "equities_1m_dbeq")
XNAS = os.path.join(PERM, "equities_1m_xnas8y")
os.makedirs(DBEQ, exist_ok=True); os.makedirs(XNAS, exist_ok=True)

SEL = ['NVDA','TSLA','AAPL','MSFT','AMZN','AMD','MU','PLTR','MSTR','LLY','JPM','HOOD','V','COST','WMT','UBER','CVX','LITE','DIS','F','RIVN']
SECTOR = {'NVDA':'semis','AMD':'semis','MU':'semis','AAPL':'megatech','MSFT':'megatech','AMZN':'megatech',
 'TSLA':'ev','F':'ev','RIVN':'ev','PLTR':'crypto','MSTR':'crypto','HOOD':'crypto','JPM':'fin','V':'fin',
 'LLY':'health','CVX':'energy','COST':'consumer','WMT':'consumer','DIS':'consumer','UBER':'indust','LITE':'optical'}

# archivar los 6 XNAS de 8 años ya bajados (no re-pagar)
old = r"D:\OSCAR\Documents\Trading Proyects\tvindicators\tradfi\data_db"
if os.path.isdir(old):
    for f in os.listdir(old):
        if f.endswith(".parquet"):
            shutil.copy2(os.path.join(old, f), os.path.join(XNAS, f))

c = db.Historical(KEY)
done = []
for sym in SEL:
    path = os.path.join(DBEQ, f"{sym}_1m.parquet")
    if os.path.exists(path):
        print(f"{sym}: existe, skip"); done.append(sym); continue
    try:
        data = c.timeseries.get_range(dataset="DBEQ.BASIC", symbols=[sym], schema="ohlcv-1m",
                                      start="2023-03-28", end="2026-06-13", stype_in="raw_symbol")
        df = data.to_df()
        df.to_parquet(path)
        print(f"{sym}: {len(df):,} filas {df.index.min()} -> {df.index.max()}")
        done.append(sym)
    except Exception as e:
        print(f"{sym}: ERROR {repr(e)[:120]}")

manifest = {"dataset":"DBEQ.BASIC (consolidado, todas las plazas)","schema":"ohlcv-1m",
 "range":"2023-03-28..2026-06-13","tickers":done,"sectors":SECTOR,
 "note":"Universo tradfi de baja correlacion (corr media 0.25). 1-min OHLCV. Reusar para sweeps de patrones intradia.",
 "archive_xnas8y":"equities_1m_xnas8y/ = AMD,MU,LITE,TSLA,AAPL,NVDA 2018-2026 (solo Nasdaq, historia profunda)"}
with open(os.path.join(PERM, "MANIFEST.json"), "w") as f:
    json.dump(manifest, f, indent=2)
print(f"\nLISTO: {len(done)}/{len(SEL)} en {DBEQ}")
print(f"Manifest: {os.path.join(PERM,'MANIFEST.json')}")

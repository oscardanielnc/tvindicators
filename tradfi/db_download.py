import os, databento as db
import pandas as pd
KEY = "db-qpawebQq654FynQE6JK6YuKjv3LmC"
OUT = r"D:\OSCAR\Documents\Trading Proyects\tvindicators\tradfi\data_db"
os.makedirs(OUT, exist_ok=True)
SYMS = ["AMD","MU","LITE","TSLA","AAPL","NVDA"]
c = db.Historical(KEY)
for sym in SYMS:
    path = os.path.join(OUT, f"{sym}_1m.parquet")
    if os.path.exists(path):
        print(f"{sym}: ya existe, skip"); continue
    data = c.timeseries.get_range(
        dataset="XNAS.ITCH", symbols=[sym], schema="ohlcv-1m",
        start="2018-05-01", end="2026-06-13", stype_in="raw_symbol")
    df = data.to_df()
    df.to_parquet(path)
    print(f"{sym}: {len(df):,} filas | cols={list(df.columns)} | "
          f"{df.index.min()} -> {df.index.max()}")

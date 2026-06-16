"""Descarga tickers 1-min de Databento (DBEQ.BASIC, 3 años) al store local tradfi/data_db.
Uso: python download_dbeq.py NKE PFE UNH AAL"""
import os
import sys
import databento as db

KEY = "db-qpawebQq654FynQE6JK6YuKjv3LmC"
OUT = r"D:\OSCAR\Documents\Trading Proyects\tvindicators\tradfi\data_db"
syms = [s.upper() for s in sys.argv[1:]] or ["NKE", "PFE", "UNH", "AAL"]
c = db.Historical(KEY)
for sym in syms:
    path = os.path.join(OUT, f"{sym}_1m.parquet")
    if os.path.exists(path):
        print(f"{sym}: ya existe, skip"); continue
    data = c.timeseries.get_range(dataset="DBEQ.BASIC", symbols=[sym], schema="ohlcv-1m",
                                  start="2023-03-28", end="2026-06-13", stype_in="raw_symbol")
    df = data.to_df()
    df.to_parquet(path)
    print(f"{sym}: {len(df):,} filas | {df.index.min()} -> {df.index.max()}")

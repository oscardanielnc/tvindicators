"""Descarga WDC 1-min de Databento (DBEQ.BASIC consolidado, 3 años) al store local tradfi/data_db,
con el mismo formato que los otros tickers (para reusar patterns/sweep_orb/indicator_probe).
Uso: python download_wdc.py"""
import os
import databento as db
import pandas as pd

KEY = "db-qpawebQq654FynQE6JK6YuKjv3LmC"
OUT = r"D:\OSCAR\Documents\Trading Proyects\tvindicators\tradfi\data_db"
SYM = "WDC"
path = os.path.join(OUT, f"{SYM}_1m.parquet")

if os.path.exists(path):
    print(f"{SYM}: ya existe -> {path}")
else:
    c = db.Historical(KEY)
    data = c.timeseries.get_range(dataset="DBEQ.BASIC", symbols=[SYM], schema="ohlcv-1m",
                                  start="2023-03-28", end="2026-06-13", stype_in="raw_symbol")
    df = data.to_df()
    df.to_parquet(path)
    print(f"{SYM}: {len(df):,} filas | cols={list(df.columns)} | {df.index.min()} -> {df.index.max()}")

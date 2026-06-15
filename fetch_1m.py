"""Descarga OHLCV de Binance perps al store Oscilion. Generico por TF.
Para la validacion honesta de la estrategia S/D (replica del stream 'Forex Education Live').
Mismo patron de paginacion que fetch_perps.py. Idempotente (salta lo ya bajado).

Uso:  python fetch_1m.py [tf] [since] [coins]
Ej.:  python fetch_1m.py 1m 2025-01-01 BTC,ETH,SOL
      python fetch_1m.py 5m 2024-01-01 BTC,ETH
"""
import os
import sys
import ccxt
import pandas as pd

OHLCV = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/{tf}.parquet"
TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}

TF = sys.argv[1] if len(sys.argv) > 1 else "1m"
SINCE_STR = sys.argv[2] if len(sys.argv) > 2 else "2025-01-01"
COINS = sys.argv[3].split(",") if len(sys.argv) > 3 else ["BTC", "ETH", "SOL"]
STEP = TF_MS[TF]

ex = ccxt.binanceusdm({"enableRateLimit": True, "options": {"defaultType": "swap"}})
SINCE = ex.parse8601(SINCE_STR + "T00:00:00Z")


def fetch_all(sym):
    out = []
    since = SINCE
    now = ex.milliseconds()
    while since < now:
        b = ex.fetch_ohlcv(sym, TF, since=since, limit=1500)
        if not b:
            break
        out += b
        nxt = b[-1][0] + STEP
        if nxt <= since:
            break
        since = nxt
        if len(out) % 75000 == 0:
            print(f"    {sym}: {len(out)}... ({pd.to_datetime(b[-1][0], unit='ms')})", flush=True)
    return pd.DataFrame(out, columns=["ts", "open", "high", "low", "close", "volume"]) \
        .drop_duplicates("ts").reset_index(drop=True)


for c in COINS:
    po = OHLCV.format(c=c, tf=TF)
    if os.path.exists(po):
        print(f"{c} {TF}: ya existe ({len(pd.read_parquet(po))} velas). SKIP.", flush=True)
        continue
    os.makedirs(os.path.dirname(po), exist_ok=True)
    print(f"{c} {TF}: bajando desde {SINCE_STR}...", flush=True)
    d = fetch_all(f"{c}/USDT:USDT")
    d.to_parquet(po)
    print(f"{c} {TF}: LISTO {len(d)} velas "
          f"({pd.to_datetime(d['ts'].min(), unit='ms')} .. {pd.to_datetime(d['ts'].max(), unit='ms')})",
          flush=True)
print("=== DESCARGA COMPLETA ===", flush=True)

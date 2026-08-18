"""Descarga perps de ORO de Binance (XAU, PAXG) al store Oscilion: 1m/15m/1h OHLCV + funding.
XAU/USDT:USDT = oro directo (corto: desde 2025-12). PAXG/USDT:USDT = Paxos Gold (~15 meses, útil
para backtest con IS/OOS). Mismo formato que el resto del universo cripto. Uso: python fetch_gold.py
"""
import os, ccxt
import pandas as pd

OHLCV = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/{tf}.parquet"
FUND = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{c}_USDT_USDT.parquet"
COINS = {"XAU": "XAU/USDT:USDT", "PAXG": "PAXG/USDT:USDT"}
TFS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000}
SINCE = ccxt.binanceusdm().parse8601("2025-01-01T00:00:00Z")

ex = ccxt.binanceusdm({"enableRateLimit": True}); ex.load_markets()


def fetch_ohlcv_all(sym, tf, step):
    out = []; since = SINCE; now = ex.milliseconds()
    while since < now:
        b = ex.fetch_ohlcv(sym, tf, since=since, limit=1500)
        if not b:
            break
        out += b; nxt = b[-1][0] + step
        if nxt <= since:
            break
        since = nxt
    return pd.DataFrame(out, columns=["ts", "open", "high", "low", "close", "volume"]).drop_duplicates("ts")


def fetch_fund_all(sym):
    out = []; since = SINCE; now = ex.milliseconds()
    while since < now:
        b = ex.fetch_funding_rate_history(sym, since=since, limit=1000)
        if not b:
            break
        out += [(int(x["timestamp"]), float(x["fundingRate"])) for x in b]
        nxt = b[-1]["timestamp"] + 1
        if nxt <= since:
            break
        since = nxt
    return pd.DataFrame(out, columns=["ts", "funding_rate"]).drop_duplicates("ts")


for c, sym in COINS.items():
    for tf, step in TFS.items():
        po = OHLCV.format(c=c, tf=tf)
        os.makedirs(os.path.dirname(po), exist_ok=True)
        d = fetch_ohlcv_all(sym, tf, step)
        d.to_parquet(po)
        rng = (pd.to_datetime(d["ts"].min(), unit="ms").date(),
               pd.to_datetime(d["ts"].max(), unit="ms").date()) if len(d) else (None, None)
        print(f"  {c} {tf}: {len(d):6} velas ({rng[0]}..{rng[1]})", flush=True)
    pf = FUND.format(c=c)
    os.makedirs(os.path.dirname(pf), exist_ok=True)
    f = fetch_fund_all(sym); f.to_parquet(pf)
    print(f"  {c} funding: {len(f)} eventos", flush=True)
print("LISTO", flush=True)

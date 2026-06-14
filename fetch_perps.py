"""Descarga perps NUEVOS de Binance (1h OHLCV + funding) al store, formato Oscilion.
Para expandir el universo cripto del pipeline de alta convicción."""
import os, time, ccxt
import pandas as pd
OHLCV = "C:/Users/LENOVO/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/1h.parquet"
FUND  = "C:/Users/LENOVO/Oscilion/data/funding/binanceusdm/{c}_USDT_USDT.parquet"
HAVE = {"ADA","AVAX","BNB","BTC","DOGE","DOT","ETH","LINK","LTC","SOL","SUI","TRX","XRP"}
CAND = ["APT","ARB","OP","NEAR","ATOM","INJ","SEI","TIA","RUNE","AAVE","UNI","MKR","LDO",
        "FIL","ICP","IMX","RENDER","GRT","FET","TAO","HBAR","ALGO","ETC","BCH","XLM","VET",
        "AXS","SAND","DYDX","ENA","STX","CRV","PEPE","WIF","ORDI","JUP","PYTH","NEO","EGLD","FLOW"]
SINCE = ccxt.binanceusdm().parse8601("2022-06-01T00:00:00Z")

ex = ccxt.binanceusdm({"enableRateLimit": True}); m = ex.load_markets()
avail = [c for c in CAND if f"{c}/USDT:USDT" in m and c not in HAVE]
print(f"Disponibles para bajar: {len(avail)} -> {avail}", flush=True)

def fetch_ohlcv_all(sym):
    out=[]; since=SINCE; now=ex.milliseconds()
    while since < now:
        b = ex.fetch_ohlcv(sym, "1h", since=since, limit=1500)
        if not b: break
        out += b; nxt = b[-1][0] + 3600000
        if nxt <= since: break
        since = nxt
    df = pd.DataFrame(out, columns=["ts","open","high","low","close","volume"]).drop_duplicates("ts")
    return df

def fetch_fund_all(sym):
    out=[]; since=SINCE; now=ex.milliseconds()
    while since < now:
        b = ex.fetch_funding_rate_history(sym, since=since, limit=1000)
        if not b: break
        out += [(int(x["timestamp"]), float(x["fundingRate"])) for x in b]
        nxt = b[-1]["timestamp"] + 1
        if nxt <= since: break
        since = nxt
    return pd.DataFrame(out, columns=["ts","funding_rate"]).drop_duplicates("ts")

done=[]
for c in avail:
    try:
        po = OHLCV.format(c=c)
        if not os.path.exists(po):
            os.makedirs(os.path.dirname(po), exist_ok=True)
            d = fetch_ohlcv_all(f"{c}/USDT:USDT")
            if len(d) < 5000:
                print(f"  {c}: solo {len(d)} velas, SKIP (historia corta)", flush=True); continue
            d.to_parquet(po)
        pf = FUND.format(c=c)
        if not os.path.exists(pf):
            os.makedirs(os.path.dirname(pf), exist_ok=True)
            fetch_fund_all(f"{c}/USDT:USDT").to_parquet(pf)
        dd = pd.read_parquet(po)
        print(f"  {c}: {len(dd)} velas 1h ({pd.to_datetime(dd['ts'].min(),unit='ms').date()}..{pd.to_datetime(dd['ts'].max(),unit='ms').date()})", flush=True)
        done.append(c)
    except Exception as e:
        print(f"  {c}: ERROR {str(e)[:80]}", flush=True)
print(f"LISTO: {len(done)} perps bajados -> {done}", flush=True)

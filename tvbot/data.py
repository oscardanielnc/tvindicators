"""Datos de mercado via ccxt (publico, sin API key). Sin look-ahead: solo velas CERRADAS."""
import time

import ccxt
import pandas as pd

import config

_ex = None


def exchange():
    global _ex
    if _ex is None:
        _ex = getattr(ccxt, config.EXCHANGE)({"enableRateLimit": True,
                                              "options": {"defaultType": "swap"}})
    return _ex


TF_MS = {"15m": 15 * 60_000, "1h": 60 * 60_000}


def fetch_bars(symbol, tf, limit=None):
    """Devuelve (df_velas_cerradas, open_de_vela_en_curso).
    La ultima fila del df es la ultima vela CERRADA (la senal se evalua ahi).
    El open de la vela en curso es el precio de entrada del paper trade."""
    limit = limit or config.WARMUP_BARS
    raw = exchange().fetch_ohlcv(symbol, tf, limit=limit + 1)
    if not raw or len(raw) < 50:
        raise RuntimeError(f"datos insuficientes {symbol} {tf}: {len(raw) if raw else 0}")
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    now_ms = exchange().milliseconds()
    cur_start = (now_ms // TF_MS[tf]) * TF_MS[tf]
    live = df[df["ts"] == cur_start]
    live_open = float(live["open"].iloc[0]) if len(live) else float(df["close"].iloc[-1])
    df = df[df["ts"] < cur_start]                     # solo cerradas
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("dt"), live_open


def funding_since(symbol, since_ms, until_ms):
    """Suma de funding rates entre dos timestamps (eventos cada 8h en Binance)."""
    try:
        rows = exchange().fetch_funding_rate_history(symbol, since=int(since_ms), limit=200)
        return sum(r["fundingRate"] for r in rows
                   if r["timestamp"] and since_ms < r["timestamp"] <= until_ms)
    except Exception:
        return 0.0      # si falla la API, no bloquear el cierre; queda en 0 y se audita


def retry(fn, tries=3, wait=2):
    for k in range(tries):
        try:
            return fn()
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(wait * (k + 1))

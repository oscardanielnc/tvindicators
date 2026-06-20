"""Datos de mercado via ccxt (publico, sin API key). Sin look-ahead: solo velas CERRADAS."""
import time
from zoneinfo import ZoneInfo

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


TF_MS = {"15m": 15 * 60_000, "30m": 30 * 60_000, "1h": 60 * 60_000, "1d": 24 * 60 * 60_000}

_ET = ZoneInfo("America/New_York")


def filter_us_session(df):
    """Filtra velas a la sesión regular US (09:30-16:00 ET, L-V) — DST-aware. Para titulares 'us':
    durante la sesión el perp Binance ≈ la acción real (arbitraje), que es donde se validaron."""
    et = df.index.tz_convert(_ET)
    mask = (et.weekday < 5) & (
        ((et.hour > 9) | ((et.hour == 9) & (et.minute >= 30))) & (et.hour < 16))
    return df[mask]


def in_us_session(ts_utc=None):
    """¿Estamos en sesión regular US ahora? (para gating de entradas de titulares 'us')."""
    et = (ts_utc or pd.Timestamp.now(tz="UTC")).tz_convert(_ET)
    return et.weekday() < 5 and (
        (et.hour > 9 or (et.hour == 9 and et.minute >= 30)) and et.hour < 16)


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
    # guard de frescura: la ultima vela cerrada debe ser exactamente la anterior
    # a la vela en curso; si Binance devuelve datos viejos, mejor fallar y reintentar
    expected_last = cur_start - TF_MS[tf]
    if int(df["ts"].iloc[-1]) != expected_last:
        raise RuntimeError(
            f"datos no frescos {symbol} {tf}: ultima vela {int(df['ts'].iloc[-1])}, "
            f"esperada {expected_last}")
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

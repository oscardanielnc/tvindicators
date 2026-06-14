"""
PoC — MOMENTUM INTRADIA en acciones (¿la dirección de la mañana predice el resto del día?).

Pregunta de Oscar: detectar cuándo la dirección del día se asienta y montarse, cerrando
antes del cierre (intradía, sin apalancamiento overnight). Test directo:
  - señal = retorno de la(s) primera(s) vela(s) de sesión (mañana).
  - ¿predice el retorno del RESTO del día (hasta el cierre)?
  - regla operable: entrar en la dirección de la señal al cierre de la ventana mañanera,
    salir al cierre de sesión. LONG y SHORT por separado (prueba de dos lados).

Datos: yfinance intradía (1h ~2yr; 15m ~60d). Sesión regular NY 09:30-16:00 ET.
Costos: maker entrada 0.02% + taker+slip salida 0.07% (~0.12% RT). Uso: python tradfi/poc_intraday.py
"""
from __future__ import annotations
import numpy as np
import pandas as pd

TICKERS = ["AMD", "MU", "LITE", "TSLA", "AAPL", "NVDA"]
RT_COST = 0.0002 + 0.0005 + 0.0005          # entrada maker + salida taker+slip
MORNING_BARS = {"1h": 1, "15m": 2}          # ventana "mañana": 1h=1ª hora; 15m=primeros 30min


def fetch(tk, interval, period):
    import yfinance as yf
    raw = yf.download(tk, interval=interval, period=period, auto_adjust=True, progress=False)
    if raw.empty:
        return None
    raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
    df = raw.rename(columns=str.lower)[["open", "high", "low", "close"]].copy()
    idx = pd.to_datetime(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx
    df.index = idx.tz_convert("America/New_York")
    sess = (df.index.time >= pd.Timestamp("09:30").time()) & (df.index.time < pd.Timestamp("16:00").time())
    return df[sess].dropna()


def day_table(df, mbars):
    """Por día: r_morning (señal) y r_rest (resto hasta cierre)."""
    rows = []
    for d, g in df.groupby(df.index.date):
        if len(g) < mbars + 2:
            continue
        o = g["open"].values; c = g["close"].values
        r_morning = c[mbars - 1] / o[0] - 1                  # open -> cierre de la ventana mañana
        r_rest = c[-1] / c[mbars - 1] - 1                    # entrada (cierre ventana) -> cierre sesión
        rows.append((pd.Timestamp(d), r_morning, r_rest))
    return pd.DataFrame(rows, columns=["date", "r_morning", "r_rest"])


def evaluate(tk, interval, period):
    df = fetch(tk, interval, period)
    if df is None or len(df) < 50:
        return None
    t = day_table(df, MORNING_BARS[interval])
    if len(t) < 30:
        return None
    sign = np.sign(t["r_morning"])
    # regla momentum: entrar en dirección de la mañana, salir al cierre
    pnl = sign * t["r_rest"] - RT_COST
    pnl = pnl[t["r_morning"] != 0]
    longs = (sign > 0)
    shorts = (sign < 0)
    corr = np.corrcoef(t["r_morning"], t["r_rest"])[0, 1]
    hit = (np.sign(t["r_rest"]) == sign).mean()
    yrs = max((t["date"].max() - t["date"].min()).days / 365, 0.2)
    return dict(
        tk=tk, itv=interval, days=len(t), corr=corr, hit=hit,
        pnl_day=pnl.mean(), pnl_ann=pnl.sum() / yrs,
        long_pnl=(t.loc[longs, "r_rest"] - RT_COST).mean() if longs.sum() else np.nan,
        short_pnl=((-t.loc[shorts, "r_rest"]) - RT_COST).mean() if shorts.sum() else np.nan,
        n_long=int(longs.sum()), n_short=int(shorts.sum()),
        wr=(pnl > 0).mean(),
    )


def main():
    for interval, period in [("1h", "730d"), ("15m", "60d")]:
        print(f"\n########## {interval} (ventana mañana = {MORNING_BARS[interval]} vela/s) ##########")
        print(f"{'tk':5} {'días':>5} {'corr':>6} {'hit%':>6} {'pnl/día':>8} {'pnl/año':>8} "
              f"{'long/día':>9} {'short/día':>9} {'wr%':>5}")
        rs = []
        for tk in TICKERS:
            r = evaluate(tk, interval, period)
            if r is None:
                print(f"{tk:5} sin datos"); continue
            rs.append(r)
            print(f"{r['tk']:5} {r['days']:5} {r['corr']:+.3f} {r['hit']*100:5.0f} "
                  f"{r['pnl_day']*100:+7.3f}% {r['pnl_ann']*100:+7.1f}% "
                  f"{r['long_pnl']*100:+8.3f}% {r['short_pnl']*100:+8.3f}% {r['wr']*100:4.0f}")
        if rs:
            R = pd.DataFrame(rs)
            print(f"{'POOL':5} {R['days'].sum():5} {R['corr'].mean():+.3f} {R['hit'].mean()*100:5.0f} "
                  f"{R['pnl_day'].mean()*100:+7.3f}% {R['pnl_ann'].mean()*100:+7.1f}% "
                  f"{R['long_pnl'].mean()*100:+8.3f}% {R['short_pnl'].mean()*100:+8.3f}% {R['wr'].mean()*100:4.0f}")
            print(f"  -> corr media {R['corr'].mean():+.3f} | hit medio {R['hit'].mean()*100:.0f}% | "
                  f"momentum gana neto en {(R['pnl_day']>0).sum()}/{len(R)} tickers | "
                  f"short gana neto en {(R['short_pnl']>0).sum()}/{len(R)}")


if __name__ == "__main__":
    main()

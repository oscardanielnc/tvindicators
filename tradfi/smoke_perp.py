"""SMOKE-TEST de las 5 estrategias tradfi sobre los PERPS de Binance (instrumento real donde se operará).
Los perps trackean la acción pero cotizan 24/7 y solo tienen ~40 días de historia -> esto NO es validación,
es un chequeo direccional: ¿el edge (validado en la acción real) sobrevive al perp 24/7?

T2-T5: trend-following sobre barras continuas (igual que el probe). T1-ORB: rango de apertura US (13:30 UTC).
Compara cada una vs buy&hold del perp (anti-beta). Costos taker+slip (ignora funding, holds cortos).
Uso: python smoke_perp.py
"""
import os
import sys
import math
import time as _t
import numpy as np
import pandas as pd
import ccxt

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from indicator_probe import signals, backtest, COST
from tvbot import indicators as I

EX = ccxt.binanceusdm({"enableRateLimit": True, "options": {"defaultType": "swap"}})
EX.load_markets()


def fetch_perp(sym, tf, days=45):
    since = EX.milliseconds() - days * 86400 * 1000
    out = []
    while True:
        o = EX.fetch_ohlcv(sym, tf, since=since, limit=1000)
        if not o:
            break
        out += o
        since = o[-1][0] + 1
        if len(o) < 1000:
            break
        _t.sleep(0.2)
    df = pd.DataFrame(out, columns=["ts", "open", "high", "low", "close", "volume"]).drop_duplicates("ts")
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("dt")[["open", "high", "low", "close", "volume"]].astype(float)


def metr(rets, years):
    r = np.asarray(rets, float)
    if len(r) < 8:
        return None
    sd = r.std(ddof=1); tpy = len(r) / years
    g = r[r > 0].sum(); l = -r[r < 0].sum()
    return dict(n=len(r), tpy=tpy, wr=(r > 0).mean(), exp=r.mean(), pf=(g / l if l > 0 else np.inf),
                sharpe=(r.mean() / sd * math.sqrt(tpy) if sd > 0 else 0), cum=(1 + pd.Series(r)).prod() - 1)


def buyhold_sharpe(df):
    br = df["close"].pct_change().dropna().values
    yrs = (df.index[-1] - df.index[0]).days / 365.25
    bpy = len(br) / max(yrs, 0.01)
    return br.mean() / br.std(ddof=1) * math.sqrt(bpy) if br.std() > 0 else 0


def orb_perp(df15):
    """ORB experimental sobre el perp: OR = primera vela 15m de la apertura US (13:30 UTC), día hábil."""
    rets = []
    for day, g in df15.groupby(df15.index.date):
        if pd.Timestamp(day).weekday() >= 5:
            continue
        et_open = g.between_time("13:30", "13:44")        # 09:30-09:44 ET = OR (en EDT; aprox)
        rest = g.between_time("13:45", "19:59")
        if len(et_open) < 1 or len(rest) < 5:
            continue
        orh, orl = et_open["high"].max(), et_open["low"].min()
        if orh <= orl or (orh - orl) / orh < 0.0225:
            continue
        op, hi, lo, cl = rest["open"].values, rest["high"].values, rest["low"].values, rest["close"].values
        e = None
        for k in range(len(rest)):
            if hi[k] >= orh:
                e = k; break
        if e is None:
            continue
        entry = orh; ex = None
        for k in range(e, len(rest)):
            if lo[k] <= orl:
                ex = orl; break
        if ex is None:
            ex = cl[-1]
        rets.append((ex / entry - 1) - COST)
    return rets


STRrows = [
    ("T2 NVDA-ST-30m",  "NVDA/USDT:USDT", "30m", "Supertrend"),
    ("T3 NVDA-AO-30m",  "NVDA/USDT:USDT", "30m", "AO"),
    ("T4 NVDA-SQZ-15m", "NVDA/USDT:USDT", "15m", "Squeeze"),
    ("T5 TSLA-ADX-15m", "TSLA/USDT:USDT", "15m", "ADX"),
]


def main():
    print("=" * 92)
    print("SMOKE-TEST sobre PERPS Binance 24/7 (~40d, NO es validación — chequeo direccional)")
    print("=" * 92)
    cache = {}
    def get(sym, tf):
        if (sym, tf) not in cache:
            cache[(sym, tf)] = fetch_perp(sym, tf)
        return cache[(sym, tf)]

    print(f"\n{'estrategia':18} {'n':>4} {'WR':>4} {'exp':>7} {'PF':>5} {'Sharpe':>7} {'B&H Sh':>7} {'cum':>7}  veredicto")
    for name, sym, tf, ind in STRrows:
        df = get(sym, tf)
        yrs = (df.index[-1] - df.index[0]).days / 365.25
        st = I.st_flips(df)[2]
        le, _ = signals(ind, df)
        mm = metr(backtest(df, le, 1, st), yrs)
        bh = buyhold_sharpe(df)
        if mm is None:
            print(f"{name:18}  pocos trades"); continue
        beat = mm["sharpe"] > bh + 0.1 and mm["exp"] > 0
        v = "★ sobrevive (gana beta)" if beat else ("positivo pero ~beta" if mm["exp"] > 0 else "NO transfiere")
        print(f"{name:18} {mm['n']:4} {mm['wr']*100:3.0f}% {mm['exp']*1e4:+6.0f} {mm['pf']:5.2f} "
              f"{mm['sharpe']:+7.2f} {bh:+7.2f} {mm['cum']*100:+6.0f}%  {v}")

    # ORB perp
    df15 = get("TSLA/USDT:USDT", "15m")
    yrs = (df15.index[-1] - df15.index[0]).days / 365.25
    mm = metr(orb_perp(df15), yrs)
    if mm:
        print(f"{'T1 TSLA-ORB(US)':18} {mm['n']:4} {mm['wr']*100:3.0f}% {mm['exp']*1e4:+6.0f} {mm['pf']:5.2f} "
              f"{mm['sharpe']:+7.2f} {'—':>7} {mm['cum']*100:+6.0f}%  (experimental, n minúsculo)")
    else:
        print(f"{'T1 TSLA-ORB(US)':18}  n insuficiente en 40d (esperado)")

    print(f"\nHistoria disponible: {df15.index[0].date()} -> {df15.index[-1].date()} (~40d)")
    print("=" * 92)
    print("LECTURA: con ~40d y sin IS/OOS, esto es SOLO un smoke-test. Un ★ = el edge parece transferir al")
    print("perp; 'NO transfiere' = bandera roja. El juez real será el paper vivo sobre el perp (semanas).")


if __name__ == "__main__":
    main()

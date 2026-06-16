"""Prueba EFICIENTE del arsenal de indicadores del bot cripto sobre acciones, multi-timeframe.
¿Algún indicador (Supertrend, ADX, Vortex, Squeeze, AO, TSI, ZeroLag) se adapta bien a TSLA/LITE/otros?

Backtest trend-following uniforme (mismo para todos, comparable):
  - Entrada: evento del indicador (long o short), al open de la barra siguiente.
  - Salida: flip del Supertrend en contra (salida maestra) o stop ATR k·ATR, lo que pegue antes.
  - Costos: taker+slip por lado (acciones/futuro, conservador).
TFs: 1d (nativo, historia larga) + 1h/30m/15m (resampleados de 1m, 2018+). Marca ★ los prometedores.
Uso: python indicator_probe.py            (TSLA LITE NVDA por defecto)
     python indicator_probe.py AAPL AMD MU
"""
import os
import sys
import math
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root -> tvbot
import sweep_orb as S
from tvbot import indicators as I

TICKERS = sys.argv[1:] if len(sys.argv) > 1 else ["TSLA", "LITE", "NVDA"]
TFS = ["1d", "1h", "30m", "15m"]
COST = 2 * (S.TAKER + S.SLIP)        # ida y vuelta, con slippage ambos lados
ATR_K = 3.0
WARM = 300
RULES = {"1h": "60min", "30m": "30min", "15m": "15min", "5m": "5min"}


def load_tf(t, tf):
    if tf == "1d":
        d = pd.read_parquet(f"data/{t}_1d.parquet")[["open", "high", "low", "close", "volume"]].dropna()
        return d.astype(float)
    df = S.load(t)                    # 1m, ET, sesión regular 09:30-16:00
    g = df.resample(RULES[tf], label="left", closed="left")
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(),
                        "low": g["low"].min(), "close": g["close"].last(),
                        "volume": g["volume"].sum()}).dropna()
    return out


SIGS = ["Supertrend", "ADX", "Vortex", "Squeeze", "AO", "TSI", "ZeroLag"]


def signals(name, df):
    """Devuelve (long_events, short_events) como arrays bool."""
    if name == "Supertrend":
        up, dn, _ = I.st_flips(df); return np.asarray(up), np.asarray(dn)
    fn = {"ADX": I.adx_dmi, "Vortex": I.vortex, "Squeeze": I.squeeze_momentum,
          "AO": I.awesome_osc, "TSI": I.tsi, "ZeroLag": I.zero_lag_entry}[name]
    le, se = fn(df); return np.asarray(le), np.asarray(se)


def backtest(df, entries, side, st_dir):
    """Trend-following: entra en evento, sale en flip ST en contra o stop ATR. Lista de retornos netos."""
    op = df["open"].values; hi = df["high"].values; lo = df["low"].values; cl = df["close"].values
    atr = I.atr14(df).values
    n = len(df); i = WARM; rets = []
    while i < n - 1:
        if not entries[i] or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1; continue
        e = i + 1; ep = op[e]; stop = ep - side * ATR_K * atr[i]
        ex = None; j = e
        while j < n - 1:
            if side > 0 and lo[j] <= stop:
                ex = min(op[j], stop); break
            if side < 0 and hi[j] >= stop:
                ex = max(op[j], stop); break
            if st_dir[j] == -side:                 # flip del Supertrend en contra = salida maestra
                ex = op[j + 1]; break
            j += 1
        if ex is None:
            ex = cl[-1]; j = n - 1
        rets.append(side * (ex / ep - 1) - COST); i = j + 1
    return rets


def metr(rets, years):
    r = np.asarray(rets, float)
    if len(r) < 20:
        return None
    sd = r.std(ddof=1); wr = (r > 0).mean()
    g = r[r > 0].sum(); l = -r[r < 0].sum()
    tpy = len(r) / years
    return dict(n=len(r), tpy=tpy, wr=wr, exp=r.mean(), pf=(g / l if l > 0 else np.inf),
                sharpe=(r.mean() / sd * math.sqrt(tpy) if sd > 0 else 0), cum=(1 + pd.Series(r)).prod() - 1)


def main():
    print("=" * 96)
    print(f"PROBE DE INDICADORES sobre acciones — {', '.join(TICKERS)}  (trend-following, salida ST/ATR)")
    print("=" * 96)
    print(f"costos {COST*1e4:.0f}bp ida+vuelta · stop {ATR_K}·ATR · TFs {TFS}\n")
    shortlist = []
    for t in TICKERS:
        print(f"###### {t} ######")
        print(f"  {'TF':5} {'indic':10} {'side':5} {'n':>5} {'t/año':>6} {'WR':>4} {'exp':>7} {'PF':>5} {'Sharpe':>7} {'cum':>7}")
        for tf in TFS:
            try:
                df = load_tf(t, tf)
            except Exception as e:
                print(f"  {tf}: error carga ({e})"); continue
            if len(df) < 400:
                continue
            years = max((df.index[-1] - df.index[0]).days / 365.25, 0.5)
            st_dir = I.st_flips(df)[2]
            for name in SIGS:
                le, se = signals(name, df)
                for side, ev in ((1, le), (-1, se)):
                    mm = metr(backtest(df, ev, side, st_dir), years)
                    if mm is None:
                        continue
                    good = mm["pf"] >= 1.2 and mm["sharpe"] >= 0.5 and mm["exp"] > 0
                    star = " ★" if good else ""
                    if good:
                        shortlist.append((t, tf, name, "L" if side > 0 else "S", mm))
                    print(f"  {tf:5} {name:10} {'LONG' if side>0 else 'SHORT':5} {mm['n']:5} "
                          f"{mm['tpy']:6.0f} {mm['wr']*100:3.0f}% {mm['exp']*1e4:+6.0f} {mm['pf']:5.2f} "
                          f"{mm['sharpe']:+7.2f} {mm['cum']*100:+6.0f}%{star}")
        print()
    print("=" * 96)
    print(f"SHORTLIST (PF≥1.2, Sharpe≥0.5, exp>0) — candidatos a validar con holdout IS/OOS:")
    if not shortlist:
        print("  (ninguno superó el umbral — ningún indicador se adapta limpio a estos tickers/TFs)")
    for t, tf, name, sd, mm in sorted(shortlist, key=lambda x: -x[4]["sharpe"]):
        print(f"  {t:5} {tf:4} {name:10} {sd}  Sharpe {mm['sharpe']:+.2f} · PF {mm['pf']:.2f} · "
              f"exp {mm['exp']*1e4:+.0f}bp · t/año {mm['tpy']:.0f} · cum {mm['cum']*100:+.0f}%")
    print("\nOjo: esto es IN-SAMPLE (sin holdout). Los ★ son SHORTLIST, no edge probado. El siguiente paso")
    print("es validar los mejores con IS/OOS + anti-beta, igual que TSLA-ORB. Salida ST/ATR es genérica.")


if __name__ == "__main__":
    main()

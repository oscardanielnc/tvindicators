"""
TRADFI sweep — MEAN-REVERSION en acciones (pivote tras el no-go de trend).

Tesis: las acciones revierten a la media en horizonte corto (mucho más que cripto).
Señales clásicas de reversión:
  - RSI(2) extremo (Connors), RSI(14) sobre/bajo, Bollinger(20,2), z-score 2σ, días consecutivos.
Cada una con/sin filtro de tendencia (SMA200) — comprar dips en uptrend / vender pops en downtrend.
Salida de reversión: vuelta a una media corta (SMA5/SMA20) + stop protector 3xATR + time-stop.

Mismo gate honesto que el sweep de trend: expectancy>0, PF>1.1, año-a-año, n>=20,
+ benchmark buy&hold + prueba de SHORTS (las acciones tienen drift alcista; si solo el long
revierte, es beta; si el short también, hay edge de dos lados).

Datos: parquets cacheados por sweep_tradfi.py (yfinance, subyacente). Uso: python tradfi/sweep_meanrev.py
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

ROOT = r"D:\OSCAR\Documents\Trading Proyects\tvindicators"
exec(open(os.path.join(ROOT, "portafolio.py"), encoding="utf-8").read().split("daily, stats =")[0])

WARMUP = 250
TICKERS = ["AMD", "MU", "LITE", "TSLA", "AAPL", "NVDA"]
DATA_DIR = os.path.join(ROOT, "tradfi", "data")
E_MAKER, E_TAKER, E_SLIP = 0.0002, 0.0005, 0.0005
TO_BARS = {"1d": 10, "1h": 24}     # time-stop: reversión es de hold corto


def load_cached(tk, tf):
    p = os.path.join(DATA_DIR, f"{tk}_{tf}.parquet")
    return pd.read_parquet(p) if os.path.exists(p) else None


def atr_arr(df, n=14):
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    return pine_rma(tr, n).values


# ───────── motor mean-reversion: stop protector / reversión a media / time-stop ─────────

def bt_mr(df, atrv, ent, side, sma_exit, to_bars, atr_mult=3.0):
    op, hi, lo, cl = (df[c].values for c in ("open", "high", "low", "close"))
    idx = df.index; n = len(df)
    trades, j_free = [], 0
    for i_sig in np.flatnonzero(ent[WARMUP:n - 2]) + WARMUP:
        if i_sig < j_free:
            continue
        e_i = i_sig + 1; epx = op[e_i]
        if not np.isfinite(epx) or epx <= 0:
            continue
        stop = epx - side * atr_mult * atrv[i_sig]
        j, exit_px, cost_out, t_out = e_i, None, E_MAKER, None
        while j < n - 1:
            hit = lo[j] <= stop if side > 0 else hi[j] >= stop
            if hit:
                exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                cost_out, t_out = E_TAKER + E_SLIP, j; break
            revert = cl[j] >= sma_exit[j] if side > 0 else cl[j] <= sma_exit[j]
            if revert:
                exit_px, t_out = op[j + 1], j + 1; break
            if j - e_i + 1 >= to_bars:
                exit_px, t_out = op[j + 1], j + 1; break
            j += 1
        if exit_px is None:
            break
        net = side * (exit_px / epx - 1) - E_MAKER - cost_out
        trades.append((idx[e_i], idx[t_out], net, t_out - e_i))
        j_free = t_out + 1
    return pd.DataFrame(trades, columns=["t_in", "t_out", "net", "bars"])


# ───────── señales de reversión ─────────

def mr_signals(df):
    c = df["close"]
    sma20 = pine_sma(c, 20); std20 = c.rolling(20).std()
    z = ((c - sma20) / std20).values
    rsi2 = pine_rsi(c, 2).values
    rsi14 = pine_rsi(c, 14).values
    upper = (sma20 + 2 * std20).values; lower = (sma20 - 2 * std20).values
    cl = c.values
    down3 = (cl < np.roll(cl, 1)) & (np.roll(cl, 1) < np.roll(cl, 2)) & (np.roll(cl, 2) < np.roll(cl, 3))
    up3 = (cl > np.roll(cl, 1)) & (np.roll(cl, 1) > np.roll(cl, 2)) & (np.roll(cl, 2) > np.roll(cl, 3))
    sma200 = pine_sma(c, 200).values
    return dict(
        rsi2=rsi2, rsi14=rsi14, z=z, upper=upper, lower=lower, cl=cl,
        down3=down3, up3=up3, above200=cl > sma200, below200=cl < sma200,
        sma5=pine_sma(c, 5).values, sma20=sma20.values,
    )


def recipes(s):
    """{nombre: (entry, side)} — long=sobreventa, short=sobrecompra; _f = filtro tendencia."""
    R = {}
    longs = {
        "RSI2<10":  s["rsi2"] < 10,
        "RSI14<30": s["rsi14"] < 30,
        "BB_low":   s["cl"] < s["lower"],
        "Z<-2":     s["z"] < -2,
        "3down":    s["down3"],
    }
    shorts = {
        "RSI2>90":  s["rsi2"] > 90,
        "RSI14>70": s["rsi14"] > 70,
        "BB_up":    s["cl"] > s["upper"],
        "Z>2":      s["z"] > 2,
        "3up":      s["up3"],
    }
    for k, sig in longs.items():
        R[f"L_{k}"] = (sig, 1)
        R[f"L_{k}_f"] = (sig & s["above200"], 1)        # solo dips en uptrend
    for k, sig in shorts.items():
        R[f"S_{k}"] = (sig, -1)
        R[f"S_{k}_f"] = (sig & s["below200"], -1)        # solo pops en downtrend
    return R


def metrics(tr, df):
    n = len(tr)
    if n < 5:
        return None
    r = tr["net"]
    yrs = (df.index[-1] - df.index[WARMUP]).days / 365
    eq = (1 + r).cumprod()
    mdd = float(((eq / eq.cummax()) - 1).min())
    by = tr.groupby(tr["t_in"].dt.year)["net"].apply(lambda g: np.prod(1 + g) - 1)
    pos = r[r > 0].sum(); neg = abs(r[r <= 0].sum())
    dd = pd.Series(r.values, index=tr["t_in"].values).resample("1D").sum()
    sharpe = dd.mean() / dd.std() * np.sqrt(365) if dd.std() > 0 else 0.0
    return dict(n=n, wr=(r > 0).mean(), expect=r.mean(), bars=tr["bars"].mean(),
                cagr=(eq.iloc[-1] ** (1 / yrs) - 1) if eq.iloc[-1] > 0 else -1, mdd=mdd,
                pf=(pos / neg) if neg > 0 else np.inf, sharpe=sharpe,
                ypos=int((by > 0).sum()), ytot=int(len(by)))


def buyhold(df):
    yrs = (df.index[-1] - df.index[WARMUP]).days / 365
    return (df["close"].iloc[-1] / df["close"].iloc[WARMUP]) ** (1 / yrs) - 1


def main():
    rows, bh = [], {}
    for tf in ["1d", "1h"]:
        for tk in TICKERS:
            df = load_cached(tk, tf)
            if df is None or len(df) < WARMUP + 50:
                continue
            s = mr_signals(df); atrv = atr_arr(df); bh[(tk, tf)] = buyhold(df)
            for name, (ent, side) in recipes(s).items():
                for exmode, sma in [("ma5", s["sma5"]), ("ma20", s["sma20"])]:
                    tr = bt_mr(df, atrv, ent, side, sma, TO_BARS[tf])
                    m = metrics(tr, df)
                    if m:
                        rows.append(dict(tf=tf, ticker=tk, recipe=name,
                                         side="L" if side > 0 else "S", exit=exmode, **m))
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(ROOT, "tradfi", "results_meanrev.csv"), index=False)

    surv = res[(res.n >= 20) & (res.expect > 0) & (res.pf > 1.1) & (res.ypos >= 0.7 * res.ytot)].copy()
    print(f"\n{len(res)} backtests mean-reversion | supervivientes (gate honesto): {len(surv)}")
    print("\nSupervivientes por (tf, lado):")
    print(surv.groupby(["tf", "side"]).size().to_string() if len(surv) else "  (ninguno)")

    print("\n--- TOP 25 por Sharpe ---")
    sh = surv.sort_values("sharpe", ascending=False).head(25).copy()
    for col, f in [("wr", 100), ("expect", 100), ("cagr", 100), ("mdd", 100)]:
        sh[col] = (sh[col] * f).round(1 if col in ("expect",) else 0)
    sh["pf"] = sh["pf"].round(2); sh["sharpe"] = sh["sharpe"].round(2); sh["bars"] = sh["bars"].round(0)
    sh["yr"] = sh["ypos"].astype(str) + "/" + sh["ytot"].astype(str)
    print(sh[["tf", "ticker", "recipe", "side", "exit", "n", "bars", "wr", "expect",
              "cagr", "mdd", "pf", "sharpe", "yr"]].to_string(index=False))

    print(f"\nSupervivientes SHORT (prueba imparcial, no riden beta): {len(surv[surv.side=='S'])} "
          f"de {len(res[res.side=='S'])} backtests short")
    print("Sharpe por tf — mediana / máx supervivientes:")
    for tf in ["1d", "1h"]:
        ss = surv[surv.tf == tf]
        if len(ss):
            print(f"  [{tf}] mediana {ss.sharpe.median():.2f} / máx {ss.sharpe.max():.2f}")
    # long que baten B&H ajustado por riesgo (CAGR/|maxDD|)
    surv["risk_adj"] = surv.cagr / surv["mdd"].abs().clip(lower=0.01)
    print("\nLONG diario con mejor retorno/DD que comprar-y-aguantar (B&H DD típico ~0.55):")
    dl = surv[(surv.tf == "1d") & (surv.side == "L")]
    for _, r in dl.sort_values("risk_adj", ascending=False).head(8).iterrows():
        bh_ra = bh[(r.ticker, "1d")] / 0.55
        flag = "  <-- bate B&H risk-adj" if r.risk_adj > bh_ra else ""
        print(f"  {r.ticker:5} {r.recipe:12} {r.exit:4} CAGR {r.cagr*100:+.0f}% DD {r.mdd*100:.0f}% "
              f"ret/DD {r.risk_adj:.2f} (B&H {bh_ra:.2f}){flag}")


if __name__ == "__main__":
    main()

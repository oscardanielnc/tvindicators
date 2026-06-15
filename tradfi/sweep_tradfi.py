"""
TRADFI sweep — nuestros indicadores aplicados a futuros de acciones de Binance.

Datos: Binance lista AMD/MU/LITE/TSLA/AAPL/NVDA pero con semanas de historia →
validamos en el SUBYACENTE (yfinance: diario décadas, 1h ~2yr) y se desplegaría en
el futuro Binance (replica el subyacente). 15m descartado (yfinance solo 60d).

Metodologia = sweep1/2/3 portada a equities:
  - 12 recetas de entrada (componentes individuales + las plantillas del roster cripto),
    en LONG y SHORT, con 2 salidas (atrstop 2xATR+timeout, flip del Supertrend).
  - Costos CONSERVADORES de equities (más altos que cripto). Sin funding.
  - Gate honesto: expectancy neto>0, PF>1.1, año-a-año mayormente positivo, n>=20.
  - Benchmark buy&hold por ticker (clave: en acciones con uptrend secular, cualquier
    long-bias luce bien por beta; los SHORTS y el batir-B&H son la prueba real).

Uso:  python tradfi/sweep_tradfi.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd

# --- traer librería de indicadores (pine_*, t3, dch_trend, supertrend_dir, hacolt, tema,
#     st_flips, bx_trig, tm_trig, rib_str, bxreg) sin correr backtests de cripto ---
ROOT = r"D:\OSCAR\Documents\Trading Proyects\tvindicators"
src = open(os.path.join(ROOT, "portafolio.py"), encoding="utf-8").read()
exec(src.split("daily, stats =")[0])

WARMUP = 300
TICKERS = ["AMD", "MU", "LITE", "TSLA", "AAPL", "NVDA"]
DATA_DIR = os.path.join(ROOT, "tradfi", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# costos equities (conservadores; futuros Binance jóvenes/ilíquidos). Sin funding.
E_MAKER, E_TAKER, E_SLIP = 0.0002, 0.0005, 0.0005
TO_BARS = {"1d": 20, "1h": 48}     # timeout: ~1 mes en diario, ~1 semana en 1h


# ───────────────────────── datos (yfinance, cache local) ─────────────────────────

def load_equity(ticker, tf):
    path = os.path.join(DATA_DIR, f"{ticker}_{tf}.parquet")
    if os.path.exists(path):
        return pd.read_parquet(path)
    import yfinance as yf
    if tf == "1d":
        raw = yf.download(ticker, start="2005-01-01", interval="1d",
                          auto_adjust=True, progress=False)
    else:
        raw = yf.download(ticker, period="730d", interval="1h",
                          auto_adjust=True, progress=False)
    if raw.empty:
        return None
    raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
    df = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.dropna().sort_index()
    df.to_parquet(path)
    return df


def atr_arr(df, n=14):
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    return pine_rma(tr, n).values


# ───────────────────────── motor de backtest (propio, equities) ─────────────────────────

def bt(df, atrv, ent, side, exit_mode, exm, to_bars, atr_mult=2.0):
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    idx = df.index; n = len(df)
    trades, j_free = [], 0
    sig_idx = np.flatnonzero(ent[WARMUP:n - 2]) + WARMUP
    for i_sig in sig_idx:
        if i_sig < j_free:
            continue
        e_i = i_sig + 1; epx = op[e_i]
        if not np.isfinite(epx) or epx <= 0:
            continue
        stop = epx - side * atr_mult * atrv[i_sig]
        j, exit_px, cost_out, t_out = e_i, None, E_MAKER, None
        while j < n - 1:
            if exit_mode == "atrstop":
                hit = lo[j] <= stop if side > 0 else hi[j] >= stop
                if hit:
                    exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                    cost_out, t_out = E_TAKER + E_SLIP, j; break
                if j - e_i + 1 >= to_bars:
                    exit_px, t_out = op[j + 1], j + 1; break
            else:  # flip del Supertrend (sin stop)
                if exm[j]:
                    exit_px, t_out = op[j + 1], j + 1; break
            j += 1
        if exit_px is None:
            break
        net = side * (exit_px / epx - 1) - E_MAKER - cost_out
        trades.append((idx[e_i], idx[t_out], net, t_out - e_i))
        j_free = t_out + 1
    return pd.DataFrame(trades, columns=["t_in", "t_out", "net", "bars"])


# ───────────────────────── señales por df ─────────────────────────

def signals(df):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    up, dn, sd = st_flips(df)
    don = dch_trend(c, h, l, 20)
    hc = hacolt(o, h, l, c)
    ribL, ribS = rib_str(df)
    regU = bxreg(c, up=True); regD = bxreg(c, up=False)
    def edge(b):
        b = np.asarray(b); return b & ~np.roll(b, 1)
    return dict(
        st_up=up, st_dn=dn, sd=sd,
        bxL=bx_trig(c, long=True), bxS=bx_trig(c, long=False),
        don=don, hc=hc, ribL=ribL, ribS=ribS, regU=regU, regD=regD,
        tmG=tm_trig(c), tmR=tm_red(c),
        donU_e=edge(don == 1), donD_e=edge(don == -1),
        hcU_e=edge(hc == 1), hcD_e=edge(hc == -1),
        ribLfull_e=edge(ribL == 10), ribSfull_e=edge(ribS == 10),
    )


def tm_red(c):
    fmacd = pine_ema(c, 8) - pine_ema(c, 21)
    fhist = (fmacd - pine_ema(fmacd, 5)) > 0
    neg = ((~fhist) & (pine_rsi(c, 13) < 50) & (pine_rsi(c, 5) < 50)).values
    return neg & ~np.roll(neg, 1)


def recipes(s):
    """Devuelve {nombre: (entry_bool, side)} para long y short."""
    A = np.logical_and
    R = {}
    # LONG
    R["L_ST"]          = (s["st_up"], 1)
    R["L_ST+DON"]      = (A(s["st_up"], s["don"] == 1), 1)
    R["L_ST+HAC"]      = (A(s["st_up"], s["hc"] == 1), 1)
    R["L_ST+DON+HAC"]  = (A(s["st_up"], A(s["don"] == 1, s["hc"] == 1)), 1)
    R["L_ST+RIB"]      = (A(s["st_up"], s["ribL"] >= 8), 1)
    R["L_BX"]          = (s["bxL"], 1)
    R["L_BX+DON"]      = (A(s["bxL"], s["don"] == 1), 1)
    R["L_BX+reg"]      = (A(s["bxL"], s["regU"]), 1)
    R["L_RIB+reg+ST"]  = (A(s["ribLfull_e"], A(s["regU"], s["sd"] == 1)), 1)
    R["L_TM"]          = (s["tmG"], 1)
    R["L_DON"]         = (s["donU_e"], 1)
    R["L_HAC"]         = (s["hcU_e"], 1)
    # SHORT (espejo)
    R["S_ST"]          = (s["st_dn"], -1)
    R["S_ST+DON"]      = (A(s["st_dn"], s["don"] == -1), -1)
    R["S_ST+HAC"]      = (A(s["st_dn"], s["hc"] == -1), -1)
    R["S_ST+DON+HAC"]  = (A(s["st_dn"], A(s["don"] == -1, s["hc"] == -1)), -1)
    R["S_ST+RIB"]      = (A(s["st_dn"], s["ribS"] >= 8), -1)
    R["S_BX"]          = (s["bxS"], -1)
    R["S_BX+DON"]      = (A(s["bxS"], s["don"] == -1), -1)
    R["S_BX+reg"]      = (A(s["bxS"], s["regD"]), -1)
    R["S_RIB+reg+ST"]  = (A(s["ribSfull_e"], A(s["regD"], s["sd"] == -1)), -1)
    R["S_TM"]          = (s["tmR"], -1)
    R["S_DON"]         = (s["donD_e"], -1)
    R["S_HAC"]         = (s["hcD_e"], -1)
    return R


# ───────────────────────── métricas ─────────────────────────

def metrics(tr, df, tf):
    n = len(tr)
    if n < 5:
        return None
    r = tr["net"]
    yrs = (df.index[-1] - df.index[WARMUP]).days / 365
    eq = (1 + r).cumprod()
    mdd = float(((eq / eq.cummax()) - 1).min())
    by_year = tr.groupby(tr["t_in"].dt.year)["net"].apply(lambda g: np.prod(1 + g) - 1)
    pos = r[r > 0].sum(); neg = abs(r[r <= 0].sum())
    dd = pd.Series(r.values, index=tr["t_in"].values).resample("1D").sum()
    sharpe = dd.mean() / dd.std() * np.sqrt(365) if dd.std() > 0 else 0.0
    return dict(
        n=n, tpy=n / yrs, wr=(r > 0).mean(), expect=r.mean(),
        total=eq.iloc[-1] - 1, cagr=(eq.iloc[-1] ** (1 / yrs) - 1) if eq.iloc[-1] > 0 else -1,
        mdd=mdd, pf=(pos / neg) if neg > 0 else np.inf, sharpe=sharpe,
        ypos=int((by_year > 0).sum()), ytot=int(len(by_year)),
    )


def buyhold(df, tf):
    yrs = (df.index[-1] - df.index[WARMUP]).days / 365
    tot = df["close"].iloc[-1] / df["close"].iloc[WARMUP] - 1
    return (1 + tot) ** (1 / yrs) - 1


# ───────────────────────── sweep ─────────────────────────

def main():
    rows, bh = [], {}
    for tf in ["1d", "1h"]:
        for tk in TICKERS:
            df = load_equity(tk, tf)
            if df is None or len(df) < WARMUP + 50:
                print(f"  {tk} {tf}: sin datos suficientes", file=sys.stderr); continue
            s = signals(df)
            atrv = atr_arr(df)
            bh[(tk, tf)] = buyhold(df, tf)
            R = recipes(s)
            for name, (ent, side) in R.items():
                exm = s["st_dn"] if side > 0 else s["st_up"]   # flip contrario
                for exmode in ["atrstop", "flip"]:
                    tr = bt(df, atrv, ent, side, exmode, exm, TO_BARS[tf])
                    m = metrics(tr, df, tf)
                    if m is None:
                        continue
                    rows.append(dict(tf=tf, ticker=tk, recipe=name, side="L" if side > 0 else "S",
                                     exit=exmode, **m))
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(ROOT, "tradfi", "results_tradfi.csv"), index=False)
    print(f"\n{len(res)} backtests. Buy&Hold CAGR por ticker:")
    for tf in ["1d", "1h"]:
        bhs = "  ".join(f"{tk}:{bh.get((tk,tf),float('nan'))*100:+.0f}%" for tk in TICKERS)
        print(f"  [{tf}] {bhs}")

    # gate de supervivientes (honesto)
    surv = res[(res.n >= 20) & (res.expect > 0) & (res.pf > 1.1) &
               (res.ypos >= 0.7 * res.ytot)].copy()
    surv["score"] = surv["sharpe"]
    surv = surv.sort_values("score", ascending=False)

    print(f"\n===== SUPERVIVIENTES (n>=20, exp>0, PF>1.1, año-a-año>=70%): "
          f"{len(surv)} de {len(res)} =====")
    cols = ["tf", "ticker", "recipe", "side", "exit", "n", "wr", "expect", "cagr",
            "mdd", "pf", "sharpe", "ypos", "ytot"]
    if len(surv):
        sh = surv[cols].copy()
        sh["wr"] = (sh["wr"] * 100).round(0)
        sh["expect"] = (sh["expect"] * 100).round(2)
        sh["cagr"] = (sh["cagr"] * 100).round(0)
        sh["mdd"] = (sh["mdd"] * 100).round(0)
        sh["pf"] = sh["pf"].round(2); sh["sharpe"] = sh["sharpe"].round(2)
        sh["yr"] = sh["ypos"].astype(str) + "/" + sh["ytot"].astype(str)
        print(sh.drop(columns=["ypos", "ytot"]).head(30).to_string(index=False))
        print(f"\n  supervivientes SHORT (no riden beta): {len(surv[surv.side=='S'])}")
        print(f"  supervivientes LONG que BATEN su buy&hold:")
        for _, r in surv[surv.side == "L"].iterrows():
            if r["cagr"] > bh.get((r["ticker"], r["tf"]), 0):
                print(f"    [{r['tf']}] {r['ticker']:5} {r['recipe']:14} {r['exit']:8} "
                      f"CAGR {r['cagr']*100:+.0f}% vs B&H {bh[(r['ticker'],r['tf'])]*100:+.0f}%")
    else:
        print("  (ninguno) — los indicadores no muestran edge robusto en equities con este gate.")


if __name__ == "__main__":
    main()

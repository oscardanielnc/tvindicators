"""
Sweep de SETUPS INTRADIA DE ALTA CONVICCION sobre el universo tradfi descorrelacionado.

Enfoque (ver [[trading-project]]): NO buscar edge que bate buy&hold, sino setups de
ALTO WIN RATE que disparan POCO pero confiable, sobre muchos tickers poco correlacionados
-> agregados dan >=1 trade/día de alta calidad. Todo intradía, plano al cierre (sin overnight).

Familias probadas (long y short, exit al cierre de sesión):
  1. GAP-FADE   — gap de apertura en banda -> fade hacia el cierre previo (gaps tienden a llenarse).
  2. VWAP-REV   — precio se aleja N% del VWAP intradía -> reversión al VWAP.
  3. ORB-VOL    — ruptura del rango de apertura en días de alta volatilidad (momentum).

Gate de convicción: WR>=58%, expectancy neto>0, n>=30, año-a-año >=70% positivos.
Luego: portafolio de los setups supervivientes -> frecuencia agregada + correlación.

Datos: C:\\Users\\LENOVO\\market_data\\databento\\equities_1m_dbeq (1-min consolidado).
Uso: python tradfi/sweep_intraday.py
"""
from __future__ import annotations
import os, glob
import numpy as np
import pandas as pd

STORE = r"C:\Users\LENOVO\market_data\databento\equities_1m_dbeq"
TAKER, SLIP = 0.0005, 0.0004
OPEN_T, END_T, CUT_T = pd.Timestamp("09:30").time(), pd.Timestamp("16:00").time(), pd.Timestamp("10:00").time()


def load5(sym):
    df = pd.read_parquet(os.path.join(STORE, f"{sym}_1m.parquet"))
    idx = pd.to_datetime(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df = df.copy(); df.index = idx.tz_convert("America/New_York")
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df = df[(df.index.time >= OPEN_T) & (df.index.time < END_T)].dropna()
    g = df.resample("5min").agg({"open": "first", "high": "max", "low": "min",
                                 "close": "last", "volume": "sum"}).dropna()
    g["date"] = g.index.date
    tp = (g["high"] + g["low"] + g["close"]) / 3
    g["vwap"] = (tp * g["volume"]).groupby(g["date"]).cumsum() / g["volume"].groupby(g["date"]).cumsum()
    return g


def _close_trade(side, entry, exit_px, R, date):
    gross = side * (exit_px / entry - 1)
    return dict(date=date, side=side, net=gross - 2 * TAKER,
                r=(side * (exit_px - entry) - 2 * TAKER * entry) / R if R > 0 else np.nan)


def gap_fade(g, glo, ghi, stop_pct):
    """Gap de apertura en [glo,ghi] (abs) -> fade hacia cierre previo."""
    out = []
    days = list(g.groupby("date"))
    prev_close = None
    for d, day in days:
        if prev_close is not None and len(day) >= 4:
            o = day["open"].iloc[0]
            gap = o / prev_close - 1
            if glo <= abs(gap) <= ghi:
                side = 1 if gap < 0 else -1                 # gap abajo -> long fade
                entry = o
                target = prev_close                          # llenar el gap
                stop = entry * (1 - side * stop_pct)
                R = abs(entry - stop)
                hi, lo, cl = day["high"].values, day["low"].values, day["close"].values
                exit_px = None
                for k in range(len(day)):
                    if side > 0:
                        if lo[k] <= stop: exit_px = stop; break
                        if hi[k] >= target: exit_px = target; break
                    else:
                        if hi[k] >= stop: exit_px = stop; break
                        if lo[k] <= target: exit_px = target; break
                if exit_px is None: exit_px = cl[-1]
                out.append(_close_trade(side, entry, exit_px, R, d))
        prev_close = day["close"].iloc[-1]
    return pd.DataFrame(out)


def vwap_rev(g, dev, stop_pct):
    """Precio se aleja 'dev' (frac) del VWAP tras 10:00 -> reversión al VWAP."""
    out = []
    for d, day in g.groupby("date"):
        if len(day) < 8: continue
        c, vw = day["close"].values, day["vwap"].values
        hi, lo = day["high"].values, day["low"].values
        t = day.index.time
        side = e = None
        for k in range(len(day)):
            if t[k] < CUT_T: continue
            disp = (c[k] - vw[k]) / vw[k]
            if disp <= -dev: side, e = 1, k; break
            if disp >= dev: side, e = -1, k; break
        if side is None: continue
        entry = c[e]; target = vw[e]
        stop = entry * (1 - side * stop_pct); R = abs(entry - stop)
        exit_px = None
        for k in range(e, len(day)):
            if side > 0:
                if lo[k] <= stop: exit_px = stop; break
                if hi[k] >= target: exit_px = target; break
            else:
                if hi[k] >= stop: exit_px = stop; break
                if lo[k] <= target: exit_px = target; break
        if exit_px is None: exit_px = c[-1]
        out.append(_close_trade(side, entry, exit_px, R, d))
    return pd.DataFrame(out)


def orb_vol(g, n5, minwidth):
    """Ruptura del rango de los primeros n5*5min, solo si rango>=minwidth (frac). Momentum."""
    out = []
    for d, day in g.groupby("date"):
        if len(day) < n5 + 4: continue
        orw = day.iloc[:n5]
        orh, orl = orw["high"].max(), orw["low"].min()
        entry_lvl = (orh + orl) / 2
        if (orh - orl) / entry_lvl < minwidth: continue
        rest = day.iloc[n5:]
        hi, lo, cl = rest["high"].values, rest["low"].values, rest["close"].values
        R = orh - orl; side = e = None
        for k in range(len(rest)):
            if hi[k] >= orh: side, e = 1, k; break
            if lo[k] <= orl: side, e = -1, k; break
        if side is None: continue
        entry = (orh if side > 0 else orl) * (1 + side * SLIP)
        stop = orl if side > 0 else orh
        exit_px = None
        for k in range(e, len(rest)):
            if side > 0 and lo[k] <= stop: exit_px = stop * (1 - SLIP); break
            if side < 0 and hi[k] >= stop: exit_px = stop * (1 + SLIP); break
        if exit_px is None: exit_px = cl[-1]
        out.append(_close_trade(side, entry, exit_px, R, d))
    return pd.DataFrame(out)


def stats(t):
    if len(t) < 30: return None
    net = t["net"]; yrs = max((pd.Timestamp(t["date"].max()) - pd.Timestamp(t["date"].min())).days / 365, 0.5)
    by = t.assign(y=pd.to_datetime(t["date"]).dt.year).groupby("y")["net"].sum()
    return dict(n=len(t), tpy=len(t)/yrs, wr=(net > 0).mean(), exp=net.mean(),
                pf=net[net > 0].sum()/max(abs(net[net <= 0].sum()), 1e-9),
                ypos=int((by > 0).sum()), ytot=int(len(by)))


GRID = (
    [("gap", dict(glo=a, ghi=b, stop_pct=s)) for (a, b) in [(0.01, 0.05), (0.02, 0.08)] for s in (0.02, 0.03)] +
    [("vwap", dict(dev=d, stop_pct=s)) for d in (0.01, 0.015, 0.02) for s in (0.015, 0.025)] +
    [("orb", dict(n5=n, minwidth=w)) for n in (3, 6) for w in (0.01, 0.02)]
)
FAM = {"gap": gap_fade, "vwap": vwap_rev, "orb": orb_vol}


def main():
    syms = sorted(os.path.splitext(os.path.basename(p))[0].replace("_1m", "")
                  for p in glob.glob(os.path.join(STORE, "*_1m.parquet")))
    print(f"Universo: {len(syms)} tickers -> {syms}\n")
    data = {s: load5(s) for s in syms}
    survivors = []
    for s in syms:
        g = data[s]
        for fam, params in GRID:
            t = FAM[fam](g, **params)
            m = stats(t)
            if not m: continue
            if m["wr"] >= 0.58 and m["exp"] > 0 and m["ypos"] >= 0.7 * m["ytot"]:
                survivors.append(dict(sym=s, fam=fam, **params, **m, trades=t))
    print(f"===== SETUPS DE ALTA CONVICCION (WR>=58%, exp>0, año-a-año>=70%): {len(survivors)} =====")
    sv = sorted(survivors, key=lambda x: x["wr"], reverse=True)
    print(f"{'sym':6}{'fam':6}{'n':>5}{'t/año':>6}{'WR%':>6}{'exp%':>7}{'PF':>6}{'años+':>7}  params")
    for r in sv:
        p = {k: v for k, v in r.items() if k in ("glo", "ghi", "stop_pct", "dev", "n5", "minwidth")}
        print(f"{r['sym']:6}{r['fam']:6}{r['n']:5}{r['tpy']:6.0f}{r['wr']*100:6.0f}"
              f"{r['exp']*100:+7.3f}{r['pf']:6.2f}{r['ypos']:4}/{r['ytot']:<2}  {p}")

    if not survivors:
        print("\n(ninguno pasó el gate de convicción)"); return

    # ── PORTAFOLIO: 1 mejor setup por ticker, frecuencia agregada + correlación ──
    best = {}
    for r in sv:
        if r["sym"] not in best:
            best[r["sym"]] = r
    print(f"\n===== PORTAFOLIO (mejor setup por ticker, {len(best)} tickers) =====")
    dailies = {}
    all_dates = set()
    tot_tr = 0
    for s, r in best.items():
        d = r["trades"].groupby("date")["net"].sum()
        dailies[s] = d; all_dates |= set(d.index); tot_tr += r["n"]
    span_days = (max(all_dates) - min(all_dates)).days if all_dates else 1
    trading_days = span_days * 252 / 365
    print(f"  trades totales/año (suma): {sum(r['tpy'] for r in best.values()):.0f} "
          f"-> ~{sum(r['tpy'] for r in best.values())/252:.2f} trades/día de mercado")
    wr_pool = np.average([r["wr"] for r in best.values()], weights=[r["tpy"] for r in best.values()])
    exp_pool = np.average([r["exp"] for r in best.values()], weights=[r["tpy"] for r in best.values()])
    print(f"  WR ponderado: {wr_pool*100:.0f}%  |  expectancy ponderado: {exp_pool*100:+.3f}%/trade")
    D = pd.DataFrame(dailies).fillna(0.0)
    cc = D.corr().values
    print(f"  correlación media entre setups (retorno diario): "
          f"{cc[np.triu_indices(len(D.columns), 1)].mean():.2f}")
    print(f"  cobertura: setups activos en {(D != 0).any(axis=1).sum()} días distintos")


if __name__ == "__main__":
    main()

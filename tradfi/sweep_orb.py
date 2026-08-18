"""
Backtest — Opening Range Breakout (ORB) intradía sobre acciones, datos Databento 1-min.

Por día y ticker:
  - Rango de apertura (OR): high/low de los primeros N min tras 09:30 ET. N ∈ {5,15,30}.
  - Entrada: primera ruptura del OR-high (LONG) u OR-low (SHORT), antes del corte horario.
    Fill al nivel de ruptura + slippage (orden stop, agresiva).
  - Stop: lado opuesto del OR (riesgo R = ancho del OR).
  - Salida: target K×R (opcional), o stop, o CIERRE de sesión (plano overnight).
  - Costos: taker ambos lados + slippage en fills de mercado.

Gate honesto: expectancy neto>0 en LONG y SHORT (dos lados), año-a-año, PF>1.1.
Uso: python tradfi/sweep_orb.py
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
from __future__ import annotations
import os
import numpy as np
import pandas as pd

DATA = r"D:\OSCAR\Documents\Trading Proyects\tvindicators\tradfi\data_db"
TICKERS = ["AMD", "MU", "LITE", "TSLA", "AAPL", "NVDA"]
TAKER, SLIP = 0.0005, 0.0004              # costos por lado (futuro de acciones, conservador)
SESSION_OPEN = pd.Timestamp("09:30").time()
SESSION_END = pd.Timestamp("16:00").time()
CUTOFF = pd.Timestamp("12:00").time()      # solo rupturas antes del mediodía


def load(sym):
    df = pd.read_parquet(os.path.join(DATA, f"{sym}_1m.parquet"))
    idx = pd.to_datetime(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df = df.copy(); df.index = idx.tz_convert("America/New_York")
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    sess = (df.index.time >= SESSION_OPEN) & (df.index.time < SESSION_END)
    return df[sess].dropna()


def orb_day(g, n_min, target_R):
    """Una operación ORB para el día g (1-min, sesión). Devuelve dict o None."""
    if len(g) < n_min + 10:
        return None
    t = g.index.time
    in_or = np.array([ (x.hour * 60 + x.minute) < (9 * 60 + 30 + n_min) for x in t ])
    orw = g[in_or]
    if len(orw) < max(1, n_min // 2):
        return None
    orh, orl = orw["high"].max(), orw["low"].min()
    R = orh - orl
    if R <= 0:
        return None
    rest = g[~in_or]
    hi, lo, cl = rest["high"].values, rest["low"].values, rest["close"].values
    times = rest.index.time
    # primera ruptura antes del corte
    side = e_i = None
    for k in range(len(rest)):
        if times[k] >= CUTOFF:
            break
        up, dn = hi[k] >= orh, lo[k] <= orl
        if up and dn:
            s = 1 if cl[k] >= orh else (-1 if cl[k] <= orl else 0)
            if s == 0:
                continue
            side = s
        elif up:
            side = 1
        elif dn:
            side = -1
        else:
            continue
        e_i = k
        break
    if side is None:
        return None
    entry_lvl = orh if side > 0 else orl
    entry = entry_lvl * (1 + side * SLIP)
    stop = orl if side > 0 else orh
    target = entry_lvl + side * target_R * R if target_R else None
    exit_px = reason = None
    for k in range(e_i, len(rest)):
        if side > 0:
            if lo[k] <= stop:
                exit_px, reason = stop * (1 - SLIP), "stop"; break
            if target and hi[k] >= target:
                exit_px, reason = target, "target"; break
        else:
            if hi[k] >= stop:
                exit_px, reason = stop * (1 + SLIP), "stop"; break
            if target and lo[k] <= target:
                exit_px, reason = target, "target"; break
    if exit_px is None:
        exit_px, reason = cl[-1], "close"
    gross = side * (exit_px / entry - 1)
    net = gross - 2 * TAKER
    r_mult = side * (exit_px - entry) / R - 2 * TAKER * entry / R
    return dict(date=g.index[0].date(), side=side, net=net, r=r_mult, reason=reason,
                or_pct=R / entry_lvl * 100)


def run(sym_data, n_min, target_R):
    rows = []
    for sym, df in sym_data.items():
        for _, g in df.groupby(df.index.date):
            tr = orb_day(g, n_min, target_R)
            if tr:
                tr["sym"] = sym; rows.append(tr)
    return pd.DataFrame(rows)


def stats(t):
    if len(t) < 10:
        return None
    net = t["net"]
    yrs = (pd.Timestamp(t["date"].max()) - pd.Timestamp(t["date"].min())).days / 365
    by = t.assign(y=pd.to_datetime(t["date"]).dt.year).groupby("y")["net"].apply(lambda g: g.sum())
    eq = net.cumsum()
    mdd = float((eq - eq.cummax()).min())
    return dict(n=len(t), tpy=len(t) / yrs, wr=(net > 0).mean(), exp=net.mean(),
                expR=t["r"].mean(), pf=net[net > 0].sum() / max(abs(net[net <= 0].sum()), 1e-9),
                sharpe=net.mean() / net.std() * np.sqrt(len(t) / yrs) if net.std() > 0 else 0,
                ypos=int((by > 0).sum()), ytot=int(len(by)), cum=eq.iloc[-1])


def show(tag, t):
    s = stats(t)
    if not s:
        print(f"  {tag}: <10 trades"); return s
    print(f"  {tag:26} n={s['n']:4} t/año={s['tpy']:4.0f} WR={s['wr']*100:4.0f}% "
          f"exp={s['exp']*100:+.3f}% expR={s['expR']:+.3f} PF={s['pf']:.2f} "
          f"Sharpe={s['sharpe']:+.2f} años+={s['ypos']}/{s['ytot']} cum={s['cum']*100:+.0f}%")
    return s


def main():
    sym_data = {s: load(s) for s in TICKERS if os.path.exists(os.path.join(DATA, f"{s}_1m.parquet"))}
    print(f"Cargados {len(sym_data)} tickers. Rango: "
          f"{min(d.index.min() for d in sym_data.values()).date()} -> "
          f"{max(d.index.max() for d in sym_data.values()).date()}")
    print(f"Costos: taker {TAKER*100}%/lado + slip {SLIP*100}% | corte ruptura {CUTOFF}\n")

    for n_min in (5, 15, 30):
        for target_R in (None, 1.0, 2.0):
            tgt = f"T={target_R}R" if target_R else "T=cierre"
            t = run(sym_data, n_min, target_R)
            if len(t) == 0:
                continue
            print(f"===== OR={n_min}min  {tgt} =====")
            show("POOL (todos)", t)
            show("LONG", t[t.side == 1])
            show("SHORT", t[t.side == -1])
            print()

    # detalle por ticker de la mejor config base (OR=15, cierre)
    print("===== Detalle por ticker (OR=15min, salida cierre) =====")
    t = run(sym_data, 15, None)
    for sym in sym_data:
        show(sym, t[t.sym == sym])
    t.to_csv(str(_ROOT / "tradfi/results_orb.csv"), index=False)

    # ── REFINACION: filtro de volatilidad (solo rangos de apertura amplios) ──
    print("\n===== REFINACION: filtro por amplitud del OR (OR=30min, salida cierre) =====")
    t30 = run(sym_data, 30, None)
    for q in (0.0, 0.5, 0.7, 0.85):
        thr = t30["or_pct"].quantile(q)
        f = t30[t30["or_pct"] >= thr]
        print(f"\n  -- solo OR_width >= p{int(q*100)} ({thr:.2f}% del precio): {len(f)} trades --")
        show("POOL", f); show("LONG", f[f.side == 1]); show("SHORT", f[f.side == -1])
    print("\n  -- TSLA con filtro de volatilidad (OR=30, cierre) --")
    ts = t30[t30.sym == "TSLA"]
    for q in (0.0, 0.5, 0.7):
        thr = ts["or_pct"].quantile(q)
        show(f"TSLA OR>=p{int(q*100)}", ts[ts["or_pct"] >= thr])


if __name__ == "__main__":
    main()

"""
POC — Hipótesis del usuario: "acciones que NO se movieron mucho antes de la apertura de NY,
y cuya PRIMERA vela rompe con fuerza al abrir, guían el resto del día".

= ORB (Opening Range Breakout) condicionado a un PRE-MARKET QUIETO.
Filtro pre-market: rango (high-low) de 08:00-09:30 ET, normalizado por precio, comparado
contra su baseline reciente (mediana móvil 20 días del propio ticker). "Quieto" = ratio bajo.

Probamos las 3 definiciones de "primera vela": OR = 5 / 15 / 30 min.
Gate honesto: ¿el filtro de pre-market quieto MEJORA el ORB base (mismo ticker/lado),
y aguanta año-a-año? Datos: Databento 1-min, extended hours.

Uso: python tradfi/poc_quiet_open.py
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

DATA = r"D:\OSCAR\Documents\Trading Proyects\tvindicators\tradfi\data_db"
TAKER, SLIP = 0.0005, 0.0004
OPEN_MIN = 9 * 60 + 30           # 09:30 ET
SESSION_END = pd.Timestamp("16:00").time()
CUTOFF_MIN = 12 * 60             # rupturas solo antes del mediodía
PM_START, PM_END = 8 * 60, 9 * 60 + 30   # ventana pre-market 08:00-09:30 ET
BASELINE_DAYS = 20


def load_ext(sym):
    """Carga con extended hours (NO recorta pre-market)."""
    df = pd.read_parquet(os.path.join(DATA, f"{sym}_1m.parquet"))
    idx = pd.to_datetime(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df = df.copy(); df.index = idx.tz_convert("America/New_York")
    return df[["open", "high", "low", "close", "volume"]].astype(float).dropna()


def day_features(g):
    """Para un día: rango pre-market % (08:00-09:30) y precio de referencia (último pre-open)."""
    mins = g.index.hour * 60 + g.index.minute
    pm = g[(mins >= PM_START) & (mins < PM_END)]
    if len(pm) < 5:
        return None
    ref = pm["close"].iloc[-1]
    if ref <= 0:
        return None
    pm_rng = (pm["high"].max() - pm["low"].min()) / ref * 100
    return pm_rng, ref


def orb_day(g, n_min, target_R):
    """Operación ORB del día (sesión 09:30-16:00). Devuelve dict o None."""
    mins = g.index.hour * 60 + g.index.minute
    sess = g[(mins >= OPEN_MIN) & (g.index.time < SESSION_END)]
    if len(sess) < n_min + 10:
        return None
    smins = sess.index.hour * 60 + sess.index.minute
    in_or = smins < (OPEN_MIN + n_min)
    orw = sess[in_or]
    if len(orw) < max(1, n_min // 2):
        return None
    orh, orl = orw["high"].max(), orw["low"].min()
    R = orh - orl
    if R <= 0:
        return None
    rest = sess[~in_or]
    hi, lo, cl = rest["high"].values, rest["low"].values, rest["close"].values
    rmins = rest.index.hour * 60 + rest.index.minute
    side = e_i = None
    for k in range(len(rest)):
        if rmins[k] >= CUTOFF_MIN:
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
    net = side * (exit_px / entry - 1) - 2 * TAKER
    r_mult = side * (exit_px - entry) / R - 2 * TAKER * entry / R
    return dict(side=side, net=net, r=r_mult, reason=reason, or_pct=R / entry_lvl * 100)


def build(sym, n_min, target_R):
    """Tabla de trades por día con features de pre-market."""
    df = load_ext(sym)
    rows = []
    for d, g in df.groupby(df.index.date):
        feat = day_features(g)
        if feat is None:
            continue
        pm_rng, ref = feat
        tr = orb_day(g, n_min, target_R)
        if tr is None:
            continue
        tr.update(date=d, sym=sym, pm_rng=pm_rng)
        rows.append(tr)
    t = pd.DataFrame(rows)
    if len(t) == 0:
        return t
    t = t.sort_values("date").reset_index(drop=True)
    # baseline: mediana móvil del rango pre-market (20 días previos, sin look-ahead)
    t["pm_base"] = t["pm_rng"].shift(1).rolling(BASELINE_DAYS, min_periods=10).median()
    t["pm_ratio"] = t["pm_rng"] / t["pm_base"]
    return t


def stats(t):
    if len(t) < 10:
        return None
    net = t["net"]
    yrs = max((pd.Timestamp(t["date"].max()) - pd.Timestamp(t["date"].min())).days / 365, 0.1)
    by = t.assign(y=pd.to_datetime(t["date"]).dt.year).groupby("y")["net"].sum()
    eq = net.cumsum(); mdd = float((eq - eq.cummax()).min())
    return dict(n=len(t), tpy=len(t) / yrs, wr=(net > 0).mean(), exp=net.mean(),
                expR=t["r"].mean(), pf=net[net > 0].sum() / max(abs(net[net <= 0].sum()), 1e-9),
                sharpe=net.mean() / net.std() * np.sqrt(len(t) / yrs) if net.std() > 0 else 0,
                ypos=int((by > 0).sum()), ytot=int(len(by)), mdd=mdd, cum=eq.iloc[-1])


def show(tag, t):
    s = stats(t)
    if not s:
        print(f"  {tag:30} <10 trades"); return
    print(f"  {tag:30} n={s['n']:4} t/a={s['tpy']:4.0f} WR={s['wr']*100:3.0f}% "
          f"exp={s['exp']*100:+.3f}% expR={s['expR']:+.2f} PF={s['pf']:.2f} "
          f"Shrp={s['sharpe']:+.2f} a+={s['ypos']}/{s['ytot']} cum={s['cum']*100:+.0f}%")


def main():
    syms = [f.replace("_1m.parquet", "") for f in os.listdir(DATA) if f.endswith("_1m.parquet")]
    syms.sort()
    print(f"Universo ({len(syms)}): {', '.join(syms)}")
    print(f"Pre-market window: 08:00-09:30 ET | baseline {BASELINE_DAYS}d | "
          f"costos {TAKER*100}%/lado + slip {SLIP*100}%\n")

    for n_min in (5, 15, 30):
        print(f"################  OR = {n_min} min (primera vela = {n_min}min)  ################")
        # acumular trades de todos los tickers
        all_t = pd.concat([build(s, n_min, None) for s in syms], ignore_index=True)
        all_t = all_t.dropna(subset=["pm_ratio"])
        print(f"  [base sin filtro] pool de {len(all_t)} trades, {all_t['sym'].nunique()} tickers")
        show("BASE pool", all_t)
        show("BASE long", all_t[all_t.side == 1])
        show("BASE short", all_t[all_t.side == -1])
        # filtro pre-market quieto: ratio bajo = quieto
        for q in (0.5, 0.33, 0.25):
            thr = all_t["pm_ratio"].quantile(q)
            f = all_t[all_t["pm_ratio"] <= thr]
            print(f"  -- PRE-MARKET QUIETO: pm_ratio <= p{int(q*100)} ({thr:.2f}) --")
            show(f"  quieto pool", f)
            show(f"  quieto long", f[f.side == 1])
            show(f"  quieto short", f[f.side == -1])
        print()


if __name__ == "__main__":
    main()

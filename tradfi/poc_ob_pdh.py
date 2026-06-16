"""POC — ORB + Order-Block retest + target PDH/PDL (estrategia ICT del usuario).
Largo (corto = espejo):
  PDH/PDL = high/low RTH del día previo.
  ORH15/ORL15 = rango de la 1ª vela 15m de NY (09:30-09:45 ET).
  En 5m: primer CIERRE que rompe ORH15 -> sesgo largo.
  Order-block: una vela 5m posterior retrocede y TOCA ORH15 (low<=ORH15) pero CIERRA por encima
    (rechazo) -> entro al cierre de esa vela.
  SL = low de esa vela de retest (variante 'tight')  ó  ORL15 (variante 'wide').
  TP = PDH (largo) / PDL (corto). Salida: SL, TP, o cierre de sesión.

Honesto: pariente del ORB+TurtleSoup. Gate: expectancy NETA>0 y PF>1.1 en AMBOS lados, y que
SUPERE al ORB plano (si no, la estructura ICT no aporta). Costos equity-perp 5+4bp/lado.
Uso: python tradfi/poc_ob_pdh.py
"""
from __future__ import annotations
import os, sys
from datetime import time as _t
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATA = r"D:\OSCAR\Documents\Trading Proyects\tvindicators\tradfi\data_db"
TAKER, SLIP = 0.0005, 0.0004
OPEN, OREND, CUTOFF, SESS_END = _t(9, 30), _t(9, 45), _t(15, 0), _t(16, 0)
IS_END = pd.Timestamp("2024-01-01").date()


def load_5m(sym):
    df = pd.read_parquet(os.path.join(DATA, f"{sym}_1m.parquet"))
    idx = pd.to_datetime(df.index); idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df = df[["open", "high", "low", "close", "volume"]].astype(float); df.index = idx.tz_convert("America/New_York")
    g5 = df.resample("5min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return g5


def rth(day_df):
    """Sesión regular 09:30-16:00 ET de un frame que ya es de UN solo día."""
    tt = day_df.index.time
    return day_df[(tt >= OPEN) & (tt < SESS_END)]


def trade_day(prev_df, cur_df, day, sl_mode="tight", require_ob=True):
    pv = rth(prev_df)
    if len(pv) < 30:
        return None
    pdh, pdl = pv["high"].max(), pv["low"].min()
    s = rth(cur_df)
    if len(s) < 30:
        return None
    orw = s[s.index.time < OREND]                     # 09:30-09:45 = 3 velas 5m
    if len(orw) < 2:
        return None
    orh, orl = orw["high"].max(), orw["low"].min()
    rest = s[(s.index.time >= OREND) & (s.index.time < SESS_END)]
    o, h, l, c = rest["open"].values, rest["high"].values, rest["low"].values, rest["close"].values
    tt = rest.index.time
    side = None; broke = oppo = None; bi = None
    for i in range(len(rest)):
        if tt[i] >= CUTOFF:
            break
        if c[i] > orh:
            side, broke, oppo, bi = 1, orh, orl, i; break
        if c[i] < orl:
            side, broke, oppo, bi = -1, orl, orh, i; break
    if side is None:
        return None
    # order-block / retest: vela posterior que toca el nivel roto y cierra del lado correcto
    ei = None; sl = None
    for j in range(bi + 1, len(rest)):
        if tt[j] >= SESS_END:
            break
        if side > 0:
            touched = l[j] <= broke
            held = c[j] > broke
            if (touched and held) or (not require_ob):
                ei = j; sl = (l[j] if sl_mode == "tight" else oppo); break
        else:
            touched = h[j] >= broke
            held = c[j] < broke
            if (touched and held) or (not require_ob):
                ei = j; sl = (h[j] if sl_mode == "tight" else oppo); break
    if ei is None:
        return None
    entry = c[ei] * (1 + side * SLIP)                 # entra al cierre de la vela OB (slippage)
    tp = pdh if side > 0 else pdl
    R = side * (entry - sl)
    if R <= 0:                                         # SL del lado equivocado -> setup inválido
        return None
    if side * (tp - entry) <= 0:                       # PDH/PDL ya superado: sin recorrido -> skip
        return None
    rr = side * (tp - entry) / R
    exit_px = reason = None
    for k in range(ei + 1, len(rest)):
        if side > 0:
            if l[k] <= sl:
                exit_px, reason = sl * (1 - SLIP), "SL"; break
            if h[k] >= tp:
                exit_px, reason = tp, "TP"; break
        else:
            if h[k] >= sl:
                exit_px, reason = sl * (1 + SLIP), "SL"; break
            if l[k] <= tp:
                exit_px, reason = tp, "TP"; break
    if exit_px is None:
        exit_px, reason = c[-1], "close"
    net = side * (exit_px / entry - 1) - 2 * TAKER
    return dict(date=day, side=side, net=net, reason=reason, rr=rr,
                r_mult=side * (exit_px - entry) / R - 2 * TAKER * entry / R)


_CACHE = {}

def run(sym, **kw):
    if sym not in _CACHE:                       # agrupa por día UNA vez (evita re-escanear el frame)
        g5 = load_5m(sym)
        _CACHE[sym] = {d: sub for d, sub in g5.groupby(g5.index.date)}
    by_day = _CACHE[sym]
    days = sorted(by_day)
    rows = []
    for k in range(1, len(days)):
        t = trade_day(by_day[days[k - 1]], by_day[days[k]], days[k], **kw)
        if t:
            t["sym"] = sym; rows.append(t)
    return pd.DataFrame(rows)


def stats(t):
    if len(t) < 10:
        return None
    net = t["net"].values
    wr = (net > 0).mean(); g = net[net > 0].sum(); ls = -net[net < 0].sum()
    return dict(n=len(t), wr=wr*100, exp=net.mean()*1e4, pf=g/max(ls, 1e-9),
                tp=(t["reason"] == "TP").mean()*100, rr=t["rr"].median(),
                cum=net.sum()*100, expR=t["r_mult"].mean())


def show(tag, t):
    s = stats(t)
    if not s:
        print(f"  {tag:30} <10 trades"); return
    print(f"  {tag:30} n={s['n']:4} WR={s['wr']:3.0f}% exp={s['exp']:+6.0f}bp PF={s['pf']:.2f} "
          f"TP%={s['tp']:3.0f} RRmed={s['rr']:.1f} expR={s['expR']:+.2f} cum={s['cum']:+.0f}%")


def main():
    syms = sorted(f.replace("_1m.parquet", "") for f in os.listdir(DATA) if f.endswith("_1m.parquet"))
    print(f"OB+PDH/PDL · {len(syms)} tickers · 5m · costos {TAKER*1e4:.0f}+{SLIP*1e4:.0f}bp/lado\n")
    for sl_mode in ("tight", "wide"):
        for require_ob in (True, False):
            tag = f"SL={sl_mode}, OB={'sí' if require_ob else 'no(entra al romper)'}"
            T = pd.concat([run(s, sl_mode=sl_mode, require_ob=require_ob) for s in syms], ignore_index=True)
            print(f"===== {tag} =====")
            show("POOL", T); show("LONG", T[T.side == 1]); show("SHORT", T[T.side == -1])
            T["seg"] = np.where(pd.to_datetime(T["date"]).astype("datetime64[ns]").dt.date < IS_END, "IS", "OOS")
            show("OOS pool", T[T.seg == "OOS"])
            print()
    # detalle por ticker de la variante base (tight+OB)
    print("===== Por ticker (SL=tight, OB=sí) =====")
    T = pd.concat([run(s, sl_mode="tight", require_ob=True) for s in syms], ignore_index=True)
    for s in syms:
        show(s, T[T.sym == s])


if __name__ == "__main__":
    main()

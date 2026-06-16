"""Validación honesta del filtro PRE-MARKET AGITADO sobre ORB-long.
Hipótesis (invertida del usuario): el breakout de apertura tiene MÁS edge cuando el pre-market
(08:00-09:30 ET) YA venía movido (pm_ratio alto) vs su baseline reciente.

Mismo rigor que validate_orb_tsla.py:
  1) HOLDOUT IS/OOS: OR-window y umbral del filtro pm_ratio se eligen SOLO en IS (<2024) por Sharpe IS;
     OOS (>=2024) se reporta sin re-tocar -> estimación insesgada.
  2) ANTI-BETA: comparar contra "long intradía 09:30->16:00 todos los días". Si no le gana en Sharpe, es beta.
  3) PSR(0): probabilidad de Sharpe OOS>0 corrigiendo skew/kurtosis y T pequeño.

Reutiliza poc_quiet_open.build (features pre-market sin look-ahead: baseline shift(1).rolling).
Uso: python tradfi/validate_active_open.py
"""
from __future__ import annotations
import sys, math, os
from statistics import NormalDist
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import poc_quiet_open as P

IS_END = pd.Timestamp("2024-01-01").date()
N01 = NormalDist()
DATA = P.DATA


def psr(sr_pt, T, sk, ku):
    if T < 3:
        return float("nan")
    den = math.sqrt(max(1e-12, 1 - sk * sr_pt + ((ku - 1) / 4) * sr_pt ** 2))
    return N01.cdf((sr_pt * math.sqrt(T - 1)) / den)


def m(net):
    net = np.asarray(net, float)
    if len(net) < 10:
        return None
    sd = net.std(ddof=1) if len(net) > 1 else 0
    if sd == 0:
        return None
    z = (net - net.mean()) / sd
    sr_pt = net.mean() / sd
    wr = (net > 0).mean(); g = net[net > 0].sum(); l = -net[net < 0].sum()
    return dict(n=len(net), wr=wr, exp=net.mean(), pf=g / l if l > 0 else np.inf,
                sharpe=sr_pt * math.sqrt(252), sr_pt=sr_pt,
                sk=float((z ** 3).mean()), ku=float((z ** 4).mean()), T=len(net),
                cum=(1 + pd.Series(net)).prod() - 1)


def bench_long(df):
    """Anti-beta: comprar 1ª barra de sesión (>=09:30), vender al cierre, todos los días."""
    rows = []
    mins = df.index.hour * 60 + df.index.minute
    sess = df[(mins >= P.OPEN_MIN) & (df.index.time < P.SESSION_END)]
    for d, g in sess.groupby(sess.index.date):
        if len(g) < 30:
            continue
        rows.append((d, g["close"].iloc[-1] / g["open"].iloc[0] - 1 - 2 * P.TAKER))
    return pd.DataFrame(rows, columns=["date", "net"])


def validate(sym):
    """Devuelve dict con veredicto OOS o None si datos insuficientes."""
    try:
        df = P.load_ext(sym)
    except Exception:
        return None
    # construir trades long con feature pm_ratio (sin lookahead) para OR 15 y 30
    cand = {}
    for n_min in (15, 30):
        t = P.build(sym, n_min, None)
        t = t.dropna(subset=["pm_ratio"])
        t = t[t.side == 1].copy()
        if len(t) < 60:
            continue
        cand[n_min] = t
    if not cand:
        return None

    # ---- selección SOLO en IS: OR-window x umbral pm_ratio (agitado = ratio >= q) ----
    best = None
    for n_min, t in cand.items():
        t_is = t[pd.to_datetime(t["date"]).dt.date < IS_END]
        for q in (0.0, 0.33, 0.5, 0.67):           # q=0 => sin filtro (base)
            thr = t_is["pm_ratio"].quantile(q)
            mm = m(t_is[t_is["pm_ratio"] >= thr]["net"].values)
            if mm and (best is None or mm["sharpe"] > best["is_sharpe"]):
                best = dict(n_min=n_min, q=q, is_sharpe=mm["sharpe"])
    if best is None:
        return None

    t = cand[best["n_min"]]
    thr = t[pd.to_datetime(t["date"]).dt.date < IS_END]["pm_ratio"].quantile(best["q"])
    seg = np.where(pd.to_datetime(t["date"]).dt.date < IS_END, "IS", "OOS")
    t = t.assign(seg=seg)
    tf = t[t["pm_ratio"] >= thr]
    m_is = m(tf[tf.seg == "IS"]["net"].values)
    m_oos = m(tf[tf.seg == "OOS"]["net"].values)
    m_base_oos = m(t[t.seg == "OOS"]["net"].values)   # base sin filtro, mismos OOS days
    b = bench_long(df)
    b_oos = m(b[pd.to_datetime(b["date"]).dt.date >= IS_END]["net"].values)

    by = {}
    oos = tf[tf.seg == "OOS"]
    for y, v in oos.assign(y=pd.to_datetime(oos["date"]).dt.year).groupby("y")["net"]:
        by[int(y)] = v.sum()

    return dict(sym=sym, n_min=best["n_min"], q=best["q"], thr=thr,
                m_is=m_is, m_oos=m_oos, m_base_oos=m_base_oos, b_oos=b_oos, by=by)


def fmt(mm):
    return "n/a" if not mm else (f"n={mm['n']:3} Shrp={mm['sharpe']:+.2f} PF={mm['pf']:.2f} "
                                 f"exp={mm['exp']*1e4:+5.0f}bp WR={mm['wr']*100:3.0f}%")


def main():
    syms = sorted(f.replace("_1m.parquet", "") for f in os.listdir(DATA) if f.endswith("_1m.parquet"))
    print("=" * 100)
    print("VALIDACIÓN filtro PRE-MARKET AGITADO sobre ORB-long · holdout IS<2024 / OOS>=2024 · anti-beta · PSR")
    print(f"costos {P.TAKER*1e4:.0f}+{P.SLIP*1e4:.0f}bp/lado · pre-market 08:00-09:30 ET · baseline {P.BASELINE_DAYS}d")
    print("=" * 100)
    winners = []
    for s in syms:
        r = validate(s)
        if r is None:
            print(f"\n### {s}: datos insuficientes"); continue
        mo, mb = r["m_oos"], r["m_base_oos"]
        beta = r["b_oos"]["sharpe"] if r["b_oos"] else float("nan")
        print(f"\n### {s}  [IS elige: OR={r['n_min']}min · pm_ratio>=p{int(r['q']*100)} (thr {r['thr']:.2f})]")
        print(f"    IS        : {fmt(r['m_is'])}")
        print(f"    OOS filtro: {fmt(mo)}")
        print(f"    OOS base  : {fmt(mb)}   (sin filtro, mismos años — ¿el filtro AÑADE algo?)")
        print(f"    Anti-beta : long intradía OOS Sharpe {beta:+.2f}")
        if mo:
            p = psr(mo["sr_pt"], mo["T"], mo["sk"], mo["ku"])
            beats_beta = mo["sharpe"] - beta
            beats_base = mo["sharpe"] - (mb["sharpe"] if mb else 0)
            yrs = " · ".join(f"{y}:{v*100:+.0f}%" for y, v in r["by"].items())
            print(f"    PSR(0)={p*100:4.0f}%  vs beta {beats_beta:+.2f}  vs base {beats_base:+.2f}  | OOS años: {yrs}")
            ok = (mo["sharpe"] > 0 and p > 0.90 and beats_beta > 0.15 and beats_base > 0.10
                  and mo["pf"] > 1.10 and r["q"] > 0)
            verdict = "★ PASA (alpha real, filtro aporta)" if ok else "✗ no pasa"
            print(f"    => {verdict}")
            if ok:
                winners.append((s, mo["sharpe"], mo["pf"], beats_beta, beats_base))
    print("\n" + "=" * 100)
    print("GANADORES (PSR>90% · gana al beta +0.15 · el filtro mejora la base +0.10 Sharpe · PF>1.1 · OOS):")
    if winners:
        for s, sh, pf, bb, bbs in sorted(winners, key=lambda x: -x[1]):
            print(f"  {s:6} Sharpe {sh:+.2f}  PF {pf:.2f}  (+{bb:.2f} vs beta, +{bbs:.2f} vs base)")
    else:
        print("  NINGUNO pasa el gate completo.")
    print("=" * 100)


if __name__ == "__main__":
    main()

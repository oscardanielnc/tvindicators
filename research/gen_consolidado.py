"""Regenera CONSOLIDADO.md con métricas REALES recalculadas de las 29 estrategias.
Reusa la reconstrucción array-form (valida_roster_completo) para las 21 + el builder de las 8.
No inventa nada: n, tr/mes, WR, exp_bps, PF, años+, CAGR_1x, maxDD_1x por estrategia, y el
portafolio combinado vol-parity a 1x + anclas de apalancamiento por DD.

Uso: python gen_consolidado.py   (imprime el markdown; lo escribo a CONSOLIDADO.md aparte)
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/valida_roster_completo.py"), encoding="utf-8").read()
exec(src.split("\ndef main():")[0])   # COIN_TF, coin_arrays, entry_array, run_f, met, load_fund, DATA, I, TOP8, daily_pnl, build_tr, eff_bets...

from tvbot import strategies as STRAT

NEW_MAP = {  # sid -> (coin, signal, side, filtros) de las 8 promovidas
    "S22": ("ENA", "SQZ", +1, ["regime"]), "S23": ("SAND", "VTX", -1, ["regime"]),
    "S24": ("WIF", "SQZ", +1, ["regime"]), "S25": ("SEI", "VTX", -1, ["sweep6", "trend"]),
    "S26": ("ARB", "VTX", -1, ["sweep6", "trend"]), "S27": ("RUNE", "VTX", -1, ["sweep6", "trend"]),
    "S28": ("AVAX", "VTX", -1, ["sweep6"]), "S29": ("BNB", "SQZ", +1, ["trend", "vol"]),
}


def tr_for(sid):
    """Trade-level DataFrame (t_in, ret) para cualquiera de las 29, con funding real."""
    if sid in NEW_MAP:
        coin, sname, side, fs = NEW_MAP[sid]
        df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        ft, fr = load_fund(coin); up, dn, _ = I.st_flips(df)
        return build_tr(coin, df, ft, fr, (up, dn), sname, side, fs), "1h"
    coin, tf, side, em, sa = COIN_TF[sid]
    df = pd.read_parquet(DATA.format(c=coin, tf=tf))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    ft, fr = load_fund(coin); A = coin_arrays(coin, df)
    ent = np.asarray(entry_array(sid, A))
    flips = (A["up"], A["tm_red"]) if sid in ("S2", "S14") else (A["up"], A["dn"])
    return run_f(df, side, em, sa, ent, flips, tf, ft, fr), tf


def row(sid, tr):
    r = tr["ret"]; idx = tr["t_in"]
    months = max((idx.max() - idx.min()).days / 30.44, 1)
    eq = (1 + r).cumprod(); dd = (eq / eq.cummax() - 1).min()
    yrs = max((idx.max() - idx.min()).days / 365.25, 0.5)
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    by = tr.assign(y=idx.dt.year).groupby("y")["ret"].mean()
    return dict(n=len(tr), trmes=len(tr) / months, wr=(r > 0).mean() * 100,
                exp=r.mean() * 1e4, pf=r[r > 0].sum() / max(abs(r[r <= 0].sum()), 1e-9),
                cagr=cagr * 100, dd=dd * 100, ypos=int((by > 0).sum()), ytot=int(len(by)))


def lev_for_dd(daily, target_dd):
    """Apalancamiento que lleva el maxDD del portafolio al objetivo (búsqueda)."""
    lo, hi = 1.0, 12.0
    for _ in range(40):
        L = (lo + hi) / 2
        eq = (1 + L * daily).cumprod(); dd = (eq / eq.cummax() - 1).min()
        if abs(dd) > abs(target_dd): hi = L
        else: lo = L
    L = (lo + hi) / 2
    eq = (1 + L * daily).cumprod()
    yrs = (daily.index[-1] - daily.index[0]).days / 365.25
    return L, (eq.iloc[-1] ** (1 / yrs) - 1) * 100, (eq / eq.cummax() - 1).min() * 100


def main():
    sids = [s.sid for s in STRAT.STRATEGIES]
    rows = {}; daily = {}
    for sid in sids:
        tr, tf = tr_for(sid)
        if tr is None or len(tr) == 0:
            continue
        rows[sid] = row(sid, tr)
        daily[sid] = tr.set_index("t_in")["ret"].resample("1D").sum()
    # portafolio combinado vol-parity (suplentes ya entran a su exp real; pesos 1/sigma)
    M = pd.concat(daily.values(), axis=1).fillna(0)
    sig = M.std().replace(0, np.nan); w = (1 / sig); w = (w / w.sum())
    port = (M * w.values).sum(axis=1)
    eqp = (1 + port).cumprod(); ddp = (eqp / eqp.cummax() - 1).min()
    yrs = (M.index[-1] - M.index[0]).days / 365.25
    cagrp = eqp.iloc[-1] ** (1 / yrs) - 1
    sharpe = port.mean() / port.std() * np.sqrt(365)
    posmonths = (port.resample("ME").sum() > 0).mean() * 100

    # imprime filas para construir el doc
    print("SID|name|coin|tf|side|role|n|trmes|wr|exp|pf|cagr|dd|yrs")
    for s in STRAT.STRATEGIES:
        if s.sid not in rows: continue
        m = rows[s.sid]; sd = "L" if s.side > 0 else "S"
        print(f"{s.sid}|{s.name}|{s.coin}|{s.tf}|{sd}|{s.role}|{m['n']}|{m['trmes']:.1f}|"
              f"{m['wr']:.0f}|{m['exp']:.0f}|{m['pf']:.2f}|{m['cagr']:+.0f}|{m['dd']:.0f}|{m['ypos']}/{m['ytot']}")
    print("---PORT---")
    print(f"1x|CAGR {cagrp*100:+.0f}%|maxDD {ddp*100:.1f}%|Sharpe {sharpe:.2f}|meses+ {posmonths:.0f}%")
    for tgt in (-0.15, -0.20, -0.30):
        L, c, d = lev_for_dd(port, tgt)
        print(f"{L:.2f}x|CAGR {c:+.0f}%|maxDD {d:.0f}%|(ancla DD{tgt*100:.0f}%)")
    # por año del portafolio
    by = port.groupby(port.index.year).sum() * 100
    print("AÑOS|" + " ".join(f"{y}:{v:+.0f}%" for y, v in by.items()))
    print(f"NTOT|{len(rows)}")


if __name__ == "__main__":
    main()

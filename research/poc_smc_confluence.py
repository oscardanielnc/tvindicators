"""POC — Confluencia del Swing BOS (SMC) con filtros del roster y contexto SMC.
Base: sBOS cripto validado (bidireccional, exp +51bp PF1.28). Pregunta: ¿algún filtro SUBE el edge
(exp/PF/Sharpe) filtrando mejores ganadores, sin matar la muestra?
Filtros (direccionales donde aplica), exigidos en la barra de señal:
  roster: trend (EMA), vol (vol_ok), regime (B-X), sweep (barrido de liquidez<=6)
  SMC:    itrend (trend interno SMC concuerda), zoneBuyLow (long en discount / short en premium)
Salida SL 2xATR+timeout (igual que la validación). Uso: python poc_smc_confluence.py
"""
from __future__ import annotations
import sys, math
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import smc
from poc_smc import load_crypto, atr14, CRYPTO, TAKER, SLIP, TIMEOUT_BARS
from tvbot import indicators as I

IS_END = pd.Timestamp("2024-09-01", tz="UTC")


def sim_sided(df, ent, side, atr):
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    n = len(df); rows = []; i = 5
    while i < n - 1:
        if not ent[i] or side[i] == 0:
            i += 1; continue
        s = int(side[i]); e = i + 1; epx = o[e]; stop = epx - s * 2 * atr[i]; exit_px = None
        for j in range(e, min(e + TIMEOUT_BARS, n)):
            if (s > 0 and l[j] <= stop) or (s < 0 and h[j] >= stop):
                exit_px = (min(o[j], stop) if s > 0 else max(o[j], stop)) * (1 - s * SLIP); co = TAKER + SLIP; break
        if exit_px is None:
            j = min(e + TIMEOUT_BARS, n - 1); exit_px = c[j]; co = TAKER
        rows.append((df.index[e], s * (exit_px / epx - 1) - TAKER - co)); i = j + 1
    return pd.DataFrame(rows, columns=["t", "net"])


def filters(df, res):
    """Arrays bool por barra, ya orientados: dict nombre -> (okLong, okShort)."""
    c = df["close"]
    trL = np.asarray(I.ema_trend_ok(c, +1)); trS = np.asarray(I.ema_trend_ok(c, -1))
    vol = np.asarray(I.vol_ok(df))
    _, _, regup, regdn = (np.asarray(x) for x in I.bx_parts(c))
    sL, sS = I.liquidity_sweeps(df)
    swL = np.asarray(I.sweep_recent(sL, 6)); swS = np.asarray(I.sweep_recent(sS, 6))
    itr = res["itrend"]; disc = res["discount"]; prem = res["premium"]
    return {
        "trend":      (trL, trS),
        "vol":        (vol, vol),
        "regime":     (regup, regdn),
        "sweep":      (swL, swS),
        "itrend":     (itr == smc.BULL, itr == smc.BEAR),
        "zoneBuyLow": (disc, prem),
    }


def stats(T):
    if len(T) < 15:
        return None
    T = T.copy(); T["t"] = pd.to_datetime(T["t"], utc=True)
    net = T["net"].values; pf = net[net > 0].sum() / max(-net[net < 0].sum(), 1e-9)
    oos = T[T["t"] >= IS_END]["net"].values
    d = T.set_index("t")["net"].sort_index().resample("1D").sum()
    do = d[d.index >= IS_END]
    sh = do.mean() / do.std(ddof=1) * math.sqrt(365) if len(do) > 2 and do.std(ddof=1) > 0 else 0
    return dict(n=len(T), exp=net.mean()*1e4, pf=pf,
                oexp=oos.mean()*1e4 if len(oos) else np.nan,
                opf=(oos[oos>0].sum()/max(-oos[oos<0].sum(),1e-9)) if len(oos) else np.nan,
                oosh=sh)


def main():
    print(f"CONFLUENCIA sBOS cripto · SL 2xATR+timeout{TIMEOUT_BARS} · costos {TAKER*1e4:.0f}+{SLIP*1e4:.0f}bp · OOS>={IS_END.date()}\n")
    combos = ["BASE", "trend", "vol", "regime", "sweep", "itrend", "zoneBuyLow",
              "trend+vol", "trend+regime", "trend+itrend"]
    agg = {k: [] for k in combos}
    for cs in CRYPTO:
        try:
            df = load_crypto(cs)
        except Exception:
            continue
        if len(df) < 600:
            continue
        res = smc.compute(df); atr = atr14(df)
        bull, bear = res["sbos_bull"], res["sbos_bear"]
        base_ent = bull | bear
        side = np.where(bull, 1, np.where(bear, -1, 0)).astype(np.int8)
        F = filters(df, res)

        def okmask(names):
            okL = np.ones(len(df), bool); okS = np.ones(len(df), bool)
            for nm in names:
                fl, fs = F[nm]; okL &= fl; okS &= fs
            return np.where(side > 0, okL, okS)

        for combo in combos:
            if combo == "BASE":
                ent = base_ent
            else:
                ent = base_ent & okmask(combo.split("+"))
            agg[combo].append(sim_sided(df, ent, side, atr))

    print(f"  {'combo':16} {'n':>5} {'exp':>8} {'PF':>6}   {'OOS exp':>8} {'OOS PF':>6} {'OOS Sharpe':>10}")
    base = stats(pd.concat(agg["BASE"], ignore_index=True))
    for combo in combos:
        s = stats(pd.concat(agg[combo], ignore_index=True))
        if s is None:
            print(f"  {combo:16} <15"); continue
        d_exp = s["exp"] - base["exp"]
        star = "★" if (combo != "BASE" and s["exp"] > base["exp"] and s["pf"] > base["pf"]
                       and s["oosh"] > base["oosh"] and s["n"] > 60) else " "
        print(f" {star}{combo:16} {s['n']:>5} {s['exp']:>+7.0f}bp {s['pf']:>6.2f}   "
              f"{s['oexp']:>+7.0f}bp {s['opf']:>6.2f} {s['oosh']:>+10.2f}"
              + (f"   Δexp {d_exp:+.0f}bp" if combo != "BASE" else "   <- baseline"))


if __name__ == "__main__":
    main()

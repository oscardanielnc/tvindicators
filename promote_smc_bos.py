"""Promoción sBOS — Paso 1 (selección de monedas/lado robustos) + Paso 2 (chequeo de cartera).
Por (moneda,lado): n, exp, PF, OOS. Gate de selección: n>=25, exp>0, OOS exp>0, PF>=1.15.
Luego: correlación de PnL diario entre los seleccionados + nº efectivo de apuestas (que no apilen
la misma exposición). Imprime el roster sBOS elegido para cablear. Uso: python promote_smc_bos.py
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import smc
from poc_smc import load_crypto, atr14, CRYPTO, TAKER, SLIP, TIMEOUT_BARS

IS_END = pd.Timestamp("2024-09-01", tz="UTC")


def sbos_trades(df, atr):
    res = smc.compute(df)
    bull, bear = res["sbos_bull"], res["sbos_bear"]
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    n = len(df); rows = []; i = 5
    while i < n - 1:
        side = 1 if bull[i] else (-1 if bear[i] else 0)
        if side == 0:
            i += 1; continue
        e = i + 1; epx = o[e]; stop = epx - side * 2 * atr[i]; exit_px = None
        for j in range(e, min(e + TIMEOUT_BARS, n)):
            if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                exit_px = (min(o[j], stop) if side > 0 else max(o[j], stop)) * (1 - side * SLIP); co = TAKER + SLIP; break
        if exit_px is None:
            j = min(e + TIMEOUT_BARS, n - 1); exit_px = c[j]; co = TAKER
        rows.append((df.index[e], side, side * (exit_px / epx - 1) - TAKER - co)); i = j + 1
    return pd.DataFrame(rows, columns=["t", "side", "net"])


def seg_stats(net, t, side_sel):
    sub = net[t["side"] == side_sel] if side_sel else net
    x = sub["net"].values if hasattr(sub, "columns") else sub
    return x


def main():
    print(f"PROMOCIÓN sBOS — selección + cartera · SL2xATR+to{TIMEOUT_BARS} · OOS>={IS_END.date()}\n")
    rows = []; series = {}
    for cs in CRYPTO:
        try:
            df = load_crypto(cs)
        except Exception:
            continue
        if len(df) < 600:
            continue
        t = sbos_trades(df, atr14(df))
        for side, lab in ((1, "L"), (-1, "S")):
            ts = t[t["side"] == side]
            if len(ts) < 25:
                continue
            net = ts["net"].values; oos = ts[ts["t"] >= IS_END]["net"].values
            pf = net[net > 0].sum() / max(-net[net < 0].sum(), 1e-9)
            oexp = oos.mean()*1e4 if len(oos) >= 5 else np.nan
            opf = (oos[oos > 0].sum()/max(-oos[oos < 0].sum(), 1e-9)) if len(oos) >= 5 else np.nan
            key = f"{cs}-{lab}"
            ok = (net.mean() > 0 and pf >= 1.15 and not np.isnan(oexp) and oexp > 0)
            rows.append(dict(key=key, coin=cs, side=side, n=len(ts), exp=net.mean()*1e4,
                             pf=pf, oexp=oexp, opf=opf, ok=ok))
            if ok:
                s = ts.set_index("t")["net"].sort_index()
                s.index = pd.to_datetime(s.index, utc=True)
                series[key] = s.resample("1D").sum()

    R = pd.DataFrame(rows).sort_values("exp", ascending=False)
    print("=== Por moneda/lado (★=pasa gate: n>=25, exp>0, OOS exp>0, PF>=1.15) ===")
    for _, r in R.iterrows():
        star = "★" if r["ok"] else " "
        print(f" {star}{r['key']:9} n={int(r['n']):4} exp={r['exp']:+6.0f}bp PF={r['pf']:.2f} "
              f"OOSexp={r['oexp']:+6.0f}bp OOSpf={r['opf']:.2f}")

    sel = R[R["ok"]]["key"].tolist()
    print(f"\nSeleccionados ({len(sel)}): {sel}")
    if len(sel) < 2:
        print("Muy pocos para cartera."); return

    M = pd.concat({k: series[k] for k in sel}, axis=1).fillna(0.0)
    cc = M.corr()
    off = cc.values[np.triu_indices(len(sel), 1)]
    ev = np.linalg.eigvalsh(cc.values); eff = (ev.sum()**2)/(ev**2).sum()
    print(f"\n=== Cartera de los seleccionados ===")
    print(f"  correlación media entre pares: {np.nanmean(off):+.2f}  (baja = diversifican)")
    print(f"  nº efectivo de apuestas: {eff:.1f} de {len(sel)}  -> "
          f"{'diversifican bien' if eff > len(sel)*0.6 else 'algo redundantes'}")
    # pares muy correlacionados (posible redundancia)
    hi = [(sel[i], sel[j], cc.values[i, j]) for i in range(len(sel)) for j in range(i+1, len(sel)) if cc.values[i, j] > 0.5]
    if hi:
        print("  pares corr>0.5 (revisar redundancia): " + ", ".join(f"{a}~{b}({c:.2f})" for a, b, c in hi))
    else:
        print("  ningún par corr>0.5: set descorrelacionado.")
    # sugerencia final: top por exp con dedup simple (quitar el de menor exp en pares corr>0.7)
    drop = set()
    for a, b, c in hi:
        if c > 0.7:
            ea = R[R.key == a]["exp"].values[0]; eb = R[R.key == b]["exp"].values[0]
            drop.add(b if eb < ea else a)
    final = [k for k in sel if k not in drop]
    print(f"\nROSTER sBOS sugerido para cablear ({len(final)}): {final}")
    if drop:
        print(f"  (descartados por redundancia corr>0.7: {sorted(drop)})")


if __name__ == "__main__":
    main()

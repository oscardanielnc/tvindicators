"""Reconciliación señal VIVA vs BACKTEST.
El bot evalúa en vivo con las funciones escalares sN_entry (último bar cerrado). El backtest
usa la reconstrucción vectorizada (arrays). Si divergen (timezone, vela en curso, warmup, o un
edit que toca solo una de las dos), la comparación live-vs-backtest queda corrupta SIN avisar.
Esto lo verifica: para cada estrategia, sobre velas recientes, compara sN_entry(df[:k+1]) (camino
vivo) contra el array del backtest en k. Reporta mismatches. Uso: python reconcile.py
"""
import sys
import numpy as np
import pandas as pd

try:                                    # consola/hook en Windows suele ser cp1252; el reporte usa ✅/⚠
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\gen_summary.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # COIN_TF, coin_arrays, entry_array, TOP8_SID, SIGFN, LATE, I, filt_arrays, getdf, STRAT

from tvbot import strategies as STRAT

TOPFN = {"SQZ": I.squeeze_momentum, "VTX": I.vortex}
WINDOW = 2500     # velas recientes a revisar (rápido y representativo)
SAMPLE_SIG = 25   # muestras donde el backtest dice señal
SAMPLE_NON = 15   # muestras donde NO


def entry_array_for(sid, df):
    """Array de entrada estilo backtest (referencia independiente del sN_entry escalar)."""
    s = STRAT.BY_ID[sid]
    if sid in COIN_TF:
        return np.asarray(entry_array(sid, coin_arrays(s.coin, df)))
    if sid == "S30":
        c = df["close"]; basis = c.rolling(20).mean(); dev = 2.0 * c.rolling(20).std(ddof=0)
        cond = (c < (basis - dev)) & (c > c.rolling(200).mean())
        ev = cond.values & ~np.roll(cond.values, 1); ev[0] = False
        return ev
    if sid in TOP8_SID:
        coin, sname, side, fs = TOP8_SID[sid]; fn = TOPFN[sname]
    else:
        coin, fam, side, fs = LATE[sid]; fn = SIGFN[fam]
    le, se = fn(df); ev = np.asarray(le if side > 0 else se)
    fa = filt_arrays(df, side); m = np.ones(len(df), bool)
    for f in fs:
        m &= fa[f]
    return ev & m


def main():
    print(f"Reconciliación señal viva (sN_entry) vs backtest (array) · ventana {WINDOW} velas recientes\n")
    total_mis = 0; flagged = []
    rng = np.random.RandomState(0)
    for s in STRAT.STRATEGIES:
        try:
            df0 = getdf(s.coin, s.tf)
        except Exception:
            continue
        df = df0.iloc[-WINDOW:] if len(df0) > WINDOW else df0
        arr = entry_array_for(s.sid, df)
        lo = 600  # margen de warmup dentro de la ventana
        sig_idx = [k for k in range(lo, len(df)) if arr[k]]
        non_idx = [k for k in range(lo, len(df)) if not arr[k]]
        samp = (list(rng.permutation(sig_idx))[:SAMPLE_SIG] if sig_idx else []) + \
               (list(rng.permutation(non_idx))[:SAMPLE_NON] if non_idx else [])
        mis = 0
        for k in samp:
            live = bool(s.entry_signal(df.iloc[:k + 1]))
            ref = bool(arr[k])
            if live != ref:
                mis += 1
        total_mis += mis
        if mis:
            flagged.append((s.sid, s.coin, mis, len(samp), len(sig_idx)))
        # progreso compacto
        print(f"  {s.sid:4} {s.coin:5} señales_bt={len(sig_idx):4} muestras={len(samp):3} "
              f"mismatches={mis}", end="\r" if not mis else "\n", flush=True)

    print("\n" + "=" * 70)
    if total_mis == 0:
        print("✅ RECONCILIACIÓN OK: el camino vivo reproduce el backtest en las 56 (0 mismatches).")
        print("   La comparación live-vs-backtest del dashboard es JUSTA.")
    else:
        print(f"⚠ {total_mis} mismatches en {len(flagged)} estrategias — REVISAR (la señal viva NO coincide):")
        for sid, coin, mis, n, ns in flagged:
            print(f"   {sid} {coin}: {mis}/{n} discrepancias (señales bt={ns})")
    return total_mis


if __name__ == "__main__":
    # exit-code != 0 si hay mismatches -> el pre-push hook bloquea el push (ver hooks/pre-push)
    sys.exit(1 if main() else 0)

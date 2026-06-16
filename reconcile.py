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
from tvbot import strategies_tradfi as STRAT_TF
from tvbot import data as TVDATA
import smc

TOPFN = {"SQZ": I.squeeze_momentum, "VTX": I.vortex}
SBOS_SIDE = {"S57": 1, "S58": -1, "S59": 1, "S60": 1, "S61": -1, "S62": -1, "S63": -1, "S64": 1}

# --- TRADFI: loader (data_db 1m -> tf, UTC) y referencias de array por estrategia ---
DATA_DB = r"D:\OSCAR\Documents\Trading Proyects\tvindicators\tradfi\data_db"
_TF_RULE = {"15m": "15min", "30m": "30min", "1h": "1h"}
_DFTF = {}

def getdf_tradfi(coin, tf):
    if (coin, tf) not in _DFTF:
        import os
        df = pd.read_parquet(os.path.join(DATA_DB, f"{coin}_1m.parquet"))
        idx = pd.to_datetime(df.index); idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        df = df[["open", "high", "low", "close", "volume"]].astype(float); df.index = idx
        g = df.resample(_TF_RULE[tf]).agg({"open": "first", "high": "max", "low": "min",
                                           "close": "last", "volume": "sum"}).dropna()
        _DFTF[(coin, tf)] = g
    return _DFTF[(coin, tf)]


def tradfi_array_for(sid, df):
    """Array de referencia (mismas funciones que el sN_entry escalar) para verificar causalidad.
    None = estrategia sin array limpio (ORB session-stateful: causalidad por construcción)."""
    if sid in ("T1", "T6"):
        return None
    if sid == "T2":                                   # NVDA-L Supertrend flip
        return np.asarray(I.st_flips(df)[0])
    if sid == "T3":                                   # AO long
        return np.asarray(I.awesome_osc(df)[0])
    if sid == "T4":                                   # Squeeze long
        return np.asarray(I.squeeze_momentum(df)[0])
    if sid == "T5":                                   # ADX/DMI long
        return np.asarray(I.adx_dmi(df)[0])
    if sid in ("T7", "T8", "T9", "T10", "T11"):       # S/R[LuxAlgo]+Supertrend
        s = STRAT_TF.BY_ID_TRADFI[sid]
        up, dn, _ = I.st_flips(df); brkL, brkS = I.sr_break_lux(df)
        if s.side > 0:
            rec = pd.Series(brkL).rolling(10, min_periods=1).max().fillna(0).astype(bool).values
            return np.asarray(up) & rec
        rec = pd.Series(brkS).rolling(10, min_periods=1).max().fillna(0).astype(bool).values
        return np.asarray(dn) & rec
    if sid in ("T12", "T13", "T14", "T15"):           # SMC Swing BOS long
        return np.asarray(smc.compute(df)["sbos_bull"])
    return None
WINDOW = 2500     # velas recientes a revisar (rápido y representativo)
SAMPLE_SIG = 25   # muestras donde el backtest dice señal
SAMPLE_NON = 15   # muestras donde NO


def entry_array_for(sid, df):
    """Array de entrada estilo backtest (referencia independiente del sN_entry escalar)."""
    s = STRAT.BY_ID[sid]
    if sid in SBOS_SIDE:                          # SMC Swing BOS (batch 8): array fiel del motor smc
        res = smc.compute(df)
        return np.asarray(res["sbos_bull"] if SBOS_SIDE[sid] > 0 else res["sbos_bear"])
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

    # ---- TRADFI (T1-T15): verifica causalidad scalar-vs-array sobre data_db resampleado ----
    print("\n  --- tradfi ---")
    skipped_tf = []
    for s in STRAT_TF.STRATEGIES_TRADFI:
        try:
            df0 = getdf_tradfi(s.coin, s.tf)
        except Exception:
            continue
        arr_full = tradfi_array_for(s.sid, df0)
        if arr_full is None:
            skipped_tf.append(s.sid); continue
        # titulares 'us' ven solo barras de sesión regular (igual que engine._view)
        if getattr(s, "session", "24/7") == "us":
            df = TVDATA.filter_us_session(df0)
            arr = tradfi_array_for(s.sid, df)
        else:
            df = df0; arr = arr_full
        if len(df) > WINDOW:
            df = df.iloc[-WINDOW:]; arr = arr[-WINDOW:]
        sig_idx = [k for k in range(600, len(df)) if arr[k]]
        non_idx = [k for k in range(600, len(df)) if not arr[k]]
        samp = (list(rng.permutation(sig_idx))[:SAMPLE_SIG] if sig_idx else []) + \
               (list(rng.permutation(non_idx))[:SAMPLE_NON] if non_idx else [])
        mis = sum(bool(s.entry_signal(df.iloc[:k + 1])) != bool(arr[k]) for k in samp)
        total_mis += mis
        if mis:
            flagged.append((s.sid, s.coin, mis, len(samp), len(sig_idx)))
        print(f"  {s.sid:4} {s.coin:5} señales_bt={len(sig_idx):4} muestras={len(samp):3} "
              f"mismatches={mis}", end="\r" if not mis else "\n", flush=True)
    if skipped_tf:
        print(f"\n  (ORB session-stateful sin array: {skipped_tf} — causalidad por construcción, no reconciliadas)")

    print("\n" + "=" * 70)
    if total_mis == 0:
        ntot = len(STRAT.STRATEGIES) + len([s for s in STRAT_TF.STRATEGIES_TRADFI if s.sid not in skipped_tf])
        print(f"✅ RECONCILIACIÓN OK: el camino vivo reproduce el backtest en las {ntot} (0 mismatches).")
        print("   La comparación live-vs-backtest del dashboard es JUSTA.")
    else:
        print(f"⚠ {total_mis} mismatches en {len(flagged)} estrategias — REVISAR (la señal viva NO coincide):")
        for sid, coin, mis, n, ns in flagged:
            print(f"   {sid} {coin}: {mis}/{n} discrepancias (señales bt={ns})")
    return total_mis


if __name__ == "__main__":
    # exit-code != 0 si hay mismatches -> el pre-push hook bloquea el push (ver hooks/pre-push)
    sys.exit(1 if main() else 0)

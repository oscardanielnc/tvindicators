"""Validación de la SHORTLIST de indicadores (del indicator_probe) con holdout IS/OOS + anti-beta.
Cada candidato (ticker, TF, indicador, long) se prueba:
  1) HOLDOUT: métricas IS (<2024) y OOS (>=2024) por separado. Sobrevive si es positivo en AMBOS.
  2) ANTI-BETA: ¿el Sharpe OOS supera a comprar-y-mantener (buy&hold) el mismo activo/TF en OOS?
     Si no lo supera, el 'edge' es solo beta sub-muestreada (long en un activo alcista) + costos.
Sharpe anualizado HONESTO = SR_por-trade · sqrt(trades/año) (no √252).
Uso: python validate_indicators.py
"""
import os
import sys
import math
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from indicator_probe import load_tf, signals, ATR_K, COST
from tvbot import indicators as I

IS_END = pd.Timestamp("2024-01-01").date()
WARM = 300

# shortlist del probe (todos LONG): (ticker, TF, indicador)
SHORTLIST = [
    ("TSLA", "15m", "Supertrend"), ("TSLA", "30m", "ADX"), ("TSLA", "15m", "Squeeze"),
    ("TSLA", "15m", "AO"), ("TSLA", "15m", "TSI"), ("TSLA", "15m", "ZeroLag"),
    ("TSLA", "30m", "ZeroLag"), ("TSLA", "15m", "Vortex"), ("TSLA", "15m", "ADX"),
    ("NVDA", "15m", "Squeeze"), ("NVDA", "1h", "Squeeze"), ("NVDA", "30m", "Supertrend"),
    ("NVDA", "30m", "AO"), ("LITE", "1h", "Supertrend"), ("LITE", "30m", "Supertrend"),
    ("TSLA", "1d", "Supertrend"), ("TSLA", "1d", "Squeeze"), ("TSLA", "1d", "TSI"),
]


def backtest_dated(df, entries, side, st_dir):
    """Como el probe pero registra la fecha de entrada (para partir IS/OOS)."""
    op = df["open"].values; hi = df["high"].values; lo = df["low"].values; cl = df["close"].values
    atr = I.atr14(df).values
    idx = df.index; n = len(df); i = WARM; out = []
    while i < n - 1:
        if not entries[i] or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1; continue
        e = i + 1; ep = op[e]; stop = ep - side * ATR_K * atr[i]
        ex = None; j = e
        while j < n - 1:
            if side > 0 and lo[j] <= stop:
                ex = min(op[j], stop); break
            if side < 0 and hi[j] >= stop:
                ex = max(op[j], stop); break
            if st_dir[j] == -side:
                ex = op[j + 1]; break
            j += 1
        if ex is None:
            ex = cl[-1]; j = n - 1
        out.append((idx[e], side * (ex / ep - 1) - COST)); i = j + 1
    return out


def met(rets, years):
    r = np.asarray(rets, float)
    if len(r) < 12:
        return None
    sd = r.std(ddof=1); tpy = len(r) / years
    g = r[r > 0].sum(); l = -r[r < 0].sum()
    return dict(n=len(r), tpy=tpy, wr=(r > 0).mean(), exp=r.mean(), pf=(g / l if l > 0 else np.inf),
                sharpe=(r.mean() / sd * math.sqrt(tpy) if sd > 0 else 0))


def buyhold_sharpe(df, mask):
    """Sharpe anualizado de comprar-y-mantener sobre las barras OOS (benchmark beta)."""
    sub = df[mask]
    if len(sub) < 100:
        return None
    br = sub["close"].pct_change().dropna().values
    if br.std() == 0:
        return None
    years = max((sub.index[-1] - sub.index[0]).days / 365.25, 0.5)
    bpy = len(br) / years
    return br.mean() / br.std(ddof=1) * math.sqrt(bpy)


def main():
    print("=" * 104)
    print("VALIDACIÓN SHORTLIST INDICADORES — holdout IS/OOS + anti-beta (buy&hold)")
    print("=" * 104)
    print(f"{'cand':28} {'IS:Sh/PF/exp':>20} {'OOS:Sh/PF/exp/n':>26} {'B&H OOS Sh':>11} {'veredicto'}")
    survivors = []
    cache = {}
    for t, tf, ind in SHORTLIST:
        key = (t, tf)
        if key not in cache:
            try:
                df = load_tf(t, tf)
                cache[key] = (df, I.st_flips(df)[2])
            except Exception as e:
                cache[key] = (None, None)
        df, st_dir = cache[key]
        if df is None or len(df) < 400:
            print(f"{t} {tf} {ind:12}  (sin datos)"); continue
        le, _ = signals(ind, df)
        trades = backtest_dated(df, le, 1, st_dir)
        is_tr = [(d, n) for d, n in trades if d.date() < IS_END]
        oos_tr = [(d, n) for d, n in trades if d.date() >= IS_END]
        if not is_tr or not oos_tr:
            continue
        yr = lambda tr: max((tr[-1][0] - tr[0][0]).days / 365.25, 0.5)
        mis = met([n for _, n in is_tr], yr(is_tr))
        moos = met([n for _, n in oos_tr], yr(oos_tr))
        if mis is None or moos is None:
            print(f"{t} {tf} {ind:12}  (pocos trades)"); continue
        oos_mask = df.index.map(lambda x: x.date() >= IS_END)
        bh = buyhold_sharpe(df, np.asarray(oos_mask))
        # veredicto: positivo en IS y OOS + supera beta OOS
        beats_beta = bh is not None and moos["sharpe"] > bh + 0.1
        ok = mis["exp"] > 0 and moos["exp"] > 0 and moos["pf"] >= 1.1 and beats_beta
        verd = "★ SOBREVIVE" if ok else ("solo beta" if (moos["exp"] > 0 and not beats_beta)
                                          else "falla holdout")
        if ok:
            survivors.append((t, tf, ind, moos, bh))
        cand = f"{t} {tf} {ind}"
        print(f"{cand:28} {mis['sharpe']:+5.2f}/{mis['pf']:.2f}/{mis['exp']*1e4:+4.0f}  "
              f"{moos['sharpe']:+5.2f}/{moos['pf']:.2f}/{moos['exp']*1e4:+4.0f}/{moos['n']:>4}  "
              f"{(bh if bh is not None else float('nan')):+11.2f}  {verd}")

    print("\n" + "=" * 104)
    if survivors:
        print(f"SOBREVIVIENTES ({len(survivors)}) — positivos IS+OOS Y ganan al beta (candidatos a la cartera):")
        for t, tf, ind, mm, bh in sorted(survivors, key=lambda x: -x[3]["sharpe"]):
            print(f"  {t} {tf} {ind:10} L · OOS Sharpe {mm['sharpe']:+.2f} (B&H {bh:+.2f}) · "
                  f"PF {mm['pf']:.2f} · exp {mm['exp']*1e4:+.0f}bp · {mm['tpy']:.0f} t/año")
    else:
        print("NINGUNO sobrevive: todos los long-only indicador son beta sub-muestreada (no ganan a buy&hold")
        print("en OOS) o fallan el holdout. El edge intradía limpio sigue siendo TSLA-ORB.")
    print("\nNota: 'solo beta' = positivo pero NO supera comprar-y-mantener -> apalancarlo = apalancar beta.")


if __name__ == "__main__":
    main()

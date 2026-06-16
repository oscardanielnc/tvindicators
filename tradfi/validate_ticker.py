"""Batería de validación para tickers nuevos: indicador × TF, holdout IS/OOS + anti-beta (vs buy&hold).
Reporta SOBREVIVIENTES (positivo IS+OOS y gana al beta) por ticker. Split por defecto 2025 (datos 3-4 años).
Uso: python validate_ticker.py NKE PFE UNH AAL [IS_END=2025-01-01]"""
import sys
import os
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import validate_indicators as V
from indicator_probe import load_tf, signals, SIGS
from tvbot import indicators as I

args = [a for a in sys.argv[1:] if not a.startswith("20")]
TICKERS = args or ["NKE", "PFE", "UNH", "AAL"]
isend = [a for a in sys.argv[1:] if a.startswith("20")]
V.IS_END = pd.Timestamp(isend[0]).date() if isend else pd.Timestamp("2025-01-01").date()
TFS = ["1h", "30m", "15m"]


def main():
    print("=" * 88)
    print(f"VALIDACIÓN BATERÍA — holdout IS<{V.IS_END}/OOS + anti-beta (long-only)")
    print("=" * 88)
    for t in TICKERS:
        survivors, n_tested, bh_oos = [], 0, None
        for tf in TFS:
            try:
                df = load_tf(t, tf)
            except Exception as e:
                print(f"  {t} {tf}: error {e}"); continue
            st = I.st_flips(df)[2]
            oos_mask = np.asarray(df.index.map(lambda x: x.date() >= V.IS_END))
            bh_oos = V.buyhold_sharpe(df, oos_mask)
            for ind in SIGS:
                le, _ = signals(ind, df)
                tr = V.backtest_dated(df, le, 1, st)
                isr = [(d, n) for d, n in tr if d.date() < V.IS_END]
                oosr = [(d, n) for d, n in tr if d.date() >= V.IS_END]
                if not isr or not oosr:
                    continue
                yr = lambda x: max((x[-1][0] - x[0][0]).days / 365.25, 0.5)
                mi = V.met([n for _, n in isr], yr(isr))
                mo = V.met([n for _, n in oosr], yr(oosr))
                if mi is None or mo is None:
                    continue
                n_tested += 1
                beat = mo["sharpe"] > (bh_oos or 0) + 0.1
                if mi["exp"] > 0 and mo["exp"] > 0 and mo["pf"] >= 1.1 and beat:
                    survivors.append((tf, ind, mo, bh_oos))
        print(f"\n### {t} ### buy&hold OOS Sharpe={bh_oos:+.2f} "
              f"({'rally fuerte -> difícil ganarle' if (bh_oos or 0) > 1.5 else 'beta moderado/bajo -> el timing puede ganar'})")
        if not survivors:
            print(f"  sin sobrevivientes ({n_tested} combos probados) -> no aporta edge sobre el beta")
        for tf, ind, mo, bh in sorted(survivors, key=lambda x: -x[2]["sharpe"]):
            print(f"  ★ {tf:3} {ind:10} OOS Sharpe {mo['sharpe']:+.2f} (B&H {bh:+.2f}) · "
                  f"PF {mo['pf']:.2f} · exp {mo['exp']*1e4:+.0f}bp · {mo['tpy']:.0f} t/año · n={mo['n']}")
    print("\n" + "=" * 88)
    print("★ = positivo IS+OOS Y gana al buy&hold (alpha de timing, no beta). Sin ★ = solo beta/ruido.")


if __name__ == "__main__":
    main()

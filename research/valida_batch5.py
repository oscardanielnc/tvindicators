"""Validacion batch 5: ¿los momentum-systems aportan algo NUEVO o son redundantes?
Foco en candidatos de MONEDA NUEVA (no en roster). corr vs roster + corr mutua + IS/OOS.
Uso: python valida_batch5.py"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/poc_batch5.py"), encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # ichimoku, kst, tsi, ao, run_f, met, filt_arrays, load_fund, DATA, I, FILTER_SETS, split_met, roster_pnl_daily

SIGFN = {"ICHI": ichimoku, "KST": kst, "TSI": tsi, "AO": ao}

# candidatos de MONEDA NUEVA (no en el roster de 38), IS>0 y OOS>0 balanceados
CANDS = [
    ("LINK", "KST", +1, ["sweep6"]),
    ("NEO",  "AO",  +1, ["sweep6", "trend"]),
    ("ICP",  "KST", -1, ["regime"]),
    ("NEAR", "AO",  -1, ["sweep6"]),
    ("ALGO", "TSI", -1, ["sweep6", "trend"]),
    ("TAO",  "AO",  -1, ["trend", "vol"]),
]


def daily(coin, sig, side, fs):
    df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    ft, fr = load_fund(coin); up, dn, _ = I.st_flips(df)
    le, se = SIGFN[sig](df); ev = le if side > 0 else se
    fa = filt_arrays(df, side); mask = np.ones(len(df), bool)
    for f in fs:
        mask &= fa[f]
    tr = run_f(df, side, "atrstop", None, np.asarray(ev) & mask, (up, dn), "1h", ft, fr)
    return tr


def main():
    R = roster_pnl_daily()
    series = {}; rows = []
    for coin, sig, side, fs in CANDS:
        tr = daily(coin, sig, side, fs)
        mi, mo = split_met(tr); m = met(tr)
        d = tr.set_index("t_in")["ret"].resample("1D").sum()
        nm = f"{coin}-{sig}-{'L' if side>0 else 'S'}"
        d.name = nm; series[nm] = d
        al = pd.concat([d, R.rename("R")], axis=1).fillna(0)
        rows.append((nm, m, mi, mo, al.iloc[:, 0].corr(al["R"])))
    print(f"{'='*92}")
    print(f"BATCH 5 — candidatos de MONEDA NUEVA")
    print(f"{'cand':14}{'n':>5}{'exp':>6}{'PF':>6}{'IS':>7}{'OOS':>7}{'corr_roster':>13}")
    print(f"{'-'*92}")
    for nm, m, mi, mo, cr in rows:
        print(f"{nm:14}{m['n']:5}{m['exp']:6.0f}{m['pf']:6.2f}{mi['exp']:7.0f}{mo['exp']:7.0f}{cr:13.2f}")
    # corr mutua
    M = pd.concat(series.values(), axis=1).fillna(0)
    print(f"\nCORR MUTUA:\n{M.corr().round(2).to_string()}")
    ev = np.linalg.eigvalsh(M.corr().values); pr = (ev.sum()**2)/(ev**2).sum()
    off = M.corr().values[np.triu_indices(len(M.corr()), 1)]
    print(f"\ncorr media mutua: {off.mean():.2f} · nº efectivo apuestas: {pr:.1f}/{len(series)}")
    print("Bajo corr vs roster + baja corr mutua = aportan. Alta = redundantes con el momentum existente.")


if __name__ == "__main__":
    main()

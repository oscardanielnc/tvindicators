"""Validación batch 7a: candidatos SRB (S/R High Volume Boxes). KVO se descarta (redundante).
Sensibilidad (lookback/vol_len) + corr vs roster + corr vs incumbente del mismo par/lado.
Uso: python valida_batch7.py"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/poc_batch7.py"), encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # srbreak, run_f, met, filt_arrays, load_fund, DATA, I, FILTER_SETS, split_met, roster_pnl_daily

# candidatos SRB con IS/OOS balanceado: (coin, side, filtros)  + incumbente del mismo par/lado para corr
CANDS = [
    ("UNI",  +1, ["vol"],            None),                                   # NUEVA
    ("DOGE", +1, ["trend"],          None),                                   # NUEVA
    ("FET",  +1, ["vol"],            ("sqz", +1, ["trend", "vol"])),          # vs S50 FET-L
    ("ARB",  -1, ["regime"],         ("adx", -1, ["trend", "vol"])),          # vs S31 ARB-S
    ("ALGO", +1, ["trend", "vol"],   None),                                   # ALGO solo tiene short (S43)
    ("INJ",  +1, ["vol"],            None),                                   # INJ-L vs S30 (meanrev, otra clase)
]
INCFN = {"sqz": I.squeeze_momentum, "adx": I.adx_dmi}


def srb_daily(coin, side, fs, lookback=20, vol_len=2):
    df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    ft, fr = load_fund(coin); up, dn, _ = I.st_flips(df)
    le, se = srbreak(df, lookback=lookback, vol_len=vol_len); ev = le if side > 0 else se
    fa = filt_arrays(df, side); mask = np.ones(len(df), bool)
    for f in fs:
        mask &= fa[f]
    return run_f(df, side, "atrstop", None, np.asarray(ev) & mask, (up, dn), "1h", ft, fr), df, (up, dn), ft, fr


def inc_daily(df, flips, ft, fr, fn, side, fs):
    le, se = fn(df); ev = le if side > 0 else se
    fa = filt_arrays(df, side); mask = np.ones(len(df), bool)
    for f in fs:
        mask &= fa[f]
    return run_f(df, side, "atrstop", None, np.asarray(ev) & mask, flips, "1h", ft, fr)


def main():
    R = roster_pnl_daily()
    print(f"{'='*100}\nBATCH 7a — SRB: sensibilidad(lookback 15/20/25 + vol_len 2/3) + corr roster + corr par")
    print(f"{'cand':12}{'n':>5}{'exp':>6}{'PF':>6}{'IS':>7}{'OOS':>7}{'sens_min':>9}{'corr_R':>8}{'corr_par':>9}  veredicto")
    print(f"{'-'*100}")
    for coin, side, fs, inc in CANDS:
        tr, df, flips, ft, fr = srb_daily(coin, side, fs); mi, mo = split_met(tr); m = met(tr)
        sens = []
        for lb in (15, 20, 25):
            t, *_ = srb_daily(coin, side, fs, lookback=lb); mm = met(t); sens.append(mm["exp"] if mm else -999)
        for vl in (2, 3):
            t, *_ = srb_daily(coin, side, fs, vol_len=vl); mm = met(t); sens.append(mm["exp"] if mm else -999)
        d = tr.set_index("t_in")["ret"].resample("1D").sum()
        cr = pd.concat([d, R.rename("R")], axis=1).fillna(0).corr().iloc[0, 1]
        cp = np.nan
        if inc:
            fn, isd, ifs = inc
            itr = inc_daily(df, flips, ft, fr, INCFN[fn], isd, ifs)
            if itr is not None:
                di = itr.set_index("t_in")["ret"].resample("1D").sum()
                cp = pd.concat([d, di], axis=1).fillna(0).corr().iloc[0, 1]
        smin = min(sens); tag = f"{coin}-SRB-{'L' if side>0 else 'S'}"
        robust = smin > 0 and mi["exp"] > 0 and mo["exp"] > 0
        red = (not np.isnan(cp)) and cp > 0.5
        ver = ("ROBUSTO" if robust else "frágil") + (" REDUNDANTE" if red else (" ok-par" if not np.isnan(cp) else " par-nuevo")) + (" lowcorrR" if abs(cr) < 0.25 else "")
        print(f"{tag:12}{m['n']:5}{m['exp']:6.0f}{m['pf']:6.2f}{mi['exp']:7.0f}{mo['exp']:7.0f}"
              f"{smin:9.0f}{cr:8.2f}{(f'{cp:.2f}' if not np.isnan(cp) else '   —'):>9}  {ver}")
    print("\nKVO: descartado (oscilador de volumen, redundante con momentum — varios IS débiles/OOS decayente).")


if __name__ == "__main__":
    main()

"""Validación batch 6 (Zero Lag): sensibilidad a length/mult + corr vs roster + corr mutua.
Foco en monedas nuevas y balance IS/OOS. Uso: python valida_batch6.py"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_batch6.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # zl_flip, zl_entry, run_f, met, filt_arrays, load_fund, DATA, I, FILTER_SETS, split_met, roster_pnl_daily

SIGFN = {"ZLflip": zl_flip, "ZLentry": zl_entry}
# candidatos priorizados: monedas NUEVAS (no en roster) + balance IS/OOS, sobre todo longs
CANDS = [
    ("CRV",  "ZLentry", +1, ["trend", "vol"]),    # nueva, long, 5/5
    ("LDO",  "ZLflip",  +1, ["sweep6"]),          # nueva, long, balanceada
    ("ATOM", "ZLflip",  +1, ["sweep6"]),          # nueva, long, balanceada
    ("FIL",  "ZLentry", +1, ["sweep6"]),          # nueva, long, IS121/OOS298
    ("NEO",  "ZLentry", -1, ["sweep6", "trend"]), # short (NEO-L ya es S40 -> ver corr)
    ("STX",  "ZLentry", -1, ["sweep6"]),          # nueva, short, balanceada
    ("CRV",  "ZLentry", -1, ["sweep6", "trend"]), # nueva, short (ver corr con CRV-L)
]


def daily(coin, sig, side, fs, length=70, mult=1.2):
    df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    ft, fr = load_fund(coin); up, dn, _ = I.st_flips(df)
    le, se = SIGFN[sig](df, length, mult); ev = le if side > 0 else se
    fa = filt_arrays(df, side); mask = np.ones(len(df), bool)
    for f in fs:
        mask &= fa[f]
    return run_f(df, side, "atrstop", None, np.asarray(ev) & mask, (up, dn), "1h", ft, fr)


def main():
    R = roster_pnl_daily(); series = {}; rows = []
    for coin, sig, side, fs in CANDS:
        tr = daily(coin, sig, side, fs); mi, mo = split_met(tr); m = met(tr)
        # sensibilidad a length y mult
        sens = []
        for L in (50, 70, 90):
            t = daily(coin, sig, side, fs, length=L); mm = met(t); sens.append(mm["exp"] if mm else -999)
        for mu in (1.0, 1.2, 1.5):
            t = daily(coin, sig, side, fs, mult=mu); mm = met(t); sens.append(mm["exp"] if mm else -999)
        d = tr.set_index("t_in")["ret"].resample("1D").sum()
        nm = f"{coin}-{sig[2:]}-{'L' if side>0 else 'S'}"; d.name = nm; series[nm] = d
        al = pd.concat([d, R.rename("R")], axis=1).fillna(0)
        rows.append((nm, m, mi, mo, min(sens), al.iloc[:, 0].corr(al["R"])))
    print(f"{'='*96}")
    print(f"BATCH 6 — Zero Lag · sensibilidad(length 50/70/90 + mult 1.0/1.2/1.5) + corr roster")
    print(f"{'cand':16}{'n':>5}{'exp':>6}{'PF':>6}{'IS':>7}{'OOS':>7}{'sens_min':>9}{'corr_R':>8}  veredicto")
    print(f"{'-'*96}")
    for nm, m, mi, mo, smin, cr in rows:
        ver = "ROBUSTO" if (smin > 0 and mi["exp"] > 0 and mo["exp"] > 0) else "frágil(sens)" if smin <= 0 else "ok"
        ver += " lowcorr" if abs(cr) < 0.25 else ""
        print(f"{nm:16}{m['n']:5}{m['exp']:6.0f}{m['pf']:6.2f}{mi['exp']:7.0f}{mo['exp']:7.0f}"
              f"{smin:9.0f}{cr:8.2f}  {ver}")
    M = pd.concat(series.values(), axis=1).fillna(0)
    print(f"\nCORR MUTUA:\n{M.corr().round(2).to_string()}")
    ev = np.linalg.eigvalsh(M.corr().values); pr = (ev.sum()**2)/(ev**2).sum()
    print(f"\nnº efectivo de apuestas: {pr:.1f}/{len(series)}")


if __name__ == "__main__":
    main()

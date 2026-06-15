"""Validacion batch 4: ¿el edge de volumen es NUEVO o redundante con los shorts del roster?
Para cada candidato robusto (IS>0 y OOS>0): sensibilidad + corr directa vs la(s) estrategia(s)
del mismo par ya en el roster. Uso: python valida_batch4.py"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_batch4.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # obv_sig, cmf_sig, fi_sig, stc_sig, run_f, met, filt_arrays, load_fund, DATA, I, split_met

SIGFN = {"OBV": obv_sig, "CMF": cmf_sig, "FI": fi_sig, "STC": stc_sig}


def daily_for(df, ev, side, fs, ft, fr):
    up, dn, _ = I.st_flips(df); fa = filt_arrays(df, side)
    mask = np.ones(len(df), bool)
    for f in fs:
        mask &= fa[f]
    return run_f(df, side, "atrstop", None, np.asarray(ev) & mask, (up, dn), "1h", ft, fr)


def roster_event(df, kind, side):
    """Evento de una estrategia existente del roster, para comparar correlacion."""
    if kind == "VTX":
        l, s = I.vortex(df)
    elif kind == "ADX":
        l, s = I.adx_dmi(df)
    elif kind == "SQZ":
        l, s = I.squeeze_momentum(df)
    elif kind == "BXREG":
        _, rs, _, regdn = I.bx_parts(df["close"]); s = np.asarray(rs) & np.asarray(regdn); l = s
    return l if side > 0 else s


# candidato (coin, sig, side, fs) + comparadores roster [(kind, fs)] del MISMO par
CANDS = [
    ("ORDI", "CMF", +1, ["trend", "vol"],     []),                                   # NUEVA (long)
    ("ORDI", "FI",  +1, ["regime"],           []),                                   # NUEVA (long)
    ("RUNE", "FI",  -1, ["sweep6", "trend"],   [("VTX", ["sweep6", "trend"])]),       # vs S27
    ("ARB",  "FI",  -1, ["sweep6", "trend"],   [("VTX", ["sweep6", "trend"]), ("ADX", ["trend", "vol"])]),  # vs S26,S31
    ("SEI",  "STC", -1, ["sweep6", "trend"],   [("VTX", ["sweep6", "trend"])]),       # vs S25
    ("SEI",  "FI",  -1, ["sweep6", "trend"],   [("VTX", ["sweep6", "trend"])]),       # vs S25
    ("EGLD", "FI",  -1, ["sweep6"],            [("SQZ", ["sweep6"]), ("BXREG", ["sweep6"])]),  # vs S32,S18
]


def main():
    print(f"{'='*104}")
    print(f"BATCH 4 — ¿edge de volumen NUEVO o redundante? sensibilidad + corr vs short(s) del par")
    print(f"{'cand':14}{'IS_exp':>7}{'OOS_exp':>8}{'sens':>16}{'corr_max_roster':>18}  veredicto")
    print(f"{'-'*104}")
    keep = []
    for coin, sig, side, fs, comps in CANDS:
        df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        ft, fr = load_fund(coin)
        le, se = SIGFN[sig](df); ev = le if side > 0 else se
        tr = daily_for(df, ev, side, fs, ft, fr)
        mi, mo = split_met(tr)
        # sensibilidad: para FI varia n(8,13,21); CMF n(14,20,28); STC sin params clave -> fija; OBV fija
        sens = [mo["exp"]]
        if sig == "FI":
            sens = [met(daily_for(df, (fi_sig(df, n=nn)[0] if side > 0 else fi_sig(df, n=nn)[1]), side, fs, ft, fr))["exp"]
                    for nn in (8, 13, 21)]
        elif sig == "CMF":
            sens = [met(daily_for(df, (cmf_sig(df, n=nn)[0] if side > 0 else cmf_sig(df, n=nn)[1]), side, fs, ft, fr))["exp"]
                    for nn in (14, 20, 28)]
        sens_ok = min(sens) > 0
        # corr vs comparadores del roster (mismo par)
        a = tr.set_index("t_in")["ret"].resample("1D").sum()
        cmax = np.nan
        for kind, cfs in comps:
            ce = roster_event(df, kind, -1)
            ctr = daily_for(df, ce, -1, cfs, ft, fr)
            if ctr is not None:
                b = ctr.set_index("t_in")["ret"].resample("1D").sum()
                al = pd.concat([a, b], axis=1).fillna(0)
                c = al.iloc[:, 0].corr(al.iloc[:, 1])
                cmax = c if np.isnan(cmax) else max(cmax, c)
        tag = f"{coin}-{sig}-{'L' if side>0 else 'S'}"
        cs = "NUEVA" if np.isnan(cmax) else f"{cmax:.2f}"
        stable = mi["exp"] > 0 and mo["exp"] > 0 and sens_ok
        red = (not np.isnan(cmax)) and cmax > 0.5
        ver = ("ESTABLE" if stable else "INESTABLE(IS/sens)") + (" REDUNDANTE" if red else (" ortogonal" if not np.isnan(cmax) else " par-nuevo"))
        if stable and not red:
            keep.append(tag)
        print(f"{tag:14}{mi['exp']:7.0f}{mo['exp']:8.0f}  [{min(sens):4.0f},{max(sens):4.0f}]{'':4}{cs:>18}  {ver}")
    print(f"\nPromovibles (estables + no redundantes): {keep if keep else 'NINGUNO'}")
    print("corr>0.5 vs un short del par = el volumen re-detecta el mismo down-move (no diversifica).")


if __name__ == "__main__":
    main()

"""Validacion OOS de los supervivientes de poc_indicadores_nuevos.py (batch SQZ/VTX).

El sweep eligio el MEJOR filtro entre 7x2x2 combos -> riesgo de sobreajuste por
multiple-comparison. Aqui el gate honesto (mismo que valido S10-S21):
  - split IS (<2025) / OOS (>=2025). Debe ganar en AMBOS, no solo full-period.
  - PROMOVIBLE si: OOS exp>0, OOS n>=12, OOS PF>=1.2 e IS exp>0.
  - sensibilidad: perturbar el knob clave (longitud) +/-; el edge no debe vivir solo en 1 valor.

Uso: python valida_indicadores_nuevos.py
"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_indicadores_nuevos.py", encoding="utf-8").read()
exec(src.split("def main(")[0])   # I, DATA, run_f, met, squeeze_momentum, vortex, filt_arrays, load_fund, SIGNALS...

# candidatos = supervivientes top del sweep: (coin, signal, side, filtros)
CANDS = [
    ("ENA",  "SQZ", +1, ["regime"]),
    ("WIF",  "SQZ", +1, ["regime"]),
    ("WIF",  "VTX", -1, ["sweep6"]),
    ("SAND", "VTX", -1, ["regime"]),
    ("XLM",  "SQZ", +1, ["vol"]),
    ("EGLD", "VTX", -1, ["sweep6", "trend"]),
    ("AVAX", "VTX", -1, ["sweep6"]),
    ("RUNE", "VTX", -1, ["sweep6", "trend"]),
    ("SEI",  "VTX", -1, ["sweep6", "trend"]),
    ("ARB",  "VTX", -1, ["sweep6", "trend"]),
    ("FET",  "SQZ", +1, ["trend", "vol"]),
    ("TAO",  "SQZ", +1, ["trend", "vol"]),
    ("AVAX", "SQZ", +1, ["trend"]),
    ("XRP",  "SQZ", +1, ["trend"]),
    ("BNB",  "SQZ", +1, ["trend", "vol"]),
]
FN = {"SQZ": squeeze_momentum, "VTX": vortex}


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return None, None
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def evt_for(coin, df, sname, side, length=None):
    if length is None:
        le, se = FN[sname](df)
    elif sname == "SQZ":
        le, se = squeeze_momentum(df, bb_len=length, kc_len=length)
    else:
        le, se = vortex(df, n=length)
    return np.asarray(le if side > 0 else se)


def build_tr(coin, df, ft, fr, flips, sname, side, fs, length=None):
    evt = evt_for(coin, df, sname, side, length)
    fa = filt_arrays(df, side)
    mask = np.ones(len(df), bool)
    for f in fs:
        mask &= fa[f]
    return run_f(df, side, "atrstop", None, evt & mask, flips, "1h", ft, fr)


def main():
    print(f"{'='*104}")
    print(f"VALIDACION OOS  ·  IS<2025 / OOS>=2025  ·  PROMOVIBLE: OOS exp>0, n>=12, PF>=1.2 e IS exp>0")
    print(f"{'cand':16}{'filtros':18}{'IS_n':>5}{'IS_exp':>7}{'IS_PF':>6}  {'OOS_n':>5}{'OOS_exp':>8}{'OOS_PF':>7}  {'sens(len)':>20}  veredicto")
    print(f"{'-'*104}")
    promovibles = []
    for coin, sname, side, fs in CANDS:
        df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        ft, fr = load_fund(coin)
        up, dn, _ = I.st_flips(df); flips = (up, dn)
        tr = build_tr(coin, df, ft, fr, flips, sname, side, fs)
        mi, mo = split_met(tr)
        if mi is None or mo is None:
            continue
        # sensibilidad: longitud base 20(SQZ)/14(VTX) +/-
        base_len = 20 if sname == "SQZ" else 14
        sens = []
        for L in ([14, 20, 26] if sname == "SQZ" else [10, 14, 18]):
            trs = build_tr(coin, df, ft, fr, flips, sname, side, fs, length=L)
            ms = met(trs)
            sens.append(ms["exp"] if ms else -999)
        sens_ok = min(sens) > 0
        prom = (mo["exp"] > 0 and mo["n"] >= 12 and mo["pf"] >= 1.2 and mi["exp"] > 0)
        ver = "PROMOVIBLE" + (" (robusto sens)" if sens_ok else " (sens fragil)") if prom else \
              "falla OOS" if mo["exp"] <= 0 else "OOS chico/PF bajo"
        if prom:
            promovibles.append((coin, sname, side, fs, mi, mo, sens_ok))
        tag = f"{coin}-{sname}-{'L' if side>0 else 'S'}"
        print(f"{tag:16}{('+'.join(fs)):18}{mi['n']:5}{mi['exp']:7.0f}{mi['pf']:6.2f}  "
              f"{mo['n']:5}{mo['exp']:8.0f}{mo['pf']:7.2f}  [{min(sens):4.0f},{max(sens):4.0f}]{'':9}  {ver}")
    print(f"\n{len(promovibles)} PROMOVIBLES (de {len(CANDS)}). "
          f"Robustos a sensibilidad: {sum(1 for p in promovibles if p[6])}")


if __name__ == "__main__":
    main()

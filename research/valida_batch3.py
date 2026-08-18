"""Validacion de los top de batch 3: sensibilidad de params + correlacion DIRECTA con el
short del mismo par que ya esta en el roster (redundancia). Uso: python valida_batch3.py"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_batch3.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # fisher, kama, adx_dmi, vortex, squeeze_momentum, run_f, met, filt_arrays, load_fund, DATA, I, split_met

# candidato -> (coin, kind, side, filtros) + short existente del mismo par para corr directa
CANDS = [
    ("AVAX", "ADX", -1, ["sweep6"],          ("VTX", ["sweep6"])),          # vs S28
    ("ARB",  "ADX", -1, ["trend", "vol"],    ("VTX", ["sweep6", "trend"])), # vs S26
    ("BCH",  "ADX", -1, ["sweep6"],          None),                          # NUEVA
    ("HBAR", "ADX", -1, ["sweep6"],          None),                          # NUEVA
    ("DOT",  "ADX", -1, ["sweep6"],          ("BXDON", None)),               # vs S10
    ("EGLD", "SQZS", -1, ["sweep6"],         ("BXREG", None)),               # vs S18
    ("FLOW", "SQZS", -1, ["sweep6"],         None),                          # short nuevo (FLOW solo era long)
    ("SEI",  "KAMA", -1, ["sweep6", "trend"], ("VTX", ["sweep6", "trend"])), # vs S25
]


def event(df, kind, side, **kw):
    if kind == "ADX":
        l, s = adx_dmi(df, n=kw.get("n", 14), thr=kw.get("thr", 25))
    elif kind == "KAMA":
        l, s = kama(df, n=kw.get("n", 10))
    elif kind == "SQZS":
        l, s = squeeze_momentum(df)
    elif kind == "VTX":
        l, s = vortex(df)
    elif kind == "BXDON":          # S10: B-X rojo + Donchian=-1
        _, rs, _, _ = I.bx_parts(df["close"]); don = I.dch_trend(df["close"], df["high"], df["low"], 20)
        s = np.asarray(rs) & (don == -1); l = np.zeros(len(s), bool)
    elif kind == "BXREG":          # S18: B-X rojo + regimen<0
        _, rs, _, regdn = I.bx_parts(df["close"]); s = np.asarray(rs) & np.asarray(regdn); l = np.zeros(len(s), bool)
    return l if side > 0 else s


def daily(df, ev, side, fs, ft, fr):
    up, dn, _ = I.st_flips(df); fa = filt_arrays(df, side)
    mask = np.ones(len(df), bool)
    for f in fs:
        mask &= fa[f]
    tr = run_f(df, side, "atrstop", None, np.asarray(ev) & mask, (up, dn), "1h", ft, fr)
    return tr


def main():
    print(f"{'='*100}")
    print(f"BATCH 3 — sensibilidad + corr directa vs short del mismo par en roster")
    print(f"{'cand':14}{'OOS_exp':>8}{'sens(param)':>22}{'corr_par':>10}  veredicto")
    print(f"{'-'*100}")
    for coin, kind, side, fs, exist in CANDS:
        df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        ft, fr = load_fund(coin)
        tr = daily(df, event(df, kind, side), side, fs, ft, fr)
        _, mo = split_met(tr)
        # sensibilidad
        sens = []
        if kind == "ADX":
            for thr in (20, 25, 30):
                for nn in (10, 14, 18):
                    t = daily(df, event(df, kind, side, thr=thr, n=nn), side, fs, ft, fr)
                    m = met(t); sens.append(m["exp"] if m else -999)
        elif kind == "KAMA":
            for nn in (7, 10, 14):
                t = daily(df, event(df, kind, side, n=nn), side, fs, ft, fr)
                m = met(t); sens.append(m["exp"] if m else -999)
        else:
            sens = [mo["exp"]]  # SQZ sin params
        sens_ok = min(sens) > 0
        # corr directa con el short existente del mismo par
        corr = np.nan
        if exist:
            ek, efs = exist
            te = daily(df, event(df, ek, -1), -1, efs if efs else [], ft, fr)
            if tr is not None and te is not None:
                a = tr.set_index("t_in")["ret"].resample("1D").sum()
                b = te.set_index("t_in")["ret"].resample("1D").sum()
                al = pd.concat([a, b], axis=1).fillna(0)
                corr = al.iloc[:, 0].corr(al.iloc[:, 1])
        tag = f"{coin}-{kind}-S"
        cs = f"{corr:.2f}" if not np.isnan(corr) else "NUEVA"
        red = "" if np.isnan(corr) else (" REDUNDANTE" if corr > 0.5 else " ok-distinta")
        ver = ("ROBUSTO" if sens_ok else "FRAGIL") + (red if exist else " (par nuevo)")
        print(f"{tag:14}{mo['exp']:8.0f}  [{min(sens):5.0f},{max(sens):5.0f}]{'':6}{cs:>10}  {ver}")
    print("\nNota: corr>0.5 con el short existente del par = redundante (no sumar). NUEVA = par sin short en roster.")


if __name__ == "__main__":
    main()

"""Validación OOS de los 7 setups nuevos (DOT/DOGE/ADA) antes de sumarlos al roster.

Mismo rigor que validar_combos: funding real + split train(2023-24)/test(2025-26) +
sensibilidad a los parámetros del filtro. Decide cuáles son de fiar (suplentes) y cuáles
descartar (sobreajuste / fallan fuera de muestra).

Uso: python validar_nuevos.py
"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\expandir_universo.py", encoding="utf-8").read()
exec(src.split("def main(")[0])   # templates, run_f, load_fund, detect_sweeps, recent, I, DATA, met, WARM


def fil_arrays(df, side, sL, sS, ema_len, volwin, sweepF):
    c = df["close"]; _, _, regup, regdn = I.bx_parts(c)
    ema = c.ewm(span=ema_len, adjust=False).mean().values
    atr = I.atr14(df).values; atrpct = atr / c.values
    volmed = pd.Series(atrpct).rolling(volwin, min_periods=100).median().values
    return {"trend": (c.values > ema) if side > 0 else (c.values < ema),
            "vol": atrpct >= volmed, "sweep": recent(sL if side > 0 else sS, sweepF),
            "regime": (np.asarray(regup) if side > 0 else np.asarray(regdn))}


def build_run(coin, tname, filters, ema_len=200, W_=5, MAXAGE_=200, volwin=500, sweepF=6):
    df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    global W, MAXAGE
    W, MAXAGE = W_, MAXAGE_
    sL, sS = detect_sweeps(df)
    T, flips = templates(coin, df); ft, fr = load_fund(coin)
    side, em, sa, entry = T[tname]
    fa = fil_arrays(df, side, sL, sS, ema_len, volwin, sweepF)
    mask = np.ones(len(df), bool)
    for f in filters:
        mask &= fa[f]
    base = run_f(df, side, em, sa, entry, flips, "1h", ft, fr)
    filt = run_f(df, side, em, sa, entry & mask, flips, "1h", ft, fr)
    return base, filt


def met2(tr):
    if tr is None or len(tr) == 0:
        return dict(n=0, wr=0, exp=0, pf=0, ypos=0, ytot=0)
    return met(tr)


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return met2(None), met2(None)
    cut = pd.Timestamp(cut)
    return met2(tr[tr["t_in"] < cut]), met2(tr[tr["t_in"] >= cut])


SETUPS = [
    ("DOT", "RIB-L", ["trend", "vol"]),
    ("DOGE", "BX-S", ["sweep"]),
    ("DOT", "BXdon-S", ["sweep"]),
    ("DOGE", "RIB-L", ["trend", "vol"]),
    ("ADA", "BX-S", ["trend", "vol"]),
    ("ADA", "BXdon-S", ["sweep"]),
    ("DOT", "STdon-S", ["trend"]),
]


def main():
    verdicts = []
    for coin, tname, filters in SETUPS:
        base, filt = build_run(coin, tname, filters)
        ff = met2(filt)
        f_tr, f_te = split_met(filt)
        print(f"\n{'='*86}\n{coin} {tname}  filtros={'+'.join(filters)}  (funding real)")
        print(f"  full:  n={ff['n']:4} WR={ff['wr']:3.0f}% exp={ff['exp']:6.0f} PF={ff['pf']:.2f} años+={ff['ypos']}/{ff['ytot']}")
        print(f"  TRAIN 23-24: n={f_tr['n']:3} exp={f_tr['exp']:6.0f} PF={f_tr['pf']:.2f}   "
              f"TEST 25-26: n={f_te['n']:3} exp={f_te['exp']:6.0f} PF={f_te['pf']:.2f}")
        # sensibilidad
        ex = []
        if "trend" in filters:
            for el in (150, 200, 250):
                _, fl = build_run(coin, tname, filters, ema_len=el); ex.append(met2(fl)["exp"])
        if "sweep" in filters:
            for F in (3, 6, 9, 12):
                _, fl = build_run(coin, tname, filters, sweepF=F); ex.append(met2(fl)["exp"])
            for mg in (150, 250):
                _, fl = build_run(coin, tname, filters, MAXAGE_=mg); ex.append(met2(fl)["exp"])
        if "vol" in filters:
            for vw in (300, 800):
                _, fl = build_run(coin, tname, filters, volwin=vw); ex.append(met2(fl)["exp"])
        sens_ok = len(ex) > 0 and min(ex) > 0
        # veredicto OOS
        oos = (f_tr["exp"] > 0 and f_te["exp"] > 0 and f_te["n"] >= 8)
        oos_part = (f_te["exp"] > 0 and f_te["n"] >= 8)
        v = ("APROBADO" if (oos and sens_ok) else
             "DUDOSO" if (oos_part or oos) else "DESCARTADO")
        why = []
        if not oos:
            why.append("test<=0" if f_te["exp"] <= 0 else "train<=0")
        if not sens_ok:
            why.append(f"frágil (exp min {min(ex):.0f})" if ex else "sin sens")
        print(f"  sensibilidad exp: [{min(ex):.0f}, {max(ex):.0f}]" if ex else "  (sin knobs)")
        print(f"  >> VEREDICTO: {v}" + (f"  ({', '.join(why)})" if why else ""))
        verdicts.append((coin, tname, "+".join(filters), v, ff, f_te))

    print(f"\n{'='*86}\nRESUMEN")
    for coin, tname, fil, v, ff, f_te in verdicts:
        print(f"  {coin:5}{tname:11}{fil:14} {v:11} full_exp={ff['exp']:5.0f} PF={ff['pf']:.2f} "
              f"test_exp={f_te['exp']:5.0f}")
    apr = [x for x in verdicts if x[3] == "APROBADO"]
    print(f"\n  APROBADOS (de fiar como suplentes): {len(apr)}/7 -> "
          f"{', '.join(f'{c} {t}' for c, t, *_ in apr)}")


if __name__ == "__main__":
    main()

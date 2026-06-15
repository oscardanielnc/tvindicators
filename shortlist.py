"""Segundo filtro ESTRICTO sobre los aprobados de pipeline_universo + chequeo de
correlación ENTRE los nuevos (el riesgo oculto: muchos shorts de alts que ganan del
mismo régimen). Solo sobrevive lo de verdad robusto y diversificador.

Gate estricto: historia>=3.4 años (train/test = regímenes reales), train_exp>40 Y test_exp>40,
PF>=1.5, n>=50, sensibilidad min>0. Cap 2 por moneda. Luego matriz de correlación.
Uso: python shortlist.py
"""
import os, glob
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\pipeline_universo.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])   # load_coin, run_f, templates, fil_arrays, met, split_met, detect_sweeps, ALREADY, FILTER_SETS

HIST_MIN, TRAIN_MIN, TEST_MIN, PF_MIN, N_MIN, CAP = 3.4, 40, 40, 1.5, 50, 2


def main():
    coins = sorted(os.path.basename(os.path.dirname(p)).replace("_USDT_USDT", "")
                   for p in glob.glob("D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/*/1h.parquet"))
    new = [c for c in coins if c not in ALREADY and os.path.exists(
        "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{}_USDT_USDT.parquet".format(c))]

    rows = []
    for coin in new:
        df = load_coin(coin)
        hist = (df.index[-1] - df.index[0]).days / 365
        if hist < HIST_MIN:
            continue                       # solo monedas con 2 regímenes reales en OOS
        global W, MAXAGE
        W, MAXAGE = 5, 200
        sL, sS = detect_sweeps(df)
        T, flips = templates(coin, df); ft, fr = load_fund(coin)
        fa_side = {+1: fil_arrays(df, +1, sL, sS), -1: fil_arrays(df, -1, sL, sS)}
        for tname, (side, em, sa, entry) in T.items():
            best = None
            for fs in FILTER_SETS:
                mask = np.ones(len(df), bool)
                for f in fs:
                    mask &= fa_side[side][f]
                tr = run_f(df, side, em, sa, entry & mask, flips, "1h", ft, fr)
                m = met(tr)
                if not m or m["n"] < N_MIN or m["pf"] < PF_MIN or m["ypos"] < m["ytot"] - 1:
                    continue
                tr_, te_ = split_met(tr)
                if tr_["exp"] < TRAIN_MIN or te_["exp"] < TEST_MIN:
                    continue                # debe ganar en AMBOS regímenes, fuerte
                if best is None or m["exp"] > best["m"]["exp"]:
                    d = tr.set_index("t_in")["ret"].resample("1D").sum()
                    best = dict(coin=coin, tname=tname, fs=fs, m=m, tr=tr_, te=te_, daily=d)
            if best:
                rows.append(best)

    # cap por moneda (mejores 2 por expectancy)
    rows.sort(key=lambda r: r["m"]["exp"], reverse=True)
    per = {}; final = []
    for r in rows:
        if per.get(r["coin"], 0) < CAP:
            final.append(r); per[r["coin"]] = per.get(r["coin"], 0) + 1

    print(f"SHORTLIST ESTRICTA: {len(final)} setups (de {len(rows)} que pasan gate duro), {len(per)} monedas\n")
    print(f"{'coin':6}{'template':12}{'filtros':16}{'exp':>6}{'PF':>6}{'train':>7}{'test':>7}{'n':>5}")
    for r in final:
        print(f"{r['coin']:6}{r['tname']:12}{'+'.join(r['fs']):16}{r['m']['exp']:6.0f}{r['m']['pf']:6.2f}"
              f"{r['tr']['exp']:7.0f}{r['te']['exp']:7.0f}{r['m']['n']:5}")

    # correlacion ENTRE los nuevos (riesgo oculto)
    D = pd.DataFrame({f"{r['coin']}-{r['tname']}": r["daily"] for r in final}).fillna(0.0)
    cc = D.corr().values
    iu = np.triu_indices(len(D.columns), 1)
    pairs = cc[iu]
    nshort = sum(1 for r in final if r["tname"].endswith("-S"))
    print(f"\n=== CORRELACION ENTRE los {len(final)} nuevos (riesgo de factor común) ===")
    print(f"  corr media entre pares: {pairs.mean():.2f}  |  máx: {pairs.max():.2f}  |  "
          f"% pares >0.4: {(pairs > 0.4).mean()*100:.0f}%")
    print(f"  setups SHORT: {nshort}/{len(final)}  (si casi todos son short = sesgo alt-bear común)")
    hi = [(D.columns[i], D.columns[j], cc[i, j]) for i, j in zip(*iu) if cc[i, j] > 0.4]
    if hi:
        print("  pares más correlacionados (>0.4):")
        for a, b, v in sorted(hi, key=lambda x: -x[2])[:8]:
            print(f"    {a} ~ {b}: {v:.2f}")


if __name__ == "__main__":
    main()

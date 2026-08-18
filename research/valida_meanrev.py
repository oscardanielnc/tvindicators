"""Chequeo de robustez de los supervivientes de reversion (batch 2) mas solidos.
Sensibilidad al umbral/exit + correlacion vs roster (proxy). Uso: python valida_meanrev.py"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_meanrev.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])   # run_mr, signals, target, met, split_met, load_fund, DATA, I, roster_pnl_daily

# top robustos (IS≈OOS, PF>1.4 ambos, años+): (coin, sig, side, thr, trend, exit, stop)
TOP = [
    ("ARB",  "CRSI", -1, 5, 100, 5,  3.0),
    ("OP",   "CRSI", -1, 5, 100, 5,  3.0),
    ("XLM",  "CRSI", +1, 5, 200, 10, 3.0),
    ("EGLD", "CRSI", +1, 5, 200, 10, 3.0),
    ("INJ",  "BB%b", +1, 0, 200, 20, 3.0),
]


def build(coin, sig, side, thr, tl, el, sa):
    df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    ft, fr = load_fund(coin)
    ev = signals(df, sig, side, thr, tl); tgt = target(df, el)
    return run_mr(df, side, ev, tgt, sa, TO_H, ft, fr)


def main():
    R = roster_pnl_daily()
    print(f"{'='*100}")
    print(f"ROBUSTEZ REVERSION  ·  sensibilidad(exp al perturbar) + corr vs roster(proxy S1-S9)")
    print(f"{'cand':16}{'base_exp':>9}{'OOS_exp':>9}{'sens_thr':>20}{'sens_exit':>20}{'corr':>7}  veredicto")
    print(f"{'-'*100}")
    for coin, sig, side, thr, tl, el, sa in TOP:
        tr = build(coin, sig, side, thr, tl, el, sa)
        m = met(tr); _, mo = split_met(tr)
        d = tr.set_index("t_in")["ret"].resample("1D").sum()
        al = pd.concat([d.rename("x"), R.rename("R")], axis=1).fillna(0)
        corr = al["x"].corr(al["R"])
        # sensibilidad umbral (CRSI: thr; BB%b: no aplica -> varia trend_len)
        if sig == "CRSI":
            sens_t = [met(build(coin, sig, side, t, tl, el, sa)) for t in (3, 5, 8, 12)]
        else:
            sens_t = [met(build(coin, sig, side, thr, t, el, sa)) for t in (100, 150, 200)]
        sens_x = [met(build(coin, sig, side, thr, tl, e, sa)) for e in (5, 10, 20)]
        et = [x["exp"] if x else -999 for x in sens_t]
        ex = [x["exp"] if x else -999 for x in sens_x]
        robust = min(et) > 0 and min(ex) > 0
        tag = f"{coin}-{sig}-{'L' if side>0 else 'S'}"
        ver = ("ROBUSTO" if robust else "FRAGIL") + (" lowcorr" if abs(corr) < 0.2 else "")
        print(f"{tag:16}{m['exp']:9.0f}{mo['exp']:9.0f}  [{min(et):4.0f},{max(et):4.0f}]"
              f"{'':6}[{min(ex):4.0f},{max(ex):4.0f}]{'':6}{corr:7.2f}  {ver}")
    print(f"\nNota: exp en bps/trade. Reversion = alta frecuencia, edge fino (contrastar con SQZ/VTX 55-248 bps).")


if __name__ == "__main__":
    main()

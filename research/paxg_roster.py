"""Aplica la LÓGICA de cada estrategia del roster (S1-S56) a PAXG (oro) y mide su edge.
Reusa el motor real: entry_array_for (reconcile) reconstruye la señal de cada estrategia sobre
cualquier df; run_f (poc_indicadores_nuevos) simula con costos+funding reales (paridad engine.py).

OJO honesto: PAXG son ~15 meses (2025-03..2026-06) en UN solo instrumento, y se prueban 56 setups
-> multiple testing severo + sin holdout 2024. Esto es EXPLORATORIO: dice si los MECANISMOS del
roster se comportan coherentes en oro, NO valida una estrategia. Cualquier 'ganador' aquí es
candidato a sospecha de ruido hasta validarlo aparte. Uso: python paxg_roster.py
"""
import sys
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import reconcile as R                     # trae entry_array_for, run_f, met, load_fund, I, tm_red_exit, ...
from tvbot import strategies as STRAT

COIN = "PAXG"
STORE = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/{tf}.parquet"


def load(tf):
    df = pd.read_parquet(STORE.format(c=COIN, tf=tf))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("dt").sort_index()


def main():
    dfs = {tf: load(tf) for tf in ("15m", "1h")}
    ft, fr = R.load_fund(COIN)
    rng = (dfs["1h"].index.min().date(), dfs["1h"].index.max().date())
    bh = dfs["1h"]["close"].iloc[-1] / dfs["1h"]["open"].iloc[0] - 1
    print(f"PAXG {rng[0]}..{rng[1]} · buy&hold {bh*100:+.0f}% · {len(dfs['1h'])} velas 1h\n")

    rows = []
    skipped = []
    for s in STRAT.STRATEGIES:
        if s.exit_mode == "meanrev":
            skipped.append(s.sid); continue          # run_f no simula meanrev (S30)
        df = dfs.get(s.tf)
        if df is None:
            skipped.append(s.sid); continue
        try:
            ent = np.asarray(R.entry_array_for(s.sid, df))
            up, dn, _ = R.I.st_flips(df)
            flips = (up, R.tm_red_exit(df)) if s.sid in ("S2", "S14") else (up, dn)
            tr = R.run_f(df, s.side, s.exit_mode, s.safety_atr, ent, flips, s.tf, ft, fr)
            m = R.met(tr)
        except Exception as e:
            print(f"  (skip {s.sid}: {str(e)[:70]})"); skipped.append(s.sid); continue
        if m is None:
            rows.append((s.sid, s.coin, s.side, s.tf, 0, None, None, None, None)); continue
        rows.append((s.sid, s.coin, s.side, s.tf, m["n"], m["wr"], m["exp"], m["pf"],
                     f"{m['ypos']}/{m['ytot']}"))

    df_res = pd.DataFrame(rows, columns=["sid", "coin0", "side", "tf", "n", "wr", "exp_bp", "pf", "yrs+"])
    traded = df_res[df_res["n"] >= 5].copy()
    print(f"Estrategias evaluadas: {len(df_res)} · con >=5 trades en PAXG: {len(traded)} · "
          f"meanrev/sin-tf saltadas: {skipped}\n")

    def block(title, sub):
        print(f"===== {title} ({len(sub)}) =====")
        sub = sub.sort_values("exp_bp", ascending=False)
        for _, r in sub.iterrows():
            tag = "★" if (r["pf"] and r["pf"] > 1.3 and r["n"] >= 15 and r["exp_bp"] > 0) else " "
            print(f" {tag} {r['sid']:4} {('L' if r['side']>0 else 'S')} {r['tf']:3} orig={r['coin0']:5} "
                  f"n={int(r['n']):4} WR={r['wr']:4.0f}% exp={r['exp_bp']:+6.0f}bp PF={r['pf']:.2f} años+={r['yrs+']}")
        print()

    block("LONGS sobre PAXG", traded[traded.side > 0])
    block("SHORTS sobre PAXG", traded[traded.side < 0])

    # resumen agregado honesto
    pos = traded[(traded.exp_bp > 0)]
    strong = traded[(traded.pf > 1.3) & (traded.n >= 15) & (traded.exp_bp > 0)]
    print("=" * 80)
    print(f"Con exp>0: {len(pos)}/{len(traded)}  ·  'fuertes' (PF>1.3, n>=15, exp>0): {len(strong)} "
          f"-> {list(strong['sid'])}")
    print(f"Esperado por AZAR con 56 setups y ~15mo: varios exp>0 saldrán por ruido. "
          f"Tratar 'fuertes' como CANDIDATOS, no validados (sin holdout). buy&hold PAXG {bh*100:+.0f}%.")
    print("=" * 80)


if __name__ == "__main__":
    main()

"""Tuneo fino + validación de los 8 nuevos antes de implementarlos (mismo trato que las 9).
Por cada (coin, template): prueba un grid amplio de filtros, elige el MEJOR ajuste por
calidad (expectancy alta, ambos regímenes positivos, PF>=1.5, n>=50), valida sensibilidad.
Si ninguno da la talla -> DROP. Sobrevivientes -> implementar.
Uso: python tune_nuevos.py
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/pipeline_universo.py"), encoding="utf-8").read()
exec(src.split("\ndef main():")[0])   # load_coin, run_f, templates, fil_arrays, met, split_met, detect_sweeps, load_fund

SETUPS = [("XLM", "TM-L"), ("RUNE", "STdonhac-L"), ("IMX", "STdonhac-L"), ("FLOW", "SThac-L"),
          ("EGLD", "BX-S"), ("FET", "BXdon-S"), ("APT", "STdon-S"), ("GRT", "BX-S")]

GRID = [["trend"], ["trend", "vol"], ["regime", "trend"], ["sweep6"], ["sweep6", "trend"],
        ["sweep6", "regime"], ["sweep6", "trend", "vol"], ["regime", "trend", "vol"]]
SWEEPFS = [3, 6, 12]


def run_combo(coin, tname, filters, ema_len=200, W_=5, MAXAGE_=200, volwin=500, sweepF=6):
    df = load_coin(coin)
    global W, MAXAGE
    W, MAXAGE = W_, MAXAGE_
    sL, sS = detect_sweeps(df)
    T, flips = templates(coin, df); ft, fr = load_fund(coin)
    side, em, sa, entry = T[tname]
    fa = fil_arrays(df, side, sL, sS, ema_len, volwin, sweepF)
    mask = np.ones(len(df), bool)
    for f in filters:
        mask &= fa[f]
    return run_f(df, side, em, sa, entry & mask, flips, "1h", ft, fr)


def main():
    survivors = []
    print(f"{'coin':6}{'template':12}{'MEJOR filtro':22}{'exp':>6}{'PF':>6}{'tr':>6}{'te':>6}{'n':>5}{'sens':>14}  veredicto")
    for coin, tname in SETUPS:
        best = None
        for filters in GRID:
            fs_list = SWEEPFS if "sweep6" in filters else [6]
            for sf in fs_list:
                tr = run_combo(coin, tname, filters, sweepF=sf)
                m = met(tr)
                if not m or m["n"] < 50 or m["pf"] < 1.5 or m["ypos"] < m["ytot"] - 1:
                    continue
                trn, tst = split_met(tr)
                if trn["exp"] < 30 or tst["exp"] < 30:        # ambos regímenes fuertes
                    continue
                key = (filters, sf, m, trn, tst)
                if best is None or m["exp"] > best[2]["exp"]:
                    best = key
        if best is None:
            print(f"{coin:6}{tname:12}{'(ningún combo)':22}{'':30}  >> DROP")
            continue
        filters, sf, m, trn, tst = best
        # sensibilidad sobre el elegido
        ex = []
        if "trend" in filters:
            for el in (150, 250): ex.append((met(run_combo(coin, tname, filters, ema_len=el, sweepF=sf)) or {"exp": -1})["exp"])
        if "sweep6" in filters:
            for F in (max(3, sf-3), sf+3): ex.append((met(run_combo(coin, tname, filters, sweepF=F)) or {"exp": -1})["exp"])
        if "vol" in filters:
            for vw in (300, 800): ex.append((met(run_combo(coin, tname, filters, volwin=vw, sweepF=sf)) or {"exp": -1})["exp"])
        sens_ok = len(ex) == 0 or min(ex) > 0
        v = "PASA" if sens_ok else "DROP (frágil)"
        tag = "+".join(f.replace("sweep6", f"sweep{sf}") for f in filters)
        srange = f"[{min(ex):.0f},{max(ex):.0f}]" if ex else "n/a"
        print(f"{coin:6}{tname:12}{tag:22}{m['exp']:6.0f}{m['pf']:6.2f}{trn['exp']:6.0f}{tst['exp']:6.0f}"
              f"{m['n']:5}{srange:>14}  >> {v}")
        if sens_ok:
            survivors.append((coin, tname, filters, sf, m))
    print(f"\nSOBREVIVIENTES a implementar: {len(survivors)}/8 -> "
          f"{', '.join(f'{c} {t} ({chr(43).join(f for f in fs)}/F{sf})' for c, t, fs, sf, _ in survivors)}")


if __name__ == "__main__":
    main()

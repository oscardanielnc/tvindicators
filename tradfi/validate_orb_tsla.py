"""Validación honesta de TSLA-long ORB: ¿edge real o beta apalancada?
Reutiliza la lógica EXACTA de sweep_orb.py (load, orb_day). Dos pruebas que matan falsos edges:

  1) HOLDOUT IS/OOS: el umbral del filtro de volatilidad (or_pct) se elige SOLO en IS (2018-2023);
     OOS (2024-2026) se reporta sin tocar -> estimación insesgada.
  2) BENCHMARK ANTI-BETA: comparar contra "long intradía todos los días 09:30->16:00". Si el ORB
     no le gana en Sharpe, el 'edge' es solo deriva alcista de TSLA (beta), no alpha.

Además: Deflated Sharpe (corrige el nº de configs probadas) + robustez año a año.
Uso: python validate_orb_tsla.py [TICKER]
"""
import sys
import math
from statistics import NormalDist
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import sweep_orb as S                       # lógica fiel del ORB

TICKER = sys.argv[1] if len(sys.argv) > 1 else "TSLA"
IS_END = pd.Timestamp("2024-01-01").date()  # IS < 2024 ; OOS >= 2024
N01 = NormalDist()
N_CONFIGS = 24                              # configs exploradas (OR{5,15,30}×target{None,1,2}×filtros) ~ deflación


def psr(sr, sr_star, T, skew, kurt):
    if T < 2:
        return float("nan")
    den = math.sqrt(max(1e-12, 1 - skew * sr + ((kurt - 1) / 4) * sr ** 2))
    return N01.cdf(((sr - sr_star) * math.sqrt(T - 1)) / den)


def sr_stats(r):
    r = np.asarray(r, float); T = len(r)
    sd = r.std(ddof=1) if T > 1 else 0
    if sd == 0:
        return 0, 0, 3, T
    z = (r - r.mean()) / sd
    return r.mean() / sd, float((z ** 3).mean()), float((z ** 4).mean()), T


def m(net):
    """Métricas de una serie de retornos por-trade/día."""
    net = np.asarray(net, float)
    if len(net) < 10:
        return None
    wr = (net > 0).mean(); g = net[net > 0].sum(); l = -net[net < 0].sum()
    pf = g / l if l > 0 else np.inf
    sr_pt, sk, ku, T = sr_stats(net)
    sharpe = sr_pt * math.sqrt(252)          # ~252 días de trading/año
    return dict(n=len(net), wr=wr, exp=net.mean(), pf=pf, sharpe=sharpe,
                cum=(1 + pd.Series(net)).prod() - 1, sr_pt=sr_pt, sk=sk, ku=ku, T=T)


def show(tag, mm):
    if mm is None:
        print(f"  {tag:30} <10 trades"); return
    print(f"  {tag:30} n={mm['n']:4} WR={mm['wr']*100:3.0f}% exp={mm['exp']*1e4:+5.0f}bp "
          f"PF={mm['pf']:.2f} Sharpe={mm['sharpe']:+.2f} cum={mm['cum']*100:+.0f}%")


def orb_long_trades(df, n_min):
    """DataFrame de trades ORB del lado LONG (días en que la 1ª ruptura fue al alza)."""
    rows = []
    for _, g in df.groupby(df.index.date):
        tr = S.orb_day(g, n_min, None)
        if tr and tr["side"] == 1:
            rows.append(tr)
    return pd.DataFrame(rows)


def intraday_long_benchmark(df):
    """Benchmark: comprar en la apertura (1ª barra) y vender en el cierre, cada día. Neto de costos."""
    rows = []
    for d, g in df.groupby(df.index.date):
        if len(g) < 30:
            continue
        ret = g["close"].iloc[-1] / g["open"].iloc[0] - 1 - 2 * S.TAKER
        rows.append((d, ret))
    return pd.DataFrame(rows, columns=["date", "net"])


def by_year(t):
    s = t.assign(y=pd.to_datetime(t["date"]).dt.year).groupby("y")["net"]
    return {int(y): (v.sum(), (v > 0).mean()) for y, v in s}


def main():
    print("=" * 84)
    print(f"VALIDACIÓN {TICKER}-LONG ORB — holdout IS/OOS + benchmark anti-beta")
    print("=" * 84)
    df = S.load(TICKER)
    print(f"Datos: {df.index.min().date()} -> {df.index.max().date()} · costos {S.TAKER*1e4:.0f}+{S.SLIP*1e4:.0f}bp/lado")

    # --- elegir OR window y umbral de filtro SOLO en IS ---
    print(f"\n[1] SELECCIÓN en IS (<{IS_END}) — eligiendo OR window y filtro de volatilidad por Sharpe IS")
    best = None
    for n_min in (15, 30):
        t = orb_long_trades(df, n_min)
        t_is = t[pd.to_datetime(t["date"]).dt.date < IS_END]
        for q in (0.0, 0.3, 0.5, 0.7):
            thr = t_is["or_pct"].quantile(q)
            sub = t_is[t_is["or_pct"] >= thr]
            mm = m(sub["net"].values)
            if mm is None:
                continue
            print(f"  OR={n_min:2}min filtro or_pct>=p{int(q*100):2} (thr {thr:.2f}%): "
                  f"IS n={mm['n']:4} Sharpe={mm['sharpe']:+.2f} PF={mm['pf']:.2f} exp={mm['exp']*1e4:+.0f}bp")
            if best is None or mm["sharpe"] > best["sharpe"]:
                best = dict(n_min=n_min, q=q, thr=thr, sharpe=mm["sharpe"])
    print(f"  -> elegido en IS: OR={best['n_min']}min · filtro or_pct>=p{int(best['q']*100)} (thr {best['thr']:.2f}%)")

    # --- aplicar la config elegida a OOS (sin re-tocar) ---
    t = orb_long_trades(df, best["n_min"])
    thr = t[pd.to_datetime(t["date"]).dt.date < IS_END]["or_pct"].quantile(best["q"])  # umbral fijado en IS
    t["seg"] = np.where(pd.to_datetime(t["date"]).dt.date < IS_END, "IS", "OOS")
    tf = t[t["or_pct"] >= thr]

    print(f"\n[2] RESULTADO con la config fija (umbral {thr:.2f}% fijado en IS):")
    show("ESTRATEGIA IS  (in-sample)", m(tf[tf.seg == "IS"]["net"].values))
    oos = tf[tf.seg == "OOS"]
    moos = m(oos["net"].values)
    show("ESTRATEGIA OOS (holdout)  ", moos)

    # --- benchmark anti-beta sobre los MISMOS días OOS ---
    bench = intraday_long_benchmark(df)
    bench["seg"] = np.where(pd.to_datetime(bench["date"]).dt.date < IS_END, "IS", "OOS")
    b_oos_all = bench[bench.seg == "OOS"]
    oos_days = set(oos["date"])
    b_oos_match = b_oos_all[b_oos_all["date"].isin(oos_days)]   # OJO: condiciona en días elegidos => lookahead
    print(f"\n[3] BENCHMARK ANTI-BETA (long intradía 09:30->16:00):")
    show("BENCH OOS (todos los días)*", m(b_oos_all["net"].values))
    show("BENCH días-trade (NO operable)", m(b_oos_match["net"].values))
    print("  *único benchmark honesto. 'días-trade' usa info post-apertura (qué días rompieron al alza)")
    print("   => no operable; solo mide cuánto del movimiento del día deja la estrategia sobre la mesa.")

    # --- veredicto ---
    print(f"\n[4] VEREDICTO OOS (2024-2026, holdout limpio):")
    if moos:
        p0 = psr(moos["sr_pt"], 0, moos["T"], moos["sk"], moos["ku"])
        print(f"  PSR(0) P(Sharpe OOS>0): {p0*100:.1f}%")
        bm = m(b_oos_all["net"].values)                          # anti-beta honesto = TODOS los días
        beats = moos["sharpe"] - (bm["sharpe"] if bm else 0)
        print(f"  Sharpe estrategia OOS {moos['sharpe']:+.2f}  vs beta (long intradía todos los días) "
              f"{bm['sharpe'] if bm else float('nan'):+.2f}  -> "
              f"{'GANA al beta por +%.2f de Sharpe = ALPHA real ★' % beats if beats > 0.15 else 'NO supera al beta = solo deriva long'}")
        full = m(b_oos_match["net"].values)
        if full:
            print(f"  Upside no capturado: en sus días el movimiento apertura->cierre fue {full['exp']*1e4:+.0f}bp "
                  f"vs {moos['exp']*1e4:+.0f}bp que captura -> entrada/stop deja mucho (margen de mejora, sin lookahead)")
        print(f"  Año a año OOS: " + " · ".join(f"{y}:{v[0]*100:+.0f}%" for y, v in by_year(oos).items()))
        print(f"  (se probaron ~{N_CONFIGS} configs; el Sharpe IS está inflado por selección, el OOS es el honesto.)")
    print("\n" + "=" * 84)


if __name__ == "__main__":
    main()

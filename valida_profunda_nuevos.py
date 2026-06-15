"""Validacion PROFUNDA de las 8 promovibles (batch SQZ/VTX) antes de tocar el roster vivo.

El riesgo que el gate OOS NO ve: 6 de 8 son SHORTS de alts -> aunque corr_agregada~0 vs
roster, pueden correlacionar fuerte ENTRE ellas (beta de alts en caidas) = pocas apuestas
reales disfrazadas de muchas. Aqui:
  1) Matriz de correlacion 8x8 (PnL diario) + nº efectivo de apuestas (participation ratio).
  2) EGLD-VTX-S vs S18 (EGLD-S BX+regimen+barrido, ya en roster) -> corr DIRECTA (redundancia?).
  3) Las 8 como cesta vol-parity: CAGR, maxDD, Sharpe + corr de la cesta vs roster-proxy.

Uso: python valida_profunda_nuevos.py
"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\valida_indicadores_nuevos.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])   # build_tr, CANDS, FN, run_f, met, filt_arrays, squeeze_momentum, vortex, load_fund, DATA, I, roster_pnl_daily...

# las 8 de alta conviccion (#1-8 del veredicto)
TOP8 = [
    ("ENA",  "SQZ", +1, ["regime"]),
    ("SAND", "VTX", -1, ["regime"]),
    ("WIF",  "SQZ", +1, ["regime"]),
    ("SEI",  "VTX", -1, ["sweep6", "trend"]),
    ("ARB",  "VTX", -1, ["sweep6", "trend"]),
    ("RUNE", "VTX", -1, ["sweep6", "trend"]),
    ("AVAX", "VTX", -1, ["sweep6"]),
    ("BNB",  "SQZ", +1, ["trend", "vol"]),
]


def daily_pnl(coin, sname, side, fs):
    df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    ft, fr = load_fund(coin)
    up, dn, _ = I.st_flips(df); flips = (up, dn)
    tr = build_tr(coin, df, ft, fr, flips, sname, side, fs)
    if tr is None:
        return None
    return tr.set_index("t_in")["ret"].resample("1D").sum()


def s18_egld_daily():
    """S18 = EGLD-S: B-X rojo (evento) + regimen<0 + barrido<=6. Reconstruido para corr directa."""
    coin = "EGLD"
    df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    ft, fr = load_fund(coin)
    up, dn, _ = I.st_flips(df); flips = (up, dn)
    c = df["close"]; _, rs, _, regdn = I.bx_parts(c)
    entry = np.asarray(rs) & np.asarray(regdn)
    fa = filt_arrays(df, -1)
    entry = entry & fa["sweep6"]
    tr = run_f(df, -1, "atrstop", None, entry, flips, "1h", ft, fr)
    return tr.set_index("t_in")["ret"].resample("1D").sum() if tr is not None else None


def basket_stats(daily_series, weights):
    M = pd.concat(daily_series, axis=1).fillna(0)
    port = (M * weights).sum(axis=1)
    eq = (1 + port).cumprod()
    yrs = (M.index[-1] - M.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = port.mean() / port.std() * np.sqrt(365) if port.std() > 0 else 0
    return cagr, dd, sharpe, port


def main():
    names = [f"{c}-{s}-{'L' if sd>0 else 'S'}" for c, s, sd, _ in TOP8]
    series = []
    for (c, s, sd, fs), nm in zip(TOP8, names):
        d = daily_pnl(c, s, sd, fs); d.name = nm; series.append(d)

    # 1) matriz de correlacion 8x8
    M = pd.concat(series, axis=1).fillna(0)
    corr = M.corr()
    print(f"{'='*92}\n1) CORRELACION ENTRE LAS 8 NUEVAS (PnL diario)")
    print(corr.round(2).to_string())
    # nº efectivo de apuestas (participation ratio de autovalores de la corr)
    ev = np.linalg.eigvalsh(corr.values)
    pr = (ev.sum() ** 2) / (ev ** 2).sum()
    offdiag = corr.values[np.triu_indices(len(corr), 1)]
    print(f"\n  corr media (off-diag): {offdiag.mean():.2f}  ·  max par: {offdiag.max():.2f}")
    print(f"  nº efectivo de apuestas (de 8): {pr:.1f}  -> "
          f"{'BIEN diversificado' if pr >= 5 else 'OK' if pr >= 3.5 else 'POCAS apuestas reales (alts colineales)'}")

    # 2) EGLD-VTX-S vs S18
    egld_vtx = daily_pnl("EGLD", "VTX", -1, ["sweep6", "trend"])
    s18 = s18_egld_daily()
    print(f"\n{'='*92}\n2) EGLD-VTX-S (candidato #9) vs S18 EGLD-S (ya en roster)")
    if egld_vtx is not None and s18 is not None:
        al = pd.concat([egld_vtx.rename("VTX"), s18.rename("S18")], axis=1).fillna(0)
        cc = al["VTX"].corr(al["S18"])
        print(f"  corr directa: {cc:.2f}  -> {'REDUNDANTE (no sumar)' if cc > 0.5 else 'complementaria (ok)' if cc < 0.3 else 'parcial'}")

    # 3) cesta vol-parity de las 8 + vs roster-proxy
    sig = M.std().replace(0, np.nan)
    w = (1 / sig); w = (w / w.sum()).values
    cagr, dd, sharpe, port = basket_stats(series, w)
    print(f"\n{'='*92}\n3) CESTA VOL-PARITY DE LAS 8 (1x, sin apalancar)")
    print(f"  CAGR {cagr*100:+.0f}%  ·  maxDD {dd*100:.0f}%  ·  Sharpe {sharpe:.2f}")
    R = roster_pnl_daily()
    al = pd.concat([port.rename("nuevas"), R.rename("roster")], axis=1).fillna(0)
    print(f"  corr cesta-nuevas vs roster-proxy(S1-S9): {al['nuevas'].corr(al['roster']):.2f}")
    # split OOS de la cesta
    cut = pd.Timestamp("2025-01-01")
    for lbl, seg in (("IS<2025", port[port.index < cut]), ("OOS>=2025", port[port.index >= cut])):
        if len(seg) > 5:
            sh = seg.mean() / seg.std() * np.sqrt(365) if seg.std() > 0 else 0
            print(f"    cesta {lbl}: Sharpe {sh:.2f}  exp_diario {seg.mean()*1e4:+.1f}bps")


if __name__ == "__main__":
    main()

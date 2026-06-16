"""Descubrimiento de patrones intradía en espacio NORMALIZADO (scale-free) — válido pese a que
el precio derive con los meses. Prueba 3 hipótesis del usuario sobre LITE (o cualquier ticker):

  A) IMÁN DE NÚMEROS REDONDOS: ¿el precio se queda/gira cerca de múltiplos de $10 y $5?
     Test scale-free: distancia al múltiplo más cercano (precio mod 10, mod 5). Si hay imán,
     el TIEMPO y las REVERSIONES se concentran cerca de 0 (vs uniforme si no hay efecto).
  B) MAPA HORARIO: a qué hora (ET) se mueve, en qué dirección, y cuándo se forman el alto/bajo
     del día. Responde "qué esperar cada día y a qué hora abrir".
  C) CAÍDA EN V + REBOTE: tras un movimiento rápido (k*σ en 30m), ¿revierte? ¿asimetría long/short?

Todo en retornos % (scale-free) y horario ET (maneja DST). Sesión regular 09:30-16:00 ET.
Uso: python patterns.py [TICKER]   (def LITE; también AAPL AMD NVDA MU TSLA)
"""
import sys
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TICKER = sys.argv[1] if len(sys.argv) > 1 else "LITE"
RECENT_DAYS = 60                     # "régimen reciente" para contrastar vs toda la historia
SESS_OPEN, SESS_CLOSE = "09:30", "15:59"


def load(ticker):
    df = pd.read_parquet(f"data_db/{ticker}_1m.parquet")[["open", "high", "low", "close", "volume"]]
    df = df.tz_convert("America/New_York")
    df = df.between_time(SESS_OPEN, SESS_CLOSE)          # solo sesión regular
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def regular_grid(df):
    """Reindexa cada día a una rejilla de 1-min (09:30..15:59) y ffill -> tiempo no sesgado."""
    out = []
    for day, g in df.groupby(df.index.normalize()):
        idx = pd.date_range(f"{day.date()} 09:30", f"{day.date()} 15:59", freq="1min",
                            tz="America/New_York")
        s = g["close"].reindex(idx).ffill().bfill()
        if s.notna().all():
            out.append(s)
    return pd.concat(out) if out else pd.Series(dtype=float)


def conc_metric(dist, step, half):
    """Fracción de masa dentro de ±half del múltiplo más cercano; compara con uniforme."""
    near = (np.abs(dist) <= half).mean()
    exp = (2 * half) / step
    return near, exp, near / exp


def analyze_round_numbers(grid, label):
    px = grid.values
    print(f"\n  [{label}]  n={len(px):,} minutos")
    for step in (10, 5):
        d = px - np.round(px / step) * step          # distancia al múltiplo más cercano, en [-step/2, step/2]
        for half in (0.5, 1.0):
            near, exp, ratio = conc_metric(d, step, half)
            flag = "★ IMÁN" if ratio >= 1.15 else ("repele" if ratio <= 0.85 else "neutro")
            print(f"    mod ${step}: tiempo a ±{half:.1f}$ = {near*100:5.1f}%  "
                  f"(uniforme {exp*100:.0f}%, x{ratio:.2f})  {flag}")


def analyze_reversals(grid, label, win=20, step=10):
    """Extremos locales (gira en ±win min) -> ¿se agrupan en números redondos?"""
    s = grid.reset_index(drop=True)
    n = len(s); piv = []
    arr = s.values
    for i in range(win, n - win):
        w = arr[i - win:i + win + 1]
        if arr[i] == w.max() or arr[i] == w.min():
            piv.append(arr[i])
    piv = np.array(piv)
    if len(piv) < 50:
        print(f"    [{label}] pocos pivots ({len(piv)})"); return
    d = piv - np.round(piv / step) * step
    near, exp, ratio = conc_metric(d, step, 1.0)
    print(f"    [{label}] {len(piv):,} pivots · giran a ±1$ de múltiplo de ${step}: "
          f"{near*100:.1f}% (uniforme {exp*100:.0f}%, x{ratio:.2f})  "
          f"{'★ giran en redondos' if ratio>=1.15 else 'neutro'}")


def analyze_timeofday(df, label):
    """Por bucket de 30 min (ET): |retorno| medio (movimiento) y retorno medio (deriva)."""
    g = df.copy()
    g["ret"] = g.groupby(g.index.normalize())["close"].pct_change()
    g = g.dropna(subset=["ret"])
    g["bucket"] = g.index.strftime("%H:%M").str[:2].astype(int) * 60 + \
                  (g.index.minute // 30) * 30
    def lbl(m): return f"{m//60:02d}:{m%60:02d}"
    tab = g.groupby("bucket")["ret"].agg(["mean", lambda x: x.abs().mean(), "count"])
    tab.columns = ["drift", "movpct", "n"]
    print(f"\n  [{label}] movimiento y deriva por media-hora (ET):")
    print(f"    {'hora':6} {'|mov|/min':>10} {'deriva/min':>11} {'n':>8}")
    for b, r in tab.iterrows():
        bar = "█" * int(r["movpct"] * 1e4 * 1.5)
        print(f"    {lbl(b):6} {r['movpct']*1e4:9.2f}bp {r['drift']*1e4:+10.2f}bp {int(r['n']):8,}  {bar}")
    # ¿cuándo se forma el alto/bajo del día?
    hb = df.groupby(df.index.normalize()).apply(
        lambda d: pd.Series({"hi": d["high"].idxmax().strftime("%H:%M"),
                             "lo": d["low"].idxmin().strftime("%H:%M")}), include_groups=False)
    print(f"    Hora más común del ALTO del día: {hb['hi'].mode().iloc[0]}  "
          f"· del BAJO del día: {hb['lo'].mode().iloc[0]}")


def analyze_vbounce(df, label, horizon=30, k=2.0):
    """Tras un movimiento rápido de 30m (≥k·σ), ¿qué hace en los próximos `horizon` min?"""
    g = df.copy()
    nd = g.index.normalize()
    g["r30"] = g.groupby(nd)["close"].pct_change(30)
    g["fwd"] = g.groupby(nd)["close"].shift(-horizon) / g["close"] - 1
    g = g.dropna(subset=["r30", "fwd"])
    sd = g["r30"].std()
    down = g[g["r30"] <= -k * sd]; up = g[g["r30"] >= k * sd]
    def line(name, sub):
        if len(sub) < 30:
            print(f"    {name}: pocos casos ({len(sub)})"); return
        fwd = sub["fwd"]
        wr = (fwd > 0).mean() if "DROP" in name else (fwd < 0).mean()
        print(f"    {name}: n={len(sub):5,} · fwd{horizon}m medio {fwd.mean()*1e4:+6.1f}bp "
              f"· mediana {fwd.median()*1e4:+6.1f}bp · 'rebote a favor' {wr*100:.0f}%")
    print(f"\n  [{label}] reacción {horizon}m tras movimiento rápido 30m de ±{k}σ (σ30m={sd*100:.2f}%):")
    line("V-DROP (cae rápido) -> ¿rebota arriba?", down)
    line("SPIKE (sube rápido) -> ¿corrige abajo?", up)


def main():
    print("=" * 78)
    print(f"PATRONES INTRADÍA — {TICKER}  (espacio normalizado, sesión regular ET)")
    print("=" * 78)
    df = load(TICKER)
    cut = df.index.normalize().unique()
    recent_cut = cut[-RECENT_DAYS] if len(cut) > RECENT_DAYS else cut[0]
    df_rec = df[df.index.normalize() >= recent_cut]
    print(f"Historia: {df.index[0].date()} -> {df.index[-1].date()} · {len(df):,} barras · "
          f"{len(cut)} días · reciente = últimos {RECENT_DAYS} días desde {recent_cut.date()}")

    print("\n" + "-" * 78 + "\nA) IMÁN DE NÚMEROS REDONDOS (tiempo cerca de múltiplos de $10/$5)")
    grid_full = regular_grid(df); grid_rec = regular_grid(df_rec)
    analyze_round_numbers(grid_full, "TODA LA HISTORIA")
    analyze_round_numbers(grid_rec, f"RECIENTE {RECENT_DAYS}d")
    print("\n  Reversiones (pivots) en números redondos:")
    analyze_reversals(grid_full, "HISTORIA", step=10)
    analyze_reversals(grid_rec, f"RECIENTE", step=10)
    analyze_reversals(grid_full, "HISTORIA", step=5)

    print("\n" + "-" * 78 + "\nB) MAPA HORARIO (cuándo se mueve y hacia dónde)")
    analyze_timeofday(df, "HISTORIA")
    analyze_timeofday(df_rec, f"RECIENTE {RECENT_DAYS}d")

    print("\n" + "-" * 78 + "\nC) CAÍDA EN V + REBOTE (mean-reversion tras movimiento rápido)")
    analyze_vbounce(df, "HISTORIA")
    analyze_vbounce(df_rec, f"RECIENTE {RECENT_DAYS}d")

    print("\n" + "=" * 78)
    print("Lee los ★ como hipótesis CON respaldo; 'neutro' = sin evidencia de ese patrón.")


if __name__ == "__main__":
    main()

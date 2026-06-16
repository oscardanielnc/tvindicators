"""¿Los NIVELES PREVIOS reales actúan como soporte/resistencia intradía? (la versión correcta
de la observación del usuario: no 'números redondos', sino máx/mín de ayer, cierre previo,
apertura, máx/mín de premarket).

Método honesto (scale-free) con PLACEBO: para cada nivel real L medimos, en el PRIMER TOQUE del
día, si el precio lo RECHAZA (revierte contra la dirección de aproximación) en los próximos M min;
y lo comparamos contra el MISMO nivel desplazado ±0.5–2% (líneas-placebo). Si L es S/R real,
rechaza MÁS que sus placebos cercanos. Si rechaza igual, es ilusión (toda línea recibe toques).
También mide STICKINESS: cuánto se queda pegado al nivel tras tocarlo ('se para ahí un rato').

Niveles testeados (todos definidos solo con info PREVIA, sin lookahead):
  PDH/PDL = máx/mín de la sesión de ayer · PDC = cierre de ayer · OPEN = apertura de hoy
  PMH/PML = máx/mín del premarket de hoy
Uso: python patterns_levels.py [TICKER]
"""
import sys
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TICKER = sys.argv[1] if len(sys.argv) > 1 else "LITE"
BAND = 0.0012          # tolerancia de 'toque': ±0.12%
THR = 0.0025           # umbral de reacción: 0.25% para contar rechazo/ruptura
M = 15                 # minutos de reacción tras el toque
STICK_WIN = 30         # ventana para medir 'se queda pegado'
PLACEBO_OFFS = [-0.02, -0.015, -0.01, -0.005, 0.005, 0.01, 0.015, 0.02]
RECENT_DAYS = 60


def load_full(ticker):
    df = pd.read_parquet(f"data_db/{ticker}_1m.parquet")[["open", "high", "low", "close", "volume"]]
    df = df.tz_convert("America/New_York")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def first_touch_reaction(day_close, day_high, day_low, L, side):
    """Devuelve (rechazo:0/1, stickiness:float) en el primer toque de L, o None si no toca/no hay margen."""
    n = len(day_close)
    band = L * BAND
    for i in range(3, n - M):
        if day_low[i] <= L + band and day_high[i] >= L - band:        # la barra cruza el nivel
            approached_up = day_close[i - 3] < L                       # venía de abajo (hacia resistencia)
            fut = day_close[i + M]
            moved = fut - L
            if side == "res" or (side == "both" and approached_up):
                reject = 1 if moved < -L * THR else 0                  # rebota hacia abajo = respeta resistencia
            elif side == "sup" or (side == "both" and not approached_up):
                reject = 1 if moved > +L * THR else 0                  # rebota hacia arriba = respeta soporte
            else:
                reject = 0
            stick = float(np.mean(np.abs(day_close[i:i + STICK_WIN] - L) <= band))
            return reject, stick
    return None


def run_level(df_days, level_fn, side):
    """Acumula rechazo/stick para el nivel REAL y para los placebos, sobre todos los días."""
    real_rej, real_stick, plc_rej, plc_stick = [], [], [], []
    for prior, today in df_days:
        L = level_fn(prior, today)
        if L is None or not np.isfinite(L):
            continue
        c = today["close"].values; h = today["high"].values; lo = today["low"].values
        r = first_touch_reaction(c, h, lo, L, side)
        if r is not None:
            real_rej.append(r[0]); real_stick.append(r[1])
        for off in PLACEBO_OFFS:
            rp = first_touch_reaction(c, h, lo, L * (1 + off), side)
            if rp is not None:
                plc_rej.append(rp[0]); plc_stick.append(rp[1])
    return np.array(real_rej), np.array(real_stick), np.array(plc_rej), np.array(plc_stick)


def ztest(rr, pr):
    """z de dos proporciones (real vs placebo)."""
    if len(rr) < 20 or len(pr) < 20:
        return 0.0
    p1, n1 = rr.mean(), len(rr); p2, n2 = pr.mean(), len(pr)
    p = (rr.sum() + pr.sum()) / (n1 + n2)
    se = np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return (p1 - p2) / se if se > 0 else 0.0


def build_days(df):
    """Lista de (prior_regular, today_regular) con premarket adjunto. Una sola pasada con groupby
    (evita ~2040 escaneos booleanos sobre 727k filas = el cuello de botella original)."""
    reg = df.between_time("09:30", "15:59")
    reg_g = {d: g for d, g in reg.groupby(reg.index.normalize())}
    pm = df.between_time("04:00", "09:29")
    pm_g = {d: g for d, g in pm.groupby(pm.index.normalize())}
    days = sorted(reg_g.keys())
    out = []
    for k in range(1, len(days)):
        prior, today = reg_g[days[k - 1]], reg_g[days[k]]
        if len(prior) < 30 or len(today) < 60:
            continue
        p = pm_g.get(days[k])
        today.attrs["pmh"] = p["high"].max() if p is not None and len(p) else np.nan
        today.attrs["pml"] = p["low"].min() if p is not None and len(p) else np.nan
        out.append((prior, today))
    return out


LEVELS = {
    "PDH (máx ayer)": (lambda p, t: p["high"].max(), "res"),
    "PDL (mín ayer)": (lambda p, t: p["low"].min(), "sup"),
    "PDC (cierre ayer)": (lambda p, t: p["close"].iloc[-1], "both"),
    "OPEN (apertura hoy)": (lambda p, t: t["close"].iloc[0], "both"),
    "PMH (máx premarket)": (lambda p, t: t.attrs.get("pmh"), "res"),
    "PML (mín premarket)": (lambda p, t: t.attrs.get("pml"), "sup"),
}


def report(df_days, label):
    print(f"\n  [{label}]  ({len(df_days)} días)")
    print(f"    {'nivel':22} {'toques':>7} {'rechazo':>8} {'placebo':>8} {'Δ':>6} {'z':>6} {'stick':>6} {'veredicto'}")
    for name, (fn, side) in LEVELS.items():
        rr, rs, pr, ps = run_level(df_days, fn, side)
        if len(rr) < 20:
            print(f"    {name:22} {len(rr):>7}  (pocos toques)"); continue
        z = ztest(rr, pr)
        d = rr.mean() - pr.mean()
        verd = "★ S/R real" if z >= 2 and d > 0 else ("anti-S/R" if z <= -2 else "ilusión/neutro")
        print(f"    {name:22} {len(rr):>7} {rr.mean()*100:7.1f}% {pr.mean()*100:7.1f}% "
              f"{d*100:+5.1f} {z:+6.2f} {rs.mean()*100:5.0f}% {verd}")


def main():
    print("=" * 90)
    print(f"NIVELES PREVIOS COMO S/R INTRADÍA — {TICKER}   (real vs placebo desplazado ±0.5–2%)")
    print("=" * 90)
    print(f"toque=±{BAND*100:.2f}% · reacción={M}min · rechazo si revierte >{THR*100:.2f}% · stick={STICK_WIN}min")
    df = load_full(TICKER)
    days = build_days(df)
    report(days, "TODA LA HISTORIA")
    report(days[-RECENT_DAYS:], f"RECIENTE {RECENT_DAYS}d")
    print("\n" + "=" * 90)
    print("'rechazo' = % de toques donde el precio revierte (respeta el nivel) en 15min.")
    print("Compáralo con 'placebo' (mismas líneas desplazadas al azar): si rechazo>>placebo (z≥2),")
    print("el nivel EXACTO importa = S/R real. Si son iguales, es ilusión (toda línea recibe toques).")


if __name__ == "__main__":
    main()

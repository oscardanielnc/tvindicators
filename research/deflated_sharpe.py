"""Deflated Sharpe Ratio (DSR) + Probabilistic Sharpe (PSR) — estimación INSESGADA del Sharpe
corrigiendo por SESGO DE SELECCIÓN (multiple testing) y NO-NORMALIDAD de los retornos.

Contexto: el Sharpe 4.07 de la cartera se eligió DESPUÉS de probar ~185 candidatos (5 batches +
sweeps). El mejor de N pruebas SIEMPRE parece bueno aunque ninguno tenga edge: bajo H0 (Sharpe
verdadero = 0), el máximo Sharpe esperado de N intentos crece con N. El DSR (Bailey & López de
Prado, 2014) deshace eso: compara el Sharpe observado contra el que esperarías por PURA SUERTE de
selección, y da la probabilidad de que el Sharpe verdadero supere ese umbral.

Mide tres cosas que el Sharpe crudo ignora:
  1) Largo de la muestra (T): un Sharpe alto con pocos días no es fiable.
  2) No-normalidad (skew/kurtosis): colas gordas / asimetría negativa inflan el Sharpe.
  3) Sesgo de selección (N pruebas): el headline elegido entre muchos está sesgado al alza.

Lecturas:
  - PSR(0)  = P(Sharpe verdadero > 0) dado T, skew, kurt.  Limpio, no depende de N.
  - E[max]  = Sharpe que esperarías por suerte tras N pruebas bajo H0 (el "listón" de selección).
  - DSR     = PSR(E[max]) = P(Sharpe verdadero > listón de selección).  >0.95 ≈ robusto.

Holdout: la selección usó IS<2025 y OOS>=2025 como gate de validación, así que NINGÚN tramo del
backtest es 100% limpio. El holdout verdaderamente limpio es el PAPER VIVO (por eso esta fase).
Aquí reportamos full y OOS(≥2025) para contraste, etiquetados honestamente.

Uso: python deflated_sharpe.py [N_pruebas]   (N_pruebas por defecto 185, el nº de candidatos probados)
"""
import sys
import math
from statistics import NormalDist
import numpy as np
import pandas as pd

try:                                    # consola Windows suele ser cp1252; el reporte usa σ/✅/≥
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\gen_summary.py", encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # tr_for, STRAT, ...

from tvbot import strategies as STRAT

N01 = NormalDist()                      # normal estándar (stdlib, sin scipy)
GAMMA = 0.5772156649015329              # constante de Euler-Mascheroni
ANN = math.sqrt(365)                    # factor de anualización (retornos diarios)
N_TRIALS_DEFAULT = 185                  # candidatos evaluados en los 5 batches + sweeps (ver audit_robustez)


def sr_stats(r):
    """r: retornos por-observación (diarios). Devuelve (SR_por-obs, skew, kurt_no-excess, T)."""
    r = np.asarray(r, float)
    T = len(r)
    mu = r.mean()
    sd = r.std(ddof=1) if T > 1 else 0.0
    if sd == 0:
        return 0.0, 0.0, 3.0, T
    z = (r - mu) / sd
    return mu / sd, float((z ** 3).mean()), float((z ** 4).mean()), T


def psr(sr, sr_star, T, skew, kurt):
    """Probabilistic Sharpe Ratio: P(SR_verdadero > sr_star). sr y sr_star en escala POR-OBSERVACIÓN."""
    if T < 2:
        return float("nan")
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr ** 2))
    return N01.cdf(((sr - sr_star) * math.sqrt(T - 1)) / denom)


def expected_max_sr(var_sr, N):
    """E[max SR] de N pruebas independientes bajo H0 (Bailey-LdP), por-observación.
    var_sr = varianza de los SR estimados entre las pruebas (mide cuán dispersas son)."""
    if N < 2 or var_sr <= 0:
        return 0.0
    s = math.sqrt(var_sr)
    a = N01.inv_cdf(1.0 - 1.0 / N)
    b = N01.inv_cdf(1.0 - 1.0 / (N * math.e))
    return s * ((1.0 - GAMMA) * a + GAMMA * b)


def min_track_record(sr, sr_star, skew, kurt, p=0.95):
    """T mínimo (días) para que PSR(sr_star) >= p. Cuántos datos hacen falta para confiar."""
    if sr <= sr_star:
        return float("inf")
    z = N01.inv_cdf(p)
    denom = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr ** 2
    return 1.0 + denom * (z / (sr - sr_star)) ** 2


def report_block(name, port, var_sr, N):
    """Imprime PSR/DSR para una serie de retornos diarios de cartera."""
    sr, sk, ku, T = sr_stats(port.values)
    emax = expected_max_sr(var_sr, N)
    p0 = psr(sr, 0.0, T, sk, ku)
    dsr = psr(sr, emax, T, sk, ku)
    yrs = (port.index[-1] - port.index[0]).days / 365.25 if T else 0
    print(f"\n--- {name} ---")
    print(f"  T={T} días (~{yrs:.1f} años) · skew {sk:+.2f} · kurtosis {ku:.1f} (normal=3)")
    print(f"  Sharpe anualizado: {sr * ANN:.2f}   (por-obs {sr:.3f})")
    print(f"  PSR(0)  P(Sharpe>0): {p0 * 100:.2f}%   <- limpio, no usa N")
    print(f"  Listón selección E[max] anualizado (N={N}): {emax * ANN:.2f}")
    print(f"  DSR  P(Sharpe>listón): {dsr * 100:.2f}%   {'✅ robusto' if dsr >= 0.95 else '⚠ no concluyente' if dsr >= 0.5 else '❌ probable artefacto'}")
    if emax > 0:
        trl = min_track_record(sr, emax, sk, ku)
        print(f"  Track record mínimo para DSR≥95%: ~{trl:.0f} días vs {T} disponibles "
              f"({'suficiente' if trl <= T else 'INSUFICIENTE, faltan ' + str(int(trl - T)) + ' días'})")
    return sr, dsr


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else N_TRIALS_DEFAULT

    # retornos diarios por estrategia (idéntico a gen_summary / audit_robustez)
    daily = {}
    per_sr = []  # SR diario por estrategia -> varianza entre "pruebas"
    for s in STRAT.STRATEGIES:
        tr = tr_for(s.sid)
        if tr is None or len(tr) < 5:
            continue
        d = tr.set_index("t_in")["ret"].resample("1D").sum()
        daily[s.sid] = d
        sr_i, *_ = sr_stats(d.values)
        per_sr.append((s.sid, sr_i))

    M = pd.concat(daily.values(), axis=1).fillna(0)
    sig = M.std().replace(0, np.nan)
    w = (1 / sig)
    w = (w / w.sum()).values
    port = (M * w).sum(axis=1)

    # varianza de los SR entre estrategias (proxy de dispersión de las pruebas, escala por-obs)
    sr_vals = np.array([v for _, v in per_sr])
    var_sr = float(sr_vals.var(ddof=1))

    print("=" * 74)
    print(f"DEFLATED SHARPE RATIO — corrige sesgo de selección ({N} pruebas) + no-normalidad")
    print("=" * 74)
    print(f"\nPruebas consideradas (N): {N}   ·   estrategias con retornos: {len(per_sr)}")
    print(f"Dispersión de los SR entre estrategias (var, por-obs): {var_sr:.5f}  "
          f"(σ={math.sqrt(var_sr) * ANN:.2f} anualizado)")
    print("NOTA: var_sr se calcula sobre los 56 SUPERVIVIENTES (no sobre los 185 originales),")
    print("      lo que subestima la dispersión real -> el DSR aquí es OPTIMISTA (cota superior).")

    # --- cartera completa ---
    report_block("CARTERA COMPLETA (vol-parity 1×, todo el histórico)", port, var_sr, N)

    # --- holdout OOS (semi-limpio: se usó como gate de validación) ---
    oos = port[port.index.year >= 2025]
    if len(oos) > 30:
        report_block("HOLDOUT OOS (≥2025) — semi-limpio (usado como gate); el limpio real es el paper",
                     oos, var_sr, N)

    # --- mejor estrategia individual (DSR clásico de López de Prado) ---
    best_sid, best_sr = max(per_sr, key=lambda x: x[1])
    bsk = sr_stats(daily[best_sid].values)
    bsr, bskew, bkurt, bT = bsk
    emax = expected_max_sr(var_sr, N)
    print(f"\n--- MEJOR ESTRATEGIA INDIVIDUAL: {best_sid} (DSR clásico, el caso de uso directo de LdP) ---")
    print(f"  Sharpe anualizado {bsr * ANN:.2f} · T={bT} días · skew {bskew:+.2f} · kurt {bkurt:.1f}")
    print(f"  DSR P(Sharpe>listón): {psr(bsr, emax, bT, bskew, bkurt) * 100:.2f}%")
    print(f"  -> incluso la mejor estrategia SUELTA puede no superar el listón de selección;")
    print(f"     el valor está en COMBINAR muchas poco-correlacionadas (efecto √N de cartera).")

    # --- sensibilidad a N (cuánto cambia el veredicto según cuántas pruebas asumas) ---
    print(f"\n--- SENSIBILIDAD del DSR de cartera al nº de pruebas N ---")
    sr_p, sk_p, ku_p, T_p = sr_stats(port.values)
    for n in (56, 100, 185, 365, 1000):
        em = expected_max_sr(var_sr, n)
        d = psr(sr_p, em, T_p, sk_p, ku_p)
        print(f"  N={n:5}: listón {em * ANN:.2f} anualizado · DSR {d * 100:.2f}%")

    print(f"\n{'=' * 74}\nLECTURA HONESTA")
    print("  - PSR(0) alto => la cartera es positiva con alta probabilidad (eso es sólido).")
    print("  - El DSR de cartera se sostiene porque el Sharpe combinado (√N) supera con holgura el")
    print("    listón de selección de UNA prueba; pero el listón honesto debería usar la dispersión")
    print("    de los 185 originales (no disponible aquí) -> trata el DSR como cota superior.")
    print("  - Juez final = paper vivo: es el único holdout que la selección no tocó.")


if __name__ == "__main__":
    main()

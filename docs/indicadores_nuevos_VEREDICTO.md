# Veredicto — Indicadores nuevos batch 1: Squeeze Momentum + Vortex

**Fecha:** 2026-06-15 · **Datos:** Binance perps 1h, store completo (52 monedas) · IS<2025 / OOS≥2025
**Costos:** maker 0.02% entrada · taker 0.045%+slip 0.02% en SL · funding real · exit = ATR-stop 2× + timeout 48h
**Pipeline:** idéntico al que validó S10-S21 (`expandir_universo.py` + `validar_combos.py`).

## TL;DR
Dos indicadores **no probados antes**, de clase distinta al roster (que es casi todo MA-trend):
- **Squeeze Momentum (LazyBear)** — ruptura tras compresión de volatilidad (BB dentro de KC) en la dirección del momentum.
- **Vortex (VI+/VI−)** — cruce direccional.

Barrido sobre 52 monedas → **22 setups** pasan el gate de período completo (exp>0, PF≥1.4, n≥40, años+), **corr media 0.06 vs el roster** (20/22 < 0.2 → genuinamente ortogonales). Validación OOS de los 15 mejores → **11 pasan OOS, 10 robustos a sensibilidad de longitud.** Hay edge nuevo real y descorrelacionado.

## Promovibles (OOS exp>0, n≥12, PF≥1.2, IS exp>0)

| # | Setup | Filtro | IS exp / PF | OOS exp / PF | Sens. | Nota |
|---|-------|--------|-------------|--------------|-------|------|
| 1 | **ENA SQZ-L** | regime | 220 / 1.78 | **264 / 2.36** | robusto | el más fuerte |
| 2 | **SAND VTX-S** | regime | 69 / 1.43 | 77 / 1.50 | robusto | **n=354, 5/5 años — el ancla** |
| 3 | **WIF SQZ-L** | regime | 239 / 1.67 | 182 / 1.91 | robusto | moneda joven (IS corto) |
| 4 | **SEI VTX-S** | sweep6+trend | 63 / 1.29 | 137 / 1.86 | robusto | |
| 5 | **ARB VTX-S** | sweep6+trend | 66 / 1.40 | 84 / 1.53 | robusto | |
| 6 | **RUNE VTX-S** | sweep6+trend | 86 / 1.53 | 80 / 1.44 | robusto | |
| 7 | **AVAX VTX-S** | sweep6 | 83 / 1.52 | 61 / 1.39 | robusto | |
| 8 | **BNB SQZ-L** | trend+vol | 48 / 1.40 | 66 / 1.63 | robusto | |
| 9 | **EGLD VTX-S** | sweep6+trend | 110 / 1.77 | 37 / 1.24 | robusto | ya hay EGLD-S (S18); chequear corr directa |
| 10 | WIF VTX-S | sweep6 | 10 / 1.03 | 307 / 3.03 | robusto | ⚠️ IS marginal: edge casi todo OOS |
| 11 | TAO SQZ-L | trend+vol | 141 / 1.55 | 86 / 1.40 | **frágil** | una longitud da exp<0 |

**Rechazados OOS:** XLM SQZ-L (OOS −4), AVAX SQZ-L (OOS PF 1.10), XRP SQZ-L (OOS PF 1.11), FET SQZ-L (OOS n=37 chico).

## Patrones
- **VTX brilla en SHORT de alts** (SAND, SEI, ARB, RUNE, AVAX, EGLD) — cruce bajista de vórtice + barrido/tendencia. Cluster coherente.
- **SQZ brilla en LONG de alts de alta vol** (ENA, WIF, BNB) — release alcista con filtro de régimen B-X.
- Ambos casan con el exit de continuación del harness (ATR-stop/timeout). Reversión a la media (Connors/RSI2) NO se probó: requiere otro motor de salida → batch 2.

## Caveats (honestos)
1. **Multiple-comparison:** se eligió el mejor filtro entre ~7×2×2 por celda sobre 52 monedas. El split OOS es la defensa principal; 11 pasando OOS con corr~0 está muy por encima del azar, pero los números son techo.
2. **WIF y monedas jóvenes** tienen IS corto → menos fiable; WIF-VTX-S (IS PF 1.03) es de baja convicción pese a pasar.
3. **Falta integración de portafolio:** estos aún NO pasaron por peso vol-parity ni DD combinado como el roster.
4. **EGLD ya tiene un short en roster (S18).** Antes de sumar EGLD-VTX-S verificar correlación directa con S18, no solo vs roster global.

## Validación profunda de las 8 (antes de tocar el roster vivo)
La preocupación que el gate OOS no ve: 6/8 son alts → ¿colapsan a pocas apuestas? Medido:

**Entre las 8** (`valida_profunda_nuevos.py`): corr media 0.06, par máximo 0.33 (ARB-S/AVAX-S),
**nº efectivo = 7.1 de 8** (bien diversificado). EGLD-VTX-S vs S18 = 0.44 → parcialmente
redundante, **excluida de las 8** (queda como #9). Cesta vol-parity de las 8: CAGR +41%,
maxDD −11%, **Sharpe 2.34** (OOS 3.26).

**Vs roster COMPLETO S1-S21** (`valida_roster_completo.py`, 21 entradas reconstruidas array-form
fieles a strategies.py):
- Libro de shorts: 11 existentes (9.2 apuestas efectivas) + 5 nuevas VTX-S → 16 shorts,
  **12.0 apuestas efectivas** (delta +2.8 de +5 → agregan diversificación real, no apilan beta).
- corr de cada nueva vs roster agregado: todas **≤ 0.22**.
- Portafolio vol-parity 1×: **21 solo** CAGR 28% / DD −4% / Sharpe 2.94  →  **21+8** CAGR 31% /
  DD −4% / **Sharpe 3.27 (+0.33)**. Suben Sharpe sin aumentar drawdown.

## PROMOVIDAS ✅ (2026-06-15)
Las 8 se integraron al roster vivo como **S22-S29** (role 0.5, exit ATR-stop 2× + timeout 48h):
S22 ENA-L, S23 SAND-S, S24 WIF-S→S(Vortex), S25 SEI-S, S26 ARB-S, S27 RUNE-S, S28 AVAX-S, S29 BNB-L.
Squeeze Momentum y Vortex añadidos a `tvbot/indicators.py` con **paridad exacta** verificada vs
la réplica de research (array-equal). `python -m tvbot --once` corre las 29 sin error; tests de
salidas OK. Dedup confirmado: ninguna duplica estrategias de Oscilion (familia EMA/VWAP/ORB) ni del
proyecto btc descartado (que usó BB-Squeeze, no LazyBear Squeeze, y nunca Vortex).

## Recomendación (original)
**Las 8 (#1-8) están listas para promover** como suplentes (role 0.5) → roster 21→29.
Validación completa: OOS + sensibilidad + correlación vs roster completo + impacto de portafolio.
#9 EGLD-VTX-S en observación (corr 0.44 con S18). Siguiente research: batch 2 = harness de
reversión a la media (Connors/RSI2, otro motor de salida).

## Artefactos
`poc_indicadores_nuevos.py` (sweep 52 monedas, SQZ+VTX, Pine-fieles) ·
`valida_indicadores_nuevos.py` (split IS/OOS + sensibilidad) ·
`valida_profunda_nuevos.py` (corr 8×8 + cesta) ·
`valida_roster_completo.py` (corr vs S1-S21 real + impacto portafolio).

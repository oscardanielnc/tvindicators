# Reporte del optimizador de roster (conservador — marca, no quita)

Pool: 48 incumbentes + 137 challengers OOS-robustos = 185 candidatos.
Selección greedy por Sharpe marginal (vol-parity). Umbral de redundancia: corr ≥ 0.5.

## 1) Pares de INCUMBENTES redundantes (corr de PnL ≥ 0.5) → revisar, quedarse con el mejor
- S1·TRX·L  ↔  S2·TRX·L   corr **0.83**

## 2) Incumbentes FUERA del top-48 óptimo (dominados / aporte marginal bajo) → observación
> No se quitan (fase paper); se marcan para vigilar si en vivo no aportan.
- S1·TRX·L, S4·SUI·S, S5·LTC·S, S8·ETH·S, S10·DOT·S, S11·ADA·S, S12·ADA·S, S13·DOT·S, S14·XLM·L, S15·RUNE·L, S16·IMX·L, S17·FLOW·L, S18·EGLD·S, S20·APT·S, S21·GRT·S, S25·SEI·S, S26·ARB·S, S27·RUNE·S, S28·AVAX·S, S32·EGLD·S, S33·DOT·S, S35·FLOW·S, S37·ORDI·L, S38·ORDI·L, S39·LINK·L, S40·NEO·L, S41·ICP·S, S43·ALGO·S, S47·STX·S, S48·CRV·S

## 3) Challengers que ENTRARÍAN al top-48 (mejores candidatos NO promovidos)
> El caso 'moneda Z mejor que X' o mejor combo no probado. Candidatos a evaluar/promover.
- **TAO-SQZ-L** — NUEVA apuesta (descorrelacionada) · corr 0.04 con S22·ENA·L
- **HBAR-AO-L** — NUEVA apuesta (descorrelacionada) · corr 0.05 con S16·IMX·L
- **FET-SQZ-L** — NUEVA apuesta (descorrelacionada) · corr 0.06 con S17·FLOW·L
- **JUP-AO-L** — NUEVA apuesta (descorrelacionada) · corr 0.07 con S3·TRX·L
- **SUI-KST-L** — NUEVA apuesta (descorrelacionada) · corr 0.1 con S16·IMX·L
- **TRX-SQZ-L** — NUEVA apuesta (descorrelacionada) · corr 0.12 con S2·TRX·L
- **WIF-KST-S** — NUEVA apuesta (descorrelacionada) · corr 0.14 con S12·ADA·S
- **NEAR-ADX-L** — NUEVA apuesta (descorrelacionada) · corr 0.14 con S6·XRP·L
- **WIF-VTX-S** — NUEVA apuesta (descorrelacionada) · corr 0.14 con S25·SEI·S
- **GRT-AO-L** — NUEVA apuesta (descorrelacionada) · corr 0.14 con S40·NEO·L
- **TRX-CMF-L** — NUEVA apuesta (descorrelacionada) · corr 0.15 con S14·XLM·L
- **PYTH-ZL-S** — NUEVA apuesta (descorrelacionada) · corr 0.17 con S46·NEO·S
- **TRX-FI-L** — NUEVA apuesta (descorrelacionada) · corr 0.17 con S2·TRX·L
- **NEAR-TSI-L** — NUEVA apuesta (descorrelacionada) · corr 0.19 con S39·LINK·L
- **FIL-ZL-S** — NUEVA apuesta (descorrelacionada) · corr 0.22 con S25·SEI·S
- **BNB-AO-L** — NUEVA apuesta (descorrelacionada) · corr 0.23 con S3·TRX·L
- **RUNE-ZL-S** — NUEVA apuesta (descorrelacionada) · corr 0.24 con S43·ALGO·S
- **CRV-ZL-L** — NUEVA apuesta (descorrelacionada) · corr 0.28 con S3·TRX·L
- **RUNE-KST-S** — NUEVA apuesta (descorrelacionada) · corr 0.29 con S27·RUNE·S
- **TIA-KST-S** — NUEVA apuesta (descorrelacionada) · corr 0.32 con S41·ICP·S
- **EGLD-TSI-S** — NUEVA apuesta (descorrelacionada) · corr 0.34 con S32·EGLD·S
- **WIF-FI-S** — NUEVA apuesta (descorrelacionada) · corr 0.34 con S12·ADA·S
- **FLOW-ZL-S** — NUEVA apuesta (descorrelacionada) · corr 0.38 con S35·FLOW·S
- **BCH-ADX-S** — NUEVA apuesta (descorrelacionada) · corr 0.38 con S46·NEO·S
- **DOT-ZL-S** — NUEVA apuesta (descorrelacionada) · corr 0.41 con S10·DOT·S
- **XLM-FI-L** — ALTERNATIVA a corr 0.53 con S14·XLM·L
- **BTC-CMF-L** — ALTERNATIVA a corr 0.54 con S9·BTC·L
- **WIF-CMF-L** — ALTERNATIVA a corr 0.58 con S24·WIF·L
- **SEI-TSI-S** — ALTERNATIVA a corr 0.64 con S25·SEI·S
- **TRX-KST-L** — ALTERNATIVA a corr 0.87 con S1·TRX·L

## Resumen
- Sharpe del portafolio óptimo (greedy, 60 sel.): **5.76**
- Incumbentes redundantes (pares): 1 · fuera del top: 30 · challengers a revisar: 30
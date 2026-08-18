# Veredicto — Batch 3: ADX/DMI + Squeeze-short + KAMA + Fisher

**Fecha:** 2026-06-15 · Datos store 52 monedas 1h · costos+funding reales · IS<2025/OOS≥2025
**Motor:** continuación (ATR-stop 2× + timeout 48h) · pipeline idéntico a batch 1.

## TL;DR — el mejor batch: edge GRUESO, baja frecuencia, encaja la filosofía
Sweep 52 monedas × 5 señales (Fisher, KAMA, ADX/DMI, Vortex-long, Squeeze-short) → **29 setups full+OOS**.
Por clase: **ADX 12, KAMA 9, Fisher 5, SQZ-short 2, VTX-long 1**. Validación profunda (sensibilidad + corr
directa vs el short del mismo par ya en roster) sobre los 8 mejores → **6 promovibles** robustos y no redundantes.

## Hallazgos
- **ADX/DMI en SHORT es la estrella**: cruce DI−>DI+ con ADX>25 + barrido/tendencia. Pocas señales (n~45),
  **edge 130-260 bps OOS**, IS≈OOS, PF 2-3.4. Es exactamente "raras y buenas".
- **Squeeze sirve también en SHORT** (el lado que el batch 1 no usó): EGLD (OOS 241, PF 3.13), FLOW (124).
- **KAMA** aporta shorts pero varios redundantes con los VTX-S existentes (mismo par → corr alta).
- **Vortex-long y Fisher-long: débiles** → ese lado no tiene edge fiable, descartado.

## Promovibles (robustos + no redundantes)
| # | Setup | Filtro | OOS exp / PF | Sens. | Corr par | Nota |
|---|-------|--------|--------------|-------|----------|------|
| 1 | **ARB-ADX-S** | trend+vol | 242 / 2.63 | [78,458] | 0.03 vs S26 | ortogonal pese a mismo par |
| 2 | **EGLD-SQZ-S** | sweep6 | 241 / 3.13 | fija | 0.18 vs S18 | |
| 3 | **DOT-ADX-S** | sweep6 | 219 / 2.52 | [45,132] | 0.10 vs S10 | |
| 4 | **HBAR-ADX-S** | sweep6 | 191 / 2.45 | [21,248] | par NUEVO | 5/5 años, moneda nueva |
| 5 | **FLOW-SQZ-S** | sweep6 | 124 / 1.72 | fija | short NUEVO | FLOW solo tenía long (S17) |
| 6 | 🟡 **AVAX-ADX-S** | sweep6 | 260 / 3.07 | [91,224] | **0.39** vs S28 | robusto pero corr media con S28 |

**Rechazados:** BCH-ADX-S (sensibilidad frágil, un param da −82), SEI-KAMA-S (corr 0.67 con S25 = redundante).

## Caveats
1. **n bajo en los ADX-S (43-53 trades)** → estimación de edge ruidosa. Mitigado: sensibilidad a thr(20/25/30)
   y n(10/14/18) toda positiva en los 5 robustos, e IS≈OOS ambos gruesos. Aun así, peso ½ y observar.
2. **AVAX-ADX-S corr 0.39 con S28** (AVAX-VTX-S): no redundante (<0.5) pero el par AVAX-short ya pesa;
   promover con cautela o dejar en observación.
3. Multiple-comparison alto (52×5×2×7); el split OOS + sensibilidad + corr directa son la defensa.

## Recomendación
Promover **las 5 limpias (ARB-ADX-S, EGLD-SQZ-S, DOT-ADX-S, HBAR-ADX-S, FLOW-SQZ-S)** como S31-S35 (role 0.5),
y AVAX-ADX-S (#6) opcional/observación por la corr con S28. Roster 30→35 (o 36). Requiere replicar
ADX/DMI en `tvbot/indicators.py` (Fisher/KAMA NO hacen falta: ningún promovido los usa salvo descartados).
Siguiente: batch 4 podría explorar combinaciones ADX×régimen o multi-TF de los ganadores.

## Artefactos
`poc_batch3.py` (sweep + OOS) · `valida_batch3.py` (sensibilidad + corr directa vs par).
**Lección:** ADX/DMI en short de alts + Squeeze bidireccional = vetas de edge grueso sin explotar; el
lado importa (Vortex solo short, Squeeze ambos, Fisher/Vortex-long no). Ver [[indicadores-nuevos-batch1-sqz-vtx]].

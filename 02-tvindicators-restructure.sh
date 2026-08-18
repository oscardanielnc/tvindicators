#!/usr/bin/env bash
# Reorganiza la raíz de tvindicators. Conserva historial con git mv.
# Ejecutar en Git Bash DENTRO de D:\OSCAR\Documents\Trading Proyects\tvindicators
#   bash 02-tvindicators-restructure.sh
set -euo pipefail

say() { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }
ask() { read -r -p "$1 [y/N] " r; [[ "$r" == "y" || "$r" == "Y" ]]; }

[[ -d .git ]] || { echo "No estás en la raíz del repo."; exit 1; }
[[ -d tvbot ]] || { echo "No encuentro tvbot/. ¿Es el repo correcto?"; exit 1; }

say "Estado actual"
git status --porcelain || true
if ! git diff-index --quiet HEAD --; then
  echo "Hay cambios sin commitear. Commitéalos o descártalos antes de reorganizar."; exit 1
fi

say "Creando rama de trabajo"
git checkout -b refactor/repo-structure

mkdir -p research docs data

move() { # mueve solo si existe y aún no está movido
  local f="$1" dest="$2"
  [[ -e "$f" ]] || return 0
  git mv -k "$f" "$dest/" 2>/dev/null && echo "  $f -> $dest/"
}

say "Moviendo scripts de investigación a research/"
for pat in 'poc_*.py' 'sweep*.py' 'valida*.py' 'validar_*.py' 'validate_*.py' \
           'tune_*.py' 'promote_*.py' 'audit_*.py' 'backtest_sd*.py' 'fetch_*.py' 'gen_*.py'; do
  for f in $pat; do move "$f" research; done
done
for f in apalancamiento.py backfill_shadow.py calibra_R.py candidatos.py confirmacion.py \
         deflated_sharpe.py expandir_universo.py informe_tesis.py paxg_roster.py \
         pipeline_universo.py portafolio.py pulir_filtros.py reconcile.py regime_split.py \
         riesgo_ruina.py robustez_top.py roster_optimizer.py sd_replica.py sensibilidad5.py \
         shortlist.py smc.py test_salidas.py; do
  move "$f" research
done

say "Moviendo documentación a docs/"
for f in *_VEREDICTO.md CONSOLIDADO.md METODOLOGIA_PRODUCCION.md VALIDACION_Y_PRODUCCION.md \
         ARQUITECTURA.md ESTADO_PROYECTO.md roster_optimizer_REPORT.md \
         backtest_sd_matrix.md backtest_sd_multi.md; do
  move "$f" docs
done

say "Moviendo CSV de resultados a data/"
for f in results_sweep*.csv; do move "$f" data; done

say "gitignore"
for l in '__pycache__/' '.pytest_cache/' '.venv/'; do
  grep -qxF "$l" .gitignore 2>/dev/null || echo "$l" >> .gitignore
done
git add .gitignore

say "Qué queda en la raíz"
ls -1 | grep -v '/$' || true

say "IMPORTANTE — revisar imports"
echo "Estos archivos hacen import entre sí y pueden haberse roto:"
grep -rln --include='*.py' -E '^(from|import) (poc_|sweep|valida|portafolio|smc|config)' research/ 2>/dev/null | head -20 || echo "  (nada obvio)"
echo
echo "Y estas referencias a rutas pueden necesitar ajuste:"
grep -rn --include='*.py' -E "results_sweep|ARQUITECTURA|CONSOLIDADO" . 2>/dev/null | head -10 || echo "  (ninguna)"

say "Tests"
if ask "Correr pytest ahora?"; then
  python -m pytest -q || echo "!! Tests fallando: arregla imports ANTES de commitear."
fi

say "Siguiente paso (manual, a propósito)"
cat <<'EOF'
  1. Arregla los imports/rutas que hayan quedado rotos.
  2. Actualiza README.md donde mencione rutas que cambiaron.
  3. Cuando pase pytest:
       git add -A
       git commit -m "refactor: reorganize repository structure"
       git checkout main && git merge refactor/repo-structure
       git push
  Si algo sale mal:  git checkout main && git branch -D refactor/repo-structure
EOF

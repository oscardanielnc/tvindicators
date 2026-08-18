#!/usr/bin/env bash
# Arregla el fallo de pytest tras la reorganización de tvindicators.
# Ejecutar en Git Bash DENTRO de tvindicators, en la rama refactor/repo-structure.
#   bash fix-tvindicators.sh
set -euo pipefail

say() { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }

[[ -d .git ]] || { echo "No estás en la raíz del repo."; exit 1; }

# ------------------------------------------------------------------ 1
say "1/4 · test_salidas.py no es un test, es un estudio"
# pytest lo recoge solo por el prefijo 'test_'. Renombrarlo resuelve la causa,
# no el síntoma: es un script de investigación que abre parquets externos.
if [[ -f research/test_salidas.py ]]; then
  git mv research/test_salidas.py research/salidas_study.py
  echo "  research/test_salidas.py -> research/salidas_study.py"
else
  echo "  ya renombrado, salto"
fi

# ------------------------------------------------------------------ 2
say "2/4 · Quitando la ruta absoluta a sweep3.py"
python - <<'PY'
from pathlib import Path
p = Path("research/salidas_study.py")
s = p.read_text(encoding="utf-8")
old = r'src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\sweep3.py", encoding="utf-8").read()'
new = ('from pathlib import Path as _P\n'
       'src = (_P(__file__).resolve().parent / "sweep3.py").read_text(encoding="utf-8")')
if old in s:
    p.write_text(s.replace(old, new, 1), encoding="utf-8")
    print("  ruta corregida (ahora relativa al propio archivo)")
elif "_P(__file__)" in s:
    print("  ya estaba corregida")
else:
    print("  !! no encontré la línea esperada, revísala a mano")
PY

# ------------------------------------------------------------------ 3
say "3/4 · Limitando qué recoge pytest"
if [[ -f pytest.ini ]]; then
  echo "  pytest.ini ya existe — revisa que tenga: testpaths = tests"
  cat pytest.ini
else
  printf '[pytest]\ntestpaths = tests\n' > pytest.ini
  git add pytest.ini
  echo "  pytest.ini creado con testpaths = tests"
fi

# ------------------------------------------------------------------ 4
say "4/4 · Buscando OTRAS rutas absolutas en el repo"
echo "Estas son rutas de tu máquina metidas en el código. No rompen nada hoy,"
echo "pero en un repo público no deberían estar:"
echo
grep -rn --include='*.py' -E '["'\'']([A-Za-z]:[\\/]|/home/|/root/)' . \
  | grep -v '^\./\.git' | grep -v '^\./\.venv' | head -40 || echo "  (ninguna)"
echo
echo "Ojo especialmente con C:/Users/LENOVO/... — expone tu usuario de Windows."

say "Ahora corre los tests"
echo "  python -m pytest -q"
echo
echo "Si pasan:"
cat <<'EOF'
  git add -A
  git commit -m "refactor: reorganize repository structure"
  git checkout main
  git merge refactor/repo-structure
  git push
EOF

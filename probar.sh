#!/bin/bash
# Corre la bateria de pruebas dentro del contenedor, contra su propia base.
#   ./probar.sh              todas
#   ./probar.sh candados     solo las de un archivo
#   ./probar.sh -k geocerca  solo las que coincidan con un nombre
set -e
cd "$(dirname "$0")"

if [ -z "$1" ]; then
  docker compose exec -T api pytest
elif [ "$1" = "-k" ]; then
  docker compose exec -T api pytest -k "$2"
else
  docker compose exec -T api pytest "tests/test_$1.py"
fi

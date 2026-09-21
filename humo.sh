#!/bin/bash
# La prueba de humo: las pantallas, en un navegador de verdad.
#
# Corre en su propio contenedor, con el navegador ya puesto, sobre la
# misma red de docker compose: no instala nada en la Mac y habla con
# `api` por su nombre, no por localhost.
#
# La bateria mira el motor y esto mira lo que se ve. Son dos cosas
# distintas y las dos hacen falta: en un solo dia salieron cuatro
# defectos de pantalla que `probar.sh` no podia tocar.
set -e
cd "$(dirname "$0")"

IMAGEN="mcr.microsoft.com/playwright:v1.49.0-noble"
RED="$(docker compose ps --format '{{.Name}}' api >/dev/null 2>&1 && \
       docker inspect centauro_api \
         -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' \
       2>/dev/null || true)"

if [ -z "$RED" ]; then
  echo "El sistema no esta arriba. Levantalo con: docker compose up -d"
  exit 1
fi

echo "Recorriendo las pantallas..."
docker run --rm \
  --network "$RED" \
  -v "$PWD/humo:/humo" \
  -w /humo \
  -e BASE="http://api:8000" \
  "$IMAGEN" \
  bash -c "npm install --silent playwright@1.49.0 >/dev/null 2>&1 || true; node humo.js"

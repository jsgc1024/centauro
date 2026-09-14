#!/bin/bash
# Borra la base, la vuelve a crear con las migraciones y siembra los catalogos.
# Util antes de correr los scripts de prueba, que no limpian lo que dejan.
set -e
cd "$(dirname "$0")"

echo "Borrando la base..."
docker compose down -v >/dev/null

echo "Levantando..."
docker compose up -d >/dev/null
sleep 12

echo "Aplicando migraciones..."
docker compose exec -T api alembic upgrade head

echo "Sembrando catalogos..."
curl -s -X POST http://localhost:8000/sistema/sembrar-catalogos >/dev/null
echo
echo "Base limpia y lista."

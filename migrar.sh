#!/bin/bash
# Atajos para trabajar con migraciones.
#
#   ./migrar.sh nueva "descripcion del cambio"   crea la migracion leyendo los modelos
#   ./migrar.sh aplicar                          aplica las migraciones pendientes
#   ./migrar.sh estado                           en que version esta la base
#   ./migrar.sh historial                        lista de migraciones
#   ./migrar.sh atras                            deshace la ultima migracion

set -e
cd "$(dirname "$0")"

case "$1" in
  nueva)
    [ -z "$2" ] && { echo "Falta la descripcion. Ej: ./migrar.sh nueva \"agrega tabla bonos\""; exit 1; }
    docker compose exec api alembic revision --autogenerate -m "$2"
    echo
    echo "Revisa el archivo generado en backend/migrations/versions/ antes de aplicarlo."
    ;;
  aplicar)  docker compose exec api alembic upgrade head ;;
  estado)   docker compose exec api alembic current -v ;;
  historial) docker compose exec api alembic history --verbose ;;
  atras)    docker compose exec api alembic downgrade -1 ;;
  *)
    echo "Uso: ./migrar.sh {nueva|aplicar|estado|historial|atras}"
    exit 1
    ;;
esac

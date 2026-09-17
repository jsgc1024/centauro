#!/usr/bin/env bash
#
# El respaldo diario de Centauro.
#
# Con las imagenes guardadas dentro de la base —las cuatro fotos de cada
# revision de unidad, los comprobantes de viaticos, las firmas— el
# respaldo ES el sistema completo. Se pierde el dump y se pierden las
# fotos que prueban en que estado se entrego una camioneta.
#
# Por eso este script no solo saca el dump: **lo restaura en una base
# desechable y cuenta las filas**. Un respaldo que nadie ha restaurado
# no es un respaldo, es un archivo grande.
#
# Se agenda en el cron del servidor, no en Celery: si la aplicacion esta
# caida es justo cuando mas falta hace.
#
#   0 3 * * *  /opt/centauro/despliegue/respaldo.sh >> /var/log/centauro-respaldo.log 2>&1
#
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINO="${CENTAURO_RESPALDOS:-/var/respaldos/centauro}"
DIAS_A_GUARDAR="${CENTAURO_DIAS:-14}"
COMPOSE="docker compose -f $RAIZ/docker-compose.prod.yml"
SELLO="$(date +%Y%m%d-%H%M)"
ARCHIVO="$DESTINO/centauro-$SELLO.dump"

decir() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

mkdir -p "$DESTINO"

# ---------------------------------------------------------------- sacar
decir "Sacando el respaldo…"
# Formato custom (-Fc): comprimido y restaurable por partes. El .sql
# plano de una base con imagenes dentro pesa el triple y tarda lo mismo.
$COMPOSE exec -T db pg_dump -U centauro -Fc centauro > "$ARCHIVO"

PESO=$(du -h "$ARCHIVO" | cut -f1)
if [ ! -s "$ARCHIVO" ]; then
  decir "ERROR: el respaldo salio vacio. No se borra nada viejo."
  exit 1
fi
decir "Respaldo en $ARCHIVO ($PESO)"

# ------------------------------------------------------------ verificar
# Aqui es donde este script se gana el sueldo. Se restaura en una base
# desechable dentro del mismo Postgres y se cuenta lo que llego. Si algo
# no cuadra, el respaldo viejo NO se borra.
PRUEBA="verificacion_$SELLO"
decir "Restaurando en $PRUEBA para verificar…"

limpiar() {
  $COMPOSE exec -T db psql -U centauro -d postgres \
    -c "DROP DATABASE IF EXISTS $PRUEBA;" >/dev/null 2>&1 || true
}
trap limpiar EXIT

$COMPOSE exec -T db psql -U centauro -d postgres \
  -c "CREATE DATABASE $PRUEBA;" >/dev/null

# pg_restore avisa de cosas menores —duenos, permisos— que no importan
# aqui: lo que se verifica es que los datos lleguen.
$COMPOSE exec -T db pg_restore -U centauro -d "$PRUEBA" --no-owner --no-acl \
  < "$ARCHIVO" >/dev/null 2>&1 || true

contar() {
  $COMPOSE exec -T db psql -U centauro -d "$1" -tAc \
    "SELECT count(*) FROM $2" 2>/dev/null | tr -d '[:space:]' || echo "x"
}

FALLAS=0
# Las tres que de verdad duelen: los servicios, el dinero y las fotos.
for TABLA in servicio asignacion_viatico foto_revision nomina_semanal; do
  VIVA=$(contar centauro "$TABLA")
  COPIA=$(contar "$PRUEBA" "$TABLA")
  if [ "$VIVA" = "$COPIA" ] && [ "$VIVA" != "x" ]; then
    decir "  $TABLA: $VIVA filas ✓"
  else
    decir "  $TABLA: la base tiene '$VIVA' y el respaldo '$COPIA'  ✗"
    FALLAS=$((FALLAS + 1))
  fi
done

if [ "$FALLAS" -gt 0 ]; then
  decir "ERROR: el respaldo no se restaura completo. No se borra nada viejo."
  exit 1
fi

decir "Verificado: el respaldo se restaura y trae todo."

# ----------------------------------------------------------- rotar
# Solo despues de verificar. Borrar lo viejo confiando en un archivo que
# no se ha abierto es como no tener respaldo.
BORRADOS=$(find "$DESTINO" -name 'centauro-*.dump' -mtime "+$DIAS_A_GUARDAR" -print -delete | wc -l)
decir "Se guardan $DIAS_A_GUARDAR dias. Borrados: $BORRADOS"

# ------------------------------------------------------- fuera del servidor
#
# Object storage S3 multizona. Es lo unico que protege del caso que de
# verdad importa: perder el servidor. Un respaldo en el mismo disco que
# la base no es un respaldo, es una copia.
#
# Se sube con la imagen oficial del cliente de AWS para no tener que
# instalar nada en el servidor, y con `--endpoint-url` sirve igual con
# cualquier proveedor compatible con S3, no solo con AWS.
#
# En el .env:
#   RESPALDO_S3_DESTINO=s3://centauro-respaldos/postgres
#   RESPALDO_S3_ENDPOINT=https://s3.us-west-1.amazonaws.com   (opcional)
#   RESPALDO_S3_REGION=us-west-1
#   AWS_ACCESS_KEY_ID=...
#   AWS_SECRET_ACCESS_KEY=...
#
# DOS COSAS DEL LADO DEL BUCKET, y las dos importan mas que este script:
#
#   1. La credencial de aqui NO debe poder borrar. Solo PutObject. Si el
#      servidor se ve comprometido, quien entre tiene estas llaves: con
#      permiso de borrado se lleva tambien todo el historial de
#      respaldos, que es justo lo que se iba a usar para recuperarse.
#
#   2. Versionado y Object Lock (WORM) en el bucket, con una regla de
#      ciclo de vida que retire lo viejo. La rotacion remota la hace el
#      bucket, no este script: si el script pudiera borrar alla,
#      volveriamos al punto uno.
if [ -n "${RESPALDO_S3_DESTINO:-}" ]; then
  decir "Subiendo a $RESPALDO_S3_DESTINO…"
  LLAVE="$(basename "$ARCHIVO")"

  ENDPOINT=()
  [ -n "${RESPALDO_S3_ENDPOINT:-}" ] && ENDPOINT=(--endpoint-url "$RESPALDO_S3_ENDPOINT")

  aws_() {
    docker run --rm \
      -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
      -e AWS_DEFAULT_REGION="${RESPALDO_S3_REGION:-us-east-1}" \
      -v "$DESTINO:/respaldos:ro" \
      amazon/aws-cli:latest "$@"
  }

  # --sse: cifrado en reposo del lado del proveedor. Es el minimo. Si
  # algun dia hace falta que el proveedor tampoco pueda leerlo, el dump
  # se cifra aqui antes de subirlo y la llave privada vive fuera del
  # servidor; hasta entonces, esto.
  if aws_ s3 cp "/respaldos/$LLAVE" "$RESPALDO_S3_DESTINO/$LLAVE" \
        --sse AES256 --only-show-errors "${ENDPOINT[@]}"; then
    decir "Subido."
  else
    decir "ERROR: no se pudo subir el respaldo fuera del servidor."
    exit 1
  fi

  # Que la subida diga "ok" no quiere decir que el archivo este completo
  # del otro lado. Se pregunta el tamano y se compara: una subida que
  # falla a la mitad y nadie revisa es un respaldo que no existe.
  LOCAL=$(stat -c%s "$ARCHIVO" 2>/dev/null || stat -f%z "$ARCHIVO")
  REMOTO=$(aws_ s3 ls "$RESPALDO_S3_DESTINO/$LLAVE" "${ENDPOINT[@]}" \
           | awk '{print $3}' | tr -d '[:space:]')
  if [ "$LOCAL" != "$REMOTO" ]; then
    decir "ERROR: alla pesa '$REMOTO' y aqui '$LOCAL'. La copia no sirve."
    exit 1
  fi
  decir "Verificado del otro lado: $REMOTO bytes."
else
  decir "AVISO: sin RESPALDO_S3_DESTINO. El respaldo se queda en este"
  decir "       servidor, y eso no protege del unico caso que importa."
fi

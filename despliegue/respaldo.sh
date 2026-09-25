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
# caida es justo cuando mas falta hace. En el servidor de Google va en
# /etc/cron.d/centauro-respaldo (ver despliegue/LEEME.md, paso 8), a las
# 2:30, antes de la foto diaria del disco de las 3:00:
#
#   30 2 * * *  root  /opt/centauro/despliegue/respaldo.sh >> /var/log/centauro-respaldo.log 2>&1
#
set -euo pipefail

# El dump es la empresa entera: servicios, dinero, fotos y firmas. Lo
# que crea este script solo lo lee quien lo corre.
umask 077

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Lo que este script necesita del .env del servidor. En el cron no hay
# nada en el entorno --el .env lo lee docker compose, no bash--, y sin
# esto la copia fuera del servidor no se hacia nunca: cada noche decia
# "sin RESPALDO_S3_DESTINO" aunque estuviera en el .env. Se lee renglon
# por renglon y no con `source`: el .env no es bash (CORREO_DE lleva < y >).
del_env() {
  local valor="${!1:-}"
  if [ -z "$valor" ] && [ -f "$RAIZ/.env" ]; then
    valor="$(grep -E "^$1=" "$RAIZ/.env" | tail -1 | cut -d= -f2- | tr -d '\r')"
  fi
  printf '%s' "$valor"
}

# En modo prueba no se rota nada, no se sube nada y el dump se borra al
# terminar. Es para correrlo en la maquina de desarrollo y ver con los
# propios ojos que el respaldo se restaura, que es lo unico que
# convierte un archivo grande en un respaldo.
#
#   ./despliegue/respaldo.sh --probar
PROBANDO=0
[ "${1:-}" = "--probar" ] && PROBANDO=1

# En el servidor, el compose de produccion; probando, el de desarrollo,
# que es el que esta encendido en la maquina de quien prueba. Un script
# que solo corre en el servidor es un script que nadie prueba hasta el
# dia que hace falta.
if [ "$PROBANDO" = "1" ]; then
  ARCHIVO_COMPOSE="${CENTAURO_COMPOSE:-$RAIZ/docker-compose.yml}"
else
  ARCHIVO_COMPOSE="${CENTAURO_COMPOSE:-$RAIZ/docker-compose.prod.yml}"
fi
COMPOSE="docker compose -f $ARCHIVO_COMPOSE"

if [ "$PROBANDO" = "1" ]; then
  DESTINO="$(mktemp -d)"
else
  DESTINO="${CENTAURO_RESPALDOS:-/var/respaldos/centauro}"
fi
DIAS_A_GUARDAR="${CENTAURO_DIAS:-14}"
SELLO="$(date +%Y%m%d-%H%M)"
ARCHIVO="$DESTINO/centauro-$SELLO.dump"

decir() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# La base desechable de la verificacion se borra pase lo que pase, y el
# resultado de la noche se anota tambien en el registro del sistema: de
# ahi lo lee el agente de Google, y un respaldo que falla en silencio se
# descubre el dia que hace falta.
PRUEBA=""
limpiar() {
  [ -n "$PRUEBA" ] || return 0
  $COMPOSE exec -T db psql -U centauro -d postgres \
    -c "DROP DATABASE IF EXISTS $PRUEBA;" >/dev/null 2>&1 || true
}
al_salir() {
  local salida=$?
  limpiar
  if [ "$PROBANDO" = "0" ] && command -v logger >/dev/null 2>&1; then
    if [ "$salida" = "0" ]; then
      logger -t centauro-respaldo "Respaldo completo: $(basename "$ARCHIVO")" || true
    else
      logger -p user.err -t centauro-respaldo \
        "ERROR: el respaldo fallo (salida $salida). Ver /var/log/centauro-respaldo.log" || true
    fi
  fi
}
trap al_salir EXIT

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
# El sello lleva un guion --20260919-1442-- y en el nombre de un
# archivo se lee bien, pero Postgres no acepta guiones en el nombre de
# una base sin comillas. Se cambia por guion bajo aqui y solo aqui.
PRUEBA="verificacion_${SELLO//-/_}"
decir "Restaurando en $PRUEBA para verificar…"

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

# Y el contenido de las fotos, no solo cuantas son.
#
# Es la diferencia entre "llegaron 240 filas" y "llegaron las mismas
# 240 fotos". Las imagenes viven DENTRO de la base --las cinco de cada
# revision de unidad, los comprobantes, las firmas-- y son lo que se
# usa para discutir un golpe tres semanas despues. Una fila que llega
# con la imagen cortada cuenta igual y no sirve para nada.
#
# Se saca un md5 por fila y un md5 del conjunto: comparar los datos
# completos de las dos bases no cabria en memoria.
huella() {
  $COMPOSE exec -T db psql -U centauro -d "$1" -tAc \
    "SELECT coalesce(md5(string_agg(md5(imagen), '' ORDER BY id)), 'vacia')
       FROM foto_revision" 2>/dev/null | tr -d '[:space:]' || echo "x"
}

VIVAS=$(huella centauro)
COPIAS=$(huella "$PRUEBA")
if [ "$VIVAS" = "vacia" ] && [ "$COPIAS" = "vacia" ]; then
  # Sin fotos no hay nada que comparar, y eso NO es una verificacion
  # buena: es una que no se hizo. Decirlo con palomita seria decir que
  # se probo lo unico que de verdad hay que probar.
  decir "  fotos: no hay ninguna en la base. ESTA PARTE NO SE PROBO."
  decir "         El dia que haya fotos reales, vuelve a correr esto."
elif [ "$VIVAS" = "$COPIAS" ] && [ "$VIVAS" != "x" ]; then
  decir "  fotos: el contenido coincide ✓ ($VIVAS)"
else
  decir "  fotos: la base dice '$VIVAS' y el respaldo '$COPIAS'  ✗"
  FALLAS=$((FALLAS + 1))
fi

# Y que la copia sepa en que version del esquema esta: una base sin la
# marca de alembic se restaura pero no se puede seguir migrando.
VERSION=$($COMPOSE exec -T db psql -U centauro -d "$PRUEBA" -tAc \
  "SELECT version_num FROM alembic_version" 2>/dev/null | tr -d '[:space:]')
if [ -n "$VERSION" ]; then
  decir "  esquema: $VERSION ✓"
else
  decir "  esquema: el respaldo no trae la version de alembic  ✗"
  FALLAS=$((FALLAS + 1))
fi

if [ "$FALLAS" -gt 0 ]; then
  decir "ERROR: el respaldo no se restaura completo. No se borra nada viejo."
  exit 1
fi

decir "Verificado: el respaldo se restaura y trae todo."

if [ "$PROBANDO" = "1" ]; then
  decir "Modo prueba: no se rota nada ni se sube nada."
  rm -rf "$DESTINO"
  if [ "$VIVAS" = "vacia" ]; then
    decir "Listo. El respaldo se saca y se restaura. Lo de las fotos"
    decir "       queda pendiente hasta que haya fotos que comparar."
  else
    decir "Listo. El respaldo se saca, se restaura y trae las fotos enteras."
  fi
  exit 0
fi

# ----------------------------------------------------------- rotar
# Solo despues de verificar. Borrar lo viejo confiando en un archivo que
# no se ha abierto es como no tener respaldo.
BORRADOS=$(find "$DESTINO" -name 'centauro-*.dump' -mtime "+$DIAS_A_GUARDAR" -print -delete | wc -l)
decir "Se guardan $DIAS_A_GUARDAR dias. Borrados: $BORRADOS"

# ------------------------------------------------------- fuera del servidor
#
# En Google Cloud (seccion 68) va al deposito del proyecto, con la cuenta
# de la propia maquina y sin llaves: lo sube backend/subir_a_google.py,
# que pregunta al final que llego y compara tamano y md5. En el .env:
#
#   RESPALDO_GCS_DESTINO=gs://centauro-respaldos-<proyecto>/postgres
#
# La cuenta de la maquina puede crear y leer alla, no borrar, y el
# deposito no deja borrar ni reemplazar nada antes de 14 dias: son los
# mismos dos candados de abajo, puestos del lado de Google.
#
# Fuera de Google: object storage S3 multizona. Cualquiera de los dos es
# lo unico que protege del caso que de verdad importa: perder el
# servidor. Un respaldo en el mismo disco que la base no es un respaldo,
# es una copia.
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
GCS_DESTINO="$(del_env RESPALDO_GCS_DESTINO)"
RESPALDO_S3_DESTINO="$(del_env RESPALDO_S3_DESTINO)"
RESPALDO_S3_ENDPOINT="$(del_env RESPALDO_S3_ENDPOINT)"
RESPALDO_S3_REGION="$(del_env RESPALDO_S3_REGION)"

if [ -n "$GCS_DESTINO" ]; then
  decir "Subiendo a $GCS_DESTINO…"
  if python3 "$RAIZ/backend/subir_a_google.py" "$ARCHIVO" "$GCS_DESTINO"; then
    decir "Fuera del servidor: completo."
  else
    decir "ERROR: no se pudo subir el respaldo fuera del servidor."
    exit 1
  fi
elif [ -n "$RESPALDO_S3_DESTINO" ]; then
  decir "Subiendo a $RESPALDO_S3_DESTINO…"
  AWS_ACCESS_KEY_ID="$(del_env AWS_ACCESS_KEY_ID)"
  AWS_SECRET_ACCESS_KEY="$(del_env AWS_SECRET_ACCESS_KEY)"
  export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
  LLAVE="$(basename "$ARCHIVO")"

  ENDPOINT=()
  [ -n "$RESPALDO_S3_ENDPOINT" ] && ENDPOINT=(--endpoint-url "$RESPALDO_S3_ENDPOINT")

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
  decir "AVISO: sin RESPALDO_GCS_DESTINO ni RESPALDO_S3_DESTINO. El respaldo"
  decir "       se queda en este servidor, y eso no protege del unico caso"
  decir "       que importa."
fi

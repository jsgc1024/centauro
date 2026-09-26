#!/bin/bash
# El archivo de los comprobantes (seccion 69), en Cloud Shell:
#
#   bash crear_archivo.sh
#
# Tres meses despues de la factura, las fotos de los comprobantes salen de
# Centauro y se guardan aqui seis anos. Este script arma el deposito y lo
# que lo rodea:
#
#   - el deposito, en EE. UU. como el de los respaldos --otra region que
#     la maquina--, clase Archive (la mas barata, y se lee al momento),
#     sin acceso publico;
#   - el candado de retencion: nadie borra ni reemplaza una foto antes de
#     seis anos. Queda SIN SELLAR: se sella cuando el contador confirme el
#     plazo (ver despliegue/LEEME.md), porque sellado ya no se acorta;
#   - el borrado solo, a los seis anos;
#   - la cuenta de la maquina puede guardar y leer, no borrar;
#   - la alerta "Centauro: fallo el archivo" a los dos correos de las
#     demas alertas.
#
# Se puede volver a correr: lo que ya existe se deja como esta. Al final
# dice el renglon que va en el .env del servidor; hasta que se pega ahi,
# no sale ninguna foto de Centauro.
set -euo pipefail

PROYECTO=project-8fda7c0c-0799-4989-9c2
CUENTA=centauro-vm@$PROYECTO.iam.gserviceaccount.com
DEPOSITO=gs://centauro-archivo-$PROYECTO
ANIOS=${ANIOS:-6}
DIAS=$((ANIOS * 365 + (ANIOS + 3) / 4))    # seis anos, con sus bisiestos

hay() { "$@" >/dev/null 2>&1; }

if [ "$(hostname)" = "centauro" ]; then
  echo "ALTO: esto va en Cloud Shell, no dentro de la maquina."
  echo "Escribe exit, espera la linea que dice cloudshell y vuelve a pegarlo."
  exit 1
fi
gcloud config set project "$PROYECTO" >/dev/null 2>&1
D=$(mktemp -d)

echo "1/4 El deposito del archivo: $DEPOSITO"
hay gcloud storage buckets describe "$DEPOSITO" || \
  gcloud storage buckets create "$DEPOSITO" --location=US \
    --default-storage-class=ARCHIVE --uniform-bucket-level-access \
    --public-access-prevention
echo "{\"rule\":[{\"action\":{\"type\":\"Delete\"},\"condition\":{\"age\":$DIAS}}]}" > "$D/ciclo.json"
gcloud storage buckets update "$DEPOSITO" --lifecycle-file="$D/ciclo.json" >/dev/null
if gcloud storage buckets describe "$DEPOSITO" \
     --format='value(retention_policy.isLocked)' 2>/dev/null | grep -qi true; then
  echo "    El candado ya esta sellado: no se toca."
else
  gcloud storage buckets update "$DEPOSITO" --retention-period="${DIAS}d" >/dev/null
  echo "    Candado de $ANIOS anos puesto, sin sellar."
fi

echo "2/4 La cuenta de la maquina: guardar y leer, no borrar"
for ROL in roles/storage.objectCreator roles/storage.objectViewer; do
  gcloud storage buckets add-iam-policy-binding "$DEPOSITO" \
    --member="serviceAccount:$CUENTA" --role=$ROL >/dev/null
done

echo "3/4 La alerta si una noche falla"
canal() {
  gcloud beta monitoring channels list --project="$PROYECTO" \
    --filter="displayName=\"$1\"" --format='value(name)' | head -1
}
C1=$(canal "Salvador - correo")
C2=$(canal "Salvador - Centauro")
if [ -z "$C1" ] || [ -z "$C2" ]; then
  echo "    ALTO: no encuentro los dos correos de las alertas. Corre primero"
  echo "    el bloque de las alertas y vuelve a correr este."
  exit 1
fi
cat > "$D/archivo.json" <<EOF
{
  "displayName": "Centauro: fallo el archivo",
  "combiner": "OR",
  "conditions": [{
    "displayName": "El archivo de la noche dijo ERROR",
    "conditionMatchedLog": {
      "filter": "logName=\"projects/$PROYECTO/logs/syslog\" AND \"centauro-archivo\" AND \"ERROR\""
    }
  }],
  "alertStrategy": {"notificationRateLimit": {"period": "3600s"}, "autoClose": "86400s"},
  "notificationChannels": ["$C1", "$C2"],
  "documentation": {"mimeType": "text/markdown", "content": "Anoche algunas fotos de comprobantes no se pudieron archivar. Se quedan en Centauro y se reintenta la noche siguiente; no se perdio nada. Entra a la maquina y revisa con: journalctl -t centauro-archivo --since yesterday"}
}
EOF
if [ -n "$(gcloud monitoring policies list --project="$PROYECTO" \
            --filter='displayName="Centauro: fallo el archivo"' --format='value(name)')" ]; then
  echo "    Ya existia."
else
  gcloud monitoring policies create --project="$PROYECTO" \
    --policy-from-file="$D/archivo.json" --format='value(name)' >/dev/null
  echo "    Lista, a tus dos correos."
fi

echo "4/4 Listo. Este renglon va en el .env del servidor (con nano):"
echo
echo "    ARCHIVO_DESTINO=$DEPOSITO"
echo
echo "Hasta que se pega ahi y se aplica con up -d api worker beat, no sale"
echo "ninguna foto de Centauro."

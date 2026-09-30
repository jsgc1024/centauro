#!/bin/bash
# Los expedientes del freelance (seccion 111), en Cloud Shell:
#
#   bash crear_expedientes.sh
#
# El PDF y las fotos de lo que Recursos Humanos pide para activar a un
# freelance --INE, antecedentes, pruebas toxicologicas, la caratula del
# banco-- no se quedan en la base: van a un deposito privado de Google y
# solo se abren desde Connect, con permiso. Este script arma el deposito:
#
#   - en Mexico (northamerica-south1), junto a la maquina: se abre cada vez
#     que Recursos Humanos revisa un documento, y los datos personales de
#     la gente de aqui se quedan aqui;
#   - clase Standard, porque se lee seguido; sin acceso publico;
#   - la cuenta de la maquina puede guardar y leer, no borrar;
#   - SIN borrado automatico ni candado: se guardan mientras el freelance
#     colabore y seis anos despues de su ultimo servicio (decision 7), y
#     eso no lo puede contar un reloj del deposito desde el dia en que se
#     subio. Connect no borra nada.
#
# Se puede volver a correr: lo que ya existe se deja como esta. Al final
# dice el renglon que va en el .env del servidor; hasta que se pega ahi,
# los archivos se quedan en la base y la tarea de cada hora los muda en
# cuanto se ponga.
set -euo pipefail

PROYECTO=project-8fda7c0c-0799-4989-9c2
CUENTA=centauro-vm@$PROYECTO.iam.gserviceaccount.com
DEPOSITO=gs://centauro-expedientes-$PROYECTO

hay() { "$@" >/dev/null 2>&1; }

if [ "$(hostname)" = "centauro" ]; then
  echo "ALTO: esto va en Cloud Shell, no dentro de la maquina."
  echo "Escribe exit, espera la linea que dice cloudshell y vuelve a pegarlo."
  exit 1
fi
gcloud config set project "$PROYECTO" >/dev/null 2>&1

echo "1/2 El deposito de los expedientes: $DEPOSITO"
hay gcloud storage buckets describe "$DEPOSITO" || \
  gcloud storage buckets create "$DEPOSITO" --location=northamerica-south1 \
    --default-storage-class=STANDARD --uniform-bucket-level-access \
    --public-access-prevention

echo "2/2 La cuenta de la maquina: guardar y leer, no borrar"
for ROL in roles/storage.objectCreator roles/storage.objectViewer; do
  gcloud storage buckets add-iam-policy-binding "$DEPOSITO" \
    --member="serviceAccount:$CUENTA" --role=$ROL >/dev/null
done

echo "Listo. Este renglon va en el .env del servidor:"
echo
echo "    EXPEDIENTES_DESTINO=$DEPOSITO"
echo
echo "Y se aplica con up -d api worker beat."

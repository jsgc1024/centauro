#!/bin/bash
# El servidor de Centauro en Google Cloud, region Queretaro.
# Se corre en Cloud Shell. Lo que ya existe se deja como esta: se puede
# volver a correr sin romper nada.
set -euo pipefail

REGION=northamerica-south1
ZONA=northamerica-south1-a
MAQUINA=e2-standard-2
DISCO=100GB
IMAGEN=ubuntu-2404-lts-amd64
PROYECTO=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROYECTO" ] || { echo "ALTO: Cloud Shell no tiene proyecto elegido."; exit 1; }
CUENTA=centauro-vm@$PROYECTO.iam.gserviceaccount.com
DEPOSITO=gs://centauro-respaldos-$PROYECTO
hay() { "$@" >/dev/null 2>&1; }
echo "Proyecto: $PROYECTO"

echo "1/8 Nombre del proyecto"
gcloud projects update "$PROYECTO" --name="Centauro produccion" >/dev/null

echo "2/8 Servicios de Google (la primera vez tarda un par de minutos)"
gcloud services enable compute.googleapis.com iap.googleapis.com \
  monitoring.googleapis.com logging.googleapis.com storage.googleapis.com

echo "3/8 Red propia: al mundo solo la web; la administracion solo por el tunel de Google"
hay gcloud compute networks describe centauro-red || \
  gcloud compute networks create centauro-red --subnet-mode=custom
hay gcloud compute networks subnets describe centauro-subred --region=$REGION || \
  gcloud compute networks subnets create centauro-subred --network=centauro-red \
    --region=$REGION --range=10.20.0.0/24
hay gcloud compute firewall-rules describe centauro-web || \
  gcloud compute firewall-rules create centauro-web --network=centauro-red \
    --direction=INGRESS --allow=tcp:80,tcp:443 --source-ranges=0.0.0.0/0 \
    --target-tags=web
hay gcloud compute firewall-rules describe centauro-ssh-iap || \
  gcloud compute firewall-rules create centauro-ssh-iap --network=centauro-red \
    --direction=INGRESS --allow=tcp:22 --source-ranges=35.235.240.0/20 \
    --target-tags=iap-ssh

echo "4/8 IP fija"
hay gcloud compute addresses describe centauro-ip --region=$REGION || \
  gcloud compute addresses create centauro-ip --region=$REGION
IP=$(gcloud compute addresses describe centauro-ip --region=$REGION \
  --format='value(address)')

echo "5/8 Cuenta de la maquina, con lo minimo"
if ! hay gcloud iam service-accounts describe "$CUENTA"; then
  gcloud iam service-accounts create centauro-vm --display-name="Centauro servidor"
  sleep 15
fi
for ROL in roles/logging.logWriter roles/monitoring.metricWriter; do
  gcloud projects add-iam-policy-binding "$PROYECTO" \
    --member="serviceAccount:$CUENTA" --role=$ROL --condition=None >/dev/null
done

echo "6/8 Deposito de respaldos: fuera de la region, y nada se borra antes de 14 dias"
hay gcloud storage buckets describe "$DEPOSITO" || \
  gcloud storage buckets create "$DEPOSITO" --location=US \
    --uniform-bucket-level-access --public-access-prevention \
    --retention-period=14d
echo '{"rule":[{"action":{"type":"Delete"},"condition":{"age":90}}]}' > /tmp/ciclo.json
gcloud storage buckets update "$DEPOSITO" --lifecycle-file=/tmp/ciclo.json >/dev/null
for ROL in roles/storage.objectCreator roles/storage.objectViewer; do
  gcloud storage buckets add-iam-policy-binding "$DEPOSITO" \
    --member="serviceAccount:$CUENTA" --role=$ROL >/dev/null
done

echo "7/8 La maquina"
hay gcloud compute images describe-from-family $IMAGEN --project=ubuntu-os-cloud || {
  echo "ALTO: no encuentro la imagen $IMAGEN. Las de Ubuntu 24.04 que hay:"
  gcloud compute images list --project=ubuntu-os-cloud --filter="family~2404" \
    --format='value(family)' | sort -u
  exit 1; }
hay gcloud compute instances describe centauro --zone=$ZONA || \
  gcloud compute instances create centauro --zone=$ZONA --machine-type=$MAQUINA \
    --subnet=centauro-subred --address="$IP" --tags=web,iap-ssh \
    --image-family=$IMAGEN --image-project=ubuntu-os-cloud \
    --boot-disk-size=$DISCO --boot-disk-type=pd-balanced \
    --service-account="$CUENTA" --scopes=cloud-platform \
    --metadata=enable-oslogin=TRUE \
    --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
    --deletion-protection

echo "8/8 Foto diaria del disco completo, 14 dias"
hay gcloud compute resource-policies describe centauro-diario --region=$REGION || \
  gcloud compute resource-policies create snapshot-schedule centauro-diario \
    --region=$REGION --daily-schedule --start-time=09:00 \
    --max-retention-days=14 --on-source-disk-delete=keep-auto-snapshots
gcloud compute disks describe centauro --zone=$ZONA \
  --format='value(resourcePolicies)' | grep -q centauro-diario || \
  gcloud compute disks add-resource-policies centauro --zone=$ZONA \
    --resource-policies=centauro-diario

echo
echo "Listo. IP fija del servidor: $IP"
echo "Deposito de respaldos: $DEPOSITO"
echo "Para entrar a la maquina:"
echo "  gcloud compute ssh centauro --zone=$ZONA --tunnel-through-iap"

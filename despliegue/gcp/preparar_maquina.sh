#!/bin/bash
# Prepara la maquina de Centauro (Ubuntu 24.04 en Google Cloud).
# Se corre DENTRO de la maquina:  sudo bash ~/preparar.sh
# Lo que ya esta hecho se deja como esta: se puede volver a correr.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
[ "$(id -u)" = 0 ] || { echo "ALTO: correlo asi:  sudo bash ~/preparar.sh"; exit 1; }
QUIEN=${SUDO_USER:-}
APT="apt-get -y -q -o DPkg::Lock::Timeout=600 -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
instalado() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "ok installed"; }

echo "1/7 Hora de Mexico"
timedatectl set-timezone America/Mexico_City

echo "2/7 Todo al dia (tarda unos minutos)"
apt-get -q -o DPkg::Lock::Timeout=600 update
$APT full-upgrade
$APT install ca-certificates curl git unattended-upgrades

echo "3/7 Parches de seguridad solos cada noche; si piden reinicio, a las 4:00"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat > /etc/apt/apt.conf.d/52centauro <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF
for T in apt-daily:03:00 apt-daily-upgrade:03:30; do
  mkdir -p "/etc/systemd/system/${T%%:*}.timer.d"
  printf '[Timer]\nOnCalendar=\nOnCalendar=*-*-* %s\nRandomizedDelaySec=10m\n' \
    "${T#*:}" > "/etc/systemd/system/${T%%:*}.timer.d/centauro.conf"
done
systemctl daemon-reload
systemctl restart apt-daily.timer apt-daily-upgrade.timer

echo "4/7 Docker, del repositorio oficial de Docker"
if ! instalado docker-ce; then
  for P in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx \
           podman-docker containerd runc; do
    if instalado "$P"; then $APT remove "$P"; fi
  done
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt-get -q -o DPkg::Lock::Timeout=600 update
  $APT install docker-ce docker-ce-cli containerd.io docker-buildx-plugin \
    docker-compose-plugin
fi
# Registros que no llenan el disco (5 de 20 MB por contenedor), los
# contenedores siguen vivos si Docker se reinicia, y las imagenes publicas
# bajan de la copia de Google antes que de Docker Hub.
mkdir -p /etc/docker
cat > /tmp/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {"max-size": "20m", "max-file": "5"},
  "live-restore": true,
  "registry-mirrors": ["https://mirror.gcr.io"]
}
EOF
if ! cmp -s /tmp/daemon.json /etc/docker/daemon.json; then
  if dockerd --validate --config-file=/tmp/daemon.json >/dev/null 2>&1; then
    install -m 0644 /tmp/daemon.json /etc/docker/daemon.json
    systemctl restart docker
  else
    echo "AVISO: Docker no acepto su configuracion; se queda con la de fabrica."
  fi
fi
systemctl enable --now docker containerd >/dev/null 2>&1
# Para usar docker sin sudo. Con OS Login el usuario no esta en
# /etc/passwd, por eso gpasswd y no usermod.
if [ -n "$QUIEN" ] && ! id -nG "$QUIEN" | grep -qw docker; then
  gpasswd -a "$QUIEN" docker >/dev/null
fi

echo "5/7 Memoria de reserva (swap) de 4 GB"
if ! grep -qE '^/swapfile[[:space:]]' /proc/swaps; then
  [ -f /swapfile ] || fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
fi
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
cat > /etc/sysctl.d/60-centauro.conf <<'EOF'
# El swap solo como ultimo recurso.
vm.swappiness = 10
# Redis lo pide para guardar a disco sin fallar.
vm.overcommit_memory = 1
EOF
sysctl -q -p /etc/sysctl.d/60-centauro.conf

echo "6/7 Agente de Google: memoria y disco, para las alertas"
if ! instalado google-cloud-ops-agent; then
  curl -fsSL https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh \
    -o /tmp/ops-agent.sh
  bash /tmp/ops-agent.sh --also-install
fi

echo "7/7 La maquina ve su deposito de respaldos, con su propia cuenta y sin llaves"
META=http://metadata.google.internal/computeMetadata/v1
PROYECTO=$(curl -fsS -H 'Metadata-Flavor: Google' $META/project/project-id)
DEPOSITO=centauro-respaldos-$PROYECTO
TOKEN=$(curl -fsS -H 'Metadata-Flavor: Google' \
  $META/instance/service-accounts/default/token |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
ve_deposito() {
  curl -fsS -o /dev/null -H "Authorization: Bearer $TOKEN" \
    "https://storage.googleapis.com/storage/v1/b/$DEPOSITO/o?maxResults=1"
}

FALTAN=0
revisa() {
  local texto=$1; shift
  if "$@" >/dev/null 2>&1; then printf '  OK     %s\n' "$texto"
  else printf '  FALTA  %s\n' "$texto"; FALTAN=$((FALTAN+1)); fi
}
echo
echo "=============== RESUMEN ==============="
revisa "Hora de Mexico: $(date '+%d/%m/%Y %H:%M')" \
  test "$(timedatectl show -p Timezone --value)" = America/Mexico_City
revisa "Parches solos cada noche, reinicio 4:00 si hace falta" \
  test -f /etc/apt/apt.conf.d/52centauro
revisa "Docker $(docker version -f '{{.Server.Version}}' 2>/dev/null)" \
  systemctl is-active --quiet docker
revisa "Docker Compose $(docker compose version --short 2>/dev/null)" \
  docker compose version
revisa "Registros de Docker con limite" grep -q max-size /etc/docker/daemon.json
revisa "Swap de $(free -h | awk '/^Swap:/{print $2}')" grep -qE '^/swapfile[[:space:]]' /proc/swaps
revisa "Agente de Google" systemctl is-active --quiet \
  google-cloud-ops-agent-opentelemetry-collector google-cloud-ops-agent-fluent-bit
revisa "Deposito gs://$DEPOSITO" ve_deposito
revisa "Disco de $(df -h --output=size / | tail -1 | tr -d ' ')" \
  test "$(df -BG --output=size / | tail -1 | tr -dc 0-9)" -ge 90
if [ -n "$QUIEN" ]; then
  revisa "$QUIEN usa docker sin sudo (al volver a entrar)" \
    sh -c "id -nG '$QUIEN' | grep -qw docker"
fi
echo "======================================="
[ "$FALTAN" = 0 ] && echo "Todo en orden." || echo "Hay $FALTAN renglon(es) con FALTA: mandame la foto."

if [ -f /var/run/reboot-required ]; then
  echo
  echo "La maquina se reinicia en 1 minuto para estrenar lo que se actualizo."
  echo "Se va a cortar la conexion: es normal. Vuelve a entrar en 2 minutos."
  shutdown -r +1 >/dev/null 2>&1 || true
fi

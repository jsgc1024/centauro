# Despliegue

Lo que hay aquí y para qué sirve. El detalle de por qué cada cosa está
así vive en `ARQUITECTURA.md`, en la raíz.

| Archivo | Qué es |
|---|---|
| `../docker-compose.prod.yml` | Los seis procesos de producción |
| `Caddyfile` | El proxy con TLS. Saca y renueva el certificado solo |
| `respaldo.sh` | `pg_dump` diario **que se restaura y se cuenta** |
| `crear_env.py` | El `.env` de la primera vez, con sus contraseñas generadas en el servidor |
| `gcp/crear_servidor.sh` | El servidor en Google Cloud: red, IP fija, máquina, depósito de respaldos y foto diaria del disco |
| `gcp/preparar_maquina.sh` | La máquina lista: parches solos, Docker, hora de México, swap y el agente de Google |
| `gcp/crear_archivo.sh` | El archivo de los comprobantes: el depósito de seis años, sus permisos y su alerta |
| `gcp/crear_expedientes.sh` | Los expedientes del freelance: su depósito privado, en México, y sus permisos |
| `../backend/primer_arranque.py` | Los catálogos sin nada de ejemplo y la primera cuenta |
| `../backend/subir_a_google.py` | La copia del respaldo al depósito de Google, sin llaves |

---

## Dónde vive: Google Cloud

Desde el 25 de septiembre de 2026 (sección 68 de la bitácora). Lo
montó Salvador directamente, sin intermediario.

- **Proyecto** «Centauro produccion» (`project-8fda7c0c-0799-4989-9c2`),
  región Querétaro (`northamerica-south1`, zona `-a`). Créditos de
  Google hasta el 25 de diciembre de 2026.
- **La máquina** `centauro`: `e2-standard-2` (2 procesadores, 8 GB),
  disco de 100 GB, Ubuntu 24.04, IP fija **34.51.121.227**. Protegida
  contra borrado.
- **La red** es propia (`centauro-red`): al mundo solo 80 y 443. La
  administración entra **solo por el túnel de Google** (IAP) y con la
  cuenta de Google de quien entra (OS Login): en la máquina no hay
  contraseñas ni llaves SSH que robar.
- **La cuenta de la máquina**, `centauro-vm`, con lo mínimo: escribir
  registros y métricas, y crear y leer en el depósito de respaldos. No
  puede borrar.
- **El depósito de respaldos**, `gs://centauro-respaldos-project-8fda7c0c-0799-4989-9c2`,
  en EE. UU. —otra región que la máquina—, sin acceso público, con
  **retención de 14 días** (nada se borra ni se reemplaza antes) y
  borrado automático a los 90.
- **Foto diaria del disco completo**, a las 3:00, guardada 14 días.
  Además del respaldo de la base, no en su lugar.
- **El depósito del archivo**, `gs://centauro-archivo-project-8fda7c0c-0799-4989-9c2`
  (sección 69): las fotos de los comprobantes tres meses después de la
  factura, seis años. Lo arma `gcp/crear_archivo.sh`; ver *El archivo de
  los comprobantes*, abajo.
- **La organización** nace con políticas seguras por defecto; una de
  ellas prohíbe IP pública en las máquinas. Se abrió la excepción solo
  para esta máquina (`compute.vmExternalIpAccess`). Para verla, en Cloud
  Shell: `gcloud org-policies describe compute.vmExternalIpAccess
  --project=project-8fda7c0c-0799-4989-9c2`.

**Entrar a la máquina**, desde Cloud Shell:

```bash
gcloud compute ssh centauro --zone=northamerica-south1-a --tunnel-through-iap
```

**Cómo se armó**: `gcp/crear_servidor.sh` en Cloud Shell y
`gcp/preparar_maquina.sh` dentro de la máquina, con `sudo`. Los dos se
pueden volver a correr: lo que ya existe se deja como está.

**Solo, cada noche**: los parches de seguridad de Ubuntu a las 3:30 y,
si alguno pide reinicio, la máquina se reinicia a las 4:00. Los seis
procesos vuelven solos (`restart: unless-stopped`). Docker no se
actualiza solo: eso se hace a mano, en un rato tranquilo.

---

## Encender por primera vez

**1. El servidor.** Ubuntu LTS o Debian estable, con Docker y Docker
Compose. Zona horaria en `America/Mexico_City`. Solo los puertos 80 y
443 abiertos al mundo. En Google Cloud lo dejan así los dos scripts de
`gcp/` (arriba).

**1b. El código llega por git.** El repositorio vive en GitHub
(`jsgc1024/centauro`, privado). El servidor lo clona con una **llave de
despliegue de solo lectura**, no con la cuenta de nadie: si alguien
entra al servidor, con esa llave puede leer el código, pero no
modificarlo ni tocar otros repositorios.

En el servidor, como el usuario que va a operar:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -C "servidor-centauro-gcp" -f ~/.ssh/id_ed25519 -N ""
curl -fsSL https://api.github.com/meta | python3 -c 'import json,sys; print("\n".join("github.com " + k for k in json.load(sys.stdin)["ssh_keys"]))' >> ~/.ssh/known_hosts
cat ~/.ssh/id_ed25519.pub
```

La tercera línea le dice al servidor cuáles son las llaves de GitHub,
leídas de GitHub por HTTPS: así `git clone` no pregunta si confía en
un desconocido. La última imprime la llave del servidor, y esa línea se
pega en GitHub: repositorio → *Settings* → *Deploy keys* → *Add deploy
key*, título `servidor centauro (Google Cloud)`, **sin** marcar *Allow
write access*. Luego:

```bash
sudo mkdir -p /opt/centauro && sudo chown "$USER": /opt/centauro
git clone git@github.com:jsgc1024/centauro.git /opt/centauro
cd /opt/centauro
```

Para actualizar después, desde `/opt/centauro`:

```bash
git pull
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d api worker beat
```

**2. El `.env`.** La primera vez lo crea `crear_env.py`, con la
contraseña de Postgres, la de Redis y la clave de sesión generadas ahí
mismo: no salen en pantalla ni quedan en el historial, y el archivo solo
lo lee quien lo creó. Si ya hay un `.env`, no lo toca.

```bash
cd /opt/centauro && python3 despliegue/crear_env.py
```

Lo demás —las llaves de Google, Microsoft, Odoo y Pegasus— se pega con
`nano .env` cuando llega cada una, nunca con `echo` —queda en el
historial de la terminal— y no va al repositorio. Estos son los
renglones que puede llevar:

```
# Las dos puertas (seccion 71): la consola --del personal
# administrativo y los consultores-- y la app del personal de seguridad.
DOMINIO=mycentauro.lat
DOMINIO_CAMPO=appep.mycentauro.lat
# La app del cliente de la Central de Inteligencia (seccion 136).
DOMINIO_CI=ci.mycentauro.lat
URL_CI=https://ci.mycentauro.lat
POSTGRES_PASSWORD=...
REDIS_PASSWORD=...
DATABASE_URL=postgresql+psycopg://centauro:LA_DE_ARRIBA@db:5432/centauro
REDIS_URL=redis://:LA_OTRA@redis:6379/0
APP_ENV=produccion
SECRET_KEY=...
GOOGLE_MAPS_KEY=...
# La del navegador, limitada a mycentauro.lat/* y ci.mycentauro.lat/*
# (seccion 135).
GOOGLE_MAPS_KEY_NAVEGADOR=...
# El lector de noticias y redes (seccion 140): la llave de Claude
# (console.anthropic.com → API Keys) y el Bearer Token de X (portal de
# desarrolladores de X, con la cuenta de la Central). Sin ellas el
# lector sigue: sin Claude, solo por palabras; sin X, sin la lista.
ANTHROPIC_API_KEY=...
X_BEARER_TOKEN=...
TELEFONO_CENTRAL=+525550221022
VAPID_CONTACTO=mailto:operaciones@centauro.lat

# De donde cuelgan los enlaces que van en correos y task sheets. Es
# el mismo DOMINIO de arriba: la consola.
URL_PUBLICA=https://mycentauro.lat

# El correo que sale del sistema: desde mycentauro.lat, por Amazon SES,
# con SMTP (paso 7c). Las respuestas de los clientes van a
# CORREO_RESPONDER_A. Estos renglones los escribe poner_correo.py, que
# pide el usuario y la contrasena SMTP de Amazon; la contrasena no se ve. Los
# tres CORREO_MS_ se dejan vacios: llenos, mandaria Microsoft 365 (paso
# 7b) y el SMTP no se usaria. Sin ninguno de los dos, no sale nada: los
# avisos quedan pendientes. Y nada sale hasta CORREO_ENCENDIDO=si, que se
# pone con poner_correo.py --encender despues de la prueba (seccion 86).
CORREO_ENCENDIDO=no
CORREO_DE=Centauro Connect <connect@mycentauro.lat>
CORREO_RESPONDER_A=Centauro Connect <cecc.notification@centauro.lat>
CORREO_MS_TENANT=
CORREO_MS_CLIENTE=
CORREO_MS_SECRETO=
CORREO_HOST=email-smtp.us-east-2.amazonaws.com
CORREO_PUERTO=587
CORREO_USUARIO=
CORREO_CLAVE=

# Odoo, de salida: la factura del servicio. Vacio = nada sale; el
# cierre se queda en "por facturar" y se manda despues.
ODOO_URL=
ODOO_TOKEN=

# Odoo, de entrada: Centauro lee de ahi al personal de seguridad cada
# hora, y solo lee. La llave es la del usuario «Centauro (conexion)»,
# no la de una persona, y Odoo la da por tres meses como maximo.
ODOO_BASE=https://centauro.odoo.com
ODOO_API_KEY=

# La factura en Odoo (secciones 116 y 117): la llave con que Connect
# crea en Odoo la prefactura en borrador del visto bueno --del eventual y
# del mes del implantado--, y nada mas: no la confirma, no la timbra, no
# la borra. Va aparte de ODOO_API_KEY para poder cambiarla sin tocar
# codigo; por decision de Salvador, por ahora el mismo valor. Vacia = no
# se manda nada y la factura se hace en Odoo como antes. Con ella, la
# tarea de cada hora (odoo.mandar_prefacturas, a los :07) reintenta lo
# que no salio. Si en Odoo el producto de los gastos no se llama
# «Gastos de Operación (Viáticos)», ODOO_PRODUCTO_GASTOS lo dice.
ODOO_FACTURACION_API_KEY=

# Lo de Odoo por pais (secciones 77, 112, 121 y 123). Vienen con su valor
# de siempre: solo se cambian si en Odoo se llaman distinto. Los campos
# del CPF y la CNH se buscan por su nombre visible («CPF», «CNH»); aqui
# va el nombre tecnico si hace falta.
ODOO_ETIQUETA_CLIENTES=Protección ejecutiva
ODOO_CAMPO_IMPLANTADOS=x_studio_lista_de_implantados
ODOO_CATEGORIA_PRODUCTOS=Protección Ejecutiva
ODOO_PREFIJO_LISTAS=PE ·
ODOO_IDIOMA=es_MX
ODOO_CATEGORIA_PRODUCTOS_BR=Proteção Executiva Brasil
ODOO_PREFIJO_LISTAS_BR=Brasil ·
ODOO_IDIOMA_BR=pt_BR
ODOO_PRODUCTO_GASTOS=Gastos de Operación (Viáticos)
ODOO_CAMPO_CPF=
ODOO_CAMPO_CNH=

# Pegasus, el GPS de las unidades. Vacio = no se lee nada. PEGASUS_GRUPOS
# dice que grupo se lee en cada pais.
PEGASUS_SITIO=https://www.centaurosatelital.mx
PEGASUS_USUARIO=
PEGASUS_CLAVE=
PEGASUS_SECRETO_AVISO=
PEGASUS_GRUPOS=MX=2025 P.E.;BR=CENTAURO BRASIL

# A donde va la copia del respaldo (paso 8).
RESPALDO_GCS_DESTINO=gs://centauro-respaldos-project-8fda7c0c-0799-4989-9c2/postgres

# El archivo de los comprobantes (seccion 69). Vacio = no sale ninguna
# foto de Centauro; el historial de Facturacion dice cuando se irian.
ARCHIVO_DESTINO=

# Los expedientes del freelance (seccion 111). Vacio = sus archivos se
# quedan en la base hasta que se ponga; la tarea de cada hora los muda.
EXPEDIENTES_DESTINO=
```

`VAPID_PUBLIC` y `VAPID_PRIVATE` **no van**, ni siquiera vacías: las
escribe el paso 6. Las demás llaves y contraseñas se pegan aquí, en el
servidor, y en ningún otro lado.

**Un cambio en el `.env` no se aplica con `restart`.** `docker compose
restart` vuelve a arrancar el mismo contenedor con los valores de antes;
lo que relee el `.env` es volver a crearlo:

```bash
docker compose -f docker-compose.prod.yml up -d api worker beat
```

**La conexión con Odoo.** El usuario «Centauro (conexión)» se crea en
Odoo con permiso de *Empleados: Oficial* —para leer el correo personal
y la referencia— y ocupa una licencia. Su llave se genera en su perfil
→ *Seguridad de la cuenta* → *Claves API*, con el vencimiento más largo
que Odoo permita (tres meses). **Anota el día que vence**: ese día la
lectura se detiene y el registro del worker dice «Odoo rechazó la
llave». La nueva se pega aquí y se aplica con `up -d api worker beat`
(arriba).

La primera lectura del personal y la de la flota se hacen a mano,
después de ver el ensayo; las tareas de cada hora no arrancan hasta que
exista esa primera. Se hacen desde la consola —*Gestión Administrativa →
Odoo*, con administración o dirección general—, que también dice lo que
falta corregir en Odoo y cuándo corrió la última de cada hora. Quien tenga
la terminal del servidor puede hacer lo mismo con el personal así (la
flota, los clientes y los tarifarios solo desde la consola):

```bash
docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py
docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py --aplicar
```

Para la flota, el usuario de la conexión también necesita leer
*Flotilla*, y tener entre sus compañías permitidas las dos de la flota:
CENTAURO ASS (México) y Centauro Brasil (sección 118). Sin la de Brasil,
el ensayo de la flota dice «Brasil 0» aunque sus unidades estén cargadas
en Odoo. Las fotos de las categorías se cargan una vez desde una
carpeta (`fotos_de_categoria.py`, instrucciones adentro): la base de
cada categoría y una por color.

Si alguna vez hace falta una contraseña o clave nueva a mano:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Si `SECRET_KEY` sigue siendo la del código, **la aplicación no arranca**.
Es a propósito: un sistema que enciende igual con o sin secreto se
despliega tarde o temprano sin él.

**3. El DNS.** Las direcciones tienen que apuntar al servidor *antes*
de levantar el proxy: Caddy pide el certificado al arrancar y Let's
Encrypt verifica que el dominio sea tuyo. El dominio es `mycentauro.lat`,
comprado en Akky, con el DNS en Google Cloud DNS (zona `mycentauro-lat`;
en Akky van sus cuatro servidores, `ns-cloud-e1` a `ns-cloud-e4` de
`googledomains.com`). Tres registros **A** hacia `34.51.121.227`: uno
por puerta (sección 71) —`mycentauro.lat`, la consola —*Centauro
Connect*, del personal administrativo y los consultores—, y
`appep.mycentauro.lat`, la app del personal de seguridad —*Protección
Ejecutiva Connect App*—— y `www.mycentauro.lat`, que el `Caddyfile`
manda a la consola (sección 100: quien escribe «www» delante no llegaba
a ningún lado). Las tres llegan al mismo servidor; el `Caddyfile` manda a
cada quien a la suya: la raíz de `appep.` abre la app, la consola que se
pide ahí se abre en `mycentauro.lat`, y la app que se pide en
`mycentauro.lat` se abre en `appep.`. El registro de `www` se crea así, y
la app de otra área, el día que exista, es un registro más y su propio
bloque en el `Caddyfile`:

```bash
gcloud dns record-sets create www.mycentauro.lat. --zone=mycentauro-lat --type=A --ttl=300 --rrdatas=34.51.121.227
gcloud dns record-sets create appXX.mycentauro.lat. --zone=mycentauro-lat --type=A --ttl=300 --rrdatas=34.51.121.227
```

Un cambio en el `Caddyfile` se aplica sin bajar nada: `docker compose -f
docker-compose.prod.yml exec -T proxy caddy reload --config
/etc/caddy/Caddyfile`.

**4. Levantar, todavía sin la puerta a internet.**

```bash
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml up -d db redis
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d api worker beat
```

El proxy va al final (6b): primero tiene que existir la primera cuenta.

**5. Los catálogos y la primera cuenta, una sola vez.**

```bash
docker compose -f docker-compose.prod.yml run --rm api python primer_arranque.py --correo tu@correo.com --nombre "Tu nombre completo"
```

Carga países, plazas, perfiles, categorías de vehículo, modalidades,
tarifario, tabulador, comisiones, festivos, hospitales y hoteles —**sin**
el personal, la flota ni el cliente de ejemplo: en producción la gente y
las unidades llegan de Odoo—. Luego pide la contraseña de esa primera
cuenta, que queda con rol de dirección general; no se ve al escribirla.
Las demás cuentas se dan de alta desde la consola (*Accesos*), cada una
con su invitación. Con cualquier usuario ya creado no hace nada.

Al terminar dice qué revisar en la consola: **los montos de la semilla
son de ejemplo**.

En producción el sembrado por la API (`/sistema/sembrar-catalogos`) no
se abre sin credenciales ni la primera vez, y nunca siembra el personal,
la flota ni el cliente de ejemplo.

**6. Las llaves de los avisos.** Con el `.env` del servidor montado
encima del contenedor: sin el `-v`, el script escribiría en un `.env`
que solo existe dentro de ese contenedor y las llaves se perderían.

```bash
docker compose -f docker-compose.prod.yml run --rm -v "$PWD/.env:/code/.env" api python generar_llaves_push.py
docker compose -f docker-compose.prod.yml up -d api worker beat
```

Escribe las dos en el `.env` y **solo imprime la pública**. Si ya
existen, no las toca: regenerarlas deja mudos todos los teléfonos que ya
se suscribieron, y nadie se entera hasta el día que un aviso importante
no llega.

**6b. Abrir la puerta.** Con la primera cuenta creada y el dominio
apuntando aquí (paso 3):

```bash
docker compose -f docker-compose.prod.yml up -d proxy
```

Caddy saca el certificado en el primer minuto. Si no lo consigue, lo
dice en `docker compose -f docker-compose.prod.yml logs proxy`.

**7. La llave de Google.** Restringida por **IP del servidor** —no por
referrer—, con **solo** Places API (New) y Maps Static API habilitadas, y
con **cuota diaria**. Sin tope, un error en un ciclo se convierte en una
factura.

**7b. El correo, por Microsoft 365 (el que se usa).** Decisión de
Salvador, 29 de septiembre: Amazon SES no aprobó la cuenta y el correo
sale de `connect@centauro.lat`, con la aplicación `Centauro correo
(servidor)` de Entra. Donde abajo dice `ai@centauro.lat`, va
`connect@centauro.lat`. Se enciende por etapas (7e). Sale del buzón `ai@centauro.lat`
y no por SMTP: Microsoft apaga el SMTP con usuario y contraseña el 31 de
diciembre de 2026. Va por Microsoft Graph, con una aplicación registrada
en Entra que **solo puede mandar desde ese buzón**. El DNS no se toca:
el correo de `centauro.lat` ya sale de Microsoft. Conviene confirmar que
DKIM de `centauro.lat` esté activo en Microsoft, porque ayuda a no caer
en correo no deseado.

1. **El buzón.** `ai@centauro.lat` tiene que existir en Microsoft 365. Si
   no existe, como buzón compartido —no gasta licencia—, con acceso para
   quien vaya a leer lo que contesten los clientes.
2. **La aplicación**, en Entra → *Registros de aplicaciones* → *Nuevo
   registro*: nombre `Centauro correo (servidor)`, solo esta
   organización, sin dirección de redirección. De su página salen el
   *Id. de directorio (inquilino)* → `CORREO_MS_TENANT` y el *Id. de
   aplicación (cliente)* → `CORREO_MS_CLIENTE`.
3. **El secreto**, en la misma aplicación → *Certificados y secretos* →
   *Nuevo secreto de cliente*, con el vencimiento más largo (24 meses).
   Se copia el **Valor** —no el Id. del secreto—, se ve una sola vez y se
   pega directo en el `.env` del servidor → `CORREO_MS_SECRETO`. Nunca
   por correo ni por chat. **Anota el día que vence**: ese día el correo
   deja de salir y `probar_correo.py` dice «AADSTS7000222». El nuevo se
   pega aquí y se aplica con `up -d api worker beat` (paso 2).
4. **Sin permisos de Graph en Entra.** A la aplicación **no** se le
   agrega `Mail.Send` en *Permisos de API*: con ese permiso podría mandar
   como cualquier persona de la empresa, incluida dirección general. El
   permiso lo da Exchange, solo sobre `ai@centauro.lat`, desde PowerShell
   con una cuenta de administración de Exchange. El *Id. de objeto* es el
   de *Aplicaciones empresariales*, no el de *Registros de aplicaciones*:
   son distintos.

   ```powershell
   Connect-ExchangeOnline
   New-ServicePrincipal -AppId <Id. de aplicacion> -ObjectId <Id. de objeto> -DisplayName "Centauro correo"
   New-ManagementScope -Name "Solo ai@centauro.lat" -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'ai@centauro.lat'"
   New-ManagementRoleAssignment -App <Id. de objeto> -Role "Application Mail.Send" -CustomResourceScope "Solo ai@centauro.lat"
   Test-ServicePrincipalAuthorization -Identity <Id. de objeto> -Resource ai@centauro.lat
   ```

   La última tiene que decir `InScope: True`; contra cualquier otro
   buzón, `False`. Exchange tarda hasta dos horas en aplicarlo.
5. **Probarlo**, con los tres datos en el `.env`:

   ```bash
   docker compose -f docker-compose.prod.yml up -d api worker beat
   docker compose -f docker-compose.prod.yml run --rm api python probar_correo.py tu@correo.com
   ```

   Dice por dónde salió y, si no salió, lo que contestó Microsoft. Antes
   de soltar la cola, `GET /sistema/correo` —en `/docs`, con una cuenta
   de administración— dice cuántos avisos esperan y cuántos ya no
   saldrían por viejos.

**7c. El correo, por Amazon SES (la otra forma; no aprobó la cuenta).** Decisión de
Salvador, 27 de septiembre: los avisos salen de un servicio de envío,
para no depender de nadie. Salen de `connect@mycentauro.lat` y lo que
contesten llega a `cecc.notification@centauro.lat`. El dominio y su DNS
son de Centauro (Google Cloud DNS, zona `mycentauro-lat`), y el sistema
manda por SMTP, que ya sabía: no se programa nada. MailerSend rechazó la
cuenta dos veces y Postmark no aceptó el dominio («Public domains are not
allowed»); se quedó Amazon SES (sección 93). Google Cloud no tiene un
servicio de correo propio. La cuenta es de Ohio (`us-east-2`), la región
en la que abre su consola; Amazon no manda correo desde su región de
México. Todo lo de SES —el dominio, la llave y la aprobación— es de esa
región y de ninguna otra.

1. **La cuenta de AWS**, en aws.amazon.com, **con un correo de
   centauro.lat**, a nombre de «Centauro» y en el **plan de pago**: el
   gratis cierra la cuenta a los seis meses y el correo dejaría de salir.
   Al usuario raíz se le pone el segundo candado (MFA). Precio, a
   septiembre de 2026: la cuenta nueva empieza en el plan Essentials, 0.16
   dólares por cada mil correos y sin cuota; unos 1.60 al mes con 10,000.
   Se puede pasar al cobro por uso, a 0.10.
2. **El dominio**: arriba a la derecha, la región *Ohio*. En SES, el
   asistente de la primera vez —o *Identities → Create identity →
   Domain*—, `mycentauro.lat`, con *Easy DKIM* (RSA 2048); el MAIL FROM
   propio se pone al final de este paso. En el plan de precios, Essentials;
   los pasos opcionales se saltan, y el seguimiento de aperturas y clics
   y la validación automática se quedan apagados: el primero reescribe
   las ligas de los correos y la segunda deja de mandar, sin avisar, a
   los correos que le parecen dudosos.
   Amazon da tres `CNAME` que terminan en `._domainkey`; ninguno es
   secreto. Se ponen desde **Cloud Shell**, la terminal de Google en el
   navegador (`https://console.cloud.google.com/?cloudshell=true`),
   **afuera** del servidor —la Mac no tiene `gcloud`—, con los valores que
   da Amazon, y de paso se quitan los de MailerSend:

   ```bash
   P=project-8fda7c0c-0799-4989-9c2; Z=mycentauro-lat
   gcloud dns record-sets list --zone=$Z --project=$P --format="table(name,type,rrdatas)"
   gcloud dns record-sets create <token1>._domainkey.mycentauro.lat. --zone=$Z --project=$P --type=CNAME --ttl=3600 --rrdatas=<token1>.dkim.amazonses.com.
   gcloud dns record-sets create <token2>._domainkey.mycentauro.lat. --zone=$Z --project=$P --type=CNAME --ttl=3600 --rrdatas=<token2>.dkim.amazonses.com.
   gcloud dns record-sets create <token3>._domainkey.mycentauro.lat. --zone=$Z --project=$P --type=CNAME --ttl=3600 --rrdatas=<token3>.dkim.amazonses.com.
   gcloud dns record-sets delete ms1._domainkey.mycentauro.lat. --zone=$Z --project=$P --type=CNAME
   gcloud dns record-sets delete ms2._domainkey.mycentauro.lat. --zone=$Z --project=$P --type=CNAME
   gcloud dns record-sets delete mta.mycentauro.lat. --zone=$Z --project=$P --type=CNAME
   ```

   El SPF de la raíz, el de MailerSend, ya no sirve: Amazon no usa la
   raíz como remitente del sobre (Return-Path), sino el suyo
   (`amazonses.com`) o el subdominio de abajo. Se cambia por uno que diga
   que nadie más manda como `mycentauro.lat`, solo si ese TXT no trae
   nada más:

   ```bash
   gcloud dns record-sets update mycentauro.lat. --zone=$Z --project=$P --type=TXT --ttl=3600 --rrdatas='"v=spf1 -all"'
   ```

   DMARC se queda como está. SES marca el dominio como *Verified* cuando
   lee los tres registros: minutos, y hasta 72 horas.

   **El remitente del sobre (MAIL FROM propio).** Sin él, SES lo marca
   como recomendación de impacto alto, «El registro MAIL FROM no está
   alineado»: el Return-Path es de `amazonses.com`, así que el SPF no
   cuenta para DMARC y DMARC pasa solo por el DKIM. Con él pasan los dos.
   En la identidad `mycentauro.lat` → *Autenticación* → *Dominio MAIL FROM
   personalizado* → *Editar*: `envio`, y en *Comportamiento ante error de
   MX*, *Utilizar dominio MAIL FROM predeterminado*: si el registro
   faltara, el correo sigue saliendo como antes. Amazon enseña dos
   registros, que se ponen desde Cloud Shell (el `MX` es de la región):

   ```bash
   P=project-8fda7c0c-0799-4989-9c2; Z=mycentauro-lat
   gcloud dns record-sets create envio.mycentauro.lat. --zone=$Z --project=$P --type=MX --ttl=3600 --rrdatas="10 feedback-smtp.us-east-2.amazonses.com."
   gcloud dns record-sets create envio.mycentauro.lat. --zone=$Z --project=$P --type=TXT --ttl=3600 --rrdatas='"v=spf1 include:amazonses.com ~all"'
   ```

   `envio` no recibe correo: su `MX` solo lleva los rebotes a Amazon.
   Cuando SES ve el registro, el aviso azul de la identidad se quita; la
   tabla de recomendaciones no se pone al día sola: se pica *Comprobar si
   hay recomendaciones*. La de BIMI (impacto bajo) se deja: es el logo
   junto al correo en Gmail, y pide DMARC estricto y un certificado del
   logo que se paga cada año.
3. **La cuenta a prueba (sandbox).** Una cuenta nueva solo manda a
   correos verificados, hasta 200 al día, y al buzón de pruebas de
   Amazon, `success@simulator.amazonses.com`, que recibe y tira. Para
   probar con un correo de verdad: *Identities → Create identity → Email
   address*, y se pica el enlace que llega. Amazon no vuelve a mandar a
   un correo que rebotó o que se quejó: la lista de supresión de la
   cuenta viene encendida para las dos cosas.
4. **La llave**: SES → *SMTP settings → Create SMTP credentials*. Crea un
   usuario de IAM y da un usuario y una contraseña SMTP, que se ven **una
   sola vez**: se baja el `.csv` y se guarda. Sirven solo en esa región.
   No se mandan por correo ni por chat: se pegan en el servidor, dentro,
   con

   ```bash
   cd /opt/centauro && python3 despliegue/poner_correo.py
   ```

   que escribe los renglones del correo en el `.env` y pide el usuario y
   la contraseña; la contraseña no se ve al pegarla. Se puede volver a
   correr el día que haya otra llave. Google Cloud no deja salir el
   puerto 25; el 587 sí, y es el que se usa.
5. **Probarlo sin encenderlo.** Poner la llave no enciende el correo del
   sistema: queda `CORREO_ENCENDIDO=no` y los avisos esperan en la cola.
   La prueba sale igual. Primero al buzón de pruebas y después a un
   correo verificado, que tiene que llegar:

   ```bash
   docker compose -f docker-compose.prod.yml run --rm api python probar_correo.py success@simulator.amazonses.com
   ```

   Dice por dónde salió, desde qué dirección y a dónde irán las
   respuestas; si no salió, lo que contestó Amazon. Un 535 es la llave
   equivocada o de otra región; «Email address is not verified» es la
   cuenta todavía a prueba, escribiéndole a un correo sin verificar.
6. **El acceso a producción**: SES → *Account dashboard → Request
   production access*: *Transactional*, `https://centauro.lat`, y, si lo
   piden, el uso, en inglés: el texto está en la bitácora, sección 93.
   Amazon contesta en unas 24 horas. Con una cuenta nueva puede no
   aprobar de entrada: en *Prepárese* el estado dice «Se necesita más
   información» y abre un caso en el centro de soporte, donde pregunta
   cada cuánto se manda, de dónde salen los correos, qué se hace con
   rebotes, quejas y bajas, y pide ejemplos. Se contesta en el mismo caso,
   con *Responder*; la respuesta que se mandó está en la bitácora. La
   aprobación es por región.
7. **Encenderlo, ya aprobado.** Antes no: con la cuenta a prueba, Amazon
   rechazaría los avisos a clientes y cada uno gastaría sus cinco
   intentos y quedaría en fallido. `--encender` no enciende sin la llave
   puesta:

   ```bash
   python3 despliegue/poner_correo.py --encender && docker compose -f docker-compose.prod.yml up -d api worker beat && docker compose -f docker-compose.prod.yml run --rm api python probar_correo.py cecc.notification@centauro.lat
   ```

   Con el interruptor, las actualizaciones se pueden subir en cualquier
   momento: el `up -d` de cada una no enciende nada que no diga `si`. Se
   apaga igual, con `--apagar` y el mismo `up -d`.

**7d. La otra forma: Postmark o MailerSend.** Si algún día se cambia de
servicio, la llave se pone con `poner_correo.py --postmark` —Postmark da
una sola llave, el *Server API Token*, que va de usuario y de
contraseña— o con `--mailersend`, con usuario y contraseña. Postmark pide
un DKIM (un `TXT` que termina en `._domainkey`) y un Return-Path (un
`CNAME` hacia `pm.mtasv.net`), y se prueba con su buzón que recibe y
tira, `test@blackhole.postmarkapp.com`. El 27 de septiembre Postmark no
aceptó `mycentauro.lat` («Public domains are not allowed»): antes habría
que resolverlo con su soporte.


**7e. Encender por etapas.** Decisión de Salvador, 29 de septiembre:
primero solo la gente de la empresa —consultores, central, personal de
seguridad y oficina, sin importar el dominio de su correo— y después
también los clientes (quien solicita y el ejecutivo). En la primera
etapa, lo de los clientes espera en la cola y, pasado su tiempo de vida,
se vence sin salir. Antes de encender, mira la cola (`GET
/sistema/correo`: `saldrian`, y en la primera etapa `retenidos`).

```bash
cd /opt/centauro && python3 despliegue/poner_correo.py --solo-internos && docker compose -f docker-compose.prod.yml up -d api worker beat
```

La segunda etapa, cuando ya se vio que los correos salen bien:

```bash
cd /opt/centauro && python3 despliegue/poner_correo.py --a-todos && docker compose -f docker-compose.prod.yml up -d api worker beat
```

`--apagar` apaga todo, en la etapa que sea. El estado del sistema, en el
manual, dice «Solo a la empresa» mientras dure la primera etapa.

**8. El respaldo.** En el cron del servidor, no en Celery: si la
aplicación está caída es justo cuando más falta hace. En Google Cloud,
la copia va al depósito del proyecto con la cuenta de la máquina y sin
llaves. El destino se escribe solo, leyendo el proyecto de la propia
máquina:

```bash
cd /opt/centauro
grep -q '^RESPALDO_GCS_DESTINO=' .env || echo "RESPALDO_GCS_DESTINO=gs://centauro-respaldos-$(curl -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)/postgres" >> .env
```

Córrelo **a mano una vez** y lee la salida completa antes de confiar en
él:

```bash
sudo /opt/centauro/despliegue/respaldo.sh
```

Y cada noche a las 2:30, antes de la foto del disco de las 3:00, con su
registro rotado cada mes:

```bash
echo '30 2 * * * root /opt/centauro/despliegue/respaldo.sh >> /var/log/centauro-respaldo.log 2>&1' | sudo tee /etc/cron.d/centauro-respaldo
printf '/var/log/centauro-respaldo.log {\n  monthly\n  rotate 12\n  compress\n  missingok\n  notifempty\n}\n' | sudo tee /etc/logrotate.d/centauro-respaldo
```

El resultado de cada noche queda también en el registro del sistema
(`centauro-respaldo`): de ahí lo lee el agente de Google, y de ahí sale
la alerta si una noche falla.

**9. Las contraseñas sembradas.** Con `primer_arranque.py` no hay
ninguna: cada cuenta pone la suya. Si la base se armó con la semilla de
demostración, cambiarlas antes de repartir accesos.

---

## El respaldo se verifica solo

`respaldo.sh` no se limita a sacar el `pg_dump`. Hace tres cosas más, y
son las que lo convierten en un respaldo:

1. **Lo restaura** en una base desechable dentro del mismo Postgres.
2. **Cuenta las filas** de las cuatro tablas que de verdad duelen
   —servicios, viáticos, fotos de revisión y nómina—.
3. **Compara el contenido de las fotos**, no solo cuántas son: un md5
   por imagen y un md5 del conjunto. Es la diferencia entre *"llegaron
   240 filas"* y *"llegaron las mismas 240 fotos"*. Las imágenes viven
   dentro de la base y son lo que se usa para discutir un golpe tres
   semanas después; una fila que llega con la imagen cortada cuenta
   igual y no sirve de nada.

Y comprueba que la copia traiga la versión de alembic: una base
restaurada sin esa marca se abre, pero ya no se puede seguir migrando.

Si algo no cuadra, **no borra ningún respaldo viejo** y sale con error.

Un respaldo que nadie ha restaurado no es un respaldo, es un archivo
grande.

### Probarlo sin ser el servidor

```bash
./despliegue/respaldo.sh --probar
```

Saca el respaldo de la base que esté encendida —en la máquina de
desarrollo, la de `docker-compose.yml`—, lo restaura en una base
desechable, verifica las cuatro tablas y las fotos, y **borra todo al
terminar**. No rota nada, no sube nada y no toca los respaldos de
verdad.

Es lectura: la base de trabajo no se modifica. Lo único que crea es una
base temporal `verificacion_<fecha>` que se borra sola, pase lo que
pase.

Vale la pena correrlo **antes** de que haya datos reales, para ver con
los propios ojos que el ciclo cierra. Un script de respaldo que solo
corre en el servidor es un script que nadie prueba hasta el día que
hace falta.

### La copia fuera del servidor

Es lo único que protege del caso que de verdad importa: perder el
servidor. Un respaldo en el mismo disco que la base no es un respaldo,
es una copia.

**En Google Cloud** va al depósito del proyecto (arriba), con
`RESPALDO_GCS_DESTINO` en el `.env`. La sube `backend/subir_a_google.py`
con la cuenta de la propia máquina: el permiso se le pide a Google en
cada subida y no hay llave guardada que alguien se pueda llevar. Sube por
partes, sigue desde donde se quedó si se corta, nunca escribe encima de
un respaldo que ya exista y al final **pregunta el tamaño y el md5 de lo
que llegó** y los compara con el archivo. Los dos candados de abajo ya
están puestos del lado de Google: la cuenta de la máquina no puede
borrar y el depósito no deja borrar ni reemplazar nada antes de 14 días.

Para ver lo que hay allá, en Cloud Shell:

```bash
gcloud storage ls -l gs://centauro-respaldos-project-8fda7c0c-0799-4989-9c2/postgres/
```

**Fuera de Google** va a **object storage S3 multizona**. En el `.env`:

```
RESPALDO_S3_DESTINO=s3://centauro-respaldos/postgres
RESPALDO_S3_ENDPOINT=https://s3.us-west-1.amazonaws.com   # opcional
RESPALDO_S3_REGION=us-west-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

Se sube con la imagen oficial del cliente de AWS, así que el servidor no
necesita instalar nada; y con `--endpoint-url` sirve igual con cualquier
proveedor compatible con S3.

El script sube y luego **pregunta cuánto pesa del otro lado y lo
compara**. Una subida que contesta "ok" y se cortó a la mitad es un
respaldo que no existe.

**Dos cosas del lado del bucket, y las dos importan más que el script:**

**1. La credencial del servidor no debe poder borrar.** Solo
`PutObject`. Si alguien entra al servidor, se lleva estas llaves; con
permiso de borrado se lleva también todo el historial de respaldos, que
es exactamente lo que se iba a usar para recuperarse. Es el patrón
clásico del ransomware y la razón por la que muchas empresas descubren
que no tenían respaldos justo el día que los necesitaban.

**2. Versionado y Object Lock (WORM), con regla de ciclo de vida.** La
rotación remota la hace el bucket, no el script. Si el script pudiera
borrar allá, volveríamos al punto uno.

Localmente se guardan 14 días; allá, lo que diga la regla del bucket.

---

## El archivo de los comprobantes

Sección 69 de la bitácora; la propuesta, con sus pantallas, es
`PROPUESTA_ARCHIVO_COMPROBANTES.md`. Tres meses después de la factura
—o de la aprobación de finanzas, mientras Odoo no esté conectado—, la
foto del ticket y la de la devolución salen de la base y se van a un
depósito de Google, donde se guardan seis años. **La foto se muda; el
registro se queda.**

Lo hace el worker cada noche a la **1:30**, antes del respaldo de las
2:30: lo que se muda esa noche ya no viaja en ese respaldo. Cada foto
sube sin escribir encima de nada, se le pregunta a Google qué recibió
—tamaño y md5— y solo si cuadra se quita de la base. Si algo falla, la
foto se queda y se reintenta la noche siguiente. Como mucho 3,000 fotos
por noche.

**Nace apagado.** Para prenderlo:

1. En Cloud Shell, el contenido de `gcp/crear_archivo.sh`. Arma el
   depósito —clase Archive, en EE. UU., sin acceso público—, el candado
   de seis años **sin sellar**, el borrado a los seis años, el permiso
   de la máquina (guardar y leer, no borrar) y la alerta *Centauro:
   falló el archivo*. Al final dice el renglón del `.env`.
2. En el servidor, `nano .env` y el renglón `ARCHIVO_DESTINO=...`.
3. `docker compose -f docker-compose.prod.yml up -d api worker beat`.

El worker lleva montado el syslog de la máquina (`/dev/log`, en
`docker-compose.prod.yml`): ahí escribe una línea cada noche, con la
etiqueta `centauro-archivo`, y si dice ERROR llega el correo, igual que
con el respaldo.

**El candado se sella** cuando el contador confirme el plazo. El Código
Fiscal (art. 30) pide cinco años contados desde la declaración anual;
seis desde que se archiva los cubren siempre. **Sellado ya no se puede
acortar ni quitar, ni por nosotros**, así que se hace una vez y a
propósito, en Cloud Shell:

```bash
gcloud storage buckets update gs://centauro-archivo-project-8fda7c0c-0799-4989-9c2 --lock-retention-period
```

**Ver qué hay**, en Cloud Shell:

```bash
gcloud storage ls -l "gs://centauro-archivo-project-8fda7c0c-0799-4989-9c2/comprobantes/**" | tail -20
```

---

## Los expedientes del freelance

Sección 111 de la bitácora. Los PDF y las fotos del expediente del
freelance —INE, antecedentes, pruebas toxicológicas, la carátula del
banco— van a un depósito privado de Google, **en México**
(`northamerica-south1`, junto a la máquina), y solo se abren desde
Connect, con permiso: Recursos Humanos, dirección de operaciones y
dirección general.

Cada archivo sube sin escribir encima de nada, se le pregunta a Google
qué recibió —tamaño y md5— y solo si cuadra se quita de la base. Si
Google no contesta al subirlo, se queda en la base y la tarea de cada
hora (a los :23) lo vuelve a intentar.

**Sin borrado automático ni candado**, a propósito: se guardan mientras
el freelance colabore y seis años después de su último servicio
(decisión 7 de Salvador), y un reloj del depósito solo sabe contar desde
el día en que se subió cada archivo. Connect no borra nada; la cuenta de
la máquina no puede borrar.

**Nace apagado.** Mientras no se ponga, los archivos se quedan en la
base (y en su respaldo de cada noche). Para prenderlo:

1. En Cloud Shell, el contenido de `gcp/crear_expedientes.sh`. Arma el
   depósito y el permiso de la máquina (guardar y leer, no borrar). Al
   final dice el renglón del `.env`.
2. En el servidor, el renglón `EXPEDIENTES_DESTINO=...` en `.env`.
3. `docker compose -f docker-compose.prod.yml up -d api worker beat`.

Cada foto lleva su folio, persona, monto y fecha pegados como datos:
el archivo se entiende solo aunque Centauro no estuviera.

**Desde la consola**, en *Facturación → Historial*: cada servicio dice
cuántas fotos siguen en Centauro y cuándo se van, o cuándo se fueron.
Una foto archivada la traen de vuelta dirección general y finanzas con
*Ver del archivo*; cada vez queda en la bitácora del servicio y se
compara su md5 con el que se guardó.

**Las copias de respaldo** de las noches anteriores todavía traen cada
foto hasta 90 días después de archivada (el depósito de respaldos borra
a los 90). Después, solo existe en el archivo.

**El desglose de gastos** que se le manda al cliente con la factura lleva
las fotos mientras están en Centauro. Uno que se vuelva a sacar después
de archivarlas sale sin ellas: se traen del archivo.

---

## Qué mirar cuando algo falle

```bash
# Como van los seis procesos
docker compose -f docker-compose.prod.yml ps

# La api, el worker, el proxy
docker compose -f docker-compose.prod.yml logs -f --tail=100 api

# La api se ve a si misma, a la base y a Redis
docker compose -f docker-compose.prod.yml exec -T api \
  python -c "import urllib.request,json; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/health')))"

# Como salio el respaldo de las ultimas noches
sudo tail -40 /var/log/centauro-respaldo.log
journalctl -t centauro-respaldo --since "7 days ago"

# Como salio el archivo de los comprobantes
journalctl -t centauro-archivo --since "7 days ago"

# Lo que falta o esta mal cargado en Odoo, por area (seccion 89): los
# cinco ensayos de la pantalla de Odoo, en la terminal. No guarda nada.
docker compose -f docker-compose.prod.yml run --rm api python lo_que_falta_en_odoo.py

# El reloj: el que marca la hora (beat) y el que hace el trabajo (worker)
docker compose -f docker-compose.prod.yml logs --tail=100 beat worker
```

**Lo primero, desde la consola**: *Gestión Administrativa → Manual del
sistema → Cuando algo se atora* dice cómo están la base, el reloj, el
correo, Odoo, el GPS y los avisos al teléfono, y *Lo que el sistema hace
solo* dice la última vuelta de cada tarea (sección 90). Casi siempre
basta con eso para saber por dónde empezar.

**Si el manual dice que el reloj está parado** —ninguna tarea terminó en
los últimos 12 minutos: los correos no salen, los cierres no avanzan,
Odoo y el GPS no se leen—, se revisan los procesos de arriba y se vuelve
a levantar el reloj. No toca la base ni la api:

```bash
if [ "$(hostname)" = "centauro" ]; then cd /opt/centauro && docker compose -f docker-compose.prod.yml up -d redis worker beat && docker compose -f docker-compose.prod.yml ps; else echo "ALTO: este bloque va dentro del servidor. Primero entra con el bloque de ssh."; fi
```

Si vuelven a caerse, sus `logs` dicen por qué.

**Si la app de campo deja de funcionar en los teléfonos**, lo primero
que hay que mirar es el certificado. Sin HTTPS válido no hay service
worker, ni cámara, ni ubicación, ni avisos: la app no existe. Caddy lo
renueva solo, y si no pudo, avisa al correo del `Caddyfile`.

**Si nadie puede entrar**, mira Redis. El límite de intentos fallidos se
apoya en él, pero está escrito para **abrirse**, no para cerrarse, si
Redis no contesta: un candado que depende de un servicio que puede
caerse dejaría a toda la operación sin trabajar justo el día malo.

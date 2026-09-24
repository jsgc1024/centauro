# Despliegue

Lo que hay aquí y para qué sirve. El detalle de por qué cada cosa está
así vive en `ARQUITECTURA.md`, en la raíz.

| Archivo | Qué es |
|---|---|
| `../docker-compose.prod.yml` | Los seis procesos de producción |
| `Caddyfile` | El proxy con TLS. Saca y renueva el certificado solo |
| `respaldo.sh` | `pg_dump` diario **que se restaura y se cuenta** |

---

## Encender por primera vez

**1. El servidor.** Ubuntu LTS o Debian estable, con Docker y Docker
Compose. Zona horaria en `America/Mexico_City`. Solo los puertos 80 y
443 abiertos al mundo.

**1b. El código llega por git.** El repositorio vive en GitHub
(`jsgc1024/centauro`, privado). El servidor lo clona con una **llave de
despliegue de solo lectura**, no con la cuenta de nadie: si alguien
entra al servidor, con esa llave puede leer el código, pero no
modificarlo ni tocar otros repositorios.

En el servidor, como el usuario que va a operar:

```bash
ssh-keygen -t ed25519 -C "servidor-centauro" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

La línea que imprime se pega en GitHub: repositorio → *Settings* →
*Deploy keys* → *Add deploy key*, título `servidor centauro`, **sin**
marcar *Allow write access*. Luego:

```bash
sudo mkdir -p /opt/centauro && sudo chown "$USER" /opt/centauro
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

**2. El `.env`.** Se edita con `nano`, nunca con `echo` —queda en el
historial de la terminal— y no va al repositorio.

```
DOMINIO=operacion.centauro.lat
POSTGRES_PASSWORD=...
REDIS_PASSWORD=...
DATABASE_URL=postgresql+psycopg://centauro:LA_DE_ARRIBA@db:5432/centauro
REDIS_URL=redis://:LA_OTRA@redis:6379/0
APP_ENV=produccion
SECRET_KEY=...
GOOGLE_MAPS_KEY=...
TELEFONO_CENTRAL=+525550221022
VAPID_PUBLIC=...
VAPID_PRIVATE=...
VAPID_CONTACTO=mailto:operaciones@centauro.lat

# De donde cuelgan los enlaces que van en correos y task sheets.
URL_PUBLICA=https://operacion.centauro.lat

# El correo que sale de la empresa (SMTP). Mientras CORREO_HOST y
# CORREO_DE esten vacios no sale nada: los avisos quedan pendientes.
CORREO_HOST=
CORREO_PUERTO=587
CORREO_USUARIO=
CORREO_CLAVE=
CORREO_DE=Centauro <avisos@centauro.lat>

# Odoo, de salida: la factura del servicio. Vacio = nada sale; el
# cierre se queda en "por facturar" y se manda despues.
ODOO_URL=
ODOO_TOKEN=

# Odoo, de entrada: Centauro lee de ahi al personal de seguridad cada
# hora, y solo lee. La llave es la del usuario «Centauro (conexion)»,
# no la de una persona, y Odoo la da por tres meses como maximo.
ODOO_BASE=https://centauro.odoo.com
ODOO_API_KEY=
```

`VAPID_PUBLIC` y `VAPID_PRIVATE` se dejan vacías al principio: las
escribe el paso 6. Las demás llaves y contraseñas se pegan aquí, en el
servidor, y en ningún otro lado.

**La conexión con Odoo.** El usuario «Centauro (conexión)» se crea en
Odoo con permiso de *Empleados: Oficial* —para leer el correo personal
y la referencia— y ocupa una licencia. Su llave se genera en su perfil
→ *Seguridad de la cuenta* → *Claves API*, con el vencimiento más largo
que Odoo permita (tres meses). **Anota el día que vence**: ese día la
lectura se detiene y el registro del worker dice «Odoo rechazó la
llave». La nueva se pega aquí y se reinician `api`, `worker` y `beat`.

La primera lectura del personal y la de la flota se hacen a mano,
después de ver el ensayo; las tareas de cada hora no arrancan hasta que
exista esa primera. Se hacen desde la consola —*Gestión Administrativa →
Odoo*, con administración o dirección general—, que también dice lo que
falta corregir en Odoo y cuándo corrió la última de cada hora. Quien tenga
la terminal del servidor puede hacer lo mismo así:

```bash
docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py
docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py --aplicar
docker compose -f docker-compose.prod.yml run --rm api python sincronizar_flota.py
docker compose -f docker-compose.prod.yml run --rm api python sincronizar_flota.py --aplicar
```

Para la flota, el usuario de la conexión también necesita leer
*Flotilla*. Las fotos de las categorías se cargan una vez desde una
carpeta (`fotos_de_categoria.py`, instrucciones adentro): la base de
cada categoría y una por color.

Las contraseñas y la clave de sesión:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Si `SECRET_KEY` sigue siendo la del código, **la aplicación no arranca**.
Es a propósito: un sistema que enciende igual con o sin secreto se
despliega tarde o temprano sin él.

**3. El DNS.** El dominio tiene que apuntar al servidor *antes* de
levantar el proxy: Caddy pide el certificado al arrancar y Let's Encrypt
verifica que el dominio sea tuyo.

**4. Levantar.**

```bash
docker compose -f docker-compose.prod.yml up -d db redis
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d api worker beat proxy
```

**5. Los catálogos, una sola vez.** Países, plazas, modalidades,
perfiles, categorías de vehículo.

**6. Las llaves de los avisos.**

```bash
docker compose -f docker-compose.prod.yml exec -T api python generar_llaves_push.py
docker compose -f docker-compose.prod.yml restart api worker beat
```

Escribe las dos en el `.env` y **solo imprime la pública**. Si ya
existen, no las toca: regenerarlas deja mudos todos los teléfonos que ya
se suscribieron, y nadie se entera hasta el día que un aviso importante
no llega.

**7. La llave de Google.** Restringida por **IP del servidor** —no por
referrer—, con **solo** Places API (New) y Maps Static API habilitadas, y
con **cuota diaria**. Sin tope, un error en un ciclo se convierte en una
factura.

**8. El respaldo.** En el cron del servidor, no en Celery: si la
aplicación está caída es justo cuando más falta hace.

```
0 3 * * *  /opt/centauro/despliegue/respaldo.sh >> /var/log/centauro-respaldo.log 2>&1
```

Córrelo **a mano una vez** y lee la salida completa antes de confiar en
él.

**9. Las contraseñas sembradas.** Cambiarlas antes de repartir accesos.

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

Va a **object storage S3 multizona**. Es lo único que protege del caso
que de verdad importa: perder el servidor. Un respaldo en el mismo disco
que la base no es un respaldo, es una copia.

En el `.env`:

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

## Qué mirar cuando algo falle

```bash
# Como van los seis procesos
docker compose -f docker-compose.prod.yml ps

# La api, el worker, el proxy
docker compose -f docker-compose.prod.yml logs -f --tail=100 api

# La api se ve a si misma, a la base y a Redis
docker compose -f docker-compose.prod.yml exec -T api \
  python -c "import urllib.request,json; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/health')))"
```

**Si la app de campo deja de funcionar en los teléfonos**, lo primero
que hay que mirar es el certificado. Sin HTTPS válido no hay service
worker, ni cámara, ni ubicación, ni avisos: la app no existe. Caddy lo
renueva solo, y si no pudo, avisa al correo del `Caddyfile`.

**Si nadie puede entrar**, mira Redis. El límite de intentos fallidos se
apoya en él, pero está escrito para **abrirse**, no para cerrarse, si
Redis no contesta: un candado que depende de un servicio que puede
caerse dejaría a toda la operación sin trabajar justo el día malo.

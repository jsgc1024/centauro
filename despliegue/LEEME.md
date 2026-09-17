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
```

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

`respaldo.sh` no se limita a sacar el `pg_dump`: lo restaura en una base
desechable dentro del mismo Postgres y **cuenta las filas** de las cuatro
tablas que de verdad duelen —servicios, viáticos, fotos de revisión y
nómina. Si algo no cuadra, **no borra ningún respaldo viejo** y sale con
error.

Un respaldo que nadie ha restaurado no es un respaldo, es un archivo
grande.

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

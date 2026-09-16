# Centauro — Arquitectura del sistema

_Para preparar el servidor de producción._
_Levantado leyendo el código. Última revisión: 16 de septiembre de 2026._

---

## En una frase

Un monolito en Python (FastAPI) contra Postgres, con Redis y Celery para lo
que corre solo, y dos frontends de HTML y JavaScript plano que el mismo
servidor entrega. No hay paso de compilación en ninguna parte: lo que está
en el repositorio es lo que corre.

Tamaño actual: **72 tablas**, **71 migraciones**, ~22,900 líneas de Python,
~11,300 de JavaScript, **393 pruebas**.

---

## Lenguajes

| Dónde | Lenguaje | Nota |
|---|---|---|
| Backend | **Python 3.12** | Imagen base `python:3.12-slim` |
| Base de datos | SQL (PostgreSQL 16) | El esquema lo escribe Alembic, no se toca a mano |
| Consola web | JavaScript ES2020, módulos nativos | Sin React, sin build, sin `node_modules` |
| App de campo | Lo mismo, más Service Worker | PWA |
| Estilos | CSS plano | Sin preprocesador |

**No hace falta Node en el servidor.** El navegador carga los módulos `.js`
tal cual salen del repositorio.

---

## Backend

**FastAPI** con **SQLAlchemy 2.0** (estilo `Mapped[]` / `mapped_column`),
**Alembic** para el esquema y **Pydantic v2** para validar.

Todas las versiones están clavadas con `==` en `requirements.txt` —revisado,
ninguna queda a rango:

```
fastapi==0.115.6          uvicorn[standard]==0.34.0
sqlalchemy==2.0.36        psycopg[binary]==3.2.3
alembic==1.14.0           pydantic-settings==2.7.0
celery==5.4.0             redis==5.2.1
pyjwt==2.10.1             bcrypt==4.2.1
python-multipart==0.0.20  httpx==0.28.1
pywebpush==2.0.3          pytest==8.3.4
```

Dos detalles de la imagen, menores pero vale saberlos: `pytest` se instala
también en producción, y `build-essential` se queda dentro de la imagen final
(unos 200 MB de más). Ninguno es un riesgo; los dos se quitan el día que
alguien quiera una imagen más chica.

### Autenticación

JWT firmado con **HS256** contra `SECRET_KEY`. La sesión dura **12 horas**;
las invitaciones para dar de alta usuarios, **72**. El token va en el
encabezado `Authorization`, nunca en la URL.

`revisar_secretos()` corre al arrancar: **si `APP_ENV` no es un entorno de
desarrollo conocido y `SECRET_KEY` sigue siendo la del código, la aplicación
se niega a encender.** Es a propósito. Un sistema que arranca igual con o sin
secreto se despliega tarde o temprano sin él.

---

## Base de datos

**PostgreSQL 16.**

- 72 tablas, con llaves foráneas y `ON DELETE CASCADE` donde corresponde.
- **70 columnas `Numeric`**: todo el dinero es decimal exacto, nunca flotante.
- Sin extensiones exóticas. No usa PostGIS: la distancia de geocerca se
  calcula en Python.
- Alembic con cadena lineal de 71 revisiones. El despliegue corre
  `alembic upgrade head`; la aplicación **no** crea tablas sola.

### Dos cosas del esquema que afectan al servidor

**1. Las imágenes viven dentro de la base.** Fotos de revisión de unidad,
comprobantes de viáticos, firmas y señales de identificación se guardan como
data URI en columnas `Text`, no como archivos ni en un bucket. Es deliberado
—una hoja que se imprime desde un aeropuerto con mala red no puede depender
de un enlace—, pero tiene consecuencias de capacidad:

- El teléfono reduce cada foto a 1600 px y JPEG al 70% antes de subirla:
  unos **300 KB**, que en base64 quedan en **~400 KB** guardados.
- Una revisión de unidad son 4 fotos → **~1.6 MB**. Un servicio con entrega
  y devolución de unidad → **~3 MB**, más los tickets de viáticos.
- **Regla gruesa: 100 servicios al mes con revisión de unidad ≈ 3–4 GB al
  año.** Hay que dimensionar disco y, sobre todo, el respaldo: un `pg_dump`
  completo crece al mismo ritmo.

**2. Las fechas son hora de pared del país del servicio.** Las columnas
`DateTime` son *naive* y guardan la hora local de donde ocurre el servicio.
`app/reloj.py` es el que sabe qué hora es en cada país; nada en el sistema
le pregunta la hora al servidor directamente. La zona horaria del contenedor
sigue siendo `America/Mexico_City`, pero ya no decide nada de operación:
ahora es solo la hora de la casa, la que se usa cuando no hay un país de por
medio (encabezados de pantalla, el calendario de Celery).

---

## Cola y tareas programadas

**Redis 7** como broker y backend de resultados. **Celery 5.4** con dos
procesos separados:

- **worker** — `celery -A app.celery_app.celery worker`
- **beat** — `celery -A app.celery_app.celery beat`

Van aparte para que reiniciar uno no se lleve al otro.

Calendario actual (`app/celery_app.py`, en hora de México):

| Hora | Tarea | Qué hace |
|---|---|---|
| 06:30 | `implantados.abrir_mes_siguiente` | Abre el mes siguiente de los implantados antes de que se acabe el actual |
| 17:00 | `campo.recordar_la_vispera` | Le avisa al equipo que mañana trabaja |

Dos cosas que hay que tener presentes:

- **Beat corre en una sola instancia.** Si algún día la API se escala a
  varios servidores, `beat` se queda en uno solo o dispara todo por duplicado.
- **El calendario de Celery es uno solo, en hora de México.** El recordatorio
  de la víspera sale a las 17:00 de México, o sea a las 19:00 de São Paulo.
  La tarea ya calcula bien el "mañana" de cada país; lo que no está partido
  por país es la hora a la que se dispara. Es un pendiente conocido, no un
  error: el aviso llega, llega dos horas más tarde de lo ideal.

---

## Frontends

Los dos los sirve el mismo FastAPI con `StaticFiles`, con cache desactivado.

**Consola** (`/consola`) — dirección, consultores, central y finanzas.
`index.html` más módulos ES: `api.js`, `servicio.js`, `nomina.js`,
`finanzas.js`, `central.js`, `panorama.js`, `mapa.js`, `catalogos.js`,
`implantado.js`, `consultor.js`, `idioma.js`, `util.js`.

**App de campo** (`/app`) — PWA para el personal en la calle, instalable
desde el navegador. `sw.js` (service worker), `cola.js` (lo que no se pudo
mandar espera y se reintenta), `memoria.js`, `foto.js`, `manifiesto.json`.

**Tres idiomas** (es / en / pt) resueltos en el navegador con `idioma.js`.

> La app de campo **exige HTTPS**. Service Worker, geolocalización, cámara y
> Web Push no funcionan sin certificado válido. No es opcional.

---

## Servicios externos

| Servicio | Uso | Si falla |
|---|---|---|
| **Google Maps Platform** | Places API (New) para buscar el punto de encuentro; Maps Static API para la imagen del task sheet | La búsqueda de direcciones deja de funcionar; el resto sigue |
| **Web Push** | Avisos al teléfono del equipo | Los avisos se pierden en silencio, a propósito: nunca detienen una nómina ni una asignación |
| **Odoo** | Empleados y flota | **Todavía no conectado.** `app/odoo.py` es el único lugar que habrá que tocar |

### Google Maps — cómo se configura la llave

Esto ya está decidido y no debe cambiarse al desplegar:

- La llave vive **solo en el servidor**, en `.env`. El navegador nunca la
  recibe: ni el mapa ni la búsqueda pasan por el cliente con la llave puesta.
- Restringir por **IP del servidor de producción**, no por referrer.
- Habilitar **únicamente** Places API (New) y Maps Static API.
- Poner cuota diaria en la consola de Google. Sin tope, un error en un ciclo
  se convierte en una factura.

---

## Los procesos que corren en el servidor

| Proceso | Imagen | Puerto | Comando |
|---|---|---|---|
| `api` | La del proyecto | 8000 | `uvicorn app.main:app` |
| `db` | `postgres:16` | 5432 | **Solo red interna.** Volumen persistente |
| `redis` | `redis:7-alpine` | 6379 | **Solo red interna** |
| `worker` | La del proyecto | — | `celery ... worker` |
| `beat` | La del proyecto | — | `celery ... beat`. Una sola instancia |

Delante de todo eso hace falta **un proxy inverso con TLS** (Nginx o Caddy):
certificado, redirección de 80 a 443, y `X-Forwarded-For` para que el registro
de auditoría vea la IP real y no la del proxy.

**Solo los puertos 80 y 443 abiertos al mundo.**

---

## El `docker-compose.yml` del repositorio es de DESARROLLO

Esto es lo más importante de este documento. El compose que está en el
repositorio **no se puede subir a un servidor tal cual**. Seis diferencias, y
las seis importan:

| En desarrollo | Por qué no sirve en producción |
|---|---|
| `db` publica `5432:5432` | Postgres queda expuesto a internet |
| `redis` publica `6379:6379` | Redis sin contraseña, expuesto a internet. Es la forma más común de que se cuele un minero |
| `POSTGRES_PASSWORD: centauro_dev` a la vista | La contraseña de la base, en el repositorio |
| `uvicorn --reload` | El recargador vigila el disco, corre en un solo proceso y no está hecho para servir |
| `volumes: ./backend:/code` | Monta el código del disco y le pasa por encima a la imagen: se despliega lo que haya en la carpeta, no lo que se construyó |
| Ningún `restart:` | Un reinicio del servidor deja todo apagado y nadie se entera hasta que llama la central |

### Un `docker-compose.prod.yml` de arranque

```yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: centauro
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: centauro
      TZ: America/Mexico_City
    volumes:
      - pgdata:/var/lib/postgresql/data
    # Sin `ports`: solo la red interna.
    command: >
      postgres -c max_connections=200
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U centauro"]
      interval: 10s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD} --appendonly yes
    volumes:
      - redisdata:/data
    # Sin `ports`.
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 10

  api:
    build: ./backend
    restart: unless-stopped
    environment:
      TZ: America/Mexico_City
    # Sin --reload, y con trabajadores de verdad.
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
             --proxy-headers --forwarded-allow-ips='*'
    # Sin `volumes`: corre la imagen construida, no la carpeta.
    ports:
      - "127.0.0.1:8000:8000"   # solo local; el proxy inverso lo alcanza
    env_file: .env
    depends_on:
      db: {condition: service_healthy}
      redis: {condition: service_healthy}

  worker:
    build: ./backend
    restart: unless-stopped
    environment:
      TZ: America/Mexico_City
    command: celery -A app.celery_app.celery worker --loglevel=warning
    env_file: .env
    depends_on: [db, redis]

  beat:
    build: ./backend
    restart: unless-stopped
    environment:
      TZ: America/Mexico_City
    command: celery -A app.celery_app.celery beat --loglevel=warning
    env_file: .env
    depends_on: [db, redis]

volumes:
  pgdata:
  redisdata:
```

Con Redis protegido por contraseña, `REDIS_URL` cambia a
`redis://:CONTRASEÑA@redis:6379/0`.

---

## Variables de entorno (`.env`)

```
DATABASE_URL=postgresql+psycopg://centauro:CONTRASEÑA@db:5432/centauro
POSTGRES_PASSWORD=CONTRASEÑA
REDIS_PASSWORD=OTRA_CONTRASEÑA
REDIS_URL=redis://:OTRA_CONTRASEÑA@redis:6379/0
APP_ENV=produccion
SECRET_KEY=...
GOOGLE_MAPS_KEY=...
TELEFONO_CENTRAL=+525550221022
VAPID_PUBLIC=...
VAPID_PRIVATE=...
VAPID_CONTACTO=mailto:operaciones@centauro.lat
```

Cómo se generan las que faltan:

```bash
# La clave de sesión
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# Las llaves de avisos: el script las escribe en .env
# y solo imprime la pública.
docker compose exec -T api python generar_llaves_push.py
```

`APP_ENV` con cualquier valor que no sea `local`, `dev`, `desarrollo`,
`test`, `pruebas` o `ci` se trata como producción. Un nombre que nadie
reconozca se trata como producción a propósito.

El `.env` **no se edita con `echo`** —queda en el historial de la terminal—
sino con `nano`. Y no va al repositorio.

---

## Dos cosas más que hay que afinar

**1. El pozo de conexiones contra el número de hilos.** Casi todos los
endpoints son `def` y no `async def` (289 contra 3). FastAPI los corre en un
pozo de hilos de **40**, pero el motor de SQLAlchemy está creado sin
parámetros: **5 conexiones más 10 de desborde = 15**. Con más de 15
peticiones simultáneas que toquen la base, las demás esperan y acaban por
reventar con *pool timeout*. Se arregla en una línea en `app/db.py`:

```python
engine = create_engine(settings.database_url, pool_pre_ping=True,
                       pool_size=20, max_overflow=20, pool_recycle=1800)
```

Con 2 trabajadores de Uvicorn más el worker de Celery, eso son hasta
~120 conexiones: de ahí el `max_connections=200` de Postgres en el compose
de arriba.

**2. El respaldo.** Con las imágenes dentro de la base, el respaldo *es* el
sistema completo: se pierde el `pg_dump` y se pierden las fotos que prueban
en qué estado se entregó una unidad. `pg_dump` diario comprimido, fuera del
servidor, con una restauración de prueba verificada **antes** de que el
sistema tenga datos reales que perder.

---

## Tamaño sugerido para arrancar

| | |
|---|---|
| CPU | 2 núcleos (4 si la central va a tener el tablero abierto todo el día) |
| RAM | 4 GB (Postgres 1 GB, Redis 256 MB, el resto para api + worker) |
| Disco | 40 GB para empezar, **que se pueda ampliar**: crece con las fotos |
| Red | Solo 80 y 443 abiertos |
| Sistema | Ubuntu LTS o Debian estable, con Docker y Docker Compose |
| Zona horaria | `America/Mexico_City`, fija y documentada |

Es un sistema de operación interna, no un sitio público: la carga son
decenas de usuarios concurrentes, no miles. El cuello de botella no va a ser
la CPU, va a ser el disco y el pozo de conexiones.

---

## Orden de encendido

1. Servidor listo, Docker instalado, zona horaria puesta.
2. `.env` completo. `SECRET_KEY` propia — si no, la aplicación no arranca.
3. `docker compose -f docker-compose.prod.yml up -d db redis`
4. `docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head`
5. Sembrar catálogos **una sola vez**.
6. `docker compose -f docker-compose.prod.yml up -d api worker beat`
7. Proxy inverso con TLS y certificado válido.
8. Llave de Google restringida por la IP del servidor, con cuota diaria.
9. Respaldo programado y **una restauración de prueba verificada**.
10. Cambiar las contraseñas de los usuarios sembrados antes de repartir
    accesos.

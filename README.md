# Centauro — Sistema de operacion

Demo local del sistema de servicios de proteccion ejecutiva.
Stack: FastAPI + Celery + Redis + Postgres, todo en Docker.

## Uso diario

    docker compose up -d          # levantar
    docker compose down           # apagar (sin borrar datos)
    ./probar.sh                   # correr las pruebas
    ./migrar.sh aplicar           # aplicar migraciones pendientes

La API queda en http://localhost:8000 y su documentacion viva en
http://localhost:8000/docs — ahi se puede probar todo sin escribir codigo.

## Cuando cambia el modelo de datos

    ./migrar.sh aplicar              # primero, siempre, lo pendiente
    ./migrar.sh nueva "que cambio"   # genera la migracion leyendo los modelos
    ./migrar.sh aplicar              # la aplica

Revisar el archivo generado en `backend/migrations/versions/` antes de
aplicarlo. Dos casos que Alembic no resuelve solo:

- Columna nueva obligatoria en tabla con datos: necesita `server_default`.
- Valor nuevo en una lista existente (un rol, un estatus): necesita
  `ALTER TYPE ... ADD VALUE` escrito a mano.

## Pruebas

    ./probar.sh                   # todas
    ./probar.sh candados          # solo un archivo
    ./probar.sh -k geocerca       # solo las que traen esa palabra

Corren contra `centauro_test`, una base aparte que se limpia sola.
La base de desarrollo no se toca.

## Otros comandos

    ./reiniciar.sh                # borra la base y siembra de cero
    docker compose logs -f api    # ver que esta pasando

Los `probar_*.py` son recorridos narrados del flujo, para ver el sistema
funcionando con ojos humanos. La red de seguridad son las pruebas de
`backend/tests/`.

## La consola

Con los contenedores arriba, abre:

    http://localhost:8000/

Entra con cualquiera de las cuentas de abajo. Lo que ve cada quien
depende de su rol:

    Operacion    todos           concentrado de lo que esta pasando ahora
    Servicios    consultor       cartera, alta, asignacion y task sheet
    Central      central         alertas de panico y proximos a iniciar
    Personal     consultor       calificacion de profesionalismo

La consola es HTML y JavaScript servidos por la misma API, sin
compilacion ni dependencias: los archivos estan en `backend/app/web/` y
se editan en caliente. Usa los mismos colores, tipografia y orden que el
task sheet, a proposito: el consultor arma el documento viendolo igual
que el cliente lo va a recibir.

La encuesta que recibe el cliente tambien vive ahi:

    /encuestas/pagina/{token}     lo que abre el cliente
    /encuestas/correo/{id}        como se ve el correo (requiere sesion)

## Accesos del demo

Todos con la contrasena `centauro2026`. Solo para el demo: en produccion
cada quien crea la suya desde el enlace que recibe por correo.

| Correo | Rol |
|---|---|
| direccion@centauro.lat | Direccion general |
| operaciones@centauro.lat | Direccion de operaciones |
| ana.solis@centauro.lat | Consultor |
| beatriz.roman@centauro.lat | Consultor |
| central@centauro.lat | Central de inteligencia |
| finanzas@centauro.lat | Finanzas |
| juan.ramirez@centauro.lat | Personal de seguridad |
| admin@centauro.lat | Administracion de catalogos |

## Lo que ya hace

- Catalogos y tarifario multipais, con jornadas parametrizables por pais
- Alta de servicios eventuales con modalidad distinta por dia
- Motor de disponibilidad: bloqueo duro, alerta de riesgo y recomendacion
  por plaza
- Viaticos: tabulador, estimado de combustible por kilometros, ventanas de
  transferencia, comprobacion y cierre con cuadre obligatorio
- Ciclo diario con geocerca, ventana de horario y ajuste de la central
- Notificaciones al solicitante y al ejecutivo, con enlace que expira
- Cierre con comparativo contra la cotizacion, revision automatica y
  rentabilidad por servicio
- Servicios implantados con base mensual del calendario y reemplazos
- Estrellas del personal, incidencias con visto bueno, comision del consultor
- Accesos individuales por rol y bitacora de quien hizo que
- Task sheet por equipo, en ingles por defecto y en el idioma local a
  peticion, con hoja imprimible y senal de identificacion en pagina aparte

## Task sheet

    GET  /task-sheets/equipo/{id}/vista-previa    como va quedando
    POST /task-sheets/equipo/{id}/publicar        congela version y comparte
    GET  /task-sheets/equipo/{id}/hoja            hoja imprimible (ingles)
    GET  /task-sheets/equipo/{id}/hoja?idioma=es  en espanol (o pt)
    PUT  /servicios/{id}/senal                    palabra de identificacion
    POST /servicios/{id}/senal/imagen             o una imagen

Cuando el servicio trae un solo equipo, que es lo normal, las mismas rutas
funcionan con /task-sheets/servicio/{id}/...

El logo va en `backend/assets/logo.(svg|png|jpg|webp)` y se incrusta en el
documento. Los colores institucionales estan en `app/tasksheet_html.py`
(#1B1546) y los textos por idioma en `app/textos.py`.

Los telefonos salen siempre con clave lada. La lada vive en el pais
(`+52` Mexico, `+55` Brasil), no en el codigo: lo que el consultor
capture empezando con `+` se respeta tal cual, por si es de otro pais.

## Fotos y datos que vienen de Odoo

La foto del personal y la de la unidad NO se capturan en este sistema:
son de Odoo. Mientras no exista la conexion real, se reciben por:

    POST /odoo/personal   [{correo, nombre, telefono, foto_url}]
    POST /odoo/flota      [{placa, color, modelo_anio, foto_url}]

La llave es el correo del empleado y la placa del vehiculo. Un campo
vacio no borra lo que ya hay. Cuando se conecte Odoo de verdad, lo unico
que cambia es `app/odoo.py`: el resto del sistema ya lee `foto_url` de la
base local y no necesita que Odoo responda al momento de armar la hoja.

Sin fotos cargadas, el task sheet dibuja el recuadro gris en su lugar.

## Lo que falta

Encuestas de satisfaccion, tablero de profesionalismo,
incidencias con boton de panico, app movil, integracion con Odoo,
operacion de Brasil (esquema 12 por 36) y despliegue en OVH.

## Pendientes de datos

Los montos del tarifario, el tabulador de viaticos, las comisiones y los
criterios de estrella son de ejemplo. Falta cargar los reales, incluido
el rendimiento por categoria de vehiculo y los dias festivos que la
empresa paga por costumbre.

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app import models  # noqa: F401  (registra las tablas en Base)
from app import auth
from app.config import (es_desarrollo, puertas_de_la_api, revisar_secretos,
                        settings)
from app.marca import logo_incrustado
from app.db import engine, get_db
from app.routers import (acceso, archivo, bonos, campo, catalogos, central,
                         cierre, contingencia, encuestas, gps, implantados,
                         mapas, nomina, odoo, operacion, panorama,
                         profesionalismo, servicios, solicitantes, tarifarios,
                         tasksheet, viaticos)
from app.seed import (sembrar, sembrar_bonos, sembrar_festivos,
                      sembrar_lugares, sembrar_parametros, sembrar_recursos)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # El esquema lo maneja Alembic, no la aplicacion:
    #   docker compose exec api alembic upgrade head
    #
    # Lo que si se revisa al arrancar son los secretos: un sistema que
    # enciende igual con o sin clave configurada se despliega tarde o
    # temprano sin ella.
    revisar_secretos(settings)
    yield


app = FastAPI(
    title="Centauro API",
    version="0.2.0",
    description="Sistema de operacion de servicios de proteccion ejecutiva.",
    lifespan=lifespan,
    # En desarrollo, `/docs` abierto. En produccion no existe: ver
    # `puertas_de_la_api`.
    **puertas_de_la_api(settings),
)

app.include_router(acceso.router)
app.include_router(catalogos.router, prefix="/catalogos")
app.include_router(solicitantes.router)
app.include_router(servicios.router)
app.include_router(viaticos.router)
app.include_router(operacion.router)
app.include_router(cierre.router)
# Las fotos que ya se fueron al archivo (seccion 69).
app.include_router(archivo.router)
app.include_router(implantados.router)
app.include_router(bonos.router)
app.include_router(tasksheet.router)
app.include_router(odoo.router)
app.include_router(tarifarios.router)
app.include_router(contingencia.router)
app.include_router(nomina.router)
app.include_router(encuestas.router)
app.include_router(profesionalismo.router)
app.include_router(panorama.router)
app.include_router(central.router)
app.include_router(gps.router)
app.include_router(campo.router)
app.include_router(mapas.router)


@app.exception_handler(IntegrityError)
def choque_con_la_base(request: Request, exc: IntegrityError):
    """Traduce los choques de integridad a una respuesta entendible,
    en vez de devolver un error del servidor con la traza."""
    original = getattr(exc, "orig", None)
    detalle = str(getattr(original, "diag", None) and original.diag.message_detail
                  or original or exc)

    if "duplicate key" in str(exc).lower() or "already exists" in detalle.lower():
        mensaje = "Ese registro ya existe"
    elif "violates foreign key" in str(exc).lower():
        mensaje = "El registro hace referencia a algo que no existe"
    elif "null value" in str(exc).lower():
        mensaje = "Falta un dato obligatorio"
    else:
        mensaje = "El dato choca con una regla de la base"

    return JSONResponse(status_code=409,
                        content={"detail": {"mensaje": mensaje,
                                            "detalle": detalle[:300]}})


@app.get("/api", tags=["Sistema"], summary="Ficha de la API")
def root():
    """La raiz la ocupa la consola; esto queda para revisar que la API
    esta arriba."""
    return {"servicio": "Centauro API", "entorno": settings.app_env,
            "docs": "/docs", "consola": "/"}


@app.get("/health", tags=["Sistema"])
def health():
    estado = {"api": "ok", "db": "desconocido", "redis": "desconocido"}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        estado["db"] = "ok"
    except Exception as e:
        estado["db"] = f"error: {e.__class__.__name__}"
    try:
        import redis as redis_lib
        redis_lib.Redis.from_url(settings.redis_url).ping()
        estado["redis"] = "ok"
    except Exception as e:
        estado["redis"] = f"error: {e.__class__.__name__}"
    return estado


@app.post("/sistema/sembrar-catalogos", tags=["Sistema"],
          summary="Cargar los catalogos iniciales")
def sembrar_catalogos(usuario=Depends(auth.usuario_opcional)):
    """Carga paises, plazas, perfiles, vehiculos, modalidades, tarifario,
    tabulador de viaticos y comisiones. Se puede correr varias veces.

    Ya no siembra los accesos. Sembrar accesos reescribe el rol y la
    contrasena de todos los usuarios que existan, y este endpoint
    estuvo abierto sin credenciales: dos peticiones —una para sembrar,
    otra para entrar con la contrasena de demo que la misma respuesta
    regalaba— y cualquiera era director general. Los usuarios de demo
    se crean ahora desde la linea de comandos:

        docker compose exec -T api python -c \
            "from app.seed import sembrar_accesos; print(sembrar_accesos())"
    """
    # La primera vez pasa sin credenciales, y solo la primera: mientras
    # no exista ni un usuario no hay a quien pedirle permiso, y exigirlo
    # dejaba la base recien creada en un circulo —sin catalogos no hay
    # usuarios, sin usuarios no hay admin, sin admin no hay catalogos.
    # En cuanto existe el primer usuario, la puerta se cierra sola.
    #
    # Eso, en la maquina de quien desarrolla. En produccion no hay puerta
    # abierta ni la primera vez (seccion 68): la base nueva la arranca
    # `primer_arranque.py` desde la terminal del servidor, que carga los
    # catalogos y crea la primera cuenta en el mismo paso. Un endpoint
    # que escribe sin credenciales, en un servidor con direccion publica,
    # queda abierto justo el rato en que nadie esta mirando.
    produccion = not es_desarrollo(settings)
    with Session(engine) as db:
        hay_usuarios = db.query(models.Usuario).first() is not None
    if (hay_usuarios or produccion) and (not usuario or usuario.rol != models.Rol.ADMIN):
        if not hay_usuarios:
            raise HTTPException(403, {
                "mensaje": "En produccion la primera vez no se hace por aqui",
                "que_hacer": "En el servidor: python primer_arranque.py "
                             "(ver despliegue/LEEME.md, paso 5)."})
        raise HTTPException(403, {
            "mensaje": "Sembrar catalogos es cosa de administracion",
            "que_hacer": "Entra como admin. Esto ya no es una base nueva."})

    # Los catalogos primero: sin plazas ni perfiles no hay donde poner a
    # nadie.
    catalogos = sembrar()
    # El personal, la flota y el cliente de ejemplo son para probar el
    # motor de disponibilidad, no para una base de verdad: ahi la gente y
    # las unidades llegan de Odoo, y una camioneta con placa inventada en
    # la lista de disponibles termina asignada a un servicio real.
    recursos = (sembrar_recursos() if not produccion else
                "no se siembran: fuera de desarrollo llegan de Odoo")
    return {"resultado": "ok", "catalogos": catalogos, "recursos": recursos,
            "parametros": sembrar_parametros(),
            "festivos": sembrar_festivos(),
            "bonos": sembrar_bonos(),
            "lugares": sembrar_lugares()}


# ================================================================ CONSOLA WEB

WEB = Path(__file__).resolve().parent / "web"

# El estado del correo lo mira quien reparte accesos: es la misma gente
# que responde cuando alguien dice que no le llego nada.
ADMINISTRA = auth.requiere(models.Rol.ADMIN, models.Rol.DIRECTOR_GENERAL)


@app.get("/sistema/logo", tags=["Sistema"], summary="Logo incrustado")
def logo():
    """La consola lo pide una vez y lo reusa: es el mismo del task sheet,
    asi que la pantalla y el documento nunca se ven distintos."""
    return {"logo": logo_incrustado()}


@app.get("/sistema/correo", tags=["Sistema"],
         summary="Como esta la cola de avisos")
def estado_del_correo(db: Session = Depends(get_db),
                      _: models.Usuario = Depends(ADMINISTRA)):
    """Si hay proveedor configurado y cuantos avisos esperan.

    Es lo que se mira cuando alguien dice que no le llego nada: o no hay
    proveedor --y entonces no le llego a nadie-- o el aviso esta ahi con
    su error escrito al lado.

    Y es lo que hay que mirar ANTES de poner las credenciales:
    `saldrian` son los avisos que van a salir en la primera vuelta y
    `viejos` los que ya no --escritos hace mas de `horas_de_vida`--.
    Encender sin mirar este numero es mandar semanas de avisos viejos a
    clientes reales.
    """
    from app import correo
    return correo.estado(db)


@app.post("/sistema/correo/despachar", tags=["Sistema"],
          summary="Sacar los avisos pendientes ahora")
def despachar_correo(db: Session = Depends(get_db),
                     _: models.Usuario = Depends(ADMINISTRA)):
    """La misma vuelta que da el reloj cada cinco minutos, a mano.

    Sirve el dia que se configura el proveedor y no se quiere esperar, y
    sirve para probar que de verdad sale algo antes de confiar en que
    sale solo.
    """
    from app import correo
    return correo.despachar(db)


class ConsolaSinCache(StaticFiles):
    """Los archivos de la consola se sirven sin cache.

    El index ya se servia asi, pero los modulos no: el navegador se
    quedaba con el .js viejo y una correccion no se veia hasta vaciar el
    cache a mano. Un recargar tiene que bastar. En produccion, cuando la
    consola se publique con version en el nombre, esto se cambia por un
    cache largo: ahi el nombre distinto es lo que invalida.
    """

    def file_response(self, *args, **kwargs):
        respuesta = super().file_response(*args, **kwargs)
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta


if WEB.is_dir():
    # Con html=True, /consola/ abre la consola igual que /. Los avisos al
    # telefono del consultor llevan /consola/#/servicio/... y la app de
    # campo manda a /consola/ a quien no es de campo: sin esto los dos
    # caian en un 404. Y desde appep.mycentauro.lat el proxy lo manda a
    # la direccion de la consola (seccion 71).
    app.mount("/consola", ConsolaSinCache(directory=WEB, html=True),
              name="consola")

    # La app del personal de seguridad. Vive en el mismo servidor y usa
    # la misma sesion y los mismos endpoints que la consola, pero es
    # otra cosa: quien la usa esta de pie, con una mano y con prisa.
    CAMPO = WEB / "campo"
    if CAMPO.is_dir():
        app.mount("/app", ConsolaSinCache(directory=CAMPO, html=True),
                  name="app")

    @app.get("/", include_in_schema=False)
    def raiz():
        """La consola. Se sirve sin cache para que un cambio en los
        archivos se vea al recargar, igual que el --reload de la API."""
        return FileResponse(WEB / "index.html",
                            headers={"Cache-Control": "no-store"})

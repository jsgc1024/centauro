from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import models  # noqa: F401  (registra las tablas en Base)
from app.config import settings
from app.marca import logo_incrustado
from app.db import engine
from app.routers import (acceso, bonos, campo, catalogos, central, cierre,
                         contingencia, encuestas, implantados, mapas, nomina,
                         odoo, operacion, panorama, profesionalismo, servicios,
                         solicitantes, tasksheet, viaticos)
from app.seed import (sembrar, sembrar_accesos, sembrar_bonos,
                      sembrar_festivos, sembrar_lugares,
                      sembrar_parametros, sembrar_recursos)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # El esquema lo maneja Alembic, no la aplicacion:
    #   docker compose exec api alembic upgrade head
    yield


app = FastAPI(
    title="Centauro API",
    version="0.2.0",
    description="Sistema de operacion de servicios de proteccion ejecutiva.",
    lifespan=lifespan,
)

app.include_router(acceso.router)
app.include_router(catalogos.router, prefix="/catalogos")
app.include_router(solicitantes.router)
app.include_router(servicios.router)
app.include_router(viaticos.router)
app.include_router(operacion.router)
app.include_router(cierre.router)
app.include_router(implantados.router)
app.include_router(bonos.router)
app.include_router(tasksheet.router)
app.include_router(odoo.router)
app.include_router(contingencia.router)
app.include_router(nomina.router)
app.include_router(encuestas.router)
app.include_router(profesionalismo.router)
app.include_router(panorama.router)
app.include_router(central.router)
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
def sembrar_catalogos():
    """Carga paises, plazas, perfiles, vehiculos, modalidades, tarifario,
    tabulador de viaticos y comisiones. Se puede correr varias veces."""
    return {"resultado": "ok", "catalogos": sembrar(), "recursos": sembrar_recursos(),
            "parametros": sembrar_parametros(),
            "accesos": sembrar_accesos(),
            "festivos": sembrar_festivos(),
            "bonos": sembrar_bonos(),
            "lugares": sembrar_lugares()}


# ================================================================ CONSOLA WEB

WEB = Path(__file__).resolve().parent / "web"


@app.get("/sistema/logo", tags=["Sistema"], summary="Logo incrustado")
def logo():
    """La consola lo pide una vez y lo reusa: es el mismo del task sheet,
    asi que la pantalla y el documento nunca se ven distintos."""
    return {"logo": logo_incrustado()}


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
    app.mount("/consola", ConsolaSinCache(directory=WEB), name="consola")

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

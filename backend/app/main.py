import logging
import re
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DataError, IntegrityError

from app import models  # noqa: F401  (registra las tablas en Base)
from app import auth
from app.config import (es_desarrollo, puertas_de_la_api, revisar_secretos,
                        settings)
from app.marca import logo_incrustado
from app.db import engine, get_db
from app.routers import (acceso, archivo, bitacora_admin, bonos, calidad,
                         campo, catalogos, central, cierre, contingencia,
                         direccion, encuestas, freelance, gps, implantados,
                         manual, mapas, nomina, odoo, operacion, panorama,
                         profesionalismo, servicios, solicitantes,
                         tarifarios, tasksheet, viaticos)
from app.routers import llaves as llaves_router
# Centauro Logistica, AI/LG (seccion 150), en su propio renglon.
from app.routers import lg_catalogos as lg_catalogos_router
from app.routers import cotizaciones as cotizaciones_router
from app.routers import propuestas as propuestas_router
from app.routers import riesgo as riesgo_router
from app.routers import cliente_ci as cliente_ci_router
from app.routers import nivel as nivel_router
from app.routers import lector as lector_router
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

# Lo mas que pesa una peticion: 20 MB. Las fotos ya se recortan a 3 o 4
# MB en su ruta; esto es la puerta de afuera, para que un cuerpo de
# gigabytes a /auth/token --publico-- no se cargue en memoria antes de
# rechazarse. El proxy (despliegue/Caddyfile) pone el mismo tope antes
# de que llegue aqui; este es por si algun dia la API se asoma sin el
# (seccion 100).
TOPE_DE_CUERPO = 20 * 1024 * 1024


class CuerpoConTope:
    """Rechaza con 413 lo que declara pesar mas del tope, sin leerlo."""

    def __init__(self, app, tope: int = TOPE_DE_CUERPO):
        self.app = app
        self.tope = tope

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            for nombre, valor in scope.get("headers", []):
                if nombre == b"content-length" and valor.isdigit() \
                        and int(valor) > self.tope:
                    respuesta = JSONResponse(status_code=413, content={"detail": {
                        "mensaje": "La peticion pesa demasiado",
                        "que_hacer": f"Lo mas que se acepta son "
                                     f"{self.tope // (1024 * 1024)} MB. Si es "
                                     "una foto, tomala con menos resolucion.",
                    }})
                    await respuesta(scope, receive, send)
                    return
        await self.app(scope, receive, send)


app.add_middleware(CuerpoConTope)


# El disparador de Pegasus lleva su secreto en la ruta (seccion 101):
# cada aviso dejaba `POST /gps/pegasus/aviso/<secreto>` en claro en el
# registro de acceso de uvicorn. Con el secreto solo se puede hacer que
# Centauro mire antes, pero es un secreto en un log. Se tapa antes de
# escribirlo, sin dependencias: uvicorn escribe la ruta como argumento
# del renglon, y el filtro la cambia por `***`. El del proxy lo salta el
# `Caddyfile`.
RUTA_CON_SECRETO = re.compile(r"(/gps/pegasus/aviso/)[^\s/?\"]+")


def tapar_secreto(texto: str) -> str:
    return RUTA_CON_SECRETO.sub(r"\1***", texto)


class SinSecretoDePegasus(logging.Filter):
    """Tapa el secreto del disparador en el renglon del access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(tapar_secreto(a) if isinstance(a, str) else a
                                for a in record.args)
        if isinstance(record.msg, str):
            record.msg = tapar_secreto(record.msg)
        return True


logging.getLogger("uvicorn.access").addFilter(SinSecretoDePegasus())

app.include_router(acceso.router)
# Entrar con huella o cara (30 sep). En su propio renglon: la lista de
# arriba la edita cada seccion.
app.include_router(llaves_router.router)
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
app.include_router(bitacora_admin.router)
app.include_router(calidad.router)
app.include_router(manual.router)
# La ventana del director de operaciones (seccion 105).
app.include_router(direccion.router)
# El freelance: su alta, sus costos y su expediente (seccion 111).
app.include_router(freelance.router)
# Centauro Logistica, AI/LG: sus catalogos con vigencia (seccion 150).
app.include_router(lg_catalogos_router.router)
# Cotizaciones: la del eventual que se arma en Connect, su PDF y el
# servicio que nace al autorizarla (seccion 114).
app.include_router(cotizaciones_router.router)
# Y la propuesta del implantado, al lado: su precio especial y el
# implantado que nace al autorizarla (seccion 115).
app.include_router(propuestas_router.router)
# La Central de Inteligencia: el mapa de riesgo y sus eventos
# (seccion 133).
app.include_router(riesgo_router.router)
# El riesgo de fondo: el Nivel Centauro (seccion 138).
app.include_router(nivel_router.router)
app.include_router(lector_router.router)
# Y la app de su cliente (seccion 136), con su propia sesion.
app.include_router(cliente_ci_router.router)


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


@app.exception_handler(DataError)
def dato_que_no_cabe(request: Request, exc: DataError):
    """Un texto mas largo que su columna, o un numero fuera de rango.

    Los esquemas ya topan lo que mas se escribe; esto es la red de
    abajo: sin ella, lo que se escapara salia como error del servidor,
    la consola decia "Error 500" y la app de campo reintentaba la marca
    para siempre (seccion 100). Es un dato del usuario, asi que es 400
    con que hacer, no 500.
    """
    original = getattr(exc, "orig", None)
    texto = str(original or exc).lower()
    if "too long" in texto or "truncat" in texto:
        mensaje = "Un texto es mas largo de lo que cabe"
        que_hacer = "Acortalo: el detalle largo va en la bitacora o en una nota."
    elif "out of range" in texto or "overflow" in texto:
        mensaje = "Un numero esta fuera de rango"
        que_hacer = "Revisa el monto o la cantidad."
    else:
        mensaje = "Un dato no tiene la forma que la base espera"
        que_hacer = "Revisa lo que escribiste y vuelve a intentar."
    return JSONResponse(status_code=400,
                        content={"detail": {"mensaje": mensaje,
                                            "que_hacer": que_hacer}})


# Un dato mal capturado (seccion 101). FastAPI contesta su lista en
# ingles --"Field required. Input should be a valid decimal"-- sin decir
# cual campo, y asi salia en la consola en los tres idiomas. Aqui se
# traduce cada renglon a lo que hay que corregir, con el nombre del
# campo, y se manda ademas en piezas (`errores`: campo, tipo, limite)
# para que la consola lo diga en el idioma de quien mira.
TIPOS_DE_CAPTURA = {
    "missing": "falta",
    "decimal_parsing": "numero", "float_parsing": "numero",
    "decimal_type": "numero", "float_type": "numero",
    "int_parsing": "entero", "int_type": "entero", "int_from_float": "entero",
    "string_too_long": "largo", "string_too_short": "corto",
    "too_long": "largo", "too_short": "corto",
    "greater_than_equal": "minimo", "greater_than": "mas_de",
    "less_than_equal": "maximo", "less_than": "menos_de",
    "date_parsing": "fecha", "date_from_datetime_parsing": "fecha",
    "date_type": "fecha", "datetime_parsing": "fecha",
    "datetime_from_date_parsing": "fecha", "datetime_type": "fecha",
    "time_parsing": "hora", "time_type": "hora",
    "enum": "opcion", "literal_error": "opcion",
    "string_type": "texto", "list_type": "lista",
    "json_invalid": "cuerpo", "missing_argument": "cuerpo",
    "value_error": "regla", "assertion_error": "regla",
}

FRASES_DE_CAPTURA = {
    "falta": "Falta el dato «{campo}».",
    "numero": "«{campo}» tiene que ser un número.",
    "entero": "«{campo}» tiene que ser un número entero.",
    "largo": "«{campo}» es demasiado largo: caben {limite} letras.",
    "corto": "«{campo}» es demasiado corto: mínimo {limite} letras.",
    "minimo": "«{campo}» tiene que ser de {limite} o más.",
    "mas_de": "«{campo}» tiene que ser más de {limite}.",
    "maximo": "«{campo}» no puede pasar de {limite}.",
    "menos_de": "«{campo}» tiene que ser menos de {limite}.",
    "fecha": "«{campo}» no es una fecha válida.",
    "hora": "«{campo}» no es una hora válida.",
    "opcion": "«{campo}» no es una opción válida.",
    "texto": "«{campo}» tiene que ser un texto.",
    "lista": "«{campo}» tiene que ser una lista.",
    "cuerpo": "Lo que se mandó no se pudo leer.",
    "regla": "«{campo}»: {detalle}",
    "otro": "«{campo}»: {detalle}",
}


def _limite_de(error: dict):
    ctx = error.get("ctx") or {}
    for llave in ("max_length", "min_length", "ge", "gt", "le", "lt"):
        if llave in ctx:
            valor = ctx[llave]
            # "ge=0" se lee "de 0 o mas"; "gt=0" es "mas de 0": se dice
            # como el minimo que no pasa.
            return str(valor)
    return None


def renglon_de_captura(error: dict) -> dict:
    """Un error de Pydantic, en piezas y con su frase en espanol."""
    tipo = TIPOS_DE_CAPTURA.get(error.get("type", ""), "otro")
    campo = "" if tipo == "cuerpo" else ".".join(
        str(x) for x in error.get("loc", ())
        if x not in ("body", "query", "path", "header"))
    detalle = str(error.get("msg", ""))
    for prefijo in ("Value error, ", "Assertion failed, "):
        if detalle.startswith(prefijo):
            detalle = detalle[len(prefijo):]
    limite = _limite_de(error)
    frase = FRASES_DE_CAPTURA[tipo].format(campo=campo or "?", limite=limite or "",
                                           detalle=detalle)
    return {"campo": campo, "tipo": tipo, "limite": limite,
            "detalle": detalle, "mensaje": frase}


@app.exception_handler(RequestValidationError)
async def dato_mal_capturado(request: Request, exc: RequestValidationError):
    renglones = [renglon_de_captura(e) for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": {
        "mensaje": " ".join(r["mensaje"] for r in renglones)
                   or "Un dato no tiene la forma esperada.",
        "que_hacer": "Corrige el dato y vuelve a guardar.",
        "errores": [{k: v for k, v in r.items() if k != "mensaje"}
                    for r in renglones],
    }})


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

    # La app del cliente de la Central de Inteligencia (seccion 136). En
    # produccion vive en su propia direccion, ci.mycentauro.lat, que el
    # proxy manda aqui: otra direccion, otra sesion y otra app instalada.
    CI = WEB / "ci"
    if CI.is_dir():
        app.mount("/ci", ConsolaSinCache(directory=CI, html=True), name="ci")

    @app.get("/", include_in_schema=False)
    def raiz():
        """La consola. Se sirve sin cache para que un cambio en los
        archivos se vea al recargar, igual que el --reload de la API."""
        return FileResponse(WEB / "index.html",
                            headers={"Cache-Control": "no-store"})

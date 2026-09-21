"""Alta de accesos, creacion de contrasena e inicio de sesion."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import accesos, auth, contrasenas, intentos
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["Acceso"])

# Administracion y direccion general. La segunda alcanza esto por
# `HEREDA`, pero se nombra aqui para que se lea sin ir a buscarlo.
# RRHH reparte los accesos: es quien da de alta a la gente y quien sabe
# quien salio. Lo que lo detiene no es no poder abrir esta pantalla,
# sino que aqui dentro nadie se toca a si mismo y que hay actividades
# que no pueden juntarse (ver INCOMPATIBLES en permisos.py).
ADMINISTRA = auth.requiere(m.Rol.ADMIN, m.Rol.DIRECTOR_GENERAL,
                           m.Rol.RECURSOS_HUMANOS)

# Quien puede dictarle un codigo al personal de campo. La central
# siempre; el consultor cuando esa persona trabaje en sus servicios --eso
# se revisa adentro, porque depende de quien sea el agente--. No entra
# direccion de operaciones: lo unico que protege este camino es que quien
# entrega el codigo reconozca la voz de quien llama.
DICTA_CODIGO = auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL)


class AltaUsuarioIn(BaseModel):
    persona_id: int
    rol: m.Rol


class MotivoIn(BaseModel):
    """Por que se cierra o se abre una puerta. Opcional, pero si se
    escribe queda en la bitacora y es lo que se lee un ano despues."""
    motivo: str | None = None


class CambioRolIn(BaseModel):
    rol: m.Rol
    motivo: str | None = None


class EstablecerContrasenaIn(BaseModel):
    token: str
    contrasena: str


class CambioContrasenaIn(BaseModel):
    """La actual se pide aunque ya tenga la sesion abierta: sin eso, una
    sesion robada se vuelve una cuenta robada para siempre."""
    actual: str
    nueva: str


class RecuperarIn(BaseModel):
    correo: str


class CategoriaIn(BaseModel):
    """Una categoria nace con su lista completa de actividades. No hay
    categoria vacia a medio llenar: o se sabe que hace ese puesto, o
    todavia no es un puesto."""
    nombre: str
    actividades: list[str]
    descripcion: str | None = None
    horas_sesion: int | None = None


class CambioCategoriaIn(BaseModel):
    """Lo que no se manda, no se toca. `actividades` es la excepcion: si
    viene, reemplaza la lista entera, porque asi es como se ve en la
    pantalla --una tabla de casillas-- y mandar solo las que cambiaron
    obligaria a inventar un lenguaje de altas y bajas."""
    nombre: str | None = None
    descripcion: str | None = None
    horas_sesion: int | None = None
    activa: bool | None = None
    actividades: list[str] | None = None


class PonerCategoriaIn(BaseModel):
    """`categoria_id` en nulo le quita la categoria: vuelve a los
    permisos de su rol, que es de donde salio."""
    categoria_id: int | None = None
    motivo: str | None = None


class PermisoIn(BaseModel):
    actividad: str
    motivo: str | None = None


class CodigoCampoIn(BaseModel):
    persona_id: int


class ContrasenaDeCampoIn(BaseModel):
    """Lo que manda la app: quien eres, los cuatro digitos que te
    dictaron, y la contrasena que quieres."""
    correo: str
    codigo: str
    contrasena: str


@router.post("/usuarios", status_code=201,
             summary="Dar de alta un acceso y generar su invitacion")
def alta_usuario(datos: AltaUsuarioIn, db: Session = Depends(get_db),
                 actor: m.Usuario = Depends(ADMINISTRA)):
    """El usuario queda ligado al correo del empleado. Se le envia un enlace
    para que el mismo cree su contrasena."""
    persona = db.get(m.Persona, datos.persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {datos.persona_id}")

    existente = db.query(m.Usuario).filter_by(persona_id=persona.id).first()
    if existente:
        raise HTTPException(409, f"Esa persona ya tiene acceso (usuario {existente.id})")

    usuario = m.Usuario(persona_id=persona.id, correo=persona.correo, rol=datos.rol)
    db.add(usuario)
    db.flush()

    token, expira = auth.token_invitacion()
    db.add(m.Invitacion(usuario_id=usuario.id, token=token, expira_en=expira))
    accesos.anotar(db, actor, "acceso creado", "usuario", usuario.id,
                   despues=usuario.rol.value, detalle=usuario.correo)
    db.commit()

    return {
        "usuario_id": usuario.id, "correo": usuario.correo, "rol": usuario.rol.value,
        "invitacion": {
            "enlace": f"https://centauro.lat/crear-contrasena/{token}",
            "expira_en": expira.isoformat(),
        },
        "nota": "En produccion este enlace se envia por correo, no se devuelve aqui",
    }


@router.get("/usuarios", summary="Quien tiene acceso al sistema")
def listar_usuarios(db: Session = Depends(get_db), incluir_inactivos: bool = True,
                    _: m.Usuario = Depends(ADMINISTRA)):
    """La lista con lo que hace falta para decidir: quien es, con que rol
    entra, si sigue activo y cuando entro por ultima vez.

    Lo ultimo es el dato que nadie miraba: una cuenta que nunca se uso es
    un acceso que se dio y no se ocupo, y una que lleva meses dormida es
    una puerta abierta a nombre de alguien que quiza ya no esta.
    """
    consulta = db.query(m.Usuario)
    if not incluir_inactivos:
        consulta = consulta.filter(m.Usuario.activo.is_(True))
    filas = consulta.order_by(m.Usuario.correo).all()
    return [{
        "usuario_id": u.id,
        "persona_id": u.persona_id,
        "nombre": u.persona.nombre if u.persona else None,
        "correo": u.correo,
        "rol": u.rol.value,
        # Con categoria, el rol ya no es lo que manda. Si el renglon
        # siguiera diciendo solo "Consultor", la lista mentiria por
        # omision justo en la pantalla donde se reparte el acceso.
        "categoria": u.categoria.nombre if u.categoria else None,
        "activo": u.activo,
        # Sin contrasena: se le dio el acceso y nunca lo estreno.
        "estrenado": u.hash_contrasena is not None,
        "ultimo_acceso": (u.ultimo_acceso.isoformat()
                          if u.ultimo_acceso else None),
        # Dado de baja como empleado pero con el acceso abierto. Hoy no
        # deberia pasar; el dia que Odoo mande las bajas, esta es la
        # senal de que algo quedo a medias.
        "persona_de_baja": bool(u.persona and not u.persona.activo),
    } for u in filas]


@router.post("/usuarios/{usuario_id}/desactivar",
             summary="Cerrarle la puerta a alguien")
def desactivar_usuario(usuario_id: int, datos: MotivoIn,
                       db: Session = Depends(get_db),
                       actor: m.Usuario = Depends(ADMINISTRA)):
    """La sesion que tenga abierta muere en su siguiente peticion.

    No lo saca de la operacion: si estaba asignado a los servicios de
    manana, la respuesta dice cuales quedan sin el.
    """
    resultado = accesos.desactivar(db, usuario_id, actor, datos.motivo)
    db.commit()
    return resultado


@router.post("/usuarios/{usuario_id}/reactivar",
             summary="Volverle a abrir la puerta")
def reactivar_usuario(usuario_id: int, datos: MotivoIn,
                      db: Session = Depends(get_db),
                      actor: m.Usuario = Depends(ADMINISTRA)):
    resultado = accesos.reactivar(db, usuario_id, actor, datos.motivo)
    db.commit()
    return resultado


@router.post("/usuarios/{usuario_id}/rol", summary="Cambiarle el puesto")
def cambiar_rol_usuario(usuario_id: int, datos: CambioRolIn,
                        db: Session = Depends(get_db),
                        actor: m.Usuario = Depends(ADMINISTRA)):
    """Del rol sale todo lo que esa persona puede tocar, asi que es la
    operacion mas delicada del sistema. Surte efecto en su siguiente
    peticion, sin cerrarle la sesion."""
    resultado = accesos.cambiar_rol(db, usuario_id, datos.rol, actor,
                                    datos.motivo)
    db.commit()
    return resultado


@router.get("/usuarios/{usuario_id}/historial",
            summary="Que se le ha hecho a ese acceso, y quien")
def historial_usuario(usuario_id: int, db: Session = Depends(get_db),
                      _: m.Usuario = Depends(ADMINISTRA)):
    return accesos.historial(db, usuario_id)


# ==================================================================
# Las categorias: que puede tocar cada quien
#
# Todo esto pide administracion. No es que el trabajo sea delicado --lo
# es--, sino que repartir permisos es la unica actividad que puede
# reescribirse a si misma: quien pueda darse permisos se los da todos.
# ==================================================================

@router.get("/actividades",
            summary="Todo lo que se puede repartir, con su descripcion")
def catalogo_actividades(_: m.Usuario = Depends(ADMINISTRA)):
    """La lista de casillas de la pantalla de categorias.

    Las actividades las declara el codigo, no el panel: una casilla que
    se pudiera inventar desde la pantalla seria una casilla que no
    protege ninguna puerta.
    """
    return accesos.catalogo_de_actividades()


@router.get("/categorias", summary="Los puestos configurados")
def listar_categorias(db: Session = Depends(get_db),
                      _: m.Usuario = Depends(ADMINISTRA)):
    """Cada una con cuanta gente la trae puesta: es el dato que hace
    falta antes de cambiarle algo."""
    return accesos.categorias(db)


@router.post("/categorias", status_code=201, summary="Crear un puesto")
def crear_categoria(datos: CategoriaIn, db: Session = Depends(get_db),
                    actor: m.Usuario = Depends(ADMINISTRA)):
    """La categoria manda sobre el rol: quien la trae puesta puede
    exactamente lo que dice su lista, ni mas ni menos.

    Por eso se crea con la lista completa y no se hereda nada del rol:
    una categoria que "agregara" permisos encima del puesto no serviria
    para lo unico que hace falta, que es quitar.
    """
    resultado = accesos.crear_categoria(
        db, actor, datos.nombre, datos.actividades,
        descripcion=datos.descripcion, horas_sesion=datos.horas_sesion)
    db.commit()
    return resultado


@router.patch("/categorias/{categoria_id}", summary="Cambiar un puesto")
def cambiar_categoria(categoria_id: int, datos: CambioCategoriaIn,
                      db: Session = Depends(get_db),
                      actor: m.Usuario = Depends(ADMINISTRA)):
    """Surte efecto para toda su gente en su siguiente peticion.

    Apagarla con `activa` en falso no le quita nada a quien ya la trae:
    solo deja de ofrecerse al asignar. Lo contrario --que apagar una
    categoria le devolviera a su gente los permisos del rol-- seria que
    apagarla diera acceso, que es justo lo que uno no quiere.
    """
    resultado = accesos.cambiar_categoria(
        db, actor, categoria_id, **datos.model_dump(exclude_unset=True))
    db.commit()
    return resultado


@router.post("/usuarios/{usuario_id}/categoria",
             summary="Ponerle o quitarle el puesto a alguien")
def poner_categoria(usuario_id: int, datos: PonerCategoriaIn,
                    db: Session = Depends(get_db),
                    actor: m.Usuario = Depends(ADMINISTRA)):
    resultado = accesos.poner_categoria(db, actor, usuario_id,
                                        datos.categoria_id, datos.motivo)
    db.commit()
    return resultado


@router.get("/usuarios/{usuario_id}/permisos",
            summary="Que puede esta persona, y de donde le viene")
def permisos_de_usuario(usuario_id: int, db: Session = Depends(get_db),
                        _: m.Usuario = Depends(ADMINISTRA)):
    """La pantalla que contesta "por que Beatriz no puede".

    Cada actividad viene con `de_donde`: su categoria, su rol o un
    permiso suelto. Sin eso, el unico camino para entenderlo es leer el
    codigo, y quien reparte accesos no lee codigo.
    """
    return accesos.permisos_de(db, usuario_id)


@router.post("/usuarios/{usuario_id}/permisos",
             summary="Darle un permiso de mas")
def dar_permiso(usuario_id: int, datos: PermisoIn,
                db: Session = Depends(get_db),
                actor: m.Usuario = Depends(ADMINISTRA)):
    """La excepcion de una persona, encima de su categoria. Solo da.

    Quitar se hace con una categoria que no lo traiga: una excepcion que
    quitara dejaria su renglon diciendo un puesto que no es, y para
    saber que puede habria que abrir su ficha y acordarse de que existe.
    """
    resultado = accesos.dar_permiso(db, actor, usuario_id, datos.actividad,
                                    datos.motivo)
    db.commit()
    return resultado


@router.delete("/usuarios/{usuario_id}/permisos/{actividad}",
               summary="Quitarle un permiso de mas")
def quitar_permiso(usuario_id: int, actividad: str,
                   db: Session = Depends(get_db),
                   actor: m.Usuario = Depends(ADMINISTRA)):
    """Quita la excepcion, no el permiso: si su categoria o su rol ya lo
    traian, sigue pudiendo. Es lo correcto --nadie pierde nada que no se
    le hubiera dado aqui-- pero la pantalla tiene que decirlo, o parecera
    que el boton no hizo nada."""
    resultado = accesos.quitar_permiso(db, actor, usuario_id, actividad)
    db.commit()
    return resultado


@router.post("/establecer-contrasena",
             summary="Poner la contrasena con un enlace")
def establecer_contrasena(datos: EstablecerContrasenaIn,
                          db: Session = Depends(get_db)):
    """Sirve para la primera y para la olvidada: es el mismo enlace con
    distinto motivo y distinta duracion."""
    resultado = contrasenas.usar_enlace(db, datos.token, datos.contrasena)
    db.commit()
    return resultado


@router.post("/mi-contrasena", summary="Cambiar mi propia contrasena")
def cambiar_mi_contrasena(datos: CambioContrasenaIn, peticion: Request,
                          db: Session = Depends(get_db),
                          usuario: m.Usuario = Depends(auth.usuario_actual)):
    """Cambiarla tira las demas sesiones abiertas.

    Va con el mismo limite de intentos que el inicio de sesion: adivinar
    la contrasena actual desde una sesion robada es el mismo ataque por
    otra puerta.
    """
    ip = peticion.client.host if peticion.client else None
    intentos.revisar(usuario.correo, ip)
    try:
        resultado = contrasenas.cambiar(db, usuario, datos.actual, datos.nueva)
    except HTTPException as e:
        if e.status_code == 401:
            intentos.fallo(usuario.correo, ip)
        raise
    intentos.exito(usuario.correo, ip)
    db.commit()
    return resultado


@router.post("/recuperar", summary="Se me olvido la contrasena")
def recuperar(datos: RecuperarIn, peticion: Request,
              db: Session = Depends(get_db)):
    """La respuesta es la misma exista o no la cuenta.

    El enlace no viaja aqui: esta puerta es publica, y devolverlo seria
    regalar la cuenta a quien escriba un correo ajeno. Mientras el
    sistema no sepa mandar correos que no cuelguen de un servicio, lo
    entrega administracion desde el panel.
    """
    ip = peticion.client.host if peticion.client else None
    # En su propio carril, no en el del inicio de sesion: con el mismo
    # contador, ocho peticiones aqui con un correo ajeno dejaban a esa
    # persona sin poder entrar quince minutos. El limite sigue --pedir
    # enlaces sin fin tampoco-- pero solo frena la recuperacion.
    carril = f"recuperar:{datos.correo}"
    intentos.revisar(carril, ip)
    intentos.fallo(carril, ip)
    resultado = contrasenas.pedir_recuperacion(db, datos.correo)
    db.commit()
    return resultado


@router.get("/campo/buscar", summary="Buscar a quien darle un codigo")
def buscar_para_codigo(q: str = "", db: Session = Depends(get_db),
                       actor: m.Usuario = Depends(DICTA_CODIGO)):
    """El buscador de la pantalla del codigo.

    El consultor ve a su gente; la central ve a todos. Pide al menos dos
    letras: una busqueda que devuelve a todos es el padron completo en la
    pantalla de cualquier consultor.
    """
    return contrasenas.buscar_para_codigo(db, actor, q)


@router.post("/campo/codigo", summary="Generar el codigo para dictarlo")
def generar_codigo(datos: CodigoCampoIn, db: Session = Depends(get_db),
                   actor: m.Usuario = Depends(DICTA_CODIGO)):
    """Cuatro digitos, diez minutos, un solo uso.

    Es la unica vez que se ven: si se cierra la tarjeta hay que generar
    otro, y ese mata a este. Asi nadie acumula una lista de codigos
    vigentes en una pestana abierta.
    """
    resultado = contrasenas.generar_codigo(db, actor, datos.persona_id)
    db.commit()
    return resultado


@router.post("/campo/contrasena", summary="Poner la contrasena con el codigo")
def contrasena_de_campo(datos: ContrasenaDeCampoIn, peticion: Request,
                        db: Session = Depends(get_db)):
    """Lo que hace el agente desde la app.

    Va con limite propio: cuatro digitos son diez mil combinaciones, y el
    tope por codigo --cinco fallos y se muere-- vive en la base, no en
    Redis. Este de aqui es el segundo cinturon, contra quien pruebe con
    muchos correos distintos.
    """
    ip = peticion.client.host if peticion.client else None
    carril = f"codigo:{datos.correo}"
    intentos.revisar(carril, ip)
    try:
        resultado = contrasenas.usar_codigo(db, datos.correo, datos.codigo,
                                            datos.contrasena)
    except HTTPException as e:
        if e.status_code == 401:
            intentos.fallo(carril, ip)
        raise
    intentos.exito(carril, ip)
    db.commit()
    return resultado


@router.get("/usuarios/{usuario_id}/enlace-pendiente",
            summary="El enlace vivo de esa cuenta, para entregarlo")
def enlace_pendiente(usuario_id: int, db: Session = Depends(get_db),
                     actor: m.Usuario = Depends(ADMINISTRA)):
    """Existe porque el sistema todavia no sabe mandar un correo que no
    cuelgue de un servicio. Mientras tanto lo entrega una persona, igual
    que el codigo del personal de campo lo dicta su consultor.

    Queda escrito quien lo pidio: un enlace de contrasena en manos de
    alguien es una cuenta en manos de alguien.
    """
    resultado = contrasenas.enlace_pendiente(db, usuario_id)
    accesos.anotar(db, actor, "enlace entregado", "usuario", usuario_id,
                   detalle=resultado["tipo"])
    db.commit()
    return resultado


@router.post("/token", summary="Iniciar sesion")
def iniciar_sesion(peticion: Request,
                   formulario: OAuth2PasswordRequestForm = Depends(),
                   db: Session = Depends(get_db)):
    """Con limite de intentos: sin el, una lista de correos y un
    diccionario bastan para entrar, y en la bitacora no queda nada raro
    porque cada intento es una peticion normal."""
    # Detras del proxy, `client.host` es la IP real solo si uvicorn corre
    # con --proxy-headers (ver docker-compose.prod.yml). Sin eso, todos
    # los intentos cuentan como uno solo y el tope por IP no sirve.
    ip = peticion.client.host if peticion.client else None
    intentos.revisar(formulario.username, ip)

    usuario = db.query(m.Usuario).filter_by(correo=formulario.username).first()
    if not usuario or not auth.verificar(formulario.password, usuario.hash_contrasena):
        intentos.fallo(formulario.username, ip)
        # El mismo mensaje exista o no la cuenta: decir "ese correo no
        # existe" regala la mitad del trabajo a quien esta probando.
        raise HTTPException(401, "Correo o contrasena incorrectos")
    if not usuario.activo:
        raise HTTPException(403, "Ese acceso esta desactivado")

    intentos.exito(formulario.username, ip)
    usuario.ultimo_acceso = datetime.now()
    db.commit()
    return {"access_token": auth.crear_token(usuario), "token_type": "bearer",
            "rol": usuario.rol.value, "nombre": usuario.persona.nombre}


@router.get("/yo", summary="Quien soy")
def yo(usuario: m.Usuario = Depends(auth.usuario_actual)):
    # El idioma viaja aqui porque aqui es donde la app pregunta quien es
    # antes de pintar nada. Sale del pais de su plaza: el de campo no
    # elige idioma, y pedirselo seria un boton mas en una pantalla que se
    # usa con una mano.
    plaza = usuario.persona.plaza if usuario.persona else None
    return {"usuario_id": usuario.id, "nombre": usuario.persona.nombre,
            "correo": usuario.correo, "rol": usuario.rol.value,
            "persona_id": usuario.persona_id,
            "idioma": plaza.pais.idioma if plaza and plaza.pais else "es",
            # Y su pais, por la misma razon que el idioma: las pantallas
            # que se piden por pais --el personal, la nomina-- abrian en
            # el primero del catalogo, que sale ordenado por nombre. Al
            # de Mexico le abria Brasil y veia una tabla vacia.
            "pais_id": plaza.pais_id if plaza else None,
            "plaza_id": usuario.persona.plaza_id if usuario.persona else None,
            # Si todavia no ha visto el recorrido de la primera vez.
            "recorrido_pendiente": usuario.recorrido_en is None}


@router.post("/recorrido-visto", summary="Ya vio el recorrido")
def recorrido_visto(db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(auth.usuario_actual)):
    """Se marca en cuanto se abre, no al terminarlo.

    El que lo salta en el primer paso tambien lo vio: si se marcara al
    final, saltarlo lo dejaria apareciendo cada vez que entra, y un
    recorrido que no se deja cerrar se aprende a odiar. Para volver a
    verlo esta el menu de su nombre, que es donde vive lo que no cambia.
    """
    if usuario.recorrido_en is None:
        usuario.recorrido_en = datetime.now()
        db.commit()
    return {"resultado": "visto"}

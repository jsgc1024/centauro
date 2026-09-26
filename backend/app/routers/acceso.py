"""Alta de accesos, creacion de contrasena e inicio de sesion."""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import acceso_por_correo, accesos, auth, contrasenas, intentos
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["Acceso"])

# Administracion y direccion general. La segunda alcanza esto por
# `HEREDA`, pero se nombra aqui para que se lea sin ir a buscarlo.
# RRHH reparte los accesos: es quien da de alta a la gente y quien sabe
# quien salio. Lo que lo detiene no es no poder abrir esta pantalla,
# sino que aqui dentro nadie se toca a si mismo y que hay actividades
# que no pueden juntarse (ver INCOMPATIBLES en permisos.py).
#
# Desde la seccion 73 es una actividad y no una lista de roles: los roles
# que la traen de fabrica son los mismos, pero ahora un puesto la puede
# quitar. Capacitacion entra como recursos humanos y no reparte accesos.
ADMINISTRA = auth.puede("accesos.dar")

# Quien puede dictarle un codigo al personal de campo. La central
# siempre; el consultor cuando esa persona trabaje en sus servicios --eso
# se revisa adentro, porque depende de quien sea el agente--. No entra
# direccion de operaciones: lo unico que protege este camino es que quien
# entrega el codigo reconozca la voz de quien llama.
DICTA_CODIGO = auth.puede("codigo.dictar")      # seccion 73, como ADMINISTRA

# Quien puede ver un enlace de contrasena: administracion, y direccion
# general porque hereda todo lo de administracion. Decision de Salvador
# (23 sep). Con el enlace en la mano se le pone la contrasena a otra
# persona y se entra como ella; por eso RRHH, que si da los accesos, no
# lo ve: da el acceso y el enlace le llega a la persona por su correo.
COPIA_ENLACE = auth.requiere(m.Rol.ADMIN)


def _copia_enlaces(actor: m.Usuario) -> bool:
    """Lo mismo que COPIA_ENLACE, para decidir que va en una respuesta."""
    return (actor.rol == m.Rol.ADMIN
            or m.Rol.ADMIN in auth.HEREDA.get(actor.rol, set()))


class AltaUsuarioIn(BaseModel):
    persona_id: int
    rol: m.Rol
    # El puesto, de una vez. Opcional: sin puesto entra con lo de su rol.
    categoria_id: int | None = None


class EnlaceIn(BaseModel):
    """El token viaja en el cuerpo y no en la ruta: una ruta queda
    escrita en la bitacora de cada servidor del camino."""
    token: str


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
    # Seccion 73: con que rol entra quien lo trae, su area, las pantallas
    # de su menu, a que puestos de Odoo se parece y su lugar en la lista.
    rol: m.Rol | None = None
    area: str | None = None
    pantallas: list[str] | None = None
    puestos_odoo: str | None = None
    orden: int | None = None


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
    rol: m.Rol | None = None
    area: str | None = None
    pantallas: list[str] | None = None
    puestos_odoo: str | None = None
    orden: int | None = None


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
             summary="Dar de alta un acceso y mandar su invitacion")
def alta_usuario(datos: AltaUsuarioIn, tareas: BackgroundTasks,
                 db: Session = Depends(get_db),
                 actor: m.Usuario = Depends(ADMINISTRA)):
    """El usuario queda ligado al correo del empleado, y ese correo recibe
    el enlace para que el mismo cree su contrasena.

    Solo quien trabaja en la consola: el personal de seguridad recibe su
    acceso de Odoo y pone su contrasena con el codigo de cuatro digitos.
    """
    persona = db.get(m.Persona, datos.persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {datos.persona_id}")
    if not persona.activo:
        raise HTTPException(409, {
            "mensaje": "Esa persona esta dada de baja como empleado.",
            "que_hacer": "El acceso no puede ser la puerta de atras de una "
                         "baja: si volvio, reactivala primero como empleada.",
        })

    existente = db.query(m.Usuario).filter_by(persona_id=persona.id).first()
    if existente:
        raise HTTPException(409, f"Esa persona ya tiene acceso (usuario {existente.id})")
    # El correo es la llave del acceso y no se repite. Sin esto, dos
    # personas con el mismo correo reventaban contra la base.
    llave = (persona.correo or "").strip().lower()
    if db.query(m.Usuario.id).filter(
            func.lower(func.trim(m.Usuario.correo)) == llave).first():
        raise HTTPException(409, {
            "mensaje": "Ese correo ya es el acceso de otra persona.",
            "que_hacer": "Corrige el correo de esta persona en el padron.",
        })

    # Con puesto, entra con el rol de su puesto (seccion 73): la pantalla
    # ya lo pone asi, pero quien llame a la API directo no puede dejar a
    # un monitorista entrando como consultor.
    rol = datos.rol
    if datos.categoria_id is not None:
        puesto = db.get(m.CategoriaAcceso, datos.categoria_id)
        if puesto is not None and puesto.rol is not None:
            rol = puesto.rol
    usuario = m.Usuario(persona_id=persona.id, correo=persona.correo, rol=rol)
    db.add(usuario)
    db.flush()
    accesos.anotar(db, actor, "acceso creado", "usuario", usuario.id,
                   despues=usuario.rol.value, detalle=usuario.correo)
    if datos.categoria_id is not None:
        accesos.poner_categoria(db, actor, usuario.id, datos.categoria_id)

    enlace, aviso = contrasenas.invitar(db, usuario)
    db.commit()
    acceso_por_correo.despachar_despues(tareas, aviso)

    return {
        "usuario_id": usuario.id, "correo": usuario.correo, "rol": usuario.rol.value,
        "invitacion": {
            "expira_en": enlace.expira_en.isoformat(),
            # Sale por correo a quien trabaja en la consola; al de campo no.
            "por_correo": aviso is not None,
            "correo_encendido": acceso_por_correo.encendido(),
            # Solo para administracion (ver COPIA_ENLACE).
            "enlace": (acceso_por_correo.enlace(enlace.token)
                       if _copia_enlaces(actor) else None),
        },
    }


@router.get("/personas-sin-acceso",
            summary="A quien se le puede dar acceso")
def personas_sin_acceso(db: Session = Depends(get_db),
                        _: m.Usuario = Depends(ADMINISTRA)):
    """La lista de "Dar acceso": las personas vivas del padron que todavia
    no tienen uno.

    Fuera quien ya lo tiene --el acceso es uno por persona-- y quien trae
    un correo que ya es la llave de otro acceso. Y con lo que la pantalla
    dice arriba del formulario: de que direccion sale el correo y cuanto
    dura el enlace, o que el correo todavia no esta encendido.
    """
    con_acceso = {persona_id for (persona_id,)
                  in db.query(m.Usuario.persona_id).all()}
    llaves = {(c or "").strip().lower()
              for (c,) in db.query(m.Usuario.correo).all()}
    filas = (db.query(m.Persona)
             .filter(m.Persona.activo.is_(True))
             .order_by(m.Persona.nombre).all())
    encendido = acceso_por_correo.encendido()
    return {
        "personas": [{"persona_id": p.id, "nombre": p.nombre,
                      "correo": p.correo}
                     for p in filas
                     if p.id not in con_acceso
                     and (p.correo or "").strip().lower() not in llaves],
        "correo_encendido": encendido,
        "de": acceso_por_correo.remitente() if encendido else None,
        "dias": auth.HORAS_INVITACION // 24,
    }


@router.get("/oficina",
            summary="La oficina que llego de Odoo, con su puesto sugerido")
def oficina_de_odoo(db: Session = Depends(get_db),
                    _: m.Usuario = Depends(ADMINISTRA)):
    """Lo que Recursos Humanos necesita para dar los accesos de la oficina
    (seccion 74).

    `sin_acceso`: quien llego de Odoo como personal de oficina y todavia
    no tiene acceso, con el puesto de Centauro que sugiere su puesto de
    Odoo --o nada, y entonces se escoge a mano--. `sin_correo`: quien en
    Odoo no tiene correo de trabajo, de la ultima lectura: no puede
    llegar hasta que RH se lo ponga alla, y entonces llega solo.
    """
    from app import odoo_oficina

    con_acceso = {persona_id for (persona_id,)
                  in db.query(m.Usuario.persona_id).all()}
    llaves = {(c or "").strip().lower()
              for (c,) in db.query(m.Usuario.correo).all()}
    puestos = odoo_oficina.sugeribles(db)
    filas = (db.query(m.Persona)
             .filter(m.Persona.oficina.is_(True), m.Persona.activo.is_(True))
             .order_by(m.Persona.nombre).all())
    leido_en, informe = odoo_oficina.ultimo_informe(db)
    return {
        "sin_acceso": [{
            "persona_id": p.id, "nombre": p.nombre, "correo": p.correo,
            "puesto_odoo": p.puesto_odoo, "area_odoo": p.area_odoo,
            "sugerido": odoo_oficina.sugerencia(p.puesto_odoo, puestos),
        } for p in filas
            if p.id not in con_acceso
            and (p.correo or "").strip().lower() not in llaves],
        "sin_correo": sorted((informe or {}).get("sin_correo", []),
                             key=lambda x: x.get("nombre") or ""),
        "leido_en": leido_en.isoformat() if leido_en else None,
    }


@router.get("/usuarios/{usuario_id}/invitacion",
            summary="Como va la invitacion de alguien")
def estado_de_invitacion(usuario_id: int, db: Session = Depends(get_db),
                         actor: m.Usuario = Depends(ADMINISTRA)):
    """Si su enlace sigue vivo y que paso con su correo: lo que se
    necesita para contestar "no me llego"."""
    usuario = db.get(m.Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, f"No existe el acceso {usuario_id}")
    return {**contrasenas.estado_de_invitacion(db, usuario),
            "puede_copiar": _copia_enlaces(actor)}


@router.post("/usuarios/{usuario_id}/invitacion",
             summary="Mandarle otra vez su invitacion")
def reenviar_invitacion(usuario_id: int, tareas: BackgroundTasks,
                        db: Session = Depends(get_db),
                        actor: m.Usuario = Depends(ADMINISTRA)):
    """Un enlace nuevo por correo, y el anterior deja de servir.

    Para quien todavia no estrena su acceso: se le paso el correo,
    vencio a los tres dias, o no le llego.
    """
    usuario = db.get(m.Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, f"No existe el acceso {usuario_id}")
    enlace, aviso = contrasenas.reinvitar(db, usuario, actor)
    db.commit()
    acceso_por_correo.despachar_despues(tareas, aviso)
    return {
        "correo": usuario.correo,
        "expira_en": enlace.expira_en.isoformat(),
        "correo_encendido": acceso_por_correo.encendido(),
        "enlace": (acceso_por_correo.enlace(enlace.token)
                   if _copia_enlaces(actor) else None),
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
        # Si su puesto dice con que rol entra, el rol no se cambia a mano
        # (seccion 73): la pantalla no lo ofrece.
        "rol_por_puesto": bool(u.categoria and u.categoria.rol),
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
        descripcion=datos.descripcion, horas_sesion=datos.horas_sesion,
        rol=datos.rol, area=datos.area, pantallas=datos.pantallas,
        puestos_odoo=datos.puestos_odoo, orden=datos.orden)
    db.commit()
    return resultado


@router.get("/categorias/base",
            summary="Los puestos de la propuesta que todavia no existen")
def puestos_base_que_faltan(db: Session = Depends(get_db),
                            _: m.Usuario = Depends(ADMINISTRA)):
    """Para el boton de la pantalla: si falta alguno, se ofrece crearlos.
    Y los dos que entran con su rol, para que la lista de puestos este
    completa."""
    from app import puestos_base
    return {"faltan": puestos_base.faltan(db),
            "por_rol": puestos_base.por_rol(db)}


@router.post("/categorias/base",
             summary="Crear los puestos de la propuesta (seccion 73)")
def crear_puestos_base(db: Session = Depends(get_db),
                       actor: m.Usuario = Depends(ADMINISTRA)):
    """Crea los que falten y no toca los que ya estan: si alguien ya los
    ajusto, sus ajustes mandan."""
    from app import puestos_base
    resultado = puestos_base.crear_puestos(db, actor)
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


@router.post("/enlace", summary="Como esta un enlace de contrasena")
def revisar_enlace(datos: EnlaceIn, db: Session = Depends(get_db)):
    """Lo que la pagina del enlace pregunta al abrirse: si sirve, y si
    sirve, de quien es y con que entra.

    Publica, como la de abajo: quien la usa todavia no tiene contrasena.
    El token son 256 bits al azar; no se adivina ni se enumera.
    """
    return contrasenas.revisar_enlace(db, datos.token)


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
def recuperar(datos: RecuperarIn, peticion: Request, tareas: BackgroundTasks,
              db: Session = Depends(get_db)):
    """La respuesta es la misma exista o no la cuenta.

    El enlace no viaja aqui: esta puerta es publica, y devolverlo seria
    regalar la cuenta a quien escriba un correo ajeno. Viaja por el
    correo de la persona, que sale en cuanto se confirma.
    """
    ip = peticion.client.host if peticion.client else None
    # En su propio carril, no en el del inicio de sesion: con el mismo
    # contador, ocho peticiones aqui con un correo ajeno dejaban a esa
    # persona sin poder entrar quince minutos. El limite sigue --pedir
    # enlaces sin fin tampoco-- pero solo frena la recuperacion.
    carril = f"recuperar:{datos.correo}"
    intentos.revisar(carril, ip)
    intentos.fallo(carril, ip)
    resultado, aviso = contrasenas.pedir_recuperacion(db, datos.correo)
    db.commit()
    acceso_por_correo.despachar_despues(tareas, aviso)
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
                     actor: m.Usuario = Depends(COPIA_ENLACE)):
    """El "Copiar el enlace" del panel, para cuando el correo no llega.

    Solo administracion (ver COPIA_ENLACE), y queda escrito quien lo
    pidio: un enlace de contrasena en manos de alguien es una cuenta en
    manos de alguien.
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
def yo(usuario: m.Usuario = Depends(auth.usuario_actual),
       db: Session = Depends(get_db)):
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
            "recorrido_pendiente": usuario.recorrido_en is None,
            # Seccion 73. Lo que puede hacer --para no pintar un boton que
            # va a contestar 403--, las pantallas de su menu si su puesto
            # las dice, y el nombre de su puesto. Deciden lo que se pinta;
            # cada puerta la sigue cuidando el servidor.
            "actividades": sorted(accesos.actividades_de(db, usuario)),
            "pantallas": accesos.pantallas_de(usuario),
            "puesto": usuario.categoria.nombre if usuario.categoria else None}


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

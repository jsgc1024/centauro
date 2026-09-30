"""Abrir y cerrar la puerta: desactivar, reactivar y cambiar el rol.

El candado existia desde el principio y funciona: `usuario_actual` vuelve
a buscar al usuario en la base en cada peticion y revisa que siga activo,
asi que en cuanto `activo` pasa a falso, la sesion abierta muere en el
siguiente clic. No hay que esperar a que expire nada.

Lo que no habia era forma de accionarlo. `Usuario.activo` se leia en tres
lugares y no se escribia en ninguno, y `Usuario.rol` solo se escribia en
el sembrado de demostracion. Cortarle el acceso a alguien que se fue
enojado, o cambiarle el puesto a quien cambio de area, era un UPDATE a
mano en Postgres.

Los candados de aqui no son burocracia: un panel de permisos mal hecho es
la forma mas rapida de quedarse fuera del propio sistema.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import reloj

# Estas jornadas ya no se pueden quedar sin nadie: una cancelada no va y
# una terminada ya se trabajo.
CERRADAS = (m.EstatusJornada.CANCELADA, m.EstatusJornada.TERMINADA)

# El ciclo del viatico que todavia corre. Mientras uno de estos viva, esa
# persona no se va: trae dinero de la empresa o esta a punto de traerlo,
# y sin su comprobacion el servicio no cierra.
#
# Fuera quedan dos a proposito:
#   ASIGNADO   el consultor lo planeo y nunca se movio un peso. Quitarla
#              del servicio lo borra con ella, sin rastro que cuadrar.
#   CERRADO    su ciclo ya termino. Si bloqueara, nadie que haya recibido
#              un viatico en su vida podria darse de baja nunca.
CICLO_ABIERTO = (m.EstatusViatico.SOLICITADO, m.EstatusViatico.TRANSFERIDO,
                 m.EstatusViatico.EN_COMPROBACION)


# ------------------------------------------------------------ la bitacora

def anotar(db: Session, actor: m.Usuario, accion: str, objeto: str,
           objeto_id: int | None = None, antes: str | None = None,
           despues: str | None = None, detalle: str | None = None) -> None:
    """Un renglon en la bitacora de administracion.

    El rol del actor se guarda tal como era en este momento: si manana lo
    cambian, el renglon sigue diciendo con que sombrero actuo.
    """
    # Al largo de la columna: un motivo de 401 letras reventaba el
    # renglon --y la pantalla-- con un error del servidor (seccion 100).
    # El texto largo se pierde por el final, que es donde menos importa.
    db.add(m.RegistroAdmin(
        usuario_id=actor.id, persona_id=actor.persona_id, rol=actor.rol,
        accion=accion[:80], objeto=objeto, objeto_id=objeto_id,
        antes=antes[:200] if antes else antes,
        despues=despues[:200] if despues else despues,
        detalle=detalle[:400] if detalle else detalle))


# ------------------------------------------- quien lleva un servicio

def lleva_servicios(db: Session, persona_id: int | None) -> bool:
    """Si esta persona puede ser el consultor de un servicio (seccion 87):
    tiene acceso de consultor, abierto, y sigue activa. Es la misma
    lista de /catalogos/consultores, que es la que ofrece la pantalla."""
    if not persona_id:
        return False
    return (db.query(m.Usuario.id)
            .join(m.Persona, m.Persona.id == m.Usuario.persona_id)
            .filter(m.Usuario.persona_id == persona_id,
                    m.Usuario.rol == m.Rol.CONSULTOR,
                    m.Usuario.activo.is_(True),
                    m.Persona.activo.is_(True))
            .first()) is not None


def no_es_consultor(persona_id: int) -> HTTPException:
    return HTTPException(400, {
        "mensaje": "Un servicio lo lleva alguien con acceso de consultor.",
        "que_hacer": "Escoge a uno de la lista. Si falta alguien, se le da "
                     "acceso de consultor en Accesos.",
        "consultor_id": persona_id,
    })


# Un cierre que ya termino: finanzas lo aprobo o ya esta facturado. Lo
# que queda en cualquier otro estatus todavia necesita a su consultor.
CIERRE_TERMINADO = (m.EstatusCierre.APROBADO, m.EstatusCierre.FACTURADO)


def servicio_sigue_vivo(db: Session, servicio: m.Servicio) -> bool:
    """Si a ese servicio todavia le toca algo a su consultor titular
    (decision 13, seccion 105).

    El cerrado ya no: su comision se genero al cerrarlo y no se toca. El
    cancelado sigue vivo mientras tenga un cierre por terminar --dinero
    afuera o dias trabajados que finanzas no ha aprobado--; sin cierre,
    o con todos aprobados, ya no le pasa nada. Lo demas --planeado, en
    la calle, terminado, sin visto bueno, en facturacion-- sigue
    necesitando a alguien que reciba sus avisos, corra sus plazos y
    cobre su comision.
    """
    if servicio.estatus == m.EstatusServicio.CERRADO:
        return False
    if servicio.estatus == m.EstatusServicio.CANCELADO:
        return (db.query(m.Cierre.id)
                .filter(m.Cierre.servicio_id == servicio.id,
                        m.Cierre.estatus.notin_(CIERRE_TERMINADO))
                .first()) is not None
    return True


def servicios_como_titular(db: Session, persona_id: int | None) -> list[dict]:
    """Los servicios vivos que esa persona lleva como titular.

    Es lo que le impide irse (decision 13, seccion 105): cerrarle el
    acceso a un consultor con servicios a su nombre dejaba a esos
    servicios avisandole a quien ya no esta, con sus plazos corriendo y
    sin quien cobre la comision. Primero se cambia el titular desde la
    ficha de cada uno.
    """
    if not persona_id:
        return []
    filas = (db.query(m.Servicio)
             .filter(m.Servicio.consultor_id == persona_id,
                     m.Servicio.estatus != m.EstatusServicio.CERRADO)
             .order_by(m.Servicio.id).all())
    return [{"servicio_id": s.id, "folio": s.folio, "tipo": s.tipo.value,
             "estatus": s.estatus.value}
            for s in filas if servicio_sigue_vivo(db, s)]


def no_se_va_siendo_titular(db: Session, persona: m.Persona | None) -> None:
    """409 si es titular de servicios vivos: primero se cambian."""
    vivos = servicios_como_titular(db, persona.id if persona else None)
    if not vivos:
        return
    folios = ", ".join(s["folio"] for s in vivos)
    raise HTTPException(409, {
        "mensaje": (f"Tiene {len(vivos)} servicio(s) como titular: "
                    f"cámbialos primero."),
        "que_hacer": "Dirección de operaciones le pone otro titular a cada "
                     "uno desde la ficha del servicio («Cambiar titular»), "
                     f"y entonces se le cierra el acceso. Son: {folios}.",
        "servicios": vivos,
    })


# ------------------------------------------------------------- los candados

def _obtener(db: Session, usuario_id: int) -> m.Usuario:
    usuario = db.get(m.Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, f"No existe el acceso {usuario_id}")
    return usuario


def _admins_vivos(db: Session, menos: int | None = None) -> int:
    """Cuantos quedarian con la llave maestra sin contar a uno.

    La llave la tienen administracion y direccion general (`ALTOS`, mas
    abajo): direccion general alcanza todo, administracion incluida, y es
    quien la da (seccion 83).

    Antes contaba solo administracion (seccion 88). A la unica persona
    con ese rol no se le podia quitar ni cuando se le dio por error --a
    Aridiai, el 27 de septiembre, confundido con el nombre de su puesto--,
    aunque direccion general, que si estaba, se lo puede volver a dar a
    quien sea.
    """
    consulta = (db.query(m.Usuario)
                .filter(m.Usuario.rol.in_(ALTOS),
                        m.Usuario.activo.is_(True)))
    if menos is not None:
        consulta = consulta.filter(m.Usuario.id != menos)
    return consulta.count()


def _no_es_el_ultimo_admin(db: Session, usuario: m.Usuario, que: str) -> None:
    """Quedarse sin la llave maestra es no poder volver a entrar.

    No es un caso raro: pasa el dia que alguien limpia accesos viejos y
    el ultimo administrador resulta ser una cuenta que nadie reconocia.
    """
    if usuario.rol not in ALTOS or not usuario.activo:
        return
    if _admins_vivos(db, menos=usuario.id) == 0:
        raise HTTPException(409, {
            "mensaje": f"No se puede {que}: nadie mas quedaria con la "
                       "llave maestra del sistema (administracion o "
                       "direccion general).",
            "que_hacer": "Dale administracion a alguien mas primero.",
        })


def _no_sobre_si_mismo(actor: m.Usuario, usuario: m.Usuario, que: str) -> None:
    """Nadie se cierra la puerta ni se cambia el puesto a si mismo.

    Contra el error de dedo, y tambien contra el atajo: un cambio sobre
    uno mismo no tiene quien lo revise.
    """
    if actor.id == usuario.id:
        raise HTTPException(409, {
            "mensaje": f"No te puedes {que} a ti mismo.",
            "que_hacer": "Pideselo a otro administrador.",
        })


def _lo_que_ya_puede(db: Session, usuario: m.Usuario) -> set[str]:
    """Todo lo que esta persona puede hoy, venga de donde venga.

    Su categoria manda sobre su rol --de eso se tratan las categorias--,
    y los permisos de mas se suman encima de cualquiera de los dos.
    """
    from app import permisos

    extras = {x.actividad for x in db.query(m.PermisoExtra)
              .filter_by(usuario_id=usuario.id).all()}
    if usuario.categoria_id:
        base = {x.actividad for x in db.query(m.ActividadDeCategoria)
                .filter_by(categoria_id=usuario.categoria_id).all()}
    else:
        base = permisos.actividades_de_rol(usuario.rol)
    return base | extras


def actividades_de(db: Session, usuario: m.Usuario) -> set[str]:
    """Todo lo que esta persona puede, contado igual que lo cuenta
    `auth.puede_el_usuario` en cada puerta: administracion todo; si no,
    sus permisos de mas y encima su puesto --o su rol con lo que hereda,
    si no tiene puesto--.

    Lo usa la consola para no pintar un boton que va a contestar 403 y
    para armar el menu de quien no tiene puesto. Decide la pantalla, no
    la puerta: la puerta la sigue cuidando el servidor en cada peticion.
    """
    from app import auth, permisos

    if usuario.rol == m.Rol.ADMIN:
        return set(permisos.ACTIVIDADES)
    extras = {x.actividad for x in db.query(m.PermisoExtra)
              .filter_by(usuario_id=usuario.id).all()}
    if usuario.categoria_id:
        base = {x.actividad for x in db.query(m.ActividadDeCategoria)
                .filter_by(categoria_id=usuario.categoria_id).all()}
    else:
        base = permisos.actividades_por_rol(usuario.rol, auth.HEREDA)
    return base | extras


def pantallas_de(usuario: m.Usuario) -> list[str] | None:
    """Las pantallas de su menu si su puesto las dice; si no, nada, y la
    consola arma el menu de su rol como siempre."""
    c = usuario.categoria
    if c is None or not c.pantallas:
        return None
    return [x for x in c.pantallas.split(",") if x]


def _no_juntar_incompatibles(db: Session, usuario: m.Usuario,
                             nuevas: set[str]) -> None:
    """Hay actividades que no pueden vivir en la misma mano.

    Autorizar el bono del mes y depositarlo, por ejemplo: juntas, el
    unico control sobre ese dinero es la buena fe. Esto se revisa aqui
    --al repartir-- y no al usarlas, porque quien reparte los accesos
    ahora es RRHH, que es justo quien autoriza.
    """
    from app import permisos

    tiene = _lo_que_ya_puede(db, usuario)
    for actividad in nuevas:
        choque = permisos.choca_con(actividad) & tiene
        if choque:
            raise HTTPException(409, {
                "mensaje": (f"'{actividad}' no puede convivir con "
                            f"'{sorted(choque)[0]}' en la misma persona."),
                "que_hacer": ("Son dos manos a proposito. Dale una a esta "
                              "persona y la otra a alguien mas."),
            })


def _no_juntarlas_en_un_puesto(actividades: set[str]) -> None:
    """Una categoria tampoco puede traer las dos.

    Sin esto, el candado del renglon anterior se esquiva armando un
    puesto que ya las trae juntas y poniendoselo a alguien.
    """
    from app import permisos

    for actividad in actividades:
        choque = permisos.choca_con(actividad) & actividades
        if choque:
            raise HTTPException(409, {
                "mensaje": (f"Un puesto no puede traer '{actividad}' y "
                            f"'{sorted(choque)[0]}' a la vez."),
                "que_hacer": "Son dos manos a proposito. Haz dos puestos.",
            })


def _tambien_se_lo_daria_a_si_mismo(actor: m.Usuario,
                                    usuario: m.Usuario) -> None:
    """Nadie se amplia los accesos a si mismo.

    Vale para toda la pantalla, y desde que la abre RRHH vale el doble:
    quien reparte permisos y no tiene este candado, tiene todos.
    """
    if actor.id == usuario.id:
        raise HTTPException(409, {
            "mensaje": "No te puedes dar accesos a ti mismo.",
            "que_hacer": "Pideselo a otra persona con acceso a esta pantalla.",
        })


# ------------------------------------------- los de arriba (seccion 83)
#
# Decision de Salvador, 27 de septiembre, al aprobar el puesto de
# administracion del sistema y calidad. Al revisarlo aparecieron dos
# huecos que ya existian: quien reparte accesos podia ampliar el puesto
# que el mismo trae --"nadie se da permisos a si mismo" se brincaba
# cambiando el puesto en vez de la persona-- y podia hacer a otra persona
# direccion general o administracion. Desde aqui:
#
#   * nadie cambia el puesto que trae puesto;
#   * direccion general y administracion --la llave maestra-- solo las
#     da, las quita o las toca direccion general;
#   * el poder de repartir accesos tambien: los puestos que lo traen, el
#     permiso suelto y el acceso de quien ya lo tiene solo los cambia
#     direccion general. Cerrarle la puerta a quien se va, si se puede.
#
# Sin lo tercero, "lo cambia direccion general" no seria cierto: quien
# reparte le podria ampliar el acceso a quien tambien reparte, y ese le
# devolveria el favor.

# Direccion general y la llave maestra.
ALTOS = (m.Rol.DIRECTOR_GENERAL, m.Rol.ADMIN)
# La actividad que reparte a las demas.
REPARTE = "accesos.dar"


def es_direccion(usuario: m.Usuario) -> bool:
    """Direccion general, o la llave maestra: pasa todo candado, y solo
    la da direccion general."""
    return usuario.rol in ALTOS


def solo_direccion(actor: m.Usuario, que: str) -> None:
    if not es_direccion(actor):
        raise HTTPException(403, {
            "mensaje": f"{que} solo lo hace Dirección general.",
            "que_hacer": "Pídeselo a Dirección general.",
        })


def reparte_de_fabrica(rol) -> bool:
    """Si ese rol, sin puesto, reparte accesos."""
    from app import auth, permisos
    return REPARTE in permisos.actividades_por_rol(m.Rol(rol), auth.HEREDA)


def reparte(db: Session, usuario: m.Usuario) -> bool:
    """Si esta persona hoy reparte accesos, le venga de donde le venga."""
    return REPARTE in actividades_de(db, usuario)


def trae_reparte(categoria: m.CategoriaAcceso) -> bool:
    return any(a.actividad == REPARTE for a in categoria.actividades)


def _no_es_su_puesto(actor: m.Usuario, categoria: m.CategoriaAcceso) -> None:
    """El puesto que uno trae lo cambia otra persona. Sin esto, quien
    reparte accesos se agregaba a su propio puesto lo que le faltara."""
    if actor.categoria_id is not None and actor.categoria_id == categoria.id:
        raise HTTPException(409, {
            "mensaje": "Es tu puesto: no lo cambias tú.",
            "que_hacer": "Lo cambia Dirección general, y queda en la "
                         "bitácora.",
        })


# --------------------------------------------------- lo que deja atras

def viaticos_sin_cerrar(db: Session, persona_id: int) -> list[dict]:
    """El dinero que esa persona todavia no cierra.

    Es lo que le impide irse. No es burocracia: un viatico transferido y
    sin comprobar es dinero de la empresa que se queda sin dueno, y el
    servicio no cierra hasta que alguien lo comprueba. El que se va tiene
    que terminar su ciclo primero.
    """
    filas = (db.query(m.AsignacionViatico)
             .filter(m.AsignacionViatico.persona_id == persona_id,
                     m.AsignacionViatico.estatus.in_(CICLO_ABIERTO))
             .all())
    salida = []
    for v in filas:
        jornada = db.get(m.Jornada, v.jornada_id)
        servicio = (jornada.equipo.servicio
                    if jornada and jornada.equipo else None)
        salida.append({
            "viatico_id": v.id,
            "fecha": jornada.fecha.isoformat() if jornada else None,
            "folio": servicio.folio if servicio else None,
            "estatus": v.estatus.value,
            "monto": float(v.monto_total or 0),
            "comprobado": float(v.monto_comprobado or 0),
            "limite": (v.limite_comprobacion.isoformat()
                       if v.limite_comprobacion else None),
        })
    return sorted(salida, key=lambda f: f["fecha"] or "")


def jornadas_por_cubrir(db: Session, persona_id: int) -> list[dict]:
    """Los dias futuros donde esa persona sigue asignada.

    Cerrarle la puerta a alguien no lo saca de la operacion: si estaba
    asignado a los servicios de manana, esas jornadas se quedan sin el y
    nadie se entera hasta que el equipo no llega.

    No se quitan aqui. El sistema propone y el consultor decide: quitarlas
    solo seria el sistema dejando un servicio sin gente.
    """
    filas = (db.query(m.Jornada)
             .join(m.AsignacionPersonal,
                   m.AsignacionPersonal.jornada_id == m.Jornada.id)
             .filter(m.AsignacionPersonal.persona_id == persona_id,
                     m.Jornada.estatus.notin_(CERRADAS))
             .order_by(m.Jornada.fecha).all())

    # El "hoy" es el del pais de cada servicio, no el del contenedor: un
    # servicio en Sao Paulo ya arranco cuando en Mexico todavia es de
    # madrugada.
    relojes = reloj.Relojes(db)
    por_servicio: dict[int, dict] = {}
    for j in filas:
        servicio = j.equipo.servicio if j.equipo else None
        if not servicio:
            continue
        if j.fecha < relojes.hoy(servicio.pais_id):
            continue
        ficha = por_servicio.setdefault(servicio.id, {
            "servicio_id": servicio.id, "folio": servicio.folio,
            "desde": j.fecha, "hasta": j.fecha, "dias": 0})
        ficha["hasta"] = max(ficha["hasta"], j.fecha)
        ficha["desde"] = min(ficha["desde"], j.fecha)
        ficha["dias"] += 1

    return [{**f, "desde": f["desde"].isoformat(), "hasta": f["hasta"].isoformat()}
            for f in sorted(por_servicio.values(), key=lambda f: f["desde"])]


# ------------------------------------------------------------ las acciones

def _ficha(usuario: m.Usuario, resultado: str, **extra) -> dict:
    return {
        "resultado": resultado,
        "usuario_id": usuario.id,
        "nombre": usuario.persona.nombre if usuario.persona else None,
        "correo": usuario.correo,
        "rol": usuario.rol.value,
        "activo": usuario.activo,
        **extra,
    }


def desactivar(db: Session, usuario_id: int, actor: m.Usuario,
               motivo: str | None = None) -> dict:
    """Le cierra la puerta. La sesion que tenga abierta muere en su
    siguiente clic."""
    usuario = _obtener(db, usuario_id)
    _no_sobre_si_mismo(actor, usuario, "desactivar")
    if usuario.rol in ALTOS:
        solo_direccion(actor, "Cerrar el acceso de Dirección general o de "
                               "administración")
    _no_es_el_ultimo_admin(db, usuario, "desactivar este acceso")

    if not usuario.activo:
        raise HTTPException(409, "Ese acceso ya estaba desactivado")

    # El que trae dinero de la empresa no se va hasta comprobarlo. Es la
    # misma regla que ya impedia sacarla de un servicio; faltaba de este
    # lado, donde se cierra la puerta de verdad.
    debiendo = viaticos_sin_cerrar(db, usuario.persona_id)
    if debiendo:
        pendiente = sum(f["monto"] - f["comprobado"] for f in debiendo)
        raise HTTPException(409, {
            "mensaje": (f"No se le puede cerrar el acceso: tiene "
                        f"{len(debiendo)} viatico(s) sin cerrar, por "
                        f"{pendiente:,.2f}."),
            "que_hacer": "Tiene que terminar su ciclo: comprobar lo que "
                         "recibio. Si ya no va a volver, finanzas puede "
                         "cerrarlo con el ajuste que corresponda.",
            "viaticos": debiendo,
        })
    # El titular de servicios vivos tampoco (decision 13, seccion 105):
    # sus servicios se quedarian avisandole a quien ya no esta.
    no_se_va_siendo_titular(db, usuario.persona)

    usuario.activo = False
    anotar(db, actor, "acceso desactivado", "usuario", usuario.id,
           antes="activo", despues="desactivado", detalle=motivo)
    db.flush()

    # Estaba asignada pero sin dinero de por medio: no afecta a la
    # operacion. Se va, y el consultor asigna a alguien mas. No se
    # desasigna nada aqui: solo se dice lo que queda colgando.
    pendientes = jornadas_por_cubrir(db, usuario.persona_id)
    return _ficha(usuario, "desactivado",
                  sesion_cortada=True,
                  jornadas_por_cubrir=pendientes,
                  aviso=(f"Sigue asignado a {sum(f['dias'] for f in pendientes)} "
                         f"dia(s) en {len(pendientes)} servicio(s). Hay que "
                         f"cubrirlos." if pendientes else None))


def reactivar(db: Session, usuario_id: int, actor: m.Usuario,
              motivo: str | None = None) -> dict:
    """Le vuelve a abrir la puerta. No sirve para revivir a quien ya no
    trabaja aqui."""
    usuario = _obtener(db, usuario_id)
    if usuario.activo:
        raise HTTPException(409, "Ese acceso ya estaba activo")
    if usuario.rol in ALTOS:
        solo_direccion(actor, "Abrir de nuevo el acceso de Dirección general "
                               "o de administración")

    # Si la persona esta dada de baja, reactivar su acceso seria abrirle
    # la puerta a alguien que ya no trabaja aqui. Primero se corrige la
    # baja donde vive, que es Odoo.
    if usuario.persona and not usuario.persona.activo:
        raise HTTPException(409, {
            "mensaje": "Esa persona esta dada de baja.",
            "que_hacer": "Si volvio, reactivala primero como empleada. El "
                         "acceso no puede ser la puerta de atras de una baja.",
        })

    usuario.activo = True
    anotar(db, actor, "acceso reactivado", "usuario", usuario.id,
           antes="desactivado", despues="activo", detalle=motivo)
    db.flush()
    return _ficha(usuario, "reactivado")


def cambiar_rol(db: Session, usuario_id: int, rol: m.Rol, actor: m.Usuario,
                motivo: str | None = None) -> dict:
    """Le cambia el puesto. Es la operacion mas delicada del sistema: del
    rol sale todo lo que esa persona puede tocar."""
    usuario = _obtener(db, usuario_id)
    _no_sobre_si_mismo(actor, usuario, "cambiar el rol")

    if usuario.rol == rol:
        raise HTTPException(409, f"Ya tiene el rol {rol.value}")
    # Con un puesto que dice su rol, el rol es del puesto (seccion 73):
    # cambiarlo a mano dejaria a un monitorista recibiendo los avisos de
    # finanzas con los permisos de monitorista.
    if usuario.categoria and usuario.categoria.rol:
        raise HTTPException(409, {
            "mensaje": (f"Su rol lo pone su puesto, "
                        f"{usuario.categoria.nombre}."),
            "que_hacer": "Cámbiale el puesto, o quítaselo primero.",
        })
    # Seccion 83: direccion general y administracion, y el poder de
    # repartir accesos que trae un rol sin puesto.
    if rol in ALTOS or usuario.rol in ALTOS:
        solo_direccion(actor, "Hacer a alguien Dirección general o "
                               "administración, o quitárselo,")
    # Con puesto o sin el: el rol queda debajo del puesto, y en cuanto
    # el puesto se quite manda el rol. Revisado solo sin puesto, un
    # puesto sin rol servia de escondite para cambiar el rol a uno que
    # reparte y quitar el puesto despues (seccion 100).
    if reparte_de_fabrica(rol) or reparte_de_fabrica(usuario.rol):
        solo_direccion(actor, "Darle o quitarle a alguien el poder de "
                               "repartir accesos")
    if rol not in ALTOS:
        _no_es_el_ultimo_admin(db, usuario, "quitarle ese rol")

    antes = usuario.rol
    usuario.rol = rol
    anotar(db, actor, "rol cambiado", "usuario", usuario.id,
           antes=antes.value, despues=rol.value, detalle=motivo)
    db.flush()

    # El rol viaja dentro del token, pero nadie lo lee de ahi: cada
    # peticion vuelve a buscar al usuario. Asi que el cambio manda desde
    # el siguiente clic, sin cerrarle la sesion.
    return _ficha(usuario, "rol cambiado", antes=antes.value,
                  surte_efecto="en su siguiente peticion")


def historial(db: Session, usuario_id: int, limite: int = 50) -> list[dict]:
    """Lo que se le ha hecho a ese acceso, y quien."""
    filas = (db.query(m.RegistroAdmin)
             .filter_by(objeto="usuario", objeto_id=usuario_id)
             .order_by(m.RegistroAdmin.creado_en.desc())
             .limit(limite).all())
    return [{
        "accion": r.accion, "antes": r.antes, "despues": r.despues,
        "detalle": r.detalle,
        "quien": r.persona.nombre if r.persona else None,
        "rol_de_quien": r.rol.value,
        "cuando": r.creado_en.isoformat() if r.creado_en else None,
    } for r in filas]


# ==================================================================
# Las categorias: un puesto configurable
# ==================================================================

def _existe(actividad: str) -> None:
    """Una actividad que no existe seria una casilla que no hace nada.

    Peor: se guardaria sin protestar y el dia que alguien la necesite,
    la puerta estaria cerrada para el y nadie sabria por que.
    """
    from app import permisos
    if actividad not in permisos.ACTIVIDADES:
        raise HTTPException(400, {
            "mensaje": f"No existe la actividad '{actividad}'.",
            "que_hacer": "Las actividades las declara el sistema. Si falta "
                         "una, se agrega en el codigo primero.",
        })


def catalogo_de_actividades() -> list[dict]:
    """Lo que se puede repartir, con su descripcion.

    La descripcion es la que ve quien decide que le da a quien, asi que
    esta escrita pensando en el, no en el endpoint.
    """
    from app import permisos
    return permisos.catalogo()


def _ficha_categoria(db: Session, c: m.CategoriaAcceso) -> dict:
    gente = db.query(m.Usuario).filter_by(categoria_id=c.id).count()
    return {
        "categoria_id": c.id,
        "nombre": c.nombre,
        "descripcion": c.descripcion,
        "horas_sesion": c.horas_sesion,
        "activa": c.activa,
        "personas": gente,
        "actividades": sorted(a.actividad for a in c.actividades),
        # Seccion 73: con que rol entra quien lo trae, que le sale en el
        # menu y a que puestos de Odoo se parece.
        "rol": c.rol.value if c.rol else None,
        "area": c.area,
        "pantallas": ([x for x in c.pantallas.split(",") if x]
                      if c.pantallas else None),
        "puestos_odoo": c.puestos_odoo,
        "orden": c.orden,
        # Seccion 83: si reparte accesos. Ese puesto solo lo cambia y lo
        # da direccion general, y la pantalla no ofrece lo que no se puede.
        "reparte": trae_reparte(c),
    }


def categorias(db: Session) -> list[dict]:
    """Por su orden --el del organigrama-- y los que no tienen, al final
    por nombre."""
    filas = (db.query(m.CategoriaAcceso)
             .order_by(m.CategoriaAcceso.orden.is_(None),
                       m.CategoriaAcceso.orden, m.CategoriaAcceso.nombre)
             .all())
    return [_ficha_categoria(db, c) for c in filas]


def _pantallas(pantallas: list[str] | None) -> str | None:
    """La lista de pantallas como se guarda. Una clave que el menu no
    conoce no se guarda: seria una casilla que no hace nada."""
    from app import permisos
    if pantallas is None:
        return None
    for clave in pantallas:
        if clave not in permisos.PANTALLAS:
            raise HTTPException(400, {
                "mensaje": f"No existe la pantalla '{clave}'.",
                "que_hacer": "Las pantallas son las del menu de la consola.",
            })
    # En el orden del menu, sin repetir: asi se lee igual en todos lados.
    puestas = set(pantallas)
    return ",".join(c for c in permisos.PANTALLAS if c in puestas) or None


def _rol_de_puesto(rol) -> m.Rol | None:
    """El de campo no entra por la consola: un puesto con ese rol dejaria
    a alguien con menu de oficina y sin nada que abrir.

    Y direccion general y administracion entran con su rol, sin puesto
    (seccion 73): la primera puede todo --un puesto con todo juntaria lo
    que no puede vivir en la misma mano-- y la segunda pasa cualquier
    candado, asi que su lista no le quitaria nada. Un puesto con esos
    roles seria, ademas, la forma de hacer administrador a alguien sin
    que se viera como tal."""
    if rol is None:
        return None
    rol = m.Rol(rol)
    if rol == m.Rol.PERSONAL_SEGURIDAD:
        raise HTTPException(400, {
            "mensaje": "Un puesto no entra como personal de seguridad.",
            "que_hacer": "El personal de seguridad entra por la app, "
                         "con su rol; los puestos son de la consola.",
        })
    if rol in (m.Rol.ADMIN, m.Rol.DIRECTOR_GENERAL):
        raise HTTPException(400, {
            "mensaje": "Dirección general y administración entran con su "
                       "rol, sin puesto.",
            "que_hacer": "Escoge otro rol base para el puesto.",
        })
    return rol


def crear_categoria(db: Session, actor: m.Usuario, nombre: str,
                    actividades: list[str], descripcion: str | None = None,
                    horas_sesion: int | None = None, rol=None,
                    area: str | None = None,
                    pantallas: list[str] | None = None,
                    puestos_odoo: str | None = None,
                    orden: int | None = None) -> dict:
    nombre = (nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "La categoria necesita un nombre")
    if db.query(m.CategoriaAcceso).filter_by(nombre=nombre).first():
        raise HTTPException(409, f"Ya existe una categoria '{nombre}'")
    for a in actividades:
        _existe(a)
    _no_juntarlas_en_un_puesto(set(actividades))
    if REPARTE in actividades:
        solo_direccion(actor, "Armar un puesto que reparte accesos")

    categoria = m.CategoriaAcceso(nombre=nombre, descripcion=descripcion,
                                  horas_sesion=horas_sesion,
                                  rol=_rol_de_puesto(rol),
                                  area=(area or "").strip() or None,
                                  pantallas=_pantallas(pantallas),
                                  puestos_odoo=(puestos_odoo or "").strip()
                                  or None,
                                  orden=orden)
    db.add(categoria)
    db.flush()
    for a in sorted(set(actividades)):
        db.add(m.ActividadDeCategoria(categoria_id=categoria.id, actividad=a))
    anotar(db, actor, "categoria creada", "categoria", categoria.id,
           despues=nombre, detalle=f"{len(set(actividades))} actividad(es)")
    db.flush()
    return _ficha_categoria(db, categoria)


def _ni_con_los_permisos_de_su_gente(db: Session, categoria: m.CategoriaAcceso,
                                     nuevas: set) -> None:
    """Las dos manos tampoco se juntan por este camino (seccion 100).

    Se cuidaban al armar el puesto, al repartirlo y al dar un permiso
    de mas; faltaba al EDITAR un puesto que alguien ya trae: con
    "autorizar bonos" como permiso de mas, agregarle "pagar bonos" al
    puesto dejaba a esa persona autorizando y depositando el bono.
    """
    from app import permisos
    gente = (db.query(m.Usuario)
             .filter(m.Usuario.categoria_id == categoria.id,
                     m.Usuario.activo.is_(True)).all())
    for usuario in gente:
        extras = {x.actividad for x in db.query(m.PermisoExtra)
                  .filter_by(usuario_id=usuario.id).all()}
        for suelto in sorted(extras):
            choque = permisos.choca_con(suelto) & nuevas
            if choque:
                quien = usuario.persona.nombre if usuario.persona else usuario.correo
                raise HTTPException(409, {
                    "mensaje": (f"'{sorted(choque)[0]}' no puede convivir con "
                                f"'{suelto}', que {quien} trae como permiso "
                                f"de mas con este puesto."),
                    "que_hacer": "Quitale primero ese permiso de mas, o "
                                 "deja el puesto como esta.",
                })


def cambiar_categoria(db: Session, actor: m.Usuario, categoria_id: int,
                      **cambios) -> dict:
    """Cambia una categoria. Lo que no se manda, no se toca."""
    categoria = db.get(m.CategoriaAcceso, categoria_id)
    if not categoria:
        raise HTTPException(404, f"No existe la categoria {categoria_id}")
    # Seccion 83: el puesto propio no, y el que reparte accesos --o el
    # que quedaria repartiendolos-- solo direccion general.
    _no_es_su_puesto(actor, categoria)
    nuevas = cambios.get("actividades")
    if trae_reparte(categoria) or (nuevas is not None and REPARTE in nuevas):
        solo_direccion(actor, "Cambiar un puesto que reparte accesos")

    antes = sorted(a.actividad for a in categoria.actividades)
    # Cambiarle el nombre se puede, pero no al de otro puesto ni a nada:
    # la pantalla ahora trae el nombre en el mismo formulario, y un
    # duplicado reventaba en la base en vez de decirse.
    if "nombre" in cambios:
        nombre = (cambios["nombre"] or "").strip()
        cambios["nombre"] = nombre or None
        if nombre and nombre != categoria.nombre and (
                db.query(m.CategoriaAcceso)
                .filter(m.CategoriaAcceso.nombre == nombre,
                        m.CategoriaAcceso.id != categoria.id).first()):
            raise HTTPException(409, f"Ya existe un puesto '{nombre}'")
    for campo in ("nombre", "descripcion", "horas_sesion", "activa", "orden"):
        if cambios.get(campo) is not None:
            setattr(categoria, campo, cambios[campo])
    # Lo de la seccion 73. Aqui "vacio" si significa algo --quitarle las
    # pantallas es volver al menu de su rol--, asi que se mira si vino, no
    # si trae valor.
    if "rol" in cambios and cambios["rol"] is not None:
        nuevo_rol = _rol_de_puesto(cambios["rol"])
        if nuevo_rol != categoria.rol:
            _el_rol_de_su_gente(db, actor, categoria, nuevo_rol)
        categoria.rol = nuevo_rol
    if "area" in cambios:
        categoria.area = (cambios["area"] or "").strip() or None
    if "pantallas" in cambios:
        categoria.pantallas = _pantallas(cambios["pantallas"])
    if "puestos_odoo" in cambios:
        categoria.puestos_odoo = (cambios["puestos_odoo"] or "").strip() or None

    actividades = cambios.get("actividades")
    if actividades is not None:
        for a in actividades:
            _existe(a)
        _no_juntarlas_en_un_puesto(set(actividades))
        _ni_con_los_permisos_de_su_gente(db, categoria, set(actividades))
        for fila in list(categoria.actividades):
            db.delete(fila)
        db.flush()
        for a in sorted(set(actividades)):
            db.add(m.ActividadDeCategoria(categoria_id=categoria.id,
                                          actividad=a))
        db.flush()
        db.refresh(categoria)

    ahora = sorted(a.actividad for a in categoria.actividades)
    # Se escribe lo que cambio y no el estado entero: un ano despues, lo
    # que alguien busca es que se le quito a esa categoria y cuando.
    quitadas = [a for a in antes if a not in ahora]
    puestas = [a for a in ahora if a not in antes]
    anotar(db, actor, "categoria cambiada", "categoria", categoria.id,
           antes=", ".join(quitadas)[:200] or None,
           despues=", ".join(puestas)[:200] or None,
           detalle=categoria.nombre)
    db.flush()
    return _ficha_categoria(db, categoria)


def poner_categoria(db: Session, actor: m.Usuario, usuario_id: int,
                    categoria_id: int | None, motivo: str | None = None,
                    recien_dado: bool = False) -> dict:
    """Le pone o le quita la categoria a una persona.

    Sin categoria vuelve a los permisos de su rol, que es de donde salio.

    `recien_dado`: el acceso se acaba de dar con este puesto, y el alta ya
    reviso que quien lo da pueda darlo. En ese instante la persona trae el
    rol del puesto sin el puesto, y ese rol puede repartir accesos de
    fabrica --Capacitacion entra como recursos humanos--: no es alguien
    que ya reparta.
    """
    usuario = _obtener(db, usuario_id)
    _tambien_se_lo_daria_a_si_mismo(actor, usuario)
    if usuario.rol in ALTOS:
        solo_direccion(actor, "Ponerle o quitarle un puesto a Dirección "
                               "general o a administración")
    categoria = None
    if categoria_id is not None:
        categoria = db.get(m.CategoriaAcceso, categoria_id)
        if not categoria:
            raise HTTPException(404, f"No existe la categoria {categoria_id}")
    # Seccion 83: dar el puesto que reparte accesos, o cambiarle el suyo a
    # quien ya los reparte. Y lo que QUEDARIA pudiendo (seccion 100): sin
    # puesto vuelve a su rol, y si ese rol reparte de fabrica --recursos
    # humanos-- quitarle el puesto es darle el poder. Mirando solo lo que
    # podia antes, se esquivaba dandole Capacitacion y quitandoselo.
    if ((categoria is not None and trae_reparte(categoria))
            or (not recien_dado and reparte(db, usuario))
            or (categoria is None and reparte_de_fabrica(usuario.rol))):
        solo_direccion(actor, "Darle o quitarle a alguien el poder de "
                               "repartir accesos")
    if categoria is not None:
        # El puesto reemplaza a su rol y a su puesto de antes: lo que hay
        # que revisar contra lo nuevo son solo sus permisos de mas. Contado
        # contra todo lo que ya podia, a quien entraba como finanzas --que
        # de fabrica arma y paga la nomina-- no se le podia poner el puesto
        # de Nomina, que justo le quita pagar (seccion 73).
        nuevas = {x.actividad for x in db.query(m.ActividadDeCategoria)
                  .filter_by(categoria_id=categoria.id).all()}
        extras = {x.actividad for x in db.query(m.PermisoExtra)
                  .filter_by(usuario_id=usuario.id).all()}
        from app import permisos
        for suelto in sorted(extras):
            choque = permisos.choca_con(suelto) & nuevas
            if choque:
                raise HTTPException(409, {
                    "mensaje": (f"Su permiso de mas '{suelto}' no puede "
                                f"convivir con '{sorted(choque)[0]}', que "
                                f"trae el puesto {categoria.nombre}."),
                    "que_hacer": "Quitale primero ese permiso de mas, o "
                                 "dale otro puesto.",
                })

    antes = usuario.categoria.nombre if usuario.categoria else None
    usuario.categoria_id = categoria.id if categoria else None
    anotar(db, actor, "categoria asignada", "usuario", usuario.id,
           antes=antes, despues=categoria.nombre if categoria else None,
           detalle=motivo)
    # Y entra con el rol de su puesto: de ahi salen los avisos que le
    # llegan y en que listas aparece (seccion 73).
    if categoria is not None and categoria.rol and categoria.rol != usuario.rol:
        _ponerle_su_rol(db, actor, usuario, categoria.rol, categoria.nombre)
    db.flush()
    return _ficha(usuario, "categoria asignada",
                  categoria=categoria.nombre if categoria else None)


def _ponerle_su_rol(db: Session, actor: m.Usuario, usuario: m.Usuario,
                    rol: m.Rol, puesto: str) -> None:
    """El rol que le toca por su puesto, con los mismos candados que un
    cambio de rol a mano: no sobre uno mismo --eso ya se reviso antes--
    y no dejar al sistema sin administracion."""
    if rol not in ALTOS:
        _no_es_el_ultimo_admin(db, usuario, "quitarle ese rol")
    antes = usuario.rol
    usuario.rol = rol
    anotar(db, actor, "rol cambiado", "usuario", usuario.id,
           antes=antes.value, despues=rol.value,
           detalle=f"por su puesto: {puesto}")


def _el_rol_de_su_gente(db: Session, actor: m.Usuario,
                        categoria: m.CategoriaAcceso, rol: m.Rol) -> None:
    """Cambiarle el rol a un puesto se lo cambia a quien ya lo trae."""
    for u in db.query(m.Usuario).filter_by(categoria_id=categoria.id).all():
        if u.rol != rol:
            _tambien_se_lo_daria_a_si_mismo(actor, u)
            _ponerle_su_rol(db, actor, u, rol, categoria.nombre)


def dar_permiso(db: Session, actor: m.Usuario, usuario_id: int,
                actividad: str, motivo: str | None = None) -> dict:
    """Un permiso de mas, encima de su categoria.

    Solo da. Para quitar se le hace una categoria que no lo traiga: una
    excepcion que quitara dejaria su renglon diciendo "Consultor" cuando
    no lo es, y para saber que puede habria que abrir su ficha y
    acordarse de que existe.
    """
    usuario = _obtener(db, usuario_id)
    _tambien_se_lo_daria_a_si_mismo(actor, usuario)
    _existe(actividad)
    # Seccion 83: el permiso de repartir accesos, y cualquier permiso de
    # mas a quien ya los reparte, solo los da direccion general.
    if actividad == REPARTE or reparte(db, usuario):
        solo_direccion(actor, "Darle un permiso de más a quien reparte "
                               "accesos, o el de repartirlos,")
    if db.query(m.PermisoExtra).filter_by(usuario_id=usuario.id,
                                          actividad=actividad).first():
        raise HTTPException(409, "Ya tiene ese permiso de mas")
    _no_juntar_incompatibles(db, usuario, {actividad})

    db.add(m.PermisoExtra(usuario_id=usuario.id, actividad=actividad,
                          dado_por_id=actor.persona_id, motivo=motivo))
    anotar(db, actor, "permiso de mas dado", "usuario", usuario.id,
           despues=actividad, detalle=motivo)
    db.flush()
    return _ficha(usuario, "permiso dado", actividad=actividad)


def quitar_permiso(db: Session, actor: m.Usuario, usuario_id: int,
                   actividad: str) -> dict:
    usuario = _obtener(db, usuario_id)
    if actividad == REPARTE or reparte(db, usuario):
        solo_direccion(actor, "Quitarle un permiso de más a quien reparte "
                               "accesos")
    fila = (db.query(m.PermisoExtra)
            .filter_by(usuario_id=usuario.id, actividad=actividad).first())
    if not fila:
        raise HTTPException(404, "No tiene ese permiso de mas")
    db.delete(fila)
    anotar(db, actor, "permiso de mas quitado", "usuario", usuario.id,
           antes=actividad)
    db.flush()
    return _ficha(usuario, "permiso quitado", actividad=actividad)


def permisos_de(db: Session, usuario_id: int) -> dict:
    """Todo lo que esta persona puede, y de donde le viene cada cosa.

    Es la pantalla que contesta "por que Beatriz no puede": se ve de un
    golpe si viene de su categoria, de su rol o de un permiso suelto.
    """
    from app import permisos as tabla
    usuario = _obtener(db, usuario_id)
    extras = {p.actividad for p in db.query(m.PermisoExtra)
              .filter_by(usuario_id=usuario.id).all()}
    de_categoria = set()
    if usuario.categoria_id:
        de_categoria = {a.actividad for a in
                        db.query(m.ActividadDeCategoria)
                        .filter_by(categoria_id=usuario.categoria_id).all()}

    salida = []
    for entrada in tabla.catalogo():
        nombre = entrada["actividad"]
        if nombre in extras:
            origen = "permiso de mas"
        elif usuario.categoria_id:
            origen = "categoria" if nombre in de_categoria else None
        else:
            origen = "rol" if usuario.rol.value in entrada["roles"] else None
        salida.append({**entrada, "puede": origen is not None,
                       "de_donde": origen})
    return {
        "usuario_id": usuario.id,
        "nombre": usuario.persona.nombre if usuario.persona else None,
        "rol": usuario.rol.value,
        "categoria": usuario.categoria.nombre if usuario.categoria else None,
        "actividades": salida,
    }

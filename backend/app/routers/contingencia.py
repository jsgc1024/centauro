"""Alertas durante el servicio y cambio de recurso por contingencia.

La central atiende la alerta y estabiliza el servicio; el consultor
formaliza el cambio de recurso. Son dos permisos distintos a proposito.
"""
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auditoria, auth, contingencia as motor
from app import emergencias
from app import reloj
from app import models as m
from app import operacion
from app import push
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/contingencia", tags=["Contingencia"])
registro = logging.getLogger("centauro.contingencia")

# La app del agente no se muda a actividades. El candado de ahi no es un
# permiso repartible sino "es su propia jornada": como casilla del panel
# seria una que nadie debe marcar nunca, y el dia que alguien la marcara
# por curiosidad le abriria la app del campo a gente de oficina.
CAMPO = auth.requiere(m.Rol.PERSONAL_SEGURIDAD)

CENTRAL = auth.puede("contingencia.atender")
CONSULTOR = auth.puede("relevos.mover")
LECTURA = auth.puede("contingencia.ver")


def _servicio_de(db: Session, alerta: m.AlertaIncidencia):
    if alerta.jornada_id:
        jornada = db.get(m.Jornada, alerta.jornada_id)
        if jornada:
            return jornada.equipo.servicio
    if alerta.servicio_id:
        return db.get(m.Servicio, alerta.servicio_id)
    return None


@router.post("/alertas", response_model=s.AlertaOut, status_code=201,
             summary="Reportar una incidencia durante el servicio")
def reportar(datos: s.AlertaIn, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(auth.usuario_actual)):
    """Los tres canales entran por aqui.

    El boton de panico de la app manda canal=boton_app y casi nunca trae
    descripcion: quien lo aprieta no esta para escribir. Por eso la
    ubicacion importa tanto. La llamada la captura la central.
    """
    # Quien reporta es quien tiene la sesion abierta, siempre, y no lo
    # que diga el cuerpo. Aceptarlo del cuerpo permitia levantar un
    # panico a nombre de otro elemento, en un servicio ajeno y con
    # coordenadas inventadas —y un panico mueve equipo de respuesta.
    # La central sigue pudiendo capturar la llamada de alguien mas,
    # porque para eso tiene su propio rol.
    if usuario.rol == m.Rol.PERSONAL_SEGURIDAD:
        datos.reporta_persona_id = usuario.persona_id
    elif not datos.reporta_persona_id:
        datos.reporta_persona_id = usuario.persona_id

    # El panico del cliente de la Central solo nace en su app (seccion
    # 145): por aqui seria una alerta de EP escondida de la central.
    if datos.canal == m.CanalAlerta.BOTON_CI:
        raise HTTPException(400, "Ese canal es de la app del cliente de la "
                                 "Central")

    # El boton de panico pasa SIN servicio. Todo lo demas lo exige.
    #
    # La app siempre lo dijo --"manda la alerta sin jornada, que es mejor
    # que no mandarla"-- y este renglon hacia lo contrario: el boton
    # aparecia, se tocaba, y no mandaba nada. Encontrado en la calle el
    # 21 de septiembre, probando con una cuenta sin jornada asignada.
    #
    # Exigir servicio en un boton de panico es fallar EXACTAMENTE cuando
    # los datos estan incompletos, que es cuando las cosas salen mal de
    # verdad: el escolta que va en camino y todavia no tiene jornada, el
    # servicio que se cancelo con la gente aun en la calle, el mes que
    # nadie genero, el que va fuera de turno en una unidad de la casa.
    # La alerta sin servicio sigue sirviendo: trae quien, donde y cuando,
    # que es lo que necesita un equipo de respuesta. El servicio es
    # contexto util, no un requisito.
    #
    # El reporte de incidencia SI lo exige y no se afloja: ese describe
    # algo que le paso a un servicio, y sin servicio no se puede atender
    # ni cobrar ni analizar despues.
    if not datos.jornada_id and not datos.servicio_id:
        if datos.canal != m.CanalAlerta.BOTON_APP:
            raise HTTPException(400, {
                "mensaje": "Hay que decir a que jornada o servicio pertenece",
                "que_hacer": "Solo el boton de panico de la app puede "
                             "levantar una alerta sin servicio."})

    if datos.jornada_id and not db.get(m.Jornada, datos.jornada_id):
        raise HTTPException(404, f"No existe la jornada {datos.jornada_id}")

    # Y un elemento solo levanta alertas de los servicios en los que va.
    # Las dos puertas: la jornada y el servicio. Cerrar solo una dejaba
    # la otra abierta, que es como se cuela casi siempre.
    if usuario.rol == m.Rol.PERSONAL_SEGURIDAD:
        if datos.jornada_id:
            if not auth.es_su_propia_jornada(db, usuario, datos.jornada_id):
                raise HTTPException(403, "No estas asignado a esa jornada")
        elif datos.servicio_id:
            suyo = (db.query(m.AsignacionPersonal)
                    .join(m.Jornada,
                          m.AsignacionPersonal.jornada_id == m.Jornada.id)
                    .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                    .filter(m.Equipo.servicio_id == datos.servicio_id,
                            m.AsignacionPersonal.persona_id
                            == usuario.persona_id)
                    .first())
            if not suyo:
                raise HTTPException(403, "No participas en ese servicio")

    alerta = m.AlertaIncidencia(**datos.model_dump())
    if alerta.jornada_id and not alerta.servicio_id:
        alerta.servicio_id = db.get(m.Jornada, alerta.jornada_id).equipo.servicio_id
    db.add(alerta)
    db.flush()
    # La primera lectura del recorrido que ve Respuesta a emergencias
    # (seccion 145); las que siguen las manda la app cada 15 segundos.
    if alerta.lat is not None and alerta.lon is not None:
        emergencias.poner_punto(db, alerta, alerta.lat, alerta.lon)

    servicio = _servicio_de(db, alerta)
    if servicio:
        auditoria.registrar(db, usuario, servicio, "alerta de incidencia",
                            f"canal {alerta.canal.value}",
                            jornada_id=alerta.jornada_id)
    db.commit()
    db.refresh(alerta)
    return alerta


@router.get("/alertas", response_model=list[s.AlertaOut],
            summary="Tablero de alertas de la central")
def listar(abiertas: bool = True, servicio_id: int | None = None,
           db: Session = Depends(get_db), _=Depends(LECTURA)):
    """`servicio_id` es para la pantalla del servicio (seccion 101): el
    panel del cambio por contingencia busca la alerta abierta de ese
    servicio para ligarla al cambio."""
    # El panico del cliente de la Central (seccion 145) no sale aqui: no
    # es de un servicio y lo atiende Respuesta a emergencias en su panel.
    consulta = db.query(m.AlertaIncidencia).filter(
        m.AlertaIncidencia.canal != m.CanalAlerta.BOTON_CI)
    if abiertas:
        consulta = consulta.filter(
            m.AlertaIncidencia.estatus != m.EstatusAlerta.CERRADA)
    if servicio_id is not None:
        consulta = consulta.filter(
            m.AlertaIncidencia.servicio_id == servicio_id)
    filas = consulta.order_by(m.AlertaIncidencia.reportada_en.desc()).all()

    # Que paso despues de la alerta. Una alerta atendida que dejo un
    # cambio de recurso y una que no se leen distinto: la central ve si
    # el consultor ya hizo lo suyo.
    cambios = {}
    for r in (db.query(m.ReemplazoRecurso)
              .filter(m.ReemplazoRecurso.alerta_id.isnot(None)).all()):
        cambios[r.alerta_id] = motor.quien_entra_por_quien(db, r)

    for fila in filas:
        fila.cambio = cambios.get(fila.id)
    return filas


@router.post("/alertas/{alerta_id}/tomar", response_model=s.AlertaOut,
             summary="La central toma la alerta")
def tomar(alerta_id: int, datos: s.TomarAlertaIn, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(CENTRAL)):
    # De una en una, y sin pisar a Respuesta a emergencias (seccion 145):
    # la tarjeta de la central se refresca cada minuto y puede seguir
    # ofreciendo «Tomar» sobre un panico que el area ya tomo.
    alerta = (db.query(m.AlertaIncidencia).filter_by(id=alerta_id)
              .with_for_update().first())
    if not alerta or alerta.canal == m.CanalAlerta.BOTON_CI:
        raise HTTPException(404, f"No existe la alerta {alerta_id}")
    if alerta.estatus == m.EstatusAlerta.CERRADA:
        raise HTTPException(409, "Esa alerta ya esta cerrada")
    if alerta.estatus == m.EstatusAlerta.EN_ATENCION \
            and alerta.tomada_por_id != usuario.persona_id:
        raise HTTPException(409, {
            "mensaje": "Esa alerta ya la atiende "
                       + (emergencias.atiende(db, alerta) or "alguien mas"),
            "que_hacer": "Recarga el tablero."})

    alerta.estatus = m.EstatusAlerta.EN_ATENCION
    alerta.tomada_por_id = usuario.persona_id
    alerta.tomada_en = datetime.now()
    # Lo que ya se hizo no se deshace: si el area ya mando al equipo,
    # tomarla otra vez no lo regresa.
    alerta.equipo_respuesta_enviado = (bool(alerta.equipo_respuesta_enviado)
                                       or datos.equipo_respuesta_enviado)
    if datos.nota:
        alerta.descripcion = " · ".join(filter(None, [alerta.descripcion,
                                                     datos.nota]))[:600]

    # Y en la bitacora de la alerta, que lee Respuesta a emergencias
    # (seccion 145): quien la tomo, aunque haya sido la central.
    emergencias.anotar(db, alerta, usuario, "tomo",
                       "Desde la central" + (" · con equipo de respuesta"
                                             if datos.equipo_respuesta_enviado
                                             else ""))

    servicio = _servicio_de(db, alerta)
    if servicio:
        auditoria.registrar(
            db, usuario, servicio, "alerta tomada por la central",
            "con equipo de respuesta" if datos.equipo_respuesta_enviado else "",
            jornada_id=alerta.jornada_id)
    db.commit()
    db.refresh(alerta)
    return alerta


@router.post("/alertas/{alerta_id}/cerrar", response_model=s.AlertaOut,
             summary="Cerrar la alerta con su resolucion")
def cerrar(alerta_id: int, datos: s.CerrarAlertaIn, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(CENTRAL)):
    alerta = (db.query(m.AlertaIncidencia).filter_by(id=alerta_id)
              .with_for_update().first())
    if not alerta or alerta.canal == m.CanalAlerta.BOTON_CI:
        raise HTTPException(404, f"No existe la alerta {alerta_id}")
    if alerta.estatus == m.EstatusAlerta.ABIERTA:
        raise HTTPException(409, "Primero hay que tomarla, luego cerrarla")
    if alerta.estatus == m.EstatusAlerta.CERRADA:
        raise HTTPException(409, "Esa alerta ya esta cerrada")

    alerta.estatus = m.EstatusAlerta.CERRADA
    alerta.resolucion = datos.resolucion
    alerta.cerrada_por_id = usuario.persona_id
    alerta.cerrada_en = datetime.now()
    emergencias.anotar(db, alerta, usuario, "cerro",
                       f"Desde la central · {datos.resolucion}")

    servicio = _servicio_de(db, alerta)
    if servicio:
        auditoria.registrar(db, usuario, servicio, "alerta cerrada",
                            datos.resolucion[:120],
                            jornada_id=alerta.jornada_id)
    db.commit()
    db.refresh(alerta)
    return alerta


class UbicacionIn(BaseModel):
    lat: float
    lon: float
    precision: float | None = None


@router.post("/alertas/{alerta_id}/ubicacion",
             summary="Donde va quien apreto el panico, cada pocos segundos")
def ubicacion(alerta_id: int, datos: UbicacionIn,
              db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(CAMPO)):
    """La app de campo la manda mientras la alerta esta abierta (seccion
    145). Solo quien la levanto; cerrada, contesta 409 y la app deja de
    mandar."""
    alerta = db.get(m.AlertaIncidencia, alerta_id)
    if not alerta or usuario.persona_id is None \
            or alerta.reporta_persona_id != usuario.persona_id \
            or alerta.canal != m.CanalAlerta.BOTON_APP:
        raise HTTPException(404, "No existe esa alerta")
    if alerta.estatus == m.EstatusAlerta.CERRADA:
        raise HTTPException(409, "La alerta ya se cerró")
    emergencias.poner_punto(db, alerta, datos.lat, datos.lon,
                            datos.precision)
    db.commit()
    return {"estatus": alerta.estatus.value,
            "atiende": emergencias.atiende(db, alerta, para_quien_pidio=True)}


# ------------------------------------------------------- cambio de recurso

def _contarle_al_cliente(db: Session, jornada: m.Jornada, quien: str,
                         clase: str = "persona",
                         puesto: str | None = None) -> bool | None:
    """El aviso al cliente, que nunca puede tumbar el cambio.

    El reemplazo ya esta guardado cuando se llama a esto. Si escribir el
    aviso fallara --un correo mal capturado, un texto que no existe-- lo
    que no puede pasar es que la operacion pierda un cambio que ya dio
    por hecho: la central movio gente de verdad.

    Devuelve None cuando fallo, que la pantalla lee distinto de "no se
    aviso porque no tocaba": uno es una decision y el otro es un error.
    """
    try:
        return operacion.avisar_reemplazo(db, jornada, quien, clase=clase,
                                          puesto=puesto)
    except Exception:                     # noqa: BLE001
        # La sesion puede haber quedado sucia a medio aviso; se limpia
        # para que el commit de afuera no arrastre el destrozo.
        db.rollback()
        registro.exception(
            "no se pudo avisar del reemplazo de la jornada %s", jornada.id)
        return None


def _hoja_por_publicar(db: Session, jornada: m.Jornada,
                       cliente_avisado: bool | None) -> bool:
    """Si la hoja que el cliente ya tiene se quedo con el nombre viejo.

    Un cambio para otro dia no manda correo: "viaja en el task sheet".
    Pero la hoja que se publico es una foto de ese momento, y nadie la
    volvia a publicar ni se lo decia al consultor (seccion 101): el
    cliente llegaba el jueves con el nombre y el telefono de quien ya no
    va. Solo cuando no hubo correo --con correo el cliente ya tiene al
    equipo como queda-- y solo si hay hoja publicada que corregir.
    """
    from app import tasksheet
    return (cliente_avisado is False
            and tasksheet.vigente(db, jornada.equipo_id) is not None)


@router.post("/reemplazos/personal",
             summary="Cambiar a una persona del equipo por contingencia")
def reemplazo_personal(datos: s.ReemplazoPersonalIn,
                       db: Session = Depends(get_db),
                       ahora: datetime | None = None,
                       usuario: m.Usuario = Depends(CONSULTOR)):
    """Cambia a la persona de esa jornada en adelante y mueve los viaticos:
    quien sale entra a comprobacion con su plazo, quien entra recibe nuevos.

    `ahora` es el reloj del servidor para las pruebas (seccion 101): la
    hora del relevo se revisa contra el; en produccion se ignora."""
    resultado = motor.reemplazar_personal(
        db, datos.desde_jornada_id, datos.sale_persona_id,
        datos.entra_persona_id, datos.motivo,
        hecho_por_id=usuario.persona_id, alerta_id=datos.alerta_id,
        motivo_tipo=datos.motivo_tipo, hasta_jornada_id=datos.hasta_jornada_id,
        relevado_en=datos.relevado_en, ahora=reloj.de_prueba(ahora))

    jornada = db.get(m.Jornada, datos.desde_jornada_id)
    sale = db.get(m.Persona, datos.sale_persona_id)
    entra = db.get(m.Persona, datos.entra_persona_id)
    auditoria.registrar(
        db, usuario, jornada.equipo.servicio, "reemplazo de personal",
        f"entra {entra.nombre} en lugar de {sale.nombre}: {datos.motivo}",
        jornada_id=jornada.id)
    db.commit()

    # El aviso sale aqui y no en el recordatorio de la vispera: ese solo
    # mira manana, y un cambio hecho hoy para hoy nunca lo dispararia.
    # El caso urgente seria justo el que no avisa.
    resultado["avisado"] = push.avisar_relevo(db, entra, sale, resultado)
    # Y al cliente, si el cambio es de hoy o del dia en curso: el
    # ejecutivo tiene que poder reconocer a quien llega por el. Si es de
    # otro dia no sale nada, porque eso viaja en el task sheet.
    # El puesto sale de la asignacion, no de la persona: nadie tiene
    # puesto fijo --el mismo agente que hoy conduce manana coordina-- y
    # el que entra hereda el rol del que sale.
    nueva = (db.query(m.AsignacionPersonal)
             .filter_by(jornada_id=jornada.id, persona_id=entra.id,
                        relevado_en=None).first())
    resultado["cliente_avisado"] = _contarle_al_cliente(
        db, jornada, entra.nombre,
        puesto=nueva.rol.nombre if nueva and nueva.rol else None)
    # Sin correo, la hoja publicada se quedo con el nombre viejo: la
    # pantalla le dice al consultor que la vuelva a publicar.
    resultado["hoja_por_publicar"] = _hoja_por_publicar(
        db, jornada, resultado["cliente_avisado"])
    # `avisar` apaga las suscripciones de los telefonos que ya no
    # existen. Sin este guardado ese apagado se perdia y se les seguia
    # mandando a un telefono desinstalado para siempre.
    db.commit()
    return resultado


@router.post("/reemplazos/vehiculo",
             summary="Cambiar la unidad por contingencia")
def reemplazo_vehiculo(datos: s.ReemplazoVehiculoIn,
                       db: Session = Depends(get_db),
                       ahora: datetime | None = None,
                       usuario: m.Usuario = Depends(CONSULTOR)):
    resultado = motor.reemplazar_vehiculo(
        db, datos.desde_jornada_id, datos.sale_vehiculo_id,
        datos.entra_vehiculo_id, datos.motivo,
        hecho_por_id=usuario.persona_id, alerta_id=datos.alerta_id,
        motivo_tipo=datos.motivo_tipo, hasta_jornada_id=datos.hasta_jornada_id,
        relevado_en=datos.relevado_en, ahora=reloj.de_prueba(ahora))

    jornada = db.get(m.Jornada, datos.desde_jornada_id)
    sale = db.get(m.Vehiculo, datos.sale_vehiculo_id)
    entra = db.get(m.Vehiculo, datos.entra_vehiculo_id)
    auditoria.registrar(
        db, usuario, jornada.equipo.servicio, "reemplazo de unidad",
        f"entra {entra.placa} en lugar de {sale.placa}: {datos.motivo}",
        jornada_id=jornada.id)
    # El cambio primero. Si el aviso o la hoja fallaran, lo que no puede
    # pasar es que se deshaga un reemplazo que la operacion ya dio por
    # hecho.
    db.commit()

    # Sin correo al cliente. Decision 3 de Salvador (seccion 105): el
    # cambio de unidad se hace sin avisarle, a diferencia del cambio de
    # persona. Lo que si sale es el aviso al equipo --en que placa se
    # sube manana-- y la hoja publicada se vuelve a publicar con la
    # unidad nueva, sin escribirle a nadie, para que la vigente sea la
    # que va.
    resultado["cliente_avisado"] = False
    resultado.update(_despues_del_cambio_de_unidad(
        db, usuario, jornada, resultado["jornadas_afectadas"],
        sale.placa, entra.placa,
        f"Cambio de unidad por contingencia: entra {entra.placa} en lugar "
        f"de {sale.placa}"))
    db.commit()
    return resultado


def _despues_del_cambio_de_unidad(db: Session, usuario: m.Usuario,
                                  jornada: m.Jornada, fechas: list[str],
                                  sale: str, entra: str, motivo: str) -> dict:
    """Lo que sigue a un cambio de unidad ya guardado (seccion 105): el
    aviso al telefono de quien va en esos dias y la hoja vuelta a
    publicar si ya habia una. Ninguna de las dos tumba el cambio.

    Devuelve lo que la pantalla dice: a cuantos se aviso, que version
    quedo publicada o, si la hoja no se pudo publicar, que hay que
    hacerlo a mano.
    """
    from app import tasksheet

    dias = (db.query(m.Jornada)
            .filter(m.Jornada.equipo_id == jornada.equipo_id,
                    m.Jornada.fecha.in_([date.fromisoformat(f)
                                         for f in fechas]))
            .all()) if fechas else []
    salida = {"avisado": None, "hoja_republicada": None,
              "hoja_por_publicar": False}
    try:
        salida["avisado"] = push.avisar_cambio_de_unidad(
            db, dias, jornada.equipo.servicio.folio, sale, entra)
    except Exception:                     # noqa: BLE001
        registro.exception("no se pudo avisar el cambio de unidad de la "
                           "jornada %s", jornada.id)

    if tasksheet.vigente(db, jornada.equipo_id) is None:
        return salida
    try:
        hoja = tasksheet.publicar(db, jornada.equipo_id, usuario.persona_id,
                                  motivo=motivo, forzar=True, avisar=False)
        auditoria.registrar(db, usuario, jornada.equipo.servicio,
                            "publicar task sheet",
                            f"{jornada.equipo.alias} version {hoja.version} "
                            "(cambio de unidad)")
        salida["hoja_republicada"] = hoja.version
    except Exception:                     # noqa: BLE001
        db.rollback()
        registro.exception("no se pudo volver a publicar la hoja del "
                           "equipo %s", jornada.equipo_id)
        salida["hoja_por_publicar"] = True
    return salida


@router.post("/reemplazos/vehiculo/vista-previa",
             summary="Que pasaria con este cambio de unidad, sin guardarlo")
def vista_previa_vehiculo(datos: s.ReemplazoVehiculoIn,
                          db: Session = Depends(get_db),
                          ahora: datetime | None = None,
                          _: m.Usuario = Depends(CONSULTOR)):
    """El panel de la unidad (seccion 105, decision 3) ensena lo mismo
    que el de la persona antes de confirmar: los dias que se mueven, el
    que se parte con su hora, la revision que queda pendiente y los que
    chocan. Ejecutado de verdad y deshecho, como el de personal."""
    return motor.vista_previa_vehiculo(
        db, desde_jornada_id=datos.desde_jornada_id,
        sale_vehiculo_id=datos.sale_vehiculo_id,
        entra_vehiculo_id=datos.entra_vehiculo_id, motivo=datos.motivo,
        motivo_tipo=datos.motivo_tipo, hasta_jornada_id=datos.hasta_jornada_id,
        relevado_en=datos.relevado_en, ahora=reloj.de_prueba(ahora))


@router.post("/reemplazos/{reemplazo_id}/regreso",
             summary="El titular vuelve: cierra el cambio")
def regreso(reemplazo_id: int, datos: s.RegresoIn,
            db: Session = Depends(get_db),
            ahora: datetime | None = None,
            usuario: m.Usuario = Depends(CONSULTOR)):
    """Marta se recupera y regresa el 25; Luis trabaja hasta el 24.

    No abre otro movimiento: recorre el `hasta` del que ya existe, para
    que el mes lea "Luis cubrio a Marta del 10 al 24" y no dos cambios
    cruzados que nadie sabe cual cierra a cual.
    """
    resultado = motor.regresar(db, reemplazo_id, datos.desde,
                               hecho_por_id=usuario.persona_id,
                               relevado_en=datos.relevado_en,
                               ahora=reloj.de_prueba(ahora))
    servicio = db.get(m.Servicio, resultado["servicio_id"])
    partidos = resultado["jornadas_partidas"]
    auditoria.registrar(
        db, usuario, servicio, "regreso del titular",
        f"regresa {resultado['regresa']}; {resultado['sale']} cubrio del "
        f"{resultado['desde']} al {resultado['hasta']}"
        + (f"; dia partido: {', '.join(partidos)}" if partidos else ""))
    db.commit()

    # A los dos, al telefono, en el momento (seccion 101). Igual que en
    # el cambio: el recordatorio de la vispera solo mira manana, y sin
    # esto el que cubria podia presentarse el dia del regreso a un
    # servicio que ya no era suyo, y el titular solo se enteraba si
    # abria la app. Es de personal: una unidad no tiene telefono.
    reemplazo = db.get(m.ReemplazoRecurso, reemplazo_id)
    if reemplazo and reemplazo.tipo == m.TipoRecurso.PERSONAL:
        titular = db.get(m.Persona, reemplazo.sale_persona_id)
        cubre = db.get(m.Persona, reemplazo.entra_persona_id)
        resultado["avisado"] = (push.avisar_regreso(db, titular, cubre,
                                                    resultado)
                                if titular and cubre else None)
        # `avisar` apaga los telefonos que ya no existen: se guarda.
        db.commit()
    elif reemplazo:
        # La unidad que vuelve (seccion 105, decision 3): igual que el
        # cambio, sin correo al cliente; el equipo se entera al telefono
        # y la hoja publicada se vuelve a publicar con la placa de
        # siempre.
        arranco = db.get(m.Jornada, reemplazo.desde_jornada_id)
        resultado["cliente_avisado"] = False
        resultado.update(_despues_del_cambio_de_unidad(
            db, usuario, arranco, resultado.get("jornadas_devueltas") or [],
            resultado.get("sale") or "?", resultado.get("regresa") or "?",
            f"Regreso de la unidad {resultado.get('regresa') or '?'}"))
        db.commit()
    return resultado


@router.post("/reemplazos/{reemplazo_id}/regreso/vista-previa",
             summary="Que pasaria con este regreso, sin guardarlo")
def regreso_previa(reemplazo_id: int, datos: s.RegresoIn,
                   db: Session = Depends(get_db),
                   ahora: datetime | None = None,
                   _: m.Usuario = Depends(CONSULTOR)):
    """Hasta que dia se queda el que cubria, si ese dia se parte y a que
    hora, y que pasa con el dinero de los dos.

    Se ejecuta el regreso de verdad y se deshace, por la misma razon que
    el cambio: una segunda cuenta que calcule "lo que pasaria" acaba
    separandose de la primera.
    """
    try:
        return motor.regresar(db, reemplazo_id, datos.desde,
                              hecho_por_id=None,
                              relevado_en=datos.relevado_en,
                              ahora=reloj.de_prueba(ahora))
    finally:
        db.rollback()


@router.post("/reemplazos/personal/vista-previa",
             summary="Que pasaria con este cambio, sin guardarlo")
def vista_previa(datos: s.ReemplazoPersonalIn, db: Session = Depends(get_db),
                 ahora: datetime | None = None,
                 _: m.Usuario = Depends(CONSULTOR)):
    """Los dias que se mueven, los que chocan y —sobre todo— los viaticos.

    Lo delicado de un reemplazo no es el nombre de quien va: es que la
    persona que sale se queda con dinero que tiene que comprobar y la
    que entra necesita dinero nuevo. Eso ya pasaba; lo que faltaba era
    decirlo antes.
    """
    return motor.vista_previa(
        db, desde_jornada_id=datos.desde_jornada_id,
        sale_persona_id=datos.sale_persona_id,
        entra_persona_id=datos.entra_persona_id, motivo=datos.motivo,
        motivo_tipo=datos.motivo_tipo, hasta_jornada_id=datos.hasta_jornada_id,
        relevado_en=datos.relevado_en, ahora=reloj.de_prueba(ahora))


@router.post("/reemplazos/{reemplazo_id}/deshacer",
             summary="Deshacer un cambio recien hecho")
def deshacer(reemplazo_id: int, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(CONSULTOR)):
    """Para el que se equivoco de persona hace un minuto.

    Solo mientras nadie haya tocado el dinero. Despues de eso, deshacer
    a mano seria peor que el error: lo que corresponde es un cambio en
    sentido contrario, con su rastro.
    """
    reemplazo = db.get(m.ReemplazoRecurso, reemplazo_id)
    if not reemplazo:
        raise HTTPException(404, f"No existe el reemplazo {reemplazo_id}")
    servicio = db.get(m.Servicio, reemplazo.servicio_id)
    resultado = motor.deshacer(db, reemplazo_id)
    auditoria.registrar(db, usuario, servicio, "reemplazo deshecho",
                        f"se deshizo el cambio {reemplazo_id}")
    db.commit()
    return resultado


def _partidos(db: Session, r: m.ReemplazoRecurso, desde: m.Jornada,
              hasta: m.Jornada | None) -> list[dict]:
    """Los dias que el movimiento partio en dos, con su hora y su dueno.

    La asignacion de quien fue relevado sigue ahi, marcada con la hora en
    que lo relevaron. Ese renglon es lo que explica por que el mismo dia
    aparece dos veces en la nomina, y el consultor tiene que poder verlo
    sin abrirla.

    Se busca en los dos sentidos porque un movimiento puede partir dos
    dias: el que lo abre --se fue el titular a media manana y entro el
    que cubre-- y el que lo cierra --el que cubria trabajo la manana en
    que el titular volvio--. En el primero el relevado es el titular; en
    el segundo, el que cubria. Buscando en un solo sentido, el dia
    partido del regreso no aparecia en ninguna pantalla.

    `quien` es el que cobra hasta esa hora: el relevado de ese dia.
    """
    if r.tipo != m.TipoRecurso.PERSONAL or not r.sale_persona_id:
        return []

    def buscar(relevado: int, releva: int) -> list:
        consulta = (db.query(m.Jornada.fecha, m.AsignacionPersonal.relevado_en)
                    .join(m.AsignacionPersonal,
                          m.AsignacionPersonal.jornada_id == m.Jornada.id)
                    .filter(m.Jornada.equipo_id == desde.equipo_id,
                            m.Jornada.fecha >= desde.fecha,
                            m.AsignacionPersonal.persona_id == relevado,
                            m.AsignacionPersonal.relevado_por_id == releva,
                            m.AsignacionPersonal.relevado_en.isnot(None)))
        if hasta is not None:
            consulta = consulta.filter(m.Jornada.fecha <= hasta.fecha)
        return consulta.all()

    titular, cubre = r.sale_persona_id, r.entra_persona_id
    filas = ([(f, h, titular) for f, h in buscar(titular, cubre)]
             + [(f, h, cubre) for f, h in buscar(cubre, titular)])
    return [{"fecha": f.isoformat(), "hora": h.strftime("%H:%M"),
             "quien": _nombre(db, quien)}
            for f, h, quien in sorted(filas, key=lambda x: x[0])]


def _nombre(db: Session, persona_id: int | None) -> str | None:
    persona = db.get(m.Persona, persona_id) if persona_id else None
    return persona.nombre if persona else None


@router.get("/reemplazos/servicio/{servicio_id}",
            summary="Historial de cambios de recurso del servicio")
def historial(servicio_id: int, db: Session = Depends(get_db),
              _=Depends(LECTURA)):
    filas = (db.query(m.ReemplazoRecurso)
             .filter_by(servicio_id=servicio_id)
             .order_by(m.ReemplazoRecurso.creado_en).all())
    # El "hoy" que decide si un cambio sigue corriendo es el del pais del
    # servicio. El del navegador no sirve: un consultor en Mexico mirando
    # un servicio de Sao Paulo veria terminado lo que alli sigue vivo.
    servicio = db.get(m.Servicio, servicio_id)
    hoy = reloj.Relojes(db).hoy(servicio.pais_id if servicio else None)
    implantado = bool(servicio and servicio.tipo == m.TipoServicio.IMPLANTADO)
    salida = []
    for r in filas:
        sale = entra = None
        if r.tipo == m.TipoRecurso.PERSONAL:
            sale = db.get(m.Persona, r.sale_persona_id)
            entra = db.get(m.Persona, r.entra_persona_id)
            sale, entra = (sale.nombre if sale else None,
                           entra.nombre if entra else None)
        else:
            v_sale = db.get(m.Vehiculo, r.sale_vehiculo_id)
            v_entra = db.get(m.Vehiculo, r.entra_vehiculo_id)
            sale, entra = (v_sale.placa if v_sale else None,
                           v_entra.placa if v_entra else None)
        quien = db.get(m.Persona, r.hecho_por_id) if r.hecho_por_id else None
        desde = db.get(m.Jornada, r.desde_jornada_id)
        hasta = db.get(m.Jornada, r.hasta_jornada_id) if r.hasta_jornada_id else None
        salida.append({
            "id": r.id, "tipo": r.tipo.value, "sale": sale, "entra": entra,
            "motivo": r.motivo,
            "motivo_tipo": r.motivo_tipo.value if r.motivo_tipo else None,
            "jornadas_afectadas": r.jornadas_afectadas,
            "desde": desde.fecha.isoformat() if desde else None,
            # Vacio quiere decir "de ahi en adelante", que es como se
            # resuelve una contingencia.
            "hasta": hasta.fecha.isoformat() if hasta else None,
            "formalizo": quien.nombre if quien else None,
            "alerta_id": r.alerta_id,
            "creado_en": r.creado_en.isoformat() if r.creado_en else None,
            # Si tiene fecha de regreso, el titular ya volvio y el `hasta`
            # de arriba es el ultimo dia que cubrio el que entro. Sin
            # ella, el cambio sigue corriendo.
            "regreso_en": r.regreso_en.isoformat() if r.regreso_en else None,
            "regreso_por": _nombre(db, r.regreso_por_id),
            # Lo que el sistema habria puesto solo, de los dos lados del
            # movimiento. Si no coincide con la hora que quedo en la
            # asignacion, alguien la corrigio.
            "hora_propuesta": (r.hora_propuesta.isoformat()
                               if r.hora_propuesta else None),
            "hora_propuesta_regreso": (r.hora_propuesta_regreso.isoformat()
                                       if r.hora_propuesta_regreso else None),
            # Sigue corriendo: nadie lo cerro y todavia no llega a su
            # ultimo dia. Es lo que decide si se ofrece el regreso.
            "en_curso": (r.regreso_en is None
                         and (hasta is None or hasta.fecha >= hoy)),
            # Los dias que se partieron, con la hora del relevo. Se
            # llama distinto que el `jornadas_partidas` de las puertas de
            # cambio porque lleva la hora: dos formas con el mismo nombre
            # es como se rompe una pantalla sin que nadie lo note.
            "partidos": _partidos(db, r, desde, hasta) if desde else [],
            # El implantado siempre termina en una fecha, aunque el
            # consultor no la haya escrito. Despues de esa fecha hay que
            # volver a pedirlo.
            "se_vuelve_a_pedir": implantado and hasta is not None,
            # La hoja que el cliente tiene se publico antes de este
            # cambio: trae el nombre de quien ya no va (seccion 101).
            "hoja_por_publicar": motor.hoja_anterior_al_cambio(db, r),
        })
    return salida

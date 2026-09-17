"""Alertas durante el servicio y cambio de recurso por contingencia.

La central atiende la alerta y estabiliza el servicio; el consultor
formaliza el cambio de recurso. Son dos permisos distintos a proposito.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auditoria, auth, contingencia as motor
from app import models as m
from app import push
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/contingencia", tags=["Contingencia"])

CAMPO = auth.requiere(m.Rol.PERSONAL_SEGURIDAD)
CENTRAL = auth.requiere(m.Rol.CENTRAL, m.Rol.DIRECTOR_OPERACIONES)
CONSULTOR = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES)
LECTURA = auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL, m.Rol.FINANZAS,
                        m.Rol.DIRECTOR_OPERACIONES)


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

    if not datos.jornada_id and not datos.servicio_id:
        raise HTTPException(400, "Hay que decir a que jornada o servicio pertenece")

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
def listar(abiertas: bool = True, db: Session = Depends(get_db),
           _=Depends(LECTURA)):
    consulta = db.query(m.AlertaIncidencia)
    if abiertas:
        consulta = consulta.filter(
            m.AlertaIncidencia.estatus != m.EstatusAlerta.CERRADA)
    filas = consulta.order_by(m.AlertaIncidencia.reportada_en.desc()).all()

    # Que paso despues de la alerta. Una alerta atendida que dejo un
    # cambio de recurso y una que no se leen distinto: la central ve si
    # el consultor ya hizo lo suyo.
    cambios = {}
    for r in (db.query(m.ReemplazoRecurso)
              .filter(m.ReemplazoRecurso.alerta_id.isnot(None)).all()):
        if r.tipo == m.TipoRecurso.PERSONAL:
            sale = db.get(m.Persona, r.sale_persona_id)
            entra = db.get(m.Persona, r.entra_persona_id)
            nombres = (sale.nombre if sale else "?",
                       entra.nombre if entra else "?")
        else:
            sale = db.get(m.Vehiculo, r.sale_vehiculo_id)
            entra = db.get(m.Vehiculo, r.entra_vehiculo_id)
            nombres = (sale.placa if sale else "?",
                       entra.placa if entra else "?")
        cambios[r.alerta_id] = f"{nombres[1]} entra por {nombres[0]}"

    for fila in filas:
        fila.cambio = cambios.get(fila.id)
    return filas


@router.post("/alertas/{alerta_id}/tomar", response_model=s.AlertaOut,
             summary="La central toma la alerta")
def tomar(alerta_id: int, datos: s.TomarAlertaIn, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(CENTRAL)):
    alerta = db.get(m.AlertaIncidencia, alerta_id)
    if not alerta:
        raise HTTPException(404, f"No existe la alerta {alerta_id}")
    if alerta.estatus == m.EstatusAlerta.CERRADA:
        raise HTTPException(409, "Esa alerta ya esta cerrada")

    alerta.estatus = m.EstatusAlerta.EN_ATENCION
    alerta.tomada_por_id = usuario.persona_id
    alerta.tomada_en = datetime.now()
    alerta.equipo_respuesta_enviado = datos.equipo_respuesta_enviado
    if datos.nota:
        alerta.descripcion = " · ".join(filter(None, [alerta.descripcion,
                                                     datos.nota]))

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
    alerta = db.get(m.AlertaIncidencia, alerta_id)
    if not alerta:
        raise HTTPException(404, f"No existe la alerta {alerta_id}")
    if alerta.estatus == m.EstatusAlerta.ABIERTA:
        raise HTTPException(409, "Primero hay que tomarla, luego cerrarla")

    alerta.estatus = m.EstatusAlerta.CERRADA
    alerta.resolucion = datos.resolucion
    alerta.cerrada_por_id = usuario.persona_id
    alerta.cerrada_en = datetime.now()

    servicio = _servicio_de(db, alerta)
    if servicio:
        auditoria.registrar(db, usuario, servicio, "alerta cerrada",
                            datos.resolucion[:120],
                            jornada_id=alerta.jornada_id)
    db.commit()
    db.refresh(alerta)
    return alerta


# ------------------------------------------------------- cambio de recurso

@router.post("/reemplazos/personal",
             summary="Cambiar a una persona del equipo por contingencia")
def reemplazo_personal(datos: s.ReemplazoPersonalIn,
                       db: Session = Depends(get_db),
                       usuario: m.Usuario = Depends(CONSULTOR)):
    """Cambia a la persona de esa jornada en adelante y mueve los viaticos:
    quien sale entra a comprobacion con su plazo, quien entra recibe nuevos."""
    resultado = motor.reemplazar_personal(
        db, datos.desde_jornada_id, datos.sale_persona_id,
        datos.entra_persona_id, datos.motivo,
        hecho_por_id=usuario.persona_id, alerta_id=datos.alerta_id,
        motivo_tipo=datos.motivo_tipo, hasta_jornada_id=datos.hasta_jornada_id,
        relevado_en=datos.relevado_en)

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
    return resultado


@router.post("/reemplazos/vehiculo",
             summary="Cambiar la unidad por contingencia")
def reemplazo_vehiculo(datos: s.ReemplazoVehiculoIn,
                       db: Session = Depends(get_db),
                       usuario: m.Usuario = Depends(CONSULTOR)):
    resultado = motor.reemplazar_vehiculo(
        db, datos.desde_jornada_id, datos.sale_vehiculo_id,
        datos.entra_vehiculo_id, datos.motivo,
        hecho_por_id=usuario.persona_id, alerta_id=datos.alerta_id,
        motivo_tipo=datos.motivo_tipo, hasta_jornada_id=datos.hasta_jornada_id,
        relevado_en=datos.relevado_en)

    jornada = db.get(m.Jornada, datos.desde_jornada_id)
    sale = db.get(m.Vehiculo, datos.sale_vehiculo_id)
    entra = db.get(m.Vehiculo, datos.entra_vehiculo_id)
    auditoria.registrar(
        db, usuario, jornada.equipo.servicio, "reemplazo de unidad",
        f"entra {entra.placa} en lugar de {sale.placa}: {datos.motivo}",
        jornada_id=jornada.id)
    db.commit()
    return resultado


@router.post("/reemplazos/personal/vista-previa",
             summary="Que pasaria con este cambio, sin guardarlo")
def vista_previa(datos: s.ReemplazoPersonalIn, db: Session = Depends(get_db),
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
        relevado_en=datos.relevado_en)


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


@router.get("/reemplazos/servicio/{servicio_id}",
            summary="Historial de cambios de recurso del servicio")
def historial(servicio_id: int, db: Session = Depends(get_db),
              _=Depends(LECTURA)):
    filas = (db.query(m.ReemplazoRecurso)
             .filter_by(servicio_id=servicio_id)
             .order_by(m.ReemplazoRecurso.creado_en).all())
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
        })
    return salida

"""La hoja del implantado: el acuerdo y quien lo cubre.

Es otro documento que el del eventual, aunque se parezca. El eventual se
lee por dias —a que hora, donde, que sigue—; el implantado se lee una
vez y se archiva: el cliente ya sabe que el servicio es de lunes a
viernes a las ocho, lo que quiere saber es hasta donde llega, a quien le
habla y quien es la persona que va a tener enfrente todos los dias.

Por eso esta hoja no lleva agenda ni hotel ni señal, y en cambio lleva
el perfil de quien cubre: foto, experiencia, certificaciones y
calificacion. Eso es lo que contesta la unica pregunta que de verdad
hace el cliente de un implantado.

Van dos: la del servicio —la gente de planta, la que se archiva— y la
de cobertura, para el dia que cubre alguien mas. Misma hoja, mismo
diseño; cambia a quien presenta y por que.
"""
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import implantado as motor
from app import models as m
from app import profesionalismo
from app import tasksheet


def _persona(db: Session, persona: m.Persona, vehiculo=None,
             puesto: str | None = None) -> dict:
    """La ficha de quien cubre el servicio.

    Lo que no hay no se inventa ni deja hueco: el bloque de
    certificaciones solo sale si alguien las cargo. Una hoja con
    "capacitacion: —" dice menos que una hoja sin ese renglon.
    """
    tablero = profesionalismo.ficha(db, persona.id)
    cursos = [c for c in (db.query(m.Capacitacion)
                          .filter_by(persona_id=persona.id, activo=True)
                          .order_by(m.Capacitacion.nombre).all())]

    return {
        "persona_id": persona.id,
        "nombre": persona.nombre,
        "puesto": puesto,
        "telefono": persona.telefono,
        "foto_url": persona.foto_url,
        "horas": tablero.get("horas_en_centauro"),
        "calificacion": tablero.get("calificacion"),
        "confianza": tablero.get("confianza"),
        "capacitacion": [{
            "nombre": c.nombre,
            "institucion": c.institucion,
            "obtenida_en": c.obtenida_en.isoformat() if c.obtenida_en else None,
            "vigencia_hasta": (c.vigencia_hasta.isoformat()
                               if c.vigencia_hasta else None),
            "vigente": c.vigente,
        } for c in cursos],
        "unidad": _unidad(vehiculo) if vehiculo else None,
    }


def _unidad(vehiculo: m.Vehiculo) -> dict:
    return {
        "placa": vehiculo.placa,
        "marca_modelo": vehiculo.marca_modelo,
        "categoria": vehiculo.categoria.nombre if vehiculo.categoria else None,
        "blindada": vehiculo.categoria.blindado if vehiculo.categoria else None,
        "color": vehiculo.color,
        "anio": vehiculo.modelo_anio,
        "foto_url": vehiculo.foto_url,
    }


def _contrato_vigente(db: Session, servicio: m.Servicio,
                      cuando: date | None = None):
    """El contrato del mes que se pide, o el ultimo que exista.

    La hoja del servicio no es de un mes —el acuerdo no cambia— pero la
    plantilla si vive en el contrato, y hay que sacarla de alguno.
    """
    consulta = db.query(m.ContratoImplantado).filter_by(servicio_id=servicio.id)
    if cuando:
        del_mes = consulta.filter_by(anio=cuando.year, mes=cuando.month).first()
        if del_mes:
            return del_mes
    return (consulta.order_by(m.ContratoImplantado.anio.desc(),
                              m.ContratoImplantado.mes.desc()).first())


def _acuerdo(db: Session, servicio: m.Servicio) -> m.AcuerdoImplantado:
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    if not acuerdo:
        raise HTTPException(409, {
            "mensaje": "El servicio no tiene acuerdo capturado",
            "que_hacer": "Sin el acuerdo la hoja saldria vacia: es todo lo "
                         "que el cliente lee de un implantado."})
    return acuerdo


def _base(db: Session, servicio: m.Servicio, acuerdo, contrato) -> dict:
    """Lo que las dos hojas comparten: el acuerdo y donde se opera."""
    hospitales = tasksheet.hospitales_cercanos(
        db, servicio.plaza_id,
        float(acuerdo.origen_lat) if acuerdo.origen_lat is not None else None,
        float(acuerdo.origen_lon) if acuerdo.origen_lon is not None else None)

    return {
        "servicio": servicio.folio,
        "cliente": servicio.cliente.nombre if servicio.cliente else None,
        "ciudad": servicio.plaza.nombre if getattr(servicio, "plaza", None)
                  else (db.get(m.Plaza, servicio.plaza_id).nombre
                        if servicio.plaza_id else None),
        "ejecutivo": servicio.ejecutivo_completo,
        "ejecutivo_telefono": servicio.ejecutivo_telefono,
        "punto": {
            "direccion": acuerdo.origen_direccion,
            "lat": float(acuerdo.origen_lat) if acuerdo.origen_lat is not None else None,
            "lon": float(acuerdo.origen_lon) if acuerdo.origen_lon is not None else None,
            "metros": acuerdo.geocerca_metros,
        },
        "dias_semana": acuerdo.dias_semana,
        "hora": contrato.hora_presentacion if contrato else None,
        "zona": acuerdo.zona_operacion,
        "cubre": acuerdo.cubre,
        "no_cubre": acuerdo.no_cubre,
        "coordinacion": {
            "nombre": " ".join(filter(None, [acuerdo.reporta_a_nombre,
                                             acuerdo.reporta_a_apellidos])) or None,
            "telefono": acuerdo.reporta_a_telefono,
            "correo": acuerdo.reporta_a_correo,
        },
        "protocolo": acuerdo.protocolo_contacto,
        "hospitales": hospitales,
        "escalacion": tasksheet._escalacion(db, servicio),
    }


def armar(db: Session, servicio_id: int) -> dict:
    """La hoja del servicio: el acuerdo y la gente de planta.

    Solo la gente permanente. Un relevo de un sabado no entra aqui: este
    es el documento que el cliente archiva, y ensuciarlo con quien fue
    una vez lo vuelve inservible.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio or servicio.tipo != m.TipoServicio.IMPLANTADO:
        raise HTTPException(404, f"No existe el implantado {servicio_id}")

    acuerdo = _acuerdo(db, servicio)
    contrato = _contrato_vigente(db, servicio)

    equipo = []
    if contrato:
        for fila in contrato.plantilla:
            if not fila.persona:
                continue
            equipo.append(_persona(db, fila.persona, fila.vehiculo,
                                   fila.rol.nombre if fila.rol else None))

    return {**_base(db, servicio, acuerdo, contrato),
            "tipo": "servicio",
            "equipo": equipo,
            "periodo": (f"{contrato.mes:02d}/{contrato.anio}" if contrato
                        else None)}


def armar_cobertura(db: Session, servicio_id: int, fecha: date) -> dict:
    """La hoja de un dia que cubre alguien mas.

    Misma hoja, con dos diferencias: dice que es una cobertura y con que
    fechas, y en lugar del equipo de planta presenta a quien va. El
    resto se mantiene —punto fijo, horario, zona, coordinacion y
    protocolo— porque el cliente necesita el documento entero, no un
    anexo suelto.

    Un fin de semana sale en una sola hoja: es el mismo relevo y el
    cliente recibe un correo, no dos.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio or servicio.tipo != m.TipoServicio.IMPLANTADO:
        raise HTTPException(404, f"No existe el implantado {servicio_id}")

    acuerdo = _acuerdo(db, servicio)
    contrato = _contrato_vigente(db, servicio, fecha)
    if not contrato:
        raise HTTPException(409, f"El mes {fecha.month:02d}/{fecha.year} "
                                 f"no esta abierto")

    equipo_servicio = servicio.equipos[0] if servicio.equipos else None
    if not equipo_servicio:
        raise HTTPException(409, "El servicio no tiene jornadas")

    # El dia y, si el fin de semana se cubrio completo, su pareja.
    fechas = [fecha]
    vecino = motor._vecino_del_fin(db, equipo_servicio.id, fecha,
                                   contrato.dias_servicio)
    if vecino:
        fechas.append(vecino)

    cubren, dias = {}, []
    for dia in sorted(set(fechas)):
        jornada = (db.query(m.Jornada)
                   .filter_by(equipo_id=equipo_servicio.id, fecha=dia).first())
        if not jornada or not jornada.personal:
            continue
        dias.append(dia.isoformat())
        for asignacion in jornada.personal:
            if asignacion.persona:
                cubren[asignacion.persona_id] = (
                    asignacion.persona, asignacion.vehiculo,
                    asignacion.rol.nombre if asignacion.rol else None)

    if not dias:
        raise HTTPException(409, {
            "mensaje": f"El {fecha.isoformat()} no tiene a nadie asignado",
            "que_hacer": "Primero se cubre el dia desde el calendario."})

    de_planta = {f.persona_id for f in contrato.plantilla}
    equipo = [_persona(db, persona, vehiculo, puesto)
              for persona, vehiculo, puesto in cubren.values()]
    relevo = any(pid not in de_planta for pid in cubren)

    return {**_base(db, servicio, acuerdo, contrato),
            "tipo": "cobertura",
            "equipo": equipo,
            "fechas": dias,
            "es_relevo": relevo,
            "periodo": f"{contrato.mes:02d}/{contrato.anio}"}

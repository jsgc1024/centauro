"""Quien responde por una unidad, y que le falta antes de soltarla.

Esto vive aparte porque lo usan dos lados que no se hablan: el endpoint
que guarda la revision --en `routers/campo.py`-- y el candado del fin de
servicio --en `operacion.py`--. Si cada uno trajera su propia version de
"cual unidad es la tuya", el dia que una cambiara, la otra se quedaria
diciendo lo contrario y nadie sabria cual manda.

Es la misma leccion del umbral de silencio, que vivio meses con 60 en una
pantalla y 120 en la otra.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m

# Jornadas que ya no van a pasar: no cuentan para decidir si una unidad
# sigue en el servicio manana.
MUERTAS = (m.EstatusJornada.CANCELADA,)


def unidades_del_dia(jornada: m.Jornada) -> list[int]:
    """Las unidades de esa jornada, incluida la que salio a media jornada.

    La relevada se queda en su dia a proposito --para poder hacerle su
    revision de devolucion-- y es justo la que mas facil se escapa sin
    revisar, porque manana ya no aparece en ningun lado.
    """
    return [a.vehiculo_id for a in jornada.vehiculos if a.vehiculo_id]


def _con_las_que_relevo(jornada: m.Jornada, unidades: list[int]) -> list[int]:
    """Suma las que salieron para que entraran estas.

    Una camioneta que se fue al taller y la que llego en su lugar no son
    "dos unidades": son la misma silla, antes y despues. Quien responde
    por la que quedo responde tambien por la que salio --la manejo esa
    manana-- y es la que hay que entregar, porque manana ya no va.

    Va encadenado: si en un mal dia se cambio dos veces, la primera
    tambien es suya.
    """
    salida = list(unidades)
    por_revisar = list(unidades)
    while por_revisar:
        actual = por_revisar.pop()
        for a in jornada.vehiculos:
            if (a.relevado_por_vehiculo_id == actual
                    and a.vehiculo_id not in salida):
                salida.append(a.vehiculo_id)
                por_revisar.append(a.vehiculo_id)
    return salida


def mis_unidades(jornada: m.Jornada, persona_id: int) -> list[int]:
    """De las de ese dia, cuales responde esa persona.

    La regla sale del propio modelo: `AsignacionPersonal.vehiculo_id` dice
    en que unidad va cada quien, y su comentario ya lo explicaba --"con
    una sola unidad sobra decirlo; cuando el equipo lleva dos o mas, es lo
    que ordena las salidas"--.

    Con una sola unidad en el dia, es de quien vaya en el equipo. Con dos
    o mas, solo la que trae asignada: si no tiene ninguna, no responde por
    ninguna, y eso es correcto --el escolta que va de copiloto no es quien
    firma que la camioneta volvio sin un golpe--.

    Para contar cuantas hay, **la relevada no cuenta**. Si contara, el dia
    que una camioneta se va al taller el equipo pasaria a tener "dos
    unidades" y, como nadie tiene unidad asignada cuando solo habia una,
    el dia entero se quedaria sin dueno. Justo el dia del cambio, que es
    el unico que de verdad importa.
    """
    if not jornada.vehiculos:
        return []

    vigentes = [a.vehiculo_id for a in jornada.vehiculos
                if a.vehiculo_id and a.relevado_en is None]

    suya = next((a.vehiculo_id for a in jornada.personal
                 if a.persona_id == persona_id), None)
    if suya is not None:
        if suya not in unidades_del_dia(jornada):
            return []
        return _con_las_que_relevo(jornada, [suya])

    if len(vigentes) != 1:
        return []
    return _con_las_que_relevo(jornada, vigentes)


def es_suya(db: Session, servicio_id: int, vehiculo_id: int,
            persona_id: int) -> m.Servicio:
    """Que esa persona traiga de verdad esa unidad en ese servicio.

    Antes solo se comprobaba que estuviera asignada al servicio: la
    unidad llegaba como dato y nadie la miraba. En un equipo de cuatro con
    dos camionetas, el conductor de la primera podia firmar la recepcion
    de la segunda, y **la firma es justo lo que hace que la revision sirva
    para discutir un golpe tres semanas despues**. Una revision firmada
    por quien no traia la unidad es papel.

    Se mira dia por dia y no el servicio entero: en un implantado de un
    mes, la camioneta de hoy no es la de la semana pasada.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    mios = (db.query(m.AsignacionPersonal)
            .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == servicio_id,
                    m.AsignacionPersonal.persona_id == persona_id)
            .all())
    if not mios:
        raise HTTPException(403, "No estas asignado a ese servicio")

    ajena = None
    for suyo in mios:
        if vehiculo_id not in unidades_del_dia(suyo.jornada):
            continue
        if vehiculo_id in mis_unidades(suyo.jornada, persona_id):
            return servicio
        ajena = suyo

    if ajena is None:
        raise HTTPException(403, {
            "mensaje": "Esa unidad no va en tus dias de este servicio",
            "que_hacer": "Revisa que sea la placa correcta. Si de verdad la "
                         "traes tu, habla con tu consultor: en el sistema "
                         "esta asignada a otro dia o a otro equipo."})

    trae = db.get(m.Vehiculo, ajena.vehiculo_id) if ajena.vehiculo_id else None
    raise HTTPException(403, {
        "mensaje": "Esa unidad no es la tuya",
        "que_hacer": ("La revision la firma quien trae la unidad: si la "
                      "firma alguien mas, no sirve para discutir un golpe "
                      "despues. "
                      + (f"A ti te toca la {trae.placa}." if trae else
                         "Habla con tu consultor para que diga cual traes.")),
        "la_tuya": trae.placa if trae else None})


def _sigue_manana(db: Session, jornada: m.Jornada, vehiculo_id: int) -> bool:
    """Si esa unidad vuelve a aparecer en el servicio despues de este dia.

    La que se relevo a media jornada no vuelve, aunque siga colgada de
    hoy: para ella este **es** el ultimo dia, y es la que se escapaba sin
    revision de entrega porque manana ya no sale en la app de nadie.
    """
    return (db.query(m.AsignacionVehiculo.id)
            .join(m.Jornada, m.AsignacionVehiculo.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == jornada.equipo.servicio_id,
                    m.AsignacionVehiculo.vehiculo_id == vehiculo_id,
                    m.Jornada.fecha > jornada.fecha,
                    m.Jornada.estatus.notin_(MUERTAS))
            .first()) is not None


def _hecha(db: Session, servicio_id: int, vehiculo_id: int,
           tipo: m.TipoRevision) -> bool:
    return (db.query(m.RevisionUnidad.id)
            .filter_by(servicio_id=servicio_id, vehiculo_id=vehiculo_id,
                       tipo=tipo)
            .first()) is not None


def falta_entregar(db: Session, jornada: m.Jornada,
                   persona_id: int) -> list[dict]:
    """Las unidades de esa persona que hoy dejan el servicio sin revisar.

    Solo las que no vuelven manana. Un implantado con la misma camioneta
    veintidos dias se revisa dos veces, no cuarenta y cuatro: pedirsela
    cada tarde seria la forma mas rapida de que dejara de significar algo.
    """
    servicio_id = jornada.equipo.servicio_id
    pendientes = []
    for vehiculo_id in mis_unidades(jornada, persona_id):
        if _sigue_manana(db, jornada, vehiculo_id):
            continue
        if _hecha(db, servicio_id, vehiculo_id, m.TipoRevision.ENTREGA):
            continue
        unidad = db.get(m.Vehiculo, vehiculo_id)
        pendientes.append({
            "vehiculo_id": vehiculo_id,
            "placa": unidad.placa if unidad else None,
            # Sin la recepcion no se puede guardar la entrega --no hay
            # contra que comparar-- asi que este de aqui no lo resuelve
            # el agente solo, y el mensaje tiene que decirlo.
            "sin_recepcion": not _hecha(db, servicio_id, vehiculo_id,
                                        m.TipoRevision.RECIBE),
        })
    return pendientes

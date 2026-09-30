"""La central de inteligencia."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auditoria
from app import auth
from app import central as motor
from app import models as m
from app import operacion
from app import push
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/central", tags=["Central de inteligencia"])

MONITOREO = auth.puede("operacion.ver")
# La hora de un dia que ya tiene gente confirmada la mueve quien corrige
# (seccion 105, decision 5): es la misma puerta que `hora-de-manana` de
# la central, y por la misma razon.
CORREGIR = auth.puede("operacion.corregir")


@router.get("/tablero", summary="Lo que va a pasar, antes de que pase")
def tablero(db: Session = Depends(get_db), ahora: datetime | None = None,
            _=Depends(MONITOREO)):
    """Una sola consulta para toda la pantalla.

    Va en una y no en cuatro porque la pantalla se refresca sola cada
    minuto: cuatro consultas en paralelo cada minuto, con cinco personas
    mirando, son mil doscientas consultas por hora para el mismo dato.
    """
    return motor.tablero(db, ahora)


@router.get("/manana", summary="El meet and greet de manana, servicio por servicio")
def manana(db: Session = Depends(get_db), ahora: datetime | None = None,
           _=Depends(MONITOREO)):
    return motor.manana(db, ahora)


def _jornada_con_propuesta(db: Session, jornada_id: int) -> m.Jornada:
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    return jornada


@router.post("/manana/{jornada_id}/confirmar-hora",
             summary="Confirmar la hora que propuso el equipo para ese dia")
def confirmar_hora(jornada_id: int, db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(CORREGIR)):
    """El clic desde "Manana" (seccion 105, decision 5).

    Hace lo que hacia la captura del conductor antes: mueve la hora del
    dia, la geocerca se mide contra la hora nueva, queda en la bitacora
    y a quien ya habia confirmado le llega "cambio tu hora". La
    diferencia es que ahora lo decide la central, no el telefono.
    """
    jornada = _jornada_con_propuesta(db, jornada_id)
    hecho = operacion.resolver_hora_propuesta(
        db, jornada, usuario.persona_id, operacion.CONFIRMADA_CENTRAL)
    auditoria.registrar(db, usuario, jornada.equipo.servicio,
                        "hora de maniana",
                        f"{jornada.fecha} {hecho['hora']}: confirmada la "
                        "propuesta del equipo",
                        jornada_id=jornada.id)
    db.commit()

    avisados = None
    if hecho["movida"]:
        avisados = push.avisar_cambio_de_hora(db, jornada, hecho["antes"])
        db.commit()
    return {"resultado": "confirmada",
            "jornada_id": jornada.id,
            "fecha": jornada.fecha.isoformat(),
            "inicio": jornada.inicio_programado.isoformat(),
            "fin": jornada.fin_programado.isoformat(),
            "avisados": avisados}


@router.post("/manana/{jornada_id}/rechazar-hora",
             summary="Dejar la hora de la hoja: la propuesta no se toma")
def rechazar_hora(jornada_id: int, db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(CORREGIR)):
    """La central deja la hora que ya tenia el dia. Al que propuso se le
    dice al telefono que se queda la de la hoja, para que no planee su
    noche alrededor de una hora que no va a ser."""
    jornada = _jornada_con_propuesta(db, jornada_id)
    hecho = operacion.resolver_hora_propuesta(
        db, jornada, usuario.persona_id, operacion.RECHAZADA)
    auditoria.registrar(db, usuario, jornada.equipo.servicio,
                        "hora de maniana",
                        f"{jornada.fecha}: se queda la de la hoja "
                        f"({jornada.inicio_programado:%H:%M}); no se tomó "
                        f"la propuesta de las {hecho['hora']}",
                        jornada_id=jornada.id)
    db.commit()

    avisado = None
    if hecho["propuso_id"]:
        avisado = push.avisar_hora_rechazada(db, jornada, hecho["propuso_id"])
        db.commit()
    return {"resultado": "rechazada",
            "jornada_id": jornada.id,
            "fecha": jornada.fecha.isoformat(),
            "inicio": jornada.inicio_programado.isoformat(),
            "avisado": avisado}


@router.get("/camino", summary="Quien viene en camino a su meet and greet")
def camino(db: Session = Depends(get_db), ahora: datetime | None = None,
           _=Depends(MONITOREO)):
    """El rato en que todavia se puede hacer algo: reponer a alguien
    toma hasta hora y media."""
    return motor.camino(db, ahora)


@router.post("/camino/{jornada_id}/por-telefono",
             summary="Hablo con la central y dijo que ya va")
def camino_por_telefono(
        jornada_id: int, datos: s.PorTelefonoIn,
        db: Session = Depends(get_db),
        usuario: m.Usuario = Depends(
            auth.puede("asignaciones.confirmar_a_mano"))):
    """Lo que la central hace todo el dia, ahora asentado.

    El toque se le fue a un telefono guardado en el bolsillo de alguien
    que va manejando; la central marca su numero y el hombre contesta
    que va en camino. Eso vale, y queda con el nombre de quien lo
    registro: nunca se puede confundir con una posicion del GPS.

    No apaga la vigilancia. Da un plazo y vuelve a mirar: quien dijo
    que iba y no llego es el caso que esta pantalla existe para cazar.
    """
    from app import trayecto

    resultado = trayecto.dijo_que_va(db, jornada_id, datos.persona_id,
                                     usuario.persona_id, datos.nota)
    if not resultado.get("estado"):
        raise HTTPException(409, {
            "mensaje": resultado.get("motivo", "no se pudo registrar"),
            "que_hacer": "Revisa que esa persona siga asignada a ese dia."})
    return resultado


@router.get("/pulso", summary="Los servicios en curso y cuanto llevan callados")
def pulso(db: Session = Depends(get_db), ahora: datetime | None = None,
          _=Depends(MONITOREO)):
    return motor.pulso(db, ahora)


@router.get("/jornadas/{jornada_id}/revision",
            summary="Que le falta a un dia para poder salir")
def revision(jornada_id: int, db: Session = Depends(get_db),
             _=Depends(MONITOREO)):
    """La misma lista que ve la central, para un dia cualquiera.

    Sirve para revisar hoy lo que sale pasado manana, sin esperar a que
    caiga en la banda de la vispera.
    """
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    return {"jornada_id": jornada.id,
            "fecha": jornada.fecha.isoformat(),
            "revision": motor.revision_del_dia(db, jornada)}

"""La central de inteligencia."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth
from app import central as motor
from app import models as m
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/central", tags=["Central de inteligencia"])

MONITOREO = auth.puede("operacion.ver")


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

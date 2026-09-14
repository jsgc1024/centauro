"""La central de inteligencia."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth
from app import central as motor
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/central", tags=["Central de inteligencia"])

MONITOREO = auth.requiere(m.Rol.CENTRAL, m.Rol.CONSULTOR,
                          m.Rol.DIRECTOR_OPERACIONES, m.Rol.DIRECTOR_GENERAL)


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

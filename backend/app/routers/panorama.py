"""Concentrado de la operacion viva."""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth
from app import panorama as motor
from app.db import get_db

router = APIRouter(tags=["Panorama"])

LECTURA = auth.puede("panorama.ver")


@router.get("/panorama", summary="Todo lo que esta pasando ahora")
def ver(db: Session = Depends(get_db), ahora: datetime | None = None,
        _=Depends(LECTURA)):
    """La misma pantalla para todos, completa. Un consultor puede cubrir
    la cartera de otro, asi que esconderle que ese equipo lleva dos
    horas callado no protege nada: solo lo deja sin ver."""
    return motor.panorama(db, ahora)


@router.get("/panorama/marcas", summary="Las marcas que no cuadran")
def marcas(db: Session = Depends(get_db), ahora: datetime | None = None,
           _=Depends(LECTURA)):
    return motor.marcas_raras(db, ahora=ahora)

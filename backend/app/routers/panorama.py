"""Concentrado de la operacion viva."""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth
from app import models as m
from app import panorama as motor
from app.db import get_db

router = APIRouter(tags=["Panorama"])

LECTURA = auth.requiere(m.Rol.DIRECTOR_GENERAL, m.Rol.DIRECTOR_OPERACIONES,
                        m.Rol.CONSULTOR, m.Rol.CENTRAL, m.Rol.FINANZAS)


@router.get("/panorama", summary="Todo lo que esta pasando ahora")
def ver(db: Session = Depends(get_db), ahora: datetime | None = None,
        _=Depends(LECTURA)):
    return motor.panorama(db, ahora)

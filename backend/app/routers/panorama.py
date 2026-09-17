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
        usuario: m.Usuario = Depends(LECTURA)):
    """La misma pantalla para todos, recortada a lo que a cada quien le
    toca: el consultor ve su cartera, la direccion ve todo."""
    mio = (usuario.persona_id if usuario.rol == m.Rol.CONSULTOR else None)
    return motor.panorama(db, ahora, consultor_id=mio)


@router.get("/panorama/marcas", summary="Las marcas que no cuadran")
def marcas(db: Session = Depends(get_db), ahora: datetime | None = None,
           usuario: m.Usuario = Depends(LECTURA)):
    mio = (usuario.persona_id if usuario.rol == m.Rol.CONSULTOR else None)
    return motor.marcas_raras(db, consultor_id=mio, ahora=ahora)

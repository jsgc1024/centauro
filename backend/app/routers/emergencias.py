"""El panel de Respuesta a emergencias en la consola (seccion 145).

Quien trae `emergencias.ver` ve los panicos abiertos con la ubicacion en
vivo de quien pidio ayuda; quien trae `emergencias.atender` los toma, manda
al equipo de respuesta, anota el aviso a las autoridades y los cierra.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app import emergencias as motor
from app import models as m
from app.config import settings
from app.db import get_db

router = APIRouter(prefix="/emergencias", tags=["Respuesta a emergencias"])

VER = auth.puede("emergencias.ver")
ATENDER = auth.puede("emergencias.atender")


class NotaIn(BaseModel):
    nota: str = Field("", max_length=600)


class CerrarIn(BaseModel):
    resolucion: str = Field(max_length=600)


@router.get("", summary="Los panicos abiertos y como va el dia")
def panel(db: Session = Depends(get_db), _=Depends(VER)):
    return motor.panel(db)


@router.get("/mapa-llave", summary="La llave de Google del mapa")
def mapa_llave(_=Depends(VER)):
    """La misma del mapa de riesgo, para quien ve este panel: la llave va
    limitada en Google a las direcciones del sistema."""
    return {"llave": settings.google_maps_key_navegador or None}


@router.get("/{alerta_id}", summary="Una alerta con su recorrido y su bitacora")
def ficha(alerta_id: int, db: Session = Depends(get_db), _=Depends(VER)):
    return motor.ficha(db, motor.alerta_de(db, alerta_id))


def _hecho(db: Session, alerta: m.AlertaIncidencia) -> dict:
    db.commit()
    return motor.ficha(db, alerta)


@router.post("/{alerta_id}/tomar", summary="Tomarla")
def tomar(alerta_id: int, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(ATENDER)):
    alerta = _bloqueada(db, alerta_id)
    motor.tomar(db, usuario, alerta)
    return _hecho(db, alerta)


@router.post("/{alerta_id}/equipo", summary="Salio el equipo de respuesta")
def equipo(alerta_id: int, datos: NotaIn, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(ATENDER)):
    alerta = _bloqueada(db, alerta_id)
    motor.mandar_equipo(db, usuario, alerta, datos.nota)
    return _hecho(db, alerta)


@router.post("/{alerta_id}/autoridades", summary="Se aviso a las autoridades")
def autoridades(alerta_id: int, datos: NotaIn, db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(ATENDER)):
    alerta = _bloqueada(db, alerta_id)
    motor.avisar_autoridades(db, usuario, alerta, datos.nota)
    return _hecho(db, alerta)


@router.post("/{alerta_id}/nota", summary="Una nota en su bitacora")
def nota(alerta_id: int, datos: NotaIn, db: Session = Depends(get_db),
         usuario: m.Usuario = Depends(ATENDER)):
    alerta = _bloqueada(db, alerta_id)
    motor.poner_nota(db, usuario, alerta, datos.nota)
    return _hecho(db, alerta)


@router.post("/{alerta_id}/cerrar", summary="Cerrarla con su resolucion")
def cerrar(alerta_id: int, datos: CerrarIn, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(ATENDER)):
    alerta = _bloqueada(db, alerta_id)
    motor.cerrar(db, usuario, alerta, datos.resolucion)
    return _hecho(db, alerta)


def _bloqueada(db: Session, alerta_id: int) -> m.AlertaIncidencia:
    """De una en una: dos de la guardia que pican «Tomarla» a la vez no la
    toman los dos."""
    alerta = (db.query(m.AlertaIncidencia).filter_by(id=alerta_id)
              .with_for_update().first())
    if not alerta:
        motor.alerta_de(db, alerta_id)          # el 404 de siempre
    return alerta

"""El lector de noticias y redes en la consola (seccion 140).

Quien ve el mapa de riesgo ve lo que encontro el lector; quien publica
eventos lo convierte en evento, lo suma o lo descarta; quien lleva los
catalogos de riesgo cuida las fuentes y el tope de X.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app import lector as motor
from app import models as m
from app import riesgo
from app.db import get_db

router = APIRouter(prefix="/riesgo/lector", tags=["Central de Inteligencia"])

VER = auth.puede("riesgo.ver")
PUBLICAR = auth.puede("riesgo.publicar")
CATALOGO = auth.puede("riesgo.catalogo")


class CrearIn(BaseModel):
    tipo_id: int | None = None
    region_id: int | None = None
    nivel: int | None = Field(None, ge=1, le=4)
    titulo: str | None = Field(None, max_length=160)


class SumarIn(BaseModel):
    evento_id: int


class DescartarIn(BaseModel):
    motivo: str = Field(max_length=40)


class FuenteIn(BaseModel):
    tipo: str = Field(max_length=20)
    nombre: str | None = Field(None, max_length=120)
    direccion: str = Field(max_length=600)
    regiones: list[str] = Field(default_factory=list, max_length=32)
    oficial: bool = False
    cada_min: int | None = None


class FuenteCambio(BaseModel):
    activa: bool | None = None
    cada_min: int | None = None


class ParametrosIn(BaseModel):
    tope_x_dia: int | None = Field(None, ge=0, le=100000)
    pausado: bool | None = None


def _mexico(db: Session) -> m.Pais:
    pais = db.query(m.Pais).filter_by(codigo="MX").first()
    if not pais:
        raise HTTPException(404, "No está México en el catálogo")
    return pais


@router.get("", summary="Lo que encontró el lector, por revisar")
def ver(db: Session = Depends(get_db), usuario: m.Usuario = Depends(VER)):
    salida = motor.por_revisar(db, _mexico(db))
    salida["puede"] = {
        "publicar": auth.puede_el_usuario(db, usuario, "riesgo.publicar"),
        "fuentes": auth.puede_el_usuario(db, usuario, "riesgo.catalogo")}
    db.commit()                   # los parametros nacen la primera vez
    return salida


@router.get("/hallazgos/{hallazgo_id}", summary="Un hallazgo con sus notas")
def hallazgo(hallazgo_id: int, db: Session = Depends(get_db), _=Depends(VER)):
    return motor.vista_hallazgo(db, motor.hallazgo_de(db, hallazgo_id),
                                completa=True)


@router.post("/hallazgos/{hallazgo_id}/evento",
             summary="Crear el evento propuesto con sus notas como fuentes")
def crear_evento(hallazgo_id: int, datos: CrearIn,
                 db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(PUBLICAR)):
    h = motor.hallazgo_de(db, hallazgo_id, bloquear=True)
    evento = motor.crear_evento(db, usuario, h,
                                datos.model_dump(exclude_none=True))
    db.commit()
    return riesgo.vista(evento)


@router.post("/hallazgos/{hallazgo_id}/sumar",
             summary="Sumar sus notas a un evento que ya existe")
def sumar(hallazgo_id: int, datos: SumarIn, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(PUBLICAR)):
    evento = motor.sumar(db, usuario,
                         motor.hallazgo_de(db, hallazgo_id, bloquear=True),
                         datos.evento_id)
    db.commit()
    return riesgo.vista(evento)


@router.post("/hallazgos/{hallazgo_id}/descartar",
             summary="Descartarlo, con su motivo")
def descartar(hallazgo_id: int, datos: DescartarIn,
              db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(PUBLICAR)):
    motor.descartar(db, usuario,
                    motor.hallazgo_de(db, hallazgo_id, bloquear=True),
                    datos.motivo)
    db.commit()
    return {"resultado": "descartado"}


@router.get("/fuentes", summary="Lo que lee el lector")
def fuentes(db: Session = Depends(get_db), _=Depends(VER)):
    salida = motor.fuentes(db, _mexico(db))
    db.commit()
    return salida


@router.post("/fuentes", summary="Agregar una fuente")
def agregar_fuente(datos: FuenteIn, db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(CATALOGO)):
    pais = _mexico(db)
    motor.agregar_fuente(db, usuario, pais, datos.model_dump())
    db.commit()
    return motor.fuentes(db, pais)


@router.patch("/fuentes/{fuente_id}", summary="Apagar, encender o espaciar")
def cambiar_fuente(fuente_id: int, datos: FuenteCambio,
                   db: Session = Depends(get_db), _=Depends(CATALOGO)):
    f = db.get(m.FuenteLector, fuente_id)
    if not f:
        raise HTTPException(404, "No existe esa fuente")
    if datos.activa is not None:
        f.activa = datos.activa
    if datos.cada_min is not None:
        if datos.cada_min not in motor.CADA_MIN:
            raise HTTPException(400, "Cada 5, 10, 15, 30, 60 o 120 minutos")
        f.cada_min = datos.cada_min
    db.commit()
    return motor.fuentes(db, _mexico(db))


@router.put("/parametros", summary="El tope de X y la pausa del lector")
def cambiar_parametros(datos: ParametrosIn, db: Session = Depends(get_db),
                       _=Depends(CATALOGO)):
    par = motor.parametros(db)
    if datos.tope_x_dia is not None:
        par.tope_x_dia = datos.tope_x_dia
    if datos.pausado is not None:
        par.pausado = datos.pausado
    db.commit()
    return motor.fuentes(db, _mexico(db))

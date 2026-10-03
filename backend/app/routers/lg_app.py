"""LG Connect: la API de la app de los operadores de Logistica (seccion 151).

Vive bajo /lgapp-api y solo acepta la sesion de LG Connect: la de la
consola y la de la app de EP no abren nada aqui, y la de LG Connect no
abre nada alla. Las reglas viven en `app/lg_app.py` y `app/lg_jornada.py`.
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import lg_app as motor
from app import lg_jornada
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/lgapp-api", tags=["LG Connect: app de los operadores"])

YO = motor.operador_actual


class EntrarIn(BaseModel):
    correo: str = Field(..., max_length=160)
    contrasena: str = Field(..., max_length=200)


class CodigoIn(BaseModel):
    correo: str = Field(..., max_length=160)
    codigo: str = Field(..., max_length=10)
    nueva: str = Field(..., max_length=200)


class CambioIn(BaseModel):
    actual: str = Field(..., max_length=200)
    nueva: str = Field(..., max_length=200)


class MarcaIn(BaseModel):
    lat: float
    lon: float
    precision: float | None = None
    nota: str | None = Field(None, max_length=200)


class OpcionesEntradaIn(BaseModel):
    correo: str | None = Field(None, max_length=160)


class EntradaIn(BaseModel):
    credencial: dict
    estado: str = Field(..., max_length=2000)


class AltaOpcionesIn(BaseModel):
    contrasena: str = Field(..., max_length=200)


class AltaIn(BaseModel):
    credencial: dict
    estado: str = Field(..., max_length=2000)
    nombre: str | None = Field(None, max_length=120)


class IdiomaIn(BaseModel):
    idioma: str = Field(..., max_length=5)


def _ip(peticion: Request) -> str | None:
    return peticion.client.host if peticion.client else None


@router.post("/entrar", summary="Entrar a LG Connect con correo y contrasena")
def entrar(datos: EntrarIn, peticion: Request, db: Session = Depends(get_db)):
    salida = motor.entrar(db, datos.correo, datos.contrasena, _ip(peticion))
    db.commit()
    return salida


@router.post("/codigo", summary="Crear la contrasena con el codigo que dicto la gerencia")
def codigo(datos: CodigoIn, peticion: Request, db: Session = Depends(get_db)):
    salida = motor.usar_codigo(db, datos.correo, datos.codigo, datos.nueva, _ip(peticion))
    db.commit()
    return salida


@router.post("/llaves/entrada/opciones", summary="El reto para entrar con huella o cara")
def opciones_entrada(datos: OpcionesEntradaIn, db: Session = Depends(get_db)):
    return motor.opciones_de_entrada(db, datos.correo)


@router.post("/llaves/entrada", summary="Entrar con huella o cara")
def entrada(datos: EntradaIn, db: Session = Depends(get_db)):
    salida = motor.entrar_con_huella(db, datos.credencial, datos.estado)
    db.commit()
    return salida


@router.get("/yo", summary="Mi dia: mi marca de hoy, mi semana y los patios")
def yo(db: Session = Depends(get_db), operador: m.LgOperador = Depends(YO)):
    return motor.mi_dia(db, operador)


@router.post("/jornada", status_code=201, summary="Marcar mi inicio de jornada")
def jornada(datos: MarcaIn, db: Session = Depends(get_db),
            operador: m.LgOperador = Depends(YO)):
    lg_jornada.marcar(db, operador, datos.lat, datos.lon, datos.precision, datos.nota)
    db.commit()
    return motor.mi_dia(db, operador)


@router.post("/contrasena", summary="Cambiar mi contrasena")
def contrasena(datos: CambioIn, db: Session = Depends(get_db),
               operador: m.LgOperador = Depends(YO)):
    salida = motor.cambiar_contrasena(db, operador, datos.actual, datos.nueva)
    db.commit()
    return salida


@router.post("/idioma", summary="Mi idioma")
def idioma(datos: IdiomaIn, db: Session = Depends(get_db),
           operador: m.LgOperador = Depends(YO)):
    if datos.idioma in ("es", "en", "pt"):
        operador.idioma = datos.idioma
        db.commit()
    return {"idioma": operador.idioma}


@router.get("/llaves", summary="Mis telefonos con huella")
def llaves(db: Session = Depends(get_db), operador: m.LgOperador = Depends(YO)):
    return motor.mis_llaves(db, operador)


@router.post("/llaves/alta/opciones", summary="Lo que el telefono necesita para la huella")
def alta_opciones(datos: AltaOpcionesIn, peticion: Request, db: Session = Depends(get_db),
                  operador: m.LgOperador = Depends(YO)):
    return motor.opciones_de_alta(db, operador, datos.contrasena, _ip(peticion))


@router.post("/llaves/alta", status_code=201, summary="Activar la huella en este telefono")
def alta(datos: AltaIn, db: Session = Depends(get_db), operador: m.LgOperador = Depends(YO)):
    llave = motor.dar_de_alta(db, operador, datos.credencial, datos.estado, datos.nombre)
    db.commit()
    return {"id": llave.id, "nombre": llave.nombre, "credencial_id": llave.credencial_id}


@router.delete("/llaves/{llave_id}", status_code=204, summary="Quitar la huella de un telefono")
def quitar(llave_id: int, db: Session = Depends(get_db),
           operador: m.LgOperador = Depends(YO)):
    motor.quitar_llave(db, operador, llave_id)
    db.commit()

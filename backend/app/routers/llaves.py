"""Entrar con huella o cara (30 sep). La logica vive en `app/llaves.py`."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, llaves
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/auth/llaves", tags=["Acceso"])


class AltaIn(BaseModel):
    contrasena: str = Field(..., max_length=200)


class CredencialIn(BaseModel):
    credencial: dict
    estado: str = Field(..., max_length=2000)
    # Como se llamara en su lista: lo propone la pantalla ("Chrome en
    # Android") y se puede dejar asi.
    nombre: str | None = Field(None, max_length=120)


class EntradaIn(BaseModel):
    correo: str | None = Field(None, max_length=160)


def _ip(peticion: Request) -> str | None:
    return peticion.client.host if peticion.client else None


@router.post("/alta/opciones", summary="Empezar a activar la huella en este equipo")
def alta_opciones(datos: AltaIn, peticion: Request,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(auth.usuario_actual)):
    return llaves.opciones_de_alta(db, usuario, datos.contrasena, _ip(peticion))


@router.post("/alta", status_code=201, summary="Activar la huella en este equipo")
def alta(datos: CredencialIn, db: Session = Depends(get_db),
         usuario: m.Usuario = Depends(auth.usuario_actual)):
    llave = llaves.dar_de_alta(db, usuario, datos.credencial, datos.estado,
                               datos.nombre)
    return {"id": llave.id, "nombre": llave.nombre,
            "credencial_id": llave.credencial_id}


@router.post("/entrada/opciones", summary="Empezar a entrar con huella")
def entrada_opciones(datos: EntradaIn, db: Session = Depends(get_db)):
    return llaves.opciones_de_entrada(db, datos.correo)


@router.post("/entrada", summary="Entrar con huella")
def entrada(datos: CredencialIn, db: Session = Depends(get_db)):
    """Devuelve lo mismo que entrar con contrasena: la sesion dura lo
    mismo y vale lo mismo."""
    usuario = llaves.entrar(db, datos.credencial, datos.estado)
    return {"access_token": auth.crear_token(usuario), "token_type": "bearer",
            "rol": usuario.rol.value, "nombre": usuario.persona.nombre,
            "correo": usuario.correo}


@router.get("", summary="Mis equipos con huella")
def mias(db: Session = Depends(get_db),
         usuario: m.Usuario = Depends(auth.usuario_actual)):
    return llaves.de(db, usuario)


@router.delete("/{llave_id}", status_code=204, summary="Quitar la huella de un equipo")
def quitar(llave_id: int, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(auth.usuario_actual)):
    llaves.quitar(db, usuario, llave_id)

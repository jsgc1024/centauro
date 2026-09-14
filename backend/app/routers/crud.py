"""Fabrica de routers CRUD: evita repetir el mismo codigo por cada catalogo."""
from typing import Type

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth
from app import models as m
from app.db import get_db


def crud_router(
    *,
    modelo: Type,
    esquema_in: Type[BaseModel],
    esquema_out: Type[BaseModel],
    prefijo: str,
    etiqueta: str,
    actividad: str | None = None,
) -> APIRouter:
    """Un catalogo se administra desde el rol de administracion, salvo que
    se le nombre una actividad: entonces lo puede tocar quien la tenga.

    Lo primero vale para el tarifario, que nadie mas debe mover. Lo
    segundo para catalogos que crecen durante la operacion, como las
    ciudades: el consultor da de alta el servicio y la ciudad al mismo
    tiempo, sin esperar a que alguien se la de de alta.
    """
    router = APIRouter(prefix=prefijo, tags=[etiqueta])
    escribir = (auth.puede(actividad) if actividad
                else auth.requiere(m.Rol.ADMIN))

    @router.get("", response_model=list[esquema_out], summary=f"Listar {etiqueta}")
    def listar(db: Session = Depends(get_db), limite: int = 200,
               incluir_inactivos: bool = False,
               _=Depends(auth.usuario_actual)):
        """Lo dado de baja no se ofrece: si una ciudad, una persona o una
        unidad se desactivo, no tiene por que seguir apareciendo en las
        listas donde se elige. La pantalla de administracion la pide con
        incluir_inactivos para poder reactivarla."""
        consulta = db.query(modelo)
        if hasattr(modelo, "activo") and not incluir_inactivos:
            consulta = consulta.filter(modelo.activo.is_(True))
        return consulta.limit(limite).all()

    @router.get("/{item_id}", response_model=esquema_out, summary=f"Ver {etiqueta}")
    def ver(item_id: int, db: Session = Depends(get_db),
            _=Depends(auth.usuario_actual)):
        obj = db.get(modelo, item_id)
        if not obj:
            raise HTTPException(404, f"No existe el registro {item_id}")
        return obj

    @router.post("", response_model=esquema_out, status_code=201, summary=f"Crear {etiqueta}")
    def crear(datos: esquema_in, db: Session = Depends(get_db),
              _=Depends(escribir)):
        obj = modelo(**datos.model_dump())
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @router.patch("/{item_id}", response_model=esquema_out, summary=f"Editar {etiqueta}")
    def editar(item_id: int, datos: esquema_in, db: Session = Depends(get_db),
               _=Depends(escribir)):
        obj = db.get(modelo, item_id)
        if not obj:
            raise HTTPException(404, f"No existe el registro {item_id}")
        for campo, valor in datos.model_dump(exclude_unset=True).items():
            setattr(obj, campo, valor)
        db.commit()
        db.refresh(obj)
        return obj

    @router.delete("/{item_id}", status_code=204, summary=f"Desactivar {etiqueta}")
    def desactivar(item_id: int, db: Session = Depends(get_db),
                   _=Depends(escribir)):
        obj = db.get(modelo, item_id)
        if not obj:
            raise HTTPException(404, f"No existe el registro {item_id}")
        if hasattr(obj, "activo"):
            obj.activo = False          # nunca borramos historia, solo desactivamos
        else:
            db.delete(obj)
        db.commit()

    return router

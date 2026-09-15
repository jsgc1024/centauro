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

    # Leer un catalogo es cosa de la consola. Aqui viven la plantilla
    # completa con telefonos, el tarifario que se le cobra al cliente y
    # lo que se le paga a cada rol: con la sesion de un elemento de
    # campo se sacaba todo de corrido. La app de campo no toca
    # /catalogos —lo suyo va por /campo—, asi que esto no le quita nada.
    leer = auth.requiere(m.Rol.ADMIN, m.Rol.CONSULTOR, m.Rol.CENTRAL,
                         m.Rol.FINANZAS, m.Rol.DIRECTOR_OPERACIONES,
                         m.Rol.DIRECTOR_GENERAL)

    @router.get("", response_model=list[esquema_out], summary=f"Listar {etiqueta}")
    def listar(db: Session = Depends(get_db), limite: int = 5000,
               incluir_inactivos: bool = False,
               _=Depends(leer)):
        """Lo dado de baja no se ofrece: si una ciudad, una persona o una
        unidad se desactivo, no tiene por que seguir apareciendo en las
        listas donde se elige. La pantalla de administracion la pide con
        incluir_inactivos para poder reactivarla.

        El limite es alto a proposito. Estaba en 200 y las pantallas lo
        piden sin parametro, asi que con mas de 200 personas de campo la
        201 desaparecia: no salia en el selector para asignarla, ni en
        la lista para registrarle un ajuste, y nada avisaba. Un catalogo
        que se corta en silencio es peor que uno que tarda.

        Y sale ordenado: sin ORDER BY, Postgres no promete un orden, asi
        que dos cargas de la misma pantalla podian traer las filas
        distintas.
        """
        consulta = db.query(modelo)
        if hasattr(modelo, "activo") and not incluir_inactivos:
            consulta = consulta.filter(modelo.activo.is_(True))
        orden = getattr(modelo, "nombre", None)
        consulta = consulta.order_by(orden if orden is not None else modelo.id)
        return consulta.limit(limite).all()

    @router.get("/{item_id}", response_model=esquema_out, summary=f"Ver {etiqueta}")
    def ver(item_id: int, db: Session = Depends(get_db),
            _=Depends(leer)):
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

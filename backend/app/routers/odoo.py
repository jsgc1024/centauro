"""Sincronizacion con Odoo: empleados y flota.

Odoo es la fuente de verdad del nombre, telefono y fotografia. El sistema
no los captura: los recibe por aqui y los guarda para que el task sheet
los muestre sin depender de que Odoo responda en ese momento.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models as m
from app import odoo, schemas as s
from app.auth import requiere
from app.db import get_db

router = APIRouter(prefix="/odoo", tags=["Odoo"])


@router.post("/personal", summary="Recibir empleados desde Odoo")
def personal(empleados: list[s.EmpleadoOdoo],
             db: Session = Depends(get_db),
             _=Depends(requiere(m.Rol.ADMIN))):
    return odoo.sincronizar_personal(
        db, [e.model_dump(exclude_none=True) for e in empleados])


@router.post("/flota", summary="Recibir la flota desde Odoo")
def flota(vehiculos: list[s.VehiculoOdoo],
          db: Session = Depends(get_db),
          _=Depends(requiere(m.Rol.ADMIN))):
    return odoo.sincronizar_flota(
        db, [v.model_dump(exclude_none=True) for v in vehiculos])


@router.post("/capacitaciones",
             summary="Recibir los cursos y certificados desde Odoo")
def capacitaciones(filas: list[s.CapacitacionOdoo],
                   db: Session = Depends(get_db),
                   _=Depends(requiere(m.Rol.ADMIN))):
    """Los cursos del personal viven en Odoo y entran por aqui.

    De este padron sale si alguien esta al corriente --el criterio del
    bono y la dimension de la calificacion-- y de aqui salen los avisos
    de certificado por vencer. Mientras no llegue la primera carga, ese
    criterio simplemente no aplica: nadie reprueba por un padron vacio.
    """
    return odoo.sincronizar_capacitaciones(
        db, [f.model_dump(exclude_none=False) for f in filas])


@router.post("/taller", summary="Recibir del taller las unidades fuera")
def taller(entradas: list[s.TallerOdoo],
           db: Session = Depends(get_db),
           _=Depends(requiere(m.Rol.ADMIN))):
    """El mantenimiento de la flota vive en Odoo. Aqui solo se recibe el
    rango en que cada unidad esta fuera, para dejar de ofrecerla."""
    return odoo.sincronizar_taller(
        db, [e.model_dump(exclude_none=True) for e in entradas])

"""Tablero de profesionalismo del personal de seguridad."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth
from app import models as m
from app import profesionalismo as motor
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/profesionalismo", tags=["Profesionalismo"])

LECTURA = auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL,
                        m.Rol.DIRECTOR_OPERACIONES)
CONFIGURA = auth.requiere(m.Rol.ADMIN, m.Rol.DIRECTOR_OPERACIONES)


@router.get("", summary="Tablero de todo el personal")
def tablero(pais_id: int, plaza_id: int | None = None,
            db: Session = Depends(get_db),
            _=Depends(LECTURA)):
    return motor.tabla(db, pais_id, plaza_id)


@router.get("/persona/{persona_id}", summary="Ficha de una persona")
def ficha(persona_id: int, db: Session = Depends(get_db), _=Depends(LECTURA)):
    resultado = motor.ficha(db, persona_id)
    if not resultado:
        raise HTTPException(404, f"No existe la persona {persona_id}")
    return resultado


@router.get("/pesos", summary="Ver los pesos de cada dimension")
def ver_pesos(pais_id: int, db: Session = Depends(get_db), _=Depends(LECTURA)):
    tabla = motor.pesos(db, pais_id)
    p = motor.parametros(db, pais_id)
    return {
        "pais_id": pais_id,
        "pesos": {d.value: float(v) for d, v in tabla.items()},
        "suma": float(sum(tabla.values())),
        "ventana_meses": p.meses_ventana,
        "horas_referencia": p.horas_referencia,
        "castigo_por_incidencia": {
            "error_menor": float(p.castigo_error_menor),
            "leve": float(p.castigo_leve),
            "grave": float(p.castigo_grave),
        },
        "configurado": bool(db.query(m.PesoProfesionalismo)
                            .filter_by(pais_id=pais_id).first()),
    }


@router.put("/pesos", summary="Definir los pesos de cada dimension")
def definir_pesos(datos: s.PesosProfesionalismoIn,
                  db: Session = Depends(get_db), _=Depends(CONFIGURA)):
    """Los cinco pesos tienen que sumar 100. Si no, la calificacion no
    significaria lo mismo entre una persona y otra."""
    suma = sum(datos.pesos.values())
    if abs(suma - 100) > 0.01:
        raise HTTPException(409, {
            "mensaje": "Los pesos tienen que sumar 100",
            "suma": float(suma)})

    faltan = set(d.value for d in m.DimensionProfesionalismo) - set(datos.pesos)
    if faltan:
        raise HTTPException(400, {
            "mensaje": "Faltan dimensiones por definir",
            "dimensiones": sorted(faltan)})

    for nombre, peso in datos.pesos.items():
        dimension = m.DimensionProfesionalismo(nombre)
        fila = (db.query(m.PesoProfesionalismo)
                .filter_by(pais_id=datos.pais_id, dimension=dimension).first())
        if fila:
            fila.peso = peso
            fila.activo = True
        else:
            db.add(m.PesoProfesionalismo(pais_id=datos.pais_id,
                                         dimension=dimension, peso=peso))

    p = (db.query(m.ParametroProfesionalismo)
         .filter_by(pais_id=datos.pais_id).first())
    if not p:
        p = m.ParametroProfesionalismo(pais_id=datos.pais_id)
        db.add(p)
    if datos.meses_ventana is not None:
        p.meses_ventana = datos.meses_ventana
    if datos.horas_referencia is not None:
        p.horas_referencia = datos.horas_referencia
    if datos.castigo_leve is not None:
        p.castigo_leve = datos.castigo_leve
    if datos.castigo_grave is not None:
        p.castigo_grave = datos.castigo_grave
    if datos.castigo_error_menor is not None:
        p.castigo_error_menor = datos.castigo_error_menor

    db.commit()
    return {"resultado": "guardado", "pais_id": datos.pais_id,
            "pesos": datos.pesos}

"""Tablero de profesionalismo del personal de seguridad."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import accesos, auth
from app import models as m
from app import profesionalismo as motor
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/profesionalismo", tags=["Profesionalismo"])

LECTURA = auth.puede("profesionalismo.ver")
CONFIGURA = auth.puede("profesionalismo.pesos")


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


@router.get("/persona/{persona_id}/expediente",
            summary="El bono, lo que dijeron los clientes y sus certificados")
def expediente(persona_id: int, meses: int = 6,
               db: Session = Depends(get_db), _=Depends(LECTURA)):
    """Los tres bloques de la ficha, debajo de las dimensiones.

    Viven en tres tablas distintas y hasta hoy no se podian ver juntos:
    para decidir a quien mandar habia que abrir tres pantallas y
    acordarse de las tres.
    """
    return motor.expediente(db, persona_id, meses)


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
        "puntos_por_evento_manejo": float(p.puntos_por_evento_manejo),
        "configurado": bool(db.query(m.PesoProfesionalismo)
                            .filter_by(pais_id=pais_id).first()),
    }


# Los parametros que no son peso y se pueden mover desde aqui.
PARAMETROS = ("meses_ventana", "horas_referencia", "castigo_error_menor",
              "castigo_leve", "castigo_grave", "puntos_por_evento_manejo")


def _en_200(partes: list[str]) -> str | None:
    """Lo que cabe en la columna de la bitacora."""
    texto = "; ".join(partes)
    return (texto[:197] + "...") if len(texto) > 200 else (texto or None)


def _lo_que_cambio(antes_pesos: dict, antes_p, datos) -> tuple[list, list]:
    """Solo lo que se movio, con su valor de antes (seccion 86)."""
    antes, despues = [], []
    for nombre, peso in datos.pesos.items():
        previo = antes_pesos.get(nombre)
        if previo is None or Decimal(str(previo)) != Decimal(str(peso)):
            antes.append(f"{nombre}: {previo}")
            despues.append(f"{nombre}: {peso}")
    for campo in PARAMETROS:
        nuevo = getattr(datos, campo)
        if nuevo is None:
            continue
        previo = getattr(antes_p, campo)
        if Decimal(str(previo)) != Decimal(str(nuevo)):
            antes.append(f"{campo}: {previo}")
            despues.append(f"{campo}: {nuevo}")
    return antes, despues


@router.put("/pesos", summary="Definir los pesos de cada dimension")
def definir_pesos(datos: s.PesosProfesionalismoIn,
                  db: Session = Depends(get_db),
                  actor: m.Usuario = Depends(CONFIGURA)):
    """Los seis pesos tienen que sumar 100. Si no, la calificacion no
    significaria lo mismo entre una persona y otra.

    Desde la seccion 86 el cambio queda en la bitacora, como el de
    cualquier catalogo: los pesos deciden como se califica a la gente, y
    un dia alguien va a preguntar desde cuando pesa asi."""
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

    antes_pesos = {d.value: v for d, v in motor.pesos(db, datos.pais_id).items()}
    antes_p = motor.parametros(db, datos.pais_id)
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
    if datos.puntos_por_evento_manejo is not None:
        p.puntos_por_evento_manejo = datos.puntos_por_evento_manejo

    antes, despues = _lo_que_cambio(antes_pesos, antes_p, datos)
    if antes:
        pais = db.get(m.Pais, datos.pais_id)
        accesos.anotar(db, actor, "catalogo cambiado", "profesionalismo",
                       datos.pais_id, antes=_en_200(antes),
                       despues=_en_200(despues),
                       detalle=pais.nombre if pais else None)
    db.commit()
    return {"resultado": "guardado", "pais_id": datos.pais_id,
            "pesos": datos.pesos}

"""El riesgo de fondo en la consola: el Nivel Centauro (seccion 138).

Quien ve el mapa de riesgo lo ve; el analista (quien publica eventos)
sube fuentes, recalcula y ajusta; el jefe de turno (quien confirma el
nivel 4) publica el mes; quien lleva los catalogos cambia pesos y cortes.
"""
import json
from datetime import date

from fastapi import (APIRouter, Depends, File, Form, HTTPException,
                     UploadFile)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app import fuentes_riesgo as fuentes
from app import models as m
from app import nivel_centauro as motor
from app.db import get_db

router = APIRouter(prefix="/riesgo/nivel", tags=["Central de Inteligencia"])

VER = auth.puede("riesgo.ver")
ANALISTA = auth.puede("riesgo.publicar")
JEFE = auth.puede("riesgo.confirmar")
CATALOGO = auth.puede("riesgo.catalogo")


class CalcularIn(BaseModel):
    pais_id: int | None = None
    periodo: date | None = None


class AjusteIn(BaseModel):
    valor: float = Field(ge=0, le=100)
    motivo: str = Field(max_length=400)


class ParametrosIn(BaseModel):
    pais_id: int | None = None
    pesos: dict[str, float] | None = None
    cortes: list[float] | None = None
    referencia_id: int | None = None
    quitar_referencia: bool = False


def _pais(db: Session, pais_id: int | None) -> m.Pais:
    pais = (db.get(m.Pais, pais_id) if pais_id
            else db.query(m.Pais).filter_by(codigo="MX").first())
    if not pais:
        raise HTTPException(404, "No existe ese país")
    return pais


def _mes(db: Session, mes_id: int) -> m.NivelMes:
    mes = db.get(m.NivelMes, mes_id)
    if not mes:
        raise HTTPException(404, f"No existe el mes {mes_id}")
    return mes


@router.get("", summary="El nivel de un mes, por estado")
def ver(pais_id: int | None = None, mes_id: int | None = None,
        db: Session = Depends(get_db),
        usuario: m.Usuario = Depends(VER)):
    pais = _pais(db, pais_id)
    meses = motor.meses(db, pais)
    borrador = next((x for x in meses if x["estado"] == "borrador"), None)
    mes = (_mes(db, mes_id) if mes_id else motor.vigente(db, pais))
    if mes is None and borrador:
        mes = db.get(m.NivelMes, borrador["id"])
    return {
        "mes": motor.vista_mes(db, mes) if mes else None,
        "meses": meses, "borrador_id": borrador["id"] if borrador else None,
        "cargas": motor.cargas(db),
        "parametros": motor.parametros(db, pais),
        "puede": {
            "analista": auth.puede_el_usuario(db, usuario, "riesgo.publicar"),
            "publicar": auth.puede_el_usuario(db, usuario, "riesgo.confirmar"),
            "parametros": auth.puede_el_usuario(db, usuario,
                                                "riesgo.catalogo")},
    }


@router.get("/{mes_id}/estados/{region_id}",
            summary="Un estado y sus municipios en un mes")
def estado(mes_id: int, region_id: int, db: Session = Depends(get_db),
           _=Depends(VER)):
    mes = _mes(db, mes_id)
    estados = motor.vista_mes(db, mes, region_id=region_id)
    municipios = motor.vista_mes(db, mes, region_id=region_id,
                                 con_municipios=True)
    if not estados["lugares"]:
        raise HTTPException(404, "Ese estado no está en ese mes")
    return {"estado": estados["lugares"][0],
            "municipios": municipios["lugares"]}


@router.get("/{mes_id}/revisar", summary="Lo que hay que ver antes de publicar")
def revisar(mes_id: int, db: Session = Depends(get_db), _=Depends(VER)):
    return motor.para_revisar(db, _mes(db, mes_id))


@router.post("/calcular", summary="Calcular (o rehacer) el borrador de un mes")
def calcular(datos: CalcularIn, db: Session = Depends(get_db),
             _=Depends(ANALISTA)):
    pais = _pais(db, datos.pais_id)
    periodo = datos.periodo or _ultimo_mes_con_datos(db) or \
        motor.mes_a_calcular(pais)
    mes = motor.calcular(db, pais, periodo)
    db.commit()
    return motor.vista_mes(db, mes)


def _ultimo_mes_con_datos(db: Session) -> date | None:
    carga = (db.query(m.CargaFuente).filter_by(fuente=fuentes.FUENTE_SESNSP)
             .order_by(m.CargaFuente.periodo.desc()).first())
    return carga.periodo if carga else None


@router.post("/lugares/{lugar_id}/ajuste", summary="Ajustar un nivel con motivo")
def ajustar(lugar_id: int, datos: AjusteIn, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(ANALISTA)):
    lugar = motor.ajustar(db, usuario, lugar_id, datos.valor, datos.motivo)
    db.commit()
    mes = db.get(m.NivelMes, lugar.nivel_mes_id)
    return motor.vista_lugar(lugar, json.loads(mes.resumen)["cortes"])


@router.post("/{mes_id}/publicar", summary="Publicar el nivel del mes")
def publicar(mes_id: int, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(JEFE)):
    mes = motor.publicar(db, usuario, mes_id)
    db.commit()
    return motor.vista_mes(db, mes)


@router.post("/fuentes/sesnsp", summary="Subir el archivo del Secretariado")
async def subir_sesnsp(archivo: UploadFile = File(...),
                       db: Session = Depends(get_db),
                       usuario: m.Usuario = Depends(ANALISTA)):
    contenido = await archivo.read()
    datos = fuentes.leer_sesnsp(contenido, archivo.filename)
    carga = fuentes.guardar_sesnsp(db, datos, "subida", archivo.filename,
                                   usuario)
    pais = _pais(db, None)
    mes = _recalcular(db, pais, carga.periodo)
    db.commit()
    return {"periodo": carga.periodo.isoformat(), "filas": carga.filas,
            "mes_id": mes.id if mes else None,
            "nota": json.loads(carga.nota)}


def _recalcular(db: Session, pais: m.Pais, periodo: date) -> m.NivelMes | None:
    """Con datos nuevos se rehace el borrador de ese mes; si ese mes ya se
    publico, se deja como esta."""
    previo = db.query(m.NivelMes).filter_by(pais_id=pais.id,
                                            periodo=periodo).first()
    if previo and previo.estado == "publicado":
        return None
    return motor.calcular(db, pais, periodo)


@router.post("/fuentes/sesnsp/bajar",
             summary="Buscar ahora el archivo del Secretariado")
def bajar_sesnsp(db: Session = Depends(get_db), _=Depends(ANALISTA)):
    salida = fuentes.bajar_sesnsp(db)
    if salida.get("resultado") == "nuevo":
        _recalcular(db, _pais(db, None), date.fromisoformat(salida["periodo"]))
    db.commit()
    return salida


@router.post("/fuentes/encuesta", summary="Subir una encuesta del INEGI")
async def subir_encuesta(fuente: str = Form(...), periodo: date = Form(...),
                         archivo: UploadFile = File(...),
                         db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(ANALISTA)):
    contenido = await archivo.read()
    salida = fuentes.guardar_encuesta(db, fuente, motor._mes(periodo),
                                      contenido, archivo.filename, usuario)
    pais = _pais(db, None)
    periodo_sesnsp = _ultimo_mes_con_datos(db)
    if periodo_sesnsp:
        _recalcular(db, pais, periodo_sesnsp)
    db.commit()
    return salida


@router.put("/parametros", summary="Cambiar pesos, cortes o referencia")
def cambiar_parametros(datos: ParametrosIn, db: Session = Depends(get_db),
                       _=Depends(CATALOGO)):
    pais = _pais(db, datos.pais_id)
    salida = motor.guardar_parametros(db, pais, datos.pesos, datos.cortes,
                                      datos.referencia_id,
                                      datos.quitar_referencia)
    db.commit()
    return salida

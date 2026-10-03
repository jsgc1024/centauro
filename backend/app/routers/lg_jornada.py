"""Centauro Logistica: la jornada de los operadores (seccion 151).

La pantalla Operaciones LG -> Jornada LG. La abre quien trae
`lg.jornada.ver` --la gerencia de Logistica, quien lleva la flota, la
Central, sistema y calidad--. La Central valida o rechaza las marcas
fuera del patio (`lg.jornada.validar`); la gerencia y quien lleva la flota
capturan la licencia y dan el codigo de LG Connect (`lg.operadores.editar`).
Las reglas viven en `app/lg_jornada.py` y `app/lg_app.py`.
"""
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, lg_app, lg_disponibilidad
from app import lg_flota as fl
from app import lg_jornada as jo
from app import models as m
from app import odoo_lg
from app.db import get_db
from app.routers.lg_flota import _leer

router = APIRouter(prefix="/lg/jornada", tags=["Logistica: jornada"])

VE = auth.puede("lg.jornada.ver")
VALIDA = auth.puede("lg.jornada.validar")
OPERADORES = auth.puede("lg.operadores.editar")
VIAJE = auth.puede("lg.en_viaje.marcar")
OBJETOS = ("lg_jornada", "lg_operadores")


class RevisionIn(BaseModel):
    validar: bool
    justificacion: str = Field(..., max_length=300)


class ViajeIn(BaseModel):
    """Con `hasta`, un viaje nuevo; sin el, «ya regreso»: el viaje termina
    el dia de `regreso` (ayer, si no se dice)."""
    desde: date | None = None
    hasta: date | None = None
    regreso: date | None = None


class OdooIn(BaseModel):
    aplicar: bool = False


def _puede(db: Session, usuario: m.Usuario) -> dict:
    return {"validar": auth.puede_el_usuario(db, usuario, "lg.jornada.validar"),
            "operadores": auth.puede_el_usuario(db, usuario, "lg.operadores.editar"),
            "en_viaje": auth.puede_el_usuario(db, usuario, "lg.en_viaje.marcar")}


def _operador(db: Session, operador_id: int) -> m.LgOperador:
    o = db.get(m.LgOperador, operador_id)
    if not o:
        raise HTTPException(404, "No existe ese operador")
    return o


@router.get("/dia", summary="Quien se presento a trabajar ese dia")
def dia(fecha: date | None = None, db: Session = Depends(get_db),
        usuario: m.Usuario = Depends(VE)):
    return {**jo.dia(db, fecha), "puede": _puede(db, usuario),
            "por_validar": len(jo.por_validar(db))}


@router.get("/semana", summary="La semana de cada operador y su bono de movilidad")
def semana(lunes: date | None = None, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(VE)):
    return {**jo.semana(db, lunes), "por_validar": len(jo.por_validar(db))}


@router.get("/por-validar", summary="Las marcas fuera del patio que esperan a la Central")
def por_validar(db: Session = Depends(get_db), usuario: m.Usuario = Depends(VE)):
    return {"marcas": jo.por_validar(db), "puede": _puede(db, usuario)}


@router.post("/marcas/{jornada_id}/revisar", summary="Validar o rechazar una marca")
def revisar(jornada_id: int, entrada: RevisionIn, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(VALIDA)):
    jo.revisar(db, usuario, jornada_id, entrada.validar, entrada.justificacion)
    db.commit()
    return {"marcas": jo.por_validar(db), "puede": _puede(db, usuario)}


@router.get("/operadores", summary="Los operadores, su licencia y su acceso a LG Connect")
def operadores(db: Session = Depends(get_db), usuario: m.Usuario = Depends(VE)):
    return {**jo.operadores(db), "puede": _puede(db, usuario),
            "odoo": odoo_lg.ultima(db, odoo_lg.TIPO_OPERADORES),
            "por_validar": len(jo.por_validar(db))}


@router.post("/operadores/{operador_id}/licencia", status_code=201,
             summary="La licencia federal del operador, con su archivo")
def licencia(operador_id: int, folio: str | None = Form(None), detalle: str | None = Form(None),
             vence_en: date | None = Form(None), archivo: UploadFile | None = File(None),
             db: Session = Depends(get_db), usuario: m.Usuario = Depends(OPERADORES)):
    operador = _operador(db, operador_id)
    fila = None
    nombre, tipo, contenido = _leer(archivo)
    if contenido is not None:
        fila = fl.guardar_archivo(db, usuario, nombre, tipo, contenido)
    fl.capturar_documento(db, usuario, fl.LICENCIA, operador=operador, folio=folio,
                          detalle=detalle, vence_en=vence_en, archivo=fila)
    db.commit()
    return jo.operadores(db)


@router.post("/operadores/{operador_id}/codigo",
             summary="Los cuatro digitos para que el operador cree su contrasena")
def codigo(operador_id: int, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(OPERADORES)):
    salida = lg_app.dar_codigo(db, usuario, operador_id)
    db.commit()
    return salida


@router.post("/operadores/{operador_id}/en-viaje",
             summary="Marcar a mano que el operador va en viaje (mientras siga Tango)")
def en_viaje(operador_id: int, entrada: ViajeIn, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(VIAJE)):
    operador = _operador(db, operador_id)
    if entrada.hasta is not None:
        jo.marcar_en_viaje(db, usuario, operador, entrada.desde, entrada.hasta)
    else:
        jo.terminar_viaje(db, usuario, operador, entrada.regreso)
    db.commit()
    return {**jo.operadores(db), "puede": _puede(db, usuario)}


@router.get("/operadores/{operador_id}/disponibilidad",
            summary="Si el operador puede salir a un viaje de esas fechas")
def disponibilidad(operador_id: int, desde: date | None = None, hasta: date | None = None,
                   db: Session = Depends(get_db), usuario: m.Usuario = Depends(VE)):
    return lg_disponibilidad.operador(db, operador_id, desde, hasta)


@router.post("/odoo", summary="Leer los operadores de Odoo: ensayo o aplicar")
def odoo_leer(entrada: OdooIn, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(OPERADORES)):
    from app import odoo_api
    if not odoo_api.hay_conexion():
        raise HTTPException(409, {"mensaje": "Odoo no está conectado en este servidor.",
                                  "que_hacer": "Sistema y calidad revisa la conexión en "
                                               "la pantalla de Odoo."})
    try:
        return odoo_lg.sincronizar_operadores(db, odoo_api.cliente(),
                                              ensayo=not entrada.aplicar, quien=usuario)
    except odoo_api.NoResponde as error:
        raise HTTPException(502, f"Odoo no contestó: {error}")


@router.get("/bitacora", summary="Lo que le ha pasado a la jornada y a los operadores")
def bitacora(pagina: int = 1, idioma: str = "es", db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(VE)):
    return fl.bitacora(db, OBJETOS, pagina, idioma)

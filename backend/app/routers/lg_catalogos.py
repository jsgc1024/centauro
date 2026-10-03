"""Centauro Logistica: los catalogos con vigencia por fecha (seccion 150).

La pantalla Operaciones LG -> Catalogos. La abre quien trae
`lg.catalogos.ver`; lo que decide dinero lo fija quien trae
`lg.catalogos.dinero` --la gerencia de Logistica-- y los tipos de unidad
y los patios, quien trae `lg.catalogos.editar` --sistema y calidad--.
Las reglas de la vigencia viven en `app/lg_catalogos.py`.
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app import lg_catalogos as lg
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/lg/catalogos", tags=["Logistica: catalogos"])

VE = auth.puede("lg.catalogos.ver")
FIJA = auth.puede("lg.catalogos.dinero")
LLEVA = auth.puede("lg.catalogos.editar")


class ValorIn(BaseModel):
    """Un valor desde una fecha. Los de un numero traen `valor`; los de
    varios --el tabulador, el costo del operador o de la unidad, el bono,
    la garantia-- traen `datos`."""
    clave: str = Field(..., max_length=30)
    tipo_unidad_id: int | None = None
    vigente_desde: date
    valor: float | str | None = None
    datos: dict | None = None
    motivo: str | None = Field(None, max_length=200)


class EdicionIn(BaseModel):
    """Lo programado, corregido: su nueva fecha y su valor."""
    vigente_desde: date
    valor: float | str | None = None
    datos: dict | None = None
    motivo: str | None = Field(None, max_length=200)


class TipoIn(BaseModel):
    nombre: str = Field(..., max_length=60)
    capacidad_ton: float | str | None = None
    nombre_tango: str | None = Field(None, max_length=60)
    orden: int | None = None


class PatioIn(BaseModel):
    nombre: str = Field(..., max_length=80)
    direccion: str | None = Field(None, max_length=300)
    lat: float | None = None
    lon: float | None = None
    geocerca_metros: int = 300


def _con_permisos(db: Session, usuario: m.Usuario, datos: dict) -> dict:
    """Lo que la pantalla necesita saber para no pintar un boton que va a
    contestar que no."""
    return {**datos, "puede": {
        "dinero": auth.puede_el_usuario(db, usuario, "lg.catalogos.dinero"),
        "editar": auth.puede_el_usuario(db, usuario, "lg.catalogos.editar"),
        "buscar": auth.puede_el_usuario(db, usuario, "mapas.buscar"),
    }}


@router.get("", summary="Los catalogos de Logistica, todos de una vez")
def leer(db: Session = Depends(get_db), usuario: m.Usuario = Depends(VE)):
    return _con_permisos(db, usuario, lg.todo(db))


@router.post("/valores", status_code=201,
             summary="Un valor nuevo desde una fecha")
def capturar(entrada: ValorIn, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(FIJA)):
    """Si ya hay uno vivo desde esa misma fecha, lo reemplaza: si aquel
    ya regia, pide el motivo. Con fecha que ya paso, tambien."""
    fila = lg.capturar(db, usuario, entrada.clave, entrada.vigente_desde,
                       {"valor": entrada.valor, "datos": entrada.datos},
                       tipo_unidad_id=entrada.tipo_unidad_id,
                       motivo=entrada.motivo)
    db.commit()
    return {"id": fila.id}


@router.put("/valores/{valor_id}", summary="Corregir lo programado")
def editar(valor_id: int, entrada: EdicionIn, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(FIJA)):
    fila = lg.editar_programado(db, usuario, valor_id, entrada.vigente_desde,
                                {"valor": entrada.valor, "datos": entrada.datos},
                                motivo=entrada.motivo)
    db.commit()
    return {"id": fila.id}


@router.delete("/valores/{valor_id}", summary="Quitar lo programado")
def quitar(valor_id: int, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(FIJA)):
    lg.quitar_programado(db, usuario, valor_id)
    db.commit()
    return {"ok": True}


@router.get("/comision", summary="Probar el tabulador con un viaje")
def probar(tipo_unidad_id: int, km: Decimal, fecha: date | None = None,
           db: Session = Depends(get_db), _=Depends(VE)):
    """La comision de un viaje con el tabulador que regia en su fecha, y
    como sale."""
    if km < 0 or km > 20000:
        raise HTTPException(400, {"mensaje": "Esos km no se ven bien.",
                                  "que_hacer": "Escribe los km cargados del "
                                               "viaje."})
    try:
        c = lg.comision(db, tipo_unidad_id, km, fecha)
    except lg.FaltaValor as falta:
        raise HTTPException(400, {"mensaje": str(falta)})
    return {k: (str(v) if isinstance(v, Decimal) else
                v.isoformat() if isinstance(v, date) else v)
            for k, v in c.items()}


@router.get("/bitacora", summary="Lo que le ha pasado a los catalogos")
def bitacora(catalogo: str | None = None, pagina: int = 1,
             idioma: str = "es", db: Session = Depends(get_db),
             _=Depends(VE)):
    return lg.bitacora(db, catalogo, pagina, idioma)


# ------------------------------------------------ tipos de unidad y patios

@router.post("/tipos", status_code=201, summary="Agregar un tipo de unidad")
def alta_tipo(entrada: TipoIn, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(LLEVA)):
    tipo = lg.alta_tipo(db, usuario, entrada.model_dump())
    db.commit()
    return {"id": tipo.id}


@router.patch("/tipos/{tipo_id}", summary="Cambiar un tipo de unidad")
def cambiar_tipo(tipo_id: int, entrada: TipoIn, db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(LLEVA)):
    lg.cambiar_tipo(db, usuario, tipo_id, entrada.model_dump())
    db.commit()
    return {"id": tipo_id}


@router.delete("/tipos/{tipo_id}", summary="Quitar un tipo de unidad")
def quitar_tipo(tipo_id: int, db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(LLEVA)):
    lg.prender(db, usuario, m.LgTipoUnidad, "lg_tipos", tipo_id, False)
    db.commit()
    return {"ok": True}


@router.post("/tipos/{tipo_id}/reactivar",
             summary="Volver a poner un tipo de unidad")
def reactivar_tipo(tipo_id: int, db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(LLEVA)):
    lg.prender(db, usuario, m.LgTipoUnidad, "lg_tipos", tipo_id, True)
    db.commit()
    return {"ok": True}


@router.post("/patios", status_code=201, summary="Agregar un patio")
def alta_patio(entrada: PatioIn, db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(LLEVA)):
    patio = lg.alta_patio(db, usuario, entrada.model_dump())
    db.commit()
    return {"id": patio.id}


@router.patch("/patios/{patio_id}", summary="Cambiar un patio")
def cambiar_patio(patio_id: int, entrada: PatioIn,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(LLEVA)):
    lg.cambiar_patio(db, usuario, patio_id, entrada.model_dump())
    db.commit()
    return {"id": patio_id}


@router.delete("/patios/{patio_id}", summary="Quitar un patio")
def quitar_patio(patio_id: int, db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(LLEVA)):
    lg.prender(db, usuario, m.LgPatio, "lg_patios", patio_id, False)
    db.commit()
    return {"ok": True}


@router.post("/patios/{patio_id}/reactivar", summary="Volver a poner un patio")
def reactivar_patio(patio_id: int, db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(LLEVA)):
    lg.prender(db, usuario, m.LgPatio, "lg_patios", patio_id, True)
    db.commit()
    return {"ok": True}

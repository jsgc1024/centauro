"""La pantalla de Calidad y su reporte del mes (seccion 89).

El mes en cifras de un pais: lo que dijo el cliente, la calle, el
cierre, la gente y los datos (`app.calidad`). La abre quien trae
`calidad.ver`: sistema y calidad, direccion de operaciones y, por lo que
hereda, direccion general. Los consultores no: compara a unos con otros.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import auth, calidad
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/calidad", tags=["Calidad"])

LEE = auth.puede("calidad.ver")


def _pais(db: Session, pais_id: int | None, usuario: m.Usuario) -> m.Pais:
    """El que se pidio; si no, el de quien mira; si no, Mexico; si no, el
    primero."""
    if pais_id is not None:
        pais = db.get(m.Pais, pais_id)
        if not pais:
            raise HTTPException(404, f"No existe el pais {pais_id}")
        return pais
    persona = usuario.persona
    if persona and persona.plaza and persona.plaza.pais:
        return persona.plaza.pais
    pais = (db.query(m.Pais).filter_by(codigo="MX").first()
            or db.query(m.Pais).filter(m.Pais.activo.is_(True))
            .order_by(m.Pais.nombre).first())
    if not pais:
        raise HTTPException(409, "Todavia no hay paises dados de alta")
    return pais


@router.get("", summary="El mes en cifras")
def ver(pais_id: int | None = None, mes: str | None = None,
        idioma: str = "es", db: Session = Depends(get_db),
        usuario: m.Usuario = Depends(LEE)):
    """`mes`: "2026-09"; sin mes, el de hoy, al dia. Cada cifra trae su
    detalle y su frase en `idioma`."""
    pais = _pais(db, pais_id, usuario)
    anio, numero = calidad.mes_pedido(mes, pais)
    resultado = calidad.reporte(db, pais.id, anio, numero, idioma)
    # El detalle ya viaja dentro de cada renglon: la lista suelta es para
    # el Excel.
    resultado.pop("detalles", None)
    resultado["opciones"] = calidad.opciones(db, pais, idioma=idioma)
    return resultado


@router.get("/excel", summary="El reporte del mes, en Excel")
def en_excel(pais_id: int | None = None, mes: str | None = None,
             idioma: str = "es", db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(LEE)):
    """Para la junta de direccion: el resumen con el mes de antes a su
    lado, y una hoja por cada detalle."""
    pais = _pais(db, pais_id, usuario)
    anio, numero = calidad.mes_pedido(mes, pais)
    contenido, nombre = calidad.excel_de(db, pais.id, anio, numero, idioma)
    return Response(
        content=contenido,
        media_type=("application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

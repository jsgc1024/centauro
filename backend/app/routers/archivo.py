"""Las fotos que ya se fueron al archivo (seccion 69).

Tres meses despues de la factura, la foto del ticket y la de la
devolucion se mudan a un deposito de Google. Desde ahi solo las traen de
vuelta direccion general y finanzas --decision de Salvador, 25 de
septiembre--, y cada vez queda en la bitacora del servicio: quien, cuando
y cual.

Lo que llega se compara con la huella que se guardo el dia que se
archivo. Si no coincide se dice, en vez de ensenarla como buena: una
foto del archivo que alguien cambio es justo lo que el archivo existe
para descubrir.
"""
import base64
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import archivo
from app import auditoria
from app import auth
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/archivo", tags=["Archivo de comprobantes"])

VER = auth.puede("archivo.ver")


def _dinero(monto, moneda) -> str:
    return f"${monto:,.2f} {moneda or ''}".strip()


def _traer(db: Session, usuario: m.Usuario, fila, que: str) -> dict:
    if not fila.archivo_objeto:
        raise HTTPException(404, {
            "mensaje": "Esa foto no esta en el archivo",
            "que_hacer": "Sigue en Centauro: se abre desde su miniatura."})
    try:
        traida = archivo.traer(fila)
    except archivo.Fallo as error:
        raise HTTPException(502, {
            "mensaje": "No se pudo traer la foto del archivo",
            "que_hacer": f"{error}. Intenta de nuevo en un momento."}) from None

    asignacion = fila.asignacion
    servicio = asignacion.jornada.equipo.servicio
    persona = asignacion.persona.nombre if asignacion.persona else None
    moneda = asignacion.moneda.value if asignacion.moneda else None
    if isinstance(fila, m.Comprobante):
        subida = fila.subido_en
        concepto = fila.concepto.value if fila.concepto else None
        tipo = fila.tipo.value if fila.tipo else None
    else:
        subida = fila.declarada_en or fila.confirmada_en
        concepto, tipo = "devolucion", "transferencia"

    ahora = datetime.now()
    detalle = (f"{que} de {persona or 'sin nombre'}, "
               f"{_dinero(fila.monto, moneda)}"
               + (f", subida el {subida:%d/%m/%Y %H:%M}" if subida else "")
               + ("" if traida["coincide"]
                  else ". LA HUELLA NO COINCIDE con la que se guardo"))
    auditoria.registrar(db, usuario, servicio, "foto traida del archivo",
                        detalle, jornada_id=asignacion.jornada_id)
    db.commit()

    return {
        "imagen": (f"data:{traida['tipo']};base64,"
                   f"{base64.b64encode(traida['datos']).decode()}"),
        "coincide": traida["coincide"],
        "traida_en": ahora.isoformat(),
        "por": usuario.persona.nombre if usuario.persona else None,
        "folio": servicio.folio,
        "persona": persona,
        "concepto": concepto,
        "descripcion": getattr(fila, "descripcion", None),
        "tipo": tipo,
        "monto": str(fila.monto),
        "moneda": moneda,
        "subida_en": subida.isoformat() if subida else None,
        "archivada_en": fila.archivado_en.isoformat(),
    }


@router.get("/comprobantes/{comprobante_id}",
            summary="La foto de un ticket, traida del archivo")
def traer_comprobante(comprobante_id: int, db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(VER)):
    fila = db.get(m.Comprobante, comprobante_id)
    if not fila:
        raise HTTPException(404, f"No existe el comprobante {comprobante_id}")
    return _traer(db, usuario, fila, "Comprobante")


@router.get("/devoluciones/{devolucion_id}",
            summary="La foto de una devolucion, traida del archivo")
def traer_devolucion(devolucion_id: int, db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(VER)):
    fila = db.get(m.DevolucionViatico, devolucion_id)
    if not fila:
        raise HTTPException(404, f"No existe la devolucion {devolucion_id}")
    return _traer(db, usuario, fila, "Devolucion")

"""El manual del sistema (seccion 90).

Lo leen quien administra el sistema --sistema y calidad, administracion y,
por lo que hereda, direccion general-- con `manual.ver`. El manual va
entero en una sola respuesta, en el idioma de quien lo lee; el estado del
sistema va aparte, porque es en vivo y se pide cada vez que se abre.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth, manual
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/manual", tags=["Manual del sistema"])

LEE = auth.puede("manual.ver")


class CasoIn(BaseModel):
    titulo: str | None = None
    que_se_vio: str | None = None
    causa: str | None = None
    solucion: str | None = None
    area: str | None = None
    falla: str | None = None


# Lo que falta, dicho como lo lee quien lo escribio.
FALTA = {
    "titulo": "Falta el título: lo que se vio, en una línea.",
    "que_se_vio": "Falta qué se vio.",
    "causa": "Falta la causa: sin ella es una queja, no un caso resuelto.",
    "solucion": "Falta cómo se arregló.",
    "falla": "Di si la causa fue una falla del sistema: sí, no o no sé.",
}


def _limpio(datos: CasoIn, parcial: bool) -> dict:
    try:
        return manual.limpiar_caso(datos.model_dump(exclude_unset=True), parcial)
    except ValueError as error:
        campo = str(error).split(":")[0]
        raise HTTPException(422, {
            "mensaje": FALTA.get(campo, f"No se puede guardar: {error}"),
            "que_hacer": "Corrígelo y vuelve a guardar.",
        })


@router.get("", summary="El manual del sistema, en el idioma de quien lo lee")
def leer(idioma: str | None = None, db: Session = Depends(get_db),
         _: m.Usuario = Depends(LEE)):
    return manual.manual(db, idioma)


@router.get("/estado", summary="Como esta el sistema ahora")
def estado(idioma: str | None = None, db: Session = Depends(get_db),
           _: m.Usuario = Depends(LEE)):
    return {"ahora": datetime.now(timezone.utc).isoformat(),
            "tarjetas": manual.estado(db, manual.idioma_de(idioma))}


@router.get("/casos", summary="Los casos resueltos, del mas nuevo al mas viejo")
def casos(db: Session = Depends(get_db), _: m.Usuario = Depends(LEE)):
    return manual.casos(db)


@router.post("/casos", status_code=201, summary="Anotar un caso resuelto")
def crear_caso(datos: CasoIn, db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(LEE)):
    valores = _limpio(datos, parcial=False)
    caso = m.CasoResuelto(**valores, escrito_por_id=usuario.persona_id)
    db.add(caso)
    db.commit()
    return next(c for c in manual.casos(db) if c["id"] == caso.id)


@router.patch("/casos/{caso_id}", summary="Corregir un caso resuelto")
def editar_caso(caso_id: int, datos: CasoIn, db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(LEE)):
    caso = db.get(m.CasoResuelto, caso_id)
    if caso is None:
        raise HTTPException(404, f"No existe el caso {caso_id}")
    for campo, valor in _limpio(datos, parcial=True).items():
        setattr(caso, campo, valor)
    caso.editado_por_id = usuario.persona_id
    caso.editado_en = datetime.now(timezone.utc)
    db.commit()
    return next(c for c in manual.casos(db) if c["id"] == caso.id)

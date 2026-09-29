"""El manual del sistema (seccion 90).

Lo leen quien administra el sistema --sistema y calidad, administracion y,
por lo que hereda, direccion general-- con `manual.ver`. El manual va
entero en una sola respuesta, en el idioma de quien lo lee; el estado del
sistema va aparte, porque es en vivo y se pide cada vez que se abre.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import arranque, auth, fallas, manual
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


class FallaIn(BaseModel):
    """Lo que manda quien reporta una falla (seccion 92). `contexto` es
    lo que la pantalla junta sola; se guarda recortado y nunca se usa
    para decidir nada."""
    que_paso: str
    esperaba: str | None = None
    captura: str | None = None
    contexto: dict | None = None


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


@router.post("/correo/reintentar", summary="Regresar a la cola los avisos fallidos")
def reintentar_correo(db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(LEE)):
    """Lo fallido vuelve a la cola y sale en la siguiente vuelta (seccion
    100). Antes no habia forma de reintentarlo sin tocar la base."""
    from app import accesos, correo

    cuantos = correo.reintentar_fallidas(db)
    accesos.anotar(db, usuario, "correo reintentado", "notificacion",
                   despues=str(cuantos))
    db.commit()
    return {"reintentados": cuantos}


# ------------------------------------------------ el arranque (seccion 97)
#
# Lo que falta para operar todo en Connect y apagar OVH, revisandose
# solo. Lo lee quien lee el manual; lo que no se revisa solo --el
# respaldo-- lo confirma a mano cualquiera de ellos, con su nombre.

@router.get("/arranque", summary="Lo que falta para operar todo en Connect")
def ver_arranque(idioma: str | None = None, db: Session = Depends(get_db),
                 _: m.Usuario = Depends(LEE)):
    return arranque.revisar(db, idioma)


@router.put("/arranque/{clave}/confirmacion",
            summary="Confirmar a mano un renglon del arranque")
def confirmar_arranque(clave: str, idioma: str | None = None,
                       db: Session = Depends(get_db),
                       usuario: m.Usuario = Depends(LEE)):
    arranque.confirmar(db, clave, usuario)
    db.commit()
    return arranque.revisar(db, idioma)


@router.delete("/arranque/{clave}/confirmacion",
               summary="Quitar la confirmacion a mano de un renglon")
def quitar_confirmacion_arranque(clave: str, idioma: str | None = None,
                                 db: Session = Depends(get_db),
                                 usuario: m.Usuario = Depends(LEE)):
    arranque.quitar(db, clave, usuario)
    db.commit()
    return arranque.revisar(db, idioma)


@router.get("/casos", summary="Los reportes abiertos primero y despues los casos resueltos")
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


# ------------------------------------------------------ reportar una falla

@router.get("/version", summary="Con que actualizacion esta el sistema")
def version(idioma: str | None = None,
            _: m.Usuario = Depends(auth.usuario_actual)):
    """Para la forma de reportar una falla, que la ensena entre lo que se
    manda solo. La ve cualquiera que entra: no dice nada del manual."""
    return manual.version(manual.idioma_de(idioma))


@router.post("/fallas", status_code=201, summary="Reportar una falla")
def reportar(datos: FallaIn, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(auth.usuario_actual)):
    """Cualquiera que entra al sistema, desde la consola o desde la app
    (seccion 92). Llega a los casos como «por revisar» y a sistema y
    calidad le llega el aviso."""
    caso = fallas.crear(db, usuario, datos.que_paso, esperaba=datos.esperaba,
                        captura=datos.captura, contexto=datos.contexto)
    return {"id": caso.id, "titulo": caso.titulo, "estado": caso.estado}


def _caso(db: Session, caso_id: int) -> m.CasoResuelto:
    caso = db.get(m.CasoResuelto, caso_id)
    if caso is None:
        raise HTTPException(404, f"No existe el caso {caso_id}")
    return caso


@router.get("/casos/{caso_id}/captura", summary="La captura de un reporte")
def captura(caso_id: int, db: Session = Depends(get_db),
            _: m.Usuario = Depends(LEE)):
    imagen = fallas.imagen(_caso(db, caso_id))
    if imagen is None:
        raise HTTPException(404, "Ese caso no trae captura")
    contenido, tipo = imagen
    return Response(content=contenido, media_type=tipo,
                    headers={"Cache-Control": "private, max-age=600"})


@router.post("/casos/{caso_id}/para-claude",
             summary="El reporte en texto, para pegarlo en la conversacion con Claude")
def para_claude(caso_id: int, db: Session = Depends(get_db),
                _: m.Usuario = Depends(LEE)):
    """El que estaba por revisar pasa a «con Claude»: la falla es del
    sistema y se esta arreglando."""
    caso = _caso(db, caso_id)
    texto = fallas.copiado(db, caso)
    return {"texto": texto,
            "caso": next(c for c in manual.casos(db) if c["id"] == caso.id)}


@router.post("/casos/{caso_id}/resolver", summary="Resolver un reporte")
def resolver(caso_id: int, datos: CasoIn, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(LEE)):
    """Con la causa y como se arreglo, y si fue falla del sistema. A quien
    lo reporto le llega el aviso."""
    caso = _caso(db, caso_id)
    valores = _limpio(datos, parcial=True)
    fallas.resolver(db, caso, usuario, valores)
    return next(c for c in manual.casos(db) if c["id"] == caso.id)


"""La bitacora de administracion, para leerla y bajarla (seccion 86).

Se escribe desde el panel de accesos, los catalogos, los puestos y el
tipo de cambio (`accesos.anotar`). Aqui se lee: toda junta, con filtros y
en Excel, quien trae `bitacora.ver`; la de un catalogo, quien abre la
pantalla de Catalogos.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import auth, bitacora_admin
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/bitacora-admin",
                   tags=["Bitacora de administracion"])

LEE = auth.puede("bitacora.ver")

# La pantalla de Catalogos la abre quien lleva uno de sus catalogos o lee
# la bitacora; ensena abajo de cada catalogo lo ultimo que le paso.
# Saber quien movio un numero no es poder moverlo: la pregunta la hace
# quien ve el numero raro.
DE_LA_PANTALLA = ("catalogos.editar", "catalogos.dinero", "bitacora.ver")


def abre_catalogos(usuario: m.Usuario = Depends(auth.usuario_actual),
                   db: Session = Depends(get_db)) -> m.Usuario:
    if any(auth.puede_el_usuario(db, usuario, a) for a in DE_LA_PANTALLA):
        return usuario
    raise HTTPException(403, {
        "mensaje": "No tienes permiso para esta accion",
        "que_hacer": "Lo de los catalogos lo ve quien los lleva: sistema y "
                     "calidad y direccion de operaciones.",
        "actividades": list(DE_LA_PANTALLA),
    })


@router.get("", summary="La bitacora de administracion, filtrada")
def leer(que: str | None = None, quien: int | None = None,
         mes: str | None = None, pagina: int = 1, idioma: str = "es",
         db: Session = Depends(get_db), _=Depends(LEE)):
    """`que`: accesos, puestos, catalogos, tipo_cambio u odoo; sin nada,
    todo menos las lecturas de Odoo de cada hora. `quien`: el usuario que
    lo hizo. `mes`: "2026-09". Cada renglon viene contado en `idioma`."""
    return bitacora_admin.consultar(db, que, quien, mes, pagina, idioma)


@router.get("/excel", summary="La bitacora de administracion, en Excel")
def en_excel(que: str | None = None, quien: int | None = None,
             mes: str | None = None, idioma: str = "es",
             db: Session = Depends(get_db), _=Depends(LEE)):
    """Lo mismo que se filtro en la pantalla, completo, y a su lado lo que
    se escribio tal cual: la accion, el antes y el despues."""
    contenido, nombre = bitacora_admin.excel_de(db, que, quien, mes, idioma)
    return Response(
        content=contenido,
        media_type=("application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/catalogo/{clave}", summary="Lo ultimo que le paso a un catalogo")
def de_un_catalogo(clave: str, idioma: str = "es",
                   db: Session = Depends(get_db),
                   _=Depends(abre_catalogos)):
    if clave not in bitacora_admin.DE_CADA_CATALOGO:
        raise HTTPException(404, f"No hay catalogo '{clave}'")
    return bitacora_admin.de_un_catalogo(db, clave, idioma)

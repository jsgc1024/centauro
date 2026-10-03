# -*- coding: utf-8 -*-
"""Cotizaciones (seccion 114): la cotizacion del eventual que se arma en
Connect, su PDF, sus versiones y, cuando el cliente la autoriza, el
servicio que nace de ella. El motor vive en `cotizacion_cliente.py`; el
PDF, en `cotizacion_pdf.py`.

Las rutas viven en `/cotizaciones/eventual/...`: las de `/cotizaciones/...`
a secas son las de la cotizacion registrada en el servicio (seccion 94),
que siguen igual. La propuesta del implantado (seccion 115) tiene las
suyas al lado, en `routers/propuestas.py`; la lista de la pantalla trae
las dos (`/cotizaciones/lista`).
"""
from datetime import date, time
from decimal import Decimal
from typing import Literal

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Response,
                     UploadFile)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app import cotizacion_cliente as motor
from app import cotizacion_pdf
from app import imagenes
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/cotizaciones", tags=["Cotizaciones"])

VER = auth.puede("cotizaciones.ver")
ARMAR = auth.puede("cotizaciones.armar")


class LlevaIn(BaseModel):
    tipo: Literal["recurso", "vehiculo"]
    id: int
    cantidad: int = Field(1, ge=0, le=motor.MAX_CANTIDAD)


class DiaIn(BaseModel):
    fecha: date
    modalidad_id: int
    hora: time | None = None
    es_foraneo: bool = False
    destino: str | None = Field(None, max_length=motor.LARGO_DESTINO)
    # Vacio: lo que lleva el equipo todos los dias.
    lleva: list[LlevaIn] | None = None


class EquipoIn(BaseModel):
    plaza_id: int | None = None
    lleva: list[LlevaIn] = []
    dias: list[DiaIn] = []


class CotizacionIn(BaseModel):
    cliente_id: int | None = None
    prospecto: str | None = Field(None, max_length=motor.LARGO_NOMBRE)
    pais_id: int | None = None
    solicitante_id: int | None = None
    solicitante_nombre: str | None = Field(None, max_length=motor.LARGO_NOMBRE)
    solicitante_apellidos: str | None = Field(None,
                                              max_length=motor.LARGO_NOMBRE)
    solicitante_correo: str | None = Field(None, max_length=motor.LARGO_NOMBRE)
    solicitante_telefono: str | None = Field(None, max_length=40)
    consultor_id: int | None = None
    tipo_servicio: str | None = Field(None, max_length=motor.LARGO_TIPO)
    introduccion: str | None = Field(None,
                                     max_length=motor.LARGO_INTRODUCCION)
    valida_hasta: date | None = None
    idioma: Literal["es", "en", "pt"] | None = None
    # La moneda que se escogio (seccion 120). Vacia: la de la lista.
    moneda: str | None = Field(None, max_length=3)
    con_iva: bool = True
    gastos: Literal["dentro", "fijo", "comprobar"] = "comprobar"
    monto_gastos: Decimal | None = None
    motivo: str | None = Field(None, max_length=motor.LARGO_MOTIVO)
    equipos: list[EquipoIn] = []


class RechazoIn(BaseModel):
    motivo: str = Field(..., max_length=motor.LARGO_MOTIVO)


class EliminarIn(BaseModel):
    """Por que ya no va (seccion 126). Sin el, se pregunta."""
    motivo: str | None = Field(None, max_length=motor.LARGO_MOTIVO)


class TextosIn(BaseModel):
    razon_social: str | None = Field(None, max_length=200)
    rfc: str | None = Field(None, max_length=30)
    tasa_iva: Decimal | None = None
    textos: dict[str, dict[str, str]] = {}


def _datos(cuerpo: CotizacionIn) -> dict:
    return cuerpo.model_dump()


def _puede_armar(db: Session, usuario: m.Usuario) -> bool:
    return auth.puede_el_usuario(db, usuario, "cotizaciones.armar")


def _de(db: Session, cotizacion_id: int) -> m.Cotizacion:
    return motor.de_folio(db, cotizacion_id)


# ------------------------------------------------------------- la lista

@router.get("/eventual", summary="Las cotizaciones, una por folio")
def lista(vista: str = "todas", q: str | None = None,
          db: Session = Depends(get_db), usuario: m.Usuario = Depends(VER)):
    return {"filas": motor.lista(db, vista, q), "cuentas": motor.cuentas(db),
            "puede_armar": _puede_armar(db, usuario)}


@router.get("/lista",
            summary="Las cotizaciones y las propuestas, una por folio")
def lista_de_las_dos(vista: str = "todas", q: str | None = None,
                     que: Literal["todas", "cotizaciones",
                                  "propuestas"] = "todas",
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(VER)):
    """La pantalla de Cotizaciones (seccion 115): las del eventual y las
    propuestas del implantado juntas, la mas nueva arriba, o solo unas."""
    return {"filas": motor.lista(db, vista, q, que),
            "cuentas": motor.cuentas(db, que),
            "puede_armar": _puede_armar(db, usuario)}


@router.get("/eventual/lista-de-precios",
            summary="La lista con que se cotiza a un cliente o a una empresa")
def lista_de_precios(cliente_id: int | None = None, pais_id: int | None = None,
                     moneda: str | None = None,
                     db: Session = Depends(get_db), _=Depends(ARMAR)):
    return motor.lista_info(db, cliente_id, pais_id, moneda)


@router.post("/eventual/precios",
             summary="Los precios de lo que se esta armando, sin guardar")
def precios(cuerpo: CotizacionIn, db: Session = Depends(get_db),
            _=Depends(ARMAR)):
    return motor.precios(db, _datos(cuerpo))


# ------------------------------------------------------------- armarla

@router.post("/eventual", status_code=201, summary="Una cotizacion nueva")
def crear(cuerpo: CotizacionIn, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(ARMAR)):
    cot, error = motor.guardar(db, usuario, _datos(cuerpo))
    db.commit()
    db.refresh(cot)
    return {**motor.detalle(db, cot, True), "aviso_precios": error}


@router.get("/eventual/{cotizacion_id}", summary="Una cotizacion")
def ver(cotizacion_id: int, db: Session = Depends(get_db),
        usuario: m.Usuario = Depends(VER)):
    cot = _de(db, cotizacion_id)
    return motor.detalle(db, cot, _puede_armar(db, usuario))


@router.put("/eventual/{cotizacion_id}", summary="Guardar el borrador")
def guardar(cotizacion_id: int, cuerpo: CotizacionIn,
            db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(ARMAR)):
    cot = _de(db, cotizacion_id)
    cot, error = motor.guardar(db, usuario, _datos(cuerpo), cot)
    db.commit()
    db.refresh(cot)
    return {**motor.detalle(db, cot, True), "aviso_precios": error}


@router.post("/eventual/{cotizacion_id}/enviar",
             summary="Mandarla: su PDF se guarda tal como sale")
def enviar(cotizacion_id: int, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(ARMAR)):
    cot = motor.enviar(db, usuario, _de(db, cotizacion_id))
    db.commit()
    db.refresh(cot)
    return motor.detalle(db, cot, True)


@router.post("/eventual/{cotizacion_id}/version", status_code=201,
             summary="La version siguiente, como borrador")
def nueva_version(cotizacion_id: int, db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(ARMAR)):
    nueva = motor.nueva_version(db, usuario, _de(db, cotizacion_id))
    db.commit()
    db.refresh(nueva)
    return motor.detalle(db, nueva, True)


@router.post("/eventual/{cotizacion_id}/descartar",
             summary="Descartar este borrador")
def descartar(cotizacion_id: int, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(ARMAR)):
    """El borrador abierto por error (seccion 131, decision 1): la version
    2 o siguiente se borra y la anterior vuelve a ser la ultima; la
    version 1 que nunca se mando se elimina con registro y su folio no se
    vuelve a usar."""
    hecho = motor.descartar(db, usuario, _de(db, cotizacion_id))
    db.commit()
    return hecho


@router.post("/eventual/{cotizacion_id}/rechazar",
             summary="El cliente dijo que no")
def rechazar(cotizacion_id: int, cuerpo: RechazoIn,
             db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(ARMAR)):
    cot = motor.rechazar(db, usuario, _de(db, cotizacion_id), cuerpo.motivo)
    db.commit()
    db.refresh(cot)
    return motor.detalle(db, cot, True)


@router.post("/eventual/{cotizacion_id}/autorizar",
             summary="El cliente la autorizo: nace el servicio")
async def autorizar(cotizacion_id: int,
                    autorizada_por: str = Form(...),
                    autorizada_el: date = Form(...),
                    cliente_id: int | None = Form(None),
                    comprobante: UploadFile | None = File(None),
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(ARMAR)):
    from app import freelance

    cot = _de(db, cotizacion_id)
    adjunto = None
    if comprobante is not None and comprobante.filename:
        contenido = await comprobante.read()
        nombre, tipo = freelance.revisar_archivo(
            comprobante.filename, comprobante.content_type, contenido)
        adjunto = (nombre, tipo, contenido)
    servicio = motor.autorizar(db, usuario, cot, autorizada_por,
                               autorizada_el, cliente_id, adjunto)
    db.commit()
    return _nacido(servicio)


def _nacido(servicio: m.Servicio) -> dict:
    """La respuesta del servicio que nace de la cotizacion. Si nacio sin
    consultor titular --quien firmo perdio su acceso entre mandar y
    autorizar (seccion 129, hallazgo r1-duda5)-- se dice aqui, para que
    la pantalla lo diga y alguien lo asigne, en vez de descubrirlo cuando
    falte en la cartera."""
    return {"servicio_id": servicio.id, "folio": servicio.folio,
            "estatus": servicio.estatus.value,
            "sin_consultor": servicio.consultor_id is None,
            "aviso": (None if servicio.consultor_id else
                      "Nació sin consultor titular: quien firmó la cotización "
                      "ya no lleva servicios. Asígnale uno desde su ficha.")}


# ------------------------------------------------------- su servicio se elimino

@router.post("/eventual/{cotizacion_id}/servicio",
             summary="Volver a crear el servicio que se elimino")
def recrear_servicio(cotizacion_id: int, db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(ARMAR)):
    """La autorizada cuyo servicio se elimino (seccion 126): nace otra vez,
    con lo mismo y la misma autorizacion, con folio nuevo."""
    servicio = motor.recrear_servicio(db, usuario, _de(db, cotizacion_id))
    db.commit()
    return _nacido(servicio)


@router.post("/eventual/{cotizacion_id}/eliminar",
             summary="Eliminar la cotizacion cuyo servicio se elimino")
def eliminar(cotizacion_id: int, cuerpo: EliminarIn,
             db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(ARMAR)):
    """La que ya no va (seccion 126): se van todas sus versiones; queda su
    renglon en las eliminadas, con el motivo, y su folio no se vuelve a
    usar."""
    nombre = motor.eliminar(db, usuario, _de(db, cotizacion_id), cuerpo.motivo)
    db.commit()
    return {"eliminada": nombre}


# ------------------------------------------------------------- archivos

def _archivo(contenido: bytes, tipo: str, nombre: str,
             bajar: bool) -> Response:
    from app.archivo import cabecera_de_archivo
    return Response(content=contenido, media_type=tipo,
                    headers=cabecera_de_archivo(nombre, bajar))


@router.get("/eventual/{cotizacion_id}/pdf",
            summary="El PDF: el que se mando, o como va el borrador")
def ver_pdf(cotizacion_id: int, bajar: bool = False,
            db: Session = Depends(get_db), _=Depends(VER)):
    cot = _de(db, cotizacion_id)
    guardado = motor.archivo(cot, "pdf")
    if guardado is not None:
        return _archivo(guardado.contenido, guardado.tipo, guardado.nombre,
                        bajar)
    if cot.estatus != m.EstatusCotizacion.BORRADOR:
        raise HTTPException(404, "Esta versión no guardó su PDF.")
    return _archivo(cotizacion_pdf.pdf(db, cot), "application/pdf",
                    cotizacion_pdf.nombre_del_archivo(db, cot), bajar)


@router.get("/eventual/{cotizacion_id}/comprobante",
            summary="El comprobante de que el cliente la autorizo")
def ver_comprobante(cotizacion_id: int, db: Session = Depends(get_db),
                    _=Depends(VER)):
    cot = _de(db, cotizacion_id)
    adjunto = motor.archivo(cot, "comprobante")
    if adjunto is None:
        raise HTTPException(404, "No trae comprobante.")
    return _archivo(adjunto.contenido, adjunto.tipo, adjunto.nombre, False)


# ------------------------------------------------------------- la firma

@router.get("/firma", summary="Tu firma para las cotizaciones")
def mi_firma(db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(ARMAR)):
    imagen = motor.firma_de(db, usuario.persona_id)
    return {"tiene": imagen is not None, "imagen": imagen}


@router.put("/firma", summary="Subir o cambiar tu firma")
async def poner_mi_firma(archivo: UploadFile = File(...),
                         db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(ARMAR)):
    motor.poner_firma(db, usuario, await imagenes.leer(archivo))
    db.commit()
    return {"tiene": True}


@router.delete("/firma", summary="Quitar tu firma")
def quitar_mi_firma(db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(ARMAR)):
    motor.quitar_firma(db, usuario)
    db.commit()
    return {"tiene": False}


# ------------------------------------------------------------- Catalogos

def _lee_textos(usuario: m.Usuario = Depends(auth.usuario_actual),
                db: Session = Depends(get_db)) -> m.Usuario:
    """Los lee quien cotiza y quien lleva Catalogos."""
    for actividad in ("cotizaciones.ver", "catalogos.dinero",
                      "catalogos.editar", "bitacora.ver"):
        if auth.puede_el_usuario(db, usuario, actividad):
            return usuario
    raise HTTPException(403, {
        "mensaje": "No tienes permiso para esta accion",
        "que_hacer": "Los textos de la cotización los ve quien cotiza o "
                     "lleva Catálogos.",
        "actividad": "cotizaciones.ver"})


@router.get("/textos", summary="Los datos y textos de la cotizacion de un pais")
def textos(pais_id: int, db: Session = Depends(get_db),
           _=Depends(_lee_textos)):
    if db.get(m.Pais, pais_id) is None:
        raise HTTPException(404, f"No existe el país {pais_id}")
    return motor.textos_de(db, pais_id)


@router.put("/textos/{pais_id}",
            summary="Cambiar los datos y textos de la cotizacion de un pais")
def guardar_textos(pais_id: int, cuerpo: TextosIn,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(
                       auth.puede("catalogos.dinero"))):
    salida = motor.guardar_textos(db, usuario, pais_id, cuerpo.model_dump())
    db.commit()
    return salida

# -*- coding: utf-8 -*-
"""La propuesta del implantado (seccion 115): se arma en Cotizaciones,
junto a la cotizacion del eventual, sale su PDF, direccion de operaciones
autoriza su precio especial y, cuando el cliente la autoriza, nace el
implantado. El motor vive en `propuesta.py`; el PDF, en
`propuesta_pdf.py`.

Las rutas viven en `/cotizaciones/propuesta/...`, al lado de las de la
cotizacion del eventual (`/cotizaciones/eventual/...`), con las mismas
dos puertas: la ve quien ve cotizaciones y la arma quien las arma. El
precio especial lo autoriza quien trae `propuestas.precio_especial`.
"""
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app import cotizacion_cliente as cc
from app import models as m
from app import propuesta as motor
from app import propuesta_pdf
from app.db import get_db
from app.routers.cotizaciones import _archivo, _lee_textos

router = APIRouter(prefix="/cotizaciones/propuesta", tags=["Propuestas"])

VER = auth.puede("cotizaciones.ver")
ARMAR = auth.puede("cotizaciones.armar")
ESPECIAL = auth.puede(motor.ESPECIAL)


class PosicionIn(BaseModel):
    tipo: Literal["recurso", "vehiculo", "paquete"]
    perfil_id: int | None = None
    categoria_id: int | None = None
    cantidad: int = Field(1, ge=0, le=motor.MAX_CANTIDAD)
    # Vacio: el de la lista. Escrito, el mensual que se pacto.
    precio_mes: Decimal | None = Field(None, ge=0)
    # Como lo lee el cliente --«Conductor de seguridad bilingüe»--. Vacio,
    # el producto de Odoo o el nombre del rol o de la unidad.
    descripcion: str | None = Field(None, max_length=motor.LARGO_DESCRIPCION)


class PropuestaIn(BaseModel):
    cliente_id: int | None = None
    prospecto: str | None = Field(None, max_length=cc.LARGO_NOMBRE)
    pais_id: int | None = None
    solicitante_id: int | None = None
    solicitante_nombre: str | None = Field(None, max_length=cc.LARGO_NOMBRE)
    solicitante_apellidos: str | None = Field(None, max_length=cc.LARGO_NOMBRE)
    solicitante_correo: str | None = Field(None, max_length=cc.LARGO_NOMBRE)
    solicitante_telefono: str | None = Field(None, max_length=40)
    consultor_id: int | None = None
    plaza_id: int | None = None
    tipo_servicio: str | None = Field(None, max_length=cc.LARGO_TIPO)
    introduccion: str | None = Field(None, max_length=cc.LARGO_INTRODUCCION)
    valida_hasta: date | None = None
    idioma: Literal["es", "en", "pt"] | None = None
    con_iva: bool = True
    inicio: date | None = None
    dias_servicio: Literal["lunes_viernes", "lunes_sabado", "todos"] = \
        "lunes_viernes"
    viaticos: Literal["aparte", "incluidos"] = "aparte"
    horas_jornada: Decimal | None = None
    hora_presentacion: str | None = Field(None, max_length=8)
    alcance: str | None = Field(None, max_length=motor.LARGO_ALCANCE)
    precio_hora_extra: Decimal | None = Field(None, ge=0)
    especial_motivo: str | None = Field(None, max_length=motor.LARGO_NOTA)
    motivo: str | None = Field(None, max_length=cc.LARGO_MOTIVO)
    posiciones: list[PosicionIn] = Field([], max_length=motor.MAX_POSICIONES)


class DecisionIn(BaseModel):
    autoriza: bool
    nota: str | None = Field(None, max_length=motor.LARGO_NOTA)
    # La de los precios que se vieron: si cambiaron, no se autoriza.
    huella: str | None = Field(None, max_length=64)


class RechazoIn(BaseModel):
    motivo: str = Field(..., max_length=cc.LARGO_MOTIVO)


class TextosIn(BaseModel):
    textos: dict[str, dict[str, str]] = {}
    alcances: dict[str, dict[str, str]] = {}


def _de(db: Session, cotizacion_id: int) -> m.Cotizacion:
    return cc.de_folio(db, cotizacion_id, motor.CLASE)


def _con_aviso(db: Session, cot: m.Cotizacion, usuario: m.Usuario,
               calc: dict) -> dict:
    """El detalle, con lo que se guardo sin precio: se guarda igual y la
    pantalla dice que falta."""
    return {**motor.detalle(db, cot, usuario),
            "aviso_precios": (", ".join(calc["faltan"])
                              if calc["faltan"] else None)}


# ------------------------------------------------------------- armarla

@router.get("/lista-de-precios",
            summary="La lista de implantados de un cliente, para la propuesta")
def lista_de_precios(cliente_id: int | None = None, pais_id: int | None = None,
                     db: Session = Depends(get_db), _=Depends(ARMAR)):
    return motor.lista_info(db, cliente_id, pais_id)


@router.post("/precios",
             summary="Los precios de la propuesta que se arma, sin guardar")
def precios(cuerpo: PropuestaIn, db: Session = Depends(get_db),
            _=Depends(ARMAR)):
    return motor.precios(db, cuerpo.model_dump())


@router.get("/textos", summary="Los textos de la propuesta de un pais")
def textos(pais_id: int, db: Session = Depends(get_db),
           _=Depends(_lee_textos)):
    if db.get(m.Pais, pais_id) is None:
        raise HTTPException(404, f"No existe el país {pais_id}")
    return motor.textos_de(db, pais_id)


@router.put("/textos/{pais_id}",
            summary="Cambiar los textos de la propuesta de un pais")
def guardar_textos(pais_id: int, cuerpo: TextosIn,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(
                       auth.puede("catalogos.dinero"))):
    salida = motor.guardar_textos(db, usuario, pais_id, cuerpo.model_dump())
    db.commit()
    return salida


@router.post("", status_code=201, summary="Una propuesta nueva")
def crear(cuerpo: PropuestaIn, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(ARMAR)):
    cot, calc = motor.guardar(db, usuario, cuerpo.model_dump())
    db.commit()
    db.refresh(cot)
    return _con_aviso(db, cot, usuario, calc)


@router.get("/{cotizacion_id}", summary="Una propuesta")
def ver(cotizacion_id: int, db: Session = Depends(get_db),
        usuario: m.Usuario = Depends(VER)):
    return motor.detalle(db, _de(db, cotizacion_id), usuario)


@router.put("/{cotizacion_id}", summary="Guardar el borrador")
def guardar(cotizacion_id: int, cuerpo: PropuestaIn,
            db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(ARMAR)):
    cot, calc = motor.guardar(db, usuario, cuerpo.model_dump(),
                              _de(db, cotizacion_id))
    db.commit()
    db.refresh(cot)
    return _con_aviso(db, cot, usuario, calc)


# ------------------------------------------------------------- el precio especial

@router.post("/{cotizacion_id}/especial",
             summary="Pedir el visto bueno del precio especial")
def pedir_especial(cotizacion_id: int, db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(ARMAR)):
    cot = motor.pedir_especial(db, usuario, _de(db, cotizacion_id))
    db.commit()
    db.refresh(cot)
    return motor.detalle(db, cot, usuario)


@router.post("/{cotizacion_id}/especial/decidir",
             summary="Autorizar o no el precio especial")
def decidir_especial(cotizacion_id: int, cuerpo: DecisionIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(ESPECIAL)):
    cot = motor.decidir_especial(db, usuario, _de(db, cotizacion_id),
                                 cuerpo.autoriza, cuerpo.nota, cuerpo.huella)
    db.commit()
    db.refresh(cot)
    return motor.detalle(db, cot, usuario)


# ------------------------------------------------------------- mandarla y lo que sigue

@router.post("/{cotizacion_id}/enviar",
             summary="Mandarla: su PDF se guarda tal como sale")
def enviar(cotizacion_id: int, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(ARMAR)):
    cot = motor.enviar(db, usuario, _de(db, cotizacion_id))
    db.commit()
    db.refresh(cot)
    return motor.detalle(db, cot, usuario)


@router.post("/{cotizacion_id}/version", status_code=201,
             summary="La version siguiente, como borrador")
def nueva_version(cotizacion_id: int, db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(ARMAR)):
    nueva = motor.nueva_version(db, usuario, _de(db, cotizacion_id))
    db.commit()
    db.refresh(nueva)
    return motor.detalle(db, nueva, usuario)


@router.post("/{cotizacion_id}/rechazar", summary="El cliente dijo que no")
def rechazar(cotizacion_id: int, cuerpo: RechazoIn,
             db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(ARMAR)):
    cot = motor.rechazar(db, usuario, _de(db, cotizacion_id), cuerpo.motivo)
    db.commit()
    db.refresh(cot)
    return motor.detalle(db, cot, usuario)


@router.post("/{cotizacion_id}/autorizar",
             summary="El cliente la autorizo: nace el implantado")
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
    return {"servicio_id": servicio.id, "folio": servicio.folio,
            "estatus": servicio.estatus.value}


# ------------------------------------------------------------- archivos

@router.get("/{cotizacion_id}/pdf",
            summary="El PDF: el que se mando, o como va el borrador")
def ver_pdf(cotizacion_id: int, bajar: bool = False,
            db: Session = Depends(get_db), _=Depends(VER)):
    cot = _de(db, cotizacion_id)
    guardado = cc.archivo(cot, "pdf")
    if guardado is not None:
        return _archivo(guardado.contenido, guardado.tipo, guardado.nombre,
                        bajar)
    if cot.estatus != m.EstatusCotizacion.BORRADOR:
        raise HTTPException(404, "Esta versión no guardó su PDF.")
    return _archivo(propuesta_pdf.pdf(db, cot), "application/pdf",
                    propuesta_pdf.nombre_del_archivo(db, cot), bajar)


@router.get("/{cotizacion_id}/comprobante",
            summary="El comprobante de que el cliente la autorizo")
def ver_comprobante(cotizacion_id: int, db: Session = Depends(get_db),
                    _=Depends(VER)) -> Response:
    cot = _de(db, cotizacion_id)
    adjunto = cc.archivo(cot, "comprobante")
    if adjunto is None:
        raise HTTPException(404, "No trae comprobante.")
    return _archivo(adjunto.contenido, adjunto.tipo, adjunto.nombre, False)

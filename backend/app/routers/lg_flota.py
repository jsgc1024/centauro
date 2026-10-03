"""Centauro Logistica: la flota (seccion 151).

La pantalla Operaciones LG -> Flota LG. La abre quien trae `lg.flota.ver`
--la gerencia de Logistica, quien lleva la flota, sistema y calidad--; la
edita quien trae `lg.flota.editar` --quien lleva la flota--. «En viaje» a
mano lo marca tambien quien trae `lg.en_viaje.marcar`, mientras los viajes
sigan en Tango. Las reglas viven en `app/lg_flota.py`; quien puede salir,
en `app/lg_disponibilidad.py`.
"""
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import archivo as archivo_motor
from app import auth, lg_carga, lg_disponibilidad
from app import lg_flota as fl
from app import models as m
from app import odoo_lg
from app.db import get_db

router = APIRouter(prefix="/lg/flota", tags=["Logistica: flota"])

VE = auth.puede("lg.flota.ver")
EDITA = auth.puede("lg.flota.editar")
OBJETOS = ("lg_unidades", "lg_plan", "lg_carga")


class EstadoIn(BaseModel):
    estado: str = Field(..., max_length=20)
    motivo: str | None = Field(None, max_length=300)
    hasta: date | None = None


class OdometroIn(BaseModel):
    km: int | float | str
    fecha: date | None = None
    motivo: str | None = Field(None, max_length=300)


class LlantaIn(BaseModel):
    posicion: str = Field(..., max_length=8)
    km: int | float | str
    fecha: date | None = None
    detalle: str | None = Field(None, max_length=120)
    costo: float | str | None = None


class MotivoIn(BaseModel):
    motivo: str = Field(..., max_length=300)


class PlanIn(BaseModel):
    clase: str = Field("unidad", max_length=12)
    tipo_id: int | None = None
    nombre: str | None = Field(None, max_length=80)
    cada_km: int | float | str | None = None
    costo_aprox: float | str | None = None
    orden: int | None = None
    activo: bool | None = None


class OdooIn(BaseModel):
    aplicar: bool = False


def _puede(db: Session, usuario: m.Usuario) -> dict:
    return {"editar": auth.puede_el_usuario(db, usuario, "lg.flota.editar"),
            "en_viaje": auth.puede_el_usuario(db, usuario, "lg.en_viaje.marcar")}


def _tipos(db: Session) -> list[dict]:
    return [{"id": t.id, "nombre": t.nombre} for t in db.query(m.LgTipoUnidad)
            .filter(m.LgTipoUnidad.activo.is_(True))
            .order_by(m.LgTipoUnidad.orden, m.LgTipoUnidad.id)]


def _patios(db: Session) -> list[dict]:
    return [{"id": p.id, "nombre": p.nombre} for p in db.query(m.LgPatio)
            .filter(m.LgPatio.activo.is_(True)).order_by(m.LgPatio.nombre)]


def _detalle(db: Session, usuario: m.Usuario, unidad_id: int) -> dict:
    """El detalle de la unidad con lo que la pantalla necesita para sus
    formas. Cada cambio contesta con esto mismo: la pantalla se repinta
    con lo que quedo guardado, sin otra vuelta."""
    return {**fl.detalle(db, unidad_id), "puede": _puede(db, usuario),
            "tipos": _tipos(db), "patios": _patios(db)}


@router.get("", summary="La flota de Logistica, con quien puede salir hoy")
def lista(db: Session = Depends(get_db), usuario: m.Usuario = Depends(VE)):
    return {**fl.lista(db), "puede": _puede(db, usuario), "tipos": _tipos(db),
            "patios": _patios(db), "odoo": odoo_lg.ultima(db, odoo_lg.TIPO_FLOTA)}


@router.get("/unidades/{unidad_id}", summary="El detalle de una unidad")
def detalle(unidad_id: int, db: Session = Depends(get_db), usuario: m.Usuario = Depends(VE)):
    return _detalle(db, usuario, unidad_id)


@router.patch("/unidades/{unidad_id}", summary="Cambiar los datos de una unidad")
def editar(unidad_id: int, datos: dict, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(EDITA)):
    permitidos = {"numero_economico", "tipo_id", "rendimiento_ref", "patio_id",
                  *fl.CAMPOS_COSTO}
    fl.editar(db, usuario, fl.unidad_o_404(db, unidad_id),
              {k: v for k, v in (datos or {}).items() if k in permitidos})
    db.commit()
    return _detalle(db, usuario, unidad_id)


@router.post("/unidades/{unidad_id}/estado", summary="Cambiar el estado de una unidad")
def estado(unidad_id: int, entrada: EstadoIn, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(VE)):
    puede = _puede(db, usuario)
    solo_viaje = entrada.estado in ("en_viaje", "disponible") and puede["en_viaje"]
    if not (puede["editar"] or solo_viaje):
        raise HTTPException(403, "No tienes permiso para cambiar el estado de las unidades.")
    unidad = fl.unidad_o_404(db, unidad_id)
    if not puede["editar"] and unidad.estado in fl.CON_MOTIVO:
        raise HTTPException(403, "Una unidad en taller o fuera de servicio la libera "
                                 "quien lleva la flota.")
    fl.cambiar_estado(db, usuario, unidad, entrada.estado, entrada.motivo, entrada.hasta)
    db.commit()
    return _detalle(db, usuario, unidad_id)


@router.post("/unidades/{unidad_id}/odometro", status_code=201, summary="Capturar el odometro")
def odometro(unidad_id: int, entrada: OdometroIn, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(EDITA)):
    fl.capturar_odometro(db, usuario, fl.unidad_o_404(db, unidad_id), entrada.km,
                         entrada.fecha, entrada.motivo)
    db.commit()
    return _detalle(db, usuario, unidad_id)


@router.post("/unidades/{unidad_id}/documentos", status_code=201,
             summary="Un documento del expediente, con su archivo")
def documento(unidad_id: int, tipo: str = Form(...), folio: str | None = Form(None),
              detalle: str | None = Form(None), vence_en: date | None = Form(None),
              archivo: UploadFile | None = File(None), db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(EDITA)):
    unidad = fl.unidad_o_404(db, unidad_id)
    fila = None
    nombre, tipo_archivo, contenido = _leer(archivo)
    if contenido is not None:
        fila = fl.guardar_archivo(db, usuario, nombre, tipo_archivo, contenido)
    fl.capturar_documento(db, usuario, tipo, unidad=unidad, folio=folio, detalle=detalle,
                          vence_en=vence_en, archivo=fila)
    db.commit()
    return _detalle(db, usuario, unidad_id)


@router.post("/unidades/{unidad_id}/servicios", status_code=201,
             summary="Registrar un servicio hecho, con su factura")
def servicio(unidad_id: int, plan_id: int | None = Form(None), nombre: str | None = Form(None),
             fecha: date = Form(...), km: str | None = Form(None), costo: str = Form(...),
             taller: str | None = Form(None), factura: str | None = Form(None),
             archivo: UploadFile | None = File(None), db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(EDITA)):
    unidad = fl.unidad_o_404(db, unidad_id)
    fila = None
    nombre_a, tipo_a, contenido = _leer(archivo)
    if contenido is not None:
        fila = fl.guardar_archivo(db, usuario, nombre_a, tipo_a, contenido)
    fl.registrar_servicio(db, usuario, unidad, {
        "plan_id": plan_id, "nombre": nombre, "fecha": fecha, "km": km, "costo": costo,
        "taller": taller, "factura": factura}, fila)
    db.commit()
    return _detalle(db, usuario, unidad_id)


@router.post("/servicios/{servicio_id}/anular", summary="Anular un servicio mal capturado")
def anular(servicio_id: int, entrada: MotivoIn, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(EDITA)):
    servicio = fl.anular_servicio(db, usuario, servicio_id, entrada.motivo)
    db.commit()
    return _detalle(db, usuario, servicio.unidad_id)


@router.post("/unidades/{unidad_id}/llantas", status_code=201,
             summary="Una llanta nueva en una posicion")
def llanta(unidad_id: int, entrada: LlantaIn, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(EDITA)):
    fl.cambiar_llanta(db, usuario, fl.unidad_o_404(db, unidad_id), entrada.posicion,
                      entrada.km, entrada.fecha, entrada.detalle, entrada.costo)
    db.commit()
    return _detalle(db, usuario, unidad_id)


@router.post("/unidades/{unidad_id}/costo", summary="Recalcular el costo por dia desde hoy")
def recalcular(unidad_id: int, entrada: MotivoIn, db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(EDITA)):
    fl.recalcular(db, usuario, fl.unidad_o_404(db, unidad_id), entrada.motivo)
    db.commit()
    return _detalle(db, usuario, unidad_id)


@router.get("/unidades/{unidad_id}/disponibilidad",
            summary="Si la unidad puede salir a un viaje de esas fechas y esos km")
def disponibilidad(unidad_id: int, desde: date | None = None, hasta: date | None = None,
                   km: int | None = None, db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(VE)):
    return lg_disponibilidad.unidad(db, unidad_id, desde, hasta, km)


@router.get("/archivos/{archivo_id}", summary="El archivo de un documento o una factura")
def ver_archivo(archivo_id: int, bajar: bool = False, db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(auth.usuario_actual)):
    if not (auth.puede_el_usuario(db, usuario, "lg.flota.ver")
            or auth.puede_el_usuario(db, usuario, "lg.jornada.ver")):
        raise HTTPException(403, "No tienes permiso para ver este archivo.")
    fila = db.get(m.LgArchivo, archivo_id)
    if not fila:
        raise HTTPException(404, "No existe ese archivo")
    return Response(fl.leer_archivo(fila), media_type=fila.tipo,
                    headers=archivo_motor.cabecera_de_archivo(fila.nombre, bajar))


@router.get("/plan", summary="El plan preventivo de cada tipo y de las cajas")
def plan(db: Session = Depends(get_db), usuario: m.Usuario = Depends(VE)):
    return {**fl.planes(db), "puede": _puede(db, usuario)}


@router.post("/plan", status_code=201, summary="Un servicio nuevo en el plan")
def alta_plan(entrada: PlanIn, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(EDITA)):
    fl.alta_plan(db, usuario, entrada.model_dump())
    db.commit()
    return fl.planes(db)


@router.patch("/plan/{plan_id}", summary="Cambiar o quitar un servicio del plan")
def cambiar_plan(plan_id: int, entrada: PlanIn, db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(EDITA)):
    fl.cambiar_plan(db, usuario, plan_id, entrada.model_dump(exclude_unset=True))
    db.commit()
    return fl.planes(db)


@router.patch("/tipos/{tipo_id}", summary="Las llantas de un tipo de unidad")
def tipo(tipo_id: int, datos: dict, db: Session = Depends(get_db),
         usuario: m.Usuario = Depends(EDITA)):
    fl.tipo_de_flota(db, usuario, tipo_id, {k: v for k, v in (datos or {}).items()
                                            if k in ("llantas", "vida_llanta_km")})
    db.commit()
    return fl.planes(db)


@router.post("/carga", summary="La carga inicial del Excel: revisar y, si todo esta bien, cargar")
def carga(archivo: UploadFile = File(...), aplicar: bool = Form(False),
          db: Session = Depends(get_db), usuario: m.Usuario = Depends(EDITA)):
    _, _, contenido = _leer(archivo)
    return lg_carga.cargar(db, usuario, contenido or b"", aplicar)


@router.get("/odoo", summary="La ultima lectura de las unidades de Odoo")
def odoo_ultima(db: Session = Depends(get_db), usuario: m.Usuario = Depends(VE)):
    return {"ultima": odoo_lg.ultima(db, odoo_lg.TIPO_FLOTA)}


@router.post("/odoo", summary="Leer las unidades de Odoo: ensayo o aplicar")
def odoo_leer(entrada: OdooIn, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(EDITA)):
    from app import odoo_api
    if not odoo_api.hay_conexion():
        raise HTTPException(409, {"mensaje": "Odoo no está conectado en este servidor.",
                                  "que_hacer": "Sistema y calidad revisa la conexión en "
                                               "la pantalla de Odoo."})
    try:
        return odoo_lg.sincronizar_flota(db, odoo_api.cliente(), ensayo=not entrada.aplicar,
                                         quien=usuario)
    except odoo_api.NoResponde as error:
        raise HTTPException(502, f"Odoo no contestó: {error}")


@router.get("/bitacora", summary="Lo que le ha pasado a la flota")
def bitacora(pagina: int = 1, idioma: str = "es", unidad_id: int | None = None,
             db: Session = Depends(get_db), usuario: m.Usuario = Depends(VE)):
    objetos = ("lg_unidades",) if unidad_id else OBJETOS
    return fl.bitacora(db, objetos, pagina, idioma, unidad_id)


def _leer(archivo: UploadFile | None) -> tuple:
    """(nombre, tipo, bytes) del archivo subido, sin pasar de 10 MB."""
    if archivo is None or not archivo.filename:
        return None, None, None
    contenido = archivo.file.read(10 * 1024 * 1024 + 1)
    if len(contenido) > 10 * 1024 * 1024:
        raise HTTPException(400, f"«{archivo.filename}» pasa de 10 MB.")
    return archivo.filename, archivo.content_type, contenido

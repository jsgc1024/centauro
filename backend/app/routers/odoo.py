"""Sincronizacion con Odoo: empleados y flota.

Odoo es la fuente de verdad del nombre, telefono y fotografia. El sistema
no los captura: los recibe por aqui y los guarda para que el task sheet
los muestre sin depender de que Odoo responda en ese momento.

El personal de seguridad ya no espera a que se lo manden: Centauro lo lee
de Odoo (seccion 51). `/personal/ensayo` dice que haria sin guardar nada
y `/personal/sincronizar` lo guarda; despues lo sigue leyendo solo, cada
hora. `POST /personal` se queda para quien todavia lo mande.

La flota y el taller, igual (seccion 52): `/flota/ensayo` y
`/flota/sincronizar`.

La pantalla de Odoo de la consola (seccion 64) usa estas mismas rutas y
`/estado`, que dice si hay llave y como van las lecturas: en produccion
no hay terminal, y la primera lectura se hace desde ahi.
"""
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import odoo, odoo_api, odoo_flota, odoo_personal, schemas as s
from app.auth import requiere
from app.config import settings
from app.db import get_db

router = APIRouter(prefix="/odoo", tags=["Odoo"])


@router.post("/personal", summary="Recibir empleados desde Odoo")
def personal(empleados: list[s.EmpleadoOdoo],
             db: Session = Depends(get_db),
             _=Depends(requiere(m.Rol.ADMIN))):
    return odoo.sincronizar_personal(
        db, [e.model_dump(exclude_none=True) for e in empleados])


@router.post("/flota", summary="Recibir la flota desde Odoo")
def flota(vehiculos: list[s.VehiculoOdoo],
          db: Session = Depends(get_db),
          _=Depends(requiere(m.Rol.ADMIN))):
    return odoo.sincronizar_flota(
        db, [v.model_dump(exclude_none=True) for v in vehiculos])


@router.post("/capacitaciones",
             summary="Recibir los cursos y certificados desde Odoo")
def capacitaciones(filas: list[s.CapacitacionOdoo],
                   db: Session = Depends(get_db),
                   _=Depends(requiere(m.Rol.ADMIN))):
    """Los cursos del personal viven en Odoo y entran por aqui.

    De este padron sale si alguien esta al corriente --el criterio del
    bono y la dimension de la calificacion-- y de aqui salen los avisos
    de certificado por vencer. Mientras no llegue la primera carga, ese
    criterio simplemente no aplica: nadie reprueba por un padron vacio.
    """
    return odoo.sincronizar_capacitaciones(
        db, [f.model_dump(exclude_none=False) for f in filas])


@router.post("/taller", summary="Recibir del taller las unidades fuera")
def taller(entradas: list[s.TallerOdoo],
           db: Session = Depends(get_db),
           _=Depends(requiere(m.Rol.ADMIN))):
    """El mantenimiento de la flota vive en Odoo. Aqui solo se recibe el
    rango en que cada unidad esta fuera, para dejar de ofrecerla."""
    return odoo.sincronizar_taller(
        db, [e.model_dump(exclude_none=True) for e in entradas])


# ------------------------------------------------ el personal, leido de Odoo

def _conexion():
    """El cliente de Odoo, o un 503 que dice que falta."""
    try:
        return odoo_api.cliente()
    except odoo_api.SinConexion:
        raise HTTPException(503, {
            "mensaje": "Odoo no esta conectado en este servidor.",
            "que_hacer": "Falta ODOO_BASE y ODOO_API_KEY en el .env del "
                         "servidor.",
        })


def _leer(modulo, db: Session, ensayo: bool, quien: m.Usuario) -> dict:
    """El personal o la flota: la misma puerta, el mismo 503 y el
    mismo 502."""
    cliente = _conexion()
    try:
        return modulo.sincronizar(db, cliente, ensayo=ensayo,
                                  quien=None if ensayo else quien)
    except odoo_api.NoResponde as error:
        raise HTTPException(502, {
            "mensaje": str(error),
            "que_hacer": "Si Odoo rechazo la llave, hay que crear una nueva "
                         "en Odoo y ponerla en el .env del servidor.",
        })


# Las lecturas que salen en la pantalla de Odoo: las de cada hora sin
# novedades tambien dejan su renglon, asi que con diez se ve el dia.
LECTURAS_EN_PANTALLA = 10


def _renglon(fila, nombres: dict) -> dict | None:
    if fila is None:
        return None
    return {"id": fila.id, "tipo": fila.tipo,
            "hecha_en": fila.hecha_en.isoformat() if fila.hecha_en else None,
            "automatica": fila.automatica,
            "hecha_por": nombres.get(fila.hecha_por_id),
            "leidos": fila.leidos, "altas": fila.altas,
            "cambios": fila.cambios, "bajas": fila.bajas,
            "pendientes": fila.pendientes}


@router.get("/estado",
            summary="Si Odoo esta conectado y como van sus lecturas")
def estado(db: Session = Depends(get_db),
           _=Depends(requiere(m.Rol.ADMIN))):
    """Lo que la pantalla de Odoo dice antes de leer nada: si este
    servidor tiene la llave, si ya se hizo la primera lectura a mano de
    cada cosa --sin ella la de cada hora no arranca-- y las ultimas
    lecturas, a mano y solas. No le pregunta nada a Odoo."""
    L = m.SincronizacionOdoo
    reciente = (L.hecha_en.desc(), L.id.desc())
    ultimas = db.query(L).order_by(*reciente).limit(LECTURAS_EN_PANTALLA).all()
    por_tipo = {}
    for tipo in (odoo_personal.TIPO, odoo_flota.TIPO):
        a_mano = (db.query(L).filter_by(tipo=tipo, automatica=False)
                  .order_by(*reciente).first())
        sola = (db.query(L).filter_by(tipo=tipo, automatica=True)
                .order_by(*reciente).first())
        por_tipo[tipo] = (a_mano, sola)
    quienes = {f.hecha_por_id for f in ultimas} | {
        f.hecha_por_id for par in por_tipo.values() for f in par if f}
    quienes.discard(None)
    nombres = {p.id: p.nombre for p in
               db.query(m.Persona).filter(m.Persona.id.in_(quienes)).all()
               } if quienes else {}
    sitio = urlparse(settings.odoo_base or "").hostname or None
    return {
        "conectado": odoo_api.hay_conexion(),
        "sitio": sitio,
        **{tipo: {"primera_hecha": a_mano is not None,
                  "ultima_a_mano": _renglon(a_mano, nombres),
                  "ultima_sola": _renglon(sola, nombres)}
           for tipo, (a_mano, sola) in por_tipo.items()},
        "lecturas": [_renglon(f, nombres) for f in ultimas],
    }


@router.get("/personal/ensayo",
            summary="Que cambiaria al leer el personal de Odoo, sin guardar")
def personal_ensayo(db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(requiere(m.Rol.ADMIN))):
    """Lee Odoo y dice que haria: altas, cambios, bajas y pendientes.
    No guarda nada, ni aqui ni en Odoo."""
    return _leer(odoo_personal, db, True, usuario)


@router.post("/personal/sincronizar",
             summary="Leer el personal de Odoo y guardarlo")
def personal_sincronizar(db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(requiere(m.Rol.ADMIN))):
    """Lo mismo que el ensayo, guardado. La primera vez se hace a mano,
    despues de ver el ensayo; de ahi en adelante se lee solo cada hora."""
    return _leer(odoo_personal, db, False, usuario)


# ------------------------------------------------ la flota, leida de Odoo

@router.get("/flota/ensayo",
            summary="Que cambiaria al leer la flota y el taller, sin guardar")
def flota_ensayo(db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(requiere(m.Rol.ADMIN))):
    """Lee Odoo y dice que haria con las unidades de Proteccion
    Ejecutiva y con el taller. No guarda nada, ni aqui ni en Odoo."""
    return _leer(odoo_flota, db, True, usuario)


@router.post("/flota/sincronizar",
             summary="Leer la flota y el taller de Odoo y guardarlos")
def flota_sincronizar(db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(requiere(m.Rol.ADMIN))):
    """Lo mismo que el ensayo, guardado. La primera vez se hace a mano;
    de ahi en adelante se lee sola cada hora."""
    return _leer(odoo_flota, db, False, usuario)

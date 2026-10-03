"""Lo que arman las pruebas de Logistica, bloque 2 (seccion 151): los
catalogos de arranque, las cuentas que hacen de Karla, de la Central y de
sistema y calidad, y las unidades y los operadores como los dejaria la
lectura de Odoo.

Los catalogos de Logistica no se vacian con el movimiento: aqui se
vuelven a sembrar antes de cada prueba, como en las de la seccion 150, y
las cuentas que cambian de rol se dejan como estaban.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import lg_catalogos, lg_flota
from app import models as m

KARLA = "finanzas2@centauro.lat"      # la gerencia de Logistica
CALIDAD = "central2@centauro.lat"     # sistema y calidad
CENTRAL = "central@centauro.lat"      # la Central, con su rol
ADMIN = "admin@centauro.lat"
CUENTAS = (KARLA, CALIDAD, CENTRAL)
# Base Cuautitlan con su punto, como lo pondria sistema y calidad.
PATIO = (Decimal("19.6720000"), Decimal("-99.1790000"))
DENTRO = (Decimal("19.6730000"), Decimal("-99.1790000"))     # a ~111 m
FUERA = (Decimal("19.6900000"), Decimal("-99.1790000"))      # a ~2 km
# El costo de un 1.5 ton del boceto de Flota: 900 pesos al dia.
UNIDAD_15 = {"rendimiento": 7, "compra": 547500, "anios": 4, "seguro": 34675,
             "mantenimiento": 94900, "llantas": 40150, "gps": 21900}


@pytest.fixture(autouse=True)
def logistica(base_de_pruebas):
    """Los cuatro tipos con sus llantas y Base Cuautitlan con su punto."""
    with base_de_pruebas.begin() as con:
        con.execute(text("TRUNCATE lg_valor, lg_patio, lg_tipo_unidad "
                         "RESTART IDENTITY CASCADE"))
        cuentas = con.execute(text(
            "SELECT id, rol, categoria_id FROM usuario WHERE correo = ANY(:c)"),
            {"c": list(CUENTAS)}).all()
    with Session(base_de_pruebas) as db:
        lg_catalogos.sembrar(db)
        lg_flota.sembrar(db)
        patio = db.query(m.LgPatio).one()
        patio.lat, patio.lon = PATIO
        db.commit()
    yield
    with base_de_pruebas.begin() as con:
        for u in cuentas:
            con.execute(text("UPDATE usuario SET rol = :rol, categoria_id = :c "
                             "WHERE id = :id"),
                        {"rol": u.rol, "c": u.categoria_id, "id": u.id})


@pytest.fixture
def db(base_de_pruebas):
    with Session(base_de_pruebas) as sesion_db:
        yield sesion_db


def entrar(cliente, correo):
    r = cliente.post("/auth/token",
                     data={"username": correo, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def con_rol(base_de_pruebas, correo, rol):
    with base_de_pruebas.begin() as con:
        con.execute(text("UPDATE usuario SET rol = :r, categoria_id = NULL "
                         "WHERE correo = :c"), {"r": rol, "c": correo})


@pytest.fixture
def karla(cliente, base_de_pruebas):
    """La gerencia de Logistica, con su rol: ve todo, no edita la flota."""
    con_rol(base_de_pruebas, KARLA, "LOGISTICA")
    return entrar(cliente, KARLA)


@pytest.fixture
def calidad(cliente, base_de_pruebas):
    con_rol(base_de_pruebas, CALIDAD, "SISTEMA_CALIDAD")
    return entrar(cliente, CALIDAD)


@pytest.fixture
def central(cliente):
    return entrar(cliente, CENTRAL)


@pytest.fixture
def admin(cliente):
    return entrar(cliente, ADMIN)


def hoy() -> date:
    return lg_flota.hoy()


def usuario(db, correo=ADMIN) -> m.Usuario:
    return db.query(m.Usuario).filter_by(correo=correo).one()


def tipo_id(db, nombre="1.5 ton") -> int:
    return db.query(m.LgTipoUnidad).filter_by(nombre=nombre).one().id


def unidad(db, placa="LGA1001", tipo="1.5 ton", clase="unidad", odoo_id=None,
           **campos) -> m.LgUnidad:
    """Una unidad como la deja la lectura de Odoo, con lo que se le pase."""
    u = m.LgUnidad(placa=placa, clase=clase, odoo_id=odoo_id,
                   tipo_id=tipo_id(db, tipo) if clase == "unidad" and tipo else None,
                   estado="disponible", activo=True, **campos)
    db.add(u)
    db.commit()
    return u


def operador(db, nombre="Pedro Lopez", correo="pedro.lopez@gmail.com",
             ingreso=date(2020, 1, 15), odoo_id=None, **campos) -> m.LgOperador:
    o = m.LgOperador(nombre=nombre, correo=correo, fecha_ingreso=ingreso,
                     odoo_id=odoo_id, puesto_odoo="Operador", activo=True, **campos)
    db.add(o)
    db.commit()
    return o


def expediente(db, u: m.LgUnidad, vence: date | None = None, salvo=()) -> None:
    """Los cinco documentos de la unidad, vigentes un ano (o hasta `vence`)."""
    actor = usuario(db)
    for tipo in lg_flota.DOCUMENTOS:
        if tipo in salvo:
            continue
        lg_flota.capturar_documento(db, actor, tipo, unidad=u,
                                    vence_en=vence or hoy() + timedelta(days=365))
    db.commit()


def licencia(db, o: m.LgOperador, vence: date | None = None) -> None:
    lg_flota.capturar_documento(db, usuario(db), lg_flota.LICENCIA, operador=o,
                                vence_en=vence or hoy() + timedelta(days=365),
                                detalle="Tipo E")
    db.commit()


def costo_del_tipo(cliente, karla, db, tipo="1.5 ton", desde=None, datos=UNIDAD_15):
    """El costo del tipo en los catalogos de la seccion 150."""
    r = cliente.post("/lg/catalogos/valores", headers=karla, json={
        "clave": "unidad", "vigente_desde": (desde or hoy()).isoformat(),
        "datos": datos, "tipo_unidad_id": tipo_id(db, tipo),
        "motivo": "el del boceto de Flota" if (desde or hoy()) < hoy() else None})
    assert r.status_code == 201, r.text
    return r.json()

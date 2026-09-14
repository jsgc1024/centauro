"""Punto de entrada de lo que viene de Odoo.

Odoo es la fuente de verdad de empleados y flota: nombre, telefono y
fotografia. Aqui no se capturan a mano, se sincronizan.

Mientras no exista la conexion real, estas funciones son el unico lugar
que habra que cambiar: el resto del sistema ya lee foto_url y telefono
de la base local, sin saber de donde salieron.
"""
from sqlalchemy.orm import Session

from app import models as m
from app import telefonos


def _con_clave(db: Session, fila, campo: str, valor):
    """Regla general: ningun telefono se guarda sin clave de pais.

    Tambien lo que llega de Odoo: el pais sale de la ciudad donde esta
    dada de alta la persona.
    """
    if campo != "telefono" or not valor:
        return valor
    plaza = db.get(m.Plaza, getattr(fila, "plaza_id", None))
    return telefonos.normalizar(db, valor, plaza.pais_id if plaza else None)


def sincronizar_personal(db: Session, empleados: list[dict]) -> dict:
    """Cada empleado: {correo, nombre?, telefono?, foto_url?}.

    El correo es la llave: es con el que el empleado entra al sistema.
    """
    return _sincronizar(db, m.Persona, "correo", empleados,
                        ("nombre", "telefono", "foto_url"))


def sincronizar_flota(db: Session, vehiculos: list[dict]) -> dict:
    """Cada vehiculo: {placa, color?, modelo_anio?, foto_url?}."""
    return _sincronizar(db, m.Vehiculo, "placa", vehiculos,
                        ("color", "modelo_anio", "foto_url"))


def sincronizar_taller(db: Session, entradas: list[dict]) -> dict:
    """Las unidades que estan fuera de circulacion.

    Odoo manda el rango; aqui solo se guarda y se respeta. Lo que ya
    vino se actualiza por su odoo_id —el taller cambia la fecha de
    entrega mas de una vez— y lo que no lo trae se guarda tal cual.
    """
    guardados, sin_encontrar = 0, []
    for entrada in entradas:
        placa = (entrada.get("placa") or "").strip().upper()
        vehiculo = db.query(m.Vehiculo).filter_by(placa=placa).first() if placa else None
        if not vehiculo:
            sin_encontrar.append(placa)
            continue

        fila = None
        if entrada.get("odoo_id"):
            fila = (db.query(m.TallerVehiculo)
                    .filter_by(odoo_id=entrada["odoo_id"]).first())
        if not fila:
            fila = m.TallerVehiculo(vehiculo_id=vehiculo.id,
                                    desde=entrada["desde"])
            db.add(fila)

        fila.vehiculo_id = vehiculo.id
        for campo in ("desde", "hasta", "tipo", "taller", "folio", "nota",
                      "odoo_id"):
            if campo in entrada:
                setattr(fila, campo, entrada[campo])
        guardados += 1

    db.commit()
    return {"guardados": guardados, "sin_encontrar": sin_encontrar}


def _sincronizar(db: Session, modelo, llave: str, registros: list[dict],
                 campos: tuple) -> dict:
    actualizados, sin_encontrar = 0, []
    for registro in registros:
        valor = registro.get(llave)
        if not valor:
            continue
        fila = db.query(modelo).filter_by(**{llave: valor}).first()
        if not fila:
            sin_encontrar.append(valor)
            continue
        cambio = False
        for campo in campos:
            nuevo = _con_clave(db, fila, campo, registro.get(campo))
            # Odoo manda solo lo que trae: un campo vacio no borra lo local.
            if nuevo not in (None, "") and getattr(fila, campo) != nuevo:
                setattr(fila, campo, nuevo)
                cambio = True
        if cambio:
            actualizados += 1
    db.commit()
    return {"actualizados": actualizados, "sin_encontrar": sin_encontrar}

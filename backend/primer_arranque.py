#!/usr/bin/env python3
"""La primera vez de una base de produccion: los catalogos y la primera cuenta.

    docker compose -f docker-compose.prod.yml run --rm api \\
        python primer_arranque.py --correo tu@centauro.lat --nombre "Tu Nombre"

Hace dos cosas, y solo en una base sin ningun usuario:

1. **Carga los catalogos**: paises, plazas, perfiles, categorias de
   vehiculo, modalidades, tarifario, tabulador de viaticos, comisiones,
   parametros, festivos, criterios de estrella, hospitales y hoteles.
   **No** carga el personal, la flota ni el cliente de ejemplo: en
   produccion la gente y las unidades llegan de Odoo, y una camioneta con
   placa inventada en la lista de disponibles termina asignada a un
   servicio de verdad.

2. **Crea la primera cuenta**, con rol de direccion general, y pide su
   contrasena aqui mismo: no se ve en pantalla ni queda en el historial
   de la terminal. Las demas cuentas se dan de alta desde la consola
   (Accesos), cada una con su invitacion.

Con cualquier usuario ya creado no hace nada. La base ya arranco, y volver
a sembrar encima de datos reales es como se cuelan los montos de ejemplo.

Los MONTOS de la semilla son de ejemplo. Al terminar dice cuales revisar.
"""
import argparse
import getpass
import sys

from fastapi import HTTPException

from app import accesos, auth, contrasenas, seed
from app import models as m

# En el orden en que dependen una de otra: sin paises y plazas no hay
# donde colgar lo demas. `sembrar_recursos` --el personal, la flota y el
# cliente de ejemplo-- no esta, a proposito.
SEMILLAS = ("sembrar", "sembrar_parametros", "sembrar_festivos",
            "sembrar_bonos", "sembrar_lugares")

POR_REVISAR = (
    "el tarifario general y el tabulador de viaticos (montos de ejemplo)",
    "las comisiones, los criterios de estrella y sus montos (de ejemplo)",
    "el precio del combustible y los pesos del tablero de profesionalismo",
    "los festivos del ano",
    "los hospitales y hoteles (ubicaciones aproximadas, sin telefonos)",
)


class NoSePuede(Exception):
    """Algo que quien lo corre tiene que corregir; el mensaje dice que."""


def _motivo(error: HTTPException) -> str:
    detalle = error.detail
    if isinstance(detalle, dict):
        return " ".join(str(v) for v in detalle.values())
    return str(detalle)


def ya_arranco(fabrica=None) -> bool:
    fabrica = fabrica or seed.SessionLocal
    db = fabrica()
    try:
        return db.query(m.Usuario.id).first() is not None
    finally:
        db.close()


def revisar_cuenta(correo: str, nombre: str) -> tuple[str, str]:
    """El correo y el nombre, antes de pedir la contrasena."""
    correo = (correo or "").strip().lower()
    nombre = " ".join((nombre or "").split())
    usuario, _, dominio = correo.partition("@")
    if not usuario or "." not in dominio or " " in correo:
        raise NoSePuede(f"'{correo}' no parece un correo.")
    if len(nombre) < 3:
        raise NoSePuede("Falta el nombre completo.")
    return correo, nombre


def revisar_datos(correo: str, nombre: str, contrasena: str) -> tuple[str, str]:
    """Todo lo que puede estar mal se dice antes de escribir nada."""
    correo, nombre = revisar_cuenta(correo, nombre)
    try:
        contrasenas.validar(contrasena, m.Usuario(correo=correo))
    except HTTPException as e:
        raise NoSePuede(_motivo(e)) from None
    return correo, nombre


def arrancar(correo: str, nombre: str, contrasena: str, fabrica=None) -> dict:
    fabrica = fabrica or seed.SessionLocal
    if ya_arranco(fabrica):
        raise NoSePuede(
            "Esta base ya tiene usuarios: ya arranco. Las cuentas nuevas se "
            "dan de alta desde la consola (Accesos), y los catalogos se "
            "corrigen en sus pantallas.")
    correo, nombre = revisar_datos(correo, nombre, contrasena)

    sembrado = {nombre_semilla: getattr(seed, nombre_semilla)()
                for nombre_semilla in SEMILLAS}

    db = fabrica()
    try:
        plaza = db.query(m.Plaza).filter_by(nombre="Ciudad de Mexico").first()
        if plaza is None:
            raise NoSePuede("Los catalogos no dejaron la plaza Ciudad de Mexico.")
        persona = db.query(m.Persona).filter_by(correo=correo).first()
        if persona is None:
            persona = m.Persona(nombre=nombre, correo=correo, plaza_id=plaza.id)
            db.add(persona)
            db.flush()
        usuario = m.Usuario(persona_id=persona.id, correo=correo,
                            rol=m.Rol.DIRECTOR_GENERAL,
                            hash_contrasena=auth.cifrar(contrasena))
        db.add(usuario)
        db.flush()
        accesos.anotar(db, usuario, "acceso creado", "usuario", usuario.id,
                       despues=usuario.rol.value,
                       detalle="la primera cuenta, desde la terminal del "
                               "servidor (primer_arranque.py)")
        db.commit()
        cuenta = {"correo": correo, "nombre": persona.nombre,
                  "rol": usuario.rol.value}
        conteos = {
            "paises": db.query(m.Pais).count(),
            "plazas": db.query(m.Plaza).count(),
            "modalidades": db.query(m.Modalidad).count(),
            "personal": db.query(m.Persona).count(),
            "vehiculos": db.query(m.Vehiculo).count(),
            "clientes": db.query(m.Cliente).count(),
        }
    finally:
        db.close()
    return {"cuenta": cuenta, "conteos": conteos, "sembrado": sembrado}


def main(argv=None) -> int:
    lector = argparse.ArgumentParser(
        description="Catalogos y primera cuenta de una base nueva.")
    lector.add_argument("--correo", required=True,
                        help="el correo con el que vas a entrar")
    lector.add_argument("--nombre", required=True,
                        help="tu nombre completo, entre comillas")
    args = lector.parse_args(argv)

    if ya_arranco():
        print("Esta base ya tiene usuarios: ya arranco. No se toca nada.\n"
              "Las cuentas nuevas se dan de alta desde la consola (Accesos).")
        return 1
    try:
        revisar_cuenta(args.correo, args.nombre)
    except NoSePuede as e:
        print(f"ALTO: {e}")
        return 1

    print(f"La contrasena de {args.correo.strip().lower()}. No se ve al "
          "escribirla.\nAl menos 8 caracteres; mejor una frase que solo tu "
          "digas asi.")
    contrasena = getpass.getpass("Contrasena: ")
    if getpass.getpass("Otra vez: ") != contrasena:
        print("ALTO: no coinciden. No se toco nada; vuelve a correrlo.")
        return 1

    try:
        r = arrancar(args.correo, args.nombre, contrasena)
    except NoSePuede as e:
        print(f"ALTO: {e}")
        return 1

    c, n = r["cuenta"], r["conteos"]
    print("\nListo.")
    print(f"  Catalogos: {n['paises']} paises, {n['plazas']} plazas, "
          f"{n['modalidades']} modalidades.")
    print(f"  Sin ejemplos: {n['personal']} persona(s) --la tuya--, "
          f"{n['vehiculos']} vehiculos, {n['clientes']} clientes. La gente y "
          "la flota llegan de Odoo.")
    print(f"  Primera cuenta: {c['correo']} ({c['nombre']}), direccion general.")
    print("\nRevisa en la consola, antes de operar:")
    for cosa in POR_REVISAR:
        print(f"  - {cosa}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

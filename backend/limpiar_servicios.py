#!/usr/bin/env python3
"""Deja la mesa limpia: se va el movimiento, se quedan los catalogos.

Borra TODOS los servicios y todo lo que cuelga de ellos --jornadas,
marcas, viaticos, depositos, cierres, nominas, encuestas, bonos, alertas
y bitacoras-- y NO toca lo que se configura: usuarios y contrasenas,
personal, flota, clientes, plazas, modalidades, tarifarios y tabuladores.
Se entra igual que antes y se captura sin volver a sembrar nada.

    docker compose exec -T api python limpiar_servicios.py

Con `--accesos` ademas retira las cuentas de oficina de ejemplo --admin,
los consultores, central, finanzas, RRHH y direccion de operaciones-- y
deja solo la de direccion general, que las cubre todas por herencia, mas
las del personal de seguridad, que son las UNICAS que pueden marcar
desde el telefono: direccion general no hereda ese rol a proposito,
porque nadie debe poder firmarse su propia llegada.

    docker compose exec -T api python limpiar_servicios.py --accesos

No borra personas, solo su acceso. La ficha de Sofia Navarro sigue ahi;
lo que se va es su llave.

La lista de que es movimiento y que es catalogo NO se escribe aqui: se
lee de `tests/conftest.py`, que es la que la bateria mantiene al dia. Dos
listas iguales en dos archivos se separan el dia que alguien agrega una
tabla y toca una sola, y entonces esto deja huerfanos sin avisar.
"""
import sys

# El contenedor monta `backend/` en /code y arranca ahi, asi que
# `app` ya se importa; `tests` hay que decirlo.
sys.path.insert(0, "tests")

from sqlalchemy import text                                   # noqa: E402

from app import models as m                                   # noqa: E402
from app.config import settings                               # noqa: E402
from app.db import SessionLocal                               # noqa: E402
from app.seed import sembrar_recursos                         # noqa: E402
from conftest import TABLAS_DE_OPERACION                      # noqa: E402


# Este script vacia tablas enteras y no se puede deshacer. El candado va
# por el NOMBRE de la base: la de desarrollo se llama `centauro` y la de
# la bateria `centauro_test`. Cualquier otra cosa --una produccion que
# algun dia se llame distinto-- lo detiene aqui, antes de tocar nada.
PERMITIDAS = ("centauro", "centauro_test")

# La cuenta que manda. No se toca nunca por esta puerta: un script que
# se puede quedar sin nadie con quien entrar es un script que te encierra
# afuera de tu propio sistema.
DUENO = "direccion@centauro.lat"


def cual_base() -> str:
    return settings.database_url.rsplit("/", 1)[-1].split("?")[0]


def limpiar_accesos() -> None:
    """Deja la cuenta de direccion general y las del personal de campo.

    Las de oficina --admin, consultores, central, finanzas, RRHH,
    direccion de operaciones-- salen sobrando cuando quien prueba es el
    dueno: direccion general hereda esos seis roles. Las de campo NO
    salen sobrando, y es lo contrario de lo que uno supondria: son las
    unicas que pueden marcar un hito, subir un comprobante o revisar una
    unidad. Sin ellas, la mitad del ciclo no se puede recorrer.
    """
    db = SessionLocal()
    try:
        fuera = (db.query(m.Usuario)
                 .filter(m.Usuario.correo != DUENO,
                         m.Usuario.rol != m.Rol.PERSONAL_SEGURIDAD)
                 .all())
        if not fuera:
            print("No habia cuentas de oficina que retirar.")
            return
        for u in fuera:
            print(f"  retirando {u.correo} ({u.rol.value})")
            db.delete(u)
        db.commit()
        quedan = db.query(m.Usuario).count()
        campo = (db.query(m.Usuario)
                 .filter_by(rol=m.Rol.PERSONAL_SEGURIDAD).count())
        print(f"Quedan {quedan} cuentas: direccion general y {campo} de campo.")
        print("Las personas siguen ahi; lo que se fue es su llave.")
    finally:
        db.close()


def _solo_accesos() -> int:
    print()
    limpiar_accesos()
    return 0


def main() -> int:
    base = cual_base()
    if base not in PERMITIDAS:
        print(f"Me niego: esta base se llama '{base}' y no es de desarrollo.")
        print(f"Solo corro contra {' o '.join(PERMITIDAS)}.")
        return 1

    db = SessionLocal()
    try:
        cuantos = db.execute(text("SELECT count(*) FROM servicio")).scalar()
        print(f"Base '{base}': {cuantos} servicios.")
        if not cuantos:
            # Sin servicios no hay movimiento que borrar, pero eso NO
            # quiere decir que no haya nada que hacer: `--accesos` es
            # otra tarea y tiene que correr igual. Salir aqui de golpe
            # hacia que una base ya limpia ignorara la peticion sin
            # decir por que, que es la peor forma de no hacer algo.
            print("No hay movimiento que borrar.")
            return 0 if "--accesos" not in sys.argv else _solo_accesos()

        db.execute(text(
            f"TRUNCATE {', '.join(TABLAS_DE_OPERACION)} RESTART IDENTITY CASCADE"))
        db.commit()
        print("Movimiento borrado.")
    finally:
        db.close()

    # La flota se fue con el vaciado y no es movimiento: es el catalogo
    # con el que se trabaja. El auto subarrendado vive en la misma tabla
    # y apunta a su servicio, asi que al vaciar servicio Postgres se
    # lleva vehiculo por el CASCADE, quiera uno o no.
    print("Volviendo a sembrar la flota...", sembrar_recursos())

    db = SessionLocal()
    try:
        for tabla in ("servicio", "jornada", "persona", "vehiculo", "usuario"):
            n = db.execute(text(f"SELECT count(*) FROM {tabla}")).scalar()
            print(f"  {tabla}: {n}")
    finally:
        db.close()
    if "--accesos" in sys.argv:
        print()
        limpiar_accesos()

    print("Listo. El personal y los catalogos siguen ahi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

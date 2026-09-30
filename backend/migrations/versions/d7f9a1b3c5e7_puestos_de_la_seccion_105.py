"""Los puestos que ya existen toman lo nuevo de la seccion 105

`crear_puestos` no pisa un puesto que ya esta en la base (para eso se
cambiaron), asi que las actividades y la pantalla que trajo la seccion
105 no le llegaban solas a quien entra con puesto: habia que marcarlas a
mano desde Accesos. Salvador (30 sep) pidio que quedaran puestas
directo:

- «Direccion de operaciones»: la pantalla `direccion` y las actividades
  `direccion.ver` (su bandeja y el tablero de hoy), `cierre.autorizar_cobro`
  (el cobro al cancelar) y `servicios.titular` (cambiar al consultor
  titular).
- «Supervisor de central» y «Monitorista»: `bonos.incidencia`
  (registrar una incidencia; la central tambien la levanta).

Solo suma: no quita nada que alguien haya puesto a mano, y si el puesto
no existe en esa base no hace nada. Correrla dos veces no duplica.

Revision ID: d7f9a1b3c5e7
Revises: c5e7a9b1d3f5
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

revision = "d7f9a1b3c5e7"
down_revision = "c5e7a9b1d3f5"
branch_labels = None
depends_on = None

ACTIVIDADES = {
    "Dirección de operaciones": ["direccion.ver", "cierre.autorizar_cobro",
                                 "servicios.titular"],
    "Supervisor de central": ["bonos.incidencia"],
    "Monitorista": ["bonos.incidencia"],
}
PANTALLAS = {"Dirección de operaciones": ["direccion"]}


def _categoria(con, nombre):
    fila = con.execute(sa.text(
        "SELECT id, pantallas FROM categoria_acceso WHERE nombre = :n"),
        {"n": nombre}).first()
    return fila


def upgrade() -> None:
    con = op.get_bind()
    for nombre, actividades in ACTIVIDADES.items():
        fila = _categoria(con, nombre)
        if fila is None:
            continue
        for actividad in actividades:
            # Con el tipo dicho: psycopg no deduce el del parametro que
            # se usa como texto y como varchar en la misma sentencia.
            con.execute(sa.text(
                "INSERT INTO actividad_de_categoria (categoria_id, actividad) "
                "SELECT CAST(:c AS INTEGER), CAST(:a AS VARCHAR(60)) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM actividad_de_categoria "
                "  WHERE categoria_id = CAST(:c AS INTEGER) "
                "  AND actividad = CAST(:a AS VARCHAR(60)))"),
                {"c": fila.id, "a": actividad})
    for nombre, pantallas in PANTALLAS.items():
        fila = _categoria(con, nombre)
        # Sin lista de pantallas el menu sale del rol, que ya trae la
        # pantalla nueva: no hay nada que agregar.
        if fila is None or not fila.pantallas:
            continue
        puestas = [x for x in fila.pantallas.split(",") if x]
        nuevas = [p for p in pantallas if p not in puestas]
        if nuevas:
            con.execute(sa.text(
                "UPDATE categoria_acceso SET pantallas = :p WHERE id = :c"),
                {"p": ",".join(puestas + nuevas), "c": fila.id})


def downgrade() -> None:
    con = op.get_bind()
    for nombre, actividades in ACTIVIDADES.items():
        fila = _categoria(con, nombre)
        if fila is None:
            continue
        for actividad in actividades:
            con.execute(sa.text(
                "DELETE FROM actividad_de_categoria "
                "WHERE categoria_id = :c AND actividad = :a"),
                {"c": fila.id, "a": actividad})
    for nombre, pantallas in PANTALLAS.items():
        fila = _categoria(con, nombre)
        if fila is None or not fila.pantallas:
            continue
        quedan = [x for x in fila.pantallas.split(",") if x and x not in pantallas]
        con.execute(sa.text(
            "UPDATE categoria_acceso SET pantallas = :p WHERE id = :c"),
            {"p": ",".join(quedan), "c": fila.id})

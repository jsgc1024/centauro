"""La pantalla del mapa de riesgo (seccion 135)

Los puestos de la central, direccion de operaciones y sistema y calidad
toman la pantalla nueva en su menu. Sistema y calidad toma tambien
`riesgo.ver`: lleva los tipos de evento y los clientes de la Central, y
para eso tiene que ver el mapa.

Revision ID: e6c4a2f0b8d1
Revises: d4b2f8e6a1c3
"""
import sqlalchemy as sa
from alembic import op

revision = "e6c4a2f0b8d1"
down_revision = "d4b2f8e6a1c3"
branch_labels = None
depends_on = None

PANTALLAS = {
    "Dirección de operaciones": ["riesgo"],
    "Supervisor de central": ["riesgo"],
    "Monitorista": ["riesgo"],
    "Administración del sistema y calidad": ["riesgo"],
}
ACTIVIDADES = {"Administración del sistema y calidad": ["riesgo.ver"]}


def _categoria(con, nombre):
    return con.execute(sa.text(
        "SELECT id, pantallas FROM categoria_acceso WHERE nombre = :n"),
        {"n": nombre}).first()


def upgrade() -> None:
    con = op.get_bind()
    for nombre, actividades in ACTIVIDADES.items():
        fila = _categoria(con, nombre)
        if fila is None:
            continue
        for actividad in actividades:
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
        # Sin lista de pantallas el menu sale del rol, que ya la trae.
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
    fila = _categoria(con, "Administración del sistema y calidad")
    if fila is not None:
        con.execute(sa.text(
            "DELETE FROM actividad_de_categoria WHERE categoria_id = :c "
            "AND actividad = 'riesgo.ver'"), {"c": fila.id})
    for nombre in PANTALLAS:
        fila = _categoria(con, nombre)
        if fila is None or not fila.pantallas:
            continue
        quedan = [x for x in fila.pantallas.split(",") if x and x != "riesgo"]
        con.execute(sa.text(
            "UPDATE categoria_acceso SET pantallas = :p WHERE id = :c"),
            {"p": ",".join(quedan), "c": fila.id})

"""El puesto «Gerente de administración» (seccion 108)

Salvador lo pidio el 30 de septiembre con la recomendacion de Claude:
firma el dinero y la gente sin operar. Aprueba y factura los cierres,
fija los tabuladores, autoriza el bono del mes, registra las diferencias
de las comisiones y ve toda la operacion, las encuestas y el mes en
cifras. Lo que ejecuta el dinero --depositar, armar el corte, marcarlo
pagado, pagar el bono-- se queda en Tesoreria, Nomina y el Jefe de
finanzas: quien autoriza no paga. No da accesos ni toca Odoo.

`crear_puestos` no crea solo lo que falta en una base que ya existe --se
crea desde el boton de Accesos--, asi que esta migracion lo deja puesto
en produccion. Si ya existe un puesto con ese nombre no lo toca; correrla
dos veces no duplica. Las actividades y pantallas son las mismas de
`puestos_base.PUESTOS`.

Revision ID: f0b2d4e6a8c0
Revises: e9c1a3b5d7f9
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

revision = "f0b2d4e6a8c0"
down_revision = "e9c1a3b5d7f9"
branch_labels = None
depends_on = None

NOMBRE = "Gerente de administración"
DESCRIPCION = ("Firma el dinero y la gente sin operar: aprueba y factura "
               "los cierres, fija los tabuladores, autoriza el bono del "
               "mes y ve toda la operación en cifras.")
# En el orden del menu, como las guarda la consola.
PANTALLAS = "panorama,servicios,implantados,equipo,bonos,encuestas,calidad,finanzas,facturacion,nomina,catalogos"
PUESTOS_ODOO = ("Gerente de Administración, Gerente de Administracion, "
                "Gerente Administrativo, Gerente Administrativa, "
                "Gerente de Administración y Finanzas")
ACTIVIDADES = [
    "panorama.ver", "servicios.ver", "solicitantes.ver", "asignaciones.ver",
    "tasksheet.ver", "contingencia.ver", "implantado.ver", "unidades.ver",
    "encuestas.ver", "profesionalismo.ver",
    "viaticos.ver", "viaticos.evidencia", "archivo.ver",
    "cierre.ver", "cierre.facturar", "cierre.rentabilidad", "cierre.historial",
    "nomina.ver", "nomina.tabulador", "comisiones.ver", "comisiones.ajustar",
    "bonos.ver", "bonos.autorizar",
    "catalogos.dinero",
    "calidad.ver",
]


def _id(con):
    fila = con.execute(sa.text(
        "SELECT id FROM categoria_acceso WHERE nombre = :n"), {"n": NOMBRE}).first()
    return fila.id if fila else None


def upgrade() -> None:
    con = op.get_bind()
    if _id(con) is not None:
        return
    con.execute(sa.text(
        "INSERT INTO categoria_acceso "
        "(nombre, descripcion, activa, rol, area, pantallas, puestos_odoo, orden) "
        "VALUES (:n, :d, true, CAST('FINANZAS' AS rol), :a, :p, :o, 35)"),
        {"n": NOMBRE, "d": DESCRIPCION, "a": "Administración",
         "p": PANTALLAS, "o": PUESTOS_ODOO})
    categoria_id = _id(con)
    for actividad in ACTIVIDADES:
        # Con el tipo dicho (seccion 105): psycopg no deduce el del
        # parametro que se usa dos veces en la misma sentencia.
        con.execute(sa.text(
            "INSERT INTO actividad_de_categoria (categoria_id, actividad) "
            "SELECT CAST(:c AS INTEGER), CAST(:a AS VARCHAR(60)) "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM actividad_de_categoria "
            "  WHERE categoria_id = CAST(:c AS INTEGER) "
            "  AND actividad = CAST(:a AS VARCHAR(60)))"),
            {"c": categoria_id, "a": actividad})


def downgrade() -> None:
    con = op.get_bind()
    categoria_id = _id(con)
    if categoria_id is None:
        return
    # A quien lo traiga se le quita: vuelve a entrar con lo de su rol.
    con.execute(sa.text(
        "UPDATE usuario SET categoria_id = NULL WHERE categoria_id = :c"),
        {"c": categoria_id})
    con.execute(sa.text(
        "DELETE FROM actividad_de_categoria WHERE categoria_id = :c"),
        {"c": categoria_id})
    con.execute(sa.text("DELETE FROM categoria_acceso WHERE id = :c"),
                {"c": categoria_id})

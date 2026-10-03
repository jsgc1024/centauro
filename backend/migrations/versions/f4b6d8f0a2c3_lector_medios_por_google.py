"""Los medios cuyo RSS no deja leer, por Google Noticias (seccion 144)

Animal Politico (404), Riodoce (500), Quadratin (no da RSS), Aristegui y
Pie de Pagina (cero notas) pasan a leerse con una busqueda «site:».
Solo si la direccion sigue siendo la de origen: lo que la Central ya
cambio a mano no se toca.

Revision ID: f4b6d8f0a2c3
Revises: e3a5c7e9f1b2
"""
import sqlalchemy as sa
from alembic import op

revision = "f4b6d8f0a2c3"
down_revision = "e3a5c7e9f1b2"
branch_labels = None
depends_on = None

CAMBIOS = (
    ("https://animalpolitico.com/feed/", "site:animalpolitico.com"),
    ("https://aristeguinoticias.com/feed/", "site:aristeguinoticias.com"),
    ("https://piedepagina.mx/feed/", "site:piedepagina.mx"),
    ("https://riodoce.mx/feed/", "site:riodoce.mx"),
    ("https://www.quadratin.com.mx/feed/", "site:quadratin.com.mx"),
)


def upgrade() -> None:
    con = op.get_bind()
    for antes, ahora in CAMBIOS:
        con.execute(sa.text(
            "UPDATE fuente_lector SET tipo = 'busqueda', direccion = :ahora, "
            "error = NULL, error_en = NULL, leida_en = NULL "
            "WHERE tipo = 'medio' AND direccion = :antes"),
            {"antes": antes, "ahora": ahora})


def downgrade() -> None:
    con = op.get_bind()
    for antes, ahora in CAMBIOS:
        con.execute(sa.text(
            "UPDATE fuente_lector SET tipo = 'medio', direccion = :antes "
            "WHERE tipo = 'busqueda' AND direccion = :ahora"),
            {"antes": antes, "ahora": ahora})

"""El deposito guarda cuando se hizo y quien lo hizo

Revision ID: c92e40b7a531
Revises: b83f16a09d2e
"""
from alembic import op
import sqlalchemy as sa


revision = "c92e40b7a531"
down_revision = "b83f16a09d2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Finanzas no tenia memoria de lo que pagaba.

    Hasta hoy, confirmar un deposito cambiaba el estatus y nada mas: no
    quedaba la hora ni el nombre de quien lo confirmo. En cuanto el
    renglon salia de la bandeja, la unica forma de saber si a alguien ya
    se le habia depositado era preguntarle.

    Con esto el deposito queda firmado, y de ahi sale el historial: que
    salio esta semana, con que referencia y quien lo despacho.
    """
    op.add_column("solicitud_transferencia",
                  sa.Column("confirmada_en", sa.DateTime(), nullable=True))
    op.add_column("solicitud_transferencia",
                  sa.Column("confirmada_por_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_solicitud_confirmada_por",
                          "solicitud_transferencia", "persona",
                          ["confirmada_por_id"], ["id"])

    # Lo que ya estaba confirmado no tiene fecha real y no se inventa:
    # se le pone la de creacion de la solicitud, que es lo mas cercano
    # que existe, y se deja dicho aqui para que nadie lo lea como la
    # hora exacta del deposito.
    op.execute("""
        UPDATE solicitud_transferencia
        SET confirmada_en = creada_en
        WHERE estatus = 'CONFIRMADA' AND confirmada_en IS NULL
    """)


def downgrade() -> None:
    op.drop_constraint("fk_solicitud_confirmada_por",
                       "solicitud_transferencia", type_="foreignkey")
    op.drop_column("solicitud_transferencia", "confirmada_por_id")
    op.drop_column("solicitud_transferencia", "confirmada_en")

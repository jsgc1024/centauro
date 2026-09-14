"""El auto rentado que se deja de usar le queda a finanzas

Revision ID: c74a91be05d3
Revises: b06f4e28c517
Create Date: 2026-09-13

Borrar el servicio no cancela la renta. El contrato con la arrendadora
sigue vivo y el auto se sigue cobrando todos los dias este parado o no,
asi que el registro no puede desaparecer con el servicio: tiene que
quedarle a alguien enfrente hasta que hable con la arrendadora.

Por eso el folio se guarda aparte del enlace al servicio —el servicio se
puede borrar— y hay una marca de "por cancelar" con la firma de quien la
cancelo.
"""
import sqlalchemy as sa
from alembic import op

revision = "c74a91be05d3"
down_revision = "b06f4e28c517"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("vehiculo", sa.Column("renta_folio", sa.String(length=24),
                                        nullable=True))
    op.add_column("vehiculo", sa.Column(
        "renta_por_cancelar", sa.Boolean(), nullable=False,
        server_default="false"))
    op.add_column("vehiculo", sa.Column("renta_cancelada_en", sa.DateTime(),
                                        nullable=True))
    op.add_column("vehiculo", sa.Column("renta_cancelada_por_id",
                                        sa.Integer(), nullable=True))
    op.create_foreign_key("fk_vehiculo_renta_cancelada_por", "vehiculo",
                          "persona", ["renta_cancelada_por_id"], ["id"])

    # Lo que ya existe: el folio del servicio que pidio cada renta.
    op.execute("""
        UPDATE vehiculo v SET renta_folio = s.folio
        FROM servicio s
        WHERE v.servicio_id = s.id AND v.rentado = true
    """)
    # Y las que ya se habian dado de baja quedan pendientes: nadie llamo
    # a la arrendadora porque hasta ahora no habia donde verlas.
    op.execute("""
        UPDATE vehiculo SET renta_por_cancelar = true
        WHERE rentado = true AND activo = false
    """)


def downgrade():
    op.drop_constraint("fk_vehiculo_renta_cancelada_por", "vehiculo",
                       type_="foreignkey")
    for columna in ("renta_cancelada_por_id", "renta_cancelada_en",
                    "renta_por_cancelar", "renta_folio"):
        op.drop_column("vehiculo", columna)

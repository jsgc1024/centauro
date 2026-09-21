"""La declaracion de dano de la unidad

Pedido por Salvador (18 sep): que quien recibe la unidad declare si la
recibe con algun dano, y que al entregarla declare si se dano durante el
servicio y explique que paso.

Antes habia una nota libre y fotos de golpe, las dos opcionales. El caso
normal de una casilla opcional es que se quede vacia: quien recibe una
camioneta golpeada a las seis de la manana, con prisa, no va a
documentar por su cuenta un dano que no hizo --y ahi es exactamente
donde le va a hacer falta--.

Una sola pregunta por punta. Lo que significa lo dice el `tipo` que ya
existe: recibe + dano es "asi me la dieron"; entrega + dano es "esto
paso conmigo". Esa es la distincion que decide quien responde, y hasta
hoy habia que deducirla comparando fotos.

`hubo_dano` entra en falso para las revisiones que ya existen. No es que
no tuvieran dano: es que nadie pregunto, y eso no se puede inventar
hacia atras. Lo que vale es que a partir de aqui nadie firma sin
contestar.

Revision ID: b6d3f90a172c
Revises: a2f5e70c9d14
"""
import sqlalchemy as sa
from alembic import op

revision = "b6d3f90a172c"
down_revision = "a2f5e70c9d14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("revision_unidad",
                  sa.Column("hubo_dano", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    # El tipo va como texto y no como ENUM de Postgres, igual que
    # `angulo` y `tipo` en estas mismas tablas. Es la decision que ya
    # ahorro dos migraciones: agregar un tipo de dano manana no va a
    # necesitar tocar la base.
    op.add_column("revision_unidad",
                  sa.Column("dano_tipo", sa.String(12), nullable=True))
    op.add_column("revision_unidad",
                  sa.Column("dano_nota", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("revision_unidad", "dano_nota")
    op.drop_column("revision_unidad", "dano_tipo")
    op.drop_column("revision_unidad", "hubo_dano")

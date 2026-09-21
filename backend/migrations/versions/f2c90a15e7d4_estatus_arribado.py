"""El dia que llego al punto y espera al principal.

Llegar y esperar veinte minutos a que el ejecutivo baje no es tener el
servicio corriendo. La marca a mano de la central ya lo decia asi; la
marca desde la app encendia "en curso" al llegar. Este estatus las pone
de acuerdo.

Revision ID: f2c90a15e7d4
Revises: e5b71c04da38
"""
from alembic import op

revision = "f2c90a15e7d4"
down_revision = "e5b71c04da38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres no deja quitar un valor de un enum, asi que el downgrade
    # solo devuelve los dias a `en_curso`: el valor se queda en el tipo,
    # sin nadie que lo use.
    # Va antes de EN_CURSO para que el orden del tipo siga el orden real
    # del dia: si alguien ordena por estatus, arribado cae donde toca.
    op.execute("ALTER TYPE estatusjornada ADD VALUE IF NOT EXISTS 'ARRIBADO' "
               "BEFORE 'EN_CURSO'")


def downgrade() -> None:
    op.execute("UPDATE jornada SET estatus = 'EN_CURSO' "
               "WHERE estatus = 'ARRIBADO'")

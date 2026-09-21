"""Un aviso puede no ser sobre un servicio

`Notificacion.servicio_id` era obligatorio. Con eso, el sistema no sabia
mandar nada que no colgara de un servicio: ni la invitacion de acceso de
alguien que acaba de entrar a la empresa, ni el enlace de "olvide mi
contrasena", ni un aviso a administracion. Por eso esos dos los sigue
entregando una persona a mano desde el panel.

Es la tercera tabla con la misma suposicion metida --"todo lo que pasa
aqui pasa dentro de un servicio"--. `RegistroAccion` la tenia y por eso
nacio `RegistroAdmin`. Aqui se quita en vez de hacer una tabla nueva: un
aviso a una persona y un aviso sobre un servicio son la misma cosa
saliendo por el mismo canal, y partirlos habria dejado dos bandejas que
revisar.

Nada cambia para lo que ya existe: todas las notificaciones de hoy traen
su servicio y lo siguen trayendo. Lo unico que se abre es el hueco para
las que no lo tienen.

Revision ID: a2f5e70c9d14
Revises: f0c47a2e5b91
"""
import sqlalchemy as sa
from alembic import op

revision = "a2f5e70c9d14"
down_revision = "f0c47a2e5b91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("notificacion", "servicio_id",
                    existing_type=sa.Integer(), nullable=True)
    # El destinatario que no es un papel dentro de un servicio, sino una
    # persona de la empresa a secas.
    op.execute("ALTER TYPE destinatario ADD VALUE IF NOT EXISTS 'COLABORADOR'")


def downgrade() -> None:
    # Un aviso sin servicio no tiene a donde volver: si se baja esta
    # migracion con alguno guardado, la columna no puede ponerse
    # obligatoria otra vez. Se borran, que es lo unico honesto --son
    # avisos ya entregados, no dinero ni operacion-- y se dice aqui para
    # que nadie se sorprenda.
    op.execute("DELETE FROM notificacion WHERE servicio_id IS NULL")
    op.alter_column("notificacion", "servicio_id",
                    existing_type=sa.Integer(), nullable=False)
    # El valor del enum se queda: Postgres no sabe quitar uno, y dejarlo
    # no le hace daño a nadie.

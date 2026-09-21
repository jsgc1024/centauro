"""la hora de un implantado siempre esta confirmada

En el eventual de varios dias, el dia 2 hereda la hora del dia 1 y esa
hora es una suposicion hasta que alguien la confirma: la app del
personal la esconde a proposito, para no hacerle planear la noche
alrededor de una hora que nadie dijo.

En el implantado no aplica: la hora sale del acuerdo con el cliente y
es la misma todos los dias. Las jornadas que ya existen nacieron con la
marca en falso, asi que el agente veia "Sin hora" en todos sus dias.

Revision ID: d4a7e0b91c35
Revises: c07b53a91e46
Create Date: 2026-09-21 00:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a7e0b91c35'
down_revision: Union[str, None] = 'c07b53a91e46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE jornada SET hora_confirmada = true
        WHERE hora_confirmada = false
          AND equipo_id IN (
            SELECT e.id FROM equipo e
            JOIN servicio s ON s.id = e.servicio_id
            -- El enum guarda el NOMBRE, no el valor: desde la
            -- migracion b06f4e28c517 las etiquetas son IMPLANTADO y
            -- EVENTUAL. Se compara contra el texto en mayusculas para
            -- que valga en cualquiera de las dos formas.
            WHERE UPPER(s.tipo::text) = 'IMPLANTADO')
    """))


def downgrade() -> None:
    # No se deshace: no hay como saber cuales estaban en falso antes, y
    # volver a apagarlas le quitaria la hora a quien ya la ve.
    pass

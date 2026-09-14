"""El nivel de atencion del hospital deja de ser texto libre

Revision ID: f5d2091ac8b4
Revises: e8b407c1a2f9
Create Date: 2026-09-13

De este campo sale la regla que garantiza un quirofano en la referencia
medica de la hoja: si ninguno de los tres hospitales mas cercanos es de
tercer nivel, el ultimo lugar se le cede al tercer nivel mas proximo.

Escrito a mano, "3er nivel" no coincidia con nada, contaba como cero y
la regla dejaba de proteger sin avisarle a nadie. Ahora son tres valores
y ya. Lo que no se pueda traducir se queda vacio, que se ve y se
corrige, en vez de pasar por un nivel que no es.
"""
import sqlalchemy as sa
from alembic import op

revision = "f5d2091ac8b4"
down_revision = "e8b407c1a2f9"
branch_labels = None
depends_on = None

NIVELES = ("PRIMERO", "SEGUNDO", "TERCERO")


def upgrade():
    nivel = sa.Enum(*NIVELES, name="nivelhospital")
    nivel.create(op.get_bind(), checkfirst=True)
    op.execute("""
        ALTER TABLE hospital ALTER COLUMN nivel_atencion TYPE nivelhospital
        USING CASE
            WHEN lower(nivel_atencion) LIKE '%%primer%%' THEN 'PRIMERO'
            WHEN lower(nivel_atencion) LIKE '%%segundo%%' THEN 'SEGUNDO'
            WHEN lower(nivel_atencion) LIKE '%%tercer%%' THEN 'TERCERO'
            ELSE NULL
        END::nivelhospital
    """)


def downgrade():
    op.execute("""
        ALTER TABLE hospital ALTER COLUMN nivel_atencion TYPE VARCHAR(60)
        USING CASE nivel_atencion::text
            WHEN 'PRIMERO' THEN 'Primer nivel'
            WHEN 'SEGUNDO' THEN 'Segundo nivel'
            WHEN 'TERCERO' THEN 'Tercer nivel'
            ELSE NULL
        END
    """)
    sa.Enum(name="nivelhospital").drop(op.get_bind(), checkfirst=True)

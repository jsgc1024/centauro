"""El implantado con su propia jornada y los cambios del acuerdo (seccion 105)

Decision 6 de Salvador (29 sep): en Mexico y en Brasil el implantado es
de 12 horas corridas, y el ano que entra van a llevar horas de descanso
dentro de esas 12 --en bloques de una hora, 4 en total, salvo el 12x36--.
Hasta hoy el implantado tomaba el full day del pais, que en Brasil es de
10 horas, y cada dia generaba dos horas extra.

  - Un valor nuevo del enum de modalidad: `IMPLANTADO`.
  - `modalidad.intervalo_descanso`: de cuantas horas es cada bloque.
  - La modalidad `implantado` de cada pais: 12 h, 0 de descanso,
    intervalo 1, con horas extra y bloquea el dia.
  - Los contratos de implantado pasan a esa modalidad; sus dias ya
    generados se quedan con las horas que se contrataron.
  - Las comisiones del implantado y las tarifas de freelance que hoy
    viven en el full day se copian a la modalidad nueva: la nomina busca
    la tarifa por la modalidad del dia y sin esto los dias nuevos se
    quedaban sin tarifa.
  - `contrato_implantado.horas_jornada` y `horas_descanso`: lo que ese
    acuerdo tiene de distinto al pais (vacio = lo del pais).

Decision 14: el cambio del acuerdo aplica desde el mes siguiente. La
hora del encuentro que se acuerda con el cliente vive ahora tambien en
`acuerdo_implantado.hora_presentacion`: es la que toma el mes que se
abre; cada mes conserva la suya.

Revision ID: c5e7a9b1d3f5
Revises: c1e3a5b7d9f1
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op

revision = "c5e7a9b1d3f5"
down_revision = "c1e3a5b7d9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Un valor nuevo de un ENUM no se puede usar en la misma transaccion
    # que lo agrega, y abajo se insertan las modalidades nuevas.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE codigomodalidad ADD VALUE IF NOT EXISTS "
                   "'IMPLANTADO'")

    op.add_column("modalidad", sa.Column(
        "intervalo_descanso", sa.Numeric(4, 2), nullable=False,
        server_default="1"))
    op.add_column("contrato_implantado", sa.Column(
        "horas_jornada", sa.Numeric(4, 2), nullable=True))
    op.add_column("contrato_implantado", sa.Column(
        "horas_descanso", sa.Numeric(4, 2), nullable=True))
    op.add_column("acuerdo_implantado", sa.Column(
        "hora_presentacion", sa.String(8), nullable=True))

    # La modalidad del implantado en cada pais que no la tenga.
    op.execute("""
        INSERT INTO modalidad (pais_id, codigo, horas, horas_descanso,
                               intervalo_descanso, aplica_horas_extra,
                               bloquea_dia_completo, km_estimados)
        SELECT p.id, 'IMPLANTADO', 12, 0, 1, true, true, NULL
        FROM pais p
        WHERE NOT EXISTS (SELECT 1 FROM modalidad x
                          WHERE x.pais_id = p.id AND x.codigo = 'IMPLANTADO')
    """)

    # Lo que la nomina y el cierre buscan por modalidad, copiado del full
    # day a la modalidad nueva del mismo pais: las comisiones del
    # implantado y las tarifas de freelance. Se copian, no se mueven: los
    # dias que ya existen siguen con el full day y su tarifa.
    op.execute("""
        INSERT INTO comision_personal (pais_id, tipo_servicio, perfil_id,
                                       modalidad_id, monto,
                                       monto_hora_extra, moneda)
        SELECT c.pais_id, c.tipo_servicio, c.perfil_id, nueva.id, c.monto,
               c.monto_hora_extra, c.moneda
        FROM comision_personal c
        JOIN modalidad vieja ON vieja.id = c.modalidad_id
                            AND vieja.codigo = 'FULL_DAY'
        JOIN modalidad nueva ON nueva.pais_id = vieja.pais_id
                            AND nueva.codigo = 'IMPLANTADO'
        WHERE c.tipo_servicio = 'IMPLANTADO'
          AND NOT EXISTS (SELECT 1 FROM comision_personal x
                          WHERE x.pais_id = c.pais_id
                            AND x.tipo_servicio = c.tipo_servicio
                            AND x.perfil_id = c.perfil_id
                            AND x.modalidad_id = nueva.id)
    """)
    op.execute("""
        INSERT INTO tarifa_freelance (persona_id, modalidad_id, costo,
                                      costo_hora_extra, moneda)
        SELECT t.persona_id, nueva.id, t.costo, t.costo_hora_extra, t.moneda
        FROM tarifa_freelance t
        JOIN modalidad vieja ON vieja.id = t.modalidad_id
                            AND vieja.codigo = 'FULL_DAY'
        JOIN modalidad nueva ON nueva.pais_id = vieja.pais_id
                            AND nueva.codigo = 'IMPLANTADO'
        WHERE NOT EXISTS (SELECT 1 FROM tarifa_freelance x
                          WHERE x.persona_id = t.persona_id
                            AND x.modalidad_id = nueva.id)
    """)

    # Los contratos de implantado, a la modalidad de su pais.
    op.execute("""
        UPDATE contrato_implantado c
        SET modalidad_id = nueva.id
        FROM servicio s, modalidad nueva
        WHERE s.id = c.servicio_id
          AND nueva.pais_id = s.pais_id
          AND nueva.codigo = 'IMPLANTADO'
          AND c.modalidad_id <> nueva.id
    """)
    # Y sus dias ya generados, los que iban con el full day del pais:
    # con ellos la nomina y el cierre buscan la tarifa por la modalidad
    # del dia, y un dia de implantado que siguiera en full day cobraria
    # de una tabla que Nominas ya no ensena. Sus horas no cambian: el
    # inicio y el fin programados se quedan como se contrataron (como
    # cuando el catalogo cambia sus horas, ver `horas_extra.limite`).
    op.execute("""
        UPDATE jornada j
        SET modalidad_id = nueva.id
        FROM equipo e, servicio s, modalidad vieja, modalidad nueva
        WHERE e.id = j.equipo_id
          AND s.id = e.servicio_id
          AND s.tipo = 'IMPLANTADO'
          AND vieja.id = j.modalidad_id
          AND vieja.codigo = 'FULL_DAY'
          AND nueva.pais_id = vieja.pais_id
          AND nueva.codigo = 'IMPLANTADO'
    """)


def downgrade() -> None:
    # Los contratos y los dias vuelven al full day de su pais; lo copiado
    # a la modalidad nueva se quita y la modalidad tambien. El valor del
    # enum se queda: Postgres no deja quitarlo.
    op.execute("""
        UPDATE contrato_implantado c
        SET modalidad_id = vieja.id
        FROM servicio s, modalidad vieja, modalidad nueva
        WHERE s.id = c.servicio_id
          AND nueva.id = c.modalidad_id AND nueva.codigo = 'IMPLANTADO'
          AND vieja.pais_id = s.pais_id AND vieja.codigo = 'FULL_DAY'
    """)
    op.execute("""
        UPDATE jornada j
        SET modalidad_id = vieja.id
        FROM modalidad nueva, modalidad vieja
        WHERE nueva.id = j.modalidad_id AND nueva.codigo = 'IMPLANTADO'
          AND vieja.pais_id = nueva.pais_id AND vieja.codigo = 'FULL_DAY'
    """)
    op.execute("""
        DELETE FROM comision_personal
        WHERE modalidad_id IN (SELECT id FROM modalidad
                               WHERE codigo = 'IMPLANTADO')
    """)
    op.execute("""
        DELETE FROM tarifa_freelance
        WHERE modalidad_id IN (SELECT id FROM modalidad
                               WHERE codigo = 'IMPLANTADO')
    """)
    op.execute("DELETE FROM modalidad WHERE codigo = 'IMPLANTADO'")
    op.drop_column("acuerdo_implantado", "hora_presentacion")
    op.drop_column("contrato_implantado", "horas_descanso")
    op.drop_column("contrato_implantado", "horas_jornada")
    op.drop_column("modalidad", "intervalo_descanso")

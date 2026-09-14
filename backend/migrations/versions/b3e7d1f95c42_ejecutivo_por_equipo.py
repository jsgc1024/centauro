"""Cada equipo con su ejecutivo principal

Revision ID: b3e7d1f95c42
Revises: f8a1c64d20e5
Create Date: 2026-09-12

Un servicio de dos equipos casi nunca cubre a una sola persona. Lo del
servicio se queda: el equipo que no capture el suyo lo hereda.
"""
import sqlalchemy as sa
from alembic import op

revision = "b3e7d1f95c42"
down_revision = "f8a1c64d20e5"
branch_labels = None
depends_on = None

COLUMNAS = [
    ("ejecutivo_nombre", sa.String(160)),
    ("ejecutivo_apellidos", sa.String(160)),
    ("ejecutivo_correo", sa.String(160)),
    ("ejecutivo_telefono", sa.String(40)),
]


def upgrade():
    for nombre, tipo in COLUMNAS:
        op.add_column("equipo", sa.Column(nombre, tipo, nullable=True))


def downgrade():
    for nombre, _ in COLUMNAS:
        op.drop_column("equipo", nombre)

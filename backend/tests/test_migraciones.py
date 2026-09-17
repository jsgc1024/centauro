"""Que las migraciones dejen la base igual que el modelo.

La bateria arma su base desde el modelo (create_all), no desde las
migraciones. Eso es rapido, pero deja ciego justo el camino que corre en
produccion: una migracion mal escrita pasa todas las pruebas y revienta
en el primer INSERT del dia.

Ya paso una vez. Los tipos ENUM de Postgres se crearon con los valores
del enum de Python —"saturacion"— cuando SQLAlchemy guarda el NOMBRE
—"SATURACION"—, y ninguna prueba lo vio.

Esta prueba levanta una base aparte, le corre las migraciones desde cero
y compara lo que quedo contra el modelo.
"""
import pytest
from sqlalchemy import create_engine, inspect, text

BASE_MIGRADA = "centauro_migraciones"
SERVIDOR = "postgresql://centauro:centauro_dev@db:5432/postgres"
URL_MIGRADA = f"postgresql+psycopg://centauro:centauro_dev@db:5432/{BASE_MIGRADA}"


@pytest.fixture(scope="module")
def base_migrada():
    import psycopg
    from alembic import command
    from alembic.config import Config
    from app import config as configuracion

    with psycopg.connect(SERVIDOR, autocommit=True) as con:
        con.execute(f"DROP DATABASE IF EXISTS {BASE_MIGRADA} WITH (FORCE)")
        con.execute(f"CREATE DATABASE {BASE_MIGRADA}")

    # env.py toma la direccion de settings, no del alembic.ini.
    anterior = configuracion.settings.database_url
    configuracion.settings.database_url = URL_MIGRADA
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        configuracion.settings.database_url = anterior

    motor = create_engine(URL_MIGRADA)
    yield motor
    motor.dispose()


def _enums_del_modelo():
    """Los tipos ENUM que el modelo espera, con sus etiquetas."""
    from sqlalchemy import Enum as TipoEnum
    from app.db import Base

    tipos = {}
    for tabla in Base.metadata.tables.values():
        for columna in tabla.columns:
            if isinstance(columna.type, TipoEnum) and columna.type.name:
                tipos[columna.type.name] = set(columna.type.enums)
    return tipos


def test_los_enums_quedan_con_las_mismas_etiquetas(base_migrada):
    """El caso que ya nos mordio: el tipo creado a mano con los valores
    en minuscula, cuando SQLAlchemy escribe los nombres."""
    with base_migrada.connect() as con:
        en_la_base = {}
        for nombre, etiqueta in con.execute(text("""
                SELECT t.typname, e.enumlabel
                FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
        """)):
            en_la_base.setdefault(nombre, set()).add(etiqueta)

    for nombre, esperadas in _enums_del_modelo().items():
        assert nombre in en_la_base, f"falta el tipo {nombre}"
        assert en_la_base[nombre] == esperadas, (
            f"el tipo {nombre} quedo con {sorted(en_la_base[nombre])} "
            f"y el modelo espera {sorted(esperadas)}")


def test_no_falta_ninguna_tabla_ni_columna(base_migrada):
    """Una columna que se agrego al modelo y no a una migracion se ve
    aqui y no el dia que alguien la use."""
    from app.db import Base

    inspector = inspect(base_migrada)
    en_la_base = set(inspector.get_table_names())

    for nombre, tabla in Base.metadata.tables.items():
        assert nombre in en_la_base, f"falta la tabla {nombre}"
        columnas = {c["name"] for c in inspector.get_columns(nombre)}
        faltan = {c.name for c in tabla.columns} - columnas
        assert not faltan, f"a {nombre} le faltan columnas: {sorted(faltan)}"


def test_lo_obligatorio_en_el_modelo_lo_es_en_la_base(base_migrada):
    """Una columna que el modelo declara NOT NULL y la migracion creo
    nullable.

    Es de las que no se notan: el INSERT normal siempre trae valor, asi
    que la base nunca se queja. Lo que se rompe es la promesa —el modelo
    dice `datetime` y la base puede entregar None— y eso revienta lejos
    del lugar donde se origino, en cualquier `.isoformat()` a medio
    calculo.

    Se reportan todas de una vez: arreglar una y descubrir la siguiente
    en la corrida que sigue es perder media tarde.
    """
    from app.db import Base

    inspector = inspect(base_migrada)
    mal = []
    for nombre, tabla in Base.metadata.tables.items():
        en_la_base = {c["name"]: c for c in inspector.get_columns(nombre)}
        for columna in tabla.columns:
            suya = en_la_base.get(columna.name)
            if not suya:
                continue        # eso ya lo dice la prueba de arriba
            if not columna.nullable and suya["nullable"]:
                mal.append(f"{nombre}.{columna.name}")

    assert not mal, ("el modelo las declara obligatorias y la base las "
                     f"dejo opcionales: {sorted(mal)}")


def test_los_depositos_viejos_conservan_su_referencia(base_migrada):
    """La migracion del deposito bancario rellena hacia atras.

    Antes de que el deposito existiera, cada solicitud confirmada
    guardaba su referencia y su firma. La migracion las agrupa en un
    deposito por persona y equipo: si eso se hiciera mal, se perderia el
    rastro de todo lo que ya se pago, y eso no se puede recuperar.

    La base migrada esta vacia de movimientos, asi que aqui se verifica
    lo que si se puede verificar sin datos: que la tabla quedo, que la
    columna que las amarra existe, y que la llave foranea esta puesta.
    Lo que pasa con datos reales lo cubre la migracion en la base de
    verdad, que es donde hay filas.
    """
    inspector = inspect(base_migrada)
    assert "deposito_bancario" in inspector.get_table_names()

    columnas = {c["name"] for c in inspector.get_columns("deposito_bancario")}
    for necesaria in ("persona_id", "equipo_id", "monto", "moneda",
                      "referencia", "comprobante", "depositado_en",
                      "despachado_por_id"):
        assert necesaria in columnas, f"falta {necesaria}"

    amarre = {c["name"] for c in inspector.get_columns("solicitud_transferencia")}
    assert "deposito_id" in amarre

    llaves = [f for f in inspector.get_foreign_keys("solicitud_transferencia")
              if f["referred_table"] == "deposito_bancario"]
    assert llaves, "la solicitud no apunta al deposito"

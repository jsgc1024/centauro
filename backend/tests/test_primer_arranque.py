"""La primera vez de una base de produccion (seccion 68).

La semilla de demostracion trae personal, flota y un cliente inventados:
sirven para probar el motor de disponibilidad y en produccion se cuelan a
la lista de disponibles. Y el sembrado por la API se abria sin
credenciales mientras la base no tuviera usuarios, justo el rato en que un
servidor recien encendido tiene direccion publica y nadie mirando.

Estas pruebas corren en una base aparte, migrada desde cero como la del
servidor, y se vacia antes de cada una.
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BASE = "centauro_primer_arranque"
SERVIDOR = "postgresql://centauro:centauro_dev@db:5432/postgres"
URL = f"postgresql+psycopg://centauro:centauro_dev@db:5432/{BASE}"
FRASE = "una frase que solo yo digo"


@pytest.fixture(scope="module")
def motor_nuevo():
    import psycopg
    from alembic import command
    from alembic.config import Config
    from app import config as configuracion

    with psycopg.connect(SERVIDOR, autocommit=True) as con:
        con.execute(f"DROP DATABASE IF EXISTS {BASE} WITH (FORCE)")
        con.execute(f"CREATE DATABASE {BASE}")
    anterior = configuracion.settings.database_url
    configuracion.settings.database_url = URL
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        configuracion.settings.database_url = anterior

    motor = create_engine(URL)
    yield motor
    motor.dispose()
    with psycopg.connect(SERVIDOR, autocommit=True) as con:
        con.execute(f"DROP DATABASE IF EXISTS {BASE} WITH (FORCE)")


@pytest.fixture
def base_nueva(motor_nuevo, monkeypatch):
    """Una base vacia, recien migrada; la semilla escribe en ella."""
    from app import seed
    from app.db import Base

    tablas = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with motor_nuevo.begin() as con:
        con.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))
    fabrica = sessionmaker(bind=motor_nuevo, autoflush=False, autocommit=False)
    monkeypatch.setattr(seed, "SessionLocal", fabrica)
    return fabrica


def _cuantos(fabrica, modelo, **filtro):
    db = fabrica()
    try:
        return db.query(modelo).filter_by(**filtro).count()
    finally:
        db.close()


# ============================================================ el arranque

def test_arranca_una_base_nueva_sin_nada_de_ejemplo(base_nueva):
    import primer_arranque
    from app import auth
    from app import models as m

    r = primer_arranque.arrancar(" Salvador@Centauro.LAT ",
                                 "  Salvador   Garcia Carrasco ", FRASE)

    # Los catalogos llegaron.
    assert _cuantos(base_nueva, m.Pais, codigo="MX") == 1
    assert _cuantos(base_nueva, m.Plaza, nombre="Ciudad de Mexico") == 1
    assert _cuantos(base_nueva, m.Modalidad) > 0
    # Y nada de lo inventado: ni la flota, ni el cliente, ni la gente.
    assert _cuantos(base_nueva, m.Vehiculo) == 0
    assert _cuantos(base_nueva, m.Cliente) == 0
    assert _cuantos(base_nueva, m.Persona) == 1
    assert _cuantos(base_nueva, m.Persona, correo="juan.ramirez@centauro.lat") == 0
    assert r["conteos"]["vehiculos"] == 0

    # La primera cuenta, con su contrasena y sin la de demostracion.
    db = base_nueva()
    try:
        usuario = db.query(m.Usuario).one()
        assert usuario.correo == "salvador@centauro.lat"
        assert usuario.rol == m.Rol.DIRECTOR_GENERAL
        assert auth.verificar(FRASE, usuario.hash_contrasena)
        assert not auth.verificar("centauro2026", usuario.hash_contrasena)
        persona = db.get(m.Persona, usuario.persona_id)
        assert persona.nombre == "Salvador Garcia Carrasco"
        assert persona.plaza.nombre == "Ciudad de Mexico"
        # Queda en la bitacora de administracion, como cualquier alta.
        assert db.query(m.RegistroAdmin).filter_by(
            usuario_id=usuario.id, accion="acceso creado").count() == 1
    finally:
        db.close()


def test_con_un_usuario_ya_no_hace_nada(base_nueva):
    import primer_arranque
    from app import models as m

    primer_arranque.arrancar("salvador@centauro.lat", "Salvador Garcia", FRASE)
    with pytest.raises(primer_arranque.NoSePuede, match="ya tiene usuarios"):
        primer_arranque.arrancar("otra@centauro.lat", "Otra Persona",
                                 "otra frase bien distinta")
    assert _cuantos(base_nueva, m.Usuario) == 1


def test_una_contrasena_mala_no_deja_nada_a_medias(base_nueva):
    """Se revisa todo antes de escribir: ni catalogos sueltos ni cuenta."""
    import primer_arranque
    from app import models as m

    for mala in ("corta", "centauro2026", "aaaaaaaaaa", "salvador-2026-x"):
        with pytest.raises(primer_arranque.NoSePuede):
            primer_arranque.arrancar("salvador@centauro.lat", "Salvador", mala)
    with pytest.raises(primer_arranque.NoSePuede, match="no parece un correo"):
        primer_arranque.arrancar("salvador.centauro.lat", "Salvador", FRASE)
    assert _cuantos(base_nueva, m.Pais) == 0
    assert _cuantos(base_nueva, m.Usuario) == 0


def test_la_terminal_pide_la_contrasena_dos_veces(base_nueva, monkeypatch, capsys):
    import primer_arranque
    from app import models as m

    respuestas = iter([FRASE, FRASE + " distinta"])
    monkeypatch.setattr(primer_arranque.getpass, "getpass",
                        lambda *_: next(respuestas))
    salida = primer_arranque.main(["--correo", "salvador@centauro.lat",
                                   "--nombre", "Salvador Garcia"])
    assert salida == 1
    assert "no coinciden" in capsys.readouterr().out
    assert _cuantos(base_nueva, m.Usuario) == 0

    monkeypatch.setattr(primer_arranque.getpass, "getpass", lambda *_: FRASE)
    assert primer_arranque.main(["--correo", "salvador@centauro.lat",
                                 "--nombre", "Salvador Garcia"]) == 0
    dicho = capsys.readouterr().out
    assert "Primera cuenta: salvador@centauro.lat" in dicho
    assert "0 vehiculos" in dicho
    assert _cuantos(base_nueva, m.Usuario) == 1


def test_en_la_base_de_siempre_ni_pregunta_la_contrasena(monkeypatch, capsys):
    """La base de pruebas tiene usuarios: se detiene antes de pedir nada."""
    import primer_arranque

    pedida = []
    monkeypatch.setattr(primer_arranque.getpass, "getpass",
                        lambda *_: pedida.append(1) or FRASE)
    assert primer_arranque.main(["--correo", "x@centauro.lat",
                                 "--nombre", "Alguien Mas"]) == 1
    assert not pedida
    assert "ya tiene usuarios" in capsys.readouterr().out


# ============================================= el sembrado por la API

def test_en_produccion_la_primera_vez_no_es_por_la_api(base_nueva, motor_nuevo,
                                                       cliente, monkeypatch):
    from app import main
    from app import models as m
    from app.config import settings

    monkeypatch.setattr(main, "engine", motor_nuevo)
    monkeypatch.setattr(settings, "app_env", "produccion")
    r = cliente.post("/sistema/sembrar-catalogos")
    assert r.status_code == 403, r.text
    assert "primer_arranque.py" in r.text
    assert _cuantos(base_nueva, m.Pais) == 0


def test_en_desarrollo_la_primera_vez_sigue_abierta(base_nueva, motor_nuevo,
                                                    cliente, monkeypatch):
    """En la maquina de quien desarrolla no cambia nada: base sin
    usuarios, puerta abierta, y con los ejemplos para probar."""
    from app import main
    from app import models as m

    monkeypatch.setattr(main, "engine", motor_nuevo)
    r = cliente.post("/sistema/sembrar-catalogos")
    assert r.status_code == 200, r.text
    assert _cuantos(base_nueva, m.Vehiculo) > 0


def test_en_produccion_el_admin_siembra_sin_ejemplos(cliente, sesion, monkeypatch):
    from app.config import settings

    antes = cliente.get("/catalogos/vehiculos", headers=sesion("admin")).json()
    entorno = settings.app_env
    monkeypatch.setattr(settings, "app_env", "produccion")
    r = cliente.post("/sistema/sembrar-catalogos", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["recursos"], str)
    assert "Odoo" in r.json()["recursos"]
    monkeypatch.setattr(settings, "app_env", entorno)
    despues = cliente.get("/catalogos/vehiculos", headers=sesion("admin")).json()
    assert len(despues) == len(antes)

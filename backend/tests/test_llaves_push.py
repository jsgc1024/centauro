"""Las llaves de los avisos al telefono, en el .env que de verdad se lee.

En produccion el contenedor corre la imagen construida, sin la carpeta
montada: `generar_llaves_push.py` escribia en un .env que solo existia
dentro de ese contenedor. Y la plantilla de la guia traia los dos
renglones vacios, que el script tomaba por llaves y no generaba nada
(seccion 68).
"""
import base64
import os

import pytest

import generar_llaves_push as g


@pytest.fixture
def env(tmp_path, monkeypatch):
    ruta = tmp_path / ".env"
    monkeypatch.setattr(g, "ENV", str(ruta))
    return ruta


def _bytes(b64: str) -> bytes:
    return base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))


def test_los_renglones_vacios_se_llenan_sin_duplicarse(env):
    env.write_text("APP_ENV=produccion\nVAPID_PUBLIC=\nVAPID_PRIVATE=\n"
                   "VAPID_CONTACTO=mailto:operaciones@centauro.lat\n")
    assert g.main() == 0
    texto = env.read_text()
    assert texto.count("VAPID_PUBLIC=") == 1
    assert texto.count("VAPID_PRIVATE=") == 1
    assert "APP_ENV=produccion\n" in texto
    assert "VAPID_CONTACTO=mailto:operaciones@centauro.lat\n" in texto

    # Y son un par de verdad: la publica sale de la privada.
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    valores = g._valores(texto)
    privada = _bytes(valores["VAPID_PRIVATE"])
    publica = _bytes(valores["VAPID_PUBLIC"])
    assert len(privada) == 32 and len(publica) == 65 and publica[0] == 4
    llave = ec.derive_private_key(int.from_bytes(privada, "big"), ec.SECP256R1())
    assert llave.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint) == publica


def test_las_que_ya_estan_no_se_tocan(env):
    env.write_text("VAPID_PUBLIC=abc\nVAPID_PRIVATE=def\n")
    assert g.main() == 0
    assert env.read_text() == "VAPID_PUBLIC=abc\nVAPID_PRIVATE=def\n"


def test_una_sin_su_pareja_no_se_toca(env, capsys):
    """Generar un par nuevo encima de una llave que ya se repartio deja
    mudos a esos telefonos. Mejor detenerse y que alguien mire."""
    env.write_text("VAPID_PUBLIC=abc\nVAPID_PRIVATE=\n")
    assert g.main() == 1
    assert env.read_text() == "VAPID_PUBLIC=abc\nVAPID_PRIVATE=\n"
    assert "pareja" in capsys.readouterr().out


def test_en_produccion_sin_el_env_montado_no_escribe_nada(env, monkeypatch, capsys):
    monkeypatch.setattr(g, "_es_produccion", lambda: True)
    assert g.main() == 1
    assert not env.exists()
    assert '-v "$PWD/.env:/code/.env"' in capsys.readouterr().out


def test_en_desarrollo_lo_crea_si_no_existe(env, monkeypatch):
    monkeypatch.setattr(g, "_es_produccion", lambda: False)
    assert g.main() == 0
    assert set(g._valores(env.read_text())) == {"VAPID_PUBLIC", "VAPID_PRIVATE"}


def test_se_reescribe_el_mismo_archivo(env):
    """En el servidor el .env va montado encima del contenedor: montado se
    reescribe; un archivo nuevo que lo reemplace no llega al de afuera."""
    env.write_text("SECRET_KEY=x\nVAPID_PUBLIC=\nVAPID_PRIVATE=\n")
    antes = os.stat(env).st_ino
    assert g.main() == 0
    assert os.stat(env).st_ino == antes


def test_dice_como_hacer_que_la_app_las_tome(env, capsys):
    env.write_text("")
    assert g.main() == 0
    dicho = capsys.readouterr().out
    assert "up -d api worker beat" in dicho
    assert g._valores(env.read_text())["VAPID_PRIVATE"] not in dicho

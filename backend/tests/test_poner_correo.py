"""El correo en el .env del servidor, por Amazon SES (secciones 84, 91 y 93).

`despliegue/poner_correo.py` corre en el servidor, fuera de los
contenedores: pone de donde sale el correo, a donde llegan las respuestas
y el servidor de envio, y pide la llave sin que se vea. Amazon da un
usuario y una contrasena SMTP, y su servidor es uno por region. Postmark,
que no acepto el dominio, y MailerSend, que rechazo la cuenta, se quedan
como la otra forma. Lo que escribe lo tienen que leer igual docker
compose y la aplicacion.
"""
import importlib.util
import pathlib

import pytest
from dotenv import dotenv_values

RUTA = pathlib.Path(__file__).resolve().parents[2] / "despliegue" / "poner_correo.py"
_spec = importlib.util.spec_from_file_location("poner_correo", RUTA)
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)

# Asi lo dejo crear_env.py en el servidor de Google, el 25 de septiembre.
DEL_SERVIDOR = """APP_ENV=produccion
SECRET_KEY=abc
# Correo, del buzon de Microsoft 365 (guia, paso 7b). Vacio = no sale nada.
CORREO_DE=Centauro <ai@centauro.lat>
CORREO_MS_TENANT=
CORREO_MS_CLIENTE=
CORREO_MS_SECRETO=

# Odoo. Vacio = no se lee ni se manda nada.
ODOO_BASE=
"""

# Una llave con la forma de las de Postmark.
LLAVE = "1a2b3c4d-5e6f-7a8b-9c0d-e1f2a3b4c5d6"
# El usuario y la contrasena SMTP de Amazon: el usuario tiene la forma de
# una llave de acceso (el de ejemplo de la documentacion de Amazon) y la
# contrasena trae + y /.
USUARIO_SES = "AKIAIOSFODNN7EXAMPLE"
CLAVE_SES = "BGbWmCq4hq5l/a0+Ex3kS7Yr6o9tUq2Zp8wNcDfLmH1z"
SES = "email-smtp.us-east-2.amazonaws.com"


@pytest.fixture
def env(tmp_path, monkeypatch):
    ruta = tmp_path / ".env"
    monkeypatch.setattr(pc, "ENV", str(ruta))
    return ruta


def _correr(respuestas, clave, argv=()):
    otra = iter(respuestas)
    return pc.main(argv=list(argv), preguntar=lambda _: next(otra),
                   secreto=lambda _: clave)


def test_pone_amazon_y_deja_lo_demas(env, capsys):
    """Seccion 93: por omision, Amazon SES en Ohio, con su usuario y
    su contrasena SMTP."""
    env.write_text(DEL_SERVIDOR)
    env.chmod(0o600)
    assert _correr([USUARIO_SES], CLAVE_SES) == 0
    leido = dotenv_values(env)
    assert leido["CORREO_DE"] == "Centauro Connect <connect@mycentauro.lat>"
    assert (leido["CORREO_RESPONDER_A"]
            == "Centauro Connect <cecc.notification@centauro.lat>")
    assert leido["CORREO_HOST"] == SES
    assert leido["CORREO_PUERTO"] == "587"
    assert leido["CORREO_USUARIO"] == USUARIO_SES
    assert leido["CORREO_CLAVE"] == CLAVE_SES
    # El + y la / no piden comillas: se escriben tal cual.
    texto = env.read_text()
    assert f"CORREO_CLAVE={CLAVE_SES}\n" in texto
    assert texto.startswith("APP_ENV=produccion\nSECRET_KEY=abc\n")
    assert "ODOO_BASE=\n" in texto
    assert texto.count("CORREO_DE=") == 1
    assert pc.NUEVO in texto
    assert env.stat().st_mode & 0o777 == 0o600
    # La contrasena no sale en pantalla, ni un pedazo; del usuario, tres
    # letras. Y dice como se prueba mientras Amazon no apruebe.
    salida = capsys.readouterr().out
    assert CLAVE_SES[:6] not in salida and USUARIO_SES not in salida
    assert "Amazon SES" in salida and "simulator.amazonses.com" in salida


def test_amazon_en_otra_region(env):
    env.write_text(DEL_SERVIDOR)
    assert _correr([USUARIO_SES], CLAVE_SES, argv=["--region=us-east-1"]) == 0
    assert dotenv_values(env)["CORREO_HOST"] == "email-smtp.us-east-1.amazonaws.com"


@pytest.mark.parametrize("region", ["ohio", "us east 2", "mx-central", ""])
def test_una_region_mal_escrita_no_toca_nada(env, region):
    env.write_text(DEL_SERVIDOR)
    assert _correr([USUARIO_SES], CLAVE_SES, argv=[f"--region={region}"]) == 1
    assert env.read_text() == DEL_SERVIDOR


def test_de_postmark_a_amazon(env):
    """El .env ya traia Postmark: al poner Amazon se cambian el servidor,
    el usuario y la contrasena, sin renglones repetidos."""
    env.write_text(DEL_SERVIDOR)
    assert _correr([], LLAVE, argv=["--postmark"]) == 0
    assert _correr([USUARIO_SES], CLAVE_SES) == 0
    texto = env.read_text()
    leido = dotenv_values(env)
    assert leido["CORREO_HOST"] == SES
    assert leido["CORREO_USUARIO"] == USUARIO_SES
    assert leido["CORREO_CLAVE"] == CLAVE_SES
    assert LLAVE not in texto
    for c in ("CORREO_HOST=", "CORREO_USUARIO=", "CORREO_CLAVE="):
        assert texto.count(c) == 1


def test_por_postmark_sigue_sirviendo(env, capsys):
    """Seccion 91: la llave de Postmark va de usuario y de contrasena, y
    no se pregunta nada mas."""
    env.write_text(DEL_SERVIDOR)
    env.chmod(0o600)
    assert _correr([], LLAVE, argv=["--postmark"]) == 0
    leido = dotenv_values(env)
    assert leido["CORREO_DE"] == "Centauro Connect <connect@mycentauro.lat>"
    assert (leido["CORREO_RESPONDER_A"]
            == "Centauro Connect <cecc.notification@centauro.lat>")
    assert leido["CORREO_HOST"] == "smtp.postmarkapp.com"
    assert leido["CORREO_PUERTO"] == "587"
    assert leido["CORREO_USUARIO"] == LLAVE
    assert leido["CORREO_CLAVE"] == LLAVE
    # Lo demas, igual; nada repetido; el archivo sigue siendo solo suyo.
    texto = env.read_text()
    assert texto.startswith("APP_ENV=produccion\nSECRET_KEY=abc\n")
    assert "ODOO_BASE=\n" in texto
    assert texto.count("CORREO_DE=") == 1
    assert "Microsoft 365 (guia, paso 7b). Vacio" not in texto
    assert pc.NUEVO in texto
    assert leido["CORREO_MS_SECRETO"] == ""
    assert env.stat().st_mode & 0o777 == 0o600
    # La llave no sale en pantalla, ni un pedazo: es tambien la contrasena.
    salida = capsys.readouterr().out
    assert LLAVE[:3] not in salida and "Postmark" in salida


def test_por_mailersend_sigue_sirviendo(env, capsys):
    """La otra forma: usuario y contrasena, con el $ entre comillas."""
    env.write_text(DEL_SERVIDOR)
    assert _correr(["MS_abc123@mycentauro.lat"], "Xy9$kq.Lm",
                   argv=["--mailersend"]) == 0
    leido = dotenv_values(env)
    assert leido["CORREO_HOST"] == "smtp.mailersend.net"
    assert leido["CORREO_USUARIO"] == "MS_abc123@mycentauro.lat"
    # El $ va entre comillas simples: compose no lo toma por variable.
    assert leido["CORREO_CLAVE"] == "Xy9$kq.Lm"
    assert "CORREO_CLAVE='Xy9$kq.Lm'\n" in env.read_text()
    assert "Xy9$kq.Lm" not in capsys.readouterr().out


def test_de_mailersend_a_postmark(env):
    """El .env del servidor ya trae MailerSend: al poner Postmark se
    cambian el servidor y la llave, y el comentario deja de decir
    MailerSend."""
    env.write_text(DEL_SERVIDOR)
    assert _correr(["MS_abc@mycentauro.lat"], "clave-ms",
                   argv=["--mailersend"]) == 0
    viejo = env.read_text().replace(pc.NUEVO, pc.VIEJOS[1])
    env.write_text(viejo)
    assert _correr([], LLAVE, argv=["--postmark"]) == 0
    texto = env.read_text()
    leido = dotenv_values(env)
    assert leido["CORREO_HOST"] == "smtp.postmarkapp.com"
    assert leido["CORREO_USUARIO"] == leido["CORREO_CLAVE"] == LLAVE
    assert "mailersend" not in texto.lower()
    for c in ("CORREO_HOST=", "CORREO_USUARIO=", "CORREO_CLAVE="):
        assert texto.count(c) == 1


def test_se_puede_volver_a_correr(env):
    env.write_text(DEL_SERVIDOR)
    assert _correr([USUARIO_SES], "primera-llave") == 0
    assert _correr([USUARIO_SES], "segunda-llave") == 0
    texto = env.read_text()
    assert texto.count("CORREO_CLAVE=") == 1
    assert texto.count(pc.NUEVO) == 1
    assert dotenv_values(env)["CORREO_CLAVE"] == "segunda-llave"


@pytest.mark.parametrize("llave", ["", "dos palabras", "con'comilla"])
def test_sin_llave_buena_no_toca_nada(env, llave):
    env.write_text(DEL_SERVIDOR)
    assert _correr([], llave, argv=["--postmark"]) == 1
    assert env.read_text() == DEL_SERVIDOR


@pytest.mark.parametrize("usuario, clave", [
    ("", CLAVE_SES),
    (USUARIO_SES, ""),
    (USUARIO_SES, "dos palabras"),
    ("AKIA con espacio", CLAVE_SES),
])
def test_por_amazon_sin_usuario_o_clave_buenos_no_toca_nada(env, usuario, clave):
    env.write_text(DEL_SERVIDOR)
    assert _correr([usuario], clave) == 1
    assert env.read_text() == DEL_SERVIDOR


@pytest.mark.parametrize("usuario, clave", [
    ("", "clave"),
    ("MS_abc@mycentauro.lat", ""),
    ("MS_abc@mycentauro.lat", "dos palabras"),
])
def test_por_mailersend_sin_usuario_o_clave_buenos_no_toca_nada(env, usuario,
                                                                clave):
    env.write_text(DEL_SERVIDOR)
    assert _correr([usuario], clave, argv=["--mailersend"]) == 1
    assert env.read_text() == DEL_SERVIDOR


def test_con_microsoft_puesto_pregunta_antes(env):
    """Con los datos de Microsoft 365 llenos manda Microsoft: Amazon no
    se usaria. Se pregunta; si no, nada cambia."""
    lleno = DEL_SERVIDOR.replace("CORREO_MS_TENANT=", "CORREO_MS_TENANT=t-1")
    env.write_text(lleno)
    assert _correr([USUARIO_SES, "n"], CLAVE_SES) == 1
    assert env.read_text() == lleno
    assert _correr([USUARIO_SES, "s"], CLAVE_SES) == 0
    leido = dotenv_values(env)
    assert leido["CORREO_MS_TENANT"] == ""
    assert leido["CORREO_HOST"] == SES


def test_sin_env_no_crea_uno(env):
    assert _correr([USUARIO_SES], CLAVE_SES) == 1
    assert not env.exists()


# ====================================================== el interruptor

def test_poner_la_llave_no_enciende_el_correo(env, capsys):
    """Seccion 86: la llave se pone y se prueba con el correo apagado."""
    env.write_text(DEL_SERVIDOR)
    assert _correr([USUARIO_SES], CLAVE_SES) == 0
    assert dotenv_values(env)["CORREO_ENCENDIDO"] == "no"
    assert "sigue apagado" in capsys.readouterr().out
    # Y encendido se queda encendido si se vuelve a poner la llave.
    assert _correr([], "", argv=["--encender"]) == 0
    assert _correr([USUARIO_SES], "otra-llave") == 0
    assert dotenv_values(env)["CORREO_ENCENDIDO"] == "si"
    assert env.read_text().count("CORREO_ENCENDIDO=") == 1


def test_encender_pide_la_llave_antes(env):
    env.write_text(DEL_SERVIDOR)
    assert _correr([], "", argv=["--encender"]) == 1
    assert env.read_text() == DEL_SERVIDOR
    assert _correr([USUARIO_SES], CLAVE_SES) == 0
    assert _correr([], "", argv=["--encender"]) == 0
    assert dotenv_values(env)["CORREO_ENCENDIDO"] == "si"
    assert _correr([], "", argv=["--apagar"]) == 0
    assert dotenv_values(env)["CORREO_ENCENDIDO"] == "no"
    # La llave no se toca al mover el interruptor.
    assert dotenv_values(env)["CORREO_CLAVE"] == CLAVE_SES


# ---------------------------------- por Microsoft y por etapas (29 sep)

# Asi quedo el .env del servidor el 29 de septiembre: sale por Microsoft
# 365 desde connect@centauro.lat, con lo de Amazon todavia escrito.
CON_MICROSOFT = """APP_ENV=produccion
CORREO_DE=Centauro Connect <connect@centauro.lat>
CORREO_MS_TENANT=inquilino
CORREO_MS_CLIENTE=cliente
CORREO_MS_SECRETO=secreto
CORREO_ENCENDIDO=no
"""


def test_con_microsoft_se_enciende_sin_pedir_lo_de_amazon(env):
    env.write_text(CON_MICROSOFT)
    assert _correr([], "", argv=["--encender"]) == 0
    assert dotenv_values(env)["CORREO_ENCENDIDO"] == "si"


def test_primero_solo_la_empresa_y_despues_todos(env, capsys):
    """Decision de Salvador, 29 sep: el correo se enciende por etapas."""
    env.write_text(CON_MICROSOFT)
    assert _correr([], "", argv=["--solo-internos"]) == 0
    v = dotenv_values(env)
    assert (v["CORREO_ENCENDIDO"], v["CORREO_SOLO_INTERNOS"]) == ("si", "si")
    assert "SOLO para la empresa" in capsys.readouterr().out

    assert _correr([], "", argv=["--a-todos"]) == 0
    v = dotenv_values(env)
    assert (v["CORREO_ENCENDIDO"], v["CORREO_SOLO_INTERNOS"]) == ("si", "no")
    assert env.read_text().count("CORREO_SOLO_INTERNOS=") == 1
    # La llave no se toca.
    assert v["CORREO_MS_SECRETO"] == "secreto"


def test_sin_proveedor_la_etapa_no_enciende_nada(env):
    env.write_text(DEL_SERVIDOR)
    assert _correr([], "", argv=["--solo-internos"]) == 1
    assert env.read_text() == DEL_SERVIDOR

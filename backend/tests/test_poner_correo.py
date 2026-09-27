"""El correo en el .env del servidor, por MailerSend (seccion 84).

`despliegue/poner_correo.py` corre en el servidor, fuera de los
contenedores: pone de donde sale el correo, a donde llegan las respuestas
y el servidor de MailerSend, y pide el usuario y la contrasena sin que la
contrasena se vea. Lo que escribe lo tienen que leer igual docker compose
y la aplicacion.
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


@pytest.fixture
def env(tmp_path, monkeypatch):
    ruta = tmp_path / ".env"
    monkeypatch.setattr(pc, "ENV", str(ruta))
    return ruta


def _correr(respuestas, clave, argv=()):
    otra = iter(respuestas)
    return pc.main(argv=list(argv), preguntar=lambda _: next(otra),
                   secreto=lambda _: clave)


def test_pone_el_correo_y_deja_lo_demas(env, capsys):
    env.write_text(DEL_SERVIDOR)
    env.chmod(0o600)
    assert _correr(["MS_abc123@mycentauro.lat"], "Xy9$kq.Lm") == 0
    leido = dotenv_values(env)
    assert leido["CORREO_DE"] == "Centauro Connect <connect@mycentauro.lat>"
    assert (leido["CORREO_RESPONDER_A"]
            == "Centauro Connect <cecc.notification@centauro.lat>")
    assert leido["CORREO_HOST"] == "smtp.mailersend.net"
    assert leido["CORREO_PUERTO"] == "587"
    assert leido["CORREO_USUARIO"] == "MS_abc123@mycentauro.lat"
    # El $ va entre comillas simples: compose no lo toma por variable.
    assert leido["CORREO_CLAVE"] == "Xy9$kq.Lm"
    assert "CORREO_CLAVE='Xy9$kq.Lm'\n" in env.read_text()
    # Lo demas, igual; nada repetido; el archivo sigue siendo solo suyo.
    texto = env.read_text()
    assert texto.startswith("APP_ENV=produccion\nSECRET_KEY=abc\n")
    assert "ODOO_BASE=\n" in texto
    assert texto.count("CORREO_DE=") == 1
    assert "Microsoft 365 (guia, paso 7b). Vacio" not in texto
    assert leido["CORREO_MS_SECRETO"] == ""
    assert env.stat().st_mode & 0o777 == 0o600
    # La contrasena no sale en pantalla.
    assert "Xy9$kq.Lm" not in capsys.readouterr().out


def test_se_puede_volver_a_correr(env):
    env.write_text(DEL_SERVIDOR)
    assert _correr(["MS_abc123@mycentauro.lat"], "primera") == 0
    assert _correr(["MS_abc123@mycentauro.lat"], "segunda") == 0
    texto = env.read_text()
    assert texto.count("CORREO_CLAVE=") == 1
    assert dotenv_values(env)["CORREO_CLAVE"] == "segunda"


@pytest.mark.parametrize("usuario, clave", [
    ("", "clave"),
    ("MS_abc@mycentauro.lat", ""),
    ("MS_abc@mycentauro.lat", "dos palabras"),
])
def test_sin_usuario_o_clave_buenos_no_toca_nada(env, usuario, clave):
    env.write_text(DEL_SERVIDOR)
    assert _correr([usuario], clave) == 1
    assert env.read_text() == DEL_SERVIDOR


def test_con_microsoft_puesto_pregunta_antes(env):
    """Con los datos de Microsoft 365 llenos manda Microsoft: MailerSend
    no se usaria. Se pregunta; si no, nada cambia."""
    lleno = DEL_SERVIDOR.replace("CORREO_MS_TENANT=", "CORREO_MS_TENANT=t-1")
    env.write_text(lleno)
    assert _correr(["MS_abc@mycentauro.lat", "n"], "clave") == 1
    assert env.read_text() == lleno
    assert _correr(["MS_abc@mycentauro.lat", "s"], "clave") == 0
    leido = dotenv_values(env)
    assert leido["CORREO_MS_TENANT"] == ""
    assert leido["CORREO_HOST"] == "smtp.mailersend.net"


def test_sin_env_no_crea_uno(env):
    assert _correr(["MS_abc@mycentauro.lat"], "clave") == 1
    assert not env.exists()


# ====================================================== el interruptor

def test_poner_la_llave_no_enciende_el_correo(env, capsys):
    """Seccion 86: la llave se pone y se prueba con el correo apagado."""
    env.write_text(DEL_SERVIDOR)
    assert _correr(["MS_abc@mycentauro.lat"], "clave") == 0
    assert dotenv_values(env)["CORREO_ENCENDIDO"] == "no"
    assert "sigue apagado" in capsys.readouterr().out
    # Y encendido se queda encendido si se vuelve a poner la llave.
    assert _correr([], "", argv=["--encender"]) == 0
    assert _correr(["MS_abc@mycentauro.lat"], "otra") == 0
    assert dotenv_values(env)["CORREO_ENCENDIDO"] == "si"
    assert env.read_text().count("CORREO_ENCENDIDO=") == 1


def test_encender_pide_la_llave_antes(env):
    env.write_text(DEL_SERVIDOR)
    assert _correr([], "", argv=["--encender"]) == 1
    assert env.read_text() == DEL_SERVIDOR
    assert _correr(["MS_abc@mycentauro.lat"], "clave") == 0
    assert _correr([], "", argv=["--encender"]) == 0
    assert dotenv_values(env)["CORREO_ENCENDIDO"] == "si"
    assert _correr([], "", argv=["--apagar"]) == 0
    assert dotenv_values(env)["CORREO_ENCENDIDO"] == "no"
    # La llave no se toca al mover el interruptor.
    assert dotenv_values(env)["CORREO_CLAVE"] == "clave"

#!/usr/bin/env python3
"""El correo en el .env del servidor, por MailerSend (seccion 84).

    cd /opt/centauro && python3 despliegue/poner_correo.py

Escribe los renglones del correo --de donde sale, a donde llegan las
respuestas, el servidor de MailerSend y su puerto-- y pide el usuario y
la contrasena SMTP que da MailerSend (Domains -> mycentauro.lat -> SMTP).
La contrasena se pega en la terminal del servidor y no se ve al pegarla:
no queda en pantalla, ni en el historial, ni pasa por un chat.

Se puede volver a correr: el dia que MailerSend de otra contrasena, se
corre otra vez y se reemplaza. Lo demas del .env no se toca.

El interruptor (seccion 86). Poner la llave no enciende el correo del
sistema: queda CORREO_ENCENDIDO=no, se prueba con probar_correo.py --que
sale igual-- y, ya aprobada la cuenta de MailerSend, se enciende:

    python3 despliegue/poner_correo.py --encender
    python3 despliegue/poner_correo.py --apagar

Encendido antes de tiempo, con la llave equivocada o la cuenta sin
aprobar, cada aviso a un cliente gastaria sus intentos y quedaria en
fallido.

Decision de Salvador, 27 de septiembre: sale de connect@mycentauro.lat y
lo que contesten llega a cecc.notification@centauro.lat.
"""
import getpass
import io
import os
import re
import sys

ENV = ".env"

FIJOS = {
    "CORREO_DE": "Centauro Connect <connect@mycentauro.lat>",
    "CORREO_RESPONDER_A": "Centauro Connect <cecc.notification@centauro.lat>",
    "CORREO_HOST": "smtp.mailersend.net",
    "CORREO_PUERTO": "587",
}
LLAVES = ("CORREO_USUARIO", "CORREO_CLAVE")
# Llenos, el correo sale por Microsoft 365 y no por MailerSend (paso 7b).
MICROSOFT = ("CORREO_MS_TENANT", "CORREO_MS_CLIENTE", "CORREO_MS_SECRETO")

# Lo que va sin comillas. Lo demas va entre comillas simples, que docker
# compose y la aplicacion leen tal cual: sin ellas, compose tomaria un $
# de la contrasena por el nombre de una variable y la cambiaria.
SIMPLE = re.compile(r"[A-Za-z0-9._@+=/-]+")


def _clave_de(renglon: str) -> str | None:
    r = renglon.strip()
    if not r or r.startswith("#") or "=" not in r:
        return None
    return r.split("=", 1)[0].strip()


def _valores(texto: str) -> dict:
    valores = {}
    for renglon in texto.splitlines():
        clave = _clave_de(renglon)
        if clave:
            v = renglon.split("=", 1)[1].strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            valores[clave] = v
    return valores


def escrito(valor: str) -> str:
    """Como va el valor en el .env."""
    if SIMPLE.fullmatch(valor):
        return valor
    return f"'{valor}'"


def _falla(valor: str, que: str) -> str | None:
    if not valor:
        return f"{que} vino vacio."
    if any(c.isspace() for c in valor):
        return f"{que} trae espacios: se pego de mas. Copialo otra vez de MailerSend."
    if "'" in valor:
        return f"{que} trae una comilla simple; ese no se puede guardar asi."
    return None


# El comentario con que crear_env.py abria el correo, cuando iba a salir
# por Microsoft 365. Se cambia para que no diga lo que ya no es.
VIEJO = "# Correo, del buzon de Microsoft 365 (guia, paso 7b). Vacio = no sale nada."
NUEVO = ("# Correo, por MailerSend (guia, paso 7c). Los CORREO_MS_ son la otra "
         "forma (7b): llenos, manda Microsoft 365.")


def nuevo_texto(actual: str, poner: dict) -> str:
    """El .env con esos renglones puestos: donde ya estaban, en su lugar;
    los que faltan, al final. Un renglon repetido se queda una vez."""
    vistos = set()
    salida = []
    for renglon in actual.splitlines(keepends=True):
        if renglon.rstrip("\n") == VIEJO:
            renglon = NUEVO + "\n"
        clave = _clave_de(renglon)
        if clave in poner:
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append(f"{clave}={poner[clave]}\n")
        else:
            salida.append(renglon)
    texto = "".join(salida)
    faltan = [c for c in poner if c not in vistos]
    if faltan:
        if texto and not texto.endswith("\n"):
            texto += "\n"
        texto += "\n# Correo, por MailerSend (guia, paso 7c).\n"
        texto += "".join(f"{c}={poner[c]}\n" for c in faltan)
    return texto


INTERRUPTOR = "CORREO_ENCENDIDO"
# Lo que tiene que estar antes de encender.
PARA_ENCENDER = ("CORREO_DE", "CORREO_HOST", "CORREO_USUARIO", "CORREO_CLAVE")


def encendido(valores: dict) -> bool:
    return (valores.get(INTERRUPTOR) or "").strip().lower() in (
        "si", "s\u00ed", "yes", "true", "1")


def interruptor(encender: bool) -> int:
    """--encender o --apagar: solo el interruptor, sin tocar la llave."""
    actual = io.open(ENV, encoding="utf-8").read()
    valores = _valores(actual)
    if encender:
        faltan = [c for c in PARA_ENCENDER if not valores.get(c)]
        if faltan:
            print(f"Falta {', '.join(faltan)} en el .env. Primero la llave:\n"
                  "  python3 despliegue/poner_correo.py")
            return 1
    with io.open(ENV, "w", encoding="utf-8") as f:
        f.write(nuevo_texto(actual, {INTERRUPTOR: "si" if encender else "no"}))
    if encender:
        print("Listo: CORREO_ENCENDIDO=si. Los avisos salen desde que la "
              "aplicacion se reinicia.")
    else:
        print("Listo: CORREO_ENCENDIDO=no. Desde que la aplicacion se "
              "reinicia, los avisos esperan en la cola.")
    return 0


def main(argv=None, preguntar=input, secreto=getpass.getpass) -> int:
    if not os.path.exists(ENV):
        print("No veo el .env aqui. Corre esto desde /opt/centauro:\n"
              "  cd /opt/centauro && python3 despliegue/poner_correo.py")
        return 1
    argv = sys.argv[1:] if argv is None else argv
    if "--encender" in argv or "--apagar" in argv:
        return interruptor("--encender" in argv)

    actual = io.open(ENV, encoding="utf-8").read()
    valores = _valores(actual)

    usuario = preguntar("Usuario SMTP de MailerSend: ").strip()
    falla = _falla(usuario, "El usuario")
    if falla:
        print(f"{falla} No se toco nada.")
        return 1
    clave = secreto("Contrasena SMTP de MailerSend (no se ve al pegarla): ").strip()
    falla = _falla(clave, "La contrasena")
    if falla:
        print(f"{falla} No se toco nada.")
        return 1

    poner = dict(FIJOS)
    poner["CORREO_USUARIO"] = escrito(usuario)
    poner["CORREO_CLAVE"] = escrito(clave)
    # El interruptor no se mueve aqui: si no esta, entra apagado.
    if INTERRUPTOR not in valores:
        poner[INTERRUPTOR] = "no"

    llenos = [c for c in MICROSOFT if valores.get(c)]
    if llenos:
        r = preguntar("El .env trae los datos de Microsoft 365, y con ellos el "
                      "correo sale por Microsoft y no por MailerSend. "
                      "Los vacio? (s/n): ").strip().lower()
        if r not in ("s", "si", "sí"):
            print("No se toco nada.")
            return 1
        for c in MICROSOFT:
            poner[c] = ""

    # Se reescribe el mismo archivo: se queda con su dueno y con sus
    # permisos (solo lo lee quien lo creo).
    with io.open(ENV, "w", encoding="utf-8") as f:
        f.write(nuevo_texto(actual, poner))

    print("Listo. El correo quedo en el .env:")
    for c, v in FIJOS.items():
        print(f"  {c}={v}")
    print(f"  CORREO_USUARIO={usuario[:3]}... (guardado)")
    print("  CORREO_CLAVE: guardada; no se imprime.")
    if llenos:
        print("  Los datos de Microsoft 365 quedaron vacios.")
    if encendido(valores):
        print("El correo ya estaba encendido: la llave nueva vale desde que "
              "la aplicacion se reinicia.")
    else:
        print("El correo del sistema sigue apagado. Primero la prueba "
              "(probar_correo.py); ya aprobada la cuenta de MailerSend, se "
              "enciende con --encender (guia, paso 7c).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

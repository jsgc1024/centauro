#!/usr/bin/env python3
"""El correo en el .env del servidor, por Amazon SES (secciones 84, 91 y 93).

    cd /opt/centauro && python3 despliegue/poner_correo.py

Escribe los renglones del correo --de donde sale, a donde llegan las
respuestas, el servidor de Amazon y su puerto-- y pide el usuario y la
contrasena SMTP que da Amazon (SES -> SMTP settings -> Create SMTP
credentials). La contrasena se pega en la terminal del servidor y no se
ve al pegarla: no queda en pantalla, ni en el historial, ni pasa por un
chat.

MailerSend rechazo la cuenta dos veces (seccion 91) y Postmark no acepto
el dominio (seccion 93); Salvador escogio Amazon SES. La cuenta es de
Ohio (us-east-2), la region en la que abre su consola: Amazon no manda
correo desde su region de Mexico. Si algun dia es otra region, se dice:

    python3 despliegue/poner_correo.py --region=us-east-1

Los otros dos se quedan como la otra forma: Postmark con su sola llave y
MailerSend con usuario y contrasena:

    python3 despliegue/poner_correo.py --postmark
    python3 despliegue/poner_correo.py --mailersend

Se puede volver a correr: el dia que haya otra llave, se corre otra vez
y se reemplaza. Lo demas del .env no se toca.

El interruptor (seccion 86). Poner la llave no enciende el correo del
sistema: queda CORREO_ENCENDIDO=no, se prueba con probar_correo.py --que
sale igual-- y, ya aprobado el acceso a produccion de Amazon, se enciende:

    python3 despliegue/poner_correo.py --encender
    python3 despliegue/poner_correo.py --apagar

Por etapas (decision de Salvador, 29 sep). Primero solo la gente de la
empresa; lo de los clientes espera en la cola. Despues, todos:
    python3 despliegue/poner_correo.py --solo-internos
    python3 despliegue/poner_correo.py --a-todos
Las dos encienden el correo. Con los datos de Microsoft 365 en el .env
(paso 7b) no piden los del servicio de envio.

Encendido antes de tiempo, con la llave equivocada o la cuenta todavia a
prueba, cada aviso a un cliente gastaria sus intentos y quedaria en
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
    "CORREO_PUERTO": "587",
}

# Los servicios de envio que se saben poner. Amazon y MailerSend dan un
# usuario y una contrasena; Postmark, una sola llave que va de usuario y
# de contrasena. Los tres hablan SMTP por el 587: Google Cloud no deja
# salir el 25. El servidor de Amazon es uno por region.
PROVEEDORES = {
    "amazon": {"nombre": "Amazon SES",
               "host": "email-smtp.{region}.amazonaws.com",
               "donde": "SES -> SMTP settings -> Create SMTP credentials",
               "una_llave": False},
    "postmark": {"nombre": "Postmark", "host": "smtp.postmarkapp.com",
                 "donde": "Servers -> Centauro Connect -> API Tokens",
                 "una_llave": True},
    "mailersend": {"nombre": "MailerSend", "host": "smtp.mailersend.net",
                   "donde": "Domains -> mycentauro.lat -> SMTP",
                   "una_llave": False},
}
# La region de la cuenta de Amazon (seccion 93): Ohio, la que abre su
# consola. Las identidades, la llave SMTP y el acceso a produccion son de
# esa region y de ninguna otra.
REGION = "us-east-2"
FORMA_REGION = re.compile(r"[a-z]{2}(-gov)?-[a-z]+-[0-9]")
LLAVES = ("CORREO_USUARIO", "CORREO_CLAVE")
# Llenos, el correo sale por Microsoft 365 y no por el servicio de envio
# (paso 7b).
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


def _falla(valor: str, que: str, de: str) -> str | None:
    if not valor:
        return f"{que} vino vacio."
    if any(c.isspace() for c in valor):
        return f"{que} trae espacios: se pego de mas. Copialo otra vez de {de}."
    if "'" in valor:
        return f"{que} trae una comilla simple; ese no se puede guardar asi."
    return None


# El comentario con que abria el correo en el .env. Los viejos se cambian
# por este, para que no diga lo que ya no es: el de cuando iba a salir por
# Microsoft 365 (lo escribia crear_env.py) y los de MailerSend.
VIEJOS = (
    "# Correo, del buzon de Microsoft 365 (guia, paso 7b). Vacio = no sale nada.",
    "# Correo, por MailerSend (guia, paso 7c). Los CORREO_MS_ son la otra "
    "forma (7b): llenos, manda Microsoft 365.",
    "# Correo, por MailerSend (guia, paso 7c).",
)
NUEVO = ("# Correo, por un servicio de envio (guia, paso 7c). Los CORREO_MS_ son "
         "la otra forma (7b): llenos, manda Microsoft 365.")


def nuevo_texto(actual: str, poner: dict) -> str:
    """El .env con esos renglones puestos: donde ya estaban, en su lugar;
    los que faltan, al final. Un renglon repetido se queda una vez."""
    vistos = set()
    salida = []
    for renglon in actual.splitlines(keepends=True):
        if renglon.rstrip("\n") in VIEJOS:
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
        if NUEVO not in texto:
            texto += "\n" + NUEVO + "\n"
        texto += "".join(f"{c}={poner[c]}\n" for c in faltan)
    return texto


INTERRUPTOR = "CORREO_ENCENDIDO"
# Lo que tiene que estar antes de encender: de donde sale y por donde,
# el servicio de envio (SMTP) o Microsoft 365.
PARA_ENCENDER = ("CORREO_DE", "CORREO_HOST", "CORREO_USUARIO", "CORREO_CLAVE")
# Las etapas (29 sep): primero solo la gente de la empresa, despues los
# clientes tambien.
ETAPA = "CORREO_SOLO_INTERNOS"


def faltan_para_encender(valores: dict) -> list:
    """Lo que falta para encender. Con los tres de Microsoft llenos no se
    piden los del servicio de envio: manda Microsoft (seccion 67)."""
    if not valores.get("CORREO_DE"):
        return ["CORREO_DE"]
    if all(valores.get(c) for c in MICROSOFT):
        return []
    return [c for c in PARA_ENCENDER if not valores.get(c)]


def encendido(valores: dict) -> bool:
    return (valores.get(INTERRUPTOR) or "").strip().lower() in (
        "si", "sí", "yes", "true", "1")


def interruptor(encender: bool) -> int:
    """--encender o --apagar: solo el interruptor, sin tocar la llave."""
    actual = io.open(ENV, encoding="utf-8").read()
    valores = _valores(actual)
    if encender:
        faltan = faltan_para_encender(valores)
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


def etapa(solo_internos: bool) -> int:
    """--solo-internos o --a-todos: enciende el correo y dice a quien.

    Decision de Salvador, 29 sep. Primera etapa, --solo-internos: sale lo
    de consultores, central, personal y la gente de la oficina; lo de los
    clientes espera en la cola y, pasado su tiempo, se vence sin salir.
    Segunda etapa, --a-todos: sale tambien a los clientes."""
    actual = io.open(ENV, encoding="utf-8").read()
    faltan = faltan_para_encender(_valores(actual))
    if faltan:
        print(f"Falta {', '.join(faltan)} en el .env: el correo no se "
              "enciende. No se toco nada.")
        return 1
    with io.open(ENV, "w", encoding="utf-8") as f:
        f.write(nuevo_texto(actual, {INTERRUPTOR: "si",
                                     ETAPA: "si" if solo_internos else "no"}))
    if solo_internos:
        print("Listo: correo encendido SOLO para la empresa (consultores, "
              "central, personal y oficina). Lo de los clientes espera. "
              "Vale desde que la aplicacion se reinicia.")
    else:
        print("Listo: correo encendido para TODOS, clientes incluidos. "
              "Vale desde que la aplicacion se reinicia.")
    return 0


def _pedir_llave(p: dict, preguntar, secreto) -> tuple | None:
    """(usuario, contrasena), o None si lo que se pego no sirve."""
    nombre = p["nombre"]
    if p["una_llave"]:
        llave = secreto(f"Server API Token de {nombre} ({p['donde']}); "
                        "no se ve al pegarlo: ").strip()
        falla = _falla(llave, "La llave", nombre)
        if falla:
            print(f"{falla} No se toco nada.")
            return None
        return llave, llave
    usuario = preguntar(f"Usuario SMTP de {nombre} ({p['donde']}): ").strip()
    falla = _falla(usuario, "El usuario", nombre)
    if falla:
        print(f"{falla} No se toco nada.")
        return None
    clave = secreto(f"Contrasena SMTP de {nombre} (no se ve al pegarla): ").strip()
    falla = _falla(clave, "La contrasena", nombre)
    if falla:
        print(f"{falla} No se toco nada.")
        return None
    return usuario, clave


def elegir(argv: list) -> dict | None:
    """El servicio de envio, con su servidor ya escrito. Amazon, salvo que
    se pida otro; su region, la de la cuenta, salvo que se diga otra."""
    if "--postmark" in argv:
        return dict(PROVEEDORES["postmark"])
    if "--mailersend" in argv:
        return dict(PROVEEDORES["mailersend"])
    p = dict(PROVEEDORES["amazon"])
    region = REGION
    for arg in argv:
        if arg.startswith("--region="):
            region = arg.split("=", 1)[1].strip().lower()
    if not FORMA_REGION.fullmatch(region):
        print(f"La region «{region}» no tiene forma de region de Amazon "
              "(como us-east-2). No se toco nada.")
        return None
    p["host"] = p["host"].format(region=region)
    return p


def main(argv=None, preguntar=input, secreto=getpass.getpass) -> int:
    if not os.path.exists(ENV):
        print("No veo el .env aqui. Corre esto desde /opt/centauro:\n"
              "  cd /opt/centauro && python3 despliegue/poner_correo.py")
        return 1
    argv = sys.argv[1:] if argv is None else argv
    if "--solo-internos" in argv or "--a-todos" in argv:
        return etapa("--solo-internos" in argv)
    if "--encender" in argv or "--apagar" in argv:
        return interruptor("--encender" in argv)
    p = elegir(argv)
    if p is None:
        return 1

    actual = io.open(ENV, encoding="utf-8").read()
    valores = _valores(actual)

    llave = _pedir_llave(p, preguntar, secreto)
    if not llave:
        return 1
    usuario, clave = llave

    poner = dict(FIJOS)
    poner["CORREO_HOST"] = p["host"]
    poner["CORREO_USUARIO"] = escrito(usuario)
    poner["CORREO_CLAVE"] = escrito(clave)
    # El interruptor no se mueve aqui: si no esta, entra apagado.
    if INTERRUPTOR not in valores:
        poner[INTERRUPTOR] = "no"

    llenos = [c for c in MICROSOFT if valores.get(c)]
    if llenos:
        r = preguntar("El .env trae los datos de Microsoft 365, y con ellos el "
                      f"correo sale por Microsoft y no por {p['nombre']}. "
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

    print(f"Listo. El correo quedo en el .env, por {p['nombre']}:")
    for c in ("CORREO_DE", "CORREO_RESPONDER_A"):
        print(f"  {c}={FIJOS[c]}")
    print(f"  CORREO_HOST={p['host']}")
    print(f"  CORREO_PUERTO={FIJOS['CORREO_PUERTO']}")
    if p["una_llave"]:
        # La llave es el usuario y la contrasena: no se imprime nada de ella.
        print("  La llave: guardada como usuario y contrasena; no se imprime.")
    else:
        print(f"  CORREO_USUARIO={usuario[:3]}... (guardado)")
        print("  CORREO_CLAVE: guardada; no se imprime.")
    if llenos:
        print("  Los datos de Microsoft 365 quedaron vacios.")
    if encendido(valores):
        print("El correo ya estaba encendido: la llave nueva vale desde que "
              "la aplicacion se reinicia.")
    else:
        print(f"El correo del sistema sigue apagado. Primero la prueba "
              f"(probar_correo.py); ya aprobada la cuenta de {p['nombre']}, se "
              "enciende con --encender (guia, paso 7c).")
        if p["nombre"] == "Amazon SES":
            print("Mientras Amazon no apruebe el acceso a produccion, la prueba "
                  "va a success@simulator.amazonses.com o a un correo "
                  "verificado en SES.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

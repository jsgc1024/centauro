#!/usr/bin/env python3
"""Sube un respaldo al deposito de Google Cloud Storage, sin llaves.

    python3 backend/subir_a_google.py /var/respaldos/centauro/centauro-20260926-0230.dump \\
        gs://centauro-respaldos-XYZ/postgres

Lo llama `despliegue/respaldo.sh` (seccion 68). Corre en el servidor,
fuera de los contenedores, con el python3 de Ubuntu y la biblioteca
estandar: no hay nada que instalar.

**No lleva llaves.** El permiso se lo da Google a la maquina --su cuenta,
`centauro-vm`-- y se pide cada vez al servidor de metadatos, que solo
contesta desde la propia maquina. Esa cuenta puede crear y leer en el
deposito, no borrar; y el deposito no deja borrar ni reemplazar nada
antes de 14 dias. Si alguien entra al servidor no se lleva el historial
de respaldos, que es justo lo que se usaria para recuperarse.

**Sube por partes** (subida reanudable): si se corta a la mitad, pregunta
hasta donde llego y sigue de ahi. Y nunca escribe encima de un respaldo
que ya exista.

**Al final pregunta que quedo del otro lado** --tamano y md5-- y lo compara
con el archivo. Una subida que dijo "ok" y llego cortada es un respaldo
que no existe.

Sale con 0 si el respaldo quedo completo alla; con 1 si no.
"""
import base64
import hashlib
import http.client
import json
import os
import sys
import time
import urllib.parse

# Las dos direcciones se pueden cambiar solo para las pruebas.
METADATOS = os.environ.get(
    "CENTAURO_METADATOS", "http://metadata.google.internal/computeMetadata/v1")
STORAGE = os.environ.get("CENTAURO_STORAGE", "https://storage.googleapis.com")

PARTE = 16 * 1024 * 1024      # Google pide multiplos de 256 KiB
INTENTOS = 5


class Fallo(Exception):
    """El respaldo no quedo alla. El mensaje dice por que."""


def pedir(metodo: str, url: str, cuerpo: bytes | None = None,
          cabeceras: dict | None = None, espera: int = 120):
    partes = urllib.parse.urlsplit(url)
    clase = (http.client.HTTPSConnection if partes.scheme == "https"
             else http.client.HTTPConnection)
    con = clase(partes.netloc, timeout=espera)
    try:
        ruta = partes.path + ("?" + partes.query if partes.query else "")
        con.request(metodo, ruta, body=cuerpo, headers=cabeceras or {})
        r = con.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        con.close()


def permiso() -> dict:
    """El permiso de la maquina, recien pedido. Dura una hora."""
    status, _, cuerpo = pedir(
        "GET", METADATOS + "/instance/service-accounts/default/token",
        cabeceras={"Metadata-Flavor": "Google"}, espera=10)
    if status != 200:
        raise Fallo(f"el servidor de metadatos contesto {status}: esta "
                    "maquina no tiene cuenta de Google para el deposito")
    return {"Authorization": "Bearer " + json.loads(cuerpo)["access_token"]}


def partir(destino: str) -> tuple[str, str]:
    """gs://deposito/carpeta -> (deposito, carpeta)."""
    if not destino.startswith("gs://"):
        raise Fallo(f"'{destino}' no es un destino gs://deposito/carpeta")
    deposito, _, carpeta = destino[len("gs://"):].partition("/")
    if not deposito:
        raise Fallo(f"'{destino}' no dice el deposito")
    return deposito, carpeta.strip("/")


def huella(ruta: str) -> str:
    """El md5 del archivo, en base64: como lo guarda Google."""
    md5 = hashlib.md5()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            md5.update(bloque)
    return base64.b64encode(md5.digest()).decode()


def _recibido(cabeceras: dict) -> int:
    """Cuantos bytes dice Google que ya tiene ("Range: bytes=0-1234")."""
    rango = cabeceras.get("range")
    return int(rango.rsplit("-", 1)[1]) + 1 if rango else 0


def _hasta_donde(sesion: str, tamano: int, cab: dict) -> int:
    """Despues de un corte: hasta donde llego la subida."""
    status, h, _ = pedir("PUT", sesion, b"", {
        **cab, "Content-Range": f"bytes */{tamano}", "Content-Length": "0"})
    if status in (200, 201):
        return tamano
    if status == 308:
        return _recibido(h)
    raise Fallo(f"no se pudo saber hasta donde llego la subida ({status})")


def subir(ruta: str, destino: str, dormir=time.sleep) -> dict:
    deposito, carpeta = partir(destino)
    base = os.path.basename(ruta)
    nombre = f"{carpeta}/{base}" if carpeta else base
    tamano = os.path.getsize(ruta)
    if tamano == 0:
        raise Fallo(f"{ruta} esta vacio: eso no se sube")
    cab = permiso()
    en_deposito = urllib.parse.quote(deposito, safe="")

    # 1. Se abre la subida. ifGenerationMatch=0 quiere decir "solo si no
    #    existe": un respaldo nunca se escribe encima de otro.
    q = urllib.parse.urlencode({"uploadType": "resumable", "name": nombre,
                                "ifGenerationMatch": "0"})
    status, h, cuerpo = pedir(
        "POST", f"{STORAGE}/upload/storage/v1/b/{en_deposito}/o?{q}", b"",
        {**cab, "X-Upload-Content-Type": "application/octet-stream",
         "X-Upload-Content-Length": str(tamano), "Content-Length": "0"})
    if status == 412:
        raise Fallo(f"ya existe {nombre} en el deposito: no se escribe encima")
    if status != 200 or "location" not in h:
        raise Fallo(f"Google no abrio la subida ({status}): {cuerpo[:300]!r}")
    sesion = h["location"]

    # 2. Por partes. Si una se corta, se pregunta hasta donde llego.
    enviado, fallas = 0, 0
    with open(ruta, "rb") as f:
        while enviado < tamano:
            f.seek(enviado)
            parte = f.read(PARTE)
            try:
                status, h, cuerpo = pedir("PUT", sesion, parte, {
                    **cab,
                    "Content-Range": f"bytes {enviado}-{enviado + len(parte) - 1}/{tamano}",
                    "Content-Length": str(len(parte))})
            except (OSError, http.client.HTTPException) as e:
                status, h, cuerpo = None, {}, str(e).encode()
            if status in (200, 201):
                enviado = tamano
            elif status == 308:
                enviado = _recibido(h)
            else:
                fallas += 1
                if fallas > INTENTOS:
                    raise Fallo(f"la subida fallo {fallas} veces; la ultima: "
                                f"{status} {cuerpo[:200]!r}")
                if status == 401:
                    cab = permiso()          # el permiso dura una hora
                dormir(2 ** fallas)
                enviado = _hasta_donde(sesion, tamano, cab)

    # 3. Que quedo alla. El tamano y el md5 los calcula Google con lo que
    #    recibio, no con lo que se le dijo que iba a llegar.
    en_nombre = urllib.parse.quote(nombre, safe="")
    status, _, cuerpo = pedir(
        "GET", f"{STORAGE}/storage/v1/b/{en_deposito}/o/{en_nombre}", None, cab)
    if status != 200:
        raise Fallo(f"no se pudo preguntar que llego ({status}): {cuerpo[:200]!r}")
    objeto = json.loads(cuerpo)
    local = huella(ruta)
    if str(objeto.get("size")) != str(tamano) or objeto.get("md5Hash") != local:
        raise Fallo(f"alla pesa {objeto.get('size')} con md5 "
                    f"{objeto.get('md5Hash')}; aqui {tamano} con {local}. "
                    "La copia no sirve.")
    return {"objeto": f"gs://{deposito}/{nombre}", "bytes": tamano, "md5": local}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("Uso: subir_a_google.py ARCHIVO gs://deposito/carpeta")
        return 2
    try:
        r = subir(*argv)
    except (Fallo, OSError, ValueError, KeyError) as e:
        print(f"ERROR: {e}")
        return 1
    print(f"Subido y verificado del otro lado: {r['objeto']} "
          f"({r['bytes']} bytes, md5 {r['md5']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

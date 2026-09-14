"""Identidad grafica de la empresa en los documentos.

El logo se toma de backend/assets/logo.* y se incrusta en el documento,
para que la hoja se pueda guardar, imprimir o mandar por correo sin
depender de que cargue una imagen desde internet.

El formato se reconoce por el contenido del archivo, no por su nombre:
es muy comun bajar un .webp de una pagina y guardarlo como logo.png.
"""
import base64
import struct
from functools import lru_cache
from pathlib import Path

CARPETA = Path(__file__).resolve().parent.parent / "assets"
NOMBRES = ["logo.svg", "logo.png", "logo.jpg", "logo.jpeg", "logo.webp"]


def _huella() -> tuple:
    """Cambia cuando se reemplaza el archivo del logo."""
    for nombre in NOMBRES:
        archivo = CARPETA / nombre
        if archivo.is_file():
            e = archivo.stat()
            return (nombre, e.st_mtime_ns, e.st_size)
    return ()


def _reconocer(datos: bytes) -> tuple[str, bool] | None:
    """Devuelve (tipo MIME, esta completo) mirando los bytes del archivo.

    Un archivo a medias no se incrusta: mejor el nombre en texto que un
    hueco en el documento del cliente.
    """
    if len(datos) < 16:
        return None

    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", datos[-8:] == b"IEND\xaeB`\x82"

    if datos[:2] == b"\xff\xd8":
        return "image/jpeg", datos[-2:] == b"\xff\xd9"

    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        declarado = struct.unpack("<I", datos[4:8])[0] + 8
        return "image/webp", len(datos) >= declarado

    cabeza = datos[:512].lstrip()
    if cabeza[:5] == b"<?xml" or cabeza[:4] == b"<svg":
        return "image/svg+xml", b"</svg>" in datos[-512:]

    if datos[:4] == b"GIF8":
        return "image/gif", datos[-1:] == b"\x3b"

    return None


@lru_cache(maxsize=4)
def _leer(huella: tuple) -> str | None:
    for nombre in NOMBRES:
        archivo = CARPETA / nombre
        if not archivo.is_file():
            continue
        datos = archivo.read_bytes()
        reconocido = _reconocer(datos)
        if not reconocido:
            return None
        tipo, completo = reconocido
        if not completo:
            return None
        return f"data:{tipo};base64,{base64.b64encode(datos).decode()}"
    return None


def logo_incrustado() -> str | None:
    """El logo como data URI, o None si no hay archivo o esta incompleto."""
    return _leer(_huella())


def olvidar_logo() -> None:
    _leer.cache_clear()


def diagnostico() -> dict:
    """Para saber por que no sale el logo, sin adivinar."""
    for nombre in NOMBRES:
        archivo = CARPETA / nombre
        if not archivo.is_file():
            continue
        datos = archivo.read_bytes()
        reconocido = _reconocer(datos)
        return {"archivo": nombre, "bytes": len(datos),
                "formato": reconocido[0] if reconocido else "no reconocido",
                "completo": bool(reconocido and reconocido[1]),
                "se_incrusta": bool(reconocido and reconocido[1])}
    return {"archivo": None, "se_incrusta": False,
            "nota": "No hay logo en backend/assets"}

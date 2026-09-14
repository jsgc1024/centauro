"""Imagenes que se guardan dentro del documento, no como enlace.

La senal de identificacion y el comprobante de una compra se imprimen o
se mandan por correo, muchas veces desde un aeropuerto con mala red. Si
fueran un enlace, el dia que el enlace no cargue la hoja sale vacia. Por
eso viajan como data URI, dentro del propio registro.
"""
import base64

from fastapi import HTTPException, UploadFile

TIPOS_DE_IMAGEN = {"image/png": ".png", "image/jpeg": ".jpg",
                   "image/webp": ".webp", "image/svg+xml": ".svg"}
LIMITE = 3 * 1024 * 1024      # 3 MB


async def leer(archivo: UploadFile) -> str:
    """Devuelve el data URI, o revienta con un mensaje que se entiende."""
    if archivo.content_type not in TIPOS_DE_IMAGEN:
        raise HTTPException(400, {
            "mensaje": "Formato no soportado",
            "recibido": archivo.content_type,
            "aceptados": sorted(TIPOS_DE_IMAGEN),
        })

    contenido = await archivo.read()
    if len(contenido) > LIMITE:
        raise HTTPException(400, f"La imagen pasa de 3 MB "
                                 f"({len(contenido) / 1024 / 1024:.1f} MB)")

    return (f"data:{archivo.content_type};base64,"
            f"{base64.b64encode(contenido).decode()}")

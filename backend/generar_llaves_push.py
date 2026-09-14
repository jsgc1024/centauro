#!/usr/bin/env python3
"""Genera el par de llaves para los avisos al telefono, una sola vez.

    docker compose exec -T api python generar_llaves_push.py

Escribe las dos en el .env y solo imprime la publica. La privada no se
enseña en pantalla a proposito: es lo unico que impide que alguien mas
le mande avisos a tu equipo, y lo que aparece en una terminal termina en
el historial, en una captura o en un chat.

Si ya existen en el .env, no las toca: regenerarlas deja mudos todos los
telefonos que ya se suscribieron, y nadie se entera hasta el dia que un
aviso importante no llega.
"""
import base64
import io
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ENV = "/code/.env"


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def main() -> int:
    actual = io.open(ENV, encoding="utf-8").read() if os.path.exists(ENV) else ""
    if "VAPID_PRIVATE=" in actual and "VAPID_PUBLIC=" in actual:
        print("Ya hay llaves en el .env. No se tocan:\n"
              "regenerarlas deja mudos todos los telefonos que ya se\n"
              "suscribieron, y nadie se entera hasta que un aviso no llega.\n"
              "Si de verdad quieres otras, borra a mano las dos lineas\n"
              "VAPID_PUBLIC y VAPID_PRIVATE del .env y vuelve a correr esto.")
        return 0

    llave = ec.generate_private_key(ec.SECP256R1())
    privada = _b64(llave.private_numbers().private_value.to_bytes(32, "big"))
    publica = _b64(llave.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint))

    with io.open(ENV, "a", encoding="utf-8") as f:
        if actual and not actual.endswith("\n"):
            f.write("\n")
        f.write(f"VAPID_PUBLIC={publica}\n")
        f.write(f"VAPID_PRIVATE={privada}\n")

    print("Listo. Las dos llaves quedaron en el .env.")
    print(f"\nLa publica (esta si es publica, la reparte la app):\n{publica}")
    print("\nLa privada no se imprime a proposito. Reinicia la api:\n"
          "  docker compose restart api worker beat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

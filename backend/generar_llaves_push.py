#!/usr/bin/env python3
"""Genera el par de llaves para los avisos al telefono, una sola vez.

En la maquina de desarrollo:

    docker compose exec -T api python generar_llaves_push.py

En el servidor, con el .env del servidor montado encima (seccion 68):

    docker compose -f docker-compose.prod.yml run --rm \\
        -v "$PWD/.env:/code/.env" api python generar_llaves_push.py

En produccion el contenedor corre la imagen construida, sin la carpeta
montada: sin el `-v`, las llaves se escribian en un .env que solo existia
dentro de ese contenedor, la app nunca las veia y se perdian en la
siguiente actualizacion.

Escribe las dos en el .env y solo imprime la publica. La privada no se
enseña en pantalla a proposito: es lo unico que impide que alguien mas
le mande avisos a tu equipo, y lo que aparece en una terminal termina en
el historial, en una captura o en un chat.

Si ya existen en el .env, no las toca: regenerarlas deja mudos todos los
telefonos que ya se suscribieron, y nadie se entera hasta el dia que un
aviso importante no llega. Un renglon `VAPID_PUBLIC=` vacio no cuenta
como llave: se llena.
"""
import base64
import io
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ENV = "/code/.env"
CLAVES = ("VAPID_PUBLIC", "VAPID_PRIVATE")


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def _clave_de(renglon: str) -> str:
    return renglon.split("=", 1)[0].strip() if "=" in renglon else ""


def _valores(texto: str) -> dict:
    """El ultimo valor de cada llave, como lo leeria la app."""
    valores = {}
    for renglon in texto.splitlines():
        clave = _clave_de(renglon)
        if clave in CLAVES:
            valores[clave] = renglon.split("=", 1)[1].strip()
    return valores


def _es_produccion() -> bool:
    try:
        from app.config import es_desarrollo, settings
    except Exception:
        return False
    return not es_desarrollo(settings)


def main() -> int:
    if not os.path.exists(ENV) and _es_produccion():
        print("No veo el .env del servidor, y sin el las llaves se quedarian\n"
              "dentro de este contenedor: la app no las veria y se perderian\n"
              "en la siguiente actualizacion. Correlo asi, desde /opt/centauro:\n"
              "  docker compose -f docker-compose.prod.yml run --rm \\\n"
              "    -v \"$PWD/.env:/code/.env\" api python generar_llaves_push.py")
        return 1

    actual = io.open(ENV, encoding="utf-8").read() if os.path.exists(ENV) else ""
    valores = _valores(actual)
    llenas = [c for c in CLAVES if valores.get(c)]
    if len(llenas) == 2:
        print("Ya hay llaves en el .env. No se tocan:\n"
              "regenerarlas deja mudos todos los telefonos que ya se\n"
              "suscribieron, y nadie se entera hasta que un aviso no llega.\n"
              "Si de verdad quieres otras, borra a mano las dos lineas\n"
              "VAPID_PUBLIC y VAPID_PRIVATE del .env y vuelve a correr esto.")
        return 0
    if llenas:
        print(f"En el .env hay {llenas[0]} pero no su pareja. No se toca nada:\n"
              "una llave sin la otra no sirve, y generar un par nuevo encima\n"
              "de una que ya se repartio deja mudos a esos telefonos. Revisa\n"
              "a mano de donde salio esa linea.")
        return 1

    llave = ec.generate_private_key(ec.SECP256R1())
    privada = _b64(llave.private_numbers().private_value.to_bytes(32, "big"))
    publica = _b64(llave.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint))

    # Los renglones vacios de las dos llaves se quitan y las buenas van al
    # final: si se agregaran debajo, quedarian dos de cada una en el
    # archivo. Se reescribe el mismo archivo --no uno nuevo que lo
    # reemplace-- porque en el servidor esta montado encima del
    # contenedor, y montado se reescribe, no se cambia por otro.
    renglones = [r for r in actual.splitlines(keepends=True)
                 if _clave_de(r) not in CLAVES]
    texto = "".join(renglones)
    if texto and not texto.endswith("\n"):
        texto += "\n"
    texto += f"VAPID_PUBLIC={publica}\nVAPID_PRIVATE={privada}\n"
    with io.open(ENV, "w", encoding="utf-8") as f:
        f.write(texto)

    print("Listo. Las dos llaves quedaron en el .env.")
    print(f"\nLa publica (esta si es publica, la reparte la app):\n{publica}")
    print("\nLa privada no se imprime a proposito. Para que la app las tome,\n"
          "los contenedores se vuelven a crear (restart no relee el .env):\n"
          "  en el servidor:    docker compose -f docker-compose.prod.yml up -d api worker beat\n"
          "  en desarrollo:     docker compose restart api worker beat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

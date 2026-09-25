#!/usr/bin/env python3
"""Manda un correo de prueba con lo que dice el .env (seccion 67).

En el servidor, despues de poner el correo en el .env y reiniciar:

    docker compose -f docker-compose.prod.yml run --rm api python probar_correo.py tu@correo.com

Dice por donde salio --Microsoft 365 o SMTP-- y, si no salio, lo que
contesto el proveedor: ahi se lee si fue el secreto, el permiso sobre el
buzon o la direccion. No imprime llaves ni secretos.
"""
import sys

from app import correo
from app.config import settings


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("Uso: python probar_correo.py destino@correo.com")
        return 2
    destino = sys.argv[1]
    if not correo.configurado():
        print("El correo no esta configurado: falta CORREO_DE, o los datos "
              "de Microsoft 365 (CORREO_MS_TENANT, CORREO_MS_CLIENTE y "
              "CORREO_MS_SECRETO), o el SMTP.")
        return 1
    por = ("Microsoft 365" if correo.por_microsoft()
           else f"SMTP ({settings.correo_host})")
    try:
        correo.entregar(
            destino, "Centauro: correo de prueba",
            "Si lees esto, el correo del sistema ya sale.\n\n"
            f"Salio por {por}, desde {settings.correo_de}.")
    except Exception as falla:               # noqa: BLE001
        print(f"No salio por {por}: {falla}")
        return 1
    print(f"Lo acepto {por}: sale desde {settings.correo_de} hacia "
          f"{destino}. Revisa esa bandeja, y la de correo no deseado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

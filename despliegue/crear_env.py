#!/usr/bin/env python3
"""El .env del servidor, la primera vez (seccion 68).

    cd /opt/centauro && python3 despliegue/crear_env.py

Genera aqui mismo las tres cosas que nadie tiene que saber --la
contrasena de Postgres, la de Redis y la clave de sesion-- y deja lo
demas vacio, para pegarlo con nano cuando llegue cada llave. Nada de lo
generado sale en pantalla ni queda en el historial de la terminal: se
escribe directo al archivo, que solo puede leer quien lo creo.

Si ya hay un .env, no lo toca. Regenerar las contrasenas de una base con
datos la deja sin poder abrirse.

Asi se creo el del servidor de Google el 25 de septiembre de 2026.
"""
import os
import secrets
import sys

ENV = ".env"


def plantilla(pg: str, rd: str, sk: str) -> str:
    return f"""# Centauro en produccion. Este archivo no sale del servidor: no va al
# repositorio, ni a un correo, ni a un chat. Se edita con nano.

# Lo del servidor. Se genero aqui mismo y nadie tiene que saberlo.
DOMINIO=centauro.cc
URL_PUBLICA=https://centauro.cc
APP_ENV=produccion
POSTGRES_PASSWORD={pg}
REDIS_PASSWORD={rd}
DATABASE_URL=postgresql+psycopg://centauro:{pg}@db:5432/centauro
REDIS_URL=redis://:{rd}@redis:6379/0
SECRET_KEY={sk}
TELEFONO_CENTRAL=+525550221022

# Google Maps: la llave nueva, del proyecto de Centauro.
GOOGLE_MAPS_KEY=

# Avisos al telefono. Las dos llaves las escribe generar_llaves_push.py.
VAPID_CONTACTO=mailto:operaciones@centauro.lat

# Correo, del buzon de Microsoft 365 (guia, paso 7b). Vacio = no sale nada.
CORREO_DE=Centauro <ai@centauro.lat>
CORREO_MS_TENANT=
CORREO_MS_CLIENTE=
CORREO_MS_SECRETO=

# Odoo. Vacio = no se lee ni se manda nada.
ODOO_BASE=
ODOO_API_KEY=
ODOO_URL=
ODOO_TOKEN=

# Pegasus, el GPS de las unidades. Vacio = no se lee nada.
PEGASUS_SITIO=
PEGASUS_USUARIO=
PEGASUS_CLAVE=
PEGASUS_SECRETO_AVISO=
"""


def main() -> int:
    if os.path.exists(ENV):
        print("Ya hay un .env aqui: no lo toco.")
        return 1
    texto = plantilla(secrets.token_urlsafe(32), secrets.token_urlsafe(32),
                      secrets.token_urlsafe(48))
    fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(texto)
    print("Listo: .env creado; solo tu usuario lo puede leer. "
          "Las contrasenas no se imprimen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

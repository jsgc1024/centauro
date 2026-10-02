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

# Las dos puertas (seccion 71): la consola y la app del personal de
# seguridad. URL_PUBLICA es la de la consola, con https.
DOMINIO=mycentauro.lat
DOMINIO_CAMPO=appep.mycentauro.lat
URL_PUBLICA=https://mycentauro.lat

# Lo del servidor. Se genero aqui mismo y nadie tiene que saberlo.
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

# Correo, por Amazon SES (guia, paso 7c; seccion 93). La llave la pone
# poner_correo.py: el usuario y la contrasena SMTP de Amazon. El correo
# del sistema sale hasta CORREO_ENCENDIDO=si, despues de probar la llave
# (seccion 86). Los CORREO_MS_ son la otra forma (paso 7b): llenos, manda
# Microsoft 365.
CORREO_ENCENDIDO=no
CORREO_DE=Centauro Connect <connect@mycentauro.lat>
CORREO_RESPONDER_A=Centauro Connect <cecc.notification@centauro.lat>
CORREO_HOST=email-smtp.us-east-2.amazonaws.com
CORREO_PUERTO=587
CORREO_USUARIO=
CORREO_CLAVE=
CORREO_MS_TENANT=
CORREO_MS_CLIENTE=
CORREO_MS_SECRETO=

# Odoo. Vacio = no se lee ni se manda nada.
ODOO_BASE=
ODOO_API_KEY=
ODOO_URL=
ODOO_TOKEN=

# La factura en Odoo (secciones 116 y 117): la llave con que Connect crea
# la prefactura en borrador, y nada mas. Vacia = no se manda nada.
ODOO_FACTURACION_API_KEY=

# Lo de Odoo por pais (secciones 77, 112, 121 y 123). Vienen con su valor
# de siempre: solo se cambian si en Odoo se llaman distinto. Los campos
# del CPF y la CNH se buscan por su nombre visible; aqui va el tecnico
# si hace falta.
ODOO_ETIQUETA_CLIENTES=Protección ejecutiva
ODOO_CAMPO_IMPLANTADOS=x_studio_lista_de_implantados
ODOO_CATEGORIA_PRODUCTOS=Protección Ejecutiva
ODOO_PREFIJO_LISTAS=PE ·
ODOO_IDIOMA=es_MX
ODOO_CATEGORIA_PRODUCTOS_BR=Proteção Executiva Brasil
ODOO_PREFIJO_LISTAS_BR=Brasil ·
ODOO_IDIOMA_BR=pt_BR
ODOO_PRODUCTO_GASTOS=Gastos de Operación (Viáticos)
ODOO_CAMPO_CPF=
ODOO_CAMPO_CNH=

# Pegasus, el GPS de las unidades. Vacio = no se lee nada. Que grupo se
# lee en cada pais, con su valor de siempre.
PEGASUS_SITIO=
PEGASUS_USUARIO=
PEGASUS_CLAVE=
PEGASUS_SECRETO_AVISO=
PEGASUS_GRUPOS=MX=2025 P.E.;BR=CENTAURO BRASIL

# Los depositos de Google (secciones 69 y 111). Vacio = las fotos de los
# comprobantes y los archivos del expediente se quedan en la base.
ARCHIVO_DESTINO=
EXPEDIENTES_DESTINO=
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

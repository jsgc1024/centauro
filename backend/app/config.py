from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://centauro:centauro_dev@db:5432/centauro"
    redis_url: str = "redis://redis:6379/0"
    app_env: str = "local"
    # Con esta clave se firman las sesiones. La de abajo es de demo y
    # esta en el codigo, asi que cualquiera que lo lea puede firmarse
    # una sesion de director general. Fuera de local, la aplicacion se
    # niega a arrancar si sigue siendo esta (ver revisar_secretos).
    secret_key: str = "centauro-demo-cambiar-en-produccion"
    # Google Maps Platform. La llave vive solo en el servidor: el navegador
    # nunca la ve, ni en el mapa ni en la busqueda.
    google_maps_key: str = ""
    # La linea de la central: el numero que el boton de panico marca.
    # Es una linea fija, no el celular de quien este de turno, porque el
    # turno cambia y el numero al que se llama en una emergencia no.
    telefono_central: str = "+525550221022"

    # Avisos al telefono del equipo de campo (Web Push). El par de
    # llaves se genera una vez con `python generar_llaves_push.py`; la
    # publica la reparte la app, la privada nunca sale del servidor.
    vapid_public: str = ""
    vapid_private: str = ""
    # A quien le escribe el navegador si algo sale mal con los avisos.
    vapid_contacto: str = "mailto:operaciones@centauro.lat"

    # El correo que sale de la empresa.
    #
    # Va por SMTP y no por la API de un proveedor a proposito: SMTP lo
    # hablan todos --Amazon SES, Postmark, Mailgun, Google Workspace, el
    # servidor de la casa-- asi que elegir proveedor manana es cambiar
    # cuatro renglones del `.env` y no una linea de codigo. Si algun dia
    # hace falta uno que solo hable HTTP, lo unico que se toca es
    # `correo.entregar()`. Ese dia llego con Microsoft 365 (abajo).
    #
    # Mientras no haya a donde mandar --SMTP o Microsoft-- y `correo_de`
    # este vacio, no sale nada: el aviso se guarda pendiente y espera. Un
    # sistema que se cree configurado y no lo esta es peor que uno
    # apagado.
    correo_host: str = ""
    correo_puerto: int = 587
    correo_usuario: str = ""
    correo_clave: str = ""
    correo_de: str = ""            # "Centauro <ai@centauro.lat>"
    # Microsoft 365 (seccion 67). Decision de Salvador, 25 de septiembre:
    # el correo sale del buzon de la empresa. Microsoft apaga la entrada
    # por SMTP con usuario y contrasena el 31 de diciembre de 2026, asi
    # que no va por SMTP: va por Microsoft Graph, con la aplicacion
    # registrada en Entra y permiso para mandar solo desde el buzon de
    # `correo_de`. Con estos tres llenos manda Microsoft y los de SMTP de
    # arriba no se usan. El secreto vence --Entra lo da por 24 meses como
    # maximo--: anota el dia.
    correo_ms_tenant: str = ""     # Id. de directorio (inquilino)
    correo_ms_cliente: str = ""    # Id. de aplicacion (cliente)
    correo_ms_secreto: str = ""    # el Valor del secreto, no su Id.
    # De donde cuelgan los enlaces que van dentro de un correo. Sin
    # esto, el enlace de una encuesta seria "/encuestas/pagina/abc" y no
    # llevaria a ningun lado fuera del servidor.
    url_publica: str = ""          # "https://mycentauro.lat"

    # Odoo, del lado de SALIDA: la factura del servicio aprobado.
    #
    # Lo que Odoo manda --flota, capacitaciones, taller-- llega por sus
    # propias rutas y no necesita nada de esto; esto es para lo que
    # Centauro le manda. El personal ya no espera a que se lo manden: se
    # lee (abajo, `odoo_base`).
    #
    # Mientras `odoo_url` este vacio no sale nada: el cierre aprobado se
    # queda en la bandeja de "por facturar" y se puede mandar despues sin
    # volver a capturar nada. Un sistema que se cree conectado y no lo
    # esta es peor que uno apagado.
    odoo_url: str = ""             # "https://odoo.centauro.lat/api/facturas"
    odoo_token: str = ""
    odoo_timeout: int = 20

    # Odoo, del lado de ENTRADA (seccion 51): Centauro lee de ahi al
    # personal de seguridad cada hora, por la API JSON-2. Solo lee.
    # `odoo_api_key` es la llave del usuario de la conexion --no la de una
    # persona-- y Odoo la da por tres meses como maximo. Vacio = no se lee
    # nada. `odoo_bd` solo hace falta si el servidor tiene varias bases.
    odoo_base: str = ""            # "https://centauro.odoo.com"
    odoo_api_key: str = ""
    odoo_bd: str = ""
    # Seccion 77. Los clientes de Proteccion Ejecutiva son las empresas
    # que traen esta etiqueta en Odoo --asi llegan los que todavia no
    # tienen ventas y no llegan los de GPS ni los de carga--. Y la lista
    # de precios de sus implantados vive en un campo que se agrega con
    # Studio; se busca por su nombre visible, y si no, por este tecnico.
    odoo_etiqueta_clientes: str = "Protección ejecutiva"
    odoo_campo_implantados: str = "x_studio_lista_de_implantados"

    # Pegasus, el GPS de las unidades (seccion 60). Solo lectura, con un
    # usuario propio de la conexion --no el de una persona-- que solo ve
    # los grupos de Proteccion Ejecutiva. Vacio = no se lee nada.
    pegasus_sitio: str = ""        # "https://www.centaurosatelital.mx"
    pegasus_usuario: str = ""
    pegasus_clave: str = ""
    # Que grupo se lee en cada pais: "MX=2025 P.E.;BR=CENTAURO BRASIL".
    pegasus_grupos: str = "MX=2025 P.E.;BR=CENTAURO BRASIL"
    # El aviso con el que Pegasus despierta la revision de panicos. Vacio
    # = la ruta no existe y el panico se revisa cada dos minutos.
    pegasus_secreto_aviso: str = ""

    # El archivo de los comprobantes (seccion 69). Decision de Salvador,
    # 25 de septiembre: tres meses despues de la factura --o de la
    # aprobacion de finanzas, mientras Odoo no este conectado--, la foto
    # del ticket y la de la devolucion salen de la base y se van a un
    # deposito de Google. La foto se muda; el registro se queda.
    #
    # Nace apagado: con `archivo_destino` vacio no sale ninguna foto, y
    # el historial de Facturacion solo dice cuando se irian. Se prende
    # con el nombre del deposito que arma despliegue/gcp/crear_archivo.sh.
    archivo_destino: str = ""      # "gs://centauro-archivo-<proyecto>"
    archivo_meses: int = 3
    # Cuantas fotos se mudan por noche, como mucho. La primera vez puede
    # haber meses acumulados: asi se reparten en varias noches y ninguna
    # se come la madrugada.
    archivo_por_noche: int = 3000
    # Cuanto las guarda Google. Aqui solo se dice en pantalla; quien lo
    # cumple es el candado del deposito (crear_archivo.sh). El Codigo
    # Fiscal pide cinco anos contados desde la declaracion anual: seis
    # desde que se archiva los cubren siempre. Lo confirma el contador.
    archivo_anios: int = 6

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


CLAVE_DE_DEMO = "centauro-demo-cambiar-en-produccion"


# Entornos donde la clave de demo es aceptable: la maquina de quien
# desarrolla y el contenedor de pruebas. Se enumeran a proposito, en vez
# de comparar contra "produccion": un nombre de entorno que nadie
# reconozca tiene que tratarse como produccion, no como desarrollo.
NO_ES_PRODUCCION = {"local", "dev", "desarrollo", "test", "pruebas", "ci"}


def es_desarrollo(s: "Settings") -> bool:
    """Si este entorno es la maquina de alguien o el de pruebas.

    Se pregunta al reves a proposito --se enumera lo que SI es
    desarrollo-- por lo que dice la lista de arriba: un entorno con un
    nombre que nadie reconozca tiene que tratarse como produccion. Una
    puerta que se abre sola cuando no entiende el nombre del entorno es
    una puerta abierta.
    """
    return (s.app_env or "").strip().lower() in NO_ES_PRODUCCION


def puertas_de_la_api(s: "Settings") -> dict:
    """Donde se publica el mapa de la API, si es que se publica.

    `/docs`, `/redoc` y `/openapi.json` son el plano completo del
    sistema: cada endpoint, cada campo, cada nombre, con el formulario
    para probarlos al lado. No ensenan datos --todo sigue pidiendo
    sesion-- pero a quien quiera buscarle la vuelta le ahorran el
    trabajo de adivinar por donde.

    Adentro valen su peso en oro y se quedan abiertos. Afuera no: quien
    necesite el mapa lo levanta en su maquina.
    """
    abierto = es_desarrollo(s)
    return {"docs_url": "/docs" if abierto else None,
            "redoc_url": "/redoc" if abierto else None,
            "openapi_url": "/openapi.json" if abierto else None}


def revisar_secretos(s: "Settings") -> None:
    """Fuera de desarrollo, no se arranca con la clave del codigo.

    Un sistema que arranca igual con o sin secreto configurado se
    despliega tarde o temprano sin el, y nadie se entera hasta que
    alguien firma su propia sesion de director general. Es mejor que
    no encienda.
    """
    if es_desarrollo(s):
        return
    if s.secret_key == CLAVE_DE_DEMO or not s.secret_key.strip():
        raise RuntimeError(
            "SECRET_KEY sigue siendo la de demo. Con ella cualquiera que "
            "lea el codigo puede firmarse una sesion de director general. "
            "Pon una propia en .env antes de levantar esto fuera de local:\n"
            "    SECRET_KEY=$(python3 -c \"import secrets;"
            "print(secrets.token_urlsafe(48))\")")


settings = Settings()

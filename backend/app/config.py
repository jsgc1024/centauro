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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


CLAVE_DE_DEMO = "centauro-demo-cambiar-en-produccion"


# Entornos donde la clave de demo es aceptable: la maquina de quien
# desarrolla y el contenedor de pruebas. Se enumeran a proposito, en vez
# de comparar contra "produccion": un nombre de entorno que nadie
# reconozca tiene que tratarse como produccion, no como desarrollo.
NO_ES_PRODUCCION = {"local", "dev", "desarrollo", "test", "pruebas", "ci"}


def revisar_secretos(s: "Settings") -> None:
    """Fuera de desarrollo, no se arranca con la clave del codigo.

    Un sistema que arranca igual con o sin secreto configurado se
    despliega tarde o temprano sin el, y nadie se entera hasta que
    alguien firma su propia sesion de director general. Es mejor que
    no encienda.
    """
    if (s.app_env or "").strip().lower() in NO_ES_PRODUCCION:
        return
    if s.secret_key == CLAVE_DE_DEMO or not s.secret_key.strip():
        raise RuntimeError(
            "SECRET_KEY sigue siendo la de demo. Con ella cualquiera que "
            "lea el codigo puede firmarse una sesion de director general. "
            "Pon una propia en .env antes de levantar esto fuera de local:\n"
            "    SECRET_KEY=$(python3 -c \"import secrets;"
            "print(secrets.token_urlsafe(48))\")")


settings = Settings()

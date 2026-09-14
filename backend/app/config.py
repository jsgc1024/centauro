from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://centauro:centauro_dev@db:5432/centauro"
    redis_url: str = "redis://redis:6379/0"
    app_env: str = "local"
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


settings = Settings()

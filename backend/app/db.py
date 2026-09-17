from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# El pozo de conexiones contra el pozo de hilos.
#
# Casi todos los endpoints son `def` y no `async def`, asi que FastAPI
# los corre en un pozo de 40 hilos. El motor por omision da 5 conexiones
# mas 10 de desborde: pasando de 15 peticiones simultaneas que toquen la
# base, las demas esperan y acaban reventando con *pool timeout*. En
# desarrollo no se nota; con la central, finanzas y varios consultores
# trabajando al mismo tiempo, si.
#
# `pool_recycle` cierra las conexiones que llevan media hora abiertas:
# un cortafuegos en medio las corta sin avisar y la siguiente consulta
# falla sola.
#
# Cada trabajador de uvicorn tiene su propio pozo, y el worker de Celery
# el suyo: de ahi sale el `max_connections` de Postgres en
# docker-compose.prod.yml.
engine = create_engine(settings.database_url, pool_pre_ping=True,
                       pool_size=20, max_overflow=20, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

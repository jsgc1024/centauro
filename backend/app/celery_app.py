from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery = Celery(
    "centauro",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_track_started=True,
    timezone="America/Mexico_City",
    beat_schedule={
        # Todas las mananas, temprano. La tarea decide sola si toca: solo
        # hace algo cuando al mes en curso le quedan pocos dias.
        "implantados-mes-siguiente": {
            "task": "implantados.abrir_mes_siguiente",
            "schedule": crontab(hour=6, minute=30),
        },
        # El recordatorio de la vispera, a la misma hora que el corte de
        # la central: a las seis de la tarde lo que falta para manana
        # deja de ser trabajo del dia y pasa a ser un problema de esta
        # noche. Avisarle al equipo antes de esa hora es lo que evita
        # que el problema exista.
        "confirmacion-de-la-vispera": {
            "task": "campo.recordar_la_vispera",
            "schedule": crontab(hour=17, minute=0),
        },
    },
)


@celery.task(name="ping")
def ping():
    return "pong"


@celery.task(name="campo.recordar_la_vispera")
def recordar_la_vispera():
    """Le recuerda a cada quien que manana trabaja.

    La confirmacion de la vispera dependia de que alguien se acordara de
    abrir la app, y una confirmacion que nadie hace es un renglon rojo
    eterno en la central.
    """
    from app import push
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        return push.recordar_la_vispera(db)
    finally:
        db.close()


@celery.task(name="implantados.abrir_mes_siguiente")
def abrir_mes_siguiente():
    """El implantado no se vuelve a capturar cada mes.

    Antes de que se acabe el mes en curso, el sistema abre el que sigue
    con los mismos terminos y la misma plantilla, para que nadie llegue
    un dia primero a un calendario vacio. El consultor puede adelantarse
    con el boton del panel; esta tarea solo se asegura de que no se
    olvide.
    """
    # Se importa aqui y no arriba: el worker no tiene por que cargar los
    # modelos al arrancar si nunca corre esta tarea.
    from app import implantado as motor
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        return motor.abrir_los_que_toquen(db)
    finally:
        db.close()

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
        #
        # Cada hora en punto, y la tarea decide en que pais son las
        # cinco de la tarde: este calendario tiene un solo reloj --el
        # del contenedor-- y la operacion tiene tres. Disparada a la
        # hora de Mexico, la vispera de Sao Paulo salia a las 19:00.
        "confirmacion-de-la-vispera": {
            "task": "campo.recordar_la_vispera",
            "schedule": crontab(minute=0),
        },
        # El correo sale cada cinco minutos. No al instante y a
        # proposito: el aviso se escribe dentro de la transaccion que lo
        # origina --un cierre, una encuesta, una cobertura-- y mandarlo
        # ahi mismo ataria esa operacion a que el proveedor conteste. Se
        # escribe, se sigue trabajando, y se entrega aparte.
        "correo-pendiente": {
            "task": "correo.despachar",
            "schedule": crontab(minute="*/5"),
        },
        # El camino al meet and greet. Cada cinco minutos manda los
        # toques que tocan y cobra los silencios: reponer a alguien toma
        # hora y media, asi que enterarse tarde es no enterarse.
        "camino-al-punto": {
            "task": "campo.pulsar_trayecto",
            "schedule": crontab(minute="*/5"),
        },
        # Estas dos existian escritas y probadas, y eran botones que
        # nadie picaba: el reloj no las corria. Una vigilancia que nadie
        # dispara no vigila nada.
        "servicios-sin-reporte": {
            "task": "operacion.revisar_standby",
            "schedule": crontab(minute="*/15"),
        },
        # Las que arrancan dentro de la ventana pasan a "proxima a
        # iniciar". Lo mueve el reloj y no una pantalla: mientras esto
        # vivio dentro del GET del tablero, el estado de una jornada
        # dependia de que alguien lo abriera.
        "jornadas-proximas": {
            "task": "operacion.marcar_proximas",
            "schedule": crontab(minute="*/5"),
        },
        "aviso-horas-extra": {
            "task": "operacion.avisar_horas_extra",
            "schedule": crontab(minute="*/5"),
        },
        # El segundo reloj del cierre: lo que llego a T1 --o cerro todo
        # su dinero antes-- pasa a sin visto bueno y arrancan las 24 h
        # del consultor. Lo mueve el reloj, no una persona.
        "cierre-avanzar": {
            "task": "cierre.avanzar",
            "schedule": crontab(minute="*/5"),
        },
        # Los certificados que se vencen. Una vez al dia, temprano:
        # avisa a los treinta dias y el dia que vence, y nada mas. El
        # campo existia desde hacia meses y nada lo miraba.
        "certificados-por-vencer": {
            "task": "capacitaciones.revisar_vencimientos",
            "schedule": crontab(hour=7, minute=30),
        },
        # La encuesta que nadie contesto. Una vez al dia, temprano: le
        # recuerda a quien lleva cinco dias sin contestar y vence lo que
        # paso de quince. Sin esto la encuesta se mandaba una vez y ahi
        # se acababa, y "enviada" no distinguia entre esperando y
        # muerta.
        "encuestas-pasar-lista": {
            "task": "encuestas.pasar_lista",
            "schedule": crontab(hour=8, minute=0),
        },
        # Las estrellas del mes que acaba de cerrar. El dia 3 y no el 1:
        # el viatico del ultimo dia tiene 24 horas para comprobarse, asi
        # que calcular el 1 castiga a quien todavia esta en plazo.
        # Temprano, para que el corte este listo cuando abran.
        "estrellas-del-mes": {
            "task": "bonos.calcular_el_mes",
            "schedule": crontab(day_of_month="3", hour=5, minute=0),
        },
        # El personal de seguridad, leido de Odoo (seccion 51). Cada hora,
        # a los 17 minutos para no caer junto con las de la hora en punto.
        # No arranca sola: espera a que alguien haya hecho la primera
        # lectura a mano, despues de ver el ensayo.
        "odoo-personal": {
            "task": "odoo.sincronizar_personal",
            "schedule": crontab(minute=17),
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


@celery.task(name="correo.despachar")
def despachar_correo():
    """Saca los avisos que estan escritos y no han salido.

    Si no hay proveedor configurado no hace nada y no se queja: la cola
    espera. Es la unica forma honesta de estar a medio configurar.
    """
    from app import correo
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        return correo.despachar(db)
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


@celery.task(name="campo.pulsar_trayecto")
def pulsar_trayecto():
    """Los toques del camino al punto y sus silencios."""
    from app.db import SessionLocal
    from app import trayecto

    db = SessionLocal()
    try:
        return trayecto.pulsar(db)
    finally:
        db.close()


@celery.task(name="operacion.revisar_standby")
def revisar_standby():
    """El servicio que dejo de reportar. Existia y nadie lo corria."""
    from app.db import SessionLocal
    from app import operacion

    db = SessionLocal()
    try:
        return {"alertas": len(operacion.revisar_standby(db))}
    finally:
        db.close()


@celery.task(name="capacitaciones.revisar_vencimientos")
def revisar_vencimientos():
    """Los certificados por vencer: a la persona y a quien la gestiona."""
    from app import capacitaciones
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        return capacitaciones.revisar_vencimientos(db)
    finally:
        db.close()


@celery.task(name="encuestas.pasar_lista")
def encuestas_pasar_lista():
    """El recordatorio unico y el vencimiento de las encuestas."""
    from app import encuestas
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        return encuestas.pasar_lista(db)
    finally:
        db.close()


@celery.task(name="bonos.calcular_el_mes")
def calcular_estrellas_del_mes():
    """El bono del mes vencido. Nace CALCULADA: nunca se autoriza sola."""
    from datetime import date

    from app import bonos
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        anio, mes = bonos.mes_anterior(date.today())
        return bonos.calcular_el_mes(db, anio, mes)
    finally:
        db.close()


@celery.task(name="operacion.marcar_proximas")
def marcar_proximas():
    """Lo que arranca pronto pasa a PROXIMA_A_INICIAR."""
    from app.db import SessionLocal
    from app import operacion

    db = SessionLocal()
    try:
        return operacion.marcar_proximas_a_iniciar(db)
    finally:
        db.close()


@celery.task(name="operacion.avisar_horas_extra")
def avisar_horas_extra():
    """El aviso preventivo. Existia y nadie lo corria."""
    from app.db import SessionLocal
    from app import operacion

    db = SessionLocal()
    try:
        return {"avisos": len(operacion.avisar_horas_extra(db))}
    finally:
        db.close()


@celery.task(name="cierre.avanzar")
def avanzar_cierres():
    """De la comprobacion al visto bueno, cuando toca."""
    from app.db import SessionLocal
    from app import cierre

    db = SessionLocal()
    try:
        return {"movidos": cierre.avanzar_cierres(db)}
    finally:
        db.close()


@celery.task(name="odoo.sincronizar_personal")
def sincronizar_personal_de_odoo():
    """El personal de seguridad, leido de Odoo."""
    from app.db import SessionLocal
    from app import odoo_personal

    db = SessionLocal()
    try:
        return odoo_personal.sincronizar_si_toca(db)
    finally:
        db.close()

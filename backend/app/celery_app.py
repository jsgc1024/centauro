import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_postrun, task_prerun

from app.config import settings

celery = Celery(
    "centauro",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_track_started=True,
    timezone="America/Mexico_City",
    # Ninguna tarea vive para siempre (seccion 100): la que se cuelga
    # --un telefono que no contesta, Pegasus que no suelta-- recibe
    # aviso a los diez minutos y se mata a los quince, y el proceso
    # queda libre para la siguiente. La mas larga, el archivo de los
    # comprobantes, cabe de sobra.
    task_soft_time_limit=600,
    task_time_limit=900,
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
        # El corte del lunes (seccion 66): a las 7:00 de cada pais se
        # arma el borrador y a las 11:00 queda listo para pagar. Cada
        # quince minutos, y la tarea decide a que pais le toca: el
        # calendario tiene un solo reloj y la operacion tiene tres.
        "nomina-del-lunes": {
            "task": "nomina.lunes",
            "schedule": crontab(minute="*/15"),
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
        # La flota y el taller (seccion 52), diez minutos despues. Tambien
        # espera a la primera lectura hecha a mano.
        "odoo-flota": {
            "task": "odoo.sincronizar_flota",
            "schedule": crontab(minute=27),
        },
        # El personal de oficina (seccion 74), otros diez minutos despues.
        # Igual: espera a la primera lectura hecha a mano.
        "odoo-oficina": {
            "task": "odoo.sincronizar_oficina",
            "schedule": crontab(minute=37),
        },
        # Los clientes (seccion 75), a los :47. Tambien espera a la
        # primera lectura hecha a mano.
        "odoo-clientes": {
            "task": "odoo.sincronizar_clientes",
            "schedule": crontab(minute=47),
        },
        # Los tarifarios (seccion 77), a los :57, despues de los clientes:
        # asi el cliente que llego a las :47 ya sale con su lista. Tambien
        # espera a la primera lectura hecha a mano.
        "odoo-tarifarios": {
            "task": "odoo.sincronizar_tarifarios",
            "schedule": crontab(minute=57),
        },
        # El GPS de las unidades (seccion 60). Cada dos minutos: el
        # panico del vehiculo, el camino al punto, el inhibidor y la
        # corriente, y el segundo testigo de las marcas. Sin nadie en la
        # calle, las posiciones solo se leen cada quince. Sin usuario de
        # Pegasus en el .env no hace nada.
        "gps-leer": {
            "task": "gps.leer",
            "schedule": crontab(minute="*/2"),
            # La vuelta que no arranco antes de que toque la siguiente
            # se tira: dos vueltas encimadas leian lo mismo dos veces y
            # levantaban las alertas por duplicado (seccion 100). El
            # candado entre las que si arrancan vive en gps.leer.
            "options": {"expires": 110},
        },
        # Lo que recorrio cada unidad en el dia y su manejo, cuando ya se
        # guardo: dos horas despues del fin. Cada hora, a los 41.
        "gps-cerrar-dias": {
            "task": "gps.cerrar_dias",
            "schedule": crontab(minute=41),
        },
        # El archivo de los comprobantes (seccion 69). A la 1:30, antes
        # del respaldo de las 2:30: lo que se muda esta noche ya no viaja
        # en el respaldo de esta noche. Con ARCHIVO_DESTINO vacio no hace
        # nada.
        "archivo-de-comprobantes": {
            "task": "archivo.archivar",
            "schedule": crontab(hour=1, minute=30),
        },
        # La red de las diarias (seccion 100): cada media hora mira cual
        # de las de arriba no corrio a su hora --beat reiniciado en ese
        # minuto, worker caido esa manana-- y la vuelve a mandar. Ver
        # DIARIAS.
        "reloj-reponer-diarias": {
            "task": "reloj.reponer_diarias",
            "schedule": crontab(minute="*/30"),
        },
    },
)

# Las diarias que no pueden perderse: a que hora de Mexico tocan y, si
# es de un solo dia del mes, cual. El calendario de arriba las dispara;
# `reponer_diarias` repone la que no termino desde esa hora. Las cinco
# son idempotentes: la que ya hizo lo suyo no lo hace dos veces (el
# certificado avisado no se avisa otra vez, el mes abierto no se abre,
# la encuesta recordada no se recuerda, el bono autorizado no se toca).
DIARIAS = {
    "archivo.archivar": (1, 30, None),
    "bonos.calcular_el_mes": (5, 0, 3),
    "implantados.abrir_mes_siguiente": (6, 30, None),
    "capacitaciones.revisar_vencimientos": (7, 30, None),
    "encuestas.pasar_lista": (8, 0, None),
}
# Cuanto se le espera a la programada antes de reponerla, y cuanto dura
# como mucho una que esta corriendo.
MINUTOS_DE_MARGEN = 20
MINUTOS_CORRIENDO = 15
ZONA_DEL_RELOJ = ZoneInfo("America/Mexico_City")


# La vuelta de cada tarea, anotada (seccion 90). Hasta aqui nadie sabia
# cuando habia corrido cada una: si el reloj se detenia, se notaba horas
# despues, por lo que dejaba de pasar. Cada tarea anota cuando empezo,
# cuando termino y como salio, y el manual lo ensena. Anotar no puede
# tumbar la tarea: si falla, se dice en el registro y se sigue.
registro_reloj = logging.getLogger("centauro.reloj")


def _anotar(tarea, **datos) -> None:
    try:
        from app import manual
        manual.anotar_vuelta(tarea, **datos)
    except Exception:                                 # noqa: BLE001
        registro_reloj.exception("no se pudo anotar la vuelta de %s", tarea)


@task_prerun.connect
def _empieza(task=None, **_):
    if task is not None:
        _anotar(task.name, empezo=datetime.now(timezone.utc))


@task_postrun.connect
def _termina(task=None, state=None, retval=None, **_):
    if task is None:
        return
    error = nota = None
    if state == "FAILURE":
        error = f"{retval.__class__.__name__}: {retval}"[:300]
    elif isinstance(retval, dict):
        # Las lecturas de Odoo no revientan cuando Odoo no contesta:
        # devuelven su error. Y la que espera su primera lectura a mano lo
        # dice con `omitido`. Las dos cosas son lo que se quiere ver.
        if retval.get("error"):
            error = str(retval["error"])[:300]
        if retval.get("omitido"):
            nota = str(retval["omitido"])[:200]
    _anotar(task.name, termino=datetime.now(timezone.utc), error=error,
            nota=nota)


@celery.task(name="ping")
def ping():
    return "pong"


def diarias_que_faltan(db, ahora: datetime | None = None) -> list[str]:
    """Las diarias que ya debieron correr hoy y no terminaron desde su
    hora. `ahora` en UTC; la hora de cada una es de Mexico."""
    from app import models as m

    ahora = ahora or datetime.now(timezone.utc)
    local = ahora.astimezone(ZONA_DEL_RELOJ)
    faltan = []
    for nombre, (hora, minuto, dia) in DIARIAS.items():
        if dia is not None and local.day != dia:
            continue
        toca = local.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if local < toca + timedelta(minutes=MINUTOS_DE_MARGEN):
            continue
        vuelta = db.get(m.VueltaDelReloj, nombre)
        termino = vuelta.termino_en if vuelta else None
        empezo = vuelta.empezo_en if vuelta else None
        if termino is not None and termino >= toca:
            continue
        if (empezo is not None and empezo >= toca
                and ahora - empezo < timedelta(minutes=MINUTOS_CORRIENDO)):
            continue                      # esta corriendo ahora mismo
        faltan.append(nombre)
    return faltan


@celery.task(name="reloj.reponer_diarias")
def reponer_diarias():
    """Manda otra vez la diaria que no corrio a su hora (seccion 100)."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        faltan = diarias_que_faltan(db)
    finally:
        db.close()
    for nombre in faltan:
        celery.send_task(nombre)
    return {"repuestas": faltan}


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


@celery.task(name="nomina.lunes")
def nomina_del_lunes():
    """El borrador del corte a las 7:00 y su cierre a las 11:00, en hora
    de cada pais. Lo que pasa a las 12:00 --pagarlo-- es de finanzas."""
    from app import nomina
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        return nomina.reloj_del_lunes(db)
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
    """De la comprobacion al visto bueno, cuando toca.

    Antes, la red del implantado: el mes que quedo completo sin que el
    cierre de un dia lo disparara --se cancelaron sus ultimos dias--
    arranca aqui su cierre (seccion 56).
    """
    from app.db import SessionLocal
    from app import cierre, cierre_mes

    db = SessionLocal()
    try:
        meses = cierre_mes.abrir_los_que_terminaron(db)
        return {"meses_abiertos": meses,
                "movidos": cierre.avanzar_cierres(db)}
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


@celery.task(name="odoo.sincronizar_flota")
def sincronizar_flota_de_odoo():
    """La flota y el taller de Proteccion Ejecutiva, leidos de Odoo."""
    from app.db import SessionLocal
    from app import odoo_flota

    db = SessionLocal()
    try:
        return odoo_flota.sincronizar_si_toca(db)
    finally:
        db.close()


@celery.task(name="odoo.sincronizar_oficina")
def sincronizar_oficina_de_odoo():
    """El personal de oficina, leido de Odoo (seccion 74). Deja a cada
    quien listo para su acceso; el acceso lo da Recursos Humanos."""
    from app.db import SessionLocal
    from app import odoo_oficina

    db = SessionLocal()
    try:
        return odoo_oficina.sincronizar_si_toca(db)
    finally:
        db.close()


@celery.task(name="odoo.sincronizar_clientes")
def sincronizar_clientes_de_odoo():
    """Los clientes, leidos de Odoo (seccion 75)."""
    from app.db import SessionLocal
    from app import odoo_clientes

    db = SessionLocal()
    try:
        return odoo_clientes.sincronizar_si_toca(db)
    finally:
        db.close()


@celery.task(name="odoo.sincronizar_tarifarios")
def sincronizar_tarifarios_de_odoo():
    """Los tarifarios, leidos de Odoo (seccion 77)."""
    from app.db import SessionLocal
    from app import odoo_tarifarios

    db = SessionLocal()
    try:
        return odoo_tarifarios.sincronizar_si_toca(db)
    finally:
        db.close()


@celery.task(name="gps.leer")
def leer_el_gps():
    """La vuelta de cada dos minutos por Pegasus. Solo lee."""
    from app.db import SessionLocal
    from app import gps

    db = SessionLocal()
    try:
        return gps.leer(db)
    finally:
        db.close()


@celery.task(name="gps.cerrar_dias")
def cerrar_los_dias_del_gps():
    """Los km y el manejo de cada unidad en los dias ya terminados."""
    from app.db import SessionLocal
    from app import gps

    db = SessionLocal()
    try:
        return gps.cerrar_dias(db)
    finally:
        db.close()


@celery.task(name="archivo.archivar")
def archivar_comprobantes():
    """Las fotos que ya cumplieron sus tres meses, al archivo de Google."""
    from app.db import SessionLocal
    from app import archivo

    db = SessionLocal()
    try:
        return archivo.archivar(db)
    finally:
        db.close()

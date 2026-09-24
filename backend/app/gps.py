# -*- coding: utf-8 -*-
"""El GPS de las unidades, en la base (seccion 60).

Decisiones de Salvador, 23 de septiembre, despues de ver los seis
tableros: «alertas, si las manejan ellos. adelante con lo demas».

  * **Unidades.** Cada unidad de Odoo con su GPS de Pegasus, ligadas por
    la placa. Solo se leen los dos grupos de Proteccion Ejecutiva, con un
    usuario de solo lectura; en Pegasus no se escribe nada.
  * **El camino al punto.** Para quien trae una unidad, su posicion
    cuenta igual que la del telefono: lo que tiene que llegar al punto
    es la camioneta. Misma regla de la seccion 38: linea recta y reloj.
  * **Las alertas.** El panico del vehiculo suena siempre, con o sin
    servicio. El inhibidor y la corriente cortada (mas de 2 minutos),
    solo del camino al punto a la marca de fin: fuera de esa ventana las
    vigila Centauro Satelital, que ya lo hace las 24 horas. La unidad no
    apaga ninguna alerta: agrega lo que sabe.
  * **El segundo testigo.** Cada marca queda con lo que decia la unidad
    de quien marco. No frena nada: queda para revisar.
  * **La gasolina** contra los kilometros de la unidad, y **el manejo**
    en la calificacion del personal.

Lo que NO hace: no guarda el recorrido --de cada unidad solo la ultima
posicion, que se sobreescribe--, el cliente no ve nada de esto (seccion
53) y en Pegasus no se escribe nada.

Todo lo mueve el reloj, como el resto del sistema: `leer` cada dos
minutos y `cerrar_dias` cada hora. Sin usuario y clave de Pegasus en el
`.env`, las dos se quedan quietas y lo dicen.
"""
import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app import gps_reglas as reglas
from app import models as m
from app import pegasus as conexion
from app import reloj
from app import revision
from app.operacion import distancia_metros

registro = logging.getLogger("centauro.gps")

# El mismo rol que usa implantado.py para el titular.
ROL_CONDUCTOR = "conductor_seguridad"
# Sin nadie en la calle, las posiciones se leen cada tanto: solo para
# saber que unidad reporta.
MINUTOS_LECTURA_TRANQUILA = 15
# Las marcas mas viejas que esto ya no se le preguntan a Pegasus.
HORAS_PARA_EL_TESTIGO = 6
# Los dias que se cierran: de lo terminado hace dos horas --para que la
# unidad se guarde-- hasta tres dias atras.
HORAS_DESPUES_DEL_FIN = 2
DIAS_PARA_CERRAR = 3
# El aviso de Pegasus no despierta la revision de panicos dos veces en
# este rato: la ruta es publica y no tiene que servir para martillar.
SEGUNDOS_ENTRE_AVISOS = 20
VIVAS = (m.EstatusJornada.PLANEADA, m.EstatusJornada.CONFIRMADA,
         m.EstatusJornada.PROXIMA_A_INICIAR, m.EstatusJornada.ARRIBADO,
         m.EstatusJornada.EN_CURSO)
DE_LA_UNIDAD = (m.TipoAlerta.INHIBIDOR, m.TipoAlerta.SIN_CORRIENTE)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def configurado() -> bool:
    from app.config import settings
    return bool(settings.pegasus_sitio and settings.pegasus_usuario
                and settings.pegasus_clave)


def grupos_configurados() -> dict[str, str]:
    """{"MX": "2025 P.E.", "BR": "CENTAURO BRASIL"} desde el `.env`."""
    from app.config import settings
    salida = {}
    for parte in (settings.pegasus_grupos or "").split(";"):
        if "=" not in parte:
            continue
        codigo, nombre = parte.split("=", 1)
        if codigo.strip() and nombre.strip():
            salida[codigo.strip().upper()] = nombre.strip()
    return salida


def _normal(nombre) -> str:
    return re.sub(r"[\s.\-_]", "", str(nombre or "")).lower()


def local(instante: datetime | None, pais: m.Pais | None) -> datetime | None:
    """Un instante de Pegasus en la hora de pared del pais."""
    if instante is None:
        return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return reloj.ahora_en(pais, instante)


def instante(hora_local: datetime, pais: m.Pais | None) -> datetime:
    """Una hora de pared del pais, como instante."""
    zona = reloj.zona(getattr(pais, "zona_horaria", None))
    return hora_local.replace(tzinfo=zona).astimezone(timezone.utc)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


# ================================================================ quien va

def _vigentes(jornada: m.Jornada) -> list[m.AsignacionVehiculo]:
    return [a for a in jornada.vehiculos
            if a.vehiculo_id and a.relevado_en is None]


def a_bordo(jornada: m.Jornada, vehiculo_id: int) -> list[m.AsignacionPersonal]:
    """Quienes van en esa unidad ese dia: la misma regla que decide
    quien firma su revision (`revision.mis_unidades`)."""
    return [a for a in jornada.personal
            if a.persona_id and a.relevado_en is None
            and vehiculo_id in revision.mis_unidades(jornada, a.persona_id)]


def _conductores(gente: list[m.AsignacionPersonal]) -> list:
    return [a for a in gente if a.rol and a.rol.codigo == ROL_CONDUCTOR]


def la_traen(jornada: m.Jornada, vehiculo_id: int) -> list[m.AsignacionPersonal]:
    """Quien trae la unidad al punto: el conductor; si nadie va de
    conductor, quien vaya en ella."""
    gente = a_bordo(jornada, vehiculo_id)
    return _conductores(gente) or gente


def quien_maneja(jornada: m.Jornada, vehiculo_id: int) -> int | None:
    """A quien se le cuenta el manejo de esa unidad ese dia. Con dos
    conductores a bordo no se sabe quien iba al volante: a nadie."""
    gente = a_bordo(jornada, vehiculo_id)
    conductores = _conductores(gente)
    if len(conductores) == 1:
        return conductores[0].persona_id
    if not conductores and len(gente) == 1:
        return gente[0].persona_id
    return None


def unidad_de(db: Session, vehiculo_id: int | None) -> m.UnidadGps | None:
    if not vehiculo_id:
        return None
    return (db.query(m.UnidadGps)
            .filter_by(vehiculo_id=vehiculo_id, en_el_grupo=True).first())


# ================================================================ lo que dice

def dias_atras(hora_local: datetime | None,
               ahora_local: datetime | None) -> int | None:
    """Cuantos dias de calendario del pais van de esa hora a hoy: 0 hoy,
    1 ayer. Con esto la pantalla dice "de ayer" sin depender del reloj de
    quien la mira, que puede estar en otro pais."""
    if hora_local is None or ahora_local is None:
        return None
    return (ahora_local.date() - hora_local.date()).days


def linea(unidad: m.UnidadGps | None, pais: m.Pais | None,
          ahora: datetime | None = None) -> dict | None:
    """Lo que dice la unidad ahora mismo, para pintarlo en un renglon.
    Sin posicion: solo su estado y desde cuando."""
    if unidad is None:
        return None
    ahora = ahora or _utc()
    hoy = local(ahora, pais)
    placa = unidad.vehiculo.placa if unidad.vehiculo else unidad.placa
    base = {"placa": placa, "pegasus_id": unidad.pegasus_id,
            "reporte_en": _iso(local(unidad.reporte_en, pais)),
            "hace_min": (int((ahora - unidad.reporte_en).total_seconds() // 60)
                         if unidad.reporte_en else None)}

    def desde(estado: str, instante: datetime | None, **extra) -> dict:
        cuando = local(instante, pais)
        return {**base, "estado": estado, "desde": _iso(cuando),
                "desde_dias": dias_atras(cuando, hoy), **extra}

    # El inhibidor antes que el silencio: lo que hace un inhibidor es
    # justo callar al equipo, y "no reporta" diria menos que "inhibidor".
    if unidad.inhibidor:
        return desde("inhibidor", unidad.inhibidor_desde)
    if reglas.callada(unidad.reporte_en, ahora):
        return desde("sin_senal", unidad.reporte_en)
    if unidad.corriente is False:
        return desde("sin_corriente", unidad.corriente_desde)
    if unidad.en_movimiento:
        return {**base, "estado": "en_movimiento",
                "velocidad_kmh": unidad.velocidad_kmh, "desde": None}
    if unidad.encendida is False:
        return desde("apagada", unidad.encendida_desde)
    return desde("detenida", unidad.parada_desde, encendida=unidad.encendida,
                 parada_min=(int((ahora - unidad.parada_desde).total_seconds()
                                 // 60) if unidad.parada_desde else None))


def lineas_del_dia(db: Session, jornada: m.Jornada, pais: m.Pais | None,
                   ahora: datetime | None = None) -> list[dict]:
    """Lo que dice cada unidad del dia que tiene GPS."""
    salida = []
    for a in _vigentes(jornada):
        dice = linea(unidad_de(db, a.vehiculo_id), pais, ahora)
        if dice:
            salida.append(dice)
    return salida


# ================================================================ la lectura

def _grupos(db: Session, cliente, ahora: datetime) -> list[m.GrupoGps]:
    """Los grupos del `.env`, uno por pais, con su numero de Pegasus."""
    config = grupos_configurados()
    paises = {p.codigo: p for p in db.query(m.Pais).all()}
    filas, sin_numero = [], []
    for codigo, nombre in config.items():
        pais = paises.get(codigo)
        if not pais:
            continue
        fila = db.query(m.GrupoGps).filter_by(pais_id=pais.id).first()
        if not fila:
            fila = m.GrupoGps(pais_id=pais.id, nombre=nombre)
            db.add(fila)
            db.flush()
        elif fila.nombre != nombre:
            fila.nombre, fila.pegasus_id = nombre, None
        filas.append(fila)
        if fila.pegasus_id is None:
            sin_numero.append(fila)
    if sin_numero:
        # De los demas grupos no se guarda ni el nombre.
        todos = cliente.grupos()
        for fila in sin_numero:
            g = next((g for g in todos
                      if _normal(g.get("name")) == _normal(fila.nombre)), None)
            if g and g.get("id") is not None:
                fila.pegasus_id = int(g["id"])
                fila.error = None
            else:
                fila.error = (f"Pegasus no tiene un grupo que se llame "
                              f"«{fila.nombre}», o el usuario no lo ve")[:300]
                fila.error_en = ahora
    return filas


def _placas_de(db: Session, pais_id: int) -> dict[str, int]:
    """Las unidades propias de ese pais, por placa escrita sin guiones."""
    filas = (db.query(m.Vehiculo)
             .join(m.Plaza, m.Vehiculo.plaza_id == m.Plaza.id)
             .filter(m.Plaza.pais_id == pais_id,
                     m.Vehiculo.rentado.is_(False)).all())
    salida: dict[str, int] = {}
    repetidas = set()
    for v in filas:
        clave = reglas.normal_placa(v.placa)
        if not clave:
            continue
        if clave in salida:
            repetidas.add(clave)
        salida[clave] = v.id
    for clave in repetidas:
        salida.pop(clave, None)
    return salida


def _leer_unidades(db: Session, cliente, grupo: m.GrupoGps,
                   ahora: datetime) -> int:
    crudas = cliente.unidades(grupo.pegasus_id)
    estados = []
    for u in crudas:
        try:
            estados.append(reglas.estado_de_la_unidad(u))
        except (KeyError, TypeError, ValueError):
            continue
    # Una placa que viene dos veces en Pegasus no se liga a ninguna: no
    # hay como saber cual es la de verdad.
    cuantas: dict[str, int] = {}
    for e in estados:
        if e["placa_normal"]:
            cuantas[e["placa_normal"]] = cuantas.get(e["placa_normal"], 0) + 1
    placas = _placas_de(db, grupo.pais_id)

    vistas = set()
    for e in estados:
        vistas.add(e["pegasus_id"])
        fila = (db.query(m.UnidadGps)
                .filter_by(pegasus_id=e["pegasus_id"]).first())
        if not fila:
            fila = m.UnidadGps(pegasus_id=e["pegasus_id"], grupo_id=grupo.id)
            db.add(fila)
        antes_andaba, antes_parada = fila.en_movimiento, fila.parada_desde
        for campo, valor in e.items():
            if campo != "pegasus_id":
                setattr(fila, campo, valor)
        # Si el equipo no dice desde cuando esta parada, se lleva la
        # cuenta aqui: la primera lectura parada despues de verla andar.
        if e["en_movimiento"] is False and e["parada_desde"] is None:
            if antes_andaba is False and antes_parada:
                fila.parada_desde = antes_parada
            elif antes_andaba:
                fila.parada_desde = e["reporte_en"]
        fila.grupo_id = grupo.id
        fila.en_el_grupo = True
        fila.leida_en = ahora
        clave = e["placa_normal"]
        fila.vehiculo_id = (placas.get(clave)
                            if clave and cuantas.get(clave) == 1 else None)
    # La que ya no viene en el grupo deja de contarse, sin borrarse.
    for fila in (db.query(m.UnidadGps)
                 .filter(m.UnidadGps.grupo_id == grupo.id).all()):
        if fila.pegasus_id not in vistas:
            fila.en_el_grupo = False
            fila.vehiculo_id = None
    grupo.leido_en = ahora
    grupo.unidades = len(vistas)
    grupo.error = None
    return len(vistas)


def _jornadas_en_ventana(db: Session, relojes: reloj.Relojes
                         ) -> list[tuple[m.Jornada, str]]:
    """Las jornadas en las que la unidad importa: las que van en camino
    al punto (dos horas antes, como el primer toque) y las que ya
    arrancaron."""
    from app import trayecto

    hoy = datetime.now().date()
    filas = (db.query(m.Jornada)
             .filter(m.Jornada.estatus.in_(VIVAS),
                     m.Jornada.fecha >= hoy - timedelta(days=1),
                     m.Jornada.fecha <= hoy + timedelta(days=1)).all())
    salida = []
    for j in filas:
        if not j.equipo:
            continue
        if j.estatus in m.ARRANCADAS:
            salida.append((j, "servicio"))
            continue
        suyo = relojes.de_la_jornada(j)
        minutos = (trayecto.hora_de_estar(db, j) - suyo).total_seconds() / 60
        if -180 <= minutos <= trayecto.TOQUES[0]:
            salida.append((j, "camino"))
    return salida


def leer(db: Session, cliente=None, ahora: datetime | None = None) -> dict:
    """La vuelta de cada dos minutos."""
    cliente = cliente or conexion.desde_la_configuracion()
    if cliente is None:
        return {"conectado": False}
    ahora = ahora or _utc()
    relojes = reloj.Relojes(db, ahora)
    resultado: dict = {"conectado": True}
    try:
        grupos = _grupos(db, cliente, ahora)
        ventana = _jornadas_en_ventana(db, relojes)
        leidas = 0
        for g in grupos:
            if g.pegasus_id is None:
                continue
            reciente = (g.leido_en is not None
                        and (ahora - g.leido_en).total_seconds() / 60
                        < MINUTOS_LECTURA_TRANQUILA)
            if ventana or not reciente:
                leidas += _leer_unidades(db, cliente, g, ahora)
        db.flush()
        resultado["unidades"] = leidas
        resultado["panicos"] = _revisar_panicos(db, cliente, grupos, ahora)
        resultado["alertas"] = _alertas_de_la_unidad(db, relojes, ventana,
                                                     ahora)
        resultado["camino"] = _camino(db, relojes, ventana, ahora)
        resultado["testigos"] = _testimonios(db, cliente, ahora)
        db.commit()
    except conexion.NoResponde as e:
        db.rollback()
        for g in db.query(m.GrupoGps).all():
            g.error, g.error_en = str(e)[:300], ahora
        db.commit()
        registro.warning("Pegasus: %s", e)
        resultado["error"] = str(e)
    return resultado


# ================================================================ el panico

def _jornada_de_la_unidad(db: Session, vehiculo_id: int,
                          cuando: datetime) -> m.Jornada | None:
    """El dia en que va esa unidad a esa hora (hora de pared del pais):
    del camino al punto a la marca de fin."""
    from app import trayecto

    filas = (db.query(m.AsignacionVehiculo)
             .join(m.Jornada, m.AsignacionVehiculo.jornada_id == m.Jornada.id)
             .filter(m.AsignacionVehiculo.vehiculo_id == vehiculo_id,
                     m.Jornada.fecha >= cuando.date() - timedelta(days=1),
                     m.Jornada.fecha <= cuando.date() + timedelta(days=1),
                     m.Jornada.estatus != m.EstatusJornada.CANCELADA)
             .all())
    for a in filas:
        if a.relevado_en and a.relevado_en <= cuando:
            continue
        j = a.jornada
        empieza = trayecto.hora_de_estar(db, j) - timedelta(
            minutes=trayecto.TOQUES[0])
        if cuando < empieza:
            continue
        if j.estatus == m.EstatusJornada.TERMINADA:
            if j.fin_real and cuando <= j.fin_real:
                return j
            continue
        return j
    return None


def _alertar_panico(db: Session, grupo: m.GrupoGps, e: dict,
                    cuando: datetime) -> bool:
    vid = e.get("vid")
    try:
        vid = int(vid)
    except (TypeError, ValueError):
        return False
    origen = f"pegasus:{vid}:{cuando:%Y%m%d%H%M%S}"
    if db.query(m.AlertaIncidencia.id).filter_by(origen=origen).first():
        return False
    unidad = db.query(m.UnidadGps).filter_by(pegasus_id=vid).first()
    vehiculo_id = unidad.vehiculo_id if unidad else None
    placa = (unidad.vehiculo.placa if unidad and unidad.vehiculo
             else (unidad.placa if unidad else None)) or f"Pegasus {vid}"
    pais = grupo.pais
    jornada = (_jornada_de_la_unidad(db, vehiculo_id, local(cuando, pais))
               if vehiculo_id else None)
    reporta = None
    if jornada:
        conductor = quien_maneja(jornada, vehiculo_id)
        reporta = conductor or next(
            (a.persona_id for a in la_traen(jornada, vehiculo_id)), None)
    lat, lon = reglas._numero(e.get("lat")), reglas._numero(e.get("lon"))
    if lat == 0 and lon == 0:
        lat = lon = None
    db.add(m.AlertaIncidencia(
        jornada_id=jornada.id if jornada else None,
        servicio_id=jornada.equipo.servicio_id if jornada else None,
        reporta_persona_id=reporta,
        canal=m.CanalAlerta.BOTON_VEHICULO,
        descripcion=(f"Botón de pánico de la unidad {placa}"
                     + ("" if jornada else
                        ". La unidad no trae servicio en este momento")
                     + ".")[:600],
        lat=lat, lon=lon, reportada_en=cuando,
        vehiculo_id=vehiculo_id, origen=origen))
    db.flush()
    return True


def _revisar_panicos(db: Session, cliente, grupos: list[m.GrupoGps],
                     ahora: datetime) -> int:
    """El evento "panic" de las unidades de los grupos, desde donde se
    quedo la vuelta anterior. Cada panico suena una sola vez."""
    nuevos = 0
    for grupo in grupos:
        if grupo.pegasus_id is None:
            continue
        ids = [u.pegasus_id for u in db.query(m.UnidadGps)
               .filter_by(grupo_id=grupo.id, en_el_grupo=True).all()]
        if not ids:
            continue
        desde = grupo.panico_hasta or (ahora - timedelta(minutes=10))
        desde = max(desde - timedelta(minutes=1), ahora - timedelta(days=1))
        eventos = cliente.eventos(
            ids, reglas.duracion_hacia_atras(desde, ahora),
            etiquetas=reglas.PANICO,
            campos="vid,event_time,label,lat,lon,mph", tope=200)
        for e in eventos:
            if str(e.get("label") or "").lower() != reglas.PANICO:
                continue
            cuando = reglas.momento(e.get("event_time"))
            if cuando is None or cuando < desde:
                continue
            if _alertar_panico(db, grupo, e, cuando):
                nuevos += 1
        grupo.panico_hasta = ahora
    return nuevos


def revisar_panicos(db: Session, cliente=None,
                    ahora: datetime | None = None) -> dict:
    """Lo que despierta el aviso de Pegasus: solo la revision de
    panicos, y no dos veces en veinte segundos."""
    cliente = cliente or conexion.desde_la_configuracion()
    if cliente is None:
        return {"conectado": False}
    ahora = ahora or _utc()
    ultimos = [g.panico_hasta for g in db.query(m.GrupoGps).all()
               if g.panico_hasta]
    if ultimos and (ahora - max(ultimos)).total_seconds() < SEGUNDOS_ENTRE_AVISOS:
        return {"conectado": True, "panicos": 0, "reciente": True}
    try:
        grupos = _grupos(db, cliente, ahora)
        nuevos = _revisar_panicos(db, cliente, grupos, ahora)
        db.commit()
    except conexion.NoResponde as e:
        db.rollback()
        return {"conectado": True, "error": str(e)}
    return {"conectado": True, "panicos": nuevos}


# ================================================================ inhibidor y corriente

def _abierta(db: Session, jornada_id: int, vehiculo_id: int,
             tipo: m.TipoAlerta) -> m.Alerta | None:
    return (db.query(m.Alerta)
            .filter_by(jornada_id=jornada_id, vehiculo_id=vehiculo_id,
                       tipo=tipo, atendida=False).first())


def _alertas_de_la_unidad(db: Session, relojes: reloj.Relojes,
                          ventana: list, ahora: datetime) -> int:
    """Inhibidor y corriente cortada, solo del camino al punto a la
    marca de fin. Se resuelven solas cuando la unidad vuelve a estar
    bien, o cuando termina el servicio: fuera de esa ventana las vigila
    Centauro Satelital."""
    nuevas = 0
    vigiladas = set()
    for jornada, _fase in ventana:
        pais = relojes.pais(reloj.pais_de_la_jornada(jornada))
        for a in _vigentes(jornada):
            unidad = unidad_de(db, a.vehiculo_id)
            if not unidad:
                continue
            vigiladas.add((jornada.id, a.vehiculo_id))
            placa = a.vehiculo.placa if a.vehiculo else unidad.placa
            casos = []
            if unidad.inhibidor:
                casos.append((m.TipoAlerta.INHIBIDOR,
                              f"La unidad {placa} detecto un inhibidor de "
                              f"senal a las "
                              f"{local(unidad.inhibidor_desde or ahora, pais):%H:%M}"))
            if (unidad.corriente is False and unidad.corriente_desde
                    and (ahora - unidad.corriente_desde).total_seconds() / 60
                    > reglas.MINUTOS_SIN_CORRIENTE):
                casos.append((m.TipoAlerta.SIN_CORRIENTE,
                              f"La unidad {placa} perdio la corriente a las "
                              f"{local(unidad.corriente_desde, pais):%H:%M} y "
                              "sigue con su bateria"))
            for tipo, mensaje in casos:
                if _abierta(db, jornada.id, a.vehiculo_id, tipo):
                    continue
                gente = la_traen(jornada, a.vehiculo_id)
                db.add(m.Alerta(
                    jornada_id=jornada.id, tipo=tipo,
                    persona_id=gente[0].persona_id if gente else None,
                    vehiculo_id=a.vehiculo_id, mensaje=(mensaje + ".")[:400]))
                nuevas += 1
    db.flush()

    # Las que ya no dicen nada verdadero.
    en_ventana = {j.id for j, _fase in ventana}
    for alerta in (db.query(m.Alerta)
                   .filter(m.Alerta.tipo.in_(DE_LA_UNIDAD),
                           m.Alerta.atendida.is_(False)).all()):
        unidad = unidad_de(db, alerta.vehiculo_id)
        pais = relojes.pais(reloj.pais_de_la_jornada(alerta.jornada))
        hora = f"{local(ahora, pais):%H:%M}"
        resolucion = None
        if alerta.jornada_id not in en_ventana:
            resolucion = "Se cerro sola: termino el servicio."
        elif (alerta.jornada_id, alerta.vehiculo_id) not in vigiladas:
            resolucion = "Se cerro sola: la unidad salio del servicio."
        elif alerta.tipo == m.TipoAlerta.INHIBIDOR and unidad and not unidad.inhibidor:
            resolucion = (f"Se resolvio sola: la unidad volvio a mandar su "
                          f"posicion a las {hora}.")
        elif (alerta.tipo == m.TipoAlerta.SIN_CORRIENTE and unidad
              and unidad.corriente is not False):
            resolucion = (f"Se resolvio sola: la unidad recupero la "
                          f"corriente a las {hora}.")
        if resolucion:
            alerta.atendida = True
            alerta.resolucion = resolucion
    return nuevas


# ================================================================ el camino

def _camino(db: Session, relojes: reloj.Relojes, ventana: list,
            ahora: datetime) -> int:
    """Lo que dice la unidad de quien la trae al punto."""
    from app import trayecto

    movidos = 0
    for jornada, fase in ventana:
        if fase != "camino" or jornada.origen_lat is None:
            continue
        pais = relojes.pais(reloj.pais_de_la_jornada(jornada))
        suyo = relojes.de_la_jornada(jornada)
        faltan = (trayecto.hora_de_estar(db, jornada) - suyo).total_seconds() / 60
        for a in _vigentes(jornada):
            unidad = unidad_de(db, a.vehiculo_id)
            if not unidad:
                continue
            for quien in la_traen(jornada, a.vehiculo_id):
                via = (db.query(m.Trayecto)
                       .filter_by(jornada_id=jornada.id,
                                  persona_id=quien.persona_id).first())
                if not via:
                    via = m.Trayecto(jornada_id=jornada.id,
                                     persona_id=quien.persona_id)
                    db.add(via)
                    db.flush()
                if via.estado == m.EstadoTrayecto.LLEGO:
                    continue
                _evaluar(db, via, jornada, unidad, pais, faltan, ahora)
                movidos += 1
    return movidos


def _evaluar(db: Session, via: m.Trayecto, jornada: m.Jornada,
             unidad: m.UnidadGps, pais: m.Pais | None, faltan: float,
             ahora: datetime) -> None:
    from app import trayecto

    via.unidad_vehiculo_id = unidad.vehiculo_id
    if (reglas.callada(unidad.reporte_en, ahora)
            or unidad.lat is None or unidad.lon is None):
        via.unidad_estado = "sin_senal"
        via.unidad_desde = local(unidad.reporte_en, pais)
        return

    leida = local(unidad.reporte_en, pais)
    distancia = distancia_metros(unidad.lat, unidad.lon,
                                 jornada.origen_lat, jornada.origen_lon)
    anterior, minutos_entre = via.unidad_distancia_anterior_m, None
    if via.unidad_leida_en is None or leida > via.unidad_leida_en:
        # Una lectura nueva: la de antes pasa a ser la anterior.
        if via.unidad_leida_en is not None:
            anterior = via.unidad_distancia_m
            via.unidad_anterior_en = via.unidad_leida_en
        via.unidad_distancia_anterior_m = anterior
        via.unidad_distancia_m = distancia
        via.unidad_leida_en = leida
    if via.unidad_anterior_en and via.unidad_leida_en:
        minutos_entre = (via.unidad_leida_en
                         - via.unidad_anterior_en).total_seconds() / 60

    estado, motivo = reglas.evaluar_camino(
        via.unidad_distancia_m, via.unidad_distancia_anterior_m,
        minutos_entre, faltan, unidad.en_movimiento,
        unidad.encendida is False)
    via.unidad_estado = estado
    via.unidad_apagada = unidad.encendida is False
    if unidad.en_movimiento:
        via.unidad_desde = None
    elif unidad.encendida is False:
        via.unidad_desde = local(unidad.encendida_desde, pais)
    else:
        via.unidad_desde = local(unidad.parada_desde, pais)

    if motivo:
        trayecto._alertar(db, via, jornada, motivo)
    elif estado == "viene":
        # La unidad contesta por el: el silencio del telefono ya no
        # dice nada, y la alerta de "no contesta" se cierra con lo que
        # la contesto.
        placa = unidad.vehiculo.placa if unidad.vehiculo else unidad.placa
        if trayecto.resolver_alertas(
                db, jornada.id, via.persona_id,
                f"Se resolvio sola: la unidad {placa} viene hacia el punto "
                f"({leida:%H:%M})."):
            via.alertado = False


def contesta_la_unidad(via: m.Trayecto, ahora_local: datetime) -> bool:
    """Si la unidad que trae viene hacia el punto, con una lectura de
    hace poco. Entonces no se le toca el telefono a quien va manejando:
    si todo va bien, ninguna noticia."""
    return bool(via.unidad_estado in ("viene", "en_el_punto")
                and via.unidad_leida_en
                and (ahora_local - via.unidad_leida_en).total_seconds() / 60
                <= reglas.MINUTOS_SIN_SENAL)


def estado_del_camino(via: m.Trayecto, ahora_local: datetime) -> str:
    """Lo que se ensena: la unidad manda para quien la trae, el telefono
    para lo demas."""
    fresca = (via.unidad_leida_en is not None
              and (ahora_local - via.unidad_leida_en).total_seconds() / 60
              <= reglas.MINUTOS_SIN_SENAL)
    if fresca and via.unidad_estado in ("no_sale", "no_llega"):
        return via.unidad_estado
    if (fresca and via.unidad_estado == "viene"
            and via.estado in (m.EstadoTrayecto.ESPERANDO,
                               m.EstadoTrayecto.SIN_RESPUESTA)):
        return m.EstadoTrayecto.EN_CAMINO.value
    return via.estado.value if hasattr(via.estado, "value") else via.estado


# ================================================================ el testigo

def _su_unidad(jornada: m.Jornada, persona_id: int,
               cuando: datetime) -> int | None:
    """La unidad en que iba esa persona a esa hora."""
    suyas = revision.mis_unidades(jornada, persona_id)
    for a in jornada.vehiculos:
        if a.vehiculo_id not in suyas:
            continue
        if a.relevado_en is None or a.relevado_en > cuando:
            return a.vehiculo_id
    return None


def _ultimo_punto(db: Session, hito: m.Hito) -> tuple | None:
    """Donde estaba el principal la ultima vez que se supo: la marca
    anterior al fin con posicion, o el punto de encuentro."""
    previa = (db.query(m.Hito)
              .filter(m.Hito.jornada_id == hito.jornada_id,
                      m.Hito.id != hito.id,
                      m.Hito.anulado_en.is_(None),
                      m.Hito.lat.isnot(None),
                      m.Hito.marcado_en <= hito.marcado_en,
                      m.Hito.tipo != m.TipoHito.FIN_SERVICIO)
              .order_by(m.Hito.marcado_en.desc()).first())
    if previa:
        return previa.lat, previa.lon
    j = hito.jornada
    if j.origen_lat is not None:
        return j.origen_lat, j.origen_lon
    return None


def _testimonios(db: Session, cliente, ahora: datetime) -> int:
    """Lo que decia la unidad en cada marca reciente."""
    hechos = 0
    desde = datetime.now() - timedelta(hours=HORAS_PARA_EL_TESTIGO + 12)
    pendientes = (db.query(m.Hito)
                  .filter(m.Hito.unidad_revisada_en.is_(None),
                          m.Hito.marcado_en >= desde)
                  .order_by(m.Hito.marcado_en).all())
    for hito in pendientes:
        jornada = hito.jornada
        pais = db.get(m.Pais, reloj.pais_de_la_jornada(jornada))
        marca = instante(hito.marcado_en, pais)
        edad = (ahora - marca).total_seconds() / 60
        if edad > HORAS_PARA_EL_TESTIGO * 60:
            hito.unidad_revisada_en = ahora
            continue
        if edad < 2:
            continue          # que Pegasus alcance a tener la posicion
        # Lo firmado desde una oficina no tiene de donde compararse.
        if hito.anulado_en or hito.registrado_a_mano_en:
            hito.unidad_revisada_en = ahora
            continue
        vehiculo_id = _su_unidad(jornada, hito.persona_id, hito.marcado_en)
        unidad = unidad_de(db, vehiculo_id)
        hito.unidad_vehiculo_id = vehiculo_id
        if not unidad:
            hito.unidad_revisada_en = ahora
            continue
        if hito.tipo == m.TipoHito.FIN_SERVICIO:
            tramos = reglas.tramos_ordenados(cliente.tramos(
                [unidad.pegasus_id],
                reglas.duracion_hacia_atras(marca - timedelta(hours=12),
                                            ahora)))
            parada = reglas.parada_en(tramos, marca, ahora)
            punto = _ultimo_punto(db, hito)
            if parada and parada["lat"] is not None and punto:
                hito.unidad_guardada_en = local(parada["inicio"], pais)
                hito.unidad_guardada_m = distancia_metros(
                    parada["lat"], parada["lon"], punto[0], punto[1])
        if hito.lat is not None and hito.lon is not None:
            eventos = cliente.eventos(
                [unidad.pegasus_id],
                reglas.duracion_hacia_atras(marca - timedelta(minutes=6),
                                            ahora),
                campos="vid,event_time,lat,lon,mph")
            cercano = reglas.mas_cercano(eventos, marca)
            if cercano:
                hito.unidad_distancia_m = distancia_metros(
                    cercano["_lat"], cercano["_lon"], hito.lat, hito.lon)
        hito.unidad_revisada_en = ahora
        hechos += 1
    return hechos


def testimonio(hito: m.Hito) -> dict | None:
    """Lo que dijo la unidad de esa marca, para la bitacora y el cierre."""
    if not hito.unidad_revisada_en or not hito.unidad_vehiculo_id:
        return None
    if hito.tipo == m.TipoHito.FIN_SERVICIO:
        veredicto = reglas.veredicto_fin(hito.marcado_en,
                                         hito.unidad_guardada_en,
                                         hito.unidad_guardada_m,
                                         hito.unidad_distancia_m)
    else:
        veredicto = reglas.veredicto_marca(hito.unidad_distancia_m)
    if veredicto is None:
        return None
    guardada = (veredicto == "alerta"
                and hito.tipo == m.TipoHito.FIN_SERVICIO
                and hito.unidad_guardada_en is not None)
    return {
        "placa": hito.unidad.placa if hito.unidad else None,
        "veredicto": veredicto,
        "distancia_m": hito.unidad_distancia_m,
        "guardada_en": _iso(hito.unidad_guardada_en) if guardada else None,
        "guardada_m": hito.unidad_guardada_m if guardada else None,
    }


# ================================================================ el dia

def cerrar_dias(db: Session, cliente=None, ahora: datetime | None = None) -> dict:
    """Lo que recorrio cada unidad en el dia, y lo que conto de su
    manejo. Corre cada hora; espera dos horas despues del fin para que
    la unidad se haya guardado."""
    cliente = cliente or conexion.desde_la_configuracion()
    if cliente is None:
        return {"conectado": False}
    ahora = ahora or _utc()
    desde_dia = (ahora - timedelta(days=DIAS_PARA_CERRAR)).date()
    filas = (db.query(m.AsignacionVehiculo)
             .join(m.Jornada, m.AsignacionVehiculo.jornada_id == m.Jornada.id)
             .filter(m.Jornada.estatus == m.EstatusJornada.TERMINADA,
                     m.Jornada.fin_real.isnot(None),
                     m.Jornada.fecha >= desde_dia,
                     m.AsignacionVehiculo.gps_cerrado_en.is_(None)).all())
    cerrados = 0
    try:
        for a in filas:
            if _cerrar_uno(db, cliente, a, ahora):
                cerrados += 1
        db.commit()
    except conexion.NoResponde as e:
        db.rollback()
        return {"conectado": True, "error": str(e)}
    return {"conectado": True, "cerrados": cerrados}


def _cerrar_uno(db: Session, cliente, a: m.AsignacionVehiculo,
                ahora: datetime) -> bool:
    jornada = a.jornada
    pais = db.get(m.Pais, reloj.pais_de_la_jornada(jornada))
    fin = instante(jornada.fin_real, pais)
    if (ahora - fin).total_seconds() / 3600 < HORAS_DESPUES_DEL_FIN:
        return False
    unidad = unidad_de(db, a.vehiculo_id)
    if not unidad:
        a.gps_cerrado_en = ahora
        return False
    marca = (db.query(m.Hito)
             .filter_by(jornada_id=jornada.id,
                        tipo=m.TipoHito.LLEGADA_ORIGEN)
             .filter(m.Hito.anulado_en.is_(None))
             .order_by(m.Hito.marcado_en).first())
    llegada = instante(marca.marcado_en if marca
                       else (jornada.inicio_real or jornada.inicio_programado),
                       pais)
    tramos = reglas.tramos_ordenados(cliente.tramos(
        [unidad.pegasus_id],
        reglas.duracion_hacia_atras(llegada - timedelta(hours=8), ahora)))
    ventana = reglas.ventana_del_dia(tramos, llegada, fin, ahora)
    if ventana:
        desde, hasta = ventana
        # La que salio a media jornada se cuenta hasta que salio, y la
        # que entro, desde que entro.
        if a.relevado_en:
            hasta = min(hasta, instante(a.relevado_en, pais))
        releva = next((x for x in jornada.vehiculos
                       if x.relevado_por_vehiculo_id == a.vehiculo_id
                       and x.relevado_en), None)
        if releva:
            desde = max(desde, instante(releva.relevado_en, pais))
        if hasta > desde:
            eventos = cliente.eventos(
                [unidad.pegasus_id], reglas.duracion_hacia_atras(desde, ahora),
                etiquetas=",".join((reglas.EXCESO, *reglas.BRUSCOS)),
                campos="vid,event_time,label")
            a.km_gps = reglas.km_en(tramos, desde, hasta, ahora)
            a.km_gps_desde = local(desde, pais)
            a.km_gps_hasta = local(hasta, pais)
            a.excesos_gps, a.bruscos_gps = reglas.contar_manejo(
                eventos, desde, hasta)
    a.gps_cerrado_en = ahora
    return a.km_gps is not None


# ================================================================ la gasolina

def _precio(db: Session, pais_id: int, dia: date):
    fila = (db.query(m.ParametroCombustible)
            .filter(m.ParametroCombustible.pais_id == pais_id,
                    m.ParametroCombustible.activo.is_(True),
                    m.ParametroCombustible.vigencia_desde <= dia)
            .order_by(m.ParametroCombustible.vigencia_desde.desc()).first())
    if not fila:
        fila = (db.query(m.ParametroCombustible)
                .filter(m.ParametroCombustible.pais_id == pais_id,
                        m.ParametroCombustible.activo.is_(True))
                .order_by(m.ParametroCombustible.vigencia_desde.desc())
                .first())
    return fila


def gasolina_de(db: Session, suyos: list) -> dict | None:
    """La gasolina que comprobo una persona contra los kilometros de la
    unidad que trajo (tablero 5). Nada si no comprobo gasolina, o si a
    alguno de sus dias le falta el dato del GPS: comparar todo lo
    comprobado contra parte de los kilometros acusaria de mas."""
    if not suyos:
        return None
    persona_id = suyos[0].persona_id
    comprobado = sum((Decimal(str(c.monto or 0)) for v in suyos
                      for c in v.comprobantes
                      if c.concepto == m.ConceptoViatico.COMBUSTIBLE
                      and not c.rechazado), Decimal("0"))
    if comprobado <= 0:
        return None
    depositado = sum((Decimal(str(c.monto or 0)) for v in suyos
                      for c in v.conceptos
                      if c.concepto == m.ConceptoViatico.COMBUSTIBLE),
                     Decimal("0"))
    jornadas = {v.jornada.id: v.jornada for v in suyos if v.jornada}
    km = Decimal("0")
    cuenta = Decimal("0")
    km_estimados = 0
    placas, rendimientos = [], set()
    parametro = None
    for jornada in jornadas.values():
        servicio = jornada.equipo.servicio
        suyas = set(revision.mis_unidades(jornada, persona_id))
        for a in jornada.vehiculos:
            if a.vehiculo_id not in suyas:
                continue
            if a.km_gps is None:
                return None
            parametro = _precio(db, servicio.pais_id, jornada.fecha)
            categoria = a.vehiculo.categoria if a.vehiculo else None
            if not parametro or not categoria:
                return None
            parte = reglas.cuenta_gasolina(a.km_gps,
                                           categoria.rendimiento_km_litro,
                                           parametro.precio_litro,
                                           parametro.holgura_pct)
            if parte is None:
                return None
            km += Decimal(str(a.km_gps))
            cuenta += parte
            rendimientos.add(Decimal(str(categoria.rendimiento_km_litro)))
            if a.vehiculo.placa not in placas:
                placas.append(a.vehiculo.placa)
        km_estimados += jornada.km_estimados or 0
    if not placas:
        return None
    return {
        "comprobado": comprobado,
        "depositado": depositado,
        "km_estimados": km_estimados,
        "km": km,
        "cuenta": cuenta,
        "de_mas": max(Decimal("0"), comprobado - cuenta),
        "excede": comprobado > cuenta,
        "placas": placas,
        "rendimiento": (next(iter(rendimientos))
                        if len(rendimientos) == 1 else None),
        "precio": Decimal(str(parametro.precio_litro)) if parametro else None,
        "holgura": Decimal(str(parametro.holgura_pct)) if parametro else None,
    }


def con_gasolina(db: Session, personas: list[dict], viaticos: list) -> list[dict]:
    """Le pega a cada ficha del dinero su cuenta de gasolina."""
    from app import bolson

    por_persona = {s[0].persona_id: s for s in bolson.agrupar(viaticos)}
    for p in personas:
        suyos = por_persona.get(p.get("persona_id"))
        p["gasolina"] = gasolina_de(db, suyos) if suyos else None
    return personas


# ================================================================ el cierre

def _hm(minutos: int) -> str:
    h, mm = divmod(max(0, int(minutos)), 60)
    return f"{h} h {mm:02d} min" if h else f"{mm} min"


def observaciones(db: Session, jornadas: list, viaticos: list) -> list[dict]:
    """Lo que la unidad dice que no cuadra, para "Para revisar". Nunca
    frena el visto bueno: la unidad no castiga a nadie sola; senala, y
    el consultor decide."""
    from app import bolson

    salida = []
    for jornada in jornadas:
        if jornada.estatus == m.EstatusJornada.CANCELADA:
            continue
        for hito in (db.query(m.Hito)
                     .filter(m.Hito.jornada_id == jornada.id,
                             m.Hito.anulado_en.is_(None))
                     .order_by(m.Hito.marcado_en).all()):
            dice = testimonio(hito)
            if not dice or dice["veredicto"] != "alerta":
                continue
            fecha = f"{hito.marcado_en:%d/%m}"
            if hito.tipo == m.TipoHito.FIN_SERVICIO and dice["guardada_en"]:
                guardada = hito.unidad_guardada_en
                minutos = int((hito.marcado_en - guardada).total_seconds() // 60)
                extra = None
                if jornada.fin_programado and hito.marcado_en > jornada.fin_programado:
                    extra = int((hito.marcado_en - max(guardada,
                                                       jornada.fin_programado))
                                .total_seconds() // 60)
                km = round((hito.unidad_guardada_m or 0) / 1000, 1)
                mensaje = (f"la marca es de las {hito.marcado_en:%H:%M} y la "
                           f"unidad {dice['placa']} se guardo a las "
                           f"{guardada:%H:%M}, a {km} km del ultimo punto. "
                           + (f"De las horas extra, {_hm(extra)} caen con la "
                              "unidad ya guardada." if extra else
                              f"Entre una y otra hay {_hm(minutos)}."))
                salida.append({
                    "nivel": "revisar", "asunto": "Fin contra la unidad",
                    "mensaje": f"Fin del servicio del {fecha}: {mensaje}",
                    "accion": ("Si la marca esta mal, corrigela en la "
                               "bitacora de ese dia."),
                    "clave": "fin_extra" if extra else "fin",
                    "datos": {"fecha": fecha,
                              "marca": f"{hito.marcado_en:%H:%M}",
                              "guardada": f"{guardada:%H:%M}",
                              "placa": dice["placa"], "km": km,
                              "tiempo": _hm(extra if extra else minutos)}})
            elif dice["distancia_m"] is not None:
                km = round(dice["distancia_m"] / 1000, 1)
                salida.append({
                    "nivel": "revisar", "asunto": "Marca contra la unidad",
                    "mensaje": (f"{hito.tipo.value} del {fecha} a las "
                                f"{hito.marcado_en:%H:%M}: la unidad "
                                f"{dice['placa']} estaba a {km} km de donde "
                                "se marco."),
                    "accion": "Pregunta con quien iba y en que se movio.",
                    "clave": "marca",
                    "datos": {"tipo": hito.tipo.value, "fecha": fecha,
                              "hora": f"{hito.marcado_en:%H:%M}",
                              "placa": dice["placa"], "km": km}})

    for suyos in bolson.agrupar(viaticos):
        cuenta = gasolina_de(db, suyos)
        if not cuenta or not cuenta["excede"]:
            continue
        persona = suyos[0].persona
        nombre = persona.nombre if persona else str(suyos[0].persona_id)
        moneda = suyos[0].moneda.value if suyos[0].moneda else None
        salida.append({
            "nivel": "revisar", "asunto": "Gasolina contra kilometros",
            "mensaje": (f"Gasolina de {nombre}: comprobo "
                        f"${cuenta['comprobado']:,.0f} y los "
                        f"{cuenta['km']:,.0f} km que recorrio la unidad dan "
                        f"${cuenta['cuenta']:,.0f}."),
            "accion": "Revisa sus tickets abajo, en Viaticos del personal.",
            "persona_id": suyos[0].persona_id,
            "clave": "gasolina",
            "datos": {"nombre": nombre, "comprobado": str(cuenta["comprobado"]),
                      "cuenta": str(cuenta["cuenta"]),
                      "km": f"{cuenta['km']:,.0f}", "moneda": moneda}})
    return salida


# ================================================================ el manejo

def manejo_de(db: Session, persona_id: int, desde: tuple[int, int],
              puntos_por_evento) -> dict:
    """Los excesos y los arrancones o frenadas bruscas por cada mil km
    al volante en servicio (tablero 6). Solo los dias en que manejo
    esa persona; al escolta no le aplica."""
    asignaciones = (db.query(m.AsignacionPersonal)
                    .join(m.Jornada,
                          m.AsignacionPersonal.jornada_id == m.Jornada.id)
                    .filter(m.AsignacionPersonal.persona_id == persona_id,
                            m.Jornada.estatus == m.EstatusJornada.TERMINADA)
                    .all())
    km = Decimal("0")
    excesos = bruscos = 0
    for asignacion in asignaciones:
        jornada = asignacion.jornada
        if (jornada.fecha.year, jornada.fecha.month) < desde:
            continue
        for a in jornada.vehiculos:
            if a.km_gps is None or not a.km_gps:
                continue
            if quien_maneja(jornada, a.vehiculo_id) != persona_id:
                continue
            km += Decimal(str(a.km_gps))
            excesos += a.excesos_gps or 0
            bruscos += a.bruscos_gps or 0
    if km < 50:
        return {"aplica": False,
                "detalle": "Sin kilometros al volante con GPS en la ventana"}
    valor, por_mil = reglas.valor_manejo(km, excesos + bruscos,
                                         puntos_por_evento)
    return {"aplica": True, "valor": valor, "km": float(km),
            "excesos": excesos, "bruscos": bruscos,
            "detalle": (f"{km:,.0f} km al volante en servicio: {excesos} "
                        f"excesos de velocidad y {bruscos} frenadas o "
                        f"arrancones bruscos, {por_mil:.1f} por cada "
                        "1,000 km")}


# ================================================================ la pantalla

def unidades(db: Session, pais_id: int, ahora: datetime | None = None) -> dict:
    """La pantalla de Unidades (tablero 1): cada unidad de Odoo con su
    GPS, y lo que hay que arreglar antes de que haga falta. No ensena
    donde esta ninguna."""
    from app import implantado as imp

    ahora = ahora or _utc()
    pais = db.get(m.Pais, pais_id)
    grupo = db.query(m.GrupoGps).filter_by(pais_id=pais_id).first()
    gps = (db.query(m.UnidadGps)
           .filter_by(grupo_id=grupo.id, en_el_grupo=True).all()
           if grupo else [])
    vehiculos = (db.query(m.Vehiculo)
                 .join(m.Plaza, m.Vehiculo.plaza_id == m.Plaza.id)
                 .filter(m.Plaza.pais_id == pais_id,
                         m.Vehiculo.rentado.is_(False),
                         m.Vehiculo.activo.is_(True))
                 .order_by(m.Vehiculo.placa).all())
    hoy = reloj.hoy_en(pais) if pais else date.today()
    manana = hoy + timedelta(days=1)
    ids = [v.id for v in vehiculos]

    # Que trae cada unidad hoy y manana.
    dias: dict = {}
    if ids:
        for a in (db.query(m.AsignacionVehiculo)
                  .join(m.Jornada,
                        m.AsignacionVehiculo.jornada_id == m.Jornada.id)
                  .filter(m.AsignacionVehiculo.vehiculo_id.in_(ids),
                          m.AsignacionVehiculo.relevado_en.is_(None),
                          m.Jornada.fecha.in_([hoy, manana]),
                          m.Jornada.estatus != m.EstatusJornada.CANCELADA)
                  .all()):
            j = a.jornada
            conductor = quien_maneja(j, a.vehiculo_id)
            persona = db.get(m.Persona, conductor) if conductor else None
            dias.setdefault(a.vehiculo_id, {})[j.fecha] = {
                "folio": j.equipo.servicio.folio,
                "persona": persona.nombre if persona else None}
    taller = {}
    if ids:
        for t in (db.query(m.TallerVehiculo)
                  .filter(m.TallerVehiculo.vehiculo_id.in_(ids)).all()):
            if t.cubre(hoy):
                taller[t.vehiculo_id] = {
                    "tipo": t.tipo.value if t.tipo else None,
                    "desde": t.desde.isoformat(),
                    "de_odoo": t.odoo_id is not None}

    por_vehiculo = {u.vehiculo_id: u for u in gps if u.vehiculo_id}
    repetidas: dict[str, int] = {}
    for u in gps:
        if u.placa_normal:
            repetidas[u.placa_normal] = repetidas.get(u.placa_normal, 0) + 1
    minutos_callada = reglas.HORAS_SIN_SENAL * 60

    def hace(u):
        if not u.reporte_en:
            return None
        return int((ahora - u.reporte_en).total_seconds() // 60)

    def estado_gps(u):
        return ("sin_senal" if reglas.callada(u.reporte_en, ahora,
                                              minutos_callada)
                else "reporta")

    filas = []
    for v in vehiculos:
        u = por_vehiculo.get(v.id)
        suyo = dias.get(v.id, {})
        if v.id in taller:
            hoy_ = {"estado": "taller", **taller[v.id]}
        elif hoy in suyo:
            hoy_ = {"estado": "servicio", **suyo[hoy]}
        else:
            hoy_ = {"estado": "libre"}
        fila = {
            "tipo": "ligada" if u else "centauro",
            "vehiculo_id": v.id, "placa": v.placa,
            "categoria": v.categoria.nombre if v.categoria else None,
            "plaza": v.plaza.nombre if v.plaza else None,
            "marca_modelo": v.marca_modelo, "color": v.color,
            "anio": v.modelo_anio,
            "gps": estado_gps(u) if u else "sin_gps",
            "hoy": hoy_,
            "manana": suyo.get(manana),
        }
        if u:
            fila.update({
                "pegasus_id": u.pegasus_id,
                "reporte_en": _iso(local(u.reporte_en, pais)),
                "hace_min": hace(u),
                "odometro_km": float(u.odometro_km) if u.odometro_km else None,
                "sin_encendido": u.encendida is None,
            })
        filas.append(fila)
    for u in gps:
        if u.vehiculo_id:
            continue
        motivo = ("sin_placa" if not u.placa_normal else
                  "repetida" if repetidas.get(u.placa_normal, 0) > 1 else
                  "no_esta")
        filas.append({
            "tipo": "pegasus", "pegasus_id": u.pegasus_id,
            "placa": u.placa, "motivo": motivo,
            "marca_modelo": u.marca_modelo, "color": u.color, "anio": u.anio,
            "gps": "sin_ligar", "estado_senal": estado_gps(u),
            "reporte_en": _iso(local(u.reporte_en, pais)),
            "hace_min": hace(u),
            "odometro_km": float(u.odometro_km) if u.odometro_km else None,
            "sin_encendido": u.encendida is None,
            "hoy": None, "manana": None,
        })

    def importa(f):
        # Lo que hay que arreglar primero: la que no reporta y ya tiene
        # servicio, luego lo que no liga, luego lo que no reporta.
        urgente = f["gps"] == "sin_senal" and (f.get("manana") or (
            f.get("hoy") or {}).get("estado") == "servicio")
        orden = {"sin_senal": 2, "sin_ligar": 1, "sin_gps": 1, "reporta": 3}
        return (0 if urgente else orden.get(f["gps"], 3), f.get("placa") or "")

    filas.sort(key=importa)
    sin_senal = sum(1 for u in gps if estado_gps(u) == "sin_senal")
    return {
        "conectado": configurado(),
        "grupo": ({"nombre": grupo.nombre,
                   "leido_en": _iso(local(grupo.leido_en, pais)),
                   "hace_min": (int((ahora - grupo.leido_en).total_seconds() // 60)
                                if grupo.leido_en else None),
                   "error": grupo.error,
                   "error_en": _iso(local(grupo.error_en, pais))}
                  if grupo else
                  {"nombre": grupos_configurados().get(
                      pais.codigo if pais else "", None),
                   "leido_en": None, "hace_min": None, "error": None,
                   "error_en": None}),
        "cifras": {
            "en_pegasus": len(gps),
            "ligadas": sum(1 for u in gps if u.vehiculo_id),
            "sin_ligar_pegasus": sum(1 for u in gps if not u.vehiculo_id),
            "sin_gps": sum(1 for v in vehiculos if v.id not in por_vehiculo),
            "sin_senal": sin_senal,
        },
        "sin_placa": sorted(u.pegasus_id for u in gps if not u.placa_normal),
        "unidades": filas,
    }

"""La central de inteligencia: lo que va a pasar, antes de que pase.

Una central que solo mira lo que esta ocurriendo llega tarde siempre: si
el equipo no llego al punto, ya no llego. El unico momento en que se
puede cambiar el resultado de un servicio es la vispera, y por eso el
corazon de esta pantalla no es "ahora" sino manana.

Cuatro bandas, en el orden en que se leen:

  roto      lo que ya no se arregla solo y alguien tiene que atender hoy
  manana    el meet and greet de cada servicio que arranca, con la lista
            de lo que tiene que ser cierto para que ocurra
  pulso     los servicios en curso y cuanto llevan callados
  semana    los siguientes dias, para ver venir el lunes de seis servicios

Todo sale de lo que ya existe en otros modulos. La gracia es el orden y
que lo urgente se vea primero.
"""
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app import implantado as imp
from app import models as m
from app import reloj
from app.presentacion import llegada_del_equipo

# ------------------------------------------------------------- reglas

# La hora en que manana deja de ser una lista de pendientes y se vuelve
# un problema de esta noche. Antes del corte, lo que falta es trabajo;
# despues, sube a la banda roja con el nombre de quien lo lleva.
CORTE_DE_LA_VISPERA = time(18, 0)

# Cuanto puede estar callado un servicio en curso antes de que la central
# lo persiga. Se mide contra el ultimo hito que marco el equipo.
SILENCIO_AMBAR = 30
SILENCIO_ROJO = 60

# El aviso preventivo de horas extra: cuando falta esto para el fin
# programado, mas vale decidir si se extiende o se cierra.
AVISO_HORAS_EXTRA = 30

DIAS_DE_LA_TIRA = 7

VIVAS = (m.EstatusJornada.PLANEADA, m.EstatusJornada.EN_CURSO)


def tablero(db: Session, ahora: datetime | None = None) -> dict:
    """El tablero se mira desde un solo lugar, con un solo reloj.

    El corte de la vispera y el "manana" de esta pantalla son del turno
    que esta mirando, no de cada servicio: si la central de Mexico ve un
    servicio de Sao Paulo, el corte de las 18:00 que aplica es el de
    Mexico. Lo que si se juzga con la hora de alla es lo de cada
    servicio —cuanto lleva callado, cuanto le falta para horas extra—,
    y eso vive en `pulso`.
    """
    ahora = ahora or datetime.now()
    manana_ = manana(db, ahora)
    pulso_ = pulso(db, ahora)
    return {
        "momento": ahora.isoformat(),
        "corte_de_la_vispera": CORTE_DE_LA_VISPERA.strftime("%H:%M"),
        "paso_el_corte": ahora.time() >= CORTE_DE_LA_VISPERA,
        "roto": roto(db, ahora, manana_, pulso_),
        "manana": manana_,
        "pulso": pulso_,
        "semana": semana(db, ahora),
    }


# ==================================================================
# Manana: el meet and greet
# ==================================================================

def _nombres(db: Session) -> dict:
    """Las personas por id. El servicio guarda el id del consultor, no el
    consultor, y preguntarlo renglon por renglon es una consulta por
    linea de la pantalla."""
    return {p.id: p.nombre for p in db.query(m.Persona).all()}


def _viaticos_depositados(db: Session, jornada: m.Jornada) -> bool:
    """Si el dinero ya esta con la gente, no si alguien lo pidio.

    Un viatico solicitado y no depositado es un agente pagando la
    gasolina de su bolsa a las seis de la manana.
    """
    asignaciones = (db.query(m.AsignacionViatico)
                    .filter_by(jornada_id=jornada.id).all())
    if not asignaciones:
        return False
    confirmadas = (db.query(m.SolicitudTransferencia)
                   .filter(m.SolicitudTransferencia.asignacion_id.in_(
                       [a.id for a in asignaciones]),
                       m.SolicitudTransferencia.estatus
                       == m.EstatusTransferencia.CONFIRMADA)
                   .count())
    return confirmadas > 0


def _hoja_publicada(db: Session, jornada: m.Jornada) -> bool:
    """La hoja que el ejecutivo lee para saber quien llega por el."""
    servicio = jornada.equipo.servicio
    if servicio.tipo == m.TipoServicio.IMPLANTADO:
        acuerdo = (db.query(m.AcuerdoImplantado)
                   .filter_by(servicio_id=servicio.id).first())
        return bool(acuerdo and (acuerdo.version_hoja or 0) > 0)
    return bool(db.query(m.TaskSheet)
                .filter_by(equipo_id=jornada.equipo_id,
                           estatus=m.EstatusTaskSheet.PUBLICADO).first())


def _unidad_en_taller(db: Session, jornada: m.Jornada) -> list[str]:
    ids = [a.vehiculo_id for a in jornada.vehiculos if a.vehiculo_id]
    if not ids:
        return []
    bloqueos = imp.taller_de(db, ids)
    return [a.vehiculo.placa for a in jornada.vehiculos
            if a.vehiculo and imp.en_taller(bloqueos.get(a.vehiculo_id),
                                            jornada.fecha)]


def revision_del_dia(db: Session, jornada: m.Jornada) -> list[dict]:
    """Lo que tiene que ser cierto para que el encuentro ocurra.

    Cada renglon dice que hacer, no "pendiente": quien lee esto a las
    seis de la tarde tiene que poder resolverlo sin abrir otra pantalla
    para averiguar de que se trata.
    """
    servicio = jornada.equipo.servicio
    puntos = []

    def punto(clave, listo, que_hacer=None, detalle=None):
        puntos.append({"clave": clave, "listo": bool(listo),
                       "que_hacer": None if listo else que_hacer,
                       "detalle": detalle})

    # El punto de encuentro, con coordenadas: de ahi salen la geocerca
    # que el conductor tiene que pisar y los hospitales de la hoja.
    tiene_punto = bool(jornada.origen_lat and jornada.origen_lon)
    punto("punto_de_encuentro", tiene_punto,
          "Capture el punto en el mapa. Sin coordenadas no hay geocerca "
          "ni hospitales, y el conductor no puede marcar su llegada.",
          jornada.origen_direccion)

    # Personal, con rol y confirmado.
    gente = jornada.personal
    punto("personal", bool(gente),
          "Asigne al equipo de este dia.",
          ", ".join(a.persona.nombre for a in gente if a.persona) or None)
    if gente:
        sin_rol = [a.persona.nombre for a in gente if a.persona and not a.rol_id]
        punto("rol", not sin_rol,
              f"Falta decir con que rol va {', '.join(sin_rol)}. Sin rol "
              f"no se puede cobrar ni pagar ese dia.")
        sin_confirmar = [a.persona.nombre for a in gente
                         if a.persona and not a.confirmado]
        punto("confirmacion", not sin_confirmar,
              f"Confirme con {', '.join(sin_confirmar)}. Nadie ha dicho "
              f"que sepa que manana trabaja.")

    # Unidad, y que no este en el taller.
    en_taller = _unidad_en_taller(db, jornada)
    punto("unidad", bool(jornada.vehiculos) and not en_taller,
          (f"La unidad {', '.join(en_taller)} esta en el taller ese dia. "
           f"Cambiela." if en_taller else "Asigne la unidad."),
          ", ".join(a.vehiculo.placa for a in jornada.vehiculos if a.vehiculo)
          or None)

    # La hoja, que es lo que el ejecutivo lee.
    punto("hoja", _hoja_publicada(db, jornada),
          "Libere la hoja. El ejecutivo no sabe quien llega por el.")

    # El vuelo, cuando el encuentro es contra vuelo.
    if jornada.origen_aeropuerto or jornada.vuelo_tipo:
        punto("vuelo", bool(jornada.vuelo_numero and jornada.vuelo_hora),
              "Capture el vuelo y su hora. El encuentro se mide contra "
              "el vuelo, no contra la hora del servicio.",
              (f"{jornada.vuelo_aerolinea or ''} {jornada.vuelo_numero or ''}"
               .strip() or None))

    # La hora, cuando se heredo en vez de acordarse.
    punto("hora", jornada.hora_confirmada,
          "La hora se heredo del primer dia y nadie la confirmo con el "
          "cliente.")

    # El dinero.
    punto("viaticos", _viaticos_depositados(db, jornada),
          "Los viaticos no estan depositados. El equipo sale con dinero "
          "propio.")

    # Los hospitales de esa ciudad, que son la referencia medica.
    hay_hospitales = bool(db.query(m.Hospital)
                          .filter_by(plaza_id=servicio.plaza_id, activo=True)
                          .first())
    punto("hospitales", hay_hospitales,
          "Esa ciudad no tiene hospitales cargados. La hoja sale sin "
          "referencia medica.")

    return puntos


def _ficha_del_dia(db: Session, jornada: m.Jornada, ahora: datetime,
                   ciudades: dict, nombres: dict) -> dict:
    servicio = jornada.equipo.servicio
    llega, minutos, contra_vuelo = llegada_del_equipo(
        jornada.inicio_programado, jornada.vuelo_hora, jornada.vuelo_tipo)
    revision = revision_del_dia(db, jornada)
    faltan = [p for p in revision if not p["listo"]]

    return {
        "jornada_id": jornada.id,
        "servicio_id": servicio.id,
        "folio": servicio.folio,
        "tipo": servicio.tipo.value,
        "cliente": servicio.cliente.nombre if servicio.cliente else None,
        "ejecutivo": servicio.ejecutivo_completo,
        "equipo": jornada.equipo.alias,
        "consultor": nombres.get(servicio.consultor_id),
        "ciudad": ciudades.get(servicio.plaza_id),
        # La hora que importa no es la del servicio: es a la que el
        # equipo tiene que estar parado en el punto.
        "servicio_inicia": jornada.inicio_programado.isoformat(),
        "equipo_llega": llega.isoformat(),
        "anticipacion_minutos": minutos,
        "contra_vuelo": contra_vuelo,
        "punto": jornada.origen_direccion,
        "personal": [{"nombre": a.persona.nombre if a.persona else None,
                      "rol": a.rol.nombre if a.rol else None,
                      "confirmado": a.confirmado,
                      "telefono": a.persona.telefono if a.persona else None}
                     for a in jornada.personal],
        "unidades": [a.vehiculo.placa for a in jornada.vehiculos
                     if a.vehiculo],
        "revision": revision,
        "listo": not faltan,
        "faltan": len(faltan),
    }


def manana(db: Session, ahora: datetime | None = None) -> dict:
    """El meet and greet de cada servicio que arranca manana.

    Ordenado por la hora a la que el equipo tiene que estar en el punto,
    que es la unica hora que se puede perder.
    """
    ahora = ahora or datetime.now()
    dia = ahora.date() + timedelta(days=1)
    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.fecha == dia,
                        m.Jornada.estatus.in_(VIVAS))
                .all())

    # El servicio guarda el id de la ciudad, no la ciudad: se traen una
    # vez y se buscan aqui, en vez de una consulta por renglon.
    ciudades = {p.id: p.nombre for p in db.query(m.Plaza).all()}
    nombres = _nombres(db)
    fichas = [_ficha_del_dia(db, j, ahora, ciudades, nombres)
              for j in jornadas]
    fichas.sort(key=lambda f: f["equipo_llega"])
    listos = [f for f in fichas if f["listo"]]
    return {
        "fecha": dia.isoformat(),
        "cuantos": len(fichas),
        "listos": len(listos),
        "incompletos": len(fichas) - len(listos),
        "servicios": fichas,
    }


# ==================================================================
# El pulso: lo que esta en curso
# ==================================================================

def _silencio(ultimo: m.Hito | None, ahora: datetime) -> int | None:
    if not ultimo or not ultimo.marcado_en:
        return None
    return int((ahora - ultimo.marcado_en).total_seconds() / 60)


def _color_del_silencio(minutos: int | None) -> str:
    if minutos is None:
        return "sin_reporte"
    if minutos >= SILENCIO_ROJO:
        return "rojo"
    if minutos >= SILENCIO_AMBAR:
        return "ambar"
    return "verde"


def _en_curso(db: Session, jornada: m.Jornada, ahora: datetime,
              nombres: dict, relojes=None) -> dict:
    servicio = jornada.equipo.servicio
    # Cuanto lleva callado y cuanto le falta para horas extra se miden
    # con la hora del pais donde esta el equipo, no con la del
    # contenedor: sin esto, todo servicio brasileño salia "sin reporte"
    # o en rojo desde que arrancaba —en la banda que la central lee
    # primero— y nunca avisaba que iba a entrar en horas extra.
    suyo = relojes.ahora(servicio.pais_id) if relojes else ahora
    ultimo = (db.query(m.Hito).filter_by(jornada_id=jornada.id)
              .order_by(m.Hito.marcado_en.desc()).first())
    minutos = _silencio(ultimo, suyo)

    para_extra = None
    if jornada.fin_programado:
        para_extra = int((jornada.fin_programado - suyo).total_seconds() / 60)

    abiertas = (db.query(m.Alerta)
                .filter_by(jornada_id=jornada.id, atendida=False).count())

    return {
        "jornada_id": jornada.id,
        "servicio_id": servicio.id,
        "folio": servicio.folio,
        "tipo": servicio.tipo.value,
        "cliente": servicio.cliente.nombre if servicio.cliente else None,
        "equipo": jornada.equipo.alias,
        "consultor": nombres.get(servicio.consultor_id),
        "personal": [a.persona.nombre for a in jornada.personal if a.persona],
        "unidades": [a.vehiculo.placa for a in jornada.vehiculos
                     if a.vehiculo],
        "ultimo_hito": ultimo.tipo.value if ultimo else None,
        "ultimo_en": ultimo.marcado_en.isoformat()
                     if ultimo and ultimo.marcado_en else None,
        "minutos_callado": minutos,
        "silencio": _color_del_silencio(minutos),
        "minutos_para_horas_extra": para_extra,
        "por_entrar_en_extra": (para_extra is not None
                                and 0 <= para_extra <= AVISO_HORAS_EXTRA),
        "alertas_abiertas": abiertas,
    }


def pulso(db: Session, ahora: datetime | None = None) -> dict:
    """Los servicios en curso, con lo unico que la central no adivina:
    cuanto lleva callado cada uno.

    El implantado va aparte y compacto. Diez implantados operando bien no
    pueden empujar hacia abajo el eventual que arranca en veinte minutos.
    """
    ahora = ahora or datetime.now()
    relojes = reloj.Relojes(db, ahora)
    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.estatus == m.EstatusJornada.EN_CURSO).all())

    nombres = _nombres(db)
    eventuales, implantados = [], []
    for j in jornadas:
        ficha = _en_curso(db, j, ahora, nombres, relojes)
        (implantados if ficha["tipo"] == "implantado"
         else eventuales).append(ficha)

    orden = {"sin_reporte": 0, "rojo": 1, "ambar": 2, "verde": 3}
    for lista_ in (eventuales, implantados):
        lista_.sort(key=lambda f: (orden.get(f["silencio"], 9),
                                   -(f["minutos_callado"] or 0)))

    callados = [f for f in eventuales + implantados
                if f["silencio"] in ("rojo", "sin_reporte")]
    return {
        "cuantos": len(jornadas),
        "callados": len(callados),
        "eventuales": eventuales,
        "implantados": implantados,
    }


# ==================================================================
# Lo roto: lo que alguien tiene que atender hoy
# ==================================================================

def roto(db: Session, ahora: datetime, manana_: dict, pulso_: dict) -> dict:
    """Lo que ya no se arregla solo.

    Si esta vacio, la pantalla no lo pinta: una franja que siempre dice
    "todo bien" deja de leerse a la semana.
    """
    panico = (db.query(m.AlertaIncidencia)
              .filter(m.AlertaIncidencia.estatus != m.EstatusAlerta.CERRADA)
              .order_by(m.AlertaIncidencia.reportada_en.desc()).all())

    callados = [f for f in pulso_["eventuales"] + pulso_["implantados"]
                if f["silencio"] in ("rojo", "sin_reporte")]

    # Despues del corte, lo que le falta a manana deja de ser trabajo
    # pendiente y se vuelve un problema de esta noche.
    vencidos = []
    if ahora.time() >= CORTE_DE_LA_VISPERA:
        vencidos = [f for f in manana_["servicios"] if not f["listo"]]

    extras = [f for f in pulso_["eventuales"] + pulso_["implantados"]
              if f["por_entrar_en_extra"]]

    return {
        "hay": bool(panico or callados or vencidos or extras),
        "panico": [{"id": a.id, "canal": a.canal.value,
                    "estatus": a.estatus.value,
                    "jornada_id": a.jornada_id,
                    "servicio_id": a.servicio_id,
                    "descripcion": a.descripcion,
                    "lat": float(a.lat) if a.lat is not None else None,
                    "lon": float(a.lon) if a.lon is not None else None,
                    "reportada_en": a.reportada_en.isoformat()
                                    if a.reportada_en else None}
                   for a in panico],
        "callados": callados,
        "manana_vencido": vencidos,
        "por_entrar_en_extra": extras,
    }


# ==================================================================
# La semana que viene
# ==================================================================

def semana(db: Session, ahora: datetime | None = None) -> list[dict]:
    """Los proximos dias, para ver venir el lunes de seis servicios.

    No es para trabajar: es para que alguien note el jueves que el lunes
    trae seis y solo dos con equipo.
    """
    ahora = ahora or datetime.now()
    desde = ahora.date()
    hasta = desde + timedelta(days=DIAS_DE_LA_TIRA - 1)

    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.fecha >= desde, m.Jornada.fecha <= hasta,
                        m.Jornada.estatus.in_(VIVAS))
                .all())

    por_dia: dict[date, list] = {}
    for j in jornadas:
        por_dia.setdefault(j.fecha, []).append(j)

    tira = []
    for i in range(DIAS_DE_LA_TIRA):
        dia = desde + timedelta(days=i)
        suyas = por_dia.get(dia, [])
        # Barato a proposito: la tira no abre la revision completa de
        # cada dia, solo cuenta lo que se ve de un vistazo.
        completos = sum(1 for j in suyas
                        if j.personal and j.vehiculos and j.origen_lat)
        tira.append({
            "fecha": dia.isoformat(),
            "dia_semana": dia.weekday(),
            "servicios": len(suyas),
            "completos": completos,
            "incompletos": len(suyas) - completos,
        })
    return tira

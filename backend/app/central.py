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
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app import gps
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

# La lista dice que esta MUERTO, no que esta vivo. Dicha al reves
# olvidaba dos estados --CONFIRMADA y PROXIMA_A_INICIAR-- y el segundo
# se le pone justo a las jornadas de hoy que arrancan en menos de dos
# horas: o sea que la jornada desaparecia de la banda del camino al
# punto exactamente en las dos horas que esa banda existe para vigilar.
# El trayecto seguia corriendo --su filtro si incluye ese estado-- asi
# que se seguian cobrando los silencios de algo que la central ya no
# veia.
#
# Al reves, un estado nuevo nace visible, que es el valor correcto por
# omision para una pantalla de vigilancia: lo que no se sabe se muestra.
MUERTAS = (m.EstatusJornada.CANCELADA, m.EstatusJornada.TERMINADA)


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


EN_CAMINO_EL_DINERO = (m.EstatusTransferencia.PENDIENTE,
                       m.EstatusTransferencia.ENVIADA)


def _estado_de_viaticos(
        db: Session,
        jornada: m.Jornada) -> tuple[bool, str | None, str | None]:
    """Si el dinero ya esta con la gente, no si alguien lo pidio.

    Un viatico solicitado y no depositado es un agente pagando la
    gasolina de su bolsa a las seis de la manana. Se revisa uno por uno:
    con dos personas en el dia, que a una le hayan depositado no salva a
    la otra. Y se dice el nombre y en que se quedo, porque un "no estan
    depositados" a secas manda a buscar en tres pantallas de quien se
    trata.
    """
    van = {a.persona_id: (a.persona.nombre if a.persona else "alguien")
           for a in jornada.personal}
    if not van:
        # Sin gente no hay a quien depositarle: de eso ya se queja el
        # renglon del personal.
        return True, None, None

    asignaciones = (db.query(m.AsignacionViatico)
                    .filter(m.AsignacionViatico.jornada_id == jornada.id,
                            m.AsignacionViatico.persona_id.in_(list(van)))
                    .all())

    # De cada asignacion importa su solicitud mas avanzada: una cancelada
    # y vuelta a pedir no puede contar como que nunca se pidio.
    por_asignacion: dict[int, m.EstatusTransferencia] = {}
    if asignaciones:
        for s_ in (db.query(m.SolicitudTransferencia)
                   .filter(m.SolicitudTransferencia.asignacion_id.in_(
                       [a.id for a in asignaciones])).all()):
            if s_.estatus == m.EstatusTransferencia.CANCELADA:
                continue
            if (por_asignacion.get(s_.asignacion_id)
                    == m.EstatusTransferencia.CONFIRMADA):
                continue
            por_asignacion[s_.asignacion_id] = s_.estatus

    depositados, en_camino, sin_pedir = [], [], []
    for a in asignaciones:
        nombre = van.get(a.persona_id, "alguien")
        estatus = por_asignacion.get(a.id)
        if estatus == m.EstatusTransferencia.CONFIRMADA:
            depositados.append(nombre)
        elif estatus in EN_CAMINO_EL_DINERO:
            en_camino.append(nombre)
        else:
            sin_pedir.append(nombre)

    con_viatico = {a.persona_id for a in asignaciones}
    sin_asignar = [nombre for pid, nombre in van.items()
                   if pid not in con_viatico]

    ya = f"Ya depositado a {', '.join(depositados)}." if depositados else None
    if not (en_camino or sin_pedir or sin_asignar):
        return True, None, ya

    falta = []
    if sin_asignar:
        falta.append(f"{', '.join(sin_asignar)}: sin viaticos asignados")
    if sin_pedir:
        falta.append(f"{', '.join(sin_pedir)}: asignados, pero nadie le ha "
                     f"pedido la transferencia a finanzas")
    if en_camino:
        falta.append(f"{', '.join(en_camino)}: pedidos, finanzas todavia no "
                     f"confirma el deposito")
    return (False, "Sale con dinero propio. " + "; ".join(falta) + ".", ya)


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
    hay_coordenadas = bool(jornada.origen_lat and jornada.origen_lon)
    # La direccion escrita cuenta igual que las coordenadas. Con punto y
    # sin nombre, la app del personal no tiene que pintar y el agente
    # sabe a que hora presentarse pero no donde.
    hay_nombre = bool((jornada.origen_direccion or "").strip())
    punto("punto_de_encuentro", hay_coordenadas and hay_nombre,
          ("Capture el punto en el mapa. Sin coordenadas no hay geocerca "
           "ni hospitales, y el conductor no puede marcar su llegada."
           if not hay_coordenadas else
           "El punto tiene coordenadas pero no direccion. Escribala: es "
           "lo que el equipo lee en su telefono."),
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
    hay_dinero, falta_dinero, quien_ya = _estado_de_viaticos(db, jornada)
    punto("viaticos", hay_dinero, falta_dinero, quien_ya)

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
        # `confirmado_por` vacio quiere decir que confirmo la propia
        # persona desde su app. Con nombre, lo registro la central por
        # telefono, y la pantalla no las pinta igual: el dia que alguien
        # no llegue, esa es la unica pregunta que importa.
        "personal": [{"nombre": a.persona.nombre if a.persona else None,
                      "persona_id": a.persona_id,
                      "rol": a.rol.nombre if a.rol else None,
                      "confirmado": a.confirmado,
                      "confirmado_por": (a.confirmado_por.nombre
                                         if a.confirmado_por else None),
                      "nota_confirmacion": a.nota_confirmacion,
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
                        m.Jornada.estatus.notin_(MUERTAS))
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
# El camino: quien viene en camino al punto
# ==================================================================

def camino(db: Session, ahora: datetime | None = None) -> dict:
    """Quien va llegando a su meet and greet, y quien no.

    Es la vista del rato en que todavia se puede hacer algo. Aparece
    sola cuando hay alguien en camino y desaparece cuando todos
    llegaron: si no hay nada que mirar, no ocupa pantalla.

    Ordenada por lo que peor va, no por la hora: lo primero que tiene
    que ver quien abre esto es a quien hay que llamar.
    """
    from app import trayecto

    ahora = ahora or datetime.now()
    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.fecha == ahora.date(),
                        m.Jornada.estatus.notin_(MUERTAS))
                .all())

    # El peor primero. Lo que la central necesita decidir es a quien
    # manda, y eso empieza por quien no va a llegar.
    ORDEN = {"no_sale": 0, "no_llega": 0, "sin_respuesta": 1,
             "esperando": 2, "por_telefono": 3, "en_camino": 4, "cerca": 5,
             "llego": 6}

    relojes = reloj.Relojes(db, ahora)
    filas = []
    for jornada in jornadas:
        # Para quien trae una unidad con GPS, la unidad manda: lo que
        # tiene que llegar al punto es la camioneta (seccion 60).
        gente = trayecto.en_camino(db, jornada.id,
                                   relojes.de_la_jornada(jornada))
        if not gente:
            continue
        estar = trayecto.hora_de_estar(db, jornada)
        for quien in gente:
            if quien["estado"] in ("llego", "cerca"):
                continue
            filas.append({
                **quien,
                "jornada_id": jornada.id,
                # El dia de la jornada, no el del servidor: la hora que
                # la central capture a mano se arma sobre esta fecha, y
                # un servicio de Sao Paulo puede estar en otro dia.
                "fecha": jornada.fecha.isoformat(),
                "servicio": jornada.equipo.servicio.folio,
                "estar_en_el_punto": estar.strftime("%H:%M"),
                "faltan_minutos": int((estar - ahora).total_seconds() / 60),
                "punto": jornada.origen_direccion,
            })
    filas.sort(key=lambda f: (ORDEN.get(f["estado"], 9), f["faltan_minutos"]))
    return {"cuantos": len(filas),
            "en_riesgo": len([f for f in filas
                              if f["estado"] in ("no_llega", "no_sale",
                                                 "sin_respuesta")]),
            "gente": filas}


# ==================================================================
# El pulso: lo que esta en curso
# ==================================================================

def silencio(ultimo: m.Hito | None, ahora: datetime) -> int | None:
    if not ultimo or not ultimo.marcado_en:
        return None
    return int((ahora - ultimo.marcado_en).total_seconds() / 60)


def color_del_silencio(minutos: int | None) -> str:
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
    minutos = silencio(ultimo, suyo)

    para_extra = None
    if jornada.fin_programado:
        para_extra = int((jornada.fin_programado - suyo).total_seconds() / 60)

    abiertas = (db.query(m.Alerta)
                .filter_by(jornada_id=jornada.id, atendida=False).count())
    pais = relojes.pais(servicio.pais_id) if relojes else None

    return {
        "jornada_id": jornada.id,
        "servicio_id": servicio.id,
        "folio": servicio.folio,
        "tipo": servicio.tipo.value,
        "cliente": servicio.cliente.nombre if servicio.cliente else None,
        "equipo": jornada.equipo.alias,
        "consultor": nombres.get(servicio.consultor_id),
        "personal": [a.persona.nombre for a in jornada.personal if a.persona],
        # El dia de la jornada. Lo necesita la central para asentar una
        # marca a mano desde esta misma tarjeta: la hora que le dicta el
        # agente se arma sobre esta fecha, y un servicio de Sao Paulo
        # puede estar en otro dia que el navegador de quien captura.
        "fecha": jornada.fecha.isoformat(),
        # Con telefono: lo primero que hace quien lee un renglon en rojo
        # es llamar, y buscar el numero en otra pantalla es el rato en
        # que el servicio sigue callado.
        #
        # Y con su id, porque de esta tarjeta sale tambien la marca que
        # el agente dicta en esa llamada: una marca se le acredita a una
        # persona, no a un nombre.
        "contactos": [{"persona_id": a.persona_id,
                       "nombre": a.persona.nombre,
                       "telefono": a.persona.telefono}
                      for a in jornada.personal
                      if a.persona and a.persona.telefono],
        # Cuanto lleva de terminado, para saber que se puede hacer con
        # el. Negativo o nulo: sigue corriendo y no hay nada que cerrar.
        # Menos de tres horas: son las horas de gracia, la marca todavia
        # puede llegar tarde. Mas: ya esta en "Dias sin cerrar" y se
        # firma ahi.
        "minutos_desde_fin": (
            int((suyo - jornada.fin_programado).total_seconds() / 60)
            if jornada.fin_programado else None),
        "unidades": [a.vehiculo.placa for a in jornada.vehiculos
                     if a.vehiculo],
        "ultimo_hito": ultimo.tipo.value if ultimo else None,
        "ultimo_en": ultimo.marcado_en.isoformat()
                     if ultimo and ultimo.marcado_en else None,
        "minutos_callado": minutos,
        "silencio": color_del_silencio(minutos),
        "minutos_para_horas_extra": para_extra,
        "por_entrar_en_extra": (para_extra is not None
                                and 0 <= para_extra <= AVISO_HORAS_EXTRA),
        "alertas_abiertas": abiertas,
        # Lo ultimo que dijo cada unidad del dia (seccion 60). No apaga
        # nada: un equipo callado sigue en rojo aunque su camioneta se
        # mueva --que se mueva no dice que el equipo este bien--. Solo
        # agrega lo que sabe.
        "gps": gps.lineas_del_dia(db, jornada, pais, _utc(ahora)),
    }


# Las mismas horas de gracia que usa `operacion.dias_sin_cerrar`: un dia
# no se declara abandonado antes que la otra pantalla lo recoja, o
# desaparece de las dos.
HORAS_DE_GRACIA = 3


def _dia_abandonado(ficha: dict) -> bool:
    """Un dia que arranco, nadie cerro, y nadie ha tocado en horas.

    `pulso` toma TODAS las jornadas EN_CURSO, sin mirar la fecha. Eso
    esta bien para lo que esta corriendo y esta mal para lo que quedo
    abierto: una jornada de hace tres semanas que nadie cerro seguia
    apareciendo como "servicio en curso" para siempre, y en "Atender
    ahora" como callada con veinte mil minutos de silencio. Ni era un
    servicio corriendo ni se podia hacer nada con ella desde ahi.

    Esas viven en "Dias sin cerrar", que es la pantalla que tiene el
    boton para firmarlas. Sacarlas de aqui no las esconde: las deja en
    un solo lugar, el que sirve.

    Ojo con lo que NO es abandonado: un servicio en horas extra tambien
    paso su fin programado, y ese si esta corriendo. Se distingue por el
    silencio: el que sigue trabajando sigue marcando. Hacen falta las
    dos cosas --paso el fin hace horas Y lleva horas callado-- porque
    cualquiera de las dos sola se lleva por delante un caso legitimo.
    """
    desde_el_fin = ficha.get("minutos_desde_fin")
    if desde_el_fin is None or desde_el_fin <= HORAS_DE_GRACIA * 60:
        return False
    return ficha.get("silencio") in ("rojo", "sin_reporte")


def _utc(ahora: datetime) -> datetime:
    """El `ahora` de esta pantalla es la hora del servidor, sin zona; el
    GPS habla en instantes."""
    return ahora.astimezone(timezone.utc)


def pulso(db: Session, ahora: datetime | None = None) -> dict:
    """Los servicios en curso, con lo unico que la central no adivina:
    cuanto lleva callado cada uno.

    El implantado va aparte y compacto. Diez implantados operando bien no
    pueden empujar hacia abajo el eventual que arranca en veinte minutos.
    """
    ahora = ahora or datetime.now()
    relojes = reloj.Relojes(db, ahora)
    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.estatus.in_(m.ARRANCADAS)).all())

    nombres = _nombres(db)
    eventuales, implantados = [], []
    for j in jornadas:
        ficha = _en_curso(db, j, ahora, nombres, relojes)
        if _dia_abandonado(ficha):
            continue
        (implantados if ficha["tipo"] == "implantado"
         else eventuales).append(ficha)

    orden = {"sin_reporte": 0, "rojo": 1, "ambar": 2, "verde": 3}
    for lista_ in (eventuales, implantados):
        lista_.sort(key=lambda f: (orden.get(f["silencio"], 9),
                                   -(f["minutos_callado"] or 0)))

    callados = [f for f in eventuales + implantados
                if f["silencio"] in ("rojo", "sin_reporte")]
    return {
        # Lo que de verdad esta corriendo, no cuantas filas traen
        # EN_CURSO en la base.
        "cuantos": len(eventuales) + len(implantados),
        "callados": len(callados),
        "eventuales": eventuales,
        "implantados": implantados,
    }


# ==================================================================
# Lo roto: lo que alguien tiene que atender hoy
# ==================================================================

# ------------------------------------------------------------------
# Con quien va, cuando suena el boton de panico
# ------------------------------------------------------------------

# Que dice de la compania del principal cada marca. Se lee de la ultima
# marca hacia atras: es lo unico que el sistema sabe de verdad.
CON_EL_PRINCIPAL = {
    m.TipoHito.CONTACTO_EJECUTIVO: "a_bordo",
    m.TipoHito.SALIDA_RUTA: "a_bordo",
    m.TipoHito.LLEGADA_DESTINO: "en_espera",
    m.TipoHito.STANDBY: "en_espera",
    m.TipoHito.LLEGADA_ORIGEN: "todavia_no",
    m.TipoHito.FIN_SERVICIO: "termino",
}


def _con_quien_va(db: Session, jornada_id: int | None) -> dict:
    """Si el principal va con el, segun la ultima marca.

    Cuando suena el boton de panico, la primera pregunta despues de
    "quien" es "donde" y la segunda es "va solo o lleva al principal".
    No es lo mismo mandar un apoyo a un conductor solo que a un
    conductor con el ejecutivo del cliente adentro del coche: cambia a
    quien se avisa, cuanta gente se manda y que se le dice al cliente.
    Esa respuesta estaba en el sistema y la central la buscaba abriendo
    el folio en otra pantalla, con la alerta sonando.

    Se dice de donde sale --"segun su ultima marca, 08:30"-- porque es
    una deduccion, no un hecho: el boton de panico se aprieta
    precisamente cuando las cosas dejaron de ir como estaban marcadas.
    """
    if not jornada_id:
        return {"estado": None, "ultima_marca": None}
    ultimo = (db.query(m.Hito)
              .filter(m.Hito.jornada_id == jornada_id)
              .order_by(m.Hito.marcado_en.desc()).first())
    if not ultimo:
        return {"estado": "sin_marcas", "ultima_marca": None}
    return {"estado": CON_EL_PRINCIPAL.get(ultimo.tipo, "sin_marcas"),
            "ultima_marca": ultimo.marcado_en.strftime("%H:%M")}


def _folio_de_la_alerta(db: Session, a) -> tuple[str | None, str | None]:
    """El folio y el equipo, sin obligar a abrir otra pantalla."""
    jornada = a.jornada
    if jornada and jornada.equipo:
        return (jornada.equipo.servicio.folio, jornada.equipo.alias)
    if a.servicio_id:
        servicio = db.get(m.Servicio, a.servicio_id)
        return ((servicio.folio if servicio else None), None)
    return (None, None)


def _a_bordo(db: Session, jornada: m.Jornada | None,
             vehiculo_id: int | None) -> list[dict]:
    """Quienes van en esa unidad, con su telefono: a quien se llama."""
    if not jornada or not vehiculo_id:
        return []
    return [{"persona_id": a.persona_id,
             "nombre": a.persona.nombre if a.persona else None,
             "rol": a.rol.nombre if a.rol else None,
             "telefono": a.persona.telefono if a.persona else None}
            for a in gps.a_bordo(jornada, vehiculo_id)]


def _ficha_de_panico(db: Session, a, ahora: datetime | None = None) -> dict:
    """Una alerta de panico, con lo que hay que saber antes de llamar."""
    folio, equipo = _folio_de_la_alerta(db, a)
    pais = db.get(m.Pais, reloj.pais_de_la_jornada(a.jornada)) \
        if a.jornada else None
    return {
        "id": a.id,
        "canal": a.canal.value,
        "estatus": a.estatus.value,
        "jornada_id": a.jornada_id,
        "servicio_id": a.servicio_id,
        # En que servicio esta y con quien va. Las dos preguntas que la
        # central contestaba abriendo otra pantalla con la alerta
        # sonando, y son las que deciden a quien se manda: no es lo
        # mismo un conductor solo que un conductor con el ejecutivo del
        # cliente adentro del coche.
        "servicio": folio,
        "equipo": equipo,
        "principal": _con_quien_va(db, a.jornada_id),
        # Quien la disparo, con su telefono.
        #
        # Con servicio, la central deduce quien es abriendo el folio.
        # SIN servicio no hay de donde deducirlo, y una alerta de panico
        # que no dice de quien es no se puede atender: lo primero que
        # hace quien la lee es llamar a esa persona. Faltaba, y se noto
        # el dia que el panico empezo a poder mandarse sin servicio.
        "quien": a.reporta.nombre if a.reporta else None,
        "telefono": a.reporta.telefono if a.reporta else None,
        # Quien la tomo y desde cuando. En una central con turnos es lo
        # que decide si quien la mira tiene algo que hacer: una alerta
        # tomada hace dos minutos por otro no se toca; una "en atencion"
        # desde hace cuarenta minutos y sin cerrar es una alerta que se
        # quedo sola. Sin esto, las dos se veian iguales.
        "tomada_por": (a.tomada_por.nombre
                       if a.tomada_por_id and a.tomada_por else None),
        "tomada_en": a.tomada_en.isoformat() if a.tomada_en else None,
        "descripcion": a.descripcion,
        "lat": float(a.lat) if a.lat is not None else None,
        "lon": float(a.lon) if a.lon is not None else None,
        "reportada_en": (a.reportada_en.isoformat()
                         if a.reportada_en else None),
        # El boton de la camioneta (seccion 60): de que unidad, quien va
        # a bordo, y lo que dice ahora la unidad.
        "placa": a.vehiculo.placa if a.vehiculo_id and a.vehiculo else None,
        "a_bordo": _a_bordo(db, a.jornada, a.vehiculo_id),
        "unidad": (gps.linea(gps.unidad_de(db, a.vehiculo_id), pais,
                             _utc(ahora or datetime.now()))
                   if a.vehiculo_id else None),
    }


def _alerta_de_la_unidad(db: Session, alerta: m.Alerta,
                         ahora: datetime) -> dict:
    """El inhibidor o la corriente cortada, con el servicio, quien va a
    bordo y si el principal va con ellos."""
    jornada = alerta.jornada
    servicio = jornada.equipo.servicio
    pais = db.get(m.Pais, servicio.pais_id)
    return {
        "id": alerta.id,
        "tipo": alerta.tipo.value,
        "jornada_id": jornada.id,
        "servicio_id": servicio.id,
        "tipo_servicio": servicio.tipo.value,
        "folio": servicio.folio,
        "cliente": servicio.cliente.nombre if servicio.cliente else None,
        "equipo": jornada.equipo.alias,
        "placa": alerta.vehiculo.placa if alerta.vehiculo else None,
        "mensaje": alerta.mensaje,
        "a_bordo": _a_bordo(db, jornada, alerta.vehiculo_id),
        "principal": _con_quien_va(db, jornada.id),
        "unidad": gps.linea(gps.unidad_de(db, alerta.vehiculo_id), pais,
                            _utc(ahora)),
    }


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

    # El inhibidor y la corriente cortada: solo existen del camino al
    # punto a la marca de fin, y se cierran solos (seccion 60).
    de_la_unidad = (db.query(m.Alerta)
                    .filter(m.Alerta.tipo.in_(gps.DE_LA_UNIDAD),
                            m.Alerta.atendida.is_(False))
                    .order_by(m.Alerta.creada_en.desc()).all())

    return {
        "hay": bool(panico or callados or vencidos or extras
                    or de_la_unidad),
        "panico": [_ficha_de_panico(db, a, ahora) for a in panico],
        "unidad": [_alerta_de_la_unidad(db, a, ahora) for a in de_la_unidad],
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
                        m.Jornada.estatus.notin_(MUERTAS))
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

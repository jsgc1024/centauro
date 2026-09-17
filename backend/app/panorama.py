"""La fotografia de la operacion, para quien decide.

La Central es la cola de trabajo del que actua: filas, botones, cada cosa
con su accion. Panorama contesta otra pregunta —¿estamos bien en este
momento?— y por eso esta escrita al reves que las demas pantallas:
primero una sola frase con el estado, y lo demas solo aparece cuando hay
algo que ver. Una pantalla que esta llena todos los dias deja de leerse a
las tres semanas, y entonces no sirve el dia que importa.

El umbral de silencio no se define aqui: es el mismo de la central. Antes
estaba escrito dos veces —60 minutos alla, 120 en el navegador— y un
equipo podia estar en rojo para el operador y verse normal para la
direccion.

Cada pais trae su hora. La tira del dia se dibuja por pais porque un solo
eje con Mexico y Brasil encima no significa nada: las 14:00 de la tira
son las 14:00 de donde esta parado ese equipo.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models as m
from app import reloj
from app.central import SILENCIO_ROJO, color_del_silencio, silencio
from app.nomina import lunes_de

CERO = Decimal("0")
VENTANA_PROXIMOS_HORAS = 2

# Cuantas cosas caben en el recuadro de arriba antes de mandar el resto a
# la Central. Sin tope vuelve a ser la lista larga que esta pantalla
# existe para no ser.
TOPE_ATENDER = 4


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def panorama(db: Session, ahora: datetime | None = None) -> dict:
    """El estado de la operacion, completo para quien la abra.

    No se recorta por consultor a proposito. Cualquier consultor puede
    trabajar la cartera de otro para cubrir una ausencia --asi esta
    hecho el sistema, y cada accion sobre un servicio ajeno queda
    marcada como cobertura-- y esconderle que el equipo de otro lleva
    dos horas callado es lo contrario de para lo que sirve esta
    pantalla.
    """
    ahora = ahora or datetime.now()
    relojes = reloj.Relojes(db, ahora)

    en_curso = _jornadas(db, m.EstatusJornada.EN_CURSO)
    # El equipo guarda plaza_id pero no tiene relacion con Plaza, y el
    # servicio guarda pais_id sin relacion con Pais: los nombres se
    # buscan aparte, una sola vez.
    plazas = {p.id: p.nombre for p in db.query(m.Plaza).all()}
    fichas = [_ficha(db, j, relojes, plazas) for j in en_curso]
    sin_listo = _sin_listo(db, ahora, relojes)
    alertas = _alertas(db)
    atender = _que_atender(alertas, fichas, sin_listo)

    return {
        "momento": ahora.isoformat(),
        # Lo manda el motor para que la consola no vuelva a tener su
        # propia idea de cuanto es mucho silencio.
        "umbral_silencio": SILENCIO_ROJO,
        "estado": {
            "nivel": _nivel(atender),
            "atender": atender[:TOPE_ATENDER],
            "mas": max(0, len(atender) - TOPE_ATENDER),
        },
        "en_la_calle": _en_la_calle(fichas),
        "paises": _paises(fichas, relojes),
        "dia": _dia(db, relojes),
        "dinero": _dinero(db, ahora, relojes),
        "calidad": _calidad(db, relojes, en_curso),
        "alertas": {"abiertas": len([a for a in alertas
                                     if a.estatus == m.EstatusAlerta.ABIERTA]),
                    "en_atencion": len([a for a in alertas
                                        if a.estatus == m.EstatusAlerta.EN_ATENCION])},
    }


# ==================================================================
# La cartera: quien ve que
# ==================================================================

def _jornadas(db: Session, estatus) -> list[m.Jornada]:
    return db.query(m.Jornada).filter(m.Jornada.estatus == estatus).all()


# ==================================================================
# Lo que esta corriendo
# ==================================================================

def _ficha(db: Session, j: m.Jornada, relojes: reloj.Relojes,
           plazas: dict[int, str]) -> dict:
    """Todo lo que hay que saber de una jornada en curso, ya medido con
    la hora del pais donde esta el equipo."""
    suyo = relojes.de_la_jornada(j)
    ultimo = (db.query(m.Hito)
              .filter_by(jornada_id=j.id)
              .order_by(m.Hito.marcado_en.desc()).first())
    callado = silencio(ultimo, suyo)
    servicio = j.equipo.servicio
    pais = relojes.pais(servicio.pais_id)
    falta_extra = (int((j.fin_programado - suyo).total_seconds() / 60)
                   if j.fin_programado else None)

    return {
        "jornada_id": j.id,
        "servicio_id": servicio.id,
        "servicio": servicio.folio,
        "tipo": servicio.tipo.value,
        "cliente": servicio.cliente.nombre,
        "equipo": j.equipo.alias,
        # Con un solo equipo el ejecutivo se captura en el servicio y el
        # equipo lo hereda: armarlo a mano con los campos del equipo daba
        # vacio, y el rengon de arriba decia "0 ejecutivos cubiertos"
        # todos los dias.
        "ejecutivo": j.equipo.ejecutivo_completo,
        "pais_id": servicio.pais_id,
        "pais": pais.nombre if pais else None,
        "plaza": plazas.get(j.equipo.plaza_id),
        "personas": [a.persona.nombre for a in j.personal],
        "personas_ids": [a.persona_id for a in j.personal],
        "placas": [a.vehiculo.placa for a in j.vehiculos],
        "inicio": j.inicio_programado.isoformat(),
        "fin_programado": (j.fin_programado.isoformat()
                           if j.fin_programado else None),
        "ultimo_hito": ultimo.tipo.value if ultimo else None,
        "ultima_marca": (ultimo.marcado_en.isoformat()
                         if ultimo and ultimo.marcado_en else None),
        "minutos_callado": callado,
        "silencio": color_del_silencio(callado),
        "minutos_para_horas_extra": falta_extra,
    }


def _en_la_calle(fichas: list[dict]) -> dict:
    """La gente, no los folios. El desglose importa: el implantado suma
    lo mismo todos los dias y sin separarlo tapa el movimiento real."""
    personas = set()
    eventual = set()
    implantado = set()
    for f in fichas:
        for pid in f["personas_ids"]:
            personas.add(pid)
            (eventual if f["tipo"] == m.TipoServicio.EVENTUAL.value
             else implantado).add(pid)

    ejecutivos = {f["ejecutivo"] for f in fichas if f["ejecutivo"]}
    return {
        "personas": len(personas),
        "eventual": len(eventual),
        "implantado": len(implantado),
        "ejecutivos": len(ejecutivos),
        "servicios": len({f["servicio_id"] for f in fichas}),
        "equipos": len(fichas),
        "todos_reportando": not any(f["silencio"] in ("rojo", "sin_reporte")
                                    for f in fichas),
    }


def _paises(fichas: list[dict], relojes: reloj.Relojes) -> list[dict]:
    """Un renglon por pais, con su hora. Desarma solo el '¿alla que hora
    es?' de antes de marcarle a alguien."""
    por_pais: dict[int | None, list[dict]] = {}
    for f in fichas:
        por_pais.setdefault(f["pais_id"], []).append(f)

    filas = []
    for pais_id, suyas in por_pais.items():
        personas = {pid for f in suyas for pid in f["personas_ids"]}
        plazas: dict[str, set] = {}
        for f in suyas:
            if f["plaza"]:
                plazas.setdefault(f["plaza"], set()).update(f["personas_ids"])
        filas.append({
            "pais_id": pais_id,
            "pais": suyas[0]["pais"],
            "hora_local": relojes.ahora(pais_id).isoformat(),
            "personas": len(personas),
            "servicios": len({f["servicio_id"] for f in suyas}),
            "callados": len([f for f in suyas
                             if f["silencio"] in ("rojo", "sin_reporte")]),
            "plazas": [{"plaza": nombre, "personas": len(gente)}
                       for nombre, gente in sorted(plazas.items())],
        })
    filas.sort(key=lambda x: (-x["personas"], x["pais"] or ""))
    return filas


# ==================================================================
# Lo que hay que atender, en orden de consecuencia
# ==================================================================

def _alertas(db: Session) -> list[m.AlertaIncidencia]:
    filas = (db.query(m.AlertaIncidencia)
             .filter(m.AlertaIncidencia.estatus != m.EstatusAlerta.CERRADA)
             .order_by(m.AlertaIncidencia.reportada_en.desc()).all())
    return filas


def _sin_listo(db: Session, ahora: datetime,
               relojes: reloj.Relojes) -> list[dict]:
    """Lo que arranca dentro de la ventana y le falta algo. Las faltas
    van en clave, no en español: esta consola habla tres idiomas."""
    margen = reloj.margen_de_paises(db)
    limite = ahora + timedelta(hours=VENTANA_PROXIMOS_HORAS)
    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.inicio_programado >= ahora - margen,
                        m.Jornada.inicio_programado <= limite + margen,
                        m.Jornada.estatus.notin_([m.EstatusJornada.CANCELADA,
                                                  m.EstatusJornada.TERMINADA]))
                .order_by(m.Jornada.inicio_programado).all())
    fuera = []
    for j in jornadas:
        # Lo que entro por el margen y alla todavia no esta en ventana.
        suyo = relojes.de_la_jornada(j)
        if not (suyo <= j.inicio_programado
                <= suyo + timedelta(hours=VENTANA_PROXIMOS_HORAS)):
            continue
        faltas = []
        if not j.personal:
            faltas.append("personal")
        elif any(not a.confirmado for a in j.personal):
            faltas.append("confirmar")
        if not j.vehiculos:
            faltas.append("unidad")
        if not j.origen_direccion:
            faltas.append("meet_and_greet")
        if faltas:
            fuera.append({
                "jornada_id": j.id,
                "servicio_id": j.equipo.servicio_id,
                "servicio": j.equipo.servicio.folio,
                "equipo": j.equipo.alias,
                "inicia": j.inicio_programado.isoformat(),
                "en_minutos": int((j.inicio_programado - suyo).total_seconds() / 60),
                "faltas": faltas,
            })
    return fuera


def _que_atender(alertas, fichas: list[dict], sin_listo: list[dict]) -> list[dict]:
    """El orden es por consecuencia, no por hora ni por folio: primero lo
    que puede lastimar a alguien, luego lo que deja mal a un cliente."""
    cosas = []

    for a in alertas:
        if a.estatus != m.EstatusAlerta.ABIERTA:
            continue
        cosas.append({
            "tipo": "panico", "nivel": "grave",
            "alerta_id": a.id, "servicio_id": a.servicio_id,
            "canal": a.canal.value,
            "reportada_en": (a.reportada_en.isoformat()
                             if a.reportada_en else None),
        })

    mudos = [f for f in fichas if f["silencio"] in ("rojo", "sin_reporte")]
    mudos.sort(key=lambda f: -(f["minutos_callado"] or 10 ** 6))
    for f in mudos:
        cosas.append({
            "tipo": "silencio", "nivel": "grave",
            "jornada_id": f["jornada_id"], "servicio_id": f["servicio_id"],
            "servicio": f["servicio"], "equipo": f["equipo"],
            "minutos_callado": f["minutos_callado"],
            "ultimo_hito": f["ultimo_hito"],
            "ultima_marca": f["ultima_marca"],
        })

    for x in sorted(sin_listo, key=lambda x: x["en_minutos"]):
        cosas.append({
            "tipo": "sin_listo", "nivel": "alerta",
            "jornada_id": x["jornada_id"], "servicio_id": x["servicio_id"],
            "servicio": x["servicio"], "equipo": x["equipo"],
            "en_minutos": x["en_minutos"], "faltas": x["faltas"],
        })

    return cosas


def _nivel(atender: list[dict]) -> str:
    if not atender:
        return "normal"
    return "grave" if any(c["nivel"] == "grave" for c in atender) else "atender"


# ==================================================================
# La tira del dia, un eje por pais
# ==================================================================

def _dia(db: Session, relojes: reloj.Relojes) -> list[dict]:
    paises = db.query(m.Pais).filter_by(activo=True).all()
    tiras = []
    for pais in paises:
        hoy = relojes.hoy(pais.id)
        jornadas = (db.query(m.Jornada)
                    .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                    .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
                    .filter(m.Servicio.pais_id == pais.id,
                            m.Jornada.fecha == hoy,
                            m.Jornada.estatus != m.EstatusJornada.CANCELADA)
                    .order_by(m.Jornada.inicio_programado).all())
        barras = []
        for j in jornadas:
            ultimo = (db.query(m.Hito)
                      .filter_by(jornada_id=j.id)
                      .order_by(m.Hito.marcado_en.desc()).first())
            callado = (silencio(ultimo, relojes.de_la_jornada(j))
                       if j.estatus == m.EstatusJornada.EN_CURSO else None)
            barras.append({
                "jornada_id": j.id,
                "servicio_id": j.equipo.servicio_id,
                "servicio": j.equipo.servicio.folio,
                "equipo": j.equipo.alias,
                "estatus": j.estatus.value,
                "inicio": j.inicio_programado.isoformat(),
                "fin_programado": (j.fin_programado.isoformat()
                                   if j.fin_programado else None),
                "fin_real": j.fin_real.isoformat() if j.fin_real else None,
                "silencio": (color_del_silencio(callado)
                             if j.estatus == m.EstatusJornada.EN_CURSO else None),
                "minutos_callado": callado,
                "ultima_marca": (ultimo.marcado_en.isoformat()
                                 if ultimo and ultimo.marcado_en else None),
            })
        if barras:
            tiras.append({
                "pais_id": pais.id,
                "pais": pais.nombre,
                "ahora": relojes.ahora(pais.id).isoformat(),
                "barras": barras,
            })
    tiras.sort(key=lambda t: -len(t["barras"]))
    return tiras


# ==================================================================
# El dinero, cuatro cifras
# ==================================================================

def _dinero(db: Session, ahora: datetime, relojes: reloj.Relojes) -> dict:
    viaticos = db.query(m.AsignacionViatico).all()

    por_transferir = [v for v in viaticos
                      if v.estatus in (m.EstatusViatico.ASIGNADO,
                                       m.EstatusViatico.SOLICITADO)]
    en_comprobacion = [v for v in viaticos
                       if v.estatus == m.EstatusViatico.EN_COMPROBACION]
    # El plazo de comprobacion se vence a la hora de alla.
    vencidos = [
        v for v in en_comprobacion
        if v.limite_comprobacion and v.limite_comprobacion < relojes.ahora(
            reloj.pais_de_la_jornada(v.jornada))]

    corte = lunes_de(ahora.date())
    nomina = db.query(m.NominaSemanal).filter_by(fecha_corte=corte).first()

    cierres = db.query(m.Cierre).all()
    abiertos = [c for c in cierres if c.estatus == m.EstatusCierre.ABIERTO]
    cierres_vencidos = [c for c in abiertos
                        if c.limite_consultor < relojes.ahora(
                            c.servicio.pais_id if c.servicio else None)]

    return {
        "por_depositar": {
            "monto": sum((_d(v.monto_total) for v in por_transferir), CERO),
            "cuantos": len(por_transferir)},
        "afuera_sin_comprobar": {
            "monto": sum((_d(v.monto_total) for v in en_comprobacion), CERO),
            "personas": len({v.persona_id for v in en_comprobacion}),
            "vencido": sum((_d(v.monto_total) for v in vencidos), CERO),
            "detalle_vencido": [
                {"viatico_id": v.id, "persona": v.persona.nombre,
                 "monto": _d(v.monto_total),
                 "vencio": v.limite_comprobacion.isoformat()}
                for v in vencidos]},
        "nomina_de_la_semana": {
            "fecha_corte": corte.isoformat(),
            # En clave, no en español: la consola habla tres idiomas.
            "estatus": nomina.estatus.value if nomina else "sin_calcular",
            "total": _d(nomina.total) if nomina else CERO,
            "personas": len(nomina.renglones) if nomina else 0},
        "cierres": {
            "abiertos": len(abiertos),
            "vencidos": len(cierres_vencidos),
            "esperando_finanzas": len([c for c in cierres
                                       if c.estatus == m.EstatusCierre.ENVIADO_FINANZAS]),
            "devueltos": [{"servicio": c.servicio.folio,
                           "motivo": c.devuelto_motivo}
                          for c in cierres
                          if c.estatus == m.EstatusCierre.DEVUELTO_A_OPERACION]},
    }


# ==================================================================
# La calidad del reporte: ¿nos estan reportando de verdad?
# ==================================================================

def _calidad(db: Session, relojes: reloj.Relojes,
             en_curso: list[m.Jornada]) -> dict:
    """Las tres cifras que no hablan de la operacion sino de si lo que
    nos reportan es cierto. Hoy solo se ven al cerrar cada servicio, una
    por una, y nadie las mira juntas."""
    hoy_por_pais = {p.id: relojes.hoy(p.id)
                    for p in db.query(m.Pais).filter_by(activo=True).all()}

    del_dia = (db.query(m.Jornada)
               .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
               .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
               .filter(m.Jornada.estatus != m.EstatusJornada.CANCELADA).all())
    del_dia = [j for j in del_dia
               if j.fecha == hoy_por_pais.get(j.equipo.servicio.pais_id)]
    ids = [j.id for j in del_dia]

    # Una llegada marcada fuera de la geocerca no se guarda: operacion.py
    # la rechaza con 409 y deja una alerta. Asi que lo que se puede
    # contar no son marcas malas sino INTENTOS, que para el caso dice
    # mas: alguien quiso reportar que ya habia llegado desde lejos.
    intentos = por_validar = 0
    if ids:
        intentos = (db.query(m.Alerta)
                    .filter(m.Alerta.jornada_id.in_(ids),
                            m.Alerta.tipo == m.TipoAlerta.FUERA_DE_GEOCERCA)
                    .count())
    por_validar = (db.query(m.Hito)
                   .filter(m.Hito.requiere_revision.is_(True)).count())

    # Una unidad en la calle sin estado de entrada es un daño que despues
    # no se le puede atribuir a nadie.
    sin_entrada = 0
    for j in en_curso:
        for a in j.vehiculos:
            existe = (db.query(m.RevisionUnidad)
                      .filter_by(servicio_id=j.equipo.servicio_id,
                                 vehiculo_id=a.vehiculo_id,
                                 tipo=m.TipoRevision.RECIBE).first())
            if not existe:
                sin_entrada += 1

    relevos = 0
    if ids:
        relevos = (db.query(m.Reemplazo)
                   .filter(m.Reemplazo.jornada_id.in_(ids)).count())

    return {
        "intentos_fuera_de_geocerca": intentos,
        "marcas_por_validar": por_validar,
        "unidades_sin_revision_de_entrada": sin_entrada,
        "relevos_hoy": relevos,
    }


def marcas_raras(db: Session, ahora: datetime | None = None) -> dict:
    """El detalle detras de las dos cifras de calidad. Resolverlas sigue
    siendo de la central; esto es para poder verlas sin pedirlas."""
    ahora = ahora or datetime.now()
    relojes = reloj.Relojes(db, ahora)

    consulta = (db.query(m.Hito)
                .join(m.Jornada, m.Hito.jornada_id == m.Jornada.id)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id))

    hoy_por_pais = {p.id: relojes.hoy(p.id)
                    for p in db.query(m.Pais).filter_by(activo=True).all()}

    def ficha(h: m.Hito) -> dict:
        j = h.jornada
        return {
            "hito_id": h.id,
            "jornada_id": j.id,
            "servicio_id": j.equipo.servicio_id,
            "servicio": j.equipo.servicio.folio,
            "equipo": j.equipo.alias,
            "persona": h.persona.nombre if h.persona else None,
            "tipo": h.tipo.value,
            "marcado_en": h.marcado_en.isoformat() if h.marcado_en else None,
            "distancia_m": h.distancia_origen_m,
            "geocerca_m": j.geocerca_metros,
            "fuera_de_ventana": h.fuera_de_ventana,
            "nota": h.nota,
        }

    alertas = (db.query(m.Alerta)
               .join(m.Jornada, m.Alerta.jornada_id == m.Jornada.id)
               .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
               .filter(m.Alerta.tipo == m.TipoAlerta.FUERA_DE_GEOCERCA))

    intentos = []
    for a in alertas.order_by(m.Alerta.creada_en.desc()).all():
        j = a.jornada
        if j.fecha == hoy_por_pais.get(j.equipo.servicio.pais_id):
            intentos.append({
            "alerta_id": a.id,
            "jornada_id": j.id,
            "servicio_id": j.equipo.servicio_id,
            "servicio": j.equipo.servicio.folio,
            "equipo": j.equipo.alias,
            "persona": a.persona.nombre if a.persona else None,
            # El mensaje trae la distancia y el limite.
            "mensaje": a.mensaje,
            "creada_en": a.creada_en.isoformat() if a.creada_en else None,
            "atendida": a.atendida,
        })

    por_validar = consulta.filter(m.Hito.requiere_revision.is_(True)).all()

    return {
        "intentos_fuera_de_geocerca": intentos,
        "por_validar": [ficha(h) for h in sorted(
            por_validar, key=lambda x: x.marcado_en or datetime.min)],
    }

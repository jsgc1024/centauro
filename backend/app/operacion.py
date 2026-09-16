"""Ciclo diario del servicio: hitos del conductor, candados, alertas
de la central y notificaciones al cliente.

Candados aprobados:
  1. Geocerca obligatoria en el punto de origen.
  2. Ventana de tiempo: si marca fuera de horario, lo revisa la central.
  3. Rastreo continuo durante el servicio (reportes de standby).
"""
import math
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import reloj

# --- parametros del ciclo
MINUTOS_ANTES_PERMITIDOS = 60      # puede marcar llegada hasta 1 h antes
MINUTOS_DESPUES_PERMITIDOS = 15    # despues de esto lo revisa la central
VENTANA_PROXIMOS_HORAS = 2         # la central toma el seguimiento a 2 h de iniciar
INTERVALO_STANDBY_HORAS = 2        # si no reporta en el intervalo, alerta
AVISO_HORAS_EXTRA_MINUTOS = 30     # aviso preventivo antes de cumplir la jornada
# Una marca que llega mas tarde de lo que dice haberse hecho es una
# marca diferida: el equipo la guardo sin senal y se mando despues. Dos
# minutos de margen son el viaje normal de una peticion; a partir de ahi
# es otra cosa y se dice.
MINUTOS_PARA_DIFERIDO = 2
# Y cuando la diferencia es grande, la central tiene que mirarla: media
# hora da para marcar una llegada desde otro lado de la ciudad.
MINUTOS_DIFERIDO_REVISABLE = 30
HORAS_VIGENCIA_ENLACE = 4          # el enlace de seguimiento expira tras el servicio


def distancia_metros(lat1, lon1, lat2, lon2) -> int:
    """Distancia entre dos puntos sobre la superficie terrestre."""
    r = 6371000
    f1, f2 = math.radians(float(lat1)), math.radians(float(lat2))
    df = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = (math.sin(df / 2) ** 2
         + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2)
    return int(r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _alertar(db: Session, jornada_id: int, tipo: m.TipoAlerta, mensaje: str) -> m.Alerta:
    alerta = m.Alerta(jornada_id=jornada_id, tipo=tipo, mensaje=mensaje)
    db.add(alerta)
    return alerta


def _notificar(db: Session, jornada: m.Jornada, destinatario: m.Destinatario,
               canal: m.Canal, asunto: str, cuerpo: str,
               enlace: str | None = None, expira: datetime | None = None) -> m.Notificacion:
    servicio = jornada.equipo.servicio
    correo = (servicio.solicitante_correo if destinatario == m.Destinatario.SOLICITANTE
              else servicio.ejecutivo_correo if destinatario == m.Destinatario.EJECUTIVO
              else None)
    nota = m.Notificacion(
        jornada_id=jornada.id, servicio_id=servicio.id,
        destinatario=destinatario, canal=canal, correo=correo,
        asunto=asunto, cuerpo=cuerpo,
        enlace_seguimiento=enlace, expira_en=expira)
    db.add(nota)
    return nota


def _ficha_equipo(jornada: m.Jornada) -> str:
    personal = ", ".join(a.persona.nombre for a in jornada.personal) or "por asignar"
    unidades = ", ".join(
        f"{a.vehiculo.categoria.nombre} placas {a.vehiculo.placa}"
        for a in jornada.vehiculos) or "por asignar"
    return f"Conductor: {personal}. Unidad: {unidades}."


# ---------------------------------------------------------------- hitos

def registrar_hito(db: Session, jornada_id: int, persona_id: int,
                   tipo: m.TipoHito, lat=None, lon=None,
                   marcado_en: datetime | None = None,
                   nota: str | None = None) -> dict:
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    if not any(a.persona_id == persona_id for a in jornada.personal):
        raise HTTPException(403, "Esa persona no esta asignada a la jornada")

    # Lo que dice el telefono y lo que sabe el servidor son dos cosas.
    # La app puede marcar sin senal y mandar despues, asi que la hora de
    # la marca puede ser anterior; lo que no puede es perderse el rastro
    # de cuanto tardo en llegar.
    #
    # Y "lo que sabe el servidor" es la hora del pais donde esta el
    # equipo, no la del contenedor. La marca se compara contra
    # `inicio_programado`, que guarda hora de pared de alla: con el
    # reloj del servidor, un conductor en Brasil que marcaba puntual
    # caia fuera de la ventana por tres horas y le levantaba alerta.
    recibido = reloj.ahora_de_la_jornada(db, jornada)
    ahora = marcado_en or recibido
    atraso = (recibido - ahora).total_seconds() / 60
    hito = m.Hito(jornada_id=jornada.id, persona_id=persona_id, tipo=tipo,
                  marcado_en=ahora, lat=lat, lon=lon, nota=nota,
                  recibido_en=recibido,
                  diferido=atraso > MINUTOS_PARA_DIFERIDO)
    alertas: list[str] = []

    if hito.diferido:
        alertas.append(f"Marca diferida: se hizo hace {atraso:.0f} min y "
                       f"llego ahora")
        # Una diferencia grande no se descarta ni se acepta en silencio:
        # se registra y la central decide. Media hora da para marcar una
        # llegada desde otro lado de la ciudad.
        if atraso > MINUTOS_DIFERIDO_REVISABLE:
            hito.requiere_revision = True

    # ---- Candado 1: geocerca en el origen
    if tipo == m.TipoHito.LLEGADA_ORIGEN:
        if jornada.origen_lat is None or jornada.origen_lon is None:
            raise HTTPException(400, "La jornada no tiene punto de origen configurado")
        if lat is None or lon is None:
            raise HTTPException(400, "Se requiere ubicacion para marcar la llegada")

        distancia = distancia_metros(lat, lon, jornada.origen_lat, jornada.origen_lon)
        hito.distancia_origen_m = distancia
        hito.dentro_geocerca = distancia <= jornada.geocerca_metros

        if not hito.dentro_geocerca:
            _alertar(db, jornada.id, m.TipoAlerta.FUERA_DE_GEOCERCA,
                     f"Intento de marcar llegada a {distancia} m del origen "
                     f"(limite {jornada.geocerca_metros} m)")
            db.commit()
            raise HTTPException(409, {
                "mensaje": "No se puede marcar la llegada fuera de la geocerca",
                "distancia_metros": distancia,
                "limite_metros": jornada.geocerca_metros,
            })

    # ---- Candado 2: ventana de tiempo
    if tipo in (m.TipoHito.LLEGADA_ORIGEN, m.TipoHito.CONTACTO_EJECUTIVO):
        limite_antes = jornada.inicio_programado - timedelta(minutes=MINUTOS_ANTES_PERMITIDOS)
        limite_despues = jornada.inicio_programado + timedelta(minutes=MINUTOS_DESPUES_PERMITIDOS)
        if ahora < limite_antes or ahora > limite_despues:
            hito.fuera_de_ventana = True
            hito.requiere_revision = True
            desfase = (ahora - jornada.inicio_programado).total_seconds() / 60
            _alertar(db, jornada.id, m.TipoAlerta.FUERA_DE_VENTANA,
                     f"{tipo.value} marcado con {desfase:+.0f} min respecto a la "
                     f"hora de presentacion. Requiere revision de la central.")
            alertas.append("Marca fuera de la ventana de horario: la central debe revisarla")

    # ---- Secuencia obligatoria
    if tipo == m.TipoHito.CONTACTO_EJECUTIVO:
        previo = (db.query(m.Hito)
                  .filter_by(jornada_id=jornada.id, tipo=m.TipoHito.LLEGADA_ORIGEN)
                  .first())
        if not previo:
            raise HTTPException(409, "Primero hay que marcar la llegada al punto de origen")

    db.add(hito)

    # ---- efectos de cada hito
    servicio = jornada.equipo.servicio

    if tipo == m.TipoHito.LLEGADA_ORIGEN:
        jornada.estatus = m.EstatusJornada.EN_CURSO
        cuerpo = (f"El equipo de seguridad llego al punto de origen y esta en espera "
                  f"de hacer contacto. {_ficha_equipo(jornada)}")
        _notificar(db, jornada, m.Destinatario.EJECUTIVO, m.Canal.AMBOS,
                   "Su equipo de seguridad esta en el lugar", cuerpo)
        _notificar(db, jornada, m.Destinatario.SOLICITANTE, m.Canal.AMBOS,
                   f"{servicio.folio}: equipo en el punto de origen",
                   cuerpo + f" Hora de presentacion: {jornada.inicio_programado:%H:%M}.")

    elif tipo == m.TipoHito.CONTACTO_EJECUTIVO:
        jornada.inicio_real = ahora

        # El implantado arranca de verdad con el meet and greet: hasta
        # ese momento esta programado —armado, con gente y unidad— y no
        # corriendo. Es un servicio continuo y el estatus tiene que
        # decir en que va, no repetir que ya se planeo.
        #
        # El eventual se queda como estaba: ahi el estatus lo mueve el
        # cierre del dia, no el primer contacto.
        if (servicio.tipo == m.TipoServicio.IMPLANTADO
                and servicio.estatus in (m.EstatusServicio.PLANEADO,
                                         m.EstatusServicio.ASIGNADO)):
            servicio.estatus = m.EstatusServicio.EN_CURSO
        token = secrets.token_urlsafe(16)
        expira = jornada.fin_programado + timedelta(hours=HORAS_VIGENCIA_ENLACE)
        enlace = f"https://centauro.lat/seguimiento/{token}"
        _notificar(db, jornada, m.Destinatario.SOLICITANTE, m.Canal.AMBOS,
                   f"{servicio.folio}: servicio iniciado",
                   f"Se hizo contacto con el ejecutivo a las {ahora:%H:%M}. "
                   f"Puede seguir el servicio en vivo en el enlace. "
                   f"El enlace expira al terminar el servicio.",
                   enlace=enlace, expira=expira)
        _notificar(db, jornada, m.Destinatario.EJECUTIVO, m.Canal.AMBOS,
                   "Servicio iniciado",
                   f"Su servicio inicio a las {ahora:%H:%M}. {_ficha_equipo(jornada)}")

    elif tipo == m.TipoHito.FIN_SERVICIO:
        jornada.fin_real = ahora
        jornada.estatus = m.EstatusJornada.TERMINADA
        _notificar(db, jornada, m.Destinatario.SOLICITANTE, m.Canal.CORREO,
                   f"{servicio.folio}: servicio terminado",
                   f"El servicio del {jornada.fecha} termino a las {ahora:%H:%M}.")

    db.commit()
    db.refresh(hito)

    return {
        "hito_id": hito.id,
        "tipo": tipo.value,
        "marcado_en": hito.marcado_en.isoformat(),
        "recibido_en": hito.recibido_en.isoformat() if hito.recibido_en else None,
        "diferido": hito.diferido,
        "distancia_origen_m": hito.distancia_origen_m,
        "dentro_geocerca": hito.dentro_geocerca,
        "requiere_revision": hito.requiere_revision,
        "avisos": alertas,
    }


def ajustar_hito(db: Session, hito_id: int, nuevo_momento: datetime,
                 ajustado_por_id: int, justificacion: str) -> dict:
    """La central puede ajustar el corte de tiempo, con justificacion obligatoria."""
    if not justificacion or len(justificacion.strip()) < 10:
        raise HTTPException(400, "La justificacion del ajuste es obligatoria")

    hito = db.get(m.Hito, hito_id)
    if not hito:
        raise HTTPException(404, f"No existe el hito {hito_id}")

    hito.marcado_original = hito.marcado_en
    hito.marcado_en = nuevo_momento
    hito.ajustado_por_id = ajustado_por_id
    hito.justificacion_ajuste = justificacion
    hito.requiere_revision = False

    if hito.tipo == m.TipoHito.CONTACTO_EJECUTIVO:
        hito.jornada.inicio_real = nuevo_momento
    elif hito.tipo == m.TipoHito.FIN_SERVICIO:
        hito.jornada.fin_real = nuevo_momento

    db.commit()
    return {"resultado": "ajustado", "hito_id": hito.id,
            "original": hito.marcado_original.isoformat(),
            "nuevo": nuevo_momento.isoformat(),
            "justificacion": justificacion}


# ---------------------------------------------------------------- tableros

def tablero_proximos(db: Session, ahora: datetime | None = None) -> list[dict]:
    """Servicios a dos horas de iniciar: valida confirmacion del recurso,
    viatico transferido y vehiculo asignado."""
    # Una consulta no puede llevar tres relojes, asi que se ensancha la
    # ventana por la mayor diferencia horaria entre los paises activos y
    # despues se filtra pais por pais. Traer de mas y descartar es
    # correcto; traer de menos es perder un servicio que esta por
    # arrancar, que es justo lo que esta pantalla existe para evitar.
    relojes = reloj.Relojes(db, ahora)
    margen = reloj.margen_de_paises(db)
    ahora = ahora or datetime.now()
    limite = ahora + timedelta(hours=VENTANA_PROXIMOS_HORAS)

    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.inicio_programado >= ahora - margen,
                        m.Jornada.inicio_programado <= limite + margen,
                        m.Jornada.estatus.in_([m.EstatusJornada.PLANEADA,
                                               m.EstatusJornada.CONFIRMADA,
                                               m.EstatusJornada.PROXIMA_A_INICIAR]))
                .all())

    tablero = []
    for j in jornadas:
        # Ahora si, con el reloj de ese pais. Lo que entro por el margen
        # y no le toca todavia, se descarta aqui.
        suyo = relojes.de_la_jornada(j)
        if not (suyo <= j.inicio_programado
                <= suyo + timedelta(hours=VENTANA_PROXIMOS_HORAS)):
            continue
        pendientes = []

        sin_confirmar = [a.persona.nombre for a in j.personal if not a.confirmado]
        if not j.personal:
            pendientes.append("Sin personal asignado")
        elif sin_confirmar:
            pendientes.append(f"Recurso sin confirmar: {', '.join(sin_confirmar)}")

        if not j.vehiculos:
            pendientes.append("Sin vehiculo asignado")

        viaticos = (db.query(m.AsignacionViatico)
                    .filter_by(jornada_id=j.id).all())
        if not viaticos:
            pendientes.append("Sin viaticos asignados")
        else:
            sin_transferir = [v.persona.nombre for v in viaticos
                              if v.estatus in (m.EstatusViatico.ASIGNADO,
                                               m.EstatusViatico.SOLICITADO)]
            if sin_transferir:
                pendientes.append(f"Viatico no transferido: {', '.join(sin_transferir)}")

        j.estatus = m.EstatusJornada.PROXIMA_A_INICIAR
        minutos = (j.inicio_programado - suyo).total_seconds() / 60

        tablero.append({
            "jornada_id": j.id,
            "servicio": j.equipo.servicio.folio,
            "equipo": j.equipo.alias,
            "inicia_en_minutos": int(minutos),
            "inicio_programado": j.inicio_programado.isoformat(),
            "modalidad": j.modalidad.codigo.value,
            "listo": not pendientes,
            "pendientes": pendientes,
        })

    db.commit()
    return sorted(tablero, key=lambda x: x["inicia_en_minutos"])


def revisar_standby(db: Session, ahora: datetime | None = None) -> list[dict]:
    """Si el conductor no reporta en el intervalo, la central recibe alerta."""
    # El silencio de un servicio se mide contra la hora del pais donde
    # esta: con el reloj del servidor, todo servicio brasileño aparentaba
    # tres horas de silencio desde que arrancaba y se le levantaba
    # alerta falsa de inmediato.
    relojes = reloj.Relojes(db, ahora)

    en_curso = (db.query(m.Jornada)
                .filter(m.Jornada.estatus == m.EstatusJornada.EN_CURSO).all())

    generadas = []
    for j in en_curso:
        suyo = relojes.de_la_jornada(j)
        limite = suyo - timedelta(hours=INTERVALO_STANDBY_HORAS)
        ultimo = (db.query(m.Hito)
                  .filter_by(jornada_id=j.id)
                  .order_by(m.Hito.marcado_en.desc())
                  .first())
        referencia = ultimo.marcado_en if ultimo else j.inicio_programado
        if referencia < limite:
            horas = (suyo - referencia).total_seconds() / 3600
            ya = (db.query(m.Alerta)
                  .filter_by(jornada_id=j.id, tipo=m.TipoAlerta.SIN_REPORTE,
                             atendida=False).first())
            if ya:
                continue
            _alertar(db, j.id, m.TipoAlerta.SIN_REPORTE,
                     f"Sin reporte hace {horas:.1f} h. Ultimo movimiento: "
                     f"{referencia:%d/%m %H:%M}.")
            generadas.append({"jornada_id": j.id,
                              "servicio": j.equipo.servicio.folio,
                              "horas_sin_reporte": round(horas, 1)})
    db.commit()
    return generadas


def avisar_horas_extra(db: Session, ahora: datetime | None = None) -> list[dict]:
    """Aviso preventivo 30 minutos antes de cumplir la jornada.
    Se notifica al solicitante y al ejecutivo."""
    # La ventana es de media hora. Con el reloj del servidor y tres
    # horas de diferencia, para Brasil no coincidia nunca: el aviso
    # preventivo de horas extra sencillamente no existia fuera de
    # Mexico. Se ensancha la consulta por el margen entre paises y se
    # afina despues, uno por uno.
    relojes = reloj.Relojes(db, ahora)
    margen = reloj.margen_de_paises(db)
    ahora = ahora or datetime.now()

    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.estatus == m.EstatusJornada.EN_CURSO,
                        m.Jornada.fin_programado >= ahora - margen,
                        m.Jornada.fin_programado
                        <= ahora + timedelta(minutes=AVISO_HORAS_EXTRA_MINUTOS)
                        + margen)
                .all())

    avisos = []
    for j in jornadas:
        suyo = relojes.de_la_jornada(j)
        if not (suyo <= j.fin_programado
                <= suyo + timedelta(minutes=AVISO_HORAS_EXTRA_MINUTOS)):
            continue
        if not j.modalidad.aplica_horas_extra:
            continue
        ya = (db.query(m.Alerta)
              .filter_by(jornada_id=j.id, tipo=m.TipoAlerta.HORAS_EXTRA_PROXIMAS)
              .first())
        if ya:
            continue

        minutos = int((j.fin_programado - ahora).total_seconds() / 60)
        cuerpo = (f"El servicio cumple sus {j.modalidad.horas} horas contratadas a las "
                  f"{j.fin_programado:%H:%M}. A partir de ese momento se generan "
                  f"horas extra. Faltan {minutos} minutos.")
        _notificar(db, j, m.Destinatario.SOLICITANTE, m.Canal.AMBOS,
                   "Aviso preventivo de horas extra", cuerpo)
        _notificar(db, j, m.Destinatario.EJECUTIVO, m.Canal.AMBOS,
                   "Aviso preventivo de horas extra", cuerpo)
        _alertar(db, j.id, m.TipoAlerta.HORAS_EXTRA_PROXIMAS,
                 f"Aviso de horas extra enviado. Cierre programado {j.fin_programado:%H:%M}.")
        avisos.append({"jornada_id": j.id, "servicio": j.equipo.servicio.folio,
                       "faltan_minutos": minutos})

    db.commit()
    return avisos


# ====================================================================
# Cerrar un dia a mano
#
# Un dia que se trabajo y que nadie marco se queda abierto, y mientras
# lo este no entra a nomina y su servicio no se puede cerrar para
# facturar. Alguien que trabajo no cobra por una marca que falto.
#
# Por eso la central puede cerrarlo. Pero cerrarlo a mano es decir "yo
# doy fe de que esto ocurrio asi" sin una marca desde la calle que lo
# respalde, y eso tiene que verse toda la vida del registro: queda
# firmado con quien lo cerro, cuando y por que. Un cierre a mano que se
# viera igual que un dia marcado seria una puerta para inventar dias.
# ====================================================================

# Cuanto se espera despues de la hora programada de termino antes de
# considerar que ese dia se quedo sin cerrar. Tres horas: un servicio
# se alarga, y avisar a las 18:05 de algo que termina a las 18:00 seria
# ruido que la central aprende a ignorar.
HORAS_DE_GRACIA = 3

# Lo mismo que se le exige a un ajuste de hito. Escribir diez caracteres
# obliga a decir algo; "ok" no explica nada dentro de tres meses.
MINIMO_JUSTIFICACION = 10


def dias_sin_cerrar(db: Session, ahora: datetime | None = None,
                    pais_id: int | None = None) -> list[dict]:
    """Los dias que ya pasaron y siguen abiertos.

    Es la lista de trabajo de la central: cada renglon es alguien que
    trabajo y todavia no puede cobrar. Sale ordenada por antiguedad
    porque el mas viejo es el que mas cerca esta de convertirse en un
    reclamo.
    """
    # Cada dia se juzga con la hora de su pais. Sin esto, un dia
    # brasileño aparecia aqui tres horas antes de tiempo —y la central
    # podia cerrar y pagar un dia que todavia estaba corriendo, que es
    # justo lo que el candado de `cerrar_a_mano` dice impedir.
    relojes = reloj.Relojes(db, ahora)
    margen = reloj.margen_de_paises(db)
    ahora = ahora or datetime.now()
    limite = ahora - timedelta(hours=HORAS_DE_GRACIA)

    q = (db.query(m.Jornada)
         .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
         .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
         .filter(m.Jornada.fin_programado < limite + margen,
                 m.Jornada.estatus.notin_([m.EstatusJornada.TERMINADA,
                                           m.EstatusJornada.CANCELADA])))
    if pais_id:
        q = q.filter(m.Servicio.pais_id == pais_id)

    abiertas = q.order_by(m.Jornada.fin_programado).all()
    if not abiertas:
        return []

    # Las marcas de todas de un jalon: la central abre esta pantalla
    # cada rato y una consulta por dia se nota.
    marcas: dict[int, set] = {}
    for h in (db.query(m.Hito)
              .filter(m.Hito.jornada_id.in_([j.id for j in abiertas])).all()):
        marcas.setdefault(h.jornada_id, set()).add(h.tipo)

    salida = []
    for j in abiertas:
        servicio = j.equipo.servicio
        # Lo que entro por el margen y alla todavia no cumple las horas
        # de gracia, se descarta: ese dia aun puede estar corriendo.
        suyo = relojes.ahora(servicio.pais_id)
        if j.fin_programado >= suyo - timedelta(hours=HORAS_DE_GRACIA):
            continue
        hechos = marcas.get(j.id, set())
        salida.append({
            "jornada_id": j.id,
            "fecha": j.fecha.isoformat(),
            "folio": servicio.folio,
            "servicio_id": servicio.id,
            "tipo": servicio.tipo.value,
            "equipo": j.equipo.alias,
            "estatus": j.estatus.value,
            "inicio_programado": j.inicio_programado.isoformat(),
            "fin_programado": j.fin_programado.isoformat(),
            "inicio_real": j.inicio_real.isoformat() if j.inicio_real else None,
            "horas_abierto": round(
                (suyo - j.fin_programado).total_seconds() / 3600),
            # Que se alcanzo a marcar. Un dia con contacto y sin fin es
            # una marca que falto; uno sin ninguna marca es un dia del
            # que no se sabe nada, y no es lo mismo.
            "marcas": sorted(h.value for h in hechos),
            "arranco": m.TipoHito.CONTACTO_EJECUTIVO in hechos,
            "personal": [{"persona_id": a.persona_id,
                          "nombre": a.persona.nombre if a.persona else None,
                          "rol": a.rol.nombre if a.rol else None}
                         for a in j.personal],
        })
    return salida


def cerrar_a_mano(db: Session, jornada_id: int, quien_id: int,
                  justificacion: str, fin_real: datetime | None = None,
                  inicio_real: datetime | None = None,
                  ahora: datetime | None = None) -> dict:
    """La central da fe de que ese dia se trabajo y a que horas.

    No inventa hitos. Un hito dice "alguien marco esto desde la calle" y
    eso aqui no paso; fabricar uno seria ensuciar la unica evidencia que
    tenemos de lo que si se marco. Lo que se guarda es lo que de verdad
    ocurrio: la central cerro este dia, a esta hora, por esta razon.
    """
    if not justificacion or len(justificacion.strip()) < MINIMO_JUSTIFICACION:
        raise HTTPException(400, {
            "mensaje": "Falta decir por que se cierra a mano",
            "que_hacer": "Escribe al menos "
                         f"{MINIMO_JUSTIFICACION} caracteres. Dentro de tres "
                         "meses esta nota va a ser lo unico que explique "
                         "por que este dia no tiene marcas."})

    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    # Con la hora del pais del servicio. El candado de abajo —"un dia no
    # se cierra antes de que termine"— es el que impide pagar trabajo
    # que todavia no ocurre, y con el reloj del servidor se saltaba solo
    # para los paises adelantados.
    ahora = reloj.ahora_de_la_jornada(db, jornada, ahora)

    if jornada.estatus == m.EstatusJornada.CANCELADA:
        raise HTTPException(409, {
            "mensaje": "Ese dia esta cancelado",
            "que_hacer": "Un dia cancelado no se cierra: no se trabajo."})

    if jornada.estatus == m.EstatusJornada.TERMINADA:
        raise HTTPException(409, {
            "mensaje": "Ese dia ya esta cerrado",
            "que_hacer": ("Lo cerro la central el "
                          f"{jornada.cerrada_a_mano_en:%d/%m %H:%M}"
                          if jornada.cerrada_a_mano_en
                          else "Se cerro con la marca del equipo. Si la hora "
                               "quedo mal, se ajusta el hito.")})

    # Un dia no se puede cerrar antes de que termine. Cerrar por
    # adelantado es pagar por trabajo que todavia no ocurre, y es
    # exactamente el agujero que este permiso podria abrir.
    if jornada.fin_programado > ahora:
        raise HTTPException(409, {
            "mensaje": "Ese dia todavia no termina",
            "que_hacer": "Termina a las "
                         f"{jornada.fin_programado:%H:%M}. Un dia se cierra "
                         "cuando ya paso, no antes."})

    fin = fin_real or jornada.fin_programado
    if fin > ahora:
        raise HTTPException(409, {
            "mensaje": "Esa hora de termino todavia no llega",
            "que_hacer": "No se puede cerrar un dia a una hora que aun no "
                         "ocurre."})

    inicio = inicio_real or jornada.inicio_real or jornada.inicio_programado
    if fin <= inicio:
        raise HTTPException(409, {
            "mensaje": "El servicio no puede terminar antes de empezar",
            "que_hacer": f"Empezo a las {inicio:%H:%M}. La hora de termino "
                         "tiene que ser despues."})

    jornada.inicio_real = inicio
    jornada.fin_real = fin
    jornada.estatus = m.EstatusJornada.TERMINADA
    jornada.cerrada_a_mano_por_id = quien_id
    jornada.cerrada_a_mano_en = ahora
    jornada.cierre_motivo = justificacion.strip()
    db.commit()

    horas = round((fin - inicio).total_seconds() / 3600, 2)
    return {"resultado": "dia cerrado a mano",
            "jornada_id": jornada.id,
            "fecha": jornada.fecha.isoformat(),
            "inicio_real": inicio.isoformat(),
            "fin_real": fin.isoformat(),
            "horas": horas,
            "motivo": jornada.cierre_motivo,
            "personas": len(jornada.personal),
            "nota": ("Este dia ya entra al corte de nomina. Queda marcado "
                     "como cerrado a mano.")}


def reabrir(db: Session, jornada_id: int, quien_id: int,
            justificacion: str) -> dict:
    """Deshacer un cierre a mano que se hizo mal.

    Solo se deshace lo que la central cerro. Un dia que el equipo marco
    desde la calle no se reabre por aqui: esa hora se corrige ajustando
    el hito, que es donde queda el rastro.
    """
    if not justificacion or len(justificacion.strip()) < MINIMO_JUSTIFICACION:
        raise HTTPException(400, "Falta decir por que se reabre")

    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    if not jornada.cerrada_a_mano_en:
        raise HTTPException(409, {
            "mensaje": "Ese dia no lo cerro la central",
            "que_hacer": "Lo cerro el equipo con su marca. Si la hora quedo "
                         "mal, se ajusta el hito."})

    # Si ya se pago, reabrir no devuelve el dinero: lo que cambie se
    # arrastra como ajuste al siguiente corte. Decirlo aqui evita que
    # alguien crea que esto revierte un pago.
    pagado = (db.query(m.ConceptoNomina)
              .filter_by(jornada_id=jornada.id).first() is not None)

    # Se deshace todo lo que escribio el cierre a mano, la hora de
    # inicio incluida. Dejarla era peor que no haber cerrado: quedaba
    # una hora que tecleo alguien en una oficina, sin firma, que se lee
    # exactamente igual que una marcada desde la calle.
    #
    # Y el dia vuelve a PLANEADA, no a EN_CURSO. EN_CURSO significa
    # "esta pasando ahora mismo" para el pulso de la central, para el
    # barrido de standby y para el panorama de direccion: un dia
    # reabierto de hace tres semanas subia a la banda roja con "sin
    # reporte hace 512 horas".
    jornada.estatus = m.EstatusJornada.PLANEADA
    jornada.fin_real = None
    if jornada.cerrada_a_mano_en:
        jornada.inicio_real = None
    jornada.cerrada_a_mano_por_id = None
    jornada.cerrada_a_mano_en = None
    jornada.cierre_motivo = None
    db.commit()

    return {"resultado": "dia reabierto", "jornada_id": jornada.id,
            "ya_estaba_pagado": pagado,
            "nota": ("Ese dia ya se pago; la diferencia se arrastra como "
                     "ajuste al siguiente corte."
                     if pagado else
                     "El dia vuelve a quedar abierto.")}

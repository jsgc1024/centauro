"""Ciclo diario del servicio: hitos del conductor, candados, alertas
de la central y notificaciones al cliente.

Candados aprobados:
  1. Geocerca obligatoria en el punto de origen.
  2. Ventana de tiempo: si marca fuera de horario, lo revisa la central.
  3. Rastreo continuo durante el servicio (reportes de standby).
  4. La unidad no se suelta sin revisar: no hay fin de servicio con una
     unidad que hoy deja el servicio y no tiene su revision de entrega.
"""
import logging
import math
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import correo_html
from app import models as m
from app.cierre import _horas_extra
from app import revision
from app import reloj
from app import textos_aviso as ta

registro = logging.getLogger("centauro.operacion")

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
# Y una marca no puede venir del futuro. El reloj de un telefono se
# desfasa unos segundos y eso es ruido; dos minutos adelante ya es otra
# cosa. Lo que pase de ahi no se toma como buena: se usa la hora del
# servidor y lo mira la central.
MINUTOS_FUTURO_TOLERADO = 2
# Que tan antes del inicio programado se acepta un meet and greet puesto
# a mano por la central. No es el margen de la app --esa marca trae
# ubicacion y hora del servidor--, sino la cota de lo que alguien puede
# escribir despues: un contacto tres horas antes del servicio no es de
# este servicio, es un dedazo en la fecha o en la hora.
HORAS_ANTES_DEL_INICIO = 3


def distancia_metros(lat1, lon1, lat2, lon2) -> int:
    """Distancia entre dos puntos sobre la superficie terrestre."""
    r = 6371000
    f1, f2 = math.radians(float(lat1)), math.radians(float(lat2))
    df = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = (math.sin(df / 2) ** 2
         + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2)
    return int(r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _alertar(db: Session, jornada_id: int, tipo: m.TipoAlerta, mensaje: str,
             persona_id: int | None = None) -> m.Alerta:
    """`persona_id` va cuando la alerta es de alguien. Las de la jornada
    entera --sin reporte, horas extra-- no llevan nombre."""
    alerta = m.Alerta(jornada_id=jornada_id, tipo=tipo, mensaje=mensaje,
                      persona_id=persona_id)
    db.add(alerta)
    return alerta


def _notificar(db: Session, jornada: m.Jornada, destinatario: m.Destinatario,
               canal: m.Canal, asunto: str, cuerpo: str,
               enlace: str | None = None, expira: datetime | None = None,
               pares=None) -> m.Notificacion:
    servicio = jornada.equipo.servicio
    correo = (servicio.solicitante_correo if destinatario == m.Destinatario.SOLICITANTE
              else servicio.ejecutivo_correo if destinatario == m.Destinatario.EJECUTIVO
              else None)
    nota = m.Notificacion(
        jornada_id=jornada.id, servicio_id=servicio.id,
        destinatario=destinatario, canal=canal, correo=correo,
        asunto=asunto, cuerpo=cuerpo,
        idioma=ta.idioma_de(db, servicio, destinatario),
        datos=correo_html.guardar_datos(pares),
        enlace_seguimiento=enlace, expira_en=expira)
    db.add(nota)
    return nota


def avisar_reemplazo(db: Session, jornada: m.Jornada, quien: str,
                     clase: str = "persona", puesto: str | None = None) -> bool:
    """El cambio, contado al cliente. Devuelve si salio o no.

    **Se avisa cuando el cambio le cambia el dia al cliente**, no cuando
    el cambio existe. Un reemplazo no es un hecho administrativo: es
    otra persona tocando la puerta del ejecutivo, u otra placa esperando
    en la calle.

    - El dia en curso o el de hoy: correo de inmediato a los dos.
      Enterarse por el correo es mejor que enterarse por la ventanilla.
    - Cualquier otro dia: nada. El cambio viaja en el task sheet, que es
      donde el cliente ya busca quien va. Un correo por el cambio de la
      semana que viene gasta la atencion que hace falta para el de hoy.

    **No lleva el motivo.** Que alguien se enfermo, que no llego, que
    hubo un problema: eso es de la casa. Al cliente se le dice quien va
    ahora. Un correo que explica de mas invita a preguntar de mas sobre
    algo que ya esta resuelto.

    La ficha va con el equipo COMO QUEDA, no con lo que cambio: lo que
    el ejecutivo necesita es la lista de quien llega por el, con sus
    telefonos, no un antes y un despues que tenga que comparar.
    """
    ahora = reloj.ahora_de_la_jornada(db, jornada)
    es_de_hoy = jornada.fecha == ahora.date()
    if jornada.estatus in m.ARRANCADAS:
        pass                     # el peor caso: ya hay alguien en el coche
    elif not es_de_hoy or jornada.estatus in (m.EstatusJornada.CANCELADA,
                                              m.EstatusJornada.TERMINADA):
        return False

    servicio = jornada.equipo.servicio
    clave = "cambio_cuerpo_unidad" if clase == "unidad" else "cambio_cuerpo_persona"
    for destinatario, asunto in (
            (m.Destinatario.EJECUTIVO, "cambio_asunto_principal"),
            (m.Destinatario.SOLICITANTE, "cambio_asunto_solicitante")):
        idioma = ta.idioma_de(db, servicio, destinatario)
        # El puesto se traduce con la tabla del task sheet: "Conductor de
        # seguridad" ya es "Security driver" en la hoja que el ejecutivo
        # tiene en la mano, y decirlo distinto parecen dos personas.
        cargo = ta.puesto_en(idioma, puesto)
        _notificar(db, jornada, destinatario, m.Canal.AMBOS,
                   ta.t(idioma, asunto, folio=servicio.folio),
                   ta.t(idioma, clave,
                        quien=f"{quien}{' · ' + cargo if cargo else ''}"),
                   pares=_pares_del_equipo(jornada, idioma,
                                           solo_vigentes=True))
    return True


def abrir_plazo_de_comprobacion(db: Session, jornada: m.Jornada,
                                termino: datetime) -> int:
    """Las 24 horas para comprobar empiezan cuando el dia termina.

    La regla existia entera --el numero de horas, la funcion que calcula
    la fecha, y SEIS lugares que la leen: la app del agente, el bono de
    puntualidad, la bandeja de finanzas, el panel de accesos, el dinero
    vencido de la direccion y la API-- y el campo **no lo escribia
    nadie** en el camino normal. Solo lo ponia el reemplazo por
    contingencia.

    Asi que el plazo no existia: la app no decia hasta cuando, finanzas
    no podia contar los dias vencidos, y la direccion veia en cero el
    dinero afuera sin comprobar. Lo encontro la prueba 360, por tres
    huecos distintos que resultaron ser este.

    Se respeta el que ya tenga: un reemplazo pudo haberle puesto el
    suyo, y ese cuenta desde la hora del relevo.
    """
    from app import viaticos as motor_viaticos

    cuantos = 0
    for viatico in (db.query(m.AsignacionViatico)
                    .filter_by(jornada_id=jornada.id).all()):
        if viatico.limite_comprobacion:
            continue
        viatico.limite_comprobacion = motor_viaticos.limite_de_comprobacion(
            termino)
        cuantos += 1
    return cuantos


def abrir_plazo_del_servicio(db: Session, servicio: m.Servicio,
                             termino: datetime) -> int:
    """El eventual abre el plazo una sola vez, para todos: T0 + 24 h.

    Decision de Salvador, 22 sep: las 24 horas del personal corren
    desde el termino general del servicio --el cierre del ultimo dia,
    o la cancelacion--, no desde el cierre de cada dia. En un servicio
    de tres dias los tres viaticos vencen a la misma hora.

    Se respeta el plazo que ya tenga un viatico: el del relevado, que
    corre desde su relevo (decision 1 de la propuesta). Y el dinero que
    ya cerro, se devolvio o se cancelo no recibe plazo: ya no esta
    afuera.
    """
    from app import viaticos as motor_viaticos

    limite = motor_viaticos.limite_de_comprobacion(termino)
    cuantos = 0
    for viatico in _viaticos_del_servicio(db, servicio.id):
        if viatico.limite_comprobacion or viatico.estatus in (
                m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO,
                m.EstatusViatico.CANCELADO):
            continue
        viatico.limite_comprobacion = limite
        cuantos += 1
    return cuantos


def _termino_del_implantado(db: Session, jornada: m.Jornada,
                            termino: datetime,
                            registrado: datetime | None) -> None:
    """El dia del implantado termino.

    Si es de un mes de contrato, cerrar el dia ya no abre plazo: el
    plazo es del mes y arranca con su cierre, cuando el mes queda
    completo (seccion 56). El dia sin mes de contrato --los de antes
    de que hubiera meses-- conserva sus 24 horas desde que termina.
    """
    from app import cierre_mes

    contrato = cierre_mes.contrato_de(db, jornada)
    if contrato is None:
        abrir_plazo_de_comprobacion(db, jornada, termino)
        return
    cierre_mes.terminar_si_cerro_el_mes(db, contrato, registrado=registrado)


def _viaticos_del_servicio(db: Session, servicio_id: int) -> list:
    return (db.query(m.AsignacionViatico)
            .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == servicio_id)
            .all())


def _pares_del_equipo(jornada: m.Jornada, idioma: str | None = None,
                      solo_vigentes: bool = False) -> list:
    """Quien va y en que, para la ficha del correo.

    Cada persona con su telefono al lado: el cliente que abre este aviso
    suele necesitar algo AHORA --que baje el coche, que suba por una
    maleta-- y lo que hace es llamar. Sin el numero ahi, llama a la
    central para que la central le pase el numero.

    Se traducen las claves y el puesto. El nombre, las placas y la
    direccion se quedan como se capturaron: traducir una direccion la
    vuelve inutil para quien tiene que llegar a ella.
    """
    pares = []
    for a in jornada.personal:
        # `solo_vigentes` es para el aviso de reemplazo: en un dia
        # partido la asignacion de quien salio se queda --tiene que
        # quedarse, porque ese dia lo cobra-- y sin este filtro el
        # cliente recibiria un correo de cambio con los dos nombres, el
        # que se fue y el que llega. Los demas avisos la siguen viendo
        # completa a proposito: el fin del dia cuenta quien trabajo.
        if solo_vigentes and a.relevado_en:
            continue
        rol = a.rol.nombre if getattr(a, "rol", None) else None
        puesto = ta.puesto_en(idioma, rol)
        pares.append((
            ta.t(idioma, "equipo"),
            f"{a.persona.nombre}{' · ' + puesto if puesto else ''}",
            a.persona.telefono,
        ))
    if not pares:
        pares.append((ta.t(idioma, "equipo"), ta.t(idioma, "por_asignar")))
    for a in jornada.vehiculos:
        if solo_vigentes and a.relevado_en:
            continue
        categoria = a.vehiculo.categoria.nombre if a.vehiculo.categoria else ""
        placas = ta.t(idioma, "plates")
        pares.append((ta.t(idioma, "unidad"),
                      f"{categoria} · {placas} {a.vehiculo.placa}".strip(" ·")))
    if jornada.origen_direccion:
        pares.append((ta.t(idioma, "punto"), jornada.origen_direccion))
    return pares


def _siguiente_jornada(db: Session, jornada: m.Jornada) -> m.Jornada | None:
    """El proximo dia del mismo servicio, si lo hay.

    Va por servicio y no por equipo: en el 12x36 el dia siguiente lo
    cubre la otra persona, que es otra jornada del mismo servicio. Se
    salta lo cancelado --avisar de un dia que ya se cayo manda al
    ejecutivo a esperar abajo a nadie.
    """
    return (db.query(m.Jornada)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == jornada.equipo.servicio_id,
                    m.Jornada.fecha > jornada.fecha,
                    m.Jornada.estatus != m.EstatusJornada.CANCELADA)
            .order_by(m.Jornada.fecha)
            .first())


def _cierre_del_dia(db: Session, jornada: m.Jornada, ahora: datetime,
                    idioma: str | None = None) -> tuple:
    """Cuerpo y ficha del aviso de fin de servicio.

    Son las dos preguntas que el cliente hace por telefono en cuanto se
    va el equipo: cuanto se paso del horario --porque eso se le va a
    facturar-- y a que hora y donde esta el equipo manana. Si el correo
    las trae, no hay llamada.

    Las horas extra se dicen aunque sean cero: el silencio se lee como
    "no las contaron" y provoca la misma llamada que se queria evitar.
    """
    extras = _horas_extra(jornada)
    dia = ta.dia_largo(jornada.fecha, idioma)
    cuerpo = ta.t(idioma, "fin_cuerpo", dia=dia, hora=f"{ahora:%H:%M}")
    if extras == 1:
        cuerpo += " " + ta.t(idioma, "fin_con_extra_una")
    elif extras:
        cuerpo += " " + ta.t(idioma, "fin_con_extra", horas=extras)
    else:
        cuerpo += " " + ta.t(idioma, "fin_sin_extra")

    pares = [(ta.t(idioma, "termino"), f"{ahora:%H:%M}"),
             (ta.t(idioma, "fecha"), dia),
             (ta.t(idioma, "horas_extra"),
              str(extras) if extras else ta.t(idioma, "ninguna"))]

    sigue = _siguiente_jornada(db, jornada)
    if sigue:
        # "Mañana" solo si de verdad es mañana: en un servicio con dias
        # salteados, prometer mañana es mandar a alguien a esperar.
        manana = sigue.fecha == jornada.fecha + timedelta(days=1)
        otro_dia = ta.dia_largo(sigue.fecha, idioma)
        hora = f"{sigue.inicio_programado:%H:%M}"
        pares.append((ta.t(idioma, "manana" if manana else "siguiente_dia"),
                      hora if manana else f"{otro_dia} · {hora}"))
        if sigue.origen_direccion:
            pares.append((ta.t(idioma, "punto"), sigue.origen_direccion))
        cuerpo += " " + (ta.t(idioma, "fin_manana", hora=hora) if manana
                         else ta.t(idioma, "fin_otro_dia", dia=otro_dia,
                                   hora=hora))
        cuerpo += (ta.t(idioma, "fin_en", lugar=sigue.origen_direccion)
                   if sigue.origen_direccion else ta.t(idioma, "fin_punto"))
    else:
        cuerpo += " " + ta.t(idioma, "fin_ultimo")
    return cuerpo, pares


# ---------------------------------------------------------------- hitos

def registrar_hito(db: Session, jornada_id: int, persona_id: int,
                   tipo: m.TipoHito, lat=None, lon=None,
                   marcado_en: datetime | None = None,
                   nota: str | None = None) -> dict:
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    asignacion = next((a for a in jornada.personal
                       if a.persona_id == persona_id), None)
    if asignacion is None:
        raise HTTPException(403, "Esa persona no esta asignada a la jornada")

    # Marcar con tu propio usuario dice mas que confirmar. Si no se
    # apagara aqui, la central podria ver "le falta confirmar al equipo"
    # con la persona ya parada en el punto y su llegada marcada --y en
    # un servicio de hoy para hoy eso era seguro, porque el aviso de la
    # vispera nunca le toco--. Un renglon rojo que miente ensena a
    # ignorar los renglones rojos.
    if not asignacion.confirmado:
        asignacion.confirmado = True

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

    # La hora la manda el telefono, y hasta hoy nadie la revisaba. Eso
    # abria tres puertas al mismo tiempo:
    #
    #   * la ventana de horario (candado 2) se evalua contra esta hora,
    #     asi que una marca "puntual" pasaba el candado llegara cuando
    #     llegara;
    #   * con una hora futura el atraso sale negativo, y entonces ni se
    #     marca diferida ni se manda a revisar;
    #   * en el fin de servicio esta hora fija `fin_real`, de donde
    #     salen las horas extra que se le facturan al cliente y se le
    #     pagan a la gente.
    #
    # Todo el sistema descansa en que la marca prueba la hora. Con esto
    # vuelve a ser cierto.
    #
    # No se rechaza la marca: un telefono con el reloj mal dejaria a
    # alguien parado en la calle sin poder marcar. Se usa la hora del
    # servidor, se dice lo que dijo el telefono y lo mira la central.
    # Se revisa el dia del servicio, que es cuando las marcas ocurren de
    # verdad y cuando el enganio serviria de algo: adelantar el reloj
    # para caer dentro de la ventana, o estirar el cierre para cobrar
    # horas extra. Una marca de una jornada que todavia no llega no
    # necesita este candado --la ventana de horario ya la caza-- y
    # pedirlo ahi seria pelearse con el calendario en vez de con el
    # problema.
    del_futuro = None
    if (jornada.fecha <= recibido.date()
            and (ahora - recibido).total_seconds() / 60
            > MINUTOS_FUTURO_TOLERADO):
        del_futuro = ahora
        ahora = recibido

    atraso = (recibido - ahora).total_seconds() / 60
    hito = m.Hito(jornada_id=jornada.id, persona_id=persona_id, tipo=tipo,
                  marcado_en=ahora, lat=lat, lon=lon, nota=nota,
                  recibido_en=recibido,
                  diferido=atraso > MINUTOS_PARA_DIFERIDO)
    alertas: list[str] = []

    if del_futuro is not None:
        hito.requiere_revision = True
        _alertar(db, jornada.id, m.TipoAlerta.FUERA_DE_VENTANA,
                 f"El telefono marco {tipo.value} con hora del futuro "
                 f"({del_futuro:%d/%m %H:%M}); se guardo la del servidor "
                 f"({recibido:%d/%m %H:%M}). Requiere revision.",
                 persona_id=persona_id)
        alertas.append("El reloj de tu telefono va adelantado: se guardo "
                       "la hora del servidor y la central lo va a revisar")

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
            raise HTTPException(400, {
                "mensaje": "Esta jornada no tiene punto de origen configurado",
                "que_hacer": ("Habla con tu consultor: sin el punto en el "
                              "sistema no hay contra que comparar tu "
                              "llegada."),
            })
        if lat is None or lon is None:
            raise HTTPException(400, {
                "mensaje": "Se requiere ubicacion para marcar la llegada",
                "que_hacer": ("Prende la ubicacion del telefono y vuelve a "
                              "intentar. Es lo que prueba que llegaste al "
                              "punto."),
            })

        distancia = distancia_metros(lat, lon, jornada.origen_lat, jornada.origen_lon)
        hito.distancia_origen_m = distancia
        hito.dentro_geocerca = distancia <= jornada.geocerca_metros

        if not hito.dentro_geocerca:
            _alertar(db, jornada.id, m.TipoAlerta.FUERA_DE_GEOCERCA,
                     f"Intento de marcar llegada a {distancia} m del origen "
                     f"(limite {jornada.geocerca_metros} m)",
                     persona_id=persona_id)
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
                     f"hora de presentacion. Requiere revision de la central.",
                     persona_id=persona_id)
            alertas.append("Marca fuera de la ventana de horario: la central debe revisarla")

    # ---- Secuencia obligatoria
    #
    # El fin de servicio no pedia nada: una llamada directa dejaba la
    # jornada terminada, fijaba la hora de cierre --y con ella las horas
    # extra-- y mandaba el correo de "servicio terminado" al cliente,
    # sin pasar por la geocerca ni por la ventana. El orden lo imponia
    # la pantalla, que es lo mas facil de saltarse.
    #
    # Se pide la LLEGADA y no el contacto: el ejecutivo puede no
    # aparecer --y el servicio se presto igual--, pero nadie termina un
    # dia al que nunca llego. El dia que de verdad falte la llegada, la
    # central lo cierra a mano, que para eso existe `cerrar_a_mano`.
    if tipo in (m.TipoHito.CONTACTO_EJECUTIVO, m.TipoHito.FIN_SERVICIO):
        previo = (db.query(m.Hito)
                  .filter_by(jornada_id=jornada.id, tipo=m.TipoHito.LLEGADA_ORIGEN)
                  .first())
        if not previo:
            raise HTTPException(409, {
                "mensaje": "Primero hay que marcar la llegada al punto de origen",
                "que_hacer": ("Marca tu llegada. Si ya estas en el punto y "
                              "no te deja, habla con tu consultor: el dia "
                              "se puede cerrar desde la central."),
            })

    # ---- La unidad no se suelta sin revisar
    #
    # Decision de Salvador (18 sep): candado duro. Un candado que solo
    # frenara al cerrar el servicio no salva nada --para entonces la
    # camioneta cambio de manos hace dias y las fotos de ese momento ya
    # no se pueden tomar--. El unico que sirve es el que muerde cuando la
    # unidad deja de estar en sus manos, y eso pasa aqui.
    #
    # Muerde poco a proposito:
    #   * solo en el ultimo dia de esa unidad en el servicio. Un
    #     implantado con la misma camioneta veintidos dias se revisa dos
    #     veces, no cuarenta y cuatro.
    #   * solo a quien responde por ella. El escolta que va de copiloto
    #     cierra su dia normal: si le pidieramos la revision de una
    #     unidad que no puede firmar, quedaria trabado sin salida.
    if tipo == m.TipoHito.FIN_SERVICIO:
        faltan = revision.falta_entregar(db, jornada, persona_id)
        if faltan:
            placas = ", ".join(f["placa"] or "?" for f in faltan)
            # Sin la recepcion no se puede guardar la entrega --no hay
            # contra que comparar-- asi que ese caso no lo resuelve solo
            # y el mensaje tiene que mandarlo con su consultor en vez de
            # dejarlo dando vueltas en la app.
            atorado = any(f["sin_recepcion"] for f in faltan)
            raise HTTPException(409, {
                "mensaje": (f"Antes de cerrar hay que revisar la unidad: "
                            f"{placas}."),
                "que_hacer": ("Habla con tu consultor: esa unidad nunca se "
                              "reviso al recibirla, y sin eso no hay contra "
                              "que comparar la entrega."
                              if atorado else
                              "Toma las cinco fotos de la entrega. Es el "
                              "ultimo momento en que se puede probar como "
                              "la devolviste; manana ya no."),
                # La pantalla necesita a donde mandarlo, no solo que
                # le falta: el aviso y el boton son la misma cosa.
                "servicio_id": jornada.equipo.servicio_id,
                "unidades": faltan,
            })

    db.add(hito)

    # ---- efectos de cada hito
    servicio = jornada.equipo.servicio

    if tipo == m.TipoHito.LLEGADA_ORIGEN:
        # Llego al punto: arribado, no en curso. Llegar y esperar veinte
        # minutos a que el ejecutivo baje no es tener el servicio
        # corriendo, y la central necesita ver ese rato --que es el
        # ultimo en que todavia se puede hacer algo--.
        #
        # No se le baja el estatus a un dia que ya arranco de verdad: si
        # alguien marca su llegada despues del contacto (dos personas
        # del mismo equipo marcando en desorden), el dia se queda en
        # curso.
        if jornada.estatus != m.EstatusJornada.EN_CURSO:
            jornada.estatus = m.EstatusJornada.ARRIBADO
        # Y el servicio con el, para que la cartera diga que el equipo ya
        # esta alla. Solo hacia adelante: un servicio que ya arranco de
        # verdad no regresa porque alguien mas marque su llegada.
        if servicio.estatus in m.ANTES_DE_ARRANCAR:
            servicio.estatus = m.EstatusServicio.ARRIBADO
        # Se importa aqui adentro: trayecto usa `distancia_metros` de
        # este archivo, y arriba seria un circulo.
        from app import trayecto
        trayecto.cerrar(db, jornada.id, persona_id, cuando=ahora)
        # Cada uno en su idioma: el principal suele ser extranjero y
        # quien pidio el servicio suele ser del pais. Son dos correos
        # distintos, no el mismo mandado dos veces.
        del_principal = ta.idioma_de(db, servicio, m.Destinatario.EJECUTIVO)
        del_solicitante = ta.idioma_de(db, servicio,
                                       m.Destinatario.SOLICITANTE)
        _notificar(db, jornada, m.Destinatario.EJECUTIVO, m.Canal.AMBOS,
                   ta.t(del_principal, "punto_asunto_principal"),
                   ta.t(del_principal, "punto_cuerpo"),
                   pares=_pares_del_equipo(jornada, del_principal))
        _notificar(db, jornada, m.Destinatario.SOLICITANTE, m.Canal.AMBOS,
                   ta.t(del_solicitante, "punto_asunto_solicitante",
                        folio=servicio.folio),
                   ta.t(del_solicitante, "punto_cuerpo"),
                   pares=_pares_del_equipo(jornada, del_solicitante)
                   + [(ta.t(del_solicitante, "presentacion"),
                       f"{jornada.inicio_programado:%H:%M}")])

    elif tipo == m.TipoHito.CONTACTO_EJECUTIVO:
        jornada.inicio_real = ahora
        # El contacto con el principal es el que arranca el dia. Antes lo
        # encendia la llegada, y este renglon no existia aqui --solo en
        # el registro a mano de la central, que ya pensaba asi--.
        if jornada.estatus != m.EstatusJornada.TERMINADA:
            jornada.estatus = m.EstatusJornada.EN_CURSO

        # El servicio arranca de verdad con el meet and greet: hasta ese
        # momento esta programado —armado, con gente y unidad— y no
        # corriendo. El estatus tiene que decir en que va, no repetir
        # que ya se planeo.
        #
        # Esto valia solo para el implantado y el eventual se quedaba en
        # `asignado` hasta que finanzas aprobaba el cierre: saltaba de
        # "esperando el dia" a "cerrado" sin pasar por "corriendo". En
        # la cartera del consultor, un servicio con el equipo ya con el
        # principal se veia igual que uno que todavia no sale.
        #
        # Es el mismo renglon para los dos tipos a proposito: quien
        # cambie lo que significa "en curso" lo cambia una vez, y no se
        # puede quedar a medias en una de las dos carteras.
        if servicio.estatus in (*m.ANTES_DE_ARRANCAR,
                                m.EstatusServicio.ARRIBADO):
            servicio.estatus = m.EstatusServicio.EN_CURSO
        # Solo el aviso de que ya hubo contacto, sin enlace de
        # seguimiento en vivo: no se desarrolla por ahora (decision de
        # Salvador, 23 sep).
        del_principal = ta.idioma_de(db, servicio, m.Destinatario.EJECUTIVO)
        del_solicitante = ta.idioma_de(db, servicio,
                                       m.Destinatario.SOLICITANTE)
        _notificar(db, jornada, m.Destinatario.SOLICITANTE, m.Canal.AMBOS,
                   ta.t(del_solicitante, "inicio_asunto_solicitante",
                        folio=servicio.folio),
                   ta.t(del_solicitante, "inicio_cuerpo_solicitante",
                        hora=f"{ahora:%H:%M}"),
                   pares=_pares_del_equipo(jornada, del_solicitante))
        _notificar(db, jornada, m.Destinatario.EJECUTIVO, m.Canal.AMBOS,
                   ta.t(del_principal, "inicio_asunto_principal"),
                   ta.t(del_principal, "inicio_cuerpo_principal",
                        hora=f"{ahora:%H:%M}"),
                   pares=_pares_del_equipo(jornada, del_principal))

    elif tipo == m.TipoHito.FIN_SERVICIO:
        jornada.fin_real = ahora
        jornada.estatus = m.EstatusJornada.TERMINADA
        # El dia termino. En el eventual el plazo es uno solo para todo
        # el servicio y arranca con el termino general, abajo, al
        # cerrar el ultimo dia (decision de Salvador, 22 sep). En el
        # implantado es uno por mes y arranca con el cierre del mes
        # (seccion 56).
        if servicio.tipo != m.TipoServicio.EVENTUAL:
            _termino_del_implantado(db, jornada, ahora, recibido)
        terminar_si_cerro_el_ultimo_dia(db, servicio, termino=ahora,
                                        registrado=recibido)
        del_solicitante = ta.idioma_de(db, servicio,
                                       m.Destinatario.SOLICITANTE)
        cuerpo, pares = _cierre_del_dia(db, jornada, ahora, del_solicitante)
        _notificar(db, jornada, m.Destinatario.SOLICITANTE, m.Canal.CORREO,
                   ta.t(del_solicitante, "fin_asunto", folio=servicio.folio),
                   cuerpo, pares=pares)

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
        # Al cerrar el dia, si el equipo tiene otro por delante: es el
        # momento en que el principal acaba de decir a que hora se ven
        # manana, y quien lo escucho tiene el telefono en la mano.
        # Mientras nadie lo capture, ese dia vive con la hora heredada
        # del primero, que no es un dato.
        "manana": _manana_del_equipo(jornada) if tipo == m.TipoHito.FIN_SERVICIO
                  else None,
    }


def _manana_del_equipo(jornada: m.Jornada) -> dict | None:
    siguiente = siguiente_dia(jornada)
    if not siguiente or siguiente.hora_confirmada:
        return None
    return {"jornada_id": jornada.id,
            "fecha": siguiente.fecha.isoformat(),
            "heredada": siguiente.inicio_programado.isoformat()}


def siguiente_dia(jornada: m.Jornada) -> m.Jornada | None:
    """El dia que sigue, DEL MISMO EQUIPO.

    Un servicio puede tener a Alfa en Ciudad de Mexico y a Beta en
    Monterrey: lo que dijo el principal de Alfa no mueve la hora de
    Beta.
    """
    return min((j for j in jornada.equipo.jornadas
                if j.fecha > jornada.fecha
                and j.estatus != m.EstatusJornada.CANCELADA),
               key=lambda j: j.fecha, default=None)


def fijar_hora_de_manana(db: Session, jornada: m.Jornada, hora,
                         quien_id: int | None, nota: str | None = None,
                         direccion: str | None = None,
                         lat=None, lon=None) -> dict:
    """A que hora --y donde-- se presenta el equipo el dia siguiente.

    Lo dice el principal al cerrar el dia, casi siempre en la puerta del
    hotel y casi siempre a deshoras. Hasta que alguien lo captura, el
    dia siguiente vive con la hora HEREDADA del primero, que sirve para
    calcular y no es un dato: la app lo dice asi y no la muestra como si
    alguien la hubiera confirmado.

    El punto entra aqui con su lat/lon porque el que lo captura esta
    parado en el: sin coordenadas no hay geocerca, y sin geocerca ese
    equipo no puede marcar su llegada manana. Una direccion escrita sin
    pin deja el dia a medias.
    """
    siguiente = siguiente_dia(jornada)
    if not siguiente:
        raise HTTPException(409, {
            "mensaje": "Este equipo no tiene otro dia despues de este",
            "que_hacer": "Si el cliente quiere otro dia, se agrega al "
                         "servicio desde su pantalla."})

    antes = siguiente.inicio_programado
    modalidad = db.get(m.Modalidad, siguiente.modalidad_id)
    siguiente.inicio_programado = datetime.combine(siguiente.fecha, hora)
    siguiente.fin_programado = (siguiente.inicio_programado
                                + timedelta(hours=float(modalidad.horas)))
    siguiente.hora_confirmada = True

    if direccion:
        siguiente.origen_direccion = direccion.strip()
    if lat is not None and lon is not None:
        siguiente.origen_lat = lat
        siguiente.origen_lon = lon
        if not siguiente.geocerca_metros:
            from app import geocercas
            siguiente.geocerca_metros = geocercas.radio_de(
                siguiente.origen_aeropuerto)

    # Queda en la bitacora del dia en que se supo --hoy-- y no en la del
    # dia que se movio: lo que se esta registrando es que el principal
    # lo dijo esta noche.
    texto = f"Mañana {siguiente.fecha:%d/%m} se arranca a las {hora:%H:%M}"
    if direccion:
        texto += f", en {direccion.strip()}"
    if nota:
        texto += f". {nota.strip()}"
    db.add(m.NotaBitacora(jornada_id=jornada.id, persona_id=quien_id,
                          texto=texto))
    db.flush()
    return {"siguiente": siguiente, "antes": antes}


def ajustar_hito(db: Session, hito_id: int, nuevo_momento: datetime,
                 ajustado_por_id: int, justificacion: str) -> dict:
    """La central puede ajustar el corte de tiempo, con justificacion obligatoria."""
    if not justificacion or len(justificacion.strip()) < 10:
        raise HTTPException(400, "La justificacion del ajuste es obligatoria")

    hito = db.get(m.Hito, hito_id)
    if not hito:
        raise HTTPException(404, f"No existe el hito {hito_id}")

    # La ORIGINAL es la primera, no la anterior.
    #
    # Esto se sobrescribia en cada ajuste, asi que a la segunda
    # correccion el campo dejaba de decir lo que dice su nombre: guardaba
    # la penultima hora y la de verdad original se perdia sin dejar
    # rastro. Encontrado en la calle el 20 de septiembre, en una jornada
    # corregida dos veces: el campo juraba que habia empezado a las 20:30
    # y la hora que de verdad se registro habia sido las 23:09.
    #
    # De este dato salen las horas extra que se le facturan al cliente y
    # se le pagan a la gente. Que quede a la vista PARA SIEMPRE no es un
    # adorno de auditoria; es la unica forma de reconstruir un cobro que
    # alguien discuta meses despues. Cada correccion intermedia queda en
    # el registro de acciones, con su justificacion y su firma, y la
    # bitacora del dia las enseña en orden.
    if hito.marcado_original is None:
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

    # Esta funcion NO escribe. Antes marcaba las jornadas como
    # PROXIMA_A_INICIAR y hacia commit, y como es un GET, el estado de
    # una jornada dependia de que alguien abriera una pantalla. Eso
    # vive ahora en `marcar_proximas_a_iniciar`, que corre con el reloj.
    return sorted(tablero, key=lambda x: x["inicia_en_minutos"])


def marcar_proximas_a_iniciar(db: Session,
                              ahora: datetime | None = None) -> dict:
    """Pasa a PROXIMA_A_INICIAR lo que arranca dentro de la ventana.

    Lo mueve el reloj y no una pantalla. Leer no cambia datos: mientras
    esto vivio dentro del GET del tablero, que una jornada cambiara de
    estado dependia de que alguien lo abriera, y eso no se puede
    reproducir a mano el dia que algo se ve raro.
    """
    relojes = reloj.Relojes(db, ahora)
    margen = reloj.margen_de_paises(db)
    ahora = ahora or datetime.now()
    limite = ahora + timedelta(hours=VENTANA_PROXIMOS_HORAS)

    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.inicio_programado >= ahora - margen,
                        m.Jornada.inicio_programado <= limite + margen,
                        m.Jornada.estatus.in_([m.EstatusJornada.PLANEADA,
                                               m.EstatusJornada.CONFIRMADA]))
                .all())

    marcadas = 0
    for j in jornadas:
        suyo = relojes.de_la_jornada(j)
        if not (suyo <= j.inicio_programado
                <= suyo + timedelta(hours=VENTANA_PROXIMOS_HORAS)):
            continue
        j.estatus = m.EstatusJornada.PROXIMA_A_INICIAR
        marcadas += 1
    db.commit()
    return {"marcadas": marcadas}


def dia_abandonado(jornada: m.Jornada, ultimo_movimiento: datetime,
                   ahora: datetime) -> bool:
    """Un dia que arranco, nadie cerro, y nadie ha tocado en horas.

    Hacen falta las DOS cosas --paso su fin hace mas de las horas de
    gracia Y lleva horas sin movimiento-- porque cualquiera de las dos
    sola se lleva por delante un caso legitimo: un servicio en horas
    extra tambien paso su fin programado, y ese si esta corriendo. Se
    distingue por el movimiento: el que sigue trabajando sigue marcando.

    Las horas son las mismas de `dias_sin_cerrar`, a proposito: declarar
    abandonado un dia antes de que esa pantalla lo recoja lo dejaria sin
    aparecer en ninguna de las dos.
    """
    if not jornada.fin_programado:
        return False
    gracia = timedelta(hours=HORAS_DE_GRACIA)
    if ahora - jornada.fin_programado <= gracia:
        return False
    return ahora - (ultimo_movimiento or jornada.inicio_programado) > gracia


def revisar_standby(db: Session, ahora: datetime | None = None) -> list[dict]:
    """Si el conductor no reporta en el intervalo, la central recibe alerta."""
    # El silencio de un servicio se mide contra la hora del pais donde
    # esta: con el reloj del servidor, todo servicio brasileño aparentaba
    # tres horas de silencio desde que arrancaba y se le levantaba
    # alerta falsa de inmediato.
    relojes = reloj.Relojes(db, ahora)

    # El que llego y espera al principal tambien cuenta: es exactamente
    # el rato en que nadie sabe nada de el.
    en_curso = (db.query(m.Jornada)
                .filter(m.Jornada.estatus.in_(m.ARRANCADAS)).all())

    generadas = []
    for j in en_curso:
        suyo = relojes.de_la_jornada(j)
        limite = suyo - timedelta(hours=INTERVALO_STANDBY_HORAS)
        ultimo = (db.query(m.Hito)
                  .filter_by(jornada_id=j.id)
                  .order_by(m.Hito.marcado_en.desc())
                  .first())
        referencia = ultimo.marcado_en if ultimo else j.inicio_programado
        # Un dia de hace tres semanas que nadie cerro sigue EN_CURSO, y
        # sin esto se le revisa cada quince minutos para volver a
        # concluir que lleva tres semanas callado. Ese dia no necesita
        # una alerta: necesita que alguien lo firme, y para eso esta
        # "Dias sin cerrar".
        if dia_abandonado(j, referencia, suyo):
            continue
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
                .filter(m.Jornada.estatus.in_(m.ARRANCADAS),
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
        servicio = j.equipo.servicio
        for destinatario in (m.Destinatario.SOLICITANTE,
                             m.Destinatario.EJECUTIVO):
            lengua = ta.idioma_de(db, servicio, destinatario)
            horas = f"{j.modalidad.horas}"
            _notificar(
                db, j, destinatario, m.Canal.AMBOS,
                ta.t(lengua, "extra_asunto", minutos=minutos),
                ta.t(lengua, "extra_cuerpo", horas=horas,
                     hora=f"{j.fin_programado:%H:%M}"),
                pares=[(ta.t(lengua, "cierre_programado"),
                        f"{j.fin_programado:%H:%M}"),
                       (ta.t(lengua, "contratado"),
                        f"{horas} {ta.t(lengua, 'horas')}")])
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


def terminar_si_cerro_el_ultimo_dia(db: Session, servicio: m.Servicio,
                                    termino: datetime | None = None,
                                    registrado: datetime | None = None,
                                    ) -> bool:
    """El eventual se apaga cuando ya no le queda dia por trabajar.

    `terminado` existia en el catalogo y no lo escribia nadie: el
    eventual saltaba de `asignado` --o de `en_curso`, desde hoy-- a
    `cerrado`, que es lo que pone finanzas al aprobar. O sea que entre
    "el servicio se cumplio" y "el expediente esta cerrado" no habia
    ningun estado, y son dos cosas distintas: una la sabe la operacion
    el mismo dia, la otra tarda lo que tarde el papeleo.

    **Solo el eventual.** El implantado es continuo: sus jornadas se
    generan mes con mes, asi que cerrar la ultima del mes de octubre no
    quiere decir que el servicio termino --quiere decir que falta
    generar noviembre--. Apagarlo ahi seria apagar un servicio con gente
    en la calle.

    Un dia cancelado no cuenta como pendiente: no se va a trabajar.
    """
    if servicio.tipo != m.TipoServicio.EVENTUAL:
        return False
    if servicio.estatus not in (*m.ANTES_DE_ARRANCAR,
                                m.EstatusServicio.ARRIBADO,
                                m.EstatusServicio.EN_CURSO):
        return False

    # ESTE `flush` ES EL CORAZON DE LA FUNCION, no una precaucion.
    #
    # La sesion de este proyecto corre con `autoflush=False` (ver
    # `db.py`). A quien llama a esto lo acaban de mover: puso el dia en
    # TERMINADA y todavia no ha hecho commit. Sin el flush, la consulta
    # de abajo le pregunta a la base --que aun no se entera-- y el dia
    # que se esta cerrando cuenta como pendiente. O sea que el ULTIMO
    # dia, que es el unico que puede encender `terminado`, era
    # precisamente el que nunca lo encendia.
    #
    # Sintoma en la calle: se cierra el ultimo dia y el servicio se
    # queda en curso, sin error y sin nada raro en el log.
    db.flush()

    pendientes = (db.query(m.Jornada)
                  .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                  .filter(m.Equipo.servicio_id == servicio.id,
                          m.Jornada.estatus.notin_(
                              [m.EstatusJornada.TERMINADA,
                               m.EstatusJornada.CANCELADA]))
                  .count())
    if pendientes:
        return False

    # Un servicio cuyos dias se cancelaron todos no se "termino": no se
    # trabajo. Ese camino es el de cancelar el servicio, no este.
    trabajados = (db.query(m.Jornada)
                  .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                  .filter(m.Equipo.servicio_id == servicio.id,
                          m.Jornada.estatus == m.EstatusJornada.TERMINADA)
                  .count())
    if not trabajados:
        return False

    servicio.estatus = m.EstatusServicio.TERMINADO

    # T0, el termino general: la hora real de termino del ultimo dia.
    # Si el dia se firmo tarde --la central lo cerro a mano tres dias
    # despues, o la marca llego con retraso--, T0 es la firma: un plazo
    # que nace vencido no es un plazo (decision 4 de la propuesta).
    momentos = [x for x in (termino, registrado) if x]
    t0 = max(momentos) if momentos else reloj.ahora_del_servicio(db, servicio)

    # Y arrancan solos los dos relojes: las 24 horas del personal para
    # comprobar --todos los viaticos del servicio con el mismo limite,
    # T0 + 24 h-- y, cuando vencen o todo el dinero ya cerro, las 24
    # horas del consultor (`cierre.avanzar`, cada cinco minutos).
    #
    # Se abria a mano, con un boton que alguien tenia que acordarse de
    # tocar. Si nadie lo tocaba, el plazo de 24 horas no empezaba nunca
    # --y de ese plazo depende que el consultor cobre su comision--, asi
    # que la regla existia sin correr. Un plazo que arranca cuando
    # alguien se acuerda no es un plazo.
    #
    # Las encuestas salen aqui por lo mismo: vivian en el mismo boton, y
    # el momento de preguntarle al ejecutivo es ahora, mientras tiene el
    # servicio fresco. `generar` no manda dos veces la misma.
    from app import cierre as motor_cierre
    from app import encuestas as motor_encuestas

    abrir_plazo_del_servicio(db, servicio, t0)
    motor_cierre.abrir(db, servicio.id, abierto_en=t0)
    try:
        motor_encuestas.generar(db, servicio.id)
    except Exception:                     # noqa: BLE001
        # Una encuesta que no sale no puede dejar el servicio sin
        # terminar: el dia ya se trabajo y ya se cerro.
        registro.exception("no se pudieron generar las encuestas de %s",
                           servicio.folio)
    return True


# ------------------------------------ el meet and greet puesto a mano

# Los puntos criticos del dia que la central puede asentar cuando la app
# no los tomo. El fin de servicio NO esta aqui a proposito: ese camino ya
# existe --`cerrar_a_mano`-- y hace mas cosas que poner un hito (fija el
# fin real, cierra la jornada y abre el plazo de comprobacion). Dos
# puertas para la misma escritura son dos lugares donde mantener las
# mismas reglas, y el dia que una cambie se quedan diciendo cosas
# distintas.
A_MANO = (m.TipoHito.LLEGADA_ORIGEN, m.TipoHito.CONTACTO_EJECUTIVO)


def registrar_hito_a_mano(db: Session, jornada_id: int,
                          persona_id: int, quien_id: int,
                          tipo: m.TipoHito,
                          momento: datetime,
                          justificacion: str,
                          ahora: datetime | None = None) -> dict:
    """La central asienta un punto critico que nadie marco desde la app.

    No es un ajuste. Ajustar corrige la hora de una marca que existe;
    esto crea una que nunca se hizo, porque el telefono se quedo sin
    bateria, sin senal, o simplemente porque a alguien se le paso y el
    cliente ya confirmo por telefono que el equipo esta con el.

    Se queda sellado con quien lo firmo y por que, y ese sello no se
    borra: de `inicio_real` salen las horas que se le facturan al
    cliente, y un dia que alguien firmo desde una oficina no se puede
    confundir con uno que alguien marco parado en la calle.

    Lo que NO hace: no inventa ubicacion. Un hito a mano no trae `lat`
    ni `lon` ni geocerca --nadie estaba ahi con el telefono-- y por eso
    no puede colarse como prueba de que alguien llego al punto.
    """
    if tipo not in A_MANO:
        raise HTTPException(409, {
            "mensaje": f"'{tipo.value}' no se registra a mano",
            "que_hacer": "El fin del dia se asienta con 'cerrar el dia a "
                         "mano', que ademas cierra la jornada y abre el "
                         "plazo para comprobar."})

    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    ahora = reloj.ahora_de_la_jornada(db, jornada, ahora)

    if jornada.estatus == m.EstatusJornada.CANCELADA:
        raise HTTPException(409, {
            "mensaje": "Ese dia esta cancelado",
            "que_hacer": "Un dia cancelado no tiene marcas: no se trabajo."})

    ya = (db.query(m.Hito)
          .filter_by(jornada_id=jornada_id, tipo=tipo).first())
    if ya:
        raise HTTPException(409, {
            "mensaje": "Ese dia ya tiene esa marca",
            "que_hacer": (f"Quedo marcada a las {ya.marcado_en:%H:%M}. Si la "
                          "hora esta mal, se corrige la marca; no se "
                          "registra otra.")})

    # La llegada al punto va antes que el contacto, tambien cuando la
    # pone la central: un contacto con el ejecutivo sin haber llegado
    # cuenta una historia que no ocurrio, y la app no lo permitiria.
    if tipo == m.TipoHito.CONTACTO_EJECUTIVO:
        llego = (db.query(m.Hito)
                 .filter_by(jornada_id=jornada_id,
                            tipo=m.TipoHito.LLEGADA_ORIGEN).first())
        if not llego:
            raise HTTPException(409, {
                "mensaje": "Ese dia no tiene llegada al punto",
                "que_hacer": "Primero se asienta la llegada al punto y "
                             "despues el contacto con el ejecutivo, en ese "
                             "orden."})

    asignada = next((a for a in jornada.personal
                     if a.persona_id == persona_id and not a.relevado_en), None)
    if not asignada:
        raise HTTPException(409, {
            "mensaje": "Esa persona no esta asignada a ese dia",
            "que_hacer": "El meet and greet se le acredita a quien iba, y "
                         "tiene que estar en la jornada."})

    # Una hora que todavia no llega es una hora inventada.
    if momento > ahora:
        raise HTTPException(409, {
            "mensaje": "Esa hora todavia no llega",
            "que_hacer": "El meet and greet se registra despues de que paso, "
                         "no antes."})

    if momento < jornada.inicio_programado - timedelta(hours=HORAS_ANTES_DEL_INICIO):
        raise HTTPException(409, {
            "mensaje": "Esa hora queda demasiado antes del servicio",
            "que_hacer": (f"El dia empieza a las "
                          f"{jornada.inicio_programado:%H:%M}. Una marca "
                          f"mas de {HORAS_ANTES_DEL_INICIO} horas antes no es "
                          "de este servicio.")})

    hito = m.Hito(jornada_id=jornada_id, persona_id=persona_id,
                  tipo=tipo, marcado_en=momento,
                  recibido_en=ahora,
                  registrado_a_mano_por_id=quien_id,
                  registrado_a_mano_en=ahora,
                  motivo_a_mano=justificacion.strip())
    db.add(hito)

    servicio = jornada.equipo.servicio

    # La llegada registrada a mano mueve lo mismo que la de la app: si
    # no, un dia asentado por la central se quedaria en "asignado" con
    # el equipo parado en el punto.
    if tipo == m.TipoHito.LLEGADA_ORIGEN:
        if jornada.estatus != m.EstatusJornada.EN_CURSO:
            jornada.estatus = m.EstatusJornada.ARRIBADO
        if servicio.estatus in m.ANTES_DE_ARRANCAR:
            servicio.estatus = m.EstatusServicio.ARRIBADO

    # El contacto con el ejecutivo es el que arranca el servicio. La
    # llegada al punto no: llegar y esperar veinte minutos a que el
    # ejecutivo baje no es tener el servicio corriendo.
    if tipo == m.TipoHito.CONTACTO_EJECUTIVO:
        jornada.inicio_real = momento
        if jornada.estatus in (m.EstatusJornada.PLANEADA,
                               m.EstatusJornada.CONFIRMADA,
                               m.EstatusJornada.PROXIMA_A_INICIAR,
                               m.EstatusJornada.ARRIBADO):
            jornada.estatus = m.EstatusJornada.EN_CURSO
        if servicio.estatus in (*m.ANTES_DE_ARRANCAR,
                                m.EstatusServicio.ARRIBADO):
            servicio.estatus = m.EstatusServicio.EN_CURSO

    # El camino al punto se apaga: ya llego, aunque la marca no sea suya.
    from app import trayecto
    trayecto.cerrar(db, jornada_id, persona_id, cuando=momento, a_mano=True)

    db.flush()
    return {"resultado": "marca registrada a mano",
            "tipo": tipo.value,
            "hito_id": hito.id,
            "jornada_id": jornada.id,
            "marcado_en": momento.isoformat(),
            "persona": asignada.persona.nombre if asignada.persona else None,
            "estatus_servicio": servicio.estatus.value,
            "estatus_jornada": jornada.estatus.value}


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
    # Cerrado a mano o marcado desde la calle, el dia termino igual y el
    # plazo corre igual: la diferencia queda en el sello del cierre, no
    # en el reloj de la comprobacion.
    if jornada.equipo.servicio.tipo != m.TipoServicio.EVENTUAL:
        _termino_del_implantado(db, jornada, fin, ahora)
    jornada.cerrada_a_mano_por_id = quien_id
    jornada.cerrada_a_mano_en = ahora
    jornada.cierre_motivo = justificacion.strip()
    # En el eventual, un dia firmado tarde no nace vencido: el plazo
    # corre desde la firma, no desde la hora de termino que asento la
    # central (decision 4 de la propuesta).
    terminar_si_cerro_el_ultimo_dia(db, jornada.equipo.servicio,
                                    termino=fin, registrado=ahora)
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
    cerrado_por_el_equipo = not jornada.cerrada_a_mano_en
    if cerrado_por_el_equipo and jornada.estatus != m.EstatusJornada.TERMINADA:
        raise HTTPException(409, {
            "mensaje": "Ese dia no esta cerrado",
            "que_hacer": "No hay nada que reabrir."})

    # Si ya se pago, reabrir no devuelve el dinero: lo que cambie se
    # arrastra como ajuste al siguiente corte. Decirlo aqui evita que
    # alguien crea que esto revierte un pago.
    pagado = (db.query(m.ConceptoNomina)
              .filter_by(jornada_id=jornada.id).first() is not None)

    # El eventual ya terminado: reabrir un dia deshace el termino
    # general. Si el cierre sigue en comprobacion o sin visto bueno, se
    # borra con sus plazos y el servicio vuelve a la calle; al cerrar el
    # dia otra vez nace un T0 nuevo. Con el visto bueno dado ya no: la
    # factura salio, o esta por salir, con esas horas.
    servicio = jornada.equipo.servicio
    if servicio.tipo == m.TipoServicio.EVENTUAL:
        if servicio.estatus == m.EstatusServicio.CANCELADO:
            raise HTTPException(409, {
                "mensaje": "El servicio esta cancelado: no se reabre un dia",
                "que_hacer": "Lo que haya que corregir de ese dia se "
                             "resuelve en la revision de la cancelacion."})
        cierre = (db.query(m.Cierre)
                  .filter_by(servicio_id=servicio.id).first())
        if cierre and (cierre.facturado_en or cierre.estatus in (
                m.EstatusCierre.EN_REVISION_IA,
                m.EstatusCierre.ENVIADO_FINANZAS,
                m.EstatusCierre.APROBADO, m.EstatusCierre.FACTURADO)):
            raise HTTPException(409, {
                "mensaje": "El servicio ya tiene visto bueno: no se puede reabrir",
                "que_hacer": "Lo que cambie de este dia se corrige con "
                             "finanzas, no reabriendo el dia."})
        if cierre:
            for viatico in _viaticos_del_servicio(db, servicio.id):
                if viatico.limite_comprobacion == cierre.comprobacion_hasta:
                    viatico.limite_comprobacion = None
            db.delete(cierre)
            db.flush()
        if servicio.estatus in (m.EstatusServicio.TERMINADO,
                                m.EstatusServicio.SIN_VISTO_BUENO):
            # En curso si otro dia ya se trabajo o esta en la calle;
            # si no, vuelve a esperar su dia, con el estatus que le
            # toque por sus recursos.
            otros = [j for e in servicio.equipos for j in e.jornadas
                     if j.id != jornada.id and j.estatus in (
                         m.EstatusJornada.TERMINADA,
                         m.EstatusJornada.EN_CURSO,
                         m.EstatusJornada.ARRIBADO)]
            if otros:
                servicio.estatus = m.EstatusServicio.EN_CURSO
            else:
                from app import programacion
                servicio.estatus = m.EstatusServicio.PLANEADO
                programacion.evaluar(servicio)
    else:
        # El implantado cierra por mes (seccion 56): reabrir un dia de
        # un mes en comprobacion o sin visto bueno deshace el termino de
        # ese mes; con el visto bueno dado ya no se reabre.
        from app import cierre_mes
        cierre_mes.deshacer_termino(db, cierre_mes.contrato_de(db, jornada),
                                    "no se puede reabrir un dia")

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

    # El dia que lo cerro el EQUIPO desde la calle tiene una marca de
    # fin con su hora, su ubicacion y quien la hizo. Reabrir sin tocarla
    # dejaria un dia abierto con su fin ya marcado: la app no volveria a
    # ofrecer el boton --ese paso ya esta hecho-- y el equipo se quedaria
    # sin poder cerrar otra vez.
    #
    # Asi que la marca se anula, pero NO se borra: se queda con su
    # justificacion y con el nombre de quien la anulo. Una marca real
    # que desaparece sin rastro es justo lo que este sistema no hace;
    # dentro de seis meses alguien va a querer saber por que ese dia se
    # cerro dos veces. Decision de Salvador, 20 sep.
    anulada = None
    if cerrado_por_el_equipo:
        anulada = (db.query(m.Hito)
                   .filter_by(jornada_id=jornada.id,
                              tipo=m.TipoHito.FIN_SERVICIO,
                              anulado_en=None)
                   .order_by(m.Hito.marcado_en.desc()).first())
        if anulada:
            anulada.anulado_en = reloj.ahora_de_la_jornada(db, jornada)
            anulada.anulado_por_id = quien_id
            anulada.motivo_anulacion = justificacion.strip()
    db.commit()

    return {"resultado": "dia reabierto", "jornada_id": jornada.id,
            "ya_estaba_pagado": pagado,
            "marca_anulada": bool(anulada),
            "nota": ("Ese dia ya se pago; la diferencia se arrastra como "
                     "ajuste al siguiente corte."
                     if pagado else
                     "El dia vuelve a quedar abierto.")}

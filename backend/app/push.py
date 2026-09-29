"""Avisos al telefono del equipo de campo.

Los entrega el propio navegador: sin terceros, sin costo por mensaje y
sin tramite. A cambio tiene dos limites que hay que conocer y no
esconder:

  - en iPhone solo funciona desde iOS 16.4 y solo si el agente agrego la
    app a su pantalla de inicio
  - si el telefono esta apagado, el aviso espera; si pasa mucho, se
    pierde

Por eso esto sirve para recordar —confirma manana, se te vence un
curso— y no para lo que no puede fallar. Lo que no puede fallar se
habla por telefono, y por eso la app trae el numero de la central a un
toque.

El envio nunca detiene lo que lo llamo: si un aviso no sale, el corte de
nomina o la asignacion siguen su camino igual.
"""
import json
from datetime import timedelta
import logging

from sqlalchemy.orm import Session

from app import models as m
from app.config import settings

registro = logging.getLogger("centauro.push")


def hay_llaves() -> bool:
    return bool(settings.vapid_private and settings.vapid_public)


def suscripciones(db: Session, persona_id: int) -> list[m.SuscripcionPush]:
    return (db.query(m.SuscripcionPush)
            .filter_by(persona_id=persona_id, activa=True).all())


# Cuanto guarda el servicio de avisos un mensaje para un telefono que
# esta apagado o sin senal. Estaba en una hora: el recordatorio de las
# cinco de la tarde se perdia si el telefono pasaba la noche guardado,
# que es justo el caso que el recordatorio existe para cubrir.
HORAS_DE_ESPERA = 12
HORAS_DE_ESPERA_VISPERA = 16      # de las 17:00 hasta bien entrada la manana


def avisar(db: Session, persona_id: int, titulo: str, cuerpo: str,
           url: str = "/app/", etiqueta: str | None = None,
           horas: int = HORAS_DE_ESPERA, urgente: bool = False,
           accion: str | None = None) -> dict:
    """Manda un aviso a todos los telefonos de esa persona.

    `etiqueta` hace que un aviso reemplace al anterior del mismo tipo en
    vez de apilarse: tres recordatorios iguales en la pantalla de
    bloqueo se leen como una falla de la app, no como insistencia.

    `horas` es cuanto lo guarda el servicio de avisos si el telefono
    esta apagado. `urgente` lo entrega de inmediato aunque el telefono
    este ahorrando bateria: un relevo de hoy para hoy no puede esperar a
    que alguien mueva el telefono.

    `accion` pinta un boton en la propia notificacion --"Confirmo que
    voy"--, para no tener que abrir la app y buscar el servicio a las
    seis de la manana.
    """
    if not hay_llaves():
        return {"enviados": 0, "motivo": "sin llaves configuradas"}

    filas = suscripciones(db, persona_id)
    if not filas:
        return {"enviados": 0, "motivo": "sin telefonos suscritos"}

    from pywebpush import WebPushException, webpush

    # Los botones de la notificacion, en el idioma de quien la recibe:
    # el trabajador de fondo no tiene diccionario (seccion 99).
    lengua = idioma_de(db, persona_id)
    carga = json.dumps({"titulo": titulo, "cuerpo": cuerpo, "url": url,
                        "etiqueta": etiqueta or "centauro",
                        "accion": accion,
                        "botones": {"confirmar": tx(lengua, "accion_confirmar"),
                                    "en_camino": tx(lengua, "accion_en_camino"),
                                    "abrir": tx(lengua, "accion_abrir")}})
    enviados, apagadas = 0, 0

    for fila in filas:
        try:
            webpush(
                subscription_info={
                    "endpoint": fila.endpoint,
                    "keys": {"p256dh": fila.p256dh, "auth": fila.auth},
                },
                data=carga,
                vapid_private_key=settings.vapid_private,
                vapid_claims={"sub": settings.vapid_contacto},
                ttl=horas * 3600,
                headers={"Urgency": "high" if urgente else "normal"},
            )
            enviados += 1
        except WebPushException as error:
            # 404 y 410 quieren decir que ese telefono ya no existe: se
            # apaga la fila en vez de reintentarla todas las semanas.
            codigo = getattr(error.response, "status_code", None)
            if codigo in (404, 410):
                fila.activa = False
                apagadas += 1
            else:
                registro.warning("aviso no entregado a %s: %s",
                                 fila.persona_id, error)
        except Exception as error:                        # noqa: BLE001
            # Un aviso que no sale no puede tumbar lo que lo llamo.
            registro.warning("fallo el aviso a %s: %s", fila.persona_id, error)

    if apagadas:
        db.flush()
    return {"enviados": enviados, "telefonos": len(filas),
            "apagadas": apagadas}


# ==================================================================
# En que idioma se le habla a cada quien
#
# Los avisos iban en espanol fijo, tambien a Brasil (seccion 99). Como
# la app: el idioma sale del pais de la plaza de la persona.
# ==================================================================

TEXTOS_PUSH = {
    "es": {
        "vispera_titulo": "Mañana trabajas",
        "vispera_cuerpo": "Mañana a las {hora}{mas}. Abre la app y confirma de enterado.",
        "vispera_mas": " y {n} servicio(s) más",
        "relevo_entra_titulo": "Entras a un servicio",
        "relevo_entra_cuerpo": "Cubres a {quien}: {cuando}{dias}. Abre la app y confirma de enterado.",
        "relevo_sale_titulo": "Ya no vas a este servicio",
        "relevo_sale_cuerpo": "{quien} te cubre: {cuando}{dias}. No te presentes; revisa tu día en la app.",
        "relevo_dias": " · {n} días",
        "relevo_rango": "{desde} al {hasta}",
        "asignacion_titulo": "Trabajas {dia}",
        "asignacion_cuerpo": "Te acaban de asignar {folio}: {dia} a las {hora}. Abre la app y confirma.",
        "hoy": "hoy", "manana": "mañana",
        "deposito_titulo": "Ya te depositaron",
        "deposito_cuerpo": "{monto} de viáticos.{referencia} Ya lo puedes ver en la app.",
        "deposito_referencia": " Referencia {ref}.",
        "devolucion_titulo": "Tu devolución no se pudo confirmar",
        "comprobante_titulo": "Te rechazaron un comprobante",
        "comprobante_de": "{concepto} de {monto}.",
        "falta_con_plazo": "Te faltan {monto} por comprobar hasta el {limite}.",
        "falta_sin_plazo": "Te faltan {monto} por comprobar. El plazo de 24 horas corre cuando termine el servicio.",
        "cancelacion_titulo": "Se canceló un servicio",
        "cancelacion_cuerpo": "{folio}: {rango} ya no va. No te presentes; revisa tu día en la app.",
        "cambio_hora_titulo": "Cambió tu hora",
        "cambio_hora_cuerpo": "{fecha}: ahora es a las {hora} (antes {antes}). Revisa tu día en la app.",
        "prueba": "Los avisos están funcionando en este teléfono.",
        "accion_confirmar": "Confirmo que voy",
        "accion_en_camino": "Voy en camino",
        "accion_abrir": "Abrir",
    },
    "pt": {
        "vispera_titulo": "Amanhã você trabalha",
        "vispera_cuerpo": "Amanhã às {hora}{mas}. Abra o app e confirme.",
        "vispera_mas": " e mais {n} serviço(s)",
        "relevo_entra_titulo": "Você entra em um serviço",
        "relevo_entra_cuerpo": "Você cobre {quien}: {cuando}{dias}. Abra o app e confirme.",
        "relevo_sale_titulo": "Você já não vai a este serviço",
        "relevo_sale_cuerpo": "{quien} cobre você: {cuando}{dias}. Não se apresente; veja o seu dia no app.",
        "relevo_dias": " · {n} dias",
        "relevo_rango": "{desde} a {hasta}",
        "asignacion_titulo": "Você trabalha {dia}",
        "asignacion_cuerpo": "Acabaram de designar você para {folio}: {dia} às {hora}. Abra o app e confirme.",
        "hoy": "hoje", "manana": "amanhã",
        "deposito_titulo": "Já depositaram para você",
        "deposito_cuerpo": "{monto} de diárias.{referencia} Já pode ver no app.",
        "deposito_referencia": " Referência {ref}.",
        "devolucion_titulo": "A sua devolução não pôde ser confirmada",
        "comprobante_titulo": "Rejeitaram um comprovante seu",
        "comprobante_de": "{concepto} de {monto}.",
        "falta_con_plazo": "Faltam {monto} para comprovar até {limite}.",
        "falta_sin_plazo": "Faltam {monto} para comprovar. O prazo de 24 horas corre quando o serviço terminar.",
        "cancelacion_titulo": "Um serviço foi cancelado",
        "cancelacion_cuerpo": "{folio}: {rango} já não acontece. Não se apresente; veja o seu dia no app.",
        "cambio_hora_titulo": "O seu horário mudou",
        "cambio_hora_cuerpo": "{fecha}: agora é às {hora} (antes {antes}). Veja o seu dia no app.",
        "prueba": "Os avisos estão funcionando neste telefone.",
        "accion_confirmar": "Confirmo que vou",
        "accion_en_camino": "Estou a caminho",
        "accion_abrir": "Abrir",
    },
}


def idioma_de(db: Session, persona_id: int | None) -> str:
    """El idioma del pais de la plaza de la persona; espanol si no hay."""
    from app import reloj

    persona = db.get(m.Persona, persona_id) if persona_id else None
    pais_id = reloj.pais_de_la_persona(persona)
    pais = db.get(m.Pais, pais_id) if pais_id else None
    codigo = (getattr(pais, "idioma", None) or "es").lower()
    return codigo if codigo in TEXTOS_PUSH else "es"


def tx(idioma: str, clave: str, **datos) -> str:
    plantilla = TEXTOS_PUSH.get(idioma, TEXTOS_PUSH["es"]).get(
        clave, TEXTOS_PUSH["es"].get(clave, clave))
    return plantilla.format(**datos) if datos else plantilla


# ==================================================================
# El recordatorio de la vispera
# ==================================================================

# A que hora corre el recordatorio de la vispera. Vive aqui y no solo
# en el calendario de Celery porque hay dos lugares que necesitan el
# mismo numero: el que manda el recordatorio y el que decide si un
# servicio ya se quedo sin el. Si cada uno tuviera el suyo, el dia que
# alguien mueva la hora se abre un hueco por el que no pasa ningun
# aviso.
HORA_DEL_RECORDATORIO = 17


def sin_confirmar(db: Session, dia) -> list[tuple]:
    """Quien tiene servicio ese dia y todavia no ha dicho que va."""
    filas = (db.query(m.AsignacionPersonal)
             .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
             .filter(m.Jornada.fecha == dia,
                     m.Jornada.estatus != m.EstatusJornada.CANCELADA,
                     m.AsignacionPersonal.confirmado.is_(False))
             .all())
    return [(a.persona_id, a.jornada) for a in filas if a.persona_id]


def recordar_la_vispera(db: Session, dia=None,
                        ahora=None) -> dict:
    """Le recuerda a cada quien que manana trabaja.

    Es el aviso que de verdad justifica todo esto: la confirmacion de la
    vispera dependia de que alguien se acordara de abrir la app, y una
    confirmacion que nadie hace es un renglon rojo eterno en la central.

    Un aviso por persona aunque tenga dos servicios: tres notificaciones
    seguidas se leen como una falla, no como insistencia.

    Sale a las cinco de la tarde *del pais donde se trabaja*, no de
    Mexico. El beat la llama cada hora en punto y aqui se decide a
    quien le toca: `ahora` con zona sirve para pararse en un instante y
    ver que pais contesta; sin zona vale para todos por igual, que es
    lo que quieren las pruebas que no estan viendo husos.
    """
    from datetime import date, timedelta

    from app import reloj

    # A quien le toca ahorita. "Manana" es el manana de cada pais, y la
    # hora tambien: con un solo disparo en hora de Mexico el aviso le
    # llegaba a Brasil a las 19:00 --dos horas menos de noche para
    # conseguir un relevo-- y a un pais al poniente en plena tarde de
    # trabajo, cuando todavia no se sabe quien falta manana.
    activos = db.query(m.Pais).filter(m.Pais.activo.is_(True)).all()
    if dia is not None:
        # Una fecha a mano manda sobre el reloj: eso es la tarea corrida
        # a proposito, no el calendario.
        toca = [(p, dia) for p in activos] or [(None, dia)]
    elif activos:
        # Desde las cinco, en la primera vuelta que no lo haya mandado
        # (seccion 99). Antes era "a las cinco en punto": si el reloj se
        # saltaba esa vuelta --un despliegue, el worker caido--, la tarea
        # corria a las 18:05 y ese dia nadie recibia el recordatorio.
        toca = []
        for p in activos:
            local = reloj.ahora_en(p, ahora)
            manana = local.date() + timedelta(days=1)
            if (local.hour >= HORA_DEL_RECORDATORIO
                    and not _vispera_ya_mandada(db, p, manana)):
                toca.append((p, manana))
    else:
        # Sin paises dados de alta queda el reloj de la casa.
        toca = ([(None, date.today() + timedelta(days=1))]
                if reloj.ahora_en(None, ahora).hour >= HORA_DEL_RECORDATORIO
                else [])

    if not toca:
        return {"dias": [], "paises": [], "avisados": [], "sin_telefono": 0,
                "motivo": (f"no son las {HORA_DEL_RECORDATORIO}:00 "
                           "en ningun pais")}

    por_persona: dict[int, list] = {}
    for pais, cada in sorted(toca, key=lambda par: par[1]):
        for persona_id, jornada in sin_confirmar(db, cada):
            if pais is not None and (reloj.pais_de_la_jornada(jornada)
                                     != pais.id):
                # El dia coincide pero el equipo trabaja en otro pais:
                # su recordatorio sale a su hora, no a esta.
                continue
            por_persona.setdefault(persona_id, []).append(jornada)

    avisados = []
    for persona_id, jornadas in por_persona.items():
        jornadas.sort(key=lambda j: j.inicio_programado)
        primera = jornadas[0]
        cuantos = len(jornadas)
        lengua = idioma_de(db, persona_id)
        cuerpo = tx(lengua, "vispera_cuerpo",
                    hora=f"{primera.inicio_programado:%H:%M}",
                    mas=(tx(lengua, "vispera_mas", n=cuantos - 1)
                         if cuantos > 1 else ""))
        r = avisar(db, persona_id, tx(lengua, "vispera_titulo"), cuerpo,
                   etiqueta="vispera", horas=HORAS_DE_ESPERA_VISPERA,
                   accion="confirmar")
        if r["enviados"]:
            avisados.append({"persona_id": persona_id,
                             "servicios": cuantos})
    # Queda anotado por pais para que la siguiente vuelta no lo repita:
    # el recordatorio es uno por noche, aunque el reloj pase cada hora.
    if dia is None:
        for pais, cada in toca:
            if pais is not None:
                _anotar_vispera(db, pais, cada)
    db.commit()
    return {"dias": sorted({d.isoformat() for _, d in toca}),
            "paises": [p.codigo for p, _ in toca if p is not None],
            "avisados": avisados,
            "sin_telefono": len(por_persona) - len(avisados)}


def _clave_vispera(pais) -> str:
    return f"campo.recordar_la_vispera/{pais.codigo}"


def _vispera_ya_mandada(db: Session, pais, manana) -> bool:
    """Si el recordatorio de ese pais para ese dia ya salio.

    Vive en la ultima vuelta del reloj, con una fila por pais: el dia al
    que le toco queda en la nota. El manual no la ensena --no es una
    tarea del calendario-- y las pruebas la vacian con lo demas.
    """
    fila = db.get(m.VueltaDelReloj, _clave_vispera(pais))
    return fila is not None and fila.nota == manana.isoformat()


def _anotar_vispera(db: Session, pais, manana) -> None:
    from datetime import datetime, timezone

    from app import manual

    manual.anotar_vuelta(_clave_vispera(pais),
                         termino=datetime.now(timezone.utc),
                         nota=manana.isoformat(), db=db)


# ==================================================================
# El relevo: el aviso que no puede esperar al de la vispera
# ==================================================================

def avisar_relevo(db: Session, entra: m.Persona, sale: m.Persona,
                  cambio: dict) -> dict:
    """Le avisa al que entra, en el momento del cambio.

    El recordatorio de la vispera solo mira manana. Un reemplazo hecho
    hoy para hoy nunca lo dispararia, y ese es justamente el urgente: la
    persona que entra se enteraba porque le hablaban por telefono, o no
    se enteraba.

    Como todos los avisos, este no detiene nada: si no sale, el cambio
    ya quedo hecho igual.
    """
    dias = cambio.get("jornadas_afectadas") or []
    if not dias:
        return {"enviados": 0, "motivo": "sin dias"}

    cuantos = len(dias)

    def _texto(lengua, clave, quien):
        cuando = (dias[0] if cuantos == 1
                  else tx(lengua, "relevo_rango", desde=dias[0], hasta=dias[-1]))
        return tx(lengua, clave, quien=quien, cuando=cuando,
                  dias=(tx(lengua, "relevo_dias", n=cuantos)
                        if cuantos > 1 else ""))

    de_entra = idioma_de(db, entra.id)
    r = avisar(
        db, entra.id,
        titulo=tx(de_entra, "relevo_entra_titulo"),
        cuerpo=_texto(de_entra, "relevo_entra_cuerpo", sale.nombre),
        etiqueta="relevo", urgente=True, accion="confirmar")

    # Y al que sale. Era el mismo aviso y faltaba la mitad: quien se
    # quedo fuera se enteraba por telefono, o se presentaba a las seis
    # de la manana a un servicio que ya no era suyo.
    de_sale = idioma_de(db, sale.id)
    avisar(
        db, sale.id,
        titulo=tx(de_sale, "relevo_sale_titulo"),
        cuerpo=_texto(de_sale, "relevo_sale_cuerpo", entra.nombre),
        etiqueta="relevo", urgente=True)
    return r


def avisar_asignacion_sin_vispera(db: Session, jornadas: list,
                                  persona_id: int) -> dict:
    """Te acaban de asignar, y a este servicio ya no le toca la vispera.

    El recordatorio de la vispera lo manda el reloj a las cinco de la
    tarde, para manana. Hay dos servicios que se le escapan siempre:

      * el de hoy para hoy, que nunca tuvo vispera;
      * el de manana armado despues de las cinco, cuando el
        recordatorio de esta tarde ya corrio.

    En los dos casos la persona se enteraba porque le hablaban por
    telefono, o no se enteraba. Y son justo los urgentes: ya no queda un
    dia para arreglarlo.

    Lo que se asigna con dias de anticipacion NO se avisa aqui: para eso
    esta la vispera, y dos avisos por lo mismo ensenan a ignorar los
    avisos.

    "Hoy" y "manana" son los del pais donde esta el equipo, no los del
    servidor: con el reloj del contenedor, a alguien en Brasil se le
    decidiria por una fecha que alla ya cambio.

    Como todos los avisos, este no detiene nada: si no sale, la
    asignacion ya quedo hecha igual.
    """
    from app import reloj

    urgentes = []
    for j in jornadas:
        if j.estatus in (m.EstatusJornada.CANCELADA,
                         m.EstatusJornada.TERMINADA):
            continue
        alla = reloj.ahora_de_la_jornada(db, j)
        if j.fecha == alla.date():
            urgentes.append((j, "hoy"))
        elif (j.fecha == alla.date() + timedelta(days=1)
                and alla.hour >= HORA_DEL_RECORDATORIO):
            urgentes.append((j, "manana"))
    if not urgentes:
        return {"enviados": 0, "motivo": "todavia le toca la vispera"}

    urgentes.sort(key=lambda par: par[0].inicio_programado)
    primera, cuando = urgentes[0]
    servicio = primera.equipo.servicio
    lengua = idioma_de(db, persona_id)
    dia = tx(lengua, "hoy" if cuando == "hoy" else "manana")
    return avisar(
        db, persona_id,
        titulo=tx(lengua, "asignacion_titulo", dia=dia),
        cuerpo=tx(lengua, "asignacion_cuerpo", folio=servicio.folio, dia=dia,
                  hora=f"{primera.inicio_programado:%H:%M}"),
        etiqueta="asignacion-urgente", urgente=True, accion="confirmar")


# ==================================================================
# El dinero: los dos avisos que la central contesta por telefono
# ==================================================================

def _peso(monto, moneda) -> str:
    """El monto como se dice, no como se guarda."""
    try:
        numero = f"{float(monto):,.0f}"
    except (TypeError, ValueError):
        numero = str(monto)
    codigo = getattr(moneda, "value", moneda) or ""
    return f"${numero} {codigo}".strip()


def avisar_deposito(db: Session, deposito) -> dict:
    """Ya le depositaron.

    Es la pregunta que mas recibe la central --"¿ya me depositaron?"-- y
    la unica forma de contestarla era que alguien mirara la bandeja. El
    dinero ya aparece en la app como saldo, pero solo si la persona
    entra a mirar; nadie entra a mirar lo que no sabe que llego.

    Va con la referencia del banco a proposito: es lo que sirve para
    reclamar si el banco no lo abono, y es lo primero que pide el
    ejecutivo de cuenta.
    """
    referencia = (deposito.referencia or "").strip()
    lengua = idioma_de(db, deposito.persona_id)
    return avisar(
        db, deposito.persona_id,
        titulo=tx(lengua, "deposito_titulo"),
        cuerpo=tx(lengua, "deposito_cuerpo",
                  monto=_peso(deposito.monto, deposito.moneda),
                  referencia=(tx(lengua, "deposito_referencia", ref=referencia)
                              if referencia else "")),
        etiqueta="deposito")


def avisar_devolucion_rechazada(db: Session, devolucion) -> dict:
    """Dijo que transfirio y finanzas no lo encontro.

    Sin este aviso, la persona cree que ya devolvio y lo que ve en la
    app un mes despues es que sigue debiendo, sin saber por que.
    """
    viatico = devolucion.asignacion
    return avisar(
        db, viatico.persona_id,
        titulo=tx(idioma_de(db, viatico.persona_id), "devolucion_titulo"),
        cuerpo=(f"{_peso(devolucion.monto, devolucion.moneda)}: "
                f"{devolucion.motivo_rechazo}"),
        etiqueta="devolucion", urgente=True)


def avisar_comprobante_rechazado(db: Session, viatico, comprobante) -> dict:
    """Le rechazaron un comprobante, y eso le abre una diferencia.

    Sin este aviso, el rechazo se entera de dos maneras: cuando ve el
    descuento en su pago, o cuando alguien le habla. Y casi siempre lo
    que paso es que el ticket salio borroso o subio el equivocado --dos
    minutos de arreglo-- asi que avisar a tiempo evita un descuento y un
    reclamo.

    Lleva el motivo tal cual lo escribio el consultor: un rechazo sin
    razon no se puede corregir, solo se puede discutir.
    """
    # Lo que falta es de todo su dinero en el servicio, no del dia del
    # ticket: es la misma cuenta que ve en su tarjeta (seccion 59).
    from app import bolson
    cuenta = bolson.cuenta(bolson.de_la_persona(db, viatico))
    falta = cuenta["falta"]
    limite = cuenta["limite"]
    motivo = (comprobante.motivo_rechazo or "").strip()
    concepto = getattr(comprobante.concepto, "value", comprobante.concepto)

    lengua = idioma_de(db, viatico.persona_id)
    partes = [tx(lengua, "comprobante_de", concepto=concepto,
                 monto=_peso(comprobante.monto, viatico.moneda))]
    if motivo:
        partes.append(f"{motivo}.")
    if falta > 0:
        # Sin limite el servicio no ha terminado: decir que el plazo
        # "sigue corriendo" era falso y asustaba de mas.
        partes.append(tx(lengua, "falta_con_plazo",
                         monto=_peso(falta, viatico.moneda),
                         limite=f"{limite:%d/%m %H:%M}")
                      if limite else
                      tx(lengua, "falta_sin_plazo",
                         monto=_peso(falta, viatico.moneda)))
    return avisar(
        db, viatico.persona_id,
        titulo=tx(lengua, "comprobante_titulo"),
        cuerpo=" ".join(partes),
        # Urgente de verdad: lo que esta corriendo es un plazo, y lo que
        # hay del otro lado es un descuento de su pago.
        etiqueta="comprobante", urgente=True)


# ==================================================================
# Los dos avisos que dejan a alguien parado en la calle
# ==================================================================

def _asignados(db: Session, jornadas: list) -> dict:
    """Quien tiene asignadas esas jornadas, con sus dias juntos.

    Un aviso por persona y no por dia: a quien le cancelan tres dias de
    un servicio no le sirven tres notificaciones iguales, le sirve
    saber que ese servicio ya no va.
    """
    ids = [j.id for j in jornadas]
    if not ids:
        return {}
    filas = (db.query(m.AsignacionPersonal)
             .filter(m.AsignacionPersonal.jornada_id.in_(ids))
             .all())
    por_persona: dict = {}
    for a in filas:
        if not a.persona_id:
            continue
        # Quien ya fue relevado de ese dia no tiene por que enterarse:
        # para el ese dia ya se acabo.
        if getattr(a, "relevado_en", None):
            continue
        por_persona.setdefault(a.persona_id, []).append(a.jornada)
    return por_persona


def _rango(jornadas: list, idioma: str = "es") -> str:
    dias = sorted({j.fecha for j in jornadas})
    if len(dias) == 1:
        return f"{dias[0]:%d/%m}"
    return tx(idioma, "relevo_rango", desde=f"{dias[0]:%d/%m}",
              hasta=f"{dias[-1]:%d/%m}")


def avisar_cancelacion(db: Session, jornadas: list, folio: str) -> dict:
    """El servicio ya no va, y quien lo iba a trabajar tiene que saberlo.

    Sin esto, la cancelacion se quedaba entre el consultor y el sistema:
    el equipo se presentaba a las seis de la manana a un servicio que ya
    no existia. Es el aviso mas barato de todos y el que mas pena da no
    tener.
    """
    avisados = []
    for persona_id, suyas in _asignados(db, jornadas).items():
        lengua = idioma_de(db, persona_id)
        r = avisar(db, persona_id,
                   titulo=tx(lengua, "cancelacion_titulo"),
                   cuerpo=tx(lengua, "cancelacion_cuerpo", folio=folio,
                             rango=_rango(suyas, lengua)),
                   etiqueta="cancelacion", urgente=True)
        if r["enviados"]:
            avisados.append(persona_id)
    return {"avisados": len(avisados)}


def avisar_cambio_de_hora(db: Session, jornada, antes) -> dict:
    """Confirmo para las cinco y la hora se movio.

    La confirmacion de la vispera se hace sobre una hora; si esa hora
    cambia despues y nadie avisa, la confirmacion queda apuntando a algo
    que ya no es cierto.
    """
    if jornada.estatus in (m.EstatusJornada.CANCELADA,
                           m.EstatusJornada.TERMINADA):
        return {"avisados": 0, "motivo": "el dia ya no se mueve"}

    avisados = []
    for persona_id in _asignados(db, [jornada]):
        lengua = idioma_de(db, persona_id)
        r = avisar(db, persona_id,
                   titulo=tx(lengua, "cambio_hora_titulo"),
                   cuerpo=tx(lengua, "cambio_hora_cuerpo",
                             fecha=f"{jornada.fecha:%d/%m}",
                             hora=f"{jornada.inicio_programado:%H:%M}",
                             antes=f"{antes:%H:%M}"),
                   etiqueta="cambio-hora", urgente=True)
        if r["enviados"]:
            avisados.append(persona_id)
    return {"avisados": len(avisados)}

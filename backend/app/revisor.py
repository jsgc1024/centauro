"""Revisor automatico del cierre.

Acompana al consultor durante sus 24 horas: revisa el servicio y le avisa
lo que detecta mal para que lo corrija ANTES de enviarlo a finanzas.
El mismo revisor hace el primer filtro del comparativo para finanzas.

Hoy son reglas deterministas. Aqui es donde se conecta despues el modelo
de lenguaje corriendo en local, para que ademas redacte la explicacion y
detecte patrones que las reglas no ven.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import cierre as motor
from app import cotizacion as cot
from app import horas_extra
from app import models as m
from app import reloj

GRAVE = "corregir"
AVISO = "revisar"
INFO = "informativo"


SIN_COTIZACION = ("El servicio no tiene una cotizacion autorizada, y sin "
                  "ella no hay contra que comparar lo ejecutado")
# El asunto de la observacion cuando la lista del cliente no cotiza lo
# que fue, o alguien fue sin rol (seccion 101). La pantalla lo traduce.
SIN_PRECIO = "Sin precio en la lista"


def cliente_sin_ficha_en_odoo(servicio: m.Servicio) -> dict | None:
    """El cliente que no tiene su ficha en Odoo no deja dar el visto bueno
    (seccion 117, decision 3 de Salvador): con el visto bueno sale la
    prefactura a Odoo, y sin la ficha no hay a quien facturarle. Solo
    cuando la factura ya va a Odoo --la llave esta puesta--: antes, el
    visto bueno no manda nada y frenarlo no serviria de nada. Igual para
    el eventual y para el mes del implantado."""
    from sqlalchemy.orm import object_session

    from app import odoo_facturacion

    cliente = servicio.cliente
    if not odoo_facturacion.hay_llave() or (cliente and cliente.odoo_id):
        return None
    # Solo donde la factura va a Odoo: los paises con su compania alla
    # (seccion 119, Mexico y Brasil). En otro pais no hay prefactura que
    # frenar.
    db = object_session(servicio)
    if db is not None and odoo_facturacion.compania_de(db, servicio) is None:
        return None
    nombre = cliente.nombre if cliente else "del servicio"
    return {
        "nivel": GRAVE, "asunto": "Cliente sin ficha en Odoo",
        "clave": "cliente_sin_odoo", "datos": {"cliente": nombre},
        "mensaje": (f"El cliente {nombre} no tiene su ficha en Odoo: sin ella "
                    "no se le puede mandar la prefactura"),
        "accion": ("Que finanzas lo dé de alta en Odoo con su RFC y la "
                   "etiqueta «Protección ejecutiva»; la lectura de clientes "
                   "de cada hora lo trae.")}


def revisar(db: Session, servicio_id: int, ahora: datetime | None = None) -> dict:
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    # "Te quedan N horas para cerrar" se cuenta en el pais del servicio.
    ahora = reloj.ahora_del_servicio(db, servicio, ahora)

    # Sin cotizacion autorizada no hay comparativo. Eso la revision lo
    # REPORTA; no se cae con ello.
    #
    # Esto es una lectura y la pantalla del servicio la pide sola al
    # abrir: contestar 409 dejaba un error rojo en la consola del
    # navegador y hacia ver roto un servicio al que solo le faltaba un
    # dato. El plazo de 24 horas corre igual, tenga cotizacion o no, y
    # ese es justamente el momento en que mas falta hace verlo.
    if not cot.vigente(db, servicio_id):
        return {
            "servicio": servicio.folio,
            "revisado_en": ahora.isoformat(),
            "cierre": motor.estado(db, servicio_id, ahora),
            "listo_para_finanzas": False,
            "resumen": "1 punto(s) por corregir antes de enviar a finanzas",
            "observaciones": [{
                "nivel": GRAVE, "asunto": "Sin cotizacion autorizada",
                # En clave para que la pantalla lo diga en su idioma y
                # apunte al bloque donde se registra (seccion 94).
                "clave": "sin_cotizacion",
                "mensaje": SIN_COTIZACION,
                "accion": "Registrala en «La cotizacion autorizada», arriba "
                          "en el servicio: sin ella no hay comparativo ni "
                          "factura."}],
            "comparativo": None,
        }

    # Alguien fue sin rol, o con un rol o una unidad que la lista del
    # cliente no cotiza: el comparativo no se puede armar, y eso tambien
    # se REPORTA (seccion 101). Antes reventaba con 400 y la tarjeta
    # pintaba el texto crudo sin decir que hacer, con el boton de visto
    # bueno vivo contestando el mismo 400.
    try:
        comparativo = motor.comparar(db, servicio_id)
    except HTTPException as error:
        detalle = error.detail if isinstance(error.detail, dict) else {}
        if error.status_code != 400 or "clave" not in detalle:
            raise
        return {
            "servicio": servicio.folio,
            "revisado_en": ahora.isoformat(),
            "cierre": motor.estado(db, servicio_id, ahora),
            "listo_para_finanzas": False,
            "resumen": "1 punto(s) por corregir antes de enviar a finanzas",
            "observaciones": [{
                "nivel": GRAVE, "asunto": SIN_PRECIO,
                "clave": detalle["clave"],
                "datos": {"que": detalle.get("que"),
                          "modalidad": detalle.get("modalidad")},
                "mensaje": detalle["mensaje"],
                "accion": detalle.get("que_hacer", "")}],
            "comparativo": None,
        }
    observaciones = []

    # --- desviaciones del comparativo
    respaldadas = set()
    registro = (db.query(m.Cierre)
                .filter_by(servicio_id=servicio_id, contrato_id=None).first())
    if registro:
        respaldadas = {d.descripcion for d in registro.desviaciones if d.respaldada}

    # Las horas extra las genera el cliente al retener al equipo, llevan su
    # aviso preventivo y se cobran por tarifa: se informan, no frenan el cierre.
    INFORMATIVAS = {m.TipoDesviacion.HORAS_EXTRA.value}

    # El dinero del personal se dice aparte, persona por persona (abajo):
    # repetirlo aqui como desviacion ponia dos veces el mismo pendiente
    # en la lista, y con una accion que no era suya ("recotiza").
    DEL_DINERO = {m.TipoDesviacion.VIATICO_SIN_COMPROBAR.value,
                  m.TipoDesviacion.VIATICO_NO_CERRADO.value}

    cobro = comparativo.get("cobro")
    for d in comparativo["desviaciones"]:
        if d["tipo"] in DEL_DINERO and not d.get("respaldada"):
            continue
        if d["tipo"] in INFORMATIVAS:
            # Se dicen abajo, dia por dia y en horas (seccion 65): el
            # renglon de dinero ("cobra 960 mas de lo cotizado") no decia
            # cuantas horas ni por que.
            continue
        # El dia que se cancelo con el servicio no se recotiza ni se
        # justifica (seccion 105): se dice, con lo que operaciones
        # decidio cobrar. La pantalla lo traduce por su clave.
        if d.get("informativa"):
            completo = bool(cobro and cobro["cobro"] == motor.COBRO_COMPLETO)
            observaciones.append({
                "nivel": INFO, "asunto": "Dia cancelado",
                "clave": "dia_cancelado",
                "datos": {"completo": completo, "fecha": d.get("fecha"),
                          "equipo": d.get("equipo"), "que": d.get("que")},
                "mensaje": d["descripcion"],
                "accion": ("Se cobra completo por decision de operaciones."
                           if completo else
                           "No se cobra: el servicio se cancelo.")})
            continue
        # El cierre con descuento ya viene resuelto: hay decision tomada,
        # motivo escrito y dinero asignado. No hay nada que justificar.
        if d.get("respaldada") or d["descripcion"] in respaldadas:
            observaciones.append({
                "nivel": INFO, "asunto": "Desviacion respaldada",
                "mensaje": d["descripcion"],
                "accion": "Ya tiene justificacion registrada, no escala."})
            continue
        observaciones.append({
            "nivel": GRAVE, "asunto": d["tipo"],
            "mensaje": d["descripcion"],
            # La tarjeta ofrece "Justificar" sobre estas (seccion 105): es
            # la desviacion viva que `respaldar` acepta tal como se dice.
            "justificable": True,
            "accion": "Recotiza y autoriza con el cliente, o justifica la desviacion."})

    # El cobro de la cancelacion sin autorizar (seccion 105): el visto
    # bueno espera a direccion de operaciones. Grave, para que la tarjeta
    # lo diga arriba y el envio lo frene.
    if cobro and not cobro["autorizado"]:
        observaciones.append({
            "nivel": GRAVE, "asunto": "Cobro por autorizar",
            "clave": "cobro_por_autorizar",
            "datos": {"cobro": cobro["cobro"]},
            "mensaje": (f"El consultor pidio cobrar la cancelacion "
                        f"{cobro['cobro']}; falta que direccion de operaciones "
                        "lo autorice"),
            "accion": "Direccion de operaciones lo autoriza desde «Autorizar "
                      "el cobro», en esta tarjeta."})

    # --- el cliente sin ficha en Odoo (seccion 117, decision 3 de Salvador)
    sin_ficha = cliente_sin_ficha_en_odoo(servicio)
    if sin_ficha:
        observaciones.append(sin_ficha)

    # --- el tipo de cambio (seccion 82). Con gastos netos y la cotizacion
    # en otra moneda, lo comprobado --en pesos-- se factura en la moneda
    # de la cotizacion al tipo de cambio que este puesto en el visto
    # bueno. Sin el no hay cifra de gastos: la factura no puede salir.
    sin_cambio = comparativo["gastos"].get("sin_tipo_de_cambio")
    if sin_cambio:
        observaciones.append({
            "nivel": GRAVE, "asunto": "Sin tipo de cambio",
            "clave": "sin_tipo_de_cambio", "datos": sin_cambio,
            "mensaje": (f"Los gastos se comprobaron en {sin_cambio['local']} "
                        f"y se facturan en {sin_cambio['moneda']}: "
                        f"{sin_cambio['mensaje']}"),
            "accion": sin_cambio["que_hacer"]})

    # --- las horas extra en horas, las corregidas y las que no tienen
    # precio (seccion 65). Ninguna frena el visto bueno.
    ejecutado = comparativo["ejecutado"]
    observaciones.extend(horas_extra.observaciones(
        db, [j for e in servicio.equipos for j in e.jornadas],
        ejecutado["horas_extra_por_dia"], ejecutado["horas_extra_sin_precio"]))

    # --- jornadas sin cerrar
    for equipo in servicio.equipos:
        for j in equipo.jornadas:
            if j.estatus == m.EstatusJornada.CANCELADA:
                continue
            if not j.fin_real:
                observaciones.append({
                    "nivel": GRAVE, "asunto": "Jornada sin termino",
                    "mensaje": f"{j.fecha}: el conductor no marco el fin del servicio",
                    "accion": "Pide a la central que registre el corte con justificacion."})

    # --- la unidad que salio del servicio y no se entrego (seccion 107)
    #
    # El fin del dia ya no la frena; lo que la reclama es esto. Grave
    # mientras siga abierta: el cierre no sale a finanzas con una
    # camioneta de la que nadie sabe como volvio. La salida, cuando las
    # fotos ya no se pueden tomar, es registrarla sin revision con la
    # razon --y entonces se dice, informativo, quien lo decidio--.
    from app import entregas
    for pendiente in entregas.del_servicio(db, servicio_id, ahora).values():
        if pendiente["cerrada_en"] is None:
            observaciones.append({
                "nivel": GRAVE, "asunto": "Unidad sin entregar",
                "clave": "entrega_pendiente",
                "datos": {"placa": pendiente["placa"],
                          "persona": pendiente["persona"],
                          "limite": pendiente["limite"],
                          "vencido": pendiente["vencido"],
                          "entrega_id": pendiente["entrega_id"]},
                "mensaje": (f"La unidad {pendiente['placa']} salio del "
                            f"servicio y no tiene su revision de entrega "
                            f"(responde {pendiente['persona']})"),
                "accion": ("Que la entregue con las cinco fotos desde su "
                           "app. Si ya no se puede, registrala como "
                           "entregada sin revision, con la razon, desde la "
                           "revision de la unidad en esta ficha.")})
        elif pendiente["sin_revision"]:
            observaciones.append({
                "nivel": INFO, "asunto": "Entregada sin revision",
                "clave": "entrega_sin_revision",
                "datos": {"placa": pendiente["placa"],
                          "quien": pendiente["justificada_por"],
                          "justificacion": pendiente["justificacion"]},
                "mensaje": (f"La unidad {pendiente['placa']} se dio por "
                            f"entregada sin revision"
                            f" ({pendiente['justificada_por']}): "
                            f"{pendiente['justificacion']}"),
                "accion": "No hay fotos de como volvio; queda escrito quien "
                          "lo decidio y por que."})

    # --- viaticos que nadie cerro
    #
    # Va aqui y es grave por dos razones. La primera es del dinero: el
    # comparativo cuenta como facturable lo comprobado, asi que enviar a
    # finanzas con comprobaciones abiertas es facturar sobre una cifra
    # que todavia se mueve.
    #
    # La segunda es de la persona. Con el visto bueno dado, el gasto
    # desaparece de la app del agente --ya no hay nada que el pueda
    # hacer-- asi que un viatico abierto en ese momento se convierte
    # solo en un descuento a su nomina que el no vio venir. Si de verdad
    # no comprobo, el consultor lo cierra con descuento: eso es una
    # decision tomada, no un olvido.
    observaciones.extend(observaciones_del_dinero(
        motor.viaticos_del_servicio(db, servicio_id), ahora))

    # --- marcas que la central no ha revisado
    pendientes = (db.query(m.Hito)
                  .join(m.Jornada, m.Hito.jornada_id == m.Jornada.id)
                  .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                  .filter(m.Equipo.servicio_id == servicio_id,
                          m.Hito.requiere_revision.is_(True)).all())
    for h in pendientes:
        observaciones.append({
            "nivel": AVISO, "asunto": "Marca fuera de horario sin revisar",
            "mensaje": f"{h.tipo.value} del {h.marcado_en:%d/%m %H:%M} sigue marcado "
                       f"para revision de la central",
            "accion": "La central debe validarla o ajustarla antes del cierre."})

    # --- alertas abiertas
    abiertas = (db.query(m.Alerta)
                .join(m.Jornada, m.Alerta.jornada_id == m.Jornada.id)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                .filter(m.Equipo.servicio_id == servicio_id,
                        m.Alerta.atendida.is_(False)).all())
    if abiertas:
        observaciones.append({
            "nivel": AVISO, "asunto": "Alertas sin atender",
            "mensaje": f"{len(abiertas)} alerta(s) de la central siguen abiertas",
            "accion": "Cierra cada alerta con su resolucion."})

    # --- lo que dice la unidad (seccion 60): el fin contra la unidad y
    # la gasolina contra los kilometros. Para revisar, nunca frena: la
    # unidad no castiga a nadie sola; senala, y el consultor decide.
    from app import gps
    observaciones.extend(gps.observaciones(
        db, [j for e in servicio.equipos for j in e.jornadas],
        motor.viaticos_del_servicio(db, servicio_id)))

    # --- los dos relojes
    if registro and registro.estatus == m.EstatusCierre.ABIERTO:
        # Corren las 24 h del personal: el visto bueno todavia no abre.
        hasta = registro.comprobacion_hasta
        observaciones.append({
            "nivel": AVISO, "asunto": "Comprobacion en curso",
            "mensaje": (f"El personal tiene hasta el {hasta:%d/%m %H:%M} "
                        "para comprobar sus viaticos" if hasta else
                        "El personal esta comprobando sus viaticos"),
            "accion": "El visto bueno se abre cuando venza ese plazo, o "
                      "antes si todos los viaticos ya cerraron."})
    elif registro:
        observaciones.extend(observaciones_del_plazo(registro, ahora))

    graves = [o for o in observaciones if o["nivel"] == GRAVE]

    # El mismo reloj que la pantalla pide por su cuenta cuando esto
    # revienta por falta de cotizacion. Una sola definicion: si hubiera
    # dos, un dia dirian horas distintas.
    cierre = motor.estado(db, servicio_id, ahora)

    return {
        "servicio": comparativo["servicio"],
        "revisado_en": ahora.isoformat(),
        "cierre": cierre,
        "listo_para_finanzas": not graves,
        "resumen": ("Sin observaciones que corregir" if not graves
                    else f"{len(graves)} punto(s) por corregir antes de enviar a finanzas"),
        "observaciones": observaciones,
        "comparativo": comparativo,
    }


def _dinero(monto, moneda) -> str:
    return f"${monto:,.2f} {moneda or ''}".strip()


def observaciones_del_plazo(cierre: m.Cierre, ahora: datetime,
                            del_mes: bool = False) -> list[dict]:
    """Lo que el revisor dice del reloj del consultor.

    Regresado por finanzas corre el de 24 horas desde el regreso, y lo
    "en plazo" de su primer visto bueno ya quedo (decision 1 de
    Salvador, 23 sep): pasarse de ese reloj no toca la comision, solo
    retrasa la factura. Decir otra cosa asustaria por nada.
    """
    vigente = motor.limite_vigente(cierre)
    quien, hasta = vigente or ("consultor", cierre.limite_consultor)
    restante = (hasta - ahora).total_seconds() / 3600
    if quien == "regreso":
        if restante < 0:
            return [{
                "nivel": AVISO, "asunto": "Regreso vencido",
                "mensaje": (f"Se pasaron {abs(restante):.1f} h de las 24 horas "
                            "desde que finanzas lo regreso"),
                "accion": ("Mandalo de nuevo cuanto antes: lo en plazo de tu "
                           "primer visto bueno se queda como estaba.")}]
        if restante < 6:
            return [{
                "nivel": AVISO, "asunto": "Regreso por vencer",
                "mensaje": f"Quedan {restante:.1f} h para volver a mandarlo",
                "accion": "Corrige lo que pidio finanzas y mandalo."}]
        return []
    if restante < 0:
        # Vencido no significa que no se pueda facturar: debe cobrarse
        # igual. La consecuencia es la perdida de la comision.
        return [{
            "nivel": AVISO, "asunto": "Plazo vencido",
            "mensaje": f"Se pasaron {abs(restante):.1f} h del limite de 24 horas",
            "accion": ("El mes se factura igual; la comision del mes se "
                       "pierde si no se cerro a tiempo." if del_mes else
                       "El servicio ya esta fuera de plazo; la comision del "
                       "consultor se pierde si no se cerro a tiempo.")}]
    if restante < 6:
        return [{
            "nivel": AVISO, "asunto": "Plazo por vencer",
            "mensaje": f"Quedan {restante:.1f} h para cerrar y facturar",
            "accion": "Cierra pronto para no perder la comision."}]
    return []


def observaciones_del_dinero(viaticos: list, ahora: datetime) -> list[dict]:
    """El dinero del personal que sigue sin cerrar, persona por persona.

    Grave: con el visto bueno el gasto desaparece de la app de quien lo
    debe --ya no puede hacer nada-- y un viatico abierto en ese momento
    se volveria un descuento a su nomina que no vio venir. Si de verdad
    no comprobo, el consultor lo cierra con descuento cuando venza su
    plazo: eso es una decision tomada, no un olvido.
    """
    from app import bolson

    salida = []
    for suyos in bolson.agrupar(viaticos):
        c = bolson.cuenta(suyos)
        if c["estatus"] != "abierto":
            continue
        persona = suyos[0].persona
        nombre = persona.nombre if persona else str(suyos[0].persona_id)
        moneda = suyos[0].moneda.value if suyos[0].moneda else None
        partes = []
        if c["falta"] > 0:
            partes.append(f"le faltan {_dinero(c['falta'], moneda)} por "
                          "comprobar")
        elif c["falta"] < 0:
            partes.append(f"comprobo {_dinero(-c['falta'], moneda)} de mas")
        if c["por_depositar"] > 0:
            partes.append(f"{_dinero(c['por_depositar'], moneda)} autorizados "
                          "que no se depositaron")
        if c["devolucion_en_revision"] > 0:
            partes.append("una devolucion de "
                          f"{_dinero(c['devolucion_en_revision'], moneda)} "
                          "que finanzas no confirma")
        if c["sin_revisar"]:
            partes.append(f"{c['sin_revisar']} comprobante(s) sin revisar")
        if not partes:
            partes.append("ya cuadra; falta cerrarlo")
        vencido = c["limite"] is not None and ahora >= c["limite"]
        salida.append({
            "nivel": GRAVE, "asunto": "Viaticos sin cerrar",
            "mensaje": f"{nombre}: " + "; ".join(partes),
            "persona_id": suyos[0].persona_id,
            "accion": ("Cierralo abajo, en Viaticos del personal."
                       + (" Lo que no comprobo se puede cerrar con descuento: "
                          "su plazo ya vencio." if vencido and c["falta"] > 0
                          else ""))})
    return salida

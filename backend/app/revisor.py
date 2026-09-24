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
from app import models as m
from app import reloj

GRAVE = "corregir"
AVISO = "revisar"
INFO = "informativo"


SIN_COTIZACION = ("El servicio no tiene una cotizacion autorizada, y sin "
                  "ella no hay contra que comparar lo ejecutado")


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
                "mensaje": SIN_COTIZACION,
                "accion": "Captura la propuesta y marcala autorizada por el "
                          "cliente: sin ella no hay comparativo ni factura."}],
            "comparativo": None,
        }

    comparativo = motor.comparar(db, servicio_id)
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

    for d in comparativo["desviaciones"]:
        if d["tipo"] in DEL_DINERO and not d.get("respaldada"):
            continue
        if d["tipo"] in INFORMATIVAS:
            observaciones.append({
                "nivel": INFO, "asunto": "Horas extra",
                "mensaje": d["descripcion"],
                "accion": "Se cobra por tarifa; no requiere justificacion."})
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
            "accion": "Recotiza y autoriza con el cliente, o justifica la desviacion."})

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

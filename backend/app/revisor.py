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
    registro = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()
    if registro:
        respaldadas = {d.descripcion for d in registro.desviaciones if d.respaldada}

    # Las horas extra las genera el cliente al retener al equipo, llevan su
    # aviso preventivo y se cobran por tarifa: se informan, no frenan el cierre.
    INFORMATIVAS = {m.TipoDesviacion.HORAS_EXTRA.value}

    for d in comparativo["desviaciones"]:
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
    abiertos = [v for v in (
        db.query(m.AsignacionViatico)
        .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
        .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
        .filter(m.Equipo.servicio_id == servicio_id,
                m.AsignacionViatico.estatus.notin_(
                    (m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO,
                     m.EstatusViatico.CANCELADO)))
        .all())]
    if abiertos:
        quienes = sorted({v.persona.nombre for v in abiertos if v.persona})
        observaciones.append({
            "nivel": GRAVE, "asunto": "Viaticos sin cerrar",
            "mensaje": (f"{len(abiertos)} viatico(s) abiertos"
                        + (f": {', '.join(quienes)}" if quienes else "")),
            "accion": ("Cierralos cuando esten comprobados. Si alguien no "
                       "comprobo, cierralo con descuento: con el visto "
                       "bueno el gasto desaparece de su app y ya no puede "
                       "hacer nada.")})

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

    # --- reloj del consultor
    if registro:
        restante = (registro.limite_consultor - ahora).total_seconds() / 3600
        if restante < 0:
            # Vencido no significa que no se pueda facturar: el servicio debe
            # cobrarse igual. La consecuencia es la perdida de la comision.
            observaciones.append({
                "nivel": AVISO, "asunto": "Plazo vencido",
                "mensaje": f"Se pasaron {abs(restante):.1f} h del limite de 24 horas",
                "accion": "El servicio ya esta fuera de plazo; la comision del "
                          "consultor se pierde si no se cerro a tiempo."})
        elif restante < 6:
            observaciones.append({
                "nivel": AVISO, "asunto": "Plazo por vencer",
                "mensaje": f"Quedan {restante:.1f} h para cerrar y facturar",
                "accion": "Cierra pronto para no perder la comision."})

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

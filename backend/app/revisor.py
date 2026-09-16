"""Revisor automatico del cierre.

Acompana al consultor durante sus 24 horas: revisa el servicio y le avisa
lo que detecta mal para que lo corrija ANTES de enviarlo a finanzas.
El mismo revisor hace el primer filtro del comparativo para finanzas.

Hoy son reglas deterministas. Aqui es donde se conecta despues el modelo
de lenguaje corriendo en local, para que ademas redacte la explicacion y
detecte patrones que las reglas no ven.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app import cierre as motor
from app import models as m
from app import reloj

GRAVE = "corregir"
AVISO = "revisar"
INFO = "informativo"


def revisar(db: Session, servicio_id: int, ahora: datetime | None = None) -> dict:
    servicio = db.get(m.Servicio, servicio_id)
    # "Te quedan N horas para cerrar" se cuenta en el pais del servicio.
    ahora = reloj.ahora_del_servicio(db, servicio, ahora)
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

    return {
        "servicio": comparativo["servicio"],
        "revisado_en": ahora.isoformat(),
        "listo_para_finanzas": not graves,
        "resumen": ("Sin observaciones que corregir" if not graves
                    else f"{len(graves)} punto(s) por corregir antes de enviar a finanzas"),
        "observaciones": observaciones,
        "comparativo": comparativo,
    }

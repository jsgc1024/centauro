# -*- coding: utf-8 -*-
"""El cierre por mes del implantado (sesion 2 del cierre en dos relojes).

Decision de Salvador, 22 sep (PROPUESTA_CIERRE_24H.md, regla 8), y el
camino A del 23 sep: un cierre por mes de contrato en la misma tabla del
eventual, que sigue con uno por servicio y cuyo camino no cambia.

  * T0 del mes: el cierre de su ultimo dia trabajado (o la firma, si fue
    tarde). Todos los viaticos del mes vencen en T0 + 24 h; cerrar cada
    dia ya no abre plazo. Tambien arranca si el mes se completa porque
    se cancelaron sus ultimos dias, y al cancelar el implantado.
  * T1 y el visto bueno: los mismos relojes, con la revision del mes y
    el comparativo contra el contrato. La factura del mes sale con el
    visto bueno; finanzas aprueba el mes y se detona la comision del
    consultor por mes. El estatus del servicio no se mueve.
  * Un dia que se reabre o entra despues de T0 deshace el termino del
    mes; con el visto bueno dado ya no se puede.

Idempotente. Todas las escrituras al final.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    "models": B / "app/models.py",
    "cierre": B / "app/cierre.py",
    "revisor": B / "app/revisor.py",
    "comisiones": B / "app/comisiones.py",
    "facturacion": B / "app/facturacion.py",
    "rcierre": B / "app/routers/cierre.py",
    "operacion": B / "app/operacion.py",
    "implantado": B / "app/implantado.py",
    "servicios": B / "app/routers/servicios.py",
    "campo": B / "app/routers/campo.py",
    "rimplantados": B / "app/routers/implantados.py",
    "celery": B / "app/celery_app.py",
    "t_relojes": B / "tests/test_cierre_dos_relojes.py",
    "bitacora": RAIZ / "BITACORA.md",
}
NUEVOS = {'app/cierre_mes.py': '# -*- coding: utf-8 -*-\n"""El cierre por mes del implantado.\n\nDecision de Salvador, 22 de septiembre (PROPUESTA_CIERRE_24H.md, regla\n8); sesion 2 de tres. El implantado nunca termina: cuando cierra un mes,\nel siguiente ya esta abierto. Asi que la cadena de dos relojes no la\nrecorre el servicio sino el mes de contrato:\n\n* **T0** es el cierre del ultimo dia trabajado del mes: la hora real de\n  termino, o la firma si se cerro tarde --un plazo que nace vencido no\n  es un plazo--. Todos los viaticos del mes vencen en T0 + 24 h; cerrar\n  cada dia ya no abre plazo. El del relevado corre desde su relevo.\n* **T1** llega al vencer ese plazo, o antes si todo el dinero del mes ya\n  cerro: el consultor tiene 24 h para el visto bueno. Lo mueve la misma\n  tarea de cada cinco minutos que mueve al eventual.\n* **El visto bueno** manda la factura del mes, a los precios del\n  contrato. Finanzas valida y cierra el mes; si el visto bueno fue en\n  plazo se detona la comision del consultor por ese mes.\n\nUn cierre por mes, en la misma tabla que el del eventual (camino A,\ndecision del 23 sep): el eventual sigue con uno por servicio y su camino\nno cambia. El estatus del servicio tampoco se mueve --sigue en la calle\ncon el mes que corre--: la fase la lleva cada mes.\n\nUn dia que se reabre o que entra despues de T0 deshace el termino del\nmes mientras no haya visto bueno; despues ya no, porque la factura del\nmes salio con esos dias. Cancelar el implantado cierra, con lo\ntrabajado, cada mes que tenga algo que cerrar.\n"""\nimport calendar\nfrom datetime import date, datetime, timedelta\nfrom decimal import Decimal\n\nfrom fastapi import HTTPException\nfrom sqlalchemy.orm import Session\n\nfrom app import auditoria\nfrom app import cierre as motor\nfrom app import comisiones\nfrom app import facturacion\nfrom app import implantado as motor_implantado\nfrom app import models as m\nfrom app import nomina\nfrom app import reloj\nfrom app import viaticos as motor_viaticos\nfrom app.revisor import AVISO, GRAVE, INFO\n\nCERO = Decimal("0")\n\n# Con el visto bueno dado, la factura del mes ya salio o esta por salir:\n# ya no se reabre un dia ni entra uno nuevo. Los mismos del eventual.\nCON_VISTO_BUENO = (m.EstatusCierre.EN_REVISION_IA,\n                   m.EstatusCierre.ENVIADO_FINANZAS,\n                   m.EstatusCierre.APROBADO, m.EstatusCierre.FACTURADO)\n\n\ndef _d(valor) -> Decimal:\n    return Decimal(str(valor or 0))\n\n\ndef periodo(contrato: m.ContratoImplantado) -> str:\n    return f"{contrato.mes:02d}/{contrato.anio}"\n\n\ndef contrato_o_404(db: Session, contrato_id: int) -> m.ContratoImplantado:\n    contrato = db.get(m.ContratoImplantado, contrato_id)\n    if not contrato:\n        raise HTTPException(404, f"No existe el contrato {contrato_id}")\n    return contrato\n\n\ndef contrato_de(db: Session, jornada: m.Jornada | None\n                ) -> m.ContratoImplantado | None:\n    """El mes de contrato de un dia del implantado, si lo tiene."""\n    if jornada is None or jornada.equipo is None:\n        return None\n    return (db.query(m.ContratoImplantado)\n            .filter_by(servicio_id=jornada.equipo.servicio_id,\n                       anio=jornada.fecha.year, mes=jornada.fecha.month)\n            .first())\n\n\ndef cierre_de(db: Session, contrato: m.ContratoImplantado | None\n              ) -> m.Cierre | None:\n    if contrato is None:\n        return None\n    return db.query(m.Cierre).filter_by(contrato_id=contrato.id).first()\n\n\ndef _dias(db: Session, contrato: m.ContratoImplantado) -> list:\n    """Todos los dias del mes, los cancelados incluidos, leidos de la base.\n\n    De la base y no de la lista del equipo: quien llama acaba de cancelar\n    o de borrar un dia, y la lista cargada en memoria todavia lo tendria.\n    """\n    ultimo = calendar.monthrange(contrato.anio, contrato.mes)[1]\n    return (db.query(m.Jornada)\n            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)\n            .filter(m.Equipo.servicio_id == contrato.servicio_id,\n                    m.Jornada.fecha >= date(contrato.anio, contrato.mes, 1),\n                    m.Jornada.fecha <= date(contrato.anio, contrato.mes,\n                                            ultimo))\n            .order_by(m.Jornada.fecha).all())\n\n\ndef viaticos_del_mes(db: Session, contrato: m.ContratoImplantado) -> list:\n    """Todo el dinero del mes: el de sus dias --tambien el de quien cubrio\n    uno-- y el de los dias que se cancelaron con el dinero ya afuera."""\n    ids = [j.id for j in _dias(db, contrato)]\n    if not ids:\n        return []\n    return (db.query(m.AsignacionViatico)\n            .filter(m.AsignacionViatico.jornada_id.in_(ids)).all())\n\n\ndef viaticos_abiertos(db: Session, contrato: m.ContratoImplantado) -> int:\n    """Cuantos viaticos del mes siguen sin cerrar."""\n    return sum(1 for v in viaticos_del_mes(db, contrato)\n               if v.estatus not in motor.VIATICO_RESUELTO)\n\n\n# ------------------------------------------------------------ T0 del mes\n\ndef abrir(db: Session, contrato: m.ContratoImplantado,\n          abierto_en: datetime | None = None,\n          motivo: str = "termino") -> m.Cierre:\n    """El primer reloj del mes: las 24 horas del personal.\n\n    Todos los viaticos del mes reciben el mismo limite, T0 + 24 h. Se\n    respeta el que ya tenga uno --el del relevado, que corre desde su\n    relevo-- y el dinero que ya cerro, se devolvio o se cancelo no recibe\n    plazo: ya no esta afuera. Solo escribe; guarda quien llama.\n    """\n    existente = cierre_de(db, contrato)\n    if existente:\n        return existente\n\n    # En hora del pais del servicio, como el eventual: de este plazo\n    # depende la comision del consultor.\n    momento = reloj.ahora_del_servicio(db, contrato.servicio, abierto_en)\n    hasta = momento + timedelta(hours=motor.HORAS_PERSONAL)\n    cierre = m.Cierre(\n        servicio_id=contrato.servicio_id, contrato_id=contrato.id,\n        abierto_en=momento, comprobacion_hasta=hasta,\n        limite_consultor=hasta + timedelta(hours=motor.HORAS_CONSULTOR),\n        motivo_apertura=motivo)\n    db.add(cierre)\n\n    limite = motor_viaticos.limite_de_comprobacion(momento)\n    for viatico in viaticos_del_mes(db, contrato):\n        if (viatico.limite_comprobacion\n                or viatico.estatus in motor.VIATICO_RESUELTO):\n            continue\n        viatico.limite_comprobacion = limite\n    db.flush()\n    return cierre\n\n\ndef terminar_si_cerro_el_mes(db: Session,\n                             contrato: m.ContratoImplantado | None,\n                             registrado: datetime | None = None\n                             ) -> m.Cierre | None:\n    """Si al mes ya no le queda dia por trabajar, arranca su cierre.\n\n    Se llama al cerrar un dia --desde la app o a mano--, al cancelar uno\n    y desde la tarea de cada cinco minutos: lo que importa es que el mes\n    quedo completo, no por donde. Un dia cancelado no es pendiente.\n\n    T0 es la hora de termino del ultimo dia trabajado o `registrado`, lo\n    que sea despues: un dia firmado tarde no hace nacer vencido el plazo\n    (decision 4 de la propuesta). Sin dias trabajados ni dinero que haya\n    salido no hay nada que cerrar, y no arranca ningun reloj.\n    """\n    if contrato is None or cierre_de(db, contrato):\n        return None\n\n    # Quien llama acaba de mover un dia y todavia no guarda: sin esto la\n    # cuenta de abajo no lo ve. Es el mismo caso del eventual, ver\n    # `operacion.terminar_si_cerro_el_ultimo_dia`.\n    db.flush()\n    dias = _dias(db, contrato)\n    if any(j.estatus not in (m.EstatusJornada.TERMINADA,\n                             m.EstatusJornada.CANCELADA) for j in dias):\n        return None\n    trabajados = [j for j in dias if j.estatus == m.EstatusJornada.TERMINADA]\n    salio = [v for v in viaticos_del_mes(db, contrato)\n             if v.estatus != m.EstatusViatico.CANCELADO]\n    if not trabajados and not salio:\n        return None\n\n    momentos = [j.fin_real for j in trabajados if j.fin_real]\n    if registrado:\n        momentos.append(registrado)\n    return abrir(db, contrato, max(momentos) if momentos else None)\n\n\ndef abrir_los_que_terminaron(db: Session,\n                             ahora: datetime | None = None) -> list[str]:\n    """La red de la tarea de cada cinco minutos.\n\n    El mes que quedo completo sin que el cierre de un dia lo disparara\n    --se cancelaron o se borraron sus ultimos dias-- arranca aqui su\n    cierre, con T0 = ahora. Mira solo el mes en curso y el anterior, los\n    que no tienen cierre: un mes viejo sin nada que cerrar no se vuelve a\n    revisar cada cinco minutos para siempre. Devuelve los que abrio.\n    """\n    referencia = (ahora or datetime.now()).date()\n    anterior = (referencia.replace(day=1) - timedelta(days=1))\n    desde = anterior.year * 100 + anterior.month\n    hasta = referencia.year * 100 + referencia.month\n    clave = m.ContratoImplantado.anio * 100 + m.ContratoImplantado.mes\n    candidatos = (db.query(m.ContratoImplantado)\n                  .outerjoin(m.Cierre,\n                             m.Cierre.contrato_id == m.ContratoImplantado.id)\n                  .filter(m.Cierre.id.is_(None), clave >= desde,\n                          clave <= hasta)\n                  .all())\n    abiertos = []\n    for contrato in candidatos:\n        momento = reloj.ahora_del_servicio(db, contrato.servicio, ahora)\n        if terminar_si_cerro_el_mes(db, contrato, registrado=momento):\n            abiertos.append(f"{contrato.servicio.folio} {periodo(contrato)}")\n    db.commit()\n    return abiertos\n\n\ndef al_cancelar(db: Session, servicio: m.Servicio) -> list[m.Cierre]:\n    """Cancelar el implantado es un termino para cada mes con algo que\n    cerrar (regla 11 de la propuesta).\n\n    T0 es el momento de cancelar: los viaticos del mes que salieron\n    reciben su plazo y el consultor revisa el mes cancelado, que se\n    factura con lo trabajado. Los meses sin dias trabajados ni dinero\n    afuera --los que ya estaban abiertos para despues-- se quedan sin\n    relojes. El mes que ya tenia su cierre sigue el suyo.\n    """\n    db.flush()\n    momento = reloj.ahora_del_servicio(db, servicio)\n    abiertos = []\n    for contrato in (db.query(m.ContratoImplantado)\n                     .filter_by(servicio_id=servicio.id)\n                     .order_by(m.ContratoImplantado.anio,\n                               m.ContratoImplantado.mes).all()):\n        if cierre_de(db, contrato):\n            continue\n        trabajados = any(j.estatus == m.EstatusJornada.TERMINADA\n                         for j in _dias(db, contrato))\n        salio = any(v.estatus != m.EstatusViatico.CANCELADO\n                    for v in viaticos_del_mes(db, contrato))\n        if trabajados or salio:\n            abiertos.append(abrir(db, contrato, momento,\n                                  motivo="cancelacion"))\n    return abiertos\n\n\ndef con_visto_bueno(db: Session,\n                    contrato: m.ContratoImplantado | None) -> bool:\n    """Si el mes ya tiene visto bueno: su factura salio o esta por salir."""\n    cierre = cierre_de(db, contrato)\n    return bool(cierre and (cierre.facturado_en\n                            or cierre.estatus in CON_VISTO_BUENO))\n\n\ndef deshacer_termino(db: Session, contrato: m.ContratoImplantado | None,\n                     que: str) -> bool:\n    """Un dia que se reabre, o que entra, despues de T0.\n\n    Con el mes en comprobacion o sin visto bueno, el termino se deshace:\n    el cierre se borra con sus plazos y el mes vuelve a cerrar cuando\n    quede completo otra vez, con su nuevo ultimo dia. Con el visto bueno\n    dado ya no: la factura del mes salio, o esta por salir, con esos dias.\n    `que` completa el mensaje: "no se puede reabrir un dia".\n    """\n    cierre = cierre_de(db, contrato)\n    if cierre is None:\n        return False\n    if con_visto_bueno(db, contrato):\n        raise HTTPException(409, {\n            "mensaje": (f"El mes {periodo(contrato)} ya tiene visto bueno: "\n                        f"{que}"),\n            "que_hacer": ("Lo que cambie de ese mes se corrige con finanzas: "\n                          "la factura del mes ya salio con esos dias.")})\n    for viatico in viaticos_del_mes(db, contrato):\n        if viatico.limite_comprobacion == cierre.comprobacion_hasta:\n            viatico.limite_comprobacion = None\n    db.delete(cierre)\n    db.flush()\n    return True\n\n\n# ------------------------------------------------------------ el reloj del mes\n\ndef estado(db: Session, contrato: m.ContratoImplantado,\n           ahora: datetime | None = None) -> dict:\n    """El reloj del mes, para su panel y para la cartera.\n\n    Las mismas llaves que el del eventual (`cierre.estado`), mas el mes;\n    el limite y el momento van los dos en hora del pais del servicio.\n    """\n    ahora = reloj.ahora_del_servicio(db, contrato.servicio, ahora)\n    fila = cierre_de(db, contrato)\n    base = {"contrato_id": contrato.id, "periodo": periodo(contrato),\n            "momento": ahora.isoformat()}\n    if fila is None:\n        return {**base, "existe": False, "cierre_id": None, "estatus": None,\n                "fase": None, "abierto_en": None, "comprobacion_hasta": None,\n                "visto_bueno_desde": None, "limite": None,\n                "minutos_restantes": None, "viaticos_abiertos": None,\n                "motivo": None, "factura": None, "factura_error": None,\n                "dentro_de_plazo": None, "total": None}\n\n    def iso(momento):\n        return momento.isoformat() if momento else None\n\n    return {\n        **base,\n        "existe": True,\n        "cierre_id": fila.id,\n        "estatus": fila.estatus.value,\n        "fase": motor.FASES.get(fila.estatus),\n        "abierto_en": iso(fila.abierto_en),\n        "comprobacion_hasta": iso(fila.comprobacion_hasta),\n        "visto_bueno_desde": iso(fila.visto_bueno_desde),\n        "limite": iso(fila.limite_consultor),\n        "minutos_restantes": int(\n            (fila.limite_consultor - ahora).total_seconds() / 60),\n        "viaticos_abiertos": viaticos_abiertos(db, contrato),\n        "motivo": fila.motivo_apertura,\n        "factura": fila.factura_odoo,\n        "factura_error": fila.factura_error,\n        "dentro_de_plazo": fila.dentro_de_plazo,\n        # Lo que se mando a facturar; antes del visto bueno no hay cifra.\n        "total": str(fila.total_ejecutado) if fila.enviado_en else None,\n    }\n\n\ndef fases_de(db: Session, contratos: list) -> dict:\n    """La fase del cierre de varios meses de una vez: {contrato_id: fase}.\n    El mes sin cierre no aparece: todavia se esta trabajando."""\n    ids = [c.id for c in contratos]\n    if not ids:\n        return {}\n    return {c.contrato_id: motor.FASES.get(c.estatus)\n            for c in (db.query(m.Cierre)\n                      .filter(m.Cierre.contrato_id.in_(ids)).all())}\n\n\n# ------------------------------------------------------------ comparativo\n\ndef comparar(db: Session, contrato: m.ContratoImplantado) -> dict:\n    """Lo contratado del mes contra lo trabajado, y el dinero del mes.\n\n    Sale del corte (`implantado.cierre_del_mes`): los dias que tuvieron\n    gente y no se cancelaron, base y adicionales, a los precios del\n    contrato; la unidad va por mes completo. Se factura lo trabajado, no\n    lo contratado: un dia que el cliente cancelo no se cobra, y se dice.\n    Un dia que quedo sin cubrir, o un precio que falta, se tiene que\n    resolver antes del visto bueno.\n    """\n    corte = motor_implantado.cierre_del_mes(db, contrato.id)\n    base = corte["cliente"]["base"]\n    adicionales = corte["cliente"]["adicionales"]\n    precios = {"dia": _d(contrato.precio_dia_personal),\n               "dia_adicional": _d(contrato.precio_dia_adicional),\n               "unidad_mes": _d(contrato.precio_mes_vehiculo),\n               "mes_completo": _d(contrato.precio_mes_completo)}\n    mes_completo = (contrato.esquema\n                    == m.EsquemaCotizacionImplantado.MES_COMPLETO)\n    desviaciones, notas = [], []\n\n    if mes_completo:\n        contratado = trabajado = precios["mes_completo"]\n        desglose = {"mes_completo": trabajado}\n        if not contrato.precio_mes_completo:\n            desviaciones.append({\n                "tipo": m.TipoDesviacion.COBRO_MENOR.value,\n                "descripcion": (f"{periodo(contrato)}: el contrato no tiene "\n                                "el precio del mes completo"),\n                "monto": CERO})\n    else:\n        contratado = precios["dia"] * contrato.dias_base + precios["unidad_mes"]\n        desglose = {"dias_base": precios["dia"] * base,\n                    "dias_adicionales": precios["dia_adicional"] * adicionales,\n                    "vehiculo_mes": precios["unidad_mes"]}\n        trabajado = sum(desglose.values(), CERO)\n        if base and not contrato.precio_dia_personal:\n            desviaciones.append({\n                "tipo": m.TipoDesviacion.COBRO_MENOR.value,\n                "descripcion": (f"{periodo(contrato)}: el contrato no tiene "\n                                "precio por dia"),\n                "monto": CERO})\n        if adicionales and not contrato.precio_dia_adicional:\n            desviaciones.append({\n                "tipo": m.TipoDesviacion.COBRO_MENOR.value,\n                "descripcion": (f"{periodo(contrato)}: {adicionales} dia(s) "\n                                "adicional(es) sin precio en el contrato"),\n                "monto": CERO})\n        if base < contrato.dias_base:\n            notas.append(f"Se trabajaron {base} de {contrato.dias_base} dias "\n                         "base: se cobran los trabajados")\n    if adicionales:\n        notas.append(f"{adicionales} dia(s) adicional(es): "\n                     + ", ".join(corte["cliente"]["fechas_adicionales"]))\n\n    # El dia que existio y nadie cubrio: ni se cobra ni se paga, pero es\n    # un dia que el cliente pidio y no tuvo. Se explica antes de facturar.\n    for fecha in corte["dias_sin_cubrir"]:\n        desviaciones.append({\n            "tipo": m.TipoDesviacion.DIAS_DE_MENOS.value,\n            "descripcion": (f"{fecha}: el dia quedo sin cubrir; no se cobra "\n                            "ni se paga"),\n            "monto": CERO if mes_completo else -precios["dia"]})\n\n    viaticos = viaticos_del_mes(db, contrato)\n    asignado = sum((_d(v.monto_total) for v in viaticos), CERO)\n    comprobado = sum((_d(v.monto_comprobado) for v in viaticos), CERO)\n    devuelto = sum((_d(v.monto_devuelto) for v in viaticos), CERO)\n    descontado = sum((_d(v.monto_descontado) for v in viaticos), CERO)\n    absorbido = sum((_d(v.monto_absorbido) for v in viaticos), CERO)\n    for v in viaticos:\n        if v.cerrado_con_descuento:\n            quien = v.persona.nombre if v.persona else v.persona_id\n            notas.append(f"{quien}: cierre con descuento de "\n                         f"{_d(v.monto_descontado)}"\n                         + (f", {_d(v.monto_absorbido)} absorbido por la "\n                            "empresa" if _d(v.monto_absorbido) else ""))\n\n    return {\n        "servicio": contrato.servicio.folio,\n        "periodo": periodo(contrato),\n        "esquema": contrato.esquema.value,\n        "precios": precios,\n        "contratado": {"dias_base": contrato.dias_base,\n                       "importe": contratado},\n        "trabajado": {"dias_base": base, "dias_adicionales": adicionales,\n                      "fechas_adicionales":\n                          corte["cliente"]["fechas_adicionales"],\n                      "importe": trabajado, "desglose": desglose},\n        "diferencia": trabajado - contratado,\n        "viaticos": {"asignado": asignado, "comprobado": comprobado,\n                     "devuelto": devuelto,\n                     "pendiente": asignado - comprobado - devuelto,\n                     "descontado_al_personal": descontado,\n                     "absorbido_por_la_empresa": absorbido},\n        "desviaciones": desviaciones,\n        "notas": notas,\n        "sin_desviaciones": not desviaciones,\n    }\n\n\n# ------------------------------------------------------------ la revision\n\ndef revisar(db: Session, contrato: m.ContratoImplantado,\n            ahora: datetime | None = None) -> dict:\n    """La revision del mes antes del visto bueno.\n\n    Las mismas reglas que la del eventual (`revisor.revisar`), sobre los\n    dias y el dinero de este mes, y con el comparativo contra el contrato\n    en lugar de una cotizacion. Vive aparte a proposito: la del eventual\n    no se toca (el implantado no mueve nada del eventual).\n    """\n    servicio = contrato.servicio\n    ahora = reloj.ahora_del_servicio(db, servicio, ahora)\n    comparativo = comparar(db, contrato)\n    fila = cierre_de(db, contrato)\n    respaldadas = ({d.descripcion for d in fila.desviaciones if d.respaldada}\n                   if fila else set())\n    observaciones = []\n\n    for nota in comparativo["notas"]:\n        observaciones.append({\n            "nivel": INFO, "asunto": "Del mes", "mensaje": nota,\n            "accion": "Informativo."})\n    for d in comparativo["desviaciones"]:\n        if d["descripcion"] in respaldadas:\n            observaciones.append({\n                "nivel": INFO, "asunto": "Desviacion respaldada",\n                "mensaje": d["descripcion"],\n                "accion": "Ya tiene justificacion registrada, no escala."})\n            continue\n        observaciones.append({\n            "nivel": GRAVE, "asunto": d["tipo"], "mensaje": d["descripcion"],\n            "accion": ("Captura el precio en el contrato del mes: sin el, la "\n                       "factura sale en cero."\n                       if d["tipo"] == m.TipoDesviacion.COBRO_MENOR.value\n                       else "Justifica la desviacion o corrige el mes.")})\n\n    dias = _dias(db, contrato)\n    for j in dias:\n        if j.estatus != m.EstatusJornada.CANCELADA and not j.fin_real:\n            observaciones.append({\n                "nivel": GRAVE, "asunto": "Jornada sin termino",\n                "mensaje": f"{j.fecha}: el conductor no marco el fin del servicio",\n                "accion": "Pide a la central que registre el corte con "\n                          "justificacion."})\n\n    # El dinero que nadie cerro. Grave por lo mismo que en el eventual:\n    # con el visto bueno el gasto desaparece de la app de quien lo debe.\n    abiertos = [v for v in viaticos_del_mes(db, contrato)\n                if v.estatus not in motor.VIATICO_RESUELTO]\n    if abiertos:\n        quienes = sorted({v.persona.nombre for v in abiertos if v.persona})\n        observaciones.append({\n            "nivel": GRAVE, "asunto": "Viaticos sin cerrar",\n            "mensaje": (f"{len(abiertos)} viatico(s) abiertos"\n                        + (f": {\', \'.join(quienes)}" if quienes else "")),\n            "accion": ("Cierralos cuando esten comprobados. Si alguien no "\n                       "comprobo, cierralo con descuento: con el visto "\n                       "bueno el gasto desaparece de su app y ya no puede "\n                       "hacer nada.")})\n\n    ids = [j.id for j in dias]\n    if ids:\n        for h in (db.query(m.Hito)\n                  .filter(m.Hito.jornada_id.in_(ids),\n                          m.Hito.requiere_revision.is_(True)).all()):\n            observaciones.append({\n                "nivel": AVISO, "asunto": "Marca fuera de horario sin revisar",\n                "mensaje": (f"{h.tipo.value} del {h.marcado_en:%d/%m %H:%M} "\n                            "sigue marcado para revision de la central"),\n                "accion": "La central debe validarla o ajustarla antes del "\n                          "cierre."})\n        alertas = (db.query(m.Alerta)\n                   .filter(m.Alerta.jornada_id.in_(ids),\n                           m.Alerta.atendida.is_(False)).count())\n        if alertas:\n            observaciones.append({\n                "nivel": AVISO, "asunto": "Alertas sin atender",\n                "mensaje": f"{alertas} alerta(s) de la central siguen abiertas",\n                "accion": "Cierra cada alerta con su resolucion."})\n\n    # Los dos relojes del mes.\n    if fila is None:\n        observaciones.append({\n            "nivel": AVISO, "asunto": "El mes sigue abierto",\n            "mensaje": "El cierre del mes arranca al cerrar su ultimo dia "\n                       "trabajado.",\n            "accion": "Nada que hacer todavia."})\n    elif fila.estatus == m.EstatusCierre.ABIERTO:\n        hasta = fila.comprobacion_hasta\n        observaciones.append({\n            "nivel": AVISO, "asunto": "Comprobacion en curso",\n            "mensaje": (f"El personal tiene hasta el {hasta:%d/%m %H:%M} "\n                        "para comprobar sus viaticos del mes" if hasta else\n                        "El personal esta comprobando sus viaticos del mes"),\n            "accion": "El visto bueno se abre cuando venza ese plazo, o "\n                      "antes si todos los viaticos del mes ya cerraron."})\n    else:\n        restante = (fila.limite_consultor - ahora).total_seconds() / 3600\n        if restante < 0:\n            observaciones.append({\n                "nivel": AVISO, "asunto": "Plazo vencido",\n                "mensaje": (f"Se pasaron {abs(restante):.1f} h del limite de "\n                            "24 horas"),\n                "accion": "El mes se factura igual; la comision del mes se "\n                          "pierde si no se cerro a tiempo."})\n        elif restante < 6:\n            observaciones.append({\n                "nivel": AVISO, "asunto": "Plazo por vencer",\n                "mensaje": f"Quedan {restante:.1f} h para cerrar y facturar",\n                "accion": "Cierra pronto para no perder la comision."})\n\n    graves = [o for o in observaciones if o["nivel"] == GRAVE]\n    return {\n        "servicio": servicio.folio,\n        "periodo": periodo(contrato),\n        "revisado_en": ahora.isoformat(),\n        "cierre": estado(db, contrato, ahora),\n        "listo_para_finanzas": not graves,\n        "resumen": ("Sin observaciones que corregir" if not graves\n                    else f"{len(graves)} punto(s) por corregir antes de "\n                         "enviar a finanzas"),\n        "observaciones": observaciones,\n        "comparativo": comparativo,\n    }\n\n\n# ------------------------------------------------------------ visto bueno y finanzas\n\ndef enviar_a_finanzas(db: Session, cierre: m.Cierre, usuario: m.Usuario,\n                      ahora: datetime | None = None) -> dict:\n    """El visto bueno del mes: su termino general.\n\n    El mismo recorrido que el del eventual (`routers/cierre.py`), con la\n    revision del mes: solo desde T1, sin viaticos del mes abiertos y con\n    el comparativo contra el contrato. En plazo si llega antes de T1 +\n    24 h; de eso depende la comision. La factura del mes sale en ese\n    momento; si Odoo no contesta, el mes queda por facturar. El servicio\n    no cambia de estatus: sigue en la calle con el mes que corre.\n    """\n    contrato = cierre.contrato\n    momento = reloj.ahora_del_servicio(db, cierre.servicio, ahora)\n\n    # Si ya llego T1 --o todo el dinero del mes ya cerro-- y la tarea de\n    # cada cinco minutos no ha pasado, se avanza aqui y se guarda.\n    if motor.avanzar(db, cierre, momento):\n        db.commit()\n\n    if cierre.estatus not in (m.EstatusCierre.SIN_VISTO_BUENO,\n                              m.EstatusCierre.DEVUELTO_A_OPERACION):\n        raise HTTPException(409, {\n            "mensaje": ("Todavia corre la comprobacion de viaticos del personal"\n                        if cierre.estatus == m.EstatusCierre.ABIERTO\n                        else f"El cierre esta en {cierre.estatus.value}"),\n            "hasta": (cierre.comprobacion_hasta.isoformat()\n                      if cierre.comprobacion_hasta else None),\n            "observaciones": [],\n        })\n\n    revision = revisar(db, contrato, momento)\n    if not revision["listo_para_finanzas"]:\n        raise HTTPException(409, {\n            "mensaje": "Hay puntos por corregir antes de enviar a finanzas",\n            "observaciones": [o for o in revision["observaciones"]\n                              if o["nivel"] == GRAVE],\n        })\n\n    comparativo = revision["comparativo"]\n    cierre.total_cotizado = comparativo["contratado"]["importe"]\n    cierre.total_ejecutado = comparativo["trabajado"]["importe"]\n    cierre.estatus = m.EstatusCierre.ENVIADO_FINANZAS\n    cierre.enviado_en = momento\n    cierre.cerrado_por_id = usuario.persona_id\n    cierre.dentro_de_plazo = momento <= cierre.limite_consultor\n    auditoria.registrar(db, usuario, cierre.servicio, "enviar a finanzas",\n                        f"{periodo(contrato)}: contratado "\n                        f"{cierre.total_cotizado}, trabajado "\n                        f"{cierre.total_ejecutado}, "\n                        f"{\'en plazo\' if cierre.dentro_de_plazo else \'FUERA DE PLAZO\'}")\n\n    # Lo pagado cada semana contra lo que corresponde al corte del mes:\n    # las diferencias van a la nomina siguiente, como en el eventual.\n    ajustes = nomina.diferencias_del_servicio(db, cierre.servicio_id,\n                                              usuario.persona_id)\n    if ajustes["ajustes_generados"]:\n        auditoria.registrar(\n            db, usuario, cierre.servicio, "ajustes de nomina",\n            f"{len(ajustes[\'ajustes_generados\'])} diferencias a la "\n            f"siguiente nomina")\n    db.commit()\n\n    # La factura del mes, despues de guardar: un Odoo caido no deshace el\n    # visto bueno, el mes se queda por facturar con el error a la vista.\n    factura = facturacion.enviar(db, cierre)\n    db.commit()\n\n    return {"resultado": "enviado a finanzas", "cierre_id": cierre.id,\n            "periodo": periodo(contrato),\n            "factura": factura,\n            "dentro_de_plazo": cierre.dentro_de_plazo,\n            "comision_consultor": ("se detona con la validacion de finanzas"\n                                   if cierre.dentro_de_plazo\n                                   else "se pierde por cierre fuera de plazo"),\n            "ajustes_de_nomina": ajustes["ajustes_generados"]}\n\n\ndef aprobar(db: Session, cierre: m.Cierre, usuario: m.Usuario) -> dict:\n    """Finanzas valida el mes.\n\n    El mes queda aprobado; el servicio no se cierra, sigue vivo con el mes\n    que corre. Si el visto bueno fue en plazo se detona la comision del\n    consultor por ese mes. La rentabilidad del mes viene despues, con la\n    moneda.\n    """\n    cierre.estatus = m.EstatusCierre.APROBADO\n    cierre.aprobado_en = datetime.now()\n    cierre.aprobado_por_id = usuario.persona_id\n    auditoria.registrar(db, usuario, cierre.servicio, "aprobar cierre",\n                        f"{periodo(cierre.contrato)}, validado por finanzas")\n    db.commit()\n\n    comision = None\n    if cierre.servicio.consultor_id:\n        c = comisiones.generar_del_mes(db, cierre)\n        comision = {"comision_id": c.id, "consultor": c.consultor.nombre,\n                    "base": c.base, "porcentaje": float(c.porcentaje),\n                    "monto": c.monto, "estatus": c.estatus.value,\n                    "motivo": c.motivo}\n\n    # Solo reintenta si el envio del visto bueno fallo; si ya salio, el\n    # mes pasa a facturado.\n    factura = facturacion.enviar(db, cierre)\n    db.commit()\n\n    return {"resultado": "aprobado", "cierre_id": cierre.id,\n            "periodo": periodo(cierre.contrato),\n            "comision_consultor": comision,\n            "factura": factura,\n            "rentabilidad": None}\n\n\ndef armar_factura(db: Session, cierre: m.Cierre) -> dict:\n    """La factura del mes, renglon por renglon, a los precios del contrato.\n\n    El folio de Centauro y el mes viajan siempre: son la llave para\n    conciliar las dos bases el dia que no cuadren. Los viaticos por\n    comprobar no van todavia --tampoco en la del eventual--: entran con\n    la factura en Odoo (etapa 4), para los dos a la vez.\n    """\n    contrato = cierre.contrato\n    servicio = cierre.servicio\n    comparativo = comparar(db, contrato)\n    trabajado = comparativo["trabajado"]\n    precios = comparativo["precios"]\n    de_que = periodo(contrato)\n\n    conceptos = []\n    if contrato.esquema == m.EsquemaCotizacionImplantado.MES_COMPLETO:\n        conceptos.append({\n            "tipo": "mes_completo",\n            "descripcion": f"Servicio implantado {de_que}, mes completo",\n            "cantidad": 1, "precio": str(precios["mes_completo"]),\n            "importe": str(precios["mes_completo"])})\n    else:\n        if trabajado["dias_base"]:\n            conceptos.append({\n                "tipo": "dias_base",\n                "descripcion": f"Servicio implantado {de_que}, dias de servicio",\n                "cantidad": trabajado["dias_base"],\n                "precio": str(precios["dia"]),\n                "importe": str(trabajado["desglose"]["dias_base"])})\n        if trabajado["dias_adicionales"]:\n            conceptos.append({\n                "tipo": "dias_adicionales",\n                "descripcion": f"Dias adicionales {de_que}",\n                "cantidad": trabajado["dias_adicionales"],\n                "precio": str(precios["dia_adicional"]),\n                "importe": str(trabajado["desglose"]["dias_adicionales"]),\n                "fechas": trabajado["fechas_adicionales"]})\n        if precios["unidad_mes"]:\n            conceptos.append({\n                "tipo": "vehiculo_mes",\n                "descripcion": f"Unidad {de_que}, mes completo",\n                "cantidad": 1, "precio": str(precios["unidad_mes"]),\n                "importe": str(precios["unidad_mes"])})\n\n    pais = db.get(m.Pais, servicio.pais_id)\n    cliente = servicio.cliente\n    return {\n        "referencia": f"{servicio.folio} {de_que}",\n        "cierre_id": cierre.id,\n        "periodo": de_que,\n        "cliente": {"id_odoo": cliente.odoo_id if cliente else None,\n                    "nombre": cliente.nombre if cliente else None},\n        "moneda": pais.moneda_local.value if pais else None,\n        "fecha": (cierre.enviado_en or cierre.aprobado_en\n                  or datetime.now()).date().isoformat(),\n        "total": str(trabajado["importe"]),\n        "conceptos": conceptos,\n    }\n', 'migrations/versions/d4f1b8e2a6c9_cierre_por_mes.py': '"""El cierre por mes del implantado.\n\nSesion 2 del cierre en dos relojes (PROPUESTA_CIERRE_24H.md, regla 8;\nseccion 56 de la bitacora). El cierre deja de ser uno por servicio: uno\npor servicio en el eventual y uno por mes de contrato en el implantado.\nLa comision del consultor, igual: la del implantado es por mes.\n\nLa regla del eventual no se afloja: sigue habiendo a lo mas un cierre y\nuna comision por servicio cuando no son de un mes, ahora como indice\nparcial en lugar de la restriccion de columna.\n\nRevision ID: d4f1b8e2a6c9\nRevises: c3e9a5d1f7b2\n"""\nfrom typing import Sequence, Union\n\nimport sqlalchemy as sa\nfrom alembic import op\n\nrevision: str = "d4f1b8e2a6c9"\ndown_revision: Union[str, None] = "c3e9a5d1f7b2"\nbranch_labels: Union[str, Sequence[str], None] = None\ndepends_on: Union[str, Sequence[str], None] = None\n\n\ndef _quitar_unica(tabla: str, columnas: list) -> None:\n    """Quita la restriccion unica de esas columnas, se llame como se llame.\n\n    Se crearon sin nombre, asi que el nombre lo puso Postgres; se busca\n    por las columnas para no depender de como lo haya escrito.\n    """\n    nombre = op.get_bind().execute(sa.text(\n        "SELECT c.conname FROM pg_constraint c "\n        "JOIN pg_class t ON t.oid = c.conrelid "\n        "WHERE t.relname = :tabla AND c.contype = \'u\' "\n        "AND ARRAY(SELECT a.attname::text FROM unnest(c.conkey) AS k(n) "\n        "          JOIN pg_attribute a "\n        "            ON a.attrelid = t.oid AND a.attnum = k.n "\n        "          ORDER BY 1) = CAST(:columnas AS text[])"),\n        {"tabla": tabla, "columnas": sorted(columnas)}).scalar()\n    if nombre:\n        op.drop_constraint(nombre, tabla, type_="unique")\n\n\ndef upgrade() -> None:\n    # El cierre: el mes de contrato, en el implantado.\n    op.add_column("cierre", sa.Column("contrato_id", sa.Integer(),\n                                      nullable=True))\n    op.create_foreign_key("cierre_contrato_id_fkey", "cierre",\n                          "contrato_implantado", ["contrato_id"], ["id"])\n    op.create_unique_constraint("cierre_contrato_id_key", "cierre",\n                                ["contrato_id"])\n    _quitar_unica("cierre", ["servicio_id"])\n    op.create_index("uq_cierre_del_eventual", "cierre", ["servicio_id"],\n                    unique=True,\n                    postgresql_where=sa.text("contrato_id IS NULL"))\n\n    # La comision del consultor: la del implantado es por mes.\n    op.add_column("comision_consultor", sa.Column("contrato_id",\n                                                  sa.Integer(),\n                                                  nullable=True))\n    op.create_foreign_key("comision_consultor_contrato_id_fkey",\n                          "comision_consultor", "contrato_implantado",\n                          ["contrato_id"], ["id"])\n    _quitar_unica("comision_consultor", ["servicio_id", "consultor_id"])\n    op.create_index("uq_comision_del_servicio", "comision_consultor",\n                    ["servicio_id", "consultor_id"], unique=True,\n                    postgresql_where=sa.text("contrato_id IS NULL"))\n    op.create_index("uq_comision_del_mes", "comision_consultor",\n                    ["contrato_id", "consultor_id"], unique=True,\n                    postgresql_where=sa.text("contrato_id IS NOT NULL"))\n\n\ndef downgrade() -> None:\n    # Lo que era de un mes no cabe en la regla de antes: se va.\n    op.drop_index("uq_comision_del_mes", table_name="comision_consultor")\n    op.drop_index("uq_comision_del_servicio", table_name="comision_consultor")\n    op.execute("DELETE FROM comision_consultor WHERE contrato_id IS NOT NULL")\n    op.drop_column("comision_consultor", "contrato_id")\n    op.create_unique_constraint(\n        "comision_consultor_servicio_id_consultor_id_key",\n        "comision_consultor", ["servicio_id", "consultor_id"])\n\n    op.drop_index("uq_cierre_del_eventual", table_name="cierre")\n    op.execute("DELETE FROM desviacion WHERE cierre_id IN "\n               "(SELECT id FROM cierre WHERE contrato_id IS NOT NULL)")\n    op.execute("DELETE FROM cierre WHERE contrato_id IS NOT NULL")\n    op.drop_column("cierre", "contrato_id")\n    op.create_unique_constraint("cierre_servicio_id_key", "cierre",\n                                ["servicio_id"])\n', 'tests/test_cierre_mes.py': '# -*- coding: utf-8 -*-\n"""El cierre por mes del implantado.\n\nDecision de Salvador, 22 de septiembre (PROPUESTA_CIERRE_24H.md, regla\n8), y el camino A del 23: un cierre por mes de contrato en la misma\ntabla del eventual. Seccion 56 de la bitacora.\n\nTodo pasa en septiembre de 2029, que acaba en domingo: del lunes 24 al\nviernes 28 son cinco dias de servicio. La central cierra los dias a mano\ncon `ahora` en la mano --a las 21:00, una hora despues del termino--,\nasi que nada depende del reloj de la maquina.\n"""\nfrom datetime import date, datetime, timedelta\n\nH24 = timedelta(hours=24)\nMOTIVO = "El equipo cerro por telefono; confirmado con el cliente"\nDIAS = [date(2029, 9, d) for d in (24, 25, 26, 27, 28)]\nSABADO = date(2029, 9, 29)\nDOMINGO = date(2029, 9, 30)\n\n\ndef _alta(cliente, sesion, datos, inicio=DIAS[0]):\n    """Un implantado de lunes a viernes, Juan con la Suburban, del 24 al\n    fin de septiembre de 2029, con Ana de consultora."""\n    r = cliente.post("/implantados", headers=sesion("consultor"), json={\n        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],\n        "plaza_id": datos["cdmx"]["id"],\n        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",\n        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",\n        "consultor_id": datos["personal"]["Ana Solis"]["id"],\n        "fecha_inicio": str(inicio), "dias_servicio": "lunes_viernes",\n        "modalidad_id": datos["modalidades"]["full_day"]["id"],\n        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],\n                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],\n                      "vehiculo_id": datos["suburban"]["id"]}],\n        "unidades": [datos["suburban"]["id"]],\n        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000",\n        "precio_dia_adicional": "3500",\n    })\n    assert r.status_code == 201, r.text\n    return r.json()\n\n\ndef _jornadas(cliente, sesion, servicio_id, anio=2029, mes=9):\n    """{fecha: jornada_id} de los dias del mes."""\n    panel = cliente.get(f"/implantados/{servicio_id}/mes/{anio}/{mes}",\n                        headers=sesion("consultor"))\n    assert panel.status_code == 200, panel.text\n    return {date.fromisoformat(d["fecha"]): d["jornada_id"]\n            for d in panel.json()["dias"]}\n\n\ndef _a_las_21(dia):\n    return datetime.combine(dia, datetime.min.time()) + timedelta(hours=21)\n\n\ndef _cerrar(cliente, sesion, jornada_id, dia, ahora=None):\n    """La central cierra el dia a mano; si no se dice cuando, una hora\n    despues de su termino."""\n    r = cliente.post(f"/operacion/jornadas/{jornada_id}/cerrar-a-mano",\n                     headers=sesion("central"), json={"justificacion": MOTIVO},\n                     params={"ahora": (ahora or _a_las_21(dia)).isoformat()})\n    assert r.status_code == 200, r.text\n\n\ndef _cerrar_mes(cliente, sesion, servicio_id, dias=DIAS):\n    jornadas = _jornadas(cliente, sesion, servicio_id)\n    for dia in dias:\n        _cerrar(cliente, sesion, jornadas[dia], dia)\n    return jornadas\n\n\ndef _viatico(cliente, sesion, datos, jornada_id, monto="900"):\n    r = cliente.post("/viaticos/asignar", headers=sesion("consultor"), json={\n        "jornada_id": jornada_id,\n        "persona_id": datos["personal"]["Juan Ramirez"]["id"],\n        "conceptos": [{"concepto": "alimentos", "monto": monto,\n                       "origen": "tabulador"}]})\n    assert r.status_code in (200, 201), r.text\n    return r.json()["id"]\n\n\ndef _cierre(contrato_id):\n    from app import models as m\n    from app.db import SessionLocal\n    with SessionLocal() as db:\n        c = db.query(m.Cierre).filter_by(contrato_id=contrato_id).first()\n        if not c:\n            return None\n        return {"id": c.id, "estatus": c.estatus.value,\n                "abierto_en": c.abierto_en,\n                "comprobacion_hasta": c.comprobacion_hasta,\n                "visto_bueno_desde": c.visto_bueno_desde,\n                "limite": c.limite_consultor, "motivo": c.motivo_apertura,\n                "servicio_id": c.servicio_id,\n                "total_cotizado": float(c.total_cotizado or 0),\n                "total_ejecutado": float(c.total_ejecutado or 0)}\n\n\ndef _limites(vids):\n    from app import models as m\n    from app.db import SessionLocal\n    with SessionLocal() as db:\n        return [db.get(m.AsignacionViatico, v).limite_comprobacion\n                for v in vids]\n\n\ndef _avanzar(cierre_id, ahora):\n    """Lo que hace la tarea de cada cinco minutos, a una hora dada."""\n    from app import cierre as motor\n    from app import models as m\n    from app.db import SessionLocal\n    with SessionLocal() as db:\n        movio = motor.avanzar(db, db.get(m.Cierre, cierre_id), ahora)\n        db.commit()\n        return movio\n\n\ndef _estatus(cliente, sesion, servicio_id):\n    r = cliente.get(f"/servicios/{servicio_id}", headers=sesion("consultor"))\n    assert r.status_code == 200, r.text\n    return r.json()["estatus"]\n\n\n# El servicio no recorre la cadena: la recorre cada mes.\nDEL_EVENTUAL = {"terminado", "sin_visto_bueno", "en_facturacion", "cerrado"}\n\n\n# ------------------------------------------------------------ T0 del mes\n\ndef test_el_mes_arranca_su_cierre_al_cerrar_su_ultimo_dia(cliente, sesion,\n                                                          datos):\n    """Cerrar los dias de en medio ya no abre plazo a nadie. Al cerrar el\n    viernes 28 --el mes acaba en domingo-- arranca el cierre del mes:\n    todos sus viaticos vencen en T0 + 24 h y el servicio no se mueve."""\n    alta = _alta(cliente, sesion, datos)\n    sid, contrato = alta["servicio_id"], alta["contrato_id"]\n    jornadas = _jornadas(cliente, sesion, sid)\n    assert sorted(jornadas) == DIAS, "el mes son sus cinco dias habiles"\n    vids = [_viatico(cliente, sesion, datos, jornadas[d])\n            for d in (DIAS[0], DIAS[3])]\n\n    for dia in DIAS[:4]:\n        _cerrar(cliente, sesion, jornadas[dia], dia)\n    assert _limites(vids) == [None, None], \\\n        "el plazo del implantado ya no es del dia: es del mes"\n    assert _cierre(contrato) is None\n\n    _cerrar(cliente, sesion, jornadas[DIAS[4]], DIAS[4])\n    t0 = _a_las_21(DIAS[4])\n    c = _cierre(contrato)\n    assert c["estatus"] == "abierto" and c["motivo"] == "termino"\n    assert c["servicio_id"] == sid\n    assert c["abierto_en"] == t0, "T0 es la firma del ultimo dia"\n    assert c["comprobacion_hasta"] == t0 + H24\n    assert c["limite"] == t0 + 2 * H24, "provisional: T1 todavia no llega"\n    assert _limites(vids) == [t0 + H24] * 2, "todos vencen a la misma hora"\n    assert _estatus(cliente, sesion, sid) not in DEL_EVENTUAL\n\n    # Su panel y la cartera lo dicen.\n    h = sesion("consultor")\n    estado = cliente.get(f"/implantados/contratos/{contrato}/cierre/estado",\n                         headers=h).json()\n    assert estado["fase"] == "comprobacion" and estado["periodo"] == "09/2029"\n    assert estado["viaticos_abiertos"] == 2\n    panel = cliente.get(f"/implantados/{sid}/mes/2029/9", headers=h).json()\n    assert panel["cierre"]["cierre_id"] == c["id"]\n    ficha = next(x for x in cliente.get("/implantados", headers=h).json()\n                 if x["servicio_id"] == sid)\n    assert [p["fase"] for p in ficha["periodos"]] == ["comprobacion"]\n\n    # Y el eventual no puede abrir el suyo: el implantado cierra por mes.\n    r = cliente.post(f"/cierre/servicio/{sid}/abrir", headers=h)\n    assert r.status_code == 409, r.text\n\n\ndef test_sin_dinero_afuera_el_consultor_arranca_y_la_factura_es_del_mes(\n        cliente, sesion, datos, monkeypatch):\n    """Sin viaticos no hay nada que esperar: T1 llega en cuanto corre el\n    reloj. El visto bueno manda la factura del mes --aqui sin Odoo, queda\n    por facturar con su mes--; finanzas aprueba el mes, el servicio sigue\n    vivo y la comision del consultor es de ese mes: 1 por ciento."""\n    from app import facturacion\n    monkeypatch.setattr(facturacion.settings, "odoo_url", "")\n\n    alta = _alta(cliente, sesion, datos)\n    sid, contrato = alta["servicio_id"], alta["contrato_id"]\n    _cerrar_mes(cliente, sesion, sid)\n    t0 = _a_las_21(DIAS[4])\n    c = _cierre(contrato)\n    assert _avanzar(c["id"], t0 + timedelta(hours=1)) is True\n    c = _cierre(contrato)\n    assert c["estatus"] == "sin_visto_bueno"\n    assert c["visto_bueno_desde"] == t0 + timedelta(hours=1)\n    assert c["limite"] == t0 + timedelta(hours=25)\n    assert _estatus(cliente, sesion, sid) not in DEL_EVENTUAL\n\n    h = sesion("consultor")\n    revision = cliente.get(f"/implantados/contratos/{contrato}/cierre/revision",\n                           headers=h,\n                           params={"ahora": (t0 + timedelta(hours=2)).isoformat()})\n    assert revision.status_code == 200, revision.text\n    assert revision.json()["listo_para_finanzas"] is True, revision.json()\n    comparativo = revision.json()["comparativo"]\n    assert comparativo["trabajado"]["dias_base"] == 5\n    assert float(comparativo["trabajado"]["importe"]) == 5 * 2900 + 66000\n\n    envio = cliente.post(f"/cierre/{c[\'id\']}/enviar-finanzas", headers=h,\n                         params={"ahora": (t0 + timedelta(hours=2)).isoformat()})\n    assert envio.status_code == 200, envio.text\n    assert envio.json()["periodo"] == "09/2029"\n    assert envio.json()["dentro_de_plazo"] is True\n    assert envio.json()["factura"]["resultado"] == "sin conexion"\n    c = _cierre(contrato)\n    assert c["estatus"] == "enviado_finanzas"\n    assert c["total_ejecutado"] == 5 * 2900 + 66000\n    assert c["total_cotizado"] == 5 * 2900 + 66000\n    assert _estatus(cliente, sesion, sid) not in DEL_EVENTUAL\n\n    bandeja = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))\n    suyo = next(x for x in bandeja.json()["por_facturar"]\n                if x["cierre_id"] == c["id"])\n    assert suyo["periodo"] == "09/2029" and suyo["error"]\n\n    # La factura del mes: renglon por renglon, con el folio y el mes.\n    from app import models as m\n    from app.db import SessionLocal\n    with SessionLocal() as db:\n        cuerpo = facturacion.armar(db, db.get(m.Cierre, c["id"]))\n    assert cuerpo["referencia"].endswith(" 09/2029")\n    assert cuerpo["total"] == "80500.00"\n    assert [(x["tipo"], x["cantidad"]) for x in cuerpo["conceptos"]] == \\\n        [("dias_base", 5), ("vehiculo_mes", 1)]\n\n    r = cliente.post(f"/cierre/{c[\'id\']}/aprobar", headers=sesion("finanzas"))\n    assert r.status_code == 200, r.text\n    comision = r.json()["comision_consultor"]\n    assert comision["porcentaje"] == 1.0\n    assert float(comision["monto"]) == 805.0\n    assert comision["estatus"] == "generada"\n    assert _cierre(contrato)["estatus"] == "aprobado"\n    assert _estatus(cliente, sesion, sid) not in DEL_EVENTUAL, \\\n        "aprobar un mes no cierra el implantado"\n\n\ndef test_con_dinero_afuera_el_mes_espera_a_su_personal(cliente, sesion, datos):\n    """Con un viatico del mes sin cerrar, a las 23 h no pasa nada y el\n    consultor no se puede adelantar; a las 24 abre el visto bueno, pero\n    no se da con ese dinero abierto."""\n    alta = _alta(cliente, sesion, datos)\n    sid, contrato = alta["servicio_id"], alta["contrato_id"]\n    jornadas = _jornadas(cliente, sesion, sid)\n    _viatico(cliente, sesion, datos, jornadas[DIAS[2]])\n    _cerrar_mes(cliente, sesion, sid)\n    t0 = _a_las_21(DIAS[4])\n    c = _cierre(contrato)\n    h = sesion("consultor")\n\n    assert _avanzar(c["id"], t0 + timedelta(hours=23)) is False\n    envio = cliente.post(f"/cierre/{c[\'id\']}/enviar-finanzas", headers=h,\n                         params={"ahora": (t0 + timedelta(hours=23)).isoformat()})\n    assert envio.status_code == 409, envio.text\n    assert "comprobacion" in envio.json()["detail"]["mensaje"].lower()\n\n    assert _avanzar(c["id"], t0 + H24) is True\n    assert _cierre(contrato)["limite"] == t0 + 2 * H24\n    envio = cliente.post(f"/cierre/{c[\'id\']}/enviar-finanzas", headers=h,\n                         params={"ahora": (t0 + H24 + timedelta(hours=1)).isoformat()})\n    assert envio.status_code == 409, envio.text\n    asuntos = [o["asunto"] for o in envio.json()["detail"]["observaciones"]]\n    assert "Viaticos sin cerrar" in asuntos, asuntos\n\n\n# ------------------------------------------------------------ un dia despues de T0\n\ndef test_el_sabado_que_entra_despues_de_t0_mueve_el_termino(cliente, sesion,\n                                                           datos):\n    """El cliente pide el sabado cuando el viernes ya cerro: el termino\n    del mes se deshace y vuelve a arrancar al cerrar el sabado, que se\n    cobra aparte. Con el visto bueno dado ya no entra otro dia."""\n    alta = _alta(cliente, sesion, datos)\n    sid, contrato = alta["servicio_id"], alta["contrato_id"]\n    jornadas = _jornadas(cliente, sesion, sid)\n    vid = _viatico(cliente, sesion, datos, jornadas[DIAS[0]])\n    _cerrar_mes(cliente, sesion, sid)\n    assert _cierre(contrato) is not None\n    h = sesion("consultor")\n\n    r = cliente.post(f"/implantados/contratos/{contrato}/dias-adicionales",\n                     json={"fecha": str(SABADO)}, headers=h)\n    assert r.status_code == 200, r.text\n    assert _cierre(contrato) is None, "el mes volvio a tener un dia por trabajar"\n    assert _limites([vid]) == [None], "el plazo se fue con el termino"\n\n    _cerrar(cliente, sesion, _jornadas(cliente, sesion, sid)[SABADO], SABADO)\n    c = _cierre(contrato)\n    assert c["abierto_en"] == _a_las_21(SABADO), "T0 paso al sabado"\n    assert _limites([vid]) == [_a_las_21(SABADO) + H24]\n\n    # Ese dinero nunca salio: se cancela. Sin nada afuera el consultor da\n    # el visto bueno, y el domingo ya no entra.\n    from app import models as m\n    from app.db import SessionLocal\n    with SessionLocal() as db:\n        db.get(m.AsignacionViatico, vid).estatus = m.EstatusViatico.CANCELADO\n        db.commit()\n    ahora = (_a_las_21(SABADO) + timedelta(hours=1)).isoformat()\n    envio = cliente.post(f"/cierre/{c[\'id\']}/enviar-finanzas", headers=h,\n                         params={"ahora": ahora})\n    assert envio.status_code == 200, envio.text\n    assert _cierre(contrato)["total_ejecutado"] == 5 * 2900 + 3500 + 66000\n    r = cliente.post(f"/implantados/contratos/{contrato}/dias-adicionales",\n                     json={"fecha": str(DOMINGO)}, headers=h)\n    assert r.status_code == 409, r.text\n    assert "visto bueno" in r.text\n\n\ndef test_reabrir_un_dia_deshace_el_termino_del_mes(cliente, sesion, datos,\n                                                   monkeypatch):\n    """Antes del visto bueno, reabrir un dia borra el cierre del mes y\n    volver a cerrarlo lo arranca de nuevo; con el visto bueno dado, el\n    dia ya no se reabre."""\n    from app import facturacion\n    monkeypatch.setattr(facturacion.settings, "odoo_url", "")\n\n    alta = _alta(cliente, sesion, datos)\n    sid, contrato = alta["servicio_id"], alta["contrato_id"]\n    jornadas = _cerrar_mes(cliente, sesion, sid)\n    hc = sesion("central")\n\n    r = cliente.post(f"/operacion/jornadas/{jornadas[DIAS[2]]}/reabrir",\n                     headers=hc, json={"justificacion": MOTIVO})\n    assert r.status_code == 200, r.text\n    assert _cierre(contrato) is None\n\n    # Se vuelve a cerrar el sabado en la manana: T0 es esa firma, que\n    # llega despues del termino del viernes.\n    firma = datetime(2029, 9, 29, 10, 0)\n    _cerrar(cliente, sesion, jornadas[DIAS[2]], DIAS[2], ahora=firma)\n    c = _cierre(contrato)\n    assert c is not None and c["abierto_en"] == firma\n\n    ahora = firma + timedelta(hours=1)\n    assert _avanzar(c["id"], ahora) is True\n    envio = cliente.post(f"/cierre/{c[\'id\']}/enviar-finanzas",\n                         headers=sesion("consultor"),\n                         params={"ahora": ahora.isoformat()})\n    assert envio.status_code == 200, envio.text\n    r = cliente.post(f"/operacion/jornadas/{jornadas[DIAS[2]]}/reabrir",\n                     headers=hc, json={"justificacion": MOTIVO})\n    assert r.status_code == 409, r.text\n    assert "visto bueno" in r.text\n\n\ndef test_cancelar_los_ultimos_dias_completa_el_mes(cliente, sesion, datos):\n    """El cliente ya no necesita el viernes: el consultor lo quita y el mes\n    queda completo sin que otro dia lo cierre. El cierre arranca ahi, con\n    el termino del jueves."""\n    alta = _alta(cliente, sesion, datos)\n    sid, contrato = alta["servicio_id"], alta["contrato_id"]\n    _cerrar_mes(cliente, sesion, sid, dias=DIAS[:4])\n    assert _cierre(contrato) is None\n\n    r = cliente.delete(f"/implantados/{sid}/dia/{DIAS[4]}",\n                       headers=sesion("consultor"))\n    assert r.status_code == 200, r.text\n    c = _cierre(contrato)\n    assert c is not None and c["motivo"] == "termino"\n    assert c["abierto_en"].date() >= DIAS[3]\n\n\ndef test_la_red_de_cada_cinco_minutos_abre_el_mes_que_quedo_completo(\n        cliente, sesion, datos):\n    """Un mes que se completo por un camino que no dispara el cierre lo\n    encuentra la tarea de cada cinco minutos, y no lo abre dos veces."""\n    from app import cierre_mes\n    from app import models as m\n    from app.db import SessionLocal\n\n    alta = _alta(cliente, sesion, datos)\n    sid, contrato = alta["servicio_id"], alta["contrato_id"]\n    with SessionLocal() as db:\n        for j in (db.query(m.Jornada).join(m.Equipo)\n                  .filter(m.Equipo.servicio_id == sid).all()):\n            j.estatus = m.EstatusJornada.TERMINADA\n            j.inicio_real, j.fin_real = j.inicio_programado, j.fin_programado\n        db.commit()\n    assert _cierre(contrato) is None\n\n    ahora = datetime(2029, 10, 1, 9, 0)\n    with SessionLocal() as db:\n        abiertos = cierre_mes.abrir_los_que_terminaron(db, ahora)\n    assert len(abiertos) == 1 and abiertos[0].endswith("09/2029")\n    assert _cierre(contrato)["abierto_en"] == ahora, \\\n        "lo encontro despues: el plazo corre desde ahi"\n    with SessionLocal() as db:\n        assert cierre_mes.abrir_los_que_terminaron(db, ahora) == []\n\n\ndef test_dos_meses_en_fases_distintas(cliente, sesion, datos):\n    """Septiembre cierra mientras octubre ya esta abierto: cada mes lleva\n    su fase, y el dinero de octubre no detiene a septiembre."""\n    from app import implantado as motor\n    from app import models as m\n    from app.db import SessionLocal\n\n    alta = _alta(cliente, sesion, datos)\n    sid, septiembre = alta["servicio_id"], alta["contrato_id"]\n    with SessionLocal() as db:\n        abierto = motor.abrir_siguiente(db, db.get(m.Servicio, sid),\n                                        hoy=date(2029, 9, 27))\n    octubre = abierto["contrato_id"]\n    de_octubre = _jornadas(cliente, sesion, sid, 2029, 10)\n    vid = _viatico(cliente, sesion, datos, de_octubre[date(2029, 10, 1)])\n\n    _cerrar_mes(cliente, sesion, sid)\n    c = _cierre(septiembre)\n    assert c is not None and _cierre(octubre) is None\n    assert _limites([vid]) == [None], "el viatico de octubre no es de septiembre"\n    # Sin dinero en septiembre, su consultor arranca aunque octubre deba.\n    assert _avanzar(c["id"], _a_las_21(DIAS[4]) + timedelta(hours=1)) is True\n\n    h = sesion("consultor")\n    ficha = next(x for x in cliente.get("/implantados", headers=h).json()\n                 if x["servicio_id"] == sid)\n    assert [(p["periodo"], p["fase"]) for p in ficha["periodos"]] == \\\n        [("09/2029", "sin_visto_bueno"), ("10/2029", None)]\n    assert cliente.get(f"/implantados/{sid}/mes/2029/10",\n                       headers=h).json()["cierre"]["existe"] is False\n\n\ndef test_cancelar_el_implantado_cierra_el_mes_con_lo_trabajado(cliente, sesion,\n                                                              datos):\n    """Se cancela con tres dias trabajados: el mes arranca su cierre por\n    cancelacion y se factura con lo trabajado. El mes de despues, sin\n    nada que cerrar, se queda sin relojes."""\n    from app import implantado as motor\n    from app import models as m\n    from app.db import SessionLocal\n\n    alta = _alta(cliente, sesion, datos)\n    sid, septiembre = alta["servicio_id"], alta["contrato_id"]\n    with SessionLocal() as db:\n        octubre = motor.abrir_siguiente(db, db.get(m.Servicio, sid),\n                                        hoy=date(2029, 9, 27))["contrato_id"]\n    _cerrar_mes(cliente, sesion, sid, dias=DIAS[:3])\n\n    r = cliente.post(f"/servicios/{sid}/cancelar", headers=sesion("consultor"),\n                     json={"motivo": "El ejecutivo regreso a su pais"})\n    assert r.status_code == 200, r.text\n    c = _cierre(septiembre)\n    assert c is not None and c["motivo"] == "cancelacion"\n    assert _cierre(octubre) is None\n    with SessionLocal() as db:\n        from app import cierre_mes\n        comparativo = cierre_mes.comparar(db, db.get(m.ContratoImplantado,\n                                                     septiembre))\n    assert comparativo["trabajado"]["dias_base"] == 3\n\n\ndef test_la_app_esconde_solo_el_mes_con_visto_bueno(cliente, sesion, datos):\n    """La tarjeta de viaticos del implantado es del mes: se va con el\n    visto bueno de su mes, no con el de otro."""\n    from app import models as m\n    from app.db import SessionLocal\n    from app.routers.campo import _con_visto_bueno\n\n    alta = _alta(cliente, sesion, datos)\n    sid, contrato = alta["servicio_id"], alta["contrato_id"]\n    _cerrar_mes(cliente, sesion, sid)\n    with SessionLocal() as db:\n        cierre = db.query(m.Cierre).filter_by(contrato_id=contrato).first()\n        cierre.estatus = m.EstatusCierre.ENVIADO_FINANZAS\n        db.commit()\n        assert _con_visto_bueno(db, sid, date(2029, 9, 26)) is True\n        assert _con_visto_bueno(db, sid, date(2029, 10, 3)) is False\n        # Sin mes, es la pregunta del eventual: el implantado no tiene\n        # cierre de servicio entero.\n        assert _con_visto_bueno(db, sid) is False\n'}

textos = {k: io.open(v, encoding="utf-8").read() for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(viejo) == 1, f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces"
    textos[clave] = t.replace(viejo, nuevo)


# ================================================================ modelos
cambiar("models",
        "class Cierre(Base):\n"
        "    \"\"\"El consultor tiene 24 horas tras el cierre de viaticos del personal.\n"
        "    Maximo 48 horas tras el termino del servicio para cerrar y facturar.\"\"\"\n"
        "    __tablename__ = \"cierre\"\n"
        "\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        "    servicio_id: Mapped[int] = mapped_column(ForeignKey(\"servicio.id\"), unique=True)\n",
        "class Cierre(Base):\n"
        "    \"\"\"El consultor tiene 24 horas tras el cierre de viaticos del personal.\n"
        "    Maximo 48 horas tras el termino del servicio para cerrar y facturar.\n"
        "\n"
        "    Uno por servicio en el eventual y uno por mes de contrato en el\n"
        "    implantado (seccion 56): el implantado no termina, cada mes recorre\n"
        "    la cadena de dos relojes por su cuenta.\n"
        "    \"\"\"\n"
        "    __tablename__ = \"cierre\"\n"
        "    # El eventual conserva su regla --a lo mas un cierre por servicio--\n"
        "    # como indice parcial. La restriccion de columna no dejaba vivir al\n"
        "    # implantado, que lleva un cierre por mes con el mismo folio.\n"
        "    __table_args__ = (\n"
        "        Index(\"uq_cierre_del_eventual\", \"servicio_id\", unique=True,\n"
        "              postgresql_where=text(\"contrato_id IS NULL\")),\n"
        "    )\n"
        "\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        "    servicio_id: Mapped[int] = mapped_column(ForeignKey(\"servicio.id\"))\n"
        "    # El mes de contrato, en el implantado; vacio en el eventual.\n"
        "    contrato_id: Mapped[int | None] = mapped_column(\n"
        "        ForeignKey(\"contrato_implantado.id\"), nullable=True, unique=True)\n",
        marca="        Index(\"uq_cierre_del_eventual\", \"servicio_id\", unique=True,\n")
cambiar("models",
        "    servicio: Mapped[Servicio] = relationship()\n"
        "    desviaciones: Mapped[list[\"Desviacion\"]] = relationship(\n"
        "        back_populates=\"cierre\", cascade=\"all, delete-orphan\")\n",
        "    servicio: Mapped[Servicio] = relationship()\n"
        "    contrato: Mapped[\"ContratoImplantado | None\"] = relationship()\n"
        "    desviaciones: Mapped[list[\"Desviacion\"]] = relationship(\n"
        "        back_populates=\"cierre\", cascade=\"all, delete-orphan\")\n")
cambiar("models",
        "    __tablename__ = \"comision_consultor\"\n"
        "    __table_args__ = (UniqueConstraint(\"servicio_id\", \"consultor_id\"),)\n"
        "\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        "    servicio_id: Mapped[int] = mapped_column(ForeignKey(\"servicio.id\"))\n",
        "    __tablename__ = \"comision_consultor\"\n"
        "    # Una por servicio y consultor en el eventual; en el implantado, una\n"
        "    # por mes de contrato (seccion 56): se factura mes con mes.\n"
        "    __table_args__ = (\n"
        "        Index(\"uq_comision_del_servicio\", \"servicio_id\", \"consultor_id\",\n"
        "              unique=True, postgresql_where=text(\"contrato_id IS NULL\")),\n"
        "        Index(\"uq_comision_del_mes\", \"contrato_id\", \"consultor_id\",\n"
        "              unique=True,\n"
        "              postgresql_where=text(\"contrato_id IS NOT NULL\")),\n"
        "    )\n"
        "\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        "    servicio_id: Mapped[int] = mapped_column(ForeignKey(\"servicio.id\"))\n"
        "    # El mes de contrato, en el implantado; vacio en el eventual.\n"
        "    contrato_id: Mapped[int | None] = mapped_column(\n"
        "        ForeignKey(\"contrato_implantado.id\"), nullable=True)\n",
        marca="        Index(\"uq_comision_del_servicio\", \"servicio_id\", \"consultor_id\",\n")

# ================================================================ el motor del cierre
cambiar("cierre",
        "    ahora = reloj.ahora_del_servicio(db, servicio, ahora)\n"
        "    fila = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()\n",
        "    ahora = reloj.ahora_del_servicio(db, servicio, ahora)\n"
        "    # El del servicio. El implantado lleva uno por mes y se lee con\n"
        "    # `cierre_mes.estado`.\n"
        "    fila = (db.query(m.Cierre)\n"
        "            .filter_by(servicio_id=servicio_id, contrato_id=None).first())\n")
cambiar("cierre",
        "    existente = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()\n"
        "    if existente:\n"
        "        return existente\n",
        "    # El implantado no termina: cierra por mes, solo, al cerrar el ultimo\n"
        "    # dia trabajado de cada mes (`cierre_mes`, seccion 56). Un cierre del\n"
        "    # servicio entero lo sacaria de esa cadena.\n"
        "    if servicio.tipo == m.TipoServicio.IMPLANTADO:\n"
        "        raise HTTPException(409, {\n"
        "            \"mensaje\": \"El implantado cierra por mes, no por servicio\",\n"
        "            \"que_hacer\": \"El cierre de cada mes arranca solo al cerrar su \"\n"
        "                         \"ultimo dia trabajado.\"})\n"
        "\n"
        "    existente = (db.query(m.Cierre)\n"
        "                 .filter_by(servicio_id=servicio_id, contrato_id=None).first())\n"
        "    if existente:\n"
        "        return existente\n")
cambiar("cierre",
        "def avanzar(db: Session, cierre: m.Cierre,\n"
        "            ahora: datetime | None = None) -> bool:\n",
        "def _dinero_afuera(db: Session, cierre: m.Cierre) -> int:\n"
        "    \"\"\"Los viaticos sin cerrar de lo que cierra: el servicio entero en\n"
        "    el eventual; en el implantado, solo los del mes (seccion 56).\"\"\"\n"
        "    if cierre.contrato_id:\n"
        "        from app import cierre_mes\n"
        "        return cierre_mes.viaticos_abiertos(db, cierre.contrato)\n"
        "    return viaticos_abiertos(db, cierre.servicio_id)\n"
        "\n"
        "\n"
        "def avanzar(db: Session, cierre: m.Cierre,\n"
        "            ahora: datetime | None = None) -> bool:\n",
        marca="def _dinero_afuera(db: Session, cierre: m.Cierre) -> int:\n")
cambiar("cierre",
        "    elif viaticos_abiertos(db, servicio.id) == 0:\n"
        "        t1 = ahora\n",
        "    elif _dinero_afuera(db, cierre) == 0:\n"
        "        t1 = ahora\n")
cambiar("cierre",
        "    if servicio.consultor_id and not viejo:\n"
        "        from app import push\n"
        "        try:\n"
        "            push.avisar(\n"
        "                db, servicio.consultor_id,\n"
        "                titulo=f\"{servicio.folio}: tienes 24 h para el visto bueno\",\n"
        "                cuerpo=(\"La comprobacion del personal termino. Tu plazo \"\n"
        "                        f\"vence el {limite:%d/%m a las %H:%M}.\"),\n"
        "                # El consultor trabaja en la consola, no en la app de campo.\n"
        "                url=f\"/consola/#/servicio/{servicio.id}\",\n",
        "    if servicio.consultor_id and not viejo:\n"
        "        from app import push\n"
        "        # En el implantado el visto bueno es del mes y se da en su\n"
        "        # panel (seccion 56).\n"
        "        de_que = (f\"{servicio.folio} {cierre.contrato.mes:02d}/\"\n"
        "                  f\"{cierre.contrato.anio}\" if cierre.contrato_id\n"
        "                  else servicio.folio)\n"
        "        pantalla = (f\"/consola/#/implantado/{servicio.id}\"\n"
        "                    if cierre.contrato_id\n"
        "                    else f\"/consola/#/servicio/{servicio.id}\")\n"
        "        try:\n"
        "            push.avisar(\n"
        "                db, servicio.consultor_id,\n"
        "                titulo=f\"{de_que}: tienes 24 h para el visto bueno\",\n"
        "                cuerpo=(\"La comprobacion del personal termino. Tu plazo \"\n"
        "                        f\"vence el {limite:%d/%m a las %H:%M}.\"),\n"
        "                # El consultor trabaja en la consola, no en la app de campo.\n"
        "                url=pantalla,\n")
cambiar("cierre",
        "        if avanzar(db, cierre, ahora):\n"
        "            movidos.append(cierre.servicio.folio)\n",
        "        if avanzar(db, cierre, ahora):\n"
        "            # El mes del implantado se dice con su mes: el folio es el\n"
        "            # mismo todo el contrato.\n"
        "            movidos.append(\n"
        "                cierre.servicio.folio if not cierre.contrato_id else\n"
        "                f\"{cierre.servicio.folio} {cierre.contrato.mes:02d}/\"\n"
        "                f\"{cierre.contrato.anio}\")\n")

cambiar("revisor",
        "    registro = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()\n",
        "    registro = (db.query(m.Cierre)\n"
        "                .filter_by(servicio_id=servicio_id, contrato_id=None).first())\n")

# ================================================================ la comision
cambiar("comisiones",
        "    registro = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()\n",
        "    registro = (db.query(m.Cierre)\n"
        "                .filter_by(servicio_id=servicio_id, contrato_id=None).first())\n")
cambiar("comisiones",
        "    existente = (db.query(m.ComisionConsultor)\n"
        "                 .filter_by(servicio_id=servicio_id,\n"
        "                            consultor_id=servicio.consultor_id).first())\n",
        "    existente = (db.query(m.ComisionConsultor)\n"
        "                 .filter_by(servicio_id=servicio_id, contrato_id=None,\n"
        "                            consultor_id=servicio.consultor_id).first())\n")
cambiar("comisiones",
        "def resolver_retenida(db: Session, comision_id: int, se_paga: bool,\n",
        "def generar_del_mes(db: Session, cierre: m.Cierre) -> m.ComisionConsultor:\n"
        "    \"\"\"La comision del consultor por un mes de implantado (seccion 56).\n"
        "\n"
        "    La misma regla que la del servicio --sobre lo facturado,\n"
        "    descontando los viaticos; se pierde si el visto bueno salio fuera\n"
        "    de plazo; se retiene si hubo incidencia grave-- pero por mes,\n"
        "    porque el implantado se factura mes con mes. La incidencia que\n"
        "    cuenta es la de ese mes.\n"
        "    \"\"\"\n"
        "    from app import cierre_mes\n"
        "\n"
        "    servicio = cierre.servicio\n"
        "    if not servicio.consultor_id:\n"
        "        raise HTTPException(400, \"El servicio no tiene consultor asignado\")\n"
        "    if cierre.estatus not in (m.EstatusCierre.APROBADO,\n"
        "                              m.EstatusCierre.FACTURADO):\n"
        "        raise HTTPException(409, \"La comision se detona con el cierre validado \"\n"
        "                                 \"por finanzas\")\n"
        "\n"
        "    existente = (db.query(m.ComisionConsultor)\n"
        "                 .filter_by(contrato_id=cierre.contrato_id,\n"
        "                            consultor_id=servicio.consultor_id).first())\n"
        "    if existente:\n"
        "        return existente\n"
        "\n"
        "    contrato = cierre.contrato\n"
        "    facturacion = Decimal(str(cierre.total_ejecutado or 0))\n"
        "    # El costo real de los viaticos del mes es lo comprobado.\n"
        "    viaticos = sum((Decimal(str(v.monto_comprobado or 0))\n"
        "                    for v in cierre_mes.viaticos_del_mes(db, contrato)),\n"
        "                   CERO)\n"
        "    base = facturacion - viaticos\n"
        "    pct = _porcentaje(db, servicio.pais_id, servicio.tipo)\n"
        "    monto = (base * pct / Decimal(\"100\")).quantize(Decimal(\"0.01\"))\n"
        "\n"
        "    referencia = cierre.aprobado_en or cierre.enviado_en\n"
        "    periodo = referencia.date() if referencia else date.today()\n"
        "    pais = db.get(m.Pais, servicio.pais_id)\n"
        "\n"
        "    comision = m.ComisionConsultor(\n"
        "        servicio_id=servicio.id, contrato_id=contrato.id,\n"
        "        consultor_id=servicio.consultor_id,\n"
        "        anio=periodo.year, mes=periodo.month,\n"
        "        facturacion=facturacion, viaticos=viaticos, base=base,\n"
        "        porcentaje=pct, monto=monto, moneda=pais.moneda_local)\n"
        "\n"
        "    ultimo = calendar.monthrange(contrato.anio, contrato.mes)[1]\n"
        "    grave = (db.query(m.Incidencia)\n"
        "             .filter(m.Incidencia.servicio_id == servicio.id,\n"
        "                     m.Incidencia.gravedad == m.GravedadIncidencia.GRAVE,\n"
        "                     m.Incidencia.autorizada.is_(True),\n"
        "                     m.Incidencia.fecha >= date(contrato.anio,\n"
        "                                                contrato.mes, 1),\n"
        "                     m.Incidencia.fecha <= date(contrato.anio,\n"
        "                                                contrato.mes, ultimo))\n"
        "             .first())\n"
        "    if not cierre.dentro_de_plazo:\n"
        "        comision.estatus = m.EstatusComision.PERDIDA\n"
        "        comision.monto = CERO\n"
        "        comision.motivo = (\"El consultor no dio el visto bueno del mes \"\n"
        "                           \"dentro de sus 24 horas: se pierde la comision \"\n"
        "                           \"de ese mes\")\n"
        "    elif grave:\n"
        "        comision.estatus = m.EstatusComision.RETENIDA\n"
        "        comision.motivo = (\"Hay una incidencia grave en el mes. \"\n"
        "                           \"La consecuencia la decide el director general.\")\n"
        "\n"
        "    db.add(comision)\n"
        "    db.commit()\n"
        "    db.refresh(comision)\n"
        "    return comision\n"
        "\n"
        "\n"
        "def resolver_retenida(db: Session, comision_id: int, se_paga: bool,\n",
        marca="def generar_del_mes(db: Session, cierre: m.Cierre) -> m.ComisionConsultor:\n")
cambiar("comisiones",
        "from datetime import date\nfrom decimal import Decimal\n",
        "import calendar\nfrom datetime import date\nfrom decimal import Decimal\n")

# ================================================================ la factura
cambiar("facturacion",
        "    from app import cotizacion as cot\n"
        "\n"
        "    servicio = cierre.servicio\n"
        "    cotizacion = cot.vigente(db, servicio.id)\n",
        "    from app import cotizacion as cot\n"
        "\n"
        "    # El mes del implantado se factura con los precios de su contrato,\n"
        "    # no con una cotizacion por dia (seccion 56).\n"
        "    if cierre.contrato_id:\n"
        "        from app import cierre_mes\n"
        "        return cierre_mes.armar_factura(db, cierre)\n"
        "\n"
        "    servicio = cierre.servicio\n"
        "    cotizacion = cot.vigente(db, servicio.id)\n")
cambiar("facturacion",
        "        \"folio\": c.servicio.folio,\n",
        "        \"folio\": c.servicio.folio,\n"
        "        # El mes, en el implantado: el mismo folio factura mes con mes.\n"
        "        \"periodo\": (f\"{c.contrato.mes:02d}/{c.contrato.anio}\"\n"
        "                    if c.contrato_id else None),\n")

# ================================================================ las rutas del cierre
cambiar("rcierre",
        "from app import cierre as motor\n",
        "from app import cierre as motor\n"
        "from app import cierre_mes\n")
cambiar("rcierre",
        "    \"\"\"No se puede enviar con observaciones graves sin resolver.\"\"\"\n"
        "    cierre = db.get(m.Cierre, cierre_id)\n"
        "    if not cierre:\n"
        "        raise HTTPException(404, f\"No existe el cierre {cierre_id}\")\n",
        "    \"\"\"No se puede enviar con observaciones graves sin resolver.\"\"\"\n"
        "    cierre = db.get(m.Cierre, cierre_id)\n"
        "    if not cierre:\n"
        "        raise HTTPException(404, f\"No existe el cierre {cierre_id}\")\n"
        "    # El mes del implantado lleva su revision y su factura del mes;\n"
        "    # lo de abajo es el eventual, sin cambios (seccion 56).\n"
        "    if cierre.contrato_id:\n"
        "        return cierre_mes.enviar_a_finanzas(db, cierre, usuario, ahora)\n")
cambiar("rcierre",
        "    if cierre.estatus != m.EstatusCierre.ENVIADO_FINANZAS:\n"
        "        raise HTTPException(409, f\"El cierre esta en {cierre.estatus.value}\")\n"
        "\n"
        "    cierre.estatus = m.EstatusCierre.APROBADO\n",
        "    if cierre.estatus != m.EstatusCierre.ENVIADO_FINANZAS:\n"
        "        raise HTTPException(409, f\"El cierre esta en {cierre.estatus.value}\")\n"
        "    # El mes del implantado: se aprueba el mes, el servicio sigue vivo\n"
        "    # y la comision es de ese mes (seccion 56).\n"
        "    if cierre.contrato_id:\n"
        "        return cierre_mes.aprobar(db, cierre, usuario)\n"
        "\n"
        "    cierre.estatus = m.EstatusCierre.APROBADO\n")

# ================================================================ la operacion
cambiar("operacion",
        "def _viaticos_del_servicio(db: Session, servicio_id: int) -> list:\n",
        "def _termino_del_implantado(db: Session, jornada: m.Jornada,\n"
        "                            termino: datetime,\n"
        "                            registrado: datetime | None) -> None:\n"
        "    \"\"\"El dia del implantado termino.\n"
        "\n"
        "    Si es de un mes de contrato, cerrar el dia ya no abre plazo: el\n"
        "    plazo es del mes y arranca con su cierre, cuando el mes queda\n"
        "    completo (seccion 56). El dia sin mes de contrato --los de antes\n"
        "    de que hubiera meses-- conserva sus 24 horas desde que termina.\n"
        "    \"\"\"\n"
        "    from app import cierre_mes\n"
        "\n"
        "    contrato = cierre_mes.contrato_de(db, jornada)\n"
        "    if contrato is None:\n"
        "        abrir_plazo_de_comprobacion(db, jornada, termino)\n"
        "        return\n"
        "    cierre_mes.terminar_si_cerro_el_mes(db, contrato, registrado=registrado)\n"
        "\n"
        "\n"
        "def _viaticos_del_servicio(db: Session, servicio_id: int) -> list:\n",
        marca="def _termino_del_implantado(db: Session, jornada: m.Jornada,\n")
cambiar("operacion",
        "        # El dia termino. En el implantado empiezan a correr las 24\n"
        "        # horas para comprobar ese dia; en el eventual el plazo es uno\n"
        "        # solo para todo el servicio y arranca con el termino general,\n"
        "        # abajo, al cerrar el ultimo dia (decision de Salvador, 22 sep).\n"
        "        if servicio.tipo != m.TipoServicio.EVENTUAL:\n"
        "            abrir_plazo_de_comprobacion(db, jornada, ahora)\n",
        "        # El dia termino. En el eventual el plazo es uno solo para todo\n"
        "        # el servicio y arranca con el termino general, abajo, al\n"
        "        # cerrar el ultimo dia (decision de Salvador, 22 sep). En el\n"
        "        # implantado es uno por mes y arranca con el cierre del mes\n"
        "        # (seccion 56).\n"
        "        if servicio.tipo != m.TipoServicio.EVENTUAL:\n"
        "            _termino_del_implantado(db, jornada, ahora, recibido)\n")
cambiar("operacion",
        "    if jornada.equipo.servicio.tipo != m.TipoServicio.EVENTUAL:\n"
        "        abrir_plazo_de_comprobacion(db, jornada, fin)\n",
        "    if jornada.equipo.servicio.tipo != m.TipoServicio.EVENTUAL:\n"
        "        _termino_del_implantado(db, jornada, fin, ahora)\n")
cambiar("operacion",
        "                from app import programacion\n"
        "                servicio.estatus = m.EstatusServicio.PLANEADO\n"
        "                programacion.evaluar(servicio)\n"
        "\n"
        "    # Se deshace todo lo que escribio el cierre a mano, la hora de\n",
        "                from app import programacion\n"
        "                servicio.estatus = m.EstatusServicio.PLANEADO\n"
        "                programacion.evaluar(servicio)\n"
        "    else:\n"
        "        # El implantado cierra por mes (seccion 56): reabrir un dia de\n"
        "        # un mes en comprobacion o sin visto bueno deshace el termino de\n"
        "        # ese mes; con el visto bueno dado ya no se reabre.\n"
        "        from app import cierre_mes\n"
        "        cierre_mes.deshacer_termino(db, cierre_mes.contrato_de(db, jornada),\n"
        "                                    \"no se puede reabrir un dia\")\n"
        "\n"
        "    # Se deshace todo lo que escribio el cierre a mano, la hora de\n",
        marca="        cierre_mes.deshacer_termino(db, cierre_mes.contrato_de(db, jornada),\n")

# ================================================================ el implantado
cambiar("implantado",
        "    equipo = contrato.servicio.equipos[0]\n"
        "    ya_esta = (db.query(m.Jornada)\n"
        "               .filter_by(equipo_id=equipo.id, fecha=fecha).first())\n",
        "    # Un dia que entra despues de T0 (seccion 56): con el mes en\n"
        "    # comprobacion o sin visto bueno el termino se deshace y el mes\n"
        "    # vuelve a cerrar con su nuevo ultimo dia; con el visto bueno dado\n"
        "    # ya no entra: la factura del mes salio con los dias que tenia.\n"
        "    from app import cierre_mes\n"
        "    cierre_mes.deshacer_termino(db, contrato, \"ya no entra un dia nuevo\")\n"
        "\n"
        "    equipo = contrato.servicio.equipos[0]\n"
        "    ya_esta = (db.query(m.Jornada)\n"
        "               .filter_by(equipo_id=equipo.id, fecha=fecha).first())\n",
        marca="    cierre_mes.deshacer_termino(db, contrato, \"ya no entra un dia nuevo\")\n\n"
              "    equipo = contrato.servicio.equipos[0]\n"
              "    ya_esta = ")
cambiar("implantado",
        "    if not personal:\n"
        "        raise HTTPException(409, \"Hay que decir quien cubre el dia\")\n",
        "    if not personal:\n"
        "        raise HTTPException(409, \"Hay que decir quien cubre el dia\")\n"
        "    # Lo mismo que el dia adicional: despues de T0 un dia nuevo deshace\n"
        "    # el termino del mes, y con el visto bueno dado ya no entra.\n"
        "    from app import cierre_mes\n"
        "    cierre_mes.deshacer_termino(db, contrato, \"ya no entra un dia nuevo\")\n")
cambiar("implantado",
        "    if _ya_empezo(jornada):\n"
        "        raise HTTPException(409, \"Ese dia ya empezo: no se puede cerrar\")\n"
        "\n"
        "    # El dinero de ese dia. Lo que ya salio del banco no se borra con un\n",
        "    if _ya_empezo(jornada):\n"
        "        raise HTTPException(409, \"Ese dia ya empezo: no se puede cerrar\")\n"
        "    # Si con este dia el mes se queda sin nada por trabajar, arranca su\n"
        "    # cierre (seccion 56): ya no hay otro dia cuyo termino lo dispare.\n"
        "    from app import cierre_mes\n"
        "    contrato = cierre_mes.contrato_de(db, jornada)\n"
        "\n"
        "    # El dinero de ese dia. Lo que ya salio del banco no se borra con un\n")
cambiar("implantado",
        "        jornada.estatus = m.EstatusJornada.CANCELADA\n"
        "        db.commit()\n"
        "        return {\"cancelado\": fecha.isoformat(), \"borrado\": False,\n",
        "        jornada.estatus = m.EstatusJornada.CANCELADA\n"
        "        cierre_mes.terminar_si_cerro_el_mes(\n"
        "            db, contrato, registrado=reloj.ahora_del_servicio(db, servicio))\n"
        "        db.commit()\n"
        "        return {\"cancelado\": fecha.isoformat(), \"borrado\": False,\n")
cambiar("implantado",
        "    db.delete(jornada)\n"
        "    db.commit()\n"
        "    return {\"cerrado\": fecha.isoformat(),\n",
        "    db.delete(jornada)\n"
        "    cierre_mes.terminar_si_cerro_el_mes(\n"
        "        db, contrato, registrado=reloj.ahora_del_servicio(db, servicio))\n"
        "    db.commit()\n"
        "    return {\"cerrado\": fecha.isoformat(),\n")

cambiar("implantado",
        "    if jornada.estatus != m.EstatusJornada.CANCELADA:\n"
        "        raise HTTPException(409, \"Ese dia no esta cancelado\")\n"
        "    jornada.estatus = m.EstatusJornada.PLANEADA\n",
        "    if jornada.estatus != m.EstatusJornada.CANCELADA:\n"
        "        raise HTTPException(409, \"Ese dia no esta cancelado\")\n"
        "    # Un dia que vuelve despues de T0 deshace el termino del mes; con el\n"
        "    # visto bueno dado ya no vuelve (seccion 56).\n"
        "    from app import cierre_mes\n"
        "    cierre_mes.deshacer_termino(db, cierre_mes.contrato_de(db, jornada),\n"
        "                                \"ya no vuelve un dia cancelado\")\n"
        "    jornada.estatus = m.EstatusJornada.PLANEADA\n")

# ================================================================ cancelar
cambiar("servicios",
        "        motor_cierre.abrir(db, servicio.id, abierto_en=momento,\n"
        "                           motivo=\"cancelacion\")\n"
        "\n"
        "    antes = servicio.estatus.value\n",
        "        motor_cierre.abrir(db, servicio.id, abierto_en=momento,\n"
        "                           motivo=\"cancelacion\")\n"
        "    # El implantado cierra por mes (seccion 56): cada mes con dias\n"
        "    # trabajados o dinero que salio arranca su cierre con T0 = ahora y\n"
        "    # se factura con lo trabajado; los que no tienen nada que cerrar se\n"
        "    # quedan sin relojes.\n"
        "    elif servicio.tipo == m.TipoServicio.IMPLANTADO:\n"
        "        from app import cierre_mes\n"
        "        cierre_mes.al_cancelar(db, servicio)\n"
        "\n"
        "    antes = servicio.estatus.value\n",
        marca="        cierre_mes.al_cancelar(db, servicio)\n")

# ================================================================ la app
cambiar("campo",
        "            \"visto_bueno\": _con_visto_bueno(db, servicio.id),\n",
        "            \"visto_bueno\": _con_visto_bueno(\n"
        "                db, servicio.id, jornada.fecha if por_mes else None),\n")
cambiar("campo",
        "def _con_visto_bueno(db: Session, servicio_id: int) -> bool:\n"
        "    \"\"\"Si el consultor ya cerro ese servicio y lo mando a facturar.\"\"\"\n"
        "    cierre = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()\n"
        "    return bool(cierre and cierre.estatus != m.EstatusCierre.ABIERTO)\n",
        "def _con_visto_bueno(db: Session, servicio_id: int,\n"
        "                     del_mes: date | None = None) -> bool:\n"
        "    \"\"\"Si el consultor ya cerro ese servicio y lo mando a facturar.\n"
        "\n"
        "    En el implantado el cierre es del mes (seccion 56): la tarjeta de\n"
        "    septiembre se va con el cierre de septiembre, no con el de octubre.\n"
        "    \"\"\"\n"
        "    consulta = db.query(m.Cierre).filter_by(servicio_id=servicio_id)\n"
        "    if del_mes is None:\n"
        "        cierre = consulta.filter(m.Cierre.contrato_id.is_(None)).first()\n"
        "    else:\n"
        "        cierre = (consulta\n"
        "                  .join(m.ContratoImplantado,\n"
        "                        m.Cierre.contrato_id == m.ContratoImplantado.id)\n"
        "                  .filter(m.ContratoImplantado.anio == del_mes.year,\n"
        "                          m.ContratoImplantado.mes == del_mes.month)\n"
        "                  .first())\n"
        "    return bool(cierre and cierre.estatus != m.EstatusCierre.ABIERTO)\n")

# ================================================================ el panel del implantado
cambiar("rimplantados",
        "from app import implantado as motor\n",
        "from app import cierre_mes\n"
        "from app import implantado as motor\n")
cambiar("rimplantados",
        "    return motor.cierre_del_mes(db, contrato_id)\n",
        "    return motor.cierre_del_mes(db, contrato_id)\n"
        "\n"
        "\n"
        "@router.get(\"/contratos/{contrato_id}/cierre/estado\",\n"
        "            summary=\"El reloj del cierre del mes\")\n"
        "def estado_del_cierre(contrato_id: int, db: Session = Depends(get_db),\n"
        "                      ahora: datetime | None = None, _=Depends(LECTURA)):\n"
        "    \"\"\"En que fase va el mes --comprobacion, sin visto bueno, en\n"
        "    facturacion-- con sus relojes (seccion 56). El visto bueno y la\n"
        "    aprobacion del mes van por las mismas rutas del cierre: `/cierre/\n"
        "    {cierre_id}/enviar-finanzas` y `/cierre/{cierre_id}/aprobar`.\"\"\"\n"
        "    return cierre_mes.estado(db, cierre_mes.contrato_o_404(db, contrato_id),\n"
        "                             ahora)\n"
        "\n"
        "\n"
        "@router.get(\"/contratos/{contrato_id}/cierre/revision\",\n"
        "            summary=\"Revision del mes antes del visto bueno\")\n"
        "def revision_del_mes(contrato_id: int, db: Session = Depends(get_db),\n"
        "                     ahora: datetime | None = None, _=Depends(LECTURA)):\n"
        "    \"\"\"Lo que el consultor tiene que resolver antes del visto bueno del\n"
        "    mes: el comparativo contra el contrato, el dinero y las marcas.\"\"\"\n"
        "    return cierre_mes.revisar(db, cierre_mes.contrato_o_404(db, contrato_id),\n"
        "                              ahora)\n",
        marca="@router.get(\"/contratos/{contrato_id}/cierre/estado\",\n")
cambiar("rimplantados",
        "        ultimo = meses[0] if meses else None\n",
        "        ultimo = meses[0] if meses else None\n"
        "        fases = cierre_mes.fases_de(db, meses)\n")
cambiar("rimplantados",
        "            \"periodos\": [{\"anio\": c.anio, \"mes\": c.mes,\n"
        "                          \"periodo\": f\"{c.mes:02d}/{c.anio}\"}\n"
        "                         for c in reversed(meses)],\n",
        "            \"periodos\": [{\"anio\": c.anio, \"mes\": c.mes,\n"
        "                          \"periodo\": f\"{c.mes:02d}/{c.anio}\",\n"
        "                          # En que va el cierre de cada mes; vacio\n"
        "                          # mientras se trabaja (seccion 56).\n"
        "                          \"fase\": fases.get(c.id)}\n"
        "                         for c in reversed(meses)],\n")
cambiar("rimplantados",
        "        \"resumen\": motor.resumen_mensual(db, contrato.id) if contrato else None,\n",
        "        \"resumen\": motor.resumen_mensual(db, contrato.id) if contrato else None,\n"
        "        # El cierre del mes: su fase y sus relojes (seccion 56).\n"
        "        \"cierre\": cierre_mes.estado(db, contrato) if contrato else None,\n")

cambiar("rimplantados",
        "    hecho = motor.generar_mes(db, contrato.id,\n"
        "                              rellenando=True)\n",
        "    # Con el visto bueno del mes dado ya no entran dias; antes, los que\n"
        "    # entren deshacen el termino del mes (seccion 56).\n"
        "    if cierre_mes.con_visto_bueno(db, contrato):\n"
        "        cierre_mes.deshacer_termino(db, contrato,\n"
        "                                    \"ya no se completan sus dias\")\n"
        "    hecho = motor.generar_mes(db, contrato.id,\n"
        "                              rellenando=True)\n"
        "    if hecho.get(\"jornadas_creadas\"):\n"
        "        cierre_mes.deshacer_termino(db, contrato,\n"
        "                                    \"ya no se completan sus dias\")\n")

# ================================================================ el reloj de cada cinco minutos
cambiar("celery",
        "@celery.task(name=\"cierre.avanzar\")\n"
        "def avanzar_cierres():\n"
        "    \"\"\"De la comprobacion al visto bueno, cuando toca.\"\"\"\n"
        "    from app.db import SessionLocal\n"
        "    from app import cierre\n"
        "\n"
        "    db = SessionLocal()\n"
        "    try:\n"
        "        return {\"movidos\": cierre.avanzar_cierres(db)}\n",
        "@celery.task(name=\"cierre.avanzar\")\n"
        "def avanzar_cierres():\n"
        "    \"\"\"De la comprobacion al visto bueno, cuando toca.\n"
        "\n"
        "    Antes, la red del implantado: el mes que quedo completo sin que el\n"
        "    cierre de un dia lo disparara --se cancelaron sus ultimos dias--\n"
        "    arranca aqui su cierre (seccion 56).\n"
        "    \"\"\"\n"
        "    from app.db import SessionLocal\n"
        "    from app import cierre, cierre_mes\n"
        "\n"
        "    db = SessionLocal()\n"
        "    try:\n"
        "        meses = cierre_mes.abrir_los_que_terminaron(db)\n"
        "        return {\"meses_abiertos\": meses,\n"
        "                \"movidos\": cierre.avanzar_cierres(db)}\n")

# ================================================================ la prueba del eventual
cambiar("t_relojes",
        "Solo el eventual. El implantado corta a mes y llega en su propia sesion.\n",
        "Solo el eventual. El implantado corta a mes: test_cierre_mes.py.\n")

# ================================================================ bitacora
cambiar("bitacora",
        "## 14. Lo que falta\n",
        "## 56. El cierre por mes del implantado\n"
        "\n"
        "Decisión de Salvador, 22 de septiembre (`PROPUESTA_CIERRE_24H.md`,\n"
        "regla 8), y el camino A del 23 de septiembre. Segunda de las tres\n"
        "sesiones del cierre en dos relojes. El implantado nunca termina: la\n"
        "cadena la recorre cada mes de contrato.\n"
        "\n"
        "- **Un cierre por mes, en la misma tabla.** El cierre y la comisión\n"
        "  del consultor llevan el mes de contrato (`contrato_id`). El eventual\n"
        "  sigue con uno por servicio —ahora como índice parcial— y su camino\n"
        "  no cambia; toda su batería pasa igual.\n"
        "- **T0 del mes.** El cierre del último día trabajado del mes: la hora\n"
        "  real de término, o la firma si se cerró tarde. Si el mes acaba en\n"
        "  fin de semana, el viernes; si se trabaja el sábado adicional, el\n"
        "  sábado. También arranca si el mes queda completo porque se\n"
        "  cancelaron sus últimos días, con red en la tarea de cada cinco\n"
        "  minutos. Sin días trabajados ni dinero que haya salido, no hay\n"
        "  relojes.\n"
        "- **Los viáticos del mes** vencen todos en T0 + 24 h; cerrar cada día\n"
        "  ya no abre plazo. El del relevado corre desde su relevo. Un día sin\n"
        "  mes de contrato conserva sus 24 h desde que termina.\n"
        "- **T1 y el visto bueno.** Los mismos relojes: a las 24 h —o antes, si\n"
        "  todo el dinero del mes cerró— el consultor tiene sus 24 h. La\n"
        "  revisión del mes compara contra el contrato: días base y adicionales\n"
        "  trabajados a su precio, la unidad por mes; un día sin cubrir o un\n"
        "  precio que falta se resuelve antes. El visto bueno manda la factura\n"
        "  del mes; si Odoo no contesta, el mes queda por facturar.\n"
        "- **Finanzas aprueba el mes** y se detona la comisión del consultor\n"
        "  por mes: 1 % sobre lo facturado, sin los viáticos comprobados; se\n"
        "  pierde fuera de plazo y se retiene con incidencia grave del mes.\n"
        "- **El estatus del servicio no se mueve.** Cada mes lleva su fase: en\n"
        "  la cartera (`periodos[].fase`) y en su panel (`cierre`), con\n"
        "  `/implantados/contratos/{id}/cierre/estado` y `/cierre/revision`.\n"
        "- **Un día que entra o se reabre después de T0** deshace el término\n"
        "  del mes; con el visto bueno dado ya no se puede.\n"
        "- **Cancelar el implantado** cierra con lo trabajado cada mes que\n"
        "  tenga algo que cerrar, con T0 = el momento de cancelar.\n"
        "- **La app** esconde la tarjeta de un mes con el cierre de ese mes, no\n"
        "  con el de otro.\n"
        "\n"
        "Los viáticos por comprobar todavía no van en la factura del mes —la\n"
        "del eventual tampoco los lleva—: entran con la factura en Odoo.\n"
        "Queda para la sesión 3: la consola y la app con la fase y sus relojes.\n"
        "\n"
        "## 14. Lo que falta\n",
        marca="## 56. El cierre por mes del implantado\n")

# ================================================================ escrituras
for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(textos[clave])
        print("escrito ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for relativa, contenido in NUEVOS.items():
    ruta = B / relativa
    if ruta.exists() and io.open(ruta, encoding="utf-8").read() == contenido:
        print("sin cambio", ruta.relative_to(RAIZ))
    else:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        print("escrito ", ruta.relative_to(RAIZ))
for s in saltados:
    print("saltado:", s)

# -*- coding: utf-8 -*-
"""El historial de lo facturado (seccion 69).

Lo que finanzas ya cerro nunca se borraba --el servicio, el cierre, los
montos, quien aprobo, la factura--, pero no habia donde verlo: la
pestana de cerrados de Facturacion ensena solo el mes en curso. Aqui va
todo, desde el primer servicio, con filtros y en Excel.

Cada renglon dice tambien que pasa con sus fotos: cuantas siguen en
Centauro y cuando se archivan, o cuando se archivaron. Es lo que deja
ver el archivo antes de prenderlo: con `ARCHIVO_DESTINO` vacio el
historial funciona igual y ya dice que se iria y cuando.

Un renglon es un cierre: el eventual, uno por servicio; el implantado,
uno por mes.
"""
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app import archivo
from app import auth
from app import excel
from app import facturacion
from app import models as m
from app.config import settings

CERO = Decimal("0")
POR_PAGINA = 50


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _iso(momento) -> str | None:
    return momento.isoformat() if momento else None


def mes(texto: str | None) -> date | None:
    """"2026-10" -> 1 de octubre de 2026."""
    if not texto:
        return None
    try:
        anio, numero = (int(x) for x in texto.split("-")[:2])
        return date(anio, numero, 1)
    except (TypeError, ValueError):
        raise HTTPException(400, f"El mes '{texto}' no se entiende: va como "
                                 "2026-10") from None


def filtros(desde: str | None = None, hasta: str | None = None,
            cliente_id: int | None = None, consultor_id: int | None = None,
            tipo: str | None = None, folio: str | None = None) -> dict:
    if tipo and tipo not in {t.value for t in m.TipoServicio}:
        raise HTTPException(400, f"Tipo '{tipo}' no existe")
    return {"desde": mes(desde), "hasta": mes(hasta),
            "cliente_id": cliente_id, "consultor_id": consultor_id,
            "tipo": tipo or None, "folio": (folio or "").strip() or None}


def _cuando():
    """El dia en que se cerro: la factura, o la aprobacion si no hubo."""
    return func.coalesce(m.Cierre.facturado_en, m.Cierre.aprobado_en)


def _consulta(db: Session, f: dict):
    cuando = _cuando()
    q = (db.query(m.Cierre)
         .join(m.Servicio, m.Cierre.servicio_id == m.Servicio.id)
         .filter(m.Cierre.estatus.in_(archivo.CERRADOS)))
    if f["desde"]:
        q = q.filter(cuando >= datetime(f["desde"].year, f["desde"].month, 1))
    if f["hasta"]:
        despues = archivo.sumar_meses(f["hasta"], 1)
        q = q.filter(cuando < datetime(despues.year, despues.month, 1))
    if f["cliente_id"]:
        q = q.filter(m.Servicio.cliente_id == f["cliente_id"])
    if f["consultor_id"]:
        q = q.filter(m.Servicio.consultor_id == f["consultor_id"])
    if f["tipo"]:
        q = q.filter(m.Servicio.tipo == m.TipoServicio(f["tipo"]))
    if f["folio"]:
        q = q.filter(m.Servicio.folio.icontains(f["folio"], autoescape=True))
    return (q.options(joinedload(m.Cierre.servicio),
                      joinedload(m.Cierre.contrato))
            .order_by(cuando.desc(), m.Cierre.id.desc()))


# ================================================================ los datos

def _por_cierre(db: Session, cierres: list) -> dict[int, dict]:
    """Por cierre: lo comprobado y como van sus fotos."""
    de_cada = archivo.asignaciones_por_cierre(db, cierres)
    comprobado, fotos, archivadas, ultima = {}, {}, {}, {}
    todas = [a for lista in de_cada.values() for a in lista]
    for trozo in archivo.en_trozos(todas):
        for vid, monto in (db.query(m.AsignacionViatico.id,
                                    m.AsignacionViatico.monto_comprobado)
                           .filter(m.AsignacionViatico.id.in_(trozo),
                                   m.AsignacionViatico.estatus
                                   != m.EstatusViatico.CANCELADO)):
            comprobado[vid] = _d(monto)
        for modelo, foto in ((m.Comprobante, m.Comprobante.imagen),
                             (m.DevolucionViatico,
                              m.DevolucionViatico.comprobante)):
            for vid, en_base, idas, cuando in (
                    db.query(modelo.asignacion_id,
                             func.count(case((foto.isnot(None), 1))),
                             func.count(modelo.archivado_en),
                             func.max(modelo.archivado_en))
                    .filter(modelo.asignacion_id.in_(trozo))
                    .group_by(modelo.asignacion_id)):
                fotos[vid] = fotos.get(vid, 0) + en_base
                archivadas[vid] = archivadas.get(vid, 0) + idas
                if cuando and (vid not in ultima or cuando > ultima[vid]):
                    ultima[vid] = cuando
    salida = {}
    for cierre_id, lista in de_cada.items():
        fechas = [ultima[a] for a in lista if a in ultima]
        salida[cierre_id] = {
            "comprobado": sum((comprobado.get(a, CERO) for a in lista), CERO),
            "en_centauro": sum(fotos.get(a, 0) for a in lista),
            "archivadas": sum(archivadas.get(a, 0) for a in lista),
            "archivadas_en": max(fechas) if fechas else None,
            "asignaciones": lista,
        }
    return salida


def _monedas(db: Session, cierres: list) -> dict[int, str | None]:
    """La del renglon de facturacion: la de la cotizacion vigente en el
    eventual, la del pais en el mes del implantado."""
    eventuales = {c.servicio_id for c in cierres if not c.contrato_id}
    vigentes = {}
    for trozo in archivo.en_trozos(eventuales):
        for sid, version, moneda in (
                db.query(m.Cotizacion.servicio_id, m.Cotizacion.version,
                         m.Cotizacion.moneda)
                .filter(m.Cotizacion.servicio_id.in_(trozo),
                        m.Cotizacion.estatus
                        == m.EstatusCotizacion.AUTORIZADA)):
            if sid not in vigentes or version > vigentes[sid][0]:
                vigentes[sid] = (version, moneda)
    del_pais = {p.id: p.moneda_local for p in db.query(m.Pais)}
    salida = {}
    for c in cierres:
        moneda = (vigentes.get(c.servicio_id, (None, None))[1]
                  if not c.contrato_id else None)
        moneda = moneda or del_pais.get(c.servicio.pais_id)
        salida[c.id] = moneda.value if moneda else None
    return salida


def _rangos(db: Session, cierres: list) -> dict[int, tuple]:
    """El primer y el ultimo dia de cada servicio eventual."""
    eventuales = {c.servicio_id for c in cierres if not c.contrato_id}
    salida = {}
    for trozo in archivo.en_trozos(eventuales):
        for sid, primero, ultimo in (
                db.query(m.Equipo.servicio_id, func.min(m.Jornada.fecha),
                         func.max(m.Jornada.fecha))
                .join(m.Jornada, m.Jornada.equipo_id == m.Equipo.id)
                .filter(m.Equipo.servicio_id.in_(trozo))
                .group_by(m.Equipo.servicio_id)):
            salida[sid] = (primero, ultimo)
    return salida


def _nombres(db: Session, modelo, ids) -> dict:
    ids = {i for i in ids if i}
    salida = {}
    for trozo in archivo.en_trozos(ids):
        for i, nombre in (db.query(modelo.id, modelo.nombre)
                          .filter(modelo.id.in_(trozo))):
            salida[i] = nombre
    return salida


def _renglones(db: Session, cierres: list, conexion: bool) -> list[dict]:
    if not cierres:
        return []
    datos = _por_cierre(db, cierres)
    monedas = _monedas(db, cierres)
    rangos = _rangos(db, cierres)
    personas = _nombres(db, m.Persona,
                        [c.servicio.consultor_id for c in cierres])
    clientes = _nombres(db, m.Cliente, [c.servicio.cliente_id for c in cierres])
    filas = []
    for c in cierres:
        s = c.servicio
        if c.contrato_id:
            anio, numero = c.contrato.anio, c.contrato.mes
            primero = date(anio, numero, 1)
            ultimo = date(anio, numero, monthrange(anio, numero)[1])
        else:
            anio = numero = None
            primero, ultimo = rangos.get(s.id, (None, None))
        r = archivo.reloj(c, conexion)
        d = datos[c.id]
        filas.append({
            "cierre_id": c.id, "servicio_id": s.id, "folio": s.folio,
            "cliente_id": s.cliente_id, "cliente": clientes.get(s.cliente_id),
            "tipo": s.tipo.value,
            "cancelado": s.estatus == m.EstatusServicio.CANCELADO,
            "anio": anio, "mes": numero,
            "desde": _iso(primero), "hasta": _iso(ultimo),
            "consultor_id": s.consultor_id,
            "consultor": personas.get(s.consultor_id),
            "estatus": c.estatus.value,
            "factura": c.factura_odoo,
            "facturado_en": _iso(c.facturado_en),
            "aprobado_en": _iso(c.aprobado_en),
            "total": str(_d(c.total_ejecutado)),
            "moneda": monedas.get(c.id),
            "viaticos": str(d["comprobado"]),
            "reloj": ({"desde": r["desde"], "inicio": r["inicio"].isoformat(),
                       "archivo": r["archivo"].isoformat()} if r else None),
            "fotos": {"en_centauro": d["en_centauro"],
                      "archivadas": d["archivadas"],
                      "archivadas_en": _iso(d["archivadas_en"])},
        })
    return filas


def _resumen(filas: list[dict]) -> dict:
    facturado, viaticos = {}, {}
    for f in filas:
        clave = f["moneda"] or ""
        facturado[clave] = facturado.get(clave, CERO) + _d(f["total"])
        viaticos[clave] = viaticos.get(clave, CERO) + _d(f["viaticos"])
    return {"servicios": len(filas),
            "facturado": {k: str(v) for k, v in facturado.items()},
            "viaticos": {k: str(v) for k, v in viaticos.items()},
            "fotos_en_centauro": sum(f["fotos"]["en_centauro"] for f in filas),
            "fotos_archivadas": sum(f["fotos"]["archivadas"] for f in filas)}


def _opciones(db: Session) -> dict:
    """Con que se puede filtrar: solo lo que aparece en el historial."""
    cerrados = m.Cierre.estatus.in_(archivo.CERRADOS)
    clientes = (db.query(m.Cliente.id, m.Cliente.nombre)
                .join(m.Servicio, m.Servicio.cliente_id == m.Cliente.id)
                .join(m.Cierre, m.Cierre.servicio_id == m.Servicio.id)
                .filter(cerrados).distinct().all())
    consultores = (db.query(m.Persona.id, m.Persona.nombre)
                   .join(m.Servicio, m.Servicio.consultor_id == m.Persona.id)
                   .join(m.Cierre, m.Cierre.servicio_id == m.Servicio.id)
                   .filter(cerrados).distinct().all())
    primero, ultimo = (db.query(func.min(_cuando()), func.max(_cuando()))
                       .filter(cerrados).one())
    return {
        "clientes": [{"id": i, "nombre": n}
                     for i, n in sorted(clientes, key=lambda x: (x[1] or "").lower())],
        "consultores": [{"id": i, "nombre": n}
                        for i, n in sorted(consultores,
                                           key=lambda x: (x[1] or "").lower())],
        "primer_mes": primero.strftime("%Y-%m") if primero else None,
        "ultimo_mes": ultimo.strftime("%Y-%m") if ultimo else None,
    }


def _del_archivo() -> dict:
    return {"activo": bool((settings.archivo_destino or "").strip()),
            "meses": settings.archivo_meses, "anios": settings.archivo_anios,
            "odoo": facturacion.hay_conexion(),
            "hoy": date.today().isoformat()}


def consultar(db: Session, f: dict, pagina: int = 1,
              por_pagina: int = POR_PAGINA) -> dict:
    """La lista, con lo que suma todo lo filtrado --no solo la pagina--."""
    conexion = facturacion.hay_conexion()
    filas = _renglones(db, _consulta(db, f).all(), conexion)
    pagina = max(1, pagina)
    por_pagina = max(1, min(por_pagina, 500))
    inicio = (pagina - 1) * por_pagina
    return {"filas": filas[inicio:inicio + por_pagina],
            "total": len(filas), "pagina": pagina, "por_pagina": por_pagina,
            "resumen": _resumen(filas), "opciones": _opciones(db),
            "archivo": _del_archivo()}


# ================================================================ el detalle

def _comprobantes(db: Session, asignaciones: list) -> list[dict]:
    """Sin cargar la foto: cada una pesa cientos de kilobytes y aqui solo
    hace falta saber si esta."""
    salida = []
    for trozo in archivo.en_trozos(asignaciones):
        for fila in (db.query(m.Comprobante.id, m.Comprobante.asignacion_id,
                              m.Comprobante.concepto, m.Comprobante.tipo,
                              m.Comprobante.monto, m.Comprobante.descripcion,
                              m.Comprobante.validado, m.Comprobante.rechazado,
                              m.Comprobante.motivo_rechazo,
                              m.Comprobante.subido_en,
                              m.Comprobante.imagen.isnot(None),
                              m.Comprobante.archivado_en)
                     .filter(m.Comprobante.asignacion_id.in_(trozo))
                     .order_by(m.Comprobante.id)):
            (i, vid, concepto, tipo, monto, descripcion, validado, rechazado,
             motivo, subido, tiene, archivada) = fila
            salida.append({
                "id": i, "viatico_id": vid,
                "concepto": concepto.value if concepto else None,
                "tipo": tipo.value if tipo else None,
                "monto": str(_d(monto)), "descripcion": descripcion,
                "validado": bool(validado) and not rechazado,
                "rechazado": bool(rechazado), "motivo_rechazo": motivo,
                "subido_en": _iso(subido), "tiene_imagen": bool(tiene),
                "archivada_en": _iso(archivada)})
    return salida


def _devoluciones(db: Session, asignaciones: list) -> list[dict]:
    salida = []
    for trozo in archivo.en_trozos(asignaciones):
        for fila in (db.query(m.DevolucionViatico.id,
                              m.DevolucionViatico.asignacion_id,
                              m.DevolucionViatico.monto,
                              m.DevolucionViatico.moneda,
                              m.DevolucionViatico.referencia,
                              m.DevolucionViatico.estatus,
                              m.DevolucionViatico.declarada_en,
                              m.DevolucionViatico.confirmada_en,
                              m.DevolucionViatico.comprobante.isnot(None),
                              m.DevolucionViatico.archivado_en)
                     .filter(m.DevolucionViatico.asignacion_id.in_(trozo))
                     .order_by(m.DevolucionViatico.id)):
            (i, vid, monto, moneda, referencia, estatus, declarada,
             confirmada, tiene, archivada) = fila
            salida.append({
                "id": i, "viatico_id": vid, "monto": str(_d(monto)),
                "moneda": moneda.value if moneda else None,
                "referencia": referencia, "estatus": estatus.value,
                "declarada_en": _iso(declarada),
                "confirmada_en": _iso(confirmada),
                "tiene_imagen": bool(tiene), "archivada_en": _iso(archivada)})
    return salida


def _viaticos(db: Session, asignaciones: list) -> list[tuple]:
    """(viatico, fecha de su dia), sin sus comprobantes."""
    salida = []
    for trozo in archivo.en_trozos(asignaciones):
        salida += (db.query(m.AsignacionViatico, m.Jornada.fecha)
                   .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
                   .filter(m.AsignacionViatico.id.in_(trozo)).all())
    return salida


def detalle(db: Session, cierre_id: int, usuario: m.Usuario) -> dict:
    """Un servicio del historial: sus numeros y, por persona, cada
    comprobante y cada devolucion con el estado de su foto."""
    from app import bolson

    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    if cierre.estatus not in archivo.CERRADOS:
        raise HTTPException(409, {
            "mensaje": "Ese servicio todavia no lo cierra finanzas",
            "que_hacer": "Se ve en Facturacion, en Por aprobar."})
    conexion = facturacion.hay_conexion()
    fila = _renglones(db, [cierre], conexion)[0]
    asignaciones = _por_cierre(db, [cierre])[cierre.id]["asignaciones"]

    viaticos = _viaticos(db, asignaciones)
    dia = {v.id: fecha for v, fecha in viaticos}
    comprobantes = _comprobantes(db, asignaciones)
    devoluciones = _devoluciones(db, asignaciones)
    for c in comprobantes:
        c["fecha"] = _iso(dia.get(c["viatico_id"]))
    for d in devoluciones:
        d["fecha"] = _iso(dia.get(d["viatico_id"]))

    nombres = _nombres(db, m.Persona, [v.persona_id for v, _ in viaticos])
    grupos: dict[int, list] = {}
    for v, _ in viaticos:
        grupos.setdefault(v.persona_id, []).append(v)
    personas = []
    entregado = comprobado = devuelto = CERO
    for persona_id, suyos in grupos.items():
        vivos = [v for v in suyos if v.estatus != m.EstatusViatico.CANCELADO]
        ids = {v.id for v in suyos}
        suyo_entregado = sum((_d(v.monto_total) for v in vivos
                              if v.estatus in bolson.DEPOSITADOS), CERO)
        suyo_comprobado = sum((_d(v.monto_comprobado) for v in vivos), CERO)
        suyo_devuelto = sum((_d(v.monto_devuelto) for v in vivos), CERO)
        entregado += suyo_entregado
        comprobado += suyo_comprobado
        devuelto += suyo_devuelto
        personas.append({
            "persona_id": persona_id, "nombre": nombres.get(persona_id),
            "moneda": suyos[0].moneda.value if suyos[0].moneda else None,
            "entregado": str(suyo_entregado),
            "comprobado": str(suyo_comprobado),
            "devuelto": str(suyo_devuelto),
            "comprobantes": sorted(
                (c for c in comprobantes if c["viatico_id"] in ids),
                key=lambda c: (c["fecha"] or "", c["subido_en"] or "", c["id"])),
            "devoluciones": [d for d in devoluciones if d["viatico_id"] in ids],
        })
    personas.sort(key=lambda p: (p["nombre"] or "").lower())

    plaza = db.get(m.Plaza, cierre.servicio.plaza_id)
    return {**fila,
            "plaza": plaza.nombre if plaza else None,
            "entregado": str(entregado), "comprobado": str(comprobado),
            "devuelto": str(devuelto),
            "personas": personas,
            "archivo": _del_archivo(),
            "puede_ver_archivo": auth.puede_el_usuario(db, usuario,
                                                       "archivo.ver")}


# ================================================================ el Excel

TEXTOS = {
    "es": {
        "hojas": ("Servicios", "Comprobantes"),
        "servicios": ("Folio", "Cliente", "Tipo", "Del", "Al", "Consultor",
                      "Estatus", "Factura", "Fecha de factura", "Aprobado",
                      "Total", "Moneda", "Viáticos comprobados",
                      "Fotos en Centauro", "Fotos archivadas",
                      "Fecha de archivo"),
        "comprobantes": ("Folio", "Cliente", "Persona", "Día", "Concepto",
                         "Tipo", "Monto", "Moneda", "Estado", "Referencia",
                         "Subida", "Foto", "Archivada el"),
        "tipo": {"eventual": "Eventual", "implantado": "Implantado"},
        "estatus": {"facturado": "Facturado",
                    "sin_factura": "Aprobado sin factura",
                    "cancelado": "cancelado"},
        "concepto": {"alimentos": "Alimentos", "hospedaje": "Hospedaje",
                     "combustible": "Gasolina", "casetas": "Casetas",
                     "traslado_personal": "Traslado del personal",
                     "otros": "Otros", "devolucion": "Devolución"},
        "ticket": {"factura": "Factura", "nota": "Ticket",
                   "transferencia": "Transferencia"},
        "estado": {"validado": "Validado", "rechazado": "Rechazado",
                   "sin_revisar": "Sin revisar", "confirmada": "Confirmada",
                   "rechazada": "Rechazada", "declarada": "Declarada"},
        "foto": {"centauro": "En Centauro", "archivo": "En el archivo",
                 "sin_foto": "Sin foto"},
        "archivo": "Historial_de_facturacion",
    },
    "en": {
        "hojas": ("Services", "Receipts"),
        "servicios": ("Folio", "Client", "Type", "From", "To", "Consultant",
                      "Status", "Invoice", "Invoice date", "Approved",
                      "Total", "Currency", "Expenses proven",
                      "Photos in Centauro", "Photos archived",
                      "Archive date"),
        "comprobantes": ("Folio", "Client", "Person", "Day", "Concept",
                         "Type", "Amount", "Currency", "Status", "Reference",
                         "Uploaded", "Photo", "Archived on"),
        "tipo": {"eventual": "One-off", "implantado": "Embedded"},
        "estatus": {"facturado": "Invoiced",
                    "sin_factura": "Approved, no invoice",
                    "cancelado": "cancelled"},
        "concepto": {"alimentos": "Meals", "hospedaje": "Lodging",
                     "combustible": "Fuel", "casetas": "Tolls",
                     "traslado_personal": "Staff transport",
                     "otros": "Other", "devolucion": "Return"},
        "ticket": {"factura": "Invoice", "nota": "Receipt",
                   "transferencia": "Transfer"},
        "estado": {"validado": "Validated", "rechazado": "Rejected",
                   "sin_revisar": "Not reviewed", "confirmada": "Confirmed",
                   "rechazada": "Rejected", "declarada": "Declared"},
        "foto": {"centauro": "In Centauro", "archivo": "In the archive",
                 "sin_foto": "No photo"},
        "archivo": "Invoicing_history",
    },
    "pt": {
        "hojas": ("Serviços", "Comprovantes"),
        "servicios": ("Folio", "Cliente", "Tipo", "De", "Até", "Consultor",
                      "Status", "Nota fiscal", "Data da nota", "Aprovado",
                      "Total", "Moeda", "Despesas comprovadas",
                      "Fotos no Centauro", "Fotos arquivadas",
                      "Data do arquivo"),
        "comprobantes": ("Folio", "Cliente", "Pessoa", "Dia", "Conceito",
                         "Tipo", "Valor", "Moeda", "Status", "Referência",
                         "Enviada", "Foto", "Arquivada em"),
        "tipo": {"eventual": "Eventual", "implantado": "Implantado"},
        "estatus": {"facturado": "Faturado",
                    "sin_factura": "Aprovado sem nota fiscal",
                    "cancelado": "cancelado"},
        "concepto": {"alimentos": "Alimentação", "hospedaje": "Hospedagem",
                     "combustible": "Combustível", "casetas": "Pedágios",
                     "traslado_personal": "Transporte da equipe",
                     "otros": "Outros", "devolucion": "Devolução"},
        "ticket": {"factura": "Nota fiscal", "nota": "Recibo",
                   "transferencia": "Transferência"},
        "estado": {"validado": "Validado", "rechazado": "Rejeitado",
                   "sin_revisar": "Sem revisar", "confirmada": "Confirmada",
                   "rechazada": "Rejeitada", "declarada": "Declarada"},
        "foto": {"centauro": "No Centauro", "archivo": "No arquivo",
                 "sin_foto": "Sem foto"},
        "archivo": "Historico_de_faturamento",
    },
}


def _momento(iso: str | None):
    return datetime.fromisoformat(iso) if iso else None


def _dia(iso: str | None):
    return date.fromisoformat(iso[:10]) if iso else None


def _foto(t: dict, x: dict) -> str:
    if x["archivada_en"]:
        return t["foto"]["archivo"]
    return t["foto"]["centauro"] if x["tiene_imagen"] else t["foto"]["sin_foto"]


def excel_del_historial(db: Session, f: dict, idioma: str = "es") -> tuple[bytes, str]:
    """El .xlsx de lo filtrado, en dos hojas: servicios y comprobantes.
    Las fotos no van: se ven en Centauro o se traen del archivo."""
    t = TEXTOS.get(idioma, TEXTOS["es"])
    conexion = facturacion.hay_conexion()
    cierres = _consulta(db, f).all()
    filas = _renglones(db, cierres, conexion)

    servicios = []
    for x in filas:
        estatus = (t["estatus"]["facturado"] if x["facturado_en"]
                   else t["estatus"]["sin_factura"])
        if x["cancelado"]:
            estatus += f" · {t['estatus']['cancelado']}"
        servicios.append([
            x["folio"], x["cliente"], t["tipo"].get(x["tipo"], x["tipo"]),
            _dia(x["desde"]), _dia(x["hasta"]), x["consultor"], estatus,
            x["factura"], _dia(x["facturado_en"]), _dia(x["aprobado_en"]),
            x["total"], x["moneda"], x["viaticos"],
            x["fotos"]["en_centauro"], x["fotos"]["archivadas"],
            _dia(x["reloj"]["archivo"]) if x["reloj"] else None])

    renglones = _del_excel(db, cierres, filas)
    comprobantes = []
    for x, persona, c, es_devolucion in renglones:
        if es_devolucion:
            estado = t["estado"].get(c["estatus"], c["estatus"])
            comprobantes.append([
                x["folio"], x["cliente"], persona, _dia(c["fecha"]),
                t["concepto"]["devolucion"], t["ticket"]["transferencia"],
                c["monto"], c["moneda"] or x["moneda"], estado,
                c["referencia"], _momento(c["declarada_en"]),
                _foto(t, c), _momento(c["archivada_en"])])
        else:
            if c["rechazado"]:
                estado = t["estado"]["rechazado"]
                if c["motivo_rechazo"]:
                    estado += f": {c['motivo_rechazo']}"
            elif c["validado"]:
                estado = t["estado"]["validado"]
            else:
                estado = t["estado"]["sin_revisar"]
            concepto = t["concepto"].get(c["concepto"], c["concepto"])
            if c["concepto"] == "otros" and c["descripcion"]:
                concepto = c["descripcion"]
            comprobantes.append([
                x["folio"], x["cliente"], persona, _dia(c["fecha"]), concepto,
                t["ticket"].get(c["tipo"], c["tipo"]), c["monto"], x["moneda"],
                estado, None, _momento(c["subido_en"]), _foto(t, c),
                _momento(c["archivada_en"])])

    tipos_s = ("texto", "texto", "texto", "fecha", "fecha", "texto", "texto",
               "texto", "fecha", "fecha", "dinero", "texto", "dinero",
               "entero", "entero", "fecha")
    anchos_s = (16, 28, 12, 11, 11, 22, 24, 12, 13, 11, 14, 8, 14, 10, 10, 12)
    tipos_c = ("texto", "texto", "texto", "fecha", "texto", "texto", "dinero",
               "texto", "texto", "texto", "momento", "texto", "momento")
    anchos_c = (16, 28, 22, 11, 20, 13, 12, 8, 26, 16, 16, 14, 16)
    contenido = excel.libro([
        {"nombre": t["hojas"][0],
         "columnas": list(zip(t["servicios"], tipos_s, anchos_s)),
         "filas": servicios},
        {"nombre": t["hojas"][1],
         "columnas": list(zip(t["comprobantes"], tipos_c, anchos_c)),
         "filas": comprobantes},
    ])
    return contenido, f"{t['archivo']}_{date.today():%Y%m%d}.xlsx"


def _del_excel(db: Session, cierres: list, filas: list[dict]) -> list[tuple]:
    """(renglon, persona, comprobante o devolucion, es_devolucion) de todo
    lo filtrado, en orden. Todo junto y no servicio por servicio: el
    Excel puede traer el historial completo."""
    de_cada = archivo.asignaciones_por_cierre(db, cierres)
    del_cierre = {a: cierre_id for cierre_id, lista in de_cada.items()
                  for a in lista}
    todas = list(del_cierre)
    viaticos = _viaticos(db, todas)
    dia = {v.id: fecha for v, fecha in viaticos}
    persona_de = {v.id: v.persona_id for v, _ in viaticos}
    nombres = _nombres(db, m.Persona, persona_de.values())
    renglon = {x["cierre_id"]: x for x in filas}
    orden = {x["cierre_id"]: i for i, x in enumerate(filas)}
    salida = []
    for lista, es_devolucion in ((_comprobantes(db, todas), False),
                                 (_devoluciones(db, todas), True)):
        for c in lista:
            c["fecha"] = _iso(dia.get(c["viatico_id"]))
            cierre_id = del_cierre[c["viatico_id"]]
            salida.append((renglon[cierre_id],
                           nombres.get(persona_de.get(c["viatico_id"])),
                           c, es_devolucion))
    salida.sort(key=lambda r: (orden[r[0]["cierre_id"]], (r[1] or "").lower(),
                               r[2]["fecha"] or "", r[3], r[2]["id"]))
    return salida

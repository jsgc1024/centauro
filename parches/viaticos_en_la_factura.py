# -*- coding: utf-8 -*-
"""Los viaticos en la factura, segun la cotizacion.

Decision de Salvador, 23 de septiembre: la cotizacion dice si los
viaticos van incluidos en el precio o se cobran aparte; son dos opciones
distintas.

  * Eventual: si se cobran, la factura suma lo comprobado valido en su
    propio renglon; si van incluidos, nada aparte. La rentabilidad cuenta
    como facturado lo que se cobra, y la comision del consultor --sobre
    lo facturado descontando los viaticos-- deja de restar unos que no
    se facturaban (aprobado por Salvador el mismo dia).
  * Implantado: no tiene cotizacion por dia; sus precios viven en los
    terminos de cada mes, y ahi va la misma opcion (por omision
    incluidos, como el eventual). Pasa sola al mes siguiente.

Idempotente. Todas las escrituras al final.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    "models": B / "app/models.py",
    "cierre": B / "app/cierre.py",
    "facturacion": B / "app/facturacion.py",
    "rcierre": B / "app/routers/cierre.py",
    "cierre_mes": B / "app/cierre_mes.py",
    "rimplantados": B / "app/routers/implantados.py",
    "implantado": B / "app/implantado.py",
    "bitacora": RAIZ / "BITACORA.md",
}
NUEVOS = {'migrations/versions/e8c3a1f5d7b9_viaticos_del_implantado.py': '"""Como se cobran los viaticos del implantado.\n\nDecision de Salvador, 23 de septiembre (seccion 57 de la bitacora): la\ncotizacion dice si los viaticos van incluidos en el precio o se cobran\naparte, por lo comprobado. El implantado no tiene cotizacion por dia:\nsus precios viven en los terminos de cada mes, y ahi va la misma\nopcion. Los meses que ya existen quedan con los viaticos incluidos, que\nes lo que el sistema suponia hasta hoy.\n\nRevision ID: e8c3a1f5d7b9\nRevises: d4f1b8e2a6c9\n"""\nfrom typing import Sequence, Union\n\nimport sqlalchemy as sa\nfrom alembic import op\n\nrevision: str = "e8c3a1f5d7b9"\ndown_revision: Union[str, None] = "d4f1b8e2a6c9"\nbranch_labels: Union[str, Sequence[str], None] = None\ndepends_on: Union[str, Sequence[str], None] = None\n\n\ndef upgrade() -> None:\n    op.add_column("contrato_implantado",\n                  sa.Column("viaticos_incluidos", sa.Boolean(),\n                            server_default=sa.text("true"), nullable=False))\n\n\ndef downgrade() -> None:\n    op.drop_column("contrato_implantado", "viaticos_incluidos")\n', 'tests/test_viaticos_en_factura.py': '# -*- coding: utf-8 -*-\n"""Los viaticos en la factura.\n\nDecision de Salvador, 23 de septiembre: la cotizacion dice si los\nviaticos van incluidos en el precio o se cobran aparte; son dos opciones\ndistintas. Si se cobran, la factura suma lo comprobado valido; si van\nincluidos, nada aparte. En el implantado la misma opcion vive en los\nterminos del mes y pasa al siguiente.\n\nLa comision del consultor sigue siendo sobre lo facturado descontando\nlos viaticos. Con los viaticos cobrados ya dentro de la factura, deja de\nrestar unos que no se facturaban. Seccion 57 de la bitacora.\n\nEl viatico se da por comprobado directo en la base: aqui importa la\ncuenta de la factura, no el camino de la comprobacion, que ya tiene sus\npruebas.\n"""\nfrom datetime import date, datetime\n\nfrom ayudas import (asignar, configurar_origen, crear_servicio,\n                    ejecutar_jornada, jornada, manana)\n\nMOTIVO = "El equipo cerro por telefono; confirmado con el cliente"\nDIAS = [date(2029, 9, d) for d in (24, 25, 26, 27, 28)]\nSERVICIO_DEL_MES = 5 * 2900 + 66000      # cinco dias y la unidad del mes\n\n\ndef _viatico(cliente, sesion, datos, jornada_id, monto="900"):\n    r = cliente.post("/viaticos/asignar", headers=sesion("consultor"), json={\n        "jornada_id": jornada_id,\n        "persona_id": datos["personal"]["Juan Ramirez"]["id"],\n        "conceptos": [{"concepto": "alimentos", "monto": monto,\n                       "origen": "tabulador"}]})\n    assert r.status_code in (200, 201), r.text\n    return r.json()["id"]\n\n\ndef _comprobado(viatico_id, monto):\n    """El viatico ya comprobado completo y cerrado por el consultor."""\n    from decimal import Decimal\n\n    from app import models as m\n    from app.db import SessionLocal\n    with SessionLocal() as db:\n        v = db.get(m.AsignacionViatico, viatico_id)\n        v.monto_comprobado = Decimal(monto)\n        v.estatus = m.EstatusViatico.CERRADO\n        db.commit()\n\n\ndef _armar(cierre_id):\n    from app import facturacion\n    from app import models as m\n    from app.db import SessionLocal\n    with SessionLocal() as db:\n        return facturacion.armar(db, db.get(m.Cierre, cierre_id))\n\n\ndef _renglones(cuerpo):\n    return [(c["tipo"], c["cantidad"], c["importe"]) for c in cuerpo["conceptos"]\n            if c["tipo"] == "viaticos"]\n\n\n# ---------------------------------------------------------------- el eventual\n\ndef _eventual(cliente, sesion, datos, incluidos, offset):\n    """Un dia cotizado --con los viaticos incluidos o aparte--, con un\n    viatico de 900 que se comprueba completo, y el dia trabajado."""\n    h = sesion("consultor")\n    servicio = crear_servicio(\n        cliente, h, datos,\n        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],\n        consultor_id=datos["personal"]["Ana Solis"]["id"])\n    j = servicio["equipos"][0]["jornadas"][0]\n    r = cliente.post("/cotizaciones", headers=h, json={\n        "servicio_id": servicio["id"], "viaticos_incluidos": incluidos,\n        "lineas": [\n            {"fecha": j["fecha"], "tipo": "recurso",\n             "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]},\n            {"fecha": j["fecha"], "tipo": "vehiculo",\n             "categoria_id": datos["categorias"]["suv_blindada"]["id"]}]})\n    assert r.status_code == 201, r.text\n    r = cliente.post(f"/cotizaciones/{r.json()[\'cotizacion_id\']}/autorizar",\n                     json={"autorizada_por": "Cliente de prueba"}, headers=h)\n    assert r.status_code == 200, r.text\n    asignar(cliente, h, j["id"],\n            persona_id=datos["personal"]["Juan Ramirez"]["id"],\n            vehiculo_id=datos["suburban"]["id"])\n    configurar_origen(cliente, h, j["id"])\n    vid = _viatico(cliente, sesion, datos, j["id"])\n    assert ejecutar_jornada(cliente, sesion("juan"), j).status_code == 200\n    _comprobado(vid, "900")\n    return servicio\n\n\ndef _visto_bueno_y_aprobacion(cliente, sesion, servicio_id):\n    from app import models as m\n    from app.db import SessionLocal\n    with SessionLocal() as db:\n        cierre_id = (db.query(m.Cierre)\n                     .filter_by(servicio_id=servicio_id).first().id)\n    envio = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",\n                         headers=sesion("consultor"))\n    assert envio.status_code == 200, envio.text\n    aprobacion = cliente.post(f"/cierre/{cierre_id}/aprobar",\n                              headers=sesion("finanzas"))\n    assert aprobacion.status_code == 200, aprobacion.text\n    return cierre_id, aprobacion.json()\n\n\ndef test_el_eventual_que_cobra_viaticos_los_factura(cliente, sesion, datos,\n                                                   monkeypatch):\n    """La cotizacion los cobra aparte: la factura suma lo comprobado en su\n    propio renglon, la rentabilidad lo cuenta como facturado y la comision\n    queda sobre el servicio --ya no le resta unos viaticos que antes ni\n    se facturaban--."""\n    from app import facturacion\n    monkeypatch.setattr(facturacion.settings, "odoo_url", "")\n\n    servicio = _eventual(cliente, sesion, datos, incluidos=False, offset=1400)\n    h = sesion("consultor")\n    comparativo = cliente.get(\n        f"/cierre/servicio/{servicio[\'id\']}/comparativo", headers=h).json()\n    del_servicio = float(comparativo["ejecutado"]["total"])\n    assert comparativo["viaticos"]["facturable_al_cliente"] == 900\n\n    cierre_id, aprobacion = _visto_bueno_y_aprobacion(cliente, sesion,\n                                                      servicio["id"])\n    cuerpo = _armar(cierre_id)\n    assert _renglones(cuerpo) == [("viaticos", 1, "900.00")]\n    assert float(cuerpo["total"]) == del_servicio + 900\n\n    bandeja = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))\n    suyo = next(x for x in bandeja.json()["por_facturar"]\n                if x["cierre_id"] == cierre_id)\n    assert float(suyo["total"]) == del_servicio + 900\n\n    rent = cliente.get(f"/cierre/servicio/{servicio[\'id\']}/rentabilidad",\n                       headers=h).json()\n    assert float(rent["facturacion"]) == del_servicio + 900\n    assert float(rent["viaticos_cobrados"]) == 900\n    base = float(aprobacion["comision_consultor"]["base"])\n    assert abs(base - del_servicio) < 0.01, \\\n        "la comision no resta los viaticos que el cliente paga aparte"\n\n\ndef test_el_eventual_con_viaticos_incluidos_no_los_suma(cliente, sesion, datos,\n                                                       monkeypatch):\n    """Van dentro del precio: la factura no lleva renglon de viaticos y la\n    comision descuenta su costo, como siempre."""\n    from app import facturacion\n    monkeypatch.setattr(facturacion.settings, "odoo_url", "")\n\n    servicio = _eventual(cliente, sesion, datos, incluidos=True, offset=1403)\n    comparativo = cliente.get(\n        f"/cierre/servicio/{servicio[\'id\']}/comparativo",\n        headers=sesion("consultor")).json()\n    del_servicio = float(comparativo["ejecutado"]["total"])\n\n    cierre_id, aprobacion = _visto_bueno_y_aprobacion(cliente, sesion,\n                                                      servicio["id"])\n    cuerpo = _armar(cierre_id)\n    assert _renglones(cuerpo) == []\n    assert float(cuerpo["total"]) == del_servicio\n    base = float(aprobacion["comision_consultor"]["base"])\n    assert abs(base - (del_servicio - 900)) < 0.01\n\n\n# ---------------------------------------------------------------- el implantado\n\ndef _alta(cliente, sesion, datos, **extra):\n    r = cliente.post("/implantados", headers=sesion("consultor"), json={\n        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],\n        "plaza_id": datos["cdmx"]["id"],\n        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",\n        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",\n        "consultor_id": datos["personal"]["Ana Solis"]["id"],\n        "fecha_inicio": str(DIAS[0]), "dias_servicio": "lunes_viernes",\n        "modalidad_id": datos["modalidades"]["full_day"]["id"],\n        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],\n                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],\n                      "vehiculo_id": datos["suburban"]["id"]}],\n        "unidades": [datos["suburban"]["id"]],\n        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000",\n        **extra,\n    })\n    assert r.status_code == 201, r.text\n    return r.json()\n\n\ndef _mes_con_visto_bueno(cliente, sesion, datos, **extra):\n    """Septiembre de 2029 con un viatico de 900 comprobado, trabajado\n    completo y con el visto bueno dado. Devuelve el id del cierre."""\n    from app import models as m\n    from app.db import SessionLocal\n\n    alta = _alta(cliente, sesion, datos, **extra)\n    panel = cliente.get(f"/implantados/{alta[\'servicio_id\']}/mes/2029/9",\n                        headers=sesion("consultor")).json()\n    jornadas = {date.fromisoformat(d["fecha"]): d["jornada_id"]\n                for d in panel["dias"]}\n    vid = _viatico(cliente, sesion, datos, jornadas[DIAS[1]])\n    for dia in DIAS:\n        r = cliente.post(\n            f"/operacion/jornadas/{jornadas[dia]}/cerrar-a-mano",\n            headers=sesion("central"), json={"justificacion": MOTIVO},\n            params={"ahora": datetime.combine(dia, datetime.min.time())\n                    .replace(hour=21).isoformat()})\n        assert r.status_code == 200, r.text\n    _comprobado(vid, "900")\n\n    with SessionLocal() as db:\n        cierre_id = (db.query(m.Cierre)\n                     .filter_by(contrato_id=alta["contrato_id"]).first().id)\n    ahora = datetime(2029, 9, 28, 22, 0)\n    envio = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",\n                         headers=sesion("consultor"),\n                         params={"ahora": ahora.isoformat()})\n    assert envio.status_code == 200, envio.text\n    return cierre_id\n\n\ndef test_el_mes_que_cobra_viaticos_los_factura(cliente, sesion, datos,\n                                              monkeypatch):\n    from app import facturacion\n    monkeypatch.setattr(facturacion.settings, "odoo_url", "")\n\n    cierre_id = _mes_con_visto_bueno(cliente, sesion, datos,\n                                     viaticos_incluidos=False)\n    cuerpo = _armar(cierre_id)\n    assert [c["tipo"] for c in cuerpo["conceptos"]] == \\\n        ["dias_base", "vehiculo_mes", "viaticos"]\n    assert _renglones(cuerpo) == [("viaticos", 1, "900.00")]\n    assert float(cuerpo["total"]) == SERVICIO_DEL_MES + 900\n\n    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))\n    assert r.status_code == 200, r.text\n    comision = r.json()["comision_consultor"]\n    assert float(comision["base"]) == SERVICIO_DEL_MES\n    assert float(comision["monto"]) == SERVICIO_DEL_MES / 100\n\n\ndef test_el_mes_con_viaticos_incluidos_no_los_suma(cliente, sesion, datos,\n                                                  monkeypatch):\n    """Por omision van incluidos, como en la cotizacion del eventual."""\n    from app import facturacion\n    monkeypatch.setattr(facturacion.settings, "odoo_url", "")\n\n    cierre_id = _mes_con_visto_bueno(cliente, sesion, datos)\n    cuerpo = _armar(cierre_id)\n    assert _renglones(cuerpo) == []\n    assert float(cuerpo["total"]) == SERVICIO_DEL_MES\n\n    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))\n    assert r.status_code == 200, r.text\n    assert float(r.json()["comision_consultor"]["base"]) == SERVICIO_DEL_MES - 900\n\n\ndef test_el_mes_siguiente_hereda_como_se_cobran_los_viaticos(cliente, sesion,\n                                                            datos):\n    from app import implantado as motor\n    from app import models as m\n    from app.db import SessionLocal\n\n    alta = _alta(cliente, sesion, datos, viaticos_incluidos=False)\n    with SessionLocal() as db:\n        abierto = motor.abrir_siguiente(\n            db, db.get(m.Servicio, alta["servicio_id"]), hoy=date(2029, 9, 27))\n        octubre = db.get(m.ContratoImplantado, abierto["contrato_id"])\n        assert octubre.viaticos_incluidos is False\n'}

textos = {k: io.open(v, encoding="utf-8").read() for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(viejo) == 1, f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces"
    textos[clave] = t.replace(viejo, nuevo)


# ================================================================ el modelo
cambiar("models",
        "    precio_mes_completo: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)\n"
        "\n"
        "    generado: Mapped[bool] = mapped_column(Boolean, default=False)\n",
        "    precio_mes_completo: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)\n"
        "    # Como se cobran los viaticos: dentro del precio del mes, o aparte,\n"
        "    # por lo comprobado. La misma opcion que la cotizacion del eventual\n"
        "    # (seccion 57); pasa sola al mes siguiente.\n"
        "    viaticos_incluidos: Mapped[bool] = mapped_column(\n"
        "        Boolean, default=True, server_default=text(\"true\"))\n"
        "\n"
        "    generado: Mapped[bool] = mapped_column(Boolean, default=False)\n",
        marca="    viaticos_incluidos: Mapped[bool] = mapped_column(\n"
              "        Boolean, default=True, server_default=text(\"true\"))\n")

# ================================================================ el eventual
cambiar("cierre",
        "def comparar(db: Session, servicio_id: int) -> dict:\n",
        "def viaticos_por_cobrar(db: Session, servicio_id: int,\n"
        "                        cotizacion) -> Decimal:\n"
        "    \"\"\"Los viaticos que se le cobran al cliente aparte (seccion 57).\n"
        "\n"
        "    Lo dice la cotizacion, y son dos opciones distintas: incluidos, el\n"
        "    cliente ya los paga dentro del precio y la factura no suma nada;\n"
        "    por comprobar, se le factura lo comprobado valido --sin lo\n"
        "    rechazado ni lo enviado a descuento, que no es gasto del servicio--.\n"
        "    \"\"\"\n"
        "    comprobado = sum((_d(v.monto_comprobado) for v in (\n"
        "        db.query(m.AsignacionViatico)\n"
        "        .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)\n"
        "        .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)\n"
        "        .filter(m.Equipo.servicio_id == servicio_id).all())), CERO)\n"
        "    return _viatico_facturable(cotizacion, comprobado)\n"
        "\n"
        "\n"
        "def comparar(db: Session, servicio_id: int) -> dict:\n",
        marca="def viaticos_por_cobrar(db: Session, servicio_id: int,\n")
cambiar("cierre",
        "    real = ejecutado(db, servicio, cotizacion.tarifario_id)\n"
        "    facturacion = real[\"total\"]\n",
        "    real = ejecutado(db, servicio, cotizacion.tarifario_id)\n"
        "    # Lo que se le factura: lo ejecutado y, si la cotizacion cobra los\n"
        "    # viaticos aparte, lo comprobado (seccion 57). Sin esto la utilidad\n"
        "    # y la comision restaban unos viaticos que no se facturaban.\n"
        "    viaticos_cobrados = viaticos_por_cobrar(db, servicio_id, cotizacion)\n"
        "    facturacion = real[\"total\"] + viaticos_cobrados\n")
cambiar("cierre",
        "        \"facturacion\": facturacion,\n",
        "        \"facturacion\": facturacion,\n"
        "        \"viaticos_cobrados\": viaticos_cobrados,\n")

cambiar("facturacion",
        "    ejecutado = motor_cierre.ejecutado(db, servicio, cotizacion.tarifario_id)\n"
        "    cliente = servicio.cliente\n"
        "\n"
        "    return {\n",
        "    ejecutado = motor_cierre.ejecutado(db, servicio, cotizacion.tarifario_id)\n"
        "    cliente = servicio.cliente\n"
        "    conceptos = [{\n"
        "        \"fecha\": linea[\"fecha\"],\n"
        "        \"equipo\": linea[\"equipo\"],\n"
        "        \"tipo\": linea[\"tipo\"],\n"
        "        \"descripcion\": linea[\"descripcion\"],\n"
        "        \"cantidad\": linea[\"cantidad\"],\n"
        "        \"importe\": str(linea[\"importe\"]),\n"
        "        \"horas_extra\": linea.get(\"horas_extra\") or 0,\n"
        "    } for linea in ejecutado[\"detalle\"]]\n"
        "    # Los viaticos, en su propio renglon, cuando la cotizacion los cobra\n"
        "    # aparte: lo comprobado valido (seccion 57). Incluidos, ya van en el\n"
        "    # precio y no se suman.\n"
        "    viaticos = motor_cierre.viaticos_por_cobrar(db, servicio.id, cotizacion)\n"
        "    if viaticos:\n"
        "        conceptos.append({\"fecha\": None, \"equipo\": None,\n"
        "                          \"tipo\": \"viaticos\",\n"
        "                          \"descripcion\": \"Viaticos comprobados\",\n"
        "                          \"cantidad\": 1, \"importe\": str(viaticos),\n"
        "                          \"horas_extra\": 0})\n"
        "\n"
        "    return {\n",
        marca="    viaticos = motor_cierre.viaticos_por_cobrar(db, servicio.id, cotizacion)\n")
cambiar("facturacion",
        "        \"total\": str(ejecutado[\"total\"]),\n"
        "        \"conceptos\": [{\n"
        "            \"fecha\": linea[\"fecha\"],\n"
        "            \"equipo\": linea[\"equipo\"],\n"
        "            \"tipo\": linea[\"tipo\"],\n"
        "            \"descripcion\": linea[\"descripcion\"],\n"
        "            \"cantidad\": linea[\"cantidad\"],\n"
        "            \"importe\": str(linea[\"importe\"]),\n"
        "            \"horas_extra\": linea.get(\"horas_extra\") or 0,\n"
        "        } for linea in ejecutado[\"detalle\"]],\n"
        "    }\n",
        "        \"total\": str(ejecutado[\"total\"] + viaticos),\n"
        "        \"conceptos\": conceptos,\n"
        "    }\n")

cambiar("rcierre",
        "    cierre.total_ejecutado = comparativo[\"ejecutado\"][\"total\"]\n",
        "    # Lo que se factura: lo ejecutado y, si la cotizacion cobra los\n"
        "    # viaticos aparte, lo comprobado (seccion 57).\n"
        "    cierre.total_ejecutado = (comparativo[\"ejecutado\"][\"total\"]\n"
        "                              + comparativo[\"viaticos\"][\"facturable_al_cliente\"])\n")

# ================================================================ el mes del implantado
cambiar("cierre_mes",
        "    return {\n"
        "        \"servicio\": contrato.servicio.folio,\n"
        "        \"periodo\": periodo(contrato),\n"
        "        \"esquema\": contrato.esquema.value,\n",
        "    # Los que se cobran aparte, si los terminos del mes asi lo dicen\n"
        "    # (seccion 57): lo comprobado valido. Incluidos, van en el precio.\n"
        "    por_cobrar = CERO if contrato.viaticos_incluidos else comprobado\n"
        "\n"
        "    return {\n"
        "        \"servicio\": contrato.servicio.folio,\n"
        "        \"periodo\": periodo(contrato),\n"
        "        \"esquema\": contrato.esquema.value,\n",
        marca="    por_cobrar = CERO if contrato.viaticos_incluidos else comprobado\n")
cambiar("cierre_mes",
        "                     \"descontado_al_personal\": descontado,\n"
        "                     \"absorbido_por_la_empresa\": absorbido},\n"
        "        \"desviaciones\": desviaciones,\n",
        "                     \"descontado_al_personal\": descontado,\n"
        "                     \"absorbido_por_la_empresa\": absorbido,\n"
        "                     \"modo_cobro\": (\"incluidos_en_el_precio\"\n"
        "                                    if contrato.viaticos_incluidos\n"
        "                                    else \"por_comprobar\"),\n"
        "                     \"facturable_al_cliente\": por_cobrar},\n"
        "        # Lo que sale en la factura del mes: el servicio y, si se cobran\n"
        "        # aparte, los viaticos comprobados.\n"
        "        \"a_facturar\": {\"servicio\": trabajado, \"viaticos\": por_cobrar,\n"
        "                       \"total\": trabajado + por_cobrar},\n"
        "        \"desviaciones\": desviaciones,\n")
cambiar("cierre_mes",
        "    cierre.total_ejecutado = comparativo[\"trabajado\"][\"importe\"]\n",
        "    cierre.total_ejecutado = comparativo[\"a_facturar\"][\"total\"]\n")
cambiar("cierre_mes",
        "    conciliar las dos bases el dia que no cuadren. Los viaticos por\n"
        "    comprobar no van todavia --tampoco en la del eventual--: entran con\n"
        "    la factura en Odoo (etapa 4), para los dos a la vez.\n",
        "    conciliar las dos bases el dia que no cuadren. Los viaticos van en\n"
        "    su renglon cuando los terminos del mes los cobran aparte (seccion\n"
        "    57); incluidos, ya van en el precio.\n")
cambiar("cierre_mes",
        "    pais = db.get(m.Pais, servicio.pais_id)\n"
        "    cliente = servicio.cliente\n"
        "    return {\n"
        "        \"referencia\": f\"{servicio.folio} {de_que}\",\n",
        "    a_facturar = comparativo[\"a_facturar\"]\n"
        "    if a_facturar[\"viaticos\"]:\n"
        "        conceptos.append({\n"
        "            \"tipo\": \"viaticos\",\n"
        "            \"descripcion\": f\"Viaticos comprobados {de_que}\",\n"
        "            \"cantidad\": 1, \"precio\": str(a_facturar[\"viaticos\"]),\n"
        "            \"importe\": str(a_facturar[\"viaticos\"])})\n"
        "\n"
        "    pais = db.get(m.Pais, servicio.pais_id)\n"
        "    cliente = servicio.cliente\n"
        "    return {\n"
        "        \"referencia\": f\"{servicio.folio} {de_que}\",\n",
        marca="    a_facturar = comparativo[\"a_facturar\"]\n")
cambiar("cierre_mes",
        "        \"total\": str(trabajado[\"importe\"]),\n"
        "        \"conceptos\": conceptos,\n",
        "        \"total\": str(a_facturar[\"total\"]),\n"
        "        \"conceptos\": conceptos,\n")

# ================================================================ los terminos del mes
cambiar("rimplantados",
        "    precio_mes_completo: Decimal | None = None\n"
        "\n"
        "\n"
        "class DiaAdicionalIn(BaseModel):\n",
        "    precio_mes_completo: Decimal | None = None\n"
        "    # Dentro del precio, o aparte por lo comprobado (seccion 57).\n"
        "    viaticos_incluidos: bool = True\n"
        "\n"
        "\n"
        "class DiaAdicionalIn(BaseModel):\n")
cambiar("rimplantados",
        "    precio_mes_completo: Decimal | None = None\n"
        "\n"
        "\n"
        "class AltaImplantadoIn(BaseModel):\n",
        "    precio_mes_completo: Decimal | None = None\n"
        "    # Dentro del precio, o aparte por lo comprobado (seccion 57).\n"
        "    viaticos_incluidos: bool = True\n"
        "\n"
        "\n"
        "class AltaImplantadoIn(BaseModel):\n")
cambiar("rimplantados",
        "    precio_mes_completo: Decimal | None = None\n"
        "\n"
        "    acuerdo: AcuerdoIn = AcuerdoIn()\n",
        "    precio_mes_completo: Decimal | None = None\n"
        "    # Como se cobran los viaticos, la misma opcion que la cotizacion del\n"
        "    # eventual: dentro del precio, o aparte por lo comprobado (seccion 57).\n"
        "    viaticos_incluidos: bool = True\n"
        "\n"
        "    acuerdo: AcuerdoIn = AcuerdoIn()\n")
cambiar("rimplantados",
        "        precio_mes_completo=datos.precio_mes_completo,\n",
        "        precio_mes_completo=datos.precio_mes_completo,\n"
        "        viaticos_incluidos=datos.viaticos_incluidos,\n")
cambiar("implantado",
        "        precio_mes_completo=anterior.precio_mes_completo,\n",
        "        precio_mes_completo=anterior.precio_mes_completo,\n"
        "        viaticos_incluidos=anterior.viaticos_incluidos,\n")

# ================================================================ bitacora
cambiar("bitacora",
        "## 14. Lo que falta\n",
        "## 57. Los viáticos en la factura, según la cotización\n"
        "\n"
        "Decisión de Salvador, 23 de septiembre: la cotización dice si los\n"
        "viáticos van incluidos en el precio o se cobran aparte; son dos\n"
        "opciones distintas.\n"
        "\n"
        "- **Eventual.** Si se cobran, la factura suma lo comprobado válido\n"
        "  —sin notas rechazadas ni lo enviado a descuento— en su propio\n"
        "  renglón, y el total por facturar lo incluye. Si van incluidos, nada\n"
        "  aparte.\n"
        "- **La comisión y la rentabilidad.** Lo facturado ya cuenta los\n"
        "  viáticos que se cobran. La comisión sigue siendo sobre lo facturado\n"
        "  descontando los viáticos, así que cuando se cobran aparte deja de\n"
        "  restar unos que antes ni se facturaban (aprobado por Salvador).\n"
        "  Con viáticos incluidos, nada cambia.\n"
        "- **Implantado.** No tiene cotización por día: sus precios viven en\n"
        "  los términos de cada mes, y ahí va la misma opción\n"
        "  (`viaticos_incluidos`), incluidos por omisión como en el eventual.\n"
        "  Pasa sola al mes siguiente. La factura del mes y la comisión del\n"
        "  mes siguen la misma regla.\n"
        "\n"
        "La opción todavía no se ve en la consola: llega con las pantallas.\n"
        "\n"
        "## 14. Lo que falta\n",
        marca="## 57. Los viáticos en la factura, según la cotización\n")

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

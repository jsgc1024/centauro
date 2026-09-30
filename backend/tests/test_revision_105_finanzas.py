# -*- coding: utf-8 -*-
"""Seccion 105 (Ola 5, g6): finanzas y viaticos.

Las decisiones 8, 9 y 10 de Salvador (29 de septiembre): la bandeja de
finanzas sin barrido y ordenada por la fecha del servicio, el combustible
que se propone una vez por unidad a quien va al volante, y el dinero
nuevo que ya no entra en un servicio cancelado, en facturacion o cerrado.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from zoneinfo import ZoneInfo

from ayudas import (asignar, crear_servicio, depositar, jornada, manana,
                    servicio_para_cierre)

WEB = Path(__file__).resolve().parents[1] / "app" / "web"
MX = ZoneInfo("America/Mexico_City")


def _js(nombre):
    return (WEB / nombre).read_text(encoding="utf-8")


def _combustible(km, rendimiento):
    """La cuenta del deposito: km / rendimiento * 24.50 + 20 %, al entero
    de arriba (el precio y la holgura son los de la semilla)."""
    crudo = (Decimal(km) / Decimal(rendimiento) * Decimal("24.50")
             * Decimal("1.20"))
    return crudo.to_integral_value(rounding=ROUND_CEILING)


def _servicio(cliente, h, datos, offset, km=150):
    """Un eventual de un dia completo a las 9:00, con sus km capturados."""
    return crear_servicio(cliente, h, datos, [jornada(
        manana(offset), datos["modalidades"]["full_day"]["id"],
        hora="09:00:00", km_estimados=km)])


def _abordo(cliente, h, jornada_id, persona_id, vehiculo_id):
    r = cliente.patch(f"/servicios/jornadas/{jornada_id}/personal/{persona_id}/unidad",
                      json={"vehiculo_id": vehiculo_id}, headers=h)
    assert r.status_code == 200, r.text


def _propuesta(cliente, h, jornada_id, persona_id):
    r = cliente.get(f"/viaticos/calcular?jornada_id={jornada_id}"
                    f"&persona_id={persona_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _gasolina(propuesta):
    fila = next(c for c in propuesta["conceptos"] if c["concepto"] == "combustible")
    return Decimal(str(fila["monto"])), fila


def _fijar(cliente, h, equipo_id, persona_id, monto):
    return cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                        json={"persona_id": persona_id, "monto": monto},
                        headers=h)


def _agregar(cliente, h, equipo_id, persona_id, monto):
    return cliente.post(f"/viaticos/equipos/{equipo_id}/persona/agregar",
                        json={"persona_id": persona_id, "monto": monto},
                        headers=h)


def _solicitar(cliente, h, equipo_id, persona_id=None):
    return cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                        json={"persona_id": persona_id} if persona_id else {},
                        headers=h)


def _bandeja(cliente, sesion, folios):
    """Los renglones de la bandeja de esos folios, en el orden en que
    finanzas los ve."""
    r = cliente.get("/viaticos/finanzas/bandeja", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    return [f for p in r.json()["paises"] for f in p["depositos"]
            if f["folio"] in folios]


def _enviada(viatico_ids):
    """La instruccion ya esta con finanzas: `enviada`. Sin barrido, la
    pone la conexion con Odoo; aqui se escribe directo en la base."""
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        for s in (db.query(m.SolicitudTransferencia)
                  .filter(m.SolicitudTransferencia.asignacion_id.in_(viatico_ids))
                  .all()):
            s.estatus = m.EstatusTransferencia.ENVIADA
        db.commit()


def _viaticos_de(equipo_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [v.id for v in db.query(m.AsignacionViatico)
                .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
                .filter(m.Jornada.equipo_id == equipo_id).all()]


def _estatus(cliente, sesion, servicio_id):
    return cliente.get(f"/servicios/{servicio_id}",
                       headers=sesion("consultor")).json()["estatus"]


# ============================================ decision 8: sin barrido

def test_el_barrido_y_la_ventana_ya_no_existen(cliente, sesion):
    """La regla de un dia antes vivia en una ruta que nadie corria y la
    bandeja ensenaba todo igual. Se fueron las dos puertas y el motor ya
    no las tiene: lo pedido entra a la bandeja en cuanto se pide."""
    from app import viaticos as motor
    assert not hasattr(motor, "ventana_de_transferencia")
    assert cliente.post("/viaticos/transferencias/barrido",
                        headers=sesion("finanzas")).status_code == 404
    assert cliente.get("/viaticos/transferencias/ventana?jornada_id=1",
                       headers=sesion("finanzas")).status_code == 404


def test_lo_solicitado_entra_a_la_bandeja_en_cuanto_se_pide(cliente, sesion, datos):
    """Un servicio dentro de treinta dias: la solicitud sale en la bandeja
    hoy mismo, con su fecha y como "despues"; finanzas decide cuando."""
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos, 30)
    equipo_id = servicio["equipos"][0]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    asignar(cliente, h, servicio["equipos"][0]["jornadas"][0]["id"],
            persona_id=juan, vehiculo_id=datos["suburban"]["id"])
    assert _fijar(cliente, h, equipo_id, juan, 500).status_code == 200
    assert _solicitar(cliente, h, equipo_id).status_code == 200

    filas = _bandeja(cliente, sesion, {servicio["folio"]})
    assert len(filas) == 1
    assert filas[0]["urgencia"] == "despues"
    assert filas[0]["fecha_servicio"] == manana(30).isoformat()
    assert filas[0]["pedida_tras_cierre"] is False


def test_la_bandeja_va_por_fecha_del_servicio_con_lo_vencido_arriba(
        cliente, sesion, datos):
    """Cuatro solicitudes --ayer, hoy, manana y en treinta dias-- pedidas
    en el orden contrario. La bandeja las devuelve vencida, hoy, manana y
    despues, cada una con su urgencia y su fecha, y suma lo vencido."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    folios = {}
    for offset in (30, 1, 0, -1):
        servicio = _servicio(cliente, h, datos, offset)
        equipo_id = servicio["equipos"][0]["id"]
        asignar(cliente, h, servicio["equipos"][0]["jornadas"][0]["id"],
                persona_id=juan, vehiculo_id=datos["suburban"]["id"])
        assert _fijar(cliente, h, equipo_id, juan, 400 + offset).status_code == 200
        assert _solicitar(cliente, h, equipo_id).status_code == 200, offset
        folios[servicio["folio"]] = offset

    filas = _bandeja(cliente, sesion, set(folios))
    assert [folios[f["folio"]] for f in filas] == [-1, 0, 1, 30]
    assert [f["urgencia"] for f in filas] == ["vencida", "hoy", "manana", "despues"]
    assert [f["fecha_servicio"] for f in filas] == [
        manana(-1).isoformat(), manana(0).isoformat(),
        manana(1).isoformat(), manana(30).isoformat()]

    r = cliente.get("/viaticos/finanzas/bandeja", headers=sesion("finanzas")).json()
    mx = next(p for p in r["paises"] if p["codigo"] == "MX")
    assert Decimal(str(mx["total_vencido"])) == Decimal("399")


def test_la_bandeja_de_la_consola_pinta_los_cuatro_bloques():
    """finanzas.js agrupa por `urgencia` --vencido en rojo y hasta arriba,
    hoy, manana, mas adelante-- y sin boton para lo pedido tras el
    cierre; cada texto nuevo esta en los tres idiomas."""
    js = _js("finanzas.js")
    for clave in ("fin_urg_vencida", "fin_urg_hoy", "fin_urg_manana",
                  "fin_urg_despues", "fin_vencido_etiqueta",
                  "fin_pedida_tras_cierre"):
        assert clave in js, clave
    assert "f.urgencia" in js and "f.pedida_tras_cierre" in js
    assert "f.fecha_servicio" in js
    assert "pais.total_vencido" in js
    idioma = _js("idioma.js")
    for clave in ("fin_urg_vencida", "fin_urg_vencida_pie", "fin_urg_hoy",
                  "fin_urg_manana", "fin_urg_despues", "fin_vencido_etiqueta",
                  "fin_pedida_tras_cierre", "via_cerrado", "via_cerrado_mes",
                  "via_cancelado"):
        assert idioma.count(f"    {clave}:") == 3, clave


# ================================= decision 9: la gasolina por unidad

def test_conductor_y_agente_en_la_misma_unidad_una_sola_gasolina(
        cliente, sesion, datos):
    """Juan conduce y Luis va de agente en la misma Suburban: a los dos
    se les proponia el tanque completo y "Usar el propuesto" lo
    depositaba dos veces. Ahora la gasolina es de Juan y Luis la ve en
    cero, editable; el total del equipo lleva el tanque una vez."""
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos, 40)
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"], rol="conductor_seguridad")
    asignar(cliente, h, j["id"], persona_id=luis, rol="agente_seguridad")

    tanque = _combustible(150, "5.5")
    de_juan, _ = _gasolina(_propuesta(cliente, h, j["id"], juan))
    de_luis, fila = _gasolina(_propuesta(cliente, h, j["id"], luis))
    assert de_juan == tanque
    assert de_luis == 0
    assert fila["editable"] is True and "conduce" in fila["descripcion"]

    panel = cliente.get(f"/viaticos/equipos/{servicio['equipos'][0]['id']}",
                        headers=h).json()
    por_persona = {p["persona_id"]: Decimal(str(p["propuesto"]))
                   for p in panel["personal"]}
    # Los demas conceptos son los mismos para los dos: la diferencia es
    # exactamente un tanque, y el total lo lleva una sola vez.
    assert por_persona[juan] - por_persona[luis] == tanque
    assert Decimal(str(panel["total_propuesto"])) == por_persona[juan] + por_persona[luis]


def test_con_dos_unidades_cada_conductor_recibe_la_de_la_suya(
        cliente, sesion, datos):
    """Juan en la Suburban (5.5 km/l) y Luis en la minivan (10 km/l): el
    segundo recibia el rendimiento de la primera. Ahora cada uno recibe
    la gasolina de su unidad, con su propio rendimiento."""
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos, 41)
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    suburban = datos["suburban"]["id"]
    minivan = next(v["id"] for v in datos["vehiculos"]
                   if v["categoria_id"] == datos["categorias"]["minivan"]["id"])
    asignar(cliente, h, j["id"], persona_id=juan, vehiculo_id=suburban,
            rol="conductor_seguridad")
    asignar(cliente, h, j["id"], persona_id=luis, vehiculo_id=minivan,
            rol="conductor_seguridad")
    _abordo(cliente, h, j["id"], juan, suburban)
    _abordo(cliente, h, j["id"], luis, minivan)

    de_juan, fila_juan = _gasolina(_propuesta(cliente, h, j["id"], juan))
    de_luis, fila_luis = _gasolina(_propuesta(cliente, h, j["id"], luis))
    assert de_juan == _combustible(150, "5.5")
    assert de_luis == _combustible(150, "10.0")
    assert de_juan != de_luis
    # Cada renglon dice de que unidad es la cuenta.
    assert "ABC-1234" in fila_juan["descripcion"]
    assert "DEF-1111" in fila_luis["descripcion"]


def test_el_agente_solo_con_la_unidad_recibe_la_gasolina(cliente, sesion, datos):
    """Sin conductor asignado, el agente puede quedar a cargo de la
    unidad: la gasolina se le propone a el (decision de Salvador). Y es
    la de SU unidad: Luis solo en la minivan mientras Juan conduce la
    Suburban recibe la cuenta de la minivan, no la de la primera del dia."""
    h = sesion("consultor")
    luis = datos["personal"]["Luis Mendoza"]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    suburban = datos["suburban"]["id"]

    # Solo el, con la unidad.
    servicio = _servicio(cliente, h, datos, 42)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=luis, vehiculo_id=suburban,
            rol="agente_seguridad")
    de_luis, fila = _gasolina(_propuesta(cliente, h, j["id"], luis))
    assert de_luis == _combustible(150, "5.5")
    assert fila["origen"] == "estimado"

    # Solo el en la minivan, con Juan al volante de la Suburban.
    servicio = _servicio(cliente, h, datos, 43)
    j = servicio["equipos"][0]["jornadas"][0]
    minivan = next(v["id"] for v in datos["vehiculos"]
                   if v["categoria_id"] == datos["categorias"]["minivan"]["id"])
    asignar(cliente, h, j["id"], persona_id=juan, vehiculo_id=suburban,
            rol="conductor_seguridad")
    asignar(cliente, h, j["id"], persona_id=luis, vehiculo_id=minivan,
            rol="agente_seguridad")
    _abordo(cliente, h, j["id"], juan, suburban)
    _abordo(cliente, h, j["id"], luis, minivan)
    de_juan, _ = _gasolina(_propuesta(cliente, h, j["id"], juan))
    de_luis, _ = _gasolina(_propuesta(cliente, h, j["id"], luis))
    assert de_juan == _combustible(150, "5.5")
    assert de_luis == _combustible(150, "10.0")


def test_en_el_implantado_la_gasolina_del_acuerdo_es_de_quien_conduce(
        cliente, sesion, datos):
    """El acuerdo dice 300 de gasolina por dia. Juan conduce la unidad y
    Luis va de agente: la gasolina se le propone a Juan; Luis la ve en
    cero y lo demas del acuerdo igual para los dos."""
    from tests.test_mes_siguiente import _alta
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = manana(0)
    r = cliente.put(f"/implantados/{servicio_id}/tabulador", headers=h, json={
        "renglones": [{"concepto": "alimentos", "monto": "200", "activo": True},
                      {"concepto": "combustible", "monto": "300", "activo": True}]})
    assert r.status_code == 200, r.text

    panel = cliente.get(f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}",
                        headers=h).json()
    juan = next(p for p in panel["personal"]
                if p["persona_id"] == datos["personal"]["Juan Ramirez"]["id"])
    luis = next(p for p in panel["personal"]
                if p["persona_id"] == datos["personal"]["Luis Mendoza"]["id"])
    assert juan["dias"] == luis["dias"]
    assert Decimal(str(juan["propuesto"])) == Decimal(500) * juan["dias"]
    assert Decimal(str(luis["propuesto"])) == Decimal(200) * luis["dias"]


# =================================== decision 10: dinero nuevo tras el cierre

def _en_facturacion(cliente, sesion, datos, offset):
    """Un eventual trabajado y con el visto bueno dado: en facturacion.
    Devuelve (servicio, cierre_id, equipo_id, jornada_id)."""
    servicio, cierre_id = servicio_para_cierre(cliente, sesion, datos,
                                               offset=offset, dias=1)
    assert _estatus(cliente, sesion, servicio["id"]) == "en_facturacion"
    equipo = servicio["equipos"][0]
    return servicio, cierre_id, equipo["id"], equipo["jornadas"][0]["id"]


def _frenado(respuesta, motivo):
    assert respuesta.status_code == 409, respuesta.text
    d = respuesta.json()["detail"]
    assert "no entra dinero nuevo" in d["mensaje"], d
    assert d["motivo"] == motivo
    assert d["que_hacer"]
    return d


def test_en_facturacion_y_cerrado_no_entra_dinero_nuevo(cliente, sesion, datos):
    """Con el visto bueno dado (en facturacion) y despues de que finanzas
    aprueba (cerrado), fijar, abrir, agregar y pedir contestan 409 con el
    mensaje y que hacer; antes se depositaba sin tarjeta ni plazo."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio, cierre_id, equipo_id, jornada_id = _en_facturacion(
        cliente, sesion, datos, offset=1400)

    d = _frenado(_fijar(cliente, h, equipo_id, juan, 1500), "en_facturacion")
    assert "en facturación" in d["mensaje"]
    assert "regrese el servicio" in d["que_hacer"]
    _frenado(_agregar(cliente, h, equipo_id, juan, 300), "en_facturacion")
    _frenado(_solicitar(cliente, h, equipo_id), "en_facturacion")
    _frenado(cliente.post("/viaticos/asignar", headers=h, json={
        "jornada_id": jornada_id, "persona_id": juan,
        "conceptos": [{"concepto": "alimentos", "monto": "350",
                       "origen": "tabulador"}]}), "en_facturacion")
    panel = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
    assert panel["dinero_cerrado"] == "en_facturacion"

    # Finanzas aprueba: cerrado, y sigue sin entrar.
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert _estatus(cliente, sesion, servicio["id"]) == "cerrado"
    d = _frenado(_fijar(cliente, h, equipo_id, juan, 1500), "cerrado")
    assert "cerrado" in d["mensaje"]
    _frenado(_solicitar(cliente, h, equipo_id), "cerrado")
    assert cliente.get(f"/viaticos/equipos/{equipo_id}",
                       headers=h).json()["dinero_cerrado"] == "cerrado"


def test_cuando_finanzas_regresa_el_servicio_vuelve_a_entrar_dinero(
        cliente, sesion, datos):
    """Si de verdad hace falta mas dinero, finanzas regresa el servicio,
    se mueve el dinero y se vuelve a cerrar: con el regreso, fijar y
    pedir vuelven a contestar 200."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio, cierre_id, equipo_id, _ = _en_facturacion(
        cliente, sesion, datos, offset=1410)
    _frenado(_fijar(cliente, h, equipo_id, juan, 800), "en_facturacion")

    r = cliente.post(f"/cierre/{cierre_id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "Falto el dinero de un dia del equipo"})
    assert r.status_code == 200, r.text
    assert _estatus(cliente, sesion, servicio["id"]) == "sin_visto_bueno"

    assert _fijar(cliente, h, equipo_id, juan, 800).status_code == 200
    assert _solicitar(cliente, h, equipo_id).status_code == 200
    panel = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
    assert panel["dinero_cerrado"] is None
    assert len(_bandeja(cliente, sesion, {servicio["folio"]})) == 1


def test_un_servicio_cancelado_no_recibe_dinero_nuevo_pero_paga_lo_pedido(
        cliente, sesion, datos):
    """Lo pedido antes de la cancelacion --ya en manos de finanzas-- se
    deposita, le llega al agente y lo comprueba como siempre; pero fijar
    o agregar dinero nuevo al servicio cancelado contesta 409."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = _servicio(cliente, h, datos, 45)
    equipo_id = servicio["equipos"][0]["id"]
    asignar(cliente, h, servicio["equipos"][0]["jornadas"][0]["id"],
            persona_id=juan, vehiculo_id=datos["suburban"]["id"])
    assert _fijar(cliente, h, equipo_id, juan, 500).status_code == 200
    assert _solicitar(cliente, h, equipo_id).status_code == 200
    vid = _viaticos_de(equipo_id)[0]
    _enviada([vid])

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "El cliente cancelo"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["depositos_pedidos_a_finanzas"] == 1

    d = _frenado(_fijar(cliente, h, equipo_id, juan, 900), "cancelado")
    assert "cancelado" in d["mensaje"]
    _frenado(_agregar(cliente, h, equipo_id, juan, 300), "cancelado")
    assert cliente.get(f"/viaticos/equipos/{equipo_id}",
                       headers=h).json()["dinero_cerrado"] == "cancelado"

    # Lo pedido antes sigue su camino: la bandeja lo trae con boton y
    # finanzas lo deposita.
    fila = _bandeja(cliente, sesion, {servicio["folio"]})[0]
    assert fila["pedida_tras_cierre"] is False
    dep = depositar(cliente, sesion("finanzas"), equipo_id, juan, "SPEI-105-1")
    assert dep.status_code == 200, dep.text
    assert dep.json()["sobre_cancelada"] is False

    # Y el agente lo ve en su app y lo comprueba.
    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    tarjeta = next(x for x in mios["servicios"] + mios["cerrados"]
                   if x["folio"] == servicio["folio"])
    assert Decimal(str(tarjeta["entregado"])) == Decimal("500")
    r = cliente.post(f"/campo/viaticos/{vid}/comprobante", headers=sesion("juan"),
                     json={"concepto": "alimentos", "tipo": "nota", "monto": "120"})
    assert r.status_code == 200, r.text


def _solicitud_directa(jornada_id, persona_id, monto, creada_en, moneda="MXN"):
    """Una solicitud escrita a mano en la base, con la hora que se diga.
    Es el decorado de "lo que no deberia existir": las puertas ya no
    dejan pedir con el servicio cerrado, y el revisor no da el visto
    bueno con dinero pendiente."""
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        viatico = (db.query(m.AsignacionViatico)
                   .filter_by(jornada_id=jornada_id, persona_id=persona_id).first())
        if viatico is None:
            viatico = m.AsignacionViatico(
                jornada_id=jornada_id, persona_id=persona_id,
                escenario=m.EscenarioViatico.FULL_DAY_LOCAL,
                moneda=m.Moneda(moneda), monto_total=Decimal(monto),
                estatus=m.EstatusViatico.SOLICITADO)
            db.add(viatico)
            db.flush()
            db.add(m.ConceptoAsignado(
                asignacion_id=viatico.id, concepto=m.ConceptoViatico.OTROS,
                monto=Decimal(monto), origen=m.OrigenMonto.MANUAL,
                descripcion="Deposito adicional", es_adicional=True))
        else:
            viatico.monto_total = Decimal(str(viatico.monto_total)) + Decimal(monto)
        solicitud = m.SolicitudTransferencia(
            asignacion_id=viatico.id, monto=Decimal(monto),
            moneda=m.Moneda(moneda), creada_en=creada_en)
        db.add(solicitud)
        db.commit()
        return solicitud.id


def _visto_bueno_en(cierre_id):
    """La hora del visto bueno (hora de pared de Mexico), como instante."""
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        enviado = db.get(m.Cierre, cierre_id).enviado_en
    return enviado.replace(tzinfo=MX).astimezone(timezone.utc)


def test_lo_pedido_antes_del_cierre_se_deposita_y_lo_de_despues_no(
        cliente, sesion, datos):
    """En facturacion: una solicitud de antes del visto bueno se deposita
    como siempre. Una nacida despues --no deberia existir-- sale en la
    bandeja sin boton y finanzas no la puede registrar."""
    juan = datos["personal"]["Juan Ramirez"]["id"]

    # De antes del cierre: se deposita.
    servicio, cierre_id, equipo_id, jornada_id = _en_facturacion(
        cliente, sesion, datos, offset=1420)
    visto_bueno = _visto_bueno_en(cierre_id)
    _solicitud_directa(jornada_id, juan, "700", visto_bueno - timedelta(hours=1))
    fila = _bandeja(cliente, sesion, {servicio["folio"]})[0]
    assert fila["pedida_tras_cierre"] is False
    dep = depositar(cliente, sesion("finanzas"), equipo_id, juan, "SPEI-105-2")
    assert dep.status_code == 200, dep.text

    # De despues del cierre: sin boton en la bandeja y 409 al depositar.
    otro, cierre2, equipo2, jornada2 = _en_facturacion(
        cliente, sesion, datos, offset=1430)
    visto_bueno = _visto_bueno_en(cierre2)
    sid = _solicitud_directa(jornada2, juan, "700", visto_bueno + timedelta(hours=1))
    fila = _bandeja(cliente, sesion, {otro["folio"]})[0]
    assert fila["pedida_tras_cierre"] is True
    dep = depositar(cliente, sesion("finanzas"), equipo2, juan, "SPEI-105-3")
    _frenado(dep, "en_facturacion")
    # Ni por la puerta de lo que llega confirmado de Odoo.
    _frenado(cliente.post(f"/viaticos/transferencias/{sid}/confirmar",
                          headers=sesion("finanzas")), "en_facturacion")


def test_el_mes_del_implantado_con_visto_bueno_no_recibe_dinero_nuevo(
        cliente, sesion, datos):
    """El implantado no cambia de estatus: cierra por mes. Con el mes en
    facturacion no entra dinero nuevo en ese mes; cuando finanzas lo
    regresa, vuelve a entrar."""
    from app import models as m
    from app.db import SessionLocal
    from tests.test_mes_siguiente import _alta
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = manana(0)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    base = f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}"
    r = cliente.post(f"{base}/persona", json={"persona_id": juan, "monto": "3000"},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["dinero_cerrado"] is None

    # El visto bueno del mes, dado (decorado directo: el mes cierra solo
    # al terminar su ultimo dia trabajado).
    with SessionLocal() as db:
        contrato = (db.query(m.ContratoImplantado)
                    .filter_by(servicio_id=servicio_id, anio=hoy.year,
                               mes=hoy.month).first())
        ahora = datetime.now()
        cierre = m.Cierre(servicio_id=servicio_id, contrato_id=contrato.id,
                          abierto_en=ahora, comprobacion_hasta=ahora,
                          limite_consultor=ahora + timedelta(hours=24),
                          estatus=m.EstatusCierre.ENVIADO_FINANZAS,
                          enviado_en=ahora)
        db.add(cierre)
        db.commit()
        cierre_id = cierre.id

    d = _frenado(cliente.post(f"{base}/persona/agregar",
                              json={"persona_id": juan, "monto": "500"},
                              headers=h), "en_facturacion")
    assert d["mensaje"].startswith("El mes")
    _frenado(cliente.post(f"{base}/solicitar", json={}, headers=h),
             "en_facturacion")
    assert cliente.get(base, headers=h).json()["dinero_cerrado"] == "en_facturacion"

    # Finanzas lo regresa: vuelve a entrar.
    with SessionLocal() as db:
        db.get(m.Cierre, cierre_id).estatus = m.EstatusCierre.DEVUELTO_A_OPERACION
        db.commit()
    assert cliente.post(f"{base}/solicitar", json={}, headers=h).status_code == 200
    assert cliente.get(base, headers=h).json()["dinero_cerrado"] is None


def test_la_ficha_esconde_los_botones_con_el_servicio_cerrado():
    """La ficha del servicio y el panel del mes leen `dinero_cerrado`:
    los campos se quedan quietos y en lugar del boton de pedir se dice
    por que (via_cerrado / via_cerrado_mes / via_cancelado)."""
    servicio = _js("servicio.js")
    assert "datos.dinero_cerrado" in servicio
    assert 'renglonViatico(p, equipo, moneda, repintar, cerrado)' in servicio
    assert 'decideElDinero() && !cerrado' in servicio
    assert 't(cerrado === "cancelado" ? "via_cancelado" : "via_cerrado")' in servicio
    implantado = _js("implantado.js")
    assert "datos.dinero_cerrado" in implantado
    assert 'decideElDinero() && !cerrado' in implantado
    assert '"via_cerrado_mes"' in implantado

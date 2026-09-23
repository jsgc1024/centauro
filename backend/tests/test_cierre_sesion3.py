# -*- coding: utf-8 -*-
"""El cierre, sesion 3: las reglas que traen las pantallas.

Decisiones de Salvador, 23 de septiembre (seccion 59 de la bitacora):

1. Si finanzas regresa un servicio, el consultor tiene 24 horas desde el
   regreso y lo "en plazo" de su primer visto bueno se queda.
2. Cerrar con descuento solo despues del plazo de esa persona, y solo
   sobre dinero depositado.
3. Comprobar el dinero a tiempo es haber terminado antes de su plazo;
   cada dinero cuenta en el mes en que cae su plazo; el cierre con
   descuento no es a tiempo.
4. Si finanzas regresa un servicio ya facturado, esa factura se anula y
   con el nuevo visto bueno sale otra.

Y los dos tratos de gastos con el cliente: a precio alzado se factura el
monto fijo de la propuesta, se gaste mas o menos; con gastos netos se
factura lo comprobado y el cliente recibe el desglose.

El dinero de una persona en un servicio es un solo bolson: se revisa y
se cierra por persona, no dia por dia.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from ayudas import (asignar, crear_servicio, depositar_de_verdad,
                    ejecutar_jornada, jornada, manana)

# La foto del ticket: un JPEG de un pixel, como data URI --asi la manda
# la app--.
FOTO = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEB"
        "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
        "AQEBAQEBAQH/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQ"
        "AQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")

PUNTO = {"origen_direccion": "Aeropuerto Benito Juárez, T2",
         "origen_lat": "19.4270", "origen_lon": "-99.1677",
         "geocerca_metros": 250}
H24 = timedelta(hours=24)


# ------------------------------------------------------------ el decorado

def _cotizar(cliente, h, servicio, datos, gastos=None, alzado=True):
    """La propuesta del servicio: Juan y la Suburban cada dia y, si se
    dice, un monto de gastos a precio alzado --o estimado, en netos--."""
    dias = servicio["equipos"][0]["jornadas"]
    lineas = []
    for j in dias:
        lineas.append({"fecha": j["fecha"], "tipo": "recurso",
                       "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]})
        lineas.append({"fecha": j["fecha"], "tipo": "vehiculo",
                       "categoria_id": datos["categorias"]["suv_blindada"]["id"]})
    if gastos is not None:
        lineas.append({"fecha": dias[0]["fecha"], "tipo": "viaticos",
                       "precio_unitario": str(gastos),
                       "descripcion": "Gastos del servicio"})
    r = cliente.post("/cotizaciones", headers=h, json={
        "servicio_id": servicio["id"], "lineas": lineas,
        "viaticos_incluidos": alzado})
    assert r.status_code == 201, r.text
    r = cliente.post(f"/cotizaciones/{r.json()['cotizacion_id']}/autorizar",
                     json={"autorizada_por": "Compras del cliente"}, headers=h)
    assert r.status_code == 200, r.text


def _armar(cliente, sesion, datos, offset, dias=2, gastos=None, alzado=True,
           deposito="1200"):
    """Un eventual de `dias` dias con Juan y la Suburban, cotizado, con
    su dinero ya depositado, y trabajado completo: T0 ya paso."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"],
                 **PUNTO) for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    _cotizar(cliente, h, servicio, datos, gastos, alzado)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"], persona_id=juan,
                vehiculo_id=datos["suburban"]["id"])
    if deposito:
        equipo = servicio["equipos"][0]["id"]
        r = cliente.post(f"/viaticos/equipos/{equipo}/persona", headers=h,
                         json={"persona_id": juan, "monto": deposito})
        assert r.status_code in (200, 201), r.text
        depositar_de_verdad(cliente, sesion, equipo, juan,
                            referencia=f"SPEI-S3-{servicio['id']}")
    for j in servicio["equipos"][0]["jornadas"]:
        ejecutar_jornada(cliente, sesion("juan"), j)
    return servicio, juan


def _viaticos(servicio_id, persona_id=None):
    """Los ids de los viaticos del servicio, dia por dia."""
    from app import cierre as motor
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [v.id for v in sorted(motor.viaticos_del_servicio(
                    db, servicio_id), key=lambda v: v.jornada.fecha)
                if persona_id is None or v.persona_id == persona_id]


def _ticket(cliente, sesion, viatico_id, monto, concepto="combustible",
            tipo="factura", descripcion=None, imagen=FOTO):
    r = cliente.post(f"/campo/viaticos/{viatico_id}/comprobante",
                     headers=sesion("juan"),
                     json={"concepto": concepto, "tipo": tipo,
                           "monto": str(monto), "descripcion": descripcion,
                           "imagen": imagen})
    assert r.status_code in (200, 201), r.text


def _comprobantes(viatico_id):
    """Los tickets del viatico, en el orden en que se subieron."""
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return sorted(c.id for c in db.get(m.AsignacionViatico,
                                           viatico_id).comprobantes)


def _validar_todo(cliente, sesion, servicio_id):
    for vid in _viaticos(servicio_id):
        for cid in _comprobantes(vid):
            r = cliente.post(f"/viaticos/{vid}/validar-comprobante/{cid}",
                             headers=sesion("consultor"))
            assert r.status_code == 200, r.text


def _cierre(servicio_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = (db.query(m.Cierre)
             .filter_by(servicio_id=servicio_id, contrato_id=None).first())
        return {"id": c.id, "estatus": c.estatus.value,
                "limite": c.limite_consultor,
                "comprobacion_hasta": c.comprobacion_hasta,
                "visto_bueno_en": c.visto_bueno_en,
                "enviado_en": c.enviado_en, "devuelto_en": c.devuelto_en,
                "dentro_de_plazo": c.dentro_de_plazo,
                "factura": c.factura_odoo, "anulada": c.factura_anulada,
                "intentos": c.factura_intentos} if c else None


def _ahora_del(servicio_id):
    from app import models as m
    from app import reloj
    from app.db import SessionLocal
    with SessionLocal() as db:
        return reloj.ahora_del_servicio(db, db.get(m.Servicio, servicio_id))


def _t0_hace(servicio_id, horas):
    """Mueve la linea de tiempo: T0 fue hace `horas`. El plazo del
    personal y el provisional del consultor se mueven con el."""
    from app import cierre as motor
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = (db.query(m.Cierre)
             .filter_by(servicio_id=servicio_id, contrato_id=None).first())
        t0 = _ahora_del(servicio_id) - timedelta(hours=horas)
        c.abierto_en = t0
        c.comprobacion_hasta = t0 + H24
        c.limite_consultor = t0 + 2 * H24
        for v in motor.viaticos_del_servicio(db, servicio_id):
            if v.limite_comprobacion:
                v.limite_comprobacion = t0 + H24
        db.commit()


def _avanzar(servicio_id):
    """La tarea de cada cinco minutos, con la hora de verdad."""
    from app import cierre as motor
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = (db.query(m.Cierre)
             .filter_by(servicio_id=servicio_id, contrato_id=None).first())
        movio = motor.avanzar(db, c)
        db.commit()
        return movio


def _al_visto_bueno(cliente, sesion, servicio, juan, horas_desde_t0=30):
    """El dinero cerrado y el reloj del consultor corriendo."""
    _validar_todo(cliente, sesion, servicio["id"])
    vid = _viaticos(servicio["id"], juan)[0]
    r = cliente.post(f"/viaticos/{vid}/bolson/cerrar",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    _t0_hace(servicio["id"], horas_desde_t0)
    _avanzar(servicio["id"])
    assert _cierre(servicio["id"])["estatus"] == "sin_visto_bueno"


def _visto_bueno(cliente, sesion, servicio_id):
    c = _cierre(servicio_id)
    r = cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def odoo(monkeypatch):
    """Un Odoo de mentiras que guarda lo que le llega y contesta folio."""
    from app import facturacion

    recibidas = []

    class Respuesta:
        status_code = 200
        content = b"{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {"factura": f"F-{len(recibidas):04d}"}

    def falso(url, json=None, headers=None, timeout=None):
        recibidas.append(json)
        return Respuesta()

    monkeypatch.setattr(facturacion.settings, "odoo_url",
                        "https://odoo.example/facturas")
    monkeypatch.setattr(facturacion.httpx, "post", falso)
    return recibidas


# ------------------------------------------------------------ los gastos

def test_a_precio_alzado_se_factura_el_monto_fijo_de_la_propuesta(
        cliente, sesion, datos, odoo):
    """El hueco de la seccion 57: el monto fijo de gastos iba en la
    cotizacion y no llegaba a la factura. Se factura aunque se haya
    gastado menos --lo que sobra es margen-- y el servicio se compara
    contra el servicio, sin los gastos revueltos."""
    servicio, juan = _armar(cliente, sesion, datos, 1600, gastos=5000)
    vid = _viaticos(servicio["id"], juan)[0]
    _ticket(cliente, sesion, vid, 1200)

    comparativo = cliente.get(
        f"/cierre/servicio/{servicio['id']}/comparativo",
        headers=sesion("consultor")).json()
    gastos = comparativo["gastos"]
    assert gastos["modo"] == "precio_alzado"
    assert Decimal(str(gastos["cotizado"])) == 5000
    assert Decimal(str(gastos["comprobado"])) == 1200
    assert Decimal(str(gastos["a_facturar"])) == 5000
    servicio_ = Decimal(str(comparativo["a_facturar"]["servicio"]))
    assert (Decimal(str(comparativo["a_facturar"]["total"]))
            == servicio_ + 5000)
    # La diferencia del servicio no se come los gastos.
    assert (Decimal(str(comparativo["cotizacion"]["servicio"]))
            == Decimal(str(comparativo["cotizacion"]["total"])) - 5000)
    assert Decimal(str(comparativo["diferencia"])) == 0

    _al_visto_bueno(cliente, sesion, servicio, juan)
    _visto_bueno(cliente, sesion, servicio["id"])
    renglones = {c["descripcion"]: Decimal(c["importe"])
                 for c in odoo[-1]["conceptos"]}
    assert renglones["Gastos a precio alzado"] == 5000
    assert Decimal(odoo[-1]["total"]) == servicio_ + 5000


def test_con_gastos_netos_se_factura_lo_comprobado_no_lo_estimado(
        cliente, sesion, datos, odoo):
    """El monto de la propuesta, en netos, es un estimado: se factura lo
    comprobado valido, sin lo rechazado."""
    servicio, juan = _armar(cliente, sesion, datos, 1610, gastos=5000,
                            alzado=False)
    uno, dos = _viaticos(servicio["id"], juan)
    _ticket(cliente, sesion, uno, 600)
    _ticket(cliente, sesion, dos, 350, concepto="casetas", tipo="nota")
    _ticket(cliente, sesion, dos, 180, concepto="alimentos", tipo="nota")
    malo = max(_comprobantes(dos))
    r = cliente.post(f"/viaticos/{dos}/rechazar-comprobante/{malo}",
                     json={"motivo": "No corresponde al servicio"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text

    comparativo = cliente.get(
        f"/cierre/servicio/{servicio['id']}/comparativo",
        headers=sesion("consultor")).json()
    assert comparativo["gastos"]["modo"] == "netos"
    assert Decimal(str(comparativo["gastos"]["a_facturar"])) == 950

    # El desglose para el cliente: lo valido, sin lo rechazado, con su
    # total, en el idioma de quien lo pide.
    hoja = cliente.get(
        f"/cierre/servicio/{servicio['id']}/desglose-gastos",
        headers=sesion("consultor"))
    assert hoja.status_code == 200, hoja.text
    texto = hoja.text
    assert "Desglose de gastos" in texto
    assert "$600.00" in texto and "$350.00" in texto
    assert "$180.00" not in texto
    assert "$950.00 MXN" in texto
    assert "Copias de los comprobantes" in texto
    en_ingles = cliente.get(
        f"/cierre/servicio/{servicio['id']}/desglose-gastos?idioma=en",
        headers=sesion("consultor")).text
    assert "Expense breakdown" in en_ingles and "Tolls" in en_ingles


def test_la_comision_se_queda_con_su_regla_a_precio_alzado(cliente, sesion,
                                                          datos, odoo):
    """Sobre lo facturado menos los viaticos comprobados (seccion 57): a
    precio alzado, lo que se ahorre en gastos le suma al consultor."""
    servicio, juan = _armar(cliente, sesion, datos, 1620, gastos=1500,
                            deposito="1200")
    vid = _viaticos(servicio["id"], juan)[0]
    _ticket(cliente, sesion, vid, 1200)
    _al_visto_bueno(cliente, sesion, servicio, juan)
    envio = _visto_bueno(cliente, sesion, servicio["id"])
    assert envio["dentro_de_plazo"] is True

    estado = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                         headers=sesion("consultor")).json()
    total = Decimal(estado["total"])
    comision = estado["comision"]
    assert comision["estatus"] == "por_generar"
    assert Decimal(str(comision["base"])) == total - 1200

    r = cliente.post(f"/cierre/{estado['cierre_id']}/aprobar",
                     headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    generada = r.json()["comision_consultor"]
    assert Decimal(str(generada["base"])) == total - 1200

    # Es suya: la ve ella, y la ve finanzas. Otro consultor puede abrir
    # el servicio, pero no su comision: la misma regla que el corte.
    ruta = f"/cierre/servicio/{servicio['id']}/estado"
    assert cliente.get(ruta, headers=sesion("consultor")).json()["comision"]
    assert cliente.get(ruta, headers=sesion("finanzas")).json()["comision"]
    assert cliente.get(ruta, headers=sesion("consultor2")).json()[
        "comision"] is None
    ajena = cliente.get("/cierre/facturacion",
                        headers=sesion("consultor2")).json()["cerrados"]
    assert ajena and all(f["comision"] is None for f in ajena)
    propia = cliente.get("/cierre/facturacion",
                         headers=sesion("consultor")).json()["cerrados"]
    assert all(f["comision"] for f in propia)


# ------------------------------------------------------------ el bolson

def test_el_dinero_de_una_persona_se_cierra_junto(cliente, sesion, datos):
    """Un ticket cargado el lunes cubre lo que se le deposito para el
    martes. Dia por dia nunca cuadraba; por persona, si."""
    servicio, juan = _armar(cliente, sesion, datos, 1630)
    uno, dos = _viaticos(servicio["id"], juan)
    _ticket(cliente, sesion, uno, 1200)          # todo, en el primer dia

    revision = cliente.get(f"/cierre/servicio/{servicio['id']}/viaticos",
                           headers=sesion("consultor")).json()
    (juan_,) = revision["personas"]
    assert Decimal(str(juan_["depositado"])) == 1200
    assert Decimal(str(juan_["falta"])) == 0
    assert juan_["sin_revisar"] == 1
    assert juan_["puede_cerrar"] is False
    assert "sin revisar" in juan_["frena_cierre"]["mensaje"]
    # La pantalla lo dice en su idioma: con la clave, no con el texto.
    assert juan_["frena_cierre"]["codigo"] == "sin_revisar"
    assert juan_["comprobantes"][0]["tiene_imagen"] is True

    r = cliente.post(f"/viaticos/{dos}/bolson/cerrar",
                     headers=sesion("consultor"))
    assert r.status_code == 409, r.text

    _validar_todo(cliente, sesion, servicio["id"])
    r = cliente.post(f"/viaticos/{dos}/bolson/cerrar",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text

    revision = cliente.get(f"/cierre/servicio/{servicio['id']}/viaticos",
                           headers=sesion("consultor")).json()
    assert revision["personas"][0]["estatus"] == "cerrado"
    # Y el comparativo ya no ve un dia "sin comprobar" y otro "de mas".
    comparativo = cliente.get(
        f"/cierre/servicio/{servicio['id']}/comparativo",
        headers=sesion("consultor")).json()
    assert not [d for d in comparativo["desviaciones"]
                if d["tipo"].startswith("viatico")]


def test_si_falta_o_sobra_dice_que_hacer(cliente, sesion, datos):
    servicio, juan = _armar(cliente, sesion, datos, 1640)
    uno, _ = _viaticos(servicio["id"], juan)
    _ticket(cliente, sesion, uno, 950)
    _validar_todo(cliente, sesion, servicio["id"])
    r = cliente.post(f"/viaticos/{uno}/bolson/cerrar",
                     headers=sesion("consultor"))
    assert r.status_code == 409
    assert "faltan" in r.json()["detail"]["mensaje"]
    assert r.json()["detail"]["codigo"] == "falta"

    _ticket(cliente, sesion, uno, 400, concepto="casetas")
    _validar_todo(cliente, sesion, servicio["id"])
    r = cliente.post(f"/viaticos/{uno}/bolson/cerrar",
                     headers=sesion("consultor"))
    assert r.status_code == 409
    assert "de mas" in r.json()["detail"]["mensaje"]
    assert r.json()["detail"]["codigo"] == "de_mas"


def test_cerrar_con_descuento_espera_a_que_venza_su_plazo(cliente, sesion,
                                                         datos):
    """Decision 2: antes de su plazo todavia puede comprobar."""
    servicio, juan = _armar(cliente, sesion, datos, 1650)
    uno, dos = _viaticos(servicio["id"], juan)
    _ticket(cliente, sesion, uno, 950)
    _validar_todo(cliente, sesion, servicio["id"])
    motivo = {"motivo": "No entrego el ticket de la comida"}

    # T0 fue hace una hora: su plazo corre.
    _t0_hace(servicio["id"], 1)
    r = cliente.post(f"/viaticos/{uno}/bolson/cerrar-con-descuento",
                     json=motivo, headers=sesion("consultor"))
    assert r.status_code == 409
    assert "en plazo" in r.json()["detail"]["mensaje"]
    revision = cliente.get(f"/cierre/servicio/{servicio['id']}/viaticos",
                           headers=sesion("consultor")).json()
    assert revision["personas"][0]["puede_descontar"] is False
    assert revision["personas"][0]["vencido"] is False

    # Y el de un dia suelto, igual.
    r = cliente.post(f"/viaticos/{dos}/cerrar-con-descuento",
                     json=motivo, headers=sesion("consultor"))
    assert r.status_code == 409

    # Vencido: se puede, sobre lo que falta de todo su dinero.
    _t0_hace(servicio["id"], 25)
    revision = cliente.get(f"/cierre/servicio/{servicio['id']}/viaticos",
                           headers=sesion("consultor")).json()
    assert revision["personas"][0]["puede_descontar"] is True
    r = cliente.post(f"/viaticos/{dos}/bolson/cerrar-con-descuento",
                     json=motivo, headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["descontado_al_personal"])) == 250

    # Un solo ajuste de nomina, por lo que falto.
    pendientes = cliente.get("/nomina/ajustes/pendientes",
                             params={"pais_id": datos["mx"]["id"]},
                             headers=sesion("finanzas")).json()
    suyos = [p for p in pendientes if p["sentido"] == "descuento"]
    assert len(suyos) == 1
    assert Decimal(str(suyos[0]["monto"])) == -250

    revision = cliente.get(f"/cierre/servicio/{servicio['id']}/viaticos",
                           headers=sesion("consultor")).json()
    assert revision["personas"][0]["estatus"] == "con_descuento"
    assert Decimal(str(revision["personas"][0]["falta"])) == 0


def test_lo_que_no_se_deposito_no_se_descuenta(cliente, sesion, datos):
    """Decision 2: solo sobre dinero depositado."""
    servicio, juan = _armar(cliente, sesion, datos, 1660, deposito=None)
    h = sesion("consultor")
    j = servicio["equipos"][0]["jornadas"][0]
    r = cliente.post("/viaticos/asignar", headers=h, json={
        "jornada_id": j["id"], "persona_id": juan,
        "conceptos": [{"concepto": "alimentos", "monto": "900",
                       "origen": "tabulador"}]})
    assert r.status_code in (200, 201), r.text
    vid = r.json()["id"]
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        db.get(m.AsignacionViatico, vid).limite_comprobacion = (
            datetime.now() - timedelta(hours=2))
        db.commit()

    motivo = {"motivo": "No comprobo nada del servicio"}
    r = cliente.post(f"/viaticos/{vid}/bolson/cerrar-con-descuento",
                     json=motivo, headers=h)
    assert r.status_code == 409
    assert "no se depositan" in r.json()["detail"]["mensaje"]
    r = cliente.post(f"/viaticos/{vid}/cerrar-con-descuento", json=motivo,
                     headers=h)
    assert r.status_code == 409
    assert "no se deposita" in r.json()["detail"]["mensaje"]


def test_la_foto_del_ticket_la_ven_quien_revisa_y_su_dueno(cliente, sesion,
                                                          datos):
    servicio, juan = _armar(cliente, sesion, datos, 1670)
    uno, _ = _viaticos(servicio["id"], juan)
    _ticket(cliente, sesion, uno, 300)
    cid = _comprobantes(uno)[0]
    ruta = f"/viaticos/{uno}/comprobantes/{cid}/imagen"

    r = cliente.get(ruta, headers=sesion("consultor"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert cliente.get(ruta, headers=sesion("juan")).status_code == 200
    assert cliente.get(ruta, headers=sesion("luis")).status_code == 403


def test_rechazar_pide_por_que(cliente, sesion, datos):
    servicio, juan = _armar(cliente, sesion, datos, 1680)
    uno, _ = _viaticos(servicio["id"], juan)
    _ticket(cliente, sesion, uno, 300)
    cid = _comprobantes(uno)[0]
    r = cliente.post(f"/viaticos/{uno}/rechazar-comprobante/{cid}",
                     json={"motivo": ""}, headers=sesion("consultor"))
    assert r.status_code == 400
    r = cliente.post(f"/viaticos/{uno}/rechazar-comprobante/{cid}",
                     json={"motivo": "La foto no se lee"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    # Rechazado ya no se valida: que lo vuelva a subir.
    r = cliente.post(f"/viaticos/{uno}/validar-comprobante/{cid}",
                     headers=sesion("consultor"))
    assert r.status_code == 409


# ------------------------------------------------------------ el regreso

def test_solo_se_regresa_lo_que_esta_en_facturacion_y_con_motivo(
        cliente, sesion, datos):
    servicio, juan = _armar(cliente, sesion, datos, 1690)
    _ticket(cliente, sesion, _viaticos(servicio["id"], juan)[0], 1200)
    _al_visto_bueno(cliente, sesion, servicio, juan)
    c = _cierre(servicio["id"])
    r = cliente.post(f"/cierre/{c['id']}/devolver",
                     json={"motivo": "La hora extra no la autorizo nadie"},
                     headers=sesion("finanzas"))
    assert r.status_code == 409, "sin visto bueno no es de finanzas"

    _visto_bueno(cliente, sesion, servicio["id"])
    r = cliente.post(f"/cierre/{c['id']}/devolver", json={"motivo": "mal"},
                     headers=sesion("finanzas"))
    assert r.status_code == 400


def test_al_regresarlo_tiene_24_horas_y_su_plazo_se_queda(cliente, sesion,
                                                         datos):
    """Decision 1: 24 horas desde el regreso, y el "en plazo" del primer
    visto bueno no se pierde por la vuelta."""
    servicio, juan = _armar(cliente, sesion, datos, 1700)
    _ticket(cliente, sesion, _viaticos(servicio["id"], juan)[0], 1200)
    _al_visto_bueno(cliente, sesion, servicio, juan)
    _visto_bueno(cliente, sesion, servicio["id"])
    antes = _cierre(servicio["id"])
    assert antes["dentro_de_plazo"] is True

    r = cliente.post(f"/cierre/{antes['id']}/devolver",
                     json={"motivo": "La hora extra no trae el visto bueno "
                                     "del cliente"},
                     headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    estado = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                         headers=sesion("consultor")).json()
    assert estado["fase"] == "devuelto"
    assert estado["reloj"]["quien"] == "regreso"
    assert 23 * 60 <= estado["reloj"]["minutos"] <= 24 * 60
    assert "visto bueno del cliente" in estado["devuelto_motivo"]
    assert (cliente.get(f"/servicios/{servicio['id']}",
                        headers=sesion("consultor")).json()["estatus"]
            == "sin_visto_bueno")

    # Su limite de siempre ya paso de sobra: el revisor no lo cuenta,
    # porque lo que corre es el reloj del regreso.
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = db.get(m.Cierre, antes["id"])
        c.limite_consultor = datetime.now() - timedelta(days=3)
        db.commit()
    ruta = f"/cierre/servicio/{servicio['id']}/revision"
    asuntos = [o["asunto"] for o in cliente.get(
        ruta, headers=sesion("consultor")).json()["observaciones"]]
    assert "Plazo vencido" not in asuntos

    # Y si tambien se pasa de las 24 horas del regreso, se dice asi,
    # sin amenazar una comision que ya quedo juzgada.
    with SessionLocal() as db:
        c = db.get(m.Cierre, antes["id"])
        c.devuelto_en = c.devuelto_en - timedelta(hours=30)
        db.commit()
    (regreso,) = [o for o in cliente.get(
        ruta, headers=sesion("consultor")).json()["observaciones"]
        if o["asunto"].startswith(("Regreso", "Plazo"))]
    assert regreso["asunto"] == "Regreso vencido"
    assert "comision" not in regreso["accion"]
    _visto_bueno(cliente, sesion, servicio["id"])
    despues = _cierre(servicio["id"])
    assert despues["dentro_de_plazo"] is True
    assert despues["visto_bueno_en"] == antes["visto_bueno_en"]
    assert despues["enviado_en"] > antes["enviado_en"]


def test_fuera_de_plazo_se_queda_fuera_aunque_lo_regresen(cliente, sesion,
                                                         datos):
    servicio, juan = _armar(cliente, sesion, datos, 1710)
    _ticket(cliente, sesion, _viaticos(servicio["id"], juan)[0], 1200)
    _al_visto_bueno(cliente, sesion, servicio, juan, horas_desde_t0=60)
    _visto_bueno(cliente, sesion, servicio["id"])
    c = _cierre(servicio["id"])
    assert c["dentro_de_plazo"] is False
    r = cliente.post(f"/cierre/{c['id']}/devolver",
                     json={"motivo": "Falta la orden de compra del cliente"},
                     headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    _visto_bueno(cliente, sesion, servicio["id"])
    assert _cierre(servicio["id"])["dentro_de_plazo"] is False


def test_la_factura_se_anula_al_regresarlo_y_sale_otra(cliente, sesion,
                                                       datos, odoo):
    """Decision 4, y nunca dos facturas vivas: la nueva dice a cual
    sustituye."""
    servicio, juan = _armar(cliente, sesion, datos, 1720)
    _ticket(cliente, sesion, _viaticos(servicio["id"], juan)[0], 1200)
    _al_visto_bueno(cliente, sesion, servicio, juan)
    _visto_bueno(cliente, sesion, servicio["id"])
    c = _cierre(servicio["id"])
    primera = c["factura"]
    assert primera and len(odoo) == 1

    r = cliente.post(f"/cierre/{c['id']}/devolver",
                     json={"motivo": "El cliente pidio otra razon social"},
                     headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["factura_anulada"] == primera
    c = _cierre(servicio["id"])
    assert c["factura"] is None and c["anulada"] == primera

    _visto_bueno(cliente, sesion, servicio["id"])
    assert len(odoo) == 2
    assert odoo[-1]["sustituye_a"] == primera
    assert _cierre(servicio["id"])["factura"] not in (None, primera)


def test_la_hora_por_parametro_no_vale_en_produccion(cliente, sesion, datos,
                                                     monkeypatch):
    """El "en plazo" decide una comision: no lo decide quien escribe una
    hora en la direccion."""
    from app import config

    servicio, juan = _armar(cliente, sesion, datos, 1730)
    _ticket(cliente, sesion, _viaticos(servicio["id"], juan)[0], 1200)
    _al_visto_bueno(cliente, sesion, servicio, juan, horas_desde_t0=60)
    c = _cierre(servicio["id"])
    antes_del_limite = (c["limite"] - timedelta(hours=1)).isoformat()

    monkeypatch.setattr(config.settings, "app_env", "produccion")
    r = cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                     params={"ahora": antes_del_limite},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["dentro_de_plazo"] is False


# ------------------------------------------------------------ finanzas

def test_la_bandeja_de_facturacion(cliente, sesion, datos):
    servicio, juan = _armar(cliente, sesion, datos, 1740, gastos=800)
    _ticket(cliente, sesion, _viaticos(servicio["id"], juan)[0], 1200)
    _al_visto_bueno(cliente, sesion, servicio, juan)
    _visto_bueno(cliente, sesion, servicio["id"])

    bandeja = cliente.get("/cierre/facturacion",
                          headers=sesion("finanzas")).json()
    (fila,) = bandeja["por_aprobar"]
    assert fila["folio"] == servicio["folio"]
    assert fila["dentro_de_plazo"] is True
    assert fila["consultor"]
    assert fila["gastos"]["modo"] == "precio_alzado"
    assert Decimal(str(fila["gastos"]["monto"])) == 800
    assert bandeja["resumen"]["por_aprobar"]["cuantos"] == 1
    # Sin Odoo en este servidor: queda por facturar, con lo que paso.
    (sin_factura,) = bandeja["por_facturar"]
    assert sin_factura["que_paso"] == "sin_conexion"
    assert sin_factura["intentos"] >= 1

    r = cliente.post(f"/cierre/{fila['cierre_id']}/aprobar",
                     headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    bandeja = cliente.get("/cierre/facturacion",
                          headers=sesion("finanzas")).json()
    assert not bandeja["por_aprobar"]
    (cerrado,) = bandeja["cerrados"]
    assert cerrado["comision"]["generada"] is True
    assert bandeja["resumen"]["cerrados"]["cuantos"] == 1


def test_aprobar_dos_veces_no_se_puede_y_se_dice_en_palabras(cliente, sesion,
                                                            datos):
    servicio, juan = _armar(cliente, sesion, datos, 1750)
    _ticket(cliente, sesion, _viaticos(servicio["id"], juan)[0], 1200)
    _al_visto_bueno(cliente, sesion, servicio, juan)
    _visto_bueno(cliente, sesion, servicio["id"])
    c = _cierre(servicio["id"])
    assert cliente.post(f"/cierre/{c['id']}/aprobar",
                        headers=sesion("finanzas")).status_code == 200
    r = cliente.post(f"/cierre/{c['id']}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 409
    assert "_" not in r.json()["detail"]["mensaje"]


# ------------------------------------------------------------ la cartera y el panorama

def test_los_relojes_de_la_cartera(cliente, sesion, datos):
    servicio, juan = _armar(cliente, sesion, datos, 1760)
    _t0_hace(servicio["id"], 3)
    relojes = {r["servicio_id"]: r for r in cliente.get(
        "/cierre/relojes", headers=sesion("consultor")).json()}
    suyo = relojes[servicio["id"]]
    assert suyo["fase"] == "comprobacion"
    assert suyo["reloj"]["quien"] == "personal"
    assert 20 * 60 < suyo["reloj"]["minutos"] <= 21 * 60


def test_el_panorama_cuenta_lo_depositado_aunque_no_traiga_ticket(
        cliente, sesion, datos):
    """Antes solo contaba lo que ya traia un ticket, y el monto completo:
    quien no habia subido nada no aparecia."""
    servicio, juan = _armar(cliente, sesion, datos, 1770)
    _t0_hace(servicio["id"], 30)
    r = cliente.get("/panorama", headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text
    dinero = r.json()["dinero"]
    afuera = dinero["afuera_sin_comprobar"]
    assert Decimal(str(afuera["monto"])) == 1200
    assert afuera["personas"] == 1
    assert Decimal(str(afuera["vencido"])) == 1200
    assert dinero["camino"]["comprobacion"]["cuantos"] == 1


# ------------------------------------------------------------ la app

def test_la_app_dice_cuanto_le_queda(cliente, sesion, datos):
    servicio, juan = _armar(cliente, sesion, datos, 1780)
    _t0_hace(servicio["id"], 19)
    r = cliente.get("/campo/mis-viaticos", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    (tarjeta,) = [s for s in r.json()["servicios"]
                  if s["servicio_id"] == servicio["id"]]
    assert 4 * 60 < tarjeta["minutos"] <= 5 * 60
    assert tarjeta["momento"]


def test_antes_de_terminar_no_hay_plazo_en_la_app(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(1790), datos["modalidades"]["full_day"]["id"],
                 **PUNTO)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    juan = datos["personal"]["Juan Ramirez"]["id"]
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    equipo = servicio["equipos"][0]["id"]
    cliente.post(f"/viaticos/equipos/{equipo}/persona", headers=h,
                 json={"persona_id": juan, "monto": "700"})
    depositar_de_verdad(cliente, sesion, equipo, juan,
                        referencia=f"SPEI-S3-{servicio['id']}")
    (tarjeta,) = [s for s in cliente.get(
        "/campo/mis-viaticos", headers=sesion("juan")).json()["servicios"]
        if s["servicio_id"] == servicio["id"]]
    assert tarjeta["limite"] is None and tarjeta["minutos"] is None


# ------------------------------------------------------------ el bono

def _bono(persona_id, anio, mes):
    from app import bonos
    from app.db import SessionLocal
    with SessionLocal() as db:
        return bonos.medir_cierre_viaticos(db, persona_id, anio, mes)


def _mover(servicio_id, plazo, subido=None):
    """Pone el plazo del dinero y la hora de sus tickets."""
    from zoneinfo import ZoneInfo

    from app import cierre as motor
    from app.db import SessionLocal
    with SessionLocal() as db:
        for v in motor.viaticos_del_servicio(db, servicio_id):
            v.limite_comprobacion = plazo
            for c in v.comprobantes:
                if subido:
                    c.subido_en = subido.replace(
                        tzinfo=ZoneInfo("America/Mexico_City"))
        db.commit()


def test_comprobar_a_tiempo_se_mide_cuando_termino_de_comprobar(
        cliente, sesion, datos):
    """Decision 3. A tiempo, uno; tarde, otro; y el descuento no cuenta
    como a tiempo. Todo con plazo en marzo de 2031."""
    plazo = datetime(2031, 3, 17, 18, 40)
    bien, juan = _armar(cliente, sesion, datos, 1800)
    _ticket(cliente, sesion, _viaticos(bien["id"], juan)[0], 1200)
    _mover(bien["id"], plazo, subido=plazo - timedelta(hours=3))

    tarde, _ = _armar(cliente, sesion, datos, 1810)
    _ticket(cliente, sesion, _viaticos(tarde["id"], juan)[0], 1200)
    _mover(tarde["id"], plazo, subido=plazo + timedelta(hours=5))

    # Uno sin un solo ticket, con su plazo todavia por delante: sigue en
    # plazo y no se mide --una evaluacion a medio mes no lo castiga--.
    pendiente, _ = _armar(cliente, sesion, datos, 1830)
    _mover(pendiente["id"], plazo)

    r = _bono(juan, 2031, 3)
    assert r["valor"] == Decimal("50.00"), r
    assert pendiente["folio"] not in r["detalle"]
    assert f"{tarde['folio']}: termino de comprobar el lun 17 a las 23:40" \
        in r["detalle"]
    assert "5 hora(s) despues de su plazo (18:40)" in r["detalle"]
    # En febrero no cae ningun plazo: ahi no aplica.
    assert _bono(juan, 2031, 2)["aplica"] is False

    # Vencido sin comprobar, si cuenta: en enero de 2026 ya paso.
    _mover(pendiente["id"], datetime(2026, 1, 20, 10, 0))
    r = _bono(juan, 2026, 1)
    assert r["valor"] == 0, r
    assert f"{pendiente['folio']}: no termino de comprobar" in r["detalle"]


def test_el_cierre_con_descuento_no_es_a_tiempo(cliente, sesion, datos):
    servicio, juan = _armar(cliente, sesion, datos, 1820)
    uno, _ = _viaticos(servicio["id"], juan)
    _ticket(cliente, sesion, uno, 1000)
    _validar_todo(cliente, sesion, servicio["id"])
    _t0_hace(servicio["id"], 30)
    r = cliente.post(f"/viaticos/{uno}/bolson/cerrar-con-descuento",
                     json={"motivo": "Perdio el ticket de la caseta"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    hoy = _ahora_del(servicio["id"]) - timedelta(hours=6)
    medido = _bono(juan, hoy.year, hoy.month)
    assert medido["valor"] == 0
    assert "con descuento" in medido["detalle"]


# ------------------------------------------------------------ el implantado

def _implantado(cliente, sesion, datos):
    """El implantado de septiembre de 2029 de test_cierre_mes."""
    from test_cierre_mes import DIAS, _alta

    alta = _alta(cliente, sesion, datos)
    return alta, alta["contrato_id"], DIAS


def test_los_terminos_del_mes_se_corrigen_hasta_el_visto_bueno(cliente,
                                                               sesion, datos):
    """Hasta hoy los precios del mes solo se capturaban al abrirlo."""
    alta, contrato, _ = _implantado(cliente, sesion, datos)
    h = sesion("consultor")
    r = cliente.put(f"/implantados/contratos/{contrato}/terminos", headers=h,
                    json={"esquema": "por_dia", "precio_dia_personal": "1850",
                          "precio_dia_adicional": "2100",
                          "precio_mes_vehiculo": "38000",
                          "viaticos_incluidos": True, "gastos_mes": "6000"})
    assert r.status_code == 200, r.text
    assert r.json()["modo_gastos"] == "precio_alzado"
    assert Decimal(str(r.json()["gastos_mes"])) == 6000
    assert r.json()["editable"] is True

    from app import cierre_mes
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = db.get(m.ContratoImplantado, contrato)
        comparativo = cierre_mes.comparar(db, c)
        assert comparativo["gastos"]["modo"] == "precio_alzado"
        assert comparativo["gastos"]["a_facturar"] == 6000
        assert (comparativo["a_facturar"]["total"]
                == comparativo["a_facturar"]["servicio"] + 6000)
        # Con el visto bueno dado, ya no.
        db.add(m.Cierre(servicio_id=c.servicio_id, contrato_id=c.id,
                        abierto_en=datetime(2029, 9, 28, 20),
                        limite_consultor=datetime(2029, 9, 30, 20),
                        estatus=m.EstatusCierre.ENVIADO_FINANZAS))
        db.commit()
    r = cliente.put(f"/implantados/contratos/{contrato}/terminos", headers=h,
                    json={"esquema": "por_dia", "viaticos_incluidos": False})
    assert r.status_code == 409
    assert (cliente.get(f"/implantados/contratos/{contrato}/terminos",
                        headers=h).json()["editable"] is False)


def test_los_gastos_del_mes_pasan_al_mes_siguiente(cliente, sesion, datos):
    alta, contrato, _ = _implantado(cliente, sesion, datos)
    h = sesion("consultor")
    r = cliente.put(f"/implantados/contratos/{contrato}/terminos", headers=h,
                    json={"esquema": "por_dia", "precio_dia_personal": "2900",
                          "precio_mes_vehiculo": "66000",
                          "viaticos_incluidos": True, "gastos_mes": "4500"})
    assert r.status_code == 200, r.text
    from app import implantado as motor
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        servicio = db.get(m.Servicio, alta["servicio_id"])
        motor.abrir_siguiente(db, servicio, hoy=date(2029, 9, 20))
        db.commit()
        octubre = (db.query(m.ContratoImplantado)
                   .filter_by(servicio_id=servicio.id, anio=2029, mes=10)
                   .one())
        assert octubre.viaticos_incluidos is True
        assert Decimal(str(octubre.gastos_mes)) == 4500


def test_la_cartera_dice_como_va_cada_mes(cliente, sesion, datos):
    alta, contrato, _ = _implantado(cliente, sesion, datos)
    fila = next(x for x in cliente.get("/implantados",
                                       headers=sesion("consultor")).json()
                if x["servicio_id"] == alta["servicio_id"])
    (septiembre,) = fila["periodos"]
    assert septiembre["fase"] is None
    assert septiembre["sin_cierre"] in ("por_empezar", "en_curso",
                                        "dias_sin_cerrar")

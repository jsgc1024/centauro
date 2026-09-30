# -*- coding: utf-8 -*-
"""Seccion 105, grupo g3: el cierre.

Decision 1 de Salvador (29 sep): cancelar con el equipo en la calle. El
dia que esta arribado o en curso termina con la hora de la cancelacion y
cuenta como trabajado; al cancelar el consultor elige si al cliente se
le cobra la cotizacion completa o lo ejecutado; direccion de operaciones
lo autoriza desde la tarjeta del cierre; los dias cancelados de un
cancelado no exigen recotizar, y un cancelado se cotiza mientras su
cierre no tenga visto bueno (hallazgos 5, 6 y 19).

Decision 12: cuando vence un plazo del cierre. A la mitad del plazo se
le avisa al consultor; al vencer, al consultor y al director de
operaciones, por correo y al telefono; el servicio sigue esperando su
visto bueno, ya sin comision, y los vencidos salen en la bandeja del
director (hallazgo 59).
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana, marcar)


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


# ---------------------------------------------------------------- escenarios

def _servicio(cliente, sesion, datos, offset, dias=2, hora="07:00:00",
              cotizado=True):
    """Un eventual de `dias` dias con Juan y su unidad, cotizado si se
    pide. Ninguno trabajado todavia."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"],
                 hora=hora) for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    if cotizado:
        cotizar_y_autorizar(
            cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
            datos["categorias"]["suv_blindada"]["id"])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
    return servicio


def _primer_dia_trabajado(cliente, sesion, datos, offset, cotizado=True):
    """Dos dias: el primero ya se trabajo completo, el segundo esta
    planeado. El servicio sigue en curso y se puede cancelar."""
    servicio = _servicio(cliente, sesion, datos, offset, dias=2,
                         cotizado=cotizado)
    r = ejecutar_jornada(cliente, sesion("juan"),
                         servicio["equipos"][0]["jornadas"][0])
    assert r.status_code == 200, r.text
    return servicio


def _cancelar(cliente, sesion, servicio_id, cobro=None, motivo="El cliente canceló el viaje"):
    cuerpo = {"motivo": motivo}
    if cobro:
        cuerpo["cobro"] = cobro
    return cliente.post(f"/servicios/{servicio_id}/cancelar",
                        headers=sesion("consultor"), json=cuerpo)


def _cierre(servicio_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()
        if c is None:
            return None
        return {"id": c.id, "estatus": c.estatus.value,
                "motivo": c.motivo_apertura, "cobro": c.cobro,
                "autorizado_en": c.cobro_autorizado_en,
                "autorizado_por_id": c.cobro_autorizado_por_id,
                "total_cotizado": c.total_cotizado,
                "total_ejecutado": c.total_ejecutado,
                "abierto_en": c.abierto_en, "limite": c.limite_consultor,
                "visto_bueno_desde": c.visto_bueno_desde,
                "devuelto_en": c.devuelto_en,
                "aviso_mitad_en": c.aviso_mitad_en,
                "aviso_vencido_en": c.aviso_vencido_en}


def _jornada(jornada_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        j = db.get(m.Jornada, jornada_id)
        return {"estatus": j.estatus.value, "inicio_real": j.inicio_real,
                "fin_real": j.fin_real,
                "cerrada_por": j.cerrada_a_mano_por_id,
                "cerrada_en": j.cerrada_a_mano_en, "motivo": j.cierre_motivo}


def _avisos(servicio_id, destinatario=None, correo=None):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        q = db.query(m.Notificacion).filter_by(servicio_id=servicio_id)
        if destinatario:
            q = q.filter_by(destinatario=destinatario)
        if correo:
            q = q.filter_by(correo=correo)
        return [{"asunto": n.asunto, "cuerpo": n.cuerpo, "correo": n.correo,
                 "idioma": n.idioma, "datos": n.datos or "",
                 "para": n.destinatario.value, "enlace": n.enlace_seguimiento}
                for n in q.order_by(m.Notificacion.id).all()]


def _bitacora(servicio_id, accion):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [(r.detalle, r.jornada_id) for r in db.query(m.RegistroAccion)
                .filter_by(servicio_id=servicio_id, accion=accion)
                .order_by(m.RegistroAccion.id).all()]


def _ahora_del(servicio_id):
    from app import models as m
    from app import reloj
    from app.db import SessionLocal
    with SessionLocal() as db:
        return reloj.ahora_del_servicio(db, db.get(m.Servicio, servicio_id))


def _revision(cliente, sesion, servicio_id, quien="consultor", ahora=None):
    params = {"ahora": ahora.isoformat()} if ahora else None
    r = cliente.get(f"/cierre/servicio/{servicio_id}/revision",
                    headers=sesion(quien), params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _enviar(cliente, sesion, cierre_id, ahora=None, quien="consultor"):
    params = {"ahora": ahora.isoformat()} if ahora else None
    return cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                        headers=sesion(quien), params=params)


def _autorizar(cliente, sesion, cierre_id, cobro, nota=None,
               quien="diroperaciones"):
    return cliente.post(f"/cierre/{cierre_id}/autorizar-cobro",
                        headers=sesion(quien), json={"cobro": cobro, "nota": nota})


# ============================= 1 · cancelar con el equipo en la calle (a1-05)

def test_cancelar_con_el_equipo_en_la_calle_termina_el_dia_y_lo_cobra(
        cliente, sesion, datos, db):
    """Juan ya esta con el principal cuando el cliente corta el servicio.
    El dia termina con la hora de la cancelacion, firmado como terminado
    por cancelacion, entra al comparativo y la app lo ensena cerrado."""
    from app import models as m

    servicio = _servicio(cliente, sesion, datos, offset=0, dias=1,
                         hora="00:10:00")
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])
    hj = sesion("juan")
    assert marcar(cliente, hj, j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, hj, j["id"], "contacto_ejecutivo",
                  inicio).status_code == 200
    assert _jornada(j["id"])["estatus"] == "en_curso"

    antes = _ahora_del(servicio["id"])
    r = _cancelar(cliente, sesion, servicio["id"], motivo="El ejecutivo se regresa hoy")
    assert r.status_code == 200, r.text
    assert r.json()["dias_cancelados"] == 0
    assert len(r.json()["dias_terminados"]) == 1
    assert r.json()["cobro"] == "ejecutado"

    dia = _jornada(j["id"])
    assert dia["estatus"] == "terminada"
    assert dia["inicio_real"] == inicio
    assert timedelta(0) <= dia["fin_real"] - antes < timedelta(minutes=5)
    assert dia["cerrada_por"] == datos["personal"]["Ana Solis"]["id"]
    assert dia["motivo"].startswith("Terminado por cancelación")
    assert "El ejecutivo se regresa hoy" in dia["motivo"]
    # Queda en la bitacora del dia como cierre a mano.
    rastro = _bitacora(servicio["id"], "cerrar dia a mano")
    assert len(rastro) == 1 and rastro[0][1] == j["id"]
    assert "terminado por cancelación" in rastro[0][0]
    bitacora = cliente.get(f"/operacion/jornadas/{j['id']}/dia",
                           headers=sesion("central")).json()
    assert any(x["titulo"] == "cerrar dia a mano" for x in bitacora["renglones"])

    # El cierre nace con la cancelacion y el dia entra al comparativo.
    c = _cierre(servicio["id"])
    assert c and c["motivo"] == "cancelacion" and c["cobro"] == "ejecutado"
    comparativo = cliente.get(f"/cierre/servicio/{servicio['id']}/comparativo",
                              headers=sesion("consultor")).json()
    assert comparativo["ejecutado"]["dias"] == 1
    assert Decimal(str(comparativo["ejecutado"]["total"])) > 0
    assert not [d for d in comparativo["desviaciones"]
                if d["tipo"] == "dias_de_menos"]
    # Y cuenta como trabajado para la nomina: es una jornada terminada
    # con su gente, que entra al corte cuando el cierre vaya a facturacion.
    cierre = db.get(m.Cierre, c["id"])
    cierre.estatus = m.EstatusCierre.ENVIADO_FINANZAS
    db.flush()
    from app import nomina
    pendientes = nomina.jornadas_pendientes(db, datos["mx"]["id"])
    assert any(jj.id == j["id"] for jj, _ in pendientes)
    db.rollback()

    # La app lo ensena como un dia cerrado, no como uno cancelado.
    mi_dia = cliente.get("/campo/mi-dia", headers=hj).json()
    assert all(f["jornada_id"] != j["id"] for f in mi_dia["hoy"])
    assert mi_dia["cerrados_hoy"] == 1


def test_arribado_antes_de_la_presentacion_termina_desde_su_llegada(
        cliente, sesion, datos):
    """El equipo llego al punto dos horas antes y el cliente cancela
    antes de la hora de presentacion: el dia termina ahora y sus horas
    corren desde que llego, no desde una presentacion que no ocurrio."""
    cuando = datetime.now().replace(microsecond=0) + timedelta(hours=2)
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(cuando.date(), datos["modalidades"]["full_day"]["id"],
                 hora=cuando.strftime("%H:%M:%S"))],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    llego = datetime.now().replace(microsecond=0)
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen", llego)
    assert r.status_code == 200, r.text
    assert _jornada(j["id"])["estatus"] == "arribado"

    r = _cancelar(cliente, sesion, servicio["id"])
    assert r.status_code == 200, r.text
    dia = _jornada(j["id"])
    assert dia["estatus"] == "terminada"
    assert dia["inicio_real"] == llego
    assert llego <= dia["fin_real"] < cuando
    assert dia["motivo"].startswith("Terminado por cancelación")
    assert _cierre(servicio["id"])["motivo"] == "cancelacion"


def test_el_dia_que_no_arranco_se_cancela_como_antes(cliente, sesion, datos):
    """El segundo dia, que nadie habia empezado, se queda cancelado; el
    primero, ya trabajado, se queda terminado."""
    servicio = _primer_dia_trabajado(cliente, sesion, datos, offset=2200)
    dias = servicio["equipos"][0]["jornadas"]
    r = _cancelar(cliente, sesion, servicio["id"])
    assert r.status_code == 200, r.text
    assert r.json()["dias_cancelados"] == 1
    assert r.json()["dias_terminados"] == []
    assert _jornada(dias[0]["id"])["estatus"] == "terminada"
    assert _jornada(dias[1]["id"])["estatus"] == "cancelada"


# ============================== 1 · el cobro: completo o ejecutado (a1-20)

def test_cancelar_con_cobro_completo_no_se_manda_sin_autorizar(
        cliente, sesion, datos):
    """El consultor pide cobrar completo. El cierre lo guarda, la revision
    lo frena y el envio a finanzas contesta 409 con que hacer hasta que
    operaciones lo autorice."""
    servicio = _primer_dia_trabajado(cliente, sesion, datos, offset=2210)
    r = _cancelar(cliente, sesion, servicio["id"], cobro="completo")
    assert r.status_code == 200, r.text
    assert r.json()["cobro"] == "completo"
    c = _cierre(servicio["id"])
    assert c["cobro"] == "completo" and c["autorizado_en"] is None
    assert any("cobro pedido: completo" in d
               for d, _ in _bitacora(servicio["id"], "cancelar servicio"))

    estado = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                         headers=sesion("consultor")).json()
    assert estado["cobro"] == {"cobro": "completo", "autorizado": False,
                               "autorizado_en": None, "autorizado_por": None}
    assert estado["cobro_por_autorizar"] is True

    ahora = c["abierto_en"] + timedelta(hours=1)
    envio = _enviar(cliente, sesion, c["id"], ahora)
    assert envio.status_code == 409, envio.text
    detalle = envio.json()["detail"]
    assert "autorice el cobro" in detalle["mensaje"]
    assert "Autorizar el cobro" in detalle["que_hacer"]

    revision = _revision(cliente, sesion, servicio["id"], ahora=ahora)
    assert revision["listo_para_finanzas"] is False
    graves = [o for o in revision["observaciones"] if o["nivel"] == "corregir"]
    assert [o["clave"] for o in graves] == ["cobro_por_autorizar"]
    assert graves[0]["datos"] == {"cobro": "completo"}
    assert _cierre(servicio["id"])["estatus"] == "sin_visto_bueno"


def test_sin_cotizacion_no_se_pide_completo(cliente, sesion, datos):
    """Completo es la cotizacion autorizada tal cual: sin ella no hay
    nada que cobrar completo, y la cancelacion lo dice."""
    servicio = _primer_dia_trabajado(cliente, sesion, datos, offset=2220,
                                     cotizado=False)
    r = _cancelar(cliente, sesion, servicio["id"], cobro="completo")
    assert r.status_code == 409, r.text
    assert "cotización autorizada" in r.json()["detail"]["mensaje"]
    assert "ejecutado" in r.json()["detail"]["que_hacer"]
    r = _cancelar(cliente, sesion, servicio["id"], cobro="ejecutado")
    assert r.status_code == 200, r.text


def test_el_director_autoriza_el_cobro_completo_y_se_factura_lo_cotizado(
        cliente, sesion, datos):
    """Direccion de operaciones autoriza el cobro completo: queda en la
    bitacora, al consultor le llega el correo, el cierre se puede mandar
    y lo que se factura es el total de la cotizacion, con el dia que ya
    no se trabajo."""
    from app import models as m

    servicio = _primer_dia_trabajado(cliente, sesion, datos, offset=2230)
    assert _cancelar(cliente, sesion, servicio["id"], cobro="completo").status_code == 200
    c = _cierre(servicio["id"])
    ana = datos["personal"]["Ana Solis"]

    # El consultor no autoriza su propio cobro; la central tampoco.
    assert _autorizar(cliente, sesion, c["id"], "completo",
                      quien="consultor").status_code == 403
    assert _autorizar(cliente, sesion, c["id"], "completo",
                      quien="central").status_code == 403
    r = _autorizar(cliente, sesion, c["id"], "completo")
    assert r.status_code == 200, r.text
    assert r.json()["cobro"] == "completo" and r.json()["pedido"] == "completo"
    assert r.json()["autorizado_por"] == "Jose Luis Pichardo"
    assert r.json()["cierre"]["cobro"]["autorizado"] is True
    assert r.json()["cierre"]["cobro_por_autorizar"] is False

    rastro = _bitacora(servicio["id"], "autorizar cobro")
    assert len(rastro) == 1 and "se cobra completo" in rastro[0][0]
    correos = _avisos(servicio["id"], m.Destinatario.CONSULTOR)
    autorizo = [x for x in correos if "autorizó el cobro" in x["asunto"]]
    assert len(autorizo) == 1 and autorizo[0]["correo"] == ana["correo"]
    assert "completo" in autorizo[0]["asunto"]
    assert "cotización autorizada tal cual" in autorizo[0]["cuerpo"]

    ahora = c["abierto_en"] + timedelta(hours=1)
    revision = _revision(cliente, sesion, servicio["id"], ahora=ahora)
    assert revision["listo_para_finanzas"] is True, revision["observaciones"]
    cmp = revision["comparativo"]
    assert cmp["a_facturar"]["completo"] is True
    assert Decimal(str(cmp["a_facturar"]["servicio"])) == Decimal(str(cmp["cotizacion"]["servicio"]))
    assert Decimal(str(cmp["ejecutado"]["total"])) < Decimal(str(cmp["cotizacion"]["total"]))

    envio = _enviar(cliente, sesion, c["id"], ahora)
    assert envio.status_code == 200, envio.text
    despues = _cierre(servicio["id"])
    assert despues["estatus"] == "enviado_finanzas"
    assert Decimal(str(despues["total_ejecutado"])) == Decimal(str(despues["total_cotizado"]))
    assert Decimal(str(despues["total_cotizado"])) == Decimal(str(cmp["cotizacion"]["total"]))
    # Y la factura lleva los dos dias, con la nota de por que.
    from app import facturacion
    from app.db import SessionLocal
    with SessionLocal() as db:
        cuerpo = facturacion.armar(db, db.get(m.Cierre, c["id"]))
    assert Decimal(cuerpo["total"]) == Decimal(str(cmp["cotizacion"]["total"]))
    assert len({x["fecha"] for x in cuerpo["conceptos"]}) == 2
    assert "completo" in cuerpo["nota"]
    # Con el visto bueno dado el cobro ya no se cambia.
    r = _autorizar(cliente, sesion, c["id"], "ejecutado", nota="Mejor lo ejecutado")
    assert r.status_code == 409, r.text
    assert "finanzas" in r.json()["detail"]["que_hacer"]


def test_con_cobro_ejecutado_autorizado_se_factura_lo_trabajado(
        cliente, sesion, datos):
    """El consultor pidio completo y el director decide ejecutado, con su
    nota: se manda y lo que se factura es el dia que si se trabajo. La
    nota es obligatoria cuando cambia lo pedido."""
    from app import models as m

    servicio = _primer_dia_trabajado(cliente, sesion, datos, offset=2240)
    assert _cancelar(cliente, sesion, servicio["id"], cobro="completo").status_code == 200
    c = _cierre(servicio["id"])
    r = _autorizar(cliente, sesion, c["id"], "ejecutado")
    assert r.status_code == 400, r.text
    assert "di por qué" in r.json()["detail"]["mensaje"]
    # Direccion general lo alcanza por lo que hereda.
    r = _autorizar(cliente, sesion, c["id"], "ejecutado",
                   nota="El cliente avisó con tiempo: solo lo trabajado",
                   quien="dirgeneral")
    assert r.status_code == 200, r.text
    assert r.json()["pedido"] == "completo" and r.json()["cobro"] == "ejecutado"
    rastro = _bitacora(servicio["id"], "autorizar cobro")[0][0]
    assert "el consultor pidió completo" in rastro and "avisó con tiempo" in rastro
    correo = [x for x in _avisos(servicio["id"], m.Destinatario.CONSULTOR)
              if "autorizó el cobro" in x["asunto"]][0]
    assert "solo lo trabajado" in correo["datos"]

    ahora = c["abierto_en"] + timedelta(hours=1)
    cmp = _revision(cliente, sesion, servicio["id"], ahora=ahora)["comparativo"]
    assert cmp["a_facturar"]["completo"] is False
    assert Decimal(str(cmp["a_facturar"]["servicio"])) == Decimal(str(cmp["ejecutado"]["total"]))
    envio = _enviar(cliente, sesion, c["id"], ahora)
    assert envio.status_code == 200, envio.text
    despues = _cierre(servicio["id"])
    assert Decimal(str(despues["total_ejecutado"])) == Decimal(str(cmp["ejecutado"]["total"]))
    assert Decimal(str(despues["total_ejecutado"])) < Decimal(str(despues["total_cotizado"]))
    # El dia trabajado entra a la nomina; el cancelado no.
    from app import nomina
    from app.db import SessionLocal
    dias = servicio["equipos"][0]["jornadas"]
    with SessionLocal() as db:
        pendientes = {j.id for j, _ in nomina.jornadas_pendientes(db, datos["mx"]["id"])}
    assert dias[0]["id"] in pendientes and dias[1]["id"] not in pendientes


# ======================== 1 · los dias cancelados no piden recotizar (a4-01)

def test_los_dias_cancelados_de_un_cancelado_no_piden_recotizar(
        cliente, sesion, datos):
    """Antes cada dia cotizado que no se trabajo era un "dias de menos"
    grave, y las dos salidas --recotizar o justificar-- no existian en
    un cancelado. Ahora es informativo y dice que se cobra."""
    servicio = _primer_dia_trabajado(cliente, sesion, datos, offset=2250)
    dias = servicio["equipos"][0]["jornadas"]
    assert _cancelar(cliente, sesion, servicio["id"], cobro="ejecutado").status_code == 200
    c = _cierre(servicio["id"])
    assert _autorizar(cliente, sesion, c["id"], "ejecutado").status_code == 200

    ahora = c["abierto_en"] + timedelta(hours=1)
    revision = _revision(cliente, sesion, servicio["id"], ahora=ahora)
    assert revision["listo_para_finanzas"] is True, revision["observaciones"]
    assert not [o for o in revision["observaciones"]
                if o["asunto"] == "dias_de_menos"]
    cancelados = [o for o in revision["observaciones"]
                  if o.get("clave") == "dia_cancelado"]
    assert len(cancelados) == 2, "el rol y la unidad del dia que no fue"
    assert all(o["nivel"] == "informativo" for o in cancelados)
    assert cancelados[0]["datos"]["completo"] is False
    assert cancelados[0]["datos"]["fecha"] == dias[1]["fecha"]
    assert "No se cobra" in cancelados[0]["accion"]
    informativas = [d for d in revision["comparativo"]["desviaciones"]
                    if d.get("informativa")]
    assert len(informativas) == 2 and all(
        Decimal(str(d["monto"])) < 0 for d in informativas)


def test_un_dia_cancelado_en_un_servicio_terminado_si_se_justifica(
        cliente, sesion, datos):
    """El caso hermano: el cliente cancelo un dia de dos y el servicio
    termino. Ese dia sigue siendo un "dias de menos" que se justifica, y
    la revision lo marca justificable para que la tarjeta ofrezca el
    boton (la ruta existia y ningun boton la llamaba)."""
    servicio = _servicio(cliente, sesion, datos, offset=2260, dias=2)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    r = cliente.delete(f"/servicios/jornadas/{dias[1]['id']}", headers=h)
    assert r.status_code == 200, r.text
    assert ejecutar_jornada(cliente, sesion("juan"), dias[0]).status_code == 200
    c = _cierre(servicio["id"])
    ahora = c["abierto_en"] + timedelta(hours=1)
    revision = _revision(cliente, sesion, servicio["id"], ahora=ahora)
    graves = [o for o in revision["observaciones"]
              if o["nivel"] == "corregir" and o["asunto"] == "dias_de_menos"]
    assert len(graves) == 2 and all(o.get("justificable") for o in graves)
    # Y se justifica tal como la dice la revision.
    _enviar(cliente, sesion, c["id"], ahora)
    for o in graves:
        r = cliente.post(f"/cierre/{c['id']}/desviaciones/respaldar", headers=h,
                         params={"descripcion": o["mensaje"]},
                         json={"justificacion": "El cliente canceló ese día con una semana"})
        assert r.status_code == 200, r.text
    assert _revision(cliente, sesion, servicio["id"], ahora=ahora)["listo_para_finanzas"]


def test_el_cancelado_se_cotiza_mientras_no_tenga_visto_bueno(
        cliente, sesion, datos):
    """Se cancela con un dia trabajado y sin cotizacion: antes el bloque
    contestaba "esta cancelado" y el cierre no tenia salida. Ahora se
    registra, con los dias cancelados a la vista, y con el visto bueno
    dado ya no."""
    servicio = _primer_dia_trabajado(cliente, sesion, datos, offset=2270,
                                     cotizado=False)
    dias = servicio["equipos"][0]["jornadas"]
    assert _cancelar(cliente, sesion, servicio["id"]).status_code == 200
    h = sesion("consultor")
    bloque = cliente.get(f"/cotizaciones/servicio/{servicio['id']}/bloque",
                         headers=h).json()
    assert bloque["se_puede"] is True and bloque["con_visto_bueno"] is False
    assert [d["fecha"] for d in bloque["dias"]] == [dias[0]["fecha"], dias[1]["fecha"]]

    lineas = []
    for d in dias:
        lineas.append({"fecha": d["fecha"], "tipo": "recurso",
                       "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]})
        lineas.append({"fecha": d["fecha"], "tipo": "vehiculo",
                       "categoria_id": datos["categorias"]["suv_blindada"]["id"]})
    r = cliente.post("/cotizaciones/autorizada", headers=h, json={
        "servicio_id": servicio["id"], "lineas": lineas, "gastos": "dentro",
        "autorizada_por": "Patricia Lundgren", "autorizada_el": str(manana(0))})
    assert r.status_code == 201, r.text
    assert r.json()["dias"] == 2

    c = _cierre(servicio["id"])
    assert _autorizar(cliente, sesion, c["id"], "ejecutado").status_code == 200
    ahora = c["abierto_en"] + timedelta(hours=1)
    assert _enviar(cliente, sesion, c["id"], ahora).status_code == 200
    bloque = cliente.get(f"/cotizaciones/servicio/{servicio['id']}/bloque",
                         headers=h).json()
    assert bloque["se_puede"] is False and bloque["con_visto_bueno"] is True
    r = cliente.post("/cotizaciones/autorizada", headers=h, json={
        "servicio_id": servicio["id"], "lineas": lineas, "gastos": "dentro",
        "autorizada_por": "Patricia Lundgren", "autorizada_el": str(manana(0)),
        "motivo": "Se recotiza con el visto bueno dado"})
    assert r.status_code == 409, r.text


def test_la_bandeja_de_cobros_por_autorizar(cliente, sesion, datos, db):
    """Lo que la pantalla del director va a pintar: el cancelado con su
    cobro pedido, lo cotizado y lo trabajado; y desaparece al autorizar."""
    from app import cierre as motor

    servicio = _primer_dia_trabajado(cliente, sesion, datos, offset=2280)
    assert _cancelar(cliente, sesion, servicio["id"], cobro="completo").status_code == 200
    filas = motor.cobros_por_autorizar(db)
    mia = next(f for f in filas if f["servicio_id"] == servicio["id"])
    assert mia["folio"] == servicio["folio"] and mia["cobro"] == "completo"
    assert mia["consultor"] == "Ana Solis" and mia["cliente"]
    assert mia["cancelado_en"] and mia["moneda"] == "MXN"
    assert mia["total_cotizado"] > mia["total_ejecutado"] > 0
    assert mia["pantalla"] == f"/consola/#/servicio/{servicio['id']}"

    c = _cierre(servicio["id"])
    assert _autorizar(cliente, sesion, c["id"], "completo").status_code == 200
    db.expire_all()
    assert all(f["servicio_id"] != servicio["id"] for f in motor.cobros_por_autorizar(db))


# ================================ 12 · cuando vence un plazo del cierre (a4-17)

def _terminado(cliente, sesion, datos, offset):
    """Un servicio de un dia, trabajado y terminado: su cierre nacio en
    comprobacion. Se avanza a mano al visto bueno --sin viaticos, T1
    llega en cuanto alguien pregunta-- y se devuelve con su T1."""
    from app import cierre as motor
    from app import models as m
    from app.db import SessionLocal

    servicio = _servicio(cliente, sesion, datos, offset, dias=1)
    assert ejecutar_jornada(cliente, sesion("juan"),
                            servicio["equipos"][0]["jornadas"][0]).status_code == 200
    c = _cierre(servicio["id"])
    t1 = c["abierto_en"] + timedelta(hours=1)
    with SessionLocal() as db:
        assert motor.avanzar(db, db.get(m.Cierre, c["id"]), t1) is True
        db.commit()
    c = _cierre(servicio["id"])
    assert c["estatus"] == "sin_visto_bueno" and c["visto_bueno_desde"] == t1
    return servicio, c


def _barrer(ahora):
    """Lo que hace la tarea de cada cinco minutos, a una hora dada."""
    from app import cierre as motor
    from app.db import SessionLocal
    with SessionLocal() as db:
        return motor.avisar_plazos(db, ahora)


def test_a_la_mitad_del_plazo_se_le_avisa_al_consultor_una_sola_vez(
        cliente, sesion, datos):
    """Van doce de sus veinticuatro horas: correo al consultor con hasta
    cuando. Dos vueltas mas del reloj no lo repiten, y antes de la mitad
    no sale nada."""
    from app import models as m

    servicio, c = _terminado(cliente, sesion, datos, offset=2300)
    t1, limite = c["visto_bueno_desde"], c["limite"]
    assert limite == t1 + timedelta(hours=24)

    assert _barrer(t1 + timedelta(hours=11)) == {"mitad": [], "vencidos": []}
    assert _barrer(t1 + timedelta(hours=12)) == {"mitad": [servicio["folio"]],
                                                 "vencidos": []}
    assert _barrer(t1 + timedelta(hours=13)) == {"mitad": [], "vencidos": []}
    assert _barrer(t1 + timedelta(hours=20)) == {"mitad": [], "vencidos": []}

    avisos = [x for x in _avisos(servicio["id"], m.Destinatario.CONSULTOR)
              if "mitad" in x["asunto"]]
    assert len(avisos) == 1, avisos
    assert avisos[0]["correo"] == datos["personal"]["Ana Solis"]["correo"]
    assert avisos[0]["idioma"] == "es"
    assert f"{limite:%d/%m}" in avisos[0]["cuerpo"] and f"{limite:%H:%M}" in avisos[0]["cuerpo"]
    assert avisos[0]["enlace"] == f"/consola/#/servicio/{servicio['id']}"
    assert _cierre(servicio["id"])["aviso_mitad_en"] == t1 + timedelta(hours=12)
    # El director no recibe nada a la mitad.
    assert _avisos(servicio["id"], m.Destinatario.COLABORADOR) == []


def test_al_vencer_se_avisa_al_consultor_y_al_director_una_sola_vez(
        cliente, sesion, datos, db):
    """Vencidas las veinticuatro horas: correo al consultor y al director
    de operaciones, una vez. El servicio sigue esperando el visto bueno
    y sale entre los plazos vencidos del director. La vuelta que llega
    ya vencida no manda el aviso de la mitad."""
    from app import cierre as motor
    from app import models as m

    servicio, c = _terminado(cliente, sesion, datos, offset=2310)
    t1, limite = c["visto_bueno_desde"], c["limite"]
    assert motor.plazos_vencidos(db, t1 + timedelta(hours=23)) == []

    vencido = t1 + timedelta(hours=25)
    assert _barrer(vencido) == {"mitad": [], "vencidos": [servicio["folio"]]}
    assert _barrer(vencido + timedelta(hours=1)) == {"mitad": [], "vencidos": []}
    assert _barrer(vencido + timedelta(days=3)) == {"mitad": [], "vencidos": []}

    al_consultor = _avisos(servicio["id"], m.Destinatario.CONSULTOR)
    vencidos = [x for x in al_consultor if "venció" in x["asunto"]]
    assert len(vencidos) == 1, al_consultor
    assert not [x for x in al_consultor if "mitad" in x["asunto"]]
    assert "sin comisión" in vencidos[0]["cuerpo"]
    assert f"{limite:%H:%M}" in vencidos[0]["cuerpo"]

    al_director = _avisos(servicio["id"], m.Destinatario.COLABORADOR)
    assert len(al_director) == 1, al_director
    assert al_director[0]["correo"] == "operaciones@centauro.lat"
    assert "Ana Solis" in al_director[0]["asunto"] and "venció" in al_director[0]["asunto"]
    assert "sin comisión" in al_director[0]["cuerpo"]
    assert "Ana Solis" in al_director[0]["datos"]

    despues = _cierre(servicio["id"])
    assert despues["estatus"] == "sin_visto_bueno", "no se mueve solo"
    assert despues["aviso_vencido_en"] == vencido and despues["aviso_mitad_en"] is None

    # La sesion de la prueba ya habia leido el cierre: se vuelve a leer.
    db.expire_all()
    filas = motor.plazos_vencidos(db, vencido + timedelta(hours=1))
    mia = next(f for f in filas if f["servicio_id"] == servicio["id"])
    assert mia["plazo"] == "consultor" and mia["consultor"] == "Ana Solis"
    assert mia["vencio_en"] == limite.isoformat()
    assert mia["desde_hace_minutos"] == 120 and mia["desde_hace"] == "2 h"
    assert mia["avisado_en"] == vencido.isoformat()
    assert mia["pantalla"] == f"/consola/#/servicio/{servicio['id']}"

    # Y el visto bueno fuera de plazo sigue saliendo, sin comision.
    envio = _enviar(cliente, sesion, c["id"], vencido + timedelta(hours=2))
    assert envio.status_code == 200, envio.text
    assert envio.json()["dentro_de_plazo"] is False


def test_regresado_por_finanzas_el_plazo_nuevo_vuelve_a_avisar(
        cliente, sesion, datos):
    """Finanzas lo regresa y corren otras 24 horas: la mitad y el
    vencimiento se avisan otra vez, con los textos del regreso, y el
    regreso limpia lo avisado del plazo anterior."""
    from app import models as m

    servicio, c = _terminado(cliente, sesion, datos, offset=2320)
    t1 = c["visto_bueno_desde"]
    assert _barrer(t1 + timedelta(hours=25))["vencidos"] == [servicio["folio"]]
    assert _cierre(servicio["id"])["aviso_vencido_en"] is not None

    assert _enviar(cliente, sesion, c["id"], t1 + timedelta(hours=26)).status_code == 200
    r = cliente.post(f"/cierre/{c['id']}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "La hora de termino esta mal capturada"})
    assert r.status_code == 200, r.text
    regresado = _cierre(servicio["id"])
    assert regresado["estatus"] == "devuelto_a_operacion"
    assert regresado["aviso_mitad_en"] is None and regresado["aviso_vencido_en"] is None
    devuelto = regresado["devuelto_en"]

    assert _barrer(devuelto + timedelta(hours=13)) == {"mitad": [servicio["folio"]],
                                                       "vencidos": []}
    assert _barrer(devuelto + timedelta(hours=25)) == {"mitad": [],
                                                       "vencidos": [servicio["folio"]]}
    assert _barrer(devuelto + timedelta(hours=26)) == {"mitad": [], "vencidos": []}

    al_consultor = _avisos(servicio["id"], m.Destinatario.CONSULTOR)
    mitades = [x for x in al_consultor if "mitad" in x["asunto"]]
    vencidos = [x for x in al_consultor if "venció" in x["asunto"]]
    assert len(mitades) == 1 and "regresó" in mitades[0]["cuerpo"]
    assert len(vencidos) == 2, "el del primer plazo y el del regreso"
    assert "regresó" in vencidos[-1]["cuerpo"] and "se queda" in vencidos[-1]["cuerpo"]
    al_director = _avisos(servicio["id"], m.Destinatario.COLABORADOR)
    assert len(al_director) == 2
    assert "regresó" in al_director[-1]["cuerpo"]

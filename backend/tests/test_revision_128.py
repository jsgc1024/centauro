# -*- coding: utf-8 -*-
"""Seccion 128: la ola 2 de la revision del 2 de octubre.

La entrega de la unidad que se escapaba (al cancelar con el equipo en
la calle, con dos unidades y en el mes del implantado); el reabrir que
deja la entrega colgada; la nota de «por reconfirmar» que se quedaba
junto a la palomita, y en espanol para la central de Brasil; el
freelance con urgencia al que la consola no le daba acceso; su baja con
dias asignados; el que RH contrata de planta y Odoo adivinaba; los
archivos con nombre raro que no se podian abrir; Google que tumbaba la
carga del expediente; el reto de la huella que valia como sesion; y la
huella que no quedaba en el historial.
"""
import os
from datetime import datetime, timedelta

import httpx
import pytest

from app import models as m
from ayudas import (KM_RECEPCION, asignar, configurar_origen,
                    cotizar_y_autorizar, crear_servicio, jornada, manana,
                    marcar, revisar_unidad)
from test_cierre_mes import DIAS, _alta as _alta_implantado, _cerrar, _jornadas
from test_odoo_personal import OdooFalso, empleado, leer
from test_odoo_personal import sin_rastro  # noqa: F401  (fixture)
from test_revision_111_freelance import (_alta as _alta_freelance, _asignar_equipo,
                                         _completar, _costos, _servicio as _eventual)
from test_revision_111_freelance import nuevos  # noqa: F401  (fixture)
from test_revision_111_freelance import db  # noqa: F401  (fixture)
from test_llaves import Telefono, _activar
from test_llaves import sin_llaves  # noqa: F401  (fixture)
from test_zona_horaria import brasil  # noqa: F401  (fixture)

WEB = os.path.join(os.path.dirname(__file__), "..", "app", "web")
MOTIVO = "El cliente cancelo el viaje desde su oficina"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _js(nombre: str) -> str:
    return open(os.path.join(WEB, nombre), encoding="utf-8").read()


@pytest.fixture
def salieron(monkeypatch):
    """Los avisos al telefono que se habrian mandado, sin salir a internet."""
    import pywebpush
    from app import push
    mandados = []

    def falso(**kwargs):
        mandados.append(kwargs)
        return True
    monkeypatch.setattr(pywebpush, "webpush", falso)
    monkeypatch.setattr(push.settings, "vapid_private", "llave-de-prueba")
    monkeypatch.setattr(push.settings, "vapid_public", "publica-de-prueba")
    return mandados


def _telefono(db, persona_id, endpoint):
    db.add(m.SuscripcionPush(persona_id=persona_id, endpoint=endpoint,
                             p256dh="clave-publica", auth="secreto"))
    db.commit()


def _entregas(db, servicio_id):
    db.expire_all()
    return (db.query(m.EntregaPendiente).filter_by(servicio_id=servicio_id)
            .order_by(m.EntregaPendiente.id).all())


def _servicio_de_juan(cliente, sesion, datos, offset, dias=1, hora="07:00:00"):
    """Un eventual de `dias` dias con Juan y la Suburban, cotizado."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"],
                 hora=hora) for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
    return servicio


def _fin(cliente, cabeceras, j):
    """El dia completo hasta el fin de servicio, a su hora programada."""
    inicio = datetime.fromisoformat(j["inicio_programado"])
    marcar(cliente, cabeceras, j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))
    marcar(cliente, cabeceras, j["id"], "contacto_ejecutivo", inicio)
    return marcar(cliente, cabeceras, j["id"], "fin_servicio",
                  datetime.fromisoformat(j["fin_programado"]),
                  ubicacion={"lat": 19.4326, "lon": -99.1332})


# =================================== r8-01 · cancelar con el equipo en la calle

def test_cancelar_con_dias_por_delante_deja_la_unidad_por_entregar(
        cliente, sesion, datos, db):
    """Tres dias; Juan esta con el principal el primero y el cliente
    corta el servicio. Los dos que faltaban se cancelan y la Suburban,
    que ya no vuelve a salir, queda por entregar. Antes el dia en la
    calle se terminaba con los otros dos todavia vivos y la camioneta
    salia del servicio sin que nadie la reclamara."""
    servicio = _servicio_de_juan(cliente, sesion, datos, offset=0, dias=3,
                                 hora="00:10:00")
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])
    hj = sesion("juan")
    assert marcar(cliente, hj, j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, hj, j["id"], "contacto_ejecutivo",
                  inicio).status_code == 200
    assert _entregas(db, servicio["id"]) == []

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     headers=sesion("consultor"), json={"motivo": MOTIVO})
    assert r.status_code == 200, r.text
    assert r.json()["dias_cancelados"] == 2
    assert len(r.json()["dias_terminados"]) == 1

    abiertas = _entregas(db, servicio["id"])
    assert len(abiertas) == 1
    assert abiertas[0].vehiculo_id == datos["suburban"]["id"]
    assert abiertas[0].persona_id == datos["personal"]["Juan Ramirez"]["id"]
    assert abiertas[0].cerrada_en is None
    # Y su app se la ensena para que la lleve a la oficina.
    mi_dia = cliente.get("/campo/mi-dia", headers=hj).json()
    assert [e["placa"] for e in mi_dia["entregas_pendientes"]] == [
        datos["suburban"]["placa"]]


# ======================================== r8-02 · dos unidades, un solo fin

def test_el_fin_del_companero_abre_la_entrega_de_la_unidad_de_juan(
        cliente, sesion, datos, db):
    """Juan trae la Suburban y Luis va en la otra unidad. Luis marca el
    fin --que cierra el dia de todos-- y Juan ya no marca nada: la
    Suburban queda por entregar igual, a nombre de Juan, y su app se la
    ensena. Antes solo se abrian las unidades de quien marcaba."""
    h = sesion("consultor")
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["plaza_id"] == datos["suburban"]["plaza_id"])
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(128), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    for persona in (juan, luis):
        for r in asignar(cliente, h, j["id"], persona_id=persona):
            assert r.status_code == 200, r.text
    for unidad in (datos["suburban"]["id"], otra["id"]):
        for r in asignar(cliente, h, j["id"], vehiculo_id=unidad):
            assert r.status_code == 200, r.text
    assert cliente.patch(
        f"/servicios/jornadas/{j['id']}/personal/{juan}/unidad",
        json={"vehiculo_id": datos["suburban"]["id"]},
        headers=h).status_code == 200
    configurar_origen(cliente, h, j["id"])

    r = _fin(cliente, sesion("luis"), j)
    assert r.status_code == 200, r.text
    # A Luis no le toca ninguna: no trae unidad asignada.
    assert r.json()["entregas_pendientes"] == []
    abiertas = _entregas(db, servicio["id"])
    assert [(e.vehiculo_id, e.persona_id) for e in abiertas] == [
        (datos["suburban"]["id"], juan)]
    luego = (datetime.fromisoformat(j["fin_programado"])
             + timedelta(hours=1)).isoformat()
    assert cliente.get(f"/campo/mi-dia?ahora={luego}",
                       headers=sesion("luis")).json()["entregas_pendientes"] == []
    pendientes = cliente.get(f"/campo/mi-dia?ahora={luego}",
                             headers=sesion("juan")).json()["entregas_pendientes"]
    assert [e["placa"] for e in pendientes] == [datos["suburban"]["placa"]]
    # Y si Juan marca su fin despues, su app le ensena la suya aunque la
    # haya abierto el fin de Luis.
    r = _fin(cliente, sesion("juan"), j)
    assert r.status_code == 200, r.text
    assert [e["placa"] for e in r.json()["entregas_pendientes"]] == [
        datos["suburban"]["placa"]]
    assert len(_entregas(db, servicio["id"])) == 1


# ================================= r8-03 · el mes del implantado la reclama

def test_el_mes_del_implantado_no_sale_a_finanzas_con_la_unidad_sin_entregar(
        cliente, sesion, datos, db):
    """La central cierra a mano los cinco dias de septiembre; el viernes
    no tiene un dia despues y la Suburban queda por entregar. La revision
    del mes lo dice y el visto bueno no sale; con la entrega hecha, sale.
    Antes el mes no miraba las entregas y el renglon se quedaba en la
    central para siempre."""
    sid = _alta_implantado(cliente, sesion, datos)["servicio_id"]
    jornadas = _jornadas(cliente, sesion, sid)
    for dia in DIAS:
        _cerrar(cliente, sesion, jornadas[dia], dia)
    abiertas = _entregas(db, sid)
    assert len(abiertas) == 1 and abiertas[0].cerrada_en is None

    cierre = db.query(m.Cierre).filter_by(servicio_id=sid).one()
    h = sesion("consultor")
    r = cliente.post(f"/cierre/{cierre.id}/enviar-finanzas", headers=h,
                     params={"ahora": datetime(2029, 9, 28, 22).isoformat()})
    assert r.status_code == 409, r.text
    claves = [o["clave"] for o in r.json()["detail"]["observaciones"]]
    assert "entrega_pendiente" in claves

    # Juan la entrega esa noche y el mes sale.
    hj = sesion("juan")
    assert revisar_unidad(cliente, hj, sid, datos["suburban"]["id"],
                          "recibe", KM_RECEPCION).status_code == 201
    assert revisar_unidad(cliente, hj, sid, datos["suburban"]["id"],
                          "entrega", KM_RECEPCION + 300).status_code == 201
    assert _entregas(db, sid)[0].cerrada_en is not None
    r = cliente.post(f"/cierre/{cierre.id}/enviar-finanzas", headers=h,
                     params={"ahora": datetime(2029, 9, 28, 23).isoformat()})
    assert r.status_code == 200, r.text


def test_la_ficha_del_implantado_y_la_central_llevan_a_la_entrega():
    """El bloque de revisiones de la unidad vive tambien en la ficha del
    implantado, y el renglon de la central lleva a la pantalla que es:
    el implantado abria la ficha del eventual."""
    assert "bloqueRevisiones" in _js("implantado.js")
    assert "export async function bloqueRevisiones" in _js("servicio.js")
    central = _js("central.js")
    assert "rutaDelServicio(e)" in central
    assert "/implantado/" in central


def test_al_abrir_el_mes_la_unidad_que_sigue_deja_de_estar_por_entregar(
        cliente, sesion, datos, db):
    """El proceso que abre octubre no corrio y la central cerro el ultimo
    dia de septiembre: la Suburban quedo por entregar. Al abrir octubre
    la camioneta vuelve a tener dias y la entrega abierta se va: no hay
    que pedir fotos de una entrega que nunca paso."""
    sid = _alta_implantado(cliente, sesion, datos)["servicio_id"]
    jornadas = _jornadas(cliente, sesion, sid)
    for dia in DIAS:
        _cerrar(cliente, sesion, jornadas[dia], dia)
    assert len(_entregas(db, sid)) == 1
    # El proceso de todas las mananas, corriendo por fin el 29.
    from datetime import date
    from app import implantado
    hecho = implantado.abrir_los_que_toquen(db, hoy=date(2029, 9, 29))
    assert [a["periodo"] for a in hecho["abiertos"] if a["servicio_id"] == sid] == [
        "10/2029"], hecho
    assert _entregas(db, sid) == []


def test_el_sabado_que_entra_despues_del_viernes_cerrado_se_lleva_la_entrega(
        cliente, sesion, datos, db):
    """El viernes cerro y la Suburban quedo por entregar; el cliente pide
    el sabado. La camioneta sigue: la entrega abierta se va y vuelve a
    nacer con el cierre del sabado, que ahora si es el ultimo dia."""
    from datetime import date
    alta = _alta_implantado(cliente, sesion, datos)
    sid = alta["servicio_id"]
    jornadas = _jornadas(cliente, sesion, sid)
    for dia in DIAS:
        _cerrar(cliente, sesion, jornadas[dia], dia)
    assert len(_entregas(db, sid)) == 1
    sabado = date(2029, 9, 29)
    r = cliente.post(f"/implantados/contratos/{alta['contrato_id']}/dias-adicionales",
                     json={"fecha": str(sabado)}, headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert _entregas(db, sid) == []
    _cerrar(cliente, sesion, _jornadas(cliente, sesion, sid)[sabado], sabado)
    abiertas = _entregas(db, sid)
    assert len(abiertas) == 1
    assert abiertas[0].jornada.fecha == sabado


# ======================================= r8-05 · reabrir el dia cerrado a mano

def test_reabrir_el_dia_se_lleva_la_entrega_que_abrio(cliente, sesion, datos, db):
    """La central cerro a mano con la hora equivocada y reabre: la
    entrega que nacio con ese cierre se va, y vuelve a nacer con el
    cierre bueno. Antes se quedaba abierta con su reloj corriendo sobre
    un dia que ya no estaba cerrado."""
    servicio = _servicio_de_juan(cliente, sesion, datos, offset=400)
    j = servicio["equipos"][0]["jornadas"][0]
    termino = datetime.fromisoformat(j["fin_programado"])
    central = sesion("central")
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     headers=central, json={"justificacion": MOTIVO},
                     params={"ahora": (termino + timedelta(hours=1)).isoformat()})
    assert r.status_code == 200, r.text
    assert len(_entregas(db, servicio["id"])) == 1

    r = cliente.post(f"/operacion/jornadas/{j['id']}/reabrir", headers=central,
                     json={"justificacion": "Se cerro con la hora equivocada"})
    assert r.status_code == 200, r.text
    assert _entregas(db, servicio["id"]) == []

    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     headers=central, json={"justificacion": MOTIVO},
                     params={"ahora": (termino + timedelta(hours=2)).isoformat()})
    assert r.status_code == 200, r.text
    abiertas = _entregas(db, servicio["id"])
    assert len(abiertas) == 1 and abiertas[0].jornada_id == j["id"]


# ================================= r8-04 · la nota de «por reconfirmar»

def test_al_reconfirmar_se_va_la_nota_y_en_brasil_va_en_portugues(
        cliente, sesion, datos, db, brasil):
    """Un servicio en Sao Paulo: Juan confirma, el consultor mueve la
    hora y la nota --en portugues, que es lo que lee la central de alla--
    dice por que vuelve a estar por confirmar. Juan reconfirma y la nota
    se va: la central veia la palomita y la razon juntas."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(129), datos["modalidades"]["full_day"]["id"])],
        pais_id=brasil["pais"]["id"], plaza_id=brasil["plaza"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    assert asignar(cliente, h, j["id"], persona_id=juan)[0].status_code == 200
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text

    r = cliente.patch(f"/servicios/jornadas/{j['id']}",
                      json={"hora_presentacion": "08:30:00"}, headers=h)
    assert r.status_code == 200, r.text
    fila = (db.query(m.AsignacionPersonal)
            .filter_by(jornada_id=j["id"], persona_id=juan).one())
    db.refresh(fila)
    assert fila.confirmado is False
    assert fila.nota_confirmacion.startswith("por reconfirmar")
    assert "o horário mudou" in fila.nota_confirmacion
    assert "07:00" in fila.nota_confirmacion

    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text
    db.refresh(fila)
    assert fila.confirmado is True
    assert fila.nota_confirmacion is None
    assert fila.confirmado_por_id is None


def test_los_textos_de_reconfirmar_existen_en_los_tres_idiomas():
    from app import push
    for lengua in ("es", "en", "pt"):
        for clave in ("reconfirmar_hora", "reconfirmar_fecha"):
            texto = push.tx(lengua, clave, antes="07:00")
            assert texto.startswith("por reconfirmar"), (lengua, clave, texto)
            assert "07:00" in texto


# ================================ r6-02 · el acceso del freelance urgente

def test_la_ficha_dice_que_el_urgente_puede_tener_acceso(
        cliente, sesion, datos, nuevos, db):
    """Sin expediente la ficha dice que no; con la urgencia autorizada
    dice que si, con la misma regla que la puerta de dar acceso. La
    consola decidia solo con el expediente y dejaba el boton en gris al
    urgente que el servidor si aceptaba."""
    h = sesion("consultor")
    persona_id = _alta_freelance(cliente, h, datos, nuevos)
    _costos(cliente, sesion, persona_id)
    ficha = cliente.get(f"/freelance/{persona_id}", headers=h).json()
    assert ficha["puede_acceso"] is False
    assert ficha["expediente"]["asignable"] is False

    servicio = _eventual(cliente, sesion, datos, desde=130)
    r = cliente.post(f"/freelance/{persona_id}/urgencias", json={
        "servicio_id": servicio["id"],
        "motivo": "El conductor de planta se enfermo y no hay otro en CDMX"},
        headers=h)
    assert r.status_code == 201, r.text
    assert cliente.post(f"/freelance/urgencias/{r.json()['id']}/autorizar",
                        json={"respuesta": "Solo este servicio"},
                        headers=sesion("diroperaciones")).status_code == 200
    ficha = cliente.get(f"/freelance/{persona_id}", headers=h).json()
    assert ficha["puede_acceso"] is True
    assert ficha["expediente"]["asignable"] is False
    r = cliente.post(f"/freelance/{persona_id}/acceso", headers=h)
    assert r.status_code == 200, r.text
    # La pantalla decide con lo que dice la ficha, no con el expediente.
    assert "f.puede_acceso" in _js("freelance.js")


# ================================ r6-04 · la baja con dias asignados

def test_la_baja_del_freelance_avisa_de_los_dias_que_deja(
        cliente, sesion, datos, nuevos, db, salieron):
    """Esta asignado a un dia de la semana que entra y lo dan de baja:
    la alerta queda en ese dia, el consultor recibe el aviso en su
    telefono y la respuesta dice que queda por cubrir. Antes la baja lo
    desactivaba y nadie se enteraba de que ese dia quedaba sin nadie."""
    h = sesion("consultor")
    persona_id = _alta_freelance(cliente, h, datos, nuevos)
    _costos(cliente, sesion, persona_id)
    _completar(cliente, sesion, persona_id)
    servicio = _eventual(cliente, sesion, datos, desde=131)
    assert _asignar_equipo(cliente, h, servicio, persona_id).status_code == 200
    j = servicio["equipos"][0]["jornadas"][0]
    ana = datos["personal"]["Ana Solis"]["id"]
    _telefono(db, ana, "https://push.example/128-baja")

    r = cliente.post(f"/freelance/{persona_id}/baja",
                     json={"motivo": "Ya no colabora con nosotros"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_por_cubrir"]
    assert r.json()["aviso"] and "cubrir" in r.json()["aviso"]
    alerta = (db.query(m.Alerta)
              .filter_by(jornada_id=j["id"], tipo=m.TipoAlerta.PERSONAL_DE_BAJA)
              .one())
    assert "freelance" in alerta.mensaje and alerta.persona_id == persona_id
    assert len(salieron) == 1, salieron
    assert "ya no esta en la empresa" in str(salieron[0]["data"])
    assert "acc_deja_dias" in _js("freelance.js")
    # Reactivarlo y volverlo a dar de baja no apila otra alerta sobre la
    # que la central no ha atendido.
    assert cliente.post(f"/freelance/{persona_id}/reactivar",
                        headers=h).status_code == 200
    r = cliente.post(f"/freelance/{persona_id}/baja",
                     json={"motivo": "Ya no colabora, otra vez"}, headers=h)
    assert r.status_code == 200, r.text
    assert (db.query(m.Alerta)
            .filter_by(jornada_id=j["id"], tipo=m.TipoAlerta.PERSONAL_DE_BAJA)
            .count()) == 1


# ===================== r6-01 · el freelance que RH contrata de planta

def test_el_freelance_que_aparece_en_odoo_queda_pendiente_y_no_se_liga(
        cliente, sesion, datos, nuevos, db):
    """RH lo contrata de planta y lo captura en Odoo con su mismo correo.
    La lectura no lo adivina: queda pendiente, con la razon, y sigue
    siendo freelance hasta que alguien lo pase a mano. Antes se ligaba y
    quedaba freelance a medias."""
    persona_id = _alta_freelance(cliente, sesion("consultor"), datos, nuevos)
    persona = db.get(m.Persona, persona_id)
    correo = persona.correo
    informe = leer(db, OdooFalso(empleado(1, private_email=correo,
                                          work_email=False)))
    assert informe["altas"] == [] and informe["vinculadas"] == []
    assert [(p["persona_id"], p["falta"]) for p in informe["pendientes"]] == [
        (persona_id, ["en Centauro es freelance; en Odoo ya es de planta: "
                      "pasarlo a mano"])]
    db.expire_all()
    persona = db.get(m.Persona, persona_id)
    assert persona.es_freelance and persona.odoo_id is None
    # Y la pantalla de Odoo sabe decirlo en los tres idiomas.
    assert "odo_f_freelance_de_planta" in _js("odoo.js")
    assert _js("idioma.js").count("    odo_f_freelance_de_planta:") == 3


# ================================ r4-03 · la CNH como archivo en Odoo

def test_un_campo_de_archivo_nunca_es_el_de_la_cnh():
    """Si RH crea «CNH» en Odoo como archivo, no se lee: cada hora
    bajaria la licencia escaneada de todos. Se toma el campo que dice su
    nombre, o el de Odoo, o ninguno."""
    from app.odoo_personal_reglas import campos_por_capturar
    base = {"name": {"type": "char", "string": "Nombre"},
            "identification_id": {"type": "char",
                                  "string": "Número de identificación"}}
    con_nombre = {**base,
                  "x_studio_cnh": {"type": "binary", "string": "CNH"},
                  "x_studio_cnh_filename": {"type": "char",
                                            "string": "CNH Filename"},
                  "driving_license_name": {"type": "char",
                                           "string": "Licencia para conducir"}}
    assert campos_por_capturar(con_nombre)["cnh"] == "x_studio_cnh_filename"
    solo_odoo = {**base, "x_studio_cnh": {"type": "binary", "string": "CNH"},
                 "driving_license_name": {"type": "char",
                                          "string": "Licencia para conducir"}}
    assert campos_por_capturar(solo_odoo)["cnh"] == "driving_license_name"
    nada = {**base, "x_studio_cnh": {"type": "binary", "string": "CNH"},
            "x_studio_foto_cnh": {"type": "image", "string": "Foto CNH"}}
    assert campos_por_capturar(nada)["cnh"] is None


# ================================== r6-05 · Google que no contesta

def test_si_google_no_contesta_es_un_fallo_y_no_un_reventon():
    """Un tiempo de espera o una conexion caida en httpx se dice como
    `Fallo`, que es lo que quien guarda el expediente sabe atrapar para
    dejar el archivo aqui hasta la mudanza. Antes se escapaba y tumbaba
    la carga entera."""
    from app import archivo

    class Respuesta:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "permiso", "expires_in": 300}

    class HttpCaido:
        def get(self, url, **kwargs):
            if "metadata" in url.lower():
                return Respuesta()
            raise httpx.ReadTimeout("Google tardo demasiado")

        def post(self, url, **kwargs):
            raise httpx.ConnectError("sin red")

    google = archivo.Google("gs://centauro-expedientes/pruebas", http=HttpCaido())
    with pytest.raises(archivo.Fallo) as error:
        google.describir("alguien/documento.pdf")
    assert "ReadTimeout" in str(error.value)
    with pytest.raises(archivo.Fallo):
        google.bajar("alguien/documento.pdf")
    with pytest.raises(archivo.Fallo):
        google.subir("alguien/documento.pdf", b"%PDF", "application/pdf", {})


# ============================= r7-01 · los archivos con nombre raro

def test_el_archivo_con_guion_largo_y_acentos_se_abre(
        cliente, sesion, datos, nuevos, db):
    """«Autorización – Henkel.pdf» se guardaba bien y nunca se podia
    abrir: Starlette codifica las cabeceras en Latin-1 y el guion largo
    la reventaba (500). Ahora va con un nombre parecido en ASCII y el
    completo en `filename*`, y sin cache."""
    from app.archivo import cabecera_de_archivo
    cabecera = cabecera_de_archivo("Autorización – Henkel.pdf")
    assert cabecera["Content-Disposition"] == (
        'inline; filename="Autorizacion - Henkel.pdf"; '
        "filename*=UTF-8''Autorizaci%C3%B3n%20%E2%80%93%20Henkel.pdf")
    cabecera["Content-Disposition"].encode("latin-1")
    assert cabecera["Cache-Control"] == "no-store"
    assert cabecera_de_archivo("Captura de pantalla 2026-10-02 a la(s) 9.15.43 a.m..png",
                               bajar=True)["Content-Disposition"].startswith(
        'attachment; filename="Captura de pantalla 2026-10-02 a la(s) 9.15.43 a.m..png"')
    assert cabecera_de_archivo("")["Content-Disposition"].startswith(
        'inline; filename="archivo"')

    # De punta a punta: el documento del expediente con ese nombre.
    rh = sesion("rrhh")
    persona_id = _alta_freelance(cliente, sesion("consultor"), datos, nuevos)
    exp = cliente.get(f"/freelance/{persona_id}/expediente", headers=rh).json()
    req = next(r for r in exp["requisitos"] if r["captura"] == "archivo")
    r = cliente.post(
        f"/freelance/{persona_id}/expediente/{req['requisito_id']}",
        data={"datos": "{}", "validar": "false",
              "vence_en": (datetime.now() + timedelta(days=900)).date().isoformat()},
        files=[("archivos", ("Autorización – Henkel.pdf", PDF, "application/pdf"))],
        headers=rh)
    assert r.status_code == 201, r.text
    fila = (db.query(m.ArchivoFreelance)
            .filter_by(nombre="Autorización – Henkel.pdf").first())
    assert fila is not None
    r = cliente.get(f"/freelance/archivos/{fila.id}", headers=rh)
    assert r.status_code == 200, r.text
    assert r.content == PDF
    assert "filename*=UTF-8''Autorizaci%C3%B3n" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"


# ============================== r7-03 y r7-05 · el reto de la huella

def test_el_reto_de_la_huella_no_vale_como_sesion(cliente, sesion):
    """El «estado» de la alta trae el usuario y va firmado con la misma
    clave que la sesion: mandado como sesion valia cinco minutos. Y el de
    la entrada, mandado como sesion, daba un 500 en vez de 401."""
    h = sesion("consultor")
    r = cliente.post("/auth/llaves/alta/opciones", json={"contrasena": "centauro2026"},
                     headers=h)
    assert r.status_code == 200, r.text
    estado_alta = r.json()["estado"]
    yo = cliente.get("/auth/yo", headers={"Authorization": f"Bearer {estado_alta}"})
    assert yo.status_code == 401, yo.text

    r = cliente.post("/auth/llaves/entrada/opciones", json={"correo": None})
    assert r.status_code == 200, r.text
    yo = cliente.get("/auth/yo",
                     headers={"Authorization": f"Bearer {r.json()['estado']}"})
    assert yo.status_code == 401, yo.text


def test_la_huella_queda_en_el_historial_del_acceso(cliente, sesion):
    """Activarla y quitarla se escriben en el historial del usuario,
    como el alta del acceso: la huella es una puerta mas."""
    tel = Telefono()
    h = sesion("consultor")
    yo = cliente.get("/auth/yo", headers=h).json()
    _activar(cliente, sesion, "consultor", tel, nombre="Chrome en el iPhone")
    historial = cliente.get(f"/auth/usuarios/{yo['usuario_id']}/historial",
                            headers=sesion("admin")).json()
    activadas = [f for f in historial if f["accion"] == "huella activada"]
    assert len(activadas) == 1
    assert activadas[0]["detalle"] == "Chrome en el iPhone"

    llaves = cliente.get("/auth/llaves", headers=h).json()
    assert len(llaves) == 1
    r = cliente.delete(f"/auth/llaves/{llaves[0]['id']}", headers=h)
    assert r.status_code in (200, 204), r.text
    historial = cliente.get(f"/auth/usuarios/{yo['usuario_id']}/historial",
                            headers=sesion("admin")).json()
    assert sorted(f["accion"] for f in historial
                  if f["accion"].startswith("huella")) == [
        "huella activada", "huella quitada"]

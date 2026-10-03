"""Los clientes de la Central y sus alertas (seccion 131).

Lo que se cuida: el evento le llega solo a quien sigue su estado; el
nivel decide por donde; una alerta por evento, persona y nivel; el nivel
4 sin acuse termina en una llamada de la central.
"""
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from app import alertas_riesgo
from app import models as m

AHORA = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
def cat(cliente, sesion, datos):
    c = cliente.get(f"/riesgo/catalogos?pais_id={datos['mx']['id']}",
                    headers=sesion("central")).json()
    return {"pais_id": datos["mx"]["id"],
            "regiones": {x["nombre"]: x["id"] for x in c["regiones"]},
            "tipos": {x["nombre"]: x["id"] for x in c["tipos"]}}


@pytest.fixture
def cliente_ci(cliente, sesion, datos, cat):
    """Un cliente que sigue Tamaulipas y Nuevo León, con su gerente."""
    h = sesion("diroperaciones")
    r = cliente.post("/riesgo/clientes", json={"cliente_id": datos["cliente_id"]},
                     headers=h)
    assert r.status_code == 200, r.text
    cc = r.json()
    r = cliente.put(f"/riesgo/clientes/{cc['id']}/zonas", json={
        "region_ids": [cat["regiones"]["Tamaulipas"],
                       cat["regiones"]["Nuevo León"]]}, headers=h)
    assert r.status_code == 200, r.text
    r = cliente.post(f"/riesgo/clientes/{cc['id']}/gente", json={
        "nombre": "Andrés", "apellidos": "Saucedo",
        "correo": "Andres.Saucedo@Cliente.com", "telefono": "+52 55 1234 5678",
        "perfil": "gerente"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def publicar(cliente, sesion, cat):
    def hacer(nivel=3, region="Tamaulipas", **cambios):
        cuerpo = {
            "pais_id": cat["pais_id"], "region_id": cat["regiones"][region],
            "tipo_id": cat["tipos"]["Bloqueo carretero"], "nivel": nivel,
            "titulo": "Bloqueo en la carretera Reynosa-Monterrey",
            "texto_cliente": "Bloqueo con vehículos en el km 40. Evite el "
                             "tramo y use la autopista de cuota.",
            "lat": 25.98, "lon": -98.6,
            "ocurrio_en": (AHORA - timedelta(minutes=10)).isoformat(),
            "vigente_hasta": (AHORA + timedelta(hours=8)).isoformat(),
        }
        cuerpo.update(cambios)
        e = cliente.post("/riesgo/eventos", json=cuerpo,
                         headers=sesion("central")).json()
        r = cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                         headers=sesion("central"))
        assert r.status_code == 200, r.text
        return r.json()
    return hacer


def _avisos(cliente, sesion, evento_id):
    return cliente.get(f"/riesgo/eventos/{evento_id}/avisos",
                       headers=sesion("central")).json()


def test_alta_del_cliente_y_su_gente(cliente, sesion, cliente_ci):
    assert [z["nombre"] for z in cliente_ci["zonas"]] == ["Nuevo León",
                                                         "Tamaulipas"]
    gente = cliente_ci["gente"][0]
    assert gente["correo"] == "andres.saucedo@cliente.com"
    assert gente["con_contrasena"] is False
    r = cliente.post(f"/riesgo/clientes/{cliente_ci['id']}/gente", json={
        "nombre": "Otro", "apellidos": "Igual",
        "correo": "andres.saucedo@cliente.com"},
        headers=sesion("diroperaciones"))
    assert r.status_code == 409


def test_la_central_no_da_de_alta_clientes(cliente, sesion, datos):
    r = cliente.post("/riesgo/clientes", json={"cliente_id": datos["cliente_id"]},
                     headers=sesion("central"))
    assert r.status_code == 403


def test_zonas_de_otro_pais_no(cliente, sesion, cliente_ci):
    paises = cliente.get("/catalogos/paises", headers=sesion("admin")).json()
    br = next(p for p in paises if p["codigo"] == "BR")
    sp = next(r for r in cliente.get(
        f"/riesgo/catalogos?pais_id={br['id']}",
        headers=sesion("central")).json()["regiones"] if r["clave"] == "SP")
    r = cliente.put(f"/riesgo/clientes/{cliente_ci['id']}/zonas",
                    json={"region_ids": [sp["id"]]},
                    headers=sesion("diroperaciones"))
    assert r.status_code == 400


def test_telefono_sin_clave_de_pais_no(cliente, sesion, cliente_ci):
    r = cliente.post(f"/riesgo/clientes/{cliente_ci['id']}/gente", json={
        "nombre": "Laura", "apellidos": "Díaz", "correo": "laura@cliente.com",
        "telefono": "55 1234 5678"}, headers=sesion("diroperaciones"))
    assert r.status_code == 400


def test_nivel_1_no_es_alerta(cliente, sesion, cliente_ci, publicar):
    e = publicar(nivel=1)
    assert _avisos(cliente, sesion, e["id"]) == []


def test_nivel_2_avisa_sin_correo_ni_acuse(cliente, sesion, cliente_ci,
                                           publicar):
    e = publicar(nivel=2)
    avisos = _avisos(cliente, sesion, e["id"])
    assert len(avisos) == 1
    assert avisos[0]["persona"] == "Andrés Saucedo"
    assert avisos[0]["correo_enviado"] is False
    assert avisos[0]["requiere_acuse"] is False
    bit = cliente.get(f"/riesgo/eventos/{e['id']}",
                      headers=sesion("central")).json()["bitacora"]
    assert bit[-1]["accion"] == "aviso"


def test_nivel_3_manda_correo_y_pide_acuse(cliente, sesion, cliente_ci,
                                           publicar):
    from app.db import SessionLocal
    e = publicar(nivel=3)
    avisos = _avisos(cliente, sesion, e["id"])
    assert avisos[0]["correo_enviado"] is True
    assert avisos[0]["requiere_acuse"] is True
    db = SessionLocal()
    try:
        aviso = (db.query(m.Notificacion)
                 .filter_by(destinatario=m.Destinatario.CLIENTE_CI).one())
        assert aviso.correo == "andres.saucedo@cliente.com"
        assert aviso.asunto.startswith("[Nivel 3 · Alto]")
        assert "km 40" in aviso.cuerpo
        assert "Tamaulipas" in aviso.datos
    finally:
        db.close()


def test_otra_zona_no_le_llega(cliente, sesion, cliente_ci, publicar):
    e = publicar(nivel=3, region="Jalisco")
    assert _avisos(cliente, sesion, e["id"]) == []


def test_cliente_o_persona_apagados_no_reciben(cliente, sesion, cliente_ci,
                                               publicar):
    h = sesion("diroperaciones")
    gente = cliente_ci["gente"][0]
    cliente.patch(f"/riesgo/clientes/{cliente_ci['id']}/gente/{gente['id']}",
                  json={"activo": False}, headers=h)
    e = publicar(nivel=3)
    assert _avisos(cliente, sesion, e["id"]) == []

    cliente.patch(f"/riesgo/clientes/{cliente_ci['id']}/gente/{gente['id']}",
                  json={"activo": True}, headers=h)
    cliente.patch(f"/riesgo/clientes/{cliente_ci['id']}",
                  json={"activo": False}, headers=h)
    e = publicar(nivel=3)
    assert _avisos(cliente, sesion, e["id"]) == []


def test_subir_de_nivel_es_otra_alerta_corregir_no(cliente, sesion,
                                                   cliente_ci, publicar):
    e = publicar(nivel=2)
    h = sesion("central")
    cliente.patch(f"/riesgo/eventos/{e['id']}",
                  json={"lugar": "Km 40, a la altura de Los Herreras"},
                  headers=h)
    assert len(_avisos(cliente, sesion, e["id"])) == 1
    cliente.patch(f"/riesgo/eventos/{e['id']}", json={"nivel": 3}, headers=h)
    avisos = _avisos(cliente, sesion, e["id"])
    assert [(a["nivel"], a["motivo"]) for a in avisos] == [(2, "nuevo"),
                                                          (3, "sube")]


def test_nivel_4_sin_acuse_la_central_llama(cliente, sesion, cliente_ci,
                                            publicar, cat):
    e = cliente.post("/riesgo/eventos", json={
        "pais_id": cat["pais_id"], "region_id": cat["regiones"]["Nuevo León"],
        "tipo_id": cat["tipos"]["Enfrentamiento armado"], "nivel": 4,
        "titulo": "Enfrentamiento en Cadereyta",
        "texto_cliente": "Enfrentamiento armado en Cadereyta. No circule "
                         "por la zona hasta nuevo aviso.",
        "ocurrio_en": AHORA.isoformat(),
        "vigente_hasta": (AHORA + timedelta(hours=4)).isoformat()},
        headers=sesion("central")).json()
    cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                 headers=sesion("central"))
    assert _avisos(cliente, sesion, e["id"]) == []      # espera al jefe
    cliente.post(f"/riesgo/eventos/{e['id']}/confirmar",
                 headers=sesion("diroperaciones"))
    avisos = _avisos(cliente, sesion, e["id"])
    assert avisos[0]["nivel"] == 4 and avisos[0]["llamar_desde"]

    antes = (AHORA + timedelta(minutes=5)).isoformat()
    despues = (datetime.now(timezone.utc) + timedelta(minutes=16)).isoformat()
    assert cliente.get("/riesgo/por-llamar", params={"ahora": antes},
                       headers=sesion("central")).json() == []
    lista = cliente.get("/riesgo/por-llamar", params={"ahora": despues},
                        headers=sesion("central")).json()
    assert [x["id"] for x in lista] == [avisos[0]["id"]]

    r = cliente.post(f"/riesgo/avisos/{avisos[0]['id']}/llamada",
                     json={"nota": "Contestó, ya sabía y está en su hotel"},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert cliente.get("/riesgo/por-llamar", params={"ahora": despues},
                       headers=sesion("central")).json() == []


def test_el_acuse_saca_de_la_lista_de_llamadas(cliente, sesion, cliente_ci,
                                               publicar):
    from app.db import SessionLocal
    e = publicar(nivel=4)          # pide confirmacion
    cliente.post(f"/riesgo/eventos/{e['id']}/confirmar",
                 headers=sesion("diroperaciones"))
    alerta_id = _avisos(cliente, sesion, e["id"])[0]["id"]
    db = SessionLocal()
    try:
        gente = db.query(m.UsuarioCliente).one()
        alertas_riesgo.acusar(db, gente, alerta_id)
        db.commit()
    finally:
        db.close()
    despues = (datetime.now(timezone.utc) + timedelta(minutes=16)).isoformat()
    assert cliente.get("/riesgo/por-llamar", params={"ahora": despues},
                       headers=sesion("central")).json() == []


def test_avisa_al_telefono(cliente, sesion, cliente_ci, publicar):
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        db.add(m.SuscripcionPushCliente(
            usuario_cliente_id=cliente_ci["gente"][0]["id"],
            endpoint="https://push.example/abc", p256dh="x", auth="y"))
        db.commit()
    finally:
        db.close()
    with mock.patch("app.push.hay_llaves", return_value=True), \
            mock.patch("pywebpush.webpush") as webpush:
        e = publicar(nivel=3)
    assert webpush.call_count == 1
    assert '"etiqueta": "evento-' in webpush.call_args.kwargs["data"]
    assert _avisos(cliente, sesion, e["id"])[0]["telefonos"] == 1


def test_el_resumen_del_dia_junta_el_nivel_2(cliente, sesion, cliente_ci,
                                             publicar):
    from app.db import SessionLocal
    publicar(nivel=2)
    publicar(nivel=2, titulo="Manifestación en el puente internacional")
    db = SessionLocal()
    try:
        # Las 19:30 de Mexico: todavia no.
        siete = datetime(2026, 10, 3, 1, 30, tzinfo=timezone.utc)
        ocho = datetime(2026, 10, 3, 2, 15, tzinfo=timezone.utc)
        for a in db.query(m.AlertaCliente).all():
            a.creada_en = siete - timedelta(hours=2)
        db.commit()
        assert alertas_riesgo.resumen_del_dia(db, siete) == {"resumenes": 0}
        assert alertas_riesgo.resumen_del_dia(db, ocho) == {"resumenes": 1}
        db.commit()
        assert alertas_riesgo.resumen_del_dia(db, ocho) == {"resumenes": 0}
        aviso = (db.query(m.Notificacion)
                 .filter_by(destinatario=m.Destinatario.CLIENTE_CI).one())
        assert aviso.asunto == "Resumen de riesgo del día · 2 evento(s)"
        assert "Manifestación" in aviso.datos
    finally:
        db.close()

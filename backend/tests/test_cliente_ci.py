"""La app del cliente de la Central (seccion 136).

Lo que se cuida: entra solo con su enlace y su contrasena; su sesion no
abre nada de Centauro ni la de Centauro abre la suya; ve solo lo
publicado en sus estados y lo que le llego a el, sin fuentes ni
bitacora; el «Enterado» queda en el evento y quita la llamada.
"""
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import cliente_ci as motor
from app import models as m
from app.config import settings
from app.db import SessionLocal
from tests.test_riesgo_clientes import cat, cliente_ci, publicar  # noqa: F401

CONTRASENA = "una frase que solo yo digo"


def _token_del_correo(plantilla="ci_invitacion"):
    db = SessionLocal()
    try:
        aviso = (db.query(m.Notificacion).filter_by(plantilla=plantilla)
                 .order_by(m.Notificacion.id.desc()).first())
        assert aviso is not None
        return aviso.enlace_seguimiento.rsplit("/", 1)[-1], aviso
    finally:
        db.close()


def _entrar(cliente, cliente_ci):  # noqa: F811
    token, _ = _token_del_correo()
    r = cliente.post("/ci-api/enlace/usar",
                     json={"token": token, "contrasena": CONTRASENA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_el_alta_manda_la_invitacion(cliente, cliente_ci):  # noqa: F811
    token, aviso = _token_del_correo()
    assert aviso.destinatario == m.Destinatario.CLIENTE_CI
    assert aviso.correo == "andres.saucedo@cliente.com"
    assert "/ci/#/enlace/" in aviso.enlace_seguimiento
    assert aviso.expira_en is not None
    # Del token solo se guarda la huella.
    db = SessionLocal()
    try:
        enlace = db.query(m.EnlaceCliente).one()
        assert enlace.huella != token and len(enlace.huella) == 64
    finally:
        db.close()
    assert cliente_ci["gente"][0]["invitacion_vence"]

    r = cliente.post("/ci-api/enlace", json={"token": token}).json()
    assert r["estado"] == "vivo" and r["nombre"] == "Andrés"
    assert cliente.post("/ci-api/enlace",
                        json={"token": "otro"}).json() == {"estado": "invalido"}


def test_el_correo_de_invitacion_lleva_su_boton(cliente, cliente_ci):  # noqa: F811
    _, aviso = _token_del_correo()
    db = SessionLocal()
    try:
        aviso = db.get(m.Notificacion, aviso.id)
        with mock.patch.object(settings, "url_publica",
                               "https://mycentauro.lat"):
            texto, html = motor.versiones(db, aviso)
    finally:
        db.close()
    assert "Crear mi contraseña" in html
    assert "https://mycentauro.lat/ci/#/enlace/" in texto
    assert "vence el" in texto


def test_poner_contrasena_y_entrar(cliente, cliente_ci):  # noqa: F811
    token, _ = _token_del_correo()
    r = cliente.post("/ci-api/enlace/usar",
                     json={"token": token, "contrasena": "centauro2026"})
    assert r.status_code == 400
    h = _entrar(cliente, cliente_ci)
    # El enlace ya no sirve.
    r = cliente.post("/ci-api/enlace/usar",
                     json={"token": token, "contrasena": CONTRASENA})
    assert r.status_code == 409
    yo = cliente.get("/ci-api/yo", headers=h).json()
    assert yo["cliente"] and yo["zonas"] == ["Nuevo León", "Tamaulipas"]
    # Y entra con el correo escrito como sea.
    r = cliente.post("/ci-api/entrar", json={
        "correo": " Andres.Saucedo@cliente.com", "contrasena": CONTRASENA})
    assert r.status_code == 200, r.text
    r = cliente.post("/ci-api/entrar", json={
        "correo": "andres.saucedo@cliente.com", "contrasena": "otra cosa"})
    assert r.status_code == 401


def test_las_sesiones_no_se_cruzan(cliente, sesion, cliente_ci):  # noqa: F811
    h = _entrar(cliente, cliente_ci)
    assert cliente.get("/riesgo/mapa", headers=h).status_code == 401
    assert cliente.get("/auth/yo", headers=h).status_code == 401
    assert cliente.get("/ci-api/yo",
                       headers=sesion("central")).status_code == 401


def test_cerrar_el_acceso_tira_la_sesion(cliente, sesion, cliente_ci):  # noqa: F811
    h = _entrar(cliente, cliente_ci)
    gente = cliente_ci["gente"][0]
    r = cliente.patch(f"/riesgo/clientes/{cliente_ci['id']}/gente/{gente['id']}",
                      json={"activo": False}, headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    assert cliente.get("/ci-api/yo", headers=h).status_code == 401
    r = cliente.post("/ci-api/entrar", json={
        "correo": "andres.saucedo@cliente.com", "contrasena": CONTRASENA})
    assert r.status_code == 403


def test_reenviar_la_invitacion_mata_la_anterior(cliente, sesion, cliente_ci):  # noqa: F811
    viejo, _ = _token_del_correo()
    gente = cliente_ci["gente"][0]
    r = cliente.post(f"/riesgo/clientes/{cliente_ci['id']}/gente/"
                     f"{gente['id']}/invitacion",
                     headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    nuevo, _ = _token_del_correo()
    assert nuevo != viejo
    assert cliente.post("/ci-api/enlace",
                        json={"token": viejo}).json()["estado"] == "anulado"
    assert cliente.post(f"/riesgo/clientes/{cliente_ci['id']}/gente/"
                        f"{gente['id']}/invitacion",
                        headers=sesion("central")).status_code == 403


def test_recuperar_contesta_igual(cliente, cliente_ci):  # noqa: F811
    _entrar(cliente, cliente_ci)
    a = cliente.post("/ci-api/recuperar",
                     json={"correo": "andres.saucedo@cliente.com"})
    b = cliente.post("/ci-api/recuperar", json={"correo": "nadie@x.com"})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    token, aviso = _token_del_correo("ci_recuperacion")
    assert aviso.correo == "andres.saucedo@cliente.com"
    r = cliente.post("/ci-api/enlace/usar",
                     json={"token": token, "contrasena": "otra frase larga"})
    assert r.status_code == 200, r.text


def test_cambiar_contrasena(cliente, cliente_ci):  # noqa: F811
    h = _entrar(cliente, cliente_ci)
    r = cliente.post("/ci-api/contrasena", headers=h,
                     json={"actual": "mal", "nueva": "otra frase larga"})
    assert r.status_code == 403
    r = cliente.post("/ci-api/contrasena", headers=h,
                     json={"actual": CONTRASENA, "nueva": "otra frase larga"})
    assert r.status_code == 200
    # La sesion vieja se cae; la nueva sirve.
    assert cliente.get("/ci-api/yo", headers=h).status_code == 401
    nuevo = {"Authorization": f"Bearer {r.json()['token']}"}
    assert cliente.get("/ci-api/yo", headers=nuevo).status_code == 200


def test_ve_solo_lo_de_sus_estados(cliente, sesion, cat, cliente_ci,  # noqa: F811
                                   publicar):
    h = _entrar(cliente, cliente_ci)
    suyo = publicar(nivel=2)
    ajeno = publicar(nivel=3, region="Jalisco", titulo="En Zapopan")
    mapa = cliente.get("/ci-api/mapa", headers=h).json()
    assert [e["id"] for e in mapa["eventos"]] == [suyo["id"]]
    e = mapa["eventos"][0]
    assert "fuentes" not in e and "motivo" not in e
    assert e["texto"].startswith("Bloqueo con vehículos")
    assert cliente.get(f"/ci-api/eventos/{ajeno['id']}",
                       headers=h).status_code == 404
    assert cliente.get(f"/ci-api/eventos/{suyo['id']}",
                       headers=h).status_code == 200
    # Lo que no se ha publicado no existe para el.
    borrador = cliente.post("/riesgo/eventos", json={
        "pais_id": cat["pais_id"], "region_id": suyo["region_id"],
        "tipo_id": suyo["tipo_id"], "nivel": 2, "titulo": "Borrador",
        "texto_cliente": "Todavía no", "ocurrio_en":
            datetime.now(timezone.utc).isoformat(),
        "vigente_hasta": (datetime.now(timezone.utc)
                          + timedelta(hours=2)).isoformat()},
        headers=sesion("central")).json()
    assert cliente.get(f"/ci-api/eventos/{borrador['id']}",
                       headers=h).status_code == 404


def test_enterado_quita_la_llamada(cliente, sesion, cliente_ci, publicar):  # noqa: F811
    h = _entrar(cliente, cliente_ci)
    e = publicar(nivel=3)
    avisos = cliente.get("/ci-api/avisos", headers=h).json()
    assert len(avisos["por_confirmar"]) == 1
    alerta = avisos["por_confirmar"][0]
    assert alerta["evento"]["id"] == e["id"]
    assert cliente.get(f"/ci-api/eventos/{e['id']}", headers=h
                       ).json()["alerta_por_confirmar"] == alerta["id"]
    r = cliente.post(f"/ci-api/avisos/{alerta['id']}/enterado", headers=h)
    assert r.status_code == 200, r.text
    avisos = cliente.get("/ci-api/avisos", headers=h).json()
    assert avisos["por_confirmar"] == []
    assert avisos["anteriores"][0]["acuse_en"]
    bitacora = cliente.get(f"/riesgo/eventos/{e['id']}",
                           headers=sesion("central")).json()["bitacora"]
    assert any(b["accion"] == "acuse" for b in bitacora)
    # La alerta de otro no se toca.
    assert cliente.post("/ci-api/avisos/99999/enterado",
                        headers=h).status_code == 404


def test_su_telefono(cliente, cliente_ci):  # noqa: F811
    h = _entrar(cliente, cliente_ci)
    r = cliente.post("/ci-api/push", headers=h, json={
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc", "p256dh": "x", "auth": "y"})
    assert r.status_code == 200
    # Una direccion que no es de un servicio de avisos no se guarda: el
    # servidor le escribiria a ella cada vez que se publica algo.
    for mala in ("http://fcm.googleapis.com/x", "https://api:8000/riesgo",
                 "https://169.254.169.254/latest", "https://fcm.googleapis.com.evil.io/x"):
        assert cliente.post("/ci-api/push", headers=h, json={
            "endpoint": mala, "p256dh": "x", "auth": "y"}).status_code == 400
    estado = cliente.get("/ci-api/push", headers=h,
                         params={"endpoint": "https://fcm.googleapis.com/fcm/send/abc"}).json()
    assert estado["este_telefono"] is True and estado["telefonos"] == 1
    assert cliente.delete("/ci-api/push", headers=h, params={
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc"}).status_code == 204
    assert cliente.get("/ci-api/push", headers=h).json()["telefonos"] == 0


def test_cambiar_idioma(cliente, cliente_ci):  # noqa: F811
    h = _entrar(cliente, cliente_ci)
    assert cliente.patch("/ci-api/yo", headers=h,
                         json={"idioma": "pt"}).json()["idioma"] == "pt"
    assert cliente.patch("/ci-api/yo", headers=h,
                         json={"idioma": "fr"}).status_code == 422


def test_cinco_telefonos_y_el_mas_viejo_sale(cliente, cliente_ci):  # noqa: F811
    h = _entrar(cliente, cliente_ci)
    for i in range(7):
        assert cliente.post("/ci-api/push", headers=h, json={
            "endpoint": f"https://web.push.apple.com/t{i}", "p256dh": "x",
            "auth": "y"}).status_code == 200
    assert cliente.get("/ci-api/push", headers=h).json()["telefonos"] == 5
    estado = cliente.get("/ci-api/push", headers=h, params={
        "endpoint": "https://web.push.apple.com/t6"}).json()
    assert estado["este_telefono"] is True


def test_cambiar_su_correo_mata_el_enlace_viejo(cliente, sesion, cliente_ci):  # noqa: F811
    viejo, _ = _token_del_correo()
    gente = cliente_ci["gente"][0]
    r = cliente.patch(f"/riesgo/clientes/{cliente_ci['id']}/gente/{gente['id']}",
                      json={"correo": "andres.bueno@cliente.com"},
                      headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    assert cliente.post("/ci-api/enlace",
                        json={"token": viejo}).json()["estado"] == "anulado"
    nuevo, aviso = _token_del_correo()
    assert aviso.correo == "andres.bueno@cliente.com"
    assert cliente.post("/ci-api/enlace",
                        json={"token": nuevo}).json()["estado"] == "vivo"


def test_el_olvido_sin_contrasena_manda_otra_invitacion(cliente, cliente_ci):  # noqa: F811
    cliente.post("/ci-api/recuperar",
                 json={"correo": "andres.saucedo@cliente.com"})
    db = SessionLocal()
    try:
        assert db.query(m.Notificacion).filter_by(
            plantilla="ci_recuperacion").count() == 0
        vivos = db.query(m.EnlaceCliente).filter(
            m.EnlaceCliente.anulado_en.is_(None)).all()
        assert [e.tipo for e in vivos] == ["invitacion"]
    finally:
        db.close()

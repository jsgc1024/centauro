# -*- coding: utf-8 -*-
"""Reportar una falla (seccion 92).

El ciclo que aprobo Salvador --«asi cerramos el ciclo»--: quien ve la
falla la reporta ahi mismo, desde la consola o desde la app; llega a los
casos como «por revisar» con lo que hace falta para entenderla; sistema y
calidad la resuelve o la copia para Claude; y ya resuelta, a quien la
reporto le llega el aviso.
"""
import pytest

from ayudas import crear_servicio, jornada, manana

# Un pixel, en PNG: la captura mas chica que se puede pegar.
PIXEL = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
         "FcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


@pytest.fixture
def avisos(monkeypatch):
    """Los avisos al telefono que salieron, sin salir de verdad."""
    from app import push

    salieron = []
    monkeypatch.setattr(push, "avisar", lambda db, persona_id, titulo, cuerpo,
                        **k: salieron.append((persona_id, titulo, k.get("url")))
                        or {"enviados": 1})
    return salieron


def _reportar(cliente, headers, que="Le di Dar visto bueno y salió en rojo "
              "«Hay puntos por corregir», pero no hay ninguno.", **extra):
    cuerpo = {"que_paso": que, **extra}
    return cliente.post("/manual/fallas", json=cuerpo, headers=headers)


def _casos(cliente, sesion):
    r = cliente.get("/manual/casos", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    return r.json()


def _correos(asunto_contiene):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [(n.correo, n.asunto, n.destinatario) for n in
                db.query(m.Notificacion).all() if asunto_contiene in n.asunto]


def test_desde_la_consola_llega_por_revisar_con_su_contexto(cliente, sesion,
                                                            datos, avisos):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(700), datos["modalidades"]["full_day"]["id"])])
    r = _reportar(cliente, h, esperaba="Que se fuera a finanzas.", contexto={
        "desde": "consola", "pantalla": "EP eventual", "ruta": f"#/servicio/{servicio['id']}",
        "servicio_id": servicio["id"], "navegador": "Mozilla/5.0 Chrome/141",
        "mensajes": [{"cuando": "2026-10-17T21:13:00Z", "texto":
                      "Hay puntos por corregir antes de enviar a finanzas",
                      "tono": "grave"}],
        "llamadas": [{"cuando": "2026-10-17T21:13:00Z", "metodo": "post",
                      "ruta": "/cierre/88/enviar-finanzas?token=no-debe-quedar",
                      "codigo": 409, "mensaje": "Hay puntos por corregir"}],
        "sesion": "esto no se guarda"})
    assert r.status_code == 201, r.text

    caso = _casos(cliente, sesion)[0]
    assert caso["estado"] == "por_revisar"
    assert caso["titulo"].startswith(f"{servicio['folio']} · Le di Dar visto bueno")
    assert caso["reportado_por"] == "Ana Solis"
    assert caso["esperaba"] == "Que se fuera a finanzas."
    c = caso["contexto"]
    assert c["servicio"]["folio"] == servicio["folio"]
    assert c["version"]["seccion"]
    # La ruta sin lo que va despues del ?, y lo que no esta en la lista
    # no se guarda.
    assert c["llamadas"][0]["ruta"] == "/cierre/88/enviar-finanzas"
    assert c["llamadas"][0]["metodo"] == "POST"
    assert "sesion" not in c and "no-debe-quedar" not in str(c)
    assert caso["tiene_captura"] is False
    # Sin nadie de sistema y calidad en esta base, le llega a administracion.
    assert _correos("Falla reportada")
    assert avisos and avisos[0][2] == "/consola/#/manual/casos"


def test_desde_la_app_con_foto_y_solo_la_ve_quien_revisa(cliente, sesion,
                                                         avisos):
    r = _reportar(cliente, sesion("juan"), "Ya estoy en el hotel y la app dice "
                  "que estoy lejos del punto.", captura=PIXEL,
                  contexto={"desde": "app", "app": "centauro-campo-v13",
                            "navegador": "Android 14"})
    assert r.status_code == 201, r.text
    caso_id = r.json()["id"]
    assert r.json()["titulo"].startswith("App de campo · Ya estoy en el hotel")

    caso = next(c for c in _casos(cliente, sesion) if c["id"] == caso_id)
    assert caso["tiene_captura"] and caso["contexto"]["desde"] == "app"
    imagen = cliente.get(f"/manual/casos/{caso_id}/captura",
                         headers=sesion("admin"))
    assert imagen.status_code == 200
    assert imagen.headers["content-type"] == "image/png"
    assert imagen.content.startswith(b"\x89PNG")
    # Quien reporta no lee los casos: eso es de sistema y calidad.
    assert cliente.get("/manual/casos", headers=sesion("juan")).status_code == 403
    assert cliente.get(f"/manual/casos/{caso_id}/captura",
                       headers=sesion("juan")).status_code == 403


@pytest.mark.parametrize("cuerpo", [
    {"que_paso": ""},
    {"que_paso": "no"},
    {"que_paso": "Algo falló", "captura": "data:text/html;base64,PGgxPg=="},
])
def test_lo_que_no_sirve_no_se_guarda(cliente, sesion, cuerpo, avisos):
    r = cliente.post("/manual/fallas", json=cuerpo, headers=sesion("consultor"))
    assert r.status_code == 422, r.text
    assert "mensaje" in r.json()["detail"]
    assert not [c for c in _casos(cliente, sesion) if c["estado"] != "resuelto"]


def test_sin_sesion_no_se_reporta(cliente):
    assert cliente.post("/manual/fallas",
                        json={"que_paso": "Algo falló"}).status_code == 401


def test_diez_por_hora_y_ya(cliente, sesion, avisos):
    h = sesion("consultor2")
    for i in range(10):
        assert _reportar(cliente, h, f"Falla número {i + 1}").status_code == 201
    r = _reportar(cliente, h, "La once")
    assert r.status_code == 429
    assert "central" in r.json()["detail"]["que_hacer"]


def test_copiar_para_claude(cliente, sesion, datos, avisos):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(705), datos["modalidades"]["full_day"]["id"])])
    caso_id = _reportar(cliente, h, "No sale el visto bueno.\nNi con recargar.",
                        captura=PIXEL, contexto={
                            "pantalla": "EP eventual", "ruta": "#/servicio/1",
                            "servicio_id": servicio["id"], "navegador": "Chrome 141",
                            "llamadas": [{"cuando": "2026-10-17T21:13:00Z",
                                          "metodo": "POST", "ruta": "/cierre/5/enviar-finanzas",
                                          "codigo": 409, "mensaje": "Hay puntos"}]}
                        ).json()["id"]

    r = cliente.post(f"/manual/casos/{caso_id}/para-claude", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    texto = r.json()["texto"]
    assert texto.startswith(f"Falla en Connect · caso {caso_id} · con Claude")
    for dice in (servicio["folio"], "Ana Solis", "Qué pasó:", "No sale el visto bueno.",
                 "Ni con recargar.", "POST /cierre/5/enviar-finanzas · 409",
                 "Versión:", f"en el caso {caso_id}"):
        assert dice in texto, dice
    # La captura no viaja en el texto.
    assert "base64" not in texto and "iVBOR" not in texto
    assert r.json()["caso"]["estado"] == "con_claude"
    assert r.json()["caso"]["con_claude_en"]
    # Quien reporta no copia nada para nadie.
    assert cliente.post(f"/manual/casos/{caso_id}/para-claude",
                        headers=h).status_code == 403


def test_el_folio_no_se_repite(cliente, sesion, datos, avisos):
    """En un servicio, el titulo de la pantalla es el folio: el texto para
    Claude lo dice una vez."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(706), datos["modalidades"]["full_day"]["id"])])
    caso_id = _reportar(cliente, h, "No sale.", contexto={
        "pantalla": servicio["folio"], "ruta": f"#/servicio/{servicio['id']}",
        "servicio_id": servicio["id"]}).json()["id"]
    texto = cliente.post(f"/manual/casos/{caso_id}/para-claude",
                         headers=sesion("admin")).json()["texto"]
    donde = next(r for r in texto.splitlines() if r.startswith("Dónde:"))
    assert donde.count(servicio["folio"]) == 1, donde
    assert f"#/servicio/{servicio['id']}" in donde


def test_resolver_avisa_a_quien_lo_reporto(cliente, sesion, avisos):
    caso_id = _reportar(cliente, sesion("juan"), "No me deja marcar la llegada.",
                        contexto={"desde": "app"}).json()["id"]
    admin = sesion("admin")

    sin_causa = cliente.post(f"/manual/casos/{caso_id}/resolver", headers=admin,
                             json={"solucion": "Se corrigió el punto.", "falla": "no"})
    assert sin_causa.status_code == 422

    r = cliente.post(f"/manual/casos/{caso_id}/resolver", headers=admin, json={
        "causa": "El punto de encuentro estaba capturado en otro hotel.",
        "solucion": "El consultor corrigió la dirección del punto.",
        "falla": "no", "area": "operacion",
        "titulo": "App de campo · El punto estaba en otro hotel"})
    assert r.status_code == 200, r.text
    caso = r.json()
    assert caso["estado"] == "resuelto" and caso["falla"] == "no"
    assert caso["resuelto_por"] and caso["resuelto_en"]
    assert caso["titulo"] == "App de campo · El punto estaba en otro hotel"

    # A Juan le llega por correo y al telefono, a su app.
    assert [c for c in _correos("La falla que reportaste") if c[0] ==
            "juan.ramirez@centauro.lat"]
    assert any(url == "/app/#/yo" for _, _, url in avisos)

    otra = cliente.post(f"/manual/casos/{caso_id}/resolver", headers=admin, json={
        "causa": "x", "solucion": "y", "falla": "no"})
    assert otra.status_code == 409


def test_la_version_la_ve_cualquiera_en_su_idioma(cliente, sesion):
    """La forma ensena con que actualizacion esta el sistema: la pide
    cualquiera que entra --tambien el de campo, que no lee el manual-- y
    llega en su idioma."""
    from app import manual

    r = cliente.get("/manual/version?idioma=pt", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert r.json() == manual.version("pt")
    assert r.json()["seccion"] == manual.version("es")["seccion"]
    assert cliente.get("/manual/version").status_code == 401


def test_los_abiertos_van_primero(cliente, sesion, avisos):
    admin = sesion("admin")
    anotado = cliente.post("/manual/casos", headers=admin, json={
        "titulo": "Se anotó a mano", "que_se_vio": "Algo", "causa": "Esto",
        "solucion": "Aquello", "falla": "no"}).json()
    assert anotado["estado"] == "resuelto"
    reportado = _reportar(cliente, sesion("consultor"), "Otra cosa falló").json()
    orden = [c["id"] for c in _casos(cliente, sesion)]
    assert orden.index(reportado["id"]) < orden.index(anotado["id"])

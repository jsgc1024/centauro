# -*- coding: utf-8 -*-
"""Los avisos del dia, al principal de cada equipo (seccion 91).

Un servicio puede traer varios equipos, y cada uno cuida a su principal:
el del equipo si lo trae, si no el del servicio. El task sheet ya lo
hacia asi. Los avisos del dia --el equipo llego, ya hubo contacto, las
horas extra, el relevo-- se iban siempre al principal del servicio: el
de Beta nunca sabia que su equipo ya lo esperaba abajo, y el de Alfa
recibia los de un equipo que no era el suyo.
"""
from datetime import datetime, timedelta

from ayudas import asignar, configurar_origen, jornada, manana, marcar


def _avisos_al_principal(servicio_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [(a.jornada_id, a.correo) for a in
                db.query(m.Notificacion).filter_by(
                    servicio_id=servicio_id,
                    destinatario=m.Destinatario.EJECUTIVO).all()]


def test_cada_equipo_avisa_a_su_principal(cliente, sesion, datos):
    h = sesion("consultor")
    dia = manana(610)
    full = datos["modalidades"]["full_day"]["id"]
    r = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
        "solicitante_correo": "solicitante@cliente.com",
        "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
        "ejecutivo_correo": "ejecutivo@cliente.com",
        "equipos": [
            {"jornadas": [jornada(dia, full)]},
            {"ejecutivo_nombre": "Lars", "ejecutivo_apellidos": "Berg",
             "ejecutivo_correo": "lars.berg@cliente.com",
             "jornadas": [jornada(dia, full)]},
        ]})
    assert r.status_code == 201, r.text
    servicio = r.json()
    alfa, beta = (e["jornadas"][0] for e in servicio["equipos"])

    otra_unidad = next(v for v in datos["vehiculos"]
                       if v["id"] != datos["suburban"]["id"]
                       and v["plaza_id"] == datos["cdmx"]["id"])
    for j, persona, unidad in ((alfa, "Juan Ramirez", datos["suburban"]["id"]),
                               (beta, "Luis Mendoza", otra_unidad["id"])):
        asignar(cliente, h, j["id"], persona_id=datos["personal"][persona]["id"],
                vehiculo_id=unidad)
        assert configurar_origen(cliente, h, j["id"]).status_code == 200

    for j, quien in ((alfa, "juan"), (beta, "luis")):
        inicio = datetime.fromisoformat(j["inicio_programado"])
        assert marcar(cliente, sesion(quien), j["id"], "llegada_origen",
                      inicio - timedelta(minutes=10)).status_code == 200
        assert marcar(cliente, sesion(quien), j["id"], "contacto_ejecutivo",
                      inicio).status_code == 200

    avisos = _avisos_al_principal(servicio["id"])
    de_alfa = {c for jid, c in avisos if jid == alfa["id"]}
    de_beta = {c for jid, c in avisos if jid == beta["id"]}
    # La llegada y el contacto de cada equipo.
    assert len([a for a in avisos if a[0] == beta["id"]]) == 2
    assert de_beta == {"lars.berg@cliente.com"}
    # El equipo sin principal propio sigue avisando al del servicio.
    assert de_alfa == {"ejecutivo@cliente.com"}

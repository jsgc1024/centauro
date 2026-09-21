# -*- coding: utf-8 -*-
"""En qué idioma sale cada correo.

Los diez avisos salían en español fijo mientras el task sheet del mismo
servicio salía en inglés: el ejecutivo extranjero recibía su hoja en su
idioma y dos horas después un correo que no entendía.

La regla es la que `textos.py` ya tenía escrita para el task sheet y que
Salvador confirmó el 20 de septiembre: **el principal arranca en inglés,
porque suele ser extranjero**. Y su otra mitad: **el solicitante lee en
el idioma del país donde se ejecuta**, porque quien pide el servicio casi
siempre es gente local.
"""
from ayudas import (asignar, configurar_origen, crear_servicio,
                    ejecutar_jornada, jornada, manana)


def _avisos(servicio_id, destinatario=None):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        q = db.query(m.Notificacion).filter_by(servicio_id=servicio_id)
        if destinatario:
            q = q.filter_by(destinatario=destinatario)
        return q.all()


def _dia_trabajado(cliente, sesion, datos, offset):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def test_el_alta_deja_al_principal_en_ingles_y_al_solicitante_en_su_pais(
        cliente, sesion, datos):
    from app import models as m
    from app.db import SessionLocal

    servicio, _ = _dia_trabajado(cliente, sesion, datos, 500)
    with SessionLocal() as db:
        guardado = db.get(m.Servicio, servicio["id"])
        assert guardado.idioma_ejecutivo == "en"
        # El servicio es de México: quien lo pidió lee español.
        assert guardado.idioma_solicitante == "es"


def test_cada_uno_recibe_su_aviso_en_su_idioma(cliente, sesion, datos):
    """El mismo hecho, dos correos distintos. No es el mismo mandado
    dos veces."""
    from app import models as m

    servicio, j = _dia_trabajado(cliente, sesion, datos, 520)
    ejecutar_jornada(cliente, sesion("juan"), j)

    al_principal = _avisos(servicio["id"], m.Destinatario.EJECUTIVO)
    al_solicitante = _avisos(servicio["id"], m.Destinatario.SOLICITANTE)

    llegada_en = next(a for a in al_principal if "on site" in a.asunto)
    assert "security team has arrived" in llegada_en.cuerpo
    # Y la ficha también: las claves, no los nombres.
    assert '"Team"' in (llegada_en.datos or "")

    llegada_es = next(a for a in al_solicitante
                      if "punto de origen" in a.asunto)
    assert "llegó al punto de origen" in llegada_es.cuerpo
    assert '"Equipo"' in (llegada_es.datos or "")


def test_el_cierre_del_dia_le_llega_al_solicitante_en_su_idioma(
        cliente, sesion, datos):
    from app import models as m

    servicio, j = _dia_trabajado(cliente, sesion, datos, 540)
    ejecutar_jornada(cliente, sesion("juan"), j, horas_extra=2)

    cierre = next(a for a in _avisos(servicio["id"], m.Destinatario.SOLICITANTE)
                  if "terminado" in a.asunto)
    assert "horas extra" in cierre.cuerpo
    assert cierre.idioma == "es"


def test_un_principal_que_lee_espanol_se_captura_y_manda_en_espanol(
        cliente, sesion, datos):
    """El caso contrario al normal: el ejecutivo es local. Un clic en el
    alta y sus correos salen en español."""
    from app import models as m

    h = sesion("consultor")
    r = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"],
        "pais_id": datos["mx"]["id"], "plaza_id": datos["cdmx"]["id"],
        "tipo": "eventual",
        "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
        "solicitante_correo": "solicitante@cliente.com",
        "ejecutivo_nombre": "Roberto", "ejecutivo_apellidos": "Sandoval",
        "ejecutivo_correo": "ejecutivo@cliente.com",
        "idioma_ejecutivo": "es",
        "equipos": [{"clave": "EQ-1", "jornadas": [
            jornada(manana(560), datos["modalidades"]["full_day"]["id"])]}],
    })
    assert r.status_code == 201, r.text
    servicio = r.json()
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("juan"), j)

    al_principal = _avisos(servicio["id"], m.Destinatario.EJECUTIVO)
    llegada = next(a for a in al_principal if "está en el lugar" in a.asunto)
    assert llegada.idioma == "es"
    assert "on site" not in llegada.asunto


def test_la_encuesta_sale_en_el_idioma_de_quien_la_contesta(
        cliente, sesion, datos):
    """Entraba "en" fijo y se equivocaba sola cada vez que el ejecutivo
    era mexicano."""
    from app import models as m
    from app.db import SessionLocal

    servicio, j = _dia_trabajado(cliente, sesion, datos, 580)
    ejecutar_jornada(cliente, sesion("juan"), j)

    r = cliente.post(f"/encuestas/servicio/{servicio['id']}/enviar",
                     headers=sesion("consultor"))
    assert r.status_code == 201, r.text

    with SessionLocal() as db:
        encuestas = (db.query(m.Encuesta)
                     .filter_by(servicio_id=servicio["id"]).all())
        por_tipo = {e.tipo: e.idioma for e in encuestas}
        assert por_tipo[m.TipoEncuesta.EJECUTIVO] == "en"
        assert por_tipo[m.TipoEncuesta.SOLICITANTE] == "es"


def test_el_implantado_tambien_captura_el_idioma(cliente, sesion, datos):
    """La pantalla del implantado tiene su propia alta. Sin esto, sus
    servicios quedaban con la omisión correcta pero sin forma de
    cambiarla."""
    from datetime import date

    from app import models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    r = cliente.post("/implantados", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        # Un principal que lee portugués: el caso que la omisión no cubre.
        "idioma_ejecutivo": "pt",
        "fecha_inicio": str(date.today().replace(day=1)),
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": datos["suburban"]["id"]}],
        "unidades": [datos["suburban"]["id"]],
        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000",
    })
    assert r.status_code == 201, r.text

    with SessionLocal() as db:
        servicio = db.get(m.Servicio, r.json()["servicio_id"])
        assert servicio.idioma_ejecutivo == "pt"
        # Y el solicitante, sin capturar, en el idioma de su país.
        assert servicio.idioma_solicitante == "es"

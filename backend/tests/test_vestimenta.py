# -*- coding: utf-8 -*-
"""El código de vestimenta del equipo.

Lo pone el consultor al dar de alta el servicio y lo leen tres: el
personal en la app --la noche anterior, que es cuando se decide qué
ponerse--, el cliente en el task sheet, y la central cuando alguien
pregunta.

Dos reglas que se prueban aquí porque son las que se rompen solas:
**solo aplica al eventual**, y **sin código la hoja no dice nada**. Un
servicio del que nadie acordó nada no es un servicio "casual".
"""
from ayudas import asignar, crear_servicio, jornada, manana


def _servicio(cliente, sesion, datos, vestimenta=None, dia=1,
              tipo="eventual"):
    h = sesion("consultor")
    extra = {"vestimenta": vestimenta} if vestimenta is not None else {}
    # Con direccion y pin: `configurar_origen` pone el pin pero no la
    # direccion, y sin ella el task sheet no se libera --y esta prueba
    # necesita imprimirlo--.
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(dia), datos["modalidades"]["full_day"]["id"],
                 origen_direccion="Las Alcobas, Polanco - lobby",
                 origen_lat="19.4284", origen_lon="-99.1957")],
        tipo=tipo, **extra)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    return servicio, j


def test_el_alta_guarda_el_codigo(cliente, sesion, datos):
    servicio, _ = _servicio(cliente, sesion, datos, "formal")
    assert servicio["vestimenta"] == "formal"


def test_sin_codigo_el_servicio_no_dice_nada(cliente, sesion, datos):
    """Vacío no es "casual": es que nadie lo acordó."""
    servicio, _ = _servicio(cliente, sesion, datos)
    assert servicio["vestimenta"] is None


def test_el_implantado_no_lleva_vestimenta(cliente, sesion, datos):
    """El implantado trabaja todos los días con el mismo cliente y eso se
    acuerda una vez, no servicio por servicio. Si entrara por el alta
    sería un dato que nadie va a mantener."""
    servicio, _ = _servicio(cliente, sesion, datos, "formal",
                            tipo="implantado")
    assert servicio["vestimenta"] is None

    r = cliente.put(f"/servicios/{servicio['id']}/vestimenta",
                    json={"vestimenta": "casual"}, headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "eventuales" in r.json()["detail"]["mensaje"]


def test_se_puede_cambiar_y_se_puede_quitar(cliente, sesion, datos):
    """El cliente cambia de idea --una cena que se vuelve junta de
    consejo-- y lo que no puede pasar es que el equipo se entere por
    teléfono mientras la hoja dice otra cosa."""
    h = sesion("consultor")
    servicio, _ = _servicio(cliente, sesion, datos, "casual")

    r = cliente.put(f"/servicios/{servicio['id']}/vestimenta",
                    json={"vestimenta": "formal"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["vestimenta"] == "formal"

    r = cliente.put(f"/servicios/{servicio['id']}/vestimenta",
                    json={"vestimenta": None}, headers=h)
    assert r.json()["vestimenta"] is None


def test_el_personal_la_ve_en_su_app(cliente, sesion, datos):
    """En la tarjeta de mañana, que es la que se mira la noche anterior."""
    _servicio(cliente, sesion, datos, "semiformal", dia=1)
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert dia["manana"][0]["vestimenta"] == "semiformal"


def test_la_hoja_lo_dice_en_el_idioma_del_cliente(cliente, sesion, datos):
    """El task sheet sale en el idioma del principal: el mismo código
    tiene que leerse en los dos."""
    h = sesion("consultor")
    servicio, _ = _servicio(cliente, sesion, datos, "semiformal")

    vista = cliente.get(
        f"/task-sheets/servicio/{servicio['id']}/vista-previa",
        headers=h).json()
    assert vista["vestimenta"] == "semiformal"

    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={"motivo": "prueba de vestimenta"}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion",
                 headers=h)

    es = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja?idioma=es",
                     headers=h)
    assert es.status_code == 200, es.text
    assert "Código de vestimenta: Semiformal" in es.text

    en = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja?idioma=en",
                     headers=h)
    assert "Dress code: Business casual" in en.text


def test_la_hoja_sin_codigo_no_lo_menciona(cliente, sesion, datos):
    """Una etiqueta vacía en la hoja del cliente es peor que no tenerla."""
    h = sesion("consultor")
    servicio, _ = _servicio(cliente, sesion, datos)
    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={"motivo": "prueba sin vestimenta"}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion",
                 headers=h)

    hoja = cliente.get(
        f"/task-sheets/servicio/{servicio['id']}/hoja?idioma=es", headers=h)
    assert "Código de vestimenta" not in hoja.text

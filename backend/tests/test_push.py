# -*- coding: utf-8 -*-
"""Los avisos al teléfono del equipo.

No había ni una prueba de esto, y por eso el recordatorio de la víspera
llevaba desde el primer día terminando en error: los avisos salían —el
guardado es la línea de antes— pero la tarea quedaba marcada como
fallida y nadie sabía a cuántos se había avisado.

Aquí no se prueba que el aviso llegue al teléfono —eso depende de Google
y de Apple, que aquí no existen—. Se prueba lo que sí es nuestro: a
quién se le manda, qué dice, y que un teléfono que ya no existe deje de
gastarnos la cola.
"""
from datetime import date

import pytest

from ayudas import asignar, crear_servicio, jornada, manana


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def salieron(monkeypatch):
    """Los avisos que se habrían mandado, sin salir a internet."""
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


def _telefono(db, persona_id, endpoint="https://push.example/abc"):
    from app import models as m
    fila = m.SuscripcionPush(persona_id=persona_id, endpoint=endpoint,
                             p256dh="clave-publica", auth="secreto")
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def test_el_recordatorio_de_la_vispera_no_revienta(db, salieron, datos):
    """El defecto que llevaba ahí desde el primer día: la tarea de las
    17:00 la llama sin fecha y terminaba en AttributeError."""
    from datetime import datetime

    from app import push

    # Sin argumentos, a la hora que sea: es como la llama el beat.
    assert "dias" in push.recordar_la_vispera(db)

    # Y parada a las cinco de la tarde, sale con el mañana de cada país.
    r = push.recordar_la_vispera(db, ahora=datetime(2026, 3, 10, 17, 0))
    assert isinstance(r["dias"], list) and r["dias"]
    # Mañana de cada país activo, no la de un país inventado.
    assert all(isinstance(d, str) for d in r["dias"])


def test_la_vispera_sale_a_las_cinco_de_cada_pais(db, salieron, datos):
    """El recordatorio se dispara con el reloj del país de operación.

    El calendario de Celery tiene un solo reloj, el del contenedor. Con
    el disparo fijo a las 17:00 de México, en São Paulo el aviso salía a
    las 19:00: dos horas menos de noche para que alguien consiga un
    relevo si el confirmado dice que no puede.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app import push

    en_brasil = push.recordar_la_vispera(db, ahora=datetime(
        2026, 3, 10, 17, 0, tzinfo=ZoneInfo("America/Sao_Paulo")))["paises"]
    assert "BR" in en_brasil, en_brasil
    assert "MX" not in en_brasil, "a México le faltan tres horas"

    en_mexico = push.recordar_la_vispera(db, ahora=datetime(
        2026, 3, 10, 17, 0, tzinfo=ZoneInfo("America/Mexico_City")))["paises"]
    assert "MX" in en_mexico, en_mexico
    assert "BR" not in en_mexico, "en Brasil ya son las ocho de la noche"

    # Y a media mañana no le toca a nadie.
    temprano = push.recordar_la_vispera(db, ahora=datetime(
        2026, 3, 10, 10, 0, tzinfo=ZoneInfo("America/Mexico_City")))
    assert temprano["paises"] == [] and temprano["avisados"] == []


def test_sin_llaves_no_se_manda_nada_y_se_dice(db, monkeypatch, datos):
    """Apagado a medias es peor que apagado."""
    from app import push

    monkeypatch.setattr(push.settings, "vapid_private", "")
    persona = datos["personal"]["Juan Ramirez"]["id"]
    r = push.avisar(db, persona, "Hola", "Cuerpo")
    assert r["enviados"] == 0
    assert "llaves" in r["motivo"]


def test_el_relevo_le_avisa_a_los_dos(cliente, sesion, datos, db, salieron):
    """Se le avisaba solo al que entra. El reemplazado se presentaba a
    las seis de la mañana a un servicio que ya no era suyo."""
    from app import push

    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    _telefono(db, juan, "https://push.example/juan")
    _telefono(db, luis, "https://push.example/luis")

    from app import models as m
    entra = db.get(m.Persona, luis)
    sale = db.get(m.Persona, juan)
    push.avisar_relevo(db, entra, sale,
                       {"jornadas_afectadas": [str(date.today())]})

    assert len(salieron) == 2, salieron
    cuerpos = " ".join(str(x["data"]) for x in salieron)
    assert "Entras a un servicio" in cuerpos
    assert "Ya no vas a este servicio" in cuerpos


def test_la_cancelacion_le_avisa_a_quien_iba(cliente, sesion, datos, db,
                                             salieron):
    """Sin esto la cancelación se quedaba entre el consultor y el
    sistema."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(700), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan)
    _telefono(db, juan, "https://push.example/cancelacion")

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "El cliente ya no viaja"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["avisados"] == 1

    assert len(salieron) == 1, salieron
    assert "ya no va" in str(salieron[0]["data"])


def test_al_asignar_un_servicio_de_hoy_se_avisa_en_el_momento(
        cliente, sesion, datos, db, salieron):
    """El aviso de la víspera lo manda el reloj la noche anterior, así
    que a un servicio de hoy para hoy no le toca nunca. La persona se
    enteraba porque le hablaban por teléfono, o no se enteraba."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _telefono(db, juan, "https://push.example/hoy")

    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(date.today(), datos["modalidades"]["full_day"]["id"],
                 hora="23:30:00")])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)

    assert len(salieron) == 1, salieron
    dicho = str(salieron[0]["data"])
    assert "Trabajas hoy" in dicho
    assert servicio["folio"] in dicho


def test_lo_de_manana_armado_despues_de_las_cinco_tambien_avisa(
        cliente, sesion, datos, db, salieron, monkeypatch):
    """El mismo hueco, corrido un día.

    El recordatorio de la víspera corre a las cinco de la tarde. Quien
    se asigna a las ocho de la noche para mañana a las seis de la
    mañana tampoco recibe nada: su víspera ya pasó. Aquí se adelanta la
    hora del recordatorio para que cualquier momento del día cuente
    como "ya corrió".
    """
    from app import push

    monkeypatch.setattr(push, "HORA_DEL_RECORDATORIO", 0)
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _telefono(db, juan, "https://push.example/manana")

    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(1), datos["modalidades"]["full_day"]["id"],
                 hora="06:00:00")])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)

    assert len(salieron) == 1, salieron
    assert "Trabajas manana" in str(salieron[0]["data"])


def test_al_asignar_un_servicio_de_otro_dia_no_se_avisa_todavia(
        cliente, sesion, datos, db, salieron):
    """Ese es el trabajo del recordatorio de la víspera. Avisar dos
    veces por lo mismo enseña a ignorar los avisos."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _telefono(db, juan, "https://push.example/otro-dia")

    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(710), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)

    assert salieron == []


def test_un_telefono_que_ya_no_existe_se_apaga(db, salieron, datos,
                                               monkeypatch):
    """Y el apagado se guarda: se llamaba después del commit y se perdía,
    así que se le seguía mandando a un teléfono desinstalado."""
    import pywebpush
    from app import models as m, push

    persona = datos["personal"]["Juan Ramirez"]["id"]
    fila = _telefono(db, persona, "https://push.example/muerto")

    class Respuesta:
        status_code = 410

    def desaparecido(**kwargs):
        raise pywebpush.WebPushException("se fue", response=Respuesta())

    monkeypatch.setattr(pywebpush, "webpush", desaparecido)

    r = push.avisar(db, persona, "Hola", "Cuerpo")
    db.commit()

    assert r["enviados"] == 0
    assert r["apagadas"] == 1
    db.refresh(fila)
    assert fila.activa is False
    # Y ya no se le vuelve a intentar.
    assert push.suscripciones(db, persona) == []


def test_el_recordatorio_dura_hasta_la_manana_y_trae_su_boton(db, salieron,
                                                              datos):
    """A las 17:00 con una hora de vida, el teléfono guardado en el
    bolsillo hasta la mañana no recibía nada: justo el caso que este
    aviso existe para cubrir.

    Y el botón en la propia notificación ahorra cuatro toques a las seis
    de la mañana: desbloquear, abrir, buscar el servicio, confirmar.
    """
    from app import push

    persona = datos["personal"]["Juan Ramirez"]["id"]
    _telefono(db, persona, "https://push.example/vispera")

    push.avisar(db, persona, "Confirma que vas mañana", "A las 05:00",
                etiqueta="vispera", horas=push.HORAS_DE_ESPERA_VISPERA,
                accion="confirmar")

    assert len(salieron) == 1, salieron
    assert salieron[0]["ttl"] == push.HORAS_DE_ESPERA_VISPERA * 3600
    assert '"accion": "confirmar"' in salieron[0]["data"]


def test_lo_urgente_sale_marcado_como_urgente(db, salieron, datos):
    """Un relevo de hoy para hoy no puede esperar a que alguien mueva el
    teléfono."""
    from app import push

    persona = datos["personal"]["Juan Ramirez"]["id"]
    _telefono(db, persona, "https://push.example/urgente")

    push.avisar(db, persona, "Entras a un servicio", "Hoy", urgente=True)
    push.avisar(db, persona, "Se te vence un curso", "En 15 dias")

    assert salieron[0]["headers"]["Urgency"] == "high"
    assert salieron[1]["headers"]["Urgency"] == "normal"


# ==================================================================
# El dinero: los dos avisos que la central contestaba por teléfono
# ==================================================================

def _archivo_png():
    import base64
    import io as _io
    pixel = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGA"
        "hKmMIQAAAABJRU5ErkJggg==")
    return {"archivo": ("comprobante.png", _io.BytesIO(pixel), "image/png")}


def _viatico_solicitado(cliente, sesion, datos, monto="900"):
    """Un día con viáticos asignados y ya pedidos a finanzas."""
    from ayudas import configurar_origen

    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(710), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    viatico = cliente.post(
        "/viaticos/asignar", headers=h,
        json={"jornada_id": j["id"], "persona_id": juan,
              "conceptos": [{"concepto": "alimentos", "monto": monto,
                             "origen": "tabulador"}]}).json()
    cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                 headers=h)
    return servicio, viatico, juan


def test_el_deposito_le_avisa_a_quien_lo_recibe(cliente, sesion, datos, db,
                                                salieron):
    """"¿Ya me depositaron?" es la pregunta que más recibe la central, y
    la única forma de contestarla era que alguien mirara la bandeja."""
    servicio, _, juan = _viatico_solicitado(cliente, sesion, datos)
    _telefono(db, juan, "https://push.example/deposito")

    equipo_id = servicio["equipos"][0]["id"]
    r = cliente.post(
        "/viaticos/finanzas/depositar",
        data={"equipo_id": str(equipo_id), "persona_id": str(juan),
              "referencia": "SPEI-4471002839"},
        files=_archivo_png(), headers=sesion("finanzas"))
    assert r.status_code == 200, r.text

    cuerpos = " ".join(str(x["data"]) for x in salieron)
    assert "Ya te depositaron" in cuerpos
    # La referencia del banco va en el aviso: es lo que sirve para
    # reclamar si el banco no lo abonó.
    assert "SPEI-4471002839" in cuerpos


def test_el_comprobante_rechazado_le_avisa_con_el_motivo(cliente, sesion,
                                                         datos, db, salieron):
    """Sin esto se enteraba cuando veía el descuento en su pago. Y casi
    siempre lo que pasó es que el ticket salió borroso."""
    _, viatico, juan = _viatico_solicitado(cliente, sesion, datos)
    _telefono(db, juan, "https://push.example/comprobante")

    subido = cliente.post(
        f"/viaticos/{viatico['id']}/comprobantes", headers=sesion("juan"),
        json={"concepto": "alimentos", "tipo": "nota", "monto": "340",
              "archivo_url": "data:image/png;base64,AAAA"})
    assert subido.status_code in (200, 201), subido.text
    comprobante_id = subido.json()["comprobantes"][-1]["id"]

    salieron.clear()
    r = cliente.post(
        f"/viaticos/{viatico['id']}/rechazar-comprobante/{comprobante_id}"
        f"?motivo=La%20foto%20no%20se%20alcanza%20a%20leer",
        headers=sesion("consultor"))
    assert r.status_code == 200, r.text

    cuerpos = " ".join(str(x["data"]) for x in salieron)
    assert "rechazaron un comprobante" in cuerpos
    # El motivo tal cual: un rechazo sin razón no se puede corregir,
    # solo se puede discutir.
    assert "no se alcanza a leer" in cuerpos
    # Y lo que le falta por comprobar, que es lo que se le va a descontar.
    assert "por comprobar" in cuerpos


def test_un_aviso_que_falla_no_tumba_el_deposito(cliente, sesion, datos, db,
                                                 monkeypatch, salieron):
    """El dinero ya salió del banco. Que no se pueda avisar es un
    problema; perder el registro del depósito es otro mucho peor."""
    from app import push

    servicio, _, juan = _viatico_solicitado(cliente, sesion, datos)
    _telefono(db, juan, "https://push.example/revienta")

    def truena(*_a, **_k):
        raise RuntimeError("el servicio de avisos no contesta")

    monkeypatch.setattr(push, "avisar_deposito", truena)

    r = cliente.post(
        "/viaticos/finanzas/depositar",
        data={"equipo_id": str(servicio["equipos"][0]["id"]),
              "persona_id": str(juan), "referencia": "SPEI-000111"},
        files=_archivo_png(), headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["deposito_id"]

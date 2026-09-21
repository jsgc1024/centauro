# -*- coding: utf-8 -*-
"""La carrera entre el consultor y el banco.

El consultor cancela el depósito y, mientras tanto, finanzas ya fue al
banco. Vuelve con su referencia y su comprobante, los sube, y el sistema
le contestaba **404**: el dinero ya había salido y no había dónde
registrarlo. Lo que no se puede registrar se arregla por fuera, y lo que
se arregla por fuera no se audita.

Tres candados, en orden de qué tan seguido pasan:

1. **No se borra nada con dinero en camino.** Antes el servicio se
   borraba, las solicitudes se iban de la base, y a finanzas no le
   avisaba nadie.
2. **Lo que ya está con finanzas, el consultor no lo cancela solo.** El
   único que sabe si el dinero salió del banco es quien lo manda.
3. **La puerta de atrás.** Si aun así el depósito llega tarde, se
   acepta y queda marcado.
"""
import base64
import io as _io

from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana

PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg==")


def _archivo():
    return {"archivo": ("comprobante.png", _io.BytesIO(PIXEL), "image/png")}


def _servicio_con_deposito_pedido(cliente, sesion, datos, dias=1):
    """Un servicio con viáticos asignados y ya solicitados a finanzas."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        # Mañana, no dentro de un año: el barrido solo manda al banco
        # lo que entra en su ventana --el día previo al servicio--, y
        # sin eso no hay forma de probar lo que ya está con finanzas.
        [jornada(manana(1 + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    juan = datos["personal"]["Juan Ramirez"]["id"]
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"], persona_id=juan,
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
        viatico = cliente.post(
            "/viaticos/asignar", headers=h,
            json={"jornada_id": j["id"], "persona_id": juan,
                  "conceptos": [{"concepto": "alimentos", "monto": "900",
                                 "origen": "tabulador"}]}).json()
        cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                     headers=h)
    return servicio, servicio["equipos"][0]["id"], juan


def _enviar_al_banco(cliente, sesion):
    """El barrido: lo que ya salió de la casa y está en manos de finanzas."""
    return cliente.post("/viaticos/transferencias/barrido",
                        headers=sesion("finanzas"))


def _depositar(cliente, sesion, equipo_id, persona_id,
               referencia="SPEI-9080706"):
    return cliente.post(
        "/viaticos/finanzas/depositar",
        data={"equipo_id": str(equipo_id), "persona_id": str(persona_id),
              "referencia": referencia},
        files=_archivo(), headers=sesion("finanzas"))


def _panel(cliente, sesion, equipo_id):
    return cliente.get(f"/viaticos/equipos/{equipo_id}",
                       headers=sesion("consultor")).json()


# =================================== 1 · no se borra con dinero en camino

def test_no_se_borra_un_servicio_con_deposito_en_camino(cliente, sesion, datos):
    """Antes se borraba: las solicitudes se iban de la base y quien
    borraba se llevaba un número en la respuesta que no lee nadie. Si
    finanzas ya había ido al banco, ese depósito quedaba fuera del
    sistema para siempre."""
    h = sesion("consultor")
    servicio, equipo_id, _ = _servicio_con_deposito_pedido(cliente, sesion,
                                                           datos)
    r = cliente.delete(f"/servicios/{servicio['id']}", headers=h)
    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert "en camino" in detalle["mensaje"]
    assert "viaticos" in detalle["que_hacer"]

    # Y una vez cancelado el depósito, sí se borra.
    cliente.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
                 json={}, headers=h)
    assert cliente.delete(f"/servicios/{servicio['id']}",
                          headers=h).status_code == 200


# ============================ 2 · lo que ya está con finanzas no lo cancela él

def test_lo_que_ya_esta_con_finanzas_queda_pedido_no_cancelado(
        cliente, sesion, datos):
    """El único que sabe si el dinero ya salió del banco es quien lo
    manda. Cancelarlo aquí dejaría una transferencia hecha sin registro."""
    h = sesion("consultor")
    servicio, equipo_id, juan = _servicio_con_deposito_pedido(cliente, sesion,
                                                              datos)
    _enviar_al_banco(cliente, sesion)

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
                     json={}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["pedidos_a_finanzas"] == 1
    assert r.json()["cancelados"] == 0
    # No se canceló: el dinero sigue contando como en camino.
    assert float(r.json()["total_en_camino"]) > 0

    # Finanzas lo ve en su bandeja antes de ir al banco.
    bandeja = cliente.get("/viaticos/finanzas/bandeja",
                          headers=sesion("finanzas")).json()
    filas = [f for p in bandeja["paises"] for f in p["depositos"]
             if f["folio"] == servicio["folio"]]
    assert filas and filas[0]["cancelacion_pedida"] is True

    # Y lo cierra finanzas, no el consultor.
    cierre = cliente.post(
        f"/viaticos/finanzas/transferencias/cancelar"
        f"?equipo_id={equipo_id}&persona_id={juan}",
        headers=sesion("finanzas"))
    assert cierre.status_code == 200, cierre.text
    assert float(_panel(cliente, sesion, equipo_id)["total_en_camino"]) == 0


def test_el_consultor_no_puede_cerrar_la_cancelacion_el_mismo(cliente, sesion,
                                                              datos):
    _, equipo_id, juan = _servicio_con_deposito_pedido(cliente, sesion, datos)
    _enviar_al_banco(cliente, sesion)
    r = cliente.post(
        f"/viaticos/finanzas/transferencias/cancelar"
        f"?equipo_id={equipo_id}&persona_id={juan}",
        headers=sesion("consultor"))
    assert r.status_code == 403, r.text


def test_finanzas_no_cancela_lo_que_nadie_pidio(cliente, sesion, datos):
    _, equipo_id, juan = _servicio_con_deposito_pedido(cliente, sesion, datos)
    _enviar_al_banco(cliente, sesion)
    r = cliente.post(
        f"/viaticos/finanzas/transferencias/cancelar"
        f"?equipo_id={equipo_id}&persona_id={juan}",
        headers=sesion("finanzas"))
    assert r.status_code == 409, r.text


# ========================================== 3 · la puerta de atrás

def test_el_deposito_que_llega_tarde_se_registra_y_queda_marcado(
        cliente, sesion, datos):
    """El caso que traía todo esto: el consultor canceló mientras
    finanzas estaba en el banco. El dinero salió, y un depósito real
    siempre tiene dónde registrarse."""
    h = sesion("consultor")
    _, equipo_id, juan = _servicio_con_deposito_pedido(cliente, sesion, datos)

    # Se cancela cuando todavía no había salido de la casa.
    cancelado = cliente.post(
        f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
        json={}, headers=h)
    assert cancelado.json()["cancelados"] == 1

    # Pero finanzas ya había transferido y sube su comprobante.
    r = _depositar(cliente, sesion, equipo_id, juan)
    assert r.status_code == 200, r.text
    assert r.json()["sobre_cancelada"] is True
    assert "devolucion" in r.json()["nota"]

    # Y el consultor lo ve: es dinero que hay que aplicar o pedir de vuelta.
    panel = _panel(cliente, sesion, equipo_id)
    assert float(panel["total_tras_cancelar"]) > 0
    suyo = next(f for f in panel["personal"] if f["persona_id"] == juan)
    assert float(suyo["depositado_tras_cancelar"]) > 0


def test_el_deposito_normal_no_queda_marcado(cliente, sesion, datos):
    """La marca tiene que significar algo: si saliera en todos, no."""
    _, equipo_id, juan = _servicio_con_deposito_pedido(cliente, sesion, datos)
    r = _depositar(cliente, sesion, equipo_id, juan)
    assert r.status_code == 200, r.text
    assert r.json()["sobre_cancelada"] is False
    assert float(_panel(cliente, sesion, equipo_id)["total_tras_cancelar"]) == 0


def test_no_se_paga_dos_veces_la_misma_cancelada(cliente, sesion, datos):
    """La puerta de atrás no puede volverse una forma de pagar doble."""
    h = sesion("consultor")
    _, equipo_id, juan = _servicio_con_deposito_pedido(cliente, sesion, datos)
    cliente.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
                 json={}, headers=h)
    assert _depositar(cliente, sesion, equipo_id, juan).status_code == 200

    otra = _depositar(cliente, sesion, equipo_id, juan, referencia="SPEI-2")
    assert otra.status_code == 404, otra.text

"""Lo que queda pendiente cuando una unidad cambia de manos.

El motor lo calcula desde hace meses —`revision_pendiente`: falta
entregar la que sale, falta recibir la que entra— y lo devuelve en la
respuesta del cambio, del regreso y del taller. **Ninguna pantalla lo
pintaba**, así que el consultor hacía el cambio, el sistema le contestaba
qué faltaba, y él nunca lo veía.

Hoy no se pierde: el candado del fin de servicio no deja soltar una
unidad sin entregar. Lo que se perdía era encargarlo **en el momento**,
que es cuando la gente todavía está junto a las dos camionetas.

Estas pruebas cuidan el contrato del que ahora depende la pantalla, y que
hasta hoy no vigilaba nadie. Lo delicado no es que el campo exista: es
que diga la verdad en los dos casos que se confunden —la unidad que rodó
y la que nunca salió—.
"""
from datetime import date, timedelta

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana, revisar_unidad)
from tests.test_mes_siguiente import _alta


def _otra(datos, distinta_de):
    return next(v for v in datos["vehiculos"]
                if v["id"] != distinta_de
                and v["plaza_id"] == datos["suburban"]["plaza_id"])


def _un_dia_habil(desde):
    dia = desde
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia


def _servicio(cliente, sesion, datos, dias=2):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(i), datos["modalidades"]["full_day"]["id"])
        for i in range(dias)])
    for j in servicio["equipos"][0]["jornadas"]:
        for r in asignar(cliente, h, j["id"],
                         persona_id=datos["personal"]["Juan Ramirez"]["id"],
                         vehiculo_id=datos["suburban"]["id"]):
            assert r.status_code == 200, r.text
        configurar_origen(cliente, h, j["id"])
    return servicio


def _relevar(cliente, sesion, servicio, datos, desde_jornada):
    otra = _otra(datos, datos["suburban"]["id"])
    r = cliente.post("/contingencia/reemplazos/vehiculo",
                     headers=sesion("consultor"), json={
                         "desde_jornada_id": desde_jornada["id"],
                         "sale_vehiculo_id": datos["suburban"]["id"],
                         "entra_vehiculo_id": otra["id"],
                         "motivo": "Se quedo en el camino"})
    assert r.status_code in (200, 201), r.text
    return r.json(), otra


# ================================================== el relevo de unidad

def test_la_que_rodo_hay_que_entregarla_y_la_que_entra_recibirla(
        cliente, sesion, datos):
    """El caso completo: la camioneta salió a la calle y se cambia a
    media operación. Las dos puntas quedan abiertas."""
    servicio = _servicio(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]

    # Juan la recibió: ya cambió de manos una vez.
    assert revisar_unidad(cliente, sesion("juan"), servicio["id"],
                          datos["suburban"]["id"], "recibe",
                          42_000).status_code == 201

    hecho, _ = _relevar(cliente, sesion, servicio, datos, jornadas[1])
    pendiente = hecho["revision_pendiente"]
    assert pendiente["entrega_de_la_que_sale"] is True
    assert pendiente["recepcion_de_la_que_entra"] is True


def test_la_que_nunca_salio_no_se_entrega(cliente, sesion, datos):
    """Si nadie la recibió, no rodó: cambiarla es corregir un nombre en
    una lista, no un cambio de manos. Pedir su entrega sería mandar a
    alguien a fotografiar una camioneta que nunca tocó —y es la forma más
    rápida de que el aviso deje de significar algo."""
    servicio = _servicio(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]

    hecho, _ = _relevar(cliente, sesion, servicio, datos, jornadas[1])
    pendiente = hecho["revision_pendiente"]
    assert pendiente["entrega_de_la_que_sale"] is False
    # La que entra sí: va a andar en la calle.
    assert pendiente["recepcion_de_la_que_entra"] is True


def test_lo_ya_hecho_deja_de_pedirse(cliente, sesion, datos):
    """El aviso tiene que apagarse solo. Uno que sigue ahí después de
    resolverlo enseña a ignorarlo."""
    servicio = _servicio(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("juan")

    revisar_unidad(cliente, h, servicio["id"], datos["suburban"]["id"],
                   "recibe", 42_000)
    revisar_unidad(cliente, h, servicio["id"], datos["suburban"]["id"],
                   "entrega", 42_200)

    hecho, _ = _relevar(cliente, sesion, servicio, datos, jornadas[1])
    pendiente = hecho["revision_pendiente"]
    assert pendiente["entrega_de_la_que_sale"] is False
    # La que entra sigue pendiente: esa todavía nadie la ha recibido.
    assert pendiente["recepcion_de_la_que_entra"] is True


# ========================================================== el taller

def test_el_taller_tambien_lo_dice(cliente, sesion, datos):
    """Es la misma puerta por dentro —`cambiar_recurso`— y la pantalla
    del implantado ahora lo pinta. Si el campo se perdiera en el camino,
    el consultor volvería a no enterarse."""
    hoy = date.today()
    alta, h = _alta(cliente, sesion, datos, inicio=hoy.replace(day=1))
    entra = _otra(datos, datos["suburban"]["id"])
    desde = _un_dia_habil(max(hoy, hoy.replace(day=1)))

    r = cliente.post(f"/implantados/{alta['servicio_id']}/taller", json={
        "desde": str(desde), "tipo": "mantenimiento_correctivo",
        "entra_id": entra["id"]}, headers=h)
    assert r.status_code == 200, r.text
    assert "revision_pendiente" in r.json(), r.json().keys()
    assert r.json()["revision_pendiente"][
        "recepcion_de_la_que_entra"] is True

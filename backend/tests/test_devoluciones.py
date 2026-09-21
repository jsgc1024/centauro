# -*- coding: utf-8 -*-
"""El dinero que regresa.

Existía un endpoint que sumaba al devuelto y nada más: sin evidencia,
sin quién lo registró, con el monto viajando en la dirección, y sin un
solo botón en ninguna pantalla que lo llamara. Se podía deber dinero y
no tener manera de devolverlo.

Ahora es la transferencia al revés, con la misma regla que el depósito:
la persona transfiere y declara, finanzas confirma cuando lo ve entrar.
Lo que se prueba aquí es que **declarada no es confirmada** —el mismo
defecto que tenía la app cuando decía "te depositaron" con dinero que
seguía en el banco, del otro lado del mostrador—.
"""
from decimal import Decimal

from ayudas import depositar_de_verdad, devolver


def _viatico_con_dinero(cliente, sesion, datos, dias=800, monto="1500"):
    """Un viático depositado de verdad: si no, no hay qué devolver."""
    from ayudas import asignar, crear_servicio, jornada, manana

    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(dias), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)
    equipo_id = servicio["equipos"][0]["id"]
    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": juan, "monto": monto}, headers=h)
    depositar_de_verdad(cliente, sesion, equipo_id, juan)

    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    fila = next(s for s in mios["servicios"]
                if s["folio"] == servicio["folio"])
    return servicio, fila, fila["dias"][0]["viatico_id"], juan


def _mio(cliente, sesion, servicio):
    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    return next(s for s in mios["servicios"]
                if s["folio"] == servicio["folio"])


def test_lo_declarado_no_baja_lo_que_falta_comprobar(cliente, sesion, datos):
    """El corazón de todo esto.

    Si lo declarado contara de una vez, la deuda de la persona se
    apagaría sola —y con ella el plazo de las 24 horas— por un dinero
    que la empresa todavía no ha visto entrar.
    """
    servicio, fila, viatico_id, _juan = _viatico_con_dinero(
        cliente, sesion, datos)
    antes = fila["por_comprobar"]
    assert antes > 0

    r = cliente.post(f"/campo/viaticos/{viatico_id}/devolucion",
                     json={"monto": "500", "referencia": "SPEI-77"},
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "declarada"

    ahora = _mio(cliente, sesion, servicio)
    assert ahora["por_comprobar"] == antes, "se le apagó la deuda sin dinero"
    # Pero se le dice, con su nombre y aparte.
    assert Decimal(str(ahora["devolucion_en_revision"])) == Decimal("500")


def test_cuando_finanzas_la_confirma_entonces_si_baja(cliente, sesion, datos):
    """Y ahí sí: el dinero volvió."""
    servicio, fila, viatico_id, _juan = _viatico_con_dinero(
        cliente, sesion, datos, dias=801)
    antes = Decimal(str(fila["por_comprobar"]))

    r = cliente.post(f"/campo/viaticos/{viatico_id}/devolucion",
                     json={"monto": "500"}, headers=sesion("juan"))
    devolucion_id = r.json()["devolucion_id"]

    r = cliente.post(f"/viaticos/devoluciones/{devolucion_id}/confirmar",
                     headers=sesion("finanzas"))
    assert r.status_code == 200, r.text

    ahora = _mio(cliente, sesion, servicio)
    assert Decimal(str(ahora["por_comprobar"])) == antes - Decimal("500")
    assert Decimal(str(ahora["devolucion_en_revision"])) == Decimal("0")


def test_no_se_declara_dos_veces_el_mismo_dinero(cliente, sesion, datos):
    """Sin contar lo que está esperando, alguien podría declarar tres
    veces los mismos mil pesos mientras finanzas revisa la primera."""
    _servicio, _fila, viatico_id, _juan = _viatico_con_dinero(
        cliente, sesion, datos, dias=802, monto="1000")

    r = cliente.post(f"/campo/viaticos/{viatico_id}/devolucion",
                     json={"monto": "1000"}, headers=sesion("juan"))
    assert r.status_code == 200, r.text

    r = cliente.post(f"/campo/viaticos/{viatico_id}/devolucion",
                     json={"monto": "1000"}, headers=sesion("juan"))
    assert r.status_code == 409, r.text
    # El dinero se dice con sus centavos, aqui y en el mensaje.
    assert r.json()["detail"]["por_devolver"] == "0.00"


def test_la_rechazada_queda_con_su_motivo_y_libera_el_monto(cliente, sesion,
                                                            datos):
    """No se borra: la persona dijo que transfirió y eso queda. Una
    devolución que desaparece deja la discusión sin papeles."""
    _servicio, _fila, viatico_id, _juan = _viatico_con_dinero(
        cliente, sesion, datos, dias=803, monto="1000")

    r = cliente.post(f"/campo/viaticos/{viatico_id}/devolucion",
                     json={"monto": "1000"}, headers=sesion("juan"))
    devolucion_id = r.json()["devolucion_id"]

    r = cliente.post(f"/viaticos/devoluciones/{devolucion_id}/rechazar",
                     json={"motivo": "No aparece en el estado de cuenta"},
                     headers=sesion("finanzas"))
    assert r.status_code == 200, r.text

    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        fila = db.get(m.DevolucionViatico, devolucion_id)
        assert fila.estatus == m.EstatusDevolucion.RECHAZADA
        assert fila.motivo_rechazo
        assert float(fila.asignacion.monto_devuelto) == 0

    # Y el monto vuelve a estar disponible para declararlo bien.
    r = cliente.post(f"/campo/viaticos/{viatico_id}/devolucion",
                     json={"monto": "1000", "referencia": "SPEI-88"},
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text


def test_solo_se_devuelve_de_lo_propio(cliente, sesion, datos):
    """El viático es de una persona. Nadie devuelve por otra."""
    _servicio, _fila, viatico_id, _juan = _viatico_con_dinero(
        cliente, sesion, datos, dias=804)

    r = cliente.post(f"/campo/viaticos/{viatico_id}/devolucion",
                     json={"monto": "100"}, headers=sesion("carlos"))
    assert r.status_code == 403, r.text


def test_finanzas_captura_la_que_llego_sin_que_nadie_la_declarara(
        cliente, sesion, datos):
    """El agente sin la app transfiere igual. Finanzas la ve entrar y la
    captura: un solo acto, una sola fila, con su evidencia."""
    servicio, fila, viatico_id, _juan = _viatico_con_dinero(
        cliente, sesion, datos, dias=805, monto="1200")
    antes = Decimal(str(fila["por_comprobar"]))

    r = devolver(cliente, sesion("finanzas"), viatico_id, "1200")
    assert r.status_code == 200, r.text

    ahora = _mio(cliente, sesion, servicio)
    assert Decimal(str(ahora["por_comprobar"])) == antes - Decimal("1200")
    assert Decimal(str(ahora["devolucion_en_revision"])) == Decimal("0")


def test_la_devolucion_exige_referencia_y_comprobante(cliente, sesion, datos):
    """Del lado de finanzas los dos son obligatorios: es lo que permite
    rastrear el movimiento en el banco si después no cuadra."""
    _servicio, _fila, viatico_id, _juan = _viatico_con_dinero(
        cliente, sesion, datos, dias=806)

    r = cliente.post(f"/viaticos/{viatico_id}/devolver",
                     data={"monto": "100"}, headers=sesion("finanzas"))
    assert r.status_code == 422, r.text


def test_el_consultor_ya_no_registra_devoluciones(cliente, sesion, datos):
    """Nunca vio ese dinero entrar. Lo único que se registraba con su
    firma era su buena fe."""
    _servicio, _fila, viatico_id, _juan = _viatico_con_dinero(
        cliente, sesion, datos, dias=807)

    r = devolver(cliente, sesion("consultor"), viatico_id, "100")
    assert r.status_code == 403, r.text


def test_finanzas_ve_lo_que_esta_esperando_confirmacion(cliente, sesion,
                                                        datos):
    """Mientras siga ahí, ni el dinero volvió ni la persona quedó
    libre. Era lo único que esta pantalla no sabía mostrar."""
    _servicio, _fila, viatico_id, juan = _viatico_con_dinero(
        cliente, sesion, datos, dias=808, monto="900")

    cliente.post(f"/campo/viaticos/{viatico_id}/devolucion",
                 json={"monto": "900", "referencia": "SPEI-99"},
                 headers=sesion("juan"))

    r = cliente.get("/viaticos/finanzas/devoluciones",
                    headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    filas = [x for p in r.json()["paises"]
             for x in p.get("por_confirmar", [])
             if x["viatico_id"] == viatico_id]
    assert filas, r.json()
    assert filas[0]["referencia"] == "SPEI-99"
    assert filas[0]["persona"]


def test_la_pantalla_dice_cuanto_se_devolvio_y_la_cuenta_cierra(cliente,
                                                                sesion,
                                                                datos):
    """Entregado = comprobado + devuelto + lo que falta.

    La tarjeta decia "te depositaron 285, comprobaste 270, no te falta
    nada" y los quince pesos que faltaban para cuadrar no salian por
    ningun lado. Quien la lee no tiene como saber si sobro dinero, si se
    perdio o si la app esta mal.
    """
    servicio, _fila, viatico_id, _juan = _viatico_con_dinero(
        cliente, sesion, datos, dias=806, monto="1000")

    cliente.post(f"/campo/viaticos/{viatico_id}/comprobante",
                 json={"concepto": "alimentos", "tipo": "nota",
                       "monto": "700"}, headers=sesion("juan"))
    r = cliente.post(f"/campo/viaticos/{viatico_id}/devolucion",
                     json={"monto": "300", "referencia": "SPEI-99"},
                     headers=sesion("juan"))
    devolucion_id = r.json()["devolucion_id"]

    # Declarada todavia no es devuelta: se dice en su propio renglon.
    esperando = _mio(cliente, sesion, servicio)
    assert Decimal(str(esperando["devuelto"])) == Decimal("0")
    assert Decimal(str(esperando["devolucion_en_revision"])) == Decimal("300")

    cliente.post(f"/viaticos/devoluciones/{devolucion_id}/confirmar",
                 headers=sesion("finanzas"))

    fila = _mio(cliente, sesion, servicio)
    assert Decimal(str(fila["devuelto"])) == Decimal("300")
    assert (Decimal(str(fila["comprobado"]))
            + Decimal(str(fila["devuelto"]))
            + Decimal(str(fila["por_comprobar"]))
            == Decimal(str(fila["entregado"]))), "la cuenta no cierra"
    # Y por dia, que es como se comprueba.
    assert Decimal(str(fila["dias"][0]["devuelto"])) == Decimal("300")

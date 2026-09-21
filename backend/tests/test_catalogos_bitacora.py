"""Los catálogos: lo que se apaga se vuelve a encender, y todo queda escrito.

Aquí viven diecinueve catálogos —el tarifario que se le cobra al cliente,
lo que se le paga a cada rol, la plantilla, la flota— y hasta hoy tenían
dos huecos que se notaban solo el día que dolían:

**No había vuelta.** `DELETE` desactiva —nunca se borra historia— pero
nada volvía a encender, y como los esquemas de entrada no traen `activo`,
el `PATCH` tampoco podía. Una unidad desactivada por error se quedaba
fuera de todas las listas para siempre.

**No había rastro.** Se podía subir un precio un viernes y en diciembre no
había forma de saber quién lo subió ni cuánto valía antes. La bitácora de
administración existía desde el panel de accesos; faltaba conectarla.

Los nombres de lo que se crea aquí llevan un sufijo al azar: los
catálogos no se vacían entre pruebas —son el piso sobre el que corre toda
la batería— así que lo que una prueba da de alta se queda.
"""
import uuid

import pytest

from ayudas import asignar, crear_servicio, jornada, manana


def _ciudad(cliente, h, datos):
    r = cliente.post("/catalogos/plazas", headers=h, json={
        "pais_id": datos["mx"]["id"], "nombre": f"Prueba {uuid.uuid4().hex[:8]}"})
    assert r.status_code == 201, r.text
    return r.json()


def _historial(cliente, h, ruta, item_id):
    r = cliente.get(f"/catalogos/{ruta}/{item_id}/historial", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _acciones(filas):
    return [f["accion"] for f in filas]


# ============================================== volver a encender lo apagado

def test_lo_que_se_apaga_se_puede_volver_a_encender(cliente, sesion, datos):
    """El hueco que dejaba un catálogo apagado para siempre."""
    h = sesion("admin")
    ciudad = _ciudad(cliente, h, datos)

    assert cliente.delete(f"/catalogos/plazas/{ciudad['id']}",
                          headers=h).status_code == 204

    # Desactivada: deja de ofrecerse donde se elige.
    vivas = [p["id"] for p in cliente.get("/catalogos/plazas", headers=h).json()]
    assert ciudad["id"] not in vivas

    r = cliente.post(f"/catalogos/plazas/{ciudad['id']}/reactivar", headers=h)
    assert r.status_code == 200, r.text

    # Se comprueba en la lista y no en la respuesta: `PlazaOut` ni
    # siquiera devuelve `activo`, que es parte de por que este hueco vivio
    # tanto tiempo sin que nadie lo viera.
    vivas = [p["id"] for p in cliente.get("/catalogos/plazas", headers=h).json()]
    assert ciudad["id"] in vivas


def test_no_se_reactiva_lo_que_ya_estaba_activo(cliente, sesion, datos):
    h = sesion("admin")
    ciudad = _ciudad(cliente, h, datos)
    r = cliente.post(f"/catalogos/plazas/{ciudad['id']}/reactivar", headers=h)
    assert r.status_code == 409, r.text


def test_reactivar_algo_que_no_existe(cliente, sesion):
    r = cliente.post("/catalogos/plazas/999999/reactivar",
                     headers=sesion("admin"))
    assert r.status_code == 404, r.text


def test_reactivar_pide_lo_mismo_que_dar_de_baja(cliente, sesion, datos):
    """No se abre una puerta más ancha que la que ya existía: quien no
    puede desactivar una unidad tampoco la reactiva."""
    admin = sesion("admin")
    ciudad = _ciudad(cliente, admin, datos)
    cliente.delete(f"/catalogos/plazas/{ciudad['id']}", headers=admin)

    # Las ciudades las mueve el consultor —crecen con la operación— así
    # que él sí. Un tarifario, no.
    assert cliente.post(f"/catalogos/plazas/{ciudad['id']}/reactivar",
                        headers=sesion("consultor")).status_code == 200
    assert cliente.post("/catalogos/tarifarios/1/reactivar",
                        headers=sesion("consultor")).status_code == 403


# ====================================================== que quede escrito

def test_dar_de_alta_deja_renglon(cliente, sesion, datos):
    h = sesion("admin")
    ciudad = _ciudad(cliente, h, datos)
    filas = _historial(cliente, h, "plazas", ciudad["id"])
    assert _acciones(filas) == ["catalogo creado"]
    assert filas[0]["despues"] == ciudad["nombre"]
    assert filas[0]["quien"]
    assert filas[0]["rol_de_quien"] == "admin"


def test_el_cambio_dice_que_se_movio_y_cuanto_valia_antes(cliente, sesion,
                                                          datos):
    """Lo que alguien busca en diciembre no es cómo estaba todo ese día:
    es qué se le movió a ese renglón, cuánto valía antes y quién fue."""
    h = sesion("admin")
    ciudad = _ciudad(cliente, h, datos)
    nuevo = f"Corregida {uuid.uuid4().hex[:8]}"

    r = cliente.patch(f"/catalogos/plazas/{ciudad['id']}", headers=h,
                      json={"pais_id": datos["mx"]["id"], "nombre": nuevo})
    assert r.status_code == 200, r.text

    filas = _historial(cliente, h, "plazas", ciudad["id"])
    assert _acciones(filas) == ["catalogo cambiado", "catalogo creado"]
    cambio = filas[0]
    assert f"nombre: {ciudad['nombre']}" in cambio["antes"]
    assert f"nombre: {nuevo}" in cambio["despues"]
    # El país no se tocó, así que no ensucia el renglón.
    assert "pais_id" not in cambio["antes"]


def test_un_cambio_que_no_cambia_nada_no_ensucia_la_bitacora(cliente, sesion,
                                                             datos):
    """Guardar sin haber tocado nada es lo que más se hace en una pantalla
    de catálogo. Si cada guardado dejara renglón, el historial de un
    tarifario sería cien líneas iguales y la que importa estaría perdida
    entre ellas."""
    h = sesion("admin")
    ciudad = _ciudad(cliente, h, datos)
    cliente.patch(f"/catalogos/plazas/{ciudad['id']}", headers=h,
                  json={"pais_id": datos["mx"]["id"], "nombre": ciudad["nombre"]})

    filas = _historial(cliente, h, "plazas", ciudad["id"])
    assert _acciones(filas) == ["catalogo creado"]


def test_la_baja_y_el_alta_quedan_escritas(cliente, sesion, datos):
    h = sesion("admin")
    ciudad = _ciudad(cliente, h, datos)
    cliente.delete(f"/catalogos/plazas/{ciudad['id']}", headers=h)
    cliente.post(f"/catalogos/plazas/{ciudad['id']}/reactivar", headers=h)

    filas = _historial(cliente, h, "plazas", ciudad["id"])
    assert _acciones(filas) == ["catalogo reactivado", "catalogo desactivado",
                                "catalogo creado"]
    assert filas[0]["antes"] == "desactivado"
    assert filas[0]["despues"] == "activo"


def test_el_historial_lo_lee_quien_ve_el_numero_raro(cliente, sesion, datos):
    """Va con permiso de lectura, no de escritura.

    El tarifario solo lo mueve administración, pero la pregunta "¿quién
    subió esto?" la hace finanzas, que es quien ve el número al facturar.
    Si el historial pidiera permiso de escritura, el único que puede
    saber quién movió el precio sería el que lo movió.
    """
    admin = sesion("admin")
    r = cliente.post("/catalogos/tarifarios", headers=admin, json={
        "pais_id": datos["mx"]["id"], "moneda": "MXN",
        "vigencia_desde": "2026-01-01",
        "nombre": f"Tarifario {uuid.uuid4().hex[:8]}"})
    assert r.status_code == 201, r.text
    tarifario = r.json()

    # Finanzas no lo puede mover...
    suyo = {"pais_id": datos["mx"]["id"], "moneda": "MXN",
            "vigencia_desde": "2026-01-01", "nombre": "Mio"}
    assert cliente.patch(f"/catalogos/tarifarios/{tarifario['id']}",
                         headers=sesion("finanzas"),
                         json=suyo).status_code == 403
    # ...pero sí puede ver quién lo movió.
    filas = _historial(cliente, sesion("finanzas"), "tarifarios",
                       tarifario["id"])
    assert _acciones(filas) == ["catalogo creado"]


# ========================================= la baja de alguien con dinero

@pytest.fixture
def luis_vuelve_a_la_plantilla(cliente, sesion, datos):
    """Luis lo usan casi todas las baterías: pase lo que pase aquí, vuelve
    a estar de alta."""
    yield datos["personal"]["Luis Mendoza"]["id"]
    cliente.post(f"/catalogos/personal/{datos['personal']['Luis Mendoza']['id']}"
                 "/reactivar", headers=sesion("admin"))


def test_no_se_da_de_baja_a_quien_trae_dinero_sin_comprobar(
        cliente, sesion, datos, luis_vuelve_a_la_plantilla):
    """La misma regla que ya cuidaba el panel de accesos.

    Eran dos puertas a la misma baja —cerrarle el acceso y darlo de baja
    de la plantilla— y solo una tenía candado. Por la de aquí se iba con
    el dinero puesto, y el servicio se queda sin poder cerrar.
    """
    persona = luis_vuelve_a_la_plantilla
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(60), datos["modalidades"]["full_day"]["id"])])
    primera = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, primera["id"], persona_id=persona,
            vehiculo_id=datos["suburban"]["id"])

    viatico = cliente.post("/viaticos/asignar", headers=h, json={
        "jornada_id": primera["id"], "persona_id": persona,
        "conceptos": [{"concepto": "alimentos", "monto": "1200",
                       "origen": "tabulador"}]}).json()
    solicitud = cliente.post(
        f"/viaticos/{viatico['id']}/solicitar-transferencia", headers=h).json()
    assert cliente.post(
        f"/viaticos/transferencias/{solicitud['id']}/confirmar",
        params={"referencia_odoo": "TRX-951"},
        headers=sesion("finanzas")).status_code == 200

    r = cliente.delete(f"/catalogos/personal/{persona}",
                       headers=sesion("admin"))
    assert r.status_code == 409, r.text
    cuerpo = r.json()["detail"]
    assert len(cuerpo["viaticos"]) == 1
    assert "ciclo" in cuerpo["que_hacer"].lower()

    # Y sigue en la plantilla: el candado no se cerró a medias.
    vivos = [p["id"] for p in
             cliente.get("/catalogos/personal", headers=sesion("admin")).json()]
    assert persona in vivos


def test_sin_dinero_de_por_medio_si_se_da_de_baja(
        cliente, sesion, datos, luis_vuelve_a_la_plantilla):
    """Quien no trae nada se va y ya. El candado es por el dinero, no por
    la persona."""
    persona = luis_vuelve_a_la_plantilla
    h = sesion("admin")
    assert cliente.delete(f"/catalogos/personal/{persona}",
                          headers=h).status_code == 204

    filas = _historial(cliente, h, "personal", persona)
    assert filas[0]["accion"] == "catalogo desactivado"
    assert filas[0]["detalle"] == "Luis Mendoza"

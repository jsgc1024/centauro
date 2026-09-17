"""El deposito bancario.

Finanzas paga un deposito por persona y equipo: son varios dias, varias
solicitudes, y una sola transferencia. Ese hecho no vivia en ninguna
tabla —la bandeja lo armaba al vuelo— y por eso no habia a que colgarle
la referencia ni el comprobante del banco.

Lo que se verifica aqui no es que el endpoint conteste 201, sino que
quede la evidencia: que un deposito confirme de golpe todos sus dias,
que no se pueda pagar dos veces lo mismo, que el desglose que finanzas
lee sume exactamente lo que se va a depositar, y que sin comprobante no
se registre.
"""
import base64
import io

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana)

# Un PNG de un pixel. Lo que importa de la evidencia en estas pruebas no
# es que se vea, sino que exista y que se pueda volver a bajar.
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg==")


def _archivo():
    return {"archivo": ("comprobante.png", io.BytesIO(PIXEL), "image/png")}


def _servicio_con_viaticos(cliente, sesion, datos, dias=2, monto="900"):
    """Dos dias con Juan, con viaticos asignados y ya solicitados."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(400 + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    juan = datos["personal"]["Juan Ramirez"]["id"]
    ids = []
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"], persona_id=juan,
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
        viatico = cliente.post(
            "/viaticos/asignar", headers=h,
            json={"jornada_id": j["id"], "persona_id": juan,
                  "conceptos": [
                      {"concepto": "alimentos", "monto": monto,
                       "origen": "tabulador"},
                      {"concepto": "combustible", "monto": "200",
                       "origen": "estimado",
                       "descripcion": "120 km"}]}).json()
        solicitud = cliente.post(
            f"/viaticos/{viatico['id']}/solicitar-transferencia",
            headers=h).json()
        ids.append(solicitud["id"])
    return servicio, ids


def _bandeja(cliente, sesion, folio):
    datos = cliente.get("/viaticos/finanzas/bandeja",
                        headers=sesion("finanzas")).json()
    for pais in datos["paises"]:
        for fila in pais["depositos"]:
            if fila["folio"] == folio:
                return fila
    return None


def _depositar(cliente, sesion, fila, referencia="SPEI-4471002839",
               archivo=True):
    envio = {"equipo_id": str(fila["equipo_id"]),
             "persona_id": str(fila["persona_id"]),
             "referencia": referencia}
    return cliente.post("/viaticos/finanzas/depositar", data=envio,
                        files=_archivo() if archivo else None,
                        headers=sesion("finanzas"))


# ================================================== lo que finanzas ve

def test_la_bandeja_dice_de_que_se_compone(cliente, sesion, datos):
    """Finanzas veia un total y nada mas. Para depositar alcanzaba; para
    revisar antes de depositar, no."""
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])
    assert fila, "el deposito no aparecio en la bandeja"

    # Un renglon por persona, con sus dos dias adentro.
    assert fila["dias"] == 2
    assert len(fila["detalle"]) == 2

    # Y el desglose suma exactamente lo que se va a depositar. Si no
    # cuadrara, finanzas estaria autorizando algo distinto de lo que ve.
    suma = sum(float(c["monto"]) for d in fila["detalle"]
               for c in d["conceptos"])
    assert round(suma, 2) == round(float(fila["monto"]), 2)


def test_se_ve_quien_lo_solicito_y_de_donde_sale_cada_monto(cliente, sesion,
                                                             datos):
    """El origen importa tanto como el monto: uno del tabulador no se
    discute, uno capturado a mano si."""
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])

    assert fila["solicito"] == "Ana Solis"
    origenes = {c["origen"] for d in fila["detalle"] for c in d["conceptos"]}
    assert origenes == {"tabulador", "estimado"}


# ================================================== el deposito

def test_un_deposito_confirma_todos_sus_dias(cliente, sesion, datos):
    """Son dos dias y una sola transferencia. Confirmar dos renglones del
    mismo agente es como se paga dos veces."""
    servicio, ids = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])

    r = _depositar(cliente, sesion, fila)
    assert r.status_code == 200, r.text
    assert r.json()["depositos"] == 2
    assert float(r.json()["monto"]) == float(fila["monto"])

    # Y sale de la bandeja: ya se pago.
    assert _bandeja(cliente, sesion, servicio["folio"]) is None


def test_sin_comprobante_no_se_registra(cliente, sesion, datos):
    """Sin evidencia, la unica prueba de que se pago es la palabra de
    quien lo hizo."""
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])

    r = _depositar(cliente, sesion, fila, archivo=False)
    assert r.status_code == 422, r.text
    # Y no se pago a medias: sigue en la bandeja.
    assert _bandeja(cliente, sesion, servicio["folio"]) is not None


def test_no_se_paga_dos_veces_lo_mismo(cliente, sesion, datos):
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])
    assert _depositar(cliente, sesion, fila).status_code == 200

    r = _depositar(cliente, sesion, fila)
    assert r.status_code == 404, r.text


def test_la_evidencia_se_puede_ver_despues(cliente, sesion, datos):
    """Un comprobante que se guarda y no se puede volver a ver no es
    evidencia."""
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])
    deposito_id = _depositar(cliente, sesion, fila).json()["deposito_id"]

    r = cliente.get(f"/viaticos/depositos/{deposito_id}/comprobante",
                    headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.content == PIXEL


def test_el_agente_ve_el_suyo_y_solo_el_suyo(cliente, sesion, datos):
    """Contesta la pregunta que hoy termina en una llamada al consultor.
    Y solo la suya: el deposito de otro no es asunto de nadie."""
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])
    deposito_id = _depositar(cliente, sesion, fila).json()["deposito_id"]

    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    suyo = next(x for x in mios["servicios"] if x["folio"] == servicio["folio"])
    assert len(suyo["depositos"]) == 1
    assert suyo["depositos"][0]["referencia"] == "SPEI-4471002839"
    assert suyo["depositos"][0]["tiene_comprobante"] is True

    assert cliente.get(f"/viaticos/depositos/{deposito_id}/comprobante",
                       headers=sesion("juan")).status_code == 200
    ajeno = cliente.get(f"/viaticos/depositos/{deposito_id}/comprobante",
                        headers=sesion("luis"))
    assert ajeno.status_code == 403, ajeno.text


# ================================================== corregir y anular

def test_la_evidencia_se_corrige_y_deja_rastro(cliente, sesion, datos):
    """Subir el archivo correcto es lo mas comun que pasa despues. Una
    evidencia que se reemplaza sin rastro no es evidencia."""
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])
    deposito_id = _depositar(cliente, sesion, fila).json()["deposito_id"]

    r = cliente.patch(f"/viaticos/depositos/{deposito_id}",
                      data={"referencia": "SPEI-0000000001"},
                      headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["referencia"] == "SPEI-0000000001"
    assert r.json()["corregido_en"], "sin rastro de quien la cambio"
    assert r.json()["corregido_por"]


def test_no_se_anula_si_el_agente_ya_comprobo(cliente, sesion, datos):
    """Anularlo dejaria comprobaciones colgando de un deposito que ya no
    existe, y arreglarlo seria peor que el error."""
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])
    hecho = _depositar(cliente, sesion, fila).json()

    # Antes de comprobar nada, si se puede.
    limpio = cliente.post(f"/viaticos/depositos/{hecho['deposito_id']}/anular",
                          data={"motivo": "Me equivoque de persona"},
                          headers=sesion("finanzas"))
    assert limpio.status_code == 200, limpio.text

    # Se vuelve a depositar y ahora el agente comprueba un gasto.
    fila = _bandeja(cliente, sesion, servicio["folio"])
    assert fila, "las solicitudes tenian que regresar a la bandeja"
    otro = _depositar(cliente, sesion, fila).json()

    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    suyo = next(x for x in mios["servicios"] if x["folio"] == servicio["folio"])
    viatico_id = suyo["dias"][0]["viatico_id"]
    subido = cliente.post(f"/viaticos/{viatico_id}/comprobantes",
                          headers=sesion("juan"),
                          json={"concepto": "alimentos", "tipo": "nota",
                                "monto": "100"})
    assert subido.status_code in (200, 201), subido.text

    r = cliente.post(f"/viaticos/depositos/{otro['deposito_id']}/anular",
                     data={"motivo": "Ya no"}, headers=sesion("finanzas"))
    assert r.status_code == 409, r.text


def test_anular_necesita_motivo(cliente, sesion, datos):
    """Es la unica huella que queda de dinero que salio del banco y se
    dio por no salido."""
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])
    hecho = _depositar(cliente, sesion, fila).json()

    r = cliente.post(f"/viaticos/depositos/{hecho['deposito_id']}/anular",
                     data={"motivo": "   "}, headers=sesion("finanzas"))
    assert r.status_code == 400, r.text


# ================================================== la memoria

def test_depositado_lista_un_renglon_por_deposito(cliente, sesion, datos):
    """No uno por dia: son dos dias y una transferencia. Listarla dos
    veces hace parecer que se pago dos veces."""
    servicio, _ = _servicio_con_viaticos(cliente, sesion, datos)
    fila = _bandeja(cliente, sesion, servicio["folio"])
    _depositar(cliente, sesion, fila)

    datos_ = cliente.get("/viaticos/finanzas/depositado",
                         headers=sesion("finanzas")).json()
    suyos = [d for p in datos_["paises"] for d in p["depositos"]
             if d["folio"] == servicio["folio"]]
    assert len(suyos) == 1, suyos
    assert suyos[0]["dias"] == 2
    assert suyos[0]["tiene_comprobante"] is True
    assert suyos[0]["despacho"], "sin decir quien lo despacho"

"""Quien puede hacer que. Lo que mas importa: que nadie corrija su propia marca."""
from ayudas import (DENTRO, asignar, configurar_origen, crear_servicio,
                    jornada, manana, marcar)
from datetime import datetime, timedelta


def test_sin_sesion_no_se_entra(cliente):
    assert cliente.get("/servicios").status_code == 401


def test_contrasena_incorrecta(cliente):
    r = cliente.post("/auth/token", data={"username": "juan.ramirez@centauro.lat",
                                          "password": "equivocada"})
    assert r.status_code == 401


def test_cada_rol_en_su_carril(cliente, sesion, datos):
    import uuid
    # El conductor no da de alta servicios
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual", "equipos": []},
        headers=sesion("juan"))
    assert r.status_code == 403

    # El barrido de transferencias es de finanzas
    assert cliente.post("/viaticos/transferencias/barrido",
                        headers=sesion("consultor")).status_code == 403
    assert cliente.post("/viaticos/transferencias/barrido",
                        headers=sesion("finanzas")).status_code == 200

    # Los catalogos de dinero son de administracion
    tarifario = {"pais_id": datos["mx"]["id"], "moneda": "MXN",
                 "vigencia_desde": "2026-01-01",
                 "nombre": f"Tarifario {uuid.uuid4().hex[:8]}"}
    assert cliente.post("/catalogos/tarifarios", json=tarifario,
                        headers=sesion("consultor")).status_code == 403
    assert cliente.post("/catalogos/tarifarios", json=tarifario,
                        headers=sesion("admin")).status_code == 201

    # Las ciudades son la excepcion: crecen con la operacion y las agrega
    # el consultor al dar de alta un servicio donde nunca se ha trabajado.
    ciudad = {"pais_id": datos["mx"]["id"],
              "nombre": f"Ciudad {uuid.uuid4().hex[:8]}"}
    assert cliente.post("/catalogos/plazas", json=ciudad,
                        headers=sesion("consultor")).status_code == 201


def test_direccion_general_alcanza_operacion_pero_no_catalogos(cliente, sesion, datos):
    h = sesion("dirgeneral")
    assert cliente.get("/servicios", headers=h).status_code == 200
    assert cliente.post("/viaticos/transferencias/barrido", headers=h).status_code == 200
    import uuid
    assert cliente.post("/catalogos/tarifarios",
                        json={"pais_id": datos["mx"]["id"], "moneda": "MXN",
                              "vigencia_desde": "2026-01-01",
                              "nombre": f"Tarifario {uuid.uuid4().hex[:8]}"},
                        headers=h).status_code == 403


def _jornada_con_juan(cliente, sesion, datos, dia=None):
    h = sesion("consultor")
    dia = dia or manana(20)
    servicio = crear_servicio(cliente, h, datos,
                              [jornada(dia, datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=datos["personal"]["Juan Ramirez"]["id"])
    configurar_origen(cliente, h, j["id"])
    return j


def test_el_personal_solo_marca_en_sus_jornadas(cliente, sesion, datos):
    j = _jornada_con_juan(cliente, sesion, datos)
    inicio = datetime.fromisoformat(j["inicio_programado"])

    ajeno = marcar(cliente, sesion("luis"), j["id"], "llegada_origen", inicio)
    assert ajeno.status_code == 403

    propio = marcar(cliente, sesion("juan"), j["id"], "llegada_origen", inicio)
    assert propio.status_code == 200


def test_nadie_ajusta_su_propia_marca(cliente, sesion, datos):
    j = _jornada_con_juan(cliente, sesion, datos, manana(21))
    inicio = datetime.fromisoformat(j["inicio_programado"])
    hito = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  inicio - timedelta(minutes=5)).json()["hito_id"]

    ajuste = {"nuevo_momento": inicio.isoformat(),
              "justificacion": "El conductor pidio el ajuste por telefono."}

    assert cliente.post(f"/operacion/hitos/{hito}/ajustar", json=ajuste,
                        headers=sesion("juan")).status_code == 403
    assert cliente.post(f"/operacion/hitos/{hito}/ajustar", json=ajuste,
                        headers=sesion("consultor")).status_code == 403
    assert cliente.post(f"/operacion/hitos/{hito}/ajustar", json=ajuste,
                        headers=sesion("central")).status_code == 200


def test_el_ajuste_exige_justificacion_y_queda_firmado(cliente, sesion, datos):
    j = _jornada_con_juan(cliente, sesion, datos, manana(22))
    inicio = datetime.fromisoformat(j["inicio_programado"])
    hito = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  inicio - timedelta(minutes=5)).json()["hito_id"]

    corta = cliente.post(f"/operacion/hitos/{hito}/ajustar",
                         json={"nuevo_momento": inicio.isoformat(),
                               "justificacion": "porque si"},
                         headers=sesion("central"))
    assert corta.status_code == 400

    cliente.post(f"/operacion/hitos/{hito}/ajustar",
                 json={"nuevo_momento": inicio.isoformat(),
                       "justificacion": "Error de la app confirmado con GPS."},
                 headers=sesion("central"))

    bitacora = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                           headers=sesion("central")).json()
    ajuste = bitacora["hitos"][0]["ajuste"]
    assert ajuste is not None
    assert ajuste["ajustado_por"] == "Sofia Navarro"
    assert "GPS" in ajuste["justificacion"]


def test_el_personal_solo_ve_sus_propias_jornadas(cliente, sesion, datos):
    j = _jornada_con_juan(cliente, sesion, datos, manana(23))
    assert cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                       headers=sesion("luis")).status_code == 403
    assert cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                       headers=sesion("juan")).status_code == 200


def test_cobertura_entre_consultores_queda_registrada(cliente, sesion, datos):
    ana = datos["personal"]["Ana Solis"]["id"]
    servicio = crear_servicio(cliente, sesion("consultor"), datos,
                              [jornada(manana(24),
                                       datos["modalidades"]["full_day"]["id"])],
                              consultor_id=ana)
    j = servicio["equipos"][0]["jornadas"][0]

    # Beatriz cubre a Ana
    r = asignar(cliente, sesion("consultor2"), j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"])[0]
    assert r.status_code == 200

    auditoria = cliente.get(f"/servicios/{servicio['id']}/auditoria",
                            headers=sesion("consultor")).json()
    assert auditoria["consultor_titular"] == "Ana Solis"
    assert auditoria["movimientos_en_cobertura"] >= 1
    cobertura = [m for m in auditoria["movimientos"] if m["en_cobertura"]]
    assert cobertura[0]["quien"] == "Beatriz Roman"


def test_un_duplicado_devuelve_un_mensaje_claro(cliente, sesion, datos):
    """Nada de errores del servidor con traza: un choque se explica."""
    h = sesion("admin")
    plaza = {"pais_id": datos["mx"]["id"], "nombre": "Plaza Duplicada"}

    primera = cliente.post("/catalogos/plazas", json=plaza, headers=h)
    assert primera.status_code in (201, 409)

    segunda = cliente.post("/catalogos/plazas", json=plaza, headers=h)
    assert segunda.status_code == 409
    assert "ya existe" in segunda.json()["detail"]["mensaje"].lower()

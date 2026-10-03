"""El mapa de riesgo de la Central de Inteligencia (seccion 133).

Lo que se cuida: nada llega al cliente sin publicarse; el nivel 4 lo
confirma otra persona; la verificacion sale de las fuentes; todo evento
se apaga solo al vencer su vigencia.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import riesgo

AHORA = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
def cat(cliente, sesion, datos):
    r = cliente.get(f"/riesgo/catalogos?pais_id={datos['mx']['id']}",
                    headers=sesion("central"))
    assert r.status_code == 200, r.text
    c = r.json()
    return {
        "pais_id": datos["mx"]["id"],
        "regiones": {x["nombre"]: x["id"] for x in c["regiones"]},
        "tipos": {x["nombre"]: x["id"] for x in c["tipos"]},
    }


@pytest.fixture
def capturar(cliente, sesion, cat):
    def hacer(quien="central", **cambios):
        cuerpo = {
            "pais_id": cat["pais_id"],
            "region_id": cat["regiones"]["Tamaulipas"],
            "municipio": "Reynosa",
            "tipo_id": cat["tipos"]["Enfrentamiento armado"],
            "nivel": 3,
            "titulo": "Enfrentamiento en el libramiento de Reynosa",
            "texto_cliente": "Enfrentamiento armado en el libramiento "
                             "Reynosa-Monterrey. Evite la zona.",
            "lat": 26.0508, "lon": -98.2979,
            "ocurrio_en": (AHORA - timedelta(minutes=30)).isoformat(),
            "vigente_hasta": (AHORA + timedelta(hours=6)).isoformat(),
            "tendencia": "creciente",
        }
        cuerpo.update(cambios)
        return cliente.post("/riesgo/eventos", json=cuerpo,
                            headers=sesion(quien))
    return hacer


def test_los_catalogos_traen_estados_y_la_cifra_negra(cat):
    assert len(cat["regiones"]) == 32
    assert "Ciudad de México" in cat["regiones"]
    for tipo in ("Artefacto explosivo", "Ponchallantas", "Mensaje criminal",
                 "Bloqueo carretero"):
        assert tipo in cat["tipos"]


def test_nace_propuesto_y_no_sale_en_el_mapa(cliente, sesion, capturar, cat):
    r = capturar()
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["folio"].startswith("CI-")
    assert e["estado"] == "propuesto"
    assert e["radio_m"] == 3000            # el del tipo
    assert e["bitacora"][0]["accion"] == "creo"

    mapa = cliente.get(f"/riesgo/mapa?pais_id={cat['pais_id']}",
                       headers=sesion("central")).json()
    assert mapa["publicados"] == []
    assert [x["id"] for x in mapa["cola"]] == [e["id"]]


def test_publicar_lo_pone_en_el_mapa_y_avisa(cliente, sesion, capturar, cat):
    avisos = []
    riesgo.AL_PUBLICAR.append(lambda db, ev, motivo: avisos.append(
        (ev.folio, motivo)))
    try:
        e = capturar(nivel=2).json()
        r = cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                         headers=sesion("central"))
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "publicado"
        mapa = cliente.get(f"/riesgo/mapa?pais_id={cat['pais_id']}",
                           headers=sesion("central")).json()
        assert [x["id"] for x in mapa["publicados"]] == [e["id"]]
        assert mapa["cola"] == []
        assert avisos == [(e["folio"], "nuevo")]
    finally:
        riesgo.AL_PUBLICAR.pop()


def test_sin_texto_para_el_cliente_no_se_publica(cliente, sesion, capturar):
    e = capturar(texto_cliente="").json()
    r = cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                     headers=sesion("central"))
    assert r.status_code == 400
    assert "texto para el cliente" in r.json()["detail"]["mensaje"]


def test_nivel_4_espera_al_jefe_y_no_lo_confirma_quien_lo_pidio(
        cliente, sesion, capturar):
    avisos = []
    riesgo.AL_PUBLICAR.append(lambda db, ev, motivo: avisos.append(motivo))
    try:
        e = capturar("diroperaciones", nivel=4).json()
        r = cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                         headers=sesion("diroperaciones"))
        assert r.json()["estado"] == "por_confirmar"
        assert avisos == []                       # todavia no sale

        r = cliente.post(f"/riesgo/eventos/{e['id']}/confirmar",
                         headers=sesion("diroperaciones"))
        assert r.status_code == 409
        assert "otra persona" in r.json()["detail"]["mensaje"]

        # La central no confirma: no es jefe de turno.
        r = cliente.post(f"/riesgo/eventos/{e['id']}/confirmar",
                         headers=sesion("central"))
        assert r.status_code == 403

        r = cliente.post(f"/riesgo/eventos/{e['id']}/confirmar",
                         headers=sesion("dirgeneral"))
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "publicado"
        assert r.json()["nivel"] == 4
        assert avisos == ["nuevo"]
    finally:
        riesgo.AL_PUBLICAR.pop()


def test_publicado_que_sube_a_4_sigue_en_su_nivel_hasta_confirmar(
        cliente, sesion, capturar):
    avisos = []
    riesgo.AL_PUBLICAR.append(lambda db, ev, motivo: avisos.append(
        (motivo, ev.nivel)))
    try:
        e = capturar(nivel=2).json()
        cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                     headers=sesion("central"))
        r = cliente.patch(f"/riesgo/eventos/{e['id']}", json={"nivel": 4},
                          headers=sesion("central"))
        assert r.status_code == 200, r.text
        assert r.json()["nivel"] == 2
        assert r.json()["nivel_pendiente"] == 4
        assert avisos == [("nuevo", 2)]

        r = cliente.post(f"/riesgo/eventos/{e['id']}/confirmar",
                         headers=sesion("diroperaciones"))
        assert r.json()["nivel"] == 4
        assert r.json()["nivel_pendiente"] is None
        assert avisos == [("nuevo", 2), ("sube", 4)]
    finally:
        riesgo.AL_PUBLICAR.pop()


def test_subir_de_1_a_3_avisa_otra_vez_y_bajar_no(cliente, sesion, capturar):
    avisos = []
    riesgo.AL_PUBLICAR.append(lambda db, ev, motivo: avisos.append(motivo))
    try:
        e = capturar(nivel=1).json()
        cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                     headers=sesion("central"))
        cliente.patch(f"/riesgo/eventos/{e['id']}", json={"nivel": 3},
                      headers=sesion("central"))
        cliente.patch(f"/riesgo/eventos/{e['id']}", json={"nivel": 2},
                      headers=sesion("central"))
        assert avisos == ["nuevo", "sube"]
    finally:
        riesgo.AL_PUBLICAR.pop()


def test_el_jefe_devuelve_el_4_con_su_motivo(cliente, sesion, capturar):
    e = capturar(nivel=4).json()
    cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                 headers=sesion("central"))
    r = cliente.post(f"/riesgo/eventos/{e['id']}/devolver",
                     json={"motivo": "corto"},
                     headers=sesion("diroperaciones"))
    assert r.status_code == 400
    r = cliente.post(f"/riesgo/eventos/{e['id']}/devolver",
                     json={"motivo": "Una sola fuente sin confirmar todavía"},
                     headers=sesion("diroperaciones"))
    assert r.json()["estado"] == "propuesto"
    assert r.json()["bitacora"][-1]["accion"] == "devolvio_critico"


def test_editar_lo_que_espera_al_jefe_lo_regresa_a_propuesto(
        cliente, sesion, capturar):
    e = capturar(nivel=4).json()
    cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                 headers=sesion("central"))
    r = cliente.patch(f"/riesgo/eventos/{e['id']}",
                      json={"municipio": "Río Bravo"},
                      headers=sesion("central"))
    assert r.json()["estado"] == "propuesto"


def test_la_verificacion_sale_de_las_fuentes(cliente, sesion, capturar):
    e = capturar().json()
    url = f"/riesgo/eventos/{e['id']}/fuentes"
    h = sesion("central")
    r = cliente.post(url, json={"descripcion": "El Mañana de Reynosa",
                                "url": "https://elmanana.com/nota"},
                     headers=h)
    assert r.json()["verificacion"] == "sin_confirmar"
    r = cliente.post(url, json={"descripcion": "Cuenta de X @ReynosaFollow"},
                     headers=h)
    assert r.json()["verificacion"] == "confirmado"
    r = cliente.post(url, json={"descripcion": "Comunicado de la SSP",
                                "oficial": True}, headers=h)
    assert r.json()["verificacion"] == "oficial"
    oficial = r.json()["fuentes"][-1]["id"]
    r = cliente.delete(f"{url}/{oficial}", headers=h)
    assert r.json()["verificacion"] == "confirmado"
    r = cliente.post(url, json={"descripcion": "Nota", "url": "ftp://x"},
                     headers=h)
    assert r.status_code == 400


def test_lo_publicado_se_cierra_y_no_se_descarta(cliente, sesion, capturar):
    e = capturar(nivel=2).json()
    h = sesion("central")
    cliente.post(f"/riesgo/eventos/{e['id']}/publicar", headers=h)
    r = cliente.post(f"/riesgo/eventos/{e['id']}/descartar",
                     json={"motivo": "Ya no aplica para nada"}, headers=h)
    assert r.status_code == 409
    r = cliente.post(f"/riesgo/eventos/{e['id']}/cerrar",
                     json={"motivo": "La SSP reporta la zona en calma"},
                     headers=h)
    assert r.json()["estado"] == "cerrado"
    r = cliente.patch(f"/riesgo/eventos/{e['id']}", json={"nivel": 1},
                      headers=h)
    assert r.status_code == 409


def test_el_reloj_cierra_lo_vencido(cliente, sesion, capturar):
    from app.db import SessionLocal
    from app import models as m

    publicado = capturar(nivel=2).json()
    cliente.post(f"/riesgo/eventos/{publicado['id']}/publicar",
                 headers=sesion("central"))
    propuesto = capturar(nivel=2).json()

    db = SessionLocal()
    try:
        assert riesgo.vencer(db, AHORA + timedelta(hours=1)) == 0
        assert riesgo.vencer(db, AHORA + timedelta(hours=7)) == 2
        db.commit()
        assert db.get(m.EventoRiesgo, publicado["id"]).estado == \
            m.EstadoEvento.CERRADO
        assert db.get(m.EventoRiesgo, propuesto["id"]).estado == \
            m.EstadoEvento.DESCARTADO
    finally:
        db.close()


@pytest.mark.parametrize("cambios, frase", [
    ({"region_id": None}, "Faltan datos"),
    ({"vigente_hasta": (AHORA - timedelta(hours=1)).isoformat()},
     "termina antes"),
    ({"vigente_hasta": (AHORA + timedelta(days=40)).isoformat()},
     "30 días"),
    ({"nivel": 5}, "del 1"),
    ({"lat": 26.05, "lon": None}, "latitud y longitud"),
    ({"radio_m": 10}, "radio"),
])
def test_lo_que_no_entra(capturar, cambios, frase):
    r = capturar(**cambios)
    assert r.status_code == 400, r.text
    detalle = r.json()["detail"]
    texto = detalle["mensaje"] if isinstance(detalle, dict) else detalle
    assert frase in texto


def test_un_estado_de_otro_pais_no_entra(cliente, sesion, capturar, datos):
    paises = cliente.get("/catalogos/paises", headers=sesion("admin")).json()
    br = next(p for p in paises if p["codigo"] == "BR")
    regiones = cliente.get(f"/riesgo/catalogos?pais_id={br['id']}",
                           headers=sesion("central")).json()["regiones"]
    r = capturar(region_id=regiones[0]["id"])
    assert r.status_code == 400
    assert "no es de este país" in r.json()["detail"]


def test_sin_zona_horaria_la_hora_es_la_del_pais(capturar):
    r = capturar(ocurrio_en="2026-10-02T21:00:00",
                 vigente_hasta="2026-10-03T03:00:00")
    assert r.status_code == 200, r.text
    # Se guarda en UTC (las 03:00 del dia siguiente) y sale en la hora del
    # pais del evento.
    assert r.json()["ocurrio_en"] == "2026-10-02T21:00:00-06:00"
    from app.db import SessionLocal
    from app import models as m
    db = SessionLocal()
    try:
        guardado = db.get(m.EventoRiesgo, r.json()["id"]).ocurrio_en
        assert guardado == datetime(2026, 10, 3, 3, 0, tzinfo=timezone.utc)
    finally:
        db.close()


def test_quien_no_es_de_la_central_no_entra(cliente, sesion, cat, capturar):
    assert cliente.get("/riesgo/mapa", headers=sesion("consultor")) \
        .status_code == 403
    assert capturar("consultor").status_code == 403


def test_el_catalogo_de_tipos(cliente, sesion, cat):
    h = sesion("diroperaciones")
    r = cliente.post("/riesgo/tipos", json={
        "pais_id": cat["pais_id"], "nombre": "Robo a transporte",
        "definicion": "Robo con violencia a unidad de carga en tránsito.",
        "radio_m": 3000}, headers=h)
    assert r.status_code == 200, r.text
    nuevo = r.json()["id"]
    r = cliente.post("/riesgo/tipos", json={
        "pais_id": cat["pais_id"], "nombre": "Robo a transporte"}, headers=h)
    assert r.status_code == 409
    r = cliente.patch(f"/riesgo/tipos/{nuevo}", json={"activo": False},
                      headers=h)
    assert r.status_code == 200
    assert cliente.post("/riesgo/tipos", json={
        "pais_id": cat["pais_id"], "nombre": "Otro"},
        headers=sesion("central")).status_code == 403

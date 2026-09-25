# -*- coding: utf-8 -*-
"""El GPS de las unidades (seccion 60 de la bitacora).

Contra un Pegasus de mentiras, en memoria: ninguna prueba sale a la red.
Las unidades, los panicos y los tramos del dia se arman aqui con la forma
que tiene Pegasus de verdad --la del reconocimiento del 23 de
septiembre--: horas en UTC, velocidades en millas, distancias en metros.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from ayudas import (DENTRO, asignar, configurar_origen, crear_servicio,
                    jornada, marcar, marcar_fin)
from app import gps
from app import gps_reglas as reglas
from app import models as m

MX = ZoneInfo("America/Mexico_City")
ORIGEN_LAT, ORIGEN_LON = 19.4270, -99.1677
KM_POR_GRADO = 104.5
GRUPO_MX, GRUPO_BR = 3436, 2477


def a_km(km: float) -> tuple:
    """Un punto a esa distancia del origen de las pruebas, al oriente."""
    return (ORIGEN_LAT, ORIGEN_LON + km / KM_POR_GRADO)


def utc(local: datetime) -> datetime:
    return local.replace(tzinfo=MX).astimezone(timezone.utc)


def texto(instante: datetime) -> str:
    return instante.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def unidad(vid, placa, cuando, lat=None, lon=None, mph=0.0, ign=True,
           ign_desde=None, pwr=True, pwr_desde=None, jam=False,
           jam_desde=None, parada_desde=None, odometro_m=48_210_000,
           con_encendido=True):
    """Una unidad de /vehicles, con su ultimo reporte."""
    t = cuando.timestamp()

    def dato(valor, desde=None):
        return {"value": valor, "evtime": t,
                "change": {"evtime": (desde or cuando).timestamp()}}

    data = {"mph": dato(mph, parada_desde),
            "io_pwr": dato(pwr, pwr_desde),
            "jamm_detected": dato(jam, jam_desde)}
    if con_encendido:
        data["io_ign"] = dato(ign, ign_desde)
    return {"id": vid, "name": "Juan Ramirez SUBURBAN",
            "info": {"license_plate": placa, "make": "CHEVROLET",
                     "model": "SUBURBAN", "color": "Negro", "year": 2024,
                     "vin": "no se guarda"},
            "device": {"imei": "no se guarda", "latest": {
                "loc": {"evtime": t, "lat": lat, "lon": lon, "mph": mph},
                "data": data,
                "counters": {"evtime": t, "dev_dist": odometro_m}}}}


class PegasusFalso:
    def __init__(self):
        self.grupos_ = [{"id": GRUPO_MX, "name": "2025 P.E."},
                        {"id": GRUPO_BR, "name": "CENTAURO BRASIL"},
                        {"id": 1, "name": "CLIENTE AJENO"}]
        self.unidades_ = {GRUPO_MX: [], GRUPO_BR: []}
        self.eventos_ = []
        self.tramos_ = []
        self.leidos = []
        self.pedidos = []         # (etiquetas, unidades) de cada /rawdata

    def grupos(self):
        return self.grupos_

    def unidades(self, grupo_id):
        self.leidos.append(grupo_id)
        return self.unidades_.get(grupo_id, [])

    def eventos(self, vehiculos, duracion, etiquetas=None, campos=None,
                tope=None):
        vs = {str(v) for v in vehiculos}
        self.pedidos.append((etiquetas, {int(v) for v in vehiculos}))
        quiere = set(etiquetas.split(",")) if etiquetas else None
        return [e for e in self.eventos_ if str(e["vid"]) in vs
                and (quiere is None or e.get("label") in quiere)]

    def tramos(self, vehiculos, duracion):
        vs = {str(v) for v in vehiculos}
        return [t for t in self.tramos_ if str(t["vid"]) in vs]


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture
def pegasus():
    return PegasusFalso()


def _dia_de_hoy(cliente, sesion, datos, hora="18:00:00", escolta=False,
                fecha=None):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(fecha or date.today(),
                 datos["modalidades"]["full_day"]["id"], hora=hora)])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    if escolta:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Luis Mendoza"]["id"],
                rol="agente_seguridad")
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def _estar(db, j):
    from app import trayecto
    return trayecto.hora_de_estar(db, db.get(m.Jornada, j["id"]))


def _en_curso(cliente, sesion, datos, escolta=False):
    """Un servicio de hoy que ya arranco: llegada y contacto marcados."""
    ahora = datetime.now().replace(second=0, microsecond=0)
    # El dia es el del arranque, no el de hoy: pasada la medianoche, lo
    # que arranco hace 50 minutos es de ayer. Con la fecha de hoy, entre
    # las 00:00 y las 00:50 el servicio "en curso" arrancaba hasta la
    # noche y tres pruebas fallaban solo a esa hora.
    inicio = ahora - timedelta(minutes=50)
    servicio, j = _dia_de_hoy(cliente, sesion, datos,
                              hora=inicio.strftime("%H:%M:00"),
                              escolta=escolta, fecha=inicio.date())
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code in (200, 201), r.text
    r = marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)
    assert r.status_code in (200, 201), r.text
    return servicio, j


def _placa_suburban(datos):
    return datos["suburban"]["placa"]


# ================================================================ las reglas

def test_la_placa_se_compara_sin_espacios_ni_guiones():
    assert reglas.normal_placa(" abc-1234 ") == "ABC1234"
    assert reglas.normal_placa("") is None
    assert reglas.normal_placa(None) is None


def test_una_unidad_de_pegasus_se_lee_sin_nombre_ni_vin():
    cuando = datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)
    e = reglas.estado_de_la_unidad(unidad(
        55, "ABC-1234", cuando, lat=19.4, lon=-99.1, mph=31.07,
        ign=False, ign_desde=cuando - timedelta(hours=3)))
    assert e["pegasus_id"] == 55
    assert e["placa_normal"] == "ABC1234"
    assert e["velocidad_kmh"] == 50
    assert e["en_movimiento"] is True
    assert e["encendida"] is False
    assert e["encendida_desde"] == cuando - timedelta(hours=3)
    assert e["odometro_km"] == 48210.0
    # Lo que no se guarda nunca: el nombre de la unidad, el VIN, el IMEI.
    assert not {"name", "nombre", "vin", "imei"} & set(e)


def test_el_equipo_sin_encendido_dice_que_no_se_sabe():
    cuando = datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)
    e = reglas.estado_de_la_unidad(unidad(56, "RTX4E21", cuando,
                                          con_encendido=False))
    assert e["encendida"] is None
    assert e["en_movimiento"] is False


def test_el_equipo_que_manda_ceros_y_unos_tambien_se_entiende():
    """Hay equipos que mandan el encendido y la corriente como 0/1 o como
    texto. Un 0 no es "no se sabe": es apagada."""
    cuando = datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)
    u = unidad(57, "ABC1234", cuando)
    data = u["device"]["latest"]["data"]
    data["io_ign"]["value"] = 0
    data["io_pwr"]["value"] = "1"
    data["jamm_detected"]["value"] = 0
    e = reglas.estado_de_la_unidad(u)
    assert (e["encendida"], e["corriente"], e["inhibidor"]) == (False, True, False)
    data["io_ign"]["value"] = "a veces"
    assert reglas.estado_de_la_unidad(u)["encendida"] is None


def test_la_cuenta_de_la_gasolina_es_la_del_deposito():
    """212 km en una SUV Blindada de 5.5 km/l, a $24.50 y 20 % de
    holgura: al entero de arriba, como el deposito."""
    assert reglas.cuenta_gasolina(212, "5.5", "24.50", "20") == Decimal("1134")
    assert reglas.cuenta_gasolina(300, "5.5", "24.50", "20") == Decimal("1604")


def test_el_camino_de_la_unidad():
    # Parada a 29 km con 40 minutos: ya tendria que haber salido.
    estado, motivo = reglas.evaluar_camino(29_000, None, None, 40, False, True)
    assert estado == "no_sale" and "apagada" in motivo
    # Parada a 29 km con hora y media: todavia no.
    assert reglas.evaluar_camino(29_000, None, None, 90, False, True)[0] == "quieta"
    # Se acerca y le alcanza.
    assert reglas.evaluar_camino(18_000, 20_000, 2, 70, True, False)[0] == "viene"
    # En el punto no dice nada del camino.
    assert reglas.evaluar_camino(600, None, None, 10, False, True)[0] == "en_el_punto"


def test_el_fin_no_cuadra_si_la_unidad_se_guardo_lejos_y_antes():
    marca = datetime(2026, 9, 22, 23, 10)
    assert reglas.veredicto_fin(marca, datetime(2026, 9, 22, 21, 32),
                                14_000, None) == "alerta"
    # Estacionada donde estaba el principal: normal.
    assert reglas.veredicto_fin(marca, datetime(2026, 9, 22, 21, 32),
                                300, None) == "ok"
    # Guardada hace poco: todavia no.
    assert reglas.veredicto_fin(marca, datetime(2026, 9, 22, 22, 55),
                                14_000, None) == "ok"


# ================================================================ la lectura

def test_un_sitio_que_no_existe_se_dice_y_no_truena(db):
    """El sitio mal escrito no llega a Pegasus: se dice en la pantalla,
    en vez de tronar la lectura cada dos minutos."""
    import httpx
    from app import pegasus as conexion

    def sin_sitio(peticion):
        raise httpx.ConnectError("Name or service not known", request=peticion)

    cliente = conexion.Pegasus("https://no-existe.invalid", "u", "c")
    cliente.http = httpx.Client(transport=httpx.MockTransport(sin_sitio))
    with pytest.raises(conexion.NoResponde, match="PEGASUS_SITIO"):
        cliente.grupos()

    # Aunque sea la primera vuelta, la pantalla dice por que no hay lectura.
    r = gps.leer(db, cliente, datetime.now(timezone.utc))
    assert "PEGASUS_SITIO" in r["error"]
    grupos = db.query(m.GrupoGps).all()
    assert {g.nombre for g in grupos} == {"2025 P.E.", "CENTAURO BRASIL"}
    assert all("PEGASUS_SITIO" in g.error for g in grupos)


def test_si_pegasus_pide_esperar_no_se_le_pide_nada(db):
    """Un 429 se respeta hasta la hora que diga Pegasus: seguir pidiendo
    despues de un 429 hace que bloquee la IP."""
    import time as reloj_real

    import httpx
    from app import pegasus as conexion

    llamadas = []

    def sitio(peticion):
        llamadas.append(peticion.url.path)
        if peticion.url.path.endswith("/login"):
            return httpx.Response(200, json={"auth": "sesion"})
        return httpx.Response(429, headers={
            "X-RateLimit-Reset": str(int(reloj_real.time()) + 120)})

    conexion.quitar_pausa("https://cuota.invalid")
    try:
        cliente = conexion.Pegasus("https://cuota.invalid", "u", "c")
        cliente.http = httpx.Client(transport=httpx.MockTransport(sitio))
        with pytest.raises(conexion.NoResponde, match="bajar el ritmo"):
            cliente.grupos()
        antes = len(llamadas)
        otro = conexion.Pegasus("https://cuota.invalid", "u", "c")
        otro.http = httpx.Client(transport=httpx.MockTransport(sitio))
        with pytest.raises(conexion.NoResponde, match="bajar el ritmo"):
            otro.grupos()
        assert len(llamadas) == antes          # ni siquiera salio
        r = gps.leer(db, otro, datetime.now(timezone.utc))
        assert "bajar el ritmo" in r["error"]
        assert len(llamadas) == antes
    finally:
        conexion.quitar_pausa("https://cuota.invalid")
        conexion._sesiones.clear()


def test_sin_usuario_de_pegasus_no_hace_nada(db):
    assert gps.leer(db) == {"conectado": False}
    assert gps.cerrar_dias(db) == {"conectado": False}


def test_se_ligan_por_placa_y_lo_que_no_liga_dice_por_que(
        cliente, sesion, datos, db, pegasus):
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [
        unidad(101, "ABC1234", ahora),            # es la ABC-1234
        unidad(102, "", ahora),                   # sin placa
        unidad(103, "ZZZ-999", ahora),            # no esta en Centauro
        unidad(104, "DEF-1111", ahora),           # dos veces en Pegasus
        unidad(105, "def1111", ahora),
        unidad(106, "JKL3333", ahora - timedelta(days=3)),   # sin senal
    ]
    r = gps.leer(db, pegasus, ahora)
    assert r["conectado"] and not r.get("error"), r

    ligadas = {u.pegasus_id: u.vehiculo_id for u in db.query(m.UnidadGps).all()}
    abc = next(v["id"] for v in datos["vehiculos"] if v["placa"] == "ABC-1234")
    assert ligadas[101] == abc
    assert ligadas[102] is None and ligadas[103] is None
    assert ligadas[104] is None and ligadas[105] is None

    r = cliente.get(f"/gps/unidades?pais_id={datos['mx']['id']}",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["cifras"]["en_pegasus"] == 6
    assert d["cifras"]["ligadas"] == 2           # ABC-1234 y JKL-3333
    assert d["cifras"]["sin_ligar_pegasus"] == 4
    assert d["cifras"]["sin_senal"] == 1
    assert d["sin_placa"] == [102]
    motivos = {f["pegasus_id"]: f["motivo"] for f in d["unidades"]
               if f["tipo"] == "pegasus"}
    assert motivos == {102: "sin_placa", 103: "no_esta", 104: "repetida",
                       105: "repetida"}
    # Las de Centauro sin GPS tambien se dicen.
    assert any(f["gps"] == "sin_gps" for f in d["unidades"])
    # Y la pantalla no dice donde esta ninguna.
    assert not any("lat" in f or "lon" in f for f in d["unidades"])


def test_solo_lee_los_grupos_de_proteccion_ejecutiva(db, pegasus):
    gps.leer(db, pegasus, datetime.now(timezone.utc))
    assert 1 not in pegasus.leidos
    assert GRUPO_MX in pegasus.leidos
    assert {g.nombre for g in db.query(m.GrupoGps).all()} <= {
        "2025 P.E.", "CENTAURO BRASIL"}


def test_la_pantalla_la_ve_monitoreo_y_no_finanzas(cliente, sesion, datos):
    pais = datos["mx"]["id"]
    for quien in ("consultor", "central", "diroperaciones", "dirgeneral"):
        r = cliente.get(f"/gps/unidades?pais_id={pais}", headers=sesion(quien))
        assert r.status_code == 200, (quien, r.text)
    r = cliente.get(f"/gps/unidades?pais_id={pais}", headers=sesion("finanzas"))
    assert r.status_code == 403


# ================================================================ el panico

def _panico(pegasus, vid, cuando, lat=19.43, lon=-99.16):
    pegasus.eventos_.append({"vid": vid, "event_time": texto(cuando),
                             "label": "panic", "code": 10, "type": 10,
                             "lat": lat, "lon": lon, "mph": 0})


def test_el_panico_del_vehiculo_suena_una_vez_con_su_servicio(
        cliente, sesion, datos, db, pegasus):
    servicio, j = _en_curso(cliente, sesion, datos, escolta=True)
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [
        unidad(101, _placa_suburban(datos), ahora, lat=19.43, lon=-99.16)]
    _panico(pegasus, 101, ahora - timedelta(minutes=1))

    r = gps.leer(db, pegasus, ahora)
    assert r["panicos"] == 1, r
    # La segunda vuelta y el aviso de Pegasus no la repiten.
    assert gps.leer(db, pegasus, ahora + timedelta(minutes=2))["panicos"] == 0
    assert gps.revisar_panicos(db, pegasus,
                               ahora + timedelta(minutes=3))["panicos"] == 0

    alertas = db.query(m.AlertaIncidencia).all()
    assert len(alertas) == 1
    a = alertas[0]
    assert a.canal == m.CanalAlerta.BOTON_VEHICULO
    assert a.jornada_id == j["id"]
    assert a.reporta_persona_id == datos["personal"]["Juan Ramirez"]["id"]

    tablero = cliente.get("/central/tablero", headers=sesion("central")).json()
    ficha = tablero["roto"]["panico"][0]
    assert ficha["canal"] == "boton_vehiculo"
    assert ficha["placa"] == _placa_suburban(datos)
    assert {p["nombre"] for p in ficha["a_bordo"]} == {"Juan Ramirez",
                                                        "Luis Mendoza"}
    assert ficha["unidad"]["estado"] in ("detenida", "en_movimiento")
    assert ficha["principal"]["estado"] == "a_bordo"


def test_el_panico_se_revisa_seguido_en_servicio_y_de_todas_cada_tanto(
        cliente, sesion, datos, db, pegasus):
    """La cuota de eventos de Pegasus es de todo el sitio de Centauro
    Satelital. En cada vuelta se revisa el panico de las unidades en
    servicio; el de todas, cada quince minutos."""
    servicio, j = _en_curso(cliente, sesion, datos)
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, _placa_suburban(datos), ahora),
                                   unidad(102, "ZZZ999", ahora)]

    def panicos_pedidos():
        return [u for e, u in pegasus.pedidos if e == reglas.PANICO]

    gps.leer(db, pegasus, ahora)                      # primer barrido
    assert panicos_pedidos()[-1] == {101, 102}
    gps.leer(db, pegasus, ahora + timedelta(minutes=2))
    assert panicos_pedidos()[-1] == {101}             # solo la de servicio
    gps.leer(db, pegasus, ahora + timedelta(minutes=16))
    assert panicos_pedidos()[-1] == {101, 102}        # otro barrido

    # Un panico de la que no esta en servicio suena en el barrido.
    _panico(pegasus, 102, ahora + timedelta(minutes=17))
    gps.leer(db, pegasus, ahora + timedelta(minutes=18))
    assert db.query(m.AlertaIncidencia).count() == 0
    gps.leer(db, pegasus, ahora + timedelta(minutes=32))
    assert db.query(m.AlertaIncidencia).count() == 1


def test_el_panico_sin_servicio_tambien_suena(db, pegasus, datos):
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, "ABC1234", ahora)]
    _panico(pegasus, 101, ahora - timedelta(minutes=1))
    assert gps.leer(db, pegasus, ahora)["panicos"] == 1
    a = db.query(m.AlertaIncidencia).one()
    assert a.jornada_id is None and a.vehiculo_id is not None
    assert "no trae servicio" in a.descripcion


# ================================================================ inhibidor y corriente

def test_el_inhibidor_suena_en_servicio_y_se_resuelve_solo(
        cliente, sesion, datos, db, pegasus):
    servicio, j = _en_curso(cliente, sesion, datos)
    ahora = datetime.now(timezone.utc)
    placa = _placa_suburban(datos)
    pegasus.unidades_[GRUPO_MX] = [unidad(
        101, placa, ahora, lat=19.43, lon=-99.16, jam=True,
        jam_desde=ahora - timedelta(minutes=3))]
    gps.leer(db, pegasus, ahora)
    alertas = db.query(m.Alerta).filter_by(tipo=m.TipoAlerta.INHIBIDOR).all()
    assert len(alertas) == 1 and alertas[0].jornada_id == j["id"]

    tablero = cliente.get("/central/tablero", headers=sesion("central")).json()
    assert tablero["roto"]["hay"]
    suya = tablero["roto"]["unidad"][0]
    assert suya["tipo"] == "inhibidor" and suya["placa"] == placa
    assert suya["unidad"]["estado"] == "inhibidor"

    # Otra vuelta con el inhibidor puesto: no se repite.
    gps.leer(db, pegasus, ahora + timedelta(minutes=2))
    assert db.query(m.Alerta).filter_by(tipo=m.TipoAlerta.INHIBIDOR).count() == 1

    # Se quita: se resuelve sola.
    pegasus.unidades_[GRUPO_MX] = [unidad(
        101, placa, ahora + timedelta(minutes=4), lat=19.43, lon=-99.16)]
    gps.leer(db, pegasus, ahora + timedelta(minutes=4))
    db.expire_all()
    alerta = db.query(m.Alerta).filter_by(tipo=m.TipoAlerta.INHIBIDOR).one()
    assert alerta.atendida and "Se resolvio sola" in alerta.resolucion


def test_con_inhibidor_la_unidad_se_calla_y_se_dice_por_que(db, pegasus):
    """Un inhibidor calla al equipo. A los diez minutos la unidad ya "no
    reporta", pero lo que se dice sigue siendo el inhibidor."""
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(
        101, "ABC1234", ahora - timedelta(minutes=25), jam=True,
        jam_desde=ahora - timedelta(minutes=25))]
    gps.leer(db, pegasus, ahora)
    dice = gps.linea(db.query(m.UnidadGps).one(), None, ahora)
    assert dice["estado"] == "inhibidor"
    # Hoy, o ayer si la prueba corre justo despues de medianoche.
    assert dice["desde_dias"] in (0, 1)


def test_sin_servicio_el_inhibidor_es_de_centauro_satelital(db, pegasus):
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, "ABC1234", ahora, jam=True)]
    gps.leer(db, pegasus, ahora)
    assert db.query(m.Alerta).count() == 0


def test_la_corriente_cortada_espera_dos_minutos(
        cliente, sesion, datos, db, pegasus):
    servicio, j = _en_curso(cliente, sesion, datos)
    ahora = datetime.now(timezone.utc)
    placa = _placa_suburban(datos)
    pegasus.unidades_[GRUPO_MX] = [unidad(
        101, placa, ahora, lat=19.43, lon=-99.16, pwr=False,
        pwr_desde=ahora - timedelta(minutes=1))]
    gps.leer(db, pegasus, ahora)
    assert db.query(m.Alerta).filter_by(
        tipo=m.TipoAlerta.SIN_CORRIENTE).count() == 0

    gps.leer(db, pegasus, ahora + timedelta(minutes=3))
    assert db.query(m.Alerta).filter_by(
        tipo=m.TipoAlerta.SIN_CORRIENTE).count() == 1


# ================================================================ el camino

def test_la_unidad_contesta_por_quien_va_manejando(
        cliente, sesion, datos, db, pegasus):
    """Maneja y no toca el telefono: la unidad viene hacia el punto, no
    suena nada y no se le toca el telefono."""
    from app import central, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    estar = _estar(db, j)
    placa = _placa_suburban(datos)

    for minutos, km in ((82, 20), (80, 18)):
        local = estar - timedelta(minutes=minutos)
        lat, lon = a_km(km)
        pegasus.unidades_[GRUPO_MX] = [unidad(
            101, placa, utc(local) - timedelta(seconds=20), lat=lat, lon=lon,
            mph=25)]
        gps.leer(db, pegasus, utc(local))

    via = db.query(m.Trayecto).filter_by(jornada_id=j["id"]).one()
    assert via.unidad_estado == "viene"

    # El telefono no contesto, y aun asi no se cobra el silencio.
    r = trayecto.pulsar(db, ahora=estar - timedelta(minutes=60))
    assert r["silencios"] == 0
    db.expire_all()
    assert db.query(m.Alerta).filter_by(jornada_id=j["id"]).count() == 0

    camino = central.camino(db, estar - timedelta(minutes=79))
    fila = next(f for f in camino["gente"] if f["jornada_id"] == j["id"])
    assert fila["estado"] == "en_camino"
    assert fila["unidad"]["placa"] == placa
    assert fila["unidad"]["estado"] == "viene"


def test_la_unidad_no_ha_salido_aunque_el_telefono_diga_que_va(
        cliente, sesion, datos, db, pegasus):
    """Viene, pero sin la camioneta: el telefono se acerca y la unidad
    sigue apagada a 29 km."""
    from app import central, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    estar = _estar(db, j)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    local = estar - timedelta(minutes=40)

    lat, lon = a_km(8)
    trayecto.registrar(db, j["id"], juan, lat, lon,
                       ahora=local - timedelta(minutes=5))
    lat, lon = a_km(29)
    pegasus.unidades_[GRUPO_MX] = [unidad(
        101, _placa_suburban(datos), utc(local), lat=lat, lon=lon, ign=False,
        ign_desde=utc(local) - timedelta(hours=7))]
    gps.leer(db, pegasus, utc(local))

    camino = central.camino(db, local)
    fila = next(f for f in camino["gente"] if f["jornada_id"] == j["id"])
    assert fila["estado"] == "no_sale"
    assert fila["unidad"]["apagada"] is True
    # Cada testigo con lo suyo: el telefono a 8 km, la unidad a 29.
    assert fila["distancia_km"] == pytest.approx(8, abs=0.3)
    assert fila["unidad"]["distancia_km"] == pytest.approx(29, abs=0.3)
    alerta = db.query(m.Alerta).filter_by(jornada_id=j["id"]).one()
    assert "ya tendria que haber salido" in alerta.mensaje


def test_la_unidad_sin_senal_no_inventa_nada(
        cliente, sesion, datos, db, pegasus):
    from app import central

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    estar = _estar(db, j)
    local = estar - timedelta(minutes=60)
    lat, lon = a_km(29)
    pegasus.unidades_[GRUPO_MX] = [unidad(
        101, _placa_suburban(datos), utc(local) - timedelta(minutes=40),
        lat=lat, lon=lon, ign=False)]
    gps.leer(db, pegasus, utc(local))
    via = db.query(m.Trayecto).filter_by(jornada_id=j["id"]).one()
    assert via.unidad_estado == "sin_senal"
    fila = next(f for f in central.camino(db, local)["gente"]
                if f["jornada_id"] == j["id"])
    assert fila["estado"] == "esperando"


# ================================================================ el testigo

def test_el_segundo_testigo_de_la_llegada_y_del_fin(
        cliente, sesion, datos, db, pegasus):
    from app import bitacora

    servicio, j = _en_curso(cliente, sesion, datos)
    placa = _placa_suburban(datos)
    llegada = (db.query(m.Hito).filter_by(jornada_id=j["id"],
               tipo=m.TipoHito.LLEGADA_ORIGEN).one())
    ahora = datetime.now(timezone.utc)
    marca = utc(llegada.marcado_en)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, placa, ahora,
                                          lat=19.43, lon=-99.16)]
    pegasus.eventos_ += [
        {"vid": 101, "event_time": texto(marca - timedelta(seconds=40)),
         "label": "trckpnt", "lat": float(DENTRO["lat"]) + 0.0008,
         "lon": float(DENTRO["lon"]), "mph": 0},
        {"vid": 101, "event_time": texto(marca - timedelta(minutes=30)),
         "label": "trckpnt", "lat": a_km(12)[0], "lon": a_km(12)[1],
         "mph": 30},
    ]
    gps.leer(db, pegasus, ahora)
    db.expire_all()
    llegada = db.get(m.Hito, llegada.id)
    assert llegada.unidad_distancia_m is not None
    assert llegada.unidad_distancia_m < 200
    assert gps.testimonio(llegada)["veredicto"] == "ok"

    # El fin: la unidad se guardo a 14 km, hora y media antes de la marca.
    fin_local = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=5)
    guardada = utc(fin_local) - timedelta(minutes=98)
    lat14, lon14 = a_km(14)
    pegasus.tramos_ = [
        {"vid": 101, "moving": True, "start_time": texto(guardada - timedelta(minutes=30)),
         "end_time": texto(guardada), "distance": 14_000,
         "start_lat": ORIGEN_LAT, "start_lon": ORIGEN_LON},
        {"vid": 101, "moving": False, "start_time": texto(guardada),
         "end_time": None, "distance": 0,
         "start_lat": lat14, "start_lon": lon14},
    ]
    r = marcar_fin(cliente, sesion("juan"), j["id"], fin_local)
    assert r.status_code in (200, 201), r.text
    gps.leer(db, pegasus, utc(fin_local) + timedelta(minutes=3))
    db.expire_all()
    fin = (db.query(m.Hito).filter_by(jornada_id=j["id"],
           tipo=m.TipoHito.FIN_SERVICIO).one())
    assert fin.unidad_guardada_m > 13_000
    dice = gps.testimonio(fin)
    assert dice["veredicto"] == "alerta" and dice["guardada_en"]

    renglones = bitacora.del_dia(db, j["id"])["renglones"]
    del_fin = next(r for r in renglones if r.get("hito_id") == fin.id)
    assert del_fin["unidad"]["veredicto"] == "alerta"

    obs = gps.observaciones(db, [db.get(m.Jornada, j["id"])], [])
    assert [o["clave"] for o in obs] in (["fin"], ["fin_extra"])
    assert obs[0]["nivel"] == "revisar"


def test_lo_firmado_a_mano_no_tiene_testigo(cliente, sesion, datos, db,
                                            pegasus):
    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, _placa_suburban(datos), ahora)]
    hito = m.Hito(jornada_id=j["id"],
                  persona_id=datos["personal"]["Juan Ramirez"]["id"],
                  tipo=m.TipoHito.LLEGADA_ORIGEN,
                  marcado_en=datetime.now() - timedelta(minutes=10),
                  registrado_a_mano_en=datetime.now())
    db.add(hito)
    db.commit()
    gps.leer(db, pegasus, ahora)
    db.refresh(hito)
    assert hito.unidad_revisada_en is not None
    assert gps.testimonio(hito) is None


# ================================================================ el dia

def test_los_kilometros_del_dia_y_su_manejo(cliente, sesion, datos, db,
                                            pegasus):
    servicio, j = _en_curso(cliente, sesion, datos)
    placa = _placa_suburban(datos)
    fin_local = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=2)
    r = marcar_fin(cliente, sesion("juan"), j["id"], fin_local)
    assert r.status_code in (200, 201), r.text
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, placa, ahora)]
    gps.leer(db, pegasus, ahora)

    llegada = utc(db.query(m.Hito).filter_by(
        jornada_id=j["id"], tipo=m.TipoHito.LLEGADA_ORIGEN).one().marcado_en)
    fin = utc(fin_local)

    def tramo(movimiento, ini, fin_, km):
        return {"vid": 101, "moving": movimiento, "start_time": texto(ini),
                "end_time": texto(fin_), "distance": km * 1000,
                "start_lat": ORIGEN_LAT, "start_lon": ORIGEN_LON}

    pegasus.tramos_ = [
        tramo(False, llegada - timedelta(hours=10), llegada - timedelta(minutes=90), 0),
        tramo(True, llegada - timedelta(minutes=90), llegada - timedelta(minutes=5), 30),
        tramo(False, llegada - timedelta(minutes=5), llegada + timedelta(minutes=5), 0),
        tramo(True, llegada + timedelta(minutes=5), fin - timedelta(minutes=5), 20),
        tramo(False, fin - timedelta(minutes=5), fin + timedelta(minutes=5), 0),
        tramo(True, fin + timedelta(minutes=5), fin + timedelta(minutes=40), 14),
        tramo(False, fin + timedelta(minutes=40), fin + timedelta(hours=10), 0),
    ]
    pegasus.eventos_ = [
        {"vid": 101, "event_time": texto(llegada - timedelta(minutes=30)), "label": "spd"},
        {"vid": 101, "event_time": texto(llegada + timedelta(minutes=10)), "label": "posac"},
        {"vid": 101, "event_time": texto(fin + timedelta(minutes=10)), "label": "spd"},
        {"vid": 101, "event_time": texto(fin + timedelta(hours=3)), "label": "spd"},
        {"vid": 101, "event_time": texto(llegada), "label": "aggdrv"},
    ]
    # Antes de dos horas no se cierra: la unidad puede no haberse guardado.
    assert gps.cerrar_dias(db, pegasus, fin + timedelta(minutes=30))["cerrados"] == 0
    r = gps.cerrar_dias(db, pegasus, fin + timedelta(hours=3))
    assert r["cerrados"] == 1, r
    a = db.query(m.AsignacionVehiculo).filter_by(jornada_id=j["id"]).one()
    assert float(a.km_gps) == 64.0
    assert (a.excesos_gps, a.bruscos_gps) == (2, 1)


def _dia_terminado(db, datos, cliente, sesion, km, excesos=0, bruscos=0,
                   escolta=True):
    servicio, j = _dia_de_hoy(cliente, sesion, datos, escolta=escolta)
    jor = db.get(m.Jornada, j["id"])
    jor.estatus = m.EstatusJornada.TERMINADA
    jor.fin_real = jor.fin_programado
    a = jor.vehiculos[0]
    a.km_gps, a.excesos_gps, a.bruscos_gps = km, excesos, bruscos
    a.gps_cerrado_en = datetime.now(timezone.utc)
    db.commit()
    return servicio, j


def test_el_manejo_es_de_quien_maneja(cliente, sesion, datos, db):
    from app import profesionalismo

    _dia_terminado(db, datos, cliente, sesion, km=1240, excesos=9, bruscos=6)
    juan = profesionalismo.ficha(db, datos["personal"]["Juan Ramirez"]["id"])
    manejo = next(d for d in juan["dimensiones"] if d["dimension"] == "manejo")
    assert manejo["aplica"]
    assert manejo["valor"] == pytest.approx(100 - 3 * 15 / 1.24, abs=0.1)
    assert manejo["peso_base"] == 10.0

    luis = profesionalismo.ficha(db, datos["personal"]["Luis Mendoza"]["id"])
    suyo = next(d for d in luis["dimensiones"] if d["dimension"] == "manejo")
    assert not suyo["aplica"]


def _gasolina(db, j, persona_id, depositado, tickets):
    viatico = m.AsignacionViatico(
        jornada_id=j["id"], persona_id=persona_id,
        escenario=m.EscenarioViatico.FULL_DAY_LOCAL, monto_total=depositado,
        monto_comprobado=sum(tickets), moneda=m.Moneda.MXN,
        estatus=m.EstatusViatico.EN_COMPROBACION)
    db.add(viatico)
    db.flush()
    db.add(m.ConceptoAsignado(asignacion_id=viatico.id,
                              concepto=m.ConceptoViatico.COMBUSTIBLE,
                              monto=depositado,
                              origen=m.OrigenMonto.TABULADOR))
    for monto in tickets:
        db.add(m.Comprobante(asignacion_id=viatico.id,
                             concepto=m.ConceptoViatico.COMBUSTIBLE,
                             tipo=m.TipoComprobante.FACTURA, monto=monto))
    db.commit()
    return viatico


def test_la_gasolina_contra_los_kilometros(cliente, sesion, datos, db):
    servicio, j = _dia_terminado(db, datos, cliente, sesion, km=212,
                                 escolta=False)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _gasolina(db, j, juan, 1604, [830, 774])
    viaticos = db.query(m.AsignacionViatico).filter_by(jornada_id=j["id"]).all()

    cuenta = gps.gasolina_de(db, viaticos)
    assert cuenta["excede"]
    assert cuenta["comprobado"] == Decimal("1604")
    assert cuenta["km"] == Decimal("212.0")

    obs = gps.observaciones(db, [db.get(m.Jornada, j["id"])], viaticos)
    assert [o["clave"] for o in obs] == ["gasolina"]
    assert obs[0]["nivel"] == "revisar" and obs[0]["persona_id"] == juan


def test_sin_los_km_del_gps_no_se_compara_la_gasolina(cliente, sesion, datos,
                                                      db):
    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _gasolina(db, j, juan, 1604, [1600])
    viaticos = db.query(m.AsignacionViatico).filter_by(jornada_id=j["id"]).all()
    assert gps.gasolina_de(db, viaticos) is None


# ================================================================ el aviso y la app

def test_el_aviso_de_pegasus_solo_despierta_la_revision(
        cliente, datos, db, pegasus, monkeypatch):
    from app.config import settings

    # Sin secreto la ruta no existe.
    assert cliente.post("/gps/pegasus/aviso/abc").status_code == 404

    monkeypatch.setattr(settings, "pegasus_secreto_aviso", "s3cr3t0-largo")
    monkeypatch.setattr(gps.conexion, "desde_la_configuracion",
                        lambda: pegasus)
    assert cliente.post("/gps/pegasus/aviso/otro").status_code == 404

    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, "ABC1234", ahora)]
    gps.leer(db, pegasus, ahora - timedelta(minutes=5))
    _panico(pegasus, 101, ahora - timedelta(minutes=1))
    r = cliente.post("/gps/pegasus/aviso/s3cr3t0-largo", json={"lo": "que sea"})
    assert r.status_code == 202, r.text
    assert r.json()["panicos"] == 1
    # El cuerpo del aviso no se cree: la alerta sale de lo que se leyo.
    a = db.query(m.AlertaIncidencia).one()
    assert a.origen.startswith("pegasus:101:")


def test_la_app_le_dice_al_conductor_que_su_unidad_tiene_gps(
        cliente, sesion, datos, db, pegasus):
    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, _placa_suburban(datos), ahora)]
    gps.leer(db, pegasus, ahora)
    r = cliente.get("/campo/mi-dia", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    hoy = r.json()
    fichas = hoy.get("hoy") or hoy.get("jornadas") or []
    if isinstance(fichas, dict):
        fichas = [fichas]
    suya = next(f for f in fichas if f.get("jornada_id") == j["id"])
    assert suya["unidades"][0]["gps"] is True
    assert suya["unidades"][0]["mia"] is True

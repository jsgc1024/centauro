"""Los tres candados de la app: geocerca, ventana de horario y secuencia."""
from datetime import datetime, timedelta

from ayudas import (DENTRO, LEJOS, asignar, configurar_origen, crear_servicio,
                    jornada, manana, marcar)


def _preparar(cliente, sesion, datos, dia_offset=30):
    h = sesion("consultor")
    dia = manana(dia_offset)
    servicio = crear_servicio(cliente, h, datos,
                              [jornada(dia, datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    return j


def test_geocerca_rechaza_llegada_lejos_del_origen(cliente, sesion, datos):
    j = _preparar(cliente, sesion, datos, 30)
    inicio = datetime.fromisoformat(j["inicio_programado"])

    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=5), ubicacion=LEJOS)

    assert r.status_code == 409
    detalle = r.json()["detail"]
    assert detalle["distancia_metros"] > 2000
    assert detalle["limite_metros"] == 250


def test_geocerca_deja_pasar_dentro_del_radio(cliente, sesion, datos):
    j = _preparar(cliente, sesion, datos, 31)
    inicio = datetime.fromisoformat(j["inicio_programado"])

    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=5), ubicacion=DENTRO)

    assert r.status_code == 200
    assert r.json()["dentro_geocerca"] is True
    assert r.json()["distancia_origen_m"] < 250


def test_marca_fuera_de_horario_pasa_pero_queda_para_revision(cliente, sesion, datos):
    j = _preparar(cliente, sesion, datos, 32)
    inicio = datetime.fromisoformat(j["inicio_programado"])

    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(hours=3))

    assert r.status_code == 200
    assert r.json()["requiere_revision"] is True

    alertas = cliente.get("/operacion/alertas", headers=sesion("central")).json()
    assert any(a["tipo"] == "fuera_de_ventana" for a in alertas)


def test_no_se_puede_iniciar_sin_haber_llegado(cliente, sesion, datos):
    j = _preparar(cliente, sesion, datos, 33)
    inicio = datetime.fromisoformat(j["inicio_programado"])

    r = marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)

    assert r.status_code == 409
    assert "llegada" in r.json()["detail"].lower()


def test_el_contacto_avisa_al_cliente_con_enlace_que_expira(cliente, sesion, datos):
    j = _preparar(cliente, sesion, datos, 34)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    h = sesion("juan")

    marcar(cliente, h, j["id"], "llegada_origen", inicio - timedelta(minutes=10))
    marcar(cliente, h, j["id"], "contacto_ejecutivo", inicio)

    bitacora = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                           headers=sesion("central")).json()
    avisos = bitacora["notificaciones"]
    al_solicitante = [n for n in avisos if n["para"] == "solicitante"]
    al_ejecutivo = [n for n in avisos if n["para"] == "ejecutivo"]

    assert al_solicitante and al_ejecutivo
    con_enlace = [n for n in al_solicitante if n["enlace"]]
    assert con_enlace, "el solicitante debe recibir el enlace de seguimiento"
    assert con_enlace[0]["expira"] is not None, "el enlace debe expirar"


def test_tablero_lista_lo_que_falta_antes_de_iniciar(cliente, sesion, datos):
    h = sesion("consultor")
    # Dentro de la ventana de dos horas
    inicio = datetime.now() + timedelta(minutes=45)
    servicio = crear_servicio(cliente, h, datos, [jornada(
        inicio.date(), datos["modalidades"]["full_day"]["id"],
        hora=inicio.strftime("%H:%M:%S"))])
    j = servicio["equipos"][0]["jornadas"][0]

    tablero = cliente.get("/operacion/tablero-proximos", headers=sesion("central")).json()
    fila = next(f for f in tablero if f["jornada_id"] == j["id"])
    assert fila["listo"] is False
    assert any("personal" in p.lower() for p in fila["pendientes"])
    assert any("vehiculo" in p.lower() for p in fila["pendientes"])


def test_aviso_de_horas_extra_llega_a_los_dos_destinatarios(cliente, sesion, datos):
    j = _preparar(cliente, sesion, datos, 35)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    fin = datetime.fromisoformat(j["fin_programado"])
    h = sesion("juan")

    marcar(cliente, h, j["id"], "llegada_origen", inicio - timedelta(minutes=10))
    marcar(cliente, h, j["id"], "contacto_ejecutivo", inicio)

    simulado = (fin - timedelta(minutes=25)).isoformat()
    r = cliente.post(f"/operacion/avisar-horas-extra?ahora={simulado}",
                     headers=sesion("central"))
    assert r.status_code == 200
    assert len(r.json()["avisos"]) == 1

    bitacora = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                           headers=sesion("central")).json()
    avisos = [n for n in bitacora["notificaciones"]
              if "horas extra" in n["asunto"].lower()]
    destinatarios = {n["para"] for n in avisos}
    assert destinatarios == {"solicitante", "ejecutivo"}


def test_alerta_cuando_el_conductor_deja_de_reportar(cliente, sesion, datos):
    j = _preparar(cliente, sesion, datos, 36)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    h = sesion("juan")

    marcar(cliente, h, j["id"], "llegada_origen", inicio - timedelta(minutes=10))
    marcar(cliente, h, j["id"], "contacto_ejecutivo", inicio)

    simulado = (inicio + timedelta(hours=5)).isoformat()
    r = cliente.post(f"/operacion/revisar-standby?ahora={simulado}",
                     headers=sesion("central"))
    assert r.status_code == 200
    generadas = r.json()["alertas_generadas"]
    assert len(generadas) == 1
    assert generadas[0]["horas_sin_reporte"] >= 4

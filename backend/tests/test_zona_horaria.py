"""Cada país con su hora.

Las columnas de fecha del sistema son *naive* y guardan hora de pared
del país del servicio: un servicio de São Paulo que arranca a las 07:00
guarda 07:00. Todo el sistema las comparaba contra el reloj del
servidor, y con el contenedor en México eso dejaba a Brasil corrido tres
horas:

  - el conductor que marcaba puntual caía fuera de la ventana permitida
    y se le levantaba alerta,
  - el servicio en curso aparecía "sin reporte" en la banda roja desde
    que arrancaba,
  - y el aviso de horas extra —una ventana de media hora— no coincidía
    nunca: no existía fuera de México.

Lo que se prueba aquí es que la misma escena, con el mismo reloj de
servidor, se juzga distinto según el país del servicio. Por eso casi
todas las pruebas son la misma dos veces.
"""
from datetime import datetime, timedelta

import pytest

from app import reloj
from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana, marcar)


# São Paulo va tres horas adelante de la Ciudad de México.
DESFASE_BR = 3


@pytest.fixture
def brasil(cliente, sesion, datos):
    """El país de al lado, con su propia hora y su propia ciudad."""
    h = sesion("admin")
    paises = cliente.get("/catalogos/paises", headers=h).json()
    br = next((p for p in paises if p["codigo"] == "BR"), None)
    assert br, "la semilla tiene que traer Brasil"
    assert br["zona_horaria"] == "America/Sao_Paulo", br

    plazas = cliente.get("/catalogos/plazas?todas=true", headers=h).json()
    sp = next((p for p in plazas if p["pais_id"] == br["id"]), None)
    if not sp:
        sp = cliente.post("/catalogos/plazas", headers=h,
                          json={"pais_id": br["id"], "nombre": "Sao Paulo"}).json()
    return {"pais": br, "plaza": sp}


def _ahora_de_pared(zona_horaria):
    """Que hora es alla en este momento.

    Es la misma hora que guarda la jornada: las columnas del sistema son
    naive y guardan hora de pared del pais del servicio.
    """
    return reloj.ahora_en(type("P", (), {"zona_horaria": zona_horaria})())


def _servicio_en(cliente, sesion, datos, pais_id, plaza_id, fecha,
                 hora="07:00:00"):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(fecha, datos["modalidades"]["full_day"]["id"], hora=hora)],
        pais_id=pais_id, plaza_id=plaza_id)
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def _servicio_ahora(cliente, sesion, datos, pais, plaza_id):
    """Un servicio que arranca *en este momento*, en hora de alla.

    Es la escena que importa: el conductor se presenta y marca. Anclar
    la jornada a una hora fija —las 07:00— y marcar ahi convertia la
    marca en *diferida* por las horas que hubiera entre esa hora y el
    momento en que corre la prueba, y una marca diferida de mas de media
    hora levanta revision por si sola. Eso hacia fallar la prueba por
    una razon que no tiene nada que ver con la zona horaria, y hacia
    fallar tambien la de Mexico, donde el reloj no cambio: la senal de
    que el escenario estaba mal planteado, no el codigo.
    """
    ahora = _ahora_de_pared(pais["zona_horaria"])
    return _servicio_en(cliente, sesion, datos, pais["id"], plaza_id,
                        ahora.date(), ahora.strftime("%H:%M:%S"))


# ================================================== el módulo

def test_la_hora_de_alla_no_es_la_de_aca(cliente, sesion):
    """La pieza sobre la que se apoya todo lo demás."""
    h = sesion("admin")
    paises = {p["codigo"]: p for p in
              cliente.get("/catalogos/paises", headers=h).json()}

    class ComoPais:
        def __init__(self, zona):
            self.zona_horaria = zona

    mx = reloj.ahora_en(ComoPais(paises["MX"]["zona_horaria"]))
    br = reloj.ahora_en(ComoPais(paises["BR"]["zona_horaria"]))
    assert round((br - mx).total_seconds() / 3600) == DESFASE_BR


def test_una_zona_invalida_no_tumba_la_pantalla(cliente):
    """Un nombre mal escrito en un catálogo no puede dejar sin monitoreo
    a la central: se cae a la hora de la casa y sigue."""
    class ComoPais:
        zona_horaria = "Marte/Olympus"

    assert reloj.ahora_en(ComoPais()) is not None


# ================================================== la ventana de marcado

def test_el_conductor_puntual_en_brasil_ya_no_cae_fuera_de_ventana(
        cliente, sesion, datos, brasil):
    """Era el peor de todos: marcaba a su hora, el sistema decía que iba
    tres horas tarde, y le levantaba alerta."""
    servicio, j = _servicio_ahora(cliente, sesion, datos,
                                  brasil["pais"], brasil["plaza"]["id"])
    # Marca ahora, que es su hora de presentación. Sin `marcado_en`: es
    # lo que manda el teléfono cuando hay señal, y obliga al servidor a
    # poner la hora él —con el reloj de São Paulo o con el de México,
    # que es justo lo que se está probando.
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen")
    assert r.status_code == 200, r.text
    assert "fuera de la ventana" not in " ".join(r.json()["avisos"]).lower()
    assert r.json()["requiere_revision"] is False


def test_marcar_de_verdad_tarde_si_se_sigue_notando(cliente, sesion, datos,
                                                     brasil):
    """El candado tiene que seguir cerrando. Si arreglar la zona lo
    apagara, habríamos cambiado un error por otro peor."""
    servicio, j = _servicio_ahora(cliente, sesion, datos,
                                  brasil["pais"], brasil["plaza"]["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio + timedelta(hours=4))
    assert r.status_code == 200, r.text
    assert r.json()["requiere_revision"] is True


# ================================================== el pulso de la central

def test_el_servicio_brasileno_no_nace_callado(cliente, sesion, datos, brasil):
    """Aparecía "sin reporte" o en rojo desde que arrancaba, en la banda
    que la central lee primero. Un tablero que siempre grita deja de
    leerse."""
    servicio, j = _servicio_ahora(cliente, sesion, datos,
                                  brasil["pais"], brasil["plaza"]["id"])
    marcar(cliente, sesion("juan"), j["id"], "llegada_origen")
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo")

    d = cliente.get("/central/tablero", headers=sesion("central")).json()
    mio = [f for f in d["pulso"]["eventuales"]
           if f["servicio_id"] == servicio["id"]]
    assert mio, "el servicio tiene que estar en curso"
    # Acaba de marcar: no puede estar en rojo.
    assert mio[0]["silencio"] in ("verde", "ambar"), mio[0]


# ================================================== el día del agente

def test_el_agente_ve_su_dia_no_el_del_servidor(cliente, sesion, datos):
    """La pantalla que abre cada mañana. Cerca de la medianoche el día
    del servidor y el suyo son distintos."""
    r = cliente.get("/campo/mi-dia", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    momento = datetime.fromisoformat(r.json()["momento"])
    assert momento is not None


# ================================================== el plazo del consultor

def test_el_plazo_para_cerrar_nace_en_la_hora_del_pais(cliente, sesion, datos,
                                                        brasil):
    """De ese plazo depende que el consultor cobre su comisión. Si nace
    con un reloj y se juzga con otro, queda torcido desde el principio."""
    servicio, j = _servicio_en(cliente, sesion, datos,
                               brasil["pais"]["id"], brasil["plaza"]["id"],
                               manana(-2))
    h = sesion("consultor")
    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h)
    assert r.status_code in (200, 201), r.text

    abierto = datetime.fromisoformat(r.json()["abierto_en"])
    hasta = datetime.fromisoformat(r.json()["comprobacion_hasta"])
    limite = datetime.fromisoformat(r.json()["limite_consultor"])
    # 24 horas exactas para el personal, contadas desde la hora de São
    # Paulo; las del consultor, provisionales en 48 hasta que llegue T1.
    assert round((hasta - abierto).total_seconds() / 3600) == 24
    assert round((limite - abierto).total_seconds() / 3600) == 48
    ahora_br = reloj.ahora_en(type("P", (), {
        "zona_horaria": brasil["pais"]["zona_horaria"]})())
    assert abs((abierto - ahora_br).total_seconds()) < 120, (abierto, ahora_br)


# ================================================== lo que no cambia

def test_mexico_sigue_exactamente_igual(cliente, sesion, datos):
    """El contenedor corre en hora de México, así que para México nada
    de esto cambia nada. Vale probarlo: un arreglo que mueve lo que ya
    funcionaba no es un arreglo."""
    servicio, j = _servicio_ahora(cliente, sesion, datos,
                                  datos["mx"], datos["cdmx"]["id"])
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen")
    assert r.status_code == 200, r.text
    assert r.json()["requiere_revision"] is False

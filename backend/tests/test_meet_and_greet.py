# -*- coding: utf-8 -*-
"""El meet and greet: lo que enciende el servicio, y lo que lo apaga.

Hasta hoy el eventual saltaba de `asignado` a `cerrado` sin pasar por
`en_curso` ni por `terminado`: dos estados que existían en el catálogo y
que no escribía nadie. En la cartera del consultor, un servicio con el
equipo ya con el principal se veía igual que uno que todavía no sale.

Y si el equipo llegaba pero nadie marcaba desde la app —sin batería, sin
señal, o simplemente se pasó— no había forma de dejarlo asentado. Existía
`ajustar` (corrige la hora de una marca que existe) y `cerrar el día a
mano` (cierra el día), pero nada que registrara un contacto que nunca se
marcó.

El candado del registro a mano es el mismo que el de cerrar un día:
central y dirección, nunca el consultor. Esa hora fija `inicio_real`, de
donde salen las horas extra que se le facturan al cliente.
"""
from datetime import datetime, timedelta

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana, marcar, marcar_fin)


def _servicio(cliente, sesion, datos, dias=1, tipo="eventual", offset=0,
              atras=0):
    """`atras` pone el servicio en el pasado, que es lo unico que se
    puede cerrar: un dia se cierra cuando ya paso."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset - atras + i),
                 datos["modalidades"]["full_day"]["id"],
                 # Sin punto de inicio el servicio no sale de borrador:
                 # `programacion.evaluar` lo pide para promoverlo. Un
                 # decorado sin esto deja al servicio en un estatus que
                 # la operacion real nunca tiene a estas alturas.
                 origen_direccion="Las Alcobas, Polanco - lobby")
         for i in range(dias)],
        tipo=tipo)
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
    return servicio


def _estatus(cliente, sesion, servicio_id):
    return cliente.get(f"/servicios/{servicio_id}",
                       headers=sesion("consultor")).json()["estatus"]


# ============================================================ el verde

def test_el_eventual_se_enciende_con_el_meet_and_greet(cliente, sesion, datos):
    """Antes solo se encendía el implantado. El eventual se quedaba en
    `asignado` hasta que finanzas aprobaba el cierre, así que la cartera
    no distinguía un servicio corriendo de uno que todavía no sale."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    assert _estatus(cliente, sesion, servicio["id"]) == "asignado"

    assert marcar(cliente, sesion("juan"), j["id"],
                  "llegada_origen").status_code == 200
    assert _estatus(cliente, sesion, servicio["id"]) == "arribado", \
        "llegar al punto no es estar con el principal, pero tampoco es " \
        "seguir esperando el dia"

    assert marcar(cliente, sesion("juan"), j["id"],
                  "contacto_ejecutivo").status_code == 200
    assert _estatus(cliente, sesion, servicio["id"]) == "en_curso"


def test_llegar_al_punto_deja_el_dia_arribado_y_no_en_curso(cliente, sesion,
                                                            datos):
    """Llegar y esperar veinte minutos a que el ejecutivo baje no es
    tener el servicio corriendo. Decisión de Salvador, 20 sep.

    Hasta hoy la llegada encendía `en_curso` y la central perdía de
    vista ese rato —que es el último en el que todavía se puede hacer
    algo si el equipo no está donde debería—.
    """
    from app import models as m
    from app.db import SessionLocal

    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    def estatus_del_dia():
        with SessionLocal() as db:
            return db.get(m.Jornada, j["id"]).estatus

    assert marcar(cliente, sesion("juan"), j["id"],
                  "llegada_origen").status_code == 200
    assert estatus_del_dia() == m.EstatusJornada.ARRIBADO

    assert marcar(cliente, sesion("juan"), j["id"],
                  "contacto_ejecutivo").status_code == 200
    assert estatus_del_dia() == m.EstatusJornada.EN_CURSO


def test_el_que_llego_y_espera_sigue_contando_como_en_la_calle(cliente, sesion,
                                                               datos):
    """Lo único que cambia es lo que dice la pantalla.

    Si `arribado` no contara como arrancado, alguien parado en la calle
    desaparecería del monitoreo justo en el rato en que nadie sabe nada
    de él. Aquí se prueba por el panorama, que es donde la dirección lo
    ve.
    """
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    assert marcar(cliente, sesion("juan"), j["id"],
                  "llegada_origen").status_code == 200

    p = cliente.get("/panorama", headers=sesion("dirgeneral")).json()
    assert p["en_la_calle"]["personas"] >= 1, p["en_la_calle"]
    suyo = next((b for tira in p["dia"] for b in tira["barras"]
                 if b["jornada_id"] == j["id"]), None)
    assert suyo is not None, p["dia"]
    assert suyo["estatus"] == "arribado"
    # Y se le mide el silencio: es justo de quien nadie sabe nada.
    assert suyo["silencio"] is not None


def test_la_cartera_dice_que_el_equipo_ya_esta_en_el_punto(cliente, sesion,
                                                           datos):
    """Salvador miraba la cartera con su gente ya parada allá y leía
    "asignado", que es lo mismo que dice un servicio que todavía no
    sale. El servicio pasa por arribado antes de en curso."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    assert _estatus(cliente, sesion, servicio["id"]) == "asignado"
    marcar(cliente, sesion("juan"), j["id"], "llegada_origen")
    assert _estatus(cliente, sesion, servicio["id"]) == "arribado"
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo")
    assert _estatus(cliente, sesion, servicio["id"]) == "en_curso"


def test_un_dia_que_llego_y_nunca_hizo_contacto_se_puede_terminar(
        cliente, sesion, datos):
    """El principal nunca bajó, o nadie marcó el contacto. El día se
    cierra igual y el servicio tiene que poder terminar: si `arribado`
    no estuviera en la lista, ese servicio se quedaría abierto para
    siempre sin que nadie supiera por qué."""
    from app import models as m
    from app.db import SessionLocal

    servicio = _servicio(cliente, sesion, datos, atras=1)
    j = servicio["equipos"][0]["jornadas"][0]
    juan = sesion("juan")

    # Cada marca a la hora de SU dia: con la hora en que corre la
    # prueba, el fin de un dia de ayer quedaria antes de su inicio.
    arranca = datetime.fromisoformat(j["inicio_programado"])
    marcar(cliente, juan, j["id"], "llegada_origen",
           arranca - timedelta(minutes=10))
    assert _estatus(cliente, sesion, servicio["id"]) == "arribado"

    r = marcar_fin(cliente, juan, j["id"],
                   datetime.fromisoformat(j["fin_programado"]))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert (db.get(m.Jornada, j["id"]).estatus
                == m.EstatusJornada.TERMINADA)
    assert _estatus(cliente, sesion, servicio["id"]) == "terminado"


def test_el_implantado_sigue_encendiendo_igual(cliente, sesion, datos):
    """El renglón es el mismo para los dos tipos desde hoy. Esta prueba
    existe para que ampliarlo al eventual no le haya cambiado nada al
    implantado, que ya funcionaba así."""
    servicio = _servicio(cliente, sesion, datos, tipo="implantado")
    j = servicio["equipos"][0]["jornadas"][0]

    # La secuencia manda: no hay contacto con el ejecutivo sin haber
    # llegado al punto.
    assert marcar(cliente, sesion("juan"), j["id"],
                  "llegada_origen").status_code == 200
    assert marcar(cliente, sesion("juan"), j["id"],
                  "contacto_ejecutivo").status_code == 200
    assert _estatus(cliente, sesion, servicio["id"]) == "en_curso"


# ============================================================ el café

def test_el_eventual_termina_al_cerrar_su_ultimo_dia(cliente, sesion, datos):
    """Y no antes. En un servicio de tres días, cerrar el primero no lo
    termina: el equipo sigue en la calle los otros dos."""
    servicio = _servicio(cliente, sesion, datos, dias=3, atras=3)
    dias = servicio["equipos"][0]["jornadas"]
    juan = sesion("juan")

    for i, j in enumerate(dias):
        # Cada marca a la hora de SU dia. Con la hora en que corre la
        # prueba, el fin de un dia de hace tres quedaria antes de su
        # propio inicio.
        arranca = datetime.fromisoformat(j["inicio_programado"])
        marcar(cliente, juan, j["id"], "llegada_origen",
               arranca - timedelta(minutes=10))
        marcar(cliente, juan, j["id"], "contacto_ejecutivo", arranca)
        r = marcar_fin(cliente, juan, j["id"],
                       datetime.fromisoformat(j["fin_programado"]))
        assert r.status_code == 200, f"no cerro el dia {i + 1}: {r.text}"

        esperado = "terminado" if i == len(dias) - 1 else "en_curso"
        assert _estatus(cliente, sesion, servicio["id"]) == esperado, \
            f"tras cerrar el dia {i + 1} de {len(dias)}"


def test_el_implantado_no_se_termina_al_cerrar_su_ultimo_dia(cliente, sesion,
                                                             datos):
    """Es continuo: sus jornadas se generan mes con mes. Cerrar la última
    de octubre no quiere decir que el servicio terminó, quiere decir que
    falta generar noviembre. Apagarlo ahí sería apagar un servicio con
    gente en la calle."""
    servicio = _servicio(cliente, sesion, datos, tipo="implantado", atras=1)
    j = servicio["equipos"][0]["jornadas"][0]
    juan = sesion("juan")

    arranca = datetime.fromisoformat(j["inicio_programado"])
    marcar(cliente, juan, j["id"], "llegada_origen",
           arranca - timedelta(minutes=10))
    marcar(cliente, juan, j["id"], "contacto_ejecutivo", arranca)
    marcar_fin(cliente, juan, j["id"],
               datetime.fromisoformat(j["fin_programado"]))

    assert _estatus(cliente, sesion, servicio["id"]) == "en_curso"


# ================================================= el registro a mano

def test_la_central_registra_el_meet_and_greet_que_nadie_marco(cliente,
                                                               sesion, datos):
    """El caso de verdad: el cliente confirmó por teléfono que el equipo
    está con él, y en el sistema no hay marca."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    cuando = datetime.fromisoformat(j["inicio_programado"])
    despues = (cuando + timedelta(hours=1)).isoformat()

    # Los dos puntos, en el orden en que ocurren: primero llegó al punto
    # y después quedó con el ejecutivo. El servidor exige ese orden
    # también cuando la marca la pone la central.
    for tipo, momento in (("llegada_origen", cuando - timedelta(minutes=10)),
                          ("contacto_ejecutivo", cuando)):
        r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                         headers=sesion("central"),
                         json={"tipo": tipo,
                               "persona_id":
                                   datos["personal"]["Juan Ramirez"]["id"],
                               "momento": momento.isoformat(),
                               "justificacion":
                                   "El cliente confirmó por teléfono"},
                         params={"ahora": despues})
        assert r.status_code == 200, (tipo, r.text)
    assert r.json()["estatus_servicio"] == "en_curso"

    # Y queda sellado: el día lo dice, para siempre.
    d = cliente.get(f"/operacion/jornadas/{j['id']}/dia",
                    headers=sesion("central")).json()
    assert d["meet_and_greet"]["hay"] is True
    assert d["meet_and_greet"]["a_mano"] is True
    assert d["meet_and_greet"]["firmado_por"]
    assert "teléfono" in d["meet_and_greet"]["motivo"]

    # Y se distingue en la bitácora de quien marcó desde la calle.
    suyo = next(x for x in d["renglones"]
                if x["fuente"] == "hito" and x["titulo"] == "contacto_ejecutivo")
    assert suyo["marca"] == "a mano"


def test_el_consultor_no_puede_registrarlo(cliente, sesion, datos):
    """Es quien vende el servicio y a quien más le conviene que un día
    aparezca trabajado. Ve el panel; no escribe en él."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                     headers=sesion("consultor"),
                     json={"tipo": "contacto_ejecutivo",
                           "persona_id":
                               datos["personal"]["Juan Ramirez"]["id"],
                           "momento": j["inicio_programado"],
                           "justificacion": "me lo dijo el cliente"})
    assert r.status_code == 403, r.text

    # Y la pantalla lo sabe antes de dibujar el botón.
    d = cliente.get(f"/operacion/jornadas/{j['id']}/dia",
                    headers=sesion("consultor")).json()
    assert d["puedo_registrar_a_mano"] is False
    d = cliente.get(f"/operacion/jornadas/{j['id']}/dia",
                    headers=sesion("central")).json()
    assert d["puedo_registrar_a_mano"] is True


def test_no_se_registra_dos_veces(cliente, sesion, datos):
    """Si ya hay marca, lo que se corrige es la hora —ajustar el hito—,
    no se apila otra encima."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    assert marcar(cliente, sesion("juan"), j["id"],
                  "llegada_origen").status_code == 200
    assert marcar(cliente, sesion("juan"), j["id"],
                  "contacto_ejecutivo").status_code == 200

    r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                     headers=sesion("central"),
                     json={"tipo": "contacto_ejecutivo",
                           "persona_id":
                               datos["personal"]["Juan Ramirez"]["id"],
                           "momento": j["inicio_programado"],
                           "justificacion": "por si las dudas"})
    assert r.status_code == 409, r.text


def test_no_se_registra_una_hora_que_no_ha_llegado(cliente, sesion, datos):
    """Registrar por adelantado es dar fe de algo que todavía no pasa, y
    esa hora se factura."""
    servicio = _servicio(cliente, sesion, datos, offset=3)
    j = servicio["equipos"][0]["jornadas"][0]

    # La llegada, no el contacto: así lo que la rechaza es la hora que
    # todavía no llega, y no la falta de una marca previa.
    r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                     headers=sesion("central"),
                     json={"tipo": "llegada_origen",
                           "persona_id":
                               datos["personal"]["Juan Ramirez"]["id"],
                           "momento": j["inicio_programado"],
                           "justificacion": "adelantando trabajo"})
    assert r.status_code == 409, r.text
    assert "todavia no llega" in r.json()["detail"]["mensaje"], r.text


def test_nadie_se_firma_su_propio_meet_and_greet(cliente, sesion, datos):
    """El mismo candado que cerrar a mano un día que uno trabajó."""
    from app import models as m
    from app.db import SessionLocal

    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    # Se le presta el día a quien tiene el permiso: la central.
    db = SessionLocal()
    try:
        usuario = (db.query(m.Usuario)
                   .filter_by(correo="central@centauro.lat").one())
        asignacion = (db.query(m.AsignacionPersonal)
                      .filter_by(jornada_id=j["id"]).first())
        asignacion.persona_id = usuario.persona_id
        db.commit()
    finally:
        db.close()

    r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                     headers=sesion("central"),
                     json={"tipo": "contacto_ejecutivo", "persona_id": 1,
                           "momento": j["inicio_programado"],
                           "justificacion": "me firmo a mi mismo"})
    assert r.status_code == 403, r.text


def test_el_servicio_cotizado_y_autorizado_tambien_enciende(cliente, sesion,
                                                            datos):
    """El hueco que encontró la batería el 20 de septiembre.

    La cotización autorizada deja el servicio en `autorizado`. La lista
    que enciende el servicio con el contacto miraba sólo `planeado` y
    `asignado`, así que un servicio con su cotización firmada —que es el
    camino normal— se trabajaba, se cerraba el día, y en la cartera
    seguía viéndose como uno que todavía no sale.
    """
    from app import models as m
    from app.db import SessionLocal

    servicio = _servicio(cliente, sesion, datos)

    # Se pone en `autorizado` a mano porque llegar ahi con el equipo ya
    # armado no se puede: asignar recursos lo promueve a `asignado`. En
    # la calle pasa al reves --se autoriza la cotizacion y despues se
    # arma el equipo-- y basta que nadie vuelva a tocar el servicio para
    # que se quede aqui. Lo que se prueba es que desde este estatus el
    # servicio tambien enciende.
    with SessionLocal() as db:
        s = db.get(m.Servicio, servicio["id"])
        s.estatus = m.EstatusServicio.AUTORIZADO
        db.commit()
    assert _estatus(cliente, sesion, servicio["id"]) == "autorizado"

    j = servicio["equipos"][0]["jornadas"][0]
    assert marcar(cliente, sesion("juan"), j["id"],
                  "llegada_origen").status_code == 200
    assert _estatus(cliente, sesion, servicio["id"]) == "arribado"

    assert marcar(cliente, sesion("juan"), j["id"],
                  "contacto_ejecutivo").status_code == 200
    assert _estatus(cliente, sesion, servicio["id"]) == "en_curso"

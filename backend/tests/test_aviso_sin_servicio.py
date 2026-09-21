"""Un aviso que no es sobre un servicio.

`Notificacion.servicio_id` era obligatorio, y con eso el sistema no sabía
mandar nada que no colgara de un servicio: ni la invitación de acceso de
alguien que acaba de entrar a la empresa, ni el enlace de "olvidé mi
contraseña", ni un aviso a administración. Por eso esos dos los sigue
entregando una persona a mano desde el panel.

Es la tercera tabla con la misma suposición metida —*"todo lo que pasa
aquí pasa dentro de un servicio"*—. `RegistroAccion` la tenía, y por eso
nació `RegistroAdmin`. Aquí se quitó en vez de hacer otra tabla: un aviso
a una persona y un aviso sobre un servicio son la misma cosa saliendo por
el mismo canal, y partirlos habría dejado dos bandejas que revisar.

Lo que **no** cambia: nada sale todavía. El envío real no existe —el
modelo lo dice desde el principio: "en el demo se registra; el envío real
se conecta después"— así que el enlace de recuperación lo sigue
entregando administración. Lo que se quitó es la traba de diseño, no el
trabajo de conectar un proveedor.
"""
import uuid

import pytest

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, jornada, manana)


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _aviso(db, correo, servicio_id=None, jornada_id=None):
    from app import models as m
    fila = m.Notificacion(
        servicio_id=servicio_id, jornada_id=jornada_id,
        destinatario=(m.Destinatario.COLABORADOR if servicio_id is None
                      else m.Destinatario.SOLICITANTE),
        canal=m.Canal.CORREO, correo=correo,
        asunto="Crea tu contraseña",
        cuerpo="Alguien de administración te dio acceso al sistema.")
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def test_un_aviso_a_una_persona_se_guarda_sin_servicio(db):
    """La traba, vista de frente: antes esto reventaba con una violación
    de llave no nula."""
    from app import models as m

    correo = f"{uuid.uuid4().hex[:8]}@centauro.lat"
    fila = _aviso(db, correo)

    assert fila.servicio_id is None
    assert fila.jornada_id is None
    assert fila.servicio is None
    assert fila.destinatario == m.Destinatario.COLABORADOR

    guardado = db.get(m.Notificacion, fila.id)
    assert guardado.correo == correo


def test_el_colaborador_no_es_un_papel_del_servicio(db):
    """Los cinco destinatarios de antes son papeles dentro de un
    servicio: quien lo pidió, quien lo recibe, la central, el consultor,
    el personal. El nuevo es una persona a secas, y por eso hacía falta:
    mandarle su contraseña a alguien como "personal" diría que el aviso
    es sobre una jornada suya, y no lo es."""
    from app import models as m

    assert m.Destinatario.COLABORADOR.value == "colaborador"
    assert m.Destinatario.COLABORADOR not in (
        m.Destinatario.SOLICITANTE, m.Destinatario.EJECUTIVO,
        m.Destinatario.CENTRAL, m.Destinatario.CONSULTOR,
        m.Destinatario.PERSONAL)


def test_borrar_un_servicio_no_se_lleva_los_avisos_ajenos(cliente, sesion,
                                                          datos, db):
    """El riesgo que abre hacer la columna opcional.

    El borrado completo limpia las notificaciones del servicio. Si lo
    hiciera a lo ancho, se llevaría de paso las que no son de ningún
    servicio —que son justo las que nadie va a echar de menos hasta que
    alguien pregunte por qué no le llegó su invitación—.
    """
    from app import models as m

    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(40), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])

    del_servicio = _aviso(db, "cliente@ejemplo.com",
                          servicio_id=servicio["id"]).id
    de_nadie = _aviso(db, "nuevo@centauro.lat").id

    r = cliente.request("DELETE", f"/servicios/{servicio['id']}",
                        json={"motivo": "Se capturo al cliente equivocado"},
                        headers=h)
    assert r.status_code == 200, r.text

    # Se pregunta por consulta y no con `db.get`. La sesion de la prueba
    # sigue trayendo las dos filas en su mapa de identidad, y `get` sobre
    # una que el borrado se llevo revienta con ObjectDeletedError en vez
    # de contestar "ya no esta", que es lo que aqui se quiere saber.
    db.rollback()

    def existe(fila_id):
        return (db.query(m.Notificacion.id)
                .filter_by(id=fila_id).first()) is not None

    assert not existe(del_servicio), "el aviso del servicio se quedo colgando"
    assert existe(de_nadie), "se llevo un aviso que no era suyo"
    assert (db.query(m.Notificacion)
            .filter_by(id=de_nadie).one().correo) == "nuevo@centauro.lat"


def test_los_avisos_del_servicio_siguen_colgando_de_el(cliente, sesion, datos,
                                                       db):
    """Que la columna admita nulo no afloja lo de siempre: el aviso de
    "su equipo llegó al punto de origen" se sigue viendo en la bitácora
    de esa jornada, que es donde se busca."""
    from ayudas import marcar
    from datetime import datetime, timedelta

    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(0), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])

    inicio = datetime.fromisoformat(j["inicio_programado"])
    assert marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200

    bitacora = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                           headers=sesion("central")).json()
    assert bitacora["notificaciones"], "el aviso de la jornada se perdio"

# -*- coding: utf-8 -*-
"""La bitácora del día: cuatro fuentes en una sola columna.

Lo que el cliente dictó, lo que el equipo marcó, lo que el sistema
alertó y lo que la central tocó a mano. Cada cosa vivía en su tabla y en
su pantalla; nadie podía ver las cuatro juntas ordenadas por hora, que
es la única forma de ver dónde el plan y la realidad se separaron.

Lo que estas pruebas cuidan, en orden: que las cuatro fuentes lleguen;
que el reloj mande; que una parada sin hora no se invente una; que el
rastreo del camino al punto NO entre; y que el registro de acciones
llegue filtrado y no entero.
"""
from datetime import datetime, timedelta

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana, marcar)


def _dia(cliente, sesion, datos, offset=0):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"],
                 origen_direccion="Las Alcobas, Polanco - lobby")])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def _bitacora(cliente, headers, jornada_id):
    r = cliente.get(f"/operacion/jornadas/{jornada_id}/dia",
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_las_cuatro_fuentes_caen_en_la_misma_columna(cliente, sesion, datos):
    """Una parada de la agenda, una marca del equipo y un movimiento de
    la central tienen que salir juntos, cada uno diciendo de dónde
    viene. Separados no se puede leer un día."""
    h = sesion("consultor")
    servicio, j = _dia(cliente, sesion, datos, 0)

    r = cliente.post(f"/operacion/jornadas/{j['id']}/agenda/paradas",
                     json={"hora": "09:00:00", "lugar": "oficinas corporativas",
                           "direccion": "Reforma 250, piso 12"}, headers=h)
    assert r.status_code == 201, r.text

    assert marcar(cliente, sesion("juan"), j["id"],
                  "llegada_origen").status_code == 200

    d = _bitacora(cliente, h, j["id"])
    fuentes = {r["fuente"] for r in d["renglones"] + d["sin_hora"]}
    assert "plan" in fuentes, "la agenda del cliente"
    assert "hito" in fuentes, "lo que el equipo marcó"
    # La carga de la agenda es una acción de la central y queda en el
    # hilo: quien lee el día ve cuándo entró esa parada.
    assert "central" in fuentes, "lo que alguien de la casa tocó"

    # Y cada renglón se puede dibujar: título siempre, el resto opcional.
    for renglon in d["renglones"] + d["sin_hora"]:
        assert renglon["titulo"]
        assert set(renglon) >= {"fuente", "momento", "titulo", "detalle",
                                "marca", "tono"}


def test_el_reloj_manda_y_lo_que_no_trae_hora_se_va_aparte(cliente, sesion,
                                                           datos):
    """Una parada sin hora es lo normal —el cliente no siempre la da— y
    colarla a medianoche sería inventarle un dato que nadie dio."""
    h = sesion("consultor")
    servicio, j = _dia(cliente, sesion, datos, 0)
    ruta = f"/operacion/jornadas/{j['id']}/agenda/paradas"

    for hora, lugar in (("14:00:00", "comida"),
                        ("09:00:00", "junta"),
                        (None, "cena")):
        cuerpo = {"lugar": lugar}
        if hora:
            cuerpo["hora"] = hora
        assert cliente.post(ruta, json=cuerpo, headers=h).status_code == 201

    d = _bitacora(cliente, h, j["id"])

    momentos = [r["momento"] for r in d["renglones"]]
    assert momentos == sorted(momentos), "la columna va por reloj"
    assert all(r["momento"] is None for r in d["sin_hora"])

    lugares = [r["titulo"] for r in d["sin_hora"]]
    assert "Cena" in lugares, "la parada sin hora se va al final y lo dice"
    assert "Cena" not in [r["titulo"] for r in d["renglones"]]


def test_la_bitacora_no_es_un_rastreo(cliente, sesion, datos):
    """Decisión de diseño, no omisión: las lecturas de posición del
    camino al punto existen para una decisión —reponer a alguien toma
    hora y media— y se apagan al marcar la llegada. Volcarlas aquí
    convertiría la bitácora en un historial de dónde anduvo la gente."""
    from app import models as m, trayecto
    from app.db import SessionLocal

    h = sesion("consultor")
    servicio, j = _dia(cliente, sesion, datos, 0)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    db = SessionLocal()
    try:
        trayecto.registrar(db, j["id"], juan,
                           lat=19.4540, lon=-99.1677,
                           ahora=datetime.now())
        assert db.query(m.LecturaTrayecto).count() >= 1, \
            "el decorado tiene que existir para que la prueba valga"
    finally:
        db.close()

    d = _bitacora(cliente, h, j["id"])
    titulos = " ".join(r["titulo"] or ""
                       for r in d["renglones"] + d["sin_hora"]).lower()
    assert "lectura" not in titulos
    assert not any(r["fuente"] == "trayecto"
                   for r in d["renglones"] + d["sin_hora"])


def test_del_registro_de_acciones_solo_pasa_lo_que_importa(cliente, sesion,
                                                           datos):
    """La bitácora de acciones guarda todo, abrir la pantalla incluido.
    Volcarla entera aquí sería cambiar una columna vacía por una
    ilegible."""
    from app import auditoria, bitacora, models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    servicio, j = _dia(cliente, sesion, datos, 0)

    # El decorado se siembra por la misma puerta que usa la operación
    # --`auditoria.registrar`-- y no a mano: una fila inventada no prueba
    # que el filtro sirva contra lo que el sistema escribe de verdad.
    db = SessionLocal()
    try:
        fila = db.get(m.Servicio, servicio["id"])
        usuario = (db.query(m.Usuario)
                   .filter_by(correo="ana.solis@centauro.lat").one())
        auditoria.registrar(db, usuario, fila, "ver tablero",
                            "alguien abrió la pantalla", jornada_id=j["id"])
        auditoria.registrar(db, usuario, fila, "cerrar dia a mano",
                            "nadie marcó el fin", jornada_id=j["id"])
        db.commit()

        d = bitacora.del_dia(db, j["id"])
        de_central = [r["titulo"] for r in d["renglones"] + d["sin_hora"]
                      if r["fuente"] == "central"]
        assert "cerrar dia a mano" in de_central
        assert "ver tablero" not in de_central, \
            "abrir una pantalla no es un movimiento del día"
    finally:
        db.close()


def test_todas_las_horas_son_del_pais_del_servicio(cliente, sesion, datos):
    """Lo que toco la central, las notas y las alertas se guardan como un
    instante, y salian con el reloj de la base: en UTC en desarrollo, en
    hora de Mexico en el servidor aunque el servicio fuera de Brasil. Van
    con la hora de pared del pais del servicio, como las marcas, y la
    bitacora dice cual es."""
    from datetime import timezone

    from app import auditoria, bitacora, models as m
    from app.db import SessionLocal

    servicio, j = _dia(cliente, sesion, datos, 0)
    # Un instante de UTC que en Mexico (UTC-6) cae a las 18:21 del dia
    # anterior: si alguien olvida convertir, se nota en la fecha tambien.
    instante = datetime(2026, 9, 24, 0, 21, tzinfo=timezone.utc)
    en_mexico = datetime(2026, 9, 23, 18, 21)

    db = SessionLocal()
    try:
        fila = db.get(m.Servicio, servicio["id"])
        usuario = (db.query(m.Usuario)
                   .filter_by(correo="ana.solis@centauro.lat").one())
        auditoria.registrar(db, usuario, fila, "cerrar dia a mano",
                            "nadie marco el fin", jornada_id=j["id"])
        db.flush()
        (db.query(m.RegistroAccion).filter_by(jornada_id=j["id"])
         .update({"creado_en": instante}))
        db.add(m.NotaBitacora(jornada_id=j["id"], persona_id=usuario.persona_id,
                              texto="Hablo el cliente", creada_en=instante))
        db.add(m.Alerta(jornada_id=j["id"], tipo=m.TipoAlerta.SIN_REPORTE,
                        mensaje="Sin reportar", creada_en=instante))
        db.commit()

        d = bitacora.del_dia(db, j["id"])
        assert d["hora_de"] == "Mexico"
        horas = {r["fuente"]: r["momento"] for r in d["renglones"]
                 if r["fuente"] in ("central", "nota", "alerta")}
        assert set(horas) == {"central", "nota", "alerta"}
        for fuente, momento in horas.items():
            assert datetime.fromisoformat(momento) == en_mexico, fuente
    finally:
        db.close()


def test_una_marca_diferida_ensena_las_dos_horas(cliente, sesion, datos):
    """La app puede marcar sin señal y mandar después. Hasta hoy esa
    diferencia no se enseñaba en ningún lado, y un día donde todo llega
    diferido no es un día bien reportado."""
    from app import bitacora, models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    # De ayer: asi la hora del servicio ya paso, sea cual sea la hora en
    # que corra la bateria. Con el dia de hoy, una prueba que corre a
    # las cinco de la manana marca en el futuro y el servidor le pone su
    # propia hora, que cae fuera de la ventana.
    servicio, j = _dia(cliente, sesion, datos, -1)

    # A la hora del servicio, no a la hora en que corre la prueba: una
    # marca fuera de la ventana del dia se rotula "fuera de ventana", y
    # ese rotulo pisa al de diferido a proposito --de los dos, el que
    # tiene que saltar es el que sale del horario contratado--. Marcando
    # cuando de verdad se marca, lo que queda a la vista es el diferido.
    assert marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  datetime.fromisoformat(j["inicio_programado"])
                  ).status_code == 200

    db = SessionLocal()
    try:
        hito = (db.query(m.Hito).filter_by(jornada_id=j["id"])
                .order_by(m.Hito.id.desc()).first())
        assert not hito.fuera_de_ventana, \
            "el decorado tiene que caer dentro de la ventana"
        hito.diferido = True
        hito.recibido_en = hito.marcado_en + timedelta(minutes=40)
        db.commit()

        d = bitacora.del_dia(db, j["id"])
        suyo = next(r for r in d["renglones"] if r["fuente"] == "hito")
        assert "40" in suyo["marca"], suyo["marca"]
        assert suyo["tono"] == "alerta"
        assert "recibido" in (suyo["detalle"] or ""), suyo["detalle"]
    finally:
        db.close()


def test_la_bitacora_pide_permiso(cliente, sesion, datos):
    """Es el día de un cliente: no se abre sin sesión."""
    servicio, j = _dia(cliente, sesion, datos, 0)
    r = cliente.get(f"/operacion/jornadas/{j['id']}/dia")
    assert r.status_code in (401, 403), r.status_code

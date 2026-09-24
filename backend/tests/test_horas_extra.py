# -*- coding: utf-8 -*-
"""Las horas extra (seccion 65).

Decisiones de Salvador, 24 de septiembre: las horas del dia corren desde
la presentacion, o desde el meet and greet si fue antes; se cuentan por
hora o fraccion, en minutos completos; la unidad no cobra hora extra; el
consultor corrige las horas de su servicio, con motivo, hasta su visto
bueno; en el implantado se cobran en la factura del mes.

Y lo que salio de la revision: el aviso de Brasil decia los minutos con
el reloj de Mexico, la central no veia a un equipo que ya estaba en
horas extra, y la hora de un dia ya trabajado se podia mover sin motivo
aun con la factura en Odoo.
"""
from datetime import date, datetime, timedelta

import pytest

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, jornada, manana, marcar, marcar_fin)

MOTIVO = "El cliente confirmo por telefono la hora de termino"


# ------------------------------------------------------------ ayudas

def _db():
    from app.db import SessionLocal
    return SessionLocal()


def _extras(jornada_id):
    from app import horas_extra
    from app import models as m
    with _db() as db:
        return horas_extra.horas(db.get(m.Jornada, jornada_id))


def _dia(cliente, sesion, datos, offset=300, contacto=0, fin=timedelta(0),
         modalidad="full_day"):
    """Un dia ejecutado por Juan con la Suburban, de Ana. `contacto` son
    minutos contra la presentacion y `fin` es contra el fin programado."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"][modalidad]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    termino = datetime.fromisoformat(j["fin_programado"])
    juan = sesion("juan")
    r = marcar(cliente, juan, j["id"], "llegada_origen",
               inicio + timedelta(minutes=min(contacto, 0) - 10))
    assert r.status_code in (200, 201), r.text
    r = marcar(cliente, juan, j["id"], "contacto_ejecutivo",
               inicio + timedelta(minutes=contacto))
    assert r.status_code in (200, 201), r.text
    r = marcar_fin(cliente, juan, j["id"], termino + fin)
    assert r.status_code in (200, 201), r.text
    j["inicio"], j["termino"] = inicio, termino
    return servicio, j


def _visto_bueno(cliente, sesion, servicio):
    h = sesion("consultor")
    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=h).json()
    r = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas",
                     headers=h)
    assert r.status_code == 200, r.text
    return cierre["cierre_id"]


def _hito(jornada_id, tipo):
    from app import models as m
    with _db() as db:
        return (db.query(m.Hito)
                .filter_by(jornada_id=jornada_id, tipo=m.TipoHito(tipo))
                .order_by(m.Hito.id).first().id)


def _corregir(cliente, sesion, j, quien="consultor", **horas):
    """Corrige las horas del dia con el reloj ya pasado el dia."""
    cuerpo = {"justificacion": horas.pop("motivo", MOTIVO)}
    for k, v in horas.items():
        cuerpo[k] = v.isoformat()
    ahora = (j["termino"] + timedelta(days=1)).isoformat()
    return cliente.post(f"/operacion/jornadas/{j['id']}/horas",
                        params={"ahora": ahora}, json=cuerpo,
                        headers=sesion(quien))


# ------------------------------------------------------------ la regla

@pytest.mark.parametrize("de_mas, horas", [
    (timedelta(0), 0),
    # Lo que se ve como 19:00 no genera nada: minutos completos.
    (timedelta(seconds=59), 0),
    # Un minuto de mas ya es una hora.
    (timedelta(minutes=1), 1),
    (timedelta(minutes=59), 1),
    (timedelta(minutes=61), 2),
])
def test_hora_o_fraccion_por_minutos_completos(cliente, sesion, datos, de_mas,
                                               horas):
    _, j = _dia(cliente, sesion, datos, fin=de_mas)
    assert _extras(j["id"]) == horas


def test_si_el_meet_and_greet_fue_antes_las_horas_corren_desde_ahi(
        cliente, sesion, datos):
    """Arranco con el ejecutivo una hora antes y termino a su hora
    programada: trece horas con el. Antes salian cero horas extra."""
    _, j = _dia(cliente, sesion, datos, contacto=-60)
    assert _extras(j["id"]) == 1


def test_si_el_ejecutivo_llega_tarde_la_espera_cuenta(cliente, sesion, datos):
    """El equipo estaba a la hora contratada: esperar al ejecutivo no le
    quita horas al dia."""
    _, j = _dia(cliente, sesion, datos, contacto=120, fin=timedelta(hours=2))
    assert _extras(j["id"]) == 2


def test_medio_dia_no_genera_horas_extra(cliente, sesion, datos):
    _, j = _dia(cliente, sesion, datos, modalidad="medio_dia",
                fin=timedelta(hours=3))
    assert _extras(j["id"]) == 0


def test_la_unidad_no_cobra_hora_extra(cliente, sesion, datos):
    from app import cierre, cotizacion
    from app import models as m
    servicio, _ = _dia(cliente, sesion, datos, fin=timedelta(hours=2))
    with _db() as db:
        s = db.get(m.Servicio, servicio["id"])
        c = cotizacion.vigente(db, s.id)
        eje = cierre.ejecutado(db, s, c.tarifario_id)
    persona = next(l for l in eje["detalle"] if l["tipo"] == "recurso")
    unidad = next(l for l in eje["detalle"] if l["tipo"] == "vehiculo")
    assert persona["horas_extra"] == 2
    assert float(persona["importe_horas_extra"]) == 640
    assert "horas_extra" not in unidad


def test_con_dos_meet_and_greet_cuenta_el_primero(cliente, sesion, datos):
    """Si dos del equipo marcan el contacto, el segundo no mueve la hora
    en que arranco el dia."""
    from app import models as m
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(305), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Luis Mendoza"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    for quien in ("juan", "luis"):
        marcar(cliente, sesion(quien), j["id"], "llegada_origen",
               inicio - timedelta(minutes=40))
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo",
           inicio - timedelta(minutes=30))
    marcar(cliente, sesion("luis"), j["id"], "contacto_ejecutivo",
           inicio - timedelta(minutes=10))
    with _db() as db:
        assert db.get(m.Jornada, j["id"]).inicio_real == \
            inicio - timedelta(minutes=30)


# ------------------------------------------------------------ el aviso y la central

@pytest.fixture
def brasil(cliente, sesion, datos):
    h = sesion("admin")
    paises = cliente.get("/catalogos/paises", headers=h).json()
    br = next(p for p in paises if p["codigo"] == "BR")
    plazas = cliente.get("/catalogos/plazas?todas=true", headers=h).json()
    sp = next((p for p in plazas if p["pais_id"] == br["id"]), None)
    if not sp:
        sp = cliente.post("/catalogos/plazas", headers=h,
                          json={"pais_id": br["id"], "nombre": "Sao Paulo"}).json()
    return {"pais": br, "plaza": sp}


def _corriendo(cliente, sesion, datos, zona="America/Mexico_City",
               pais_id=None, plaza_id=None, fin_en=20, adelanto=0,
               modalidad="full_day"):
    """Un dia corriendo ahora mismo, en la hora de alla. `fin_en` son los
    minutos que le faltan al fin programado; `adelanto`, cuanto antes de
    la presentacion fue el meet and greet."""
    from app import models as m
    from app import reloj
    ahora = reloj.ahora_en(type("P", (), {"zona_horaria": zona})())
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(ahora.date(), datos["modalidades"][modalidad]["id"],
                 hora=ahora.strftime("%H:%M:%S"))],
        pais_id=pais_id, plaza_id=plaza_id)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    marcar(cliente, sesion("juan"), j["id"], "llegada_origen")
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo")
    with _db() as db:
        jj = db.get(m.Jornada, j["id"])
        base = ahora.replace(microsecond=0)
        jj.fin_programado = base + timedelta(minutes=fin_en + adelanto)
        jj.inicio_real = jj.inicio_programado - timedelta(minutes=adelanto)
        db.commit()
        limite = jj.fin_programado - timedelta(minutes=adelanto)
    return servicio, j, limite


def test_el_aviso_de_brasil_dice_los_minutos_de_alla(cliente, sesion, datos,
                                                    brasil):
    """Con el reloj del servidor decia "faltam 199 minutos"."""
    from app import operacion
    _corriendo(cliente, sesion, datos, "America/Sao_Paulo",
               brasil["pais"]["id"], brasil["plaza"]["id"])
    with _db() as db:
        avisos = operacion.avisar_horas_extra(db)
    assert len(avisos) == 1
    assert 18 <= avisos[0]["faltan_minutos"] <= 20, avisos


def test_el_aviso_sale_contra_el_limite_si_arranco_antes(cliente, sesion,
                                                        datos):
    """El meet and greet fue una hora antes: las horas se cumplen una
    hora antes del fin programado, y el aviso sale para esa hora."""
    from app import operacion
    _, _, limite = _corriendo(cliente, sesion, datos, fin_en=20, adelanto=60)
    with _db() as db:
        avisos = operacion.avisar_horas_extra(db)
    assert len(avisos) == 1
    assert 18 <= avisos[0]["faltan_minutos"] <= 20, avisos


def test_la_central_ve_cuanto_lleva_en_horas_extra(cliente, sesion, datos):
    servicio, _, limite = _corriendo(cliente, sesion, datos, fin_en=-40)
    d = cliente.get("/central/tablero", headers=sesion("central")).json()
    fila = next(f for f in d["pulso"]["eventuales"]
                if f["servicio_id"] == servicio["id"])
    assert 38 <= fila["minutos_en_extra"] <= 41, fila
    assert fila["horas_extra_desde"] == f"{limite:%H:%M}"
    assert fila["por_entrar_en_extra"] is False


def test_un_medio_dia_no_sale_por_entrar_en_horas_extra(cliente, sesion, datos):
    servicio, _, _ = _corriendo(cliente, sesion, datos, fin_en=20,
                                modalidad="medio_dia")
    d = cliente.get("/central/tablero", headers=sesion("central")).json()
    fila = next(f for f in d["pulso"]["eventuales"]
                if f["servicio_id"] == servicio["id"])
    assert fila["por_entrar_en_extra"] is False
    assert fila["minutos_en_extra"] is None


# ------------------------------------------------------------ los candados

def test_un_dia_que_arranco_ya_no_cambia_su_hora_ni_su_modalidad(
        cliente, sesion, datos):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(320), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ruta = f"/servicios/jornadas/{j['id']}"

    # Antes de que llegue el equipo, la hora se mueve como siempre.
    r = cliente.patch(ruta, json={"hora_presentacion": "08:00:00"}, headers=h)
    assert r.status_code == 200, r.text
    inicio = datetime.fromisoformat(r.json()["inicio"])
    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))

    r = cliente.patch(ruta, json={"hora_presentacion": "09:00:00"}, headers=h)
    assert r.status_code == 409, r.text
    r = cliente.patch(ruta, json={
        "modalidad_id": datos["modalidades"]["medio_dia"]["id"]}, headers=h)
    assert r.status_code == 409, r.text
    # Lo que no toca las horas sigue igual, y repetir la misma hora no
    # es moverla.
    assert cliente.patch(ruta, json={"km_estimados": 210},
                         headers=h).status_code == 200
    assert cliente.patch(ruta, json={"hora_presentacion": "08:00:00"},
                         headers=h).status_code == 200


def test_el_vuelo_ya_no_mueve_la_presentacion_de_un_dia_que_arranco(
        cliente, sesion, datos):
    from app import models as m
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(330), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))

    r = cliente.patch(f"/operacion/jornadas/{j['id']}/vuelo", headers=h,
                      json={"vuelo_tipo": "llegada",
                            "vuelo_hora": (inicio + timedelta(hours=3))
                            .isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["presentacion_movida"] is False
    with _db() as db:
        jj = db.get(m.Jornada, j["id"])
        assert jj.inicio_programado == inicio
        assert jj.vuelo_hora == inicio + timedelta(hours=3)


def test_la_hora_de_manana_no_mueve_un_dia_que_ya_arranco(cliente, sesion,
                                                         datos):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(340), datos["modalidades"]["full_day"]["id"]),
         jornada(manana(341), datos["modalidades"]["full_day"]["id"])])
    uno, dos = servicio["equipos"][0]["jornadas"]
    for j in (uno, dos):
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
    marcar(cliente, sesion("juan"), dos["id"], "llegada_origen",
           datetime.fromisoformat(dos["inicio_programado"])
           - timedelta(minutes=10))
    r = cliente.post(f"/operacion/jornadas/{uno['id']}/hora-de-manana",
                     headers=sesion("central"), json={"hora": "10:00:00"})
    assert r.status_code == 409, r.text


def test_con_visto_bueno_ya_no_se_ajustan_las_marcas_de_las_horas(
        cliente, sesion, datos):
    """Reabrir el dia ya tenia este candado; ajustar la marca no, y la
    factura se iba a Odoo con unas horas y el sistema cambiaba a otras."""
    servicio, j = _dia(cliente, sesion, datos, offset=350,
                       fin=timedelta(hours=2))
    _visto_bueno(cliente, sesion, servicio)
    central = sesion("central")
    r = cliente.post(f"/operacion/hitos/{_hito(j['id'], 'fin_servicio')}/ajustar",
                     headers=central,
                     json={"nuevo_momento": (j["termino"] + timedelta(hours=5))
                           .isoformat(), "justificacion": MOTIVO})
    assert r.status_code == 409, r.text
    assert _extras(j["id"]) == 2
    # La llegada no mueve horas extra: esa se sigue ajustando.
    r = cliente.post(
        f"/operacion/hitos/{_hito(j['id'], 'llegada_origen')}/ajustar",
        headers=central,
        json={"nuevo_momento": (j["inicio"] - timedelta(minutes=5)).isoformat(),
              "justificacion": MOTIVO})
    assert r.status_code == 200, r.text


# ------------------------------------------------------------ la correccion

def test_el_consultor_corrige_el_fin_de_su_servicio(cliente, sesion, datos):
    from app import models as m
    servicio, j = _dia(cliente, sesion, datos, offset=360,
                       fin=timedelta(hours=5))
    marca = j["termino"] + timedelta(hours=5)
    nueva = j["termino"] + timedelta(minutes=110)

    r = _corregir(cliente, sesion, j, fin=nueva)
    assert r.status_code == 200, r.text
    assert (r.json()["horas_extra_antes"], r.json()["horas_extra"]) == (5, 2)

    ana = datos["personal"]["Ana Solis"]["id"]
    with _db() as db:
        hito = db.get(m.Hito, _hito(j["id"], "fin_servicio"))
        assert hito.marcado_original == marca, "la hora de la calle se queda"
        assert hito.marcado_en == nueva
        assert hito.ajustado_por_id == ana
        filas = db.query(m.CorreccionHoras).filter_by(jornada_id=j["id"]).all()
        assert [(f.campo, f.antes, f.despues, f.persona_id) for f in filas] \
            == [("fin", marca, nueva, ana)]

    d = cliente.get(f"/operacion/jornadas/{j['id']}/dia",
                    headers=sesion("consultor")).json()
    assert d["horas"]["horas_extra"] == 2
    assert d["horas"]["puedo_corregir"] is True
    assert d["horas"]["correcciones"][0]["quien"] == "Ana Solis"
    assert any(x["titulo"] == "corregir horas" for x in d["renglones"])


def test_corregir_el_arranque_con_el_ejecutivo(cliente, sesion, datos):
    """El ejecutivo bajo una hora antes y el equipo marco el contacto a la
    hora de la presentacion: esa hora de mas se cobra y se paga."""
    from app import models as m
    _, j = _dia(cliente, sesion, datos, offset=362)
    assert _extras(j["id"]) == 0
    r = _corregir(cliente, sesion, j, inicio=j["inicio"] - timedelta(hours=1))
    assert r.status_code == 200, r.text
    assert r.json()["horas_extra"] == 1
    with _db() as db:
        hito = db.get(m.Hito, _hito(j["id"], "contacto_ejecutivo"))
        assert hito.marcado_original == j["inicio"]
        assert db.get(m.Jornada, j["id"]).inicio_real == \
            j["inicio"] - timedelta(hours=1)


def test_solo_el_consultor_del_servicio_o_la_central(cliente, sesion, datos):
    _, j = _dia(cliente, sesion, datos, offset=364, fin=timedelta(hours=3))
    nueva = j["termino"] + timedelta(minutes=30)
    assert _corregir(cliente, sesion, j, "consultor2",
                     fin=nueva).status_code == 403
    assert _corregir(cliente, sesion, j, "juan", fin=nueva).status_code == 403
    assert _extras(j["id"]) == 3
    assert _corregir(cliente, sesion, j, "central",
                     fin=nueva).status_code == 200
    assert _extras(j["id"]) == 1


def test_la_marca_en_revision_solo_la_valida_la_central(cliente, sesion, datos):
    from app import models as m
    _, j = _dia(cliente, sesion, datos, offset=366, fin=timedelta(hours=3))
    fin_id = _hito(j["id"], "fin_servicio")
    with _db() as db:
        db.get(m.Hito, fin_id).requiere_revision = True
        db.commit()

    r = _corregir(cliente, sesion, j, fin=j["termino"] + timedelta(hours=2))
    assert r.status_code == 200, r.text
    with _db() as db:
        assert db.get(m.Hito, fin_id).requiere_revision is True

    r = _corregir(cliente, sesion, j, "central",
                  fin=j["termino"] + timedelta(hours=1))
    assert r.status_code == 200, r.text
    with _db() as db:
        assert db.get(m.Hito, fin_id).requiere_revision is False


def test_con_visto_bueno_el_consultor_ya_no_corrige(cliente, sesion, datos):
    servicio, j = _dia(cliente, sesion, datos, offset=368,
                       fin=timedelta(hours=2))
    _visto_bueno(cliente, sesion, servicio)
    r = _corregir(cliente, sesion, j, fin=j["termino"])
    assert r.status_code == 409, r.text
    assert _extras(j["id"]) == 2
    d = cliente.get(f"/operacion/jornadas/{j['id']}/dia",
                    headers=sesion("consultor")).json()
    assert d["horas"]["puedo_corregir"] is False
    assert d["horas"]["por_que_no"] == "visto_bueno"


def test_un_dia_que_no_termina_no_se_corrige(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(370), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)
    j["termino"] = datetime.fromisoformat(j["fin_programado"])
    r = _corregir(cliente, sesion, j, fin=j["termino"])
    assert r.status_code == 409, r.text


def test_los_topes_de_la_correccion(cliente, sesion, datos):
    _, j = _dia(cliente, sesion, datos, offset=372, fin=timedelta(hours=2))
    # El motivo lleva diez letras.
    assert _corregir(cliente, sesion, j, motivo="Corrige",
                     fin=j["termino"]).status_code == 400
    # Nada que corregir.
    assert _corregir(cliente, sesion, j,
                     fin=j["termino"] + timedelta(hours=2)).status_code == 400
    # Mas de tres horas antes de la presentacion no es de este servicio.
    assert _corregir(cliente, sesion, j,
                     inicio=j["inicio"] - timedelta(hours=4)).status_code == 409
    # No termina antes de arrancar.
    assert _corregir(cliente, sesion, j,
                     fin=j["inicio"] - timedelta(minutes=5)).status_code == 409
    # Ni a una hora que todavia no llega.
    ahora = (j["termino"] + timedelta(hours=3)).isoformat()
    r = cliente.post(f"/operacion/jornadas/{j['id']}/horas",
                     params={"ahora": ahora}, headers=sesion("consultor"),
                     json={"fin": (j["termino"] + timedelta(hours=4))
                           .isoformat(), "justificacion": MOTIVO})
    assert r.status_code == 409, r.text
    assert _extras(j["id"]) == 2


def test_un_dia_cerrado_a_mano_tambien_se_corrige(cliente, sesion, datos):
    """Sin marca de fin: la hora la puso la central al cerrarlo. El renglon
    de la correccion guarda la que tenia."""
    from app import models as m
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(374), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    termino = datetime.fromisoformat(j["fin_programado"])
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     headers=sesion("central"),
                     params={"ahora": (termino + timedelta(hours=4)).isoformat()},
                     json={"justificacion": MOTIVO,
                           "fin_real": (termino + timedelta(hours=3))
                           .isoformat()})
    assert r.status_code == 200, r.text
    j["termino"], j["inicio"] = termino, datetime.fromisoformat(
        j["inicio_programado"])
    assert _extras(j["id"]) == 3

    r = _corregir(cliente, sesion, j, fin=termino + timedelta(minutes=30))
    assert r.status_code == 200, r.text
    assert _extras(j["id"]) == 1
    with _db() as db:
        fila = db.query(m.CorreccionHoras).filter_by(jornada_id=j["id"]).one()
        assert fila.antes == termino + timedelta(hours=3)


# ------------------------------------------------------------ el visto bueno

def test_el_visto_bueno_dice_las_horas_en_horas(cliente, sesion, datos):
    servicio, _ = _dia(cliente, sesion, datos, offset=380, contacto=-30,
                       fin=timedelta(hours=1))
    rev = cliente.get(f"/cierre/servicio/{servicio['id']}/revision",
                      headers=sesion("consultor")).json()
    assert rev["listo_para_finanzas"] is True
    obs = [o for o in rev["observaciones"] if o.get("clave") == "horas_extra"]
    assert len(obs) == 1 and obs[0]["nivel"] == "informativo"
    # Arranco media hora antes: corrian hasta media hora antes del fin
    # programado, y termino una hora despues de el. Hora y media: 2 h.
    assert obs[0]["datos"]["horas"] == 2
    assert obs[0]["datos"]["arranco"] is not None
    eje = rev["comparativo"]["ejecutado"]
    assert float(eje["importe_horas_extra"]) == 640
    assert eje["horas_extra_por_dia"][0]["horas"] == 2


def test_el_visto_bueno_dice_quien_corrigio_las_horas(cliente, sesion, datos):
    servicio, j = _dia(cliente, sesion, datos, offset=382,
                       fin=timedelta(hours=4))
    assert _corregir(cliente, sesion, j,
                     fin=j["termino"] + timedelta(hours=1)).status_code == 200
    rev = cliente.get(f"/cierre/servicio/{servicio['id']}/revision",
                      headers=sesion("finanzas")).json()
    obs = [o for o in rev["observaciones"]
           if o.get("clave") == "horas_corregidas"]
    assert len(obs) == 1 and obs[0]["nivel"] == "revisar"
    assert obs[0]["datos"]["quien"] == "Ana Solis"
    assert obs[0]["datos"]["motivo"] == MOTIVO


def test_las_horas_extra_sin_precio_se_dicen(cliente, sesion, datos):
    """Antes no se cobraban y nadie se enteraba; a la gente si se le
    pagaban."""
    from app import models as m
    with _db() as db:
        tarifas = (db.query(m.TarifaRecurso)
                   .filter_by(perfil_id=datos["perfiles"]
                              ["conductor_seguridad"]["id"],
                              modalidad_id=datos["modalidades"]
                              ["full_day"]["id"]).all())
        antes = {t.id: t.precio_hora_extra for t in tarifas}
        for t in tarifas:
            t.precio_hora_extra = None
        db.commit()
    try:
        servicio, _ = _dia(cliente, sesion, datos, offset=384,
                           fin=timedelta(hours=2))
        rev = cliente.get(f"/cierre/servicio/{servicio['id']}/revision",
                          headers=sesion("consultor")).json()
        obs = [o for o in rev["observaciones"]
               if o.get("clave") == "horas_sin_precio"]
        assert len(obs) == 1 and obs[0]["datos"]["horas"] == 2
        assert float(rev["comparativo"]["ejecutado"]["importe_horas_extra"]) == 0
    finally:
        with _db() as db:
            for tid, precio in antes.items():
                db.get(m.TarifaRecurso, tid).precio_hora_extra = precio
            db.commit()


# ------------------------------------------------------------ el implantado

DIAS = [date(2029, 9, d) for d in (24, 25, 26, 27, 28)]
MOTIVO_MES = "El equipo cerro por telefono; confirmado con el cliente"


def _alta_implantado(cliente, sesion, datos):
    r = cliente.post("/implantados", headers=sesion("consultor"), json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "fecha_inicio": str(DIAS[0]), "dias_servicio": "lunes_viernes",
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": datos["suburban"]["id"]}],
        "unidades": [datos["suburban"]["id"]],
        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000",
        "precio_dia_adicional": "3500",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _terminos(cliente, sesion, contrato_id, hora_extra):
    r = cliente.put(f"/implantados/contratos/{contrato_id}/terminos",
                    headers=sesion("consultor"),
                    json={"esquema": "por_dia", "precio_dia_personal": "2900",
                          "precio_dia_adicional": "3500",
                          "precio_mes_vehiculo": "66000",
                          "viaticos_incluidos": True, "gastos_mes": None,
                          "precio_hora_extra": hora_extra})
    assert r.status_code == 200, r.text
    return r.json()


def _cerrar_el_mes(cliente, sesion, servicio_id, extra_el_24):
    """La central cierra los cinco dias a mano; el 24 termino tarde."""
    panel = cliente.get(f"/implantados/{servicio_id}/mes/2029/9",
                        headers=sesion("consultor")).json()
    jornadas = {date.fromisoformat(d["fecha"]): d["jornada_id"]
                for d in panel["dias"]}
    for dia in DIAS:
        fin = datetime.combine(dia, datetime.min.time()) + timedelta(hours=20)
        cuerpo = {"justificacion": MOTIVO_MES}
        if dia == DIAS[0]:
            cuerpo["fin_real"] = (fin + extra_el_24).isoformat()
        r = cliente.post(f"/operacion/jornadas/{jornadas[dia]}/cerrar-a-mano",
                         headers=sesion("central"), json=cuerpo,
                         params={"ahora": (fin + timedelta(hours=4))
                                 .isoformat()})
        assert r.status_code == 200, r.text


def test_el_implantado_cobra_sus_horas_extra_en_el_mes(cliente, sesion, datos):
    from app import cierre_mes
    from app import models as m
    alta = _alta_implantado(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    assert _terminos(cliente, sesion, contrato, "320")["precio_hora_extra"] \
        is not None
    _cerrar_el_mes(cliente, sesion, sid, timedelta(minutes=90))

    rev = cliente.get(f"/implantados/contratos/{contrato}/cierre/revision",
                      headers=sesion("consultor")).json()
    trabajado = rev["comparativo"]["trabajado"]
    assert trabajado["horas_extra"] == 2
    assert float(trabajado["desglose"]["horas_extra"]) == 640
    # Cinco dias a 2900, la unidad y las dos horas.
    assert float(trabajado["importe"]) == 5 * 2900 + 66000 + 640
    assert any(o.get("clave") == "horas_extra_mes"
               for o in rev["observaciones"])

    with _db() as db:
        cierre = db.query(m.Cierre).filter_by(contrato_id=contrato).one()
        factura = cierre_mes.armar_factura(db, cierre)
    renglon = next(c for c in factura["conceptos"] if c["tipo"] == "horas_extra")
    assert (renglon["cantidad"], float(renglon["importe"])) == (2, 640)


def test_sin_precio_el_mes_dice_que_no_las_va_a_cobrar(cliente, sesion, datos):
    alta = _alta_implantado(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    _cerrar_el_mes(cliente, sesion, sid, timedelta(minutes=30))
    rev = cliente.get(f"/implantados/contratos/{contrato}/cierre/revision",
                      headers=sesion("consultor")).json()
    assert rev["comparativo"]["trabajado"]["horas_extra"] == 1
    assert any(o.get("clave") == "horas_sin_precio_mes"
               for o in rev["observaciones"])
    assert rev["listo_para_finanzas"] is True, "no frena el visto bueno"


def test_el_precio_de_hora_extra_pasa_al_mes_siguiente(cliente, sesion, datos):
    from app import implantado as motor
    from app import models as m
    alta = _alta_implantado(cliente, sesion, datos)
    _terminos(cliente, sesion, alta["contrato_id"], "450")
    with _db() as db:
        octubre = motor.abrir_siguiente(
            db, db.get(m.Servicio, alta["servicio_id"]),
            hoy=date(2029, 9, 27))["contrato_id"]
        db.commit()
        assert float(db.get(m.ContratoImplantado, octubre)
                     .precio_hora_extra) == 450


# ------------------------------------------------------------ lo que salio de la revision

def test_la_marca_con_zona_se_dice_en_la_hora_de_alla(cliente, sesion, datos):
    """La app mandaba la hora UTC sin decirlo y aqui se leia como hora de
    pared: en Mexico cada marca llegaba seis horas en el futuro. Ahora la
    manda con su zona y se guarda en la hora del pais."""
    from app import models as m
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(390), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    llegada = inicio - timedelta(minutes=10)
    # Ciudad de Mexico va seis horas detras de UTC.
    en_utc = (llegada + timedelta(hours=6)).isoformat() + "Z"
    r = cliente.post(f"/operacion/jornadas/{j['id']}/hitos",
                     headers=sesion("juan"),
                     json={"tipo": "llegada_origen", "marcado_en": en_utc,
                           "lat": "19.4272", "lon": "-99.1679"})
    assert r.status_code in (200, 201), r.text
    with _db() as db:
        hito = db.get(m.Hito, _hito(j["id"], "llegada_origen"))
        assert hito.marcado_en == llegada
        assert hito.requiere_revision is False


def test_el_fin_que_llega_despues_con_hora_anterior_no_quita_horas(
        cliente, sesion, datos):
    """El dia termina con el ultimo del equipo: la marca que llega tarde
    de la cola con una hora anterior no le quita horas."""
    _, j = _dia(cliente, sesion, datos, offset=392, fin=timedelta(hours=2))
    r = marcar_fin(cliente, sesion("juan"), j["id"],
                   j["termino"] + timedelta(hours=1))
    assert r.status_code in (200, 201), r.text
    assert _extras(j["id"]) == 2


def test_una_marca_despues_del_visto_bueno_no_mueve_las_horas(
        cliente, sesion, datos):
    from app import models as m
    servicio, j = _dia(cliente, sesion, datos, offset=394,
                       fin=timedelta(hours=2))
    _visto_bueno(cliente, sesion, servicio)
    r = marcar_fin(cliente, sesion("juan"), j["id"],
                   j["termino"] + timedelta(hours=5))
    assert r.status_code in (200, 201), r.text
    assert _extras(j["id"]) == 2
    with _db() as db:
        tarde = (db.query(m.Hito)
                 .filter_by(jornada_id=j["id"], tipo=m.TipoHito.FIN_SERVICIO)
                 .order_by(m.Hito.id.desc()).first())
        assert tarde.requiere_revision is True


def test_ajustar_otro_meet_and_greet_no_quita_el_primero(cliente, sesion,
                                                        datos):
    from app import models as m
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(396), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Luis Mendoza"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    for quien in ("juan", "luis"):
        marcar(cliente, sesion(quien), j["id"], "llegada_origen",
               inicio - timedelta(minutes=40))
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo",
           inicio - timedelta(minutes=30))
    marcar(cliente, sesion("luis"), j["id"], "contacto_ejecutivo",
           inicio - timedelta(minutes=10))
    with _db() as db:
        de_luis = (db.query(m.Hito)
                   .filter_by(jornada_id=j["id"],
                              tipo=m.TipoHito.CONTACTO_EJECUTIVO,
                              persona_id=datos["personal"]["Luis Mendoza"]["id"])
                   .one().id)
    r = cliente.post(f"/operacion/hitos/{de_luis}/ajustar",
                     headers=sesion("central"),
                     json={"nuevo_momento": (inicio - timedelta(minutes=15))
                           .isoformat(), "justificacion": MOTIVO})
    assert r.status_code == 200, r.text
    with _db() as db:
        assert db.get(m.Jornada, j["id"]).inicio_real == \
            inicio - timedelta(minutes=30)


def test_una_marca_anulada_no_se_ajusta(cliente, sesion, datos):
    """El fin de un dia que se reabrio ya no cuenta: ajustarlo le ponia
    hora de termino a un dia abierto."""
    _, j = _dia(cliente, sesion, datos, offset=398, fin=timedelta(hours=1))
    fin_id = _hito(j["id"], "fin_servicio")
    r = cliente.post(f"/operacion/jornadas/{j['id']}/reabrir",
                     headers=sesion("central"),
                     json={"justificacion": "El equipo cerro antes de tiempo"})
    assert r.status_code == 200, r.text
    r = cliente.post(f"/operacion/hitos/{fin_id}/ajustar",
                     headers=sesion("central"),
                     json={"nuevo_momento": (j["termino"] + timedelta(hours=2))
                           .isoformat(), "justificacion": MOTIVO})
    assert r.status_code == 409, r.text


def test_reabrir_conserva_el_meet_and_greet_de_la_calle(cliente, sesion, datos):
    """Un dia con su meet and greet marcado, que la central cerro a mano y
    luego reabrio: la hora de la calle se queda, porque de ella corren las
    horas y ya no se puede volver a poner a mano."""
    from app import models as m
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(400), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    termino = datetime.fromisoformat(j["fin_programado"])
    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=70))
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo",
           inicio - timedelta(minutes=60))
    central = sesion("central")
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     headers=central, json={"justificacion": MOTIVO},
                     params={"ahora": (termino + timedelta(hours=2))
                             .isoformat()})
    assert r.status_code == 200, r.text
    r = cliente.post(f"/operacion/jornadas/{j['id']}/reabrir", headers=central,
                     json={"justificacion": "Se cerro con la hora equivocada"})
    assert r.status_code == 200, r.text
    with _db() as db:
        assert db.get(m.Jornada, j["id"]).inicio_real == \
            inicio - timedelta(minutes=60)


def test_cerrar_a_mano_con_un_arranque_de_mas_de_tres_horas_antes(
        cliente, sesion, datos):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(402), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    termino = datetime.fromisoformat(j["fin_programado"])
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     headers=sesion("central"),
                     params={"ahora": (termino + timedelta(hours=2))
                             .isoformat()},
                     json={"justificacion": MOTIVO,
                           "inicio_real": (inicio - timedelta(hours=4))
                           .isoformat()})
    assert r.status_code == 409, r.text


def test_guardar_los_km_no_rehace_la_ventana_del_dia(cliente, sesion, datos):
    """Rehacerla siempre le ponia al dia las horas que hoy tiene la
    modalidad en el catalogo, y no las que se contrataron."""
    from app import models as m
    _, j = _dia(cliente, sesion, datos, offset=404, fin=timedelta(hours=1))
    contratado = j["termino"] - timedelta(hours=2)
    with _db() as db:
        db.get(m.Jornada, j["id"]).fin_programado = contratado
        db.commit()
    r = cliente.patch(f"/servicios/jornadas/{j['id']}", headers=sesion("consultor"),
                      json={"km_estimados": 180})
    assert r.status_code == 200, r.text
    with _db() as db:
        assert db.get(m.Jornada, j["id"]).fin_programado == contratado


def test_el_meet_and_greet_a_mano_en_un_dia_terminado(cliente, sesion, datos):
    """En un dia ya terminado, asentarlo mueve las horas extra: queda como
    correccion para el visto bueno, y con el visto bueno dado ya no se
    asienta."""
    from app import models as m
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(406), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    termino = datetime.fromisoformat(j["fin_programado"])
    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=70))
    assert marcar_fin(cliente, sesion("juan"), j["id"],
                      termino).status_code in (200, 201)
    assert _extras(j["id"]) == 0

    r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                     headers=sesion("central"),
                     params={"ahora": (termino + timedelta(hours=1))
                             .isoformat()},
                     json={"tipo": "contacto_ejecutivo", "persona_id": juan,
                           "momento": (inicio - timedelta(minutes=60))
                           .isoformat(), "justificacion": MOTIVO})
    assert r.status_code == 200, r.text
    assert _extras(j["id"]) == 1
    with _db() as db:
        assert db.get(m.Jornada, j["id"]).estatus == m.EstatusJornada.TERMINADA
        assert db.query(m.CorreccionHoras).filter_by(
            jornada_id=j["id"], campo="inicio").count() == 1

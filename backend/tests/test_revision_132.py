# -*- coding: utf-8 -*-
"""Seccion 132: la ola 4c de la revision del 2 de octubre (decisiones 6,
7, 8, 17 y 18 de Salvador).

  * El freelance que Centauro contrata de planta: «Pasar a planta» en su
    ficha, para RH; la ficha se cierra como historia y la lectura de
    Odoo lo toma por su correo. Y el alta de freelance acepta el correo
    de quien se dio de baja en Odoo: vuelve la misma persona (decision 6).
  * El de emergencia que repite: quince dias desde el ultimo dia del
    servicio que se le asigna, no del anterior (decision 7).
  * La huella se ofrece sola solo en telefonos; en computadoras se activa
    a mano con la advertencia; el saludo con el nombre de pila (decision 8).
  * Por la unidad responde quien va al volante; la reconfirmacion por
    cambio de hora no le llega a quien propuso esa hora (decision 17).
  * El texto de la 108 ya no dice que el gerente «no toca Odoo» (18).
"""
import os
import pathlib
from datetime import date, datetime, timedelta

from sqlalchemy import text

from app import freelance as motor
from app import models as m
from app import push
from app.db import SessionLocal
from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana, marcar)
from test_odoo_personal import DOMINIO, ODOO0, OdooFalso, empleado, leer
from test_odoo_personal import sin_rastro  # noqa: F401  (fixture)
from test_revision_105_calle import _dos_dias, _proponer
from test_revision_105_calle import avisos  # noqa: F401  (fixture)
from test_revision_111_freelance import (_alta, _asignar_equipo, _completar,
                                         _costos, _servicio)
from test_revision_111_freelance import db, nuevos  # noqa: F401  (fixtures)

RAIZ = pathlib.Path(__file__).resolve().parents[1]
WEB = os.path.join(RAIZ, "app", "web")


def _js(nombre: str) -> str:
    return open(os.path.join(WEB, nombre), encoding="utf-8").read()


def _idioma_tiene(*claves) -> None:
    js = _js("idioma.js")
    for clave in claves:
        assert js.count(f"\n    {clave}: ") == 3, clave


def _ficha(db, persona_id):
    db.expire_all()
    return db.query(m.Freelance).filter_by(persona_id=persona_id).one()


def _historial(db, persona_id, accion):
    return (db.query(m.RegistroAdmin)
            .filter_by(objeto="freelance", objeto_id=persona_id, accion=accion)
            .order_by(m.RegistroAdmin.id.desc()).first())


# ============================== decision 6 · el freelance pasa a planta

def test_rh_pasa_al_freelance_a_planta_y_la_ficha_queda_como_historia(
        cliente, sesion, datos, nuevos, db):
    """Centauro lo contrato: RH lo pasa a planta. Deja de ser freelance,
    su ficha se queda con quien y cuando, se lee pero ya no se opera, la
    lista lo ensena con su filtro y la lectura de Odoo ya lo liga por su
    correo en vez de dejarlo pendiente."""
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    _costos(cliente, sesion, persona_id)
    assert _completar(cliente, sesion, persona_id)["resumen"]["estado"] == "listo"
    r = cliente.post(f"/freelance/{persona_id}/acceso", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    servicio = _servicio(cliente, sesion, datos, desde=20)
    assert _asignar_equipo(cliente, sesion("consultor"), servicio,
                           persona_id).status_code == 200

    # Lo pide RH, no el consultor.
    r = cliente.post(f"/freelance/{persona_id}/a-planta", headers=sesion("consultor"))
    assert r.status_code == 403, r.text
    rh = sesion("rrhh")
    r = cliente.post(f"/freelance/{persona_id}/a-planta", headers=rh)
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "de planta"
    assert "tarifa de freelance" in r.json()["que_sigue"]

    db.expire_all()
    persona = db.get(m.Persona, persona_id)
    assert persona.es_freelance is False and persona.activo
    ficha = _ficha(db, persona_id)
    assert ficha.planta_en is not None
    assert ficha.planta_por_id == (db.query(m.Usuario)
                                   .filter_by(correo="rrhh@centauro.lat").one()
                                   .persona_id)
    registro = _historial(db, persona_id, "pasa a planta")
    assert registro is not None and registro.despues == "de planta"
    # Su acceso, sus dias y su expediente siguen.
    assert db.query(m.Usuario).filter_by(persona_id=persona_id).one().activo
    assert db.query(m.AsignacionPersonal).filter_by(persona_id=persona_id).count() == 1
    assert db.query(m.DocumentoFreelance).filter_by(persona_id=persona_id).count() > 0

    # La ficha se lee como historia: dice que paso a planta y no se edita.
    r = cliente.get(f"/freelance/{persona_id}", headers=rh)
    assert r.status_code == 200, r.text
    f = r.json()
    rh_persona = db.get(m.Persona, ficha.planta_por_id)
    assert f["planta_en"] and f["planta_por"] == rh_persona.nombre
    assert f["puede"]["editar"] is False and f["puede"]["a_planta"] is False
    assert f["puede"]["costos"] is False and f["puede_acceso"] is False
    assert f["puede"]["expediente"] is True
    r = cliente.get(f"/freelance/{persona_id}/expediente", headers=rh)
    assert r.status_code == 200 and r.json()["puede_cargar"] is False
    assert r.json()["puede_validar"] is False
    assert cliente.patch(f"/freelance/{persona_id}", json={"nombre": "Otro"},
                         headers=rh).status_code == 404
    assert cliente.post(f"/freelance/{persona_id}/acceso", headers=rh).status_code == 404
    assert cliente.post(f"/freelance/{persona_id}/a-planta", headers=rh).status_code == 404
    assert cliente.post(f"/freelance/{persona_id}/baja", json={"motivo": "ya no"},
                        headers=rh).status_code == 404

    # En la lista solo con las bajas, y marcado.
    pais = datos["cdmx"]["pais_id"]
    vivos = cliente.get(f"/freelance?pais_id={pais}", headers=rh).json()
    assert persona_id not in [x["persona_id"] for x in vivos]
    todos = cliente.get(f"/freelance?pais_id={pais}&incluir_bajas=true", headers=rh).json()
    suya = next(x for x in todos if x["persona_id"] == persona_id)
    assert suya["planta_en"] and suya["activo"]

    # Ya no va en implantados como freelance ni le estorba la puerta.
    assert motor.revisar_para_asignar(
        db, persona, db.get(m.Servicio, servicio["id"]), {"full_day"}) is None

    # La lectura de Odoo lo liga por su correo: antes quedaba pendiente
    # «en Centauro es freelance; en Odoo ya es de planta».
    informe = leer(db, OdooFalso(empleado(1, private_email=persona.correo,
                                          work_email=False)))
    assert informe["pendientes"] == []
    assert [v["persona_id"] for v in informe["vinculadas"]] == [persona_id]
    db.expire_all()
    persona = db.get(m.Persona, persona_id)
    assert persona.odoo_id == ODOO0 + 1 and persona.es_freelance is False


def test_los_dias_de_antes_se_pagan_como_freelance_y_desde_el_cambio_como_planta(
        cliente, sesion, datos, nuevos, db):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    _costos(cliente, sesion, persona_id)
    persona = db.get(m.Persona, persona_id)
    assert motor.cobra_como_freelance(db, persona, date.today())
    assert motor.cobra_como_freelance(db, persona, date.today() + timedelta(days=30))
    r = cliente.post(f"/freelance/{persona_id}/a-planta", headers=sesion("rrhh"))
    assert r.status_code == 200, r.text
    db.expire_all()
    persona = db.get(m.Persona, persona_id)
    hoy = motor._hoy(db, persona)
    assert motor.cobra_como_freelance(db, persona, hoy - timedelta(days=1))
    assert not motor.cobra_como_freelance(db, persona, hoy)
    assert not motor.cobra_como_freelance(db, persona, hoy + timedelta(days=5))
    # Un de planta de siempre: nunca como freelance.
    juan = db.get(m.Persona, datos["personal"]["Juan Ramirez"]["id"])
    assert not motor.cobra_como_freelance(db, juan, hoy - timedelta(days=100))


def test_la_urgencia_pedida_del_que_paso_a_planta_ya_no_se_lista(
        cliente, sesion, datos, nuevos, db):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    _costos(cliente, sesion, persona_id)
    servicio = _servicio(cliente, sesion, datos, desde=22)
    r = cliente.post(f"/freelance/{persona_id}/urgencias",
                     json={"servicio_id": servicio["id"],
                           "motivo": "el cliente lo pidio por nombre"},
                     headers=sesion("consultor"))
    assert r.status_code == 201, r.text
    assert [u["persona_id"] for u in cliente.get(
        "/freelance/urgencias", headers=sesion("diroperaciones")).json()
            if u["persona_id"] == persona_id] == [persona_id]
    assert cliente.post(f"/freelance/{persona_id}/a-planta",
                        headers=sesion("rrhh")).status_code == 200
    assert [u for u in cliente.get("/freelance/urgencias",
                                   headers=sesion("diroperaciones")).json()
            if u["persona_id"] == persona_id] == []


def test_el_alta_de_freelance_trae_de_vuelta_a_quien_se_fue_de_odoo(
        cliente, sesion, datos, nuevos, db):
    """Se dio de baja en Odoo y vuelve como freelance con su mismo correo:
    es la misma persona --sus horas, su acceso cerrado--, se le suelta el
    empleado de Odoo que fue (la lectura no lo vuelve a dar de baja), y
    «Dar acceso» le vuelve a abrir el que tenia. Si Odoo lo contrata de
    nuevo, queda pendiente y RH lo pasa a planta."""
    odoo = OdooFalso(empleado(1), empleado(2))
    leer(db, odoo)
    db.expire_all()
    persona = db.query(m.Persona).filter_by(odoo_id=ODOO0 + 1).one()
    persona_id, correo = persona.id, persona.correo
    usuario_id = db.query(m.Usuario).filter_by(persona_id=persona_id).one().id
    odoo.archivar(1)
    assert len(leer(db, odoo)["bajas"]) == 1
    db.expire_all()
    persona = db.get(m.Persona, persona_id)
    assert not persona.activo and persona.baja_odoo_en is not None

    # Mientras esta activo no: el correo es de alguien.
    h = sesion("consultor")
    r = cliente.post("/freelance", json={
        "nombre": "Agente", "apellidos": "Odoo Uno", "lada": "+52",
        "telefono": "55 3412 8890", "correo": f"agente2@{DOMINIO}",
        "plaza_id": datos["cdmx"]["id"], "tipo": "programado"}, headers=h)
    assert r.status_code == 409, r.text
    assert "ya es de" in r.json()["detail"]["mensaje"]

    # Dado de baja en Odoo: vuelve la misma persona.
    r = cliente.post("/freelance", json={
        "nombre": "Agente", "apellidos": "Odoo Uno", "lada": "+52",
        "telefono": "55 3412 8890", "correo": correo,
        "plaza_id": datos["cdmx"]["id"], "tipo": "emergencia"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["persona_id"] == persona_id and r.json()["vuelve"] is True
    nuevos.append(persona_id)
    db.expire_all()
    persona = db.get(m.Persona, persona_id)
    assert persona.activo and persona.es_freelance and not persona.oficina
    assert persona.odoo_id is None and persona.baja_odoo_en is None
    assert persona.nombre == "Agente Odoo Uno"
    ficha = _ficha(db, persona_id)
    assert ficha.tipo == "emergencia" and ficha.odoo_id_anterior == ODOO0 + 1
    assert ficha.planta_en is None
    registro = _historial(db, persona_id, "alta")
    assert registro is not None and "vuelve de Odoo" in registro.detalle
    # Su acceso de antes sigue cerrado: se abre con el expediente.
    assert not db.query(m.Usuario).filter_by(persona_id=persona_id).one().activo
    f = cliente.get(f"/freelance/{persona_id}", headers=h).json()
    assert f["acceso"]["usuario_id"] == usuario_id and f["acceso"]["activo"] is False

    # La siguiente lectura, con el empleado todavia archivado, no lo
    # vuelve a dar de baja: ya no es de Odoo.
    informe = leer(db, odoo)
    assert informe["bajas"] == [] and informe["pendientes"] == []
    db.expire_all()
    assert db.get(m.Persona, persona_id).activo

    # Con el expediente listo, «Dar acceso» reabre el que tenia.
    _costos(cliente, sesion, persona_id)
    assert _completar(cliente, sesion, persona_id)["resumen"]["estado"] == "listo"
    r = cliente.post(f"/freelance/{persona_id}/acceso", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["usuario_id"] == usuario_id
    db.expire_all()
    assert db.query(m.Usuario).filter_by(persona_id=persona_id).one().activo
    assert cliente.post(f"/freelance/{persona_id}/acceso", headers=h).status_code == 409

    # Odoo lo contrata otra vez, con otro empleado y el mismo correo:
    # pendiente hasta que RH lo pase a planta, y entonces se liga al nuevo.
    odoo = OdooFalso(empleado(2), empleado(3, private_email=correo, work_email=False))
    informe = leer(db, odoo)
    assert [(p["persona_id"], p["falta"]) for p in informe["pendientes"]] == [
        (persona_id, ["en Centauro es freelance; en Odoo ya es de planta: "
                      "pasarlo a mano"])]
    assert cliente.post(f"/freelance/{persona_id}/a-planta",
                        headers=sesion("rrhh")).status_code == 200
    informe = leer(db, odoo)
    assert [v["persona_id"] for v in informe["vinculadas"]] == [persona_id]
    db.expire_all()
    persona = db.get(m.Persona, persona_id)
    assert persona.odoo_id == ODOO0 + 3 and not persona.es_freelance and persona.activo
    assert _ficha(db, persona_id).odoo_id_anterior == ODOO0 + 1


def test_el_freelance_dado_de_baja_no_se_da_de_alta_dos_veces(
        cliente, sesion, datos, nuevos, db):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    correo = db.get(m.Persona, persona_id).correo
    assert cliente.post(f"/freelance/{persona_id}/baja", json={"motivo": "se fue"},
                        headers=sesion("rrhh")).status_code == 200
    r = cliente.post("/freelance", json={
        "nombre": "Mario", "apellidos": "Esquivel Rangel", "lada": "+52",
        "telefono": "55 3412 8890", "correo": correo,
        "plaza_id": datos["cdmx"]["id"], "tipo": "programado"},
        headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "De baja" in r.json()["detail"]["que_hacer"]
    # Y al dado de baja no se le pasa a planta sin reactivarlo.
    r = cliente.post(f"/freelance/{persona_id}/a-planta", headers=sesion("rrhh"))
    assert r.status_code == 409 and "Volver a dar de alta" in r.json()["detail"]["que_hacer"]


def test_la_pantalla_de_la_ficha_trae_pasar_a_planta():
    js = _js("freelance.js")
    assert "/a-planta" in js and "puede.a_planta" in js
    assert 'filtroEstado === "a_planta"' in js and "f.planta_en" in js
    assert "(!acc || !acc.activo) && puede.editar" in js
    assert "e.puede_cargar !== false" in js
    assert 'r.vuelve ? "fre_alta_vuelve"' in js
    _idioma_tiene("fre_filtro_a_planta", "fre_de_planta", "fre_alta_vuelve",
                  "fre_planta_titulo", "fre_pasar_a_planta", "fre_planta_pie",
                  "fre_planta_pregunta", "fre_planta_hecha", "fre_paso_a_planta",
                  "fre_paso_a_planta_pie", "fre_ver_en_personal",
                  "fre_h_pasa_a_planta")


# ================================= decision 7 · el plazo del de emergencia

def test_el_plazo_del_de_emergencia_cuenta_desde_el_servicio_que_se_le_asigna(
        cliente, sesion, datos, nuevos, db):
    h = sesion("consultor")
    persona_id = _alta(cliente, h, datos, nuevos, tipo="emergencia")
    _costos(cliente, sesion, persona_id)
    assert _completar(cliente, sesion, persona_id)["resumen"]["estado"] == "listo"
    primero = _servicio(cliente, sesion, datos, desde=30)
    assert _asignar_equipo(cliente, h, primero, persona_id).status_code == 200
    # El segundo dura tres dias: el plazo arranca en el ultimo.
    segundo = _servicio(cliente, sesion, datos, desde=40, dias=3)
    persona = db.get(m.Persona, persona_id)
    resp = motor.para_asignar(db, persona, db.get(m.Servicio, segundo["id"]),
                              {"full_day"})
    assert resp["asignable"] and resp["plazo_nuevo"] == (
        manana(42) + timedelta(days=15)).isoformat()
    # Si el servicio que se le asigna ya paso --se registra tarde--, el
    # plazo cuenta desde hoy: nunca nace vencido.
    db.execute(text("UPDATE jornada SET fecha = fecha - interval '50 days' "
                    "WHERE equipo_id IN (SELECT id FROM equipo WHERE servicio_id = :s)"),
               {"s": segundo["id"]})
    db.commit()
    resp = motor.para_asignar(db, persona, db.get(m.Servicio, segundo["id"]),
                              {"full_day"})
    assert resp["asignable"] and resp["motivo"] is None
    assert resp["plazo_nuevo"] == (motor._hoy(db, persona)
                                   + timedelta(days=15)).isoformat()
    assert "plazo_vencido" not in str(resp)


# ========================================= decision 8 · la huella en PCs

def test_la_huella_se_ofrece_sola_solo_en_telefonos():
    huella = _js("huella.js")
    assert "export function esTelefono()" in huella
    assert "if (!esTelefono()) return false;" in huella
    assert "export function primerNombre" in huella
    consola = _js("huella_consola.js")
    assert "huella.primerNombre(r.nombre)" in consola
    assert "r.correo" not in consola
    assert 'huella.esTelefono() ? null : aviso(huella.th("solo_tuyo"), "alerta")' in consola
    campo = _js(os.path.join("campo", "app.js"))
    assert "huella.primerNombre(conocido.nombre)" in campo
    assert "conocido.nombre)," not in campo
    _idioma_tiene("hue_solo_tuyo")


# ====================== decision 17 · quien responde por la unidad y la hora

def _fin(cliente, headers, j):
    inicio = datetime.fromisoformat(j["inicio_programado"])
    fin = datetime.fromisoformat(j["fin_programado"])
    marcar(cliente, headers, j["id"], "llegada_origen", inicio - timedelta(minutes=10))
    marcar(cliente, headers, j["id"], "contacto_ejecutivo", inicio)
    return marcar(cliente, headers, j["id"], "fin_servicio", fin,
                  ubicacion={"lat": 19.4326, "lon": -99.1332})


def test_por_la_unidad_responde_quien_va_al_volante(cliente, sesion, datos, db,
                                                    avisos):
    """Una unidad, Luis de conductor y Juan de agente. Juan marca el fin:
    la entrega pendiente es de Luis, que maneja; antes era de quien
    marcaba el fin."""
    from ayudas import KM_RECEPCION, revisar_unidad
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(66), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    for r in asignar(cliente, h, j["id"], persona_id=juan, rol="agente_seguridad"):
        assert r.status_code == 200, r.text
    for r in asignar(cliente, h, j["id"], persona_id=luis, rol="conductor_seguridad",
                     vehiculo_id=datos["suburban"]["id"]):
        assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    assert revisar_unidad(cliente, sesion("luis"), servicio["id"],
                          datos["suburban"]["id"], "recibe",
                          KM_RECEPCION).status_code == 201
    r = _fin(cliente, sesion("juan"), j)
    assert r.status_code == 200, r.text
    pend = (db.query(m.EntregaPendiente)
            .filter_by(servicio_id=servicio["id"], vehiculo_id=datos["suburban"]["id"])
            .one())
    assert pend.persona_id == luis
    fin = datetime.fromisoformat(j["fin_programado"])
    luego = (fin + timedelta(hours=1)).isoformat()
    assert len(cliente.get(f"/campo/mi-dia?ahora={luego}",
                           headers=sesion("luis")).json()["entregas_pendientes"]) == 1
    # El «te falta entregar la unidad» al telefono es de Luis.
    assert [a["persona_id"] for a in avisos
            if str(a.get("etiqueta", "")).startswith("entrega-")] == [luis]


def test_la_reconfirmacion_por_cambio_de_hora_no_le_llega_a_quien_la_propuso(
        cliente, sesion, datos, db, avisos):
    """Juan propone las 07:30 y ya habia confirmado manana; Luis tambien.
    La central confirma: a Luis le llega «cambio tu hora» y vuelve a
    «por confirmar»; Juan, que pidio esa hora, se queda confirmado y sin
    aviso. Lo mismo cuando la confirma el reloj a las 22:00."""
    from app import operacion
    servicio, dias = _dos_dias(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    assert cliente.post(f"/operacion/jornadas/{dias[1]['id']}/confirmar-recurso",
                        headers=sesion("juan")).status_code == 200
    assert _proponer(cliente, sesion, dias[0]).status_code == 200
    avisos.clear()
    r = cliente.post(f"/central/manana/{dias[1]['id']}/confirmar-hora",
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert r.json()["avisados"] == {"avisados": 1, "reconfirman": 1}
    assert [a["persona_id"] for a in avisos] == [luis]
    assert avisos[0]["titulo"] == push.tx("es", "cambio_hora_titulo")
    db.expire_all()
    por_persona = {a.persona_id: a for a in db.get(m.Jornada, dias[1]["id"]).personal}
    assert por_persona[luis].confirmado is False
    assert por_persona[juan].confirmado is True

    # El reloj: otra propuesta sobre el mismo dia, confirmada a las 22:00.
    assert cliente.post(f"/operacion/jornadas/{dias[1]['id']}/confirmar-recurso",
                        headers=sesion("luis")).status_code == 200
    assert _proponer(cliente, sesion, dias[0], hora="07:45:00").status_code == 200
    avisos.clear()
    hoy = db.get(m.Jornada, dias[0]["id"]).fecha
    r = operacion.confirmar_propuestas_vencidas(
        db, datetime.combine(hoy, datetime.min.time()).replace(hour=22, minute=5))
    assert [c["propuso_id"] for c in r["confirmadas"]] == [juan]
    assert [a["persona_id"] for a in avisos] == [luis]
    db.expire_all()
    por_persona = {a.persona_id: a for a in db.get(m.Jornada, dias[1]["id"]).personal}
    assert por_persona[luis].confirmado is False
    assert por_persona[juan].confirmado is True


# ===================================== decision 18 · el gerente y Odoo

def test_las_novedades_ya_no_dicen_que_el_gerente_no_toca_odoo():
    for lengua, frase, vieja in (("es", "no administra la conexión con Odoo",
                                  "no toca Odoo. Se sugiere"),
                                 ("pt", "não administra a conexão com o Odoo",
                                  "não mexe no Odoo. É sugerido")):
        texto = (RAIZ / "manual" / "novedades" / f"{lengua}.md").read_text(encoding="utf-8")
        seccion = texto.split("## 108 ·")[1].split("\n## ")[0]
        assert frase in seccion and vieja not in seccion


# ========================================= la migracion de la seccion

def test_la_migracion_de_planta_es_la_cabeza():
    versiones = RAIZ / "migrations" / "versions"
    nueva = (versiones / "d4e8f0a3b2c5_freelance_a_planta.py").read_text()
    assert 'down_revision = "c3d7e9f2a1b4"' in nueva
    assert sum(1 for p in versiones.glob("*.py")
               if 'down_revision = "d4e8f0a3b2c5"' in p.read_text()) == 0
    with SessionLocal() as db:
        assert db.query(m.Freelance.planta_en, m.Freelance.planta_por_id,
                        m.Freelance.odoo_id_anterior).limit(1).all() is not None

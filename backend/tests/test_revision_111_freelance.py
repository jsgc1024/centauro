# -*- coding: utf-8 -*-
"""Seccion 111: el freelance en Connect.

Salvador (30 sep): un lugar para dar de alta al freelance con su foto y
sus datos --los que salen en la hoja--, otro donde se cargue lo que pide
Recursos Humanos para activarlo, y sus costos propios de dia completo,
medio dia y transfer, solo en eventuales. Con sus doce decisiones:
vive en Connect; lo dan de alta el consultor, direccion de operaciones y
RRHH, y el expediente lo valida solo RRHH; sin costos o sin expediente
no se asigna, salvo la urgencia que autoriza direccion de operaciones;
el de emergencia que repite tiene quince dias para completar lo de
programado; los documentos los abren RRHH, direccion de operaciones y
direccion general; nunca en implantados.
"""
import importlib.util
import json
import os
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app import freelance as motor
from app import models as m
from tests.ayudas import (PIXEL, asignar, crear_servicio, jornada, manana,
                          rol_por_omision)

WEB = os.path.join(os.path.dirname(__file__), "..", "app", "web")
MIGRACION = os.path.join(os.path.dirname(__file__), "..", "migrations",
                         "versions", "cd3b659a42f6_freelance_en_connect.py")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _js(nombre: str) -> str:
    return open(os.path.join(WEB, nombre), encoding="utf-8").read()


def _migracion():
    spec = importlib.util.spec_from_file_location("m111", MIGRACION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _clabe(base17: str) -> str:
    pesos = (3, 7, 1) * 6
    suma = sum((int(d) * w) % 10 for d, w in zip(base17, pesos))
    return base17 + str((10 - suma % 10) % 10)


@pytest.fixture
def db(nuevos):
    """Depende de `nuevos` para cerrarse antes que el: la limpieza vacia
    tablas, y una sesion abierta con su transaccion la dejaria esperando
    para siempre."""
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def nuevos(base_de_pruebas):
    """Los freelance que da de alta cada prueba se van al terminar: la
    persona no es movimiento y se quedaria en las listas de las demas."""
    creados: list[int] = []
    yield creados
    if not creados:
        return
    from tests.conftest import TABLAS_DE_OPERACION
    from app.seed import sembrar_recursos
    ids = ",".join(str(i) for i in creados)
    with base_de_pruebas.begin() as con:
        con.execute(text(f"TRUNCATE {', '.join(TABLAS_DE_OPERACION)} "
                         "RESTART IDENTITY CASCADE"))
        con.execute(text(f"DELETE FROM permiso_extra WHERE usuario_id IN "
                         f"(SELECT id FROM usuario WHERE persona_id IN ({ids}))"))
        con.execute(text(f"DELETE FROM usuario WHERE persona_id IN ({ids})"))
        con.execute(text(f"DELETE FROM tarifa_freelance WHERE persona_id IN ({ids})"))
        con.execute(text(f"DELETE FROM persona WHERE id IN ({ids})"))
    sembrar_recursos()


def _alta(cliente, h, datos, nuevos, tipo="programado", plaza="cdmx",
          nombre="Mario", apellidos="Esquivel Rangel"):
    correo = f"fre-{uuid.uuid4().hex[:10]}@prueba111.mx"
    r = cliente.post("/freelance", json={
        "nombre": nombre, "apellidos": apellidos, "lada": "+52",
        "telefono": "55 3412 8890", "correo": correo,
        "plaza_id": datos[plaza]["id"], "tipo": tipo}, headers=h)
    assert r.status_code == 201, r.text
    nuevos.append(r.json()["persona_id"])
    return r.json()["persona_id"]


def _costos(cliente, sesion, persona_id, **mas):
    r = cliente.put(f"/freelance/{persona_id}/costos", json={
        "dia_completo": "2000", "medio_dia": "1200", "transfer": "800",
        "hora_extra": "200", **mas}, headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    return r.json()


def _para(req: dict, hoy: date) -> tuple[dict, dict, list]:
    """Lo que se carga para cada requisito, bien hecho."""
    cap, vig = req["captura"], req["vigencia"]
    datos, campos, archivos = {}, {}, []
    if cap in ("archivo", "archivo_numero", "banco", "riesgo"):
        archivos = [("archivos", (f"{req['clave']}.pdf", PDF, "application/pdf"))]
    if cap == "numero":
        datos["numero"] = ("GOCS800101HDFRRL09" if req["clave"] == "curp"
                           else "12345678901")
    elif cap == "archivo_numero":
        datos["numero"] = "GOCS800101AB1"
    elif cap == "banco":
        datos.update(banco="BBVA", clabe=_clabe("01218000123456789"),
                     titular="Mario Esquivel Rangel")
    elif cap == "riesgo":
        datos["riesgo"] = 1
    elif cap == "entrevista":
        datos.update(fecha=(hoy - timedelta(days=2)).isoformat(),
                     quien="Luis Pichardo", resultado="apto")
    elif cap == "contactos":
        datos["contactos"] = [
            {"nombre": "Rosa Rangel", "parentesco": "Madre",
             "telefono": "55 1111 2222"},
            {"nombre": "Pedro Esquivel", "parentesco": "Hermano",
             "telefono": "55 3333 4444"}]
    elif cap == "prueba":
        datos.update(resultado="negativo", aplico="Caseta Reforma")
    if vig == "documento":
        campos["vence_en"] = (hoy + timedelta(days=900)).isoformat()
    elif vig == "meses":
        campos["fecha_documento"] = (hoy - timedelta(days=20)).isoformat()
    return datos, campos, archivos


def _cargar(cliente, h, persona_id, req, hoy, validar=True, **cambios):
    datos, campos, archivos = _para(req, hoy)
    datos.update(cambios.pop("datos", {}))
    campos.update(cambios)
    return cliente.post(
        f"/freelance/{persona_id}/expediente/{req['requisito_id']}",
        data={"datos": json.dumps(datos), "validar": "true" if validar else "false",
              **campos},
        files=archivos or None, headers=h)


def _completar(cliente, sesion, persona_id, sin=()):
    """Recursos Humanos carga y valida todo lo de su tipo."""
    h = sesion("rrhh")
    exp = cliente.get(f"/freelance/{persona_id}/expediente", headers=h).json()
    hoy = date.today()
    for req in exp["requisitos"]:
        if req["para_programado"] or req["clave"] in sin:
            continue
        r = _cargar(cliente, h, persona_id, req, hoy)
        assert r.status_code == 201, (req["clave"], r.text)
    return cliente.get(f"/freelance/{persona_id}/expediente", headers=h).json()


def _servicio(cliente, sesion, datos, desde=40, dias=1, tipo="eventual",
              modalidad="full_day"):
    h = sesion("consultor")
    return crear_servicio(cliente, h, datos, [
        jornada(manana(desde + i), datos["modalidades"][modalidad]["id"])
        for i in range(dias)], tipo=tipo,
        consultor_id=datos["personal"]["Ana Solis"]["id"])


def _equipo(servicio):
    return servicio["equipos"][0]["id"]


def _asignar_equipo(cliente, h, servicio, persona_id):
    return cliente.post(
        f"/servicios/equipos/{_equipo(servicio)}/asignar-personal",
        json={"persona_id": persona_id,
              "rol_id": rol_por_omision(cliente, h), "forzar": True},
        headers=h)


# ================================================= la lista de RRHH

def test_la_lista_de_mexico_es_la_de_recursos_humanos(db, datos):
    """Programado: quince y el aviso de privacidad. Emergencia: nueve y el
    aviso, con la prueba rapida de la caseta aparte. La migracion siembra
    en produccion la misma lista."""
    reqs = motor.requisitos_de(db, datos["mx"]["id"])
    programado = motor.del_tipo(reqs, "programado")
    emergencia = motor.del_tipo(reqs, "emergencia")
    assert len(programado) == 16
    assert len(emergencia) == 10
    assert [r.clave for r in emergencia if r.vigencia == "servicio"] == ["caseta"]
    assert {r.clave for r in programado} >= {"privacidad", "veritas",
                                             "entrevista", "antecedentes"}
    assert "privacidad" in {r.clave for r in emergencia}

    migracion = _migracion()
    campos = ("clave", "nombre", "detalle", "programado", "emergencia",
              "captura", "vigencia", "vigencia_meses", "antiguedad_meses",
              "orden")
    assert [tuple(r[c] for c in campos) for r in motor.REQUISITOS_MEXICO] \
        == migracion.REQUISITOS_MEXICO


def test_los_puestos_de_la_migracion_son_los_de_la_propuesta():
    from app import puestos_base
    migracion = _migracion()
    for p in puestos_base.PUESTOS:
        de_freelance = {a for a in p["actividades"] if a.startswith("freelance.")}
        assert de_freelance == set(migracion.ACTIVIDADES.get(p["nombre"], [])), \
            p["nombre"]
    rh = next(p for p in puestos_base.PUESTOS if p["nombre"] == "Recursos Humanos")
    assert {"freelance.validar", "freelance.expediente"} <= rh["actividades"]
    dirop = next(p for p in puestos_base.PUESTOS
                 if p["nombre"] == "Dirección de operaciones")
    assert "freelance.autorizar" in dirop["actividades"]
    assert "freelance.validar" not in dirop["actividades"]


# ============================================================= el alta

def test_el_consultor_lo_da_de_alta_y_la_central_solo_lo_ve(
        cliente, sesion, datos, nuevos, db):
    h = sesion("consultor")
    persona_id = _alta(cliente, h, datos, nuevos, tipo="emergencia")
    persona = db.get(m.Persona, persona_id)
    assert persona.es_freelance and persona.activo and not persona.oficina
    assert persona.nombre == "Mario Esquivel Rangel"
    assert persona.telefono.startswith("+52")
    ficha = db.query(m.Freelance).filter_by(persona_id=persona_id).one()
    assert ficha.tipo == "emergencia"
    assert ficha.alta_por_id == datos["personal"]["Ana Solis"]["id"]

    # El correo es su llave: no se repite.
    r = cliente.post("/freelance", json={
        "nombre": "Otro", "apellidos": "Igual", "telefono": "5512345678",
        "correo": persona.correo.upper(), "plaza_id": datos["cdmx"]["id"],
        "tipo": "programado"}, headers=h)
    assert r.status_code == 409, r.text

    # La central lo ve --si esta listo, sus costos--, no lo da de alta
    # ni abre su expediente.
    c = sesion("central")
    assert cliente.get(f"/freelance/{persona_id}", headers=c).status_code == 200
    assert cliente.post("/freelance", json={
        "nombre": "X", "apellidos": "Y", "telefono": "5512345678",
        "correo": "x@prueba111.mx", "plaza_id": datos["cdmx"]["id"],
        "tipo": "programado"}, headers=c).status_code == 403
    assert cliente.get(f"/freelance/{persona_id}/expediente",
                       headers=c).status_code == 403
    assert cliente.get(f"/freelance/{persona_id}/expediente",
                       headers=h).status_code == 403

    lista = cliente.get(f"/freelance?pais_id={datos['mx']['id']}", headers=c).json()
    fila = next(x for x in lista if x["persona_id"] == persona_id)
    assert fila["tipo"] == "emergencia"
    assert fila["expediente"]["estado"] == "faltan"
    assert fila["expediente"]["total"] == 9
    assert fila["costos"]["full_day"] is None

    # El tipo lo cambia Recursos Humanos, no quien lo dio de alta.
    assert cliente.patch(f"/freelance/{persona_id}", json={"tipo": "programado"},
                         headers=h).status_code == 403
    assert cliente.patch(f"/freelance/{persona_id}", json={"tipo": "programado"},
                         headers=sesion("rrhh")).status_code == 200


def test_la_foto_sale_en_la_hoja(cliente, sesion, datos, nuevos, db):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    r = cliente.put(f"/freelance/{persona_id}/foto",
                    files={"archivo": ("cara.png", PIXEL, "image/png")},
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(m.Persona, persona_id).foto_url.startswith("data:image/png")


def test_los_costos_los_pone_direccion_y_no_el_consultor(
        cliente, sesion, datos, nuevos, db):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    r = cliente.put(f"/freelance/{persona_id}/costos", json={
        "dia_completo": "2000", "medio_dia": "1200", "transfer": "800"},
        headers=sesion("consultor"))
    assert r.status_code == 403
    r = cliente.put(f"/freelance/{persona_id}/costos", json={
        "dia_completo": "2000", "medio_dia": None, "transfer": "800"},
        headers=sesion("diroperaciones"))
    assert r.status_code == 400 and "medio día" in r.text
    costos = _costos(cliente, sesion, persona_id)
    assert costos == {"full_day": 2000.0, "medio_dia": 1200.0,
                      "transfer": 800.0, "hora_extra": 200.0, "moneda": "MXN"}
    # Viven donde el corte del lunes les paga.
    tarifas = db.query(m.TarifaFreelance).filter_by(persona_id=persona_id).all()
    assert len(tarifas) == 3
    assert sum(1 for t in tarifas if t.costo_hora_extra is not None) == 1


# ======================================================== el expediente

def test_lo_que_se_carga_se_revisa_antes_de_guardar(cliente, sesion, datos, nuevos):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    h = sesion("rrhh")
    exp = cliente.get(f"/freelance/{persona_id}/expediente", headers=h).json()
    req = {r["clave"]: r for r in exp["requisitos"]}
    hoy = date.today()

    r = _cargar(cliente, h, persona_id, req["banco"], hoy,
                datos={"clabe": "012180001234567890"})
    assert r.status_code == 400 and "CLABE" in r.text
    r = _cargar(cliente, h, persona_id, req["domicilio"], hoy,
                fecha_documento=(hoy - timedelta(days=120)).isoformat())
    assert r.status_code == 400 and "más de 3 meses" in r.text
    r = _cargar(cliente, h, persona_id, req["licencia"], hoy, vence_en="")
    assert r.status_code == 400
    r = _cargar(cliente, h, persona_id, req["curp"], hoy,
                datos={"numero": "NO-ES-CURP"})
    assert r.status_code == 400
    r = cliente.post(
        f"/freelance/{persona_id}/expediente/{req['responsiva']['requisito_id']}",
        data={"datos": "{}"},
        files=[("archivos", ("virus.exe", b"MZ....", "application/octet-stream"))],
        headers=h)
    assert r.status_code == 400
    r = _cargar(cliente, h, persona_id, req["contactos"], hoy,
                datos={"contactos": [{"nombre": "Solo", "parentesco": "Uno",
                                      "telefono": "5512341234"}]})
    assert r.status_code == 400


def test_recursos_humanos_valida_y_direccion_carga_para_revision(
        cliente, sesion, datos, nuevos, db):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    rh, dirop = sesion("rrhh"), sesion("diroperaciones")
    exp = cliente.get(f"/freelance/{persona_id}/expediente", headers=dirop).json()
    req = {r["clave"]: r for r in exp["requisitos"]}
    hoy = date.today()

    # Direccion de operaciones carga, pero no valida.
    r = _cargar(cliente, dirop, persona_id, req["banco"], hoy, validar=True)
    assert r.status_code == 403
    r = _cargar(cliente, dirop, persona_id, req["banco"], hoy, validar=False)
    assert r.status_code == 201, r.text
    doc_id = r.json()["documento_id"]
    assert r.json()["estado"] == "por_revisar"
    db.expire_all()
    assert db.get(m.Persona, persona_id).clabe is None     # aun no rige

    assert cliente.post(f"/freelance/documentos/{doc_id}/validar",
                        headers=dirop).status_code == 403
    assert cliente.post(f"/freelance/documentos/{doc_id}/rechazar",
                        json={"motivo": "no"}, headers=rh).status_code == 400
    assert cliente.post(f"/freelance/documentos/{doc_id}/validar",
                        headers=rh).status_code == 200
    db.expire_all()
    persona = db.get(m.Persona, persona_id)
    assert persona.banco == "BBVA" and persona.clabe.endswith(
        _clabe("01218000123456789")[-4:])

    # El numero completo: finanzas y direccion general; los demas, recortado.
    ficha = cliente.get(f"/freelance/{persona_id}", headers=rh).json()
    assert "clabe" not in ficha and ficha["clabe_recortada"].startswith("····")
    assert cliente.get(f"/freelance/{persona_id}",
                       headers=sesion("dirgeneral")).json()["clabe"] == persona.clabe
    exp = cliente.get(f"/freelance/{persona_id}/expediente", headers=rh).json()
    banco = next(r for r in exp["requisitos"] if r["clave"] == "banco")
    assert banco["estado"] == "validado"
    assert "clabe" not in banco["efectivo"]["datos"]

    # Rechazar con motivo, y la nueva carga reemplaza la rechazada.
    r = _cargar(cliente, dirop, persona_id, req["referencias"], hoy, validar=False)
    doc = r.json()["documento_id"]
    assert cliente.post(f"/freelance/documentos/{doc}/rechazar",
                        json={"motivo": "La carta no trae firma"},
                        headers=rh).status_code == 200
    exp = cliente.get(f"/freelance/{persona_id}/expediente", headers=rh).json()
    ref = next(r for r in exp["requisitos"] if r["clave"] == "referencias")
    assert ref["estado"] == "rechazado"
    assert ref["pendiente"]["motivo_rechazo"] == "La carta no trae firma"
    _cargar(cliente, rh, persona_id, req["referencias"], hoy)
    exp = cliente.get(f"/freelance/{persona_id}/expediente", headers=rh).json()
    ref = next(r for r in exp["requisitos"] if r["clave"] == "referencias")
    assert ref["estado"] == "validado" and ref["anteriores"] == 1

    # El archivo se abre con permiso, y solo con permiso.
    archivo_id = ref["efectivo"]["archivos"][0]["id"]
    r = cliente.get(f"/freelance/archivos/{archivo_id}", headers=rh)
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert cliente.get(f"/freelance/archivos/{archivo_id}",
                       headers=sesion("consultor")).status_code == 403


def test_la_renovacion_no_le_quita_lo_asignable_mientras_la_revisan(
        cliente, sesion, datos, nuevos):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    _costos(cliente, sesion, persona_id)
    exp = _completar(cliente, sesion, persona_id)
    assert exp["resumen"]["estado"] == "listo", exp["resumen"]
    req = next(r for r in exp["requisitos"] if r["clave"] == "toxicologica")
    r = _cargar(cliente, sesion("diroperaciones"), persona_id, req, date.today(),
                validar=False)
    assert r.status_code == 201
    exp = cliente.get(f"/freelance/{persona_id}/expediente",
                      headers=sesion("rrhh")).json()
    assert exp["resumen"]["estado"] == "listo"
    assert exp["resumen"]["esperan_revision"] == 1


def test_el_estado_dice_vencido_por_vencer_y_listo(db, cliente, sesion, datos,
                                                   nuevos):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    _completar(cliente, sesion, persona_id)
    persona, ficha = motor.ficha_de(db, persona_id)
    hoy = date.today()
    assert motor.expediente(db, persona, ficha, hoy)["estado"] == "listo"
    # La toxicologica vale seis meses desde su fecha.
    vence = motor.sumar_meses(hoy - timedelta(days=20), 6)
    info = motor.expediente(db, persona, ficha, vence - timedelta(days=10))
    assert info["estado"] == "listo"
    assert info["por_vencer"][0]["nombre"] == "Prueba toxicológica en laboratorio"
    info = motor.expediente(db, persona, ficha, vence + timedelta(days=1))
    assert info["estado"] == "vencido" and not info["asignable"]


# ======================================================== al asignar

def test_sin_expediente_no_se_asigna_y_la_urgencia_lo_abre(
        cliente, sesion, datos, nuevos, db):
    h = sesion("consultor")
    persona_id = _alta(cliente, h, datos, nuevos)
    servicio = _servicio(cliente, sesion, datos, desde=45)

    # Sin costos: ni con urgencia.
    r = _asignar_equipo(cliente, h, servicio, persona_id)
    assert r.status_code == 409
    assert "costo" in r.json()["detail"]["mensaje"]

    _costos(cliente, sesion, persona_id)
    r = _asignar_equipo(cliente, h, servicio, persona_id)
    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert detalle["codigo"] == "freelance_no_asignable"
    assert detalle["freelance"]["puede_pedir"] is True

    # La lista de a quien asignar ya lo dice, antes del clic.
    rec = cliente.get(
        f"/servicios/equipos/{_equipo(servicio)}/recomendaciones"
        f"?categoria_id={datos['categorias']['suv_blindada']['id']}",
        headers=h).json()["personal"]
    todos = [f for g in ("disponibles", "con_alerta", "no_disponibles",
                         "de_otras_ciudades") for f in rec.get(g) or []]
    suya = next(f for f in todos if f["persona_id"] == persona_id)
    assert suya["freelance"]["asignable"] is False
    assert suya["freelance"]["estado"] == "faltan"
    assert suya["freelance"]["costos"]["full_day"] == 2000.0

    # El consultor pide la urgencia; direccion de operaciones la autoriza.
    r = cliente.post(f"/freelance/{persona_id}/urgencias", json={
        "servicio_id": servicio["id"], "motivo": "corto"}, headers=h)
    assert r.status_code == 400
    r = cliente.post(f"/freelance/{persona_id}/urgencias", json={
        "servicio_id": servicio["id"],
        "motivo": "El conductor de planta se enfermó y no hay otro en CDMX"},
        headers=h)
    assert r.status_code == 201 and r.json()["estado"] == "pedida"
    bandeja = cliente.get("/direccion/bandeja",
                          headers=sesion("diroperaciones")).json()
    pedida = next(x for x in bandeja["freelance_por_autorizar"]
                  if x["persona_id"] == persona_id)
    assert pedida["folio"] == servicio["folio"]
    assert "le falta" in pedida["faltaba"]
    assert cliente.post(f"/freelance/urgencias/{pedida['id']}/autorizar",
                        json={}, headers=h).status_code == 403
    assert _asignar_equipo(cliente, h, servicio, persona_id).status_code == 409
    assert cliente.post(f"/freelance/urgencias/{pedida['id']}/autorizar",
                        json={"respuesta": "Solo este servicio"},
                        headers=sesion("diroperaciones")).status_code == 200
    r = _asignar_equipo(cliente, h, servicio, persona_id)
    assert r.status_code == 200, r.text
    # Vale solo para ese servicio.
    otro = _servicio(cliente, sesion, datos, desde=50)
    assert _asignar_equipo(cliente, h, otro, persona_id).status_code == 409
    historial = cliente.get(f"/freelance/{persona_id}", headers=h).json()["historial"]
    assert {"urgencia pedida", "urgencia autorizada"} <= {x["accion"] for x in historial}


def test_listo_y_con_costos_se_asigna_como_cualquiera(
        cliente, sesion, datos, nuevos):
    h = sesion("consultor")
    persona_id = _alta(cliente, h, datos, nuevos)
    _costos(cliente, sesion, persona_id)
    _completar(cliente, sesion, persona_id)
    servicio = _servicio(cliente, sesion, datos, desde=46)
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"], persona_id=persona_id)[0]
    assert r.status_code == 200, r.text
    # Sale en su lista de servicios y como ultimo servicio.
    ficha = cliente.get(f"/freelance/{persona_id}", headers=h).json()
    assert ficha["servicios"][0]["folio"] == servicio["folio"]
    assert ficha["proximo_servicio"]["folio"] == servicio["folio"]


def test_el_freelance_no_va_en_implantados(cliente, sesion, datos, nuevos, db):
    """Decision 10: sus costos son solo de eventuales. La plantilla del
    mes no lo acepta, el dia no lo cubre y la puerta de asignar lo
    rechaza aunque llegue por la API."""
    from fastapi import HTTPException
    from app import implantado
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    persona = db.get(m.Persona, persona_id)
    assert "freelance" in implantado.por_que_no_va(db, persona, datos["cdmx"]["id"])
    with pytest.raises(HTTPException) as error:
        implantado._que_pueda_cubrir(db, persona_id)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        motor.revisar_para_asignar(
            db, persona, m.Servicio(tipo=m.TipoServicio.IMPLANTADO), {"full_day"})
    assert "implantados" in error.value.detail["mensaje"]
    # Y en la lista de a quien asignar de un implantado no sale.
    bloque = {"disponibles": [{"persona_id": persona_id, "es_freelance": True},
                              {"persona_id": 1, "es_freelance": False}]}
    motor.enriquecer(db, bloque, m.Servicio(tipo=m.TipoServicio.IMPLANTADO),
                     {"implantado"})
    assert [f["persona_id"] for f in bloque["disponibles"]] == [1]


def test_el_de_emergencia_que_repite_tiene_quince_dias(
        cliente, sesion, datos, nuevos, db):
    h = sesion("consultor")
    persona_id = _alta(cliente, h, datos, nuevos, tipo="emergencia")
    _costos(cliente, sesion, persona_id)
    exp = _completar(cliente, sesion, persona_id)
    assert exp["resumen"]["estado"] == "listo", exp["resumen"]
    assert exp["resumen"]["total"] == 9
    assert exp["resumen"]["para_programado"]["faltan"]

    primero = _servicio(cliente, sesion, datos, desde=30)
    assert _asignar_equipo(cliente, h, primero, persona_id).status_code == 200
    db.expire_all()
    assert db.query(m.Freelance).filter_by(persona_id=persona_id).one() \
        .plazo_programado is None

    segundo = _servicio(cliente, sesion, datos, desde=35)
    r = _asignar_equipo(cliente, h, segundo, persona_id)
    assert r.status_code == 200, r.text
    db.expire_all()
    ficha = db.query(m.Freelance).filter_by(persona_id=persona_id).one()
    assert ficha.plazo_programado == manana(30) + timedelta(days=15)
    # Recursos Humanos se entero.
    aviso = (db.query(m.Notificacion)
             .filter(m.Notificacion.correo == "rrhh@centauro.lat")
             .order_by(m.Notificacion.id.desc()).first())
    assert aviso is not None and "segundo servicio" in aviso.asunto

    # Con el plazo corriendo, su estado lo dice; vencido, no se asigna.
    persona = db.get(m.Persona, persona_id)
    assert motor.expediente(db, persona, ficha)["estado"] == "plazo"
    vencido = motor.expediente(db, persona, ficha,
                               ficha.plazo_programado + timedelta(days=1))
    assert vencido["estado"] == "plazo_vencido" and not vencido["asignable"]

    # Completo lo de programado, pasa a programado y el plazo se borra.
    rh = sesion("rrhh")
    exp = cliente.get(f"/freelance/{persona_id}/expediente", headers=rh).json()
    for req in exp["requisitos"]:
        if req["para_programado"]:
            assert _cargar(cliente, rh, persona_id, req,
                           date.today()).status_code == 201
    db.expire_all()
    ficha = db.query(m.Freelance).filter_by(persona_id=persona_id).one()
    assert ficha.tipo == "programado" and ficha.plazo_programado is None


def test_el_acceso_a_la_app_se_abre_con_el_expediente_listo(
        cliente, sesion, datos, nuevos, db):
    h = sesion("consultor")
    persona_id = _alta(cliente, h, datos, nuevos)
    r = cliente.post(f"/freelance/{persona_id}/acceso", headers=h)
    assert r.status_code == 409
    _completar(cliente, sesion, persona_id)
    r = cliente.post(f"/freelance/{persona_id}/acceso", headers=h)
    assert r.status_code == 200, r.text
    usuario = db.query(m.Usuario).filter_by(persona_id=persona_id).one()
    assert usuario.rol == m.Rol.PERSONAL_SEGURIDAD and usuario.activo
    # La central lo encuentra para dictarle su codigo.
    r = cliente.get("/auth/campo/buscar?q=Esquivel", headers=sesion("central"))
    assert any(x["persona_id"] == persona_id for x in r.json()), r.text
    # Y la baja le cierra la puerta.
    assert cliente.post(f"/freelance/{persona_id}/baja",
                        json={"motivo": "Ya no colabora"},
                        headers=h).status_code == 200
    db.expire_all()
    assert not db.query(m.Usuario).filter_by(persona_id=persona_id).one().activo
    assert cliente.post(f"/freelance/{persona_id}/reactivar",
                        headers=h).status_code == 200
    db.expire_all()
    assert db.query(m.Usuario).filter_by(persona_id=persona_id).one().activo


# =========================================================== los avisos

def test_recursos_humanos_se_entera_de_lo_que_vence(
        cliente, sesion, datos, nuevos, db):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    _completar(cliente, sesion, persona_id)
    hoy = date.today()
    vence = motor.sumar_meses(hoy - timedelta(days=20), 6)
    antes = db.query(m.Notificacion).count()
    r = motor.revisar_vencimientos(db, hoy=vence - timedelta(days=30))
    assert r["avisados"] == 1
    assert motor.revisar_vencimientos(db, hoy=vence - timedelta(days=29))["avisados"] == 0
    assert motor.revisar_vencimientos(db, hoy=vence)["avisados"] == 1
    assert motor.revisar_vencimientos(db, hoy=vence)["avisados"] == 0
    nuevas = (db.query(m.Notificacion).order_by(m.Notificacion.id)
              .offset(antes).all())
    assert {n.correo for n in nuevas} == {"rrhh@centauro.lat"}
    assert "vence hoy" in nuevas[-1].asunto


# ========================================================= el deposito

class _Google:
    """El deposito de mentiras: guarda y dice que tiene."""

    def __init__(self):
        self.deposito, self.prefijo, self.objetos = "centauro-expedientes", "", {}

    def ruta(self, relativa):
        return relativa

    def subir(self, ruta, datos, tipo, metadatos):
        self.objetos[ruta] = datos

    def describir(self, ruta):
        import base64
        import hashlib
        datos = self.objetos.get(ruta)
        if datos is None:
            return None
        return {"size": str(len(datos)),
                "md5Hash": base64.b64encode(hashlib.md5(datos).digest()).decode()}

    def bajar(self, ruta):
        return self.objetos[ruta], "application/pdf"


def test_los_archivos_se_mudan_al_deposito_sin_perder_nada(
        cliente, sesion, datos, nuevos, db, monkeypatch):
    persona_id = _alta(cliente, sesion("consultor"), datos, nuevos)
    _completar(cliente, sesion, persona_id, sin=())
    assert motor.mudar_pendientes(db)["omitido"] == "sin EXPEDIENTES_DESTINO"
    monkeypatch.setattr(motor.settings, "expedientes_destino",
                        "gs://centauro-expedientes")
    google = _Google()
    r = motor.mudar_pendientes(db, google=google)
    assert r["mudados"] >= 1 and r["fallas"] == 0
    fila = db.query(m.ArchivoFreelance).first()
    db.refresh(fila)
    assert fila.contenido is None and fila.objeto.startswith("gs://")
    assert motor.leer_archivo(fila, google) == PDF


# ============================================================ la consola

def test_la_consola_trae_la_pestana_la_ficha_y_el_catalogo():
    personal = _js("personal.js")
    assert "pestanaFreelance" in personal
    ficha = _js("freelance.js")
    for pedazo in ("/freelance/", "/expediente", "/costos", "/urgencias",
                   "/acceso", "/foto"):
        assert pedazo in ficha, pedazo
    assert "requisitos-freelance" in _js("catalogos_pantalla.js")
    assert "tarifas-freelance" not in _js("catalogos_pantalla.js").split(
        "const DE_DINERO")[1].split("]")[0]
    assert "freelance_por_autorizar" in _js("direccion.js")
    servicio = _js("servicio.js")
    assert "avisoFreelance(p, hecho)" in servicio and "fre.asignable" in servicio
    assert "/urgencias" in ficha
    idioma = _js("idioma.js")
    for clave in ("fre_titulo_tab:", "fre_dar_de_alta:", "fre_est_listo:",
                  "fre_pedir_autorizacion:", "ctl_requisitos:"):
        assert idioma.count("    " + clave) == 3, clave

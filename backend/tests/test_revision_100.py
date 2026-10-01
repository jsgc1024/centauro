# -*- coding: utf-8 -*-
"""Seccion 100: accesos, correo, reloj y servidor.

Tercera tanda de la revision del 28 de septiembre: el correo con
mayusculas al entrar, el repartidor de accesos, la cuota por direccion,
el codigo de campo, el tabulador con rastro, las dos manos al editar un
puesto, la baja por catalogos, los textos largos, el tope de las
peticiones; el taller de Odoo, el cambio de oficina a seguridad, la vida
de los avisos, la cola de correo, el reloj, el GPS por fases.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app import models as m

DOMINIO = "revision-100.lat"


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def como_estaba(base_de_pruebas):
    """Las cuentas y los puestos son catalogo: se dejan como estaban."""
    with base_de_pruebas.begin() as con:
        cuentas = con.execute(text(
            "SELECT id, rol, categoria_id, activo, correo FROM usuario")).all()
        extras = [f[0] for f in con.execute(text("SELECT id FROM permiso_extra"))]
        puestos = [f[0] for f in con.execute(text("SELECT id FROM categoria_acceso"))]
    yield
    with base_de_pruebas.begin() as con:
        con.execute(text("DELETE FROM permiso_extra WHERE NOT (id = ANY(:ids))"),
                    {"ids": extras})
        ids = [f[0] for f in con.execute(text(
            "SELECT id FROM persona WHERE correo LIKE :d"), {"d": f"%@{DOMINIO}"})]
        if ids:
            con.execute(text("DELETE FROM invitacion WHERE usuario_id IN "
                             "(SELECT id FROM usuario WHERE persona_id = ANY(:ids))"),
                        {"ids": ids})
            con.execute(text("DELETE FROM usuario WHERE persona_id = ANY(:ids)"),
                        {"ids": ids})
            con.execute(text("DELETE FROM persona WHERE id = ANY(:ids)"), {"ids": ids})
        for u in cuentas:
            con.execute(text("UPDATE usuario SET rol = :rol, categoria_id = :c, "
                             "activo = :a, correo = :correo WHERE id = :id"),
                        {"rol": u.rol, "c": u.categoria_id, "a": u.activo,
                         "correo": u.correo, "id": u.id})
        nuevos = [i for (i,) in con.execute(text("SELECT id FROM categoria_acceso"))
                  if i not in puestos]
        if nuevos:
            con.execute(text("UPDATE usuario SET categoria_id = NULL "
                             "WHERE categoria_id = ANY(:ids)"), {"ids": nuevos})
            con.execute(text("DELETE FROM actividad_de_categoria "
                             "WHERE categoria_id = ANY(:ids)"), {"ids": nuevos})
            con.execute(text("DELETE FROM categoria_acceso WHERE id = ANY(:ids)"),
                        {"ids": nuevos})


def _entrar(cliente, correo, contrasena="centauro2026"):
    return cliente.post("/auth/token",
                        data={"username": correo, "password": contrasena})


def _persona_nueva(db, nombre="Persona Revision"):
    plaza = db.query(m.Plaza).first()
    p = m.Persona(nombre=nombre, correo=f"{uuid.uuid4().hex[:8]}@{DOMINIO}",
                  plaza_id=plaza.id)
    db.add(p)
    db.commit()
    return p.id


def _puestos(cliente, sesion):
    h = sesion("dirgeneral")
    assert cliente.post("/auth/categorias/base", headers=h).status_code == 200
    return {p["nombre"]: p for p in cliente.get("/auth/categorias", headers=h).json()}


# ================================================================ los accesos

def test_el_correo_entra_con_mayusculas_y_espacios(cliente, datos):
    """El teclado del telefono pone la primera letra en mayuscula; el
    correo se guarda en minusculas. Se comparaba exacto, y cada intento
    asi gastaba el tope de intentos."""
    from app import intentos
    for escrito in ("Juan.Ramirez@centauro.lat", " juan.ramirez@centauro.lat ",
                    "JUAN.RAMIREZ@CENTAURO.LAT"):
        r = _entrar(cliente, escrito)
        assert r.status_code == 200, (escrito, r.text)
        assert r.json()["nombre"] == "Juan Ramirez"
    intentos.limpiar("juan.ramirez@centauro.lat", "testclient")


def test_recuperar_y_el_codigo_tambien_reconocen_el_correo_como_sea(cliente, db):
    """Las otras dos puertas publicas usan la misma llave."""
    from app import auth
    assert auth.llave_de_correo("  Juan.Ramirez@Centauro.lat ") == "juan.ramirez@centauro.lat"
    usuario = auth.usuario_por_correo(db, "JUAN.ramirez@centauro.lat")
    assert usuario is not None and usuario.correo == "juan.ramirez@centauro.lat"
    assert auth.usuario_por_correo(db, "   ") is None
    assert auth.usuario_por_correo(db, "nadie@centauro.lat") is None


def test_cada_puerta_cuenta_su_propia_direccion():
    """Cuarenta 'olvide mi contrasena' desde una direccion no dejan sin
    entrar a la oficina entera: el tope por IP es por puerta."""
    from app import intentos
    entrar = dict(intentos._claves("juan@x.lat", "10.0.0.1"))
    recuperar = dict(intentos._claves("recuperar:juan@x.lat", "10.0.0.1"))
    codigo = dict(intentos._claves("codigo:juan@x.lat", "10.0.0.1"))
    llaves_ip = [k for k in list(entrar) + list(recuperar) + list(codigo)
                 if k.startswith("intentos:ip:")]
    assert len(set(llaves_ip)) == 3, llaves_ip
    assert "intentos:ip:entrar:10.0.0.1" in entrar
    assert "intentos:ip:recuperar:10.0.0.1" in recuperar
    assert "intentos:ip:codigo:10.0.0.1" in codigo


def test_el_contador_del_codigo_toma_la_fila(db):
    """Cinco fallos y se muere, aunque lleguen juntos: la fila del codigo
    se bloquea al contar el fallo."""
    from app import contrasenas
    from sqlalchemy.dialects import postgresql
    consulta = (db.query(m.Invitacion)
                .filter(m.Invitacion.usuario_id == 1)
                .order_by(m.Invitacion.id.desc()).with_for_update())
    assert "FOR UPDATE" in str(consulta.statement.compile(dialect=postgresql.dialect()))
    # Y la funcion lo usa: sin codigo vigente contesta None, con o sin candado.
    assert contrasenas.codigo_vigente(db, 999_999, bloquear=True) is None


def test_recursos_humanos_no_fabrica_un_repartidor_quitando_el_puesto(
        cliente, sesion, db, como_estaba):
    """Seccion 83 por la puerta de atras: Capacitacion (rol recursos
    humanos, no reparte) y despues quitarle el puesto dejaba a la persona
    como recursos humanos sin puesto, que reparte de fabrica."""
    rh = sesion("rrhh")
    puestos = _puestos(cliente, sesion)
    pid = _persona_nueva(db)
    r = cliente.post("/auth/usuarios", json={
        "persona_id": pid, "rol": "consultor",
        "categoria_id": puestos["Capacitación"]["categoria_id"]}, headers=rh)
    assert r.status_code == 201, r.text
    usuario_id = r.json()["usuario_id"]

    r = cliente.post(f"/auth/usuarios/{usuario_id}/categoria",
                     json={"categoria_id": None, "motivo": "prueba"}, headers=rh)
    assert r.status_code == 403, r.text
    assert "Dirección general" in r.json()["detail"]["mensaje"]
    # Direccion general si puede.
    r = cliente.post(f"/auth/usuarios/{usuario_id}/categoria",
                     json={"categoria_id": None, "motivo": "prueba"},
                     headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text


def test_recursos_humanos_no_fabrica_un_repartidor_con_un_puesto_sin_rol(
        cliente, sesion, db, como_estaba):
    """La otra puerta: con un puesto que no dice rol, cambiar el rol a
    uno que reparte ya no se salta el candado."""
    rh = sesion("rrhh")
    r = cliente.post("/auth/categorias", json={
        "nombre": f"Sin rol {uuid.uuid4().hex[:6]}", "actividades": ["bonos.ver"]},
        headers=rh)
    assert r.status_code == 201, r.text
    puesto_id = r.json()["categoria_id"]
    pid = _persona_nueva(db)
    r = cliente.post("/auth/usuarios", json={
        "persona_id": pid, "rol": "consultor", "categoria_id": puesto_id},
        headers=rh)
    assert r.status_code == 201, r.text
    usuario_id = r.json()["usuario_id"]
    r = cliente.post(f"/auth/usuarios/{usuario_id}/rol",
                     json={"rol": "recursos_humanos", "motivo": "prueba"}, headers=rh)
    assert r.status_code == 403, r.text


def test_el_tabulador_deja_rastro_y_el_arranque_lo_ve(cliente, sesion, datos, db):
    """Lo que se paga por dia es dinero de configuracion: queda en la
    bitacora con antes y despues, y el arranque deja de decir 'montos de
    ejemplo'."""
    perfil = datos["perfiles"]["conductor_seguridad"]["id"]
    modalidad = datos["modalidades"]["full_day"]["id"]
    antes = db.query(m.RegistroAdmin).count()
    r = cliente.put("/nomina/tabulador", json={
        "pais_id": datos["mx"]["id"], "tipo_servicio": "eventual",
        "renglones": [{"perfil_id": perfil, "modalidad_id": modalidad,
                       "monto": "999.00", "monto_hora_extra": "99.00"}]},
        headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(m.RegistroAdmin).count() == antes + 1
    rastro = db.query(m.RegistroAdmin).order_by(m.RegistroAdmin.id.desc()).first()
    assert rastro.objeto == "comisiones"
    assert "conductor_seguridad/full_day 700 (+90)" in rastro.antes
    assert "conductor_seguridad/full_day 999 (+99)" in rastro.despues

    r = cliente.get("/manual/arranque?idioma=es", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    dinero = next(g for g in r.json()["grupos"] if g["clave"] == "dinero")
    pago = next(x for x in dinero["renglones"] if x["clave"] == "pago_dia")
    assert pago["tono"] == "ok", pago

    # Guardar lo mismo otra vez no escribe otro renglon.
    r = cliente.put("/nomina/tabulador", json={
        "pais_id": datos["mx"]["id"], "tipo_servicio": "eventual",
        "renglones": [{"perfil_id": perfil, "modalidad_id": modalidad,
                       "monto": "999.00", "monto_hora_extra": "99.00"}]},
        headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(m.RegistroAdmin).count() == antes + 1
    # Se regresa como estaba.
    cliente.put("/nomina/tabulador", json={
        "pais_id": datos["mx"]["id"], "tipo_servicio": "eventual",
        "renglones": [{"perfil_id": perfil, "modalidad_id": modalidad,
                       "monto": "700", "monto_hora_extra": "90"}]},
        headers=sesion("diroperaciones"))


def test_editar_un_puesto_no_junta_las_dos_manos(cliente, sesion, db, como_estaba):
    """Con 'autorizar bonos' como permiso de mas, agregarle 'pagar bonos'
    al puesto se rechaza: eran la misma mano."""
    rh = sesion("rrhh")
    r = cliente.post("/auth/categorias", json={
        "nombre": f"Cobranza {uuid.uuid4().hex[:6]}",
        "actividades": ["cierre.ver", "cierre.facturar"]}, headers=rh)
    assert r.status_code == 201, r.text
    puesto_id = r.json()["categoria_id"]
    pid = _persona_nueva(db)
    r = cliente.post("/auth/usuarios", json={
        "persona_id": pid, "rol": "finanzas", "categoria_id": puesto_id}, headers=rh)
    assert r.status_code == 201, r.text
    usuario_id = r.json()["usuario_id"]
    r = cliente.post(f"/auth/usuarios/{usuario_id}/permisos",
                     json={"actividad": "bonos.autorizar"}, headers=rh)
    assert r.status_code == 200, r.text
    r = cliente.patch(f"/auth/categorias/{puesto_id}",
                      json={"actividades": ["cierre.ver", "cierre.facturar", "bonos.pagar"]},
                      headers=rh)
    assert r.status_code == 409, r.text
    assert "bonos.autorizar" in r.json()["detail"]["mensaje"]
    # Sin la actividad que choca, el puesto si se edita.
    r = cliente.patch(f"/auth/categorias/{puesto_id}",
                      json={"actividades": ["cierre.ver", "cierre.facturar", "bonos.ver"]},
                      headers=rh)
    assert r.status_code == 200, r.text


def test_la_baja_por_catalogos_cierra_el_acceso(cliente, sesion, db, como_estaba):
    from app import auth as auth_mod
    rh = sesion("rrhh")
    pid = _persona_nueva(db, "Baja Catalogo")
    r = cliente.post("/auth/usuarios", json={"persona_id": pid, "rol": "consultor"},
                     headers=rh)
    assert r.status_code == 201, r.text
    u = db.get(m.Usuario, r.json()["usuario_id"])
    u.hash_contrasena = auth_mod.cifrar("una contrasena larga")
    db.commit()
    token = _entrar(cliente, u.correo, "una contrasena larga").json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert cliente.get("/auth/yo", headers=h).status_code == 200

    r = cliente.delete(f"/catalogos/personal/{pid}", headers=sesion("admin"))
    assert r.status_code == 204, r.text
    db.expire_all()
    assert db.get(m.Persona, pid).activo is False
    assert db.get(m.Usuario, u.id).activo is False
    assert cliente.get("/auth/yo", headers=h).status_code == 401
    assert _entrar(cliente, u.correo, "una contrasena larga").status_code == 403


def test_un_motivo_largo_se_rechaza_con_mensaje(cliente, sesion):
    rh = sesion("rrhh")
    usuarios = {u["correo"]: u for u in cliente.get("/auth/usuarios", headers=rh).json()}
    beatriz = usuarios["beatriz.roman@centauro.lat"]
    r = cliente.post(f"/auth/usuarios/{beatriz['usuario_id']}/desactivar",
                     json={"motivo": "x" * 401}, headers=rh)
    assert r.status_code == 422, r.text
    # Y lo que se escapa de los esquemas lo recorta la bitacora.
    from app import accesos
    from app.db import SessionLocal
    with SessionLocal() as db:
        actor = db.query(m.Usuario).filter_by(correo="rrhh@centauro.lat").one()
        accesos.anotar(db, actor, "prueba", "usuario", actor.id,
                       antes="a" * 300, despues="b" * 300, detalle="c" * 500)
        db.flush()
        fila = db.query(m.RegistroAdmin).order_by(m.RegistroAdmin.id.desc()).first()
        assert (len(fila.antes), len(fila.despues), len(fila.detalle)) == (200, 200, 400)
        db.rollback()


def test_un_dato_que_no_cabe_es_400_y_no_500():
    """La red de abajo: el DataError de la base se traduce."""
    from sqlalchemy.exc import DataError
    from app.main import dato_que_no_cabe

    class Original(Exception):
        pass
    falla = DataError("INSERT ...", {}, Original("value too long for type character varying(80)"))
    respuesta = dato_que_no_cabe(None, falla)
    assert respuesta.status_code == 400
    assert b"mas largo" in respuesta.body


def test_los_textos_de_la_central_y_el_alta_tienen_tope(cliente, sesion, datos):
    """Una descripcion de 601 letras o un idioma 'eng' contestan 422, no
    un error del servidor."""
    h = sesion("consultor")
    r = cliente.post("/contingencia/alertas", json={
        "canal": "llamada", "descripcion": "x" * 601}, headers=sesion("central"))
    assert r.status_code == 422, r.text
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"],
        "pais_id": datos["mx"]["id"], "plaza_id": datos["cdmx"]["id"],
        "idioma_ejecutivo": "eng", "equipos": []}, headers=h)
    assert r.status_code == 422, r.text


def test_una_peticion_que_pesa_demasiado_se_rechaza_sin_leerla():
    import asyncio
    from app.main import CuerpoConTope, TOPE_DE_CUERPO
    llegadas, respuestas = [], []

    async def adentro(scope, receive, send):
        llegadas.append(scope["path"])

    async def send(mensaje):
        respuestas.append(mensaje)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def correr():
        tope = CuerpoConTope(adentro)
        scope = {"type": "http", "path": "/auth/token", "method": "POST",
                 "headers": [(b"content-length", str(TOPE_DE_CUERPO + 1).encode())],
                 "query_string": b"", "scheme": "http", "server": ("x", 80),
                 "client": ("1.2.3.4", 1)}
        await tope(scope, receive, send)
        assert not llegadas
        assert respuestas[0]["status"] == 413
        # Lo normal pasa.
        scope["headers"] = [(b"content-length", b"120")]
        await tope(scope, receive, send)
        assert llegadas == ["/auth/token"]

    asyncio.run(correr())


# ================================================================ Odoo

ODOO0 = 8_700_000


@pytest.fixture
def sin_rastro_odoo(base_de_pruebas):
    """Lo que estas pruebas dan de alta desde un Odoo de mentiras se va."""
    yield
    from conftest import TABLAS_DE_OPERACION
    from app.seed import sembrar_recursos

    with base_de_pruebas.begin() as con:
        con.execute(text(f"TRUNCATE {', '.join(TABLAS_DE_OPERACION)} "
                         "RESTART IDENTITY CASCADE"))
        con.execute(text(
            "UPDATE persona SET odoo_id = NULL, oficina = false, "
            "puesto_odoo = NULL, area_odoo = NULL, odoo_sincronizado_en = NULL, "
            "baja_odoo_en = NULL, activo = true "
            "WHERE odoo_id >= :o AND correo NOT LIKE :d"),
            {"o": ODOO0, "d": f"%@{DOMINIO}"})
        ids = [f[0] for f in con.execute(text(
            "SELECT id FROM persona WHERE odoo_id >= :o OR correo LIKE :d"),
            {"o": ODOO0, "d": f"%@{DOMINIO}"})]
        if ids:
            con.execute(text("DELETE FROM invitacion WHERE usuario_id IN "
                             "(SELECT id FROM usuario WHERE persona_id = ANY(:ids))"),
                        {"ids": ids})
            con.execute(text("DELETE FROM usuario WHERE persona_id = ANY(:ids)"),
                        {"ids": ids})
            con.execute(text("DELETE FROM persona WHERE id = ANY(:ids)"),
                        {"ids": ids})
        con.execute(text("DELETE FROM cliente WHERE odoo_id >= :o"), {"o": ODOO0})
    sembrar_recursos()


def _unidad(n, **cambios):
    u = {"id": ODOO0 + n, "license_plate": f"R{n:02d}EVC",
         "category_id": [9, "MINIVAN"], "location": "Ciudad de México",
         "model_id": [4, "Toyota/SIENNA XSE"], "color": "Blanco",
         "model_year": "2023", "tag_ids": [1],
         "write_date": "2026-01-01 10:00:00", "active": True}
    u.update(cambios)
    return u


def _taller(n, dueno, **cambios):
    from app import odoo_flota
    r = {"id": 9_700_000 + n, "vehicle_id": [ODOO0 + dueno, "x"],
         "service_type_id": [3, "Correctivo"], "state": "running",
         odoo_flota.ENTRADA: str(date.today() + timedelta(days=2)),
         odoo_flota.SALIDA: None,
         "vendor_id": [7, "Taller Norte"], "description": "Frenos"}
    r.update(cambios)
    return r


class OdooFlotaFalso:
    def __init__(self, *unidades, taller=(), con_fechas=True):
        from app import odoo_flota
        self.unidades = {u["id"]: u for u in unidades}
        self.taller = {r["id"]: r for r in taller}
        self.con_fechas = con_fechas
        self._campos = list(odoo_flota.CAMPOS_TALLER)
        self._entrada, self._salida = odoo_flota.ENTRADA, odoo_flota.SALIDA

    def campos(self, modelo):
        campos = {c: {"type": "char"} for c in self._campos}
        if self.con_fechas:
            campos[self._entrada] = campos[self._salida] = {"type": "date"}
        return campos

    def leer(self, modelo, dominio, campos, archivados=False):
        if modelo == "fleet.vehicle.tag":
            return [{"id": 1, "name": "pe"}]
        if modelo == "fleet.vehicle.log.services":
            filas = list(self.taller.values())
        else:
            filas = [u for u in self.unidades.values()
                     if archivados or u.get("active", True)]
        for campo, operador, valor in dominio:
            filas = [f for f in filas if f["id"] in valor]
        return [{"id": f["id"], **{c: f.get(c, False) for c in campos}}
                for f in filas]


def test_sin_los_campos_del_taller_no_se_toca_el_taller(sin_rastro_odoo, db, datos):
    """Odoo Studio pierde las fechas: la lectura dice que no leyo el
    taller, y el taller guardado se queda. Y la vuelta lo marca como
    error, no como una vuelta 'ok' con el taller sin leer."""
    from app import odoo_flota
    odoo = OdooFlotaFalso(_unidad(1), taller=[_taller(1, 1)])
    odoo_flota.sincronizar(db, odoo, ensayo=False)
    assert db.query(m.TallerVehiculo).filter_by(odoo_id=9_700_001).count() == 1

    db.expire_all()
    roto = OdooFlotaFalso(_unidad(1), taller=[_taller(1, 1)], con_fechas=False)
    informe = odoo_flota.sincronizar(db, roto, ensayo=False)
    assert "no tiene los campos" in informe["taller"]["error"]
    assert db.query(m.TallerVehiculo).filter_by(odoo_id=9_700_001).count() == 1
    assert "no tiene los campos" in odoo_flota.resumen(informe)["error"]


class OdooPersonalFalso:
    def __init__(self, *empleados):
        self.empleados = {e["id"]: e for e in empleados}

    def leer(self, modelo, dominio, campos, archivados=False):
        if modelo == "ir.model.fields":
            # El campo de la cuenta existe; falta el permiso (ver `campos`).
            from app import odoo_personal
            return [{"id": 1, "name": odoo_personal.CAMPO_CUENTA}]
        filas = [e for e in self.empleados.values()
                 if archivados or e.get("active", True)]
        for campo, operador, valor in dominio:
            filas = [e for e in filas if e["id"] in valor]
        return [{"id": e["id"], **{c: e.get(c, False) for c in campos}}
                for e in filas]

    def campos(self, modelo, atributos=None):
        """Sin el campo de la cuenta bancaria (seccion 105): la lectura
        del personal pregunta por el antes de pedirlo."""
        from app import odoo_personal
        return {c: {"type": "char"} for c in odoo_personal.CAMPOS}

    def cambiar(self, n, **valores):
        self.empleados[ODOO0 + n].update(valores)


def _empleado_oficina(n, **cambios):
    e = {"id": ODOO0 + n, "name": f"Oficina Rev {n}",
         "job_id": [70, "Facturista"], "job_title": "Facturista",
         "department_id": [5, "Finanzas"],
         "work_location_id": [30, "Ciudad de México"],
         "work_email": f"oficina{n}@{DOMINIO}",
         "private_email": f"personal{n}@{DOMINIO}",
         "mobile_phone": "55 1234 5678",
         "write_date": "2026-09-01 10:00:00", "active": True}
    e.update(cambios)
    return e


def test_quien_pasa_de_oficina_a_seguridad_queda_pendiente(
        sin_rastro_odoo, db, cliente, sesion, datos):
    """Seccion 74, en los dos sentidos: la lectura del personal ya no se
    lleva a la calle a alguien de oficina ni le cambia el correo de su
    acceso; lo deja pendiente con su No. Odoo."""
    from app import odoo_oficina, odoo_personal
    odoo = OdooPersonalFalso(_empleado_oficina(1))
    odoo_oficina.sincronizar(db, odoo, ensayo=False)
    db.expire_all()
    p = db.query(m.Persona).filter_by(odoo_id=ODOO0 + 1).one()
    assert p.oficina is True
    r = cliente.post("/auth/usuarios", json={"persona_id": p.id, "rol": "finanzas"},
                     headers=sesion("admin"))
    assert r.status_code == 201, r.text

    odoo.cambiar(1, job_title="Personal de Seguridad",
                 job_id=[71, "Personal de Seguridad"])
    db.expire_all()
    informe = odoo_personal.sincronizar(db, odoo, ensayo=False)
    db.expire_all()
    p = db.query(m.Persona).filter_by(odoo_id=ODOO0 + 1).one()
    u = db.query(m.Usuario).filter_by(persona_id=p.id).one()
    pendientes = [x for x in informe["pendientes"] if x["odoo_id"] == ODOO0 + 1]
    assert pendientes and "de oficina" in " ".join(pendientes[0]["falta"])
    assert p.oficina is True
    assert u.correo == f"oficina1@{DOMINIO}" and u.rol == m.Rol.FINANZAS


def test_los_textos_largos_de_odoo_se_recortan_al_largo_de_su_columna(
        sin_rastro_odoo, db, datos):
    """Un modelo de 120 letras ya no tumba la lectura entera cada hora."""
    from app import odoo_flota
    largo = "Chevrolet/SUBURBAN PREMIER 4X4 BLINDADA NIVEL V PLUS EDICION " * 3
    odoo = OdooFlotaFalso(_unidad(2, model_id=[5, largo], color="Negro " * 20))
    informe = odoo_flota.sincronizar(db, odoo, ensayo=False)
    assert len(informe["altas"]) == 1
    v = db.query(m.Vehiculo).filter_by(odoo_id=ODOO0 + 2).one()
    assert len(v.marca_modelo) <= 80 and len(v.color) <= 40
    # Y la segunda lectura no lo ve como cambio.
    db.expire_all()
    assert odoo_flota.sincronizar(db, odoo, ensayo=True)["cambios"] == []


def test_los_clientes_sin_la_etiqueta_son_un_error_de_la_vuelta():
    from app import odoo_clientes
    informe = {"sin_etiqueta": "Protección ejecutiva", "leidos": 0, "altas": [],
               "vinculadas": [], "cambios": [], "bajas": [], "sin_rfc": [],
               "pendientes": []}
    assert "etiqueta" in odoo_clientes.resumen(informe)["error"]
    informe["sin_etiqueta"] = None
    assert "error" not in odoo_clientes.resumen(informe)


def test_una_lista_de_precios_dudosa_no_se_toma_como_de_mexico():
    from app.odoo_tarifarios_reglas import pais_de_la_lista
    paises = {"MX": 1, "BR": 2}
    # Clientes en dos paises: sin pais.
    assert pais_de_la_lista({"grupos": [], "moneda": "MXN"}, {1, 2}, paises, {})[0] is None
    # En dolares y sin clientes: sin pais.
    assert pais_de_la_lista({"grupos": [], "moneda": "USD"}, set(), paises, {})[0] is None
    # Lo que si dice su pais, lo dice.
    assert pais_de_la_lista({"grupos": [], "moneda": "BRL"}, set(), paises, {})[0] == 2
    assert pais_de_la_lista({"grupos": [], "moneda": "USD"}, {1}, paises, {})[0] == 1


def test_una_lectura_de_odoo_toma_su_candado(db):
    """Dos lecturas del mismo tipo no se pisan: la segunda espera."""
    from app import odoo_api
    odoo_api.candado(db, "flota")
    cuantos = db.execute(text(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
        "AND pid = pg_backend_pid()")).scalar()
    assert cuantos == 1
    db.rollback()


# ================================================================ el correo

def _aviso(db, plantilla=None, expira_en=None, hace_horas=0, correo="x@y.lat",
           estado="pendiente"):
    aviso = m.Notificacion(
        destinatario=m.Destinatario.COLABORADOR, canal=m.Canal.CORREO,
        correo=correo, asunto="Prueba", cuerpo="Cuerpo", plantilla=plantilla,
        expira_en=expira_en, estado=estado,
        enviada_en=datetime.now(timezone.utc) - timedelta(hours=hace_horas))
    db.add(aviso)
    db.commit()
    return aviso


def test_la_invitacion_vive_lo_que_vive_su_enlace(db):
    """Con el correo apagado dos dias, la invitacion (72 h) sale al
    encender; el aviso operativo de ayer, no."""
    from app import correo
    invitacion = _aviso(db, "acceso_invitacion",
                        expira_en=datetime.now() + timedelta(hours=70), hace_horas=48)
    operativo = _aviso(db, None, expira_en=datetime.now() + timedelta(hours=70),
                       hace_horas=48)
    encuesta = _aviso(db, "encuesta", expira_en=datetime.now() + timedelta(days=10),
                      hace_horas=100)
    vencida = _aviso(db, "acceso_invitacion",
                     expira_en=datetime.now() - timedelta(hours=1), hace_horas=80)
    assert correo.vencio(invitacion) is False
    assert correo.vencio(operativo) is True
    assert correo.vencio(encuesta) is False
    assert correo.vencio(vencida) is True
    # Y de un golpe, sin gastar el cupo de la vuelta.
    assert correo.vencer_lo_viejo(db) == 2
    db.commit()
    db.expire_all()
    assert (invitacion.estado, operativo.estado, encuesta.estado, vencida.estado) == (
        "pendiente", "vencida", "pendiente", "vencida")


def test_el_rechazo_del_destinatario_falla_de_una_y_el_proveedor_caido_espera(
        db, monkeypatch):
    import smtplib
    from app import correo
    monkeypatch.setattr(correo, "configurado", lambda: True)
    monkeypatch.setattr(correo, "versiones", lambda db_, a: ("t", "<p>h</p>"))
    rechazado = _aviso(db, correo="no-existe@y.lat")
    caido = _aviso(db, correo="bien@y.lat")

    def entregar(para, asunto, texto, html):
        if para == "no-existe@y.lat":
            raise smtplib.SMTPRecipientsRefused({para: (550, b"no such user")})
        raise smtplib.SMTPConnectError(421, "no contesta")
    monkeypatch.setattr(correo, "entregar", entregar)

    r = correo.despachar(db, solo=[rechazado.id, caido.id])
    db.expire_all()
    assert rechazado.estado == "fallida" and r["fallidos"] == 1
    assert caido.estado == "pendiente" and caido.intentos == 1
    assert caido.reintentar_en is not None
    assert caido.reintentar_en > datetime.now() + timedelta(minutes=4)
    # Mientras espera su reintento, la vuelta no lo toma.
    assert caido.id not in [a.id for a in correo.pendientes(db)]
    # Y con el proveedor de vuelta, sale.
    monkeypatch.setattr(correo, "entregar", lambda *a: None)
    caido.reintentar_en = datetime.now() - timedelta(minutes=1)
    db.commit()
    r = correo.despachar(db, solo=[caido.id])
    db.expire_all()
    assert caido.estado == "enviada" and caido.reintentar_en is None


def test_lo_fallido_se_regresa_a_la_cola_desde_la_pantalla(db, cliente, sesion):
    from app import correo
    fallido = _aviso(db, estado="fallida", hace_horas=2)
    viejo = _aviso(db, estado="fallida", hace_horas=50)
    e = correo.estado(db)
    assert e["fallidas_recientes"] == 1 and e["avisos"]["fallida"] == 2
    r = cliente.post("/manual/correo/reintentar", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["reintentados"] == 1
    db.expire_all()
    assert fallido.estado == "pendiente" and fallido.intentos == 0
    assert viejo.estado == "vencida"
    # El estado del sistema trae el boton solo cuando hay fallidas.
    from app import manual
    tarjetas = {t["clave"]: t for t in manual.estado(db, "es")}
    assert "accion" not in tarjetas["correo"]


def test_el_correo_sale_con_el_certificado_comprobado(monkeypatch):
    import smtplib
    import ssl
    from app import correo
    from app.config import settings
    visto = {}

    class SMTPFalso:
        def __init__(self, host, puerto, timeout=None):
            visto["host"] = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            visto["context"] = context

        def login(self, u, c):
            visto["login"] = u

        def send_message(self, mensaje):
            visto["enviado"] = mensaje["To"]

    monkeypatch.setattr(smtplib, "SMTP", SMTPFalso)
    monkeypatch.setattr(correo, "por_microsoft", lambda: False)
    monkeypatch.setattr(settings, "correo_host", "smtp.prueba.lat")
    monkeypatch.setattr(settings, "correo_puerto", 587)
    monkeypatch.setattr(settings, "correo_usuario", "u")
    monkeypatch.setattr(settings, "correo_clave", "c")
    monkeypatch.setattr(settings, "correo_de", "Centauro <connect@prueba.lat>")
    correo.entregar("alguien@prueba.lat", "Asunto", "texto", None)
    assert isinstance(visto["context"], ssl.SSLContext)
    assert visto["context"].verify_mode == ssl.CERT_REQUIRED
    assert visto["enviado"] == "alguien@prueba.lat"


def test_el_aviso_al_telefono_no_espera_para_siempre(db, monkeypatch):
    import pywebpush
    from app import push
    visto = {}

    def falso(**kwargs):
        visto.update(kwargs)
        return True
    monkeypatch.setattr(pywebpush, "webpush", falso)
    monkeypatch.setattr(push.settings, "vapid_private", "llave")
    monkeypatch.setattr(push.settings, "vapid_public", "publica")
    db.add(m.SuscripcionPush(persona_id=1, endpoint="https://push.example/100",
                             p256dh="k", auth="a"))
    db.commit()
    push.avisar(db, 1, "Prueba", "Cuerpo", url="/app/", etiqueta="prueba")
    assert visto.get("timeout") == push.SEGUNDOS_DE_ESPERA == 10


# ================================================================ el reloj

def test_el_certificado_avisa_aunque_el_reloj_no_corra_el_dia_exacto(
        cliente, sesion, datos, db):
    from app import capacitaciones
    hoy = date.today()
    persona = datos["personal"]["Juan Ramirez"]["id"]
    curso = m.Capacitacion(persona_id=persona, nombre="Manejo evasivo",
                           vigencia_hasta=hoy + timedelta(days=27), activo=True)
    db.add(curso)
    db.commit()
    # El reloj no corrio a los 30 ni a los 29: a los 27 avisa igual.
    assert capacitaciones.revisar_vencimientos(db, hoy)["avisados"] == 1
    # Y no repite mientras dure la ventana.
    assert capacitaciones.revisar_vencimientos(db, hoy + timedelta(days=1))["avisados"] == 0
    assert capacitaciones.revisar_vencimientos(db, hoy + timedelta(days=20))["avisados"] == 0
    # Vencio y el reloj tampoco corrio ese dia: avisa al dia siguiente, una vez.
    assert capacitaciones.revisar_vencimientos(db, hoy + timedelta(days=28))["avisados"] == 1
    assert capacitaciones.revisar_vencimientos(db, hoy + timedelta(days=29))["avisados"] == 0


def test_la_diaria_que_no_corrio_se_repone(db):
    from app import celery_app
    zona = celery_app.ZONA_DEL_RELOJ
    # Un lunes a las 9:00 de Mexico: ya debieron correr la 1:30, la 6:30,
    # la 7:30 y la 8:00; la del dia 3 no toca hoy (a menos que sea 3).
    ahora = datetime(2026, 10, 5, 9, 0, tzinfo=zona).astimezone(timezone.utc)
    faltan = celery_app.diarias_que_faltan(db, ahora)
    assert "capacitaciones.revisar_vencimientos" in faltan
    assert "bonos.calcular_el_mes" not in faltan
    # La que si termino hoy, ya no falta; la que termino ayer, si.
    db.merge(m.VueltaDelReloj(
        tarea="capacitaciones.revisar_vencimientos",
        empezo_en=ahora - timedelta(minutes=80), termino_en=ahora - timedelta(minutes=79)))
    db.merge(m.VueltaDelReloj(
        tarea="encuestas.pasar_lista",
        empezo_en=ahora - timedelta(days=1), termino_en=ahora - timedelta(days=1)))
    # Y la que esta corriendo ahora mismo se deja en paz.
    db.merge(m.VueltaDelReloj(tarea="implantados.abrir_mes_siguiente",
                              empezo_en=ahora - timedelta(minutes=3)))
    db.commit()
    faltan = celery_app.diarias_que_faltan(db, ahora)
    assert "capacitaciones.revisar_vencimientos" not in faltan
    assert "encuestas.pasar_lista" in faltan
    assert "implantados.abrir_mes_siguiente" not in faltan
    # A las 7:40 todavia no se repone la de las 7:30: tiene su margen.
    temprano = datetime(2026, 10, 5, 7, 40, tzinfo=zona).astimezone(timezone.utc)
    assert "capacitaciones.revisar_vencimientos" not in celery_app.diarias_que_faltan(db, temprano)


def test_un_pais_que_revienta_no_deja_al_otro_sin_corte(db, datos, monkeypatch):
    from app import nomina
    lunes = datetime(2026, 10, 5, 11, 30)   # en hora de Mexico
    monkeypatch.setattr(nomina, "_hay_que_pagar", lambda db_, pais_id: True)

    def hecho(db_, pais_id, fecha):
        if pais_id == datos["mx"]["id"]:
            raise ValueError("una jornada sin modalidad")
        from fastapi import HTTPException
        raise HTTPException(409, {"sin_tarifa": [1]})
    monkeypatch.setattr(nomina, "calcular", hecho)
    from zoneinfo import ZoneInfo
    ahora = lunes.replace(tzinfo=ZoneInfo("America/Mexico_City")).astimezone(timezone.utc)
    hechos = nomina.reloj_del_lunes(db, ahora)
    por_pais = {h["pais"]: h["resultado"] for h in hechos}
    assert por_pais.get("MX") == "error"
    assert por_pais.get("BR") == "no_salio"


def test_un_implantado_que_revienta_no_frena_a_los_demas(monkeypatch, db):
    from app import implantado

    class S:
        def __init__(self, i):
            self.id, self.folio = i, f"IM-{i}"
            # El proceso pregunta que dia es en el pais de cada servicio
            # (seccion 101); sin pais, el reloj de la casa.
            self.pais_id = None
    monkeypatch.setattr(implantado, "por_abrir", lambda db_, hoy: [S(1), S(2)])

    def abrir(db_, servicio, hoy):
        if servicio.id == 1:
            raise ValueError("hora mal guardada")
        return {"periodo": "2026-11"}
    monkeypatch.setattr(implantado, "abrir_siguiente", abrir)
    r = implantado.abrir_los_que_toquen(db)
    assert [x["folio"] for x in r["abiertos"]] == ["IM-2"]
    assert r["fallados"][0]["folio"] == "IM-1"


# ================================================================ el GPS

def test_si_falla_el_testigo_la_posicion_y_el_panico_se_quedan(cliente, sesion, datos):
    """Pegasus contesta bien las unidades y los panicos, y truena en la
    consulta del testigo de una marca. Antes se deshacia la vuelta entera;
    ahora lo leido se queda y el error se anota en su fase."""
    from app import gps, pegasus as conexion
    from app.db import SessionLocal
    from test_gps import (GRUPO_MX, PegasusFalso, _en_curso, _panico,
                          _placa_suburban, unidad)

    db = SessionLocal()
    try:
        _en_curso(cliente, sesion, datos)
        ahora = datetime.now(timezone.utc)

        class PegasusConTestigoRoto(PegasusFalso):
            def eventos(self, vehiculos, duracion, etiquetas=None, campos=None,
                        tope=None):
                if etiquetas is None:
                    raise conexion.NoResponde("Pegasus contesto 500 en /rawdata.")
                return super().eventos(vehiculos, duracion, etiquetas, campos, tope)

        pegasus = PegasusConTestigoRoto()
        pegasus.unidades_[GRUPO_MX] = [
            unidad(101, _placa_suburban(datos), ahora, lat=19.43, lon=-99.16)]
        _panico(pegasus, 101, ahora - timedelta(minutes=1))

        r = gps.leer(db, pegasus, ahora)
        assert r["panicos"] == 1
        assert "testigos" in r["error"]
        db.expire_all()
        assert db.query(m.AlertaIncidencia).count() == 1
        u = db.query(m.UnidadGps).filter_by(pegasus_id=101).first()
        assert u is not None and u.reporte_en is not None
    finally:
        db.close()


def test_una_vuelta_del_gps_no_se_encima_con_otra(monkeypatch):
    from app import gps
    from app.db import SessionLocal
    monkeypatch.setattr(gps, "_tomar_vuelta", lambda: False)
    llamadas = []
    monkeypatch.setattr(gps, "_leer", lambda *a: llamadas.append(a) or {})
    with SessionLocal() as db:
        r = gps.leer(db, cliente=object(), ahora=datetime.now(timezone.utc))
    assert r.get("omitido") and not llamadas


def test_el_aviso_de_pegasus_en_el_silencio_pide_el_barrido(datos, monkeypatch):
    """El disparador que cae en los veinte segundos deja bandera, y la
    siguiente vuelta de dos minutos hace barrido completo: el panico de
    una unidad sin servicio ya no espera quince minutos."""
    from app import gps
    from app.db import SessionLocal
    from test_gps import GRUPO_MX, PegasusFalso, _panico, unidad

    pedido = {"barrido": False}
    monkeypatch.setattr(gps, "_pedir_barrido", lambda: pedido.update(barrido=True))
    monkeypatch.setattr(gps, "_barrido_pedido", lambda: pedido.pop("barrido", False))
    monkeypatch.setattr(gps, "_tomar_vuelta", lambda: True)
    monkeypatch.setattr(gps, "_soltar_vuelta", lambda: None)

    db = SessionLocal()
    try:
        pegasus = PegasusFalso()
        ahora = datetime.now(timezone.utc)
        pegasus.unidades_[GRUPO_MX] = [unidad(101, "ZZZ111", ahora)]
        assert gps.leer(db, pegasus, ahora)["panicos"] == 0        # barrido
        _panico(pegasus, 101, ahora + timedelta(seconds=5))
        r = gps.revisar_panicos(db, pegasus, ahora + timedelta(seconds=10))
        assert r.get("reciente") is True and pedido["barrido"] is True
        # La siguiente vuelta de dos minutos lo encuentra, sin servicio.
        r = gps.leer(db, pegasus, ahora + timedelta(minutes=2))
        assert r["panicos"] == 1
        assert db.query(m.AlertaIncidencia).filter(
            m.AlertaIncidencia.origen.like("pegasus:101:%")).count() == 1
    finally:
        db.close()


def test_deshacer_la_baja_desde_catalogos_reabre_el_acceso(cliente, sesion, db, como_estaba):
    """La baja por error se deshace entera; el acceso que se cerro a
    proposito desde Accesos sigue cerrado."""
    rh = sesion("rrhh")
    pid = _persona_nueva(db, "Baja por error")
    r = cliente.post("/auth/usuarios", json={"persona_id": pid, "rol": "consultor"},
                     headers=rh)
    assert r.status_code == 201, r.text
    uid = r.json()["usuario_id"]
    assert cliente.delete(f"/catalogos/personal/{pid}", headers=sesion("admin")).status_code == 204
    db.expire_all()
    assert db.get(m.Usuario, uid).activo is False
    assert cliente.post(f"/catalogos/personal/{pid}/reactivar",
                        headers=sesion("admin")).status_code == 200
    db.expire_all()
    assert db.get(m.Usuario, uid).activo is True

    # Cerrado a proposito desde Accesos: la baja y su deshecho no lo tocan.
    assert cliente.post(f"/auth/usuarios/{uid}/desactivar", json={"motivo": "se fue"},
                        headers=rh).status_code == 200
    assert cliente.delete(f"/catalogos/personal/{pid}", headers=sesion("admin")).status_code == 204
    assert cliente.post(f"/catalogos/personal/{pid}/reactivar",
                        headers=sesion("admin")).status_code == 200
    db.expire_all()
    assert db.get(m.Usuario, uid).activo is False

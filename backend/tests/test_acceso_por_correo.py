"""La invitacion y la recuperacion, por correo.

Lo que se cuida aqui no es que el correo llegue --eso es del proveedor,
que en las pruebas no existe-- sino lo que si es nuestro:

  - que salga solo a quien trabaja en la consola, y nunca al personal de
    campo, cuyo correo es personal;
  - que salga al guardar y no a la vuelta de cinco minutos;
  - que un enlace muerto no salga por correo;
  - que la pagina del enlace sepa si sirve antes de pedir nada;
  - que copiar el enlace sea solo de administracion.
"""
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app import correo
from app import models as m

BUENA = "jueves de tormenta"


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _encendido(monkeypatch, dominio="https://centauro.lat"):
    """El proveedor y el dominio, y lo que sale queda en una lista."""
    monkeypatch.setattr(correo.settings, "correo_host", "smtp.proveedor.com")
    monkeypatch.setattr(correo.settings, "correo_de",
                        "Centauro <ai@centauro.lat>")
    monkeypatch.setattr(correo.settings, "url_publica", dominio)
    salieron = []
    monkeypatch.setattr(correo, "entregar",
                        lambda destino, asunto, cuerpo, html=None:
                        salieron.append({"a": destino, "asunto": asunto,
                                         "texto": cuerpo, "html": html}))
    return salieron


def _persona(cliente, sesion, datos, plaza_id=None):
    marca = uuid4().hex[:8]
    r = cliente.post("/catalogos/personal", headers=sesion("admin"), json={
        "nombre": f"Prueba {marca}", "correo": f"prueba.{marca}@centauro.lat",
        "plaza_id": plaza_id or datos["cdmx"]["id"]})
    assert r.status_code == 201, r.text
    return r.json()


def _alta(cliente, sesion, datos, rol="consultor", quien="admin",
          plaza_id=None, **extra):
    persona = _persona(cliente, sesion, datos, plaza_id)
    r = cliente.post("/auth/usuarios", headers=sesion(quien),
                     json={"persona_id": persona["id"], "rol": rol, **extra})
    assert r.status_code == 201, r.text
    return {**r.json(), "persona": persona}


def _token(enlace):
    return enlace.rsplit("/", 1)[-1]


def _avisos(db, correo_destino):
    db.expire_all()
    return (db.query(m.Notificacion)
            .filter(m.Notificacion.correo == correo_destino)
            .order_by(m.Notificacion.id).all())


# ============================================================ la invitacion

def test_el_alta_de_consola_deja_su_invitacion_escrita(cliente, sesion,
                                                       datos, db):
    alta = _alta(cliente, sesion, datos)
    assert alta["invitacion"]["por_correo"] is True
    # En las pruebas no hay proveedor: se escribe y se queda esperando.
    assert alta["invitacion"]["correo_encendido"] is False

    avisos = _avisos(db, alta["correo"])
    assert len(avisos) == 1
    aviso = avisos[0]
    assert aviso.plantilla == "acceso_invitacion"
    assert aviso.destinatario == m.Destinatario.COLABORADOR
    assert aviso.servicio_id is None
    assert aviso.estado == "pendiente"
    assert aviso.idioma == "es"
    # El enlace detras del "#": el token no viaja al servidor.
    token = _token(alta["invitacion"]["enlace"])
    assert aviso.enlace_seguimiento == f"/#/crear-contrasena/{token}"
    # El correo vive lo que vive su enlace: tres dias.
    faltan = aviso.expira_en - datetime.now()
    assert timedelta(hours=71) < faltan <= timedelta(hours=72)


def test_al_personal_de_campo_no_le_sale_correo(cliente, sesion, datos, db):
    """Su correo es personal y la empresa no lo controla: lo suyo es el
    codigo de cuatro digitos."""
    alta = _alta(cliente, sesion, datos, rol="personal_seguridad")
    assert alta["invitacion"]["por_correo"] is False
    assert _avisos(db, alta["correo"]) == []


def test_la_invitacion_sale_al_guardar(cliente, sesion, datos, db,
                                       monkeypatch):
    """No espera la vuelta de cinco minutos: quien la dio esta frente a
    la pantalla, y quien la recibe quiza tambien."""
    salieron = _encendido(monkeypatch)
    alta = _alta(cliente, sesion, datos)

    assert len(salieron) == 1, salieron
    enviado = salieron[0]
    assert enviado["a"] == alta["correo"]
    assert enviado["asunto"] == "Tu acceso a Centauro Connect"
    token = _token(alta["invitacion"]["enlace"])
    liga = f"https://centauro.lat/#/crear-contrasena/{token}"
    assert liga in enviado["html"] and liga in enviado["texto"]
    assert "Crear mi contraseña" in enviado["html"]
    assert "Consultor" in enviado["html"]
    assert "vence el" in enviado["texto"]
    assert _avisos(db, alta["correo"])[0].estado == "enviada"


def test_sin_dominio_el_correo_de_acceso_no_sale_sin_boton(cliente, sesion,
                                                           datos, db,
                                                           monkeypatch):
    """Un correo que pide crear la contrasena y no dice donde es peor que
    no mandarlo: se queda pendiente con el motivo escrito."""
    salieron = _encendido(monkeypatch, dominio="")
    alta = _alta(cliente, sesion, datos)
    assert alta["invitacion"]["correo_encendido"] is False
    assert salieron == []

    correo.despachar(db)
    aviso = _avisos(db, alta["correo"])[0]
    assert salieron == []
    assert aviso.estado == "pendiente"
    assert "URL_PUBLICA" in (aviso.ultimo_error or "")


def test_el_correo_dice_la_hora_y_el_idioma_de_su_pais(cliente, sesion,
                                                        datos, db,
                                                        monkeypatch):
    """A quien trabaja en Sao Paulo, "13:10" de Mexico es una hora que no
    es. Y lee en portugues, la misma regla de la app de campo."""
    salieron = _encendido(monkeypatch)
    plazas = {p["nombre"]: p for p in cliente.get(
        "/catalogos/plazas", headers=sesion("admin")).json()}
    alta = _alta(cliente, sesion, datos,
                 plaza_id=plazas["Sao Paulo"]["id"])

    aviso = _avisos(db, alta["correo"])[0]
    assert aviso.idioma == "pt"
    enviado = salieron[0]
    assert enviado["asunto"] == "Seu acesso ao Centauro Connect"
    assert "Criar minha senha" in enviado["html"]
    alla = aviso.expira_en.astimezone(ZoneInfo("America/Sao_Paulo"))
    assert f"às {alla:%H:%M}" in enviado["texto"], enviado["texto"]


def test_dar_acceso_con_su_puesto_de_una_vez(cliente, sesion, datos, db):
    h = sesion("admin")
    actividad = cliente.get("/auth/actividades", headers=h).json()[0]
    puesto = cliente.post("/auth/categorias", headers=h, json={
        "nombre": f"Puesto {uuid4().hex[:6]}",
        "actividades": [actividad["actividad"]]})
    assert puesto.status_code == 201, puesto.text

    alta = _alta(cliente, sesion, datos,
                 categoria_id=puesto.json()["categoria_id"])
    db.expire_all()
    usuario = db.get(m.Usuario, alta["usuario_id"])
    assert usuario.categoria_id == puesto.json()["categoria_id"]


def test_la_lista_de_dar_acceso(cliente, sesion, datos):
    """Las personas vivas del padron que todavia no tienen acceso."""
    persona = _persona(cliente, sesion, datos)

    def ids(quien="admin"):
        r = cliente.get("/auth/personas-sin-acceso", headers=sesion(quien))
        assert r.status_code == 200, r.text
        return {p["persona_id"] for p in r.json()["personas"]}

    assert persona["id"] in ids()
    # RRHH da los accesos: tambien la ve.
    assert persona["id"] in ids("rrhh")
    assert cliente.get("/auth/personas-sin-acceso",
                       headers=sesion("consultor")).status_code == 403

    cliente.post("/auth/usuarios", headers=sesion("admin"),
                 json={"persona_id": persona["id"], "rol": "central"})
    assert persona["id"] not in ids()


def test_no_se_da_acceso_a_una_baja(cliente, sesion, datos):
    persona = _persona(cliente, sesion, datos)
    h = sesion("admin")
    assert cliente.delete(f"/catalogos/personal/{persona['id']}",
                          headers=h).status_code == 204
    r = cliente.post("/auth/usuarios", headers=h,
                     json={"persona_id": persona["id"], "rol": "consultor"})
    assert r.status_code == 409, r.text


def test_un_correo_no_abre_dos_accesos(cliente, sesion, datos):
    """El correo es la llave del acceso. Escrito con otras mayusculas
    sigue siendo el mismo buzon, y antes reventaba contra la base."""
    h = sesion("admin")
    primera = _alta(cliente, sesion, datos)
    otra = cliente.post("/catalogos/personal", headers=h, json={
        "nombre": f"Otra {uuid4().hex[:6]}",
        "correo": primera["correo"].upper(),
        "plaza_id": datos["cdmx"]["id"]})
    assert otra.status_code == 201, otra.text
    r = cliente.post("/auth/usuarios", headers=h,
                     json={"persona_id": otra.json()["id"], "rol": "consultor"})
    assert r.status_code == 409, r.text
    # Y tampoco se ofrece en la lista de dar acceso.
    lista = cliente.get("/auth/personas-sin-acceso", headers=h).json()
    assert otra.json()["id"] not in {p["persona_id"] for p in lista["personas"]}


# ========================================================== la recuperacion

def test_la_recuperacion_sale_por_correo_y_no_delata_a_nadie(cliente, sesion,
                                                            datos, db,
                                                            monkeypatch):
    alta = _alta(cliente, sesion, datos, rol="central")
    token = _token(alta["invitacion"]["enlace"])
    assert cliente.post("/auth/establecer-contrasena", json={
        "token": token, "contrasena": BUENA}).status_code == 200

    salieron = _encendido(monkeypatch)
    real = cliente.post("/auth/recuperar", json={"correo": alta["correo"]})
    falso = cliente.post("/auth/recuperar",
                         json={"correo": f"{uuid4().hex}@centauro.lat"})
    assert real.status_code == falso.status_code == 200
    assert real.json() == falso.json()
    assert real.json()["por_correo"] is True
    assert real.json()["de"] == "ai@centauro.lat"
    assert "crear-contrasena" not in real.text

    # Salio uno, a la cuenta que existe, al momento.
    assert [s["a"] for s in salieron] == [alta["correo"]]
    assert salieron[0]["asunto"] == "Para poner una nueva contraseña"
    assert "Poner mi nueva contraseña" in salieron[0]["html"]
    assert "vence a las" in salieron[0]["texto"]


def test_sin_correo_encendido_la_respuesta_lo_dice(cliente):
    """Mientras el correo no este encendido el enlace lo entrega
    administracion; la pantalla no manda a nadie a esperar un correo que
    no va a salir."""
    r = cliente.post("/auth/recuperar",
                     json={"correo": f"{uuid4().hex}@centauro.lat"})
    assert r.status_code == 200
    assert r.json()["por_correo"] is False
    assert r.json()["de"] is None


# ================================================== el enlace que ya no sirve

def test_reenviar_mata_el_enlace_y_el_correo_que_no_salio(cliente, sesion,
                                                          datos, db):
    alta = _alta(cliente, sesion, datos)
    viejo = _token(alta["invitacion"]["enlace"])
    h = sesion("admin")

    r = cliente.post(f"/auth/usuarios/{alta['usuario_id']}/invitacion",
                     headers=h)
    assert r.status_code == 200, r.text
    nuevo = _token(r.json()["enlace"])
    assert nuevo != viejo

    # El correo viejo no habia salido: ya no sale, llevaria un enlace
    # muerto. El nuevo espera su turno.
    estados = [a.estado for a in _avisos(db, alta["correo"])]
    assert estados == ["vencida", "pendiente"]

    assert cliente.post("/auth/establecer-contrasena", json={
        "token": viejo, "contrasena": BUENA}).status_code == 409
    assert cliente.post("/auth/establecer-contrasena", json={
        "token": nuevo, "contrasena": BUENA}).status_code == 200

    acciones = [f["accion"] for f in cliente.get(
        f"/auth/usuarios/{alta['usuario_id']}/historial", headers=h).json()]
    assert "invitacion reenviada" in acciones


def test_usar_el_enlace_retira_su_correo_pendiente(cliente, sesion, datos, db):
    """Si lo uso con el enlace copiado antes de que saliera el correo, el
    correo ya no tiene nada que ofrecer."""
    alta = _alta(cliente, sesion, datos)
    assert cliente.post("/auth/establecer-contrasena", json={
        "token": _token(alta["invitacion"]["enlace"]),
        "contrasena": BUENA}).status_code == 200
    assert [a.estado for a in _avisos(db, alta["correo"])] == ["vencida"]


def test_reenviar_solo_a_quien_todavia_no_estrena(cliente, sesion, datos):
    h = sesion("admin")
    ruta = "/auth/usuarios/{}/invitacion"

    ya = _alta(cliente, sesion, datos)
    cliente.post("/auth/establecer-contrasena", json={
        "token": _token(ya["invitacion"]["enlace"]), "contrasena": BUENA})
    assert cliente.post(ruta.format(ya["usuario_id"]),
                        headers=h).status_code == 409

    campo = _alta(cliente, sesion, datos, rol="personal_seguridad")
    assert cliente.post(ruta.format(campo["usuario_id"]),
                        headers=h).status_code == 409

    cerrado = _alta(cliente, sesion, datos)
    cliente.post(f"/auth/usuarios/{cerrado['usuario_id']}/desactivar",
                 json={}, headers=h)
    assert cliente.post(ruta.format(cerrado["usuario_id"]),
                        headers=h).status_code == 409

    # Y no lo hace cualquiera.
    otro = _alta(cliente, sesion, datos)
    assert cliente.post(ruta.format(otro["usuario_id"]),
                        headers=sesion("consultor")).status_code == 403
    assert cliente.post(ruta.format(otro["usuario_id"]),
                        headers=sesion("rrhh")).status_code == 200


# ==================================================== la pagina del enlace

def test_la_pagina_sabe_si_el_enlace_sirve(cliente, sesion, datos, db):
    alta = _alta(cliente, sesion, datos)
    token = _token(alta["invitacion"]["enlace"])

    def como(t):
        r = cliente.post("/auth/enlace", json={"token": t})
        assert r.status_code == 200, r.text
        return r.json()

    vivo = como(token)
    assert vivo["estado"] == "vivo"
    assert vivo["tipo"] == "invitacion"
    assert vivo["correo"] == alta["correo"]
    assert vivo["rol"] == "consultor"
    assert vivo["idioma"] == "es"

    assert como("no-es-un-token") == {"estado": "invalido"}

    # Reenviado: el anterior se anula, y no dice de quien era.
    cliente.post(f"/auth/usuarios/{alta['usuario_id']}/invitacion",
                 headers=sesion("admin"))
    assert como(token) == {"estado": "anulado"}

    nuevo = db.query(m.Invitacion).filter_by(
        usuario_id=alta["usuario_id"], anulado_en=None).one()
    nuevo.expira_en = datetime.now() - timedelta(minutes=1)
    db.commit()
    assert como(nuevo.token) == {"estado": "vencido"}

    nuevo.expira_en = datetime.now() + timedelta(hours=1)
    db.commit()
    cliente.post("/auth/establecer-contrasena", json={
        "token": nuevo.token, "contrasena": BUENA})
    assert como(nuevo.token) == {"estado": "usado"}


def test_la_pagina_de_un_acceso_cerrado(cliente, sesion, datos):
    alta = _alta(cliente, sesion, datos)
    cliente.post(f"/auth/usuarios/{alta['usuario_id']}/desactivar",
                 json={}, headers=sesion("admin"))
    r = cliente.post("/auth/enlace",
                     json={"token": _token(alta["invitacion"]["enlace"])})
    assert r.json() == {"estado": "cerrado"}


def test_el_codigo_de_campo_no_sirve_como_enlace(db):
    """El codigo de cuatro digitos vive en la misma tabla, cifrado. Aunque
    alguien consiguiera el renglon, no abre la pagina del enlace."""
    from app import contrasenas
    usuario = db.query(m.Usuario).filter_by(
        rol=m.Rol.PERSONAL_SEGURIDAD).first()
    fila = m.Invitacion(usuario_id=usuario.id, token=f"cifrado-{uuid4().hex}",
                        tipo=m.TipoInvitacion.CODIGO_CAMPO, fallos=0,
                        expira_en=datetime.now() + timedelta(minutes=10))
    db.add(fila)
    db.flush()
    assert contrasenas.revisar_enlace(db, fila.token) == {"estado": "invalido"}


# ================================================== copiar el enlace

def test_copiar_el_enlace_es_solo_de_administracion(cliente, sesion, datos):
    """Decision de Salvador (23 sep): con el enlace en la mano se le pone
    la contrasena a otra persona. Administracion si --y direccion
    general, que hereda lo de administracion--; RRHH da el acceso, pero
    el enlace le llega a la persona por su correo."""
    alta = _alta(cliente, sesion, datos)
    ruta = f"/auth/usuarios/{alta['usuario_id']}/enlace-pendiente"
    assert cliente.get(ruta, headers=sesion("admin")).status_code == 200
    assert cliente.get(ruta, headers=sesion("dirgeneral")).status_code == 200
    assert cliente.get(ruta, headers=sesion("rrhh")).status_code == 403

    # Tampoco se le cuela en las respuestas del alta o del reenvio.
    de_rrhh = _alta(cliente, sesion, datos, quien="rrhh")
    assert de_rrhh["invitacion"]["enlace"] is None
    r = cliente.post(f"/auth/usuarios/{de_rrhh['usuario_id']}/invitacion",
                     headers=sesion("rrhh"))
    assert r.json()["enlace"] is None
    estado = cliente.get(f"/auth/usuarios/{de_rrhh['usuario_id']}/invitacion",
                         headers=sesion("rrhh")).json()
    assert estado["puede_copiar"] is False


def test_el_panel_dice_como_va_la_invitacion(cliente, sesion, datos, db):
    alta = _alta(cliente, sesion, datos)
    ruta = f"/auth/usuarios/{alta['usuario_id']}/invitacion"
    r = cliente.get(ruta, headers=sesion("admin"))
    assert r.status_code == 200, r.text
    estado = r.json()
    assert estado["estado"] == "vigente"
    assert estado["estrenado"] is False
    assert estado["correo"]["estado"] == "pendiente"
    assert estado["correo_encendido"] is False
    assert estado["puede_copiar"] is True

    cliente.post("/auth/establecer-contrasena", json={
        "token": _token(alta["invitacion"]["enlace"]), "contrasena": BUENA})
    estado = cliente.get(ruta, headers=sesion("admin")).json()
    assert estado["estado"] == "usada"
    assert estado["estrenado"] is True


# ================================================== dos despachadores

def test_dos_despachadores_no_mandan_el_mismo_correo(cliente, sesion, datos,
                                                     db, monkeypatch):
    """El de la vuelta de cinco minutos y el que sale al guardar pueden
    coincidir. Lo que uno tiene tomado, el otro lo salta."""
    from app.db import SessionLocal

    alta = _alta(cliente, sesion, datos)
    salieron = _encendido(monkeypatch)
    aviso_id = _avisos(db, alta["correo"])[0].id
    db.rollback()

    otro = SessionLocal()
    try:
        tomados = correo.pendientes(otro, solo=[aviso_id], bloquear=True)
        assert [a.id for a in tomados] == [aviso_id]
        r = correo.despachar(db, solo=[aviso_id])
        assert r["enviados"] == 0
        assert salieron == []
    finally:
        otro.rollback()
        otro.close()

    r = correo.despachar(db, solo=[aviso_id])
    assert r["enviados"] == 1
    assert len(salieron) == 1


def test_los_textos_del_correo_de_acceso_estan_en_los_tres_idiomas():
    from app import textos_aviso as ta
    claves = [k for k in ta.TEXTOS["es"]
              if k.startswith("acc_") or k.startswith("rol_")]
    assert len(claves) >= 18
    for idioma in ("en", "pt"):
        faltan = [k for k in claves if k not in ta.TEXTOS[idioma]]
        assert not faltan, (idioma, faltan)
    for rol in m.Rol:
        assert f"rol_{rol.value}" in ta.TEXTOS["es"], rol


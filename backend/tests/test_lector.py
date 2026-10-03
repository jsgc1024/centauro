"""El lector de noticias y redes (seccion 140).

Lo que se cuida: cada nota se guarda una vez; solo lo que parece de
seguridad va a Claude; lo que Claude dice que es el mismo hecho se junta;
sin llave de Claude el lector sigue por palabras; X tiene tope; el
analista crea el evento (propuesto, con las notas como fuentes), lo suma
o lo descarta con motivo; nada se publica solo.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from app import lector
from app import models as m
from app.config import settings
from app.db import SessionLocal
from tests.test_riesgo_clientes import cat, publicar  # noqa: F401

AHORA = datetime.now(timezone.utc)


def _rss(*items) -> bytes:
    cuerpo = "".join(
        f"<item><title>{t} - {medio}</title><link>{url}</link>"
        f"<guid>{url}</guid><pubDate>{fecha}</pubDate>"
        f"<source url='https://x'>{medio}</source>"
        f"<description>&lt;a href='{url}'&gt;{t}&lt;/a&gt;</description></item>"
        for t, medio, url, fecha in items)
    return f"<?xml version='1.0'?><rss><channel>{cuerpo}</channel></rss>".encode()


def _fecha(horas=0):
    return (AHORA - timedelta(hours=horas)).strftime("%a, %d %b %Y %H:%M:%S GMT")


class _Respuesta:
    def __init__(self, contenido=b"", codigo=200, datos=None):
        self.content, self.status_code, self._datos = contenido, codigo, datos

    def json(self):
        return self._datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Cliente:
    def __init__(self, respuesta):
        self.respuesta, self.pedidos = respuesta, []

    def get(self, url, **k):
        self.pedidos.append((url, k))
        return self.respuesta


def _fuente(tipo="busqueda", direccion="bloqueo", oficial=False):
    db = SessionLocal()
    try:
        f = m.FuenteLector(tipo=tipo, nombre=f"Fuente {tipo}",
                           direccion=direccion, oficial=oficial)
        db.add(f)
        db.commit()
        return f.id
    finally:
        db.close()


NOTAS = (
    ("Bloquean con tráileres la carretera Reynosa-Monterrey", "El Mañana",
     "https://elmanana.com/a", _fecha(1)),
    ("El América gana el clásico", "Récord", "https://record.com/b", _fecha(1)),
    ("Balacera en Culiacán deja dos heridos", "Noroeste",
     "https://noroeste.com/c", _fecha(2)),
    ("Narcobloqueo de hace una semana", "Viejo", "https://viejo.com/d",
     _fecha(80)),
)


def test_leer_el_rss_de_google_noticias():
    notas = lector.leer_rss(_rss(*NOTAS[:1]))
    assert notas[0]["titulo"] == ("Bloquean con tráileres la carretera "
                                  "Reynosa-Monterrey")
    assert notas[0]["medio"] == "El Mañana"
    assert notas[0]["url"] == "https://elmanana.com/a"
    assert notas[0]["publicada_en"] is not None
    atom = (b"<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Asalto "
            b"en la autopista</title><link href='https://y/1'/>"
            b"<updated>2026-10-03T10:00:00Z</updated></entry></feed>")
    assert lector.leer_rss(atom)[0]["url"] == "https://y/1"
    with pytest.raises(Exception):
        lector.leer_rss(b"<html>no")


def test_cada_nota_una_vez_y_solo_lo_de_seguridad_pasa():
    fid = _fuente()
    db = SessionLocal()
    try:
        f = db.get(m.FuenteLector, fid)
        cliente = _Cliente(_Respuesta(_rss(*NOTAS)))
        assert lector.leer_fuente(db, f, cliente, AHORA) == 3   # la vieja no
        assert "news.google.com" in cliente.pedidos[0][0]
        assert lector.leer_fuente(db, f, cliente, AHORA) == 0   # ya estaban
        db.commit()
        estados = {n.titulo: n.estado for n in db.query(m.NotaLector)}
        assert estados["El América gana el clásico"] == "sin_filtro"
        assert estados["Balacera en Culiacán deja dos heridos"] == "nueva"
        # Una pagina caida queda dicha en la fuente, sin reventar.
        assert lector.leer_fuente(db, f, _Cliente(_Respuesta(codigo=503)),
                                  AHORA) == 0
        assert "503" in f.error
    finally:
        db.close()


def test_sin_llave_de_claude_sigue_por_palabras():
    fid = _fuente()
    db = SessionLocal()
    try:
        lector.leer_fuente(db, db.get(m.FuenteLector, fid),
                           _Cliente(_Respuesta(_rss(*NOTAS))), AHORA)
        with mock.patch.object(settings, "anthropic_api_key", ""):
            salida = lector.entender(db, AHORA)
        db.commit()
        assert salida == {"notas": 2, "hallazgos": 2, "con_ia": False}
        h = db.query(m.HallazgoLector).first()
        assert h.con_ia is False and h.estado == "por_revisar"
    finally:
        db.close()


def _con_claude(respuestas):
    """Claude de mentiras: contesta lo que se le diga, lote por lote."""
    def consulta(db, pais, notas, abiertos, eventos, descartes):
        return respuestas.pop(0)
    return mock.patch.multiple(lector, _consulta=consulta), \
        mock.patch.object(settings, "anthropic_api_key", "sk-prueba")


def test_claude_entiende_y_junta_el_mismo_hecho():
    fid = _fuente()
    oficial = _fuente(tipo="medio", direccion="https://gn/rss", oficial=True)
    db = SessionLocal()
    try:
        lector.leer_fuente(db, db.get(m.FuenteLector, fid), _Cliente(
            _Respuesta(_rss(NOTAS[0], NOTAS[2], (
                "Bloqueo en la Reynosa-Monterrey: lo que sabemos", "Milenio",
                "https://milenio.com/e", _fecha(0))))), AHORA)
        dijo = [[
            {"n": 1, "es_hecho": True, "tipo": "Bloqueo carretero",
             "estado": "Nuevo León", "municipio": "Cadereyta Jiménez",
             "lugar": "km 40", "nivel": 3, "razon": "vía principal",
             "titulo": "Bloqueo con tráileres en la Reynosa-Monterrey"},
            {"n": 2, "es_hecho": False},
            {"n": 3, "es_hecho": True, "tipo": "Bloqueo carretero",
             "estado": "Nuevo León", "mismo_que": "N1"},
        ]]
        a, b = _con_claude(dijo)
        with a, b:
            salida = lector.entender(db, AHORA)
        db.commit()
        assert salida["hallazgos"] == 1
        h = db.query(m.HallazgoLector).one()
        assert h.titulo == "Bloqueo con tráileres en la Reynosa-Monterrey"
        assert h.tipo.nombre == "Bloqueo carretero" and h.nivel == 3
        assert h.region.nombre == "Nuevo León"
        assert h.municipio.nombre.startswith("Cadereyta")
        # El punto es el centro del municipio, de los contornos del mapa.
        assert 25.3 < float(h.lat) < 25.8 and -100.2 < float(h.lon) < -99.7
        assert len(h.notas) == 2
        assert (db.query(m.NotaLector).filter_by(estado="no_es").count()
                == 1)

        # Una nota oficial despues, del mismo hecho: se suma al hallazgo.
        lector.leer_fuente(db, db.get(m.FuenteLector, oficial), _Cliente(
            _Respuesta(_rss(("Guardia Nacional atiende bloqueo en el km 40",
                             "Guardia Nacional", "https://gn/1",
                             _fecha(0))))), AHORA)
        a, b = _con_claude([[{"n": 1, "es_hecho": True,
                              "tipo": "Bloqueo carretero",
                              "estado": "Nuevo León",
                              "mismo_que": f"H{h.id}"}]])
        with a, b:
            lector.entender(db, AHORA)
        db.commit()
        db.refresh(h)
        assert len(h.notas) == 3
    finally:
        db.close()


def _hallazgo(con_tipo=True, oficial=False, nota=NOTAS[2]):
    fid = _fuente(oficial=oficial)
    db = SessionLocal()
    try:
        lector.leer_fuente(db, db.get(m.FuenteLector, fid),
                           _Cliente(_Respuesta(_rss(nota))), AHORA)
        dijo = {"n": 1, "es_hecho": True, "estado": "Sinaloa",
                "municipio": "Culiacán", "nivel": 3,
                "titulo": "Balacera en Culiacán deja dos heridos"}
        if con_tipo:
            dijo["tipo"] = "Ataque armado (arma de fuego)"
        a, b = _con_claude([[dijo]])
        with a, b:
            lector.entender(db, AHORA)
        db.commit()
        return db.query(m.HallazgoLector).order_by(
            m.HallazgoLector.id.desc()).first().id
    finally:
        db.close()


def test_crear_el_evento_con_sus_notas(cliente, sesion):
    hid = _hallazgo(oficial=True)
    vista = cliente.get("/riesgo/lector", headers=sesion("central")).json()
    assert [x["id"] for x in vista["hallazgos"]] == [hid]
    ficha = cliente.get(f"/riesgo/lector/hallazgos/{hid}",
                        headers=sesion("central")).json()
    assert ficha["notas"][0]["medio"] == "Noroeste"
    assert ficha["region"] == "Sinaloa" and ficha["lat"] is not None

    # Quien no publica en el mapa no lo convierte.
    assert cliente.post(f"/riesgo/lector/hallazgos/{hid}/evento", json={},
                        headers=sesion("rrhh")).status_code == 403
    r = cliente.post(f"/riesgo/lector/hallazgos/{hid}/evento", json={},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    evento = r.json()
    assert evento["estado"] == "propuesto"          # nada se publica solo
    assert evento["nivel"] == 3
    assert evento["verificacion"] == "oficial"
    assert len(evento["fuentes"]) == 1
    assert "Noroeste" in evento["fuentes"][0]["descripcion"]
    # Ya revisado: no se convierte dos veces ni sigue por revisar.
    assert cliente.post(f"/riesgo/lector/hallazgos/{hid}/evento", json={},
                        headers=sesion("central")).status_code == 409
    vista = cliente.get("/riesgo/lector", headers=sesion("central")).json()
    assert vista["hallazgos"] == [] and vista["hoy"]["eventos"] == 1


def test_sin_tipo_lo_elige_el_analista(cliente, sesion, cat):  # noqa: F811
    hid = _hallazgo(con_tipo=False)
    r = cliente.post(f"/riesgo/lector/hallazgos/{hid}/evento", json={},
                     headers=sesion("central"))
    assert r.status_code == 400
    r = cliente.post(f"/riesgo/lector/hallazgos/{hid}/evento",
                     json={"tipo_id": cat["tipos"]["Enfrentamiento armado"]},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert r.json()["tipo"] == "Enfrentamiento armado"


def test_sumar_y_descartar(cliente, sesion, cat):  # noqa: F811
    hid = _hallazgo()
    base = {"pais_id": cat["pais_id"], "region_id": cat["regiones"]["Sinaloa"],
            "tipo_id": cat["tipos"]["Enfrentamiento armado"], "nivel": 2,
            "titulo": "Enfrentamiento en Culiacán",
            "ocurrio_en": AHORA.isoformat(),
            "vigente_hasta": (AHORA + timedelta(hours=6)).isoformat()}
    evento = cliente.post("/riesgo/eventos", json=base,
                          headers=sesion("central")).json()
    r = cliente.post(f"/riesgo/lector/hallazgos/{hid}/sumar",
                     json={"evento_id": evento["id"]},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert len(r.json()["fuentes"]) == 1

    hid = _hallazgo(nota=("Otra balacera en Culiacán", "Ríodoce",
                          "https://riodoce.mx/f", _fecha(0)))
    assert cliente.post(f"/riesgo/lector/hallazgos/{hid}/descartar",
                        json={"motivo": "porque si"},
                        headers=sesion("central")).status_code == 400
    assert cliente.post(f"/riesgo/lector/hallazgos/{hid}/descartar",
                        json={"motivo": "ya_paso"},
                        headers=sesion("central")).status_code == 200
    db = SessionLocal()
    try:
        assert lector._descartes(db)[0][1] == "ya_paso"
    finally:
        db.close()


def test_las_fuentes_y_el_tope_de_x(cliente, sesion):
    h = sesion("diroperaciones")
    r = cliente.post("/riesgo/lector/fuentes", headers=h, json={
        "tipo": "lista_x", "direccion": "https://x.com/centauro"})
    assert r.status_code == 400
    r = cliente.post("/riesgo/lector/fuentes", headers=h, json={
        "tipo": "lista_x", "nombre": "Lista de la Central",
        "direccion": "https://x.com/i/lists/1234567890"})
    assert r.status_code == 200, r.text
    with mock.patch.object(lector, "_direccion_publica", lambda url: None):
        r = cliente.post("/riesgo/lector/fuentes", headers=h, json={
            "tipo": "medio", "direccion": "https://riodoce.mx/feed/",
            "regiones": ["Sinaloa"]})
    assert r.status_code == 200, r.text
    fuentes = {f["nombre"]: f for f in r.json()["fuentes"]}
    assert fuentes["https://riodoce.mx/feed/"]["regiones"] == ["Sinaloa"]
    # Quien no lleva el catalogo no agrega fuentes.
    assert cliente.post("/riesgo/lector/fuentes", headers=sesion("rrhh"),
                        json={"tipo": "busqueda",
                              "direccion": "robo"}).status_code == 403

    lista = fuentes["Lista de la Central"]["id"]
    from app import intentos
    if intentos._redis():
        intentos._redis().delete(f"lector:x:{AHORA.date().isoformat()}")
    tuits = {"data": [{"id": str(100 + i), "text": f"Bloqueo en el km {i}",
                       "author_id": "9", "created_at": AHORA.isoformat()}
                      for i in range(3)],
             "includes": {"users": [{"id": "9", "username": "monitorNL"}]}}
    db = SessionLocal()
    try:
        f = db.get(m.FuenteLector, lista)
        with mock.patch.object(settings, "x_bearer_token", ""):
            lector.leer_fuente(db, f, _Cliente(_Respuesta()), AHORA)
        assert f.error == "Falta la llave de X"
        with mock.patch.object(settings, "x_bearer_token", "token"):
            cliente_x = _Cliente(_Respuesta(datos=tuits))
            assert lector.leer_fuente(db, f, cliente_x, AHORA) == 3
            assert "lists/1234567890/tweets" in cliente_x.pedidos[0][0]
            nota = db.query(m.NotaLector).filter_by(fuente_id=lista).first()
            assert nota.url.startswith("https://x.com/monitorNL/status/")
            assert lector.x_leidas_hoy(db, AHORA) == 3
            # X no cobra dos veces la misma en su dia: la vuelta que trae
            # las mismas tres no suma; la de manana si.
            assert lector.leer_fuente(db, f, cliente_x, AHORA) == 0
            assert lector.x_leidas_hoy(db, AHORA) == 3
            manana = AHORA + timedelta(days=1)
            if intentos._redis():
                intentos._redis().delete(
                    f"lector:x:{manana.date().isoformat()}")
                lector.leer_fuente(db, f, cliente_x, manana)
                assert lector.x_leidas_hoy(db, manana) == 3
                lector.parametros(db).x_dia = AHORA.date()
                lector.parametros(db).x_leidas = 3
            lector.parametros(db).tope_x_dia = 3
            assert lector.leer_fuente(db, f, cliente_x, AHORA) == 0
            assert f.error == "Llegó al tope de X de hoy"
        db.commit()
    finally:
        db.close()
    r = cliente.put("/riesgo/lector/parametros", headers=h,
                    json={"tope_x_dia": 800, "pausado": True})
    assert r.json()["tope_x_dia"] == 800 and r.json()["pausado"] is True
    db = SessionLocal()
    try:
        assert lector.vuelta(db, _Cliente(_Respuesta()), AHORA) == {
            "pausado": True}
    finally:
        db.close()


def test_podar_lo_que_no_sirvio():
    fid = _fuente()
    db = SessionLocal()
    try:
        lector.leer_fuente(db, db.get(m.FuenteLector, fid),
                           _Cliente(_Respuesta(_rss(*NOTAS))), AHORA)
        db.commit()
        assert lector.podar(db, AHORA + timedelta(days=15)) == 3
        db.commit()
    finally:
        db.close()


def test_las_fuentes_iniciales():
    from app import lector_catalogo
    iniciales = lector_catalogo.iniciales()
    assert len([f for f in iniciales if f["cada_min"] == 60]) == 32
    # Los medios que no dejan leer su RSS van por Google con «site:».
    sitios = {f["nombre"]: f for f in iniciales
              if f["direccion"].startswith("site:")}
    assert sitios["Ríodoce"]["tipo"] == "busqueda"
    assert sitios["Ríodoce"]["regiones"] == ["Sinaloa"]
    assert "site%3Ariodoce.mx" in lector.direccion_de(
        m.FuenteLector(tipo="busqueda", direccion="site:riodoce.mx"))
    assert all(f["tipo"] in lector.TIPOS for f in iniciales)
    assert json.dumps(iniciales)          # se pueden guardar tal cual


def test_los_enlaces_raros_no_pasan():
    rss = (b"<rss><channel><item><title>Asalto en la autopista</title>"
           b"<link>javascript:alert(1)</link></item><item><title>Bloqueo en "
           b"la caseta</title><link>/nota/9</link></item></channel></rss>")
    notas = lector.leer_rss(rss, "https://medio.mx/rss")
    assert notas[0]["url"] is None
    assert notas[1]["url"] == "https://medio.mx/nota/9"


def test_no_lee_direcciones_internas():
    for ip in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.9"):
        with mock.patch("socket.getaddrinfo",
                        return_value=[(2, 1, 6, "", (ip, 443))]):
            with pytest.raises(Exception) as e:
                lector._direccion_publica("https://medio.mx/rss")
            assert "pública" in str(e.value.detail)
    with mock.patch("socket.getaddrinfo",
                    return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
        lector._direccion_publica("https://medio.mx/rss")
    with pytest.raises(Exception):
        lector._direccion_publica("file:///etc/passwd")


def test_lo_que_claude_no_contesta_no_se_paga_dos_veces():
    fid = _fuente()
    db = SessionLocal()
    try:
        lector.leer_fuente(db, db.get(m.FuenteLector, fid),
                           _Cliente(_Respuesta(_rss(NOTAS[0], NOTAS[2]))),
                           AHORA)
        # Contesta solo la segunda, y con el numero como texto.
        a, b = _con_claude([[{"n": "2", "es_hecho": True,
                              "tipo": "Bloqueo carretero",
                              "estado": "Sinaloa", "mismo_que": 7}]])
        with a, b:
            lector.entender(db, AHORA)
        estados = sorted(n.estado for n in db.query(m.NotaLector))
        assert estados == ["analizada", "error"]
        # Nada queda como nueva: la siguiente vuelta no las vuelve a pagar.
        a, b = _con_claude([])
        with a, b:
            assert lector.entender(db, AHORA) == {"notas": 0, "hallazgos": 0}
    finally:
        db.close()


def test_lo_nuevo_de_un_hecho_que_ya_es_evento_va_a_su_evento(cliente,
                                                               sesion):
    hid = _hallazgo()
    evento = cliente.post(f"/riesgo/lector/hallazgos/{hid}/evento", json={},
                          headers=sesion("central")).json()
    db = SessionLocal()
    try:
        oficial = _fuente(tipo="medio", direccion="https://gn/rss",
                          oficial=True)
        lector.leer_fuente(db, db.get(m.FuenteLector, oficial), _Cliente(
            _Respuesta(_rss(("Fiscalía confirma dos heridos en Culiacán",
                             "Fiscalía de Sinaloa", "https://fge/1",
                             _fecha(0))))), AHORA)
        a, b = _con_claude([[{"n": 1, "es_hecho": True,
                              "mismo_que": f"H{hid}"}]])
        with a, b:
            lector.entender(db, AHORA)
        nuevo = (db.query(m.HallazgoLector)
                 .filter_by(estado="por_revisar").one())
        # Se le propone a ese evento, para sumarlo; y lo que no dijo
        # Claude no borra lo que se sabia.
        assert nuevo.evento_id == evento["id"]
    finally:
        db.close()
    ficha = cliente.get(f"/riesgo/lector/hallazgos/{nuevo.id}",
                        headers=sesion("central")).json()
    assert ficha["evento_folio"] == evento["folio"]


def _error_de_claude(codigo, tipo, mensaje):
    import httpx
    pedido = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    respuesta = httpx.Response(codigo, request=pedido, json={
        "type": "error", "error": {"type": tipo, "message": mensaje}})
    return httpx.HTTPStatusError("no", request=pedido, response=respuesta)


def test_por_que_claude_no_contesto():
    import httpx
    casos = [
        (_error_de_claude(401, "authentication_error", "invalid x-api-key"),
         "llave"),
        (_error_de_claude(400, "invalid_request_error",
                          "This API key is not scoped to a workspace"),
         "espacio"),
        (_error_de_claude(400, "invalid_request_error",
                          "Your credit balance is too low"), "saldo"),
        (_error_de_claude(529, "overloaded_error", "Overloaded"), "saturado"),
        (httpx.ConnectTimeout("lento"), "red"),
        (_error_de_claude(404, "not_found_error", "model: x"), "otro"),
    ]
    for error, esperado in casos:
        falla, detalle = lector.falla_de_claude(error)
        assert falla == esperado, (error, falla)
        assert "sk-" not in detalle
    assert lector.falla_de_claude(_error_de_claude(
        404, "not_found_error", "model: x"))[1].startswith("404")


def test_si_claude_no_contesta_la_consola_lo_dice(cliente, sesion):
    yo = sesion("central")
    fid = _fuente()
    db = SessionLocal()
    try:
        lector.leer_fuente(db, db.get(m.FuenteLector, fid),
                           _Cliente(_Respuesta(_rss(NOTAS[0], NOTAS[2]))),
                           AHORA)
        db.commit()

        def falla(*a, **k):
            raise _error_de_claude(400, "invalid_request_error",
                                   "This API key is not scoped to a workspace")
        with mock.patch.object(lector, "_consulta", falla), \
                mock.patch.object(settings, "anthropic_api_key", "sk-prueba"):
            salida = lector.entender(db, AHORA)
            assert salida["falla"] == "espacio"
            # Las notas esperan: nada se perdio ni se marco como error.
            assert {n.estado for n in db.query(m.NotaLector)} == {"nueva"}
            # Una segunda falla no mueve el «desde cuando».
            lector.entender(db, AHORA + timedelta(minutes=5))
            par = lector.parametros(db)
            assert par.ia_falla == "espacio"
            assert par.ia_falla_en == AHORA

            datos = cliente.get("/riesgo/lector", headers=yo).json()
            assert datos["ia"]["falla"] == "espacio"
            assert datos["ia"]["esperan"] == 2
            assert "workspace" in datos["ia"]["detalle"]
            fuentes = cliente.get("/riesgo/lector/fuentes",
                                  headers=yo).json()
            assert fuentes["ia"]["falla"] == "espacio"

        # Vuelve a contestar: el aviso se va solo.
        a, b = _con_claude([[{"n": 1, "es_hecho": False},
                             {"n": 2, "es_hecho": False}]])
        with a, b:
            lector.entender(db, AHORA + timedelta(minutes=10))
            db.expire_all()
            assert lector.parametros(db).ia_falla is None
            assert cliente.get("/riesgo/lector",
                               headers=yo).json()["ia"] is None
    finally:
        db.close()


# ------------------------------------------------- lo que publica solo (143)

TEXTO = ("Balacera en la colonia Las Quintas de Culiacán. Evite la zona "
         "y siga las indicaciones de la autoridad.")


def _para_solo(nivel=2, oficial=False, texto=TEXTO, notas=(NOTAS[2],),
               ocurrio=None, tipo="Ataque armado (arma de fuego)"):
    """Un hallazgo como lo deja Claude, listo para ver si sale solo."""
    fid = _fuente(oficial=oficial)
    db = SessionLocal()
    try:
        lector.leer_fuente(db, db.get(m.FuenteLector, fid),
                           _Cliente(_Respuesta(_rss(*notas))), AHORA)
        dijo = [{"n": 1, "es_hecho": True, "estado": "Sinaloa",
                 "municipio": "Culiacán", "nivel": nivel,
                 "tipo": tipo,
                 "titulo": "Balacera en Culiacán", "texto_cliente": texto}]
        if ocurrio:
            dijo[0]["ocurrio"] = ocurrio.isoformat()
        dijo += [{"n": i + 1, "es_hecho": True, "mismo_que": "N1"}
                 for i in range(1, len(notas))]
        a, b = _con_claude([dijo])
        with a, b:
            lector.entender(db, AHORA)
        db.commit()
        return db.query(m.HallazgoLector).order_by(
            m.HallazgoLector.id.desc()).first().id
    finally:
        db.close()


def _publicar_solos():
    db = SessionLocal()
    try:
        n = lector.publicar_solos(db, AHORA)
        db.commit()
        return n
    finally:
        db.close()


def test_lo_oficial_de_nivel_2_sale_solo_y_firma_connect(cliente, sesion):
    hid = _para_solo(oficial=True)
    assert _publicar_solos() == 1
    db = SessionLocal()
    try:
        h = db.get(m.HallazgoLector, hid)
        assert h.estado == "evento" and h.revisado_por_id is None
        e = db.get(m.EventoRiesgo, h.evento_id)
        assert e.estado == m.EstadoEvento.PUBLICADO
        assert (e.auto_regla, e.auto_dato) == ("oficial", "Fuente busqueda")
        assert e.texto_cliente == TEXTO and e.publicado_por_id is None
        assert e.verificacion == m.VerificacionEvento.OFICIAL
        firmas = {(c.quien, c.accion) for c in
                  db.query(m.CambioEvento).filter_by(evento_id=e.id)}
        assert ("Connect", "publico") in firmas
        assert all(q == "Connect" for q, _ in firmas)
        publico = db.query(m.CambioEvento).filter_by(
            evento_id=e.id, accion="publico").one()
        assert "fuente oficial (Fuente busqueda)" in publico.detalle
        folio = e.folio
    finally:
        db.close()
    # La consola lo ve marcado, y lo que hizo hoy por regla.
    yo = sesion("central")
    mapa = cliente.get("/riesgo/mapa", headers=yo)
    assert mapa.status_code == 200, mapa.text
    vivos = {x["folio"]: x for x in mapa.json()["publicados"]}
    assert vivos[folio]["auto_regla"] == "oficial"
    solos = cliente.get("/riesgo/lector/fuentes", headers=yo).json()["solos"]
    assert solos["activo"] is True
    assert solos["hoy"]["total"] == 1 and solos["hoy"]["oficial"] == 1
    # Ya salio: no sale dos veces.
    assert _publicar_solos() == 0


def test_lo_que_siempre_va_al_analista():
    _para_solo(nivel=3, oficial=True)                     # nivel 3
    _para_solo(oficial=True, texto="")                    # sin texto
    _para_solo(oficial=True,                              # de hace 8 h
               ocurrio=AHORA - timedelta(hours=8))
    _para_solo(nivel=2)                                   # una sola nota
    assert _publicar_solos() == 0


def test_lo_confirmado_por_tres_medios_y_lo_informativo():
    otros = (("Bloqueo en la México-Puebla, km 72", "Milenio",
              "https://milenio.com/x", _fecha(1)),
             ("Bloqueo en la autopista México-Puebla", "El Sol",
              "https://elsol.com/y", _fecha(1)),
             ("Bloquean la México-Puebla a la altura de Texmelucan",
              "Excélsior", "https://excelsior.com/z", _fecha(1)))
    hid = _para_solo(notas=otros)
    informativo = _para_solo(nivel=1, notas=(NOTAS[0],),
                             tipo="Bloqueo carretero")
    db = SessionLocal()
    try:
        par = lector.parametros(db)
        par.solo_informativo = False
        db.commit()
    finally:
        db.close()
    assert _publicar_solos() == 1                 # el confirmado, no el 1
    db = SessionLocal()
    try:
        e = db.get(m.EventoRiesgo, db.get(m.HallazgoLector, hid).evento_id)
        assert (e.auto_regla, e.auto_dato) == ("confirmado", "3")
        assert db.get(m.HallazgoLector, informativo).estado == "por_revisar"
        lector.parametros(db).solo_informativo = True
        db.commit()
    finally:
        db.close()
    assert _publicar_solos() == 1
    db = SessionLocal()
    try:
        h = db.get(m.HallazgoLector, informativo)
        assert db.get(m.EventoRiesgo, h.evento_id).auto_regla == \
            "informativo"
        # Apagado, nada sale solo.
        lector.parametros(db).solo_activo = False
        db.commit()
    finally:
        db.close()
    _para_solo(oficial=True)
    assert _publicar_solos() == 0


def test_las_reglas_las_mueve_quien_lleva_el_catalogo(cliente, sesion):
    r = cliente.put("/riesgo/lector/parametros", headers=sesion("rrhh"),
                    json={"solo_activo": False})
    assert r.status_code == 403
    r = cliente.put("/riesgo/lector/parametros",
                    headers=sesion("diroperaciones"),
                    json={"solo_oficial": False, "solo_activo": True})
    assert r.status_code == 200, r.text
    solos = r.json()["solos"]
    assert solos["oficial"] is False and solos["activo"] is True
    assert solos["confirmado"] is True


def test_el_texto_de_claude_llega_al_evento_que_crea_el_analista(cliente,
                                                                 sesion):
    hid = _para_solo(nivel=3)
    r = cliente.post(f"/riesgo/lector/hallazgos/{hid}/evento", json={},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert r.json()["texto_cliente"] == TEXTO
    assert r.json()["estado"] == "propuesto" and r.json()["auto_regla"] is None


def test_lo_violento_nunca_es_informativo_y_la_detencion_no_sale_sola():
    """Seccion 146: el primer dia salio solo un «hombre muere en ataque
    armado» como nivel 1, y cinco detenciones."""
    ataque = _para_solo(nivel=1)
    detencion = _para_solo(nivel=1, notas=(NOTAS[0],), tipo="Detención")
    db = SessionLocal()
    try:
        assert db.get(m.HallazgoLector, ataque).nivel == 2
        assert db.get(m.HallazgoLector, detencion).nivel == 1
        par = lector.parametros(db)
        par.solo_oficial = par.solo_confirmado = False   # solo informativo
        db.commit()
    finally:
        db.close()
    assert _publicar_solos() == 0
    db = SessionLocal()
    try:
        assert db.get(m.HallazgoLector, detencion).estado == "por_revisar"
        assert db.get(m.HallazgoLector, ataque).estado == "por_revisar"
    finally:
        db.close()



def test_lo_de_3_y_4_muy_confirmado_sale_al_momento():
    """Seccion 147: si esta muy confirmado, no espera a que el analista
    llegue; el 4 sale como 4 sin el jefe de turno."""
    tres = (("Bloqueo en la México-Puebla, km 72", "Milenio",
             "https://milenio.com/x", _fecha(1)),
            ("Bloqueo en la autopista México-Puebla", "El Sol",
             "https://elsol.com/y", _fecha(1)),
            ("Bloquean la México-Puebla en Texmelucan", "Excélsior",
             "https://excelsior.com/z", _fecha(1)))
    # Otras notas (cada nota se lee una vez: con los mismos enlaces no
    # entrarian).
    cuatro = tuple((t, medio, url + "4", f) for t, medio, url, f in tres) + (
        ("Bloqueo total en la México-Puebla", "Proceso",
         "https://proceso.com/w", _fecha(1)),)
    solo_una = _para_solo(nivel=3, oficial=True)              # 1 fuente
    alto = _para_solo(nivel=3, oficial=True, notas=tres)      # oficial + 2
    critico = _para_solo(nivel=4, notas=cuatro)               # 4 medios
    assert _publicar_solos() == 2
    db = SessionLocal()
    try:
        assert db.get(m.HallazgoLector, solo_una).estado == "por_revisar"
        e3 = db.get(m.EventoRiesgo, db.get(m.HallazgoLector, alto).evento_id)
        assert e3.estado == m.EstadoEvento.PUBLICADO and e3.nivel == 3
        assert (e3.auto_regla, e3.auto_dato) == ("alto", "3")
        e4 = db.get(m.EventoRiesgo,
                    db.get(m.HallazgoLector, critico).evento_id)
        assert e4.estado == m.EstadoEvento.PUBLICADO and e4.nivel == 4
        assert e4.auto_regla == "critico" and e4.publicado_por_id is None
        nota = db.query(m.CambioEvento).filter_by(
            evento_id=e4.id, accion="publico").one()
        assert "sin el jefe de turno" in nota.detalle
        # Apagadas, el 3 y el 4 esperan al analista.
        par = lector.parametros(db)
        par.solo_alto = par.solo_critico = False
        db.commit()
    finally:
        db.close()
    _para_solo(nivel=4, notas=tuple((t, medio, url + "b", f)
                                    for t, medio, url, f in cuatro))
    assert _publicar_solos() == 0


def test_lo_que_publica_una_persona_en_4_sigue_esperando(
        cliente, sesion, publicar):  # noqa: F811
    """La segunda firma del 4 solo se salta en lo que publica el lector."""
    e = publicar(nivel=4)
    assert e["estado"] == "por_confirmar"


def test_los_informativos_van_aparte_y_no_se_cuentan(cliente, sesion):
    """Seccion 148: lo de nivel 1 va aparte en la cola; la cuenta de la
    pestana es solo lo que espera al analista."""
    grave = _hallazgo(nota=NOTAS[2])
    info = _hallazgo(nota=NOTAS[0])
    db = SessionLocal()
    try:
        db.get(m.HallazgoLector, info).nivel = 1
        db.commit()
    finally:
        db.close()
    vista = cliente.get("/riesgo/lector", headers=sesion("central")).json()
    assert [x["id"] for x in vista["hallazgos"]] == [grave, info]
    assert vista["cuenta"] == {"revisar": 1, "informativos": 1,
                               "vigencia_horas": lector.VIGENCIA_DEL_HALLAZGO}

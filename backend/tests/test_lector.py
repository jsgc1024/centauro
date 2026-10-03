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
from tests.test_riesgo_clientes import cat  # noqa: F401

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

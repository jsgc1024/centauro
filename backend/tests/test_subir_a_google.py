"""La copia del respaldo fuera del servidor, al deposito de Google (seccion 68).

Se prueba contra un Google de mentiras que habla lo mismo que el de
verdad para esto: el servidor de metadatos da el permiso, la subida
reanudable contesta 308 con lo que ya recibio, y el objeto dice su tamano
y su md5.
"""
import base64
import hashlib
import http.server
import json
import os
import threading
import urllib.parse

import pytest

import subir_a_google as s

DESTINO = "gs://centauro-respaldos-prueba/postgres"
NOMBRE = "postgres/centauro-20260926-0230.dump"


class Google:
    def __init__(self):
        self.objetos = {}
        self.sesiones = {}
        self.permisos = 0
        self.cortar_en = None          # el byte donde la subida se cae una vez
        self.md5_de_otro = False       # alla quedo algo distinto


def _manejador(google):
    class Manejador(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _contestar(self, status, cuerpo=b"", cabeceras=None):
            self.send_response(status)
            for k, v in (cabeceras or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _estado(self, sesion):
            if sesion["nombre"] in google.objetos:
                return self._contestar(200, b"{}")
            n = len(sesion["datos"])
            return self._contestar(308, cabeceras={"Range": f"bytes=0-{n - 1}"} if n else {})

        def do_GET(self):
            ruta = urllib.parse.urlsplit(self.path).path
            if ruta.endswith("/instance/service-accounts/default/token"):
                if self.headers.get("Metadata-Flavor") != "Google":
                    return self._contestar(403)
                google.permisos += 1
                return self._contestar(200, json.dumps(
                    {"access_token": f"permiso-{google.permisos}",
                     "expires_in": 3599}).encode())
            if self.headers.get("Authorization", "").startswith("Bearer ") is False:
                return self._contestar(401)
            nombre = urllib.parse.unquote(ruta.split("/o/", 1)[1])
            datos = google.objetos.get(nombre)
            if datos is None:
                return self._contestar(404)
            md5 = hashlib.md5(datos + (b"!" if google.md5_de_otro else b"")).digest()
            return self._contestar(200, json.dumps(
                {"name": nombre, "size": str(len(datos)),
                 "md5Hash": base64.b64encode(md5).decode()}).encode())

        def do_POST(self):
            partes = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(partes.query)
            assert partes.path == "/upload/storage/v1/b/centauro-respaldos-prueba/o"
            assert q["uploadType"] == ["resumable"]
            nombre = q["name"][0]
            if q.get("ifGenerationMatch") == ["0"] and nombre in google.objetos:
                return self._contestar(412)
            sid = str(len(google.sesiones) + 1)
            google.sesiones[sid] = {"nombre": nombre, "datos": bytearray(),
                                    "total": int(self.headers["X-Upload-Content-Length"])}
            puerto = self.server.server_address[1]
            return self._contestar(200, cabeceras={
                "Location": f"http://127.0.0.1:{puerto}/sesion/{sid}"})

        def do_PUT(self):
            sesion = google.sesiones[self.path.rsplit("/", 1)[1]]
            cuerpo = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            rango = self.headers["Content-Range"]
            if rango.startswith("bytes */"):
                return self._estado(sesion)
            inicio = int(rango.split()[1].split("-")[0])
            assert inicio == len(sesion["datos"]), "se salto o repitio un pedazo"
            if google.cortar_en is not None and inicio <= google.cortar_en < inicio + len(cuerpo):
                # Llega solo una parte y la conexion se cae.
                sesion["datos"] += cuerpo[:google.cortar_en - inicio]
                google.cortar_en = None
                return self._contestar(503)
            sesion["datos"] += cuerpo
            if len(sesion["datos"]) >= sesion["total"]:
                google.objetos[sesion["nombre"]] = bytes(sesion["datos"])
                return self._contestar(200, json.dumps({"name": sesion["nombre"]}).encode())
            return self._estado(sesion)

    return Manejador


@pytest.fixture
def google(monkeypatch):
    g = Google()
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _manejador(g))
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}"
    monkeypatch.setattr(s, "METADATOS", base + "/computeMetadata/v1")
    monkeypatch.setattr(s, "STORAGE", base)
    monkeypatch.setattr(s, "PARTE", 256 * 1024)
    yield g
    servidor.shutdown()


@pytest.fixture
def respaldo(tmp_path):
    ruta = tmp_path / "centauro-20260926-0230.dump"
    ruta.write_bytes(os.urandom(700 * 1024))      # tres pedazos de 256 KiB
    return ruta


def test_sube_por_partes_y_verifica_lo_que_llego(google, respaldo):
    r = s.subir(str(respaldo), DESTINO)
    assert google.objetos[NOMBRE] == respaldo.read_bytes()
    assert r["objeto"] == f"gs://centauro-respaldos-prueba/{NOMBRE}"
    assert r["bytes"] == 700 * 1024
    assert google.permisos == 1


def test_si_se_corta_sigue_desde_donde_llego(google, respaldo):
    google.cortar_en = 300 * 1024                  # a media segunda parte
    esperas = []
    s.subir(str(respaldo), DESTINO, dormir=esperas.append)
    assert google.objetos[NOMBRE] == respaldo.read_bytes()
    assert esperas == [2]


def test_nunca_escribe_encima_de_otro_respaldo(google, respaldo):
    google.objetos[NOMBRE] = b"el de anoche"
    with pytest.raises(s.Fallo, match="ya existe"):
        s.subir(str(respaldo), DESTINO)
    assert google.objetos[NOMBRE] == b"el de anoche"


def test_si_alla_no_cuadra_no_se_da_por_bueno(google, respaldo):
    google.md5_de_otro = True
    with pytest.raises(s.Fallo, match="La copia no sirve"):
        s.subir(str(respaldo), DESTINO)


def test_sin_permiso_de_la_maquina_sale_con_error(respaldo, monkeypatch, capsys):
    # Nadie contesta en ese puerto: fuera de Google no hay servidor de
    # metadatos.
    monkeypatch.setattr(s, "METADATOS", "http://127.0.0.1:9/computeMetadata/v1")
    assert s.main([str(respaldo), DESTINO]) == 1
    assert capsys.readouterr().out.startswith("ERROR:")


def test_el_destino_tiene_que_ser_de_google(respaldo):
    with pytest.raises(s.Fallo, match="gs://"):
        s.subir(str(respaldo), "s3://otro/lado")


def test_main_dice_que_quedo(google, respaldo, capsys):
    assert s.main([str(respaldo), DESTINO]) == 0
    dicho = capsys.readouterr().out
    assert "Subido y verificado del otro lado" in dicho
    assert f"{700 * 1024} bytes" in dicho

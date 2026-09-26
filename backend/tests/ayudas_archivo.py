# -*- coding: utf-8 -*-
"""Lo que arman las pruebas del archivo de comprobantes (seccion 69).

Un Google de mentiras que habla lo mismo que el de verdad para esto --el
permiso de la maquina, la subida en una sola peticion que nunca escribe
encima, lo que dice que tiene y la foto de vuelta--, y servicios ya
cerrados con sus fotos, armados directo en la base: lo que se prueba
aqui es el archivo, no el camino para cerrar un servicio, que tiene sus
propias pruebas.
"""
import base64
import hashlib
import http.server
import json
import os
import threading
import urllib.parse
from datetime import date, datetime, timedelta

from ayudas import crear_servicio, jornada, manana

DEPOSITO = "centauro-archivo-prueba"


# ================================================================ Google

class Google:
    def __init__(self):
        self.objetos = {}          # nombre -> {"datos", "tipo", "metadatos"}
        self.subidas = []          # cada POST, en orden
        self.permisos = 0
        self.caido = False         # contesta 503 a todo lo que se suba
        self.md5_de_otro = False   # dice que tiene otra cosa
        self.perder_respuesta = 0  # guarda la foto y contesta 503, n veces

    def huella(self, nombre):
        return hashlib.md5(self.objetos[nombre]["datos"]).hexdigest()


def _manejador(g):
    class Manejador(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _contestar(self, status, cuerpo=b"", tipo="application/json"):
            if isinstance(cuerpo, (dict, list)):
                cuerpo = json.dumps(cuerpo).encode()
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _recurso(self, nombre):
            o = g.objetos[nombre]
            datos = o["datos"] + (b"!" if g.md5_de_otro else b"")
            return {"name": nombre, "bucket": DEPOSITO,
                    "size": str(len(o["datos"])),
                    "md5Hash": base64.b64encode(
                        hashlib.md5(datos).digest()).decode(),
                    "contentType": o["tipo"], "metadata": o["metadatos"]}

        def do_GET(self):
            partes = urllib.parse.urlsplit(self.path)
            if partes.path.endswith("/instance/service-accounts/default/token"):
                if self.headers.get("Metadata-Flavor") != "Google":
                    return self._contestar(403)
                g.permisos += 1
                return self._contestar(200, {"access_token": "permiso",
                                             "expires_in": 3599})
            if not self.headers.get("Authorization", "").startswith("Bearer "):
                return self._contestar(401)
            prefijo = f"/storage/v1/b/{DEPOSITO}/o/"
            if not partes.path.startswith(prefijo):
                return self._contestar(404)
            nombre = urllib.parse.unquote(partes.path[len(prefijo):])
            if nombre not in g.objetos:
                return self._contestar(404, {"error": "no esta"})
            if urllib.parse.parse_qs(partes.query).get("alt") == ["media"]:
                o = g.objetos[nombre]
                return self._contestar(200, o["datos"], o["tipo"])
            return self._contestar(200, self._recurso(nombre))

        def do_POST(self):
            partes = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(partes.query)
            assert partes.path == f"/upload/storage/v1/b/{DEPOSITO}/o"
            assert q["uploadType"] == ["multipart"]
            # Nunca se escribe encima: la subida lo pide siempre.
            assert q["ifGenerationMatch"] == ["0"]
            assert self.headers["Authorization"] == "Bearer permiso"
            cuerpo = self.rfile.read(int(self.headers["Content-Length"]))
            if g.caido:
                return self._contestar(503, {"error": "dormido"})
            frontera = self.headers["Content-Type"].split("boundary=")[1]
            pedazos = cuerpo.split(b"--" + frontera.encode())
            metadatos = json.loads(pedazos[1].split(b"\r\n\r\n", 1)[1][:-2])
            cabeza, datos = pedazos[2].split(b"\r\n\r\n", 1)
            datos = datos[:-2]
            tipo = cabeza.decode().split("Content-Type:")[1].strip()
            nombre = metadatos["name"]
            g.subidas.append(nombre)
            if nombre in g.objetos:
                return self._contestar(412, {"error": "ya existe"})
            g.objetos[nombre] = {"datos": datos, "tipo": tipo,
                                 "metadatos": metadatos.get("metadata", {})}
            if g.perder_respuesta:
                g.perder_respuesta -= 1
                return self._contestar(503, {"error": "se corto"})
            return self._contestar(200, self._recurso(nombre))

    return Manejador


def levantar_google(monkeypatch):
    """Un Google de mentiras en un puerto local, y el archivo prendido
    apuntando a el. Devuelve (google, apagar)."""
    from app import archivo
    from app.config import settings

    g = Google()
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _manejador(g))
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}"
    monkeypatch.setattr(archivo, "METADATOS", base + "/computeMetadata/v1")
    monkeypatch.setattr(archivo, "STORAGE", base)
    monkeypatch.setattr(settings, "archivo_destino", f"gs://{DEPOSITO}")
    # Nada de syslog de la maquina de quien corre las pruebas.
    monkeypatch.setattr(archivo, "SYSLOG", "/no/existe/dev-log")
    return g, servidor.shutdown


# ================================================================ las fotos

def foto(semilla: int) -> tuple[str, bytes]:
    """Una foto distinta cada vez, como data URI y en bytes."""
    datos = b"\xff\xd8\xff\xe0" + bytes([semilla % 256]) * 16 + os.urandom(2048)
    return "data:image/jpeg;base64," + base64.b64encode(datos).decode(), datos


def _viatico(db, m, jornada_id, persona_id, comprobantes, devoluciones,
             fotos, semilla):
    """Un viatico con sus comprobantes y devoluciones, cada uno con foto."""
    total = sum(monto for monto, _ in comprobantes)
    devuelto = sum(monto for monto, estatus in devoluciones
                   if estatus == "confirmada")
    v = m.AsignacionViatico(
        jornada_id=jornada_id, persona_id=persona_id,
        escenario=m.EscenarioViatico.FULL_DAY_LOCAL,
        monto_total=total + devuelto, monto_comprobado=total,
        monto_devuelto=devuelto, moneda=m.Moneda.MXN,
        estatus=m.EstatusViatico.CERRADO)
    db.add(v)
    db.flush()
    for monto, concepto in comprobantes:
        uri, datos = foto(semilla[0])
        semilla[0] += 1
        c = m.Comprobante(asignacion_id=v.id,
                          concepto=m.ConceptoViatico(concepto),
                          tipo=m.TipoComprobante.FACTURA, monto=monto,
                          imagen=uri, validado=True)
        db.add(c)
        db.flush()
        fotos[("comprobante", c.id)] = datos
    for monto, estatus in devoluciones:
        uri, datos = foto(semilla[0])
        semilla[0] += 1
        d = m.DevolucionViatico(
            asignacion_id=v.id, monto=monto, moneda=m.Moneda.MXN,
            referencia=f"SPEI-{semilla[0]:04d}", comprobante=uri,
            estatus=m.EstatusDevolucion(estatus),
            declarada_en=datetime(2026, 12, 4, 18, 0))
        db.add(d)
        db.flush()
        fotos[("devolucion", d.id)] = datos
    return v


def _cierre(db, m, servicio_id, estatus, facturado_en, aprobado_en,
            contrato_id=None, total="48600.00", factura="F-01245"):
    abierto = (facturado_en or aprobado_en or datetime(2026, 12, 6)) - timedelta(days=4)
    c = m.Cierre(
        servicio_id=servicio_id, contrato_id=contrato_id,
        abierto_en=abierto, limite_consultor=abierto + timedelta(hours=48),
        estatus=m.EstatusCierre(estatus), total_ejecutado=total,
        aprobado_en=aprobado_en, facturado_en=facturado_en,
        factura_odoo=factura if facturado_en else None)
    db.add(c)
    db.flush()
    return c


GASTOS_JUAN = [(1018.40, "combustible"), (164.00, "casetas"), (585.00, "alimentos")]
GASTOS_LUIS = [(1740.00, "hospedaje"), (707.60, "combustible")]


def eventual(cliente, sesion, datos, *, estatus="facturado",
             facturado_en=datetime(2026, 12, 10, 12, 0),
             aprobado_en=datetime(2026, 12, 9, 17, 30),
             offset=600, devoluciones=(("285.00", "confirmada"),),
             consultor="Ana Solis", total="48600.00", factura="F-01245"):
    """Un eventual de un dia con Juan y Luis, cerrado como se pida.

    Juan trae tres tickets; Luis dos y sus devoluciones. Devuelve lo que
    las pruebas necesitan, con los bytes de cada foto para comparar lo que
    llega al archivo."""
    from app import models as m
    from app.db import SessionLocal

    s = crear_servicio(
        cliente, sesion("consultor"), datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"][consultor]["id"])
    jornada_id = s["equipos"][0]["jornadas"][0]["id"]
    fotos = {}
    with SessionLocal() as db:
        semilla = [offset]
        juan = _viatico(db, m, jornada_id, datos["personal"]["Juan Ramirez"]["id"],
                        GASTOS_JUAN, [], fotos, semilla)
        luis = _viatico(db, m, jornada_id, datos["personal"]["Luis Mendoza"]["id"],
                        GASTOS_LUIS, [(float(x), e) for x, e in devoluciones],
                        fotos, semilla)
        cierre = _cierre(db, m, s["id"], estatus, facturado_en, aprobado_en,
                         total=total, factura=factura)
        db.commit()
        return {"servicio_id": s["id"], "folio": s["folio"],
                "cierre_id": cierre.id, "jornada_id": jornada_id,
                "viaticos": {"juan": juan.id, "luis": luis.id},
                "fotos": fotos}


def implantado_de_dos_meses(cliente, sesion, datos):
    """Un implantado con este mes y el siguiente abiertos. Devuelve el
    servicio y, por mes, (anio, mes, contrato_id, [jornada_id, ...])."""
    from app import models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    inicio = date.today().replace(day=1)
    r = cliente.post("/implantados", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "fecha_inicio": str(inicio), "dias_servicio": "lunes_viernes",
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": datos["suburban"]["id"]}],
        "unidades": [datos["suburban"]["id"]],
        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000"})
    assert r.status_code == 201, r.text
    servicio_id = r.json()["servicio_id"]
    r = cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)
    assert r.status_code in (200, 201), r.text

    meses = []
    with SessionLocal() as db:
        for k in (db.query(m.ContratoImplantado)
                  .filter_by(servicio_id=servicio_id)
                  .order_by(m.ContratoImplantado.anio,
                            m.ContratoImplantado.mes)):
            panel = cliente.get(f"/implantados/{servicio_id}/mes/{k.anio}/{k.mes}",
                                headers=h)
            assert panel.status_code == 200, panel.text
            dias = [d["jornada_id"] for d in panel.json()["dias"]
                    if d.get("jornada_id")]
            meses.append((k.anio, k.mes, k.id, dias))
        folio = db.get(m.Servicio, servicio_id).folio
    return {"servicio_id": servicio_id, "folio": folio, "meses": meses}


def cerrar_mes(servicio_id, contrato_id, jornada_id, datos, estatus,
               facturado_en, aprobado_en, semilla):
    """El mes cerrado como se pida, con un viatico de Juan y sus tickets."""
    from app import models as m
    from app.db import SessionLocal

    fotos = {}
    with SessionLocal() as db:
        _viatico(db, m, jornada_id, datos["personal"]["Juan Ramirez"]["id"],
                 GASTOS_JUAN[:2], [], fotos, [semilla])
        cierre = _cierre(db, m, servicio_id, estatus, facturado_en,
                         aprobado_en, contrato_id=contrato_id,
                         total="186000.00", factura=f"F-{semilla:05d}")
        db.commit()
        return cierre.id, fotos


def estado(tabla: str, fila_id: int) -> dict:
    """Como quedo una foto en la base."""
    from app import models as m
    from app.db import SessionLocal

    modelo = m.Comprobante if tabla == "comprobante" else m.DevolucionViatico
    with SessionLocal() as db:
        fila = db.get(modelo, fila_id)
        foto_ = fila.imagen if tabla == "comprobante" else fila.comprobante
        return {"foto": foto_, "archivado_en": fila.archivado_en,
                "objeto": fila.archivo_objeto, "md5": fila.archivo_md5,
                "bytes": fila.archivo_bytes, "monto": fila.monto}


def archivar(hoy):
    from app import archivo
    from app.db import SessionLocal

    with SessionLocal() as db:
        return archivo.archivar(db, hoy=hoy)

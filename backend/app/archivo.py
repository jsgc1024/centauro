# -*- coding: utf-8 -*-
"""El archivo de los comprobantes (seccion 69).

Decision de Salvador, 25 de septiembre: tres meses despues de que el
servicio se factura, las fotos que subio el personal --el ticket del
gasto y la transferencia de la devolucion-- salen de Centauro y se van a
un deposito de Google, donde se guardan seis anos. **La foto se muda; el
registro se queda**: el monto, el concepto, quien la subio, cuando y si
se valido no se mueven de aqui.

Por que. La foto vive dentro de la base, como texto, y nada la sacaba
nunca: mil tickets son cuatrocientos megas mas en la base y en cada
respaldo de cada noche, para siempre. Y lo que hace falta del servicio
ya cerrado es el registro; la foto se consulta una vez cada mucho.

**El reloj.** Arranca con la factura. Mientras Odoo no este conectado,
Centauro no tiene factura que mirar y arranca con la aprobacion de
finanzas. En el implantado cada mes tiene su cierre y su reloj. Lo que
no ha cerrado no tiene reloj, y una devolucion que finanzas todavia no
confirma no se archiva: su foto es justo lo que se esta revisando.

**La mudanza no pierde nada.** Cada foto sube sin escribir encima de
nada, se le pregunta a Google que recibio --tamano y huella--, y solo si
cuadra se quita de la base, en la misma transaccion en que se anota
donde quedo. Si algo falla, la foto se queda aqui y se reintenta la
noche siguiente. Si la foto llego pero no se alcanzo a anotar, la noche
siguiente Google dice que ya la tiene, se compara la huella y se termina
la mudanza. No hay un momento en que la foto no este en ningun lado.

**Nace apagado.** Con `ARCHIVO_DESTINO` vacio en el .env no sale nada.

Habla con Google sin sus librerias, como `subir_a_google.py`: el permiso
lo da el servidor de metadatos de la maquina, sin llaves que guardar.
"""
import base64
import hashlib
import json
import logging
import logging.handlers
import os
import re
import secrets
import time
import urllib.parse
from calendar import monthrange
from datetime import date, datetime

import httpx
from sqlalchemy.orm import Session

from app import facturacion
from app import imagenes
from app import models as m
from app.config import settings

registro = logging.getLogger("centauro.archivo")

# Dentro de un contenedor el nombre metadata.google.internal no siempre
# se resuelve; la direccion es la misma en toda maquina de Google.
METADATOS = os.environ.get("CENTAURO_METADATOS",
                           "http://169.254.169.254/computeMetadata/v1")
STORAGE = os.environ.get("CENTAURO_STORAGE", "https://storage.googleapis.com")

# Con tres fallas seguidas se deja para la noche siguiente: casi siempre
# es que Google no contesta, y seguir intentando solo llena el registro.
SEGUIDAS = 3

# Lo que ya cerro finanzas. Antes de eso la foto se sigue revisando.
CERRADOS = (m.EstatusCierre.APROBADO, m.EstatusCierre.FACTURADO)

# El syslog de la maquina, montado en el worker (docker-compose.prod.yml).
# De ahi lo lee Google, y si dice ERROR llega el correo, igual que con el
# respaldo. Fuera del servidor no existe y no se usa.
SYSLOG = "/dev/log"
ETIQUETA = "centauro-archivo"


class Fallo(Exception):
    """Algo que impide mudar una foto. La foto se queda donde estaba."""


class YaExiste(Fallo):
    """Google ya tiene un objeto con ese nombre."""


# ================================================================ el reloj

def sumar_meses(dia: date, meses: int) -> date:
    """Meses de calendario: del 10 de diciembre al 10 de marzo. El 30 de
    noviembre mas tres cae en el ultimo de febrero, no en marzo."""
    total = dia.year * 12 + (dia.month - 1) + meses
    anio, mes = divmod(total, 12)
    return date(anio, mes + 1, min(dia.day, monthrange(anio, mes + 1)[1]))


def reloj(cierre: m.Cierre, conexion: bool) -> dict | None:
    """Desde cuando cuentan los tres meses de este cierre, y cuando se
    archiva. None si todavia no hay reloj.

    `conexion` es si Centauro esta conectado a Odoo: sin conexion no
    hay factura que esperar y cuenta la aprobacion de finanzas. Con
    conexion, lo aprobado sin factura espera a su factura.
    """
    if cierre.estatus not in CERRADOS:
        return None
    if cierre.facturado_en:
        desde, momento = "factura", cierre.facturado_en
    elif not conexion and cierre.aprobado_en:
        desde, momento = "aprobacion", cierre.aprobado_en
    else:
        return None
    inicio = momento.date()
    return {"desde": desde, "inicio": inicio,
            "archivo": sumar_meses(inicio, settings.archivo_meses)}


# ============================================= de que cierre es cada viatico

def en_trozos(ids, tamano: int = 5000):
    ids = list(ids)
    for i in range(0, len(ids), tamano):
        yield ids[i:i + tamano]


def cierres_de(db: Session, asignaciones) -> dict[int, m.Cierre]:
    """El cierre de cada viatico: el eventual por su servicio, el
    implantado por el mes de su dia."""
    filas = []
    for trozo in en_trozos(asignaciones):
        filas += (db.query(m.AsignacionViatico.id, m.Equipo.servicio_id,
                           m.Servicio.tipo, m.Jornada.fecha)
                  .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
                  .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                  .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
                  .filter(m.AsignacionViatico.id.in_(trozo)).all())
    eventuales = {s for _, s, tipo, _ in filas if tipo == m.TipoServicio.EVENTUAL}
    implantados = {s for _, s, tipo, _ in filas
                   if tipo == m.TipoServicio.IMPLANTADO}

    del_servicio = {}
    for trozo in en_trozos(eventuales):
        for c in (db.query(m.Cierre)
                  .filter(m.Cierre.servicio_id.in_(trozo),
                          m.Cierre.contrato_id.is_(None))):
            del_servicio[c.servicio_id] = c
    del_mes = {}
    for trozo in en_trozos(implantados):
        for c, k in (db.query(m.Cierre, m.ContratoImplantado)
                     .join(m.ContratoImplantado,
                           m.Cierre.contrato_id == m.ContratoImplantado.id)
                     .filter(m.ContratoImplantado.servicio_id.in_(trozo))):
            del_mes[(k.servicio_id, k.anio, k.mes)] = c

    salida = {}
    for asignacion_id, servicio_id, tipo, fecha in filas:
        cierre = (del_servicio.get(servicio_id)
                  if tipo == m.TipoServicio.EVENTUAL
                  else del_mes.get((servicio_id, fecha.year, fecha.month)))
        if cierre is not None:
            salida[asignacion_id] = cierre
    return salida


def asignaciones_por_cierre(db: Session, cierres: list) -> dict[int, list[int]]:
    """Lo mismo al reves: los viaticos de cada cierre."""
    salida = {c.id: [] for c in cierres}
    del_servicio = {c.servicio_id: c.id for c in cierres if not c.contrato_id}
    por_contrato = {c.contrato_id: c.id for c in cierres if c.contrato_id}
    del_mes = {}
    for trozo in en_trozos(por_contrato):
        for k in db.query(m.ContratoImplantado).filter(
                m.ContratoImplantado.id.in_(trozo)):
            del_mes[(k.servicio_id, k.anio, k.mes)] = por_contrato[k.id]
    servicios = set(del_servicio) | {s for s, _, _ in del_mes}
    for trozo in en_trozos(servicios):
        for asignacion_id, servicio_id, fecha in (
                db.query(m.AsignacionViatico.id, m.Equipo.servicio_id,
                         m.Jornada.fecha)
                .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                .filter(m.Equipo.servicio_id.in_(trozo))):
            cierre_id = (del_servicio.get(servicio_id)
                         or del_mes.get((servicio_id, fecha.year, fecha.month)))
            if cierre_id is not None:
                salida[cierre_id].append(asignacion_id)
    return salida


# ================================================================ Google

def partir(objeto: str) -> tuple[str, str]:
    """gs://deposito/ruta/de/la/foto.jpg -> (deposito, ruta)."""
    if not objeto or not objeto.startswith("gs://"):
        raise Fallo(f"El archivo tiene que ser un deposito de Google "
                    f"(gs://...), no '{objeto}'")
    deposito, _, ruta = objeto[5:].partition("/")
    if not deposito:
        raise Fallo(f"Falta el nombre del deposito en '{objeto}'")
    return deposito, ruta.strip("/")


class Google:
    """Lo poco que hace falta del deposito: subir, preguntar que llego y
    bajar. El permiso es el de la cuenta de la maquina, que puede guardar
    y leer pero no borrar ni escribir encima."""

    def __init__(self, destino: str, http: httpx.Client | None = None):
        self.deposito, self.prefijo = partir(destino)
        self.http = http or httpx.Client(timeout=60)
        self._permiso = None
        self._vence = 0.0

    def ruta(self, relativa: str) -> str:
        return f"{self.prefijo}/{relativa}" if self.prefijo else relativa

    def _cabeceras(self) -> dict:
        if not self._permiso or time.monotonic() >= self._vence:
            try:
                r = self.http.get(
                    f"{METADATOS}/instance/service-accounts/default/token",
                    headers={"Metadata-Flavor": "Google"}, timeout=10)
                r.raise_for_status()
                datos = r.json()
            except Exception as error:                      # noqa: BLE001
                raise Fallo("La maquina no dio permiso para el archivo "
                            f"(servidor de metadatos): {error}") from error
            self._permiso = datos["access_token"]
            self._vence = (time.monotonic()
                           + max(60, int(datos.get("expires_in", 300)) - 60))
        return {"Authorization": f"Bearer {self._permiso}"}

    def _objeto(self, ruta: str) -> str:
        return (f"{STORAGE}/storage/v1/b/{self.deposito}/o/"
                f"{urllib.parse.quote(ruta, safe='')}")

    def subir(self, ruta: str, datos: bytes, tipo: str,
              metadatos: dict) -> dict:
        """Sube la foto con sus datos en una sola peticion. Nunca escribe
        encima de otra: si el nombre ya existe, Google contesta 412."""
        frontera = "centauro-" + secrets.token_hex(12)
        cabeza = json.dumps({"name": ruta, "contentType": tipo,
                             "metadata": metadatos},
                            ensure_ascii=False).encode("utf-8")
        cuerpo = b"".join([
            f"--{frontera}\r\nContent-Type: application/json; "
            f"charset=UTF-8\r\n\r\n".encode(), cabeza,
            f"\r\n--{frontera}\r\nContent-Type: {tipo}\r\n\r\n".encode(),
            datos, f"\r\n--{frontera}--\r\n".encode()])
        r = self.http.post(
            f"{STORAGE}/upload/storage/v1/b/{self.deposito}/o",
            params={"uploadType": "multipart", "ifGenerationMatch": "0"},
            headers={**self._cabeceras(),
                     "Content-Type": f"multipart/related; boundary={frontera}"},
            content=cuerpo)
        if r.status_code == 412:
            raise YaExiste(ruta)
        if r.status_code >= 300:
            raise Fallo(f"Google no acepto la foto ({r.status_code}): "
                        f"{r.text[:200]}")
        return r.json()

    def describir(self, ruta: str) -> dict | None:
        r = self.http.get(self._objeto(ruta), headers=self._cabeceras())
        if r.status_code == 404:
            return None
        if r.status_code >= 300:
            raise Fallo(f"Google no dijo que tiene ({r.status_code})")
        return r.json()

    def bajar(self, ruta: str) -> tuple[bytes, str]:
        r = self.http.get(self._objeto(ruta), params={"alt": "media"},
                          headers=self._cabeceras())
        if r.status_code == 404:
            raise Fallo("La foto no esta en el archivo")
        if r.status_code >= 300:
            raise Fallo(f"Google no entrego la foto ({r.status_code})")
        tipo = r.headers.get("content-type", "image/jpeg").split(";")[0]
        return r.content, tipo


# ================================================================ la mudanza

def abrir(data_uri: str) -> tuple[str, bytes]:
    """El data URI guardado: su tipo y sus bytes."""
    cabeza, coma, cuerpo = (data_uri or "").partition(",")
    if not coma or not cabeza.startswith("data:") or ";base64" not in cabeza:
        raise Fallo("La foto no esta guardada como imagen: no se toca")
    tipo = cabeza[5:].split(";")[0] or "image/jpeg"
    try:
        return tipo, base64.b64decode(cuerpo, validate=False)
    except Exception as error:                              # noqa: BLE001
        raise Fallo(f"La foto no se pudo leer: {error}") from error


def _limpio(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", texto or "sin-folio")


def _que_es(fila) -> str:
    return "comprobante" if isinstance(fila, m.Comprobante) else "devolucion"


def _foto(fila) -> str | None:
    return fila.imagen if isinstance(fila, m.Comprobante) else fila.comprobante


def _cuando(fila) -> datetime | None:
    if isinstance(fila, m.Comprobante):
        return fila.subido_en
    return fila.declarada_en or fila.confirmada_en


def ruta_de(fila, folio: str, huella: str, tipo: str) -> str:
    """comprobantes/2026/CEN-2026-0612/comprobante-812-3f2a9c1b.jpg

    Con la huella en el nombre: la misma foto siempre cae en el mismo
    nombre --volver a subirla es encontrarla ya ahi-- y dos fotos
    distintas nunca chocan, aunque una base restaurada repita un numero.
    """
    que = _que_es(fila)
    cuando = _cuando(fila) or datetime.now()
    extension = imagenes.TIPOS_DE_IMAGEN.get(tipo, ".bin")
    return (f"{que}s" if que == "comprobante" else "devoluciones") + (
        f"/{cuando.year}/{_limpio(folio)}/{que}-{fila.id}-{huella[:8]}"
        f"{extension}")


def _metadatos(fila, folio: str) -> dict:
    """Lo que viaja pegado a la foto, para que el archivo se entienda
    solo aunque Centauro no estuviera."""
    asignacion = fila.asignacion
    persona = asignacion.persona.nombre if asignacion and asignacion.persona else ""
    cuando = _cuando(fila)
    datos = {"folio": folio or "", "persona": persona,
             "monto": str(fila.monto),
             "moneda": asignacion.moneda.value if asignacion and asignacion.moneda else "",
             "subida": cuando.isoformat() if cuando else "",
             "centauro": f"{_que_es(fila)}-{fila.id}"}
    if isinstance(fila, m.Comprobante):
        datos["concepto"] = fila.concepto.value if fila.concepto else ""
        datos["tipo"] = fila.tipo.value if fila.tipo else ""
    else:
        datos["referencia"] = fila.referencia or ""
    return datos


def mudar(db: Session, google: Google, fila, folio: str) -> dict:
    """Una foto al archivo, comprobada, y fuera de la base. Todo o nada."""
    tipo, datos = abrir(_foto(fila))
    huella = hashlib.md5(datos)
    ruta = google.ruta(ruta_de(fila, folio, huella.hexdigest(), tipo))
    try:
        objeto = google.subir(ruta, datos, tipo, _metadatos(fila, folio))
    except YaExiste:
        # Ya se habia subido y no se alcanzo a anotar. Con la huella en el
        # nombre, lo que esta ahi es esta misma foto; se comprueba igual.
        objeto = google.describir(ruta) or {}
    esperado = base64.b64encode(huella.digest()).decode()
    if (objeto.get("md5Hash") != esperado
            or int(objeto.get("size", -1)) != len(datos)):
        raise Fallo(f"Lo que quedo en el archivo no cuadra con la foto "
                    f"({ruta}). La foto se queda en Centauro.")

    fila.archivado_en = datetime.now()
    fila.archivo_objeto = f"gs://{google.deposito}/{ruta}"
    fila.archivo_md5 = huella.hexdigest()
    fila.archivo_bytes = len(datos)
    if isinstance(fila, m.Comprobante):
        fila.imagen = None
    else:
        fila.comprobante = None
    db.commit()
    return {"objeto": fila.archivo_objeto, "bytes": len(datos)}


def _fotos(db: Session, asignaciones: list):
    """Las fotos de estos viaticos que todavia estan en la base, una por
    una: cada una pesa cientos de kilobytes y no se cargan todas juntas."""
    for trozo in en_trozos(asignaciones):
        ids = [i for (i,) in (db.query(m.Comprobante.id)
                              .filter(m.Comprobante.asignacion_id.in_(trozo),
                                      m.Comprobante.imagen.isnot(None))
                              .order_by(m.Comprobante.id))]
        for i in ids:
            fila = db.get(m.Comprobante, i)
            if fila is not None and fila.imagen:
                yield fila
        ids = [i for (i,) in (
            db.query(m.DevolucionViatico.id)
            .filter(m.DevolucionViatico.asignacion_id.in_(trozo),
                    m.DevolucionViatico.comprobante.isnot(None),
                    m.DevolucionViatico.estatus != m.EstatusDevolucion.DECLARADA)
            .order_by(m.DevolucionViatico.id))]
        for i in ids:
            fila = db.get(m.DevolucionViatico, i)
            if fila is not None and fila.comprobante:
                yield fila


def _con_foto(db: Session) -> set[int]:
    """Los viaticos que todavia tienen alguna foto que se puede mudar."""
    con_foto = {a for (a,) in (db.query(m.Comprobante.asignacion_id)
                               .filter(m.Comprobante.imagen.isnot(None))
                               .distinct())}
    con_foto |= {a for (a,) in (
        db.query(m.DevolucionViatico.asignacion_id)
        .filter(m.DevolucionViatico.comprobante.isnot(None),
                m.DevolucionViatico.estatus != m.EstatusDevolucion.DECLARADA)
        .distinct())}
    return con_foto


def _contar(db: Session, asignaciones: list) -> int:
    total = 0
    for trozo in en_trozos(asignaciones):
        total += (db.query(m.Comprobante.id)
                  .filter(m.Comprobante.asignacion_id.in_(trozo),
                          m.Comprobante.imagen.isnot(None)).count())
        total += (db.query(m.DevolucionViatico.id)
                  .filter(m.DevolucionViatico.asignacion_id.in_(trozo),
                          m.DevolucionViatico.comprobante.isnot(None),
                          m.DevolucionViatico.estatus
                          != m.EstatusDevolucion.DECLARADA).count())
    return total


def archivar(db: Session, hoy: date | None = None,
             google: Google | None = None) -> dict:
    """La tarea de la noche: todo lo que ya cumplio sus tres meses."""
    destino = (settings.archivo_destino or "").strip()
    if not destino:
        return {"resultado": "apagado", "archivadas": 0, "fallidas": 0,
                "pendientes": 0, "errores": []}
    hoy = hoy or date.today()
    conexion = facturacion.hay_conexion()

    maduros: dict[int, list] = {}
    for asignacion_id, cierre in cierres_de(db, _con_foto(db)).items():
        r = reloj(cierre, conexion)
        if r and r["archivo"] <= hoy:
            maduros.setdefault(cierre.id, [r["archivo"], cierre.id,
                                           cierre.servicio.folio, []])
            maduros[cierre.id][3].append(asignacion_id)
    # Lo mas viejo primero: si el tope corta, corta lo mas nuevo.
    orden = sorted(maduros.values(), key=lambda x: (x[0], x[1]))
    por_mudar = sum(_contar(db, x[3]) for x in orden)

    google = google or Google(destino)
    tope = max(0, settings.archivo_por_noche)
    archivadas = fallidas = seguidas = 0
    errores: list[str] = []
    parar = False
    for _, _, folio, asignaciones in orden:
        for fila in _fotos(db, asignaciones):
            if archivadas + fallidas >= tope:
                parar = True
                break
            try:
                mudar(db, google, fila, folio)
                archivadas += 1
                seguidas = 0
            except Exception as error:                  # noqa: BLE001
                db.rollback()
                fallidas += 1
                seguidas += 1
                errores.append(f"{folio}: {error}")
                if seguidas >= SEGUIDAS:
                    parar = True
                    break
        if parar:
            break

    pendientes = max(0, por_mudar - archivadas)
    resultado = {"resultado": "con fallas" if fallidas else "listo",
                 "archivadas": archivadas, "fallidas": fallidas,
                 "pendientes": pendientes, "errores": errores[:5]}
    _contar_la_noche(resultado)
    return resultado


# ================================================================ el aviso

def _al_sistema(texto: str) -> None:
    """Al syslog de la maquina, con su etiqueta. Si no hay syslog --fuera
    del servidor-- no pasa nada: el registro de la aplicacion lo tiene."""
    if not os.path.exists(SYSLOG):
        return
    manejador = None
    try:
        manejador = logging.handlers.SysLogHandler(address=SYSLOG)
        manejador.setFormatter(logging.Formatter(f"{ETIQUETA}: %(message)s"))
        manejador.emit(logging.LogRecord(ETIQUETA, logging.INFO, __file__, 0,
                                         texto, None, None))
    except Exception:                                       # noqa: BLE001
        registro.warning("no se pudo escribir en el syslog: %s", texto)
    finally:
        if manejador is not None:
            manejador.close()


def _contar_la_noche(r: dict) -> None:
    """Una linea por noche. Con ERROR si algo se quedo, que es lo que la
    alerta de Google busca para mandar el correo."""
    if r["fallidas"]:
        texto = (f"ERROR: {r['fallidas']} foto(s) no se pudieron archivar y "
                 f"se quedan en Centauro; se reintenta la noche siguiente. "
                 f"Archivadas: {r['archivadas']}. La primera falla: "
                 f"{r['errores'][0] if r['errores'] else '-'}")
        registro.error(texto)
    else:
        texto = (f"Archivadas: {r['archivadas']}. Quedan para las noches "
                 f"siguientes: {r['pendientes']}.")
        registro.info(texto)
    _al_sistema(texto)


# ================================================================ traerla

def traer(fila, google: Google | None = None) -> dict:
    """Una foto de vuelta del archivo, con la comparacion de su huella."""
    if not fila.archivo_objeto:
        raise Fallo("Esa foto no esta en el archivo")
    deposito, ruta = partir(fila.archivo_objeto)
    google = google or Google(f"gs://{deposito}")
    datos, tipo = google.bajar(ruta)
    return {"tipo": tipo, "datos": datos,
            "coincide": hashlib.md5(datos).hexdigest() == fila.archivo_md5}

"""Lo que entra al Nivel Centauro desde fuera (seccion 135).

**El Secretariado (SESNSP), solo.** Cada mes, alrededor del dia 18,
publica en su pagina de datos abiertos el archivo de victimas por
municipio de la metodologia 2026 (un zip con un CSV: un renglon por
municipio, delito, sexo y edad, y una columna por mes). Connect busca el
enlace en esa pagina, baja el archivo, lo suma por componente y lo
guarda. El enlace cambia cada mes (es de OneDrive), por eso se busca por
su texto y no se guarda. Si la pagina cambia y ya no se encuentra, se
dice en la consola y el analista sube el archivo a mano: el mismo zip o
el CSV.

**Las encuestas del INEGI, subidas.** La ENSU (cada tres meses, por
ciudad) y la ENVIPE (una vez al ano, por estado) se suben como una tabla
de dos columnas --lugar y valor--: es lo que el analista copia del
tabulado del INEGI. Una ciudad de la ENSU se casa con su municipio por
el nombre; la que no se reconoce se dice, no se adivina.
"""
import csv
import io
import json
import re
import unicodedata
import zipfile
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app import models as m
from app import nivel_catalogo as nc

FUENTE_SESNSP = "sesnsp"
PAGINA_SESNSP = ("https://www.gob.mx/sesnsp/acciones-y-programas/"
                 "datos-abiertos-de-incidencia-delictiva")
# El texto del enlace que se busca en esa pagina (metodologia 2026).
TEXTO_DEL_ENLACE = re.compile(
    r"Fuero com[uú]n\s*-\s*V[ií]ctimas\)\.?\s*Incidencia delictiva municipal",
    re.I)
MESES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
COLUMNAS = ("Año", "Clave_Ent", "Cve. Municipio", "Tipo de delito",
            "Subtipo de delito", "Modalidad")

ENCUESTAS = ("ensu", "envipe_percepcion", "envipe_prevalencia")
# Lo mas que puede pesar el CSV ya descomprimido.
MAXIMO_DESCOMPRIMIDO = 600 * 1024 * 1024
MAXIMO_ARCHIVO = 60 * 1024 * 1024


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def normalizar(texto: str) -> str:
    """Sin acentos, sin mayusculas, sin signos: «Culiacán Rosales» y
    «culiacan rosales» son lo mismo."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# ================================================================ el Secretariado

def _texto_del_archivo(contenido: bytes, nombre: str | None) -> str:
    if len(contenido) > MAXIMO_ARCHIVO:
        raise HTTPException(413, "El archivo pesa demasiado")
    if contenido[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(contenido)) as z:
                csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
                if not csvs:
                    raise HTTPException(400, "El zip no trae ningún CSV")
                # Un zip chico puede abrir en gigas: se mira antes.
                if z.getinfo(csvs[0]).file_size > MAXIMO_DESCOMPRIMIDO:
                    raise HTTPException(413, "El archivo pesa demasiado")
                contenido = z.read(csvs[0])
        except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError):
            raise HTTPException(400, "El zip viene dañado")
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise HTTPException(400, "No se puede leer el archivo")


def leer_sesnsp(contenido: bytes, nombre: str | None = None) -> dict:
    """Suma el archivo de victimas municipal por componente, municipio y
    mes. No toca la base."""
    texto = _texto_del_archivo(contenido, nombre)
    lector = csv.reader(io.StringIO(texto))
    try:
        encabezado = [c.strip() for c in next(lector)]
    except StopIteration:
        raise HTTPException(400, "El archivo viene vacío")
    faltan = [c for c in COLUMNAS + MESES if c not in encabezado]
    if faltan:
        raise HTTPException(400, {
            "mensaje": "Ese no es el archivo de víctimas por municipio del "
                       "Secretariado (metodología 2026)",
            "que_hacer": "Le faltan las columnas: " + ", ".join(faltan[:6]),
        })
    i = {c: encabezado.index(c) for c in COLUMNAS + MESES}
    sumas: dict[tuple, int] = {}       # (componente, clave_mun, ent, mes)
    total_mes = [0] * 12
    presentes: set[tuple] = set()      # (clave_mun, ent)
    anios = set()
    filas = 0
    for numero, fila in enumerate(lector, start=2):
        if len(fila) < len(encabezado):
            continue
        filas += 1
        try:
            anio = int(fila[i["Año"]])
            ent = f"{int(fila[i['Clave_Ent']]):02d}"
            clave = int(fila[i["Cve. Municipio"]])
            valores = [int(float(fila[i[mes]] or 0)) for mes in MESES]
        except ValueError:
            raise HTTPException(400, {
                "mensaje": f"El renglón {numero} no se entiende",
                "que_hacer": "Revisa que el año, las claves y los meses "
                             "sean números, como los publica el Secretariado"})
        anios.add(anio)
        presentes.add((clave, ent))
        for k, v in enumerate(valores):
            total_mes[k] += v
        comp = nc.componente_del_delito(fila[i["Tipo de delito"]].strip(),
                                        fila[i["Subtipo de delito"]].strip(),
                                        fila[i["Modalidad"]].strip())
        if comp is None:
            continue
        for k, v in enumerate(valores):
            if v:
                llave = (comp, clave, ent, k + 1)
                sumas[llave] = sumas.get(llave, 0) + v
    if len(anios) != 1:
        raise HTTPException(400, "El archivo trae más de un año: súbelo "
                                 "como lo publica el Secretariado, un año "
                                 "por archivo")
    # El ultimo mes con datos: los meses que faltan vienen en cero.
    ultimo = max((k + 1 for k, t in enumerate(total_mes) if t), default=0)
    if not ultimo:
        raise HTTPException(400, "El archivo no trae ningún mes con datos")
    return {"anio": anios.pop(), "ultimo_mes": ultimo, "sumas": sumas,
            "presentes": presentes, "filas": filas}


def guardar_sesnsp(db: Session, datos: dict, origen: str,
                   archivo: str | None, usuario: m.Usuario | None
                   ) -> m.CargaFuente:
    """Reemplaza lo del ano del archivo: el Secretariado corrige meses
    pasados en cada publicacion, y el archivo nuevo es la verdad."""
    pais = db.query(m.Pais).filter_by(codigo="MX").one()
    regiones = {r.clave: r.id for r in
                db.query(m.Region).filter_by(pais_id=pais.id)}
    municipios = {c: (mid, rid) for mid, c, rid in
                  db.query(m.Municipio.id, m.Municipio.clave,
                           m.Municipio.region_id)}
    anio, ultimo = datos["anio"], datos["ultimo_mes"]
    periodos = [date(anio, mes, 1) for mes in range(1, ultimo + 1)]
    db.execute(delete(m.CifraOficial).where(
        m.CifraOficial.fuente == FUENTE_SESNSP,
        m.CifraOficial.periodo.in_(periodos)))

    filas: dict[tuple, int] = {}
    # Cada municipio que aparece en el archivo reporto: va con su cero.
    for clave, ent in datos["presentes"]:
        if clave in municipios:
            mid, rid = municipios[clave]
            for comp in nc.OFICIALES:
                for p in periodos:
                    filas[(comp, rid, mid, p)] = 0
    no_reconocidos = set()
    for (comp, clave, ent, mes), v in datos["sumas"].items():
        if mes > ultimo:
            continue
        p = date(anio, mes, 1)
        if clave in municipios:
            mid, rid = municipios[clave]
        elif ent in regiones:
            # «No especificado» y claves que el CONAPO no tiene: cuentan
            # para el estado.
            mid, rid = None, regiones[ent]
            no_reconocidos.add(clave)
        else:
            continue
        filas[(comp, rid, mid, p)] = filas.get((comp, rid, mid, p), 0) + v
    if filas:
        db.execute(insert(m.CifraOficial), [
            {"fuente": FUENTE_SESNSP, "componente": c, "region_id": r,
             "municipio_id": mi, "periodo": p, "valor": v}
            for (c, r, mi, p), v in filas.items()])
    carga = m.CargaFuente(
        fuente=FUENTE_SESNSP, periodo=periodos[-1], origen=origen,
        archivo=(archivo or "")[:200] or None, filas=datos["filas"],
        usuario_id=usuario.id if usuario else None,
        nota=json.dumps({"municipios": len(datos["presentes"]),
                         "sin_municipio": sorted(no_reconocidos)[:50]}))
    db.add(carga)
    db.flush()
    return carga


def enlace_en_la_pagina(html: str) -> str | None:
    """El primer enlace de la pagina cuyo texto es el del archivo de
    victimas municipal: la pagina pone primero la metodologia vigente."""
    for href, texto in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                                  html, re.S | re.I):
        limpio = re.sub(r"<[^>]+>", " ", texto)
        limpio = re.sub(r"\s+", " ", limpio)
        if TEXTO_DEL_ENLACE.search(limpio):
            return href.replace("&amp;", "&")
    return None


def con_descarga(enlace: str) -> str:
    """Un enlace para compartir de OneDrive baja el archivo con
    download=1; sin eso entrega la pagina del visor."""
    return enlace + ("&" if "?" in enlace else "?") + "download=1"


def bajar_sesnsp(db: Session, cliente=None) -> dict:
    """Busca el archivo del mes en la pagina del Secretariado y, si es
    nuevo, lo guarda. Lo llama la tarea diaria; nunca revienta: lo que
    falla queda dicho en el resultado y en la consola."""
    import httpx
    propio = cliente is None
    cliente = cliente or httpx.Client(
        timeout=120, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Centauro Connect)"})
    try:
        pagina = cliente.get(PAGINA_SESNSP)
        pagina.raise_for_status()
        enlace = enlace_en_la_pagina(pagina.text)
        if not enlace:
            return {"resultado": "sin_enlace"}
        archivo = cliente.get(con_descarga(enlace))
        archivo.raise_for_status()
        datos = leer_sesnsp(archivo.content)
        anterior = (db.query(m.CargaFuente).filter_by(fuente=FUENTE_SESNSP)
                    .order_by(m.CargaFuente.id.desc()).first())
        hasta = date(datos["anio"], datos["ultimo_mes"], 1)
        if anterior and anterior.periodo >= hasta:
            return {"resultado": "sin_cambios", "periodo": hasta.isoformat()}
        carga = guardar_sesnsp(db, datos, "automatica", None, None)
        return {"resultado": "nuevo", "periodo": carga.periodo.isoformat(),
                "carga_id": carga.id}
    except HTTPException as e:
        return {"resultado": "archivo_raro", "detalle": str(e.detail)[:300]}
    except Exception as e:                               # noqa: BLE001
        return {"resultado": "sin_conexion", "detalle": str(e)[:300]}
    finally:
        if propio:
            cliente.close()


# ================================================================ las encuestas

def _tabla(contenido: bytes) -> list[tuple[str, str, str | None]]:
    """(lugar, valor, estado?) de un CSV de dos o tres columnas, con o sin
    encabezado, separado por coma, punto y coma o tabulador."""
    texto = _texto_del_archivo(contenido, None)
    muestra = texto[:2000]
    separador = "\t" if "\t" in muestra else (";" if muestra.count(";") >
                                              muestra.count(",") else ",")
    salida = []
    for fila in csv.reader(io.StringIO(texto), delimiter=separador):
        fila = [c.strip() for c in fila]
        if len(fila) < 2 or not fila[0]:
            continue
        valor = _numero(fila[1])
        if valor is None:
            continue                       # el encabezado o un renglon suelto
        salida.append((fila[0], valor, fila[2] if len(fila) > 2 and fila[2]
                       else None))
    if not salida:
        raise HTTPException(400, "No encontré renglones con un lugar y un "
                                 "número")
    return salida


def _numero(texto: str) -> str | None:
    """«61.5», «61,5», «34 930», «34,930» y «61.5%» como numero. Una coma
    con tres cifras detras es de miles; con una o dos, decimal."""
    t = (texto or "").replace("%", "").replace(" ", "").replace("\xa0", "")
    if "," in t and "." not in t:
        t = t.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", t) \
            else t.replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        float(t)
    except ValueError:
        return None
    return t


def _region_por_nombre(regiones: list[m.Region], texto: str) -> m.Region | None:
    n = normalizar(texto)
    for r in regiones:
        if n in (normalizar(r.nombre), r.clave.lstrip("0"), r.clave):
            return r
    alias = {"cdmx": "09", "ciudad de mexico": "09", "edomex": "15",
             "mexico": "15", "estado de mexico": "15", "coahuila de zaragoza":
             "05", "michoacan de ocampo": "16",
             "veracruz de ignacio de la llave": "30"}
    clave = alias.get(n)
    return next((r for r in regiones if r.clave == clave), None)


def _municipios_de_la_ciudad(db: Session, regiones: list[m.Region],
                             ciudad: str, estado: str | None
                             ) -> list[m.Municipio]:
    """Los municipios de una ciudad de la ENSU. Si el nombre es el de un
    estado (Ciudad de Mexico), todos los del estado; si no, el municipio
    con ese nombre, o el que es el principio del nombre («Culiacán
    Rosales» es Culiacán)."""
    region = _region_por_nombre(regiones, estado) if estado else None
    como_estado = _region_por_nombre(regiones, ciudad)
    if como_estado and normalizar(ciudad) in ("ciudad de mexico", "cdmx"):
        return db.query(m.Municipio).filter_by(region_id=como_estado.id).all()
    q = db.query(m.Municipio)
    if region:
        q = q.filter_by(region_id=region.id)
    todos = q.all()
    n = normalizar(ciudad)
    exactos = [x for x in todos if normalizar(x.nombre) == n]
    if len(exactos) == 1:
        return exactos
    if len(exactos) > 1:
        return []                          # ambiguo: que lo diga el estado
    prefijos = [x for x in todos if n.startswith(normalizar(x.nombre) + " ")]
    if prefijos:
        largo = max(len(normalizar(x.nombre)) for x in prefijos)
        mejores = [x for x in prefijos if len(normalizar(x.nombre)) == largo]
        return mejores if len(mejores) == 1 else []
    return []


def guardar_encuesta(db: Session, fuente: str, periodo: date,
                     contenido: bytes, archivo: str | None,
                     usuario: m.Usuario) -> dict:
    if fuente not in ENCUESTAS:
        raise HTTPException(400, "Esa fuente no es una encuesta")
    filas = _tabla(contenido)
    pais = db.query(m.Pais).filter_by(codigo="MX").one()
    regiones = db.query(m.Region).filter_by(pais_id=pais.id).all()
    nuevos, no_reconocidos = [], []
    for lugar, valor, estado in filas:
        if fuente == "ensu":
            municipios = _municipios_de_la_ciudad(db, regiones, lugar, estado)
            if not municipios:
                no_reconocidos.append(lugar)
                continue
            for mun in municipios:
                nuevos.append({"fuente": fuente, "periodo": periodo,
                               "region_id": mun.region_id,
                               "municipio_id": mun.id, "etiqueta": lugar[:120],
                               "valor": float(valor)})
        else:
            region = _region_por_nombre(regiones, lugar)
            if not region:
                no_reconocidos.append(lugar)
                continue
            nuevos.append({"fuente": fuente, "periodo": periodo,
                           "region_id": region.id, "municipio_id": None,
                           "etiqueta": lugar[:120], "valor": float(valor)})
    if not nuevos:
        raise HTTPException(400, {"mensaje": "No reconocí ningún lugar",
                                  "que_hacer": "Revisa que la primera "
                                  "columna traiga el nombre del estado o de "
                                  "la ciudad como lo escribe el INEGI"})
    db.execute(delete(m.EncuestaValor).where(
        m.EncuestaValor.fuente == fuente,
        m.EncuestaValor.periodo == periodo))
    db.execute(insert(m.EncuestaValor), nuevos)
    db.add(m.CargaFuente(fuente=fuente, periodo=periodo, origen="subida",
                         archivo=(archivo or "")[:200] or None,
                         filas=len(filas), usuario_id=usuario.id,
                         nota=json.dumps({"no_reconocidos": no_reconocidos})))
    db.flush()
    return {"guardados": len(nuevos), "renglones": len(filas),
            "no_reconocidos": no_reconocidos}

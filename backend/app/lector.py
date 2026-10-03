"""El lector de noticias y redes de la Central de Inteligencia (seccion 140).

Cada pocos minutos Connect lee sus fuentes --medios por su RSS, busquedas
de Google Noticias y una lista de X--, guarda cada nota una vez, se queda
con las que parecen de seguridad (por palabras) y se las pasa a Claude
para que diga que paso, donde, que tan grave y si es el mismo hecho que
otra nota. Lo que entendio queda como un *hallazgo* para el analista:
crear el evento, sumarlo a uno que ya existe o descartarlo. Nada se
publica solo (Salvador, 3 oct).

Sin la llave de Claude el lector sigue: cada nota con palabras de
seguridad sale sola, sin «lo que entendio Connect». Sin la llave de X,
la lista de X espera.

X cobra por publicacion leida: se lleva la cuenta del dia y hay un tope
que se mueve en la pantalla de fuentes.
"""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.fuentes_riesgo import normalizar

TIPOS = ("medio", "busqueda", "lista_x")
MOTIVOS = ("no_es_seguridad", "ya_paso", "repetida", "fuera_de_mexico",
           "sin_importancia")
CADA_MIN = (5, 10, 15, 30, 60, 120)
GUARDAR_DIAS = 14              # las notas sin hallazgo se borran despues
POR_LOTE = 12                  # notas por consulta a Claude
MAX_POR_VUELTA = 120           # notas que se le pasan a Claude por vuelta
X_POR_LLAMADA = 50
MODELO = "claude-haiku-4-5-20251001"
GOOGLE = ("https://news.google.com/rss/search?q={q}&hl=es-419&gl=MX"
          "&ceid=MX:es-419")

# Lo que hace que una nota merezca que Claude la lea. Es ancho a
# proposito: lo fino lo decide Claude; esto solo quita el futbol, la
# farandula y la bolsa.
PALABRAS = re.compile(r"\b(" + "|".join([
    r"balacera\w*", r"enfrentamiento\w*", r"bloque[oa]\w*", r"narcobloqueo\w*",
    r"ataque armado", r"disparos?", r"detonaciones", r"tiroteo\w*",
    r"homicidi\w+", r"asesina\w*", r"ejecuta\w*", r"secuestr\w+",
    r"levant[oó]n\w*", r"privad[oa]s? de (la|su) libertad", r"desaparec\w+",
    r"robo\w*", r"asalt\w+", r"atraco\w*", r"extorsi\w+", r"cobro de piso",
    r"narcomanta\w*", r"cuerpos?", r"fosas?", r"explosiv\w+", r"drones?",
    r"quema\w*", r"incendi\w+", r"manifestaci\w+", r"marcha\w*",
    r"protesta\w*", r"cierr\w+", r"cierran", r"toma de casetas?",
    r"paro\w*", r"normalistas", r"transportistas", r"inundaci\w+",
    r"deslave\w*", r"hurac[aá]n", r"sismo\w*", r"protecci[oó]n civil",
    r"operativo\w*", r"guardia nacional", r"sedena", r"militares",
    r"emboscad\w+", r"persecuci\w+", r"carretera\w*", r"autopista\w*",
    r"violencia", r"armad[oa]s", r"sicari\w+", r"c[aá]rtel\w*",
]) + r")\b", re.I)


def _ahora(ahora: datetime | None = None) -> datetime:
    return ahora or datetime.now(timezone.utc)


def huella(*partes: str) -> str:
    return hashlib.sha256("|".join(partes).encode()).hexdigest()


def _limpio(texto: str | None, largo: int) -> str:
    t = unescape(re.sub(r"<[^>]+>", " ", texto or ""))
    return re.sub(r"\s+", " ", t).strip()[:largo]


def parece_de_seguridad(titulo: str, texto: str = "") -> bool:
    return bool(PALABRAS.search(f"{titulo} {texto}"))


# ============================================================ leer fuentes

def _fecha(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        d = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def leer_rss(contenido: bytes) -> list[dict]:
    """Las notas de un RSS 2.0 o un Atom. En Google Noticias el medio
    viene en <source> y al final del titulo («... - Milenio»)."""
    try:
        raiz = ET.fromstring(contenido)
    except ET.ParseError:
        raise HTTPException(400, "No es un RSS: la direccion no da noticias")
    salida = []
    atom = "{http://www.w3.org/2005/Atom}"
    items = raiz.findall(".//item") or raiz.findall(f".//{atom}entry")
    for it in items:
        def de(etiqueta):
            nodo = it.find(etiqueta)
            if nodo is None:
                nodo = it.find(atom + etiqueta)
            return nodo
        titulo = _limpio(de("title").text if de("title") is not None else "",
                         400)
        enlace = de("link")
        url = None
        if enlace is not None:
            url = (enlace.text or enlace.get("href") or "").strip() or None
        guid = de("guid")
        medio_n = it.find("source")
        medio = medio_n.text.strip() if medio_n is not None and medio_n.text \
            else None
        if medio and titulo.endswith(f" - {medio}"):
            titulo = titulo[: -len(medio) - 3].strip()
        texto = de("description")
        if texto is None:
            texto = de("summary")
        fecha = de("pubDate")
        if fecha is None:
            fecha = de("published")
        if fecha is None:
            fecha = de("updated")
        if not titulo:
            continue
        salida.append({
            "id": ((guid.text if guid is not None else None) or url
                   or titulo).strip(),
            "titulo": titulo, "url": url, "medio": medio,
            "texto": _limpio(texto.text if texto is not None else "", 1500),
            "publicada_en": _fecha(fecha.text if fecha is not None else None),
        })
    return salida


def direccion_de(fuente: m.FuenteLector) -> str:
    if fuente.tipo == "busqueda":
        from urllib.parse import quote
        return GOOGLE.format(q=quote(f"{fuente.direccion} when:1d"))
    return fuente.direccion


def id_de_lista(direccion: str) -> str | None:
    """https://x.com/i/lists/1234567890 -> 1234567890"""
    hallado = re.search(r"lists/(\d+)", direccion or "")
    return hallado.group(1) if hallado else None


def leer_lista_x(cliente, lista_id: str) -> list[dict]:
    r = cliente.get(
        f"https://api.x.com/2/lists/{lista_id}/tweets",
        params={"max_results": X_POR_LLAMADA,
                "tweet.fields": "created_at,author_id",
                "expansions": "author_id", "user.fields": "username,name"},
        headers={"Authorization": f"Bearer {settings.x_bearer_token}"})
    if r.status_code in (401, 403):
        raise HTTPException(400, "X no acepta la llave (X_BEARER_TOKEN)")
    if r.status_code == 402:
        raise HTTPException(400, "La cuenta de X se quedó sin créditos")
    if r.status_code == 429:
        raise HTTPException(400, "X pide esperar: demasiadas lecturas")
    r.raise_for_status()
    datos = r.json()
    gente = {u["id"]: u for u in datos.get("includes", {}).get("users", [])}
    salida = []
    for p in datos.get("data", []):
        u = gente.get(p.get("author_id"), {})
        usuario = u.get("username", "")
        salida.append({
            "id": f"x:{p['id']}", "titulo": _limpio(p.get("text"), 400),
            "texto": "", "medio": f"@{usuario}" if usuario else "X",
            "url": (f"https://x.com/{usuario}/status/{p['id']}"
                    if usuario else None),
            "publicada_en": _fecha(p.get("created_at")),
        })
    return salida


def parametros(db: Session) -> m.ParametrosLector:
    par = db.query(m.ParametrosLector).first()
    if not par:
        par = m.ParametrosLector()
        db.add(par)
        db.flush()
    return par


def _inicio_del_dia(ahora: datetime) -> datetime:
    # El dia de X es el de UTC: asi cuenta lo que cobra.
    return ahora.replace(hour=0, minute=0, second=0, microsecond=0)


def x_leidas_hoy(db: Session, ahora: datetime | None = None) -> int:
    desde = _inicio_del_dia(_ahora(ahora).astimezone(timezone.utc))
    return (db.query(func.count(m.NotaLector.id))
            .join(m.FuenteLector, m.FuenteLector.id == m.NotaLector.fuente_id)
            .filter(m.FuenteLector.tipo == "lista_x",
                    m.NotaLector.leida_en >= desde).scalar() or 0)


def _toca(fuente: m.FuenteLector, ahora: datetime) -> bool:
    return (fuente.leida_en is None
            or fuente.leida_en + timedelta(minutes=fuente.cada_min) <= ahora)


def leer_fuente(db: Session, fuente: m.FuenteLector, cliente,
                ahora: datetime | None = None) -> int:
    """Lee una fuente y guarda lo nuevo. Devuelve cuantas notas nuevas.
    Lo que falla queda escrito en la fuente; nunca revienta la vuelta."""
    ahora = _ahora(ahora)
    try:
        if fuente.tipo == "lista_x":
            if not settings.x_bearer_token:
                raise HTTPException(400, "Falta la llave de X")
            par = parametros(db)
            if x_leidas_hoy(db, ahora) >= par.tope_x_dia:
                raise HTTPException(400, "Llegó al tope de X de hoy")
            lista = id_de_lista(fuente.direccion)
            if not lista:
                raise HTTPException(400, "La dirección no es de una lista")
            notas = leer_lista_x(cliente, lista)
        else:
            r = cliente.get(direccion_de(fuente))
            if r.status_code >= 400:
                raise HTTPException(400, f"La página contestó {r.status_code}")
            notas = leer_rss(r.content)
    except HTTPException as e:
        fuente.error, fuente.error_en = str(e.detail)[:300], ahora
        fuente.leida_en = ahora
        return 0
    except Exception as e:                               # noqa: BLE001
        fuente.error = f"No se pudo leer: {type(e).__name__}"[:300]
        fuente.error_en = ahora
        fuente.leida_en = ahora
        return 0
    fuente.error = None
    fuente.leida_en = ahora
    nuevas = 0
    vistas = set()
    for n in notas:
        # La misma nota sale en varias busquedas: se guarda una vez.
        h = huella(n["url"] or n["id"]) if fuente.tipo != "lista_x" \
            else huella(n["id"])
        if h in vistas:
            continue
        vistas.add(h)
        if db.query(m.NotaLector.id).filter_by(huella=h).first():
            continue
        # Lo de hace mas de dos dias ya no es noticia para la Central.
        if n["publicada_en"] and n["publicada_en"] < ahora - timedelta(days=2):
            continue
        estado = ("nueva" if parece_de_seguridad(n["titulo"], n["texto"])
                  else "sin_filtro")
        db.add(m.NotaLector(
            fuente_id=fuente.id, huella=h, url=(n["url"] or "")[:600] or None,
            titulo=n["titulo"][:400], texto=n["texto"], medio=n["medio"],
            publicada_en=n["publicada_en"], leida_en=ahora, estado=estado))
        nuevas += 1
    db.flush()
    return nuevas


# ============================================================ entender

def _municipios_por_region(db: Session, region_id: int) -> list[m.Municipio]:
    return db.query(m.Municipio).filter_by(region_id=region_id).all()


def _municipio(db: Session, region_id: int | None, nombre: str | None
               ) -> m.Municipio | None:
    if not region_id or not nombre:
        return None
    buscado = normalizar(nombre)
    candidatos = _municipios_por_region(db, region_id)
    for x in candidatos:
        if normalizar(x.nombre) == buscado:
            return x
    for x in candidatos:
        n = normalizar(x.nombre)
        if n.startswith(buscado) or buscado.startswith(n):
            return x
    return None


_CENTROS: dict[str, dict] = {}


def centro_municipio(municipio: m.Municipio) -> tuple[float, float] | None:
    """El centro aproximado del municipio, de los contornos del INEGI que
    usa el mapa: basta para «punto aproximado»."""
    from pathlib import Path
    estado = f"{municipio.clave // 1000:02d}"
    if estado not in _CENTROS:
        ruta = Path(__file__).parent / "web" / "geo" / f"mun_{estado}.json"
        centros = {}
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            datos = {"features": []}
        for f in datos["features"]:
            g = f["geometry"]
            anillos = (g["coordinates"] if g["type"] == "Polygon"
                       else [p[0] for p in g["coordinates"]])
            mayor = max(anillos, key=len) if anillos else []
            if mayor:
                centros[f["properties"]["c"]] = (
                    sum(p[1] for p in mayor) / len(mayor),
                    sum(p[0] for p in mayor) / len(mayor))
        _CENTROS[estado] = centros
    return _CENTROS[estado].get(municipio.clave)


def _herramienta(tipos: list[str], estados: list[str]) -> dict:
    return {
        "name": "clasificar",
        "description": "Lo que dice cada nota, en el orden en que llegaron.",
        "input_schema": {
            "type": "object",
            "properties": {"notas": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer",
                          "description": "El numero de la nota"},
                    "es_hecho": {"type": "boolean", "description":
                        "true solo si narra un hecho concreto de seguridad, "
                        "orden publico o fenomeno natural en Mexico, con "
                        "lugar, ocurrido o anunciado para las proximas 48 h. "
                        "Opinion, estadistica, politica, deporte, juicios, "
                        "detenciones de meses atras: false."},
                    "tipo": {"type": "string", "enum": tipos + ["otro"]},
                    "estado": {"type": "string", "enum": estados + ["?"]},
                    "municipio": {"type": "string"},
                    "lugar": {"type": "string", "description":
                        "La referencia precisa: calle, colonia, km, caseta"},
                    "nivel": {"type": "integer", "minimum": 1, "maximum": 4},
                    "razon": {"type": "string", "description":
                        "Por que ese nivel, en una frase corta en espanol"},
                    "titulo": {"type": "string", "description":
                        "Que paso y donde, en una frase de menos de 120 "
                        "caracteres, en espanol, sin adjetivos"},
                    "resumen": {"type": "string", "description":
                        "Dos frases con lo que se sabe"},
                    "ocurrio": {"type": "string", "description":
                        "Cuando paso o empieza, ISO 8601 con zona, o vacio"},
                    "sigue": {"type": "boolean"},
                    "mismo_que": {"type": "string", "description":
                        "Si es el mismo hecho que un hallazgo (H12), un "
                        "evento (CI-0040) u otra nota de este lote (N3), su "
                        "clave; si es nuevo, vacio"},
                },
                "required": ["n", "es_hecho"]}}},
            "required": ["notas"]},
    }


NIVELES = ("1 Informativo: algo que conviene saber, sin riesgo directo. "
           "2 Precaucion: puede afectar un traslado o una zona; evitarla. "
           "3 Alto: riesgo para quien pase por ahi hoy; cambiar ruta o "
           "planes. 4 Critico: riesgo grave e inmediato para las personas; "
           "requiere accion ya.")


def _consulta(db: Session, pais: m.Pais, notas: list[m.NotaLector],
              abiertos: list, eventos: list, descartes: list) -> list[dict]:
    """Una consulta a Claude con un lote de notas. Devuelve lo que dijo
    de cada una."""
    import httpx
    tipos = db.query(m.TipoEvento).filter_by(pais_id=pais.id,
                                              activo=True).all()
    estados = [r.nombre for r in db.query(m.Region).filter_by(
        pais_id=pais.id, activo=True)]
    contexto = [
        "Eres analista de la Central de Inteligencia de Centauro, empresa de "
        "seguridad en Mexico. Clasifica cada nota.",
        "Tipos de evento:\n" + "\n".join(
            f"- {t.nombre}: {t.definicion[:200]}" for t in tipos),
        "Niveles: " + NIVELES,
        "Hallazgos abiertos (para juntar el mismo hecho):\n" + ("\n".join(
            f"H{h.id}: {h.titulo} ({h.region.nombre if h.region else '?'})"
            for h in abiertos) or "ninguno"),
        "Eventos ya en el mapa:\n" + ("\n".join(
            f"{e.folio}: {e.titulo} ({e.region.nombre})" for e in eventos)
            or "ninguno"),
        "La Central descarto hace poco cosas como estas (no las propongas):\n"
        + ("\n".join(f"- {t} [{mo}]" for t, mo in descartes) or "nada"),
    ]
    lote = "\n".join(
        f"N{i + 1} [{n.medio or n.fuente.nombre}"
        f"{', oficial' if n.fuente.oficial else ''}"
        f"{', ' + n.publicada_en.isoformat() if n.publicada_en else ''}]: "
        f"{n.titulo}. {n.texto[:500]}"
        for i, n in enumerate(notas))
    r = httpx.post(
        "https://api.anthropic.com/v1/messages", timeout=90,
        headers={"x-api-key": settings.anthropic_api_key,
                 "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODELO, "max_tokens": 4000,
              "system": "\n\n".join(contexto),
              "tools": [_herramienta([t.nombre for t in tipos], estados)],
              "tool_choice": {"type": "tool", "name": "clasificar"},
              "messages": [{"role": "user", "content": lote}]})
    r.raise_for_status()
    for bloque in r.json().get("content", []):
        if bloque.get("type") == "tool_use":
            return bloque["input"].get("notas", [])
    return []


def _abiertos(db: Session, pais: m.Pais, ahora: datetime) -> list:
    return (db.query(m.HallazgoLector)
            .filter(m.HallazgoLector.pais_id == pais.id,
                    m.HallazgoLector.creado_en >= ahora - timedelta(hours=36))
            .order_by(m.HallazgoLector.id.desc()).limit(60).all())


def _eventos_vivos(db: Session, pais: m.Pais, ahora: datetime) -> list:
    E = m.EstadoEvento
    return (db.query(m.EventoRiesgo)
            .filter(m.EventoRiesgo.pais_id == pais.id,
                    m.EventoRiesgo.estado.in_([E.PROPUESTO, E.POR_CONFIRMAR,
                                               E.PUBLICADO]),
                    m.EventoRiesgo.vigente_hasta > ahora - timedelta(hours=6))
            .order_by(m.EventoRiesgo.id.desc()).limit(40).all())


def _descartes(db: Session) -> list[tuple[str, str]]:
    return [(h.titulo, h.motivo) for h in db.query(m.HallazgoLector)
            .filter_by(estado="descartado")
            .order_by(m.HallazgoLector.revisado_en.desc()).limit(15)]


def _nuevo_hallazgo(db: Session, pais: m.Pais, nota: m.NotaLector,
                    dijo: dict | None, ahora: datetime) -> m.HallazgoLector:
    h = m.HallazgoLector(pais_id=pais.id, titulo=nota.titulo[:300],
                         resumen=nota.texto[:600], creado_en=ahora,
                         actualizado_en=ahora,
                         ocurrio_en=nota.publicada_en or ahora)
    if dijo:
        _aplicar_lo_que_dijo(db, pais, h, dijo, ahora)
    db.add(h)
    db.flush()
    return h


def _aplicar_lo_que_dijo(db: Session, pais: m.Pais, h: m.HallazgoLector,
                         dijo: dict, ahora: datetime) -> None:
    h.con_ia = True
    if dijo.get("titulo"):
        h.titulo = dijo["titulo"][:300]
    if dijo.get("resumen"):
        h.resumen = dijo["resumen"][:1000]
    tipo = (db.query(m.TipoEvento)
            .filter_by(pais_id=pais.id, nombre=dijo.get("tipo")).first())
    h.tipo_id = tipo.id if tipo else None
    region = (db.query(m.Region)
              .filter_by(pais_id=pais.id, nombre=dijo.get("estado")).first())
    h.region_id = region.id if region else None
    mun = _municipio(db, h.region_id, dijo.get("municipio"))
    h.municipio_id = mun.id if mun else None
    h.lugar = (dijo.get("lugar") or "")[:300] or None
    if mun:
        punto = centro_municipio(mun)
        if punto:
            h.lat, h.lon = round(punto[0], 6), round(punto[1], 6)
    if dijo.get("nivel") in (1, 2, 3, 4):
        h.nivel = dijo["nivel"]
    h.razon = (dijo.get("razon") or "")[:300] or None
    ocurrio = _fecha(dijo.get("ocurrio")) if dijo.get("ocurrio") else None
    if ocurrio and ahora - timedelta(days=3) < ocurrio < ahora + timedelta(
            days=3):
        h.ocurrio_en = ocurrio
    h.sigue = dijo.get("sigue")


def entender(db: Session, ahora: datetime | None = None) -> dict:
    """Las notas nuevas que pasaron el filtro: a Claude por lotes, y cada
    una a su hallazgo (nuevo o el del mismo hecho)."""
    ahora = _ahora(ahora)
    pais = db.query(m.Pais).filter_by(codigo="MX").first()
    if not pais:
        return {"notas": 0}
    pendientes = (db.query(m.NotaLector).filter_by(estado="nueva")
                  .order_by(m.NotaLector.id).limit(MAX_POR_VUELTA).all())
    if not pendientes:
        return {"notas": 0, "hallazgos": 0}
    nuevos = 0
    if not settings.anthropic_api_key:
        # Sin Claude: cada nota sola, y las de titulo igual juntas.
        for nota in pendientes:
            igual = (db.query(m.HallazgoLector)
                     .filter(m.HallazgoLector.estado == "por_revisar",
                             m.HallazgoLector.titulo == nota.titulo[:300])
                     .first())
            if not igual:
                igual = _nuevo_hallazgo(db, pais, nota, None, ahora)
                nuevos += 1
            nota.hallazgo_id, nota.estado = igual.id, "analizada"
        db.flush()
        return {"notas": len(pendientes), "hallazgos": nuevos, "con_ia": False}

    for i in range(0, len(pendientes), POR_LOTE):
        lote = pendientes[i:i + POR_LOTE]
        abiertos = _abiertos(db, pais, ahora)
        eventos = _eventos_vivos(db, pais, ahora)
        try:
            respuestas = _consulta(db, pais, lote, abiertos, eventos,
                                   _descartes(db))
        except Exception:                                # noqa: BLE001
            # Claude no contesto: se quedan como nuevas para la que sigue.
            break
        por_n = {r.get("n"): r for r in respuestas}
        del_lote: dict[int, m.HallazgoLector] = {}
        for k, nota in enumerate(lote, start=1):
            dijo = por_n.get(k)
            if not dijo:
                continue
            if not dijo.get("es_hecho"):
                nota.estado = "no_es"
                continue
            destino = None
            mismo = (dijo.get("mismo_que") or "").strip().upper()
            if mismo.startswith("H") and mismo[1:].isdigit():
                destino = db.get(m.HallazgoLector, int(mismo[1:]))
            elif mismo.startswith("CI-"):
                evento = (db.query(m.EventoRiesgo)
                          .filter_by(folio=mismo).first())
                if evento:
                    destino = (db.query(m.HallazgoLector)
                               .filter_by(evento_id=evento.id,
                                          estado="por_revisar").first())
                    if not destino:
                        destino = _nuevo_hallazgo(db, pais, nota, dijo, ahora)
                        destino.evento_id = evento.id
                        nuevos += 1
            elif mismo.startswith("N") and mismo[1:].isdigit():
                destino = del_lote.get(int(mismo[1:]))
            if destino is None:
                destino = _nuevo_hallazgo(db, pais, nota, dijo, ahora)
                nuevos += 1
            elif destino.estado == "por_revisar":
                destino.actualizado_en = ahora
                # Una oficial manda: su version del titulo y del nivel.
                if nota.fuente.oficial:
                    _aplicar_lo_que_dijo(db, pais, destino, dijo, ahora)
            del_lote[k] = destino
            nota.hallazgo_id, nota.estado = destino.id, "analizada"
        db.flush()
    return {"notas": len(pendientes), "hallazgos": nuevos, "con_ia": True}


def vuelta(db: Session, cliente=None, ahora: datetime | None = None) -> dict:
    """Lo que corre la tarea: leer lo que toca y entender lo nuevo."""
    import httpx
    ahora = _ahora(ahora)
    par = parametros(db)
    if par.pausado:
        return {"pausado": True}
    propio = cliente is None
    cliente = cliente or httpx.Client(
        timeout=30, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Centauro Connect; lector)"})
    leidas = 0
    try:
        for f in db.query(m.FuenteLector).filter_by(activa=True):
            if _toca(f, ahora):
                leidas += leer_fuente(db, f, cliente, ahora)
                db.commit()
    finally:
        if propio:
            cliente.close()
    salida = entender(db, ahora)
    db.commit()
    salida["leidas"] = leidas
    return salida


def podar(db: Session, ahora: datetime | None = None) -> int:
    """Las notas que no llegaron a ningun hallazgo se borran a las dos
    semanas. Su huella ya no hace falta: a esa edad no salen en el RSS."""
    limite = _ahora(ahora) - timedelta(days=GUARDAR_DIAS)
    return (db.query(m.NotaLector)
            .filter(m.NotaLector.hallazgo_id.is_(None),
                    m.NotaLector.leida_en < limite)
            .delete(synchronize_session=False))


# ============================================================ lo que se ve

def _local(instante: datetime | None, pais: m.Pais) -> str | None:
    from app import reloj
    if instante is None:
        return None
    return instante.astimezone(reloj.zona(pais.zona_horaria)).isoformat()


def vista_nota(n: m.NotaLector, pais: m.Pais) -> dict:
    return {"id": n.id, "titulo": n.titulo, "url": n.url,
            "medio": n.medio or n.fuente.nombre, "oficial": n.fuente.oficial,
            "publicada_en": _local(n.publicada_en or n.leida_en, pais)}


def vista_hallazgo(db: Session, h: m.HallazgoLector,
                   completa: bool = False) -> dict:
    pais = db.get(m.Pais, h.pais_id)
    notas = sorted(h.notas, key=lambda n: n.publicada_en or n.leida_en)
    primera = notas[0] if notas else None
    salida = {
        "id": h.id, "estado": h.estado, "titulo": h.titulo,
        "resumen": h.resumen, "con_ia": h.con_ia,
        "tipo_id": h.tipo_id, "tipo": h.tipo.nombre if h.tipo else None,
        "region_id": h.region_id,
        "region": h.region.nombre if h.region else None,
        "municipio": h.municipio.nombre if h.municipio else None,
        "lugar": h.lugar, "nivel": h.nivel, "razon": h.razon,
        "lat": float(h.lat) if h.lat is not None else None,
        "lon": float(h.lon) if h.lon is not None else None,
        "ocurrio_en": _local(h.ocurrio_en, pais), "sigue": h.sigue,
        "creado_en": _local(h.creado_en, pais),
        "actualizado_en": _local(h.actualizado_en, pais),
        "notas_n": len(notas),
        "primera": vista_nota(primera, pais) if primera else None,
        "evento_id": h.evento_id,
        "evento_folio": (db.get(m.EventoRiesgo, h.evento_id).folio
                         if h.evento_id else None),
        "motivo": h.motivo,
    }
    if completa:
        salida["notas"] = [vista_nota(n, pais) for n in notas]
        salida["cerca"] = cerca(db, h)
        salida["texto"] = primera.texto if primera else ""
    return salida


def cerca(db: Session, h: m.HallazgoLector) -> dict:
    """A quien le importa: los clientes que siguen ese estado y el
    servicio de hoy mas cercano al punto."""
    from app import riesgo_campo
    clientes = 0
    if h.region_id:
        clientes = (db.query(func.count(func.distinct(
            m.ZonaCliente.cliente_central_id)))
            .join(m.ClienteCentral,
                  m.ClienteCentral.id == m.ZonaCliente.cliente_central_id)
            .filter(m.ZonaCliente.region_id == h.region_id,
                    m.ClienteCentral.activo.is_(True)).scalar() or 0)
    servicio = None
    if h.lat is not None:
        pais = db.get(m.Pais, h.pais_id)
        jornadas = riesgo_campo._jornadas_del_dia(
            db, SimpleNamespace(pais=pais), _ahora())
        mejor = None
        for j in jornadas:
            km = riesgo_campo.distancia_km(float(h.lat), float(h.lon),
                                           float(j.origen_lat),
                                           float(j.origen_lon))
            if km <= riesgo_campo.RADIO_KM and (mejor is None
                                                or km < mejor[0]):
                mejor = (km, j)
        if mejor:
            j = mejor[1]
            servicio = {"km": round(mejor[0]),
                        "folio": (j.equipo.servicio.folio
                                  if j.equipo else None)}
    return {"clientes": clientes, "servicio": servicio}


def por_revisar(db: Session, pais: m.Pais, ahora: datetime | None = None
                ) -> dict:
    ahora = _ahora(ahora)
    lista = (db.query(m.HallazgoLector)
             .filter_by(pais_id=pais.id, estado="por_revisar").all())
    # Lo mas grave primero, y en cada nivel lo mas reciente.
    lista.sort(key=lambda h: (-(h.nivel or 0),
                              -(h.actualizado_en or h.creado_en).timestamp()))
    from app import reloj
    hoy = ahora.astimezone(reloj.zona(pais.zona_horaria)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    leidas = (db.query(func.count(m.NotaLector.id))
              .filter(m.NotaLector.leida_en >= hoy).scalar() or 0)
    filtradas = (db.query(func.count(m.NotaLector.id))
                 .filter(m.NotaLector.leida_en >= hoy,
                         m.NotaLector.estado.in_(["nueva", "analizada",
                                                  "no_es"])).scalar() or 0)
    def contar(estado):
        return (db.query(func.count(m.HallazgoLector.id))
                .filter(m.HallazgoLector.pais_id == pais.id,
                        m.HallazgoLector.estado == estado,
                        m.HallazgoLector.revisado_en >= hoy).scalar() or 0)
    return {
        "hallazgos": [vista_hallazgo(db, h) for h in lista],
        "hoy": {"leidas": leidas, "parecian": filtradas,
                "fuentes": db.query(func.count(m.FuenteLector.id))
                .filter_by(activa=True).scalar() or 0,
                "eventos": contar("evento") + contar("sumado"),
                "descartados": contar("descartado")},
        "llaves": {"ia": bool(settings.anthropic_api_key),
                   "x": bool(settings.x_bearer_token)},
        "pausado": parametros(db).pausado,
    }


# ============================================================ lo que hace el analista

def hallazgo_de(db: Session, hallazgo_id: int) -> m.HallazgoLector:
    h = db.get(m.HallazgoLector, hallazgo_id)
    if not h:
        raise HTTPException(404, "No existe ese hallazgo")
    return h


def _sin_revisar(h: m.HallazgoLector) -> None:
    if h.estado != "por_revisar":
        raise HTTPException(409, "Ese hallazgo ya se revisó")


def _cerrar(h: m.HallazgoLector, usuario: m.Usuario, estado: str) -> None:
    h.estado = estado
    h.revisado_por_id = usuario.id
    h.revisado_en = _ahora()


def _fuentes_al_evento(db: Session, usuario: m.Usuario,
                       evento: m.EventoRiesgo, h: m.HallazgoLector) -> None:
    from app import riesgo
    ya = {f.url for f in evento.fuentes if f.url}
    for n in h.notas:
        if n.url and n.url in ya:
            continue
        riesgo.agregar_fuente(
            db, usuario, evento,
            f"{n.medio or n.fuente.nombre}: {n.titulo}"[:300], n.url,
            n.fuente.oficial)


def crear_evento(db: Session, usuario: m.Usuario, h: m.HallazgoLector,
                 cambios: dict) -> m.EventoRiesgo:
    """El evento propuesto con lo que entendio Connect (y lo que el
    analista corrigio), y las notas como sus fuentes."""
    from app import riesgo
    _sin_revisar(h)
    datos = {
        "pais_id": h.pais_id,
        "region_id": cambios.get("region_id") or h.region_id,
        "tipo_id": cambios.get("tipo_id") or h.tipo_id,
        "nivel": cambios.get("nivel") or h.nivel,
        "titulo": (cambios.get("titulo") or h.titulo)[:160],
        "municipio": h.municipio.nombre if h.municipio else None,
        "lugar": h.lugar,
        "ocurrio_en": h.ocurrio_en or _ahora(),
    }
    if h.lat is not None:
        datos["lat"], datos["lon"] = float(h.lat), float(h.lon)
        # El punto es el centro del municipio: el circulo lo cubre.
        datos["radio_m"] = 8000
    falta = [k for k in ("region_id", "tipo_id", "nivel") if not datos[k]]
    if falta:
        raise HTTPException(400, {
            "mensaje": "Faltan datos para crear el evento",
            "que_hacer": "Elige el tipo, el estado y el nivel."})
    tipo = db.get(m.TipoEvento, datos["tipo_id"])
    datos["vigente_hasta"] = max(datos["ocurrio_en"], _ahora()) + \
        timedelta(hours=VIGENCIA_HORAS.get(tipo.nombre, 12) if tipo else 12)
    evento = riesgo.crear(db, usuario, datos, origen="lector")
    _fuentes_al_evento(db, usuario, evento, h)
    _cerrar(h, usuario, "evento")
    h.evento_id = evento.id
    db.flush()
    return evento


# La vigencia con la que nace el evento, por tipo. El analista la ajusta.
VIGENCIA_HORAS = {"Bloqueo carretero": 8, "Manifestación": 6,
                  "Fenómeno natural": 24}


def sumar(db: Session, usuario: m.Usuario, h: m.HallazgoLector,
          evento_id: int) -> m.EventoRiesgo:
    from app import riesgo
    _sin_revisar(h)
    evento = riesgo.evento_de(db, evento_id)
    _fuentes_al_evento(db, usuario, evento, h)
    _cerrar(h, usuario, "sumado")
    h.evento_id = evento.id
    db.flush()
    return evento


def descartar(db: Session, usuario: m.Usuario, h: m.HallazgoLector,
              motivo: str) -> None:
    _sin_revisar(h)
    if motivo not in MOTIVOS:
        raise HTTPException(400, "Di por qué se descarta")
    _cerrar(h, usuario, "descartado")
    h.motivo = motivo
    db.flush()


# ============================================================ las fuentes

def vista_fuente(db: Session, f: m.FuenteLector, hoy: datetime) -> dict:
    regiones = json.loads(f.regiones or "[]")
    nombres = [r.nombre for r in db.query(m.Region)
               .filter(m.Region.id.in_(regiones))] if regiones else []
    leidas = (db.query(func.count(m.NotaLector.id))
              .filter(m.NotaLector.fuente_id == f.id,
                      m.NotaLector.leida_en >= hoy).scalar() or 0)
    propuso = (db.query(func.count(func.distinct(m.NotaLector.hallazgo_id)))
               .filter(m.NotaLector.fuente_id == f.id,
                       m.NotaLector.leida_en >= hoy,
                       m.NotaLector.hallazgo_id.isnot(None)).scalar() or 0)
    return {"id": f.id, "tipo": f.tipo, "nombre": f.nombre,
            "direccion": f.direccion, "regiones": nombres,
            "oficial": f.oficial, "cada_min": f.cada_min, "activa": f.activa,
            "leida_en": f.leida_en.isoformat() if f.leida_en else None,
            "error": f.error, "leidas_hoy": leidas, "propuso_hoy": propuso}


def fuentes(db: Session, pais: m.Pais, ahora: datetime | None = None) -> dict:
    from app import reloj
    ahora = _ahora(ahora)
    hoy = ahora.astimezone(reloj.zona(pais.zona_horaria)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    par = parametros(db)
    # Primero lo que mas dice --la lista de X, los medios, las busquedas
    # de todo el pais-- y al final las de cada estado; las apagadas abajo.
    orden = {"lista_x": 0, "medio": 1, "busqueda": 2}
    lista = sorted(db.query(m.FuenteLector).all(), key=lambda f: (
        not f.activa, orden.get(f.tipo, 9),
        f.tipo == "busqueda" and f.regiones not in ("[]", "", None),
        f.nombre))
    return {"fuentes": [vista_fuente(db, f, hoy) for f in lista],
            "tope_x_dia": par.tope_x_dia, "x_hoy": x_leidas_hoy(db, ahora),
            "pausado": par.pausado,
            "llaves": {"ia": bool(settings.anthropic_api_key),
                       "x": bool(settings.x_bearer_token)}}


def agregar_fuente(db: Session, usuario: m.Usuario, pais: m.Pais,
                   datos: dict) -> m.FuenteLector:
    tipo = datos.get("tipo")
    if tipo not in TIPOS:
        raise HTTPException(400, "El tipo es medio, búsqueda o lista de X")
    direccion = (datos.get("direccion") or "").strip()
    if tipo == "medio" and not direccion.lower().startswith(("http://",
                                                            "https://")):
        raise HTTPException(400, "Un medio se agrega con la dirección de su "
                                 "RSS (empieza con https://)")
    if tipo == "lista_x" and not id_de_lista(direccion):
        raise HTTPException(400, {
            "mensaje": "Esa no es la dirección de una lista de X",
            "que_hacer": "Abre la lista en X y copia su dirección: "
                         "https://x.com/i/lists/…"})
    if tipo == "busqueda" and len(direccion) < 3:
        raise HTTPException(400, "Escribe las palabras a buscar")
    nombre = (datos.get("nombre") or "").strip() or direccion[:120]
    regiones = []
    for texto in datos.get("regiones") or []:
        buscado = normalizar(texto)
        region = next((r for r in db.query(m.Region)
                       .filter_by(pais_id=pais.id)
                       if normalizar(r.nombre) == buscado), None)
        if not region:
            raise HTTPException(400, f"No conozco el estado «{texto}»")
        regiones.append(region.id)
    cada = int(datos.get("cada_min") or (60 if tipo == "busqueda" else 15))
    if cada not in CADA_MIN:
        raise HTTPException(400, "Cada 5, 10, 15, 30, 60 o 120 minutos")
    f = m.FuenteLector(tipo=tipo, nombre=nombre[:120],
                       direccion=direccion[:600],
                       regiones=json.dumps(regiones),
                       oficial=bool(datos.get("oficial")), cada_min=cada,
                       creada_por_id=usuario.id)
    db.add(f)
    db.flush()
    return f

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

import logging

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.fuentes_riesgo import normalizar

log = logging.getLogger(__name__)

TIPOS = ("medio", "busqueda", "lista_x")
MOTIVOS = ("no_es_seguridad", "ya_paso", "repetida", "fuera_de_mexico",
           "sin_importancia")
CADA_MIN = (5, 10, 15, 30, 60, 120)
GUARDAR_DIAS = 14              # las notas sin hallazgo se borran despues
POR_LOTE = 12                  # notas por consulta a Claude
MAX_POR_VUELTA = 120           # notas que se le pasan a Claude por vuelta
X_POR_LLAMADA = 50
MAXIMO_RSS = 5 * 1024 * 1024    # lo mas que pesa un RSS de verdad
VIGENCIA_DEL_HALLAZGO = 48      # horas que espera revision antes de vencer
EN_LA_PANTALLA = 200
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
    r"herid[oa]s?", r"lesionad[oa]s?", r"muert[oa]s?",
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

def _fecha(valor, zona=None) -> datetime | None:
    """Una fecha de RSS (RFC 822) o ISO. Sin zona se entiende en la del
    pais (lo que diga Claude) o en UTC (lo que diga un feed)."""
    if not valor or not isinstance(valor, str):
        return None
    try:
        d = parsedate_to_datetime(valor)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=zona or timezone.utc)
    return d


def _enlace(url: str | None, base: str | None) -> str | None:
    """Solo enlaces http(s), completos: un «javascript:» o una ruta suelta
    no llegan a la pantalla ni a las fuentes del evento."""
    from urllib.parse import urljoin, urlparse
    if not url:
        return None
    completo = urljoin(base or "", url.strip())
    return completo[:600] if urlparse(completo).scheme in ("http",
                                                            "https") else None


def leer_rss(contenido: bytes, base: str | None = None) -> list[dict]:
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
        def de(*etiquetas):
            for etiqueta in etiquetas:
                for nombre in (etiqueta, atom + etiqueta):
                    nodo = it.find(nombre)
                    if nodo is not None:
                        return nodo
            return None
        nodo = de("title")
        titulo = _limpio(nodo.text if nodo is not None else "", 400)
        enlace = de("link")
        url = None
        if enlace is not None:
            url = (enlace.text or enlace.get("href") or "").strip() or None
        url = _enlace(url, base)
        guid = de("guid", "id")
        medio_n = it.find("source")
        medio = (medio_n.text.strip()[:120]
                 if medio_n is not None and medio_n.text else None)
        if medio and titulo.endswith(f" - {medio}"):
            titulo = titulo[: -len(medio) - 3].strip()
        texto = de("description", "summary")
        fecha = de("pubDate", "published", "updated")
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
    datos = r.json() or {}
    gente = {u.get("id"): u for u in
             (datos.get("includes") or {}).get("users", []) or []}
    salida = []
    for p in datos.get("data") or []:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        u = gente.get(p.get("author_id"), {})
        usuario = re.sub(r"[^A-Za-z0-9_]", "", u.get("username") or "")
        salida.append({
            "id": f"x:{p['id']}", "titulo": _limpio(p.get("text"), 400),
            "texto": "", "medio": (f"@{usuario}" if usuario else "X")[:120],
            "url": (f"https://x.com/{usuario}/status/{p['id']}"
                    if usuario else None),
            "publicada_en": _fecha(p.get("created_at")),
        })
    return salida


def parametros(db: Session) -> m.ParametrosLector:
    par = db.query(m.ParametrosLector).order_by(m.ParametrosLector.id).first()
    if not par:
        par = m.ParametrosLector()
        db.add(par)
        db.flush()
    return par


def _dia_de_x(ahora: datetime):
    # El dia de X es el de UTC: asi cuenta lo que cobra.
    return ahora.astimezone(timezone.utc).date()


def x_leidas_hoy(db: Session, ahora: datetime | None = None) -> int:
    """Las publicaciones distintas que X entrego hoy (su dia, el de UTC):
    lo que cobra. Es lo que se compara contra el tope."""
    par = parametros(db)
    return par.x_leidas if par.x_dia == _dia_de_x(_ahora(ahora)) else 0


def _cobradas_hoy(ids: list[str], ahora: datetime) -> int:
    """De lo que X acaba de entregar, cuanto cobra: X no cobra dos veces
    la misma publicacion en su dia (UTC), y una lista no deja pedir solo
    lo nuevo, asi que cada vuelta trae repetidas (seccion 142). Las ya
    vistas hoy se apuntan en Redis; sin Redis se cuentan todas, que es
    lo seguro (de mas, nunca de menos)."""
    from app import intentos
    if not ids:
        return 0
    r = intentos._redis()
    if not r:
        return len(ids)
    llave = f"lector:x:{_dia_de_x(ahora).isoformat()}"
    try:
        nuevas = r.sadd(llave, *ids)
        r.expire(llave, 2 * 86400)
        return int(nuevas)
    except Exception:                                    # noqa: BLE001
        return len(ids)


def _contar_x(db: Session, cuantas: int, ahora: datetime) -> None:
    par = parametros(db)
    dia = _dia_de_x(ahora)
    if par.x_dia != dia:
        par.x_dia, par.x_leidas = dia, 0
    par.x_leidas += cuantas


def _toca(fuente: m.FuenteLector, ahora: datetime) -> bool:
    # Un minuto de holgura: la tarea no cae siempre en el mismo segundo,
    # y sin esto una fuente de cada 5 minutos se leia cada 10.
    return (fuente.leida_en is None
            or fuente.leida_en + timedelta(minutes=fuente.cada_min - 1)
            <= ahora)


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
            if x_leidas_hoy(db, ahora) + X_POR_LLAMADA > par.tope_x_dia:
                raise HTTPException(400, "Llegó al tope de X de hoy")
            lista = id_de_lista(fuente.direccion)
            if not lista:
                raise HTTPException(400, "La dirección no es de una lista")
            notas = leer_lista_x(cliente, lista)
            _contar_x(db, _cobradas_hoy(
                sorted({n["id"] for n in notas}), ahora), ahora)
        else:
            direccion = direccion_de(fuente)
            r = cliente.get(direccion)
            if r.status_code >= 400:
                raise HTTPException(400, f"La página contestó {r.status_code}")
            if len(r.content) > MAXIMO_RSS:
                raise HTTPException(400, "La página pesa demasiado para "
                                         "ser un RSS")
            notas = leer_rss(r.content, direccion)
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
    porhuella = {}
    for n in notas:
        # La misma nota sale en varias busquedas: se guarda una vez.
        h = huella(n["id"] if fuente.tipo == "lista_x"
                   else (n["url"] or n["id"]))
        porhuella.setdefault(h, n)
    if not porhuella:
        return 0
    ya = {x for (x,) in db.query(m.NotaLector.huella)
          .filter(m.NotaLector.huella.in_(list(porhuella)))}
    nuevas = 0
    for h, n in porhuella.items():
        if h in ya:
            continue
        # Lo de hace mas de dos dias ya no es noticia para la Central.
        if n["publicada_en"] and n["publicada_en"] < ahora - timedelta(days=2):
            continue
        estado = ("nueva" if parece_de_seguridad(n["titulo"], n["texto"])
                  else "sin_filtro")
        db.add(m.NotaLector(
            fuente_id=fuente.id, huella=h, url=n["url"],
            titulo=n["titulo"][:400], texto=n["texto"],
            medio=(n["medio"] or None) and n["medio"][:120],
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
                    "texto_cliente": {"type": "string", "description":
                        "Lo que leera el cliente de Centauro: que paso, "
                        "donde y que hacer (evitar la zona, usar otra ruta), "
                        "en una o dos frases, en espanol neutro. Sin nombrar "
                        "medios ni cuentas, sin adjetivos, sin especular, "
                        "sin cifras que la nota no de"},
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
           "requiere accion ya. Un ataque armado, una ejecucion, un "
           "enfrentamiento, un secuestro o un explosivo nunca es 1: con "
           "heridos o muertos es al menos 2, y 3 si puede seguir.")

# Seccion 146 (Salvador, 3 oct): lo violento nunca queda como informativo
# aunque Claude lo diga --en su primer dia publico solo un «hombre muere
# en ataque armado» como nivel 1--, y una detencion nunca sale sola: es
# noticia, no riesgo para quien pasa.
NIVEL_MINIMO = {"Ataque armado (arma de fuego)": 2,
                "Ataque armado (arma blanca)": 2, "Ejecución": 2,
                "Enfrentamiento armado": 2, "Persecución armada": 2,
                "Secuestro": 2, "Artefacto explosivo": 2}
NUNCA_SOLO = {"Detención"}


def _consulta(db: Session, pais: m.Pais, notas: list[m.NotaLector],
              abiertos: list, eventos: list, descartes: list) -> list[dict]:
    """Una consulta a Claude con un lote de notas. Devuelve lo que dijo
    de cada una, ya revisado que tenga forma de lista de objetos."""
    import httpx
    tipos = db.query(m.TipoEvento).filter_by(pais_id=pais.id,
                                              activo=True).all()
    estados = [r.nombre for r in db.query(m.Region).filter_by(
        pais_id=pais.id, activo=True)]

    def etiqueta(h):
        if h.estado == "por_revisar":
            return ""
        if h.evento_id:
            return " (ya es evento)"
        return " (la Central lo descartó)"
    contexto = [
        "Eres analista de la Central de Inteligencia de Centauro, empresa de "
        "seguridad en Mexico. Clasifica cada nota.",
        "Tipos de evento:\n" + "\n".join(
            f"- {t.nombre}: {t.definicion[:200]}" for t in tipos),
        "Niveles: " + NIVELES,
        "Hallazgos recientes (para juntar el mismo hecho):\n" + ("\n".join(
            f"H{h.id}: {h.titulo} ({h.region.nombre if h.region else '?'})"
            f"{etiqueta(h)}" for h in abiertos) or "ninguno"),
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
        "https://api.anthropic.com/v1/messages", timeout=60,
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
            notas_dichas = (bloque.get("input") or {}).get("notas")
            if isinstance(notas_dichas, str):
                try:
                    notas_dichas = json.loads(notas_dichas)
                except ValueError:
                    notas_dichas = []
            if not isinstance(notas_dichas, list):
                return []
            return [x for x in notas_dichas if isinstance(x, dict)]
    return []


def _abiertos(db: Session, pais: m.Pais, ahora: datetime) -> list:
    """Los hallazgos de las ultimas 36 horas, tambien los ya revisados:
    asi una nota nueva de un hecho que ya es evento va a ese evento, y la
    de uno descartado no vuelve a salir."""
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


def _texto(dijo: dict, clave: str) -> str:
    valor = dijo.get(clave)
    return valor.strip() if isinstance(valor, str) else ""


def _aplicar_lo_que_dijo(db: Session, pais: m.Pais, h: m.HallazgoLector,
                         dijo: dict, ahora: datetime) -> None:
    """Pone lo que dijo Claude. Solo lo que dijo: lo que no trae no borra
    lo que ya se sabia."""
    from app import reloj
    h.con_ia = True
    if _texto(dijo, "titulo"):
        h.titulo = _texto(dijo, "titulo")[:300]
    if _texto(dijo, "resumen"):
        h.resumen = _texto(dijo, "resumen")[:1000]
    if len(_texto(dijo, "texto_cliente")) >= 20:
        h.texto_cliente = _texto(dijo, "texto_cliente")[:600]
    tipo = (db.query(m.TipoEvento)
            .filter_by(pais_id=pais.id, nombre=_texto(dijo, "tipo")).first())
    if tipo:
        h.tipo_id = tipo.id
    region = (db.query(m.Region)
              .filter_by(pais_id=pais.id, nombre=_texto(dijo, "estado"))
              .first())
    if region:
        h.region_id = region.id
    mun = _municipio(db, h.region_id, _texto(dijo, "municipio"))
    if mun:
        h.municipio_id = mun.id
        punto = centro_municipio(mun)
        if punto:
            h.lat, h.lon = round(punto[0], 6), round(punto[1], 6)
    if _texto(dijo, "lugar"):
        h.lugar = _texto(dijo, "lugar")[:300]
    if dijo.get("nivel") in (1, 2, 3, 4):
        h.nivel = dijo["nivel"]
    if h.tipo_id and h.nivel:
        minimo = NIVEL_MINIMO.get(db.get(m.TipoEvento, h.tipo_id).nombre)
        if minimo and h.nivel < minimo:
            h.nivel = minimo
    if _texto(dijo, "razon"):
        h.razon = _texto(dijo, "razon")[:300]
    ocurrio = _fecha(_texto(dijo, "ocurrio"),
                     reloj.zona(pais.zona_horaria))
    if ocurrio and ahora - timedelta(days=3) < ocurrio < ahora + timedelta(
            days=3):
        h.ocurrio_en = ocurrio
    if isinstance(dijo.get("sigue"), bool):
        h.sigue = dijo["sigue"]


def _numero(valor) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _destino(db: Session, pais: m.Pais, nota: m.NotaLector, dijo: dict,
             del_lote: dict, ahora: datetime) -> tuple:
    """A que hallazgo va la nota: (hallazgo, es_nuevo)."""
    mismo = _texto(dijo, "mismo_que").upper()
    destino = None
    if mismo.startswith("H"):
        num = _numero(mismo[1:])
        if num and num < 2 ** 31:
            destino = db.get(m.HallazgoLector, num)
    elif mismo.startswith("CI-"):
        evento = db.query(m.EventoRiesgo).filter_by(folio=mismo).first()
        if evento:
            return _del_evento(db, pais, nota, dijo, evento, ahora)
    elif mismo.startswith("N"):
        destino = del_lote.get(_numero(mismo[1:]))
    if destino is not None and destino.estado != "por_revisar" \
            and destino.evento_id:
        # Ya es un evento: la nota nueva se le propone a ese evento.
        evento = db.get(m.EventoRiesgo, destino.evento_id)
        if evento:
            return _del_evento(db, pais, nota, dijo, evento, ahora)
    if destino is None:
        return _nuevo_hallazgo(db, pais, nota, dijo, ahora), True
    return destino, False


def _del_evento(db, pais, nota, dijo, evento, ahora) -> tuple:
    """El hallazgo por revisar de un evento que ya existe: lo que llegue de
    ese hecho se le propone para sumarlo."""
    abierto = (db.query(m.HallazgoLector)
               .filter_by(evento_id=evento.id, estado="por_revisar").first())
    if abierto:
        return abierto, False
    nuevo = _nuevo_hallazgo(db, pais, nota, dijo, ahora)
    nuevo.evento_id = evento.id
    return nuevo, True


FALLAS_DE_CLAUDE = ("llave", "espacio", "saldo", "saturado", "red", "otro")


def falla_de_claude(e: Exception) -> tuple[str, str]:
    """Por que Claude no contesto, en una palabra que la consola sabe
    decir, y lo que dijo tal cual (recortado). Nunca lleva la llave."""
    import httpx
    if isinstance(e, httpx.HTTPStatusError):
        codigo = e.response.status_code
        try:
            error = e.response.json().get("error") or {}
        except ValueError:
            error = {}
        dijo = str(error.get("message") or e.response.text or "")[:300]
        texto = dijo.lower()
        if codigo in (401, 403) or error.get("type") in (
                "authentication_error", "permission_error"):
            return "llave", dijo
        if "workspace" in texto:
            return "espacio", dijo
        if "credit balance" in texto or "billing" in texto:
            return "saldo", dijo
        if codigo in (429, 500, 502, 503, 529) or error.get("type") in (
                "rate_limit_error", "overloaded_error", "api_error"):
            return "saturado", dijo
        return "otro", f"{codigo} · {dijo}"[:300]
    if isinstance(e, httpx.TransportError):
        return "red", type(e).__name__
    return "otro", type(e).__name__


def _anotar_falla(db: Session, falla: tuple[str, str] | None,
                  ahora: datetime) -> None:
    """Deja dicho (o borra) que Claude no contesto. Quien ya estaba
    fallando conserva desde cuando."""
    par = parametros(db)
    if falla is None:
        par.ia_falla = par.ia_detalle = par.ia_falla_en = None
        return
    if par.ia_falla is None:
        par.ia_falla_en = ahora
    par.ia_falla, par.ia_detalle = falla


def entender(db: Session, ahora: datetime | None = None) -> dict:
    """Las notas nuevas que pasaron el filtro: a Claude por lotes, y cada
    una a su hallazgo (nuevo o el del mismo hecho). Cada lote se guarda al
    terminar: si uno falla, lo pagado antes no se pierde."""
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
        _anotar_falla(db, None, ahora)
        db.commit()
        return {"notas": len(pendientes), "hallazgos": nuevos, "con_ia": False}

    for i in range(0, len(pendientes), POR_LOTE):
        lote = pendientes[i:i + POR_LOTE]
        try:
            respuestas = _consulta(db, pais, lote, _abiertos(db, pais, ahora),
                                   _eventos_vivos(db, pais, ahora),
                                   _descartes(db))
        except Exception as e:                           # noqa: BLE001
            # Claude no contesto: se quedan como nuevas para la que sigue,
            # y la consola lo dice (antes se quedaba callada).
            db.rollback()
            falla = falla_de_claude(e)
            log.warning("El lector no pudo consultar a Claude: %s (%s)",
                        falla[0], falla[1])
            _anotar_falla(db, falla, ahora)
            db.commit()
            return {"notas": i, "hallazgos": nuevos, "con_ia": True,
                    "falla": falla[0]}
        _anotar_falla(db, None, ahora)
        por_n = {}
        for r in respuestas:
            n = _numero(r.get("n"))
            if n is not None:
                por_n[n] = r
        del_lote: dict[int, m.HallazgoLector] = {}
        for k, nota in enumerate(lote, start=1):
            dijo = por_n.get(k)
            if not dijo:
                # Claude no la contesto (se corto o la salto): no se le
                # vuelve a pagar; queda como error y no sale.
                nota.estado = "error"
                continue
            if dijo.get("es_hecho") is not True:
                nota.estado = "no_es"
                continue
            try:
                with db.begin_nested():
                    destino, es_nuevo = _destino(db, pais, nota, dijo,
                                                 del_lote, ahora)
                    nuevos += int(es_nuevo)
                    if not es_nuevo and destino.estado == "por_revisar":
                        destino.actualizado_en = ahora
                        # Una oficial manda: su version de lo que paso.
                        if nota.fuente.oficial:
                            _aplicar_lo_que_dijo(db, pais, destino, dijo,
                                                 ahora)
                    del_lote[k] = destino
                    nota.hallazgo_id, nota.estado = destino.id, "analizada"
            except Exception:                            # noqa: BLE001
                nota.estado = "error"
        db.commit()
    return {"notas": len(pendientes), "hallazgos": nuevos, "con_ia": True}


def cliente_seguro():
    """El cliente con el que se leen las fuentes: nunca va a una direccion
    interna (ni el primer pedido ni una redireccion), y no baja mas de lo
    que pesa un RSS."""
    import httpx

    def revisar(pedido):
        _direccion_publica(str(pedido.url))
    return httpx.Client(
        timeout=20, follow_redirects=True, max_redirects=3,
        event_hooks={"request": [revisar]},
        headers={"User-Agent": "Mozilla/5.0 (Centauro Connect; lector)"})


def _direccion_publica(url: str) -> None:
    """Rechaza lo que apunta adentro: localhost, la red privada, la de la
    nube (169.254...), Redis o la base por su nombre."""
    import ipaddress
    import socket
    from urllib.parse import urlparse
    partes = urlparse(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise HTTPException(400, "La dirección empieza con https://")
    try:
        direcciones = {x[4][0] for x in socket.getaddrinfo(
            partes.hostname, partes.port or 443)}
    except OSError:
        raise HTTPException(400, "No existe esa dirección")
    for d in direcciones:
        ip = ipaddress.ip_address(d.split("%")[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise HTTPException(400, "Esa dirección no es pública")


def vuelta(db: Session, cliente=None, ahora: datetime | None = None) -> dict:
    """Lo que corre la tarea: leer lo que toca y entender lo nuevo."""
    ahora = _ahora(ahora)
    par = parametros(db)
    db.commit()
    if par.pausado:
        return {"pausado": True}
    propio = cliente is None
    cliente = cliente or cliente_seguro()
    leidas = 0
    try:
        for fid in [f.id for f in db.query(m.FuenteLector)
                    .filter_by(activa=True)]:
            f = db.get(m.FuenteLector, fid)
            if not _toca(f, ahora):
                continue
            try:
                leidas += leer_fuente(db, f, cliente, ahora)
                db.commit()
            except Exception as e:                       # noqa: BLE001
                # Una fuente rara no frena a las demas.
                db.rollback()
                f = db.get(m.FuenteLector, fid)
                f.error = f"No se pudo guardar: {type(e).__name__}"[:300]
                f.error_en = f.leida_en = ahora
                db.commit()
    finally:
        if propio:
            cliente.close()
    salida = entender(db, ahora)
    db.commit()
    salida["leidas"] = leidas
    salida["publico_solo"] = publicar_solos(db, ahora)
    db.commit()
    return salida


def podar(db: Session, ahora: datetime | None = None) -> int:
    """Las notas que no llegaron a ningun hallazgo se borran a las dos
    semanas (su huella ya no hace falta: a esa edad no salen en el RSS), y
    lo que nadie reviso en dos dias deja de esperar: ya no es noticia."""
    ahora = _ahora(ahora)
    (db.query(m.HallazgoLector)
     .filter(m.HallazgoLector.estado == "por_revisar",
             m.HallazgoLector.actualizado_en < ahora - timedelta(
                 hours=VIGENCIA_DEL_HALLAZGO))
     .update({"estado": "vencido"}, synchronize_session=False))
    limite = ahora - timedelta(days=GUARDAR_DIAS)
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
    from sqlalchemy.orm import selectinload

    from app import reloj
    ahora = _ahora(ahora)
    lista = (db.query(m.HallazgoLector)
             .options(selectinload(m.HallazgoLector.notas)
                      .selectinload(m.NotaLector.fuente),
                      selectinload(m.HallazgoLector.tipo),
                      selectinload(m.HallazgoLector.region),
                      selectinload(m.HallazgoLector.municipio))
             .filter(m.HallazgoLector.pais_id == pais.id,
                     m.HallazgoLector.estado == "por_revisar",
                     m.HallazgoLector.actualizado_en
                     >= ahora - timedelta(hours=VIGENCIA_DEL_HALLAZGO))
             .all())
    # Lo mas grave primero, y en cada nivel lo mas reciente.
    lista.sort(key=lambda h: (-(h.nivel or 0),
                              -(h.actualizado_en or h.creado_en).timestamp()))
    lista = lista[:EN_LA_PANTALLA]
    hoy = ahora.astimezone(reloj.zona(pais.zona_horaria)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    leidas = (db.query(func.count(m.NotaLector.id))
              .filter(m.NotaLector.leida_en >= hoy).scalar() or 0)
    filtradas = (db.query(func.count(m.NotaLector.id))
                 .filter(m.NotaLector.leida_en >= hoy,
                         m.NotaLector.estado.in_(["nueva", "analizada",
                                                  "no_es"])).scalar() or 0)

    def contar(*estados):
        return (db.query(func.count(m.HallazgoLector.id))
                .filter(m.HallazgoLector.pais_id == pais.id,
                        m.HallazgoLector.estado.in_(estados),
                        m.HallazgoLector.revisado_en >= hoy).scalar() or 0)
    return {
        "hallazgos": [vista_hallazgo(db, h) for h in lista],
        "hoy": {"leidas": leidas, "parecian": filtradas,
                "fuentes": db.query(func.count(m.FuenteLector.id))
                .filter_by(activa=True).scalar() or 0,
                "eventos": contar("evento", "sumado"),
                "descartados": contar("descartado")},
        "llaves": {"ia": bool(settings.anthropic_api_key),
                   "x": bool(settings.x_bearer_token)},
        "pausado": parametros(db).pausado,
        "ia": vista_falla(db),
    }


def vista_falla(db: Session) -> dict | None:
    """Si Claude no esta contestando: que paso, lo que dijo, desde cuando
    y cuantas notas esperan. None si todo va bien."""
    par = parametros(db)
    if not par.ia_falla or not settings.anthropic_api_key:
        return None
    return {"falla": par.ia_falla, "detalle": par.ia_detalle,
            "desde": par.ia_falla_en.isoformat() if par.ia_falla_en else None,
            "esperan": db.query(func.count(m.NotaLector.id))
            .filter_by(estado="nueva").scalar() or 0}


# ============================================================ lo que hace el analista

def hallazgo_de(db: Session, hallazgo_id: int,
                bloquear: bool = False) -> m.HallazgoLector:
    """El hallazgo. Con `bloquear`, de uno en uno: dos analistas que pican
    «Crear el evento» a la vez no hacen dos eventos."""
    q = db.query(m.HallazgoLector).filter_by(id=hallazgo_id)
    if bloquear:
        q = q.with_for_update()
    h = q.first()
    if not h:
        raise HTTPException(404, "No existe ese hallazgo")
    return h


def _sin_revisar(h: m.HallazgoLector) -> None:
    if h.estado != "por_revisar":
        raise HTTPException(409, "Ese hallazgo ya se revisó")


def _cerrar(h: m.HallazgoLector, usuario: m.Usuario | None,
            estado: str) -> None:
    h.estado = estado
    h.revisado_por_id = usuario.id if usuario else None
    h.revisado_en = _ahora()


def _fuentes_al_evento(db: Session, usuario: m.Usuario | None,
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


def crear_evento(db: Session, usuario: m.Usuario | None,
                 h: m.HallazgoLector, cambios: dict) -> m.EventoRiesgo:
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
        # Lo que escribio Claude para el cliente: el analista lo corrige.
        "texto_cliente": h.texto_cliente or "",
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


# ============================================================ lo que publica solo
#
# Seccion 143 (Salvador, 3 oct): lo de nivel 1 o 2 que dice una fuente
# oficial, que dicen tres medios distintos, o que es informativo, sale al
# cliente sin analista. Siempre al analista: nivel 3 o 4, lo de hace mas
# de seis horas, lo que no se sabe ubicar (tipo, estado y municipio), lo
# que es el mismo hecho que un evento, y lo que no trae texto para el
# cliente. Firma «Connect» en la bitacora y el evento queda marcado.

VENTANA_SOLO = timedelta(hours=6)
MEDIOS_PARA_CONFIRMAR = 3
MAX_SOLOS_POR_VUELTA = 10
REGLAS_SOLO = ("oficial", "confirmado", "informativo", "alto", "critico")
# Seccion 147 (Salvador, 3 oct: «que pasa si esta super confirmado y el
# analista se demora y nos gana la noticia?»): lo de nivel 3 y 4 tambien
# sale solo, al momento, si esta muy confirmado: una fuente oficial y dos
# medios mas, o cuatro medios distintos. El 4 sale como 4, sin el jefe de
# turno (su decision); queda marcado para que lo revise.
MEDIOS_MUY_CONFIRMADO = 4


def _cuando(h: m.HallazgoLector):
    if h.ocurrio_en:
        return h.ocurrio_en
    fechas = [n.publicada_en for n in h.notas if n.publicada_en]
    return min(fechas) if fechas else None


def regla_para_publicar_solo(h: m.HallazgoLector, par: m.ParametrosLector,
                             ahora: datetime) -> tuple[str, str] | None:
    """Por que regla sale solo este hallazgo, con su dato, o None si va
    al analista."""
    if not par.solo_activo or h.estado != "por_revisar" or h.evento_id:
        return None
    if h.nivel not in (1, 2, 3, 4) or not h.con_ia:
        return None
    if not (h.tipo_id and h.region_id and h.municipio_id):
        return None
    if h.tipo and h.tipo.nombre in NUNCA_SOLO:
        return None
    if len((h.texto_cliente or "").strip()) < 20:
        return None
    cuando = _cuando(h)
    if cuando is None or cuando < ahora - VENTANA_SOLO:
        return None
    oficiales = [n.fuente.nombre for n in h.notas if n.fuente.oficial]
    medios = {(n.medio or n.fuente.nombre).strip().lower() for n in h.notas}
    if h.nivel in (3, 4):
        muy = ((oficiales and len(medios) >= 3)
               or len(medios) >= MEDIOS_MUY_CONFIRMADO)
        if not muy:
            return None
        if h.nivel == 3 and par.solo_alto:
            return "alto", str(len(medios))
        if h.nivel == 4 and par.solo_critico:
            return "critico", str(len(medios))
        return None
    if par.solo_oficial and oficiales:
        return "oficial", oficiales[0][:120]
    if par.solo_confirmado and len(medios) >= MEDIOS_PARA_CONFIRMAR:
        return "confirmado", str(len(medios))
    if par.solo_informativo and h.nivel == 1:
        return "informativo", ""
    return None


def _por_que(regla: tuple[str, str], nivel: int) -> str:
    """Lo que queda en la bitacora."""
    clave, dato = regla
    if clave == "oficial":
        motivo = f"fuente oficial ({dato})"
    elif clave == "confirmado":
        motivo = f"lo dicen {dato} medios distintos"
    elif clave == "alto":
        motivo = f"muy confirmado, {dato} fuentes distintas"
    elif clave == "critico":
        motivo = (f"muy confirmado, {dato} fuentes distintas; salió como 4 "
                  "sin el jefe de turno")
    else:
        motivo = "informativo"
    return f"Lo publicó solo: {motivo}, nivel {nivel}"


def publicar_solos(db: Session, ahora: datetime | None = None) -> int:
    """Lo que cumple una regla se crea y se publica sin analista. Cada uno
    en su propio intento: uno que falla no frena a los demas."""
    from sqlalchemy.orm import selectinload

    from app import riesgo
    ahora = _ahora(ahora)
    par = parametros(db)
    if not par.solo_activo:
        return 0
    candidatos = (db.query(m.HallazgoLector)
                  .options(selectinload(m.HallazgoLector.notas)
                           .selectinload(m.NotaLector.fuente))
                  .filter(m.HallazgoLector.estado == "por_revisar",
                          m.HallazgoLector.evento_id.is_(None),
                          m.HallazgoLector.nivel.in_([1, 2, 3, 4]),
                          m.HallazgoLector.actualizado_en
                          >= ahora - VENTANA_SOLO)
                  .order_by(m.HallazgoLector.nivel.desc(),
                            m.HallazgoLector.id).all())
    publicados = 0
    for h in candidatos:
        if publicados >= MAX_SOLOS_POR_VUELTA:
            break
        regla = regla_para_publicar_solo(h, par, ahora)
        if not regla:
            continue
        firma = riesgo.QUIEN_SISTEMA.set("Connect")
        try:
            with db.begin_nested():
                evento = crear_evento(db, None, h, {})
                evento.auto_regla, evento.auto_dato = regla
                riesgo.publicar(db, None, evento, ahora,
                                detalle=_por_que(regla, evento.nivel),
                                sin_segunda_firma=regla[0] == "critico")
            publicados += 1
        except Exception as e:                           # noqa: BLE001
            log.warning("No se pudo publicar solo el hallazgo H%s: %s",
                        h.id, e)
        finally:
            riesgo.QUIEN_SISTEMA.reset(firma)
    return publicados


def vista_solos(db: Session, pais: m.Pais, ahora: datetime) -> dict:
    """Las reglas y lo que publico solo hoy, por regla."""
    from app import reloj
    par = parametros(db)
    hoy = ahora.astimezone(reloj.zona(pais.zona_horaria)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    filas = (db.query(m.EventoRiesgo.auto_regla, m.EventoRiesgo.estado)
             .filter(m.EventoRiesgo.pais_id == pais.id,
                     m.EventoRiesgo.auto_regla.isnot(None),
                     m.EventoRiesgo.publicado_en >= hoy).all())
    return {"activo": par.solo_activo, "oficial": par.solo_oficial,
            "confirmado": par.solo_confirmado,
            "informativo": par.solo_informativo,
            "alto": par.solo_alto, "critico": par.solo_critico,
            "hoy": {"total": len(filas),
                    **{r: sum(1 for x, _ in filas if x == r)
                       for r in REGLAS_SOLO},
                    "cerrados": sum(1 for _, e in filas if e in (
                        m.EstadoEvento.CERRADO,
                        m.EstadoEvento.DESCARTADO))}}


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
                       "x": bool(settings.x_bearer_token)},
            "ia": vista_falla(db),
            "solos": vista_solos(db, pais, ahora)}


def agregar_fuente(db: Session, usuario: m.Usuario, pais: m.Pais,
                   datos: dict) -> m.FuenteLector:
    tipo = datos.get("tipo")
    if tipo not in TIPOS:
        raise HTTPException(400, "El tipo es medio, búsqueda o lista de X")
    direccion = (datos.get("direccion") or "").strip()
    if tipo == "medio":
        if not direccion.lower().startswith(("http://", "https://")):
            raise HTTPException(400, "Un medio se agrega con la dirección de "
                                     "su RSS (empieza con https://)")
        _direccion_publica(direccion)
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

"""Google Maps, siempre desde el servidor.

El punto de encuentro es el dato mas importante del servicio: de sus
coordenadas salen la geocerca que el conductor tiene que pisar para
marcar su llegada y los tres hospitales mas cercanos del task sheet.
Escribirlas a mano es la forma mas facil de equivocarse, asi que aqui se
buscan en Google y se toman de ahi.

La llave nunca sale del servidor: ni la busqueda ni la imagen del mapa
pasan por el navegador con la llave puesta. Asi no se puede copiar de la
pantalla ni la cobra alguien mas, y las direcciones de los ejecutivos
salen de un solo lugar, no del navegador de cada consultor.
"""
from urllib.parse import quote, urlencode

import httpx

from app.config import settings

BUSQUEDA = "https://places.googleapis.com/v1/places:searchText"
SUGERENCIAS = "https://places.googleapis.com/v1/places:autocomplete"
DETALLE = "https://places.googleapis.com/v1/places"
ESTATICO = "https://maps.googleapis.com/maps/api/staticmap"
CAMPOS = "places.displayName,places.formattedAddress,places.location"
TIEMPO = 8.0


class SinLlave(RuntimeError):
    """No hay llave de Google configurada."""


def _llave() -> str:
    llave = (settings.google_maps_key or "").strip()
    if not llave:
        raise SinLlave(
            "Falta la llave de Google Maps. Se configura en el archivo .env "
            "como GOOGLE_MAPS_KEY y se reinicia la aplicacion.")
    return llave


def enlace(direccion: str | None = None, lat=None, lon=None) -> str | None:
    """Para abrir el punto en la app de Google Maps del telefono."""
    if lat is not None and lon is not None:
        destino = f"{lat},{lon}"
    elif direccion and direccion.strip():
        destino = direccion.strip()
    else:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={quote(destino)}"


def buscar(texto: str, pais: str | None = None, idioma: str = "es",
           cuantos: int = 5) -> list[dict]:
    """Lugares que coinciden con lo que escribio el consultor.

    Se busca a peticion, no mientras teclea: cada busqueda se cobra, y
    "Las Alcobas Polanco" encuentra el hotel igual de bien que media
    docena de busquedas a medio escribir.
    """
    texto = (texto or "").strip()
    if len(texto) < 3:
        return []

    cuerpo = {"textQuery": texto, "languageCode": idioma,
              "maxResultCount": max(1, min(cuantos, 10))}
    if pais:
        cuerpo["regionCode"] = pais

    respuesta = httpx.post(
        BUSQUEDA, json=cuerpo, timeout=TIEMPO,
        headers={"X-Goog-Api-Key": _llave(), "X-Goog-FieldMask": CAMPOS})
    respuesta.raise_for_status()

    lugares = []
    for lugar in respuesta.json().get("places", []):
        punto = lugar.get("location") or {}
        if punto.get("latitude") is None:
            continue
        lugares.append({
            "nombre": (lugar.get("displayName") or {}).get("text"),
            "direccion": lugar.get("formattedAddress"),
            "lat": punto["latitude"],
            "lon": punto["longitude"],
        })
    return lugares


CERCANOS = "https://places.googleapis.com/v1/places:searchNearby"
# Del hospital se guarda lo que sirve en una emergencia: como se llama,
# donde esta, a que numero se marca y el punto exacto para llegar.
CAMPOS_HOSPITAL = ("places.displayName,places.formattedAddress,"
                   "places.location,places.nationalPhoneNumber,"
                   "places.internationalPhoneNumber")


def buscar_hospital(nombre: str, lat: float, lon: float,
                    radio_m: int = 6000, idioma: str = "es") -> dict | None:
    """Un hospital por su nombre, buscado alrededor de donde se cree que
    esta.

    Se busca por nombre y no entre los de al lado porque el catalogo ya
    dice cual es: lo que falta es el dato bueno —la direccion, el
    telefono, las coordenadas de verdad—. El circulo alrededor de la
    ubicacion aproximada es lo que evita traerse el hospital del mismo
    nombre que esta en otra ciudad.
    """
    nombre = (nombre or "").strip()
    if len(nombre) < 3:
        return None

    def preguntar(radio: int, solo_hospitales: bool) -> list:
        cuerpo = {
            "textQuery": nombre,
            "languageCode": idioma,
            "maxResultCount": 1,
            "locationBias": {"circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(max(100, min(radio, 50000)))}},
        }
        if solo_hospitales:
            cuerpo["includedType"] = "hospital"
        respuesta = httpx.post(
            BUSQUEDA, json=cuerpo, timeout=TIEMPO,
            headers={"X-Goog-Api-Key": _llave(),
                     "X-Goog-FieldMask": CAMPOS_HOSPITAL})
        respuesta.raise_for_status()
        return respuesta.json().get("places", [])

    lugares = preguntar(radio_m, True)
    if not lugares:
        # Segundo intento, mas abierto. La ubicacion del catalogo es
        # aproximada, asi que el circulo puede estar dejando fuera al
        # hospital de verdad; y hay hospitales que Google no clasifica
        # como "hospital" sino como centro medico o clinica.
        lugares = preguntar(max(radio_m, 20000), False)
    if not lugares:
        return None
    lugar = lugares[0]
    punto = lugar.get("location") or {}
    if punto.get("latitude") is None:
        return None
    return {
        "nombre": (lugar.get("displayName") or {}).get("text"),
        "direccion": lugar.get("formattedAddress"),
        "telefono": (lugar.get("nationalPhoneNumber")
                     or lugar.get("internationalPhoneNumber")),
        "lat": punto["latitude"],
        "lon": punto["longitude"],
    }


def hospitales_cerca(lat: float, lon: float, radio_m: int = 8000,
                     idioma: str = "es", cuantos: int = 15) -> list[dict]:
    """Los hospitales alrededor de un punto, como los ve Google.

    De aqui salen el nombre oficial, la direccion, el telefono y las
    coordenadas —los cuatro datos que en una emergencia no se pueden
    estar escribiendo a mano ni recordando mal—. Lo que Google no sabe
    es hasta donde llega cada hospital: eso lo marca Centauro al darlo
    de alta, y no se adivina, porque de ese nivel sale la regla que
    garantiza un quirofano en la referencia medica.
    """
    radio_m = max(100, min(int(radio_m), 50000))
    cuerpo = {
        "includedTypes": ["hospital"],
        "maxResultCount": max(1, min(cuantos, 20)),
        "languageCode": idioma,
        "locationRestriction": {"circle": {
            "center": {"latitude": lat, "longitude": lon},
            "radius": float(radio_m)}},
        # Por distancia y no por "relevancia": en una emergencia lo que
        # importa es cual esta mas cerca, no cual esta mejor calificado.
        "rankPreference": "DISTANCE",
    }
    respuesta = httpx.post(
        CERCANOS, json=cuerpo, timeout=TIEMPO,
        headers={"X-Goog-Api-Key": _llave(),
                 "X-Goog-FieldMask": CAMPOS_HOSPITAL})
    respuesta.raise_for_status()

    hospitales = []
    for lugar in respuesta.json().get("places", []):
        punto = lugar.get("location") or {}
        if punto.get("latitude") is None:
            continue
        hospitales.append({
            "nombre": (lugar.get("displayName") or {}).get("text"),
            "direccion": lugar.get("formattedAddress"),
            "telefono": (lugar.get("nationalPhoneNumber")
                         or lugar.get("internationalPhoneNumber")),
            "lat": punto["latitude"],
            "lon": punto["longitude"],
        })
    return hospitales


# Las divisiones de una ciudad —alcaldias, municipios, comunas, distritos—
# son "regiones" para Google. Se piden asi y cada pais contesta con las
# suyas, que es justo lo que se necesita: en Mexico salen las alcaldias,
# en Chile las comunas, sin una lista por pais escrita a mano.
REGIONES = "(regions)"
# Y las ciudades, para dar de alta una plaza nueva con el nombre que
# tiene de verdad. "Sn Pedro Garza Garcia" y "San Pedro Garza Garcia"
# son la misma ciudad escritas por dos personas distintas; tomarla de
# Google evita que el catalogo termine con las dos.
CIUDADES = "(cities)"


def sugerir(texto: str, sesion: str, pais: str | None = None,
            idioma: str = "es", tipos: list[str] | None = None,
            cerca: tuple[float, float] | None = None,
            radio_km: int = 50) -> list[dict]:
    """Lo que Google propone mientras el consultor escribe.

    Va con un identificador de sesion: Google cobra una sesion completa
    —todas las teclas mas el detalle del lugar que se elija— en vez de
    cobrar cada peticion por separado. Por eso el mismo identificador
    tiene que viajar en las sugerencias y en el detalle, y cambiar cuando
    se empieza a buscar otra cosa.
    """
    texto = (texto or "").strip()
    if len(texto) < 3:
        return []

    cuerpo = {"input": texto, "languageCode": idioma, "sessionToken": sesion}
    if pais:
        cuerpo["includedRegionCodes"] = [pais]
    if tipos:
        cuerpo["includedPrimaryTypes"] = tipos
    if cerca:
        # Alrededor del punto donde se presenta el equipo: "Miguel
        # Hidalgo" hay en varios estados, y la que importa es la de la
        # ciudad donde corre el servicio.
        # Google no acepta un radio mayor a cincuenta kilometros: pedir
        # mas no amplia la busqueda, la rechaza entera.
        metros = max(1, min(radio_km, 50)) * 1000
        cuerpo["locationBias"] = {"circle": {
            "center": {"latitude": float(cerca[0]),
                       "longitude": float(cerca[1])},
            "radius": metros}}

    respuesta = httpx.post(SUGERENCIAS, json=cuerpo, timeout=TIEMPO,
                           headers={"X-Goog-Api-Key": _llave()})
    respuesta.raise_for_status()

    propuestas = []
    for fila in respuesta.json().get("suggestions", []):
        prediccion = fila.get("placePrediction")
        if not prediccion:
            continue                      # las sugerencias de consulta no sirven
        formato = prediccion.get("structuredFormat") or {}
        propuestas.append({
            "id": prediccion.get("placeId"),
            "nombre": (formato.get("mainText") or {}).get("text")
                      or (prediccion.get("text") or {}).get("text"),
            "direccion": (formato.get("secondaryText") or {}).get("text"),
        })
    return propuestas


def detalle(lugar_id: str, sesion: str, idioma: str = "es") -> dict:
    """El lugar elegido, ya con sus coordenadas. Cierra la sesion de cobro."""
    respuesta = httpx.get(
        f"{DETALLE}/{lugar_id}",
        params={"languageCode": idioma, "sessionToken": sesion},
        timeout=TIEMPO,
        headers={"X-Goog-Api-Key": _llave(),
                 # El telefono viene en el mismo llamado: pedirlo aparte
                 # seria otra sesion de cobro por el mismo lugar.
                 "X-Goog-FieldMask":
                     "displayName,formattedAddress,location,types,"
                     "internationalPhoneNumber,nationalPhoneNumber"})
    respuesta.raise_for_status()
    lugar = respuesta.json()
    punto = lugar.get("location") or {}
    tipos = lugar.get("types") or []
    return {
        "nombre": (lugar.get("displayName") or {}).get("text"),
        "direccion": lugar.get("formattedAddress"),
        "lat": punto.get("latitude"),
        "lon": punto.get("longitude"),
        # Google ya sabe si el punto es un aeropuerto. Si lo es, el servicio
        # arranca contra un vuelo y hay que pedir sus datos.
        "aeropuerto": any(t in ("airport", "international_airport")
                          for t in tipos),
        # Con clave de pais, que es la regla del sistema: el ejecutivo
        # puede estar marcando desde el extranjero.
        "telefono": (lugar.get("internationalPhoneNumber")
                     or lugar.get("nationalPhoneNumber")),
    }


# Que tanto se aleja el mapa para que el circulo de la geocerca quepa.
ACERCAMIENTO = ((300, 16), (700, 15), (1500, 14), (3000, 13))


def _zoom_para(metros: int | None) -> int:
    if not metros:
        return 16
    for tope, zoom in ACERCAMIENTO:
        if metros <= tope:
            return zoom
    return 12


def imagen(lat, lon, zoom: int | None = None, ancho: int = 520,
           alto: int = 300, metros: int | None = None) -> bytes:
    """El mapa del punto, con su pin en el azul de la casa.

    Se pide desde el servidor y se devuelve la imagen: el navegador
    recibe un PNG, no una llave.
    """
    parametros = {
        "center": f"{lat},{lon}",
        "zoom": zoom or _zoom_para(metros),
        "size": f"{ancho}x{alto}",
        "scale": 2,
        "maptype": "roadmap",
        "markers": f"color:0x1B1546|{lat},{lon}",
        "key": _llave(),
    }
    if metros:
        # La geocerca dibujada, para ver de que tamano es el circulo que el
        # conductor tiene que pisar.
        parametros["path"] = _circulo(float(lat), float(lon), metros)

    respuesta = httpx.get(f"{ESTATICO}?{urlencode(parametros)}", timeout=TIEMPO)
    respuesta.raise_for_status()
    return respuesta.content


def _circulo(lat: float, lon: float, metros: int, puntos: int = 24) -> str:
    """El contorno de la geocerca, en grados alrededor del punto."""
    import math

    grados_lat = metros / 111_320
    grados_lon = metros / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    vertices = []
    for i in range(puntos + 1):
        angulo = 2 * math.pi * i / puntos
        vertices.append(f"{lat + grados_lat * math.sin(angulo):.6f},"
                        f"{lon + grados_lon * math.cos(angulo):.6f}")
    return "color:0x1B1546aa|weight:2|fillcolor:0x1B154622|" + "|".join(vertices)

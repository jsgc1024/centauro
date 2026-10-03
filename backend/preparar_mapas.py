"""Arma los mapas del riesgo de fondo (seccion 135): los contornos de los
estados y de los municipios de Mexico, simplificados para el navegador.

Se corre a mano, una vez, y lo que sale se guarda en el repositorio
(`app/web/geo/`): el servidor no baja nada al arrancar. Vuelve a correrse
solo si INEGI cambia municipios (un municipio nuevo aparece cada pocos
anos).

    python3 preparar_mapas.py

Fuente: el Marco Geoestadistico de INEGI (2022), en la copia en GeoJSON
de github.com/PhantomInsights/mexico-geojson. Datos abiertos de INEGI.

Sin el detalle de la costa ni de cada calle: un municipio se reconoce en
el mapa igual con 1 de cada 50 vertices, y el archivo de cada estado
pasa de 3 MB a unos 100 KB.
"""
import json
import pathlib
import urllib.parse
import urllib.request

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

FUENTE = ("https://raw.githubusercontent.com/PhantomInsights/mexico-geojson/"
          "main/2022/states/{}.json")
# El nombre oficial de INEGI, que es como se llama cada archivo.
ESTADOS = {
    "01": "Aguascalientes", "02": "Baja California",
    "03": "Baja California Sur", "04": "Campeche",
    "05": "Coahuila de Zaragoza", "06": "Colima", "07": "Chiapas",
    "08": "Chihuahua", "09": "Ciudad de México", "10": "Durango",
    "11": "Guanajuato", "12": "Guerrero", "13": "Hidalgo", "14": "Jalisco",
    "15": "México", "16": "Michoacán de Ocampo", "17": "Morelos",
    "18": "Nayarit", "19": "Nuevo León", "20": "Oaxaca", "21": "Puebla",
    "22": "Querétaro", "23": "Quintana Roo", "24": "San Luis Potosí",
    "25": "Sinaloa", "26": "Sonora", "27": "Tabasco", "28": "Tamaulipas",
    "29": "Tlaxcala", "30": "Veracruz de Ignacio de la Llave",
    "31": "Yucatán", "32": "Zacatecas",
}
TOLERANCIA_MUNICIPIO = 0.004      # grados, ~400 m
TOLERANCIA_ESTADO = 0.02          # ~2 km
DESTINO = pathlib.Path(__file__).parent / "app" / "web" / "geo"


def _redondear(geometria: dict, decimales: int = 4) -> dict:
    def r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], decimales), round(c[1], decimales)]
        return [r(x) for x in c]
    return {"type": geometria["type"], "coordinates": r(geometria["coordinates"])}


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    estados = []
    for clave, nombre in ESTADOS.items():
        url = FUENTE.format(urllib.parse.quote(nombre))
        with urllib.request.urlopen(url, timeout=120) as r:
            datos = json.load(r)
        municipios, formas = [], []
        for f in datos["features"]:
            forma = shape(f["geometry"]).buffer(0)
            formas.append(forma)
            chica = forma.simplify(TOLERANCIA_MUNICIPIO, preserve_topology=True)
            municipios.append({"type": "Feature",
                               "properties": {"c": int(f["properties"]["CVEGEO"]),
                                              "n": f["properties"]["NOMGEO"]},
                               "geometry": _redondear(mapping(chica))})
        (DESTINO / f"mun_{clave}.json").write_text(json.dumps(
            {"type": "FeatureCollection", "features": municipios},
            ensure_ascii=False, separators=(",", ":")))
        estado = unary_union(formas).simplify(TOLERANCIA_ESTADO,
                                              preserve_topology=True)
        estados.append({"type": "Feature", "properties": {"c": clave},
                        "geometry": _redondear(mapping(estado), 3)})
        print(clave, nombre, len(municipios))
    (DESTINO / "estados.json").write_text(json.dumps(
        {"type": "FeatureCollection", "features": estados},
        ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

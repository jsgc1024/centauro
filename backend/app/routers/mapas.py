"""Buscar un punto en Google y dibujarlo, sin que la llave salga de aqui."""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import auth, mapas
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/mapas", tags=["Mapas"])


def _fuera(error: Exception) -> HTTPException:
    if isinstance(error, mapas.SinLlave):
        return HTTPException(503, {"mensaje": str(error)})

    # Cuando Google rechaza la peticion contesta por que en el cuerpo, no
    # en el texto de la excepcion. Sin eso todo se ve igual —"no
    # contesto"— y no se puede arreglar nada.
    detalle = str(error)[:200]
    respuesta = getattr(error, "response", None)
    if respuesta is not None:
        try:
            cuerpo = respuesta.json().get("error", {})
            detalle = f"{respuesta.status_code}: {cuerpo.get('message') or cuerpo}"
        except Exception:
            detalle = f"{respuesta.status_code}: {respuesta.text[:200]}"

    return HTTPException(502, {
        "mensaje": "Google Maps no contesto. Revisa la conexion o la llave.",
        "detalle": detalle[:300]})


@router.get("/lugares", summary="Buscar un punto de encuentro en Google")
def lugares(texto: str, pais_id: int | None = None,
            db: Session = Depends(get_db),
            _=Depends(auth.puede("mapas.buscar"))):
    """Devuelve los lugares que coinciden, ya con sus coordenadas: de ahi
    salen la geocerca y los hospitales cercanos del task sheet."""
    pais = db.get(m.Pais, pais_id) if pais_id else None
    try:
        return {"lugares": mapas.buscar(texto, pais.codigo if pais else None)}
    except (mapas.SinLlave, httpx.HTTPError) as error:
        raise _fuera(error)


@router.get("/sugerencias", summary="Lo que Google propone mientras se escribe")
def sugerencias(texto: str, sesion: str, pais_id: int | None = None,
                tipos: str | None = None,
                lat: float | None = None, lon: float | None = None,
                db: Session = Depends(get_db),
                _=Depends(auth.puede("mapas.buscar"))):
    """El identificador de sesion agrupa el cobro: todas las teclas de una
    misma busqueda mas el detalle del lugar elegido cuentan como una.

    Con tipos=regiones contesta divisiones —alcaldias, municipios,
    comunas— en vez de lugares. Sirve para decir por donde opera un
    servicio, que no es un punto sino un pedazo de ciudad. Con
    tipos=ciudades contesta ciudades, para dar de alta una plaza con su
    nombre oficial. Con lat y lon se ordenan las de esa ciudad primero.
    """
    pais = db.get(m.Pais, pais_id) if pais_id else None
    listado = {"regiones": [mapas.REGIONES],
               "ciudades": [mapas.CIUDADES]}.get(tipos)
    cerca = (lat, lon) if lat is not None and lon is not None else None
    try:
        return {"lugares": mapas.sugerir(texto, sesion,
                                         pais.codigo if pais else None,
                                         tipos=listado, cerca=cerca)}
    except (mapas.SinLlave, httpx.HTTPError) as error:
        raise _fuera(error)


@router.get("/lugar/{lugar_id}", summary="El lugar elegido, con sus coordenadas")
def lugar(lugar_id: str, sesion: str,
          _=Depends(auth.puede("mapas.buscar"))):
    try:
        return mapas.detalle(lugar_id, sesion)
    except (mapas.SinLlave, httpx.HTTPError) as error:
        raise _fuera(error)


@router.get("/hospitales", summary="Hospitales cerca de un punto")
def hospitales(lat: float, lon: float, radio_km: float = 8,
               pais_id: int | None = None, plaza_id: int | None = None,
               db: Session = Depends(get_db),
               _=Depends(auth.puede("mapas.buscar"))):
    """Lo que Google sabe del hospital, y lo que ya esta en el catalogo.

    Google llena el nombre, la direccion, el telefono y las coordenadas.
    El nivel de atencion no: eso lo marca Centauro una sola vez, al dar
    de alta el hospital, porque de ahi sale la regla que garantiza un
    quirofano en la referencia medica y no es algo que se adivine.

    Los que ya estan en el catalogo salen marcados, para no dar de alta
    dos veces el mismo hospital con dos escrituras distintas.
    """
    try:
        encontrados = mapas.hospitales_cerca(lat, lon, int(radio_km * 1000))
    except (httpx.HTTPError, mapas.SinLlave) as error:
        raise _fuera(error)

    consulta = db.query(m.Hospital).filter(m.Hospital.activo.is_(True))
    if pais_id:
        consulta = consulta.filter(m.Hospital.pais_id == pais_id)
    if plaza_id:
        consulta = consulta.filter(m.Hospital.plaza_id == plaza_id)
    ya = {(h.nombre or "").strip().lower(): h for h in consulta.all()}

    for hospital in encontrados:
        suyo = ya.get((hospital["nombre"] or "").strip().lower())
        hospital["en_catalogo_id"] = suyo.id if suyo else None
        hospital["nivel_atencion"] = (
            suyo.nivel_atencion.value
            if suyo and suyo.nivel_atencion else None)
    return {"cuantos": len(encontrados), "hospitales": encontrados}


@router.get("/imagen", summary="El mapa del punto, como imagen")
def imagen(lat: float, lon: float, metros: int | None = None,
           zoom: int | None = None,
           _=Depends(auth.puede("mapas.buscar"))):
    """El navegador recibe un PNG; la llave se queda en el servidor."""
    try:
        png = mapas.imagen(lat, lon, zoom=zoom, metros=metros)
    except (mapas.SinLlave, httpx.HTTPError) as error:
        raise _fuera(error)
    # El mismo punto no cambia: que el navegador lo guarde un rato y no
    # se vuelva a cobrar la imagen.
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=86400"})

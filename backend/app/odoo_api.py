# -*- coding: utf-8 -*-
"""La conexion con Odoo, de solo lectura.

Odoo 19 en la nube (centauro.odoo.com), plan Personalizado. Su API
externa es JSON-2: POST /json/2/<modelo>/<metodo>, con la llave en la
cabecera. La API vieja (XML-RPC y JSON-RPC) desaparece con Odoo 20, asi
que aqui ni se toca.

Este cliente SOLO LEE: los metodos permitidos estan en LECTURA y cualquier
otro truena antes de salir a la red. Lo unico que Connect escribe en Odoo
es la prefactura del eventual en borrador (seccion 116), y eso va por su
propio cliente, con su propia llave: `odoo_facturacion`.

La llave es la del usuario de la conexion --no la de una persona--, vive
solo en el .env del servidor (ODOO_API_KEY) y dura a lo mas tres meses:
Odoo no permite mas.
"""
import httpx

from app.config import settings

LECTURA = frozenset({"search_read", "fields_get"})

# En que compania de Odoo vive cada pais (decision de Salvador, 1 de
# octubre; secciones 118 y 119): Mexico es CENTAURO ASS y Brasil, Centauro
# Brasil. La flota se lee de la suya y la prefactura sale a la suya. El
# usuario de la conexion tiene las dos entre sus companias permitidas.
COMPANIAS = {"MX": 1, "BR": 5}
# Centauro Logistic SA CV (seccion 151): su oficina entra a Connect como
# la de Mexico; sus operadores van a LG Connect y sus unidades a la flota
# de Logistica. No es un pais: por eso no va en COMPANIAS.
COMPANIA_LOGISTIC = 3


class SinConexion(Exception):
    """Odoo no esta configurado en este servidor."""


class NoResponde(Exception):
    """Odoo no contesto, o rechazo la llave."""


def candado(db, tipo: str) -> None:
    """Una lectura de este tipo a la vez, hasta que confirme (seccion 100).

    "Aplicar" a mano a las :17:05, mientras corre la de cada hora,
    calculaba las mismas altas; la que llegaba segunda reventaba con
    "ese registro ya existe" y su vuelta entera se revertia. Con el
    candado, la segunda espera y encuentra todo hecho. Vive en la
    transaccion: se suelta solo al confirmar o deshacer.
    """
    import zlib

    from sqlalchemy import text

    db.execute(text("SELECT pg_advisory_xact_lock(:llave)"),
               {"llave": zlib.crc32(f"odoo:{tipo}".encode())})


def hay_conexion() -> bool:
    return bool(settings.odoo_base and settings.odoo_api_key)


class Odoo:
    def __init__(self, base: str, llave: str, bd: str | None = None,
                 timeout: int = 20):
        base = base.strip().rstrip("/")
        self.base = base if base.startswith("http") else "https://" + base
        cabeceras = {"Authorization": f"bearer {llave}",
                     "Content-Type": "application/json; charset=utf-8",
                     "User-Agent": "centauro/1.0"}
        if bd:
            cabeceras["X-Odoo-Database"] = bd
        self.http = httpx.Client(headers=cabeceras, timeout=timeout)

    # Lo que se dice cuando se le pide lo que no puede.
    NO_PUEDE = "no es de lectura: esta conexion no escribe en Odoo"

    def permitido(self, modelo: str, metodo: str, args: dict) -> bool:
        """Lo que esta conexion le puede pedir a Odoo: leer. La de la
        factura (seccion 116) agrega una sola cosa."""
        return metodo in LECTURA

    def llamar(self, modelo: str, metodo: str, **args):
        if not self.permitido(modelo, metodo, args):
            raise RuntimeError(f"{modelo}/{metodo} {self.NO_PUEDE}")
        # Los nombres, en espanol de Mexico: en Odoo cada producto guarda
        # su nombre por idioma (seccion 112, `odoo_idioma`).
        contexto = {"lang": settings.odoo_idioma or "es_MX",
                    **args.pop("context", {})}
        try:
            r = self.http.post(f"{self.base}/json/2/{modelo}/{metodo}",
                               json={"context": contexto, **args})
        except httpx.HTTPError as error:
            raise NoResponde(f"Odoo no contesto: {error}") from error
        if r.status_code == 200:
            return r.json()
        try:
            mensaje = r.json().get("message") or r.text
        except ValueError:
            mensaje = r.text
        mensaje = " ".join(str(mensaje).split())[:200]
        if r.status_code == 401:
            raise NoResponde("Odoo rechazo la llave; puede que haya vencido. "
                             + mensaje)
        raise NoResponde(f"Odoo contesto {r.status_code}: {mensaje}")

    def leer(self, modelo: str, dominio: list, campos: list,
             archivados: bool = False, idioma: str | None = None,
             compania: int | None = None) -> list:
        """`idioma`: los nombres en ese idioma --los de Brasil, en
        portugues (seccion 123)--. `compania`: lo leido desde esa compania;
        la lista de precios de la ficha de un cliente es de cada compania,
        y la de un cliente de Brasil se lee desde la de Brasil."""
        contexto = {"active_test": False} if archivados else {}
        if idioma:
            contexto["lang"] = idioma
        if compania:
            contexto["allowed_company_ids"] = [compania]
        return self.llamar(modelo, "search_read", domain=dominio,
                           fields=campos, order="id", context=contexto) or []

    def campos(self, modelo: str, atributos: list | None = None) -> dict:
        """Los campos que tiene ese modelo en este Odoo: los que agrego
        la empresa con Studio pueden no estar."""
        return self.llamar(modelo, "fields_get",
                           attributes=atributos or ["type"]) or {}


def cliente() -> Odoo:
    if not hay_conexion():
        raise SinConexion("Odoo no esta conectado en este servidor.")
    return Odoo(settings.odoo_base, settings.odoo_api_key,
                settings.odoo_bd or None, settings.odoo_timeout)

# -*- coding: utf-8 -*-
"""La conexion con Odoo, de solo lectura.

Odoo 19 en la nube (centauro.odoo.com), plan Personalizado. Su API
externa es JSON-2: POST /json/2/<modelo>/<metodo>, con la llave en la
cabecera. La API vieja (XML-RPC y JSON-RPC) desaparece con Odoo 20, asi
que aqui ni se toca.

Este cliente SOLO LEE: los metodos permitidos estan en LECTURA y cualquier
otro truena antes de salir a la red. La conexion de Centauro no escribe en
Odoo; lo unico que algun dia escribira es la factura en borrador, y eso
tendra su propio cliente, probado primero en una copia de Odoo.

La llave es la del usuario de la conexion --no la de una persona--, vive
solo en el .env del servidor (ODOO_API_KEY) y dura a lo mas tres meses:
Odoo no permite mas.
"""
import httpx

from app.config import settings

LECTURA = frozenset({"search_read", "fields_get"})


class SinConexion(Exception):
    """Odoo no esta configurado en este servidor."""


class NoResponde(Exception):
    """Odoo no contesto, o rechazo la llave."""


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

    def llamar(self, modelo: str, metodo: str, **args):
        if metodo not in LECTURA:
            raise RuntimeError(f"{metodo} no es de lectura: esta conexion no "
                               "escribe en Odoo")
        contexto = {"lang": "es_MX", **args.pop("context", {})}
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
             archivados: bool = False) -> list:
        contexto = {"active_test": False} if archivados else {}
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

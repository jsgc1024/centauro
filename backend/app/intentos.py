"""Cuantas veces se puede fallar la contrasena antes de que espere.

Sin esto, `POST /auth/token` acepta intentos sin fin: una lista de
correos y un diccionario bastan para entrar, y en la bitacora de accesos
no queda nada raro porque cada intento es una peticion normal.

Los contadores viven en Redis y no en memoria a proposito: en produccion
la API corre con varios trabajadores, y un contador por proceso deja el
limite en "ocho por trabajador", que no es un limite.

**Se abre, no se cierra, si Redis no contesta.** Un candado que depende
de un servicio que puede caerse deja a toda la operacion sin entrar
justo el dia malo. Que se pueda intentar de mas un rato es peor que
nadie pueda trabajar.
"""
import logging

from fastapi import HTTPException

from app.config import settings

registro = logging.getLogger("centauro.intentos")

# Ocho fallos seguidos no los hace quien se equivoco de contrasena: los
# hace un programa. Quince minutos no estorban a una persona y le
# arruinan el dia a un diccionario.
MAXIMO = 8
VENTANA_SEGUNDOS = 15 * 60

# Desde una misma direccion se prueban muchas cuentas distintas, y eso no
# lo atrapa el contador por correo. El tope es mas alto porque una
# oficina entera sale por la misma IP.
MAXIMO_POR_IP = 40

_cliente = None
_sin_redis = False


def _redis():
    """El cliente, traido una vez. None si no se puede."""
    global _cliente, _sin_redis
    if _sin_redis:
        return None
    if _cliente is None:
        try:
            import redis

            _cliente = redis.Redis.from_url(
                settings.redis_url, socket_connect_timeout=0.5,
                socket_timeout=0.5, decode_responses=True)
            _cliente.ping()
        except Exception as error:                        # noqa: BLE001
            registro.warning("sin Redis: el limite de intentos queda "
                             "abierto (%s)", error)
            _cliente, _sin_redis = None, True
    return _cliente


def _claves(correo: str, ip: str | None) -> list[tuple[str, int]]:
    llaves = [(f"intentos:correo:{(correo or '').strip().lower()}", MAXIMO)]
    if ip:
        llaves.append((f"intentos:ip:{ip}", MAXIMO_POR_IP))
    return llaves


def revisar(correo: str, ip: str | None = None) -> None:
    """Antes de comparar la contrasena. Revienta con 429 si ya se paso."""
    r = _redis()
    if not r:
        return
    try:
        for llave, tope in _claves(correo, ip):
            valor = r.get(llave)
            if valor and int(valor) >= tope:
                espera = max(1, round((r.ttl(llave) or VENTANA_SEGUNDOS) / 60))
                raise HTTPException(429, {
                    "mensaje": "Demasiados intentos fallidos",
                    "que_hacer": (f"Espera {espera} minuto(s) y vuelve a "
                                  "intentar. Si olvidaste la contrasena, "
                                  "pide una invitacion nueva."),
                })
    except HTTPException:
        raise
    except Exception as error:                            # noqa: BLE001
        registro.warning("no se pudo revisar intentos: %s", error)


def fallo(correo: str, ip: str | None = None) -> None:
    """Un intento que no era. Cuenta, y la ventana corre desde el primero."""
    r = _redis()
    if not r:
        return
    try:
        for llave, _ in _claves(correo, ip):
            if r.incr(llave) == 1:
                r.expire(llave, VENTANA_SEGUNDOS)
    except Exception as error:                            # noqa: BLE001
        registro.warning("no se pudo contar el intento: %s", error)


def exito(correo: str, ip: str | None = None) -> None:
    """Entro: se borra la cuenta. Quien se equivoco tres veces y luego le
    atino no arrastra nada."""
    limpiar(correo, ip)


def limpiar(correo: str, ip: str | None = None) -> None:
    r = _redis()
    if not r:
        return
    try:
        r.delete(*[llave for llave, _ in _claves(correo, ip)])
    except Exception as error:                            # noqa: BLE001
        registro.warning("no se pudo limpiar intentos: %s", error)

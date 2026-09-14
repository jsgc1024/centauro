"""Telefonos del task sheet, siempre con clave lada.

El ejecutivo casi siempre es extranjero y marca desde su celular: un
numero sin lada no le sirve de nada. La lada sale del pais del servicio,
porque el sistema es multipais.

Lo que el consultor ya capturo con "+" se respeta tal cual: puede ser un
contacto de otro pais.
"""


def con_lada(telefono: str | None, lada: str | None) -> str | None:
    if not telefono:
        return telefono
    t = " ".join(str(telefono).split())
    if not t:
        return t
    if t.startswith("+"):
        return t
    if t.startswith("00"):           # marcacion internacional a la antigua
        return "+" + t[2:].lstrip()
    if not lada:
        return t
    # Numeros cortos de emergencia (911, 190) se quedan como estan.
    if len(_solo_digitos(t)) <= 5:
        return t
    return f"{lada} {t.lstrip('0').lstrip()}"


def _solo_digitos(t: str) -> str:
    return "".join(c for c in t if c.isdigit())


def lada_de_pais(db, pais_id: int | None) -> str | None:
    """La clave del pais, para completar un telefono al guardarlo."""
    if not pais_id:
        return None
    from app import models as m
    pais = db.get(m.Pais, pais_id)
    return pais.lada if pais else None


def normalizar(db, telefono: str | None, pais_id: int | None) -> str | None:
    """Regla general del sistema: ningun telefono se guarda sin clave de pais.

    Se guarda ya completo, no solo al imprimirlo, porque el numero se usa
    para llamar desde la app, para mandar WhatsApp y para que el ejecutivo
    marque desde el extranjero. Lo que el consultor escriba empezando con
    "+" se respeta tal cual: puede ser un contacto de otro pais.
    """
    return con_lada(telefono, lada_de_pais(db, pais_id))


def poner_lada(nodo, lada: str | None):
    """Recorre el contenido del task sheet y completa todos los telefonos."""
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            if isinstance(valor, str) and clave.endswith("telefono"):
                nodo[clave] = con_lada(valor, lada)
            else:
                poner_lada(valor, lada)
    elif isinstance(nodo, list):
        for elemento in nodo:
            poner_lada(elemento, lada)
    return nodo

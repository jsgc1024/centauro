# -*- coding: utf-8 -*-
"""Corregir los contactos de un servicio (seccion 95).

Pieza 2 de «Para poder operar». Decision 3 de Salvador, 28 de
septiembre: los corrigen el consultor del servicio y quien lo cubre --los
mismos que hacen el alta--, y queda en la bitacora con lo de antes.

El correo y el telefono de quien solicita y del principal se capturan en
el alta y ya no se podian corregir: un correo mal escrito mandaba a otro
lado los avisos del dia, el task sheet y la encuesta, y la unica salida
era borrar el servicio y darlo de alta otra vez, que ya no se puede en
cuanto arranca o tiene viaticos depositados.

Lo que se corrige vale de aqui en adelante:

  * El servicio guarda los datos nuevos, y los avisos que todavia no
    salen se van a la direccion nueva.
  * La encuesta que no se ha contestado, tambien.
  * Si el task sheet ya se libero, la pantalla ofrece la version nueva:
    la hoja que se descarga ya sale con los datos nuevos.
  * Quien solicita se puede cambiar por otro de la lista del cliente, y
    corregirlo tambien en esa lista, para el siguiente servicio.
  * Si otro servicio abierto del mismo cliente lleva el correo de antes,
    se dice cual, para corregirlo ahi con su propia bitacora.

Mientras el servicio no este cerrado ni cancelado.
"""
import re

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import auditoria, auth, reloj, telefonos
from app import models as m
from app.odoo_personal_reglas import DOMINIOS_RAROS

IDIOMAS = ("es", "en", "pt")
CERRADOS = (m.EstatusServicio.CERRADO, m.EstatusServicio.CANCELADO)
# El servicio que ya termino y todavia se corrige: si le aparece el
# correo del principal o del solicitante, la encuesta que no nacio sale
# ahora (seccion 101).
TERMINADOS = (m.EstatusServicio.TERMINADO, m.EstatusServicio.SIN_VISTO_BUENO,
              m.EstatusServicio.EN_FACTURACION)
FORMA_DE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LARGO_NOMBRE = 160
LARGO_CORREO = 160
LARGO_TELEFONO = 40
CAMPOS = ("nombre", "apellidos", "correo", "telefono")


# ---------------------------------------------------------------- leer

def _idioma_del_solicitante(db: Session, servicio: m.Servicio) -> str:
    if servicio.idioma_solicitante:
        return servicio.idioma_solicitante
    pais = db.get(m.Pais, servicio.pais_id)
    return pais.idioma if pais else "es"


def datos(db: Session, servicio: m.Servicio, usuario: m.Usuario) -> dict:
    """Lo que la forma necesita: los contactos de hoy, la lista del
    cliente y si el task sheet ya salio."""
    lista = (db.query(m.Solicitante)
             .filter_by(cliente_id=servicio.cliente_id, activo=True)
             .order_by(m.Solicitante.nombre, m.Solicitante.apellidos).all())
    return {
        "servicio_id": servicio.id,
        "se_puede": servicio.estatus not in CERRADOS,
        "solicitante": {
            "solicitante_id": servicio.solicitante_id,
            "nombre": servicio.solicitante_nombre,
            "apellidos": servicio.solicitante_apellidos,
            "correo": servicio.solicitante_correo,
            "telefono": servicio.solicitante_telefono,
            "idioma": _idioma_del_solicitante(db, servicio),
        },
        "ejecutivo": {
            "nombre": servicio.ejecutivo_nombre,
            "apellidos": servicio.ejecutivo_apellidos,
            "correo": servicio.ejecutivo_correo,
            "telefono": servicio.ejecutivo_telefono,
            "idioma": servicio.idioma_ejecutivo or "en",
        },
        # Solo el equipo que cuida a otro principal lleva el suyo; los
        # demas heredan el del servicio y se corrigen con el.
        "equipos": [{
            "equipo_id": e.id, "alias": e.alias,
            "nombre": e.ejecutivo_nombre, "apellidos": e.ejecutivo_apellidos,
            "correo": e.ejecutivo_correo, "telefono": e.ejecutivo_telefono,
        } for e in servicio.equipos if e.tiene_ejecutivo_propio],
        "lista": [{
            "id": s.id, "nombre": s.nombre, "apellidos": s.apellidos,
            "correo": s.correo, "telefono": s.telefono, "puesto": s.puesto,
        } for s in lista],
        "task_sheet_liberado": servicio.asignacion_confirmada_en is not None,
        "puede_corregir_lista": auth.puede_el_usuario(
            db, usuario, "solicitantes.editar"),
    }


# ---------------------------------------------------------------- limpiar

def _texto(valor, largo: int, que: str) -> str | None:
    limpio = " ".join((valor or "").split()) or None
    if limpio and len(limpio) > largo:
        raise HTTPException(400, f"{que} es demasiado largo.")
    return limpio


def _correo(valor, de_quien: str) -> str | None:
    correo = "".join((valor or "").split()) or None
    if correo is None:
        return None
    if len(correo) > LARGO_CORREO or not FORMA_DE_CORREO.match(correo):
        raise HTTPException(400, f"El correo {de_quien} no esta bien "
                                 f"escrito: {correo}")
    dominio = correo.rsplit("@", 1)[1].lower()
    if dominio in DOMINIOS_RAROS:
        raise HTTPException(400, f"El correo {de_quien} parece mal escrito: "
                                 f"«{dominio}».")
    return correo


def _idioma(valor, quien: str) -> str:
    if valor not in IDIOMAS:
        raise HTTPException(400, f"Di en que idioma lee {quien}.")
    return valor


def _limpiar(db: Session, servicio: m.Servicio, d: dict, de_quien: str) -> dict:
    """`de_quien` va con su preposicion --«de quien solicita», «del
    principal»-- para que el mensaje se lea bien."""
    limpio = {
        "nombre": _texto(d.get("nombre"), LARGO_NOMBRE, "El nombre"),
        "apellidos": _texto(d.get("apellidos"), LARGO_NOMBRE, "Los apellidos"),
        "correo": _correo(d.get("correo"), de_quien),
        "telefono": telefonos.normalizar(
            db, _texto(d.get("telefono"), LARGO_TELEFONO, "El telefono"),
            servicio.pais_id),
    }
    if not limpio["nombre"]:
        raise HTTPException(400, f"Falta el nombre {de_quien}.")
    return limpio


# ---------------------------------------------------------------- corregir

def _igual(a, b) -> bool:
    return (a or "").strip().lower() == (b or "").strip().lower()


def _poner(objeto, prefijo: str, nuevos: dict, quien: str, cambios: list) -> None:
    for campo in CAMPOS:
        actual = getattr(objeto, f"{prefijo}{campo}") or None
        nuevo = nuevos[campo] or None
        if actual != nuevo:
            cambios.append({"quien": quien, "campo": campo,
                            "antes": actual, "despues": nuevo})
            setattr(objeto, f"{prefijo}{campo}", nuevo)


def _repuntar_avisos(db: Session, servicio_id: int, destinatario,
                     antes: str | None, despues: str | None) -> int:
    """Los avisos que todavia no salen se van a la direccion nueva. Los que
    ya salieron no se tocan: ya se intentaron."""
    if not antes or not despues or _igual(antes, despues):
        return 0
    avisos = (db.query(m.Notificacion)
              .filter(m.Notificacion.servicio_id == servicio_id,
                      m.Notificacion.destinatario == destinatario,
                      m.Notificacion.estado == "pendiente",
                      func.lower(m.Notificacion.correo) == antes.strip().lower())
              .all())
    for aviso in avisos:
        aviso.correo = despues
    return len(avisos)


def _repuntar_encuesta(db: Session, servicio: m.Servicio, tipo,
                       nombre: str | None, correo: str | None,
                       idioma: str | None) -> int:
    """La encuesta que no se ha contestado le llega a quien es ahora: su
    recordatorio sale del correo de la encuesta.

    Su vencimiento es hora del pais del servicio y se compara con esa
    misma hora (seccion 101): con la del servidor, en Brasil una encuesta
    que vence en las proximas tres horas se re-apuntaba o no segun la
    hora de Mexico.
    """
    ahora = reloj.ahora_del_servicio(db, servicio)
    cuantas = 0
    for e in (db.query(m.Encuesta)
              .filter_by(servicio_id=servicio.id, tipo=tipo,
                         estatus=m.EstatusEncuesta.ENVIADA)
              .filter(m.Encuesta.respondida_en.is_(None)).all()):
        if e.expira_en and e.expira_en < ahora:
            continue
        e.destinatario_nombre = nombre
        e.destinatario_correo = correo
        if idioma:
            e.idioma = idioma
        cuantas += 1
    return cuantas


def corregir(db: Session, servicio_id: int, entrada: dict,
             usuario: m.Usuario) -> dict:
    """Corrige lo que traiga `entrada` --`solicitante`, `ejecutivo` y
    `equipos`, cada uno opcional-- y dice que cambio. No confirma."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    if servicio.estatus in CERRADOS:
        raise HTTPException(409, "El servicio ya esta cerrado: sus contactos "
                                 "ya no se corrigen.")

    cambios: list[dict] = []
    avisos = encuestas = 0
    lista_corregida = False
    # Los correos que aqui se corrigieron: si otro servicio abierto los
    # lleva, se dice cual.
    de_antes: set[str] = set()

    # ---- quien solicita
    sol = entrada.get("solicitante")
    if sol is not None:
        antes_correo = servicio.solicitante_correo
        antes_idioma = _idioma_del_solicitante(db, servicio)
        nuevo_id = sol.get("solicitante_id")
        if nuevo_id and nuevo_id != servicio.solicitante_id:
            contacto = db.get(m.Solicitante, nuevo_id)
            if not contacto or not contacto.activo:
                raise HTTPException(404, "Ese contacto ya no esta en la lista "
                                         "del cliente.")
            if contacto.cliente_id != servicio.cliente_id:
                raise HTTPException(400, "Ese contacto es de otro cliente.")
            cambios.append({"quien": "solicitante", "campo": "de la lista",
                            "antes": servicio.solicitante_completo,
                            "despues": contacto.completo})
            servicio.solicitante_id = contacto.id
        nuevos = _limpiar(db, servicio, sol, "de quien solicita")
        _poner(servicio, "solicitante_", nuevos, "solicitante", cambios)
        idioma = _idioma(sol.get("idioma"), "quien solicita")
        if idioma != antes_idioma:
            cambios.append({"quien": "solicitante", "campo": "idioma",
                            "antes": antes_idioma, "despues": idioma})
        servicio.idioma_solicitante = idioma

        if sol.get("corregir_en_lista"):
            if not auth.puede_el_usuario(db, usuario, "solicitantes.editar"):
                raise HTTPException(403, "Corregir la lista del cliente no "
                                         "esta en tu puesto.")
            lista_corregida = _corregir_en_la_lista(db, servicio, nuevos)

        avisos += _repuntar_avisos(db, servicio.id, m.Destinatario.SOLICITANTE,
                                   antes_correo, servicio.solicitante_correo)
        if antes_correo and not _igual(antes_correo, servicio.solicitante_correo):
            de_antes.add(antes_correo)
        if any(c["quien"] == "solicitante" for c in cambios):
            encuestas += _repuntar_encuesta(
                db, servicio, m.TipoEncuesta.SOLICITANTE,
                servicio.solicitante_completo, servicio.solicitante_correo,
                servicio.idioma_solicitante)

    # ---- el principal del servicio
    eje = entrada.get("ejecutivo")
    principal_de_antes = None
    if eje is not None:
        antes_correo = servicio.ejecutivo_correo
        principal_de_antes = {campo: getattr(servicio, f"ejecutivo_{campo}")
                              for campo in CAMPOS}
        nuevos = _limpiar(db, servicio, eje, "del principal")
        _poner(servicio, "ejecutivo_", nuevos, "ejecutivo", cambios)
        idioma = _idioma(eje.get("idioma"), "el principal")
        if idioma != (servicio.idioma_ejecutivo or "en"):
            cambios.append({"quien": "ejecutivo", "campo": "idioma",
                            "antes": servicio.idioma_ejecutivo, "despues": idioma})
        servicio.idioma_ejecutivo = idioma
        avisos += _repuntar_avisos(db, servicio.id, m.Destinatario.EJECUTIVO,
                                   antes_correo, servicio.ejecutivo_correo)
        if antes_correo and not _igual(antes_correo, servicio.ejecutivo_correo):
            de_antes.add(antes_correo)
        if any(c["quien"] == "ejecutivo" for c in cambios):
            encuestas += _repuntar_encuesta(
                db, servicio, m.TipoEncuesta.EJECUTIVO,
                servicio.ejecutivo_completo, servicio.ejecutivo_correo,
                servicio.idioma_ejecutivo)

    # ---- el principal de cada equipo que tiene el suyo
    for d in entrada.get("equipos") or []:
        equipo = db.get(m.Equipo, d.get("equipo_id"))
        if not equipo or equipo.servicio_id != servicio.id:
            raise HTTPException(404, "Ese equipo no es de este servicio.")
        if not equipo.tiene_ejecutivo_propio:
            raise HTTPException(400, f"El equipo {equipo.alias} no tiene "
                                     "principal propio: se corrige con el del "
                                     "servicio.")
        antes_correo = equipo.ejecutivo_correo
        de_quien = f"del principal del equipo {equipo.alias}"
        nuevos = _limpiar(db, servicio, d, de_quien)
        _poner(equipo, "ejecutivo_", nuevos, f"equipo {equipo.alias}", cambios)
        avisos += _repuntar_avisos(db, servicio.id, m.Destinatario.EJECUTIVO,
                                   antes_correo, equipo.ejecutivo_correo)

    # ---- los equipos que traian una copia del principal del servicio
    if principal_de_antes is not None:
        cambios += _adoptar_el_del_servicio(servicio, principal_de_antes)

    if cambios:
        auditoria.registrar(db, usuario, servicio, "corregir contactos",
                            _para_la_bitacora(cambios))

    # La encuesta que no nacio (seccion 101): al terminar sin correo del
    # principal --frecuente: se consigue despues-- no se creo, y quien
    # capturaba el correo aqui esperaba que saliera. Sale ahora, si el
    # servicio ya termino; `generar` no repite la que ya existe ni crea
    # la que sigue sin correo.
    nuevas = []
    if (servicio.estatus in TERMINADOS
            and any(c["campo"] == "correo" and c["quien"] in ("solicitante",
                                                                "ejecutivo")
                    for c in cambios)):
        from app import encuestas as motor_encuestas
        nuevas = motor_encuestas.generar(db, servicio.id)
        if nuevas:
            auditoria.registrar(db, usuario, servicio, "enviar encuestas",
                                ", ".join(e.tipo.value for e in nuevas)
                                + " (al corregir el correo)")
    db.flush()
    return {"cambios": cambios, "avisos": avisos, "encuestas": encuestas,
            "encuestas_nuevas": [e.tipo.value for e in nuevas],
            "lista_corregida": lista_corregida,
            "task_sheet_liberado": servicio.asignacion_confirmada_en is not None,
            "otros_servicios": _otros_con_lo_de_antes(db, servicio, de_antes)}


def _adoptar_el_del_servicio(servicio: m.Servicio, de_antes: dict) -> list[dict]:
    """El equipo que traia una copia del principal del servicio pasa a
    heredarlo (seccion 101).

    El alta de la consola copiaba el principal al equipo Alfa, y la hoja,
    el correo del task sheet y los avisos de llegada y contacto leen la
    copia del equipo (`Equipo.tiene_ejecutivo_propio`): corregir el
    correo o el telefono arriba quedaba en la bitacora y en la cartera,
    pero la hoja y los avisos seguian saliendo con el dato viejo. La
    copia identica a lo de antes se suelta --el equipo queda heredando--
    y de ahi en adelante cualquier correccion del servicio le llega
    sola. El equipo que cuida a OTRO principal no se toca.
    """
    adoptados = []
    for equipo in servicio.equipos:
        if not equipo.tiene_ejecutivo_propio:
            continue
        if not all(_igual(getattr(equipo, f"ejecutivo_{campo}"), de_antes[campo])
                   for campo in CAMPOS):
            continue
        for campo in CAMPOS:
            setattr(equipo, f"ejecutivo_{campo}", None)
        adoptados.append({"quien": f"equipo {equipo.alias}", "campo": "principal",
                          "antes": "copia del principal del servicio",
                          "despues": "el del servicio"})
    return adoptados


def _otros_con_lo_de_antes(db: Session, servicio: m.Servicio,
                           correos: set[str]) -> list[str]:
    """Los otros servicios abiertos del mismo cliente que todavia llevan
    un correo que aqui se corrigio. Se dicen para corregirlos ahi; no se
    tocan solos: cada servicio lo corrige quien lo lleva, y queda en su
    propia bitacora."""
    if not correos:
        return []
    bajos = sorted({c.strip().lower() for c in correos})
    otros = (db.query(m.Servicio.folio)
             .filter(m.Servicio.cliente_id == servicio.cliente_id,
                     m.Servicio.id != servicio.id,
                     m.Servicio.estatus.notin_(CERRADOS),
                     or_(func.lower(m.Servicio.solicitante_correo).in_(bajos),
                         func.lower(m.Servicio.ejecutivo_correo).in_(bajos)))
             .order_by(m.Servicio.folio).all())
    return [folio for (folio,) in otros]


def _corregir_en_la_lista(db: Session, servicio: m.Servicio, nuevos: dict) -> bool:
    """Quien solicita, corregido tambien en la lista del cliente: el
    siguiente servicio ya lo toma bien."""
    contacto = (db.get(m.Solicitante, servicio.solicitante_id)
                if servicio.solicitante_id else None)
    if contacto is None:
        from app.routers import solicitantes as contactos
        contacto = contactos.buscar_o_crear(
            db, servicio.cliente_id, nuevos["nombre"], nuevos["apellidos"],
            nuevos["correo"], nuevos["telefono"])
        if contacto is None:
            return False
        servicio.solicitante_id = contacto.id
    if nuevos["correo"]:
        otro = (db.query(m.Solicitante)
                .filter(m.Solicitante.cliente_id == servicio.cliente_id,
                        m.Solicitante.id != contacto.id,
                        func.lower(m.Solicitante.correo) == nuevos["correo"].lower())
                .first())
        if otro:
            raise HTTPException(409, f"Ese correo ya es de {otro.completo} en la "
                                     "lista del cliente: escogelo de la lista.")
    for campo in CAMPOS:
        setattr(contacto, campo, nuevos[campo])
    return True


def _para_la_bitacora(cambios: list) -> str:
    """Quien, que y lo de antes, en una linea para quien audita."""
    partes = []
    for c in cambios:
        antes = c["antes"] if c["antes"] else "vacio"
        despues = c["despues"] if c["despues"] else "vacio"
        partes.append(f"{c['quien']} {c['campo']}: {antes} -> {despues}")
    return "; ".join(partes)

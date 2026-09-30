"""La entrega de la unidad, como proceso aparte del fin del dia.

Seccion 107, decision de Salvador (30 sep): **el servicio termina cuando
el ejecutivo corta**. "Hasta aqui me dejas" es el fin del dia y ahi se
cierran las horas; lo que tarde el conductor en llegar a la oficina y
entregar la camioneta es otro proceso, con su propio plazo --las mismas
24 horas de los viaticos-- y no toca los tiempos del dia.

Hasta la seccion 106 la entrega era un candado en el fin del dia (18
sep): sin revision de entrega no habia fin. Se puso ahi para que las
fotos no se quedaran sin tomar, pero obligaba a marcar el fin desde la
oficina --y el trayecto se cobraba como servicio-- o a topar con el
rechazo con el cliente todavia en el coche.

Lo que preserva la evidencia ahora no es un candado sino que la
entrega **no se puede perder de vista**: nace con el fin, la app la deja
enfrente con su reloj, el telefono la recuerda, la central la ve y el
cierre no sale sin que alguien la haya hecho o haya escrito por que no.
Sin candado duro, por decision de Salvador.
"""
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import reloj
from app import revision

registro = logging.getLogger(__name__)

# Cuantas horas hay para entregar la unidad desde el fin del dia. Las
# mismas que para comprobar los viaticos: es el mismo "mientras cierras
# tu dia" y se viven juntas en la app.
HORAS_PARA_ENTREGAR = 24

MINIMO_JUSTIFICACION = 10


def _abierta(db: Session, servicio_id: int, vehiculo_id: int):
    return (db.query(m.EntregaPendiente)
            .filter_by(servicio_id=servicio_id, vehiculo_id=vehiculo_id)
            .first())


def _quien_responde(jornada: m.Jornada, vehiculo_id: int,
                    persona_id: int) -> int:
    """El que traia esa unidad asignada ese dia; si nadie la trae
    asignada (una sola unidad), quien marco el fin."""
    for a in jornada.personal:
        if a.vehiculo_id == vehiculo_id and a.relevado_en is None:
            return a.persona_id
    return persona_id


def abrir_al_terminar(db: Session, jornada: m.Jornada, persona_id: int,
                      ahora: datetime, avisar: bool = True) -> list[dict]:
    """Con el fin del dia, cada unidad de esa persona que hoy deja el
    servicio sin revision de entrega queda como entrega pendiente.

    Una por unidad y servicio: el segundo del equipo que marca su fin no
    abre otra. Solo escribe y avisa; quien llama guarda.
    """
    servicio_id = jornada.equipo.servicio_id
    abiertas = []
    for falta in revision.falta_entregar(db, jornada, persona_id):
        vehiculo_id = falta["vehiculo_id"]
        if _abierta(db, servicio_id, vehiculo_id):
            continue
        fila = m.EntregaPendiente(
            servicio_id=servicio_id, vehiculo_id=vehiculo_id,
            jornada_id=jornada.id,
            persona_id=_quien_responde(jornada, vehiculo_id, persona_id),
            abierta_en=ahora,
            vence_en=ahora + timedelta(hours=HORAS_PARA_ENTREGAR))
        db.add(fila)
        db.flush()
        abiertas.append((fila, falta["sin_recepcion"]))
        if avisar:
            _avisar_al_terminar(db, fila, falta["sin_recepcion"])
    return [{**_ficha(f, ahora), "sin_recepcion": sin_recepcion}
            for f, sin_recepcion in abiertas]


def cerrar_con_revision(db: Session, rev: m.RevisionUnidad,
                        ahora: datetime) -> bool:
    """La revision de entrega guardada cierra la pendiente de esa unidad."""
    if (rev.tipo.value if hasattr(rev.tipo, "value") else rev.tipo) != "entrega":
        return False
    fila = _abierta(db, rev.servicio_id, rev.vehiculo_id)
    if fila is None or fila.cerrada_en is not None:
        return False
    fila.cerrada_en = ahora
    fila.revision_id = rev.id
    return True


def registrar_sin_revision(db: Session, entrega_id: int, usuario: m.Usuario,
                           justificacion: str,
                           ahora: datetime | None = None) -> dict:
    """Darla por entregada sin revision, con la razon escrita.

    Es la salida cuando las fotos ya no se pueden tomar: queda quien lo
    decidio y por que, y el cierre deja de reclamarla. No es una
    revision --no prueba como volvio la unidad-- y la ficha lo dice asi.
    """
    fila = db.get(m.EntregaPendiente, entrega_id)
    if not fila:
        raise HTTPException(404, f"No existe la entrega pendiente {entrega_id}")
    if fila.cerrada_en is not None:
        raise HTTPException(409, {
            "mensaje": ("Esa unidad ya se entrego con su revision"
                        if fila.revision_id else
                        "Esa entrega ya se registro sin revision"),
            "que_hacer": "No hay nada que registrar."})
    if not justificacion or len(justificacion.strip()) < MINIMO_JUSTIFICACION:
        raise HTTPException(400, {
            "mensaje": "Falta decir por que se da por entregada sin revision",
            "que_hacer": "Escribe que paso con la unidad y por que ya no se "
                         "le tomaron las fotos. Queda en el expediente del "
                         "servicio."})
    from app import auth
    servicio = fila.servicio
    es_su_consultor = (usuario.persona_id is not None
                       and usuario.persona_id == servicio.consultor_id)
    if not (es_su_consultor
            or auth.puede_el_usuario(db, usuario, "operacion.corregir")):
        raise HTTPException(403, {
            "mensaje": "Esto lo registra el consultor del servicio o la central",
            "que_hacer": "Pide la actividad «corregir marcas y cerrar dias» "
                         "a administracion, o que lo haga el consultor."})
    momento = reloj.ahora_del_servicio(db, servicio, ahora)
    fila.cerrada_en = momento
    fila.sin_revision = True
    fila.justificacion = justificacion.strip()
    fila.justificada_por_id = usuario.persona_id
    db.commit()
    db.refresh(fila)
    return {"resultado": "entrega registrada sin revision",
            **_ficha(fila, momento)}


# ------------------------------------------------------------------
# Lo que ve cada quien
# ------------------------------------------------------------------

def _ficha(fila: m.EntregaPendiente, ahora: datetime) -> dict:
    servicio = fila.servicio
    minutos = int((fila.vence_en - ahora).total_seconds() / 60)
    return {
        "entrega_id": fila.id,
        "servicio_id": fila.servicio_id,
        "folio": servicio.folio if servicio else None,
        "cliente": (servicio.cliente.nombre
                    if servicio and servicio.cliente else None),
        "vehiculo_id": fila.vehiculo_id,
        "placa": fila.vehiculo.placa if fila.vehiculo else None,
        "persona_id": fila.persona_id,
        "persona": fila.persona.nombre if fila.persona else None,
        "fecha": fila.jornada.fecha.isoformat() if fila.jornada else None,
        "abierta_en": fila.abierta_en.isoformat(),
        # Como lo pinta la app: el mismo reloj que los viaticos.
        "limite": fila.vence_en.isoformat(),
        "momento": ahora.isoformat(),
        "minutos": minutos,
        "vencido": fila.cerrada_en is None and minutos < 0,
        "cerrada_en": fila.cerrada_en.isoformat() if fila.cerrada_en else None,
        "sin_revision": fila.sin_revision,
        "justificacion": fila.justificacion,
        "justificada_por": (fila.justificada_por.nombre
                            if fila.justificada_por else None),
    }


def _mias(db: Session, persona_id: int) -> list[m.EntregaPendiente]:
    """Las abiertas por las que responde esa persona: las suyas, y las
    de un dia suyo en que la unidad era de todos (una sola unidad)."""
    abiertas = (db.query(m.EntregaPendiente)
                .filter(m.EntregaPendiente.cerrada_en.is_(None))
                .order_by(m.EntregaPendiente.vence_en).all())
    salida = []
    for fila in abiertas:
        if fila.persona_id == persona_id:
            salida.append(fila)
            continue
        jornada = fila.jornada
        if (jornada and any(a.persona_id == persona_id
                            for a in jornada.personal)
                and fila.vehiculo_id in revision.mis_unidades(jornada,
                                                              persona_id)):
            salida.append(fila)
    return salida


def pendientes_de(db: Session, persona_id: int,
                  ahora: datetime | None = None) -> list[dict]:
    """Para la app: lo que esa persona tiene por entregar, con su reloj
    en la hora del pais de cada servicio."""
    relojes = reloj.Relojes(db, ahora)
    salida = []
    for fila in _mias(db, persona_id):
        ficha = _ficha(fila, relojes.del_servicio(fila.servicio))
        # Sin la recepcion no hay como guardar la entrega: la app lo
        # manda con su consultor en vez de a una puerta cerrada.
        ficha["sin_recepcion"] = not revision._hecha(
            db, fila.servicio_id, fila.vehiculo_id, m.TipoRevision.RECIBE)
        salida.append(ficha)
    return salida


def abiertas(db: Session, ahora: datetime | None = None) -> list[dict]:
    """Para la central: todas las que siguen abiertas, las vencidas
    primero."""
    relojes = reloj.Relojes(db, ahora)
    filas = (db.query(m.EntregaPendiente)
             .filter(m.EntregaPendiente.cerrada_en.is_(None))
             .order_by(m.EntregaPendiente.vence_en).all())
    return [_ficha(f, relojes.del_servicio(f.servicio)) for f in filas]


def del_servicio(db: Session, servicio_id: int,
                 ahora: datetime | None = None) -> dict[int, dict]:
    """Por unidad, la entrega pendiente o como se cerro, para la ficha
    del servicio y el revisor del cierre."""
    filas = (db.query(m.EntregaPendiente)
             .filter_by(servicio_id=servicio_id).all())
    if not filas:
        return {}
    momento = reloj.ahora_del_servicio(db, filas[0].servicio, ahora)
    return {f.vehiculo_id: _ficha(f, momento) for f in filas}


# ------------------------------------------------------------------
# Los avisos
# ------------------------------------------------------------------

def _pantalla(fila: m.EntregaPendiente) -> str:
    return f"/app/#/revision/{fila.servicio_id}"


def _avisar_al_terminar(db: Session, fila: m.EntregaPendiente,
                        sin_recepcion: bool) -> None:
    """Al marcar el fin: te falta entregar la unidad, tienes hasta tal
    hora. Nunca frena la marca."""
    from app import push

    lengua = push.idioma_de(db, fila.persona_id)
    placa = fila.vehiculo.placa if fila.vehiculo else "?"
    try:
        push.avisar(db, fila.persona_id,
                    titulo=push.tx(lengua, "entrega_titulo", placa=placa),
                    cuerpo=push.tx(lengua, "entrega_sin_recepcion_cuerpo"
                                   if sin_recepcion else "entrega_cuerpo",
                                   placa=placa,
                                   fecha=f"{fila.vence_en:%d/%m}",
                                   hora=f"{fila.vence_en:%H:%M}"),
                    url=_pantalla(fila), etiqueta=f"entrega-{fila.id}")
    except Exception:                     # noqa: BLE001
        registro.exception("no se pudo avisar la entrega pendiente %s", fila.id)


def avisar_vencidas(db: Session, ahora: datetime | None = None) -> list[str]:
    """El barrido: la que se vencio sin entregar avisa una sola vez a la
    persona, al consultor titular (correo y telefono) y a direccion de
    operaciones del pais. Devuelve las placas avisadas."""
    from app import cierre as motor_cierre
    from app import correo_html
    from app import push
    from app import textos_aviso as ta

    relojes = reloj.Relojes(db, ahora)
    avisadas = []
    filas = (db.query(m.EntregaPendiente)
             .filter(m.EntregaPendiente.cerrada_en.is_(None),
                     m.EntregaPendiente.aviso_vencido_en.is_(None)).all())
    for fila in filas:
        servicio = fila.servicio
        momento = relojes.del_servicio(servicio)
        if momento < fila.vence_en:
            continue
        fila.aviso_vencido_en = momento
        placa = fila.vehiculo.placa if fila.vehiculo else "?"
        folio = servicio.folio if servicio else "?"
        quien = fila.persona.nombre if fila.persona else "—"
        datos = {"placa": placa, "folio": folio, "quien": quien,
                 "fecha": f"{fila.vence_en:%d/%m}",
                 "hora": f"{fila.vence_en:%H:%M}"}

        def al_telefono(persona_id, titulo, cuerpo):
            lengua = push.idioma_de(db, persona_id)
            try:
                push.avisar(db, persona_id,
                            titulo=push.tx(lengua, titulo, **datos),
                            cuerpo=push.tx(lengua, cuerpo, **datos),
                            url=_pantalla(fila),
                            etiqueta=f"entrega-vencida-{fila.id}")
            except Exception:             # noqa: BLE001
                registro.exception("no se pudo avisar la entrega vencida %s",
                                   fila.id)

        def por_correo(persona, lengua,
                       destinatario=m.Destinatario.COLABORADOR):
            if not persona or not persona.correo:
                return
            db.add(m.Notificacion(
                servicio_id=fila.servicio_id,
                destinatario=destinatario,
                canal=m.Canal.CORREO, correo=persona.correo, idioma=lengua,
                asunto=ta.t(lengua, "ent_venc_asunto", **datos)[:200],
                cuerpo=ta.t(lengua, "ent_venc_cuerpo", **datos)[:2000],
                datos=correo_html.guardar_datos([
                    (ta.t(lengua, "enc_servicio"), folio),
                    (ta.t(lengua, "ent_unidad"), placa),
                    (ta.t(lengua, "ent_quien"), quien,
                     fila.persona.telefono if fila.persona else None),
                    (ta.t(lengua, "cie_vence"),
                     f"{fila.vence_en:%d/%m/%Y %H:%M}"),
                    (ta.t(lengua, "cie_que_hacer"),
                     ta.t(lengua, "ent_venc_que_hacer"))]),
                enlace_seguimiento=f"/consola/#/servicio/{fila.servicio_id}"))

        al_telefono(fila.persona_id, "entrega_vencida_titulo",
                    "entrega_vencida_cuerpo")
        consultor = (db.get(m.Persona, servicio.consultor_id)
                     if servicio and servicio.consultor_id else None)
        if consultor:
            por_correo(consultor, ta.idioma_de(db, servicio,
                                               m.Destinatario.CONSULTOR),
                       m.Destinatario.CONSULTOR)
            al_telefono(consultor.id, "entrega_vencida_of_titulo",
                        "entrega_vencida_of_cuerpo")
        for director in motor_cierre.directores_de_operaciones(
                db, servicio.pais_id if servicio else None):
            if consultor and director.id == consultor.id:
                continue
            pais = (db.get(m.Pais, director.plaza.pais_id)
                    if director.plaza else None)
            por_correo(director, pais.idioma if pais else "es")
            al_telefono(director.id, "entrega_vencida_of_titulo",
                        "entrega_vencida_of_cuerpo")
        avisadas.append(placa)
    db.commit()
    return avisadas

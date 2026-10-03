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
    """Por la unidad responde quien va al volante (seccion 132, decision
    17 de Salvador): la misma regla que la gasolina y que la central
    (`viaticos.al_volante`): el conductor a bordo de esa unidad, y si
    nadie va de conductor, quien vaya en ella. Antes era el que traia
    la unidad asignada por nombre, y con una sola unidad --donde nadie
    la trae asignada-- caia en quien marco el fin, que suele ser el
    agente y no quien maneja. Sin nadie a bordo, quien marco el fin."""
    from app import viaticos
    conductor = viaticos.al_volante(jornada, vehiculo_id)
    if conductor is not None:
        return conductor
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


def al_reabrir(db: Session, jornada: m.Jornada) -> int:
    """Las abiertas que nacieron con el fin de ese dia se van cuando el
    dia se reabre (seccion 128). Solo las abiertas: la que ya se cerro con
    su revision o sin ella se queda."""
    filas = (db.query(m.EntregaPendiente)
             .filter(m.EntregaPendiente.jornada_id == jornada.id,
                     m.EntregaPendiente.cerrada_en.is_(None)).all())
    for fila in filas:
        db.delete(fila)
    if filas:
        db.flush()
    return len(filas)


def al_seguir_la_unidad(db: Session, servicio_id: int) -> int:
    """La abierta de una unidad que vuelve a salir se va (seccion 128).

    Nace cuando el ultimo dia que habia se cierra sin un dia despues
    --el mes que sigue no estaba abierto porque el proceso no corrio-- y
    la unidad en realidad no dejo el servicio: al abrir el mes la
    camioneta vuelve a tener dias, y reclamarla como "sin entregar"
    seria pedir fotos de una entrega que nunca paso. Solo las abiertas,
    igual que al reabrir: la que ya se cerro con su revision se queda."""
    filas = (db.query(m.EntregaPendiente)
             .filter(m.EntregaPendiente.servicio_id == servicio_id,
                     m.EntregaPendiente.cerrada_en.is_(None)).all())
    idas = 0
    for fila in filas:
        if fila.jornada is not None and revision._sigue_manana(
                db, fila.jornada, fila.vehiculo_id):
            db.delete(fila)
            idas += 1
    if idas:
        db.flush()
    return idas


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
        # Eventual o implantado (seccion 128): la central y el correo
        # llevan a la pantalla que es.
        "tipo": (servicio.tipo.value if servicio and servicio.tipo else None),
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


def suyas_del_servicio(db: Session, servicio_id: int, persona_id: int,
                       ahora: datetime) -> list[dict]:
    """Las abiertas de ese servicio por las que responde esa persona
    (seccion 128): lo que su app le ensena al cerrar el dia, aunque las
    haya abierto el fin de otro del equipo."""
    salida = []
    for fila in _mias(db, persona_id):
        if fila.servicio_id != servicio_id:
            continue
        ficha = _ficha(fila, ahora)
        ficha["sin_recepcion"] = not revision._hecha(
            db, fila.servicio_id, fila.vehiculo_id, m.TipoRevision.RECIBE)
        salida.append(ficha)
    return salida


def observaciones(db: Session, servicio_id: int, ahora: datetime | None = None,
                  anio: int | None = None, mes: int | None = None) -> list[dict]:
    """Lo que el revisor del cierre dice de las entregas (seccion 107):
    grave mientras una siga abierta --el cierre no sale a finanzas con
    una camioneta de la que nadie sabe como volvio--, e informativo la que
    se dio por entregada sin revision, con quien y por que. El eventual
    las mira todas; el mes del implantado (seccion 128, hallazgo r8-03),
    las de los dias de ese mes: antes el mes no las reclamaba y el
    renglon se quedaba en la central para siempre."""
    from app.revisor import GRAVE, INFO

    filas = (db.query(m.EntregaPendiente)
             .filter_by(servicio_id=servicio_id)
             .order_by(m.EntregaPendiente.id).all())
    if anio is not None and mes is not None:
        filas = [f for f in filas if f.jornada is not None
                 and (f.jornada.fecha.year, f.jornada.fecha.month) == (anio, mes)]
    if not filas:
        return []
    momento = reloj.ahora_del_servicio(db, filas[0].servicio, ahora)
    salida = []
    for pendiente in (_ficha(f, momento) for f in filas):
        if pendiente["cerrada_en"] is None:
            salida.append({
                "nivel": GRAVE, "asunto": "Unidad sin entregar",
                "clave": "entrega_pendiente",
                "datos": {"placa": pendiente["placa"],
                          "persona": pendiente["persona"],
                          "limite": pendiente["limite"],
                          "vencido": pendiente["vencido"],
                          "entrega_id": pendiente["entrega_id"]},
                "mensaje": (f"La unidad {pendiente['placa']} salio del "
                            f"servicio y no tiene su revision de entrega "
                            f"(responde {pendiente['persona']})"),
                "accion": ("Que la entregue con las cinco fotos desde su "
                           "app. Si ya no se puede, registrala como "
                           "entregada sin revision, con la razon, desde la "
                           "revision de la unidad en esta ficha.")})
        elif pendiente["sin_revision"]:
            salida.append({
                "nivel": INFO, "asunto": "Entregada sin revision",
                "clave": "entrega_sin_revision",
                "datos": {"placa": pendiente["placa"],
                          "quien": pendiente["justificada_por"],
                          "justificacion": pendiente["justificacion"]},
                "mensaje": (f"La unidad {pendiente['placa']} se dio por "
                            f"entregada sin revision"
                            f" ({pendiente['justificada_por']}): "
                            f"{pendiente['justificacion']}"),
                "accion": "No hay fotos de como volvio; queda escrito quien "
                          "lo decidio y por que."})
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


def pantalla_de_consola(servicio: m.Servicio | None, servicio_id: int) -> str:
    """La ficha del servicio en la consola, segun lo que es (seccion
    128): el implantado tiene la suya; antes el correo y el aviso de la
    entrega vencida llevaban siempre a la del eventual."""
    if servicio is not None and servicio.tipo == m.TipoServicio.IMPLANTADO:
        return f"/consola/#/implantado/{servicio_id}"
    return f"/consola/#/servicio/{servicio_id}"


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
                enlace_seguimiento=pantalla_de_consola(servicio, fila.servicio_id)))

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

"""Las horas extra: desde cuando corren, cuantas son y quien las corrige
(seccion 65).

Decisiones de Salvador, 24 de septiembre:

  - Las horas del dia corren desde la presentacion, o desde el meet and
    greet si fue antes. Si el ejecutivo llega tarde, la espera cuenta: el
    equipo estaba ahi a la hora que se contrato. Si arranca antes, las
    horas corren desde que arranco, y esa hora de mas se cobra y se paga.
  - Hora o fraccion, por minutos completos: un minuto de mas ya es una
    hora; lo que se ve como 19:00 no genera nada.
  - La unidad no cobra hora extra; solo el personal.
  - El consultor corrige las horas de un dia de su servicio, con motivo,
    hasta su visto bueno. La hora original se queda guardada con quien
    la cambio y por que, y el visto bueno se lo dice a finanzas.

Aqui vive la regla una sola vez. Antes el calculo estaba en `cierre` y
el aviso preventivo, la central y el panorama median cada uno contra el
fin programado por su lado: el dia que la regla cambio, cambiaba en
cuatro lugares o en ninguno.
"""
import math
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import reloj

# Lo mismo que se le exige a un ajuste de hito o a un cierre a mano:
# "ok" no explica nada dentro de tres meses.
MINIMO_MOTIVO = 10
# El mismo tope que el meet and greet puesto a mano: un arranque tres
# horas antes de la presentacion no es de este servicio, es un dedazo.
HORAS_ANTES_DEL_INICIO = 3
# Y un dia de mas de veinticuatro horas tampoco.
HORAS_MAXIMAS_DEL_DIA = 24

# Con el visto bueno la factura salio, o esta por salir, con esas horas.
CON_VISTO_BUENO = (m.EstatusCierre.EN_REVISION_IA,
                   m.EstatusCierre.ENVIADO_FINANZAS,
                   m.EstatusCierre.APROBADO, m.EstatusCierre.FACTURADO)

INICIO, FIN = "inicio", "fin"


# ---------------------------------------------------------------- la regla

def inicio_de_las_horas(jornada: m.Jornada) -> datetime | None:
    """Desde cuando corren las horas del dia: la presentacion, o el
    meet and greet si fue antes."""
    programado = jornada.inicio_programado
    real = jornada.inicio_real
    if real is not None and (programado is None or real < programado):
        return real
    return programado


def limite(jornada: m.Jornada) -> datetime | None:
    """Cuando se cumplen las horas contratadas del dia.

    Se mueve desde el fin programado y no se vuelve a sumar la modalidad:
    si el catalogo cambia sus horas, los dias que ya existian se quedan
    con las que se contrataron.
    """
    fin = jornada.fin_programado
    if fin is None:
        return None
    inicio = inicio_de_las_horas(jornada)
    if inicio is None or jornada.inicio_programado is None:
        return fin
    return fin - (jornada.inicio_programado - inicio)


def aplica(jornada: m.Jornada) -> bool:
    """Solo el dia completo genera horas extra; medio dia y traslado no."""
    return bool(jornada.modalidad and jornada.modalidad.aplica_horas_extra)


def minutos_de_mas(jornada: m.Jornada, momento: datetime) -> int:
    """Minutos completos entre el limite y `momento`. Negativo: faltan."""
    tope = limite(jornada)
    if tope is None or momento is None:
        return 0
    return int((momento - tope).total_seconds() // 60)


def de_minutos(minutos: int) -> int:
    """Hora o fraccion: un minuto ya es una hora."""
    return math.ceil(minutos / 60) if minutos > 0 else 0


def horas(jornada: m.Jornada) -> int:
    """Las horas extra del dia: las que se cobran y se pagan."""
    if not aplica(jornada) or not jornada.fin_real:
        return 0
    return de_minutos(minutos_de_mas(jornada, jornada.fin_real))


# ---------------------------------------------------------------- candados

def visto_bueno_dado(db: Session, jornada: m.Jornada) -> bool:
    """Si el servicio de ese dia --o su mes, en el implantado-- ya tiene
    visto bueno."""
    servicio = jornada.equipo.servicio
    if servicio.tipo == m.TipoServicio.EVENTUAL:
        cierre = (db.query(m.Cierre)
                  .filter_by(servicio_id=servicio.id, contrato_id=None)
                  .first())
        return bool(cierre and (cierre.facturado_en
                                or cierre.estatus in CON_VISTO_BUENO))
    from app import cierre_mes
    return cierre_mes.con_visto_bueno(db, cierre_mes.contrato_de(db, jornada))


def candado_del_visto_bueno(db: Session, jornada: m.Jornada, que: str):
    """Con el visto bueno dado, las horas del dia ya no se mueven.

    Reabrir el dia ya tenia este candado; ajustar la marca no, y la
    factura se iba a Odoo con unas horas y el sistema se quedaba con
    otras.
    """
    if visto_bueno_dado(db, jornada):
        raise HTTPException(409, {
            "mensaje": f"El servicio ya tiene visto bueno: {que}",
            "que_hacer": ("Lo que cambie de ese dia se corrige con finanzas: "
                          "la factura ya salio, o esta por salir, con esas "
                          "horas.")})


def ya_arranco(db: Session, jornada: m.Jornada) -> bool:
    """Si el equipo ya llego al punto: desde ahi el dia tiene horas
    reales y su hora programada ya no se mueve."""
    if jornada.estatus in (*m.ARRANCADAS, m.EstatusJornada.TERMINADA):
        return True
    return (db.query(m.Hito.id)
            .filter(m.Hito.jornada_id == jornada.id,
                    m.Hito.anulado_en.is_(None)).first()) is not None


def candado_del_arranque(db: Session, jornada: m.Jornada):
    """La hora, la fecha y la modalidad de un dia que ya arranco no se
    cambian desde la tabla de dias, el vuelo ni la hora de manana.

    Cambiarlas despues movia las horas extra --y la puntualidad del
    equipo-- sin motivo y sin firma. Si las horas quedaron mal, se
    corrigen en el panel del dia.
    """
    if ya_arranco(db, jornada):
        raise HTTPException(409, {
            "mensaje": (f"El dia {jornada.fecha:%d/%m} ya arranco: su hora, "
                        "su fecha y su modalidad ya no se cambian"),
            "que_hacer": ("Si las horas de ese dia quedaron mal, corrigelas "
                          "en el panel del dia, con el motivo.")})


# ---------------------------------------------------------------- corregir

def _marcas(db: Session, jornada: m.Jornada, campo: str) -> list:
    """Las marcas de la calle de esa hora, sin las anuladas, en orden."""
    tipo = (m.TipoHito.CONTACTO_EJECUTIVO if campo == INICIO
            else m.TipoHito.FIN_SERVICIO)
    return (db.query(m.Hito)
            .filter(m.Hito.jornada_id == jornada.id, m.Hito.tipo == tipo,
                    m.Hito.anulado_en.is_(None))
            .order_by(m.Hito.marcado_en, m.Hito.id).all())


def recalcular(db: Session, jornada: m.Jornada, campo: str):
    """La hora del dia que sale de las marcas: el primer meet and greet o
    el ultimo fin. Sin marcas se queda la que habia --un dia cerrado a
    mano no tiene de donde sacarla--."""
    marcas = _marcas(db, jornada, campo)
    if not marcas:
        return
    if campo == INICIO:
        jornada.inicio_real = marcas[0].marcado_en
    else:
        jornada.fin_real = marcas[-1].marcado_en


def anotar(db: Session, jornada: m.Jornada, campo: str,
           antes: datetime | None, despues: datetime,
           persona_id: int | None, motivo: str):
    """El renglon de la correccion. Tambien lo deja el ajuste de la
    central en la bitacora, para que las dos puertas se lean igual."""
    db.add(m.CorreccionHoras(jornada_id=jornada.id, campo=campo,
                             antes=antes, despues=despues,
                             persona_id=persona_id, motivo=motivo))


def _mover(db: Session, jornada: m.Jornada, campo: str, nuevo: datetime,
           quien: m.Usuario, motivo: str, valida: bool):
    """Pone la hora del dia y corrige las marcas que la contradicen.

    La marca que la daba --el primer meet and greet, el ultimo fin-- se
    mueve a la hora nueva. Y si alguien mas del equipo marco un fin
    despues de esa hora, o un meet and greet antes, tambien: si el dia
    termino a las 20:50 nadie lo cerro a las 23:10. Cada marca guarda su
    hora de la calle en `marcado_original`.
    """
    actual = jornada.inicio_real if campo == INICIO else jornada.fin_real
    marcas = _marcas(db, jornada, campo)
    if marcas:
        la_que_manda = marcas[0] if campo == INICIO else marcas[-1]
        for marca in marcas:
            contradice = (marca.marcado_en < nuevo if campo == INICIO
                          else marca.marcado_en > nuevo)
            if marca is not la_que_manda and not contradice:
                continue
            if marca.marcado_original is None:
                marca.marcado_original = marca.marcado_en
            marca.marcado_en = nuevo
            marca.ajustado_por_id = quien.persona_id
            marca.justificacion_ajuste = motivo
            # Validar una marca que la central mando a revisar es de la
            # central. Si la corrige el consultor, la marca sigue
            # esperando a que la central la vea.
            if valida:
                marca.requiere_revision = False
    if campo == INICIO:
        jornada.inicio_real = nuevo
    else:
        jornada.fin_real = nuevo
    anotar(db, jornada, campo, actual, nuevo, quien.persona_id, motivo)


def corregir(db: Session, jornada: m.Jornada, quien: m.Usuario,
             inicio: datetime | None, fin: datetime | None,
             justificacion: str, valida: bool = False,
             ahora: datetime | None = None) -> dict:
    """Corrige la hora de arranque con el ejecutivo o la de termino.

    `valida` dice si quien corrige es la central: solo entonces la marca
    que estaba en revision queda revisada.
    """
    motivo = (justificacion or "").strip()
    if len(motivo) < MINIMO_MOTIVO:
        raise HTTPException(400, {
            "mensaje": "Falta decir por que se corrigen las horas",
            "que_hacer": (f"Escribe al menos {MINIMO_MOTIVO} letras. Es lo "
                          "que finanzas lee en el visto bueno y lo unico que "
                          "va a explicar este cambio dentro de tres meses.")})

    if jornada.estatus == m.EstatusJornada.CANCELADA:
        raise HTTPException(409, {
            "mensaje": "Ese dia esta cancelado",
            "que_hacer": "Un dia cancelado no tiene horas: no se trabajo."})
    if jornada.estatus != m.EstatusJornada.TERMINADA or not jornada.fin_real:
        raise HTTPException(409, {
            "mensaje": "Ese dia todavia no termina",
            "que_hacer": ("Las horas se corrigen cuando el dia ya termino. "
                          "Mientras corre, una marca mal puesta la corrige "
                          "la central en la bitacora.")})
    candado_del_visto_bueno(db, jornada, "sus horas ya no se corrigen aqui")

    ahora = reloj.ahora_de_la_jornada(db, jornada, ahora)
    # Una hora con zona se dice en la hora de alla, como todo el sistema.
    if inicio is not None and inicio.tzinfo is not None:
        inicio = reloj.ahora_de_la_jornada(db, jornada, inicio)
    if fin is not None and fin.tzinfo is not None:
        fin = reloj.ahora_de_la_jornada(db, jornada, fin)
    inicio = inicio.replace(microsecond=0) if inicio else None
    fin = fin.replace(microsecond=0) if fin else None
    cambia_inicio = inicio is not None and inicio != jornada.inicio_real
    cambia_fin = fin is not None and fin != jornada.fin_real
    if not (cambia_inicio or cambia_fin):
        raise HTTPException(400, {
            "mensaje": "No hay nada que corregir",
            "que_hacer": "Esas son las horas que ya tiene el dia."})

    nuevo_inicio = inicio if cambia_inicio else jornada.inicio_real
    nuevo_fin = fin if cambia_fin else jornada.fin_real
    if nuevo_fin > ahora:
        raise HTTPException(409, {
            "mensaje": "Esa hora de termino todavia no llega",
            "que_hacer": "Un dia no termina a una hora que aun no ocurre."})
    arranque = nuevo_inicio or jornada.inicio_programado
    if nuevo_fin <= arranque:
        raise HTTPException(409, {
            "mensaje": "El dia no puede terminar antes de arrancar",
            "que_hacer": (f"Arranco a las {arranque:%H:%M}: la hora de "
                          "termino tiene que ser despues.")})
    if nuevo_inicio is not None:
        if nuevo_inicio < (jornada.inicio_programado
                           - timedelta(hours=HORAS_ANTES_DEL_INICIO)):
            raise HTTPException(409, {
                "mensaje": "Esa hora de arranque queda demasiado antes",
                "que_hacer": (f"El dia se presentaba a las "
                              f"{jornada.inicio_programado:%H:%M}. Mas de "
                              f"{HORAS_ANTES_DEL_INICIO} horas antes no es de "
                              "este servicio.")})
    base = min(x for x in (nuevo_inicio, jornada.inicio_programado)
               if x is not None)
    if nuevo_fin - base > timedelta(hours=HORAS_MAXIMAS_DEL_DIA):
        raise HTTPException(409, {
            "mensaje": "Ese dia pasaria de 24 horas",
            "que_hacer": "Revisa la fecha de la hora de termino."})

    antes = horas(jornada)
    if cambia_inicio:
        _mover(db, jornada, INICIO, nuevo_inicio, quien, motivo, valida)
    if cambia_fin:
        _mover(db, jornada, FIN, nuevo_fin, quien, motivo, valida)
    db.flush()
    return {"resultado": "horas corregidas", "jornada_id": jornada.id,
            "fecha": jornada.fecha.isoformat(),
            "horas_extra_antes": antes, "horas_extra": horas(jornada)}


# ---------------------------------------------------------------- el panel

def _de_alla(db: Session, instante: datetime | None, jornada: m.Jornada):
    """Un instante con zona, en la hora de pared del servicio."""
    if instante is None or instante.tzinfo is None:
        return instante
    pais_id = reloj.pais_de_la_jornada(jornada)
    return reloj.ahora_en(db.get(m.Pais, pais_id) if pais_id else None,
                          instante)


def correcciones(db: Session, jornada_ids: list[int]) -> list:
    if not jornada_ids:
        return []
    return (db.query(m.CorreccionHoras)
            .filter(m.CorreccionHoras.jornada_id.in_(jornada_ids))
            .order_by(m.CorreccionHoras.creado_en, m.CorreccionHoras.id)
            .all())


def del_dia(db: Session, jornada: m.Jornada,
            ahora: datetime | None = None) -> dict:
    """Lo que el panel del dia dice de sus horas: lo programado, desde
    cuando corren, a que hora termino, cuantas extra y quien las corrigio.
    """
    iso = lambda x: x.isoformat() if x else None  # noqa: E731
    ahora = reloj.ahora_de_la_jornada(db, jornada, ahora)
    tope = limite(jornada)
    corre = jornada.estatus in m.ARRANCADAS
    en_extra = (minutos_de_mas(jornada, ahora)
                if corre and aplica(jornada) else None)
    horas_contratadas = (float(jornada.modalidad.horas)
                         if jornada.modalidad else None)
    return {
        "aplica": aplica(jornada),
        "presentacion": iso(jornada.inicio_programado),
        "fin_programado": iso(jornada.fin_programado),
        "horas_contratadas": horas_contratadas,
        "con_el_ejecutivo": iso(jornada.inicio_real),
        "adelantado": (jornada.inicio_real is not None
                       and jornada.inicio_programado is not None
                       and jornada.inicio_real < jornada.inicio_programado),
        "corren_hasta": iso(tope),
        "termino": iso(jornada.fin_real),
        "horas_extra": horas(jornada),
        "en_curso": corre,
        "minutos_en_extra": en_extra if en_extra and en_extra > 0 else None,
        "correcciones": [{
            "campo": c.campo, "antes": iso(c.antes), "despues": iso(c.despues),
            "quien": c.persona.nombre if c.persona else None,
            "motivo": c.motivo,
            "en": iso(_de_alla(db, c.creado_en, jornada)),
        } for c in correcciones(db, [jornada.id])],
    }


# ---------------------------------------------------------------- el visto bueno

def _dia(fecha) -> str:
    return f"{fecha:%d/%m}"


def observaciones(db: Session, jornadas: list, por_dia: list[dict],
                  sin_precio: list[dict], del_mes: bool = False) -> list[dict]:
    """Lo que el visto bueno dice de las horas extra, en horas y no solo
    en dinero: cuantas fueron cada dia y por que, quien corrigio horas y
    las que no se van a cobrar porque falta su precio.

    Van con su clave y sus datos para que la consola las diga en su
    idioma; el mensaje en espanol es el que lee finanzas y el que queda
    si alguien pide la revision cruda.
    """
    salida = []
    if del_mes and por_dia:
        # En el mes pueden ser treinta dias: un renglon con todos.
        total = sum(d["horas"] for d in por_dia)
        lista = ", ".join(f"{d['fecha'][8:10]}/{d['fecha'][5:7]} {d['horas']} h"
                          for d in por_dia)
        salida.append({
            "nivel": "informativo", "asunto": "Horas extra",
            "mensaje": f"{total} h en {len(por_dia)} dia(s): {lista}",
            "accion": "Se cobran con el precio de hora extra del mes.",
            "clave": "horas_extra_mes",
            "datos": {"horas": total, "dias": len(por_dia), "lista": lista}})
    else:
        for d in por_dia:
            dia = f"{d['fecha'][8:10]}/{d['fecha'][5:7]}"
            mensaje = (f"{dia} {d['equipo'] or ''}: {d['horas']} h, termino a "
                       f"las {d['termino']} y las horas corrian hasta las "
                       f"{d['corren_hasta']}")
            if d["adelantado"]:
                mensaje += (f" (arranco con el ejecutivo a las "
                            f"{d['con_el_ejecutivo']}, antes de la "
                            "presentacion)")
            salida.append({
                "nivel": "informativo", "asunto": "Horas extra",
                "mensaje": mensaje,
                "accion": "Se cobran por tarifa; no requieren justificacion.",
                "clave": "horas_extra",
                "datos": {"fecha": dia, "equipo": d["equipo"] or "",
                          "horas": d["horas"], "termino": d["termino"],
                          "hasta": d["corren_hasta"],
                          "arranco": (d["con_el_ejecutivo"]
                                      if d["adelantado"] else None)}})

    for c in correcciones(db, [j.id for j in jornadas]):
        j = c.jornada
        cual = "arranque" if c.campo == INICIO else "fin"
        antes = f"{c.antes:%H:%M}" if c.antes else "sin hora"
        quien = c.persona.nombre if c.persona else "—"
        cuando = _de_alla(db, c.creado_en, j)
        salida.append({
            "nivel": "revisar", "asunto": "Horas corregidas",
            "mensaje": (f"{_dia(j.fecha)} {j.equipo.alias or ''}: el {cual} "
                        f"paso de {antes} a {c.despues:%H:%M} · {quien}"
                        + (f", {cuando:%d/%m %H:%M}" if cuando else "")
                        + f" · «{c.motivo}»"),
            "accion": "Finanzas lo ve igual al aprobar.",
            "clave": "horas_corregidas",
            "datos": {"fecha": _dia(j.fecha), "equipo": j.equipo.alias or "",
                      "campo": c.campo, "antes": antes,
                      "despues": f"{c.despues:%H:%M}", "quien": quien,
                      "cuando": f"{cuando:%d/%m %H:%M}" if cuando else "",
                      "motivo": c.motivo}})

    for s in sin_precio:
        if del_mes:
            mensaje = (f"{s['horas']} h extra en el mes y los terminos no "
                       "tienen precio de hora extra: no se le van a cobrar "
                       "al cliente")
            dia = ""
        else:
            dia = f"{s['fecha'][8:10]}/{s['fecha'][5:7]}"
            mensaje = (f"{dia} {s.get('descripcion') or ''}: {s['horas']} h "
                       "extra y no hay precio de hora extra: no se le van a "
                       "cobrar al cliente")
        salida.append({
            "nivel": "revisar", "asunto": "Horas extra sin precio",
            "mensaje": mensaje,
            "accion": ("Pide que se cargue el precio de hora extra antes de "
                       "mandarlo."),
            "clave": "horas_sin_precio_mes" if del_mes else "horas_sin_precio",
            "datos": {"fecha": dia, "rol": s.get("descripcion") or "",
                      "horas": s["horas"]}})
    return salida

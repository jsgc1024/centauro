# -*- coding: utf-8 -*-
"""El dinero de una persona en un servicio: un solo bolson.

Se deposita junto --un movimiento por persona, por todos sus dias-- y se
gasta junto (`viaticos.bolson_del_servicio`). Por dentro el viatico
vive dia por dia, que es como el consultor calculo el monto; pero lo
que falta, la revision de sus comprobantes y el cierre son de la
persona. Un ticket de gasolina cargado el lunes cubre lo que se le
deposito para el martes, y cerrar dia por dia pedia que cada dia
cuadrara solo: nunca cuadraba, y el consultor se quedaba sin como
cerrar.

Aqui vive esa cuenta, para las dos pantallas que la usan --el visto
bueno del eventual y el del mes del implantado--, para el comparativo
del cierre y para el bono.

Dos reglas de Salvador (23 sep) viven aqui:

* **Cerrar con descuento** solo despues del plazo de esa persona, y
  solo sobre dinero que ya se le deposito. Antes del plazo todavia
  puede comprobar; y lo que no ha salido del banco no es una deuda.
* **Comprobar a tiempo** (el bono) es haber terminado de comprobar
  antes de su plazo. El cierre con descuento no es a tiempo.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import auditoria
from app import devoluciones
from app import models as m
from app import reloj
from app import viaticos as motor_viaticos

CERO = Decimal("0")

# Ya salio del banco: esta con la persona, o ya se resolvio despues de
# estarlo.
DEPOSITADOS = (m.EstatusViatico.TRANSFERIDO, m.EstatusViatico.EN_COMPROBACION,
               m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO)
# Autorizado, todavia no depositado: existe en el sistema, no en su cuenta.
POR_DEPOSITAR = (m.EstatusViatico.ASIGNADO, m.EstatusViatico.SOLICITADO)
# Lo que ya no es dinero afuera.
RESUELTOS = (m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO,
             m.EstatusViatico.CANCELADO)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _fecha(v: m.AsignacionViatico):
    return v.jornada.fecha if v.jornada else None


def de_la_persona(db: Session, viatico: m.AsignacionViatico) -> list:
    """El bolson al que pertenece ese viatico, dia por dia."""
    return sorted(motor_viaticos.bolson_del_servicio(db, viatico),
                  key=lambda v: (_fecha(v) or datetime.min.date(), v.id))


def agrupar(viaticos: list) -> list[list]:
    """Los viaticos de un servicio --o de un mes-- por persona.

    Quien llama ya escogio el servicio o el mes; aqui solo se junta por
    persona. Los cancelados se quedan fuera: nunca salieron y ya no le
    deben nada a nadie.
    """
    grupos: dict[int, list] = {}
    for v in viaticos:
        if v.estatus == m.EstatusViatico.CANCELADO:
            continue
        grupos.setdefault(v.persona_id, []).append(v)
    for suyos in grupos.values():
        suyos.sort(key=lambda v: (_fecha(v) or datetime.min.date(), v.id))
    return sorted(grupos.values(),
                  key=lambda s: (s[0].persona.nombre if s[0].persona
                                 else "").lower())


def cuenta(suyos: list) -> dict:
    """Los numeros del bolson, en una sola resta.

    Lo que falta es lo depositado menos lo comprobado valido y lo que ya
    regreso: lo autorizado que sigue en finanzas no le cuenta en contra.
    Negativo quiere decir que comprobo de mas: la empresa le debe.
    """
    vivos = [v for v in suyos if v.estatus != m.EstatusViatico.CANCELADO]
    depositado = sum((_d(v.monto_total) for v in vivos
                      if v.estatus in DEPOSITADOS), CERO)
    por_depositar = sum((_d(v.monto_total) for v in vivos
                         if v.estatus in POR_DEPOSITAR), CERO)
    comprobado = sum((_d(v.monto_comprobado) for v in vivos), CERO)
    devuelto = sum((_d(v.monto_devuelto) for v in vivos), CERO)
    en_revision = sum((devoluciones.declarado_pendiente(v) for v in vivos),
                      CERO)
    rechazado = sum((_d(c.monto) for v in vivos for c in v.comprobantes
                     if c.rechazado), CERO)
    descontado = sum((_d(v.monto_descontado) for v in vivos), CERO)
    absorbido = sum((_d(v.monto_absorbido) for v in vivos), CERO)
    sin_revisar = sum(1 for v in vivos for c in v.comprobantes
                      if not c.validado)
    limites = [v.limite_comprobacion for v in vivos if v.limite_comprobacion]
    # Si algun dinero depositado todavia no tiene plazo, el plazo de la
    # persona no ha arrancado: corre al terminar el servicio.
    sin_plazo = any(not v.limite_comprobacion for v in vivos
                    if v.estatus in DEPOSITADOS
                    and v.estatus not in RESUELTOS)
    if not vivos:
        estatus = "sin_dinero"
    elif all(v.estatus in RESUELTOS for v in vivos):
        estatus = ("con_descuento"
                   if any(v.cerrado_con_descuento for v in vivos)
                   else "cerrado")
    else:
        estatus = "abierto"
    motivo = next((v.motivo_cierre for v in vivos
                   if v.cerrado_con_descuento and v.motivo_cierre), None)
    return {
        "depositado": depositado,
        "por_depositar": por_depositar,
        "comprobado": comprobado,
        "devuelto": devuelto,
        "devolucion_en_revision": en_revision,
        "rechazado": rechazado,
        # Lo que ya se mando a descuento o absorbio la empresa tambien
        # esta resuelto: no se vuelve a pedir.
        "falta": depositado - comprobado - devuelto - descontado - absorbido,
        "descontado": descontado,
        "absorbido": absorbido,
        "motivo_cierre": motivo,
        "sin_revisar": sin_revisar,
        # El plazo de la persona. Casi siempre es uno solo --T0 + 24 h--;
        # si hay dos, manda el ultimo: nadie pierde tiempo por el otro.
        "limite": None if sin_plazo or not limites else max(limites),
        "estatus": estatus,
    }


def _moneda(suyos: list) -> str | None:
    return suyos[0].moneda.value if suyos and suyos[0].moneda else None


def _dinero(monto: Decimal, moneda: str | None) -> str:
    return f"${monto:,.2f} {moneda or ''}".strip()


# ------------------------------------------------------------ lo que frena

def que_frena_el_cierre(c: dict, moneda: str | None = None) -> dict | None:
    """Por que todavia no se puede cerrar ese dinero, o None.

    Cerrar es decir "esta persona ya no debe nada y no se le debe
    nada": todo lo depositado quedo comprobado o devuelto, cada ticket
    tiene su revision, y no hay dinero en el camino ni devolucion
    esperando a finanzas.
    """
    if c["estatus"] != "abierto":
        return {"codigo": "cerrado", "mensaje": "Ese dinero ya esta cerrado"}
    if c["por_depositar"] > 0:
        return {
            "codigo": "por_depositar",
            "mensaje": (f"Hay {_dinero(c['por_depositar'], moneda)} "
                        "autorizados que todavia no se depositan"),
            "que_hacer": ("Si ya no aplican, cancelalos en los viaticos del "
                          "equipo; si si, espera a que finanzas los "
                          "deposite.")}
    if c["devolucion_en_revision"] > 0:
        return {
            "codigo": "devolucion",
            "mensaje": (f"Finanzas todavia no confirma una devolucion de "
                        f"{_dinero(c['devolucion_en_revision'], moneda)}"),
            "que_hacer": "Se cierra en cuanto finanzas la vea entrar."}
    if c["sin_revisar"]:
        return {
            "codigo": "sin_revisar",
            "mensaje": f"Hay {c['sin_revisar']} comprobante(s) sin revisar",
            "que_hacer": "Validalos o rechazalos primero."}
    if c["falta"] > 0:
        return {
            "codigo": "falta",
            "mensaje": (f"Le faltan {_dinero(c['falta'], moneda)} por "
                        "comprobar"),
            "que_hacer": ("Cuando venza su plazo, lo que falte se cierra con "
                          "descuento a su nomina.")}
    if c["falta"] < 0:
        return {
            "codigo": "de_mas",
            "mensaje": (f"Comprobo {_dinero(-c['falta'], moneda)} de mas"),
            "que_hacer": ("Si el gasto era del servicio, pide viaticos "
                          "adicionales por la diferencia; si no, rechaza "
                          "el comprobante que no aplica.")}
    return None


def que_frena_el_descuento(c: dict, ahora: datetime,
                           moneda: str | None = None) -> dict | None:
    """Por que todavia no se puede cerrar con descuento, o None.

    Decision de Salvador (23 sep): solo despues del plazo de esa persona
    --antes todavia puede comprobar-- y solo sobre lo que ya se le
    deposito.
    """
    if c["estatus"] != "abierto":
        return {"codigo": "cerrado", "mensaje": "Ese dinero ya esta cerrado"}
    if c["limite"] is None:
        return {"codigo": "sin_plazo",
                "mensaje": "Su plazo para comprobar todavia no arranca",
                "que_hacer": "Corre 24 horas desde que termina el servicio."}
    if ahora < c["limite"]:
        return {"codigo": "en_plazo",
                "mensaje": (f"Todavia esta en plazo: puede comprobar hasta el "
                            f"{c['limite']:%d/%m a las %H:%M}"),
                "que_hacer": "Cuando venza, lo que falte se puede descontar."}
    if c["por_depositar"] > 0:
        return {
            "codigo": "por_depositar",
            "mensaje": (f"Hay {_dinero(c['por_depositar'], moneda)} "
                        "autorizados que todavia no se depositan"),
            "que_hacer": ("Lo que no se deposito no se descuenta: cancelalo "
                          "en los viaticos del equipo, o espera el "
                          "deposito.")}
    if c["devolucion_en_revision"] > 0:
        return {
            "codigo": "devolucion",
            "mensaje": (f"Finanzas todavia no confirma una devolucion de "
                        f"{_dinero(c['devolucion_en_revision'], moneda)}"),
            "que_hacer": "Descontarla ahora seria cobrarle dos veces."}
    if c["sin_revisar"]:
        return {
            "codigo": "sin_revisar",
            "mensaje": f"Hay {c['sin_revisar']} comprobante(s) sin revisar",
            "que_hacer": ("Validalos o rechazalos primero: lo que se descuenta "
                          "sale de lo que no quede comprobado.")}
    if c["falta"] <= 0:
        return {"codigo": "nada", "mensaje": "No hay nada que descontar",
                "que_hacer": "Cierralo sin descuento."}
    return None


# ------------------------------------------------------------ la pantalla

def _puesto(v: m.AsignacionViatico) -> str | None:
    """Con que rol fue: el del primer dia basta para reconocerla."""
    jornada = v.jornada
    for a in (jornada.personal if jornada else []):
        if a.persona_id == v.persona_id and a.rol:
            return a.rol.nombre
    return None


def _comprobante(v: m.AsignacionViatico, c: m.Comprobante) -> dict:
    return {
        "id": c.id, "viatico_id": v.id,
        "fecha": _fecha(v).isoformat() if _fecha(v) else None,
        "concepto": c.concepto.value if c.concepto else None,
        "tipo": c.tipo.value if c.tipo else None,
        "monto": _d(c.monto),
        "descripcion": c.descripcion,
        "validado": bool(c.validado) and not c.rechazado,
        "rechazado": bool(c.rechazado),
        "motivo_rechazo": c.motivo_rechazo,
        "observacion": c.observacion,
        "subido_en": c.subido_en.isoformat() if c.subido_en else None,
        "tiene_imagen": bool(c.imagen),
        # Sin foto porque ya se fue al archivo (seccion 69), que no es lo
        # mismo que un ticket que nunca la trajo.
        "archivada_en": (c.archivado_en.isoformat()
                         if c.archivado_en else None),
    }


def ficha(suyos: list, ahora: datetime) -> dict:
    """Una persona, como la ve el consultor: sus numeros, sus tickets y
    lo que puede hacer con ese dinero."""
    c = cuenta(suyos)
    moneda = _moneda(suyos)
    persona = suyos[0].persona
    frena = que_frena_el_cierre(c, moneda)
    frena_descuento = que_frena_el_descuento(c, ahora, moneda)
    comprobantes = sorted(
        (_comprobante(v, x) for v in suyos for x in v.comprobantes),
        key=lambda x: (x["fecha"] or "", x["subido_en"] or "", x["id"]))
    return {
        "persona_id": suyos[0].persona_id,
        "nombre": persona.nombre if persona else None,
        "puesto": _puesto(suyos[0]),
        "moneda": moneda,
        # Cualquiera de sus viaticos sirve para nombrar el bolson en las
        # acciones: el servidor junta los demas.
        "viatico_id": suyos[0].id,
        **c,
        "limite": c["limite"].isoformat() if c["limite"] else None,
        "vencido": bool(c["limite"] and ahora >= c["limite"]),
        "minutos": (int((c["limite"] - ahora).total_seconds() // 60)
                    if c["limite"] else None),
        "puede_cerrar": frena is None,
        "frena_cierre": frena,
        "puede_descontar": frena_descuento is None,
        "frena_descuento": frena_descuento,
        "comprobantes": comprobantes,
    }


def revision(viaticos: list, ahora: datetime) -> list[dict]:
    """Todas las personas de un servicio --o de un mes--, en orden."""
    return [ficha(suyos, ahora) for suyos in agrupar(viaticos)]


# ------------------------------------------------------------ cerrar

def _servicio(v: m.AsignacionViatico) -> m.Servicio:
    return v.jornada.equipo.servicio


def _ahora(db: Session, v: m.AsignacionViatico,
           ahora: datetime | None = None) -> datetime:
    """El plazo vence a la hora del pais del servicio."""
    return reloj.ahora_de_la_jornada(db, v.jornada, ahora)


def _nombre(v: m.AsignacionViatico) -> str:
    return v.persona.nombre if v.persona else str(v.persona_id)


def cerrar(db: Session, viatico: m.AsignacionViatico, usuario: m.Usuario,
           ahora: datetime | None = None) -> dict:
    """Todo el dinero de esa persona en el servicio quedo resuelto."""
    suyos = de_la_persona(db, viatico)
    c = cuenta(suyos)
    moneda = _moneda(suyos)
    frena = que_frena_el_cierre(c, moneda)
    if frena:
        raise HTTPException(409, frena)

    for v in suyos:
        if v.estatus not in RESUELTOS:
            v.estatus = m.EstatusViatico.CERRADO
            v.cerrado_por_id = usuario.persona_id
    auditoria.registrar(
        db, usuario, _servicio(viatico), "cerrar viaticos",
        f"{_nombre(viatico)}: depositado {c['depositado']}, comprobado "
        f"{c['comprobado']}, devuelto {c['devuelto']}",
        jornada_id=viatico.jornada_id)
    db.commit()
    return {"resultado": "cerrado", "persona_id": viatico.persona_id,
            "depositado": c["depositado"], "comprobado": c["comprobado"],
            "devuelto": c["devuelto"]}


def repartir(suyos: list, descuento: Decimal,
             absorbido: Decimal) -> list[tuple]:
    """Lo que se descuenta y lo que absorbe la empresa, dia por dia.

    Se carga primero a los dias a los que les falta, del primero al
    ultimo, sin pasar de lo que le falta a cada uno. Alcanza siempre: lo
    que les falta a los dias que deben suma por lo menos lo que falta en
    total, porque los dias comprobados de mas solo restan. Y la suma de
    los dias da exactamente lo que escribio el consultor.
    """
    quedan_d, quedan_a = descuento, absorbido
    reparto = []
    for v in suyos:
        if v.estatus not in DEPOSITADOS or v.estatus in RESUELTOS:
            continue
        falta = max(_d(v.monto_total) - _d(v.monto_comprobado)
                    - _d(v.monto_devuelto), CERO)
        d = min(falta, quedan_d)
        quedan_d -= d
        a = min(falta - d, quedan_a)
        quedan_a -= a
        reparto.append((v, d, a))
    return reparto


def cerrar_con_descuento(db: Session, viatico: m.AsignacionViatico,
                         datos, usuario: m.Usuario,
                         ahora: datetime | None = None) -> dict:
    """La persona no comprobo a tiempo: lo que falta va a su nomina.

    El consultor puede decidir que la empresa absorba una parte, pero
    tiene que decir cuanto y por que: por omision se descuenta todo lo
    que falta. Un solo ajuste de nomina por la persona, no uno por dia:
    es un solo dinero y un solo descuento que ella va a ver.
    """
    suyos = de_la_persona(db, viatico)
    c = cuenta(suyos)
    moneda = _moneda(suyos)
    momento = _ahora(db, viatico, ahora)
    frena = que_frena_el_descuento(c, momento, moneda)
    if frena:
        raise HTTPException(409, frena)
    motivo = (datos.motivo or "").strip()
    if len(motivo) < 5:
        raise HTTPException(400, {
            "mensaje": "Escribe por que se descuenta",
            "que_hacer": "Queda escrito en su nomina y en la bitacora."})

    pendiente = c["falta"]
    descuento = (_d(datos.monto_descuento)
                 if datos.monto_descuento is not None else pendiente)
    if descuento < 0 or descuento > pendiente:
        raise HTTPException(409, {
            "mensaje": ("El descuento no puede ser negativo ni mayor a lo "
                        "que falta"),
            "por_cubrir": float(pendiente)})
    absorbido = pendiente - descuento
    if absorbido > 0 and not (datos.motivo_absorcion or "").strip():
        raise HTTPException(409, {
            "mensaje": "Si la empresa absorbe una parte, hay que decir por que",
            "absorbido": float(absorbido)})

    servicio = _servicio(viatico)
    ultimo = None
    for v, d, a in repartir(suyos, descuento, absorbido):
        v.monto_descontado = d
        v.monto_absorbido = a
        if d or a:
            v.cerrado_con_descuento = True
            v.motivo_cierre = motivo[:400]
            if d:
                ultimo = v
    for v in suyos:
        if v.estatus not in RESUELTOS:
            v.estatus = m.EstatusViatico.CERRADO
            v.cerrado_por_id = usuario.persona_id

    if descuento > 0:
        fechas = sorted({_fecha(v) for v in suyos if _fecha(v)})
        dias = (fechas[0].strftime("%d/%m") if len(fechas) == 1 else
                f"{fechas[0]:%d/%m}-{fechas[-1]:%d/%m}") if fechas else ""
        from app import nomina
        db.add(m.AjusteNomina(
            concepto=nomina.AJUSTE_VIATICO,
            persona_id=viatico.persona_id, pais_id=servicio.pais_id,
            servicio_id=servicio.id,
            jornada_id=(ultimo or viatico).jornada_id,
            monto=-descuento, creado_por_id=usuario.persona_id,
            motivo=(f"{servicio.folio} {dias}: viaticos sin comprobar. "
                    f"{motivo}")[:400]))

    auditoria.registrar(
        db, usuario, servicio, "cierre de viaticos con descuento",
        f"{_nombre(viatico)}: descuento {descuento}"
        + (f", absorbido {absorbido} ({datos.motivo_absorcion})"
           if absorbido else "")
        + f": {motivo}", jornada_id=viatico.jornada_id)
    db.commit()
    return {
        "resultado": "cerrado con descuento",
        "persona_id": viatico.persona_id,
        "depositado": c["depositado"],
        "comprobado": c["comprobado"],
        "descontado_al_personal": descuento,
        "absorbido_por_la_empresa": absorbido,
        "nota": ("El descuento entra en el proximo corte semanal de nomina. "
                 "Lo rechazado no se le cobra al cliente."),
    }


# ------------------------------------------------------------ el bono

def termino_de_comprobar(suyos: list, pais: m.Pais | None) -> datetime | None:
    """Cuando dejo de deber: el momento en que lo comprobado valido y lo
    devuelto alcanzaron lo depositado.

    En hora de pared del pais del servicio, para compararlo contra su
    plazo. El ticket guarda un instante absoluto (`subido_en`); la
    devolucion, la hora en que la persona la declaro --lo que hizo
    ella--, y solo cuenta si finanzas la confirmo. None si todavia no
    termina.
    """
    depositado = cuenta(suyos)["depositado"]
    if depositado <= 0:
        return None
    eventos = []
    for v in suyos:
        if v.estatus == m.EstatusViatico.CANCELADO:
            continue
        for c in v.comprobantes:
            if c.rechazado or not c.subido_en:
                continue
            eventos.append((reloj.ahora_en(pais, c.subido_en), _d(c.monto)))
        for x in v.devoluciones:
            if x.estatus != m.EstatusDevolucion.CONFIRMADA:
                continue
            cuando = x.declarada_en or x.confirmada_en
            if cuando:
                eventos.append((cuando, _d(x.monto)))
    llevado = CERO
    for cuando, monto in sorted(eventos, key=lambda e: e[0]):
        llevado += monto
        if llevado >= depositado:
            return cuando
    return None

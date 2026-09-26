# -*- coding: utf-8 -*-
"""Los precios del implantado, de la lista de implantados del cliente
(seccion 80, paso C de los tarifarios desde Odoo).

Hasta aqui un implantado abria su primer mes sin precios: alguien los
capturaba a mano en los terminos del mes, y sin ellos el visto bueno no
pasaba. La lista de implantados del cliente --un campo de su ficha en
Odoo, junto a la de siempre (seccion 77)-- ya los tiene, por dia y por
producto. Aqui se vuelven los terminos del mes, con la plantilla:

  * cada persona, al precio de su rol;
  * el conductor con su unidad, en paquete si la lista lo pacta: un solo
    precio por dia, y esa unidad ya no se cobra aparte;
  * cada unidad, a su precio por dia por los dias de servicio del mes:
    la unidad va por mes, apartada para el cliente aunque un dia no salga;
  * la hora extra del equipo, la suma de la de cada quien: el dia que el
    equipo se queda, se queda cada uno.

El dia adicional lleva el precio del dia: la lista no tiene otro. El
precio fijo por mes no sale de aqui --la lista no trae precio por mes--;
se dice cuanto seria a precios de la lista, de referencia.

Si el cliente no tiene lista de implantados, sale de su lista de siempre,
y se dice. En 12x36 trabaja una de las dos personas cada dia: se cobra
una. Lo que la lista no tiene no se adivina: se dice, y ese precio se
queda como este.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app import cierre as motor_cierre
from app import cotizacion as cot
from app import implantado as motor
from app import models as m
from app.revisor import AVISO

CERO = Decimal("0")
CENTAVO = Decimal("0.01")

# Los precios del mes que salen de la lista, en el orden de la tarjeta.
CAMPOS = ("precio_dia_personal", "precio_dia_adicional", "precio_mes_vehiculo",
          "precio_hora_extra")

SIN_LISTA = "sin_lista"
OTRA_MONEDA = "otra_moneda"

# Como se dicen en el aviso del visto bueno, para quien lo lee por la API.
NOMBRES = {"precio_dia_personal": "personal por dia",
           "precio_dia_adicional": "dia adicional",
           "precio_mes_vehiculo": "vehiculo al mes",
           "precio_hora_extra": "hora extra"}


def _d(valor) -> Decimal | None:
    if valor is None:
        return None
    return Decimal(str(valor)).quantize(CENTAVO)


def lista_del_implantado(db: Session,
                         servicio: m.Servicio) -> tuple[m.Tarifario | None, bool]:
    """(la lista, si es la de implantados). Sin lista de implantados, la de
    siempre: es con la que Odoo le cobraria."""
    cliente = db.get(m.Cliente, servicio.cliente_id)
    if cliente is None:
        return None, False
    if cliente.tarifario_implantado_id:
        return db.get(m.Tarifario, cliente.tarifario_implantado_id), True
    if cliente.tarifario_id:
        return db.get(m.Tarifario, cliente.tarifario_id), False
    return None, False


def del_dia(db: Session, contrato: m.ContratoImplantado) -> list:
    """Quienes trabajan un dia: la plantilla entera; en 12x36, una de las
    dos, que manejan la misma unidad."""
    if motor.turno_del_servicio(db, contrato.servicio_id) == motor.TURNO_12X36:
        return motor.pareja_del_turno(contrato)[:1]
    return sorted(contrato.plantilla, key=lambda f: f.id)


def _unidad_de(db: Session, contrato: m.ContratoImplantado, fila) -> m.Vehiculo | None:
    """La unidad que lleva esa persona. En 12x36 es la del mes, la maneje
    quien la maneje."""
    if fila.vehiculo is not None:
        return fila.vehiculo
    if (motor.turno_del_servicio(db, contrato.servicio_id) == motor.TURNO_12X36
            and len(contrato.unidades) == 1):
        return contrato.unidades[0].vehiculo
    return None


def de_la_lista(db: Session, contrato: m.ContratoImplantado) -> dict:
    """Los terminos del mes segun la lista, renglon por renglon.

    {lista, motivo, renglones, faltan, terminos, completa, dias_base,
    mes_completo}: `motivo` dice por que no hay propuesta (sin lista, o
    una lista en otra moneda que la del pais); `faltan`, lo que la lista
    no tiene; `completa`, si todo lo del dia y de las unidades salio de
    ella. La hora extra que la lista no trae no se cobra: eso no falta.
    """
    salida = {"lista": None, "motivo": None, "renglones": [], "faltan": [],
              "terminos": dict.fromkeys(CAMPOS), "completa": False,
              "dias_base": contrato.dias_base, "mes_completo": None}
    servicio = contrato.servicio
    lista, de_implantados = lista_del_implantado(db, servicio)
    if lista is None:
        salida["motivo"] = SIN_LISTA
        return salida
    salida["lista"] = {"id": lista.id, "nombre": lista.nombre,
                       "de_implantados": de_implantados,
                       "de_odoo": lista.odoo_id is not None,
                       "moneda": lista.moneda.value}
    pais = db.get(m.Pais, servicio.pais_id)
    if pais is not None and lista.moneda != pais.moneda_local:
        # Una lista en dolares para un servicio que se cobra en pesos: la
        # utilidad restaria dolares menos pesos (seccion 77).
        salida["motivo"] = OTRA_MONEDA
        return salida

    modalidad = contrato.modalidad
    paquetes = cot.paquetes_del_tarifario(db, lista.id, contrato.modalidad_id)
    renglones, faltan = salida["renglones"], salida["faltan"]
    en_paquete = set()
    dia, hora_extra = CERO, CERO
    dia_completo, con_hora_extra = True, False

    for fila in del_dia(db, contrato):
        quien = fila.persona.nombre if fila.persona else None
        if not fila.rol_id:
            faltan.append({"que": "rol", "quien": quien, "descripcion": None})
            dia_completo = False
            continue
        rol = fila.rol.nombre if fila.rol else None
        unidad = _unidad_de(db, contrato, fila)
        paquete = None
        if unidad is not None and unidad.id not in en_paquete:
            paquete = next((p for p in paquetes if p.perfil_id == fila.rol_id
                            and p.categoria_id == unidad.categoria_id), None)
        extra = _d(motor_cierre._precio_hora_extra(db, lista.id, fila.rol_id,
                                                   modalidad))
        if paquete is not None:
            en_paquete.add(unidad.id)
            precio = _d(paquete.precio)
            renglones.append({"tipo": "paquete", "quien": quien, "rol": rol,
                              "unidad": unidad.categoria.nombre,
                              "placa": unidad.placa, "precio_dia": precio,
                              "precio_hora_extra": extra})
        else:
            tarifa = (db.query(m.TarifaRecurso)
                      .filter_by(tarifario_id=lista.id, perfil_id=fila.rol_id,
                                 modalidad_id=contrato.modalidad_id).first())
            if tarifa is None:
                faltan.append({"que": "rol", "quien": quien, "descripcion": rol})
                dia_completo = False
                continue
            precio = _d(tarifa.precio)
            renglones.append({"tipo": "recurso", "quien": quien, "rol": rol,
                              "precio_dia": precio, "precio_hora_extra": extra})
        dia += precio
        if extra:
            hora_extra += extra
            con_hora_extra = True

    unidades_completas = True
    vehiculo_mes = CERO if contrato.unidades else None
    for u in sorted(contrato.unidades, key=lambda u: u.id):
        v = u.vehiculo
        if v.id in en_paquete:
            renglones.append({"tipo": "unidad_en_paquete", "placa": v.placa,
                              "unidad": v.categoria.nombre})
            continue
        tarifa = (db.query(m.TarifaVehiculo)
                  .filter_by(tarifario_id=lista.id, categoria_id=v.categoria_id,
                             modalidad_id=contrato.modalidad_id).first())
        if tarifa is None:
            faltan.append({"que": "unidad", "quien": v.placa,
                           "descripcion": v.categoria.nombre})
            unidades_completas = False
            continue
        precio = _d(tarifa.precio)
        mes = (precio * contrato.dias_base).quantize(CENTAVO)
        renglones.append({"tipo": "unidad", "placa": v.placa,
                          "unidad": v.categoria.nombre, "precio_dia": precio,
                          "dias": contrato.dias_base, "precio_mes": mes})
        vehiculo_mes += mes

    # Lo que falta se queda sin precio: una suma a medias cobraria de menos
    # sin que nadie lo viera. Sin precio por dia, el visto bueno no pasa.
    personal = dia if dia_completo and dia else None
    unidades = vehiculo_mes if unidades_completas else None
    salida["terminos"] = {
        "precio_dia_personal": personal,
        "precio_dia_adicional": personal,
        "precio_mes_vehiculo": unidades,
        "precio_hora_extra": hora_extra if con_hora_extra else None,
    }
    salida["completa"] = bool(dia_completo and unidades_completas and personal)
    if salida["completa"]:
        salida["mes_completo"] = (personal * contrato.dias_base
                                  + (unidades or CERO)).quantize(CENTAVO)
    return salida


def diferencias(contrato: m.ContratoImplantado, propuesta: dict) -> list[dict]:
    """En que no son los terminos del mes los de la lista: [{campo, mes,
    lista}]. Lo que la lista no sabe --un rol sin precio-- no se compara:
    eso lo dice `faltan`. Con precio fijo por mes solo cuenta la hora
    extra: lo demas no se usa."""
    if propuesta["lista"] is None or propuesta["motivo"]:
        return []
    campos = (CAMPOS if contrato.esquema == m.EsquemaCotizacionImplantado.POR_DIA
              else ("precio_hora_extra",))
    salida = []
    for campo in campos:
        lista = propuesta["terminos"][campo]
        if lista is None and campo != "precio_hora_extra":
            continue
        mes = _d(getattr(contrato, campo))
        if (mes or CERO) != (lista or CERO):
            salida.append({"campo": campo, "mes": mes, "lista": lista})
    return salida


def sigue_la_lista(contrato: m.ContratoImplantado, propuesta: dict) -> bool:
    """Si el mes va con la lista: cobrado por dia, con todo lo de la lista
    y sin nada distinto."""
    return (contrato.esquema == m.EsquemaCotizacionImplantado.POR_DIA
            and propuesta["completa"]
            and not diferencias(contrato, propuesta))


def aplicar(contrato: m.ContratoImplantado, propuesta: dict) -> list[str]:
    """Pone en el mes los precios de la lista. Lo que la lista no tiene se
    queda como estaba. Devuelve lo que cambio, para la auditoria."""
    cambios = []
    for campo in CAMPOS:
        nuevo = propuesta["terminos"][campo]
        if nuevo is None and campo != "precio_hora_extra":
            continue
        antes = _d(getattr(contrato, campo))
        if antes != nuevo:
            cambios.append(f"{campo}: {antes} -> {nuevo}")
            setattr(contrato, campo, nuevo)
    contrato.precios_de_la_lista = sigue_la_lista(contrato, propuesta)
    return cambios


def al_abrir(db: Session, contrato: m.ContratoImplantado) -> dict:
    """El mes que se abre toma los precios de la lista, si la hay. Se
    llama con la plantilla ya guardada: de ella salen los precios. Lo que
    la lista no tiene se queda como venia."""
    db.flush()
    # La plantilla se guardo fila por fila: la que el contrato tenga en
    # memoria puede ser la de antes.
    db.expire(contrato, ["plantilla", "unidades"])
    propuesta = de_la_lista(db, contrato)
    if propuesta["lista"] is not None and not propuesta["motivo"]:
        aplicar(contrato, propuesta)
    return propuesta


def observaciones(contrato: m.ContratoImplantado, propuesta: dict) -> list[dict]:
    """Lo que el visto bueno del mes le dice a finanzas de la lista. No
    frena: un precio distinto puede ser un acuerdo especial con el
    cliente. Llevan su clave y sus datos para que la consola los diga en
    su idioma, con el dinero en su moneda."""
    if propuesta["lista"] is None or propuesta["motivo"]:
        return []
    lista = propuesta["lista"]
    salida = []

    def monto(valor):
        return "sin precio" if valor is None else str(valor)

    distintos = diferencias(contrato, propuesta)
    if distintos:
        detalle = "; ".join(f"{NOMBRES[d['campo']]}: {monto(d['mes'])} "
                            f"(la lista, {monto(d['lista'])})" for d in distintos)
        salida.append({
            "nivel": AVISO, "asunto": "Precios distintos a los de la lista",
            "clave": "precios_lista",
            "datos": {"lista": lista["nombre"], "moneda": lista["moneda"],
                      "diferencias": distintos},
            "mensaje": (f"Los terminos del mes no son los de la lista "
                        f"{lista['nombre']}: {detalle}"),
            "accion": ("Si es un acuerdo especial con el cliente, se deja asi. "
                       "Si no, «Usar los de la lista» en los terminos del mes.")})
    if propuesta["faltan"]:
        que = ", ".join(f["descripcion"] or f["quien"] or "?"
                        for f in propuesta["faltan"])
        salida.append({
            "nivel": AVISO, "asunto": "La lista no tiene todo",
            "clave": "lista_incompleta",
            "datos": {"lista": lista["nombre"], "que": que},
            "mensaje": f"La lista {lista['nombre']} no tiene precio para: {que}",
            "accion": ("Se agrega en Odoo, o se captura a mano en los terminos "
                       "del mes.")})
    return salida

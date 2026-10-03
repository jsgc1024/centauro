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

Salvo que la lista cobre por mes (seccion 130, decision 12 de Salvador):
el paquete de Amazon Brasil viene de Odoo por «Mes», y la propuesta ya lo
leia asi (seccion 123). Ahora el alta directa lo lee igual: el mes nace
con el esquema de mes completo y el mensual de la lista --el de cada
puesto, cada paquete y cada unidad, tal cual--, el dia adicional es el
mensual de las personas entre los dias de la modalidad, y la hora extra la
del paquete. Antes el mes de Amazon Brasil nacia sin precios, «Usar los de
la lista» borraba la hora extra escrita a mano, y la prefactura tomaba el
producto del dia y no el del paquete.

Si el cliente no tiene lista de implantados, sale de su lista de siempre,
y se dice. En 12x36 trabaja una de las dos personas cada dia: se cobra
una. Lo que la lista no tiene no se adivina: se dice, y ese precio se
queda como este.

Los precios del mes van en la moneda de su lista (seccion 82): una lista
en dolares deja el mes en dolares, con el tipo de cambio que esta puesto
cuando se abre --como el de una cotizacion autorizada--. Solo la lista en
una moneda que Centauro no sabe convertir se queda sin propuesta.
"""
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app import cierre as motor_cierre
from app import cotizacion as cot
from app import implantado as motor
from app import models as m
from app import tipo_cambio
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
           "precio_hora_extra": "hora extra",
           "precio_mes_completo": "mensual",
           "esquema": "esquema",
           "moneda": "moneda"}


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


def modalidad_de_la_lista(db: Session,
                          contrato: m.ContratoImplantado) -> m.Modalidad | None:
    """Con que modalidad se lee la lista del cliente: el dia completo del
    pais. Las listas de Odoo traen precios por full day, medio dia y
    transfer, y el dia del implantado se cobra como el dia completo. El
    contrato apunta a la modalidad `implantado` desde la seccion 105 --la
    de sus horas--, y con ella la lista no tendria ningun precio."""
    return (db.query(m.Modalidad)
            .filter_by(pais_id=contrato.servicio.pais_id,
                       codigo=m.CodigoModalidad.FULL_DAY).first()
            or contrato.modalidad)


def de_la_lista(db: Session, contrato: m.ContratoImplantado) -> dict:
    """Los terminos del mes segun la lista, renglon por renglon.

    {lista, motivo, renglones, faltan, terminos, completa, dias_base,
    mes_completo, moneda_local}: `motivo` dice por que no hay propuesta
    (sin lista, o una lista en una moneda que no se sabe convertir);
    `faltan`, lo que la lista no tiene; `completa`, si todo lo del dia y
    de las unidades salio de ella. La hora extra que la lista no trae no
    se cobra: eso no falta. Los precios, en la moneda de la lista.
    """
    salida = {"lista": None, "motivo": None, "renglones": [], "faltan": [],
              "terminos": dict.fromkeys(CAMPOS), "completa": False,
              "dias_base": contrato.dias_base, "mes_completo": None,
              "moneda_local": None,
              # Si la lista cobra por mes (seccion 130): el mes va con el
              # esquema de mes completo y estos terminos.
              "por_mes": False, "precio_mes_completo": None,
              "dias_del_mensual": None}
    servicio = contrato.servicio
    local = tipo_cambio.local_del_pais(db, servicio.pais_id)
    salida["moneda_local"] = local.value if local else None
    lista, de_implantados = lista_del_implantado(db, servicio)
    if lista is None:
        salida["motivo"] = SIN_LISTA
        return salida
    salida["lista"] = {"id": lista.id, "nombre": lista.nombre,
                       "de_implantados": de_implantados,
                       "de_odoo": lista.odoo_id is not None,
                       "moneda": lista.moneda.value}
    if local is not None and not tipo_cambio.se_puede(lista.moneda, local):
        # Una lista en dolares para un servicio en Brasil: Centauro no
        # convierte de dolares a reales, y la utilidad restaria dolares
        # menos reales (seccion 82). En dolares para Mexico si se lee.
        salida["motivo"] = OTRA_MONEDA
        return salida

    modalidad = modalidad_de_la_lista(db, contrato)
    modalidad_id = modalidad.id if modalidad else contrato.modalidad_id
    # La modalidad con la que la lista guarda lo que cobra al mes (seccion
    # 123): la del implantado del pais. Con un precio ahi, ese renglon va
    # por mes (seccion 130, decision 12), como en la propuesta.
    from app import propuesta as motor_propuesta
    mensual = motor_propuesta.mensual_del_pais(db, servicio.pais_id)
    # Los dias que cubre el mensual: los de la modalidad del mes (22, 26 o
    # 30), como en la propuesta; sin esquema, los dias base del mes.
    base = motor.DIAS_DEL_MENSUAL.get(contrato.dias_servicio) or contrato.dias_base
    paquetes = cot.paquetes_del_tarifario(db, lista.id, modalidad_id)
    paquetes_mes = (cot.paquetes_del_tarifario(db, lista.id, mensual.id)
                    if mensual is not None else [])
    renglones, faltan = salida["renglones"], salida["faltan"]
    en_paquete = set()
    dia, hora_extra = CERO, CERO
    dia_completo, con_hora_extra = True, False
    por_mes = False

    def al_mes(precio_dia):
        return (precio_dia * base).quantize(CENTAVO)

    def al_dia(precio_mes):
        return (precio_mes / base).quantize(CENTAVO, rounding=ROUND_HALF_UP)

    for fila in del_dia(db, contrato):
        quien = fila.persona.nombre if fila.persona else None
        if not fila.rol_id:
            faltan.append({"que": "rol", "quien": quien, "descripcion": None})
            dia_completo = False
            continue
        rol = fila.rol.nombre if fila.rol else None
        unidad = _unidad_de(db, contrato, fila)
        paquete, con = None, modalidad
        if unidad is not None and unidad.id not in en_paquete:
            # El del mes primero; si la lista trae los dos, el del mes.
            paquete = next((p for p in paquetes_mes if p.perfil_id == fila.rol_id
                            and p.categoria_id == unidad.categoria_id), None)
            if paquete is not None:
                con = mensual
            else:
                paquete = next((p for p in paquetes if p.perfil_id == fila.rol_id
                                and p.categoria_id == unidad.categoria_id), None)
        if paquete is not None:
            en_paquete.add(unidad.id)
            es_mes = con is mensual
            precio = _d(paquete.precio)
            extra = _d(motor_cierre._precio_hora_extra(db, lista.id, fila.rol_id,
                                                       con))
            renglones.append({"tipo": "paquete", "quien": quien, "rol": rol,
                              # De que rol y que unidad: con ellos sale el
                              # producto de Odoo de la factura (seccion 117).
                              "perfil_id": fila.rol_id,
                              "categoria_id": unidad.categoria_id,
                              "unidad": unidad.categoria.nombre,
                              "placa": unidad.placa,
                              "precio_dia": al_dia(precio) if es_mes else precio,
                              "precio_mes": precio if es_mes else al_mes(precio),
                              "por_mes": es_mes,
                              "precio_hora_extra": extra})
            por_mes = por_mes or es_mes
            precio_dia = al_dia(precio) if es_mes else precio
        else:
            tarifa, con = None, modalidad
            if mensual is not None:
                tarifa = (db.query(m.TarifaRecurso)
                          .filter_by(tarifario_id=lista.id, perfil_id=fila.rol_id,
                                     modalidad_id=mensual.id).first())
                if tarifa is not None:
                    con = mensual
            if tarifa is None:
                tarifa = (db.query(m.TarifaRecurso)
                          .filter_by(tarifario_id=lista.id, perfil_id=fila.rol_id,
                                     modalidad_id=modalidad_id).first())
            if tarifa is None:
                faltan.append({"que": "rol", "quien": quien, "descripcion": rol})
                dia_completo = False
                continue
            es_mes = con is mensual
            precio = _d(tarifa.precio)
            extra = _d(motor_cierre._precio_hora_extra(db, lista.id, fila.rol_id,
                                                       con))
            renglones.append({"tipo": "recurso", "quien": quien, "rol": rol,
                              "perfil_id": fila.rol_id,
                              "precio_dia": al_dia(precio) if es_mes else precio,
                              "precio_mes": precio if es_mes else al_mes(precio),
                              "por_mes": es_mes,
                              "precio_hora_extra": extra})
            por_mes = por_mes or es_mes
            precio_dia = al_dia(precio) if es_mes else precio
        dia += precio_dia
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
        tarifa, es_mes = None, False
        if mensual is not None:
            tarifa = (db.query(m.TarifaVehiculo)
                      .filter_by(tarifario_id=lista.id, categoria_id=v.categoria_id,
                                 modalidad_id=mensual.id).first())
            es_mes = tarifa is not None
        if tarifa is None:
            tarifa = (db.query(m.TarifaVehiculo)
                      .filter_by(tarifario_id=lista.id, categoria_id=v.categoria_id,
                                 modalidad_id=modalidad_id).first())
        if tarifa is None:
            faltan.append({"que": "unidad", "quien": v.placa,
                           "descripcion": v.categoria.nombre})
            unidades_completas = False
            continue
        precio = _d(tarifa.precio)
        mes = precio if es_mes else (precio * contrato.dias_base).quantize(CENTAVO)
        renglones.append({"tipo": "unidad", "placa": v.placa,
                          "categoria_id": v.categoria_id,
                          "unidad": v.categoria.nombre,
                          "precio_dia": None if es_mes else precio,
                          "por_mes": es_mes,
                          "dias": None if es_mes else contrato.dias_base,
                          "precio_mes": mes})
        por_mes = por_mes or es_mes
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
    salida["por_mes"] = por_mes
    if salida["completa"]:
        if por_mes:
            # El mes completo es la suma de los mensuales, tal cual: el de
            # cada persona o paquete y el de cada unidad.
            de_personas = sum((r["precio_mes"] for r in renglones
                               if r["tipo"] in ("recurso", "paquete")), CERO)
            salida["mes_completo"] = (de_personas + (unidades or CERO)).quantize(CENTAVO)
            salida["precio_mes_completo"] = salida["mes_completo"]
            salida["dias_del_mensual"] = base
        else:
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
    if propuesta.get("por_mes"):
        # La lista cobra por mes (seccion 130): lo que cuenta es el
        # mensual, el dia adicional y la hora extra; el esquema tambien.
        campos = ("precio_mes_completo", "precio_dia_adicional",
                  "precio_hora_extra")
    else:
        campos = (CAMPOS if contrato.esquema == m.EsquemaCotizacionImplantado.POR_DIA
                  else ("precio_hora_extra",))
    salida = []
    if (propuesta.get("por_mes") and propuesta["completa"]
            and contrato.esquema != m.EsquemaCotizacionImplantado.MES_COMPLETO):
        salida.append({"campo": "esquema", "mes": contrato.esquema.value,
                       "lista": m.EsquemaCotizacionImplantado.MES_COMPLETO.value})
    # Unos precios en pesos no son los de una lista en dolares aunque
    # digan el mismo numero (seccion 82).
    moneda_mes = contrato.moneda.value if contrato.moneda else propuesta.get(
        "moneda_local")
    if moneda_mes and moneda_mes != propuesta["lista"]["moneda"]:
        salida.append({"campo": "moneda", "mes": moneda_mes,
                       "lista": propuesta["lista"]["moneda"]})
    for campo in campos:
        lista = (propuesta["precio_mes_completo"] if campo == "precio_mes_completo"
                 else propuesta["terminos"][campo])
        if lista is None and campo != "precio_hora_extra":
            continue
        mes = _d(getattr(contrato, campo))
        if (mes or CERO) != (lista or CERO):
            salida.append({"campo": campo, "mes": mes, "lista": lista})
    return salida


def sigue_la_lista(contrato: m.ContratoImplantado, propuesta: dict) -> bool:
    """Si el mes va con la lista: cobrado por dia, con todo lo de la lista
    y sin nada distinto."""
    esquema = (m.EsquemaCotizacionImplantado.MES_COMPLETO
               if propuesta.get("por_mes")
               else m.EsquemaCotizacionImplantado.POR_DIA)
    return (contrato.esquema == esquema
            and propuesta["completa"]
            and not diferencias(contrato, propuesta))


def aplicar(contrato: m.ContratoImplantado, propuesta: dict) -> list[str]:
    """Pone en el mes los precios de la lista, y su moneda. Lo que la
    lista no tiene se queda como estaba, si la moneda no cambia. Devuelve
    lo que cambio, para la auditoria."""
    cambios = []
    # Los precios del mes van en la moneda de la lista (seccion 82). Si el
    # mes cambia de moneda, lo que la lista no trae ya no se queda como
    # estaba --eran pesos y ahora se leerian como dolares--: se borra, y
    # tambien el precio fijo del mes y los gastos a precio alzado. Se
    # capturan de nuevo en la moneda del mes. Su tipo de cambio se vuelve
    # a fijar (`fijar_moneda_del_mes`).
    local = propuesta.get("moneda_local")
    de_la_lista = propuesta["lista"]["moneda"]
    moneda = None if de_la_lista == local else m.Moneda(de_la_lista)
    cambia = contrato.moneda != moneda
    if cambia:
        cambios.append(f"moneda: {contrato.moneda.value if contrato.moneda else local}"
                       f" -> {de_la_lista}")
        contrato.moneda = moneda
        contrato.tipo_cambio = None
        contrato.tipo_cambio_fecha = None
        for campo in ("precio_mes_completo", "gastos_mes"):
            if getattr(contrato, campo) is not None:
                cambios.append(f"{campo}: {_d(getattr(contrato, campo))} -> None")
                setattr(contrato, campo, None)
    for campo in CAMPOS:
        nuevo = propuesta["terminos"][campo]
        if nuevo is None and campo != "precio_hora_extra" and not cambia:
            continue
        antes = _d(getattr(contrato, campo))
        if antes != nuevo:
            cambios.append(f"{campo}: {antes} -> {nuevo}")
            setattr(contrato, campo, nuevo)
    if propuesta.get("por_mes") and propuesta["completa"]:
        # La lista cobra por mes (seccion 130, decision 12): el mes va con
        # el esquema de mes completo, el mensual de la lista y los dias
        # que cubre, como el que nace de una propuesta.
        if contrato.esquema != m.EsquemaCotizacionImplantado.MES_COMPLETO:
            cambios.append(f"esquema: {contrato.esquema.value} -> mes_completo")
            contrato.esquema = m.EsquemaCotizacionImplantado.MES_COMPLETO
        for campo, nuevo in (("precio_mes_completo", propuesta["precio_mes_completo"]),
                             ("dias_del_mensual", propuesta["dias_del_mensual"])):
            antes = getattr(contrato, campo)
            antes = _d(antes) if campo == "precio_mes_completo" else antes
            if antes != nuevo:
                cambios.append(f"{campo}: {antes} -> {nuevo}")
                setattr(contrato, campo, nuevo)
    contrato.precios_de_la_lista = sigue_la_lista(contrato, propuesta)
    return cambios


def fijar_moneda_del_mes(db: Session,
                         contrato: m.ContratoImplantado) -> dict | None:
    """El tipo de cambio de un mes en otra moneda que la del pais: el que
    esta puesto cuando se abre, como el de una cotizacion autorizada, y ya
    no se mueve --con el se calculan la utilidad y la comision del mes--.
    Si entonces no habia ninguno, lo fija el visto bueno. Un mes en la
    moneda del pais no lleva ninguno. None si no hay."""
    local = tipo_cambio.local_del_pais(db, contrato.servicio.pais_id)
    if contrato.moneda is None or contrato.moneda == local:
        contrato.moneda = None
        contrato.tipo_cambio = None
        contrato.tipo_cambio_fecha = None
        return None
    if contrato.tipo_cambio:
        return tipo_cambio.fijo(contrato.tipo_cambio,
                                contrato.tipo_cambio_fecha)
    tc = (tipo_cambio.vigente(db, contrato.moneda, local)
          if tipo_cambio.se_puede(contrato.moneda, local) else None)
    if tc:
        contrato.tipo_cambio = tc["tasa"]
        contrato.tipo_cambio_fecha = tc["fecha"]
    return tc


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
    fijar_moneda_del_mes(db, contrato)
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
                      "moneda_mes": (contrato.moneda.value if contrato.moneda
                                     else propuesta.get("moneda_local")),
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

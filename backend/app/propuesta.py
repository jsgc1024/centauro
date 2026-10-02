# -*- coding: utf-8 -*-
"""La propuesta del implantado (seccion 115).

Salvador, 30 de septiembre: «empezamos implantado. Te mando el ejemplo de
una propuesta. Esta no se llama cotizacion, se llama propuesta». La de
Siemens Energy en Queretaro: un conductor de seguridad bilingue y una
RAV, cada uno con su costo mensual fijo, los gastos de operacion aparte,
la jornada de 14 horas, la hora extra a $400 y el dia de mas a lo que
sale el mensual entre 22.

Sus decisiones del 1 de octubre, una por una:

  1. Folio de Connect, EP/PRO-0001, con su version. El PDF y la pantalla
     dicen propuesta.
  2. Los precios salen de la lista de implantados del cliente (Odoo). Si
     no tiene --Siemens Energy es nueva-- o se pacta otro precio, el
     consultor lo escribe con su motivo y direccion de operaciones lo
     autoriza antes de que se pueda mandar.
  3. «Hay 3 diferentes modalidades. 22 dias (lunes a viernes) mas dias
     adicionales, 26 dias (lunes a sabado) mas dias adicionales o mes
     completo 30 dias al mes con un costo fijo. En estas 3 modalidades
     podria ser mas viaticos o con viaticos incluidos.» El mensual de
     cada puesto es su precio por dia por esos dias y no cambia si el mes
     trae 21 o 23 habiles; el dia de mas es el precio por dia del puesto;
     la unidad va por mes. El primer mes que empieza a medio mes se cobra
     por dia de servicio.
  4. El mensual antes de IVA, el IVA y el mensual con IVA, como la
     cotizacion; el cliente sin IVA se marca.
  5. Cuando el cliente la autoriza nace el implantado en EP implantado,
     con lo pactado y la propuesta adentro. Le falta lo que una propuesta
     no dice: el ejecutivo, el punto fijo y quien va en que unidad.

Como vive. Es una `Cotizacion` de clase «propuesta», con la misma vida
que la del eventual (seccion 114): borrador, enviada --su PDF se guarda
tal como salio--, la version siguiente, rechazada, vencida y autorizada.
En vez de dias lleva lo del mes: sus puestos y unidades
(`PosicionPropuesta`), la modalidad, la jornada, el inicio y el alcance.
Cuando nace el implantado, su primer mes se abre con estos terminos
(`terminos_del_primer_mes`): precio fijo por mes, el dia adicional, la
hora extra y los viaticos como se pactaron.
"""
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from app import accesos, auditoria, auth, reloj, tipo_cambio
from app import cierre as motor_cierre
from app import cotizacion as motor
from app import cotizacion_cliente as cc
from app import implantado as motor_implantado
from app import models as m

E = m.EstatusCotizacion
D = m.DiasServicio
CLASE = motor.PROPUESTA

# Los dias que cubre el mensual en cada modalidad (decision 3): los mismos
# con que se cobra el mes del implantado que nace de ella.
BASE = motor_implantado.DIAS_DEL_MENSUAL

RECURSO, VEHICULO, PAQUETE = "recurso", "vehiculo", "paquete"
TIPOS = (RECURSO, VEHICULO, PAQUETE)
DE_PERSONAL = (RECURSO, PAQUETE)

APARTE, INCLUIDOS = "aparte", "incluidos"

# El precio especial (decision 2).
PEDIDO, AUTORIZADO, RECHAZADO = "pedido", "autorizado", "rechazado"
ESPECIAL = "propuestas.precio_especial"

MAX_POSICIONES = 24
MAX_CANTIDAD = 20
LARGO_DESCRIPCION = 200
LARGO_ALCANCE = 6000
LARGO_NOTA = 400

CENTAVO = Decimal("0.01")
CERO = Decimal("0")

# Los textos de Catalogos → Propuesta al cliente, por pais e idioma, y el
# alcance de cada rol (`alcance:<codigo>`).
CLAVES_DE_TEXTO = ("pro_incluye", "pro_incluye_unidad", "pro_incluidos",
                   "pro_no_incluye", "pro_viaticos", "pro_cliente",
                   "pro_centauro", "pro_aceptacion")
ALCANCE = "alcance:"

# Lo que trae Mexico de nacimiento: los textos de la propuesta de ejemplo
# de Salvador. La migracion b8e1d4f6a9c3 trae la misma copia; una prueba
# cuida que digan lo mismo.
TEXTOS_MEXICO = {
    "pro_incluye": {
        "es": "Personal de seguridad debidamente capacitado, con las "
              "certificaciones y entrenamientos correspondientes.",
        "en": "Security personnel duly trained, with the corresponding "
              "certifications and training.",
        "pt": "Pessoal de segurança devidamente capacitado, com as "
              "certificações e treinamentos correspondentes.",
    },
    "pro_incluye_unidad": {
        "es": "Unidad de nueva generación con monitoreo activo mediante "
              "sistema IVMS y botón de pánico para atención y respuesta "
              "ante cualquier eventualidad.\n"
              "Mantenimiento preventivo de la unidad cada 10,000 km. Si una "
              "reparación puede afectar la operación, la unidad se "
              "reemplaza de inmediato para garantizar la continuidad y la "
              "seguridad del servicio.",
        "en": "Latest-generation vehicle with active monitoring through an "
              "IVMS system and a panic button for response to any event.\n"
              "Preventive maintenance of the vehicle every 10,000 km. If a "
              "repair could affect the operation, the vehicle is replaced "
              "immediately to ensure the continuity and safety of the "
              "service.",
        "pt": "Veículo de nova geração com monitoramento ativo por sistema "
              "IVMS e botão de pânico para atendimento e resposta a "
              "qualquer eventualidade.\n"
              "Manutenção preventiva do veículo a cada 10.000 km. Se um "
              "reparo puder afetar a operação, o veículo é substituído "
              "imediatamente para garantir a continuidade e a segurança do "
              "serviço.",
    },
    "pro_incluidos": {
        "es": "Los gastos de operación del servicio: gasolina, tag, "
              "estacionamientos y alimentos del personal.",
        "en": "The operating expenses of the service: fuel, tolls, parking "
              "and meals for the personnel.",
        "pt": "As despesas operacionais do serviço: combustível, pedágios, "
              "estacionamentos e alimentação do pessoal.",
    },
    "pro_no_incluye": {
        "es": "Los gastos de operación: hospedaje cuando la operación lo "
              "requiera, amenidades cuando sean necesarias para el "
              "servicio, estacionamientos, gasolina y tag.\n"
              "Cualquier otro gasto que pida el cliente o que sea "
              "indispensable para la operación, aprobado antes por el "
              "cliente.",
        "en": "Operating expenses: lodging when the operation requires it, "
              "amenities when needed for the service, parking, fuel and "
              "tolls.\n"
              "Any other expense requested by the client or essential to "
              "the operation, approved in advance by the client.",
        "pt": "As despesas operacionais: hospedagem quando a operação "
              "exigir, amenidades quando forem necessárias para o serviço, "
              "estacionamentos, combustível e pedágios.\n"
              "Qualquer outra despesa solicitada pelo cliente ou "
              "indispensável para a operação, aprovada previamente pelo "
              "cliente.",
    },
    "pro_viaticos": {
        "es": "Los gastos de operación se facturan cada mes, junto con el "
              "servicio y con su desglose. Cada gasto lleva su comprobante: "
              "lo presenta el personal de seguridad y Centauro lo revisa y "
              "lo valida.",
        "en": "Operating expenses are invoiced every month, together with "
              "the service and with their breakdown. Each expense comes "
              "with its receipt: the security personnel submit it and "
              "Centauro reviews and validates it.",
        "pt": "As despesas operacionais são faturadas todo mês, junto com o "
              "serviço e com o seu detalhamento. Cada despesa tem o seu "
              "comprovante: o pessoal de segurança o apresenta e a Centauro "
              "o revisa e valida.",
    },
    "pro_cliente": {
        "es": "Proporcionar itinerario, horarios y puntos de servicio con "
              "anticipación.\n"
              "Reportar cualquier incidente durante el servicio de manera "
              "inmediata.",
        "en": "Provide the itinerary, schedules and service locations in "
              "advance.\n"
              "Report any incident during the service immediately.",
        "pt": "Informar o itinerário, os horários e os pontos de serviço com "
              "antecedência.\n"
              "Comunicar imediatamente qualquer incidente durante o "
              "serviço.",
    },
    "pro_centauro": {
        "es": "Centauro cumple los protocolos de seguridad y "
              "confidencialidad: toda la información relacionada con el "
              "servicio, los pasajeros y la operación se trata como "
              "confidencial.",
        "en": "Centauro complies with its security and confidentiality "
              "protocols: all information related to the service, the "
              "passengers and the operation is treated as confidential.",
        "pt": "A Centauro cumpre os protocolos de segurança e "
              "confidencialidade: todas as informações relacionadas ao "
              "serviço, aos passageiros e à operação são tratadas como "
              "confidenciais.",
    },
    "pro_aceptacion": {
        "es": "Para autorizarla, responda por correo a {correo_consultor} "
              "con copia a luis.pichardo@centauro.lat, indicando el folio "
              "{folio}. Le agradecemos su aceptación con 72 horas de "
              "anticipación al inicio del servicio, para agendar a nuestros "
              "elementos y vehículos.",
        "en": "To approve it, please reply by email to {correo_consultor}, "
              "copying luis.pichardo@centauro.lat, and quote reference "
              "{folio}. We appreciate your approval 72 hours before the "
              "start of the service so we can schedule our personnel and "
              "vehicles.",
        "pt": "Para aprová-la, responda por e-mail para {correo_consultor}, "
              "com cópia para luis.pichardo@centauro.lat, indicando a "
              "referência {folio}. Agradecemos a sua aprovação com 72 horas "
              "de antecedência do início do serviço, para agendarmos nossos "
              "agentes e veículos.",
    },
    "alcance:conductor_seguridad": {
        "es": "El servicio de conductor de seguridad tiene como finalidad "
              "proporcionar traslados seguros, discretos y eficientes al "
              "principal y a su familia, mediante la aplicación de medidas "
              "preventivas orientadas a salvaguardar su integridad física "
              "durante cada desplazamiento.\n\n"
              "El conductor es responsable de operar la unidad asignada con "
              "apego a la normatividad vigente, realizar inspecciones "
              "preventivas del vehículo, planificar las rutas considerando "
              "factores de seguridad y movilidad, y mantener una actitud "
              "profesional, discreta y de absoluta confidencialidad "
              "respecto a la información, los itinerarios y las actividades "
              "del cliente. Asimismo, identifica y reporta oportunamente "
              "cualquier situación de riesgo, aplica los protocolos de "
              "seguridad establecidos por la empresa y mantiene "
              "comunicación con el centro de operaciones o el responsable "
              "del servicio cuando la operación así lo requiera.\n\n"
              "El alcance del servicio se limita exclusivamente a las "
              "funciones inherentes al transporte seguro y la protección "
              "preventiva durante los desplazamientos. En consecuencia, el "
              "conductor no realiza actividades ajenas a su función, como "
              "labores domésticas, asistencia personal, manejo de recursos "
              "económicos del cliente o cualquier otra actividad que no "
              "haya sido previamente acordada y autorizada por escrito como "
              "parte del servicio contratado.",
        "en": "The purpose of the security driver service is to provide "
              "safe, discreet and efficient transportation for the "
              "principal and their family, applying preventive measures "
              "aimed at safeguarding their physical integrity during every "
              "trip.\n\n"
              "The driver is responsible for operating the assigned vehicle "
              "in compliance with current regulations, carrying out "
              "preventive vehicle inspections, planning routes with "
              "security and mobility in mind, and maintaining a "
              "professional, discreet attitude and absolute confidentiality "
              "regarding the client's information, itineraries and "
              "activities. The driver also identifies and promptly reports "
              "any risk situation, applies the company's security protocols "
              "and keeps in contact with the operations center or the "
              "person in charge of the service when the operation requires "
              "it.\n\n"
              "The scope of the service is limited exclusively to the "
              "functions inherent to secure transportation and preventive "
              "protection during trips. Accordingly, the driver does not "
              "perform activities outside their role, such as domestic "
              "chores, personal assistance, handling the client's money or "
              "any other activity not previously agreed and authorized in "
              "writing as part of the contracted service.",
        "pt": "O serviço de motorista de segurança tem como finalidade "
              "oferecer deslocamentos seguros, discretos e eficientes ao "
              "principal e à sua família, com a aplicação de medidas "
              "preventivas voltadas a salvaguardar a sua integridade física "
              "em cada deslocamento.\n\n"
              "O motorista é responsável por operar o veículo designado em "
              "conformidade com a legislação vigente, realizar inspeções "
              "preventivas do veículo, planejar as rotas considerando "
              "fatores de segurança e mobilidade, e manter uma atitude "
              "profissional, discreta e de absoluta confidencialidade em "
              "relação às informações, aos itinerários e às atividades do "
              "cliente. Além disso, identifica e comunica oportunamente "
              "qualquer situação de risco, aplica os protocolos de "
              "segurança da empresa e mantém comunicação com a central de "
              "operações ou com o responsável pelo serviço quando a "
              "operação exigir.\n\n"
              "O escopo do serviço limita-se exclusivamente às funções "
              "inerentes ao transporte seguro e à proteção preventiva "
              "durante os deslocamentos. Assim, o motorista não realiza "
              "atividades alheias à sua função, como tarefas domésticas, "
              "assistência pessoal, manejo de recursos financeiros do "
              "cliente ou qualquer outra atividade que não tenha sido "
              "previamente acordada e autorizada por escrito como parte do "
              "serviço contratado.",
    },
}


def _dinero(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _o_nada(valor) -> Decimal | None:
    return None if valor is None else _dinero(valor)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def nombre_de(cot: m.Cotizacion) -> str:
    """EP/PRO-0001 V2."""
    return cc.nombre_de(cot)


def folio_de(cot: m.Cotizacion) -> str | None:
    return motor.folio_texto(cot.folio, cot.clase)


def base_de(dias_servicio) -> int:
    return BASE[D(dias_servicio)] if dias_servicio else BASE[D.LUNES_VIERNES]


# ------------------------------------------------------------- la lista

def lista_de_implantados(db: Session,
                         cliente: m.Cliente | None) -> m.Tarifario | None:
    """La lista de implantados del cliente en Odoo (seccion 80). La
    propuesta no toma la de siempre: el precio de un dia suelto no es el
    de un mes (decision 2). Sin ella --o sin cliente--, se escribe."""
    if cliente is None or not cliente.tarifario_implantado_id:
        return None
    return db.get(m.Tarifario, cliente.tarifario_implantado_id)


def _modalidad(db: Session, pais_id: int | None) -> m.Modalidad | None:
    """Con que modalidad se lee la lista: el dia completo del pais, como
    el mes del implantado (`implantado_precios.modalidad_de_la_lista`)."""
    if not pais_id:
        return None
    return (db.query(m.Modalidad)
            .filter_by(pais_id=pais_id, codigo=m.CodigoModalidad.FULL_DAY)
            .first())


def mensual_del_pais(db: Session, pais_id: int | None) -> m.Modalidad | None:
    """Con que modalidad guarda la lista lo que cobra al mes (seccion 123):
    la del implantado de su pais. El paquete de Amazon Brasil viene de
    Odoo por «Mes»."""
    if not pais_id:
        return None
    return (db.query(m.Modalidad)
            .filter_by(pais_id=pais_id, codigo=m.CodigoModalidad.IMPLANTADO)
            .first())


def _producto(db: Session, tarifa) -> str | None:
    producto_id = getattr(tarifa, "producto_odoo_id", None)
    if not producto_id:
        return None
    producto = db.get(m.ProductoOdoo, producto_id)
    return producto.nombre if producto else None


def _tarifa(db: Session, lista: m.Tarifario, modalidad: m.Modalidad, tipo: str,
            perfil_id: int | None, categoria_id: int | None):
    """El renglon de la lista para un puesto, una unidad o un paquete en esa
    modalidad. Del paquete, solo el que la lista pacta."""
    if tipo == RECURSO:
        return (db.query(m.TarifaRecurso)
                .filter_by(tarifario_id=lista.id, perfil_id=perfil_id,
                           modalidad_id=modalidad.id).first())
    if tipo == VEHICULO:
        return (db.query(m.TarifaVehiculo)
                .filter_by(tarifario_id=lista.id, categoria_id=categoria_id,
                           modalidad_id=modalidad.id).first())
    if tipo == PAQUETE:
        return (motor._pactados(db)
                .filter_by(tarifario_id=lista.id, perfil_id=perfil_id,
                           categoria_id=categoria_id,
                           modalidad_id=modalidad.id).first())
    return None


def _de_la_lista(db: Session, lista: m.Tarifario | None,
                 modalidad: m.Modalidad | None, tipo: str,
                 perfil_id: int | None, categoria_id: int | None) -> dict:
    """{dia, mes, producto, hora_extra} de la lista para un puesto, una
    unidad o un paquete. Lo que la lista no tiene va vacio.

    Lo que la lista cobra al mes (seccion 123) trae `mes` --el mensual,
    tal cual-- y no `dia`; su hora extra es la del mes. Lo demas, su
    precio por dia."""
    salida = {"dia": None, "mes": None, "producto": None, "hora_extra": None}
    if lista is None or modalidad is None:
        return salida
    mensual = mensual_del_pais(db, modalidad.pais_id)
    tarifa, con = None, modalidad
    if mensual is not None:
        tarifa = _tarifa(db, lista, mensual, tipo, perfil_id, categoria_id)
        if tarifa is not None:
            salida["mes"] = _dinero(tarifa.precio)
            con = mensual
    if tarifa is None:
        tarifa = _tarifa(db, lista, modalidad, tipo, perfil_id, categoria_id)
        if tarifa is not None:
            salida["dia"] = _dinero(tarifa.precio)
    if tarifa is not None:
        salida["producto"] = _producto(db, tarifa)
    if tipo in DE_PERSONAL and perfil_id:
        extra = motor_cierre._precio_hora_extra(db, lista.id, perfil_id, con)
        salida["hora_extra"] = _o_nada(extra)
    return salida


def paquetes_de_la_lista(db: Session, lista: m.Tarifario,
                         modalidad: m.Modalidad) -> list:
    """Los paquetes que la lista pacta: los del mes (seccion 123) y los
    del dia, uno por rol y unidad --si la lista trae los dos, el del
    mes--."""
    salida, vistos = [], set()
    mensual = mensual_del_pais(db, modalidad.pais_id)
    for mod in (mensual, modalidad):
        if mod is None:
            continue
        for t in motor.paquetes_del_tarifario(db, lista.id, mod.id):
            if (t.perfil_id, t.categoria_id) in vistos:
                continue
            vistos.add((t.perfil_id, t.categoria_id))
            salida.append(t)
    return salida


def usa_paquetes(lista: m.Tarifario | None, viaticos: str) -> bool:
    """La regla de la cotizacion del eventual (`motor.usa_paquetes`): el
    paquete de una lista cuyos paquetes traen los gastos solo va con los
    viaticos incluidos. Con mas viaticos, el puesto y la unidad van por
    separado, cada uno a su precio sin gastos."""
    return motor.usa_paquetes(
        lista, motor.GASTOS_DENTRO if viaticos == INCLUIDOS
        else motor.GASTOS_COMPROBAR)


def _nombre(perfil, categoria, tipo: str) -> str:
    if tipo == PAQUETE:
        return f"{perfil.nombre} + {categoria.nombre}"
    return perfil.nombre if tipo == RECURSO else categoria.nombre


def _moneda(db: Session, lista: m.Tarifario | None, pais_id: int) -> m.Moneda:
    """La de su lista --dolares, si el cliente paga en dolares (seccion
    82)--; sin lista, la del pais."""
    if lista is not None:
        return lista.moneda
    pais = db.get(m.Pais, pais_id)
    return pais.moneda_local


def horas_del_pais(db: Session, pais_id: int | None) -> Decimal | None:
    modalidad = motor_implantado.modalidad_del_pais(db, pais_id)
    return Decimal(str(modalidad.horas)) if modalidad else None


def lista_info(db: Session, cliente_id: int | None,
               pais_id: int | None) -> dict:
    """Lo que la pantalla necesita al escoger el cliente: su lista de
    implantados --o por que no hay--, todos los roles y unidades con el
    precio por dia de la lista si lo tiene, los paquetes que pacta, la
    jornada del pais, las ciudades, la tasa de IVA y sus contactos."""
    cliente = db.get(m.Cliente, cliente_id) if cliente_id else None
    if cliente_id and cliente is None:
        raise HTTPException(404, f"No existe el cliente {cliente_id}")
    pais_id = cliente.pais_id if cliente else pais_id
    if not pais_id or db.get(m.Pais, pais_id) is None:
        raise HTTPException(400, "Di de qué país es la empresa.")
    lista = lista_de_implantados(db, cliente)
    modalidad = _modalidad(db, pais_id)
    # El precio por dia o, si la lista lo trae por mes (seccion 123), el
    # mensual.
    roles = []
    for p in (db.query(m.PerfilPersonal).filter_by(activo=True)
              .order_by(m.PerfilPersonal.id).all()):
        precio = _de_la_lista(db, lista, modalidad, RECURSO, p.id, None)
        roles.append({"id": p.id, "codigo": p.codigo, "nombre": p.nombre,
                      "precio_dia": _flotante(precio["dia"]),
                      "precio_mes": _flotante(precio["mes"]),
                      "hora_extra": _flotante(precio["hora_extra"]),
                      "producto": precio["producto"]})
    unidades = []
    for c in (db.query(m.CategoriaVehiculo).filter_by(activo=True)
              .order_by(m.CategoriaVehiculo.nombre).all()):
        precio = _de_la_lista(db, lista, modalidad, VEHICULO, None, c.id)
        unidades.append({"id": c.id, "nombre": c.nombre,
                         "precio_dia": _flotante(precio["dia"]),
                         "precio_mes": _flotante(precio["mes"]),
                         "producto": precio["producto"]})
    paquetes = []
    if lista is not None and modalidad is not None:
        for t in paquetes_de_la_lista(db, lista, modalidad):
            precio = _de_la_lista(db, lista, modalidad, PAQUETE, t.perfil_id,
                                  t.categoria_id)
            paquetes.append({"perfil_id": t.perfil_id,
                             "categoria_id": t.categoria_id,
                             "nombre": motor.nombre_del_paquete(t),
                             "precio_dia": _flotante(precio["dia"]),
                             "precio_mes": _flotante(precio["mes"]),
                             "hora_extra": _flotante(precio["hora_extra"]),
                             "producto": precio["producto"]})
    tasa = cc.tasa_iva(db, pais_id)
    horas = horas_del_pais(db, pais_id)
    return {
        "pais_id": pais_id,
        "lista": ({"id": lista.id, "nombre": lista.nombre,
                   "moneda": lista.moneda.value,
                   # Sus paquetes traen los gastos: solo van con los
                   # viaticos incluidos (`usa_paquetes`).
                   "paquetes_con_viaticos": bool(lista.paquetes_con_viaticos)}
                  if lista else None),
        # Por que se escribe el precio: la empresa todavia no esta en
        # Odoo, o el cliente no tiene lista de implantados.
        "sin_lista": (None if lista else
                      ("prospecto" if cliente is None else "sin_lista")),
        "moneda": _moneda(db, lista, pais_id).value,
        "roles": roles, "unidades": unidades, "paquetes": paquetes,
        "horas_del_pais": float(horas) if horas is not None else None,
        "bases": {k.value: v for k, v in BASE.items()},
        "plazas": [{"id": p.id, "nombre": p.nombre} for p in
                   db.query(m.Plaza).filter_by(pais_id=pais_id)
                   .order_by(m.Plaza.nombre).all()],
        "tasa_iva": float(tasa) if tasa is not None else None,
        "solicitantes": ([{"id": s.id, "nombre": s.nombre,
                           "apellidos": s.apellidos, "correo": s.correo,
                           "telefono": s.telefono, "completo": s.completo}
                          for s in (db.query(m.Solicitante)
                                    .filter_by(cliente_id=cliente.id,
                                               activo=True)
                                    .order_by(m.Solicitante.nombre).all())]
                         if cliente else []),
    }


def _flotante(valor) -> float | None:
    return None if valor is None else float(valor)


# ------------------------------------------------------------- la entrada

def _decimal(valor, que: str, positivo: bool = True) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        numero = _dinero(valor)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, f"{que} no es un número.")
    if numero < 0 or (positivo and numero == 0):
        raise HTTPException(400, f"{que} tiene que ser mayor que cero.")
    return numero


def _posiciones(db: Session, crudas) -> list[dict]:
    """[{tipo, perfil_id, categoria_id, cantidad, precio_mes, descripcion}]
    limpias: el rol y la unidad que existen, una cantidad razonable y el
    mensual escrito si se escribio."""
    crudas = crudas or []
    if len(crudas) > MAX_POSICIONES:
        raise HTTPException(400, f"Hasta {MAX_POSICIONES} renglones por "
                                 "propuesta.")
    salida = []
    for i, cruda in enumerate(crudas, start=1):
        tipo = cruda.get("tipo")
        if tipo not in TIPOS:
            raise HTTPException(400, f"Renglón {i}: solo se proponen puestos, "
                                     "unidades o paquetes.")
        try:
            cantidad = int(cruda.get("cantidad") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Renglón {i}: la cantidad no es un "
                                     "número.")
        if cantidad <= 0:
            continue
        if cantidad > MAX_CANTIDAD:
            raise HTTPException(400, f"Renglón {i}: hasta {MAX_CANTIDAD} de "
                                     "cada uno.")
        perfil = categoria = None
        if tipo in DE_PERSONAL:
            perfil = (db.get(m.PerfilPersonal, cruda.get("perfil_id"))
                      if cruda.get("perfil_id") else None)
            if perfil is None:
                raise HTTPException(400, f"Renglón {i}: escoge el rol.")
        if tipo in (VEHICULO, PAQUETE):
            categoria = (db.get(m.CategoriaVehiculo, cruda.get("categoria_id"))
                         if cruda.get("categoria_id") else None)
            if categoria is None:
                raise HTTPException(400, f"Renglón {i}: escoge la unidad.")
        descripcion = cc._limpio(cruda.get("descripcion"), LARGO_DESCRIPCION)
        salida.append({
            "tipo": tipo, "perfil": perfil, "categoria": categoria,
            "perfil_id": perfil.id if perfil else None,
            "categoria_id": categoria.id if categoria else None,
            "cantidad": cantidad,
            "precio_mes": _decimal(cruda.get("precio_mes"),
                                   f"El precio al mes del renglón {i}"),
            "descripcion": descripcion})
    return salida


def preparar(db: Session, datos: dict) -> dict:
    """Lo que manda la pantalla, revisado: para quien es, su lista de
    implantados, la ciudad, la modalidad, los viaticos, la jornada y lo
    que lleva al mes."""
    from app.routers.implantados import hora_valida

    cliente = None
    if datos.get("cliente_id"):
        cliente = db.get(m.Cliente, datos["cliente_id"])
        if cliente is None:
            raise HTTPException(404, f"No existe el cliente {datos['cliente_id']}")
    pais_id = cliente.pais_id if cliente else datos.get("pais_id")
    if not pais_id or db.get(m.Pais, pais_id) is None:
        raise HTTPException(400, "Di de qué país es la empresa.")
    prospecto = None if cliente else cc._limpio(datos.get("prospecto"),
                                                cc.LARGO_NOMBRE)
    if cliente is None and not prospecto:
        raise HTTPException(400, "Escoge el cliente o escribe el nombre de "
                                 "la empresa.")
    lista = lista_de_implantados(db, cliente)

    consultor_id = datos.get("consultor_id")
    if consultor_id and not accesos.lleva_servicios(db, consultor_id):
        raise accesos.no_es_consultor(consultor_id)

    plaza_id = datos.get("plaza_id")
    if plaza_id:
        plaza = db.get(m.Plaza, plaza_id)
        if plaza is None or plaza.pais_id != pais_id:
            raise HTTPException(400, "Esa ciudad no es del país de la "
                                     "propuesta.")
    try:
        dias_servicio = D(datos.get("dias_servicio") or D.LUNES_VIERNES.value)
    except ValueError:
        raise HTTPException(400, "La modalidad es de lunes a viernes, de "
                                 "lunes a sábado o el mes completo.")
    viaticos = datos.get("viaticos") or APARTE
    if viaticos not in (APARTE, INCLUIDOS):
        raise HTTPException(400, "Los viáticos van aparte o incluidos.")
    horas = datos.get("horas_jornada")
    if horas in ("", None):
        horas = None
    else:
        try:
            horas, _descanso = motor_implantado.validar_horas(horas, None)
        except (InvalidOperation, ValueError):
            raise HTTPException(400, "La jornada no es un número de horas.")
    hora = datos.get("hora_presentacion")
    if hora:
        try:
            hora = hora_valida(hora)
        except ValueError as error:
            raise HTTPException(400, str(error))
    else:
        hora = None

    idioma = datos.get("idioma") or (db.get(m.Pais, pais_id).idioma or "es")
    if idioma not in cc.IDIOMAS:
        raise HTTPException(400, "El PDF sale en español, inglés o portugués.")
    alcance = (datos.get("alcance") or "").strip() or None
    if alcance and len(alcance) > LARGO_ALCANCE:
        raise HTTPException(400, f"El alcance pasa de {LARGO_ALCANCE} letras.")

    return {
        "cliente": cliente, "cliente_id": cliente.id if cliente else None,
        "prospecto": prospecto, "pais_id": pais_id, "lista": lista,
        **cc._contacto(db, datos, cliente, pais_id),
        "consultor_id": consultor_id or None,
        "plaza_id": plaza_id or None,
        "tipo_servicio": cc._limpio(datos.get("tipo_servicio"), cc.LARGO_TIPO),
        "introduccion": (datos.get("introduccion") or "").strip() or None,
        "valida_hasta": datos.get("valida_hasta"),
        "idioma": idioma,
        "con_iva": datos.get("con_iva") is not False,
        "inicio": datos.get("inicio"),
        "dias_servicio": dias_servicio,
        "viaticos": viaticos,
        "horas_jornada": horas,
        "hora_presentacion": hora,
        "alcance": alcance,
        "precio_hora_extra": _decimal(datos.get("precio_hora_extra"),
                                      "La hora extra", positivo=False),
        "especial_motivo": cc._limpio(datos.get("especial_motivo"),
                                      LARGO_NOTA),
        "motivo": cc._limpio(datos.get("motivo"), cc.LARGO_MOTIVO),
        "posiciones": _posiciones(db, datos.get("posiciones")),
    }


# ------------------------------------------------------------- los precios

def calcular(db: Session, prep: dict) -> dict:
    """Los precios de lo que lleva al mes, renglon por renglon.

    El de la lista: su precio por dia por los dias de la modalidad; si la
    lista lo cobra al mes (seccion 123, el paquete de Amazon Brasil), ese
    mensual tal cual, y su dia es el mensual entre los dias. El escrito:
    el mensual que se escribio, y su dia es ese mensual entre los dias;
    si no es el de la lista --o la lista no lo tiene--, es especial. La
    hora extra del equipo es la que se escribio o la suma de la de cada
    rol en la lista. El dia adicional, el precio por dia de las personas:
    la unidad va por mes.
    """
    base = base_de(prep["dias_servicio"])
    lista = prep["lista"]
    modalidad = _modalidad(db, prep["pais_id"])
    paquetes = usa_paquetes(lista, prep["viaticos"])
    posiciones, faltan = [], []
    for orden, p in enumerate(prep["posiciones"], start=1):
        if p["tipo"] == PAQUETE and lista is not None and not paquetes:
            raise HTTPException(400, {
                "mensaje": f"Con más viáticos no va el paquete de la lista "
                           f"{lista.nombre}: trae los gastos dentro",
                "que_hacer": "Pon el puesto y la unidad por separado, o "
                             "cambia a viáticos incluidos.",
                "clave": "paquete_con_gastos"})
        de_lista = _de_la_lista(db, lista, modalidad, p["tipo"],
                                p["perfil_id"], p["categoria_id"])
        nombre = _nombre(p["perfil"], p["categoria"], p["tipo"])
        if de_lista["mes"] is not None:
            lista_mes = de_lista["mes"]
        else:
            lista_mes = ((de_lista["dia"] * base).quantize(CENTAVO)
                         if de_lista["dia"] is not None else None)
        escrito = p["precio_mes"]
        if escrito is not None and escrito != lista_mes:
            precio_mes = escrito
            precio_dia = (escrito / base).quantize(CENTAVO,
                                                   rounding=ROUND_HALF_UP)
            especial = True
        elif lista_mes is not None:
            precio_mes, especial = lista_mes, False
            precio_dia = (de_lista["dia"] if de_lista["dia"] is not None
                          else (lista_mes / base).quantize(
                              CENTAVO, rounding=ROUND_HALF_UP))
        else:
            precio_mes = precio_dia = None
            especial = False
            faltan.append(nombre)
        posiciones.append({
            "orden": orden, "tipo": p["tipo"], "perfil_id": p["perfil_id"],
            "categoria_id": p["categoria_id"], "cantidad": p["cantidad"],
            "precio_dia": precio_dia, "precio_mes": precio_mes,
            "precio_hora_extra": de_lista["hora_extra"],
            "especial": especial, "lista_precio_dia": de_lista["dia"],
            # El mensual de la lista, tal cual: el que trae por mes o su
            # precio por dia por los dias (seccion 123).
            "lista_precio_mes": lista_mes,
            "lista_por_mes": de_lista["mes"] is not None,
            "producto": de_lista["producto"],
            "descripcion": p["descripcion"], "nombre": nombre,
            "importe": (precio_mes * p["cantidad"]
                        if precio_mes is not None else None)})
    return _con_totales(posiciones, faltan, base, prep["dias_servicio"],
                        prep["precio_hora_extra"])


def _con_totales(posiciones: list[dict], faltan: list[str], base: int,
                 dias_servicio, hora_extra_escrita) -> dict:
    personas = [p for p in posiciones if p["tipo"] in DE_PERSONAL]
    subtotal = sum((p["importe"] for p in posiciones
                    if p["importe"] is not None), CERO)
    # El dia adicional: el precio por dia de las personas. Con el mes
    # completo no hay dia fuera de la modalidad.
    dia_adicional = None
    if (D(dias_servicio) != D.TODOS and personas
            and all(p["precio_dia"] is not None for p in personas)):
        dia_adicional = sum((p["precio_dia"] * p["cantidad"]
                             for p in personas), CERO)
    con_extra = [p for p in personas if p["precio_hora_extra"] is not None]
    hora_extra_lista = (sum((p["precio_hora_extra"] * p["cantidad"]
                             for p in con_extra), CERO) if con_extra else None)
    if hora_extra_escrita is not None:
        hora_extra = hora_extra_escrita
        hora_extra_especial = hora_extra_escrita != (hora_extra_lista or CERO)
    else:
        hora_extra, hora_extra_especial = hora_extra_lista, False
    return {
        "base": base, "posiciones": posiciones, "faltan": faltan,
        "subtotal": subtotal, "dia_adicional": dia_adicional,
        "hora_extra": hora_extra, "hora_extra_lista": hora_extra_lista,
        "hora_extra_especial": hora_extra_especial,
        "especial": (any(p["especial"] for p in posiciones)
                     or hora_extra_especial),
        "personas": sum(p["cantidad"] for p in personas),
        "unidades": sum(p["cantidad"] for p in posiciones
                        if p["tipo"] in (VEHICULO, PAQUETE)),
    }


def de_la_guardada(cot: m.Cotizacion) -> dict:
    """Los mismos totales, de lo que se guardo: lo que dice el PDF y lo
    que toma el implantado. Sin volver a leer la lista."""
    base = base_de(cot.dias_servicio)
    posiciones = [{
        "orden": p.orden, "tipo": p.tipo, "perfil_id": p.perfil_id,
        "categoria_id": p.categoria_id, "cantidad": p.cantidad,
        "precio_dia": _o_nada(p.precio_dia), "precio_mes": _o_nada(p.precio_mes),
        "precio_hora_extra": _o_nada(p.precio_hora_extra),
        "especial": p.especial, "lista_precio_dia": _o_nada(p.lista_precio_dia),
        **_mensual_de_la_lista(p.lista_precio_dia, p.lista_precio_mes, base),
        "producto": p.producto, "descripcion": p.descripcion,
        "nombre": (_nombre(p.perfil, p.categoria, p.tipo)
                   if (p.perfil or p.categoria) else "—"),
        "importe": (_dinero(p.precio_mes) * p.cantidad
                    if p.precio_mes is not None else None)}
        for p in sorted(cot.posiciones, key=lambda x: (x.orden, x.id or 0))]
    faltan = [p["nombre"] for p in posiciones if p["precio_mes"] is None]
    return _con_totales(posiciones, faltan, base,
                        cot.dias_servicio or D.LUNES_VIERNES,
                        _o_nada(cot.precio_hora_extra))


def _mensual_de_la_lista(dia, mes, base: int) -> dict:
    """{lista_precio_mes, lista_por_mes} de un renglon guardado: el mensual
    que la lista trae por mes (seccion 123) o, si no, su precio por dia
    por los dias --las propuestas de antes solo guardaban el del dia--."""
    if mes is not None:
        return {"lista_precio_mes": _dinero(mes), "lista_por_mes": dia is None}
    return {"lista_precio_mes": ((_dinero(dia) * base).quantize(CENTAVO)
                                 if dia is not None else None),
            "lista_por_mes": False}


def sugerencias(db: Session, prep: dict) -> list[dict]:
    """El puesto y la unidad que la lista del cliente pacta en un solo
    precio y se pusieron separados con el precio de la lista: se le dice
    al consultor, que decide. No se juntan solos --la propuesta es lo que
    se le ofrece al cliente--."""
    lista = prep["lista"]
    modalidad = _modalidad(db, prep["pais_id"])
    if (lista is None or modalidad is None
            or not usa_paquetes(lista, prep["viaticos"])):
        return []
    roles = {p["perfil_id"] for p in prep["posiciones"]
             if p["tipo"] == RECURSO and p["precio_mes"] is None}
    unidades = {p["categoria_id"] for p in prep["posiciones"]
                if p["tipo"] == VEHICULO and p["precio_mes"] is None}
    salida = []
    for t in paquetes_de_la_lista(db, lista, modalidad):
        if t.perfil_id in roles and t.categoria_id in unidades:
            # El del mes (seccion 123) dice su mensual; el del dia, su
            # precio por dia.
            por_mes = t.modalidad_id != modalidad.id
            salida.append({"perfil_id": t.perfil_id,
                           "categoria_id": t.categoria_id,
                           "nombre": motor.nombre_del_paquete(t),
                           "precio_dia": None if por_mes else float(_dinero(t.precio)),
                           "precio_mes": float(_dinero(t.precio)) if por_mes else None})
    return salida


def huella(dias_servicio, moneda, calc: dict) -> str:
    """Lo que direccion de operaciones autoriza, en una cadena: la
    modalidad, la moneda, cada renglon con su mensual y la hora extra. Si
    algo de eso cambia, el visto bueno ya no es de esto."""
    partes = [D(dias_servicio).value if dias_servicio else None,
              m.Moneda(moneda).value if moneda else None,
              [[p["tipo"], p["perfil_id"], p["categoria_id"], p["cantidad"],
                str(p["precio_mes"]), bool(p["especial"])]
               for p in calc["posiciones"]],
              str(calc["hora_extra"])]
    return hashlib.sha256(json.dumps(partes).encode()).hexdigest()


def huella_de(cot: m.Cotizacion, calc: dict | None = None) -> str:
    return huella(cot.dias_servicio, cot.moneda,
                  calc if calc is not None else de_la_guardada(cot))


# ------------------------------------------------------------- guardar

CAMPOS = ("cliente_id", "prospecto", "pais_id", "solicitante_id",
          "solicitante_nombre", "solicitante_apellidos", "solicitante_correo",
          "solicitante_telefono", "consultor_id", "tipo_servicio",
          "introduccion", "valida_hasta", "idioma", "con_iva", "plaza_id",
          "dias_servicio", "horas_jornada", "hora_presentacion", "inicio",
          "alcance", "precio_hora_extra", "especial_motivo")


def _poner(db: Session, cot: m.Cotizacion, prep: dict) -> None:
    for campo in CAMPOS:
        setattr(cot, campo, prep[campo])
    cot.motivo_recotizacion = prep["motivo"] if cot.version > 1 else None
    cot.tarifario_id = prep["lista"].id if prep["lista"] else None
    cot.moneda = _moneda(db, prep["lista"], prep["pais_id"])
    cot.viaticos_incluidos = prep["viaticos"] == INCLUIDOS


def _poner_posiciones(db: Session, cot: m.Cotizacion, calc: dict) -> None:
    cot.posiciones.clear()
    db.flush()
    for p in calc["posiciones"]:
        cot.posiciones.append(m.PosicionPropuesta(
            orden=p["orden"], tipo=p["tipo"], perfil_id=p["perfil_id"],
            categoria_id=p["categoria_id"], cantidad=p["cantidad"],
            precio_dia=p["precio_dia"], precio_mes=p["precio_mes"],
            precio_hora_extra=p["precio_hora_extra"], especial=p["especial"],
            lista_precio_dia=p["lista_precio_dia"],
            lista_precio_mes=p["lista_precio_mes"], producto=p["producto"],
            descripcion=p["descripcion"]))
    cot.total = calc["subtotal"]


def _revisar_especial(cot: m.Cotizacion, calc: dict) -> None:
    """Sin precio especial no hay nada que autorizar. Con el, el visto
    bueno vale mientras los precios sean los que se autorizaron."""
    if not calc["especial"]:
        cot.especial_estatus = None
        return
    if (cot.especial_estatus == AUTORIZADO
            and cot.especial_huella != huella_de(cot, calc)):
        cot.especial_estatus = None


def especial_vigente(cot: m.Cotizacion, calc: dict | None = None) -> bool:
    """Si el precio especial tiene el visto bueno, y es de estos precios."""
    return (cot.especial_estatus == AUTORIZADO
            and cot.especial_huella == huella_de(cot, calc))


def guardar(db: Session, actor: m.Usuario, datos: dict,
            cot: m.Cotizacion | None = None) -> tuple[m.Cotizacion, dict]:
    """El borrador: nuevo, con su folio EP/PRO, o el mismo con lo que
    cambio."""
    prep = preparar(db, datos)
    if cot is None:
        cot = m.Cotizacion(clase=CLASE, folio=cc._siguiente_folio(db, CLASE),
                           version=1, estatus=E.BORRADOR,
                           creada_por_id=actor.persona_id)
        db.add(cot)
    elif cot.estatus != E.BORRADOR:
        raise HTTPException(409, {
            "mensaje": f"La {nombre_de(cot)} ya se mandó: lo enviado no cambia",
            "que_hacer": "Haz la versión siguiente para cambiarla."})
    _poner(db, cot, prep)
    calc = calcular(db, prep)
    _poner_posiciones(db, cot, calc)
    _revisar_especial(cot, calc)
    cot.tasa_iva = cc.tasa_iva(db, prep["pais_id"])
    cot.actualizada_en = _ahora()
    db.flush()
    return cot, calc


def datos_de(cot: m.Cotizacion) -> dict:
    """Lo que se guardo, en la forma en que lo manda la pantalla. El
    renglon con el precio de la lista va sin precio: al mandarla se lee
    otra vez la lista. El especial lleva el suyo."""
    return {
        "cliente_id": cot.cliente_id, "prospecto": cot.prospecto,
        "pais_id": cot.pais_id, "solicitante_id": cot.solicitante_id,
        "solicitante_nombre": cot.solicitante_nombre,
        "solicitante_apellidos": cot.solicitante_apellidos,
        "solicitante_correo": cot.solicitante_correo,
        "solicitante_telefono": cot.solicitante_telefono,
        "consultor_id": cot.consultor_id, "plaza_id": cot.plaza_id,
        "tipo_servicio": cot.tipo_servicio, "introduccion": cot.introduccion,
        "valida_hasta": cot.valida_hasta, "idioma": cot.idioma,
        "con_iva": cot.con_iva, "inicio": cot.inicio,
        "dias_servicio": (cot.dias_servicio.value if cot.dias_servicio
                          else None),
        "viaticos": INCLUIDOS if cot.viaticos_incluidos else APARTE,
        "horas_jornada": cot.horas_jornada,
        "hora_presentacion": cot.hora_presentacion,
        "alcance": cot.alcance,
        "precio_hora_extra": cot.precio_hora_extra,
        "especial_motivo": cot.especial_motivo,
        "motivo": cot.motivo_recotizacion,
        "posiciones": [{"tipo": p.tipo, "perfil_id": p.perfil_id,
                        "categoria_id": p.categoria_id,
                        "cantidad": p.cantidad,
                        "precio_mes": p.precio_mes if p.especial else None,
                        "descripcion": p.descripcion}
                       for p in sorted(cot.posiciones,
                                       key=lambda x: (x.orden, x.id or 0))],
    }


def precios(db: Session, datos: dict) -> dict:
    """Los precios de lo que se esta armando, sin guardar nada: los
    renglones, el mensual con IVA, el dia adicional, la hora extra, si
    lleva precio especial, la introduccion y el alcance que Connect
    escribiria, y lo que le falta al PDF de Catalogos."""
    from app import propuesta_pdf

    sin_nombre = (not datos.get("cliente_id")
                  and not (datos.get("prospecto") or "").strip())
    prep = preparar(db, {**datos, "prospecto": "—"} if sin_nombre else datos)
    calc = calcular(db, prep)
    tasa = cc.tasa_iva(db, prep["pais_id"])
    moneda = _moneda(db, prep["lista"], prep["pais_id"])
    como_va = _como_va(db, prep, calc, moneda)
    return {
        **_en_json(calc),
        **{k: float(v) for k, v in cc._totales(calc["subtotal"],
                                               prep["con_iva"], tasa).items()},
        "tasa_iva": float(tasa) if tasa is not None else None,
        "con_iva": prep["con_iva"],
        "moneda": moneda.value,
        "huella": huella(prep["dias_servicio"], moneda, calc),
        "sugerencias": sugerencias(db, prep),
        "firma": cc.tiene_firma(db, prep["consultor_id"]),
        "faltan_textos": faltan_textos(db, prep["pais_id"], prep["idioma"],
                                       como_va),
        "introduccion_auto": (None if sin_nombre else
                              propuesta_pdf.intro_automatica(
                                  db, como_va, prep["idioma"], False)),
        "alcance_auto": alcance_auto(db, prep["pais_id"], prep["idioma"],
                                     [p["perfil_id"] for p in calc["posiciones"]]),
        "horas_del_pais": _flotante(horas_del_pais(db, prep["pais_id"])),
    }


def _como_va(db: Session, prep: dict, calc: dict, moneda) -> SimpleNamespace:
    """Lo que se esta armando con la forma de una propuesta guardada, para
    escribir su introduccion y revisar sus textos sin guardar nada."""
    return SimpleNamespace(
        introduccion=None, tipo_servicio=prep["tipo_servicio"],
        solicitante_nombre=prep["solicitante_nombre"],
        solicitante_apellidos=prep["solicitante_apellidos"],
        cliente=prep["cliente"], prospecto=prep["prospecto"],
        plaza=db.get(m.Plaza, prep["plaza_id"]) if prep["plaza_id"] else None,
        inicio=prep["inicio"], dias_servicio=prep["dias_servicio"],
        viaticos_incluidos=prep["viaticos"] == INCLUIDOS, moneda=moneda,
        lleva_unidad=calc["unidades"] > 0)


def _en_json(calc: dict) -> dict:
    return {
        "base": calc["base"],
        "posiciones": [{
            **{k: v for k, v in p.items()
               if k not in ("precio_dia", "precio_mes", "precio_hora_extra",
                            "lista_precio_dia", "lista_precio_mes", "importe")},
            "precio_dia": _flotante(p["precio_dia"]),
            "precio_mes": _flotante(p["precio_mes"]),
            "precio_hora_extra": _flotante(p["precio_hora_extra"]),
            "lista_precio_dia": _flotante(p["lista_precio_dia"]),
            # El mensual de la lista, tal cual (seccion 123): el que trae
            # por mes no se vuelve a armar con el precio por dia.
            "lista_precio_mes": _flotante(p["lista_precio_mes"]),
            "lista_por_mes": bool(p.get("lista_por_mes")),
            "importe": _flotante(p["importe"])} for p in calc["posiciones"]],
        "faltan_precios": calc["faltan"],
        "dia_adicional": _flotante(calc["dia_adicional"]),
        "hora_extra": _flotante(calc["hora_extra"]),
        "hora_extra_lista": _flotante(calc["hora_extra_lista"]),
        "hora_extra_especial": calc["hora_extra_especial"],
        "especial": calc["especial"],
        "personas": calc["personas"], "unidades": calc["unidades"],
    }


# ------------------------------------------------------------- mandarla

def _hoy(db: Session, cot: m.Cotizacion) -> date:
    return reloj.Relojes(db).hoy(cot.pais_id)


def que_le_falta(db: Session, cot: m.Cotizacion,
                 calc: dict | None = None) -> list[str]:
    """Lo que impide mandarla, en palabras del consultor."""
    calc = calc if calc is not None else de_la_guardada(cot)
    faltan = []
    if not (cot.solicitante_nombre or "").strip():
        faltan.append("El nombre de quien la pide")
    if not cot.consultor_id:
        faltan.append("Quien la firma")
    if not cot.plaza_id:
        faltan.append("La ciudad donde opera")
    if not cot.valida_hasta:
        faltan.append("Hasta cuándo es válida")
    elif cot.valida_hasta < _hoy(db, cot):
        faltan.append("Una fecha de «válida hasta» que no haya pasado")
    if not calc["posiciones"]:
        faltan.append("Lo que lleva al mes")
    else:
        if not calc["personas"]:
            faltan.append("Al menos una persona: el implantado no va sin "
                          "personal")
        if calc["faltan"]:
            faltan.append("El precio de " + ", ".join(calc["faltan"]))
    if cot.version > 1 and not cot.motivo_recotizacion:
        faltan.append("Qué cambió en esta versión")
    if calc["especial"]:
        if not cot.especial_motivo:
            faltan.append("Por qué el precio es especial")
        elif not especial_vigente(cot, calc):
            faltan.append("El visto bueno de dirección de operaciones al "
                          "precio especial")
    return faltan


def enviar(db: Session, actor: m.Usuario, cot: m.Cotizacion) -> m.Cotizacion:
    """La deja mandada: se vuelve a leer la lista, se arma el PDF y se
    guarda tal como sale. El precio especial tiene que traer su visto
    bueno, y de estos precios. Las versiones de antes que seguian
    abiertas quedan sustituidas."""
    from app import propuesta_pdf

    if cot.estatus != E.BORRADOR:
        raise HTTPException(409, f"La {nombre_de(cot)} ya se mandó.")
    if cc.ultima(db, cot.folio, cot.clase).id != cot.id:
        raise HTTPException(409, "Ya hay una versión más nueva de esta "
                                 "propuesta.")
    prep = preparar(db, datos_de(cot))
    calc = calcular(db, prep)
    _poner_posiciones(db, cot, calc)
    _revisar_especial(cot, calc)
    faltan = que_le_falta(db, cot, calc)
    if faltan:
        raise HTTPException(400, {
            "mensaje": "Le falta: " + "; ".join(faltan).lower(),
            "que_hacer": "Complétalo y vuelve a mandarla.",
            "faltan": faltan})
    cot.tasa_iva = cc.tasa_iva(db, cot.pais_id)
    cot.estatus = E.ENVIADA
    cot.enviada_en = _ahora()
    cot.enviada_por_id = actor.persona_id
    cot.actualizada_en = cot.enviada_en
    db.flush()
    contenido = propuesta_pdf.pdf(db, cot)
    cot.archivos.append(m.ArchivoCotizacion(
        clase="pdf", nombre=propuesta_pdf.nombre_del_archivo(db, cot),
        tipo="application/pdf", tamano=len(contenido), contenido=contenido,
        subido_por_id=actor.persona_id))
    for vieja in cc.versiones(db, cot.folio, cot.clase):
        if vieja.id != cot.id and vieja.estatus in (E.BORRADOR, E.ENVIADA,
                                                    E.VENCIDA):
            vieja.estatus = E.SUSTITUIDA
    db.flush()
    return cot


# ------------------------------------------------------------- el precio especial

def _el_borrador(db: Session, cot: m.Cotizacion) -> None:
    if cot.estatus != E.BORRADOR:
        raise HTTPException(409, f"La {nombre_de(cot)} ya se mandó: su precio "
                                 "ya no se autoriza.")
    if cc.ultima(db, cot.folio, cot.clase).id != cot.id:
        raise HTTPException(409, "Ya hay una versión más nueva de esta "
                                 "propuesta.")


def pedir_especial(db: Session, actor: m.Usuario,
                   cot: m.Cotizacion) -> m.Cotizacion:
    """El consultor pide el visto bueno del precio especial a direccion de
    operaciones (decision 2). Si quien lo pide ya puede autorizarlo
    --direccion arma una propuesta--, queda autorizado de una vez."""
    _el_borrador(db, cot)
    calc = calcular(db, preparar(db, datos_de(cot)))
    _poner_posiciones(db, cot, calc)
    if not calc["especial"]:
        raise HTTPException(409, "Todo sale de la lista del cliente: no hay "
                                 "precio especial que autorizar.")
    if calc["faltan"]:
        raise HTTPException(400, "Ponle precio a todo antes de pedirlo: "
                                 + ", ".join(calc["faltan"]) + ".")
    if not cot.especial_motivo:
        raise HTTPException(400, {
            "mensaje": "Di por qué el precio es especial",
            "que_hacer": "Escríbelo junto al precio: es lo que lee dirección "
                         "de operaciones para autorizarlo."})
    ahora = _ahora()
    cot.especial_pedido_por_id = actor.persona_id
    cot.especial_pedido_en = ahora
    cot.especial_huella = huella_de(cot, calc)
    cot.especial_nota = None
    if auth.puede_el_usuario(db, actor, ESPECIAL):
        cot.especial_estatus = AUTORIZADO
        cot.especial_por_id = actor.persona_id
        cot.especial_en = ahora
    else:
        cot.especial_estatus = PEDIDO
        cot.especial_por_id = None
        cot.especial_en = None
    db.flush()
    # Los nombres salen de la relacion, que se lee de nuevo tras guardar.
    db.expire(cot, ["especial_pedido_por", "especial_por"])
    if cot.especial_estatus == PEDIDO:
        _avisar_pedido(db, cot, calc)
    return cot


def decidir_especial(db: Session, actor: m.Usuario, cot: m.Cotizacion,
                     autoriza: bool, nota: str | None,
                     huella_vista: str | None) -> m.Cotizacion:
    """Direccion de operaciones lo autoriza o no, con su nota. La huella
    es la de los precios que vio en su pantalla: si cambiaron mientras
    tanto, no se autoriza a ciegas."""
    if cot.especial_estatus != PEDIDO:
        raise HTTPException(409, "No hay precio especial por autorizar en "
                                 f"la {nombre_de(cot)}.")
    _el_borrador(db, cot)
    calc = calcular(db, preparar(db, datos_de(cot)))
    actual = huella_de(cot, calc)
    if huella_vista and huella_vista != actual:
        raise HTTPException(409, {
            "mensaje": "Los precios cambiaron desde que la abriste",
            "que_hacer": "Vuelve a abrirla y revisa los precios de ahora."})
    nota = cc._limpio(nota, LARGO_NOTA)
    if not autoriza and not nota:
        raise HTTPException(400, "Di por qué no: el consultor lo lee para "
                                 "corregirla.")
    _poner_posiciones(db, cot, calc)
    cot.especial_estatus = AUTORIZADO if autoriza else RECHAZADO
    cot.especial_por_id = actor.persona_id
    cot.especial_en = _ahora()
    cot.especial_nota = nota
    cot.especial_huella = actual
    db.flush()
    db.expire(cot, ["especial_pedido_por", "especial_por"])
    _avisar_decision(db, cot)
    return cot


def _quien_autoriza(db: Session) -> list[m.Usuario]:
    from app import freelance
    return freelance._quienes(db, ESPECIAL)


def _pares(cot: m.Cotizacion, calc: dict) -> list:
    return [("prop_folio", nombre_de(cot)),
            ("prop_cliente", cc.cliente_texto(cot)),
            ("prop_mensual", f"{_dinero(calc['subtotal']):,.2f} "
                             f"{cot.moneda.value}"),
            ("prop_motivo", cot.especial_motivo or "-")]


def _avisar_pedido(db: Session, cot: m.Cotizacion, calc: dict) -> int:
    from app import freelance
    quien = (cot.especial_pedido_por.nombre if cot.especial_pedido_por
             else "—")
    return freelance._avisar(
        db, _quien_autoriza(db), "prop_especial_asunto",
        "prop_especial_cuerpo", _pares(cot, calc), "/consola/#/direccion",
        f"propuesta-especial-{cot.id}", quien=quien, folio=nombre_de(cot),
        cliente=cc.cliente_texto(cot), motivo=cot.especial_motivo or "-")


def _avisar_decision(db: Session, cot: m.Cotizacion) -> int:
    from app import freelance
    persona_id = cot.especial_pedido_por_id
    if not persona_id:
        return 0
    usuarios = (db.query(m.Usuario)
                .filter_by(persona_id=persona_id, activo=True).all())
    si = cot.especial_estatus == AUTORIZADO
    return freelance._avisar(
        db, usuarios,
        "prop_especial_si_asunto" if si else "prop_especial_no_asunto",
        "prop_especial_si_cuerpo" if si else "prop_especial_no_cuerpo",
        [("prop_folio", nombre_de(cot)),
         ("prop_cliente", cc.cliente_texto(cot)),
         ("prop_nota", cot.especial_nota or "-")],
        f"/consola/#/propuesta/{cot.id}", f"propuesta-especial-{cot.id}",
        quien=cot.especial_por.nombre if cot.especial_por else "—",
        folio=nombre_de(cot), cliente=cc.cliente_texto(cot),
        nota=cot.especial_nota or "-")


def por_autorizar(db: Session) -> list[dict]:
    """La seccion de la bandeja de direccion de operaciones: las
    propuestas que esperan el visto bueno de su precio especial, la mas
    vieja primero."""
    salida = []
    for cot in (db.query(m.Cotizacion)
                .options(selectinload(m.Cotizacion.posiciones))
                .filter(m.Cotizacion.clase == CLASE,
                        m.Cotizacion.estatus == E.BORRADOR,
                        m.Cotizacion.especial_estatus == PEDIDO)
                .order_by(m.Cotizacion.especial_pedido_en).all()):
        calc = de_la_guardada(cot)
        salida.append({
            "id": cot.id, "folio": folio_de(cot), "version": cot.version,
            "nombre": nombre_de(cot), "cliente": cc.cliente_texto(cot),
            "es_prospecto": cot.cliente_id is None,
            "consultor": cot.consultor.nombre if cot.consultor else None,
            "pedido_por": (cot.especial_pedido_por.nombre
                           if cot.especial_pedido_por else None),
            "pedido_en": (cot.especial_pedido_en.isoformat()
                          if cot.especial_pedido_en else None),
            "motivo": cot.especial_motivo,
            "moneda": cot.moneda.value,
            "dias_servicio": (cot.dias_servicio.value if cot.dias_servicio
                              else None),
            "subtotal": float(calc["subtotal"]),
            "hora_extra": _flotante(calc["hora_extra"]),
            "hora_extra_lista": _flotante(calc["hora_extra_lista"]),
            "hora_extra_especial": calc["hora_extra_especial"],
            "especiales": [{
                "nombre": p["descripcion"] or p["nombre"],
                "cantidad": p["cantidad"],
                "precio_mes": _flotante(p["precio_mes"]),
                "lista_precio_mes": _flotante(p["lista_precio_mes"])}
                for p in calc["posiciones"] if p["especial"]],
            "huella": huella_de(cot, calc),
            "ruta": f"#/propuesta/{cot.id}",
        })
    return salida


# ------------------------------------------------------------- la siguiente

def nueva_version(db: Session, actor: m.Usuario,
                  cot: m.Cotizacion) -> m.Cotizacion:
    """La version siguiente, como borrador, copiando la de antes. Trae el
    visto bueno del precio especial de la de antes: vale mientras sus
    precios no cambien."""
    if cc.ultima(db, cot.folio, cot.clase).id != cot.id:
        raise HTTPException(409, "Ya hay una versión más nueva de esta "
                                 "propuesta: cámbiala a ella.")
    if cot.estatus not in cc.DE_ESTAS_SALE_OTRA:
        if cot.estatus == E.AUTORIZADA:
            raise HTTPException(409, {
                "mensaje": "Ya la autorizó el cliente: es la propuesta de su "
                           f"implantado {cot.servicio_folio or ''}".strip(),
                "que_hacer": "Si el cliente cambió algo, se cambia en los "
                             "términos del mes del implantado."})
        raise HTTPException(409, "Esta versión todavía es borrador: cámbiala "
                                 "a ella.")
    nueva = m.Cotizacion(clase=CLASE, folio=cot.folio, version=cot.version + 1,
                         estatus=E.BORRADOR, creada_por_id=actor.persona_id,
                         tarifario_id=cot.tarifario_id, moneda=cot.moneda,
                         viaticos_incluidos=cot.viaticos_incluidos,
                         total=cot.total, tasa_iva=cot.tasa_iva)
    for campo in CAMPOS + ("especial_estatus", "especial_pedido_por_id",
                           "especial_pedido_en", "especial_por_id",
                           "especial_en", "especial_nota", "especial_huella"):
        setattr(nueva, campo, getattr(cot, campo))
    for p in sorted(cot.posiciones, key=lambda x: (x.orden, x.id or 0)):
        nueva.posiciones.append(m.PosicionPropuesta(
            orden=p.orden, tipo=p.tipo, perfil_id=p.perfil_id,
            categoria_id=p.categoria_id, cantidad=p.cantidad,
            precio_dia=p.precio_dia, precio_mes=p.precio_mes,
            precio_hora_extra=p.precio_hora_extra, especial=p.especial,
            lista_precio_dia=p.lista_precio_dia,
            lista_precio_mes=p.lista_precio_mes, producto=p.producto,
            descripcion=p.descripcion))
    nueva.actualizada_en = _ahora()
    db.add(nueva)
    db.flush()
    return nueva


rechazar = cc.rechazar


# ------------------------------------------------------------- autorizarla

DIAS_SEMANA = {D.LUNES_VIERNES: "Lunes a viernes", D.LUNES_SABADO:
               "Lunes a sábado", D.TODOS: "Todos los días"}


def _cubre(cot: m.Cotizacion, calc: dict) -> str:
    """Lo que el acuerdo del implantado dice que cubre: lo de la
    propuesta, en una linea."""
    lleva = ", ".join(f"{p['cantidad']} {p['descripcion'] or p['nombre']}"
                      for p in calc["posiciones"])
    horas = (f" Jornada de {_horas_texto(cot.horas_jornada)} horas."
             if cot.horas_jornada else "")
    return (f"Lo de la propuesta {nombre_de(cot)}: {lleva}. "
            f"{DIAS_SEMANA[D(cot.dias_servicio)]}, "
            f"{base_de(cot.dias_servicio)} días al mes.{horas}")[:2000]


def _horas_texto(horas) -> str:
    valor = Decimal(str(horas)).normalize()
    return f"{valor:f}"


def autorizar(db: Session, actor: m.Usuario, cot: m.Cotizacion,
              autorizada_por: str | None, autorizada_el: date | None,
              cliente_id: int | None = None,
              comprobante: tuple | None = None) -> m.Servicio:
    """El cliente dijo que si: nace el implantado (decision 5).

    El mismo alta que el implantado nuevo --cliente, quien la pidio, el
    consultor, la ciudad y el trato: desde cuando y que dias--, y esta
    MISMA propuesta queda adentro, autorizada. Su primer mes se abre con
    sus terminos (`terminos_del_primer_mes`). Le falta lo que una
    propuesta no dice: el ejecutivo, el punto fijo y quien va en que
    unidad. Si algo falla --el tipo de cambio que falta-- no queda nada.
    """
    from app.routers import implantados as rutas

    if cot.estatus not in cc.SE_AUTORIZAN:
        if cot.estatus == E.BORRADOR:
            raise HTTPException(409, "Primero se manda: el cliente autoriza "
                                     "lo que vio.")
        raise HTTPException(409, f"La {nombre_de(cot)} está "
                                 f"{cot.estatus.value}: ya no se autoriza.")
    if cc.ultima(db, cot.folio, cot.clase).id != cot.id:
        raise HTTPException(409, "Hay una versión más nueva: el cliente "
                                 "autoriza la última.")

    cliente = cot.cliente
    if cliente is None:
        if not cliente_id:
            raise HTTPException(400, {
                "mensaje": f"«{cot.prospecto}» todavía no es cliente en "
                           "Connect",
                "que_hacer": "Escoge su cliente. Si no aparece, que lo den "
                             "de alta en Odoo con la etiqueta de Protección "
                             "Ejecutiva: Connect lo lee cada hora.",
                "clave": "sin_cliente"})
        cliente = db.get(m.Cliente, cliente_id)
        if cliente is None:
            raise HTTPException(404, f"No existe el cliente {cliente_id}")
        if cliente.pais_id != cot.pais_id:
            raise HTTPException(400, "Ese cliente es de otro país.")
    if not cliente.odoo_id:
        raise HTTPException(400, {
            "mensaje": f"{cliente.nombre} no viene de Odoo",
            "que_hacer": "Para autorizarla el cliente tiene que estar en "
                         "Odoo: de ahí sale su factura."})

    quien = cc._limpio(autorizada_por, motor.LARGO_QUIEN)
    if not quien:
        raise HTTPException(400, "Di quién la autorizó del lado del cliente.")
    if autorizada_el is None:
        raise HTTPException(400, "Falta el día en que el cliente la autorizó.")
    if autorizada_el > _hoy(db, cot):
        raise HTTPException(400, "El día en que el cliente la autorizó no "
                                 "puede ser después de hoy.")
    local = tipo_cambio.local_del_pais(db, cot.pais_id)
    if local and cot.moneda != local:
        tc = (tipo_cambio.vigente(db, cot.moneda, local)
              if tipo_cambio.se_puede(cot.moneda, local) else None)
        if tc is None:
            raise HTTPException(409, motor.sin_tipo_de_cambio(db, cot.moneda,
                                                              local))
    if not cot.plaza_id:
        raise HTTPException(400, "Falta la ciudad donde opera.")

    calc = de_la_guardada(cot)
    suyo = (db.get(m.Solicitante, cot.solicitante_id)
            if cot.solicitante_id else None)
    contacto = suyo.id if suyo is not None and suyo.cliente_id == cliente.id \
        else None
    consultor_id = (cot.consultor_id if cot.consultor_id
                    and accesos.lleva_servicios(db, cot.consultor_id)
                    else None)
    datos = rutas.ServicioImplantadoIn(
        cliente_id=cliente.id, pais_id=cot.pais_id, plaza_id=cot.plaza_id,
        solicitante_id=contacto,
        solicitante_nombre=None if contacto else cot.solicitante_nombre,
        solicitante_apellidos=None if contacto else cot.solicitante_apellidos,
        solicitante_correo=None if contacto else cot.solicitante_correo,
        solicitante_telefono=None if contacto else cot.solicitante_telefono,
        idioma_solicitante=cot.idioma, consultor_id=consultor_id,
        acuerdo=rutas.AcuerdoIn(
            fecha_inicio=cot.inicio, dias_servicio=cot.dias_servicio,
            dias_semana=DIAS_SEMANA[D(cot.dias_servicio)],
            turno=motor_implantado.TURNO_NATURAL, cubre=_cubre(cot, calc)))
    servicio = rutas._guardar_servicio(db, actor, datos)
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    if acuerdo is not None and cot.hora_presentacion:
        acuerdo.hora_presentacion = cot.hora_presentacion

    cot.cliente_id = cliente.id
    cot.servicio_id = servicio.id
    cot.servicio = servicio
    motor._autorizar(db, cot, quien, autorizada_el, None)
    for otra in cc.versiones(db, cot.folio, cot.clase):
        otra.servicio_folio = servicio.folio
        if otra.id == cot.id:
            continue
        otra.servicio_id = servicio.id
        otra.cliente_id = cliente.id
        if otra.estatus in (E.BORRADOR, E.ENVIADA, E.VENCIDA):
            otra.estatus = E.SUSTITUIDA
    if comprobante:
        nombre, tipo, contenido = comprobante
        cot.archivos.append(m.ArchivoCotizacion(
            clase="comprobante", nombre=nombre, tipo=tipo,
            tamano=len(contenido), contenido=contenido,
            subido_por_id=actor.persona_id))
    db.flush()
    auditoria.registrar(db, actor, servicio, "alta desde la propuesta",
                        f"{nombre_de(cot)} · autorizada por {quien} el "
                        f"{autorizada_el:%d/%m/%Y}")
    return servicio


# ------------------------------------------------------------- el implantado

def autorizada_de(db: Session, servicio_id: int) -> m.Cotizacion | None:
    """La propuesta autorizada de la que nacio el implantado, si nacio de
    una."""
    return (db.query(m.Cotizacion)
            .filter_by(clase=CLASE, servicio_id=servicio_id,
                       estatus=E.AUTORIZADA)
            .order_by(m.Cotizacion.version.desc()).first())


def terminos_del_primer_mes(db: Session,
                            servicio: m.Servicio) -> dict | None:
    """Como se cobra el primer mes del implantado que nacio de una
    propuesta: precio fijo por mes --el mensual de la propuesta, antes de
    IVA--, el dia adicional, la hora extra, la jornada si no es la del
    pais y los viaticos como se pactaron. Los meses que siguen copian el
    de antes, como siempre. None si no nacio de una propuesta."""
    cot = autorizada_de(db, servicio.id)
    if cot is None:
        return None
    calc = de_la_guardada(cot)
    personas = [p for p in calc["posiciones"] if p["tipo"] in DE_PERSONAL]
    unidades = [p for p in calc["posiciones"] if p["tipo"] == VEHICULO]
    del_pais = horas_del_pais(db, servicio.pais_id)
    horas = (_dinero(cot.horas_jornada) if cot.horas_jornada is not None
             else None)
    local = tipo_cambio.local_del_pais(db, servicio.pais_id)
    moneda = None if (local is None or cot.moneda == local) else cot.moneda
    return {
        "esquema": m.EsquemaCotizacionImplantado.MES_COMPLETO,
        # Con esto el mes cobra aparte el dia fuera de la modalidad, y el
        # primer mes a medias va por dia (`implantado.cobro_del_mensual`).
        "dias_del_mensual": base_de(cot.dias_servicio),
        "precio_mes_completo": calc["subtotal"],
        "precio_dia_personal": (sum((p["precio_dia"] * p["cantidad"]
                                     for p in personas), CERO)
                                if personas else None),
        "precio_dia_adicional": calc["dia_adicional"],
        "precio_mes_vehiculo": (sum((p["importe"] for p in unidades), CERO)
                                if unidades else None),
        "precio_hora_extra": calc["hora_extra"],
        "horas_jornada": (horas if horas is not None and horas != del_pais
                          else None),
        # Incluidos: dentro del precio, sin monto aparte. Si no, los
        # netos: lo comprobado, con su desglose (seccion 59).
        "viaticos_incluidos": cot.viaticos_incluidos,
        "gastos_mes": None,
        "precios_de_la_lista": False,
        "moneda": moneda,
        "tipo_cambio": cot.tipo_cambio if moneda else None,
        "tipo_cambio_fecha": cot.tipo_cambio_fecha if moneda else None,
    }


def del_implantado(db: Session, servicio: m.Servicio) -> dict | None:
    """El bloque «La propuesta autorizada» de la pantalla del implantado."""
    cot = autorizada_de(db, servicio.id)
    if cot is None:
        return None
    calc = de_la_guardada(cot)
    return {
        "id": cot.id, "folio": folio_de(cot), "version": cot.version,
        "nombre": nombre_de(cot),
        "autorizada_por": cot.autorizada_por,
        "autorizada_el": (cot.autorizada_el.isoformat()
                          if cot.autorizada_el else None),
        "moneda": cot.moneda.value, "subtotal": float(calc["subtotal"]),
        "dias_servicio": cot.dias_servicio.value if cot.dias_servicio else None,
        "base": calc["base"],
        "horas_jornada": _flotante(cot.horas_jornada),
        "inicio": cot.inicio.isoformat() if cot.inicio else None,
        "viaticos": INCLUIDOS if cot.viaticos_incluidos else APARTE,
        "dia_adicional": _flotante(calc["dia_adicional"]),
        "hora_extra": _flotante(calc["hora_extra"]),
        "posiciones": [{"cantidad": p["cantidad"],
                        "nombre": p["descripcion"] or p["nombre"],
                        "precio_mes": _flotante(p["precio_mes"])}
                       for p in calc["posiciones"]],
        "pdf": cc.archivo(cot, "pdf") is not None,
    }


# ------------------------------------------------------------- la lista y el detalle

def renglon_de_lista(cot: m.Cotizacion) -> dict:
    calc = de_la_guardada(cot)
    tasa = (Decimal(str(cot.tasa_iva)) if cot.tasa_iva is not None else None)
    t = cc._totales(calc["subtotal"], cot.con_iva, tasa)
    return {
        "id": cot.id, "clase": CLASE, "folio": folio_de(cot),
        "version": cot.version, "estatus": cot.estatus.value,
        "cliente": cc.cliente_texto(cot), "es_prospecto": cot.cliente_id is None,
        "solicitante": m._nombre_completo(cot.solicitante_nombre,
                                          cot.solicitante_apellidos),
        "consultor": cot.consultor.nombre if cot.consultor else None,
        "desde": cot.inicio.isoformat() if cot.inicio else None,
        "hasta": None,
        "total": float(t["total"]), "al_mes": True,
        "moneda": cot.moneda.value,
        "valida_hasta": cot.valida_hasta.isoformat() if cot.valida_hasta else None,
        "enviada_en": cot.enviada_en.isoformat() if cot.enviada_en else None,
        "autorizada_por": cot.autorizada_por,
        "autorizada_el": (cot.autorizada_el.isoformat()
                          if cot.autorizada_el else None),
        "rechazo_motivo": cot.rechazo_motivo,
        "especial": cot.especial_estatus,
        "servicio": ({"id": cot.servicio.id, "folio": cot.servicio.folio}
                     if cot.servicio else None),
        "servicio_folio": cot.servicio_folio,
    }


def detalle(db: Session, cot: m.Cotizacion, usuario: m.Usuario) -> dict:
    from app import propuesta_pdf

    puede_armar = auth.puede_el_usuario(db, usuario, "cotizaciones.armar")
    puede_especial = auth.puede_el_usuario(db, usuario, ESPECIAL)
    calc = de_la_guardada(cot)
    tasa = (Decimal(str(cot.tasa_iva)) if cot.tasa_iva is not None else None)
    t = cc._totales(calc["subtotal"], cot.con_iva, tasa)
    pdf = cc.archivo(cot, "pdf")
    comprobante = cc.archivo(cot, "comprobante")
    es_ultima = cc.ultima(db, cot.folio, cot.clase).id == cot.id
    borrador = cot.estatus == E.BORRADOR
    lista = db.get(m.Tarifario, cot.tarifario_id) if cot.tarifario_id else None
    perfiles = [p["perfil_id"] for p in calc["posiciones"]]
    como_va = SimpleNamespace(
        introduccion=None, tipo_servicio=cot.tipo_servicio,
        solicitante_nombre=cot.solicitante_nombre,
        solicitante_apellidos=cot.solicitante_apellidos,
        cliente=cot.cliente, prospecto=cot.prospecto, plaza=cot.plaza,
        inicio=cot.inicio, dias_servicio=cot.dias_servicio,
        viaticos_incluidos=cot.viaticos_incluidos, moneda=cot.moneda,
        lleva_unidad=calc["unidades"] > 0)
    vigente = especial_vigente(cot, calc)
    return {
        **renglon_de_lista(cot),
        "nombre": nombre_de(cot),
        "pais_id": cot.pais_id,
        "pais": cot.pais.nombre if cot.pais else None,
        "cliente_id": cot.cliente_id, "prospecto": cot.prospecto,
        "cliente_rfc": cot.cliente.rfc if cot.cliente else None,
        "lista": ({"id": lista.id, "nombre": lista.nombre,
                   "moneda": lista.moneda.value} if lista else None),
        "solicitante_id": cot.solicitante_id,
        "solicitante_nombre": cot.solicitante_nombre,
        "solicitante_apellidos": cot.solicitante_apellidos,
        "solicitante_correo": cot.solicitante_correo,
        "solicitante_telefono": cot.solicitante_telefono,
        "consultor_id": cot.consultor_id,
        "tipo_servicio": cot.tipo_servicio, "introduccion": cot.introduccion,
        "introduccion_auto": propuesta_pdf.intro_automatica(
            db, como_va, cot.idioma or "es", False),
        "idioma": cot.idioma, "con_iva": cot.con_iva,
        "tasa_iva": float(cot.tasa_iva) if cot.tasa_iva is not None else None,
        "plaza_id": cot.plaza_id,
        "plaza": cot.plaza.nombre if cot.plaza else None,
        "inicio": cot.inicio.isoformat() if cot.inicio else None,
        "dias_servicio": (cot.dias_servicio.value if cot.dias_servicio
                          else None),
        "viaticos": INCLUIDOS if cot.viaticos_incluidos else APARTE,
        "horas_jornada": _flotante(cot.horas_jornada),
        "horas_del_pais": _flotante(horas_del_pais(db, cot.pais_id)),
        "hora_presentacion": (cot.hora_presentacion[:5]
                              if cot.hora_presentacion else None),
        "alcance": cot.alcance,
        "alcance_auto": alcance_auto(db, cot.pais_id, cot.idioma or "es",
                                     perfiles),
        "precio_hora_extra": _flotante(cot.precio_hora_extra),
        "motivo": cot.motivo_recotizacion,
        **_en_json(calc),
        "subtotal": float(t["subtotal"]), "iva": float(t["iva"]),
        "total": float(t["total"]),
        "especial": {
            "necesita": calc["especial"],
            "estatus": cot.especial_estatus,
            "vigente": vigente,
            "motivo": cot.especial_motivo,
            "pedido_por": (cot.especial_pedido_por.nombre
                           if cot.especial_pedido_por else None),
            "pedido_en": (cot.especial_pedido_en.isoformat()
                          if cot.especial_pedido_en else None),
            "por": cot.especial_por.nombre if cot.especial_por else None,
            "en": cot.especial_en.isoformat() if cot.especial_en else None,
            "nota": cot.especial_nota,
        },
        "huella": huella_de(cot, calc),
        "enviada_por": cot.enviada_por.nombre if cot.enviada_por else None,
        "rechazada_en": cot.rechazada_en.isoformat() if cot.rechazada_en else None,
        "autorizada_en": (cot.autorizada_en.isoformat()
                          if cot.autorizada_en else None),
        "pdf": {"nombre": pdf.nombre} if pdf else None,
        "comprobante": ({"nombre": comprobante.nombre}
                        if comprobante else None),
        "es_ultima": es_ultima,
        "se_edita": puede_armar and es_ultima and borrador,
        "se_autoriza": (puede_armar and es_ultima
                        and cot.estatus in cc.SE_AUTORIZAN),
        "sale_otra": (puede_armar and es_ultima
                      and cot.estatus in cc.DE_ESTAS_SALE_OTRA),
        "se_pide_especial": (puede_armar and es_ultima and borrador
                             and calc["especial"] and not vigente
                             and cot.especial_estatus != PEDIDO),
        "se_decide_especial": (puede_especial and es_ultima and borrador
                               and cot.especial_estatus == PEDIDO),
        "puede_especial": puede_especial,
        "faltan": que_le_falta(db, cot, calc) if borrador else [],
        "faltan_textos": (faltan_textos(db, cot.pais_id, cot.idioma or "es",
                                        como_va) if borrador else []),
        "firma": cc.tiene_firma(db, cot.consultor_id),
        "hoy": _hoy(db, cot).isoformat(),
        "versiones": [{
            "id": v.id, "version": v.version, "estatus": v.estatus.value,
            "motivo": v.motivo_recotizacion,
            "total": renglon_de_lista(v)["total"],
            "enviada_en": v.enviada_en.isoformat() if v.enviada_en else None,
            "pdf": cc.archivo(v, "pdf") is not None}
            for v in cc.versiones(db, cot.folio, cot.clase)],
    }


# ------------------------------------------------------------- Catalogos

def _roles(db: Session) -> list[m.PerfilPersonal]:
    return (db.query(m.PerfilPersonal).filter_by(activo=True)
            .order_by(m.PerfilPersonal.id).all())


def textos_de(db: Session, pais_id: int) -> dict:
    """Los textos de la propuesta de un pais, como los edita Catalogos:
    los de siempre y el alcance de cada rol."""
    claves = list(CLAVES_DE_TEXTO)
    roles = _roles(db)
    textos = {c: {i: "" for i in cc.IDIOMAS} for c in claves}
    alcances = {r.codigo: {i: "" for i in cc.IDIOMAS} for r in roles}
    for fila in db.query(m.TextoCotizacion).filter_by(pais_id=pais_id).all():
        if fila.idioma not in cc.IDIOMAS:
            continue
        if fila.clave in textos:
            textos[fila.clave][fila.idioma] = fila.texto
        elif fila.clave.startswith(ALCANCE):
            codigo = fila.clave[len(ALCANCE):]
            if codigo in alcances:
                alcances[codigo][fila.idioma] = fila.texto
    return {
        "pais_id": pais_id, "textos": textos,
        "alcances": [{"perfil_id": r.id, "codigo": r.codigo,
                      "nombre": r.nombre, "textos": alcances[r.codigo]}
                     for r in roles],
    }


def _texto(db: Session, pais_id: int | None, clave: str,
           idioma: str) -> str:
    if not pais_id:
        return ""
    fila = (db.query(m.TextoCotizacion)
            .filter_by(pais_id=pais_id, clave=clave, idioma=idioma).first())
    return fila.texto if fila else ""


def texto(db: Session, pais_id: int | None, clave: str, idioma: str) -> str:
    return _texto(db, pais_id, clave, idioma)


def alcance_auto(db: Session, pais_id: int | None, idioma: str,
                 perfil_ids) -> str:
    """El alcance que Connect escribe: el de Catalogos de cada rol que
    lleva, en el orden en que aparecen, uno tras otro."""
    vistos, partes = set(), []
    for perfil_id in perfil_ids:
        if not perfil_id or perfil_id in vistos:
            continue
        vistos.add(perfil_id)
        perfil = db.get(m.PerfilPersonal, perfil_id)
        if perfil is None:
            continue
        suyo = _texto(db, pais_id, ALCANCE + perfil.codigo, idioma).strip()
        if suyo:
            partes.append(suyo)
    return "\n\n".join(partes)


def faltan_textos(db: Session, pais_id: int | None, idioma: str,
                  cot) -> list[str]:
    """Lo que el PDF de ese pais en ese idioma no va a poder decir, para
    lo que lleva esta propuesta."""
    if not pais_id:
        return []
    claves = ["pro_incluye", "pro_cliente", "pro_centauro", "pro_aceptacion"]
    if getattr(cot, "lleva_unidad", False):
        claves.append("pro_incluye_unidad")
    if getattr(cot, "viaticos_incluidos", False):
        claves.append("pro_incluidos")
    else:
        claves += ["pro_no_incluye", "pro_viaticos"]
    faltan = [c for c in claves if not _texto(db, pais_id, c, idioma).strip()]
    datos = cc.datos_del_pais(db, pais_id)
    if datos is None or not datos.razon_social:
        faltan.append("razon_social")
    if datos is None or not datos.rfc:
        faltan.append("rfc")
    if datos is None or datos.tasa_iva is None:
        faltan.append("tasa_iva")
    return faltan


def guardar_textos(db: Session, actor: m.Usuario, pais_id: int,
                   datos: dict) -> dict:
    """Lo que escribio direccion de operaciones, con su renglon en la
    bitacora de administracion: cuales cambiaron, no el texto entero."""
    pais = db.get(m.Pais, pais_id)
    if pais is None:
        raise HTTPException(404, f"No existe el país {pais_id}")
    antes = textos_de(db, pais_id)
    de_antes = {**{c: antes["textos"][c] for c in CLAVES_DE_TEXTO},
                **{ALCANCE + a["codigo"]: a["textos"] for a in antes["alcances"]}}
    nuevos = {}
    for clave, por_idioma in (datos.get("textos") or {}).items():
        if clave not in CLAVES_DE_TEXTO:
            raise HTTPException(400, f"No existe el texto «{clave}».")
        nuevos[clave] = por_idioma or {}
    codigos = {a["codigo"] for a in antes["alcances"]}
    for codigo, por_idioma in (datos.get("alcances") or {}).items():
        if codigo not in codigos:
            raise HTTPException(400, f"No existe el rol «{codigo}».")
        nuevos[ALCANCE + codigo] = por_idioma or {}
    cambiados = []
    for clave, por_idioma in nuevos.items():
        for idioma, valor in por_idioma.items():
            if idioma not in cc.IDIOMAS:
                raise HTTPException(400, f"No existe el idioma «{idioma}».")
            valor = (valor or "").strip()
            largo = LARGO_ALCANCE if clave.startswith(ALCANCE) else cc.LARGO_TEXTO
            if len(valor) > largo:
                raise HTTPException(400, f"El texto «{clave}» pasa de "
                                         f"{largo} letras.")
            if valor == de_antes[clave][idioma]:
                continue
            fila = (db.query(m.TextoCotizacion)
                    .filter_by(pais_id=pais_id, clave=clave,
                               idioma=idioma).first())
            if valor and fila:
                fila.texto = valor
            elif valor:
                db.add(m.TextoCotizacion(pais_id=pais_id, clave=clave,
                                         idioma=idioma, texto=valor))
            elif fila:
                db.delete(fila)
            cambiados.append(f"{clave}:{idioma}")
    if cambiados:
        accesos.anotar(db, actor, "textos de la propuesta", "propuesta",
                       pais_id, despues=", ".join(cambiados)[:400],
                       detalle=pais.nombre)
    db.flush()
    return textos_de(db, pais_id)


def sembrar_mexico(db: Session) -> None:
    """Los textos de la propuesta de Mexico si no los tiene: la semilla de
    una base nueva. La de produccion los recibe con su migracion."""
    pais = db.query(m.Pais).filter_by(codigo="MX").first()
    if pais is None:
        return
    tiene = {(t.clave, t.idioma) for t in
             db.query(m.TextoCotizacion).filter_by(pais_id=pais.id).all()}
    for clave, por_idioma in TEXTOS_MEXICO.items():
        for idioma, valor in por_idioma.items():
            if (clave, idioma) not in tiene:
                db.add(m.TextoCotizacion(pais_id=pais.id, clave=clave,
                                         idioma=idioma, texto=valor))
    db.commit()


# ------------------------------------------------------------- el visto bueno del mes

NOMBRES = {"precio_mes_completo": "mensual", "precio_dia_adicional":
           "dia adicional", "precio_hora_extra": "hora extra",
           "viaticos_incluidos": "viaticos incluidos", "esquema": "esquema"}


def observaciones_del_mes(db: Session,
                          contrato: m.ContratoImplantado) -> list[dict] | None:
    """Lo que el visto bueno del mes dice de sus precios cuando el
    implantado nacio de una propuesta: que son los que el cliente
    autorizo, o en que ya no lo son. No frena: un cambio puede ser un
    acuerdo nuevo con el cliente. None si no nacio de una propuesta --se
    compara con la lista de implantados, como siempre--."""
    from app.revisor import AVISO, INFO

    cot = autorizada_de(db, contrato.servicio_id)
    if cot is None:
        return None
    pactado = terminos_del_primer_mes(db, contrato.servicio)
    distintos = []
    for campo in NOMBRES:
        del_mes, de_ella = getattr(contrato, campo), pactado[campo]
        if campo == "esquema" or campo == "viaticos_incluidos":
            if del_mes != de_ella:
                distintos.append(campo)
        elif _o_nada(del_mes) != _o_nada(de_ella):
            distintos.append(campo)
    cuando = (f"{cot.autorizada_el:%d/%m/%Y}" if cot.autorizada_el else "")
    if not distintos:
        return [{"nivel": INFO, "asunto": "Precios de la propuesta",
                 "clave": "precios_propuesta",
                 "datos": {"folio": nombre_de(cot), "el": cuando},
                 "mensaje": (f"Los términos del mes son los de la propuesta "
                             f"{nombre_de(cot)}, autorizada por el cliente "
                             f"el {cuando}"),
                 "accion": "Informativo."}]
    detalle = "; ".join(f"{NOMBRES[c]}: {_texto_de(getattr(contrato, c))} "
                        f"(la propuesta, {_texto_de(pactado[c])})"
                        for c in distintos)
    return [{"nivel": AVISO, "asunto": "Precios distintos a la propuesta",
             "clave": "precios_no_propuesta",
             "datos": {"folio": nombre_de(cot), "campos": distintos},
             "mensaje": (f"Los términos del mes no son los de la propuesta "
                         f"{nombre_de(cot)}: {detalle}"),
             "accion": ("Si el cliente aceptó otro precio, se deja así. Si no, "
                        "corrígelos en los términos del mes.")}]


def _texto_de(valor) -> str:
    if valor is None:
        return "sin precio"
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, m.EsquemaCotizacionImplantado):
        return valor.value
    return str(_dinero(valor))

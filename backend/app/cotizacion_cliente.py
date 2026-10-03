# -*- coding: utf-8 -*-
"""La cotizacion que se le manda al cliente (seccion 114).

Salvador, 30 de septiembre: la cotizacion del eventual se arma en
Connect, en una pantalla nueva que pregunta si es una propuesta para
implantado --pendiente-- o una cotizacion para eventual. Sale su PDF, el
consultor se la manda al cliente y, cuando el cliente la autoriza, pasa a
servicio eventual: el servicio se crea solo.

Sus decisiones del 1 de octubre, una por una:

  1. Folio nuevo de Connect: EP/COT-0001, con su version.
  2. Se puede cotizar a una empresa que todavia no esta en Odoo, con la
     lista general de su pais. Para autorizarla ya tiene que estar en
     Odoo con la etiqueta de Proteccion Ejecutiva: de ahi sale su factura.
  3. El cliente autoriza por correo, como hoy; el consultor registra
     quien y que dia, con el correo o el PDF firmado adjunto.
  4. El PDF lleva subtotal, IVA y total, con la tasa de cada pais en
     Catalogos; el cliente que no lleva IVA se marca en su cotizacion.
  5. Cada consultor sube su firma una vez y sale en sus cotizaciones.

Y lo que se agrego al ejemplo: la razon social y el RFC de Centauro al
pie, las condiciones de pago y facturacion, el RFC del cliente, y en la
tabla solo la modalidad --sin horario--.

Como vive. Es una `Cotizacion` sin servicio, con su folio, sus dias
(`DiaCotizacion`) y sus renglones con precio. Los precios salen de la
lista del cliente con el mismo motor que la cotizacion del servicio
(seccion 94): el paquete conductor + unidad cuando la lista lo pacta.
Mientras es borrador se puede cambiar; al mandarla, el PDF se guarda tal
como salio y lo enviado ya no cambia. Si el cliente pide cambios, se hace
la version siguiente y la anterior queda sustituida al mandar la nueva.
Cuando el cliente la autoriza, nace el servicio con el mismo alta que
Nuevo servicio y la MISMA fila queda como su cotizacion autorizada: lo
que el cliente vio es lo que compara el cierre, sin copiar precios.
"""
import json
import logging
import unicodedata
import zlib
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session, selectinload

from app import accesos, auditoria, reloj, telefonos, tipo_cambio
from app import cotizacion as motor
from app import models as m

E = m.EstatusCotizacion
SERIE = motor.SERIE
folio_texto = motor.folio_texto
registro = logging.getLogger(__name__)

# Lo que la lista cuenta como abierta, cerrada o ya resuelta.
ABIERTAS = (E.BORRADOR, E.ENVIADA)
CERRADAS = (E.RECHAZADA, E.VENCIDA)
# El cliente la puede autorizar mandada, o vencida: el consultor decide.
SE_AUTORIZAN = (E.ENVIADA, E.VENCIDA)
# De estas se puede hacer la version siguiente. La autorizada ya es del
# servicio: un cambio se recotiza alla (seccion 94).
DE_ESTAS_SALE_OTRA = (E.ENVIADA, E.VENCIDA, E.RECHAZADA)

IDIOMAS = ("es", "en", "pt")
MODALIDADES_DEL_EVENTUAL = (m.CodigoModalidad.FULL_DAY,
                            m.CodigoModalidad.MEDIO_DIA,
                            m.CodigoModalidad.TRANSFER)
CLAVES_DE_TEXTO = ("incluye_dentro", "incluye_fijo", "incluye_comprobar",
                   "pago", "aceptacion", "cancelacion", "cierre")

LARGO_NOMBRE = 160
LARGO_TIPO = 120
LARGO_INTRODUCCION = 2000
LARGO_MOTIVO = 300
LARGO_DESTINO = 120
LARGO_TEXTO = 2000
MAX_EQUIPOS = 24
MAX_DIAS = 120
MAX_CANTIDAD = 20

# Lo que trae Mexico de nacimiento: la razon social de la cotizacion de
# ejemplo de Salvador y los textos de sus condiciones. El RFC y las
# condiciones de pago se escriben en Catalogos. La migracion e3a5c7b9d1f4
# trae la misma copia; una prueba cuida que digan lo mismo.
DATOS_MEXICO = {"razon_social": "Centauro ASS, S.A. de C.V.",
                "tasa_iva": "0.1600"}
TEXTOS_MEXICO = {
    "incluye_dentro": {
        "es": "El personal y las unidades que se describen, con los gastos "
              "operativos del servicio: combustible, casetas, "
              "estacionamientos y alimentos del personal.",
        "en": "The personnel and vehicles described, including the "
              "operating expenses of the service: fuel, tolls, parking and "
              "meals for the personnel.",
        "pt": "O pessoal e as unidades descritos, com as despesas "
              "operacionais do serviço: combustível, pedágios, "
              "estacionamentos e alimentação do pessoal.",
    },
    "incluye_fijo": {
        "es": "El personal y las unidades que se describen. Los gastos "
              "operativos se cobran como el monto fijo que dice esta "
              "cotización.",
        "en": "The personnel and vehicles described. Operating expenses "
              "are charged as the fixed amount stated in this quotation.",
        "pt": "O pessoal e as unidades descritos. As despesas operacionais "
              "são cobradas como o valor fixo indicado nesta cotação.",
    },
    "incluye_comprobar": {
        "es": "El personal y las unidades que se describen. Los gastos "
              "operativos —combustible, casetas, estacionamientos, "
              "alimentos y hospedaje del personal— se facturan aparte, "
              "según lo comprobado y con su desglose.",
        "en": "The personnel and vehicles described. Operating expenses "
              "—fuel, tolls, parking, meals and lodging for the "
              "personnel— are invoiced separately, as incurred and with "
              "their breakdown.",
        "pt": "O pessoal e as unidades descritos. As despesas operacionais "
              "—combustível, pedágios, estacionamentos, alimentação e "
              "hospedagem do pessoal— são faturadas à parte, conforme "
              "comprovadas e com o seu detalhamento.",
    },
    "aceptacion": {
        "es": "Para autorizarla, responda por correo a {correo_consultor} "
              "con copia a salvador.carrasco@centauro.lat y "
              "luis.pichardo@centauro.lat, indicando el folio {folio}. "
              "Nuestros servicios se confirman diariamente: le agradecemos "
              "su aceptación con 72 horas de anticipación para agendar a "
              "nuestros elementos y vehículos.",
        "en": "To approve it, please reply by email to {correo_consultor}, "
              "copying salvador.carrasco@centauro.lat and "
              "luis.pichardo@centauro.lat, and quote reference {folio}. "
              "Our services are confirmed daily: we appreciate your "
              "approval 72 hours in advance so we can schedule our "
              "personnel and vehicles.",
        "pt": "Para aprová-la, responda por e-mail para {correo_consultor}, "
              "com cópia para salvador.carrasco@centauro.lat e "
              "luis.pichardo@centauro.lat, indicando a referência {folio}. "
              "Nossos serviços são confirmados diariamente: agradecemos a "
              "sua aprovação com 72 horas de antecedência para agendarmos "
              "nossos agentes e veículos.",
    },
    "cancelacion": {
        "es": "Si se cancela con más de 24 horas de anticipación al inicio "
              "del servicio, no hay cargo. Con menos de 24 horas, se cobra "
              "el 15% del valor del servicio.",
        "en": "Cancellations made more than 24 hours before the start of "
              "the service are free of charge. With less than 24 hours' "
              "notice, 15% of the value of the service is charged.",
        "pt": "Cancelamentos feitos com mais de 24 horas de antecedência do "
              "início do serviço não têm custo. Com menos de 24 horas, é "
              "cobrado 15% do valor do serviço.",
    },
    "cierre": {
        "es": "Agradecemos la oportunidad de presentarle esta propuesta. "
              "Quedamos a sus órdenes para cualquier duda o comentario.",
        "en": "Thank you for the opportunity to present this proposal. We "
              "remain at your disposal for any questions or comments.",
        "pt": "Agradecemos a oportunidade de apresentar esta proposta. "
              "Ficamos à disposição para qualquer dúvida ou comentário.",
    },
}

CENTAVO = Decimal("0.01")


def _dinero(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _limpio(texto: str | None, largo: int | None = None) -> str | None:
    """Sin espacios de mas; vacio es None. Con tope, al largo de su
    columna."""
    limpio = " ".join((texto or "").split()) or None
    if limpio and largo and len(limpio) > largo:
        raise HTTPException(400, f"«{limpio[:40]}…» es demasiado largo "
                                 f"(hasta {largo} letras).")
    return limpio


def nombre_de(c: m.Cotizacion) -> str:
    """EP/COT-0001 V2, o EP/PRO-0001 V2 la propuesta del implantado."""
    return f"{folio_texto(c.folio, c.clase)} V{c.version}"


# ------------------------------------------------------------- los equipos

def _alias(posicion: int) -> str:
    from app.routers.servicios import alias_de_equipo
    return alias_de_equipo(posicion)


def orden_de(clave: str) -> int:
    """La posicion de un equipo por su alias: Alfa 0, Beta 1..."""
    for i in range(MAX_EQUIPOS * 2):
        if _alias(i) == clave:
            return i
    return MAX_EQUIPOS * 2


# ------------------------------------------------------------- la lista

general_del_pais = motor.general_del_pais


def _moneda(valor) -> m.Moneda | None:
    if valor in (None, ""):
        return None
    try:
        return valor if isinstance(valor, m.Moneda) else m.Moneda(valor)
    except ValueError:
        raise HTTPException(400, f"No conozco la moneda {valor}.")


def lista_de(db: Session, cliente: m.Cliente | None,
             pais_id: int, moneda=None) -> m.Tarifario:
    """La lista con la que se cotiza: la del cliente o, para la empresa
    que todavia no esta en Odoo, la general de su pais.

    Con generales en dos monedas (seccion 120) la moneda se escoge: la
    empresa nueva y el cliente que esta en la general se cotizan con la
    general de la moneda que se escogio. El cliente con lista pactada, en
    la moneda de su lista: sus precios se pactaron en ella."""
    moneda = _moneda(moneda)
    if cliente is not None:
        tarifario = (db.get(m.Tarifario, cliente.tarifario_id)
                     if cliente.tarifario_id else None)
        if tarifario is None:
            raise HTTPException(400, {
                "mensaje": f"{cliente.nombre} no tiene lista de precios",
                "que_hacer": "En Odoo ponle su lista de precios —o la "
                             "general de su país—; Connect la lee cada hora.",
                "clave": "sin_lista"})
        if (moneda is None or not tarifario.general
                or moneda == tarifario.moneda):
            return tarifario
    tarifario = general_del_pais(db, pais_id, moneda)
    if tarifario is None:
        pais = db.get(m.Pais, pais_id)
        nombre = pais.nombre if pais else "ese país"
        raise HTTPException(400, {
            "mensaje": (f"No hay lista general de {nombre} en {moneda.value}"
                        if moneda else f"No hay lista general de {nombre}"),
            "que_hacer": "La lista general del país se marca en Odoo; "
                         "Connect la lee cada hora.",
            "clave": "sin_lista"})
    return tarifario


def monedas_a_escoger(db: Session, cliente: m.Cliente | None,
                      pais_id: int) -> list[str]:
    """Entre que monedas se escoge (seccion 120): las de las generales del
    pais, para la empresa nueva y para el cliente que esta en la general.
    Vacio si no hay que escoger: una sola general, o una lista pactada."""
    if cliente is not None:
        suya = (db.get(m.Tarifario, cliente.tarifario_id)
                if cliente.tarifario_id else None)
        if suya is None or not suya.general:
            return []
    monedas = motor.monedas_generales(db, pais_id)
    return monedas if len(monedas) > 1 else []


def _modalidades(db: Session, pais_id: int) -> dict[int, m.Modalidad]:
    return {x.id: x for x in db.query(m.Modalidad).filter(
        m.Modalidad.pais_id == pais_id,
        m.Modalidad.codigo.in_(MODALIDADES_DEL_EVENTUAL)).all()}


def hora_extra(db: Session, tarifario: m.Tarifario, perfil_ids,
               pais_id: int) -> list[dict]:
    """La hora extra de cada rol, de la lista (seccion 113): la de su
    renglon de dia completo y, si no la trae, la de toda la lista. Solo
    del dia completo, que es la que genera horas extra."""
    completo = (db.query(m.Modalidad)
                .filter_by(pais_id=pais_id,
                           codigo=m.CodigoModalidad.FULL_DAY).first())
    if completo is None or not completo.aplica_horas_extra:
        return []
    from app.cierre import hora_extra_del_rol

    salida = []
    for perfil in (db.query(m.PerfilPersonal)
                   .filter(m.PerfilPersonal.id.in_(set(perfil_ids) or {0}))
                   .order_by(m.PerfilPersonal.id).all()):
        # La misma regla que el cierre (seccion 127, hallazgos r5-04 y
        # r9-04): la de su renglon, la de su paquete si solo va en
        # paquete, y si no la de la lista; y el producto de Odoo es el
        # que guarda ese renglon (seccion 116), no el primero que diga
        # «hora extra» de ese rol: con los de Brasil confirmados, el PDF
        # en espanol decia «Motorista Executivo Bilingue».
        precio, producto_id = hora_extra_del_rol(db, tarifario.id, perfil.id,
                                                 completo)
        if precio:
            producto = None
            hora = db.get(m.ProductoOdoo, producto_id) if producto_id else None
            if hora is None:
                hora = (db.query(m.ProductoOdoo)
                        .filter_by(clase="hora_extra", perfil_id=perfil.id,
                                   confirmado=True)
                        .filter(m.ProductoOdoo.pais_id.in_((pais_id, None))
                                if pais_id else True)
                        .order_by(m.ProductoOdoo.preferido.desc(),
                                  m.ProductoOdoo.vendible.desc(),
                                  m.ProductoOdoo.id).first())
            if hora is not None:
                producto = hora.nombre
            salida.append({"perfil_id": perfil.id, "rol": perfil.nombre,
                           "producto": producto, "precio": _dinero(precio)})
    return salida


def datos_del_pais(db: Session, pais_id: int | None) -> m.DatosCotizacion | None:
    if not pais_id:
        return None
    return db.query(m.DatosCotizacion).filter_by(pais_id=pais_id).first()


def tasa_iva(db: Session, pais_id: int | None) -> Decimal | None:
    datos = datos_del_pais(db, pais_id)
    if datos is None or datos.tasa_iva is None:
        return None
    return Decimal(str(datos.tasa_iva))


def lista_info(db: Session, cliente_id: int | None,
               pais_id: int | None, moneda=None) -> dict:
    """Lo que la pantalla necesita al escoger el cliente: con que lista se
    cotiza, que roles y unidades tienen precio, las modalidades del pais,
    la hora extra de cada rol y la tasa de IVA. Y entre que monedas se
    escoge, si se escoge (seccion 120)."""
    cliente = db.get(m.Cliente, cliente_id) if cliente_id else None
    if cliente_id and cliente is None:
        raise HTTPException(404, f"No existe el cliente {cliente_id}")
    pais_id = cliente.pais_id if cliente else pais_id
    if not pais_id or db.get(m.Pais, pais_id) is None:
        raise HTTPException(400, "Di de qué país es la empresa.")
    tarifario = lista_de(db, cliente, pais_id, moneda)
    roles, unidades = motor.lo_que_tiene_precio(db, tarifario.id)
    modalidades = sorted(_modalidades(db, pais_id).values(),
                         key=lambda x: MODALIDADES_DEL_EVENTUAL.index(x.codigo))
    tasa = tasa_iva(db, pais_id)
    return {
        "pais_id": pais_id,
        "tarifario": _tarifario(tarifario),
        "monedas": monedas_a_escoger(db, cliente, pais_id),
        # La general de otra moneda que la de su ficha: se dice que se
        # escogio, no que es «la lista del cliente en Odoo».
        "escogida": bool(cliente and cliente.tarifario_id != tarifario.id),
        # La lista pactada del cliente: su moneda no se escoge.
        "pactada": bool(cliente and not tarifario.general),
        "roles": roles, "unidades": unidades,
        "modalidades": [{"id": x.id, "codigo": x.codigo.value,
                         "horas": float(x.horas)} for x in modalidades],
        "hora_extra": [{**x, "precio": float(x["precio"])} for x in hora_extra(
            db, tarifario, [r["id"] for r in roles], pais_id)],
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


def _tarifario(t: m.Tarifario) -> dict:
    return {"id": t.id, "nombre": t.nombre, "moneda": t.moneda.value,
            "general": bool(t.general),
            "paquetes_con_viaticos": bool(t.paquetes_con_viaticos)}


# ------------------------------------------------------------- la entrada

def _lleva(db: Session, crudo, donde: str) -> list[dict]:
    """[{tipo, id, cantidad}] limpio: roles y unidades que existen, sin
    cantidades raras. Lo repetido se junta."""
    junto = {}
    for item in crudo or []:
        tipo = item.get("tipo")
        if tipo not in ("recurso", "vehiculo"):
            raise HTTPException(400, f"{donde}: solo se cotizan roles y "
                                     "unidades.")
        try:
            ident = int(item.get("id") or 0)
            cantidad = int(item.get("cantidad") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{donde}: una cantidad no es un número.")
        if not ident or cantidad <= 0:
            continue
        if cantidad > MAX_CANTIDAD:
            raise HTTPException(400, f"{donde}: hasta {MAX_CANTIDAD} de cada "
                                     "rol o unidad por equipo.")
        modelo = m.PerfilPersonal if tipo == "recurso" else m.CategoriaVehiculo
        if db.get(modelo, ident) is None:
            raise HTTPException(400, f"{donde}: no existe ese "
                                     f"{'rol' if tipo == 'recurso' else 'tipo de unidad'}.")
        junto[(tipo, ident)] = junto.get((tipo, ident), 0) + cantidad
    return [{"tipo": t, "id": i, "cantidad": n}
            for (t, i), n in sorted(junto.items(),
                                    key=lambda x: (x[0][0] != "recurso", x[0][1]))]


def _equipos(db: Session, pais_id: int, crudos: list) -> list[dict]:
    """Los equipos con sus dias, limpios y con su alias por posicion."""
    if len(crudos or []) > MAX_EQUIPOS:
        raise HTTPException(400, f"Hasta {MAX_EQUIPOS} equipos por cotización.")
    modalidades = _modalidades(db, pais_id)
    salida = []
    for posicion, crudo in enumerate(crudos or []):
        clave = _alias(posicion)
        plaza_id = crudo.get("plaza_id")
        if plaza_id:
            plaza = db.get(m.Plaza, plaza_id)
            if plaza is None or plaza.pais_id != pais_id:
                raise HTTPException(400, f"Equipo {clave}: esa ciudad no es "
                                         "del país de la cotización.")
        dias, vistos = [], set()
        if len(crudo.get("dias") or []) > MAX_DIAS:
            raise HTTPException(400, f"Equipo {clave}: hasta {MAX_DIAS} días.")
        for d in crudo.get("dias") or []:
            fecha = d.get("fecha")
            if isinstance(fecha, str):
                try:
                    fecha = date.fromisoformat(fecha)
                except ValueError:
                    raise HTTPException(400, f"Equipo {clave}: una fecha no "
                                             "se entiende.")
            if not isinstance(fecha, date):
                raise HTTPException(400, f"Equipo {clave}: a un día le falta "
                                         "la fecha.")
            if fecha in vistos:
                raise HTTPException(400, f"Equipo {clave}: el {fecha:%d/%m/%Y} "
                                         "está dos veces.")
            vistos.add(fecha)
            modalidad_id = d.get("modalidad_id")
            if modalidad_id not in modalidades:
                raise HTTPException(400, f"Equipo {clave}: el {fecha:%d/%m/%Y} "
                                         "lleva una modalidad que no es del "
                                         "eventual de ese país.")
            hora = d.get("hora")
            if isinstance(hora, str):
                try:
                    hora = time.fromisoformat(hora) if hora else None
                except ValueError:
                    raise HTTPException(400, f"Equipo {clave}: la hora del "
                                             f"{fecha:%d/%m/%Y} no se entiende.")
            foraneo = bool(d.get("es_foraneo"))
            destino = _limpio(d.get("destino"), LARGO_DESTINO) if foraneo else None
            lleva = _lleva(db, d.get("lleva") if d.get("lleva") is not None
                           else crudo.get("lleva"),
                           f"Equipo {clave}, {fecha:%d/%m/%Y}")
            dias.append({"fecha": fecha, "modalidad_id": modalidad_id,
                         "hora": hora, "es_foraneo": foraneo,
                         "destino": destino, "lleva": lleva})
        dias.sort(key=lambda x: x["fecha"])
        salida.append({"clave": clave, "plaza_id": plaza_id, "dias": dias})
    return salida


def _contacto(db: Session, datos: dict, cliente: m.Cliente | None,
              pais_id: int) -> dict:
    """Quien la pide: el contacto del cliente si lo escogieron, o lo que
    se escribio --con la clave de pais en el telefono--."""
    solicitante_id = datos.get("solicitante_id")
    if solicitante_id:
        contacto = db.get(m.Solicitante, solicitante_id)
        if contacto is None:
            raise HTTPException(404, f"No existe el contacto {solicitante_id}")
        if cliente is None or contacto.cliente_id != cliente.id:
            raise HTTPException(400, "Ese contacto es de otro cliente.")
        return {"solicitante_id": contacto.id,
                "solicitante_nombre": contacto.nombre,
                "solicitante_apellidos": contacto.apellidos,
                "solicitante_correo": contacto.correo,
                "solicitante_telefono": contacto.telefono}
    return {"solicitante_id": None,
            "solicitante_nombre": _limpio(datos.get("solicitante_nombre"),
                                          LARGO_NOMBRE),
            "solicitante_apellidos": _limpio(datos.get("solicitante_apellidos"),
                                             LARGO_NOMBRE),
            "solicitante_correo": _limpio(datos.get("solicitante_correo"),
                                          LARGO_NOMBRE),
            "solicitante_telefono": telefonos.normalizar(
                db, _limpio(datos.get("solicitante_telefono"), 40), pais_id)}


def preparar(db: Session, datos: dict) -> dict:
    """Lo que manda la pantalla, revisado: el cliente o la empresa, su
    lista, quien la pide, quien la firma, los equipos y los gastos."""
    cliente = None
    if datos.get("cliente_id"):
        cliente = db.get(m.Cliente, datos["cliente_id"])
        if cliente is None:
            raise HTTPException(404, f"No existe el cliente {datos['cliente_id']}")
    pais_id = cliente.pais_id if cliente else datos.get("pais_id")
    if not pais_id or db.get(m.Pais, pais_id) is None:
        raise HTTPException(400, "Di de qué país es la empresa.")
    prospecto = None if cliente else _limpio(datos.get("prospecto"),
                                             LARGO_NOMBRE)
    if cliente is None and not prospecto:
        raise HTTPException(400, "Escoge el cliente o escribe el nombre de "
                                 "la empresa.")
    tarifario = lista_de(db, cliente, pais_id, datos.get("moneda"))

    consultor_id = datos.get("consultor_id")
    if consultor_id and not accesos.lleva_servicios(db, consultor_id):
        raise accesos.no_es_consultor(consultor_id)

    gastos = datos.get("gastos") or motor.GASTOS_COMPROBAR
    if gastos not in motor.MODOS_DE_GASTOS:
        raise HTTPException(400, "Di cómo se cobran los gastos.")
    monto = None
    if gastos == motor.GASTOS_FIJOS and datos.get("monto_gastos") not in (None, ""):
        try:
            monto = _dinero(datos.get("monto_gastos"))
        except (InvalidOperation, ValueError):
            raise HTTPException(400, "El monto fijo de gastos no es un número.")
        if monto <= 0:
            raise HTTPException(400, "El monto fijo de gastos tiene que ser "
                                     "mayor que cero.")

    idioma = datos.get("idioma") or (db.get(m.Pais, pais_id).idioma or "es")
    if idioma not in IDIOMAS:
        raise HTTPException(400, "El PDF sale en español, inglés o portugués.")

    return {
        "cliente": cliente, "cliente_id": cliente.id if cliente else None,
        "prospecto": prospecto, "pais_id": pais_id, "tarifario": tarifario,
        **_contacto(db, datos, cliente, pais_id),
        "consultor_id": consultor_id or None,
        "tipo_servicio": _limpio(datos.get("tipo_servicio"), LARGO_TIPO),
        "introduccion": (datos.get("introduccion") or "").strip() or None,
        "valida_hasta": datos.get("valida_hasta"),
        "idioma": idioma,
        "con_iva": datos.get("con_iva") is not False,
        "gastos": gastos, "monto": monto,
        "motivo": _limpio(datos.get("motivo"), LARGO_MOTIVO),
        "equipos": _equipos(db, pais_id, datos.get("equipos")),
    }


def _lineas(equipos: list[dict], gastos: str, monto) -> tuple[dict, list[dict]]:
    """{(equipo, fecha): modalidad} y los renglones que se le piden al
    motor de precios. El monto fijo de gastos va el primer dia del primer
    equipo, como en el servicio (seccion 59)."""
    modalidad_por_dia, lineas = {}, []
    for e in equipos:
        for d in e["dias"]:
            modalidad_por_dia[(e["clave"], d["fecha"])] = d["modalidad_id"]
            for i in d["lleva"]:
                lineas.append({
                    "fecha": d["fecha"], "equipo_clave": e["clave"],
                    "tipo": i["tipo"], "cantidad": i["cantidad"],
                    **({"perfil_id": i["id"]} if i["tipo"] == "recurso"
                       else {"categoria_id": i["id"]})})
    # Con monto fijo el renglon de gastos va siempre, aunque el monto
    # todavia no este escrito (seccion 129, hallazgo r1-05): en cero, el
    # borrador guarda que son gastos fijos --antes volvia a «dentro del
    # precio» al reabrirlo-- y `que_le_falta` reclama el monto antes de
    # mandarla.
    if gastos == motor.GASTOS_FIJOS and lineas:
        primero = next((e for e in equipos if e["dias"]), None)
        if primero is not None:
            lineas.append({"fecha": primero["dias"][0]["fecha"],
                           "equipo_clave": primero["clave"],
                           "tipo": m.TipoLinea.VIATICOS.value, "cantidad": 1,
                           "precio_unitario": monto or Decimal("0.00"),
                           "descripcion": "Gastos"})
    return modalidad_por_dia, lineas


def _totales(subtotal: Decimal, con_iva: bool, tasa: Decimal | None) -> dict:
    iva = (_dinero(subtotal * tasa) if con_iva and tasa is not None
           else Decimal("0.00"))
    return {"subtotal": _dinero(subtotal), "iva": iva,
            "total": _dinero(subtotal) + iva}


def _renglon_de_salida(r: dict) -> dict:
    return {"fecha": r["fecha"].isoformat(), "equipo": r["equipo_clave"],
            "tipo": m.TipoLinea(r["tipo"]).value,
            "perfil_id": r.get("perfil_id"), "categoria_id": r.get("categoria_id"),
            "descripcion": r.get("descripcion"), "producto": r.get("producto"),
            "cantidad": r["cantidad"], "precio": float(r["precio_unitario"]),
            "importe": float(r["subtotal"])}


def _como_va(db: Session, prep: dict) -> SimpleNamespace:
    """Lo que se esta armando con la forma de una cotizacion, para
    escribir su introduccion sin guardar nada."""
    plazas = {}
    dias = []
    for e in prep["equipos"]:
        if e["plaza_id"] and e["plaza_id"] not in plazas:
            plazas[e["plaza_id"]] = db.get(m.Plaza, e["plaza_id"])
        for d in e["dias"]:
            dias.append(SimpleNamespace(
                fecha=d["fecha"], equipo_clave=e["clave"],
                plaza=plazas.get(e["plaza_id"]), es_foraneo=d["es_foraneo"],
                destino=d["destino"]))
    return SimpleNamespace(
        introduccion=None, dias=dias, tipo_servicio=prep["tipo_servicio"],
        solicitante_nombre=prep["solicitante_nombre"],
        solicitante_apellidos=prep["solicitante_apellidos"],
        cliente=prep["cliente"], prospecto=prep["prospecto"])


def tiene_firma(db: Session, persona_id: int | None) -> bool:
    return bool(persona_id and db.query(m.FirmaConsultor)
                .filter_by(persona_id=persona_id).count())


def precios(db: Session, datos: dict) -> dict:
    """Los precios de lo que se esta armando, sin guardar nada.

    El nombre de la empresa nueva no cambia un precio: mientras no se
    escribe, los precios salen igual --de la lista general de su pais--.
    Tambien dice la introduccion que Connect escribiria, si quien la
    firma ya subio su firma y que le falta al PDF de Catalogos."""
    from app import cotizacion_pdf

    sin_nombre = (not datos.get("cliente_id")
                  and not (datos.get("prospecto") or "").strip())
    prep = preparar(db, {**datos, "prospecto": "—"} if sin_nombre else datos)
    modalidad_por_dia, lineas = _lineas(prep["equipos"], prep["gastos"],
                                        prep["monto"])
    renglones = (motor.renglones_con_precio(
        db, prep["tarifario"].id, modalidad_por_dia, lineas,
        con_paquetes=motor.usa_paquetes(prep["tarifario"], prep["gastos"]))
                 if lineas else [])
    subtotal = sum((r["subtotal"] for r in renglones), Decimal("0"))
    tasa = tasa_iva(db, prep["pais_id"])
    perfiles = {r["perfil_id"] for r in renglones if r.get("perfil_id")}
    como_va = _como_va(db, prep)
    return {
        "introduccion_auto": (
            cotizacion_pdf.intro_automatica(como_va, prep["idioma"], False)
            if como_va.dias and not sin_nombre else None),
        "firma": tiene_firma(db, prep["consultor_id"]),
        "faltan_textos": faltan_textos(db, prep["pais_id"], prep["idioma"],
                                       prep["con_iva"]),
        "tarifario": _tarifario(prep["tarifario"]),
        "moneda": prep["tarifario"].moneda.value,
        "lineas": [_renglon_de_salida(r) for r in renglones],
        **{k: float(v) for k, v in _totales(subtotal, prep["con_iva"],
                                            tasa).items()},
        "tasa_iva": float(tasa) if tasa is not None else None,
        "con_iva": prep["con_iva"],
        "dias": len({(r["equipo_clave"], r["fecha"]) for r in renglones
                     if r["tipo"] != m.TipoLinea.VIATICOS}),
        "equipos": len({r["equipo_clave"] for r in renglones
                        if r["tipo"] != m.TipoLinea.VIATICOS}),
        "hora_extra": [{**x, "precio": float(x["precio"])} for x in hora_extra(
            db, prep["tarifario"], perfiles, prep["pais_id"])],
    }


# ------------------------------------------------------------- guardar

def _siguiente_folio(db: Session, clase: str = motor.COTIZACION) -> int:
    """El siguiente de la serie EP/COT --o EP/PRO, la de la propuesta del
    implantado (seccion 115)--, con candado: dos consultores que arman al
    mismo tiempo no se llevan el mismo numero. Vive en la transaccion,
    como el de asignar. Cada serie lleva su candado y su cuenta."""
    db.execute(text("SELECT pg_advisory_xact_lock(:llave)"),
               {"llave": zlib.crc32(f"{clase}:folio".encode())})
    ultimo = (db.query(func.max(m.Cotizacion.folio))
              .filter(m.Cotizacion.clase == clase).scalar())
    # El de una eliminada no se vuelve a usar (seccion 126): el cliente
    # pudo recibir el PDF con ese numero.
    eliminado = (db.query(func.max(m.CotizacionEliminada.folio))
                 .filter(m.CotizacionEliminada.clase == clase).scalar())
    return max(ultimo or 0, eliminado or 0) + 1


def _poner(cot: m.Cotizacion, prep: dict) -> None:
    for campo in ("cliente_id", "prospecto", "pais_id", "solicitante_id",
                  "solicitante_nombre", "solicitante_apellidos",
                  "solicitante_correo", "solicitante_telefono",
                  "consultor_id", "tipo_servicio", "introduccion",
                  "valida_hasta", "idioma", "con_iva"):
        setattr(cot, campo, prep[campo])
    cot.motivo_recotizacion = prep["motivo"] if cot.version > 1 else None
    cot.tarifario_id = prep["tarifario"].id
    cot.moneda = prep["tarifario"].moneda
    cot.viaticos_incluidos = prep["gastos"] != motor.GASTOS_COMPROBAR


def _poner_dias(db: Session, cot: m.Cotizacion, equipos: list[dict]) -> None:
    # Los de antes se van primero: el mismo dia del mismo equipo choca
    # con su candado si el nuevo entra antes de que el viejo salga.
    cot.dias.clear()
    db.flush()
    for e in equipos:
        for d in e["dias"]:
            cot.dias.append(m.DiaCotizacion(
                equipo_clave=e["clave"], fecha=d["fecha"],
                modalidad_id=d["modalidad_id"], plaza_id=e["plaza_id"],
                hora=d["hora"], es_foraneo=d["es_foraneo"],
                destino=d["destino"], lleva=json.dumps(d["lleva"])))


def _poner_precios(db: Session, cot: m.Cotizacion, prep: dict,
                   estricto: bool) -> dict | None:
    """Los renglones con el precio de hoy de la lista. Si algo no tiene
    precio: mandandola, no se manda; en borrador se guarda sin renglones
    y la pantalla dice que falta."""
    modalidad_por_dia, lineas = _lineas(prep["equipos"], prep["gastos"],
                                        prep["monto"])
    # El paquete «Todo incluido» solo con los gastos dentro del precio
    # (seccion 115, `motor.usa_paquetes`).
    paquetes = motor.usa_paquetes(prep["tarifario"], prep["gastos"])
    error = None
    try:
        renglones = (motor.renglones_con_precio(
            db, prep["tarifario"].id, modalidad_por_dia, lineas,
            con_paquetes=paquetes)
            if lineas else [])
    except HTTPException as fallo:
        if estricto:
            raise
        # El monto fijo de gastos si tiene precio --lo escribio el
        # consultor--: se queda, para que el borrador no olvide su modo.
        error = fallo.detail
        gastos = [x for x in lineas if x["tipo"] == m.TipoLinea.VIATICOS.value]
        renglones = (motor.renglones_con_precio(
            db, prep["tarifario"].id, modalidad_por_dia, gastos,
            con_paquetes=paquetes)
            if gastos else [])
    cot.lineas.clear()
    for r in renglones:
        cot.lineas.append(m.LineaCotizacion(**r))
    cot.total = sum((r["subtotal"] for r in renglones), Decimal("0"))
    return error


def guardar(db: Session, actor: m.Usuario, datos: dict,
            cot: m.Cotizacion | None = None) -> tuple[m.Cotizacion, dict | None]:
    """El borrador: nuevo, con su folio, o el mismo con lo que cambio."""
    prep = preparar(db, datos)
    if cot is None:
        cot = m.Cotizacion(folio=_siguiente_folio(db), version=1,
                           estatus=E.BORRADOR,
                           creada_por_id=actor.persona_id)
        db.add(cot)
    elif cot.estatus != E.BORRADOR:
        raise HTTPException(409, {
            "mensaje": f"La {nombre_de(cot)} ya se mandó: lo enviado no cambia",
            "que_hacer": "Haz la versión siguiente para cambiarla."})
    _poner(cot, prep)
    _poner_dias(db, cot, prep["equipos"])
    error = _poner_precios(db, cot, prep, estricto=False)
    cot.tasa_iva = tasa_iva(db, prep["pais_id"])
    cot.actualizada_en = _ahora()
    db.flush()
    return cot, error


# ------------------------------------------------------------- leer

def lleva_de(dia: m.DiaCotizacion) -> list[dict]:
    try:
        return json.loads(dia.lleva or "[]")
    except ValueError:
        return []


def equipos_de(cot: m.Cotizacion) -> list[dict]:
    """Los equipos como los manda la pantalla: con su ciudad y sus dias."""
    porclave = {}
    for d in sorted(cot.dias, key=lambda x: (orden_de(x.equipo_clave), x.fecha)):
        e = porclave.setdefault(d.equipo_clave, {
            "clave": d.equipo_clave, "plaza_id": d.plaza_id,
            "plaza": d.plaza.nombre if d.plaza else None, "dias": []})
        e["dias"].append({
            "fecha": d.fecha.isoformat(), "modalidad_id": d.modalidad_id,
            "modalidad": d.modalidad.codigo.value if d.modalidad else None,
            "hora": d.hora.strftime("%H:%M") if d.hora else None,
            "es_foraneo": d.es_foraneo, "destino": d.destino,
            "lleva": lleva_de(d)})
    return list(porclave.values())


def datos_de(cot: m.Cotizacion) -> dict:
    """Lo que se guardo, en la forma en que lo manda la pantalla: con esto
    se arma la version siguiente y se vuelve a cotizar al mandarla."""
    return {
        "cliente_id": cot.cliente_id, "prospecto": cot.prospecto,
        "pais_id": cot.pais_id, "solicitante_id": cot.solicitante_id,
        "solicitante_nombre": cot.solicitante_nombre,
        "solicitante_apellidos": cot.solicitante_apellidos,
        "solicitante_correo": cot.solicitante_correo,
        "solicitante_telefono": cot.solicitante_telefono,
        "consultor_id": cot.consultor_id, "tipo_servicio": cot.tipo_servicio,
        "introduccion": cot.introduccion, "valida_hasta": cot.valida_hasta,
        "idioma": cot.idioma, "con_iva": cot.con_iva,
        "moneda": cot.moneda.value if cot.moneda else None,
        "gastos": motor.modo_de_gastos(cot),
        "monto_gastos": gastos_fijos(cot) or None,
        "motivo": cot.motivo_recotizacion,
        "equipos": [{"plaza_id": e["plaza_id"],
                     "dias": [{**d, "fecha": date.fromisoformat(d["fecha"]),
                               "hora": d["hora"]} for d in e["dias"]]}
                    for e in equipos_de(cot)],
    }


def gastos_fijos(cot: m.Cotizacion) -> Decimal:
    return sum((Decimal(str(l.subtotal)) for l in cot.lineas
                if l.tipo == m.TipoLinea.VIATICOS), Decimal("0"))


def totales(cot: m.Cotizacion) -> dict:
    tasa = (Decimal(str(cot.tasa_iva)) if cot.tasa_iva is not None else None)
    return _totales(Decimal(str(cot.total or 0)), cot.con_iva, tasa)


def versiones(db: Session, folio: int,
              clase: str = motor.COTIZACION) -> list[m.Cotizacion]:
    """Las versiones de un folio, de la mas nueva a la primera. El numero
    solo no basta: la EP/COT-0001 y la EP/PRO-0001 son dos."""
    return (db.query(m.Cotizacion).filter_by(folio=folio, clase=clase)
            .order_by(m.Cotizacion.version.desc()).all())


def ultima(db: Session, folio: int,
           clase: str = motor.COTIZACION) -> m.Cotizacion:
    return versiones(db, folio, clase)[0]


def de_folio(db: Session, cotizacion_id: int,
             clase: str = motor.COTIZACION) -> m.Cotizacion:
    cot = db.get(m.Cotizacion, cotizacion_id)
    if cot is None or cot.folio is None or cot.clase != clase:
        raise HTTPException(404, (f"No existe la propuesta {cotizacion_id}"
                                  if clase == motor.PROPUESTA else
                                  f"No existe la cotización {cotizacion_id}"))
    return cot


def cliente_texto(cot: m.Cotizacion) -> str:
    return cot.cliente.nombre if cot.cliente else (cot.prospecto or "—")


def _hoy(db: Session, cot: m.Cotizacion) -> date:
    return reloj.Relojes(db).hoy(cot.pais_id)


# ------------------------------------------------------------- mandarla

def que_le_falta(db: Session, cot: m.Cotizacion) -> list[str]:
    """Lo que impide mandarla, en palabras del consultor."""
    faltan = []
    if not (cot.solicitante_nombre or "").strip():
        faltan.append("El nombre de quien la pide")
    if not cot.consultor_id:
        faltan.append("Quien la firma")
    if not cot.valida_hasta:
        faltan.append("Hasta cuándo es válida")
    elif cot.valida_hasta < _hoy(db, cot):
        faltan.append("Una fecha de «válida hasta» que no haya pasado")
    if not cot.dias:
        faltan.append("Al menos un día")
    else:
        if any(not d.plaza_id for d in cot.dias):
            faltan.append("La ciudad de cada equipo")
        if any(not lleva_de(d) for d in cot.dias):
            faltan.append("Lo que lleva cada día")
    if cot.version > 1 and not cot.motivo_recotizacion:
        faltan.append("Qué cambió en esta versión")
    if (motor.modo_de_gastos(cot) == motor.GASTOS_FIJOS
            and not gastos_fijos(cot) > 0):
        faltan.append("El monto fijo de gastos")
    faltan += lo_del_pais_que_frena(db, cot.pais_id, cot.idioma or "es",
                                    cot.con_iva)
    return faltan


def lo_del_pais_que_frena(db: Session, pais_id: int | None, idioma: str,
                          con_iva) -> list[str]:
    """Lo de Catalogos sin lo que una cotizacion o una propuesta no se
    manda (seccion 130, decision 15): la tasa de IVA, si va con IVA, y las
    condiciones de pago y facturacion del pais en el idioma del PDF. Lo
    demas que le falte al PDF se avisa en amarillo y deja mandar; esto
    no: una cotizacion de Brasil salia sin tasa ni condiciones."""
    if not pais_id:
        return []
    d = textos_de(db, pais_id)
    faltan = []
    if con_iva is not False and d["tasa_iva"] is None:
        faltan.append("La tasa de IVA del país, en Catálogos → Cotización "
                      "al cliente")
    if not d["textos"]["pago"].get(idioma, "").strip():
        faltan.append("Las condiciones de pago y facturación del país en "
                      f"{NOMBRE_IDIOMA.get(idioma, idioma)}, en Catálogos → "
                      "Cotización al cliente")
    return faltan


NOMBRE_IDIOMA = {"es": "español", "en": "inglés", "pt": "portugués"}


def enviar(db: Session, actor: m.Usuario, cot: m.Cotizacion) -> m.Cotizacion:
    """La deja mandada: se vuelve a cotizar con la lista de hoy, se arma el
    PDF y se guarda tal como sale. Las versiones de antes que seguian
    abiertas quedan sustituidas."""
    from app import cotizacion_pdf

    if cot.estatus != E.BORRADOR:
        raise HTTPException(409, f"La {nombre_de(cot)} ya se mandó.")
    if ultima(db, cot.folio, cot.clase).id != cot.id:
        raise HTTPException(409, "Ya hay una versión más nueva de esta "
                                 "cotización.")
    faltan = que_le_falta(db, cot)
    if faltan:
        raise HTTPException(400, {
            "mensaje": "Le falta: " + "; ".join(faltan).lower(),
            "que_hacer": "Complétalo y vuelve a mandarla.",
            "faltan": faltan})
    prep = preparar(db, datos_de(cot))
    _poner_precios(db, cot, prep, estricto=True)
    if not cot.lineas:
        raise HTTPException(400, "La cotización no lleva nada: di qué lleva "
                                 "cada día.")
    # La lista y la moneda son las de hoy, igual que los precios (seccion
    # 127, hallazgo r1-03): si entre guardar y mandar al cliente le llego
    # su lista pactada, el PDF, el cierre y la factura la leen.
    cot.tarifario_id = prep["tarifario"].id
    cot.moneda = prep["tarifario"].moneda
    cot.tasa_iva = tasa_iva(db, cot.pais_id)
    cot.estatus = E.ENVIADA
    cot.enviada_en = _ahora()
    cot.enviada_por_id = actor.persona_id
    cot.actualizada_en = cot.enviada_en
    db.flush()
    contenido = cotizacion_pdf.pdf(db, cot)
    pdf = m.ArchivoCotizacion(
        clase="pdf", nombre=cotizacion_pdf.nombre_del_archivo(db, cot),
        tipo="application/pdf", tamano=len(contenido), contenido=contenido,
        subido_por_id=actor.persona_id)
    cot.archivos.append(pdf)
    for vieja in versiones(db, cot.folio, cot.clase):
        if vieja.id != cot.id and vieja.estatus in (E.BORRADOR, E.ENVIADA,
                                                    E.VENCIDA):
            vieja.estatus = E.SUSTITUIDA
    db.flush()
    # El titular se entera si la mando otro (decision 16).
    avisar_al_titular(db, actor, cot, pdf)
    return cot


def avisar_al_titular(db: Session, actor: m.Usuario, cot: m.Cotizacion,
                      pdf: m.ArchivoCotizacion | None) -> dict | None:
    """Cuando quien la manda no es el consultor titular, el titular se
    entera (seccion 131, decision 16 de Salvador): la cotizacion --o la
    propuesta-- salio al cliente con su firma y su contacto, y le llega
    el aviso al correo con el PDF tal como salio, y al telefono. Quien
    arma sigue pudiendo mandarla. Solo escribe; quien llama guarda.
    Devuelve a quien se le aviso, o None si no habia a quien."""
    from app import correo_html, push
    from app import textos_aviso as ta

    if not cot.consultor_id or cot.consultor_id == actor.persona_id:
        return None
    titular = db.get(m.Persona, cot.consultor_id)
    if titular is None:
        return None
    quien = (db.get(m.Persona, actor.persona_id) if actor.persona_id else None)
    nombre_de_quien = (quien.nombre if quien else None) or actor.correo or "—"
    nombre, cliente = nombre_de(cot), cliente_texto(cot)
    lengua = push.idioma_de(db, titular.id)
    pantalla = ("/consola/#/propuesta/" if cot.clase == motor.PROPUESTA
                else "/consola/#/cotizacion/") + str(cot.id)
    avisado = {"persona_id": titular.id, "nombre": titular.nombre,
               "correo": False, "telefono": 0}
    if titular.correo:
        pares = [(ta.t(lengua, "ctz_otro_nombre"), nombre),
                 (ta.t(lengua, "ctz_otro_cliente"), cliente),
                 (ta.t(lengua, "ctz_otro_quien"), nombre_de_quien),
                 (ta.t(lengua, "cie_que_hacer"),
                  ta.t(lengua, "ctz_otro_que_hacer", quien=nombre_de_quien))]
        db.add(m.Notificacion(
            servicio_id=cot.servicio_id,
            destinatario=m.Destinatario.CONSULTOR, canal=m.Canal.CORREO,
            correo=titular.correo, idioma=lengua,
            asunto=ta.t(lengua, "ctz_otro_asunto", nombre=nombre,
                        quien=nombre_de_quien)[:200],
            cuerpo=ta.t(lengua, "ctz_otro_cuerpo", nombre=nombre,
                        quien=nombre_de_quien, cliente=cliente)[:2000],
            datos=correo_html.guardar_datos(pares),
            enlace_seguimiento=pantalla,
            adjunto_id=pdf.id if pdf is not None else None))
        avisado["correo"] = True
    try:
        r = push.avisar(
            db, titular.id,
            titulo=push.tx(lengua, "ctz_otro_titulo", nombre=nombre,
                           quien=nombre_de_quien),
            cuerpo=push.tx(lengua, "ctz_otro_cuerpo", cliente=cliente),
            url=pantalla, etiqueta=f"cotizacion-{cot.id}")
        avisado["telefono"] = r.get("enviados", 0)
    except Exception:                                   # noqa: BLE001
        # Un aviso que no sale no deshace el envio al cliente.
        registro.exception("no se pudo avisar al titular de %s", nombre)
    # Y en la bitacora de administracion: quien mando que con la firma
    # de quien, y que el titular se entero.
    accesos.anotar(db, actor, "mandada con la firma de otro",
                   "propuesta" if cot.clase == motor.PROPUESTA else "cotizacion",
                   cot.folio,
                   antes=f"titular {titular.nombre}"[:200],
                   despues=("avisado por correo con el PDF" if avisado["correo"]
                            else "titular sin correo: solo al telefono")[:200],
                   detalle=f"{nombre} · {cliente}"[:400])
    return avisado


def archivo(cot: m.Cotizacion, clase: str) -> m.ArchivoCotizacion | None:
    return next((a for a in sorted(cot.archivos, key=lambda x: x.id,
                                   reverse=True) if a.clase == clase), None)


# ------------------------------------------------------------- la siguiente

def nueva_version(db: Session, actor: m.Usuario,
                  cot: m.Cotizacion) -> m.Cotizacion:
    """La version siguiente, como borrador, copiando la de antes. La de
    antes sigue valiendo hasta que se mande la nueva."""
    if ultima(db, cot.folio, cot.clase).id != cot.id:
        raise HTTPException(409, "Ya hay una versión más nueva de esta "
                                 "cotización: cámbiala a ella.")
    if cot.estatus not in DE_ESTAS_SALE_OTRA:
        if cot.estatus == E.AUTORIZADA:
            raise HTTPException(409, {
                "mensaje": "Ya la autorizó el cliente: es la cotización de "
                           f"su servicio {cot.servicio_folio or ''}".strip(),
                "que_hacer": "Si el cliente cambió algo, se recotiza en el "
                             "servicio."})
        raise HTTPException(409, "Esta versión todavía es borrador: cámbiala "
                                 "a ella.")
    nueva = m.Cotizacion(folio=cot.folio, version=cot.version + 1,
                         estatus=E.BORRADOR, creada_por_id=actor.persona_id,
                         tarifario_id=cot.tarifario_id, moneda=cot.moneda,
                         viaticos_incluidos=cot.viaticos_incluidos,
                         total=cot.total, tasa_iva=cot.tasa_iva)
    for campo in ("cliente_id", "prospecto", "pais_id", "solicitante_id",
                  "solicitante_nombre", "solicitante_apellidos",
                  "solicitante_correo", "solicitante_telefono",
                  "consultor_id", "tipo_servicio", "introduccion",
                  "valida_hasta", "idioma", "con_iva"):
        setattr(nueva, campo, getattr(cot, campo))
    for d in cot.dias:
        nueva.dias.append(m.DiaCotizacion(
            equipo_clave=d.equipo_clave, fecha=d.fecha,
            modalidad_id=d.modalidad_id, plaza_id=d.plaza_id, hora=d.hora,
            es_foraneo=d.es_foraneo, destino=d.destino, lleva=d.lleva))
    for l in cot.lineas:
        nueva.lineas.append(m.LineaCotizacion(
            fecha=l.fecha, equipo_clave=l.equipo_clave,
            modalidad_id=l.modalidad_id, tipo=l.tipo, perfil_id=l.perfil_id,
            categoria_id=l.categoria_id, cantidad=l.cantidad,
            precio_unitario=l.precio_unitario, subtotal=l.subtotal,
            descripcion=l.descripcion, producto=l.producto))
    nueva.actualizada_en = _ahora()
    db.add(nueva)
    db.flush()
    return nueva


def rechazar(db: Session, actor: m.Usuario, cot: m.Cotizacion,
             motivo: str | None) -> m.Cotizacion:
    if cot.estatus not in SE_AUTORIZAN:
        raise HTTPException(409, "Solo se rechaza la que se le mandó al "
                                 "cliente.")
    motivo = _limpio(motivo, LARGO_MOTIVO)
    if not motivo:
        raise HTTPException(400, "Di por qué la rechazó: sirve para saber "
                                 "por qué se pierden.")
    cot.estatus = E.RECHAZADA
    cot.rechazada_en = _ahora()
    cot.rechazo_motivo = motivo
    db.flush()
    return cot


# ------------------------------------------------------------- autorizarla


def _nacer_servicio(db: Session, cot: m.Cotizacion, cliente: m.Cliente,
                    actor: m.Usuario) -> m.Servicio:
    """El servicio de la cotizacion, con el mismo alta que Nuevo servicio:
    el cliente, quien la pidio, el consultor y los equipos con su ciudad y
    sus dias con su modalidad, hora y foraneo."""
    from app import schemas as s
    from app.routers import servicios as rutas_servicios

    equipos = equipos_de(cot)
    if not equipos or any(not e["plaza_id"] for e in equipos):
        raise HTTPException(400, "Cada equipo necesita su ciudad.")
    suyo = (db.get(m.Solicitante, cot.solicitante_id)
            if cot.solicitante_id else None)
    contacto = suyo.id if suyo is not None and suyo.cliente_id == cliente.id \
        else None
    consultor_id = (cot.consultor_id if cot.consultor_id
                    and accesos.lleva_servicios(db, cot.consultor_id)
                    else None)
    datos = s.ServicioIn(
        cliente_id=cliente.id, pais_id=cot.pais_id,
        plaza_id=equipos[0]["plaza_id"], tipo=m.TipoServicio.EVENTUAL,
        consultor_id=consultor_id, solicitante_id=contacto,
        solicitante_nombre=None if contacto else cot.solicitante_nombre,
        solicitante_apellidos=None if contacto else cot.solicitante_apellidos,
        solicitante_correo=None if contacto else cot.solicitante_correo,
        solicitante_telefono=None if contacto else cot.solicitante_telefono,
        idioma_solicitante=cot.idioma,
        equipos=[s.EquipoIn(plaza_id=e["plaza_id"], jornadas=[
            s.JornadaIn(fecha=date.fromisoformat(d["fecha"]),
                        modalidad_id=d["modalidad_id"],
                        hora_presentacion=(time.fromisoformat(d["hora"])
                                           if d["hora"] else None),
                        es_foraneo=d["es_foraneo"])
            for d in e["dias"]]) for e in equipos])
    servicio, _pendientes = rutas_servicios.dar_de_alta(db, datos, actor)
    return servicio


def autorizar(db: Session, actor: m.Usuario, cot: m.Cotizacion,
              autorizada_por: str | None, autorizada_el: date | None,
              cliente_id: int | None = None,
              comprobante: tuple | None = None) -> m.Servicio:
    """El cliente dijo que si: nace el servicio con lo cotizado.

    Mismo alta que Nuevo servicio --cliente, quien la pidio, el
    consultor, los equipos con su ciudad y sus dias con su modalidad,
    hora y foraneo--, y esta MISMA cotizacion queda como la autorizada del
    servicio, con los precios que el cliente vio. Le falta el principal y
    el punto de inicio: se completa como cualquier servicio.

    La empresa que se cotizo sin estar en Odoo ya tiene que estar: se
    escoge el cliente que le corresponde (decision 2). Si algo falla --el
    tipo de cambio que falta, por ejemplo-- no queda nada.
    """
    if cot.estatus not in SE_AUTORIZAN:
        if cot.estatus == E.BORRADOR:
            raise HTTPException(409, "Primero se manda: el cliente autoriza "
                                     "lo que vio.")
        raise HTTPException(409, f"La {nombre_de(cot)} está "
                                 f"{cot.estatus.value}: ya no se autoriza.")
    if ultima(db, cot.folio, cot.clase).id != cot.id:
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

    quien = _limpio(autorizada_por, motor.LARGO_QUIEN)
    if not quien:
        raise HTTPException(400, "Di quién la autorizó del lado del cliente.")
    if autorizada_el is None:
        raise HTTPException(400, "Falta el día en que el cliente la autorizó.")
    if autorizada_el > _hoy(db, cot):
        raise HTTPException(400, "El día en que el cliente la autorizó no "
                                 "puede ser después de hoy.")
    # El tipo de cambio antes que nada: sin el, la cotizacion en dolares
    # no se autoriza (seccion 82), y mejor decirlo antes de armar nada.
    local = tipo_cambio.local_del_pais(db, cot.pais_id)
    if local and cot.moneda != local:
        tc = (tipo_cambio.vigente(db, cot.moneda, local)
              if tipo_cambio.se_puede(cot.moneda, local) else None)
        if tc is None:
            raise HTTPException(409, motor.sin_tipo_de_cambio(db, cot.moneda,
                                                              local))

    servicio = _nacer_servicio(db, cot, cliente, actor)

    cot.cliente_id = cliente.id
    cot.servicio_id = servicio.id
    cot.servicio = servicio
    motor._autorizar(db, cot, quien, autorizada_el, None)
    # Toda la historia de la cotizacion queda con su servicio: el bloque
    # del servicio ensena sus versiones, y una recotizacion alla sigue
    # con el mismo folio y la version siguiente.
    for otra in versiones(db, cot.folio, cot.clase):
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
    auditoria.registrar(db, actor, servicio, "alta desde la cotizacion",
                        f"{nombre_de(cot)} · autorizada por {quien} el "
                        f"{autorizada_el:%d/%m/%Y}")
    return servicio


# ------------------------------------------------------------- su servicio se elimino

def servicio_eliminado(cot: m.Cotizacion) -> bool:
    """La autorizada cuyo servicio se elimino despues (seccion 126): se
    queda con el folio que tuvo y sin servicio. Antes se quedaba atorada:
    ni otra version --ya estaba autorizada-- ni su servicio. Desde la
    seccion 131 tambien la propuesta cuyo implantado se elimino
    (decision 2 de Salvador, 2 de octubre)."""
    return (cot.estatus == E.AUTORIZADA and cot.servicio_id is None
            and bool(cot.servicio_folio))


def _del_servicio_eliminado(db: Session, cot: m.Cotizacion) -> None:
    if not servicio_eliminado(cot):
        raise HTTPException(409, "Solo con la propuesta autorizada cuyo "
                                 "implantado se eliminó."
                                 if cot.clase == motor.PROPUESTA else
                                 "Solo con la cotización autorizada cuyo "
                                 "servicio se eliminó.")
    if ultima(db, cot.folio, cot.clase).id != cot.id:
        raise HTTPException(409, "Hay una versión más nueva de esta "
                                 + ("propuesta." if cot.clase == motor.PROPUESTA
                                    else "cotización."))


def recrear_servicio(db: Session, actor: m.Usuario,
                     cot: m.Cotizacion) -> m.Servicio:
    """Vuelve a nacer su servicio (seccion 126), con lo mismo que la
    primera vez y la misma autorizacion: quien, cuando, el comprobante y
    el tipo de cambio que quedo fijo no se tocan. El servicio lleva folio
    nuevo; el que se elimino queda en su bitacora de eliminados."""
    _del_servicio_eliminado(db, cot)
    cliente = cot.cliente
    if cliente is None or not cliente.activo:
        raise HTTPException(409, "Su cliente ya no está activo en Connect.")
    antes = cot.servicio_folio
    servicio = _nacer_servicio(db, cot, cliente, actor)
    cot.servicio_id = servicio.id
    cot.servicio = servicio
    # Nace autorizado, como al autorizarla.
    if servicio.estatus in (m.EstatusServicio.BORRADOR,
                            m.EstatusServicio.SOLICITADO,
                            m.EstatusServicio.COTIZADO):
        servicio.estatus = m.EstatusServicio.AUTORIZADO
    for otra in versiones(db, cot.folio, cot.clase):
        otra.servicio_folio = servicio.folio
        otra.servicio_id = servicio.id
    db.flush()
    auditoria.registrar(db, actor, servicio, "alta desde la cotizacion",
                        f"{nombre_de(cot)} · otra vez: su servicio {antes} "
                        "se había eliminado")
    return servicio


def eliminar(db: Session, actor: m.Usuario, cot: m.Cotizacion,
             motivo: str | None) -> str:
    """La que ya no va (seccion 126): se van todas sus versiones, con sus
    PDF. Queda su renglon --que era, quien la quito y por que-- y su folio
    no se vuelve a usar."""
    _del_servicio_eliminado(db, cot)
    motivo = _limpio(motivo, LARGO_MOTIVO)
    if not motivo:
        raise HTTPException(400, "Di por qué se elimina.")
    nombre = nombre_de(cot)
    todas = versiones(db, cot.folio, cot.clase)
    que = "implantado" if cot.clase == motor.PROPUESTA else "servicio"
    db.add(m.CotizacionEliminada(
        clase=cot.clase, folio=cot.folio,
        cliente=cliente_texto(cot)[:200],
        resumen=(f"{nombre} · {len(todas)} versión(es) · autorizada; su "
                 f"{que} {cot.servicio_folio} se había eliminado")[:400],
        motivo=motivo, eliminado_por_id=actor.persona_id))
    for v in todas:
        db.delete(v)
    db.flush()
    return nombre


def descartar(db: Session, actor: m.Usuario, cot: m.Cotizacion) -> dict:
    """«Descartar este borrador» (seccion 131, decision 1 de Salvador, 2 de
    octubre). La version 2 o siguiente se borra y la anterior vuelve a
    ser la ultima: la V1 que el cliente autorizo tal como la vio se puede
    autorizar otra vez. La version 1 que nunca se mando se elimina con su
    registro, y su folio no se vuelve a usar. Antes un borrador abierto
    por error vivia para siempre en «Abiertas» y bloqueaba la anterior."""
    if cot.estatus != E.BORRADOR:
        raise HTTPException(409, f"La {nombre_de(cot)} ya no es borrador: "
                                 "no se descarta.")
    if ultima(db, cot.folio, cot.clase).id != cot.id:
        raise HTTPException(409, "Hay una versión más nueva de esta "
                                 + ("propuesta." if cot.clase == motor.PROPUESTA
                                    else "cotización."))
    nombre, folio, version = nombre_de(cot), cot.folio, cot.version
    anteriores = [v for v in versiones(db, folio, cot.clase) if v.id != cot.id]
    objeto = "propuesta" if cot.clase == motor.PROPUESTA else "cotizacion"
    if anteriores:
        vuelve = anteriores[0]
        accesos.anotar(db, actor, "version descartada", objeto, folio,
                       antes=f"V{version} en borrador"[:200],
                       despues=f"V{vuelve.version} vuelve a ser la última "
                               f"({vuelve.estatus.value})"[:200],
                       detalle=nombre[:400])
        db.delete(cot)
        db.flush()
        return {"resultado": "borrador descartado", "nombre": nombre,
                "folio": folio, "version": version,
                "vuelve": {"id": vuelve.id, "version": vuelve.version,
                           "estatus": vuelve.estatus.value},
                "eliminada": False}
    db.add(m.CotizacionEliminada(
        clase=cot.clase, folio=folio, cliente=cliente_texto(cot)[:200],
        resumen=f"{nombre} · borrador que nunca se mandó, descartado"[:400],
        motivo=None, eliminado_por_id=actor.persona_id))
    accesos.anotar(db, actor, "borrador descartado", objeto, folio,
                   antes="V1 en borrador, nunca mandada"[:200],
                   despues="eliminada; su folio no se vuelve a usar"[:200],
                   detalle=nombre[:400])
    db.delete(cot)
    db.flush()
    return {"resultado": "borrador descartado", "nombre": nombre,
            "folio": folio, "version": version, "vuelve": None,
            "eliminada": True}


# ------------------------------------------------------------- el reloj

def vencer(db: Session) -> dict:
    """Las mandadas que pasaron su «valida hasta» sin respuesta. Cada
    noche; idempotente: la vencida ya no esta mandada."""
    relojes = reloj.Relojes(db)
    vencidas = 0
    for cot in (db.query(m.Cotizacion)
                .filter(m.Cotizacion.estatus == E.ENVIADA,
                        m.Cotizacion.folio.isnot(None),
                        m.Cotizacion.valida_hasta.isnot(None)).all()):
        if cot.valida_hasta < relojes.hoy(cot.pais_id):
            cot.estatus = E.VENCIDA
            vencidas += 1
    db.commit()
    return {"vencidas": vencidas}


# ------------------------------------------------------------- la lista

VISTAS = {
    "abiertas": ABIERTAS,
    "autorizadas": (E.AUTORIZADA,),
    "cerradas": CERRADAS,
    "todas": None,
}


def _sin_tildes(texto: str) -> str:
    limpio = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in limpio if unicodedata.category(c) != "Mn")


def renglon_de_lista(cot: m.Cotizacion) -> dict:
    if cot.clase == motor.PROPUESTA:
        from app import propuesta
        return propuesta.renglon_de_lista(cot)
    fechas = sorted({d.fecha for d in cot.dias})
    t = totales(cot)
    return {
        "id": cot.id, "clase": cot.clase,
        "folio": folio_texto(cot.folio), "version": cot.version,
        "estatus": cot.estatus.value,
        "cliente": cliente_texto(cot), "es_prospecto": cot.cliente_id is None,
        "solicitante": m._nombre_completo(cot.solicitante_nombre,
                                          cot.solicitante_apellidos),
        "consultor": cot.consultor.nombre if cot.consultor else None,
        "desde": fechas[0].isoformat() if fechas else None,
        "hasta": fechas[-1].isoformat() if fechas else None,
        "total": float(t["total"]), "moneda": cot.moneda.value,
        "valida_hasta": cot.valida_hasta.isoformat() if cot.valida_hasta else None,
        "enviada_en": cot.enviada_en.isoformat() if cot.enviada_en else None,
        "autorizada_por": cot.autorizada_por,
        "autorizada_el": (cot.autorizada_el.isoformat()
                          if cot.autorizada_el else None),
        "rechazo_motivo": cot.rechazo_motivo,
        "servicio": ({"id": cot.servicio.id, "folio": cot.servicio.folio}
                     if cot.servicio else None),
        "servicio_folio": cot.servicio_folio,
    }


# Que se lista (seccion 115): las cotizaciones del eventual, las
# propuestas del implantado, o las dos.
QUE = {"todas": None, "cotizaciones": motor.COTIZACION,
       "propuestas": motor.PROPUESTA}


def _de_que(consulta, que: str):
    if que not in QUE:
        raise HTTPException(400, "Eso no se lista.")
    if QUE[que] is not None:
        consulta = consulta.filter(m.Cotizacion.clase == QUE[que])
    return consulta


def lista(db: Session, vista: str = "todas", q: str | None = None,
          que: str = "cotizaciones") -> list[dict]:
    """Una por folio: su ultima version. La mas nueva arriba: el orden en
    que nacio cada folio, que con dos series ya no es su numero."""
    if vista not in VISTAS:
        raise HTTPException(400, "Esa vista no existe.")
    todas = (_de_que(db.query(m.Cotizacion), que)
             .options(selectinload(m.Cotizacion.dias),
                      selectinload(m.Cotizacion.posiciones),
                      selectinload(m.Cotizacion.cliente),
                      selectinload(m.Cotizacion.servicio),
                      selectinload(m.Cotizacion.consultor))
             .filter(m.Cotizacion.folio.isnot(None))
             .order_by(m.Cotizacion.clase, m.Cotizacion.folio.desc(),
                       m.Cotizacion.version.desc()).all())
    ultimas, primera = [], {}
    for cot in todas:
        llave = (cot.clase, cot.folio)
        if llave not in primera:
            ultimas.append(cot)
            primera[llave] = cot.id
        primera[llave] = min(primera[llave], cot.id)
    ultimas.sort(key=lambda c: primera[(c.clase, c.folio)], reverse=True)
    estatus = VISTAS[vista]
    if estatus is not None:
        ultimas = [c for c in ultimas if c.estatus in estatus]
    if q and q.strip():
        buscado = _sin_tildes(q.strip())
        ultimas = [c for c in ultimas if buscado in _sin_tildes(" ".join(filter(None, (
            folio_texto(c.folio, c.clase), cliente_texto(c),
            c.solicitante_nombre, c.solicitante_apellidos,
            c.servicio_folio))))]
    return [renglon_de_lista(c) for c in ultimas]


def cuentas(db: Session, que: str = "cotizaciones") -> dict:
    """Cuantas hay en cada vista, para las pestanas."""
    salida = {k: 0 for k in VISTAS}
    vistos = set()
    for clase, folio, version, estatus in (
            _de_que(db.query(m.Cotizacion.clase, m.Cotizacion.folio,
                             m.Cotizacion.version, m.Cotizacion.estatus), que)
            .filter(m.Cotizacion.folio.isnot(None))
            .order_by(m.Cotizacion.clase, m.Cotizacion.folio,
                      m.Cotizacion.version.desc())):
        if (clase, folio) in vistos:
            continue
        vistos.add((clase, folio))
        salida["todas"] += 1
        for vista, cuales in VISTAS.items():
            if cuales is not None and estatus in cuales:
                salida[vista] += 1
    return salida


# ------------------------------------------------------------- el detalle

def dias_pasados(db: Session, cot: m.Cotizacion) -> dict:
    """{n, desde, hasta}: cuantos dias de la cotizacion ya pasaron con el
    hoy de su pais, y entre que fechas."""
    hoy = _hoy(db, cot)
    fechas = sorted({d.fecha for d in cot.dias if d.fecha and d.fecha < hoy})
    return {"n": len(fechas),
            "desde": fechas[0].isoformat() if fechas else None,
            "hasta": fechas[-1].isoformat() if fechas else None}


def detalle(db: Session, cot: m.Cotizacion, puede_armar: bool) -> dict:
    t = totales(cot)
    fechas = sorted({d.fecha for d in cot.dias})
    pdf = archivo(cot, "pdf")
    comprobante = archivo(cot, "comprobante")
    es_ultima = ultima(db, cot.folio, cot.clase).id == cot.id
    tarifario = db.get(m.Tarifario, cot.tarifario_id)
    perfiles = {l.perfil_id for l in cot.lineas if l.perfil_id}
    # En otra moneda que la del pais, el tipo de cambio que quedaria fijo
    # si se autoriza hoy (seccion 120): se ve antes de autorizar.
    local = tipo_cambio.local_del_pais(db, cot.pais_id)
    otra = local is not None and cot.moneda != local
    tc = (tipo_cambio.vigente(db, cot.moneda, local)
          if otra and tipo_cambio.se_puede(cot.moneda, local) else None)
    return {
        **renglon_de_lista(cot),
        "moneda_local": local.value if local else None,
        "tipo_cambio_hoy": ({**tipo_cambio.en_json(tc),
                             "corta": tipo_cambio.corto(tc["tasa"])}
                            if tc else None),
        "pais_id": cot.pais_id,
        "pais": cot.pais.nombre if cot.pais else None,
        "cliente_id": cot.cliente_id, "prospecto": cot.prospecto,
        "cliente_rfc": cot.cliente.rfc if cot.cliente else None,
        "tarifario": _tarifario(tarifario) if tarifario else None,
        "solicitante_id": cot.solicitante_id,
        "solicitante_nombre": cot.solicitante_nombre,
        "solicitante_apellidos": cot.solicitante_apellidos,
        "solicitante_correo": cot.solicitante_correo,
        "solicitante_telefono": cot.solicitante_telefono,
        "consultor_id": cot.consultor_id,
        "tipo_servicio": cot.tipo_servicio, "introduccion": cot.introduccion,
        "idioma": cot.idioma, "con_iva": cot.con_iva,
        "tasa_iva": float(cot.tasa_iva) if cot.tasa_iva is not None else None,
        "gastos": motor.modo_de_gastos(cot),
        "monto_gastos": float(gastos_fijos(cot)) or None,
        "motivo": cot.motivo_recotizacion,
        "equipos": equipos_de(cot),
        "lineas": [{
            "fecha": l.fecha.isoformat(), "equipo": l.equipo_clave,
            "modalidad": l.modalidad.codigo.value if l.modalidad else None,
            "tipo": l.tipo.value, "perfil_id": l.perfil_id,
            "categoria_id": l.categoria_id, "descripcion": l.descripcion,
            "producto": l.producto, "cantidad": l.cantidad,
            "precio": float(l.precio_unitario), "importe": float(l.subtotal)}
            for l in sorted(cot.lineas, key=lambda x: (
                x.fecha, orden_de(x.equipo_clave),
                motor.ORDEN_DE_TIPO.get(x.tipo, 9), x.id or 0))],
        "subtotal": float(t["subtotal"]), "iva": float(t["iva"]),
        "dias_n": len({(d.equipo_clave, d.fecha) for d in cot.dias}),
        "equipos_n": len({d.equipo_clave for d in cot.dias}),
        "desde": fechas[0].isoformat() if fechas else None,
        "hasta": fechas[-1].isoformat() if fechas else None,
        "enviada_por": cot.enviada_por.nombre if cot.enviada_por else None,
        "rechazada_en": cot.rechazada_en.isoformat() if cot.rechazada_en else None,
        "autorizada_en": (cot.autorizada_en.isoformat()
                          if cot.autorizada_en else None),
        "pdf": {"nombre": pdf.nombre} if pdf else None,
        "comprobante": ({"nombre": comprobante.nombre}
                        if comprobante else None),
        "hora_extra": ([{**x, "precio": float(x["precio"])} for x in
                        hora_extra(db, tarifario, perfiles, cot.pais_id)]
                       if tarifario else []),
        "es_ultima": es_ultima,
        "se_edita": puede_armar and es_ultima and cot.estatus == E.BORRADOR,
        "se_autoriza": puede_armar and es_ultima and cot.estatus in SE_AUTORIZAN,
        # Su servicio se elimino (seccion 126): se vuelve a crear o se
        # elimina la cotizacion.
        "se_recrea": puede_armar and es_ultima and servicio_eliminado(cot),
        "sale_otra": (puede_armar and es_ultima
                      and cot.estatus in DE_ESTAS_SALE_OTRA),
        "faltan": (que_le_falta(db, cot) if cot.estatus == E.BORRADOR else []),
        "firma": tiene_firma(db, cot.consultor_id),
        "hoy": _hoy(db, cot).isoformat(),
        # Los dias de la cotizacion que ya pasaron (seccion 131, decision
        # 11): la vencida que se autoriza tarde, o el servicio que se
        # vuelve a crear dias despues, nace con esos dias atras. Se avisa
        # antes de autorizar o recrear, y se deja seguir.
        "dias_pasados": dias_pasados(db, cot),
        "versiones": [{
            "id": v.id, "version": v.version, "estatus": v.estatus.value,
            "motivo": v.motivo_recotizacion,
            "total": float(totales(v)["total"]),
            # Cada version con su moneda (seccion 129, hallazgo r1-07):
            # la V1 en dolares se pintaba en pesos desde la V2.
            "moneda": v.moneda.value if v.moneda else None,
            "enviada_en": v.enviada_en.isoformat() if v.enviada_en else None,
            "pdf": archivo(v, "pdf") is not None}
            for v in versiones(db, cot.folio, cot.clase)],
    }


# ------------------------------------------------------------- la firma

TIPOS_DE_FIRMA = ("image/png", "image/jpeg")


def poner_firma(db: Session, actor: m.Usuario, imagen: str) -> None:
    """La firma de quien la sube, y solo de el: no hay forma de subir la
    de otro."""
    if not actor.persona_id:
        raise HTTPException(400, "Tu acceso no está ligado a una persona.")
    tipo = imagen.split(";", 1)[0].removeprefix("data:")
    if tipo not in TIPOS_DE_FIRMA:
        raise HTTPException(400, {
            "mensaje": "La firma va en PNG o JPG",
            "que_hacer": "Toma una foto de tu firma en papel blanco, o "
                         "escanéala, y súbela de nuevo."})
    fila = (db.query(m.FirmaConsultor)
            .filter_by(persona_id=actor.persona_id).first())
    if fila is None:
        db.add(m.FirmaConsultor(persona_id=actor.persona_id, imagen=imagen))
    else:
        fila.imagen = imagen
        fila.actualizada_en = _ahora()
    db.flush()


def quitar_firma(db: Session, actor: m.Usuario) -> None:
    db.query(m.FirmaConsultor).filter_by(
        persona_id=actor.persona_id).delete()
    db.flush()


def firma_de(db: Session, persona_id: int | None) -> str | None:
    if not persona_id:
        return None
    fila = db.query(m.FirmaConsultor).filter_by(persona_id=persona_id).first()
    return fila.imagen if fila else None


# ------------------------------------------------------------- Catalogos

def textos_de(db: Session, pais_id: int) -> dict:
    """Los datos y los textos de un pais, como los edita Catalogos."""
    datos = datos_del_pais(db, pais_id)
    textos = {clave: {idioma: "" for idioma in IDIOMAS}
              for clave in CLAVES_DE_TEXTO}
    for fila in db.query(m.TextoCotizacion).filter_by(pais_id=pais_id).all():
        if fila.clave in textos and fila.idioma in IDIOMAS:
            textos[fila.clave][fila.idioma] = fila.texto
    return {
        "pais_id": pais_id,
        "razon_social": datos.razon_social if datos else None,
        "rfc": datos.rfc if datos else None,
        "tasa_iva": (float(datos.tasa_iva) if datos and datos.tasa_iva
                     is not None else None),
        "textos": textos,
    }


def faltan_textos(db: Session, pais_id: int | None, idioma: str,
                  con_iva: bool = True) -> list[str]:
    """Lo que el PDF de ese pais en ese idioma no va a poder decir. La
    tasa de IVA solo si la cotizacion va con IVA (seccion 129)."""
    if not pais_id:
        return []
    d = textos_de(db, pais_id)
    faltan = [c for c in CLAVES_DE_TEXTO if not d["textos"][c][idioma].strip()]
    if not d["razon_social"]:
        faltan.append("razon_social")
    if not d["rfc"]:
        faltan.append("rfc")
    if con_iva is not False and d["tasa_iva"] is None:
        faltan.append("tasa_iva")
    return faltan


def guardar_textos(db: Session, actor: m.Usuario, pais_id: int,
                   datos: dict) -> dict:
    """Lo que escribio direccion de operaciones, con su renglon en la
    bitacora de administracion: que cambio, no el texto entero."""
    pais = db.get(m.Pais, pais_id)
    if pais is None:
        raise HTTPException(404, f"No existe el país {pais_id}")
    antes = textos_de(db, pais_id)
    fila = datos_del_pais(db, pais_id)
    if fila is None:
        fila = m.DatosCotizacion(pais_id=pais_id)
        db.add(fila)
    cambios_antes, cambios_despues, textos_cambiados = [], [], []

    razon = _limpio(datos.get("razon_social"), 200)
    rfc = _limpio(datos.get("rfc"), 30)
    rfc = rfc.upper() if rfc else None
    tasa = datos.get("tasa_iva")
    if tasa in ("", None):
        tasa = None
    else:
        try:
            tasa = Decimal(str(tasa)).quantize(Decimal("0.0001"))
        except (InvalidOperation, ValueError):
            raise HTTPException(400, "La tasa de IVA no es un número.")
        if tasa < 0 or tasa >= 1:
            raise HTTPException(400, "La tasa de IVA va como fracción: 0.16 "
                                     "para el 16 %.")
    for campo, valor in (("razon_social", razon), ("rfc", rfc),
                         ("tasa_iva", tasa)):
        viejo = antes[campo]
        nuevo = float(valor) if campo == "tasa_iva" and valor is not None else valor
        if viejo != nuevo:
            cambios_antes.append(f"{campo}: {viejo}")
            cambios_despues.append(f"{campo}: {nuevo}")
            setattr(fila, campo, valor)

    for clave, por_idioma in (datos.get("textos") or {}).items():
        if clave not in CLAVES_DE_TEXTO:
            raise HTTPException(400, f"No existe el texto «{clave}».")
        for idioma, texto in (por_idioma or {}).items():
            if idioma not in IDIOMAS:
                raise HTTPException(400, f"No existe el idioma «{idioma}».")
            texto = (texto or "").strip()
            if len(texto) > LARGO_TEXTO:
                raise HTTPException(400, f"El texto «{clave}» pasa de "
                                         f"{LARGO_TEXTO} letras.")
            if texto == antes["textos"][clave][idioma]:
                continue
            existente = (db.query(m.TextoCotizacion)
                         .filter_by(pais_id=pais_id, clave=clave,
                                    idioma=idioma).first())
            if texto and existente:
                existente.texto = texto
            elif texto:
                db.add(m.TextoCotizacion(pais_id=pais_id, clave=clave,
                                         idioma=idioma, texto=texto))
            elif existente:
                db.delete(existente)
            textos_cambiados.append(f"{clave}:{idioma}")
    # Dos renglones en la bitacora: los datos, con su antes y su despues;
    # los textos, cuales cambiaron --el texto entero no cabe ni se lee--.
    if cambios_despues:
        accesos.anotar(db, actor, "catalogo cambiado", "cotizacion", pais_id,
                       antes="; ".join(cambios_antes) or None,
                       despues="; ".join(cambios_despues),
                       detalle=pais.nombre)
    if textos_cambiados:
        accesos.anotar(db, actor, "textos de la cotizacion", "cotizacion",
                       pais_id, despues=", ".join(textos_cambiados),
                       detalle=pais.nombre)
    db.flush()
    return textos_de(db, pais_id)


# ------------------------------------------------------------- semilla

def sembrar_mexico(db: Session) -> None:
    """Los datos y los textos de Mexico si no los tiene: la semilla de
    una base nueva. La de produccion los recibio con su migracion."""
    pais = db.query(m.Pais).filter_by(codigo="MX").first()
    if pais is None:
        return
    if datos_del_pais(db, pais.id) is None:
        db.add(m.DatosCotizacion(pais_id=pais.id,
                                 razon_social=DATOS_MEXICO["razon_social"],
                                 tasa_iva=Decimal(DATOS_MEXICO["tasa_iva"])))
    tiene = {(t.clave, t.idioma) for t in
             db.query(m.TextoCotizacion).filter_by(pais_id=pais.id).all()}
    for clave, por_idioma in TEXTOS_MEXICO.items():
        for idioma, texto in por_idioma.items():
            if (clave, idioma) not in tiene:
                db.add(m.TextoCotizacion(pais_id=pais.id, clave=clave,
                                         idioma=idioma, texto=texto))
    db.commit()

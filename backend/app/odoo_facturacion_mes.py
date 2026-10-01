# -*- coding: utf-8 -*-
"""La prefactura del mes del implantado en Odoo (seccion 117).

Decisiones de Salvador (1 oct, proyecto «La factura del implantado, en
Odoo»): el mes se factura como el eventual --con el visto bueno sale a
Odoo una factura de cliente en borrador y el facturista la timbra--, una
factura por implantado y por mes, y **un renglon por puesto y por
unidad**, como en la propuesta, cada uno con su producto de Odoo.

Las cifras no se calculan aqui: son las del cierre del mes
(`cierre_mes.comparar`), las mismas que ve el consultor en su visto bueno.
Aqui solo se reparten en renglones y se les pone su producto:

* **El servicio del mes.** Con precio fijo, el mensual de cada puesto y
  cada unidad; el mes que empieza o se cancela a la mitad, sus dias de
  servicio al precio por dia de cada uno. Por dia trabajado, los dias de
  cada persona a su precio y cada unidad por mes.
* **El dia adicional**, al precio del dia de cada persona; **la hora
  extra**, con el producto de la de su rol; **los gastos**, en un solo
  renglon con «Gastos de Operación (Viáticos)».

¿De donde sale lo de cada puesto? De la propuesta que el cliente
autorizo, si el implantado nacio de una; si no, de la plantilla del mes
con su lista de implantados. Si lo de los puestos no suma lo que dice el
mes --un precio que se puso a mano--, ese concepto va en un solo renglon
con el producto del puesto principal, y no se inventa un reparto. El
centavo que sobre al repartir el precio por dia va en el ultimo puesto.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import odoo_facturacion as of
from app.odoo_tarifarios_reglas import FULL_DAY, HORA_EXTRA, PAQUETE, ROL, UNIDAD

CERO = Decimal("0")
CENTAVO = Decimal("0.01")

# Lo que el cliente lee en cada renglon del mes.
TEXTOS = {
    "es": {"servicio": "Servicio implantado", "el_mensual": "el mensual",
           "el_mes": "el mes", "mes_completo": "mes completo",
           "dias": "{n} días", "dias_servicio": "{n} días de servicio",
           "por_personas": "{p} personas × {d}",
           "dia_adicional": "día adicional", "dias_adicionales": "días adicionales",
           "horas": "{n} h", "hora_extra": "Hora extra",
           "modalidad": {"lunes_viernes": "lunes a viernes",
                         "lunes_sabado": "lunes a sábado",
                         "todos": "mes completo"}},
    "en": {"servicio": "Dedicated service", "el_mensual": "monthly fee",
           "el_mes": "the month", "mes_completo": "full month",
           "dias": "{n} days", "dias_servicio": "{n} service days",
           "por_personas": "{p} people × {d}",
           "dia_adicional": "additional day", "dias_adicionales": "additional days",
           "horas": "{n} h", "hora_extra": "Overtime",
           "modalidad": {"lunes_viernes": "Monday to Friday",
                         "lunes_sabado": "Monday to Saturday",
                         "todos": "full month"}},
    "pt": {"servicio": "Serviço implantado", "el_mensual": "a mensalidade",
           "el_mes": "o mês", "mes_completo": "mês completo",
           "dias": "{n} dias", "dias_servicio": "{n} dias de serviço",
           "por_personas": "{p} pessoas × {d}",
           "dia_adicional": "dia adicional", "dias_adicionales": "dias adicionais",
           "horas": "{n} h", "hora_extra": "Hora extra",
           "modalidad": {"lunes_viernes": "segunda a sexta",
                         "lunes_sabado": "segunda a sábado",
                         "todos": "mês completo"}},
}

# Lo que falta, ademas de lo del eventual.
of.FALTA.update({
    "sin_producto_puesto": "«{que}»: no se sabe con qué producto de Odoo se "
                           "cobra; dilo en Facturación → Tarifarios, en la "
                           "tabla de productos.",
    "sin_puesto_principal": "El mes no tiene a nadie en la plantilla: no se "
                            "sabe con qué producto se cobra el servicio.",
})


def _d(valor) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))


@dataclass
class Puesto:
    """Lo que lleva el mes: un puesto (persona o el conductor con su
    unidad, en paquete) o una unidad, con cuantos son y sus precios por
    cada uno."""
    tipo: str                       # persona | unidad | paquete
    perfil_id: int | None
    categoria_id: int | None
    cantidad: int
    lee: str                        # como lo lee el cliente
    mes: Decimal | None = None      # el mensual de cada uno
    dia: Decimal | None = None      # el precio por dia de cada uno
    he: Decimal | None = None       # la hora extra de cada uno

    @property
    def es_persona(self) -> bool:
        return self.tipo in ("persona", "paquete")


def puestos_del_mes(db: Session, contrato: m.ContratoImplantado,
                    propuesta: m.Cotizacion | None) -> list[Puesto] | None:
    """Lo que lleva el mes, puesto por puesto: de la propuesta que el
    cliente autorizo o, si el mes va con los precios de la lista, de la
    plantilla con su lista. None: no se sabe cuanto es de cada uno."""
    from app import implantado_precios
    from app import propuesta as motor_propuesta

    if propuesta is not None:
        calc = motor_propuesta.de_la_guardada(propuesta)
        tipos = {"recurso": "persona", "vehiculo": "unidad",
                 "paquete": "paquete"}
        return [Puesto(tipo=tipos.get(p["tipo"], "persona"),
                       perfil_id=p["perfil_id"], categoria_id=p["categoria_id"],
                       cantidad=p["cantidad"] or 1,
                       lee=(p["descripcion"] or p["producto"] or p["nombre"]
                            or "—"),
                       mes=_d(p["precio_mes"]), dia=_d(p["precio_dia"]),
                       he=_d(p["precio_hora_extra"]))
                for p in calc["posiciones"]]
    if not contrato.precios_de_la_lista:
        return None
    lista = implantado_precios.de_la_lista(db, contrato)
    if not lista["completa"]:
        return None
    grupos: dict = {}
    for r in lista["renglones"]:
        if r["tipo"] == "unidad_en_paquete":
            continue
        tipo = {"recurso": "persona", "paquete": "paquete",
                "unidad": "unidad"}.get(r["tipo"])
        if tipo is None:
            continue
        lee = (r.get("rol") if tipo == "persona" else r.get("unidad")
               if tipo == "unidad" else f"{r.get('rol')} + {r.get('unidad')}")
        clave = (tipo, r.get("perfil_id"), r.get("categoria_id"),
                 str(r.get("precio_dia")), str(r.get("precio_mes")),
                 str(r.get("precio_hora_extra")))
        if clave in grupos:
            grupos[clave].cantidad += 1
            continue
        grupos[clave] = Puesto(
            tipo=tipo, perfil_id=r.get("perfil_id"),
            categoria_id=r.get("categoria_id"), cantidad=1, lee=lee or "—",
            mes=_d(r.get("precio_mes")), dia=_d(r.get("precio_dia")),
            he=_d(r.get("precio_hora_extra")))
    return list(grupos.values())


class Productos:
    """Con que producto de Odoo se cobra cada cosa del mes: el del precio
    en la lista del cliente --la de implantados, o la de siempre-- en dia
    completo; si la lista no lo trae, el que dice lo mismo en la tabla de
    productos (el unico, o el que manda)."""

    def __init__(self, db: Session, contrato: m.ContratoImplantado, faltan):
        from app import implantado_precios

        self.db, self.faltan = db, faltan
        self.lista, _ = implantado_precios.lista_del_implantado(
            db, contrato.servicio)
        modalidad = implantado_precios.modalidad_de_la_lista(db, contrato)
        self.modalidad_id = modalidad.id if modalidad else None
        self.todos = {p.id: p for p in db.query(m.ProductoOdoo)}

    def _de_la_lista(self, modelo, **llave) -> m.TarifaRecurso | None:
        if self.lista is None or self.modalidad_id is None:
            return None
        return (self.db.query(modelo)
                .filter_by(tarifario_id=self.lista.id,
                           modalidad_id=self.modalidad_id, **llave).first())

    def _por_concepto(self, clase: str, perfil_id=None, categoria_id=None,
                      modalidad: str | None = FULL_DAY) -> int | None:
        candidatos = [p for p in self.todos.values()
                      if p.confirmado and p.clase == clase
                      and p.perfil_id == perfil_id
                      and p.categoria_id == categoria_id
                      and (modalidad is None or p.modalidad == modalidad)]
        vivos = [p for p in candidatos if p.vendible] or candidatos
        if len(vivos) == 1:
            return vivos[0].id
        preferidos = [p for p in vivos if p.preferido]
        return preferidos[0].id if len(preferidos) == 1 else None

    def del_puesto(self, p: Puesto) -> int | None:
        """El producto (de la tabla) de un puesto o una unidad."""
        if p.tipo == "persona":
            fila = self._de_la_lista(m.TarifaRecurso, perfil_id=p.perfil_id)
            return ((fila.producto_odoo_id if fila else None)
                    or self._por_concepto(ROL, perfil_id=p.perfil_id))
        if p.tipo == "unidad":
            fila = self._de_la_lista(m.TarifaVehiculo,
                                     categoria_id=p.categoria_id)
            return ((fila.producto_odoo_id if fila else None)
                    or self._por_concepto(UNIDAD, categoria_id=p.categoria_id))
        fila = self._de_la_lista(m.TarifaPaquete, perfil_id=p.perfil_id,
                                 categoria_id=p.categoria_id)
        return ((fila.producto_odoo_id if fila else None)
                or self._por_concepto(PAQUETE, perfil_id=p.perfil_id,
                                      categoria_id=p.categoria_id))

    def de_hora_extra(self, perfil_id: int | None) -> int | None:
        """La hora extra de un rol: la de la lista, la de su rol en la
        tabla, o la de todos."""
        if perfil_id:
            fila = self._de_la_lista(m.TarifaRecurso, perfil_id=perfil_id)
            if fila and fila.producto_hora_extra_id:
                return fila.producto_hora_extra_id
        if self.lista is not None and self.lista.producto_hora_extra_id:
            return self.lista.producto_hora_extra_id
        return (self._por_concepto(HORA_EXTRA, perfil_id=perfil_id,
                                   modalidad=None) if perfil_id else None) \
            or self._por_concepto(HORA_EXTRA, modalidad=None)

    def variante(self, producto_id: int | None, que: str) -> tuple:
        """(variante de Odoo, nombre del producto); lo que falta, dicho."""
        p = self.todos.get(producto_id) if producto_id else None
        if p is None:
            self.faltan("sin_producto_puesto", que=que)
            return None, None
        if not p.variante_odoo_id:
            if (p.variantes or 0) > 1:
                self.faltan("varias_variantes", producto=p.nombre,
                            variantes=p.variantes)
            else:
                self.faltan("sin_variante", producto=p.nombre)
        return p.variante_odoo_id, p.nombre


def _principal(contrato: m.ContratoImplantado,
               puestos: list[Puesto] | None) -> Puesto | None:
    """El puesto principal, para lo que no se puede repartir: la primera
    persona de lo que lleva el mes, o de la plantilla."""
    for p in puestos or []:
        if p.es_persona:
            return p
    for fila in sorted(contrato.plantilla, key=lambda f: f.id):
        if fila.rol_id:
            return Puesto(tipo="persona", perfil_id=fila.rol_id,
                          categoria_id=None, cantidad=1,
                          lee=fila.rol.nombre if fila.rol else "—")
    return None


def _unidad_principal(contrato: m.ContratoImplantado,
                      puestos: list[Puesto] | None) -> Puesto | None:
    for p in puestos or []:
        if p.tipo == "unidad":
            return p
    for u in sorted(contrato.unidades, key=lambda u: u.id):
        if u.vehiculo is not None:
            return Puesto(tipo="unidad", perfil_id=None,
                          categoria_id=u.vehiculo.categoria_id, cantidad=1,
                          lee=u.vehiculo.categoria.nombre)
    return None


def reparto_por_dia(puestos: list[Puesto], base: int,
                    precio_dia: Decimal) -> list[tuple] | None:
    """[(puesto, precio por dia)] del mes que va por dia de servicio: el
    mensual de cada puesto entre los dias de la modalidad. Suman, por la
    cantidad de cada uno, el precio por dia del mes; el centavo que sobre
    va en el ultimo puesto que es uno solo. None si no se puede."""
    if not puestos or any(p.mes is None for p in puestos) or not base:
        return None
    precios = [(p, (p.mes / base).quantize(CENTAVO, rounding=ROUND_HALF_UP))
               for p in puestos]
    resta = precio_dia - sum((p.cantidad * x for p, x in precios), CERO)
    if resta:
        for i in range(len(precios) - 1, -1, -1):
            p, x = precios[i]
            if p.cantidad == 1 and x + resta > 0:
                precios[i] = (p, x + resta)
                break
        else:
            return None
    return precios


def prefactura_del_mes(db: Session, cierre: m.Cierre) -> dict:
    """La prefactura del mes del implantado tal como se mandaria a Odoo,
    sin mandarla. `faltan` vacio: se puede mandar."""
    from app import cierre_mes
    from app import propuesta as motor_propuesta
    from app.cotizacion_pdf import MESES

    contrato = cierre.contrato
    servicio = cierre.servicio
    cliente = servicio.cliente
    periodo = cierre_mes.periodo(contrato)
    faltan = of._Faltan()
    salida = {"cierre_id": cierre.id, "servicio_id": servicio.id,
              "contrato_id": contrato.id, "periodo": periodo,
              "referencia": f"{servicio.folio} · {periodo}",
              "origen": f"{of.ORIGEN} · {servicio.folio} · {periodo}",
              "cliente": {"id": cliente.id if cliente else None,
                          "nombre": cliente.nombre if cliente else None,
                          "odoo_id": cliente.odoo_id if cliente else None},
              "moneda": None, "nota": None, "renglones": [], "total": CERO,
              "faltan": faltan.lista}
    if cliente is None or not cliente.odoo_id:
        faltan("cliente_sin_odoo",
               cliente=cliente.nombre if cliente else "del servicio")
    try:
        comparativo = cierre_mes.comparar(db, contrato)
    except HTTPException as error:
        detalle = error.detail
        faltan("sin_precio", texto=(detalle.get("mensaje")
                                    if isinstance(detalle, dict) else str(detalle)))
        return salida
    salida["moneda"] = comparativo["moneda"]

    propuesta = motor_propuesta.autorizada_de(db, servicio.id)
    idioma = (propuesta.idioma if propuesta is not None
              and propuesta.idioma in TEXTOS else "es")
    T, Te = TEXTOS[idioma], of.TEXTOS[idioma]
    mes = f"{MESES[idioma][contrato.mes - 1]} {contrato.anio}"
    productos = Productos(db, contrato, faltan)
    puestos = puestos_del_mes(db, contrato, propuesta)
    principal = _principal(contrato, puestos)
    trabajado = comparativo["trabajado"]
    desglose = trabajado["desglose"]
    precios = comparativo["precios"]
    mensual = comparativo["mensual"]
    renglones = []

    def renglon(tipo, producto_id, que, etiqueta, cantidad, precio):
        variante, nombre = productos.variante(producto_id, que)
        precio = Decimal(str(precio)).quantize(CENTAVO)
        renglones.append({"tipo": tipo, "fecha": None, "equipo": None,
                          "producto_id": producto_id,
                          "producto": nombre or que,
                          "variante_odoo_id": variante,
                          "etiqueta": etiqueta, "cantidad": cantidad,
                          "precio": precio, "importe": precio * cantidad})

    def del_principal(tipo, detalle, cantidad, precio):
        """Lo que no se puede repartir: un renglon, con el producto del
        puesto principal."""
        if principal is None:
            faltan("sin_puesto_principal")
            return
        renglon(tipo, productos.del_puesto(principal), principal.lee,
                f"{T['servicio']} · {mes} · {detalle}", cantidad, precio)

    def por_personas(cantidad, texto):
        return (T["por_personas"].format(p=cantidad, d=texto)
                if cantidad > 1 else texto)

    personas = [p for p in puestos or [] if p.es_persona]
    unidades = [p for p in puestos or [] if p.tipo == "unidad"]
    modalidad = T["modalidad"].get(contrato.dias_servicio.value
                                   if contrato.dias_servicio else "", "")

    # ---------------------------------------------------- el servicio del mes
    if "mes_completo" in desglose:
        importe = desglose["mes_completo"]
        if mensual and mensual["parcial"]:
            dias = mensual["dias_de_servicio"]
            texto = T["dias_servicio"].format(n=dias)
            reparto = (reparto_por_dia(puestos, mensual["dias"],
                                       mensual["precio_dia"])
                       if puestos and sum((p.cantidad * p.mes for p in puestos
                                           if p.mes is not None), CERO)
                       == _d(contrato.precio_mes_completo) else None)
            if reparto:
                for p, precio in reparto:
                    renglon("mes", productos.del_puesto(p), p.lee,
                            f"{p.lee} · {mes} · {por_personas(p.cantidad, texto)}",
                            p.cantidad * dias, precio)
            elif dias:
                del_principal("mes", texto, dias, mensual["precio_dia"])
        elif mensual:
            if puestos and all(p.mes is not None for p in puestos) and sum(
                    (p.cantidad * p.mes for p in puestos), CERO) == importe:
                for p in puestos:
                    partes = [p.lee, mes] + ([modalidad] if p.es_persona
                                             and modalidad else [])
                    renglon("mes", productos.del_puesto(p), p.lee,
                            " · ".join(partes + [T["el_mensual"]]),
                            p.cantidad, p.mes)
            elif importe:
                del_principal("mes", T["el_mensual"], 1, importe)
        elif importe:
            # El precio fijo de antes, con todo incluido: no dice de que
            # puesto es cada peso.
            del_principal("mes", T["mes_completo"], 1, importe)
    if desglose.get("dias_base"):
        dias = trabajado["dias_base"]
        texto = T["dias"].format(n=dias)
        if personas and all(p.dia is not None for p in personas) and sum(
                (p.cantidad * p.dia for p in personas), CERO) == _d(precios["dia"]):
            for p in personas:
                renglon("dias", productos.del_puesto(p), p.lee,
                        f"{p.lee} · {mes} · {por_personas(p.cantidad, texto)}",
                        p.cantidad * dias, p.dia)
        else:
            del_principal("dias", texto, dias, precios["dia"])
    if desglose.get("vehiculo_mes"):
        importe = desglose["vehiculo_mes"]
        if unidades and all(p.mes is not None for p in unidades) and sum(
                (p.cantidad * p.mes for p in unidades), CERO) == importe:
            for p in unidades:
                renglon("unidad", productos.del_puesto(p), p.lee,
                        f"{p.lee} · {mes} · {T['el_mes']}", p.cantidad, p.mes)
        else:
            u = _unidad_principal(contrato, puestos)
            if u is None:
                faltan("sin_producto_puesto", que="la unidad del mes")
            else:
                renglon("unidad", productos.del_puesto(u), u.lee,
                        f"{u.lee} · {mes} · {T['el_mes']}", 1, importe)

    # ---------------------------------------------------- el dia adicional
    if desglose.get("dias_adicionales"):
        n = trabajado["dias_adicionales"]
        fechas = ", ".join(f"{date.fromisoformat(f):%d/%m}"
                           for f in trabajado["fechas_adicionales"])
        texto = (T["dia_adicional"] if n == 1 else T["dias_adicionales"]) \
            + (f" · {fechas}" if fechas else "")
        if personas and all(p.dia is not None for p in personas) and sum(
                (p.cantidad * p.dia for p in personas), CERO) \
                == _d(precios["dia_adicional"]):
            for p in personas:
                renglon("dia_adicional", productos.del_puesto(p), p.lee,
                        f"{p.lee} · {texto}", p.cantidad * n, p.dia)
        else:
            del_principal("dia_adicional", texto, n, precios["dia_adicional"])

    # ---------------------------------------------------- la hora extra
    if desglose.get("horas_extra"):
        horas = trabajado["horas_extra"]
        texto = T["horas"].format(n=horas)
        con_he = [p for p in personas if p.he]
        if con_he and sum((p.cantidad * p.he for p in con_he), CERO) \
                == _d(precios["hora_extra"]):
            for p in con_he:
                producto_id = productos.de_hora_extra(p.perfil_id)
                nombre = (productos.todos[producto_id].nombre
                          if producto_id in productos.todos else T["hora_extra"])
                renglon("horas_extra", producto_id,
                        f"{T['hora_extra']} · {p.lee}",
                        f"{nombre} · {mes} · {por_personas(p.cantidad, texto)}",
                        p.cantidad * horas, p.he)
        else:
            perfil = principal.perfil_id if principal else None
            producto_id = productos.de_hora_extra(perfil)
            nombre = (productos.todos[producto_id].nombre
                      if producto_id in productos.todos else T["hora_extra"])
            renglon("horas_extra", producto_id, T["hora_extra"],
                    f"{nombre} · {mes} · {texto}", horas, precios["hora_extra"])

    # ---------------------------------------------------- los gastos
    a_facturar = comparativo["a_facturar"]
    gastos = a_facturar["viaticos"]
    if gastos is None:
        sin = comparativo["gastos"].get("sin_tipo_de_cambio") or {}
        faltan("sin_tipo_de_cambio",
               texto=sin.get("mensaje") or "Falta el tipo de cambio.")
    elif gastos:
        de_gastos, falta = of.producto_de_gastos(db)
        if falta:
            faltan(falta[0], **falta[1])
        modo = Te["fijos" if contrato.viaticos_incluidos else "comprobados"]
        tc = comparativo["gastos"].get("tipo_cambio")
        if tc and not contrato.viaticos_incluidos:
            from app import tipo_cambio
            modo += Te["origen"].format(
                moneda=comparativo["moneda_local"],
                importe=f"{Decimal(str(comparativo['gastos']['comprobado'])):,.2f}",
                tc=tipo_cambio.corto(tipo_cambio.texto(tc["tasa"])))
        nombre = de_gastos.nombre if de_gastos else of.settings.odoo_producto_gastos
        if de_gastos is not None:
            renglon("gastos", de_gastos.id, nombre,
                    f"{nombre} · {servicio.folio} · {mes} · {modo}", 1, gastos)
        else:
            renglones.append({"tipo": "gastos", "fecha": None, "equipo": None,
                              "producto_id": None, "producto": nombre,
                              "variante_odoo_id": None,
                              "etiqueta": f"{nombre} · {servicio.folio} · {mes} · {modo}",
                              "cantidad": 1, "precio": Decimal(str(gastos)),
                              "importe": Decimal(str(gastos))})

    salida["renglones"] = renglones
    salida["total"] = sum((r["importe"] for r in renglones), CERO)
    esperado = a_facturar["total"]
    if esperado is not None and salida["total"] != Decimal(str(esperado)):
        faltan("no_cuadra", suma=f"{salida['total']:,.2f}",
               total=f"{Decimal(str(esperado)):,.2f}")
    return salida

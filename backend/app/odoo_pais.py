# -*- coding: utf-8 -*-
"""Lo que un pais entero puede perder en una lectura de Odoo, y el cambio
de pais de una persona, una unidad o un cliente (seccion 130, decisiones 3
y 4 de Salvador del 2 de octubre).

El freno por pais. Las cuatro lecturas --personal, flota, oficina y
clientes-- tomaban «Odoo no me lo devolvio» como «lo borraron» y daban de
baja. Si al usuario de la conexion le quitan la compania de Brasil, en una
hora la lectura lee «Brasil 0» y da de baja a los 40 de Brasil con sus
accesos, y a sus 13 unidades. Ahora, si un pais leyo cero y Connect tiene
registros activos de ese pais que vinieron de Odoo, la vuelta entera se
detiene y lo dice: nada se toca hasta que alguien revise la conexion. Y lo
que no se encuentra en Odoo --ni entre los archivados-- ya no es baja: queda
pendiente, «no se encontro en Odoo: revisar la conexion»; solo el archivado
explicito en Odoo da de baja.

El cambio de pais. La persona o la unidad que Odoo pasa a otro pais quedaba
pendiente para siempre: Catalogos no deja cambiarle la ciudad porque «viene
de Odoo» (y en Odoo ya esta corregido). Ahora el pendiente trae a que pais
y a que ciudad la pone Odoo, y quien administra Odoo la pasa desde la
pantalla, solo si no tiene dias asignados por delante; la siguiente lectura
la toma. El cliente, que antes cambiaba de pais solo --con sus cotizaciones
y servicios del otro pais--, queda pendiente igual hasta que alguien lo
decida.
"""
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import accesos
from app import models as m
from app import reloj

# Lo que dice el pendiente de lo que Odoo no devolvio ni entre los
# archivados: la conexion dejo de verlo, o lo borraron de verdad. Si lo
# borraron, se da de baja a mano en Catalogos.
NO_ENCONTRADO = "no se encontro en Odoo: revisar la conexion"

PERSONAL, FLOTA, OFICINA, CLIENTES = "personal", "flota", "oficina", "clientes"
registro = logging.getLogger("centauro.odoo")


def _paises(db: Session) -> dict:
    return {p.codigo.upper(): p for p in db.query(m.Pais).all()}


def activos_por_pais(db: Session, tipo: str) -> dict:
    """Cuantos registros activos que vinieron de Odoo tiene Connect de cada
    pais, por codigo (MX, BR): los que una lectura que leyera cero daria de
    baja."""
    cuenta: dict = {}
    if tipo in (PERSONAL, OFICINA):
        filas = (db.query(m.Persona)
                 .filter(m.Persona.activo.is_(True),
                         m.Persona.odoo_id.isnot(None),
                         m.Persona.oficina.is_(tipo == OFICINA))
                 .all())
        for p in filas:
            pais = p.plaza.pais if p.plaza is not None else None
            if pais is not None:
                cuenta[pais.codigo.upper()] = cuenta.get(pais.codigo.upper(), 0) + 1
    elif tipo == FLOTA:
        paises = {p.id: p for p in db.query(m.Pais).all()}
        filas = (db.query(m.Vehiculo)
                 .filter(m.Vehiculo.activo.is_(True),
                         m.Vehiculo.odoo_id.isnot(None)).all())
        for v in filas:
            pais = paises.get(v.pais_de_la_unidad)
            if pais is not None:
                cuenta[pais.codigo.upper()] = cuenta.get(pais.codigo.upper(), 0) + 1
    elif tipo == CLIENTES:
        paises = {p.id: p for p in db.query(m.Pais).all()}
        filas = (db.query(m.Cliente)
                 .filter(m.Cliente.activo.is_(True),
                         m.Cliente.odoo_id.isnot(None)).all())
        for c in filas:
            pais = paises.get(c.pais_id)
            if pais is not None:
                cuenta[pais.codigo.upper()] = cuenta.get(pais.codigo.upper(), 0) + 1
    return cuenta


def por_compania(filas: list, grupos) -> dict:
    """Cuantos registros de Odoo trae cada pais, por la compania de cada
    uno: {codigo: cuantos}. `grupos`: los paises con su `compania`
    (PERSONAL o FLOTAS). Lo que no es de una compania de Connect no cuenta."""
    de_compania = {g["compania"]: g["pais"] for g in grupos}
    cuenta = {g["pais"]: 0 for g in grupos}
    for f in filas:
        compania = f.get("company_id")
        if isinstance(compania, (list, tuple)):
            compania = compania[0] if compania else None
        codigo = de_compania.get(compania)
        if codigo is not None:
            cuenta[codigo] += 1
    return cuenta


def frenos(db: Session, tipo: str, leidos_por_pais: dict) -> list[dict]:
    """Los paises por los que la vuelta se detiene: leyeron cero en Odoo y
    Connect tiene registros activos suyos que vinieron de Odoo.
    [{codigo, pais, leidos, activos}]. Vacio: la vuelta sigue."""
    activos = activos_por_pais(db, tipo)
    paises = _paises(db)
    salida = []
    for codigo, leidos in leidos_por_pais.items():
        codigo = (codigo or "").upper()
        if leidos == 0 and activos.get(codigo):
            pais = paises.get(codigo)
            salida.append({"codigo": codigo,
                           "pais": pais.nombre if pais else codigo,
                           "leidos": 0, "activos": activos[codigo]})
    return salida


def detenida(informe: dict, freno: list[dict], **cuentas) -> dict:
    """El informe de una vuelta que se detuvo: lo leido por pais, el freno
    y nada mas. Las listas van vacias a proposito: lo que la lectura
    hubiera hecho no se ensena, porque no se va a hacer."""
    informe.update({"detenida": True, "freno": freno, "altas": [],
                    "vinculadas": [], "cambios": [], "bajas": [],
                    "pendientes": [], "por_capturar": [], "sin_cambio": 0})
    informe.update(cuentas)
    return informe


def texto_del_freno(freno: list[dict]) -> str:
    return "; ".join(f"{f['pais']} leyó 0 y Connect tiene {f['activos']} "
                     f"activos de {f['pais']}" for f in freno)


def registrar_detenida(db: Session, tipo: str, informe: dict,
                       quien: m.Usuario | None, automatica: bool) -> None:
    """La vuelta que se detuvo deja su renglon en las lecturas --se sabe
    que corrio y por que no toco nada-- y, si la pidio alguien, su
    renglon en la bitacora de administracion."""
    import json
    fila = m.SincronizacionOdoo(
        tipo=tipo, automatica=automatica,
        hecha_por_id=quien.persona_id if quien else None,
        leidos=informe.get("leidos", informe.get("leidas", 0)) or 0,
        altas=0, cambios=0, bajas=0, pendientes=0,
        detalle=json.dumps({"detenida": True, "freno": informe["freno"],
                            "leidos": informe.get("leidos", informe.get("leidas", 0)),
                            "por_pais": informe.get("por_pais", [])},
                           ensure_ascii=False, default=str))
    db.add(fila)
    db.flush()
    if quien is not None:
        accesos.anotar(db, quien, f"{tipo} leido de odoo: detenida",
                       "sincronizacion_odoo", fila.id,
                       despues=texto_del_freno(informe["freno"])[:200])
    db.commit()
    registro.warning("lectura de %s detenida por el freno por pais: %s", tipo,
                     texto_del_freno(informe["freno"]))


# ------------------------------------------------------------ el cambio de pais

def _plaza_central(db: Session, pais_id: int, nombre: str | None) -> m.Plaza | None:
    """La ciudad a la que pasa: la que Odoo dice, si existe en Centauro, o
    la primera activa del pais."""
    plazas = (db.query(m.Plaza).filter_by(pais_id=pais_id, activo=True)
              .order_by(m.Plaza.id).all())
    if nombre:
        quiere = nombre.strip().lower()
        for p in plazas:
            if p.nombre.strip().lower() == quiere:
                return p
    return plazas[0] if plazas else None


def _dias_por_delante_persona(db: Session, persona_id: int) -> int:
    from app.odoo_personal import dias_por_delante
    return len(dias_por_delante(db, persona_id))


def _dias_por_delante_unidad(db: Session, vehiculo_id: int) -> int:
    from app.odoo_flota import dias_por_delante
    return len(dias_por_delante(db, vehiculo_id))


def _dias_por_delante_cliente(db: Session, cliente_id: int) -> int:
    relojes = reloj.Relojes(db)
    filas = (db.query(m.Jornada)
             .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
             .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
             .filter(m.Servicio.cliente_id == cliente_id,
                     m.Jornada.estatus.notin_((m.EstatusJornada.TERMINADA,
                                               m.EstatusJornada.CANCELADA)))
             .all())
    return sum(1 for j in filas
               if j.fecha >= relojes.hoy(j.equipo.servicio.pais_id))


def cambiar(db: Session, actor: m.Usuario, tipo: str, cual: int,
            pais_id: int, plaza_id: int | None = None,
            plaza: str | None = None) -> dict:
    """Pasa a otro pais a quien Odoo ya puso alla: la persona, la unidad o
    el cliente. Solo lo que vino de Odoo, y solo sin dias asignados por
    delante --lo que ya trabajo se queda en su pais de antes--. La
    siguiente lectura lo toma con lo demas de Odoo."""
    pais = db.get(m.Pais, pais_id)
    if pais is None:
        raise HTTPException(404, f"No existe el país {pais_id}")
    destino = (db.get(m.Plaza, plaza_id) if plaza_id
               else _plaza_central(db, pais_id, plaza))
    if tipo in ("persona", "unidad") and (destino is None
                                          or destino.pais_id != pais_id):
        raise HTTPException(409, {
            "mensaje": f"No hay una ciudad de {pais.nombre} a la que pasarla",
            "que_hacer": "Da de alta la ciudad en Catálogos y vuelve a intentar."})

    if tipo == "persona":
        obj = db.get(m.Persona, cual)
        if obj is None or not obj.odoo_id:
            raise HTTPException(404, "No existe esa persona, o no viene de Odoo")
        por_delante = _dias_por_delante_persona(db, cual)
        nombre, de = obj.nombre, obj.plaza.nombre if obj.plaza else "—"
    elif tipo == "unidad":
        obj = db.get(m.Vehiculo, cual)
        if obj is None or not obj.odoo_id:
            raise HTTPException(404, "No existe esa unidad, o no viene de Odoo")
        por_delante = _dias_por_delante_unidad(db, cual)
        nombre, de = obj.placa, obj.plaza.nombre if obj.plaza else "—"
    elif tipo == "cliente":
        obj = db.get(m.Cliente, cual)
        if obj is None or not obj.odoo_id:
            raise HTTPException(404, "No existe ese cliente, o no viene de Odoo")
        por_delante = _dias_por_delante_cliente(db, cual)
        nombre = obj.nombre
        de_pais = db.get(m.Pais, obj.pais_id)
        de = de_pais.nombre if de_pais else "—"
    else:
        raise HTTPException(400, f"No sé pasar de país «{tipo}»")

    if por_delante:
        raise HTTPException(409, {
            "mensaje": f"{nombre} tiene {por_delante} día(s) asignado(s) por "
                       "delante: no se pasa de país con ellos",
            "que_hacer": "Quítalo de esos días (o espera a que pasen) y "
                         "vuelve a intentar.",
            "clave": "dias_por_delante", "dias": por_delante})

    if tipo == "cliente":
        antes = f"{de}"
        obj.pais_id = pais_id
        # Su lista era de su pais de antes: la de Odoo la vuelve a poner la
        # lectura de tarifarios; mientras, sin lista no se le cotiza.
        if obj.tarifario_id and obj.tarifario and obj.tarifario.pais_id != pais_id:
            obj.tarifario_id = None
        if (obj.tarifario_implantado_id and obj.tarifario_implantado
                and obj.tarifario_implantado.pais_id != pais_id):
            obj.tarifario_implantado_id = None
        despues = pais.nombre
    else:
        antes = f"{de}"
        obj.plaza_id = destino.id
        if tipo == "unidad":
            obj.pais_id = pais_id
        despues = f"{destino.nombre} ({pais.nombre})"
    db.flush()
    accesos.anotar(db, actor, "pasado de pais desde odoo", tipo, obj.id,
                   antes=antes[:200], despues=despues[:200],
                   detalle=(f"{nombre}: lo que ya trabajo se queda; la "
                            "siguiente lectura de Odoo lo toma")[:400])
    db.commit()
    return {"resultado": "pasado de pais", "tipo": tipo, "id": obj.id,
            "pais": pais.nombre, "plaza": destino.nombre if destino else None}

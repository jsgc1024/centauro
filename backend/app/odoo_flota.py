# -*- coding: utf-8 -*-
"""La flota y el taller de Proteccion Ejecutiva, leidos de Odoo.

Decision de Salvador, 23 de septiembre: etapa 2 de la conexion con Odoo.
Odoo es donde vive la flota; Centauro deja de capturar unidades y las
lee de ahi, igual que el personal.

  * Entran las unidades con la etiqueta «PROTECCION EJECUTIVA» o «pe».
  * La llave es el numero interno de Odoo; la primera vez se vincula por
    placa con la unidad que ya estaba.
  * Placa, categoria, plaza (la Ubicacion), marca y modelo, color y año
    vienen de Odoo y manda Odoo: en el catalogo ya no se editan. Un campo
    vacio en Odoo no borra el de Centauro. Lo de la operacion --si va a
    un implantado o se queda para eventuales, su costo diario-- sigue
    siendo de Centauro. Los autos rentados no se tocan.
  * La foto no viene de Odoo: cada categoria tiene su foto representativa
    en Centauro (decision de Salvador, 23 sep).
  * Baja: si Odoo la archiva, deja de ofrecerse y la central recibe una
    alerta en cada dia que la unidad tenia asignado; su consultor, un
    aviso.
  * El taller: las entradas de Flotilla -> Servicios de tipo Preventivo,
    Correctivo o Desgaste natural la sacan de circulacion de la fecha de
    entrada a la de salida; sin salida, se da por adentro. Lo que Odoo
    cancela o borra deja de bloquear. Lo que se capturo a mano en
    Centauro no se toca.
  * Nunca escribe en Odoo. Ensayo primero; la tarea de cada hora espera
    a que alguien haga la primera lectura a mano.

Las reglas viven en odoo_flota_reglas.py, sin base de datos.
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import accesos
from app import models as m
from app import odoo_flota_reglas as reglas
from app import reloj

registro = logging.getLogger("centauro.odoo")

TIPO = "flota"
CAMPOS = ["license_plate", "category_id", "location", "model_id", "color",
          "model_year", "tag_ids", "write_date"]
# Las fechas del taller son campos que la empresa agrego en Odoo Studio.
ENTRADA = "x_studio_fecha_de_entrada"
SALIDA = "x_studio_fecha_de_salida"
CAMPOS_TALLER = ["vehicle_id", "service_type_id", "state", "description",
                 "vendor_id"]
ACABADAS = (m.EstatusJornada.TERMINADA, m.EstatusJornada.CANCELADA)


def _utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fotos_fijas(db: Session) -> tuple:
    categorias = {c.codigo: {"id": c.id, "codigo": c.codigo, "nombre": c.nombre}
                  for c in db.query(m.CategoriaVehiculo)
                  .filter(m.CategoriaVehiculo.activo.is_(True)).all()}
    plazas = {reglas.normal(p.nombre): {"id": p.id, "nombre": p.nombre}
              for p in db.query(m.Plaza).filter(m.Plaza.activo.is_(True)).all()}
    vehiculos = [{
        "id": v.id, "odoo_id": v.odoo_id, "placa": v.placa,
        "categoria_id": v.categoria_id, "plaza_id": v.plaza_id,
        "marca_modelo": v.marca_modelo, "color": v.color,
        "modelo_anio": v.modelo_anio, "activo": v.activo,
        "sincronizado_en": v.odoo_sincronizado_en,
    } for v in db.query(m.Vehiculo).filter(m.Vehiculo.rentado.is_(False)).all()]
    return categorias, plazas, vehiculos


def _del_taller(db: Session) -> dict:
    """Lo que Centauro ya guardo del taller de Odoo, por su odoo_id."""
    return {t.odoo_id: {"id": t.id, "vehiculo_id": t.vehiculo_id,
                        "desde": t.desde, "hasta": t.hasta,
                        "tipo": t.tipo.value if t.tipo else None,
                        "taller": t.taller, "nota": t.nota}
            for t in db.query(m.TallerVehiculo)
            .filter(m.TallerVehiculo.odoo_id.isnot(None)).all()}


def dias_por_delante(db: Session, vehiculo_id: int,
                     relojes: reloj.Relojes | None = None) -> list:
    """Las asignaciones de esa unidad de hoy en adelante, con el hoy del
    pais de cada servicio. El dia de hoy cuenta aunque ya este en curso."""
    relojes = relojes or reloj.Relojes(db)
    filas = (db.query(m.AsignacionVehiculo)
             .join(m.Jornada, m.AsignacionVehiculo.jornada_id == m.Jornada.id)
             .filter(m.AsignacionVehiculo.vehiculo_id == vehiculo_id,
                     m.AsignacionVehiculo.relevado_en.is_(None),
                     m.Jornada.estatus.notin_(ACABADAS))
             .order_by(m.Jornada.fecha).all())
    salida = []
    for a in filas:
        servicio = a.jornada.equipo.servicio if a.jornada.equipo else None
        if servicio and a.jornada.fecha >= relojes.hoy(servicio.pais_id):
            salida.append(a)
    return salida


def _dar_de_baja(db: Session, baja: dict, ahora: datetime,
                 relojes: reloj.Relojes) -> None:
    from app import push

    vehiculo = db.get(m.Vehiculo, baja["vehiculo_id"])
    vehiculo.activo = False
    vehiculo.baja_odoo_en = ahora
    avisados = set()
    for asignacion in dias_por_delante(db, vehiculo.id, relojes):
        db.add(m.Alerta(
            jornada_id=asignacion.jornada_id, tipo=m.TipoAlerta.UNIDAD_DE_BAJA,
            mensaje=(f"La unidad {vehiculo.placa} fue dada de baja en Odoo y "
                     "esta asignada a este dia: hay que cambiarla.")[:400]))
        servicio = asignacion.jornada.equipo.servicio
        if servicio.consultor_id and servicio.id not in avisados:
            avisados.add(servicio.id)
            try:
                push.avisar(
                    db, servicio.consultor_id,
                    titulo=f"{servicio.folio}: la unidad {vehiculo.placa} "
                           "ya no esta en la flota",
                    cuerpo=(f"Estaba asignada el "
                            f"{asignacion.jornada.fecha:%d/%m}. Hay que "
                            "cambiarla."),
                    url=f"/consola/#/servicio/{servicio.id}",
                    etiqueta=f"baja-unidad-{vehiculo.id}-{servicio.id}")
            except Exception:                         # noqa: BLE001
                registro.exception("no se pudo avisar la baja de %s",
                                   vehiculo.placa)


def _leer_taller(odoo) -> tuple:
    """(registros, error). Los registros traen sus fechas como `entrada`
    y `salida`; si Odoo no tiene esos campos, no se lee el taller."""
    campos = odoo.campos("fleet.vehicle.log.services")
    if ENTRADA not in campos or SALIDA not in campos:
        return [], ("Odoo no tiene los campos de fecha de entrada y salida "
                    "del taller: no se leyo el taller.")
    filas = odoo.leer("fleet.vehicle.log.services", [],
                      CAMPOS_TALLER + [ENTRADA, SALIDA])
    for f in filas:
        f["entrada"], f["salida"] = f.get(ENTRADA), f.get(SALIDA)
    return filas, None


def sincronizar(db: Session, odoo, ensayo: bool = True,
                quien: m.Usuario | None = None,
                automatica: bool = False) -> dict:
    """Lee la flota y el taller de Odoo y, si no es ensayo, los guarda."""
    ahora = _utc()
    relojes = reloj.Relojes(db)
    etiquetas = {t["id"]: t.get("name")
                 for t in odoo.leer("fleet.vehicle.tag", [], ["name"])}
    unidades = odoo.leer("fleet.vehicle", [], CAMPOS)
    categorias, plazas, vehiculos = _fotos_fijas(db)
    plan = reglas.planear(unidades, etiquetas, vehiculos, categorias, plazas)

    estados = {}
    if plan["revisar_salida"]:
        estados = {f["id"]: f for f in odoo.leer(
            "fleet.vehicle",
            [["id", "in", [v["odoo_id"] for v in plan["revisar_salida"]]]],
            ["active", "tag_ids"], archivados=True)}
    bajas, pendientes_de_salida = reglas.clasificar_salidas(
        plan["revisar_salida"], estados, etiquetas)
    plan["pendientes"].extend(pendientes_de_salida)
    for baja in bajas:
        baja["dias_por_delante"] = len(
            dias_por_delante(db, baja["vehiculo_id"], relojes))

    registros, error_taller = _leer_taller(odoo)
    existentes = _del_taller(db)

    def plan_del_taller():
        por_odoo = {v.odoo_id: v.id for v in db.query(m.Vehiculo).filter(
            m.Vehiculo.odoo_id.isnot(None)).all()}
        if ensayo:
            # Lo que este plan vincula o da de alta todavia no tiene id en
            # Centauro: para contar basta una marca.
            por_odoo.update({x["odoo_id"]: x["vehiculo_id"]
                             for x in plan["vinculos"]})
            por_odoo.update({a["odoo_id"]: f"nueva-{a['odoo_id']}"
                             for a in plan["altas"]})
        return reglas.planear_taller(registros, por_odoo, existentes)

    def informe_con(taller):
        return {
            "ensayo": ensayo,
            "leidas": plan["leidas"],
            "altas": [{k: a[k] for k in ("odoo_id", "placa", "categoria", "plaza")}
                      for a in plan["altas"]],
            "vinculadas": plan["vinculos"],
            "cambios": [{k: c[k] for k in ("vehiculo_id", "odoo_id", "placa", "que")}
                        for c in plan["cambios"]],
            "bajas": bajas,
            "pendientes": plan["pendientes"],
            "sin_cambio": plan["sin_cambio"],
            "taller": {"nuevas": len(taller["crear"]),
                       "cambios": len(taller["cambiar"]),
                       "borradas": len(taller["borrar"]),
                       "sin_cambio": taller["sin_cambio"],
                       "de_otras_unidades": taller["de_otras_unidades"],
                       "pendientes": taller["pendientes"],
                       "error": error_taller},
        }

    if ensayo:
        return informe_con(plan_del_taller())

    # ------------------------------------------------------------ aplicar
    for alta in plan["altas"]:
        db.add(m.Vehiculo(
            placa=alta["placa"], categoria_id=alta["categoria_id"],
            plaza_id=alta["plaza_id"], marca_modelo=alta["marca_modelo"],
            color=alta["color"], modelo_anio=alta["modelo_anio"],
            odoo_id=alta["odoo_id"], odoo_sincronizado_en=ahora,
            activo=True, rentado=False))
    for vinculo in plan["vinculos"]:
        db.get(m.Vehiculo, vinculo["vehiculo_id"]).odoo_id = vinculo["odoo_id"]
    for cambio in plan["cambios"]:
        vehiculo = db.get(m.Vehiculo, cambio["vehiculo_id"])
        for campo, valor in cambio["valores"].items():
            setattr(vehiculo, campo, valor)
    for vehiculo_id in plan["procesadas"]:
        vehiculo = db.get(m.Vehiculo, vehiculo_id)
        vehiculo.odoo_sincronizado_en = ahora
        vehiculo.baja_odoo_en = None
    db.flush()

    for baja in bajas:
        _dar_de_baja(db, baja, ahora, relojes)

    taller = plan_del_taller()
    for nueva in taller["crear"]:
        db.add(m.TallerVehiculo(
            vehiculo_id=nueva["vehiculo_id"], desde=nueva["desde"],
            hasta=nueva["hasta"], tipo=m.MotivoCambio(nueva["tipo"]),
            taller=nueva["taller"], nota=nueva["nota"],
            odoo_id=nueva["odoo_id"]))
    for cambio in taller["cambiar"]:
        fila = db.get(m.TallerVehiculo, cambio["id"])
        fila.vehiculo_id, fila.desde, fila.hasta = (
            cambio["vehiculo_id"], cambio["desde"], cambio["hasta"])
        fila.tipo = m.MotivoCambio(cambio["tipo"])
        fila.taller, fila.nota = cambio["taller"], cambio["nota"]
    for fila_id in taller["borrar"]:
        db.delete(db.get(m.TallerVehiculo, fila_id))

    informe = informe_con(taller)
    hubo_algo = (plan["altas"] or plan["vinculos"] or plan["cambios"] or bajas
                 or taller["crear"] or taller["cambiar"] or taller["borrar"])
    fila = m.SincronizacionOdoo(
        tipo=TIPO, automatica=automatica,
        hecha_por_id=quien.persona_id if quien else None,
        leidos=plan["leidas"], altas=len(plan["altas"]),
        cambios=_tocadas(plan),
        bajas=len(bajas), pendientes=len(plan["pendientes"]),
        detalle=(json.dumps(informe, ensure_ascii=False, default=str)
                 if hubo_algo or not automatica else None))
    db.add(fila)
    db.flush()
    if quien is not None:
        accesos.anotar(
            db, quien, "flota leida de odoo", "sincronizacion_odoo", fila.id,
            despues=(f"{len(plan['altas'])} altas, "
                     f"{_tocadas(plan)} cambios, "
                     f"{len(bajas)} bajas, {len(taller['crear'])} al taller"))
    db.commit()
    return informe


def _tocadas(plan: dict) -> int:
    """Cuantas unidades cambian o se vinculan, cada una una vez: la que se
    vincula y ademas trae algo distinto sale en las dos listas."""
    return len({c["vehiculo_id"] for c in plan["cambios"]}
               | {v["vehiculo_id"] for v in plan["vinculos"]})


def resumen(informe: dict) -> dict:
    """Solo cuentas: para la terminal y para la tarea de cada hora."""
    faltas = {}
    for p in informe["pendientes"] + informe["taller"]["pendientes"]:
        for falta in p["falta"]:
            if falta.startswith("la plaza"):
                falta = "plaza que no existe en Centauro"
            elif falta.startswith("la categoria"):
                falta = "categoria que no existe en Centauro"
            elif falta.startswith("terminado sin fecha"):
                falta = "taller terminado sin fecha de salida"
            faltas[falta] = faltas.get(falta, 0) + 1
    t = informe["taller"]
    return {"leidas": informe["leidas"], "altas": len(informe["altas"]),
            "vinculadas": len(informe["vinculadas"]),
            "cambios": len(informe["cambios"]), "bajas": len(informe["bajas"]),
            "sin_cambio": informe["sin_cambio"], "pendientes": faltas,
            "taller": {k: t[k] for k in ("nuevas", "cambios", "borradas",
                                         "sin_cambio", "de_otras_unidades",
                                         "error")}}


def sincronizar_si_toca(db: Session, odoo=None) -> dict:
    """La tarea de cada hora. No arranca sola: espera a que alguien haya
    hecho la primera lectura a mano, despues de ver el ensayo."""
    from app import odoo_api

    primera = (db.query(m.SincronizacionOdoo)
               .filter_by(tipo=TIPO, automatica=False).first())
    if primera is None:
        return {"omitido": "falta la primera lectura a mano"}
    if odoo is None:
        if not odoo_api.hay_conexion():
            return {"omitido": "Odoo no esta conectado"}
        odoo = odoo_api.cliente()
    try:
        return resumen(sincronizar(db, odoo, ensayo=False, automatica=True))
    except odoo_api.NoResponde as error:
        db.rollback()
        registro.warning("odoo no respondio al leer la flota: %s", error)
        return {"error": str(error)}

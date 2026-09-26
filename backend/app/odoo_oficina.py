# -*- coding: utf-8 -*-
"""El personal de oficina, leido de Odoo (seccion 74).

Segundo paso de la propuesta Puestos y Odoo (Salvador, 26 sep): la gente
de oficina con correo de trabajo en Odoo llega a Centauro con su puesto
y su departamento, y Recursos Humanos le da su acceso a la consola con
el puesto que eso sugiere, en Accesos. Cuando Odoo la archiva, su acceso
se cierra.

Funciona igual que la lectura del personal de seguridad (seccion 64):

  * Ensayo: dice que haria sin guardar nada.
  * La primera vez se aplica a mano, despues de ver el ensayo; de ahi en
    adelante se lee sola cada hora.
  * Nunca escribe en Odoo.

Lo que no hace, a proposito: dar accesos. Un acceso a la consola es una
decision de Recursos Humanos, no de una lectura: la lectura solo deja a
la persona lista, con su puesto sugerido, para que RH lo de con un clic.

Las reglas viven en odoo_oficina_reglas.py, sin base de datos.
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import accesos
from app import models as m
from app import odoo_oficina_reglas as reglas
from app import odoo_personal_reglas

registro = logging.getLogger("centauro.odoo")

TIPO = "oficina"
CAMPOS = ["name", "job_id", "job_title", "department_id", "work_location_id",
          "work_email", "write_date"]


def _utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fotos_fijas(db: Session) -> tuple:
    plazas = {odoo_personal_reglas.normal(p.nombre):
              {"id": p.id, "nombre": p.nombre, "pais_id": p.pais_id}
              for p in db.query(m.Plaza).filter(m.Plaza.activo.is_(True)).all()}
    usuarios = db.query(m.Usuario).all()
    de_campo = {u.persona_id for u in usuarios
                if u.rol == m.Rol.PERSONAL_SEGURIDAD}
    personas = [{
        "id": p.id, "odoo_id": p.odoo_id, "nombre": p.nombre,
        "correo": p.correo, "plaza_id": p.plaza_id, "activo": p.activo,
        "oficina": p.oficina, "de_campo": p.id in de_campo,
        "puesto_odoo": p.puesto_odoo, "area_odoo": p.area_odoo,
        "sincronizado_en": p.odoo_sincronizado_en,
    } for p in db.query(m.Persona).all()]
    correos = {u.correo.strip().lower(): u.persona_id
               for u in usuarios if u.correo}
    return plazas, personas, correos


def ultimo_informe(db: Session) -> tuple:
    """(cuando, informe) de la ultima lectura que dejo su detalle. De ahi
    salen, en Accesos, los que no tienen correo de trabajo en Odoo."""
    fila = (db.query(m.SincronizacionOdoo)
            .filter(m.SincronizacionOdoo.tipo == TIPO,
                    m.SincronizacionOdoo.detalle.isnot(None))
            .order_by(m.SincronizacionOdoo.hecha_en.desc(),
                      m.SincronizacionOdoo.id.desc())
            .first())
    if fila is None:
        return None, None
    return fila.hecha_en, json.loads(fila.detalle)


def sincronizar(db: Session, odoo, ensayo: bool = True,
                quien: m.Usuario | None = None,
                automatica: bool = False) -> dict:
    """Lee el personal de oficina de Odoo y, si no es ensayo, lo guarda."""
    ahora = _utc()
    empleados = odoo.leer("hr.employee", [], CAMPOS)
    plazas, personas, correos = _fotos_fijas(db)
    plan = reglas.planear(empleados, personas, plazas, correos)

    estados = {}
    if plan["revisar_salida"]:
        estados = {f["id"]: f for f in odoo.leer(
            "hr.employee",
            [["id", "in", [p["odoo_id"] for p in plan["revisar_salida"]]]],
            ["active"], archivados=True)}
    bajas, pendientes_de_salida = reglas.clasificar_salidas(
        plan["revisar_salida"], estados)
    plan["pendientes"].extend(pendientes_de_salida)
    usuarios = {u.persona_id: u for u in db.query(m.Usuario).all()}
    for baja in bajas:
        usuario = usuarios.get(baja["persona_id"])
        deuda = accesos.viaticos_sin_cerrar(db, baja["persona_id"])
        baja["acceso"] = ("no tenia" if usuario is None or not usuario.activo
                          else "sigue abierto hasta que compruebe sus "
                               "viaticos" if deuda else "se cierra")

    # A quien de los que llegan no se le podra sugerir puesto: RH lo
    # escoge a mano. Se dice desde el ensayo, para corregirlo antes --con
    # los puestos de Odoo de cada puesto de Centauro, en Accesos--.
    puestos = sugeribles(db)
    sin_sugerencia = [{"odoo_id": a["odoo_id"], "nombre": a["nombre"],
                       "puesto_odoo": a["puesto_odoo"]}
                      for a in plan["altas"]
                      if sugerencia(a["puesto_odoo"], puestos) is None]

    informe = {
        "ensayo": ensayo,
        "leidos": plan["leidos"],
        "altas": [{k: a[k] for k in ("odoo_id", "nombre", "correo", "plaza",
                                     "puesto_odoo", "area_odoo")}
                  for a in plan["altas"]],
        "vinculadas": plan["vinculos"],
        "cambios": [{k: c[k] for k in ("persona_id", "odoo_id", "nombre", "que")}
                    for c in plan["cambios"]],
        "bajas": bajas,
        "pendientes": plan["pendientes"],
        "sin_correo": plan["sin_correo"],
        "sin_lugar": plan["sin_lugar"],
        "sin_sugerencia": sin_sugerencia,
        "sin_cambio": plan["sin_cambio"],
    }
    if ensayo:
        return informe

    # ------------------------------------------------------------ aplicar
    for alta in plan["altas"]:
        db.add(m.Persona(
            nombre=alta["nombre"], correo=alta["correo"],
            plaza_id=alta["plaza_id"], odoo_id=alta["odoo_id"], activo=True,
            es_freelance=False, oficina=True,
            puesto_odoo=alta["puesto_odoo"], area_odoo=alta["area_odoo"],
            odoo_sincronizado_en=ahora))

    for vinculo in plan["vinculos"]:
        persona = db.get(m.Persona, vinculo["persona_id"])
        persona.odoo_id = vinculo["odoo_id"]
        persona.oficina = True

    for cambio in plan["cambios"]:
        persona = db.get(m.Persona, cambio["persona_id"])
        for campo, valor in cambio["valores"].items():
            setattr(persona, campo, valor)
            # Entra con su correo de trabajo: si Odoo lo cambia, cambia
            # tambien la llave de su acceso.
            if campo == "correo" and cambio["persona_id"] in usuarios:
                usuarios[cambio["persona_id"]].correo = valor

    for persona_id in plan["procesadas"]:
        persona = db.get(m.Persona, persona_id)
        persona.odoo_sincronizado_en = ahora
        persona.baja_odoo_en = None
        persona.oficina = True

    for baja in bajas:
        persona = db.get(m.Persona, baja["persona_id"])
        persona.activo = False
        persona.baja_odoo_en = ahora
        usuario = usuarios.get(persona.id)
        # Con `activo` en falso la sesion abierta muere en su siguiente
        # clic: usuario_actual lo revisa en cada peticion. Quien se va
        # debiendo viaticos los comprueba primero, como en el panel de
        # accesos.
        if (usuario is not None and usuario.activo
                and not accesos.viaticos_sin_cerrar(db, persona.id)):
            usuario.activo = False
            if quien is not None:
                accesos.anotar(db, quien, "acceso cerrado", "usuario",
                               usuario.id, detalle="baja en Odoo")

    # La de cada hora deja su renglon siempre --se sabe que corrio--, y su
    # detalle cuando hubo algo: tambien si cambio quien no tiene correo de
    # trabajo, que es la lista que Recursos Humanos mira en Accesos.
    _, anterior = ultimo_informe(db)
    antes = {x["odoo_id"] for x in (anterior or {}).get("sin_correo", [])}
    ahora_sin = {x["odoo_id"] for x in plan["sin_correo"]}
    hubo_algo = (plan["altas"] or plan["vinculos"] or plan["cambios"] or bajas
                 or antes != ahora_sin or anterior is None)
    fila = m.SincronizacionOdoo(
        tipo=TIPO, automatica=automatica,
        hecha_por_id=quien.persona_id if quien else None,
        leidos=plan["leidos"], altas=len(plan["altas"]),
        cambios=len({c["persona_id"] for c in plan["cambios"]}
                    | {v["persona_id"] for v in plan["vinculos"]}),
        bajas=len(bajas), pendientes=len(plan["pendientes"]),
        detalle=(json.dumps(informe, ensure_ascii=False, default=str)
                 if hubo_algo or not automatica else None))
    db.add(fila)
    db.flush()
    if quien is not None:
        accesos.anotar(
            db, quien, "personal de oficina leido de odoo",
            "sincronizacion_odoo", fila.id,
            despues=(f"{len(plan['altas'])} altas, {len(plan['cambios'])} "
                     f"cambios, {len(bajas)} bajas, "
                     f"{len(plan['sin_correo'])} sin correo de trabajo"))
    db.commit()
    return informe


def resumen(informe: dict) -> dict:
    """Solo cuentas: para la tarea de cada hora."""
    return {"leidos": informe["leidos"], "altas": len(informe["altas"]),
            "vinculadas": len(informe["vinculadas"]),
            "cambios": len(informe["cambios"]), "bajas": len(informe["bajas"]),
            "sin_correo": len(informe["sin_correo"]),
            "pendientes": len(informe["pendientes"])}


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
        registro.warning("odoo no respondio al leer la oficina: %s", error)
        return {"error": str(error)}


# ------------------------------------------------------------ la sugerencia

def sugeribles(db: Session) -> list:
    """Lo que se puede sugerir: los puestos encendidos que dicen a que
    puestos de Odoo se parecen, y los dos que entran con su rol."""
    from app import puestos_base

    salida = [{"tipo": "puesto", "categoria_id": c.id, "nombre": c.nombre,
               "rol": c.rol.value if c.rol else None,
               "patrones": reglas.patrones(c.puestos_odoo)}
              for c in db.query(m.CategoriaAcceso)
              .filter(m.CategoriaAcceso.activa.is_(True)).all()
              if c.puestos_odoo]
    salida += [{"tipo": "rol", "categoria_id": None, "nombre": p["nombre"],
                "rol": p["rol"].value,
                "patrones": reglas.patrones(p["puestos_odoo"])}
               for p in puestos_base.POR_ROL]
    return salida


def sugerencia(puesto_odoo: str | None, puestos: list) -> dict | None:
    s = reglas.sugerir(puesto_odoo, puestos)
    if s is None:
        return None
    return {k: s[k] for k in ("tipo", "categoria_id", "nombre", "rol")}

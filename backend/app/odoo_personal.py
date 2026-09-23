# -*- coding: utf-8 -*-
"""El personal de seguridad, leido de Odoo.

Decision de Salvador, 23 de septiembre: etapa 1 de la conexion con Odoo.
Odoo es el maestro de empleados, asi que Centauro lee de ahi a la gente
que va a la calle en vez de capturarla a mano.

  * Entra el personal de seguridad: puesto «Personal de Seguridad» o
    «Security Driver». Monitoristas, oficina y guardias no.
  * La llave es el numero interno de Odoo: un cambio de nombre o de
    correo ya no parte a nadie en dos.
  * Lo que viene de Odoo --nombre, plaza, celular, correo, referencia,
    fecha de ingreso y foto-- manda. En Centauro no se edita (el catalogo
    lo rechaza): se corrige en Odoo. Lo de la operacion --a que servicio
    va, con que rol, sus viaticos-- sigue siendo de Centauro.
  * Un campo vacio en Odoo no borra el de Centauro.
  * Alta: la persona y su acceso a la app, sin contrasena. Entra con el
    codigo de cuatro digitos que le dicta su consultor o la central.
  * Baja: si Odoo la archiva, deja de estar disponible en la siguiente
    lectura y la central recibe una alerta en cada dia que tenia por
    delante. Su acceso se cierra en ese momento, salvo que deba viaticos:
    entonces sigue abierto solo para que los compruebe, y se cierra solo
    en cuanto no deba nada. Es la misma regla que ya tenia el panel de
    accesos: el que trae dinero de la empresa no se va hasta comprobarlo.
  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.
  * Nunca escribe en Odoo.
  * Ensayo: dice que haria sin guardar nada.
  * La tarea de cada hora no arranca sola: espera a que alguien haya
    hecho la primera sincronizacion a mano, despues de ver el ensayo.

Los datos del banco no se leen en esta etapa: son lo mas delicado que
guarda el sistema y su lectura se decide aparte.

Las reglas viven en odoo_personal_reglas.py, sin base de datos; aqui solo
se leen las fotos fijas y se aplica lo que ellas deciden.
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import accesos
from app import models as m
from app import odoo_personal_reglas as reglas
from app import reloj, telefonos

registro = logging.getLogger("centauro.odoo")

TIPO = "personal"
CAMPOS = ["name", "job_id", "job_title", "work_location_id", "work_email",
          "private_email", "mobile_phone", "registration_number",
          "first_contract_date", "write_date"]
ACABADAS = (m.EstatusJornada.TERMINADA, m.EstatusJornada.CANCELADA)


def _utc() -> datetime:
    """Sin zona y en UTC, como el write_date que manda Odoo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fotos_fijas(db: Session) -> tuple:
    plazas = {reglas.normal(p.nombre): {"id": p.id, "nombre": p.nombre,
                                        "pais_id": p.pais_id}
              for p in db.query(m.Plaza).filter(m.Plaza.activo.is_(True)).all()}
    personas = [{
        "id": p.id, "odoo_id": p.odoo_id, "nombre": p.nombre,
        "correo": p.correo, "plaza_id": p.plaza_id,
        "pais_id": p.plaza.pais_id if p.plaza else None,
        "activo": p.activo, "telefono": p.telefono,
        "referencia": p.referencia, "fecha_ingreso": p.fecha_ingreso,
        "foto": bool(p.foto_url), "sincronizado_en": p.odoo_sincronizado_en,
        "baja_odoo_en": p.baja_odoo_en,
    } for p in db.query(m.Persona).all()]
    correos = {u.correo.strip().lower(): u.persona_id
               for u in db.query(m.Usuario).all() if u.correo}
    return plazas, personas, correos


def dias_por_delante(db: Session, persona_id: int,
                     relojes: reloj.Relojes | None = None) -> list:
    """Las asignaciones de esa persona de hoy en adelante.

    El hoy es el del pais de cada servicio, como en el panel de accesos:
    un servicio en Sao Paulo ya arranco cuando en Mexico todavia es de
    madrugada. El dia de hoy cuenta aunque ya este en curso: es el que
    mas urge cubrir.
    """
    relojes = relojes or reloj.Relojes(db)
    filas = (db.query(m.AsignacionPersonal)
             .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
             .filter(m.AsignacionPersonal.persona_id == persona_id,
                     m.AsignacionPersonal.relevado_en.is_(None),
                     m.Jornada.estatus.notin_(ACABADAS))
             .order_by(m.Jornada.fecha).all())
    salida = []
    for a in filas:
        servicio = a.jornada.equipo.servicio if a.jornada.equipo else None
        if servicio and a.jornada.fecha >= relojes.hoy(servicio.pais_id):
            salida.append(a)
    return salida


def _accesos_por_cerrar(db: Session) -> list:
    """Dadas de baja por Odoo que conservaban el acceso por deber
    viaticos, y que ya no deben nada."""
    filas = (db.query(m.Persona, m.Usuario)
             .join(m.Usuario, m.Usuario.persona_id == m.Persona.id)
             .filter(m.Persona.baja_odoo_en.isnot(None),
                     m.Persona.activo.is_(False),
                     m.Usuario.activo.is_(True))
             .all())
    return [(p, u) for p, u in filas if not accesos.viaticos_sin_cerrar(db, p.id)]


def _dar_de_baja(db: Session, baja: dict, ahora: datetime,
                 relojes: reloj.Relojes) -> None:
    from app import push

    persona = db.get(m.Persona, baja["persona_id"])
    persona.activo = False
    persona.baja_odoo_en = ahora
    deuda = accesos.viaticos_sin_cerrar(db, persona.id)
    usuario = db.query(m.Usuario).filter_by(persona_id=persona.id).first()
    # Con `activo` en falso la sesion abierta muere en el siguiente clic:
    # usuario_actual lo revisa en cada peticion.
    if usuario is not None and not deuda:
        usuario.activo = False

    extra = (f" Tiene {len(deuda)} viatico(s) sin cerrar." if deuda else "")
    avisados = set()
    for asignacion in dias_por_delante(db, persona.id, relojes):
        db.add(m.Alerta(
            jornada_id=asignacion.jornada_id,
            tipo=m.TipoAlerta.PERSONAL_DE_BAJA, persona_id=persona.id,
            mensaje=(f"{persona.nombre} fue dado de baja en Odoo y esta "
                     "asignado a este dia: hay que reemplazarlo." + extra)[:400]))
        servicio = asignacion.jornada.equipo.servicio
        if servicio.consultor_id and servicio.id not in avisados:
            avisados.add(servicio.id)
            try:
                push.avisar(
                    db, servicio.consultor_id,
                    titulo=f"{servicio.folio}: {persona.nombre} ya no esta "
                           "en la empresa",
                    cuerpo=(f"Estaba asignado el "
                            f"{asignacion.jornada.fecha:%d/%m}. Hay que "
                            "reemplazarlo."),
                    # El consultor trabaja en la consola, no en la app de
                    # campo.
                    url=f"/consola/#/servicio/{servicio.id}",
                    etiqueta=f"baja-{persona.id}-{servicio.id}")
            except Exception:                         # noqa: BLE001
                # Un aviso que no sale no frena la baja: la alerta de la
                # central ya quedo.
                registro.exception("no se pudo avisar la baja de %s",
                                   persona.nombre)


def _contar_fotos(odoo, ids: list) -> tuple:
    """(filas leidas, cuantas son foto de verdad). Una sola lectura."""
    if not ids:
        return [], 0
    filas = odoo.leer("hr.employee", [["id", "in", ids]], ["image_128"])
    return filas, sum(1 for f in filas if reglas.foto_de(f.get("image_128")))


def sincronizar(db: Session, odoo, ensayo: bool = True,
                quien: m.Usuario | None = None,
                automatica: bool = False) -> dict:
    """Lee el personal de Odoo y, si no es ensayo, lo guarda.

    Devuelve el informe: altas, vinculadas, cambios, bajas, accesos que se
    cierran, pendientes y fotos. El ensayo lo devuelve igual, sin tocar
    nada: lee de Odoo lo mismo, fotos incluidas, para que las cuentas
    sean las de verdad.
    """
    ahora = _utc()
    relojes = reloj.Relojes(db)
    empleados = odoo.leer("hr.employee", [], CAMPOS)
    plazas, personas, correos = _fotos_fijas(db)
    plan = reglas.planear(
        empleados, personas, plazas, correos,
        lambda numero, pais_id: telefonos.normalizar(db, numero, pais_id))

    estados = {}
    if plan["revisar_salida"]:
        estados = {f["id"]: f for f in odoo.leer(
            "hr.employee",
            [["id", "in", [p["odoo_id"] for p in plan["revisar_salida"]]]],
            ["active"], archivados=True)}
    bajas, pendientes_de_salida = reglas.clasificar_salidas(
        plan["revisar_salida"], estados)
    plan["pendientes"].extend(pendientes_de_salida)
    for baja in bajas:
        deuda = accesos.viaticos_sin_cerrar(db, baja["persona_id"])
        baja["dias_por_delante"] = len(
            dias_por_delante(db, baja["persona_id"], relojes))
        baja["viaticos_sin_cerrar"] = len(deuda)
        baja["acceso"] = ("sigue abierto hasta que compruebe sus viaticos"
                          if deuda else "se cierra")
    por_cerrar = _accesos_por_cerrar(db)
    filas_de_foto, reales = _contar_fotos(odoo, plan["fotos"])

    informe = {
        "ensayo": ensayo,
        "leidos": plan["leidos"],
        "altas": [{k: a[k] for k in ("odoo_id", "nombre", "plaza", "correo")}
                  for a in plan["altas"]],
        "vinculadas": plan["vinculos"],
        "cambios": [{k: c[k] for k in ("persona_id", "odoo_id", "nombre", "que")}
                    for c in plan["cambios"]],
        "bajas": bajas,
        "accesos_cerrados": [{"persona_id": p.id, "nombre": p.nombre}
                             for p, _ in por_cerrar],
        "pendientes": plan["pendientes"],
        "sin_cambio": plan["sin_cambio"],
        # «sin_foto_real»: Odoo solo tiene el circulo con sus iniciales.
        "fotos": {"revisadas": len(filas_de_foto), "reales": reales,
                  "sin_foto_real": len(filas_de_foto) - reales,
                  "actualizadas": 0},
    }
    if ensayo:
        return informe

    # ------------------------------------------------------------ aplicar
    usados = {u.correo.strip().lower() for u in db.query(m.Usuario).all()
              if u.correo}
    for alta in plan["altas"]:
        persona = m.Persona(
            nombre=alta["nombre"], correo=alta["correo"],
            plaza_id=alta["plaza_id"], odoo_id=alta["odoo_id"], activo=True,
            es_freelance=False, telefono=alta["telefono"],
            referencia=alta["referencia"], fecha_ingreso=alta["fecha_ingreso"],
            odoo_sincronizado_en=ahora)
        db.add(persona)
        db.flush()
        db.add(m.Usuario(persona_id=persona.id, correo=alta["correo"],
                         rol=m.Rol.PERSONAL_SEGURIDAD, activo=True))
        usados.add(alta["correo"])

    for vinculo in plan["vinculos"]:
        db.get(m.Persona, vinculo["persona_id"]).odoo_id = vinculo["odoo_id"]

    usuarios = {u.persona_id: u for u in db.query(m.Usuario).all()}
    for cambio in plan["cambios"]:
        persona = db.get(m.Persona, cambio["persona_id"])
        for campo, valor in cambio["valores"].items():
            setattr(persona, campo, valor)
            if campo == "correo" and cambio["persona_id"] in usuarios:
                usuarios[cambio["persona_id"]].correo = valor
                usados.add(valor)

    for persona_id in plan["procesadas"]:
        persona = db.get(m.Persona, persona_id)
        persona.odoo_sincronizado_en = ahora
        persona.baja_odoo_en = None
        # Quien ya estaba en Centauro sin acceso a la app lo recibe, igual
        # que un alta: sin contrasena, con el codigo que le dictan.
        correo = (persona.correo or "").strip().lower()
        if persona_id not in usuarios and correo and correo not in usados:
            db.add(m.Usuario(persona_id=persona_id, correo=persona.correo,
                             rol=m.Rol.PERSONAL_SEGURIDAD, activo=True))
            usados.add(correo)
    db.flush()

    # Las fotos ya se leyeron arriba, una sola vez y solo de quien toca.
    if filas_de_foto:
        por_odoo = {p.odoo_id: p for p in db.query(m.Persona).filter(
            m.Persona.odoo_id.in_(plan["fotos"])).all()}
        for fila in filas_de_foto:
            persona = por_odoo.get(fila["id"])
            foto = reglas.foto_de(fila.get("image_128"))
            if persona is not None and foto and foto != persona.foto_url:
                persona.foto_url = foto
                informe["fotos"]["actualizadas"] += 1

    for baja in bajas:
        _dar_de_baja(db, baja, ahora, relojes)
    for _, usuario in por_cerrar:
        usuario.activo = False

    hubo_algo = (plan["altas"] or plan["vinculos"] or plan["cambios"] or bajas
                 or por_cerrar or informe["fotos"]["actualizadas"])
    fila = m.SincronizacionOdoo(
        tipo=TIPO, automatica=automatica,
        hecha_por_id=quien.persona_id if quien else None,
        leidos=plan["leidos"], altas=len(plan["altas"]),
        cambios=len(plan["cambios"]) + len(plan["vinculos"]),
        bajas=len(bajas), pendientes=len(plan["pendientes"]),
        # La de cada hora sin novedades deja su renglon --se sabe que
        # corrio-- pero no el detalle, que seria el mismo cada hora.
        detalle=(json.dumps(informe, ensure_ascii=False, default=str)
                 if hubo_algo or not automatica else None))
    db.add(fila)
    db.flush()
    if quien is not None:
        accesos.anotar(
            db, quien, "personal leido de odoo", "sincronizacion_odoo",
            fila.id, despues=(f"{len(plan['altas'])} altas, "
                              f"{len(plan['cambios']) + len(plan['vinculos'])} "
                              f"cambios, {len(bajas)} bajas, "
                              f"{len(plan['pendientes'])} pendientes"))
    db.commit()
    return informe


def resumen(informe: dict) -> dict:
    """Solo cuentas: para la terminal y para la tarea de cada hora."""
    faltas = {}
    for p in informe["pendientes"]:
        for falta in p["falta"]:
            clave = "plaza no existe" if falta.startswith("la plaza") else falta
            faltas[clave] = faltas.get(clave, 0) + 1
    return {"leidos": informe["leidos"], "altas": len(informe["altas"]),
            "vinculadas": len(informe["vinculadas"]),
            "cambios": len(informe["cambios"]), "bajas": len(informe["bajas"]),
            "accesos_cerrados": len(informe["accesos_cerrados"]),
            "sin_cambio": informe["sin_cambio"],
            "pendientes": faltas, "fotos": informe["fotos"]}


def sincronizar_si_toca(db: Session, odoo=None) -> dict:
    """La tarea de cada hora. No arranca sola: espera a que alguien haya
    hecho la primera sincronizacion a mano, despues de ver el ensayo."""
    from app import odoo_api

    primera = (db.query(m.SincronizacionOdoo)
               .filter_by(tipo=TIPO, automatica=False).first())
    if primera is None:
        return {"omitido": "falta la primera sincronizacion a mano"}
    if odoo is None:
        if not odoo_api.hay_conexion():
            return {"omitido": "Odoo no esta conectado"}
        odoo = odoo_api.cliente()
    try:
        return resumen(sincronizar(db, odoo, ensayo=False, automatica=True))
    except odoo_api.NoResponde as error:
        # Lo mas probable a los tres meses: la llave vencio. Queda en el
        # registro del worker y la siguiente hora lo vuelve a intentar.
        db.rollback()
        registro.warning("odoo no respondio al leer el personal: %s", error)
        return {"error": str(error)}

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

Cada pais lee a su gente por su compania (seccion 121): Mexico, CENTAURO
ASS con sus puestos de siempre; Brasil, su compania con «Motorista
Executivo Bilingue» o «Condutor Folguista». A la gente de Brasil le pueden
faltar el CPF, la CNH y la cuenta bancaria: entra igual y se dice como
«por capturar».

La cuenta bancaria tambien viene de Odoo (decision 7 de Salvador, 29 de
septiembre, seccion 105): los registros bancarios viven alla, Connect
solo los lee en esta misma lectura y no los captura. Si el usuario de la
conexion no puede leer las cuentas --o esta version de Odoo no trae el
campo-- la lectura sigue sin cuentas, lo anota y no toca lo guardado.

Las reglas viven en odoo_personal_reglas.py, sin base de datos; aqui solo
se leen las fotos fijas y se aplica lo que ellas deciden.
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import accesos, odoo_api
from app import models as m
from app import odoo_personal_reglas as reglas
from app import reloj, telefonos
from app.config import settings

registro = logging.getLogger("centauro.odoo")

TIPO = "personal"
CAMPOS = ["name", "job_id", "job_title", "work_location_id", "work_email",
          "private_email", "mobile_phone", "registration_number",
          "first_contract_date", "write_date", "company_id"]
# La cuenta bancaria del empleado (seccion 105): un many2one a
# res.partner.bank. Va aparte de CAMPOS porque puede no estar: en Odoo
# es un campo de RH (grupo hr.group_hr_user) y `fields_get` no se lo
# ensena a quien no lo puede leer; pedirlo sin permiso tumbaria la
# lectura entera del personal, cada hora.
CAMPO_CUENTA = reglas.CAMPO_CUENTA
MODELO_CUENTA = "res.partner.bank"
CAMPOS_CUENTA = ["acc_number", "acc_holder_name", "bank_id", "partner_id"]
SIN_PERMISO_CUENTAS = ("sin permiso para leer cuentas bancarias: la "
                       "lectura siguio sin ellas y no se toco lo guardado")
# Lo que `fields_get` no dice: si el campo falta porque no existe en esta
# version de Odoo o porque el usuario no lo puede leer. Lo dice el
# catalogo de campos de Odoo (ir.model.fields).
NO_EXISTE_CUENTA = ("el campo de la cuenta bancaria no existe en esta "
                    "version de Odoo (se busco " + " y ".join(reglas.CAMPOS_DE_CUENTA)
                    + "): la lectura siguio sin cuentas y no se toco lo guardado")
SIN_SABER_CUENTAS = ("no se pudo leer el campo de la cuenta bancaria --o no "
                     "existe en esta version de Odoo, o el usuario de la "
                     "conexion no tiene permiso--: la lectura siguio sin "
                     "cuentas y no se toco lo guardado")
ACABADAS = (m.EstatusJornada.TERMINADA, m.EstatusJornada.CANCELADA)


def _utc() -> datetime:
    """Sin zona y en UTC, como el write_date que manda Odoo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _plazas_y_paises(db: Session) -> tuple:
    """Las ciudades por pais (su id) y nombre normalizado, y los paises
    por codigo (seccion 121): cada quien se busca entre las de su pais."""
    plazas = {}
    for p in db.query(m.Plaza).filter(m.Plaza.activo.is_(True)).all():
        plazas.setdefault(p.pais_id, {})[reglas.normal(p.nombre)] = {
            "id": p.id, "nombre": p.nombre, "pais_id": p.pais_id}
    paises = {p.codigo.upper(): {"id": p.id, "nombre": p.nombre}
              for p in db.query(m.Pais).all()}
    return plazas, paises


def _fotos_fijas(db: Session) -> tuple:
    plazas, _ = _plazas_y_paises(db)
    personas = [{
        "id": p.id, "odoo_id": p.odoo_id, "nombre": p.nombre,
        "correo": p.correo, "plaza_id": p.plaza_id,
        "pais_id": p.plaza.pais_id if p.plaza else None,
        "activo": p.activo, "telefono": p.telefono,
        "referencia": p.referencia, "fecha_ingreso": p.fecha_ingreso,
        "foto": bool(p.foto_url), "sincronizado_en": p.odoo_sincronizado_en,
        "baja_odoo_en": p.baja_odoo_en, "oficina": p.oficina,
        # El freelance no se liga solo (seccion 128).
        "es_freelance": bool(p.es_freelance),
        # A donde se le deposita (seccion 105): para comparar con lo que
        # dice Odoo y cambiarlo solo cuando cambia.
        "banco": p.banco, "clabe": p.clabe, "titular_cuenta": p.titular_cuenta,
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
    alertas_de_baja(db, persona,
                    f"{persona.nombre} fue dado de baja en Odoo y esta "
                    "asignado a este dia: hay que reemplazarlo." + extra,
                    relojes)


def alertas_de_baja(db: Session, persona: m.Persona, mensaje: str,
                    relojes: reloj.Relojes | None = None) -> list:
    """Los dias por delante a los que sigue asignado quien se da de baja:
    una alerta en cada uno para la central y un aviso al consultor de cada
    servicio. La baja de Odoo y la del freelance (seccion 128, hallazgo
    r6-04) hacen lo mismo. Devuelve las asignaciones que quedan colgando."""
    from app import push

    avisados = set()
    colgando = dias_por_delante(db, persona.id, relojes)
    for asignacion in colgando:
        # Una alerta abierta por dia y persona: la baja que se deshace
        # y se vuelve a dar no apila otra sobre la que la central no ha
        # atendido.
        abierta = (db.query(m.Alerta.id)
                   .filter_by(jornada_id=asignacion.jornada_id,
                              tipo=m.TipoAlerta.PERSONAL_DE_BAJA,
                              persona_id=persona.id, atendida=False)
                   .first())
        if abierta:
            continue
        db.add(m.Alerta(
            jornada_id=asignacion.jornada_id,
            tipo=m.TipoAlerta.PERSONAL_DE_BAJA, persona_id=persona.id,
            mensaje=mensaje[:400]))
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
    return colgando


# La foto de 512 px y no la de 128. Decision de Salvador, 29 sep: la
# ficha del servicio la ensena en 120 x 150 y la de 128 se veia borrosa.
# Pesa unas decenas de KB por persona y solo viaja en fichas de una
# persona o de un equipo, nunca en listas largas.
CAMPO_FOTO = "image_512"


def _contar_fotos(odoo, ids: list) -> tuple:
    """(filas leidas, cuantas son foto de verdad). Una sola lectura."""
    if not ids:
        return [], 0
    filas = odoo.leer("hr.employee", [["id", "in", ids]], [CAMPO_FOTO])
    return filas, sum(1 for f in filas if reglas.foto_de(f.get(CAMPO_FOTO)))


def _campo_de_cuenta(odoo, visibles: dict | None = None) -> tuple:
    """(el campo de la cuenta bancaria que esta conexion ve, o None y
    por que no).

    La cuenta principal de la version saas~19.3 o, de respaldo, la de
    antes. `fields_get` deja fuera los campos que el usuario no puede leer
    y los que esta version no tiene: en los dos casos la lectura sigue
    sin cuentas (seccion 105), pero el aviso tiene que decir cual de los
    dos es --«sin permiso» con un administrador mandaba a buscar donde no
    era--. Eso lo dice ir.model.fields; si tampoco se puede leer, se dice
    que no se sabe.
    """
    if visibles is None:
        visibles = odoo.campos("hr.employee")
    for campo in reglas.CAMPOS_DE_CUENTA:
        if campo in visibles:
            return campo, None
    try:
        existen = odoo.leer("ir.model.fields",
                            [["model", "=", "hr.employee"],
                             ["name", "in", list(reglas.CAMPOS_DE_CUENTA)]],
                            ["name"])
    except odoo_api.NoResponde:
        return None, SIN_SABER_CUENTAS
    return None, SIN_PERMISO_CUENTAS if existen else NO_EXISTE_CUENTA


def _leer_cuentas(odoo, empleados: list, con_cuenta: bool,
                  por_que: str | None = None) -> tuple:
    """(cuentas por su id de Odoo, error).

    Una sola lectura por lote de `res.partner.bank`, solo de las cuentas
    que refieren los empleados de seguridad. `None` en las cuentas quiere
    decir que no se pudieron leer --sin permiso, o el campo no existe--:
    la regla entonces no toca nada de lo guardado. Un diccionario, aunque
    venga vacio, quiere decir que si se leyeron: quien no trae cuenta en
    Odoo se queda sin cuenta aqui.
    """
    if not con_cuenta:
        motivo = por_que or SIN_PERMISO_CUENTAS
        registro.warning("odoo: %s", motivo)
        return None, motivo
    ids = sorted({reglas.id_de(e.get(CAMPO_CUENTA)) for e in empleados
                  if reglas.es_de_seguridad(e)
                  and reglas.id_de(e.get(CAMPO_CUENTA))})
    if not ids:
        return {}, None
    try:
        filas = odoo.leer(MODELO_CUENTA, [["id", "in", ids]], CAMPOS_CUENTA)
    except odoo_api.NoResponde as error:
        # El empleado se leyo y las cuentas no: lo mas probable es que
        # el usuario de la conexion no tenga acceso a res.partner.bank.
        # La lectura sigue sin cuentas y no se toca lo guardado.
        registro.warning("odoo: %s (%s)", SIN_PERMISO_CUENTAS, error)
        return None, f"{SIN_PERMISO_CUENTAS} ({str(error)[:120]})"
    return {f["id"]: f for f in filas}, None


def releer_fotos(db: Session, odoo, ensayo: bool = True,
                 tanda: int = 40) -> dict:
    """Vuelve a leer de Odoo la foto de todo el personal ligado.

    Para una sola vez, al pasar de la foto de 128 a la de 512: la
    sincronizacion de cada hora solo pide la foto de quien RH toco
    despues de la ultima lectura, asi que la gente que ya estaba se
    quedaria con la chica. Por tandas, para no pedir decenas de megas de
    un golpe. Quien en Odoo solo tiene el circulo de iniciales conserva
    lo que ya tenia. Nunca escribe en Odoo.
    """
    personas = (db.query(m.Persona)
                .filter(m.Persona.odoo_id.isnot(None),
                        m.Persona.activo.is_(True))
                .all())
    por_odoo = {p.odoo_id: p for p in personas}
    ids = sorted(por_odoo)
    informe = {"revisadas": len(ids), "reales": 0, "cambian": 0}
    for i in range(0, len(ids), tanda):
        filas = odoo.leer("hr.employee", [["id", "in", ids[i:i + tanda]]],
                          [CAMPO_FOTO])
        for fila in filas:
            foto = reglas.foto_de(fila.get(CAMPO_FOTO))
            persona = por_odoo.get(fila["id"])
            if not foto or persona is None:
                continue
            informe["reales"] += 1
            if foto != persona.foto_url:
                informe["cambian"] += 1
                if not ensayo:
                    persona.foto_url = foto
    if not ensayo:
        db.commit()
    return informe


def sincronizar(db: Session, odoo, ensayo: bool = True,
                quien: m.Usuario | None = None,
                automatica: bool = False) -> dict:
    """Lee el personal de Odoo y, si no es ensayo, lo guarda.

    Devuelve el informe: altas, vinculadas, cambios, bajas, accesos que se
    cierran, pendientes y fotos. El ensayo lo devuelve igual, sin tocar
    nada: lee de Odoo lo mismo, fotos incluidas, para que las cuentas
    sean las de verdad.
    """
    if not ensayo:
        odoo_api.candado(db, TIPO)
    ahora = _utc()
    relojes = reloj.Relojes(db)
    # La cuenta bancaria solo se pide si esta conexion la puede leer
    # (seccion 105): pedirla sin permiso tumbaba la lectura entera. Se
    # pide con el nombre que tenga en este Odoo y se ve con el nuevo.
    visibles = odoo.campos("hr.employee", ["string", "type"])
    campo_cuenta, por_que = _campo_de_cuenta(odoo, visibles)
    # En que campos viven el CPF y la CNH de Brasil (seccion 121): se
    # leen solo para decir si faltan; Connect no los guarda.
    extra = reglas.campos_por_capturar(visibles, settings.odoo_campo_cpf,
                                       settings.odoo_campo_cnh)
    empleados = odoo.leer(
        "hr.employee", [],
        CAMPOS + ([campo_cuenta] if campo_cuenta else [])
        + sorted({c for c in extra.values() if c and c not in CAMPOS}))
    if campo_cuenta and campo_cuenta != CAMPO_CUENTA:
        for e in empleados:
            e[CAMPO_CUENTA] = e.pop(campo_cuenta, False)
    cuentas, error_cuentas = _leer_cuentas(odoo, empleados,
                                           campo_cuenta is not None, por_que)
    plazas, personas, correos = _fotos_fijas(db)
    _, paises = _plazas_y_paises(db)
    plan = reglas.planear(
        empleados, personas, plazas, correos,
        lambda numero, pais_id: telefonos.normalizar(db, numero, pais_id),
        cuentas=cuentas, paises=paises, campos_extra=extra)

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
        # Cuantos de cada pais (seccion 121). Brasil en cero con su gente
        # cargada en Odoo es la conexion sin su compania.
        "por_pais": [{"codigo": g["pais"], "pais": g["nombre"],
                      "leidos": plan["por_pais"][g["pais"]]}
                     for g in reglas.PERSONAL],
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
        # Odoo dice algo que no es un numero («sin dispositivo»): no se
        # guardo como telefono ni borro el que ya habia.
        "celular_no_valido": plan["celular_no_valido"],
        # Lo que a la gente de Brasil le falta en Odoo y no detiene nada:
        # el CPF, la CNH o la cuenta. Y en que campo de Odoo se buscan;
        # None: este Odoo no tiene ese campo todavia.
        "por_capturar": plan["por_capturar"],
        "campos_por_capturar": reglas.nombres_de_campos(visibles, extra),
        # «sin_foto_real»: Odoo solo tiene el circulo con sus iniciales.
        "fotos": {"revisadas": len(filas_de_foto), "reales": reales,
                  "sin_foto_real": len(filas_de_foto) - reales,
                  "actualizadas": 0},
        # Las cuentas bancarias (seccion 105): cuantos de los leidos la
        # traen en Odoo y cuantos no. Con `error`, no se leyeron y no se
        # toco nada de lo guardado.
        "cuentas": {"con_cuenta": plan["con_cuenta"],
                    "sin_cuenta": plan["sin_cuenta"],
                    "error": error_cuentas},
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
            banco=alta["banco"], clabe=alta["clabe"],
            titular_cuenta=alta["titular_cuenta"],
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
            foto = reglas.foto_de(fila.get(CAMPO_FOTO))
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
        cambios=_tocadas(plan),
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
                              f"{_tocadas(plan)} "
                              f"cambios, {len(bajas)} bajas, "
                              f"{len(plan['pendientes'])} pendientes"))
    db.commit()
    return informe


def _tocadas(plan: dict) -> int:
    """Cuantas personas cambian o se vinculan. Quien se vincula y ademas
    trae algo distinto sale en las dos listas: se cuenta una vez. Antes
    se sumaban las dos y el renglon de la lectura decia el doble."""
    return len({c["persona_id"] for c in plan["cambios"]}
               | {v["persona_id"] for v in plan["vinculos"]})


def _por_falta(lista: list) -> dict:
    faltas = {}
    for p in lista:
        for falta in p["falta"]:
            faltas[falta] = faltas.get(falta, 0) + 1
    return faltas


def resumen(informe: dict) -> dict:
    """Solo cuentas: para la terminal y para la tarea de cada hora."""
    faltas = {}
    for p in informe["pendientes"]:
        for falta in p["falta"]:
            clave = ("plaza no existe" if falta.startswith("la plaza")
                     else "puesto de un pais y compania de otro"
                     if falta.startswith("el puesto es de")
                     else "de otro pais en Centauro"
                     if falta.endswith("en Centauro es de otro pais")
                     else falta)
            faltas[clave] = faltas.get(clave, 0) + 1
    return {"leidos": informe["leidos"],
            "por_pais": {p["codigo"]: p["leidos"]
                         for p in informe.get("por_pais", [])},
            # Cuantas personas por cada cosa que falta (seccion 121), como
            # en la flota: sin CPF, sin CNH, sin cuenta bancaria.
            "por_capturar": _por_falta(informe.get("por_capturar", [])),
            "altas": len(informe["altas"]),
            "vinculadas": len(informe["vinculadas"]),
            "cambios": len(informe["cambios"]), "bajas": len(informe["bajas"]),
            "accesos_cerrados": len(informe["accesos_cerrados"]),
            "sin_cambio": informe["sin_cambio"],
            "celular_no_valido": len(informe.get("celular_no_valido", [])),
            "pendientes": faltas, "fotos": informe["fotos"],
            "cuentas": informe.get("cuentas")}


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

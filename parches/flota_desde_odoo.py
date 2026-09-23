# -*- coding: utf-8 -*-
"""La flota y el taller, leidos de Odoo (etapa 2 de la conexion).

Decisiones de Salvador, 23 sep:

  * Entran las unidades con la etiqueta «PROTECCION EJECUTIVA» o «pe».
  * La llave es el numero interno de Odoo; la primera vez, por placa.
  * Placa, categoria, plaza (la Ubicacion), marca y modelo, color y año
    vienen de Odoo; en el catalogo ya no se editan. Lo vacio no borra.
    VAN es la «Van 10 pax»; Sedan se agrega, con costo de ejemplo.
  * La foto no viene de Odoo: una por categoria, respetando el color de
    cada unidad. Se cargan en Centauro: la base y una por color.
  * Baja en Odoo: deja de ofrecerse y la central recibe una alerta en
    cada dia que la unidad tenia asignado.
  * Taller: Preventivo, Correctivo y Desgaste natural la sacan de
    circulacion de la entrada a la salida; sin salida, se da por adentro.
    De paso, el taller por fin bloquea tambien al asignar un eventual:
    hasta hoy solo lo respetaba el implantado.
  * Ensayo por consola y terminal; la tarea de cada hora espera a la
    primera lectura hecha a mano. Nunca escribe en Odoo.

Idempotente. Todas las escrituras al final.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    "models": B / "app/models.py",
    "odoo_api": B / "app/odoo_api.py",
    "rodoo": B / "app/routers/odoo.py",
    "celery": B / "app/celery_app.py",
    "disponibilidad": B / "app/disponibilidad.py",
    "catalogos": B / "app/routers/catalogos.py",
    "crud": B / "app/routers/crud.py",
    "schemas": B / "app/schemas.py",
    "seed": B / "app/seed.py",
    "tasksheet": B / "app/tasksheet.py",
    "servicios": B / "app/routers/servicios.py",
    "hoja_implantado": B / "app/hoja_implantado.py",
    "idioma": B / "app/web/idioma.js",
    "gitignore": RAIZ / ".gitignore",
    "leeme": RAIZ / "despliegue/LEEME.md",
    "bitacora": RAIZ / "BITACORA.md",
}
NUEVOS = {
    'app/odoo_flota_reglas.py': '# -*- coding: utf-8 -*-\n"""Las reglas de la flota y del taller que vienen de Odoo, sin base de datos.\n\nAqui se decide que hacer con cada unidad y con cada entrada al taller a\npartir de fotos fijas de Odoo y de Centauro. No lee ni escribe nada: por\neso se prueba sola, y el ensayo y la lectura de verdad deciden lo mismo.\n\nLas decisiones de Salvador (23 de septiembre) que viven aqui:\n\n  * Entran las unidades de Proteccion Ejecutiva: las que traen la\n    etiqueta «PROTECCION EJECUTIVA» o «pe». Logistica, Direccion y las\n    utilitarias no.\n  * La llave es el numero interno de Odoo; la primera vez se vincula por\n    placa con la que ya estaba en Centauro.\n  * Las siete categorias de Odoo son las de Centauro. VAN es la «Van 10\n    pax».\n  * La plaza sale de la Ubicacion de la unidad. El Estado de Mexico va\n    como Ciudad de Mexico.\n  * El taller: Preventivo, Correctivo y Desgaste natural sacan la unidad\n    de circulacion, de la fecha de entrada a la de salida; sin salida se\n    da por adentro. «Resguardo de Unidad» y los de contrato no cuentan.\n  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.\n"""\nimport collections\nimport re\n\nfrom app.odoo_personal_reglas import (ALIAS_PLAZA, fecha, nombre_de, normal,\n                                      texto)\n\nETIQUETAS = frozenset({"proteccion ejecutiva", "pe"})\n# El nombre de la categoria en Odoo, como codigo de Centauro. Lo que no\n# esta aqui se toma tal cual: «MINIVAN BLINDADA» -> minivan_blindada.\nALIAS_CATEGORIA = {"van": "van_10"}\nTALLER = {\n    "preventivo": "mantenimiento_preventivo",\n    "correctivo": "mantenimiento_correctivo",\n    "desgaste natural": "mantenimiento_correctivo",\n}\n\n\ndef id_de(valor):\n    """El id de un many2one, venga como [id, nombre], dict o id."""\n    if not valor:\n        return None\n    if isinstance(valor, (list, tuple)):\n        return valor[0]\n    if isinstance(valor, dict):\n        return valor.get("id")\n    return valor\n\n\ndef placa_de(valor) -> str:\n    """La placa sin espacios ni guiones y en mayusculas: «ABC-1234» y\n    «abc 1234» son la misma."""\n    return re.sub(r"[^0-9A-Z]", "", texto(valor).upper())\n\n\ndef codigo_de_categoria(nombre: str) -> str:\n    clave = normal(nombre).replace(" ", "_")\n    return ALIAS_CATEGORIA.get(clave, clave)\n\n\ndef marca_modelo_de(valor) -> str:\n    """«Toyota/SIENNA XSE» como se lee: «Toyota SIENNA XSE»."""\n    return " ".join(nombre_de(valor).replace("/", " ").split())\n\n\ndef anio_de(valor) -> int | None:\n    t = texto(valor)\n    return int(t) if t.isdigit() and 1950 < int(t) < 2100 else None\n\n\n# El color como se guarda la foto de la categoria: la primera palabra, sin\n# acentos. «Blanco perla» y «BLANCO» son la misma foto blanca.\nALIAS_COLOR = {"plateado": "plata", "silver": "plata", "white": "blanco",\n               "black": "negro", "gray": "gris", "grey": "gris",\n               "blue": "azul", "red": "rojo"}\n\n\ndef color_de(valor) -> str:\n    palabras = normal(valor).split()\n    return ALIAS_COLOR.get(palabras[0], palabras[0]) if palabras else ""\n\n\ndef plaza_de(lugar, plazas: dict) -> tuple:\n    """(plaza o None, lo que dice Odoo). `plazas` va por nombre normalizado."""\n    lugar = texto(lugar)\n    clave = normal(lugar)\n    return plazas.get(ALIAS_PLAZA.get(clave, clave)), lugar\n\n\ndef es_de_proteccion(unidad: dict, etiquetas: dict) -> bool:\n    """`etiquetas`: id -> nombre, de fleet.vehicle.tag."""\n    return any(normal(etiquetas.get(t, "")) in ETIQUETAS\n               for t in (unidad.get("tag_ids") or []))\n\n\n# ------------------------------------------------------------ las unidades\n\ndef planear(unidades: list, etiquetas: dict, vehiculos: list,\n            categorias: dict, plazas: dict) -> dict:\n    """Que hacer con cada unidad de Odoo, sin hacerlo.\n\n    `unidades`: las activas de Odoo. `vehiculos`: foto fija de la flota\n    propia de Centauro (sin las rentadas), con id, odoo_id, placa,\n    categoria_id, plaza_id, marca_modelo, color, modelo_anio, activo y\n    sincronizado_en. `categorias`: por codigo, con id y nombre.\n    `plazas`: por nombre normalizado, con id y nombre.\n    """\n    elegidas = [u for u in unidades if es_de_proteccion(u, etiquetas)]\n    por_odoo = {v["odoo_id"]: v for v in vehiculos if v.get("odoo_id")}\n    por_placa = {placa_de(v["placa"]): v for v in vehiculos if v.get("placa")}\n    cuenta = collections.Counter(placa_de(u.get("license_plate"))\n                                 for u in elegidas)\n    repetidas = {p for p, n in cuenta.items() if p and n > 1}\n\n    plan = {"leidas": len(elegidas), "altas": [], "vinculos": [],\n            "cambios": [], "pendientes": [], "sin_cambio": 0,\n            "procesadas": [], "revisar_salida": []}\n    tomadas = set()\n\n    def pendiente(u, vehiculo_id, faltas):\n        plan["pendientes"].append({"odoo_id": u["id"], "vehiculo_id": vehiculo_id,\n                                   "placa": texto(u.get("license_plate")),\n                                   "falta": faltas})\n\n    for u in elegidas:\n        placa = placa_de(u.get("license_plate"))\n        nombre_cat = nombre_de(u.get("category_id"))\n        categoria = (categorias.get(codigo_de_categoria(nombre_cat))\n                     if nombre_cat else None)\n        plaza, lugar = plaza_de(u.get("location"), plazas)\n        datos = {"marca_modelo": marca_modelo_de(u.get("model_id")) or None,\n                 "color": texto(u.get("color")) or None,\n                 "modelo_anio": anio_de(u.get("model_year"))}\n\n        vehiculo, vinculo = por_odoo.get(u["id"]), False\n        if vehiculo is None and placa and placa not in repetidas:\n            candidato = por_placa.get(placa)\n            if candidato is not None:\n                if candidato.get("odoo_id") and candidato["odoo_id"] != u["id"]:\n                    pendiente(u, candidato["id"],\n                              ["su placa ya es de otra unidad en Centauro"])\n                    continue\n                vehiculo, vinculo = candidato, True\n\n        # ------------------------------------------------ la que llega nueva\n        if vehiculo is None:\n            faltas = []\n            if not placa:\n                faltas.append("sin placa")\n            elif placa in repetidas:\n                faltas.append("placa repetida en Odoo")\n            if not nombre_cat:\n                faltas.append("sin categoria")\n            elif categoria is None:\n                faltas.append(f"la categoria «{nombre_cat}» no existe en Centauro")\n            if plaza is None:\n                faltas.append(f"la plaza «{lugar}» no existe en Centauro"\n                              if lugar else "sin plaza")\n            if faltas:\n                pendiente(u, None, faltas)\n                continue\n            tomadas.add(placa)\n            plan["altas"].append({"odoo_id": u["id"],\n                                  "placa": texto(u.get("license_plate")).upper(),\n                                  "categoria_id": categoria["id"],\n                                  "categoria": categoria["nombre"],\n                                  "plaza_id": plaza["id"], "plaza": plaza["nombre"],\n                                  **datos})\n            continue\n\n        # ------------------------------------------------ la que ya esta\n        if not vehiculo.get("activo"):\n            pendiente(u, vehiculo["id"], ["activa en Odoo pero dada de baja en "\n                                          "Centauro: reactivar a mano"])\n            continue\n\n        valores, que, avisos = {}, [], []\n        if placa and placa != placa_de(vehiculo.get("placa")):\n            otra = por_placa.get(placa)\n            if placa in repetidas:\n                avisos.append("placa repetida en Odoo")\n            elif (otra is not None and otra["id"] != vehiculo["id"]) \\\n                    or placa in tomadas:\n                avisos.append("su placa nueva ya es de otra unidad en Centauro")\n            else:\n                valores["placa"] = texto(u.get("license_plate")).upper()\n                que.append("placa")\n                tomadas.add(placa)\n        if categoria is not None and categoria["id"] != vehiculo.get("categoria_id"):\n            valores["categoria_id"] = categoria["id"]\n            que.append("categoria")\n        elif nombre_cat and categoria is None:\n            avisos.append(f"la categoria «{nombre_cat}» no existe en Centauro")\n        if plaza is not None and plaza["id"] != vehiculo.get("plaza_id"):\n            valores["plaza_id"] = plaza["id"]\n            que.append("plaza")\n        elif plaza is None and lugar:\n            avisos.append(f"la plaza «{lugar}» no existe en Centauro")\n        for campo, etiqueta in (("marca_modelo", "marca y modelo"),\n                                ("color", "color"), ("modelo_anio", "año")):\n            if datos[campo] and datos[campo] != vehiculo.get(campo):\n                valores[campo] = datos[campo]\n                que.append(etiqueta)\n\n        if vinculo:\n            plan["vinculos"].append({"vehiculo_id": vehiculo["id"],\n                                     "odoo_id": u["id"],\n                                     "placa": vehiculo.get("placa")})\n        if valores:\n            plan["cambios"].append({"vehiculo_id": vehiculo["id"],\n                                    "odoo_id": u["id"],\n                                    "placa": vehiculo.get("placa"),\n                                    "valores": valores, "que": que})\n        elif not vinculo:\n            plan["sin_cambio"] += 1\n        if avisos:\n            pendiente(u, vehiculo["id"], avisos)\n        plan["procesadas"].append(vehiculo["id"])\n\n    ids = {u["id"] for u in elegidas}\n    plan["revisar_salida"] = [\n        v for v in vehiculos\n        if v.get("odoo_id") and v.get("activo") and v.get("sincronizado_en")\n        and v["odoo_id"] not in ids]\n    return plan\n\n\ndef clasificar_salidas(revisar: list, estados: dict, etiquetas: dict) -> tuple:\n    """(bajas, pendientes). `estados`: lo que dice Odoo de cada una, leido\n    con las archivadas incluidas."""\n    bajas, pendientes = [], []\n    for v in revisar:\n        u = estados.get(v["odoo_id"])\n        if u is not None and u.get("active", True) is not False:\n            pendientes.append({"odoo_id": v["odoo_id"], "vehiculo_id": v["id"],\n                               "placa": v.get("placa"),\n                               "falta": ["ya no es de Proteccion Ejecutiva "\n                                         "en Odoo" if not es_de_proteccion(u, etiquetas)\n                                         else "revisar en Odoo"]})\n        else:\n            bajas.append({"odoo_id": v["odoo_id"], "vehiculo_id": v["id"],\n                          "placa": v.get("placa"),\n                          "motivo": ("archivada en Odoo" if u is not None\n                                     else "ya no esta en Odoo")})\n    return bajas, pendientes\n\n\n# ------------------------------------------------------------ el taller\n\ndef planear_taller(registros: list, vehiculo_por_odoo: dict,\n                   existentes: dict) -> dict:\n    """Que hacer con cada entrada al taller de Odoo, sin hacerlo.\n\n    `registros`: fleet.vehicle.log.services, con las fechas de entrada y\n    salida ya leidas como `entrada` y `salida`. `vehiculo_por_odoo`: id de\n    la unidad en Odoo -> id en Centauro. `existentes`: lo que Centauro ya\n    guardo de Odoo, por odoo_id, con vehiculo_id, desde, hasta, tipo,\n    taller y nota.\n    """\n    plan = {"crear": [], "cambiar": [], "borrar": [], "pendientes": [],\n            "sin_cambio": 0, "de_otras_unidades": 0}\n    vistos = set()\n    for r in registros:\n        tipo = TALLER.get(normal(nombre_de(r.get("service_type_id"))))\n        if tipo is None or r.get("state") == "cancelled":\n            continue                    # no es taller: si estaba, se borra\n        vehiculo_id = vehiculo_por_odoo.get(id_de(r.get("vehicle_id")))\n        if vehiculo_id is None:\n            plan["de_otras_unidades"] += 1\n            continue\n        vistos.add(r["id"])\n        desde, hasta = fecha(r.get("entrada")), fecha(r.get("salida"))\n        faltas = []\n        if desde is None:\n            faltas.append("sin fecha de entrada")\n        elif hasta is not None and hasta < desde:\n            faltas.append("la salida es antes que la entrada")\n        elif hasta is None and r.get("state") == "done":\n            # Terminado y sin salida: ya no esta en el taller, pero no se\n            # sabe desde cuando. Se toma el dia de entrada y se avisa.\n            hasta = desde\n            faltas.append("terminado sin fecha de salida: se tomo el dia "\n                          "de entrada")\n        if faltas:\n            plan["pendientes"].append({"odoo_id": r["id"],\n                                       "vehiculo_id": vehiculo_id,\n                                       "falta": faltas})\n            if desde is None or (hasta is not None and hasta < desde):\n                continue\n        valores = {"vehiculo_id": vehiculo_id, "desde": desde, "hasta": hasta,\n                   "tipo": tipo,\n                   "taller": nombre_de(r.get("vendor_id"))[:160] or None,\n                   "nota": texto(r.get("description"))[:300] or None}\n        antes = existentes.get(r["id"])\n        if antes is None:\n            plan["crear"].append({"odoo_id": r["id"], **valores})\n        elif any(antes.get(k) != v for k, v in valores.items()):\n            plan["cambiar"].append({"odoo_id": r["id"], "id": antes["id"],\n                                    **valores})\n        else:\n            plan["sin_cambio"] += 1\n    plan["borrar"] = [e["id"] for odoo_id, e in existentes.items()\n                      if odoo_id not in vistos]\n    return plan\n',
    'app/odoo_flota.py': '# -*- coding: utf-8 -*-\n"""La flota y el taller de Proteccion Ejecutiva, leidos de Odoo.\n\nDecision de Salvador, 23 de septiembre: etapa 2 de la conexion con Odoo.\nOdoo es donde vive la flota; Centauro deja de capturar unidades y las\nlee de ahi, igual que el personal.\n\n  * Entran las unidades con la etiqueta «PROTECCION EJECUTIVA» o «pe».\n  * La llave es el numero interno de Odoo; la primera vez se vincula por\n    placa con la unidad que ya estaba.\n  * Placa, categoria, plaza (la Ubicacion), marca y modelo, color y año\n    vienen de Odoo y manda Odoo: en el catalogo ya no se editan. Un campo\n    vacio en Odoo no borra el de Centauro. Lo de la operacion --si va a\n    un implantado o se queda para eventuales, su costo diario-- sigue\n    siendo de Centauro. Los autos rentados no se tocan.\n  * La foto no viene de Odoo: cada categoria tiene su foto representativa\n    en Centauro (decision de Salvador, 23 sep).\n  * Baja: si Odoo la archiva, deja de ofrecerse y la central recibe una\n    alerta en cada dia que la unidad tenia asignado; su consultor, un\n    aviso.\n  * El taller: las entradas de Flotilla -> Servicios de tipo Preventivo,\n    Correctivo o Desgaste natural la sacan de circulacion de la fecha de\n    entrada a la de salida; sin salida, se da por adentro. Lo que Odoo\n    cancela o borra deja de bloquear. Lo que se capturo a mano en\n    Centauro no se toca.\n  * Nunca escribe en Odoo. Ensayo primero; la tarea de cada hora espera\n    a que alguien haga la primera lectura a mano.\n\nLas reglas viven en odoo_flota_reglas.py, sin base de datos.\n"""\nimport json\nimport logging\nfrom datetime import datetime, timezone\n\nfrom sqlalchemy.orm import Session\n\nfrom app import accesos\nfrom app import models as m\nfrom app import odoo_flota_reglas as reglas\nfrom app import reloj\n\nregistro = logging.getLogger("centauro.odoo")\n\nTIPO = "flota"\nCAMPOS = ["license_plate", "category_id", "location", "model_id", "color",\n          "model_year", "tag_ids", "write_date"]\n# Las fechas del taller son campos que la empresa agrego en Odoo Studio.\nENTRADA = "x_studio_fecha_de_entrada"\nSALIDA = "x_studio_fecha_de_salida"\nCAMPOS_TALLER = ["vehicle_id", "service_type_id", "state", "description",\n                 "vendor_id"]\nACABADAS = (m.EstatusJornada.TERMINADA, m.EstatusJornada.CANCELADA)\n\n\ndef _utc() -> datetime:\n    return datetime.now(timezone.utc).replace(tzinfo=None)\n\n\ndef _fotos_fijas(db: Session) -> tuple:\n    categorias = {c.codigo: {"id": c.id, "codigo": c.codigo, "nombre": c.nombre}\n                  for c in db.query(m.CategoriaVehiculo)\n                  .filter(m.CategoriaVehiculo.activo.is_(True)).all()}\n    plazas = {reglas.normal(p.nombre): {"id": p.id, "nombre": p.nombre}\n              for p in db.query(m.Plaza).filter(m.Plaza.activo.is_(True)).all()}\n    vehiculos = [{\n        "id": v.id, "odoo_id": v.odoo_id, "placa": v.placa,\n        "categoria_id": v.categoria_id, "plaza_id": v.plaza_id,\n        "marca_modelo": v.marca_modelo, "color": v.color,\n        "modelo_anio": v.modelo_anio, "activo": v.activo,\n        "sincronizado_en": v.odoo_sincronizado_en,\n    } for v in db.query(m.Vehiculo).filter(m.Vehiculo.rentado.is_(False)).all()]\n    return categorias, plazas, vehiculos\n\n\ndef _del_taller(db: Session) -> dict:\n    """Lo que Centauro ya guardo del taller de Odoo, por su odoo_id."""\n    return {t.odoo_id: {"id": t.id, "vehiculo_id": t.vehiculo_id,\n                        "desde": t.desde, "hasta": t.hasta,\n                        "tipo": t.tipo.value if t.tipo else None,\n                        "taller": t.taller, "nota": t.nota}\n            for t in db.query(m.TallerVehiculo)\n            .filter(m.TallerVehiculo.odoo_id.isnot(None)).all()}\n\n\ndef dias_por_delante(db: Session, vehiculo_id: int,\n                     relojes: reloj.Relojes | None = None) -> list:\n    """Las asignaciones de esa unidad de hoy en adelante, con el hoy del\n    pais de cada servicio. El dia de hoy cuenta aunque ya este en curso."""\n    relojes = relojes or reloj.Relojes(db)\n    filas = (db.query(m.AsignacionVehiculo)\n             .join(m.Jornada, m.AsignacionVehiculo.jornada_id == m.Jornada.id)\n             .filter(m.AsignacionVehiculo.vehiculo_id == vehiculo_id,\n                     m.AsignacionVehiculo.relevado_en.is_(None),\n                     m.Jornada.estatus.notin_(ACABADAS))\n             .order_by(m.Jornada.fecha).all())\n    salida = []\n    for a in filas:\n        servicio = a.jornada.equipo.servicio if a.jornada.equipo else None\n        if servicio and a.jornada.fecha >= relojes.hoy(servicio.pais_id):\n            salida.append(a)\n    return salida\n\n\ndef _dar_de_baja(db: Session, baja: dict, ahora: datetime,\n                 relojes: reloj.Relojes) -> None:\n    from app import push\n\n    vehiculo = db.get(m.Vehiculo, baja["vehiculo_id"])\n    vehiculo.activo = False\n    vehiculo.baja_odoo_en = ahora\n    avisados = set()\n    for asignacion in dias_por_delante(db, vehiculo.id, relojes):\n        db.add(m.Alerta(\n            jornada_id=asignacion.jornada_id, tipo=m.TipoAlerta.UNIDAD_DE_BAJA,\n            mensaje=(f"La unidad {vehiculo.placa} fue dada de baja en Odoo y "\n                     "esta asignada a este dia: hay que cambiarla.")[:400]))\n        servicio = asignacion.jornada.equipo.servicio\n        if servicio.consultor_id and servicio.id not in avisados:\n            avisados.add(servicio.id)\n            try:\n                push.avisar(\n                    db, servicio.consultor_id,\n                    titulo=f"{servicio.folio}: la unidad {vehiculo.placa} "\n                           "ya no esta en la flota",\n                    cuerpo=(f"Estaba asignada el "\n                            f"{asignacion.jornada.fecha:%d/%m}. Hay que "\n                            "cambiarla."),\n                    url=f"/consola/#/servicio/{servicio.id}",\n                    etiqueta=f"baja-unidad-{vehiculo.id}-{servicio.id}")\n            except Exception:                         # noqa: BLE001\n                registro.exception("no se pudo avisar la baja de %s",\n                                   vehiculo.placa)\n\n\ndef _leer_taller(odoo) -> tuple:\n    """(registros, error). Los registros traen sus fechas como `entrada`\n    y `salida`; si Odoo no tiene esos campos, no se lee el taller."""\n    campos = odoo.campos("fleet.vehicle.log.services")\n    if ENTRADA not in campos or SALIDA not in campos:\n        return [], ("Odoo no tiene los campos de fecha de entrada y salida "\n                    "del taller: no se leyo el taller.")\n    filas = odoo.leer("fleet.vehicle.log.services", [],\n                      CAMPOS_TALLER + [ENTRADA, SALIDA])\n    for f in filas:\n        f["entrada"], f["salida"] = f.get(ENTRADA), f.get(SALIDA)\n    return filas, None\n\n\ndef sincronizar(db: Session, odoo, ensayo: bool = True,\n                quien: m.Usuario | None = None,\n                automatica: bool = False) -> dict:\n    """Lee la flota y el taller de Odoo y, si no es ensayo, los guarda."""\n    ahora = _utc()\n    relojes = reloj.Relojes(db)\n    etiquetas = {t["id"]: t.get("name")\n                 for t in odoo.leer("fleet.vehicle.tag", [], ["name"])}\n    unidades = odoo.leer("fleet.vehicle", [], CAMPOS)\n    categorias, plazas, vehiculos = _fotos_fijas(db)\n    plan = reglas.planear(unidades, etiquetas, vehiculos, categorias, plazas)\n\n    estados = {}\n    if plan["revisar_salida"]:\n        estados = {f["id"]: f for f in odoo.leer(\n            "fleet.vehicle",\n            [["id", "in", [v["odoo_id"] for v in plan["revisar_salida"]]]],\n            ["active", "tag_ids"], archivados=True)}\n    bajas, pendientes_de_salida = reglas.clasificar_salidas(\n        plan["revisar_salida"], estados, etiquetas)\n    plan["pendientes"].extend(pendientes_de_salida)\n    for baja in bajas:\n        baja["dias_por_delante"] = len(\n            dias_por_delante(db, baja["vehiculo_id"], relojes))\n\n    registros, error_taller = _leer_taller(odoo)\n    existentes = _del_taller(db)\n\n    def plan_del_taller():\n        por_odoo = {v.odoo_id: v.id for v in db.query(m.Vehiculo).filter(\n            m.Vehiculo.odoo_id.isnot(None)).all()}\n        if ensayo:\n            # Lo que este plan vincula o da de alta todavia no tiene id en\n            # Centauro: para contar basta una marca.\n            por_odoo.update({x["odoo_id"]: x["vehiculo_id"]\n                             for x in plan["vinculos"]})\n            por_odoo.update({a["odoo_id"]: f"nueva-{a[\'odoo_id\']}"\n                             for a in plan["altas"]})\n        return reglas.planear_taller(registros, por_odoo, existentes)\n\n    def informe_con(taller):\n        return {\n            "ensayo": ensayo,\n            "leidas": plan["leidas"],\n            "altas": [{k: a[k] for k in ("odoo_id", "placa", "categoria", "plaza")}\n                      for a in plan["altas"]],\n            "vinculadas": plan["vinculos"],\n            "cambios": [{k: c[k] for k in ("vehiculo_id", "odoo_id", "placa", "que")}\n                        for c in plan["cambios"]],\n            "bajas": bajas,\n            "pendientes": plan["pendientes"],\n            "sin_cambio": plan["sin_cambio"],\n            "taller": {"nuevas": len(taller["crear"]),\n                       "cambios": len(taller["cambiar"]),\n                       "borradas": len(taller["borrar"]),\n                       "sin_cambio": taller["sin_cambio"],\n                       "de_otras_unidades": taller["de_otras_unidades"],\n                       "pendientes": taller["pendientes"],\n                       "error": error_taller},\n        }\n\n    if ensayo:\n        return informe_con(plan_del_taller())\n\n    # ------------------------------------------------------------ aplicar\n    for alta in plan["altas"]:\n        db.add(m.Vehiculo(\n            placa=alta["placa"], categoria_id=alta["categoria_id"],\n            plaza_id=alta["plaza_id"], marca_modelo=alta["marca_modelo"],\n            color=alta["color"], modelo_anio=alta["modelo_anio"],\n            odoo_id=alta["odoo_id"], odoo_sincronizado_en=ahora,\n            activo=True, rentado=False))\n    for vinculo in plan["vinculos"]:\n        db.get(m.Vehiculo, vinculo["vehiculo_id"]).odoo_id = vinculo["odoo_id"]\n    for cambio in plan["cambios"]:\n        vehiculo = db.get(m.Vehiculo, cambio["vehiculo_id"])\n        for campo, valor in cambio["valores"].items():\n            setattr(vehiculo, campo, valor)\n    for vehiculo_id in plan["procesadas"]:\n        vehiculo = db.get(m.Vehiculo, vehiculo_id)\n        vehiculo.odoo_sincronizado_en = ahora\n        vehiculo.baja_odoo_en = None\n    db.flush()\n\n    for baja in bajas:\n        _dar_de_baja(db, baja, ahora, relojes)\n\n    taller = plan_del_taller()\n    for nueva in taller["crear"]:\n        db.add(m.TallerVehiculo(\n            vehiculo_id=nueva["vehiculo_id"], desde=nueva["desde"],\n            hasta=nueva["hasta"], tipo=m.MotivoCambio(nueva["tipo"]),\n            taller=nueva["taller"], nota=nueva["nota"],\n            odoo_id=nueva["odoo_id"]))\n    for cambio in taller["cambiar"]:\n        fila = db.get(m.TallerVehiculo, cambio["id"])\n        fila.vehiculo_id, fila.desde, fila.hasta = (\n            cambio["vehiculo_id"], cambio["desde"], cambio["hasta"])\n        fila.tipo = m.MotivoCambio(cambio["tipo"])\n        fila.taller, fila.nota = cambio["taller"], cambio["nota"]\n    for fila_id in taller["borrar"]:\n        db.delete(db.get(m.TallerVehiculo, fila_id))\n\n    informe = informe_con(taller)\n    hubo_algo = (plan["altas"] or plan["vinculos"] or plan["cambios"] or bajas\n                 or taller["crear"] or taller["cambiar"] or taller["borrar"])\n    fila = m.SincronizacionOdoo(\n        tipo=TIPO, automatica=automatica,\n        hecha_por_id=quien.persona_id if quien else None,\n        leidos=plan["leidas"], altas=len(plan["altas"]),\n        cambios=len(plan["cambios"]) + len(plan["vinculos"]),\n        bajas=len(bajas), pendientes=len(plan["pendientes"]),\n        detalle=(json.dumps(informe, ensure_ascii=False, default=str)\n                 if hubo_algo or not automatica else None))\n    db.add(fila)\n    db.flush()\n    if quien is not None:\n        accesos.anotar(\n            db, quien, "flota leida de odoo", "sincronizacion_odoo", fila.id,\n            despues=(f"{len(plan[\'altas\'])} altas, "\n                     f"{len(plan[\'cambios\']) + len(plan[\'vinculos\'])} cambios, "\n                     f"{len(bajas)} bajas, {len(taller[\'crear\'])} al taller"))\n    db.commit()\n    return informe\n\n\ndef resumen(informe: dict) -> dict:\n    """Solo cuentas: para la terminal y para la tarea de cada hora."""\n    faltas = {}\n    for p in informe["pendientes"] + informe["taller"]["pendientes"]:\n        for falta in p["falta"]:\n            if falta.startswith("la plaza"):\n                falta = "plaza que no existe en Centauro"\n            elif falta.startswith("la categoria"):\n                falta = "categoria que no existe en Centauro"\n            elif falta.startswith("terminado sin fecha"):\n                falta = "taller terminado sin fecha de salida"\n            faltas[falta] = faltas.get(falta, 0) + 1\n    t = informe["taller"]\n    return {"leidas": informe["leidas"], "altas": len(informe["altas"]),\n            "vinculadas": len(informe["vinculadas"]),\n            "cambios": len(informe["cambios"]), "bajas": len(informe["bajas"]),\n            "sin_cambio": informe["sin_cambio"], "pendientes": faltas,\n            "taller": {k: t[k] for k in ("nuevas", "cambios", "borradas",\n                                         "sin_cambio", "de_otras_unidades",\n                                         "error")}}\n\n\ndef sincronizar_si_toca(db: Session, odoo=None) -> dict:\n    """La tarea de cada hora. No arranca sola: espera a que alguien haya\n    hecho la primera lectura a mano, despues de ver el ensayo."""\n    from app import odoo_api\n\n    primera = (db.query(m.SincronizacionOdoo)\n               .filter_by(tipo=TIPO, automatica=False).first())\n    if primera is None:\n        return {"omitido": "falta la primera lectura a mano"}\n    if odoo is None:\n        if not odoo_api.hay_conexion():\n            return {"omitido": "Odoo no esta conectado"}\n        odoo = odoo_api.cliente()\n    try:\n        return resumen(sincronizar(db, odoo, ensayo=False, automatica=True))\n    except odoo_api.NoResponde as error:\n        db.rollback()\n        registro.warning("odoo no respondio al leer la flota: %s", error)\n        return {"error": str(error)}\n',
    'migrations/versions/c3e9a5d1f7b2_flota_desde_odoo.py': '"""La flota y el taller, leidos de Odoo.\n\nEtapa 2 de la conexion con Odoo (seccion 52 de la bitacora): la unidad\nguarda con que numero vive en Odoo, cuando se leyo y cuando Odoo la dio de\nbaja; las fotos representativas de cada categoria, una por color; un tipo\nde alerta nuevo para la central; y la categoria Sedan, que Odoo ya tenia y\nCentauro no.\n\nRevision ID: c3e9a5d1f7b2\nRevises: b7d2f4a9c1e3\n"""\nfrom typing import Sequence, Union\n\nimport sqlalchemy as sa\nfrom alembic import op\n\nrevision: str = "c3e9a5d1f7b2"\ndown_revision: Union[str, None] = "b7d2f4a9c1e3"\nbranch_labels: Union[str, Sequence[str], None] = None\ndepends_on: Union[str, Sequence[str], None] = None\n\n\ndef upgrade() -> None:\n    op.add_column("vehiculo", sa.Column("odoo_id", sa.Integer(), nullable=True))\n    op.create_unique_constraint("vehiculo_odoo_id_key", "vehiculo", ["odoo_id"])\n    op.add_column("vehiculo", sa.Column("odoo_sincronizado_en", sa.DateTime(),\n                                        nullable=True))\n    op.add_column("vehiculo", sa.Column("baja_odoo_en", sa.DateTime(),\n                                        nullable=True))\n    op.create_table(\n        "foto_categoria",\n        sa.Column("id", sa.Integer(), primary_key=True),\n        sa.Column("categoria_id", sa.Integer(),\n                  sa.ForeignKey("categoria_vehiculo.id", ondelete="CASCADE"),\n                  nullable=False),\n        sa.Column("color", sa.String(length=40), server_default="",\n                  nullable=False),\n        sa.Column("foto_url", sa.Text(), nullable=False),\n        sa.Column("cargada_en", sa.DateTime(timezone=True),\n                  server_default=sa.text("now()"), nullable=False),\n        sa.UniqueConstraint("categoria_id", "color"),\n    )\n    op.create_index("ix_foto_categoria_categoria_id", "foto_categoria",\n                    ["categoria_id"])\n    op.execute("ALTER TYPE tipoalerta ADD VALUE IF NOT EXISTS "\n               "\'UNIDAD_DE_BAJA\' AFTER \'PERSONAL_DE_BAJA\'")\n    # El Sedan ya estaba en Odoo y faltaba aqui. Solo la categoria: sus\n    # tarifas se cargan con el tarifario real.\n    op.execute("INSERT INTO categoria_vehiculo "\n               "(codigo, nombre, blindado, rendimiento_km_litro, activo) "\n               "SELECT \'sedan\', \'Sedán\', false, 15.0, true "\n               "WHERE NOT EXISTS (SELECT 1 FROM categoria_vehiculo "\n               "WHERE codigo = \'sedan\')")\n\n\ndef downgrade() -> None:\n    op.execute("DELETE FROM alerta WHERE tipo = \'UNIDAD_DE_BAJA\'")\n    op.drop_index("ix_foto_categoria_categoria_id", table_name="foto_categoria")\n    op.drop_table("foto_categoria")\n    op.drop_column("vehiculo", "baja_odoo_en")\n    op.drop_column("vehiculo", "odoo_sincronizado_en")\n    op.drop_constraint("vehiculo_odoo_id_key", "vehiculo", type_="unique")\n    op.drop_column("vehiculo", "odoo_id")\n    # La categoria Sedan se queda: puede tener unidades y tarifas.\n',
    'tests/test_odoo_flota_lectura.py': '# -*- coding: utf-8 -*-\n"""La flota y el taller, leidos de Odoo (seccion 52 de la bitacora).\n\nContra un Odoo de mentiras, en memoria: ninguna prueba sale a la red. La\nflota se vacia y se vuelve a sembrar antes de cada prueba (conftest), asi\nque las unidades que estas pruebas dan de alta no se quedan.\n"""\nfrom datetime import date, timedelta\n\nimport pytest\nfrom sqlalchemy import text\n\nfrom ayudas import PIXEL, asignar, crear_servicio, jornada, manana\nfrom app import models as m\nfrom app import odoo_api, odoo_flota\n\nODOO0 = 8_000_000\nETIQUETAS = {1: "pe", 2: "Logística", 3: "PROTECCIÓN EJECUTIVA"}\n\n\ndef unidad(n, **cambios):\n    u = {"id": ODOO0 + n, "license_plate": f"T{n:02d}ODO",\n         "category_id": [9, "MINIVAN"], "location": "Ciudad de México",\n         "model_id": [4, "Toyota/SIENNA XSE"], "color": "Blanco",\n         "model_year": "2023", "tag_ids": [1],\n         "write_date": "2026-01-01 10:00:00", "active": True}\n    u.update(cambios)\n    return u\n\n\ndef taller(n, dueno, **cambios):\n    r = {"id": 9_000_000 + n, "vehicle_id": [ODOO0 + dueno, "x"],\n         "service_type_id": [3, "Correctivo"], "state": "running",\n         odoo_flota.ENTRADA: str(manana(2)), odoo_flota.SALIDA: str(manana(5)),\n         "vendor_id": [7, "Taller Norte"], "description": "Frenos"}\n    r.update(cambios)\n    return r\n\n\nclass OdooFalso:\n    def __init__(self, *unidades, taller=(), con_fechas=True):\n        self.unidades = {u["id"]: u for u in unidades}\n        self.taller = {r["id"]: r for r in taller}\n        self.con_fechas = con_fechas\n\n    def campos(self, modelo):\n        assert modelo == "fleet.vehicle.log.services"\n        campos = {c: {"type": "char"} for c in odoo_flota.CAMPOS_TALLER}\n        if self.con_fechas:\n            campos[odoo_flota.ENTRADA] = campos[odoo_flota.SALIDA] = {"type": "date"}\n        return campos\n\n    def leer(self, modelo, dominio, campos, archivados=False):\n        if modelo == "fleet.vehicle.tag":\n            return [{"id": i, "name": n} for i, n in ETIQUETAS.items()]\n        if modelo == "fleet.vehicle.log.services":\n            filas = list(self.taller.values())\n        else:\n            assert modelo == "fleet.vehicle"\n            filas = [u for u in self.unidades.values()\n                     if archivados or u.get("active", True)]\n        for campo, operador, valor in dominio:\n            assert (campo, operador) == ("id", "in")\n            filas = [f for f in filas if f["id"] in valor]\n        return [{"id": f["id"], **{c: f.get(c, False) for c in campos}}\n                for f in filas]\n\n\nclass OdooCaido:\n    def leer(self, *args, **kwargs):\n        raise odoo_api.NoResponde("Odoo rechazo la llave; puede que haya vencido.")\n\n\n@pytest.fixture\ndef db():\n    from app.db import SessionLocal\n\n    sesion = SessionLocal()\n    yield sesion\n    sesion.close()\n\n\n@pytest.fixture(autouse=True)\ndef sin_fotos(base_de_pruebas):\n    """La categoria es catalogo y no se vacia entre pruebas: la foto que\n    sube una prueba no se queda para la siguiente."""\n    yield\n    with base_de_pruebas.begin() as con:\n        con.execute(text("DELETE FROM foto_categoria"))\n\n\ndef leer(db, odoo, ensayo=False, **kwargs):\n    # Como en produccion, donde cada lectura abre su propia sesion.\n    db.expire_all()\n    return odoo_flota.sincronizar(db, odoo, ensayo=ensayo, **kwargs)\n\n\ndef vehiculo(db, n):\n    db.expire_all()\n    return db.query(m.Vehiculo).filter_by(odoo_id=ODOO0 + n).one()\n\n\ndef de_odoo(db):\n    db.expire_all()\n    return db.query(m.Vehiculo).filter(m.Vehiculo.odoo_id >= ODOO0).count()\n\n\ndef dia_de_servicio(cliente, sesion, datos, dias=3):\n    """Un dia de un servicio de Ana en la Ciudad de Mexico."""\n    servicio = crear_servicio(\n        cliente, sesion("consultor"), datos,\n        [jornada(manana(dias), datos["modalidades"]["full_day"]["id"])],\n        consultor_id=datos["personal"]["Ana Solis"]["id"])\n    return servicio["equipos"][0]["jornadas"][0]\n\n\n# ================================================================ unidades\n\ndef test_el_ensayo_dice_que_haria_y_no_guarda_nada(db):\n    informe = leer(db, OdooFalso(unidad(1), unidad(2), taller=[taller(1, 1)]),\n                   ensayo=True)\n    assert informe["ensayo"] is True and len(informe["altas"]) == 2\n    # El taller de una unidad que llega nueva tambien se cuenta.\n    assert informe["taller"]["nuevas"] == 1\n    assert de_odoo(db) == 0\n    assert db.query(m.TallerVehiculo).count() == 0\n    assert db.query(m.SincronizacionOdoo).count() == 0\n\n\ndef test_entran_las_de_proteccion_ejecutiva_con_su_categoria_y_plaza(\n        db, datos):\n    informe = leer(db, OdooFalso(\n        unidad(1),\n        unidad(2, tag_ids=[2, 3], category_id=[9, "VAN"],\n               location="Estado de México"),\n        unidad(3, category_id=[9, "SEDAN"], location="CDMX"),\n        unidad(4, category_id=[9, "MINIVAN BLINDADA"], location="Guadalajara"),\n        unidad(5, tag_ids=[2]),\n        unidad(6, tag_ids=[])))\n    assert informe["leidas"] == 4\n    assert sorted(a["odoo_id"] - ODOO0 for a in informe["altas"]) == [1, 2, 3, 4]\n    cat = datos["categorias"]\n    assert vehiculo(db, 2).categoria_id == cat["van_10"]["id"]\n    assert vehiculo(db, 3).categoria_id == cat["sedan"]["id"]\n    assert vehiculo(db, 4).categoria_id == cat["minivan_blindada"]["id"]\n    assert vehiculo(db, 2).plaza_id == datos["cdmx"]["id"]\n    assert vehiculo(db, 3).plaza_id == datos["cdmx"]["id"]\n    assert vehiculo(db, 4).plaza_id == datos["gdl"]["id"]\n    v = vehiculo(db, 1)\n    assert (v.placa, v.marca_modelo, v.color, v.modelo_anio) == (\n        "T01ODO", "Toyota SIENNA XSE", "Blanco", 2023)\n    assert v.activo and not v.rentado and v.odoo_sincronizado_en is not None\n\n\ndef test_lo_dudoso_queda_pendiente_y_no_se_toca(db):\n    informe = leer(db, OdooFalso(\n        unidad(1, category_id=False),\n        unidad(2, category_id=[9, "MINIBUS"]),\n        unidad(3, location=False),\n        unidad(4, location="Tijuana"),\n        unidad(5, license_plate="R99ODO"),\n        unidad(6, license_plate="R99ODO")))\n    assert not informe["altas"]\n    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}\n    assert faltas == {\n        1: ["sin categoria"],\n        2: ["la categoria «MINIBUS» no existe en Centauro"],\n        3: ["sin plaza"],\n        4: ["la plaza «Tijuana» no existe en Centauro"],\n        5: ["placa repetida en Odoo"],\n        6: ["placa repetida en Odoo"],\n    }\n    assert de_odoo(db) == 0\n\n\ndef test_la_unidad_que_ya_estaba_se_vincula_por_su_placa(db, datos):\n    suburban = datos["suburban"]\n    informe = leer(db, OdooFalso(unidad(\n        1, license_plate=suburban["placa"].replace("-", ""),\n        category_id=[9, "SUV BLINDADA"], model_id=[2, "Chevrolet/SUBURBAN"])))\n    assert not informe["altas"]\n    assert [x["vehiculo_id"] for x in informe["vinculadas"]] == [suburban["id"]]\n    v = vehiculo(db, 1)\n    assert v.id == suburban["id"] and v.marca_modelo == "Chevrolet SUBURBAN"\n    # La misma placa escrita distinto no es un cambio.\n    assert v.placa == suburban["placa"]\n\n\ndef test_lo_que_cambia_en_odoo_cambia_aqui_y_lo_vacio_no_borra(db, datos):\n    odoo = OdooFalso(unidad(1))\n    leer(db, odoo)\n    odoo.unidades[ODOO0 + 1].update(color="Gris", location="Guadalajara",\n                                    category_id=[9, "CUV"])\n    informe = leer(db, odoo)\n    assert informe["cambios"][0]["que"] == ["categoria", "plaza", "color"]\n    v = vehiculo(db, 1)\n    assert (v.color, v.plaza_id, v.categoria_id) == (\n        "Gris", datos["gdl"]["id"], datos["categorias"]["cuv"]["id"])\n    odoo.unidades[ODOO0 + 1].update(color=False, model_id=False)\n    assert not leer(db, odoo)["cambios"]\n    v = vehiculo(db, 1)\n    assert (v.color, v.marca_modelo) == ("Gris", "Toyota SIENNA XSE")\n\n\ndef test_la_baja_en_odoo_avisa_en_cada_dia_que_tenia(cliente, sesion, datos, db):\n    odoo = OdooFalso(unidad(1), unidad(2))\n    leer(db, odoo)\n    j = dia_de_servicio(cliente, sesion, datos)\n    r = asignar(cliente, sesion("consultor"), j["id"],\n                vehiculo_id=vehiculo(db, 1).id)[0]\n    assert r.status_code == 200, r.text\n\n    odoo.unidades[ODOO0 + 1]["active"] = False\n    informe = leer(db, odoo)\n    assert [(b["odoo_id"] - ODOO0, b["motivo"], b["dias_por_delante"])\n            for b in informe["bajas"]] == [(1, "archivada en Odoo", 1)]\n    v = vehiculo(db, 1)\n    assert not v.activo and v.baja_odoo_en is not None\n    alerta = (db.query(m.Alerta)\n              .filter_by(jornada_id=j["id"],\n                         tipo=m.TipoAlerta.UNIDAD_DE_BAJA).one())\n    assert v.placa in alerta.mensaje\n    assert vehiculo(db, 2).activo\n\n\ndef test_la_que_deja_de_ser_de_proteccion_queda_pendiente_sin_baja(db):\n    odoo = OdooFalso(unidad(1))\n    leer(db, odoo)\n    odoo.unidades[ODOO0 + 1]["tag_ids"] = [2]\n    informe = leer(db, odoo)\n    assert not informe["bajas"]\n    assert informe["pendientes"][0]["falta"] == [\n        "ya no es de Proteccion Ejecutiva en Odoo"]\n    assert vehiculo(db, 1).activo\n\n\n# ================================================================ taller\n\ndef test_el_taller_de_odoo_saca_a_la_unidad_de_circulacion(\n        cliente, sesion, datos, db):\n    odoo = OdooFalso(unidad(1), taller=[taller(1, 1)])\n    informe = leer(db, odoo)\n    assert informe["taller"]["nuevas"] == 1\n    fila = db.query(m.TallerVehiculo).filter_by(odoo_id=9_000_001).one()\n    assert (fila.desde, fila.hasta, fila.tipo, fila.taller) == (\n        manana(2), manana(5), m.MotivoCambio.MANTENIMIENTO_CORRECTIVO,\n        "Taller Norte")\n\n    # Al asignar un eventual ya no se ofrece como libre, y no se puede.\n    j = dia_de_servicio(cliente, sesion, datos, dias=3)\n    v = vehiculo(db, 1)\n    h = sesion("consultor")\n    servicio = cliente.get(f"/servicios/jornadas/{j[\'id\']}/asignaciones",\n                           headers=h)\n    assert servicio.status_code == 200, servicio.text\n    equipo_id = db.get(m.Jornada, j["id"]).equipo_id\n    r = cliente.get(f"/servicios/equipos/{equipo_id}/recomendaciones"\n                    f"?categoria_id={v.categoria_id}", headers=h).json()\n    ficha = next(f for f in r["vehiculos"]["no_disponibles"]\n                 if f["vehiculo_id"] == v.id)\n    assert any("taller" in a["mensaje"] for a in ficha["alertas"])\n    r = asignar(cliente, h, j["id"], vehiculo_id=v.id)[0]\n    assert r.status_code == 409, r.text\n\n    # Un dia despues de la salida ya se puede.\n    despues = dia_de_servicio(cliente, sesion, datos, dias=6)\n    assert asignar(cliente, h, despues["id"],\n                   vehiculo_id=v.id)[0].status_code == 200\n\n\ndef test_sin_salida_se_da_por_adentro_y_lo_cancelado_deja_de_bloquear(db):\n    odoo = OdooFalso(unidad(1), taller=[taller(1, 1, **{odoo_flota.SALIDA: False})])\n    leer(db, odoo)\n    fila = db.query(m.TallerVehiculo).filter_by(odoo_id=9_000_001).one()\n    assert fila.hasta is None and fila.cubre(date.today() + timedelta(days=400))\n\n    # Lo que se capturo a mano en Centauro no se toca.\n    a_mano = m.TallerVehiculo(vehiculo_id=vehiculo(db, 1).id, desde=manana(30),\n                              tipo=m.MotivoCambio.MANTENIMIENTO_PREVENTIVO)\n    db.add(a_mano)\n    db.commit()\n\n    odoo.taller[9_000_001]["state"] = "cancelled"\n    assert leer(db, odoo)["taller"]["borradas"] == 1\n    db.expire_all()\n    assert db.query(m.TallerVehiculo).filter_by(odoo_id=9_000_001).count() == 0\n    assert db.query(m.TallerVehiculo).filter_by(id=a_mano.id).count() == 1\n\n\ndef test_lo_que_no_es_taller_no_saca_de_circulacion(db):\n    informe = leer(db, OdooFalso(\n        unidad(1), unidad(2, tag_ids=[2]),\n        taller=[taller(1, 1, service_type_id=[8, "Resguardo de Unidad"]),\n                taller(2, 2),\n                taller(3, 1, **{odoo_flota.ENTRADA: False}),\n                taller(4, 1, state="done", **{odoo_flota.SALIDA: False})]))\n    t = informe["taller"]\n    assert (t["nuevas"], t["de_otras_unidades"]) == (1, 1)\n    faltas = {p["odoo_id"]: p["falta"] for p in t["pendientes"]}\n    assert faltas[9_000_003] == ["sin fecha de entrada"]\n    assert faltas[9_000_004][0].startswith("terminado sin fecha de salida")\n    # El terminado sin salida no bloquea mas alla del dia que entro.\n    fila = db.query(m.TallerVehiculo).filter_by(odoo_id=9_000_004).one()\n    assert fila.hasta == fila.desde\n\n\ndef test_sin_los_campos_de_fecha_no_se_lee_el_taller(db):\n    informe = leer(db, OdooFalso(unidad(1), taller=[taller(1, 1)],\n                                 con_fechas=False))\n    assert "no tiene los campos" in informe["taller"]["error"]\n    assert len(informe["altas"]) == 1 and db.query(m.TallerVehiculo).count() == 0\n\n\n# ================================================================ la foto\n\ndef test_la_foto_de_la_categoria_respeta_el_color_de_la_unidad(\n        cliente, sesion, datos):\n    """Una foto por categoria, y aparte una por color: la Suburban negra\n    se ve negra. El color que no tiene foto ensena la base."""\n    h = sesion("admin")\n    suv = datos["categorias"]["suv_blindada"]\n    ruta = f"/catalogos/categorias-vehiculo/{suv[\'id\']}/foto"\n    r = cliente.put(ruta, headers=h,\n                    files={"archivo": ("suv.png", PIXEL, "image/png")})\n    assert r.status_code == 200, r.text\n    # La negra se distingue de la base por el tipo de imagen.\n    r = cliente.put(ruta, headers=h, params={"color": "Negro metálico"},\n                    files={"archivo": ("suv_negra.webp", PIXEL, "image/webp")})\n    assert r.status_code == 200 and r.json()["color"] == "negro", r.text\n    cats = {c["id"]: c for c in cliente.get("/catalogos/categorias-vehiculo",\n                                            headers=h).json()}\n    assert cats[suv["id"]]["fotos"] == ["", "negro"]\n    assert "foto_url" not in cats[suv["id"]]      # la lista no carga fotos\n\n    negra = datos["suburban"]\n    otra = next(v for v in datos["vehiculos"]\n                if v["categoria_id"] == suv["id"] and v["id"] != negra["id"])\n    r = cliente.patch(f"/catalogos/vehiculos/{negra[\'id\']}", headers=h, json={\n        "placa": negra["placa"], "categoria_id": suv["id"],\n        "plaza_id": negra["plaza_id"], "color": "Negro"})\n    assert r.status_code == 200, r.text\n\n    j = dia_de_servicio(cliente, sesion, datos)\n    for unidad_id in (negra["id"], otra["id"]):\n        assert asignar(cliente, sesion("consultor"), j["id"],\n                       vehiculo_id=unidad_id)[0].status_code == 200\n    fotos = {u["vehiculo_id"]: u["foto"] for u in cliente.get(\n        f"/servicios/jornadas/{j[\'id\']}/asignaciones",\n        headers=sesion("consultor")).json()["vehiculos"]}\n    assert fotos[negra["id"]].startswith("data:image/webp;base64,")\n    assert fotos[otra["id"]].startswith("data:image/png;base64,")\n\n\ndef test_la_foto_la_sube_administracion_y_tiene_que_ser_imagen(\n        cliente, sesion, datos):\n    suv = datos["categorias"]["suv_blindada"]\n    ruta = f"/catalogos/categorias-vehiculo/{suv[\'id\']}/foto"\n    archivo = {"archivo": ("suv.png", PIXEL, "image/png")}\n    assert cliente.put(ruta, headers=sesion("consultor"),\n                       files=archivo).status_code == 403\n    r = cliente.put(ruta, headers=sesion("admin"),\n                    files={"archivo": ("nota.txt", b"hola", "text/plain")})\n    assert r.status_code == 400, r.text\n\n\n# ================================================================ la consola\n\ndef test_lo_que_viene_de_odoo_no_se_edita_en_la_flota(cliente, sesion, db):\n    leer(db, OdooFalso(unidad(1)))\n    v = vehiculo(db, 1)\n    h = sesion("admin")\n    cuerpo = {"placa": v.placa, "categoria_id": v.categoria_id,\n              "plaza_id": v.plaza_id}\n    r = cliente.patch(f"/catalogos/vehiculos/{v.id}", headers=h,\n                      json={**cuerpo, "placa": "OTRA123"})\n    assert r.status_code == 409, r.text\n    assert "Odoo" in r.json()["detail"]["mensaje"]\n    # Lo que es de Centauro si se edita.\n    r = cliente.patch(f"/catalogos/vehiculos/{v.id}", headers=h,\n                      json={**cuerpo, "costo_diario": "950"})\n    assert r.status_code == 200, r.text\n\n\ndef test_el_sedan_ya_es_categoria_de_centauro_con_tarifa(cliente, sesion,\n                                                         datos):\n    sedan = datos["categorias"]["sedan"]\n    assert sedan["blindado"] is False\n    tarifas = cliente.get("/catalogos/tarifas-vehiculo",\n                          headers=sesion("admin")).json()\n    assert any(t["categoria_id"] == sedan["id"] for t in tarifas)\n\n\ndef test_la_tarea_de_cada_hora_espera_la_primera_a_mano(db):\n    odoo = OdooFalso(unidad(1))\n    assert odoo_flota.sincronizar_si_toca(db, odoo) == {\n        "omitido": "falta la primera lectura a mano"}\n    leer(db, odoo, ensayo=True)\n    assert "omitido" in odoo_flota.sincronizar_si_toca(db, odoo)\n    leer(db, odoo)\n    odoo.unidades[ODOO0 + 2] = unidad(2)\n    r = odoo_flota.sincronizar_si_toca(db, odoo)\n    assert (r["leidas"], r["altas"]) == (2, 1)\n    assert "vencido" in odoo_flota.sincronizar_si_toca(db, OdooCaido())["error"]\n\n\ndef test_las_rutas_de_la_flota_son_de_administracion(cliente, sesion,\n                                                     monkeypatch, db):\n    from app.config import settings\n\n    monkeypatch.setattr(settings, "odoo_base", "")\n    monkeypatch.setattr(settings, "odoo_api_key", "")\n    assert cliente.get("/odoo/flota/ensayo",\n                       headers=sesion("consultor")).status_code == 403\n    assert cliente.get("/odoo/flota/ensayo",\n                       headers=sesion("admin")).status_code == 503\n\n    monkeypatch.setattr(odoo_api, "cliente", lambda: OdooFalso(unidad(1)))\n    r = cliente.get("/odoo/flota/ensayo", headers=sesion("admin"))\n    assert r.status_code == 200 and r.json()["ensayo"] is True\n    assert de_odoo(db) == 0\n    r = cliente.post("/odoo/flota/sincronizar", headers=sesion("admin"))\n    assert r.status_code == 200 and len(r.json()["altas"]) == 1\n    assert db.query(m.SincronizacionOdoo).filter_by(tipo="flota").count() == 1\n',
    'sincronizar_flota.py': '# -*- coding: utf-8 -*-\n"""Leer la flota y el taller de Odoo, desde la terminal.\n\nLo mismo que la consola hace con «ensayo» y «sincronizar». Desde la raiz\ndel proyecto:\n\n    docker compose run --rm api python sincronizar_flota.py\n    docker compose run --rm api python sincronizar_flota.py --aplicar\n\nSin --aplicar es un ensayo: lee Odoo, dice que haria y no guarda nada.\nNunca escribe en Odoo. El detalle queda en odoo_flota_ultimo.json junto\na este archivo; no va a git.\n"""\nimport json\nimport sys\nfrom pathlib import Path\n\nfrom app import odoo_api, odoo_flota\nfrom app.db import SessionLocal\n\nDETALLE = Path(__file__).resolve().with_name("odoo_flota_ultimo.json")\n\n\ndef main(argv: list) -> int:\n    aplicar = "--aplicar" in argv\n    try:\n        odoo = odoo_api.cliente()\n    except odoo_api.SinConexion:\n        print("Falta ODOO_BASE u ODOO_API_KEY en el .env.")\n        return 1\n\n    db = SessionLocal()\n    try:\n        informe = odoo_flota.sincronizar(db, odoo, ensayo=not aplicar)\n    except odoo_api.NoResponde as error:\n        print(f"Odoo no respondio: {error}")\n        return 2\n    finally:\n        db.close()\n\n    DETALLE.write_text(json.dumps(informe, ensure_ascii=False, indent=2,\n                                  default=str), encoding="utf-8")\n    r = odoo_flota.resumen(informe)\n    t = r["taller"]\n    print("Aplicado: quedo guardado en Centauro." if aplicar\n          else "ENSAYO: no se guardo nada.")\n    print(f"Unidades de Proteccion Ejecutiva en Odoo: {r[\'leidas\']}")\n    print(f"Altas: {r[\'altas\']} · vinculadas: {r[\'vinculadas\']} · "\n          f"con cambios: {r[\'cambios\']} · sin cambio: {r[\'sin_cambio\']}")\n    print(f"Bajas: {r[\'bajas\']}")\n    if t["error"]:\n        print(f"Taller: {t[\'error\']}")\n    else:\n        print(f"Taller: {t[\'nuevas\']} nuevas · {t[\'cambios\']} con cambios · "\n              f"{t[\'borradas\']} que ya no bloquean · {t[\'sin_cambio\']} sin "\n              f"cambio · {t[\'de_otras_unidades\']} de unidades que no son de "\n              "Proteccion Ejecutiva")\n    if r["pendientes"]:\n        print("Pendientes, por motivo:")\n        for motivo, cuantos in sorted(r["pendientes"].items(),\n                                      key=lambda x: -x[1]):\n            print(f"  {cuantos:>3}  {motivo}")\n    else:\n        print("Pendientes: ninguno")\n    print(f"El detalle quedo en {DETALLE.name} (no va a git).")\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main(sys.argv[1:]))\n',
    'fotos_de_categoria.py': '# -*- coding: utf-8 -*-\n"""Cargar las fotos representativas de las categorias de vehiculo.\n\nDecision de Salvador, 23 de septiembre: la unidad no lleva su foto real\nsino la de su categoria, respetando su color --la Sienna negra se ve\nnegra--. Cada categoria tiene una foto base y, aparte, una por color; la\nunidad ensena la de su color y, si no hay, la base.\n\nEn una carpeta, una foto por archivo, con este nombre:\n\n    minivan.jpg             la base de la categoria\n    minivan__negro.jpg      la misma en negro (dos guiones bajos)\n\nDe perfil, horizontal, unos 600 x 400, JPG de menos de 200 KB. Desde la\nraiz del proyecto:\n\n    docker compose run --rm \\\\\n      -v "$HOME/Desktop/centauro/Claude outputs/fotos_categorias:/fotos" \\\\\n      api python fotos_de_categoria.py /fotos\n\nUna foto que ya estaba se reemplaza. Al final dice que colores de la flota\ntodavia no tienen su foto y ensenan la base.\n"""\nimport base64\nimport collections\nimport sys\nfrom pathlib import Path\n\nfrom app import models as m\nfrom app.db import SessionLocal\nfrom app.odoo_flota_reglas import codigo_de_categoria, color_de\n\nTIPOS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",\n         ".webp": "image/webp"}\nLIMITE = 3 * 1024 * 1024      # el mismo de las demas imagenes del sistema\n\n\ndef main(argv: list) -> int:\n    if not argv:\n        print("Falta la carpeta con las fotos.")\n        return 1\n    carpeta = Path(argv[0])\n    if not carpeta.is_dir():\n        print(f"No encuentro la carpeta {carpeta}.")\n        return 1\n\n    db = SessionLocal()\n    try:\n        categorias = {c.codigo: c for c in db.query(m.CategoriaVehiculo).all()}\n        cargadas, sin_categoria, pesadas = [], [], []\n        for archivo in sorted(carpeta.iterdir()):\n            tipo = TIPOS.get(archivo.suffix.lower())\n            if not archivo.is_file() or tipo is None:\n                continue\n            nombre, _, color = archivo.stem.partition("__")\n            categoria = categorias.get(codigo_de_categoria(nombre))\n            if categoria is None:\n                sin_categoria.append(archivo.name)\n                continue\n            contenido = archivo.read_bytes()\n            if len(contenido) > LIMITE:\n                pesadas.append(archivo.name)\n                continue\n            color = color_de(color)\n            foto = (db.query(m.FotoCategoria)\n                    .filter_by(categoria_id=categoria.id, color=color).first())\n            if foto is None:\n                foto = m.FotoCategoria(categoria_id=categoria.id, color=color)\n                db.add(foto)\n            foto.foto_url = (f"data:{tipo};base64,"\n                             f"{base64.b64encode(contenido).decode()}")\n            cargadas.append(f"{categoria.nombre}"\n                            + (f" en {color}" if color else " (base)")\n                            + f", {len(contenido) // 1024} KB")\n        db.commit()\n\n        # Que colores de la flota todavia ensenan la base.\n        hay = {(f.categoria_id, f.color) for f in db.query(\n            m.FotoCategoria.categoria_id, m.FotoCategoria.color).all()}\n        faltan = collections.Counter()\n        for v in db.query(m.Vehiculo).filter(m.Vehiculo.activo.is_(True),\n                                             m.Vehiculo.rentado.is_(False)).all():\n            color = color_de(v.color)\n            if (v.categoria_id, color) not in hay:\n                faltan[(v.categoria.nombre, color or "sin color")] += 1\n        sin_base = sorted(c.nombre for c in categorias.values()\n                          if c.activo and (c.id, "") not in hay)\n    finally:\n        db.close()\n\n    print(f"Fotos cargadas: {len(cargadas)}")\n    for c in cargadas:\n        print(f"  {c}")\n    if sin_categoria:\n        print("Sin categoria con ese nombre: " + ", ".join(sin_categoria))\n    if pesadas:\n        print("Pasan de 3 MB, no se cargaron: " + ", ".join(pesadas))\n    print("Categorias sin foto base: " + (", ".join(sin_base) or "ninguna"))\n    if faltan:\n        print("Unidades cuyo color todavia no tiene foto (ensenan la base):")\n        for (categoria, color), n in sorted(faltan.items()):\n            print(f"  {n:>3}  {categoria} en {color}")\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main(sys.argv[1:]))\n',
}

textos = {k: io.open(v, encoding="utf-8").read() for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(viejo) == 1, f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces"
    textos[clave] = t.replace(viejo, nuevo)


# ================================================================ modelos
cambiar("models",
        "    rendimiento_km_litro: Mapped[float] = mapped_column(Numeric(5, 2))\n"
        "    activo: Mapped[bool] = mapped_column(Boolean, default=True)\n"
        "\n"
        "\n"
        "class Modalidad(Base):\n",
        "    rendimiento_km_litro: Mapped[float] = mapped_column(Numeric(5, 2))\n"
        "    activo: Mapped[bool] = mapped_column(Boolean, default=True)\n"
        "\n"
        "    # Sus fotos representativas, una por color (seccion 52).\n"
        "    variantes: Mapped[list[\"FotoCategoria\"]] = relationship(\n"
        "        back_populates=\"categoria\", cascade=\"all, delete-orphan\")\n"
        "\n"
        "    @property\n"
        "    def fotos(self) -> list[str]:\n"
        "        \"\"\"Los colores que tienen foto; \"\" es la base. La lista de\n"
        "        categorias dice esto y no carga las imagenes.\"\"\"\n"
        "        return sorted(f.color for f in self.variantes)\n"
        "\n"
        "\n"
        "class FotoCategoria(Base):\n"
        "    \"\"\"La foto representativa de una categoria, en un color.\n"
        "\n"
        "    Decision de Salvador (23 sep): la unidad no lleva su foto real sino\n"
        "    la de su categoria, pero respetando su color --la Suburban negra se\n"
        "    ve negra--. La base va sin color (\"\") y cada color aparte; la\n"
        "    unidad ensena la de su color y, si no hay, la base.\n"
        "    \"\"\"\n"
        "    __tablename__ = \"foto_categoria\"\n"
        "    __table_args__ = (UniqueConstraint(\"categoria_id\", \"color\"),)\n"
        "\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        "    categoria_id: Mapped[int] = mapped_column(\n"
        "        ForeignKey(\"categoria_vehiculo.id\", ondelete=\"CASCADE\"), index=True)\n"
        "    # Como lo deja color_de(): la primera palabra, sin acentos.\n"
        "    color: Mapped[str] = mapped_column(String(40), default=\"\",\n"
        "                                       server_default=\"\")\n"
        "    # Diferida: saber que colores hay no tiene por que traer las fotos.\n"
        "    foto_url: Mapped[str] = mapped_column(Text, deferred=True)\n"
        "    cargada_en: Mapped[datetime] = mapped_column(\n"
        "        DateTime(timezone=True), server_default=func.now())\n"
        "\n"
        "    categoria: Mapped[CategoriaVehiculo] = relationship(\n"
        "        back_populates=\"variantes\")\n"
        "\n"
        "\n"
        "class Modalidad(Base):\n",
        marca="class FotoCategoria(Base):")

cambiar("models",
        "    # La ve el ejecutivo en el task sheet, igual que la foto del personal.\n"
        "    # Viene de Odoo (modulo de flota), no se captura aqui.\n"
        "    foto_url: Mapped[str | None] = mapped_column(String(400), nullable=True)\n",
        "    # La que ve el ejecutivo es la de su categoria en su color (`foto`,\n"
        "    # abajo; seccion 52). Esta queda de respaldo: se ensena solo si la\n"
        "    # categoria todavia no tiene ninguna.\n"
        "    foto_url: Mapped[str | None] = mapped_column(String(400), nullable=True)\n"
        "    # Con que numero vive en Odoo (seccion 52), cuando se leyo por\n"
        "    # ultima vez y cuando Odoo la dio de baja. En UTC y sin zona.\n"
        "    odoo_id: Mapped[int | None] = mapped_column(Integer, nullable=True,\n"
        "                                                unique=True)\n"
        "    odoo_sincronizado_en: Mapped[datetime | None] = mapped_column(\n"
        "        DateTime, nullable=True)\n"
        "    baja_odoo_en: Mapped[datetime | None] = mapped_column(DateTime,\n"
        "                                                          nullable=True)\n",
        marca="    odoo_sincronizado_en: Mapped[datetime | None] = mapped_column(\n"
              "        DateTime, nullable=True)\n"
              "    baja_odoo_en: Mapped[datetime | None] = mapped_column(DateTime,\n"
              "                                                          nullable=True)\n"
              "\n"
              "    # ------------------------------------------------------- subarrendo")

cambiar("models",
        "    categoria: Mapped[CategoriaVehiculo] = relationship()\n"
        "    plaza: Mapped[Plaza] = relationship()\n",
        "    categoria: Mapped[CategoriaVehiculo] = relationship()\n"
        "    plaza: Mapped[Plaza] = relationship()\n"
        "\n"
        "    @property\n"
        "    def foto(self) -> str | None:\n"
        "        \"\"\"La que se ensena: la de su categoria en su color, o la base\n"
        "        de la categoria, o la propia. Decision de Salvador (23 sep):\n"
        "        basta una foto representativa, pero del color de la unidad.\"\"\"\n"
        "        from app.odoo_flota_reglas import color_de\n"
        "\n"
        "        fotos = {f.color: f for f in (self.categoria.variantes\n"
        "                                      if self.categoria else [])}\n"
        "        elegida = fotos.get(color_de(self.color)) or fotos.get(\"\")\n"
        "        return elegida.foto_url if elegida else self.foto_url\n",
        marca="        elegida = fotos.get(color_de(self.color)) or fotos.get(\"\")\n")

cambiar("models",
        "    PERSONAL_DE_BAJA = \"personal_de_baja\"\n",
        "    PERSONAL_DE_BAJA = \"personal_de_baja\"\n"
        "    # Odoo archivo una unidad que tenia dias asignados (seccion 52).\n"
        "    UNIDAD_DE_BAJA = \"unidad_de_baja\"\n",
        marca="UNIDAD_DE_BAJA = ")

# ================================================================ la conexion
cambiar("odoo_api",
        "        return self.llamar(modelo, \"search_read\", domain=dominio,\n"
        "                           fields=campos, order=\"id\", context=contexto) or []\n",
        "        return self.llamar(modelo, \"search_read\", domain=dominio,\n"
        "                           fields=campos, order=\"id\", context=contexto) or []\n"
        "\n"
        "    def campos(self, modelo: str) -> dict:\n"
        "        \"\"\"Los campos que tiene ese modelo en este Odoo: los que agrego\n"
        "        la empresa con Studio pueden no estar.\"\"\"\n"
        "        return self.llamar(modelo, \"fields_get\", attributes=[\"type\"]) or {}\n",
        marca="    def campos(self, modelo: str) -> dict:")

cambiar("rodoo",
        "hora. `POST /personal` se queda para quien todavia lo mande.\n",
        "hora. `POST /personal` se queda para quien todavia lo mande.\n"
        "\n"
        "La flota y el taller, igual (seccion 52): `/flota/ensayo` y\n"
        "`/flota/sincronizar`.\n",
        marca="La flota y el taller, igual (seccion 52)")
cambiar("rodoo",
        "from app import odoo, odoo_api, odoo_personal, schemas as s\n",
        "from app import odoo, odoo_api, odoo_flota, odoo_personal, schemas as s\n")
cambiar("rodoo",
        "def _leer_personal(db: Session, ensayo: bool, quien: m.Usuario) -> dict:\n"
        "    cliente = _conexion()\n"
        "    try:\n"
        "        return odoo_personal.sincronizar(db, cliente, ensayo=ensayo,\n"
        "                                         quien=None if ensayo else quien)\n",
        "def _leer(modulo, db: Session, ensayo: bool, quien: m.Usuario) -> dict:\n"
        "    \"\"\"El personal o la flota: la misma puerta, el mismo 503 y el\n"
        "    mismo 502.\"\"\"\n"
        "    cliente = _conexion()\n"
        "    try:\n"
        "        return modulo.sincronizar(db, cliente, ensayo=ensayo,\n"
        "                                  quien=None if ensayo else quien)\n")
cambiar("rodoo",
        "    return _leer_personal(db, True, usuario)\n",
        "    return _leer(odoo_personal, db, True, usuario)\n")
cambiar("rodoo",
        "    return _leer_personal(db, False, usuario)\n",
        "    return _leer(odoo_personal, db, False, usuario)\n"
        "\n"
        "\n"
        "# ------------------------------------------------ la flota, leida de Odoo\n"
        "\n"
        "@router.get(\"/flota/ensayo\",\n"
        "            summary=\"Que cambiaria al leer la flota y el taller, sin guardar\")\n"
        "def flota_ensayo(db: Session = Depends(get_db),\n"
        "                 usuario: m.Usuario = Depends(requiere(m.Rol.ADMIN))):\n"
        "    \"\"\"Lee Odoo y dice que haria con las unidades de Proteccion\n"
        "    Ejecutiva y con el taller. No guarda nada, ni aqui ni en Odoo.\"\"\"\n"
        "    return _leer(odoo_flota, db, True, usuario)\n"
        "\n"
        "\n"
        "@router.post(\"/flota/sincronizar\",\n"
        "             summary=\"Leer la flota y el taller de Odoo y guardarlos\")\n"
        "def flota_sincronizar(db: Session = Depends(get_db),\n"
        "                      usuario: m.Usuario = Depends(requiere(m.Rol.ADMIN))):\n"
        "    \"\"\"Lo mismo que el ensayo, guardado. La primera vez se hace a mano;\n"
        "    de ahi en adelante se lee sola cada hora.\"\"\"\n"
        "    return _leer(odoo_flota, db, False, usuario)\n",
        marca="def flota_sincronizar(")

cambiar("celery",
        "        \"odoo-personal\": {\n"
        "            \"task\": \"odoo.sincronizar_personal\",\n"
        "            \"schedule\": crontab(minute=17),\n"
        "        },\n",
        "        \"odoo-personal\": {\n"
        "            \"task\": \"odoo.sincronizar_personal\",\n"
        "            \"schedule\": crontab(minute=17),\n"
        "        },\n"
        "        # La flota y el taller (seccion 52), diez minutos despues. Tambien\n"
        "        # espera a la primera lectura hecha a mano.\n"
        "        \"odoo-flota\": {\n"
        "            \"task\": \"odoo.sincronizar_flota\",\n"
        "            \"schedule\": crontab(minute=27),\n"
        "        },\n",
        marca="\"odoo-flota\": {")
cambiar("celery",
        "        return odoo_personal.sincronizar_si_toca(db)\n"
        "    finally:\n"
        "        db.close()\n",
        "        return odoo_personal.sincronizar_si_toca(db)\n"
        "    finally:\n"
        "        db.close()\n"
        "\n"
        "\n"
        "@celery.task(name=\"odoo.sincronizar_flota\")\n"
        "def sincronizar_flota_de_odoo():\n"
        "    \"\"\"La flota y el taller de Proteccion Ejecutiva, leidos de Odoo.\"\"\"\n"
        "    from app.db import SessionLocal\n"
        "    from app import odoo_flota\n"
        "\n"
        "    db = SessionLocal()\n"
        "    try:\n"
        "        return odoo_flota.sincronizar_si_toca(db)\n"
        "    finally:\n"
        "        db.close()\n",
        marca="def sincronizar_flota_de_odoo(")

# ================================================================ el taller bloquea
cambiar("disponibilidad",
        "    ocupadas = _jornadas_de_vehiculo(db, vehiculo_id, inicio, fin)\n"
        "    return _evaluar(ocupadas, inicio, fin, bloquea_dia, excluir_jornada_id, holgura_minima)\n",
        "    ocupadas = _jornadas_de_vehiculo(db, vehiculo_id, inicio, fin)\n"
        "    return (_en_el_taller(db, vehiculo_id, inicio, fin)\n"
        "            + _evaluar(ocupadas, inicio, fin, bloquea_dia,\n"
        "                       excluir_jornada_id, holgura_minima))\n"
        "\n"
        "\n"
        "def _en_el_taller(db: Session, vehiculo_id: int, inicio: datetime,\n"
        "                  fin: datetime) -> list[Hallazgo]:\n"
        "    \"\"\"La unidad en el taller no se ofrece (seccion 52).\n"
        "\n"
        "    El implantado ya lo respetaba y el eventual no: al asignar un\n"
        "    eventual, un coche desarmado salia libre, y asi se le promete al\n"
        "    cliente una unidad que no existe. Sin fecha de salida se da por\n"
        "    adentro.\n"
        "    \"\"\"\n"
        "    salida = []\n"
        "    for fila in (db.query(m.TallerVehiculo)\n"
        "                 .filter(m.TallerVehiculo.vehiculo_id == vehiculo_id,\n"
        "                         m.TallerVehiculo.desde <= fin.date())\n"
        "                 .order_by(m.TallerVehiculo.desde).all()):\n"
        "        if fila.hasta is not None and fila.hasta < inicio.date():\n"
        "            continue\n"
        "        hasta = (f\"hasta el {fila.hasta:%d/%m}\" if fila.hasta\n"
        "                 else \"sin fecha de salida\")\n"
        "        salida.append(Hallazgo(\n"
        "            nivel=\"bloqueo\",\n"
        "            motivo=f\"En el taller desde el {fila.desde:%d/%m}, {hasta}\",\n"
        "            jornada_id=None, servicio_folio=None, inicio=inicio, fin=fin))\n"
        "    return salida\n",
        marca="def _en_el_taller(")

# ================================================================ la foto de categoria
cambiar("catalogos",
        "from fastapi import APIRouter, Depends\n",
        "from fastapi import APIRouter, Depends, File, HTTPException, UploadFile\n")
cambiar("catalogos",
        "from app import auth\n",
        "from app import accesos, auth, imagenes\n")
cambiar("catalogos",
        "from app.routers.crud import crud_router\n",
        "from app.odoo_flota_reglas import color_de\n"
        "from app.routers.crud import crud_router\n")
cambiar("catalogos",
        "_CATALOGOS = [\n",
        "# ------------------------------------------------ la foto de la categoria\n"
        "\n"
        "ADMINISTRA = auth.requiere(m.Rol.ADMIN)\n"
        "\n"
        "\n"
        "@router.put(\"/categorias-vehiculo/{categoria_id}/foto\",\n"
        "            tags=[\"Categorias de vehiculo\"],\n"
        "            summary=\"La foto representativa de una categoria, en un color\")\n"
        "async def poner_foto_de_categoria(\n"
        "        categoria_id: int, archivo: UploadFile = File(...),\n"
        "        color: str = \"\", db: Session = Depends(get_db),\n"
        "        actor: m.Usuario = Depends(ADMINISTRA)):\n"
        "    \"\"\"Decision de Salvador (23 sep): la unidad no lleva su foto real,\n"
        "    lleva la de su categoria en su color. Sin color es la base: la que\n"
        "    ensenan los colores que todavia no tienen la suya.\"\"\"\n"
        "    categoria = db.get(m.CategoriaVehiculo, categoria_id)\n"
        "    if not categoria:\n"
        "        raise HTTPException(404, f\"No existe la categoria {categoria_id}\")\n"
        "    contenido = await imagenes.leer(archivo)\n"
        "    color = color_de(color)\n"
        "    foto = (db.query(m.FotoCategoria)\n"
        "            .filter_by(categoria_id=categoria.id, color=color).first())\n"
        "    if foto is None:\n"
        "        foto = m.FotoCategoria(categoria_id=categoria.id, color=color)\n"
        "        db.add(foto)\n"
        "    foto.foto_url = contenido\n"
        "    accesos.anotar(db, actor, \"foto de categoria\", \"categoria_vehiculo\",\n"
        "                   categoria.id, despues=color or \"base\",\n"
        "                   detalle=categoria.nombre)\n"
        "    db.commit()\n"
        "    db.refresh(categoria)\n"
        "    return {\"categoria_id\": categoria.id, \"color\": color,\n"
        "            \"fotos\": categoria.fotos}\n"
        "\n"
        "\n"
        "@router.delete(\"/categorias-vehiculo/{categoria_id}/foto\", status_code=204,\n"
        "               tags=[\"Categorias de vehiculo\"],\n"
        "               summary=\"Quitar la foto de una categoria en un color\")\n"
        "def quitar_foto_de_categoria(categoria_id: int, color: str = \"\",\n"
        "                             db: Session = Depends(get_db),\n"
        "                             actor: m.Usuario = Depends(ADMINISTRA)):\n"
        "    foto = (db.query(m.FotoCategoria)\n"
        "            .filter_by(categoria_id=categoria_id, color=color_de(color))\n"
        "            .first())\n"
        "    if not foto:\n"
        "        raise HTTPException(404, \"Esa categoria no tiene foto en ese color\")\n"
        "    accesos.anotar(db, actor, \"foto de categoria quitada\",\n"
        "                   \"categoria_vehiculo\", categoria_id,\n"
        "                   antes=foto.color or \"base\")\n"
        "    db.delete(foto)\n"
        "    db.commit()\n"
        "\n"
        "\n"
        "_CATALOGOS = [\n",
        marca="async def poner_foto_de_categoria(")

cambiar("crud",
        "from app.db import get_db\n",
        "from app.db import get_db\n"
        "\n"
        "# Lo que manda Odoo en cada catalogo (secciones 51 y 52): en Centauro no\n"
        "# se edita, porque la siguiente lectura lo volveria a poner como estaba.\n"
        "DE_ODOO = {\n"
        "    m.Persona: (\"nombre\", \"correo\", \"plaza_id\", \"odoo_id\"),\n"
        "    m.Vehiculo: (\"placa\", \"categoria_id\", \"plaza_id\", \"marca_modelo\",\n"
        "                 \"color\", \"modelo_anio\"),\n"
        "}\n",
        marca="DE_ODOO = {\n")
cambiar("crud",
        "        # Lo que llega de Odoo se corrige en Odoo (seccion 51): cambiado\n"
        "        # aqui, la siguiente lectura lo volveria a poner como estaba.\n"
        "        if modelo is m.Persona and obj.odoo_id:\n"
        "            nuevos = datos.model_dump(exclude_unset=True)\n"
        "            tocados = [c for c in (\"nombre\", \"correo\", \"plaza_id\", \"odoo_id\")\n"
        "                       if c in nuevos and nuevos[c] != getattr(obj, c)]\n"
        "            if tocados:\n"
        "                raise HTTPException(409, {\n"
        "                    \"mensaje\": \"Viene de Odoo: se corrige en Odoo.\",\n"
        "                    \"que_hacer\": \"Recursos Humanos lo cambia en la ficha del \"\n"
        "                                 \"empleado en Odoo y Centauro lo toma en la \"\n"
        "                                 \"siguiente lectura.\",\n",
        "        # Lo que llega de Odoo se corrige en Odoo (secciones 51 y 52).\n"
        "        de_odoo = DE_ODOO.get(modelo)\n"
        "        if de_odoo and obj.odoo_id:\n"
        "            nuevos = datos.model_dump(exclude_unset=True)\n"
        "            tocados = [c for c in de_odoo\n"
        "                       if c in nuevos and nuevos[c] != getattr(obj, c)]\n"
        "            if tocados:\n"
        "                raise HTTPException(409, {\n"
        "                    \"mensaje\": \"Viene de Odoo: se corrige en Odoo.\",\n"
        "                    \"que_hacer\": \"Se cambia en Odoo --Recursos Humanos en la \"\n"
        "                                 \"ficha del empleado, Flotilla en la de la \"\n"
        "                                 \"unidad-- y Centauro lo toma en la \"\n"
        "                                 \"siguiente lectura.\",\n",
        marca="        de_odoo = DE_ODOO.get(modelo)\n")

cambiar("schemas",
        "class CategoriaVehiculoOut(CategoriaVehiculoIn):\n"
        "    id: int\n"
        "    activo: bool\n",
        "class CategoriaVehiculoOut(CategoriaVehiculoIn):\n"
        "    id: int\n"
        "    activo: bool\n"
        "    # Los colores que tienen foto; \"\" es la base (seccion 52).\n"
        "    fotos: list[str] = []\n",
        marca="    fotos: list[str] = []\n")
cambiar("schemas",
        "class VehiculoOut(VehiculoIn):\n"
        "    id: int\n"
        "    activo: bool\n",
        "class VehiculoOut(VehiculoIn):\n"
        "    id: int\n"
        "    activo: bool\n"
        "    # Si viene de Odoo: lo de Odoo ya no se edita aqui (seccion 52).\n"
        "    odoo_id: int | None = None\n",
        marca="    # Si viene de Odoo: lo de Odoo ya no se edita aqui (seccion 52).\n")

# ================================================================ el Sedan
cambiar("seed",
        "            (\"van_10\", \"Van 10 pax\", False, \"8.5\"),\n",
        "            (\"van_10\", \"Van 10 pax\", False, \"8.5\"),\n"
        "            # Odoo ya lo tenia (seccion 52). Rendimiento y precios de\n"
        "            # ejemplo, como el resto, hasta cargar los reales.\n"
        "            (\"sedan\", \"Sedán\", False, \"15.0\"),\n",
        marca="(\"sedan\", \"Sedán\", False, \"15.0\"),")
cambiar("seed",
        "            \"van_10\":             {\"full_day\": \"4000\", \"medio_dia\": \"2400\", \"transfer\": \"1600\"},\n",
        "            \"van_10\":             {\"full_day\": \"4000\", \"medio_dia\": \"2400\", \"transfer\": \"1600\"},\n"
        "            \"sedan\":              {\"full_day\": \"2200\", \"medio_dia\": \"1300\", \"transfer\": \"900\"},\n",
        marca="            \"sedan\":              {")
cambiar("seed",
        "                   \"suv\": \"110000\", \"suv_blindada\": \"187000\", \"van_10\": \"88000\"}\n",
        "                   \"suv\": \"110000\", \"suv_blindada\": \"187000\", \"van_10\": \"88000\",\n"
        "                   \"sedan\": \"48000\"}\n",
        marca="                   \"sedan\": \"48000\"}\n")

# ================================================================ la foto que se ensena
cambiar("tasksheet",
        "        \"foto\": a.vehiculo.foto_url,\n",
        "        # La de su categoria en su color (seccion 52).\n"
        "        \"foto\": a.vehiculo.foto,\n")
cambiar("servicios",
        "            \"foto\": a.vehiculo.foto_url, \"dias\": 0})\n",
        "            \"foto\": a.vehiculo.foto, \"dias\": 0})\n")
cambiar("servicios",
        "                       \"foto\": a.vehiculo.foto_url}\n",
        "                       \"foto\": a.vehiculo.foto}\n")
cambiar("hoja_implantado",
        "        \"foto_url\": vehiculo.foto_url,\n",
        "        \"foto_url\": vehiculo.foto,\n")

# ================================================================ pantallas
for viejo, nuevo in (
        ("    bit_alerta_personal_de_baja: \"Dado de baja en Odoo\",\n",
         "    bit_alerta_unidad_de_baja: \"Unidad dada de baja en Odoo\",\n"),
        ("    bit_alerta_personal_de_baja: \"Terminated in Odoo\",\n",
         "    bit_alerta_unidad_de_baja: \"Vehicle retired in Odoo\",\n"),
        ("    bit_alerta_personal_de_baja: \"Desligado no Odoo\",\n",
         "    bit_alerta_unidad_de_baja: \"Veículo baixado no Odoo\",\n")):
    cambiar("idioma", viejo, viejo + nuevo, marca=nuevo)

# ================================================================ repo y despliegue
cambiar("gitignore",
        "backend/odoo_personal_ultimo.json\n",
        "backend/odoo_personal_ultimo.json\n"
        "backend/odoo_flota_ultimo.json\n",
        marca="backend/odoo_flota_ultimo.json\n")

cambiar("leeme",
        "La primera lectura del personal se hace a mano, después de ver el\n"
        "ensayo; la tarea de cada hora no arranca hasta que exista esa primera:\n"
        "\n"
        "```bash\n"
        "docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py\n"
        "docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py --aplicar\n"
        "```\n",
        "La primera lectura del personal y la de la flota se hacen a mano,\n"
        "después de ver el ensayo; las tareas de cada hora no arrancan hasta que\n"
        "exista esa primera:\n"
        "\n"
        "```bash\n"
        "docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py\n"
        "docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py --aplicar\n"
        "docker compose -f docker-compose.prod.yml run --rm api python sincronizar_flota.py\n"
        "docker compose -f docker-compose.prod.yml run --rm api python sincronizar_flota.py --aplicar\n"
        "```\n"
        "\n"
        "Para la flota, el usuario de la conexión también necesita leer\n"
        "*Flotilla*. Las fotos de las categorías se cargan una vez desde una\n"
        "carpeta (`fotos_de_categoria.py`, instrucciones adentro): la base de\n"
        "cada categoría y una por color.\n",
        marca="python sincronizar_flota.py --aplicar\n")

cambiar("bitacora",
        "## 14. Lo que falta\n",
        "## 52. La flota y el taller, leídos de Odoo\n"
        "\n"
        "Decisión de Salvador, 23 de septiembre: etapa 2 de la conexión con\n"
        "Odoo, igual que el personal.\n"
        "\n"
        "- **Qué entra.** Las unidades con la etiqueta «PROTECCIÓN EJECUTIVA» o\n"
        "  «pe». Logística, Dirección y las utilitarias no. La llave es el\n"
        "  número interno de Odoo; la primera vez se vincula por placa.\n"
        "- **Qué manda Odoo.** Placa, categoría, plaza —la Ubicación; el Estado\n"
        "  de México va como Ciudad de México—, marca y modelo, color y año. En\n"
        "  el catálogo ya no se editan. Lo vacío no borra. Implantado o\n"
        "  eventual, y el costo diario, siguen siendo de Centauro; los autos\n"
        "  rentados no se tocan.\n"
        "- **Las categorías** son las siete de Odoo. VAN es la «Van 10 pax» y\n"
        "  **Sedán** se agrega, con rendimiento y precios de ejemplo como el\n"
        "  resto del tarifario hasta cargar los reales.\n"
        "- **La foto** no es la de cada camioneta: es la de su categoría,\n"
        "  respetando su color. Cada categoría tiene una foto base y una por\n"
        "  color; la unidad enseña la de su color y, si no hay, la base. Se\n"
        "  cargan en Centauro (`fotos_de_categoria.py`), que al final dice qué\n"
        "  colores de la flota todavía no tienen la suya.\n"
        "- **Baja.** Si Odoo la archiva, deja de ofrecerse y la central recibe\n"
        "  una alerta *unidad dada de baja en Odoo* en cada día que tenía\n"
        "  asignado; su consultor, un aviso. Si le quitan la etiqueta, queda\n"
        "  pendiente y no se da de baja sola.\n"
        "- **El taller.** Las entradas de Flotilla → Servicios de tipo\n"
        "  Preventivo, Correctivo o Desgaste natural sacan la unidad de\n"
        "  circulación de la fecha de entrada a la de salida; sin salida, se da\n"
        "  por adentro. Lo que Odoo cancela o borra deja de bloquear. Lo que se\n"
        "  capturó a mano en Centauro no se toca. «Resguardo de Unidad» y los\n"
        "  de contrato no cuentan.\n"
        "- **El taller bloquea al eventual.** Hasta hoy solo el implantado lo\n"
        "  respetaba: al asignar un eventual, una unidad en el taller salía\n"
        "  libre. Ahora sale ocupada, con el motivo, y no se puede asignar.\n"
        "- **Cómo se lee.** `GET /odoo/flota/ensayo`, `POST\n"
        "  /odoo/flota/sincronizar` y `sincronizar_flota.py`; la tarea\n"
        "  `odoo.sincronizar_flota` cada hora, a los 27 minutos, después de la\n"
        "  primera lectura a mano.\n"
        "\n"
        "## 14. Lo que falta\n",
        marca="## 52. La flota y el taller, leídos de Odoo\n")

# ================================================================ escrituras
for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(textos[clave])
        print("escrito ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for relativa, contenido in NUEVOS.items():
    ruta = B / relativa
    if ruta.exists() and io.open(ruta, encoding="utf-8").read() == contenido:
        print("sin cambio", ruta.relative_to(RAIZ))
    else:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        print("escrito ", ruta.relative_to(RAIZ))
for s in saltados:
    print("saltado:", s)

# -*- coding: utf-8 -*-
"""El personal de seguridad, leido de Odoo (etapa 1 de la conexion).

Decision de Salvador, 23 sep: Odoo es el maestro de empleados y Centauro
lee de ahi al personal de seguridad, en vez de capturarlo a mano.

  * Entra el puesto «Personal de Seguridad...» o «Security Driver...».
  * La llave es el numero interno de Odoo; quien ya estaba se vincula por
    su correo la primera vez.
  * Nombre, plaza, celular, correo, referencia, fecha de ingreso y foto
    vienen de Odoo y en el catalogo ya no se editan. Lo vacio no borra.
  * Alta: persona y acceso sin contrasena (entra con el codigo dictado).
  * Baja: Odoo la archiva -> no disponible, acceso cerrado (salvo que
    deba viaticos: se cierra en cuanto los compruebe), alerta a la
    central en cada dia que tenia por delante y aviso a su consultor.
  * Lo dudoso queda pendiente. Nunca escribe en Odoo.
  * Ensayo por consola y por terminal; la tarea de cada hora espera a la
    primera lectura hecha a mano.
  * El buscador del codigo encuentra por numero de empleado.
  * De paso: el aviso del visto bueno abria una direccion que no existia.

Idempotente. Todas las escrituras al final.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    "models": B / "app/models.py",
    "config": B / "app/config.py",
    "rodoo": B / "app/routers/odoo.py",
    "celery": B / "app/celery_app.py",
    "contrasenas": B / "app/contrasenas.py",
    "crud": B / "app/routers/crud.py",
    "schemas": B / "app/schemas.py",
    "cierre": B / "app/cierre.py",
    "idioma": B / "app/web/idioma.js",
    "codigo": B / "app/web/codigo.js",
    "conftest": B / "tests/conftest.py",
    "hoja": B / "hoja_rh_odoo.py",
    "gitignore": RAIZ / ".gitignore",
    "leeme": RAIZ / "despliegue/LEEME.md",
    "bitacora": RAIZ / "BITACORA.md",
}
NUEVOS = {
    'app/odoo_api.py': '# -*- coding: utf-8 -*-\n"""La conexion con Odoo, de solo lectura.\n\nOdoo 19 en la nube (centauro.odoo.com), plan Personalizado. Su API\nexterna es JSON-2: POST /json/2/<modelo>/<metodo>, con la llave en la\ncabecera. La API vieja (XML-RPC y JSON-RPC) desaparece con Odoo 20, asi\nque aqui ni se toca.\n\nEste cliente SOLO LEE: los metodos permitidos estan en LECTURA y cualquier\notro truena antes de salir a la red. La conexion de Centauro no escribe en\nOdoo; lo unico que algun dia escribira es la factura en borrador, y eso\ntendra su propio cliente, probado primero en una copia de Odoo.\n\nLa llave es la del usuario de la conexion --no la de una persona--, vive\nsolo en el .env del servidor (ODOO_API_KEY) y dura a lo mas tres meses:\nOdoo no permite mas.\n"""\nimport httpx\n\nfrom app.config import settings\n\nLECTURA = frozenset({"search_read", "fields_get"})\n\n\nclass SinConexion(Exception):\n    """Odoo no esta configurado en este servidor."""\n\n\nclass NoResponde(Exception):\n    """Odoo no contesto, o rechazo la llave."""\n\n\ndef hay_conexion() -> bool:\n    return bool(settings.odoo_base and settings.odoo_api_key)\n\n\nclass Odoo:\n    def __init__(self, base: str, llave: str, bd: str | None = None,\n                 timeout: int = 20):\n        base = base.strip().rstrip("/")\n        self.base = base if base.startswith("http") else "https://" + base\n        cabeceras = {"Authorization": f"bearer {llave}",\n                     "Content-Type": "application/json; charset=utf-8",\n                     "User-Agent": "centauro/1.0"}\n        if bd:\n            cabeceras["X-Odoo-Database"] = bd\n        self.http = httpx.Client(headers=cabeceras, timeout=timeout)\n\n    def llamar(self, modelo: str, metodo: str, **args):\n        if metodo not in LECTURA:\n            raise RuntimeError(f"{metodo} no es de lectura: esta conexion no "\n                               "escribe en Odoo")\n        contexto = {"lang": "es_MX", **args.pop("context", {})}\n        try:\n            r = self.http.post(f"{self.base}/json/2/{modelo}/{metodo}",\n                               json={"context": contexto, **args})\n        except httpx.HTTPError as error:\n            raise NoResponde(f"Odoo no contesto: {error}") from error\n        if r.status_code == 200:\n            return r.json()\n        try:\n            mensaje = r.json().get("message") or r.text\n        except ValueError:\n            mensaje = r.text\n        mensaje = " ".join(str(mensaje).split())[:200]\n        if r.status_code == 401:\n            raise NoResponde("Odoo rechazo la llave; puede que haya vencido. "\n                             + mensaje)\n        raise NoResponde(f"Odoo contesto {r.status_code}: {mensaje}")\n\n    def leer(self, modelo: str, dominio: list, campos: list,\n             archivados: bool = False) -> list:\n        contexto = {"active_test": False} if archivados else {}\n        return self.llamar(modelo, "search_read", domain=dominio,\n                           fields=campos, order="id", context=contexto) or []\n\n\ndef cliente() -> Odoo:\n    if not hay_conexion():\n        raise SinConexion("Odoo no esta conectado en este servidor.")\n    return Odoo(settings.odoo_base, settings.odoo_api_key,\n                settings.odoo_bd or None, settings.odoo_timeout)\n',
    'app/odoo_personal_reglas.py': '# -*- coding: utf-8 -*-\n"""Las reglas del personal que viene de Odoo, sin base de datos.\n\nAqui se decide que hacer con cada empleado --darlo de alta, vincularlo,\ncambiarle algo o dejarlo pendiente-- a partir de fotos fijas de Odoo y de\nCentauro. No lee ni escribe nada: por eso se prueba sola, y por eso el\nensayo y la sincronizacion de verdad deciden exactamente lo mismo.\n\nLas decisiones de Salvador (23 de septiembre) que viven aqui:\n\n  * Entra el personal de seguridad: puesto «Personal de Seguridad...» o\n    «Security Driver...». Monitoristas, oficina y guardias no.\n  * La llave es el numero interno de Odoo.\n  * El correo con el que entra a la app es el de trabajo o, si no tiene,\n    el personal.\n  * El Estado de Mexico va como Ciudad de Mexico: es la misma zona\n    metropolitana.\n  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.\n"""\nimport collections\nimport re\nimport unicodedata\nfrom datetime import date, datetime\n\nPUESTOS = ("personal de seguridad", "security driver")\nALIAS_PLAZA = {\n    "estado de mexico": "ciudad de mexico",\n    "edomex": "ciudad de mexico",\n    "cdmx": "ciudad de mexico",\n}\n# Los errores de dedo que ya aparecieron en Odoo o que aparecen siempre.\nDOMINIOS_RAROS = frozenset({\n    "gamil.com", "gmial.com", "gmai.com", "gmail.con", "gmail.co",\n    "hotmial.com", "hotmal.com", "hotmail.con", "hotamil.com",\n    "yaho.com", "yahoo.con", "outlok.com", "outlook.con"})\nCORREO_VALIDO = re.compile(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")\n\n# Como empieza cada imagen en base64. El SVG no esta porque es el avatar\n# de iniciales que Odoo le pone a quien no tiene foto: no es una foto, y\n# en el task sheet el cliente no reconoceria a nadie por sus iniciales.\nFIRMAS = (("iVBOR", "image/png"), ("/9j/", "image/jpeg"),\n          ("R0lGOD", "image/gif"), ("UklGR", "image/webp"))\n\n\ndef normal(texto) -> str:\n    """Sin acentos, sin mayusculas y sin espacios de sobra."""\n    texto = unicodedata.normalize("NFKD", str(texto or ""))\n    texto = "".join(c for c in texto if not unicodedata.combining(c))\n    return " ".join(texto.lower().split())\n\n\ndef texto(valor) -> str:\n    return "" if valor in (False, None) else str(valor).strip()\n\n\ndef nombre_de(valor) -> str:\n    """El nombre de un many2one, venga como [id, nombre] o como dict."""\n    if isinstance(valor, (list, tuple)) and len(valor) > 1:\n        return texto(valor[1])\n    if isinstance(valor, dict):\n        return texto(valor.get("display_name") or valor.get("name"))\n    return ""\n\n\ndef fecha(valor) -> date | None:\n    try:\n        return date.fromisoformat(texto(valor)[:10]) if texto(valor) else None\n    except ValueError:\n        return None\n\n\ndef instante(valor) -> datetime | None:\n    """El write_date de Odoo: «AAAA-MM-DD HH:MM:SS», en UTC."""\n    try:\n        return datetime.fromisoformat(texto(valor)[:19]) if texto(valor) else None\n    except ValueError:\n        return None\n\n\ndef es_de_seguridad(empleado: dict) -> bool:\n    """Por el puesto del catalogo y, si no lo tiene, por el escrito."""\n    return any(normal(t).startswith(PUESTOS)\n               for t in (nombre_de(empleado.get("job_id")),\n                         empleado.get("job_title")))\n\n\ndef correo_de(empleado: dict) -> str:\n    for campo in ("work_email", "private_email"):\n        valor = texto(empleado.get(campo)).lower()\n        if valor:\n            return valor\n    return ""\n\n\ndef problema_de_correo(correo: str) -> str | None:\n    if not correo:\n        return "sin correo"\n    if not CORREO_VALIDO.match(correo):\n        return "correo mal escrito"\n    if correo.split("@")[-1] in DOMINIOS_RAROS:\n        return "correo con error de dedo"\n    return None\n\n\ndef plaza_de(empleado: dict, plazas: dict) -> tuple:\n    """(plaza o None, lo que dice Odoo). `plazas` va por nombre normalizado."""\n    lugar = nombre_de(empleado.get("work_location_id"))\n    clave = normal(lugar)\n    return plazas.get(ALIAS_PLAZA.get(clave, clave)), lugar\n\n\ndef foto_de(base64: str | None) -> str | None:\n    """La foto lista para una etiqueta <img>, o None si no es una foto."""\n    if not base64 or not isinstance(base64, str):\n        return None\n    base64 = base64.strip()\n    for firma, tipo in FIRMAS:\n        if base64.startswith(firma):\n            return f"data:{tipo};base64,{base64}"\n    return None\n\n\n# ------------------------------------------------------------------ el plan\n\ndef planear(empleados: list, personas: list, plazas: dict,\n            correos_de_acceso: dict, normalizar_tel) -> dict:\n    """Que hacer con cada empleado de Odoo, sin hacerlo.\n\n    `empleados`: lo que leyo Odoo (los activos). `personas`: foto fija de\n    Centauro, una por persona, con id, odoo_id, nombre, correo, plaza_id,\n    pais_id, activo, telefono, referencia, fecha_ingreso, foto (si tiene),\n    sincronizado_en y baja_odoo_en. `plazas`: por nombre normalizado, con\n    id, nombre y pais_id. `correos_de_acceso`: correo -> persona_id de los\n    accesos que ya existen. `normalizar_tel(numero, pais_id)`: la regla de\n    la lada del sistema.\n    """\n    elegidos = [e for e in empleados if es_de_seguridad(e)]\n    por_odoo = {p["odoo_id"]: p for p in personas if p.get("odoo_id")}\n    por_correo = {texto(p.get("correo")).lower(): p\n                  for p in personas if p.get("correo")}\n    cuenta = collections.Counter(correo_de(e) for e in elegidos if correo_de(e))\n    repetidos = {c for c, n in cuenta.items() if n > 1}\n\n    plan = {"leidos": len(elegidos), "altas": [], "vinculos": [],\n            "cambios": [], "fotos": [], "pendientes": [], "sin_cambio": 0,\n            "procesadas": [], "revisar_salida": []}\n    tomados = set()        # correos que este plan ya aparto\n\n    def pendiente(e, persona_id, faltas):\n        plan["pendientes"].append({"odoo_id": e["id"], "persona_id": persona_id,\n                                   "nombre": texto(e.get("name")),\n                                   "falta": faltas})\n\n    for e in elegidos:\n        nombre = texto(e.get("name"))\n        correo = correo_de(e)\n        problema = ("correo repetido en Odoo" if correo in repetidos\n                    else problema_de_correo(correo))\n        plaza, lugar = plaza_de(e, plazas)\n\n        persona, vinculo = por_odoo.get(e["id"]), False\n        if persona is None and correo and not problema:\n            candidata = por_correo.get(correo)\n            if candidata is not None:\n                if candidata.get("odoo_id") and candidata["odoo_id"] != e["id"]:\n                    pendiente(e, candidata["id"],\n                              ["su correo ya es de otra persona en Centauro"])\n                    continue\n                persona, vinculo = candidata, True\n\n        # ------------------------------------------------ quien llega nuevo\n        if persona is None:\n            faltas = []\n            if plaza is None:\n                faltas.append(f"la plaza «{lugar}» no existe en Centauro"\n                              if lugar else "sin plaza")\n            if problema:\n                faltas.append(problema)\n            elif correo in correos_de_acceso or correo in tomados:\n                faltas.append("su correo ya es de otro acceso en Centauro")\n            if faltas:\n                pendiente(e, None, faltas)\n                continue\n            tomados.add(correo)\n            celular = texto(e.get("mobile_phone"))\n            plan["altas"].append({\n                "odoo_id": e["id"], "nombre": nombre, "correo": correo,\n                "plaza_id": plaza["id"], "plaza": plaza["nombre"],\n                "telefono": (normalizar_tel(celular, plaza["pais_id"])\n                             if celular else None),\n                "referencia": texto(e.get("registration_number")) or None,\n                "fecha_ingreso": fecha(e.get("first_contract_date"))})\n            plan["fotos"].append(e["id"])\n            continue\n\n        # ------------------------------------------------ quien ya esta\n        if not persona.get("activo"):\n            pendiente(e, persona["id"], ["activo en Odoo pero dado de baja en "\n                                         "Centauro: reactivar a mano"])\n            continue\n\n        valores, que, avisos = {}, [], []\n        if nombre and nombre != persona.get("nombre"):\n            valores["nombre"] = nombre\n            que.append("nombre")\n        if plaza is not None and plaza["id"] != persona.get("plaza_id"):\n            valores["plaza_id"] = plaza["id"]\n            que.append("plaza")\n        elif plaza is None and lugar:\n            avisos.append(f"la plaza «{lugar}» no existe en Centauro")\n        celular = texto(e.get("mobile_phone"))\n        if celular:\n            pais = plaza["pais_id"] if plaza is not None else persona.get("pais_id")\n            tel = normalizar_tel(celular, pais)\n            if tel and tel != persona.get("telefono"):\n                valores["telefono"] = tel\n                que.append("celular")\n        referencia = texto(e.get("registration_number"))\n        if referencia and referencia != persona.get("referencia"):\n            valores["referencia"] = referencia\n            que.append("referencia")\n        ingreso = fecha(e.get("first_contract_date"))\n        if ingreso and ingreso != persona.get("fecha_ingreso"):\n            valores["fecha_ingreso"] = ingreso\n            que.append("fecha de ingreso")\n        actual = texto(persona.get("correo")).lower()\n        if correo and correo != actual:\n            otra = por_correo.get(correo)\n            if problema:\n                avisos.append(problema)\n            elif ((otra is not None and otra["id"] != persona["id"])\n                  or correo in tomados\n                  or correos_de_acceso.get(correo, persona["id"]) != persona["id"]):\n                avisos.append("su correo nuevo ya es de otra persona en Centauro")\n            else:\n                valores["correo"] = correo\n                que.append("correo")\n                tomados.add(correo)\n\n        # La foto se vuelve a pedir solo si Odoo toco la ficha despues de\n        # la ultima lectura: subir una foto cambia el write_date. Quien\n        # solo tiene el circulo de iniciales no se vuelve a pedir cada\n        # hora; se pide cuando RH le suba una de verdad.\n        escrito = instante(e.get("write_date"))\n        if (not persona.get("sincronizado_en")\n                or (escrito and escrito > persona["sincronizado_en"])):\n            plan["fotos"].append(e["id"])\n\n        if vinculo:\n            plan["vinculos"].append({"persona_id": persona["id"],\n                                     "odoo_id": e["id"],\n                                     "nombre": nombre or persona.get("nombre")})\n        if valores:\n            plan["cambios"].append({"persona_id": persona["id"],\n                                    "odoo_id": e["id"],\n                                    "nombre": nombre or persona.get("nombre"),\n                                    "valores": valores, "que": que})\n        elif not vinculo:\n            plan["sin_cambio"] += 1\n        if avisos:\n            pendiente(e, persona["id"], avisos)\n        plan["procesadas"].append(persona["id"])\n\n    # Las que Centauro ya lleva desde Odoo y hoy no salieron en la lista:\n    # o las archivaron, o dejaron de ser de seguridad. Se pregunta a Odoo\n    # por cada una antes de decidir.\n    ids = {e["id"] for e in elegidos}\n    plan["revisar_salida"] = [\n        p for p in personas\n        if p.get("odoo_id") and p.get("activo") and p.get("sincronizado_en")\n        and p["odoo_id"] not in ids]\n    return plan\n\n\ndef clasificar_salidas(revisar: list, estados: dict) -> tuple:\n    """(bajas, pendientes). `estados`: lo que dice Odoo de cada una,\n    leido con los archivados incluidos."""\n    bajas, pendientes = [], []\n    for p in revisar:\n        f = estados.get(p["odoo_id"])\n        if f is not None and f.get("active", True) is not False:\n            pendientes.append({"odoo_id": p["odoo_id"], "persona_id": p["id"],\n                               "nombre": p.get("nombre"),\n                               "falta": ["ya no tiene puesto de seguridad "\n                                         "en Odoo"]})\n        else:\n            bajas.append({"odoo_id": p["odoo_id"], "persona_id": p["id"],\n                          "nombre": p.get("nombre"),\n                          "motivo": ("archivado en Odoo" if f is not None\n                                     else "ya no esta en Odoo")})\n    return bajas, pendientes\n',
    'app/odoo_personal.py': '# -*- coding: utf-8 -*-\n"""El personal de seguridad, leido de Odoo.\n\nDecision de Salvador, 23 de septiembre: etapa 1 de la conexion con Odoo.\nOdoo es el maestro de empleados, asi que Centauro lee de ahi a la gente\nque va a la calle en vez de capturarla a mano.\n\n  * Entra el personal de seguridad: puesto «Personal de Seguridad» o\n    «Security Driver». Monitoristas, oficina y guardias no.\n  * La llave es el numero interno de Odoo: un cambio de nombre o de\n    correo ya no parte a nadie en dos.\n  * Lo que viene de Odoo --nombre, plaza, celular, correo, referencia,\n    fecha de ingreso y foto-- manda. En Centauro no se edita (el catalogo\n    lo rechaza): se corrige en Odoo. Lo de la operacion --a que servicio\n    va, con que rol, sus viaticos-- sigue siendo de Centauro.\n  * Un campo vacio en Odoo no borra el de Centauro.\n  * Alta: la persona y su acceso a la app, sin contrasena. Entra con el\n    codigo de cuatro digitos que le dicta su consultor o la central.\n  * Baja: si Odoo la archiva, deja de estar disponible en la siguiente\n    lectura y la central recibe una alerta en cada dia que tenia por\n    delante. Su acceso se cierra en ese momento, salvo que deba viaticos:\n    entonces sigue abierto solo para que los compruebe, y se cierra solo\n    en cuanto no deba nada. Es la misma regla que ya tenia el panel de\n    accesos: el que trae dinero de la empresa no se va hasta comprobarlo.\n  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.\n  * Nunca escribe en Odoo.\n  * Ensayo: dice que haria sin guardar nada.\n  * La tarea de cada hora no arranca sola: espera a que alguien haya\n    hecho la primera sincronizacion a mano, despues de ver el ensayo.\n\nLos datos del banco no se leen en esta etapa: son lo mas delicado que\nguarda el sistema y su lectura se decide aparte.\n\nLas reglas viven en odoo_personal_reglas.py, sin base de datos; aqui solo\nse leen las fotos fijas y se aplica lo que ellas deciden.\n"""\nimport json\nimport logging\nfrom datetime import datetime, timezone\n\nfrom sqlalchemy.orm import Session\n\nfrom app import accesos\nfrom app import models as m\nfrom app import odoo_personal_reglas as reglas\nfrom app import reloj, telefonos\n\nregistro = logging.getLogger("centauro.odoo")\n\nTIPO = "personal"\nCAMPOS = ["name", "job_id", "job_title", "work_location_id", "work_email",\n          "private_email", "mobile_phone", "registration_number",\n          "first_contract_date", "write_date"]\nACABADAS = (m.EstatusJornada.TERMINADA, m.EstatusJornada.CANCELADA)\n\n\ndef _utc() -> datetime:\n    """Sin zona y en UTC, como el write_date que manda Odoo."""\n    return datetime.now(timezone.utc).replace(tzinfo=None)\n\n\ndef _fotos_fijas(db: Session) -> tuple:\n    plazas = {reglas.normal(p.nombre): {"id": p.id, "nombre": p.nombre,\n                                        "pais_id": p.pais_id}\n              for p in db.query(m.Plaza).filter(m.Plaza.activo.is_(True)).all()}\n    personas = [{\n        "id": p.id, "odoo_id": p.odoo_id, "nombre": p.nombre,\n        "correo": p.correo, "plaza_id": p.plaza_id,\n        "pais_id": p.plaza.pais_id if p.plaza else None,\n        "activo": p.activo, "telefono": p.telefono,\n        "referencia": p.referencia, "fecha_ingreso": p.fecha_ingreso,\n        "foto": bool(p.foto_url), "sincronizado_en": p.odoo_sincronizado_en,\n        "baja_odoo_en": p.baja_odoo_en,\n    } for p in db.query(m.Persona).all()]\n    correos = {u.correo.strip().lower(): u.persona_id\n               for u in db.query(m.Usuario).all() if u.correo}\n    return plazas, personas, correos\n\n\ndef dias_por_delante(db: Session, persona_id: int,\n                     relojes: reloj.Relojes | None = None) -> list:\n    """Las asignaciones de esa persona de hoy en adelante.\n\n    El hoy es el del pais de cada servicio, como en el panel de accesos:\n    un servicio en Sao Paulo ya arranco cuando en Mexico todavia es de\n    madrugada. El dia de hoy cuenta aunque ya este en curso: es el que\n    mas urge cubrir.\n    """\n    relojes = relojes or reloj.Relojes(db)\n    filas = (db.query(m.AsignacionPersonal)\n             .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)\n             .filter(m.AsignacionPersonal.persona_id == persona_id,\n                     m.AsignacionPersonal.relevado_en.is_(None),\n                     m.Jornada.estatus.notin_(ACABADAS))\n             .order_by(m.Jornada.fecha).all())\n    salida = []\n    for a in filas:\n        servicio = a.jornada.equipo.servicio if a.jornada.equipo else None\n        if servicio and a.jornada.fecha >= relojes.hoy(servicio.pais_id):\n            salida.append(a)\n    return salida\n\n\ndef _accesos_por_cerrar(db: Session) -> list:\n    """Dadas de baja por Odoo que conservaban el acceso por deber\n    viaticos, y que ya no deben nada."""\n    filas = (db.query(m.Persona, m.Usuario)\n             .join(m.Usuario, m.Usuario.persona_id == m.Persona.id)\n             .filter(m.Persona.baja_odoo_en.isnot(None),\n                     m.Persona.activo.is_(False),\n                     m.Usuario.activo.is_(True))\n             .all())\n    return [(p, u) for p, u in filas if not accesos.viaticos_sin_cerrar(db, p.id)]\n\n\ndef _dar_de_baja(db: Session, baja: dict, ahora: datetime,\n                 relojes: reloj.Relojes) -> None:\n    from app import push\n\n    persona = db.get(m.Persona, baja["persona_id"])\n    persona.activo = False\n    persona.baja_odoo_en = ahora\n    deuda = accesos.viaticos_sin_cerrar(db, persona.id)\n    usuario = db.query(m.Usuario).filter_by(persona_id=persona.id).first()\n    # Con `activo` en falso la sesion abierta muere en el siguiente clic:\n    # usuario_actual lo revisa en cada peticion.\n    if usuario is not None and not deuda:\n        usuario.activo = False\n\n    extra = (f" Tiene {len(deuda)} viatico(s) sin cerrar." if deuda else "")\n    avisados = set()\n    for asignacion in dias_por_delante(db, persona.id, relojes):\n        db.add(m.Alerta(\n            jornada_id=asignacion.jornada_id,\n            tipo=m.TipoAlerta.PERSONAL_DE_BAJA, persona_id=persona.id,\n            mensaje=(f"{persona.nombre} fue dado de baja en Odoo y esta "\n                     "asignado a este dia: hay que reemplazarlo." + extra)[:400]))\n        servicio = asignacion.jornada.equipo.servicio\n        if servicio.consultor_id and servicio.id not in avisados:\n            avisados.add(servicio.id)\n            try:\n                push.avisar(\n                    db, servicio.consultor_id,\n                    titulo=f"{servicio.folio}: {persona.nombre} ya no esta "\n                           "en la empresa",\n                    cuerpo=(f"Estaba asignado el "\n                            f"{asignacion.jornada.fecha:%d/%m}. Hay que "\n                            "reemplazarlo."),\n                    # El consultor trabaja en la consola, no en la app de\n                    # campo.\n                    url=f"/consola/#/servicio/{servicio.id}",\n                    etiqueta=f"baja-{persona.id}-{servicio.id}")\n            except Exception:                         # noqa: BLE001\n                # Un aviso que no sale no frena la baja: la alerta de la\n                # central ya quedo.\n                registro.exception("no se pudo avisar la baja de %s",\n                                   persona.nombre)\n\n\ndef _contar_fotos(odoo, ids: list) -> tuple:\n    """(filas leidas, cuantas son foto de verdad). Una sola lectura."""\n    if not ids:\n        return [], 0\n    filas = odoo.leer("hr.employee", [["id", "in", ids]], ["image_128"])\n    return filas, sum(1 for f in filas if reglas.foto_de(f.get("image_128")))\n\n\ndef sincronizar(db: Session, odoo, ensayo: bool = True,\n                quien: m.Usuario | None = None,\n                automatica: bool = False) -> dict:\n    """Lee el personal de Odoo y, si no es ensayo, lo guarda.\n\n    Devuelve el informe: altas, vinculadas, cambios, bajas, accesos que se\n    cierran, pendientes y fotos. El ensayo lo devuelve igual, sin tocar\n    nada: lee de Odoo lo mismo, fotos incluidas, para que las cuentas\n    sean las de verdad.\n    """\n    ahora = _utc()\n    relojes = reloj.Relojes(db)\n    empleados = odoo.leer("hr.employee", [], CAMPOS)\n    plazas, personas, correos = _fotos_fijas(db)\n    plan = reglas.planear(\n        empleados, personas, plazas, correos,\n        lambda numero, pais_id: telefonos.normalizar(db, numero, pais_id))\n\n    estados = {}\n    if plan["revisar_salida"]:\n        estados = {f["id"]: f for f in odoo.leer(\n            "hr.employee",\n            [["id", "in", [p["odoo_id"] for p in plan["revisar_salida"]]]],\n            ["active"], archivados=True)}\n    bajas, pendientes_de_salida = reglas.clasificar_salidas(\n        plan["revisar_salida"], estados)\n    plan["pendientes"].extend(pendientes_de_salida)\n    for baja in bajas:\n        deuda = accesos.viaticos_sin_cerrar(db, baja["persona_id"])\n        baja["dias_por_delante"] = len(\n            dias_por_delante(db, baja["persona_id"], relojes))\n        baja["viaticos_sin_cerrar"] = len(deuda)\n        baja["acceso"] = ("sigue abierto hasta que compruebe sus viaticos"\n                          if deuda else "se cierra")\n    por_cerrar = _accesos_por_cerrar(db)\n    filas_de_foto, reales = _contar_fotos(odoo, plan["fotos"])\n\n    informe = {\n        "ensayo": ensayo,\n        "leidos": plan["leidos"],\n        "altas": [{k: a[k] for k in ("odoo_id", "nombre", "plaza", "correo")}\n                  for a in plan["altas"]],\n        "vinculadas": plan["vinculos"],\n        "cambios": [{k: c[k] for k in ("persona_id", "odoo_id", "nombre", "que")}\n                    for c in plan["cambios"]],\n        "bajas": bajas,\n        "accesos_cerrados": [{"persona_id": p.id, "nombre": p.nombre}\n                             for p, _ in por_cerrar],\n        "pendientes": plan["pendientes"],\n        "sin_cambio": plan["sin_cambio"],\n        # «sin_foto_real»: Odoo solo tiene el circulo con sus iniciales.\n        "fotos": {"revisadas": len(filas_de_foto), "reales": reales,\n                  "sin_foto_real": len(filas_de_foto) - reales,\n                  "actualizadas": 0},\n    }\n    if ensayo:\n        return informe\n\n    # ------------------------------------------------------------ aplicar\n    usados = {u.correo.strip().lower() for u in db.query(m.Usuario).all()\n              if u.correo}\n    for alta in plan["altas"]:\n        persona = m.Persona(\n            nombre=alta["nombre"], correo=alta["correo"],\n            plaza_id=alta["plaza_id"], odoo_id=alta["odoo_id"], activo=True,\n            es_freelance=False, telefono=alta["telefono"],\n            referencia=alta["referencia"], fecha_ingreso=alta["fecha_ingreso"],\n            odoo_sincronizado_en=ahora)\n        db.add(persona)\n        db.flush()\n        db.add(m.Usuario(persona_id=persona.id, correo=alta["correo"],\n                         rol=m.Rol.PERSONAL_SEGURIDAD, activo=True))\n        usados.add(alta["correo"])\n\n    for vinculo in plan["vinculos"]:\n        db.get(m.Persona, vinculo["persona_id"]).odoo_id = vinculo["odoo_id"]\n\n    usuarios = {u.persona_id: u for u in db.query(m.Usuario).all()}\n    for cambio in plan["cambios"]:\n        persona = db.get(m.Persona, cambio["persona_id"])\n        for campo, valor in cambio["valores"].items():\n            setattr(persona, campo, valor)\n            if campo == "correo" and cambio["persona_id"] in usuarios:\n                usuarios[cambio["persona_id"]].correo = valor\n                usados.add(valor)\n\n    for persona_id in plan["procesadas"]:\n        persona = db.get(m.Persona, persona_id)\n        persona.odoo_sincronizado_en = ahora\n        persona.baja_odoo_en = None\n        # Quien ya estaba en Centauro sin acceso a la app lo recibe, igual\n        # que un alta: sin contrasena, con el codigo que le dictan.\n        correo = (persona.correo or "").strip().lower()\n        if persona_id not in usuarios and correo and correo not in usados:\n            db.add(m.Usuario(persona_id=persona_id, correo=persona.correo,\n                             rol=m.Rol.PERSONAL_SEGURIDAD, activo=True))\n            usados.add(correo)\n    db.flush()\n\n    # Las fotos ya se leyeron arriba, una sola vez y solo de quien toca.\n    if filas_de_foto:\n        por_odoo = {p.odoo_id: p for p in db.query(m.Persona).filter(\n            m.Persona.odoo_id.in_(plan["fotos"])).all()}\n        for fila in filas_de_foto:\n            persona = por_odoo.get(fila["id"])\n            foto = reglas.foto_de(fila.get("image_128"))\n            if persona is not None and foto and foto != persona.foto_url:\n                persona.foto_url = foto\n                informe["fotos"]["actualizadas"] += 1\n\n    for baja in bajas:\n        _dar_de_baja(db, baja, ahora, relojes)\n    for _, usuario in por_cerrar:\n        usuario.activo = False\n\n    hubo_algo = (plan["altas"] or plan["vinculos"] or plan["cambios"] or bajas\n                 or por_cerrar or informe["fotos"]["actualizadas"])\n    fila = m.SincronizacionOdoo(\n        tipo=TIPO, automatica=automatica,\n        hecha_por_id=quien.persona_id if quien else None,\n        leidos=plan["leidos"], altas=len(plan["altas"]),\n        cambios=len(plan["cambios"]) + len(plan["vinculos"]),\n        bajas=len(bajas), pendientes=len(plan["pendientes"]),\n        # La de cada hora sin novedades deja su renglon --se sabe que\n        # corrio-- pero no el detalle, que seria el mismo cada hora.\n        detalle=(json.dumps(informe, ensure_ascii=False, default=str)\n                 if hubo_algo or not automatica else None))\n    db.add(fila)\n    db.flush()\n    if quien is not None:\n        accesos.anotar(\n            db, quien, "personal leido de odoo", "sincronizacion_odoo",\n            fila.id, despues=(f"{len(plan[\'altas\'])} altas, "\n                              f"{len(plan[\'cambios\']) + len(plan[\'vinculos\'])} "\n                              f"cambios, {len(bajas)} bajas, "\n                              f"{len(plan[\'pendientes\'])} pendientes"))\n    db.commit()\n    return informe\n\n\ndef resumen(informe: dict) -> dict:\n    """Solo cuentas: para la terminal y para la tarea de cada hora."""\n    faltas = {}\n    for p in informe["pendientes"]:\n        for falta in p["falta"]:\n            clave = "plaza no existe" if falta.startswith("la plaza") else falta\n            faltas[clave] = faltas.get(clave, 0) + 1\n    return {"leidos": informe["leidos"], "altas": len(informe["altas"]),\n            "vinculadas": len(informe["vinculadas"]),\n            "cambios": len(informe["cambios"]), "bajas": len(informe["bajas"]),\n            "accesos_cerrados": len(informe["accesos_cerrados"]),\n            "sin_cambio": informe["sin_cambio"],\n            "pendientes": faltas, "fotos": informe["fotos"]}\n\n\ndef sincronizar_si_toca(db: Session, odoo=None) -> dict:\n    """La tarea de cada hora. No arranca sola: espera a que alguien haya\n    hecho la primera sincronizacion a mano, despues de ver el ensayo."""\n    from app import odoo_api\n\n    primera = (db.query(m.SincronizacionOdoo)\n               .filter_by(tipo=TIPO, automatica=False).first())\n    if primera is None:\n        return {"omitido": "falta la primera sincronizacion a mano"}\n    if odoo is None:\n        if not odoo_api.hay_conexion():\n            return {"omitido": "Odoo no esta conectado"}\n        odoo = odoo_api.cliente()\n    try:\n        return resumen(sincronizar(db, odoo, ensayo=False, automatica=True))\n    except odoo_api.NoResponde as error:\n        # Lo mas probable a los tres meses: la llave vencio. Queda en el\n        # registro del worker y la siguiente hora lo vuelve a intentar.\n        db.rollback()\n        registro.warning("odoo no respondio al leer el personal: %s", error)\n        return {"error": str(error)}\n',
    'migrations/versions/b7d2f4a9c1e3_personal_desde_odoo.py': '"""El personal de seguridad, leido de Odoo.\n\nCentauro lee de Odoo al personal de seguridad (seccion 51 de la\nbitacora): cuatro columnas en la persona --referencia, fecha de ingreso,\ncuando se leyo de Odoo y cuando Odoo la dio de baja--, la foto pasa a\ntexto largo porque llega como data URI, un tipo de alerta nuevo para la\ncentral y la tabla donde queda cada lectura.\n\nRevision ID: b7d2f4a9c1e3\nRevises: a1c4e7b9d2f6\n"""\nfrom typing import Sequence, Union\n\nimport sqlalchemy as sa\nfrom alembic import op\n\nrevision: str = "b7d2f4a9c1e3"\ndown_revision: Union[str, None] = "a1c4e7b9d2f6"\nbranch_labels: Union[str, Sequence[str], None] = None\ndepends_on: Union[str, Sequence[str], None] = None\n\n\ndef upgrade() -> None:\n    op.alter_column("persona", "foto_url", type_=sa.Text(),\n                    existing_type=sa.String(length=400), existing_nullable=True)\n    op.add_column("persona", sa.Column("referencia", sa.String(length=40),\n                                       nullable=True))\n    op.create_index("ix_persona_referencia", "persona", ["referencia"])\n    op.add_column("persona", sa.Column("fecha_ingreso", sa.Date(),\n                                       nullable=True))\n    op.add_column("persona", sa.Column("odoo_sincronizado_en", sa.DateTime(),\n                                       nullable=True))\n    op.add_column("persona", sa.Column("baja_odoo_en", sa.DateTime(),\n                                       nullable=True))\n    op.execute("ALTER TYPE tipoalerta ADD VALUE IF NOT EXISTS "\n               "\'PERSONAL_DE_BAJA\' AFTER \'VEHICULO_SIN_ASIGNAR\'")\n    op.create_table(\n        "sincronizacion_odoo",\n        sa.Column("id", sa.Integer(), primary_key=True),\n        sa.Column("tipo", sa.String(length=20), nullable=False),\n        sa.Column("hecha_en", sa.DateTime(timezone=True),\n                  server_default=sa.text("now()"), nullable=False),\n        sa.Column("automatica", sa.Boolean(), server_default="false",\n                  nullable=False),\n        sa.Column("hecha_por_id", sa.Integer(), sa.ForeignKey("persona.id"),\n                  nullable=True),\n        sa.Column("leidos", sa.Integer(), server_default="0", nullable=False),\n        sa.Column("altas", sa.Integer(), server_default="0", nullable=False),\n        sa.Column("cambios", sa.Integer(), server_default="0", nullable=False),\n        sa.Column("bajas", sa.Integer(), server_default="0", nullable=False),\n        sa.Column("pendientes", sa.Integer(), server_default="0",\n                  nullable=False),\n        sa.Column("detalle", sa.Text(), nullable=True),\n    )\n    op.create_index("ix_sincronizacion_odoo_tipo", "sincronizacion_odoo",\n                    ["tipo"])\n\n\ndef downgrade() -> None:\n    op.drop_index("ix_sincronizacion_odoo_tipo",\n                  table_name="sincronizacion_odoo")\n    op.drop_table("sincronizacion_odoo")\n    # Postgres no deja quitar un valor de un enum: las alertas de baja se\n    # borran y el valor se queda en el tipo, sin uso.\n    op.execute("DELETE FROM alerta WHERE tipo = \'PERSONAL_DE_BAJA\'")\n    op.drop_column("persona", "baja_odoo_en")\n    op.drop_column("persona", "odoo_sincronizado_en")\n    op.drop_column("persona", "fecha_ingreso")\n    op.drop_index("ix_persona_referencia", table_name="persona")\n    op.drop_column("persona", "referencia")\n    # Una foto de Odoo no cabe en 400 caracteres: se quitan antes de\n    # regresar la columna a su tamano.\n    op.execute("UPDATE persona SET foto_url = NULL "\n               "WHERE length(foto_url) > 400")\n    op.alter_column("persona", "foto_url", type_=sa.String(length=400),\n                    existing_type=sa.Text(), existing_nullable=True)\n',
    'tests/test_odoo_personal.py': '# -*- coding: utf-8 -*-\n"""El personal de seguridad, leido de Odoo (seccion 51 de la bitacora).\n\nContra un Odoo de mentiras, en memoria: ninguna prueba sale a la red.\nImita lo que importa del de verdad: sin `archivados` no devuelve a los\narchivados, y a quien no tiene foto le da el circulo de iniciales, que\nes un SVG y no una foto.\n"""\nfrom datetime import date, datetime, timedelta, timezone\n\nimport pytest\nfrom sqlalchemy import text\n\nfrom ayudas import asignar, crear_servicio, jornada, manana\nfrom app import models as m\nfrom app import odoo_api, odoo_personal\n\nODOO0 = 7_000_000\nDOMINIO = "prueba-odoo.lat"\nPNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9Q"\n       "DwADhgGAWjR9awAAAABJRU5ErkJggg==")\nSVG = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciLz4="\n\n\nclass OdooFalso:\n    def __init__(self, *empleados, fotos=None):\n        self.empleados = {e["id"]: e for e in empleados}\n        self.fotos = dict(fotos or {})\n        self.lecturas = []\n\n    def leer(self, modelo, dominio, campos, archivados=False):\n        assert modelo == "hr.employee"\n        self.lecturas.append(list(campos))\n        filas = [e for e in self.empleados.values()\n                 if archivados or e.get("active", True)]\n        for campo, operador, valor in dominio:\n            assert (campo, operador) == ("id", "in")\n            filas = [e for e in filas if e["id"] in valor]\n        salida = []\n        for e in filas:\n            fila = {"id": e["id"]}\n            for c in campos:\n                fila[c] = (self.fotos.get(e["id"], SVG) if c == "image_128"\n                           else e.get(c, False))\n            salida.append(fila)\n        return salida\n\n    def cambiar(self, n, **valores):\n        self.empleados[ODOO0 + n].update(valores)\n\n    def archivar(self, n):\n        self.cambiar(n, active=False)\n\n\nclass OdooCaido:\n    def leer(self, *args, **kwargs):\n        raise odoo_api.NoResponde("Odoo rechazo la llave; puede que haya vencido.")\n\n\ndef empleado(n, **cambios):\n    e = {"id": ODOO0 + n, "name": f"Agente Odoo {n}",\n         "job_id": [90, "Personal de Seguridad"],\n         "job_title": "Personal de Seguridad",\n         "work_location_id": [30, "Ciudad de México"],\n         "work_email": f"agente{n}@{DOMINIO}", "private_email": False,\n         "mobile_phone": f"55 5000 {n:04d}", "registration_number": f"PO-{n}",\n         "first_contract_date": "2024-03-01",\n         "write_date": "2026-01-01 10:00:00", "active": True}\n    e.update(cambios)\n    return e\n\n\n@pytest.fixture\ndef db():\n    from app.db import SessionLocal\n\n    sesion = SessionLocal()\n    yield sesion\n    sesion.close()\n\n\n@pytest.fixture(autouse=True)\ndef sin_rastro(base_de_pruebas):\n    """Lo que estas pruebas dan de alta se va al terminar.\n\n    La persona y su acceso son catalogo: no se vacian entre pruebas. Sin\n    esto, la persona de una prueba seguiria «leida de Odoo» en la\n    siguiente, y la siguiente la daria de baja por no venir en su Odoo.\n    """\n    yield\n    from conftest import TABLAS_DE_OPERACION\n    from app.seed import sembrar_recursos\n\n    with base_de_pruebas.begin() as con:\n        con.execute(text(f"TRUNCATE {\', \'.join(TABLAS_DE_OPERACION)} "\n                         "RESTART IDENTITY CASCADE"))\n        ids = [f[0] for f in con.execute(text(\n            "SELECT id FROM persona WHERE odoo_id >= :o OR correo LIKE :d"),\n            {"o": ODOO0, "d": f"%@{DOMINIO}"})]\n        if ids:\n            con.execute(text(\n                "DELETE FROM invitacion WHERE usuario_id IN "\n                "(SELECT id FROM usuario WHERE persona_id = ANY(:ids))"),\n                {"ids": ids})\n            con.execute(text("DELETE FROM usuario WHERE persona_id = ANY(:ids)"),\n                        {"ids": ids})\n            con.execute(text("DELETE FROM persona WHERE id = ANY(:ids)"),\n                        {"ids": ids})\n    sembrar_recursos()\n\n\ndef leer(db, odoo, ensayo=False, **kwargs):\n    # Como en produccion, donde cada lectura abre su propia sesion: se lee\n    # la base como esta, no lo que esta sesion trae en memoria de antes.\n    # Sin esto, la baja que la consola hizo por su lado no se veia.\n    db.expire_all()\n    return odoo_personal.sincronizar(db, odoo, ensayo=ensayo, **kwargs)\n\n\ndef persona(db, n):\n    db.expire_all()\n    return db.query(m.Persona).filter_by(odoo_id=ODOO0 + n).one()\n\n\ndef de_prueba(db):\n    db.expire_all()\n    return db.query(m.Persona).filter(m.Persona.odoo_id >= ODOO0).count()\n\n\ndef alerta_de_baja(db, jornada_id):\n    return (db.query(m.Alerta)\n            .filter_by(jornada_id=jornada_id,\n                       tipo=m.TipoAlerta.PERSONAL_DE_BAJA).one())\n\n\ndef en_un_servicio(cliente, sesion, datos, persona_id):\n    """Lo asigna a un dia de un servicio de Ana, dentro de tres dias."""\n    h = sesion("consultor")\n    servicio = crear_servicio(\n        cliente, h, datos,\n        [jornada(manana(3), datos["modalidades"]["full_day"]["id"])],\n        consultor_id=datos["personal"]["Ana Solis"]["id"])\n    j = servicio["equipos"][0]["jornadas"][0]\n    r = asignar(cliente, h, j["id"], persona_id=persona_id)[0]\n    assert r.status_code == 200, r.text\n    return j\n\n\n# ================================================================ altas\n\ndef test_el_ensayo_dice_que_haria_y_no_guarda_nada(db):\n    odoo = OdooFalso(empleado(1), empleado(2), fotos={ODOO0 + 1: PNG})\n    informe = leer(db, odoo, ensayo=True)\n    assert informe["ensayo"] is True\n    assert [a["odoo_id"] - ODOO0 for a in informe["altas"]] == [1, 2]\n    # Lee las fotos para que la cuenta sea la de verdad, pero no guarda.\n    assert informe["fotos"] == {"revisadas": 2, "reales": 1,\n                                "sin_foto_real": 1, "actualizadas": 0}\n    assert de_prueba(db) == 0\n    assert db.query(m.SincronizacionOdoo).count() == 0\n\n\ndef test_el_alta_trae_a_la_persona_y_su_acceso_sin_contrasena(db):\n    informe = leer(db, OdooFalso(empleado(1), fotos={ODOO0 + 1: PNG}))\n    assert len(informe["altas"]) == 1 and not informe["pendientes"]\n    p = persona(db, 1)\n    assert (p.nombre, p.correo) == ("Agente Odoo 1", f"agente1@{DOMINIO}")\n    assert p.plaza.nombre == "Ciudad de Mexico"\n    assert p.telefono == "+52 55 5000 0001"\n    assert (p.referencia, p.fecha_ingreso) == ("PO-1", date(2024, 3, 1))\n    assert p.foto_url == "data:image/png;base64," + PNG\n    assert p.activo and p.odoo_sincronizado_en is not None\n    usuario = db.query(m.Usuario).filter_by(persona_id=p.id).one()\n    assert usuario.rol == m.Rol.PERSONAL_SEGURIDAD and usuario.activo\n    assert usuario.correo == p.correo\n    # Entra con el codigo que le dicta su consultor o la central.\n    assert usuario.hash_contrasena is None\n    fila = db.query(m.SincronizacionOdoo).one()\n    assert (fila.altas, fila.automatica, fila.hecha_por_id) == (1, False, None)\n\n\ndef test_la_segunda_lectura_no_cambia_nada(db):\n    odoo = OdooFalso(empleado(1), empleado(2))\n    leer(db, odoo)\n    informe = leer(db, odoo)\n    assert not (informe["altas"] or informe["cambios"] or informe["bajas"])\n    assert informe["sin_cambio"] == 2\n    # Si Odoo no toco la ficha, la foto no se vuelve a pedir.\n    assert informe["fotos"]["revisadas"] == 0\n    assert odoo.lecturas.count(["image_128"]) == 1\n\n\ndef test_solo_entra_el_personal_de_seguridad(db):\n    informe = leer(db, OdooFalso(\n        empleado(1),\n        empleado(2, job_id=False,\n                 job_title="Security Driver (Protección Ejecutiva)"),\n        empleado(3, job_id=False, job_title=" PERSONAL DE  SEGURIDAD GDL"),\n        empleado(4, job_id=[91, "Monitorista Bilingüe"],\n                 job_title="Monitorista Bilingüe"),\n        empleado(5, job_id=False, job_title="Guardia de Seguridad"),\n        empleado(6, job_id=False, job_title=False)))\n    assert informe["leidos"] == 3\n    assert sorted(a["odoo_id"] - ODOO0 for a in informe["altas"]) == [1, 2, 3]\n    assert de_prueba(db) == 3\n\n\ndef test_lo_dudoso_queda_pendiente_y_no_se_toca(db):\n    informe = leer(db, OdooFalso(\n        empleado(1, work_location_id=False),\n        empleado(2, work_location_id=[31, "Home"]),\n        empleado(3, work_email="agente3@gamil.com"),\n        empleado(4, work_email=f"repetido@{DOMINIO}"),\n        empleado(5, work_email=f"repetido@{DOMINIO}"),\n        empleado(6, work_email=False, private_email=False)))\n    assert not informe["altas"]\n    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}\n    assert faltas == {\n        1: ["sin plaza"],\n        2: ["la plaza «Home» no existe en Centauro"],\n        3: ["correo con error de dedo"],\n        4: ["correo repetido en Odoo"],\n        5: ["correo repetido en Odoo"],\n        6: ["sin correo"],\n    }\n    assert de_prueba(db) == 0\n\n\ndef test_el_estado_de_mexico_va_como_ciudad_de_mexico(db):\n    leer(db, OdooFalso(\n        empleado(1, work_location_id=[32, "Estado de México"]),\n        empleado(2, work_location_id=[33, "Guadalajara"])))\n    assert persona(db, 1).plaza.nombre == "Ciudad de Mexico"\n    assert persona(db, 2).plaza.nombre == "Guadalajara"\n\n\n# ================================================================ cambios\n\ndef test_lo_que_cambia_en_odoo_cambia_aqui_y_lo_vacio_no_borra(db):\n    odoo = OdooFalso(empleado(1))\n    leer(db, odoo)\n    odoo.cambiar(1, name="Agente Odoo Uno", work_email=f"uno@{DOMINIO}",\n                 work_location_id=[33, "Guadalajara"],\n                 mobile_phone="33 1111 2222")\n    informe = leer(db, odoo)\n    assert informe["cambios"][0]["que"] == ["nombre", "plaza", "celular",\n                                            "correo"]\n    p = persona(db, 1)\n    assert (p.nombre, p.plaza.nombre, p.telefono, p.correo) == (\n        "Agente Odoo Uno", "Guadalajara", "+52 33 1111 2222",\n        f"uno@{DOMINIO}")\n    # El acceso sigue a la persona: entra con su correo nuevo.\n    assert (db.query(m.Usuario).filter_by(persona_id=p.id).one().correo\n            == f"uno@{DOMINIO}")\n\n    odoo.cambiar(1, mobile_phone=False, registration_number=False)\n    assert not leer(db, odoo)["cambios"]\n    p = persona(db, 1)\n    assert (p.telefono, p.referencia) == ("+52 33 1111 2222", "PO-1")\n\n\ndef test_quien_ya_estaba_en_centauro_se_vincula_por_su_correo(\n        cliente, sesion, datos, db):\n    h = sesion("admin")\n    r = cliente.post("/catalogos/personal", headers=h, json={\n        "nombre": "Capturado A Mano", "correo": f"agente1@{DOMINIO}",\n        "plaza_id": datos["cdmx"]["id"]})\n    assert r.status_code == 201, r.text\n    alta = cliente.post("/auth/usuarios", headers=h, json={\n        "persona_id": r.json()["id"], "rol": "personal_seguridad"})\n    assert alta.status_code == 201, alta.text\n\n    informe = leer(db, OdooFalso(empleado(1)))\n    assert not informe["altas"]\n    assert [v["persona_id"] for v in informe["vinculadas"]] == [r.json()["id"]]\n    p = persona(db, 1)\n    # La misma persona, con lo que dice Odoo, y un solo acceso.\n    assert (p.id, p.nombre) == (r.json()["id"], "Agente Odoo 1")\n    assert db.query(m.Usuario).filter_by(persona_id=p.id).count() == 1\n\n\ndef test_el_circulo_de_iniciales_no_es_foto_y_la_foto_nueva_se_toma(db):\n    odoo = OdooFalso(empleado(1))\n    informe = leer(db, odoo)\n    assert informe["fotos"]["sin_foto_real"] == 1\n    assert persona(db, 1).foto_url is None\n\n    # RH le sube una foto: Odoo mueve el write_date de la ficha.\n    despues = datetime.now(timezone.utc) + timedelta(minutes=5)\n    odoo.fotos[ODOO0 + 1] = PNG\n    odoo.cambiar(1, write_date=despues.strftime("%Y-%m-%d %H:%M:%S"))\n    assert leer(db, odoo)["fotos"]["actualizadas"] == 1\n    assert persona(db, 1).foto_url == "data:image/png;base64," + PNG\n\n\n# ================================================================ bajas\n\ndef test_la_baja_en_odoo_cierra_el_acceso_y_avisa_a_la_central(\n        cliente, sesion, datos, db):\n    odoo = OdooFalso(empleado(1), empleado(2))\n    leer(db, odoo)\n    p = persona(db, 1)\n    j = en_un_servicio(cliente, sesion, datos, p.id)\n\n    odoo.archivar(1)\n    informe = leer(db, odoo)\n    assert [(b["odoo_id"] - ODOO0, b["motivo"], b["dias_por_delante"],\n             b["acceso"]) for b in informe["bajas"]] == [\n        (1, "archivado en Odoo", 1, "se cierra")]\n    p = persona(db, 1)\n    assert not p.activo and p.baja_odoo_en is not None\n    assert not db.query(m.Usuario).filter_by(persona_id=p.id).one().activo\n    assert alerta_de_baja(db, j["id"]).persona_id == p.id\n    assert persona(db, 2).activo\n\n\ndef test_quien_debe_viaticos_conserva_el_acceso_hasta_comprobarlos(\n        cliente, sesion, datos, db):\n    odoo = OdooFalso(empleado(1))\n    leer(db, odoo)\n    p = persona(db, 1)\n    j = en_un_servicio(cliente, sesion, datos, p.id)\n    viatico = (db.query(m.AsignacionViatico)\n               .filter_by(jornada_id=j["id"], persona_id=p.id).first())\n    if viatico is None:\n        viatico = m.AsignacionViatico(\n            jornada_id=j["id"], persona_id=p.id, moneda=m.Moneda.MXN,\n            escenario=m.EscenarioViatico.FULL_DAY_LOCAL)\n        db.add(viatico)\n    viatico.monto_total = 1500\n    viatico.estatus = m.EstatusViatico.TRANSFERIDO\n    db.commit()\n\n    odoo.archivar(1)\n    baja = leer(db, odoo)["bajas"][0]\n    assert baja["viaticos_sin_cerrar"] == 1\n    assert baja["acceso"] == "sigue abierto hasta que compruebe sus viaticos"\n    assert not persona(db, 1).activo\n    assert db.query(m.Usuario).filter_by(persona_id=p.id).one().activo\n    assert "viatico" in alerta_de_baja(db, j["id"]).mensaje\n\n    # Comprueba, y en la siguiente lectura el acceso se cierra solo.\n    viatico.estatus = m.EstatusViatico.CERRADO\n    db.commit()\n    assert [a["persona_id"] for a in leer(db, odoo)["accesos_cerrados"]] == [p.id]\n    db.expire_all()\n    assert not db.query(m.Usuario).filter_by(persona_id=p.id).one().activo\n    assert not leer(db, odoo)["accesos_cerrados"]\n\n\ndef test_quien_desaparece_de_odoo_tambien_se_da_de_baja(db):\n    odoo = OdooFalso(empleado(1))\n    leer(db, odoo)\n    del odoo.empleados[ODOO0 + 1]\n    assert [b["motivo"] for b in leer(db, odoo)["bajas"]] == ["ya no esta en Odoo"]\n    assert not persona(db, 1).activo\n\n\ndef test_quien_cambia_de_puesto_queda_pendiente_sin_baja(db):\n    odoo = OdooFalso(empleado(1))\n    leer(db, odoo)\n    odoo.cambiar(1, job_id=[91, "Monitorista Bilingüe"],\n                 job_title="Monitorista Bilingüe")\n    informe = leer(db, odoo)\n    assert not informe["bajas"]\n    assert informe["pendientes"][0]["falta"] == [\n        "ya no tiene puesto de seguridad en Odoo"]\n    assert persona(db, 1).activo\n\n\ndef test_de_baja_en_centauro_y_activo_en_odoo_se_reactiva_a_mano(\n        cliente, sesion, db):\n    odoo = OdooFalso(empleado(1))\n    leer(db, odoo)\n    p = persona(db, 1)\n    assert cliente.delete(f"/catalogos/personal/{p.id}",\n                          headers=sesion("admin")).status_code == 204\n    informe = leer(db, odoo)\n    assert informe["pendientes"][0]["falta"] == [\n        "activo en Odoo pero dado de baja en Centauro: reactivar a mano"]\n    assert not persona(db, 1).activo\n\n\n# ================================================================ la tarea\n\ndef test_la_tarea_de_cada_hora_espera_la_primera_a_mano(db):\n    odoo = OdooFalso(empleado(1))\n    assert odoo_personal.sincronizar_si_toca(db, odoo) == {\n        "omitido": "falta la primera sincronizacion a mano"}\n    assert not odoo.lecturas\n    leer(db, odoo, ensayo=True)            # el ensayo no cuenta\n    assert "omitido" in odoo_personal.sincronizar_si_toca(db, odoo)\n\n    leer(db, odoo)                         # la primera, a mano\n    odoo.empleados[ODOO0 + 2] = empleado(2)\n    r = odoo_personal.sincronizar_si_toca(db, odoo)\n    assert (r["leidos"], r["altas"]) == (2, 1)\n    fila = db.query(m.SincronizacionOdoo).filter_by(automatica=True).one()\n    assert fila.altas == 1 and fila.detalle\n\n    # Una hora sin novedades deja su renglon, sin el detalle.\n    odoo_personal.sincronizar_si_toca(db, odoo)\n    ultima = (db.query(m.SincronizacionOdoo)\n              .order_by(m.SincronizacionOdoo.id.desc()).first())\n    assert ultima.automatica and ultima.detalle is None\n\n\ndef test_la_tarea_de_cada_hora_no_truena_si_odoo_no_contesta(db):\n    leer(db, OdooFalso(empleado(1)))\n    r = odoo_personal.sincronizar_si_toca(db, OdooCaido())\n    assert "vencido" in r["error"]\n\n\n# ================================================================ la consola\n\ndef test_lo_que_viene_de_odoo_no_se_edita_en_el_catalogo(\n        cliente, sesion, db):\n    leer(db, OdooFalso(empleado(1)))\n    p = persona(db, 1)\n    h = sesion("admin")\n    cuerpo = {"nombre": p.nombre, "correo": p.correo, "plaza_id": p.plaza_id}\n    r = cliente.patch(f"/catalogos/personal/{p.id}", headers=h,\n                      json={**cuerpo, "nombre": "Otro Nombre"})\n    assert r.status_code == 409, r.text\n    assert "Odoo" in r.json()["detail"]["mensaje"]\n    # Lo que es de Centauro si se edita, y la ficha trae lo de Odoo.\n    r = cliente.patch(f"/catalogos/personal/{p.id}", headers=h,\n                      json={**cuerpo, "es_freelance": False})\n    assert r.status_code == 200, r.text\n    assert (r.json()["referencia"], r.json()["fecha_ingreso"]) == (\n        "PO-1", "2024-03-01")\n\n\ndef test_el_buscador_del_codigo_encuentra_por_numero_de_empleado(\n        cliente, sesion, db):\n    leer(db, OdooFalso(empleado(7)))\n    p = persona(db, 7)\n    h = sesion("central")\n    filas = cliente.get("/auth/campo/buscar?q=po-7", headers=h).json()\n    assert [f["persona_id"] for f in filas] == [p.id]\n    assert filas[0]["referencia"] == "PO-7"\n    # El numero va completo: un pedazo no trae a nadie por numero.\n    filas = cliente.get("/auth/campo/buscar?q=po-", headers=h).json()\n    assert p.id not in [f["persona_id"] for f in filas]\n\n\ndef test_las_rutas_son_de_administracion(cliente, sesion, monkeypatch, db):\n    from app.config import settings\n\n    monkeypatch.setattr(settings, "odoo_base", "")\n    monkeypatch.setattr(settings, "odoo_api_key", "")\n    assert cliente.get("/odoo/personal/ensayo",\n                       headers=sesion("consultor")).status_code == 403\n    r = cliente.get("/odoo/personal/ensayo", headers=sesion("admin"))\n    assert r.status_code == 503, r.text\n    assert "no esta conectado" in r.json()["detail"]["mensaje"]\n\n    odoo = OdooFalso(empleado(1))\n    monkeypatch.setattr(odoo_api, "cliente", lambda: odoo)\n    r = cliente.get("/odoo/personal/ensayo", headers=sesion("admin"))\n    assert r.status_code == 200 and r.json()["ensayo"] is True\n    assert de_prueba(db) == 0\n    r = cliente.post("/odoo/personal/sincronizar", headers=sesion("admin"))\n    assert r.status_code == 200 and len(r.json()["altas"]) == 1\n    admin = db.query(m.Usuario).filter_by(correo="admin@centauro.lat").one()\n    assert db.query(m.SincronizacionOdoo).one().hecha_por_id == admin.persona_id\n    assert db.query(m.RegistroAdmin).filter_by(\n        objeto="sincronizacion_odoo").count() == 1\n\n\ndef test_si_odoo_no_contesta_se_dice_claro(cliente, sesion, monkeypatch):\n    monkeypatch.setattr(odoo_api, "cliente", lambda: OdooCaido())\n    r = cliente.post("/odoo/personal/sincronizar", headers=sesion("admin"))\n    assert r.status_code == 502, r.text\n    assert "vencido" in r.json()["detail"]["mensaje"]\n\n\ndef test_la_conexion_no_escribe_en_odoo():\n    odoo = odoo_api.Odoo("https://odoo.invalid", "llave")\n    for metodo in ("write", "create", "unlink"):\n        with pytest.raises(RuntimeError):\n            odoo.llamar("hr.employee", metodo, ids=[1], vals={})\n',
    'sincronizar_personal.py': '# -*- coding: utf-8 -*-\n"""Leer el personal de seguridad de Odoo, desde la terminal.\n\nLo mismo que la consola hace con «ensayo» y «sincronizar», para la\nprimera vez y para cuando se quiera ver sin abrir el navegador. Desde la\nraiz del proyecto:\n\n    docker compose run --rm api python sincronizar_personal.py\n    docker compose run --rm api python sincronizar_personal.py --aplicar\n\nSin --aplicar es un ensayo: lee Odoo, dice que haria y no guarda nada.\nNunca escribe en Odoo.\n\nEn la terminal solo salen cuentas. El detalle, con nombres, queda en\nodoo_personal_ultimo.json junto a este archivo; no va a git.\n"""\nimport json\nimport sys\nfrom pathlib import Path\n\nfrom app import odoo_api, odoo_personal\nfrom app.db import SessionLocal\n\nDETALLE = Path(__file__).resolve().with_name("odoo_personal_ultimo.json")\n\n\ndef main(argv: list) -> int:\n    aplicar = "--aplicar" in argv\n    try:\n        odoo = odoo_api.cliente()\n    except odoo_api.SinConexion:\n        print("Falta ODOO_BASE u ODOO_API_KEY en el .env.")\n        return 1\n\n    db = SessionLocal()\n    try:\n        informe = odoo_personal.sincronizar(db, odoo, ensayo=not aplicar)\n    except odoo_api.NoResponde as error:\n        print(f"Odoo no respondio: {error}")\n        return 2\n    finally:\n        db.close()\n\n    DETALLE.write_text(json.dumps(informe, ensure_ascii=False, indent=2,\n                                  default=str), encoding="utf-8")\n    r = odoo_personal.resumen(informe)\n    fotos = r["fotos"]\n    print("Aplicado: quedo guardado en Centauro." if aplicar\n          else "ENSAYO: no se guardo nada.")\n    print(f"Personal de seguridad en Odoo: {r[\'leidos\']}")\n    print(f"Altas: {r[\'altas\']} · vinculadas: {r[\'vinculadas\']} · "\n          f"con cambios: {r[\'cambios\']} · sin cambio: {r[\'sin_cambio\']}")\n    print(f"Bajas: {r[\'bajas\']} · accesos que se cierran: "\n          f"{r[\'accesos_cerrados\']}")\n    print(f"Fotos revisadas: {fotos[\'revisadas\']} · de verdad: "\n          f"{fotos[\'reales\']} · solo iniciales: {fotos[\'sin_foto_real\']}"\n          + (f" · guardadas: {fotos[\'actualizadas\']}" if aplicar else ""))\n    if r["pendientes"]:\n        print("Pendientes, por motivo:")\n        for motivo, cuantos in sorted(r["pendientes"].items(),\n                                      key=lambda x: -x[1]):\n            print(f"  {cuantos:>3}  {motivo}")\n    else:\n        print("Pendientes: ninguno")\n    print(f"El detalle, con nombres, quedo en {DETALLE.name} (no va a git).")\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main(sys.argv[1:]))\n',
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
        "    # Para el task sheet: la foto y el telefono vienen de Odoo.\n"
        "    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)\n"
        "    foto_url: Mapped[str | None] = mapped_column(String(400), nullable=True)\n",
        "    # Para el task sheet: la foto y el telefono vienen de Odoo. La foto\n"
        "    # llega como data URI --la de 128 px de Odoo, unos KB-- y se guarda\n"
        "    # dentro del registro como las demas imagenes del sistema: por eso es\n"
        "    # texto largo y no los 400 caracteres de cuando se penso como enlace.\n"
        "    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)\n"
        "    foto_url: Mapped[str | None] = mapped_column(Text, nullable=True)\n"
        "    # Lo demas que llega de Odoo (seccion 51). La referencia es el numero\n"
        "    # de empleado de RH: con el se le busca para dictarle su codigo, y es\n"
        "    # algo mas que preguntarle por telefono.\n"
        "    referencia: Mapped[str | None] = mapped_column(String(40), nullable=True,\n"
        "                                                   index=True)\n"
        "    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True)\n"
        "    # Cuando se leyo de Odoo por ultima vez y cuando Odoo la dio de baja,\n"
        "    # en UTC y sin zona, como el write_date de Odoo con el que se compara.\n"
        "    # La baja se queda anotada para cerrarle el acceso en cuanto\n"
        "    # compruebe sus viaticos, si se fue debiendo.\n"
        "    odoo_sincronizado_en: Mapped[datetime | None] = mapped_column(\n"
        "        DateTime, nullable=True)\n"
        "    baja_odoo_en: Mapped[datetime | None] = mapped_column(DateTime,\n"
        "                                                          nullable=True)\n",
        marca="    odoo_sincronizado_en: Mapped[datetime | None]")

cambiar("models",
        "    plaza: Mapped[Plaza] = relationship()\n"
        "\n"
        "\n"
        "class TarifaFreelance(Base):\n",
        "    plaza: Mapped[Plaza] = relationship()\n"
        "\n"
        "\n"
        "class SincronizacionOdoo(Base):\n"
        "    \"\"\"Cada lectura de Odoo: cuando, quien y que cambio.\n"
        "\n"
        "    La de cada hora espera a que exista una hecha a mano: la primera\n"
        "    vez alguien mira el ensayo y decide. `detalle` guarda el informe\n"
        "    completo --con nombres--; la de cada hora sin novedades deja su\n"
        "    renglon sin repetirlo.\n"
        "    \"\"\"\n"
        "    __tablename__ = \"sincronizacion_odoo\"\n"
        "\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        "    tipo: Mapped[str] = mapped_column(String(20), index=True)   # personal\n"
        "    hecha_en: Mapped[datetime] = mapped_column(\n"
        "        DateTime(timezone=True), server_default=func.now())\n"
        "    automatica: Mapped[bool] = mapped_column(Boolean, default=False,\n"
        "                                             server_default=\"false\")\n"
        "    hecha_por_id: Mapped[int | None] = mapped_column(\n"
        "        ForeignKey(\"persona.id\"), nullable=True)\n"
        "    leidos: Mapped[int] = mapped_column(Integer, default=0, server_default=\"0\")\n"
        "    altas: Mapped[int] = mapped_column(Integer, default=0, server_default=\"0\")\n"
        "    cambios: Mapped[int] = mapped_column(Integer, default=0, server_default=\"0\")\n"
        "    bajas: Mapped[int] = mapped_column(Integer, default=0, server_default=\"0\")\n"
        "    pendientes: Mapped[int] = mapped_column(Integer, default=0,\n"
        "                                            server_default=\"0\")\n"
        "    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)\n"
        "\n"
        "\n"
        "class TarifaFreelance(Base):\n",
        marca="class SincronizacionOdoo(Base):")

cambiar("models",
        "    VEHICULO_SIN_ASIGNAR = \"vehiculo_sin_asignar\"\n",
        "    VEHICULO_SIN_ASIGNAR = \"vehiculo_sin_asignar\"\n"
        "    # Odoo archivo a alguien que tenia dias asignados (seccion 51): hay\n"
        "    # que reemplazarlo.\n"
        "    PERSONAL_DE_BAJA = \"personal_de_baja\"\n",
        marca="PERSONAL_DE_BAJA = ")

# ================================================================ config
cambiar("config",
        "    # Lo que entra de Odoo --personal, flota, capacitaciones, taller--\n"
        "    # llega por sus propias rutas y no necesita nada de esto; esto es\n"
        "    # para lo que Centauro le manda.\n",
        "    # Lo que Odoo manda --flota, capacitaciones, taller-- llega por sus\n"
        "    # propias rutas y no necesita nada de esto; esto es para lo que\n"
        "    # Centauro le manda. El personal ya no espera a que se lo manden: se\n"
        "    # lee (abajo, `odoo_base`).\n")

cambiar("config",
        "    odoo_timeout: int = 20\n",
        "    odoo_timeout: int = 20\n"
        "\n"
        "    # Odoo, del lado de ENTRADA (seccion 51): Centauro lee de ahi al\n"
        "    # personal de seguridad cada hora, por la API JSON-2. Solo lee.\n"
        "    # `odoo_api_key` es la llave del usuario de la conexion --no la de una\n"
        "    # persona-- y Odoo la da por tres meses como maximo. Vacio = no se lee\n"
        "    # nada. `odoo_bd` solo hace falta si el servidor tiene varias bases.\n"
        "    odoo_base: str = \"\"            # \"https://centauro.odoo.com\"\n"
        "    odoo_api_key: str = \"\"\n"
        "    odoo_bd: str = \"\"\n",
        marca="    odoo_api_key: str = ")

# ================================================================ rutas de Odoo
cambiar("rodoo",
        "los muestre sin depender de que Odoo responda en ese momento.\n"
        "\"\"\"\n",
        "los muestre sin depender de que Odoo responda en ese momento.\n"
        "\n"
        "El personal de seguridad ya no espera a que se lo manden: Centauro lo lee\n"
        "de Odoo (seccion 51). `/personal/ensayo` dice que haria sin guardar nada\n"
        "y `/personal/sincronizar` lo guarda; despues lo sigue leyendo solo, cada\n"
        "hora. `POST /personal` se queda para quien todavia lo mande.\n"
        "\"\"\"\n",
        marca="El personal de seguridad ya no espera a que se lo manden")
cambiar("rodoo",
        "from fastapi import APIRouter, Depends\n",
        "from fastapi import APIRouter, Depends, HTTPException\n")
cambiar("rodoo",
        "from app import odoo, schemas as s\n",
        "from app import odoo, odoo_api, odoo_personal, schemas as s\n")
cambiar("rodoo",
        "    return odoo.sincronizar_taller(\n"
        "        db, [e.model_dump(exclude_none=True) for e in entradas])\n",
        "    return odoo.sincronizar_taller(\n"
        "        db, [e.model_dump(exclude_none=True) for e in entradas])\n"
        "\n"
        "\n"
        "# ------------------------------------------------ el personal, leido de Odoo\n"
        "\n"
        "def _conexion():\n"
        "    \"\"\"El cliente de Odoo, o un 503 que dice que falta.\"\"\"\n"
        "    try:\n"
        "        return odoo_api.cliente()\n"
        "    except odoo_api.SinConexion:\n"
        "        raise HTTPException(503, {\n"
        "            \"mensaje\": \"Odoo no esta conectado en este servidor.\",\n"
        "            \"que_hacer\": \"Falta ODOO_BASE y ODOO_API_KEY en el .env del \"\n"
        "                         \"servidor.\",\n"
        "        })\n"
        "\n"
        "\n"
        "def _leer_personal(db: Session, ensayo: bool, quien: m.Usuario) -> dict:\n"
        "    cliente = _conexion()\n"
        "    try:\n"
        "        return odoo_personal.sincronizar(db, cliente, ensayo=ensayo,\n"
        "                                         quien=None if ensayo else quien)\n"
        "    except odoo_api.NoResponde as error:\n"
        "        raise HTTPException(502, {\n"
        "            \"mensaje\": str(error),\n"
        "            \"que_hacer\": \"Si Odoo rechazo la llave, hay que crear una nueva \"\n"
        "                         \"en Odoo y ponerla en el .env del servidor.\",\n"
        "        })\n"
        "\n"
        "\n"
        "@router.get(\"/personal/ensayo\",\n"
        "            summary=\"Que cambiaria al leer el personal de Odoo, sin guardar\")\n"
        "def personal_ensayo(db: Session = Depends(get_db),\n"
        "                    usuario: m.Usuario = Depends(requiere(m.Rol.ADMIN))):\n"
        "    \"\"\"Lee Odoo y dice que haria: altas, cambios, bajas y pendientes.\n"
        "    No guarda nada, ni aqui ni en Odoo.\"\"\"\n"
        "    return _leer_personal(db, True, usuario)\n"
        "\n"
        "\n"
        "@router.post(\"/personal/sincronizar\",\n"
        "             summary=\"Leer el personal de Odoo y guardarlo\")\n"
        "def personal_sincronizar(db: Session = Depends(get_db),\n"
        "                         usuario: m.Usuario = Depends(requiere(m.Rol.ADMIN))):\n"
        "    \"\"\"Lo mismo que el ensayo, guardado. La primera vez se hace a mano,\n"
        "    despues de ver el ensayo; de ahi en adelante se lee solo cada hora.\"\"\"\n"
        "    return _leer_personal(db, False, usuario)\n",
        marca="def personal_sincronizar(")

# ================================================================ la tarea
cambiar("celery",
        "            \"schedule\": crontab(day_of_month=\"3\", hour=5, minute=0),\n"
        "        },\n",
        "            \"schedule\": crontab(day_of_month=\"3\", hour=5, minute=0),\n"
        "        },\n"
        "        # El personal de seguridad, leido de Odoo (seccion 51). Cada hora,\n"
        "        # a los 17 minutos para no caer junto con las de la hora en punto.\n"
        "        # No arranca sola: espera a que alguien haya hecho la primera\n"
        "        # lectura a mano, despues de ver el ensayo.\n"
        "        \"odoo-personal\": {\n"
        "            \"task\": \"odoo.sincronizar_personal\",\n"
        "            \"schedule\": crontab(minute=17),\n"
        "        },\n",
        marca="\"odoo-personal\": {")
cambiar("celery",
        "        return {\"movidos\": cierre.avanzar_cierres(db)}\n"
        "    finally:\n"
        "        db.close()\n",
        "        return {\"movidos\": cierre.avanzar_cierres(db)}\n"
        "    finally:\n"
        "        db.close()\n"
        "\n"
        "\n"
        "@celery.task(name=\"odoo.sincronizar_personal\")\n"
        "def sincronizar_personal_de_odoo():\n"
        "    \"\"\"El personal de seguridad, leido de Odoo.\"\"\"\n"
        "    from app.db import SessionLocal\n"
        "    from app import odoo_personal\n"
        "\n"
        "    db = SessionLocal()\n"
        "    try:\n"
        "        return odoo_personal.sincronizar_si_toca(db)\n"
        "    finally:\n"
        "        db.close()\n",
        marca="def sincronizar_personal_de_odoo(")

# ================================================================ el codigo de campo
cambiar("contrasenas",
        "from sqlalchemy.orm import Session\n",
        "from sqlalchemy import or_\n"
        "from sqlalchemy.orm import Session\n",
        marca="from sqlalchemy import or_\n")
cambiar("contrasenas",
        "    La foto y el telefono no son adorno: como no hay numero de empleado,\n"
        "    la voz es lo unico que verifica, y esto le da al consultor algo mas\n"
        "    que preguntar --\"de que numero me llamas\"--.\n",
        "    La foto, el telefono y el numero de empleado no son adorno: le dan al\n"
        "    consultor algo mas que la voz para saber con quien habla --\"de que\n"
        "    numero me llamas\", \"cual es tu numero de empleado\"-- y la foto de\n"
        "    Odoo para verle la cara.\n")
cambiar("contrasenas",
        "        \"foto\": persona.foto_url,\n",
        "        \"foto\": persona.foto_url,\n"
        "        \"referencia\": persona.referencia,\n")
cambiar("contrasenas",
        "    \"\"\"El buscador de la pantalla del codigo.\n",
        "    \"\"\"El buscador de la pantalla del codigo: por nombre o por el numero\n"
        "    de empleado de Odoo, completo.\n")
cambiar("contrasenas",
        "                     m.Persona.nombre.ilike(f\"%{q}%\"))\n",
        "                     or_(m.Persona.nombre.ilike(f\"%{q}%\"),\n"
        "                         # El numero de empleado, completo: un pedazo\n"
        "                         # de numero traeria a medio padron.\n"
        "                         m.Persona.referencia.ilike(q)))\n")

# ================================================================ el catalogo
cambiar("crud",
        "            raise HTTPException(404, f\"No existe el registro {item_id}\")\n"
        "\n"
        "        # Se apunta solo lo que de verdad cambio, con su valor viejo al\n",
        "            raise HTTPException(404, f\"No existe el registro {item_id}\")\n"
        "\n"
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
        "                                 \"siguiente lectura.\",\n"
        "                    \"campos\": tocados,\n"
        "                })\n"
        "\n"
        "        # Se apunta solo lo que de verdad cambio, con su valor viejo al\n",
        marca="Viene de Odoo: se corrige en Odoo.")

cambiar("schemas",
        "    telefono: str | None = None\n"
        "    foto_url: str | None = None\n"
        "\n"
        "\n"
        "class TarifaFreelanceIn(Base):\n",
        "    telefono: str | None = None\n"
        "    foto_url: str | None = None\n"
        "    # Tambien de Odoo (seccion 51): el numero de empleado y desde cuando\n"
        "    # esta en la empresa.\n"
        "    referencia: str | None = None\n"
        "    fecha_ingreso: date | None = None\n"
        "\n"
        "\n"
        "class TarifaFreelanceIn(Base):\n",
        marca="    fecha_ingreso: date | None = None\n")

# ================================================================ de paso
cambiar("cierre",
        "                url=f\"/servicios/{servicio.id}\",\n",
        "                # El consultor trabaja en la consola, no en la app de campo.\n"
        "                url=f\"/consola/#/servicio/{servicio.id}\",\n")

# ================================================================ pantallas
for viejo, nuevo in (
        ("    bit_alerta_vehiculo_sin_asignar: \"Unidad sin asignar\",\n",
         "    bit_alerta_personal_de_baja: \"Dado de baja en Odoo\",\n"),
        ("    bit_alerta_vehiculo_sin_asignar: \"No vehicle assigned\",\n",
         "    bit_alerta_personal_de_baja: \"Terminated in Odoo\",\n"),
        ("    bit_alerta_vehiculo_sin_asignar: \"Sem unidade designada\",\n",
         "    bit_alerta_personal_de_baja: \"Desligado no Odoo\",\n"),
        ("    cod_sin_estrenar: \"Nunca ha entrado\",\n",
         "    cod_referencia: \"No. de empleado {s}\",\n"),
        ("    cod_sin_estrenar: \"Never signed in\",\n",
         "    cod_referencia: \"Employee no. {s}\",\n"),
        ("    cod_sin_estrenar: \"Nunca entrou\",\n",
         "    cod_referencia: \"Nº de funcionário {s}\",\n")):
    cambiar("idioma", viejo, viejo + nuevo, marca=nuevo)
for viejo, nuevo in (
        ("    cod_buscar: \"Escribe su nombre\",\n",
         "    cod_buscar: \"Escribe su nombre o su número de empleado\",\n"),
        ("    cod_buscar: \"Type their name\",\n",
         "    cod_buscar: \"Type their name or employee number\",\n"),
        ("    cod_buscar: \"Escreva o nome\",\n",
         "    cod_buscar: \"Escreva o nome ou o número de funcionário\",\n"),
        ("    cod_nadie: \"Nadie con ese nombre entre tu gente.\",\n",
         "    cod_nadie: \"Nadie con ese nombre o número entre tu gente.\",\n"),
        ("    cod_nadie: \"Nobody by that name among your people.\",\n",
         "    cod_nadie: \"Nobody by that name or number among your people.\",\n"),
        ("    cod_nadie: \"Ninguém com esse nome entre a sua gente.\",\n",
         "    cod_nadie: \"Ninguém com esse nome ou número entre a sua gente.\",\n")):
    cambiar("idioma", viejo, nuevo)

cambiar("codigo",
        "/* La foto y el telefono no son adorno: como no hay numero de empleado, la\n"
        "   voz es lo unico que verifica, y esto le da al consultor algo mas que\n"
        "   preguntar --\"de que numero me llamas\"--. El renglon de donde esta hoy\n"
        "   tambien verifica: si dice que entra a las seis y el sistema no le ve\n"
        "   nada hoy, algo no cuadra. */\n",
        "/* La foto, el telefono y el numero de empleado no son adorno: le dan al\n"
        "   consultor algo mas que la voz para saber con quien habla --\"de que\n"
        "   numero me llamas\", \"cual es tu numero de empleado\"-- y la foto de Odoo\n"
        "   para verle la cara. El renglon de donde esta hoy tambien verifica: si\n"
        "   dice que entra a las seis y el sistema no le ve nada hoy, algo no\n"
        "   cuadra. */\n")
cambiar("codigo",
        "      h(\"h4\", { style: \"margin:0 0 1px\" }, p.nombre),\n"
        "      h(\"div\", { clase: \"chico gris\" }, p.telefono || \"—\"),\n",
        "      h(\"h4\", { style: \"margin:0 0 1px\" }, p.nombre),\n"
        "      p.referencia ? h(\"div\", { clase: \"chico gris\" },\n"
        "        t(\"cod_referencia\").replace(\"{s}\", p.referencia)) : \"\",\n"
        "      h(\"div\", { clase: \"chico gris\" }, p.telefono || \"—\"),\n")
cambiar("codigo",
        "    h(\"h3\", { style: \"margin:0 0 8px\" }, p.nombre),\n"
        "    h(\"div\", { clase: \"chico\" }, p.telefono || \"—\"),\n",
        "    h(\"h3\", { style: \"margin:0 0 8px\" }, p.nombre),\n"
        "    p.referencia ? h(\"div\", { clase: \"chico\" },\n"
        "      t(\"cod_referencia\").replace(\"{s}\", p.referencia)) : \"\",\n"
        "    h(\"div\", { clase: \"chico\" }, p.telefono || \"—\"),\n")

# ================================================================ pruebas
cambiar("conftest",
        "    # que revisa el padron vacio los encontraba llenos.\n"
        "    \"capacitacion\",\n",
        "    # que revisa el padron vacio los encontraba llenos.\n"
        "    \"capacitacion\",\n"
        "    # Cada lectura de Odoo deja su renglon, y la tarea de cada hora espera\n"
        "    # a que exista uno hecho a mano: sin vaciarlo, la prueba que revisa\n"
        "    # esa espera encontraria el de la prueba anterior.\n"
        "    \"sincronizacion_odoo\",\n",
        marca="    \"sincronizacion_odoo\",\n")

# ================================================================ la hoja de RH
cambiar("hoja",
        "                  \"yaho.com\", \"yahoo.con\", \"outlok.com\", \"outlook.con\"}\n",
        "                  \"yaho.com\", \"yahoo.con\", \"outlok.com\", \"outlook.con\"}\n"
        "# Como empieza en base64 una foto de verdad: PNG, JPEG, GIF o WEBP. El\n"
        "# circulo con iniciales que Odoo le pone a quien no tiene foto es un SVG,\n"
        "# y no cuenta.\n"
        "FOTOS = (\"iVBOR\", \"/9j/\", \"R0lGOD\", \"UklGR\")\n",
        marca="FOTOS = (")
cambiar("hoja",
        "        foto = bool(e.get(\"image_128\"))\n",
        "        foto = texto(e.get(\"image_128\")).startswith(FOTOS)\n")
cambiar("hoja",
        "        (\"5. La foto no va en esta hoja: se sube en Odoo, en la ficha de la persona.\", False),\n",
        "        (\"5. La foto no va en esta hoja: se sube en Odoo, en la ficha de la persona. \"\n"
        "         \"El círculo con iniciales no es foto.\", False),\n")

# ================================================================ repo y despliegue
cambiar("gitignore",
        "backend/Personal_de_seguridad_para_RH_*.xlsx\n",
        "backend/Personal_de_seguridad_para_RH_*.xlsx\n"
        "\n"
        "# El detalle de la ultima lectura del personal de Odoo: lleva nombres.\n"
        "backend/odoo_personal_ultimo.json\n",
        marca="backend/odoo_personal_ultimo.json\n")

cambiar("leeme",
        "ODOO_URL=\n"
        "ODOO_TOKEN=\n",
        "ODOO_URL=\n"
        "ODOO_TOKEN=\n"
        "\n"
        "# Odoo, de entrada: Centauro lee de ahi al personal de seguridad cada\n"
        "# hora, y solo lee. La llave es la del usuario «Centauro (conexion)»,\n"
        "# no la de una persona, y Odoo la da por tres meses como maximo.\n"
        "ODOO_BASE=https://centauro.odoo.com\n"
        "ODOO_API_KEY=\n",
        marca="ODOO_API_KEY=\n")
cambiar("leeme",
        "servidor, y en ningún otro lado.\n",
        "servidor, y en ningún otro lado.\n"
        "\n"
        "**La conexión con Odoo.** El usuario «Centauro (conexión)» se crea en\n"
        "Odoo con permiso de *Empleados: Oficial* —para leer el correo personal\n"
        "y la referencia— y ocupa una licencia. Su llave se genera en su perfil\n"
        "→ *Seguridad de la cuenta* → *Claves API*, con el vencimiento más largo\n"
        "que Odoo permita (tres meses). **Anota el día que vence**: ese día la\n"
        "lectura se detiene y el registro del worker dice «Odoo rechazó la\n"
        "llave». La nueva se pega aquí y se reinician `api`, `worker` y `beat`.\n"
        "\n"
        "La primera lectura del personal se hace a mano, después de ver el\n"
        "ensayo; la tarea de cada hora no arranca hasta que exista esa primera:\n"
        "\n"
        "```bash\n"
        "docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py\n"
        "docker compose -f docker-compose.prod.yml run --rm api python sincronizar_personal.py --aplicar\n"
        "```\n",
        marca="**La conexión con Odoo.**")

cambiar("bitacora",
        "- **La baja en Odoo no cierra el acceso.** `odoo.sincronizar_personal`\n",
        "- ~~**La baja en Odoo no cierra el acceso.**~~ **Cerrado el 23 de\n"
        "  septiembre**, sección 51: Centauro lee el personal de Odoo y la baja\n"
        "  llega sola. *(Lo de abajo es el texto de entonces.)*\n"
        "  `odoo.sincronizar_personal`\n",
        marca="sección 51: Centauro lee el personal de Odoo")
cambiar("bitacora",
        "## 14. Lo que falta\n",
        "## 51. El personal, leído de Odoo\n"
        "\n"
        "Decisión de Salvador, 23 de septiembre: etapa 1 de la conexión con Odoo.\n"
        "Odoo es el maestro de empleados; Centauro deja de capturar a su gente y\n"
        "la lee de ahí.\n"
        "\n"
        "- **Quién entra.** El personal de seguridad: puesto «Personal de\n"
        "  Seguridad» (con los de GDL) o «Security Driver». Monitoristas,\n"
        "  oficina y guardias no. La llave es el número interno de Odoo; quien\n"
        "  ya estaba en Centauro se vincula por su correo la primera vez.\n"
        "- **Qué manda Odoo.** Nombre, plaza —la ubicación de trabajo; el Estado\n"
        "  de México va como Ciudad de México—, celular, correo, referencia de\n"
        "  empleado, fecha de ingreso y foto. En el catálogo ya no se editan: se\n"
        "  corrigen en Odoo. Un campo vacío en Odoo no borra el de Centauro. Lo\n"
        "  de la operación —a qué servicio va, con qué rol, sus viáticos— sigue\n"
        "  siendo de Centauro. Los datos del banco no se leen todavía.\n"
        "- **La foto** llega como imagen dentro del registro. El círculo con\n"
        "  iniciales que Odoo le pone a quien no tiene foto no es foto: no se\n"
        "  guarda y el informe lo cuenta aparte. Se vuelve a pedir solo cuando\n"
        "  Odoo toca la ficha.\n"
        "- **Alta**: la persona y su acceso a la app, sin contraseña; entra con\n"
        "  el código de cuatro dígitos que le dictan. El buscador de esa\n"
        "  pantalla ya encuentra por número de empleado, completo, y lo muestra\n"
        "  junto a la foto.\n"
        "- **Baja**: si Odoo la archiva, en la siguiente lectura deja de estar\n"
        "  disponible, se le cierra el acceso, la central recibe una alerta\n"
        "  *dado de baja en Odoo* en cada día que tenía por delante y su\n"
        "  consultor un aviso al teléfono. Si debe viáticos, el acceso sigue\n"
        "  abierto solo para comprobarlos y se cierra solo en cuanto no deba\n"
        "  nada: la regla del panel de accesos.\n"
        "- **Lo dudoso no se adivina**: sin plaza, plaza que no existe, correo\n"
        "  con error de dedo o repetido, cambio de puesto, o activo en Odoo y de\n"
        "  baja en Centauro quedan como *pendientes* y no se tocan.\n"
        "- **Cómo se lee.** Por la API JSON-2 de Odoo 19, con un cliente que\n"
        "  solo sabe leer. `GET /odoo/personal/ensayo` dice qué haría sin\n"
        "  guardar nada; `POST /odoo/personal/sincronizar` lo guarda;\n"
        "  `sincronizar_personal.py` hace lo mismo desde la terminal, con solo\n"
        "  cuentas en pantalla. La tarea `odoo.sincronizar_personal` lee cada\n"
        "  hora, pero no arranca hasta que exista una lectura hecha a mano. Cada\n"
        "  lectura queda en `sincronizacion_odoo`.\n"
        "- **La llave** es la del usuario «Centauro (conexión)», no la de una\n"
        "  persona, y dura tres meses como máximo (`despliegue/LEEME.md`).\n"
        "\n"
        "De paso: el aviso del visto bueno llevaba al consultor a una dirección\n"
        "que no existía (`/servicios/…`); ahora abre el servicio en la consola.\n"
        "\n"
        "Pendiente: la pantalla del ensayo en la consola; después la flotilla,\n"
        "las cotizaciones y la factura en borrador, en ese orden.\n"
        "\n"
        "## 14. Lo que falta\n",
        marca="## 51. El personal, leído de Odoo\n")

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

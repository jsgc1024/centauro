# -*- coding: utf-8 -*-
"""Reconocimiento de Odoo, de SOLO LECTURA.

Responde desde el propio Odoo las preguntas de ODOO_LO_QUE_NECESITAMOS.md
en vez de esperar a que alguien las conteste a mano: que campos existen,
cuantos empleados tienen correo, que sedes y puestos hay, como vienen las
placas, de donde sale el taller, como son las cotizaciones y las facturas.

Lo que NO hace, y esta amarrado en el codigo:
  * No escribe nada. Solo llama metodos de lectura (ver PERMITIDOS); si
    alguien le agrega otro, truena antes de salir a la red.
  * No imprime la llave, ni nombres, correos, telefonos o sueldos de
    nadie. Solo campos, conteos y catalogos: sedes, puestos, productos,
    diarios, impuestos.

Se corre desde la raiz del proyecto:

    docker compose run --rm api python reconocer_odoo.py

Lee ODOO_BASE y ODOO_API_KEY del .env (y ODOO_BD, solo si Odoo la pide).
El detalle completo queda en backend/reconocimiento_odoo.txt, que no va a
git; en la terminal sale solo el resumen.
"""
import collections
import os
import re
import sys
from datetime import datetime

import httpx

# Lo unico que este script puede pedirle a Odoo.
PERMITIDOS = {"search_read", "search_count", "fields_get", "read"}

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "reconocimiento_odoo.txt")
TOPE = 20000          # registros por lectura: sobra para una empresa como esta


class LlaveInvalida(Exception):
    """La llave no sirve o ya vencio: no tiene caso seguir."""


class Odoo:
    def __init__(self, base: str, llave: str, bd: str | None = None):
        base = base.strip().rstrip("/")
        if not base.startswith("http"):
            base = "https://" + base
        self.base = base
        cabeceras = {"Authorization": f"bearer {llave}",
                     "Content-Type": "application/json; charset=utf-8",
                     "User-Agent": "centauro-reconocimiento/1.0"}
        if bd:
            cabeceras["X-Odoo-Database"] = bd
        self.http = httpx.Client(headers=cabeceras, timeout=60)
        self.idioma = "en_US"
        self.llamadas = 0
        self.fallas = []

    def llamar(self, modelo: str, metodo: str, **args):
        if metodo not in PERMITIDOS:
            raise RuntimeError(f"{metodo} no es de solo lectura")
        contexto = args.pop("context", {})
        cuerpo = {"context": {"lang": self.idioma, **contexto}, **args}
        self.llamadas += 1
        r = self.http.post(f"{self.base}/json/2/{modelo}/{metodo}",
                           json=cuerpo)
        if r.status_code == 200:
            return r.json()
        try:
            error = r.json()
            mensaje = error.get("message") or error.get("name") or r.text
        except ValueError:
            mensaje = r.text
        mensaje = " ".join(str(mensaje).split())[:200]
        if r.status_code == 401:
            raise LlaveInvalida(mensaje)
        raise RuntimeError(f"{r.status_code}: {mensaje}")

    def pedir(self, modelo: str, metodo: str, **args):
        """Como `llamar`, pero una falla se anota y devuelve None: que un
        modulo no este instalado no puede tumbar el reconocimiento."""
        try:
            return self.llamar(modelo, metodo, **args)
        except LlaveInvalida:
            raise
        except (RuntimeError, httpx.HTTPError) as error:
            self.fallas.append(f"{modelo}.{metodo}: {error}")
            return None

    def campos(self, modelo: str) -> dict | None:
        return self.pedir(modelo, "fields_get",
                          attributes=["string", "type", "relation",
                                      "selection", "store"])

    def contar(self, modelo: str, dominio: list) -> int | None:
        return self.pedir(modelo, "search_count", domain=dominio)

    def leer(self, modelo: str, dominio: list, campos: list,
             limite: int = TOPE, orden: str = "id") -> list | None:
        return self.pedir(modelo, "search_read", domain=dominio,
                          fields=campos, limit=limite, order=orden)


# ------------------------------------------------------------------ ayudas

def nombre(valor) -> str | None:
    """El nombre de un many2one, venga como [id, nombre], dict o id."""
    if not valor:
        return None
    if isinstance(valor, (list, tuple)) and len(valor) > 1:
        return str(valor[1])
    if isinstance(valor, dict):
        return str(valor.get("display_name") or valor.get("name")
                   or valor.get("id"))
    return str(valor)


def reparto(filas: list, campo: str, vacio: str = "(vacio)") -> list:
    cuenta = collections.Counter(nombre(f.get(campo)) or vacio
                                 for f in filas)
    return cuenta.most_common()


def rango(filas: list, campo: str) -> str:
    fechas = sorted(str(f[campo])[:10] for f in filas if f.get(campo))
    return f"{fechas[0]} a {fechas[-1]}" if fechas else "sin fechas"


class Reporte:
    def __init__(self):
        self.lineas = []

    def titulo(self, texto: str):
        self.lineas += ["", texto.upper(), "=" * len(texto)]

    def sub(self, texto: str):
        self.lineas += ["", texto, "-" * len(texto)]

    def __call__(self, texto: str = ""):
        self.lineas.append(texto)

    def tabla(self, filas: list, maximo: int = 40, sangria: str = "  "):
        for etiqueta, n in filas[:maximo]:
            self.lineas.append(f"{sangria}{n:>6}  {etiqueta}")
        if len(filas) > maximo:
            self.lineas.append(f"{sangria}   ...  y {len(filas) - maximo} mas")

    def presencia(self, campos: dict | None, lista: list):
        if campos is None:
            self("  (no se pudieron leer los campos)")
            return
        for c in lista:
            if c in campos:
                self(f"  si  {c:<28} {campos[c].get('string', '')}"
                     f"  [{campos[c].get('type', '')}]")
            else:
                self(f"  no  {c}")


def personalizados(campos: dict | None) -> list:
    """Los campos que agrego la empresa (Studio o a mano): x_..."""
    if not campos:
        return []
    return sorted(c for c in campos if c.startswith("x_"))


def describir_personalizados(r: Reporte, odoo: Odoo, modelo: str,
                             campos: dict | None, filas: list | None):
    extra = personalizados(campos)
    if not extra:
        r("  (ninguno)")
        return
    for c in extra:
        info = campos[c]
        tipo = info.get("type")
        r(f"  {c:<34} {info.get('string', '')}  [{tipo}]"
          + (f" -> {info.get('relation')}" if info.get("relation") else ""))
        opciones = info.get("selection")
        if (tipo == "selection" and isinstance(opciones, list) and opciones
                and se_puede_mostrar(c, info, [])):
            etiquetas = [str(o[1]) for o in opciones
                         if isinstance(o, (list, tuple)) and len(o) > 1]
            r("      opciones: " + " | ".join(etiquetas[:25])
              + (" | ..." if len(etiquetas) > 25 else ""))
        if filas is None or tipo in ("binary", "html", "text", "one2many",
                                     "many2many"):
            continue
        valores = [f.get(c) for f in filas if c in f]
        llenos = [v for v in valores if v not in (False, None, "")]
        r(f"      llenos: {len(llenos)} de {len(valores)}")
        if se_puede_mostrar(c, info, llenos):
            # La seleccion se cuenta por su etiqueta, no por la clave interna.
            textos = {str(o[0]): str(o[1]) for o in (info.get("selection") or [])
                      if isinstance(o, (list, tuple)) and len(o) > 1}
            cuenta = collections.Counter(
                nombre(v) if tipo == "many2one" else textos.get(str(v), str(v))
                for v in llenos)
            for etiqueta, n in cuenta.most_common(12):
                r(f"        {n:>5}  {etiqueta}")


# Lo que nunca se imprime, aunque parezca un catalogo: identificaciones,
# datos de contacto, dinero de la persona, salud. Un campo "x_curp" en una
# empresa con ocho empleados pasaria cualquier regla de "pocas variantes".
DELICADO = re.compile(
    r"\b(curp|rfc|nss|ine|imss)\b|pasaporte|passport|ident|clabe|cuenta|"
    r"banco|bank|tarjeta|card|tel[eé]fono|phone|celular|correo|mail|"
    r"direcci[oó]n|address|domicilio|nombre|name|salario|sueldo|salary|"
    r"wage|nacimiento|birth|edad|sangre|blood|alerg|salud|health|m[eé]dic",
    re.IGNORECASE)
PERSONAS = {"res.users", "res.partner", "hr.employee", "hr.employee.public"}
# Un campo cuyo nombre dice que guarda a una persona --"Consultor",
# "Conductor", "Responsable"-- no ensena sus valores aunque sea una
# seleccion: en Studio una seleccion puede ser una lista de nombres.
PERSONA_CAMPO = re.compile(
    r"consultor|conductor|driver|chofer|responsable|asignad|emplead|persona|"
    r"usuario|\buser\b|supervisor|vendedor|agente|escolta|operador|jefe|"
    r"gerente|coordinador|contacto|familia|esposa|mam[aá]|pap[aá]|hij[oa]",
    re.IGNORECASE)


def se_puede_mostrar(campo: str, info: dict, llenos: list) -> bool:
    """Los valores se enseñan solo cuando son un catalogo: una seleccion,
    un si/no, una relacion que no apunta a personas, o un texto corto que
    se repite (un nivel de blindaje, una sede). Nunca texto libre que
    pueda traer un nombre o una identificacion."""
    tipo = info.get("type")
    if PERSONA_CAMPO.search(f"{campo} {info.get('string', '')}"):
        return False
    if tipo in ("selection", "boolean"):
        return True
    if tipo == "many2one":
        return info.get("relation") not in PERSONAS
    if tipo != "char" or DELICADO.search(f"{campo} {info.get('string', '')}"):
        return False
    distintos = {str(v) for v in llenos}
    return (len(distintos) <= 12 and len(distintos) * 2 <= len(llenos)
            and all(len(v) <= 30 for v in distintos))


# ------------------------------------------------------------------ secciones

def conexion(r: Reporte, odoo: Odoo) -> dict:
    r.titulo("Conexion")
    idiomas = odoo.llamar("res.lang", "search_read",
                          domain=[["active", "=", True]],
                          fields=["code", "name"]) or []
    codigos = [i["code"] for i in idiomas]
    for preferido in ("es_MX", "es_419", "es_ES"):
        if preferido in codigos:
            odoo.idioma = preferido
            break
    r(f"  Odoo: {odoo.base}")
    r("  La API respondio con la llave: si")
    r(f"  Idiomas activos: {', '.join(codigos) or '(ninguno)'}")
    r(f"  Etiquetas en: {odoo.idioma}")

    empresas = odoo.leer("res.company", [], ["name", "currency_id",
                                             "country_id"]) or []
    r.sub("Empresas en esta base")
    for e in empresas:
        r(f"  {e['name']}  ·  moneda {nombre(e.get('currency_id'))}"
          f"  ·  {nombre(e.get('country_id')) or 'sin pais'}")

    r.sub("Aplicaciones instaladas")
    apps = odoo.leer("ir.module.module",
                     [["state", "=", "installed"], ["application", "=", True]],
                     ["name", "shortdesc"], orden="name") or []
    for a in apps:
        r(f"  {a['name']:<24} {a.get('shortdesc', '')}")

    r.sub("Modulos que nos importan")
    buscados = ["hr", "hr_skills", "hr_expense", "hr_holidays", "fleet",
                "maintenance", "sale_management", "account",
                "account_accountant", "l10n_mx", "l10n_mx_edi",
                "l10n_br", "l10n_ve", "base_automation", "web_studio",
                "project", "planning", "documents", "sale_subscription",
                "hr_payroll", "approvals"]
    estado = {m["name"]: m["state"] for m in (odoo.leer(
        "ir.module.module", [["name", "in", buscados]],
        ["name", "state"]) or [])}
    for m in buscados:
        marca = "si" if estado.get(m) == "installed" else "no"
        r(f"  {marca}  {m}")
    return {"empresas": len(empresas), "modulos": estado}


def empleados(r: Reporte, odoo: Odoo) -> dict:
    r.titulo("Empleados (hr.employee)")
    campos = odoo.campos("hr.employee")
    if campos is None:
        r("  No se pudo leer el modelo de empleados.")
        return {"existe": False}

    r.sub("Campos que nos importan")
    r.presencia(campos, ["active", "work_email", "private_email",
                         "mobile_phone", "work_phone", "work_location_id",
                         "department_id", "job_id", "job_title",
                         "employee_type", "company_id", "user_id",
                         "image_1920", "departure_date",
                         "departure_reason_id", "first_contract_date",
                         "contract_date_start", "barcode", "pin",
                         "registration_number"])

    r.sub("Campos de fecha (para la antiguedad)")
    for c, info in sorted(campos.items()):
        if info.get("type") in ("date", "datetime"):
            calculado = "" if info.get("store", True) else "  (calculado)"
            r(f"  {c:<30} {info.get('string', '')}{calculado}")

    leidos = ["work_email", "job_title", "work_location_id", "department_id",
              "job_id", "company_id", "user_id", "mobile_phone", "work_phone",
              "private_email", "first_contract_date", "barcode",
              "registration_number"]
    if "employee_type" in campos:
        leidos.append("employee_type")
    extra = personalizados(campos)
    leidos += [c for c in extra if campos[c].get("type") not in (
        "binary", "html", "one2many", "many2many")]
    activos = odoo.leer("hr.employee", [], [c for c in leidos if c in campos])
    archivados = odoo.contar("hr.employee", [["active", "=", False]])
    if activos is None:
        r("  No se pudo leer la lista de empleados.")
        return {"existe": True, "campos": campos}

    r.sub("Cuantos")
    r(f"  Activos:    {len(activos)}")
    r(f"  De baja (archivados): {archivados}")
    con_usuario = sum(1 for e in activos if e.get("user_id"))
    r(f"  Con usuario de Odoo:  {con_usuario}")

    if "employee_type" in campos:
        r.sub("Tipo de empleado")
        r.tabla(reparto(activos, "employee_type"))

    # El correo: sin imprimir ninguno. Cuantos tienen, cuantos se repiten
    # y de que dominios son (centauro.lat contra gmail, por ejemplo).
    correos = [str(e["work_email"]).strip().lower() for e in activos
               if e.get("work_email")]
    repetidos = sum(n - 1 for n in collections.Counter(correos).values()
                    if n > 1)
    dominios = collections.Counter(c.split("@")[-1] for c in correos
                                   if "@" in c)
    r.sub("Correo de trabajo (work_email)")
    r(f"  Con correo:    {len(correos)} de {len(activos)}")
    r(f"  Sin correo:    {len(activos) - len(correos)}")
    r(f"  Repetidos:     {repetidos}")
    r("  Dominios:")
    r.tabla(dominios.most_common(), 10, "    ")

    # Cuantos tienen cada dato, sin ensenar ninguno. Y lo mismo solo del
    # personal operativo, que es el que usa la app y va en el task sheet.
    operativo = re.compile(r"seguridad|driver|guardia|escolta|conductor|"
                           r"custodi|agente", re.IGNORECASE)
    calle = [e for e in activos if operativo.search(str(e.get("job_title")
                                                        or ""))
             and "monitor" not in str(e.get("job_title") or "").lower()]
    r.sub("Quien tiene cada dato (conteo, sin valores)")
    r(f"  {'':<24}{'todos':>8}{'operativos':>12}")
    for c, etiqueta in (("work_email", "correo de trabajo"),
                        ("private_email", "correo personal"),
                        ("mobile_phone", "celular de trabajo"),
                        ("work_phone", "telefono de trabajo"),
                        ("first_contract_date", "fecha primer contrato"),
                        ("barcode", "credencial (barcode)"),
                        ("registration_number", "numero de empleado")):
        if c in campos:
            r(f"  {etiqueta:<24}{sum(1 for e in activos if e.get(c)):>8}"
              f"{sum(1 for e in calle if e.get(c)):>12}")
    r(f"  {'total':<24}{len(activos):>8}{len(calle):>12}")
    r("  (operativos = puesto con seguridad, driver, guardia, escolta,")
    r("   conductor, custodio o agente; sin monitoristas)")

    r.sub("Sede (work_location_id) · empleados por valor")
    r.tabla(reparto(activos, "work_location_id"))
    sedes = odoo.leer("hr.work.location", [], ["name", "location_type"]) or []
    r(f"  Catalogo de sedes en Odoo: {len(sedes)}")
    for s in sedes:
        r(f"    - {s['name']}  ({s.get('location_type') or '-'})")

    r.sub("Departamento · empleados por valor")
    r.tabla(reparto(activos, "department_id"))

    r.sub("Puesto (job_id) · empleados por valor")
    r.tabla(reparto(activos, "job_id"))

    r.sub("Titulo del puesto (job_title, texto libre)")
    r.tabla(reparto(activos, "job_title"), 30)

    if any(e.get("company_id") for e in activos):
        r.sub("Empresa · empleados por valor")
        r.tabla(reparto(activos, "company_id"))

    r.sub("Campos agregados por la empresa (x_)")
    describir_personalizados(r, odoo, "hr.employee", campos, activos)

    # Bajas: con que motivos, sin nombres.
    if "departure_reason_id" in campos and archivados:
        bajas = odoo.leer("hr.employee", [["active", "=", False]],
                          ["departure_reason_id", "departure_date"]) or []
        r.sub("Bajas · motivo")
        r.tabla(reparto(bajas, "departure_reason_id"))
        r(f"  Fechas de baja: {rango(bajas, 'departure_date')}")

    return {"existe": True, "campos": campos, "activos": len(activos),
            "archivados": archivados, "con_correo": len(correos),
            "repetidos": repetidos, "dominios": dominios.most_common(3),
            "sedes_catalogo": len(sedes),
            "con_sede": sum(1 for e in activos if e.get("work_location_id")),
            "con_departamento": sum(1 for e in activos
                                    if e.get("department_id")),
            "con_puesto": sum(1 for e in activos if e.get("job_id")),
            "operativos": len(calle),
            "operativos_con_correo": sum(1 for e in calle
                                         if e.get("work_email")),
            "operativos_con_celular": sum(1 for e in calle
                                          if e.get("mobile_phone"))}


def capacitaciones(r: Reporte, odoo: Odoo) -> dict:
    r.titulo("Cursos y certificaciones (hr_skills)")
    campos = odoo.campos("hr.employee.skill")
    if campos is None:
        r("  El modulo de habilidades no responde (quiza no esta instalado).")
        return {"existe": False}
    r.sub("Campos de la habilidad del empleado")
    r.presencia(campos, ["employee_id", "skill_id", "skill_type_id",
                         "skill_level_id", "valid_from", "valid_to"])
    tipos_campos = odoo.campos("hr.skill.type") or {}
    leer_tipo = ["name"] + (["is_certification"]
                            if "is_certification" in tipos_campos else [])
    tipos = odoo.leer("hr.skill.type", [], leer_tipo) or []
    habilidades = odoo.leer("hr.employee.skill", [], ["skill_type_id"]) or []
    por_tipo = collections.Counter(nombre(h.get("skill_type_id"))
                                   for h in habilidades)
    r.sub("Tipos de habilidad · registros")
    for t in tipos:
        cert = " (certificacion)" if t.get("is_certification") else ""
        r(f"  {por_tipo.get(t['name'], 0):>6}  {t['name']}{cert}")
    lineas = odoo.contar("hr.resume.line", [])
    if lineas is not None:
        r(f"  Renglones de curriculum (hr.resume.line): {lineas}")
    return {"existe": True, "vigencia": "valid_to" in campos,
            "registros": len(habilidades), "tipos": len(tipos)}


def mascara(placa: str) -> str:
    return re.sub(r"[0-9]", "9", re.sub(r"[A-Za-zÑñ]", "A", placa))


def flota(r: Reporte, odoo: Odoo) -> dict:
    r.titulo("Flota (fleet.vehicle)")
    campos = odoo.campos("fleet.vehicle")
    if campos is None:
        r("  No se pudo leer el modelo de vehiculos.")
        return {"existe": False}
    r.sub("Campos que nos importan")
    r.presencia(campos, ["active", "license_plate", "model_id", "brand_id",
                         "category_id", "color", "model_year", "image_128",
                         "location", "driver_id", "state_id", "vehicle_type",
                         "company_id", "vin_sn", "odometer", "tag_ids"])

    leidos = [c for c in ["license_plate", "brand_id", "category_id",
                          "model_id",
                          "model_year", "location", "state_id",
                          "vehicle_type", "color", "company_id"]
              if c in campos]
    extra = personalizados(campos)
    leidos += [c for c in extra if campos[c].get("type") not in (
        "binary", "html", "one2many", "many2many")]
    activos = odoo.leer("fleet.vehicle", [], leidos)
    archivados = odoo.contar("fleet.vehicle", [["active", "=", False]])
    if activos is None:
        r("  No se pudo leer la lista de vehiculos.")
        return {"existe": True}

    r.sub("Cuantos")
    r(f"  Activos: {len(activos)}")
    r(f"  De baja (archivados): {archivados}")

    placas = [str(v["license_plate"]).strip() for v in activos
              if v.get("license_plate")]
    r.sub("Placas · como vienen escritas (A = letra, 9 = numero)")
    r(f"  Con placa: {len(placas)} de {len(activos)}")
    r(f"  Con espacios: {sum(1 for p in placas if ' ' in p)}")
    r(f"  Con guion: {sum(1 for p in placas if '-' in p)}")
    r(f"  Con minusculas: {sum(1 for p in placas if p != p.upper())}")
    r.tabla(collections.Counter(mascara(p) for p in placas).most_common(), 12)

    for campo, titulo in (("brand_id", "Marca"),
                          ("model_id", "Modelo"),
                          ("category_id", "Categoria"),
                          ("state_id", "Estado"),
                          ("vehicle_type", "Tipo"),
                          ("company_id", "Empresa")):
        if campo in leidos:
            r.sub(f"{titulo} · vehiculos por valor")
            r.tabla(reparto(activos, campo), 25)

    if "location" in leidos:
        ubicaciones = reparto(activos, "location")
        r.sub("Ubicacion (location, texto libre)")
        if len(ubicaciones) <= 25 and all(len(u) <= 40 for u, _ in ubicaciones):
            r.tabla(ubicaciones, 25)
        else:
            r(f"  {len(ubicaciones)} valores distintos (no se listan: parece "
              "texto libre)")

    r.sub("Etiquetas de vehiculo")
    etiquetas = odoo.leer("fleet.vehicle.tag", [], ["name"]) or []
    r("  " + (", ".join(e["name"] for e in etiquetas) or "(ninguna)"))

    r.sub("Campos agregados por la empresa (x_)")
    describir_personalizados(r, odoo, "fleet.vehicle", campos, activos)

    # El blindaje: donde sea que viva. Un campo, una categoria o una
    # etiqueta con "blind" en el nombre.
    modelo_campos = odoo.campos("fleet.vehicle.model") or {}
    pistas = []
    for modelo, lista in (("fleet.vehicle", campos),
                          ("fleet.vehicle.model", modelo_campos)):
        for c, info in lista.items():
            texto = f"{c} {info.get('string', '')}".lower()
            if "blind" in texto or "armor" in texto or "armour" in texto:
                pistas.append(f"campo {modelo}.{c} ({info.get('string')})")
    categorias = odoo.leer("fleet.vehicle.model.category", [], ["name"]) or []
    for c in categorias:
        if "blind" in c["name"].lower():
            pistas.append(f"categoria '{c['name']}'")
    for e in etiquetas:
        if "blind" in e["name"].lower():
            pistas.append(f"etiqueta '{e['name']}'")
    for estado, n in reparto(activos, "state_id"):
        if "blind" in estado.lower():
            pistas.append(f"estado '{estado}' ({n} vehiculos)")
    r.sub("El blindaje · donde aparece")
    for p in pistas or ["(en ningun campo, categoria ni etiqueta)"]:
        r(f"  {p}")

    return {"existe": True, "activos": len(activos), "archivados": archivados,
            "con_placa": len(placas),
            "mascaras": collections.Counter(
                mascara(p) for p in placas).most_common(3),
            "blindaje": pistas,
            "con_ubicacion": sum(1 for v in activos if v.get("location"))}


def taller(r: Reporte, odoo: Odoo) -> dict:
    r.titulo("Taller")
    hallazgos = {}

    r.sub("Servicios de flota (fleet.vehicle.log.services)")
    campos = odoo.campos("fleet.vehicle.log.services")
    if campos is not None:
        r.presencia(campos, ["vehicle_id", "service_type_id", "date", "state",
                             "description", "vendor_id", "amount",
                             "odometer"])
        filas = odoo.leer("fleet.vehicle.log.services", [],
                          [c for c in ("service_type_id", "state", "date")
                           if c in campos]) or []
        r(f"  Registros: {len(filas)}  ·  fechas: {rango(filas, 'date')}")
        if "state" in campos:
            r("  Por estado:")
            r.tabla(reparto(filas, "state"), 10, "    ")
        r("  Por tipo de servicio:")
        r.tabla(reparto(filas, "service_type_id"), 20, "    ")
        tipos = odoo.leer("fleet.service.type", [], ["name", "category"]) or []
        r("  Catalogo de tipos de servicio: " + (", ".join(
            f"{x['name']} ({x.get('category')})" for x in tipos) or "(vacio)"))
        r("  Campos agregados por la empresa (x_):")
        describir_personalizados(r, odoo, "fleet.vehicle.log.services",
                                 campos, None)
        hallazgos["servicios"] = len(filas)

    r.sub("Mantenimiento (maintenance.request)")
    campos = odoo.campos("maintenance.request")
    if campos is None:
        r("  No disponible (el modulo de mantenimiento no esta instalado).")
    else:
        r.presencia(campos, ["maintenance_type", "request_date",
                             "schedule_date", "close_date", "stage_id",
                             "equipment_id", "duration"])
        filas = odoo.leer("maintenance.request", [],
                          [c for c in ("maintenance_type", "stage_id",
                                       "schedule_date", "close_date")
                           if c in campos]) or []
        r(f"  Solicitudes: {len(filas)}")
        if "maintenance_type" in campos:
            r("  Preventivo / correctivo:")
            r.tabla(reparto(filas, "maintenance_type"), 5, "    ")
        r("  Por etapa:")
        r.tabla(reparto(filas, "stage_id"), 10, "    ")
        equipos = odoo.contar("maintenance.equipment", [])
        r(f"  Equipos registrados: {equipos}")
        hallazgos["mantenimiento"] = len(filas)
    return hallazgos


def ventas(r: Reporte, odoo: Odoo) -> dict:
    r.titulo("Cotizaciones y pedidos (sale.order)")
    campos = odoo.campos("sale.order")
    if campos is None:
        r("  No se pudo leer ventas (quiza no esta instalado).")
        return {"existe": False}
    r.sub("Campos que nos importan")
    r.presencia(campos, ["name", "partner_id", "state", "date_order",
                         "validity_date", "commitment_date", "currency_id",
                         "pricelist_id", "amount_total", "client_order_ref",
                         "user_id", "team_id", "note", "origin",
                         "invoice_status", "company_id"])
    extra = [c for c in personalizados(campos) if campos[c].get("type") in (
        "selection", "boolean", "char", "integer", "date", "many2one")]
    pedidos = odoo.leer("sale.order", [], [c for c in (
        "state", "currency_id", "date_order", "company_id") if c in campos]
        + extra) or []
    r.sub("Cuantas y en que estado")
    r(f"  Total: {len(pedidos)}  ·  fechas: {rango(pedidos, 'date_order')}")
    r.tabla(reparto(pedidos, "state"), 10)
    r("  Por moneda:")
    r.tabla(reparto(pedidos, "currency_id"), 10, "    ")
    r.sub("Campos agregados por la empresa (x_) en la cotizacion")
    describir_personalizados(r, odoo, "sale.order", campos, pedidos)
    if "is_subscription" in campos:
        subs = odoo.contar("sale.order", [["is_subscription", "=", True]])
        r(f"  Suscripciones (is_subscription): {subs}")
    elif "plan_id" in campos:
        subs = odoo.contar("sale.order", [["plan_id", "!=", False]])
        r(f"  Suscripciones (con plan recurrente): {subs}")

    lineas_campos = odoo.campos("sale.order.line")
    r.sub("El renglon de la cotizacion (sale.order.line)")
    r.presencia(lineas_campos, ["product_id", "product_template_id", "name",
                                "product_uom_qty", "product_uom_id",
                                "product_uom", "price_unit", "discount",
                                "tax_ids", "tax_id", "display_type"])
    fechas_renglon = sorted(c for c, i in (lineas_campos or {}).items()
                            if i.get("type") in ("date", "datetime"))
    r("  Fechas en el renglon: " + (", ".join(fechas_renglon) or "(ninguna)"))
    r.sub("Campos agregados por la empresa (x_) en el renglon")
    describir_personalizados(r, odoo, "sale.order.line", lineas_campos, None)

    renglones = odoo.leer("sale.order.line",
                          [["order_id.state", "=", "sale"]],
                          ["product_id", "display_type"]) or []
    productos = [x for x in renglones if not x.get("display_type")]
    r.sub("Lo que se vende · renglones de pedidos confirmados por producto")
    r(f"  Renglones: {len(productos)}  ·  secciones y notas: "
      f"{len(renglones) - len(productos)}")
    r.tabla(reparto(productos, "product_id", "(sin producto)"), 40)

    catalogo = odoo.leer("product.template", [["sale_ok", "=", True]],
                         ["name", "type"], orden="name") or []
    r.sub(f"Catalogo de productos que se venden ({len(catalogo)})")
    for p in catalogo[:80]:
        r(f"  {p['name']}  [{p.get('type')}]")
    if len(catalogo) > 80:
        r(f"  ... y {len(catalogo) - 80} mas")

    return {"existe": True, "pedidos": len(pedidos),
            "estados": reparto(pedidos, "state"),
            "fechas_renglon": fechas_renglon,
            "productos_distintos": len({nombre(x.get("product_id"))
                                        for x in productos})}


def facturas(r: Reporte, odoo: Odoo) -> dict:
    r.titulo("Facturacion (account.move)")
    movs = odoo.leer("account.move", [["move_type", "=", "out_invoice"]],
                     ["state", "currency_id", "invoice_date"])
    if movs is None:
        r("  No se pudo leer facturacion.")
        return {"existe": False}
    r(f"  Facturas de cliente: {len(movs)}  ·  fechas: "
      f"{rango(movs, 'invoice_date')}")
    r.tabla(reparto(movs, "state"), 5)
    r("  Por moneda:")
    r.tabla(reparto(movs, "currency_id"), 10, "    ")
    notas = odoo.contar("account.move", [["move_type", "=", "out_refund"]])
    r(f"  Notas de credito: {notas}")

    campos = odoo.campos("account.move") or {}
    mx = sorted(c for c in campos if c.startswith("l10n_mx"))
    r.sub("Campos de la factura electronica de Mexico (l10n_mx...)")
    for c in mx[:40]:
        r(f"  {c:<40} {campos[c].get('string', '')}")
    if not mx:
        r("  (ninguno: no hay CFDI en esta base)")

    r.sub("Diarios de venta")
    for d in odoo.leer("account.journal", [["type", "=", "sale"]],
                       ["name", "code", "currency_id", "company_id"]) or []:
        r(f"  {d['code']:<8} {d['name']}  ·  "
          f"{nombre(d.get('currency_id')) or 'moneda de la empresa'}"
          f"  ·  {nombre(d.get('company_id'))}")

    r.sub("Impuestos de venta activos")
    for t in odoo.leer("account.tax", [["type_tax_use", "=", "sale"]],
                       ["name", "amount", "amount_type", "company_id"],
                       limite=60) or []:
        r(f"  {t['name']:<40} {t.get('amount')} ({t.get('amount_type')})"
          f"  ·  {nombre(t.get('company_id'))}")

    r.sub("Terminos de pago")
    terminos = odoo.leer("account.payment.term", [], ["name"]) or []
    r("  " + (", ".join(t["name"] for t in terminos) or "(ninguno)"))

    r.sub("Monedas activas")
    monedas = odoo.leer("res.currency", [["active", "=", True]], ["name"]) or []
    r("  " + ", ".join(m["name"] for m in monedas))

    clientes = odoo.contar("res.partner", [["customer_rank", ">", 0]])
    empresas = odoo.contar("res.partner", [["customer_rank", ">", 0],
                                           ["is_company", "=", True]])
    r.sub("Clientes")
    r(f"  Contactos que son clientes: {clientes}  ·  de ellos empresas: "
      f"{empresas}")
    return {"existe": True, "facturas": len(movs), "cfdi": bool(mx),
            "monedas": [m["name"] for m in monedas]}


def pagos(r: Reporte, odoo: Odoo) -> dict:
    r.titulo("Pagos y viaticos")
    hallazgos = {}
    campos = odoo.campos("account.payment")
    if campos is not None:
        r.sub("Pagos (account.payment)")
        r.presencia(campos, ["payment_type", "partner_type", "state", "date",
                             "memo", "ref", "payment_reference",
                             "journal_id", "partner_id", "amount"])
        salidas = odoo.leer("account.payment",
                            [["payment_type", "=", "outbound"]],
                            [c for c in ("state", "partner_type", "date")
                             if c in campos]) or []
        r(f"  Pagos de salida: {len(salidas)}  ·  fechas: "
          f"{rango(salidas, 'date')}")
        r.tabla(reparto(salidas, "partner_type"), 5, "    ")
        hallazgos["pagos_salida"] = len(salidas)
    gastos = odoo.contar("hr.expense", [])
    r.sub("Gastos de empleados (hr.expense)")
    r(f"  {gastos if gastos is not None else 'no disponible'}")
    hallazgos["gastos"] = gastos
    return hallazgos


# ------------------------------------------------------------------ resumen

def resumen(emp: dict, cap: dict, flo: dict, tal: dict, ven: dict,
            fac: dict) -> list:
    s = []
    c = emp.get("campos") or {}
    s.append("LAS CINCO RESPUESTAS (ODOO_LO_QUE_NECESITAMOS.md, punto 7)")
    s.append("")
    if emp.get("existe") and "activos" in emp:
        s.append(f"1. La baja del empleado (active): "
                 f"{'si existe' if 'active' in c else 'NO existe'}. "
                 f"{emp['activos']} activos, {emp['archivados']} de baja.")
        s.append(f"2. Correo del personal: {emp['con_correo']} de "
                 f"{emp['activos']} tienen; {emp['repetidos']} repetidos. "
                 "Dominios: " + ", ".join(f"{d} ({n})"
                                          for d, n in emp["dominios"]))
    else:
        s.append("1-2. No se pudo leer empleados.")
    s.append("3. Quien llama a quien: vamos nosotros por los datos. "
             "La API respondio.")
    if emp.get("existe") and "activos" in emp:
        s.append(f"4. La sede: work_location_id lleno en {emp['con_sede']} "
                 f"de {emp['activos']} ({emp['sedes_catalogo']} sedes en el "
                 f"catalogo); departamento en {emp['con_departamento']}; "
                 f"puesto en {emp['con_puesto']}.")
    s.append("5. El id del empleado: si, la API lo da siempre.")
    s.append("")
    s.append("LO DEMAS")
    if cap.get("existe"):
        s.append(f"- Certificaciones: {cap['registros']} registros en "
                 f"{cap['tipos']} tipos; vigencia (valid_to): "
                 f"{'si' if cap['vigencia'] else 'no'}.")
    else:
        s.append("- Certificaciones: el modulo de habilidades no respondio.")
    if flo.get("existe") and "activos" in flo:
        s.append(f"- Flota: {flo['activos']} activas, {flo['archivados']} de "
                 f"baja; placa en {flo['con_placa']}; formatos: "
                 + ", ".join(f"{m} ({n})" for m, n in flo["mascaras"]))
        s.append("- Blindaje: " + ("; ".join(flo["blindaje"])
                                   if flo["blindaje"] else "no aparece"))
    s.append(f"- Taller: servicios de flota {tal.get('servicios', 'n/d')}, "
             f"solicitudes de mantenimiento "
             f"{tal.get('mantenimiento', 'n/d')}.")
    if ven.get("existe"):
        s.append(f"- Cotizaciones: {ven['pedidos']} en total ("
                 + ", ".join(f"{e} {n}" for e, n in ven["estados"])
                 + f"); {ven['productos_distintos']} productos distintos "
                 "vendidos; fecha por renglon: "
                 + (", ".join(ven["fechas_renglon"]) or "no"))
    if fac.get("existe"):
        s.append(f"- Facturas: {fac['facturas']} de cliente; CFDI Mexico: "
                 f"{'si' if fac['cfdi'] else 'no'}; monedas: "
                 + ", ".join(fac["monedas"]))
    return s


def main() -> int:
    base = os.environ.get("ODOO_BASE", "").strip()
    llave = os.environ.get("ODOO_API_KEY", "").strip()
    bd = os.environ.get("ODOO_BD", "").strip() or None
    if not base or not llave:
        print("Falta ODOO_BASE u ODOO_API_KEY en el .env. Guarda la llave "
              "(paso 3) y vuelve a correr esto.")
        return 1

    odoo = Odoo(base, llave, bd)
    r = Reporte()
    r(f"Reconocimiento de Odoo · {datetime.now():%Y-%m-%d %H:%M}")
    r("Solo lectura. Sin datos personales: campos, conteos y catalogos.")
    print(f"Conectando con {odoo.base} ...")
    try:
        conexion(r, odoo)
        print("Conexion correcta. Leyendo (tarda un minuto)...")
        emp = empleados(r, odoo)
        cap = capacitaciones(r, odoo)
        flo = flota(r, odoo)
        tal = taller(r, odoo)
        ven = ventas(r, odoo)
        fac = facturas(r, odoo)
        pagos(r, odoo)
    except LlaveInvalida as error:
        print(f"\nOdoo rechazo la llave: {error}")
        print("Puede que se haya copiado incompleta o que ya haya vencido. "
              "Crea otra (paso 2) y guardala otra vez (paso 3).")
        return 2
    except httpx.HTTPError as error:
        print(f"\nNo se pudo hablar con Odoo: {error}")
        return 3

    corto = resumen(emp, cap, flo, tal, ven, fac)
    r.titulo("Resumen")
    r.lineas += corto
    if odoo.fallas:
        r.titulo("Lo que no se pudo leer")
        r.lineas += [f"  {f}" for f in odoo.fallas]
    r("")
    r(f"Llamadas a Odoo: {odoo.llamadas} · fallas: {len(odoo.fallas)}")
    with open(SALIDA, "w", encoding="utf-8") as f:
        f.write("\n".join(r.lineas) + "\n")

    print()
    print("\n".join(corto))
    print()
    print(f"Llamadas a Odoo: {odoo.llamadas} · lo que no se pudo leer: "
          f"{len(odoo.fallas)}")
    print("El detalle completo quedo en backend/reconocimiento_odoo.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())

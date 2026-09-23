# -*- coding: utf-8 -*-
"""Ordenar Odoo antes de conectarlo: puestos, ubicaciones y categorias.

Autorizado por Salvador el 23 de septiembre. Es una limpieza de UNA SOLA
VEZ, no la conexion de Centauro (esa solo lee). Hace tres cosas:

  1. Asigna el Puesto del catalogo al personal de seguridad, sacandolo del
     puesto que ya tienen escrito: «Personal de Seguridad...» y «Security
     Driver...». El nombre del puesto que ya tienen escrito NO se toca.
  2. Crea las ubicaciones de trabajo de las cuatro plazas: Ciudad de
     Mexico, Guadalajara, Queretaro y Monterrey.
  3. Flotilla: renombra SUVCOMPACTA como CUV, crea MINIVAN BLINDADA, SUV y
     SUV BLINDADA, y pasa a VAN las unidades que estan en MINIBUS.

Tres modos, desde la raiz del proyecto:

    docker compose run --rm api python ordenar_odoo.py            # ensayo
    docker compose run --rm api python ordenar_odoo.py --aplicar
    docker compose run --rm api python ordenar_odoo.py --deshacer odoo_cambios_AAAAMMDD_HHMM.json

  * El ENSAYO no cambia nada: dice exactamente que haria y lo guarda en
    odoo_plan.json. Solo cuenta; no imprime nombres de nadie.
  * APLICAR vuelve a calcular el plan y, si Odoo cambio desde el ensayo,
    se detiene: solo se aplica lo que se aprobo. Cada cambio se anota en
    odoo_cambios_<fecha>.json en el momento en que se hace, con el valor
    de antes, asi que un corte a la mitad tambien se puede deshacer.
  * DESHACER regresa cada cambio anotado, en orden inverso. Lo creado se
    borra solo si nadie lo usa todavia.

Lee ODOO_BASE y ODOO_API_KEY del .env. Idempotente: correrlo dos veces no
hace nada la segunda.
"""
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

import httpx

AQUI = os.path.dirname(os.path.abspath(__file__))
PLAN = os.path.join(AQUI, "odoo_plan.json")

LECTURA = {"search_read", "search_count", "fields_get", "read"}
METODOS = {
    "ensayo": LECTURA,
    "aplicar": LECTURA | {"create", "write"},
    "deshacer": LECTURA | {"write", "unlink"},
}

# Quien entra, por el puesto escrito. Decision de Salvador, 23 sep:
# personal de seguridad y security drivers; guardias y monitoristas no.
PUESTOS = [
    ("personal de seguridad", "Personal de Seguridad"),
    ("security driver", "Security Driver (Protección Ejecutiva)"),
]
UBICACIONES = ["Ciudad de México", "Guadalajara", "Querétaro", "Monterrey"]
RENOMBRAR = ("SUVCOMPACTA", "CUV")
CATEGORIAS_NUEVAS = ["MINIVAN BLINDADA", "SUV", "SUV BLINDADA"]
MOVER = ("MINIBUS", "VAN")


class LlaveInvalida(Exception):
    pass


class Odoo:
    def __init__(self, base, llave, modo):
        base = base.strip().rstrip("/")
        if not base.startswith("http"):
            base = "https://" + base
        self.base = base
        self.permitidos = METODOS[modo]
        self.http = httpx.Client(timeout=60, headers={
            "Authorization": f"bearer {llave}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "centauro-ordenar/1.0"})
        self.contexto = {"lang": "es_MX"}

    def llamar(self, modelo, metodo, **args):
        if metodo not in self.permitidos:
            raise RuntimeError(f"{metodo} no esta permitido en este modo")
        contexto = {**self.contexto, **args.pop("context", {})}
        r = self.http.post(f"{self.base}/json/2/{modelo}/{metodo}",
                           json={"context": contexto, **args})
        if r.status_code == 200:
            return r.json()
        try:
            error = r.json()
            mensaje = error.get("message") or error.get("name") or r.text
        except ValueError:
            mensaje = r.text
        mensaje = " ".join(str(mensaje).split())[:300]
        if r.status_code == 401:
            raise LlaveInvalida(mensaje)
        raise RuntimeError(f"{modelo}.{metodo} → {r.status_code}: {mensaje}")

    def leer(self, modelo, dominio, campos, **contexto):
        return self.llamar(modelo, "search_read", domain=dominio,
                           fields=campos, order="id",
                           context=contexto) or []

    def campos(self, modelo):
        return self.llamar(modelo, "fields_get",
                           attributes=["type", "required", "translate",
                                       "relation"])


def normal(texto):
    """Sin acentos, sin mayusculas y sin espacios de sobra."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.lower().split())


def id_de(valor):
    """El id de un many2one, venga como [id, nombre], dict o id."""
    if not valor:
        return None
    if isinstance(valor, (list, tuple)):
        return valor[0]
    if isinstance(valor, dict):
        return valor.get("id")
    return valor


# ------------------------------------------------------------------ el plan

def calcular(odoo):
    """Lo que hay que hacer, sin hacerlo. Devuelve (operaciones, resumen)."""
    ops, resumen = [], []

    # ---------------------------------------------------------- 1 · puestos
    empleados = odoo.leer("hr.employee", [],
                          ["job_title", "job_id", "company_id"])
    elegidos = {}
    for e in empleados:
        titulo = normal(e.get("job_title"))
        for prefijo, puesto in PUESTOS:
            if titulo.startswith(prefijo):
                elegidos.setdefault(puesto, []).append(e)
                break
    empresas = {id_de(e["company_id"])
                for grupo in elegidos.values() for e in grupo}
    if len(empresas) != 1:
        raise RuntimeError(
            f"El personal elegido esta en {len(empresas)} empresas; se "
            "esperaba una. No se hace nada: revisalo en Odoo.")
    empresa = empresas.pop()
    odoo.contexto["allowed_company_ids"] = [empresa]

    campos_puesto = odoo.campos("hr.job")
    puestos = odoo.leer("hr.job", [], ["name", "company_id"]
                        + (["active"] if "active" in campos_puesto else []),
                        active_test=False)
    resumen.append("PUESTOS DEL CATALOGO")
    for prefijo, puesto in PUESTOS:
        grupo = elegidos.get(puesto, [])
        existente = [p for p in puestos
                     if normal(p["name"]).startswith(prefijo)
                     and id_de(p.get("company_id")) in (empresa, None)]
        exacto = [p for p in existente if normal(p["name"]) == normal(puesto)]
        existente = exacto or existente
        clave = f"puesto:{puesto}"
        if not existente:
            valores = {"name": puesto, "company_id": empresa}
            for campo, valor in (("is_published", False),
                                 ("website_published", False),
                                 ("no_of_recruitment", 0)):
                if campo in campos_puesto:
                    valores[campo] = valor
            ops.append({"op": "crear", "modelo": "hr.job", "clave": clave,
                        "valores": valores,
                        "traducir": bool(campos_puesto["name"].get("translate"))})
            destino = {"ref": clave}
            resumen.append(f"  Crear el puesto «{puesto}»")
        else:
            elegido = existente[0]
            destino = {"id": elegido["id"]}
            if elegido.get("active") is False:
                ops.append({"op": "escribir", "modelo": "hr.job",
                            "id": elegido["id"], "valores": {"active": True},
                            "antes": {"active": False}})
                resumen.append(f"  Reactivar el puesto «{elegido['name']}», "
                               "que estaba archivado")
            else:
                resumen.append(f"  El puesto «{elegido['name']}» ya existe")
        faltan = [e for e in grupo
                  if not destino.get("id") or id_de(e["job_id"]) != destino["id"]]
        titulos = {}
        for e in faltan:
            titulos[e["job_title"].strip()] = titulos.get(e["job_title"].strip(), 0) + 1
            ops.append({"op": "escribir", "modelo": "hr.employee",
                        "id": e["id"], "destino": destino,
                        "valores": {"job_title": e["job_title"]},
                        "antes": {"job_id": id_de(e["job_id"]) or False,
                                  "job_title": e["job_title"]}})
        ya = len(grupo) - len(faltan)
        resumen.append(f"  Asignarlo a {len(faltan)} persona(s)"
                       + (f"; {ya} ya lo tienen" if ya else ""))
        for titulo, n in sorted(titulos.items(), key=lambda x: -x[1]):
            resumen.append(f"    {n:>4}  con puesto escrito «{titulo}»")
    resumen.append("  El nombre del puesto que ya tienen escrito no se toca.")

    # ------------------------------------------------------ 2 · ubicaciones
    campos_ubic = odoo.campos("hr.work.location")
    ubicaciones = odoo.leer("hr.work.location", [], ["name", "company_id"],
                            active_test=False)
    socio = id_de(odoo.leer("res.company", [["id", "=", empresa]],
                            ["partner_id"])[0]["partner_id"])
    resumen.append("")
    resumen.append("UBICACIONES DE TRABAJO")
    for nombre in UBICACIONES:
        if any(normal(u["name"]) == normal(nombre) for u in ubicaciones):
            resumen.append(f"  «{nombre}» ya existe")
            continue
        valores = {"name": nombre, "company_id": empresa}
        if "location_type" in campos_ubic:
            valores["location_type"] = "office"
        if "address_id" in campos_ubic:
            valores["address_id"] = socio
        ops.append({"op": "crear", "modelo": "hr.work.location",
                    "clave": f"ubicacion:{nombre}", "valores": valores,
                    "traducir": bool(campos_ubic["name"].get("translate"))})
        resumen.append(f"  Crear «{nombre}»")
    if "address_id" in campos_ubic:
        resumen.append("  (con la dirección de la empresa: Odoo pide una)")

    # ------------------------------------------------ 3 · flotilla
    campos_cat = odoo.campos("fleet.vehicle.model.category")
    traducir_cat = bool(campos_cat["name"].get("translate"))
    categorias = odoo.leer("fleet.vehicle.model.category", [], ["name"])
    por_nombre = {normal(c["name"]): c for c in categorias}
    resumen.append("")
    resumen.append("FLOTILLA · CATEGORIAS")
    viejo, nuevo = RENOMBRAR
    if normal(nuevo) in por_nombre:
        resumen.append(f"  «{nuevo}» ya existe")
    elif normal(viejo) in por_nombre:
        c = por_nombre[normal(viejo)]
        n = len(odoo.leer("fleet.vehicle", [["category_id", "=", c["id"]]],
                          ["id"]))
        ops.append({"op": "escribir", "modelo": "fleet.vehicle.model.category",
                    "id": c["id"], "valores": {"name": nuevo},
                    "antes": {"name": c["name"]}, "traducir": traducir_cat})
        resumen.append(f"  Renombrar «{c['name']}» como «{nuevo}» "
                       f"({n} unidad(es) la tienen y se quedan en ella)")
    else:
        ops.append({"op": "crear", "modelo": "fleet.vehicle.model.category",
                    "clave": f"categoria:{nuevo}", "valores": {"name": nuevo},
                    "traducir": traducir_cat})
        resumen.append(f"  Crear «{nuevo}» (no hay {viejo} que renombrar)")
    for nombre in CATEGORIAS_NUEVAS:
        if normal(nombre) in por_nombre:
            resumen.append(f"  «{nombre}» ya existe")
            continue
        ops.append({"op": "crear", "modelo": "fleet.vehicle.model.category",
                    "clave": f"categoria:{nombre}", "valores": {"name": nombre},
                    "traducir": traducir_cat})
        resumen.append(f"  Crear «{nombre}»")

    origen, destino_cat = MOVER
    if normal(origen) in por_nombre:
        if normal(destino_cat) not in por_nombre:
            raise RuntimeError(f"No existe la categoria {destino_cat}: no se "
                               "hace nada.")
        de = por_nombre[normal(origen)]["id"]
        a = por_nombre[normal(destino_cat)]["id"]
        unidades = odoo.leer("fleet.vehicle", [["category_id", "=", de]],
                             ["id", "category_id"])
        for u in unidades:
            ops.append({"op": "escribir", "modelo": "fleet.vehicle",
                        "id": u["id"], "valores": {"category_id": a},
                        "antes": {"category_id": de}})
        resumen.append(f"  Pasar {len(unidades)} unidad(es) de «{origen}» a "
                       f"«{destino_cat}»")
    else:
        resumen.append(f"  No hay categoria «{origen}»: nada que pasar")

    return ops, resumen


def huella(ops):
    return hashlib.sha256(json.dumps(ops, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


# ------------------------------------------------------------------ aplicar

def idiomas(odoo):
    return [l["code"] for l in odoo.leer("res.lang", [["active", "=", True]],
                                         ["code"])]


def escribir_en_todos(odoo, modelo, ident, valores, langs):
    """Un nombre traducible se escribe en cada idioma activo: si no, quien
    tenga Odoo en ingles seguiria viendo el nombre viejo."""
    for lang in langs:
        odoo.llamar(modelo, "write", ids=[ident], vals=valores,
                    context={"lang": lang})


def aplicar(odoo):
    ops, resumen = calcular(odoo)
    if not os.path.exists(PLAN):
        print("No hay ensayo guardado. Corre primero el ensayo (sin --aplicar).")
        return 1
    aprobado = json.load(open(PLAN, encoding="utf-8"))
    if aprobado.get("huella") != huella(ops):
        print("Odoo cambio desde el ensayo: el plan ya no es el mismo que se "
              "aprobo.\nNo se cambio nada. Corre el ensayo otra vez.")
        return 4
    if not ops:
        print("No hay nada que hacer: Odoo ya esta como se pidio.")
        return 0

    langs = idiomas(odoo)
    ruta = os.path.join(AQUI, f"odoo_cambios_{datetime.now():%Y%m%d_%H%M}.json")
    bitacora = {"hecho_en": datetime.now().isoformat(timespec="seconds"),
                "odoo": odoo.base, "contexto": odoo.contexto, "cambios": []}

    def anotar(entrada):
        bitacora["cambios"].append(entrada)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(bitacora, f, ensure_ascii=False, indent=1)

    creados = {}
    hechos = 0
    try:
        for op in ops:
            modelo = op["modelo"]
            if op["op"] == "crear":
                nuevo = odoo.llamar(modelo, "create", vals_list=[op["valores"]])
                ident = nuevo[0] if isinstance(nuevo, list) else nuevo
                creados[op["clave"]] = ident
                anotar({"op": "crear", "modelo": modelo, "id": ident,
                        "clave": op["clave"]})
                if op.get("traducir"):
                    escribir_en_todos(odoo, modelo, ident,
                                      {"name": op["valores"]["name"]}, langs)
            else:
                valores = dict(op["valores"])
                if "destino" in op:
                    d = op["destino"]
                    valores["job_id"] = d.get("id") or creados[d["ref"]]
                anotar({"op": "escribir", "modelo": modelo, "id": op["id"],
                        "antes": op["antes"], "despues": valores,
                        "traducir": op.get("traducir", False)})
                if op.get("traducir"):
                    escribir_en_todos(odoo, modelo, op["id"], valores, langs)
                else:
                    odoo.llamar(modelo, "write", ids=[op["id"]], vals=valores)
            hechos += 1
    except (RuntimeError, httpx.HTTPError) as error:
        print(f"\nSe detuvo en el cambio {hechos + 1} de {len(ops)}: {error}")
        print(f"Lo que alcanzo a hacer quedo anotado en {os.path.basename(ruta)}.")
        print("Para regresarlo: --deshacer " + os.path.basename(ruta))
        return 5

    # Se comprueba leyendo Odoo otra vez: si el plan sale vacio, quedo.
    restantes, _ = calcular(odoo)
    os.remove(PLAN)
    print(f"Hecho: {hechos} cambio(s).")
    print("Comprobado en Odoo: " + ("no queda nada por hacer." if not restantes
                                    else f"quedan {len(restantes)} pendientes."))
    print(f"Anotados en {os.path.basename(ruta)}, por si hay que deshacer.")
    return 0 if not restantes else 6


# ------------------------------------------------------------------ deshacer

def deshacer(odoo, archivo):
    ruta = archivo if os.path.isabs(archivo) else os.path.join(AQUI, archivo)
    bitacora = json.load(open(ruta, encoding="utf-8"))
    odoo.contexto.update(bitacora.get("contexto", {}))
    langs = idiomas(odoo)
    regresados, borrados, respetados = 0, 0, []
    for c in reversed(bitacora["cambios"]):
        if c["op"] == "escribir":
            if c.get("traducir"):
                escribir_en_todos(odoo, c["modelo"], c["id"], c["antes"], langs)
            else:
                odoo.llamar(c["modelo"], "write", ids=[c["id"]], vals=c["antes"])
            regresados += 1
            continue
        # Lo creado se borra solo si nadie lo usa ya.
        usos = {"hr.job": ("hr.employee", "job_id"),
                "hr.work.location": ("hr.employee", "work_location_id"),
                "fleet.vehicle.model.category": ("fleet.vehicle", "category_id")}
        modelo_uso, campo = usos[c["modelo"]]
        en_uso = odoo.llamar(modelo_uso, "search_count",
                             domain=[[campo, "=", c["id"]]])
        if en_uso:
            respetados.append(f"{c['clave']} (lo usan {en_uso})")
            continue
        odoo.llamar(c["modelo"], "unlink", ids=[c["id"]])
        borrados += 1
    print(f"Deshecho: {regresados} cambio(s) regresados, {borrados} "
          "registro(s) creados borrados.")
    for r in respetados:
        print(f"  No se borro {r}: ya se esta usando.")
    return 0


# ------------------------------------------------------------------ main

def main():
    base = os.environ.get("ODOO_BASE", "").strip()
    llave = os.environ.get("ODOO_API_KEY", "").strip()
    if not base or not llave:
        print("Falta ODOO_BASE u ODOO_API_KEY en el .env. Guarda la llave y "
              "vuelve a correr esto.")
        return 1
    args = sys.argv[1:]
    modo = ("aplicar" if "--aplicar" in args
            else "deshacer" if "--deshacer" in args else "ensayo")
    odoo = Odoo(base, llave, modo)
    try:
        if modo == "deshacer":
            i = args.index("--deshacer")
            if i + 1 >= len(args):
                print("Falta el archivo: --deshacer odoo_cambios_....json")
                return 1
            return deshacer(odoo, args[i + 1])
        if modo == "aplicar":
            return aplicar(odoo)

        ops, resumen = calcular(odoo)
        print("ENSAYO · no se ha cambiado nada en Odoo\n")
        print("\n".join(resumen))
        print(f"\nEn total: {len(ops)} cambio(s).")
        with open(PLAN, "w", encoding="utf-8") as f:
            json.dump({"huella": huella(ops), "cambios": len(ops),
                       "hecho_en": datetime.now().isoformat(timespec="seconds"),
                       "resumen": resumen}, f, ensure_ascii=False, indent=1)
        if ops:
            print("Si esta bien, se aplica con --aplicar.")
        return 0
    except LlaveInvalida as error:
        print(f"Odoo rechazo la llave: {error}. Crea otra y guardala otra vez.")
        return 2
    except (RuntimeError, httpx.HTTPError) as error:
        print(f"No se pudo: {error}")
        return 3


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Las reglas del personal de oficina que viene de Odoo, sin base de datos.

Seccion 74, segundo paso de la propuesta Puestos y Odoo que aprobo
Salvador el 26 de septiembre. Como en el personal de seguridad, aqui se
decide que hacer con cada empleado a partir de fotos fijas de Odoo y de
Centauro, sin leer ni escribir nada: el ensayo y la lectura de verdad
deciden exactamente lo mismo.

Las decisiones que viven aqui:

  * Es de oficina todo empleado activo de Odoo que no es personal de
    seguridad: monitoristas, finanzas, recursos humanos, consultores,
    direccion.
  * Entra con su correo de TRABAJO, el de la empresa. Sin correo de
    trabajo no se da de alta: se lista para que Recursos Humanos se lo
    ponga en Odoo, y en la siguiente lectura llega solo.
  * La llave es el numero interno de Odoo. La primera vez, a quien ya
    estaba en Centauro se le reconoce por ese mismo correo.
  * Llega la persona, no su acceso: el acceso lo da Recursos Humanos, con
    el puesto que sugiere su puesto de Odoo.
  * Si Odoo lo archiva, su acceso se cierra.
  * Lo dudoso no se adivina: se reporta como pendiente y no se toca. La
    excepcion es la plaza: a quien Odoo no le dice donde trabaja --o le
    dice un lugar que Centauro no tiene-- se le pone la de la oficina
    central, y el informe lo cuenta. En oficina la plaza solo decide con
    que pais abren sus pantallas.
"""
import collections
import re

from app.odoo_personal_reglas import (CORREO_VALIDO, DOMINIOS_RAROS,
                                      es_de_seguridad, nombre_de, normal,
                                      plaza_de, texto)

# La oficina central: donde queda quien no tiene lugar de trabajo en Odoo.
PLAZA_CENTRAL = "ciudad de mexico"


def es_de_oficina(empleado: dict) -> bool:
    return not es_de_seguridad(empleado)


def correo_de(empleado: dict) -> str:
    """El correo con el que entra a la consola: el de trabajo."""
    return texto(empleado.get("work_email")).lower()


def puesto_de(empleado: dict) -> str:
    """El puesto como lo escribieron, y si no, el del catalogo."""
    return texto(empleado.get("job_title")) or nombre_de(empleado.get("job_id"))


def area_de(empleado: dict) -> str:
    return nombre_de(empleado.get("department_id"))


def problema_de_correo(correo: str) -> str | None:
    if not CORREO_VALIDO.match(correo):
        return "correo de trabajo mal escrito"
    if correo.split("@")[-1] in DOMINIOS_RAROS:
        return "correo de trabajo con error de dedo"
    return None


# ------------------------------------------------------------ la sugerencia

def patrones(escritos: str | None) -> list[str]:
    """Los puestos de Odoo de un puesto de Centauro, como se capturan:
    separados por coma."""
    return [normal(x) for x in (escritos or "").split(",") if normal(x)]


def sugerir(puesto_odoo: str | None, puestos: list) -> dict | None:
    """El puesto de Centauro que se parece a su puesto de Odoo.

    `puestos`: los que se pueden sugerir, cada uno con sus `patrones` ya
    normalizados. Un patron cuenta si aparece en su puesto de Odoo como
    palabras completas --«consultor» no se encuentra dentro de
    «consultoria»--, y entre varios gana el mas largo: a «Consultor JR B»
    le queda mejor «consultor jr» que «consultor». Sin ninguno, nada: el
    puesto se escoge a mano.
    """
    escrito = normal(puesto_odoo)
    if not escrito:
        return None
    mejor, largo = None, 0
    for p in puestos:
        for patron in p["patrones"]:
            if (len(patron) > largo and re.search(
                    rf"(?<![\w]){re.escape(patron)}(?![\w])", escrito)):
                mejor, largo = p, len(patron)
    return mejor


# ------------------------------------------------------------------ el plan

def planear(empleados: list, personas: list, plazas: dict,
            correos_de_acceso: dict) -> dict:
    """Que hacer con cada empleado de oficina, sin hacerlo.

    `personas`: foto fija de Centauro, con id, odoo_id, nombre, correo,
    plaza_id, activo, oficina, de_campo (tiene acceso a la app de campo),
    puesto_odoo, area_odoo y sincronizado_en. `plazas`: por nombre
    normalizado. `correos_de_acceso`: correo -> persona_id de los accesos
    que ya existen.
    """
    elegidos = [e for e in empleados if es_de_oficina(e)]
    por_odoo = {p["odoo_id"]: p for p in personas if p.get("odoo_id")}
    por_correo = {texto(p.get("correo")).lower(): p
                  for p in personas if p.get("correo")}
    cuenta = collections.Counter(correo_de(e) for e in elegidos
                                 if correo_de(e))
    repetidos = {c for c, n in cuenta.items() if n > 1}
    central = plazas.get(PLAZA_CENTRAL)

    plan = {"leidos": len(elegidos), "altas": [], "vinculos": [],
            "cambios": [], "pendientes": [], "sin_correo": [],
            "sin_lugar": [], "sin_cambio": 0, "procesadas": [],
            "revisar_salida": []}
    tomados = set()

    def pendiente(e, persona_id, faltas):
        plan["pendientes"].append({"odoo_id": e["id"], "persona_id": persona_id,
                                   "nombre": texto(e.get("name")),
                                   "falta": faltas})

    for e in elegidos:
        nombre = texto(e.get("name"))
        correo = correo_de(e)
        puesto, area = puesto_de(e), area_de(e)
        problema = (None if not correo
                    else "correo de trabajo repetido en Odoo"
                    if correo in repetidos else problema_de_correo(correo))
        plaza, lugar = plaza_de(e, plazas)

        persona, vinculo = por_odoo.get(e["id"]), False
        if persona is not None and not persona.get("oficina"):
            # La trajo la lectura del personal de seguridad y en Odoo ya
            # no es de seguridad: un cambio de puesto no se adivina.
            pendiente(e, persona["id"], ["en Centauro es personal de "
                                         "seguridad; en Odoo ya no"])
            continue
        if persona is None and correo and not problema:
            candidata = por_correo.get(correo)
            if candidata is not None:
                if candidata.get("odoo_id") and candidata["odoo_id"] != e["id"]:
                    pendiente(e, candidata["id"],
                              ["su correo ya es de otra persona en Centauro"])
                    continue
                if candidata.get("de_campo"):
                    pendiente(e, candidata["id"],
                              ["su correo es de alguien del personal de "
                               "seguridad en Centauro"])
                    continue
                persona, vinculo = candidata, True

        # ------------------------------------------------ quien llega nuevo
        if persona is None:
            if not correo:
                plan["sin_correo"].append({"odoo_id": e["id"], "nombre": nombre,
                                           "puesto": puesto, "area": area})
                continue
            faltas = []
            if problema:
                faltas.append(problema)
            elif correo in correos_de_acceso or correo in tomados:
                faltas.append("su correo ya es de otro acceso en Centauro")
            if plaza is None and central is None:
                faltas.append(f"la plaza «{lugar}» no existe en Centauro"
                              if lugar else "sin plaza")
            if faltas:
                pendiente(e, None, faltas)
                continue
            if plaza is None:
                plaza = central
                plan["sin_lugar"].append({"odoo_id": e["id"], "nombre": nombre,
                                          "lugar": lugar or None})
            tomados.add(correo)
            plan["altas"].append({
                "odoo_id": e["id"], "nombre": nombre, "correo": correo,
                "plaza_id": plaza["id"], "plaza": plaza["nombre"],
                "puesto_odoo": puesto or None, "area_odoo": area or None})
            continue

        # ------------------------------------------------ quien ya esta
        if not persona.get("activo"):
            pendiente(e, persona["id"], ["activo en Odoo pero dado de baja en "
                                         "Centauro: reactivar a mano"])
            continue

        valores, que, avisos = {}, [], []
        if nombre and nombre != persona.get("nombre"):
            valores["nombre"] = nombre
            que.append("nombre")
        if plaza is not None and plaza["id"] != persona.get("plaza_id"):
            valores["plaza_id"] = plaza["id"]
            que.append("plaza")
        if puesto and puesto != (persona.get("puesto_odoo") or ""):
            valores["puesto_odoo"] = puesto
            que.append("puesto")
        if area and area != (persona.get("area_odoo") or ""):
            valores["area_odoo"] = area
            que.append("área")
        actual = texto(persona.get("correo")).lower()
        if correo and correo != actual:
            otra = por_correo.get(correo)
            if problema:
                avisos.append(problema)
            elif ((otra is not None and otra["id"] != persona["id"])
                  or correo in tomados
                  or correos_de_acceso.get(correo, persona["id"]) != persona["id"]):
                avisos.append("su correo nuevo ya es de otra persona en Centauro")
            else:
                valores["correo"] = correo
                que.append("correo")
                tomados.add(correo)

        if vinculo:
            plan["vinculos"].append({"persona_id": persona["id"],
                                     "odoo_id": e["id"],
                                     "nombre": nombre or persona.get("nombre")})
        if valores:
            plan["cambios"].append({"persona_id": persona["id"],
                                    "odoo_id": e["id"],
                                    "nombre": nombre or persona.get("nombre"),
                                    "valores": valores, "que": que})
        elif not vinculo:
            plan["sin_cambio"] += 1
        if avisos:
            pendiente(e, persona["id"], avisos)
        plan["procesadas"].append(persona["id"])

    # Las de oficina que Centauro ya lleva desde Odoo y hoy no salieron:
    # o las archivaron, o pasaron a ser de seguridad. Se pregunta a Odoo
    # por cada una antes de decidir.
    ids = {e["id"] for e in elegidos}
    plan["revisar_salida"] = [
        p for p in personas
        if p.get("oficina") and p.get("odoo_id") and p.get("activo")
        and p.get("sincronizado_en") and p["odoo_id"] not in ids]
    return plan


def clasificar_salidas(revisar: list, estados: dict) -> tuple:
    """(bajas, pendientes). `estados`: lo que dice Odoo de cada una,
    leido con los archivados incluidos."""
    bajas, pendientes = [], []
    for p in revisar:
        f = estados.get(p["odoo_id"])
        if f is not None and f.get("active", True) is not False:
            pendientes.append({"odoo_id": p["odoo_id"], "persona_id": p["id"],
                               "nombre": p.get("nombre"),
                               "falta": ["ahora es personal de seguridad en "
                                         "Odoo"]})
        else:
            bajas.append({"odoo_id": p["odoo_id"], "persona_id": p["id"],
                          "nombre": p.get("nombre"),
                          "motivo": ("archivado en Odoo" if f is not None
                                     else "ya no esta en Odoo")})
    return bajas, pendientes

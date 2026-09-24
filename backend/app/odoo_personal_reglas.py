# -*- coding: utf-8 -*-
"""Las reglas del personal que viene de Odoo, sin base de datos.

Aqui se decide que hacer con cada empleado --darlo de alta, vincularlo,
cambiarle algo o dejarlo pendiente-- a partir de fotos fijas de Odoo y de
Centauro. No lee ni escribe nada: por eso se prueba sola, y por eso el
ensayo y la sincronizacion de verdad deciden exactamente lo mismo.

Las decisiones de Salvador (23 de septiembre) que viven aqui:

  * Entra el personal de seguridad: puesto «Personal de Seguridad...» o
    «Security Driver...». Monitoristas, oficina y guardias no.
  * La llave es el numero interno de Odoo.
  * El correo con el que entra a la app es el de trabajo o, si no tiene,
    el personal.
  * El Estado de Mexico va como Ciudad de Mexico: es la misma zona
    metropolitana.
  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.

Y del 24 de septiembre: un celular que no es un numero --en Odoo hay
fichas que dicen «sin dispositivo»-- no se guarda como telefono ni borra
el que Centauro ya tiene; el informe lo cuenta aparte. No detiene el
alta: la persona entra sin celular.
"""
import collections
import re
import unicodedata
from datetime import date, datetime

PUESTOS = ("personal de seguridad", "security driver")
ALIAS_PLAZA = {
    "estado de mexico": "ciudad de mexico",
    "edomex": "ciudad de mexico",
    "cdmx": "ciudad de mexico",
}
# Los errores de dedo que ya aparecieron en Odoo o que aparecen siempre.
DOMINIOS_RAROS = frozenset({
    "gamil.com", "gmial.com", "gmai.com", "gmail.con", "gmail.co",
    "hotmial.com", "hotmal.com", "hotmail.con", "hotamil.com",
    "yaho.com", "yahoo.con", "outlok.com", "outlook.con"})
CORREO_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Un celular ya con la lada de su pais tiene al menos diez digitos en toda
# la region: +52 y diez en Mexico, +55 y diez u once en Brasil, +51 y
# nueve en Peru. Lo que no llega no es un numero al que se pueda llamar.
DIGITOS_CELULAR = 10

# Como empieza cada imagen en base64. El SVG no esta porque es el avatar
# de iniciales que Odoo le pone a quien no tiene foto: no es una foto, y
# en el task sheet el cliente no reconoceria a nadie por sus iniciales.
FIRMAS = (("iVBOR", "image/png"), ("/9j/", "image/jpeg"),
          ("R0lGOD", "image/gif"), ("UklGR", "image/webp"))


def normal(texto) -> str:
    """Sin acentos, sin mayusculas y sin espacios de sobra."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.lower().split())


def texto(valor) -> str:
    return "" if valor in (False, None) else str(valor).strip()


def nombre_de(valor) -> str:
    """El nombre de un many2one, venga como [id, nombre] o como dict."""
    if isinstance(valor, (list, tuple)) and len(valor) > 1:
        return texto(valor[1])
    if isinstance(valor, dict):
        return texto(valor.get("display_name") or valor.get("name"))
    return ""


def fecha(valor) -> date | None:
    try:
        return date.fromisoformat(texto(valor)[:10]) if texto(valor) else None
    except ValueError:
        return None


def instante(valor) -> datetime | None:
    """El write_date de Odoo: «AAAA-MM-DD HH:MM:SS», en UTC."""
    try:
        return datetime.fromisoformat(texto(valor)[:19]) if texto(valor) else None
    except ValueError:
        return None


def es_de_seguridad(empleado: dict) -> bool:
    """Por el puesto del catalogo y, si no lo tiene, por el escrito."""
    return any(normal(t).startswith(PUESTOS)
               for t in (nombre_de(empleado.get("job_id")),
                         empleado.get("job_title")))


def correo_de(empleado: dict) -> str:
    for campo in ("work_email", "private_email"):
        valor = texto(empleado.get(campo)).lower()
        if valor:
            return valor
    return ""


def problema_de_correo(correo: str) -> str | None:
    if not correo:
        return "sin correo"
    if not CORREO_VALIDO.match(correo):
        return "correo mal escrito"
    if correo.split("@")[-1] in DOMINIOS_RAROS:
        return "correo con error de dedo"
    return None


def es_celular(numero) -> bool:
    """Si el telefono, ya con su lada, es un numero y no un texto."""
    return sum(c.isdigit() for c in texto(numero)) >= DIGITOS_CELULAR


def plaza_de(empleado: dict, plazas: dict) -> tuple:
    """(plaza o None, lo que dice Odoo). `plazas` va por nombre normalizado."""
    lugar = nombre_de(empleado.get("work_location_id"))
    clave = normal(lugar)
    return plazas.get(ALIAS_PLAZA.get(clave, clave)), lugar


def foto_de(base64: str | None) -> str | None:
    """La foto lista para una etiqueta <img>, o None si no es una foto."""
    if not base64 or not isinstance(base64, str):
        return None
    base64 = base64.strip()
    for firma, tipo in FIRMAS:
        if base64.startswith(firma):
            return f"data:{tipo};base64,{base64}"
    return None


# ------------------------------------------------------------------ el plan

def planear(empleados: list, personas: list, plazas: dict,
            correos_de_acceso: dict, normalizar_tel) -> dict:
    """Que hacer con cada empleado de Odoo, sin hacerlo.

    `empleados`: lo que leyo Odoo (los activos). `personas`: foto fija de
    Centauro, una por persona, con id, odoo_id, nombre, correo, plaza_id,
    pais_id, activo, telefono, referencia, fecha_ingreso, foto (si tiene),
    sincronizado_en y baja_odoo_en. `plazas`: por nombre normalizado, con
    id, nombre y pais_id. `correos_de_acceso`: correo -> persona_id de los
    accesos que ya existen. `normalizar_tel(numero, pais_id)`: la regla de
    la lada del sistema.
    """
    elegidos = [e for e in empleados if es_de_seguridad(e)]
    por_odoo = {p["odoo_id"]: p for p in personas if p.get("odoo_id")}
    por_correo = {texto(p.get("correo")).lower(): p
                  for p in personas if p.get("correo")}
    cuenta = collections.Counter(correo_de(e) for e in elegidos if correo_de(e))
    repetidos = {c for c, n in cuenta.items() if n > 1}

    plan = {"leidos": len(elegidos), "altas": [], "vinculos": [],
            "cambios": [], "fotos": [], "pendientes": [], "sin_cambio": 0,
            "procesadas": [], "revisar_salida": [], "celular_no_valido": []}
    tomados = set()        # correos que este plan ya aparto

    def pendiente(e, persona_id, faltas):
        plan["pendientes"].append({"odoo_id": e["id"], "persona_id": persona_id,
                                   "nombre": texto(e.get("name")),
                                   "falta": faltas})

    def celular(e, pais_id, persona_id, nombre):
        """El celular de Odoo con su lada, o None si Odoo no trae un numero."""
        escrito = texto(e.get("mobile_phone"))
        if not escrito:
            return None
        numero = normalizar_tel(escrito, pais_id)
        if es_celular(numero):
            return numero
        plan["celular_no_valido"].append({"odoo_id": e["id"],
                                          "persona_id": persona_id,
                                          "nombre": nombre})
        return None

    for e in elegidos:
        nombre = texto(e.get("name"))
        correo = correo_de(e)
        problema = ("correo repetido en Odoo" if correo in repetidos
                    else problema_de_correo(correo))
        plaza, lugar = plaza_de(e, plazas)

        persona, vinculo = por_odoo.get(e["id"]), False
        if persona is None and correo and not problema:
            candidata = por_correo.get(correo)
            if candidata is not None:
                if candidata.get("odoo_id") and candidata["odoo_id"] != e["id"]:
                    pendiente(e, candidata["id"],
                              ["su correo ya es de otra persona en Centauro"])
                    continue
                persona, vinculo = candidata, True

        # ------------------------------------------------ quien llega nuevo
        if persona is None:
            faltas = []
            if plaza is None:
                faltas.append(f"la plaza «{lugar}» no existe en Centauro"
                              if lugar else "sin plaza")
            if problema:
                faltas.append(problema)
            elif correo in correos_de_acceso or correo in tomados:
                faltas.append("su correo ya es de otro acceso en Centauro")
            if faltas:
                pendiente(e, None, faltas)
                continue
            tomados.add(correo)
            plan["altas"].append({
                "odoo_id": e["id"], "nombre": nombre, "correo": correo,
                "plaza_id": plaza["id"], "plaza": plaza["nombre"],
                "telefono": celular(e, plaza["pais_id"], None, nombre),
                "referencia": texto(e.get("registration_number")) or None,
                "fecha_ingreso": fecha(e.get("first_contract_date"))})
            plan["fotos"].append(e["id"])
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
        elif plaza is None and lugar:
            avisos.append(f"la plaza «{lugar}» no existe en Centauro")
        pais = plaza["pais_id"] if plaza is not None else persona.get("pais_id")
        tel = celular(e, pais, persona["id"], nombre or persona.get("nombre"))
        if tel and tel != persona.get("telefono"):
            valores["telefono"] = tel
            que.append("celular")
        referencia = texto(e.get("registration_number"))
        if referencia and referencia != persona.get("referencia"):
            valores["referencia"] = referencia
            que.append("referencia")
        ingreso = fecha(e.get("first_contract_date"))
        if ingreso and ingreso != persona.get("fecha_ingreso"):
            valores["fecha_ingreso"] = ingreso
            que.append("fecha de ingreso")
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

        # La foto se vuelve a pedir solo si Odoo toco la ficha despues de
        # la ultima lectura: subir una foto cambia el write_date. Quien
        # solo tiene el circulo de iniciales no se vuelve a pedir cada
        # hora; se pide cuando RH le suba una de verdad.
        escrito = instante(e.get("write_date"))
        if (not persona.get("sincronizado_en")
                or (escrito and escrito > persona["sincronizado_en"])):
            plan["fotos"].append(e["id"])

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

    # Las que Centauro ya lleva desde Odoo y hoy no salieron en la lista:
    # o las archivaron, o dejaron de ser de seguridad. Se pregunta a Odoo
    # por cada una antes de decidir.
    ids = {e["id"] for e in elegidos}
    plan["revisar_salida"] = [
        p for p in personas
        if p.get("odoo_id") and p.get("activo") and p.get("sincronizado_en")
        and p["odoo_id"] not in ids]
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
                               "falta": ["ya no tiene puesto de seguridad "
                                         "en Odoo"]})
        else:
            bajas.append({"odoo_id": p["odoo_id"], "persona_id": p["id"],
                          "nombre": p.get("nombre"),
                          "motivo": ("archivado en Odoo" if f is not None
                                     else "ya no esta en Odoo")})
    return bajas, pendientes

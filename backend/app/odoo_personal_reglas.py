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
  * El Estado de Mexico va como Ciudad de Mexico: es la misma zona
    metropolitana.
  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.

Y de esa misma noche, ya con la hoja de RH cargada:

  * El correo con el que entra a la app es SIEMPRE el personal. Los
    correos de trabajo del personal de seguridad se van a suspender. El de
    trabajo solo sirve para reconocer, la primera vez, a quien ya estaba
    en Centauro con el; desde ahi entra con el personal. (Antes era el de
    trabajo y, si no tenia, el personal.)
  * Un celular que no es un numero --en Odoo hay fichas que dicen «sin
    dispositivo»-- no se guarda como telefono ni borra el que Centauro ya
    tiene; el informe lo cuenta aparte. No detiene el alta: la persona
    entra sin celular.

Y la de Brasil (seccion 121), con Odoo ya listo:

  * Cada pais lee a su gente por su compania, como la flota, y nunca se
    mezclan: Mexico, CENTAURO ASS con «Personal de Seguridad» o «Security
    Driver»; Brasil, CENTAURO SOLUCOES AVANCADAS DE SEGURANCA LTDA con
    «Motorista Executivo Bilingue» --el conductor de seguridad bilingue--
    o «Condutor Folguista», el de relevo. Los administrativos de Brasil
    son de oficina. El puesto de un pais con la compania de otro no entra.
  * La plaza, entre las ciudades de su pais. «Sao Paulo - Barueri» es Sao
    Paulo: el lugar de trabajo que trae un barrio o un municipio despues
    del guion se busca tambien por lo de antes.
  * A la gente de Brasil le pueden faltar en Odoo el CPF, la CNH y la
    cuenta bancaria: entra igual, y lo que falta se dice aparte, como
    «por capturar». Lo que Centauro ya tiene no se borra por eso.

Y la del 29 de septiembre (decision 7, seccion 105):

  * La cuenta bancaria de Odoo manda. Si el empleado trae cuenta con
    numero, se copian la CLABE, el banco y el titular; si no trae cuenta,
    se vacian las tres: una cuenta vieja capturada a mano no se queda
    cuando RH la quito. Pero si las cuentas no se pudieron leer --sin
    permiso, o el campo no existe en esa version-- no se toca nada,
    como con cualquier campo que Odoo pierde (seccion 100).
"""
import collections
import re
import unicodedata
from datetime import date, datetime

from app.odoo_api import COMPANIAS

# El personal de seguridad de cada pais (seccion 121). En Odoo cada pais es
# una compania, con sus puestos. `central`: la ciudad de la oficina de ese
# pais, donde queda la oficina que no dice donde trabaja. `por_capturar`:
# lo que a la gente de ese pais le puede faltar en Odoo sin detener nada.
PERSONAL = (
    {"pais": "MX", "nombre": "México", "compania": COMPANIAS["MX"],
     "puestos": ("personal de seguridad", "security driver"),
     "central": "ciudad de mexico", "por_capturar": False},
    {"pais": "BR", "nombre": "Brasil", "compania": COMPANIAS["BR"],
     "puestos": ("motorista executivo bilingue", "condutor folguista"),
     "central": "sao paulo", "por_capturar": True},
)
PUESTOS = tuple(p for grupo in PERSONAL for p in grupo["puestos"])
# Lo que se dice de quien le falta en Odoo (seccion 121), por campo.
FALTA_CPF, FALTA_CNH, FALTA_CUENTA = ("sin CPF", "sin CNH",
                                      "sin cuenta bancaria")
# La cuenta bancaria del empleado en Odoo: un many2one a res.partner.bank.
# En la version saas~19.3 es la cuenta principal, primary_bank_account_id
# (junto a la lista bank_account_ids); en las de antes, bank_account_id.
# Se lee la que exista, en ese orden, y aqui siempre se ve con el nombre
# nuevo. Con el viejo, la lectura de cada hora decia «sin permiso para
# leer cuentas bancarias» con el usuario administrador (1 oct).
CAMPO_CUENTA = "primary_bank_account_id"
CAMPOS_DE_CUENTA = ("primary_bank_account_id", "bank_account_id")
SIN_CUENTA = {"clabe": None, "banco": None, "titular_cuenta": None}
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


def corto(valor, largo: int) -> str:
    """El texto de Odoo al largo de su columna en Centauro (seccion 100).

    Una razon social de 170 letras o un modelo largo reventaban la
    lectura entera, cada hora, hasta que alguien acortara el dato en
    Odoo, y el informe no decia cual. Se pierde el final, que es lo que
    menos importa de un nombre largo.
    """
    return texto(valor)[:largo].rstrip()


def nombre_de(valor) -> str:
    """El nombre de un many2one, venga como [id, nombre] o como dict."""
    if isinstance(valor, (list, tuple)) and len(valor) > 1:
        return texto(valor[1])
    if isinstance(valor, dict):
        return texto(valor.get("display_name") or valor.get("name"))
    return ""


def id_de(valor) -> int | None:
    """El numero de un many2one, venga como [id, nombre], como dict o
    como el numero solo. False o vacio: no apunta a nada."""
    if isinstance(valor, (list, tuple)) and valor:
        valor = valor[0]
    elif isinstance(valor, dict):
        valor = valor.get("id")
    if isinstance(valor, bool) or valor in (None, ""):
        return None
    try:
        return int(valor) or None
    except (TypeError, ValueError):
        return None


def cuenta_de(empleado: dict, cuentas: dict) -> tuple:
    """(los tres campos bancarios de Centauro, aviso) para un empleado.

    Sin cuenta en Odoo: los tres vacios (Odoo es el maestro). Con cuenta
    pero sin numero, igual: un renglon sin numero no sirve para
    depositar. Si el empleado apunta a una cuenta que no vino en la
    lectura --un registro que se borro o que este usuario no alcanza--
    no se adivina: `None` y el aviso, y lo guardado se queda. El titular
    es el nombre escrito en la cuenta o, si RH no lo escribio, el
    contacto dueno de la cuenta, que es lo que Odoo entiende por
    titular.
    """
    referida = id_de(empleado.get(CAMPO_CUENTA))
    if not referida:
        return dict(SIN_CUENTA), None
    fila = cuentas.get(referida)
    if fila is None:
        return None, "su cuenta bancaria no se pudo leer de Odoo"
    numero = corto(fila.get("acc_number"), 40)
    if not numero:
        return dict(SIN_CUENTA), None
    titular = texto(fila.get("acc_holder_name")) or nombre_de(fila.get("partner_id"))
    return {"clabe": numero,
            "banco": corto(nombre_de(fila.get("bank_id")), 80) or None,
            "titular_cuenta": corto(titular, 160) or None}, None


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


def _puestos(empleado: dict) -> list:
    return [normal(t) for t in (nombre_de(empleado.get("job_id")),
                                empleado.get("job_title"))]


def es_de_seguridad(empleado: dict) -> bool:
    """Por el puesto del catalogo y, si no lo tiene, por el escrito: el
    de seguridad de cualquier pais. Asi la oficina nunca se lleva a un
    motorista de Brasil."""
    return any(t.startswith(PUESTOS) for t in _puestos(empleado))


def grupo_de_compania(compania_id) -> dict | None:
    """El pais de una compania de Odoo, o None si no es de Connect."""
    return next((g for g in PERSONAL if g["compania"] == compania_id), None)


def personal_de(empleado: dict) -> tuple:
    """(grupo, problema). El pais cuyo puesto de seguridad Y cuya
    compania trae el empleado (seccion 121). Con el puesto de un pais y
    la compania de otro --o ninguna-- no es de ninguno: (None, por que).
    Sin puesto de seguridad no es de esta lectura: (None, None)."""
    puestos = _puestos(empleado)
    suyos = [g for g in PERSONAL
             if any(t.startswith(g["puestos"]) for t in puestos)]
    if not suyos:
        return None, None
    compania = id_de(empleado.get("company_id"))
    for grupo in suyos:
        if grupo["compania"] == compania:
            return grupo, None
    grupo = suyos[0]
    if compania is None:
        return None, (f"el puesto es de «{grupo['nombre']}» y en Odoo no "
                      "tiene compania")
    nombre = nombre_de(empleado.get("company_id")) or str(compania)
    return None, (f"el puesto es de «{grupo['nombre']}» y su compania en "
                  f"Odoo es «{nombre}»")


def correo_de(empleado: dict) -> str:
    """El correo con el que entra a la app: el personal, siempre."""
    return texto(empleado.get("private_email")).lower()


def correo_de_trabajo(empleado: dict) -> str:
    """Solo para reconocer a quien ya estaba en Centauro con este."""
    return texto(empleado.get("work_email")).lower()


def problema_de_correo(correo: str) -> str | None:
    if not correo:
        return "sin correo personal"
    if not CORREO_VALIDO.match(correo):
        return "correo mal escrito"
    if correo.split("@")[-1] in DOMINIOS_RAROS:
        return "correo con error de dedo"
    return None


def es_celular(numero) -> bool:
    """Si el telefono, ya con su lada, es un numero y no un texto."""
    return sum(c.isdigit() for c in texto(numero)) >= DIGITOS_CELULAR


def buscar_plaza(lugar, plazas: dict):
    """La plaza de un lugar de Odoo, o None. `plazas` va por nombre
    normalizado. El lugar con un barrio o un municipio despues del guion
    --«Sao Paulo - Barueri»-- tambien se busca por lo de antes (seccion
    121)."""
    clave = normal(lugar)
    if not clave:
        return None
    for candidata in (clave, re.split(r"\s[-–—]\s", clave)[0].strip()):
        plaza = plazas.get(ALIAS_PLAZA.get(candidata, candidata))
        if plaza is not None:
            return plaza
    return None


def plaza_de(empleado: dict, plazas: dict) -> tuple:
    """(plaza o None, lo que dice Odoo). `plazas` va por nombre normalizado:
    las de su pais."""
    lugar = nombre_de(empleado.get("work_location_id"))
    return buscar_plaza(lugar, plazas), lugar


# Donde vive en Odoo lo que a la gente de Brasil le puede faltar (seccion
# 121), si nadie dice otra cosa: el CPF, en «Numero de identificacion»; la
# CNH, en «Licencia para conducir», el archivo escaneado --se lee su nombre
# de archivo, que Odoo llena al subirlo, y no el archivo--.
CAMPO_CPF = "identification_id"
CAMPO_CNH = "driving_license_name"
NOMBRES_DE_CAMPO = {CAMPO_CNH: "Licencia para conducir"}


def campos_por_capturar(campos: dict, cpf: str = "", cnh: str = "") -> dict:
    """En que campo de hr.employee viven el CPF y la CNH, o None si este
    Odoo no tiene ninguno (seccion 121): el tecnico que diga la
    configuracion; si no, uno cuyo nombre visible diga «CPF» o «CNH» --el
    que RH agregue con Studio--; si no, los de Odoo. `campos`: el
    fields_get del empleado, con su «string»."""
    def buscar(palabra, tecnico, de_odoo):
        if tecnico and tecnico in campos:
            return tecnico
        candidatos = []
        for nombre, info in campos.items():
            visible = normal((info or {}).get("string"))
            palabras = set(re.split(r"[^a-z0-9]+", visible))
            if palabra in palabras or palabra in nombre.lower().split("_"):
                candidatos.append((0 if visible == palabra else 1, nombre))
        if candidatos:
            return min(candidatos)[1]
        return de_odoo if de_odoo in campos else None
    return {"cpf": buscar("cpf", cpf, CAMPO_CPF),
            "cnh": buscar("cnh", cnh, CAMPO_CNH)}


def nombres_de_campos(campos: dict, extra: dict) -> dict:
    """Como se llaman en la pantalla de Odoo los campos de `extra`, para
    decir donde se busca cada cosa. None: Odoo no tiene ese campo."""
    def nombre(tecnico):
        if not tecnico:
            return None
        return (NOMBRES_DE_CAMPO.get(tecnico)
                or texto((campos.get(tecnico) or {}).get("string")) or tecnico)
    return {clave: nombre(tecnico) for clave, tecnico in extra.items()}


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
            correos_de_acceso: dict, normalizar_tel,
            cuentas: dict | None = None, paises: dict | None = None,
            campos_extra: dict | None = None) -> dict:
    """Que hacer con cada empleado de Odoo, sin hacerlo.

    `empleados`: lo que leyo Odoo (los activos). `personas`: foto fija de
    Centauro, una por persona, con id, odoo_id, nombre, correo, plaza_id,
    pais_id, activo, telefono, referencia, fecha_ingreso, foto (si tiene),
    sincronizado_en, baja_odoo_en y sus datos bancarios (banco, clabe,
    titular_cuenta). `plazas`: por pais (su id) y nombre normalizado, con
    id, nombre y pais_id. `correos_de_acceso`: correo -> persona_id de los
    accesos que ya existen. `normalizar_tel(numero, pais_id)`: la regla de
    la lada del sistema. `cuentas`: las de res.partner.bank por su id, o
    None si no se pudieron leer (seccion 105): entonces lo bancario no se
    toca. `paises`: por codigo, con id y nombre. `campos_extra`: en que
    campo de Odoo viven el CPF y la CNH (seccion 121), o None.
    """
    paises = paises or {}
    campos_extra = campos_extra or {}
    elegidos, mezclados = [], []
    for e in empleados:
        grupo, problema = personal_de(e)
        if grupo is not None:
            elegidos.append((e, grupo))
        elif problema:
            mezclados.append((e, problema))
    por_odoo = {p["odoo_id"]: p for p in personas if p.get("odoo_id")}
    por_correo = {texto(p.get("correo")).lower(): p
                  for p in personas if p.get("correo")}
    cuenta = collections.Counter(correo_de(e) for e, _ in elegidos
                                 if correo_de(e))
    repetidos = {c for c, n in cuenta.items() if n > 1}
    de_trabajo = collections.Counter(correo_de_trabajo(e) for e, _ in elegidos
                                     if correo_de_trabajo(e))
    # De que pais es cada ciudad, para decir que la de otro pais no es de
    # aqui en vez de que no existe.
    pais_de_ciudad = {nombre: pais_id for pais_id, suyas in plazas.items()
                      for nombre in suyas}
    nombres_pais = {x["id"]: x.get("nombre") for x in paises.values()}

    plan = {"leidos": len(elegidos),
            "por_pais": {g["pais"]: 0 for g in PERSONAL},
            "altas": [], "vinculos": [],
            "cambios": [], "fotos": [], "pendientes": [], "sin_cambio": 0,
            "procesadas": [], "revisar_salida": [], "celular_no_valido": [],
            "por_capturar": [], "con_cuenta": 0, "sin_cuenta": 0}
    tomados = set()        # correos que este plan ya aparto

    def pendiente(e, persona_id, faltas):
        plan["pendientes"].append({"odoo_id": e["id"], "persona_id": persona_id,
                                   "nombre": texto(e.get("name")),
                                   "falta": faltas})

    def banco(e, grupo):
        """Lo bancario que dice Odoo, o None si no se toca. Cuenta a
        quien la trae y a quien no. En el pais cuya gente llega a Odoo
        sin cuenta todavia (seccion 121), la que falta en Odoo no borra la
        que Centauro ya tiene: se dice como por capturar."""
        if cuentas is None:
            return None, None
        datos, aviso = cuenta_de(e, cuentas)
        if datos is not None:
            plan["con_cuenta" if datos["clabe"] else "sin_cuenta"] += 1
            if grupo["por_capturar"] and not datos["clabe"]:
                return None, None
        return datos, aviso

    def capturar(e, persona, grupo, nombre, plaza_pais):
        """Lo que a la persona de ese pais le falta en Odoo y no detiene
        nada (seccion 121): el CPF, la CNH y la cuenta bancaria, si
        tampoco la tiene Centauro."""
        if not grupo["por_capturar"]:
            return
        persona = persona or {}
        falta = []
        for clave, aviso in (("cpf", FALTA_CPF), ("cnh", FALTA_CNH)):
            campo = campos_extra.get(clave)
            if not campo or not texto(e.get(campo)):
                falta.append(aviso)
        if cuentas is not None and not persona.get("clabe"):
            datos, _ = cuenta_de(e, cuentas)
            if datos is not None and not datos["clabe"]:
                falta.append(FALTA_CUENTA)
        if falta:
            plan["por_capturar"].append({
                "odoo_id": e["id"], "persona_id": persona.get("id"),
                "nombre": nombre, "pais": plaza_pais, "falta": falta})

    def sin_ciudad(lugar, pais):
        """Por que no hay plaza: el lugar es de otro pais, o no existe."""
        if not lugar:
            return "sin plaza"
        otro = pais_de_ciudad.get(normal(lugar))
        if otro is not None and otro != pais["id"]:
            return (f"la plaza «{lugar}» no es una ciudad de "
                    f"«{pais['nombre']}» en Centauro")
        return f"la plaza «{lugar}» no existe en Centauro"

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

    # El puesto de un pais con la compania de otro (seccion 121): no entra
    # en ninguno ni se toca a quien ya estaba. Cuenta como visto, para que
    # no se tome por una salida.
    for e, problema in mezclados:
        ya = por_odoo.get(e["id"])
        pendiente(e, ya["id"] if ya else None, [problema])

    for e, grupo in elegidos:
        plan["por_pais"][grupo["pais"]] += 1
        nombre = corto(e.get("name"), 160)
        pais = paises.get(grupo["pais"])
        if pais is None:
            ya = por_odoo.get(e["id"])
            pendiente(e, ya["id"] if ya else None,
                      [f"el pais «{grupo['pais']}» no existe en Centauro"])
            continue
        correo = correo_de(e)
        problema = ("correo repetido en Odoo" if correo in repetidos
                    else problema_de_correo(correo))
        # La ciudad, entre las de su pais: «Guadalajara» en un motorista
        # de Brasil no lo manda a Mexico.
        plaza, lugar = plaza_de(e, plazas.get(pais["id"], {}))

        persona, vinculo = por_odoo.get(e["id"]), False
        if persona is None:
            # Quien ya estaba en Centauro se reconoce por su correo: el
            # personal o, si lo capturaron con el de trabajo, ese. Solo un
            # correo bien escrito y que nadie mas trae en Odoo.
            trabajo = correo_de_trabajo(e)
            posibles = [c for c, sirve in (
                (correo, correo and not problema),
                (trabajo, trabajo and de_trabajo[trabajo] == 1
                 and not problema_de_correo(trabajo))) if sirve]
            candidata = next((por_correo[c] for c in posibles
                              if c in por_correo), None)
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
                faltas.append(sin_ciudad(lugar, pais))
            if problema:
                faltas.append(problema)
            elif correo in correos_de_acceso or correo in tomados:
                faltas.append("su correo ya es de otro acceso en Centauro")
            if faltas:
                pendiente(e, None, faltas)
                continue
            tomados.add(correo)
            # Con su cuenta, si Odoo la trae; sin cuentas leidas o con
            # una que no se alcanzo, entra sin ella y se dice.
            datos_banco, aviso_banco = banco(e, grupo)
            plan["altas"].append({
                "odoo_id": e["id"], "nombre": nombre, "correo": correo,
                "plaza_id": plaza["id"], "plaza": plaza["nombre"],
                "telefono": celular(e, plaza["pais_id"], None, nombre),
                "referencia": corto(e.get("registration_number"), 40) or None,
                "fecha_ingreso": fecha(e.get("first_contract_date")),
                **(datos_banco or SIN_CUENTA)})
            plan["fotos"].append(e["id"])
            if aviso_banco:
                pendiente(e, None, [aviso_banco])
            capturar(e, None, grupo, nombre, pais["nombre"])
            continue

        # ------------------------------------------------ quien ya esta
        if not persona.get("activo"):
            pendiente(e, persona["id"], ["activo en Odoo pero dado de baja en "
                                         "Centauro: reactivar a mano"])
            continue
        if persona.get("oficina"):
            # Un cambio de puesto no se adivina (seccion 74), tampoco en
            # este sentido: quien en Centauro es de oficina --finanzas,
            # una consultora-- y en Odoo aparece de seguridad queda
            # pendiente. Antes esta lectura se lo llevaba a la calle, le
            # cambiaba el correo de su acceso al personal y le dejaba su
            # rol de consola (seccion 100).
            pendiente(e, persona["id"], ["en Centauro es de oficina; en Odoo "
                                         "ya es de seguridad"])
            continue
        if persona.get("pais_id") and persona["pais_id"] != pais["id"]:
            # Una persona no cambia de pais sola (seccion 121), como la
            # unidad: el cambio lo decide alguien.
            pendiente(e, persona["id"], [f"en Odoo es de «{pais['nombre']}» y "
                                         "en Centauro es de otro pais"])
            continue

        valores, que, avisos = {}, [], []
        if nombre and nombre != persona.get("nombre"):
            valores["nombre"] = nombre
            que.append("nombre")
        if plaza is not None and plaza["id"] != persona.get("plaza_id"):
            valores["plaza_id"] = plaza["id"]
            que.append("plaza")
        elif plaza is None and lugar:
            avisos.append(sin_ciudad(lugar, pais))
        lada = plaza["pais_id"] if plaza is not None else persona.get("pais_id")
        tel = celular(e, lada, persona["id"], nombre or persona.get("nombre"))
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
        elif not correo:
            # Sigue entrando con el que ya tenia, pero RH tiene que poner
            # el personal: el de trabajo se va a suspender.
            avisos.append(problema)

        # La cuenta bancaria: lo que dice Odoo manda, tambien para vaciar
        # (seccion 105). Con las cuentas sin leer, `banco` no dice nada.
        datos_banco, aviso_banco = banco(e, grupo)
        if aviso_banco:
            avisos.append(aviso_banco)
        elif datos_banco is not None:
            bancarios = {campo: valor for campo, valor in datos_banco.items()
                         if valor != persona.get(campo)}
            if bancarios:
                valores.update(bancarios)
                que.append("cuenta bancaria")

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
        capturar(e, persona, grupo, nombre or persona.get("nombre"),
                 pais["nombre"])
        plan["procesadas"].append(persona["id"])

    # Las que Centauro ya lleva desde Odoo y hoy no salieron en la lista:
    # o las archivaron, o dejaron de ser de seguridad. Se pregunta a Odoo
    # por cada una antes de decidir. Las de oficina no: esas las lleva su
    # propia lectura (seccion 74), y aqui saldrian cada hora como
    # pendientes de algo que no son. Las de puesto y compania de paises
    # distintos ya salieron como pendientes: no son salidas.
    ids = {e["id"] for e, _ in elegidos} | {e["id"] for e, _ in mezclados}
    plan["revisar_salida"] = [
        p for p in personas
        if p.get("odoo_id") and p.get("activo") and p.get("sincronizado_en")
        and not p.get("oficina") and p["odoo_id"] not in ids]
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

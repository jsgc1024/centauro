# -*- coding: utf-8 -*-
"""La hoja de RH ya cargada a Odoo, y dos arreglos (seccion 62).

Decision de Salvador, 23 de septiembre: "de acuerdo, adelante".

  * cargar_hoja_rh.py: primero se revisa el nombre y despues si la persona
    ya vino. Antes, una fila con el No. Odoo de otra persona le apartaba
    el numero a la fila buena que venia despues.
  * La lectura del personal de Odoo: un celular que, ya con su lada, no
    llega a diez digitos («sin dispositivo») no se guarda ni borra el que
    habia; el alta sigue sin celular, y el informe y
    sincronizar_personal.py lo cuentan aparte.
  * Pruebas: tests/test_cargar_hoja_rh.py (nuevo) y una mas en
    test_odoo_personal.py. BITACORA, seccion 62.

Sin migracion. Idempotente. Todo se arma en memoria, se comprueba contra
lo que se probo (md5 por archivo) y solo entonces se escribe.
"""
import hashlib
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    'cargador': RAIZ / 'backend/cargar_hoja_rh.py',
    'reglas': RAIZ / 'backend/app/odoo_personal_reglas.py',
    'personal': RAIZ / 'backend/app/odoo_personal.py',
    'sincronizar': RAIZ / 'backend/sincronizar_personal.py',
    't_personal': RAIZ / 'backend/tests/test_odoo_personal.py',
    'bitacora': RAIZ / 'BITACORA.md',
}
NUEVOS = {'tests/test_cargar_hoja_rh.py': '# -*- coding: utf-8 -*-\n"""El cargador de la hoja que devuelve RH (cargar_hoja_rh.py).\n\nSolo el calculo del plan, contra un Odoo de mentiras: no sale a la red,\nno escribe nada y no necesita openpyxl (las filas van ya leidas).\n"""\nimport cargar_hoja_rh as hoja\n\n\nclass OdooFalso:\n    def __init__(self, *empleados):\n        self.empleados = list(empleados)\n        self.contexto = {}\n\n    def leer(self, modelo, dominio, campos, **contexto):\n        if modelo == "hr.work.location":\n            return [{"id": i, "name": p, "company_id": [1, "Centauro"]}\n                    for i, p in enumerate(hoja.PLAZAS, start=1)]\n        assert modelo == "hr.employee"\n        if dominio:      # la revision de referencias: quien ya tiene una\n            return [e for e in self.empleados if e["registration_number"]]\n        return self.empleados\n\n\ndef empleado(n):\n    return {"id": n, "name": f"Agente {n}", "job_id": False,\n            "job_title": "Personal de Seguridad", "company_id": [1, "Centauro"],\n            "work_location_id": False, "mobile_phone": False,\n            "work_email": False, "private_email": f"agente{n}@correo.lat",\n            "registration_number": False}\n\n\ndef fila(n, plaza, nombre=None):\n    return {"id": n, "nombre": nombre or f"Agente {n}",\n            "work_location_id": plaza, "mobile_phone": None,\n            "work_email": None, "private_email": None,\n            "registration_number": None, "notas": None}\n\n\nGDL, MTY = hoja.PLAZAS.index("Guadalajara") + 1, hoja.PLAZAS.index("Monterrey") + 1\n\n\ndef test_una_fila_movida_no_le_quita_su_numero_a_la_fila_buena():\n    # Paso con la hoja del 24 de septiembre: un bloque de filas quedo con\n    # el No. Odoo de otras personas. La fila movida se salta y la buena,\n    # que viene despues con el mismo numero, se toma.\n    ops, resumen = hoja.calcular(OdooFalso(empleado(1), empleado(2)), [\n        fila(1, "Guadalajara", nombre="Agente 2"),\n        fila(1, "Monterrey"),\n        fila(2, "Guadalajara")])\n    assert {op["id"]: op["valores"] for op in ops} == {\n        1: {"work_location_id": MTY}, 2: {"work_location_id": GDL}}\n    assert "      1  el nombre de la fila no es el de Odoo" in resumen\n    assert not any("dos veces" in renglon for renglon in resumen)\n\n\ndef test_la_misma_persona_dos_veces_solo_cuenta_la_primera():\n    ops, resumen = hoja.calcular(OdooFalso(empleado(1)), [\n        fila(1, "Monterrey"),\n        fila(1, "Guadalajara")])\n    assert [op["valores"] for op in ops] == [{"work_location_id": MTY}]\n    assert "      1  la persona viene dos veces" in resumen\n'}
ESPERADO = {'cargador': '6566040862f4ef0e5725e825da6ce423', 'reglas': '2064e5332d45477eadf02aea16c0b906', 'personal': 'd5875581d78914bacda4428081b996b2', 'sincronizar': '5253582a7cc5d0721221e408a2777548', 't_personal': '7a837865e67d66d5ff0a8e0f2806cad6', 'bitacora': '85ddf91c14b100a857282e0ed3c58622', 'nuevo:tests/test_cargar_hoja_rh.py': '6e164550339bee8bc99ce273db712b7a'}

textos = {k: io.open(v, encoding="utf-8", newline="").read()
          for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(clave)
        return
    assert t.count(viejo) == 1, (
        f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces. "
        "No se escribio nada.")
    textos[clave] = t.replace(viejo, nuevo)


cambiar('cargador',
        '\n  * A cada persona se le encuentra por el No. Odoo, y ademas el nombre de\n    la fila tiene que ser el de Odoo: una fila movida no le escribe a\n    otra persona. Si no coincide, la fila entera se salta.\n  * Una casilla vacia no borra lo que Odoo ya tiene.\n  * Lo que no pasa la revision --una plaza que no es de las cuatro, un\n    celular de menos de diez digitos, un correo mal escrito o repetido,\n',
        '\n  * A cada persona se le encuentra por el No. Odoo, y ademas el nombre de\n    la fila tiene que ser el de Odoo: una fila movida no le escribe a\n    otra persona. Si no coincide, la fila entera se salta, y la persona\n    no se da por vista: si su fila buena viene despues, se toma.\n  * Una casilla vacia no borra lo que Odoo ya tiene.\n  * Lo que no pasa la revision --una plaza que no es de las cuatro, un\n    celular de menos de diez digitos, un correo mal escrito o repetido,\n')

cambiar('cargador',
        '        if e is None:\n            saltadas["no es personal de seguridad en Odoo"] += 1\n            continue\n        if e["id"] in vistos:\n            saltadas["la persona viene dos veces"] += 1\n            continue\n        vistos.add(e["id"])\n        if normal(celda(fila.get("nombre"))) != normal(e.get("name")):\n            saltadas["el nombre de la fila no es el de Odoo"] += 1\n            continue\n\n        # La hoja trae lo que Odoo ya tenia: solo se revisa y se escribe lo\n        # que cambia.\n',
        '        if e is None:\n            saltadas["no es personal de seguridad en Odoo"] += 1\n            continue\n        # Primero el nombre y despues si ya vino: una fila movida no le\n        # aparta el numero a la fila buena que viene mas abajo.\n        if normal(celda(fila.get("nombre"))) != normal(e.get("name")):\n            saltadas["el nombre de la fila no es el de Odoo"] += 1\n            continue\n        if e["id"] in vistos:\n            saltadas["la persona viene dos veces"] += 1\n            continue\n        vistos.add(e["id"])\n\n        # La hoja trae lo que Odoo ya tenia: solo se revisa y se escribe lo\n        # que cambia.\n')

cambiar('reglas',
        '  * El Estado de Mexico va como Ciudad de Mexico: es la misma zona\n    metropolitana.\n  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.\n"""\nimport collections\nimport re\n',
        '  * El Estado de Mexico va como Ciudad de Mexico: es la misma zona\n    metropolitana.\n  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.\n\nY del 24 de septiembre: un celular que no es un numero --en Odoo hay\nfichas que dicen «sin dispositivo»-- no se guarda como telefono ni borra\nel que Centauro ya tiene; el informe lo cuenta aparte. No detiene el\nalta: la persona entra sin celular.\n"""\nimport collections\nimport re\n')

cambiar('reglas',
        '    "hotmial.com", "hotmal.com", "hotmail.con", "hotamil.com",\n    "yaho.com", "yahoo.con", "outlok.com", "outlook.con"})\nCORREO_VALIDO = re.compile(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")\n\n# Como empieza cada imagen en base64. El SVG no esta porque es el avatar\n# de iniciales que Odoo le pone a quien no tiene foto: no es una foto, y\n',
        '    "hotmial.com", "hotmal.com", "hotmail.con", "hotamil.com",\n    "yaho.com", "yahoo.con", "outlok.com", "outlook.con"})\nCORREO_VALIDO = re.compile(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")\n# Un celular ya con la lada de su pais tiene al menos diez digitos en toda\n# la region: +52 y diez en Mexico, +55 y diez u once en Brasil, +51 y\n# nueve en Peru. Lo que no llega no es un numero al que se pueda llamar.\nDIGITOS_CELULAR = 10\n\n# Como empieza cada imagen en base64. El SVG no esta porque es el avatar\n# de iniciales que Odoo le pone a quien no tiene foto: no es una foto, y\n')

cambiar('reglas',
        '    return None\n\n\ndef plaza_de(empleado: dict, plazas: dict) -> tuple:\n    """(plaza o None, lo que dice Odoo). `plazas` va por nombre normalizado."""\n    lugar = nombre_de(empleado.get("work_location_id"))\n',
        '    return None\n\n\ndef es_celular(numero) -> bool:\n    """Si el telefono, ya con su lada, es un numero y no un texto."""\n    return sum(c.isdigit() for c in texto(numero)) >= DIGITOS_CELULAR\n\n\ndef plaza_de(empleado: dict, plazas: dict) -> tuple:\n    """(plaza o None, lo que dice Odoo). `plazas` va por nombre normalizado."""\n    lugar = nombre_de(empleado.get("work_location_id"))\n')

cambiar('reglas',
        '\n    plan = {"leidos": len(elegidos), "altas": [], "vinculos": [],\n            "cambios": [], "fotos": [], "pendientes": [], "sin_cambio": 0,\n            "procesadas": [], "revisar_salida": []}\n    tomados = set()        # correos que este plan ya aparto\n\n    def pendiente(e, persona_id, faltas):\n        plan["pendientes"].append({"odoo_id": e["id"], "persona_id": persona_id,\n                                   "nombre": texto(e.get("name")),\n                                   "falta": faltas})\n\n    for e in elegidos:\n        nombre = texto(e.get("name"))\n',
        '\n    plan = {"leidos": len(elegidos), "altas": [], "vinculos": [],\n            "cambios": [], "fotos": [], "pendientes": [], "sin_cambio": 0,\n            "procesadas": [], "revisar_salida": [], "celular_no_valido": []}\n    tomados = set()        # correos que este plan ya aparto\n\n    def pendiente(e, persona_id, faltas):\n        plan["pendientes"].append({"odoo_id": e["id"], "persona_id": persona_id,\n                                   "nombre": texto(e.get("name")),\n                                   "falta": faltas})\n\n    def celular(e, pais_id, persona_id, nombre):\n        """El celular de Odoo con su lada, o None si Odoo no trae un numero."""\n        escrito = texto(e.get("mobile_phone"))\n        if not escrito:\n            return None\n        numero = normalizar_tel(escrito, pais_id)\n        if es_celular(numero):\n            return numero\n        plan["celular_no_valido"].append({"odoo_id": e["id"],\n                                          "persona_id": persona_id,\n                                          "nombre": nombre})\n        return None\n\n    for e in elegidos:\n        nombre = texto(e.get("name"))\n')

cambiar('reglas',
        '                pendiente(e, None, faltas)\n                continue\n            tomados.add(correo)\n            celular = texto(e.get("mobile_phone"))\n            plan["altas"].append({\n                "odoo_id": e["id"], "nombre": nombre, "correo": correo,\n                "plaza_id": plaza["id"], "plaza": plaza["nombre"],\n                "telefono": (normalizar_tel(celular, plaza["pais_id"])\n                             if celular else None),\n                "referencia": texto(e.get("registration_number")) or None,\n                "fecha_ingreso": fecha(e.get("first_contract_date"))})\n            plan["fotos"].append(e["id"])\n',
        '                pendiente(e, None, faltas)\n                continue\n            tomados.add(correo)\n            plan["altas"].append({\n                "odoo_id": e["id"], "nombre": nombre, "correo": correo,\n                "plaza_id": plaza["id"], "plaza": plaza["nombre"],\n                "telefono": celular(e, plaza["pais_id"], None, nombre),\n                "referencia": texto(e.get("registration_number")) or None,\n                "fecha_ingreso": fecha(e.get("first_contract_date"))})\n            plan["fotos"].append(e["id"])\n')

cambiar('reglas',
        '            que.append("plaza")\n        elif plaza is None and lugar:\n            avisos.append(f"la plaza «{lugar}» no existe en Centauro")\n        celular = texto(e.get("mobile_phone"))\n        if celular:\n            pais = plaza["pais_id"] if plaza is not None else persona.get("pais_id")\n            tel = normalizar_tel(celular, pais)\n            if tel and tel != persona.get("telefono"):\n                valores["telefono"] = tel\n                que.append("celular")\n        referencia = texto(e.get("registration_number"))\n        if referencia and referencia != persona.get("referencia"):\n            valores["referencia"] = referencia\n',
        '            que.append("plaza")\n        elif plaza is None and lugar:\n            avisos.append(f"la plaza «{lugar}» no existe en Centauro")\n        pais = plaza["pais_id"] if plaza is not None else persona.get("pais_id")\n        tel = celular(e, pais, persona["id"], nombre or persona.get("nombre"))\n        if tel and tel != persona.get("telefono"):\n            valores["telefono"] = tel\n            que.append("celular")\n        referencia = texto(e.get("registration_number"))\n        if referencia and referencia != persona.get("referencia"):\n            valores["referencia"] = referencia\n')

cambiar('personal',
        '                             for p, _ in por_cerrar],\n        "pendientes": plan["pendientes"],\n        "sin_cambio": plan["sin_cambio"],\n        # «sin_foto_real»: Odoo solo tiene el circulo con sus iniciales.\n        "fotos": {"revisadas": len(filas_de_foto), "reales": reales,\n                  "sin_foto_real": len(filas_de_foto) - reales,\n',
        '                             for p, _ in por_cerrar],\n        "pendientes": plan["pendientes"],\n        "sin_cambio": plan["sin_cambio"],\n        # Odoo dice algo que no es un numero («sin dispositivo»): no se\n        # guardo como telefono ni borro el que ya habia.\n        "celular_no_valido": plan["celular_no_valido"],\n        # «sin_foto_real»: Odoo solo tiene el circulo con sus iniciales.\n        "fotos": {"revisadas": len(filas_de_foto), "reales": reales,\n                  "sin_foto_real": len(filas_de_foto) - reales,\n')

cambiar('personal',
        '            "cambios": len(informe["cambios"]), "bajas": len(informe["bajas"]),\n            "accesos_cerrados": len(informe["accesos_cerrados"]),\n            "sin_cambio": informe["sin_cambio"],\n            "pendientes": faltas, "fotos": informe["fotos"]}\n\n\n',
        '            "cambios": len(informe["cambios"]), "bajas": len(informe["bajas"]),\n            "accesos_cerrados": len(informe["accesos_cerrados"]),\n            "sin_cambio": informe["sin_cambio"],\n            "celular_no_valido": len(informe.get("celular_no_valido", [])),\n            "pendientes": faltas, "fotos": informe["fotos"]}\n\n\n')

cambiar('sincronizar',
        '    print(f"Fotos revisadas: {fotos[\'revisadas\']} · de verdad: "\n          f"{fotos[\'reales\']} · solo iniciales: {fotos[\'sin_foto_real\']}"\n          + (f" · guardadas: {fotos[\'actualizadas\']}" if aplicar else ""))\n    if r["pendientes"]:\n        print("Pendientes, por motivo:")\n        for motivo, cuantos in sorted(r["pendientes"].items(),\n',
        '    print(f"Fotos revisadas: {fotos[\'revisadas\']} · de verdad: "\n          f"{fotos[\'reales\']} · solo iniciales: {fotos[\'sin_foto_real\']}"\n          + (f" · guardadas: {fotos[\'actualizadas\']}" if aplicar else ""))\n    if r["celular_no_valido"]:\n        print(f"Celular que en Odoo no es un numero: {r[\'celular_no_valido\']} "\n              "(no se guarda y no borra el que ya habia)")\n    if r["pendientes"]:\n        print("Pendientes, por motivo:")\n        for motivo, cuantos in sorted(r["pendientes"].items(),\n')

cambiar('t_personal',
        '    assert (p.telefono, p.referencia) == ("+52 33 1111 2222", "PO-1")\n\n\ndef test_quien_ya_estaba_en_centauro_se_vincula_por_su_correo(\n        cliente, sesion, datos, db):\n    h = sesion("admin")\n',
        '    assert (p.telefono, p.referencia) == ("+52 33 1111 2222", "PO-1")\n\n\ndef test_un_celular_que_no_es_numero_no_se_guarda_ni_borra(db):\n    # En Odoo hay fichas que en el celular dicen «sin dispositivo».\n    odoo = OdooFalso(empleado(1, mobile_phone="Sin dispositivo"),\n                     empleado(2), empleado(3, mobile_phone="555 1234"))\n    informe = leer(db, odoo)\n    # No detiene el alta: entran, sin celular.\n    assert len(informe["altas"]) == 3 and not informe["pendientes"]\n    assert (persona(db, 1).telefono, persona(db, 3).telefono) == (None, None)\n    assert sorted(c["odoo_id"] - ODOO0\n                  for c in informe["celular_no_valido"]) == [1, 3]\n    assert odoo_personal.resumen(informe)["celular_no_valido"] == 2\n\n    # A quien ya tiene celular, un texto en Odoo no se lo borra...\n    odoo.cambiar(2, mobile_phone="N/A")\n    informe = leer(db, odoo)\n    assert not informe["cambios"]\n    assert persona(db, 2).telefono == "+52 55 5000 0002"\n    assert sorted(c["odoo_id"] - ODOO0\n                  for c in informe["celular_no_valido"]) == [1, 2, 3]\n    # ...y cuando Odoo ya trae el numero, entra con su lada.\n    odoo.cambiar(1, mobile_phone="5512345678")\n    informe = leer(db, odoo)\n    assert [c["que"] for c in informe["cambios"]] == [["celular"]]\n    assert persona(db, 1).telefono == "+52 5512345678"\n\n\ndef test_quien_ya_estaba_en_centauro_se_vincula_por_su_correo(\n        cliente, sesion, datos, db):\n    h = sesion("admin")\n')

cambiar('bitacora',
        'antes de importar nada, y la pausa por un 429 es de cada sitio: la de una\nprueba ya no puede borrar la del Pegasus de verdad.\n\n## 14. Lo que falta\n\n### Abierto\n',
        'antes de importar nada, y la pausa por un 429 es de cada sitio: la de una\nprueba ya no puede borrar la del Pegasus de verdad.\n\n## 62. La hoja de RH, cargada a Odoo\n\nRH devolvió la hoja del personal de seguridad (`hoja_rh_odoo.py`, sacada\nde Odoo la noche del 22 de septiembre) con lo que faltaba, y\n`cargar_hoja_rh.py` la subió a Odoo el 23 en la noche, con ensayo, visto\nbueno de Salvador y la bitácora para deshacer\n(`odoo_cambios_hoja_20260923_2207.json`, fuera de git): **65 personas,\n62 plazas, 5 celulares, 1 correo personal y 3 referencias**. La plaza era\nlo que detenía todo: sin ella la lectura del personal (sección 51) deja a\nla persona pendiente y no la da de alta.\n\n- **El No. Odoo venía recorrido** en 16 filas, con números repetidos y\n  nombres distintos. El cargador no le escribe a quien no es, pero se\n  habría saltado a 25 personas. Los correos y las referencias sí\n  cuadraban con cada nombre, así que se hizo una copia con el número\n  corregido por el nombre, lo cambiado en naranja y una columna\n  «Revisión Centauro» que dice qué pasa con cada fila y sirve para\n  devolverle a RH. La hoja de RH no se tocó.\n- **Lo que Odoo ya tenía más nuevo no se pisó.** Un revisor de solo\n  lectura comparó Odoo con la hoja que se sacó: un celular que ya habían\n  cambiado en Odoo se quedó como estaba. Tres personas tienen en Odoo la\n  ubicación «Office» y RH puso Ciudad de México; Salvador decidió dejarlas\n  así, de modo que la lectura del personal las deja pendientes hasta que\n  tengan una plaza de Centauro.\n- **Lo que le queda a RH, en Odoo:** 5 altas (una es un supervisor), 3\n  bajas y una renuncia en proceso por archivar, una persona de oficina con\n  puesto de seguridad y 2 supervisores que no hacen servicios —su puesto\n  decide si salen en Centauro—, 4 números que RH no reconoce y 7 personas\n  sin ningún celular.\n\nDe paso, dos arreglos:\n\n- **El cargador** revisaba si la persona ya había venido antes de revisar\n  el nombre: una fila movida le apartaba el número a la fila buena que\n  venía después. Ahora primero el nombre.\n- **La lectura del personal** tomaba como teléfono lo que dijera Odoo, y\n  en tres fichas dice «sin dispositivo». Ahora, si el celular ya con su\n  lada no llega a diez dígitos —en toda la región un celular con lada\n  tiene al menos diez—, no se guarda ni borra el que había, el alta sigue\n  sin celular, y el informe y `sincronizar_personal.py` lo cuentan aparte.\n\n## 14. Lo que falta\n\n### Abierto\n')


# ============================================================ comprobar
def _md5(texto):
    return hashlib.md5(texto.encode("utf-8")).hexdigest()


distintos = [clave for clave in ARCHIVOS
             if _md5(textos[clave]) != ESPERADO[clave]]
distintos += [rel for rel, contenido in NUEVOS.items()
              if _md5(contenido) != ESPERADO["nuevo:" + rel]]
if distintos:
    raise SystemExit("Estos archivos no quedarian como los que se probaron: "
                     + ", ".join(distintos) + ". No se escribio nada.")

# ============================================================ escrituras
for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8", newline="").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8", newline="") as f:
            f.write(textos[clave])
        print("escrito  ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for relativa, contenido in NUEVOS.items():
    ruta = B / relativa
    if ruta.exists() and io.open(ruta, encoding="utf-8", newline="").read() == contenido:
        print("sin cambio", ruta.relative_to(RAIZ))
    else:
        with io.open(ruta, "w", encoding="utf-8", newline="") as f:
            f.write(contenido)
        print("escrito  ", ruta.relative_to(RAIZ))
if saltados:
    print("ya estaban:", len(saltados), "cambios")

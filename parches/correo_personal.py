# -*- coding: utf-8 -*-
"""El personal de seguridad entra con su correo personal (seccion 63).

Decision de Salvador, 23 de septiembre: "sera mejor que siempre tomes el
correo personal como bueno. muy pronto suspendere las cuentas de correo
del personal de seguridad unicamente".

  * La lectura del personal de Odoo: el correo de acceso es siempre el
    personal; sin el, la persona queda pendiente aunque tenga el de
    trabajo. El de trabajo solo reconoce, la primera vez, a quien ya
    estaba en Centauro con el, y desde ahi entra con el personal. A quien
    ya esta y le falta el personal no se le cierra el acceso: queda
    pendiente hasta que RH se lo ponga.
  * hoja_rh_odoo.py pide el correo personal; cargar_hoja_rh.py revisa las
    repeticiones contra el personal.
  * Pruebas: test_odoo_personal.py y test_cargar_hoja_rh.py. BITACORA,
    seccion 63.

Sin migracion. Idempotente. Todo se arma en memoria, se comprueba contra
lo que se probo (md5 por archivo) y solo entonces se escribe.
"""
import hashlib
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    'reglas': RAIZ / 'backend/app/odoo_personal_reglas.py',
    'cargador': RAIZ / 'backend/cargar_hoja_rh.py',
    'hoja_rh': RAIZ / 'backend/hoja_rh_odoo.py',
    't_personal': RAIZ / 'backend/tests/test_odoo_personal.py',
    't_cargador': RAIZ / 'backend/tests/test_cargar_hoja_rh.py',
    'bitacora': RAIZ / 'BITACORA.md',
}
NUEVOS = {}
ESPERADO = {'reglas': 'a32f70717391f41d985b581c729635e8', 'cargador': '591dc589f620c6b24c330395269603f4', 'hoja_rh': 'a82afafa55e07039ec6d01ccfbf4f52a', 't_personal': '7ac112e90f5b1cf7f49ecbd260362454', 't_cargador': 'dbc4cf40f71d5a030ffb4c94d5a4ee07', 'bitacora': '534b0231e0e76ccc0e637c52c1817549'}

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


cambiar('reglas',
        '  * Entra el personal de seguridad: puesto «Personal de Seguridad...» o\n    «Security Driver...». Monitoristas, oficina y guardias no.\n  * La llave es el numero interno de Odoo.\n  * El correo con el que entra a la app es el de trabajo o, si no tiene,\n    el personal.\n  * El Estado de Mexico va como Ciudad de Mexico: es la misma zona\n    metropolitana.\n  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.\n\nY del 24 de septiembre: un celular que no es un numero --en Odoo hay\nfichas que dicen «sin dispositivo»-- no se guarda como telefono ni borra\nel que Centauro ya tiene; el informe lo cuenta aparte. No detiene el\nalta: la persona entra sin celular.\n"""\nimport collections\nimport re\n',
        '  * Entra el personal de seguridad: puesto «Personal de Seguridad...» o\n    «Security Driver...». Monitoristas, oficina y guardias no.\n  * La llave es el numero interno de Odoo.\n  * El Estado de Mexico va como Ciudad de Mexico: es la misma zona\n    metropolitana.\n  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.\n\nY de esa misma noche, ya con la hoja de RH cargada:\n\n  * El correo con el que entra a la app es SIEMPRE el personal. Los\n    correos de trabajo del personal de seguridad se van a suspender. El de\n    trabajo solo sirve para reconocer, la primera vez, a quien ya estaba\n    en Centauro con el; desde ahi entra con el personal. (Antes era el de\n    trabajo y, si no tenia, el personal.)\n  * Un celular que no es un numero --en Odoo hay fichas que dicen «sin\n    dispositivo»-- no se guarda como telefono ni borra el que Centauro ya\n    tiene; el informe lo cuenta aparte. No detiene el alta: la persona\n    entra sin celular.\n"""\nimport collections\nimport re\n')

cambiar('reglas',
        '\n\ndef correo_de(empleado: dict) -> str:\n    for campo in ("work_email", "private_email"):\n        valor = texto(empleado.get(campo)).lower()\n        if valor:\n            return valor\n    return ""\n\n\ndef problema_de_correo(correo: str) -> str | None:\n    if not correo:\n        return "sin correo"\n    if not CORREO_VALIDO.match(correo):\n        return "correo mal escrito"\n    if correo.split("@")[-1] in DOMINIOS_RAROS:\n',
        '\n\ndef correo_de(empleado: dict) -> str:\n    """El correo con el que entra a la app: el personal, siempre."""\n    return texto(empleado.get("private_email")).lower()\n\n\ndef correo_de_trabajo(empleado: dict) -> str:\n    """Solo para reconocer a quien ya estaba en Centauro con este."""\n    return texto(empleado.get("work_email")).lower()\n\n\ndef problema_de_correo(correo: str) -> str | None:\n    if not correo:\n        return "sin correo personal"\n    if not CORREO_VALIDO.match(correo):\n        return "correo mal escrito"\n    if correo.split("@")[-1] in DOMINIOS_RAROS:\n')

cambiar('reglas',
        '                  for p in personas if p.get("correo")}\n    cuenta = collections.Counter(correo_de(e) for e in elegidos if correo_de(e))\n    repetidos = {c for c, n in cuenta.items() if n > 1}\n\n    plan = {"leidos": len(elegidos), "altas": [], "vinculos": [],\n            "cambios": [], "fotos": [], "pendientes": [], "sin_cambio": 0,\n',
        '                  for p in personas if p.get("correo")}\n    cuenta = collections.Counter(correo_de(e) for e in elegidos if correo_de(e))\n    repetidos = {c for c, n in cuenta.items() if n > 1}\n    de_trabajo = collections.Counter(correo_de_trabajo(e) for e in elegidos\n                                     if correo_de_trabajo(e))\n\n    plan = {"leidos": len(elegidos), "altas": [], "vinculos": [],\n            "cambios": [], "fotos": [], "pendientes": [], "sin_cambio": 0,\n')

cambiar('reglas',
        '        plaza, lugar = plaza_de(e, plazas)\n\n        persona, vinculo = por_odoo.get(e["id"]), False\n        if persona is None and correo and not problema:\n            candidata = por_correo.get(correo)\n            if candidata is not None:\n                if candidata.get("odoo_id") and candidata["odoo_id"] != e["id"]:\n                    pendiente(e, candidata["id"],\n',
        '        plaza, lugar = plaza_de(e, plazas)\n\n        persona, vinculo = por_odoo.get(e["id"]), False\n        if persona is None:\n            # Quien ya estaba en Centauro se reconoce por su correo: el\n            # personal o, si lo capturaron con el de trabajo, ese. Solo un\n            # correo bien escrito y que nadie mas trae en Odoo.\n            trabajo = correo_de_trabajo(e)\n            posibles = [c for c, sirve in (\n                (correo, correo and not problema),\n                (trabajo, trabajo and de_trabajo[trabajo] == 1\n                 and not problema_de_correo(trabajo))) if sirve]\n            candidata = next((por_correo[c] for c in posibles\n                              if c in por_correo), None)\n            if candidata is not None:\n                if candidata.get("odoo_id") and candidata["odoo_id"] != e["id"]:\n                    pendiente(e, candidata["id"],\n')

cambiar('reglas',
        '                valores["correo"] = correo\n                que.append("correo")\n                tomados.add(correo)\n\n        # La foto se vuelve a pedir solo si Odoo toco la ficha despues de\n        # la ultima lectura: subir una foto cambia el write_date. Quien\n',
        '                valores["correo"] = correo\n                que.append("correo")\n                tomados.add(correo)\n        elif not correo:\n            # Sigue entrando con el que ya tenia, pero RH tiene que poner\n            # el personal: el de trabajo se va a suspender.\n            avisos.append(problema)\n\n        # La foto se vuelve a pedir solo si Odoo toco la ficha despues de\n        # la ultima lectura: subir una foto cambia el write_date. Quien\n')

cambiar('cargador',
        '        propuestas[e["id"]] = {c: v for c, v in nuevo.items()\n                               if not igual(c, v, e)}\n\n    # El correo con el que entra a la app --el de trabajo o, si no tiene, el\n    # personal-- no puede ser el de otra persona. Lo que la hoja trae y\n    # causaria la repeticion no se escribe.\n    def valor(ident, campo):\n        if campo in propuestas.get(ident, {}):\n            return propuestas[ident][campo]\n        return texto(seguridad[ident].get(campo)).lower()\n\n    def acceso_de(ident):\n        return valor(ident, "work_email") or valor(ident, "private_email")\n\n    grupos = collections.defaultdict(list)\n    for ident in seguridad:\n',
        '        propuestas[e["id"]] = {c: v for c, v in nuevo.items()\n                               if not igual(c, v, e)}\n\n    # El correo con el que entra a la app --el personal, siempre: los de\n    # trabajo del personal de seguridad se van a suspender-- no puede ser el\n    # de otra persona. Lo que la hoja trae y causaria la repeticion no se\n    # escribe.\n    def valor(ident, campo):\n        if campo in propuestas.get(ident, {}):\n            return propuestas[ident][campo]\n        return texto(seguridad[ident].get(campo)).lower()\n\n    def acceso_de(ident):\n        return valor(ident, "private_email")\n\n    grupos = collections.defaultdict(list)\n    for ident in seguridad:\n')

cambiar('cargador',
        '            continue\n        for ident in ids:\n            p = propuestas.get(ident, {})\n            quitados = [c for c in ("work_email", "private_email")\n                        if p.get(c) == correo]\n            for c in quitados:\n                p.pop(c)\n            if quitados:\n                no_se_escribe["correo repetido con otra persona"] += 1\n    # Lo que sigue repetido despues de esto ya venia asi de Odoo.\n    quedan = collections.Counter(acceso_de(i) for i in seguridad if acceso_de(i))\n',
        '            continue\n        for ident in ids:\n            p = propuestas.get(ident, {})\n            if p.get("private_email") == correo:\n                p.pop("private_email")\n                no_se_escribe["correo repetido con otra persona"] += 1\n    # Lo que sigue repetido despues de esto ya venia asi de Odoo.\n    quedan = collections.Counter(acceso_de(i) for i in seguridad if acceso_de(i))\n')

cambiar('hoja_rh',
        '            falta.append("celular")\n        if not texto(e.get("registration_number")):\n            falta.append("referencia")\n        if not trabajo and not personal:\n            falta.append("correo")\n        if not foto:\n            falta.append("foto")\n        dudosos = [c for c in (trabajo, personal) if c and (\n',
        '            falta.append("celular")\n        if not texto(e.get("registration_number")):\n            falta.append("referencia")\n        # Con el personal entra a la app: los de trabajo del personal de\n        # seguridad se van a suspender.\n        if not personal:\n            falta.append("correo personal")\n        if not foto:\n            falta.append("foto")\n        dudosos = [c for c in (trabajo, personal) if c and (\n')

cambiar('hoja_rh',
        '                celda.fill = amarillo\n            elif clave in ("trabajo", "personal") and valor in fila["dudosos"]:\n                celda.fill = naranja\n            elif clave == "personal" and not fila["trabajo"] and not fila["personal"]:\n                celda.fill = amarillo\n        if fila["foto"] == "No":\n            hoja.cell(row=r, column=9).fill = amarillo\n',
        '                celda.fill = amarillo\n            elif clave in ("trabajo", "personal") and valor in fila["dudosos"]:\n                celda.fill = naranja\n            elif clave == "personal" and not fila["personal"]:\n                celda.fill = amarillo\n        if fila["foto"] == "No":\n            hoja.cell(row=r, column=9).fill = amarillo\n')

cambiar('hoja_rh',
        '        (f"Hecha el {datetime.now():%d/%m/%Y} desde Odoo. {len(filas)} personas.", False),\n        ("", False),\n        ("Qué hacer", True),\n        ("1. Llenar las casillas en amarillo: plaza, celular de trabajo y referencia de empleado.", False),\n        ("2. Revisar las casillas en naranja: son correos con un error de dedo probable o repetidos.", False),\n        ("3. Cada persona necesita al menos un correo que funcione: con él entra a la app de campo.", False),\n        ("4. Si algo ya estaba pero está mal, se corrige aquí mismo, encima.", False),\n        ("5. La foto no va en esta hoja: se sube en Odoo, en la ficha de la persona. "\n         "El círculo con iniciales no es foto.", False),\n',
        '        (f"Hecha el {datetime.now():%d/%m/%Y} desde Odoo. {len(filas)} personas.", False),\n        ("", False),\n        ("Qué hacer", True),\n        ("1. Llenar las casillas en amarillo: plaza, celular de trabajo, correo personal y referencia de empleado.", False),\n        ("2. Revisar las casillas en naranja: son correos con un error de dedo probable o repetidos.", False),\n        ("3. Cada persona necesita su correo personal: con él entra a la app de campo. "\n         "Los correos de trabajo del personal de seguridad se van a suspender.", False),\n        ("4. Si algo ya estaba pero está mal, se corrige aquí mismo, encima.", False),\n        ("5. La foto no va en esta hoja: se sube en Odoo, en la ficha de la persona. "\n         "El círculo con iniciales no es foto.", False),\n')

cambiar('hoja_rh',
        '\n    print(f"Hoja lista: {nombre}, con {len(filas)} personas.")\n    print("Faltan: " + " · ".join(f"{k} {falta_total[k]}" for k in\n                                   ("plaza", "celular", "referencia", "correo", "foto")))\n    print(f"Personas con un correo que revisar: {revisar}")\n    return 0\n\n',
        '\n    print(f"Hoja lista: {nombre}, con {len(filas)} personas.")\n    print("Faltan: " + " · ".join(f"{k} {falta_total[k]}" for k in\n                                   ("plaza", "celular", "referencia", "correo personal", "foto")))\n    print(f"Personas con un correo que revisar: {revisar}")\n    return 0\n\n')

cambiar('t_personal',
        '         "job_id": [90, "Personal de Seguridad"],\n         "job_title": "Personal de Seguridad",\n         "work_location_id": [30, "Ciudad de México"],\n         "work_email": f"agente{n}@{DOMINIO}", "private_email": False,\n         "mobile_phone": f"55 5000 {n:04d}", "registration_number": f"PO-{n}",\n         "first_contract_date": "2024-03-01",\n         "write_date": "2026-01-01 10:00:00", "active": True}\n',
        '         "job_id": [90, "Personal de Seguridad"],\n         "job_title": "Personal de Seguridad",\n         "work_location_id": [30, "Ciudad de México"],\n         # Entra con el personal; el de trabajo se va a suspender.\n         "work_email": f"agente{n}.trabajo@{DOMINIO}",\n         "private_email": f"agente{n}@{DOMINIO}",\n         "mobile_phone": f"55 5000 {n:04d}", "registration_number": f"PO-{n}",\n         "first_contract_date": "2024-03-01",\n         "write_date": "2026-01-01 10:00:00", "active": True}\n')

cambiar('t_personal',
        '    informe = leer(db, OdooFalso(\n        empleado(1, work_location_id=False),\n        empleado(2, work_location_id=[31, "Home"]),\n        empleado(3, work_email="agente3@gamil.com"),\n        empleado(4, work_email=f"repetido@{DOMINIO}"),\n        empleado(5, work_email=f"repetido@{DOMINIO}"),\n        empleado(6, work_email=False, private_email=False)))\n    assert not informe["altas"]\n    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}\n    assert faltas == {\n',
        '    informe = leer(db, OdooFalso(\n        empleado(1, work_location_id=False),\n        empleado(2, work_location_id=[31, "Home"]),\n        empleado(3, private_email="agente3@gamil.com"),\n        empleado(4, private_email=f"repetido@{DOMINIO}"),\n        empleado(5, private_email=f"repetido@{DOMINIO}"),\n        empleado(6, work_email=False, private_email=False),\n        # Con el de trabajo solo no entra: ese se va a suspender.\n        empleado(7, private_email=False)))\n    assert not informe["altas"]\n    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}\n    assert faltas == {\n')

cambiar('t_personal',
        '        3: ["correo con error de dedo"],\n        4: ["correo repetido en Odoo"],\n        5: ["correo repetido en Odoo"],\n        6: ["sin correo"],\n    }\n    assert de_prueba(db) == 0\n\n',
        '        3: ["correo con error de dedo"],\n        4: ["correo repetido en Odoo"],\n        5: ["correo repetido en Odoo"],\n        6: ["sin correo personal"],\n        7: ["sin correo personal"],\n    }\n    assert de_prueba(db) == 0\n\n')

cambiar('t_personal',
        'def test_lo_que_cambia_en_odoo_cambia_aqui_y_lo_vacio_no_borra(db):\n    odoo = OdooFalso(empleado(1))\n    leer(db, odoo)\n    odoo.cambiar(1, name="Agente Odoo Uno", work_email=f"uno@{DOMINIO}",\n                 work_location_id=[33, "Guadalajara"],\n                 mobile_phone="33 1111 2222")\n    informe = leer(db, odoo)\n',
        'def test_lo_que_cambia_en_odoo_cambia_aqui_y_lo_vacio_no_borra(db):\n    odoo = OdooFalso(empleado(1))\n    leer(db, odoo)\n    odoo.cambiar(1, name="Agente Odoo Uno", private_email=f"uno@{DOMINIO}",\n                 work_location_id=[33, "Guadalajara"],\n                 mobile_phone="33 1111 2222")\n    informe = leer(db, odoo)\n')

cambiar('t_personal',
        '    # La misma persona, con lo que dice Odoo, y un solo acceso.\n    assert (p.id, p.nombre) == (r.json()["id"], "Agente Odoo 1")\n    assert db.query(m.Usuario).filter_by(persona_id=p.id).count() == 1\n\n\ndef test_el_circulo_de_iniciales_no_es_foto_y_la_foto_nueva_se_toma(db):\n',
        '    # La misma persona, con lo que dice Odoo, y un solo acceso.\n    assert (p.id, p.nombre) == (r.json()["id"], "Agente Odoo 1")\n    assert db.query(m.Usuario).filter_by(persona_id=p.id).count() == 1\n\n\ndef test_quien_estaba_con_el_correo_de_trabajo_pasa_a_entrar_con_el_personal(\n        cliente, sesion, datos, db):\n    # Salvador, 23 de septiembre: los correos de trabajo del personal de\n    # seguridad se van a suspender. El de trabajo reconoce a la persona la\n    # primera vez; desde ahi entra con el personal.\n    h = sesion("admin")\n    r = cliente.post("/catalogos/personal", headers=h, json={\n        "nombre": "Capturado Con El De Trabajo",\n        "correo": f"agente1.trabajo@{DOMINIO}",\n        "plaza_id": datos["cdmx"]["id"]})\n    assert r.status_code == 201, r.text\n    alta = cliente.post("/auth/usuarios", headers=h, json={\n        "persona_id": r.json()["id"], "rol": "personal_seguridad"})\n    assert alta.status_code == 201, alta.text\n\n    odoo = OdooFalso(empleado(1))\n    informe = leer(db, odoo)\n    assert not informe["altas"]\n    assert [v["persona_id"] for v in informe["vinculadas"]] == [r.json()["id"]]\n    assert "correo" in informe["cambios"][0]["que"]\n    p = persona(db, 1)\n    assert (p.id, p.correo) == (r.json()["id"], f"agente1@{DOMINIO}")\n    usuario = db.query(m.Usuario).filter_by(persona_id=p.id).one()\n    assert usuario.correo == f"agente1@{DOMINIO}"\n\n    # Si RH le borra el personal en Odoo, sigue entrando con el que tenia\n    # y queda pendiente hasta que se lo pongan.\n    odoo.cambiar(1, private_email=False)\n    informe = leer(db, odoo)\n    assert [(q["odoo_id"] - ODOO0, q["falta"]) for q in informe["pendientes"]] == [\n        (1, ["sin correo personal"])]\n    assert persona(db, 1).correo == f"agente1@{DOMINIO}"\n\n\ndef test_el_circulo_de_iniciales_no_es_foto_y_la_foto_nueva_se_toma(db):\n')

cambiar('t_cargador',
        '            "registration_number": False}\n\n\ndef fila(n, plaza, nombre=None):\n    return {"id": n, "nombre": nombre or f"Agente {n}",\n            "work_location_id": plaza, "mobile_phone": None,\n            "work_email": None, "private_email": None,\n            "registration_number": None, "notas": None}\n\n\nGDL, MTY = hoja.PLAZAS.index("Guadalajara") + 1, hoja.PLAZAS.index("Monterrey") + 1\n\n\ndef test_una_fila_movida_no_le_quita_su_numero_a_la_fila_buena():\n    # Paso con la hoja del 24 de septiembre: un bloque de filas quedo con\n    # el No. Odoo de otras personas. La fila movida se salta y la buena,\n    # que viene despues con el mismo numero, se toma.\n    ops, resumen = hoja.calcular(OdooFalso(empleado(1), empleado(2)), [\n',
        '            "registration_number": False}\n\n\ndef fila(n, plaza, nombre=None, **valores):\n    f = {"id": n, "nombre": nombre or f"Agente {n}",\n         "work_location_id": plaza, "mobile_phone": None,\n         "work_email": None, "private_email": None,\n         "registration_number": None, "notas": None}\n    f.update(valores)\n    return f\n\n\nGDL, MTY = hoja.PLAZAS.index("Guadalajara") + 1, hoja.PLAZAS.index("Monterrey") + 1\n\n\ndef test_una_fila_movida_no_le_quita_su_numero_a_la_fila_buena():\n    # Paso con la hoja que RH devolvio el 23 de septiembre: un bloque quedo con\n    # el No. Odoo de otras personas. La fila movida se salta y la buena,\n    # que viene despues con el mismo numero, se toma.\n    ops, resumen = hoja.calcular(OdooFalso(empleado(1), empleado(2)), [\n')

cambiar('t_cargador',
        '        fila(1, "Guadalajara")])\n    assert [op["valores"] for op in ops] == [{"work_location_id": MTY}]\n    assert "      1  la persona viene dos veces" in resumen\n',
        '        fila(1, "Guadalajara")])\n    assert [op["valores"] for op in ops] == [{"work_location_id": MTY}]\n    assert "      1  la persona viene dos veces" in resumen\n\n\ndef test_el_correo_personal_de_otra_persona_no_se_escribe():\n    # Con el correo personal entra a la app (los de trabajo del personal de\n    # seguridad se van a suspender): no puede ser el de alguien mas.\n    ops, resumen = hoja.calcular(OdooFalso(empleado(1), empleado(2)), [\n        fila(2, "Monterrey", private_email="AGENTE1@correo.lat")])\n    assert [op["valores"] for op in ops] == [{"work_location_id": MTY}]\n    assert "      1  correo repetido con otra persona" in resumen\n')

cambiar('bitacora',
        '  tiene al menos diez—, no se guarda ni borra el que había, el alta sigue\n  sin celular, y el informe y `sincronizar_personal.py` lo cuentan aparte.\n\n## 14. Lo que falta\n\n### Abierto\n',
        '  tiene al menos diez—, no se guarda ni borra el que había, el alta sigue\n  sin celular, y el informe y `sincronizar_personal.py` lo cuentan aparte.\n\n## 63. El personal de seguridad entra con su correo personal\n\nDecisión de Salvador, 23 de septiembre en la noche: «será mejor que\nsiempre tomes el correo personal como bueno. muy pronto suspenderé las\ncuentas de correo del personal de seguridad únicamente». Hasta entonces la\nlectura del personal (sección 51) tomaba el correo de trabajo y, si no\nhabía, el personal.\n\n- **El correo con el que entra a la app es siempre el personal.** Quien no\n  lo tiene en Odoo queda pendiente —«sin correo personal»— y no se da de\n  alta, aunque tenga el de trabajo.\n- **El de trabajo solo sirve para reconocer**, la primera vez, a quien ya\n  estaba capturado en Centauro con él. Desde esa lectura entra con el\n  personal, y su acceso cambia de correo con él.\n- **A quien ya está y le falta el personal no se le cierra el acceso**:\n  sigue entrando con el que tenía y queda pendiente hasta que RH se lo\n  ponga en Odoo.\n- La hoja para RH (`hoja_rh_odoo.py`) marca en amarillo el correo personal\n  que falta y lo pide en sus instrucciones, y el cargador\n  (`cargar_hoja_rh.py`) revisa las repeticiones contra el personal.\n\nEn Odoo, 16 del personal de seguridad tienen correo de trabajo y todos\ntienen el personal: esos 16 entrarán con el personal. Como la lectura del\npersonal todavía no se aplica en el servidor, nadie tiene que cambiar de\nacceso.\n\n## 14. Lo que falta\n\n### Abierto\n')


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

# -*- coding: utf-8 -*-
"""Los estatus que nadie escribia.

  1. `confirmada` real en la jornada: sube desde `planeada` cuando toda
     su gente confirmo (app, posicion, telefono o central). Solo hacia
     adelante, como `evaluar` con el servicio.
  2. `cotizado` reservado: la cotizacion vive en Odoo (Salvador, 21 sep).
  3. Etiquetas de la jornada en la consola (es/en/pt).
  4. El recorrido 360: la cadena exacta desde el alta, la cancelacion con
     dinero en la calle y la cadena del implantado.

Idempotente: lo que ya esta aplicado se salta. Todas las escrituras van
al final, despues de que todos los cambios se armaron en memoria.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    "programacion": B / "app/programacion.py",
    "trayecto": B / "app/trayecto.py",
    "rop": B / "app/routers/operacion.py",
    "implantado": B / "app/implantado.py",
    "models": B / "app/models.py",
    "util": B / "app/web/util.js",
    "idioma": B / "app/web/idioma.js",
    "odoo": RAIZ / "ODOO_LO_QUE_NECESITAMOS.md",
    "bitacora": RAIZ / "BITACORA.md",
    "prueba": B / "tests/test_recorrido_360_cuentas.py",
}

textos = {k: io.open(v, encoding="utf-8").read() for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    """Reemplaza `viejo` por `nuevo` exactamente una vez. Si `marca`
    (o `nuevo`) ya esta en el archivo, el cambio ya se aplico y se
    salta."""
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(viejo) == 1, f"{clave}: '{viejo[:60]}...' esta {t.count(viejo)} veces"
    textos[clave] = t.replace(viejo, nuevo)


# ------------------------------------------------ 1 · el helper
cambiar("programacion", '''
    return []


def estado(servicio: m.Servicio) -> dict:
''', '''
    return []


def confirmar_si_todos(jornada: m.Jornada) -> bool:
    """El dia pasa a *confirmada* cuando ya confirmo toda su gente.

    `confirmada` existia en el catalogo de la jornada y no lo escribia
    nadie: cada asignacion guardaba su `confirmado` y el dia se quedaba
    en `planeada` hasta que alguien llegaba al punto. La regla es la
    misma que la de `evaluar` con el servicio: sube cuando ya no falta
    nada, y no baja. Si despues entra un relevo sin confirmar, su renglon
    lo dice; el dia no regresa.

    Cuenta la gente viva del dia --la relevada ya no va--. Un dia sin
    nadie no se confirma solo. Y solo sube desde `planeada`: uno que el
    reloj ya puso proximo a iniciar va mas adelante, no atras.

    Lo llaman los cuatro lugares donde alguien confirma: la app, la
    posicion del "voy en camino", lo dicho por telefono y la central.
    """
    if jornada.estatus != m.EstatusJornada.PLANEADA:
        return False
    vivos = [a for a in jornada.personal if a.persona_id and not a.relevado_en]
    if not vivos or not all(a.confirmado for a in vivos):
        return False
    jornada.estatus = m.EstatusJornada.CONFIRMADA
    return True


def estado(servicio: m.Servicio) -> dict:
''')

# ------------------------------------------------ 1 · las cuatro puertas
cambiar("trayecto", '''from app import push
from app import reloj
''', '''from app import programacion
from app import push
from app import reloj
''')

cambiar("trayecto", '''    if asignacion and not asignacion.confirmado:
        asignacion.confirmado = True

    distancia = _distancia(jornada, lat, lon)
''', '''    if asignacion and not asignacion.confirmado:
        asignacion.confirmado = True
        programacion.confirmar_si_todos(jornada)

    distancia = _distancia(jornada, lat, lon)
''')

cambiar("trayecto", '''    if not asignacion.confirmado:
        asignacion.confirmado = True
    db.commit()
    return {"estado": via.estado,
            "vigilancia_vuelve_en": MINUTOS_DE_GRACIA_POR_TELEFONO}
''', '''    if not asignacion.confirmado:
        asignacion.confirmado = True
        programacion.confirmar_si_todos(jornada)
    db.commit()
    return {"estado": via.estado,
            "vigilancia_vuelve_en": MINUTOS_DE_GRACIA_POR_TELEFONO}
''')

cambiar("rop", '''    asignacion.confirmado_en = reloj.ahora_de_la_jornada(
        db, asignacion.jornada)
    db.commit()
    return {"resultado": "confirmado", "persona": asignacion.persona.nombre}
''', '''    asignacion.confirmado_en = reloj.ahora_de_la_jornada(
        db, asignacion.jornada)
    programacion.confirmar_si_todos(asignacion.jornada)
    db.commit()
    return {"resultado": "confirmado", "persona": asignacion.persona.nombre}
''')

cambiar("rop", '''    asignacion.nota_confirmacion = (datos.nota or "").strip() or None
''', '''    asignacion.nota_confirmacion = (datos.nota or "").strip() or None
    programacion.confirmar_si_todos(jornada)
''')

# ------------------------------------------------ 1 · el implantado rehace dias
cambiar("implantado", '''        if jornada.estatus != m.EstatusJornada.PLANEADA:
            continue
        # Un dia con cambio ya fue decidido a mano: no se pisa.
        if any(a.reemplaza_a_id for a in jornada.personal):
            continue

        for a in list(jornada.personal):
            db.delete(a)
        for a in list(jornada.vehiculos):
            db.delete(a)
        db.flush()
''', '''        # Un dia que su gente ya confirmo cuenta igual que uno planeado:
        # todavia no arranca y lo que se rehace es su plantilla. Vuelve a
        # planeada porque la gente que entra no ha confirmado nada.
        if jornada.estatus not in (m.EstatusJornada.PLANEADA,
                                   m.EstatusJornada.CONFIRMADA):
            continue
        # Un dia con cambio ya fue decidido a mano: no se pisa.
        if any(a.reemplaza_a_id for a in jornada.personal):
            continue

        for a in list(jornada.personal):
            db.delete(a)
        for a in list(jornada.vehiculos):
            db.delete(a)
        db.flush()
        jornada.estatus = m.EstatusJornada.PLANEADA
''')

# ------------------------------------------------ 2 · cotizado, reservado
cambiar("models", '''    SOLICITADO = "solicitado"
    COTIZADO = "cotizado"
    AUTORIZADO = "autorizado"
''', '''    SOLICITADO = "solicitado"
    # Reservado: hoy no lo escribe nadie. La cotizacion se hace y se
    # autoriza en Odoo (decision de Salvador, 21 sep), asi que el
    # servicio que llega de alla nace ya `autorizado`; el rato entre
    # "se cotizo" y "el cliente dijo que si" no pasa aqui. Se queda en
    # el catalogo para que un dato viejo no truene y por si algun dia
    # la cotizacion vuelve a vivir en Centauro.
    COTIZADO = "cotizado"
    AUTORIZADO = "autorizado"
''')

cambiar("odoo", '''**Qué pasa al recibirlo.** El servicio **nace en Centauro**, en borrador,
con su cliente, su ejecutivo y su línea base cargada. El consultor lo
abre y arma el equipo; nadie vuelve a capturar el encabezado ni el
precio.
''', '''**Qué pasa al recibirlo.** El servicio **nace en Centauro** ya
**autorizado**, con su cliente, su ejecutivo y su línea base cargada. El
consultor lo abre y arma el equipo; nadie vuelve a capturar el
encabezado ni el precio.

**El estatus `cotizado` no existe en Centauro.** Entre "se cotizó" y "el
cliente autorizó" todo pasa en Odoo, y aquí no hay nada que mostrar en
ese rato. El catálogo conserva el valor por si algún día la cotización
vuelve a vivir aquí, pero ningún proceso lo escribe.
''')

# ------------------------------------------------ 3 · etiquetas
cambiar("util", '''  cotizado: "est_cotizado",
  autorizado: "est_autorizado",
''', '''  // Reservado: la cotizacion vive en Odoo y el servicio llega ya
  // autorizado. Se traduce por si un dato viejo lo trae.
  cotizado: "est_cotizado",
  autorizado: "est_autorizado",
''')
cambiar("util", '''  devuelto: "est_devuelto",
};
''', '''  devuelto: "est_devuelto",
  // Los del dia. `arribado` y `en_curso` son los mismos de arriba.
  planeada: "est_planeada",
  confirmada: "est_confirmada",
  proxima_a_iniciar: "est_proxima_a_iniciar",
  terminada: "est_terminada",
  cancelada: "est_cancelada",
};
''')

cambiar("idioma", '''    est_devuelto: "Devuelto",
''', '''    est_devuelto: "Devuelto",
    est_planeada: "Planeada",
    est_confirmada: "Confirmada",
    est_proxima_a_iniciar: "Próxima a iniciar",
    est_terminada: "Terminada",
    est_cancelada: "Cancelada",
''')
cambiar("idioma", '''    est_devuelto: "Returned",
''', '''    est_devuelto: "Returned",
    est_planeada: "Planned",
    est_confirmada: "Confirmed",
    est_proxima_a_iniciar: "Starting soon",
    est_terminada: "Finished",
    est_cancelada: "Cancelled",
''')
cambiar("idioma", '''    est_devuelto: "Devolvido",
''', '''    est_devuelto: "Devolvido",
    est_planeada: "Planejada",
    est_confirmada: "Confirmada",
    est_proxima_a_iniciar: "Prestes a começar",
    est_terminada: "Terminada",
    est_cancelada: "Cancelada",
''')

# ------------------------------------------------ bitacora
cambiar("bitacora", '''
## 14. Lo que falta
''', '''
## 48. Los estatus que nadie escribía

Al revisar la cadena de estatus para la prueba 360 (21 sep) salieron
dos valores del catálogo que ningún proceso escribía.

- **`confirmada`, de la jornada.** Cada asignación guardaba su
  `confirmado`, pero el día se quedaba en `planeada` hasta que alguien
  llegaba al punto. Ahora sube a `confirmada` cuando **toda** su gente
  viva confirmó —desde la app, con una posición de "voy en camino", por
  teléfono con la central o registrada a mano—. Solo hacia adelante,
  como el servicio con `evaluar`: un relevo que entra sin confirmar se
  ve en su renglón, el día no regresa. Un día de implantado que se
  rehace por un cambio del acuerdo sí vuelve a `planeada`: la gente
  nueva no ha confirmado nada.

- **`cotizado`, del servicio.** Decisión de Salvador (21 sep): *«en
  teoría, Odoo nos dará la cotización confirmada; de ahí se levanta el
  servicio»*. El rato entre "se cotizó" y "el cliente autorizó" vive en
  Odoo, así que aquí el servicio nace ya `autorizado` y `cotizado` queda
  **reservado**: en el catálogo, para que un dato viejo no truene, pero
  sin nadie que lo escriba.

Y una regla que ya existía y ahora tiene prueba: **el implantado no
llega a café.** Cerrar un día, abrir el mes que sigue o cerrar el último
día del mes lo deja en curso; `terminado` es del eventual. El implantado
se apaga cancelándolo o cuando finanzas aprueba su cierre.

## 14. Lo que falta
''')

# ------------------------------------------------ 4 · la prueba 360
cambiar("prueba", '''    for j in jornadas:
        asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])
    assert _estatus_servicio(cliente, h, sid) == "asignado", \\
        "con gente y unidad en todos los días debía estar azul"
''', '''    for j in jornadas:
        asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])
    assert _estatus_servicio(cliente, h, sid) == "asignado", \\
        "con gente y unidad en todos los días debía estar azul"
    # Los días, en cambio, siguen planeados: asignar no confirma. Eso lo
    # hace la gente, desde la app o por teléfono con la central.
    with SessionLocal() as db:
        for j in jornadas:
            assert _estatus_jornada(db, j["id"]) == "planeada"
''')

cambiar("prueba", '''    assert cliente.post(f"/servicios/{sid}/confirmar-asignacion",
                        headers=h).status_code == 200
    assert _estatus_servicio(cliente, h, sid) == "asignado"
''', '''    assert cliente.post(f"/servicios/{sid}/confirmar-asignacion",
                        headers=h).status_code == 200
    assert _estatus_servicio(cliente, h, sid) == "asignado"

    # Juan confirma sus dos días desde la app. Como es el único del
    # equipo, cada día queda confirmado; el servicio no se mueve.
    for j in jornadas:
        r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                         headers=hj)
        assert r.status_code == 200, r.text
    with SessionLocal() as db:
        for j in jornadas:
            assert _estatus_jornada(db, j["id"]) == "confirmada", \\
                "confirmó toda la gente del día y el día sigue en planeada"
    assert _estatus_servicio(cliente, h, sid) == "asignado"
''')

cambiar("prueba", '''    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])

    # Juan confirma desde la app: el día pasa a confirmada, y de ahí lo
    # toma el reloj.
    hj = sesion("juan")
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=hj)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "confirmada"

    with SessionLocal() as db:
        # 1 · La víspera, a las cinco de la tarde de México, lo tiene en
        #     la lista: con teléfono lo avisa, sin teléfono lo cuenta.
        hoy_17 = datetime.combine(date.today(), datetime.min.time()).replace(
            hour=17, tzinfo=ZoneInfo("America/Mexico_City"))
        r = push.recordar_la_vispera(db, ahora=hoy_17)
        assert j["fecha"] in r["dias"], r
        assert (len(r["avisados"]) + r["sin_telefono"]) >= 1, \\
            "la víspera no consideró a quien trabaja mañana"

        # 2 · A dos horas del arranque, el reloj lo pone próximo a iniciar.
''', '''    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])

    with SessionLocal() as db:
        # 1 · La víspera, a las cinco de la tarde de México, lo tiene en
        #     la lista: con teléfono lo avisa, sin teléfono lo cuenta.
        hoy_17 = datetime.combine(date.today(), datetime.min.time()).replace(
            hour=17, tzinfo=ZoneInfo("America/Mexico_City"))
        r = push.recordar_la_vispera(db, ahora=hoy_17)
        assert j["fecha"] in r["dias"], r
        assert (len(r["avisados"]) + r["sin_telefono"]) >= 1, \\
            "la víspera no consideró a quien trabaja mañana"

    # Juan le hace caso a la víspera y confirma desde la app: el día pasa
    # a confirmada. Después de la víspera y no antes: el recordatorio es
    # solo para quien todavía no ha confirmado.
    hj = sesion("juan")
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=hj)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "confirmada"

    with SessionLocal() as db:
        # 2 · A dos horas del arranque, el reloj lo pone próximo a iniciar.
''')

cambiar("prueba", '''    hj = sesion("juan")
    marcar(cliente, hj, j["id"], "llegada_origen", inicio - timedelta(minutes=10))
''', '''    marcar(cliente, hj, j["id"], "llegada_origen", inicio - timedelta(minutes=10))
''', marca="el 21 de septiembre.\n    marcar(cliente, hj")

NUEVAS = '''

# ==================================================================
# La cadena, escalón por escalón, desde un alta incompleta
# ==================================================================

def test_la_cadena_de_estatus_desde_el_alta(cliente, sesion, datos):
    """El estatus exacto —del servicio y del día— en cada escalón.

    El recorrido de arriba nace con el punto puesto, así que el servicio
    aparece ya planeado. Aquí nace sin punto, para ver cada paso:

        borrador → autorizado → planeado → planeado (gente sin unidad)
        → asignado. Y el día: planeada → confirmada, solo cuando TODOS
        los del día confirmaron, por la app o por teléfono.
    """
    from app.db import SessionLocal

    h = sesion("consultor")
    hc = sesion("central")
    hj = sesion("juan")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]

    # Sin punto de inicio le falta lo mínimo para estar planeado.
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(320), datos["modalidades"]["full_day"]["id"],
                 hora="09:00:00")],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    sid = servicio["id"]
    j = servicio["equipos"][0]["jornadas"][0]
    assert _estatus_servicio(cliente, h, sid) == "borrador"

    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"])
    assert _estatus_servicio(cliente, h, sid) == "autorizado", \\
        "con la cotización autorizada y sin punto debía estar autorizado"

    # El punto de inicio completa lo mínimo: planeado.
    assert configurar_origen(cliente, h, j["id"]).status_code == 200
    assert _estatus_servicio(cliente, h, sid) == "planeado"

    asignar(cliente, h, j["id"], persona_id=juan)
    asignar(cliente, h, j["id"], persona_id=luis, rol="agente_seguridad")
    assert _estatus_servicio(cliente, h, sid) == "planeado", \\
        "gente sin unidad no es asignado"
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "planeada"

    asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])
    assert _estatus_servicio(cliente, h, sid) == "asignado"
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "planeada", \\
            "asignar no confirma: confirma la gente"

    # Juan confirma desde la app; Luis todavía no. Uno de dos no basta.
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=hj)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "planeada", \\
            "con uno de dos confirmados el día ya se puso en confirmada"

    # La central registra que Luis confirmó por teléfono: ya están todos.
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-a-mano",
                     json={"persona_id": luis, "nota": "confirmó por WhatsApp"},
                     headers=hc)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "confirmada"
    assert _estatus_servicio(cliente, h, sid) == "asignado", \\
        "confirmar el día no mueve el servicio: sigue asignado hasta que llega"


# ==================================================================
# Cancelar con dinero en la calle
# ==================================================================

def test_cancelar_con_dinero_en_la_calle(cliente, sesion, datos):
    """Se cancela un servicio armado, con un viático ya depositado y otro
    que no había salido de la caja.

    El servicio y su día quedan cancelados. El viático que no salió se
    cancela solo. El que ya salió NO se cierra por decreto: queda
    enlistado con el neto que tiene que regresar y solo se cierra cuando
    finanzas registra la devolución. Y cancelado no se cancela dos veces.
    """
    from app import models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    hf = sesion("finanzas")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]

    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(330), datos["modalidades"]["full_day"]["id"],
                 hora="06:00:00", km_estimados=120, **PUNTO)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    sid = servicio["id"]
    j = servicio["equipos"][0]["jornadas"][0]
    equipo_id = servicio["equipos"][0]["id"]
    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"])
    asignar(cliente, h, j["id"], persona_id=juan)
    asignar(cliente, h, j["id"], persona_id=luis, rol="agente_seguridad")
    asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])
    assert _estatus_servicio(cliente, h, sid) == "asignado"

    def viatico_de(persona_id):
        propuesta = cliente.get(
            f"/viaticos/calcular?jornada_id={j['id']}&persona_id={persona_id}",
            headers=h)
        assert propuesta.status_code == 200, propuesta.text
        v = cliente.post("/viaticos/asignar", headers=h, json={
            "jornada_id": j["id"], "persona_id": persona_id,
            "conceptos": [{"concepto": c["concepto"], "monto": str(c["monto"]),
                           "descripcion": c["descripcion"], "origen": c["origen"]}
                          for c in propuesta.json()["conceptos"]]})
        assert v.status_code in (200, 201), v.text
        return v.json()

    # El de Juan sale de la caja; el de Luis se queda asignado.
    de_juan = viatico_de(juan)
    de_luis = viatico_de(luis)
    cliente.post(f"/viaticos/{de_juan['id']}/solicitar-transferencia", headers=h)
    dep = depositar(cliente, hf, equipo_id, juan, referencia="SPEI-CANCELA")
    assert dep.status_code == 200, dep.text
    entregado = _d(de_juan["monto_total"])
    assert entregado > 0

    r = cliente.post(f"/servicios/{sid}/cancelar",
                     json={"motivo": "el cliente canceló el viaje"}, headers=h)
    assert r.status_code == 200, r.text
    r = r.json()
    assert r["estatus_anterior"] == "asignado"
    assert r["dias_cancelados"] == 1
    assert _estatus_servicio(cliente, h, sid) == "cancelado"
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "cancelada"
        assert (db.get(m.AsignacionViatico, de_luis["id"]).estatus
                == m.EstatusViatico.CANCELADO), \\
            "el viático que no salió de la caja no se canceló"
        salio = db.get(m.AsignacionViatico, de_juan["id"])
        assert salio.estatus not in (m.EstatusViatico.CANCELADO,
                                     m.EstatusViatico.CERRADO), \\
            "el dinero que ya salió se dio por cerrado sin que volviera"

    # Lo que hay que devolver es exactamente lo entregado, y de quién.
    assert len(r["viaticos_por_devolver"]) == 1, r["viaticos_por_devolver"]
    pendiente = r["viaticos_por_devolver"][0]
    assert _d(pendiente["monto"]) == entregado, pendiente
    assert _d(pendiente["entregado"]) == entregado
    assert _d(pendiente["ya_comprobado"]) == CERO

    # Finanzas registra que volvió, y solo entonces se cierra en ceros.
    dev = devolver(cliente, hf, de_juan["id"], entregado,
                   referencia="SPEI-DEV-CANCELA")
    assert dev.status_code in (200, 201), dev.text
    cerrado = cliente.post(f"/viaticos/{de_juan['id']}/cerrar", headers=h)
    assert cerrado.status_code == 200, cerrado.text
    assert cerrado.json()["resultado"] == "cerrado", cerrado.json()
    with SessionLocal() as db:
        v = db.get(m.AsignacionViatico, de_juan["id"])
        assert _d(v.monto_devuelto) == entregado
        assert _d(v.monto_total) == _d(v.monto_comprobado) + _d(v.monto_devuelto)

    otra = cliente.post(f"/servicios/{sid}/cancelar",
                        json={"motivo": "otra vez"}, headers=h)
    assert otra.status_code == 409, otra.text


# ==================================================================
# La cadena del implantado
# ==================================================================

def test_la_cadena_del_implantado(cliente, sesion, datos):
    """El implantado no termina: se opera mes con mes hasta que alguien
    lo cancela o finanzas aprueba su cierre. Su cadena es otra:

        solicitado (alta) → planeado (el mes abierto, con su gente)
        → asignado (hoja liberada) → arribado → en curso (el primer día)
        → sigue en curso al cerrar un día, al abrir el mes que sigue y
        al cerrar el último día del mes. Café es del eventual.

    Los días llevan su ciclo: planeada → confirmada (todos los del día)
    → arribado → en curso → terminada. Y los días terminados entran a
    la nómina sin esperar ningún cierre.
    """
    from app.db import SessionLocal

    h = sesion("consultor")
    hc = sesion("central")
    hj = sesion("juan")
    hf = sesion("finanzas")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    unidad = datos["suburban"]["id"]
    mx = datos["mx"]["id"]
    hoy = date.today()

    # ------------------------------------ 1 · el alta, en sus dos mitades
    alta = cliente.post("/implantados/servicio", json={
        "cliente_id": datos["cliente_id"], "pais_id": mx,
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "acuerdo": {"zona_operacion": "Valle de Mexico", **PUNTO},
    }, headers=h)
    assert alta.status_code == 201, alta.text
    sid = alta.json()["servicio_id"]
    assert alta.json()["estatus"] == "solicitado"
    assert _estatus_servicio(cliente, h, sid) == "solicitado"

    mes = cliente.post(f"/implantados/{sid}/mes", json={
        "fecha_inicio": str(hoy.replace(day=1)), "dias_servicio": "lunes_viernes",
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "hora_presentacion": "08:00:00",
        "personal": [{"persona_id": juan,
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": unidad},
                     {"persona_id": luis,
                      "rol_id": datos["perfiles"]["agente_seguridad"]["id"],
                      "vehiculo_id": None}],
        "unidades": [unidad],
        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000",
    }, headers=h)
    assert mes.status_code == 201, mes.text
    assert _estatus_servicio(cliente, h, sid) == "planeado", \\
        "abrió el mes con su gente y el servicio no se puso planeado"

    panel = cliente.get(f"/implantados/{sid}/mes/{hoy.year}/{hoy.month}",
                        headers=h).json()
    habiles = [d for d in panel["dias"] if not d["fin_de_semana"]]
    assert habiles
    assert all(d["estatus"] == "planeada" for d in habiles), \\
        [(d["fecha"], d["estatus"]) for d in habiles]
    assert all(len(d["personal"]) == 2 for d in habiles)
    primero, ultimo = habiles[0], habiles[-1]

    # ------------------------------------- 2 · confirmar: uno no basta
    r = cliente.post(f"/operacion/jornadas/{primero['jornada_id']}/confirmar-recurso",
                     headers=hj)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, primero["jornada_id"]) == "planeada"
    r = cliente.post(f"/operacion/jornadas/{primero['jornada_id']}/confirmar-a-mano",
                     json={"persona_id": luis, "nota": "por teléfono"}, headers=hc)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, primero["jornada_id"]) == "confirmada"
    assert _estatus_servicio(cliente, h, sid) == "planeado"

    # ------------------------------------------ 3 · la hoja liberada
    r = cliente.post(f"/task-sheets/implantado/{sid}/liberar", headers=h)
    assert r.status_code == 200, r.text
    assert _estatus_servicio(cliente, h, sid) == "asignado"

    def ventana(jornada_id):
        ficha = cliente.get(f"/servicios/{sid}", headers=h).json()
        j = next(x for x in ficha["equipos"][0]["jornadas"] if x["id"] == jornada_id)
        return (datetime.fromisoformat(j["inicio_programado"]),
                datetime.fromisoformat(j["fin_programado"]))

    # ------------------------------- 4 · el primer día, marca a marca
    inicio, fin = ventana(primero["jornada_id"])
    r = marcar(cliente, hj, primero["jornada_id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code in (200, 201), r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, primero["jornada_id"]) == "arribado"
    assert _estatus_servicio(cliente, h, sid) == "arribado"

    r = marcar(cliente, hj, primero["jornada_id"], "contacto_ejecutivo", inicio)
    assert r.status_code in (200, 201), r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, primero["jornada_id"]) == "en_curso"
    assert _estatus_servicio(cliente, h, sid) == "en_curso"

    r = marcar_fin(cliente, hj, primero["jornada_id"], fin)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, primero["jornada_id"]) == "terminada"
    assert _estatus_servicio(cliente, h, sid) == "en_curso", \\
        "cerró un día y el implantado se apagó"

    # ---------------------------- 5 · el mes que sigue no mueve nada
    r = cliente.post(f"/implantados/{sid}/mes-siguiente", headers=h)
    assert r.status_code == 200, r.text
    assert _estatus_servicio(cliente, h, sid) == "en_curso", \\
        "abrir el mes que sigue movió el estatus del servicio"
    anio2, mes2 = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
    panel2 = cliente.get(f"/implantados/{sid}/mes/{anio2}/{mes2}", headers=h).json()
    habiles2 = [d for d in panel2["dias"] if not d["fin_de_semana"]]
    assert habiles2
    assert all(d["estatus"] == "planeada" and len(d["personal"]) == 2
               for d in habiles2), [(d["fecha"], d["estatus"]) for d in habiles2]

    # ------------------- 6 · el último día del mes tampoco es café
    inicio, fin = ventana(ultimo["jornada_id"])
    marcar(cliente, hj, ultimo["jornada_id"], "llegada_origen",
           inicio - timedelta(minutes=10))
    marcar(cliente, hj, ultimo["jornada_id"], "contacto_ejecutivo", inicio)
    r = marcar_fin(cliente, hj, ultimo["jornada_id"], fin)
    assert r.status_code == 200, r.text
    assert _estatus_servicio(cliente, h, sid) == "en_curso", \\
        "cerró el último día del mes y el implantado se puso en café: eso es del eventual"

    # ------------ 7 · los días cerrados entran a la nómina sin cierre
    corte = cliente.post("/nomina/calcular", headers=hf, json={
        "pais_id": mx,
        "fecha_corte": (hoy + timedelta(days=14)).isoformat()})
    assert corte.status_code == 200, corte.text
    detalle = cliente.get(f"/nomina/{corte.json()['nomina_id']}", headers=hf).json()
    renglon = next((r for r in detalle["renglones"] if r["persona_id"] == juan), None)
    assert renglon, "Juan trabajó dos días de implantado y no entró al corte"
    with SessionLocal() as db:
        for d in (primero, ultimo):
            concepto = next((c for c in renglon["conceptos"]
                             if c.get("jornada_id") == d["jornada_id"]), None)
            assert concepto, f"el día {d['fecha']} del implantado no entró al corte"
            assert _d(concepto["monto"]) == \\
                _comision_esperada(db, mx, d["jornada_id"], juan), concepto
'''

if "def test_la_cadena_del_implantado" in textos["prueba"]:
    saltados.append("prueba: las tres pruebas nuevas ya estaban")
else:
    textos["prueba"] = textos["prueba"].rstrip("\n") + "\n" + NUEVAS

# ------------------------------------------------ escrituras, todas al final
for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(textos[clave])
        print("escrito ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for s in saltados:
    print("saltado:", s)

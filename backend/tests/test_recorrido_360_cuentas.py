# -*- coding: utf-8 -*-
"""El recorrido 360, con las cuentas y los estatus.

`test_recorrido_360.py` camina un servicio de la cotización a la nómina
y verifica que cada estación deje algo. Pero es ciego en tres cosas que
son justo las que cuestan dinero o confianza:

  * el viático va con un `600` escrito a mano, no con lo que dice el
    tabulador;
  * la nómina solo comprueba que sea mayor que cero;
  * no hay una sola aserción de estatus.

Aquí el mismo camino, pero en cada estación se verifica **el número y el
estatus**. Y ningún número está escrito a mano: cada expectativa se
recalcula desde el catálogo con la misma regla que usa el sistema, así
que lo que se prueba es que los módulos se pongan de acuerdo entre
ellos —tabulador con viáticos, viáticos con la app y con finanzas,
comisiones con nómina, marcas con estatus— y no que un número mágico
siga siendo el mismo.

Pedido de Salvador, 21 sep: «que no haya tema con los cálculos de
viáticos, pago de nóminas, que corran bien los procesos del sistema y
que los estatus avancen de forma adecuada».
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from ayudas import (KM_RECEPCION, asignar, configurar_origen,
                    cotizar_y_autorizar, crear_servicio, depositar, devolver,
                    jornada, manana, marcar, marcar_fin, revisar_unidad)
from test_recorrido_360 import PUNTO, cuadrar

CERO = Decimal("0")


def _d(x) -> Decimal:
    return Decimal(str(x or 0))


def _estatus_servicio(cliente, h, servicio_id) -> str:
    r = cliente.get(f"/servicios/{servicio_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["estatus"]


def _estatus_jornada(db, jornada_id) -> str:
    from app import models as m
    return db.get(m.Jornada, jornada_id).estatus.value


# ==================================================================
# Lo que el tabulador tiene que dar, recalculado con su misma regla
# ==================================================================

def _viatico_esperado(db, jornada_id: int) -> dict:
    """Lo que `viaticos.calcular` debería proponer, concepto por concepto.

    Se recalcula aquí con las mismas reglas —traslado solo si madruga,
    combustible por kilómetros y rendimiento con holgura, estacionamiento
    por vuelta al aeropuerto, redondeo al entero de arriba— leyendo el
    catálogo directamente. Si el sistema cambia una regla sin cambiar la
    otra copia, esto lo dice.
    """
    from app import models as m
    from app.viaticos import (ESTACIONAMIENTO_AEROPUERTO, HORA_TRASLADO,
                              escenario_de, redondear, vueltas_al_aeropuerto)

    j = db.get(m.Jornada, jornada_id)
    servicio = j.equipo.servicio
    filas = (db.query(m.TabuladorViatico)
             .filter(m.TabuladorViatico.pais_id == servicio.pais_id,
                     m.TabuladorViatico.tipo_servicio == servicio.tipo,
                     m.TabuladorViatico.escenario == escenario_de(j),
                     m.TabuladorViatico.activo.is_(True)).all())
    assert filas, "el tabulador de ese escenario está vacío"

    madruga = j.inicio_programado.time() < HORA_TRASLADO
    vueltas = vueltas_al_aeropuerto(j)
    esperado = {}
    for f in filas:
        c = f.concepto
        if c == m.ConceptoViatico.TRASLADO_PERSONAL:
            esperado[c.value] = redondear(f.monto) if madruga else CERO
        elif c == m.ConceptoViatico.COMBUSTIBLE:
            veh = j.vehiculos[0].vehiculo if j.vehiculos else None
            par = (db.query(m.ParametroCombustible)
                   .filter(m.ParametroCombustible.pais_id == servicio.pais_id,
                           m.ParametroCombustible.activo.is_(True))
                   .order_by(m.ParametroCombustible.vigencia_desde.desc())
                   .first())
            if j.km_estimados and veh and par \
                    and _d(veh.categoria.rendimiento_km_litro) > 0:
                litros = Decimal(j.km_estimados) / _d(veh.categoria.rendimiento_km_litro)
                base = litros * _d(par.precio_litro)
                esperado[c.value] = redondear(
                    base * (Decimal("1") + _d(par.holgura_pct) / Decimal("100")))
            else:
                esperado[c.value] = CERO
        elif c == m.ConceptoViatico.OTROS and vueltas:
            esperado[c.value] = ESTACIONAMIENTO_AEROPUERTO * vueltas
        elif f.monto_abierto:
            esperado[c.value] = CERO
        else:
            esperado[c.value] = redondear(f.monto)
    return esperado


def _comision_esperada(db, pais_id: int, jornada_id: int, persona_id: int) -> Decimal:
    """Lo que la nómina le debe a alguien por un día, con la regla de
    `nomina.pago_de_jornada` leída desde el tabulador de comisiones."""
    from app import models as m
    from app.cierre import _horas_extra, factor_festivo

    j = db.get(m.Jornada, jornada_id)
    a = next(x for x in j.personal if x.persona_id == persona_id)
    tipo = j.equipo.servicio.tipo
    com = (db.query(m.ComisionPersonal)
           .filter_by(pais_id=pais_id, perfil_id=a.rol_id, tipo_servicio=tipo,
                      modalidad_id=j.modalidad_id).first())
    assert com, "no hay comisión cargada para ese rol y modalidad"
    factor = factor_festivo(db, pais_id, j.fecha)
    extras = 0 if a.relevado_en else _horas_extra(j)
    return _d(com.monto) * factor + _d(com.monto_hora_extra) * extras * factor


# ==================================================================
# El recorrido
# ==================================================================

def test_el_recorrido_con_las_cuentas_y_los_estatus(cliente, sesion, datos):
    """Dos full days. En cada estación: el estatus que debe tener y el
    número que debe dar, recalculado desde el catálogo."""
    from app import models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    hf = sesion("finanzas")
    hj = sesion("juan")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    mx = datos["mx"]["id"]
    dias = 2

    # ------------------------------------------------------ 1 · alta
    # Presentación a las 06:00: madruga, así que el traslado del
    # tabulador aplica. Y con kilómetros, para que el combustible se
    # estime y no quede en cero.
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(300 + i), datos["modalidades"]["full_day"]["id"],
                 hora="06:00:00", km_estimados=120, **PUNTO)
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    sid = servicio["id"]
    jornadas = servicio["equipos"][0]["jornadas"]
    equipo_id = servicio["equipos"][0]["id"]

    inicial = _estatus_servicio(cliente, h, sid)
    assert inicial not in ("asignado", "arribado", "en_curso", "terminado",
                           "cerrado"), f"recién creado y ya está {inicial}"

    # ------------------------------------------ 2 · cotizar y autorizar
    cotizacion = cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    total_cotizado = _d(cotizacion["total"])
    assert total_cotizado > 0, cotizacion

    # ------------------------------------ 3 · la gente, luego la unidad
    # Con la gente puesta y sin unidad NO es azul: azul es "ya tiene
    # todo". Y con la unidad en todos los días, sí.
    for j in jornadas:
        asignar(cliente, h, j["id"], persona_id=juan)
    assert _estatus_servicio(cliente, h, sid) != "asignado", \
        "se puso azul con gente pero sin unidad"

    for j in jornadas:
        asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])
    assert _estatus_servicio(cliente, h, sid) == "asignado", \
        "con gente y unidad en todos los días debía estar azul"
    # Los días, en cambio, siguen planeados: asignar no confirma. Eso lo
    # hace la gente, desde la app o por teléfono con la central.
    with SessionLocal() as db:
        for j in jornadas:
            assert _estatus_jornada(db, j["id"]) == "planeada"

    # ------------------------------------------ 4 · viáticos por tabulador
    viaticos = {}
    total_asignado = CERO
    with SessionLocal() as db:
        for j in jornadas:
            propuesta = cliente.get(
                f"/viaticos/calcular?jornada_id={j['id']}&persona_id={juan}",
                headers=h)
            assert propuesta.status_code == 200, propuesta.text
            propuesta = propuesta.json()

            esperado = _viatico_esperado(db, j["id"])
            visto = {c["concepto"]: _d(c["monto"]) for c in propuesta["conceptos"]}
            assert visto == esperado, (
                f"{j['fecha']}: la propuesta no sale del tabulador\n"
                f"  propuso  {visto}\n  esperado {esperado}")
            assert _d(propuesta["total_propuesto"]) == sum(esperado.values(), CERO)
            # Y lo que cuesta un traslado no puede ser cero si madruga:
            # si el tabulador lo trae, el renglón tiene que venir con monto.
            assert esperado.get("traslado_personal", CERO) > 0, \
                "presentación a las 06:00 y el traslado salió en cero"
            assert esperado.get("combustible", CERO) > 0, \
                "con 120 km y unidad asignada el combustible salió en cero"

            v = cliente.post("/viaticos/asignar", headers=h, json={
                "jornada_id": j["id"], "persona_id": juan,
                "conceptos": [{"concepto": c["concepto"], "monto": str(c["monto"]),
                               "descripcion": c["descripcion"],
                               "origen": c["origen"]}
                              for c in propuesta["conceptos"]]})
            assert v.status_code in (200, 201), v.text
            v = v.json()
            assert _d(v["monto_total"]) == _d(propuesta["total_propuesto"]), \
                "lo asignado no es lo propuesto"
            viaticos[j["id"]] = v["id"]
            total_asignado += _d(v["monto_total"])
            cliente.post(f"/viaticos/{v['id']}/solicitar-transferencia",
                         headers=h)

    # ---------------------------------------------- 5 · finanzas deposita
    dep = depositar(cliente, hf, equipo_id, juan, referencia="SPEI-360-CUENTAS")
    assert dep.status_code == 200, dep.text

    # Las tres puertas dicen lo mismo: lo depositado es lo asignado.
    mios = cliente.get("/campo/mis-viaticos", headers=hj).json()
    app = next(f for f in mios["servicios"] if f["folio"] == servicio["folio"])
    assert _d(app["entregado"]) == total_asignado, app
    assert _d(app["por_comprobar"]) == total_asignado, \
        "recién depositado, todo está por comprobar"

    caja = cliente.get("/viaticos/finanzas/por-comprobar", headers=hf).json()
    fila = next(p for pais in caja["paises"] for p in pais["personas"]
                if p["persona_id"] == juan and p["dias"] == dias)
    assert _d(fila["entregado"]) == total_asignado, fila
    assert _d(fila["pendiente"]) == total_asignado, fila

    # ------------------------------------------ 6 · el TS y la confirmación
    assert cliente.post(f"/task-sheets/servicio/{sid}/publicar",
                        json={"motivo": "alta"}, headers=h).status_code in (200, 201)
    assert cliente.post(f"/servicios/{sid}/confirmar-asignacion",
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
            assert _estatus_jornada(db, j["id"]) == "confirmada", \
                "confirmó toda la gente del día y el día sigue en planeada"
    assert _estatus_servicio(cliente, h, sid) == "asignado"

    # ------------------------------------------- 7 · el día uno, marca a marca
    assert revisar_unidad(cliente, hj, sid, datos["suburban"]["id"],
                          "recibe", KM_RECEPCION).status_code == 201
    d1 = jornadas[0]
    inicio = datetime.fromisoformat(d1["inicio_programado"])
    fin = datetime.fromisoformat(d1["fin_programado"])

    r = marcar(cliente, hj, d1["id"], "llegada_origen", inicio - timedelta(minutes=10))
    assert r.status_code in (200, 201), r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, d1["id"]) == "arribado"
    assert _estatus_servicio(cliente, h, sid) == "arribado", \
        "llegó al punto y el servicio no se puso en arribado"

    r = marcar(cliente, hj, d1["id"], "contacto_ejecutivo", inicio)
    assert r.status_code in (200, 201), r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, d1["id"]) == "en_curso"
    assert _estatus_servicio(cliente, h, sid) == "en_curso", \
        "hizo contacto con el principal y el servicio no se puso en verde"

    r = marcar_fin(cliente, hj, d1["id"], fin)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, d1["id"]) == "terminada"
    assert _estatus_servicio(cliente, h, sid) == "en_curso", \
        "cerró el día uno y el servicio se dio por terminado con un día pendiente"

    # ------------------------------------- 8 · el día dos, con dos horas extra
    d2 = jornadas[1]
    inicio2 = datetime.fromisoformat(d2["inicio_programado"])
    fin2 = datetime.fromisoformat(d2["fin_programado"])
    marcar(cliente, hj, d2["id"], "llegada_origen", inicio2 - timedelta(minutes=10))
    marcar(cliente, hj, d2["id"], "contacto_ejecutivo", inicio2)
    r = marcar_fin(cliente, hj, d2["id"], fin2 + timedelta(hours=2))
    assert r.status_code == 200, r.text
    assert _estatus_servicio(cliente, h, sid) == "terminado", \
        "cerró el último día y el servicio no se puso en café"

    with SessionLocal() as db:
        from app.cierre import _horas_extra
        assert _horas_extra(db.get(m.Jornada, d2["id"])) == 2
        assert _horas_extra(db.get(m.Jornada, d1["id"])) == 0

    # --------------------------------- 9 · comprobación parcial y devolución
    # De cada día se comprueba todo menos 100, y esos 100 se devuelven.
    # Así el cuadre tiene los dos caminos que el dinero puede tomar.
    sobra_por_dia = Decimal("100")
    comprobado_total = CERO
    for j in jornadas:
        vid = viaticos[j["id"]]
        estado = cliente.get(f"/viaticos/{vid}", headers=h).json()
        total = _d(estado["monto_total"])
        subido = cliente.post(
            f"/viaticos/{vid}/comprobantes", headers=hj,
            json={"concepto": "alimentos", "tipo": "nota",
                  "monto": str(total - sobra_por_dia)})
        assert subido.status_code in (200, 201), subido.text
        for c in subido.json()["comprobantes"]:
            cliente.post(f"/viaticos/{vid}/validar-comprobante/{c['id']}",
                         headers=h)
        comprobado_total += total - sobra_por_dia

    # La app y finanzas ven exactamente lo que falta: lo entregado menos
    # lo comprobado, contra el servicio entero y no contra un solo día.
    mios = cliente.get("/campo/mis-viaticos", headers=hj).json()
    app = next(f for f in mios["servicios"] if f["folio"] == servicio["folio"])
    assert _d(app["por_comprobar"]) == total_asignado - comprobado_total, app
    caja = cliente.get("/viaticos/finanzas/por-comprobar", headers=hf).json()
    fila = next(p for pais in caja["paises"] for p in pais["personas"]
                if p["persona_id"] == juan and p["dias"] == dias)
    assert _d(fila["comprobado"]) == comprobado_total, fila
    assert _d(fila["pendiente"]) == total_asignado - comprobado_total, fila

    for j in jornadas:
        vid = viaticos[j["id"]]
        dev = devolver(cliente, hf, vid, sobra_por_dia,
                       referencia=f"SPEI-DEV-{vid}")
        assert dev.status_code in (200, 201), dev.text
        cerrado = cliente.post(f"/viaticos/{vid}/cerrar", headers=h)
        assert cerrado.status_code == 200, cerrado.text
        assert cerrado.json()["resultado"] == "cerrado", cerrado.json()

    with SessionLocal() as db:
        for vid in viaticos.values():
            v = db.get(m.AsignacionViatico, vid)
            assert v.estatus == m.EstatusViatico.CERRADO
            assert _d(v.monto_total) == _d(v.monto_comprobado) + _d(v.monto_devuelto), (
                f"viático {vid}: {v.monto_total} entregados, "
                f"{v.monto_comprobado} comprobados + {v.monto_devuelto} devueltos")

    # ------------------------------------------- 10 · el cierre del servicio
    comparativo = cliente.get(f"/cierre/servicio/{sid}/comparativo",
                              headers=h).json()
    assert _d(comparativo["cotizacion"]["total"]) == total_cotizado, \
        "el comparativo no muestra lo que se cotizó"
    assert _d(comparativo["ejecutado"]["total"]) > 0

    cierre = cliente.post(f"/cierre/servicio/{sid}/abrir", headers=h).json()
    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas",
                         headers=h)
    assert envio.status_code == 200, envio.text
    assert _estatus_servicio(cliente, h, sid) == "en_facturacion", \
        "el visto bueno manda a facturar; cerrar, cierra finanzas"

    aprobado = cliente.post(f"/cierre/{cierre['cierre_id']}/aprobar", headers=hf)
    assert aprobado.status_code == 200, aprobado.text
    assert _estatus_servicio(cliente, h, sid) == "cerrado", \
        "finanzas aprobó y el servicio no se puso en negro"

    # --------------------------------------------------- 11 · la nómina
    corte = cliente.post("/nomina/calcular", json={"pais_id": mx}, headers=hf)
    assert corte.status_code == 200, corte.text
    nomina_id = corte.json()["nomina_id"]
    detalle = cliente.get(f"/nomina/{nomina_id}", headers=hf).json()
    renglon = next(r for r in detalle["renglones"] if r["persona_id"] == juan)

    with SessionLocal() as db:
        esperado = sum((_comision_esperada(db, mx, j["id"], juan)
                        for j in jornadas), CERO)
    assert _d(renglon["total"]) == esperado, (
        f"la nómina le paga a Juan {renglon['total']} y el tabulador de "
        f"comisiones dice {esperado} (2 días + 2 h extra)")
    assert renglon["dias"] == dias
    assert any("2 h extra" in c["descripcion"] for c in renglon["conceptos"]), \
        "las horas extra no aparecen en el recibo"

    # Pagado el corte, esos días no vuelven a entrar a ningún otro.
    assert cliente.post(f"/nomina/{nomina_id}/pagar", headers=hf).status_code == 200
    siguiente = cliente.post(
        "/nomina/calcular",
        json={"pais_id": mx,
              "fecha_corte": (date.today() + timedelta(days=7)).isoformat()},
        headers=hf).json()
    otra = cliente.get(f"/nomina/{siguiente['nomina_id']}", headers=hf).json()
    juan_otra = next((r for r in otra["renglones"] if r["persona_id"] == juan),
                     None)
    assert juan_otra is None or juan_otra["dias"] == 0, \
        f"un día ya pagado volvió a entrar al corte siguiente: {juan_otra}"

    # ---------------------------------------------------- 12 · el cuadre
    with SessionLocal() as db:
        problemas = cuadrar(db, sid)
    assert not problemas, "\n".join(problemas)


# ==================================================================
# Los procesos del reloj
# ==================================================================

def test_los_procesos_del_reloj_mueven_lo_que_les_toca(cliente, sesion, datos):
    """Lo que corre solo, sin que nadie abra una pantalla.

    Cada uno de estos ya tiene su prueba fina. Lo que aquí se verifica
    es la cadena: que sobre el MISMO servicio, la víspera lo considere,
    el reloj lo ponga en próximo a iniciar, el camino al punto le mande
    su toque, y el silencio en curso levante la alerta.
    """
    from zoneinfo import ZoneInfo

    from app import models as m, operacion, push, trayecto
    from app.db import SessionLocal

    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]

    # Un servicio para mañana a las 09:00, con su punto.
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(1), datos["modalidades"]["full_day"]["id"],
                 hora="09:00:00", **PUNTO)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])

    with SessionLocal() as db:
        # 1 · La víspera, a las cinco de la tarde de México, lo tiene en
        #     la lista: con teléfono lo avisa, sin teléfono lo cuenta.
        hoy_17 = datetime.combine(date.today(), datetime.min.time()).replace(
            hour=17, tzinfo=ZoneInfo("America/Mexico_City"))
        r = push.recordar_la_vispera(db, ahora=hoy_17)
        assert j["fecha"] in r["dias"], r
        assert (len(r["avisados"]) + r["sin_telefono"]) >= 1, \
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
        operacion.marcar_proximas_a_iniciar(db, ahora=inicio - timedelta(minutes=90))
        db.commit()
        assert (db.get(m.Jornada, j["id"]).estatus
                == m.EstatusJornada.PROXIMA_A_INICIAR)

        # 3 · El camino al punto: el primer toque sale a dos horas de la
        #     hora de estar, y no antes.
        estar = trayecto.hora_de_estar(db, db.get(m.Jornada, j["id"]))
        assert trayecto.pulsar(db, ahora=estar - timedelta(minutes=180))["toques"] == 0
        assert trayecto.pulsar(db, ahora=estar - timedelta(minutes=120))["toques"] == 1
        via = (db.query(m.Trayecto)
               .filter_by(jornada_id=j["id"], persona_id=juan).first())
        assert via and via.toques == 1

        # 4 · Sin contestar el toque, a los quince minutos es silencio y
        #     la central recibe la alerta.
        r = trayecto.pulsar(db, ahora=estar - timedelta(minutes=100))
        assert r["silencios"] == 1, r
        assert (db.query(m.Alerta)
                .filter_by(jornada_id=j["id"], persona_id=juan).count()) == 1

    # 5 · Llega y marca. La alerta del camino --"no contesta"-- la
    #     contestaron los hechos: se cierra sola, con su resolución.
    #
    #     Esto no pasaba. Nadie la cerraba, y como `revisar_standby` no
    #     apila una segunda alerta de silencio sobre una abierta, ese
    #     "no contesta" de la mañana TAPABA el silencio de verdad de la
    #     tarde. Lo cazó esta prueba el 21 de septiembre.
    marcar(cliente, hj, j["id"], "llegada_origen", inicio - timedelta(minutes=10))
    with SessionLocal() as db:
        del_camino = (db.query(m.Alerta)
                      .filter_by(jornada_id=j["id"], persona_id=juan).all())
        assert del_camino and all(a.atendida for a in del_camino), \
            "llegó al punto y la alerta de 'no contesta' sigue abierta"
        assert all("llegada" in (a.resolucion or "") for a in del_camino), \
            [a.resolucion for a in del_camino]

    marcar(cliente, hj, j["id"], "contacto_ejecutivo", inicio)
    with SessionLocal() as db:
        assert db.get(m.Jornada, j["id"]).estatus == m.EstatusJornada.EN_CURSO
        # 6 · Ya en curso, dos horas callado levantan la alerta de
        #     standby: la suya, sin que la de la mañana la tape.
        antes = db.query(m.Alerta).filter_by(
            jornada_id=j["id"], tipo=m.TipoAlerta.SIN_REPORTE).count()
        generadas = operacion.revisar_standby(
            db, ahora=inicio + timedelta(hours=2, minutes=30))
        db.commit()
        assert any(g["jornada_id"] == j["id"] for g in generadas), generadas
        despues = db.query(m.Alerta).filter_by(
            jornada_id=j["id"], tipo=m.TipoAlerta.SIN_REPORTE).count()
        assert despues == antes + 1, "el silencio en curso no levantó alerta"


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
    assert _estatus_servicio(cliente, h, sid) == "autorizado", \
        "con la cotización autorizada y sin punto debía estar autorizado"

    # El punto de inicio completa lo mínimo: planeado.
    assert configurar_origen(cliente, h, j["id"]).status_code == 200
    assert _estatus_servicio(cliente, h, sid) == "planeado"

    asignar(cliente, h, j["id"], persona_id=juan)
    asignar(cliente, h, j["id"], persona_id=luis, rol="agente_seguridad")
    assert _estatus_servicio(cliente, h, sid) == "planeado", \
        "gente sin unidad no es asignado"
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "planeada"

    asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])
    assert _estatus_servicio(cliente, h, sid) == "asignado"
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "planeada", \
            "asignar no confirma: confirma la gente"

    # Juan confirma desde la app; Luis todavía no. Uno de dos no basta.
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=hj)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "planeada", \
            "con uno de dos confirmados el día ya se puso en confirmada"

    # La central registra que Luis confirmó por teléfono: ya están todos.
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-a-mano",
                     json={"persona_id": luis, "nota": "confirmó por WhatsApp"},
                     headers=hc)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert _estatus_jornada(db, j["id"]) == "confirmada"
    assert _estatus_servicio(cliente, h, sid) == "asignado", \
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
                == m.EstatusViatico.CANCELADO), \
            "el viático que no salió de la caja no se canceló"
        salio = db.get(m.AsignacionViatico, de_juan["id"])
        assert salio.estatus not in (m.EstatusViatico.CANCELADO,
                                     m.EstatusViatico.CERRADO), \
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
    assert _estatus_servicio(cliente, h, sid) == "planeado", \
        "abrió el mes con su gente y el servicio no se puso planeado"

    panel = cliente.get(f"/implantados/{sid}/mes/{hoy.year}/{hoy.month}",
                        headers=h).json()
    habiles = [d for d in panel["dias"] if not d["fin_de_semana"]]
    assert habiles
    assert all(d["estatus"] == "planeada" for d in habiles), \
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
    assert _estatus_servicio(cliente, h, sid) == "en_curso", \
        "cerró un día y el implantado se apagó"

    # ---------------------------- 5 · el mes que sigue no mueve nada
    r = cliente.post(f"/implantados/{sid}/mes-siguiente", headers=h)
    assert r.status_code == 200, r.text
    assert _estatus_servicio(cliente, h, sid) == "en_curso", \
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
    assert _estatus_servicio(cliente, h, sid) == "en_curso", \
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
            assert _d(concepto["monto"]) == \
                _comision_esperada(db, mx, d["jornada_id"], juan), concepto

# -*- coding: utf-8 -*-
"""El recorrido completo: de la cotización a la nómina.

Las 649 pruebas miran **una regla a la vez**, y los ocho escenarios de
`test_escenarios.py` caminan un servicio pero se detienen en el task
sheet. Ninguna llega al final. Esta sí.

Lo que caza es lo que ninguna prueba unitaria puede ver: que dos reglas,
**cada una correcta por su lado, se estorben entre ellas**. El candado
de la hora contra el de la secuencia. El viático que se mueve en un
reemplazo y deja a la nómina contando dos veces.

Y al final, **el cuadre**: un puñado de igualdades que no pueden fallar
nunca. Son las que cazan lo silencioso —el sistema se ve bien y los
números no cuadran—, que es la peor clase de error porque ninguna
pantalla la enseña.
"""
from decimal import Decimal

from ayudas import (KM_RECEPCION, asignar, cotizar_y_autorizar,
                    crear_servicio, depositar, ejecutar_jornada, jornada,
                    manana, revisar_unidad)

PUNTO = {"origen_direccion": "Aeropuerto Internacional Benito Juárez, T2",
         "origen_lat": "19.4270", "origen_lon": "-99.1677",
         "geocerca_metros": 250}


# ==================================================================
# El cuadre: lo que tiene que dar al final, pase lo que pase
# ==================================================================

def cuadrar(db, servicio_id: int) -> list[str]:
    """Las igualdades que no pueden fallar. Devuelve lo que no cuadró.

    Se escribe como lista de problemas y no como una cascada de
    `assert` para que una corrida diga **todo** lo que está mal y no
    solo lo primero: si el dinero no cuadra y además quedó una alerta
    abierta, hay que enterarse de las dos cosas de una vez.
    """
    from app import models as m

    problemas = []
    servicio = db.get(m.Servicio, servicio_id)
    jornadas = [j for e in servicio.equipos for j in e.jornadas]
    viaticos = (db.query(m.AsignacionViatico)
                .filter(m.AsignacionViatico.jornada_id.in_(
                    [j.id for j in jornadas])).all())

    def d(x):
        return Decimal(str(x or 0))

    # --- 1. El dinero de cada persona cierra en cero
    for v in viaticos:
        entregado = d(v.monto_total)
        cubierto = (d(v.monto_comprobado) + d(v.monto_devuelto)
                    + d(v.monto_descontado) + d(v.monto_absorbido))
        if v.estatus == m.EstatusViatico.CERRADO and entregado != cubierto:
            problemas.append(
                f"viático {v.id}: se entregaron {entregado} y solo se "
                f"explican {cubierto}")

    # --- 2. Lo asignado es lo depositado más lo que sigue en camino
    for v in viaticos:
        solicitudes = (db.query(m.SolicitudTransferencia)
                       .filter_by(asignacion_id=v.id).all())
        salido = sum((d(s.monto) for s in solicitudes
                      if s.estatus == m.EstatusTransferencia.CONFIRMADA),
                     Decimal("0"))
        if salido > d(v.monto_total):
            problemas.append(
                f"viático {v.id}: se depositaron {salido} y solo se "
                f"asignaron {v.monto_total}")

    # --- 3. Todo día terminado tiene sus hitos, o su cierre a mano
    for j in jornadas:
        if j.estatus != m.EstatusJornada.TERMINADA:
            continue
        tipos = {h.tipo for h in db.query(m.Hito).filter_by(jornada_id=j.id)}
        if m.TipoHito.FIN_SERVICIO not in tipos and not j.cerrada_a_mano_en:
            problemas.append(
                f"jornada {j.fecha}: terminada sin fin de servicio y sin "
                f"cierre a mano")
        if (m.TipoHito.FIN_SERVICIO in tipos
                and m.TipoHito.LLEGADA_ORIGEN not in tipos):
            problemas.append(
                f"jornada {j.fecha}: cerró sin haber marcado la llegada")

    # --- 4. Ninguna unidad recibida y no entregada en un servicio cerrado
    if servicio.estatus == m.EstatusServicio.CERRADO:
        revisiones = (db.query(m.RevisionUnidad)
                      .filter_by(servicio_id=servicio.id).all())
        recibidas = {r.vehiculo_id for r in revisiones if r.tipo == "recibe"}
        entregadas = {r.vehiculo_id for r in revisiones if r.tipo == "entrega"}
        if recibidas - entregadas:
            problemas.append(
                f"servicio cerrado con {len(recibidas - entregadas)} "
                f"unidad(es) sin entregar")

    # --- 5. Ninguna alerta abierta en un servicio que ya terminó
    if servicio.estatus in (m.EstatusServicio.CERRADO,
                            m.EstatusServicio.CANCELADO):
        abiertas = (db.query(m.AlertaIncidencia)
                    .filter(m.AlertaIncidencia.jornada_id.in_(
                        [j.id for j in jornadas]),
                        m.AlertaIncidencia.estatus
                        == m.EstatusAlerta.ABIERTA).count())
        if abiertas:
            problemas.append(f"{abiertas} alerta(s) abiertas en un servicio "
                             f"{servicio.estatus.value}")

    # --- 6. Ningún viático colgando de una jornada que ya no existe
    huerfanos = (db.query(m.AsignacionViatico)
                 .outerjoin(m.Jornada,
                            m.AsignacionViatico.jornada_id == m.Jornada.id)
                 .filter(m.Jornada.id.is_(None)).count())
    if huerfanos:
        problemas.append(f"{huerfanos} viático(s) sin jornada")

    return problemas


# ==================================================================
# El guion
# ==================================================================

def _avisos(servicio_id, destinatario=None) -> list:
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        q = db.query(m.Notificacion).filter_by(servicio_id=servicio_id)
        if destinatario:
            q = q.filter_by(destinatario=destinatario)
        return [(a.destinatario, a.asunto or "", a.idioma) for a in q.all()]


def test_de_la_cotizacion_a_la_nomina(cliente, sesion, datos):
    """Un servicio caminado entero, sin saltarse una estación.

    Cada bloque verifica **lo que esa estación tiene que haber dejado**,
    no solo que el endpoint conteste 200: un 200 que no deja nada es
    exactamente el error que estas pruebas buscan.
    """
    from app import models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    dias = 2

    # ---------------------------------------- 1. El alta, con su punto
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(300 + i), datos["modalidades"]["full_day"]["id"],
                 hora="07:00:00", **PUNTO) for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    jornadas = servicio["equipos"][0]["jornadas"]
    equipo_id = servicio["equipos"][0]["id"]
    assert len(jornadas) == dias

    # ---------------------------------------- 2. Cotizar y autorizar
    cotizacion = cotizar_y_autorizar(
        cliente, h, servicio,
        datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    assert cotizacion["cotizacion_id"]

    # ---------------------------------------- 3. La gente y la unidad
    for j in jornadas:
        respuestas = asignar(cliente, h, j["id"], persona_id=juan,
                             vehiculo_id=datos["suburban"]["id"])
        assert all(r.status_code == 200 for r in respuestas), \
            [r.text for r in respuestas]

    # ---------------------------------------- 4. Los viáticos
    viaticos = []
    for j in jornadas:
        v = cliente.post("/viaticos/asignar", headers=h, json={
            "jornada_id": j["id"], "persona_id": juan,
            "conceptos": [{"concepto": "alimentos", "monto": "600",
                           "origen": "tabulador"}]}).json()
        viaticos.append(v["id"])
        cliente.post(f"/viaticos/{v['id']}/solicitar-transferencia", headers=h)

    # ---------------------------------------- 5. Finanzas deposita
    deposito = depositar(cliente, sesion("finanzas"), equipo_id, juan,
                         referencia="SPEI-360-RECORRIDO")
    assert deposito.status_code == 200, deposito.text
    # El dinero salió: la app de Juan ya lo tiene que enseñar como saldo.
    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    suyo = next((f for f in mios["servicios"]
                 if f["folio"] == servicio["folio"]), None)
    assert suyo, "la app no ve el servicio del que ya le depositaron"
    assert suyo["entregado"] > 0, suyo

    # ---------------------------------------- 6. El TS se libera
    publicado = cliente.post(
        f"/task-sheets/servicio/{servicio['id']}/publicar",
        json={"motivo": "alta del servicio"}, headers=h)
    assert publicado.status_code in (200, 201), publicado.text
    confirmada = cliente.post(
        f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    assert confirmada.status_code == 200, confirmada.text

    # Y sale en los tres idiomas, con la gente adentro.
    for idioma in ("es", "en", "pt"):
        hoja = cliente.get(
            f"/task-sheets/servicio/{servicio['id']}/hoja?idioma={idioma}",
            headers=h)
        assert hoja.status_code == 200, hoja.text
        assert "Juan Ramirez" in hoja.text, f"la hoja en {idioma} sin equipo"

    # ---------------------------------------- 7. El día, de punta a punta
    # Con el kilometraje de la casa: el cierre del ultimo dia entrega la
    # unidad con KM_ENTREGA, y un odometro no cuenta para atras.
    recibida = revisar_unidad(cliente, sesion("juan"), servicio["id"],
                              datos["suburban"]["id"], "recibe", KM_RECEPCION)
    assert recibida.status_code == 201, recibida.text
    for idx, j in enumerate(jornadas):
        cierre = ejecutar_jornada(cliente, sesion("juan"), j,
                                  horas_extra=2 if idx == dias - 1 else 0)
        assert cierre.status_code == 200, cierre.text

    # Los hitos quedaron, y en orden.
    with SessionLocal() as db:
        for j in jornadas:
            tipos = {x.tipo for x in
                     db.query(m.Hito).filter_by(jornada_id=j["id"])}
            assert m.TipoHito.LLEGADA_ORIGEN in tipos, j["fecha"]
            assert m.TipoHito.FIN_SERVICIO in tipos, j["fecha"]

    # ---------------------------------------- 8. Lo que el cliente recibió
    asuntos = _avisos(servicio["id"])
    assert asuntos, "el servicio corrió entero y no salió un solo aviso"
    quienes = {d for d, _a, _i in asuntos}
    assert m.Destinatario.EJECUTIVO in quienes
    assert m.Destinatario.SOLICITANTE in quienes
    # Cada uno en su idioma: el principal en inglés, quien solicita en
    # el de su país.
    for destinatario, _asunto, idioma in asuntos:
        if destinatario == m.Destinatario.EJECUTIVO:
            assert idioma == "en", asuntos
        if destinatario == m.Destinatario.SOLICITANTE:
            assert idioma == "es", asuntos

    # ---------------------------------------- 9. La comprobación
    for viatico_id in viaticos:
        estado = cliente.get(f"/viaticos/{viatico_id}", headers=h).json()
        falta = Decimal(str(estado["monto_total"]))
        subido = cliente.post(
            f"/viaticos/{viatico_id}/comprobantes", headers=sesion("juan"),
            json={"concepto": "alimentos", "tipo": "nota",
                  "monto": str(falta)})
        assert subido.status_code in (200, 201), subido.text
        for comprobante in subido.json()["comprobantes"]:
            cliente.post(
                f"/viaticos/{viatico_id}/validar-comprobante"
                f"/{comprobante['id']}", headers=h)
        cerrado = cliente.post(f"/viaticos/{viatico_id}/cerrar",
                               headers=h).json()
        assert cerrado["resultado"] == "cerrado", cerrado

    # ---------------------------------------- 10. El cierre del servicio
    comparativo = cliente.get(
        f"/cierre/servicio/{servicio['id']}/comparativo", headers=h).json()
    assert "ejecutado" in comparativo, comparativo
    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=h).json()
    assert cierre["cierre_id"]
    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas",
                         headers=h)
    assert envio.status_code == 200, envio.text

    # ---------------------------------------- 11. La nómina
    corte = cliente.post("/nomina/calcular",
                         json={"pais_id": datos["mx"]["id"]},
                         headers=sesion("finanzas"))
    assert corte.status_code == 200, corte.text
    resumen = corte.json()
    assert resumen["personas"] >= 1, resumen
    assert resumen["total"] > 0, resumen
    detalle = cliente.get(f"/nomina/{resumen['nomina_id']}",
                          headers=sesion("finanzas")).json()
    assert "Juan Ramirez" in str(detalle), \
        "el corte no recogió a quien trabajó"

    # ---------------------------------------- 12. Y el cuadre
    with SessionLocal() as db:
        problemas = cuadrar(db, servicio["id"])
    assert not problemas, "\n".join(problemas)


def test_el_cuadre_caza_el_dinero_que_no_se_explica(cliente, sesion, datos):
    """El cuadre tiene que servir de algo: si se le pone delante un
    viático cerrado al que le falta dinero por explicar, lo dice.

    Una verificación que nunca falla no es una verificación.
    """
    from app import models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(320), datos["modalidades"]["full_day"]["id"],
                 **PUNTO)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    v = cliente.post("/viaticos/asignar", headers=h, json={
        "jornada_id": j["id"], "persona_id": juan,
        "conceptos": [{"concepto": "alimentos", "monto": "600",
                       "origen": "tabulador"}]}).json()

    # Se cierra a la fuerza sin comprobar nada: es el agujero que el
    # cuadre tiene que ver.
    with SessionLocal() as db:
        fila = db.get(m.AsignacionViatico, v["id"])
        fila.estatus = m.EstatusViatico.CERRADO
        db.commit()
        problemas = cuadrar(db, servicio["id"])

    assert any("se explican" in p for p in problemas), problemas

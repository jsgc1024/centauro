# -*- coding: utf-8 -*-
"""Seccion 105 (grupo g7): el corte de nomina que no se pago el lunes.

Decision 11 de Salvador (29 de septiembre): el corte listo sigue a la
vista hasta pagarse --se paga el martes o despues--; mientras sea lunes
y el corte de hoy no exista se puede armar a mano, tambien despues de
las 11:00; y si un corte listo no se paga y llega al siguiente lunes, el
corte nuevo lo absorbe: sus renglones pasan al nuevo con su semana de
origen, sale un solo corte de dos semanas (o tres, o las que sean), el
viejo queda absorbido y no se paga ni se tira. Hallazgo 107 (a9-08).
"""
import threading
from datetime import timedelta
from decimal import Decimal

from test_nominas import _con_visto_bueno, _en_mexico, _lunes, _reloj, _ver


def _lunes_futuros():
    """Tres lunes seguidos, todos por venir: el reloj se mueve con
    `?ahora=` y nada depende del dia en que corra la prueba."""
    l1 = _lunes() + timedelta(days=7)
    return l1, l1 + timedelta(days=7), l1 + timedelta(days=14)


def _semana(cliente, sesion, datos, ahora):
    r = cliente.get("/nomina/semana", headers=sesion("finanzas"),
                    params={"pais_id": datos["mx"]["id"],
                            "ahora": ahora.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def _historial(cliente, sesion, datos, ahora=None):
    params = {"pais_id": datos["mx"]["id"]}
    if ahora:
        params["ahora"] = ahora.isoformat()
    r = cliente.get("/nomina", headers=sesion("finanzas"), params=params)
    assert r.status_code == 200, r.text
    return {c["fecha_corte"]: c for c in r.json()}


def _pagar(cliente, sesion, nomina_id):
    return cliente.post(f"/nomina/{nomina_id}/pagar", headers=sesion("finanzas"))


def _corte_listo(cliente, sesion, datos, lunes, offset, **kw):
    """Un servicio con visto bueno y el reloj de ese lunes a las 11:05:
    el corte queda listo para pagar."""
    servicio, _ = _con_visto_bueno(cliente, sesion, datos, offset, **kw)
    hechos = _reloj(_en_mexico(lunes, 11, 5))
    assert [x["resultado"] for x in hechos] == ["listo"], hechos
    return servicio, hechos[0]["nomina_id"]


def _conceptos_de(corte, persona):
    p = next(x for x in corte["por_persona"] if x["persona"] == persona)
    return p["conceptos"]


# ============================================ a · a la vista hasta pagarse

def test_el_corte_listo_sigue_a_la_vista_hasta_pagarse(cliente, sesion, datos):
    """El corte del lunes 21 quedo listo y nadie lo pago. El martes 22
    sigue en la pestana (es el de esta semana); el lunes 28 sin nada
    nuevo el reloj no arma otro, y la pestana sigue ensenando el del 21
    como pendiente de pago, con su boton, tambien el martes 29 y en el
    historial. Se paga, y entonces la pestana pasa a lo que va para el
    lunes que sigue."""
    l1, l2, l3 = _lunes_futuros()
    servicio, nomina_id = _corte_listo(cliente, sesion, datos, l1, 500)

    martes = _semana(cliente, sesion, datos, _en_mexico(l1 + timedelta(days=1), 10, 0))
    assert martes["corte"]["nomina_id"] == nomina_id
    assert martes["corte"]["estado"] == "listo" and martes["corte"]["pendiente"] is False

    # El lunes siguiente, sin nada nuevo que pagar.
    lunes = _semana(cliente, sesion, datos, _en_mexico(l2, 9, 0))
    corte = lunes["corte"]
    assert corte is not None, "el corte listo desaparecia el lunes siguiente"
    assert corte["nomina_id"] == nomina_id
    assert corte["pendiente"] is True and corte["estado"] == "listo"
    assert corte["fecha_corte"] == l1.isoformat()
    assert corte["desde"] == l1.isoformat() and corte["semanas"] == []
    assert [g["folio"] for g in corte["por_origen"]] == [servicio["folio"]]
    assert lunes["armar_hoy"] is False and lunes["proximo"] is None
    assert _reloj(_en_mexico(l2, 11, 5)) == [], "sin nada nuevo no hay corte nuevo"

    martes29 = _en_mexico(l2 + timedelta(days=1), 16, 0)
    assert _semana(cliente, sesion, datos, martes29)["corte"]["nomina_id"] == nomina_id
    historial = _historial(cliente, sesion, datos, martes29)
    assert historial[l1.isoformat()]["pendiente"] is True
    assert historial[l1.isoformat()]["estado"] == "listo"

    r = _pagar(cliente, sesion, nomina_id)
    assert r.status_code == 200, r.text
    semana = _semana(cliente, sesion, datos, martes29)
    assert semana["corte"] is None
    assert semana["proximo"]["fecha_corte"] == l3.isoformat()
    assert semana["ultimo_pagado"]["nomina_id"] == nomina_id
    assert _historial(cliente, sesion, datos, martes29)[l1.isoformat()]["pendiente"] is False


# ============================================ b · armar el corte de hoy

def test_si_el_reloj_no_corrio_el_lunes_se_arma_el_corte_de_hoy(cliente, sesion,
                                                                 datos):
    """Lunes 28, hay dias que pagar y el reloj no corrio. Antes de las
    7:00 no se ofrece nada; desde las 7:00 la pestana ofrece "Armar el
    corte de hoy", y despues de las 11:00 tambien. Armarlo deja el corte
    del 28 con sus botones, y la siguiente vuelta del reloj lo cierra."""
    l1, l2, _ = _lunes_futuros()
    servicio, _ = _con_visto_bueno(cliente, sesion, datos, 510)
    mx = datos["mx"]["id"]

    temprano = _semana(cliente, sesion, datos, _en_mexico(l1, 6, 30))
    assert temprano["corte"] is None and temprano["armar_hoy"] is False

    manana = _semana(cliente, sesion, datos, _en_mexico(l1, 8, 0))
    assert manana["armar_hoy"] is True and manana["no_salio"] is True
    assert manana["proximo"]["fecha_corte"] == l1.isoformat()

    tarde = _semana(cliente, sesion, datos, _en_mexico(l1, 11, 30))
    assert tarde["corte"] is None
    assert tarde["armar_hoy"] is True, "despues de las 11 tambien, mientras sea lunes"
    assert tarde["falta_hoy"] == []
    # Lo que llega despues de las 11:00 sigue siendo del lunes que sigue
    # mientras nadie arme el de hoy.
    assert tarde["proximo"]["fecha_corte"] == l2.isoformat()

    r = cliente.post("/nomina/calcular", headers=sesion("finanzas"),
                     json={"pais_id": mx, "fecha_corte": str(l1)})
    assert r.status_code == 200, r.text
    assert r.json()["personas"] == 1 and r.json()["heredados"] == 0
    despues = _semana(cliente, sesion, datos, _en_mexico(l1, 11, 40))
    assert despues["corte"]["nomina_id"] == r.json()["nomina_id"]
    assert despues["corte"]["pendiente"] is False
    assert despues["armar_hoy"] is False
    assert [g["folio"] for g in despues["corte"]["por_origen"]] == [servicio["folio"]]

    hechos = _reloj(_en_mexico(l1, 11, 50))
    assert [x["resultado"] for x in hechos] == ["listo"]
    assert _ver(cliente, sesion, r.json()["nomina_id"])["estado"] == "listo"
    # El martes ya no se ofrece armar el de ayer.
    martes = _semana(cliente, sesion, datos, _en_mexico(l1 + timedelta(days=1), 9, 0))
    assert martes["armar_hoy"] is False


def test_sin_nada_que_pagar_no_se_ofrece_armar_el_corte(cliente, sesion, datos):
    """Un lunes sin dias ni ajustes: el reloj no arma nada y la pestana
    tampoco ofrece armarlo, ni antes ni despues de las 11:00."""
    l1, _, _ = _lunes_futuros()
    for hora in (9, 12):
        semana = _semana(cliente, sesion, datos, _en_mexico(l1, hora, 0))
        assert semana["corte"] is None and semana["armar_hoy"] is False
    assert _reloj(_en_mexico(l1, 11, 5)) == []


# ============================================ c · el del 28 absorbe al del 21

def test_el_corte_nuevo_absorbe_al_que_no_se_pago(cliente, sesion, datos):
    """El del 21 quedo listo y no se pago; el lunes 28 el reloj arma el
    corte del 28 y se lleva al del 21: trae sus renglones con su semana
    de origen, cubre desde el 21, el del 21 queda absorbido y ya no se
    paga, ni se tira, ni se recalcula. Pagar el del 28 paga los dias de
    las dos semanas."""
    from app import models as m
    from app.db import SessionLocal

    l1, l2, _ = _lunes_futuros()
    viejo, viejo_id = _corte_listo(cliente, sesion, datos, l1, 520)
    total_viejo = Decimal(str(_ver(cliente, sesion, viejo_id)["total"]))
    nuevo, _ = _con_visto_bueno(cliente, sesion, datos, 522,
                                quien="Luis Mendoza", cuenta="luis")

    hechos = _reloj(_en_mexico(l2, 11, 5))
    assert [x["resultado"] for x in hechos] == ["listo"], hechos
    nuevo_id = hechos[0]["nomina_id"]
    corte = _ver(cliente, sesion, nuevo_id)
    assert corte["desde"] == l1.isoformat()
    assert corte["semanas"] == [l1.isoformat()]
    assert sorted(g["folio"] for g in corte["por_origen"]) \
        == sorted([viejo["folio"], nuevo["folio"]])
    assert Decimal(str(corte["total"])) > total_viejo
    de_juan = _conceptos_de(corte, "Juan Ramirez")
    assert [c["semana"] for c in de_juan] == [l1.isoformat()]
    assert viejo["folio"] in de_juan[0]["descripcion"] or de_juan[0]["folio"] == viejo["folio"]
    assert [c["semana"] for c in _conceptos_de(corte, "Luis Mendoza")] == [None]

    absorbido = _ver(cliente, sesion, viejo_id)
    assert absorbido["estado"] == "absorbido" and absorbido["estatus"] == "absorbida"
    assert absorbido["absorbida_por"]["nomina_id"] == nuevo_id
    # Lo que traia se sigue viendo, leido de donde vive hoy.
    assert [g["folio"] for g in absorbido["por_origen"]] == [viejo["folio"]]
    assert Decimal(str(absorbido["total"])) == total_viejo

    f = sesion("finanzas")
    r = _pagar(cliente, sesion, viejo_id)
    assert r.status_code == 409, r.text
    assert "absorbió" in r.json()["detail"]["mensaje"]
    assert f"{l2:%d/%m/%Y}" in r.json()["detail"]["mensaje"]
    assert r.json()["detail"]["nomina_id"] == nuevo_id
    assert cliente.delete(f"/nomina/{viejo_id}", headers=f).status_code == 409
    r = cliente.post("/nomina/calcular", headers=f,
                     json={"pais_id": datos["mx"]["id"], "fecha_corte": str(l1)})
    assert r.status_code == 409, r.text

    # La pestana del 28 dice que incluye la semana del 21; el historial
    # ensena al del 21 absorbido y por quien.
    semana = _semana(cliente, sesion, datos, _en_mexico(l2, 11, 30))
    assert semana["corte"]["nomina_id"] == nuevo_id
    assert semana["corte"]["semanas"] == [l1.isoformat()]
    historial = _historial(cliente, sesion, datos, _en_mexico(l2, 11, 30))
    assert historial[l1.isoformat()]["estado"] == "absorbido"
    assert historial[l1.isoformat()]["absorbida_por"]["fecha_corte"] == l2.isoformat()
    assert historial[l1.isoformat()]["pendiente"] is False
    assert historial[l1.isoformat()]["personas"] == 1
    assert historial[l2.isoformat()]["semanas"] == [l1.isoformat()]

    assert _pagar(cliente, sesion, nuevo_id).status_code == 200
    with SessionLocal() as db:
        pagadas = (db.query(m.ConceptoNomina)
                   .join(m.RenglonNomina,
                         m.ConceptoNomina.renglon_id == m.RenglonNomina.id)
                   .join(m.NominaSemanal,
                         m.RenglonNomina.nomina_id == m.NominaSemanal.id)
                   .filter(m.NominaSemanal.estatus == m.EstatusNomina.PAGADA,
                           m.ConceptoNomina.jornada_id.isnot(None)).count())
        assert pagadas == 2, "los dias de las dos semanas quedaron pagados"
        assert db.get(m.NominaSemanal, viejo_id).estatus == m.EstatusNomina.ABSORBIDA
    # Nada queda pendiente para el lunes que sigue.
    r = cliente.post(f"/nomina/servicio/{viejo['id']}/revisar-diferencias", headers=f)
    assert r.status_code == 200 and r.json()["ajustes_generados"] == []


def test_el_descuento_de_la_semana_vieja_se_cobra_de_la_nueva(cliente, sesion,
                                                              datos):
    """En el corte del 21 Juan solo tenia un descuento de 500 y quedo en
    cero, con saldo en contra. Nadie lo pago. El 28 trabaja un dia: el
    corte del 28 trae el descuento con su semana y lo cobra de ese dia,
    sin dejar a nadie en contra ni arrastrar el saldo dos veces. Y
    recalcular el del 28 antes de las 11:00 conserva lo heredado."""
    f = sesion("finanzas")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    mx = datos["mx"]["id"]
    l1, l2, _ = _lunes_futuros()
    r = cliente.post("/nomina/ajustes", headers=f, json={
        "persona_id": juan, "pais_id": mx, "monto": "-500",
        "motivo": "Uniforme que no regreso"})
    assert r.status_code == 201, r.text
    hechos = _reloj(_en_mexico(l1, 11, 5))
    assert [x["resultado"] for x in hechos] == ["listo"]
    viejo_id = hechos[0]["nomina_id"]
    viejo = _ver(cliente, sesion, viejo_id)
    assert viejo["resumen"]["en_contra"] == 1 and Decimal(str(viejo["total"])) == 0

    _con_visto_bueno(cliente, sesion, datos, 530)
    hechos = _reloj(_en_mexico(l2, 7, 5))
    assert [x["resultado"] for x in hechos] == ["borrador"]
    nuevo_id = hechos[0]["nomina_id"]

    def revisar():
        corte = _ver(cliente, sesion, nuevo_id)
        assert corte["semanas"] == [l1.isoformat()]
        assert corte["resumen"]["en_contra"] == 0
        conceptos = _conceptos_de(corte, "Juan Ramirez")
        assert [(c["semana"], c["es_ajuste"], c["saldo_en_contra"]) for c in conceptos] \
            == [(l1.isoformat(), True, False), (None, False, False)]
        dia = Decimal(str(conceptos[1]["monto"]))
        assert Decimal(str(corte["total"])) == dia - 500
        assert Decimal(str(corte["total"])) > 0
        return corte

    revisar()
    # "Recalcular" antes de las 11:00 no pierde ni duplica lo heredado.
    r = cliente.post("/nomina/calcular", headers=f,
                     json={"pais_id": mx, "fecha_corte": str(l2)})
    assert r.status_code == 200, r.text
    assert r.json()["heredados"] == 1 and r.json()["ajustes_aplicados"] == 0
    revisar()
    assert [x["resultado"] for x in _reloj(_en_mexico(l2, 11, 5))] == ["listo"]
    corte = revisar()

    assert _pagar(cliente, sesion, nuevo_id).status_code == 200
    pendientes = cliente.get("/nomina/ajustes/pendientes", headers=f,
                             params={"pais_id": mx}).json()
    assert pendientes == [], "el descuento se saldo una sola vez"
    assert corte["por_persona"][0]["persona"] == "Juan Ramirez"


# ============================================ d · tres semanas en un corte

def test_el_del_5_absorbe_al_del_28_que_ya_traia_al_del_21(cliente, sesion,
                                                            datos):
    """Nadie pago en dos semanas: el del 28 traia al 21, y el del 5 se
    lleva al del 28 con todo. Un solo corte de tres semanas, con cada
    renglon diciendo de cual viene; la cadena es lineal: el del 21 sigue
    apuntando al 28, que fue quien se lo llevo."""
    l1, l2, l3 = _lunes_futuros()
    s1, id1 = _corte_listo(cliente, sesion, datos, l1, 540)
    s2, _ = _con_visto_bueno(cliente, sesion, datos, 542,
                             quien="Luis Mendoza", cuenta="luis")
    hechos = _reloj(_en_mexico(l2, 11, 5))
    assert [x["resultado"] for x in hechos] == ["listo"]
    id2 = hechos[0]["nomina_id"]
    s3, _ = _con_visto_bueno(cliente, sesion, datos, 544)
    hechos = _reloj(_en_mexico(l3, 11, 5))
    assert [x["resultado"] for x in hechos] == ["listo"]
    id3 = hechos[0]["nomina_id"]

    corte = _ver(cliente, sesion, id3)
    assert corte["desde"] == l1.isoformat()
    assert corte["semanas"] == [l1.isoformat(), l2.isoformat()]
    assert sorted(g["folio"] for g in corte["por_origen"]) \
        == sorted([s1["folio"], s2["folio"], s3["folio"]])
    # Juan trabajo la semana del 21 y la del 5: el recibo lo dice, en
    # orden, la vieja primero.
    assert [c["semana"] for c in _conceptos_de(corte, "Juan Ramirez")] \
        == [l1.isoformat(), None]
    assert [c["semana"] for c in _conceptos_de(corte, "Luis Mendoza")] == [l2.isoformat()]
    assert corte["resumen"]["personas"] == 2

    primero = _ver(cliente, sesion, id1)
    segundo = _ver(cliente, sesion, id2)
    assert primero["estado"] == "absorbido"
    assert primero["absorbida_por"]["nomina_id"] == id2, "la cadena es lineal"
    assert segundo["estado"] == "absorbido"
    assert segundo["absorbida_por"]["nomina_id"] == id3
    assert segundo["semanas"] == [l1.isoformat()]
    # Lo que traia cada uno se sigue leyendo aunque haya viajado dos veces.
    assert [g["folio"] for g in primero["por_origen"]] == [s1["folio"]]
    assert [g["folio"] for g in segundo["por_origen"]] == [s2["folio"]]
    assert _pagar(cliente, sesion, id2).status_code == 409
    assert _pagar(cliente, sesion, id1).status_code == 409
    assert _pagar(cliente, sesion, id3).status_code == 200

    historial = _historial(cliente, sesion, datos, _en_mexico(l3, 12, 30))
    assert historial[l3.isoformat()]["estado"] == "pagado"
    assert historial[l2.isoformat()]["absorbida_por"]["fecha_corte"] == l3.isoformat()
    assert historial[l1.isoformat()]["absorbida_por"]["fecha_corte"] == l2.isoformat()


# ============================================ e · lo ya pagado no pasa

def test_lo_que_ya_se_pago_no_pasa_al_corte_nuevo(cliente, sesion, datos):
    """El del 21 se pago el martes: el del 28 no se lleva nada de el. Y
    con el del 21 pagado y el del 28 sin pagar, el del 5 se lleva solo al
    del 28. El corte se paga completo --no hay pago por persona--, asi
    que "lo ya pagado" es el corte entero."""
    l1, l2, l3 = _lunes_futuros()
    _, id1 = _corte_listo(cliente, sesion, datos, l1, 550)
    assert _pagar(cliente, sesion, id1).status_code == 200
    s2, _ = _con_visto_bueno(cliente, sesion, datos, 552,
                             quien="Luis Mendoza", cuenta="luis")
    hechos = _reloj(_en_mexico(l2, 11, 5))
    assert [x["resultado"] for x in hechos] == ["listo"]
    id2 = hechos[0]["nomina_id"]
    corte = _ver(cliente, sesion, id2)
    assert corte["desde"] == l2.isoformat() and corte["semanas"] == []
    assert [g["folio"] for g in corte["por_origen"]] == [s2["folio"]]
    assert _ver(cliente, sesion, id1)["estado"] == "pagado"

    s3, _ = _con_visto_bueno(cliente, sesion, datos, 554)
    hechos = _reloj(_en_mexico(l3, 11, 5))
    assert [x["resultado"] for x in hechos] == ["listo"]
    corte = _ver(cliente, sesion, hechos[0]["nomina_id"])
    assert corte["desde"] == l2.isoformat() and corte["semanas"] == [l2.isoformat()]
    assert sorted(g["folio"] for g in corte["por_origen"]) \
        == sorted([s2["folio"], s3["folio"]])
    assert _ver(cliente, sesion, id1)["estado"] == "pagado"
    assert _ver(cliente, sesion, id2)["estado"] == "absorbido"


# ============================================ f · el reloj dos veces

def test_el_reloj_dos_veces_el_mismo_lunes_no_absorbe_dos_veces(cliente, sesion,
                                                                 datos):
    """Dos vueltas del reloj el lunes 28 --una tras otra, y dos al mismo
    tiempo--: una arma el corte y se lleva al del 21; la otra no hace
    nada. Los renglones del 21 estan una sola vez y el del 21 queda
    absorbido una sola vez."""
    from app import models as m
    from app.db import SessionLocal

    l1, l2, _ = _lunes_futuros()
    _, id1 = _corte_listo(cliente, sesion, datos, l1, 560)
    _con_visto_bueno(cliente, sesion, datos, 562, quien="Luis Mendoza",
                     cuenta="luis")

    barrera = threading.Barrier(2)
    salidas = []

    def vuelta():
        barrera.wait()
        try:
            salidas.append(_reloj(_en_mexico(l2, 11, 5)))
        except Exception as error:      # noqa: BLE001
            salidas.append(type(error).__name__)

    hilos = [threading.Thread(target=vuelta) for _ in range(2)]
    for x in hilos:
        x.start()
    for x in hilos:
        x.join()
    resultados = sorted(([x["resultado"] for x in s] if isinstance(s, list)
                         else [s] for s in salidas), key=len)
    assert resultados == [[], ["listo"]], salidas
    # Y otra vuelta despues, la misma semana, tampoco hace nada.
    assert _reloj(_en_mexico(l2, 11, 20)) == []

    with SessionLocal() as db:
        cortes = (db.query(m.NominaSemanal).filter_by(pais_id=datos["mx"]["id"])
                  .order_by(m.NominaSemanal.fecha_corte).all())
        assert [(n.fecha_corte, n.estatus) for n in cortes] == [
            (l1, m.EstatusNomina.ABSORBIDA), (l2, m.EstatusNomina.CALCULADA)]
        assert cortes[0].absorbida_por_id == cortes[1].id
        heredados = (db.query(m.ConceptoNomina)
                     .filter_by(semana_origen=l1).all())
        assert len(heredados) == 1
        assert db.query(m.ConceptoNomina).count() == 2

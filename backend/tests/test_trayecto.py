# -*- coding: utf-8 -*-
"""El camino al meet and greet.

El conductor que se queda dormido no manda una señal equivocada: no
manda ninguna. El sistema vigilaba lo que pasa durante el servicio y
nada del silencio de antes.

Y reponer a alguien toma hasta hora y media (dato de Salvador, 20 sep),
así que el primer toque va a **dos horas** de la hora de estar en el
punto: con hora y media el reemplazo llegaría quince minutos tarde.

Lo único que se revisa es si se mueve hacia allá. La puntualidad es
responsabilidad del personal de seguridad, y si todo va bien no sale
ninguna noticia.
"""
from datetime import date, datetime, timedelta

from ayudas import asignar, configurar_origen, crear_servicio, jornada

# El origen de las pruebas, y cuánto vale un grado de longitud ahí: a
# esa latitud, un grado son unos 104.5 km. Con eso se arman puntos a la
# distancia que haga falta sin inventar coordenadas.
KM_POR_GRADO = 104.5
ORIGEN_LAT = 19.4270
ORIGEN_LON = -99.1677


def _a_kilometros(km: float) -> tuple:
    """Un punto a esa distancia del origen, al oriente."""
    return (ORIGEN_LAT, ORIGEN_LON + km / KM_POR_GRADO)


def _dia_de_hoy(cliente, sesion, datos, hora="18:00:00"):
    """Una jornada de hoy, con su punto y su gente."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(date.today(), datos["modalidades"]["full_day"]["id"],
                 hora=hora)])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def _cuando(j, minutos_antes):
    """El reloj, a tantos minutos de la hora de estar en el punto."""
    from app.db import SessionLocal
    from app import models as m, trayecto

    with SessionLocal() as db:
        estar = trayecto.hora_de_estar(db, db.get(m.Jornada, j["id"]))
    return estar - timedelta(minutes=minutos_antes)


def _via(j):
    from app.db import SessionLocal
    from app import models as m

    with SessionLocal() as db:
        return (db.query(m.Trayecto)
                .filter_by(jornada_id=j["id"]).first())


def _alertas(j):
    from app.db import SessionLocal
    from app import models as m

    with SessionLocal() as db:
        return db.query(m.Alerta).filter_by(jornada_id=j["id"]).all()


def test_el_primer_toque_sale_a_dos_horas_y_no_antes(cliente, sesion, datos):
    """La cuenta que manda: reponer toma hora y media, así que a hora y
    media el reemplazo ya llegaría tarde."""
    from app.db import SessionLocal
    from app import trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)

    with SessionLocal() as db:
        # Tres horas antes no le toca a nadie.
        r = trayecto.pulsar(db, ahora=_cuando(j, 180))
        assert r["toques"] == 0

        r = trayecto.pulsar(db, ahora=_cuando(j, 120))
        assert r["toques"] == 1, r

    assert _via(j).toques == 1


def test_si_se_acerca_no_pasa_nada(cliente, sesion, datos):
    """Regla de Salvador: si todo va bien, ninguna noticia."""
    from app.db import SessionLocal
    from app import models as m, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    with SessionLocal() as db:
        lat, lon = _a_kilometros(20)
        trayecto.registrar(db, j["id"], juan, lat, lon,
                           ahora=_cuando(j, 120))
        lat, lon = _a_kilometros(12)
        trayecto.registrar(db, j["id"], juan, lat, lon,
                           ahora=_cuando(j, 80))

    via = _via(j)
    assert via.estado == m.EstadoTrayecto.EN_CAMINO
    assert via.distancia_ultima_m < via.distancia_inicial_m
    assert _alertas(j) == []


def test_dos_lecturas_sin_moverse_levantan_la_alerta(cliente, sesion, datos):
    """Una es tráfico; dos seguidas ya no."""
    from app.db import SessionLocal
    from app import models as m, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    lat, lon = _a_kilometros(15)

    with SessionLocal() as db:
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 120))
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 100))
        # La primera sin avanzar todavía no dice nada.
        assert _via(j).estado == m.EstadoTrayecto.EN_CAMINO
        assert _alertas(j) == []

        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 80))

    assert _via(j).estado == m.EstadoTrayecto.NO_LLEGA
    alertas = _alertas(j)
    assert len(alertas) == 1
    assert "Juan" in alertas[0].mensaje


def test_se_mueve_pero_no_le_alcanza_el_tiempo(cliente, sesion, datos):
    """A media hora del punto y a cuarenta kilómetros: eso ya no es
    puntualidad, es que no va a estar ahí."""
    from app.db import SessionLocal
    from app import models as m, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    with SessionLocal() as db:
        lat, lon = _a_kilometros(45)
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 60))
        lat, lon = _a_kilometros(42)
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 40))

    via = _via(j)
    assert via.estado == m.EstadoTrayecto.NO_LLEGA
    assert len(_alertas(j)) == 1


def test_el_silencio_pesa_igual_que_no_ir(cliente, sesion, datos):
    """No contestar es exactamente lo mismo que no ir."""
    from app.db import SessionLocal
    from app import models as m, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)

    with SessionLocal() as db:
        trayecto.pulsar(db, ahora=_cuando(j, 120))
        # Quince minutos después sigue sin contestar.
        r = trayecto.pulsar(db, ahora=_cuando(j, 100))
        assert r["silencios"] == 1, r

    assert _via(j).estado == m.EstadoTrayecto.SIN_RESPUESTA
    assert len(_alertas(j)) == 1
    assert "no contesta" in _alertas(j)[0].mensaje


def test_cerca_del_punto_se_apaga(cliente, sesion, datos):
    """Ya llegó y está esperando: no se le vuelve a preguntar."""
    from app.db import SessionLocal
    from app import models as m, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    with SessionLocal() as db:
        lat, lon = _a_kilometros(0.3)
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 120))
        # Y el reloj ya no le manda nada.
        r = trayecto.pulsar(db, ahora=_cuando(j, 80))
        assert r["toques"] == 0

    assert _via(j).estado == m.EstadoTrayecto.CERCA
    assert _alertas(j) == []


def test_quien_ya_marco_su_llegada_no_recibe_toques(cliente, sesion, datos):
    """Llegar apaga el camino: ni toques ni nombre colgado en la banda.

    Marcar la llegada pone la jornada EN_CURSO y el reloj ya no la
    mira, asi que el apagado tiene que pasar en el hito. Si se dejara
    al pulso, el nombre se quedaria en la pantalla de la central toda
    la tarde con el equipo ya trabajando.
    """
    from app.db import SessionLocal
    from app import models as m, trayecto
    from ayudas import marcar

    servicio, j = _dia_de_hoy(cliente, sesion, datos, hora="23:30:00")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    inicio = datetime.fromisoformat(j["inicio_programado"])

    with SessionLocal() as db:
        lat, lon = _a_kilometros(15)
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 120))
    assert _via(j).estado == m.EstadoTrayecto.EN_CAMINO

    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))

    assert _via(j).estado == m.EstadoTrayecto.LLEGO
    banda = cliente.get("/central/camino", headers=sesion("central")).json()
    assert banda["cuantos"] == 0

    with SessionLocal() as db:
        assert trayecto.pulsar(db, ahora=_cuando(j, 120))["toques"] == 0


def test_la_central_ve_quien_viene_en_camino(cliente, sesion, datos):
    """La vista del rato en que todavía se puede hacer algo. Aparece sola
    cuando hay alguien en camino y desaparece cuando todos llegaron."""
    from app.db import SessionLocal
    from app import trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    h = sesion("central")

    # Sin nadie en camino, la caja no existe.
    vacia = cliente.get("/central/camino", headers=h).json()
    assert vacia["cuantos"] == 0

    with SessionLocal() as db:
        lat, lon = _a_kilometros(15)
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 120))
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 100))
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 80))

    r = cliente.get("/central/camino", headers=h).json()
    assert r["cuantos"] == 1
    assert r["en_riesgo"] == 1
    quien = r["gente"][0]
    assert quien["estado"] == "no_llega"
    # El teléfono a un clic: lo primero que hace quien lee esto es llamar.
    assert quien["telefono"]
    # Alrededor de 15: los kilometros por grado de la ayuda son una
    # aproximacion y la distancia real se calcula sobre la esfera. Lo
    # que se prueba es que la pantalla diga la distancia, no que dos
    # formulas distintas den el mismo decimal.
    assert 14.5 <= quien["distancia_km"] <= 15.5


def test_el_que_ya_llego_no_ocupa_la_pantalla(cliente, sesion, datos):
    from app.db import SessionLocal
    from app import trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    with SessionLocal() as db:
        lat, lon = _a_kilometros(0.2)
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 60))

    r = cliente.get("/central/camino", headers=sesion("central")).json()
    assert r["cuantos"] == 0


def test_el_servicio_con_alguien_en_camino_se_puede_borrar(cliente, sesion,
                                                           datos):
    """Borrar un servicio en el que alguien dijo "voy en camino".

    Las tablas del camino nacieron después que la limpieza del borrado
    y no se agregaron a ella: el servicio reventaba con una violación de
    llave foránea —un 500 en la cara del consultor, con el servicio a
    medio desarmar—. Lo encontró el zoológico de la prueba 360 al
    limpiarse a sí mismo.
    """
    from app.db import SessionLocal
    from app import models as m, trayecto

    h = sesion("consultor")
    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    with SessionLocal() as db:
        lat, lon = _a_kilometros(15)
        trayecto.registrar(db, j["id"], juan, lat, lon, ahora=_cuando(j, 120))
    assert _via(j) is not None

    r = cliente.request("DELETE", f"/servicios/{servicio['id']}",
                        json={"motivo": "Prueba del borrado"}, headers=h)
    assert r.status_code == 200, r.text

    # Y no quedó nada colgando del día que ya no existe.
    with SessionLocal() as db:
        assert db.query(m.Trayecto).filter_by(jornada_id=j["id"]).count() == 0
        assert db.query(m.LecturaTrayecto).count() == 0


def test_la_limpieza_cubre_todo_lo_que_cuelga_de_un_servicio(
        cliente, sesion, datos):
    """El candado contra el siguiente topo.

    Dos veces en una tarde apareció lo mismo: una tabla nueva que apunta
    al día y que nadie agregó a la limpieza del borrado. Se arregló la
    tabla, apareció otra.

    Esto no prueba un caso: recorre el modelo y exige que **toda** llave
    a `jornada`, `equipo` o `servicio` esté resuelta al desarmar —
    borrada, puesta en nulo, o con CASCADE en la base—. La siguiente
    tabla que nazca huérfana falla aquí, y no en la cara de un
    consultor con el servicio a medio desarmar.
    """
    import re
    from pathlib import Path

    import app

    raiz = Path(app.__file__).resolve().parent.parent
    modelo = (raiz / "app" / "models.py").read_text(encoding="utf-8")
    fuente = (raiz / "app" / "routers" / "servicios.py").read_text(
        encoding="utf-8")
    # Las dos funciones juntas: una suelta el día y la otra el servicio,
    # y entre las dos tienen que dejar la mesa limpia.
    desde = fuente.index("def _limpiar_jornadas")
    # Hasta donde termina `desarmar_servicio`: el primer decorador
    # después de ella. Buscar la ruta por su texto no sirve --hay varias
    # que empiezan igual-- y una rebanada al revés deja el trozo vacío,
    # que es como esta prueba pasaría sin mirar nada.
    hasta = fuente.index("@router.", fuente.index("def desarmar_servicio"))
    limpieza = fuente[desde:hasta]
    assert len(limpieza) > 2000, "la rebanada del código quedó mal"

    # Lo que sí se resuelve, pero no por su nombre de clase. Se listan
    # una por una y con su razón: una excepción sin motivo escrito es
    # una excepción que crece.
    APARTE = {
        ("Equipo", "servicio"): "se borra recorriendo servicio.equipos",
    }

    huerfanas = []
    for bloque in re.split(r"\nclass ", modelo):
        nombre = bloque.split("(")[0].strip()
        if "__tablename__" not in bloque:
            continue
        for destino in ("jornada", "equipo", "servicio"):
            patron = (r'mapped_column\(\s*ForeignKey\("' + destino
                      + r'\.id"([^)]*)\)')
            for llave in re.finditer(patron, bloque):
                if "CASCADE" in llave.group(1):
                    continue
                if (nombre, destino) in APARTE:
                    continue
                if f"m.{nombre}" not in limpieza:
                    huerfanas.append(f"{nombre} → {destino}")

    assert not huerfanas, (
        "apuntan a algo que el borrado suelta y nadie las limpia:\n  "
        + "\n  ".join(sorted(set(huerfanas))))


def test_decir_que_voy_en_camino_confirma_la_asignacion(cliente, sesion, datos):
    """Ir manejando hacia el punto dice más que confirmar.

    La central veía "le falta confirmar al equipo" mientras la persona
    estaba en la carretera: la confirmación sólo se apagaba con el botón
    de Confirmar, y quien ya iba en camino nunca volvía a tocarlo. Un
    renglón rojo que miente enseña a ignorar los renglones rojos.
    """
    from app.db import SessionLocal
    from app import models as m, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    def confirmado():
        with SessionLocal() as db:
            return (db.query(m.AsignacionPersonal)
                    .filter_by(jornada_id=j["id"], persona_id=juan)
                    .first().confirmado)

    assert confirmado() is False

    with SessionLocal() as db:
        lat, lon = _a_kilometros(20)
        trayecto.registrar(db, j["id"], juan, lat, lon,
                           ahora=_cuando(j, 120))

    assert confirmado() is True


def test_la_central_asienta_lo_que_le_contestaron_por_telefono(
        cliente, sesion, datos):
    """El caso de todos los días: el toque se le fue a un teléfono
    guardado en el bolsillo de alguien que va manejando, la banda lo
    pinta en rojo y la central marca su número.

    Lo que contesta no tenía dónde asentarse, así que el rojo se quedaba
    rojo con el hombre ya en Periférico. Un renglón rojo que miente es
    lo que enseña a ignorar los renglones rojos.
    """
    from app.db import SessionLocal
    from app import models as m, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    central = sesion("dirgeneral")

    # Se le toca y no contesta: queda en rojo.
    with SessionLocal() as db:
        trayecto.pulsar(db, ahora=_cuando(j, 120))
        trayecto.pulsar(db, ahora=_cuando(j, 100))
    assert _via(j).estado == m.EstadoTrayecto.SIN_RESPUESTA.value

    r = cliente.post(f"/central/camino/{j['id']}/por-telefono",
                     headers=central,
                     json={"persona_id": juan, "nota": "va en Periferico"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "por_telefono"

    via = _via(j)
    assert via.por_telefono_en is not None
    assert via.por_telefono_por_id, "no dice quién lo registró"
    assert via.por_telefono_nota == "va en Periferico"

    # Y la alerta de "no contesta" se cierra de verdad --la fila, no solo
    # la bandera-- con lo que contestó. Antes solo se bajaba la bandera y
    # la alerta seguía abierta en la central, tapando la siguiente.
    alertas = _alertas(j)
    assert alertas and all(a.atendida for a in alertas), \
        "habló con la central y la alerta sigue abierta"
    assert any("va en camino" in (a.resolucion or "") for a in alertas), \
        [a.resolucion for a in alertas]

    # Y la banda lo dice con nombre y hora: lo dicho por teléfono no se
    # puede confundir nunca con una posición del GPS.
    banda = cliente.get("/central/camino", headers=central).json()
    suyo = next(x for x in banda["gente"] if x["persona_id"] == juan)
    assert suyo["estado"] == "por_telefono"
    assert suyo["por_telefono_por"], "no sale quién lo registró"

    # Quien ya va manejando hacia el punto sabe que hoy trabaja.
    with SessionLocal() as db:
        asignacion = (db.query(m.AsignacionPersonal)
                      .filter_by(jornada_id=j["id"], persona_id=juan).first())
        assert asignacion.confirmado is True


def test_lo_dicho_por_telefono_no_apaga_la_vigilancia(cliente, sesion, datos):
    """Da un plazo, no una absolución. Decisión de Salvador, 21 sep.

    Quien dijo que iba y no llegó es exactamente el caso que esta
    pantalla existe para cazar: si la palabra de la central apagara el
    trayecto, ese sería el único que se escaparía.
    """
    from app.db import SessionLocal
    from app import models as m, trayecto

    servicio, j = _dia_de_hoy(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    with SessionLocal() as db:
        trayecto.pulsar(db, ahora=_cuando(j, 120))
        trayecto.dijo_que_va(db, j["id"], juan, juan, "voy saliendo",
                             ahora=_cuando(j, 115))

    # Dentro del plazo no se le vuelve a tocar: se acaba de hablar con
    # él, insistirle es ruido.
    with SessionLocal() as db:
        r = trayecto.pulsar(
            db, ahora=_cuando(j, 115 - trayecto.MINUTOS_DE_GRACIA_POR_TELEFONO
                              + 5))
        assert r["silencios"] == 0, r
    assert _via(j).estado == m.EstadoTrayecto.POR_TELEFONO.value

    # Pasado el plazo, si su teléfono sigue sin decir dónde está, el
    # silencio vuelve a pesar.
    with SessionLocal() as db:
        trayecto.pulsar(
            db, ahora=_cuando(j, 115 - trayecto.MINUTOS_DE_GRACIA_POR_TELEFONO
                              - 5))
    assert _via(j).estado == m.EstadoTrayecto.SIN_RESPUESTA.value
    assert _alertas(j), "nadie levantó la mano por el que dijo que iba"

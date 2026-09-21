"""Tablero de profesionalismo.

Lo que se verifica: que una dimension sin datos no cuente como cero, que
solo pesen las incidencias ya autorizadas, y que los pesos tengan que
sumar 100 para que la calificacion signifique lo mismo entre personas.
"""
from ayudas import (asignar, configurar_origen,
                    crear_servicio, ejecutar_jornada, jornada, manana)


def _ficha(cliente, sesion, persona_id):
    r = cliente.get(f"/profesionalismo/persona/{persona_id}",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def _dimension(ficha, nombre):
    return next(d for d in ficha["dimensiones"] if d["dimension"] == nombre)


def test_sin_datos_la_dimension_no_cuenta_como_cero(cliente, sesion, datos):
    """A quien nadie ha calificado no se le castiga por eso."""
    juan = datos["personal"]["Juan Ramirez"]["id"]
    ficha = _ficha(cliente, sesion, juan)

    satisfaccion = _dimension(ficha, "satisfaccion")
    assert satisfaccion["aplica"] is False
    assert satisfaccion["aporte"] == 0
    # Y su peso se reparte: las dimensiones que si aplican suman 100.
    aplicadas = sum(d["peso_aplicado"] for d in ficha["dimensiones"]
                    if d["aplica"])
    assert abs(aplicadas - 100) < 0.1


def test_la_confianza_avisa_cuando_falta_informacion(cliente, sesion, datos):
    juan = datos["personal"]["Juan Ramirez"]["id"]
    ficha = _ficha(cliente, sesion, juan)
    assert ficha["confianza"] in ("media", "baja")
    assert "satisfaccion" in ficha["sin_datos_para_medir"]


def test_sin_incidencias_la_dimension_vale_cien(cliente, sesion, datos):
    """No tener incidencias es informacion, no ausencia de informacion."""
    juan = datos["personal"]["Juan Ramirez"]["id"]
    incidencias = _dimension(_ficha(cliente, sesion, juan), "incidencias")
    assert incidencias["aplica"] is True
    assert incidencias["valor"] == 100


def test_una_incidencia_sin_visto_bueno_no_baja_la_calificacion(cliente, sesion,
                                                                datos):
    """Hasta que el director de operaciones la autoriza, no es un hecho."""
    juan = datos["personal"]["Juan Ramirez"]["id"]
    antes = _ficha(cliente, sesion, juan)["calificacion"]

    r = cliente.post("/incidencias",
                     json={"persona_id": juan, "gravedad": "grave",
                           "descripcion": "Falta grave capturada en la prueba",
                           "fecha": str(manana(-1))},
                     headers=sesion("consultor"))
    assert r.status_code == 201, r.text

    despues = _ficha(cliente, sesion, juan)["calificacion"]
    assert despues == antes


def test_una_incidencia_autorizada_si_la_baja(cliente, sesion, datos):
    juan = datos["personal"]["Juan Ramirez"]["id"]
    antes = _ficha(cliente, sesion, juan)
    incidencias_antes = _dimension(antes, "incidencias")["valor"]

    incidencia = cliente.post(
        "/incidencias",
        json={"persona_id": juan, "gravedad": "leve",
              "descripcion": "Queja menor del cliente por el trato",
              "fecha": str(manana(-1))},
        headers=sesion("consultor")).json()
    vb = cliente.post(f"/incidencias/{incidencia['incidencia_id']}/visto-bueno",
                      json={"autorizar": True,
                            "resolucion": "Se confirma la queja del cliente"},
                      headers=sesion("diroperaciones"))
    assert vb.status_code == 200, vb.text

    despues = _dimension(_ficha(cliente, sesion, juan), "incidencias")["valor"]
    assert despues == incidencias_antes - 25


def test_los_pesos_tienen_que_sumar_cien(cliente, sesion, datos):
    r = cliente.put("/profesionalismo/pesos",
                    json={"pais_id": datos["mx"]["id"],
                          "pesos": {"estrellas": 50, "satisfaccion": 50,
                                    "incidencias": 50, "capacitacion": 10,
                                    "experiencia": 10}},
                    headers=sesion("admin"))
    assert r.status_code == 409
    assert r.json()["detail"]["suma"] == 170


def test_no_se_pueden_dejar_dimensiones_fuera(cliente, sesion, datos):
    r = cliente.put("/profesionalismo/pesos",
                    json={"pais_id": datos["mx"]["id"],
                          "pesos": {"estrellas": 60, "satisfaccion": 40}},
                    headers=sesion("admin"))
    assert r.status_code == 400


def test_cambiar_los_pesos_cambia_la_calificacion(cliente, sesion, datos):
    juan = datos["personal"]["Juan Ramirez"]["id"]
    antes = _ficha(cliente, sesion, juan)["calificacion"]

    r = cliente.put("/profesionalismo/pesos",
                    json={"pais_id": datos["mx"]["id"],
                          "pesos": {"estrellas": 10, "satisfaccion": 10,
                                    "incidencias": 70, "capacitacion": 5,
                                    "experiencia": 5}},
                    headers=sesion("admin"))
    assert r.status_code == 200, r.text
    despues = _ficha(cliente, sesion, juan)["calificacion"]
    assert despues != antes


def test_el_tablero_ordena_de_mejor_a_peor(cliente, sesion, datos):
    r = cliente.get("/profesionalismo",
                    params={"pais_id": datos["mx"]["id"]},
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    filas = r.json()
    assert len(filas) > 1
    notas = [f["calificacion"] for f in filas]
    assert notas == sorted(notas, reverse=True)


def test_la_recomendacion_muestra_la_calificacion(cliente, sesion, datos):
    """Entre dos personas libres, el consultor ve a quien conviene mandar."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(600), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]

    r = cliente.get(f"/servicios/jornadas/{j['id']}/recomendaciones",
                    params={"perfil_id": datos["perfiles"]["conductor_seguridad"]["id"],
                            "categoria_id": datos["categorias"]["suv_blindada"]["id"]},
                    headers=h)
    assert r.status_code == 200, r.text
    disponibles = r.json()["personal"]["disponibles"]
    assert disponibles
    assert all("calificacion" in p for p in disponibles)
    notas = [p["calificacion"] or 0 for p in disponibles]
    assert notas == sorted(notas, reverse=True)


def test_las_horas_de_experiencia_cuentan(cliente, sesion, datos):
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    antes = _dimension(_ficha(cliente, sesion, juan), "experiencia")["horas"]

    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(610), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("juan"), j)

    despues = _dimension(_ficha(cliente, sesion, juan), "experiencia")["horas"]
    assert despues > antes


def test_sin_parametros_en_la_base_se_usan_los_valores_reales():
    """El objeto de SQLAlchemy sin guardar trae todo en nulo.

    Este es el error que tumbo la pantalla la primera vez, y el que
    ademas hacia que los castigos por incidencia valieran cero en
    silencio. Se prueba sin base porque es logica pura.
    """
    from decimal import Decimal

    from app.profesionalismo import _Parametros, parametros  # noqa: F401

    p = _Parametros(None)
    assert p.meses_ventana == 6
    assert p.horas_referencia == 2000
    assert p.castigo_leve == Decimal("25")
    assert p.castigo_grave == Decimal("60")


def test_lo_que_si_esta_en_la_base_gana_sobre_el_valor_por_defecto():
    from decimal import Decimal

    from app.profesionalismo import _Parametros

    class Fila:
        meses_ventana = 12
        horas_referencia = None          # incompleto: se rellena
        castigo_error_menor = Decimal("5")
        castigo_leve = Decimal("40")
        castigo_grave = None

    p = _Parametros(Fila())
    assert p.meses_ventana == 12
    assert p.horas_referencia == 2000
    assert p.castigo_leve == Decimal("40")
    assert p.castigo_grave == Decimal("60")


def test_la_ficha_dice_con_que_correo_entra(cliente, sesion, datos):
    """Debajo del nombre va el usuario, no la contraseña.

    Quien arma un equipo mira esta pantalla y la pregunta que sigue es
    si esa persona puede abrir la app. Salir a Accesos a buscarla otra
    vez es como se pierde media tarde.

    La contraseña no aparece aquí porque no existe en ningún lado: se
    guarda un hash. Lo único que se puede decir es si ya puso una.
    """
    h = sesion("dirgeneral")
    juan = datos["personal"]["Juan Ramirez"]["id"]

    f = cliente.get(f"/profesionalismo/persona/{juan}", headers=h).json()
    assert "usuario" in f, "la ficha no trae el usuario"
    if f["usuario"]:
        assert set(f["usuario"]) == {"correo", "activo",
                                     "ya_puso_contrasena"}
        assert "@" in f["usuario"]["correo"]
        # Lo que nunca puede salir de aquí: el hash, ni un pedazo.
        assert "hash" not in str(f).lower()

    # Y en la lista, que es donde se busca a alguien.
    pais = datos["personal"]["Juan Ramirez"].get("pais_id") or 1
    lista = cliente.get(f"/profesionalismo?pais_id={pais}", headers=h).json()
    assert all("usuario" in x for x in lista), "a la lista le falta"

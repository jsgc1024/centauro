"""El Nivel Centauro (seccion 138).

Lo que se cuida: el archivo del Secretariado se suma bien por componente
(sin tentativas, «no especificado» al estado); el nivel sale de pesos y
percentiles; un componente sin datos no cuenta como cero; un municipio
chico no salta al 100 por un solo caso; lo publicado no se recalcula ni
se ajusta; publica el jefe de turno.
"""
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest

from app import fuentes_riesgo as fuentes
from app import models as m
from app import nivel_centauro as motor
from app.db import SessionLocal
from tests.test_riesgo_clientes import cat, cliente_ci  # noqa: F401

ENCABEZADO = ("Año,Clave_Ent,Entidad,Cve. Municipio,Municipio,"
              "Bien jurídico afectado,Tipo de delito,Subtipo de delito,"
              "Modalidad,Sexo,Rango de edad,Enero,Febrero,Marzo,Abril,Mayo,"
              "Junio,Julio,Agosto,Septiembre,Octubre,Noviembre,Diciembre")


def _renglon(clave, tipo, subtipo, modalidad, meses):
    ent = clave // 1000
    valores = ",".join(str(x) for x in (meses + [0] * 12)[:12])
    return (f"2026,{ent:02d},Estado,{clave},Municipio,Bien,{tipo},{subtipo},"
            f"{modalidad},Hombre,18 a 29 años,{valores}")


def _archivo(renglones, comprimido=False) -> bytes:
    texto = "﻿" + ENCABEZADO + "\r\n" + "\r\n".join(renglones) + "\r\n"
    crudo = texto.encode("utf-8")
    if not comprimido:
        return crudo
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("RNID-Víctimas_Municipal-2026-ago2026.csv", crudo)
    return salida.getvalue()


# Reynosa (28032), Matamoros (28022), Nuevo Laredo (28027), un municipio
# chico de Tamaulipas (28007, Burgos) y Monterrey (19039).
RENGLONES = [
    _renglon(28032, "Homicidio", "Homicidio doloso", "Con arma de fuego",
             [10, 12, 9, 11, 10, 8, 9, 10]),
    _renglon(28032, "Homicidio", "Tentativa de homicidio doloso",
             "Tentativa de homicidio doloso", [50] * 8),
    _renglon(28032, "Robo", "Robo a transportista", "Con violencia", [5] * 8),
    _renglon(28032, "Robo", "Robo a transportista", "Sin violencia", [40] * 8),
    _renglon(28022, "Homicidio", "Homicidio doloso", "Con arma de fuego",
             [2] * 8),
    _renglon(28027, "Extorsión", "Extorsión presencial", "Extorsión presencial",
             [3] * 8),
    _renglon(28007, "Homicidio", "Homicidio doloso", "Con arma de fuego",
             [1, 0, 0, 0, 0, 0, 0, 0]),
    _renglon(19039, "Homicidio", "Homicidio doloso", "Con arma de fuego",
             [4] * 8),
    _renglon(28999, "Homicidio", "Homicidio doloso", "No especificado",
             [1] * 8),
    # Un renglon con coma adentro, entre comillas, como el del robo de
    # cables del archivo real.
    '2026,28,Tamaulipas,28032,Reynosa,El patrimonio,Robo,"Robo de maquinaria'
    ' - Cables, tubos",Con violencia,Hombre,18 a 29 años,1,1,1,1,1,1,1,1,0,0,0,0',
]


def test_leer_el_archivo_del_secretariado():
    datos = fuentes.leer_sesnsp(_archivo(RENGLONES, comprimido=True))
    assert datos["anio"] == 2026 and datos["ultimo_mes"] == 8
    s = datos["sumas"]
    assert s[("violencia_letal", 28032, "28", 1)] == 10
    # Las tentativas y el robo sin violencia no cuentan.
    assert ("violencia_letal", 28032, "28", 1) in s
    assert s[("delitos_violencia", 28032, "28", 1)] == 6   # 5 + 1 de cables
    assert s[("delincuencia_organizada", 28027, "28", 3)] == 3


def test_un_archivo_que_no_es_no_pasa():
    with pytest.raises(Exception) as e:
        fuentes.leer_sesnsp(b"a,b,c\n1,2,3\n")
    assert "columnas" in str(e.value.detail)


def _guardar(renglones=RENGLONES):
    db = SessionLocal()
    try:
        carga = fuentes.guardar_sesnsp(db, fuentes.leer_sesnsp(
            _archivo(renglones)), "subida", "prueba.csv", None)
        db.commit()
        return carga.periodo
    finally:
        db.close()


def test_guardar_reemplaza_el_ano_y_manda_lo_sin_municipio_al_estado():
    assert _guardar() == date(2026, 8, 1)
    _guardar()          # dos veces: no se duplica
    db = SessionLocal()
    try:
        reynosa = db.query(m.Municipio).filter_by(clave=28032).one()
        filas = db.query(m.CifraOficial).filter_by(
            municipio_id=reynosa.id, componente="violencia_letal").all()
        assert sorted(f.valor for f in filas) == sorted(
            [10, 12, 9, 11, 10, 8, 9, 10])
        sin = db.query(m.CifraOficial).filter_by(municipio_id=None).all()
        assert {f.valor for f in sin} == {1}
        assert len(sin) == 8
    finally:
        db.close()


def _calcular(periodo=date(2026, 8, 1)):
    db = SessionLocal()
    try:
        pais = db.query(m.Pais).filter_by(codigo="MX").one()
        mes = motor.calcular(db, pais, periodo)
        db.commit()
        return mes.id
    finally:
        db.close()


def _lugar(mes_id, clave=None, region=None):
    db = SessionLocal()
    try:
        q = db.query(m.NivelLugar).filter_by(nivel_mes_id=mes_id)
        if clave:
            mun = db.query(m.Municipio).filter_by(clave=clave).one()
            fila = q.filter_by(municipio_id=mun.id).one()
        else:
            reg = db.query(m.Region).filter_by(nombre=region).one()
            fila = q.filter_by(region_id=reg.id, municipio_id=None).one()
        return float(fila.valor), json.loads(fila.componentes), fila.sin_reporte
    finally:
        db.close()


def test_el_nivel_sale_de_los_componentes_que_hay():
    _guardar()
    mes_id = _calcular()
    db = SessionLocal()
    try:
        resumen = json.loads(db.get(m.NivelMes, mes_id).resumen)
    finally:
        db.close()
    # Sin ENSU ni ENVIPE: esos componentes no cuentan como cero.
    # Ni cifra negra: sin un solo hecho publicado no distingue a nadie.
    assert set(resumen["faltan"]) == {"miedo", "no_denuncia", "cifra_negra"}
    reynosa, comps, _ = _lugar(mes_id, 28032)
    assert comps["miedo"]["p"] is None
    assert comps["violencia_letal"]["p"] > 95
    # Reynosa arriba de Monterrey: mas homicidios por habitante.
    monterrey, _, _ = _lugar(mes_id, 19039)
    assert reynosa > monterrey
    tamaulipas, _, _ = _lugar(mes_id, region="Tamaulipas")
    assert 0 < tamaulipas <= 100


def test_un_municipio_chico_no_salta_por_un_caso():
    _guardar()
    mes_id = _calcular()
    _, burgos, _ = _lugar(mes_id, 28007)
    _, reynosa, _ = _lugar(mes_id, 28032)
    db = SessionLocal()
    try:
        # Burgos tiene unos 4 mil habitantes: un homicidio en 8 meses es
        # una tasa cruda enorme. Mezclada con la de su estado, no pasa a
        # la de Reynosa.
        assert burgos["violencia_letal"]["tasa"] < \
            reynosa["violencia_letal"]["tasa"] * 3
    finally:
        db.close()


def test_sin_reporte_se_marca():
    _guardar()
    mes_id = _calcular()
    _, _, sin_reporte = _lugar(mes_id, 1001)     # Aguascalientes: no vino
    assert sin_reporte is True
    _, _, reynosa = _lugar(mes_id, 28032)
    assert reynosa is False


def test_la_cifra_negra_cuenta_por_nivel(cliente, sesion, datos):
    _guardar()
    db = SessionLocal()
    try:
        pais = db.query(m.Pais).filter_by(codigo="MX").one()
        tam = db.query(m.Region).filter_by(nombre="Tamaulipas").one()
        tipo = db.query(m.TipoEvento).filter_by(pais_id=pais.id).first()
        cuando = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
        for nivel in (4, 3):
            db.add(m.EventoRiesgo(
                folio=f"CI-90{nivel}", pais_id=pais.id, region_id=tam.id,
                municipio="Matamoros", tipo_id=tipo.id, nivel=nivel,
                titulo="Hecho de prueba", texto_cliente="x",
                ocurrio_en=cuando, vigente_hasta=cuando + timedelta(days=1),
                estado=m.EstadoEvento.CERRADO, publicado_en=cuando))
        db.commit()
    finally:
        db.close()
    mes_id = _calcular()
    _, matamoros, _ = _lugar(mes_id, 28022)
    _, nuevo_laredo, _ = _lugar(mes_id, 28027)
    assert matamoros["cifra_negra"]["tasa"] > nuevo_laredo["cifra_negra"]["tasa"]


def test_encuestas_por_ciudad_y_por_estado(cliente, sesion):
    h = sesion("diroperaciones")
    ensu = "ciudad,porcentaje\nReynosa,86.6\nCiudad de México,51.3\n" \
           "Culiacán Rosales,90.8\nCiudad Inventada,10\n"
    r = cliente.post("/riesgo/nivel/fuentes/encuesta", headers=h,
                     data={"fuente": "ensu", "periodo": "2026-06-01"},
                     files={"archivo": ("ensu.csv", ensu.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    salida = r.json()
    assert salida["no_reconocidos"] == ["Ciudad Inventada"]
    # La Ciudad de Mexico va a sus 16 alcaldias.
    assert salida["guardados"] == 1 + 16 + 1
    envipe = "Estado;Prevalencia\nTamaulipas;24 515\nNuevo León;28 001\n"
    r = cliente.post("/riesgo/nivel/fuentes/encuesta", headers=h,
                     data={"fuente": "envipe_prevalencia",
                           "periodo": "2026-09-01"},
                     files={"archivo": ("envipe.csv", envipe.encode())})
    assert r.status_code == 200, r.text
    assert r.json()["guardados"] == 2


def test_revisar_ajustar_y_publicar(cliente, sesion):
    _guardar()
    r = cliente.post("/riesgo/nivel/calcular", json={"periodo": "2026-08-01"},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    mes = r.json()
    reynosa = next(x for x in cliente.get(
        f"/riesgo/nivel/{mes['id']}/estados/{_region('Tamaulipas')}",
        headers=sesion("central")).json()["municipios"]
        if x["municipio"] == "Reynosa")
    r = cliente.post(f"/riesgo/nivel/lugares/{reynosa['id']}/ajuste",
                     json={"valor": 95, "motivo": "corto"},
                     headers=sesion("central"))
    assert r.status_code == 400
    r = cliente.post(f"/riesgo/nivel/lugares/{reynosa['id']}/ajuste",
                     json={"valor": 95, "motivo": "Enfrentamientos diarios en "
                                                  "la colonia Las Fuentes"},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert r.json()["valor"] == 95 and r.json()["calculado"] != 95
    # La central no publica: es del jefe de turno.
    assert cliente.post(f"/riesgo/nivel/{mes['id']}/publicar",
                        headers=sesion("central")).status_code == 403
    r = cliente.post(f"/riesgo/nivel/{mes['id']}/publicar",
                     headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    # Publicado: ni se recalcula ni se ajusta.
    assert cliente.post("/riesgo/nivel/calcular",
                        json={"periodo": "2026-08-01"},
                        headers=sesion("central")).status_code == 409
    assert cliente.post(f"/riesgo/nivel/lugares/{reynosa['id']}/ajuste",
                        json={"valor": 10, "motivo": "Otro cambio con motivo"},
                        headers=sesion("central")).status_code == 409
    vista = cliente.get("/riesgo/nivel", headers=sesion("central")).json()
    assert vista["mes"]["estado"] == "publicado"
    assert len(vista["mes"]["lugares"]) == 32


def _region(nombre):
    db = SessionLocal()
    try:
        return db.query(m.Region).filter_by(nombre=nombre).one().id
    finally:
        db.close()


def test_pesos_y_cortes(cliente, sesion):
    h = sesion("diroperaciones")
    malos = {"violencia_letal": 50, "delitos_violencia": 50,
             "delincuencia_organizada": 0, "miedo": 0, "no_denuncia": 0,
             "cifra_negra": 10}
    assert cliente.put("/riesgo/nivel/parametros", json={"pesos": malos},
                       headers=h).status_code == 400
    assert cliente.put("/riesgo/nivel/parametros",
                       json={"cortes": [20, 42, 42, 80]},
                       headers=h).status_code == 400
    r = cliente.put("/riesgo/nivel/parametros",
                    json={"cortes": [20, 43, 60, 75]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["cortes"] == [20, 43, 60, 75]
    assert motor.rango(74, [20, 43, 60, 75]) == "medio_alto"
    assert motor.rango(75, [20, 43, 60, 75]) == "alto"


def test_buscar_el_enlace_en_la_pagina():
    html = ('<p><a href="https://x/a?e=1">Enero - agosto 2026 (Fuero común - '
            'Delitos). Incidencia delictiva municipal</a></p>'
            '<p><a href="https://x/b?e=2&amp;z=3">Enero - agosto 2026 (Fuero '
            'común - Víctimas). Incidencia delictiva municipal</a></p>'
            '<p><a href="https://x/c">2015 - 2025 (Fuero Común - Víctimas). '
            'Incidencia delictiva estatal</a></p>')
    enlace = fuentes.enlace_en_la_pagina(html)
    assert enlace == "https://x/b?e=2&z=3"
    assert fuentes.con_descarga(enlace) == "https://x/b?e=2&z=3&download=1"
    # Como la escribe de verdad gob.mx (3 oct): acentos y espacios como
    # entidades, y antes el tablero dinamico, que no es el archivo.
    real = ("<a href='https://x/tablero'>Enero - agosto&nbsp;2026 (Fuero "
            "com&uacute;n - V&iacute;ctimas).&nbsp;Tablero din&aacute;mico de "
            "Registro Nacional de Incidencia Delictiva municipal</a>"
            '<a href="https://x/zip?e=4">Enero - agosto&nbsp;2026 (Fuero '
            "com&uacute;n - V&iacute;ctimas). Incidencia delictiva "
            "municipal</a>")
    assert fuentes.enlace_en_la_pagina(real) == "https://x/zip?e=4"


def test_bajar_sin_conexion_no_revienta():
    class Roto:
        def get(self, *a, **k):
            raise OSError("sin red")
    db = SessionLocal()
    try:
        assert fuentes.bajar_sesnsp(db, Roto())["resultado"] == "sin_conexion"
    finally:
        db.close()


def test_el_cliente_ve_solo_lo_publicado_y_sin_el_motivo(cliente, sesion,
                                                          cliente_ci):  # noqa: F811
    from tests.test_cliente_ci import _entrar
    h = _entrar(cliente, cliente_ci)
    # Sin mes publicado: nada, aunque haya borrador.
    _guardar()
    mes_id = _calcular()
    assert cliente.get("/ci-api/fondo", headers=h).json() == {"mes": None}
    assert cliente.get(f"/ci-api/fondo/estados/{_region('Tamaulipas')}",
                       headers=h).status_code == 404

    estado = cliente.get(
        f"/riesgo/nivel/{mes_id}/estados/{_region('Tamaulipas')}",
        headers=sesion("central")).json()["estado"]
    assert cliente.post(f"/riesgo/nivel/lugares/{estado['id']}/ajuste",
                        json={"valor": 77, "motivo": "Lo que sabe la Central "
                                                     "y no el Secretariado"},
                        headers=sesion("central")).status_code == 200
    assert cliente.post(f"/riesgo/nivel/{mes_id}/publicar",
                        headers=sesion("diroperaciones")).status_code == 200

    fondo = cliente.get("/ci-api/fondo", headers=h).json()
    assert fondo["mes"]["periodo"] == "2026-08-01"
    assert len(fondo["estados"]) == 32
    mios = {x["region"] for x in fondo["estados"] if x["mio"]}
    assert mios == {"Tamaulipas", "Nuevo León"}
    # De los que no sigue, solo el color.
    otro = next(x for x in fondo["estados"] if not x["mio"])
    assert set(otro) == {"region_id", "region", "clave_region", "valor",
                         "rango", "mio"}

    ficha = cliente.get(f"/ci-api/fondo/estados/{_region('Tamaulipas')}",
                        headers=h)
    assert ficha.status_code == 200, ficha.text
    datos = ficha.json()
    # El ajustado es el que se ve, sin el motivo ni lo que calculo Connect.
    assert datos["estado"]["valor"] == 77
    assert datos["estado"]["rango"] == "medio_alto"
    assert len(datos["municipios"]) == 5
    texto = json.dumps(datos)
    assert "motivo" not in texto and "calculado" not in texto
    # De un estado que no sigue solo ve el color.
    assert cliente.get(f"/ci-api/fondo/estados/{_region('Jalisco')}",
                       headers=h).status_code == 404
    # Y la sesion de Centauro no abre la del cliente.
    assert cliente.get("/ci-api/fondo",
                       headers=sesion("central")).status_code == 401


def test_recalcular_no_borra_lo_ajustado(cliente, sesion):
    _guardar()
    mes_id = _calcular()
    estado = cliente.get(
        f"/riesgo/nivel/{mes_id}/estados/{_region('Tamaulipas')}",
        headers=sesion("central")).json()["estado"]
    assert cliente.post(f"/riesgo/nivel/lugares/{estado['id']}/ajuste",
                        json={"valor": 88, "motivo": "Operativo grande que "
                                                     "no sale en las cifras"},
                        headers=sesion("central")).status_code == 200
    # Llega una encuesta, o se pica Recalcular: el ajuste se queda.
    r = cliente.post("/riesgo/nivel/calcular", json={"periodo": "2026-08-01"},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    tamaulipas = next(x for x in r.json()["lugares"]
                      if x["region"] == "Tamaulipas")
    assert tamaulipas["valor"] == 88
    assert tamaulipas["ajuste_motivo"].startswith("Operativo grande")
    assert tamaulipas["calculado"] == estado["calculado"]

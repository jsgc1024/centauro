# -*- coding: utf-8 -*-
"""El archivo de los comprobantes (seccion 69).

Decision de Salvador, 25 de septiembre: tres meses despues de la factura
--o de la aprobacion de finanzas, mientras Odoo no este conectado--, las
fotos que subio el personal salen de Centauro y se van a un deposito de
Google. La foto se muda; el registro se queda.

Lo que no se puede perder, y es lo que se prueba: que ninguna foto quede
en ningun lado --si algo falla, se queda aqui--; que lo que llega al
archivo sea exactamente lo que se subio; que el reloj cuente desde donde
se decidio; y que lo que todavia se revisa no se toque.
"""
import hashlib
import socket
from datetime import date, datetime

import pytest

import ayudas_archivo as aa

FACTURA = datetime(2026, 12, 10, 12, 0)
APROBACION = datetime(2026, 12, 2, 17, 30)
ANTES = date(2027, 3, 9)
EL_DIA = date(2027, 3, 10)


@pytest.fixture
def google(monkeypatch):
    g, apagar = aa.levantar_google(monkeypatch)
    yield g
    apagar()


@pytest.fixture
def sin_odoo(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "odoo_url", "")


@pytest.fixture
def con_odoo(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "odoo_url", "https://odoo.example/facturas")


# ================================================================ el reloj

def test_los_meses_son_de_calendario():
    from app.archivo import sumar_meses

    assert sumar_meses(date(2026, 12, 10), 3) == date(2027, 3, 10)
    # El 30 de noviembre mas tres cae en el ultimo de febrero.
    assert sumar_meses(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert sumar_meses(date(2027, 11, 30), 3) == date(2028, 2, 29)
    assert sumar_meses(date(2026, 10, 31), 1) == date(2026, 11, 30)


def test_el_reloj_cuenta_desde_la_factura_o_sin_odoo_desde_la_aprobacion():
    from app import archivo
    from app import models as m

    facturado = m.Cierre(estatus=m.EstatusCierre.FACTURADO,
                         facturado_en=FACTURA, aprobado_en=APROBACION)
    r = archivo.reloj(facturado, conexion=True)
    assert r == {"desde": "factura", "inicio": date(2026, 12, 10),
                 "archivo": EL_DIA}

    sin_factura = m.Cierre(estatus=m.EstatusCierre.APROBADO,
                           aprobado_en=APROBACION)
    # Sin Odoo no hay factura que esperar: cuenta la aprobacion.
    assert archivo.reloj(sin_factura, conexion=False) == {
        "desde": "aprobacion", "inicio": date(2026, 12, 2),
        "archivo": date(2027, 3, 2)}
    # Con Odoo, lo aprobado sin factura espera a su factura.
    assert archivo.reloj(sin_factura, conexion=True) is None

    # Lo que finanzas no ha cerrado no tiene reloj, aunque ya lleve factura:
    # todavia la puede regresar a operacion y anularla.
    en_finanzas = m.Cierre(estatus=m.EstatusCierre.ENVIADO_FINANZAS,
                           facturado_en=FACTURA)
    assert archivo.reloj(en_finanzas, conexion=True) is None


# ================================================================ la mudanza

def test_apagado_no_sale_ninguna_foto(cliente, sesion, datos, monkeypatch):
    from app.config import settings

    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    monkeypatch.setattr(settings, "archivo_destino", "")
    r = aa.archivar(date(2030, 1, 1))
    assert r["resultado"] == "apagado"
    for (tabla, i) in s["fotos"]:
        assert aa.estado(tabla, i)["foto"]


def test_a_los_tres_meses_la_foto_se_muda_y_el_registro_se_queda(
        cliente, sesion, datos, google, con_odoo):
    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)

    # Un dia antes, nada.
    assert aa.archivar(ANTES)["archivadas"] == 0
    assert not google.objetos

    r = aa.archivar(EL_DIA)
    assert r["resultado"] == "listo"
    assert r["archivadas"] == len(s["fotos"]) == 6
    assert r["fallidas"] == 0 and r["pendientes"] == 0

    for (tabla, i), datos_ in s["fotos"].items():
        e = aa.estado(tabla, i)
        # Fuera de la base...
        assert e["foto"] is None
        assert e["archivado_en"] is not None
        # ...y en el archivo, identica, con su huella anotada.
        nombre = e["objeto"].removeprefix(f"gs://{aa.DEPOSITO}/")
        assert google.objetos[nombre]["datos"] == datos_
        assert e["md5"] == google.huella(nombre)
        assert e["bytes"] == len(datos_)
        assert nombre.startswith("comprobantes/" if tabla == "comprobante"
                                 else "devoluciones/")
        # El folio va en la ruta, sin la diagonal: en Google seria una
        # carpeta mas.
        assert f"/{s['folio'].replace('/', '_')}/" in nombre
        assert e["monto"] > 0            # el registro se queda

    # La foto viaja con sus datos, para que el archivo se entienda solo.
    uno = next(o for o in google.objetos.values()
               if o["metadatos"].get("concepto") == "combustible"
               and o["metadatos"]["persona"] == "Juan Ramirez")
    assert uno["metadatos"]["folio"] == s["folio"]
    assert uno["metadatos"]["monto"].startswith("1018.4")

    # La noche siguiente no hay nada que hacer, y nada se sube dos veces.
    subidas = len(google.subidas)
    assert aa.archivar(date(2027, 3, 11))["archivadas"] == 0
    assert len(google.subidas) == subidas


def test_sin_odoo_cuenta_desde_la_aprobacion(cliente, sesion, datos, google,
                                            sin_odoo):
    aa.eventual(cliente, sesion, datos, estatus="aprobado", facturado_en=None,
                aprobado_en=APROBACION)
    assert aa.archivar(date(2027, 3, 1))["archivadas"] == 0
    assert aa.archivar(date(2027, 3, 2))["archivadas"] == 6


def test_con_odoo_lo_aprobado_sin_factura_espera(cliente, sesion, datos, google,
                                                con_odoo):
    s = aa.eventual(cliente, sesion, datos, estatus="aprobado",
                    facturado_en=None, aprobado_en=APROBACION)
    assert aa.archivar(date(2028, 1, 1))["archivadas"] == 0
    assert all(aa.estado(t, i)["foto"] for t, i in s["fotos"])


def test_lo_que_finanzas_no_ha_cerrado_no_se_toca(cliente, sesion, datos,
                                                  google, con_odoo):
    """Con factura y todo: si sigue en finanzas, la foto se sigue
    revisando."""
    s = aa.eventual(cliente, sesion, datos, estatus="enviado_finanzas",
                    facturado_en=FACTURA, aprobado_en=None)
    assert aa.archivar(date(2028, 1, 1))["archivadas"] == 0
    assert all(aa.estado(t, i)["foto"] for t, i in s["fotos"])


def test_la_devolucion_sin_confirmar_se_queda(cliente, sesion, datos, google,
                                              con_odoo):
    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA,
                    devoluciones=(("285.00", "confirmada"),
                                  ("100.00", "declarada"),
                                  ("50.00", "rechazada")))
    r = aa.archivar(EL_DIA)
    assert r["archivadas"] == 7                     # 5 tickets + 2
    devoluciones = sorted(i for t, i in s["fotos"] if t == "devolucion")
    confirmada, declarada, rechazada = devoluciones
    assert aa.estado("devolucion", declarada)["foto"]
    assert aa.estado("devolucion", declarada)["archivado_en"] is None
    assert aa.estado("devolucion", confirmada)["archivado_en"]
    assert aa.estado("devolucion", rechazada)["archivado_en"]


def test_el_implantado_cuenta_mes_por_mes(cliente, sesion, datos, google,
                                         con_odoo):
    imp = aa.implantado_de_dos_meses(cliente, sesion, datos)
    (a1, m1, k1, dias1), (a2, m2, k2, dias2) = imp["meses"]
    _, fotos1 = aa.cerrar_mes(imp["servicio_id"], k1, dias1[0], datos,
                              "facturado", FACTURA, APROBACION, 11)
    # El segundo mes se facturo un mes despues: su reloj va un mes atras.
    _, fotos2 = aa.cerrar_mes(imp["servicio_id"], k2, dias2[0], datos,
                              "facturado", datetime(2027, 1, 10, 12, 0),
                              datetime(2027, 1, 9), 22)

    assert aa.archivar(EL_DIA)["archivadas"] == len(fotos1) == 2
    assert all(aa.estado(t, i)["archivado_en"] for t, i in fotos1)
    assert all(aa.estado(t, i)["foto"] for t, i in fotos2)

    assert aa.archivar(date(2027, 4, 10))["archivadas"] == 2
    assert all(aa.estado(t, i)["archivado_en"] for t, i in fotos2)


# ================================================================ cuando falla

def test_si_google_no_contesta_la_foto_se_queda_y_avisa(
        cliente, sesion, datos, google, con_odoo, monkeypatch):
    from app import archivo

    dicho = []
    monkeypatch.setattr(archivo, "_al_sistema", dicho.append)
    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    google.caido = True

    r = aa.archivar(EL_DIA)
    # Tres fallas seguidas y se deja para la noche siguiente.
    assert r["resultado"] == "con fallas"
    assert r["fallidas"] == archivo.SEGUIDAS == 3
    assert r["archivadas"] == 0 and r["pendientes"] == 6
    assert all(aa.estado(t, i)["foto"] for t, i in s["fotos"])
    # Una linea con ERROR: es lo que la alerta de Google busca.
    assert len(dicho) == 1 and dicho[0].startswith("ERROR:")

    google.caido = False
    r = aa.archivar(date(2027, 3, 11))
    assert r["archivadas"] == 6 and r["fallidas"] == 0
    assert not dicho[1].startswith("ERROR")


def test_si_lo_que_llego_no_cuadra_no_se_quita_de_la_base(
        cliente, sesion, datos, google, con_odoo):
    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    google.md5_de_otro = True
    r = aa.archivar(EL_DIA)
    assert r["archivadas"] == 0 and r["fallidas"] == 3
    assert "no cuadra" in r["errores"][0]
    assert all(aa.estado(t, i)["foto"] for t, i in s["fotos"])


def test_una_mudanza_a_medias_se_termina_la_noche_siguiente(
        cliente, sesion, datos, google, con_odoo):
    """La foto llego y la respuesta no: esa noche se queda en Centauro. La
    siguiente, Google dice que ya la tiene, se compara la huella y se
    termina, sin subirla dos veces ni escribir encima."""
    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    google.perder_respuesta = 1
    r = aa.archivar(EL_DIA)
    assert r["fallidas"] == 1 and r["archivadas"] == 5
    atorada = next((t, i) for t, i in s["fotos"]
                   if aa.estado(t, i)["foto"])
    assert len(google.objetos) == 6          # la foto si llego

    r = aa.archivar(date(2027, 3, 11))
    assert r["archivadas"] == 1 and r["fallidas"] == 0
    e = aa.estado(*atorada)
    assert e["foto"] is None and e["archivado_en"]
    nombre = e["objeto"].removeprefix(f"gs://{aa.DEPOSITO}/")
    assert google.objetos[nombre]["datos"] == s["fotos"][atorada]
    assert len(google.objetos) == 6


def test_el_tope_de_la_noche_se_lleva_lo_mas_viejo_primero(
        cliente, sesion, datos, google, con_odoo, monkeypatch):
    from app.config import settings

    viejo = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA,
                        offset=610)
    nuevo = aa.eventual(cliente, sesion, datos,
                        facturado_en=datetime(2026, 12, 20, 12, 0), offset=620)
    monkeypatch.setattr(settings, "archivo_por_noche", 4)

    r = aa.archivar(date(2027, 4, 1))
    assert r["archivadas"] == 4 and r["pendientes"] == 8
    assert sum(1 for t, i in viejo["fotos"]
               if aa.estado(t, i)["archivado_en"]) == 4
    assert not any(aa.estado(t, i)["archivado_en"] for t, i in nuevo["fotos"])

    monkeypatch.setattr(settings, "archivo_por_noche", 3000)
    assert aa.archivar(date(2027, 4, 2))["archivadas"] == 8


def test_el_aviso_llega_al_syslog_con_su_etiqueta(tmp_path, monkeypatch):
    """Lo que la alerta de Google lee: una linea en el syslog de la
    maquina, con la etiqueta y la palabra ERROR."""
    from app import archivo

    ruta = str(tmp_path / "dev-log")
    oido = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    oido.bind(ruta)
    oido.settimeout(5)
    try:
        monkeypatch.setattr(archivo, "SYSLOG", ruta)
        archivo._contar_la_noche({"archivadas": 2, "fallidas": 1,
                                  "pendientes": 1,
                                  "errores": ["CEN-2026-0612: Google dormido"]})
        linea = oido.recv(4096).decode()
    finally:
        oido.close()
    assert "centauro-archivo: ERROR: 1 foto(s)" in linea
    assert "CEN-2026-0612" in linea


# ================================================================ traerla

def test_traerla_del_archivo_compara_su_huella(cliente, sesion, datos, google,
                                              con_odoo):
    from app import archivo
    from app import models as m
    from app.db import SessionLocal

    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    aa.archivar(EL_DIA)
    (tabla, i), original = next(iter(s["fotos"].items()))
    with SessionLocal() as db:
        fila = db.get(m.Comprobante if tabla == "comprobante"
                      else m.DevolucionViatico, i)
        r = archivo.traer(fila)
        assert r["datos"] == original and r["coincide"] is True
        assert r["tipo"] == "image/jpeg"

        # Alguien la cambio alla: se dice, no se ensena como buena.
        nombre = fila.archivo_objeto.removeprefix(f"gs://{aa.DEPOSITO}/")
        google.objetos[nombre]["datos"] = b"otra cosa"
        assert archivo.traer(fila)["coincide"] is False


def test_el_nombre_lleva_la_huella(cliente, sesion, datos, google, con_odoo):
    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    aa.archivar(EL_DIA)
    for (tabla, i), original in s["fotos"].items():
        huella = hashlib.md5(original).hexdigest()
        assert aa.estado(tabla, i)["objeto"].endswith(
            f"{tabla}-{i}-{huella[:8]}.jpg")

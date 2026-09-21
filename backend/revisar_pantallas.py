# -*- coding: utf-8 -*-
"""El contrato de pantalla: qué llega vacío y qué llega de más.

Recorre los endpoints que usa cada pantalla, contra los servicios que
dejó `sembrar_360.py`, y reporta tres cosas:

  - **Lo que nunca trae valor.** Un campo vacío en un borrador es
    normal; el mismo campo vacío en los trece escenarios es otra cosa:
    o nadie lo llena nunca, o la pantalla pinta un hueco. Esa es la
    señal fuerte y por eso va primero.
  - **Lo que pesa de más.** Una respuesta de megabytes es información
    que viaja y nadie mira. Ya pasó: el endpoint de unidades mandaba
    las fotos de unidades ajenas a cada teléfono.
  - **Lo que truena.** Un endpoint que la pantalla llama y contesta 500
    o 404 con datos de verdad.

**No juzga.** Dice dónde hay huecos; cuáles importan lo decide quien
conoce la operación. Esto es la mitad del trabajo: la de detectar. La
de juzgar sigue siendo de una persona frente a la pantalla.

    docker compose exec -T api python revisar_pantallas.py
    docker compose exec -T api python revisar_pantallas.py --todo
"""
import json
import sys

sys.path.insert(0, "tests")

from fastapi.testclient import TestClient          # noqa: E402

from app import models as m                        # noqa: E402
from app.db import SessionLocal                    # noqa: E402
from app.main import app                           # noqa: E402

from sembrar_360 import (CORREO, catalogos, entrar,  # noqa: E402
                         revisar_donde_estamos, sembrados)

# Arriba de esto, una respuesta deja de ser "datos" y es "carga". No es
# un limite técnico: es el tamaño a partir del cual alguien con media
# barra de señal deja de ver la pantalla.
KB_QUE_PESA = 200

# Campos que se dejan vacíos a propósito y no son hallazgo. Se listan
# uno por uno --no por patrón-- para que agregar uno cueste pensarlo.
ESPERADOS = {
    # Lo que solo existe cuando algo salió mal.
    "motivo_rechazo", "resolucion", "atendida_por", "cerrada_en",
    "motivo_cierre", "relevado_en", "relevado_por",
    # Lo que solo existe al final del camino.
    "pagado_en", "cerrado_en", "confirmada_en", "corregido_en",
    # Lo que el cliente a veces no da.
    "vuelo", "agenda", "nota", "notas", "descripcion", "segundo_apellido",
}


# ==================================================================
# Las pantallas, con lo que cada una pide
# ==================================================================

# {s} servicio, {e} equipo, {j} jornada, {p} pais
PANTALLAS = [
    ("Panorama", "admin", ["/panorama", "/panorama/marcas"]),
    ("La central", "central", ["/central/tablero", "/central/camino",
                               "/operacion/dias-sin-cerrar"]),
    ("Cartera", "consultor", ["/servicios"]),
    ("Servicio", "consultor", [
        "/servicios/{s}",
        "/servicios/{s}/revisiones",
        "/servicios/{s}/programacion",
        "/servicios/equipos/{e}/asignaciones",
        "/task-sheets/servicio/{s}/vista-previa",
        "/hospedajes/equipo/{e}",
        "/viaticos/equipos/{e}",
        "/cierre/servicio/{s}/comparativo",
        "/cierre/servicio/{s}/revision",
    ]),
    ("Finanzas", "finanzas", [
        "/viaticos/finanzas/bandeja",
        "/viaticos/finanzas/corte",
        "/viaticos/finanzas/devoluciones",
        "/viaticos/finanzas/por-comprobar",
        "/viaticos/finanzas/depositado",
    ]),
    ("Nómina", "finanzas", ["/nomina?pais_id={p}",
                            "/nomina/tabulador?pais_id={p}",
                            "/nomina/ajustes/pendientes?pais_id={p}"]),
    ("Equipo", "consultor", ["/catalogos/personal", "/catalogos/vehiculos"]),
    ("Accesos", "admin", ["/auth/usuarios"]),
    ("App de campo", "juan", [
        "/campo/mi-dia", "/campo/mis-viaticos", "/campo/mis-comisiones",
        "/campo/mi-calificacion", "/campo/mi-capacitacion",
        "/campo/servicios/{s}/unidades",
    ]),
]


# ==================================================================
# El recorrido de una respuesta
# ==================================================================

def _vacio(valor) -> bool:
    return valor is None or valor == "" or valor == [] or valor == {}


def recorrer(dato, camino="", huecos=None, llenos=None):
    """Camina el JSON y anota qué campo vino vacío y cuál con valor.

    Los renglones de una lista se juntan bajo el mismo camino --`[]`--
    porque lo que interesa es el campo, no en qué renglón salió.
    """
    huecos = huecos if huecos is not None else set()
    llenos = llenos if llenos is not None else set()
    if isinstance(dato, dict):
        for clave, valor in dato.items():
            suyo = f"{camino}.{clave}" if camino else clave
            if isinstance(valor, (dict, list)) and valor:
                # Una lista con renglones ES un campo con valor. Sin
                # esta línea, `personal` con tres personas no contaba
                # como lleno --solo se recursaba-- y el mismo campo,
                # vacío en un borrador, salía reportado como "nunca
                # trajo valor". Media pantalla del reporte era eso.
                llenos.add(suyo)
                recorrer(valor, suyo, huecos, llenos)
            elif _vacio(valor):
                huecos.add(suyo)
            else:
                llenos.add(suyo)
    elif isinstance(dato, list):
        for fila in dato[:40]:          # con cuarenta renglones alcanza
            recorrer(fila, f"{camino}[]", huecos, llenos)
    return huecos, llenos


def _mensaje(r) -> str:
    """Lo que dijo el servidor, sin el envoltorio."""
    try:
        detalle = r.json().get("detail")
    except ValueError:
        return r.text[:100]
    if isinstance(detalle, dict):
        return str(detalle.get("mensaje") or detalle)[:100]
    return str(detalle or r.text)[:100]


def _imagenes(crudo: str) -> int:
    """Cuántos kilobytes de imágenes incrustadas trae la respuesta."""
    total = 0
    desde = 0
    while True:
        i = crudo.find("data:image", desde)
        if i < 0:
            return total // 1024
        fin = crudo.find('"', i)
        fin = fin if fin > 0 else len(crudo)
        total += fin - i
        desde = fin


# ==================================================================
# La pasada
# ==================================================================

def contexto(db) -> list[dict]:
    """Un juego de identificadores por cada servicio sembrado."""
    casos = []
    for servicio in sembrados(db):
        equipo = servicio.equipos[0] if servicio.equipos else None
        jornada = equipo.jornadas[0] if equipo and equipo.jornadas else None
        casos.append({"s": servicio.id,
                      "e": equipo.id if equipo else 0,
                      "j": jornada.id if jornada else 0,
                      "folio": servicio.folio,
                      "p": servicio.pais_id})
    return casos


def pasada(todo: bool = False) -> None:
    revisar_donde_estamos()
    with SessionLocal() as db:
        casos = contexto(db)
    if not casos:
        raise SystemExit(
            "No hay nada sembrado. Corre primero:\n"
            "  docker compose exec -T api python sembrar_360.py")

    with TestClient(app) as c:
        s = entrar(c)
        cat = catalogos(c, s)
        for caso in casos:
            caso.setdefault("p", cat["mx"]["id"])

        for pantalla, rol, rutas in PANTALLAS:
            cabecera = s(rol)
            # Por ruta: dónde vino vacío y dónde vino lleno, sumando
            # todos los servicios. Un campo que nunca se llenó en
            # ninguno es la señal que importa.
            huecos_de = {}
            llenos_de = {}
            problemas = []
            reglas = []
            pesados = []

            for ruta in rutas:
                necesita = "{" in ruta
                usados = casos if necesita else casos[:1]
                for caso in usados:
                    url = ruta.format(**caso)
                    r = c.get(url, headers=cabecera)
                    if r.status_code != 200:
                        # Un 4xx con mensaje es una REGLA contestando, no
                        # una pantalla rota: "este servicio no tiene
                        # cotizacion" es la verdad. Se juntan por mensaje
                        # y con su cuenta, porque trece renglones iguales
                        # esconden el unico distinto.
                        destino = (problemas if r.status_code >= 500
                                   or r.status_code == 404 else reglas)
                        destino.append((ruta, r.status_code,
                                        _mensaje(r), caso.get("folio", "")))
                        continue
                    kb = len(r.content) // 1024
                    fotos = _imagenes(r.text)
                    if kb >= KB_QUE_PESA:
                        pesados.append((url, kb, fotos))
                    try:
                        dato = r.json()
                    except ValueError:
                        continue
                    h, ll = recorrer(dato)
                    huecos_de.setdefault(ruta, set()).update(h)
                    llenos_de.setdefault(ruta, set()).update(ll)

            print(f"\n{'='*66}\n  {pantalla}\n{'='*66}")

            for ruta, codigo, texto, _folio in problemas:
                print(f"  ✗ {codigo}  {ruta}\n      {texto}")

            if reglas:
                juntas = {}
                for ruta, codigo, texto, folio in reglas:
                    fila = juntas.setdefault((ruta, codigo, texto), [])
                    fila.append(folio)
                print("  Reglas que contestaron (no es un error, es el "
                      "sistema diciendo que no):")
                for (ruta, codigo, texto), folios in juntas.items():
                    cuantos = (f"{len(folios)} servicios" if len(folios) > 1
                               else folios[0])
                    print(f"    {codigo} · {ruta} · {cuantos}")
                    print(f"      {texto}")

            for url, kb, fotos in pesados:
                extra = f", {fotos} KB de imágenes" if fotos else ""
                print(f"  ⚠ pesa {kb} KB{extra}  {url}")

            nunca = []
            for ruta, huecos in huecos_de.items():
                llenos = llenos_de.get(ruta, set())
                for campo in sorted(huecos - llenos):
                    if campo.split(".")[-1].replace("[]", "") in ESPERADOS:
                        continue
                    nunca.append((ruta, campo))

            if nunca:
                print("  Nunca trajo valor, en ningún escenario:")
                por_ruta = {}
                for ruta, campo in nunca:
                    por_ruta.setdefault(ruta, []).append(campo)
                for ruta, campos in por_ruta.items():
                    print(f"    {ruta}")
                    for campo in campos:
                        print(f"      · {campo}")

            if todo:
                a_veces = []
                for ruta, huecos in huecos_de.items():
                    llenos = llenos_de.get(ruta, set())
                    a_veces += [(ruta, x) for x in sorted(huecos & llenos)]
                if a_veces:
                    print("  A veces vacío (normal en un borrador, "
                          "sospechoso en uno cerrado):")
                    for ruta, campo in a_veces:
                        print(f"    {ruta} · {campo}")

            if not problemas and not pesados and not nunca:
                print("  Sin huecos que reportar.")

    print(f"\n{'='*66}")
    print("  Lo de arriba dice DÓNDE hay huecos, no cuáles importan.")
    print("  Un borrador debe tener huecos; una hoja publicada no.")
    print(f"{'='*66}\n")


if __name__ == "__main__":
    pasada("--todo" in sys.argv)

# -*- coding: utf-8 -*-
"""Una prueba del panorama que fallaba de madrugada.

test_un_equipo_callado_sube_al_rengon_de_arriba creaba el servicio a las
7:00 y marcaba la llegada a las 10:00, o un minuto antes de la hora real
si todavia no eran las 10. Corrida entre las 4:30 y las 6:30, el panorama
leido media hora despues veia ese servicio de las 7:00 por arrancar, sin
unidad, y --con razon-- pedia atenderlo: la prueba esperaba "normal".
Fallo el 23 de septiembre a las 6:15.

Ahora el servicio arranca a la misma hora de la llegada: a los 30 y a los
61 minutos ya esta en curso, corra a la hora que corra, y lo que se mide
sigue siendo el silencio. Idempotente.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA = RAIZ / "backend/tests/test_panorama.py"

VIEJO = (
    "    h = sesion(\"consultor\")\n"
    "    hp = sesion(\"juan\")\n"
    "    servicio = _servicio_hoy(cliente, h, datos)\n"
    "    juan = datos[\"personal\"][\"Juan Ramirez\"][\"id\"]\n"
    "    # La hora de la marca no puede estar en el futuro: el candado la\n"
    "    # cambiaria por la del servidor y el silencio medido despues saldria\n"
    "    # de horas. Las 10:00 cuando ya pasaron; cuando no, hace un minuto.\n"
    "    # Las distancias --treinta minutos y sesenta y uno-- son lo que esta\n"
    "    # prueba mide, y esas no cambian.\n"
    "    arranque = min(_momento(10, 0),\n"
    "                   datetime.now().replace(second=0, microsecond=0)\n"
    "                   - timedelta(minutes=1))\n"
    "    _arrancar(cliente, h, hp, datos, servicio, juan, arranque)\n")
NUEVO = (
    "    h = sesion(\"consultor\")\n"
    "    hp = sesion(\"juan\")\n"
    "    juan = datos[\"personal\"][\"Juan Ramirez\"][\"id\"]\n"
    "    # La hora de la marca no puede estar en el futuro: el candado la\n"
    "    # cambiaria por la del servidor y el silencio medido despues saldria\n"
    "    # de horas. Las 10:00 cuando ya pasaron; cuando no, hace un minuto.\n"
    "    # Las distancias --treinta minutos y sesenta y uno-- son lo que esta\n"
    "    # prueba mide, y esas no cambian.\n"
    "    arranque = min(_momento(10, 0),\n"
    "                   datetime.now().replace(second=0, microsecond=0)\n"
    "                   - timedelta(minutes=1))\n"
    "    # Y el servicio arranca a esa misma hora. Arrancaba a las 7:00, y\n"
    "    # corrida de madrugada el panorama lo veia por arrancar, sin unidad,\n"
    "    # y pedia atenderlo: la prueba media otra cosa que el silencio.\n"
    "    servicio = _servicio_hoy(cliente, h, datos,\n"
    "                             hora=arranque.strftime(\"%H:%M:00\"))\n"
    "    _arrancar(cliente, h, hp, datos, servicio, juan, arranque)\n")

texto = io.open(RUTA, encoding="utf-8").read()
if NUEVO in texto:
    print("sin cambio", RUTA.relative_to(RAIZ))
else:
    assert texto.count(VIEJO) == 1, "no encontre la prueba como la conozco"
    with io.open(RUTA, "w", encoding="utf-8") as f:
        f.write(texto.replace(VIEJO, NUEVO))
    print("escrito ", RUTA.relative_to(RAIZ))

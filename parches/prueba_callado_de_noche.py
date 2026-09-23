# -*- coding: utf-8 -*-
"""Una prueba de la central que fallaba por la hora, no por el codigo.

test_el_servicio_callado_trae_con_que_asentar_la_marca armaba un dia
completo de hoy a las 07:00 fijas. Despues de las diez de la noche ese
dia ya paso su fin hace mas de tres horas y la central lo trata --bien--
como dia abandonado: sale del pulso, y la prueba no lo encontraba entre
los callados. Aparecio el 22 de septiembre en una corrida a las 23:30.

La hora de presentacion va ahora pegada a la hora en que corre la
bateria: una hora antes, o la medianoche si todavia no es la una.
Idempotente.
"""
import io
from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "backend/tests/test_central.py"

VIEJO = (
    "    ser otro día que el del navegador de quien la captura.\n"
    "    \"\"\"\n"
    "    from app import models as m\n"
    "    from app.db import SessionLocal\n"
    "\n"
    "    h = sesion(\"consultor\")\n"
    "    hoy = date.today()\n"
    "    servicio = crear_servicio(\n"
    "        cliente, h, datos,\n"
    "        [jornada(hoy, datos[\"modalidades\"][\"full_day\"][\"id\"])])\n")
NUEVO = (
    "    ser otro día que el del navegador de quien la captura.\n"
    "    \"\"\"\n"
    "    from app import models as m\n"
    "    from app.db import SessionLocal\n"
    "\n"
    "    h = sesion(\"consultor\")\n"
    "    hoy = date.today()\n"
    "    # Pegada a la hora en que corre la bateria. Con las 07:00 fijas,\n"
    "    # despues de las diez de la noche el dia ya habia pasado su fin hace\n"
    "    # mas de tres horas y la central lo trataba --bien-- como abandonado:\n"
    "    # la prueba fallaba por la hora y no por el codigo.\n"
    "    arranque = max(datetime.now() - timedelta(hours=1),\n"
    "                   datetime.combine(hoy, time(0, 0)))\n"
    "    servicio = crear_servicio(\n"
    "        cliente, h, datos,\n"
    "        [jornada(hoy, datos[\"modalidades\"][\"full_day\"][\"id\"],\n"
    "                 hora=arranque.strftime(\"%H:%M:00\"))])\n")

texto = io.open(RUTA, encoding="utf-8").read()
if NUEVO in texto:
    print("sin cambio", RUTA.name)
else:
    assert texto.count(VIEJO) == 1, f"el tramo esta {texto.count(VIEJO)} veces"
    with io.open(RUTA, "w", encoding="utf-8") as f:
        f.write(texto.replace(VIEJO, NUEVO))
    print("escrito ", RUTA.name)

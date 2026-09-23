# -*- coding: utf-8 -*-
"""Una prueba del panico que fallaba de madrugada, no por el codigo.

test_el_panico_dice_en_que_servicio_va_y_si_lleva_al_principal armaba el
dia de hoy a las 07:00 fijas y marcaba a las 07:05, 07:20 y 08:10. Antes
de las siete de la manana esas marcas quedaban en el futuro y el servidor
--bien-- las cambiaba por su propia hora: la prueba esperaba «07:05» y
veia «00:43». Aparecio el 23 de septiembre en una corrida a medianoche.

Ahora todo va en el pasado, a la hora que corra la bateria: el dia empezo
hace 70 minutos y las marcas caen dentro. Idempotente.
"""
import io
from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "backend/tests/test_contingencia.py"

CAMBIOS = [
    ("    from datetime import date, datetime, time\n"
     "\n"
     "    from ayudas import configurar_origen, marcar\n"
     "    from app import central as motor\n"
     "    from app.db import SessionLocal\n"
     "\n"
     "    h = sesion(\"consultor\")\n"
     "    hp = sesion(\"juan\")\n"
     "    servicio = crear_servicio(\n"
     "        cliente, h, datos,\n"
     "        [jornada(date.today(), datos[\"modalidades\"][\"full_day\"][\"id\"],\n"
     "                 hora=\"07:00:00\")])\n",
     "    from datetime import datetime, timedelta\n"
     "\n"
     "    from ayudas import configurar_origen, marcar\n"
     "    from app import central as motor\n"
     "    from app.db import SessionLocal\n"
     "\n"
     "    h = sesion(\"consultor\")\n"
     "    hp = sesion(\"juan\")\n"
     "    # Todo en el pasado, a la hora que corra la bateria. Con las 07:00\n"
     "    # fijas, antes de las siete de la manana las marcas quedaban en el\n"
     "    # futuro y el servidor las cambiaba por su propia hora: la prueba\n"
     "    # esperaba \"07:05\" y veia \"00:43\". Fallaba por la hora, no por\n"
     "    # el codigo.\n"
     "    inicio = (datetime.now().replace(second=0, microsecond=0)\n"
     "              - timedelta(minutes=70))\n"
     "    servicio = crear_servicio(\n"
     "        cliente, h, datos,\n"
     "        [jornada(inicio.date(), datos[\"modalidades\"][\"full_day\"][\"id\"],\n"
     "                 hora=inicio.strftime(\"%H:%M:00\"))])\n"),
    ("    hoy = date.today()\n"
     "    marcar(cliente, hp, j[\"id\"], \"llegada_origen\",\n"
     "           datetime.combine(hoy, time(7, 5)))\n",
     "    llegada = inicio + timedelta(minutes=5)\n"
     "    marcar(cliente, hp, j[\"id\"], \"llegada_origen\", llegada)\n"),
    ("    assert ficha[\"principal\"][\"ultima_marca\"] == \"07:05\"\n",
     "    assert ficha[\"principal\"][\"ultima_marca\"] == f\"{llegada:%H:%M}\"\n"),
    ("    marcar(cliente, hp, j[\"id\"], \"contacto_ejecutivo\",\n"
     "           datetime.combine(hoy, time(7, 20)))\n",
     "    marcar(cliente, hp, j[\"id\"], \"contacto_ejecutivo\",\n"
     "           inicio + timedelta(minutes=20))\n"),
    ("    marcar(cliente, hp, j[\"id\"], \"llegada_destino\",\n"
     "           datetime.combine(hoy, time(8, 10)))\n",
     "    marcar(cliente, hp, j[\"id\"], \"llegada_destino\",\n"
     "           inicio + timedelta(minutes=70))\n"),
]

texto = io.open(RUTA, encoding="utf-8").read()
nuevo = texto
for viejo, reemplazo in CAMBIOS:
    if reemplazo in nuevo:
        continue
    assert nuevo.count(viejo) == 1, f"el tramo esta {nuevo.count(viejo)} veces: {viejo[:60]}"
    nuevo = nuevo.replace(viejo, reemplazo)
if nuevo == texto:
    print("sin cambio", RUTA.name)
else:
    with io.open(RUTA, "w", encoding="utf-8") as f:
        f.write(nuevo)
    print("escrito ", RUTA.name)

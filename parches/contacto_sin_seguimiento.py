# -*- coding: utf-8 -*-
"""El aviso de contacto, sin seguimiento en vivo.

Decision de Salvador, 23 de septiembre: por ahora no se desarrolla el
seguimiento en vivo. Al hacer contacto con el ejecutivo, el solicitante
recibe el aviso de que ya se hizo contacto, sin boton ni enlace. El boton
llevaba a una pagina que nunca se construyo, y el enlace apuntaba fijo a
centauro.lat.

El mapeo del boton en correo.py se queda: si algun dia se hace el panel,
basta con volver a mandar el enlace. Idempotente.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"
ARCHIVOS = {
    "operacion": B / "app/operacion.py",
    "textos": B / "app/textos_aviso.py",
    "t_candados": B / "tests/test_candados.py",
    "bitacora": RAIZ / "BITACORA.md",
}
textos = {k: io.open(v, encoding="utf-8").read() for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(viejo) == 1, f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces"
    textos[clave] = t.replace(viejo, nuevo)


cambiar("operacion", "import math\nimport secrets\nfrom datetime", "import math\nfrom datetime",
        marca="import math\nfrom datetime")
# Quitar una linea: ya esta hecho si la linea no esta.
CONSTANTE = ("HORAS_VIGENCIA_ENLACE = 4          # el enlace de seguimiento "
             "expira tras el servicio\n")
if CONSTANTE in textos["operacion"]:
    textos["operacion"] = textos["operacion"].replace(CONSTANTE, "")
else:
    saltados.append("operacion: la constante ya no estaba")
cambiar("operacion",
        "        token = secrets.token_urlsafe(16)\n"
        "        expira = jornada.fin_programado + timedelta(hours=HORAS_VIGENCIA_ENLACE)\n"
        "        enlace = f\"https://centauro.lat/seguimiento/{token}\"\n",
        "        # Solo el aviso de que ya hubo contacto, sin enlace de\n"
        "        # seguimiento en vivo: no se desarrolla por ahora (decision de\n"
        "        # Salvador, 23 sep).\n")
cambiar("operacion",
        "                   ta.t(del_solicitante, \"inicio_cuerpo_solicitante\",\n"
        "                        hora=f\"{ahora:%H:%M}\"),\n"
        "                   enlace=enlace, expira=expira,\n"
        "                   pares=_pares_del_equipo(jornada, del_solicitante))\n",
        "                   ta.t(del_solicitante, \"inicio_cuerpo_solicitante\",\n"
        "                        hora=f\"{ahora:%H:%M}\"),\n"
        "                   pares=_pares_del_equipo(jornada, del_solicitante))\n")

for viejo, nuevo in (
        ("        \"inicio_cuerpo_solicitante\": (\"Contact was made with the principal \"\n"
         "                                      \"at {hora}. You can follow the \"\n"
         "                                      \"service live here.\"),\n",
         "        \"inicio_cuerpo_solicitante\": (\"Contact was made with the principal \"\n"
         "                                      \"at {hora}.\"),\n"),
        ("        \"inicio_cuerpo_solicitante\": (\"Se hizo contacto con el ejecutivo a \"\n"
         "                                      \"las {hora}. Puede seguir el servicio \"\n"
         "                                      \"en vivo desde aquí.\"),\n",
         "        \"inicio_cuerpo_solicitante\": (\"Se hizo contacto con el ejecutivo a \"\n"
         "                                      \"las {hora}.\"),\n"),
        ("        \"inicio_cuerpo_solicitante\": (\"O contato com o principal foi feito \"\n"
         "                                      \"às {hora}. Você pode acompanhar o \"\n"
         "                                      \"serviço ao vivo aqui.\"),\n",
         "        \"inicio_cuerpo_solicitante\": (\"O contato com o principal foi feito \"\n"
         "                                      \"às {hora}.\"),\n")):
    cambiar("textos", viejo, nuevo)

cambiar("t_candados",
        "def test_el_contacto_avisa_al_cliente_con_enlace_que_expira(cliente, sesion, datos):\n",
        "def test_el_contacto_avisa_al_cliente_sin_enlace(cliente, sesion, datos):\n"
        "    \"\"\"Al hacer contacto sale el aviso, sin seguimiento en vivo: no se\n"
        "    desarrolla por ahora (decision de Salvador, 23 sep).\"\"\"\n")
cambiar("t_candados",
        "    con_enlace = [n for n in al_solicitante if n[\"enlace\"]]\n"
        "    assert con_enlace, \"el solicitante debe recibir el enlace de seguimiento\"\n"
        "    assert con_enlace[0][\"expira\"] is not None, \"el enlace debe expirar\"\n",
        "    assert not [n for n in al_solicitante if n[\"enlace\"]], \\\n"
        "        \"el aviso de contacto ya no lleva enlace de seguimiento\"\n")

cambiar("bitacora",
        "## 14. Lo que falta\n",
        "## 53. El aviso de contacto, sin seguimiento en vivo\n"
        "\n"
        "Decisión de Salvador, 23 de septiembre: por ahora no se desarrolla el\n"
        "seguimiento en vivo. Al hacer contacto con el ejecutivo, el solicitante\n"
        "recibe el aviso de que ya se hizo contacto —«Se hizo contacto con el\n"
        "ejecutivo a las 10:40»—, sin botón ni enlace. El botón llevaba a una\n"
        "página que nunca se construyó y el enlace apuntaba fijo a centauro.lat.\n"
        "El resto de los correos no cambia. El mapeo del botón en `correo.py` se\n"
        "queda por si algún día se hace el panel.\n"
        "\n"
        "## 14. Lo que falta\n",
        marca="## 53. El aviso de contacto, sin seguimiento en vivo\n")

for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(textos[clave])
        print("escrito ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for s in saltados:
    print("saltado:", s)

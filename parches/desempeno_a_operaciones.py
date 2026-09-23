# -*- coding: utf-8 -*-
"""El boton de Desempeno pasa a Operaciones EP.

Decision de Salvador, 23 de septiembre. Estaba en Gestion
Administrativa, junto a la nomina, porque el bono es dinero. Lo que mide
es como trabajo la gente en la calle, y lo consulta quien decide a quien
se manda: va con Personal. Quien lo ve no cambia. Idempotente.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"
ARCHIVOS = {
    "app": B / "app/web/app.js",
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


cambiar("app",
        "  /* El bono del mes vencido: se calcula el dia 3 y se deposita el 5.\n"
        "     Va junto a la nomina porque es dinero, y aparte porque no viaja\n"
        "     en el corte semanal: la fecha es fija y el corte cae donde cae. */\n"
        "  { ruta: \"/bonos\", texto: \"nav_bonos\", grupo: \"nav_administrativa\",\n"
        "    cuenta: \"rec_bonos\", quienes: DESEMPENO },\n",
        "  /* El desempeno del personal y su bono del mes vencido, que se\n"
        "     calcula el dia 3 y se deposita el 5. Va en Operaciones EP\n"
        "     --decision de Salvador, 23 sep--, junto a Personal: lo que mide\n"
        "     es como trabajo la gente en la calle, y lo consulta quien decide\n"
        "     a quien se manda. Estaba junto a la nomina porque el bono es\n"
        "     dinero. */\n"
        "  { ruta: \"/bonos\", texto: \"nav_bonos\", grupo: \"nav_operaciones_ep\",\n"
        "    cuenta: \"rec_bonos\", quienes: DESEMPENO },\n")

cambiar("bitacora",
        "## 14. Lo que falta\n",
        "## 55. Desempeño, en Operaciones EP\n"
        "\n"
        "Decisión de Salvador, 23 de septiembre: el botón de Desempeño pasa de\n"
        "Gestión Administrativa a Operaciones EP, junto a Personal. Estaba con\n"
        "la nómina porque el bono es dinero; lo que mide es cómo trabajó la\n"
        "gente en la calle, y lo consulta quien decide a quién se manda. Quién\n"
        "lo ve no cambia.\n"
        "\n"
        "## 14. Lo que falta\n",
        marca="## 55. Desempeño, en Operaciones EP\n")

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

"""La clave adentro de t(), no la eleccion.

`revisar.py` verifica que toda clave literal t("x") exista en es, en y
pt. Escrito como t(cond ? "a" : "b") no ve ninguna de las dos, que es
justo donde se cuela la clave que falta en un idioma.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/servicio.js"
s = R.read_text()

CAMBIOS = [
    ('''        h("label", { clase: "chico" }, adelante,
          t(puerta.implantado ? "srv_hasta_fin_mes" : "srv_adelante")),''',
     '''        h("label", { clase: "chico" }, adelante,
          puerta.implantado ? t("srv_hasta_fin_mes") : t("srv_adelante")),'''),
    ('''          t(puerta.implantado ? "srv_alcance_imp_pie"
                              : "srv_alcance_pie"))))),''',
     '''          puerta.implantado ? t("srv_alcance_imp_pie")
                            : t("srv_alcance_pie"))))),'''),
]
for viejo, nuevo in CAMBIOS:
    assert s.count(viejo) == 1, viejo[:50]
    s = s.replace(viejo, nuevo)
R.write_text(s)
print("servicio.js: las claves quedan a la vista de revisar.py")

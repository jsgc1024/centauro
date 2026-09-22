# -*- coding: utf-8 -*-
"""Retoques del panel de la senal, vistos en el arnes con la consola de
verdad: el nombre del color no cambiaba al elegir otro; el radio de cada
opcion salia como caja de 100% (regla general de `input`); y la palabra
y la nota quedaban debajo del telefono en vez de a su lado, como en la
propuesta. Idempotente; escrituras al final."""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"
ARCHIVOS = {"servicio": B / "app/web/servicio.js", "css": B / "app/web/estilo.css"}
textos = {k: io.open(v, encoding="utf-8").read() for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(viejo) == 1, f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces"
    textos[clave] = t.replace(viejo, nuevo)


cambiar("servicio", '''  const telefono = h("div", { clase: "senal-telefono" });
  const frase = h("div", { clase: "chico gris", style: "margin-top:8px" });
  const pintarPrevia = () => {
    const c = colorElegido();
    telefono.style.background = c ? c.hex : "";
    telefono.style.color = c ? c.letra : "";
    const palabra = h("b", {}, texto.value.trim());
    telefono.replaceChildren(palabra);
''', '''  const telefono = h("div", { clase: "senal-telefono" });
  const frase = h("div", { clase: "chico gris", style: "margin-top:8px" });
  const nombre = h("div", { clase: "chico gris", style: "margin:-6px 0 12px" });
  const pintarPrevia = () => {
    const c = colorElegido();
    nombre.textContent = nombreColor();
    telefono.style.background = c ? c.hex : "";
    telefono.style.color = c ? c.letra : "";
    const palabra = h("b", {}, texto.value.trim());
    telefono.replaceChildren(palabra);
''')

cambiar("servicio", '''  const cajaColor = h("div", { clase: "senal-armado" },
    h("div", {},
      campo(t("srv_elige_color"), circulos),
      h("div", { clase: "chico gris" }, nombreColor())),
    telefono);
  const cajaTexto = h("div", { clase: "campo" }, etiquetaTexto, texto);
''', '''  const cajaColor = h("div", {}, campo(t("srv_elige_color"), circulos), nombre);
  const cajaTexto = h("div", { clase: "campo" }, etiquetaTexto, texto);
''')

cambiar("servicio", '''  const acomodar = () => {
    cajaColor.hidden = !comoColor.checked;
    frase.hidden = !comoColor.checked;
''', '''  const acomodar = () => {
    cajaColor.hidden = !comoColor.checked;
    telefono.hidden = !comoColor.checked;
    frase.hidden = !comoColor.checked;
''')

cambiar("servicio", '''    cajaColor, cajaTexto, cajaImagen,
    campo(t("srv_nota_senal"), nota),
    frase,
    h("div", { clase: "acciones", style: "margin-top:10px" },
      guardar,
      (actual.texto || actual.imagen || actual.color) ? quitar : ""));
''', '''    /* Lo que se captura a la izquierda; el telefono, como lo vera el
       principal, a la derecha y solo cuando la senal es de color. */
    h("div", { clase: "senal-armado" },
      h("div", {}, cajaColor, cajaTexto, cajaImagen,
        campo(t("srv_nota_senal"), nota), frase),
      telefono),
    h("div", { clase: "acciones", style: "margin-top:10px" },
      guardar,
      (actual.texto || actual.imagen || actual.color) ? quitar : ""));
''')

cambiar("css", '''.senal-opcion input { margin: 0 2px 0 0; vertical-align: -1px; }
''', '''.senal-opcion input { width: auto; padding: 0; margin: 0 6px 0 0; vertical-align: -1px; }
''')

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

# -*- coding: utf-8 -*-
"""La senal de color. Pedido de Salvador, 22 sep; propuesta aprobada
(PROPUESTA_SENAL_COLOR.md).

  * `app/senal.py`: la paleta --ocho colores con su hex y el color de
    la letra encima--; es la unica copia.
  * `servicio.senal_color` (clave de la paleta) + migracion.
  * PUT /servicios/{id}/senal acepta `color`; solo de la paleta.
  * La vista previa del task sheet trae la paleta y la senal con su
    color; la hoja impresa pinta el bloque de color con la frase en el
    idioma del principal.
  * La ficha del dia (app) trae el color; la app pinta el punto en la
    tarjeta y llena la pantalla con el color.
  * La consola: Color primero y recomendada, circulos, palabra encima
    opcional, nota, vista previa en vivo.

Idempotente. Todas las escrituras al final.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    "models": B / "app/models.py",
    "schemas": B / "app/schemas.py",
    "rts": B / "app/routers/tasksheet.py",
    "ts": B / "app/tasksheet.py",
    "html": B / "app/tasksheet_html.py",
    "textos": B / "app/textos.py",
    "campo": B / "app/routers/campo.py",
    "app": B / "app/web/campo/app.js",
    "appcss": B / "app/web/campo/estilo.css",
    "idioma": B / "app/web/idioma.js",
    "servicio": B / "app/web/servicio.js",
    "css": B / "app/web/estilo.css",
}
NUEVOS = {
    B / "app/senal.py": None,
    B / "migrations/versions/f3a8c1d2e5b7_senal_color.py": None,
    B / "tests/test_senal_color.py": None,
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


def cambiar_tramo(clave, desde, hasta, nuevo, marca):
    """Reemplaza desde la marca `desde` hasta justo antes de `hasta`."""
    t = textos[clave]
    if marca in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(desde) == 1 and t.count(hasta) == 1, clave
    i, j = t.index(desde), t.index(hasta)
    assert i < j
    textos[clave] = t[:i] + nuevo + t[j:]


# ================================================================ la paleta
NUEVOS[B / "app/senal.py"] = '''"""La senal de color: la paleta, y lo que se sabe de cada color.

Pedido de Salvador, 22 sep. La senal con la que el principal reconoce al
equipo puede ser un color: una pantalla de un solo color se distingue a
veinte metros sin leer nada, y no hay imagen que bajar ni guardar.

Esta es la UNICA copia de la paleta. La consola la recibe en la vista
previa del task sheet, la app en la ficha del dia, y la hoja del
principal la nombra en su idioma (`textos.py`, `color_<clave>`). El
color de la letra encima va decidido aqui, por color, y no calculado
en cada pantalla: asi se lee igual en el telefono, en la hoja y en la
consola.

Los ocho salieron de la propuesta; en el sistema no habia una paleta
secundaria de la marca. El dia que llegue el manual, se cambian los hex
aqui y nada mas.
"""

COLORES = {
    "naranja":  {"hex": "#F26B1D", "letra": "#ffffff"},
    "amarillo": {"hex": "#F2C200", "letra": "#000000"},
    "verde":    {"hex": "#22A05B", "letra": "#ffffff"},
    "turquesa": {"hex": "#12A5B4", "letra": "#000000"},
    "azul":     {"hex": "#2F7FE0", "letra": "#ffffff"},
    "morado":   {"hex": "#7B3FB8", "letra": "#ffffff"},
    "magenta":  {"hex": "#D4267E", "letra": "#ffffff"},
    "rojo":     {"hex": "#D93025", "letra": "#ffffff"},
}


def color(clave: str | None) -> dict | None:
    """Lo que se sabe de un color, por su clave. Nulo si no hay o si la
    clave ya no esta en la paleta: un dato viejo no truena, se calla."""
    if not clave or clave not in COLORES:
        return None
    return {"clave": clave, **COLORES[clave]}


def paleta() -> list[dict]:
    """Toda la paleta, en el orden en que se ofrece."""
    return [{"clave": clave, **datos} for clave, datos in COLORES.items()]
'''

# ================================================================ modelo
cambiar("models", '''    senal_nota: Mapped[str | None] = mapped_column(String(200), nullable=True)
''', '''    senal_nota: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # La clave del color de la paleta (`senal.py`), no el hex: el nombre
    # sale en la hoja del principal en su idioma, y el hex puede cambiar
    # el dia que llegue el manual de marca sin tocar ningun servicio.
    senal_color: Mapped[str | None] = mapped_column(String(12), nullable=True)
''')

NUEVOS[B / "migrations/versions/f3a8c1d2e5b7_senal_color.py"] = '''"""La senal de color.

La senal con la que el principal reconoce al equipo podia ser una
palabra o una imagen. Ahora tambien un color: una pantalla de un solo
color en el telefono, que se ve desde lejos. Se guarda la clave de la
paleta (`app/senal.py`), no el hex.

Revision ID: f3a8c1d2e5b7
Revises: e6b95c72d1a4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a8c1d2e5b7"
down_revision: Union[str, None] = "e6b95c72d1a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("servicio",
                  sa.Column("senal_color", sa.String(length=12), nullable=True))


def downgrade() -> None:
    op.drop_column("servicio", "senal_color")
'''

# ================================================================ schema
cambiar("schemas", '''class SenalIn(Base):
    """La senal puede ser una palabra o una imagen; tambien las dos."""
    texto: str | None = None
    imagen: str | None = None      # data URI o URL
    nota: str | None = None
''', '''class SenalIn(Base):
    """La senal: un color de la paleta (con palabra encima o sin ella),
    una palabra sola, o una imagen."""
    texto: str | None = None
    imagen: str | None = None      # data URI o URL
    nota: str | None = None
    color: str | None = None       # clave de la paleta (app/senal.py)
''')

# ================================================================ endpoints
cambiar("rts", '''from app import auditoria, auth, imagenes
''', '''from app import auditoria, auth, imagenes
from app import senal as senal_motor
''')

cambiar("rts", '''    """Una palabra, una imagen o ambas. Se imprime en una hoja aparte para
    que el equipo la muestre al salir el ejecutivo del filtro o en el lobby."""
    servicio = _servicio(db, servicio_id)
    if not datos.texto and not datos.imagen:
        raise HTTPException(400, "Indica al menos una palabra o una imagen")

    servicio.senal_texto = datos.texto
    if datos.imagen:
        servicio.senal_imagen = datos.imagen
    servicio.senal_nota = datos.nota

    auditoria.registrar(db, usuario, servicio, "definir senal",
                        datos.texto or "imagen")
    db.commit()
    return {"resultado": "senal guardada", "texto": servicio.senal_texto,
            "tiene_imagen": bool(servicio.senal_imagen),
''', '''    """Un color de la paleta --con palabra encima o sin ella--, una
    palabra sola, o una imagen. Sale en el task sheet, para que el
    principal sepa que buscar, y en el telefono del equipo, que la
    levanta al salir el ejecutivo del filtro o en el lobby.

    La imagen que ya estaba se conserva si no viene otra: asi, despues
    de subirla, se puede mandar solo la nota.
    """
    servicio = _servicio(db, servicio_id)
    if not (datos.texto or datos.imagen or datos.color
            or servicio.senal_imagen):
        raise HTTPException(400, "Indica un color, una palabra o una imagen")
    if datos.color and datos.color not in senal_motor.COLORES:
        raise HTTPException(400, {
            "mensaje": "Ese color no esta en la paleta",
            "colores": list(senal_motor.COLORES)})

    servicio.senal_texto = datos.texto
    servicio.senal_color = datos.color
    if datos.imagen:
        servicio.senal_imagen = datos.imagen
    servicio.senal_nota = datos.nota

    auditoria.registrar(db, usuario, servicio, "definir senal",
                        " ".join(x for x in (datos.color, datos.texto) if x)
                        or "imagen")
    db.commit()
    return {"resultado": "senal guardada", "texto": servicio.senal_texto,
            "color": servicio.senal_color,
            "tiene_imagen": bool(servicio.senal_imagen),
''')

cambiar("rts", '''    servicio.senal_texto = servicio.senal_imagen = servicio.senal_nota = None
    auditoria.registrar(db, usuario, servicio, "quitar senal", None)
''', '''    servicio.senal_texto = servicio.senal_imagen = servicio.senal_nota = None
    servicio.senal_color = None
    auditoria.registrar(db, usuario, servicio, "quitar senal", None)
''')

# ================================================================ la vista previa
cambiar("ts", '''from app import correo_html
from app import models as m
''', '''from app import correo_html
from app import models as m
from app import senal as senal_motor
''')

cambiar("ts", '''        "senal": ({"texto": servicio.senal_texto,
                   "imagen": servicio.senal_imagen,
                   "nota": servicio.senal_nota}
                  if (servicio.senal_texto or servicio.senal_imagen) else None),
''', '''        "senal": ({"texto": servicio.senal_texto,
                   "imagen": servicio.senal_imagen,
                   "nota": servicio.senal_nota,
                   "color": senal_motor.color(servicio.senal_color)}
                  if (servicio.senal_texto or servicio.senal_imagen
                      or servicio.senal_color) else None),
        # La paleta viaja con la vista para que la consola la dibuje sin
        # otra consulta y sin una copia propia de los colores.
        "senal_colores": senal_motor.paleta(),
''')

# ================================================================ la hoja
cambiar("html", '''    imagen = (f'<img class="senal-imagen" src="{senal["imagen"]}" alt="">'
              if senal.get("imagen") else "")
    texto = (f'<div class="senal-texto">{_esc(senal["texto"])}</div>'
             if senal.get("texto") else "")
    nota = (f'<div class="senal-nota">{_esc(senal["nota"])}</div>'
            if senal.get("nota") else "")
''', '''    color = senal.get("color")
    if color:
        # El color llena un bloque con la palabra encima, si la hay, y
        # debajo la frase que el principal va a leer: "su equipo lo
        # espera con la pantalla del telefono en naranja".
        nombre = t.get(f"color_{color['clave']}", color["clave"])
        palabra = _esc(senal["texto"]) if senal.get("texto") else ""
        frase = t["sign_color"].replace("{color}", nombre)
        if palabra:
            frase += t["sign_color_word"].replace("{word}", palabra)
        imagen = (f'<div class="senal-color" style="background:{color["hex"]};'
                  f'color:{color["letra"]}">{palabra}</div>')
        texto = f'<div class="senal-frase">{frase}.</div>'
    else:
        imagen = (f'<img class="senal-imagen" src="{senal["imagen"]}" alt="">'
                  if senal.get("imagen") else "")
        texto = (f'<div class="senal-texto">{_esc(senal["texto"])}</div>'
                 if senal.get("texto") else "")
    nota = (f'<div class="senal-nota">{_esc(senal["nota"])}</div>'
            if senal.get("nota") else "")
''')

cambiar("html", '''  .senal-nota {{ color: #5b646d; font-size: 13px; margin-bottom: 16px; }}
''', '''  .senal-color {{ height: 300px; border-radius: 16px; display: grid;
                 place-items: center; font-size: 64px; font-weight: 800;
                 letter-spacing: -1px; word-break: break-word; padding: 0 20px;
                 -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .senal-frase {{ font-size: 15px; margin-top: 14px; color: var(--centauro); }}
  .senal-nota {{ color: #5b646d; font-size: 13px; margin-bottom: 16px; }}
''')

# ================================================================ textos de la hoja
cambiar("textos", '''        "sign_look": "Please look for it on arrival.",
''', '''        "sign_look": "Please look for it on arrival.",
        "sign_color": "Your team will be waiting with the phone screen in {color}",
        "sign_color_word": " and the word {word}",
        "color_naranja": "orange", "color_amarillo": "yellow",
        "color_verde": "green", "color_turquesa": "turquoise",
        "color_azul": "blue", "color_morado": "purple",
        "color_magenta": "magenta", "color_rojo": "red",
''')
cambiar("textos", '''        "sign_look": "Búsquela al salir.",
''', '''        "sign_look": "Búsquela al salir.",
        "sign_color": "Su equipo lo espera con la pantalla del teléfono en {color}",
        "sign_color_word": " y la palabra {word}",
        "color_naranja": "naranja", "color_amarillo": "amarillo",
        "color_verde": "verde", "color_turquesa": "turquesa",
        "color_azul": "azul", "color_morado": "morado",
        "color_magenta": "magenta", "color_rojo": "rojo",
''')
cambiar("textos", '''        "sign_look": "Procure por ele na chegada.",
''', '''        "sign_look": "Procure por ele na chegada.",
        "sign_color": "Sua equipe o espera com a tela do telefone em {color}",
        "sign_color_word": " e a palavra {word}",
        "color_naranja": "laranja", "color_amarillo": "amarelo",
        "color_verde": "verde", "color_turquesa": "turquesa",
        "color_azul": "azul", "color_morado": "roxo",
        "color_magenta": "magenta", "color_rojo": "vermelho",
''')

# ================================================================ la ficha del dia
cambiar("campo", '''from app import revision as revision_unidad
''', '''from app import revision as revision_unidad
from app import senal as senal_motor
''')
cambiar("campo", '''        "senal": ({"texto": servicio.senal_texto,
                   "nota": servicio.senal_nota,
                   "imagen": bool(servicio.senal_imagen)}
                  if (servicio.senal_texto or servicio.senal_imagen)
                  else None),
''', '''        "senal": ({"texto": servicio.senal_texto,
                   "nota": servicio.senal_nota,
                   "imagen": bool(servicio.senal_imagen),
                   # El color viene resuelto --hex y letra-- para que el
                   # telefono lo pinte sin conocer la paleta.
                   "color": senal_motor.color(servicio.senal_color)}
                  if (servicio.senal_texto or servicio.senal_imagen
                      or servicio.senal_color)
                  else None),
''')

# ================================================================ la app
cambiar("app", '''function senalDelDia(f) {
  if (!f.senal) return null;
  return h("div", { clase: "dato" },
    h("span", { clase: "clave" }, t("cmp_senal")),
    h("button", { clase: "claro chico senal-boton",
                  onclick: (e) => { e.preventDefault(); abrirSenal(f); } },
      h("span", { clase: "senal-icono", html: SENAL_SVG }),
      t("cmp_senal_ver")),
''', '''function senalDelDia(f) {
  if (!f.senal) return null;
  /* Con color, el boton trae el punto del color y su nombre: se sabe
     que buscar antes de abrirla. */
  const color = f.senal.color;
  const detalle = [color ? t(`color_${color.clave}`) : null,
                   f.senal.texto || null].filter(Boolean);
  return h("div", { clase: "dato" },
    h("span", { clase: "clave" }, t("cmp_senal")),
    h("button", { clase: "claro chico senal-boton",
                  onclick: (e) => { e.preventDefault(); abrirSenal(f); } },
      color ? h("span", { clase: "senal-punto", style: `background:${color.hex}` })
            : h("span", { clase: "senal-icono", html: SENAL_SVG }),
      [t("cmp_senal_ver"), ...detalle].join(" · ")),
''')

cambiar("app", '''  const abierta = { nodo: pantalla, url: null, candado: null, alGirar: null };
  senalAbierta = abierta;
''', '''  const abierta = { nodo: pantalla, url: null, candado: null, alGirar: null };
  senalAbierta = abierta;

  /* El color llena la pantalla; la letra encima viene decidida con el
     color, para que se lea sobre amarillo igual que sobre morado. */
  if (f.senal.color) {
    pantalla.style.background = f.senal.color.hex;
    pantalla.style.color = f.senal.color.letra;
  }
''')

cambiar("appcss", '''.senal-cerrar {
  position: absolute; right: 10px; top: max(10px, env(safe-area-inset-top));
  width: 44px; min-height: 44px; padding: 0; border-radius: 999px;
  background: rgba(0, 0, 0, .08); color: #000; font-size: 20px;
}
''', '''.senal-cerrar {
  position: absolute; right: 10px; top: max(10px, env(safe-area-inset-top));
  width: 44px; min-height: 44px; padding: 0; border-radius: 999px;
  background: rgba(127, 127, 127, .22); color: inherit; font-size: 20px;
}
.senal-punto { display: inline-block; width: 14px; height: 14px; border-radius: 50%;
               flex: 0 0 auto; }
''')

# ================================================================ idioma
cambiar("idioma", '''    est_proxima_a_iniciar: "Próxima a iniciar",
''', '''    est_proxima_a_iniciar: "Próxima a iniciar",
    color_naranja: "Naranja",
    color_amarillo: "Amarillo",
    color_verde: "Verde",
    color_turquesa: "Turquesa",
    color_azul: "Azul",
    color_morado: "Morado",
    color_magenta: "Magenta",
    color_rojo: "Rojo",
''')
cambiar("idioma", '''    est_proxima_a_iniciar: "Starting soon",
''', '''    est_proxima_a_iniciar: "Starting soon",
    color_naranja: "Orange",
    color_amarillo: "Yellow",
    color_verde: "Green",
    color_turquesa: "Turquoise",
    color_azul: "Blue",
    color_morado: "Purple",
    color_magenta: "Magenta",
    color_rojo: "Red",
''')
cambiar("idioma", '''    est_proxima_a_iniciar: "Prestes a começar",
''', '''    est_proxima_a_iniciar: "Prestes a começar",
    color_naranja: "Laranja",
    color_amarillo: "Amarelo",
    color_verde: "Verde",
    color_turquesa: "Turquesa",
    color_azul: "Azul",
    color_morado: "Roxo",
    color_magenta: "Magenta",
    color_rojo: "Vermelho",
''')

cambiar("idioma", '''    srv_senal_pie: "Se imprime en una hoja aparte para que el equipo la muestre en el filtro o en el lobby. Es una palabra o una imagen, no las dos.",
    srv_texto: "Texto",
    srv_imagen: "Imagen",
''', '''    srv_senal_pie: "Lo que el equipo levanta en el teléfono a la salida del filtro o en el lobby. Sale en el task sheet para que el principal sepa qué buscar.",
    srv_texto: "Palabra",
    srv_imagen: "Imagen",
    srv_color_pie: "Una pantalla de un solo color. Se ve desde lejos y de un vistazo.",
    srv_texto_pie: "Un nombre o una clave en letras grandes, sobre blanco.",
    srv_imagen_pie: "Un letrero del cliente, subido como imagen.",
    srv_senal_recomendada: "Recomendada",
    srv_elige_color: "Elige el color",
    srv_palabra_encima: "Palabra encima (opcional)",
    srv_nota_senal: "Nota para el equipo",
    srv_senal_hoja: "En la hoja del principal saldrá:",
    srv_senal_frase: "Su equipo lo espera con la pantalla del teléfono en {color}",
    srv_senal_frase_palabra: " y la palabra {palabra}",
''')
cambiar("idioma", '''    srv_senal_pie: "It prints on a separate sheet so the team can hold it up at the gate or in the lobby. It is a word or an image, not both.",
    srv_texto: "Text",
    srv_imagen: "Image",
''', '''    srv_senal_pie: "What the team holds up on the phone at the gate or in the lobby. It goes on the task sheet so the principal knows what to look for.",
    srv_texto: "Word",
    srv_imagen: "Image",
    srv_color_pie: "A single-color screen. Seen from afar, at a glance.",
    srv_texto_pie: "A name or a code word in big letters, on white.",
    srv_imagen_pie: "A sign from the client, uploaded as an image.",
    srv_senal_recomendada: "Recommended",
    srv_elige_color: "Pick the color",
    srv_palabra_encima: "Word on top (optional)",
    srv_nota_senal: "Note for the team",
    srv_senal_hoja: "The principal's sheet will say:",
    srv_senal_frase: "Your team will be waiting with the phone screen in {color}",
    srv_senal_frase_palabra: " and the word {palabra}",
''')
cambiar("idioma", '''    srv_senal_pie: "Imprime-se numa folha à parte para que a equipe a mostre no portão ou no lobby. É uma palavra ou uma imagem, não as duas.",
    srv_texto: "Texto",
    srv_imagen: "Imagem",
''', '''    srv_senal_pie: "O que a equipe levanta no telefone na saída do portão ou no lobby. Sai na task sheet para que o principal saiba o que procurar.",
    srv_texto: "Palavra",
    srv_imagen: "Imagem",
    srv_color_pie: "Uma tela de uma só cor. Vê-se de longe e de relance.",
    srv_texto_pie: "Um nome ou uma senha em letras grandes, sobre branco.",
    srv_imagen_pie: "Uma placa do cliente, enviada como imagem.",
    srv_senal_recomendada: "Recomendada",
    srv_elige_color: "Escolha a cor",
    srv_palabra_encima: "Palavra por cima (opcional)",
    srv_nota_senal: "Nota para a equipe",
    srv_senal_hoja: "Na folha do principal sairá:",
    srv_senal_frase: "Sua equipe o espera com a tela do telefone em {color}",
    srv_senal_frase_palabra: " e a palavra {palabra}",
''')

# ================================================================ la consola
BLOQUE = '''function bloqueSenal(servicio, vista) {
  const actual = vista.senal || {};
  const colores = vista.senal_colores || [];
  const zona = h("div", { style: "margin-top:16px" });

  /* Tres formas, y una recomendada. Un servicio nuevo abre en Color; uno
     que ya tenia palabra o imagen abre en la suya. */
  const comoColor = h("input", { type: "radio", name: "senal_como" });
  const comoTexto = h("input", { type: "radio", name: "senal_como" });
  const comoImagen = h("input", { type: "radio", name: "senal_como" });
  if (actual.imagen) comoImagen.checked = true;
  else if (actual.texto && !actual.color) comoTexto.checked = true;
  else comoColor.checked = true;

  let elegido = (actual.color && actual.color.clave)
    || (colores.length ? colores[0].clave : null);
  const colorElegido = () => colores.find(c => c.clave === elegido) || null;
  const nombreColor = () => {
    const c = colorElegido();
    return c ? t(`color_${c.clave}`) : "";
  };

  /* La senal se imprime tal cual se escribe: si el consultor la quiere
     en mayusculas, asi se queda. */
  const texto = entrada("texto", {
    placeholder: "MR. BROOKS", "data-crudo": "",
    value: actual.texto || "" });
  const nota = entrada("nota", { value: actual.nota || "", maxlength: 200 });

  const archivo = h("input", { type: "file", accept:
    "image/png,image/jpeg,image/webp,image/svg+xml" });
  const previa = h("img", { clase: "senal-previa",
                            src: actual.imagen || "",
                            hidden: !actual.imagen });
  archivo.addEventListener("change", () => {
    const f = archivo.files && archivo.files[0];
    if (!f) return;
    previa.src = URL.createObjectURL(f);
    previa.hidden = false;
  });

  /* El telefono como lo vera el principal, en vivo mientras se elige,
     y la frase que va a leer en su hoja. */
  const telefono = h("div", { clase: "senal-telefono" });
  const frase = h("div", { clase: "chico gris", style: "margin-top:8px" });
  const pintarPrevia = () => {
    const c = colorElegido();
    telefono.style.background = c ? c.hex : "";
    telefono.style.color = c ? c.letra : "";
    const palabra = h("b", {}, texto.value.trim());
    telefono.replaceChildren(palabra);
    const dice = t("srv_senal_frase").replace("{color}", nombreColor().toLowerCase())
      + (texto.value.trim()
         ? t("srv_senal_frase_palabra").replace("{palabra}", texto.value.trim())
         : "") + ".";
    const renglon = h("b", {}, dice);
    frase.replaceChildren(`${t("srv_senal_hoja")} `, renglon);
  };
  const circulos = h("div", { clase: "senal-colores" });
  const pintarCirculos = () => {
    const botones = colores.map(c => h("button", {
      type: "button",
      clase: "senal-color" + (c.clave === elegido ? " sel" : ""),
      style: `background:${c.hex};color:${c.letra}`,
      title: t(`color_${c.clave}`), "aria-label": t(`color_${c.clave}`),
      onclick: (e) => {
        e.preventDefault();
        elegido = c.clave;
        pintarCirculos();
        pintarPrevia();
      } }, c.clave === elegido ? "✓" : ""));
    circulos.replaceChildren(...botones);
  };
  pintarCirculos();
  texto.addEventListener("input", pintarPrevia);

  const etiquetaTexto = h("label", {}, t("srv_palabra_senal"));
  const cajaColor = h("div", { clase: "senal-armado" },
    h("div", {},
      campo(t("srv_elige_color"), circulos),
      h("div", { clase: "chico gris" }, nombreColor())),
    telefono);
  const cajaTexto = h("div", { clase: "campo" }, etiquetaTexto, texto);
  const cajaImagen = h("div", {},
    campo(t("srv_archivo"), archivo),
    h("div", { clase: "chico gris" },
      t("srv_senal_formatos")),
    previa);

  const acomodar = () => {
    cajaColor.hidden = !comoColor.checked;
    frase.hidden = !comoColor.checked;
    cajaTexto.hidden = !(comoColor.checked || comoTexto.checked);
    etiquetaTexto.textContent = comoColor.checked
      ? t("srv_palabra_encima") : t("srv_palabra_senal");
    cajaImagen.hidden = !comoImagen.checked;
    pintarPrevia();
  };
  for (const r of [comoColor, comoTexto, comoImagen])
    r.addEventListener("change", acomodar);
  acomodar();

  const guardar = h("button", { clase: "claro chico", onclick: async (e) => {
    e.preventDefault();
    const f = archivo.files && archivo.files[0];
    if (comoColor.checked && !elegido)
      return mensaje(t("srv_elige_color"), "alerta");
    if (comoTexto.checked && !texto.value.trim())
      return mensaje(t("srv_escribe_senal"), "alerta");
    if (comoImagen.checked && !f && !actual.imagen)
      return mensaje(t("srv_elige_senal"), "alerta");

    e.target.disabled = true;
    try {
      // Se limpia primero: una senal a la vez.
      await api.borrar(`/servicios/${servicio.id}/senal`);
      const cuerpo = { nota: nota.value.trim() || null };
      if (comoColor.checked) {
        await api.put(`/servicios/${servicio.id}/senal`,
                      { ...cuerpo, color: elegido,
                        texto: texto.value.trim() || null });
      } else if (comoTexto.checked) {
        await api.put(`/servicios/${servicio.id}/senal`,
                      { ...cuerpo, texto: texto.value.trim() });
      } else if (f) {
        await api.subir(`/servicios/${servicio.id}/senal/imagen`, f);
        await api.put(`/servicios/${servicio.id}/senal`, cuerpo);
      } else {
        await api.put(`/servicios/${servicio.id}/senal`,
                      { ...cuerpo, imagen: actual.imagen });
      }
      mensaje(t("srv_senal_guardada"));
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  } }, t("srv_guardar_senal"));

  const quitar = h("button", { clase: "claro chico", onclick: async (e) => {
    e.preventDefault();
    e.target.disabled = true;
    try {
      await api.borrar(`/servicios/${servicio.id}/senal`);
      texto.value = "";
      nota.value = "";
      previa.hidden = true;
      pintarPrevia();
      mensaje(t("srv_senal_quitada"));
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  } }, t("srv_quitar_senal"));

  const opcion = (radio, titulo, pie, recomendada) =>
    h("label", { clase: "senal-opcion" + (recomendada ? " recomendada" : "") },
      recomendada ? h("span", { clase: "senal-etiqueta" }, t("srv_senal_recomendada")) : null,
      h("div", {}, radio, " ", h("b", {}, titulo)),
      h("div", { clase: "chico gris" }, pie));

  zona.append(
    conAyuda("h4", t("srv_senal"), "ay_srv_senal", { clase: "grupo" }),
    h("div", { clase: "chico gris", style: "margin-bottom:8px" },
      t("srv_senal_pie")),
    h("div", { clase: "senal-opciones" },
      opcion(comoColor, t("srv_color"), t("srv_color_pie"), true),
      opcion(comoTexto, t("srv_texto"), t("srv_texto_pie"), false),
      opcion(comoImagen, t("srv_imagen"), t("srv_imagen_pie"), false)),
    cajaColor, cajaTexto, cajaImagen,
    campo(t("srv_nota_senal"), nota),
    frase,
    h("div", { clase: "acciones", style: "margin-top:10px" },
      guardar,
      (actual.texto || actual.imagen || actual.color) ? quitar : ""));
  return zona;
}
'''
cambiar_tramo("servicio", "function bloqueSenal(servicio, vista) {",
              "/* ------------------------------------------------------------ a bordo */",
              BLOQUE, marca='const comoColor = h("input", { type: "radio", name: "senal_como" });')

cambiar("servicio", '''/* Lo que el equipo levanta cuando el ejecutivo sale del filtro. Puede ser
   una palabra (su apellido) o una imagen (el logo del cliente, que se
   reconoce de mas lejos). Se imprime a pagina completa: es una o la otra,
   nunca las dos, asi que al guardar una se quita la que estaba. */
''', '''/* Lo que el equipo levanta cuando el ejecutivo sale del filtro. Tres
   formas, y una recomendada: un COLOR --una pantalla de un solo color se
   distingue a veinte metros sin leer nada--, con una palabra encima si
   se quiere; una PALABRA sola en letras grandes; o una IMAGEN del
   cliente. Pedido de Salvador, 22 sep. Es una forma a la vez: al
   guardar una se quita la que estaba. */
''')

cambiar("css", '''/* "Aborda" y su selector en un solo renglon, debajo de la persona. */
''', '''/* La senal: las tres formas como tarjetas, la recomendada marcada; los
   colores en circulos grandes, el elegido con su anillo; y el telefono
   como lo vera el principal. */
.senal-opciones { display: flex; gap: 10px; margin: 8px 0 14px; }
.senal-opcion { flex: 1; border: 1.5px solid var(--linea); border-radius: 10px;
                padding: 10px 12px; position: relative; cursor: pointer; }
.senal-opcion:has(input:checked) { border-color: var(--centauro);
                                   box-shadow: 0 0 0 2px rgba(27, 21, 70, .12); }
.senal-opcion input { margin: 0 2px 0 0; vertical-align: -1px; }
.senal-etiqueta { position: absolute; top: -9px; right: 10px; background: var(--centauro);
                  color: #fff; font-size: 10px; font-weight: 700; letter-spacing: .6px;
                  padding: 2px 8px; border-radius: 999px; text-transform: uppercase; }
.senal-armado { display: flex; gap: 22px; align-items: flex-start; }
.senal-armado > div:first-child { flex: 1; min-width: 0; }
.senal-colores { display: flex; flex-wrap: wrap; gap: 10px; }
.senal-color { width: 44px; height: 44px; border-radius: 50%; border: 0; padding: 0;
               cursor: pointer; font-weight: 800; font-size: 18px; }
.senal-color.sel { box-shadow: 0 0 0 3px #fff, 0 0 0 5px var(--centauro); }
.senal-telefono { width: 118px; height: 236px; border-radius: 18px; border: 6px solid #111;
                  display: grid; place-items: center; text-align: center; padding: 8px;
                  font-weight: 800; font-size: 20px; line-height: 1.05; word-break: break-word;
                  background: var(--suave); flex: 0 0 auto; }

/* "Aborda" y su selector en un solo renglon, debajo de la persona. */
''')

# ================================================================ la prueba
NUEVOS[B / "tests/test_senal_color.py"] = '''"""La senal de color: la paleta, el servicio, la hoja y el telefono.

Pedido de Salvador, 22 sep. La senal con la que el principal reconoce
al equipo puede ser un color --una pantalla de un solo color en el
telefono--, con una palabra encima o sin ella.
"""
from test_campo import _servicio_de_juan

NARANJA = {"clave": "naranja", "hex": "#F26B1D", "letra": "#ffffff"}


def _senal(cliente, sesion, servicio, **datos):
    return cliente.put(f"/servicios/{servicio['id']}/senal", json=datos,
                       headers=sesion("consultor"))


def _vista(cliente, sesion, servicio):
    r = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def _ficha(cliente, sesion, servicio):
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    return next(f for f in dia["hoy"] if f["servicio_id"] == servicio["id"])


def test_la_paleta_viaja_con_la_vista_previa(cliente, sesion, datos):
    """La consola dibuja los circulos con lo que le manda el servidor:
    una sola copia de los colores."""
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    paleta = _vista(cliente, sesion, servicio)["senal_colores"]
    assert len(paleta) == 8
    assert paleta[0] == NARANJA
    for c in paleta:
        assert c["hex"].startswith("#") and c["letra"] in ("#ffffff", "#000000")


def test_el_color_se_guarda_con_su_hex_y_su_letra(cliente, sesion, datos):
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = _senal(cliente, sesion, servicio, color="naranja", texto="CARTER",
               nota="A la salida del filtro")
    assert r.status_code == 200, r.text
    assert r.json()["color"] == "naranja"

    senal = _vista(cliente, sesion, servicio)["senal"]
    assert senal["color"] == NARANJA
    assert senal["texto"] == "CARTER" and senal["nota"] == "A la salida del filtro"
    assert senal["imagen"] is None

    # Y el telefono lo recibe resuelto: el hex y la letra, sin paleta.
    f = _ficha(cliente, sesion, servicio)
    assert f["senal"]["color"] == NARANJA
    assert f["senal"]["texto"] == "CARTER"
    assert f["senal"]["imagen"] is False


def test_el_color_puede_ir_solo(cliente, sesion, datos):
    """Sin palabra y sin imagen: el color es senal suficiente."""
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    assert _senal(cliente, sesion, servicio, color="verde").status_code == 200
    senal = _vista(cliente, sesion, servicio)["senal"]
    assert senal["color"]["clave"] == "verde"
    assert senal["texto"] is None and senal["imagen"] is None
    assert _ficha(cliente, sesion, servicio)["senal"]["color"]["clave"] == "verde"


def test_un_color_fuera_de_la_paleta_no_entra(cliente, sesion, datos):
    """Solo los de la paleta tienen nombre en los tres idiomas, y el
    nombre es lo que lee el principal."""
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = _senal(cliente, sesion, servicio, color="fucsia")
    assert r.status_code == 400, r.text
    assert "naranja" in r.json()["detail"]["colores"]
    assert _vista(cliente, sesion, servicio)["senal"] is None


def test_la_hoja_del_principal_dice_el_color_en_su_idioma(cliente, sesion,
                                                           datos):
    """Es lo que el principal lee antes de llegar: que buscar."""
    h = sesion("consultor")
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    assert _senal(cliente, sesion, servicio, color="naranja",
                  texto="CARTER").status_code == 200
    assert cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                        json={"motivo": "prueba"}, headers=h).status_code in (200, 201)
    assert cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion",
                        headers=h).status_code == 200, "no se libero el TS"

    hojas = {}
    for idioma in ("es", "en", "pt"):
        r = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja?idioma={idioma}",
                        headers=h)
        assert r.status_code == 200, r.text
        hojas[idioma] = r.text
        assert "#F26B1D" in r.text, f"la hoja en {idioma} no pinta el color"
        assert "CARTER" in r.text
    assert "en naranja" in hojas["es"] and "y la palabra CARTER" in hojas["es"]
    assert "in orange" in hojas["en"] and "and the word CARTER" in hojas["en"]
    assert "em laranja" in hojas["pt"] and "e a palavra CARTER" in hojas["pt"]


def test_quitar_la_senal_quita_el_color(cliente, sesion, datos):
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    assert _senal(cliente, sesion, servicio, color="azul",
                  texto="CARTER").status_code == 200
    r = cliente.delete(f"/servicios/{servicio['id']}/senal",
                       headers=sesion("consultor"))
    assert r.status_code == 204, r.text
    assert _vista(cliente, sesion, servicio)["senal"] is None
    assert _ficha(cliente, sesion, servicio)["senal"] is None


def test_la_nota_se_puede_mandar_sola_si_ya_hay_imagen(cliente, sesion, datos):
    """Es lo que hace la consola despues de subir la imagen: manda la
    nota en un segundo paso, y la imagen se tiene que quedar."""
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    pixel = "data:image/png;base64,iVBORw0KGgo="
    assert _senal(cliente, sesion, servicio, imagen=pixel).status_code == 200
    r = _senal(cliente, sesion, servicio, nota="En el lobby")
    assert r.status_code == 200, r.text
    senal = _vista(cliente, sesion, servicio)["senal"]
    assert senal["imagen"] == pixel and senal["nota"] == "En el lobby"
    assert senal["color"] is None
'''

# ================================================================ escrituras
for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(textos[clave])
        print("escrito ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for ruta, contenido in NUEVOS.items():
    if ruta.exists() and io.open(ruta, encoding="utf-8").read() == contenido:
        print("sin cambio", ruta.relative_to(RAIZ))
    else:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        print("escrito ", ruta.relative_to(RAIZ))
for s in saltados:
    print("saltado:", s)

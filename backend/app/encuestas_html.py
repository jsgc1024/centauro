"""La encuesta como la ve el cliente: el correo y la pagina.

Misma identidad del task sheet, porque es el mismo documento en la
cabeza del ejecutivo: azul #1B1546, Inter, el logo incrustado y el
orden de arriba hacia abajo sin adornos.
"""
import html

from app.encuestas import PREGUNTAS, _textos
from app.marca import logo_incrustado

CENTAURO = "#1B1546"
SUAVE = "#f0f3f5"


def _esc(valor) -> str:
    return html.escape(str(valor)) if valor not in (None, "") else ""


LINEA = "AI/EP"


def _marca(alto: int) -> str:
    """El logo con la linea de operacion debajo: este correo es de
    Proteccion Ejecutiva, igual que el folio del servicio."""
    if logo_incrustado():
        arriba = (f'<img src="{logo_incrustado()}" alt="Centauro" '
                  f'style="height:{alto}px;display:block">')
    else:
        arriba = (f'<span style="font-weight:700;letter-spacing:3px;'
                  f'color:{CENTAURO};font-size:{max(12, alto // 3)}px">'
                  f'CENTAURO</span>')
    return (f'{arriba}<span style="display:inline-block;margin-top:8px;'
            f'font-weight:700;font-size:11px;letter-spacing:.5px;color:#fff;'
            f'background:{CENTAURO};padding:2px 8px;border-radius:4px">'
            f'{LINEA}</span>')


# ---------------------------------------------------------------- correo

def correo(encuesta, enlace: str) -> str:
    """El correo que recibe el ejecutivo o el solicitante.

    Una sola llamada a la accion. Nada de parrafos: quien lo abre en el
    telefono decide en dos segundos si contesta o no.
    """
    t = _textos(encuesta.idioma)
    tipo = t[encuesta.tipo.value]
    nombre = _esc(encuesta.destinatario_nombre or "")
    saludo = {"en": f"Hello{' ' + nombre if nombre else ''},",
              "es": f"Hola{' ' + nombre if nombre else ''},",
              "pt": f"Ola{' ' + nombre if nombre else ''},"}[
        encuesta.idioma if encuesta.idioma in ("en", "es", "pt") else "en"]
    boton = {"en": "Answer in one tap",
             "es": "Contestar en un toque",
             "pt": "Responder num toque"}[
        encuesta.idioma if encuesta.idioma in ("en", "es", "pt") else "en"]
    pie = {"en": "It takes less than a minute. Centauro, executive protection.",
           "es": "Toma menos de un minuto. Centauro, proteccion ejecutiva.",
           "pt": "Leva menos de um minuto. Centauro, protecao executiva."}[
        encuesta.idioma if encuesta.idioma in ("en", "es", "pt") else "en"]

    return f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:{SUAVE};
  font-family:Inter,-apple-system,'Segoe UI',system-ui,sans-serif;color:#1a1d21">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  style="max-width:520px;background:#fff;border:1px solid #dfe2e6;
         border-radius:8px;border-top:5px solid {CENTAURO};overflow:hidden">
  <tr><td style="padding:22px 26px 10px">{_marca(52)}</td></tr>
  <tr><td style="padding:0 26px 4px;font-size:12px;color:#78828c">
    {_esc(encuesta.servicio.folio)}</td></tr>
  <tr><td style="padding:8px 26px 0;font-size:15px">{saludo}</td></tr>
  <tr><td style="padding:14px 26px 0;font-size:19px;font-weight:650;
                 line-height:1.35;color:{CENTAURO}">
    {_esc(tipo['general'])}</td></tr>
  <tr><td style="padding:20px 26px 8px">
    <a href="{_esc(enlace)}" style="display:inline-block;background:{CENTAURO};
       color:#fff;text-decoration:none;padding:12px 22px;border-radius:6px;
       font-weight:650;font-size:14px">{boton}</a></td></tr>
  <tr><td style="padding:14px 26px 24px;font-size:11.5px;color:#78828c;
                 border-top:1px solid #eef0f2;margin-top:10px">{pie}</td></tr>
</table>
</td></tr></table>
</body></html>"""


# ---------------------------------------------------------------- pagina

def pagina(encuesta, formulario: dict) -> str:
    """La pagina que se abre desde el correo.

    La primera pregunta llena la pantalla; las de seguimiento aparecen
    solo cuando hacen falta. Nadie ve un formulario largo de entrada.
    """
    t = _textos(encuesta.idioma)
    enviar = {"en": "Send", "es": "Enviar", "pt": "Enviar"}.get(
        encuesta.idioma, "Send")
    datos = {
        "tipo": formulario["tipo"],
        "general": formulario["general"],
        "bien": formulario.get("si_califica_4_o_5"),
        "mal": formulario.get("si_califica_3_o_menos"),
        "siempre": formulario.get("siempre"),
        "abierta": formulario.get("abierta"),
        "gracias": t["gracias"],
        "enviar": enviar,
    }
    import json
    return f"""<!doctype html>
<html lang="{_esc(encuesta.idioma)}"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Centauro · {_esc(encuesta.servicio.folio)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;650;700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:24px 16px 60px; background:{SUAVE};
    font:15px/1.5 Inter,-apple-system,'Segoe UI',system-ui,sans-serif;
    color:#1a1d21; }}
  .hoja {{ max-width:560px; margin:0 auto; background:#fff;
    border:1px solid #dfe2e6; border-radius:8px;
    border-top:5px solid {CENTAURO}; overflow:hidden; }}
  header {{ padding:22px 26px 14px; border-bottom:1px solid #eef0f2; }}
  header img {{ height:54px; display:block; }}
  header .folio {{ font-size:11.5px; color:#78828c; margin-top:8px;
    text-transform:uppercase; letter-spacing:.7px; font-weight:650; }}
  .cuerpo {{ padding:26px; }}
  h1 {{ font-size:21px; line-height:1.35; margin:0 0 6px; color:{CENTAURO};
    font-weight:650; }}
  .escala {{ color:#78828c; font-size:12.5px; margin:0 0 20px; }}
  .notas {{ display:flex; gap:8px; }}
  .notas button {{ flex:1; aspect-ratio:1; border:1px solid #dfe2e6;
    background:#fff; border-radius:8px; font-size:20px; font-weight:650;
    color:{CENTAURO}; cursor:pointer; }}
  .notas button:hover {{ border-color:{CENTAURO}; }}
  .notas button[aria-pressed="true"] {{ background:{CENTAURO}; color:#fff;
    border-color:{CENTAURO}; }}
  .detalle {{ margin-top:26px; padding-top:22px; border-top:1px solid #eef0f2; }}
  .pregunta {{ margin-bottom:22px; }}
  .pregunta label {{ display:block; font-weight:600; margin-bottom:8px; }}
  textarea {{ width:100%; padding:10px 12px; border:1px solid #dfe2e6;
    border-radius:6px; font:inherit; }}
  textarea:focus, .notas button:focus {{ outline:2px solid {CENTAURO};
    outline-offset:-1px; }}
  .enviar {{ width:100%; background:{CENTAURO}; color:#fff; border:0;
    border-radius:6px; padding:13px; font:inherit; font-weight:650;
    cursor:pointer; margin-top:6px; }}
  .enviar:disabled {{ opacity:.45; cursor:not-allowed; }}
  .gracias {{ text-align:center; padding:46px 26px; }}
  .gracias .palomita {{ font-size:40px; color:{CENTAURO}; }}
  .error {{ background:#fdecea; border:1px solid #f5cdc8; color:#8f2b20;
    border-radius:6px; padding:11px 14px; font-size:13.5px; margin-top:14px; }}
  footer {{ padding:16px 26px; background:{SUAVE}; font-size:11px;
    color:#78828c; border-top:1px solid #eef0f2; }}
</style></head>
<body>
<div class="hoja">
  <header>{_marca(54)}<div class="folio">{_esc(encuesta.servicio.folio)}</div></header>
  <div id="contenido" class="cuerpo"></div>
  <footer>Centauro · Executive protection</footer>
</div>
<script>
const DATOS = {json.dumps(datos, ensure_ascii=False)};
const TOKEN = {json.dumps(encuesta.token)};
let nota = null;
const contenido = document.getElementById("contenido");

function pintar() {{
  contenido.innerHTML = "";
  const h1 = document.createElement("h1");
  h1.textContent = DATOS.general.pregunta;
  const escala = document.createElement("p");
  escala.className = "escala";
  escala.textContent = DATOS.general.escala;
  const notas = document.createElement("div");
  notas.className = "notas";
  for (let i = 1; i <= 5; i++) {{
    const b = document.createElement("button");
    b.type = "button"; b.textContent = i;
    b.setAttribute("aria-pressed", String(nota === i));
    b.onclick = () => {{ nota = i; pintar(); }};
    notas.append(b);
  }}
  contenido.append(h1, escala, notas);
  if (nota !== null) contenido.append(detalle());
}}

function bloque(clave, texto, escalaCorta) {{
  const div = document.createElement("div");
  div.className = "pregunta";
  const label = document.createElement("label");
  label.textContent = texto;
  div.append(label);
  if (escalaCorta) {{
    const fila = document.createElement("div");
    fila.className = "notas";
    for (let i = 1; i <= 5; i++) {{
      const b = document.createElement("button");
      b.type = "button"; b.textContent = i; b.dataset.clave = clave;
      b.setAttribute("aria-pressed", "false");
      b.onclick = () => {{
        fila.querySelectorAll("button").forEach(x =>
          x.setAttribute("aria-pressed", String(x === b)));
      }};
      fila.append(b);
    }}
    div.append(fila);
  }} else {{
    const t = document.createElement("textarea");
    t.rows = 3; t.dataset.clave = clave;
    div.append(t);
  }}
  return div;
}}

function detalle() {{
  const caja = document.createElement("div");
  caja.className = "detalle";
  const preguntas = DATOS.tipo === "ejecutivo"
    ? (nota > 3 ? DATOS.bien : DATOS.mal)
    : {{ ...DATOS.siempre, ...DATOS.abierta }};
  const escalas = DATOS.tipo === "ejecutivo"
    ? ["puntualidad", "trato", "vehiculo"]
    : Object.keys(DATOS.siempre || {{}});
  for (const [clave, texto] of Object.entries(preguntas || {{}})) {{
    caja.append(bloque(clave, texto, escalas.includes(clave)));
  }}
  const enviar = document.createElement("button");
  enviar.className = "enviar";
  enviar.textContent = DATOS.enviar;
  enviar.onclick = () => mandar(enviar, caja);
  caja.append(enviar);
  return caja;
}}

async function mandar(boton, caja) {{
  boton.disabled = true;
  const respuestas = {{}};
  caja.querySelectorAll("textarea").forEach(t => {{
    if (t.value.trim()) respuestas[t.dataset.clave] = t.value.trim();
  }});
  caja.querySelectorAll("button[aria-pressed='true']").forEach(b => {{
    if (b.dataset.clave) respuestas[b.dataset.clave] = Number(b.textContent);
  }});
  try {{
    const r = await fetch("/encuestas/publica/" + TOKEN, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ calificacion: nota, respuestas }}),
    }});
    const d = await r.json();
    if (!r.ok) throw new Error(
      (d.detail && (d.detail.mensaje || d.detail)) || "No se pudo enviar");
    contenido.className = "gracias";
    contenido.innerHTML = "";
    const p = document.createElement("div");
    p.className = "palomita"; p.textContent = "\\u2713";
    const t = document.createElement("p");
    t.textContent = DATOS.gracias;
    contenido.append(p, t);
  }} catch (e) {{
    boton.disabled = false;
    const error = document.createElement("div");
    error.className = "error";
    error.textContent = typeof e.message === "string"
      ? e.message : "No se pudo enviar";
    caja.append(error);
  }}
}}

pintar();
</script>
</body></html>"""


def pagina_cerrada(mensaje: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Centauro</title></head>
<body style="margin:0;padding:60px 20px;background:{SUAVE};text-align:center;
  font:15px/1.5 Inter,-apple-system,'Segoe UI',system-ui,sans-serif;color:#1a1d21">
<div style="max-width:420px;margin:0 auto;background:#fff;border:1px solid #dfe2e6;
  border-radius:8px;border-top:5px solid {CENTAURO};padding:34px 26px">
  <div style="margin-bottom:18px">{_marca(48)}</div>
  <p style="color:#5b646d;margin:0">{_esc(mensaje)}</p>
</div></body></html>"""

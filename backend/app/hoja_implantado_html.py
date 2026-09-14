"""Como se ve la hoja del implantado.

Mismo lenguaje que la del eventual —la banda navy, AI/EP arriba, el
folio, la confidencialidad al pie— porque las dos salen de Centauro y el
cliente tiene que reconocerlas. Lo que cambia es lo que va adentro: aqui
no hay dias ni agenda, hay un acuerdo y unas personas.
"""
from html import escape

from app.marca import logo_incrustado
from app.textos import diccionario, fecha_larga

# El prefijo de la linea, igual que en la hoja del eventual.
LINEA = "AI/EP"


def _esc(valor) -> str:
    return escape(str(valor)) if valor not in (None, "") else ""


def _bloque(titulo: str, cuerpo: str) -> str:
    if not cuerpo:
        return ""
    return f'<section class="bloque"><h3>{_esc(titulo)}</h3>{cuerpo}</section>'


def _parrafo(texto) -> str:
    """El texto capturado se imprime como se escribio, renglon por
    renglon: el protocolo casi siempre viene en lista."""
    if not texto:
        return ""
    renglones = [_esc(r) for r in str(texto).splitlines() if r.strip()]
    return "".join(f"<p>{r}</p>" for r in renglones)


def _dato(etiqueta: str, valor) -> str:
    if not valor:
        return ""
    return (f'<div class="dato"><span class="etiqueta">{_esc(etiqueta)}</span>'
            f'<div class="valor">{_esc(valor)}</div></div>')


def _capacitacion(cursos: list, t: dict) -> str:
    """Lo que sabe hacer, aparte de manejar.

    Solo sale si alguien la cargo: un renglon que dice "capacitacion: —"
    resta en vez de sumar. La vencida se marca, porque una certificacion
    vencida no es una certificacion.
    """
    if not cursos:
        return ""
    filas = []
    for c in cursos:
        vence = ""
        if c.get("vigencia_hasta"):
            marca = "" if c.get("vigente") else ' class="vencida"'
            vence = (f'<span{marca}>{t["valid_until"]} '
                     f'{_esc(fecha_larga(c["vigencia_hasta"], t))}</span>')
        filas.append(
            f'<li><b>{_esc(c["nombre"])}</b>'
            + (f' · {_esc(c["institucion"])}' if c.get("institucion") else "")
            + (f'<br>{vence}' if vence else "") + "</li>")
    return (f'<div class="cursos"><h5>{_esc(t["training"])}</h5>'
            f'<ul>{"".join(filas)}</ul></div>')


def _unidad(u: dict, t: dict) -> str:
    if not u:
        return ""
    detalle = " · ".join(filter(None, [
        u.get("marca_modelo"), u.get("categoria"), u.get("color"),
        str(u["anio"]) if u.get("anio") else None]))
    foto = (f'<img class="foto-unidad" src="{_esc(u["foto_url"])}" alt="">'
            if u.get("foto_url") else '<div class="foto-unidad sin"></div>')
    blindada = (f'<span class="sello-blindada">{_esc(t["armored"])}</span>'
                if u.get("blindada") else "")
    return (f'<div class="unidad">{foto}'
            f'<div><h5>{_esc(t["vehicle"])}</h5>'
            f'<b class="placa">{_esc(u["placa"])}</b> {blindada}'
            f'<div class="gris">{_esc(detalle)}</div></div></div>')


def _ficha(p: dict, t: dict) -> str:
    """Quien va a estar enfrente del ejecutivo todos los dias.

    Es el bloque que contesta la unica pregunta que de verdad hace el
    cliente de un implantado: quien es esta persona.
    """
    foto = (f'<img class="retrato" src="{_esc(p["foto_url"])}" alt="">'
            if p.get("foto_url") else '<div class="retrato sin"></div>')

    marcas = []
    if p.get("horas"):
        marcas.append(f'<span class="marca">{int(p["horas"]):,} '
                      f'{t["hours_at"]}</span>'.replace(",", " "))
    if p.get("calificacion"):
        marcas.append(f'<span class="marca fuerte">{p["calificacion"]} '
                      f'{t["rating"]}</span>')

    return (
        f'<article class="ficha">{foto}'
        f'<div class="cuerpo-ficha">'
        f'<h4>{_esc(p["nombre"])}</h4>'
        f'<div class="puesto">{_esc(p.get("puesto") or "")}</div>'
        + (f'<div class="tel">{_esc(p["telefono"])}</div>'
           if p.get("telefono") else "")
        + (f'<div class="marcas">{"".join(marcas)}</div>' if marcas else "")
        + _capacitacion(p.get("capacitacion") or [], t)
        + _unidad(p.get("unidad"), t)
        + "</div></article>")


def _hospitales(lista: list, t: dict) -> str:
    if not lista:
        return ""
    filas = "".join(
        f'<li><b>{_esc(x["nombre"])}</b>'
        + (f' · {_esc(x["nivel"])}' if x.get("nivel") else "")
        + (f'<br><span class="gris">{_esc(x["direccion"])}</span>'
           if x.get("direccion") else "")
        + (f'<br><span class="tel">{_esc(x["telefono"])}</span>'
           if x.get("telefono") else "")
        + (f' <span class="gris">· {x["distancia_km"]} km</span>'
           if x.get("distancia_km") is not None else "")
        + "</li>" for x in lista)
    return f"<ul class='hospitales'>{filas}</ul>"


def _escalacion(niveles: list, t: dict) -> str:
    if not niveles:
        return ""
    return "".join(
        f'<div class="nivel"><span class="num">{n["nivel"]}</span>'
        f'<div><b>{_esc(n["nombre"])}</b><br>'
        f'<span class="gris">{_esc(n["cargo"])}</span><br>'
        f'<span class="tel">{_esc(n.get("telefono"))}</span></div></div>'
        for n in niveles)


def render(contenido: dict, version: int = 1, actualizado: str | None = None,
           idioma: str | None = None) -> str:
    t = diccionario(idioma)
    es_cobertura = contenido.get("tipo") == "cobertura"

    logo = logo_incrustado()
    marca = (f'<img class="logo" src="{logo}" alt="Centauro">' if logo
             else '<span class="marca-texto">CENTAURO</span>')

    if es_cobertura:
        dias = ", ".join(fecha_larga(f, t) for f in contenido["fechas"])
        banda = (f'<div class="banda">{_esc(t["coverage_sheet"])}'
                 f'<span>{_esc(dias)}</span></div>')
        titulo_equipo = t["covering"]
    else:
        banda = ""
        titulo_equipo = t["permanent_team"]

    punto = contenido.get("punto") or {}
    coordinacion = contenido.get("coordinacion") or {}

    servicio = "".join([
        _dato(t["fixed_point"], punto.get("direccion")),
        _dato(t["days_of_service"], contenido.get("dias_semana")),
        _dato(t["report_time"], (contenido.get("hora") or "")[:5]),
        _dato(t["operating_area"], contenido.get("zona")),
        _dato(t["geofence"], f'{punto["metros"]} m' if punto.get("metros") else None),
    ])

    alcance = "".join([
        (f'<div class="mitad"><h5>{_esc(t["agreements"])}</h5>'
         f'{_parrafo(contenido.get("cubre"))}</div>'
         if contenido.get("cubre") else ""),
        (f'<div class="mitad"><h5>{_esc(t["scope"])}</h5>'
         f'{_parrafo(contenido.get("no_cubre"))}</div>'
         if contenido.get("no_cubre") else ""),
    ])

    coordina = "".join([
        _dato(t["contact_name"], coordinacion.get("nombre")),
        _dato(t["phone"], coordinacion.get("telefono")),
        _dato(t["email"], coordinacion.get("correo")),
    ])

    return f"""<!doctype html>
<html lang="{idioma or 'es'}"><head><meta charset="utf-8">
<title>{_esc(contenido['servicio'])} · {_esc(t['embedded_service'])}</title>
<style>
  * {{ box-sizing: border-box; }}
  :root {{ --centauro: #1B1546; --suave: #f0f3f5; }}
  body {{ font: 13px/1.5 Inter, -apple-system, "Segoe UI", system-ui, sans-serif;
         color: #1a1d21; background: var(--suave); margin: 0; padding: 20px; }}
  .hoja {{ max-width: 860px; margin: 0 auto; background: #fff;
          border: 1px solid #dfe2e6; border-radius: 8px; overflow: hidden;
          border-top: 5px solid var(--centauro); }}
  header {{ padding: 18px 22px 16px; position: relative;
           border-bottom: 1px solid #e7e9ec; }}
  header .logo {{ height: 76px; width: auto; max-width: 340px;
                 display: block; margin-bottom: 12px; }}
  header .marca-texto {{ display: block; font-size: 13px; font-weight: 700;
                        letter-spacing: 3px; margin-bottom: 8px;
                        color: var(--centauro); }}
  header .identidad {{ padding-right: 150px; }}
  header h1 {{ font-size: 19px; margin: 0 0 2px; font-weight: 700;
              color: var(--centauro); }}
  header .sub {{ font-size: 12.5px; color: #5b646d; }}
  header .linea {{ display: flex; align-items: baseline; gap: 8px;
                  margin-bottom: 6px; }}
  header .linea .clave {{ font-weight: 700; font-size: 12px; color: #fff;
                         background: var(--centauro); padding: 2px 8px;
                         border-radius: 4px; letter-spacing: .5px; }}
  header .linea .nombre {{ font-size: 10px; text-transform: uppercase;
                          letter-spacing: 1.1px; color: #78828c;
                          font-weight: 650; }}
  header .sello {{ position: absolute; top: 18px; right: 22px;
                  text-align: right; }}
  header .confidencial {{ display: block; font-size: 10px; font-weight: 700;
                         letter-spacing: 1.4px; text-transform: uppercase;
                         color: #c0392b; margin-bottom: 6px; }}
  header .version {{ display: inline-block; font-size: 11px;
                    border: 1px solid var(--centauro); color: var(--centauro);
                    padding: 3px 9px; border-radius: 20px; font-weight: 600; }}
  header .actualizado {{ display: block; font-size: 10.5px; color: #78828c;
                        margin-top: 4px; }}
  /* La cobertura se distingue de un vistazo: es otra hoja, no el
     documento de siempre con una fecha cambiada. */
  .banda {{ background: #fdf1d6; color: #8a6216; padding: 10px 22px;
           font-size: 11px; font-weight: 700; text-transform: uppercase;
           letter-spacing: 1.2px; display: flex; justify-content: space-between;
           flex-wrap: wrap; gap: 8px; }}
  .banda span {{ text-transform: none; letter-spacing: 0; font-weight: 600;
                font-size: 12.5px; }}
  .cuerpo {{ padding: 4px 22px 22px; }}
  .bloque {{ border-top: 1px solid #e7e9ec; padding: 16px 0; }}
  .bloque:first-of-type {{ border-top: 0; }}
  h3 {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .8px;
       color: #78828c; margin: 0 0 12px; font-weight: 650; }}
  h5 {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .7px;
       color: #78828c; margin: 0 0 6px; font-weight: 650; }}
  .rejilla {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
  .rejilla.dos {{ grid-template-columns: 1fr 1fr; }}
  .dato .etiqueta {{ font-size: 10.5px; text-transform: uppercase;
                    letter-spacing: .7px; color: #78828c; font-weight: 650; }}
  .dato .valor {{ margin-top: 2px; white-space: pre-wrap; }}
  .mitad p {{ margin: 0 0 6px; }}
  /* La ficha de quien cubre: es el bloque que vende el servicio. */
  .fichas {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .ficha {{ display: flex; gap: 12px; border: 1px solid #e7e9ec;
           border-radius: 8px; padding: 12px; background: #fcfdfe; }}
  .retrato {{ width: 72px; height: 72px; border-radius: 8px;
             object-fit: cover; flex: 0 0 72px; }}
  .retrato.sin {{ background: #e7e9ec; }}
  .cuerpo-ficha {{ min-width: 0; }}
  .ficha h4 {{ margin: 0; font-size: 14px; color: var(--centauro); }}
  .ficha .puesto {{ font-size: 11.5px; color: #5b646d; }}
  .marcas {{ margin: 8px 0 4px; display: flex; flex-wrap: wrap; gap: 6px; }}
  .marca {{ font-size: 10.5px; background: var(--suave); color: var(--centauro);
           padding: 2px 8px; border-radius: 20px; font-weight: 600; }}
  .marca.fuerte {{ background: var(--centauro); color: #fff; }}
  .cursos {{ margin-top: 10px; }}
  .cursos ul {{ margin: 0; padding-left: 16px; font-size: 11.5px; }}
  .cursos li {{ margin-bottom: 4px; }}
  .vencida {{ color: #c0392b; font-weight: 600; }}
  .unidad {{ display: flex; gap: 10px; margin-top: 12px;
            border-top: 1px dashed #e7e9ec; padding-top: 10px; }}
  .foto-unidad {{ width: 64px; height: 44px; border-radius: 6px;
                 object-fit: cover; flex: 0 0 64px; }}
  .foto-unidad.sin {{ background: #e7e9ec; }}
  .placa {{ font-variant-numeric: tabular-nums; letter-spacing: .5px; }}
  .sello-blindada {{ font-size: 10px; background: var(--centauro); color: #fff;
                    padding: 1px 7px; border-radius: 20px; font-weight: 600; }}
  .hospitales {{ margin: 0; padding-left: 16px; font-size: 12px; }}
  .hospitales li {{ margin-bottom: 6px; }}
  .nivel {{ display: flex; gap: 10px; margin-bottom: 10px; }}
  .nivel .num {{ width: 22px; height: 22px; border-radius: 50%;
                background: var(--centauro); color: #fff; font-size: 11px;
                display: flex; align-items: center; justify-content: center;
                flex: 0 0 22px; font-weight: 700; }}
  .gris {{ color: #78828c; }}
  .tel {{ font-variant-numeric: tabular-nums; }}
  footer {{ padding: 14px 22px; border-top: 1px solid #e7e9ec;
           font-size: 10.5px; color: #78828c; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .hoja {{ border: 0; border-radius: 0; max-width: none; }}
    .ficha {{ break-inside: avoid; }}
    .bloque {{ break-inside: avoid; }}
  }}
  @media (max-width: 700px) {{
    .rejilla, .rejilla.dos, .fichas {{ grid-template-columns: 1fr; }}
  }}
</style></head>
<body><div class="hoja">
<header>
  <div class="sello">
    <span class="confidencial">{_esc(t["confidential"])}</span>
    <span class="version">{_esc(t["version"])} {version}</span>
    {f'<span class="actualizado">{_esc(actualizado)}</span>' if actualizado else ''}
  </div>
  <div class="identidad">
    {marca}
    <div class="linea"><span class="clave">{LINEA}</span>
      <span class="nombre">{_esc(t["linea"])}</span></div>
    <h1>{_esc(contenido['servicio'])} · {_esc(t['embedded_service'])}</h1>
    <div class="sub">{_esc(" · ".join(filter(None, [contenido.get("cliente"),
                                                    contenido.get("ciudad")])))}</div>
    {f'<div class="sub">{_esc(t["principal"])}: <b>{_esc(contenido["ejecutivo"])}</b></div>'
     if contenido.get("ejecutivo") else ''}
  </div>
</header>
{banda}
<div class="cuerpo">
  {_bloque(t["the_service"], f'<div class="rejilla">{servicio}</div>')}
  {_bloque(t["scope_block"], f'<div class="rejilla dos">{alcance}</div>')}
  {_bloque(t["service_coordination"],
           (f'<div class="rejilla">{coordina}</div>' if coordina else "")
           + (f'<div class="dato" style="margin-top:10px">'
              f'<span class="etiqueta">{_esc(t["protocol"])}</span>'
              f'<div class="valor">{_parrafo(contenido.get("protocolo"))}</div></div>'
              if contenido.get("protocolo") else ""))}
  {_bloque(titulo_equipo,
           f'<div class="fichas">'
           f'{"".join(_ficha(p, t) for p in contenido.get("equipo") or [])}</div>'
           if contenido.get("equipo") else "")}
  {_bloque(t["escalation"], _escalacion(contenido.get("escalacion") or [], t))}
  {_bloque(t["hospitals"], _hospitales(contenido.get("hospitales") or [], t))}
</div>
<footer>{_esc(t["footer_note"])}</footer>
</div></body></html>"""

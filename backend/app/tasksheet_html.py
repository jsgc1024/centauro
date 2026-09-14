"""Version imprimible del task sheet: una hoja, lectura de un vistazo."""
import html
import re

from app.marca import logo_incrustado
from app.textos import diccionario, fecha_larga


# Linea de operacion a la que pertenece todo este desarrollo. Es el mismo
# prefijo de los folios: AI/EP, que en el folio se abre por tipo —EP/E
# para el eventual, EP/IM para el implantado—.
LINEA = "AI/EP"


def _esc(valor) -> str:
    return html.escape(str(valor)) if valor not in (None, "") else "—"


def _persona(p: dict, t: dict, con_abordo: bool = False) -> str:
    """con_abordo solo cuando el dia lleva mas de una unidad: ahi si hay
    que decir en cual va cada quien."""
    foto = (f'<img class="foto" src="{_esc(p["foto"])}" alt="">'
            if p.get("foto") else '<div class="foto sin"></div>')
    horas = p.get("horas_en_centauro")
    experiencia = (f'<br><span class="experiencia">{horas:,} {t["hours_at"]}</span>'
                   if horas else "")
    abordo = (f'<br><span class="abordo">{t["boards"]} '
              f'<span class="placas">{_esc(p["abordo"])}</span></span>'
              if con_abordo and p.get("abordo") else "")
    puesto = t["perfiles"].get(p["puesto"], p["puesto"])
    return f"""<div class="persona">{foto}
      <div class="datos"><h4 class="puesto">{_esc(puesto)}</h4>
      <b>{_esc(p['nombre'])}</b><br>
      <span class="tel">{_esc(p['telefono'])}</span>{experiencia}{abordo}</div></div>"""


def _modelo(nombre: str) -> str:
    """El nombre del catalogo trae el blindaje pegado: "Toyota Sienna
    blindada". En la hoja eso ya lo dice la etiqueta, y en ingles quedaba
    "Sienna blindada / armored", repetido y a medio traducir.
    """
    limpio = re.sub(r"\s+(blindad[oa]|sin\s+blindar)\s*$", "",
                    str(nombre or ""), flags=re.IGNORECASE)
    return limpio.strip() or str(nombre or "")


def _unidad(u: dict, t: dict, titulo: str | None = None) -> str:
    """Mismo orden que la persona: titulo, nombre, identificador, detalle.

    Asi las placas caen a la altura del telefono del conductor.
    """
    # Siempre se dice el blindaje: al ejecutivo le importa saberlo, y que
    # no diga nada dejaria la duda de si es que nadie lo capturo.
    blindada = (f' <span class="etiqueta">{t["armored"]}</span>'
                if u.get("blindada")
                else f' <span class="etiqueta suave">{t["soft_skin"]}</span>')
    modelo = _modelo(u["unidad"])
    detalle = " · ".join(filter(None, [u.get("marca_modelo"), u.get("color"),
                                       str(u.get("anio") or "")]))
    linea_detalle = (f' <span class="detalle-unidad">{_esc(detalle)}</span>'
                     if detalle else "")
    foto = (f'<img class="foto foto-unidad" src="{_esc(u["foto"])}" alt="">'
            if u.get("foto") else '<div class="foto foto-unidad sin"></div>')
    encabezado = f'<h4 class="puesto">{titulo}</h4>' if titulo else ""
    return (f'<div class="unidad">{foto}'
            f'<div class="datos">{encabezado}'
            f'<b>{_esc(modelo)}</b>{blindada}<br>'
            f'<span class="placas">{_esc(u["placas"])}</span>'
            f'{linea_detalle}</div></div>')


def _hospitales(lista: list, t: dict) -> str:
    if not lista:
        return f'<span class="gris">{t["no_hospitals"]}</span>'
    filas = "".join(
        f'<tr><td>{_esc(h["nombre"])}</td>'
        f'<td class="der">{h["km"]} km</td>'
        f'<td>{_esc(h["telefono"])}</td></tr>' for h in lista)
    return f'<table class="hosp">{filas}</table>'


def _recursos_del_dia(d: dict, t: dict) -> str:
    """Solo lo que cambia respecto al equipo base. Si el dia es igual,
    no se dibuja nada: ya esta arriba."""
    cambios = d.get("cambios")
    if d.get("igual_todo_el_servicio") or not cambios:
        return ""

    partes = []

    if cambios.get("personal_se_suma"):
        partes.append(
            f'<div class="cambio-bloque"><h4>{t["added_today"]}</h4>'
            + "".join(_persona(p, t, len(d.get("unidades") or []) > 1)
                       for p in cambios["personal_se_suma"])
            + "</div>")

    if cambios.get("personal_no_va"):
        partes.append(
            f'<div class="cambio-bloque"><h4>{t["not_today"]}</h4>'
            f'<div class="gris">{_esc(", ".join(cambios["personal_no_va"]))}</div>'
            "</div>")

    if cambios.get("unidad_se_suma"):
        partes.append(
            f'<div class="cambio-bloque"><h4>{t["extra_vehicle"]}</h4>'
            + "".join(_unidad(u, t) for u in cambios["unidad_se_suma"])
            + "</div>")

    if cambios.get("unidad_no_va"):
        partes.append(
            f'<div class="cambio-bloque"><h4>{t["vehicle_out"]}</h4>'
            f'<div class="gris">{_esc(", ".join(cambios["unidad_no_va"]))}</div>'
            "</div>")

    if cambios.get("otro_origen"):
        partes.append(
            f'<div class="cambio-bloque"><h4>{t["other_origin"]}</h4>'
            f'<div>{_esc(cambios["otro_origen"])}</div></div>')

    if not partes:
        return ""
    return f'<div class="cambios">{"".join(partes)}</div>'


def _cobertura(c: dict, t: dict) -> str:
    """Que cubre el equipo: 3 full days y 2 transfers, no solo "5 dias"."""
    por_modalidad = c.get("dias_por_modalidad") or {}
    if not por_modalidad:
        cuantos = c.get("dias_con_este_equipo") or 0
        return (f' <span class="gris pequeno">· {cuantos} {t["days"]}</span>'
                if cuantos > 1 else "")

    orden = ["full_day", "medio_dia", "transfer"]
    partes = []
    for codigo in sorted(por_modalidad, key=lambda x: orden.index(x)
                         if x in orden else 99):
        n = por_modalidad[codigo]
        etiqueta = (t["modalidades_plural"] if n > 1 else t["modalidades"]).get(
            codigo, codigo)
        partes.append(f"{n} {etiqueta}")

    if len(partes) == 1 and sum(por_modalidad.values()) == 1:
        return ""
    return f' <span class="gris pequeno">· {" · ".join(partes)}</span>'


def _encuentro(c: dict, t: dict) -> str:
    """El arranque del servicio: donde, que dia y a que hora.

    Es el punto del primer dia, el mismo que abre la agenda. No es el
    punto que mas se repite en el servicio, que suele ser el hotel.
    """
    e = c.get("encuentro")
    if not e:
        return ""
    cuando = ""
    if e.get("fecha_iso"):
        cuando = (f'<span class="encuentro-cuando">'
                  f'{_esc(fecha_larga(e["fecha_iso"], t))}'
                  f'{" · " + _esc(e["hora"]) if e.get("hora") else ""}</span>')
    return f"""
      <div class="encuentro">
        <h4>{t["origin"]}{cuando}</h4>
        <div class="encuentro-lugar">{_esc(e["lugar"])}</div>
        {_vuelo(e.get("vuelo"), t)}
        {_llegada_equipo(e.get("llegada_equipo"), t)}
        <div class="encuentro-nota">{t["origin_nota"]}</div>
      </div>"""


def _llegada_equipo(l: dict | None, t: dict) -> str:
    """El equipo llega antes que el ejecutivo. Siempre.

    Va dentro del meet and greet porque es la promesa que el ejecutivo
    puede exigir: cuando el salga, el equipo ya va a estar ahi.
    """
    if not l:
        return ""
    razon = t["before_flight"] if l.get("contra_vuelo") else t["before_pickup"]
    return (f'<div class="en-sitio"><span class="vuelo-etiqueta">'
            f'{t["team_onsite"]}</span>'
            f'<span class="en-sitio-hora">{_esc(l["hora"])}</span>'
            f'<span class="vuelo-dato">{l["minutos"]} {razon}</span></div>')


def _vuelo(v: dict | None, t: dict) -> str:
    """El vuelo va dentro del meet and greet: es lo que amarra la hora.

    Dice con todas sus letras si es llegada o salida: el ejecutivo tiene
    que poder confirmar de un vistazo que es su vuelo. Se muestra lo que
    haya capturado; si falta la hora, no se inventa.
    """
    if not v:
        return ""
    identificador = " ".join(filter(None, [v.get("aerolinea"), v.get("numero")]))
    tipo = (t["flight_departure"] if v.get("tipo") == "salida"
            else t["flight_arrival"])
    partes = [f'<span class="vuelo-tipo">{tipo}</span>']
    if identificador:
        partes.append(f'<span class="vuelo-numero">{_esc(identificador)}</span>')
    if v.get("hora"):
        partes.append(f'<span class="vuelo-dato"><b>{_esc(v["hora"])}</b></span>')
    if v.get("procedencia"):
        partes.append(f'<span class="vuelo-dato">{t["flight_from"]} '
                      f'{_esc(v["procedencia"])}</span>')
    return (f'<div class="vuelo"><span class="vuelo-etiqueta">{t["flight"]}</span>'
            + "".join(partes) + "</div>")


def _constantes(c: dict | None, t: dict) -> str:
    """El equipo base del servicio. Los dias que se salen de esto lo indican."""
    if not c:
        return ""
    sufijo_dias = _cobertura(c, t)
    return f"""
    <section class="fijo">
      <div class="subtitulo">{t["security_team"]}{sufijo_dias}</div>
      <div class="rejilla dos">
        <div>
          {''.join(_persona(p, t, len(c['unidades']) > 1) for p in c['personal'])
           or f'<span class="gris">{t["to_assign"]}</span>'}
        </div>
        <div class="bloque-unidad">
          {''.join(_unidad(u, t, t["vehicle"]) for u in c['unidades'])
           or f'<h4>{t["vehicle"]}</h4>'
              f'<span class="gris">{t["to_assign"]}</span>'}
        </div>
      </div>
      {_encuentro(c, t)}
    </section>"""


def _vuelo_dia(v: dict | None, t: dict) -> str:
    """El vuelo de un dia que no es el primero.

    Un servicio solo tiene dos vuelos: la llegada del primer dia, que va
    arriba en el meet and greet, y la salida del ultimo. Si el ejecutivo
    vuela a otra ciudad a media estancia, eso es otro servicio.
    """
    if not v:
        return ""
    identificador = " ".join(filter(None, [v.get("aerolinea"), v.get("numero")]))
    tipo = (t["flight_departure"] if v.get("tipo") == "salida"
            else t["flight_arrival"])
    partes = [x for x in (identificador,
                          v.get("hora") or "",
                          f'{t["flight_from"]} {v["procedencia"]}'
                          if v.get("procedencia") else "") if x]
    return (f'<div class="vuelo-dia"><span class="vuelo-etiqueta-dia">'
            f'{t["flight"]}</span>'
            f'<span class="vuelo-tipo-dia">{tipo}</span> '
            f'{_esc(" · ".join(partes))}</div>')


def _dia(d: dict, t: dict, primero: bool = False) -> str:
    agenda = d.get("agenda") or {}
    # El vuelo del primer dia ya sale arriba, en el meet and greet.
    vuelo = "" if primero else _vuelo_dia(d.get("vuelo"), t)
    puntos = ""
    # La hora y el lugar, en columnas: es lo que el equipo lee para saber
    # a donde va y a que hora. La parada sin hora lo dice —hay que
    # confirmarla— en vez de dejar el renglon corrido y sin horario.
    for p in agenda.get("paradas") or []:
        hora = (f'<span class="hora-parada">{_esc(p["hora"])}</span>'
                if p.get("hora") else
                f'<span class="hora-parada sin">{t["to_confirm"]}</span>')
        donde = (f'<div class="donde-parada">{_esc(p["direccion"])}</div>'
                 if p.get("direccion") else "")
        nota = (f'<div class="nota-parada">{_esc(p["notas"])}</div>'
                if p.get("notas") else "")
        puntos += (f'<tr><td class="col-hora-parada">{hora}</td>'
                   f'<td><b>{_esc(p["lugar"])}</b>{donde}{nota}</td></tr>')
    # Las agendas viejas venian en un solo bloque de texto: se siguen
    # imprimiendo igual, un renglon por linea.
    if not puntos and agenda.get("puntos"):
        renglones = [p.strip() for p in agenda["puntos"].split("\n") if p.strip()]
        puntos = "".join(f'<tr><td class="col-hora-parada">'
                         f'<span class="hora-parada sin">{t["to_confirm"]}</span>'
                         f'</td><td>{_esc(p)}</td></tr>' for p in renglones)

    # Que el dia no diga donde arranca es informacion, no un hueco: sin
    # esta linea se lee como si arrancara donde el dia anterior.
    por_confirmar = (
        f'<div class="origen">{_esc(t["other_origin"])}: '
        f'{_esc(t["origin_tbc"])}</div>'
        if d.get("origen_por_confirmar") else "")

    # La tabla de paradas se arma aparte: dentro del f-string grande no
    # cabe sin pelearse con las comillas.
    tabla = f'<table class="paradas">{puntos}</table>' if puntos else ""
    bloque_agenda = (
        f'<div class="agenda"><h4>{t["agenda"]}</h4>'
        f'<p>{_esc(agenda.get("resumen"))}</p>{tabla}</div>'
        if agenda else
        f'<div class="agenda abierta"><h4>{t["agenda"]}</h4>'
        f'<p>{t["open_agenda"]}</p></div>')

    return f"""
    <section class="dia">
      <div class="cabecera">
        <div><span class="fecha">{_esc(t['dias_semana'][d['dia_semana_num']])}
             {_esc(fecha_larga(d['fecha_iso'], t))}</span>
             <span class="modalidad">{_esc(t['modalidades'].get(d['modalidad'],
                                           d['modalidad']))}</span></div>
        <div class="horas">{_esc(d['presentacion'])} — {_esc(d['cierre_estimado'])}</div>
      </div>
      {vuelo}
      {por_confirmar}
      {_recursos_del_dia(d, t)}
      {bloque_agenda}
    </section>"""


def _cierre_hoja(hospedaje: list, hospitales: list, t: dict,
                 desde: str | None = None) -> str:
    """Al final: donde se queda el ejecutivo y, a su derecha, los hospitales."""
    if not hospedaje and not hospitales and not desde:
        return ""
    izquierda = _hospedaje(hospedaje, t) or ""
    # "A 2 km" no significa lo mismo medido del hotel que del aeropuerto.
    pie = (f'<div class="gris chico">{t["hospitals_from_" + desde]}</div>'
           if desde and hospitales else "")
    # El bloque sale aunque la lista este vacia, siempre que hubiera desde
    # donde medir: que no diga nada se lee como que no hace falta, y lo
    # que pasa es que a esa ciudad todavia no le han cargado hospitales.
    # Un hueco que se ve es un hueco que alguien tapa.
    derecha = (f'<div class="hospitales-bloque"><h4>{t["hospitals"]}</h4>'
               f'{pie}{_hospitales(hospitales, t)}</div>'
               if (hospitales or desde) else "")
    return f'<div class="cierre">{izquierda}{derecha}</div>'


def _hospedaje(lista: list, t: dict) -> str:
    if not lista:
        return ""
    tarjetas = "".join(f"""
      <div class="hotel">
        <b>{_esc(h['hotel'])}</b>
        <br><span class="gris">{_esc(h['direccion'])}</span>
        <br><span class="tel">{_esc(h['telefono'])}</span>
        {f'<span class="gris"> · ' + _esc(fecha_larga(h["desde"], t)) + " — "
           + _esc(fecha_larga(h["hasta"], t)) + "</span>" if h.get("desde") else ""}
        {f'<br><span class="gris">{_esc(h["notas"])}</span>' if h.get('notas') else ''}
      </div>""" for h in lista)
    return f'<div class="hospedaje"><h4>{t["lodging"]}</h4>{tarjetas}</div>'


def _senal(senal: dict | None, contenido: dict, t: dict) -> str:
    """Hoja aparte, para imprimir y mostrarla al ejecutivo cuando sale del
    filtro del aeropuerto o espera en el lobby. Se lee de lejos."""
    if not senal:
        return ""

    imagen = (f'<img class="senal-imagen" src="{senal["imagen"]}" alt="">'
              if senal.get("imagen") else "")
    texto = (f'<div class="senal-texto">{_esc(senal["texto"])}</div>'
             if senal.get("texto") else "")
    nota = (f'<div class="senal-nota">{_esc(senal["nota"])}</div>'
            if senal.get("nota") else "")

    return f"""
  <section class="hoja-senal">
    <div class="senal-encabezado">{t["sign_title"]} ·
      {_esc(contenido['servicio'])}</div>
    <div class="senal-centro">
      {imagen}
      {texto}
    </div>
    {nota}
    <div class="senal-pie">{t["sign_footer"]}
      {_esc(contenido['ejecutivo'] or "")} {t["sign_look"]}</div>
  </section>"""


def render(contenido: dict, version: int, actualizado: str | None = None,
           idioma: str | None = None) -> str:
    t = diccionario(idioma)
    telefono = contenido.get("ejecutivo_telefono")
    telefono_ejecutivo = f" · {_esc(telefono)}" if telefono else ""
    logo = logo_incrustado()
    marca = (f'<img class="logo" src="{logo}" alt="Centauro">' if logo
             else '<span class="marca-texto">CENTAURO</span>')

    escalacion = "".join(
        f'<div class="nivel"><span class="num">{n["nivel"]}</span>'
        f'<div><b>{_esc(n["nombre"])}</b><br>'
        f'<span class="gris">{_esc(t["cargos"].get(n["cargo"], n["cargo"]))}</span><br>'
        f'<span class="tel">{_esc(n["telefono"])}</span></div></div>'
        for n in contenido["escalacion"])

    return f"""<!doctype html>
<html lang="{idioma or 'en'}"><head><meta charset="utf-8">
<title>{_esc(contenido['servicio'])} · {t["team"]} {_esc(contenido.get('equipo', ''))}</title>
<style>
  * {{ box-sizing: border-box; }}
  :root {{ --centauro: #1B1546; --suave: #f0f3f5; }}
  body {{ font: 13px/1.45 Inter, -apple-system, "Segoe UI", system-ui, sans-serif;
         color: #1a1d21; background: var(--suave); margin: 0; padding: 20px; }}
  .hoja {{ max-width: 860px; margin: 0 auto; background: #fff;
          border: 1px solid #dfe2e6; border-radius: 8px; overflow: hidden;
          border-top: 5px solid var(--centauro); }}
  header {{ background: #fff; color: var(--centauro); padding: 18px 22px 16px;
           position: relative; border-bottom: 1px solid #e7e9ec; }}
  header .logo {{ height: 76px; width: auto; max-width: 340px;
                 display: block; margin-bottom: 12px; }}
  header .marca-texto {{ display: block; font-size: 13px; font-weight: 700;
                        letter-spacing: 3px; margin-bottom: 8px;
                        color: var(--centauro); }}
  header h1 {{ font-size: 19px; margin: 0 0 1px; letter-spacing: .2px;
              font-weight: 700; }}
  /* La linea de operacion: este documento es de Proteccion Ejecutiva, el
     mismo prefijo que llevan los folios. Vienen mas lineas de negocio. */
  header .linea {{ display: flex; align-items: baseline; gap: 8px;
                  margin-bottom: 6px; }}
  header .linea .clave {{ font-weight: 700; font-size: 12px;
                         letter-spacing: .5px; color: #fff;
                         background: var(--centauro); padding: 2px 8px;
                         border-radius: 4px; }}
  header .linea .nombre {{ font-size: 10px; text-transform: uppercase;
                          letter-spacing: 1.1px; color: #78828c;
                          font-weight: 650; }}
  header .equipo-linea {{ font-size: 13px; font-weight: 600;
                         color: var(--centauro); margin-bottom: 4px; }}
  header .meta {{ font-size: 12px; color: #5b646d; text-align: center;
                 margin-top: 10px; padding-top: 10px;
                 border-top: 1px solid #eef0f2; }}
  /* Pegado a la esquina superior derecha, sin depender del alto del logo. */
  header .sello {{ position: absolute; top: 18px; right: 22px;
                  text-align: right; }}
  header .identidad {{ padding-right: 130px; }}
  header .confidencial {{ display: block; font-size: 10px; font-weight: 700;
                         letter-spacing: 1.4px; text-transform: uppercase;
                         color: #c0392b; margin-bottom: 6px; }}
  header .version {{ display: inline-block; font-size: 11px;
                    border: 1px solid var(--centauro);
                    color: var(--centauro); padding: 3px 9px;
                    border-radius: 20px; font-weight: 600; margin-top: 6px; }}
  header .actualizado {{ display: block; font-size: 10.5px; color: #78828c; }}
  .cuerpo {{ padding: 6px 22px 22px; }}
  .dia {{ border-top: 1px solid #e7e9ec; padding: 16px 0; }}
  .dia:first-of-type {{ border-top: 0; }}
  .cabecera {{ display: flex; justify-content: space-between;
              align-items: baseline; flex-wrap: wrap; gap: 8px; }}
  .fecha {{ font-weight: 650; font-size: 14px; }}
  .modalidad {{ font-size: 11px; background: var(--suave); color: var(--centauro);
               padding: 2px 8px; border-radius: 20px; margin-left: 8px; }}
  .horas {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
  .origen {{ color: #5b646d; margin: 4px 0 12px; font-size: 12px; }}
  .rejilla {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
  .rejilla.dos {{ grid-template-columns: 1fr 1fr; }}
  h4 {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .7px;
       color: #78828c; margin: 0 0 8px; font-weight: 650; }}
  .persona {{ display: flex; gap: 10px; margin-bottom: 12px;
             align-items: flex-start; }}
  .persona .datos {{ line-height: 1.45; }}
  h4.puesto {{ margin: 0 0 1px; color: var(--centauro); }}
  /* En que unidad va esa persona. Solo sale en los dias con mas de una. */
  .abordo {{ font-size: 10.5px; color: #5b6470; }}
  .subtitulo {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .7px;
               color: #78828c; font-weight: 650; margin: 0 0 12px;
               text-align: center; }}
  .subtitulo .pequeno {{ color: #78828c; }}
  .bloque-unidad h4 {{ margin: 0 0 1px; color: var(--centauro); }}
  .foto {{ width: 38px; height: 38px; border-radius: 6px; object-fit: cover;
          flex: 0 0 38px; }}
  .foto.sin {{ background: #e7e9ec; }}
  .gris {{ color: #78828c; }}
  .experiencia {{ font-size: 11px; color: var(--centauro); font-weight: 600; }}
  .tel {{ font-variant-numeric: tabular-nums; }}
  .unidad {{ display: flex; gap: 10px; margin-bottom: 12px;
            align-items: flex-start; line-height: 1.45; }}
  .foto-unidad {{ width: 56px; height: 38px; flex: 0 0 56px;
                 object-fit: cover; border-radius: 6px; }}
  .detalle-unidad {{ font-size: 11px; color: #78828c; }}
  .placas {{ font-family: ui-monospace, Menlo, monospace; background: var(--suave);
            padding: 1px 6px; border-radius: 4px; }}
  .etiqueta {{ font-size: 10px; background: var(--centauro); color: #fff;
              padding: 1px 6px; border-radius: 20px; vertical-align: 2px; }}
  .etiqueta.suave {{ background: transparent; color: #78828c;
                    border: 1px solid #d7dbe0; }}
  table.hosp {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  table.hosp td {{ padding: 2px 0; vertical-align: top; }}
  .der {{ text-align: right; color: #78828c; white-space: nowrap;
         padding-right: 8px !important; }}
  .fijo {{ padding: 16px 0 4px; }}
  .encuentro {{ margin: 14px 0 4px; padding: 12px 16px; border-radius: 6px;
               background: var(--centauro); color: #fff;
               border-left: 5px solid #c9a227; }}
  .encuentro h4 {{ color: rgba(255,255,255,.75); margin: 0 0 4px; }}
  .encuentro-lugar {{ font-size: 15px; font-weight: 650; line-height: 1.35; }}
  .encuentro-nota {{ font-size: 11px; color: rgba(255,255,255,.7);
                    margin-top: 3px; }}
  .vuelo-dia {{ margin: 6px 0 0; font-size: 12px; color: var(--centauro);
               font-variant-numeric: tabular-nums; }}
  .vuelo-etiqueta-dia {{ font-size: 9.5px; text-transform: uppercase;
                        letter-spacing: .8px; color: #78828c; font-weight: 650;
                        margin-right: 4px; }}
  .vuelo {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
           margin-top: 8px; padding-top: 8px;
           border-top: 1px solid rgba(255,255,255,.2); }}
  .vuelo-etiqueta {{ font-size: 9.5px; text-transform: uppercase;
                    letter-spacing: .8px; color: rgba(255,255,255,.6);
                    font-weight: 650; }}
  .vuelo-numero {{ font-family: ui-monospace, Menlo, monospace; font-size: 14px;
                  font-weight: 650; letter-spacing: .5px; }}
  .en-sitio {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
              margin-top: 6px; }}
  .en-sitio-hora {{ font-size: 14px; font-weight: 700;
                   font-variant-numeric: tabular-nums; }}
  .vuelo-tipo {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: 1px;
                font-weight: 700; background: #c9a227; color: #1a1508;
                padding: 2px 8px; border-radius: 20px; }}
  .vuelo-tipo-dia {{ font-size: 9.5px; text-transform: uppercase;
                    letter-spacing: 1px; font-weight: 700;
                    background: var(--centauro); color: #fff;
                    padding: 1px 7px; border-radius: 20px; margin-right: 6px; }}
  .vuelo-dato {{ font-size: 12px; color: rgba(255,255,255,.85);
                font-variant-numeric: tabular-nums; }}
  .encuentro-cuando {{ float: right; font-weight: 650; letter-spacing: 0;
                      text-transform: none; font-size: 11px;
                      font-variant-numeric: tabular-nums;
                      color: rgba(255,255,255,.9); }}
  .cambios {{ display: flex; gap: 22px; flex-wrap: wrap; margin-top: 10px;
             background: var(--suave); border-radius: 6px; padding: 11px 14px; }}
  .cambio-bloque h4 {{ margin-bottom: 6px; }}
  .pequeno {{ font-size: 10px; font-weight: 400; letter-spacing: 0;
             text-transform: none; }}
  .cambio {{ font-size: 9.5px; background: var(--centauro); color: #fff; padding: 1px 6px;
            border-radius: 20px; letter-spacing: 0; text-transform: none;
            margin-left: 4px; }}
  .titulo-dias {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .7px;
                 color: #78828c; margin: 18px 0 0; font-weight: 650;
                 border-top: 1px solid #e7e9ec; padding-top: 14px; }}
  .cierre {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
            margin-top: 18px; padding-top: 16px;
            border-top: 1px solid #e7e9ec; }}
  .hospedaje, .hospitales-bloque {{ background: var(--suave); border-radius: 6px;
                                   padding: 12px 14px; margin: 0; }}
  .hotel {{ margin-bottom: 8px; }}
  .hotel:last-child {{ margin-bottom: 0; }}
  .agenda {{ margin-top: 14px; background: #f8f9fa; border-radius: 6px;
            padding: 11px 14px; }}
  .agenda p {{ margin: 0 0 6px; }}
  .agenda.abierta {{ background: #fff; border: 1px dashed #d7dbe0; }}
  .agenda.abierta p {{ color: #78828c; margin: 0; }}
  .agenda ul {{ margin: 0; padding-left: 18px; }}
  /* La hora en su columna, alineada renglon con renglon: el equipo lee
     el horario del dia de corrido, sin buscarlo dentro del texto. */
  .agenda table.paradas {{ width: 100%; border-collapse: collapse; }}
  .agenda table.paradas td {{ padding: 3px 0; vertical-align: top;
                              border-top: 1px solid #e7e9ec; }}
  .agenda table.paradas tr:first-child td {{ border-top: 0; }}
  .agenda .col-hora-parada {{ width: 74px; white-space: nowrap; }}
  .agenda .hora-parada {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
  .agenda .hora-parada.sin {{ font-weight: 600; font-size: 10px;
                              color: #8a6d1f; text-transform: uppercase;
                              letter-spacing: .4px; }}
  .agenda .donde-parada {{ font-size: 10.5px; color: #5b6470; }}
  .agenda .nota-parada {{ font-size: 10.5px; color: #5b6470; }}
  .agenda li {{ margin-bottom: 2px; }}
  footer {{ background: var(--suave); border-top: 1px solid #e7e9ec;
           padding: 16px 22px; }}
  .aviso {{ font-size: 10.5px; color: #8a5a5a; background: #fdf3f3;
           border: 1px solid #f3dede; border-radius: 5px; padding: 8px 11px;
           margin-bottom: 14px; }}
  .escala {{ display: flex; gap: 26px; flex-wrap: wrap; }}
  .nivel {{ display: flex; gap: 9px; align-items: center; }}
  .num {{ width: 22px; height: 22px; border-radius: 50%; background: var(--centauro);
         color: #fff; display: grid; place-items: center; font-size: 11px;
         font-weight: 650; flex: 0 0 22px; }}
  .hoja-senal {{ border-top: 1px solid #e7e9ec; margin: 0 22px;
                padding: 26px 0 22px; text-align: center; }}
  .senal-encabezado {{ font-size: 10.5px; text-transform: uppercase;
                      letter-spacing: .7px; color: #78828c; font-weight: 650; }}
  .senal-centro {{ padding: 26px 0 18px; }}
  .senal-imagen {{ max-width: 100%; max-height: 420px; margin: 0 auto 18px;
                  display: block; object-fit: contain; }}
  .senal-texto {{ font-size: 58px; font-weight: 750; line-height: 1.1;
                 letter-spacing: -.5px; word-break: break-word;
                 color: var(--centauro); }}
  .senal-nota {{ color: #5b646d; font-size: 13px; margin-bottom: 16px; }}
  .senal-pie {{ font-size: 11px; color: #78828c; }}
  @media (max-width: 640px) {{
    header .sello {{ position: static; text-align: left; margin-top: 12px; }}
    header .identidad {{ padding-right: 0; }}
    .rejilla, .rejilla.dos, .cierre {{ grid-template-columns: 1fr; }}
    .senal-texto {{ font-size: 40px; }}
  }}
  @media print {{
    /* Hoja carta: la señal se imprime para levantarla en el filtro y
       tiene que leerse a varios metros, asi que ocupa una pagina entera
       y nada mas comparte esa pagina. */
    @page {{ size: letter; margin: 12mm; }}
    body {{ background: #fff; padding: 0; }}
    .hoja {{ border: 0; }}
    .hoja-senal {{
      page-break-before: always; page-break-after: always;
      break-before: page; break-after: page;
      border-top: 0; margin: 0; padding: 0;
      height: 245mm;              /* carta menos los margenes */
      display: flex; flex-direction: column; justify-content: space-between;
    }}
    /* El centro se queda con todo el alto que sobra: el nombre o el
       logotipo mandan, el encabezado y el pie solo acompañan. */
    .hoja-senal .senal-centro {{
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center; padding: 0;
    }}
    .senal-texto {{ font-size: 130pt; line-height: 1.05; letter-spacing: -1px; }}
    /* La imagen crece hasta donde la hoja aguante, sin deformarse. */
    .senal-imagen {{
      max-height: 190mm; max-width: 100%; width: auto; height: auto;
      object-fit: contain; margin: 0 auto;
    }}
    /* Con nombre e imagen juntos, el nombre cede: la imagen es la que
       se reconoce de lejos. */
    .senal-imagen + .senal-texto {{ font-size: 40pt; margin-top: 10mm; }}
    .senal-encabezado {{ font-size: 11pt; }}
    .senal-pie {{ font-size: 10pt; }}
  }}
</style></head>
<body><div class="hoja">
  <header>
    <div class="identidad">
      {marca}
      <div class="linea"><span class="clave">{LINEA}</span>
        <span class="nombre">{t["linea"]}</span></div>
      <h1>{_esc(contenido['servicio'])}</h1>
      <div class="equipo-linea">{t["team"]} {_esc(contenido.get('equipo', ''))}</div>
    </div>
    <div class="meta">{_esc(contenido['cliente'])} ·
      {t["executive"]}: {_esc(contenido['ejecutivo'])}{telefono_ejecutivo} ·
      {_esc(contenido['plaza'])}</div>
    <div class="sello">
      <span class="confidencial">{t["confidential"]}</span>
      <span class="actualizado">{t["updated"]} {_esc(actualizado
          or contenido.get('generado_en'))}</span>
      <span class="version">v{version}</span>
    </div>
  </header>
  <div class="cuerpo">
    {_constantes(contenido.get('constantes'), t)}
    <h3 class="titulo-dias">{t["schedule"]}</h3>
    {''.join(_dia(d, t, i == 0)
             for i, d in enumerate(contenido['dias']))}
    {_cierre_hoja(contenido.get('hospedaje') or [],
                  (contenido.get('constantes') or {}).get('hospitales_cercanos') or [],
                  t,
                  (contenido.get('constantes') or {}).get('hospitales_desde'))}
  </div>
  {_senal(contenido.get('senal'), contenido, t)}
  <footer>
    <div class="aviso">{t["privacy"]}</div>
    <h4>{t["escalation"]}</h4>
    <div class="escala">{escalacion
        or f'<span class="gris">{t["no_contacts"]}</span>'}</div>
  </footer>
</div></body></html>"""

/* La flota de Logistica, AI/LG (seccion 151).

   Cada unidad de la compania «Centauro Logistic» de Odoo con lo que vive
   en Connect: su numero economico, su tipo, su odometro, su estado, su
   expediente, su plan preventivo, sus servicios, sus llantas y lo que
   cuesta tenerla un dia. Cuatro pestanas, como en los bocetos aprobados
   el 3 de octubre: Unidades, Plan preventivo, Carga inicial y Bitacora; y
   el detalle de cada unidad en #/lg/flota/<id>.

   Si una unidad puede salir lo decide el servidor (`lg_disponibilidad`),
   la misma regla que vera quien asigne los viajes: aqui solo se dice en
   el idioma de quien lee. El costo por dia tambien lo calcula el
   servidor: un centavo de diferencia entre la pantalla y el margen del
   viaje es una llamada.

   Quien lleva la flota edita (`lg.flota.editar`); la gerencia de
   Logistica y sistema y calidad la ven, y la gerencia marca a mano el
   «en viaje» mientras los viajes sigan en Tango. Lo que no se puede no se
   pinta: un boton que contesta 403 no ayuda a nadie. */
import { api } from "./api.js";
import { campo, conAyuda, entrada, etiqueta, fecha, fechaLocal, h, hora, hoyLocal, lista,
         mensaje } from "./util.js";
import { idioma, t } from "./idioma.js";

/* La pestana que se esta mirando y los filtros se quedan al volver del
   detalle de una unidad: quien revisa la flota va y viene. */
let pestana = "unidades";
const filtros = { q: "", tipo: "", estado: "", revisar: false };

/* ------------------------------------------------------------ formatos */

const NUMERO = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 });
const DECIMAL = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 2 });
const KML = new Intl.NumberFormat("es-MX", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
const MXN0 = new Intl.NumberFormat("es-MX", {
  style: "currency", currency: "MXN", minimumFractionDigits: 0, maximumFractionDigits: 0 });
const MXN2 = new Intl.NumberFormat("es-MX", {
  style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MXN4 = new Intl.NumberFormat("es-MX", {
  style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 4 });
const nada = (v) => v === null || v === undefined || v === "";
const km = (v) => (nada(v) ? "—" : t("lgf_km").replace("{n}", NUMERO.format(Number(v))));
const pesos = (v) => (nada(v) ? "—" : MXN0.format(Math.round(Number(v))));
const pesos2 = (v) => (nada(v) ? "—" : MXN2.format(Number(v)));

function corta(iso) {
  if (!iso) return "";
  const f = new Date(iso.slice(0, 10) + "T00:00:00");
  const meses = t("f_meses").split(",");
  return `${String(f.getDate()).padStart(2, "0")} ${meses[f.getMonth()]}`;
}

function larga(iso) {
  if (!iso) return "—";
  const f = new Date(iso.slice(0, 10) + "T00:00:00");
  const meses = t("f_meses").split(",");
  return `${String(f.getDate()).padStart(2, "0")} ${meses[f.getMonth()]} ${f.getFullYear()}`;
}

function poner(nodo, ...hijos) {
  nodo.replaceChildren(...hijos.flat().filter(Boolean));
}

function boton(texto, alPicar, clase = "claro chico") {
  return h("button", { type: "button", clase, onclick: alPicar }, texto);
}

function tabla(cabezas, filas, vacio = "lgf_vacio") {
  return h("table", { clase: "lista ctl-tabla" },
    h("thead", {}, h("tr", {}, ...cabezas.map(c => (typeof c === "string"
      ? h("th", {}, c) : h("th", { clase: c.clase }, c.texto))))),
    h("tbody", {}, ...(filas.length ? filas
      : [h("tr", {}, h("td", { colspan: String(cabezas.length), clase: "gris chico" }, t(vacio)))])));
}

function barra(pct, tono = "") {
  const ancho = Math.max(2, Math.min(100, Math.round(pct)));
  return h("div", { clase: "lgf-barra" }, h("i", { clase: tono, style: `width:${ancho}%` }));
}

/* Lo que manda el servidor cuando algo no se puede: el mensaje y, si lo
   trae, que hacer. */
function errorDe(err) {
  const d = err && err.detalle;
  if (d && typeof d === "object" && d.que_hacer) return `${d.mensaje || err.message} ${d.que_hacer}`;
  return err.message;
}

/* ------------------------------------------------------------ lo que se dice */

export function nombreDoc(tipo) {
  return t(`lgf_doc_${tipo}`);
}

export function nombreUnidad(u) {
  return u.numero_economico ? t("lgf_eco").replace("{n}", u.numero_economico) : u.placa;
}

/* Un motivo de la regla de disponibilidad, en el idioma de quien lee.
   Lo comparten la flota y la jornada. */
export function motivoTexto(m) {
  let texto = t(`lgd_${m.clave}`);
  const huecos = {
    documento: m.documento ? nombreDoc(m.documento) : "",
    vence: m.vence ? larga(m.vence) : "",
    hasta: m.hasta ? larga(m.hasta) : "",
    servicio: m.servicio || "", motivo: m.motivo || "", viaje: m.viaje || "",
    km: nada(m.km) ? "" : NUMERO.format(Number(m.km)), dias: nada(m.dias) ? "" : String(m.dias),
  };
  for (const [k, v] of Object.entries(huecos)) texto = texto.split(`{${k}}`).join(v);
  return texto.replace(/:\s*$/, "").trim();
}

function estadoDeUnidad(u) {
  const bloqueos = u.disponibilidad.motivos.filter(m => m.nivel === "bloqueo");
  const alertas = u.disponibilidad.motivos.filter(m => m.nivel === "alerta");
  const regreso = u.estado_hasta ? t("lgf_regresa").replace("{f}", corta(u.estado_hasta)) : "";
  if (u.estado === "en_viaje") {
    return [etiqueta(t("lgf_e_en_viaje"), "azul"),
            h("div", { clase: "chico gris" }, [t("lgf_a_mano"), regreso].filter(Boolean).join(" · "))];
  }
  if (u.estado === "en_taller" || u.estado === "fuera_de_servicio") {
    return [etiqueta(t(`lgf_e_${u.estado}`), u.estado === "en_taller" ? "alerta" : "grave"),
            h("div", { clase: "chico gris" }, [u.estado_motivo, regreso].filter(Boolean).join(" · "))];
  }
  if (u.clase === "remolque") {
    /* La caja no sale sola: eso no se repite en cada renglon. Lo que si
       se dice es lo que la frenaria con su tracto. */
    const otro = bloqueos.find(m => m.clave !== "remolque");
    return [etiqueta(t("lgf_e_caja"), "info"),
            otro ? h("div", { clase: "chico rojo" }, motivoTexto(otro))
              : alertas.length ? h("div", { clase: "chico ambar" }, motivoTexto(alertas[0]))
                : h("div", { clase: "chico gris" }, t("lgd_remolque"))];
  }
  /* Sin tipo no sale, pero eso es que esta por completar: se dice que
     le falta, no que tiene algo vencido. */
  const frenan = bloqueos.filter(m => !(m.clave === "sin_tipo" && u.faltas.length));
  if (frenan.length) {
    return [etiqueta(t("lgf_e_no_sale"), "grave"),
            h("div", { clase: "chico rojo" }, motivoTexto(frenan[0]))];
  }
  if (u.faltas.length) {
    return [etiqueta(t("lgf_e_por_completar"), "alerta"),
            h("div", { clase: "chico gris" }, t("lgf_falta_de").replace(
              "{que}", u.faltas.map(f => t(`lgf_falta_${f}`)).join(", ")))];
  }
  /* Lo primero que hay que saber de una libre: una alerta, un documento
     que vence pronto, uno sin capturar; y si nada, su patio. */
  const alerta = alertas.find(m => m.clave !== "documento_falta");
  const porVencer = (u.documentos || []).find(d => d.estado === "por_vencer");
  const sub = alerta ? motivoTexto(alerta)
    : porVencer ? t("lgf_doc_vence_en").replace("{d}", nombreDoc(porVencer.tipo)).replace("{n}", porVencer.dias)
      : alertas.length ? motivoTexto(alertas[0]) : null;
  return [etiqueta(t("lgf_e_libre"), "ok"),
          sub ? h("div", { clase: "chico ambar" }, sub) : h("div", { clase: "chico gris" }, u.patio || "")];
}

function proximoDe(u) {
  const p = u.proximo;
  if (p) {
    const pct = p.cada_km ? (Math.max(p.faltan_km, 0) / p.cada_km) * 100 : 0;
    if (p.estado === "vencido") {
      return [h("span", { clase: "rojo" }, t("lgf_prox_vencido").replace("{s}", p.nombre)
        .replace("{n}", NUMERO.format(-p.faltan_km))), barra(2, "grave")];
    }
    return [h("span", { clase: p.estado === "proximo" ? "ambar" : "" },
              t("lgf_prox_en").replace("{s}", p.nombre).replace("{n}", NUMERO.format(p.faltan_km))),
            barra(pct, p.estado === "proximo" ? "alerta" : "")];
  }
  if (u.clase === "unidad" && !u.tipo_id) return h("span", { clase: "gris" }, t("lgf_prox_sin_tipo"));
  if (!u.plan_n) return h("span", { clase: "gris" }, t("lgf_prox_sin_plan"));
  if (u.sin_ultimo) return h("span", { clase: "gris" }, t("lgf_prox_sin_ultimo"));
  return h("span", { clase: "gris" }, t("lgf_prox_sin_odometro"));
}

/* ================================================ la pantalla */

export async function pantallaLgFlota(main, unidadId) {
  if (unidadId) return pantallaUnidad(main, Number(unidadId));
  const pestanas = h("div", { clase: "pestanas", style: "margin:0 0 14px" });
  const zona = h("div");
  const sub = h("p", { clase: "sub" }, t("lgf_sub"));
  const irA = (clave) => { pestana = clave; pintarPestanas(); pintarVista(); };

  function pintarPestanas() {
    poner(pestanas, [["unidades", "lgf_p_unidades"], ["plan", "lgf_p_plan"],
                     ["carga", "lgf_p_carga"], ["bitacora", "lgf_p_bitacora"]]
      .map(([clave, texto]) => h("button", {
        type: "button", clase: clave === pestana ? "pestana activa" : "pestana",
        onclick: () => irA(clave),
      }, t(texto))));
  }

  async function pintarVista() {
    poner(zona, h("div", { clase: "gris chico" }, "…"));
    try {
      if (pestana === "plan") await pestanaPlan(zona);
      else if (pestana === "carga") await pestanaCarga(zona);
      else if (pestana === "bitacora") await pestanaBitacora(zona, "/lg/flota/bitacora");
      else await pestanaUnidades(zona, sub, irA);
    } catch (err) {
      poner(zona, h("div", { clase: "aviso grave" }, errorDe(err)));
    }
  }

  main.append(h("h1", {}, t("lgf_titulo")), sub, pestanas, zona);
  pintarPestanas();
  await pintarVista();
}

/* ================================================ Unidades */

function revisarla(u) {
  return u.disponibilidad.estado !== "libre" || u.faltas.length
    || (u.proximo && u.proximo.estado !== "ok")
    || u.documentos.some(d => d.estado === "por_vencer" || d.estado === "vencido");
}

function pasaFiltros(u) {
  const q = filtros.q.trim().toLowerCase();
  if (q && ![u.numero_economico, u.placa, u.marca_modelo, u.tipo]
    .some(x => (x || "").toLowerCase().includes(q))) return false;
  if (filtros.tipo === "sin" && (u.tipo_id || u.clase === "remolque")) return false;
  if (filtros.tipo === "remolque" && u.clase !== "remolque") return false;
  if (filtros.tipo && !["sin", "remolque"].includes(filtros.tipo)
      && String(u.tipo_id) !== filtros.tipo) return false;
  if (filtros.estado === "no_sale" && u.disponibilidad.estado !== "bloqueo") return false;
  if (filtros.estado === "por_completar" && !u.faltas.length) return false;
  if (["disponible", "en_viaje", "en_taller", "fuera_de_servicio"].includes(filtros.estado)
      && u.estado !== filtros.estado) return false;
  if (filtros.revisar && !revisarla(u)) return false;
  return true;
}

async function pestanaUnidades(zona, sub, irA) {
  const d = await api.get("/lg/flota");
  const vivas = d.unidades.filter(u => u.clase === "unidad").length;
  const cajas = d.unidades.length - vivas;
  if (vivas) {
    const clave = cajas === 1 ? "lgf_sub_n_caja" : cajas ? "lgf_sub_n_cajas" : "lgf_sub_n";
    sub.textContent = t(clave).replace("{c}", NUMERO.format(cajas)).replace("{n}", NUMERO.format(vivas));
  }

  if (!d.unidades.length) {
    poner(zona, h("div", { clase: "tarjeta" },
      h("h3", {}, t("lgf_sin_unidades")),
      h("p", { clase: "gris", style: "margin:0" }, t("lgf_sin_unidades_que")),
      d.puede.editar ? h("div", { style: "margin-top:12px" },
        boton(t("lgf_ir_carga"), () => irA("carga"), ""))
        : null));
    return;
  }

  const cuerpo = h("tbody");
  const pie = h("p", { clase: "chico gris", style: "margin-top:-4px" });

  function pintarFilas() {
    const vistas = d.unidades.filter(pasaFiltros);
    poner(cuerpo, vistas.map(u => h("tr", {
      clase: "clic", onclick: () => { location.hash = `#/lg/flota/${u.id}`; },
    },
      h("td", {},
        u.numero_economico ? h("b", {}, nombreUnidad(u))
          : h("b", { clase: "ambar" }, t("lgf_sin_economico")),
        " ", h("span", { clase: "placas" }, u.placa),
        h("div", { clase: "chico gris" }, [u.marca_modelo, u.anio].filter(Boolean).join(" · "))),
      h("td", {}, u.clase === "remolque" ? t("lgf_caja")
        : (u.tipo || h("span", { clase: "gris" }, t("lgf_sin_tipo")))),
      h("td", {}, ...estadoDeUnidad(u)),
      h("td", { clase: "num der", style: "white-space:nowrap" }, km(u.odometro_km),
        h("div", { clase: "chico gris" }, corta(u.odometro_fecha))),
      h("td", { style: "min-width:150px" }, proximoDe(u)),
      h("td", { clase: "num der" }, u.costo_dia ? pesos(u.costo_dia) : h("span", { clase: "gris" }, "—"),
        u.costo_dia && u.costo_completo === false
          ? h("div", { clase: "chico ambar" }, t("lgf_costo_incompleto")) : null),
      h("td", { clase: "num der gris" }, "—"),
      h("td", { clase: "num der gris" }, "—"))));
    if (!vistas.length) {
      poner(cuerpo, h("tr", {}, h("td", { colspan: "8", clase: "gris chico" }, t("lgf_nada_filtro"))));
    }
    pie.textContent = t("lgf_mostrando").replace("{n}", vistas.length)
      .replace("{total}", d.unidades.length);
  }

  const buscar = entrada("q", { type: "search", value: filtros.q, placeholder: t("lgf_buscar_ayuda"),
    oninput: (e) => { filtros.q = e.target.value; pintarFilas(); } });
  const tipos = lista("tipo", [{ valor: "", texto: t("lgf_todos") },
    ...d.tipos.map(x => ({ valor: String(x.id), texto: x.nombre })),
    { valor: "remolque", texto: t("lgf_caja") }, { valor: "sin", texto: t("lgf_sin_tipo") }],
  { onchange: (e) => { filtros.tipo = e.target.value; pintarFilas(); } });
  tipos.value = filtros.tipo;
  const estados = lista("estado", [{ valor: "", texto: t("lgf_todos") },
    ...["disponible", "en_viaje", "en_taller", "fuera_de_servicio"].map(e => ({ valor: e, texto: t(`lgf_e_${e}`) })),
    { valor: "no_sale", texto: t("lgf_e_no_sale") },
    { valor: "por_completar", texto: t("lgf_e_por_completar") }],
  { onchange: (e) => { filtros.estado = e.target.value; pintarFilas(); } });
  estados.value = filtros.estado;
  const casilla = h("input", { type: "checkbox", onchange: (e) => { filtros.revisar = e.target.checked; pintarFilas(); } });
  casilla.checked = filtros.revisar;

  const c = d.cifras;
  const cifra = (titulo, n, pie_, color = "") => h("div", {},
    h("div", { clase: "chico gris" }, t(titulo)),
    h("div", { clase: "cifra", style: color ? `color:${color}` : null }, NUMERO.format(n)),
    h("div", { clase: "chico gris" }, t(pie_)));

  poner(zona,
    h("div", { clase: "tarjeta lisa" }, h("div", { clase: "rejilla cuatro" },
      campo(t("lgf_buscar"), buscar), campo(t("lgf_tipo"), tipos), campo(t("lgf_estado"), estados),
      h("div", { clase: "campo" }, h("label", {}, " "),
        h("label", { clase: "casilla" }, casilla, " ", t("lgf_solo_revisar"))))),
    h("div", { clase: "corte" },
      cifra("lgf_c_viaje", c.en_viaje, "lgf_c_viaje_pie"),
      cifra("lgf_c_libres", c.libres, "lgf_c_libres_pie", "var(--ok)"),
      cifra("lgf_c_taller", c.taller, "lgf_c_taller_pie"),
      cifra("lgf_c_no_salen", c.no_pueden, "lgf_c_no_salen_pie", c.no_pueden ? "var(--grave)" : ""),
      cifra("lgf_c_servicio", c.servicio_proximo, "lgf_c_servicio_pie", c.servicio_proximo ? "var(--alerta)" : ""),
      cifra("lgf_c_documentos", c.documentos, "lgf_c_documentos_pie", c.documentos ? "var(--alerta)" : "")),
    h("div", { clase: "tarjeta lisa", style: "padding:0;overflow-x:auto" },
      h("table", {}, h("thead", {}, h("tr", {},
        h("th", {}, t("lgf_col_unidad")), h("th", {}, t("lgf_tipo")), h("th", {}, t("lgf_estado")),
        h("th", { clase: "der" }, t("lgf_col_odometro")), h("th", {}, t("lgf_col_proximo")),
        h("th", { clase: "der" }, t("lgf_col_costo")), h("th", { clase: "der" }, t("lgf_col_ingreso")),
        h("th", { clase: "der" }, t("lgf_col_margen")))), cuerpo)),
    pie,
    c.por_completar ? h("p", { clase: "chico ambar", style: "margin:0" },
      t("lgf_por_completar_pie").replace("{n}", c.por_completar)) : null);
  pintarFilas();
}

/* ================================================ el detalle de una unidad */

async function pantallaUnidad(main, id) {
  const marco = h("div");
  main.append(h("p", { clase: "chico", style: "margin:0 0 10px" },
    h("a", { href: "#/lg/flota", style: "color:var(--centauro);font-weight:600;text-decoration:none" },
      t("lgf_volver"))), marco);

  async function recargar(d = null) {
    try {
      const datos = d || await api.get(`/lg/flota/unidades/${id}`);
      pintarUnidad(marco, datos, recargar);
    } catch (err) {
      poner(marco, h("div", { clase: "aviso grave" }, errorDe(err)));
    }
  }
  await recargar();
}

/* Lo que quien lleva la flota tiene que atender aunque hoy no frene: el
   documento que vence en menos de 30 dias y el servicio a menos de
   2,000 km. */
function porAtender(d) {
  const docs = d.documentos.filter(x => x.estado === "por_vencer").map((x) => {
    const clave = x.dias === 0 ? "lgf_aviso_doc_0" : x.dias === 1 ? "lgf_aviso_doc_1" : "lgf_aviso_doc";
    return t(clave).replace("{d}", nombreDoc(x.tipo)).replace("{f}", larga(x.vence_en))
      .replace("{n}", x.dias);
  });
  const servicios = d.plan.filter(x => x.estado === "proximo").map(x => t("lgf_aviso_servicio")
    .replace("{s}", x.nombre).replace("{n}", NUMERO.format(x.faltan_km)));
  return [...docs, ...servicios];
}

function bandaDisponibilidad(dispo, atender = [], esCaja = false) {
  /* Que la caja sale con su tracto no se repite como si fuera un
     problema: se dice una vez, y lo demas se cuenta igual que en una
     unidad. */
  const motivos = dispo.motivos.filter(m => !(esCaja && m.clave === "remolque"));
  const frenan = motivos.filter(m => m.nivel === "bloqueo").map(motivoTexto);
  const alertan = motivos.filter(m => m.nivel === "alerta").map(motivoTexto);
  const renglon = (titulo, cosas) => (cosas.length
    ? h("div", { style: "margin-top:4px" }, h("b", {}, titulo), ` ${cosas.join(" · ")}.`) : null);
  const atiende = renglon(t("lgf_banda_por_atender"), atender);
  const marco = (tono, ...hijos) => h("div", { clase: `aviso ${tono}`.trim(), style: "margin:12px 0 2px" }, ...hijos);
  if (frenan.length) {
    return marco("grave", h("b", {}, t("lgf_banda_no")), ` ${frenan.join(" · ")}. `, t("lgf_banda_misma"),
      renglon(t("lgf_banda_alertas"), alertan), atiende);
  }
  if (esCaja) {
    return marco(alertan.length || atender.length ? "alerta" : "", h("b", {}, `${t("lgd_remolque")}.`), " ",
      t("lgf_banda_misma"), renglon(t("lgf_banda_alertas"), alertan), atiende);
  }
  if (alertan.length) {
    const n = alertan.length;
    return marco("alerta", h("b", {}, n === 1 ? t("lgf_banda_alerta_1") : t("lgf_banda_alerta").replace("{n}", n)),
      ` ${alertan.join(" · ")}. `, t("lgf_banda_misma"), atiende);
  }
  return marco(atender.length ? "alerta" : "ok", h("b", {}, t("lgf_banda_libre")), " ", t("lgf_banda_misma"), atiende);
}

function ficha(etiquetaTexto, valor) {
  return h("div", {}, h("span", { clase: "chico gris" }, etiquetaTexto), valor);
}

function pintarUnidad(marco, d, recargar) {
  const u = d.unidad;
  const puede = d.puede;
  const formas = h("div");
  const abrir = (forma) => { poner(formas, forma); formas.scrollIntoView({ block: "nearest" }); };
  const cerrar = () => poner(formas);

  const acciones = [];
  if (puede.editar) {
    acciones.push(boton(t("lgf_a_odometro"), () => abrir(formaOdometro(u, recargar, cerrar))),
                  boton(t("lgf_a_estado"), () => abrir(formaEstado(u, puede, recargar, cerrar))),
                  boton(t("lgf_a_editar"), () => abrir(formaEditar(d, recargar, cerrar))));
  } else if (puede.en_viaje && !["en_taller", "fuera_de_servicio"].includes(u.estado)) {
    acciones.push(boton(t("lgf_a_estado"), () => abrir(formaEstado(u, puede, recargar, cerrar))));
  }

  const subtitulo = [u.marca_modelo, u.anio, u.clase === "remolque" ? t("lgf_caja") : u.tipo]
    .filter(Boolean).join(" · ");
  const estado = estadoDeUnidad({ ...u, disponibilidad: d.disponibilidad, proximo: null,
                                  documentos: d.documentos });

  poner(marco,
    h("div", { clase: "tarjeta" },
      h("div", { clase: "lgf-cabeza" },
        h("div", {},
          h("h2", {}, u.numero_economico ? nombreUnidad(u) : h("span", { clase: "ambar" }, t("lgf_sin_economico")),
            " ", h("span", { clase: "placas", style: "font-size:15px;vertical-align:middle" }, u.placa)),
          h("div", { clase: "gris" }, subtitulo || "—")),
        h("div", { clase: "lgf-acciones" }, ...acciones)),
      u.baja_odoo_en ? h("div", { clase: "aviso grave", style: "margin:12px 0 2px" }, t("lgf_de_baja")) : null,
      bandaDisponibilidad(d.disponibilidad, porAtender(d), u.clase === "remolque"),
      h("div", { clase: "lgf-ficha" },
        ficha(t("lgf_estado"), estado[0]),
        ficha(t("lgf_patio"), u.patio || h("span", { clase: "gris" }, "—")),
        ficha(t("lgf_col_odometro"), h("span", {}, km(u.odometro_km),
          u.odometro_fecha ? h("span", { clase: "chico gris", style: "display:inline" }, ` · ${corta(u.odometro_fecha)}`) : null)),
        ficha(t("lgf_rendimiento_ref"), u.clase === "remolque" ? h("span", { clase: "gris" }, "—")
          : nada(u.rendimiento_ref) ? h("span", { clase: "ambar" }, t("lgf_falta"))
            : t("lgf_km_l").replace("{n}", KML.format(Number(u.rendimiento_ref)))),
        ficha(t("lgf_chasis"), u.chasis || "—"),
        ficha(t("lgf_iave"), u.iave || "—"))),
    formas,
    h("div", { clase: "lgf-tres" },
      tarjetaExpediente(d, recargar, abrir, cerrar),
      tarjetaCosto(d, recargar, abrir, cerrar),
      tarjetaRendimiento(d)),
    h("div", { clase: "lgf-dos" },
      tarjetaPlan(d),
      tarjetaServicios(d, recargar, abrir, cerrar)),
    tarjetaLlantas(d, recargar, abrir, cerrar),
    tarjetaBitacoraUnidad(u.id));
}

/* ------------------------------------------------ el expediente */

function abrirArchivo(archivoId) {
  /* Con sesion: el navegador lo pediria sin token en un enlace a secas.
     La pestana se abre al picar, antes de esperar: abierta despues, el
     navegador la toma por ventana emergente y la bloquea. */
  const pestana_ = window.open("", "_blank");
  api.imagen(`/lg/flota/archivos/${archivoId}`)
    .then((url) => { if (pestana_) pestana_.location.href = url; else window.open(url, "_blank"); })
    .catch((err) => { if (pestana_) pestana_.close(); mensaje(errorDe(err), "grave"); });
}

function verArchivo(archivoId) {
  return archivoId ? h("a", { href: "#", style: "color:var(--centauro)",
    onclick: (e) => { e.preventDefault(); e.stopPropagation(); abrirArchivo(archivoId); } },
  t("lgf_ver_archivo")) : null;
}

export function etiquetaDoc(doc) {
  if (doc.estado === "falta") return etiqueta(t("lgf_doc_falta"), "alerta");
  if (doc.estado === "vencido") return etiqueta(t("lgf_doc_vencido"), "grave");
  if (doc.estado === "por_vencer") {
    return etiqueta(t("lgf_doc_dias").replace("{n}", doc.dias), "alerta");
  }
  return etiqueta(t("lgf_doc_vigente"), "ok");
}

export function detalleDoc(doc, conDetalle = true) {
  if (doc.estado === "falta") return h("span", { clase: "chico gris" }, t("lgf_doc_sin_capturar"));
  const partes = [conDetalle ? doc.detalle : null, doc.folio,
    doc.vence_en ? t(doc.estado === "vencido" ? "lgf_vencio" : "lgf_vence").replace("{f}", larga(doc.vence_en))
      : t("lgf_sin_vencimiento")].filter(Boolean);
  return h("span", { clase: `chico ${doc.estado === "vencido" ? "rojo" : "gris"}` },
    partes.join(" · "), doc.archivo_id ? " · " : "", verArchivo(doc.archivo_id));
}

function tarjetaExpediente(d, recargar, abrir, cerrar) {
  const caja = h("div", { clase: "tarjeta lisa" }, conAyuda("h4", t("lgf_expediente"), "lgf_ayuda_expediente"));
  for (const doc of d.documentos) {
    const accion = d.puede.editar ? boton(doc.estado === "falta" ? t("lgf_capturar") : t("lgf_actualizar"),
      () => abrir(formaDocumento(d.unidad, doc, recargar, cerrar))) : null;
    caja.append(h("div", { clase: "lgf-doc" },
      h("div", {}, h("b", {}, nombreDoc(doc.tipo)), detalleDoc(doc)),
      h("div", { clase: "lgf-doc-der" }, etiquetaDoc(doc), accion)));
  }
  caja.append(h("p", { clase: "chico gris", style: "margin:4px 0 0" }, t("lgf_expediente_pie")));
  return caja;
}

/* ------------------------------------------------ el costo por dia */

/* Una parte del costo que el servidor no mando: se dice que falta. */
const SIN_PARTE = { monto: "", fuente: "falta", detalle: {} };

function lineaCosto(componente, parte) {
  const det = parte.detalle || {};
  let texto = "";
  if (parte.fuente === "falta" && det.sin_km) {
    texto = t("lgf_costo_sin_km").replace("{p}", MXN4.format(Number(det.por_km)));
  } else if (parte.fuente === "falta") texto = t("lgf_costo_falta");
  else if (parte.fuente === "tipo") texto = t("lgf_costo_del_tipo");
  else if (componente === "depreciacion") {
    texto = t("lgf_costo_dep").replace("{c}", pesos(det.compra)).replace("{a}", DECIMAL.format(Number(det.anios)));
  } else if (componente === "llantas") {
    texto = t("lgf_costo_llantas").replace("{p}", MXN4.format(Number(det.por_km)))
      .replace("{k}", DECIMAL.format(Number(det.km_dia)));
  } else if (componente === "mantenimiento" && parte.fuente === "servicios") {
    texto = t("lgf_costo_servicios").replace("{t}", pesos(det.total)).replace("{n}", det.n);
  } else if (componente === "mantenimiento" && parte.fuente === "carga") {
    texto = t("lgf_costo_carga").replace("{t}", pesos(det.anual));
  } else if (componente === "mantenimiento" && parte.fuente === "promedio_tipo") {
    texto = t("lgf_costo_promedio").replace("{t}", pesos(det.anual)).replace("{n}", det.unidades);
  } else if (!nada(det.anual)) {
    texto = t("lgf_costo_anual").replace("{t}", pesos(det.anual));
  }
  return [h("div", {}, h("span", {}, t(`lgf_comp_${componente}`)),
            h("div", { clase: `chico ${parte.fuente === "falta" ? "ambar" : "gris"}` }, texto)),
          h("div", { clase: "der" }, nada(parte.monto) ? h("span", { clase: "gris" }, "—") : pesos2(parte.monto))];
}

function tarjetaCosto(d, recargar, abrir, cerrar) {
  const vigente = d.costo;
  const base = vigente ? vigente.desglose : d.costo_hoy.desglose;
  const total = vigente ? vigente.total : d.costo_hoy.total;
  const caja = h("div", { clase: "tarjeta lisa" }, conAyuda("h4", t("lgf_costo_dia"), "lgf_ayuda_costo"));
  const kv = h("div", { clase: "lgf-kv" });
  for (const comp of ["depreciacion", "seguro", "gps", "mantenimiento", "llantas"]) {
    kv.append(...lineaCosto(comp, base[comp] || SIN_PARTE));
  }
  kv.append(h("div", { clase: "total" }, t("lgf_costo_dia")), h("div", { clase: "der total" }, pesos2(total)));
  caja.append(kv);
  if (vigente) {
    /* De donde salio este renglon: el del mes no dice nada; la carga y el
       que se completo lo dicen en el idioma de quien lee; el recalculo,
       con el porque que escribio quien lo hizo. */
    const origen = vigente.origen === "recalculo" && vigente.motivo ? ` «${vigente.motivo}»`
      : ["carga", "completo"].includes(vigente.origen) ? ` ${t(`lgf_costo_origen_${vigente.origen}`)}` : "";
    caja.append(h("p", { clase: "chico gris", style: "margin:10px 0 0" },
      t("lgf_costo_rige").replace("{f}", larga(vigente.vigente_desde)), origen));
    if (d.costo_hoy.total !== vigente.total) {
      caja.append(h("p", { clase: "chico ambar", style: "margin:6px 0 0" },
        t("lgf_costo_cambiaria").replace("{v}", pesos2(d.costo_hoy.total))));
    }
  } else {
    caja.append(h("p", { clase: "chico ambar", style: "margin:10px 0 0" }, t("lgf_costo_sin_guardar")));
  }
  if (d.puede.editar) {
    caja.append(h("div", { style: "margin-top:10px" },
      boton(t("lgf_recalcular"), () => abrir(formaRecalcular(d.unidad, recargar, cerrar)))));
  }
  return caja;
}

function tarjetaRendimiento(d) {
  const u = d.unidad;
  if (u.clase === "remolque") {
    return h("div", { clase: "tarjeta lisa" }, h("h4", {}, t("lgf_rendimiento")),
      h("p", { clase: "chico gris", style: "margin:0" }, t("lgf_rendimiento_caja")));
  }
  return h("div", { clase: "tarjeta lisa" },
    conAyuda("h4", t("lgf_rendimiento"), "lgf_ayuda_rendimiento"),
    h("div", { clase: "lgf-kv" },
      h("div", {}, h("span", {}, t("lgf_rendimiento_ref")),
        h("div", { clase: "chico gris" }, t("lgf_rendimiento_ref_pie"))),
      h("div", { clase: "der" }, nada(u.rendimiento_ref) ? h("span", { clase: "ambar" }, t("lgf_falta"))
        : t("lgf_km_l").replace("{n}", KML.format(Number(u.rendimiento_ref)))),
      h("div", {}, h("span", {}, t("lgf_rendimiento_10")),
        h("div", { clase: "chico gris" }, t("lgf_rendimiento_10_pie"))),
      h("div", { clase: "der gris" }, "—")),
    h("div", { clase: "aviso", style: "margin:12px 0 0" }, t("lgf_rendimiento_aviso")));
}

/* ------------------------------------------------ el plan y los servicios */

function tarjetaPlan(d) {
  const u = d.unidad;
  const de = u.clase === "remolque" ? t("lgf_plan_de_cajas")
    : u.tipo ? t("lgf_plan_del_tipo").replace("{t}", u.tipo) : "";
  const filas = d.plan.map((p) => {
    let toca;
    if (p.estado === "sin_ultimo") {
      toca = h("span", { clase: "chico ambar" }, t("lgf_plan_sin_ultimo"));
    } else {
      const pct = p.cada_km && !nada(p.faltan_km) ? (Math.max(p.faltan_km, 0) / p.cada_km) * 100 : 0;
      const tono = p.estado === "vencido" ? "grave" : p.estado === "proximo" ? "alerta" : "";
      const dice = nada(p.faltan_km) ? t("lgf_plan_sin_odometro")
        : p.faltan_km <= 0 ? t("lgf_plan_vencido").replace("{n}", NUMERO.format(-p.faltan_km))
          : t("lgf_plan_faltan").replace("{n}", NUMERO.format(p.faltan_km));
      toca = [km(p.toca_km),
              h("div", { clase: `chico ${tono === "grave" ? "rojo" : tono === "alerta" ? "ambar" : "gris"}` }, dice),
              barra(p.estado === "vencido" ? 2 : pct, tono)];
    }
    return h("tr", {},
      h("td", {}, p.nombre, h("div", { clase: "chico gris" }, nada(p.ultimo_km) ? t("lgf_plan_nunca")
        : t("lgf_plan_ultimo").replace("{n}", NUMERO.format(p.ultimo_km)))),
      h("td", { clase: "num lgf-nw" }, km(p.cada_km)),
      h("td", { clase: "num lgf-nw" }, toca));
  });
  return h("div", { clase: "tarjeta lisa" },
    conAyuda("h4", [t("lgf_plan"), de].filter(Boolean).join(" · "), "lgf_ayuda_plan"),
    u.clase === "unidad" && !u.tipo_id
      ? h("p", { clase: "ambar chico" }, t("lgf_plan_sin_tipo"))
      : tabla([t("lgf_servicio"), t("lgf_cada"), t("lgf_toca")], filas, "lgf_plan_vacio"),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgf_plan_pie")));
}

function tarjetaServicios(d, recargar, abrir, cerrar) {
  const filas = d.servicios.map(s => h("tr", { clase: s.anulado ? "apagado" : "" },
    h("td", { clase: "lgf-nw" }, larga(s.fecha), h("div", { clase: "chico gris" }, km(s.km))),
    h("td", {}, s.anulado ? h("s", {}, s.nombre) : s.nombre,
      h("div", { clase: "chico gris" }, [s.taller, s.factura ? t("lgf_factura_n").replace("{f}", s.factura) : null]
        .filter(Boolean).join(" · "), s.archivo_id ? " · " : "", verArchivo(s.archivo_id)),
      s.anulado ? h("div", { clase: "chico rojo" }, t("lgf_anulado").replace("{m}", s.anulado_motivo || "")) : null),
    h("td", { clase: "num der" }, pesos(s.costo),
      d.puede.editar && !s.anulado ? h("div", {}, h("a", { href: "#", clase: "chico", style: "color:var(--grave)",
        onclick: (e) => { e.preventDefault(); abrir(formaAnular(d.unidad, s, recargar, cerrar)); } },
      t("lgf_anular"))) : null)));
  return h("div", { clase: "tarjeta lisa" },
    conAyuda("h4", t("lgf_servicios"), "lgf_ayuda_servicios"),
    tabla([t("lgf_fecha"), t("lgf_servicio"), { texto: t("lgf_costo"), clase: "der" }], filas, "lgf_servicios_vacio"),
    h("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-top:12px;gap:10px" },
      h("span", { clase: "chico gris" }, t("lgf_servicios_anio").replace("{n}", d.servicios_anio.n)
        .replace("{t}", pesos(d.servicios_anio.total))),
      d.puede.editar ? boton(t("lgf_registrar_servicio"), () => abrir(formaServicio(d, recargar, cerrar)), "chico") : null));
}

/* ------------------------------------------------ las llantas */

/* Como se acomodan en el dibujo: delanteras, cada eje de atras y la
   refaccion, con un hueco entre ejes. */
function ejes(posiciones) {
  const grupos = [];
  const delantera = posiciones.filter(p => p === "DI" || p === "DD");
  if (delantera.length) grupos.push(delantera);
  const uno = posiciones.filter(p => /^1|^T/.test(p));
  if (uno.length) grupos.push(uno);
  const dos = posiciones.filter(p => /^2/.test(p));
  if (dos.length) grupos.push(dos);
  if (posiciones.includes("R")) grupos.push(["R"]);
  return grupos;
}

function tarjetaLlantas(d, recargar, abrir, cerrar) {
  const vida = d.vida_llanta_km;
  const porPos = Object.fromEntries(d.llantas.map(x => [x.posicion, x]));
  const dibujo = h("div", { clase: "lgf-llantas" });
  for (const grupo of ejes(d.llantas.map(x => x.posicion))) {
    const eje = h("div", { clase: "lgf-eje" });
    for (const pos of grupo) {
      const x = porPos[pos];
      let tono = "";
      let pie = h("span", { clase: "gris" }, t("lgf_llanta_desde"));
      if (nada(x.instalada_km)) {
        pie = h("span", { clase: "gris" }, t("lgf_llanta_sin"));
      } else if (vida && !nada(x.km) && x.km >= vida) {
        tono = "grave";
        pie = h("span", { clase: "rojo" }, t("lgf_llanta_paso"));
      } else if (vida && !nada(x.km) && x.km >= vida * 0.9) {
        tono = "alerta";
        pie = h("span", { clase: "ambar" }, t("lgf_llanta_pronto"));
      }
      eje.append(h("div", { clase: `lgf-llanta ${tono}`.trim(),
                            title: x.detalle || "" },
        h("span", { clase: "gris" }, t(`lgf_pos_${pos}`)),
        h("b", {}, nada(x.instalada_km) ? "—" : km(x.km)), pie));
    }
    dibujo.append(eje);
  }
  return h("div", { clase: "tarjeta lisa", style: "margin-top:14px" },
    conAyuda("h4", t("lgf_llantas"), "lgf_ayuda_llantas"),
    d.llantas.length ? dibujo : h("p", { clase: "ambar chico" }, t("lgf_llantas_sin_tipo")),
    h("p", { clase: "chico gris", style: "margin:10px 0" }, t("lgf_llantas_pie"),
      vida ? ` ${t("lgf_llantas_vida").replace("{n}", NUMERO.format(vida))}` : ` ${t("lgf_llantas_sin_vida")}`),
    d.puede.editar && d.llantas.length
      ? boton(t("lgf_cambiar_llanta"), () => abrir(formaLlanta(d, recargar, cerrar))) : null);
}

function tarjetaBitacoraUnidad(unidadId) {
  const caja = h("div", { clase: "tarjeta lisa", style: "margin-top:14px" },
    h("h4", {}, t("lgf_bitacora_unidad")));
  const lugar = h("div", { clase: "chico gris" }, "…");
  caja.append(lugar);
  api.get(`/lg/flota/bitacora?unidad_id=${unidadId}&idioma=${idioma()}`).then((r) => {
    if (!r.filas.length) { poner(lugar, t("lgf_bitacora_vacia")); return; }
    poner(lugar);
    lugar.className = "";
    for (const f of r.filas.slice(0, 12)) {
      lugar.append(h("div", { clase: "ctl-hist-renglon" },
        h("span", { clase: "chico gris" }, `${fecha(f.cuando)} ${hora(f.cuando)}`),
        h("span", { clase: "chico" }, f.quien || "—"), h("span", {}, f.que)));
    }
  }).catch(() => poner(lugar, "—"));
  return caja;
}

/* ================================================ las formas

   Se abren debajo de la cabeza de la unidad, una a la vez, como en los
   bocetos. Lo que decide si se puede lo dice el servidor; aqui solo se
   deja escribir. */

function marcoForma(titulo, u, ...hijos) {
  return h("div", { clase: "tarjeta", style: "max-width:640px" },
    h("h3", {}, `${titulo} · ${nombreUnidad(u)}`), ...hijos);
}

function guardando(botonGuardar, accion) {
  return async () => {
    botonGuardar.disabled = true;
    try { await accion(); } finally { botonGuardar.disabled = false; }
  };
}

function formaEstado(u, puede, recargar, cerrar) {
  const opciones = puede.editar ? ["disponible", "en_viaje", "en_taller", "fuera_de_servicio"]
    : ["disponible", "en_viaje"];
  const estado = lista("estado", opciones.map(e => ({ valor: e, texto: t(`lgf_e_${e}`) })));
  estado.value = u.estado;
  const motivo = h("textarea", { rows: "3", placeholder: t("lgf_motivo_taller_ayuda") });
  const hasta = entrada("hasta", { type: "date", value: u.estado_hasta || "" });
  const error = h("div");
  const guardar = h("button", { type: "button" }, t("lgf_guardar"));
  guardar.onclick = guardando(guardar, async () => {
    poner(error);
    try {
      const d = await api.post(`/lg/flota/unidades/${u.id}/estado`, {
        estado: estado.value, motivo: motivo.value.trim() || null,
        hasta: estado.value === "disponible" ? null : (hasta.value || null) });
      mensaje(t("lgf_listo"));
      cerrar();
      recargar(d);
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
  });
  return marcoForma(t("lgf_a_estado"), u, error,
    campo(t("lgf_estado"), estado), campo(t("lgf_motivo"), motivo), campo(t("lgf_regresa_aprox"), hasta),
    h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgf_estado_pie")));
}

function formaOdometro(u, recargar, cerrar) {
  const kmEntrada = entrada("km", { inputmode: "numeric", placeholder: t("lgf_km_ayuda") });
  const cuando = entrada("fecha", { type: "date", value: hoyLocal() });
  const motivo = h("textarea", { rows: "2" });
  const campoMotivo = campo(t("lgf_motivo"), motivo);
  campoMotivo.hidden = true;
  const error = h("div");
  const guardar = h("button", { type: "button" }, t("lgf_guardar"));
  guardar.onclick = guardando(guardar, async () => {
    poner(error);
    try {
      const d = await api.post(`/lg/flota/unidades/${u.id}/odometro`, {
        km: kmEntrada.value.replace(/[,\s]/g, ""), fecha: cuando.value || null,
        motivo: motivo.value.trim() || null });
      mensaje(t("lgf_listo"));
      cerrar();
      recargar(d);
    } catch (err) {
      /* Menor que la anterior: el servidor pide el porque. */
      campoMotivo.hidden = false;
      poner(error, h("div", { clase: "aviso alerta" }, errorDe(err)));
    }
  });
  return marcoForma(t("lgf_a_odometro"), u, h("div", { clase: "rejilla dos" },
    campo(t("lgf_col_odometro"), kmEntrada), campo(t("lgf_fecha_lectura"), cuando)),
  error, campoMotivo, h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")),
  h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgf_odometro_pie")));
}

function formaEditar(d, recargar, cerrar) {
  const u = d.unidad;
  const tipos = (d.tipos || []);
  /* Como se escriben: «820000», «0.65» y «7», no «820000.00», «0.6500» y «7.00». */
  const sinCeros = (v) => (nada(v) ? "" : String(Number(v)));
  const valores = { numero_economico: u.numero_economico || "", rendimiento_ref: sinCeros(u.rendimiento_ref),
                    ...Object.fromEntries(Object.entries(d.costos).map(([k, v]) => [k, sinCeros(v)])) };
  const control = {};
  const numero = (nombre, ayuda = "") => {
    control[nombre] = entrada(nombre, { value: valores[nombre], inputmode: "decimal", placeholder: ayuda });
    return control[nombre];
  };
  control.numero_economico = entrada("numero_economico", { value: valores.numero_economico,
                                                           placeholder: t("lgf_eco_ayuda") });
  const tipo = lista("tipo_id", [{ valor: "", texto: t("lgf_sin_tipo") },
    ...tipos.map(x => ({ valor: String(x.id), texto: x.nombre }))]);
  tipo.value = u.tipo_id ? String(u.tipo_id) : "";
  const patio = lista("patio_id", [{ valor: "", texto: "—" },
    ...(d.patios || []).map(x => ({ valor: String(x.id), texto: x.nombre }))]);
  patio.value = u.patio_id ? String(u.patio_id) : "";
  const error = h("div");
  const guardar = h("button", { type: "button" }, t("lgf_guardar"));
  guardar.onclick = guardando(guardar, async () => {
    poner(error);
    const datos = { patio_id: patio.value || null };
    if (u.clase === "unidad") datos.tipo_id = tipo.value || null;
    for (const [k, c] of Object.entries(control)) datos[k] = c.value.replace(/,/g, "").trim() || null;
    try {
      const nuevo = await api.patch(`/lg/flota/unidades/${u.id}`, datos);
      mensaje(t("lgf_listo"));
      cerrar();
      recargar({ ...nuevo, puede: d.puede, tipos: d.tipos, patios: d.patios });
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
  });
  return marcoForma(t("lgf_a_editar"), u, error,
    h("div", { clase: "rejilla dos" },
      campo(t("lgf_economico"), control.numero_economico),
      u.clase === "unidad" ? campo(t("lgf_tipo"), tipo) : null,
      u.clase === "unidad" ? campo(t("lgf_rendimiento_ref_kml"), numero("rendimiento_ref", "7.0")) : null,
      campo(t("lgf_patio"), patio)),
    h("h4", { clase: "grupo" }, t("lgf_costos_de_la_unidad")),
    h("p", { clase: "chico gris", style: "margin:0 0 8px" }, t("lgf_costos_pie")),
    h("div", { clase: "rejilla dos" },
      campo(t("lgf_f_valor_compra"), numero("valor_compra")),
      campo(t("lgf_f_anios_vida"), numero("anios_vida")),
      campo(t("lgf_f_seguro_anual"), numero("seguro_anual")),
      campo(t("lgf_f_tenencia_anual"), numero("tenencia_anual")),
      campo(t("lgf_f_verificacion_anual"), numero("verificacion_anual")),
      campo(t("lgf_f_gps_anual"), numero("gps_anual")),
      campo(t("lgf_f_llantas_por_km"), numero("llantas_por_km")),
      campo(t("lgf_f_mantenimiento_anual"), numero("mantenimiento_anual"))),
    h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")));
}

function formaDocumento(u, doc, recargar, cerrar) {
  const folio = entrada("folio", { value: doc.folio || "" });
  const detalle = entrada("detalle", { value: doc.detalle || "", placeholder: t("lgf_doc_detalle_ayuda") });
  const vence = entrada("vence_en", { type: "date", value: doc.vence_en || "" });
  const archivo = entrada("archivo", { type: "file", accept: "application/pdf,image/*" });
  const error = h("div");
  const guardar = h("button", { type: "button" }, t("lgf_guardar"));
  guardar.onclick = guardando(guardar, async () => {
    poner(error);
    try {
      const d = await api.formulario(`/lg/flota/unidades/${u.id}/documentos`, {
        tipo: doc.tipo, folio: folio.value.trim() || null, detalle: detalle.value.trim() || null,
        vence_en: vence.value || null, archivo: archivo.files[0] || null });
      mensaje(t("lgf_listo"));
      cerrar();
      recargar(d);
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
  });
  return marcoForma(nombreDoc(doc.tipo), u, error,
    h("div", { clase: "rejilla dos" }, campo(t("lgf_folio"), folio), campo(t("lgf_doc_detalle"), detalle),
      campo(t("lgf_vence_en"), vence), campo(t("lgf_archivo"), archivo)),
    h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgf_doc_pie")));
}

function formaServicio(d, recargar, cerrar) {
  const u = d.unidad;
  const cual = lista("plan_id", [...d.plan.map(p => ({ valor: String(p.plan_id), texto: p.nombre })),
    { valor: "", texto: t("lgf_otro_servicio") }]);
  const nombre = entrada("nombre", { placeholder: t("lgf_otro_ayuda") });
  const campoNombre = campo(t("lgf_que_se_hizo"), nombre);
  const mostrar = () => { campoNombre.hidden = !!cual.value; };
  cual.onchange = mostrar;
  const cuando = entrada("fecha", { type: "date", value: hoyLocal() });
  const kmEntrada = entrada("km", { inputmode: "numeric", value: nada(u.odometro_km) ? "" : NUMERO.format(u.odometro_km) });
  const costo = entrada("costo", { inputmode: "decimal", placeholder: "0.00" });
  const taller = entrada("taller");
  const factura = entrada("factura");
  const archivo = entrada("archivo", { type: "file", accept: "application/pdf,image/*" });
  const error = h("div");
  const guardar = h("button", { type: "button" }, t("lgf_guardar"));
  guardar.onclick = guardando(guardar, async () => {
    poner(error);
    try {
      const r = await api.formulario(`/lg/flota/unidades/${u.id}/servicios`, {
        plan_id: cual.value || null, nombre: cual.value ? null : (nombre.value.trim() || null),
        fecha: cuando.value, km: kmEntrada.value.replace(/[,\s]/g, "") || null,
        costo: costo.value.replace(/[$,\s]/g, ""), taller: taller.value.trim() || null,
        factura: factura.value.trim() || null, archivo: archivo.files[0] || null });
      mensaje(t("lgf_listo"));
      cerrar();
      recargar(r);
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
  });
  mostrar();
  return marcoForma(t("lgf_registrar_servicio"), u, error,
    h("div", { clase: "rejilla dos" }, campo(t("lgf_servicio"), cual), campo(t("lgf_fecha"), cuando)),
    campoNombre,
    h("div", { clase: "rejilla dos" }, campo(t("lgf_col_odometro"), kmEntrada), campo(t("lgf_costo"), costo)),
    campo(t("lgf_taller"), taller),
    h("div", { clase: "rejilla dos" }, campo(t("lgf_factura"), factura), campo(t("lgf_archivo"), archivo)),
    h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgf_servicio_pie")));
}

function formaAnular(u, s, recargar, cerrar) {
  const motivo = h("textarea", { rows: "2" });
  const error = h("div");
  const guardar = h("button", { type: "button", clase: "peligro" }, t("lgf_anular"));
  guardar.onclick = guardando(guardar, async () => {
    poner(error);
    try {
      const d = await api.post(`/lg/flota/servicios/${s.id}/anular`, { motivo: motivo.value.trim() });
      mensaje(t("lgf_listo"));
      cerrar();
      recargar(d);
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
  });
  return marcoForma(t("lgf_anular_servicio").replace("{s}", s.nombre), u, error,
    campo(t("lgf_motivo"), motivo),
    h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgf_anular_pie")));
}

function formaRecalcular(u, recargar, cerrar) {
  const motivo = h("textarea", { rows: "2", placeholder: t("lgf_recalcular_ayuda") });
  const error = h("div");
  const guardar = h("button", { type: "button" }, t("lgf_recalcular"));
  guardar.onclick = guardando(guardar, async () => {
    poner(error);
    try {
      const d = await api.post(`/lg/flota/unidades/${u.id}/costo`, { motivo: motivo.value.trim() });
      mensaje(t("lgf_listo"));
      cerrar();
      recargar(d);
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
  });
  return marcoForma(t("lgf_recalcular"), u, error, campo(t("lgf_motivo"), motivo),
    h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgf_recalcular_pie")));
}

function formaLlanta(d, recargar, cerrar) {
  const u = d.unidad;
  const pos = lista("posicion", d.llantas.map(x => ({ valor: x.posicion, texto: t(`lgf_pos_${x.posicion}`) })));
  const kmEntrada = entrada("km", { inputmode: "numeric", value: nada(u.odometro_km) ? "" : NUMERO.format(u.odometro_km) });
  const cuando = entrada("fecha", { type: "date", value: hoyLocal() });
  const detalle = entrada("detalle", { placeholder: t("lgf_llanta_detalle_ayuda") });
  const costo = entrada("costo", { inputmode: "decimal" });
  const error = h("div");
  const guardar = h("button", { type: "button" }, t("lgf_guardar"));
  guardar.onclick = guardando(guardar, async () => {
    poner(error);
    try {
      const r = await api.post(`/lg/flota/unidades/${u.id}/llantas`, {
        posicion: pos.value, km: kmEntrada.value.replace(/[,\s]/g, ""), fecha: cuando.value || null,
        detalle: detalle.value.trim() || null, costo: costo.value.replace(/[$,\s]/g, "") || null });
      mensaje(t("lgf_listo"));
      cerrar();
      recargar(r);
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
  });
  return marcoForma(t("lgf_cambiar_llanta"), u, error,
    h("div", { clase: "rejilla dos" }, campo(t("lgf_posicion"), pos), campo(t("lgf_km_instalada"), kmEntrada),
      campo(t("lgf_fecha"), cuando), campo(t("lgf_costo"), costo)),
    campo(t("lgf_llanta_detalle"), detalle),
    h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")));
}

/* ================================================ Plan preventivo */

async function pestanaPlan(zona) {
  const d = await api.get("/lg/flota/plan");
  const recargar = () => pestanaPlan(zona).catch(err => mensaje(errorDe(err), "grave"));

  function tarjeta(titulo, renglones, clase, tipo = null) {
    const filas = renglones.map(p => h("tr", { clase: p.activo ? "" : "apagado" },
      h("td", {}, p.nombre), h("td", { clase: "num" }, km(p.cada_km)),
      h("td", { clase: "num der" }, nada(p.costo_aprox) ? "—" : pesos(p.costo_aprox)),
      h("td", { clase: "der" }, d.puede.editar ? boton(p.activo ? t("lgf_quitar") : t("lgf_volver_a_poner"),
        async () => {
          try {
            await api.patch(`/lg/flota/plan/${p.id}`, { activo: !p.activo });
            recargar();
          } catch (err) { mensaje(errorDe(err), "grave"); }
        }) : null)));
    const caja = h("div", { clase: "tarjeta lisa" }, h("h4", {}, titulo));
    if (tipo) {
      const cambiar = d.puede.editar ? [" · ", h("a", { href: "#", style: "color:var(--centauro)",
        onclick: (e) => { e.preventDefault(); caja.append(formaTipo(tipo, recargar)); } },
      t("lgf_cambiar"))] : [];
      caja.append(h("p", { clase: "chico gris", style: "margin:-6px 0 10px" },
        tipo.llantas ? t("lgf_tipo_llantas").replace("{n}", tipo.llantas) : t("lgf_tipo_sin_llantas"),
        " · ", tipo.vida_llanta_km ? t("lgf_tipo_vida").replace("{n}", NUMERO.format(tipo.vida_llanta_km))
          : t("lgf_tipo_sin_vida"), ...cambiar));
    }
    caja.append(tabla([t("lgf_servicio"), t("lgf_cada"), { texto: t("lgf_costo_aprox"), clase: "der" }, ""],
                      filas, "lgf_plan_vacio"));
    if (d.puede.editar) caja.append(formaPlan(clase, tipo, recargar));
    return caja;
  }

  poner(zona,
    h("p", { clase: "gris", style: "margin:0 0 12px" }, t("lgf_plan_explica")),
    h("div", { clase: "lgf-dos", style: "grid-template-columns:minmax(0,1fr) minmax(0,1fr)" },
      ...d.tipos.map(x => tarjeta(x.nombre, x.plan, "unidad", x)),
      tarjeta(t("lgf_caja"), d.remolque, "remolque")));
}

function formaPlan(clase, tipo, recargar) {
  const nombre = entrada("nombre", { placeholder: t("lgf_plan_nombre_ayuda") });
  const cada = entrada("cada_km", { inputmode: "numeric", placeholder: "10000" });
  const costo = entrada("costo_aprox", { inputmode: "decimal", placeholder: "0.00" });
  const guardar = h("button", { type: "button", clase: "chico" }, t("lgf_agregar"));
  guardar.onclick = guardando(guardar, async () => {
    try {
      await api.post("/lg/flota/plan", { clase, tipo_id: tipo ? tipo.id : null,
        nombre: nombre.value.trim(), cada_km: cada.value.replace(/[,\s]/g, ""),
        costo_aprox: costo.value.replace(/[$,\s]/g, "") || null });
      mensaje(t("lgf_listo"));
      recargar();
    } catch (err) { mensaje(errorDe(err), "grave"); }
  });
  return h("div", { clase: "lgf-agregar" },
    campo(t("lgf_servicio"), nombre), campo(t("lgf_cada_km"), cada), campo(t("lgf_costo_aprox"), costo),
    h("div", { clase: "campo" }, h("label", {}, " "), guardar));
}

function formaTipo(tipo, recargar) {
  const llantas = lista("llantas", [{ valor: "", texto: "—" }, ...[4, 6, 10].map(n => ({ valor: String(n), texto: String(n) }))]);
  llantas.value = tipo.llantas ? String(tipo.llantas) : "";
  const vida = entrada("vida", { inputmode: "numeric", value: tipo.vida_llanta_km ?? "" });
  const guardar = h("button", { type: "button", clase: "chico" }, t("lgf_guardar"));
  guardar.onclick = guardando(guardar, async () => {
    try {
      await api.patch(`/lg/flota/tipos/${tipo.id}`, { llantas: llantas.value || null,
        vida_llanta_km: vida.value.replace(/[,\s]/g, "") || null });
      mensaje(t("lgf_listo"));
      recargar();
    } catch (err) { mensaje(errorDe(err), "grave"); }
  });
  return h("div", { clase: "lgf-agregar" }, campo(t("lgf_tipo_llantas_campo"), llantas),
    campo(t("lgf_tipo_vida_campo"), vida), h("div", { clase: "campo" }, h("label", {}, " "), guardar));
}

/* ================================================ Carga inicial */

function resumenOdoo(o) {
  if (!o) return t("lgf_odoo_nunca");
  return t("lgf_odoo_ultima").replace("{f}", larga(fechaLocal(new Date(o.hecha_en)))).replace("{h}", hora(o.hecha_en))
    .replace("{n}", o.leidos).replace("{a}", o.altas).replace("{c}", o.cambios).replace("{b}", o.bajas);
}

/* La lectura de Odoo, la de las unidades y la de los operadores: ensayo
   primero, y aplicar con lo que dijo el ensayo a la vista. */
export function tarjetaOdoo({ titulo, explica, ruta, ultima, puede, renglon, alAplicar }) {
  const zonaRes = h("div");
  const resumen = h("p", { clase: "chico gris", style: "margin:0 0 10px" }, resumenOdoo(ultima));
  const caja = h("div", { clase: "tarjeta" }, h("h3", {}, titulo),
    h("p", { clase: "gris", style: "margin:0 0 10px" }, explica), resumen, zonaRes);
  async function leer(aplicar) {
    poner(zonaRes, h("div", { clase: "gris chico" }, "…"));
    try {
      const r = await api.post(ruta, { aplicar });
      pintar(r, aplicar);
      if (aplicar && !r.detenida) {
        /* La que se acaba de guardar ya es la ultima lectura. */
        resumen.textContent = resumenOdoo({ hecha_en: new Date().toISOString(), leidos: r.leidos,
          altas: r.altas.length, cambios: r.cambios.length, bajas: r.bajas.length });
      }
      if (aplicar && alAplicar) alAplicar(r);
    } catch (err) { poner(zonaRes, h("div", { clase: "aviso grave" }, errorDe(err))); }
  }
  function grupo(clave, filas) {
    if (!filas || !filas.length) return null;
    return h("div", { style: "margin:6px 0" }, h("b", {}, t(clave).replace("{n}", filas.length)), " ",
      h("span", { clase: "chico gris" }, filas.slice(0, 40).map(renglon).join(" · "),
        filas.length > 40 ? ` · +${filas.length - 40}` : ""));
  }
  function pintar(r, aplicado) {
    if (r.detenida) {
      poner(zonaRes, h("div", { clase: "aviso grave" }, t("lgf_odoo_detenida")));
      return;
    }
    poner(zonaRes,
      h("div", { clase: `aviso ${aplicado ? "ok" : "alerta"}` },
        h("b", {}, t(aplicado ? "lgf_odoo_aplicado" : "lgf_odoo_ensayo").replace("{n}", r.leidos))),
      grupo("lgf_odoo_altas", r.altas), grupo("lgf_odoo_vinculadas", r.vinculadas),
      grupo("lgf_odoo_cambios", r.cambios), grupo("lgf_odoo_bajas", r.bajas),
      grupo("lgf_odoo_fuera", r.fuera), grupo("lgf_odoo_pendientes", r.pendientes),
      h("p", { clase: "chico gris" }, t("lgf_odoo_sin_cambio").replace("{n}", r.sin_cambio),
        r.otros ? ` ${t("lgf_odoo_otros").replace("{n}", r.otros)}` : ""),
      !aplicado && puede ? h("button", { type: "button", onclick: () => leer(true) }, t("lgf_odoo_aplicar")) : null);
  }
  if (puede) caja.append(h("div", { clase: "lgf-acciones", style: "margin-top:8px" },
    boton(t("lgf_odoo_ensayo_boton"), () => leer(false))));
  return caja;
}

async function pestanaCarga(zona) {
  const d = await api.get("/lg/flota");
  const puede = d.puede.editar;
  const resultado = h("div");
  const archivo = h("input", { type: "file", accept: ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               style: "display:none" });
  const nombreArchivo = h("div", {}, h("b", {}, t("lgf_excel_nombre")),
    h("div", { clase: "chico gris" }, t("lgf_excel_ninguno")));
  /* Lo que se sabe del archivo: su tamano y en que va. */
  const comoVa = h("div", { clase: "chico gris" });
  const tamano = () => Math.ceil(archivo.files[0].size / 1024);

  async function revisar(aplicar) {
    const f = archivo.files[0];
    if (!f) return;
    comoVa.textContent = t("lgf_excel_subido").replace("{k}", tamano());
    poner(resultado, h("div", { clase: "gris chico" }, "…"));
    let como = "lgf_excel_revisado";
    try {
      const r = await api.formulario("/lg/flota/carga", { archivo: f, aplicar: aplicar ? "true" : "false" });
      if (r.cargado) como = "lgf_excel_ya_cargado";
      pintarResultado(r);
    } catch (err) { poner(resultado, h("div", { clase: "aviso grave" }, errorDe(err))); }
    comoVa.textContent = t(como).replace("{k}", tamano());
  }

  function pintarResultado(r) {
    if (r.cargado) {
      poner(resultado, h("div", { clase: "aviso ok" }, h("b", {}, t("lgf_excel_cargado")
        .replace("{u}", r.unidades).replace("{p}", r.plan))));
      return;
    }
    const sobran = Object.entries(r.sin_columna || {}).map(([hoja, cols]) =>
      h("p", { clase: "chico ambar", style: "margin:6px 0" },
        t("lgf_excel_sin_columna").replace("{h}", hoja).replace("{c}", cols.join(", "))));
    if (!r.ok) {
      const renglones = new Set(r.errores.map(e => `${e.hoja}:${e.renglon}`)).size;
      poner(resultado,
        h("div", { clase: "aviso grave" }, h("b", {}, renglones === 1 ? t("lgf_excel_no_uno")
          : t("lgf_excel_no").replace("{n}", renglones)), " ", t("lgf_excel_no_que")),
        tabla([t("lgf_excel_hoja"), t("lgf_excel_renglon"), t("lgf_excel_columna"), t("lgf_excel_que")],
          r.errores.map(e => h("tr", {}, h("td", {}, e.hoja), h("td", { clase: "num" }, e.renglon ?? "—"),
            h("td", {}, e.columna || "—"), h("td", {}, e.que)))),
        ...sobran);
      return;
    }
    poner(resultado,
      h("div", { clase: "aviso ok" }, h("b", {}, t("lgf_excel_bien")), " ",
        t("lgf_excel_bien_que").replace("{u}", r.unidades).replace("{p}", r.plan)),
      ...sobran,
      h("button", { type: "button", onclick: () => revisar(true) },
        t("lgf_excel_cargar").replace("{u}", r.unidades)));
  }

  archivo.onchange = () => {
    const f = archivo.files[0];
    if (!f) return;
    poner(nombreArchivo, h("b", {}, f.name), comoVa);
    revisar(false);
  };

  poner(zona,
    tarjetaOdoo({ titulo: t("lgf_odoo_titulo"), explica: t("lgf_odoo_explica"), ruta: "/lg/flota/odoo",
                  ultima: d.odoo, puede,
                  renglon: (x) => [x.placa, x.categoria || x.categoria_odoo || null, x.motivo || null]
                    .filter(Boolean).join(" ") }),
    h("div", { clase: "tarjeta" },
      h("h3", {}, t("lgf_excel_titulo")),
      h("p", { clase: "gris", style: "margin:0 0 12px" }, t("lgf_excel_explica")),
      puede ? h("div", { clase: "lgf-subir" }, nombreArchivo, archivo,
        h("button", { type: "button", clase: "claro", onclick: () => archivo.click() }, t("lgf_excel_elegir")))
        : h("p", { clase: "chico gris" }, t("lgf_excel_solo_flota")),
      resultado,
      h("h4", { clase: "grupo" }, t("lgf_excel_columnas")),
      h("p", { clase: "chico gris", style: "margin:0" }, t("lgf_excel_columnas_que"))));
}

/* ================================================ Bitacora */

export async function pestanaBitacora(zona, ruta, pagina = 1) {
  const r = await api.get(`${ruta}?pagina=${pagina}&idioma=${idioma()}`);
  const paginas = Math.max(1, Math.ceil(r.total / r.por_pagina));
  poner(zona,
    h("div", { clase: "tarjeta lisa", style: "padding:0" },
      tabla([t("lgf_cuando"), t("lgf_quien"), t("lgf_que")],
        r.filas.map(f => h("tr", {},
          h("td", { clase: "lgf-nw" }, fecha(f.cuando), h("div", { clase: "chico gris" }, hora(f.cuando))),
          h("td", {}, f.quien || "—"), h("td", {}, f.que))), "lgf_bitacora_vacia")),
    paginas > 1 ? h("div", { clase: "lgf-acciones" },
      pagina > 1 ? boton(t("lgf_anteriores"), () => pestanaBitacora(zona, ruta, pagina - 1)) : null,
      h("span", { clase: "chico gris" }, t("lgf_pagina").replace("{n}", pagina).replace("{de}", paginas)),
      pagina < paginas ? boton(t("lgf_siguientes"), () => pestanaBitacora(zona, ruta, pagina + 1)) : null) : null);
}

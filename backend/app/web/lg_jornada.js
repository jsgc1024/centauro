/* La jornada de los operadores de Logistica, AI/LG (seccion 151).

   Quien se presento a trabajar. Cada operador marca su inicio de jornada
   en su app, LG Connect, dentro de la geocerca del patio; esa marca dice
   quien esta libre para asignar hoy y cuenta los dias activos de lunes a
   viernes para el bono de movilidad (5 de 5). Cinco pestanas, como en los
   bocetos aprobados el 3 de octubre: Hoy, Semana, Por validar,
   Operadores y Bitacora.

   La Central valida o rechaza la marca hecha fuera del patio, con su
   justificacion; la gerencia de Logistica y quien lleva la flota dan el
   codigo de LG Connect, capturan la licencia y marcan a mano el «en
   viaje» mientras los viajes sigan en Tango. Si un operador puede salir
   lo dice el servidor con la misma regla de la flota. */
import { api } from "./api.js";
import { campo, conAyuda, entrada, etiqueta, fechaLocal, h, hora, hoyLocal, lista,
         mensaje } from "./util.js";
import { t } from "./idioma.js";
import { detalleDoc, etiquetaDoc, motivoTexto, pestanaBitacora,
         tarjetaOdoo } from "./lg_flota.js";

let pestana = "hoy";
let dia = null;           // el dia que se mira en Hoy; nulo es hoy
let lunes = null;         // la semana que se mira; nula es la de hoy
const filtro = { q: "", patio: "" };

const NUMERO = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 });
const DECIMAL = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 1 });
const nada = (v) => v === null || v === undefined || v === "";

function poner(nodo, ...hijos) {
  nodo.replaceChildren(...hijos.flat().filter(Boolean));
}

function boton(texto, alPicar, clase = "claro chico") {
  return h("button", { type: "button", clase, onclick: alPicar }, texto);
}

function errorDe(err) {
  const d = err && err.detalle;
  if (d && typeof d === "object" && d.que_hacer) return `${d.mensaje || err.message} ${d.que_hacer}`;
  return err.message;
}

function larga(iso) {
  if (!iso) return "—";
  const f = new Date(iso.slice(0, 10) + "T00:00:00");
  const meses = t("f_meses").split(",");
  return `${String(f.getDate()).padStart(2, "0")} ${meses[f.getMonth()]} ${f.getFullYear()}`;
}

function mesAnio(iso) {
  const f = new Date(iso.slice(0, 10) + "T00:00:00");
  return `${t("f_meses").split(",")[f.getMonth()]} ${f.getFullYear()}`;
}

/* «a 40 m» o «a 1.2 km»: lo que se lee de un vistazo. */
function distancia(m) {
  if (nada(m)) return "";
  return m < 1000 ? t("lgj_a_m").replace("{n}", NUMERO.format(m))
    : t("lgj_a_km").replace("{n}", DECIMAL.format(m / 1000));
}

function antiguedad(a) {
  if (!a) return t("lgj_sin_ingreso");
  if (a.anios >= 1) return t(a.anios === 1 ? "lgj_anio" : "lgj_anios").replace("{n}", a.anios);
  return t(a.meses === 1 ? "lgj_mes" : "lgj_meses").replace("{n}", a.meses);
}

/* ================================================ la pantalla */

export async function pantallaLgJornada(main) {
  const pestanas = h("div", { clase: "pestanas", style: "margin:0 0 14px" });
  const zona = h("div");
  let porValidar = 0;

  const irA = (clave) => { pestana = clave; pintarPestanas(); pintarVista(); };
  const contar = (n) => { if (n !== porValidar) { porValidar = n; pintarPestanas(); } };

  function pintarPestanas() {
    poner(pestanas, [["hoy", t("lgj_p_hoy")], ["semana", t("lgj_p_semana")],
                     ["validar", porValidar ? t("lgj_p_validar_n").replace("{n}", porValidar) : t("lgj_p_validar")],
                     ["operadores", t("lgj_p_operadores")], ["bitacora", t("lgf_p_bitacora")]]
      .map(([clave, texto]) => h("button", {
        type: "button", clase: clave === pestana ? "pestana activa" : "pestana",
        onclick: () => irA(clave),
      }, texto)));
  }

  async function pintarVista() {
    poner(zona, h("div", { clase: "gris chico" }, "…"));
    try {
      if (pestana === "semana") await pestanaSemana(zona, contar);
      else if (pestana === "validar") await pestanaValidar(zona, contar);
      else if (pestana === "operadores") await pestanaOperadores(zona, contar);
      else if (pestana === "bitacora") await pestanaBitacora(zona, "/lg/jornada/bitacora");
      else await pestanaHoy(zona, contar);
    } catch (err) {
      poner(zona, h("div", { clase: "aviso grave" }, errorDe(err)));
    }
  }

  main.append(h("h1", {}, t("lgj_titulo")), h("p", { clase: "sub" }, t("lgj_sub")), pestanas, zona);
  pintarPestanas();
  await pintarVista();
}

/* ================================================ Hoy */

function situacionDe(o) {
  const m = o.marca;
  const donde = m ? (m.dentro ? [m.patio, distancia(m.distancia_m)].filter(Boolean).join(", ")
    : m.patio ? t("lgj_fuera_de").replace("{d}", distancia(m.distancia_m)).replace("{p}", m.patio)
      : t("lgj_sin_punto")) : "";
  const cuando = m ? hora(m.marcada_en) : "";
  if (o.situacion === "presente") {
    return [etiqueta(t("lgj_presente"), "ok"), h("div", { clase: "chico gris" }, `${cuando} · ${donde}`)];
  }
  if (o.situacion === "por_validar") {
    return [etiqueta(t("lgj_por_validar"), "alerta"), h("div", { clase: "chico gris" }, `${cuando} · ${donde}`)];
  }
  if (o.situacion === "en_viaje") {
    return [etiqueta(t("lgj_en_viaje"), "azul"), h("div", { clase: "chico gris" },
      [t("lgj_a_mano"), o.en_viaje ? t("lgj_hasta").replace("{f}", larga(o.en_viaje.hasta)) : null]
        .filter(Boolean).join(" · "))];
  }
  if (o.situacion === "rechazada") {
    return [etiqueta(t("lgj_rechazada"), "grave"),
            h("div", { clase: "chico gris" }, `${cuando} · ${m.justificacion || ""}`)];
  }
  return [etiqueta(t("lgj_ausente")), h("div", { clase: "chico gris" }, t("lgj_sin_marca"))];
}

function licenciaDe(l) {
  if (l.estado === "falta") return h("span", { clase: "ambar" }, t("lgj_licencia_falta"));
  const vence = l.vence_en ? (l.estado === "vencido" ? t("lgf_vencio") : t("lgf_vence"))
    .replace("{f}", larga(l.vence_en)) : t("lgf_sin_vencimiento");
  const tono = l.estado === "vencido" ? "rojo" : l.estado === "por_vencer" ? "ambar" : "gris";
  return [l.detalle || t("lgj_licencia"), h("div", { clase: `chico ${tono}` }, vence,
    l.estado === "por_vencer" ? ` · ${t("lgj_en_dias").replace("{n}", l.dias)}` : "")];
}

function puedeSalir(o) {
  if (o.situacion === "en_viaje") return h("span", { clase: "chico gris" }, t("lgj_ya_va"));
  const d = o.disponibilidad;
  if (!d) return h("span", { clase: "gris" }, "—");
  if (d.estado === "bloqueo") {
    return [etiqueta(t("lgj_no"), "grave"), h("div", { clase: "chico gris" }, motivoTexto(d.motivos[0]))];
  }
  if (d.estado === "alerta") {
    return [etiqueta(t("lgj_si"), "ok"), h("div", { clase: "chico ambar" },
      t("lgj_con_alerta").replace("{m}", motivoTexto(d.motivos[0])))];
  }
  return etiqueta(t("lgj_si"), "ok");
}

async function pestanaHoy(zona, contar) {
  const d = await api.get(dia ? "/lg/jornada/dia?fecha=" + dia : "/lg/jornada/dia");
  contar(d.por_validar);
  const esHoy = d.fecha === d.hoy;
  const cuerpo = h("tbody");
  const pie = h("p", { clase: "chico gris", style: "margin-top:-4px" });

  const patios = [...new Set(d.operadores.map(o => o.marca && o.marca.patio).filter(Boolean))];

  function pintarFilas() {
    const q = filtro.q.trim().toLowerCase();
    const vistos = d.operadores.filter(o => (!q || o.nombre.toLowerCase().includes(q))
      && (!filtro.patio || (o.marca && o.marca.patio === filtro.patio)));
    poner(cuerpo, vistos.map(o => h("tr", {},
      h("td", {}, h("b", {}, o.nombre),
        h("div", { clase: "chico gris" }, [o.puesto, antiguedad(o.antiguedad)].filter(Boolean).join(" · "))),
      h("td", {}, ...situacionDe(o)),
      h("td", {}, licenciaDe(o.licencia)),
      esHoy ? h("td", {}, puedeSalir(o)) : null)));
    if (!vistos.length) {
      poner(cuerpo, h("tr", {}, h("td", { colspan: "4", clase: "gris chico" },
        d.operadores.length ? t("lgf_nada_filtro") : t("lgj_sin_operadores"))));
    }
    pie.textContent = t("lgj_mostrando").replace("{n}", vistos.length).replace("{total}", d.operadores.length);
  }

  const elDia = entrada("dia", { type: "date", value: d.fecha, max: d.hoy,
    onchange: (e) => { dia = e.target.value && e.target.value !== d.hoy ? e.target.value : null;
                       pestanaHoy(zona, contar).catch(err => mensaje(errorDe(err), "grave")); } });
  const elPatio = lista("patio", [{ valor: "", texto: t("lgj_todos_patios") },
    ...patios.map(p => ({ valor: p, texto: p }))],
  { onchange: (e) => { filtro.patio = e.target.value; pintarFilas(); } });
  elPatio.value = filtro.patio;
  const buscar = entrada("q", { type: "search", value: filtro.q, placeholder: t("lgj_buscar_ayuda"),
    oninput: (e) => { filtro.q = e.target.value; pintarFilas(); } });

  const c = d.cifras;
  const cifra = (titulo, n, pie_, color = "") => h("div", {},
    h("div", { clase: "chico gris" }, t(titulo)),
    h("div", { clase: "cifra", style: color ? `color:${color}` : null }, NUMERO.format(n)),
    h("div", { clase: "chico gris" }, t(pie_)));

  poner(zona,
    h("div", { clase: "tarjeta lisa" }, h("div", { clase: "rejilla tres" },
      campo(t("lgj_dia"), elDia), campo(t("lgf_patio"), elPatio), campo(t("lgf_buscar"), buscar))),
    h("div", { clase: "corte" },
      cifra("lgj_c_operadores", c.operadores, "lgj_c_operadores_pie"),
      cifra("lgj_c_presentes", c.presentes, "lgj_c_presentes_pie", "var(--ok)"),
      cifra("lgj_c_viaje", c.en_viaje, "lgj_c_viaje_pie"),
      cifra("lgj_c_validar", c.por_validar, "lgj_c_validar_pie", c.por_validar ? "var(--alerta)" : ""),
      cifra("lgj_c_ausentes", c.ausentes + c.rechazadas, "lgj_c_ausentes_pie",
            c.ausentes + c.rechazadas ? "var(--grave)" : "")),
    h("div", { clase: "tarjeta lisa", style: "padding:0;overflow-x:auto" },
      h("table", {}, h("thead", {}, h("tr", {},
        h("th", {}, t("lgj_col_operador")), h("th", {}, esHoy ? t("lgj_col_hoy") : larga(d.fecha)),
        h("th", {}, t("lgj_col_licencia")), esHoy ? h("th", {}, t("lgj_col_sale")) : null)), cuerpo)),
    pie);
  pintarFilas();
}

/* ================================================ Semana */

const SIGNO = {
  marca: () => h("span", { clase: "lgf-si" }, "✓"),
  viaje: () => etiqueta(t("lgj_viaje"), "azul"),
  por_validar: () => etiqueta("?", "alerta"),
  rechazada: () => h("span", { clase: "lgf-no", title: t("lgj_rechazada") }, "✗"),
  falta: () => h("span", { clase: "lgf-no" }, "✗"),
  pendiente: () => h("span", { clase: "lgf-nada" }, "·"),
  libre: () => h("span", { clase: "lgf-nada" }, "—"),
};

function bonoDe(o) {
  if (o.bono === "si") return etiqueta(t("lgj_bono_si"), "ok");
  if (o.bono === "no") return etiqueta(t("lgj_bono_no"), "grave");
  if (o.dias.some(x => x.codigo === "por_validar")) return etiqueta(t("lgj_bono_central"), "alerta");
  return etiqueta(t("lgj_bono_en_curso"), "info");
}

function moverSemana(base, dias) {
  const f = new Date(base + "T00:00:00");
  f.setDate(f.getDate() + dias);
  return `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, "0")}-${String(f.getDate()).padStart(2, "0")}`;
}

async function pestanaSemana(zona, contar) {
  const s = await api.get(lunes ? "/lg/jornada/semana?lunes=" + lunes : "/lg/jornada/semana");
  const nombres = t("f_dias").split(",");
  const encabezados = s.dias.map((iso) => {
    const f = new Date(iso + "T00:00:00");
    return h("th", { clase: "lgf-dia" }, `${nombres[f.getDay()]} ${f.getDate()}`);
  });
  const ir = (dias) => {
    lunes = moverSemana(s.lunes, dias);
    if (lunes > s.hoy) lunes = null;
    pestanaSemana(zona, contar).catch(err => mensaje(errorDe(err), "grave"));
  };
  const estaEsLaDeHoy = s.dias.includes(s.hoy);
  poner(zona,
    h("div", { clase: "lgf-acciones", style: "margin:0 0 12px;align-items:center" },
      boton(t("lgj_semana_anterior"), () => ir(-7)),
      h("b", {}, t("lgj_semana_de").replace("{a}", larga(s.dias[0])).replace("{b}", larga(s.dias[6]))),
      estaEsLaDeHoy ? null : boton(t("lgj_semana_siguiente"), () => ir(7))),
    h("div", { clase: "tarjeta lisa", style: "padding:0;overflow-x:auto" },
      h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, t("lgj_col_operador")), ...encabezados,
        h("th", { clase: "lgf-dia" }, t("lgj_col_activos")), h("th", {}, t("lgj_col_bono")))),
      h("tbody", {}, ...(s.operadores.length ? s.operadores.map(o => h("tr", {},
        h("td", {}, h("b", {}, o.nombre)),
        ...o.dias.map(x => h("td", { clase: "lgf-dia" }, SIGNO[x.codigo] ? SIGNO[x.codigo]() : "")),
        h("td", { clase: "lgf-dia" }, t("lgj_de_cinco").replace("{n}", o.activos)),
        h("td", {}, bonoDe(o))))
        : [h("tr", {}, h("td", { colspan: "10", clase: "gris chico" }, t("lgj_sin_operadores")))])))),
    h("p", { clase: "chico gris", style: "margin-top:-4px" }, t("lgj_semana_pie")));
  /* La de por validar se cuenta en su pestana; aqui no se pide de nuevo. */
  if (s.por_validar !== undefined) contar(s.por_validar);
}

/* ================================================ Por validar */

async function pestanaValidar(zona, contar) {
  const r = await api.get("/lg/jornada/por-validar");
  contar(r.marcas.length);
  if (!r.marcas.length) {
    poner(zona, h("div", { clase: "tarjeta" }, h("p", { clase: "gris", style: "margin:0" }, t("lgj_nada_por_validar"))));
    return;
  }
  poner(zona, ...r.marcas.map(m => tarjetaMarca(m, r.puede, zona, contar)));
}

function tarjetaMarca(m, puede, zona, contar) {
  const donde = m.patio ? t("lgj_marco_fuera").replace("{d}", distancia(m.distancia_m)).replace("{p}", m.patio)
    : t("lgj_marco_sin_punto");
  const precision = nada(m.precision_m) ? "" : ` ${t("lgj_precision").replace("{n}", NUMERO.format(m.precision_m))}`;
  const justificacion = h("textarea", { rows: "2", placeholder: t("lgj_justificacion_ayuda") });
  const error = h("div");

  async function revisar(validar) {
    poner(error);
    try {
      const r = await api.post(`/lg/jornada/marcas/${m.id}/revisar`,
        { validar, justificacion: justificacion.value.trim() });
      mensaje(t(validar ? "lgj_validada" : "lgj_rechazada_ok"));
      contar(r.marcas.length);
      if (!r.marcas.length) {
        poner(zona, h("div", { clase: "tarjeta" }, h("p", { clase: "gris", style: "margin:0" }, t("lgj_nada_por_validar"))));
      } else {
        poner(zona, ...r.marcas.map(x => tarjetaMarca(x, r.puede, zona, contar)));
      }
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
  }

  return h("div", { clase: "tarjeta" },
    h("div", { clase: "lgf-cabeza" },
      h("div", {}, h("h3", { style: "margin:0 0 4px" }, m.operador.nombre),
        h("div", { clase: "gris" }, t("lgj_marco").replace("{f}", larga(m.fecha)).replace("{h}", hora(m.marcada_en))
          .replace("{donde}", donde), precision)),
      etiqueta(t("lgj_por_validar"), "alerta")),
    h("div", { clase: "aviso", style: "margin:12px 0" }, t("lgj_escribio").replace("{n}", m.nota || "—")),
    puede.validar ? [error, campo(t("lgj_justificacion"), justificacion),
      h("div", { clase: "lgf-acciones" },
        h("button", { type: "button", onclick: () => revisar(true) }, t("lgj_validar")),
        h("button", { type: "button", clase: "peligro", onclick: () => revisar(false) }, t("lgj_rechazar")))]
      : h("p", { clase: "chico gris" }, t("lgj_la_valida_central")),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgj_validar_pie")));
}

/* ================================================ Operadores */

async function pestanaOperadores(zona, contar) {
  const d = await api.get("/lg/jornada/operadores");
  contar(d.por_validar);
  const recargar = () => pestanaOperadores(zona, contar).catch(err => mensaje(errorDe(err), "grave"));
  const formas = h("div");
  const abrir = (forma) => { poner(formas, forma); formas.scrollIntoView({ block: "nearest" }); };
  const cerrar = () => poner(formas);

  const filas = d.operadores.map((o) => {
    const app = o.app === "huella" ? etiqueta(t("lgj_app_huella"), "ok")
      : o.app === "contrasena" ? etiqueta(t("lgj_app_contrasena"), "info") : etiqueta(t("lgj_app_sin"));
    const acciones = [];
    if (d.puede.operadores && o.activo) {
      acciones.push(boton(o.app === "sin_acceso" ? t("lgj_dar_codigo") : t("lgj_codigo_nuevo"),
        () => darCodigo(o, abrir, cerrar)));
    }
    let viaje = null;
    if (o.en_viaje) {
      viaje = h("div", { clase: "chico", style: "margin-top:6px" }, etiqueta(t("lgj_en_viaje"), "azul"), " ",
        t("lgj_hasta").replace("{f}", larga(o.en_viaje.hasta)),
        d.puede.en_viaje ? [" ", h("a", { href: "#", style: "color:var(--centauro)", onclick: async (e) => {
          e.preventDefault();
          try { await api.post(`/lg/jornada/operadores/${o.id}/en-viaje`, {}); recargar(); }
          catch (err) { mensaje(errorDe(err), "grave"); }
        } }, t("lgj_ya_regreso"))] : null);
    } else if (d.puede.en_viaje && o.activo) {
      viaje = h("div", { style: "margin-top:6px" }, h("a", { href: "#", clase: "chico", style: "color:var(--centauro)",
        onclick: (e) => { e.preventDefault(); abrir(formaViaje(o, recargar, cerrar)); } }, t("lgj_marcar_viaje")));
    }
    const lic = o.licencia;
    return h("tr", { clase: o.activo ? "" : "apagado" },
      h("td", {}, h("b", {}, o.nombre), h("div", { clase: "chico gris" }, o.puesto || ""),
        o.activo ? viaje : h("div", { clase: "chico rojo" }, t("lgj_de_baja"))),
      h("td", {}, antiguedad(o.antiguedad), o.antiguedad
        ? h("div", { clase: "chico gris" }, t("lgj_desde").replace("{f}", mesAnio(o.antiguedad.desde))) : null),
      h("td", {}, lic.estado === "falta" ? h("span", { clase: "ambar" }, t("lgj_licencia_falta"))
        : [h("span", {}, lic.detalle || t("lgj_licencia")), " ", etiquetaDoc(lic),
           h("div", {}, detalleDoc(lic, false))],
      d.puede.operadores && o.activo ? h("div", { style: "margin-top:6px" },
        boton(lic.estado === "falta" ? t("lgf_capturar") : t("lgf_actualizar"),
          () => abrir(formaLicencia(o, recargar, cerrar)))) : null),
      h("td", {}, app, o.ultimo_acceso ? h("div", { clase: "chico gris" },
        t("lgj_ultimo_acceso").replace("{f}", larga(fechaLocal(new Date(o.ultimo_acceso))))) : null,
      acciones.length ? h("div", { style: "margin-top:6px" }, ...acciones) : null));
  });

  poner(zona,
    tarjetaOdoo({ titulo: t("lgj_odoo_titulo"), explica: t("lgj_odoo_explica"), ruta: "/lg/jornada/odoo",
                  ultima: d.odoo, puede: d.puede.operadores, alAplicar: () => setTimeout(recargar, 1200),
                  renglon: (x) => [x.nombre, x.motivo || null].filter(Boolean).join(" ") }),
    formas,
    h("div", { clase: "tarjeta lisa", style: "padding:0;overflow-x:auto" },
      h("table", {}, h("thead", {}, h("tr", {},
        h("th", {}, t("lgj_col_operador")), h("th", {}, t("lgj_col_antiguedad")),
        h("th", {}, t("lgj_col_licencia")), h("th", {}, t("lgj_col_app")))),
      h("tbody", {}, ...(filas.length ? filas
        : [h("tr", {}, h("td", { colspan: "4", clase: "gris chico" }, t("lgj_sin_operadores")))])))),
    conAyuda("h4", t("lgj_operadores_que"), "lgj_ayuda_operadores", { clase: "grupo" }),
    h("p", { clase: "chico gris", style: "margin-top:4px" }, t("lgj_operadores_pie")));
}

/* Los cuatro digitos se ven una sola vez: si se cierra la tarjeta, se
   genera otro y ese mata a este. */
async function darCodigo(o, abrir, cerrar) {
  try {
    const r = await api.post(`/lg/jornada/operadores/${o.id}/codigo`, {});
    abrir(h("div", { clase: "tarjeta", style: "max-width:640px" },
      h("h3", {}, t("lgj_codigo_para").replace("{n}", o.nombre)),
      h("div", { clase: "lgf-codigo" }, r.codigo),
      h("p", {}, t("lgj_codigo_dicta").replace("{n}", r.nombre).replace("{m}", r.minutos)),
      h("p", { clase: "chico gris" }, t("lgj_codigo_donde").replace("{c}", r.correo)),
      boton(t("lgj_listo_dictado"), cerrar, "")));
  } catch (err) { mensaje(errorDe(err), "grave"); }
}

function formaLicencia(o, recargar, cerrar) {
  const detalle = entrada("detalle", { value: o.licencia.detalle || "", placeholder: t("lgj_licencia_tipo_ayuda") });
  const folio = entrada("folio", { value: o.licencia.folio || "" });
  const vence = entrada("vence_en", { type: "date", value: o.licencia.vence_en || "" });
  const archivo = entrada("archivo", { type: "file", accept: "application/pdf,image/*" });
  const error = h("div");
  const guardar = h("button", { type: "button" }, t("lgf_guardar"));
  guardar.onclick = async () => {
    guardar.disabled = true;
    poner(error);
    try {
      await api.formulario(`/lg/jornada/operadores/${o.id}/licencia`, {
        detalle: detalle.value.trim() || null, folio: folio.value.trim() || null,
        vence_en: vence.value || null, archivo: archivo.files[0] || null });
      mensaje(t("lgf_listo"));
      cerrar();
      recargar();
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
    finally { guardar.disabled = false; }
  };
  return h("div", { clase: "tarjeta", style: "max-width:640px" },
    h("h3", {}, t("lgj_licencia_de").replace("{n}", o.nombre)), error,
    h("div", { clase: "rejilla dos" }, campo(t("lgj_licencia_tipo"), detalle), campo(t("lgf_folio"), folio),
      campo(t("lgf_vence_en"), vence), campo(t("lgf_archivo"), archivo)),
    h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgj_licencia_pie")));
}

function formaViaje(o, recargar, cerrar) {
  /* Se puede anotar el que ya paso, hasta dos semanas atras: sus dias
     cuentan para el bono. */
  const desde = entrada("desde", { type: "date", value: hoyLocal(), min: hoyLocal(-14) });
  const hasta = entrada("hasta", { type: "date", min: hoyLocal(-14) });
  const error = h("div");
  const guardar = h("button", { type: "button" }, t("lgf_guardar"));
  guardar.onclick = async () => {
    poner(error);
    /* Sin regreso no es un viaje: el servidor lo tomaria por «ya regreso». */
    if (!hasta.value) { poner(error, h("div", { clase: "aviso grave" }, t("lgj_falta_regreso"))); return; }
    guardar.disabled = true;
    try {
      await api.post(`/lg/jornada/operadores/${o.id}/en-viaje`,
        { desde: desde.value || null, hasta: hasta.value || null });
      mensaje(t("lgf_listo"));
      cerrar();
      recargar();
    } catch (err) { poner(error, h("div", { clase: "aviso grave" }, errorDe(err))); }
    finally { guardar.disabled = false; }
  };
  return h("div", { clase: "tarjeta", style: "max-width:640px" },
    h("h3", {}, t("lgj_viaje_de").replace("{n}", o.nombre)), error,
    h("div", { clase: "rejilla dos" }, campo(t("lgj_sale"), desde), campo(t("lgj_regresa"), hasta)),
    h("div", { clase: "lgf-acciones" }, guardar, boton(t("lgf_cancelar"), cerrar, "claro")),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lgj_viaje_pie")));
}

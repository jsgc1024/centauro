/* El historial de lo facturado (seccion 69).

   Lo que finanzas ya cerro nunca se borraba y no habia donde verlo: la
   pestana de cerrados ensena solo el mes en curso. Aqui va todo, desde el
   primer servicio, con filtros y en Excel. Cada renglon dice tambien que
   pasa con las fotos de sus comprobantes: cuantas siguen en Centauro y
   cuando se archivan, o cuando se archivaron.

   El detalle de un servicio se abre aqui mismo, con su "← Historial":
   los comprobantes de cada persona como en el cierre, y los que ya se
   fueron al archivo con su "Ver del archivo" para quien puede traerlos
   --direccion general y finanzas--. Traer una foto queda en la bitacora
   del servicio, y la pantalla dice si es la misma que se subio. */
import { api, ErrorApi, sesion } from "./api.js";
import { aviso, campo, conAyuda, dinero, entrada, etiqueta, h, hora,
         mensaje } from "./util.js";
import { idioma, t } from "./idioma.js";

const MESES = ["bon_mes_1", "bon_mes_2", "bon_mes_3", "bon_mes_4",
               "bon_mes_5", "bon_mes_6", "bon_mes_7", "bon_mes_8",
               "bon_mes_9", "bon_mes_10", "bon_mes_11", "bon_mes_12"];
const TIPO_TICKET = { factura: "cie_ticket_factura", nota: "cie_ticket_nota" };
const CONCEPTO = {
  alimentos: "cie_con_alimentos", hospedaje: "cie_con_hospedaje",
  combustible: "cie_con_combustible", casetas: "cie_con_casetas",
  traslado_personal: "cie_con_traslado", otros: "cie_con_otros",
};
const POR_PAGINA = 50;

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (x, [k, v]) => x.replaceAll(`{${k}}`, v ?? ""), texto);
}

/* "10 mar 2027": con el mes en letras, porque 10/03 se lee al reves en
   ingles. */
function diaCorto(iso) {
  if (!iso) return "—";
  const f = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  const meses = t("f_meses").split(",");
  return `${f.getDate()} ${meses[f.getMonth()]} ${f.getFullYear()}`;
}

function nombreMes(anio, mes) {
  return `${t(MESES[mes - 1])} ${anio}`;
}

function fechas(f) {
  if (f.mes) return nombreMes(f.anio, f.mes);
  if (!f.desde) return "—";
  if (f.desde === f.hasta) return diaCorto(f.desde);
  const a = new Date(`${f.desde}T00:00:00`);
  const b = new Date(`${f.hasta}T00:00:00`);
  if (a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear()) {
    const meses = t("f_meses").split(",");
    return `${a.getDate()}–${b.getDate()} ${meses[b.getMonth()]} ${b.getFullYear()}`;
  }
  return `${diaCorto(f.desde)} – ${diaCorto(f.hasta)}`;
}

function cuantas(n) {
  return n === 1 ? t("fac_his_una_foto") : reemplazar(t("fac_his_n_fotos"), { n });
}

function nombreConcepto(c) {
  if (c.concepto === "otros" && c.descripcion) return c.descripcion;
  return CONCEPTO[c.concepto] ? t(CONCEPTO[c.concepto]) : c.concepto;
}

/* ------------------------------------------------------------ la lista */

function factura(f) {
  if (f.facturado_en) {
    return [f.factura || "—",
      h("div", { clase: "chico gris" }, diaCorto(f.facturado_en))];
  }
  const pie = f.reloj && f.reloj.desde === "aprobacion"
    ? reemplazar(t("fac_his_sin_odoo_cuenta"), { f: diaCorto(f.reloj.inicio) })
    : t("fac_his_espera_factura");
  return [etiqueta(t("fac_his_aprobado_sin_factura"), "alerta"),
    h("div", { clase: "chico gris" }, pie)];
}

/* Que pasa con las fotos de este servicio, en una etiqueta. */
function chipFotos(f, info) {
  const x = f.fotos;
  if (!x.en_centauro && !x.archivadas) return etiqueta(t("fac_his_sin_fotos"));
  if (!x.en_centauro) {
    return etiqueta(reemplazar(t("fac_his_archivadas"),
      { f: diaCorto(x.archivadas_en) }), "cafe");
  }
  if (x.archivadas) {
    return etiqueta(reemplazar(t("fac_his_mixto"),
      { a: x.archivadas, n: x.en_centauro }), "cafe");
  }
  if (!f.reloj) {
    return etiqueta(`${cuantas(x.en_centauro)} · ${t("fac_his_esperan")}`, "info");
  }
  let cuando;
  if (f.reloj.archivo > info.hoy) {
    cuando = reemplazar(t("fac_his_se_archivan"), { f: diaCorto(f.reloj.archivo) });
  } else if (info.activo) {
    cuando = t("fac_his_esta_noche");
  } else {
    cuando = reemplazar(t("fac_his_listas"), { f: diaCorto(f.reloj.archivo) });
  }
  return etiqueta(`${cuantas(x.en_centauro)} · ${cuando}`, "info");
}

function renglon(f, info, abrir) {
  const moneda = f.moneda || "MXN";
  const tipo = f.tipo === "implantado"
    ? etiqueta(t("implantado"), "azul") : etiqueta(t("eventual"), "negro");
  return h("tr", { clase: "clic", onclick: () => abrir(f.cierre_id) },
    h("td", {}, h("b", { clase: "folio" }, f.folio),
      h("div", { clase: "chico gris" }, f.cliente || ""),
      h("div", { clase: "chico" }, tipo,
        f.cancelado ? [" ", etiqueta(t("fac_his_cancelado"), "grave")] : "")),
    h("td", {}, fechas(f)),
    h("td", {}, f.consultor || "—"),
    h("td", {}, factura(f)),
    h("td", { clase: "der num" }, h("b", {}, dinero(f.total, moneda))),
    h("td", { clase: "der num" }, dinero(f.viaticos, moneda)),
    h("td", {}, chipFotos(f, info)));
}

function sumas(porMoneda) {
  const partes = Object.entries(porMoneda || {})
    .map(([m, v]) => dinero(v, m || "MXN"));
  return partes.length ? partes.join(" + ") : dinero(0);
}

function resumen(r) {
  const servicios = r.servicios === 1 ? t("fac_his_un_servicio")
    : reemplazar(t("fac_his_servicios"), { n: r.servicios });
  return [h("b", {}, servicios), " · ", t("fac_his_facturado"), " ",
    h("b", {}, sumas(r.facturado)), " · ", t("fac_his_viaticos_resumen"), " ",
    h("b", {}, sumas(r.viaticos)), " · ",
    reemplazar(t("fac_his_fotos_resumen"),
      { c: r.fotos_en_centauro, a: r.fotos_archivadas })];
}

/* Los meses entre el primero que tiene algo y el ultimo. */
function meses(opciones) {
  if (!opciones.primer_mes) return [];
  const [a0, m0] = opciones.primer_mes.split("-").map(Number);
  const [a1, m1] = opciones.ultimo_mes.split("-").map(Number);
  const lista = [];
  for (let a = a1, m = m1; a > a0 || (a === a0 && m >= m0);) {
    lista.push([`${a}-${String(m).padStart(2, "0")}`, nombreMes(a, m)]);
    m -= 1;
    if (m === 0) { m = 12; a -= 1; }
  }
  return lista;
}

function consulta(filtros, extra = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...filtros, ...extra })) {
    if (v !== null && v !== undefined && v !== "") q.set(k, v);
  }
  return q.toString();
}

/* El Excel se baja con la sesion puesta, como toda imagen del servidor,
   y con el nombre que pone el servidor. */
async function bajar(ruta) {
  const cab = sesion.token ? { Authorization: `Bearer ${sesion.token}` } : {};
  const r = await fetch(ruta, { headers: cab });
  if (!r.ok) {
    const d = await r.json().catch(() => null);
    throw new ErrorApi(r.status, d && d.detail);
  }
  const dicho = r.headers.get("content-disposition") || "";
  const nombre = (dicho.match(/filename="([^"]+)"/) || [])[1] || "historial.xlsx";
  const url = URL.createObjectURL(await r.blob());
  const enlace = h("a", { href: url, download: nombre });
  document.body.append(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function pestanaHistorial() {
  const zona = h("div");
  const filtros = { desde: "", hasta: "", cliente_id: "", consultor_id: "",
                    tipo: "", folio: "" };
  let filas = [];
  let datos = null;
  let pagina = 1;

  const lista = (nombre, opciones) => {
    const control = h("select", { name: nombre },
      h("option", { value: "" }, t("fac_his_todos")),
      ...opciones.map(([valor, texto]) => h("option", {
        value: valor,
        selected: String(valor) === String(filtros[nombre]) ? "selected" : null,
      }, texto)));
    control.addEventListener("change", () => {
      filtros[nombre] = control.value;
      cargar();
    });
    return control;
  };

  const folio = entrada("folio", { placeholder: t("fac_his_buscar_folio"),
                                   autocomplete: "off" });
  let espera = null;
  folio.addEventListener("input", () => {
    clearTimeout(espera);
    espera = setTimeout(() => { filtros.folio = folio.value.trim(); cargar(); },
                        350);
  });

  const excel = h("button", { clase: "claro", type: "button",
    onclick: async () => {
      const antes = excel.textContent;
      excel.disabled = true;
      excel.textContent = t("fac_his_preparando");
      try {
        await bajar(`/cierre/historial.xlsx?${consulta(filtros, { idioma: idioma() })}`);
      } catch (err) {
        mensaje(err.message, "grave");
      } finally {
        excel.disabled = false;
        excel.textContent = antes;
      }
    } }, t("fac_his_excel"));

  const abrir = (cierreId) => detalle(zona, cierreId, () => pintar());

  function barra() {
    const o = datos.opciones;
    return h("div", { clase: "filtros" },
      campo(t("fac_his_desde"), lista("desde", meses(o))),
      campo(t("fac_his_hasta"), lista("hasta", meses(o))),
      campo(t("fac_his_cliente"),
        lista("cliente_id", o.clientes.map(c => [c.id, c.nombre]))),
      campo(t("fac_his_consultor"),
        lista("consultor_id", o.consultores.map(c => [c.id, c.nombre]))),
      campo(t("fac_his_tipo"), lista("tipo", [["eventual", t("eventual")],
                                               ["implantado", t("implantado")]])),
      campo(t("fac_his_folio"), folio),
      h("div", { clase: "empuja" }),
      excel);
  }

  function pintar() {
    if (!datos) return;
    const info = datos.archivo;
    const tabla = filas.length
      ? h("table", { clase: "lista" },
          h("thead", {}, h("tr", {},
            h("th", {}, t("fac_col_servicio")),
            h("th", {}, t("fac_his_col_fechas")),
            h("th", {}, t("fac_his_consultor")),
            h("th", {}, t("fac_col_factura")),
            h("th", { clase: "der" }, t("fac_col_total")),
            h("th", { clase: "der" }, t("fac_his_col_viaticos")),
            h("th", {}, t("fac_his_col_fotos")))),
          h("tbody", {}, ...filas.map(f => renglon(f, info, abrir))))
      : h("div", { clase: "tarjeta" }, h("div", { clase: "vacio" }, t("fac_his_nada")));
    const mas = filas.length < datos.total
      ? h("button", { clase: "claro chico", type: "button", onclick: async (e) => {
          e.target.disabled = true;
          pagina += 1;
          await cargar(true);
        } }, t("fac_his_ver_mas"))
      : "";
    zona.replaceChildren(
      barra(),
      conAyuda("div", resumen(datos.resumen), "ay_fac_historial",
               { clase: "resumen-filtro" }),
      tabla,
      filas.length ? h("div", { clase: "acciones", style: "margin:8px 4px 0" },
        h("span", { clase: "chico gris" }, reemplazar(t("fac_his_mostrando"),
          { n: filas.length, t: datos.total })), mas) : "");
  }

  async function cargar(otraPagina = false) {
    if (!otraPagina) pagina = 1;
    let r;
    try {
      r = await api.get(`/cierre/historial?${consulta(filtros,
        { pagina, por_pagina: POR_PAGINA })}`);
    } catch (err) {
      zona.replaceChildren(aviso(err.message, "grave"));
      return;
    }
    datos = r;
    filas = otraPagina ? filas.concat(r.filas) : r.filas;
    pintar();
  }

  cargar();
  return zona;
}

/* ------------------------------------------------------------ el detalle */

function avisoDelArchivo(d) {
  const x = d.fotos;
  const r = d.reloj;
  const info = d.archivo;
  if (!x.en_centauro && !x.archivadas) return "";
  const desde = r && r.desde === "aprobacion"
    ? t("fac_his_desde_aprobacion") : t("fac_his_desde_factura");
  if (x.archivadas && !x.en_centauro) {
    return aviso(reemplazar(t("fac_his_aviso_archivadas"),
      { f: diaCorto(x.archivadas_en), desde }));
  }
  if (x.archivadas) {
    const idas = x.archivadas === 1 ? t("fac_his_aviso_mixto_a1")
      : t("fac_his_aviso_mixto_an");
    const quedan = x.en_centauro === 1 ? t("fac_his_aviso_mixto_n1")
      : t("fac_his_aviso_mixto_nn");
    return aviso(reemplazar(`${idas} ${quedan}`,
      { a: x.archivadas, n: x.en_centauro, f: diaCorto(x.archivadas_en) }));
  }
  if (!r) return aviso(t("fac_his_aviso_esperan"));
  if (!info.activo) {
    return aviso(reemplazar(t("fac_his_aviso_apagado"), { f: diaCorto(r.archivo) }));
  }
  return aviso(reemplazar(t("fac_his_aviso_pendiente"),
    { f: diaCorto(r.archivo), desde, a: info.anios }));
}

function cifra(titulo, valor, pie = "") {
  return h("div", {}, h("div", { clase: "chico gris" }, titulo),
    h("div", { clase: "cifra", style: "font-size:20px" }, valor),
    pie ? h("div", { clase: "chico gris" }, pie) : "");
}

/* Un visor encima de la pantalla: la foto, lo que hay que saber de ella
   y el boton para bajarla. Se cierra con el boton, con Escape o picando
   afuera. */
function abrirVisor() {
  const cuerpo = h("div", { clase: "visor" });
  const fondo = h("div", { clase: "visor-fondo" }, cuerpo);
  const tecla = (e) => { if (e.key === "Escape") cerrar(); };
  function cerrar() {
    fondo.remove();
    document.removeEventListener("keydown", tecla);
  }
  fondo.addEventListener("click", (e) => { if (e.target === fondo) cerrar(); });
  document.addEventListener("keydown", tecla);
  document.body.append(fondo);
  return {
    cerrar,
    cargando(texto) { cuerpo.replaceChildren(h("p", { clase: "gris" }, texto)); },
    mostrar({ titulo, sub, imagen, nota, tono, nombre }) {
      cuerpo.replaceChildren(
        h("h3", { style: "margin:0" }, titulo),
        sub ? h("div", { clase: "chico gris", style: "margin-top:4px" }, sub) : "",
        h("img", { src: imagen, alt: "" }),
        nota ? aviso(nota, tono) : "",
        h("div", { clase: "acciones", style: "justify-content:flex-end;margin-top:12px" },
          h("button", { clase: "claro", type: "button", onclick: () => {
            const enlace = h("a", { href: imagen, download: nombre });
            document.body.append(enlace);
            enlace.click();
            enlace.remove();
          } }, t("fac_his_descargar")),
          h("button", { type: "button", onclick: cerrar }, t("fac_his_cerrar"))));
    },
  };
}

function extension(dataUri) {
  const tipo = (dataUri.match(/^data:([^;]+)/) || [])[1] || "image/jpeg";
  return { "image/png": "png", "image/webp": "webp" }[tipo] || "jpg";
}

async function verFoto(ruta, titulo, nombre) {
  const v = abrirVisor();
  v.cargando("…");
  try {
    const url = await api.imagen(ruta);
    v.mostrar({ titulo, imagen: url, nombre });
  } catch (err) {
    v.cerrar();
    mensaje(err.message, "grave");
  }
}

async function traerDelArchivo(tipo, fila, titulo) {
  const v = abrirVisor();
  v.cargando(t("fac_his_trayendo"));
  let r;
  try {
    r = await api.get(`/archivo/${tipo}/${fila.id}`);
  } catch (err) {
    v.cerrar();
    mensaje(err.message, "grave");
    return;
  }
  const nota = [
    reemplazar(t("fac_his_traida"), { f: diaCorto(r.traida_en),
      h: hora(r.traida_en), quien: r.por || "—" }),
    r.coincide ? t("fac_his_coincide") : t("fac_his_no_coincide"),
  ].join(" ");
  v.mostrar({
    titulo: `${titulo} · ${dinero(r.monto, r.moneda || "MXN")}`,
    sub: reemplazar(t("fac_his_visor_sub"), { folio: r.folio,
      persona: r.persona || "—",
      f: r.subida_en ? `${diaCorto(r.subida_en)} ${hora(r.subida_en)}` : "—" }),
    imagen: r.imagen, nota, tono: r.coincide ? "" : "grave",
    nombre: `${r.folio}_${tipo}_${fila.id}.${extension(r.imagen)}`,
  });
}

/* La miniatura mientras la foto sigue aqui; el cuadro gris cuando ya se
   fue al archivo. */
function miniatura(fila, ruta, titulo, nombre) {
  if (fila.archivada_en) {
    return h("button", { clase: "miniatura archivada", type: "button",
      disabled: "disabled",
      title: reemplazar(t("fac_his_archivada"), { f: diaCorto(fila.archivada_en) }) });
  }
  const boton = h("button", { clase: "miniatura", type: "button",
    title: t("cie_ver_foto"), onclick: () => verFoto(ruta, titulo, nombre) });
  if (fila.tiene_imagen) {
    api.imagen(ruta).then(url => {
      boton.style.backgroundImage = `url("${url}")`;
      boton.style.backgroundSize = "cover";
    }).catch(() => {});
  } else {
    boton.disabled = true;
    boton.title = t("cie_sin_foto");
  }
  return boton;
}

function archivada(fila, tipo, titulo, d) {
  if (!fila.archivada_en) return "";
  return [
    h("div", { clase: "gris", style: "margin:2px 0 5px" },
      reemplazar(t("fac_his_archivada"), { f: diaCorto(fila.archivada_en) })),
    d.puede_ver_archivo
      ? h("button", { clase: "claro chico", type: "button",
          onclick: () => traerDelArchivo(tipo, fila, titulo) },
          t("fac_his_ver_archivo"))
      : h("div", { clase: "gris" }, t("fac_his_pedir_archivo")),
  ];
}

function renglonTicket(c, moneda, d) {
  let estado;
  if (c.rechazado) {
    estado = h("div", { clase: "rojo" },
      reemplazar(t("cie_rechazado_por"), { m: c.motivo_rechazo || "" }));
  } else if (c.validado) {
    estado = h("div", { clase: "verde", style: "font-weight:650" },
      "✓ " + t("cie_validado"));
  } else {
    estado = h("div", { clase: "gris" }, t("cie_sin_revisar"));
  }
  const titulo = nombreConcepto(c);
  const ruta = `/viaticos/${c.viatico_id}/comprobantes/${c.id}/imagen`;
  return h("div", { clase: "comprobante" },
    h("div", {}, miniatura(c, ruta, titulo, `${d.folio}_${c.id}.jpg`), "  ",
      h("b", {}, titulo), " ",
      h("span", { clase: "gris chico" },
        `· ${t(TIPO_TICKET[c.tipo] || "cie_ticket_nota")} · ${diaCorto(c.fecha)}`)),
    h("div", { clase: "importe num" + (c.rechazado ? " tachado" : "") },
      dinero(c.monto, moneda)),
    h("div", { clase: "estado chico" }, estado,
      archivada(c, "comprobantes", titulo, d)));
}

function renglonDevolucion(x, moneda, d) {
  let estado;
  if (x.estatus === "confirmada") {
    estado = h("div", { clase: "verde", style: "font-weight:650" },
      "✓ " + t("fac_his_confirmada"));
  } else if (x.estatus === "rechazada") {
    estado = h("div", { clase: "rojo" }, t("fac_his_rechazada"));
  } else {
    estado = h("div", { clase: "gris" }, t("fac_his_declarada"));
  }
  const titulo = t("fac_his_devolucion");
  const ruta = `/viaticos/devoluciones/${x.id}/comprobante`;
  return h("div", { clase: "comprobante" },
    h("div", {}, miniatura(x, ruta, titulo, `${d.folio}_d${x.id}.jpg`), "  ",
      h("b", {}, titulo), " ",
      h("span", { clase: "gris chico" },
        `· ${t("fac_his_transferencia")} · ${diaCorto(x.fecha || x.declarada_en)}`)),
    h("div", { clase: "importe num" }, dinero(x.monto, x.moneda || moneda)),
    h("div", { clase: "estado chico" }, estado,
      archivada(x, "devoluciones", titulo, d)));
}

async function detalle(zona, cierreId, volver) {
  let d;
  try {
    d = await api.get(`/cierre/historial/${cierreId}`);
  } catch (err) {
    mensaje(err.message, "grave");
    return;
  }
  const moneda = d.moneda || "MXN";
  const regresar = h("a", { clase: "volver", href: "#",
    onclick: (e) => { e.preventDefault(); volver(); } }, t("fac_his_volver"));
  zona.replaceChildren(
    regresar,
    h("h2", { style: "margin:0" }, `${d.folio} · ${d.cliente || ""}`),
    h("p", { clase: "sub" }, [d.plaza, fechas(d),
      reemplazar(t("fac_his_consultor_de"), { n: d.consultor || "—" })]
      .filter(Boolean).join(" · ")),
    h("div", { clase: "corte" },
      cifra(t("fac_col_factura"), d.factura || t("fac_sin_factura"),
        diaCorto(d.facturado_en || d.aprobado_en)),
      cifra(t("fac_his_total_facturado"), dinero(d.total, moneda)),
      cifra(t("fac_his_viaticos_comprobados"), dinero(d.comprobado, moneda),
        reemplazar(t("fac_his_de_entregados"), { m: dinero(d.entregado, moneda) })),
      cifra(t("fac_his_devuelto"), dinero(d.devuelto, moneda))),
    avisoDelArchivo(d),
    ...d.personas.map(p => h("div", { clase: "tarjeta", style: "margin-top:14px" },
      h("h3", { style: "margin:0 0 4px" }, p.nombre || "—"),
      h("div", { clase: "comprobantes" },
        ...p.comprobantes.map(c => renglonTicket(c, p.moneda || moneda, d)),
        ...p.devoluciones.map(x => renglonDevolucion(x, p.moneda || moneda, d))))));
  window.scrollTo({ top: 0 });
}

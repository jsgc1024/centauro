/* El freelance (seccion 111).

   Salvador (30 sep): un lugar para darlo de alta con su foto y sus datos
   --los que salen en la hoja del servicio--, otro donde se cargue todo lo
   que pide Recursos Humanos para activarlo, y sus costos propios de dia
   completo, medio dia y transfer, solo en eventuales.

   Tres piezas:
     - la pestana Freelance de Personal de seguridad: quien es, como va su
       expediente, sus costos y su ultimo servicio;
     - su ficha (#/freelance/12): datos y costos, expediente, servicios e
       historial;
     - lo que la lista de a quien asignar dice de cada freelance, que usa
       el servicio (`avisoFreelance`).

   Quien asigna ve si esta listo; sus documentos los abren Recursos
   Humanos, direccion de operaciones y direccion general (decision 6). La
   pantalla no decide nada: pinta lo que el servidor dice y no ofrece el
   boton que va a contestar que no. */
import { api, sesion } from "./api.js";
import { aviso, campo, coincide, conAyuda, dinero, etiqueta, fecha, h, lista,
         mensaje, pieObligatorios, reducirImagen, telefono } from "./util.js";
import { t } from "./idioma.js";
import { tiene } from "./menu.js";

const TONO = { listo: "ok", plazo: "alerta", por_revisar: "alerta",
               faltan: "grave", vencido: "grave", plazo_vencido: "grave",
               sin_requisitos: "grave" };
const TONO_DOC = { validado: "ok", por_vencer: "alerta", por_revisar: "alerta",
                   rechazado: "grave", vencido: "grave", falta: "grave",
                   caseta: "info" };
const MODALIDADES = ["full_day", "medio_dia", "transfer"];

/* La silueta cuando todavia no hay foto: el hueco dice que falta. */
function foto(url, clase = "fre-foto") {
  return url
    ? h("img", { clase, src: url, alt: "" })
    : h("div", { clase: `${clase} fre-sin-foto`, title: t("fre_sin_foto") });
}

function fechaCorta(iso) {
  return iso ? fecha(iso.slice(0, 10)) : "—";
}

/* El estado del expediente en una etiqueta y una linea. */
export function estadoFreelance(x) {
  const e = x.estado;
  let detalle = "";
  if (e === "listo") {
    detalle = x.proximo_vencimiento
      ? t("fre_det_vence").replace("{que}", x.proximo_vencimiento.nombre)
          .replace("{f}", fechaCorta(x.proximo_vencimiento.fecha))
      : "";
  } else if (e === "faltan") {
    detalle = x.faltan.length === 1 ? x.faltan[0]
      : t("fre_det_faltan").replace("{lista}", x.faltan.slice(0, 3).join(", "))
          + (x.faltan.length > 3 ? " …" : "");
  } else if (e === "por_revisar") {
    detalle = t("fre_det_por_revisar").replace("{n}", x.por_revisar);
  } else if (e === "vencido") {
    const v = x.vencidos[0];
    detalle = t("fre_det_vencio").replace("{que}", v.nombre)
      .replace("{f}", fechaCorta(v.fecha));
  } else if (e === "plazo") {
    detalle = t("fre_det_plazo").replace("{n}", Math.max(0, x.dias_de_plazo));
  } else if (e === "plazo_vencido") {
    detalle = t("fre_det_plazo_vencido")
      .replace("{f}", fechaCorta(x.plazo_programado));
  } else if (e === "sin_requisitos") {
    detalle = t("fre_det_sin_requisitos");
  }
  const texto = e === "faltan"
    ? t("fre_est_faltan").replace("{n}", x.faltan.length)
    : t(`fre_est_${e}`);
  return { texto, tono: TONO[e] || "", detalle };
}

function etiquetaTipo(tipo) {
  return etiqueta(t(`fre_tipo_${tipo}`), tipo === "emergencia" ? "alerta" : "info");
}

/* =============================================================== la lista */

let filtroTipo = "";
let filtroEstado = "";
let busqueda = "";

const FILTROS = ["listo", "por_revisar", "faltan", "vencido", "por_vencer",
                 "plazo"];

function pasaFiltro(f) {
  const x = f.expediente;
  if (filtroTipo && f.tipo !== filtroTipo) return false;
  if (filtroEstado === "por_revisar" && !x.esperan_revision) return false;
  if (filtroEstado === "por_vencer" && !x.por_vencer.length) return false;
  if (filtroEstado === "plazo" && !["plazo", "plazo_vencido"].includes(x.estado)) return false;
  if (["listo", "faltan", "vencido"].includes(filtroEstado) && x.estado !== filtroEstado) {
    return false;
  }
  return !busqueda.trim() || coincide(busqueda, f.nombre, f.plaza, f.correo);
}

/* La pestana Freelance de Personal de seguridad. `paises` y `paisId` los
   comparte con la pestana de planta; `alCambiarPais` le avisa cual quedo
   y `contar` pinta cuantos hay en el boton de la pestana. */
export async function pestanaFreelance(zona, paises, paisId, alCambiarPais,
                                       contar = () => {}) {
  const selector = lista("pais_freelance", paises.map(
    p => ({ valor: p.id, texto: p.nombre })));
  selector.value = paisId;
  const caja = h("input", { type: "search", name: "buscar_freelance",
                            placeholder: t("fre_buscar"), value: busqueda });
  const tipo = lista("tipo_freelance", [
    { valor: "", texto: t("fre_todos") },
    { valor: "programado", texto: t("fre_tipo_programado") },
    { valor: "emergencia", texto: t("fre_tipo_emergencia") }]);
  tipo.value = filtroTipo;
  const estado = lista("estado_freelance", [
    { valor: "", texto: t("fre_todos") },
    ...FILTROS.map(e => ({ valor: e, texto: t(`fre_filtro_${e}`) }))]);
  estado.value = filtroEstado;

  const tabla = h("div");
  let filas = [];
  const dibujar = () => {
    const vistas = filas.filter(pasaFiltro);
    if (!filas.length) {
      return tabla.replaceChildren(h("div", { clase: "vacio" }, t("fre_vacio")));
    }
    if (!vistas.length) {
      return tabla.replaceChildren(h("div", { clase: "vacio" }, t("fre_nada_asi")));
    }
    tabla.replaceChildren(h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("col_persona")), h("th", {}, t("fre_col_tipo")),
        h("th", {}, t("fre_col_expediente")), h("th", {}, t("fre_col_costos")),
        h("th", {}, t("fre_col_ultimo")), h("th", {}, t("col_experiencia")))),
      h("tbody", {}, ...vistas.map(renglon))));
  };
  const cargar = async () => {
    tabla.replaceChildren(h("p", { clase: "gris" }, t("per_cargando")));
    try {
      filas = await api.get(`/freelance?pais_id=${selector.value}`);
    } catch (err) {
      return tabla.replaceChildren(aviso(err.message, "grave"));
    }
    contar(filas.length);
    dibujar();
  };

  selector.addEventListener("change", () => {
    alCambiarPais(Number(selector.value));
    cargar();
  });
  caja.addEventListener("input", () => { busqueda = caja.value; dibujar(); });
  tipo.addEventListener("change", () => { filtroTipo = tipo.value; dibujar(); });
  estado.addEventListener("change", () => { filtroEstado = estado.value; dibujar(); });

  const alta = tiene(sesion.usuario, "freelance.alta")
    ? h("button", { type: "button",
                    onclick: () => { location.hash = "#/freelance/nuevo"; } },
        t("fre_dar_de_alta"))
    : "";
  zona.replaceChildren(
    h("div", { clase: "tarjeta lisa" },
      conAyuda("h3", t("fre_lista_titulo"), "ay_fre_lista"),
      h("div", { clase: "rejilla cuatro" },
        campo(t("pais"), selector), campo(t("bus_buscar"), caja),
        campo(t("fre_col_tipo"), tipo), campo(t("fre_col_expediente"), estado)),
      h("div", { clase: "acciones" }, alta,
        h("span", { clase: "chico gris" }, t("fre_lista_pie")))),
    tabla);
  await cargar();
}

function costosCortos(f) {
  const c = f.costos || {};
  if (MODALIDADES.some(m => c[m] === null || c[m] === undefined)) {
    return h("span", { clase: "chico", style: "color:var(--grave)" }, t("fre_por_fijar"));
  }
  return h("div", {},
    h("div", { clase: "num chico" },
      MODALIDADES.map(m => dinero(c[m], f.moneda)).join(" · ")),
    h("div", { clase: "gris chico" }, t("fre_tres_costos")));
}

function renglon(f) {
  const est = estadoFreelance(f.expediente);
  const ultimo = f.ultimo_servicio || f.proximo_servicio;
  return h("tr", {},
    h("td", {},
      h("div", { clase: "fre-persona" }, foto(f.foto),
        h("div", {},
          h("a", { href: `#/freelance/${f.persona_id}` }, h("b", {}, f.nombre)),
          h("div", { clase: "gris chico" }, [f.plaza, f.correo].filter(Boolean).join(" · ")),
          f.activo ? "" : etiqueta(t("fre_de_baja"), "grave")))),
    h("td", {}, etiquetaTipo(f.tipo)),
    h("td", {}, etiqueta(est.texto, est.tono),
      est.detalle ? h("div", { clase: "chico gris" }, est.detalle) : ""),
    h("td", {}, costosCortos(f)),
    h("td", { clase: "chico" }, ultimo
      ? h("div", {},
          h("a", { href: `#/servicio/${ultimo.servicio_id}` }, ultimo.folio),
          h("div", { clase: "gris" },
            (f.ultimo_servicio ? "" : t("fre_proximo") + " ") + fechaCorta(ultimo.fecha)))
      : h("span", { clase: "gris" }, t("fre_sin_servicios"))),
    h("td", { clase: "num" }, `${(f.horas_en_centauro || 0).toLocaleString()} h`));
}

/* =============================================================== la ficha */

let pestanaFicha = "datos";

export async function pantallaFreelance(main, id) {
  if (id === "nuevo") return alta(main);
  const zona = h("div");
  main.append(zona);
  await pintarFicha(zona, Number(id));
}

async function pintarFicha(zona, id) {
  zona.replaceChildren(h("p", { clase: "gris" }, t("per_cargando")));
  let f;
  try {
    f = await api.get(`/freelance/${id}`);
  } catch (err) {
    return zona.replaceChildren(aviso(err.message, "grave"));
  }
  const recargar = () => pintarFicha(zona, id);
  const x = f.expediente;
  const cuerpo = h("div");
  const pestanas = h("div", { clase: "pestanas", style: "margin:0 0 12px" });
  const ir = (clave) => {
    pestanaFicha = clave;
    pintarPestanas();
    pintarCuerpo();
  };
  const pintarPestanas = () => pestanas.replaceChildren(
    ...[["datos", t("fre_tab_datos")],
        ["expediente", t("fre_tab_expediente").replace("{a}", x.validados)
                                              .replace("{b}", x.total)],
        ["servicios", t("fre_tab_servicios")],
        ["historial", t("fre_tab_historial")]]
      .map(([clave, texto]) => h("button", {
        type: "button", clase: `pestana ${pestanaFicha === clave ? "activa" : ""}`.trim(),
        onclick: () => ir(clave) }, texto)));
  const pintarCuerpo = async () => {
    if (pestanaFicha === "expediente") return pintarExpediente(cuerpo, f, recargar);
    if (pestanaFicha === "servicios") return cuerpo.replaceChildren(servicios(f));
    if (pestanaFicha === "historial") return cuerpo.replaceChildren(historial(f));
    return cuerpo.replaceChildren(...datosYCostos(f, recargar));
  };

  const est = estadoFreelance(x);
  zona.replaceChildren(
    h("div", { clase: "acciones", style: "margin:0 0 6px" },
      h("a", { clase: "enlace chico", href: "#/equipo" }, t("fre_volver"))),
    h("h1", {}, f.nombre),
    h("p", { clase: "sub" },
      t(`fre_sub_${f.tipo}`).replace("{c}", f.plaza || "—")
      + (f.alta_por
          ? " · " + t("fre_alta_por").replace("{f}", fechaCorta(f.alta_en))
                     .replace("{q}", f.alta_por)
          : ""),
      " ", etiqueta(est.texto, est.tono),
      f.activo ? "" : " ", f.activo ? "" : etiqueta(t("fre_de_baja"), "grave")),
    pestanas, cuerpo);
  pintarPestanas();
  await pintarCuerpo();
}

/* ------------------------------------------------------ datos y costos */

function formaDatos(f, plazas, nuevo = false) {
  const nombre = h("input", { name: "nombre", value: f.nombre_de_pila || "" });
  const apellidos = h("input", { name: "apellidos", value: f.apellidos || "" });
  const tel = telefono("telefono", f.lada || "+52");
  if (f.telefono) tel.poner(f.telefono);
  const correo = h("input", { name: "correo", type: "email", value: f.correo || "" });
  const suyas = nuevo ? plazas
    : plazas.filter(p => p.pais_id === f.pais_id);
  const ciudad = lista("plaza_id", suyas.map(p => ({
    valor: p.id, texto: nuevo ? `${p.nombre} · ${p.pais}` : p.nombre })));
  if (f.plaza_id) ciudad.value = f.plaza_id;
  const programado = h("input", { type: "radio", name: "tipo", value: "programado" });
  const emergencia = h("input", { type: "radio", name: "tipo", value: "emergencia" });
  (f.tipo === "emergencia" ? emergencia : programado).checked = true;
  const tipoFijo = !nuevo && !(f.puede && f.puede.tipo);
  if (tipoFijo) { programado.disabled = true; emergencia.disabled = true; }
  return {
    nodo: h("div", { clase: "rejilla dos" },
      campo(t("fre_nombre"), nombre, { obligatorio: true }),
      campo(t("fre_apellidos"), apellidos, { obligatorio: true }),
      campo(t("fre_telefono"), tel, { obligatorio: true }),
      campo(t("fre_correo"), correo, { obligatorio: true }),
      campo(t("fre_ciudad"), ciudad, { obligatorio: true }),
      campo(t("fre_col_tipo"), h("div", { clase: "fre-tipos" },
        h("label", { clase: "casilla" }, programado, " ", t("fre_tipo_programado")),
        h("label", { clase: "casilla" }, emergencia, " ", t("fre_tipo_emergencia")),
        tipoFijo ? h("div", { clase: "chico gris" }, t("fre_tipo_lo_cambia_rh")) : ""),
        { obligatorio: true })),
    valores: () => {
      const numero = tel.controles[1].value.trim();
      return {
        nombre: nombre.value.trim(), apellidos: apellidos.value.trim(),
        lada: tel.controles[0].value.trim(), telefono: numero,
        correo: correo.value.trim(), plaza_id: Number(ciudad.value),
        tipo: emergencia.checked ? "emergencia" : "programado",
      };
    },
  };
}

async function plazasConPais() {
  const [plazas, paises] = await Promise.all([
    api.get("/catalogos/plazas"), api.get("/catalogos/paises")]);
  const nombre = Object.fromEntries(paises.map(p => [p.id, p.nombre]));
  return plazas.map(p => ({ ...p, pais: nombre[p.pais_id] || "" }))
    .sort((a, b) => `${a.pais}${a.nombre}`.localeCompare(`${b.pais}${b.nombre}`));
}

async function alta(main) {
  if (!tiene(sesion.usuario, "freelance.alta")) {
    return main.append(aviso(t("sin_acceso"), "grave"));
  }
  const plazas = await plazasConPais();
  const suyo = (sesion.usuario || {}).plaza_id;
  const forma = formaDatos({ plaza_id: suyo, tipo: "programado" }, plazas, true);
  const boton = h("button", { type: "button", onclick: async () => {
    const v = forma.valores();
    if (!v.nombre || !v.apellidos || !v.telefono || !v.correo) {
      return mensaje(t("fre_faltan_datos"), "alerta");
    }
    boton.disabled = true;
    try {
      const r = await api.post("/freelance", v);
      mensaje(t("fre_alta_hecha").replace("{n}", r.nombre));
      location.hash = `#/freelance/${r.persona_id}`;
    } catch (err) {
      mensaje(err.message, "grave");
      boton.disabled = false;
    }
  } }, t("fre_dar_de_alta"));
  main.append(
    h("div", { clase: "acciones", style: "margin:0 0 6px" },
      h("a", { clase: "enlace chico", href: "#/equipo" }, t("fre_volver"))),
    h("h1", {}, t("fre_alta_titulo")),
    h("p", { clase: "sub" }, t("fre_alta_sub")),
    h("div", { clase: "tarjeta" },
      h("h3", {}, t("fre_hoja_titulo")),
      forma.nodo, pieObligatorios(),
      h("div", { clase: "acciones" }, boton,
        h("span", { clase: "chico gris" }, t("fre_alta_pie")))));
}

function datosYCostos(f, recargar) {
  const puede = f.puede || {};
  const bloques = [];

  /* Lo que sale en la hoja: la foto y los datos. */
  const marco = h("div", { clase: "fre-marco" }, foto(f.foto, "fre-foto-grande"));
  const archivo = h("input", { type: "file", accept: "image/*", hidden: "hidden" });
  archivo.addEventListener("change", async () => {
    if (!archivo.files.length) return;
    try {
      const reducida = await reducirImagen(archivo.files[0], 480, 0.82);
      await api.formulario(`/freelance/${f.persona_id}/foto`, { archivo: reducida }, "PUT");
      mensaje(t("fre_foto_puesta"));
      recargar();
    } catch (err) { mensaje(err.message, "grave"); }
  });
  const plazas = h("div");
  const guardar = h("button", { type: "button" }, t("fre_guardar"));
  bloques.push(h("div", { clase: "tarjeta" },
    h("h3", {}, t("fre_hoja_titulo")),
    h("div", { clase: "fre-hoja" },
      h("div", { clase: "fre-lado-foto" }, marco,
        puede.editar
          ? h("button", { type: "button", clase: "claro chico",
                          onclick: () => archivo.click() },
              f.foto ? t("fre_cambiar_foto") : t("fre_subir_foto"))
          : "",
        archivo,
        h("div", { clase: "chico gris" }, t("fre_foto_pie"))),
      h("div", { style: "flex:1" }, plazas,
        h("div", { clase: "chico gris" }, t("fre_experiencia_pie")
          .replace("{h}", (f.horas_en_centauro || 0).toLocaleString())))),
    puede.editar ? h("div", { clase: "acciones" }, guardar) : ""));
  plazasConPais().then((lista_) => {
    const forma = formaDatos(f, lista_);
    if (!puede.editar) {
      for (const c of forma.nodo.querySelectorAll("input,select")) c.disabled = true;
    }
    plazas.replaceChildren(forma.nodo);
    guardar.onclick = async () => {
      const v = forma.valores();
      if (v.tipo === f.tipo) delete v.tipo;
      guardar.disabled = true;
      try {
        await api.patch(`/freelance/${f.persona_id}`, v);
        mensaje(t("fre_guardado"));
        recargar();
      } catch (err) { mensaje(err.message, "grave"); guardar.disabled = false; }
    };
  }).catch((err) => plazas.replaceChildren(aviso(err.message, "grave")));

  /* Sus costos (decisiones 3 y 11): solo eventuales. */
  const c = f.costos || {};
  const cajaCosto = (clave, valor) => h("input", {
    name: clave, inputmode: "decimal", value: valor ?? "",
    disabled: puede.costos ? null : "disabled" });
  const dc = cajaCosto("dia_completo", c.full_day);
  const md = cajaCosto("medio_dia", c.medio_dia);
  const tr = cajaCosto("transfer", c.transfer);
  const he = cajaCosto("hora_extra", c.hora_extra);
  const moneda = f.moneda || "MXN";
  const conSigno = (control) => h("div", { clase: "fre-costo" },
    h("span", {}, moneda), control);
  const guardarCostos = h("button", { type: "button", onclick: async () => {
    const leer = (x) => (x.value.trim() === "" ? null : x.value.trim().replace(/,/g, ""));
    guardarCostos.disabled = true;
    try {
      await api.put(`/freelance/${f.persona_id}/costos`, {
        dia_completo: leer(dc), medio_dia: leer(md), transfer: leer(tr),
        hora_extra: leer(he) });
      mensaje(t("fre_costos_guardados"));
      recargar();
    } catch (err) { mensaje(err.message, "grave"); guardarCostos.disabled = false; }
  } }, t("fre_guardar_costos"));
  bloques.push(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("fre_costos_titulo"), "ay_fre_costos"),
    h("div", { clase: "rejilla cuatro" },
      campo(t("fre_dia_completo"), conSigno(dc), { obligatorio: true }),
      campo(t("fre_medio_dia"), conSigno(md), { obligatorio: true }),
      campo(t("fre_transfer"), conSigno(tr), { obligatorio: true }),
      campo(t("fre_hora_extra"), conSigno(he))),
    h("div", { clase: "chico gris" }, t("fre_costos_pie").replace("{m}", moneda)),
    puede.costos ? h("div", { clase: "acciones" }, guardarCostos)
                 : h("div", { clase: "chico gris" }, t("fre_costos_los_fija"))));

  /* Su acceso a EP Connect: se abre con el expediente listo, o con una
     urgencia autorizada de un servicio vivo; lo dice el servidor
     (`puede_acceso`, seccion 128), con la misma regla que al darlo. */
  const acc = f.acceso;
  let accion = "";
  if (!acc && puede.editar) {
    accion = h("button", { type: "button",
      disabled: (f.puede_acceso ?? f.expediente.asignable) ? null : "disabled",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          await api.post(`/freelance/${f.persona_id}/acceso`);
          mensaje(t("fre_acceso_dado"));
          recargar();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, t("fre_dar_acceso"));
  }
  bloques.push(h("div", { clase: "tarjeta lisa" },
    h("h3", {}, t("fre_acceso_titulo")),
    h("div", { clase: "acciones" }, accion,
      h("span", { clase: "chico gris" },
        acc ? (acc.activo
                 ? (acc.ya_puso_contrasena ? t("fre_acceso_listo")
                                           : t("fre_acceso_sin_contrasena"))
                 : t("fre_acceso_cerrado"))
            : (f.puede_acceso && !f.expediente.asignable
                 ? t("fre_acceso_urgencia") : t("fre_acceso_pie"))))));

  /* La baja: deja de ofrecerse y se le cierra el acceso; el expediente
     se queda (decision 7). */
  if (puede.editar) {
    const motivo = h("input", { name: "motivo_baja", placeholder: t("fre_baja_motivo") });
    bloques.push(h("div", { clase: "tarjeta lisa" },
      h("h3", {}, t("fre_baja_titulo")),
      f.activo
        ? h("div", { clase: "acciones" }, motivo,
            h("button", { type: "button", clase: "claro", onclick: async () => {
              if (motivo.value.trim().length < 5) {
                return mensaje(t("fre_baja_falta_motivo"), "alerta");
              }
              try {
                const r = await api.post(`/freelance/${f.persona_id}/baja`,
                                         { motivo: motivo.value.trim() });
                /* La baja no lo saca de los dias a los que ya estaba
                   asignado (seccion 128): se dice cuantos quedan por
                   cubrir, como en el panel de accesos. */
                const deja = r.jornadas_por_cubrir || [];
                if (deja.length) {
                  mensaje(t("acc_deja_dias")
                    .replace("{n}", deja.reduce((a, x) => a + x.dias, 0))
                    .replace("{s}", deja.length), "alerta");
                } else {
                  mensaje(t("fre_baja_hecha"));
                }
                recargar();
              } catch (err) { mensaje(err.message, "grave"); }
            } }, t("fre_dar_de_baja")))
        : h("div", { clase: "acciones" },
            h("button", { type: "button", onclick: async () => {
              try {
                await api.post(`/freelance/${f.persona_id}/reactivar`);
                recargar();
              } catch (err) { mensaje(err.message, "grave"); }
            } }, t("fre_reactivar"))),
      h("div", { clase: "chico gris" }, t("fre_baja_pie"))));
  }
  return bloques;
}

/* --------------------------------------------------------- el expediente */

async function pintarExpediente(zona, f, recargar) {
  const x = f.expediente;
  if (!f.puede || !f.puede.expediente) {
    const est = estadoFreelance(x);
    return zona.replaceChildren(h("div", { clase: "tarjeta" },
      h("h3", {}, t("fre_exp_titulo")),
      h("p", {}, etiqueta(est.texto, est.tono), " ", est.detalle),
      x.faltan.length
        ? h("p", { clase: "chico" }, t("fre_exp_le_falta"), " ", x.faltan.join(", "))
        : "",
      aviso(t("fre_exp_quien_lo_ve"), "")));
  }
  zona.replaceChildren(h("p", { clase: "gris" }, t("per_cargando")));
  let e;
  try {
    e = await api.get(`/freelance/${f.persona_id}/expediente`);
  } catch (err) {
    return zona.replaceChildren(aviso(err.message, "grave"));
  }
  const r = e.resumen;
  const propios = e.requisitos.filter(q => !q.para_programado);
  const extra = e.requisitos.filter(q => q.para_programado);
  const chips = [
    etiqueta(t("fre_chip_validados").replace("{n}", r.validados), "ok"),
    r.esperan_revision ? etiqueta(t("fre_chip_por_revisar").replace("{n}", r.esperan_revision), "alerta") : "",
    r.por_vencer.length ? etiqueta(t("fre_chip_por_vencer").replace("{n}", r.por_vencer.length), "alerta") : "",
    r.vencidos.length ? etiqueta(t("fre_chip_vencidos").replace("{n}", r.vencidos.length), "grave") : "",
    r.faltan.length ? etiqueta(t("fre_chip_faltan").replace("{n}", r.faltan.length), "grave") : "",
  ];
  const tabla = (filas, numerar) => h("table", { clase: "lista fre-requisitos" },
    h("thead", {}, h("tr", {},
      h("th", {}, ""), h("th", {}, t("fre_col_requisito")),
      h("th", {}, t("fre_col_subido")), h("th", {}, t("fre_col_vigencia")),
      h("th", {}, t("fre_col_estado")), h("th", {}, ""))),
    h("tbody", {}, ...filas.flatMap((q, i) =>
      renglonRequisito(q, numerar ? String(i + 1) : "+", e, f, recargar))));
  const est = estadoFreelance(r);
  zona.replaceChildren(
    h("div", { clase: "tarjeta" },
      h("div", { clase: "fre-cabeza-exp" },
        h("div", {},
          conAyuda("h3", t(`fre_exp_de_${e.tipo}`), "ay_fre_expediente"),
          h("div", { clase: "chico gris" }, t("fre_exp_pie_quien"))),
        h("div", {}, ...chips)),
      h("p", { style: "margin:10px 0" }, etiqueta(est.texto, est.tono), " ",
        h("span", { clase: "chico gris" }, est.detalle)),
      tabla(propios, true),
      h("div", { clase: "chico gris", style: "margin-top:10px" },
        t("fre_exp_pie").replace("{mb}", e.limite_mb))),
    extra.length
      ? h("div", { clase: "tarjeta lisa" },
          h("h3", {}, t("fre_para_programado")),
          h("p", { clase: "chico gris" }, t("fre_para_programado_pie")
            .replace("{f}", r.plazo_programado ? fechaCorta(r.plazo_programado) : "—")),
          tabla(extra, false))
      : "");
}

function vigenciaDe(q) {
  const d = q.efectivo || q.pendiente;
  if (q.vigencia === "servicio") return t("fre_vig_servicio");
  if (!d || !d.vence_en) {
    return q.vigencia === "meses"
      ? t("fre_vig_meses").replace("{n}", q.vigencia_meses)
      : q.vigencia === "documento" ? t("fre_vig_documento") : "—";
  }
  return t("fre_vig_hasta").replace("{f}", fechaCorta(d.vence_en));
}

function queSeSubio(q, e) {
  const d = q.efectivo || q.pendiente;
  if (!d) return h("span", { clase: "gris" }, "—");
  const x = d.datos || {};
  const partes = [];
  if (x.numero_recortado) partes.push(x.numero_recortado);
  if (x.banco) {
    partes.push(t("fre_banco_clabe").replace("{b}", x.banco)
      .replace("{c}", e.ve_cuenta && x.clabe ? x.clabe : x.clabe_recortada));
  }
  if (x.riesgo) partes.push(t("fre_riesgo_n").replace("{n}", x.riesgo));
  if (x.resultado) partes.push(t(`fre_res_${x.resultado}`));
  if (x.quien) partes.push(`${fechaCorta(x.fecha)} · ${x.quien}`);
  if (x.aplico) partes.push(`${t("fre_aplico")} ${x.aplico}`);
  if (x.contactos) partes.push(t("fre_n_contactos").replace("{n}", x.contactos.length));
  if (d.fecha_documento && !x.fecha) partes.push(t("fre_del").replace("{f}", fechaCorta(d.fecha_documento)));
  return h("div", { clase: "chico" },
    ...d.archivos.map(a => h("div", {},
      h("a", { href: "#", clase: "enlace", onclick: (ev) => {
        ev.preventDefault(); abrirArchivo(a);
      } }, a.nombre))),
    partes.length ? h("div", { clase: "gris" }, partes.join(" · ")) : "",
    x.contactos ? h("div", { clase: "gris" },
      x.contactos.map(c => `${c.nombre} (${c.parentesco}) ${c.telefono}`).join(" · ")) : "",
    q.anteriores ? h("div", { clase: "gris" },
      t("fre_anteriores").replace("{n}", q.anteriores)) : "");
}

/* Un PDF o una foto, con sesion: el navegador lo pide por su cuenta y sin
   token si se pone en un enlace a secas. */
async function abrirArchivo(a) {
  try {
    const url = await api.imagen(`/freelance/archivos/${a.id}`);
    window.open(url, "_blank", "noopener");
  } catch (err) { mensaje(err.message, "grave"); }
}

function renglonRequisito(q, numero, e, f, recargar) {
  const forma = h("tr", { hidden: "hidden" },
    h("td", { colspan: "6" }, h("div", { clase: "fre-forma" })));
  const d = q.pendiente && q.pendiente.estado === "por_revisar" ? q.pendiente : null;
  const botones = [];
  if (d && e.puede_validar) {
    botones.push(h("button", { type: "button", clase: "chico", onclick: async (ev) => {
      ev.target.disabled = true;
      try {
        await api.post(`/freelance/documentos/${d.id}/validar`);
        mensaje(t("fre_doc_validado"));
        recargar();
      } catch (err) { mensaje(err.message, "grave"); ev.target.disabled = false; }
    } }, t("fre_validar")));
    botones.push(h("button", { type: "button", clase: "claro chico", onclick: () =>
      abrirRechazo(forma, d, recargar) }, t("fre_rechazar")));
  }
  const textoCargar = q.estado === "falta" ? t("fre_cargar")
    : q.estado === "rechazado" ? t("fre_corregir")
    : q.vigencia === "servicio" ? t("fre_registrar")
    : t("fre_subir_nuevo");
  botones.push(h("button", { type: "button", clase: "claro chico", onclick: () =>
    abrirCarga(forma, q, e, f, recargar) }, textoCargar));

  const estado = q.estado === "caseta" ? t("fre_doc_caseta") : t(`fre_doc_${q.estado}`);
  const nota = q.estado === "rechazado" && q.pendiente
    ? h("div", { clase: "chico gris" }, q.pendiente.motivo_rechazo || "")
    : q.efectivo && q.pendiente && q.pendiente.estado === "por_revisar"
      ? h("div", { clase: "chico gris" }, t("fre_nueva_por_revisar"))
      : q.efectivo && q.pendiente && q.pendiente.estado === "rechazado"
        ? h("div", { clase: "chico gris" }, t("fre_nueva_rechazada")
            .replace("{m}", q.pendiente.motivo_rechazo || ""))
        : "";
  return [
    h("tr", {},
      h("td", { clase: "gris num" }, numero),
      h("td", {}, h("b", {}, q.nombre),
        q.detalle ? h("div", { clase: "chico gris" }, q.detalle) : ""),
      h("td", {}, queSeSubio(q, e)),
      h("td", { clase: "chico" }, vigenciaDe(q)),
      h("td", {}, etiqueta(estado, TONO_DOC[q.estado] || ""), nota),
      h("td", { style: "text-align:right;white-space:nowrap" }, ...botones)),
    forma,
  ];
}

function abrirRechazo(fila, d, recargar) {
  const caja = fila.querySelector(".fre-forma");
  const motivo = h("input", { name: "motivo_rechazo", placeholder: t("fre_motivo_rechazo") });
  caja.replaceChildren(
    campo(t("fre_por_que_rechazo"), motivo, { obligatorio: true }),
    h("div", { clase: "acciones" },
      h("button", { type: "button", onclick: async (ev) => {
        ev.target.disabled = true;
        try {
          await api.post(`/freelance/documentos/${d.id}/rechazar`,
                         { motivo: motivo.value.trim() });
          mensaje(t("fre_doc_rechazado"), "alerta");
          recargar();
        } catch (err) { mensaje(err.message, "grave"); ev.target.disabled = false; }
      } }, t("fre_rechazar")),
      h("button", { type: "button", clase: "claro", onclick: () => { fila.hidden = true; } },
        t("cancelar"))));
  fila.hidden = false;
}

/* La forma de cada requisito: lo que pide su captura y su vigencia. */
function abrirCarga(fila, q, e, f, recargar) {
  const caja = fila.querySelector(".fre-forma");
  const campos = [];
  const datos = {};
  const archivos = h("input", { type: "file", name: "archivos",
                                accept: "application/pdf,image/*",
                                multiple: q.captura === "archivo" ? "multiple" : null });
  const conArchivo = ["archivo", "archivo_numero", "banco", "riesgo"].includes(q.captura);
  if (conArchivo || q.captura === "entrevista") {
    campos.push(campo(t(q.captura === "banco" ? "fre_caratula" : "fre_archivo"), archivos,
                      { obligatorio: conArchivo }));
  }
  if (q.captura === "numero" || q.captura === "archivo_numero") {
    datos.numero = h("input", { name: "numero", "data-mayusculas": "" });
    campos.push(campo(t(q.clave === "rfc" ? "fre_rfc" : "fre_numero"), datos.numero,
                      { obligatorio: true }));
  }
  if (q.captura === "banco") {
    datos.banco = h("input", { name: "banco" });
    datos.clabe = h("input", { name: "clabe", inputmode: "numeric" });
    datos.titular = h("input", { name: "titular", value: f.nombre });
    campos.push(campo(t("fre_banco"), datos.banco, { obligatorio: true }),
                campo(t("fre_clabe"), datos.clabe, { obligatorio: true }),
                campo(t("fre_titular"), datos.titular, { obligatorio: true }));
  }
  if (q.captura === "riesgo") {
    datos.riesgo = lista("riesgo", ["1", "2", "3"].map(n => ({ valor: n, texto: n })));
    campos.push(campo(t("fre_riesgo"), datos.riesgo, { obligatorio: true }));
  }
  if (q.captura === "entrevista") {
    datos.fecha = h("input", { type: "date", name: "fecha" });
    datos.quien = h("input", { name: "quien" });
    datos.resultado = lista("resultado", [
      { valor: "apto", texto: t("fre_apto") }, { valor: "no_apto", texto: t("fre_no_apto") }]);
    datos.notas = h("input", { name: "notas" });
    campos.push(campo(t("fre_fecha_entrevista"), datos.fecha, { obligatorio: true }),
                campo(t("fre_quien_entrevisto"), datos.quien, { obligatorio: true }),
                campo(t("fre_resultado"), datos.resultado, { obligatorio: true }),
                campo(t("fre_notas"), datos.notas));
  }
  const contactos = [];
  if (q.captura === "contactos") {
    for (let i = 0; i < 2; i++) {
      const c = { nombre: h("input", { name: `c${i}_nombre` }),
                  parentesco: h("input", { name: `c${i}_parentesco` }),
                  telefono: h("input", { name: `c${i}_telefono`, inputmode: "tel" }) };
      contactos.push(c);
      campos.push(h("div", { clase: "rejilla tres" },
        campo(t("fre_contacto_n").replace("{n}", i + 1), c.nombre, { obligatorio: true }),
        campo(t("fre_parentesco"), c.parentesco, { obligatorio: true }),
        campo(t("fre_telefono"), c.telefono, { obligatorio: true })));
    }
  }
  if (q.captura === "prueba") {
    datos.resultado = lista("resultado_prueba", [
      { valor: "negativo", texto: t("fre_res_negativo") },
      { valor: "positivo", texto: t("fre_res_positivo") }]);
    datos.aplico = h("input", { name: "aplico" });
    datos.servicio = h("input", { name: "servicio", placeholder: "EP/E-031" });
    campos.push(campo(t("fre_resultado"), datos.resultado, { obligatorio: true }),
                campo(t("fre_quien_aplico"), datos.aplico, { obligatorio: true }),
                campo(t("fre_servicio"), datos.servicio));
  }
  const fechaDoc = h("input", { type: "date", name: "fecha_documento" });
  const vence = h("input", { type: "date", name: "vence_en" });
  if (q.vigencia === "meses" || q.vigencia === "servicio") {
    campos.push(campo(t(q.vigencia === "servicio" ? "fre_fecha_prueba" : "fre_fecha_documento"),
                      fechaDoc, { obligatorio: q.vigencia === "meses" }));
  }
  if (q.vigencia === "documento") {
    campos.push(campo(t("fre_vence_el"), vence, { obligatorio: true }));
  }
  const validar = h("input", { type: "checkbox", name: "validar" });
  validar.checked = !!e.puede_validar;
  const guardar = h("button", { type: "button", onclick: async () => {
    const valores = {};
    for (const [k, control] of Object.entries(datos)) valores[k] = control.value.trim();
    if (contactos.length) {
      valores.contactos = contactos.map(c => ({
        nombre: c.nombre.value.trim(), parentesco: c.parentesco.value.trim(),
        telefono: c.telefono.value.trim() }));
    }
    const envio = { datos: JSON.stringify(valores),
                    validar: validar.checked ? "true" : "false" };
    if (fechaDoc.value) envio.fecha_documento = fechaDoc.value;
    if (vence.value) envio.vence_en = vence.value;
    guardar.disabled = true;
    try {
      const listos = [];
      for (const a of archivos.files || []) {
        listos.push(a.type.startsWith("image/") && a.size > 1500000
          ? await reducirImagen(a, 2200, 0.85) : a);
      }
      envio.archivos = listos;
      const r = await api.formulario(
        `/freelance/${f.persona_id}/expediente/${q.requisito_id}`, envio);
      mensaje(t(r.estado === "validado" ? "fre_doc_cargado_validado"
                : r.estado === "rechazado" ? "fre_doc_cargado_rechazado"
                : "fre_doc_cargado"), r.estado === "rechazado" ? "alerta" : "ok");
      recargar();
    } catch (err) { mensaje(err.message, "grave"); guardar.disabled = false; }
  } }, t("fre_guardar"));
  caja.replaceChildren(
    h("div", { clase: "rejilla dos" }, ...campos),
    e.puede_validar && q.captura !== "prueba"
      ? h("label", { clase: "casilla" }, validar, " ", t("fre_ya_lo_revise"))
      : h("div", { clase: "chico gris" }, t(q.captura === "prueba"
          ? "fre_prueba_pie" : "fre_lo_valida_rh")),
    h("div", { clase: "acciones" }, guardar,
      h("button", { type: "button", clase: "claro", onclick: () => { fila.hidden = true; } },
        t("cancelar"))));
  fila.hidden = false;
}

/* ---------------------------------------------- servicios e historial */

function servicios(f) {
  const urg = f.urgencias || [];
  return h("div", {},
    h("div", { clase: "tarjeta lisa" },
      h("h3", {}, t("fre_servicios_titulo")),
      f.servicios.length
        ? h("table", {},
            h("thead", {}, h("tr", {},
              h("th", {}, t("enc_servicio")), h("th", {}, t("per_cliente")),
              h("th", {}, t("fre_col_fechas")), h("th", {}, t("fre_col_dias")))),
            h("tbody", {}, ...f.servicios.map(s => h("tr", {},
              h("td", {}, h("a", { href: `#/servicio/${s.servicio_id}` }, s.folio)),
              h("td", { clase: "chico" }, s.cliente || "—"),
              h("td", { clase: "chico gris" },
                s.desde === s.hasta ? fechaCorta(s.desde)
                  : `${fechaCorta(s.desde)} – ${fechaCorta(s.hasta)}`),
              h("td", { clase: "num" }, String(s.dias))))))
        : h("div", { clase: "vacio" }, t("fre_sin_servicios"))),
    urg.length
      ? h("div", { clase: "tarjeta lisa" },
          h("h3", {}, t("fre_urgencias_titulo")),
          ...urg.map(u => h("div", { clase: "caso" },
            h("div", { clase: "cabeza_caso" },
              h("div", {},
                h("a", { href: u.ruta }, u.folio || "—"),
                h("span", { clase: "chico gris" }, ` · ${u.pidio || "—"} · ${fechaCorta(u.pedida_en)}`)),
              etiqueta(t(`fre_urg_${u.estado}`),
                       u.estado === "autorizada" ? "ok" : u.estado === "pedida" ? "alerta" : "grave")),
            h("div", { clase: "chico" }, u.motivo),
            u.respuesta ? h("div", { clase: "chico gris" },
              `${u.resolvio || ""}: ${u.respuesta}`) : "")))
      : "");
}

function historial(f) {
  return h("div", { clase: "tarjeta lisa" },
    h("h3", {}, t("fre_historial_titulo")),
    f.historial.length
      ? h("table", {},
          h("tbody", {}, ...f.historial.map(x => h("tr", {},
            h("td", { clase: "chico gris" }, fechaCorta(x.cuando)),
            h("td", { clase: "chico" }, x.quien || "—"),
            h("td", { clase: "chico" },
              h("b", {}, t(`fre_h_${x.accion.replace(/ /g, "_")}`)),
              x.detalle ? ` · ${x.detalle}` : "",
              x.despues && x.accion !== "documento cargado" ? ` · ${x.despues}` : "")))))
      : h("div", { clase: "vacio" }, t("fre_historial_vacio")));
}

/* ======================================== en la lista de a quien asignar */

/* Lo que la lista de asignar dice de un freelance, y si se le deja el
   boton. `recargar` vuelve a pedir la lista cuando la urgencia cambia
   algo. */
export function avisoFreelance(p, recargar) {
  const x = p.freelance;
  if (!x) return { nodo: "", asignable: true };
  const costo = x.costos && x.costos.full_day !== null && x.costos.full_day !== undefined
    ? ` · ${t("fre_dia_completo").toLowerCase()} ${dinero(x.costos.full_day, x.moneda)}` : "";
  if (x.asignable) {
    if (x.motivo === "autorizada") {
      return { asignable: true, nodo: aviso(t("fre_asg_autorizada"), "ok fre-aviso") };
    }
    if (x.plazo) {
      return { asignable: true, nodo: aviso(t("fre_asg_plazo")
        .replace("{f}", fechaCorta(x.plazo)), "alerta fre-aviso") };
    }
    return { asignable: true, nodo: aviso(t("fre_asg_listo") + costo, "ok fre-aviso") };
  }
  const a = x.autorizacion;
  let accion = "";
  if (a && a.estado === "pedida") {
    accion = h("div", { clase: "chico gris" }, t("fre_asg_pedida"));
  } else if (x.puede_pedir && tiene(sesion.usuario, "asignaciones.mover")) {
    accion = h("button", { type: "button", clase: "claro chico", onclick: () =>
      pedirUrgencia(accion, p, x.servicio_id, recargar) },
      tiene(sesion.usuario, "freelance.autorizar") ? t("fre_autorizar_urgencia")
                                                   : t("fre_pedir_autorizacion"));
  }
  return {
    asignable: false,
    nodo: h("div", {},
      aviso(x.mensaje || t("fre_asg_no"), "grave fre-aviso"),
      a && a.estado === "rechazada"
        ? h("div", { clase: "chico gris" }, t("fre_asg_rechazada")
            .replace("{r}", a.respuesta || ""))
        : "",
      accion),
  };
}

function pedirUrgencia(ancla, p, servicioId, recargar) {
  const motivo = h("input", { name: "motivo_urgencia", placeholder: t("fre_motivo_urgencia") });
  const caja = h("div", { clase: "fre-urgencia" },
    motivo,
    h("button", { type: "button", clase: "chico", onclick: async (ev) => {
      if (motivo.value.trim().length < 10) {
        return mensaje(t("fre_urgencia_falta_motivo"), "alerta");
      }
      ev.target.disabled = true;
      try {
        const r = await api.post(`/freelance/${p.persona_id}/urgencias`,
                                 { servicio_id: servicioId, motivo: motivo.value.trim() });
        mensaje(t(r.estado === "autorizada" ? "fre_urgencia_autorizada"
                                            : "fre_urgencia_pedida"));
        if (recargar) await recargar();
      } catch (err) { mensaje(err.message, "grave"); ev.target.disabled = false; }
    } }, t("fre_mandar")));
  ancla.replaceWith(caja);
  motivo.focus();
}

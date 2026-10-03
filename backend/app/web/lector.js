/* El lector de noticias y redes en la consola (seccion 140).

   La pestana Lector del mapa de riesgo, como los bocetos aprobados el 3
   de octubre. A la izquierda lo que encontro el lector y espera una mano,
   lo mas grave primero; a la derecha la ficha del hallazgo: lo que
   entendio Connect, las otras notas del mismo hecho y las tres salidas
   --crear el evento, sumarlo a uno que ya existe, descartarlo con su
   motivo--. Abajo, lo que lee: sus fuentes y el tope de X.

   Nada se publica desde aqui. Crear el evento lo deja propuesto, con las
   notas como fuentes, y abre su ficha en Mapa y eventos para que el
   analista escriba el texto del cliente y lo publique como siempre. */
import { api } from "./api.js";
import { aviso, campo, entrada, h, lista, mensaje } from "./util.js";
import { t } from "./idioma.js";

const COLOR = { 1: "#5f7187", 2: "#c99a06", 3: "#e07000", 4: "#c62828" };
const MOTIVOS = ["no_es_seguridad", "ya_paso", "repetida", "fuera_de_mexico",
                 "sin_importancia"];
const REFRESCO_SEGUNDOS = 60;
const EN_LA_LISTA = 12;

function nivel(n) {
  if (!n) return h("span", { clase: "etiqueta" }, t("lec_sin_nivel"));
  const chip = h("span", { clase: "rsg-nivel" }, `${n} · ${t(`rsg_nivel_${n}`)}`);
  chip.style.background = COLOR[n];
  return chip;
}

function hace(iso) {
  if (!iso) return "";
  const min = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (min < 60) return t("lec_hace_min").replace("{n}", min);
  if (min < 24 * 60) return t("lec_hace_h").replace("{n}", Math.round(min / 60));
  return t("lec_hace_d").replace("{n}", Math.round(min / 1440));
}

/* Cuando Claude no contesta, la consola lo dice (seccion 141): que paso,
   desde cuando, cuantas notas esperan y que hacer. Lo pasajero (saturado,
   sin conexion) va en amarillo; lo que pide una mano, en rojo. */
const QUE_HACER = { llave: "lec_ia_hacer_llave", espacio: "lec_ia_hacer_llave",
                    saldo: "lec_ia_hacer_saldo", saturado: "lec_ia_hacer_esperar",
                    red: "lec_ia_hacer_esperar", otro: "lec_ia_hacer_otro" };

function avisoDeClaude(ia) {
  if (!ia) return null;
  const falla = QUE_HACER[ia.falla] ? ia.falla : "otro";
  const pasajero = falla === "saturado" || falla === "red";
  return aviso([
    h("div", {}, h("b", {}, t("lec_ia_titulo")), " ",
      t("lec_ia_dijo").replace("{que}", t(`lec_ia_${falla}`)).replace("{hace}", hace(ia.desde))),
    h("div", { clase: "chico lec-ia-sub" },
      t("lec_ia_esperan").replace("{n}", ia.esperan.toLocaleString()), " ",
      t(QUE_HACER[falla]).replace("{detalle}", ia.detalle || "")),
  ], pasajero ? "alerta" : "grave");
}

/* Solo enlaces http(s): lo demas no se pica. El servidor ya los limpia;
   esto es la segunda puerta. */
function seguro(url) {
  return /^https?:\/\//i.test(url || "") ? url : null;
}

function horaDe(iso) {
  return iso ? iso.slice(11, 16) : "";
}

function dondeDe(x) {
  return [x.region, x.municipio].filter(Boolean).join(" · ") || t("lec_sin_lugar");
}

/* ------------------------------------------------------------ la mesa */

export async function mesaDelLector(cuerpo, ctx) {
  if (ctx.pais.codigo !== "MX") {
    cuerpo.replaceChildren(aviso(t("lec_solo_mx"), "alerta"));
    return;
  }
  const estado = { abierto: null, vista: "revisar", cuantos: EN_LA_LISTA, ia: null };
  const izquierda = h("div", { clase: "rsg-cola lec-cola" });
  const derecha = h("div");
  const mesa = h("div", { clase: "rsg-mesa" }, izquierda, derecha);
  cuerpo.replaceChildren(mesa);

  const pintar = async () => {
    if (estado.vista === "fuentes") {
      await pintarFuentes(cuerpo, ctx, () => { estado.vista = "revisar"; cuerpo.replaceChildren(mesa); pintar(); });
      return;
    }
    let datos;
    try {
      datos = await api.get("/riesgo/lector");
    } catch (e) {
      izquierda.replaceChildren(aviso(e.message, "grave"));
      return;
    }
    ctx.contar(datos.hallazgos.length);
    estado.ia = datos.ia;
    pintarCola(izquierda, datos, estado, (id) => abrir(id), () => {
      estado.vista = "fuentes";
      pintar();
    });
    if (!estado.abierto || !datos.hallazgos.some((x) => x.id === estado.abierto)) {
      estado.abierto = datos.hallazgos.length ? datos.hallazgos[0].id : null;
      await pintarFicha();
    }
    marcar();
  };

  const marcar = () => {
    for (const b of izquierda.querySelectorAll("[data-hallazgo]")) {
      b.classList.toggle("lec-elegido", Number(b.dataset.hallazgo) === estado.abierto);
    }
  };

  const pintarFicha = async () => {
    if (!estado.abierto) {
      derecha.replaceChildren(h("div", { clase: "tarjeta lec-ficha" },
        h("p", { clase: "gris" }, t(estado.ia ? "lec_nada_sin_ia" : "lec_nada"))));
      return;
    }
    let hallazgo;
    try {
      hallazgo = await api.get(`/riesgo/lector/hallazgos/${estado.abierto}`);
    } catch (e) {
      derecha.replaceChildren(aviso(e.message, "grave"));
      return;
    }
    derecha.replaceChildren(await ficha(hallazgo, ctx, async () => {
      estado.abierto = null;
      await pintar();
    }));
  };

  const abrir = async (id) => {
    estado.abierto = id;
    marcar();
    await pintarFicha();
  };

  await pintar();
  ctx.cadaMinuto(async () => {
    if (!document.body.contains(cuerpo)) return;
    if (estado.vista !== "revisar") return;
    if (derecha.querySelector("[data-editando]")) return;
    const foco = document.activeElement;
    if (foco && derecha.contains(foco) && ["INPUT", "SELECT"].includes(foco.tagName)) return;
    await pintar();
  }, REFRESCO_SEGUNDOS * 1000);
}

function pintarCola(izquierda, datos, estado, alAbrir, alFuentes) {
  const filas = datos.hallazgos.slice(0, estado.cuantos).map((x) => h("button", {
    type: "button", clase: "rsg-renglon lec-renglon", "data-hallazgo": x.id,
    onclick: () => alAbrir(x.id) },
    h("span", { clase: "lec-arriba" }, nivel(x.nivel),
      h("span", { clase: "chico gris" },
        `${hace(x.primera ? x.primera.publicada_en : x.creado_en)} · `,
        x.primera ? x.primera.medio : ""),
      x.notas_n > 1 ? h("span", { clase: "etiqueta info" },
        t("lec_mas_notas").replace("{n}", x.notas_n - 1)) : null),
    h("b", { clase: "lec-titulo" }, x.titulo),
    h("span", { clase: "chico gris" }, [x.tipo, dondeDe(x)].filter(Boolean).join(" · "))));
  const mas = datos.hallazgos.length > estado.cuantos
    ? h("button", { type: "button", clase: "claro chico",
                    onclick: () => { estado.cuantos = datos.hallazgos.length; pintarCola(izquierda, datos, estado, alAbrir, alFuentes); } },
        t("lec_ver_los").replace("{n}", datos.hallazgos.length))
    : null;
  const hoy = datos.hoy;
  const avisos = [avisoDeClaude(datos.ia)];
  if (!datos.llaves.ia) avisos.push(aviso(t("lec_sin_ia"), "alerta"));
  if (datos.pausado) avisos.push(aviso(t("lec_pausado"), "alerta"));
  izquierda.replaceChildren(...[
    ...avisos,
    h("h3", {}, t("lec_por_revisar").replace("{n}", datos.hallazgos.length)),
    ...filas,
    datos.hallazgos.length ? null : h("p", { clase: "chico gris" }, t("lec_nada_por_revisar")),
    mas,
    h("h3", {}, t("lec_hoy")),
    h("div", { clase: "chico gris lec-hoy" }, t("lec_hoy_cuenta")
      .replace("{leidas}", hoy.leidas.toLocaleString()).replace("{fuentes}", hoy.fuentes)
      .replace("{parecian}", hoy.parecian).replace("{revisar}", datos.hallazgos.length)
      .replace("{eventos}", hoy.eventos).replace("{descartados}", hoy.descartados),
      ...(datos.ia ? [" · ", h("b", { clase: "rojo" },
        t("lec_hoy_esperan").replace("{n}", datos.ia.esperan.toLocaleString()))] : [])),
    h("button", { type: "button", clase: "claro chico", onclick: alFuentes }, t("lec_ver_fuentes")),
  ].filter(Boolean));
}

/* ------------------------------------------------------------ la ficha */

async function ficha(x, ctx, alTerminar) {
  const cat = await ctx.catalogos();
  const puede = ctx.puedePublicar;
  const salida = h("div");
  const primera = x.primera;

  // Lo que falta para crear el evento, lo elige el analista aqui mismo.
  const selTipo = lista("tipo_id", [{ valor: "", texto: t("lec_elige_tipo") },
    ...cat.tipos.filter((y) => y.activo).map((y) => ({ valor: y.id, texto: y.nombre }))]);
  const selRegion = lista("region_id", [{ valor: "", texto: t("lec_elige_estado") },
    ...cat.regiones.map((y) => ({ valor: y.id, texto: y.nombre }))]);
  const selNivel = lista("nivel", [{ valor: "", texto: t("lec_elige_nivel") },
    ...[1, 2, 3, 4].map((n) => ({ valor: n, texto: `${n} · ${t(`rsg_nivel_${n}`)}` }))]);

  const filas = [
    [t("lec_tipo"), x.tipo ? h("b", {}, x.tipo) : (puede ? selTipo : "—")],
    [t("lec_donde"), x.region
      ? h("span", {}, h("b", {}, dondeDe(x)), x.lugar ? ` · ${x.lugar}` : "",
          x.lat !== null ? h("span", { clase: "chico gris" }, ` ${t("lec_punto_aprox")}`) : null)
      : (puede ? selRegion : "—")],
    [t("lec_cuando"), h("span", {}, x.ocurrio_en ? t("lec_desde").replace("{hora}", horaDe(x.ocurrio_en)) : "—",
      x.sigue === true ? h("span", { clase: "chico gris" }, ` · ${t("lec_sigue")}`) : null)],
    [t("lec_nivel_sugerido"), x.nivel
      ? h("span", {}, nivel(x.nivel), x.razon ? h("span", { clase: "chico gris" }, ` ${x.razon}`) : null)
      : (puede ? selNivel : "—")],
    [t("lec_cerca"), cercaDe(x.cerca)],
  ];
  const otras = x.notas.slice(1);

  const acciones = h("div", { clase: "acciones lec-acciones" });
  if (puede) {
    const crear = h("button", { type: "button" }, t("lec_crear"));
    crear.onclick = async () => {
      crear.disabled = true;
      const cambios = {};
      if (!x.tipo_id && selTipo.value) cambios.tipo_id = Number(selTipo.value);
      if (!x.region_id && selRegion.value) cambios.region_id = Number(selRegion.value);
      if (!x.nivel && selNivel.value) cambios.nivel = Number(selNivel.value);
      try {
        const evento = await api.post(`/riesgo/lector/hallazgos/${x.id}/evento`, cambios);
        mensaje(t("lec_creado").replace("{folio}", evento.folio));
        await ctx.abrirEnMapa(evento.id);
      } catch (e) {
        salida.replaceChildren(aviso(e.message, "grave"));
        crear.disabled = false;
      }
    };
    const sumar = h("button", { type: "button", clase: "claro" }, t("lec_sumar"));
    sumar.onclick = async () => {
      salida.replaceChildren(await elegirEvento(x, ctx, alTerminar));
    };
    const descartar = h("button", { type: "button", clase: "claro" }, t("lec_descartar"));
    descartar.onclick = () => {
      salida.replaceChildren(h("div", { clase: "lec-motivos", "data-editando": "1" },
        h("span", { clase: "chico gris" }, t("lec_por_que")), " ",
        MOTIVOS.map((mo) => h("button", { type: "button", clase: "claro chico", onclick: async () => {
          try {
            await api.post(`/riesgo/lector/hallazgos/${x.id}/descartar`, { motivo: mo });
            mensaje(t("lec_descartado"));
            await alTerminar();
          } catch (e) {
            salida.replaceChildren(aviso(e.message, "grave"));
          }
        } }, t(`lec_motivo_${mo}`)))));
    };
    if (x.evento_folio) acciones.append(sumarDirecto(x, alTerminar, salida));
    acciones.append(crear, sumar, descartar);
  }

  return h("div", { clase: "tarjeta lec-ficha" },
    h("div", { clase: "rsg-cabeza" }, nivel(x.nivel),
      h("span", { clase: x.con_ia ? "etiqueta alerta" : "etiqueta" },
        x.con_ia ? t("lec_sugiere") : t("lec_por_palabras")),
      primera ? h("span", { clase: "chico gris" },
        `${primera.medio} · ${horaDe(primera.publicada_en)} · ${hace(primera.publicada_en)}`) : null),
    h("h2", { clase: "lec-titular" }, x.titulo),
    h("p", { clase: "chico lec-resumen" }, x.resumen || x.texto || (primera ? primera.titulo : ""), " ",
      primera && seguro(primera.url) ? h("a", { clase: "enlace", href: seguro(primera.url), target: "_blank", rel: "noopener" },
        t("lec_leer_nota")) : null),
    x.evento_folio ? aviso(t("lec_parece").replace("{folio}", x.evento_folio), "alerta") : null,
    h("h3", {}, x.con_ia ? t("lec_entendio") : t("lec_que_dice")),
    h("table", { clase: "fondo-tabla" }, h("tbody", {},
      filas.map(([k, v]) => h("tr", {}, h("td", { clase: "gris lec-clave" }, k), h("td", {}, v))))),
    otras.length ? [
      h("h3", {}, t("lec_otras").replace("{n}", otras.length)),
      h("table", { clase: "fondo-tabla" }, h("tbody", {}, otras.map((n) => h("tr", {},
        h("td", {}, n.medio, n.oficial ? h("span", { clase: "chico gris" }, ` (${t("lec_oficial")})`) : null),
        h("td", { clase: "chico" }, seguro(n.url)
          ? h("a", { href: seguro(n.url), target: "_blank", rel: "noopener" }, n.titulo) : n.titulo),
        h("td", { clase: "chico gris" }, hace(n.publicada_en))))))] : null,
    puede ? aviso(t("lec_al_crear")) : aviso(t("lec_solo_ver")),
    acciones,
    h("div", { clase: "chico gris lec-pie" }, t("lec_motivos_pie")),
    salida);
}

function cercaDe(cerca) {
  const partes = [];
  if (cerca.clientes) partes.push(t("lec_clientes").replace("{n}", cerca.clientes));
  if (cerca.servicio) {
    partes.push(t("lec_servicio").replace("{km}", cerca.servicio.km)
      .replace("{folio}", cerca.servicio.folio || "—"));
  }
  return partes.length ? partes.join(" · ") : h("span", { clase: "gris" }, t("lec_nadie_cerca"));
}

function sumarDirecto(x, alTerminar, salida) {
  const boton = h("button", { type: "button" }, t("lec_sumar_a").replace("{folio}", x.evento_folio));
  boton.onclick = async () => {
    boton.disabled = true;
    try {
      await api.post(`/riesgo/lector/hallazgos/${x.id}/sumar`, { evento_id: x.evento_id });
      mensaje(t("lec_sumado").replace("{folio}", x.evento_folio));
      await alTerminar();
    } catch (e) {
      salida.replaceChildren(aviso(e.message, "grave"));
      boton.disabled = false;
    }
  };
  return boton;
}

async function elegirEvento(x, ctx, alTerminar) {
  let vivos = [];
  try {
    const m = await api.get(`/riesgo/mapa?pais_id=${ctx.pais.id}`);
    vivos = [...(m.cola || []), ...(m.publicados || [])];
  } catch (e) {
    return aviso(e.message, "grave");
  }
  if (!vivos.length) return aviso(t("lec_sin_eventos"), "alerta");
  // Los del mismo estado primero.
  vivos.sort((a, b) => (b.region_id === x.region_id) - (a.region_id === x.region_id));
  const sel = lista("evento", vivos.map((e) => ({ valor: e.id, texto: `${e.folio} · ${e.titulo} · ${e.region}` })));
  const salida = h("div");
  const listo = h("button", { type: "button" }, t("lec_sumar_aqui"));
  listo.onclick = async () => {
    listo.disabled = true;
    try {
      const e = await api.post(`/riesgo/lector/hallazgos/${x.id}/sumar`, { evento_id: Number(sel.value) });
      mensaje(t("lec_sumado").replace("{folio}", e.folio));
      await alTerminar();
    } catch (err) {
      salida.replaceChildren(aviso(err.message, "grave"));
      listo.disabled = false;
    }
  };
  return h("div", { clase: "rsg-linea", "data-editando": "1" }, campo(t("lec_a_cual"), sel), listo, salida);
}

/* ------------------------------------------------------------ las fuentes */

const NOMBRE_TIPO = { medio: "lec_tipo_medio", busqueda: "lec_tipo_busqueda", lista_x: "lec_tipo_lista_x" };
const EN_LA_TABLA = 12;

async function pintarFuentes(cuerpo, ctx, alVolver) {
  let datos;
  try {
    datos = await api.get("/riesgo/lector/fuentes");
  } catch (e) {
    cuerpo.replaceChildren(aviso(e.message, "grave"));
    return;
  }
  const volver = h("button", { type: "button", clase: "enlace", onclick: alVolver }, t("lec_volver"));
  const salida = h("div");
  const cuerpoTabla = h("tbody");
  const filas = datos.fuentes.map((f) => h("tr", {},
    h("td", {}, h("b", {}, f.nombre), f.oficial ? h("span", { clase: "chico gris" }, ` (${t("lec_oficial")})`) : null),
    h("td", {}, t(NOMBRE_TIPO[f.tipo])),
    h("td", { clase: "chico" }, f.regiones.length ? f.regiones.join(", ") : t("lec_nacional")),
    h("td", { clase: "chico" }, t("lec_cada").replace("{n}", f.cada_min)),
    h("td", { clase: "chico" }, f.leida_en ? hace(f.leida_en) : "—"),
    h("td", {}, String(f.leidas_hoy)), h("td", {}, String(f.propuso_hoy)),
    h("td", {}, estadoDe(f)),
    h("td", {}, ctx.puedeFuentes ? h("button", { type: "button", clase: "claro chico", onclick: async () => {
      try {
        await api.patch(`/riesgo/lector/fuentes/${f.id}`, { activa: !f.activa });
        await pintarFuentes(cuerpo, ctx, alVolver);
      } catch (e) {
        salida.replaceChildren(aviso(e.message, "grave"));
      }
    } }, f.activa ? t("lec_apagar") : t("lec_encender")) : null)));
  const mostrar = (cuantos) => {
    cuerpoTabla.replaceChildren(...filas.slice(0, cuantos));
  };
  mostrar(EN_LA_TABLA);
  const verTodas = filas.length > EN_LA_TABLA
    ? h("button", { type: "button", clase: "claro chico",
                    onclick: (ev) => { mostrar(filas.length); ev.target.remove(); } },
        t("lec_ver_las").replace("{n}", filas.length))
    : null;

  const llaves = [avisoDeClaude(datos.ia)].filter(Boolean);
  if (!datos.llaves.ia) llaves.push(aviso(t("lec_sin_ia"), "alerta"));
  if (!datos.llaves.x) llaves.push(aviso(t("lec_sin_x"), "alerta"));

  const tope = entrada("tope", { type: "number", min: "0", max: "100000", step: "100",
                                 value: String(datos.tope_x_dia), clase: "lec-tope" });
  const pausa = h("button", { type: "button", clase: "claro" }, datos.pausado ? t("lec_reanudar") : t("lec_pausar"));
  const guardarTope = h("button", { type: "button", clase: "claro" }, t("lec_guardar_tope"));
  const cambiar = async (cuerpoPedido) => {
    try {
      await api.put("/riesgo/lector/parametros", cuerpoPedido);
      await pintarFuentes(cuerpo, ctx, alVolver);
    } catch (e) {
      salida.replaceChildren(aviso(e.message, "grave"));
    }
  };
  guardarTope.onclick = () => cambiar({ tope_x_dia: Number(tope.value) });
  pausa.onclick = () => cambiar({ pausado: !datos.pausado });

  /* Lo que Connect publica solo (seccion 143). Quien no lleva el
     catalogo lo ve, pero no lo mueve. */
  const solos = datos.solos;
  const casilla = (clave, texto, sangria) => {
    const caja = h("input", { type: "checkbox", name: `solo_${clave}` });
    caja.checked = !!solos[clave];
    caja.disabled = !ctx.puedeFuentes;
    return [caja, h("label", { clase: sangria ? "casilla lec-solo-regla" : "casilla" }, caja, " ", texto)];
  };
  const [cActivo, lActivo] = casilla("activo", t("lec_solo_activo"), false);
  const [cOficial, lOficial] = casilla("oficial", t("lec_solo_oficial"), true);
  const [cConfirmado, lConfirmado] = casilla("confirmado", t("lec_solo_confirmado"), true);
  const [cInformativo, lInformativo] = casilla("informativo", t("lec_solo_informativo"), true);
  /* Seccion 147: lo de nivel 3 y 4 muy confirmado, al momento. */
  const [cAlto, lAlto] = casilla("alto", t("lec_solo_alto"), true);
  const [cCritico, lCritico] = casilla("critico", t("lec_solo_critico"), true);
  const guardarSolos = h("button", { type: "button", clase: "claro" }, t("lec_solo_guardar"));
  guardarSolos.onclick = async () => {
    guardarSolos.disabled = true;
    try {
      await api.put("/riesgo/lector/parametros", {
        solo_activo: cActivo.checked, solo_oficial: cOficial.checked,
        solo_confirmado: cConfirmado.checked, solo_informativo: cInformativo.checked,
        solo_alto: cAlto.checked, solo_critico: cCritico.checked });
      mensaje(t("lec_solo_guardado"));
      await pintarFuentes(cuerpo, ctx, alVolver);
    } catch (e) {
      salida.replaceChildren(aviso(e.message, "grave"));
      guardarSolos.disabled = false;
    }
  };
  const hoySolos = solos.hoy;
  const bloqueSolos = [
    h("h3", {}, t("lec_solo_titulo")),
    h("p", { clase: "chico gris" }, t("lec_solo_sub")),
    h("div", { clase: "lec-solo-reglas" }, lActivo, lOficial, lConfirmado, lInformativo, lAlto, lCritico,
      ctx.puedeFuentes ? h("div", {}, guardarSolos) : null),
    h("p", { clase: "chico gris" }, t("lec_solo_siempre")),
    h("div", { clase: "chico" }, h("b", {}, t("lec_solo_hoy").replace("{total}", hoySolos.total)),
      hoySolos.total ? h("span", { clase: "gris" }, " · ", t("lec_solo_hoy_detalle")
        .replace("{oficial}", hoySolos.oficial).replace("{confirmado}", hoySolos.confirmado)
        .replace("{informativo}", hoySolos.informativo).replace("{cerrados}", hoySolos.cerrados)
        .replace("{alto}", hoySolos.alto).replace("{critico}", hoySolos.critico)) : null),
  ];

  const tipo = lista("tipo", Object.keys(NOMBRE_TIPO).map((k) => ({ valor: k, texto: t(`${NOMBRE_TIPO[k]}_largo`) })));
  const direccion = entrada("direccion", { "data-crudo": "", placeholder: t("lec_ph_direccion") });
  const nombre = entrada("nombre", { placeholder: t("lec_ph_nombre") });
  const estados = entrada("estados", { placeholder: t("lec_ph_estados") });
  const oficial = h("input", { type: "checkbox", name: "oficial" });
  const agregar = h("button", { type: "button" }, t("lec_agregar"));
  agregar.onclick = async () => {
    agregar.disabled = true;
    try {
      await api.post("/riesgo/lector/fuentes", {
        tipo: tipo.value, direccion: direccion.value, nombre: nombre.value || null,
        regiones: estados.value.split(",").map((x) => x.trim()).filter(Boolean),
        oficial: oficial.checked });
      mensaje(t("lec_fuente_agregada"));
      await pintarFuentes(cuerpo, ctx, alVolver);
    } catch (e) {
      salida.replaceChildren(aviso(e.message, "grave"));
      agregar.disabled = false;
    }
  };

  const pagina = h("div", {},
    volver,
    h("div", { clase: "tarjeta lec-ficha" },
      h("h3", {}, t("lec_lo_que_lee").replace("{n}", datos.fuentes.filter((f) => f.activa).length)),
      h("p", { clase: "chico gris" }, t("lec_lo_que_lee_sub")),
      ...llaves,
      h("table", { clase: "fondo-tabla" },
        h("thead", {}, h("tr", {}, ["lec_col_fuente", "lec_col_tipo", "lec_col_cubre", "lec_col_cada",
          "lec_col_ultima", "lec_col_leidas", "lec_col_propuso", "", ""].map((k) => h("th", {}, k ? t(k) : "")))),
        cuerpoTabla),
      verTodas,
      ...bloqueSolos,
      h("h3", {}, t("lec_x_titulo")),
      h("p", { clase: "chico gris" }, t("lec_x_cuenta").replace("{hoy}", datos.x_hoy).replace("{tope}", datos.tope_x_dia)),
      ctx.puedeFuentes ? h("div", { clase: "rsg-linea" }, campo(t("lec_tope"), tope), guardarTope, pausa) : null,
      ctx.puedeFuentes ? [
        h("h3", {}, t("lec_agregar_titulo")),
        h("div", { clase: "rsg-linea" }, tipo, direccion, nombre, estados,
          h("label", { clase: "casilla" }, oficial, " ", t("lec_es_oficial")), agregar),
        h("p", { clase: "chico gris" }, t("lec_agregar_ayuda"))] : null,
      salida));
  cuerpo.replaceChildren(pagina);
}

function estadoDe(f) {
  if (!f.activa) return h("span", { clase: "etiqueta" }, t("lec_apagada"));
  if (f.error) {
    const chip = h("span", { clase: "etiqueta grave" }, t("lec_error"));
    chip.title = f.error;
    return h("span", {}, chip, h("div", { clase: "chico gris" }, f.error));
  }
  if (!f.leida_en) return h("span", { clase: "etiqueta" }, t("lec_por_leer"));
  return h("span", { clase: "etiqueta ok" }, t("lec_leyendo"));
}

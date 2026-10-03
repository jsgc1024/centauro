/* El riesgo de fondo en la consola: el Nivel Centauro (seccion 135).

   La tercera pestana del mapa de riesgo, en el orden de los bocetos
   aprobados el 2 de octubre:

   - Arriba, si hay un mes calculado sin publicar y quien mira es
     analista: el borrador. De donde salio cada dato, lo que hay que ver
     antes de publicarlo (lo que se movio mas de 10 puntos, lo que cambio
     de rango, lo que no tuvo reporte) con su Ajustar, y el boton del
     jefe de turno.
   - Luego el mes publicado --el que ve el cliente--: los estados del mas
     alto al mas bajo, el mapa pintado y la ficha del estado elegido con
     como se compone su numero y sus municipios mas altos.
   - Abajo, para el analista: subir a mano lo que no llega solo (el
     archivo del Secretariado si la descarga fallo, y las encuestas del
     INEGI).

   El numero lo hace Connect; la Central lo revisa, lo ajusta con motivo
   escrito y lo publica. Nada cambia para el cliente hasta publicarlo. */
import { api } from "./api.js";
import { aviso, campo, entrada, fecha, h, hora, lista, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { capaGoogle, chip, colorDe, contornos, dibujo, leyenda, nombreRango }
  from "./mapa_fondo.js";

const COMPONENTES = ["violencia_letal", "delitos_violencia", "delincuencia_organizada",
                     "miedo", "no_denuncia", "cifra_negra"];
const COLOR_EVENTO = { 1: "#5f7187", 2: "#c99a06", 3: "#e07000", 4: "#c62828" };
const FLECHA = { 1: ["fondo-flecha fondo-sube", "▲"], "-1": ["fondo-flecha fondo-baja", "▼"],
                 0: ["fondo-flecha fondo-igual", "="] };
const EN_LA_LISTA = 9;
const PARA_REVISAR_VISIBLES = 15;

/* ---------------------------------------------------------- utilidades */

function mesLargo(iso) {
  const [a, m] = iso.split("-").map(Number);
  return `${t("rsg_f_meses").split(",")[m - 1]} ${a}`;
}
function mesSolo(iso) {
  return t("rsg_f_meses").split(",")[Number(iso.split("-")[1]) - 1];
}
/* El mes de `iso` menos `n` meses, tambien como 2026-08-01. */
function mesAntes(iso, n) {
  const [a, m] = iso.split("-").map(Number);
  const total = a * 12 + (m - 1) - n;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}-01`;
}
function mesCorto(iso, menos = 0) {
  const [a, m] = mesAntes(iso, menos).split("-").map(Number);
  return `${t("f_meses").split(",")[m - 1]} ${a}`;
}
function mayuscula(texto) {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/* ▲ 6 vs sep 2025: rojo si sube, verde si baja. */
function flecha(diferencia, contra) {
  if (diferencia === null || diferencia === undefined) return null;
  const lado = Math.sign(diferencia);
  return h("span", { clase: FLECHA[lado][0] },
    `${FLECHA[lado][1]} ${Math.abs(diferencia)} `, t("rsg_f_vs").replace("{cuando}", contra));
}

function nombreLugar(l) {
  return l.municipio
    ? t("rsg_f_lugar_mun").replace("{mun}", l.municipio).replace("{edo}", l.region)
    : t("rsg_f_lugar_edo").replace("{edo}", l.region);
}

/* ------------------------------------------------------------ la mesa */

export async function mesaDeFondo(cuerpo, ctx) {
  if (ctx.pais.codigo !== "MX") {
    cuerpo.replaceChildren(aviso(t("rsg_f_solo_mx"), "alerta"));
    return;
  }
  const estado = { mesId: null, vista: "estados", regionId: null, municipioClave: null,
                   datos: null, eventos: [], quitarCapa: null, mapa: null };
  const pintar = async () => {
    let datos;
    try {
      const extra = estado.mesId ? `&mes_id=${estado.mesId}` : "";
      datos = await api.get(`/riesgo/nivel?pais_id=${ctx.pais.id}${extra}`);
      estado.eventos = (await api.get(`/riesgo/mapa?pais_id=${ctx.pais.id}`)).publicados || [];
    } catch (e) {
      cuerpo.replaceChildren(aviso(e.message, "grave"));
      return;
    }
    estado.datos = datos;
    const partes = [];
    if (datos.borrador_id && (datos.puede.analista || datos.puede.publicar)) {
      partes.push(await tarjetaBorrador(datos, ctx, pintar));
    }
    partes.push(datos.mes ? mesPublicado(datos, estado, ctx, pintar)
                          : aviso(t("rsg_f_sin_meses"), "alerta"));
    if (datos.puede.analista) partes.push(tarjetaFuentes(datos, pintar));
    cuerpo.replaceChildren(...partes);
  };
  await pintar();
}

/* ------------------------------------------------------- el borrador */

function filaFuente(nombre, ultimo, como, tono, estadoTexto) {
  return h("tr", {},
    h("td", {}, nombre), h("td", {}, ultimo), h("td", {}, como),
    h("td", {}, h("span", { clase: `etiqueta ${tono}` }, estadoTexto)));
}

function comoLlego(carga) {
  if (!carga) return "—";
  if (carga.origen === "automatica") return t("rsg_f_bajo_solo").replace("{fecha}", fecha(carga.en));
  if (!carga.quien) return t("rsg_f_subida").replace("{fecha}", fecha(carga.en));
  return t("rsg_f_subio").replace("{quien}", carga.quien).replace("{fecha}", fecha(carga.en));
}

/* Al dia si el dato es de hace menos de `meses` meses contra el mes que
   se calcula. */
function alDia(periodoDato, periodoMes, meses) {
  if (!periodoDato) return false;
  const [a1, m1] = periodoDato.split("-").map(Number);
  const [a2, m2] = periodoMes.split("-").map(Number);
  return (a2 * 12 + m2) - (a1 * 12 + m1) <= meses;
}

function tablaFuentes(mes, cargas) {
  const f = mes.fuentes || {};
  const sesnsp = (f.sesnsp && f.sesnsp.meses) || [];
  const ultimo = sesnsp.length ? sesnsp[sesnsp.length - 1] : null;
  const filas = [];
  const estadoDe = (dato, limite) => dato
    ? (alDia(dato, mes.periodo, limite) ? ["ok", t("rsg_f_al_dia")] : ["alerta", t("rsg_f_atrasado")])
    : ["grave", t("rsg_f_sin_dato")];
  let [tono, texto] = estadoDe(ultimo, 0);
  filas.push(filaFuente(t("rsg_f_fuente_sesnsp"), ultimo ? mayuscula(mesLargo(ultimo)) : "—",
                        comoLlego(cargas.sesnsp), tono, texto));
  for (const [clave, limite] of [["ensu", 4], ["envipe_percepcion", 14], ["envipe_prevalencia", 14]]) {
    [tono, texto] = estadoDe(f[clave], limite);
    filas.push(filaFuente(t(`rsg_f_fuente_${clave}`), f[clave] ? mayuscula(mesLargo(f[clave])) : "—",
                          comoLlego(cargas[clave]), tono, texto));
  }
  filas.push(filaFuente(t("rsg_f_fuente_conapo"), mes.periodo.slice(0, 4),
                        t("rsg_f_conapo_como"), "ok", t("rsg_f_al_dia")));
  const cn = f.cifra_negra || { hechos: 0, dias: 90 };
  filas.push(filaFuente(t("rsg_f_fuente_cifra_negra"),
                        t("rsg_f_cn_ultimo").replace("{dias}", cn.dias),
                        t("rsg_f_cn_como").replace("{n}", cn.hechos),
                        cn.hechos ? "ok" : "alerta",
                        cn.hechos ? t("rsg_f_al_dia") : t("rsg_f_sin_hechos")));
  return h("table", { clase: "fondo-tabla" },
    h("thead", {}, h("tr", {}, h("th", {}, t("rsg_f_col_fuente")), h("th", {}, t("rsg_f_col_ultimo")),
                       h("th", {}, t("rsg_f_col_como")), h("th", {}))),
    h("tbody", {}, filas));
}

function porQue(motivos) {
  return motivos.map((x) => {
    if (x.tipo === "sin_reporte") return t("rsg_f_mot_sin_reporte");
    if (x.tipo === "cambio") {
      return (x.puntos > 0 ? t("rsg_f_mot_subio") : t("rsg_f_mot_bajo"))
        .replace("{n}", Math.abs(x.puntos));
    }
    return t("rsg_f_mot_rango").replace("{de}", nombreRango(x.de)).replace("{a}", nombreRango(x.a));
  }).join(" · ");
}

function filaRevisar(l, cortes, recargar, editable) {
  const ajustar = editable
    ? h("button", { type: "button", clase: "claro chico" }, t("rsg_f_ajustar")) : null;
  const fila = h("tr", {},
    h("td", {}, h("strong", {}, nombreLugar(l))),
    h("td", {}, l.antes === null || l.antes === undefined ? "—" : String(Math.round(l.antes))),
    h("td", {}, h("strong", {}, String(l.valor)), " ", chip(l.valor, cortes)),
    h("td", { clase: "chico" }, porQue(l.motivos),
      l.ajuste_motivo ? h("div", { clase: "gris" },
        t("rsg_f_ajustado").replace("{n}", l.calculado).replace("{motivo}", l.ajuste_motivo)) : null),
    h("td", {}, ajustar));
  const valor = entrada("valor", { type: "number", min: "0", max: "100", step: "1",
                                   value: String(l.valor), clase: "fondo-valor" });
  const motivo = entrada("motivo", { maxlength: "400", "data-crudo": "", placeholder: t("rsg_f_ph_motivo") });
  const guardar = h("button", { type: "button" }, t("rsg_f_guardar_ajuste"));
  const cancelar = h("button", { type: "button", clase: "claro" }, t("rsg_f_cancelar"));
  const salida = h("div");
  const editor = h("tr", { hidden: "hidden" },
    h("td", { colspan: "5" },
      h("div", { clase: "rsg-linea", "data-editando": "1" },
        campo(t("rsg_f_nivel_nuevo"), valor), campo(t("rsg_f_motivo"), motivo), guardar, cancelar),
      salida));
  if (!editable) return [fila];
  ajustar.onclick = () => { editor.hidden = !editor.hidden; if (!editor.hidden) motivo.focus(); };
  cancelar.onclick = () => { editor.hidden = true; };
  guardar.onclick = async () => {
    guardar.disabled = true;
    try {
      await api.post(`/riesgo/nivel/lugares/${l.id}/ajuste`,
                     { valor: Number(valor.value), motivo: motivo.value });
      await recargar();
    } catch (e) {
      salida.replaceChildren(aviso(e.message, "grave"));
      guardar.disabled = false;
    }
  };
  return [fila, editor];
}

async function tarjetaBorrador(datos, ctx, recargar) {
  let mes, revisar;
  try {
    mes = datos.mes && datos.mes.id === datos.borrador_id
      ? datos.mes : await api.get(`/riesgo/nivel?pais_id=${ctx.pais.id}&mes_id=${datos.borrador_id}`)
        .then((x) => x.mes);
    revisar = await api.get(`/riesgo/nivel/${datos.borrador_id}/revisar`);
  } catch (e) {
    return aviso(e.message, "grave");
  }
  const nombreMes = mesSolo(mes.periodo);
  const cabeza = h("div", { clase: "rsg-cabeza" },
    h("strong", { clase: "fondo-mes" }, mayuscula(mesLargo(mes.periodo))),
    h("span", { clase: "etiqueta alerta" }, t("rsg_f_borrador")),
    h("span", { clase: "chico gris" },
      t("rsg_f_calculado").replace("{fecha}", fecha(mes.calculado_en)).replace("{hora}", hora(mes.calculado_en))));

  const faltan = mes.faltan.length
    ? aviso(t("rsg_f_faltan").replace("{lista}",
        mes.faltan.map((c) => t(`rsg_f_comp_${c}`)).join(", ")), "alerta")
    : null;

  const anterior = mayuscula(mesSolo(mesAntes(mes.periodo, 1)));
  const cuerpoTabla = h("tbody");
  const pintarFilas = (cuantos) => {
    cuerpoTabla.replaceChildren(...revisar.slice(0, cuantos)
      .flatMap((l) => filaRevisar(l, mes.cortes, recargar, datos.puede.analista)));
  };
  pintarFilas(PARA_REVISAR_VISIBLES);
  const verTodos = revisar.length > PARA_REVISAR_VISIBLES
    ? h("button", { type: "button", clase: "claro chico",
                    onclick: (ev) => { pintarFilas(revisar.length); ev.target.remove(); } },
        t("rsg_f_ver_todos").replace("{n}", revisar.length))
    : null;
  const tablaRevisar = revisar.length
    ? h("table", { clase: "fondo-tabla" },
        h("thead", {}, h("tr", {}, h("th", {}, t("rsg_f_col_lugar")), h("th", {}, anterior),
                           h("th", {}, mayuscula(nombreMes)), h("th", {}, t("rsg_f_col_porque")),
                           h("th", {}))),
        cuerpoTabla)
    : h("p", { clase: "chico gris" }, t("rsg_f_nada_que_revisar"));

  const salida = h("div");
  const acciones = h("div", { clase: "acciones fondo-acciones" });
  const recalcular = h("button", { type: "button", clase: "claro" }, t("rsg_f_recalcular"));
  recalcular.onclick = async () => {
    recalcular.disabled = true;
    try {
      await api.post("/riesgo/nivel/calcular", { pais_id: ctx.pais.id, periodo: mes.periodo });
      await recargar();
    } catch (e) {
      salida.replaceChildren(aviso(e.message, "grave"));
      recalcular.disabled = false;
    }
  };
  if (datos.puede.publicar) {
    const publicar = h("button", { type: "button" },
      t("rsg_f_publicar").replace("{mes}", nombreMes));
    publicar.onclick = async () => {
      if (!confirm(t("rsg_f_publicar_seguro").replace("{mes}", nombreMes))) return;
      publicar.disabled = true;
      try {
        await api.post(`/riesgo/nivel/${mes.id}/publicar`, {});
        mensaje(t("rsg_f_publicado_ok").replace("{mes}", nombreMes));
        await recargar();
      } catch (e) {
        salida.replaceChildren(aviso(e.message, "grave"));
        publicar.disabled = false;
      }
    };
    acciones.append(...[publicar, datos.puede.analista && recalcular,
                        h("span", { clase: "chico gris" }, t("rsg_f_publicar_pie"))].filter(Boolean));
  } else {
    acciones.append(recalcular, h("span", { clase: "chico gris" }, t("rsg_f_solo_jefe")));
  }

  return h("div", { clase: "tarjeta fondo-borrador" }, cabeza,
    h("h3", {}, t("rsg_f_de_donde")), tablaFuentes(mes, datos.cargas), faltan,
    h("h3", {}, t("rsg_f_para_revisar").replace("{n}", revisar.length)),
    h("p", { clase: "chico gris" }, t("rsg_f_para_revisar_sub")),
    tablaRevisar, verTodos,
    aviso(t("rsg_f_ajustar_nota")), acciones, salida);
}

/* ------------------------------------------------- el mes que se ve */

function avisoDelMes(mes) {
  if (mes.estado === "publicado") {
    return aviso(t("rsg_f_publicado")
      .replace("{mes}", mesLargo(mes.periodo)).replace("{fecha}", fecha(mes.publicado_en))
      .replace("{quien}", mes.publicado_por || "—"), "ok");
  }
  return aviso(t("rsg_f_viendo_borrador").replace("{mes}", mesLargo(mes.periodo)), "alerta");
}

function renglon(l, cortes, elegido, contra, alPicar) {
  return h("button", { type: "button", clase: elegido ? "rsg-renglon fondo-renglon fondo-elegido" : "rsg-renglon fondo-renglon",
                       onclick: alPicar },
    h("b", { clase: "fondo-num" }, String(l.valor)),
    h("span", { clase: "fondo-nombre" }, h("b", {}, l.municipio || l.region),
      l.vs_ano === null || l.vs_ano === undefined ? null : h("br"), flecha(l.vs_ano, contra)),
    chip(l.valor, cortes));
}

function mesPublicado(datos, estado, ctx, recargar) {
  const mes = datos.mes;
  const pEstados = h("button", { type: "button", clase: "pestana" }, t("rsg_f_estados"));
  const pMunicipios = h("button", { type: "button", clase: "pestana" }, t("rsg_f_municipios"));
  const selMes = lista("mes", datos.meses.map((x) => ({
    valor: x.id, texto: mayuscula(mesLargo(x.periodo))
      + (x.estado === "borrador" ? ` · ${t("rsg_f_borrador_min")}` : "") })));
  selMes.value = mes.id;
  selMes.onchange = () => { estado.mesId = Number(selMes.value); recargar(); };

  const izquierda = h("div", { clase: "rsg-cola fondo-cola" });
  const lienzo = h("div", { clase: "fondo-lienzo" });
  const caja = h("div", { clase: "rsg-mapa fondo-mapa" }, lienzo, leyenda(mes.cortes),
    h("div", { clase: "chico gris fondo-nota" }, t("rsg_f_nota_mapa")));
  const ficha = h("div", { clase: "fondo-ficha" });
  const contraAno = mesCorto(mes.periodo, 12);
  const contraMes = mesSolo(mesAntes(mes.periodo, 1));

  const estados = mes.lugares;
  if (!estado.regionId || !estados.some((l) => l.region_id === estado.regionId)) {
    estado.regionId = estados.length ? estados[0].region_id : null;
    estado.municipioClave = null;
  }
  let municipios = [];

  const elegirEstado = async (regionId) => {
    estado.regionId = regionId;
    estado.municipioClave = null;
    await dibujar();
  };

  const dibujarLista = () => {
    const enMunicipios = estado.vista === "municipios";
    const filas = enMunicipios ? municipios : estados;
    const elegido = enMunicipios ? estado.municipioClave : estado.regionId;
    const titulo = enMunicipios
      ? t("rsg_f_municipios_de").replace("{edo}", (estados.find((l) => l.region_id === estado.regionId) || {}).region || "")
        .replace("{n}", filas.length)
      : t("rsg_f_los_estados").replace("{n}", filas.length);
    const mostrar = (cuantos) => {
      const botones = filas.slice(0, cuantos).map((l) => renglon(l, mes.cortes,
        enMunicipios ? l.clave_municipio === elegido : l.region_id === elegido, contraAno,
        () => (enMunicipios ? elegirMunicipio(l.clave_municipio) : elegirEstado(l.region_id))));
      const mas = filas.length > cuantos
        ? h("button", { type: "button", clase: "claro chico",
                        onclick: () => mostrar(filas.length) },
            t("rsg_f_ver_los").replace("{n}", filas.length))
        : null;
      izquierda.replaceChildren(...[h("h3", {}, titulo), ...botones, mas].filter(Boolean));
    };
    mostrar(EN_LA_LISTA);
  };

  const elegirMunicipio = async (clave) => {
    estado.municipioClave = clave;
    await dibujar();
  };

  const eventosDelMapa = () => estado.eventos.map((e) => ({
    lat: e.lat, lon: e.lon, color: COLOR_EVENTO[e.nivel] || COLOR_EVENTO[1] }));

  const dibujar = async () => {
    const enMunicipios = estado.vista === "municipios";
    pEstados.classList.toggle("activa", !enMunicipios);
    pMunicipios.classList.toggle("activa", enMunicipios);
    selEstado.hidden = !enMunicipios;
    if (estado.regionId) selEstado.value = estado.regionId;
    let detalle = null;
    if (estado.regionId) {
      try {
        detalle = await api.get(`/riesgo/nivel/${mes.id}/estados/${estado.regionId}`);
        municipios = detalle.municipios;
      } catch (e) {
        ficha.replaceChildren(aviso(e.message, "grave"));
      }
    }
    if (enMunicipios && !estado.municipioClave && municipios.length) {
      estado.municipioClave = municipios[0].clave_municipio;
    }
    dibujarLista();

    let geo;
    const elEstado = estados.find((l) => l.region_id === estado.regionId);
    try {
      geo = enMunicipios && elEstado
        ? await contornos(`mun_${elEstado.clave_region}`)
        : await contornos("estados");
    } catch (e) {
      lienzo.replaceChildren(aviso(t("rsg_f_sin_contornos"), "alerta"));
      geo = null;
    }
    if (geo) {
      const porClave = new Map(enMunicipios
        ? municipios.map((l) => [String(l.clave_municipio), { valor: l.valor, nombre: l.municipio }])
        : estados.map((l) => [String(l.clave_region), { valor: l.valor, nombre: l.region }]));
      const valorDe = (f) => porClave.get(String(f.properties.c)) || null;
      const marcado = enMunicipios ? estado.municipioClave : (elEstado ? elEstado.clave_region : null);
      const alElegir = (clave) => {
        if (enMunicipios) return elegirMunicipio(Number(clave));
        const l = estados.find((x) => String(x.clave_region) === String(clave));
        if (l) elegirEstado(l.region_id);
      };
      await pintarMapa(lienzo, estado, ctx, geo.features, valorDe, { marcado, alElegir,
        eventos: eventosDelMapa() });
    }
    if (detalle) {
      ficha.replaceChildren(enMunicipios
        ? fichaMunicipio(municipios.find((l) => l.clave_municipio === estado.municipioClave), mes, contraAno, contraMes)
        : fichaEstado(detalle, mes, contraAno, contraMes, (clave) => {
          estado.vista = "municipios";
          elegirMunicipio(clave);
        }));
    }
  };

  const selEstado = lista("estado", [...estados]
    .sort((a, b) => a.region.localeCompare(b.region))
    .map((l) => ({ valor: l.region_id, texto: l.region })));
  selEstado.onchange = () => elegirEstado(Number(selEstado.value));

  pEstados.onclick = () => { estado.vista = "estados"; estado.municipioClave = null; dibujar(); };
  pMunicipios.onclick = () => { estado.vista = "municipios"; dibujar(); };

  const vista = h("div", {},
    avisoDelMes(mes),
    h("div", { clase: "fondo-barra" }, h("div", { clase: "pestanas" }, pEstados, pMunicipios), selEstado, selMes),
    h("div", { clase: "rsg-mesa" }, izquierda, h("div", {}, caja, ficha)));
  dibujar();
  return vista;
}

/* Con llave de Google, la capa encima del mapa de verdad; sin llave, el
   dibujo. Un mapa por pantalla: se reusa al cambiar de estado. */
async function pintarMapa(lienzo, estado, ctx, features, valorDe, opciones) {
  if (estado.quitarCapa) { estado.quitarCapa(); estado.quitarCapa = null; }
  let conGoogle = false;
  if (ctx.llaveGoogle === undefined) {
    try {
      ctx.llaveGoogle = (await api.get("/riesgo/mapa-llave")).llave || null;
    } catch (e) { ctx.llaveGoogle = null; }
  }
  if (ctx.llaveGoogle) {
    try {
      await ctx.cargarGoogle(ctx.llaveGoogle);
      conGoogle = true;
    } catch (e) { conGoogle = false; }
  }
  if (!conGoogle) {
    lienzo.classList.remove("fondo-con-google");
    lienzo.replaceChildren(dibujo(features, valorDe, opciones));
    return;
  }
  if (!estado.mapa || !lienzo.contains(estado.mapa.getDiv())) {
    const div = h("div", { clase: "fondo-google" });
    lienzo.classList.add("fondo-con-google");
    lienzo.replaceChildren(div);
    estado.mapa = new google.maps.Map(div, {
      center: { lat: 23.6, lng: -102.5 }, zoom: 5, mapTypeControl: false,
      streetViewControl: false, fullscreenControl: true, clickableIcons: false });
    estado.marcas = [];
  }
  for (const marca of estado.marcas) marca.setMap(null);
  estado.marcas = opciones.eventos.filter((e) => e.lat !== null && e.lat !== undefined)
    .map((e) => new google.maps.Marker({
      map: estado.mapa, position: { lat: e.lat, lng: e.lon }, clickable: false,
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: 6, fillColor: e.color, fillOpacity: 1,
              strokeColor: "#ffffff", strokeWeight: 2 } }));
  estado.quitarCapa = capaGoogle(estado.mapa, features, valorDe, opciones);
}

function barras(lugar, mes) {
  const faltan = new Set(mes.faltan);
  return h("table", { clase: "fondo-tabla fondo-compone" }, h("tbody", {},
    COMPONENTES.map((c) => {
      const p = lugar.componentes[c] ? lugar.componentes[c].p : null;
      const sinDato = p === null || p === undefined || faltan.has(c);
      const barra = h("div", { clase: "fondo-barra-fondo" });
      if (!sinDato) {
        const lleno = h("div", { clase: "fondo-barra-llena" });
        lleno.style.width = `${Math.max(1, Math.round(p))}%`;
        barra.append(lleno);
      }
      return h("tr", {},
        h("td", {}, t(`rsg_f_comp_${c}`)),
        h("td", { clase: "chico gris" }, `${mes.pesos[c]}%`),
        h("td", { clase: "fondo-celda-barra" }, barra),
        h("td", {}, sinDato ? h("span", { clase: "chico gris" }, t("rsg_f_sin_dato_min"))
                            : h("b", {}, String(Math.round(p)))));
    })));
}

function cabezaFicha(lugar, mes, contraAno, contraMes, nombre) {
  return h("div", { clase: "rsg-cabeza" },
    h("strong", { clase: "fondo-mes" }, nombre),
    h("span", { clase: "fondo-grande" }, String(lugar.valor)), chip(lugar.valor, mes.cortes),
    flecha(lugar.vs_ano, contraAno), flecha(lugar.vs_mes, contraMes),
    lugar.ajuste_motivo ? h("span", { clase: "etiqueta info" }, t("rsg_f_ajustado_corto")) : null);
}

function piesDeFuentes(mes) {
  const f = mes.fuentes || {};
  const partes = [];
  const sesnsp = (f.sesnsp && f.sesnsp.meses) || [];
  if (sesnsp.length) partes.push(t("rsg_f_pie_sesnsp").replace("{mes}", mesCorto(sesnsp[sesnsp.length - 1])));
  if (f.ensu) partes.push(t("rsg_f_pie_ensu").replace("{mes}", mesCorto(f.ensu)));
  if (f.envipe_percepcion || f.envipe_prevalencia) {
    partes.push(t("rsg_f_pie_envipe").replace("{anio}", (f.envipe_percepcion || f.envipe_prevalencia).slice(0, 4)));
  }
  partes.push(t("rsg_f_pie_conapo").replace("{anio}", mes.periodo.slice(0, 4)));
  if (f.cifra_negra) {
    partes.push(t("rsg_f_pie_cn").replace("{n}", f.cifra_negra.hechos).replace("{dias}", f.cifra_negra.dias));
  }
  return h("p", { clase: "chico gris" }, t("rsg_f_pie_fuentes").replace("{lista}", partes.join(" · ")));
}

function fichaEstado(detalle, mes, contraAno, contraMes, abrirMunicipio) {
  const e = detalle.estado;
  const altos = detalle.municipios.slice(0, 5);
  return h("div", { clase: "tarjeta fondo-tarjeta" },
    cabezaFicha(e, mes, contraAno, contraMes, e.region),
    e.ajuste_motivo ? aviso(t("rsg_f_ajuste_dice").replace("{motivo}", e.ajuste_motivo).replace("{n}", e.calculado)) : null,
    h("h3", {}, t("rsg_f_compone")), barras(e, mes),
    h("div", { clase: "fondo-dos" },
      h("div", {}, h("h3", {}, t("rsg_f_mas_altos")),
        altos.length
          ? h("table", { clase: "fondo-tabla" }, h("tbody", {}, altos.map((l) => h("tr", {},
              h("td", {}, h("button", { type: "button", clase: "enlace",
                                       onclick: () => abrirMunicipio(l.clave_municipio) }, l.municipio)),
              h("td", {}, h("b", {}, String(l.valor))), h("td", {}, chip(l.valor, mes.cortes))))))
          : h("p", { clase: "chico gris" }, t("rsg_f_sin_municipios"))),
      h("div", {}, h("h3", {}, t("rsg_f_de_donde_mes")), piesDeFuentes(mes))));
}

function fichaMunicipio(l, mes, contraAno, contraMes) {
  if (!l) return h("div");
  return h("div", { clase: "tarjeta fondo-tarjeta" },
    cabezaFicha(l, mes, contraAno, contraMes, nombreLugar(l)),
    l.sin_reporte ? aviso(t("rsg_f_sin_reporte_aviso"), "alerta") : null,
    l.ajuste_motivo ? aviso(t("rsg_f_ajuste_dice").replace("{motivo}", l.ajuste_motivo).replace("{n}", l.calculado)) : null,
    h("h3", {}, t("rsg_f_compone")), barras(l, mes),
    h("p", { clase: "chico gris" }, t("rsg_f_municipio_pie")),
    piesDeFuentes(mes));
}

/* ------------------------------------------------ subir lo que falta */

function tarjetaFuentes(datos, recargar) {
  const salida = h("div");
  const decir = (nodo) => salida.replaceChildren(nodo);

  const archivoSesnsp = entrada("archivo", { type: "file", accept: ".zip,.csv" });
  const subirSesnsp = h("button", { type: "button" }, t("rsg_f_subir"));
  subirSesnsp.onclick = async () => {
    if (!archivoSesnsp.files.length) { decir(aviso(t("rsg_f_elige_archivo"), "alerta")); return; }
    subirSesnsp.disabled = true;
    decir(aviso(t("rsg_f_leyendo")));
    try {
      const r = await api.subir("/riesgo/nivel/fuentes/sesnsp", archivoSesnsp.files[0]);
      mensaje(t("rsg_f_sesnsp_ok").replace("{mes}", mesLargo(r.periodo)).replace("{filas}", r.filas));
      await recargar();
    } catch (e) {
      decir(aviso(e.message, "grave"));
      subirSesnsp.disabled = false;
    }
  };

  const buscar = h("button", { type: "button", clase: "claro" }, t("rsg_f_buscar_ahora"));
  buscar.onclick = async () => {
    buscar.disabled = true;
    decir(aviso(t("rsg_f_buscando")));
    try {
      const r = await api.post("/riesgo/nivel/fuentes/sesnsp/bajar", {});
      const texto = t(`rsg_f_bajar_${r.resultado}`).replace("{mes}", r.periodo ? mesLargo(r.periodo) : "");
      if (r.resultado === "nuevo") { mensaje(texto); await recargar(); return; }
      decir(aviso(texto + (r.detalle ? ` (${r.detalle})` : ""),
                  r.resultado === "sin_cambios" ? "ok" : "alerta"));
    } catch (e) {
      decir(aviso(e.message, "grave"));
    }
    buscar.disabled = false;
  };

  const fuente = lista("fuente", ["ensu", "envipe_percepcion", "envipe_prevalencia"]
    .map((c) => ({ valor: c, texto: t(`rsg_f_fuente_${c}`) })));
  const periodo = entrada("periodo", { type: "month" });
  const archivoEncuesta = entrada("archivo", { type: "file", accept: ".csv,.txt" });
  const subirEncuesta = h("button", { type: "button" }, t("rsg_f_subir"));
  subirEncuesta.onclick = async () => {
    if (!periodo.value || !archivoEncuesta.files.length) {
      decir(aviso(t("rsg_f_falta_encuesta"), "alerta"));
      return;
    }
    subirEncuesta.disabled = true;
    try {
      const r = await api.formulario("/riesgo/nivel/fuentes/encuesta", {
        fuente: fuente.value, periodo: `${periodo.value}-01`, archivo: archivoEncuesta.files[0] });
      const faltaron = r.no_reconocidos.length
        ? t("rsg_f_no_reconocidos").replace("{lista}", r.no_reconocidos.slice(0, 12).join(", "))
        : "";
      mensaje(t("rsg_f_encuesta_ok").replace("{n}", r.guardados));
      await recargar();
      if (faltaron) mensaje(faltaron, "alerta");
    } catch (e) {
      decir(aviso(e.message, "grave"));
      subirEncuesta.disabled = false;
    }
  };

  return h("div", { clase: "tarjeta fondo-tarjeta" },
    h("h3", {}, t("rsg_f_subir_titulo")),
    h("p", { clase: "chico gris" }, t("rsg_f_subir_sub")),
    h("h4", {}, t("rsg_f_fuente_sesnsp")),
    h("p", { clase: "chico gris" }, t("rsg_f_sesnsp_ayuda")),
    h("div", { clase: "rsg-linea" }, archivoSesnsp, subirSesnsp, buscar),
    h("h4", {}, t("rsg_f_encuestas")),
    h("p", { clase: "chico gris" }, t("rsg_f_encuestas_ayuda")),
    h("div", { clase: "rsg-linea" }, campo(t("rsg_f_cual"), fuente), campo(t("rsg_f_periodo"), periodo),
      archivoEncuesta, subirEncuesta),
    salida);
}

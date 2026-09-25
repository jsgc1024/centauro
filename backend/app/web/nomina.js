/* Nominas (seccion 66).

   Dos pagos distintos en la misma pantalla, cada uno en su pestana:

   - El del personal de seguridad, cada lunes. El reloj arma el borrador
     a las 7:00 y a las 11:00 lo deja listo para pagar; finanzas lo paga
     a mediodia. Lo que llega despues de las 11:00 entra al lunes
     siguiente. El implantado se paga cada semana por los dias
     trabajados, y con el visto bueno del mes su diferencia se paga o se
     descuenta el lunes siguiente.
   - La comision de los consultores, cada mes. Direccion de operaciones
     le da el visto bueno cuando el mes termina y finanzas registra cada
     transferencia con su referencia. El consultor ve la suya.

   Y una regla para los dos: nadie cobra en negativo. Quien queda
   debajo de cero cobra cero y lo que falta pasa a su siguiente corte.

   Ya pagado no se toca: el dinero ya salio. Lo que cambie despues viaja
   hacia adelante como diferencia, con su motivo escrito. */
import { api, sesion } from "./api.js";
import { aviso, campo, conAyuda, dinero, entrada, etiqueta, fecha, h, hora,
         lista, mensaje } from "./util.js";
import { catalogos } from "./catalogos.js";
import { t } from "./idioma.js";

let paisActual = null;
let pestanaActual = null;
let periodoActual = null;
let monedaActual = "MXN";
// Lo que alguien dejo abierto: al repintar no se le cierra.
const abiertas = new Set();

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (x, [k, v]) => x.replaceAll(`{${k}}`, v ?? ""), texto);
}

function diaMes(iso) {
  if (!iso) return "—";
  const f = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return `${String(f.getDate()).padStart(2, "0")}/${String(f.getMonth() + 1).padStart(2, "0")}`;
}

function diaHora(iso) {
  return iso ? `${diaMes(iso)} ${hora(iso)}` : "—";
}

function nombreMes(anio, mes) {
  return `${t(`bon_mes_${mes}`)} ${anio}`;
}

/* Quien puede que. El servidor lo decide de verdad --esto solo evita
   pintar un boton que va a contestar 403--. Direccion general y
   administracion pueden todo, como en el resto de la consola. */
function puede(que) {
  const rol = sesion.usuario && sesion.usuario.rol;
  const TODO = ["director_general", "admin"];
  const QUIENES = {
    personal: ["finanzas", "director_operaciones"],
    calcular: ["finanzas", "director_operaciones"],
    pagar: ["finanzas", "director_operaciones"],
    visto_bueno: ["director_operaciones"],
    pagar_comision: ["finanzas"],
    diferencia: ["finanzas"],
    decidir: [],
  };
  return TODO.includes(rol) || (QUIENES[que] || []).includes(rol);
}

export async function pantallaNomina(main) {
  const cat = await catalogos();
  const hoy = new Date();
  if (!periodoActual) {
    periodoActual = { anio: hoy.getFullYear(), mes: hoy.getMonth() + 1 };
  }
  /* El pais de quien mira. Abria en el primero del catalogo, que sale
     por nombre: al de Mexico le abria Brasil. */
  paisActual = paisActual || (sesion.usuario && sesion.usuario.pais_id)
    || (cat.paises[0] && cat.paises[0].id);
  const pais = cat.paises.find(p => p.id === paisActual);
  monedaActual = (pais && pais.moneda_local) || "MXN";

  const DISPONIBLES = [
    ["personal", "nom_tab_personal", puede("personal")],
    ["comisiones", "nom_tab_comisiones", true],
    ["tabulador", "nom_tab_tabulador", puede("personal")],
  ].filter(x => x[2]);
  if (!pestanaActual || !DISPONIBLES.some(x => x[0] === pestanaActual)) {
    pestanaActual = DISPONIBLES[0][0];
  }

  main.append(
    h("h1", {}, t("nom_titulo")),
    h("p", { clase: "sub" }, t("nom_sub")));

  const paises = lista("pais", cat.paises.map(
    p => ({ valor: p.id, texto: p.nombre })));
  paises.value = paisActual;
  const meses = lista("mes", Array.from({ length: 12 }, (_, i) => (
    { valor: i + 1, texto: t(`bon_mes_${i + 1}`) })));
  meses.value = periodoActual.mes;
  const anios = lista("anio", [hoy.getFullYear(), hoy.getFullYear() - 1]
    .map(a => ({ valor: a, texto: String(a) })));
  anios.value = periodoActual.anio;
  const campoMes = campo(t("nom_mes"), meses);
  const campoAnio = campo(t("nom_anio"), anios);

  const zona = h("div");

  async function recargar() {
    paisActual = Number(paises.value);
    const elegido = cat.paises.find(p => p.id === paisActual);
    monedaActual = (elegido && elegido.moneda_local) || "MXN";
    periodoActual = { anio: Number(anios.value), mes: Number(meses.value) };
    const conMes = pestanaActual === "comisiones";
    campoMes.hidden = !conMes;
    campoAnio.hidden = !conMes;
    zona.replaceChildren(h("p", { clase: "gris" }, t("nom_cargando")));
    try {
      if (pestanaActual === "comisiones") await pintarComisiones(zona, recargar);
      else if (pestanaActual === "tabulador") await pintarTabulador(zona);
      else await pintarPersonal(zona, recargar);
    } catch (err) {
      zona.replaceChildren(aviso(err.message, "grave"));
    }
  }
  for (const control of [paises, meses, anios]) {
    control.addEventListener("change", recargar);
  }

  const pestanas = h("div", { clase: "pestanas" });
  for (const [clave, texto] of DISPONIBLES) {
    const boton = h("button", {
      clase: `pestana${pestanaActual === clave ? " activa" : ""}`,
      type: "button",
      onclick: () => {
        pestanaActual = clave;
        for (const otro of pestanas.children) otro.classList.remove("activa");
        boton.classList.add("activa");
        recargar();
      },
    }, t(texto));
    pestanas.append(boton);
  }

  main.append(
    h("div", { clase: "tarjeta lisa" },
      h("div", { clase: "rejilla tres" }, campo(t("pais"), paises),
        campoMes, campoAnio),
      pestanas),
    zona);
  await recargar();
}

/* ============================================================ personal */

async function pintarPersonal(zona, recargar) {
  const [semana, meses] = await Promise.all([
    api.get(`/nomina/semana?pais_id=${paisActual}`),
    api.get(`/nomina/implantados?pais_id=${paisActual}`),
  ]);
  monedaActual = semana.moneda || monedaActual;
  const historial = h("div");
  const detalle = h("div");
  zona.replaceChildren(
    tarjetaDelLunes(semana, recargar),
    tarjetaMeses(meses.meses),
    historial, detalle, bloqueAjustes());
  await pintarHistorial(historial, detalle);
}

function estadoDelCorte(estado) {
  if (estado === "pagado") return etiqueta(t("nom_e_pagado"), "ok");
  if (estado === "listo") return etiqueta(t("nom_e_listo"), "info");
  return etiqueta(t("nom_e_borrador"), "alerta");
}

/* El corte de este lunes si hay uno por pagar; si no, lo que va
   juntandose para el siguiente. */
function tarjetaDelLunes(semana, recargar) {
  const c = semana.corte;
  const hs = semana.horario;
  const caja = h("div", { clase: "tarjeta" });

  if (c) {
    const pie = c.estado === "listo"
      ? reemplazar(t("nom_listo_pie"), { h: hora(c.lista_en) })
      : reemplazar(t("nom_armado"), {
          q: c.calculada_por || t("nom_el_sistema"), h: hora(c.calculada_en) })
        + " " + reemplazar(t("nom_horario"), { c: hs.cierre, p: hs.pago });
    caja.append(cabeza(reemplazar(t("nom_corte_del"), { f: fecha(c.fecha_corte) }),
                       estadoDelCorte(c.estado), pie));
  } else {
    const p = semana.proximo;
    caja.append(cabeza(reemplazar(t("nom_va_para"), { f: fecha(p.fecha_corte) }),
      etiqueta(reemplazar(t("nom_e_se_arma"), { h: hs.borrador })),
      reemplazar(t("nom_va_pie"), { b: hs.borrador, c: hs.cierre })));
    if (semana.no_salio) {
      caja.append(aviso(t("nom_no_salio"), "grave"));
      if (p.sin_tarifa.length) caja.append(tablaSinTarifa(p.sin_tarifa));
      if (puede("calcular")) {
        caja.append(h("div", { clase: "acciones", style: "margin-top:10px" },
          h("button", { type: "button",
            onclick: (e) => calcular(e, semana.lunes, recargar) },
            t("nom_armar"))));
      }
    }
  }

  const d = c || semana.proximo;
  caja.append(fichas(d), ...detalleDelCorte(d));

  if (c) {
    const acciones = h("div", { clase: "acciones", style: "margin-top:16px" });
    if (c.estado === "borrador" && puede("calcular")) {
      acciones.append(h("button", { clase: "claro", type: "button",
        onclick: (e) => calcular(e, c.fecha_corte, recargar) },
        t("nom_recalcular")));
    }
    if (c.estado !== "pagado" && puede("pagar")) {
      acciones.append(h("button", { type: "button",
        onclick: (e) => pagar(e, c, recargar) },
        reemplazar(t("nom_marcar_pagado"), { m: dinero(c.total, monedaActual) })));
    }
    if (acciones.children.length) caja.append(acciones);
  }
  caja.append(h("p", { clase: "gris chico", style: "margin:8px 0 0" },
    t("nom_nadie_negativo")));

  if (semana.todavia_no.length) caja.append(...todaviaNo(semana.todavia_no));
  return caja;
}

function cabeza(titulo, sello, pie) {
  return h("div", {},
    h("div", { style: "display:flex;justify-content:space-between;align-items:flex-start;gap:12px" },
      h("h2", { style: "margin:0" }, titulo), sello),
    h("p", { clase: "gris chico", style: "margin:4px 0 0" }, pie));
}

/* Las cuatro cifras de arriba. */
function fichas(d) {
  const r = d.resumen;
  const origenes = d.por_origen;
  const eventuales = origenes.filter(g => g.origen === "eventual").length;
  const contratos = origenes.filter(g => g.origen === "implantado").length;
  const pasan = Number(r.pasan);
  const cifra = (valor, texto, tono = "") => h("div", {},
    h("div", { clase: `cifra ${tono}`.trim() }, dinero(valor, monedaActual)),
    h("div", { clase: "gris chico" }, texto));
  return h("div", { clase: "rejilla cuatro", style: "margin:16px 0 4px" },
    cifra(d.total, reemplazar(t(d.estado === "pagado" ? "nom_t_pagado" : "nom_t_a_pagar"),
                              { n: r.personas })),
    cifra(r.eventual, reemplazar(t("nom_t_eventual"), { n: eventuales })),
    cifra(r.implantado, reemplazar(t("nom_t_implantado"), { n: contratos })),
    cifra(Number(r.diferencias) + pasan,
      pasan
        ? reemplazar(t("nom_t_pasan"), { m: dinero(-pasan, monedaActual),
                                         f: diaMes(d.siguiente_lunes) })
        : t("nom_t_diferencias"),
      Number(r.diferencias) + pasan < 0 ? "rojo" : ""));
}

function detalleDelCorte(d) {
  const partes = [];
  partes.push(conAyuda("h4", t("nom_entra"), "ay_nom_entra",
                       { clase: "seccion" }));
  if (!d.por_origen.length && !d.pasan.length) {
    partes.push(h("p", { clase: "gris chico" }, t("nom_nada_aun")));
    return partes;
  }
  partes.push(tablaEntra(d));
  partes.push(h("h4", { clase: "seccion" }, t("nom_por_persona")));
  partes.push(tablaPersonas(d));
  if (d.por_rol.length) {
    partes.push(conAyuda("h4", t("nom_por_rol"), "ay_nom_por_rol",
                         { clase: "seccion" }));
    partes.push(h("div", { clase: "rejilla cuatro" },
      ...d.por_rol.map(r => h("div", {},
        h("div", { clase: "gris chico" }, r.rol_id ? r.rol : t("nom_sin_rol")),
        h("div", { style: "font-size:17px;font-weight:650" },
          dinero(r.monto, monedaActual)),
        h("div", { clase: "gris chico" },
          reemplazar(t("nom_dias_n"), { n: r.dias }))))));
  }
  return partes;
}

const SELLO_ORIGEN = {
  eventual: ["nom_o_eventual", "info"],
  implantado: ["nom_o_implantado", "cafe"],
  mes: ["nom_o_diferencia", "azul"],
  regreso: ["nom_o_diferencia", "azul"],
  viaticos: ["nom_o_viaticos", "alerta"],
  manual: ["nom_o_manual", "negro"],
  saldo: ["nom_o_saldo", "grave"],
};

function porQue(g) {
  const p = g.por_que;
  if (p.clave === "visto_bueno") {
    return reemplazar(t("nom_pq_visto_bueno"), { q: p.consultor || "—",
                                                 f: diaMes(p.fecha) });
  }
  if (p.clave === "dias") {
    return reemplazar(t("nom_pq_dias"), { d: diaMes(p.desde), a: diaMes(p.hasta) });
  }
  if (p.clave === "mes") {
    return reemplazar(t("nom_pq_mes"), { m: nombreMes(p.anio, p.mes),
                                         f: diaMes(p.fecha) });
  }
  if (p.clave === "regreso") {
    return reemplazar(t("nom_pq_regreso"), { f: diaMes(p.fecha) });
  }
  return t(POR_QUE_SIN_DATOS[p.clave] || "nom_pq_manual");
}

const POR_QUE_SIN_DATOS = {
  viaticos: "nom_pq_viaticos",
  manual: "nom_pq_manual",
  saldo: "nom_pq_saldo",
};

function tablaEntra(d) {
  const filas = [];
  for (const g of d.por_origen) {
    const [texto, tono] = SELLO_ORIGEN[g.origen] || ["nom_o_manual", ""];
    const servicio = g.origen === "mes"
      ? `${g.folio} · ${t(`bon_mes_${g.mes}`)}`
      : (g.folio || "—");
    filas.push(h("tr", {},
      h("td", {}, etiqueta(t(texto), tono)),
      h("td", {}, servicio),
      h("td", {}, porQue(g)),
      h("td", { clase: "der" }, g.dias ? String(g.dias) : "—"),
      h("td", { clase: "der" }, String(g.personas)),
      h("td", { clase: "der num" }, dinero(g.monto, monedaActual))));
    if (g.horas_extra) {
      filas.push(h("tr", { clase: "sub" }, h("td", {}),
        h("td", { colspan: "4" },
          reemplazar(t("nom_incluye_extra"), { n: g.horas_extra })),
        h("td", { clase: "der num" }, dinero(g.monto_horas_extra, monedaActual))));
    }
  }
  /* Lo que no alcanzo: sale de este corte y entra al siguiente como
     descuento. Va en su renglon, con su propio sello, para que no se lea
     como un pago de mas. */
  for (const p of d.pasan) {
    filas.push(h("tr", {},
      h("td", { style: "white-space:nowrap" }, etiqueta(t("nom_o_pasa"), "grave")),
      h("td", {}, "—"),
      h("td", {}, reemplazar(t("nom_pasa"), {
        p: p.persona, f: diaMes(d.siguiente_lunes) })),
      h("td", { clase: "der" }, "—"),
      h("td", { clase: "der" }, "1"),
      h("td", { clase: "der num" }, `+${dinero(p.monto, monedaActual)}`)));
  }
  filas.push(h("tr", { clase: "total" },
    h("td", { colspan: "5" }, h("b", {}, t("nom_a_pagar"))),
    h("td", { clase: "der num" }, h("b", {}, dinero(d.total, monedaActual)))));
  return h("table", { clase: "tabla-cierre" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("nom_c_origen")), h("th", {}, t("nom_c_servicio")),
      h("th", {}, t("nom_c_por_que")), h("th", { clase: "der" }, t("nom_c_dias")),
      h("th", { clase: "der" }, t("nom_c_personas")),
      h("th", { clase: "der" }, t("nom_c_monto")))),
    h("tbody", {}, ...filas));
}

/* Cada persona con su recibo: el que va a reclamar si no le cuadra,
   y ahi tiene que decir con que rol se le pago cada dia. */
function tablaPersonas(d) {
  const cuerpo = h("tbody");
  function pintar() {
    const filas = [];
    for (const p of d.por_persona) {
      const clave = `${d.fecha_corte}:${p.persona_id}`;
      const abierta = abiertas.has(clave);
      const debe = Number(p.en_contra);
      filas.push(h("tr", {},
        h("td", {}, h("a", { href: "#", onclick: (e) => {
          e.preventDefault();
          if (abierta) abiertas.delete(clave); else abiertas.add(clave);
          pintar();
        } }, `${abierta ? "▾" : "▸"} `, abierta ? h("b", {}, p.persona) : p.persona)),
        h("td", { clase: "der" }, String(p.dias)),
        h("td", { clase: "der" }, p.horas_extra ? `${p.horas_extra} h` : "—"),
        h("td", { clase: "der num" }, Number(p.diferencias)
          ? dinero(p.diferencias, monedaActual) : "—"),
        h("td", { clase: "der num" },
          abierta ? h("b", {}, dinero(p.total, monedaActual))
                  : dinero(p.total, monedaActual),
          debe ? h("div", {}, etiqueta(reemplazar(t("nom_al_siguiente"), {
            m: dinero(-debe, monedaActual), f: diaMes(d.siguiente_lunes) }),
            "grave")) : null)));
      if (!abierta) continue;
      for (const c of p.conceptos) {
        filas.push(h("tr", { clase: "sub" },
          h("td", {}, c.folio && !c.descripcion.includes(c.folio)
            ? `${c.folio} · ${c.descripcion}` : c.descripcion),
          h("td", {}), h("td", {}), h("td", {}),
          h("td", { clase: "der num" }, c.saldo_en_contra
            ? `+${dinero(c.monto, monedaActual)}` : dinero(c.monto, monedaActual))));
      }
    }
    cuerpo.replaceChildren(...filas);
  }
  pintar();
  return h("table", { clase: "tabla-cierre" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("nom_persona")), h("th", { clase: "der" }, t("nom_c_dias")),
      h("th", { clase: "der" }, t("nom_c_horas_extra")),
      h("th", { clase: "der" }, t("nom_c_diferencias")),
      h("th", { clase: "der" }, t("nom_c_a_pagar")))),
    cuerpo);
}

/* Que le falta a cada uno: con plazo y sin plazo. Escrito entero a
   proposito --una clave armada al vuelo no se puede revisar--. */
const FALTA = {
  comprobacion: ["nom_f_comprobacion", "nom_f_comprobacion_sin"],
  visto_bueno: ["nom_f_visto_bueno", "nom_f_visto_bueno_sin"],
  regresado: ["nom_f_regresado", "nom_f_regresado_sin"],
  en_curso: ["nom_f_en_curso", "nom_f_en_curso"],
  revision: ["nom_f_revision", "nom_f_revision"],
};

function todaviaNo(filas) {
  return [
    conAyuda("h4", t("nom_no_entra"), "ay_nom_no_entra", { clase: "seccion" }),
    h("p", { clase: "gris chico", style: "margin:0 0 6px" }, t("nom_no_entra_pie")),
    h("table", { clase: "tabla-cierre" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("nom_c_servicio")), h("th", {}, t("nom_c_termino")),
        h("th", {}, t("nom_c_consultor")), h("th", {}, t("nom_c_falta")),
        h("th", { clase: "der" }, t("nom_c_estimado")))),
      h("tbody", {}, ...filas.map(f => {
        const falta = f.que_falta;
        const [conPlazo, sinPlazo] = FALTA[falta.clave] || FALTA.revision;
        const texto = falta.hasta
          ? reemplazar(t(conPlazo), { f: diaHora(falta.hasta) })
          : t(sinPlazo);
        const tono = falta.clave === "visto_bueno" || falta.clave === "regresado"
          ? "alerta" : "";
        return h("tr", {},
          h("td", {}, f.folio), h("td", {}, diaHora(f.termino)),
          h("td", {}, f.consultor || "—"),
          h("td", {}, etiqueta(texto, tono)),
          h("td", { clase: "der num" }, f.sin_tarifa
            ? etiqueta(t("nom_sin_tarifa"), "grave")
            : dinero(f.monto, monedaActual)));
      }))),
  ];
}

/* El motor se niega a armar el corte si alguna jornada no tiene tarifa.
   Eso no es un error que esconder: pagar de menos a alguien que trabajo
   es peor que retrasar el corte, asi que la pantalla lo pone completo,
   con nombre y fecha. */
function tablaSinTarifa(filas) {
  return h("table", { clase: "tabla-cierre" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("nom_persona")), h("th", {}, t("nom_dia")),
      h("th", {}, t("nom_modalidad")), h("th", {}, t("nom_rol")))),
    h("tbody", {}, ...filas.map(f => h("tr", {},
      h("td", {}, h("b", {}, f.persona)),
      h("td", {}, fecha(f.fecha)),
      h("td", {}, f.modalidad),
      h("td", {}, f.rol || etiqueta(t("nom_sin_rol"), "grave"))))));
}

async function calcular(e, lunes, recargar) {
  e.target.disabled = true;
  try {
    await api.post("/nomina/calcular", { pais_id: paisActual, fecha_corte: lunes });
    mensaje(t("nom_recalculado"));
    await recargar();
  } catch (err) {
    const filas = (err.detalle && err.detalle.sin_tarifa) || [];
    mensaje(filas.length ? t("nom_no_salio") : err.message, "grave");
    e.target.disabled = false;
  }
}

async function pagar(e, c, recargar) {
  if (!confirm(reemplazar(t("nom_confirmar_pago"), {
    f: fecha(c.fecha_corte), m: dinero(c.total, monedaActual) }))) return;
  e.target.disabled = true;
  try {
    await api.post(`/nomina/${c.nomina_id}/pagar`, {});
    mensaje(reemplazar(t("nom_corte_pagado"), { f: fecha(c.fecha_corte) }));
    await recargar();
  } catch (err) {
    mensaje(err.message, "grave");
    e.target.disabled = false;
  }
}

/* ------------------------------------------ el corte general del mes */

const SELLO_MES = {
  por_cerrar: ["nom_m_por_cerrar", "azul"],
  cerrado: ["nom_m_cerrado", "ok"],
  sin_visto_bueno: ["nom_m_sin_visto_bueno", "alerta"],
  en_curso: ["nom_m_en_curso", ""],
};

function tarjetaMeses(meses) {
  const caja = h("div", { clase: "tarjeta" },
    conAyuda("h2", t("nom_mes_titulo"), "ay_nom_mes", { style: "margin:0" }),
    h("p", { clase: "gris chico", style: "margin:4px 0 12px" }, t("nom_mes_pie")));
  if (!meses.length) {
    caja.append(h("p", { clase: "gris chico" }, t("nom_mes_vacio")));
    return caja;
  }
  const filas = [];
  for (const x of meses) {
    const [claveSello, tono] = SELLO_MES[x.estado] || SELLO_MES.en_curso;
    const sello = reemplazar(t(claveSello), { f: diaMes(x.entra_el) });
    let nota = "";
    if (x.estado === "por_cerrar") {
      nota = reemplazar(t("nom_md_visto_bueno"), { q: x.consultor || "—",
                                                  f: diaMes(x.visto_bueno) });
    } else if (x.estado === "cerrado") {
      nota = reemplazar(t("nom_md_cerrado"), { f: diaMes(x.cerrado_en) });
    } else if (x.estado === "sin_visto_bueno") {
      nota = reemplazar(t("nom_md_vence"), { q: x.consultor || "—",
                                            f: diaHora(x.limite) });
    } else {
      nota = reemplazar(t("nom_md_semanas"), { n: x.semanas_pagadas });
    }
    filas.push(h("tr", {},
      h("td", {}, x.folio),
      h("td", {}, nombreMes(x.anio, x.mes)),
      h("td", {}, etiqueta(sello, tono),
        h("div", { clase: "gris chico" }, nota)),
      h("td", { clase: "der num" }, dinero(x.pagado, monedaActual)),
      h("td", { clase: "der num" }, x.corresponde === null
        ? "—" : dinero(x.corresponde, monedaActual)),
      h("td", { clase: "der num" }, x.diferencia === null
        ? "—" : dinero(x.diferencia, monedaActual))));
    for (const d of x.diferencias) {
      filas.push(h("tr", { clase: "sub" },
        h("td", { colspan: "5" }, reemplazar(
          t(d.cancelado ? "nom_md_dif_cancelado" : "nom_md_dif_corregido"),
          { p: d.persona, f: diaMes(d.fecha) })),
        h("td", { clase: "der num" }, dinero(d.monto, monedaActual))));
    }
  }
  caja.append(
    h("table", { clase: "tabla-cierre" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("nom_c_contrato")), h("th", {}, t("nom_c_mes")),
        h("th", {}, t("nom_c_como_va")),
        h("th", { clase: "der" }, t("nom_c_pagado_semana")),
        h("th", { clase: "der" }, t("nom_c_corresponde")),
        h("th", { clase: "der" }, t("nom_c_diferencia")))),
      h("tbody", {}, ...filas)),
    h("p", { clase: "gris chico", style: "margin:8px 0 0" }, t("nom_mes_ultimo_pie")));
  return caja;
}

/* --------------------------------------------------------- historial */

async function pintarHistorial(zona, zonaDetalle) {
  let cortes = [];
  try { cortes = await api.get(`/nomina?pais_id=${paisActual}`); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }
  if (!cortes.length) {
    return zona.replaceChildren(h("div", { clase: "tarjeta" },
      h("span", { clase: "gris" }, t("nom_sin_cortes"))));
  }
  zona.replaceChildren(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("nom_cortes"), "ay_nom_cortes", { style: "margin:0 0 12px" }),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, t("nom_semana_del")), h("th", {}, t("nom_personas")),
        h("th", { style: "text-align:right" }, t("nom_total")),
        h("th", {}, t("nom_estado")), h("th", {}, ""))),
      h("tbody", {}, ...cortes.slice(0, 12).map(c => h("tr", {},
        h("td", {}, h("b", {}, fecha(c.fecha_corte))),
        h("td", {}, String(c.personas)),
        h("td", { clase: "num", style: "text-align:right" },
          dinero(c.total, c.moneda)),
        h("td", {}, estadoDelCorte(c.estado)),
        h("td", {},
          h("button", { clase: "claro chico", type: "button",
            onclick: () => verCorte(zonaDetalle, c.id) },
            t("nom_ver")))))))));
}

async function verCorte(zona, nominaId) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("nom_cargando")));
  let n;
  try { n = await api.get(`/nomina/${nominaId}`); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }
  const pie = n.estado === "pagado"
    ? reemplazar(t("nom_pagado_el"), { f: diaHora(n.pagada_en),
                                       q: n.pagada_por || "—" })
    : "";
  zona.replaceChildren(h("div", { clase: "tarjeta" },
    cabeza(reemplazar(t("nom_corte_del"), { f: fecha(n.fecha_corte) }),
           estadoDelCorte(n.estado), pie),
    fichas(n), ...detalleDelCorte(n)));
  zona.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ------------------------------------------------------- ajustes

   Lo que no entra en el corte de esta semana pero se le debe —o se le
   descuenta— a alguien. Se arrastra al siguiente corte con su motivo
   escrito: un descuento sin motivo es una llamada al dia siguiente. */

function bloqueAjustes() {
  const caja = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("nom_ajustes"), "ay_nom_ajustes",
             { style: "margin:0 0 2px" }),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("nom_ajustes_pie")));
  const lista_ = h("div");
  caja.append(lista_);
  if (puede("calcular")) caja.append(formularioAjuste(() => cargar()));

  async function cargar() {
    let filas = [];
    try {
      filas = await api.get(`/nomina/ajustes/pendientes?pais_id=${paisActual}`);
    } catch (err) { return lista_.replaceChildren(aviso(err.message, "grave")); }

    if (!filas.length) {
      return lista_.replaceChildren(h("div", { clase: "gris chico" },
        t("nom_nada_pendiente")));
    }
    lista_.replaceChildren(h("table", {},
      h("tbody", {}, ...filas.map(a => h("tr", {},
        h("td", {}, h("b", {}, a.persona),
          h("div", { clase: "chico gris" }, a.motivo)),
        h("td", {}, etiqueta(Number(a.monto) < 0 ? t("nom_descuento")
                                                 : t("nom_a_favor"),
                             Number(a.monto) < 0 ? "grave" : "ok")),
        h("td", { clase: "num", style: "text-align:right" },
          dinero(a.monto, monedaActual)))))));
  }

  cargar();
  return caja;
}

function formularioAjuste(alGuardar) {
  const abrir = h("button", { clase: "claro chico", type: "button",
    onclick: () => { form.hidden = !form.hidden; } }, t("nom_registrar"));

  const quien = lista("persona_id", []);
  const monto = entrada("monto", { type: "number", step: "1",
                                   placeholder: t("nom_mas_menos") });
  const motivo = entrada("motivo", { placeholder: t("nom_por_que") });
  const form = h("div", { hidden: true, style: "margin-top:12px" },
    h("div", { clase: "rejilla tres" },
      campo(t("nom_persona"), quien), campo(t("nom_monto"), monto),
      campo(t("nom_motivo"), motivo)),
    h("div", { clase: "acciones" },
      h("button", { clase: "chico", type: "button",
        onclick: (e) => guardar(e) }, t("nom_guardar_ajuste"))));

  (async () => {
    const cat = await catalogos();
    quien.replaceChildren(...cat.personal.map(
      p => h("option", { value: p.id }, p.nombre)));
  })();

  async function guardar(e) {
    if (!quien.value || !monto.value || !motivo.value.trim()) {
      return mensaje(t("nom_falta_ajuste"), "alerta");
    }
    e.target.disabled = true;
    try {
      await api.post("/nomina/ajustes", {
        persona_id: Number(quien.value), pais_id: paisActual,
        monto: Number(monto.value), motivo: motivo.value.trim(),
      });
      mensaje(t("nom_ajuste_hecho"));
      monto.value = ""; motivo.value = "";
      form.hidden = true;
      alGuardar();
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  }

  return h("div", {},
    h("div", { clase: "acciones", style: "margin-top:12px" }, abrir),
    form);
}

/* ========================================================== comisiones */

const SELLO_CORTE = {
  abierto: ["nom_ce_abierto", ""],
  por_autorizar: ["nom_ce_por_autorizar", "alerta"],
  autorizado: ["nom_ce_autorizado", "info"],
  pagado: ["nom_ce_pagado", "ok"],
  por_pagar: ["nom_ce_por_pagar", "alerta"],
  sin_pago: ["nom_ce_sin_pago", ""],
};

function sello(estado) {
  const [texto, tono] = SELLO_CORTE[estado] || [estado, ""];
  return etiqueta(t(texto), tono);
}

function ultimoDia(anio, mes) {
  return new Date(anio, mes, 0).getDate();
}

async function pintarComisiones(zona, recargar) {
  const { anio, mes } = periodoActual;
  const c = await api.get(
    `/nomina/comisiones?pais_id=${paisActual}&anio=${anio}&mes=${mes}`);
  monedaActual = c.moneda || monedaActual;
  const periodo = nombreMes(anio, mes);
  const caja = h("div", { clase: "tarjeta" });

  caja.append(
    h("div", { style: "display:flex;justify-content:space-between;align-items:flex-start;gap:12px" },
      conAyuda("h2", reemplazar(t("nom_com_corte"), { m: periodo }),
               "ay_nom_comisiones", { style: "margin:0" }),
      sello(c.estado)),
    h("p", { clase: "gris chico", style: "margin:4px 0 0" },
      reemplazar(t("nom_com_regla"), {
        e: c.porcentajes.eventual ?? "—", i: c.porcentajes.implantado ?? "—" })),
    fases(c, anio, mes));

  if (c.solo_el_suyo) {
    caja.append(h("p", { clase: "gris chico" }, t("nom_com_suyo")));
  }

  if (!c.consultores.length) {
    caja.append(h("p", { clase: "gris" }, t("nom_com_vacio")));
  } else {
    caja.append(tablaConsultores(c, recargar));
  }

  const acciones = h("div", { clase: "acciones", style: "margin-top:16px" });
  if (puede("diferencia") && c.estado !== "pagado") {
    const zonaForm = h("div");
    acciones.append(h("button", { clase: "claro", type: "button",
      onclick: () => zonaForm.replaceChildren(
        formularioDiferencia(c, () => recargar())) },
      t("nom_registrar_diferencia")));
    caja.append(zonaForm);
  }
  if (puede("visto_bueno") && c.se_puede_autorizar) {
    acciones.append(h("button", { type: "button",
      onclick: (e) => vistoBueno(e, periodo, recargar) },
      t("nom_dar_visto_bueno")));
  }
  if (acciones.children.length) caja.append(acciones);
  if (puede("visto_bueno") && c.estado === "abierto") {
    const siguiente = mes === 12 ? `${anio + 1}-01-01`
      : `${anio}-${String(mes + 1).padStart(2, "0")}-01`;
    caja.append(h("p", { clase: "gris chico", style: "margin:8px 0 0" },
      reemplazar(t("nom_visto_desde"), { f: fecha(siguiente) })));
  }
  caja.append(h("p", { clase: "gris chico", style: "margin:8px 0 0" },
    t("nom_com_pie")));
  zona.replaceChildren(caja);
}

function fases(c, anio, mes) {
  const hecho = (estado) => estado === "hecha" ? "✓" : null;
  const paso = (clase, numero, nombre, cuando) => h("li", { clase },
    h("span", { clase: "punto" }, hecho(clase) || String(numero)),
    h("b", {}, nombre), h("span", { clase: "cuando" }, cuando));
  const acumula = c.estado === "abierto" ? "actual" : "hecha";
  const visto = c.estado === "por_autorizar" ? "actual"
    : (c.estado === "autorizado" || c.estado === "pagado") ? "hecha" : "";
  const pagado = c.estado === "autorizado" ? "actual"
    : c.estado === "pagado" ? "hecha" : "";
  return h("ol", { clase: "fases", style: "margin-top:16px" },
    paso(acumula, 1, t("nom_paso_acumula"),
      reemplazar(t("nom_paso_acumula_de"), {
        d: `01/${String(mes).padStart(2, "0")}`,
        a: `${ultimoDia(anio, mes)}/${String(mes).padStart(2, "0")}` })),
    paso(visto, 2, t("nom_paso_visto"), c.autorizado_en
      ? reemplazar(t("nom_paso_visto_hecho"), { q: c.autorizado_por || "—",
                                                f: diaMes(c.autorizado_en) })
      : t("nom_paso_visto_de")),
    paso(pagado, 3, t("nom_paso_pagado"), c.pagado_en
      ? diaMes(c.pagado_en) : t("nom_paso_pagado_de")));
}

function tablaConsultores(c, recargar) {
  const cuerpo = h("tbody");
  const detalle = h("div");
  function pintar() {
    const filas = [];
    const partes = [];
    for (const f of c.consultores) {
      const clave = `com:${c.anio}-${c.mes}:${f.consultor_id}:${f.moneda}`;
      const abierta = abiertas.has(clave);
      const m = f.moneda;
      const tot = f.totales;
      const cuantos = f.se_paga.length;
      filas.push(h("tr", {},
        h("td", {},
          h("a", { href: "#", onclick: (e) => {
            e.preventDefault();
            if (abierta) abiertas.delete(clave); else abiertas.add(clave);
            pintar();
          } }, `${abierta ? "▾" : "▸"} `, abierta ? h("b", {}, f.consultor) : f.consultor),
          h("div", { clase: "gris chico" },
            reemplazar(t("nom_cc_servicios"), { n: cuantos }))),
        h("td", { clase: "der num" }, dinero(tot.se_paga, m)),
        h("td", { clase: "der num" }, Number(tot.no_se_paga)
          ? dinero(tot.no_se_paga, m) : "—",
          f.no_se_paga.length ? h("div", { clase: "gris chico" },
            reemplazar(t("nom_cc_servicios"), { n: f.no_se_paga.length })) : null),
        h("td", { clase: "der num" }, Number(tot.diferencias)
          ? dinero(tot.diferencias, m) : "—"),
        h("td", { clase: "der num" }, h("b", {}, dinero(tot.a_pagar, m)),
          Number(tot.en_contra) ? h("div", {}, etiqueta(reemplazar(
            t("nom_al_siguiente_mes"), { m: dinero(tot.en_contra, m) }), "grave"))
            : null),
        h("td", {}, sello(f.estado))));
      if (abierta) partes.push(detalleConsultor(f, recargar));
    }
    if (c.consultores.length > 1) {
      const tot = c.totales;
      filas.push(h("tr", { clase: "total" },
        h("td", {}, h("b", {}, t("nom_cc_total_mes"))),
        h("td", { clase: "der num" }, dinero(tot.se_paga, c.moneda)),
        h("td", { clase: "der num" }, dinero(tot.no_se_paga, c.moneda)),
        h("td", { clase: "der num" }, dinero(tot.diferencias, c.moneda)),
        h("td", { clase: "der num" }, h("b", {}, dinero(tot.a_pagar, c.moneda))),
        h("td", {})));
    }
    cuerpo.replaceChildren(...filas);
    detalle.replaceChildren(...partes);
  }
  pintar();
  return h("div", {},
    h("table", { clase: "tabla-cierre", style: "margin-top:12px" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("nom_cc_consultor")),
        h("th", { clase: "der" }, t("nom_cc_se_paga")),
        h("th", { clase: "der" }, t("nom_cc_no_se_paga")),
        h("th", { clase: "der" }, t("nom_cc_diferencias")),
        h("th", { clase: "der" }, t("nom_cc_total")),
        h("th", {}, t("nom_cc_estado")))),
      cuerpo),
    detalle);
}

function servicioDe(r) {
  return r.periodo
    ? reemplazar(t("nom_cs_implantado_de"), {
        f: r.folio, m: nombreMes(Number(r.periodo.slice(0, 4)),
                                 Number(r.periodo.slice(5, 7))) })
    : reemplazar(t("nom_cs_eventual"), { f: r.folio });
}

const CLASE_DIFERENCIA = {
  refacturacion: "nom_cd_refacturacion",
  no_cobrada: "nom_cd_no_cobrada",
  manual: "nom_cd_manual",
  saldo_en_contra: "nom_cd_saldo_en_contra",
};

function detalleConsultor(f, recargar) {
  const m = f.moneda;
  const caja = h("div", { style: "border:1px solid var(--linea);border-radius:8px;padding:4px 16px 14px;margin-top:14px;background:#fcfcfd" });
  const titulo = (clave) => h("h4", { clase: "seccion" },
    reemplazar(t(clave), { q: f.consultor }));

  if (f.se_paga.length) {
    caja.append(titulo("nom_cs_se_paga"), h("table", { clase: "tabla-cierre" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("nom_c_servicio")), h("th", {}, t("nom_cs_validado")),
        h("th", { clase: "der" }, t("nom_cs_facturado")),
        h("th", { clase: "der" }, t("nom_cs_gastos")),
        h("th", { clase: "der" }, t("nom_cs_base")),
        h("th", { clase: "der" }, "%"),
        h("th", { clase: "der" }, t("nom_cs_comision")))),
      h("tbody", {}, ...f.se_paga.map(r => h("tr", {},
        h("td", {}, servicioDe(r)), h("td", {}, diaMes(r.validado)),
        h("td", { clase: "der num" }, dinero(r.facturacion, m)),
        h("td", { clase: "der num" }, dinero(r.viaticos, m)),
        h("td", { clase: "der num" }, dinero(r.base, m)),
        h("td", { clase: "der" }, `${r.porcentaje} %`),
        h("td", { clase: "der num" }, dinero(r.monto, m)))),
        h("tr", { clase: "total" },
          h("td", { colspan: "6" }, h("b", {}, t("nom_cc_se_paga"))),
          h("td", { clase: "der num" }, h("b", {}, dinero(f.totales.se_paga, m)))))));
  }

  if (f.no_se_paga.length) {
    const tabla = h("table", { clase: "tabla-cierre" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("nom_c_servicio")), h("th", {}, t("nom_cs_por_que")),
        h("th", { clase: "der" }, t("nom_cs_comision")), h("th", {}))),
      h("tbody", {}, ...f.no_se_paga.map(r => {
        const perdida = r.estatus === "perdida";
        const porque = perdida
          ? reemplazar(t("nom_cn_perdida_texto"), { l: diaHora(r.limite),
                                                    v: diaHora(r.visto_bueno) })
          : t("nom_cn_retenida_texto");
        const zonaDecidir = h("div");
        return h("tr", {},
          h("td", {}, servicioDe(r)),
          h("td", {}, etiqueta(t(perdida ? "nom_cn_perdida" : "nom_cn_retenida"),
                               perdida ? "grave" : "alerta"), " ", porque, zonaDecidir),
          h("td", { clase: "der num" }, dinero(r.monto, m)),
          h("td", { clase: "der" }, !perdida && puede("decidir")
            ? h("button", { clase: "claro chico", type: "button",
                onclick: () => zonaDecidir.replaceChildren(
                  formularioDecidir(r, recargar)) }, t("nom_decidir"))
            : null));
      })));
    caja.append(titulo("nom_cs_no_se_paga"), tabla);
  }

  if (f.diferencias.length) {
    const tabla = h("table", { clase: "tabla-cierre" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("nom_c_servicio")), h("th", {}, t("nom_cd_que_cambio")),
        h("th", {}, t("nom_cd_quien")), h("th", { clase: "der" }, t("nom_c_monto")))),
      h("tbody", {}, ...f.diferencias.map(d => h("tr", {},
        h("td", {}, d.folio || "—"),
        h("td", {}, h("b", {}, t(CLASE_DIFERENCIA[d.tipo] || "nom_cd_manual")),
          d.motivo ? h("div", { clase: "gris chico" }, d.motivo) : null),
        h("td", {}, [d.quien || t("nom_cd_automatica"),
                     diaMes(d.creado_en)].join(" · ")),
        h("td", { clase: "der num" }, dinero(d.monto, m))))));
    caja.append(titulo("nom_cs_diferencias"), tabla);
  }

  if (f.en_camino.length) {
    caja.append(titulo("nom_cs_en_camino"),
      h("p", { clase: "gris chico", style: "margin:0 0 6px" }, t("nom_ca_pie")),
      h("table", { clase: "tabla-cierre" },
        h("thead", {}, h("tr", {},
          h("th", {}, t("nom_c_servicio")), h("th", {}, t("nom_ca_visto")),
          h("th", { clase: "der" }, t("nom_ca_estimada")))),
        h("tbody", {}, ...f.en_camino.map(e => h("tr", {},
          h("td", {}, servicioDe(e)), h("td", {}, diaMes(e.visto_bueno)),
          h("td", { clase: "der num" }, e.se_pierde
            ? etiqueta(t("nom_ca_se_pierde"), "grave") : dinero(e.monto, m)))))));
  }

  if (f.pago) {
    const p = f.pago;
    if (p.pagado_en && Number(p.total) > 0) {
      caja.append(h("p", { clase: "chico", style: "margin:12px 0 0" },
        etiqueta(t("nom_ce_pagado"), "ok"), " ",
        reemplazar(t("nom_pago_hecho"), { f: diaHora(p.pagado_en),
                                          r: p.referencia || "—",
                                          q: p.pagado_por || "—" })));
    } else if (!p.pagado_en && puede("pagar_comision")) {
      const referencia = entrada("referencia", { placeholder: t("nom_pagar_referencia"),
                                                 "data-crudo": "",
                                                 style: "max-width:320px" });
      caja.append(h("div", { clase: "acciones", style: "margin-top:12px" },
        referencia,
        h("button", { type: "button", onclick: async (e) => {
          e.target.disabled = true;
          try {
            await api.post(`/nomina/comisiones/pagos/${p.pago_id}/pagar`,
                           { referencia: referencia.value });
            mensaje(t("nom_comision_pagada"));
            await recargar();
          } catch (err) {
            mensaje(err.message, "grave");
            e.target.disabled = false;
          }
        } }, reemplazar(t("nom_marcar_pagado"), { m: dinero(p.total, m) }))));
    }
  }
  return caja;
}

function formularioDecidir(r, recargar) {
  const motivo = h("textarea", { rows: 2, placeholder: t("nom_decidir_motivo") });
  const decidir = async (e, seCobra) => {
    e.target.disabled = true;
    try {
      await api.post(`/comisiones/${r.comision_id}/resolver`,
                     { se_paga: seCobra, resolucion: motivo.value.trim() });
      mensaje(t("nom_decidido"));
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  };
  return h("div", { style: "margin-top:8px" }, motivo,
    h("div", { clase: "acciones", style: "margin-top:6px" },
      h("button", { clase: "chico", type: "button",
        onclick: (e) => decidir(e, true) }, t("nom_decidir_se_paga")),
      h("button", { clase: "claro chico", type: "button",
        onclick: (e) => decidir(e, false) }, t("nom_decidir_no"))));
}

function formularioDiferencia(c, alGuardar) {
  const quien = lista("consultor_id", []);
  const monto = entrada("monto", { type: "number", step: "0.01",
                                   placeholder: t("nom_mas_menos") });
  const motivo = entrada("motivo", { placeholder: t("nom_por_que") });
  /* Los consultores de la consola, mas los que ya salen en este corte
     aunque hoy ya no tengan acceso: a ellos tambien se les corrige. */
  (async () => {
    const cat = await catalogos();
    const todos = new Map(cat.consultores.map(p => [p.id, p.nombre]));
    for (const f of c.consultores) {
      if (!todos.has(f.consultor_id)) todos.set(f.consultor_id, f.consultor);
    }
    quien.replaceChildren(...[...todos].map(
      ([id, nombre]) => h("option", { value: id }, nombre)));
  })();
  const guardar = async (e) => {
    if (!quien.value || !monto.value || !motivo.value.trim()) {
      return mensaje(t("nom_dif_falta"), "alerta");
    }
    e.target.disabled = true;
    try {
      await api.post("/nomina/comisiones/diferencias", {
        pais_id: paisActual, consultor_id: Number(quien.value),
        monto: monto.value, motivo: motivo.value.trim() });
      mensaje(t("nom_dif_hecha"));
      alGuardar();
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  };
  return h("div", { clase: "tarjeta lisa", style: "margin-top:12px" },
    h("div", { clase: "rejilla tres" },
      campo(t("nom_cc_consultor"), quien), campo(t("nom_monto"), monto),
      campo(t("nom_motivo"), motivo)),
    h("div", { clase: "acciones" },
      h("button", { clase: "chico", type: "button", onclick: guardar },
        t("nom_dif_guardar"))));
}

async function vistoBueno(e, periodo, recargar) {
  if (!confirm(reemplazar(t("nom_confirmar_visto"), { m: periodo }))) return;
  e.target.disabled = true;
  try {
    await api.post("/nomina/comisiones/visto-bueno", {
      pais_id: paisActual, anio: periodoActual.anio, mes: periodoActual.mes });
    mensaje(t("nom_visto_hecho"));
    await recargar();
  } catch (err) {
    mensaje(err.message, "grave");
    e.target.disabled = false;
  }
}

/* ------------------------------------------------ el tabulador

   Lo que se le paga al personal por un dia de servicio. Dos tablas, una
   por tipo de operacion: un dia suelto que arranca en un aeropuerto y un
   dia de la misma persona en el mismo lugar no se pagan igual, y con un
   solo numero para las dos siempre se le paga mal a alguien.

   Tiene su pestana: es configuracion, no el trabajo de todos los lunes. */

async function pintarTabulador(zona) {
  const datos = await api.get(`/nomina/tabulador?pais_id=${paisActual}`);
  const faltan = datos.eventual.sin_cargar + datos.implantado.sin_cargar;
  zona.replaceChildren(h("div", { clase: "tarjeta" },
    h("div", { clase: "acciones", style: "margin-bottom:12px" },
      h("h2", { style: "margin:0" }, t("nom_tabulador")),
      /* Un cruce sin monto no es un detalle de captura: es un dia que no
         se va a poder pagar, y el corte se detiene por el. */
      faltan
        ? etiqueta(t("nom_cruces_faltan").replace("{n}", faltan), "alerta")
        : etiqueta(t("nom_completo"), "ok")),
    tablaComision(t("nom_eventuales"), datos, datos.eventual, "eventual"),
    tablaComision(t("nom_implantados"), datos, datos.implantado, "implantado")));
}

function tablaComision(titulo, datos, tabla, tipo) {
  const celdas = [];
  const cuerpoTabla = h("tbody");

  for (const r of tabla.renglones) {
    const fila = h("tr", {}, h("td", {}, h("b", {}, r.rol)));
    for (const c of r.celdas) {
      const monto = entrada("monto", {
        type: "number", step: "1", min: "0", clase: "num",
        style: "text-align:right; max-width:110px",
        value: c.monto !== null ? String(Math.round(Number(c.monto))) : "",
        placeholder: t("nom_sin_cargar"),
      });
      /* La hora extra solo donde la modalidad la admite. Ofrecerla donde
         no aplica invita a capturar un numero que nunca se va a usar. */
      const extra = c.aplica_horas_extra
        ? entrada("he", {
            type: "number", step: "1", min: "0", clase: "num",
            style: "text-align:right; max-width:90px",
            value: c.monto_hora_extra !== null
              ? String(Math.round(Number(c.monto_hora_extra))) : "",
            placeholder: t("nom_h_extra"),
          })
        : null;
      celdas.push({ perfil_id: r.perfil_id, modalidad_id: c.modalidad_id,
                    monto, extra });
      fila.append(h("td", { style: "text-align:right" },
        monto,
        extra ? h("div", { style: "margin-top:4px" }, extra) : null));
    }
    cuerpoTabla.append(fila);
  }

  const guardar = h("button", { clase: "chico", type: "button",
    onclick: (e) => mandar(e) },
    reemplazar(t("nom_tab_guardar"), { t: titulo.toLowerCase() }));

  async function mandar(e) {
    e.target.disabled = true;
    try {
      await api.put("/nomina/tabulador", {
        pais_id: paisActual,
        tipo_servicio: tipo,
        renglones: celdas
          .filter(c => c.monto.value !== "")
          .map(c => ({
            perfil_id: c.perfil_id,
            modalidad_id: c.modalidad_id,
            monto: Number(c.monto.value || 0),
            monto_hora_extra: c.extra && c.extra.value !== ""
              ? Number(c.extra.value) : null,
          })),
      });
      mensaje(t("nom_tab_guardado").replace("{t}", titulo.toLowerCase()));
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  }

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" },
    h("h4", { style: "margin:0 0 2px" }, titulo),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      t("nom_tab_pie").replace("{m}", datos.moneda)),
    h("div", { style: "overflow-x:auto" },
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, t("nom_rol")),
          /* Cada tabla trae sus propias modalidades: el implantado es
             siempre dia completo, y las columnas de medio dia y transfer
             ahi no significan nada. */
          ...tabla.modalidades.map(x => h("th", { style: "text-align:right" },
            x.codigo,
            h("div", { clase: "gris chico" }, `${x.horas} h`))))),
        cuerpoTabla)),
    h("div", { clase: "acciones", style: "margin-top:10px" }, guardar));
}

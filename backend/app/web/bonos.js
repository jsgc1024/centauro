/* El bono del personal de seguridad.

   Tres cosas en una pantalla, porque son tres momentos del mismo mes:
   que se mide y cuanto vale (criterios), quien gano que (el mes), y que
   hay que depositar el dia 5 (por pagar).

   El calendario manda sobre todo lo demas. El mes se calcula el dia 3
   --no el 1: el viatico del ultimo dia tiene 24 horas para
   comprobarse-- y se paga el 5, o el primer habil despues. Entre esas
   dos fechas hay una firma, y quien firma no es quien deposita.

   Lo que se autoriza se congela: de ahi en adelante es dinero, y el
   dinero no se recalcula. */
import { api, sesion } from "./api.js";
import { aviso, campo, conAyuda, dinero, etiqueta, h, lista,
         mensaje } from "./util.js";
import { catalogos } from "./catalogos.js";
import { t } from "./idioma.js";


let paisActual = null;
let periodoActual = null;
let pestanaActual = "mes";

/* El mes vencido: el que se cierra hoy. En enero, diciembre. */
function mesVencido() {
  const hoy = new Date();
  const anio = hoy.getMonth() === 0 ? hoy.getFullYear() - 1 : hoy.getFullYear();
  const mes = hoy.getMonth() === 0 ? 12 : hoy.getMonth();
  return { anio, mes };
}

function puede(actividad) {
  const rol = sesion.usuario && sesion.usuario.rol;
  const DE_TODOS = ["consultor", "director_operaciones", "director_general",
                    "finanzas", "central", "recursos_humanos", "admin"];
  /* Quien firma el bono y quien fija los montos no son la misma mano:
     la direccion decide cuanto vale cada cosa, RRHH cierra el mes. */
  const FIRMA = ["recursos_humanos", "director_general", "admin"];
  const CONFIGURA = ["director_operaciones", "director_general", "admin"];
  if (actividad === "ver") return DE_TODOS.includes(rol);
  if (actividad === "autorizar") return FIRMA.includes(rol);
  if (actividad === "configurar") return CONFIGURA.includes(rol);
  if (actividad === "pagar") return ["finanzas", "admin"].includes(rol);
  return false;
}

export async function pantallaBonos(main) {
  const cat = await catalogos();
  if (!periodoActual) periodoActual = mesVencido();

  main.append(
    h("h1", {}, t("bon_titulo")),
    h("p", { clase: "sub" }, t("bon_sub")));

  const paises = lista("pais", cat.paises.map(
    p => ({ valor: p.id, texto: p.nombre })));
  paisActual = paisActual || (cat.paises[0] && cat.paises[0].id);
  if (paisActual) paises.value = paisActual;

  const meses = lista("mes", Array.from({ length: 12 }, (_, i) => (
    { valor: i + 1, texto: t(`bon_mes_${i + 1}`) })));
  meses.value = periodoActual.mes;

  const anios = lista("anio", [periodoActual.anio, periodoActual.anio - 1]
    .map(a => ({ valor: a, texto: String(a) })));
  anios.value = periodoActual.anio;

  const zona = h("div");

  async function recargar() {
    paisActual = Number(paises.value);
    periodoActual = { anio: Number(anios.value), mes: Number(meses.value) };
    zona.replaceChildren(h("p", { clase: "gris" }, t("bon_cargando")));
    try {
      if (pestanaActual === "criterios") await pintarCriterios(zona, recargar);
      else if (pestanaActual === "pagar") await pintarCorte(zona, recargar);
      else await pintarMes(zona, recargar);
    } catch (err) {
      zona.replaceChildren(aviso(err.message, "grave"));
    }
  }

  for (const control of [paises, meses, anios]) {
    control.addEventListener("change", recargar);
  }

  const pestanas = h("div", { clase: "pestanas" });
  const DISPONIBLES = [
    ["mes", "bon_tab_mes", true],
    ["criterios", "bon_tab_criterios", puede("configurar") || puede("ver")],
    ["pagar", "bon_tab_pagar", puede("pagar") || puede("ver")],
  ];
  for (const [clave, texto, visible] of DISPONIBLES) {
    if (!visible) continue;
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
      h("div", { clase: "rejilla tres" },
        campo(t("pais"), paises),
        campo(t("bon_mes"), meses),
        campo(t("bon_anio"), anios)),
      pestanas),
    zona);

  await recargar();
}

/* ------------------------------------------------------- A. los criterios */

async function pintarCriterios(zona, recargar) {
  const d = await api.get(`/criterios/${paisActual}`);
  const editable = puede("configurar");

  const filas = d.criterios.map(c => {
    const monto = h("input", {
      clase: "campo num", type: "number", step: "1", min: "0",
      value: String(Number(c.monto_mensual)), disabled: !editable,
    });
    const umbral = h("input", {
      clase: "campo num", type: "number", step: "1", min: "0",
      value: String(Number(c.umbral_pct)), disabled: !editable,
    });
    const minutos = h("input", {
      clase: "campo num", type: "number", step: "1", min: "0",
      value: String(c.tolerancia_minutos), disabled: !editable,
    });
    const veces = h("input", {
      clase: "campo num", type: "number", step: "1", min: "0",
      value: String(c.tolerancia_ocasiones), disabled: !editable,
    });

    const guardar = h("button", {
      clase: "chico", type: "button", disabled: !editable,
      onclick: async () => {
        try {
          await api.put(`/criterios/${c.id}`, {
            monto_mensual: Number(monto.value),
            umbral_pct: Number(umbral.value),
            tolerancia_minutos: Number(minutos.value),
            tolerancia_ocasiones: Number(veces.value),
            reparte: c.reparte, activo: c.activo,
          });
          mensaje(t("bon_guardado"));
          recargar();
        } catch (err) { mensaje(err.message, "grave"); }
      },
    }, t("bon_guardar"));

    return h("tr", {},
      h("td", {},
        h("b", {}, c.nombre),
        h("div", { clase: "chico gris" },
          c.reparte ? t("bon_reparte") : t("bon_no_reparte"))),
      h("td", { clase: "num" }, `${c.peso_pct}%`),
      h("td", {}, monto),
      h("td", {}, umbral),
      h("td", {}, minutos),
      h("td", {}, veces),
      h("td", {}, c.activo ? etiqueta(t("bon_activo"), "ok") : etiqueta(t("bon_inactivo"))),
      h("td", {}, guardar));
  });

  zona.replaceChildren(
    h("div", { clase: "tarjeta" },
      conAyuda("h3", t("bon_criterios_titulo"), "bonos_criterios"),
      h("p", { clase: "chico gris" }, t("bon_criterios_pie")),
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, t("bon_criterio")),
          h("th", {}, t("bon_peso")),
          h("th", {}, t("bon_monto")),
          h("th", {}, t("bon_umbral")),
          h("th", {}, t("bon_margen_min")),
          h("th", {}, t("bon_margen_veces")),
          h("th", {}, t("bon_estado")),
          h("th", {}, ""))),
        h("tbody", {}, ...filas)),
      h("div", { clase: "total_barra" },
        h("span", {}, t("bon_posible")),
        h("b", {}, dinero(d.bono_posible, d.moneda))),
      aviso(t("bon_aviso_vigencia"), "alerta")));
}

/* ------------------------------------------------------------- B. el mes */

function estrellas(ganadas, posibles) {
  const total = Math.max(posibles, ganadas);
  return h("span", { clase: "estrellas" },
    "★".repeat(ganadas),
    h("span", { clase: "apagada" }, "★".repeat(Math.max(0, total - ganadas))));
}

async function pintarMes(zona, recargar) {
  const { anio, mes } = periodoActual;
  const d = await api.get(`/mes/${paisActual}/${anio}/${mes}`);

  if (!d.evaluados) {
    zona.replaceChildren(
      h("div", { clase: "tarjeta" },
        h("div", { clase: "vacio" }, t("bon_mes_vacio"))));
    return;
  }

  const seleccion = new Set();
  const porAutorizar = d.personas.filter(p => p.estatus === "calculada");

  const filas = d.personas.map(p => {
    const marca = h("input", { type: "checkbox",
      disabled: p.estatus !== "calculada" || !puede("autorizar"),
      onchange: (e) => {
        if (e.target.checked) seleccion.add(p.evaluacion_id);
        else seleccion.delete(p.evaluacion_id);
      } });

    const accion = p.estatus === "calculada" && puede("autorizar")
      ? h("button", { clase: "chico", type: "button",
          onclick: () => autorizar([p.evaluacion_id], recargar) },
          t("bon_autorizar"))
      : h("button", { clase: "claro chico", type: "button",
          onclick: () => abrirFicha(zona, p, recargar) }, t("bon_ver"));

    return h("tr", {},
      h("td", {}, marca),
      h("td", {},
        h("a", { href: "#", onclick: (e) => {
          e.preventDefault(); abrirFicha(zona, p, recargar);
        } }, p.persona),
        p.anulado_por_incidencia
          ? h("div", { clase: "chico gris" }, t("bon_anulada_pie")) : null),
      h("td", {}, p.plaza || "—"),
      h("td", { clase: "num" }, String(p.jornadas)),
      h("td", {}, estrellas(p.estrellas, p.estrellas_posibles)),
      h("td", { clase: "num" }, dinero(p.bono, p.moneda)),
      h("td", {},
        p.anulado_por_incidencia
          ? etiqueta(t("bon_anulada"), "grave")
          : etiqueta(t(`bon_est_${p.estatus}`),
                     p.estatus === "pagada" ? "ok"
                     : p.estatus === "autorizada" ? "ok" : "")),
      h("td", {}, accion));
  });

  const lote = h("button", {
    type: "button", disabled: !porAutorizar.length || !puede("autorizar"),
    onclick: () => autorizar([...seleccion], recargar),
  }, t("bon_autorizar_lote"));

  zona.replaceChildren(
    h("div", { clase: "corte" },
      cifra(d.evaluados, "bon_evaluados"),
      cifra(d.bono_completo, "bon_completo"),
      cifra(d.bono_parcial, "bon_parcial"),
      cifra(d.en_cero, "bon_en_cero", "rojo"),
      cifra(dinero(d.por_autorizar), "bon_por_autorizar")),
    h("div", { clase: "tarjeta lisa" },
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, ""),
          h("th", {}, t("bon_persona")),
          h("th", {}, t("bon_plaza")),
          h("th", {}, t("bon_jornadas")),
          h("th", {}, t("bon_estrellas")),
          h("th", {}, t("bon_bono")),
          h("th", {}, t("bon_estado")),
          h("th", {}, ""))),
        h("tbody", {}, ...filas)),
      h("div", { clase: "acciones" }, lote),
      aviso(t("bon_aviso_autorizar"), "")));
}

function cifra(valor, clave, tono = "") {
  return h("div", {},
    h("div", { clase: `cifra ${tono}` }, String(valor)),
    h("div", { clase: "chico gris" }, t(clave)));
}

async function autorizar(ids, recargar) {
  if (!ids.length) return;
  try {
    const r = ids.length === 1
      ? await api.post(`/evaluaciones/${ids[0]}/autorizar`, {})
      : await api.post("/evaluaciones/autorizar-lote", { evaluacion_ids: ids });
    if (r.ya_pagadas && r.ya_pagadas.length) {
      mensaje(`${t("bon_ya_pagadas")}: ${r.ya_pagadas.join(", ")}`, "alerta");
    } else {
      mensaje(t("bon_autorizado"));
    }
    recargar();
  } catch (err) { mensaje(err.message, "grave"); }
}

/* ---------------------------------------------------- C. la ficha de uno */

async function abrirFicha(zona, persona, recargar) {
  const { anio, mes } = periodoActual;
  let ficha;
  try {
    ficha = await api.get(`/evaluaciones/${persona.persona_id}/${anio}/${mes}`);
  } catch (err) { return mensaje(err.message, "grave"); }

  const criterios = ficha.criterios.map(c => h("div", { clase: "criterio" },
    h("div", { clase: `marca_bono ${c.cumplido ? "si" : c.aplica ? "no" : "na"}` },
      c.cumplido ? "✓" : c.aplica ? "✕" : "—"),
    h("div", { clase: "cuerpo" },
      h("div", { clase: "nombre" }, c.criterio),
      /* La frase con fechas. Es la pieza que convierte un bono perdido
         en una conversacion y no en un pleito con recursos humanos. */
      h("div", { clase: "chico gris" }, c.detalle || "")),
    h("div", { clase: "num" }, dinero(c.monto, ficha.moneda))));

  zona.replaceChildren(...[
    h("div", { clase: "tarjeta" },
      h("div", { clase: "cabeza_ficha" },
        h("div", {},
          h("h3", {}, ficha.persona),
          h("div", { clase: "chico gris" },
            `${ficha.periodo} · ${ficha.jornadas_evaluadas} ${t("bon_jornadas_eval")}`)),
        h("div", { style: "text-align:right" },
          estrellas(ficha.estrellas, ficha.estrellas_posibles),
          h("div", { clase: "chico gris" },
            `${ficha.estrellas} / ${ficha.estrellas_posibles}`))),
      ficha.incidencia
        ? aviso(`${t("bon_anulada_por")} ${ficha.incidencia.gravedad} · `
                + `${ficha.incidencia.fecha} · ${ficha.incidencia.descripcion}`,
                "grave")
        : null,
      ...criterios,
      h("div", { clase: "total_barra" },
        h("span", {}, t("bon_total_mes")),
        h("b", {}, dinero(ficha.bono, ficha.moneda))),
      h("div", { clase: "acciones" },
        h("button", { clase: "claro", type: "button",
          onclick: recargar }, t("bon_volver"))))].filter(Boolean));
}

/* ------------------------------------------------------- D. lo por pagar */

async function pintarCorte(zona, recargar) {
  const { anio, mes } = periodoActual;
  const d = await api.get(`/corte/${paisActual}/${anio}/${mes}`);

  if (!d.personas.length) {
    zona.replaceChildren(
      h("div", { clase: "tarjeta" },
        h("div", { clase: "vacio" }, t("bon_corte_vacio"))));
    return;
  }

  const filas = d.personas.map(p => {
    const referencia = h("input", { clase: "campo", type: "text",
      placeholder: t("bon_referencia") });
    const boton = h("button", { clase: "chico", type: "button",
      disabled: !!p.pago || !puede("pagar"),
      onclick: async () => {
        if (!referencia.value.trim()) return mensaje(t("bon_falta_ref"), "alerta");
        try {
          await api.post(`/evaluaciones/${p.evaluacion_id}/pagar`,
                         { referencia: referencia.value.trim() });
          mensaje(t("bon_pagado"));
          recargar();
        } catch (err) { mensaje(err.message, "grave"); }
      } }, t("bon_confirmar"));

    return h("tr", {},
      h("td", {}, h("b", {}, p.persona),
        h("div", { clase: "chico gris" }, p.plaza || "—")),
      h("td", {}, estrellas(p.estrellas, p.estrellas_posibles)),
      h("td", { clase: "num" }, dinero(p.bono, p.moneda)),
      p.pago
        ? h("td", { colspan: "2" },
            etiqueta(t("bon_est_pagada"), "ok"),
            h("div", { clase: "chico gris" }, p.pago.referencia))
        : h("td", {}, referencia),
      p.pago ? null : h("td", {}, boton));
  });

  zona.replaceChildren(
    h("div", { clase: "corte" },
      cifra(d.por_pagar, "bon_por_pagar"),
      cifra(dinero(d.monto_por_pagar), "bon_monto_por_pagar"),
      cifra(d.pagados, "bon_ya_pagados")),
    h("div", { clase: "tarjeta lisa" },
      conAyuda("h3", t("bon_corte_titulo"), "bonos_corte"),
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, t("bon_persona")),
          h("th", {}, t("bon_estrellas")),
          h("th", {}, t("bon_bono")),
          h("th", {}, t("bon_referencia")),
          h("th", {}, ""))),
        h("tbody", {}, ...filas)),
      aviso(t("bon_aviso_corte"), "")));
}

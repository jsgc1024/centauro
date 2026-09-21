/* Nomina del personal de seguridad.

   Aqui se paga el trabajo de la calle: los dias que cada quien cubrio y
   el rol con el que los cubrio. Es otra cosa que los gastos del
   servicio —viaticos y compras—, que viven en su propia pantalla.

   El corte corre por semana y por pais. Mientras no se pague se puede
   recalcular las veces que haga falta; una vez pagado ya no se toca, y
   lo que cambie despues viaja hacia adelante como ajuste. Eso no es una
   limitacion del sistema: es que el dinero ya salio. */
import { api } from "./api.js";
import { aviso, campo, conAyuda, dinero, entrada, estatus, etiqueta,
         fecha, h, lista, mensaje } from "./util.js";
import { catalogos } from "./catalogos.js";
import { t } from "./idioma.js";

let paisActual = null;
let corteActual = null;

export async function pantallaNomina(main) {
  const cat = await catalogos();

  main.append(
    h("h1", {}, t("nom_titulo")),
    h("p", { clase: "sub" }, t("nom_sub")));

  const paises = lista("pais", cat.paises.map(
    p => ({ valor: p.id, texto: p.nombre })));
  paisActual = paisActual || (cat.paises[0] && cat.paises[0].id);
  if (paisActual) paises.value = paisActual;

  const zona = h("div");
  const historial = h("div");
  const tabulador = h("div");

  paises.addEventListener("change", async () => {
    paisActual = Number(paises.value);
    corteActual = null;
    await pintarTabulador(tabulador);
    await pintarHistorial(historial, zona);
    zona.replaceChildren();
  });

  main.append(
    h("div", { clase: "tarjeta lisa" },
      h("div", { clase: "rejilla tres" },
        campo(t("pais"), paises),
        h("div", { clase: "campo" },
          h("label", {}, " "),
          h("button", { clase: "chico", type: "button",
            onclick: (e) => calcular(e, zona, historial) },
            t("nom_calcular"))))),
    tabulador, historial, zona);

  await pintarTabulador(tabulador);
  await pintarHistorial(historial, zona);
}

/* -------------------------------------------------------- calcular

   El motor se niega a armar el corte si alguna jornada no tiene tarifa,
   y contesta con la lista de quienes. Eso no es un error que esconder:
   pagar de menos a alguien que trabajo es peor que retrasar el corte,
   asi que la pantalla lo pone completo, con nombre y fecha. */

async function calcular(e, zona, historial) {
  e.target.disabled = true;
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("nom_calculando")));
  try {
    const r = await api.post("/nomina/calcular", { pais_id: paisActual });
    mensaje(t("nom_corte_armado").replace("{n}", r.personas));
    corteActual = r.nomina_id;
    await pintarHistorial(historial, zona);
    await pintarCorte(zona, r.nomina_id);
  } catch (err) {
    zona.replaceChildren(bloqueSinTarifa(err));
  } finally {
    e.target.disabled = false;
  }
}

function bloqueSinTarifa(err) {
  const d = err.detalle || {};
  const filas = d.sin_tarifa || [];
  if (!filas.length) return aviso(err.message, "grave");

  return h("div", { clase: "tarjeta" },
    h("h3", { style: "margin:0 0 2px" }, t("nom_no_sale")),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      err.message),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, t("nom_persona")), h("th", {}, t("nom_dia")),
        h("th", {}, t("nom_modalidad")), h("th", {}, t("nom_rol")),
        h("th", {}, t("nom_tipo")))),
      h("tbody", {}, ...filas.map(f => h("tr", {},
        h("td", {}, h("b", {}, f.persona)),
        h("td", {}, fecha(f.fecha)),
        h("td", {}, f.modalidad),
        h("td", {}, f.rol || etiqueta(t("nom_sin_rol"), "grave")),
        h("td", { clase: "chico gris" }, f.tipo))))));
}

/* -------------------------------------------------------- historial */

async function pintarHistorial(zona, zonaCorte) {
  let cortes = [];
  try { cortes = await api.get(`/nomina?pais_id=${paisActual}`); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }

  if (!cortes.length) {
    return zona.replaceChildren(h("div", { clase: "tarjeta" },
      h("span", { clase: "gris" },
        t("nom_sin_cortes"))));
  }

  zona.replaceChildren(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("nom_cortes"), "ay_nom_cortes",
             { style: "margin:0 0 12px" }),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, t("nom_semana_del")), h("th", {}, t("nom_personas")),
        h("th", { style: "text-align:right" }, t("nom_total")),
        h("th", {}, t("nom_estado")), h("th", {}, ""))),
      h("tbody", {}, ...cortes.map(c => h("tr", {},
        h("td", {}, h("b", {}, fecha(c.fecha_corte))),
        h("td", {}, String(c.personas)),
        h("td", { clase: "num", style: "text-align:right" },
          dinero(c.total, c.moneda)),
        h("td", {}, etiqueta(estatus(c.estatus),
                             c.estatus === "pagada" ? "ok" : "alerta")),
        h("td", {},
          h("button", { clase: "claro chico", type: "button",
            onclick: () => { corteActual = c.id; pintarCorte(zonaCorte, c.id); } },
            t("nom_ver"))))))))); 
}

/* ------------------------------------------------------ el corte */

async function pintarCorte(zona, nominaId) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("nom_cargando")));
  let n;
  try { n = await api.get(`/nomina/${nominaId}`); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }

  const pagada = n.estatus === "pagada";
  const caja = h("div", { clase: "tarjeta" });

  caja.append(...[
    h("div", { style: "display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline" },
      h("div", {},
        h("h3", { style: "margin:0" },
           t("nom_semana_de").replace("{f}", fecha(n.fecha_corte))),
        h("div", { clase: "gris chico" },
          t("nom_resumen_corte")
            .replace("{p}", n.renglones.length)
            .replace("{d}", n.dias_pagados))),
      h("div", { style: "text-align:right" },
        h("div", { style: "font-size:22px;font-weight:650" },
          dinero(n.total, n.moneda)),
        etiqueta(estatus(n.estatus), pagada ? "ok" : "alerta"),
        pagada && n.pagada_en
          ? h("div", { clase: "gris chico" }, fecha(n.pagada_en)) : null))].filter(Boolean));

  /* Lo que se fue en cada rol. Es la cuenta que la direccion pide, y de
     un total plano no se saca. */
  if (n.por_rol.length) {
    caja.append(
      conAyuda("h4", t("nom_por_rol"), "ay_nom_por_rol",
               { clase: "grupo" }),
      h("div", { clase: "rejilla cuatro" },
        ...n.por_rol.map(r => h("div", {},
          h("div", { clase: "gris chico" }, r.rol),
          h("div", { style: "font-size:18px;font-weight:650" },
            dinero(r.monto, n.moneda)),
          h("div", { clase: "gris chico" },
            t("nom_dias_n").replace("{n}", r.dias))))));
  }

  caja.append(h("h4", { clase: "grupo" }, t("nom_por_persona")));
  for (const r of n.renglones) caja.append(renglonPersona(r, n));

  if (!pagada) {
    caja.append(h("div", { clase: "acciones", style: "margin-top:16px" },
      h("button", { type: "button", onclick: (e) => pagar(e, zona, n) },
        t("nom_marcar_pagado").replace("{m}", dinero(n.total, n.moneda))),
      h("span", { clase: "gris chico" }, t("nom_pagado_aviso"))));
  }

  zona.replaceChildren(caja, h("div", { style: "margin-top:14px" },
    ...[bloqueAjustes()]));
}

/* Cada persona con sus dias abiertos. El detalle importa: es el recibo
   que la persona va a reclamar si no le cuadra, y ahi tiene que decir
   con que rol se le pago cada dia. */
function renglonPersona(r, n) {
  const detalle = h("div", { hidden: true, style: "margin:8px 0 0 12px" },
    h("table", {},
      h("tbody", {}, ...r.conceptos.map(c => h("tr", {},
        h("td", {}, c.descripcion,
          c.es_ajuste ? h("span", {}, " ", etiqueta("ajuste", "alerta")) : null),
        h("td", { clase: "num", style: "text-align:right" },
          dinero(c.monto, n.moneda)))))));

  const abrir = h("button", { clase: "claro chico", type: "button",
    onclick: () => { detalle.hidden = !detalle.hidden; } }, t("nom_ver_dias"));

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 8px" },
    h("div", { style: "display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center" },
      h("div", {},
        h("b", {}, r.persona),
        h("div", { clase: "gris chico" }, `${r.dias} dia(s)`)),
      h("div", { clase: "acciones" },
        h("b", { clase: "num" }, dinero(r.total, n.moneda)),
        abrir)),
    detalle);
}

async function pagar(e, zona, n) {
  e.target.disabled = true;
  try {
    await api.post(`/nomina/${n.id}/pagar`, {});
    mensaje(t("nom_corte_pagado").replace("{f}", fecha(n.fecha_corte)));
    await pintarCorte(zona, n.id);
  } catch (err) {
    mensaje(err.message, "grave");
    e.target.disabled = false;
  }
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
  caja.append(lista_, formularioAjuste(() => cargar()));

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
        h("td", {}, etiqueta(a.sentido,
                             a.sentido === "descuento" ? "grave" : "ok")),
        h("td", { clase: "num", style: "text-align:right" },
          dinero(a.monto)))))));
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

/* ------------------------------------------------ el tabulador

   Lo que se le paga al personal por un dia de servicio. Dos tablas, una
   por tipo de operacion: un dia suelto que arranca en un aeropuerto y un
   dia de la misma persona en el mismo lugar no se pagan igual, y con un
   solo numero para las dos siempre se le paga mal a alguien.

   Va plegado: es configuracion, no el trabajo de todos los lunes. */

async function pintarTabulador(zona) {
  let datos;
  try { datos = await api.get(`/nomina/tabulador?pais_id=${paisActual}`); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }

  const cuerpo = h("div", { hidden: true, style: "margin-top:12px" });
  const faltan = datos.eventual.sin_cargar + datos.implantado.sin_cargar;
  const abrir = h("button", { clase: "claro chico", type: "button",
    onclick: () => { cuerpo.hidden = !cuerpo.hidden; } },
    t("nom_tabulador"));

  cuerpo.append(
    tablaComision(t("nom_eventuales"), datos, datos.eventual, "eventual"),
    tablaComision(t("nom_implantados"), datos, datos.implantado, "implantado"));

  zona.replaceChildren(h("div", { clase: "tarjeta" },
    h("div", { clase: "acciones" }, abrir,
      /* Un cruce sin monto no es un detalle de captura: es un dia que no
         se va a poder pagar, y el corte se detiene por el. */
      faltan
        ? etiqueta(t("nom_cruces_faltan").replace("{n}", faltan), "alerta")
        : etiqueta(t("nom_completo"), "ok")),
    cuerpo));
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
    onclick: (e) => mandar(e) }, `Guardar ${titulo.toLowerCase()}`);

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

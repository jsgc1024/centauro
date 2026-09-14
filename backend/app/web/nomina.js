/* Nomina del personal de seguridad.

   Aqui se paga el trabajo de la calle: los dias que cada quien cubrio y
   el rol con el que los cubrio. Es otra cosa que los gastos del
   servicio —viaticos y compras—, que viven en su propia pantalla.

   El corte corre por semana y por pais. Mientras no se pague se puede
   recalcular las veces que haga falta; una vez pagado ya no se toca, y
   lo que cambie despues viaja hacia adelante como ajuste. Eso no es una
   limitacion del sistema: es que el dinero ya salio. */
import { api } from "./api.js";
import { aviso, campo, dinero, entrada, etiqueta, fecha, h, lista,
         mensaje } from "./util.js";
import { catalogos } from "./catalogos.js";

let paisActual = null;
let corteActual = null;

export async function pantallaNomina(main) {
  const cat = await catalogos();

  main.append(
    h("h1", {}, "Nomina del personal de seguridad"),
    h("p", { clase: "sub" },
      "Comisiones por rol y dias de servicio. Los viaticos y las compras "
      + "van en Gastos del servicio."));

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
        campo("Pais", paises),
        h("div", { clase: "campo" },
          h("label", {}, " "),
          h("button", { clase: "chico", type: "button",
            onclick: (e) => calcular(e, zona, historial) },
            "Calcular el corte de esta semana")))),
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
  zona.replaceChildren(h("div", { clase: "gris chico" }, "Calculando…"));
  try {
    const r = await api.post("/nomina/calcular", { pais_id: paisActual });
    mensaje(`Corte armado: ${r.personas} persona(s)`);
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
    h("h3", { style: "margin:0 0 2px" }, "El corte no sale todavia"),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      err.message),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, "Persona"), h("th", {}, "Dia"),
        h("th", {}, "Modalidad"), h("th", {}, "Rol"), h("th", {}, "Tipo"))),
      h("tbody", {}, ...filas.map(f => h("tr", {},
        h("td", {}, h("b", {}, f.persona)),
        h("td", {}, fecha(f.fecha)),
        h("td", {}, f.modalidad),
        h("td", {}, f.rol || etiqueta("sin rol", "grave")),
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
        "Todavia no hay ningun corte de este pais.")));
  }

  zona.replaceChildren(h("div", { clase: "tarjeta" },
    h("h3", { style: "margin:0 0 12px" }, "Cortes"),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, "Semana del"), h("th", {}, "Personas"),
        h("th", { style: "text-align:right" }, "Total"),
        h("th", {}, "Estado"), h("th", {}, ""))),
      h("tbody", {}, ...cortes.map(c => h("tr", {},
        h("td", {}, h("b", {}, fecha(c.fecha_corte))),
        h("td", {}, String(c.personas)),
        h("td", { clase: "num", style: "text-align:right" },
          dinero(c.total, c.moneda)),
        h("td", {}, etiqueta(c.estatus,
                             c.estatus === "pagada" ? "ok" : "alerta")),
        h("td", {},
          h("button", { clase: "claro chico", type: "button",
            onclick: () => { corteActual = c.id; pintarCorte(zonaCorte, c.id); } },
            "Ver")))))))); 
}

/* ------------------------------------------------------ el corte */

async function pintarCorte(zona, nominaId) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, "Cargando…"));
  let n;
  try { n = await api.get(`/nomina/${nominaId}`); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }

  const pagada = n.estatus === "pagada";
  const caja = h("div", { clase: "tarjeta" });

  caja.append(
    h("div", { style: "display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline" },
      h("div", {},
        h("h3", { style: "margin:0" }, `Semana del ${fecha(n.fecha_corte)}`),
        h("div", { clase: "gris chico" },
          `${n.renglones.length} persona(s) · ${n.dias_pagados} dia(s) `
          + `pagados`)),
      h("div", { style: "text-align:right" },
        h("div", { style: "font-size:22px;font-weight:650" },
          dinero(n.total, n.moneda)),
        etiqueta(n.estatus, pagada ? "ok" : "alerta"),
        pagada && n.pagada_en
          ? h("div", { clase: "gris chico" }, fecha(n.pagada_en)) : null)));

  /* Lo que se fue en cada rol. Es la cuenta que la direccion pide, y de
     un total plano no se saca. */
  if (n.por_rol.length) {
    caja.append(
      h("h4", { clase: "grupo" }, "Por rol"),
      h("div", { clase: "rejilla cuatro" },
        ...n.por_rol.map(r => h("div", {},
          h("div", { clase: "gris chico" }, r.rol),
          h("div", { style: "font-size:18px;font-weight:650" },
            dinero(r.monto, n.moneda)),
          h("div", { clase: "gris chico" }, `${r.dias} dia(s)`)))));
  }

  caja.append(h("h4", { clase: "grupo" }, "Por persona"));
  for (const r of n.renglones) caja.append(renglonPersona(r, n));

  if (!pagada) {
    caja.append(h("div", { clase: "acciones", style: "margin-top:16px" },
      h("button", { type: "button", onclick: (e) => pagar(e, zona, n) },
        `Marcar pagado ${dinero(n.total, n.moneda)}`),
      h("span", { clase: "gris chico" },
        "Despues de esto el corte ya no se recalcula: lo que cambie "
        + "viaja como ajuste a la semana siguiente.")));
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
    onclick: () => { detalle.hidden = !detalle.hidden; } }, "Ver dias");

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
    mensaje(`Corte de la semana del ${fecha(n.fecha_corte)} marcado como pagado`);
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
    h("h3", { style: "margin:0 0 2px" }, "Ajustes pendientes"),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      "Entran en el proximo corte. En positivo se le debe; en negativo "
      + "se le descuenta."));
  const lista_ = h("div");
  caja.append(lista_, formularioAjuste(() => cargar()));

  async function cargar() {
    let filas = [];
    try {
      filas = await api.get(`/nomina/ajustes/pendientes?pais_id=${paisActual}`);
    } catch (err) { return lista_.replaceChildren(aviso(err.message, "grave")); }

    if (!filas.length) {
      return lista_.replaceChildren(h("div", { clase: "gris chico" },
        "Nada pendiente."));
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
    onclick: () => { form.hidden = !form.hidden; } }, "Registrar un ajuste");

  const quien = lista("persona_id", []);
  const monto = entrada("monto", { type: "number", step: "1",
                                   placeholder: "Positivo o negativo" });
  const motivo = entrada("motivo", { placeholder: "Por que" });
  const form = h("div", { hidden: true, style: "margin-top:12px" },
    h("div", { clase: "rejilla tres" },
      campo("Persona", quien), campo("Monto", monto), campo("Motivo", motivo)),
    h("div", { clase: "acciones" },
      h("button", { clase: "chico", type: "button",
        onclick: (e) => guardar(e) }, "Guardar el ajuste")));

  (async () => {
    const cat = await catalogos();
    quien.replaceChildren(...cat.personal.map(
      p => h("option", { value: p.id }, p.nombre)));
  })();

  async function guardar(e) {
    if (!quien.value || !monto.value || !motivo.value.trim()) {
      return mensaje("Falta la persona, el monto o el motivo", "alerta");
    }
    e.target.disabled = true;
    try {
      await api.post("/nomina/ajustes", {
        persona_id: Number(quien.value), pais_id: paisActual,
        monto: Number(monto.value), motivo: motivo.value.trim(),
      });
      mensaje("Ajuste registrado. Entra en el proximo corte.");
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
    "Tabulador de pagos");

  cuerpo.append(
    tablaComision("Eventuales", datos, datos.eventual, "eventual"),
    tablaComision("Implantados", datos, datos.implantado, "implantado"));

  zona.replaceChildren(h("div", { clase: "tarjeta" },
    h("div", { clase: "acciones" }, abrir,
      /* Un cruce sin monto no es un detalle de captura: es un dia que no
         se va a poder pagar, y el corte se detiene por el. */
      faltan
        ? etiqueta(`${faltan} cruces sin monto`, "alerta")
        : etiqueta("completo", "ok")),
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
        placeholder: "sin cargar",
      });
      /* La hora extra solo donde la modalidad la admite. Ofrecerla donde
         no aplica invita a capturar un numero que nunca se va a usar. */
      const extra = c.aplica_horas_extra
        ? entrada("he", {
            type: "number", step: "1", min: "0", clase: "num",
            style: "text-align:right; max-width:90px",
            value: c.monto_hora_extra !== null
              ? String(Math.round(Number(c.monto_hora_extra))) : "",
            placeholder: "h extra",
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
      mensaje(`Tabulador de ${titulo.toLowerCase()} guardado`);
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  }

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" },
    h("h4", { style: "margin:0 0 2px" }, titulo),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      `Por dia y por persona, en ${datos.moneda}. Abajo de cada monto, `
      + "lo que se paga por hora extra donde la modalidad la admite."),
    h("div", { style: "overflow-x:auto" },
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, "Rol"),
          /* Cada tabla trae sus propias modalidades: el implantado es
             siempre dia completo, y las columnas de medio dia y transfer
             ahi no significan nada. */
          ...tabla.modalidades.map(x => h("th", { style: "text-align:right" },
            x.codigo,
            h("div", { clase: "gris chico" }, `${x.horas} h`))))),
        cuerpoTabla)),
    h("div", { clase: "acciones", style: "margin-top:10px" }, guardar));
}

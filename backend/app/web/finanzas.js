/* Gastos del servicio.

   Aqui vive todo el dinero que sale por un servicio menos la nomina del
   personal de seguridad: los viaticos que se depositan y las compras que
   se gestionan. Las comisiones por rol y dias de servicio son otra
   pantalla y otro trabajo.

   Despachar no es controlar, y por eso son cuatro vistas:

     Por pagar     lo de hoy: quien espera su deposito y que hay que comprar
     Depositado    la memoria de lo que ya salio, con su referencia
     Por comprobar quien trae dinero de la empresa y desde cuando
     Devoluciones  lo que tiene que regresar

   Un deposito sale como un solo renglon por persona aunque sean cinco
   dias: confirmar cinco veces al mismo agente es como se paga dos veces
   la misma cosa. */
import { api } from "./api.js";
import { aviso, campo, dinero, entrada, etiqueta, fecha, h,
         mensaje } from "./util.js";
import { t } from "./idioma.js";

const TIPOS = { vuelo: t("fin_tipo_vuelo"), hospedaje: t("fin_tipo_hospedaje"),
                transporte: t("fin_tipo_transporte"), otro: t("fin_tipo_otro") };

const VISTAS = [
  { clave: "pagar", texto: t("fin_v_pagar") },
  { clave: "depositado", texto: t("fin_v_depositado") },
  { clave: "comprobar", texto: t("fin_v_comprobar") },
  { clave: "devoluciones", texto: t("fin_v_devoluciones") },
];

let vistaActual = "pagar";

export async function bandejaFinanzas(main) {
  main.append(
    h("h1", {}, t("fin_titulo")),
    h("p", { clase: "sub" },
      t("fin_sub")));

  const encabezado = h("div");
  const pestanas = h("div", { clase: "acciones", style: "margin:0 0 16px" });
  const zona = h("div");
  main.append(encabezado, pestanas, zona);

  function pintarPestanas() {
    pestanas.replaceChildren(...VISTAS.map(v => h("button", {
      type: "button",
      clase: v.clave === vistaActual ? "chico" : "claro chico",
      onclick: () => { vistaActual = v.clave; pintarPestanas(); pintar(zona); },
    }, v.texto)));
  }

  await pintarCorte(encabezado);
  pintarPestanas();
  await pintar(zona);
}

/* Los cuatro numeros de arriba. Comprometido es lo que ya se pidio y no
   ha salido; afuera es lo que salio y no se ha comprobado. Son dos cosas
   distintas y confundirlas es como se acaba el mes creyendo que se debe
   menos de lo que se debe. */
async function pintarCorte(zona) {
  let datos;
  try { datos = await api.get("/viaticos/finanzas/corte"); }
  catch { return; }
  if (!datos.paises.length) return;

  zona.replaceChildren(...datos.paises.map(p => h("div", {
    clase: "tarjeta", style: "margin-bottom:14px",
  },
    h("div", { clase: "cabeza-pais" },
      h("h2", { style: "margin:0" }, p.pais),
      h("span", { clase: "etiqueta" }, p.moneda || p.codigo)),
    h("div", { clase: "rejilla cuatro" },
      numero(t("fin_mes"), dinero(p.depositado_mes, p.moneda)),
      numero(t("fin_comprometido"), dinero(p.comprometido, p.moneda),
             t("fin_comprometido_pie")),
      numero(t("fin_afuera"), dinero(p.afuera, p.moneda),
             Number(p.vencido) > 0
               ? t("fin_vencido_pie").replace("{m}", dinero(p.vencido, p.moneda)) : null,
             Number(p.vencido) > 0),
      numero(t("fin_compras_abiertas"), String(p.compras_abiertas))))));
}

function numero(titulo, valor, nota = null, alarma = false) {
  return h("div", {},
    h("div", { clase: "gris chico" }, titulo),
    h("div", { style: "font-size:20px;font-weight:650" }, valor),
    nota ? h("div", { clase: alarma ? "chico grave" : "gris chico" },
              nota) : null);
}

async function pintar(zona) {
  if (vistaActual === "depositado") return pintarDepositado(zona);
  if (vistaActual === "comprobar") return pintarPorComprobar(zona);
  if (vistaActual === "devoluciones") return pintarDevoluciones(zona);
  return pintarPorPagar(zona);
}

async function pintarPorPagar(zona) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("fin_cargando")));
  let datos;
  try { datos = await api.get("/viaticos/finanzas/bandeja"); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }

  const repintar = () => pintarPorPagar(zona);
  if (!datos.paises.length) {
    return zona.replaceChildren(h("div", { clase: "tarjeta" },
      h("span", { clase: "gris" }, t("fin_nada"))));
  }

  /* Un apartado por pais. Cada pais lleva su propia caja, su propia
     moneda y su propia gente: juntar pesos y reales daba un total que no
     significaba nada y ponia a quien paga en Mexico a mirar depositos de
     Brasil que no le tocan. */
  zona.replaceChildren(...datos.paises.map(pais => h("section", {},
    h("div", { clase: "cabeza-pais" },
      h("h2", { style: "margin:0" }, pais.pais),
      h("span", { clase: "etiqueta" }, pais.moneda || pais.codigo),
      pais.depositos.length
        ? h("span", { clase: "gris chico" },
            t("fin_por_depositar").replace("{m}", dinero(pais.total_depositos, pais.moneda)))
        : ""),
    bloqueDepositos(pais.depositos, pais.moneda, repintar),
    bloqueCompras(pais.compras, repintar),
    bloqueRentas(pais.rentas, pais.moneda, repintar))));
}

/* ---------------------------------------------------------- depositos */

function bloqueDepositos(filas, moneda, repintar) {
  const caja = h("div", { clase: "tarjeta" },
    h("h3", { style: "margin:0 0 2px" }, t("fin_depositos").replace("{n}", filas.length)),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("fin_depositos_pie")));

  if (!filas.length) {
    caja.append(h("span", { clase: "gris" }, t("fin_nada")));
    return caja;
  }

  const cuerpo = h("tbody");
  for (const f of filas) cuerpo.append(
    renglonDeposito(f, f.moneda || moneda, repintar));
  caja.append(h("table", {},
    h("thead", {}, h("tr", {},
      h("th", {}, t("fin_persona")),
      h("th", {}, t("fin_servicio")),
      h("th", {}, t("fin_arranca")),
      h("th", { style: "text-align:right" }, t("fin_monto")),
      h("th", {}, t("fin_referencia")),
      h("th", {}, ""))),
    cuerpo));
  return caja;
}

function renglonDeposito(f, moneda, repintar) {
  /* La referencia es opcional pero se pide en el mismo renglon: pedirla
     en una segunda pantalla termina en depositos sin rastro. */
  const referencia = entrada("referencia", {
    placeholder: t("fin_folio_ref"), style: "max-width:180px" });

  const confirmar = h("button", { clase: "chico", type: "button",
    onclick: async (e) => {
      e.target.disabled = true;
      try {
        await api.post("/viaticos/finanzas/depositar", {
          equipo_id: f.equipo_id, persona_id: f.persona_id,
          referencia: referencia.value.trim() || null,
        });
        mensaje(t("fin_confirmado").replace("{p}", f.persona));
        await repintar();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, t("fin_confirmar"));

  return h("tr", {},
    h("td", {}, h("b", {}, f.persona),
      h("div", { clase: "chico gris" }, t("fin_dias").replace("{n}", f.dias))),
    h("td", {}, h("a", { href: `#/servicio/${f.servicio_id}` }, f.folio),
      h("div", { clase: "chico gris" },
        [f.cliente, t("fin_equipo").replace("{e}", f.equipo)].filter(Boolean).join(" · "))),
    h("td", {}, fecha(f.primera_jornada)),
    h("td", { style: "text-align:right" },
      h("b", { clase: "num" }, dinero(f.monto, moneda))),
    h("td", {}, referencia),
    h("td", {}, confirmar));
}

/* ------------------------------------------------------------ compras */

function bloqueCompras(compras, repintar) {
  const caja = h("div", { clase: "tarjeta" },
    h("h3", { style: "margin:0 0 2px" }, t("fin_compras").replace("{n}", compras.length)),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("fin_compras_pie")));

  if (!compras.length) {
    caja.append(h("span", { clase: "gris" }, t("fin_nada")));
    return caja;
  }
  for (const c of compras) caja.append(tarjetaCompra(c, repintar));
  return caja;
}

function tarjetaCompra(c, repintar) {
  const enGestion = c.estatus === "en_gestion";
  const zona = h("div");

  const tomar = h("button", { clase: "claro chico", type: "button",
    onclick: async (e) => {
      e.target.disabled = true;
      try {
        await api.post(`/viaticos/compras/${c.id}/tomar`);
        await repintar();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, t("fin_viendo"));

  const contestar = h("button", { clase: "chico", type: "button",
    onclick: () => {
      if (zona.firstChild) return zona.replaceChildren();
      zona.replaceChildren(formularioRespuesta(c, repintar));
    } }, t("fin_contestar"));

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 10px" },
    h("div", { clase: "acciones", style: "justify-content:space-between" },
      h("div", {},
        h("b", {}, TIPOS[c.tipo] || c.tipo),
        h("span", { clase: "gris chico" },
          ` · ${c.folio || ""} ${c.cliente ? "· " + c.cliente : ""} `
          + t("fin_equipo").replace("{e}", c.equipo))),
      etiqueta(enGestion ? t("fin_en_gestion") : t("fin_nueva"),
               enGestion ? "alerta" : "info")),
    h("div", { clase: "chico", style: "white-space:pre-wrap; margin-top:6px" },
      c.solicitud),
    c.monto_estimado
      ? h("div", { clase: "chico gris", style: "margin-top:4px" },
          t("fin_estimado").replace("{m}", dinero(c.monto_estimado, c.moneda)))
      : "",
    h("div", { clase: "acciones", style: "margin-top:8px" },
      enGestion ? "" : tomar, contestar),
    zona);
}

function formularioRespuesta(c, repintar) {
  const confirmacion = entrada("confirmacion", {
    placeholder: t("fin_reserva") });
  const montoReal = entrada("monto_real", {
    type: "number", step: "0.01", min: "0", placeholder: t("fin_costo") });
  const nota = h("textarea", { name: "respuesta", rows: "3",
    placeholder: t("fin_detalle_compra") });
  const archivo = h("input", { type: "file", accept: "image/*" });

  const zonaError = h("div");

  const enviar = h("button", { clase: "chico", type: "button",
    onclick: async (e) => {
      if (!confirmacion.value.trim() && !archivo.files.length) {
        return zonaError.replaceChildren(aviso(
          t("fin_falta_reserva"), "alerta"));
      }
      zonaError.replaceChildren();
      e.target.disabled = true;
      try {
        // La imagen primero: la confirmacion la exige si no hay folio.
        if (archivo.files.length) {
          await api.subir(`/viaticos/compras/${c.id}/comprobante`,
                          archivo.files[0], "archivo");
        }
        await api.post(`/viaticos/compras/${c.id}/confirmar`, {
          confirmacion: confirmacion.value.trim() || null,
          monto_real: montoReal.value ? Number(montoReal.value) : null,
          respuesta: nota.value.trim() || null,
        });
        mensaje(t("fin_compra_confirmada"));
        await repintar();
      } catch (err) {
        zonaError.replaceChildren(aviso(err.message, "grave"));
        e.target.disabled = false;
      }
    } }, t("fin_confirmar_compra"));

  const rechazar = h("button", { clase: "claro chico", type: "button",
    onclick: async (e) => {
      if (!nota.value.trim()) {
        return zonaError.replaceChildren(aviso(
          t("fin_diga_por_que"), "alerta"));
      }
      e.target.disabled = true;
      try {
        await api.post(`/viaticos/compras/${c.id}/rechazar`,
                       { respuesta: nota.value.trim() });
        await repintar();
      } catch (err) {
        zonaError.replaceChildren(aviso(err.message, "grave"));
        e.target.disabled = false;
      }
    } }, t("fin_no_se_puede"));

  return h("div", { clase: "tarjeta lisa", style: "margin-top:8px" },
    h("div", { clase: "rejilla dos" },
      campo(t("fin_num_reserva"), confirmacion),
      campo(t("fin_costo"), montoReal)),
    campo(t("fin_nota_equipo"), nota),
    campo(t("fin_imagen_compra"), archivo),
    zonaError,
    h("div", { clase: "acciones", style: "margin-top:8px" },
      enviar, rechazar));
}


/* --------------------------------------------------- rentas por cancelar */

/* Esto no es dinero por salir: es dinero que sigue saliendo. El servicio
   se borro o se cancelo, el auto ya no se usa, y mientras nadie le hable
   a la arrendadora se sigue cobrando todos los dias. Sale de la lista
   cuando alguien la cancelo, no cuando el servicio desaparecio. */

function bloqueRentas(rentas, moneda, repintar) {
  if (!rentas || !rentas.length) return "";

  const cuerpo = h("tbody");
  for (const r of rentas) cuerpo.append(h("tr", {},
    h("td", {}, h("span", { clase: "placas" }, r.placa),
      h("div", { clase: "chico gris" },
        [r.unidad, r.marca_modelo, r.color].filter(Boolean).join(" · "))),
    h("td", {}, h("b", {}, r.arrendadora || "—"),
      h("div", { clase: "chico num" }, r.telefono || t("fin_sin_telefono"))),
    h("td", {}, r.folio || "—",
      h("div", { clase: "chico gris" }, r.ciudad || "")),
    h("td", { style: "text-align:right" },
      h("span", { clase: "num" }, dinero(r.costo_diario, moneda)),
      h("div", { clase: "chico gris" }, t("fin_por_dia"))),
    h("td", {}, h("button", { clase: "chico", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          await api.post(`/viaticos/finanzas/rentas/${r.vehiculo_id}/cancelada`);
          mensaje(t("fin_renta_cancelada").replace("{p}", r.placa));
          await repintar();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, t("fin_ya_cancele")))));

  return h("div", { clase: "tarjeta" },
    h("h3", { style: "margin:0 0 2px" }, t("fin_rentas").replace("{n}", rentas.length)),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("fin_rentas_pie")),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, t("fin_unidad")),
        h("th", {}, t("fin_arrendadora")),
        h("th", {}, t("fin_servicio")),
        h("th", { style: "text-align:right" }, t("fin_renta")),
        h("th", {}, ""))),
      cuerpo));
}


/* ------------------------------------------------------ depositado

   La memoria de lo que ya salio. Hasta hoy, en cuanto finanzas
   confirmaba, el renglon desaparecia y la unica forma de saber si a
   alguien ya se le habia pagado era preguntarle. */

async function pintarDepositado(zona) {
  const persona = entrada("busca", { placeholder: t("fin_folio_servicio"),
                                     style: "max-width:220px" });
  const desde = h("input", { type: "date" });
  const hasta = h("input", { type: "date" });
  const lista = h("div");

  const buscar = async () => {
    lista.replaceChildren(h("div", { clase: "gris chico" }, t("fin_cargando")));
    const p = new URLSearchParams();
    if (desde.value) p.set("desde", desde.value);
    if (hasta.value) p.set("hasta", hasta.value);
    if (persona.value.trim()) p.set("folio", persona.value.trim());
    let datos;
    try { datos = await api.get(`/viaticos/finanzas/depositado?${p}`); }
    catch (err) { return lista.replaceChildren(aviso(err.message, "grave")); }

    if (!datos.paises.length) {
      return lista.replaceChildren(h("div", { clase: "vacio" },
        t("fin_sin_depositos")));
    }
    lista.replaceChildren(...datos.paises.map(p_ => h("section", {},
      h("div", { clase: "cabeza-pais" },
        h("h2", { style: "margin:0" }, p_.pais),
        h("span", { clase: "etiqueta" }, p_.moneda || p_.codigo),
        h("span", { clase: "gris chico" },
          t("fin_resumen_dep").replace("{n}", p_.cuantos).replace("{m}", dinero(p_.total, p_.moneda)))),
      h("div", { clase: "tarjeta" },
        h("table", {},
          h("thead", {}, h("tr", {},
            h("th", {}, t("fin_cuando")),
            h("th", {}, t("fin_persona")),
            h("th", {}, t("fin_servicio")),
            h("th", { style: "text-align:right" }, t("fin_monto")),
            h("th", {}, t("fin_referencia")),
            h("th", {}, t("fin_despacho")))),
          h("tbody", {}, ...p_.depositos.map(d => h("tr", {},
            h("td", {}, fecha(d.confirmada_en)),
            h("td", {}, h("b", {}, d.persona)),
            h("td", {},
              h("a", { href: rutaServicio(d) }, d.folio || "—"),
              h("div", { clase: "chico gris" }, d.cliente || "")),
            h("td", { style: "text-align:right" },
              h("b", { clase: "num" }, dinero(d.monto, d.moneda))),
            h("td", { clase: "chico" }, d.referencia_odoo || "—"),
            /* Los depositos de antes de que existiera la firma no
               tienen quien. Se dice, en vez de dejar un hueco que
               parece un error. */
            h("td", { clase: "chico gris" },
              d.confirmada_por || t("fin_sin_registro"))))))))));
  };

  zona.replaceChildren(
    h("div", { clase: "tarjeta lisa" },
      h("div", { clase: "rejilla cuatro" },
        campo(t("fin_desde"), desde), campo(t("fin_hasta"), hasta),
        campo(t("fin_servicio"), persona),
        h("div", { clase: "campo" },
          h("label", {}, "\u00a0"),
          h("button", { clase: "chico", type: "button",
            onclick: () => buscar() }, t("fin_buscar"))))),
    lista);
  await buscar();
}

function rutaServicio(f) {
  if (!f.servicio_id) return "#/panorama";
  return f.tipo === "implantado"
    ? `#/implantado/${f.servicio_id}`
    : `#/servicio/${f.servicio_id}`;
}

/* --------------------------------------------------- por comprobar

   Quien trae dinero de la empresa y desde cuando. Perseguir la
   comprobacion es trabajo de quien paga: el consultor valida que el
   gasto aplique al servicio, pero el que tiene que saber cuanto anda
   afuera es finanzas. */

async function pintarPorComprobar(zona) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("fin_cargando")));
  let datos;
  try { datos = await api.get("/viaticos/finanzas/por-comprobar"); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }

  if (!datos.paises.length) {
    return zona.replaceChildren(h("div", { clase: "tarjeta" },
      h("span", { clase: "gris" }, t("fin_sin_afuera"))));
  }

  zona.replaceChildren(...datos.paises.map(p => h("section", {},
    h("div", { clase: "cabeza-pais" },
      h("h2", { style: "margin:0" }, p.pais),
      h("span", { clase: "etiqueta" }, p.moneda || p.codigo),
      h("span", { clase: "gris chico" },
        t("fin_total_afuera").replace("{m}", dinero(p.total, p.moneda))),
      p.cuantos_vencidos
        ? h("span", { clase: "etiqueta grave" },
            t("fin_vencidos").replace("{n}", p.cuantos_vencidos).replace("{m}", dinero(p.vencido, p.moneda)))
        : null),
    h("div", { clase: "tarjeta" },
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, t("fin_persona")),
          h("th", {}, t("fin_servicio")),
          h("th", { style: "text-align:right" }, t("fin_entregado")),
          h("th", { style: "text-align:right" }, t("fin_comprobado")),
          h("th", { style: "text-align:right" }, t("fin_falta")),
          h("th", {}, t("fin_limite")))),
        h("tbody", {}, ...p.personas.map(x => h("tr", {},
          h("td", {}, h("b", {}, x.persona),
            x.sin_validar
              ? h("div", { clase: "chico ambar" },
                  t("fin_sin_validar").replace("{n}", x.sin_validar))
              : null),
          h("td", {},
            h("a", { href: rutaServicio(x) }, x.folio || "—"),
            h("div", { clase: "chico gris" },
              [x.cliente, fecha(x.fecha)].filter(Boolean).join(" · "))),
          h("td", { clase: "num", style: "text-align:right" },
            dinero(x.entregado, x.moneda)),
          h("td", { clase: "num", style: "text-align:right" },
            dinero(x.comprobado, x.moneda)),
          h("td", { clase: "num", style: "text-align:right" },
            h("b", {}, dinero(x.pendiente, x.moneda))),
          h("td", {},
            x.vencido
              ? etiqueta(t("fin_vencido_dias").replace("{n}", x.dias_vencido), "grave")
              : h("span", { clase: "chico gris" },
                  x.limite ? fecha(x.limite) : t("fin_sin_limite")))))))))));
}

/* ---------------------------------------------------- devoluciones

   Dos caminos que terminan en lo mismo: dinero de vuelta. El servicio
   que se cancelo con el deposito ya hecho, y el viatico que se cerro
   mandando a descuento lo que nadie comprobo. */

async function pintarDevoluciones(zona) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("fin_cargando")));
  let datos;
  try { datos = await api.get("/viaticos/finanzas/devoluciones"); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }

  if (!datos.paises.length) {
    return zona.replaceChildren(h("div", { clase: "tarjeta" },
      h("span", { clase: "gris" }, t("fin_nada_regresar"))));
  }

  zona.replaceChildren(...datos.paises.map(p => h("section", {},
    h("div", { clase: "cabeza-pais" },
      h("h2", { style: "margin:0" }, p.pais),
      h("span", { clase: "etiqueta" }, p.moneda || p.codigo)),

    p.devueltos.length
      ? h("div", { clase: "tarjeta" },
          h("h3", { style: "margin:0 0 2px" },
            t("fin_devuelto").replace("{n}", p.devueltos.length)),
          h("p", { clase: "gris chico", style: "margin:0 0 12px" },
            t("fin_total").replace("{m}", dinero(p.total_devuelto, p.moneda))),
          h("table", {},
            h("tbody", {}, ...p.devueltos.map(x => h("tr", {},
              h("td", {}, h("b", {}, x.persona)),
              h("td", {}, h("a", { href: rutaServicio(x) }, x.folio || "—")),
              h("td", { clase: "num", style: "text-align:right" },
                dinero(x.monto, x.moneda)),
              h("td", {}, etiqueta(x.estatus)))))))
      : null,

    p.descuentos.length
      ? h("div", { clase: "tarjeta" },
          h("h3", { style: "margin:0 0 2px" },
            t("fin_descuento").replace("{n}", p.descuentos.length)),
          /* Este dinero no vuelve como efectivo: se descuenta en
             nomina, que es otra pantalla. Aqui se ve para que finanzas
             no lo siga esperando en la caja. */
          h("p", { clase: "gris chico", style: "margin:0 0 12px" },
            t("fin_descuento_pie")
              .replace("{m}", dinero(p.total_descuento, p.moneda))),
          h("table", {},
            h("tbody", {}, ...p.descuentos.map(x => h("tr", {},
              h("td", {}, h("b", {}, x.persona),
                x.motivo
                  ? h("div", { clase: "chico gris" }, x.motivo) : null),
              h("td", {}, h("a", { href: rutaServicio(x) }, x.folio || "—")),
              h("td", { clase: "num", style: "text-align:right" },
                dinero(x.monto, x.moneda)),
              h("td", { clase: "chico gris" },
                x.cerrado_por ? t("fin_cerro").replace("{p}", x.cerrado_por) : ""))))))
      : null)));
}

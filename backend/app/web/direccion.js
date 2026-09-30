/* La ventana del director de operaciones (seccion 105).

   Salvador la pidio al resolver las incidencias (decision 2, 29 sep):
   una pantalla exclusiva donde le lleguen sus autorizaciones --las
   incidencias, el cobro al cancelar, los plazos vencidos-- y "algunos
   puntos de la operacion que puedan ser interesantes", que se definen
   mas adelante. Arriba lo que espera su firma; abajo las cuentas de
   hoy, por pais y con el reloj de cada pais.

   No es la Central ni el Panorama: aqui no se atiende nada minuto a
   minuto. Se firma, y se mira. Se repinta al actuar. */
import { api } from "./api.js";
import { aviso, conAyuda, dinero, etiqueta, fecha, h, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { nombreGravedad } from "./incidencias.js";

export async function pantallaDireccion(main) {
  main.append(
    h("h1", {}, t("dir_titulo")),
    h("p", { clase: "sub" }, t("dir_sub")));
  const zona = h("div");
  main.append(zona);
  await pintar(zona);
}

async function pintar(zona) {
  zona.replaceChildren(h("p", { clase: "gris" }, t("dir_cargando")));
  let d;
  try {
    d = await api.get("/direccion/bandeja");
  } catch (err) {
    return zona.replaceChildren(aviso(err.message, "grave"));
  }
  const recargar = () => pintar(zona);
  zona.replaceChildren(
    tarjetaIncidencias(d.incidencias_por_autorizar, recargar),
    tarjetaFreelance(d.freelance_por_autorizar || [], recargar),
    h("div", { clase: "rejilla dos" },
      tarjetaCobros(d.cobros_por_autorizar),
      tarjetaPlazos(d.plazos_vencidos)),
    tablero(d.hoy));
}

/* ---------------------------------------------------- las incidencias */

const TONO_GRAVEDAD = { error_menor: "", leve: "alerta", grave: "grave" };

function tarjetaIncidencias(filas, recargar) {
  return h("div", { clase: "tarjeta" },
    conAyuda("h3", t("dir_inc_titulo"), "ay_dir_bandeja"),
    h("p", { clase: "chico gris", style: "margin:0 0 12px" }, t("dir_inc_pie")),
    ...(filas.length
      ? filas.map(i => renglonIncidencia(i, recargar))
      : [h("div", { clase: "vacio" }, t("dir_inc_vacio"))]));
}

/* El mes del bono, como lo dice el aviso: "septiembre 2026". */
function nombreDelMes(r) {
  return `${t(`bon_mes_${r.mes}`)} ${r.anio}`;
}

function renglonIncidencia(i, recargar) {
  /* Lo que se escribe aqui queda en la bitacora del servicio, en el
     expediente de la persona y en el aviso a RRHH: es lo unico que
     explica, meses despues, por que ese mes se quedo sin bono o por
     que no. Va como area de texto, no como renglon. */
  const resolucion = h("textarea", { name: "resolucion", rows: "2",
                                     placeholder: t("dir_resolucion") });

  async function firmar(autorizar) {
    if (resolucion.value.trim().length < 10) {
      return mensaje(t("dir_falta_resolucion"), "alerta");
    }
    for (const b of botones) b.disabled = true;
    try {
      const r = await api.post(`/incidencias/${i.id}/visto-bueno`,
                               { autorizar, resolucion: resolucion.value.trim() });
      mensaje(t(r.clave).replace("{mes}", nombreDelMes(r))
                .replace("{motivo}", r.nota || ""),
              autorizar ? "alerta" : "ok");
      if (r.comisiones_retenidas && r.comisiones_retenidas.length) {
        mensaje(t("inc_vb_comision_retenida").replace(
          "{c}", r.comisiones_retenidas.map(c => c.consultor).join(", ")), "alerta");
      }
      if (r.aviso_rrhh) mensaje(t("inc_vb_aviso_rrhh"));
      recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      for (const b of botones) b.disabled = false;
    }
  }

  const botones = [
    h("button", { type: "button", onclick: () => firmar(true) }, t("dir_autorizar")),
    h("button", { clase: "claro", type: "button", onclick: () => firmar(false) },
      t("dir_descartar")),
  ];

  return h("div", { clase: "caso" },
    h("div", { clase: "cabeza_caso" },
      h("div", {},
        h("b", {}, i.persona), " ",
        etiqueta(nombreGravedad(i.gravedad), TONO_GRAVEDAD[i.gravedad] || ""),
        h("span", { clase: "chico gris" }, ` · ${fecha(i.fecha)}`),
        h("div", { clase: "chico gris" },
          i.ruta
            ? h("a", { clase: "enlace", href: i.ruta }, i.folio || `#${i.servicio_id}`)
            : "",
          i.cliente ? ` · ${i.cliente}` : "")),
      etiqueta(t("inc_estado_pendiente"), "alerta")),
    h("p", { style: "margin:8px 0 4px" }, i.descripcion),
    h("div", { clase: "chico gris", style: "margin:0 0 8px" },
      t("dir_inc_registro").replace("{q}", i.registrada_por || "—")
        .replace("{f}", i.creada_en ? fecha(i.creada_en.slice(0, 10)) : "—")),
    resolucion,
    h("div", { clase: "acciones", style: "margin-top:8px" }, ...botones));
}

/* ------------------------------------ el freelance por urgencia (111)

   Un freelance con el expediente incompleto que alguien quiere mandar a
   un servicio (decision 4 de Salvador): vale solo para ese servicio y
   queda escrito quien lo autorizo y por que. */
function tarjetaFreelance(filas, recargar) {
  return h("div", { clase: "tarjeta" },
    h("h3", {}, t("dir_fre_titulo")),
    h("p", { clase: "chico gris", style: "margin:0 0 12px" }, t("dir_fre_pie")),
    ...(filas.length
      ? filas.map(u => renglonFreelance(u, recargar))
      : [h("div", { clase: "vacio" }, t("dir_fre_vacio"))]));
}

function renglonFreelance(u, recargar) {
  const respuesta = h("input", { name: "respuesta_urgencia",
                                 placeholder: t("dir_fre_respuesta") });
  const resolver = async (si) => {
    if (!si && respuesta.value.trim().length < 5) {
      return mensaje(t("dir_fre_falta_respuesta"), "alerta");
    }
    for (const b of botones) b.disabled = true;
    try {
      await api.post(`/freelance/urgencias/${u.id}/${si ? "autorizar" : "rechazar"}`,
                     { respuesta: respuesta.value.trim() || null });
      mensaje(t(si ? "dir_fre_autorizada" : "dir_fre_rechazada"), si ? "ok" : "alerta");
      recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      for (const b of botones) b.disabled = false;
    }
  };
  const botones = [
    h("button", { type: "button", onclick: () => resolver(true) }, t("dir_autorizar")),
    h("button", { clase: "claro", type: "button", onclick: () => resolver(false) },
      t("dir_fre_no_autorizar")),
  ];
  return h("div", { clase: "caso" },
    h("div", { clase: "cabeza_caso" },
      h("div", {},
        h("a", { clase: "enlace", href: `#/freelance/${u.persona_id}` }, h("b", {}, u.persona)),
        h("span", { clase: "chico gris" }, " · "),
        h("a", { clase: "enlace", href: u.ruta }, u.folio || `#${u.servicio_id}`),
        u.cliente ? h("span", { clase: "chico gris" }, ` · ${u.cliente}`) : "",
        h("div", { clase: "chico gris" },
          t("dir_fre_pidio").replace("{q}", u.pidio || "—")
            .replace("{f}", u.pedida_en ? fecha(u.pedida_en.slice(0, 10)) : "—"))),
      etiqueta(t("inc_estado_pendiente"), "alerta")),
    h("p", { style: "margin:8px 0 4px" }, u.motivo),
    h("div", { clase: "chico", style: "margin:0 0 8px;color:var(--grave)" },
      t("dir_fre_le_falta").replace("{x}", u.faltaba || "—")),
    respuesta,
    h("div", { clase: "acciones", style: "margin-top:8px" }, ...botones));
}

/* ---------------------------------------------- el cobro al cancelar */

/* Las cancelaciones que esperan que operaciones diga como se cobran
   (decision 1 de Salvador): lo que pidio el consultor, lo que vale cada
   opcion y «Abrir», que lleva a la tarjeta del cierre, donde esta el
   boton «Autorizar el cobro». */
function tarjetaCobros(filas) {
  return h("div", { clase: "tarjeta" },
    h("h3", {}, t("dir_cobros_titulo")),
    h("p", { clase: "chico gris", style: "margin:0 0 12px" }, t("dir_cobros_pie")),
    ...(filas.length
      ? filas.map(c => h("div", { clase: "caso" },
          h("div", { clase: "cabeza_caso" },
            h("div", {},
              h("b", {}, c.folio || `#${c.servicio_id}`),
              c.cliente ? h("span", { clase: "chico gris" }, ` · ${c.cliente}`) : "",
              h("div", { clase: "chico gris" },
                (c.consultor || t("dir_sin_consultor"))
                + (c.cancelado_en
                    ? ` · ${t("dir_cobro_cancelado").replace("{f}", fecha(c.cancelado_en.slice(0, 10)))}`
                    : "")),
              h("div", { clase: "chico" },
                etiqueta(t("dir_cobro_pidio").replace("{c}",
                  t(c.cobro === "completo" ? "cie_cobro_completo" : "cie_cobro_ejecutado")),
                  "alerta"),
                " ",
                h("span", { clase: "gris" },
                  t("dir_cobro_montos")
                    .replace("{a}", dinero(c.total_cotizado, c.moneda))
                    .replace("{b}", dinero(c.total_ejecutado, c.moneda))))),
            c.ruta
              ? h("a", { clase: "enlace", href: c.ruta }, t("dir_abrir"))
              : "")))
      : [h("div", { clase: "vacio" }, t("dir_cobros_vacio"))]));
}

/* ------------------------------------------------ los plazos vencidos */

function haceCuanto(minutos) {
  if (minutos >= 1440) return t("dir_dias").replace("{d}", Math.floor(minutos / 1440));
  if (minutos >= 60) return t("dir_horas").replace("{h}", Math.floor(minutos / 60));
  return t("dir_minutos").replace("{m}", Math.max(1, minutos));
}

function tarjetaPlazos(filas) {
  return h("div", { clase: "tarjeta" },
    h("h3", {}, t("dir_plazos_titulo")),
    h("p", { clase: "chico gris", style: "margin:0 0 12px" }, t("dir_plazos_pie")),
    ...(filas.length
      ? filas.map(p => h("div", { clase: "caso" },
          h("div", { clase: "cabeza_caso" },
            h("div", {},
              h("b", {}, p.folio || `#${p.servicio_id}`),
              p.periodo ? h("span", { clase: "chico gris" }, ` · ${p.periodo}`) : "",
              h("div", { clase: "chico gris" },
                (p.consultor || t("dir_sin_consultor"))
                + " · " + t(p.regresado ? "dir_reloj_regreso" : "dir_reloj_consultor")),
              h("div", { clase: "chico" },
                h("span", { clase: "marca grave" },
                  t("dir_vencio_hace").replace("{t}", haceCuanto(p.minutos_vencido))))),
            p.ruta
              ? h("a", { clase: "enlace", href: p.ruta }, t("dir_abrir"))
              : "")))
      : [h("div", { clase: "vacio" }, t("dir_plazos_vacio"))]));
}

/* ----------------------------------------------------------- el tablero */

function tablero(paises) {
  return h("div", { clase: "tarjeta lisa" },
    conAyuda("h3", t("dir_hoy_titulo"), "ay_dir_hoy"),
    h("p", { clase: "chico gris", style: "margin:0 0 12px" }, t("dir_hoy_pie")),
    ...paises.map(bloquePais));
}

function bloquePais(p) {
  const inc = p.incidencias_mes;
  return h("div", { style: "margin:0 0 18px" },
    h("h4", { style: "margin:0 0 6px" },
      `${p.pais} · ${fecha(p.hoy)}`,
      h("span", { clase: "chico gris" },
        ` · ${t("dir_hora_local").replace("{h}", (p.ahora || "").slice(11, 16))}`)),
    h("div", { clase: "corte" },
      cifra(p.servicios_hoy, "dir_servicios_hoy"),
      cifra(p.servicios_manana, "dir_servicios_manana"),
      cifra(p.en_curso, "dir_en_curso"),
      cifra(p.alertas_abiertas, "dir_alertas", p.alertas_abiertas.n ? "rojo" : ""),
      cifra(p.cambios_en_curso, "dir_cambios")),
    h("div", { clase: "chico", style: "margin:8px 0 0" },
      h("b", {}, t("dir_inc_mes").replace("{p}", inc.periodo)), " ",
      ...["error_menor", "leve", "grave"].flatMap(g => [
        cuenta(inc[g], nombreGravedad(g)), " · "]),
      h("span", { clase: inc.pendientes ? "marca alerta" : "gris" },
        t("dir_inc_pendientes").replace("{n}", inc.pendientes)),
      " · ",
      h("span", { clase: "gris" },
        t("dir_inc_descartadas").replace("{n}", inc.descartadas))));
}

/* Un numero con la lista detras: se abre con un clic y se cierra con
   otro. Una cifra que no se puede abrir no se puede cuestionar. */
function cifra(x, clave, tono = "") {
  const lista = listaDe(x);
  const boton = h("button", { clase: "chico claro", type: "button",
    hidden: !x.n,
    onclick: () => {
      lista.hidden = !lista.hidden;
      boton.textContent = lista.hidden ? t("dir_ver_cuales") : t("dir_ocultar");
    } }, t("dir_ver_cuales"));
  return h("div", {},
    h("div", { clase: `cifra ${tono}` }, String(x.n)),
    h("div", { clase: "chico gris" }, t(clave)),
    boton, lista);
}

function cuenta(x, nombre) {
  const lista = listaDe(x);
  const enlace = h("a", { href: "#", onclick: (e) => {
    e.preventDefault();
    lista.hidden = !lista.hidden;
  } }, `${x.n} ${nombre}`);
  return h("span", {}, x.n ? enlace : `${x.n} ${nombre}`, lista);
}

function listaDe(x) {
  return h("div", { clase: "chico", hidden: true, style: "margin-top:4px" },
    ...(x.lista.length
      ? x.lista.map(s => h("div", {},
          h("a", { href: s.ruta }, s.folio || `#${s.servicio_id}`),
          s.cliente ? h("span", { clase: "gris" }, ` · ${s.cliente}`) : ""))
      : [h("span", { clase: "gris" }, t("dir_lista_vacia"))]));
}

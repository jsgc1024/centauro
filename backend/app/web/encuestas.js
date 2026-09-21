/* Lo que dijo el cliente.

   Dos encuestas cortas al cierre: al ejecutivo se le pregunta por el
   servicio, al solicitante por su consultor. Una calificacion de 3 o
   menos NO castiga sola --abre una revision, y clasificarla es de quien
   llevo el servicio--, igual que una incidencia.

   Esta pantalla existe porque el motor llevaba meses escrito y nadie
   podia verlo: la mala calificacion llegaba, abria revision, y se
   quedaba esperando a alguien que no sabia que existia. */
import { api } from "./api.js";
import { aviso, conAyuda, entrada, fecha, h, mensaje } from "./util.js";
import { t } from "./idioma.js";

export async function pantallaEncuestas(main) {
  main.append(
    h("h1", {}, t("enc_titulo")),
    h("p", { clase: "sub" }, t("enc_sub")));

  const zona = h("div");
  main.append(zona);
  await pintar(zona);
}

async function pintar(zona) {
  zona.replaceChildren(h("p", { clase: "gris" }, t("enc_cargando")));
  let resumen, pendientes;
  try {
    [resumen, pendientes] = await Promise.all([
      api.get("/encuestas/resumen"),
      api.get("/encuestas/por-clasificar"),
    ]);
  } catch (err) {
    return zona.replaceChildren(aviso(err.message, "grave"));
  }

  const recargar = () => pintar(zona);
  zona.replaceChildren(
    corte(resumen),
    bandeja(pendientes, recargar),
    ultimas(resumen));
}

/* ------------------------------------------------------------- el corte */

function cifra(valor, clave, tono = "") {
  return h("div", {},
    h("div", { clase: `cifra ${tono}` }, String(valor)),
    h("div", { clase: "chico gris" }, t(clave)));
}

function corte(r) {
  return h("div", { clase: "corte" },
    cifra(r.enviadas, "enc_enviadas"),
    cifra(r.respondidas, "enc_respondidas"),
    cifra(`${r.tasa_pct}%`, "enc_tasa"),
    cifra(r.promedio === null ? "—" : r.promedio, "enc_promedio"),
    cifra(r.esperando, "enc_esperando"),
    cifra(r.por_revisar, "enc_por_revisar", r.por_revisar ? "rojo" : ""));
}

/* --------------------------------------------------------- lo que dijeron */

function loQueDijo(e) {
  /* Las respuestas con su pregunta al lado. Un "3" suelto no se puede
     leer, y un comentario sin la pregunta que lo provoco tampoco. */
  if (!e.respuestas.length) return null;
  return h("div", { clase: "dichos" },
    ...e.respuestas.map(r => h("div", { clase: "dicho" },
      h("span", { clase: "chico gris" }, r.pregunta),
      h("span", {}, r.texto || String(r.valor)))));
}

function nota(e) {
  const n = e.calificacion || 0;
  return h("span", { clase: "nota_encuesta n" + n }, `${n} / 5`);
}

/* ------------------------------------------------------------ la bandeja */

function bandeja(filas, recargar) {
  const cuerpo = filas.length
    ? [h("p", { clase: "chico gris", style: "margin:0 0 12px" },
        t("enc_por_revisar_pie")),
       ...filas.map(e => renglon(e, recargar))]
    : [h("div", { clase: "vacio" }, t("enc_nada_por_revisar"))];

  return h("div", { clase: "tarjeta" },
    conAyuda("h3", t("enc_por_revisar_titulo"), "encuestas_revisar"),
    ...cuerpo);
}

function renglon(e, recargar) {
  /* Lo que se escribe aqui queda en la bitacora del servicio y es lo
     unico que explica, tres meses despues, por que esa queja no costo
     nada o por que si. Una linea no alcanza: va como area de texto. */
  const texto = h("textarea", { name: "nota", rows: "3",
                                placeholder: t("enc_que_paso") });
  const incidencia = entrada("incidencia", {
    type: "number", placeholder: t("enc_incidencia_id"),
    style: "max-width:150px" });

  const formulario = h("div", { hidden: true, clase: "marco_revision" },
    h("p", { clase: "chico gris", style: "margin:0 0 8px" },
      t("enc_clasificar_pie")),
    texto,
    h("div", { clase: "acciones" },
      incidencia,
      h("button", { type: "button", onclick: async () => {
        if (texto.value.trim().length < 10) {
          return mensaje(t("enc_falta_nota"), "alerta");
        }
        try {
          const r = await api.post(`/encuestas/${e.id}/clasificar`, {
            nota: texto.value.trim(),
            incidencia_id: incidencia.value ? Number(incidencia.value) : null,
          });
          mensaje(r.nota);
          recargar();
        } catch (err) { mensaje(err.message, "grave"); }
      } }, t("enc_guardar_revision"))));

  return h("div", { clase: "caso" },
    h("div", { clase: "cabeza_caso" },
      h("div", {},
        h("b", {}, e.folio || `#${e.servicio_id}`),
        h("span", { clase: "chico gris" }, ` · ${e.cliente || ""}`),
        h("div", { clase: "chico gris" },
          `${t(`enc_tipo_${e.tipo}`)} · ${e.para || ""}`
          + (e.respondida_en ? ` · ${fecha(e.respondida_en)}` : ""))),
      nota(e)),
    loQueDijo(e),
    h("div", { clase: "acciones" },
      h("button", { clase: "chico", type: "button",
        onclick: () => { formulario.hidden = !formulario.hidden; } },
        t("enc_clasificar")),
      h("a", { clase: "enlace", href: `#/servicio/${e.servicio_id}` },
        t("enc_ver_servicio"))),
    formulario);
}

/* -------------------------------------------------------- las contestadas */

function ultimas(r) {
  if (!r.ultimas.length) {
    return h("div", { clase: "tarjeta lisa" },
      h("h3", {}, t("enc_ultimas")),
      h("div", { clase: "vacio" }, t("enc_sin_respuestas")));
  }
  return h("div", { clase: "tarjeta lisa" },
    h("h3", {}, t("enc_ultimas")),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, t("enc_servicio")),
        h("th", {}, t("enc_tipo")),
        h("th", {}, t("enc_quien")),
        h("th", {}, t("enc_nota")),
        h("th", {}, t("enc_cuando")),
        h("th", {}, t("enc_estado")))),
      h("tbody", {}, ...r.ultimas.map(e => h("tr", {},
        h("td", {}, h("a", { href: `#/servicio/${e.servicio_id}` },
                      e.folio || `#${e.servicio_id}`),
          h("div", { clase: "chico gris" }, e.cliente || "")),
        h("td", { clase: "chico" }, t(`enc_tipo_${e.tipo}`)),
        h("td", { clase: "chico" }, e.para || ""),
        h("td", {}, nota(e)),
        h("td", { clase: "chico gris" },
          e.respondida_en ? fecha(e.respondida_en) : "—"),
        h("td", { clase: "chico" },
          !e.requiere_clasificacion ? h("span", { clase: "gris" }, "—")
          : e.clasificada ? h("span", { clase: "marca ok" }, t("enc_revisada"))
          : h("span", { clase: "marca grave" }, t("enc_pendiente"))))))));
}

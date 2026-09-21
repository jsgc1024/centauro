/* El personal de seguridad.

   Dos niveles: la lista, para decidir a quien mando; y la ficha, que
   explica el numero. Antes solo existia la lista, con cuatro columnas y
   una calificacion que no se podia discutir.

   Una distincion que esta pantalla no puede borrar: **la calificacion
   sirve para asignar, el bono es dinero**. Van juntas aqui porque quien
   arma un equipo quiere ver las dos, y por eso hay que decirlo: una
   calificacion baja del cliente no baja el pago de nadie, abre una
   revision. */
import { api, sesion } from "./api.js";
import { aviso, buscador, campo, coincide, conAyuda, dinero, etiqueta,
         fecha, h, lista, mensaje } from "./util.js";
import { t } from "./idioma.js";

let paisActual = null;
let soloPorVencer = false;
let busqueda = "";

/* La ultima lista que trajo la red. El buscador filtra sobre esto y no
   vuelve a pedirla: una consulta por cada letra que se escribe es lo
   que hace que un buscador se sienta trabado, y esta lista calcula
   cinco dimensiones por persona. */
let ultimas = [];

export async function pantallaPersonal(main) {
  const paises = await api.get("/catalogos/paises");
  if (!paises.length) {
    return main.append(h("h1", {}, t("personal_titulo")),
                       aviso(t("personal_sin_paises"), "alerta"));
  }

  const suyo = paises.find(p => p.id === (sesion.usuario || {}).pais_id);
  paisActual = paisActual || (suyo || paises[0]).id;

  const selector = lista("pais", paises.map(
    p => ({ valor: p.id, texto: p.nombre })));
  selector.value = paisActual;

  const casilla = h("input", { type: "checkbox", id: "solo_por_vencer" });
  casilla.checked = soloPorVencer;

  const zona = h("div");
  const recargar = () => pintar(zona);

  const caja = buscador(t("bus_ayuda_persona"), (texto) => {
    busqueda = texto;
    dibujar(zona);
  });
  caja.value = busqueda;

  selector.addEventListener("change", () => {
    paisActual = Number(selector.value);
    recargar();
  });
  casilla.addEventListener("change", () => {
    soloPorVencer = casilla.checked;
    recargar();
  });

  main.append(
    h("h1", {}, t("personal_titulo")),
    h("p", { clase: "sub" }, t("personal_sub")),
    h("div", { clase: "tarjeta lisa" },
      h("div", { clase: "rejilla tres" },
        campo(t("pais"), selector),
        campo(t("bus_buscar"), caja),
        h("div", { clase: "campo" },
          h("label", { for: "solo_por_vencer" }, " "),
          h("label", { clase: "casilla", for: "solo_por_vencer" },
            casilla, " ", t("per_solo_por_vencer"))))),
    zona);

  await pintar(zona);
}

/* ------------------------------------------------------------- la lista */

const TONO_CAPACITACION = {
  al_corriente: "ok", por_vencer: "alerta", vencido: "grave",
  sin_registro: "",
};

async function pintar(zona) {
  zona.replaceChildren(h("p", { clase: "gris" }, t("per_cargando")));
  try {
    ultimas = await api.get(`/profesionalismo?pais_id=${paisActual}`);
  } catch (err) {
    ultimas = [];
    return zona.replaceChildren(aviso(err.message, "grave"));
  }
  dibujar(zona);
}

function dibujar(zona) {
  let filas = ultimas;
  if (soloPorVencer) {
    filas = filas.filter(f => ["por_vencer", "vencido"]
      .includes(f.capacitacion.estado));
  }
  /* Por nombre, por plaza o por el correo con el que entra: se busca
     con lo que uno tiene a la mano, que no siempre es el nombre
     completo. */
  const q = busqueda.trim();
  if (q) {
    filas = filas.filter(f => coincide(q, f.persona, f.plaza,
                                       (f.usuario || {}).correo));
  }
  if (!filas.length) {
    /* Una tabla vacia sin explicacion manda a buscar el error donde no
       esta. Y la razon no es la misma con el filtro puesto que sin el. */
    return zona.replaceChildren(aviso(
      q ? t("bus_nada").replace("{q}", q)
        : soloPorVencer ? t("per_nada_por_vencer") : t("personal_vacio"),
      (q || soloPorVencer) ? "" : "alerta"));
  }

  const cuerpo = h("tbody");
  for (const f of filas) cuerpo.append(renglon(f, zona));

  zona.replaceChildren(
    h("div", { clase: "tarjeta lisa" },
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, t("col_persona")),
          h("th", {}, t("col_calificacion")),
          h("th", {}, t("per_cliente")),
          h("th", {}, t("per_bono")),
          h("th", {}, t("per_capacitacion")),
          h("th", {}, t("per_incidencias")),
          h("th", {}, t("col_experiencia")))),
        cuerpo)));
}

function barra(valor) {
  const ancho = Math.max(0, Math.min(100, Number(valor) || 0));
  return h("span", { clase: "barrita" },
    h("i", { style: `width:${ancho}%` + (ancho < 50 ? ";background:var(--grave)" : "") }));
}

function estrellas(ganadas, posibles) {
  const total = Math.max(posibles || 0, ganadas || 0);
  return h("span", { clase: "estrellas" },
    "★".repeat(ganadas || 0),
    h("span", { clase: "apagada" },
      "★".repeat(Math.max(0, total - (ganadas || 0)))));
}

/* Con que correo entra al sistema, debajo del nombre.

   La pregunta se hace mirando esta pantalla --"y este, ya puede abrir
   la app?"-- y antes habia que salir a Accesos a buscar a la misma
   persona otra vez. La contrasena no aparece aqui ni puede aparecer en
   ningun lado: el sistema guarda un hash, no la contrasena. Lo que si
   se puede decir es quien todavia no ha puesto la suya, que es
   exactamente el que no ha podido entrar. */

function usuarioDe(f) {
  const u = f.usuario;
  if (!u) return h("div", { clase: "gris chico" }, t("per_sin_usuario"));
  const nota = !u.activo ? t("per_usuario_inactivo")
             : !u.ya_puso_contrasena ? t("per_usuario_sin_contrasena")
             : "";
  return h("div", { clase: "gris chico" },
    u.correo + (nota ? ` · ${nota}` : ""));
}

function renglon(f, zona) {
  const cap = f.capacitacion || {};
  return h("tr", {},
    h("td", {},
      h("a", { href: "#", onclick: (e) => {
        e.preventDefault(); abrirFicha(zona, f);
      } }, h("b", {}, f.persona)),
      h("div", { clase: "gris chico" },
        f.plaza + (f.es_freelance ? ` · ${t("per_freelance")}` : "")),
      usuarioDe(f)),

    h("td", {},
      h("div", { clase: "calif" },
        h("b", {}, String(f.calificacion)), barra(f.calificacion)),
      /* "Confianza baja" se leia como desconfianza de la persona. Lo que
         dice es que al sistema le faltan datos sobre ella. */
      h("div", { clase: "medido" },
        t("per_medido_con").replace("{n}", f.medido_con)
                           .replace("{total}", f.dimensiones_totales))),

    h("td", {}, f.satisfaccion
      ? h("div", {},
          estrellas(Math.round(f.satisfaccion.promedio), 5),
          h("div", { clase: "gris chico" },
            `${f.satisfaccion.promedio} · ${t("per_del_equipo")}`))
      : h("span", { clase: "gris chico" }, t("per_sin_calificar"))),

    h("td", {}, f.bono
      ? h("div", {},
          f.bono.anulado
            ? etiqueta(t("per_mes_anulado"), "grave")
            : estrellas(f.bono.estrellas, f.bono.posibles),
          h("div", { clase: "gris chico num" },
            dinero(f.bono.monto, f.bono.moneda)))
      : h("span", { clase: "gris chico" }, t("per_sin_bono"))),

    h("td", {},
      etiqueta(t(`per_cap_${cap.estado}`), TONO_CAPACITACION[cap.estado] || ""),
      cap.curso
        ? h("div", { clase: "gris chico" },
            cap.estado === "vencido"
              ? `${cap.curso} · ${fecha(cap.fecha)}`
              : t("per_vence_en").replace("{n}", cap.dias)
                  .replace("{curso}", cap.curso))
        : null),

    h("td", { clase: "chico gris" }, f.incidencias || "—"),
    h("td", { clase: "num" }, `${f.horas_en_centauro.toLocaleString()} h`));
}

/* -------------------------------------------------------------- la ficha */

async function abrirFicha(zona, fila) {
  zona.replaceChildren(h("p", { clase: "gris" }, t("per_cargando")));
  let f, exp;
  try {
    [f, exp] = await Promise.all([
      api.get(`/profesionalismo/persona/${fila.persona_id}`),
      api.get(`/profesionalismo/persona/${fila.persona_id}/expediente`),
    ]);
  } catch (err) {
    mensaje(err.message, "grave");
    return pintar(zona);
  }

  zona.replaceChildren(
    h("div", { clase: "tarjeta" },
      h("div", { clase: "cabeza_ficha" },
        h("div", {},
          h("h3", { style: "margin:0" }, f.persona),
          usuarioDe(f),
          h("div", { clase: "gris chico" },
            [f.plaza,
             `${f.horas_en_centauro.toLocaleString()} h`,
             t("per_ventana").replace("{n}", f.ventana_meses)].join(" · "))),
        h("div", { style: "text-align:right" },
          h("div", { clase: "calificacion_grande" }, String(f.calificacion)),
          h("div", { clase: "gris chico" },
            t("per_medido_con")
              .replace("{n}", f.dimensiones.length - f.sin_datos_para_medir.length)
              .replace("{total}", f.dimensiones.length)))),

      h("h4", {}, t("per_de_donde_sale")),
      ...f.dimensiones.map(dimension),

      aviso(t("per_no_es_el_bono"), "alerta"),
      h("div", { clase: "acciones" },
        h("button", { clase: "claro", type: "button",
          onclick: () => pintar(zona) }, t("per_volver")))),

    bloqueBonos(exp),
    bloqueClientes(exp),
    bloqueCertificados(exp));
}

function dimension(d) {
  const cumple = d.aplica && d.valor >= 70;
  return h("div", { clase: "dim" },
    h("div", { clase: "pesa" },
      h("div", { clase: "n" }, `${d.peso_base}%`),
      h("div", { clase: "b" },
        h("i", { style: `width:${Math.max(0, Math.min(100, d.valor || 0))}%`
                        + (d.aplica && !cumple ? ";background:var(--grave)" : "") }))),
    h("div", { clase: "cuerpo" },
      h("div", { clase: "nombre" }, t(`prof_${d.dimension}`)),
      /* La frase que explica. Es lo que convierte un 87.4 en algo que se
         puede discutir, y ya la escribia el motor. */
      h("div", { clase: "gris chico" }, d.detalle || "")),
    h("div", { clase: "aporte" },
      d.aplica ? String(d.aporte) : "—",
      h("span", { clase: "de" },
        d.aplica ? t("per_de_n").replace("{n}", d.peso_base)
                 : t("per_no_aplica"))));
}

function bloqueBonos(exp) {
  if (!exp.bonos || !exp.bonos.length) return h("div", {});
  return h("div", { clase: "tarjeta lisa" },
    h("h3", {}, t("per_bonos_titulo")),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, t("per_mes")), h("th", {}, t("bon_estrellas")),
        h("th", {}, t("per_bono")), h("th", {}, t("bon_estado")))),
      h("tbody", {}, ...exp.bonos.map(b => h("tr", {},
        h("td", {}, b.periodo),
        h("td", {}, b.anulado
          ? etiqueta(t("per_mes_anulado"), "grave")
          : estrellas(b.estrellas, b.posibles)),
        h("td", { clase: "num" }, dinero(b.monto, b.moneda)),
        h("td", {}, etiqueta(t(`bon_est_${b.estatus}`),
                             b.estatus === "pagada" ? "ok" : "")))))));
}

function bloqueClientes(exp) {
  if (!exp.clientes || !exp.clientes.length) return h("div", {});
  return h("div", { clase: "tarjeta lisa" },
    h("h3", {}, t("per_clientes_titulo")),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, t("enc_servicio")), h("th", {}, t("per_cliente")),
        h("th", {}, t("enc_nota")), h("th", {}, t("per_dijo")))),
      h("tbody", {}, ...exp.clientes.map(c => h("tr", {},
        h("td", {}, h("a", { href: `#/servicio/${c.servicio_id}` },
                      c.folio || "—")),
        h("td", { clase: "chico" }, c.cliente || ""),
        h("td", {}, estrellas(c.calificacion, 5)),
        h("td", { clase: "chico" },
          c.dijo || h("span", { clase: "gris" }, t("per_sin_comentario"))))))),
    aviso(t("per_encuesta_es_del_equipo"), ""));
}

function bloqueCertificados(exp) {
  const filas = exp.certificados || [];
  return h("div", { clase: "tarjeta lisa" },
    conAyuda("h3", t("per_certificados"), "personal_certificados"),
    filas.length
      ? h("table", {},
          h("thead", {}, h("tr", {},
            h("th", {}, t("per_curso")), h("th", {}, t("per_institucion")),
            h("th", {}, t("per_obtenido")), h("th", {}, t("per_vence")),
            h("th", {}, ""))),
          h("tbody", {}, ...filas.map(c => h("tr", {},
            h("td", {}, h("b", {}, c.nombre)),
            h("td", { clase: "chico gris" }, c.institucion || "—"),
            h("td", { clase: "chico gris" },
              c.obtenida_en ? fecha(c.obtenida_en) : "—"),
            h("td", { clase: "chico gris" },
              c.vigencia_hasta ? fecha(c.vigencia_hasta)
                               : t("per_permanente")),
            h("td", {}, c.dias === null
              ? etiqueta(t("per_cap_al_corriente"), "ok")
              : c.dias < 0
                ? etiqueta(t("per_cap_vencido"), "grave")
                : c.dias <= 30
                  ? etiqueta(t("per_vence_dias").replace("{n}", c.dias), "alerta")
                  : etiqueta(t("per_vigente"), "ok"))))))
      : h("div", { clase: "vacio" }, t("per_sin_certificados")));
}

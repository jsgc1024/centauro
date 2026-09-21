/* El recorrido de la primera vez.

   La tercera capa de la ayuda. La primera es el pie que cada bloque
   trae escrito; la segunda es el "?" que se abre al lado del titulo.
   Esta es la que solo hace falta una vez: la que le dice a quien entra
   por primera vez que es esto y donde esta lo suyo.

   Tres pasos y no diez. Un recorrido de un paso por pantalla se
   convierte en diez clics para llegar a algo que nadie leyo, y ensena
   que la ayuda de este sistema se salta. Son tres: que tienes arriba,
   donde esta el detalle cuando algo no se entienda, y donde vive lo
   tuyo.

   El primer paso sale de la MISMA lista que arma el menu, asi que cada
   quien ve exactamente sus entradas y el dia que se agregue una
   pantalla, el recorrido la trae sola --y si no trae su texto,
   `revisar.py` se queja--. Un tutorial que vive aparte se despega el dia
   que la pantalla cambia, y nadie se entera hasta que alguien sigue un
   paso que ya no existe.

   Se marca como visto al abrirlo y no al terminarlo: el que lo salta en
   el primer paso tambien lo vio, y un recorrido que no se deja cerrar
   se aprende a odiar. */
import { api } from "./api.js";
import { h, vaciar } from "./util.js";
import { t } from "./idioma.js";

export function abrirRecorrido(entradas, alCerrar = () => {}) {
  let paso = 0;

  const cuerpo = h("div", { clase: "recorrido-cuerpo" });
  const puntos = h("div", { clase: "recorrido-puntos" });
  const anterior = h("button", { clase: "claro chico", type: "button",
    onclick: () => mover(-1) }, t("rec_atras"));
  const siguiente = h("button", { type: "button",
    onclick: () => mover(1) }, t("rec_siguiente"));
  const saltar = h("button", { clase: "claro chico", type: "button",
    onclick: () => cerrar() }, t("rec_saltar"));

  const tarjeta = h("div", { clase: "recorrido-tarjeta",
                             onclick: (e) => e.stopPropagation() },
    cuerpo,
    h("div", { clase: "recorrido-pie" },
      puntos,
      h("div", { clase: "fila", style: "gap:8px" },
        saltar, anterior, siguiente)));

  const capa = h("div", { clase: "recorrido-capa", onclick: () => cerrar() },
    tarjeta);

  function pasos() {
    return [
      () => h("div", {},
        h("h2", { style: "margin:0 0 4px" }, t("rec_p1_titulo")),
        h("p", { clase: "gris chico", style: "margin:0 0 14px" },
          t("rec_p1_pie")),
        ...entradas.map(x => h("div", { clase: "recorrido-entrada" },
          h("b", {}, t(x.texto)),
          h("div", { clase: "chico gris" }, t(x.cuenta))))),
      () => h("div", {},
        h("h2", { style: "margin:0 0 4px" }, t("rec_p2_titulo")),
        h("p", { style: "margin:0" }, t("rec_p2_cuerpo")),
        h("div", { clase: "recorrido-muestra" },
          h("span", { clase: "boton-ayuda-muestra" }, "?"),
          h("span", { clase: "chico gris" }, t("rec_p2_pie")))),
      () => h("div", {},
        h("h2", { style: "margin:0 0 4px" }, t("rec_p3_titulo")),
        h("p", { style: "margin:0" }, t("rec_p3_cuerpo"))),
    ];
  }

  function pintar() {
    const lista = pasos();
    vaciar(cuerpo);
    cuerpo.append(lista[paso]());
    vaciar(puntos);
    for (let i = 0; i < lista.length; i++) {
      puntos.append(h("span", {
        clase: `recorrido-punto ${i === paso ? "activo" : ""}`.trim() }));
    }
    anterior.hidden = paso === 0;
    saltar.hidden = paso === pasos().length - 1;
    siguiente.textContent = paso === lista.length - 1
      ? t("rec_listo") : t("rec_siguiente");
  }

  function mover(cuanto) {
    if (paso + cuanto >= pasos().length) return cerrar();
    paso = Math.max(0, paso + cuanto);
    pintar();
  }

  function cerrar() {
    capa.remove();
    document.removeEventListener("keydown", tecla);
    alCerrar();
  }

  function tecla(e) {
    if (e.key === "Escape") cerrar();
  }

  document.addEventListener("keydown", tecla);
  pintar();
  document.body.append(capa);
  // Se marca al abrirlo. Si falla, no pasa nada: se vuelve a ofrecer.
  api.post("/auth/recorrido-visto", {}).catch(() => {});
}

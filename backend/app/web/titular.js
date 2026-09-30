/* Cambiar al consultor titular de un servicio (decision 13, seccion 105).

   Vacaciones largas, cambio de cartera o una baja: el titular se ponia
   en el alta y no habia forma de cambiarlo. Direccion de operaciones lo
   cambia desde la ficha del eventual y del implantado a otro consultor
   con acceso abierto, con motivo; se les avisa a los dos y desde ese
   momento los avisos, los plazos y la comision son del nuevo.

   El renglon vive aqui y no en cada pantalla porque las dos fichas lo
   pintan igual: el nombre del titular y, para quien trae la actividad,
   el boton que abre el panel debajo. */
import { api, sesion } from "./api.js";
import { campo, entrada, h, lista, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { tiene } from "./menu.js";

/* Lo que ya no cambia de titular en la pantalla: el cerrado. El servidor
   ademas niega el cancelado que ya no tiene nada que cerrar. */
const YA_NO_CAMBIA = ["cerrado"];

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (s, [k, v]) => s.split(`{${k}}`).join(v ?? ""), texto);
}

/* El renglon del titular: en el encabezado del eventual y en la tarjeta
   del cliente del implantado. Quien trae `servicios.titular` ve el boton;
   los demas solo el nombre. */
export function bloqueTitular(servicio, cat) {
  const consultor = (cat.consultores || []).find(
    c => String(c.id) === String(servicio.consultor_id));
  /* Un titular al que ya se le cerro el acceso no sale en la lista de
     consultores: se dice, en vez de dejar el renglon vacio. */
  const nombre = consultor ? consultor.nombre
    : servicio.consultor_id ? t("tit_sin_acceso") : t("tit_sin_asignar");
  const zona = h("div");
  const puede = tiene(sesion.usuario, "servicios.titular")
    && !YA_NO_CAMBIA.includes(servicio.estatus);
  return h("div", { clase: "dato" },
    h("span", { clase: "gris chico" }, t("tit_titular")),
    h("div", { clase: "acciones" },
      h("span", { clase: consultor ? "" : "gris" }, nombre),
      puede
        ? h("button", { clase: "claro chico", type: "button",
            onclick: () => abrir(servicio, zona) }, t("tit_cambiar"))
        : ""),
    zona);
}

/* El mismo boton abre el panel y lo cierra. La lista se pide al abrir y
   no de los catalogos guardados: un acceso de consultor que se dio hace
   un rato tiene que aparecer. */
async function abrir(servicio, zona) {
  if (zona.firstChild) {
    zona.replaceChildren();
    return;
  }
  let consultores;
  try {
    consultores = await api.get("/catalogos/consultores");
  } catch (err) {
    mensaje(err.message, "grave");
    return;
  }
  const otros = consultores.filter(c => c.id !== servicio.consultor_id);
  if (!otros.length) {
    mensaje(t("tit_nadie_mas"), "alerta");
    return;
  }
  zona.replaceChildren(panel(servicio, otros, zona));
  zona.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function panel(servicio, otros, zona) {
  const quien = lista("consultor_id", [
    { valor: "", texto: t("tit_escoge") },
    ...otros.map(c => ({ valor: c.id, texto: c.nombre }))]);
  const motivo = entrada("motivo", { placeholder: t("tit_motivo_ayuda"),
                                     maxlength: "300" });
  const guardar = h("button", { clase: "chico", type: "button",
    onclick: () => mandar() }, t("tit_guardar"));

  async function mandar() {
    if (!quien.value) {
      quien.focus();
      return mensaje(t("tit_falta_quien"), "alerta");
    }
    if (!motivo.value.trim()) {
      motivo.focus();
      return mensaje(t("tit_falta_motivo"), "alerta");
    }
    guardar.disabled = true;
    try {
      const r = await api.put(`/servicios/${servicio.id}/titular`,
                              { consultor_id: Number(quien.value),
                                motivo: motivo.value.trim() });
      mensaje(reemplazar(t("tit_listo"), { n: r.nuevo.nombre }));
      /* La hoja publicada trae al titular anterior como nivel 1 de la
         escalacion: hay que volver a publicarla y mandarla. */
      if (r.hojas_por_republicar) mensaje(t("tit_hoja_vieja"), "alerta");
      setTimeout(() => location.reload(), r.hojas_por_republicar ? 3000 : 1200);
    } catch (err) {
      mensaje(err.message, "grave");
      guardar.disabled = false;
    }
  }

  return h("div", { clase: "tarjeta lisa", style: "margin-top:10px" },
    h("p", { clase: "chico gris", style: "margin:0 0 10px" }, t("tit_pie")),
    campo(t("tit_nuevo"), quien, { obligatorio: true }),
    campo(t("tit_motivo"), motivo, { obligatorio: true }),
    h("div", { clase: "acciones" },
      guardar,
      h("button", { clase: "claro chico", type: "button",
        onclick: () => zona.replaceChildren() }, t("cancelar"))));
}

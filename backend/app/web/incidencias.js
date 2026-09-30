/* Registrar una incidencia (seccion 105, decision 2 de Salvador).

   El motor existia desde hace meses --clasificar, visto bueno, la leve
   quita las estrellas, la grave retiene la comision-- y ninguna pantalla
   creaba una incidencia: Encuestas pedia teclear el numero de una que
   nadie podia crear. Este es el panel, uno solo, y lo abren tres
   lugares: la ficha del eventual, la del implantado y la encuesta con
   mala calificacion.

   La levanta el consultor del servicio --o quien lo cubre-- y tambien
   la central: es quien esta despierta cuando pasa algo en la calle. No
   toca el bono ni la comision hasta el visto bueno del director de
   operaciones, que llega por su propia pantalla. */
import { api, sesion } from "./api.js";
import { aviso, campo, fecha, h, lista, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { tiene } from "./menu.js";

const GRAVEDADES = ["error_menor", "leve", "grave"];

export function puedeRegistrar() {
  return tiene(sesion.usuario, "bonos.incidencia");
}

/* El boton que abre el panel en `zona` y que tambien lo cierra: un
   boton que solo abre obliga a recargar la pantalla para salir. Vacio
   para quien no trae la actividad, como hacen las demas pantallas. */
export function botonIncidencia(servicioId, zona, opciones = {}) {
  if (!puedeRegistrar()) return "";
  const boton = h("button", { clase: "claro chico", type: "button" },
                  t("inc_registrar"));
  boton.addEventListener("click", () => {
    if (zona.firstChild) {
      zona.replaceChildren();
      boton.textContent = t("inc_registrar");
      return;
    }
    boton.textContent = t("cancelar");
    panelIncidencia(zona, servicioId, {
      ...opciones,
      alGuardar: (r) => {
        boton.textContent = t("inc_registrar");
        if (opciones.alGuardar) opciones.alGuardar(r);
      },
    });
  });
  return boton;
}

/* El panel: persona (de las que van o fueron en el servicio, y el
   consultor titular), el dia (las jornadas del servicio; por omision la
   de hoy), la gravedad con una linea que dice que hace cada una, y que
   paso. `personaId` la deja elegida --la encuesta del solicitante
   senala al consultor--. */
export async function panelIncidencia(zona, servicioId,
                                      { personaId = null, alGuardar = null } = {}) {
  zona.replaceChildren(h("p", { clase: "gris chico" }, t("inc_cargando")));
  let o;
  try {
    o = await api.get(`/incidencias/opciones/${servicioId}`);
  } catch (err) {
    return zona.replaceChildren(aviso(err.message, "grave"));
  }

  const personas = lista("persona", o.personas.map(p => ({
    valor: p.persona_id,
    texto: p.nombre
      + (p.consultor ? ` (${t("inc_consultor_titular")})` : "")
      + (p.puesto ? ` · ${p.puesto}` : ""),
  })));
  if (personaId !== null && personaId !== undefined) {
    personas.value = String(personaId);
  }

  /* Los dias del servicio, el mas reciente primero. Un servicio sin
     dias --recien capturado-- pide la fecha a secas. */
  const conDias = o.jornadas.length > 0;
  const dias = conDias
    ? lista("jornada", o.jornadas.map(j => ({
        valor: j.jornada_id, texto: `${fecha(j.fecha)} · ${j.equipo}` })))
    : h("input", { type: "date", name: "fecha", value: o.hoy });
  if (conDias && o.jornada_propuesta) dias.value = String(o.jornada_propuesta);

  const gravedad = lista("gravedad", GRAVEDADES.map(g => (
    { valor: g, texto: t(`inc_g_${g}`) })));
  gravedad.value = "leve";
  const ayuda = h("p", { clase: "chico gris", style: "margin:2px 0 8px" },
                  t("inc_g_leve_ayuda"));
  gravedad.addEventListener("change", () => {
    ayuda.textContent = t(`inc_g_${gravedad.value}_ayuda`);
  });

  const descripcion = h("textarea", { name: "descripcion", rows: "3",
                                      placeholder: t("inc_descripcion_ayuda") });

  const guardar = h("button", { type: "button", disabled: !o.personas.length,
    onclick: async () => {
      if (!personas.value) return mensaje(t("inc_falta_persona"), "alerta");
      if (descripcion.value.trim().length < 15) {
        return mensaje(t("inc_falta_descripcion"), "alerta");
      }
      const cuerpo = {
        persona_id: Number(personas.value),
        gravedad: gravedad.value,
        descripcion: descripcion.value.trim(),
        /* La ficha del implantado llega con el numero como texto (viene
           de la ruta). */
        servicio_id: Number(servicioId),
      };
      if (conDias) {
        const j = o.jornadas.find(x => String(x.jornada_id) === dias.value);
        cuerpo.jornada_id = j ? j.jornada_id : null;
        cuerpo.fecha = j ? j.fecha : o.hoy;
      } else {
        cuerpo.fecha = dias.value || o.hoy;
      }
      guardar.disabled = true;
      try {
        const r = await api.post("/incidencias", cuerpo);
        mensaje(t("inc_registrada").replace("{p}", r.persona)
                  .replace("{g}", t(`inc_g_${r.gravedad}`)));
        zona.replaceChildren();
        if (alGuardar) alGuardar(r);
      } catch (err) {
        mensaje(err.message, "grave");
        guardar.disabled = false;
      }
    } }, t("inc_guardar"));

  zona.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin:12px 0 14px" },
    h("h4", { style: "margin:0 0 4px" }, t("inc_titulo")),
    h("p", { clase: "chico gris", style: "margin:0 0 10px" }, t("inc_pie")),
    o.personas.length
      ? h("div", { clase: "rejilla tres" },
          campo(t("inc_persona"), personas),
          campo(conDias ? t("inc_dia") : t("inc_fecha"), dias),
          campo(t("inc_gravedad"), gravedad))
      : aviso(t("inc_sin_gente"), "alerta"),
    ayuda,
    campo(t("inc_descripcion"), descripcion),
    h("div", { clase: "acciones", style: "margin-top:10px" }, guardar)));
}

/* La gravedad y el estado, en el idioma de quien mira: los comparten la
   bandeja de direccion y el expediente de la persona. */
export function nombreGravedad(g) {
  return t(`inc_g_${g}`);
}

export function etiquetaEstado(estado) {
  return t(`inc_estado_${estado}`);
}

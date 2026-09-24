/* La bitacora del dia: una columna, cuatro fuentes.

   Lo que el cliente dicto, lo que el equipo marco, lo que el sistema
   alerto y lo que la central toco a mano. Cada cosa vivia en su tabla
   y en su pantalla; juntas y por hora es la unica forma de ver donde el
   plan y la realidad se separaron, y que paso en los huecos.

   No trae las lecturas de posicion del trayecto. Esas existen antes del
   meet and greet, donde hay una decision que tomar, y se apagan al
   marcar la llegada: meterlas aqui convertiria esto en un rastreo. */
import { api } from "./api.js";
import { aviso, campo, conAyuda, entrada, h, hora, lista,
         testigo } from "./util.js";
import { t } from "./idioma.js";

const ICONO = { plan: "▲", hito: "●", alerta: "◆", central: "■", nota: "✎" };

/* Los nombres de las cuatro fuentes se traducen con su tabla. Un hito
   que llegara con un tipo nuevo se dibuja con su clave cruda antes que
   desaparecer del hilo: en una bitacora, un renglon feo es mejor que un
   renglon que falta. */
function titulo(r) {
  const claves = {
    plan: null,
    hito: `cen_hito_${r.titulo}`,
    alerta: `bit_alerta_${r.titulo}`,
    central: `bit_accion_${r.titulo.replace(/ /g, "_")}`,
    // La nota se titula con el nombre de quien la escribio: el texto es
    // el cuerpo y la firma es lo que se lee primero.
    nota: null,
  };
  const clave = claves[r.fuente];
  if (!clave) return r.titulo;
  const texto = t(clave);
  return texto === clave ? r.titulo : texto;
}

export async function bitacoraDelDia(jornadaId) {
  const zona = h("div", { clase: "bitacora" });
  await pintar(zona, jornadaId);
  return zona;
}

async function pintar(zona, jornadaId) {
  let d;
  try { d = await api.get(`/operacion/jornadas/${jornadaId}/dia`); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }

  const refrescar = () => pintar(zona, jornadaId);

  /* La leyenda dice de donde sale cada renglon; el "?" dice lo que la
     leyenda no puede: que un renglon sin hora es una parada que se
     planeo y nadie marco, y que las posiciones del trayecto no estan
     aqui a proposito. Eso es justo lo que alguien pregunta la primera
     vez que abre esto y ve un hueco de dos horas. */
  const leyenda = ["plan", "hito", "alerta", "central", "nota"].map(f =>
    h("span", {}, `${ICONO[f]} `, h("b", {}, t(`bit_fuente_${f}`))));

  const todos = [...d.renglones, ...d.sin_hora];

  zona.replaceChildren(
    conAyuda("div", leyenda, "ay_bitacora", { clase: "leyenda_bitacora" }),
    /* Todas las horas son de la pared del pais del servicio, y se dice:
       la central de un pais lee la bitacora de otro. */
    d.hora_de
      ? h("div", { clase: "gris chico", style: "margin:-4px 0 10px" },
          t("bit_horas_de").replace("{pais}", d.hora_de))
      : "",
    ...(todos.length
      ? todos.map(r => renglon(r, d, refrescar))
      : [h("div", { clase: "vacio" }, t("bit_vacia"))]),
    /* Lo que se escribe va al final, debajo de lo que ya paso: primero
       se lee el dia y luego se le agrega. Un cuadro de texto arriba
       empuja el dia hacia abajo cada vez que se abre esto. */
    cajaDeNota(jornadaId, refrescar),
    bloqueManana(d, refrescar),
    bloqueReabrir(d, refrescar));
}

/* La nota de turno: lo unico que puede escribir cualquiera que vea el
   dia. No toca lo que se factura ni lo que se paga --es informacion--
   y quien recibe la llamada del cliente es el consultor, asi que si no
   pudiera escribirla, ese dato no entraria nunca. */
function cajaDeNota(jornadaId, refrescar) {
  const texto = entrada("texto", { placeholder: t("bit_nota_ph"),
                                   maxlength: 600 });
  const zonaAviso = h("div", {});
  const boton = h("button", { clase: "chico", type: "button",
    onclick: async () => {
      if (texto.value.trim().length < 3) {
        return zonaAviso.replaceChildren(aviso(t("bit_nota_corta"), "alerta"));
      }
      boton.disabled = true;
      try {
        await api.post(`/operacion/jornadas/${jornadaId}/notas`,
                       { texto: texto.value.trim() });
        await refrescar();
      } catch (err) {
        boton.disabled = false;
        zonaAviso.replaceChildren(aviso(err.message, "grave"));
      }
    } }, t("bit_nota_guardar"));

  return h("div", { clase: "bit_escribir" },
    h("div", { clase: "gris chico" }, t("bit_nota_pie")),
    h("div", { clase: "fila" },
      h("div", { style: "flex:1;min-width:220px" }, texto), boton),
    zonaAviso);
}

/* Deshacer el cierre de un dia.

   Va al final de la bitacora y no arriba, a proposito: primero se lee
   lo que paso ese dia y despues, si de verdad hay que deshacerlo, se
   deshace. Un boton de este tamaño arriba del todo se toca por error.

   Si lo cerro el equipo desde la calle, su marca de fin se anula --con
   nombre y motivo, y aparece en esta misma bitacora en rojo-- pero no
   se borra. Se dice antes de tocarlo, no despues. */
function bloqueReabrir(d, refrescar) {
  if (!d.puedo_registrar_a_mano) return h("div", {});
  if (d.estatus_jornada !== "terminada") return h("div", {});

  const motivo = entrada("motivo", { placeholder: t("bit_reabrir_ph"),
                                     maxlength: 400 });
  const zonaAviso = h("div", {});
  const boton = h("button", { clase: "chico claro", type: "button",
    onclick: async () => {
      if (motivo.value.trim().length < 5) {
        return zonaAviso.replaceChildren(
          aviso(t("bit_reabrir_falta"), "alerta"));
      }
      if (!confirm(t("bit_reabrir_seguro"))) return;
      boton.disabled = true;
      try {
        await api.post(`/operacion/jornadas/${d.jornada_id}/reabrir`,
                       { justificacion: motivo.value.trim() });
        await refrescar();
      } catch (err) {
        boton.disabled = false;
        zonaAviso.replaceChildren(aviso(err.message, "grave"));
      }
    } }, t("bit_reabrir_boton"));

  return h("div", { clase: "bit_escribir" },
    conAyuda("h4", t("bit_reabrir_titulo"), "ay_bit_reabrir"),
    h("div", { clase: "gris chico" }, t("bit_reabrir_pie")),
    motivo, zonaAviso, boton);
}

/* "Mañana arrancamos a las siete", dicho al cerrar el dia de hoy.
   Solo sale si este equipo tiene otro dia despues de este, y solo para
   quien puede corregir: cambia una hora sobre la que ya hay gente
   confirmada, y al guardarla se les avisa. */
function bloqueManana(d, refrescar) {
  if (!d.manana || !d.puedo_registrar_a_mano) return h("div", {});

  const cuando = entrada("hora", { type: "time", value: d.manana.hora });
  const nota = entrada("nota", { placeholder: t("bit_manana_nota_ph"),
                                 maxlength: 600 });
  const zonaAviso = h("div", {});
  const boton = h("button", { clase: "chico", type: "button",
    onclick: async () => {
      if (!cuando.value) {
        return zonaAviso.replaceChildren(aviso(t("bit_manana_falta"), "alerta"));
      }
      boton.disabled = true;
      try {
        await api.post(
          `/operacion/jornadas/${d.jornada_id}/hora-de-manana`,
          { hora: cuando.value.length === 5 ? `${cuando.value}:00` : cuando.value,
            nota: nota.value.trim() || null });
        await refrescar();
      } catch (err) {
        boton.disabled = false;
        zonaAviso.replaceChildren(aviso(err.message, "grave"));
      }
    } }, t("bit_manana_guardar"));

  return h("div", { clase: "bit_escribir" },
    conAyuda("h4", t("bit_manana_titulo"), "ay_bit_manana"),
    h("div", { clase: "gris chico" },
      t("bit_manana_pie").replace("{fecha}", d.manana.fecha)),
    campo(t("bit_manana_hora"), cuando),
    campo(t("bit_manana_nota"), nota),
    zonaAviso,
    h("div", { clase: "acciones" }, boton));
}

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (s, [k, v]) => s.split(`{${k}}`).join(v ?? ""), texto);
}

function distancia(metros) {
  if (metros === null || metros === undefined) return "—";
  /* "14 km", no "14.0 km"; "2.4 km" sigue con su decimal. */
  return metros < 1000 ? `${metros} m`
                       : `${Number((metros / 1000).toFixed(1))} km`;
}

/* El segundo testigo (seccion 60): lo que decia la unidad de quien
   marco, en el momento de la marca. Una sola medida por marca --las
   posiciones del camino siguen sin entrar aqui--. */
function chipDeLaUnidad(u) {
  let texto;
  if (u.veredicto === "ok") {
    texto = `✓ ${reemplazar(t("bit_unidad_a"), { d: distancia(u.distancia_m) })}`;
  } else if (u.guardada_en) {
    texto = reemplazar(t("bit_unidad_guardada"), { hora: hora(u.guardada_en) });
  } else {
    texto = reemplazar(t("bit_unidad_lejos"), { d: distancia(u.distancia_m) });
  }
  return h("span", { clase: `marca ${u.veredicto === "ok" ? "ok" : "alerta"}` },
    texto);
}

function renglon(r, d, refrescar) {
  const u = r.unidad;
  return h("div", { clase: `paso ${r.fuente}` },
    h("div", { clase: "hora" }, r.momento ? hora(r.momento) : t("bit_sin_hora")),
    h("div", { clase: "eje" }, h("span", { clase: "punto" }, ICONO[r.fuente])),
    h("div", { clase: "cuerpo" },
      h("div", { clase: "titulo" }, titulo(r),
        r.marca
          ? h("span", { clase: `marca ${r.tono}`.trim() }, r.marca)
          : null,
        u ? chipDeLaUnidad(u) : null),
      r.detalle ? h("div", { clase: "detalle" }, r.detalle) : null,
      u && u.guardada_en
        ? testigo(`${t("gps_unidad")} ${u.placa || ""}`.trim(),
                  reemplazar(t("bit_unidad_guardada_detalle"), {
                    hora: hora(u.guardada_en),
                    km: Number((u.guardada_m / 1000).toFixed(1)) }),
                  "alerta")
        : null,
      /* Corregir la hora de una marca vive AQUI y en ningun otro lado:
         es el unico lugar donde las marcas se ven en su contexto, que
         es lo que hace falta para saber si una hora esta mal. */
      r.hito_id && d.puedo_registrar_a_mano
        ? corregirMarca(r, refrescar)
        : null));
}

function corregirMarca(r, refrescar) {
  const zona = h("div", {});
  const boton = h("button", { clase: "claro chico", type: "button",
    onclick: () => {
      if (zona.firstChild) return zona.replaceChildren();
      const cuando = entrada("nuevo_momento",
                             { type: "datetime-local",
                               value: (r.momento || "").slice(0, 16) });
      const motivo = entrada("justificacion",
                             { placeholder: t("bit_corregir_ph"),
                               maxlength: 400 });
      const zonaAviso = h("div", {});
      const guardar = h("button", { clase: "chico", type: "button",
        onclick: async () => {
          /* Diez letras, las mismas que pide el servidor: con cinco, el
             boton dejaba pasar un motivo que despues rebotaba. */
          if (!cuando.value || motivo.value.trim().length < 10) {
            return zonaAviso.replaceChildren(
              aviso(t("bit_corregir_faltan"), "alerta"));
          }
          guardar.disabled = true;
          try {
            await api.post(`/operacion/hitos/${r.hito_id}/ajustar`, {
              nuevo_momento: cuando.value.length === 16
                ? `${cuando.value}:00` : cuando.value,
              justificacion: motivo.value.trim(),
            });
            await refrescar();
          } catch (err) {
            guardar.disabled = false;
            zonaAviso.replaceChildren(aviso(err.message, "grave"));
          }
        } }, t("bit_corregir_guardar"));
      zona.replaceChildren(h("div", { clase: "bit_corregir" },
        campo(t("bit_corregir_hora"), cuando),
        campo(t("bit_corregir_motivo"), motivo),
        zonaAviso,
        h("div", { clase: "acciones" }, guardar)));
    } }, t("bit_corregir"));
  return h("div", {}, boton, zona);
}

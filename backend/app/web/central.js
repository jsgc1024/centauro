/* La central de inteligencia.

   Esta pantalla queda abierta todo el dia en un monitor, asi que el
   orden importa mas que el contenido. Y el orden sale de una idea: una
   central que solo mira lo que esta pasando llega tarde siempre —si el
   equipo no llego al punto, ya no llego—. El unico momento en que se
   puede cambiar el resultado de un servicio es la vispera.

   Por eso el eje no es "ahora", es el tiempo:

     1. lo roto     lo que ya no se arregla solo
     2. manana      el meet and greet, que es el corazon
     3. el pulso    los que estan en curso y cuanto llevan callados
     4. la semana   para ver venir el lunes de seis servicios
*/
import { api } from "./api.js";
import { aviso, campo, conAyuda, entrada, estatus, etiqueta, h, hora,
         lista, mensaje } from "./util.js";
import { t } from "./idioma.js";

const REFRESCO_SEGUNDOS = 45;
let temporizador = null;

export async function tableroCentral(main) {
  main.append(
    h("h1", {}, t("central_titulo")),
    h("p", { clase: "sub" },
      t("cen_sub").replace("{s}", REFRESCO_SEGUNDOS)));

  const zona = h("div");
  main.append(zona);

  const refrescar = async () => {
    if (!document.body.contains(zona)) {
      clearInterval(temporizador);
      return;
    }
    await pintar(zona);
  };

  await refrescar();
  clearInterval(temporizador);
  temporizador = setInterval(refrescar, REFRESCO_SEGUNDOS * 1000);
}

async function pintar(zona) {
  let d;
  try {
    d = await api.get("/central/tablero");
  } catch (e) {
    return zona.replaceChildren(aviso(e.message, "grave"));
  }
  /* Los dias sin cerrar van al final a proposito: no son urgentes
     —ya pasaron— pero tampoco pueden quedarse invisibles, porque cada
     uno es alguien esperando su pago. */
  const sinCerrar = await bandaSinCerrar(zona);
  /* El camino va arriba de todo lo demas y debajo de lo roto: es el
     unico rato en que todavia se puede hacer algo. Reponer a alguien
     toma hora y media. */
  const camino = await bandaCamino();
  zona.replaceChildren(
    bandaRoto(d.roto, zona),
    ...(camino ? [camino] : []),
    bandaManana(d),
    bandaPulso(d.pulso),
    bandaSemana(d.semana),
    ...(sinCerrar ? [sinCerrar] : []));
}

/* ------------------------------------------- 0 · el camino al punto

   Aparece sola cuando hay alguien en camino y desaparece cuando todos
   llegaron: si no hay nada que mirar, no ocupa pantalla. Es la misma
   regla de la banda de lo roto, y por la misma razon.

   El peor primero. Lo que quien abre esto tiene que decidir es a quien
   manda, y eso empieza por quien no va a llegar. */

async function bandaCamino() {
  let d;
  try { d = await api.get("/central/camino"); }
  catch { return null; }
  if (!d.cuantos) return null;

  const tono = { no_llega: "grave", sin_respuesta: "grave",
                 esperando: "alerta", en_camino: "ok" };

  const caja = h("div", { clase: "tarjeta" },
    conAyuda("h3", `${t("cen_camino")} · ${d.cuantos}`, "ay_cen_camino"),
    h("p", { clase: "gris chico", style: "margin:-6px 0 12px" },
      t("cen_camino_sub")));

  for (const q of d.gente) {
    /* El renglon se arma aparte y despues se cuelga. No es estilo: los
       hijos nulos que lleva adentro los filtra h(), pero `append` los
       pintaria en letras si alguno se le pasara directo. */
    const renglon = h("div", { clase: "renglon_atender" },
      h("div", {},
        h("b", {}, q.persona || "—"),
        h("span", { clase: `etiqueta ${tono[q.estado] || ""}`,
                    style: "margin-left:8px" }, t(`cen_camino_${q.estado}`)),
        h("div", { clase: "gris chico" },
          [q.servicio,
           t("cen_camino_punto").replace("{hora}", q.estar_en_el_punto),
           q.distancia_km != null
             ? t("cen_camino_km").replace("{km}", q.distancia_km) : null,
          ].filter(Boolean).join(" · ")),
        /* Quien lo dijo y a que hora. Sin esto, "va en camino" por
           telefono se leeria igual que una posicion del GPS, y esa es
           justamente la diferencia que importa el dia que no llegue. */
        q.por_telefono
          ? h("div", { clase: "gris chico" },
              [t("cen_camino_dijo").replace("{hora}", q.por_telefono)
                 .replace("{quien}", q.por_telefono_por || "—"),
               q.por_telefono_nota].filter(Boolean).join(" · "))
          : null),
      /* El telefono a un clic: lo primero que hace quien lee esto es
         llamar. Despues, lo que se pueda asentar de esa llamada: que
         dijo que va, o que ya esta parado en el punto. Y la bitacora,
         que es lo que conviene leer antes de marcar. */
      h("div", { clase: "acciones chico" },
        q.telefono
          ? h("a", { clase: "chico", href: `tel:${q.telefono}` }, q.telefono)
          : null,
        q.persona_id ? botonVaEnCamino(q) : null,
        q.persona_id
          ? botonDeMarca(q, "llegada_origen", ".renglon_atender") : null,
        q.persona_id
          ? botonDeMarca(q, "contacto_ejecutivo", ".renglon_atender") : null,
        q.jornada_id
          ? botonBitacora(q.jornada_id, enLaTarjeta)
          : null));
    caja.append(renglon);
  }
  return caja;
}


/* ------------------------------ lo que se asienta de esa llamada

   La central llama todo el dia y hasta hoy no tenia donde escribir lo
   que le contestaron. El renglon rojo se quedaba rojo con el hombre ya
   manejando hacia el punto, y un renglon rojo que miente es lo que
   ensena a ignorar los renglones rojos.

   Dos botones y nada mas, porque de una llamada salen dos cosas: "ya
   voy" y "ya llegue". Los dos dejan el nombre de quien los registro. */

function botonVaEnCamino(q) {
  const boton = h("button", { clase: "claro chico", type: "button" },
    t("cen_camino_va"));
  boton.onclick = async () => {
    boton.disabled = true;
    try {
      const r = await api.post(
        `/central/camino/${q.jornada_id}/por-telefono`,
        { persona_id: q.persona_id });
      /* Se dice en voz alta que la vigilancia sigue: quien aprieta esto
         tiene que saber que no acaba de apagar nada. */
      mensaje(t("cen_camino_va_ok")
        .replace("{min}", r.vigilancia_vuelve_en));
      boton.remove();
    } catch (err) { mensaje(err.message, "grave"); boton.disabled = false; }
  };
  return boton;
}

/* La marca dictada por telefono NO es un clic.

   Crea una marca que nadie hizo en la calle, y de la llegada salen las
   horas que se le facturan al cliente: por eso pide la hora que dicto
   el agente y por que se registra a mano, y queda sellada para siempre
   con el nombre de quien la puso. Es el mismo camino de siempre --la
   marca a mano-- puesto donde de verdad se usa.

   Dos marcas se dictan por telefono y no una: "ya llegue al punto" y
   "ya estoy con el principal". La segunda es la que arranca el
   servicio, y sin ella un dia entero se quedaba en "arribado" con el
   equipo trabajando.

   El orden lo cuida el servidor: un contacto con el ejecutivo sin
   llegada cuenta una historia que no ocurrio, y contesta diciendolo. */

const MARCAS_A_MANO = {
  llegada_origen: "cen_marca_llego",
  contacto_ejecutivo: "cen_marca_principal",
};

function botonDeMarca(q, tipo, donde) {
  const boton = h("button", { clase: "claro chico", type: "button" },
    t(MARCAS_A_MANO[tipo]));
  boton.onclick = () => {
    const caja = boton.closest(donde);
    const abierto = caja.querySelector(".marca_a_mano");
    const mismo = abierto && abierto.dataset.tipo === tipo;
    if (abierto) abierto.remove();
    if (mismo) return;
    caja.append(formularioDeMarca(q, tipo, boton));
  };
  return boton;
}

function formularioDeMarca(q, tipo, boton) {
  const cuando = h("input", { type: "time", required: "required" });
  cuando.value = new Date().toTimeString().slice(0, 5);
  const porque = h("input", { type: "text", maxlength: "400",
                              placeholder: t("cen_marca_motivo") });
  const guardar = h("button", { clase: "chico", type: "button" },
    t("cen_marca_guardar"));

  /* Con dos o mas en el dia hay que decir de quien es la marca: se le
     acredita a quien la dicto, no al equipo. Con uno solo no se
     pregunta nada. */
  const gente = q.gente || [{ persona_id: q.persona_id, nombre: q.persona }];
  const quien = gente.length > 1
    ? lista("persona", gente.map(g => ({ valor: g.persona_id,
                                         texto: g.nombre })))
    : null;

  guardar.onclick = async () => {
    if (porque.value.trim().length < 5) {
      return mensaje(t("cen_marca_falta_motivo"), "grave");
    }
    guardar.disabled = true;
    try {
      await api.post(`/operacion/jornadas/${q.jornada_id}/marca-a-mano`, {
        tipo,
        persona_id: Number(quien ? quien.value : gente[0].persona_id),
        momento: `${q.fecha}T${cuando.value}:00`,
        justificacion: porque.value.trim(),
      });
      mensaje(t(tipo === "contacto_ejecutivo" ? "cen_marca_principal_ok"
                                              : "cen_marca_llego_ok"));
      boton.remove();
      panel.remove();
    } catch (err) { mensaje(err.message, "grave"); guardar.disabled = false; }
  };

  const panel = h("div", { clase: "marca_a_mano rejilla tres",
                           style: "margin-top:10px" },
    quien ? campo(t("srv_persona"), quien) : null,
    campo(t("cen_marca_hora"), cuando),
    campo(t("cen_marca_por_que"), porque),
    h("div", { clase: "campo" }, h("label", {}, " "), guardar));
  panel.dataset.tipo = tipo;
  return panel;
}


/* ------------------------------------------------- 1 · lo roto

   Si no hay nada, esta banda no existe. Una franja que siempre dice
   "todo bien" deja de leerse a la semana. */

function bandaRoto(roto, zona) {
  if (!roto.hay) return h("div", {});

  const caja = h("div", { clase: "tarjeta" },
    h("h3", {}, t("cen_roto")));

  for (const a of roto.panico) {
    caja.append(fichaPanico(a, zona));
  }
  for (const f of roto.callados) {
    caja.append(renglonRoto(t("cen_callado"), "grave",
      `${f.folio} · ${f.cliente || ""}`,
      f.minutos_callado === null
        ? t("cen_nunca_reporto")
        : t("cen_callado_min").replace("{n}", f.minutos_callado),
      f, quePuedoHacer(f)));
  }
  for (const f of roto.manana_vencido) {
    /* Lo que le falta, punto por punto y con lo que hay que hacer.
       Antes aqui decia "faltan 2" y ya: quien leia esto a las seis de
       la tarde no podia saber si le faltaba el punto de encuentro o la
       confirmacion de alguien, y tenia que abrir otra pantalla para
       averiguarlo. La frase existe --la escribe `revision_del_dia`-- y
       la banda de manana ya la enseña: la banda urgente decia MENOS que
       la tranquila sobre el mismo servicio. */
    caja.append(renglonRoto(t("cen_vencido"), "grave",
      `${f.folio} · ${hora(f.equipo_llega)}`,
      `${cuantasFaltan(f.faltan)}${f.consultor ? " · " + f.consultor : ""}`,
      f, loQueFalta(f)));
  }
  for (const f of roto.por_entrar_en_extra) {
    caja.append(renglonRoto(t("cen_extra"), "alerta",
      `${f.folio} · ${f.cliente || ""}`,
      `${f.minutos_para_horas_extra} min`, f));
  }
  return caja;
}

/* Un renglon en rojo sin que hacer se vuelve paisaje.

   Con el silencio hay tres situaciones distintas y hasta hoy se veian
   iguales: el servicio sigue corriendo --no hay nada que cerrar, hay
   que llamar--; acaba de terminar y corren las horas de gracia por si
   la marca llega tarde; o ya pasaron y el dia se firma a mano. La
   diferencia decide que hace quien lo lee, asi que se dice. */
const HORAS_DE_GRACIA = 3;

function quePuedoHacer(f) {
  const partes = [];

  for (const c of (f.contactos || [])) {
    partes.push(h("a", { clase: "chico", href: `tel:${c.telefono}`,
                         style: "margin-right:12px" },
      `${c.nombre} · ${c.telefono}`));
  }

  const desde = f.minutos_desde_fin;
  let consejo = t("cen_silencio_en_curso");
  if (desde !== null && desde !== undefined && desde > 0) {
    consejo = desde < HORAS_DE_GRACIA * 60
      ? t("cen_silencio_gracia").replace(
          "{n}", Math.max(1, Math.ceil(HORAS_DE_GRACIA - desde / 60)))
      : t("cen_silencio_cerrar");
  }
  partes.push(h("div", { clase: "gris chico", style: "margin-top:6px" },
                consejo));

  /* Y lo que salga de esa llamada se asienta aqui mismo.

     El caso que lo pide: el equipo lleva dos horas sin reportar, la
     central llama y el agente contesta que va con el principal desde
     hace rato --nada mas no marco--. Sin esto, el dia entero se queda
     en "arribado" y alguien tiene que ir a buscar la pantalla del
     servicio con el renglon en rojo enfrente. */
  const gente = (f.contactos || []).filter(c => c.persona_id);
  if (f.jornada_id && f.fecha && gente.length) {
    const q = { jornada_id: f.jornada_id, fecha: f.fecha, gente };
    partes.push(h("div", { clase: "acciones chico", style: "margin-top:8px" },
      botonDeMarca(q, "llegada_origen", ".tarjeta"),
      botonDeMarca(q, "contacto_ejecutivo", ".tarjeta")));
  }

  return h("div", { style: "margin-top:8px" }, ...partes);
}

function loQueFalta(f) {
  const faltan = (f.revision || []).filter(p => !p.listo);
  if (!faltan.length) return null;
  return h("ul", { clase: "minimo",
                   style: "margin:10px 0 0;padding-left:18px;display:block" },
    ...faltan.map(p => h("li", { style: "margin-bottom:4px" },
      h("b", {}, t(`cen_p_${p.clave}`)), ": ",
      h("span", { clase: "chico" }, p.que_hacer || ""))));
}

function renglonRoto(titulo, tono, principal, detalle, ficha, extra) {
  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 10px" },
    h("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center" },
      h("div", {},
        etiqueta(titulo, tono), " ",
        h("b", {}, principal),
        h("div", { clase: "gris chico" }, detalle)),
      /* Las dos salidas juntas: el servicio completo, y el dia de este
         renglon. La segunda es la que se usa al triar --lo que hay que
         saber es que paso HOY con este equipo-- y hasta ahora obligaba
         a abrir el servicio y buscar el dia ahi dentro. */
      h("div", { clase: "acciones chico" },
        ficha && ficha.servicio_id
          ? h("a", { clase: "chico", href: rutaDelServicio(ficha) },
              t("cen_ver_servicio"))
          : null,
        ficha && ficha.jornada_id
          ? botonBitacora(ficha.jornada_id, enLaTarjeta)
          : null)),
    extra || null);
}

/* Si el principal va con el, segun su ultima marca.

   Es lo que decide a quien se manda cuando suena el boton: no es lo
   mismo un conductor solo que un conductor con el ejecutivo del cliente
   adentro del coche. Y se dice de donde sale la respuesta, porque es una
   deduccion y no un hecho: el boton se aprieta justo cuando las cosas
   dejaron de ir como estaban marcadas. */

function conPrincipal(a) {
  const p = a.principal || {};
  if (!p.estado) return null;
  const tono = { a_bordo: "grave", en_espera: "alerta",
                 todavia_no: "", termino: "", sin_marcas: "alerta" };
  return h("div", { clase: "chico", style: "margin-top:4px" },
    etiqueta(t(`cen_panico_principal_${p.estado}`), tono[p.estado] || ""),
    p.ultima_marca
      ? h("span", { clase: "gris chico" },
          " " + t("cen_panico_segun_marca").replace("{hora}", p.ultima_marca))
      : null);
}

function fichaPanico(a, zona) {
  const canal = { boton_app: t("canal_boton_app"),
                  boton_vehiculo: t("canal_boton_vehiculo"),
                  llamada: t("canal_llamada") }[a.canal] || a.canal;
  const urgente = a.estatus === "abierta";
  const acciones = h("div", { clase: "acciones", style: "margin-top:10px" });

  if (urgente) {
    /* UN solo boton. Si sale o no equipo de respuesta se decide por
       telefono en los siguientes segundos --no eligiendo entre dos
       botones con una alerta de panico en pantalla-- y queda escrito en
       la resolucion al cerrarla. Decision de Salvador, 21 sep. */
    acciones.append(
      h("button", { clase: "chico", onclick: (e) => tomar(e, false) },
        t("central_tomar")));
  } else {
    /* Ya esta tomada. Lo que falta aqui no es un boton mas: es decir que
       dejarla asi ESTA BIEN.
    
       Con solo el cuadro de texto y "Cerrar", la tarjeta se lee como una
       exigencia --resuelve esto ahora-- cuando en realidad esa es la
       accion de cuando uno ya termino. Quien la tomo y se fue a
       gestionarla creia que el sistema le estaba pidiendo cerrarla de
       inmediato. Se dice con todas sus letras. */
    const nota = entrada("resolucion",
                         { placeholder: t("central_resolucion_ph") });
    acciones.append(
      h("div", { style: "flex:1;min-width:240px" }, nota),
      h("button", { clase: "chico", onclick: (e) => cerrar(e, nota) },
        t("central_cerrar")));
  }

  async function tomar(e, conEquipo) {
    e.target.disabled = true;
    try {
      await api.post(`/contingencia/alertas/${a.id}/tomar`,
                     { equipo_respuesta_enviado: conEquipo });
      mensaje(conEquipo ? t("central_alerta_tomada_equipo")
                        : t("central_alerta_tomada"));
      await pintar(zona);
    } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
  }

  async function cerrar(e, nota) {
    if (!nota.value.trim()) {
      return mensaje(t("central_falta_resolucion"), "alerta");
    }
    e.target.disabled = true;
    try {
      await api.post(`/contingencia/alertas/${a.id}/cerrar`,
                     { resolucion: nota.value });
      mensaje(t("central_alerta_cerrada"));
      await pintar(zona);
    } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
  }

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 12px" },
    h("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap" },
      h("div", {},
        etiqueta(t("cen_panico"), "grave"), " ",
        /* De quien es, ANTES del canal. Lo primero que hace quien lee
           esto es llamar a esa persona, y con el panico sin servicio no
           hay folio del que deducirlo: el nombre es lo unico que
           identifica la alerta. */
        h("b", {}, a.quien || t("cen_panico_sin_nombre")),
        h("div", { clase: "gris chico" },
          `${canal} · ${t("central_reportada")} ${hora(a.reportada_en)}`),
        /* En que servicio esta. Estaba en el sistema y habia que ir a
           buscarlo a otra pantalla con la alerta sonando. */
        a.servicio
          ? h("div", { clase: "chico" },
              h("b", {}, a.servicio),
              a.equipo ? ` · ${t("col_equipo")} ${a.equipo}` : "")
          : null,
        /* Y si lleva al principal. Es lo que decide a quien se manda:
           no es lo mismo un conductor solo que un conductor con el
           ejecutivo del cliente adentro del coche.

           Se dice de donde sale la respuesta --su ultima marca-- porque
           es una deduccion, no un hecho. El boton de panico se aprieta
           justo cuando las cosas dejaron de ir como estaban marcadas, y
           quien lee esto tiene que saber que esta leyendo la ultima
           noticia, no la situacion. */
        conPrincipal(a),
        /* Y se dice que no trae servicio, en vez de dejar el hueco.
           Un renglon sin folio se lee como un error de la pantalla; asi
           se lee como lo que es --alguien que apreto el boton fuera de
           un servicio-- que es una situacion, no una falla. */
        a.servicio_id
          ? null
          : h("div", { clase: "chico", style: "color:#7a5c07;margin-top:4px" },
              t("cen_panico_sin_servicio"))),
      etiqueta(estatus(a.estatus), urgente ? "grave" : "alerta")),
    /* El telefono a un toque: es la primera accion, siempre. */
    a.telefono
      ? h("div", { clase: "chico", style: "margin-top:6px" },
          h("a", { href: `tel:${a.telefono}` }, a.telefono))
      : null,
    /* Quien la tomo y desde cuando. Una tomada hace dos minutos por
       otro no se toca; una en atencion desde hace cuarenta minutos y
       sin cerrar es una que se quedo sola. */
    !urgente && a.tomada_por
      ? h("div", { clase: "chico gris", style: "margin-top:6px" },
          t("central_la_tomo").replace("{quien}", a.tomada_por)
            .replace("{hora}", hora(a.tomada_en)),
          h("div", {}, t("central_sin_prisa")))
      : null,
    a.descripcion ? h("p", { style: "margin:8px 0 0" }, a.descripcion) : null,
    /* La central estabiliza y el consultor formaliza. Verlo aqui ahorra
       la llamada de "oye, ¿ya lo cambiaste?". */
    a.cambio
      ? h("div", { clase: "chico", style: "margin-top:6px" },
          etiqueta(t("central_cambio"), "ok"), " ", a.cambio)
      : null,
    a.lat
      ? h("div", { clase: "chico" },
          h("a", { target: "_blank",
                   href: `https://www.google.com/maps?q=${a.lat},${a.lon}` },
            t("central_ver_mapa")))
      : null,
    acciones);
}

/* --------------------------------------------- 2 · manana

   El corazon de la pantalla. Una tarjeta por servicio, ordenadas por la
   hora a la que el equipo tiene que estar parado en el punto —que es la
   unica hora que de verdad se puede perder— y debajo, lo que tiene que
   ser cierto para que ese encuentro ocurra. */

/* A donde lleva "abrir el servicio". Eventual e implantado son dos
   pantallas distintas, y el tablero mezcla los dos. */
function rutaDelServicio(f) {
  return f.tipo === "implantado"
    ? `#/implantado/${f.servicio_id}`
    : `#/servicio/${f.servicio_id}`;
}

function cuantasFaltan(n) {
  return n === 1 ? t("cen_falta_uno") : t("cen_faltan").replace("{n}", n);
}

function bandaManana(d) {
  const m = d.manana;
  const caja = h("div", { clase: "tarjeta" },
    h("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline" },
      conAyuda("h3", t("cen_manana"), "ay_cen_manana",
               { style: "margin:0" }),
      h("div", { clase: "chico" },
        m.cuantos
          ? h("span", {},
              h("span", { clase: "verde" }, `${m.listos} ${t("cen_listos")}`),
              m.incompletos
                ? h("span", { clase: "ambar" },
                    ` · ${m.incompletos} ${t("cen_incompletos")}`)
                : null)
          : null)),
    h("p", { clase: "gris chico", style: "margin:4px 0 10px" },
      t("cen_manana_sub")),
    /* El corte de la vispera: antes es trabajo, despues es un problema
       de esta noche. Decirlo cambia como se lee toda la banda. */
    h("div", { clase: d.paso_el_corte ? "aviso alerta" : "aviso",
               style: "margin:0 0 12px" },
      h("b", {}, `${t("cen_corte")} ${d.corte_de_la_vispera}`), " · ",
      d.paso_el_corte ? t("cen_paso_el_corte") : t("cen_antes_del_corte")));

  if (!m.cuantos) {
    caja.append(h("div", { clase: "vacio" }, t("cen_manana_nada")));
    return caja;
  }
  for (const f of m.servicios) caja.append(tarjetaDelDia(f));
  return caja;
}

/* Un renglon del equipo de manana, con su confirmacion.

   Aqui vive el unico camino que existe para el agente que no trae la
   app: la central le habla, el dice que si, y alguien lo registra. Sin
   esto el renglon se quedaba rojo para siempre aunque la central
   supiera perfectamente que el agente va --y un renglon rojo que
   miente ensena a ignorar los renglones rojos--.

   Lo que se registra NO se pinta igual que lo que confirmo la persona:
   lleva el nombre de quien lo registro. El dia que alguien no llegue,
   la diferencia entre "confirmo el" y "lo confirmaron por el" es la
   unica pregunta que importa. */
function renglonDePersona(f, p) {
  const marca = h("span", { clase: `marca ${p.confirmado ? "si" : ""}` },
    p.confirmado ? "✓" : "?");
  const sello = h("span", { clase: "gris chico" },
    p.confirmado && p.confirmado_por
      ? ` · ${t("cen_por_telefono")} ${p.confirmado_por}`
      : "");

  const boton = h("button", { clase: "claro chico",
                              style: "margin-left:8px" },
    t("cen_confirmo_por_telefono"));
  boton.onclick = async () => {
    boton.disabled = true;
    try {
      await api.post(`/operacion/jornadas/${f.jornada_id}/confirmar-a-mano`,
                     { persona_id: p.persona_id });
      mensaje(t("cen_confirmacion_registrada"));
      marca.className = "marca si";
      marca.textContent = "✓";
      boton.remove();
    } catch (err) { mensaje(err.message, "grave"); boton.disabled = false; }
  };

  return h("div", { clase: "punto" },
    marca,
    h("span", {}, p.nombre,
      p.rol ? h("span", { clase: "gris chico" }, ` · ${p.rol}`) : null,
      sello),
    p.confirmado ? null : boton);
}


function tarjetaDelDia(f) {
  const faltan = f.revision.filter(p => !p.listo);

  return h("div", {
    clase: "tarjeta lisa",
    style: "margin:0 0 12px;border-left:3px solid "
           + (f.listo ? "var(--ok)" : "var(--grave)"),
  },
    h("div", { style: "display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap" },
      h("div", {},
        /* La hora grande es a la que el equipo llega, no a la que
           arranca el servicio: es la que se puede perder. */
        h("div", { style: "font-size:22px;font-weight:650;line-height:1.1" },
          hora(f.equipo_llega)),
        h("div", { clase: "gris chico" },
          `${t("cen_equipo_llega")} · ${t("cen_servicio_inicia")} `
          + `${hora(f.servicio_inicia)}`
          + (f.contra_vuelo ? ` · ${t("cen_contra_vuelo")}` : ""))),
      h("div", { style: "flex:1;min-width:220px" },
        h("b", {}, f.folio),
        h("div", {}, f.cliente || ""),
        h("div", { clase: "gris chico" },
          [f.ejecutivo, f.ciudad, f.consultor].filter(Boolean).join(" · ")),
        f.punto ? h("div", { clase: "chico" }, f.punto) : null),
      h("div", { style: "text-align:right" },
        f.listo
          ? etiqueta(t("cen_todo_listo"), "ok")
          : etiqueta(cuantasFaltan(f.faltan), "grave"),
        h("div", { style: "margin-top:6px" },
          h("a", { clase: "chico", href: rutaDelServicio(f) },
            t("cen_ver_servicio"))))),

    f.personal.length
      ? h("div", { clase: "minimo", style: "margin-top:10px" },
          ...f.personal.map(p => renglonDePersona(f, p)),
          f.unidades.length
            ? h("div", { clase: "punto" },
                h("span", { clase: "placas" }, f.unidades.join(" · ")))
            : null)
      : null,

    /* Lo que falta, con lo que hay que hacer. Un renglon que dice
       "pendiente" obliga a abrir otra pantalla para saber de que se
       trata; a las seis de la tarde eso es el problema. */
    faltan.length
      ? h("ul", { clase: "minimo", style: "margin:10px 0 0;padding-left:18px;display:block" },
          ...faltan.map(p => h("li", { style: "margin-bottom:4px" },
            h("b", {}, t(`cen_p_${p.clave}`)), ": ",
            h("span", { clase: "chico" }, p.que_hacer || ""))))
      : null);
}

/* ------------------------------------------------ 3 · el pulso */

const HITOS = {
  llegada_origen: "cen_hito_llegada_origen",
  contacto_ejecutivo: "cen_hito_contacto_ejecutivo",
  llegada_destino: "cen_hito_llegada_destino",
  salida_ruta: "cen_hito_salida_ruta",
  standby: "cen_hito_standby",
  fin_servicio: "cen_hito_fin_servicio",
};

const TONO_SILENCIO = { verde: "ok", ambar: "alerta", rojo: "grave",
                        sin_reporte: "grave" };

function bandaPulso(p) {
  const caja = h("div", { clase: "tarjeta" },
    conAyuda("h3", `${t("cen_pulso")}${p.cuantos ? ` · ${p.cuantos}` : ""}`,
             "ay_cen_pulso"),
    h("p", { clase: "gris chico", style: "margin:-6px 0 12px" },
      t("cen_pulso_sub")));

  if (!p.cuantos) {
    caja.append(h("div", { clase: "vacio" }, t("cen_pulso_nada")));
    return caja;
  }

  if (p.eventuales.length) caja.append(tablaPulso(p.eventuales));
  if (p.implantados.length) {
    caja.append(
      h("h4", { clase: "grupo" }, t("cen_implantados")),
      tablaPulso(p.implantados));
  }
  return caja;
}

function tablaPulso(filas) {
  const cuerpo = h("tbody");
  for (const f of filas) {
    cuerpo.append(...[h("tr", {},
      h("td", {}, h("b", {}, f.folio),
        h("div", { clase: "gris chico" },
          [f.cliente, f.personal.join(", ")].filter(Boolean).join(" · ")),
        f.unidades.length
          ? h("div", { clase: "placas chico" }, f.unidades.join(" · "))
          : null),
      h("td", {},
        etiqueta(
          f.minutos_callado === null
            ? t("cen_nunca_reporto")
            : t("cen_callado_min").replace("{n}", f.minutos_callado),
          TONO_SILENCIO[f.silencio] || ""),
        f.ultimo_hito
          ? h("div", { clase: "gris chico" },
              `${t("cen_ultimo")}: ${t(HITOS[f.ultimo_hito] || "")} `
              + `${hora(f.ultimo_en)}`)
          : null),
      h("td", { clase: "chico" },
        f.por_entrar_en_extra
          ? etiqueta(`${t("cen_extra")} · ${f.minutos_para_horas_extra} min`,
                     "alerta")
          : null,
        f.alertas_abiertas
          ? h("div", {}, etiqueta(`${f.alertas_abiertas}`, "grave"))
          : null),
      h("td", {},
        h("a", { clase: "chico", href: rutaDelServicio(f) },
          t("cen_ver_servicio")),
        h("div", {}, botonBitacora(f.jornada_id, enLaTabla))))].filter(Boolean));
  }
  return h("table", {}, cuerpo);
}

/* La bitacora se abre DEBAJO del renglon, donde quien la pidio ya esta
   mirando. Abrirla en otra pantalla obligaria a volver para ver el
   siguiente servicio, y lo que se hace en la central es comparar unos
   con otros: la lista es el hilo del trabajo y perderla para leer un
   dia es perder el lugar.

   `colocar` es lo unico que cambia entre un sitio y otro. En una tabla
   el panel tiene que ir en su propio <tr> --meterlo en una celda lo
   mete dentro de una columna-- y en las bandas de "atender ahora", que
   son tarjetas, va detras de la tarjeta. La forma de traerlo, de
   cerrarlo y de no pedirlo dos veces es la misma, y vive aqui una sola
   vez. */
function botonBitacora(jornadaId, colocar) {
  let abierto = null;
  const boton = h("button", { clase: "claro chico", type: "button",
    onclick: async () => {
      if (abierto) {
        abierto.remove();
        abierto = null;
        boton.textContent = t("bit_ver");
        return;
      }
      boton.disabled = true;
      boton.textContent = t("bit_abriendo");
      try {
        const { bitacoraDelDia } = await import("./bitacora.js");
        abierto = colocar(await bitacoraDelDia(jornadaId), boton);
        boton.textContent = t("bit_cerrar");
      } catch (err) {
        boton.textContent = t("bit_ver");
        alert(err.message);
      }
      boton.disabled = false;
    } }, t("bit_ver"));
  return boton;
}

/* En una tabla: un renglon propio que abarca todas las columnas. */
function enLaTabla(panel, boton) {
  const fila = h("tr", {}, h("td", { colspan: "4" }, panel));
  boton.closest("tr").after(fila);
  return fila;
}

/* En "atender ahora": pegada abajo del renglon al que pertenece, para
   que se vea de quien es.

   El selector lleva las dos clases porque las dos bandas estan armadas
   distinto --la del camino es un renglon dentro de una tarjeta, la de
   lo roto es una tarjeta por renglon-- y `closest` devuelve el mas
   cercano de los dos. Con solo `.tarjeta`, la bitacora del camino se
   iba al pie de la banda entera, lejos de la persona que la pidio. */
function enLaTarjeta(panel, boton) {
  const caja = h("div", { clase: "bitacora_pegada" }, panel);
  boton.closest(".renglon_atender, .tarjeta").append(caja);
  return caja;
}

/* ---------------------------------------------- 4 · la semana */

const DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"];

function bandaSemana(tira) {
  const celdas = tira.map(d => h("div", {
    clase: "tarjeta lisa",
    style: "flex:1;min-width:92px;text-align:center;margin:0",
  },
    h("div", { clase: "gris chico" },
      `${DIAS[d.dia_semana]} ${d.fecha.slice(8)}`),
    d.servicios
      ? h("div", {},
          h("div", { style: "font-size:20px;font-weight:650" }, d.servicios),
          h("div", { clase: d.incompletos ? "ambar chico" : "verde chico" },
            t("cen_dia_completos").replace("{c}", d.completos)
              .replace("{t}", d.servicios)))
      : h("div", { clase: "gris chico", style: "padding:6px 0" },
          t("cen_sin_servicios"))));

  return h("div", { clase: "tarjeta" },
    conAyuda("h3", t("cen_semana"), "ay_cen_semana"),
    h("p", { clase: "gris chico", style: "margin:-6px 0 12px" },
      t("cen_semana_sub")),
    h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" }, ...celdas));
}

export function detener() {
  clearInterval(temporizador);
  temporizador = null;
}


/* ------------------------------------------- 5 · dias sin cerrar

   Un dia que se trabajo y que nadie marco se queda abierto, y mientras
   lo este no entra a nomina: alguien que trabajo no cobra por una marca
   que falto. Esta banda es la lista de trabajo para que eso no pase, del
   mas viejo al mas nuevo —el mas viejo es el que mas cerca esta de
   convertirse en un reclamo.

   Si no hay nada, la banda no existe. */

async function bandaSinCerrar(zona) {
  let d;
  try { d = await api.get("/operacion/dias-sin-cerrar"); }
  catch { return null; }
  if (!d.cuantos) return null;

  const caja = h("div", { clase: "tarjeta" },
    h("div", { clase: "encabeza-revision" },
      conAyuda("h3", t("sc_titulo"), "ay_cen_sin_cerrar"),
      h("span", { clase: "etiqueta alerta" },
        t("sc_cuantos").replace("{n}", d.cuantos))),
    h("p", { clase: "sub" }, t("sc_sub")));

  for (const f of d.dias) caja.append(renglonSinCerrar(f, zona));
  return caja;
}

function renglonSinCerrar(f, zona) {
  const dias = Math.floor(f.horas_abierto / 24);
  const antiguedad = dias >= 1
    ? t("sc_dias").replace("{n}", dias)
    : t("sc_horas").replace("{n}", f.horas_abierto);

  const cuerpo = h("div", { clase: "linea-sin-cerrar" },
    h("div", {},
      h("a", { href: rutaDelServicio(f) }, h("b", {}, f.folio)),
      h("div", { clase: "chico gris" },
        `${f.fecha} · ${f.equipo} · ${f.personal.length ? f.personal
          .map(p => p.nombre).join(", ") : t("sc_sin_gente")}`)),
    h("div", { clase: "chico" },
      /* Un dia con contacto y sin fin es una marca que falto. Uno sin
         ninguna marca es un dia del que no se sabe nada, y no es lo
         mismo: el segundo hay que preguntarlo antes de firmarlo. */
      f.arranco
        ? h("span", { clase: "etiqueta alerta" }, t("sc_arranco"))
        : h("span", { clase: "etiqueta grave" }, t("sc_sin_marcas"))),
    h("div", { clase: "chico gris num" }, antiguedad));

  const zonaForm = h("div", {});
  const boton = h("button", { clase: "claro chico", onclick: () => {
    if (zonaForm.firstChild) {
      zonaForm.replaceChildren();
      boton.textContent = t("sc_cerrar");
      return;
    }
    zonaForm.append(formCerrar(f, zona));
    boton.textContent = t("sc_cancelar");
  } }, t("sc_cerrar"));

  return h("div", { clase: "renglon-sin-cerrar" },
    h("div", { clase: "encabeza-revision" }, cuerpo, boton), zonaForm);
}

function formCerrar(f, zona) {
  /* Las horas vienen llenas con las programadas: es lo que casi siempre
     paso, y pedir que alguien las teclee de cero es pedir que invente
     un numero o que se equivoque de dia.

     Casi siempre, no siempre. Cuando el dia arranco DESPUES de la hora
     en que debia terminar --el meet and greet a las 23:09 de un dia
     programado hasta las 20:30, que es un servicio que se recorrio
     entero-- la hora programada es anterior al inicio real, y el
     servidor la rechaza con razon: nada termina antes de empezar. El
     formulario entregaba esa hora igual, o sea que el unico camino para
     cerrar ese dia empezaba por un error.

     Cuando pasa, se propone el inicio real mas lo que dura la
     modalidad: "trabajo sus horas contratadas desde que de verdad
     empezo". Es una propuesta, no un dato --por eso se dice en voz alta
     debajo del campo-- y quien firma la puede cambiar. */
  const arranco = f.inicio_real || f.inicio_programado;
  const duracion = new Date(f.fin_programado) - new Date(f.inicio_programado);
  const tarde = new Date(arranco) >= new Date(f.fin_programado);
  const propuesta = tarde
    ? new Date(Math.min(new Date(arranco).getTime() + duracion, Date.now()))
    : new Date(f.fin_programado);

  const inicio = h("input", { type: "datetime-local",
    value: arranco.slice(0, 16) });
  const fin = h("input", { type: "datetime-local",
    value: new Date(propuesta.getTime()
                    - propuesta.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 16) });
  const motivo = h("textarea", { rows: 2,
    placeholder: t("sc_motivo_ejemplo") });

  const guardar = h("button", {}, t("sc_firmar"));
  const salida = h("div", {});
  const nota = tarde
    ? h("div", { clase: "chico", style: "color:#b8860b;margin-top:6px" },
        t("sc_arranco_tarde").replace("{h}", hora(arranco)))
    : null;

  guardar.addEventListener("click", async () => {
    if (motivo.value.trim().length < 10) {
      return salida.replaceChildren(aviso(t("sc_falta_motivo"), "alerta"));
    }
    guardar.disabled = true;
    try {
      const r = await api.post(
        `/operacion/jornadas/${f.jornada_id}/cerrar-a-mano`, {
          justificacion: motivo.value.trim(),
          inicio_real: inicio.value,
          fin_real: fin.value,
        });
      salida.replaceChildren(aviso(
        t("sc_cerrado").replace("{h}", r.horas)
          .replace("{n}", r.personas), "ok"));
      setTimeout(() => pintar(zona), 1200);
    } catch (e) {
      guardar.disabled = false;
      salida.replaceChildren(aviso(e.message, "grave"));
    }
  });

  return h("div", { clase: "marco-cierre" },
    h("p", { clase: "chico gris" }, t("sc_advertencia")),
    h("div", { clase: "rejilla-revision" },
      h("div", { clase: "campo" }, h("label", {}, t("sc_inicio")), inicio),
      h("div", { clase: "campo" }, h("label", {}, t("sc_fin")), fin, nota)),
    h("div", { clase: "campo" }, h("label", {}, t("sc_motivo")), motivo),
    guardar, salida);
}

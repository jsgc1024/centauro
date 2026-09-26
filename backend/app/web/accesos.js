/* Quién puede entrar al sistema.

   Lo que esta pantalla vino a resolver no es dar de alta gente: es que
   `Usuario.activo` se leía en tres lugares y no se escribía en ninguno.
   El candado existía y nadie tenía la llave: cerrarle la puerta a alguien
   que se fue enojado era un UPDATE a mano en Postgres.

   Y lo segundo, que no se pedía pero se ve solo al juntar los datos: una
   cuenta que nunca se estrenó es un acceso que se dio y no se ocupó, y
   una que lleva meses dormida es una puerta abierta a nombre de alguien
   que quizá ya no está. Ese dato se guardaba desde hace meses y nadie lo
   miraba. */
import { api } from "./api.js";
import { aviso, campo, conAyuda, entrada, fecha, h, hora, lista,
         mensaje } from "./util.js";
import { t } from "./idioma.js";
import { ROLES, nombreDelRol, pestanaPuestos,
         seccionDePermisos } from "./categorias.js";

/* Meses sin entrar a partir de los cuales conviene mirar la cuenta. No
   es un candado, es una ceja levantada. */
const MESES_DORMIDO = 3;

/* Quien entra a la consola, y por eso recibe su invitación por correo.
   El personal de seguridad no: su acceso llega de Odoo y su contraseña
   la pone con el código de cuatro dígitos. Es la misma lista que
   `contrasenas.POR_CORREO` en el servidor. */
const DE_CONSOLA = ROLES.filter(r => r !== "personal_seguridad");

/* "sáb 26 sep 2026 a las 13:10". */
function cuando(iso) {
  return t("acc_cuando").replace("{fecha}", fecha(iso)).replace("{hora}", hora(iso));
}

/* "hace 12 min", "hace 4 meses". La precisión que sirve para decidir: a
   nadie le importa si fueron 97 o 103 días, le importa que son meses. */
function desdeHace(iso) {
  if (!iso) return null;
  const minutos = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (minutos < 60) return t("acc_hace_min").replace("{n}", minutos);
  if (minutos < 60 * 36) {
    return t("acc_hace_horas").replace("{n}", Math.round(minutos / 60));
  }
  const dias = Math.round(minutos / 1440);
  if (dias < 60) return t("acc_hace_dias").replace("{n}", dias);
  return t("acc_hace_meses").replace("{n}", Math.round(dias / 30));
}

function mesesSinEntrar(iso) {
  if (!iso) return null;
  return (Date.now() - new Date(iso)) / (1000 * 60 * 60 * 24 * 30);
}

/* Las personas y los puestos viven en la misma pantalla, no en dos
   entradas del menú. Separarlas obligaría a saltar de una a otra para
   contestar la única pregunta que se hace en voz alta: "¿por qué Beatriz
   no puede?" —que se contesta mirando su renglón y el puesto que trae. */
export async function pantallaAccesos(main) {
  const pestanas = h("div", { clase: "acciones", style: "margin:0 0 4px" });
  const dar = h("div");
  const zona = h("div");
  let vista = "personas";
  let recargarPersonas = async () => {};

  function pintarPestanas() {
    const botones = [
      ["personas", t("cat_personas")], ["puestos", t("cat_puestos")],
    ].map(([clave, texto]) => h("button", {
      type: "button",
      clase: clave === vista ? "chico" : "claro chico",
      onclick: () => { vista = clave; pintarPestanas(); pintarVista(); },
    }, texto));
    /* Dar acceso es de la pestaña de personas: en la de puestos sería
       un botón que no tiene que ver con lo que se está mirando. */
    if (vista === "personas") {
      botones.push(h("button", {
        type: "button", clase: "chico", style: "margin-left:auto",
        onclick: () => abrirDarAcceso(dar, () => recargarPersonas()),
      }, t("acc_dar")));
    }
    pestanas.replaceChildren(...botones);
  }

  async function pintarVista() {
    dar.replaceChildren();
    if (vista === "puestos") return pestanaPuestos(zona);
    recargarPersonas = await pantallaPersonas(zona);
  }

  /* El titulo y su explicacion van sueltos, encima de la tarjeta, como
     en todas las demas pantallas. Metidos DENTRO de la tarjeta, el filo
     azul de esta quedaba a dos centimetros del menu y la explicacion se
     leia pegada a "Operacion · EP eventual · EP implantado": dos barras
     y dos renglones de texto amontonados en el mismo palmo. */
  main.append(
    h("h1", {}, t("acc_titulo")),
    h("p", { clase: "sub" }, t("acc_pie")),
    h("div", { clase: "tarjeta" }, pestanas, dar, zona));

  pintarPestanas();
  await pintarVista();
}

/* Dar acceso: a quién, con qué entra y, si se quiere, su puesto. Le
   llega un correo para que ella misma cree su contraseña; nadie más la
   conoce nunca. */
async function abrirDarAcceso(caja, alTerminar) {
  if (caja.childElementCount) return caja.replaceChildren();
  caja.replaceChildren(h("div", { clase: "gris chico" }, "…"));
  try {
    const [datos, puestos] = await Promise.all([
      api.get("/auth/personas-sin-acceso"), api.get("/auth/categorias")]);
    formularioDarAcceso(caja, datos, puestos, alTerminar);
  } catch (err) {
    caja.replaceChildren(aviso(err.message, "grave"));
  }
}

function formularioDarAcceso(caja, datos, puestos, alTerminar, hecho = "") {
  const persona = lista("persona", [
    { valor: "", texto: t("acc_elige_persona") },
    ...datos.personas.map(p => ({ valor: String(p.persona_id),
                                  texto: `${p.nombre} · ${p.correo}` }))]);
  const rol = lista("rol", DE_CONSOLA.map(r => ({ valor: r, texto: nombreDelRol(r) })));
  rol.value = "consultor";
  /* Los puestos apagados no se ofrecen: para eso se apagaron. */
  const activos = puestos.filter(p => p.activa);
  const puesto = lista("puesto", [{ valor: "", texto: t("acc_sin_puesto") },
    ...activos.map(p => ({ valor: String(p.categoria_id), texto: p.nombre }))]);
  /* Primero el puesto y de ahi el rol (seccion 73): si el puesto dice
     con que rol se entra, el rol queda puesto y quieto. Escoger los dos
     a mano era la forma de dar un monitorista que recibe los avisos de
     finanzas. */
  const notaRol = h("div", { clase: "gris chico" });
  puesto.addEventListener("change", () => {
    const p = activos.find(x => String(x.categoria_id) === puesto.value);
    if (p && p.rol) {
      rol.value = p.rol;
      rol.disabled = true;
      notaRol.textContent = t("acc_rol_lo_pone");
    } else {
      rol.disabled = false;
      notaRol.textContent = "";
    }
  });
  const salida = h("div");

  const mandar = h("button", { type: "button", clase: "chico" }, t("acc_mandar_inv"));
  mandar.disabled = !datos.personas.length;
  mandar.addEventListener("click", async () => {
    if (!persona.value) {
      salida.replaceChildren(aviso(t("acc_falta_persona"), "alerta"));
      return;
    }
    mandar.disabled = true;
    try {
      const r = await api.post("/auth/usuarios", {
        persona_id: Number(persona.value), rol: rol.value,
        categoria_id: puesto.value ? Number(puesto.value) : null });
      const inv = r.invitacion;
      /* Con el correo apagado, quien puede copiar el enlace lo lee aquí
         dicho; quien no, sabe a quién pedírselo. */
      const texto = inv.correo_encendido
        ? t("acc_inv_va").replace("{correo}", r.correo)
            .replace("{cuando}", cuando(inv.expira_en))
        : t(inv.enlace ? "acc_inv_apagado_copia" : "acc_inv_apagado_pide")
            .replace("{correo}", r.correo);
      await alTerminar();
      /* El formulario vuelve limpio --esa persona ya no está en la
         lista-- y con el aviso de lo que pasó. */
      formularioDarAcceso(caja, await api.get("/auth/personas-sin-acceso"),
                          puestos, alTerminar,
                          aviso(texto, inv.correo_encendido ? "ok" : "alerta"));
    } catch (err) {
      salida.replaceChildren(aviso(err.message, "grave"));
      mandar.disabled = false;
    }
  });

  caja.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin:12px 0 4px" },
    h("h3", { style: "margin:0 0 4px" }, t("acc_dar_titulo")),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      datos.correo_encendido
        ? t("acc_dar_pie").replace("{de}", datos.de).replace("{dias}", datos.dias)
        : t("acc_dar_pie_apagado")),
    datos.personas.length ? "" : aviso(t("acc_nadie_sin_acceso"), "alerta"),
    h("div", { clase: "rejilla tres" },
      campo(t("acc_persona"), persona),
      campo(t("acc_puesto_opcional"), puesto),
      h("div", {}, campo(t("acc_entra_como"), rol), notaRol)),
    h("div", { clase: "acciones" }, mandar,
      h("button", { type: "button", clase: "chico claro",
                    onclick: () => caja.replaceChildren() }, t("acc_cancelar"))),
    salida,
    hecho));
}

async function pantallaPersonas(main) {
  const cuerpo = h("div");
  const buscar = entrada("buscar", { placeholder: t("acc_buscar"),
                                     autocomplete: "off" });
  const cerrados = h("input", { type: "checkbox" });

  let todos = [];

  function pintar() {
    const texto = buscar.value.trim().toLowerCase();
    const filas = todos
      .filter(u => cerrados.checked || u.activo)
      .filter(u => !texto
        || (u.nombre || "").toLowerCase().includes(texto)
        || (u.correo || "").toLowerCase().includes(texto));
    cuerpo.replaceChildren(filas.length
      ? h("div", {}, ...filas.map(u => renglon(u, recargar)))
      : h("div", { clase: "gris chico", style: "margin-top:12px" },
          t("acc_nadie")));
  }

  async function recargar() {
    try {
      todos = await api.get("/auth/usuarios");
      pintar();
    } catch (err) {
      cuerpo.replaceChildren(aviso(err.message, "grave"));
    }
  }

  buscar.addEventListener("input", pintar);
  cerrados.addEventListener("change", pintar);

  main.replaceChildren(
    h("div", { style: "margin-top:12px" }, buscar),
    /* La casilla junto a su texto. Con la etiqueta de bloque, la casilla
       tomaba el ancho entero y salía sola en un renglón, encima y
       desfasada del texto que la explica. */
    h("label", { clase: "casilla", style: "margin-top:8px" },
      cerrados, t("acc_ver_cerrados")),
    cuerpo);

  await recargar();
  return recargar;
}

/* Los avisos son lo que esta pantalla aporta de verdad. El resto son
   datos que ya se podían pedir uno por uno. */
function avisosDe(u) {
  const salida = [];
  if (u.persona_de_baja && u.activo) {
    salida.push([t("acc_de_baja"), "grave"]);
  }
  if (!u.estrenado) salida.push([t("acc_sin_estrenar"), "alerta"]);
  const meses = mesesSinEntrar(u.ultimo_acceso);
  if (u.estrenado && u.activo && meses !== null && meses >= MESES_DORMIDO) {
    salida.push([t("acc_dormido"), "alerta"]);
  }
  return salida;
}

function renglon(u, recargar) {
  const zona = h("div");
  const fila = h("div", { clase: "renglon-acceso" },
    h("div", { clase: "quien-acceso" },
      h("div", {},
        h("b", {}, u.nombre || "—"),
        u.activo ? "" : h("span", { clase: "gris chico" },
                          ` · ${t("acc_cerrado")}`)),
      h("div", { clase: "chico gris" }, u.correo)),
    /* Con puesto puesto, el rol ya no es lo que manda. Si el renglón
       siguiera diciendo sólo "Consultor", la lista mentiría justo en la
       pantalla donde se reparte el acceso. */
    h("div", { clase: "chico" }, nombreDelRol(u.rol),
      u.categoria ? h("div", { clase: "gris chico" }, u.categoria) : ""),
    h("div", { clase: "chico gris" },
      u.ultimo_acceso ? desdeHace(u.ultimo_acceso) : t("acc_nunca")),
    h("button", { clase: "claro chico", type: "button",
      onclick: () => abrir(zona, u, recargar) }, "···"));

  const caja = h("div", { clase: u.activo ? "" : "cerrado" }, fila);
  for (const [texto, tono] of avisosDe(u)) caja.append(aviso(texto, tono));
  if (u.rol === "personal_seguridad") {
    caja.append(h("div", { clase: "chico gris", style: "margin-top:2px" },
      t("acc_por_consultor")));
  }
  caja.append(zona);
  return caja;
}

/* Las tres acciones y el rastro, en el mismo lugar. El motivo no es
   obligatorio, pero es lo que se lee un año después cuando alguien
   pregunta por qué se cerró esa cuenta. */
function abrir(zona, u, recargar) {
  if (zona.childElementCount) return zona.replaceChildren();

  const motivo = entrada("motivo", { placeholder: t("acc_motivo") });
  const rol = lista("rol", ROLES.map(r => ({ valor: r, texto: nombreDelRol(r) })));
  rol.value = u.rol;
  /* Con un puesto que dice su rol, el rol es del puesto (seccion 73): se
     cambia cambiandole el puesto, abajo. */
  if (u.rol_por_puesto) rol.disabled = true;

  const acciones = h("div", { clase: "acciones", style: "margin-top:10px" },
    u.rol_por_puesto
      ? h("span", { clase: "gris chico" }, t("acc_rol_por_puesto"))
      : h("button", { clase: "chico claro", type: "button",
      onclick: (e) => mandar(e, `/auth/usuarios/${u.usuario_id}/rol`,
                             { rol: rol.value, motivo: motivo.value.trim() || null },
                             recargar) }, t("acc_cambiar_rol")),
    u.activo
      ? h("button", { clase: "chico", type: "button",
          onclick: (e) => mandar(e, `/auth/usuarios/${u.usuario_id}/desactivar`,
                                 { motivo: motivo.value.trim() || null },
                                 recargar) }, t("acc_desactivar"))
      : h("button", { clase: "chico", type: "button",
          onclick: (e) => mandar(e, `/auth/usuarios/${u.usuario_id}/reactivar`,
                                 { motivo: motivo.value.trim() || null },
                                 recargar) }, t("acc_reactivar")));

  const rastro = h("div", { clase: "gris chico", style: "margin-top:12px" });
  const permisos = h("div");
  const invitacion = h("div");
  zona.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin-top:8px" },
    invitacion,
    h("div", { clase: "rejilla dos" },
      h("div", {}, rol), h("div", {}, motivo)),
    acciones, permisos, rastro));

  /* Quien todavía no estrena su acceso y entra a la consola: cómo va su
     invitación, y cómo mandarle otra. El de campo no tiene: lo suyo es
     el código de cuatro dígitos. */
  if (!u.estrenado && u.activo && u.rol !== "personal_seguridad") {
    bloqueInvitacion(invitacion, u);
  }

  /* Al personal de seguridad no se le reparten permisos: entra desde la
     app y lo único que hace ahí son sus propias jornadas. Ofrecerle 29
     casillas sería ruido en la pantalla y una forma de equivocarse. */
  if (u.rol !== "personal_seguridad") {
    seccionDePermisos(permisos, u.usuario_id, recargar);
  }

  api.get(`/auth/usuarios/${u.usuario_id}/historial`).then(filas => {
    rastro.replaceChildren(
      conAyuda("h4", t("acc_historial"), "ay_acc_historial",
               { style: "margin:0 0 4px" }),
      filas.length
        ? h("div", {}, ...filas.map(f => h("div", { clase: "chico" },
            `${(f.cuando || "").slice(0, 16).replace("T", " ")} · `,
            h("b", {}, f.accion),
            f.antes ? ` · ${f.antes} → ${f.despues}` : "",
            f.quien ? ` · ${f.quien}` : "",
            f.detalle ? h("span", { clase: "gris" }, ` · "${f.detalle}"`) : "")))
        : h("div", {}, t("acc_sin_historial")));
  }).catch(() => rastro.replaceChildren());
}

/* "No le llegó" tiene cuatro respuestas y cada una se arregla distinto:
   está por salir, no salió, el correo todavía no está encendido, o el
   enlace ya venció. Se dice cuál. */
function comoVa(e) {
  const vence = e.expira_en ? cuando(e.expira_en) : "";
  if (e.estado === "ninguna") return t("acc_inv_ninguna");
  if (e.estado === "vencida") return t("acc_inv_vencio").replace("{vence}", vence);
  if (e.estado !== "vigente") return t("acc_inv_no_sirve");
  const c = e.correo;
  if (!c) return t("acc_inv_sin_aviso").replace("{vence}", vence);
  if (c.estado === "enviada") {
    return t("acc_inv_salio").replace("{cuando}", cuando(c.salio_en))
      .replace("{vence}", vence);
  }
  if (c.estado === "pendiente" && !c.error) {
    return t(e.correo_encendido ? "acc_inv_por_salir" : "acc_inv_apagado")
      .replace("{vence}", vence);
  }
  return t("acc_inv_no_salio").replace("{vence}", vence);
}

async function bloqueInvitacion(caja, u) {
  let e;
  try {
    e = await api.get(`/auth/usuarios/${u.usuario_id}/invitacion`);
  } catch (err) {
    caja.replaceChildren(aviso(err.message, "grave"));
    return;
  }
  const aMano = h("div");

  const reenviar = h("button", { type: "button", clase: "chico" },
    t(e.estado === "ninguna" ? "acc_mandar_inv" : "acc_reenviar"));
  reenviar.addEventListener("click", async () => {
    reenviar.disabled = true;
    try {
      const r = await api.post(`/auth/usuarios/${u.usuario_id}/invitacion`);
      mensaje(r.correo_encendido
        ? t("acc_inv_va").replace("{correo}", r.correo)
            .replace("{cuando}", cuando(r.expira_en))
        : t(r.enlace ? "acc_reinv_apagado_copia" : "acc_reinv_apagado_pide")
            .replace("{correo}", r.correo),
        r.correo_encendido ? "ok" : "alerta");
      await bloqueInvitacion(caja, u);
    } catch (err) {
      mensaje(err.message, "grave");
      reenviar.disabled = false;
    }
  });

  const botones = [reenviar];
  /* Copiar el enlace es solo de administración (decisión de Salvador,
     23 sep): con él en la mano se le pone la contraseña a otra persona.
     El servidor lo vuelve a revisar; esto solo decide si se pinta. */
  if (e.puede_copiar && e.estado === "vigente") {
    botones.push(botonCopiar(u, aMano));
  }

  caja.replaceChildren(h("div", { style: "margin:0 0 14px" },
    h("div", { clase: "chico", style: "margin-bottom:8px" },
      h("b", {}, t("acc_su_inv")), h("span", { clase: "gris" }, ` · ${comoVa(e)}`)),
    e.correo && e.correo.error
      ? h("div", { clase: "gris chico", style: "margin:-4px 0 8px" }, e.correo.error)
      : "",
    h("div", { clase: "acciones" }, ...botones),
    h("div", { clase: "gris chico", style: "margin-top:6px" },
      t(e.puede_copiar ? "acc_inv_pie" : "acc_inv_pie_sin_copia")),
    aMano,
    h("hr", { style: "border:0;border-top:1px solid var(--linea);margin:14px 0 0" })));
}

function botonCopiar(u, aMano) {
  const boton = h("button", { type: "button", clase: "chico claro" }, t("acc_copiar"));
  boton.addEventListener("click", async () => {
    boton.disabled = true;
    try {
      const r = await api.get(`/auth/usuarios/${u.usuario_id}/enlace-pendiente`);
      const liga = new URL(r.enlace, location.origin).href;
      try {
        await navigator.clipboard.writeText(liga);
        mensaje(t("acc_copiado"));
      } catch {
        /* Sin permiso para el portapapeles --una conexión sin https, un
           navegador que no deja--: se enseña para copiarlo a mano. */
        aMano.replaceChildren(h("div", { style: "margin-top:8px" },
          h("div", { clase: "gris chico", style: "margin-bottom:4px" },
            t("acc_copia_a_mano")),
          entrada("enlace", { value: liga, readonly: "true", clase: "fijo",
                              onfocus: (ev) => ev.target.select() })));
      }
    } catch (err) {
      mensaje(err.message, "grave");
    }
    boton.disabled = false;
  });
  return boton;
}

async function mandar(e, ruta, cuerpo, recargar) {
  e.target.disabled = true;
  try {
    const r = await api.post(ruta, cuerpo);
    /* Cerrar una puerta no saca a nadie de la operación: si seguía
       asignado a los servicios de mañana, esas jornadas se quedan sin
       él y hay que cubrirlas. */
    const deja = r.jornadas_por_cubrir || [];
    if (deja.length) {
      mensaje(t("acc_deja_dias")
        .replace("{n}", deja.reduce((a, f) => a + f.dias, 0))
        .replace("{s}", deja.length), "alerta");
    } else {
      mensaje(t("acc_hecho"));
    }
    await recargar();
  } catch (err) {
    mensaje(err.message, "grave");
    e.target.disabled = false;
  }
}

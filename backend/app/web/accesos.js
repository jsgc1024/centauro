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
import { api, sesion } from "./api.js";
import { aviso, campo, conAyuda, entrada, etiqueta, fecha, h, hora, lista,
         mensaje } from "./util.js";
import { t } from "./idioma.js";
import { REPARTE, ROLES, apagarLosQueReparten, nombreDelRol, pestanaPuestos,
         seccionDePermisos, traerCatalogo } from "./categorias.js";

/* Meses sin entrar a partir de los cuales conviene mirar la cuenta. No
   es un candado, es una ceja levantada. */
const MESES_DORMIDO = 3;

/* Quien entra a la consola, y por eso recibe su invitación por correo.
   El personal de seguridad no: su acceso llega de Odoo y su contraseña
   la pone con el código de cuatro dígitos. Es la misma lista que
   `contrasenas.POR_CORREO` en el servidor. */
const DE_CONSOLA = ROLES.filter(r => r !== "personal_seguridad");

/* Los roles que quien mira puede dar (sección 83). Dirección general y
   administración sólo las da Dirección general, y también los roles que
   de fábrica reparten accesos: el poder de repartirlos lo da ella. El
   servidor lo vuelve a revisar; esto decide qué se ofrece. */
async function rolesQuePuedeDar() {
  if ((sesion.usuario || {}).es_direccion) return DE_CONSOLA;
  const cat = await traerCatalogo();
  const reparten = new Set((cat.find(a => a.actividad === REPARTE) || {}).roles || []);
  return DE_CONSOLA.filter(r => r !== "admin" && r !== "director_general"
                                && !reparten.has(r));
}

/* El rol que pone un puesto, aunque no esté entre los que quien mira
   puede escoger a mano: el puesto de Capacitación entra como Recursos
   Humanos y no reparte accesos, y lo da cualquiera de Accesos. */
function ponerRol(select, rol) {
  if (![...select.options].some(o => o.value === rol)) {
    select.append(h("option", { value: rol }, nombreDelRol(rol)));
  }
  select.value = rol;
}

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

/* Con el correo apagado, quien puede copiar el enlace lo lee aquí
   dicho; quien no, sabe a quién pedírselo. */
function textoDeInvitacion(r) {
  const inv = r.invitacion;
  return inv.correo_encendido
    ? t("acc_inv_va").replace("{correo}", r.correo)
        .replace("{cuando}", cuando(inv.expira_en))
    : t(inv.enlace ? "acc_inv_apagado_copia" : "acc_inv_apagado_pide")
        .replace("{correo}", r.correo);
}

/* Dar acceso: a quién, con qué entra y, si se quiere, su puesto. Le
   llega un correo para que ella misma cree su contraseña; nadie más la
   conoce nunca. */
async function abrirDarAcceso(caja, alTerminar) {
  if (caja.childElementCount) return caja.replaceChildren();
  caja.replaceChildren(h("div", { clase: "gris chico" }, "…"));
  try {
    const [datos, puestos, roles] = await Promise.all([
      api.get("/auth/personas-sin-acceso"), api.get("/auth/categorias"),
      rolesQuePuedeDar()]);
    formularioDarAcceso(caja, datos, puestos, roles, alTerminar);
  } catch (err) {
    caja.replaceChildren(aviso(err.message, "grave"));
  }
}

function formularioDarAcceso(caja, datos, puestos, roles, alTerminar, hecho = "") {
  const persona = lista("persona", [
    { valor: "", texto: t("acc_elige_persona") },
    ...datos.personas.map(p => ({ valor: String(p.persona_id),
                                  texto: `${p.nombre} · ${p.correo}` }))]);
  const rol = lista("rol", roles.map(r => ({ valor: r, texto: nombreDelRol(r) })));
  rol.value = "consultor";
  /* Los puestos apagados no se ofrecen: para eso se apagaron. */
  const activos = puestos.filter(p => p.activa);
  const puesto = lista("puesto", [{ valor: "", texto: t("acc_sin_puesto") },
    ...activos.map(p => ({ valor: String(p.categoria_id), texto: p.nombre }))]);
  apagarLosQueReparten(puesto, activos);
  /* Primero el puesto y de ahi el rol (seccion 73): si el puesto dice
     con que rol se entra, el rol queda puesto y quieto. Escoger los dos
     a mano era la forma de dar un monitorista que recibe los avisos de
     finanzas. */
  const notaRol = h("div", { clase: "gris chico" });
  puesto.addEventListener("change", () => {
    const p = activos.find(x => String(x.categoria_id) === puesto.value);
    if (p && p.rol) {
      ponerRol(rol, p.rol);
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
      const texto = textoDeInvitacion(r);
      await alTerminar();
      /* El formulario vuelve limpio --esa persona ya no está en la
         lista-- y con el aviso de lo que pasó. */
      formularioDarAcceso(caja, await api.get("/auth/personas-sin-acceso"),
                          puestos, roles, alTerminar,
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
      campo(t("acc_persona"), persona, { obligatorio: true }),
      campo(t("acc_puesto_opcional"), puesto),
      h("div", {}, campo(t("acc_entra_como"), rol, { obligatorio: true }), notaRol)),
    h("div", { clase: "acciones" }, mandar,
      h("button", { type: "button", clase: "chico claro",
                    onclick: () => caja.replaceChildren() }, t("acc_cancelar"))),
    salida,
    hecho));
}

/* Las personas, en tres pestañas (sección 74): quien ya tiene acceso;
   la oficina que llegó de Odoo y todavía no lo tiene, con el puesto que
   sugiere su puesto de Odoo; y quien en Odoo no tiene correo de trabajo,
   que no puede entrar hasta que Recursos Humanos se lo ponga allá. */
async function pantallaPersonas(main) {
  const pestanas = h("div", { clase: "pestanas", style: "margin:12px 0 10px" });
  const zona = h("div");
  const cuerpo = h("div");
  const buscar = entrada("buscar", { placeholder: t("acc_buscar"),
                                     autocomplete: "off" });
  const cerrados = h("input", { type: "checkbox" });
  /* Quienes ya entraron y quienes no (Salvador, 3 oct, seccion 131): el
     dato estaba en cada renglon y no habia como quedarse solo con los
     que nunca han entrado, o con los que llevan meses dormidos. */
  const entraron = lista("entraron", [
    { valor: "", texto: t("acc_f_todos") },
    { valor: "si", texto: t("acc_f_entraron") },
    { valor: "no", texto: t("acc_f_nunca") },
    { valor: "dormidos", texto: t("acc_f_dormidos").replace("{m}", MESES_DORMIDO) },
  ]);
  /* Y por pais (Salvador, 3 oct): el de la ciudad de cada quien. Las
     opciones salen de la lista misma; quien no tiene ciudad --un acceso
     de oficina sin ficha-- queda en «Sin país». */
  const pais = lista("pais", [{ valor: "", texto: t("acc_f_pais_todos") }]);
  let sub = "con";
  let todos = [];
  let oficina = { sin_acceso: [], sin_correo: [], leido_en: null };
  let puestos = [];
  let roles = [];

  function pintarPestanas() {
    const boton = (clave, texto) => h("button", {
      type: "button", clase: `pestana ${sub === clave ? "activa" : ""}`.trim(),
      onclick: () => { sub = clave; pintarPestanas(); pintarSub(); } }, texto);
    pestanas.replaceChildren(
      boton("con", t("ofi_tab_con").replace("{n}", todos.filter(u => u.activo).length)),
      boton("oficina", t("ofi_tab_oficina").replace("{n}", oficina.sin_acceso.length)),
      boton("sin_correo", t("ofi_tab_sin_correo").replace("{n}", oficina.sin_correo.length)));
  }

  const yaEntro = (u) => !!u.ultimo_acceso;
  const dormido = (u) => {
    const meses = mesesSinEntrar(u.ultimo_acceso);
    return yaEntro(u) && meses !== null && meses >= MESES_DORMIDO;
  };
  const porEntrada = (u) => {
    const cual = entraron.value;
    if (cual === "si") return yaEntro(u);
    if (cual === "no") return !yaEntro(u);
    if (cual === "dormidos") return dormido(u);
    return true;
  };

  function ponerPaises() {
    const antes = pais.value;
    const vistos = new Map();
    for (const u of todos) {
      const clave = u.pais_id ? String(u.pais_id) : "sin";
      if (!vistos.has(clave)) vistos.set(clave, u.pais || t("acc_f_sin_pais"));
    }
    pais.replaceChildren(h("option", { value: "" }, t("acc_f_pais_todos")),
      ...[...vistos.entries()]
        .sort((a, b) => (a[0] === "sin") - (b[0] === "sin") || a[1].localeCompare(b[1]))
        .map(([clave, nombre]) => h("option", { value: clave }, nombre)));
    if ([...pais.options].some(o => o.value === antes)) pais.value = antes;
    /* Con un solo pais en la lista no hay nada que separar. */
    pais.parentElement && (pais.parentElement.hidden = vistos.size < 2);
  }

  const delPais = (u) => !pais.value
    || (pais.value === "sin" ? !u.pais_id : String(u.pais_id) === pais.value);

  function pintarLista() {
    const texto = buscar.value.trim().toLowerCase();
    const visibles = todos.filter(u => cerrados.checked || u.activo).filter(delPais);
    /* Las cuentas en cada opcion, para leer de un vistazo cuantos no han
       entrado sin tener que escogerla. */
    const n = { si: visibles.filter(yaEntro).length,
                no: visibles.filter(u => !yaEntro(u)).length,
                dormidos: visibles.filter(dormido).length };
    for (const o of entraron.options) {
      if (o.value) o.textContent = o.textContent.replace(/ \(\d+\)$/, "") + ` (${n[o.value]})`;
    }
    const filas = visibles
      .filter(porEntrada)
      .filter(u => !texto
        || (u.nombre || "").toLowerCase().includes(texto)
        || (u.correo || "").toLowerCase().includes(texto));
    cuerpo.replaceChildren(filas.length
      ? h("div", {}, ...filas.map(u => renglon(u, recargar, roles)))
      : h("div", { clase: "gris chico", style: "margin-top:12px" },
          t(entraron.value && !texto ? "acc_nadie_asi" : "acc_nadie")));
  }

  function pintarSub() {
    if (sub === "oficina") {
      zona.replaceChildren(
        h("p", { clase: "gris chico", style: "margin:0 0 10px" }, t("ofi_pie")),
        oficina.leido_en ? "" : aviso(t("ofi_sin_lectura"), "alerta"),
        oficina.sin_acceso.length
          ? h("div", {}, ...oficina.sin_acceso.map(
              p => renglonOficina(p, puestos, roles, recargar)))
          : h("div", { clase: "gris chico" },
              oficina.leido_en ? t("ofi_nadie") : ""));
      return;
    }
    if (sub === "sin_correo") {
      zona.replaceChildren(
        h("p", { clase: "gris chico", style: "margin:0 0 10px" },
          t("ofi_sin_correo_pie")),
        oficina.leido_en
          ? h("div", { clase: "gris chico", style: "margin:0 0 8px" },
              t("ofi_segun_lectura").replace("{cuando}", cuando(oficina.leido_en)))
          : aviso(t("ofi_sin_lectura"), "alerta"),
        oficina.sin_correo.length
          ? h("div", {}, ...oficina.sin_correo.map(x =>
              h("div", { clase: "renglon-acceso de-oficina" },
                h("div", { clase: "quien-acceso" }, h("b", {}, x.nombre || "—")),
                h("div", { clase: "chico" }, x.puesto || "—",
                  h("div", { clase: "gris" }, x.area || "")),
                h("div"), h("div"))))
          : h("div", { clase: "gris chico" },
              oficina.leido_en ? t("ofi_todos_con_correo") : ""));
      return;
    }
    zona.replaceChildren(
      h("div", { clase: "rejilla tres" }, buscar,
        campo(t("acc_f_pais"), pais),
        campo(t("acc_f_titulo"), entraron)),
      /* La casilla junto a su texto. Con la etiqueta de bloque, la casilla
         tomaba el ancho entero y salía sola en un renglón, encima y
         desfasada del texto que la explica. */
      h("label", { clase: "casilla", style: "margin-top:8px" },
        cerrados, t("acc_ver_cerrados")),
      cuerpo);
    ponerPaises();
    pintarLista();
  }

  async function recargar() {
    try {
      [todos, oficina, puestos, roles] = await Promise.all([
        api.get("/auth/usuarios"), api.get("/auth/oficina"),
        api.get("/auth/categorias"), rolesQuePuedeDar()]);
      pintarPestanas();
      pintarSub();
    } catch (err) {
      zona.replaceChildren(aviso(err.message, "grave"));
    }
  }

  buscar.addEventListener("input", pintarLista);
  cerrados.addEventListener("change", pintarLista);
  entraron.addEventListener("change", pintarLista);
  pais.addEventListener("change", pintarLista);

  main.replaceChildren(pestanas, zona);
  await recargar();
  return recargar;
}

/* Alguien de oficina que llegó de Odoo y todavía no entra: su puesto de
   Odoo y el de Centauro que eso sugiere. Dar el acceso es un clic, y el
   puesto sugerido se puede cambiar antes (sección 74). */
/* Si ese puesto sólo lo da Dirección general y quien mira no es ella
   (sección 83). */
function loDaDireccion(puestos, categoriaId) {
  if ((sesion.usuario || {}).es_direccion || !categoriaId) return false;
  const x = puestos.find(y => y.categoria_id === categoriaId);
  return !!(x && x.reparte);
}

function renglonOficina(p, puestos, roles, recargar) {
  const zona = h("div");
  const s = p.sugerido;
  const deDireccion = !!(s && loDaDireccion(puestos, s.categoria_id));
  const fila = h("div", { clase: "renglon-acceso de-oficina" },
    h("div", { clase: "quien-acceso" },
      h("div", {}, h("b", {}, p.nombre)),
      h("div", { clase: "chico gris" }, p.correo)),
    h("div", { clase: "chico" }, p.puesto_odoo || "—",
      h("div", { clase: "gris" }, p.area_odoo || "")),
    h("div", { clase: "chico" }, s
      ? h("span", { clase: "sugerido" }, s.nombre)
      : etiqueta(t("ofi_sin_sugerido"), "alerta")),
    h("button", { clase: "chico", type: "button", onclick: () => {
      if (zona.childElementCount) return zona.replaceChildren();
      zona.replaceChildren(formularioOficina(p, puestos, roles, zona, recargar));
    } }, t("ofi_dar")));
  return h("div", {}, fila,
    s ? "" : h("div", { clase: "chico gris", style: "margin:2px 0 6px" },
               t("ofi_sin_sugerido_pie")),
    deDireccion ? h("div", { clase: "chico gris", style: "margin:2px 0 6px" },
                    t("ofi_sugerido_direccion")) : "",
    zona);
}

function formularioOficina(p, puestos, roles, zona, recargar) {
  const activos = puestos.filter(x => x.activa);
  const s = p.sugerido;
  const puesto = lista("puesto", [{ valor: "", texto: t("acc_sin_puesto") },
    ...activos.map(x => ({ valor: String(x.categoria_id), texto: x.nombre }))]);
  apagarLosQueReparten(puesto, activos);
  const rol = lista("rol", roles.map(r => ({ valor: r, texto: nombreDelRol(r) })));
  rol.value = "consultor";
  const notaRol = h("div", { clase: "gris chico" });
  function alPuesto() {
    const x = activos.find(y => String(y.categoria_id) === puesto.value);
    if (x && x.rol) {
      ponerRol(rol, x.rol);
      rol.disabled = true;
      notaRol.textContent = t("acc_rol_lo_pone");
    } else {
      rol.disabled = false;
      notaRol.textContent = "";
    }
  }
  puesto.addEventListener("change", alPuesto);
  /* Lo sugerido, ya puesto. Dirección general y administración ya no se
     sugieren (sección 83), y el puesto que reparte accesos sólo se deja
     puesto si quien mira puede darlo. */
  if (s && s.tipo === "puesto" && s.categoria_id
      && !loDaDireccion(puestos, s.categoria_id)) {
    puesto.value = String(s.categoria_id);
  }
  alPuesto();

  const salida = h("div");
  const mandar = h("button", { type: "button", clase: "chico" }, t("acc_mandar_inv"));
  mandar.addEventListener("click", async () => {
    mandar.disabled = true;
    try {
      const r = await api.post("/auth/usuarios", {
        persona_id: p.persona_id, rol: rol.value,
        categoria_id: puesto.value ? Number(puesto.value) : null });
      mensaje(textoDeInvitacion(r), r.invitacion.correo_encendido ? "ok" : "alerta");
      await recargar();
    } catch (err) {
      salida.replaceChildren(aviso(err.message, "grave"));
      mandar.disabled = false;
    }
  });
  return h("div", { clase: "tarjeta lisa", style: "margin:6px 0 10px" },
    h("div", { clase: "rejilla dos" },
      campo(t("acc_puesto_opcional"), puesto),
      h("div", {}, campo(t("acc_entra_como"), rol), notaRol)),
    h("div", { clase: "acciones" }, mandar,
      h("button", { type: "button", clase: "chico claro",
                    onclick: () => zona.replaceChildren() }, t("acc_cancelar"))),
    salida);
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

function renglon(u, recargar, roles) {
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
      u.categoria ? h("div", { clase: "gris chico" }, u.categoria) : "",
      u.pais ? h("div", { clase: "gris chico" }, u.pais) : ""),
    h("div", { clase: "chico gris" },
      u.ultimo_acceso ? desdeHace(u.ultimo_acceso) : t("acc_nunca")),
    h("button", { clase: "claro chico", type: "button",
      onclick: () => abrir(zona, u, recargar, roles) }, "···"));

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
function abrir(zona, u, recargar, roles) {
  if (zona.childElementCount) return zona.replaceChildren();

  /* Sección 83. Su propio acceso nadie lo cambia; el de Dirección
     general y administración, y el de quien reparte accesos, sólo
     Dirección general. A quien reparte sí se le puede cerrar la puerta
     cuando se va. */
  const quien = sesion.usuario || {};
  const esYo = u.usuario_id === quien.usuario_id;
  const alto = u.alto && !quien.es_direccion;
  const reparte = u.reparte && !quien.es_direccion;
  const bloqueo = esYo ? t("acc_es_tu_acceso")
    : alto ? t("acc_solo_direccion_alto")
    : reparte ? t("acc_reparte_direccion") : "";

  const motivo = entrada("motivo", { placeholder: t("acc_motivo") });
  const deRol = roles.includes(u.rol) ? roles : [...roles, u.rol];
  const rol = lista("rol", deRol.map(r => ({ valor: r, texto: nombreDelRol(r) })));
  rol.value = u.rol;
  /* Con un puesto que dice su rol, el rol es del puesto (seccion 73): se
     cambia cambiandole el puesto, abajo. */
  if (u.rol_por_puesto || bloqueo) rol.disabled = true;

  const cerrarOAbrir = (esYo || alto) ? "" : u.activo
    ? h("button", { clase: "chico", type: "button",
        onclick: (e) => mandar(e, `/auth/usuarios/${u.usuario_id}/desactivar`,
                               { motivo: motivo.value.trim() || null },
                               recargar) }, t("acc_desactivar"))
    : h("button", { clase: "chico", type: "button",
        onclick: (e) => mandar(e, `/auth/usuarios/${u.usuario_id}/reactivar`,
                               { motivo: motivo.value.trim() || null },
                               recargar) }, t("acc_reactivar"));
  const cambiarRol = bloqueo ? "" : u.rol_por_puesto
    ? h("span", { clase: "gris chico" }, t("acc_rol_por_puesto"))
    : h("button", { clase: "chico claro", type: "button",
        onclick: (e) => mandar(e, `/auth/usuarios/${u.usuario_id}/rol`,
                               { rol: rol.value, motivo: motivo.value.trim() || null },
                               recargar) }, t("acc_cambiar_rol"));
  const acciones = h("div", { clase: "acciones", style: "margin-top:10px" },
    cambiarRol, cerrarOAbrir);

  const rastro = h("div", { clase: "gris chico", style: "margin-top:12px" });
  const permisos = h("div");
  const invitacion = h("div");
  zona.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin-top:8px" },
    invitacion,
    bloqueo ? aviso(bloqueo, "alerta") : "",
    h("div", { clase: "rejilla dos" },
      h("div", {}, rol), (cambiarRol || cerrarOAbrir) ? h("div", {}, motivo) : h("div")),
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
  if (u.rol !== "personal_seguridad" && !alto) {
    seccionDePermisos(permisos, u.usuario_id, recargar,
                      (esYo || reparte) ? bloqueo : "");
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
    /* El titular de servicios vivos no se va (decision 13, seccion 105):
       se dicen cuales, para ir a cambiarlos desde su ficha. */
    const suyos = (err.detalle || {}).servicios || [];
    if (suyos.length) {
      mensaje(t("acc_titular_de").replace("{n}", suyos.length)
                .replace("{f}", suyos.map(s => s.folio).join(", ")), "alerta");
    }
    e.target.disabled = false;
  }
}

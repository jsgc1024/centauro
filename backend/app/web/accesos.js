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
import { aviso, conAyuda, entrada, h, lista, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { ROLES, nombreDelRol, pestanaPuestos,
         seccionDePermisos } from "./categorias.js";

/* Meses sin entrar a partir de los cuales conviene mirar la cuenta. No
   es un candado, es una ceja levantada. */
const MESES_DORMIDO = 3;

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
  const zona = h("div");
  let vista = "personas";

  function pintarPestanas() {
    pestanas.replaceChildren(...[
      ["personas", t("cat_personas")], ["puestos", t("cat_puestos")],
    ].map(([clave, texto]) => h("button", {
      type: "button",
      clase: clave === vista ? "chico" : "claro chico",
      onclick: () => { vista = clave; pintarPestanas(); pintarVista(); },
    }, texto)));
  }

  function pintarVista() {
    if (vista === "puestos") return pestanaPuestos(zona);
    return pantallaPersonas(zona);
  }

  /* El titulo y su explicacion van sueltos, encima de la tarjeta, como
     en todas las demas pantallas. Metidos DENTRO de la tarjeta, el filo
     azul de esta quedaba a dos centimetros del menu y la explicacion se
     leia pegada a "Operacion · EP eventual · EP implantado": dos barras
     y dos renglones de texto amontonados en el mismo palmo. */
  main.append(
    h("h1", {}, t("acc_titulo")),
    h("p", { clase: "sub" }, t("acc_pie")),
    h("div", { clase: "tarjeta" }, pestanas, zona));

  pintarPestanas();
  await pintarVista();
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
    h("label", { clase: "chico", style: "display:block;margin-top:8px" },
      cerrados, " ", t("acc_ver_cerrados")),
    cuerpo);

  await recargar();
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

  const acciones = h("div", { clase: "acciones", style: "margin-top:10px" },
    h("button", { clase: "chico claro", type: "button",
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
  zona.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin-top:8px" },
    h("div", { clase: "rejilla dos" },
      h("div", {}, rol), h("div", {}, motivo)),
    acciones, permisos, rastro));

  /* Al personal de seguridad no se le reparten permisos: entra desde la
     app y lo único que hace ahí son sus propias jornadas. Ofrecerle 29
     casillas sería ruido en la pantalla y una forma de equivocarse. */
  if (u.rol !== "personal_seguridad") seccionDePermisos(permisos, u.usuario_id);

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

/* Lo que se abre sin haber entrado: la página del enlace que llega por
   correo --crear la contraseña la primera vez, o poner una nueva si se
   olvidó-- y la que pide ese enlace.

   Son las únicas pantallas de la consola que no piden sesión, igual que
   sus endpoints. Y viven en la misma tarjeta de la entrada, con la misma
   marca: quien abre un enlace desde un correo tiene que reconocer en un
   segundo que llegó a donde debía, y no a una página que se le parece.

   El token viaja detrás del "#": lo que va ahí el navegador no lo manda
   al servidor, así que no queda escrito en ninguna bitácora del camino.
   Al servidor se le pregunta en el cuerpo de la petición, por lo mismo. */
import { api } from "./api.js";
import { aviso, campo, entrada, h } from "./util.js";
import { ponerIdioma, t } from "./idioma.js";
import { nombreDelRol } from "./categorias.js";

/* La tarjeta de la entrada, con lo que toque adentro. `op` la da el
   armazón: la marca de arriba y el camino de vuelta a la entrada. */
function tarjeta(cuerpo, op, ...hijos) {
  const f = h("form", { onsubmit: (e) => e.preventDefault() },
              ...op.cabecera(), ...hijos);
  cuerpo.replaceChildren(h("div", { clase: "entrada" }, f));
  return f;
}

/* Sin señal no hay respuesta del servidor que enseñar: se dice qué pasa
   en el idioma de quien mira, no el "sin_red" del cliente. */
function porQue(err) {
  return err.codigo === 0 ? t("cc_sin_red") : err.message;
}

function volver(op, correo = "") {
  return h("div", { clase: "centro" },
    h("button", { type: "button", clase: "enlace",
                  onclick: () => op.irAEntrada(correo) }, t("cc_volver")));
}

/* ------------------------------------------------ la página del enlace */

/* Por qué un enlace ya no sirve. Cada caso se arregla distinto, así que
   se dice cuál es. */
const MUERTO = {
  vencido: "cc_vencido",
  usado: "cc_usado",
  anulado: "cc_anulado",
  cerrado: "cc_cerrado",
  invalido: "cc_invalido",
};

export async function pantallaEnlace(cuerpo, op, token) {
  tarjeta(cuerpo, op, h("p", { clase: "gris" }, t("cc_revisando")));
  let enlace;
  try {
    enlace = await api.post("/auth/enlace", { token });
  } catch (err) {
    tarjeta(cuerpo, op, aviso(porQue(err), "grave"), volver(op));
    return;
  }
  if (enlace.estado !== "vivo") {
    muerto(cuerpo, op, enlace.estado);
    return;
  }
  /* En el idioma en que le llegó el correo: el de su país. */
  if (enlace.idioma) ponerIdioma(enlace.idioma);
  formulario(cuerpo, op, token, enlace);
}

/* "Es tu acceso a Centauro como {rol}.", con el rol en negritas. */
function conRol(texto, rol) {
  const [antes, despues = ""] = texto.split("{rol}");
  return [antes, h("b", {}, rol), despues];
}

function formulario(cuerpo, op, token, enlace) {
  const primera = enlace.tipo === "invitacion";
  /* El correo va puesto y no se cambia: es de quien recibió el enlace.
     Y va como usuario para que el navegador guarde la contraseña nueva
     junto al correo correcto. */
  const correo = entrada("correo", { value: enlace.correo, readonly: "true",
                                     clase: "fijo", autocomplete: "username" });
  const nueva = entrada("nueva", { type: "password", required: "true",
                                   autocomplete: "new-password" });
  const otra = entrada("otra", { type: "password", required: "true",
                                 autocomplete: "new-password" });
  const error = h("div");
  const boton = h("button", { type: "submit" }, t("cc_guardar"));

  const f = tarjeta(cuerpo, op,
    h("h2", {}, t(primera ? "cc_crear_titulo" : "cc_nueva_titulo")),
    h("p", { clase: "gris" }, ...(primera
      ? conRol(t("cc_tu_acceso"), nombreDelRol(enlace.rol))
      : [t("cc_nueva_sub")])),
    campo(t("cc_tu_correo"), correo),
    campo(t("cc_nueva"), nueva),
    campo(t("cc_repite"), otra),
    /* Las reglas, dichas antes de escribir y no después del error: son
       las mismas que revisa el servidor. */
    h("p", { clase: "gris chico" }, t("cc_reglas")),
    error,
    boton);

  f.addEventListener("submit", async () => {
    error.replaceChildren();
    if (nueva.value !== otra.value) {
      error.replaceChildren(aviso(t("cc_no_coinciden"), "grave"));
      return;
    }
    boton.disabled = true;
    try {
      const r = await api.post("/auth/establecer-contrasena",
                               { token, contrasena: nueva.value });
      listo(cuerpo, op, r.correo);
    } catch (err) {
      /* El enlace se murió mientras la escribía: venció, se pidió otro o
         le cerraron el acceso. Se vuelve a preguntar y la página dice
         cuál de todos, en vez de un error suelto. */
      if ([403, 404, 409].includes(err.codigo)) {
        pantallaEnlace(cuerpo, op, token);
        return;
      }
      error.replaceChildren(aviso(porQue(err), "grave"));
      boton.disabled = false;
    }
  });
}

function listo(cuerpo, op, correo) {
  tarjeta(cuerpo, op,
    aviso(h("b", {}, t("cc_listo")), "ok"),
    h("p", { clase: "gris" }, t("cc_listo_sub")),
    /* A la entrada con su correo ya escrito. Y sin la sesión que hubiera
       abierta en esta computadora: la de esta cuenta ya se cerró con la
       contraseña nueva, y si era la de otra persona, quien sigue es
       quien acaba de crear la suya. */
    h("button", { type: "button", onclick: () => op.irAEntrada(correo, true) },
      t("cc_entrar")));
}

function muerto(cuerpo, op, estado) {
  const cerrado = estado === "cerrado";
  tarjeta(cuerpo, op,
    aviso(h("b", {}, t(MUERTO[estado] || "cc_invalido")), "grave"),
    h("p", { clase: "gris" }, t(cerrado ? "cc_cerrado_sub" : "cc_muerto_sub")),
    cerrado ? null : h("p", { clase: "gris chico" },
      t("cc_muerto_olvido"), h("br"), t("cc_muerto_primera")),
    h("button", { type: "button", clase: "claro",
                  onclick: () => op.irAEntrada() }, t("cc_ir_entrada")));
}

/* ------------------------------------------------ olvidé mi contraseña */

export function pantallaOlvide(cuerpo, op) {
  const correo = entrada("correo", { type: "email", required: "true",
                                     autocomplete: "username",
                                     value: op.correo || null });
  const error = h("div");
  const boton = h("button", { type: "submit" }, t("cc_olv_mandar"));

  const f = tarjeta(cuerpo, op,
    h("h2", {}, t("cc_olv_titulo")),
    h("p", { clase: "gris" }, t("cc_olv_sub")),
    campo(t("correo"), correo),
    error,
    boton,
    volver(op, op.correo));

  f.addEventListener("submit", async () => {
    error.replaceChildren();
    boton.disabled = true;
    const escrito = correo.value.trim();
    try {
      const r = await api.post("/auth/recuperar", { correo: escrito });
      pedido(cuerpo, op, r, escrito);
    } catch (err) {
      error.replaceChildren(aviso(porQue(err), "grave"));
      boton.disabled = false;
    }
  });
}

/* Lo mismo exista o no la cuenta: la pantalla no puede servir para
   averiguar quién tiene acceso. Lo que sí cambia es si el correo está
   encendido, que no es un dato de nadie: mientras no lo esté, se dice
   que el enlace lo entrega administración. */
function pedido(cuerpo, op, r, escrito) {
  const texto = t(r.por_correo ? "cc_olv_listo" : "cc_olv_listo_apagado")
    .replace("{de}", r.de || "").replace("{horas}", r.horas);
  tarjeta(cuerpo, op,
    aviso([h("b", {}, t(r.por_correo ? "cc_olv_revisa" : "cc_olv_pedido")),
           " ", texto], "ok"),
    /* El de campo no recupera por correo, y aquí no se le puede decir
       "tu cuenta es de campo" sin decir que existe. Se le dice a todos. */
    h("p", { clase: "gris chico" }, t("cc_olv_campo")),
    volver(op, escrito));
}

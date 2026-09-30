/* Entrar con huella o cara, en la consola (30 sep). Lo que habla con el
   telefono y los textos viven en huella.js; aqui, lo que se pinta: el
   boton de la entrada, el "Hola, Salvador" de quien ya la usa en este
   equipo, la pregunta de una sola vez al entrar con contrasena y la
   pantalla para verla y quitarla (menu de su nombre). */
import * as huella from "./huella.js";
import { aviso, campo, entrada, h, mensaje } from "./util.js";

const HUELLA_SVG = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
  + 'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
  + 'style="vertical-align:-4px;margin-right:8px" aria-hidden="true">'
  + '<path d="M12 11c0 3.5-.7 6.3-2 8.5"/><path d="M8.5 7.5A5 5 0 0 1 17 11c0 1.3-.1 2.6-.3 3.8"/>'
  + '<path d="M5.3 9A8 8 0 0 1 20 11c0 2-.2 3.6-.6 5"/><path d="M8.5 11a3.5 3.5 0 0 1 7 0c0 3-.4 5.6-1.3 7.7"/>'
  + '<path d="M4 14.5c.5-1 .7-2.2.7-3.5"/></svg>';

function icono(tamano = 20) {
  /* Solo el ancho y el alto: el dibujo trae numeros propios. */
  const lado = String(tamano);
  return h("span", { html: HUELLA_SVG.replace('width="20" height="20"',
                                               'width="' + lado + '" height="' + lado + '"') });
}

/* El boton que entra. `alEntrar` es lo mismo que hace la consola despues
   de entrar con contrasena. `correo` puede ser la caja del correo. */
export function botonEntrar({ alEntrar, correo = null, error, claro = false, texto }) {
  const b = h("button", {
    type: "button", clase: claro ? "claro" : null,
    onclick: async () => {
      b.disabled = true;
      error.replaceChildren();
      try {
        await huella.entrar(correo && correo.value ? correo.value.trim().toLowerCase() : null);
        await alEntrar();
      } catch (err) {
        error.replaceChildren(aviso(err.message, "grave"));
        b.disabled = false;
      }
    } }, icono(), texto || huella.th("boton"));
  return b;
}

/* Debajo de "Entrar": una raya con una "o" y el boton claro. */
export function separador() {
  return h("div", { style: "display:flex;align-items:center;gap:10px;margin:14px 0 8px;"
                         + "color:#8a8fa3;font-size:12px" },
    h("span", { style: "flex:1;height:1px;background:#e3e5ea" }),
    huella.th("o"),
    h("span", { style: "flex:1;height:1px;background:#e3e5ea" }));
}

/* Quien ya entra con huella en este equipo: "Hola, Salvador" y un boton.
   La contrasena y "no soy yo" quedan abajo, chicos. */
export function saludo({ portada, alEntrar, usarContrasena, cambiarPersona }) {
  const r = huella.recordado();
  const error = h("div", { clase: "error" });
  return h("form", { onsubmit: (e) => e.preventDefault() },
    portada,
    h("p", { style: "text-align:center;margin:18px 0 4px;font-size:15px" },
      huella.th("hola", { nombre: "" }), h("b", {}, r.nombre)),
    h("p", { clase: "gris", style: "text-align:center;font-size:13px;margin:0 0 16px" },
      r.correo),
    error,
    (() => {
      const b = botonEntrar({ alEntrar, error });
      b.style.cssText = "width:100%;height:52px;font-size:15px";
      return b;
    })(),
    h("div", { clase: "centro", style: "margin-top:14px" },
      h("button", { type: "button", clase: "enlace", onclick: usarContrasena },
        huella.th("usar_contrasena"))),
    h("div", { clase: "centro", style: "margin-top:6px" },
      h("button", { type: "button", clase: "enlace",
                    style: "font-weight:400;font-size:12px",
                    onclick: () => { huella.olvidar(); cambiarPersona(); } },
        huella.noSoy())));
}

/* La pregunta de una sola vez, despues de entrar con contrasena. Se
   resuelve cuando decide: activar o "ahora no". */
export function ofrecer({ cuerpo, puerta, correo, nombre, contrasena }) {
  return new Promise((listo) => {
    const error = h("div");
    const si = h("button", { type: "button", onclick: async () => {
      si.disabled = true;
      error.replaceChildren();
      try {
        await huella.activar(contrasena, correo, nombre);
      } catch (err) {
        error.replaceChildren(aviso(err.message, "grave"));
        si.disabled = false;
        return;
      }
      /* El "listo" se dice aqui mismo, un momento, y se entra. Con
         mensaje() no: la barra de mensajes es de la consola y en la
         entrada todavia no existe; tronaba despues de guardar la llave y
         dejaba a la persona atorada en esta pantalla (seccion 110). */
      f.replaceChildren(
        h("div", { style: "text-align:center;margin:6px 0 10px;color:#1B1546" }, icono(54)),
        aviso(huella.th("activada"), "ok"));
      setTimeout(listo, 1600);
    } }, huella.th("ofrecer_si"));
    const f = h("form", { onsubmit: (e) => e.preventDefault() },
      h("div", { style: "text-align:center;margin:6px 0 10px;color:#1B1546" }, icono(54)),
      h("h2", { style: "text-align:center" }, huella.th("ofrecer_titulo")),
      h("p", { clase: "gris", style: "text-align:center;font-size:14px;line-height:1.5" },
        huella.th("ofrecer_texto")),
      error,
      si,
      h("div", { clase: "centro" },
        h("button", { type: "button", clase: "enlace", onclick: () => {
          huella.ahoraNo(correo);
          listo();
        } }, huella.th("ofrecer_no"))),
      h("p", { clase: "gris", style: "font-size:12px;text-align:center;margin:14px 0 0" },
        huella.th("ofrecer_pie")));
    cuerpo.replaceChildren(puerta(f));
  });
}

/* Menu de su nombre -> Entrar con huella o cara: en que equipos la
   tiene, activarla en este y quitarla. */
export async function pantalla(main, usuario) {
  const lista = h("div");
  const zona = h("div");
  const lector = await huella.hayLector();

  async function pintar() {
    const llaves = await huella.mias();
    const aqui = llaves.some(huella.esDeAqui);
    lista.replaceChildren(...[...(llaves.length ? llaves.map(k => h("div", {
      style: "display:flex;justify-content:space-between;align-items:center;gap:12px;"
           + "padding:10px 0;border-top:1px solid var(--linea)" },
      h("div", {},
        h("b", {}, k.nombre), " ",
        huella.esDeAqui(k)
          ? h("span", { clase: "etiqueta ok" }, huella.th("activado_aqui")) : null,
        h("div", { clase: "gris chico" },
          k.usada_en
            ? huella.th("usada", { cuando: new Date(k.usada_en).toLocaleString() })
            : huella.th("nunca"))),
      h("button", { type: "button", clase: "claro chico", onclick: async (e) => {
        if (!confirm(huella.th("quitar_pregunta", { nombre: k.nombre }))) return;
        e.target.disabled = true;
        try {
          await huella.quitar(k);
          mensaje(huella.th("quitada"));
          await pintar();
        } catch (err) {
          zona.replaceChildren(aviso(err.message, "grave"));
          e.target.disabled = false;
        }
      } }, huella.th("quitar"))))
      : [h("p", { clase: "gris" }, huella.th("ninguna"))])].filter(Boolean));

    if (!lector) {
      zona.replaceChildren(h("p", { clase: "gris chico" }, huella.th("no_hay")));
    } else if (aqui) {
      zona.replaceChildren();
    } else {
      const contrasena = entrada("contrasena", { type: "password",
                                                 autocomplete: "current-password" });
      const error = h("div");
      const boton = h("button", { type: "submit" }, icono(), huella.th("activar_aqui"));
      zona.replaceChildren(h("form", { onsubmit: async (e) => {
        e.preventDefault();
        boton.disabled = true;
        error.replaceChildren();
        try {
          await huella.activar(contrasena.value, usuario.correo, usuario.nombre);
          mensaje(huella.th("activada"));
          await pintar();
        } catch (err) {
          error.replaceChildren(aviso(err.message, "grave"));
          boton.disabled = false;
        }
      } },
        h("p", { clase: "gris chico", style: "margin:16px 0 8px" }, huella.th("pide_contrasena")),
        campo(huella.th("contrasena"), contrasena),
        error,
        h("div", { clase: "acciones" }, boton)));
    }
  }

  main.append(h("div", { clase: "tarjeta" },
    h("h2", {}, huella.th("titulo")),
    h("p", { clase: "sub" }, huella.th("pie")),
    lista, zona));
  await pintar();
}

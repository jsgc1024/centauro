/* Los cuatro digitos que el consultor o la central le dictan por telefono
   al personal de campo.

   Pensada para telefono desde el principio: la llamada de las 5:40 le
   llega al consultor en su casa, y si para resolverla tiene que prender
   la computadora, el agente arranca sin app. Por eso es una pantalla
   propia a un toque del menu y no un boton escondido dentro de un
   servicio: en un telefono, menu -> cartera -> encontrar el servicio ->
   bajar hasta la persona es un minuto largo con una mano. */
import { api } from "./api.js";
import { aviso, entrada, h, mensaje } from "./util.js";
import { t } from "./idioma.js";

export async function pantallaCodigo(main) {
  const resultados = h("div", { clase: "lista-codigo" });
  const zona = h("div");

  const campo = entrada("buscar", { placeholder: t("cod_buscar"),
                                    autocomplete: "off" });
  campo.addEventListener("input", () => buscar(campo.value));

  main.append(
    h("h1", {}, t("cod_titulo")),
    h("p", { clase: "sub" }, t("cod_pie")),
    h("div", { clase: "tarjeta" }, campo, resultados),
    zona);

  /* Se busca conforme se escribe, pero sin mandar una peticion por
     tecla: el que escribe rapido dispararia ocho busquedas para una
     sola palabra. */
  let pendiente = null;
  function buscar(texto) {
    clearTimeout(pendiente);
    zona.replaceChildren();
    if (texto.trim().length < 2) {
      return resultados.replaceChildren(
        h("div", { clase: "gris chico", style: "margin-top:10px" },
          t("cod_dos_letras")));
    }
    pendiente = setTimeout(async () => {
      try {
        const gente = await api.get(
          `/auth/campo/buscar?q=${encodeURIComponent(texto.trim())}`);
        resultados.replaceChildren(gente.length
          ? h("div", {}, ...gente.map(p => renglon(p, zona)))
          : h("div", { clase: "gris chico", style: "margin-top:10px" },
              t("cod_nadie")));
      } catch (err) {
        resultados.replaceChildren(aviso(err.message, "grave"));
      }
    }, 250);
  }

  campo.focus();
}

/* La foto y el telefono no son adorno: como no hay numero de empleado, la
   voz es lo unico que verifica, y esto le da al consultor algo mas que
   preguntar --"de que numero me llamas"--. El renglon de donde esta hoy
   tambien verifica: si dice que entra a las seis y el sistema no le ve
   nada hoy, algo no cuadra. */
function renglon(p, zona) {
  return h("div", { clase: "persona-codigo" },
    p.foto ? h("img", { clase: "foto", src: p.foto, alt: "" })
           : h("div", { clase: "foto" }),
    h("div", { clase: "datos-codigo" },
      h("h4", { style: "margin:0 0 1px" }, p.nombre),
      h("div", { clase: "chico gris" }, p.telefono || "—"),
      h("div", { clase: "chico gris" },
        p.hoy ? t("cod_hoy").replace("{s}", p.hoy) : t("cod_sin_hoy")),
      p.estrenado ? "" : h("div", { clase: "chico", style: "color:#b8860b" },
                           t("cod_sin_estrenar"))),
    h("button", { clase: "chico", type: "button",
      onclick: () => confirmar(zona, p) }, t("cod_generar")));
}

/* Un paso antes de generar. No es ceremonia: es el unico momento en que
   alguien se detiene a comprobar que del otro lado del telefono esta
   quien dice ser. */
function confirmar(zona, p) {
  const generar = h("button", { clase: "chico", type: "button",
    onclick: (e) => pedir(e, zona, p) }, t("cod_generar"));

  zona.replaceChildren(h("div", { clase: "tarjeta" },
    h("h3", { style: "margin:0 0 8px" }, p.nombre),
    h("div", { clase: "chico" }, p.telefono || "—"),
    h("div", { clase: "chico gris", style: "margin-bottom:10px" },
      p.hoy ? t("cod_hoy").replace("{s}", p.hoy) : t("cod_sin_hoy")),
    aviso(t("cod_confirma"), "alerta"),
    p.codigo_vigente_hasta
      ? h("div", { clase: "chico gris", style: "margin-top:8px" },
          t("cod_ya_tiene"))
      : "",
    h("div", { clase: "acciones", style: "margin-top:12px" },
      h("button", { clase: "claro chico", type: "button",
        onclick: () => zona.replaceChildren() }, t("cod_cerrar")),
      generar)));
  zona.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function pedir(e, zona, p) {
  e.target.disabled = true;
  try {
    const r = await api.post("/auth/campo/codigo", { persona_id: p.persona_id });
    zona.replaceChildren(tarjetaDelCodigo(zona, r));
  } catch (err) {
    mensaje(err.message, "grave");
    e.target.disabled = false;
  }
}

/* La unica vez que se ve. Si se cierra, se acabo: hay que generar otro, y
   ese mata a este. Asi nadie acumula una lista de codigos vigentes en una
   pestana abierta. */
function tarjetaDelCodigo(zona, r) {
  const cuenta = h("div", { clase: "gris chico" });
  const caja = h("div", { clase: "tarjeta codigo-grande" },
    h("div", { clase: "digitos" }, r.codigo.split("").join(" ")),
    cuenta,
    h("p", { clase: "chico", style: "margin:12px 0 0" },
      t("cod_dictalo").replace("{p}", r.persona.nombre)),
    h("p", { clase: "gris chico", style: "margin:4px 0 0" }, t("cod_una_vez")),
    h("div", { clase: "acciones", style: "margin-top:14px" },
      h("button", { clase: "claro chico", type: "button",
        onclick: () => zona.replaceChildren() }, t("cod_cerrar"))));

  /* El reloj se apaga solo cuando la tarjeta deja de estar en pantalla:
     asi no hace falta acordarse de detenerlo al navegar. */
  const fin = Date.now() + r.minutos * 60000;
  const latir = () => {
    if (!document.body.contains(caja)) return clearInterval(reloj);
    const faltan = Math.max(0, Math.round((fin - Date.now()) / 1000));
    if (!faltan) {
      cuenta.textContent = t("cod_vencido");
      return clearInterval(reloj);
    }
    const mm = Math.floor(faltan / 60);
    const ss = String(faltan % 60).padStart(2, "0");
    cuenta.textContent = t("cod_vence").replace("{m}", `${mm}:${ss}`);
  };
  const reloj = setInterval(latir, 1000);
  latir();
  return caja;
}

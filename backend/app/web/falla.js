/* Reportar una falla (seccion 92).

   El boton vive arriba, junto al nombre, en todas las pantallas: la
   falla se reporta donde se ve, y no despues, de memoria, por telefono.
   Quien reporta escribe que paso y, si quiere, pega una captura; lo
   demas se manda solo --la pantalla, el servicio, quien, el navegador y
   lo ultimo que salio en rojo o que contesto el servidor--, y se le
   ensena antes de mandarlo, para que sepa que se va y que no. Nunca la
   sesion ni contrasenas.

   Llega a Manual del sistema -> Casos como «por revisar», y sistema y
   calidad lo resuelve o lo copia para Claude (aprobado por Salvador el
   27 de septiembre: «asi cerramos el ciclo»). */
import { api, cajaNegra, sesion } from "./api.js";
import { aviso, fecha, h, hora, mensaje, reducirImagen } from "./util.js";
import { idioma, t } from "./idioma.js";
import { nombreDelRol } from "./categorias.js";

export function botonReportar() {
  return h("button", {
    clase: "reportar-falla", type: "button", title: t("fal_boton_pie"),
    onclick: (e) => { e.stopPropagation(); abrirReporte(); },
  }, t("fal_boton"));
}

/* "Chrome 141 · Windows": lo que hace falta para reproducirlo, sin el
   renglon entero del navegador, que viaja completo aparte. */
export function navegadorCorto(ua = navigator.userAgent) {
  const cual = [["Edg", "Edge"], ["OPR", "Opera"], ["CriOS", "Chrome"],
                ["Chrome", "Chrome"], ["FxiOS", "Firefox"], ["Firefox", "Firefox"],
                ["Version", "Safari"]]
    .map(([marca, nombre]) => {
      const m = String(ua || "").match(new RegExp(`${marca}/(\\d+)`));
      return m ? `${nombre} ${m[1]}` : null;
    }).find(Boolean) || "";
  const sistema = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android"
    : /iPhone|iPad/.test(ua) ? "iPhone" : /Mac OS X/.test(ua) ? "Mac"
    : /Linux/.test(ua) ? "Linux" : "";
  return [cual, sistema].filter(Boolean).join(" · ");
}

/* Donde esta parado: el titulo de la pantalla y, si es un servicio, su
   numero, para que en el caso diga el folio y no solo la ruta. */
function dondeEstoy() {
  const ruta = location.hash || "#/";
  const titulo = document.querySelector("main h1");
  const m = ruta.match(/^#\/(servicio|implantado)\/(\d+)/);
  return { ruta, pantalla: titulo ? titulo.textContent.trim().slice(0, 80) : "",
           servicio_id: m ? Number(m[2]) : null };
}

function comoDataUrl(archivo) {
  return new Promise((listo, falla) => {
    const lector = new FileReader();
    lector.onerror = () => falla(new Error(t("fal_captura_no")));
    lector.onload = () => listo(lector.result);
    lector.readAsDataURL(archivo);
  });
}

function llenar(clave, datos) {
  let salida = t(clave);
  for (const [k, v] of Object.entries(datos)) {
    salida = salida.split(`{${k}}`).join(String(v));
  }
  return salida;
}

export function abrirReporte() {
  // Una sola forma a la vez: el boton sigue arriba mientras esta abierta.
  if (document.querySelector(".falla-capa")) return;
  const aqui = dondeEstoy();
  const caja = cajaNegra();
  let captura = null;
  let enviado = false;

  const quePaso = h("textarea", { rows: "3", maxlength: "4000",
                                  placeholder: t("fal_que_paso_ej") });
  const esperaba = h("textarea", { rows: "2", maxlength: "2000" });

  /* Lo que falta o lo que no salio se dice aqui dentro, y no en la barra
     de mensajes: esa queda debajo de la capa, donde no se ve. Y asi
     tampoco entra a la caja negra del siguiente reporte. */
  const nota = h("div", { clase: "falla-nota" });
  const decir = (texto, tono = "alerta") => nota.replaceChildren(aviso(texto, tono));

  /* La captura se pega con Ctrl+V en cualquier parte de la forma, o se
     escoge un archivo. Se reduce antes de salir, como los tickets. */
  const archivo = h("input", { type: "file", accept: "image/*", hidden: true });
  const zona = h("div", { clase: "falla-captura", tabindex: "0",
                          onclick: () => archivo.click() });
  const pintarZona = () => {
    zona.replaceChildren(...(captura
      ? [h("img", { src: captura, alt: "" }),
         h("button", { clase: "claro chico", type: "button", onclick: (e) => {
           e.stopPropagation(); captura = null; pintarZona(); } }, t("fal_quitar_captura"))]
      : [h("span", {}, t("fal_captura_pega"), " "),
         h("u", {}, t("fal_captura_elige"))]));
  };
  const tomar = async (imagen) => {
    try {
      captura = await comoDataUrl(await reducirImagen(imagen));
      nota.replaceChildren();
      pintarZona();
    } catch (err) {
      decir(err.message);
    }
  };
  archivo.addEventListener("change", () => {
    if (archivo.files && archivo.files[0]) tomar(archivo.files[0]);
  });
  pintarZona();

  /* Lo que se manda solo, a la vista. */
  const version = h("span", { clase: "gris" }, "…");
  api.get(`/manual/version?idioma=${idioma()}`)
    .then(v => { version.textContent = llenar("fal_version", { n: v.seccion, f: v.fecha }); })
    .catch(() => { version.textContent = "—"; });
  const ultimo = caja.mensajes[0] || caja.llamadas.find(x => x.codigo === 0 || x.codigo >= 400);
  const usuario = sesion.usuario || {};
  const ahora = new Date().toISOString();
  const fila = (clave, valor) => [h("span", { clase: "gris" }, t(clave)), h("span", {}, valor)];
  const solo = h("div", { clase: "falla-solo" },
    h("h4", {}, t("fal_se_manda_solo")),
    h("div", { clase: "falla-datos" },
      ...fila("fal_pantalla", [aqui.pantalla, aqui.ruta].filter(Boolean).join(" · ")),
      ...fila("fal_quien", [usuario.nombre, usuario.puesto || nombreDelRol(usuario.rol)]
        .filter(Boolean).join(" · ")),
      ...fila("fal_cuando", `${fecha(ahora)} · ${hora(ahora)}`),
      ...fila("fal_version_t", version),
      ...fila("fal_navegador", navegadorCorto()),
      ...fila("fal_lo_ultimo", ultimo
        ? `${hora(ultimo.cuando)} · «${ultimo.texto || ultimo.mensaje || ultimo.ruta}»`
        : t("fal_nada_raro"))),
    h("p", { clase: "chico gris", style: "margin:8px 0 0" }, t("fal_nunca")));

  const mandar = h("button", { type: "button" }, t("fal_mandar"));
  const cancelar = h("button", { clase: "claro", type: "button" }, t("cancelar"));

  const tarjeta = h("div", { clase: "falla-tarjeta", role: "dialog",
                             "aria-label": t("fal_titulo") },
    h("h3", { style: "margin:0 0 4px;font-size:17px" }, t("fal_titulo")),
    h("p", { clase: "chico gris", style: "margin:0 0 14px" }, t("fal_sub")),
    h("label", {}, t("fal_que_paso")), quePaso,
    h("label", { style: "margin-top:10px" }, t("fal_esperaba"), " ",
      h("span", { clase: "gris", style: "font-weight:400" }, t("fal_si_quieres"))),
    esperaba,
    h("label", { style: "margin-top:10px" }, t("fal_captura"), " ",
      h("span", { clase: "gris", style: "font-weight:400" }, t("fal_si_quieres"))),
    zona, archivo,
    solo,
    nota,
    h("div", { clase: "acciones", style: "margin-top:14px" }, mandar, cancelar));

  const capa = h("div", { clase: "falla-capa" }, tarjeta);

  function cerrar() {
    capa.remove();
    document.removeEventListener("keydown", tecla);
  }
  /* Escape cierra solo si no hay nada escrito: lo que se escribio no se
     pierde por una tecla. Ya mandado, cierra siempre. */
  function tecla(e) {
    if (e.key !== "Escape") return;
    if (enviado || (!quePaso.value.trim() && !esperaba.value.trim())) cerrar();
  }
  tarjeta.addEventListener("paste", (e) => {
    const imagen = [...(e.clipboardData ? e.clipboardData.items : [])]
      .find(x => x.type && x.type.startsWith("image/"));
    if (imagen) {
      e.preventDefault();
      tomar(imagen.getAsFile());
    }
  });
  cancelar.addEventListener("click", cerrar);

  /* Ya mandado, la misma tarjeta lo dice: con que numero quedo y que
     sigue. Un aviso en la barra de arriba se va solo y se pierde si la
     pantalla estaba abajo. */
  function listo(numero) {
    enviado = true;
    const ok = h("button", { type: "button", onclick: cerrar }, t("fal_listo_boton"));
    tarjeta.replaceChildren(
      h("h3", { style: "margin:0 0 6px;font-size:17px" }, t("fal_listo_titulo")),
      h("p", { style: "margin:0 0 16px" }, llenar("fal_listo", { n: numero })),
      h("div", { clase: "acciones" }, ok));
    ok.focus();
    mensaje(llenar("fal_recibido", { n: numero }));
  }

  mandar.addEventListener("click", async () => {
    if (quePaso.value.trim().length < 3) {
      quePaso.focus();
      return decir(t("fal_falta_que"));
    }
    mandar.disabled = true;
    mandar.textContent = t("fal_mandando");
    nota.replaceChildren();
    try {
      const r = await api.post("/manual/fallas", {
        que_paso: quePaso.value, esperaba: esperaba.value || null, captura,
        contexto: { desde: "consola", ...aqui, navegador: navigator.userAgent,
                    mensajes: caja.mensajes, llamadas: caja.llamadas } });
      listo(r.id);
    } catch (err) {
      decir(err.message, "grave");
      mandar.disabled = false;
      mandar.textContent = t("fal_mandar");
    }
  });

  document.addEventListener("keydown", tecla);
  document.body.append(capa);
  quePaso.focus();
}

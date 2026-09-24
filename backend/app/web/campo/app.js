/* La app del personal de seguridad.

   No es una consola chica: es otra cosa. Quien la usa esta de pie, con
   una mano, a veces de madrugada y casi siempre con prisa. Por eso:

   - abre directo en el dia de hoy, sin menu que navegar
   - ofrece UN paso, el siguiente, no seis botones que hay que leer
   - lo que no se pudo mandar se ve arriba hasta que sale
   - el boton rojo siempre esta, en todas las pantallas

   Todo pasa por el mismo backend y la misma sesion que la consola. */
import { api, sesion } from "/consola/api.js";
import { idioma, ponerIdioma, t } from "/consola/idioma.js";
import { apartadas, encolar, limpiar, pendientes, retenida, sacar,
         vaciar } from "./cola.js";
import { guardar as guardarMemoria, hace, olvidar, recordar,
         traer } from "./memoria.js";
import { reducir } from "./foto.js";

const raiz = () => document.getElementById("app");

/* Las tablas de texto se arman al pintar y no al cargar el modulo: el
   idioma se pone cuando ya se sabe de quien es la sesion, y una tabla
   congelada al arrancar se quedaria en espanol para siempre. */
const hitos = () => ({
  llegada_origen: { texto: t("cmp_hito_origen"),
                    corto: t("cmp_hito_origen_c") },
  contacto_ejecutivo: { texto: t("cmp_hito_contacto"),
                        corto: t("cmp_hito_contacto_c") },
  salida_ruta: { texto: t("cmp_hito_ruta"), corto: t("cmp_hito_ruta_c") },
  llegada_destino: { texto: t("cmp_hito_destino"),
                     corto: t("cmp_hito_destino_c") },
  standby: { texto: t("cmp_hito_standby"), corto: t("cmp_hito_standby_c") },
  fin_servicio: { texto: t("cmp_hito_fin"), corto: t("cmp_hito_fin_c") },
});

/* El idioma manda tambien en las fechas y los numeros. Traducir los
   textos y dejar "es-MX" pegado deja una pantalla en portugues que dice
   "segunda-feira" en espanol: el dato tambien esta escrito en un
   idioma. */
const LOCALES = { es: "es-MX", en: "en-US", pt: "pt-BR" };
const local = () => LOCALES[idioma()] || "es-MX";

let vista = "hoy";

/* --------------------------------------------------------- arranque */

window.addEventListener("hashchange", pintar);
window.addEventListener("online", () => sincronizar(true));

/* Se actualiza sola cada minuto. Con dos candados, y los dos importan.
  
   PRIMERO: solo mientras la pantalla se ve. Un telefono que va todo el
   dia en la bolsa pidiendo datos cada minuto gasta bateria y datos para
   nada, y sin senal son sesenta intentos fallidos por hora. En cuanto
   la app se va al fondo el reloj se para, y al volver al frente se
   refresca de una vez --que es cuando de verdad hace falta.
  
   SEGUNDO: no repinta encima de quien esta escribiendo. Repintar tira
   lo que hay en los campos, y en esta app eso serian la nota de un
   movimiento, un comprobante a medio capturar o el odometro de una
   revision. Perder eso en la calle, con una mano, es peor que ver un
   dato un minuto viejo. Si hay un campo con el foco, se salta esta
   vuelta y lo intenta en la siguiente. */
const REFRESCO_SEGUNDOS = 60;

/* Hay algo capturado que se perderia al repintar.
  
   Mi primer candado miraba si habia un campo con el FOCO, y eso no
   alcanza ni de lejos. Al tomar una foto, el telefono se va a la camara
   y al volver no hay nada con el foco --pero si hay una foto en la
   ranura, recien tomada y sin guardar--. El repintado se la llevaba. Lo
   reporto Salvador el 21 de septiembre recibiendo una unidad: tomaba la
   foto y desaparecia.
  
   Asi que no se pregunta quien tiene el foco: se pregunta si hay TRABAJO
   EN PANTALLA. Una foto puesta, un campo escrito, un archivo elegido o
   una firma trazada. Con cualquiera de esos, esta vuelta se salta y se
   intenta en la siguiente; el dato se vera un minuto mas viejo y eso no
   le cuesta nada a nadie. Perder cinco fotos y una firma en la calle,
   si.
  
   Ante la duda, NO se repinta. */
function hayCaptura() {
  if (document.querySelector(".ranura.lista")) return true;      // fotos
  if (document.querySelector("canvas.firma")) return true;       // firmando
  for (const c of document.querySelectorAll("input, textarea, select")) {
    if (c.type === "file") {
      if (c.files && c.files.length) return true;
    } else if ((c.value || "").trim()) {
      return true;
    }
  }
  const foco = document.activeElement;
  return !!foco && ["INPUT", "TEXTAREA", "SELECT"].includes(foco.tagName);
}

setInterval(() => {
  if (document.visibilityState !== "visible") return;
  if (!sesion.token) return;
  if (hayCaptura()) return;
  pintar();
}, REFRESCO_SEGUNDOS * 1000);

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible" || !sesion.token) return;
  /* Mandar lo encolado siempre: eso no toca la pantalla. Repintar, solo
     si no hay nada capturado --volver de la camara es justo el momento
     en que MAS hay que perder. */
  sincronizar(true);
  if (!hayCaptura()) pintar();
});
/* El trabajador de fondo entrega los avisos y guarda el armazon de la
   app, para que abra sin senal. Se registra siempre; el permiso de
   avisos se pide aparte y solo cuando tiene sentido. */
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/app/sw.js").catch(() => {});
}
/* El logotipo de la empresa, el mismo que la consola y el task sheet.

   Sale de `backend/assets/logo.png` por la ruta `/sistema/logo`, que lo
   entrega incrustado. Se pide una vez y se guarda: asi el dia que se
   reemplace el archivo, la app y la consola cambian juntas --con dos
   copias del archivo, una de las dos se quedaria vieja para siempre--.

   Mientras no llega se usa el icono de la app, que es la misma marca en
   chico: la pantalla nunca sale sin nada arriba. */
let logoEmpresa = (recordar("logo") || {}).datos || null;

async function cargarLogo() {
  try {
    const r = await api.get("/sistema/logo");
    if (r && r.logo && r.logo !== logoEmpresa) {
      logoEmpresa = r.logo;
      guardarMemoria("logo", r.logo);
      pintar();
    }
  } catch { /* sin senal se queda con el guardado, o con el icono */ }
}

document.addEventListener("DOMContentLoaded", pintar);
pintar();
cargarLogo();


async function pintar() {
  if (!sesion.token) return entrada();
  if (!sesion.usuario) {
    try { await api.quienSoy(); } catch { return entrada(); }
  }
  /* El idioma sale del pais de su plaza y viene con la identidad, no de
     un selector. El de campo va con una mano y prisa: un boton que se
     toca sin querer y le deja la app en portugues a las seis de la
     manana es peor que el problema que resuelve.

     Se pone antes de pintar nada, y solo si cambio: `ponerIdioma`
     escribe en sessionStorage y eso no hace falta en cada vista. */
  const suyo = sesion.usuario.idioma;
  if (suyo && suyo !== idioma()) ponerIdioma(suyo);
  /* La consola y la app viven en el mismo servidor, asi que comparten
     la sesion del navegador: quien entro a la consola como consultor
     abre la app y ya esta "adentro", con un usuario que aqui no tiene
     nada que hacer. Decirle "tu rol no tiene permiso" es cierto y no
     sirve de nada; lo que hace falta es decirle de quien es esta app y
     como entrar con la cuenta correcta. */
  if (sesion.usuario.rol !== "personal_seguridad") return otraCuenta();
  vista = (location.hash.replace("#/", "") || "hoy");
  if (vista === "viaticos") return pantallaViaticos();
  if (vista === "pagos") return pantallaPagos();
  if (vista === "yo") return pantallaYo();
  if (vista.startsWith("revision/")) return pantallaRevision();
  return pantallaHoy();
}

function h(tag, props, ...hijos) {
  const nodo = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "clase") nodo.className = v;
    else if (k.startsWith("on")) nodo.addEventListener(k.slice(2), v);
    else if (k === "html") nodo.innerHTML = v;
    else nodo.setAttribute(k, v === true ? "" : v);
  }
  for (const hijo of hijos.flat()) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo.nodeType ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

function aviso(texto, tono = "") {
  return h("div", { clase: `aviso ${tono}`.trim() }, texto);
}

function hora(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(local(),
    { hour: "2-digit", minute: "2-digit" });
}

/* ----------------------------------------------------------- entrada */

function entrada() {
  const correo = h("input", { type: "email", inputmode: "email",
                              autocapitalize: "none", autocomplete: "username" });
  const clave = h("input", { type: "password",
                             autocomplete: "current-password" });
  const error = h("div");
  const boton = h("button", { onclick: () => entrar() }, t("cmp_entrar"));

  async function entrar() {
    boton.disabled = true;
    error.replaceChildren();
    try {
      await api.entrar(correo.value.trim(), clave.value);
      await api.quienSoy();
      location.hash = "#/hoy";
      pintar();
      /* El logo se pide de nuevo aqui: quien abre la app por primera
         vez no tenia sesion cuando se pidio al arrancar. */
      cargarLogo();
    } catch (err) {
      error.replaceChildren(aviso(err.message, "grave"));
      boton.disabled = false;
    }
  }

  raiz().replaceChildren(h("div", { clase: "entrada" },
    /* La marca de verdad si ya se guardo alguna vez; el nombre en texto
       la primera vez, que es cuando todavia no hay de donde sacarla. */
    logoEmpresa
      ? h("img", { clase: "logo-entrada", src: logoEmpresa,
                   alt: t("cmp_marca") })
      : h("h1", {}, t("cmp_marca")),
    h("p", { clase: "gris" }, t("cmp_lema")),
    h("div", { clase: "caja", style: "margin-top:22px" },
      error,
      h("div", { clase: "campo" }, h("label", {}, t("cmp_correo")), correo),
      h("div", { clase: "campo" }, h("label", {}, t("cmp_contrasena")), clave),
      boton,
      /* Tu contraseña no va por correo: el correo es tuyo y la empresa
         no lo controla. Va por tu consultor, que te reconoce la voz. */
      h("button", { clase: "claro", style: "margin-top:10px",
        onclick: () => conCodigo(correo.value.trim()) },
        t("cmp_olvide")))));
}

/* El agente llamó a su consultor --o a la central-- y le dictaron cuatro
   dígitos por teléfono. Aquí los escribe y pone su contraseña.

   Cuatro y no seis porque se dictan en voz alta a las seis de la mañana.
   El candado no está aquí sino en el servidor: cinco fallos y el código
   se muere. */
function conCodigo(correoPrevio) {
  const correo = h("input", { type: "email", inputmode: "email",
                              autocapitalize: "none", value: correoPrevio || "",
                              autocomplete: "username" });
  const codigo = h("input", { type: "text", inputmode: "numeric",
                              maxlength: "4", autocomplete: "one-time-code",
                              placeholder: "0000" });
  const clave = h("input", { type: "password",
                             autocomplete: "new-password" });
  const error = h("div");
  const boton = h("button", { onclick: () => guardar() }, t("cmp_guardar_entrar"));

  async function guardar() {
    boton.disabled = true;
    error.replaceChildren();
    try {
      await api.post("/auth/campo/contrasena", {
        correo: correo.value.trim(),
        codigo: codigo.value.trim(),
        contrasena: clave.value,
      });
      /* Se entra de corrido con la que acaba de poner: a las 5:40 nadie
         quiere escribirla dos veces. */
      await api.entrar(correo.value.trim(), clave.value);
      await api.quienSoy();
      location.hash = "#/hoy";
      pintar();
      /* El logo se pide de nuevo aqui: quien abre la app por primera
         vez no tenia sesion cuando se pidio al arrancar. */
      cargarLogo();
    } catch (err) {
      error.replaceChildren(aviso(err.message, "grave"));
      boton.disabled = false;
    }
  }

  raiz().replaceChildren(h("div", { clase: "entrada" },
    h("h1", {}, t("cmp_marca")),
    h("p", { clase: "gris" }, t("cmp_pide_codigo")),
    h("div", { clase: "caja", style: "margin-top:22px" },
      error,
      h("div", { clase: "campo" }, h("label", {}, t("cmp_correo")), correo),
      h("div", { clase: "campo" },
        h("label", {}, t("cmp_codigo_4")), codigo),
      h("div", { clase: "campo" },
        h("label", {}, t("cmp_contrasena_nueva")), clave),
      boton,
      h("button", { clase: "claro", style: "margin-top:10px",
        onclick: () => entrada() }, t("cmp_regresar")))));
}

/* --------------------------------------------------- la cola arriba */

let sincronizando = false;

/* Lo que el servidor contesto al cerrar el dia y todavia no se ha
   preguntado. Al marcar el fin de servicio, la respuesta trae la
   pregunta de a que hora arrancan manana; como la marca ya no sale en
   el mismo toque --se retiene unos segundos, y sin senal se queda en la
   cola-- esa respuesta llega despues y no se puede perder: el principal
   acaba de decir la hora y quien lo escucho trae el telefono en la
   mano. Se guarda aqui y la pantalla de hoy la levanta. */
let mananaPorPreguntar = null;

/* Las marcas que ya estaban en la cola antes de la seccion 65 traen la
   hora UTC sin decirlo --se armaban con toISOString().slice(0, 19)--:
   se les pone su zona antes de mandarlas o de ensenarlas. */
function conZona(cuando) {
  return cuando && !/(Z|[+-]\d\d:?\d\d)$/.test(cuando) ? `${cuando}Z` : cuando;
}

async function mandarHito(item) {
  const cuerpo = item.cuerpo && item.cuerpo.marcado_en
    ? { ...item.cuerpo, marcado_en: conZona(item.cuerpo.marcado_en) }
    : item.cuerpo;
  const r = await api.post(`/operacion/jornadas/${item.jornada_id}/hitos`,
                           cuerpo);
  if (r && r.manana) mananaPorPreguntar = r.manana;
  return r;
}

async function sincronizar(silencioso = false) {
  if (sincronizando || !pendientes().length) return;
  sincronizando = true;
  try {
    const r = await vaciar(mandarHito);
    if (r.rechazados.length) {
      /* Se guardan ANTES de avisar: si el aviso salta con el telefono
         en el bolsillo --o si nadie lo lee-- la marca rechazada sigue a
         la vista en la pantalla hasta que alguien la atienda. */
      apartadas.apartar(r.rechazados);
      alert(t("cmp_marca_rechazada") + "\n\n"
            + r.rechazados.map(x => x.motivo).join("\n"));
    }
    if (r.enviados) {
      /* La hora de manana se pregunta en cuanto llega la respuesta, no
         al volver a abrir la app: media hora despues ese dato ya se fue
         a dormir con el principal. */
      if (mananaPorPreguntar) {
        const suya = mananaPorPreguntar;
        mananaPorPreguntar = null;
        return pantallaManana(suya);
      }
      pintar();
    }
  } finally { sincronizando = false; }
}

/* Lo que el servidor rechazo, a la vista hasta que alguien lo lea.
   Una marca rechazada es una llegada que no quedo registrada: si nadie
   la atiende, ese dia queda sin prueba de que la persona estuvo ahi. */
function bandaRechazadas() {
  const filas = apartadas.todas();
  if (!filas.length) return null;

  const caja = h("div", { clase: "pendientes" });
  caja.append(h("div", {}, t("cmp_marca_rechazada")));
  for (const x of filas) {
    caja.append(h("div", { clase: "chico",
      style: "font-weight:400;margin-top:6px" },
      h("div", {}, [x.tipo && hitos()[x.tipo] ? hitos()[x.tipo].corto : x.tipo,
                    x.cuando && hora(conZona(x.cuando))]
        .filter(Boolean).join(" · ")),
      h("div", {}, x.motivo),
      h("button", { clase: "claro chico", style: "margin-top:6px",
        onclick: () => { apartadas.descartar(x.id); pintar(); } },
        t("cmp_entendido"))));
  }
  caja.append(h("div", { clase: "chico", style: "font-weight:400" },
    t("cmp_rechazada_pie")));
  return caja;
}


function bandaPendientes() {
  const cuantos = pendientes().length;
  if (!cuantos) return null;
  return h("div", { clase: "pendientes" },
    h("div", {}, t("cmp_cola_sin_enviar").replace("{n}", cuantos)),
    h("div", { clase: "chico", style: "font-weight:400;margin-top:4px" },
      t("cmp_cola_pie")),
    h("button", { clase: "claro chico", style: "margin-top:10px",
      onclick: () => sincronizar() }, t("cmp_intentar")));
}

/* --------------------------------------------------------- hoy */

async function pantallaHoy() {
  cargando();
  let r;
  try { r = await traer("mi-dia", () => api.get("/campo/mi-dia")); }
  catch (err) { return conBarra(aviso(motivo(err), "grave")); }

  const datos = r.datos;
  const hoy = datos.hoy || [];
  const manana = datos.manana || [];

  /* Con red, la senal se guarda en el telefono desde ahora: donde se
     usa --a la salida del filtro-- ya no hay con que bajarla. */
  if (!r.de_memoria) guardarSenales([...hoy, ...manana]);

  /* Se pico "Confirmo que voy" en la notificacion. El trabajador de
     fondo no puede hablar con el servidor --el permiso de la sesion
     vive aqui-- asi que abre la app con esta marca y la app lo hace.
     Se quita de la direccion antes, para que recargar no vuelva a
     dispararlo. */
  if (location.hash.includes("confirmar=1")) {
    history.replaceState(null, "", "#/hoy");
    return confirmarLoQueFalta([...hoy, ...manana]);
  }

  /* Se tocó "Voy en camino" en el aviso. Lo único que hace falta es
     decir dónde está: con esa posición y la de dentro de un rato, la
     central sabe si se está moviendo hacia el punto. */
  if (location.hash.includes("en_camino=1")) {
    history.replaceState(null, "", "#/hoy");
    return vozEnCamino(hoy);
  }

  const cuerpo = [
    h("h1", {}, t("cmp_hola")
      .replace("{nombre}", (datos.persona || "").split(" ")[0])),
    /* Un renglon por pantalla: que se espera de ti aqui. Tres de las
       cinco no lo decian. Quien lee esto esta de pie, con una mano, a
       las seis de la manana: no cabe mas que una linea. */
    h("p", { clase: "gris chico", style: "margin:2px 0 14px" }, t("cmp_hoy_pie")),
    /* Sin senal se muestra lo ultimo que se supo, con su edad escrita.
       Un dato viejo que se sabe viejo sirve; uno viejo que se ve nuevo
       es peor que no tener nada. */
    r.de_memoria ? sinLinea(r.en) : null,
  ];

  if (!hoy.length && !manana.length) {
    /* Cerrar el dia lo saca de aqui. Si el hueco dijera "no tienes
       servicios", quien acaba de trabajar doce horas leeria que su dia
       nunca existio. */
    cuerpo.push(h("div", { clase: "vacio" },
      datos.cerrados_hoy ? t("cmp_dia_cerrado") : t("cmp_sin_servicios")));
  }

  for (const f of hoy) cuerpo.push(tarjetaHoy(f));
  if (manana.length) {
    cuerpo.push(h("h2", {}, t("cmp_manana")));
    for (const f of manana) cuerpo.push(tarjetaManana(f));
    cuerpo.push(ofrecerAvisos(manana.some(x => !x.confirmado)));
  }

  if ((datos.proximos || []).length) {
    cuerpo.push(h("h2", {}, t("cmp_despues")));
    for (const p of datos.proximos) {
      cuerpo.push(h("div", { clase: "caja" },
        identificacion(p),
        h("div", { clase: "fila separa" },
          h("div", {},
            h("b", {}, new Date(p.fecha + "T12:00:00")
              .toLocaleDateString(local(), { weekday: "long", day: "numeric",
                                             month: "long" })),
            p.hora_confirmada && p.punto
              ? h("div", { clase: "chico gris" }, p.punto)
              : null),
          /* Lo mismo que en la tarjeta de manana: la hora heredada no
             ocupa el lugar de la hora. */
          h("div", { style: "text-align:right" },
            h("b", {}, p.hora_confirmada ? hora(p.llegar_a_las)
                                         : t("cmp_hora_sin_confirmar"))))));
    }
  }

  conBarra(...cuerpo);
}

function sinLinea(en) {
  return h("div", { clase: "pendientes" },
    h("div", {}, t("cmp_sin_conexion")),
    h("div", { clase: "chico", style: "font-weight:400;margin-top:4px" },
      t("cmp_ultimo_supo").replace("{cuando}", hace(en))));
}

/* De que servicio es esta tarjeta.

   En la calle el agente no habla de "mi dia": habla del folio y del
   equipo, que es lo que la central le pregunta por telefono y lo que
   trae escrito en la task sheet. Sin esto, dos servicios del mismo dia
   se leen igual. */
function identificacion(f) {
  const partes = [f.folio, f.equipo ? `${t("equipo")} ${f.equipo}` : null]
    .filter(Boolean);
  if (!partes.length) return null;
  return h("div", { clase: "chico gris", style: "margin-bottom:6px" },
    partes.join(" · "));
}

function tarjetaHoy(f) {
  const paso = f.siguiente;
  const caja = h("div", { clase: "caja" },
    identificacion(f),
    h("div", { clase: "fila separa" },
      h("div", {}, h("div", { clase: "grande" }, hora(f.llegar_a_las)),
        h("div", { clase: "chico gris" },
          t("cmp_estar_punto").replace("{hora}", hora(f.presentacion))
          + (f.contra_vuelo ? " · " + t("cmp_contra_vuelo") : ""))),
      f.mi_rol ? h("span", { clase: "marca" }, f.mi_rol) : null),

    /* Confirmar tambien vive aqui, no solo en la tarjeta de manana.

       En un servicio de hoy para hoy el aviso de la vispera nunca sale
       --lo manda el reloj la noche anterior-- y este boton no existia
       en la tarjeta de hoy, asi que no habia una sola manera de decir
       "ya se que trabajo". La central lo veia rojo hasta que pasara la
       hora de inicio.

       Desaparece en cuanto confirma: en la pantalla de las seis de la
       manana no sobra espacio para un boton que ya cumplio. */
    f.confirmado ? null : h("div", { clase: "marco" },
      h("button", { clase: "claro", onclick: (e) => confirmar(e, f) },
        t("cmp_confirmar")),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        t("cmp_confirmar_hoy_pie"))),

    h("div", { clase: "marco" },
      h("div", { clase: "dato" },
        h("span", { clase: "clave" }, t("cmp_punto")),
        h("div", {}, f.punto.direccion || t("cmp_sin_capturar")),
        f.punto.lat
          ? h("a", { clase: "chico", target: "_blank",
              href: `https://www.google.com/maps?q=${f.punto.lat},${f.punto.lon}` },
              t("cmp_abrir_mapa"))
          : null),
      f.vuelo
        ? h("div", { clase: "dato" },
            h("span", { clase: "clave" }, t("cmp_vuelo")),
            `${f.vuelo.aerolinea || ""} ${f.vuelo.numero || ""} · `
            + hora(f.vuelo.hora))
        : null,
      h("div", { clase: "dato" },
        h("span", { clase: "clave" }, t("cmp_ejecutivo")),
        f.ejecutivo || "—"),
      senalDelDia(f),
      /* Como hay que ir vestido. Si el servicio no trae codigo no se
         pinta el renglon: un servicio sin acuerdo no es "casual". */
      f.vestimenta
        ? h("div", { clase: "dato" },
            h("span", { clase: "clave" }, t("cmp_vestimenta")),
            t(`vest_${f.vestimenta}`))
        : null,
      f.unidades.length
        ? h("div", { clase: "dato" },
            h("span", { clase: "clave" }, t("cmp_unidad")),
            f.unidades.map(u => `${u.placa}${u.color ? " · " + u.color : ""}`)
              .join(" · "),
            /* Lo que la central ve de su camioneta no puede ser sorpresa
               (seccion 60): se dice aqui, con cuando y para que. */
            f.unidades.some(u => u.gps && u.mia)
              ? h("div", { clase: "chico gris", style: "margin-top:4px;line-height:1.45" },
                  t("cmp_unidad_gps"))
              : null)
        : null,
      f.companeros.length
        ? h("div", { clase: "dato" },
            h("span", { clase: "clave" }, t("cmp_con")),
            ...f.companeros.map(c => h("div", {},
              `${c.nombre}${c.rol ? " · " + c.rol : ""} `,
              c.telefono
                ? h("a", { href: `tel:${c.telefono}` }, c.telefono) : null)))
        : null),

    marcados(f),
  );

  /* "Voy en camino", para quien abre la app sin esperar el aviso.
     Solo mientras falte marcar la llegada: despues no tiene sentido.
     Es un toque y lo unico que manda es donde esta. */
  if (paso === "llegada_origen") {
    caja.append(h("div", { clase: "marco" },
      h("button", { clase: "claro", onclick: (e) => decirQueVoy(e, f) },
        t("cmp_voy_en_camino")),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        t("cmp_voy_en_camino_pie")
        + (f.unidades.some(u => u.gps && u.mia)
             ? ` ${t("cmp_voy_en_camino_gps")}` : ""))));
  }

  /* Un paso a la vez. Seis botones son seis oportunidades de marcar el
     equivocado con prisa.

     Si ese paso ya esta marcado y esperando salir, el boton no se
     vuelve a ofrecer: durante esos segundos la pantalla todavia trae el
     dato del servidor --que no sabe nada-- y el dedo volveria. */
  if (paso && enCola(f.jornada_id, paso)) {
    caja.append(h("div", { clase: "marco" },
      h("button", { disabled: "disabled" }, t("cmp_marca_enviando"))));
  } else if (paso) {
    caja.append(h("div", { clase: "marco" },
      h("button", { onclick: (e) => marcar(e, f, paso) },
        hitos()[paso].texto),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        paso === "llegada_origen"
          ? t("cmp_ventana_marca")
              .replace("{abre}", hora(f.ventana.abre))
              .replace("{cierra}", hora(f.ventana.cierra))
          : "")));
  }

  /* Los movimientos del servicio en curso, con un renglon para decir
     QUE paso.

     Hasta hoy subian la hora y el lugar y nada mas: el escolta podia
     decir "sali a ruta a las 14:32, desde aqui" y no podia decir
     "salimos a ruta, el ejecutivo cambio el destino a Santa Fe". Ese
     dato se quedaba en una llamada o no existia.

     El renglon NO es obligatorio, y eso es la mitad del diseno. El de
     campo va con una mano y con prisa; un campo obligatorio se llena
     con un punto para poder seguir, y entonces la bitacora se llena de
     puntos y deja de servir. Va vacio, y quien tenga algo que decir lo
     dice.

     Sin fotos, decision de Salvador (20 sep). */
  if (f.sueltos && f.sueltos.length) {
    const nota = h("input", { type: "text", maxlength: 300,
                              placeholder: t("cmp_nota_ph") });
    /* La nota va ARRIBA de los botones. Decision de Salvador, 20 sep.
       Con los botones primero, el dedo los tocaba antes de escribir y
       la marca se iba sin nota --y la nota es lo unico de esta pantalla
       que la central no puede deducir sola--. Puesto asi, se lee de
       arriba abajo en el orden en que hay que hacerlo: cuento que pasa,
       y luego digo en que estoy. */
    caja.append(h("div", { clase: "marco" },
      nota,
      h("div", { clase: "chico gris", style: "margin:6px 0 10px" },
        t("cmp_nota_pie")),
      h("div", { clase: "fila", style: "flex-wrap:wrap" },
        ...f.sueltos.map(s => enCola(f.jornada_id, s)
          ? h("button", { clase: "claro chico", disabled: "disabled" },
              hitos()[s].corto)
          : h("button", { clase: "claro chico",
              onclick: (e) => marcar(e, f, s, nota) }, hitos()[s].corto)))));
  }

  /* La unidad se revisa cuando cambia de manos, no cada dia. Por eso
     el boton solo aparece cuando de verdad falta algo: sin revisar al
     empezar, o dejando el servicio hoy y todavia sin entregar.

     El aviso de hoy va primero y va grande. El fin de servicio no se
     marca sin esa revisión, y enterarse de eso al intentar cerrar —a las
     ocho de la noche, con el cliente en el coche— es el peor momento
     posible. Que lo sepa desde que abre la pantalla. */
  const hoy = (f.revision && f.revision.entregar_hoy) || [];
  if (hoy.length) {
    const atorado = hoy.some(u => u.sin_recepcion);
    caja.append(h("div", { clase: "marco alerta" },
      h("a", { href: `#/revision/${f.servicio_id}`, clase: "botonazo" },
        hoy.length > 1 ? t("cmp_entregar_unidades") : t("cmp_entregar")),
      h("div", { clase: "chico", style: "margin-top:8px;text-align:center" },
        atorado
          ? t("cmp_nunca_revisada")
          : t("cmp_sin_esto_fin").replace("{placas}", hoy
              .map(u => u.placa).filter(Boolean).join(", ")))));
  } else if (f.revision && f.revision.por_recibir) {
    caja.append(h("div", { clase: "marco" },
      h("a", { href: `#/revision/${f.servicio_id}`, clase: "botonazo" },
        t("cmp_revisar_antes")),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        t("cmp_rev_pie"))));
  } else if (f.revision && f.revision.por_entregar) {
    caja.append(h("div", { clase: "marco" },
      h("a", { href: `#/revision/${f.servicio_id}`, clase: "chico" },
        t("cmp_entregar_flecha"))));
  }

  if (f.hospitales && f.hospitales.length) {
    caja.append(...[h("div", { clase: "marco" },
      h("span", { clase: "clave gris chico" }, t("cmp_hospital")),
      h("div", {}, f.hospitales[0].nombre),
      f.hospitales[0].telefono
        ? h("a", { href: `tel:${f.hospitales[0].telefono}` },
            f.hospitales[0].telefono)
        : null)].filter(Boolean));
  }

  const suAgenda = agenda(f);
  if (suAgenda) caja.append(suAgenda);
  return caja;
}

/* ------------------------------------------------- la agenda del dia

   Lo que el equipo tiene planeado hoy, parada por parada. Va cerrada:
   la pantalla de las seis de la manana es para marcar la llegada, no
   para leer el dia completo. Se abre cuando hace falta --en el
   estacionamiento, antes de arrancar, o cuando el principal pregunta
   "¿que sigue?"--.

   Viaja dentro del dia guardado, asi que tambien esta sin senal. Una
   agenda que solo existe con red es una agenda que no esta cuando hace
   falta. */
function agenda(f) {
  const a = f.agenda;
  if (!a) return null;
  const paradas = a.paradas || [];
  if (!paradas.length && !a.resumen && !a.puntos) return null;

  const lista = h("div", { hidden: true, clase: "marco" });
  const abrir = h("button", { clase: "claro", style: "margin-top:10px",
    onclick: () => { lista.hidden = !lista.hidden; } },
    t("cmp_agenda"));

  if (a.resumen) {
    lista.append(h("div", { style: "margin-bottom:8px" }, a.resumen));
  }
  for (const p of paradas) {
    lista.append(...[h("div", { clase: "dato" },
      /* La hora manda el renglon: es lo que el equipo busca con el ojo
         cuando pregunta "¿a que hora nos movemos?". */
      h("span", { clase: "clave" }, p.hora || t("cmp_sin_hora")),
      h("div", {}, p.lugar),
      p.direccion ? h("div", { clase: "chico gris" }, p.direccion) : null,
      p.notas ? h("div", { clase: "chico" }, p.notas) : null)].filter(Boolean));
  }
  if (a.puntos) {
    lista.append(h("div", { clase: "chico", style: "margin-top:8px" },
      a.puntos));
  }
  lista.append(h("div", { clase: "chico gris", style: "margin-top:10px" },
    t("cmp_agenda_pie")));

  return h("div", {}, abrir, lista);
}

function marcados(f) {
  if (!f.marcados.length) return null;
  return h("div", { clase: "marco fila", style: "flex-wrap:wrap;gap:6px" },
    ...f.marcados.map(mm => h("span", {
      clase: `marca ${mm.requiere_revision ? "alerta" : "ok"}`,
    }, `${hitos()[mm.tipo] ? hitos()[mm.tipo].corto : mm.tipo} `
       + hora(mm.marcado_en)
       + (mm.diferido ? " · " + t("cmp_diferida") : ""))));
}

function tarjetaManana(f) {
  const boton = f.confirmado
    ? h("span", { clase: "marca ok" }, t("cmp_confirmado"))
    : h("button", { onclick: (e) => confirmar(e, f) },
        t("cmp_confirmar"));

  return h("div", { clase: "caja" },
    identificacion(f),
    h("div", { clase: "fila separa" },
      h("div", {},
        /* Un dia que todavia no tiene hora no enseña NINGUN dato sin
           confirmar. Decision de Salvador, 20 sep.

           La hora heredada del dia 1 sirve adentro --sin ella no hay
           ventana ni geocerca-- pero puesta aqui se lee como si alguien
           hubiera dicho 3:30, y nadie lo dijo. Con saber que hay dia,
           como ir vestido y que esta planeado alcanza; la hora y el
           punto aparecen en cuanto el principal los diga. */
        h("div", { style: "font-size:22px;font-weight:700" },
          f.hora_confirmada ? hora(f.llegar_a_las)
                            : t("cmp_hora_sin_confirmar")),
        /* Donde presentarse. La direccion escrita si la hay, y el
           enlace al mapa siempre que haya coordenadas: un punto sin
           nombre capturado se veia como si no hubiera punto. */
        f.hora_confirmada && (f.punto.direccion || f.punto.lat)
          ? h("div", { clase: "chico gris" },
              f.punto.direccion || t("cmp_sin_capturar"),
              f.punto.lat
                ? h("div", {},
                    h("a", { clase: "chico", target: "_blank",
                      href: `https://www.google.com/maps?q=${f.punto.lat},${f.punto.lon}` },
                      t("cmp_abrir_mapa")))
                : null)
          : null),
      f.mi_rol ? h("span", { clase: "marca" }, f.mi_rol) : null),
    /* La vestimenta vive aqui y no solo en la de hoy: la noche anterior
       es cuando de verdad se usa. */
    f.vestimenta
      ? h("div", { clase: "marco" },
          h("div", { clase: "dato", style: "margin:0" },
            h("span", { clase: "clave" }, t("cmp_vestimenta")),
            t(`vest_${f.vestimenta}`)))
      : null,
    /* La senal tambien: la noche anterior es cuando se ve por primera
       vez, y abrirla con red es lo que la deja guardada en el telefono
       para la manana siguiente. */
    f.senal ? h("div", { clase: "marco" }, senalDelDia(f)) : null,
    /* El inventario de la unidad tambien vive aqui. Decision de
       Salvador, 20 sep.

       Lo que se revisa es el CAMBIO DE MANOS, y el cambio de manos pasa
       cuando el agente recoge el coche: para estar a las 7:15 en el
       aeropuerto, eso es la noche anterior. Ofrecerlo solo el mismo dia
       lo empujaba a hacerlo a las cinco de la manana en un
       estacionamiento oscuro, o a no hacerlo --y una revision a medias
       no sirve para discutir un golpe tres semanas despues--. */
    /* La agenda del dia: lo unico que si esta confirmado de un dia que
       todavia no tiene hora. */
    agenda(f),
    f.revision && f.revision.por_recibir
      ? h("div", { clase: "marco" },
          h("a", { href: `#/revision/${f.servicio_id}`, clase: "botonazo" },
            t("cmp_revisar_antes")),
          h("div", { clase: "chico gris",
                     style: "margin-top:8px;text-align:center" },
            t("cmp_rev_pie_manana")))
      : null,
    h("div", { clase: "marco" }, boton));
}

/* Confirmar de una vez todo lo que falte, que es lo que pidio quien
   toco el boton del aviso.

   Miraba solo manana, porque el unico aviso con ese boton era el de la
   vispera. Ahora tambien lo trae el de "te acaban de asignar, y es
   hoy": si aqui no se mirara hoy, ese boton no haria nada y el agente
   se quedaria pensando que ya confirmo. */
/* La ventana del camino: se abre con este toque y se cierra al marcar
   la llegada o al acercarse al punto. Se le dice con todas sus letras,
   porque el día que alguien sienta que lo vigilan de más deja el
   teléfono en la guantera y se pierde justo la señal que se quería. */
async function decirQueVoy(e, f) {
  const boton = e.target;
  boton.disabled = true;
  boton.textContent = t("cmp_tomando_ubicacion");
  const donde = await ubicacion();
  if (!donde) {
    boton.disabled = false;
    boton.textContent = t("cmp_voy_en_camino");
    return alert(t("cmp_camino_sin_ubicacion"));
  }
  try {
    await api.post(`/campo/jornadas/${f.jornada_id}/en-camino`,
                   { lat: String(donde.lat), lon: String(donde.lon) });
    boton.textContent = t("cmp_camino_listo");
  } catch (err) {
    boton.disabled = false;
    boton.textContent = t("cmp_voy_en_camino");
    alert(motivo(err));
  }
}


async function vozEnCamino(hoy) {
  const suya = (hoy || []).find(f => f.siguiente === "llegada_origen")
    || (hoy || [])[0];
  if (!suya) return pintar();

  const donde = await ubicacion();
  if (!donde) {
    alert(t("cmp_camino_sin_ubicacion"));
    return pintar();
  }
  try {
    await api.post(`/campo/jornadas/${suya.jornada_id}/en-camino`,
                   { lat: String(donde.lat), lon: String(donde.lon) });
    alert(t("cmp_camino_gracias"));
  } catch (err) {
    alert(motivo(err));
  }
  pintar();
}


async function confirmarLoQueFalta(fichas) {
  const faltan = (fichas || []).filter(x => !x.confirmado);
  if (!faltan.length) return pintar();

  const fallas = [];
  for (const f of faltan) {
    try {
      await api.post(`/operacion/jornadas/${f.jornada_id}/confirmar-recurso`, {});
    } catch (err) { fallas.push(motivo(err)); }
  }
  olvidar("mi-dia");
  if (fallas.length) alert(fallas.join("\n"));
  else alert(t("cmp_confirmado_gracias"));
  pintar();
}


async function confirmar(e, f) {
  e.target.disabled = true;
  try {
    await api.post(`/operacion/jornadas/${f.jornada_id}/confirmar-recurso`, {});
    pintar();
  } catch (err) {
    alert(motivo(err));
    e.target.disabled = false;
  }
}

/* --------------------------------------------------- marcar un hito */

function ubicacion() {
  return new Promise((listo) => {
    if (!navigator.geolocation) return listo(null);
    navigator.geolocation.getCurrentPosition(
      (p) => listo({ lat: p.coords.latitude, lon: p.coords.longitude }),
      () => listo(null),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 10000 });
  });
}

async function marcar(e, f, tipo, campoNota = null) {
  /* El contacto con el principal se pregunta antes. Es la marca que
     mas cuesta deshacer: enciende el dia, fija `inicio_real` --de donde
     salen las horas que se le facturan al cliente y se le pagan a la
     gente-- y dispara los correos al principal y a quien solicito el
     servicio diciendo que el servicio ya arranco.

     Y es la mas facil de tocar por error: aparece en la misma posicion
     donde estaba el boton de la llegada, que el agente acaba de picar.
     Deshacerla despues es una correccion a mano en la central. */
  if (tipo === "contacto_ejecutivo"
      && !confirm(t("cmp_seguro_contacto"))) return;

  const boton = e.target;
  boton.disabled = true;
  const antes = boton.textContent;
  boton.textContent = t("cmp_tomando_ubicacion");

  const donde = await ubicacion();
  if (!donde && tipo === "llegada_origen") {
    boton.disabled = false;
    boton.textContent = antes;
    return alert(t("cmp_sin_ubicacion"));
  }

  /* La hora se sella AQUI, no al enviar. Si no hay senal, la marca se
     guarda con este momento y se manda despues: lo que cuenta es cuando
     paso, no cuando llego el mensaje.

     Y por eso mismo se puede retener unos segundos aunque SI haya
     senal: la hora ya no se mueve, asi que esperar no le quita un
     minuto a nadie y le da al equipo la unica ventana que tenia para
     corregir un dedazo sin llamar a la central.

     Con esto todas las marcas salen por la cola, con senal o sin ella.
     Antes habia dos caminos --envio directo, y cola solo cuando el
     directo fallaba-- y el de la cola unicamente se ejercitaba con mala
     senal, que es como se juntan los errores que nadie ve. */
  const cuerpo = {
    tipo,
    /* El instante con su zona (seccion 65). Se cortaba la "Z" y el
       servidor leia la hora UTC como hora de pared: en Mexico cada marca
       llegaba seis horas en el futuro. */
    marcado_en: new Date().toISOString(),
    ...(donde ? { lat: String(donde.lat), lon: String(donde.lon) } : {}),
    /* La nota viaja DENTRO de la marca, no aparte. Mandarla en una
       segunda peticion seria perderla justo cuando mas importa: sin
       senal, la marca se encola entera y la nota se va con ella. Y al
       deshacer se va con ella tambien: una nota huerfana de un
       movimiento que no ocurrio no le sirve a nadie. */
    ...(campoNota && campoNota.value.trim()
      ? { nota: campoNota.value.trim() } : {}),
  };
  if (campoNota) campoNota.value = "";

  encolar({ jornada_id: f.jornada_id, cuerpo,
            sale_en: Date.now() + ESPERA_DESHACER * 1000 });
  pintar();
}

/* ------------------------------------------------- deshacer la marca

   Ocho segundos y un boton. No un dialogo antes: un "estas seguro" se
   contesta que si por reflejo cuando se va con prisa, y ademas tapa la
   pantalla justo cuando hay que mirarla. La unica pregunta previa que
   se queda es la del contacto con el principal, que enciende el
   servicio y manda correos al cliente.

   La franja va fija abajo, que es donde el pulgar acaba de estar, y
   nunca encima del boton de panico. */

const ESPERA_DESHACER = 8;

let relojDeshacer = null;

function franjaDeshacer() {
  /* El reloj se apaga SIEMPRE al repintar. Si no, deshacer dejaba
     corriendo el tic anterior sobre un renglon que ya no existe, y ese
     fantasma seguia llamando al envio cada segundo. */
  clearInterval(relojDeshacer);
  const suya = retenida();
  if (!suya || !suya.cuerpo) return null;

  const tipo = suya.cuerpo.tipo;
  const corto = hitos()[tipo] ? hitos()[tipo].corto : tipo;
  const cuando = suya.cuerpo.marcado_en
    ? hora(conZona(suya.cuerpo.marcado_en)) : "";
  const pie = h("div", { clase: "chico" });

  const deshacer = h("button", { clase: "claro chico",
    onclick: () => {
      sacar(suya.id);
      mensajeCorto(t("cmp_marca_deshecha"));
      pintar();
    } }, t("cmp_deshacer"));

  const franja = h("div", { clase: "deshacer" },
    h("div", {},
      h("b", {}, `✓ ${corto}${cuando ? " · " + cuando : ""}`),
      pie),
    deshacer);

  /* El reloj vive aqui y no en el repintado general: repintar la
     pantalla entera cada segundo tiraria lo que el equipo este
     escribiendo, que es justo lo que el resto de la app cuida. */
  const tic = () => {
    const faltan = suya.sale_en
      ? Math.ceil((suya.sale_en - Date.now()) / 1000) : 0;
    if (faltan > 0) {
      pie.textContent = t("cmp_marca_sale_en").replace("{n}", faltan);
      return;
    }
    pie.textContent = t("cmp_marca_en_cola");
    clearInterval(relojDeshacer);
    sincronizar(true);
  };
  tic();
  relojDeshacer = setInterval(tic, 1000);
  return franja;
}

/* Un aviso que no detiene la mano. `alert` hay que cerrarlo, y aqui lo
   que se dice no necesita respuesta. */
function mensajeCorto(texto) {
  const caja = h("div", { clase: "deshacer dicho" }, h("b", {}, texto));
  document.body.append(caja);
  setTimeout(() => caja.remove(), 2600);
}

/* Una marca que ya esta en el telefono, esperando salir. La tarjeta la
   usa para no ofrecer otra vez el mismo paso: sin esto, durante esos
   segundos el boton sigue ahi y el dedo vuelve. */
function enCola(jornada_id, tipo) {
  return pendientes().some(x => x.jornada_id === jornada_id
    && x.cuerpo && x.cuerpo.tipo === tipo);
}

/* ------------------------------------------------------- la senal */

/* La senal con la que el principal reconoce al equipo: una palabra, una
   imagen o las dos. La captura el consultor en el servicio y sale en el
   task sheet; aqui es lo que se levanta en la pantalla a la salida del
   filtro. Pedido de Salvador, 22 sep.

   La imagen NO viaja dentro de la ficha del dia --puede pesar megas y
   la ficha vive en localStorage, que no los aguanta--. Se baja aparte,
   con la sesion puesta, y se guarda en `caches`, que si aguanta y que
   el trabajador de fondo respeta al cambiar de version (ver sw.js).
   Donde se usa no hay barras: por eso se baja al cargar el dia y no al
   abrirla. */
const SENAL_CACHE = "centauro-senal";
const senalesEnMemoria = new Map();
const SENAL_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
  + 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
  + '<rect x="3" y="4" width="18" height="12" rx="2"/>'
  + '<path d="M12 16v4M8 20h8"/></svg>';

function rutaDeLaSenal(servicioId) {
  return `/campo/servicios/${servicioId}/senal/imagen`;
}

async function cacheDeSenales() {
  try { return ("caches" in window) ? await caches.open(SENAL_CACHE) : null; }
  catch { return null; }
}

/* Baja la imagen con la sesion puesta --una etiqueta <img> no manda el
   token, y el token nunca va en la direccion-- y la guarda. */
async function bajarSenal(servicioId) {
  const ruta = rutaDeLaSenal(servicioId);
  const cab = sesion.token ? { Authorization: `Bearer ${sesion.token}` } : {};
  const r = await fetch(ruta, { headers: cab });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const blob = await r.blob();
  senalesEnMemoria.set(servicioId, blob);
  const cache = await cacheDeSenales();
  if (cache) {
    try {
      await cache.put(ruta, new Response(blob, {
        headers: { "Content-Type": blob.type || "image/jpeg" } }));
    } catch { /* sin espacio: se queda en memoria mientras la app viva */ }
  }
  return blob;
}

/* Primero lo guardado, luego la red. Sin ninguna de las dos, null. */
async function traerSenal(servicioId) {
  if (senalesEnMemoria.has(servicioId)) return senalesEnMemoria.get(servicioId);
  const cache = await cacheDeSenales();
  if (cache) {
    const guardada = await cache.match(rutaDeLaSenal(servicioId));
    if (guardada) {
      const blob = await guardada.blob();
      senalesEnMemoria.set(servicioId, blob);
      return blob;
    }
  }
  try { return await bajarSenal(servicioId); } catch { return null; }
}

function guardarSenales(fichas) {
  for (const f of fichas) {
    if (!f.senal || !f.senal.imagen) continue;
    traerSenal(f.servicio_id).catch(() => {});
  }
}

/* El renglon de la tarjeta: el icono, y debajo la nota del consultor
   --"a la salida del filtro"-- o, si no dejo nota, cuando se usa. */
function senalDelDia(f) {
  if (!f.senal) return null;
  /* Con color, el boton trae el punto del color y su nombre: se sabe
     que buscar antes de abrirla. */
  const color = f.senal.color;
  const detalle = [color ? t(`color_${color.clave}`) : null,
                   f.senal.texto || null].filter(Boolean);
  return h("div", { clase: "dato" },
    h("span", { clase: "clave" }, t("cmp_senal")),
    h("button", { clase: "claro chico senal-boton",
                  onclick: (e) => { e.preventDefault(); abrirSenal(f); } },
      color ? h("span", { clase: "senal-punto", style: `background:${color.hex}` })
            : h("span", { clase: "senal-icono", html: SENAL_SVG }),
      [t("cmp_senal_ver"), ...detalle].join(" · ")),
    h("div", { clase: "chico gris", style: "margin-top:6px" },
      f.senal.nota || t("cmp_senal_pie")));
}

let senalAbierta = null;

/* A pantalla completa: blanco, y la imagen ocupando todo lo que el
   telefono de, vertical u horizontal. Si solo hay palabra, la palabra
   en letras enormes; si hay las dos, la imagen arriba y la palabra
   abajo. Mientras esta abierta la pantalla no se apaga: el equipo la
   sostiene en alto esperando a que salga el principal. */
async function abrirSenal(f) {
  cerrarSenal();
  const pantalla = h("div", { clase: "senal-pantalla", onclick: cerrarSenal });
  const cerrar = h("button", {
    clase: "senal-cerrar", "aria-label": t("cmp_senal_cerrar"),
    onclick: (e) => { e.stopPropagation(); cerrarSenal(); } }, "✕");
  pantalla.append(cerrar);
  document.body.append(pantalla);
  document.body.classList.add("senal-abierta");
  const abierta = { nodo: pantalla, url: null, candado: null, alGirar: null };
  senalAbierta = abierta;

  /* El color llena la pantalla; la letra encima viene decidida con el
     color, para que se lea sobre amarillo igual que sobre morado. */
  if (f.senal.color) {
    pantalla.style.background = f.senal.color.hex;
    pantalla.style.color = f.senal.color.letra;
  }

  try {
    if (navigator.wakeLock) {
      abierta.candado = await navigator.wakeLock.request("screen");
    }
  } catch { /* sin permiso o sin soporte: se muestra igual */ }

  const partes = [];
  if (f.senal.imagen) {
    const espera = h("div", { clase: "senal-texto chico" }, t("cmp_senal_cargando"));
    pantalla.append(espera);
    const blob = await traerSenal(f.servicio_id);
    if (senalAbierta !== abierta) return;        // la cerraron mientras cargaba
    espera.remove();
    if (blob) {
      abierta.url = URL.createObjectURL(blob);
      partes.push(h("img", {
        clase: "senal-imagen" + (f.senal.texto ? " con-texto" : ""),
        src: abierta.url, alt: f.senal.texto || "" }));
    } else {
      partes.push(h("div", { clase: "senal-aviso" }, t("cmp_senal_sin_guardar")));
    }
  }
  if (f.senal.texto) {
    partes.push(h("div", {
      clase: "senal-texto" + (f.senal.imagen ? " con-imagen" : "") }, f.senal.texto));
  }
  pantalla.append(...partes);

  if (f.senal.texto && !f.senal.imagen) {
    const texto = pantalla.querySelector(".senal-texto");
    abierta.alGirar = () => ajustarSenal(texto);
    window.addEventListener("resize", abierta.alGirar);
    ajustarSenal(texto);
  }
}

/* La palabra lo mas grande que quepa, y no mas. */
function ajustarSenal(nodo) {
  if (!nodo) return;
  let tam = Math.round(Math.min(window.innerWidth, window.innerHeight) * 0.34);
  nodo.style.fontSize = `${tam}px`;
  const cabe = () => nodo.scrollHeight <= window.innerHeight * 0.88;
  while (!cabe() && tam > 28) {
    tam -= 4;
    nodo.style.fontSize = `${tam}px`;
  }
}

function cerrarSenal() {
  if (!senalAbierta) return;
  const { nodo, url, candado, alGirar } = senalAbierta;
  senalAbierta = null;
  nodo.remove();
  document.body.classList.remove("senal-abierta");
  if (alGirar) window.removeEventListener("resize", alGirar);
  if (url) URL.revokeObjectURL(url);
  if (candado) candado.release().catch(() => {});
}

/* ------------------------------------------------------- el panico */

function botonPanico(f, central) {
  return h("div", { clase: "caja urgente" },
    h("button", { clase: "panico", onclick: () => panico(f, central) },
      t("cmp_emergencia")),
    h("div", { clase: "chico gris", style: "margin-top:10px;text-align:center" },
      t("cmp_emergencia_pie")),
    /* Cuando algo se rompe —la app, la señal, el servicio— la salida es
       llamar. Decir "llama a la central" sin dar el número es no decir
       nada. */
    central && central.telefono
      ? h("a", { href: `tel:${central.telefono}`, style: "text-decoration:none" },
          h("button", { clase: "claro", style: "margin-top:10px" },
            t("cmp_llamar_central").replace("{tel}", central.telefono)))
      : null);
}

async function panico(f, central) {
  if (!confirm(t("cmp_confirmar_panico"))) return;
  const donde = await ubicacion();
  try {
    await api.post("/contingencia/alertas", {
      canal: "boton_app",
      jornada_id: f ? f.jornada_id : null,
      ...(donde ? { lat: String(donde.lat), lon: String(donde.lon) } : {}),
    });
    alert(t("cmp_alerta_enviada"));
  } catch (err) {
    const tel = central && central.telefono
      ? t("cmp_panico_al").replace("{tel}", central.telefono) : "";
    alert(t("cmp_panico_falla")
      .replace("{error}", err.message)
      .replace("{tel}", tel));
    if (central && central.telefono) location.href = `tel:${central.telefono}`;
  }
}

/* ----------------------------------------------------- mis viaticos */

async function pantallaViaticos() {
  cargando();
  let r;
  try { r = await traer("viaticos", () => api.get("/campo/mis-viaticos")); }
  catch (err) { return conBarra(aviso(motivo(err), "grave")); }
  const d = r.datos;

  const cuerpo = [h("h1", {}, t("cmp_viaticos")),
    r.de_memoria ? sinLinea(r.en) : null,
    h("p", { clase: "gris chico" },
      t("cmp_viaticos_pie"))];

  if (!d.servicios.length) {
    cuerpo.push(h("div", { clase: "vacio" },
      (d.cerrados || []).length ? t("cmp_viaticos_al_dia")
                                : t("cmp_sin_viaticos")));
  }

  for (const s of d.servicios) cuerpo.push(tarjetaViatico(s));

  /* Lo cerrado, plegado y abajo. No se borra --es su dinero y tiene
     derecho a consultarlo-- pero tampoco estorba: al ano son doscientos
     servicios y el unico que importa es el que todavia le corre el
     plazo. */
  if ((d.cerrados || []).length) {
    const lista = h("div", { hidden: true });
    for (const s of d.cerrados) lista.append(tarjetaViatico(s));
    cuerpo.push(
      h("button", { clase: "claro", style: "margin-top:14px",
        onclick: () => { lista.hidden = !lista.hidden; } },
        t("cmp_ver_cerrados").replace("{n}", d.cerrados.length)),
      lista);
  }

  conBarra(...cuerpo);
}

/* Con qué depósito le llegó el dinero.

   Es la pregunta que hoy termina en una llamada al consultor —"¿ya me
   depositaron?"— y la referencia es con lo que puede reclamarle al
   banco si el dinero no aparece. Cada quien ve únicamente el suyo. */
function depositos(servicio) {
  const filas = servicio.depositos || [];
  if (!filas.length) return [];
  return [h("div", { clase: "marco", style: "margin-top:12px" },
    h("div", { clase: "gris chico", style: "margin-bottom:6px" },
      filas.length === 1 ? t("cmp_tu_deposito") : t("cmp_tus_depositos")),
    ...filas.map(d => h("div", { clase: "fila separa",
                                 style: "margin-bottom:6px" },
      h("div", {},
        h("b", { clase: "num" },
          `$${Number(d.monto).toLocaleString(local())}`),
        d.cuando
          ? h("div", { clase: "chico gris" },
              new Date(d.cuando).toLocaleDateString(local()))
          : null,
        d.referencia
          ? h("div", { clase: "chico gris num" },
              t("cmp_ref").replace("{ref}", d.referencia))
          : null),
      d.tiene_comprobante
        ? h("a", { clase: "chico", target: "_blank",
                   href: `/viaticos/depositos/${d.id}/comprobante` },
            t("cmp_ver_comprobante"))
        : h("span", { clase: "chico gris" }, t("cmp_sin_comprobante")))))];
}

function renglon(clave, valor, tono = "") {
  return h("div", { clase: "fila separa", style: "margin-bottom:8px" },
    h("span", { clase: "gris chico" }, clave),
    h("b", { clase: `num ${tono}`.trim() }, valor));
}

/* -------------------------------------------------------- mis pagos */

async function pantallaPagos() {
  cargando();
  let r;
  try { r = await traer("pagos", () => api.get("/campo/mis-comisiones")); }
  catch (err) { return conBarra(aviso(motivo(err), "grave")); }
  const d = r.datos;

  const cuerpo = [h("h1", {}, t("cmp_pagos")),
    h("p", { clase: "gris chico", style: "margin:2px 0 14px" }, t("cmp_pagos_pie")),
    r.de_memoria ? sinLinea(r.en) : null];

  /* Lo que va corriendo se enseña como lo que es: una cuenta que
     todavia se puede mover. Un numero que baja sin aviso es la forma
     mas rapida de que el equipo deje de creerle a la app. */
  const curso = d.en_curso;
  cuerpo.push(h("div", { clase: "caja" },
    h("span", { clase: "gris chico" }, t("cmp_semana_curso")),
    h("div", { clase: "grande" },
      `$${(curso.total || 0).toLocaleString(local())}`),
    h("div", { clase: "chico gris" }, curso.nota),
    ...(curso.dias || []).map(x => h("div", {
      clase: "fila separa chico", style: "margin-top:8px" },
      h("span", {}, `${x.fecha} · ${x.rol || ""}`),
      h("span", { clase: "num" }, `$${x.monto.toLocaleString(local())}`)))));

  /* El bono del mes vencido, arriba de los cortes semanales. Va aqui y
     no en "yo" porque es dinero, y porque el dia que no llega es el dia
     que se pregunta aqui.

     Se ensena con su estado en palabras y con la frase que explica cada
     punto perdido, con su fecha. Enterarse el dia 3 de por que no hubo
     bono es una conversacion; enterarse el dia 5 por un deposito que no
     llego es un pleito. */
  try {
    const b = await api.get("/campo/mi-bono");
    if (b.hay) cuerpo.push(tarjetaBono(b));
  } catch { /* sin bono calculado la pantalla sigue sirviendo */ }

  if (!d.cortes.length) {
    cuerpo.push(h("div", { clase: "vacio" }, t("cmp_sin_cortes")));
  }

  for (const c of d.cortes) {
    const abierto = h("div", { hidden: true, clase: "marco" },
      ...c.dias.map(x => h("div", { clase: "fila separa chico",
                                    style: "margin-bottom:6px" },
        h("span", {}, x.descripcion),
        h("span", { clase: "num" }, `$${x.monto.toLocaleString(local())}`))));

    cuerpo.push(h("div", { clase: "caja" },
      h("div", { clase: "fila separa" },
        h("div", {},
          h("b", {}, t("cmp_semana_del").replace("{fecha}", c.semana_del)),
          h("div", { clase: "chico gris" },
            c.pagado ? t("cmp_pagado") : t("cmp_calculado_no_pagado"))),
        h("div", { style: "text-align:right" },
          h("b", { clase: "num" }, `$${c.total.toLocaleString(local())}`),
          h("div", {},
            h("span", { clase: `marca ${c.pagado ? "ok" : "alerta"}` },
              c.pagado ? t("cmp_marca_pagado")
                       : t("cmp_marca_pendiente"))))),
      h("button", { clase: "claro chico", style: "margin-top:10px",
        onclick: () => { abierto.hidden = !abierto.hidden; } },
        t("cmp_ver_dias")),
      abierto));
  }
  conBarra(...cuerpo);
}

function tarjetaBono(b) {
  const abierto = h("div", { hidden: true, clase: "marco" },
    ...b.criterios.map(c => h("div", { clase: "renglon_bono" },
      h("span", { clase: `punto ${c.cumplido ? "si" : c.aplica ? "no" : "na"}` },
        c.cumplido ? "✓" : c.aplica ? "✕" : "—"),
      h("div", {},
        h("b", {}, c.criterio),
        /* La frase con fechas: es lo unico que convierte un punto
           perdido en algo que se puede corregir el mes que entra. */
        h("div", { clase: "chico gris" }, c.detalle || "")))));

  const estado = b.pagado_en ? t("cmp_bono_depositado")
    : b.estatus === "autorizada" ? t("cmp_bono_autorizado")
    : t("cmp_bono_calculado");

  return h("div", { clase: "caja principal" },
    h("span", { clase: "gris chico" },
      `${t("cmp_bono")} · ${b.periodo}`),
    h("div", { clase: "grande" },
      `$${Number(b.bono).toLocaleString(local())}`),
    h("div", { clase: "chico" },
      h("span", { clase: `marca ${b.pagado_en ? "ok" : "alerta"}` }, estado)),
    h("div", { clase: "chico gris", style: "margin-top:6px" },
      `${b.estrellas} / ${b.estrellas_posibles} ${t("cmp_bono_estrellas")}`),
    b.incidencia
      ? h("div", { clase: "aviso grave", style: "margin-top:10px" },
          `${t("cmp_bono_anulado")} · ${b.incidencia.fecha}`)
      : null,
    h("button", { clase: "claro chico", style: "margin-top:10px",
      onclick: () => { abierto.hidden = !abierto.hidden; } },
      t("cmp_bono_ver")),
    abierto);
}

/* ------------------------------------------------------------- yo */

async function pantallaYo() {
  cargando();
  const cuerpo = [h("h1", {},
    sesion.usuario ? sesion.usuario.nombre : t("cmp_yo")),
    h("p", { clase: "gris chico", style: "margin:2px 0 14px" }, t("cmp_yo_pie")),
  ];

  try {
    const c = await api.get("/campo/mi-calificacion");
    cuerpo.push(h("div", { clase: "caja" },
      h("span", { clase: "gris chico" }, t("cmp_calificacion")),
      h("div", { clase: "grande" }, String(c.calificacion ?? "—")),
      h("div", { clase: "chico gris" },
        t("cmp_horas_confianza")
          .replace("{horas}", c.horas_en_centauro || 0)
          .replace("{confianza}", c.confianza || "—")),
      ...(c.dimensiones || []).filter(x => x.aplica).map(x =>
        h("div", { clase: "fila separa chico", style: "margin-top:8px" },
          h("span", {}, x.dimension),
          h("span", { clase: "num" }, String(x.valor ?? "—"))))));
  } catch { /* sin tablero todavia */ }

  try {
    const cap = await api.get("/campo/mi-capacitacion");
    const caja = h("div", { clase: "caja" },
      h("span", { clase: "gris chico" }, t("cmp_capacitacion")));
    if (!cap.cursos.length) {
      caja.append(h("div", { clase: "gris chico", style: "margin-top:8px" },
        t("cmp_sin_cursos")));
    }
    for (const x of cap.cursos) {
      caja.append(h("div", { clase: "fila separa", style: "margin-top:10px" },
        h("div", {}, h("div", {}, x.nombre),
          h("div", { clase: "chico gris" }, x.institucion || "")),
        x.vencida
          ? h("span", { clase: "marca grave" }, t("cmp_vencida"))
          : x.por_vencer
            ? h("span", { clase: "marca alerta" },
                t("cmp_dias_faltan").replace("{n}", x.dias_para_vencer))
            : h("span", { clase: "marca ok" }, t("cmp_vigente"))));
    }
    cuerpo.push(caja);
  } catch { /* sin capacitacion cargada */ }

  cuerpo.push(bloqueAvisos());

  conBarra(...cuerpo);
}

/* Salir vive ARRIBA y chico, en el encabezado, lejos del pulgar.

   Estaba al final del contenido, y el boton de panico se pinta justo
   despues --en todas las pantallas, encima de la barra-- asi que los dos
   quedaban pegados en la zona que mas se toca. Los dos peores errores
   posibles estaban a un centimetro uno del otro: pedir un equipo de
   respuesta por querer salir, o cerrar la sesion en una emergencia y
   quedarse sin app hasta que haya red.

   Y su frecuencia es opuesta: salir pasa una vez, cuando el telefono
   cambia de manos; el panico tiene que estar donde cae el dedo sin
   pensar. Asi que uno sube y se hace chico, y el otro se queda solo
   abajo. */
function botonSalir() {
  return h("button", { clase: "claro chico", onclick: () => {
    /* Se pregunta antes: tocarlo sin querer a las seis de la manana y
       sin senal deja la app inservible hasta que haya red, porque para
       volver a entrar hace falta el servidor.

       Y al salir se borra lo guardado --el dia de alguien mas no se
       queda en un telefono que cambia de manos-- INCLUIDA LA COLA. Se
       quedaba: las marcas pendientes del anterior se intentaban mandar
       despues con el token del siguiente. */
    if (pendientes().length
        && !confirm(t("cmp_salir_con_pendientes")
                      .replace("{n}", pendientes().length))) return;
    if (!confirm(t("cmp_confirmar_salir"))) return;
    olvidar();
    limpiar();
    sesion.token = null; sesion.usuario = null; location.hash = ""; pintar();
  } }, t("cmp_salir"));
}

/* ---------------------------------------------------------- armazon */

function cargando() {
  /* Con la barra y el boton rojo puestos. Antes se reemplazaba la
     pantalla entera: con media barra de senal la app se quedaba en "Un
     momento..." sin navegacion y --lo grave-- sin forma de pedir
     ayuda. Ahora lo unico que espera es el contenido. */
  conBarra(h("div", { clase: "vacio" }, t("cmp_un_momento")));
}

/* Lo que se le enseña cuando algo falla.

   El navegador dice "Failed to fetch" --en ingles y sin decir que
   hacer-- justo cuando se cae la senal, que es cuando menos sirve. El
   codigo 0 lo pone `api.js` para las fallas de red y de tiempo. */
function motivo(err) {
  if (!err || !err.codigo) return t("cmp_error_red");
  return err.message;
}


/* El boton rojo va en TODAS las pantallas, como dice la cabecera de
   este archivo. Vivia solo en Hoy: quien estaba en Viaticos, en Pagos o
   a medio llenar una revision tenia que navegar para pedir ayuda.

   Los datos salen de lo ultimo que se supo del dia. Si nunca se supo
   --primer arranque sin senal-- el boton sale igual: manda la alerta
   sin jornada, que es mejor que no mandarla. */
function panicoDeSiempre() {
  const guardado = recordar("mi-dia");
  const datos = (guardado && guardado.datos) || {};
  const hoy = datos.hoy || [];
  return botonPanico(hoy[0], datos.central);
}


function conBarra(...cuerpo) {
  const enlace = (ruta, icono, texto) => h("a", {
    href: `#/${ruta}`,
    clase: vista === ruta ? "activo" : "",
  }, h("span", { clase: "icono" }, icono), texto);

  /* `replaceChildren` no es `h`: lo que recibe y no es un nodo lo
     convierte a texto, y un `null` se pinta literalmente como "null".
     Las dos bandas devuelven `null` cuando no hay nada que avisar --que
     es casi siempre-- asi que en la cima de cada pantalla salia
     "nullnull". Se filtra antes de entregar. */
  /* En la cima de cada pantalla va la marca, no un hueco. El agente
     abre la app de madrugada y lo primero que ve tiene que decirle de
     quien es el turno que esta por empezar.

     Sale del mismo PNG que el icono de la app y que el icono de los
     avisos --el service worker ya lo guarda--, asi que en el
     estacionamiento sin senal tambien se ve. */
  const encabezado = h("div", { clase: "encabezado" },
    h("img", { clase: logoEmpresa ? "logo ancho" : "logo",
               src: logoEmpresa || "/app/icono-192.png",
               alt: t("cmp_marca") }),
    vista === "yo" ? botonSalir() : null);

  raiz().replaceChildren(...[
    encabezado,
    bandaRechazadas(),
    bandaPendientes(),
    ...cuerpo,
    panicoDeSiempre(),
    /* Va fija abajo y nunca encima del boton rojo: si alguna vez se
       pelean por el espacio, gana el panico. */
    franjaDeshacer(),
    h("div", { clase: "barra" },
      enlace("hoy", "◉", t("cmp_nav_hoy")),
      enlace("viaticos", "▤", t("cmp_nav_viaticos")),
      enlace("pagos", "≡", t("cmp_nav_pagos")),
      enlace("yo", "☺", t("cmp_nav_yo"))),
  ].filter(Boolean));

  // Cada vez que se pinta algo se intenta vaciar la cola: si volvio la
  // senal mientras miraba otra pantalla, sale sola.
  sincronizar(true);
}


/* ---------------------------------------------- comprobar un gasto

   El que comprueba es un agente parado en una gasolinera con el ticket
   en la mano. Lo que trae es la camara del telefono, no un archivo que
   subir a ningun lado: por eso el flujo es foto, monto, concepto, y ya.

   La foto se reduce en el telefono antes de salir. Un telefono saca
   fotos de cuatro megas y subirlas con media barra de senal no termina
   nunca; mil seiscientos pixeles dejan un ticket perfectamente legible
   en trescientos kilobytes. */

const conceptos = () => [
  ["alimentos", t("cmp_c_alimentos")],
  ["combustible", t("cmp_c_combustible")],
  ["casetas", t("cmp_c_casetas")],
  ["traslado_personal", t("cmp_c_traslado")],
  ["hospedaje", t("cmp_c_hospedaje")],
  ["otros", t("cmp_c_otros")],
];

/* La tarjeta de un servicio en la pestana de Viaticos. Es la misma para
   lo pendiente y para lo cerrado: un viatico cerrado se lee igual, con
   sus numeros en cero y sin botones que ofrecer. */
/* El plazo, dicho como se vive (seccion 59). Antes de terminar el
   servicio no hay fecha: el plazo de 24 horas corre al terminar. Ya
   terminado, cuando vence y cuanto le queda, con la hora del pais del
   servicio. Pasado, vencido, y lo que eso quiere decir. */
function cuandoVence(s) {
  if (!s.limite) {
    return { marca: h("span", { clase: "marca" }, t("cmp_en_servicio")),
             pie: h("div", { clase: "chico gris" }, t("cmp_plazo_al_terminar")) };
  }
  const limite = new Date(s.limite);
  const hoy = new Date(s.momento || Date.now());
  const dias = Math.round((new Date(limite.toDateString())
                           - new Date(hoy.toDateString())) / 86400000);
  const hh = `${String(limite.getHours()).padStart(2, "0")}:`
           + `${String(limite.getMinutes()).padStart(2, "0")}`;
  const cuando = dias === 0 ? t("cmp_hoy") : dias === 1 ? t("cmp_manana_")
    : dias === -1 ? t("cmp_ayer")
    : limite.toLocaleDateString(local(), { weekday: "short", day: "numeric" });
  const minutos = s.minutos ?? 0;
  if (s.vencido || minutos < 0) {
    return { marca: h("span", { clase: "marca grave" }, t("cmp_vencido")),
             pie: h("div", { clase: "chico rojo", style: "font-weight:650" },
               t("cmp_vencio").replace("{cuando}", cuando).replace("{hora}", hh)) };
  }
  const queda = minutos < 60 ? t("cmp_n_min").replace("{n}", minutos)
                             : t("cmp_n_h").replace("{n}", Math.floor(minutos / 60));
  return { marca: h("span", { clase: "marca alerta" }, queda),
           pie: h("div", { clase: "chico ambar", style: "font-weight:650" },
             t("cmp_vence").replace("{cuando}", cuando).replace("{hora}", hh)
               .replace("{queda}", queda)) };
}

function tarjetaViatico(s) {
  const plazo = s.por_comprobar > 0 ? cuandoVence(s) : null;
  return h("div", { clase: `caja ${s.vencido ? "urgente" : ""}` },
      h("div", { clase: "fila separa" },
        /* El periodo, cuando la tarjeta es de un implantado: dos meses
           del mismo servicio son dos depositos y dos cuentas. */
        h("div", {}, h("b", {}, s.folio),
          s.periodo ? h("span", { clase: "marca" }, s.periodo) : null,
          h("div", { clase: "chico gris" }, s.cliente || "")),
        plazo ? plazo.marca : null),
      h("div", { clase: "marco" },
        renglon(t("cmp_te_depositaron"),
                `$${s.entregado.toLocaleString(local())}`),
        /* Lo autorizado que sigue en finanzas, dicho aparte y con su
           nombre. Sumarlo arriba era decirle a alguien que ya tenia un
           dinero que no habia salido del banco. */
        s.por_depositar > 0
          ? renglon(t("cmp_por_depositar"),
                    `$${s.por_depositar.toLocaleString(local())}`, "ambar")
          : null,
        renglon(t("cmp_has_comprobado"),
                `$${s.comprobado.toLocaleString(local())}`),
        /* Lo que ya regreso, confirmado por finanzas. Va pegado a lo
           comprobado porque los dos apagan la misma deuda: sin este
           renglon, "te depositaron 285, comprobaste 270, no te falta
           nada" es una cuenta que no cierra y manda a llamar al
           consultor para preguntar por quince pesos. */
        s.devuelto > 0
          ? renglon(t("cmp_devolviste"),
                    `$${s.devuelto.toLocaleString(local())}`, "verde")
          : null,
        renglon(t("cmp_te_falta_comprobar"),
                `$${s.por_comprobar.toLocaleString(local())}`,
                s.por_comprobar > 0 ? "ambar" : "verde"),
        /* Lo que dijo que transfirio y finanzas todavia no ha visto
           entrar. Se dice con su nombre y no se descuenta de arriba:
           hasta que se confirme, ese dinero sigue siendo suyo. */
        s.devolucion_en_revision > 0
          ? renglon(t("cmp_devolucion_en_revision"),
                    `$${s.devolucion_en_revision.toLocaleString(local())}`,
                    "ambar")
          : null),
      plazo ? plazo.pie : null,
      ...depositos(s),
      s.por_comprobar > 0 ? comprobar(s) : null,
      s.por_devolver > 0 ? devolver(s) : null);
}


/* --------------------------------------------- la hora de manana

   Se pregunta al cerrar el dia y no antes: es cuando el principal lo
   dice, en la puerta del hotel.

   El punto se toma del GPS porque quien contesta esta parado en el.
   Sin coordenadas no hay geocerca, y sin geocerca manana no va a poder
   marcar su llegada: una direccion escrita a mano deja el dia a
   medias. Por eso el boton de tomar la ubicacion es lo primero. */
function pantallaManana(manana) {
  const hora = h("input", { type: "time" });
  const direccion = h("input", { type: "text",
                                 placeholder: t("cmp_donde_manana_ph") });
  const nota = h("input", { type: "text",
                            placeholder: t("cmp_algo_mas") });
  const vista = h("div", { clase: "chico gris", style: "margin-top:6px" });
  let punto = null;

  /* Dos caminos, y ninguno se da por hecho.

     Que el dia siguiente arranque donde termino el de hoy es lo mas
     comun --se deja al principal en el hotel y ahi lo recogen-- pero NO
     es una regla: puede ser en su casa, en otra oficina, en el
     aeropuerto. Preguntarlo con un boton que dice "aqui mismo" y ya,
     seria convertir la costumbre en ley.

     El camino de "aqui mismo" toma el GPS y con eso el dia queda
     completo: hay geocerca y manana se puede marcar la llegada. El otro
     deja la direccion escrita y se dice con todas sus letras que a la
     central le toca ponerle el pin, porque sin pin no hay geocerca. */
  const direccionCaja = h("div", { hidden: true, style: "margin-top:8px" },
    direccion,
    h("div", { clase: "chico gris", style: "margin-top:6px" },
      t("cmp_otro_lado_pie")));

  const aqui = h("button", { clase: "claro chico", onclick: async (e) => {
    e.target.disabled = true;
    direccionCaja.hidden = true;
    vista.textContent = t("cmp_tomando_ubicacion");
    const donde = await ubicacion();
    e.target.disabled = false;
    if (!donde) return vista.textContent = t("cmp_camino_sin_ubicacion");
    punto = donde;
    vista.textContent = t("cmp_punto_tomado");
  } }, t("cmp_aqui_mismo"));

  const otro = h("button", { clase: "claro chico", onclick: () => {
    punto = null;
    vista.textContent = "";
    direccionCaja.hidden = false;
    direccion.focus();
  } }, t("cmp_en_otro_lado"));

  const tomar = h("div", {},
    h("div", { clase: "fila", style: "gap:8px;flex-wrap:wrap" }, aqui, otro));

  const guardar = h("button", { style: "margin-top:12px",
    onclick: async (e) => {
      if (!hora.value) return alert(t("cmp_falta_hora"));
      e.target.disabled = true;
      try {
        await api.post(`/campo/jornadas/${manana.jornada_id}/manana`, {
          hora: hora.value.length === 5 ? `${hora.value}:00` : hora.value,
          direccion: direccion.value.trim() || null,
          lat: punto ? String(punto.lat) : null,
          lon: punto ? String(punto.lon) : null,
          nota: nota.value.trim() || null,
        });
        alert(t("cmp_manana_guardada"));
        location.hash = "#/hoy";
        pintar();
      } catch (err) { alert(err.message); e.target.disabled = false; }
    } }, t("cmp_guardar_manana"));

  const dia = new Date(manana.fecha + "T12:00:00")
    .toLocaleDateString(local(), { weekday: "long", day: "numeric",
                                   month: "long" });

  conBarra(
    h("h1", {}, t("cmp_y_manana")),
    h("p", { clase: "gris chico" },
      t("cmp_y_manana_pie").replace("{dia}", dia)),
    h("div", { clase: "caja" },
      h("div", { clase: "campo" },
        h("label", {}, t("cmp_hora_manana")), hora),
      h("div", { clase: "campo" },
        h("label", {}, t("cmp_donde_manana")), tomar, vista, direccionCaja),
      h("div", { clase: "campo" }, h("label", {}, t("cmp_nota")), nota),
      guardar,
      /* Se puede dejar para despues: si el principal no dijo nada, no
         hay nada que inventar. El dia sigue con su hora heredada y la
         app lo dice con todas sus letras. */
      h("button", { clase: "claro chico", style: "margin-top:10px",
        onclick: () => { location.hash = "#/hoy"; pintar(); } },
        t("cmp_no_me_dijeron"))));
}


/* ------------------------------------------- devolver lo que sobro

   La otra mitad del dinero. Si sobro --o el servicio se cancelo con el
   deposito ya hecho-- la persona transfiere de vuelta y lo dice aqui,
   con la referencia del banco y la foto de la transferencia.

   Lo que declara NO se le descuenta de una vez: queda "en revision"
   hasta que finanzas lo vea entrar a la cuenta. Decirle que ya devolvio
   --y apagarle el plazo-- por un dinero que la empresa no ha visto
   seria el mismo defecto que tenia esta pantalla cuando decia "te
   depositaron" con dinero que seguia en el banco. */
function devolver(servicio) {
  const form = h("div", { hidden: true, clase: "marco" });
  const abrir = h("button", { clase: "claro", style: "margin-top:12px",
    onclick: () => { form.hidden = !form.hidden; } },
    t("cmp_devolver"));

  const dia = document.createElement("select");
  for (const d of servicio.dias) {
    if (!(d.por_devolver > 0)) continue;
    dia.append(h("option", { value: d.viatico_id },
      `${d.fecha} · $${d.por_devolver.toLocaleString(local())}`));
  }

  const monto = h("input", { type: "number", inputmode: "decimal",
                             step: "0.01", min: "0", placeholder: "0.00" });
  const referencia = h("input", { type: "text",
                                  placeholder: t("cmp_referencia_banco") });

  const archivo = h("input", { type: "file", accept: "image/*",
                               capture: "environment" });
  const vista = h("div", { clase: "chico gris", style: "margin-top:6px" });
  let imagen = null;

  archivo.addEventListener("change", async () => {
    const f = archivo.files && archivo.files[0];
    if (!f) return;
    vista.textContent = t("cmp_preparando_foto");
    try {
      imagen = await reducir(f);
      vista.replaceChildren(h("img", {
        src: imagen,
        style: "max-width:120px;border-radius:8px;display:block;margin-top:6px",
      }));
    } catch (err) { imagen = null; vista.textContent = err.message; }
  });

  const guardar = h("button", { style: "margin-top:6px",
    onclick: (e) => mandar(e) }, t("cmp_guardar_devolucion"));

  async function mandar(e) {
    if (!monto.value || Number(monto.value) <= 0) {
      return alert(t("cmp_escribe_monto"));
    }
    e.target.disabled = true;
    try {
      await api.post(`/campo/viaticos/${dia.value}/devolucion`, {
        monto: monto.value,
        referencia: referencia.value || null,
        imagen,
      });
      alert(t("cmp_devolucion_ok"));
      pintar();
    } catch (err) {
      alert(err.message);
      e.target.disabled = false;
    }
  }

  form.append(
    h("div", { clase: "campo" }, h("label", {}, t("cmp_dia")), dia),
    h("div", { clase: "campo" }, h("label", {}, t("cmp_cuanto_devuelves")),
      monto),
    h("div", { clase: "campo" }, h("label", {}, t("cmp_referencia")),
      referencia),
    h("div", { clase: "campo" }, h("label", {}, t("cmp_foto_transferencia")),
      archivo, vista),
    guardar,
    h("div", { clase: "chico gris", style: "margin-top:8px" },
      t("cmp_devolucion_pie")));

  return h("div", {}, abrir, form);
}


function comprobar(servicio) {
  const form = h("div", { hidden: true, clase: "marco" });
  const abrir = h("button", { clase: "claro", style: "margin-top:12px",
    onclick: () => { form.hidden = !form.hidden; } },
    t("cmp_comprobar_gasto"));

  const dia = document.createElement("select");
  for (const d of servicio.dias) {
    dia.append(h("option", { value: d.viatico_id },
      `${d.fecha} · $${d.entregado.toLocaleString(local())}`));
  }
  const concepto = document.createElement("select");
  for (const [valor, texto] of conceptos()) {
    concepto.append(h("option", { value: valor }, texto));
  }

  const monto = h("input", { type: "number", inputmode: "decimal",
                             step: "0.01", min: "0", placeholder: "0.00" });
  const nota = h("input", { type: "text", placeholder: t("cmp_de_que_fue") });
  const tipo = document.createElement("select");
  tipo.append(h("option", { value: "nota" }, t("cmp_nota_ticket")),
              h("option", { value: "factura" }, t("cmp_factura")));

  /* La camara directo: `capture` abre la camara en vez del carrete, que
     es lo que se quiere cuando el ticket esta en la mano. */
  const archivo = h("input", { type: "file", accept: "image/*",
                               capture: "environment" });
  const vista = h("div", { clase: "chico gris", style: "margin-top:6px" });
  let imagen = null;

  archivo.addEventListener("change", async () => {
    const f = archivo.files && archivo.files[0];
    if (!f) return;
    vista.textContent = t("cmp_preparando_foto");
    try {
      imagen = await reducir(f);
      const kb = Math.round(imagen.length * 0.75 / 1024);
      vista.replaceChildren(
        h("img", { src: imagen, style: "max-width:120px;border-radius:8px;"
                                       + "display:block;margin-top:6px" }),
        h("div", { clase: "chico gris" },
          t("cmp_foto_lista").replace("{kb}", kb)));
    } catch (err) {
      imagen = null;
      vista.textContent = err.message;
    }
  });

  const guardar = h("button", { style: "margin-top:6px",
    onclick: (e) => mandar(e) }, t("cmp_guardar_comprobante"));

  async function mandar(e) {
    if (!monto.value || Number(monto.value) <= 0) {
      return alert(t("cmp_escribe_monto"));
    }
    e.target.disabled = true;
    try {
      const r = await api.post(`/campo/viaticos/${dia.value}/comprobante`, {
        concepto: concepto.value,
        tipo: tipo.value,
        monto: monto.value,
        descripcion: nota.value || null,
        imagen,
      });
      alert(t("cmp_comprobante_ok").replace("{monto}",
        Number(r.falta).toLocaleString(local())));
      pintar();
    } catch (err) {
      alert(err.message);
      e.target.disabled = false;
    }
  }

  form.append(
    h("div", { clase: "campo" }, h("label", {}, t("cmp_dia")), dia),
    h("div", { clase: "campo" }, h("label", {}, t("cmp_concepto")), concepto),
    h("div", { clase: "campo" }, h("label", {}, t("cmp_monto")), monto),
    h("div", { clase: "campo" }, h("label", {}, t("cmp_tipo")), tipo),
    h("div", { clase: "campo" }, h("label", {}, t("cmp_nota")), nota),
    h("div", { clase: "campo" },
      h("label", {}, t("cmp_foto_ticket")), archivo, vista),
    guardar);

  return h("div", {}, abrir, form);
}


/* Quien entro con una cuenta que no es de campo. */
const nombreRol = () => ({
  consultor: t("cmp_rol_consultor"), central: t("cmp_rol_central"),
  finanzas: t("cmp_rol_finanzas"),
  director_operaciones: t("cmp_rol_dir_operaciones"),
  director_general: t("cmp_rol_dir_general"), admin: t("cmp_rol_admin"),
  recursos_humanos: t("cmp_rol_rrhh"),
});

function otraCuenta() {
  const suyo = nombreRol()[sesion.usuario.rol] || sesion.usuario.rol;
  raiz().replaceChildren(h("div", { clase: "entrada" },
    h("div", { clase: "linea" },
      h("span", { clase: "clave" }, "AI/EP"),
      h("span", { clase: "nombre" }, t("cmp_lema"))),
    h("div", { clase: "caja principal" },
      h("h1", {}, t("cmp_otra_cuenta")),
      h("p", { clase: "gris" },
        t("cmp_entraste_como")
          .replace("{nombre}", sesion.usuario.nombre)
          .replace("{rol}", suyo)),
      h("p", { clase: "gris chico" },
        t("cmp_otra_cuenta_pie")),
      h("button", { style: "margin-top:8px", onclick: () => {
        if (pendientes().length
            && !confirm(t("cmp_salir_con_pendientes")
                          .replace("{n}", pendientes().length))) return;
        olvidar();
        limpiar();
        sesion.token = null; sesion.usuario = null;
        location.hash = ""; pintar();
      } }, t("cmp_entrar_otra")),
      h("a", { href: "/", style: "text-decoration:none" },
        h("button", { clase: "claro", style: "margin-top:10px" },
          t("cmp_ir_consola"))))));
}


/* ------------------------------------------------- avisos al telefono

   No se pide el permiso al abrir la app. Un permiso que se pide antes de
   que alguien entienda para que sirve se niega, y negado no se vuelve a
   preguntar: el navegador no da segunda oportunidad. Por eso se ofrece
   en dos momentos donde ya se entiende:

   - en "Yo", como un interruptor que se enciende cuando uno quiere
   - en la pantalla de hoy, cuando hay algo que confirmar para manana,
     que es justo el aviso que se va a recibir */

function soportaAvisos() {
  return "serviceWorker" in navigator && "PushManager" in window;
}

function estadoAvisos() {
  if (!soportaAvisos()) return "sin_soporte";
  return Notification.permission;   // default | granted | denied
}

function base64aBytes(base64) {
  const relleno = "=".repeat((4 - base64.length % 4) % 4);
  const limpio = (base64 + relleno).replace(/-/g, "+").replace(/_/g, "/");
  const crudo = atob(limpio);
  return Uint8Array.from([...crudo].map((c) => c.charCodeAt(0)));
}

async function encenderAvisos() {
  if (!soportaAvisos()) {
    return alert(t("cmp_avisos_sin_soporte"));
  }

  let llave;
  try { llave = await api.get("/campo/push/llave"); }
  catch { return alert(t("cmp_avisos_sin_llave")); }
  if (!llave.activo) {
    return alert(t("cmp_avisos_sin_configurar"));
  }

  const permiso = await Notification.requestPermission();
  if (permiso !== "granted") {
    return alert(t("cmp_avisos_sin_permiso"));
  }

  try {
    const reg = await navigator.serviceWorker.ready;
    const sus = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64aBytes(llave.llave),
    });
    const j = sus.toJSON();
    await api.post("/campo/push/suscribir", {
      endpoint: j.endpoint,
      p256dh: j.keys.p256dh,
      auth: j.keys.auth,
      agente: navigator.userAgent,
    });
    alert(t("cmp_avisos_listo"));
    pintar();
  } catch (err) {
    alert(t("cmp_avisos_falla").replace("{error}", err.message));
    pintar();
  }
}

async function probarAviso(e) {
  e.target.disabled = true;
  try {
    await api.post("/campo/push/probar", {});
    alert(t("cmp_avisos_prueba_ok"));
  } catch (err) { alert(err.message); }
  e.target.disabled = false;
}

/* Lo que el servidor sabe de este telefono. La pantalla no puede
   decidir solo con el permiso del navegador: el permiso puede estar
   concedido y la suscripcion no haberse guardado nunca —o haberla
   rotado el navegador— y entonces "Encendidos" es mentira. */
async function suscripcionDelServidor() {
  try {
    let endpoint = null;
    if (soportaAvisos() && navigator.serviceWorker) {
      const reg = await navigator.serviceWorker.ready;
      const sus = await reg.pushManager.getSubscription();
      endpoint = sus ? sus.endpoint : null;
    }
    return await api.get("/campo/push/estado"
      + (endpoint ? `?endpoint=${encodeURIComponent(endpoint)}` : ""));
  } catch { return null; }
}

/* El interruptor, en "Yo". */
function bloqueAvisos() {
  const estado = estadoAvisos();
  const caja = h("div", { clase: "caja" },
    h("span", { clase: "gris chico" }, t("cmp_avisos")));

  if (estado === "sin_soporte") {
    caja.append(h("p", { clase: "chico gris", style: "margin-top:8px" },
      t("cmp_avisos_no")));
    return caja;
  }
  if (estado === "denied") {
    caja.append(h("p", { clase: "chico gris", style: "margin-top:8px" },
      t("cmp_avisos_bloqueados")));
    return caja;
  }
  if (estado === "granted") {
    /* El permiso esta, pero eso no quiere decir que el servidor tenga a
       donde mandar. Se pregunta, y mientras llega la respuesta se dice
       lo que se sabe con certeza. */
    const linea = h("p", { clase: "chico gris", style: "margin-top:8px" },
      t("cmp_comprobando"));
    const accion = h("div", {});
    caja.append(linea, accion);

    suscripcionDelServidor().then((estado) => {
      if (estado && estado.este_telefono) {
        linea.textContent = t("cmp_avisos_encendidos");
        accion.replaceChildren(
          h("button", { clase: "claro", onclick: (e) => probarAviso(e) },
            t("cmp_aviso_prueba")));
        return;
      }
      linea.textContent = t("cmp_avisos_sin_registrar");
      accion.replaceChildren(
        h("button", { onclick: () => encenderAvisos() },
          t("cmp_reintentar")));
    });
    return caja;
  }
  caja.append(
    h("p", { clase: "chico gris", style: "margin-top:8px" },
      t("cmp_avisos_pie")),
    h("button", { onclick: () => encenderAvisos() }, t("cmp_encender_avisos")));
  return caja;
}

/* El ofrecimiento en la pantalla de hoy, solo cuando hay algo que
   confirmar: es el aviso que de verdad se va a recibir, asi que es el
   momento en que se entiende para que sirve. */
function ofrecerAvisos(hayManana) {
  if (!hayManana || estadoAvisos() !== "default") return null;
  return h("div", { clase: "caja" },
    h("p", { clase: "chico", style: "margin:0 0 10px" },
      t("cmp_avisos_pregunta")),
    h("button", { clase: "claro", onclick: () => encenderAvisos() },
      t("cmp_si_avisame")));
}


/* ================================================================
   La revision de la unidad

   El dano al vehiculo siempre aparece despues y sin dueno. Un golpe
   que nadie vio al recibir se discute tres semanas mas tarde, cuando
   ya nadie puede probar nada y el que pierde siempre es el ultimo que
   la trajo. Cuatro fotos y una firma en el momento en que la unidad
   cambia de manos son lo unico que lo resuelve, porque ese es el
   unico momento en que todavia se puede saber.

   Va por servicio, no por dia: la misma camioneta veintidos dias no
   se revisa veintidos veces. Y solo cuando cambia de manos.
   ================================================================ */

/* Los cuatro lados prueban cómo estaba la lata. El odómetro prueba el
   número: hasta hoy el kilometraje era un dato tecleado, y la cuenta que
   sale al entregar —"recorrió 1,800 km", la que nadie apunta y de la que
   después todos se acuerdan distinto— salía de dos cifras escritas de
   memoria. Al entregar, además, la ranura enseña la foto de cuando la
   recibió: se ve el tablero de entonces y el de ahora, uno al lado del
   otro. */
const angulos = () => [
  ["frente", t("cmp_a_frente")],
  ["atras", t("cmp_a_atras")],
  ["izquierdo", t("cmp_a_izquierdo")],
  ["derecho", t("cmp_a_derecho")],
  ["odometro", t("cmp_a_odometro")],
];

const octavos = () => [t("cmp_tanque_vacio"), "1/8", "1/4", "3/8", "1/2",
                       "5/8", "3/4", "7/8", t("cmp_tanque_lleno")];

/* Corta a propósito: se elige de un vistazo, con una mano, a las seis de
   la mañana. "Otro" existe para que nadie se quede atorado escogiendo.
   El texto de la explicación es lo que de verdad cuenta qué pasó; esto
   sirve para poder contarlos. */
const tiposDano = () => [
  ["rayon", t("cmp_d_rayon")],
  ["golpe", t("cmp_d_golpe")],
  ["cristal", t("cmp_d_cristal")],
  ["llanta", t("cmp_d_llanta")],
  ["mecanico", t("cmp_d_mecanico")],
  ["otro", t("cmp_d_otro")],
];

function nombreDelDano(codigo) {
  const par = tiposDano().find(([c]) => c === codigo);
  return par ? par[1] : codigo;
}

async function pantallaRevision() {
  cargando();
  const servicioId = Number(location.hash.split("/")[2]);
  let guardado;
  try {
    guardado = await traer(`unidades-${servicioId}`,
                           () => api.get(`/campo/servicios/${servicioId}/unidades`));
  } catch (err) { return conBarra(aviso(motivo(err), "grave")); }
  const r = guardado.datos;

  const cuerpo = [
    h("a", { href: "#/hoy", clase: "chico" }, t("cmp_volver_dia")),
    h("h1", {}, t("cmp_revision")),
    /* Sin senal se ve lo ultimo que se supo, con su edad escrita: al
       menos se sabe que unidad se trae y si ya se reviso. Lo que no se
       puede sin linea es GUARDAR la revision --las fotos son medio mega
       y la cola vive en el telefono--, y eso se dice al intentarlo. */
    guardado.de_memoria ? sinLinea(guardado.en) : null,
    h("div", { clase: "chico gris" }, r.folio),
    /* Estaba al final de la pantalla, despues de las unidades: para
       cuando se leia, ya se habia decidido que hacer. */
    h("p", { clase: "gris chico", style: "margin:2px 0 14px" }, t("cmp_revision_pie")),
  ];

  if (!r.unidades.length) {
    cuerpo.push(h("div", { clase: "vacio" },
      t("cmp_sin_unidad")));
    return conBarra(...cuerpo);
  }

  for (const u of r.unidades) cuerpo.push(tarjetaUnidad(servicioId, u));
  conBarra(...cuerpo);
}

function tarjetaUnidad(servicioId, u) {
  const caja = h("div", { clase: "caja" },
    h("div", { clase: "fila separa" },
      h("div", {},
        h("div", { clase: "grande" }, u.placa),
        h("div", { clase: "chico gris" },
          [u.marca_modelo, u.unidad, u.color].filter(Boolean).join(" · "))),
      u.entregada
        ? h("span", { clase: "marca ok" }, t("cmp_completa"))
        : u.recibida
          ? h("span", { clase: "marca alerta" }, t("cmp_en_tus_manos"))
          : h("span", { clase: "marca grave" }, t("cmp_sin_revisar"))));

  if (u.recibida) {
    caja.append(h("div", { clase: "marco" },
      resumen(t("cmp_recibida"), u.recibida)));
  }
  if (u.entregada) {
    caja.append(...[h("div", { clase: "marco" },
      resumen(t("cmp_entregada"), u.entregada),
      (u.recibida && u.recibida.kilometraje != null
       && u.entregada.kilometraje != null)
        ? h("div", { clase: "chico", style: "margin-top:6px" },
            h("b", {}, t("cmp_km_valor").replace("{km}",
              (u.entregada.kilometraje - u.recibida.kilometraje)
                .toLocaleString(local()))),
            " " + t("cmp_recorridos_servicio"))
        : null)].filter(Boolean));
  }

  if (!u.recibida) {
    caja.append(h("div", { clase: "marco" },
      h("button", { onclick: () => formRevision(servicioId, u, "recibe") },
        t("cmp_recibir")),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        t("cmp_recibir_pie"))));
  } else if (!u.entregada) {
    caja.append(h("div", { clase: "marco" },
      h("button", { clase: "claro",
        onclick: (e) => abrirEntrega(e, servicioId, u) },
        t("cmp_entregar")),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        t("cmp_entregar_pie"))));
  }
  return caja;
}

/* Para entregar hay que ver como se recibio --las fotos lado a lado--
   y esas fotos ya no vienen en la lista. Se piden aqui, que es el unico
   momento en que hacen falta.

   Si no se pueden traer, el formato se abre igual: entregar sin la
   comparacion es peor que no poder entregar. */
async function abrirEntrega(e, servicioId, unidad) {
  const boton = e.target;
  boton.disabled = true;
  boton.textContent = t("cmp_un_momento");
  let recibida = unidad.recibida;
  try {
    if (recibida && recibida.cuantas_fotos) {
      recibida = await api.get(`/campo/revisiones/${recibida.id}`);
    }
  } catch { /* sin las fotos de antes, pero con el formato */ }
  formRevision(servicioId, { ...unidad, recibida }, "entrega");
}


function resumen(titulo, r) {
  return h("div", {},
    h("div", { clase: "fila separa" },
      h("span", { clase: "clave gris chico" }, titulo),
      h("span", { clase: "chico gris" }, fechaHora(r.momento))),
    h("div", { clase: "chico" },
      [r.persona,
       r.kilometraje != null
         ? t("cmp_km_valor").replace("{km}",
             r.kilometraje.toLocaleString(local())) : null,
       r.combustible_octavos != null
         ? t("cmp_tanque_valor").replace("{nivel}",
             octavos()[r.combustible_octavos]) : null,
      ].filter(Boolean).join(" · ")),
    r.hubo_dano
      ? h("div", { clase: "aviso alerta", style: "margin:6px 0" },
          h("b", {}, nombreDelDano(r.dano_tipo)),
          r.dano_nota ? ` · ${r.dano_nota}` : "")
      : null,
    r.nota ? h("div", { clase: "chico gris" }, r.nota) : null,
    tiras(r));
}


/* Las fotos ya no vienen con la lista: son medio mega cada una y la
   pantalla traia todas las de todas las unidades del servicio en cada
   consulta. Se piden de una revision a la vez, cuando alguien de
   verdad las quiere ver. */
function tiras(r) {
  const caja = h("div", { clase: "tiras" });
  if (!r.cuantas_fotos) return caja;

  const ver = h("button", { clase: "claro chico", onclick: async () => {
    ver.disabled = true;
    ver.textContent = t("cmp_un_momento");
    try {
      const completa = await api.get(`/campo/revisiones/${r.id}`);
      caja.replaceChildren(
        ...completa.fotos.map(f => h("img", { clase: "tira", src: f.imagen,
                                              alt: f.angulo })));
    } catch (err) {
      ver.disabled = false;
      ver.textContent = t("cmp_ver_fotos").replace("{n}", r.cuantas_fotos);
      alert(motivo(err));
    }
  } }, t("cmp_ver_fotos").replace("{n}", r.cuantas_fotos));

  caja.append(ver);
  return caja;
}

function fechaHora(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(local(), { day: "numeric", month: "short" })
         + " · " + hora(iso);
}


/* ------------------------------------------------------ el formato */

function formRevision(servicioId, unidad, tipo) {
  const entrando = tipo === "recibe";
  const antes = {};
  for (const f of (unidad.recibida ? unidad.recibida.fotos : [])) {
    antes[f.angulo] = f.imagen;
  }

  /* El borrador de esta revision, en el telefono.
  
     Cinco fotos, el odometro, el tanque, la declaracion de daño y una
     firma son diez minutos con una mano. Que se pierdan enteros porque
     la app se repinto, porque se cerro sin querer o porque el telefono
     se quedo sin bateria es el camino mas corto a que nadie quiera
     usarla --y a que las revisiones se hagan "despues", que en la
     practica es nunca.
  
     Se guarda en cada cambio, no al final. Una llave por unidad y por
     tipo: recibir y entregar son dos revisiones distintas de la misma
     camioneta y no se pisan.
  
     Vive solo en este telefono y se borra al guardar la revision de
     verdad. No sustituye al servidor: es la red debajo del trapecio. */
  const llave = `revision_${unidad.vehiculo_id}_${tipo}`;
  const previo = (recordar(llave) || {}).datos || {};

  const apuntar = () => guardarMemoria(llave, {
    fotos: Object.fromEntries(
      ranuras.filter(r => r.imagen()).map(r => [r.angulo, r.imagen()])),
    danos: danos.filter(d => d.imagen()).map(d => d.imagen()),
    km: km.value, tanque: tanque.value, nota: nota.value, hubo,
    tipo_dano: tipoDano.value,
  });

  const ranuras = angulos().map(([clave, texto]) =>
    ranura(clave, texto, entrando ? null : antes[clave],
           () => apuntar(), (previo.fotos || {})[clave]));

  const danos = [];
  const cajaDanos = h("div", { clase: "rejilla" });
  const nuevoDano = (guardada = null) => {
    const extra = ranura("dano",
      t("cmp_detalle_n").replace("{n}", danos.length + 1), null,
      () => apuntar(), guardada);
    danos.push(extra);
    cajaDanos.append(extra.nodo);
    return extra;
  };
  for (const img of (previo.danos || [])) nuevoDano(img);

  const masDano = h("button", { clase: "claro chico",
    onclick: () => nuevoDano() }, t("cmp_mas_foto_golpe"));

  const km = h("input", { type: "number", inputmode: "numeric", min: "0",
    placeholder: t("cmp_ph_kilometraje"), oninput: () => apuntar() });
  if (previo.km) km.value = previo.km;
  const tanque = document.createElement("select");
  octavos().forEach((nivel, i) =>
    tanque.append(h("option", { value: i }, nivel)));
  tanque.value = previo.tanque !== undefined ? previo.tanque : 8;
  tanque.addEventListener("change", () => apuntar());

  /* Una sola caja de texto, no dos. La revisión ya traía una nota libre
     y la declaración pide una explicación: con las dos en pantalla, el
     golpe se escribe en la que toque primero y del otro lado hay que
     leer en dos lugares. Aquí es la misma caja, que cambia de nombre
     según lo que se contestó. */
  const nota = h("input", { type: "text", oninput: () => apuntar() });
  if (previo.nota) nota.value = previo.nota;
  const etiquetaNota = h("label", {});

  /* La declaración de daño. Dos botones y ninguno marcado de antemano:
     no se puede firmar sin contestar.

     Contestar "no" es un toque. Esa es la única forma de que el dato
     sirva: si declarar costara más que no declarar, la casilla diría
     "no" siempre y tendríamos una falsa sensación de estar
     documentando. */
  let hubo = null;
  const tipoDano = document.createElement("select");
  for (const [valor, texto] of tiposDano()) {
    tipoDano.append(h("option", { value: valor }, texto));
  }
  const zonaDano = h("div");
  /* Los dos botones tienen que HACER algo.
  
     Se creaban, se pintaban y nadie los conectaba: `hubo` se quedaba en
     nulo para siempre y el guardado --que exige haber contestado-- no
     dejaba pasar nunca. O sea que ninguna revision de unidad se podia
     completar desde la app. Lo encontro Salvador el 21 de septiembre
     recibiendo una camioneta: "pico y no hace nada".
  
     La bateria no lo veia porque las pruebas mandan la revision por el
     API y no por la pantalla. Es el hueco de siempre: lo que solo vive
     en el navegador se prueba usandolo. */
  const botonNo = h("button", { clase: "claro", type: "button",
    onclick: () => contestar(false) }, t("cmp_no"));
  const botonSi = h("button", { clase: "claro", type: "button",
    onclick: () => contestar(true) },
    entrando ? t("cmp_si_tiene_dano") : t("cmp_si_se_dano"));

  function contestar(valor) {
    hubo = valor;
    botonNo.className = valor === false ? "" : "claro";
    botonSi.className = valor === true ? "" : "claro";
    etiquetaNota.textContent = valor
      ? (entrando ? t("cmp_describe_dano") : t("cmp_que_paso"))
      : t("cmp_observaciones");
    nota.placeholder = valor
      ? (entrando ? t("cmp_ph_donde_dano") : t("cmp_ph_que_paso"))
      : t("cmp_ph_observaciones");
    zonaDano.replaceChildren(...(valor ? [
      h("div", { clase: "campo" }, h("label", {}, t("cmp_de_que_fue")), tipoDano),
      cajaDanos, masDano,
      h("div", { clase: "chico gris", style: "margin-top:8px" },
        t("cmp_golpe_pie")),
    ] : []));
    apuntar();
  }

  /* La declaracion tambien se recupera. Es la unica respuesta del
     formulario que no se puede volver a deducir de lo capturado, y sin
     ella el boton de guardar no deja pasar. */
  tipoDano.addEventListener("change", () => apuntar());
  contestar(previo.hubo === undefined ? null : previo.hubo);
  if (previo.tipo_dano) tipoDano.value = previo.tipo_dano;

  const firma = lienzoFirma();

  /* Se dice que se recupero, arriba del todo. Encontrarse la pantalla ya
     llena sin que nadie lo explique hace dudar de si eso es de hoy o de
     la semana pasada --y en una revision de unidad esa duda es grave. */
  const avisoBorrador = (previo.fotos && Object.keys(previo.fotos).length)
    ? aviso(t("cmp_borrador_recuperado"), "ok")
    : null;

  const guardar = h("button", { style: "margin-top:8px" },
    entrando ? t("cmp_guardar_recibir") : t("cmp_guardar_entregar"));
  guardar.addEventListener("click", () => mandar(guardar));

  const cuerpo = [
    avisoBorrador,
    /* Un enlace al mismo hash no dispara nada: el formulario se abrio
       reemplazando el DOM, sin tocar la direccion. Con las cuatro fotos
       ya tomadas, tocar "Volver" y que no pase nada se siente como una
       pantalla congelada. */
    h("a", { href: "#", clase: "chico",
             onclick: (e) => { e.preventDefault(); pantallaRevision(); } },
      t("cmp_volver")),
    h("h1", {}, entrando ? t("cmp_recibir_unidad") : t("cmp_entregar")),
    h("div", { clase: "chico gris" },
      `${unidad.placa}${unidad.color ? " · " + unidad.color : ""}`),
  ];

  const comparando = !entrando && !!unidad.recibida;
  if (comparando) {
    cuerpo.push(h("div", { clase: "aviso alerta", style: "margin-top:12px" },
      t("cmp_lado_a_lado")));
  }

  cuerpo.push(
    h("div", { clase: "marco" },
      h("h2", {}, t("cmp_cinco_fotos")),
      h("div", { clase: "chico gris", style: "margin-bottom:10px" },
        t("cmp_cinco_pie")),
      /* Al entregar, cada celda trae DOS fotos --como estaba y como
         esta-- asi que la rejilla baja a una sola columna: con dos
         celdas por renglon cabrian cuatro fotos de ochenta pixeles y un
         rayon de ochenta pixeles no se ve. Al recibir, que es una sola
         foto por celda, se quedan dos por renglon. */
      h("div", { clase: comparando ? "rejilla comparando" : "rejilla" },
        ...ranuras.map(r => r.nodo))),

    h("div", { clase: "marco" },
      h("h2", {}, entrando ? t("cmp_pregunta_recibe_dano")
                           : t("cmp_pregunta_entrega_dano")),
      h("div", { clase: "fila", style: "gap:10px;margin:10px 0" },
        botonNo, botonSi),
      /* Se dice con todas sus letras. Un candado que no se explica se
         siente como una trampa, y quien recibe una camioneta golpeada
         con prisa necesita saber que declararlo juega a su favor. */
      h("div", { clase: "chico gris" }, entrando
        ? t("cmp_dano_protege") : t("cmp_dano_revisa")),
      zonaDano),

    h("div", { clase: "marco" },
      h("div", { clase: "campo" }, h("label", {}, t("cmp_kilometraje")), km),
      h("div", { clase: "campo" }, h("label", {}, t("cmp_tanque")), tanque),
      h("div", { clase: "campo" }, etiquetaNota, nota)),

    h("div", { clase: "marco" },
      h("h2", {}, entrando ? t("cmp_firma_recibe") : t("cmp_firma_entrega")),
      firma.nodo,
      h("div", { clase: "fila", style: "margin-top:8px" },
        h("button", { clase: "claro chico", onclick: firma.borrar },
          t("cmp_borrar_firma")))),

    h("div", { clase: "marco" }, guardar),
  );

  raiz().replaceChildren(h("div", {}, ...cuerpo.filter(Boolean)));
  window.scrollTo(0, 0);

  async function mandar(boton) {
    const fotos = [];
    const faltan = [];
    for (const r of ranuras) {
      if (r.imagen()) fotos.push({ angulo: r.angulo, imagen: r.imagen() });
      else faltan.push(r.texto);
    }
    if (faltan.length) {
      return alert(t("cmp_faltan_fotos")
        .replace("{fotos}", faltan.join(", ")));
    }
    for (const d of danos) {
      if (d.imagen()) fotos.push({ angulo: "dano", imagen: d.imagen() });
    }
    if (!km.value) return alert(t("cmp_falta_km"));

    /* Lo mismo que revisa el servidor, revisado aquí primero: con las
       fotos ya tomadas y media barra de señal, que el viaje se pierda
       por una casilla es la peor forma de enterarse. */
    if (hubo === null) {
      return alert(entrando ? t("cmp_falta_declara_recibe")
                            : t("cmp_falta_declara_entrega"));
    }
    if (hubo) {
      if (!nota.value || nota.value.trim().length < 10) {
        return alert(entrando ? t("cmp_falta_describe_recibe")
                              : t("cmp_falta_describe_entrega"));
      }
      if (!danos.some(d => d.imagen())) {
        return alert(t("cmp_falta_foto_golpe"));
      }
    }
    if (!firma.hayTrazo()) return alert(t("cmp_falta_firma"));

    boton.disabled = true;
    boton.textContent = t("cmp_tomando_ubicacion");
    const donde = await ubicacion();
    boton.textContent = t("cmp_enviando_fotos").replace("{n}", fotos.length);

    try {
      const r = await api.post("/campo/revisiones", {
        servicio_id: servicioId,
        vehiculo_id: unidad.vehiculo_id,
        tipo,
        kilometraje: Number(km.value),
        combustible_octavos: Number(tanque.value),
        /* La caja es una sola; a donde va depende de lo que contestó.
           En la base son dos columnas porque el consultor necesita ver
           el daño destacado y aparte de una observación cualquiera. */
        nota: hubo ? null : (nota.value || null),
        hubo_dano: hubo,
        dano_tipo: hubo ? tipoDano.value : null,
        dano_nota: hubo ? nota.value : null,
        firma: firma.imagen(),
        lat: donde ? donde.lat : null,
        lon: donde ? donde.lon : null,
        fotos,
      });
      /* El borrador ya cumplio: la revision esta en el servidor y
         guardarlo mas tiempo solo arriesga que la proxima vez se
         recupere una captura vieja. */
      olvidar(llave);
      olvidar("mi-dia");
      const km_recorridos = r.kilometros_recorridos;
      alert(entrando
        ? t("cmp_unidad_recibida_ok")
        : t("cmp_unidad_entregada_ok")
          + (km_recorridos != null
             ? t("cmp_km_en_servicio").replace("{km}",
                 km_recorridos.toLocaleString(local()))
             : ""));
      location.hash = `#/revision/${servicioId}`;
      pintar();
    } catch (err) {
      boton.disabled = false;
      boton.textContent = entrando ? t("cmp_guardar_recibir")
                                   : t("cmp_guardar_entregar");
      /* Las fotos no se encolan: son medio mega y la cola vive en el
         telefono. Mas honesto es decir que no salio y que lo intente
         donde haya senal, con las fotos todavia en pantalla. */
      alert(motivo(err) + t("cmp_fotos_siguen"));
    }
  }
}

/* Una ranura de foto: el cuadro que se toca, la camara, y —cuando se
   entrega— la foto de como estaba al recibirla, al lado. */
function ranura(angulo, texto, referencia, alCambiar = null,
                guardada = null) {
  let imagen = guardada || null;
  const archivo = h("input", { type: "file", accept: "image/*",
                               capture: "environment", hidden: true });
  const lienzo = h("div", { clase: "ranura",
                            onclick: () => archivo.click() },
    h("span", { clase: "chico gris" }, t("cmp_tocar_foto")));

  /* Quitar UNA foto, sin tocar las otras.
  
     Antes la unica forma de cambiar una era volver a tocarla y disparar
     la camara otra vez. Eso sirve para repetir, no para descartar: si
     salio movida y todavia no se sabe si se va a repetir, no habia forma
     de dejar la ranura vacia. */
  const quitar = h("button", { clase: "claro chico", hidden: true,
    type: "button",
    onclick: (e) => {
      e.stopPropagation();
      imagen = null;
      archivo.value = "";
      ver();
      if (alCambiar) alCambiar();
    } }, t("cmp_quitar_foto"));

  function ver() {
    if (imagen) {
      lienzo.replaceChildren(h("img", { src: imagen, alt: texto }));
      lienzo.classList.add("lista");
    } else {
      lienzo.replaceChildren(
        h("span", { clase: "chico gris" }, t("cmp_tocar_foto")));
      lienzo.classList.remove("lista");
    }
    quitar.hidden = !imagen;
  }

  archivo.addEventListener("change", async () => {
    const f = archivo.files && archivo.files[0];
    if (!f) return;
    lienzo.replaceChildren(h("span", { clase: "chico gris" }, t("cmp_preparando")));
    try {
      imagen = await reducir(f);
      ver();
      /* Se guarda EN EL MOMENTO, no al enviar. Cinco fotos, el odometro
         y una firma son diez minutos de trabajo con una mano; que se
         pierdan enteros porque la app se repinto, se cerro sin querer o
         el telefono se quedo sin bateria es el camino mas corto a que
         nadie quiera usarla. */
      if (alCambiar) alCambiar();
    } catch (err) {
      imagen = null;
      ver();
      lienzo.replaceChildren(h("span", { clase: "chico rojo" }, err.message));
    }
  });

  const nodo = h("div", { clase: "celda" },
    h("div", { clase: "chico", style: "margin-bottom:4px" }, texto),
    referencia
      ? h("div", { clase: "par" },
          h("div", {}, h("div", { clase: "chico gris" }, t("cmp_al_recibirla")),
            h("img", { clase: "ranura vieja", src: referencia, alt: texto })),
          h("div", {}, h("div", { clase: "chico gris" }, t("cmp_ahora")), lienzo))
      : lienzo,
    quitar, archivo);

  if (imagen) ver();
  return { angulo, texto, nodo, imagen: () => imagen };
}

/* La firma con el dedo. Un lienzo chico: una firma no necesita mas de
   seiscientos pixeles y asi pesa diez kilobytes en vez de trescientos. */
function lienzoFirma() {
  const canvas = document.createElement("canvas");
  canvas.width = 600;
  canvas.height = 200;
  canvas.className = "firma";
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = "#1b2a3a";

  let trazando = false, hubo = false;

  const punto = (e) => {
    const caja = canvas.getBoundingClientRect();
    return [(e.clientX - caja.left) * (canvas.width / caja.width),
            (e.clientY - caja.top) * (canvas.height / caja.height)];
  };

  canvas.addEventListener("pointerdown", (e) => {
    trazando = true; hubo = true;
    canvas.setPointerCapture(e.pointerId);
    const [x, y] = punto(e);
    ctx.beginPath(); ctx.moveTo(x, y);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!trazando) return;
    e.preventDefault();
    const [x, y] = punto(e);
    ctx.lineTo(x, y); ctx.stroke();
  });
  const soltar = () => { trazando = false; };
  canvas.addEventListener("pointerup", soltar);
  canvas.addEventListener("pointercancel", soltar);
  canvas.addEventListener("pointerleave", soltar);

  return {
    nodo: canvas,
    hayTrazo: () => hubo,
    imagen: () => (hubo ? canvas.toDataURL("image/png") : null),
    borrar: () => {
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = "#1b2a3a";
      hubo = false;
    },
  };
}

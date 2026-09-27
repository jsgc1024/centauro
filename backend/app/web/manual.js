/* El manual del sistema (seccion 90).

   Vive dentro de la consola, y no en un PDF suelto, porque un PDF se
   queda viejo el dia que cambia una pantalla y nadie sabe si lo que dice
   sigue siendo cierto (propuesta del 27 sep, aprobada por Salvador). Lo
   escrito viaja en el mismo codigo --backend/manual--, y lo que se puede
   sacar del sistema --el reloj, quien puede que, los mensajes, las
   novedades-- sale del sistema cada vez que se abre. Las pruebas no
   dejan subir un cambio que lo deje atras.

   Lo lee quien administra el sistema: sistema y calidad, administracion
   y direccion general. Esta escrito en espanol y en portugues; la
   consola en ingles lo lee en espanol, con su aviso.

   El texto llega del servidor en bloques --titulo, parrafo, lista,
   nota-- con sus negritas y sus ligas en pedazos, y aqui se pinta con
   h(): nada de HTML armado a mano. Tampoco lleva "?": el manual es la
   ayuda, y un "?" sobre la ayuda seria explicar la explicacion. */
import { api } from "./api.js";
import { aviso, etiqueta, fecha, h, hora, lista, mensaje,
         sinTildes } from "./util.js";
import { idioma, t } from "./idioma.js";
import { nombreDelRol, porFamilia } from "./categorias.js";

/* El manual se pide una vez y se guarda un rato: lo escrito cambia con
   cada actualizacion, no mientras alguien lo lee. Lo que si cambia --el
   estado del sistema y los casos-- se pide aparte, cada vez. */
let guardado = null;
let guardadoIdioma = null;
let guardadoEn = 0;
const VIGENCIA_MS = 5 * 60 * 1000;

async function traer(fresco = false) {
  const actual = idioma();
  if (!fresco && guardado && guardadoIdioma === actual
      && Date.now() - guardadoEn < VIGENCIA_MS) {
    return guardado;
  }
  guardado = await api.get(`/manual?idioma=${actual}`);
  guardadoIdioma = actual;
  guardadoEn = Date.now();
  return guardado;
}

/* Lo que se busco en la portada viaja a la pagina que lo ensena entero:
   quien busco "llave" y pica en los mensajes no lo vuelve a escribir. */
let buscado = "";

/* ------------------------------------------------------------ ayudas */

function llenar(clave, datos) {
  let salida = t(clave);
  for (const [k, v] of Object.entries(datos)) {
    salida = salida.split(`{${k}}`).join(String(v));
  }
  return salida;
}

/* Buscar como escribe alguien con prisa: sin acentos, sin mayusculas, y
   cada palabra por su lado --"correo cliente" encuentra "el correo no le
   llego al cliente"--. */
function palabras(q) {
  return sinTildes(q).split(/\s+/).filter(Boolean);
}

function dice(texto, q) {
  const buscadas = palabras(q);
  if (!buscadas.length) return true;
  const donde = sinTildes(texto);
  return buscadas.every(p => donde.includes(p));
}

function textoDe(partes) {
  return (partes || []).map(p => p.t).join("");
}

function textoDelCapitulo(c) {
  const bloques = c.bloques.map(b => b.texto || textoDe(b.partes)
    || (b.items || []).map(textoDe).join(" "));
  return [c.titulo, c.resumen, c.area, c.buscar, ...bloques].join(" ");
}

function cajaDeBuscar(ayuda, valor = "") {
  /* data-crudo: lo que se escribe aqui es para buscar, no un nombre que
     haya que dejar en mayusculas y minusculas (vigilarCapturas). */
  return h("input", { type: "search", clase: "man-buscar", placeholder: ayuda,
                      value: valor || null, "data-crudo": "", autocomplete: "off" });
}

function volver(ruta = "#/manual", clave = "man_volver") {
  return h("a", { href: ruta, clase: "man-volver chico" }, t(clave));
}

function alDia(d) {
  return etiqueta(llenar("man_al_dia", { f: d.version.fecha }), "ok");
}

function enOtroIdioma(d) {
  return d.en_otro_idioma ? aviso(t("man_en_espanol")) : null;
}

function haceCuanto(iso) {
  if (!iso) return "—";
  const minutos = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutos < 1) return t("man_hace_nada");
  if (minutos < 120) return llenar("man_hace_min", { n: minutos });
  if (minutos < 48 * 60) return llenar("man_hace_h", { n: Math.floor(minutos / 60) });
  return llenar("man_hace_dias", { n: Math.floor(minutos / 1440) });
}

/* --------------------------------------------------------- los bloques */

function trozos(partes) {
  return (partes || []).map(p => (p.a ? h("a", { href: p.a }, p.t)
                                  : p.b ? h("b", {}, p.t) : p.t));
}

/* El ancla va con prefijo: `panorama` a secas chocaria con cualquier
   otro id de la consola. */
function pintarBloque(b) {
  const id = b.ancla ? `man-${b.ancla}` : null;
  if (b.tipo === "h2") return h("h2", { id, clase: "man-h2" }, b.texto);
  if (b.tipo === "h3") return h("h3", { id, clase: "man-h3" }, b.texto);
  if (b.tipo === "lista") {
    return h(b.numerada ? "ol" : "ul", { clase: "man-lista" },
      ...b.items.map(x => h("li", {}, ...trozos(x))));
  }
  if (b.tipo === "nota") return h("div", { clase: "man-nota" }, ...trozos(b.partes));
  return h("p", {}, ...trozos(b.partes));
}

function texto(c) {
  return h("div", { clase: "man-texto" }, ...c.bloques.map(pintarBloque));
}

/* ------------------------------------------------------------ la puerta */

export async function pantallaManual(main, resto = "") {
  const [pagina, ...demas] = (resto || "").split("/");
  let d;
  try {
    d = await traer(pagina === "imprimir");
  } catch (err) {
    main.append(aviso(err.message, "grave"));
    return;
  }
  if (!pagina) return portada(main, d);
  if (pagina === "atorado") return atorado(main, d);
  if (pagina === "leer") return leer(main, d, demas[0], demas[1]);
  if (pagina === "reloj") return reloj(main, d);
  if (pagina === "mensajes") return mensajes(main, d);
  if (pagina === "permisos") return permisos(main, d);
  if (pagina === "novedades") return novedades(main, d);
  if (pagina === "casos") return casos(main, d);
  if (pagina === "imprimir") return imprimir(main, d);
  main.append(volver(), aviso(t("man_no_existe"), "alerta"));
}

/* ------------------------------------------------------------ portada */

function portada(main, d) {
  const caja = cajaDeBuscar(t("man_buscar_ayuda"), buscado);
  const resultados = h("div", { clase: "tarjeta man-resultados", hidden: "hidden" });
  const partes = h("div", { clase: "rejilla tres man-partes" }, ...tresPartes(d));
  const nuevo = loNuevo(d);

  const buscar = () => {
    const q = caja.value.trim();
    buscado = q;
    const hay = palabras(q).length > 0;
    resultados.hidden = !hay;
    partes.hidden = hay;
    nuevo.hidden = hay;
    if (hay) resultados.replaceChildren(...lasRespuestas(d, q));
  };
  caja.addEventListener("input", buscar);

  const pdf = h("button", { clase: "claro man-pdf", type: "button",
    onclick: () => { location.hash = "#/manual/imprimir"; } }, t("man_pdf"));

  main.append(...[
    h("h1", {}, t("man_titulo")),
    h("p", { clase: "sub" }, t("man_sub")),
    enOtroIdioma(d),
    h("div", { clase: "acciones man-barra" }, caja, alDia(d), pdf),
    resultados, partes, nuevo,
  ].filter(Boolean));
  if (buscado) buscar();
}

function tresPartes(d) {
  const entender = d.capitulos.filter(c => c.parte === "entender");
  const sintomas = d.capitulos.filter(c => c.parte === "resolver");
  const roles = new Set(d.permisos.actividades.flatMap(a => a.roles));
  const tareas = d.reloj.filter(x => !x.fuera).length;

  const tarjeta = (numero, titulo, sub, renglones) => h("div", { clase: "tarjeta man-parte" },
    h("h4", {}, numero),
    h("h3", {}, titulo),
    h("p", { clase: "chico gris" }, sub),
    h("ul", { clase: "man-indice" }, ...renglones.map(([dicho, ruta]) =>
      h("li", {}, h("a", { href: ruta }, dicho)))));

  return [
    tarjeta(t("man_p1_num"), t("man_p1_titulo"), t("man_p1_sub"),
            entender.map(c => [c.titulo, `#/manual/leer/${c.id}`])),
    tarjeta(t("man_p2_num"), t("man_p2_titulo"), t("man_p2_sub"), [
      [t("man_p2_estado"), "#/manual/atorado"],
      [llenar("man_p2_sintomas", { n: sintomas.length }), "#/manual/atorado"],
      [llenar("man_p2_casos", { n: d.casos.length }), "#/manual/casos"]]),
    tarjeta(t("man_p3_num"), t("man_p3_titulo"), t("man_p3_sub"), [
      [llenar("man_p3_reloj", { n: tareas }), "#/manual/reloj"],
      [llenar("man_p3_permisos", { a: d.permisos.actividades.length, r: roles.size }),
       "#/manual/permisos"],
      [llenar("man_p3_mensajes", { n: d.mensajes.length }), "#/manual/mensajes"],
      [t("man_p3_novedades"), "#/manual/novedades"]]),
  ];
}

function novedad(n) {
  return h("p", { clase: "man-novedad" },
    h("b", {}, `${n.fecha} · ${n.titulo}.`), " ", ...trozos(n.partes));
}

function loNuevo(d) {
  return h("div", { clase: "tarjeta" },
    h("h3", {}, t("man_lo_nuevo")),
    ...d.novedades.slice(0, 3).map(novedad),
    h("button", { clase: "claro", type: "button",
      onclick: () => { location.hash = "#/manual/novedades"; } }, t("man_ver_novedades")));
}

/* Lo que encontro la caja de la portada: los capitulos que lo dicen y,
   de lo que sale solo del sistema, cuantos renglones lo dicen y donde. */
function lasRespuestas(d, q) {
  const capitulos = d.capitulos.filter(c => dice(textoDelCapitulo(c), q));
  const enMensajes = d.mensajes.filter(x => dice(`${x.mensaje} ${x.que_hacer}`, q)).length;
  const enPermisos = d.permisos.actividades.filter(
    a => dice(`${a.actividad} ${a.descripcion} ${a.puestos.join(" ")}`, q)).length;
  const enReloj = d.reloj.filter(x => dice(`${x.cuando} ${x.que} ${x.revisa}`, q)).length;

  const renglones = capitulos.map(c => h("div", { clase: "man-resultado" },
    h("a", { href: `#/manual/leer/${c.id}` }, c.titulo),
    h("div", { clase: "chico gris" },
      [c.parte === "entender" ? t("man_parte_entender") : t("man_parte_resolver"),
       c.area].filter(Boolean).join(" · "))));

  const aparte = [
    [enMensajes, "man_res_mensajes", "#/manual/mensajes"],
    [enPermisos, "man_res_permisos", "#/manual/permisos"],
    [enReloj, "man_res_reloj", "#/manual/reloj"],
  ].filter(([n]) => n > 0).map(([n, clave, ruta]) => h("div", { clase: "man-resultado" },
    h("a", { href: ruta }, llenar(clave, { n, q }))));

  if (!renglones.length && !aparte.length) {
    return [h("p", { clase: "gris" }, llenar("man_sin_resultados", { q }))];
  }
  return [h("h4", {}, t("man_resultados")), ...renglones, ...aparte];
}

/* ------------------------------------------------ cuando algo se atora */

function tarjetaEstado(x) {
  return h("div", { clase: "tarjeta lisa man-tile man-tile-" + x.tono },
    h("h3", {}, x.titulo),
    etiqueta(x.etiqueta, x.tono === "ok" ? "ok" : x.tono === "grave" ? "grave" : "alerta"),
    h("p", { clase: "chico gris" }, x.texto),
    x.ir ? h("a", { href: x.ir, clase: "chico" }, t("man_que_hacer_ir")) : null);
}

async function atorado(main, d) {
  const tablero = h("div", { clase: "rejilla tres man-estado" });
  const cuando = h("span", { clase: "chico gris" });
  const revisar = async () => {
    tablero.replaceChildren(h("p", { clase: "gris" }, t("man_revisando")));
    try {
      const e = await api.get(`/manual/estado?idioma=${idioma()}`);
      tablero.replaceChildren(...e.tarjetas.map(tarjetaEstado));
      cuando.textContent = llenar("man_revisado", { h: hora(e.ahora) });
    } catch (err) {
      tablero.replaceChildren(aviso(err.message, "grave"));
    }
  };

  main.append(...[
    volver(),
    h("h1", {}, t("man_atorado_titulo")),
    h("p", { clase: "sub" }, t("man_atorado_sub")),
    enOtroIdioma(d),
    h("div", { clase: "man-estado-cabeza" },
      h("h4", {}, t("man_estado_ahora")), cuando,
      h("button", { clase: "claro chico", type: "button", onclick: revisar },
        t("man_revisar_otra_vez"))),
    tablero,
    losSintomas(d),
  ].filter(Boolean));
  await revisar();
}

function sintoma(c, abierto) {
  return h("details", { clase: "man-sintoma", open: abierto ? "open" : null },
    h("summary", {}, c.titulo),
    texto(c),
    h("a", { href: `#/manual/leer/${c.id}`, clase: "chico" }, t("man_abrir_sola")));
}

function losSintomas(d) {
  const sintomas = d.capitulos.filter(c => c.parte === "resolver");
  const caja = cajaDeBuscar(t("man_buscar_sintoma"));
  const zona = h("div");

  const pintar = () => {
    const q = caja.value.trim();
    const vistos = sintomas.filter(c => dice(textoDelCapitulo(c), q));
    /* Con pocos que coincidan, ya abiertos: quien busco "correo" quiere
       leer la respuesta, no picar otra vez. */
    const abiertos = palabras(q).length > 0 && vistos.length <= 2;
    const nodos = [];
    let area = null;
    for (const c of vistos) {
      if (c.area !== area) {
        area = c.area;
        nodos.push(h("h4", { clase: "man-area" }, area));
      }
      nodos.push(sintoma(c, abiertos));
    }
    zona.replaceChildren(...(nodos.length ? nodos
      : [h("p", { clase: "gris" }, llenar("man_sin_sintomas", { q }))]));
  };
  caja.addEventListener("input", pintar);
  pintar();

  return h("div", { clase: "tarjeta man-sintomas" }, caja, zona,
    h("p", { clase: "chico gris man-no-esta" }, t("man_no_esta"), " ",
      h("a", { href: "#/manual/casos" }, t("man_ir_casos"))));
}

/* ------------------------------------------------------------ un capitulo */

function leer(main, d, id, ancla) {
  const c = d.capitulos.find(x => x.id === id);
  if (!c) {
    main.append(volver(), aviso(t("man_no_existe"), "alerta"));
    return;
  }
  const hermanos = d.capitulos.filter(x => x.parte === c.parte);
  const i = hermanos.indexOf(c);
  const antes = hermanos[i - 1];
  const despues = hermanos[i + 1];
  const resolver = c.parte === "resolver";

  main.append(...[
    resolver ? volver("#/manual/atorado", "man_volver_atorado") : volver(),
    h("h4", { clase: "man-donde" },
      [resolver ? t("man_parte_resolver") : t("man_parte_entender"), c.area]
        .filter(Boolean).join(" · ")),
    h("h1", {}, c.titulo),
    c.resumen ? h("p", { clase: "sub" }, c.resumen) : null,
    enOtroIdioma(d),
    h("div", { clase: "tarjeta" }, texto(c)),
    h("div", { clase: "man-pasos chico" },
      antes ? h("a", { href: `#/manual/leer/${antes.id}` },
                llenar("man_anterior", { t: antes.titulo })) : h("span"),
      despues ? h("a", { href: `#/manual/leer/${despues.id}` },
                  llenar("man_siguiente", { t: despues.titulo })) : h("span")),
  ].filter(Boolean));

  if (ancla) {
    const destino = document.getElementById(`man-${ancla}`);
    if (destino) destino.scrollIntoView({ block: "start" });
  }
}

/* ------------------------------------------------ lo que hace el reloj */

/* "GPS: lee Pegasus..." con la pieza en negritas, como se lee de un
   vistazo en la tabla. */
function queHace(que) {
  const i = (que || "").indexOf(": ");
  if (i < 0 || i > 40) return [que];
  return [h("b", {}, que.slice(0, i + 1)), que.slice(i + 1)];
}

function ultimaVuelta(x) {
  if (x.fuera) return h("span", { clase: "chico gris" }, t("man_fuera_reloj"));
  const v = x.ultima;
  if (!v || !v.termino_en) return etiqueta(t("man_sin_vueltas"));
  if (v.estado === "error") {
    return h("div", {},
      etiqueta(llenar("man_con_error", { hace: haceCuanto(v.error_en || v.termino_en) }),
               "grave"),
      v.error ? h("div", { clase: "chico gris man-error" }, v.error) : null);
  }
  if (v.nota) {
    return h("div", {}, etiqueta(v.nota, "alerta"),
      h("div", { clase: "chico gris" }, haceCuanto(v.termino_en)));
  }
  return etiqueta(haceCuanto(v.termino_en), "ok");
}

function filasDelReloj(tareas) {
  const filas = [];
  let grupo = null;
  for (const x of tareas) {
    if (x.grupo_titulo !== grupo) {
      grupo = x.grupo_titulo;
      filas.push(h("tr", { clase: "man-grupo" }, h("td", { colspan: "4" }, grupo)));
    }
    filas.push(h("tr", {},
      h("td", { clase: "man-cuando" }, h("b", {}, x.cuando)),
      h("td", {}, ...queHace(x.que)),
      h("td", { clase: "chico gris" }, x.revisa),
      h("td", {}, ultimaVuelta(x))));
  }
  return filas;
}

function tablaDelReloj(cuerpo) {
  return h("table", { clase: "lista man-reloj" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("man_col_cuando")), h("th", {}, t("man_col_que")),
      h("th", {}, t("man_col_revisa")), h("th", {}, t("man_col_ultima")))),
    cuerpo);
}

function reloj(main, d) {
  const caja = cajaDeBuscar(t("man_buscar_reloj"), buscado);
  const cuerpo = h("tbody");
  const pintar = () => {
    const q = caja.value.trim();
    const vistas = d.reloj.filter(x => dice(`${x.cuando} ${x.que} ${x.revisa}`, q));
    cuerpo.replaceChildren(...filasDelReloj(vistas));
  };
  caja.addEventListener("input", pintar);
  pintar();

  main.append(...[
    volver(),
    h("h1", {}, t("man_reloj_titulo")),
    h("p", { clase: "sub" }, t("man_reloj_sub")),
    enOtroIdioma(d),
    h("div", { clase: "acciones man-barra" }, caja,
      h("span", { clase: "chico gris" }, t("man_reloj_horas"))),
    tablaDelReloj(cuerpo),
  ].filter(Boolean));
}

/* ----------------------------------------- cuando el sistema dice que no */

function renglonMensaje(x) {
  return h("div", { clase: "man-mensaje" },
    h("b", {}, x.mensaje),
    h("div", { clase: "verde" }, h("b", {}, t("man_que_hacer")), " ", x.que_hacer),
    h("div", { clase: "chico gris" }, x.area_titulo));
}

function mensajes(main, d) {
  let area = null;
  const caja = cajaDeBuscar(t("man_buscar_mensaje"), buscado);
  const chips = h("div", { clase: "man-chips" });
  const zona = h("div");

  const cuantos = new Map();
  for (const x of d.mensajes) cuantos.set(x.area, (cuantos.get(x.area) || 0) + 1);
  const areas = d.areas.filter(a => cuantos.has(a.clave))
    .sort((a, b) => cuantos.get(b.clave) - cuantos.get(a.clave));

  const chip = (dicho, activo, alPicar) => h("button", {
    type: "button", clase: activo ? "pestana activa" : "pestana", onclick: alPicar }, dicho);

  const pintar = () => {
    chips.replaceChildren(
      chip(llenar("man_todas", { n: d.mensajes.length }), area === null,
           () => { area = null; pintar(); }),
      ...areas.map(a => chip(`${a.titulo} · ${cuantos.get(a.clave)}`, area === a.clave,
                             () => { area = a.clave; pintar(); })));
    const q = caja.value.trim();
    const vistos = d.mensajes.filter(x => (area === null || x.area === area)
                                          && dice(`${x.mensaje} ${x.que_hacer}`, q));
    zona.replaceChildren(...(vistos.length ? vistos.map(renglonMensaje)
      : [h("p", { clase: "gris" }, llenar("man_sin_mensajes", { q }))]));
  };
  caja.addEventListener("input", pintar);
  pintar();

  main.append(...[
    volver(),
    h("h1", {}, t("man_mensajes_titulo")),
    h("p", { clase: "sub" }, t("man_mensajes_sub")),
    idioma() === "es" ? null : aviso(t("man_mensajes_en_espanol")),
    h("div", { clase: "tarjeta" }, caja, chips, zona,
      h("p", { clase: "chico gris" }, t("man_mensajes_pie"))),
  ].filter(Boolean));
}

/* ------------------------------------------------------ quien puede que */

function tablaPermisos(filas, pareja, porNombre) {
  return h("table", { clase: "lista man-permisos" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("man_col_actividad")), h("th", {}, t("man_col_roles")),
      h("th", {}, t("man_col_puestos")))),
    h("tbody", {}, ...filas.map(a => {
      const otra = pareja.get(a.actividad);
      const suya = otra ? (porNombre.get(otra) || {}).descripcion || otra : null;
      return h("tr", {},
        h("td", {}, a.descripcion,
          h("div", { clase: "chico gris man-codigo" }, a.actividad),
          suya ? h("div", { clase: "chico ambar" }, llenar("man_no_convive", { a: suya })) : null),
        h("td", { clase: "chico" }, a.roles.map(nombreDelRol).join(", ")),
        h("td", { clase: "chico" }, a.puestos.length ? a.puestos.join(", ")
          : h("span", { clase: "gris" }, t("man_ningun_puesto"))));
    })));
}

function dosManos(d, porNombre) {
  const nombre = (a) => (porNombre.get(a) || {}).descripcion || a;
  return h("div", { clase: "tarjeta" },
    h("h3", {}, t("man_dos_manos")),
    h("p", { clase: "chico gris" }, t("man_dos_manos_pie")),
    h("ul", { clase: "man-lista" }, ...d.permisos.dos_manos.map(([a, b]) =>
      h("li", {}, nombre(a), h("b", {}, " ⇄ "), nombre(b)))));
}

function lasParejas(d) {
  const pareja = new Map();
  for (const [a, b] of d.permisos.dos_manos) {
    pareja.set(a, b);
    pareja.set(b, a);
  }
  return pareja;
}

function permisos(main, d) {
  const actividades = d.permisos.actividades;
  const porNombre = new Map(actividades.map(a => [a.actividad, a]));
  const pareja = lasParejas(d);
  const roles = [...new Set(actividades.flatMap(a => a.roles))]
    .sort((a, b) => nombreDelRol(a).localeCompare(nombreDelRol(b)));
  const rol = lista("rol", [{ valor: "", texto: t("man_todos_roles") },
    ...roles.map(r => ({ valor: r, texto: nombreDelRol(r) }))],
    { style: "width:auto" });
  const caja = cajaDeBuscar(t("man_buscar_permiso"), buscado);
  const zona = h("div");

  const pintar = () => {
    const q = caja.value.trim();
    const vistas = actividades.filter(a => (!rol.value || a.roles.includes(rol.value))
      && dice(`${a.actividad} ${a.descripcion} ${a.puestos.join(" ")}`, q));
    zona.replaceChildren(...porFamilia(vistas).map(g => h("div", { clase: "tarjeta" },
      h("h3", {}, g.titulo), tablaPermisos(g.filas, pareja, porNombre))));
  };
  caja.addEventListener("input", pintar);
  rol.addEventListener("change", pintar);
  pintar();

  main.append(...[
    volver(),
    h("h1", {}, t("man_permisos_titulo")),
    h("p", { clase: "sub" }, t("man_permisos_sub")),
    aviso(t("man_permisos_pie")),
    idioma() === "es" ? null : h("p", { clase: "chico gris" }, t("man_permisos_desc_es")),
    h("div", { clase: "acciones man-barra" }, caja, rol),
    zona,
    dosManos(d, porNombre),
  ].filter(Boolean));
}

/* ------------------------------------------------------------ novedades */

function novedadLarga(n) {
  return h("div", { clase: "man-novedad-larga" },
    h("h3", {}, n.titulo),
    h("div", { clase: "chico gris" }, `${n.fecha} · ${llenar("man_seccion", { n: n.seccion })}`),
    h("p", {}, ...trozos(n.partes)));
}

function novedades(main, d) {
  main.append(...[
    volver(),
    h("h1", {}, t("man_novedades_titulo")),
    h("p", { clase: "sub" }, t("man_novedades_sub")),
    enOtroIdioma(d),
    h("div", { clase: "tarjeta" }, ...d.novedades.map(novedadLarga)),
  ].filter(Boolean));
}

/* ------------------------------------------------------ casos resueltos */

const FALLA = { si: ["man_etq_falla", "grave"], no_se: ["man_etq_no_se", "alerta"] };

function nombreDelArea(d, clave) {
  const a = d.areas.find(x => x.clave === clave);
  return a ? a.titulo : clave;
}

function tarjetaCaso(d, c, alEditar = null) {
  const falla = FALLA[c.falla];
  const quien = [
    c.area ? nombreDelArea(d, c.area) : null,
    llenar("man_escrito_por", { q: c.escrito_por || "—", f: fecha(c.escrito_en) }),
    c.editado_en ? llenar("man_editado_por", { q: c.editado_por || "—", f: fecha(c.editado_en) })
                 : null,
  ].filter(Boolean).join(" · ");
  const parte = (clave, valor) => [h("h4", {}, t(clave)),
                                   h("p", { clase: "man-largo" }, valor)];
  return h("div", { clase: "tarjeta lisa man-caso" },
    h("div", { clase: "man-caso-cabeza" },
      h("h3", {}, c.titulo),
      falla ? etiqueta(t(falla[0]), falla[1]) : null,
      alEditar ? h("button", { clase: "claro chico", type: "button",
                               onclick: () => alEditar(c) }, t("man_editar")) : null),
    h("div", { clase: "chico gris" }, quien),
    ...parte("man_caso_que_se_vio", c.que_se_vio),
    ...parte("man_caso_causa", c.causa),
    ...parte("man_caso_solucion", c.solucion));
}

/* El caso se escribe para quien lo va a leer la proxima vez que pase:
   que se vio, la causa y como se arreglo. Y si la causa fue una falla
   del sistema, lo dice: regla de Salvador (27 sep), la falla chica que
   no cambia como se trabaja se arregla directo y se le avisa; la que
   pide cambiar un proceso lleva primero su propuesta. */
function formularioCaso(d, caso, alGuardar, alCancelar) {
  const titulo = h("input", { type: "text", maxlength: "160", "data-crudo": "",
                              value: caso ? caso.titulo : null });
  const area = lista("area", [{ valor: "", texto: t("man_caso_sin_area") },
    ...d.areas.map(a => ({ valor: a.clave, texto: a.titulo }))]);
  area.value = caso && caso.area ? caso.area : "";
  const largo = (valor) => h("textarea", { rows: "3", maxlength: "4000" }, valor || "");
  const queSeVio = largo(caso && caso.que_se_vio);
  const causa = largo(caso && caso.causa);
  const solucion = largo(caso && caso.solucion);
  const falla = lista("falla", [
    { valor: "no_se", texto: t("man_falla_no_se") },
    { valor: "si", texto: t("man_falla_si") },
    { valor: "no", texto: t("man_falla_no") }]);
  falla.value = caso ? caso.falla : "no_se";

  const campo = (clave, control) => h("div", { clase: "campo" },
    h("label", {}, t(clave)), control);
  const guardar = h("button", { type: "button", onclick: async () => {
    guardar.disabled = true;
    const datos = { titulo: titulo.value, area: area.value, que_se_vio: queSeVio.value,
                    causa: causa.value, solucion: solucion.value, falla: falla.value };
    try {
      if (caso) await api.patch(`/manual/casos/${caso.id}`, datos);
      else await api.post("/manual/casos", datos);
      mensaje(t("man_guardado"));
      await alGuardar();
    } catch (err) {
      mensaje(err.message, "grave");
      guardar.disabled = false;
    }
  } }, t("man_guardar"));

  return h("div", { clase: "tarjeta man-formulario" },
    campo("man_caso_titulo", titulo),
    campo("man_caso_area", area),
    campo("man_caso_que_se_vio", queSeVio),
    campo("man_caso_causa", causa),
    campo("man_caso_solucion", solucion),
    campo("man_caso_falla", falla),
    h("p", { clase: "chico gris" }, t("man_falla_pie")),
    h("div", { clase: "acciones" }, guardar,
      h("button", { clase: "claro", type: "button", onclick: alCancelar }, t("man_cancelar"))));
}

function casos(main, d) {
  let todos = d.casos;
  const formulario = h("div");
  const caja = cajaDeBuscar(t("man_buscar_caso"));
  const cuales = lista("cuales", [], { style: "width:auto" });
  const zona = h("div");

  const pintarCuales = () => {
    const antes = cuales.value;
    const fallas = todos.filter(c => c.falla === "si").length;
    cuales.replaceChildren(
      h("option", { value: "" }, llenar("man_todos_casos", { n: todos.length })),
      h("option", { value: "si" }, llenar("man_solo_fallas", { n: fallas })));
    cuales.value = antes || "";
  };

  const pintar = () => {
    const q = caja.value.trim();
    const vistos = todos.filter(c => (!cuales.value || c.falla === cuales.value)
      && dice([c.titulo, c.que_se_vio, c.causa, c.solucion,
               c.area ? nombreDelArea(d, c.area) : ""].join(" "), q));
    zona.replaceChildren(...(vistos.length ? vistos.map(c => tarjetaCaso(d, c, abrir))
      : [h("p", { clase: "gris" }, t(todos.length ? "man_sin_casos_asi" : "man_sin_casos"))]));
  };

  const cerrar = () => {
    formulario.replaceChildren();
    anotar.hidden = false;
  };
  const recargar = async () => {
    todos = await api.get("/manual/casos");
    d.casos = todos;
    cerrar();
    pintarCuales();
    pintar();
  };
  function abrir(caso = null) {
    anotar.hidden = true;
    formulario.replaceChildren(formularioCaso(d, caso, recargar, cerrar));
    formulario.scrollIntoView({ block: "start" });
  }
  const anotar = h("button", { type: "button", onclick: () => abrir() }, t("man_anotar"));

  caja.addEventListener("input", pintar);
  cuales.addEventListener("change", pintar);
  pintarCuales();
  pintar();

  main.append(...[
    volver(),
    h("h1", {}, t("man_casos_titulo")),
    h("p", { clase: "sub" }, t("man_casos_sub")),
    h("div", { clase: "acciones man-barra" }, anotar, caja, cuales),
    formulario,
    zona,
  ].filter(Boolean));
}

/* ---------------------------------------------------------- en PDF

   El manual entero en una sola hoja larga, para la ventana de imprimir
   del navegador: de ahi sale el PDF. Lo que no sirve en papel --la barra,
   los botones-- no se imprime (estilo.css, @media print). */
async function imprimir(main, d) {
  let estado = null;
  try {
    estado = await api.get(`/manual/estado?idioma=${idioma()}`);
  } catch {
    estado = null;
  }
  const ahora = new Date().toISOString();
  const entender = d.capitulos.filter(c => c.parte === "entender");
  const sintomas = d.capitulos.filter(c => c.parte === "resolver");
  const porNombre = new Map(d.permisos.actividades.map(a => [a.actividad, a]));
  const pareja = lasParejas(d);

  const capitulo = (c, nivel = "h2") => h("div", { clase: "man-impreso-capitulo" },
    h(nivel, {}, c.titulo), texto(c));
  const parte = (titulo, ...nodos) => h("div", { clase: "man-impreso-parte" },
    h("h1", {}, titulo), ...nodos);

  main.append(...[
    h("div", { clase: "acciones man-barra man-no-imprimir" },
      volver(),
      h("button", { type: "button", onclick: () => window.print() }, t("man_imprimir")),
      h("span", { clase: "chico gris" }, t("man_impreso_pie"))),
    h("div", { clase: "man-impreso" },
      h("h1", {}, t("man_titulo")),
      h("p", { clase: "sub" }, llenar("man_impreso_de", {
        n: d.version.seccion, f: d.version.fecha, h: `${fecha(ahora)} ${hora(ahora)}` })),
      enOtroIdioma(d),
      estado ? h("div", {},
        h("h2", {}, t("man_estado_al_imprimir")),
        h("div", { clase: "rejilla tres man-estado" }, ...estado.tarjetas.map(tarjetaEstado)))
        : null,
      parte(t("man_p1_titulo"), ...entender.map(c => capitulo(c))),
      parte(t("man_p2_titulo"), ...sintomas.map(c => capitulo(c, "h3"))),
      parte(t("man_casos_titulo"), ...(d.casos.length ? d.casos.map(c => tarjetaCaso(d, c))
        : [h("p", { clase: "gris" }, t("man_sin_casos"))])),
      parte(t("man_reloj_titulo"), h("p", { clase: "chico gris" }, t("man_reloj_horas")),
        tablaDelReloj(h("tbody", {}, ...filasDelReloj(d.reloj)))),
      parte(t("man_permisos_titulo"), h("p", { clase: "chico gris" }, t("man_permisos_pie")),
        tablaPermisos(d.permisos.actividades, pareja, porNombre)),
      parte(t("man_mensajes_titulo"), ...d.mensajes.map(renglonMensaje),
        h("p", { clase: "chico gris" }, t("man_mensajes_pie"))),
      parte(t("man_novedades_titulo"), ...d.novedades.map(novedadLarga))),
  ].filter(Boolean));

  /* Un momento para que el navegador acomode la hoja antes de abrir la
     ventana de imprimir. */
  setTimeout(() => window.print(), 400);
}

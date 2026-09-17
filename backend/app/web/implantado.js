/* Cartera y alta de implantados.

   El implantado es continuo: un renglon por servicio, no uno por mes.
   Lo que importa de un vistazo es quien lo cubre, con que unidad y
   hasta que mes esta armado —eso es lo que se pregunta por telefono—.

   El alta arranca igual que la del eventual —cliente, quien solicita,
   ejecutivo— y termina distinto: en lugar de dias con agenda se captura
   el trato, que no cambia, y la plantilla del primer mes. */
import { api, sesion } from "./api.js";
import { catalogos } from "./catalogos.js";
import { campo, dinero, entrada, estatus, etiqueta, h, lista, mensaje, telefono, vaciar } from "./util.js";
import { buscadorDeLugar } from "./mapa.js";
import { IDIOMAS, idioma, t } from "./idioma.js";

const TONO_ESTATUS = {
  borrador: "", solicitado: "info", cotizado: "", autorizado: "ok", planeado: "alerta",
  asignado: "ok", en_curso: "alerta", terminado: "", cerrado: "ok",
  cancelado: "grave",
};

/* Hasta que dia de la semana llega cada esquema. En JavaScript el
   domingo es 0, asi que se corre para que el lunes sea 0 y la cuenta
   quede como se lee un calendario. */
const HASTA = { lunes_viernes: 5, lunes_sabado: 6, todos: 7 };
const lunesPrimero = (fecha) => (fecha.getDay() + 6) % 7;

/* El mes pintado.

   verde  cubierto
   ambar  fin de semana contratado al que le falta quien lo cubra: el que
          trabajo toda la semana descansa, y darlo por hecho es como se
          llega al sabado sin conductor
   gris   no hay servicio contratado ese dia

   Lo usan las dos pantallas: en el alta pinta lo que se esta capturando,
   antes de guardar nada, y en el servicio pinta lo que hay en la base,
   con el nombre de quien cubre cada dia. Una sola regla de color para
   los dos, que es como no terminan diciendo cosas distintas. */
function widgetCalendario(alPicar = null) {
  const titulo = h("div", { clase: "calendario-mes" });
  const rejilla = h("div", { clase: "calendario" });
  const leyenda = h("div", {},
    h("div", { clase: "calendario-leyenda" },
      h("span", {}, h("i", { clase: "punto verde" }), t("imp_leyenda_verde")),
      h("span", {}, h("i", { clase: "punto ambar" }), t("imp_leyenda_ambar")),
      h("span", {}, h("i", { clase: "punto gris" }), t("imp_leyenda_gris"))),
    h("p", { clase: "gris chico", style: "margin:8px 0 0" },
      t("imp_calendario_ayuda")));

  /* cubiertos: fecha ISO -> quien la cubre. Vacio en el alta, porque
     todavia no hay nadie asignado a ningun dia. */
  function pintar(fechaISO, diasServicio, cubiertos = {}) {
    vaciar(rejilla);
    vaciar(titulo);
    if (!fechaISO) {
      rejilla.append(h("div", { clase: "vacio" }, t("imp_sin_fecha")));
      return;
    }

    const inicio = new Date(`${fechaISO}T12:00:00`);
    const anio = inicio.getFullYear();
    const mes = inicio.getMonth();
    const desde = inicio.getDate();
    const tope = HASTA[diasServicio] || 5;
    const ultimo = new Date(anio, mes + 1, 0).getDate();
    const lengua = idioma();

    titulo.append(h("b", {}, new Intl.DateTimeFormat(lengua, {
      month: "long", year: "numeric" }).format(inicio)));

    // Encabezado de lunes a domingo, en el idioma de la consola.
    const corto = new Intl.DateTimeFormat(lengua, { weekday: "short" });
    for (let d = 0; d < 7; d++) {
      rejilla.append(h("div", { clase: "calendario-cabeza" },
        corto.format(new Date(2024, 0, 1 + d))));   // 1 de enero de 2024: lunes
    }

    // Los huecos de antes del dia 1, para que las columnas cuadren.
    for (let i = 0; i < lunesPrimero(new Date(anio, mes, 1)); i++) {
      rejilla.append(h("div", { clase: "calendario-hueco" }));
    }

    for (let numero = 1; numero <= ultimo; numero++) {
      const dia = new Date(anio, mes, numero);
      const semana = lunesPrimero(dia);
      const iso = `${anio}-${String(mes + 1).padStart(2, "0")}-`
                + `${String(numero).padStart(2, "0")}`;
      const quien = cubiertos[iso];

      let tono = "gris";
      let titulo_ = t("imp_dia_sin_servicio");

      if (quien) {
        tono = "verde";
        titulo_ = quien;
      } else if (numero < desde) {
        titulo_ = t("imp_dia_antes");
      } else if (semana < 5) {
        tono = "verde";
        titulo_ = t("imp_dia_cubierto");
      } else if (semana < tope) {
        tono = "ambar";
        titulo_ = t("imp_dia_por_cubrir");
      }

      /* En el alta el calendario solo se lee. En el servicio se pica:
         ahi ya existe el mes y hay a quien asignarle el dia. */
      rejilla.append(h("div", {
        clase: `calendario-dia ${tono}${alPicar ? " se-puede" : ""}`,
        title: titulo_,
        onclick: alPicar ? () => alPicar(iso) : null,
      }, String(numero)));
    }
  }

  return { titulo, rejilla, leyenda, pintar,
           nodo: h("div", {}, titulo, rejilla, leyenda) };
}

/* Quien cubre y con que unidad, en dos listas.

   Son dos cosas distintas y se agregan por separado: un servicio puede
   llevar dos personas y un coche, o una persona y ninguno. Meterlas en
   el mismo renglon obligaba a inventar una unidad para cada persona.

   La liga entre las dos vive en la unidad: cada unidad dice quien la
   lleva. Asi se lee como se opera —"la Suburban la maneja Ernesto"— y
   cae sola la regla que valida el servidor: ninguna unidad sale sin
   alguien de seguridad a bordo.

   La disponibilidad de un implantado no es la de un dia: es la del mes
   completo, porque es la misma persona todos los dias. Alguien que trae
   otro servicio el dia 12 no sirve aunque hoy este libre, asi que cada
   nombre y cada placa se ofrecen con cuantos de los dias verdes del
   calendario puede de verdad. */
function widgetPlantilla(cat, ciudadId, alCambiar = () => {},
                         disponibilidad = () => null) {
  const gente = [];
  const flota = [];
  const cuerpoGente = h("tbody");
  const cuerpoFlota = h("tbody");

  /* El personal y la flota se ofrecen de la ciudad donde opera: un
     implantado de Monterrey no se cubre con gente de Guadalajara, y una
     lista de doscientos nombres es una lista que nadie lee. */
  const deLaCiudad = (coleccion) => coleccion.filter(
    x => !ciudadId() || String(x.plaza_id) === String(ciudadId()));

  // "libre 22/22", o nada mientras no se sepa de que mes hablamos.
  function cuantosDias(ficha) {
    const d = disponibilidad();
    if (!d || !ficha) return "";
    return ` · ${t("imp_libre")} ${ficha.libres}/${d.dias}`;
  }

  /* --------------------------------------------------------- personal */

  /* Primero el rol, despues la persona.

     El rol es de la tarea, no de la persona: el personal de seguridad
     es general y el mismo agente que hoy conduce manana coordina. Por
     eso los cuatro roles se ofrecen siempre, y la lista de personas no
     se filtra por ellos —sale todo el que este libre esos dias—. De
     este rol salen el precio al cliente y la comision que se le paga. */
  function opcionesPerfil() {
    return [{ valor: "", texto: t("imp_elige_rol") },
      ...cat.perfiles.map(p => ({ valor: p.id, texto: p.nombre || p.codigo }))];
  }

  function opcionesPersona(perfilId) {
    if (!perfilId) return [{ valor: "", texto: t("imp_elige_rol") }];
    const d = disponibilidad();
    if (d) {
      return [{ valor: "", texto: t("imp_elige_persona") },
        ...d.personal.map(p => ({ valor: p.persona_id,
                                  texto: `${p.nombre}${cuantosDias(p)}` }))];
    }
    /* Sin fecha todavia no hay mes contra que medir: se ofrece el
       catalogo de la ciudad, sin disponibilidad. */
    return [{ valor: "", texto: t("imp_elige_persona") },
      ...deLaCiudad(cat.personal).map(p => ({ valor: p.id, texto: p.nombre }))];
  }

  /* ---------------------------------------------------------- unidades */

  /* La unidad se escoge por categoria, que es como la pide el cliente:
     "una SUV blindada", no "la CTR-105". La placa viene despues. */
  function opcionesCategoria() {
    const d = disponibilidad();
    const hay = d
      ? new Set(d.vehiculos.map(v => String(v.categoria_id)))
      : new Set(deLaCiudad(cat.vehiculos).map(v => String(v.categoria_id)));
    return [{ valor: "", texto: t("imp_elige_categoria") },
      ...cat.categorias
        .filter(c => hay.has(String(c.id)))
        .map(c => ({ valor: c.id, texto: c.nombre || c.codigo }))];
  }

  function opcionesUnidad(categoriaId) {
    if (!categoriaId) return [{ valor: "", texto: t("imp_elige_categoria") }];
    const d = disponibilidad();
    if (d) {
      return [{ valor: "", texto: t("imp_elige_unidad") },
        ...d.vehiculos
          .filter(v => String(v.categoria_id) === String(categoriaId))
          .map(v => ({
            valor: v.vehiculo_id,
            texto: `${v.placa}${v.marca_modelo ? " · " + v.marca_modelo : ""}`
                   + cuantosDias(v) }))];
    }
    return [{ valor: "", texto: t("imp_elige_unidad") },
      ...deLaCiudad(cat.vehiculos)
        .filter(v => String(v.categoria_id) === String(categoriaId))
        .map(v => ({
          valor: v.id,
          texto: v.marca_modelo ? `${v.placa} · ${v.marca_modelo}` : v.placa }))];
  }

  // Quien puede llevar una unidad: los que ya estan en la lista de arriba.
  function opcionesConductor() {
    return [{ valor: "", texto: t("imp_elige_conductor") },
      ...gente
        .filter(f => f.persona.value)
        .map(f => ({ valor: f.persona.value,
                     texto: f.persona.options[f.persona.selectedIndex].textContent
                              .split(" · ")[0] }))];
  }

  function ponerOpciones(control, opciones) {
    const antes = control.value;
    control.replaceChildren(...opciones.map(
      o => h("option", { value: o.valor }, o.texto)));
    control.value = [...control.options].some(o => o.value === antes)
      ? antes : "";
  }

  /* Al cambiar la ciudad, la fecha o los dias, las listas se rehacen.
     Lo que ya estaba elegido se respeta si sigue existiendo. */
  function repintar() {
    revisarCatalogo();
    for (const f of gente) {
      ponerOpciones(f.perfil, opcionesPerfil());
      ponerOpciones(f.persona, opcionesPersona(f.perfil.value));
    }
    for (const f of flota) {
      ponerOpciones(f.categoria, opcionesCategoria());
      ponerOpciones(f.unidad, opcionesUnidad(f.categoria.value));
      ponerOpciones(f.conductor, opcionesConductor());
    }
  }

  function agregarPersona() {
    const perfil = lista("perfil_id", opcionesPerfil(),
                         { onchange: () => {
                           ponerOpciones(persona, opcionesPersona(perfil.value));
                           cambio();
                         } });
    const persona = lista("persona_id", opcionesPersona(""),
                          { onchange: () => cambio() });

    const fila = h("tr", {},
      h("td", {}, perfil),
      h("td", {}, persona),
      h("td", {}, h("button", { clase: "claro chico", type: "button",
        onclick: () => quitar() }, t("quitar"))));

    const registro = { perfil, persona, fila };
    function quitar() {
      const i = gente.indexOf(registro);
      if (i >= 0) gente.splice(i, 1);
      fila.remove();
      cambio();
    }

    gente.push(registro);
    cuerpoGente.append(fila);
    cambio();
  }

  function agregarUnidad() {
    const categoria = lista("categoria_id", opcionesCategoria(),
                            { onchange: () => {
                              ponerOpciones(unidad, opcionesUnidad(categoria.value));
                              cambio();
                            } });
    const unidad = lista("vehiculo_id", opcionesUnidad(""),
                         { onchange: () => cambio() });
    const conductor = lista("lleva_id", opcionesConductor(),
                            { onchange: () => cambio() });

    const fila = h("tr", {},
      h("td", {}, categoria),
      h("td", {}, unidad),
      h("td", {}, conductor),
      h("td", {}, h("button", { clase: "claro chico", type: "button",
        onclick: () => quitar() }, t("quitar"))));

    const registro = { categoria, unidad, conductor, fila };
    function quitar() {
      const i = flota.indexOf(registro);
      if (i >= 0) flota.splice(i, 1);
      fila.remove();
      cambio();
    }

    flota.push(registro);
    cuerpoFlota.append(fila);
    cambio();
  }

  /* Cambiar a alguien de la lista de personal cambia quien puede llevar
     una unidad: las dos listas se miran. */
  function cambio() {
    for (const f of flota) ponerOpciones(f.conductor, opcionesConductor());
    alCambiar();
  }

  /* Lo que se manda: una linea por persona, con la unidad que lleva —si
     lleva alguna—. Sale de la liga que vive en la unidad. */
  function valor() {
    return gente
      .filter(f => f.persona.value)
      .map(f => {
        const suya = flota.find(
          v => v.unidad.value && v.conductor.value === f.persona.value);
        return {
          persona_id: Number(f.persona.value),
          rol_id: Number(f.perfil.value) || null,
          vehiculo_id: suya ? Number(suya.unidad.value) : null,
        };
      });
  }

  const unidades = () => [...new Set(flota.filter(f => f.unidad.value)
                                          .map(f => Number(f.unidad.value)))];

  /* Una ciudad sin gente de seguridad deja los selectores vacios, y un
     selector vacio no explica nada: lo dice. */
  const avisoVacio = h("div", { clase: "bloqueo", hidden: true });

  function revisarCatalogo() {
    const d = disponibilidad();
    const sinGente = (d ? d.personal.length
                        : deLaCiudad(cat.personal).length) === 0;
    const sinFlota = opcionesCategoria().length <= 1;
    avisoVacio.hidden = !sinGente && !sinFlota;
    if (avisoVacio.hidden) return;
    const falta = [sinGente ? t("imp_sin_gente_ciudad") : null,
                   sinFlota ? t("imp_sin_flota_ciudad") : null].filter(Boolean);
    avisoVacio.replaceChildren(...falta.map(x => h("div", {}, x)));
  }

  const nodo = h("div", {},
    avisoVacio,
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("imp_col_rol")),
        h("th", {}, t("imp_col_persona")),
        h("th", {}, ""))),
      cuerpoGente),
    h("div", { clase: "acciones", style: "margin-top:10px" },
      h("button", { clase: "claro chico", type: "button",
        onclick: () => agregarPersona() }, t("imp_agregar_persona"))),

    h("h4", { clase: "grupo" }, t("imp_unidades")),
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("imp_col_categoria")),
        h("th", {}, t("col_unidad")),
        h("th", {}, t("imp_col_lleva")),
        h("th", {}, ""))),
      cuerpoFlota),
    h("div", { clase: "acciones", style: "margin-top:10px" },
      h("button", { clase: "claro chico", type: "button",
        onclick: () => agregarUnidad() }, t("imp_agregar_unidad"))));

  revisarCatalogo();

  return { nodo, agregar: agregarPersona, agregarUnidad, repintar,
           valor, unidades };
}

/* Por donde opera el servicio. No es un punto: es un pedazo de ciudad,
   y cada pais lo parte a su manera —alcaldias en Mexico, municipios en
   Brasil, comunas en Chile—. Se piden a Google como "regiones" y cada
   pais contesta con las suyas, en vez de mantener una lista a mano que
   se desactualiza sola. Se eligen varias: un ejecutivo vive en una
   alcaldia y trabaja en otra. */
const DIVISION = {
  MX: "alcaldias y municipios", BR: "municipios", CL: "comunas",
  AR: "partidos y comunas", CO: "municipios y localidades",
  PE: "distritos", EC: "cantones y parroquias", PA: "distritos",
  GT: "municipios", DO: "municipios", CR: "cantones",
};

const DIAS_DE_SERVICIO = () => [
  { valor: "lunes_viernes", texto: t("imp_lunes_viernes") },
  { valor: "lunes_sabado", texto: t("imp_lunes_sabado") },
  { valor: "todos", texto: t("imp_todos_los_dias") },
];


function widgetZona({ cat, paisId, pin = () => ({}), valores = "" }) {
  const elegidas = String(valores || "").split(",")
    .map(x => x.trim()).filter(Boolean);
  const fichas = h("div", { clase: "zonas" });
  const opciones = h("div", { clase: "resultados" });
  const caja = h("input", { oninput: () => esperar() });
  let sesion = nuevaSesion();
  let reloj = null;

  function palabra() {
    const pais = cat.paises.find(p => String(p.id) === String(paisId()));
    return DIVISION[(pais && pais.codigo) || ""] || t("imp_zona_generico");
  }

  function pintar() {
    fichas.replaceChildren(...elegidas.map((nombre, i) =>
      h("span", { clase: "zona" }, nombre,
        h("button", { type: "button", clase: "quitar-zona",
          title: t("quitar"),
          onclick: () => { elegidas.splice(i, 1); pintar(); } }, "\u00d7"))));
  }

  function esperar() {
    clearTimeout(reloj);
    reloj = setTimeout(consultar, 300);   // no una peticion por tecla
  }

  async function consultar() {
    const texto = caja.value.trim();
    opciones.replaceChildren();
    if (texto.length < 3) return;

    const parametros = new URLSearchParams({ texto, sesion, tipos: "regiones" });
    if (paisId()) parametros.set("pais_id", paisId());
    const punto = pin() || {};
    if (punto.lat && punto.lon) {
      parametros.set("lat", punto.lat);
      parametros.set("lon", punto.lon);
    }

    try {
      const r = await api.get(`/mapas/sugerencias?${parametros}`);
      opciones.replaceChildren(...(r.lugares || []).map(lugar =>
        h("button", { clase: "resultado", type: "button",
          onclick: () => agregar(lugar.nombre) },
          h("b", {}, lugar.nombre),
          lugar.direccion ? h("span", { clase: "gris chico" },
                              lugar.direccion) : null)));
    } catch (err) {
      /* Sin llave de Google o sin red. No se traba la captura: lo que
         este escrito se toma tal cual, que es como se trabajaba antes de
         que existiera el buscador. El motivo se dice tal cual: sin el,
         no hay nada que arreglar. */
      opciones.replaceChildren(
        h("div", { clase: "gris chico" }, t("imp_zona_a_mano")),
        h("div", { clase: "gris chico" }, err.message || ""));
    }
  }

  function agregar(nombre) {
    if (nombre && !elegidas.includes(nombre)) elegidas.push(nombre);
    caja.value = "";
    opciones.replaceChildren();
    sesion = nuevaSesion();            // se cierra el cobro de esa busqueda
    pintar();
  }

  pintar();
  caja.placeholder = `${t("imp_zona_buscar")} ${palabra()}`;

  return {
    nodo: h("div", {}, caja, opciones, fichas),
    /* Lo que se escribio y no se eligio de la lista tambien cuenta: hay
       zonas que Google no conoce por su nombre de calle. */
    valor: () => [...elegidas, caja.value.trim()].filter(Boolean).join(", ")
                 || null,
    repintar: () => { caja.placeholder = `${t("imp_zona_buscar")} ${palabra()}`; },
  };
}

/* ------------------------------------------------------------ cartera */

export async function carteraImplantados(main) {
  const servicios = await api.get("/implantados");

  main.append(
    h("h1", {}, t("implantados_titulo")),
    h("p", { clase: "sub" }, t("implantados_sub")),
    h("div", { clase: "acciones", style: "margin-bottom:16px" },
      h("button", { onclick: () => (location.hash = "#/implantado/nuevo") },
        t("nuevo_implantado"))));

  if (!servicios.length) {
    main.append(h("div", { clase: "tarjeta" },
      h("div", { clase: "vacio" }, t("sin_implantados"))));
    return;
  }

  const vacio = () => h("span", { clase: "gris" }, "—");
  const cuerpo = h("tbody");
  for (const s of servicios) {
    cuerpo.append(h("tr", { clase: "clic",
      onclick: () => (location.hash = `#/implantado/${s.servicio_id}`) },
      h("td", {}, h("b", {}, s.folio),
        h("div", { clase: "gris chico" }, s.ciudad || "")),
      h("td", {}, s.cliente || vacio()),
      h("td", {}, s.ejecutivo || vacio()),
      h("td", {}, s.titular || vacio()),
      h("td", {}, s.unidad || vacio()),
      h("td", {}, s.ultimo_mes || vacio()),
      h("td", {}, etiqueta(estatus(s.estatus), TONO_ESTATUS[s.estatus] || ""))));
  }

  main.append(h("table", { clase: "lista" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("col_folio")), h("th", {}, t("col_cliente")),
      h("th", {}, t("col_ejecutivo")), h("th", {}, t("col_titular")),
      h("th", {}, t("col_unidad")), h("th", {}, t("col_ultimo_mes")),
      h("th", {}, t("col_estatus")))),
    cuerpo));
}

/* ------------------------------------------------------------ alta */

/* Google cobra por sesion: todas las teclas de una misma busqueda mas el
   lugar que se elija cuentan como una. El identificador se renueva cada
   vez que se cierra una busqueda. */
function nuevaSesion() {
  return (crypto.randomUUID && crypto.randomUUID())
         || String(Date.now() + Math.random());
}


export async function nuevoImplantado(main) {
  const cat = await catalogos();
  const hoy = new Date();

  /* ================================================ cliente y ciudad */

  const clientes = lista("cliente_id",
    [{ valor: "", texto: t("elige_cliente") },
     ...cat.clientes.map(c => ({ valor: c.id, texto: c.nombre }))],
    { onchange: () => { cargarSolicitantes(); revisar(); } });

  const consultores = lista("consultor_id",
    cat.consultores.map(c => ({ valor: c.id, texto: c.nombre })));
  if (sesion.usuario && sesion.usuario.persona_id) {
    const suyo = cat.consultores.find(c => c.id === sesion.usuario.persona_id);
    if (suyo) consultores.value = suyo.id;
  }

  const paises = lista("pais_id",
    cat.paises.map(p => ({ valor: p.id, texto: p.nombre })),
    { onchange: () => {
      repintarCiudades(); repintarModalidades(); clavesDeTelefono();
      zona.repintar(); revisar();
    } });

  const ciudades = lista("plaza_id", [], {
    onchange: () => { verBuscadorCiudad(); traerDisponibilidad(); revisar(); } });

  // "nueva" no es una ciudad: es la opcion de dar de alta una.
  const ciudadElegida = () => (ciudades.value && ciudades.value !== "nueva"
    ? ciudades.value : null);

  /* Una ciudad donde nunca se ha operado no esta en el catalogo, y el
     consultor no tiene por que esperar a que alguien se la de de alta.
     Se busca en Google y se guarda con el nombre que tiene de verdad:
     escrita a mano, la misma ciudad entra tres veces con tres
     ortografias y despues nadie puede contar cuantos servicios hubo
     ahi. */
  const buscarCiudad = h("input", { oninput: () => esperarCiudad() });
  const opcionesCiudad = h("div", { clase: "resultados" });
  const cajaCiudad = h("div", { hidden: true, style: "margin-top:8px" },
                       buscarCiudad, opcionesCiudad);
  let sesionCiudad = nuevaSesion();
  let relojCiudad = null;

  function verBuscadorCiudad() {
    const nueva = ciudades.value === "nueva";
    cajaCiudad.hidden = !nueva;
    opcionesCiudad.replaceChildren();
    if (nueva) buscarCiudad.focus();
  }

  function esperarCiudad() {
    clearTimeout(relojCiudad);
    relojCiudad = setTimeout(consultarCiudad, 300);
  }

  async function consultarCiudad() {
    const texto = buscarCiudad.value.trim();
    opcionesCiudad.replaceChildren();
    if (texto.length < 3) return;

    const parametros = new URLSearchParams({
      texto, sesion: sesionCiudad, tipos: "ciudades" });
    if (paises.value) parametros.set("pais_id", paises.value);

    try {
      const r = await api.get(`/mapas/sugerencias?${parametros}`);
      opcionesCiudad.replaceChildren(...(r.lugares || []).map(lugar =>
        h("button", { clase: "resultado", type: "button",
          onclick: () => darDeAltaCiudad(lugar.nombre) },
          h("b", {}, lugar.nombre),
          lugar.direccion ? h("span", { clase: "gris chico" },
                              lugar.direccion) : null)));
    } catch (err) {
      opcionesCiudad.replaceChildren(
        h("div", { clase: "gris chico" }, t("imp_ciudad_a_mano")),
        h("div", { clase: "gris chico" }, err.message || ""));
    }
  }

  async function darDeAltaCiudad(nombre) {
    // La que ya estaba no se da de alta dos veces: se elige.
    const ya = cat.plazas.find(
      p => String(p.pais_id) === String(paises.value)
           && p.nombre.toLowerCase() === nombre.toLowerCase());
    if (ya) {
      ciudades.value = ya.id;
      verBuscadorCiudad();
      traerDisponibilidad();
      revisar();
      return;
    }

    try {
      const ciudad = await api.post("/catalogos/plazas",
                                    { nombre, pais_id: Number(paises.value) });
      cat.plazas.push(ciudad);
      repintarCiudades();
      ciudades.value = ciudad.id;
      buscarCiudad.value = "";
      sesionCiudad = nuevaSesion();
      verBuscadorCiudad();
      traerDisponibilidad();
      revisar();
      mensaje(`${ciudad.nombre} ${t("ciudad_dada_alta")}`);
    } catch (err) {
      mensaje(err.message, "grave");
    }
  }

  function repintarCiudades() {
    const antes = ciudades.value;
    ciudades.replaceChildren(
      ...cat.plazas
        .filter(p => String(p.pais_id) === String(paises.value))
        .map(p => h("option", { value: p.id }, p.nombre)),
      h("option", { value: "nueva" }, t("otra_ciudad")));
    if (antes && [...ciudades.options].some(o => o.value === antes)) {
      ciudades.value = antes;
    }
    verBuscadorCiudad();
  }

  /* ================================================ quien solicita */

  const solicitanteCorreo = entrada("solicitante_correo", {
    type: "email", oninput: () => reconocerPorCorreo() });
  const solicitante = entrada("solicitante_nombre", { oninput: () => revisar() });
  const solicitanteApellidos = entrada("solicitante_apellidos");
  const solicitanteTelefono = telefono("solicitante_telefono");

  let contactos = [];
  const solicitanteElegido = lista("solicitante_id", [], {
    onchange: () => usarSolicitante() });

  async function cargarSolicitantes() {
    try {
      contactos = clientes.value
        ? await api.get(`/solicitantes?cliente_id=${clientes.value}`)
        : [];
    } catch { contactos = []; }

    solicitanteElegido.replaceChildren(
      h("option", { value: "" },
        contactos.length ? t("nuevo_solicitante")
                         : t("nuevo_solicitante_vacio")),
      ...contactos.map(c => h("option", { value: c.id },
        c.correo ? `${c.completo} · ${c.correo}` : c.completo)));
    solicitanteElegido.value = "";
    usarSolicitante();
  }

  function usarSolicitante(conservarCorreo = false) {
    const elegido = contactos.find(
      c => String(c.id) === solicitanteElegido.value);
    for (const [control, llave] of [[solicitante, "nombre"],
                                    [solicitanteApellidos, "apellidos"]]) {
      control.value = elegido ? (elegido[llave] || "") : "";
      control.readOnly = !!elegido;
      control.classList.toggle("fijo", !!elegido);
    }
    if (elegido) solicitanteTelefono.poner(elegido.telefono);
    else solicitanteTelefono.limpiar();
    solicitanteTelefono.bloquear(!!elegido);
    if (!conservarCorreo) {
      solicitanteCorreo.value = elegido ? (elegido.correo || "") : "";
    }
    revisar();
  }

  function reconocerPorCorreo() {
    const escrito = solicitanteCorreo.value.trim().toLowerCase();
    const encontrado = escrito
      ? contactos.find(c => (c.correo || "").toLowerCase() === escrito)
      : null;
    const ahora = encontrado ? String(encontrado.id) : "";
    if (ahora !== solicitanteElegido.value) {
      solicitanteElegido.value = ahora;
      usarSolicitante(true);
      if (encontrado) mensaje(`${encontrado.completo} ${t("ya_registrado")}`);
    }
    revisar();
  }

  /* ================================================ el ejecutivo */

  const ejecutivoNombre = entrada("ejecutivo_nombre", { oninput: () => revisar() });
  const ejecutivoApellidos = entrada("ejecutivo_apellidos");
  const ejecutivoCorreo = entrada("ejecutivo_correo", { type: "email" });
  const ejecutivoTelefono = telefono("ejecutivo_telefono");

  function clavesDeTelefono() {
    const pais = cat.paises.find(p => String(p.id) === String(paises.value));
    const clave = (pais && pais.lada) || "+52";
    solicitanteTelefono.clavePais(clave);
    ejecutivoTelefono.clavePais(clave);
  }

  /* ================================================ el trato */

  /* El implantado no lleva agenda: lleva un punto fijo al que el
     conductor se presenta todos los dias, el mismo meet and greet. */
  const punto = buscadorDeLugar({
    paisId: () => paises.value,
    alCambiar: () => revisar(),
    filas: "3",
  });

  /* Que dias corre el servicio. Va con el meet and greet porque es
     parte del trato —lo que se le dijo al cliente que iba a tener—, no
     de la facturacion. De aqui sale el color del calendario. */
  const DIAS_SERVICIO = DIAS_DE_SERVICIO();
  const diasServicio = lista("dias_servicio", DIAS_SERVICIO,
                             { onchange: () => {
                               pintarMes(); traerDisponibilidad();
                             } });

  const horaPresentacion = h("input", { type: "time", value: "08:00" });
  const zona = widgetZona({
    cat, paisId: () => paises.value, pin: () => punto.valor() });
  const cubre = h("textarea", { rows: "3", placeholder: t("imp_cubre_ej") });
  const noCubre = h("textarea", { rows: "3", placeholder: t("imp_no_cubre_ej") });
  const reportaNombre = entrada("reporta_a_nombre");
  const reportaApellidos = entrada("reporta_a_apellidos");
  const reportaTelefono = telefono("reporta_a_telefono");
  const reportaCorreo = entrada("reporta_a_correo", { type: "email" });
  const protocolo = h("textarea", { rows: "8",
                                    placeholder: t("imp_protocolo_ej") });

  /* ================================================ el mes */

  /* El servicio arranca el dia del meet and greet y corre hasta el
     ultimo dia del mes: ahi cae el corte y el mes siguiente entra limpio
     el dia 1. De esa fecha salen el anio, el mes y el dia de arranque;
     preguntar los tres por separado era preguntar lo mismo tres veces. */
  const fechaInicio = h("input", { type: "date",
                                   value: hoy.toISOString().slice(0, 10),
                                   onchange: () => {
                                     pintarMes(); traerDisponibilidad();
                                     revisar();
                                   } });


  /* El implantado es siempre dia completo: no hay implantado de medio
     dia ni de transfer. No se pregunta ni se muestra —ocupaba un
     recuadro para decir siempre lo mismo—, se toma del pais, que es
     donde vive la jornada: doce horas en Mexico no son las de Brasil.
     Si un pais no la tiene en su catalogo, el alta se traba. */
  let modalidadId = null;

  function repintarModalidades() {
    const suya = cat.modalidades.find(
      m => m.codigo === "full_day"
           && String(m.pais_id) === String(paises.value));
    modalidadId = suya ? suya.id : null;
    revisar();
  }


  /* ================================================ el calendario */

  /* Se pinta mientras se captura, antes de guardar nada: el consultor ve
     el mes que esta vendiendo. */
  const calendario = widgetCalendario();
  const pintarMes = () => calendario.pintar(fechaInicio.value,
                                            diasServicio.value);

  /* ================================================ precios */


  /* ================================================ la plantilla */

  /* La disponibilidad se pide una vez por ciudad, fecha y esquema de
     dias: son los tres datos que definen contra que mes se mide. */
  let libres = null;

  async function traerDisponibilidad() {
    libres = null;
    if (ciudadElegida() && fechaInicio.value) {
      const parametros = new URLSearchParams({
        plaza_id: ciudadElegida(), desde: fechaInicio.value,
        dias_servicio: diasServicio.value,
        hora: `${horaPresentacion.value || "08:00"}:00` });
      try {
        libres = await api.get(`/implantados/disponibilidad?${parametros}`);
      } catch (err) {
        libres = null;                 // sin mes, se ofrece el catalogo
      }
    }
    roster.repintar();
    revisar();
  }

  const roster = widgetPlantilla(cat, () => ciudadElegida(), () => revisar(),
                                 () => libres);
  const plantilla = () => roster.valor();
  const unidades = () => roster.unidades();
  const repintarPlantilla = () => roster.repintar();
  const agregarFila = () => roster.agregar();

  /* ================================================ que falta */

  const faltantes = h("ul", { clase: "minimo" });

  /* El alta va en dos pasos y cada uno tiene su minimo.

     Capturar el acuerdo de un implantado toma su tiempo —el alcance, la
     coordinacion, el protocolo— y perderlo porque la plantilla no
     cuadraba es la forma mas facil de que nadie quiera volver a
     capturar uno. Por eso en cuanto estan el cliente y el acuerdo se
     guardan, sale el folio, y la asignacion se arma despues, hoy o
     manana. */
  function faltaDelAcuerdo() {
    const falta = [];
    if (!clientes.value) falta.push(t("min_cliente"));
    if (!ciudadElegida()) falta.push(t("ciudad_opera"));
    if (!solicitante.value.trim()) falta.push(t("quien_solicita"));
    if (!ejecutivoNombre.value.trim()) falta.push(t("ejecutivo_principal"));
    if (!punto.direccion.value.trim()) falta.push(t("imp_falta_punto"));
    if (!fechaInicio.value) falta.push(t("imp_falta_fecha"));
    return falta;
  }

  function faltaDeLaAsignacion() {
    const falta = [];
    if (!modalidadId) falta.push(t("imp_falta_modalidad"));
    if (!plantilla().length) falta.push(t("imp_falta_plantilla"));
    return falta;
  }

  function revisar() {
    const delAcuerdo = faltaDelAcuerdo();
    const falta = [...delAcuerdo, ...faltaDeLaAsignacion()];

    verAsignacion();
    faltantes.replaceChildren(...falta.map(x => h("li", {}, x)));
    faltantes.hidden = !falta.length;
    botonAlta.disabled = !!falta.length;
    botonAcuerdo.disabled = !!delAcuerdo.length || !!servicioId;
    return falta;
  }

  /* El servicio, una vez guardado. Mientras sea nulo, el boton de abajo
     hace las dos cosas de un golpe. */
  let servicioId = null;

  const avisoAcuerdo = h("span", { clase: "gris chico" });
  const botonAcuerdo = h("button", { clase: "claro", type: "button",
    onclick: () => guardarAcuerdo() }, t("imp_guardar_acuerdo"));

  function cuerpoDelAcuerdo() {
    const lugar = punto.valor();
    return {
      cliente_id: Number(clientes.value),
      pais_id: Number(paises.value),
      plaza_id: Number(ciudadElegida()),
      consultor_id: consultores.value ? Number(consultores.value) : null,
      solicitante_id: solicitanteElegido.value
        ? Number(solicitanteElegido.value) : null,
      solicitante_nombre: solicitante.value.trim() || null,
      solicitante_apellidos: solicitanteApellidos.value.trim() || null,
      solicitante_correo: solicitanteCorreo.value.trim() || null,
      solicitante_telefono: solicitanteTelefono.valor(),
      ejecutivo_nombre: ejecutivoNombre.value.trim() || null,
      ejecutivo_apellidos: ejecutivoApellidos.value.trim() || null,
      ejecutivo_correo: ejecutivoCorreo.value.trim() || null,
      ejecutivo_telefono: ejecutivoTelefono.valor(),
      acuerdo: {
        cubre: cubre.value.trim() || null,
        no_cubre: noCubre.value.trim() || null,
        zona_operacion: zona.valor(),
        dias_semana: (DIAS_SERVICIO.find(
          d => d.valor === diasServicio.value) || {}).texto || null,
        fecha_inicio: fechaInicio.value || null,
        dias_servicio: diasServicio.value,
        origen_direccion: lugar.direccion || null,
        origen_lat: lugar.lat,
        origen_lon: lugar.lon,
        geocerca_metros: lugar.metros,
        reporta_a_nombre: reportaNombre.value.trim() || null,
        reporta_a_apellidos: reportaApellidos.value.trim() || null,
        reporta_a_telefono: reportaTelefono.valor(),
        reporta_a_correo: reportaCorreo.value.trim() || null,
        protocolo_contacto: protocolo.value.trim() || null,
      },
    };
  }

  function cuerpoDeLaAsignacion() {
    return {
      fecha_inicio: fechaInicio.value,
      dias_servicio: diasServicio.value,
      modalidad_id: modalidadId,
      hora_presentacion: `${horaPresentacion.value || "08:00"}:00`,
      esquema: "por_dia",
      personal: plantilla(),
      unidades: unidades(),
    };
  }

  async function guardarAcuerdo() {
    if (faltaDelAcuerdo().length || servicioId) return;
    botonAcuerdo.disabled = true;
    try {
      const r = await api.post("/implantados/servicio", cuerpoDelAcuerdo());
      servicioId = r.servicio_id;
      avisoAcuerdo.replaceChildren(h("b", {}, r.folio),
                                   ` · ${t("imp_acuerdo_guardado")}`);
      mensaje(`${r.folio}: ${t("imp_acuerdo_guardado")}`);
      revisar();
    } catch (err) {
      mensaje(err.message, "grave");
      botonAcuerdo.disabled = false;
    }
  }

  /* No se asigna gente a un servicio que todavia no se sabe que es.

     Primero el cliente y el acuerdo —a quien se cuida, donde se presenta
     el equipo, que dias, hasta donde llega el servicio— y despues a
     quien se le encarga. Al reves se arma una plantilla que puede no
     servir: la ciudad manda en quien esta disponible, y el punto fijo
     manda en la ciudad.

     Es un fieldset porque asi el navegador traba todo lo de adentro de
     una sola vez, sin recorrer campo por campo. */
  const camposAsignacion = h("fieldset", { clase: "grupo-campos" },
    roster.nodo,

    h("h4", { clase: "grupo" }, t("imp_calendario")),
    calendario.nodo);

  const avisoAsignacion = h("div", { clase: "bloqueo" });

  function verAsignacion() {
    const falta = faltaDelAcuerdo();
    camposAsignacion.disabled = !!falta.length;
    avisoAsignacion.hidden = !falta.length;
    if (falta.length) {
      avisoAsignacion.replaceChildren(
        h("b", {}, t("imp_bloqueo_asignacion")),
        h("ul", { clase: "minimo" }, ...falta.map(x => h("li", {}, x))));
    }
  }

  const botonAlta = h("button", { type: "submit" }, t("imp_dar_alta"));

  /* ================================================ guardar */

  async function guardar(evento) {
    evento.preventDefault();
    if (revisar().length) return;

    botonAlta.disabled = true;
    try {
      /* Si el acuerdo ya se guardo, aqui solo se abre el mes sobre el
         servicio que ya existe. Si no, van los dos de un golpe. */
      const r = servicioId
        ? await api.post(`/implantados/${servicioId}/mes`,
                         cuerpoDeLaAsignacion())
        : await api.post("/implantados", { ...cuerpoDelAcuerdo(),
                                           ...cuerpoDeLaAsignacion() });
      mensaje(`${r.folio}: ${r.jornadas_creadas || 0} ${t("imp_dias_armados")}`);
      if (!punto.conPin()) mensaje(t("pendiente_pin"), "alerta");
      location.hash = "#/implantados";
    } catch (err) {
      mensaje(err.message, "grave");
      botonAlta.disabled = false;
    }
  }

  /* ================================================ armado */

  const formulario = h("form", { onsubmit: guardar });

  formulario.append(
    h("div", { clase: "tarjeta" },
      h("h4", {}, t("cliente")),
      h("div", { clase: "rejilla tres" },
        campo(t("cliente"), clientes),
        campo(t("consultor_asignado"), consultores),
        campo(t("pais"), paises)),
      h("div", { clase: "rejilla tres" },
        h("div", { clase: "campo" },
          h("label", {}, t("ciudad_opera")), ciudades, cajaCiudad)),

      h("h4", { clase: "grupo" }, t("quien_solicita")),
      campo(t("elegir_solicitante"), solicitanteElegido),
      h("div", { clase: "rejilla cuatro" },
        campo(t("correo_campo"), solicitanteCorreo),
        campo(t("nombre"), solicitante),
        campo(t("apellido"), solicitanteApellidos),
        campo(t("telefono"), solicitanteTelefono)),

      h("h4", { clase: "grupo" }, t("ejecutivo_principal")),
      h("div", { clase: "rejilla cuatro" },
        campo(t("nombre"), ejecutivoNombre),
        campo(t("apellido"), ejecutivoApellidos),
        campo(t("correo_campo"), ejecutivoCorreo),
        campo(t("telefono"), ejecutivoTelefono))),

    h("div", { clase: "tarjeta" },
      h("h4", {}, t("imp_trato")),
      h("p", { clase: "gris chico", style: "margin:0 0 12px" },
        t("imp_trato_sub")),
      campo(t("imp_punto_fijo"), punto.direccion),
      punto.resultados,
      punto.cajaMapa,
      h("div", { clase: "rejilla tres" },
        campo(t("imp_lat"), punto.lat),
        campo(t("imp_lon"), punto.lon),
        campo(t("imp_geocerca"), punto.metros)),
      h("div", { clase: "rejilla tres" },
        campo(t("imp_fecha_inicio"), fechaInicio),
        campo(t("imp_dias_semana"), diasServicio),
        campo(t("imp_hora"), horaPresentacion)),
      campo(t("imp_zona"), zona.nodo),
      h("div", { clase: "rejilla dos" },
        campo(t("imp_cubre"), cubre),
        campo(t("imp_no_cubre"), noCubre)),
      h("h4", { clase: "grupo" }, t("imp_reporta")),
      h("div", { clase: "rejilla cuatro" },
        campo(t("nombre"), reportaNombre),
        campo(t("apellido"), reportaApellidos),
        campo(t("telefono"), reportaTelefono),
        campo(t("correo_campo"), reportaCorreo)),
      campo(t("imp_protocolo"), protocolo),
      h("div", { clase: "acciones", style: "margin-top:14px" },
        botonAcuerdo, avisoAcuerdo)),

    /* Quien cubre, con que unidad, como se cobra y como queda el mes.
       Era dos tarjetas y es una sola cosa: el consultor no arma una
       plantilla sin ver el calendario ni cotiza sin saber a quien
       asigno. */
    h("div", { clase: "tarjeta" },
      h("h4", {}, t("imp_asignacion")),
      h("p", { clase: "gris chico", style: "margin:0 0 12px" },
        t("imp_plantilla_sub")),
      avisoAsignacion,
      camposAsignacion),

    h("div", { clase: "tarjeta minimo-caja" },
      h("h4", {}, t("imp_falta")),
      faltantes),

    h("div", { clase: "acciones" }, botonAlta,
      h("button", { clase: "claro", type: "button",
        onclick: () => (location.hash = "#/implantados") }, t("cancelar"))));

  main.append(h("h1", {}, t("imp_alta_titulo")),
              h("p", { clase: "sub" }, t("imp_alta_sub")),
              formulario);

  repintarCiudades();
  repintarModalidades();
  clavesDeTelefono();
  zona.repintar();
  pintarMes();
  agregarFila();
  revisar();
  traerDisponibilidad();
}


/* ------------------------------------------------ el servicio por dentro */

/* Lo que se ve al entrar a un implantado: el acuerdo que se firmo y el
   mes como va.

   Un implantado guardado a medias es lo normal, no la excepcion: el
   consultor cierra el acuerdo con el cliente hoy y arma la plantilla
   cuando sabe quien esta libre. Por eso esta pantalla hace las dos
   cosas: muestra lo que ya hay y, si el mes no se ha abierto, lo abre
   desde aqui sin volver a capturar nada. */

function renglon(etiqueta_, valor) {
  if (!valor) return null;
  return h("div", { clase: "dato" },
    h("span", { clase: "gris chico" }, etiqueta_),
    h("div", {}, valor));
}

export async function pantallaImplantado(main, servicioId) {
  const [cartera, acuerdo, servicio, cat] = await Promise.all([
    api.get("/implantados"),
    api.get(`/implantados/${servicioId}/acuerdo`),
    api.get(`/servicios/${servicioId}`),
    catalogos(),
  ]);

  const ficha = cartera.find(x => String(x.servicio_id) === String(servicioId));
  if (!ficha) {
    main.append(h("div", { clase: "tarjeta" },
      h("div", { clase: "vacio" }, t("imp_no_existe"))));
    return;
  }

  /* ------------------------------------------------------ encabezado */

  main.append(
    h("div", { clase: "cabeza-servicio" },
      h("div", {},
        h("h1", { style: "margin:0" }, ficha.folio),
        h("p", { clase: "sub", style: "margin:4px 0 0" },
          [ficha.cliente, ficha.ciudad].filter(Boolean).join(" · "))),
      etiqueta(ficha.estatus, TONO_ESTATUS[ficha.estatus] || "")),
    h("div", { clase: "acciones", style: "margin:0 0 16px" },
      h("button", { clase: "claro chico", type: "button",
        onclick: () => (location.hash = "#/implantados") },
        t("imp_volver"))));

  /* --------------------------------------------------------- cliente */

  const consultor = cat.consultores.find(
    c => String(c.id) === String(servicio.consultor_id));

  main.append(h("div", { clase: "tarjeta" },
    h("h4", {}, t("cliente")),
    h("div", { clase: "rejilla tres" },
      renglon(t("cliente"), ficha.cliente),
      renglon(t("ciudad_opera"), ficha.ciudad),
      renglon(t("consultor_asignado"), consultor ? consultor.nombre : null)),
    h("div", { clase: "rejilla tres" },
      renglon(t("quien_solicita"), servicio.solicitante_completo),
      renglon(t("ejecutivo_principal"), servicio.ejecutivo_completo),
      renglon(t("telefono"), servicio.ejecutivo_telefono))));

  /* --------------------------------------------------------- acuerdo */

  const coordinacion = [acuerdo.reporta_a_nombre, acuerdo.reporta_a_apellidos]
    .filter(Boolean).join(" ");

  /* El acuerdo se corrige cuando el cliente pide algo nuevo o cambia de
     oficina, y eso pasa con el servicio ya corriendo: por eso se edita
     siempre, no solo mientras se captura. Lo que no se puede es que el
     conductor siga operando con una hoja que ya no dice la verdad. */
  const tarjetaAcuerdo = h("div", { clase: "tarjeta" });
  main.append(tarjetaAcuerdo);

  function verAcuerdo() {
    tarjetaAcuerdo.replaceChildren(
      h("div", { clase: "cabeza-servicio" },
        h("h4", { style: "margin:0" }, t("imp_trato")),
        h("button", { clase: "claro chico", type: "button",
          onclick: () => editarAcuerdo() }, t("imp_editar"))),
      h("div", { clase: "rejilla dos" },
        renglon(t("imp_punto_fijo"), acuerdo.origen_direccion),
        renglon(t("imp_zona"), acuerdo.zona_operacion)),
      arranque(servicioId, acuerdo),
      h("div", { clase: "rejilla dos" },
        renglon(t("imp_dias_semana"), acuerdo.dias_semana),
        renglon(t("ejecutivo_principal"), ficha.ejecutivo)),
      h("div", { clase: "rejilla dos" },
        renglon(t("imp_cubre"), acuerdo.cubre),
        renglon(t("imp_no_cubre"), acuerdo.no_cubre)),
      h("div", { clase: "rejilla tres" },
        renglon(t("imp_reporta"), coordinacion),
        renglon(t("telefono"), acuerdo.reporta_a_telefono),
        renglon(t("correo_campo"), acuerdo.reporta_a_correo)),
      renglon(t("imp_protocolo"), acuerdo.protocolo_contacto),
      /* El tabulador es parte del trato, no de la operacion del mes:
         por eso vive aqui y no en el panel de viaticos. Ahi se usa;
         aqui se acuerda. */
      bloqueTabulador(servicioId));
  }

  function editarAcuerdo() {
    const punto = buscadorDeLugar({
      paisId: () => servicio.pais_id,
      filas: "3",
      valores: { direccion: acuerdo.origen_direccion || "",
                 lat: acuerdo.origen_lat || "",
                 lon: acuerdo.origen_lon || "",
                 metros: acuerdo.geocerca_metros || 500 },
    });
    const zona = widgetZona({ cat, paisId: () => servicio.pais_id,
                              pin: () => punto.valor(),
                              valores: acuerdo.zona_operacion });

    const fecha = h("input", { type: "date",
                               value: acuerdo.fecha_inicio || "" });
    const dias = lista("dias_servicio", DIAS_DE_SERVICIO());
    if (acuerdo.dias_servicio) dias.value = acuerdo.dias_servicio;

    const cubre = h("textarea", { rows: "3" });
    cubre.value = acuerdo.cubre || "";
    const noCubre = h("textarea", { rows: "3" });
    noCubre.value = acuerdo.no_cubre || "";
    const protocolo = h("textarea", { rows: "6" });
    protocolo.value = acuerdo.protocolo_contacto || "";

    const reportaNombre = entrada("reporta_a_nombre",
                                  { value: acuerdo.reporta_a_nombre || "" });
    const reportaApellidos = entrada("reporta_a_apellidos",
                                     { value: acuerdo.reporta_a_apellidos || "" });
    const reportaCorreo = entrada("reporta_a_correo", { type: "email",
                                  value: acuerdo.reporta_a_correo || "" });
    const reportaTelefono = telefono("reporta_a_telefono");
    if (acuerdo.reporta_a_telefono) {
      reportaTelefono.poner(acuerdo.reporta_a_telefono);
    }

    const boton = h("button", { type: "button",
                                onclick: () => guardar() }, t("imp_guardar"));

    async function guardar() {
      const lugar = punto.valor();
      boton.disabled = true;
      try {
        await api.put(`/implantados/${servicioId}/acuerdo`, {
          cubre: cubre.value.trim() || null,
          no_cubre: noCubre.value.trim() || null,
          zona_operacion: zona.valor(),
          dias_semana: (DIAS_DE_SERVICIO().find(
            d => d.valor === dias.value) || {}).texto || null,
          fecha_inicio: fecha.value || null,
          dias_servicio: dias.value,
          origen_direccion: lugar.direccion || null,
          origen_lat: lugar.lat,
          origen_lon: lugar.lon,
          geocerca_metros: lugar.metros,
          reporta_a_nombre: reportaNombre.value.trim() || null,
          reporta_a_apellidos: reportaApellidos.value.trim() || null,
          reporta_a_telefono: reportaTelefono.valor(),
          reporta_a_correo: reportaCorreo.value.trim() || null,
          protocolo_contacto: protocolo.value.trim() || null,
        });
        mensaje(t("imp_acuerdo_corregido"));
        location.reload();
      } catch (err) {
        mensaje(err.message, "grave");
        boton.disabled = false;
      }
    }

    tarjetaAcuerdo.replaceChildren(
      h("div", { clase: "cabeza-servicio" },
        h("h4", { style: "margin:0" }, t("imp_trato")),
        h("button", { clase: "claro chico", type: "button",
          onclick: () => verAcuerdo() }, t("cancelar"))),
      campo(t("imp_punto_fijo"), punto.direccion),
      punto.resultados,
      punto.cajaMapa,
      h("div", { clase: "rejilla tres" },
        campo(t("imp_lat"), punto.lat),
        campo(t("imp_lon"), punto.lon),
        campo(t("imp_geocerca"), punto.metros)),
      h("div", { clase: "rejilla dos" },
        campo(t("imp_fecha_inicio"), fecha),
        campo(t("imp_dias_semana"), dias)),
      campo(t("imp_zona"), zona.nodo),
      h("div", { clase: "rejilla dos" },
        campo(t("imp_cubre"), cubre),
        campo(t("imp_no_cubre"), noCubre)),
      h("h4", { clase: "grupo" }, t("imp_reporta")),
      h("div", { clase: "rejilla cuatro" },
        campo(t("nombre"), reportaNombre),
        campo(t("apellido"), reportaApellidos),
        campo(t("telefono"), reportaTelefono),
        campo(t("correo_campo"), reportaCorreo)),
      campo(t("imp_protocolo"), protocolo),
      h("div", { clase: "acciones", style: "margin-top:14px" }, boton));
  }

  verAcuerdo();

  /* ------------------------------------------------------------ el mes */

  if (ficha.meses) {
    await pintarMesDelServicio(main, servicioId, ficha);
    // Los hospitales antes de la hoja: es lo que la hoja va a llevar, y
    // si la ciudad no tiene ninguno mas vale verlo antes de liberarla.
    main.append(bloqueHospitales(servicioId));
    // La hoja hasta abajo: es lo ultimo que se hace, cuando todo lo de
    // arriba ya quedo.
    main.append(bloqueHoja(servicioId, ficha.estatus));
  } else {
    armarPrimerMes(main, servicioId, acuerdo, servicio, cat);
  }
}

/* El dia de arranque.

   Si ya esta, se lee. Si no —los servicios que se capturaron antes de
   que este dato viviera en el acuerdo—, se pone aqui: sin el no se
   puede abrir ningun mes, y mandar al consultor a capturar el servicio
   otra vez por una fecha seria absurdo.

   El acuerdo se guarda completo, no solo la fecha: el servidor
   reescribe la ficha entera y lo que no se mande se borra. */
function arranque(servicioId, acuerdo) {
  if (acuerdo.fecha_inicio) {
    return h("div", { clase: "rejilla dos" },
      renglon(t("imp_fecha_inicio"), acuerdo.fecha_inicio));
  }

  const fecha = h("input", { type: "date" });
  const dias = lista("dias_servicio", DIAS_DE_SERVICIO());
  if (acuerdo.dias_servicio) dias.value = acuerdo.dias_servicio;

  const boton = h("button", { clase: "claro chico", type: "button",
    onclick: () => guardar() }, t("agregar"));

  async function guardar() {
    if (!fecha.value) return mensaje(t("imp_falta_fecha"), "alerta");
    boton.disabled = true;
    try {
      await api.put(`/implantados/${servicioId}/acuerdo`, {
        ...sinLlavesDeBase(acuerdo),
        fecha_inicio: fecha.value,
        dias_servicio: dias.value,
      });
      mensaje(t("imp_arranque_guardado"));
      location.reload();
    } catch (err) {
      mensaje(err.message, "grave");
      boton.disabled = false;
    }
  }

  return h("div", {},
    h("div", { clase: "bloqueo" }, h("b", {}, t("imp_sin_arranque"))),
    h("div", { clase: "rejilla tres" },
      campo(t("imp_fecha_inicio"), fecha),
      campo(t("imp_dias_semana"), dias),
      h("div", { clase: "campo" }, h("label", {}, "\u00a0"), boton)));
}

/* El acuerdo viene de la base con su id y su servicio_id; al devolverlo
   solo van los campos del trato. */
function sinLlavesDeBase(acuerdo) {
  const copia = { ...acuerdo };
  delete copia.id;
  delete copia.servicio_id;
  return copia;
}

/* El mes que ya existe: el calendario con quien cubre cada dia.

   El implantado es continuo, asi que casi siempre hay un mes corriendo y
   a veces el que sigue ya abierto. Arriba van las pestanas para saltar
   entre los meses abiertos —se entra por el que se esta operando, no por
   el ultimo que se abrio— y abajo el boton para abrir el que falta. */
async function pintarMesDelServicio(main, servicioId, ficha) {
  const tarjeta = h("div", { clase: "tarjeta" },
    h("h4", {}, t("imp_asignacion")));
  main.append(tarjeta);

  const periodos = ficha.periodos && ficha.periodos.length
    ? ficha.periodos
    : [periodoSuelto(ficha.ultimo_mes)].filter(Boolean);
  if (!periodos.length) {
    tarjeta.append(h("div", { clase: "vacio" }, t("imp_sin_meses")));
    return;
  }

  // Se entra por el mes de hoy si esta abierto; si no, por el ultimo.
  const hoy = new Date();
  let actual = periodos.find(p => p.anio === hoy.getFullYear()
                                  && p.mes === hoy.getMonth() + 1)
               || periodos[periodos.length - 1];

  const pestanas = h("div", { clase: "acciones", style: "margin:0 0 14px" });
  const cuerpo = h("div", {});
  tarjeta.append(
    h("div", { clase: "rejilla tres" },
      renglon(t("col_titular"), ficha.titular),
      renglon(t("col_unidad"), ficha.unidad),
      renglon(t("col_ultimo_mes"), ficha.ultimo_mes)),
    periodos.length > 1 ? pestanas : null,
    cuerpo);

  function pintarPestanas() {
    pestanas.replaceChildren(...periodos.map(p => h("button", {
      type: "button",
      clase: p === actual ? "chico" : "claro chico",
      onclick: () => { actual = p; pintarPestanas(); pintar(); },
    }, p.periodo)));
  }

  async function pintar() {
    cuerpo.replaceChildren(h("div", { clase: "vacio" }, t("imp_cargando")));
    let datos;
    try {
      datos = await api.get(
        `/implantados/${servicioId}/calendario/${actual.anio}/${actual.mes}`);
    } catch (err) {
      cuerpo.replaceChildren(h("div", { clase: "vacio" }, err.message));
      return;
    }

    const cubiertos = {};
    for (const dia of datos.dias) {
      if (dia.cubre) cubiertos[dia.fecha] = dia.cubre;
    }

    const fichaDia = h("div", { clase: "ficha-dia" });
    const calendario = widgetCalendario(
      (fecha) => fichaDelDia(servicioId, fecha, fichaDia));
    const primero = datos.dias.find(d => d.estado !== "sin_servicio");
    calendario.pintar(primero ? primero.fecha : datos.dias[0].fecha,
                      datos.dias_servicio, cubiertos);

    const porCubrir = datos.dias.filter(d => d.estado === "por_cubrir");
    // Los viaticos van antes del calendario: el consultor decide el
    // dinero del mes mirando a su gente, no dia por dia.
    const caja = h("div");
    pintarViaticos(caja, servicioId, actual.anio, actual.mes);
    cuerpo.replaceChildren(
      porCubrir.length
        ? h("div", { clase: "bloqueo", style: "margin:0 0 14px" },
            h("b", {}, `${porCubrir.length} ${t("imp_por_cubrir_aviso")}`))
        : h("div", {}),
      caja,
      calendario.nodo,
      bloqueTaller(servicioId, actual, () => pintar()),
      fichaDia,
      abrirSiguiente(servicioId, ficha.siguiente, periodos, (nuevo) => {
        periodos.push(nuevo);
        actual = nuevo;
        pintarPestanas();
        pintar();
      }));
  }

  pintarPestanas();
  await pintar();
}

function periodoSuelto(texto) {
  if (!texto) return null;
  const [mes, anio] = texto.split("/");
  return { anio: Number(anio), mes: Number(mes), periodo: texto };
}

/* El boton de abrir el mes que sigue.

   El implantado no se vuelve a capturar: el mes nuevo nace con los
   mismos terminos y la misma plantilla. El proceso de la manana lo abre
   solo cuando se acaba el mes; esto es para adelantarse.

   Cuando no se puede, el boton se queda apagado *con la razon al lado*:
   el tope es un mes por delante del que se opera. */
function abrirSiguiente(servicioId, estado, periodos, alAbrir) {
  // Ya se abrio en esta misma pantalla: el estado que trajo la cartera
  // hablaba del mes anterior.
  const ultimo = periodos[periodos.length - 1];
  const abierto = estado && estado.periodo === ultimo.periodo;
  const sePuede = !!(estado && estado.se_puede) && !abierto;

  const razon = h("span", { clase: "gris chico" },
    sePuede ? "" : (abierto ? t("imp_mes_tope")
                            : (estado && estado.razon) || ""));
  const boton = h("button", { type: "button", clase: "claro",
    onclick: () => abrir() },
    `${t("imp_mes_siguiente")}${estado && estado.periodo && sePuede
        ? ` (${estado.periodo})` : ""}`);
  boton.disabled = !sePuede;

  async function abrir() {
    boton.disabled = true;
    try {
      const r = await api.post(`/implantados/${servicioId}/mes-siguiente`, {});
      mensaje(`${r.periodo} ${t("imp_mes_abierto")}: `
              + `${r.jornadas_creadas || 0} ${t("imp_dias_armados")}`);
      const [mes, anio] = r.periodo.split("/");
      alAbrir({ anio: Number(anio), mes: Number(mes), periodo: r.periodo });
    } catch (err) {
      mensaje(err.message, "grave");
      boton.disabled = false;
    }
  }

  return h("div", { clase: "acciones", style: "margin-top:16px" },
           boton, razon);
}

/* El task sheet, al final de la pantalla.

   Un PDF por idioma, siempre los tres: la hoja la lee el ejecutivo y el
   idioma es el que el prefiera, no el de quien opera la consola. Ver es
   otra cosa —eso lo lee el consultor— y sale en el idioma en que tenga
   puesta la suya. */
function bloqueHoja(servicioId, estatus) {
  const liberar = h("button", { type: "button",
    onclick: () => soltar() }, t("imp_liberar"));
  /* Lo que falta para poder liberar, con los dias por su nombre: decir
     "faltan 3 dias" y dejar al consultor buscandolos en el calendario
     es la mitad del trabajo. */
  const traba = h("div", { clase: "bloqueo", hidden: true,
                           style: "margin-bottom:10px" });

  async function soltar() {
    liberar.disabled = true;
    traba.hidden = true;
    try {
      const r = await api.post(
        `/task-sheets/implantado/${servicioId}/liberar`);
      mensaje(`${r.folio}: ${t("imp_liberada")} ${r.version} · ${r.estatus}`);
      location.reload();
    } catch (err) {
      const d = err.detalle || {};
      traba.replaceChildren(
        h("b", {}, err.message),
        d.que_hacer ? h("div", { clase: "chico" }, d.que_hacer) : null,
        d.dias && d.dias.length
          ? h("div", { clase: "chico ambar" }, d.dias.join(" · "))
          : null);
      traba.hidden = false;
      mensaje(err.message, "grave");
      liberar.disabled = false;
    }
  }

  return h("div", { clase: "tarjeta" },
    h("h4", {}, t("ts_titulo")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      t("imp_ts_nota")),
    /* Liberar la hoja es decir que el servicio ya esta armado: ahi pasa
       a asignado. Antes de eso se puede ver, pero no se ha entregado. */
    traba,
    h("div", { clase: "acciones", style: "margin-bottom:10px" }, liberar),
    h("div", { clase: "acciones" },
      ...IDIOMAS.map(i => h("button", {
        title: `${t("ts_pdf")} · ${i.nombre}`,
        onclick: () => abrirHoja(servicioId, i.codigo, true) },
        `${i.bandera} ${t("ts_pdf")} · ${i.nombre}`))),
    h("div", { clase: "acciones", style: "margin-top:8px" },
      h("button", { clase: "claro chico",
        onclick: () => abrirHoja(servicioId, idioma()) }, t("ts_ver"))));
}

/* Se abre en otra pestaña y, si se pide, se manda a imprimir: ahi se
   elige "Guardar como PDF". La hoja ya esta diseñada para imprimirse, y
   lo que el ejecutivo recibe es exactamente lo que se ve en pantalla.

   Se pide con la sesion puesta y se escribe en la pestaña nueva. Abrirla
   por su direccion no funciona —el navegador no lleva el token— y
   ponerlo en la direccion tampoco es opcion: se quedaria en el historial
   y en cualquier bitacora por donde pase. */
async function abrirHoja(servicioId, lengua, imprimir = false) {
  const w = window.open("", "_blank");
  if (!w) return mensaje(t("imp_ventana_bloqueada"), "alerta");
  w.document.write('<p style="font:14px system-ui;padding:20px">'
                   + `${t("imp_cargando")}</p>`);
  try {
    const html = await api.get(
      `/task-sheets/implantado/${servicioId}/hoja?idioma=${lengua}`,
      { crudo: true });
    w.document.open();
    w.document.write(html);
    w.document.close();
    if (imprimir) setTimeout(() => w.print(), 500);
  } catch (err) {
    w.close();
    mensaje(err.message, "grave");
  }
}

/* La ficha de un dia.

   Un implantado se opera de lunes a viernes y lo que de verdad cuesta
   trabajo son los bordes: el sabado que el cliente pide de mas y el fin
   de semana contratado que nadie ha cubierto. Los dos se resuelven
   picando el dia.

   La plantilla no crece aqui: el dia se cubre con las mismas posiciones
   del mes, con su gente o con un relevo en su lugar. Si el cliente
   quiere personal adicional eso es otro servicio —un eventual, con su
   folio y su hoja—. */
async function fichaDelDia(servicioId, fecha, caja) {
  caja.replaceChildren(h("div", { clase: "gris chico" }, t("imp_cargando")));

  let dia;
  try {
    dia = await api.get(`/implantados/${servicioId}/dia/${fecha}`);
  } catch (err) {
    caja.replaceChildren(h("div", { clase: "bloqueo" }, err.message));
    return;
  }

  const lengua = idioma();
  const comoSeLee = new Intl.DateTimeFormat(lengua, {
    weekday: "long", day: "numeric", month: "long" })
    .format(new Date(`${fecha}T12:00:00`));

  const TITULOS = {
    sin_servicio: t("imp_dia_sin_servicio"),
    por_cubrir: t("imp_dia_por_cubrir"),
    cubierto: t("imp_dia_cubierto"),
  };

  /* Quien puede cubrir cada posicion. Los ocupados se ven, pero no se
     eligen: saber que Ernesto no puede es tan util como saber que Luis
     si, y esconderlo lleva a preguntar por telefono. */
  function candidatos(porOmision) {
    return [...dia.candidatos].map(c => h("option", {
      value: c.persona_id,
      disabled: c.ocupado ? "" : null,
      selected: String(c.persona_id) === String(porOmision) ? "" : null,
    }, c.nombre
       + (c.del_equipo ? ` · ${t("imp_del_equipo")}` : "")
       + (c.ocupado ? ` · ${t("imp_ocupado")}` : "")));
  }

  const filas = dia.posiciones.map(posicion => {
    const quien = h("select", {});
    quien.append(...candidatos(posicion.persona_id));
    return { posicion, quien,
      nodo: h("tr", {},
        h("td", {}, posicion.rol || "—",
          posicion.placa
            ? h("div", { clase: "gris chico" }, posicion.placa) : null),
        h("td", {}, quien)) };
  });

  const ambos = h("input", { type: "checkbox", checked: "" });
  const boton = h("button", { type: "button", onclick: () => cubrir() },
    dia.estado === "sin_servicio" ? t("imp_abrir_dia") : t("imp_cubrir_dia"));
  const cerrar = h("button", { clase: "claro", type: "button",
    onclick: () => cerrarDia() }, t("imp_cerrar_dia"));

  async function cubrir() {
    boton.disabled = true;
    try {
      await api.post(`/implantados/${servicioId}/dia/${fecha}/cubrir`, {
        personal: filas.map(f => ({
          persona_id: Number(f.quien.value),
          vehiculo_id: f.posicion.vehiculo_id || null })),
        ambos_dias: ambos.checked,
      });
      mensaje(t("imp_dia_guardado"));
      location.reload();
    } catch (err) {
      mensaje(err.message, "grave");
      boton.disabled = false;
    }
  }

  async function cerrarDia() {
    cerrar.disabled = true;
    try {
      await api.borrar(`/implantados/${servicioId}/dia/${fecha}`);
      mensaje(t("imp_dia_cerrado"));
      location.reload();
    } catch (err) {
      mensaje(err.message, "grave");
      cerrar.disabled = false;
    }
  }

  caja.replaceChildren(
    h("div", { clase: "cabeza-servicio" },
      h("div", {},
        h("b", { style: "text-transform:capitalize" }, comoSeLee),
        h("div", { clase: "gris chico" }, TITULOS[dia.estado] || "")),
      h("button", { clase: "claro chico", type: "button",
        onclick: () => caja.replaceChildren() }, t("cancelar"))),

    filas.length
      ? h("table", { clase: "lista" },
          h("thead", {}, h("tr", {},
            h("th", {}, t("imp_col_posicion")),
            h("th", {}, t("imp_col_cubre")))),
          h("tbody", {}, ...filas.map(f => f.nodo)))
      : h("div", { clase: "vacio" }, t("imp_sin_plantilla")),

    dia.otro_dia_del_fin
      ? h("label", { clase: "casilla", style: "margin-top:10px" }, ambos,
          h("span", {}, `${t("imp_todo_el_fin")} ${dia.otro_dia_del_fin}`))
      : null,

    h("div", { clase: "acciones", style: "margin-top:14px" },
      filas.length ? boton : null,
      dia.se_puede_cerrar ? cerrar : null));
}

/* El mes que no existe todavia: se arma aqui, con lo que ya dice el
   acuerdo. La fecha y los dias no se vuelven a preguntar. */
function armarPrimerMes(main, servicioId, acuerdo, servicio, cat) {
  let libres = null;
  const roster = widgetPlantilla(cat, () => servicio.plaza_id,
                                 () => revisar(), () => libres);

  (async () => {
    if (!acuerdo.fecha_inicio) return;
    const parametros = new URLSearchParams({
      plaza_id: servicio.plaza_id, desde: acuerdo.fecha_inicio,
      dias_servicio: acuerdo.dias_servicio || "lunes_viernes" });
    try {
      libres = await api.get(`/implantados/disponibilidad?${parametros}`);
      roster.repintar();
    } catch (err) { /* sin mes que medir: se ofrece el catalogo */ }
  })();
  const calendario = widgetCalendario();

  const faltantes = h("ul", { clase: "minimo" });
  /* El error se dice aqui abajo, junto al boton. Arriba de la pantalla
     tambien sale, pero quien acaba de picar el boton esta mirando el
     boton, no el encabezado. */
  const error = h("div", { clase: "bloqueo", hidden: true });
  const boton = h("button", { type: "button", onclick: () => abrir() },
                  t("imp_abrir_mes"));

  function revisar() {
    const falta = [];
    if (!acuerdo.fecha_inicio) falta.push(t("imp_falta_fecha"));
    if (!roster.valor().length) falta.push(t("imp_falta_plantilla"));
    if (!modalidadDelPais(cat, servicio.pais_id)) {
      falta.push(t("imp_sin_modalidad"));
    }
    faltantes.replaceChildren(...falta.map(x => h("li", {}, x)));
    faltantes.hidden = !falta.length;
    boton.disabled = !!falta.length;
    return falta;
  }

  function decir(texto, tono = "grave") {
    error.hidden = !texto;
    error.replaceChildren(texto || "");
    if (texto) mensaje(texto, tono);
  }

  async function abrir() {
    if (revisar().length) return;
    boton.disabled = true;
    decir("");
    try {
      const r = await api.post(`/implantados/${servicioId}/mes`, {
        personal: roster.valor(),
        unidades: roster.unidades(),
        modalidad_id: modalidadDelPais(cat, servicio.pais_id),
        esquema: "por_dia",
      });
      mensaje(`${r.folio}: ${r.jornadas_creadas || 0} ${t("imp_dias_armados")}`);
      location.hash = "#/implantados";
    } catch (err) {
      decir(err.message);
      boton.disabled = false;
    }
  }

  main.append(h("div", { clase: "tarjeta" },
    h("h4", {}, t("imp_asignacion")),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("imp_plantilla_sub")),
    roster.nodo,
    h("h4", { clase: "grupo" }, t("imp_calendario")),
    calendario.nodo,
    h("div", { clase: "minimo-caja", style: "margin-top:14px" },
      h("h4", {}, t("imp_falta")), faltantes),
    error,
    h("div", { clase: "acciones", style: "margin-top:14px" }, boton)));

  calendario.pintar(acuerdo.fecha_inicio, acuerdo.dias_servicio);
  roster.agregar();
  revisar();
}

/* El implantado es siempre dia completo, y la jornada es del pais. */
function modalidadDelPais(cat, paisId) {
  const suya = cat.modalidades.find(
    x => x.codigo === "full_day" && String(x.pais_id) === String(paisId));
  return suya ? suya.id : null;
}


/* ------------------------------------------------ viaticos del mes

   Mismo trato que en eventual —un renglon por persona, un solo monto,
   el semaforo del deposito— con una diferencia: aqui todo va amarrado
   al mes que se esta mirando. El implantado corre sin fin, pero el
   dinero se deposita, se comprueba y se cierra mes con mes, igual que
   se factura. Por eso cada llamada lleva su anio y su mes. */

const SEMAFORO_VIATICO = {
  por_asignar: { clave: "imp_vi_por_asignar", tono: "" },
  asignado: { clave: "imp_vi_asignado", tono: "info" },
  solicitado: { clave: "imp_vi_solicitado", tono: "alerta" },
  depositado: { clave: "imp_vi_ya_depositado", tono: "ok" },
};

async function pintarViaticos(caja, servicioId, anio, mes) {
  /* Puerta propia del implantado: el corte es mensual y no se comparte
     con el eventual, que deposita una vez por todo el servicio. */
  const ruta = `/implantados/${servicioId}/viaticos/${anio}/${mes}`;
  let datos;
  try {
    datos = await api.get(ruta);
  } catch (err) {
    return caja.replaceChildren(h("div", { clase: "bloqueo" }, err.message));
  }
  // Sin gente en el mes no hay a quien depositarle.
  if (!datos.personal.length) return caja.replaceChildren();

  const moneda = datos.moneda || "MXN";
  const repintar = () => pintarViaticos(caja, servicioId, anio, mes);

  const cuerpo = h("tbody");
  for (const p of datos.personal) {
    cuerpo.append(renglonViatico(p, servicioId, anio, mes, moneda, repintar));
  }

  const porSolicitar = datos.personal.filter(
    p => p.estatus === "asignado").length;
  const pedir = h("button", { clase: "chico", type: "button",
    onclick: (e) => solicitar(e) },
    porSolicitar ? `${t("imp_vi_solicitar")} (${porSolicitar})`
                 : t("imp_vi_solicitar"));
  pedir.disabled = !porSolicitar;

  async function solicitar(e) {
    e.target.disabled = true;
    try {
      await api.post(
        `/implantados/${servicioId}/viaticos/${anio}/${mes}/solicitar`, {});
      mensaje(t("imp_vi_pedido"));
      await repintar();
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  }

  caja.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" },
    h("h4", { style: "margin:0 0 2px" },
      `${t("imp_viaticos")} · ${datos.periodo || ""}`),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("imp_viaticos_sub")),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, t("imp_vi_persona")),
        h("th", { style: "text-align:right" }, t("imp_vi_propone")),
        h("th", { style: "text-align:right" }, t("imp_vi_deposita")),
        h("th", {}, t("imp_vi_estado")))),
      cuerpo),
    h("div", { clase: "acciones", style: "margin-top:10px" },
      pedir,
      h("span", { clase: "chico" },
        h("b", {}, `${t("imp_vi_total")} ${dinero(datos.total_asignado, moneda)}`),
        Number(datos.total_depositado) > 0
          ? h("span", { clase: "verde" },
              ` · ${t("imp_vi_depositado")} `
              + dinero(datos.total_depositado, moneda))
          : "",
        Number(datos.total_en_camino) > 0
          ? h("span", { clase: "ambar" },
              ` · ${t("imp_vi_con_finanzas")} `
              + dinero(datos.total_en_camino, moneda))
          : "",
        Number(datos.total_por_solicitar) > 0
          ? h("span", { clase: "gris" },
              ` · ${t("imp_vi_por_solicitar")} `
              + dinero(datos.total_por_solicitar, moneda))
          : ""))));
}

function renglonViatico(p, servicioId, anio, mes, moneda, repintar) {
  const est = SEMAFORO_VIATICO[p.estatus] || SEMAFORO_VIATICO.por_asignar;
  /* Lo que ya salio no se reescribe: cuando hay dinero con finanzas o
     con la persona, el campo deja de ser "cuanto se le deposita" y pasa
     a ser "cuanto mas". */
  const yaSalio = Number(p.depositado) > 0 || Number(p.en_camino) > 0;
  const destino = yaSalio ? "persona/agregar" : "persona";

  const monto = entrada("monto", {
    type: "number", step: "1", min: "0", clase: "num",
    style: "text-align:right; max-width:130px",
    value: !yaSalio && Number(p.asignado)
             ? String(Math.round(Number(p.asignado))) : "",
    placeholder: yaSalio ? t("imp_vi_mas") : "",
  });

  const guardar = h("button", { clase: "claro chico", type: "button",
    onclick: (e) => fijar(e) }, t("imp_vi_guardar"));

  async function fijar(e) {
    const valor = Number(monto.value);
    if (!valor) return;
    e.target.disabled = true;
    try {
      await api.post(
        `/implantados/${servicioId}/viaticos/${anio}/${mes}/${destino}`,
        { persona_id: p.persona_id, monto: valor });
      await repintar();
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  }

  /* Mientras el dinero no salga, el consultor puede echarse para atras:
     se pide el deposito y despues cambia la gente o el monto. */
  const cancelar = Number(p.en_camino) > 0
    ? h("button", { clase: "claro chico", type: "button",
        onclick: async (e) => {
          e.target.disabled = true;
          try {
            await api.post(
              `/implantados/${servicioId}/viaticos/${anio}/${mes}/cancelar`,
              { persona_id: p.persona_id });
            await repintar();
          } catch (err) {
            mensaje(err.message, "grave");
            e.target.disabled = false;
          }
        } }, t("imp_vi_cancelar"))
    : null;

  return h("tr", {},
    h("td", {},
      h("div", {}, p.nombre),
      h("div", { clase: "gris chico" },
        `${p.puesto || ""} · ${p.dias} ${t("imp_vi_dias")}`)),
    h("td", { clase: "num", style: "text-align:right" },
      dinero(p.propuesto, moneda)),
    h("td", { style: "text-align:right" },
      h("div", { clase: "acciones", style: "justify-content:flex-end" },
        monto, guardar),
      yaSalio
        ? h("div", { clase: "gris chico" },
            `${dinero(p.asignado, moneda)} ${t("imp_vi_total").toLowerCase()}`)
        : null),
    h("td", {},
      etiqueta(t(est.clave), est.tono),
      cancelar ? h("div", { style: "margin-top:6px" }, cancelar) : null));
}


/* ------------------------------------------------------ el taller

   Una unidad que se queda en el camino no es un tramite: es el servicio
   de manana. Por eso el bloqueo y el cambio son un solo boton —la
   unidad sale de circulacion para toda la empresa y otra toma su lugar
   en los dias del tramo—, y las unidades que entran salen medidas
   contra esos dias, no contra el catalogo.

   El dato normalmente llega de Odoo, que es donde vive el mantenimiento
   de la flota. Esto es para cuando hay que resolverlo aqui y ahora. */

function bloqueTaller(servicioId, periodo, alGuardar) {
  const caja = h("div", { hidden: true, style: "margin-top:14px" });
  const abrir = h("button", { clase: "claro chico", type: "button",
    onclick: () => alternar() }, t("imp_taller_abrir"));

  const fuera = h("div", { clase: "gris chico", style: "margin-top:8px" });
  (async () => {
    try {
      const filas = await api.get(`/implantados/${servicioId}/taller`);
      const hoy = filas.filter(x => x.hoy_fuera);
      if (!hoy.length) return;
      fuera.replaceChildren(...hoy.map(x => h("div", {},
        etiqueta(`${t("imp_taller_fuera")}: ${x.placa}`, "alerta"),
        h("span", { clase: "chico" },
          ` ${x.desde} → ${x.hasta || t("imp_taller_sin_fecha")}`
          + (x.taller ? ` · ${x.taller}` : "")))));
    } catch (err) { /* sin taller que mostrar */ }
  })();

  function alternar() {
    caja.hidden = !caja.hidden;
    if (!caja.hidden) pintarFormulario();
  }

  async function pintarFormulario() {
    const hoy = new Date().toISOString().slice(0, 10);
    const primero = `${periodo.anio}-${String(periodo.mes).padStart(2, "0")}-01`;
    const desde = h("input", { type: "date",
      value: hoy > primero ? hoy : primero });
    const hasta = h("input", { type: "date" });
    const tipo = lista("tipo", [
      { valor: "mantenimiento_correctivo", texto: t("imp_taller_correctivo") },
      { valor: "mantenimiento_preventivo", texto: t("imp_taller_preventivo") },
    ]);
    const categoria = lista("categoria", []);
    const entra = lista("entra", []);
    const taller = entrada("taller");
    const folio = entrada("folio");
    const nota = entrada("nota");
    const error = h("div", { clase: "bloqueo", hidden: true });

    let flota = [];
    let diasDelTramo = 0;

    /* Las unidades se miden contra los dias del tramo: una libre hoy
       que trae otro servicio el jueves no sirve para un tramo que
       llega al viernes. Se vuelve a preguntar cada vez que se mueve
       una fecha. */
    async function medir() {
      if (!desde.value) return;
      const p = new URLSearchParams({ desde: desde.value });
      if (hasta.value) p.set("hasta", hasta.value);
      try {
        const r = await api.get(
          `/implantados/${servicioId}/unidades-libres?${p}`);
        flota = r.vehiculos;
        diasDelTramo = r.dias;
        pintarCategorias();
      } catch (err) {
        flota = [];
        entra.replaceChildren();
        decir(err.message);
      }
    }

    function pintarCategorias() {
      decir("");
      const vistas = new Map();
      for (const v of flota) {
        if (!vistas.has(v.categoria_id)) {
          vistas.set(v.categoria_id, v.categoria || "");
        }
      }
      const antes = categoria.value;
      categoria.replaceChildren(...[...vistas].map(([id, nombre]) =>
        h("option", { value: id }, nombre)));
      if (antes) categoria.value = antes;
      pintarUnidades();
    }

    function pintarUnidades() {
      const suyas = flota.filter(
        v => String(v.categoria_id) === String(categoria.value));
      entra.replaceChildren(...suyas.map(v => h("option", { value: v.vehiculo_id },
        `${v.placa} · ${v.marca_modelo || ""} — ${v.libres} `
        + `${t("imp_taller_de")} ${diasDelTramo} ${t("imp_taller_libre")}`)));
    }

    // Cambiar de categoria solo reordena lo que ya se midio; cambiar
    // una fecha si obliga a volver a medir, porque el tramo es otro.
    categoria.addEventListener("change", () => pintarUnidades());
    desde.addEventListener("change", () => medir());
    hasta.addEventListener("change", () => medir());

    function decir(texto) {
      error.hidden = !texto;
      error.replaceChildren(texto || "");
    }

    const guardar = h("button", { type: "button",
      onclick: () => mandar() }, t("imp_taller_guardar"));

    async function mandar() {
      if (!entra.value) return decir(t("imp_taller_falta"));
      guardar.disabled = true;
      decir("");
      try {
        const r = await api.post(`/implantados/${servicioId}/taller`, {
          desde: desde.value,
          hasta: hasta.value || null,
          tipo: tipo.value,
          entra_id: Number(entra.value),
          taller: taller.value || null,
          folio: folio.value || null,
          nota: nota.value || null,
        });
        mensaje(`${r.taller.placa} ${t("imp_taller_hecho")} ${r.entra} `
                + `(${r.dias_cambiados})`);
        caja.hidden = true;
        alGuardar();
      } catch (err) {
        decir(err.message);
        guardar.disabled = false;
      }
    }

    caja.replaceChildren(h("div", { clase: "tarjeta lisa" },
      h("h4", { style: "margin:0 0 2px" }, t("imp_taller")),
      h("p", { clase: "gris chico", style: "margin:0 0 12px" },
        t("imp_taller_sub")),
      h("div", { clase: "rejilla tres" },
        campo(t("imp_taller_desde"), desde),
        campo(t("imp_taller_hasta"), hasta),
        campo(t("imp_taller_tipo"), tipo)),
      h("div", { clase: "rejilla dos" },
        campo(t("col_unidad"), categoria),
        campo(t("imp_taller_entra"), entra)),
      h("div", { clase: "rejilla tres" },
        campo(t("imp_taller_donde"), taller),
        campo(t("imp_taller_folio"), folio),
        campo(t("imp_taller_nota"), nota)),
      error,
      h("div", { clase: "acciones", style: "margin-top:10px" },
        guardar,
        h("button", { clase: "claro chico", type: "button",
          onclick: () => { caja.hidden = true; } }, t("imp_taller_cerrar")))));

    await medir();
  }

  return h("div", {},
    h("div", { clase: "acciones", style: "margin-top:14px" }, abrir),
    fuera, caja);
}


/* ------------------------------------------------- los hospitales

   En una emergencia nadie va a buscar un hospital en el telefono: lo
   lee de la hoja. Por eso los tres que la hoja va a llevar se ven aqui
   antes de liberarla, y por eso la ciudad sin hospitales cargados lo
   dice en rojo en vez de salir en blanco.

   Google llena el nombre oficial, la direccion, el telefono y las
   coordenadas —los cuatro datos que no se pueden escribir a mano ni
   recordar mal—. El nivel de atencion no: eso lo marca Centauro una
   sola vez al darlo de alta, porque de ese nivel sale la regla que
   garantiza un quirofano y no es algo que se adivine. */

const NIVELES_HOSPITAL = () => [
  { valor: "", texto: "—" },
  { valor: "tercer_nivel", texto: t("imp_hosp_tercero") },
  { valor: "segundo_nivel", texto: t("imp_hosp_segundo") },
  { valor: "primer_nivel", texto: t("imp_hosp_primero") },
];

function bloqueHospitales(servicioId) {
  const lista_ = h("div");
  const hallazgos = h("div", { style: "margin-top:12px" });
  const buscar = h("button", { clase: "claro chico", type: "button",
    onclick: () => enGoogle() }, t("imp_hosp_buscar"));
  let punto = null;

  async function cargar() {
    lista_.replaceChildren(h("div", { clase: "gris chico" }, t("imp_cargando")));
    let datos;
    try {
      datos = await api.get(`/implantados/${servicioId}/hospitales`);
    } catch (err) {
      return lista_.replaceChildren(h("div", { clase: "bloqueo" }, err.message));
    }
    punto = datos;
    buscar.disabled = datos.lat === null || datos.lon === null;

    if (!datos.hospitales.length) {
      return lista_.replaceChildren(h("div", { clase: "bloqueo" },
        h("b", {}, buscar.disabled ? t("imp_hosp_sin_punto")
                                   : t("imp_hosp_vacio"))));
    }
    lista_.replaceChildren(h("table", {},
      h("tbody", {}, ...datos.hospitales.map(x => h("tr", {},
        h("td", {},
          h("div", {}, x.nombre),
          h("div", { clase: "gris chico" }, x.direccion || "")),
        h("td", { clase: "chico" }, x.telefono || "—"),
        h("td", { clase: "num chico", style: "text-align:right" },
          `${x.km} km`),
        h("td", {}, etiqueta(nombreDelNivel(x.nivel),
                             x.nivel === "tercer_nivel" ? "ok" : "alerta")))))));
  }

  function nombreDelNivel(nivel) {
    if (nivel === "tercer_nivel") return t("imp_hosp_tercero");
    if (nivel === "segundo_nivel") return t("imp_hosp_segundo");
    if (nivel === "primer_nivel") return t("imp_hosp_primero");
    return "—";
  }

  async function enGoogle() {
    if (!punto || punto.lat === null) return;
    buscar.disabled = true;
    hallazgos.replaceChildren(h("div", { clase: "gris chico" }, t("imp_cargando")));
    let datos;
    try {
      const p = new URLSearchParams({
        lat: punto.lat, lon: punto.lon,
        pais_id: punto.pais_id, plaza_id: punto.plaza_id });
      datos = await api.get(`/mapas/hospitales?${p}`);
    } catch (err) {
      buscar.disabled = false;
      return hallazgos.replaceChildren(
        h("div", { clase: "bloqueo" }, err.message));
    }
    buscar.disabled = false;
    hallazgos.replaceChildren(
      h("p", { clase: "gris chico", style: "margin:0 0 8px" },
        t("imp_hosp_nota")),
      ...datos.hospitales.map(x => fichaDeHospital(x)));
  }

  function fichaDeHospital(x) {
    if (x.en_catalogo_id) {
      return h("div", { clase: "punto", style: "margin-bottom:8px" },
        etiqueta(t("imp_hosp_ya"), "ok"),
        h("span", { clase: "chico" }, x.nombre));
    }
    const nivel = lista("nivel", NIVELES_HOSPITAL());
    const boton = h("button", { clase: "claro chico", type: "button",
      onclick: (e) => agregar(e) }, t("imp_hosp_agregar"));

    async function agregar(e) {
      if (!nivel.value) return mensaje(t("imp_hosp_falta_nivel"), "alerta");
      e.target.disabled = true;
      try {
        await api.post("/catalogos/hospitales", {
          pais_id: punto.pais_id, plaza_id: punto.plaza_id,
          nombre: x.nombre, direccion: x.direccion || null,
          telefono: x.telefono || null,
          lat: x.lat, lon: x.lon, nivel_atencion: nivel.value,
        });
        mensaje(`${x.nombre} ${t("imp_hosp_agregado")}`);
        await cargar();
        await enGoogle();
      } catch (err) {
        mensaje(err.message, "grave");
        e.target.disabled = false;
      }
    }

    return h("div", { clase: "tarjeta lisa", style: "margin:0 0 8px" },
      h("div", {}, h("b", {}, x.nombre)),
      h("div", { clase: "gris chico" },
        `${x.direccion || ""}${x.telefono ? " · " + x.telefono : ""}`),
      h("div", { clase: "acciones", style: "margin-top:8px" },
        campo(t("imp_hosp_nivel"), nivel), boton));
  }

  cargar();
  return h("div", { clase: "tarjeta" },
    h("h4", {}, t("imp_hospitales")),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("imp_hospitales_sub")),
    lista_,
    h("div", { clase: "acciones", style: "margin-top:12px" }, buscar),
    hallazgos);
}


/* --------------------------------------------- tabulador del acuerdo

   El tabulador de la empresa vale para el eventual: un dia suelto con
   las mismas reglas para todos. El implantado se negocia cliente por
   cliente —que come el equipo, si se le paga el traslado, que pasa con
   la gasolina— y eso es parte del acuerdo. Por eso este apartado vive
   dentro del acuerdo y no en el panel de viaticos: ahi se usa, aqui se
   acuerda.

   Los montos son por dia y por persona, que es como se comprueban y
   como se reparten cuando el consultor fija el mes. */

const NOMBRE_CONCEPTO = {
  alimentos: "imp_tab_alimentos",
  traslado_personal: "imp_tab_traslado",
  combustible: "imp_tab_combustible",
  casetas: "imp_tab_casetas",
  hospedaje: "imp_tab_hospedaje",
  otros: "imp_tab_otros",
};

function bloqueTabulador(servicioId) {
  const caja = h("div", { clase: "minimo-caja", style: "margin-top:16px" });
  pintarTabulador(caja, servicioId);
  return caja;
}

async function pintarTabulador(caja, servicioId) {
  caja.replaceChildren(h("div", { clase: "gris chico" }, t("imp_cargando")));
  let datos;
  try {
    datos = await api.get(`/implantados/${servicioId}/tabulador`);
  } catch (err) {
    return caja.replaceChildren(h("div", { clase: "bloqueo" }, err.message));
  }

  const moneda = datos.moneda || "MXN";
  const filas = [];
  const cuerpo = h("tbody");

  for (const r of datos.renglones) {
    /* Cada concepto trae su casilla de "va": el cliente que no paga
       casetas no tiene por que ver un renglon de casetas en cero, y
       borrarlo del catalogo no es lo mismo que no haberlo acordado. */
    const va = h("input", { type: "checkbox" });
    va.checked = !!r.activo;
    const monto = entrada("monto", {
      type: "number", step: "1", min: "0", clase: "num",
      style: "text-align:right; max-width:120px",
      value: r.monto !== null ? String(Math.round(Number(r.monto))) : "",
      placeholder: r.sugerido ? String(Math.round(Number(r.sugerido))) : "",
    });
    const abierto = h("input", { type: "checkbox",
                                 title: t("imp_tab_abierto_ayuda") });
    abierto.checked = !!r.monto_abierto;
    const nota = entrada("nota", { value: r.nota || "",
                                   placeholder: t("imp_tab_nota") });

    const sincronizar = () => {
      monto.disabled = !va.checked || abierto.checked;
      nota.disabled = !va.checked;
      abierto.disabled = !va.checked;
    };
    va.addEventListener("change", sincronizar);
    abierto.addEventListener("change", sincronizar);
    sincronizar();

    filas.push({ concepto: r.concepto, va, monto, abierto, nota });
    cuerpo.append(h("tr", {},
      h("td", {}, va),
      h("td", {},
        h("div", {}, t(NOMBRE_CONCEPTO[r.concepto] || "imp_tab_otros")),
        r.sugerido
          ? h("div", { clase: "gris chico" },
              `${t("imp_tab_sugerido")} ${dinero(r.sugerido, moneda)}`)
          : null),
      h("td", { style: "text-align:right" }, monto),
      h("td", { style: "text-align:center" }, abierto),
      h("td", {}, nota)));
  }

  const guardar = h("button", { clase: "claro chico", type: "button",
    onclick: (e) => mandar(e) }, t("imp_tab_guardar"));

  async function mandar(e) {
    e.target.disabled = true;
    try {
      const r = await api.put(`/implantados/${servicioId}/tabulador`, {
        renglones: filas.map(f => ({
          concepto: f.concepto,
          monto: f.abierto.checked ? 0 : Number(f.monto.value || 0),
          monto_abierto: f.abierto.checked,
          nota: f.nota.value || null,
          activo: f.va.checked,
        })),
      });
      mensaje(`${t("imp_tab_guardado")}: `
              + `${dinero(r.total_dia, moneda)} ${t("imp_tab_monto").toLowerCase()}`);
      await pintarTabulador(caja, servicioId);
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  }

  caja.replaceChildren(
    h("h4", { style: "margin:0 0 2px" }, t("imp_tabulador")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" }, t("imp_tab_sub")),
    datos.capturado
      ? null
      : h("div", { clase: "bloqueo", style: "margin:0 0 10px" },
          h("b", {}, t("imp_tab_vacio"))),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", { style: "width:34px" }, t("imp_tab_va")),
        h("th", {}, t("imp_tab_concepto")),
        h("th", { style: "text-align:right" }, t("imp_tab_monto")),
        h("th", { style: "text-align:center" }, t("imp_tab_abierto")),
        h("th", {}, t("imp_tab_nota")))),
      cuerpo),
    h("div", { clase: "acciones", style: "margin-top:10px" },
      guardar,
      h("span", { clase: "chico" },
        h("b", {}, `${t("imp_tab_total")} `
                   + dinero(datos.total_dia, moneda)))));
}

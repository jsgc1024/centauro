/* Pantallas del consultor: su cartera, el alta de un servicio y el
   armado del mismo hasta publicar el task sheet.

   El orden de la pantalla de servicio es el mismo del task sheet:
   encabezado, equipo y unidad, los dias con su agenda, y al final el
   hospedaje. Quien arma el documento lo ve igual que quien lo recibe. */
import { api, sesion } from "./api.js";
import { catalogos } from "./catalogos.js";
import { aviso, buscador, campo, coincide, conAyuda, datosDeFormulario,
         dinero, entrada, estatus, etiqueta, fecha, h, hora, lista,
         mensaje, plegable, telefono, textoDe, vaciar } from "./util.js";
import { IDIOMAS, t } from "./idioma.js";
import { queda } from "./cierre.js";

/* Google cobra por sesion: todas las teclas de una misma busqueda mas el
   lugar que se elija cuentan como una. Se renueva al cerrar cada una. */
function sesionDeBusqueda() {
  return (crypto.randomUUID && crypto.randomUUID())
         || String(Date.now() + Math.random());
}

const TONO_ESTATUS = {
  /* El semaforo del servicio, de izquierda a derecha en el tiempo.

     Azul es "listo y esperando": el equipo esta completo y el dia
     todavia no llega. Verde es "el equipo ya esta con el principal",
     que es el estado bueno de verdad y el que la pantalla debe hacer
     saltar. Ambar es lo que le falta algo.

     Y por eso el final se apaga: un servicio que ya paso no necesita
     atencion, y dejarlo en verde hacia que el color mas fuerte de la
     lista lo llevaran los que ya no importan --con doscientos servicios
     cerrados, el verde dejaba de querer decir nada--.

     Y el principio tambien se apaga: `solicitado` va en gris, decision
     de Salvador. Es el primer estado de la fila y todavia no pide nada
     --lo que pide es `planeado`, que es el que le falta equipo--. En
     azul competia con `asignado` en la misma columna y adelantaba una
     urgencia que no existe.

     Apagado no quiere decir igual. Cafe es `terminado` --el dia se
     cumplio, falta el papeleo-- y negro es `cerrado` --el expediente ya
     no se toca--, decision de Salvador. Con los dos en gris, tres
     estados muy distintos se leian iguales en la misma columna. */
  borrador: "", solicitado: "", cotizado: "", autorizado: "info",
  planeado: "alerta",
  asignado: "azul",
  arribado: "arribo",
  en_curso: "ok",
  terminado: "cafe", sin_visto_bueno: "alerta", en_facturacion: "cafe",
  cerrado: "negro", cancelado: "grave",
};

/* ------------------------------------------------------------ cartera */

export async function cartera(main) {
  /* Los relojes del cierre se piden aparte y no frenan la lista: quien
     no puede ver el cierre ve la cartera igual, sin relojes. */
  const [servicios, cat, relojes] = await Promise.all([
    api.get("/servicios"), catalogos(),
    api.get("/cierre/relojes").catch(() => [])]);
  const relojDe = new Map(relojes.map(r => [r.servicio_id, r]));
  const cliente = (id) => {
    const c = cat.clientes.find(x => x.id === id);
    return c ? c.nombre : "—";
  };
  main.append(
    h("h1", {}, t("cartera_titulo")),
    h("p", { clase: "sub" }, t("cartera_sub")),
    h("div", { clase: "acciones", style: "margin-bottom:16px" },
      h("button", { onclick: () => (location.hash = "#/servicio/nuevo") },
        t("nuevo_servicio"))),
  );

  if (!servicios.length) {
    main.append(h("div", { clase: "tarjeta" },
      h("div", { clase: "vacio" }, t("sin_servicios"))));
    return;
  }

  /* Por folio, por cliente, por ejecutivo o por estatus. La cartera
     crece y nada mas: con doscientos servicios, encontrar uno a ojo
     deja de ser posible. */
  const zona = h("div");
  let q = "";
  const caja = buscador(t("bus_ayuda_servicio"), (texto) => {
    q = texto;
    dibujar();
  });
  main.append(
    h("div", { clase: "tarjeta lisa", style: "margin-bottom:16px" },
      campo(t("bus_buscar"), caja)),
    zona);
  dibujar();

  function dibujar() {
    const filas = servicios.slice().reverse().filter(
      s => coincide(q, s.folio, cliente(s.cliente_id), s.ejecutivo_completo,
                    s.tipo, estatus(s.estatus)));
    if (!filas.length) {
      return zona.replaceChildren(
        aviso(t("bus_nada").replace("{q}", q.trim())));
    }

    const cuerpo = h("tbody");
    for (const s of filas) {
      cuerpo.append(h("tr", { clase: "clic",
                              onclick: () => (location.hash = `#/servicio/${s.id}`) },
        h("td", {}, h("b", {}, s.folio)),
        h("td", {}, cliente(s.cliente_id)),
        h("td", {}, s.ejecutivo_completo
          || h("span", { clase: "gris" }, t("sin_ejecutivo"))),
        h("td", {}, s.tipo),
        h("td", {}, etiqueta(estatus(s.estatus), TONO_ESTATUS[s.estatus] || ""),
          relojDeCartera(relojDe.get(s.id), s)),
        h("td", { clase: "num" }, s.equipos ? s.equipos.length : 1),
      ));
    }

    zona.replaceChildren(h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("col_folio")), h("th", {}, t("col_cliente")),
        h("th", {}, t("col_ejecutivo")), h("th", {}, t("col_tipo")),
        h("th", {}, t("col_estatus")), h("th", {}, t("col_equipos")))),
      cuerpo));
  }
}

/* Junto al estatus, el tiempo que queda (seccion 59): el del personal
   mientras comprueba, el del consultor sin visto bueno, y el de volver a
   mandarlo si finanzas lo regreso. Fuera de plazo, en rojo. */
function relojDeCartera(r, servicio) {
  if (!r || !r.reloj) return null;
  const min = r.reloj.minutos;
  const mio = sesion.usuario && servicio.consultor_id === sesion.usuario.persona_id;
  let texto;
  let color = "";
  if (r.fase === "comprobacion") {
    texto = t("cie_cartera_comprobando").replace("{q}", queda(min));
  } else if (min < 0) {
    texto = t("cie_fuera_de_plazo");
    color = "color:var(--grave);font-weight:650";
  } else {
    texto = (r.fase === "devuelto" ? t("cie_cartera_regresado")
             : mio ? t("cie_cartera_te_quedan") : t("cie_cartera_quedan"))
      .replace("{q}", queda(min));
    color = "color:var(--alerta);font-weight:650";
  }
  return h("div", { clase: "chico" + (color ? "" : " gris"),
                    style: "margin-top:5px;" + color }, texto);
}

/* ------------------------------------------------------------ alta */

/* Pantalla 1: alta de servicio.

   El minimo para cerrar la programacion es corto a proposito: cliente,
   quien lo solicita, el dia con su hora de inicio y el punto donde
   arranca el servicio, que puede ser la direccion, los datos del vuelo,
   o los dos. El equipo, la unidad y los viaticos son el paso siguiente.

   La lista de arriba dice en todo momento que falta, para que nadie
   tenga que adivinar por que no se puede guardar todavia. */

const ANTICIPACION_AEROPUERTO = 45;
const ANTICIPACION_NORMAL = 30;

function hoyMas(dias) {
  const f = new Date(Date.now() + dias * 86400000);
  return f.toISOString().slice(0, 10);
}

/* La hora a la que el equipo tiene que estar en el punto. En 24 h,
   porque es la que se guarda y la que llena el campo de presentacion. */
function menos(reloj, minutos) {
  const [hh, mm] = reloj.split(":").map(Number);
  const t = new Date(2000, 0, 1, hh, mm - minutos);
  return `${String(t.getHours()).padStart(2, "0")}:`
       + `${String(t.getMinutes()).padStart(2, "0")}`;
}

/* Como se lee: con am/pm. Es la hora que se le dicta por telefono al
   conductor, y un 05:15 sin marca se confunde con las cinco de la tarde. */
function enDoce(reloj) {
  const [hh, mm] = reloj.split(":").map(Number);
  const h12 = hh % 12 || 12;
  return `${String(h12).padStart(2, "0")}:${String(mm).padStart(2, "0")} `
       + (hh < 12 ? "am" : "pm");
}

export async function nuevoServicio(main) {
  const cat = await catalogos();

  /* Un servicio puede llevar varios equipos: Alfa cuida al director y
     Beta a su esposa, o uno hace la avanzada mientras el otro traslada.
     Cada equipo tiene su propio ejecutivo principal, sus propios dias y
     su propio punto de inicio, porque cada uno publica su task sheet. */
  const ALIAS = ["Alfa", "Beta", "Gamma", "Delta", "Epsilon", "Zeta",
                 "Eta", "Theta"];
  const equipos = [];

  /* Sin llave de Google el buscador se apaga una vez para toda la
     pantalla, no equipo por equipo. */
  let buscadorApagado = false;

  /* =================================================== cliente y ciudad */

  /* Los clientes llegan de Odoo sin tarifario (seccion 75): se ofrecen
     igual, diciendolo, porque sin tarifario no se les puede cotizar. */
  const clientes = lista("cliente_id",
    [{ valor: "", texto: t("elige_cliente") },
     ...cat.clientes.map(c => ({ valor: c.id, texto: c.tarifario_id
       ? c.nombre : `${c.nombre} ${t("cli_sin_tarifario")}` }))],
    { onchange: () => { cargarSolicitantes(); revisar(); } });

  const consultores = lista("consultor_id",
    cat.consultores.map(c => ({ valor: c.id, texto: c.nombre })));
  /* El consultor que da de alta se propone a si mismo: casi siempre es su
     propio cliente, y si esta cubriendo a alguien lo cambia. */
  if (sesion.usuario && sesion.usuario.persona_id) {
    const suyo = cat.consultores.find(c => c.id === sesion.usuario.persona_id);
    if (suyo) consultores.value = suyo.id;
  }

  const paises = lista("pais_id", cat.paises.map(
    p => ({ valor: p.id, texto: p.nombre })), {
    onchange: () => {
      for (const eq of equipos) eq.ciudad.repintar();
      repintarModalidades(); clavesDeTelefono(); revisar();
    } });


  /* La ciudad es de cada equipo, no del servicio: un mismo proyecto lleva
     al ejecutivo de Ciudad de Mexico a Monterrey, y cada equipo opera
     donde le toca. De ahi salen a quien se recomienda y si el recurso
     viaja, que es lo que genera viaticos foraneos.

     Y no son una lista cerrada: si el servicio cae en una ciudad donde
     nunca se ha trabajado, el consultor la agrega aqui mismo en vez de
     pedirle a alguien que se la de de alta. */
  function crearCiudad() {
    const select = lista("plaza_id", [], { onchange: () => verNueva() });
    /* La ciudad nueva se busca en Google y se guarda con el nombre que
       tiene de verdad. Escrita a mano, la misma ciudad entra tres veces
       con tres ortografias —"San Pedro Garza Garcia", "Sn Pedro", "San
       Pedro GG"— y despues nadie puede contar cuantos servicios hubo
       ahi ni a quien le queda cerca. */
    const nombre = entrada("ciudad_nueva",
                           { placeholder: t("buscar_ciudad"),
                             oninput: () => esperar() });
    const opciones = h("div", { clase: "resultados" });
    const caja = h("div", { style: "display:none;margin-top:8px" },
                   nombre, opciones);
    let sesion = sesionDeBusqueda();
    let reloj = null;

    function repintar() {
      const antes = select.value;
      select.replaceChildren(
        ...cat.plazas
          .filter(p => String(p.pais_id) === String(paises.value))
          .map(p => h("option", { value: p.id }, p.nombre)),
        h("option", { value: "nueva" }, t("otra_ciudad")));
      // Si la ciudad que estaba sigue existiendo en el pais nuevo, se
      // respeta; si no, se queda la primera.
      if (antes && [...select.options].some(o => o.value === antes)) {
        select.value = antes;
      }
      verNueva();
    }

    function verNueva() {
      const nueva = select.value === "nueva";
      caja.style.display = nueva ? "block" : "none";
      if (nueva) nombre.focus();
      else opciones.replaceChildren();
      revisar();
    }

    function esperar() {
      clearTimeout(reloj);
      reloj = setTimeout(consultar, 300);   // no una peticion por tecla
    }

    async function consultar() {
      const texto = nombre.value.trim();
      opciones.replaceChildren();
      if (texto.length < 3) return;

      const parametros = new URLSearchParams({
        texto, sesion, tipos: "ciudades" });
      if (paises.value) parametros.set("pais_id", paises.value);

      try {
        const r = await api.get(`/mapas/sugerencias?${parametros}`);
        opciones.replaceChildren(...(r.lugares || []).map(lugar =>
          h("button", { clase: "resultado", type: "button",
            onclick: () => agregar(lugar.nombre) },
            h("b", {}, lugar.nombre),
            lugar.direccion ? h("span", { clase: "gris chico" },
                                lugar.direccion) : null)));
      } catch (err) {
        opciones.replaceChildren(h("div", { clase: "gris chico" },
                                   t("ciudad_sin_google")));
      }
    }

    async function agregar(escrito) {
      if (!escrito) return mensaje(t("escribe_ciudad"), "alerta");

      // La que ya estaba no se da de alta dos veces: se elige.
      const ya = cat.plazas.find(
        p => String(p.pais_id) === String(paises.value)
             && p.nombre.toLowerCase() === escrito.toLowerCase());
      if (ya) {
        select.value = ya.id;
        nombre.value = "";
        verNueva();
        return;
      }

      try {
        const ciudad = await api.post("/catalogos/plazas",
                                      { nombre: escrito,
                                        pais_id: Number(paises.value) });
        cat.plazas.push(ciudad);
        // La ciudad nueva le sirve a todos los equipos, no solo a este.
        for (const eq of equipos) eq.ciudad.repintar();
        select.value = ciudad.id;
        nombre.value = "";
        sesion = sesionDeBusqueda();
        verNueva();
        mensaje(`${ciudad.nombre} ${t("ciudad_dada_alta")}`);
      } catch (err) {
        mensaje(err.message, "grave");
      }
    }

    return {
      repintar, select, caja,
      valor: () => (select.value && select.value !== "nueva"
        ? Number(select.value) : null),
      nodo: h("div", { clase: "campo" },
              h("label", {}, t("ciudad_opera")), select, caja),
    };
  }

  /* =================================================== quien solicita */

  /* El correo va primero porque es lo que identifica al contacto: en
     cuanto se escribe uno ya conocido, el resto se llena solo. */
  /* En que idioma lee cada uno. El principal arranca en ingles
     --suele ser extranjero-- y quien solicita, en el de su pais: casi
     siempre es gente local. El vacio del solicitante no es "sin idioma",
     es "el de su pais", y lo resuelve el servidor con el pais del
     servicio. Decision de Salvador (20 sep). */
  const idiomaEjecutivo = h("select", { name: "idioma_ejecutivo" },
    ...IDIOMAS.map(i => h("option", {
      value: i.codigo, selected: i.codigo === "en" || undefined },
      `${i.bandera} ${i.nombre}`)));
  const idiomaSolicitante = h("select", { name: "idioma_solicitante" },
    h("option", { value: "" }, t("idioma_del_pais")),
    ...IDIOMAS.map(i => h("option", { value: i.codigo },
                          `${i.bandera} ${i.nombre}`)));

  /* Como se presenta el equipo. Tres y no texto libre: "traje oscuro
     sin corbata" escrito a mano en cada servicio se lee distinto cada
     vez, y quien lo tiene que cumplir lo lee en la app a las cinco de
     la manana. Arranca vacio a proposito: un servicio del que nadie
     acordo nada no es un servicio "casual". */
  const vestimenta = h("select", { name: "vestimenta" },
    h("option", { value: "" }, t("vestimenta_sin")),
    ...["casual", "semiformal", "formal"].map(
      v => h("option", { value: v }, t(`vest_${v}`))));

  const solicitanteCorreo = entrada("solicitante_correo", {
    type: "email", oninput: () => reconocerPorCorreo() });
  const solicitante = entrada("solicitante_nombre", { oninput: () => revisar() });
  const solicitanteApellidos = entrada("solicitante_apellidos",
                                       { oninput: () => revisar() });
  const solicitanteTelefono = telefono("solicitante_telefono");

  /* Quien solicita se da de alta una vez y despues se elige de la lista:
     nadie tiene que volver a escribir el correo de un cliente que pide
     servicios cada semana. */
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
      // Se muestran, no se editan: para corregirlos esta la ficha del
      // contacto, y asi un dedazo aqui no cambia lo que ya estaba bien.
      control.readOnly = !!elegido;
      control.classList.toggle("fijo", !!elegido);
    }
    if (elegido) solicitanteTelefono.poner(elegido.telefono);
    else solicitanteTelefono.limpiar();
    solicitanteTelefono.bloquear(!!elegido);

    // El correo nunca se bloquea: es por donde se empieza y por donde se
    // corrige si el consultor se equivoco de contacto.
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

  /* =================================================== modalidades */

  /* Las modalidades son de cada pais: la jornada de Mexico no es la de
     Brasil. Sin filtrar aparecian las de todos los paises juntas. */
  const NOMBRE_MODALIDAD = {
    full_day: t("mod_full_day"), medio_dia: t("mod_medio_dia"),
    transfer: t("mod_transfer"),
  };
  const ORDEN_MODALIDAD = ["full_day", "medio_dia", "transfer"];

  function opcionesModalidad() {
    return cat.modalidades
      .filter(m => String(m.pais_id) === String(paises.value))
      .sort((a, b) => ORDEN_MODALIDAD.indexOf(a.codigo)
                      - ORDEN_MODALIDAD.indexOf(b.codigo))
      .map(m => ({
        valor: m.id,
        texto: `${NOMBRE_MODALIDAD[m.codigo] || m.codigo} · ${Number(m.horas)} h`,
      }));
  }

  /* Al cambiar de pais cada dia se queda en la misma modalidad, pero la
     del pais nuevo. */
  function repintarModalidades() {
    const opciones = opcionesModalidad();
    for (const equipo of equipos) {
      for (const fila of equipo.filas) {
        const antes = cat.modalidades.find(
          m => String(m.id) === String(fila.modalidad.value));
        fila.modalidad.replaceChildren(
          ...opciones.map(o => h("option", { value: o.valor }, o.texto)));
        const igual = antes && cat.modalidades.find(
          m => m.codigo === antes.codigo
               && String(m.pais_id) === String(paises.value));
        if (igual) {
          fila.modalidad.value = igual.id;
          if (!fila.km.dataset.suyo) fila.km.value = igual.km_estimados || "";
        }
      }
    }
  }

  /* Todo telefono lleva clave de pais; la del servicio se propone sola y
     solo se respeta lo que el consultor escriba encima. */
  function clavesDeTelefono() {
    const pais = cat.paises.find(p => String(p.id) === String(paises.value));
    const clave = (pais && pais.lada) || "+52";
    solicitanteTelefono.clavePais(clave);
    for (const equipo of equipos) equipo.ejecutivoTelefono.clavePais(clave);
  }

  /* =================================================== un equipo */

  /* Todo lo que es de un equipo vive dentro de esta funcion: sus dias, su
     ejecutivo principal, su punto de inicio y su propia sesion de
     busqueda en Google. Agregar el segundo equipo es llamarla otra vez,
     sin que el primero se entere. */
  function crearEquipo() {
    const equipo = { filas: [] };
    const filas = equipo.filas;

    equipo.ciudad = crearCiudad();

    /* ------------------------------------------- ejecutivo principal */

    const ejecutivoNombre = entrada("ejecutivo_nombre",
                                    { oninput: () => revisar() });
    const ejecutivoApellidos = entrada("ejecutivo_apellidos",
                                       { oninput: () => revisar() });
    const ejecutivoCorreo = entrada("ejecutivo_correo", { type: "email" });
    const ejecutivoTelefono = telefono("ejecutivo_telefono");
    equipo.ejecutivoTelefono = ejecutivoTelefono;

    /* Un proyecto que mueve al mismo ejecutivo de una ciudad a otra:
       Alfa lo cuida en Mexico, Beta en Monterrey. Se copia en vez de
       volver a escribirlo, y se mantiene copiado: si se corrige arriba,
       aqui se corrige solo. */
    const mismoEjecutivo = h("input", { type: "checkbox",
      onchange: () => { copiarEjecutivo(); revisar(); } });
    const cajaMismo = h("label", { clase: "casilla", hidden: true },
      mismoEjecutivo, h("span", {}, t("mismo_ejecutivo")));
    equipo.mismoEjecutivo = mismoEjecutivo;
    equipo.cajaMismo = cajaMismo;

    function copiarEjecutivo() {
      const primero = equipos[0];
      const copiar = mismoEjecutivo.checked && primero && primero !== equipo;
      for (const control of [ejecutivoNombre, ejecutivoApellidos,
                             ejecutivoCorreo]) {
        control.readOnly = copiar;
        control.classList.toggle("fijo", copiar);
      }
      ejecutivoTelefono.bloquear(copiar);
      if (!copiar) return;
      const suyo = primero.ejecutivo();
      ejecutivoNombre.value = suyo.nombre;
      ejecutivoApellidos.value = suyo.apellidos;
      ejecutivoCorreo.value = suyo.correo;
      ejecutivoTelefono.poner(suyo.telefono);
    }
    equipo.copiarEjecutivo = copiarEjecutivo;
    equipo.ejecutivo = () => ({
      nombre: ejecutivoNombre.value.trim(),
      apellidos: ejecutivoApellidos.value.trim(),
      correo: ejecutivoCorreo.value.trim(),
      telefono: ejecutivoTelefono.valor(),
    });

    /* ------------------------------------------------------- dias */

    const tablaJornadas = h("tbody");

    const agregarDia = (base) => {
      const fila = h("tr");
      const f = h("input", { type: "date", value: base || "",
                             onchange: () => revisar() });
      const modalidad = lista("modalidad", opcionesModalidad(),
                              { onchange: () => { proponerKm(); revisar(); } });
      /* La hora de presentacion es del dia 1: es la que amarra el
         arranque. Los demas dias arrancan con lo que diga su agenda, y
         mientras no la haya heredan la del primero. */
      const hora_ = h("input", { type: "time", value: "07:30",
        oninput: () => { hora_.dataset.suyo = "1"; revisar(); } });
      /* Los km del dia salen de la modalidad: transfer 40, medio dia 80,
         dia completo 150. Es una propuesta, no un candado: en cuanto el
         consultor escribe los suyos, deja de moverse sola. */
      const km = h("input", { type: "number", min: "0", placeholder: "km",
        oninput: () => { km.dataset.suyo = "1"; } });

      function proponerKm() {
        if (km.dataset.suyo) return;
        const elegida = cat.modalidades.find(
          m => String(m.id) === String(modalidad.value));
        km.value = (elegida && elegida.km_estimados) || "";
      }

      /* La agenda del dia se carga desde el alta cuando el cliente ya la
         mando; si no, se queda pendiente y se sube despues, en la
         pantalla del servicio. Se captura igual que alla —hora y lugar,
         parada por parada— para que sea la misma agenda y no dos formas
         distintas de escribir lo mismo. */
      const paradas = [];
      const listaParadas = h("tbody");

      const agregarParada = () => {
        const hora = h("input", { type: "time" });
        const lugar = entrada("parada_lugar",
          { placeholder: t("ph_parada") });
        const fila = h("tr");
        const ref = { hora, lugar };
        fila.append(
          h("td", { clase: "col-hora" }, hora),
          h("td", {}, lugar),
          h("td", {}, h("button", { clase: "claro chico", type: "button",
            onclick: () => {
              fila.remove();
              paradas.splice(paradas.indexOf(ref), 1);
              marcarAgenda();
            } }, t("quitar"))));
        lugar.addEventListener("input", marcarAgenda);
        paradas.push(ref);
        listaParadas.append(fila);
      };

      const cajaAgenda = h("td", { colspan: "6", clase: "caja-agenda" },
        h("div", { clase: "gris chico", style: "margin-bottom:8px" },
          t("agenda_opcional")),
        h("table", {},
          h("thead", {}, h("tr", {},
            h("th", { clase: "col-hora" }, t("hora")),
            h("th", {}, t("lugar_direccion")), h("th", {}, ""))),
          listaParadas),
        h("div", { clase: "acciones", style: "margin-top:10px" },
          h("button", { clase: "claro chico", type: "button",
            onclick: () => agregarParada() }, t("agregar_parada"))));
      const filaAgenda = h("tr", { hidden: true }, cajaAgenda);

      const verAgenda = h("button", { clase: "claro chico", type: "button",
        onclick: () => {
          filaAgenda.hidden = !filaAgenda.hidden;
          verAgenda.textContent = filaAgenda.hidden ? t("agenda")
                                                     : t("cerrar_agenda");
          marcarAgenda();
        } }, t("agenda"));

      const marcaAgenda = h("span", { clase: "chico", style: "color:#b8860b" });
      function marcarAgenda() {
        const hay = paradas.some(p => p.lugar.value.trim());
        marcaAgenda.textContent = hay && filaAgenda.hidden
          ? t("agenda_cargada") : "";
      }

      const ref = { f, modalidad, hora_, km, paradas, fila, filaAgenda };
      const quitar = h("button", { clase: "claro chico", type: "button",
        onclick: () => {
          if (filas.length === 1) {
            return mensaje(t("un_dia_minimo"), "alerta");
          }
          fila.remove();
          filaAgenda.remove();
          filas.splice(filas.indexOf(ref), 1);
          numerar();
          revisar();
        } }, t("quitar"));
      filas.push(ref);
      agregarParada();
      proponerKm();
      fila.append(h("td", { clase: "dia-num gris chico" }, ""),
                  h("td", {}, f), h("td", {}, modalidad),
                  h("td", { clase: "col-hora" }, hora_, verAgenda, marcaAgenda),
                  h("td", { clase: "col-km" }, km), h("td", {}, quitar));
      tablaJornadas.append(fila, filaAgenda);
      numerar();
      revisar();
    };
    equipo.agregarDia = agregarDia;

    /* El dia 1 es el que manda: su hora y su punto de inicio son los que
       amarran el arranque del equipo. Por eso va marcado, y es el unico
       que pide hora. */
    const numerar = () => {
      filas.forEach((ref, i) => {
        ref.fila.querySelector(".dia-num").textContent =
          i === 0 ? t("dia_uno") : `${t("dia_n")} ${i + 1}`;
        ref.hora_.hidden = i > 0;
      });
    };

    /* ------------------------------------------- punto de inicio */

    const direccion = h("textarea", {
      rows: "2",
      placeholder: t("ph_direccion"),
      oninput: () => { sugerirMientrasEscribe(); revisar(); } });

    const vueloAerolinea = entrada("vuelo_aerolinea");
    const vueloNumero = entrada("vuelo_numero", {
      placeholder: "UA 1518", "data-mayusculas": "",
      oninput: () => revisar() });
    const vueloHora = h("input", { type: "datetime-local",
                                   oninput: () => revisar() });
    const vueloOrigen = entrada("vuelo_origen");
    /* El equipo que arranca en un aeropuerto siempre arranca contra un
       vuelo que llega: el ejecutivo esta aterrizando. El de salida es del
       ultimo dia y se captura en la pantalla del servicio, no aqui.

       Google ya sabe si el punto elegido es un aeropuerto, asi que la
       casilla se marca sola; queda a la vista por si el lugar no viene
       clasificado o el buscador esta apagado. */
    /* Lo que dijo Google del lugar elegido, aparte de lo que decida el
       consultor. Vacio mientras la direccion se escriba a mano: ahi no
       hay veredicto que contradecir. */
    let googleAeropuerto = null;
    let forzadoAeropuerto = false;

    const esAeropuerto = h("input", { type: "checkbox", onchange: () => {
      /* La casilla no es una etiqueta: abre la geocerca de 500 m a 2 km,
         y en un hotel eso deja al conductor marcando su llegada desde
         cuatro cuadras antes. */
      if (esAeropuerto.checked && googleAeropuerto === false) {
        const ok = confirm(t("cons_no_aeropuerto"));
        if (!ok) { esAeropuerto.checked = false; return; }
        forzadoAeropuerto = true;
      }
      verVuelo();
    } });

    const bloqueVuelo = h("div", { clase: "vuelo-datos", style: "display:none" },
      h("h4", { clase: "grupo" }, t("vuelo_llegada")),
      h("p", { clase: "gris chico", style: "margin:0 0 12px" },
        t("vuelo_llegada_sub")),
      h("div", { clase: "rejilla tres" },
        campo(t("aerolinea"), vueloAerolinea),
        campo(t("numero_vuelo"), vueloNumero),
        campo(t("procedencia"), vueloOrigen)),
      campo(t("fecha_hora_llegada"), vueloHora));

    function verVuelo() {
      const aeropuerto = esAeropuerto.checked;
      bloqueVuelo.style.display = aeropuerto ? "block" : "none";
      proponerRadio();
      if (!aeropuerto) {
        // Un punto que no es aeropuerto no lleva vuelo: no se queda un
        // dato suelto de una captura anterior.
        for (const c of [vueloAerolinea, vueloNumero, vueloOrigen, vueloHora]) {
          c.value = "";
        }
      }
      revisar();
    }

    const lat = entrada("origen_lat", { placeholder: "19.4361",
                                        oninput: () => repintarMapa() });
    const lon = entrada("origen_lon", { placeholder: "-99.0719",
                                        oninput: () => repintarMapa() });
    /* El radio de la geocerca, alrededor del mismo pin del punto de
       encuentro. Dos kilometros en aeropuerto y uno en cualquier otro
       lado: un aeropuerto no cabe en un kilometro —entre terminales,
       estacionamientos y accesos— y la app le negaria la llegada a
       alguien que esta donde debe. Es una propuesta: al escribir un
       radio a mano deja de moverse solo. */
    const GEOCERCA_AEROPUERTO = 2000;
    const GEOCERCA_NORMAL = 500;

    const metros = entrada("geocerca_metros", { type: "number", min: "50",
      step: "50", value: String(GEOCERCA_NORMAL),
      oninput: () => { metros.dataset.suyo = "1"; repintarMapa(); } });

    function proponerRadio() {
      if (metros.dataset.suyo) return;
      metros.value = esAeropuerto.checked ? GEOCERCA_AEROPUERTO
                                          : GEOCERCA_NORMAL;
      repintarMapa();
    }

    const enSitio = h("div", { clase: "destacado" });
    equipo.enSitio = enSitio;

    /* El punto de encuentro se busca en Google y de ahi se toman sus
       coordenadas: de ellas salen la geocerca que el conductor tiene que
       pisar y los tres hospitales del task sheet. Escribirlas a mano es
       la forma mas facil de equivocarse. */
    const mapaImagen = h("img", { clase: "mapa-vista", alt: "" });
    const mapaEnlace = h("a", { target: "_blank", rel: "noopener" },
                         t("abrir_google"));
    const mapaPie = h("div", { clase: "mapa-pie" }, mapaEnlace);
    const mapaVacio = h("div", { clase: "mapa-vacio" },
      t("buscar_para_pin"));
    const cajaMapa = h("div", { clase: "mapa-caja" }, mapaVacio);

    const resultados = h("div", { clase: "resultados" });

    /* La imagen se pide con la sesion puesta: en el src a secas el
       navegador la pide sin token y queda el icono de imagen rota. La
       anterior se suelta al pedir otra, para no ir juntandolas. */
    let direccionImagen = null;

    async function repintarMapa() {
      const conPin = lat.value.trim() && lon.value.trim();
      vaciar(cajaMapa);
      if (!conPin) { cajaMapa.append(mapaVacio); return; }

      const radio = Number(metros.value) || GEOCERCA_NORMAL;
      mapaEnlace.href = "https://www.google.com/maps/search/?api=1&query="
        + encodeURIComponent(`${lat.value.trim()},${lon.value.trim()}`);
      cajaMapa.append(mapaImagen, mapaPie);

      try {
        const nueva = await api.imagen(
          `/mapas/imagen?lat=${lat.value.trim()}`
          + `&lon=${lon.value.trim()}&metros=${radio}`);
        if (direccionImagen) URL.revokeObjectURL(direccionImagen);
        direccionImagen = nueva;
        mapaImagen.src = nueva;
      } catch (err) {
        vaciar(cajaMapa);
        cajaMapa.append(h("div", { clase: "mapa-vacio" }, err.message));
      }
    }

    /* Google cobra por sesion de busqueda: todas las teclas de un mismo
       lugar mas el detalle del que se elija cuentan como una. Por eso el
       identificador se mantiene mientras se escribe y se renueva al
       elegir, que es cuando esa busqueda termino. Cada equipo lleva la
       suya: son dos puntos distintos. */
    let sesionBusqueda = nuevaSesion();
    let esperaSugerencias = null;
    let ultimoBuscado = "";

    function nuevaSesion() {
      return (crypto.randomUUID && crypto.randomUUID())
        || String(Date.now()) + Math.random().toString(16).slice(2);
    }

    function sugerirMientrasEscribe() {
      if (buscadorApagado) return;
      clearTimeout(esperaSugerencias);
      const texto = direccion.value.trim();
      if (texto.length < 3) { vaciar(resultados); return; }
      // Se espera a que deje de teclear: no se pide una sugerencia por letra.
      esperaSugerencias = setTimeout(() => pedirSugerencias(texto), 350);
    }

    async function pedirSugerencias(texto) {
      if (texto === ultimoBuscado) return;
      ultimoBuscado = texto;
      try {
        const r = await api.get("/mapas/sugerencias?texto="
          + encodeURIComponent(texto)
          + `&pais_id=${paises.value}&sesion=${sesionBusqueda}`);
        // Si el consultor siguio escribiendo, esta respuesta ya no sirve.
        if (direccion.value.trim() !== texto) return;
        pintarSugerencias(r.lugares);
      } catch (err) {
        vaciar(resultados);
        if (err.codigo === 503) {
          /* Sin llave de Google la pantalla sigue sirviendo: se escribe la
             direccion y el pin se pone a mano. No tiene caso repetir el
             intento —ni el aviso rojo— en cada tecla. */
          buscadorApagado = true;
          resultados.append(h("div", { clase: "gris chico" }, t("sin_google")));
        } else {
          resultados.append(aviso(err.message, "grave"));
        }
      }
    }

    function pintarSugerencias(lugares) {
      vaciar(resultados);
      for (const lugar of lugares) {
        resultados.append(h("button", {
          clase: "resultado", type: "button",
          onclick: () => tomarLugar(lugar) },
          h("b", {}, lugar.nombre),
          lugar.direccion
            ? h("span", { clase: "gris chico" }, lugar.direccion) : null));
      }
    }

    /* Al elegir una sugerencia se piden sus coordenadas y se guarda la
       direccion como la escribe Google: el consultor puede seguir
       corrigiendo el texto si quiere, el punto ya quedo. */
    async function tomarLugar(sugerencia) {
      vaciar(resultados);
      resultados.append(h("div", { clase: "gris chico" }, t("buscando_punto")));
      try {
        const lugar = await api.get(
          `/mapas/lugar/${sugerencia.id}?sesion=${sesionBusqueda}`);
        direccion.value = lugar.nombre && lugar.direccion
          ? `${lugar.nombre} - ${lugar.direccion}`
          : (lugar.direccion || lugar.nombre);
        lat.value = lugar.lat;
        lon.value = lugar.lon;
        googleAeropuerto = !!lugar.aeropuerto;
        if (lugar.aeropuerto && !esAeropuerto.checked) {
          esAeropuerto.checked = true;
          mensaje(t("es_aeropuerto_aviso"));
        }
        verVuelo();
        repintarMapa();
      } catch (err) {
        mensaje(err.message, "grave");
      }
      vaciar(resultados);
      // Esa busqueda termino: la siguiente es otra sesion.
      sesionBusqueda = nuevaSesion();
      ultimoBuscado = "";
      revisar();
    }

    /* ------------------------------------------------- la tarjeta */

    const titulo = h("h3", { style: "margin:0" }, t("equipo"));
    const quitar = h("button", { clase: "claro chico", type: "button",
      onclick: () => quitarEquipo(equipo) }, t("quitar_equipo"));
    equipo.titulo = titulo;
    equipo.quitar = quitar;

    equipo.nodo = h("div", { clase: "tarjeta equipo" },
      h("div", { clase: "cabeza-equipo" }, titulo, quitar),

      equipo.ciudad.nodo,

      h("h4", { clase: "grupo" }, t("ejecutivo_principal")),
      h("p", { clase: "gris chico", style: "margin:0 0 12px" },
        t("ejecutivo_sub")),
      cajaMismo,
      h("div", { clase: "rejilla cuatro" },
        campo(t("nombre"), ejecutivoNombre),
        campo(t("apellido"), ejecutivoApellidos),
        campo(t("correo_campo"), ejecutivoCorreo),
        campo(t("telefono"), ejecutivoTelefono)),

      /* El punto de inicio y los dias son una sola cosa: el punto es
         donde arranca el dia 1, y la hora de ese dia es la que amarra el
         arranque. Por eso van en el mismo apartado y en ese orden. */
      conAyuda("h4", t("inicio_y_dias"), "ay_alta_inicio",
               { clase: "grupo" }),
      h("p", { clase: "gris chico", style: "margin:0 0 12px" },
        t("inicio_y_dias_sub")),
      h("div", { clase: "punto-inicio" },
        h("div", {},
          campo(t("direccion_encuentro"), direccion),
          resultados),
        cajaMapa),
      h("label", { clase: "casilla" }, esAeropuerto,
        h("span", {}, t("es_aeropuerto"))),
      bloqueVuelo,
      enSitio,
      h("details", { clase: "plegable" },
        h("summary", {}, t("ajustar_pin")),
        h("p", { clase: "gris chico" }, t("ajustar_pin_sub")),
        h("div", { clase: "rejilla tres" },
          campo(t("latitud"), lat),
          campo(t("longitud"), lon),
          campo(t("radio_metros"), metros))),

      conAyuda("h4", t("dias"), "ay_alta_dias",
               { style: "margin:18px 0 2px" }),
      h("p", { clase: "gris chico", style: "margin:0 0 10px" }, t("dias_sub")),
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, ""), h("th", {}, t("fecha_col")),
          h("th", {}, t("modalidad")), h("th", {}, t("presentacion")),
          h("th", { clase: "col-km" }, "Km"), h("th", {}, ""))),
        tablaJornadas),
      h("div", { clase: "acciones", style: "margin-top:12px" },
        h("button", { clase: "claro chico", type: "button",
          onclick: () => {
            const ultima = filas.length ? filas[filas.length - 1].f.value : "";
            const siguiente = ultima
              ? new Date(new Date(ultima + "T00:00:00").getTime() + 86400000)
                  .toISOString().slice(0, 10)
              : "";
            agregarDia(siguiente);
          } }, t("agregar_dia"))));

    /* Lo que el resto de la pantalla necesita saber de este equipo. */
    equipo.cumple = () => ({
      ciudad: equipo.ciudad.valor() !== null,
      ejecutivo: !!ejecutivoNombre.value.trim()
                 && !!ejecutivoApellidos.value.trim(),
      dia: filas.length > 0 && !!filas[0].f.value && !!filas[0].hora_.value,
      inicio: !!direccion.value.trim() || !!vueloNumero.value.trim()
              || !!vueloHora.value,
    });

    equipo.conDireccion = () => !!direccion.value.trim();
    equipo.conPin = () => !!lat.value.trim() && !!lon.value.trim();
    equipo.horaDeInicio = () => (filas.length ? filas[0].hora_.value : "");

    /* Con vuelo, la hora de presentacion es la de la llegada del equipo:
       45 minutos antes de que aterrice. Se propone sola porque es lo que
       siempre se hace, y se deja editar porque el consultor a veces la
       adelanta: aduana lenta, trafico, un ejecutivo que no factura. */
    equipo.proponerPresentacion = (reloj) => {
      if (!filas.length) return false;
      const hora_ = filas[0].hora_;
      if (hora_.dataset.suyo || hora_.value === reloj) return false;
      hora_.value = reloj;
      return true;
    };
    equipo.horaDeVuelo = () =>
      (esAeropuerto.checked && vueloHora.value
        ? vueloHora.value.slice(11, 16) : "");

    equipo.datos = () => {
      const jornadas = filas
        .filter(r => r.f.value)
        .map((r, i) => {
          const j = {
            fecha: r.f.value,
            modalidad_id: Number(r.modalidad.value),
            km_estimados: r.km.value ? Number(r.km.value) : null,
          };
          // La hora es del dia 1; los demas la heredan en el servidor.
          if (i === 0 && r.hora_.value) {
            j.hora_presentacion = r.hora_.value + ":00";
          }
          const paradasDelDia = r.paradas
            .filter(p => p.lugar.value.trim())
            .map(p => ({ hora: p.hora.value ? `${p.hora.value}:00` : null,
                         lugar: p.lugar.value.trim() }));
          if (paradasDelDia.length) j.paradas = paradasDelDia;
          if (i > 0) return j;
          /* El punto de inicio y el vuelo van en el dia 1. */
          if (direccion.value.trim()) j.origen_direccion = direccion.value.trim();
          if (lat.value && lon.value) {
            j.origen_lat = lat.value;
            j.origen_lon = lon.value;
            j.geocerca_metros = metros.value
              ? Number(metros.value)
              : (esAeropuerto.checked ? GEOCERCA_AEROPUERTO : GEOCERCA_NORMAL);
          }
          j.origen_aeropuerto = esAeropuerto.checked;
          j.origen_google_aeropuerto = googleAeropuerto;
          j.forzar_aeropuerto = forzadoAeropuerto;
          if (vueloAerolinea.value.trim())
            j.vuelo_aerolinea = vueloAerolinea.value.trim();
          if (vueloNumero.value.trim()) j.vuelo_numero = vueloNumero.value.trim();
          if (vueloOrigen.value.trim()) j.vuelo_origen = vueloOrigen.value.trim();
          if (vueloHora.value) {
            j.vuelo_hora = vueloHora.value.length === 16
              ? `${vueloHora.value}:00` : vueloHora.value;
            j.vuelo_tipo = "llegada";
          }
          return j;
        });

      return {
        plaza_id: equipo.ciudad.valor(),
        ejecutivo_nombre: ejecutivoNombre.value.trim() || null,
        ejecutivo_apellidos: ejecutivoApellidos.value.trim() || null,
        ejecutivo_correo: ejecutivoCorreo.value.trim() || null,
        ejecutivo_telefono: ejecutivoTelefono.valor() || null,
        jornadas,
      };
    };

    return equipo;
  }

  /* =================================================== los equipos */

  const zonaEquipos = h("div");

  function agregarEquipo(conDia = true) {
    if (equipos.length >= ALIAS.length) {
      return mensaje(t("alta_tope_equipos").replace("{n}", ALIAS.length),
                     "alerta");
    }
    const equipo = crearEquipo();
    equipos.push(equipo);
    zonaEquipos.append(equipo.nodo);
    equipo.ciudad.repintar();
    // El equipo nuevo arranca en la misma ciudad que el primero: casi
    // siempre es el mismo proyecto y la excepcion es cambiarla.
    if (equipos.length > 1 && equipos[0].ciudad.valor()) {
      equipo.ciudad.select.value = equipos[0].ciudad.valor();
    }
    clavesDeTelefono();
    if (conDia) equipo.agregarDia(hoyMas(1));
    renombrarEquipos();
    revisar();
    return equipo;
  }

  function quitarEquipo(equipo) {
    if (equipos.length === 1) {
      return mensaje(t("un_equipo_minimo"), "alerta");
    }
    equipo.nodo.remove();
    equipos.splice(equipos.indexOf(equipo), 1);
    renombrarEquipos();
    revisar();
  }

  /* El alias sale de la posicion, igual que en el servidor: si se quita
     Beta, el que era Gamma pasa a ser Beta. */
  function renombrarEquipos() {
    equipos.forEach((equipo, i) => {
      equipo.titulo.textContent = `${t("equipo")} ${ALIAS[i]}`;
      equipo.quitar.style.display = equipos.length > 1 ? "" : "none";
      // Copiar el ejecutivo solo tiene sentido a partir del segundo.
      equipo.cajaMismo.hidden = i === 0;
      if (i === 0) equipo.mismoEjecutivo.checked = false;
      equipo.copiarEjecutivo();
    });
  }

  /* =================================================== el minimo */

  const puntos = {
    cliente: t("min_cliente"),
    ciudad: t("min_ciudad"),
    solicitante: t("min_solicitante"),
    ejecutivo: t("min_ejecutivo"),
    dia: t("min_dia"),
    inicio: t("min_inicio"),
  };
  const marcas = {};
  const listaMinimo = h("div", { clase: "minimo" });
  for (const [llave, texto] of Object.entries(puntos)) {
    marcas[llave] = h("span", { clase: "marca" }, "—");
    listaMinimo.append(h("div", { clase: "punto" }, marcas[llave],
                         h("span", {}, texto)));
  }

  const botonAlta = h("button", { type: "submit" }, t("dar_de_alta"));
  const resumen = h("div", { clase: "gris chico" });

  function revisar() {
    // Un equipo a medias deja el servicio en borrador, aunque el otro
    // este completo: la hoja se publica por equipo.
    const deCadaEquipo = equipos.map(e => e.cumple());
    const todos = (llave) => deCadaEquipo.length > 0
      && deCadaEquipo.every(c => c[llave]);

    const cumple = {
      cliente: !!clientes.value,
      ciudad: todos("ciudad"),
      solicitante: !!solicitante.value.trim()
                   && !!solicitanteApellidos.value.trim(),
      ejecutivo: todos("ejecutivo"),
      dia: todos("dia"),
      inicio: todos("inicio"),
    };

    for (const [llave, ok] of Object.entries(cumple)) {
      marcas[llave].textContent = ok ? "✓" : "—";
      marcas[llave].className = `marca ${ok ? "si" : ""}`.trim();
    }

    const faltan = Object.entries(cumple).filter(([, ok]) => !ok)
                         .map(([k]) => puntos[k]);
    botonAlta.disabled = faltan.length > 0;
    botonAlta.textContent = faltan.length ? t("falta_info") : t("dar_de_alta");
    resumen.textContent = faltan.length
      ? `${t("falta")}: ${faltan.join(", ")}.`
      : t("queda_planeado");

    /* A que hora tiene que estar cada equipo en su punto: 45 minutos
       antes de que aterrice el vuelo, 30 antes de la presentacion. */
    const pais = cat.paises.find(p => String(p.id) === String(paises.value));
    const antesVuelo = (pais && pais.anticipacion_aeropuerto_min) || 45;
    const antesNormal = (pais && pais.anticipacion_min) || 30;

    let cambio = false;
    for (const equipo of equipos) {
      const reloj = equipo.horaDeVuelo();
      let texto = null;
      if (reloj) {
        // Con vuelo manda el vuelo: la presentacion del dia 1 se ajusta
        // sola a la hora en que el equipo tiene que estar en el punto.
        const enPunto = menos(reloj, antesVuelo);
        if (equipo.proponerPresentacion(enPunto)) cambio = true;
        texto = [`${enDoce(enPunto)} ${t("en_el_punto")}`,
                 `${antesVuelo} ${t("antes_vuelo")}`];
      } else if (equipo.horaDeInicio()) {
        const presentacion = equipo.horaDeInicio();
        texto = [`${enDoce(menos(presentacion, antesNormal))} ${t("en_el_punto")}`,
                 `${antesNormal} ${t("antes_presentacion")}`];
      }
      vaciar(equipo.enSitio);
      if (texto) {
        equipo.enSitio.append(h("h4", {}, t("llega_antes")),
                              h("div", { clase: "valor" }, texto[0]),
                              h("div", { clase: "nota" }, texto[1]));
      }
    }
    // Llenar la presentacion pudo completar el minimo del dia.
    if (cambio) revisar();
  }

  /* =================================================== formulario */

  const formulario = h("form", { onsubmit: async (e) => {
    e.preventDefault();
    const d = datosDeFormulario(formulario);

    // Quien copia al ejecutivo del primero se lleva sus datos ya
    // resueltos: lo que se ve en pantalla es lo que se guarda.
    for (const eq of equipos) eq.copiarEjecutivo();
    const armados = equipos.map(eq => eq.datos());
    if (armados.some(eq => !eq.jornadas.length)) {
      return mensaje(t("dia_con_fecha"), "alerta");
    }

    botonAlta.disabled = true;
    try {
      const servicio = await api.post("/servicios", {
        cliente_id: Number(d.cliente_id),
        pais_id: Number(d.pais_id),
        // La del servicio es la del primer equipo: es la del proyecto.
        plaza_id: armados[0].plaza_id,
        // Esta pantalla es la del eventual; el implantado tiene la suya.
        tipo: "eventual",
        consultor_id: d.consultor_id ? Number(d.consultor_id) : null,
        solicitante_id: d.solicitante_id ? Number(d.solicitante_id) : null,
        solicitante_nombre: d.solicitante_nombre,
        solicitante_apellidos: d.solicitante_apellidos,
        solicitante_correo: d.solicitante_correo,
        solicitante_telefono: solicitanteTelefono.valor(),
        /* El ejecutivo del primer equipo se guarda tambien arriba: es el
           que sale en la cartera y el que heredan los equipos que no
           capturen el suyo. */
        ejecutivo_nombre: armados[0].ejecutivo_nombre,
        ejecutivo_apellidos: armados[0].ejecutivo_apellidos,
        ejecutivo_correo: armados[0].ejecutivo_correo,
        ejecutivo_telefono: armados[0].ejecutivo_telefono,
        idioma_ejecutivo: idiomaEjecutivo.value,
        idioma_solicitante: idiomaSolicitante.value || null,
        vestimenta: vestimenta.value || null,
        equipos: armados,
      });
      mensaje(`${servicio.folio}: `
        + (servicio.estatus === "planeado" ? t("servicio_planeado")
                                           : t("servicio_borrador")));

      const sinDireccion = equipos.filter(eq => !eq.conDireccion()).length;
      const sinPin = equipos.filter(eq => eq.conDireccion() && !eq.conPin()).length;
      if (sinDireccion) {
        mensaje(t("pendiente_direccion"), "alerta");
      } else if (sinPin) {
        mensaje(t("pendiente_pin"), "alerta");
      }
      location.hash = `#/servicio/${servicio.id}`;
    } catch (err) {
      mensaje(err.message, "grave");
      botonAlta.disabled = false;
    }
  }});

  /* =================================================== armado */

  /* Cada bloque se pliega cuando ya se resolvio, y al plegarse deja su
     resumen en el mismo renglon del titulo. Para cuando se llega a los
     dias de cada equipo --que es lo largo del alta-- lo de arriba ya no
     estorba y sigue estando a la vista en una linea. */
  const unidos = (...partes) => partes.filter(Boolean).join(" · ");

  formulario.append(
    h("div", { clase: "tarjeta" },
      plegable(t("cliente"), [
        h("div", { clase: "rejilla tres" },
          campo(t("cliente"), clientes),
          campo(t("consultor_asignado"), consultores)),
        h("div", { clase: "rejilla tres" },
          campo(t("pais"), paises)),
      ], () => unidos(clientes.value ? textoDe(clientes) : "",
                      textoDe(paises), textoDe(consultores))),

      plegable(t("quien_solicita"), [
        campo(t("elegir_solicitante"), solicitanteElegido),
        h("div", { clase: "rejilla cuatro" },
          campo(t("correo_campo"), solicitanteCorreo),
          campo(t("nombre"), solicitante),
          campo(t("apellido"), solicitanteApellidos),
          campo(t("telefono"), solicitanteTelefono)),
      ], () => unidos(
        [solicitante.value, solicitanteApellidos.value]
          .filter(Boolean).join(" ").trim(),
        solicitanteCorreo.value), { clase: "grupo" }),

      plegable(t("idioma_titulo"), [
        h("p", { clase: "gris chico", style: "margin:0 0 12px" },
          t("idioma_sub")),
        h("div", { clase: "rejilla tres" },
          campo(t("idioma_principal"), idiomaEjecutivo),
          campo(t("idioma_solicitante"), idiomaSolicitante)),
      ], () => unidos(textoDe(idiomaEjecutivo), textoDe(idiomaSolicitante)),
         { clase: "grupo" }),

      plegable(t("vestimenta_titulo"), [
        h("p", { clase: "gris chico", style: "margin:0 0 12px" },
          t("vestimenta_sub")),
        h("div", { clase: "rejilla tres" },
          campo(t("vestimenta_campo"), vestimenta)),
      ], () => textoDe(vestimenta), { clase: "grupo" })),

    h("div", { clase: "tarjeta minimo-caja" },
      conAyuda("h4", t("equipos_titulo"), "ay_alta_equipos"),
      h("p", { clase: "gris chico", style: "margin:0" }, t("equipos_sub"))),

    zonaEquipos,

    h("div", { clase: "acciones", style: "margin-bottom:18px" },
      h("button", { clase: "claro", type: "button",
                    onclick: () => agregarEquipo() }, t("agregar_equipo"))),

    h("div", { clase: "acciones" },
      botonAlta,
      h("button", { clase: "claro", type: "button",
                    onclick: () => (location.hash = "#/servicios") },
        t("cancelar")),
      resumen),
  );

  main.append(
    h("h1", {}, t("alta_titulo")),
    h("p", { clase: "sub" }, t("alta_sub")),
    h("div", { clase: "tarjeta minimo-caja" },
      conAyuda("h4", t("para_planeado"), "ay_alta_minimo"),
      listaMinimo),
    formulario);

  agregarEquipo();
  cargarSolicitantes();
}

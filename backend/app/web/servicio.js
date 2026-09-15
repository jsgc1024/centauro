/* Pantalla de un servicio. Sigue el mismo orden del task sheet:
   encabezado, meet and greet, equipo y unidad por dia, y al final el
   hospedaje. Quien lo arma ve lo mismo que quien lo va a recibir. */
import { api } from "./api.js";
import { catalogos } from "./catalogos.js";
import { buscadorDeLugar } from "./mapa.js";
import { aviso, campo, dinero, entrada, etiqueta, fecha, h, lista,
         mensaje, telefono } from "./util.js";
import { IDIOMAS, idioma, t } from "./idioma.js";

export async function pantallaServicio(main, servicioId) {
  const [servicio, cat] = await Promise.all([
    api.get(`/servicios/${servicioId}`), catalogos()]);
  const cliente = cat.clientes.find(c => c.id === servicio.cliente_id);
  const plaza = cat.plazas.find(p => p.id === servicio.plaza_id);

  main.append(encabezado(servicio, cliente, plaza));

  for (const equipo of servicio.equipos) {
    main.append(await bloqueEquipo(servicio, equipo, cat));
  }
  main.append(await bloqueTaskSheet(servicio));
  main.append(await bloqueRevisiones(servicio));
}

/* ------------------------------------------------------------ encabezado */

function encabezado(servicio, cliente, plaza) {
  return h("div", { clase: "tarjeta" },
    h("div", { style: "display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap" },
      h("div", {},
        h("h1", { style: "margin:0" }, servicio.folio),
        h("div", { clase: "gris" },
          `${cliente ? cliente.nombre : "—"} · ${servicio.tipo} · ${plaza ? plaza.nombre : "—"}`)),
      /* Lo que se puede hacer con el servicio va debajo de su estatus:
         de el depende cual de los dos aplica. Antes de que se mueva se
         borra; despues ya no, pero se cancela, y entonces se queda con
         su rastro y libera a la gente y las unidades. */
      h("div", { clase: "sello" },
        etiqueta(servicio.estatus, servicio.estatus === "cancelado" ? "grave" : ""),
        h("div", { clase: "acciones bajo-sello" },
          ANTES_DE_ARRANCAR.includes(servicio.estatus)
            ? h("button", { clase: "claro chico", type: "button",
                onclick: () => borrar(
                  `/servicios/${servicio.id}`,
                  `Eliminar el servicio ${servicio.folio} completo, con sus `
                  + `${servicio.equipos.length} equipo(s). Esto no se puede `
                  + "deshacer.",
                  "Servicio eliminado", "#/servicios") }, "Eliminar")
            : "",
          !["cancelado", "cerrado"].includes(servicio.estatus)
            ? h("button", { clase: "claro chico", type: "button",
                onclick: () => cancelar(servicio) }, "Cancelar")
            : ""))),
    h("div", { clase: "rejilla dos", style: "margin-top:14px" },
      h("div", {},
        h("h4", {}, "Ejecutivo principal"),
        h("div", {}, servicio.ejecutivo_completo || h("span", { clase: "gris" }, "Por definir")),
        h("div", { clase: "gris num" }, servicio.ejecutivo_telefono || "")),
      h("div", {},
        h("h4", {}, "Solicita"),
        h("div", {}, servicio.solicitante_completo || h("span", { clase: "gris" }, "—")))));
}

/* Un servicio que ya arranco no se borra: se cancela. La pantalla no
   decide nada, solo evita ofrecer un boton que el servidor va a negar. */
const ANTES_DE_ARRANCAR = ["borrador", "cotizado", "autorizado", "planeado",
                           "asignado"];

/* Cancelar exige motivo: es lo primero que pregunta el cliente y lo
   que la central necesita para saber por que se cayo el servicio. */
async function cancelar(servicio) {
  const motivo = prompt(
    `Cancelar el servicio ${servicio.folio}. Sus dias se cancelan y la `
    + "gente y las unidades quedan libres.\n\nMotivo de la cancelacion:");
  if (motivo === null) return;
  if (!motivo.trim()) return mensaje("La cancelacion necesita un motivo", "alerta");
  try {
    const r = await api.post(`/servicios/${servicio.id}/cancelar`,
                             { motivo: motivo.trim() });
    mensaje(`${r.folio} cancelado`);
    for (const v of r.viaticos_por_devolver || []) {
      mensaje(`Pendiente de devolver: ${v.persona} · ${v.monto} ${v.moneda}`,
              "alerta");
    }
    setTimeout(() => location.reload(), 1200);
  } catch (err) { mensaje(err.message, "grave"); }
}

/* Borrar pide el motivo: no es un tramite, es la unica huella que queda
   de un servicio que dejo de existir. */
async function borrar(ruta, advertencia, listo, destino = null) {
  const motivo = prompt(`${advertencia}\n\nPor que se elimina?`);
  if (motivo === null) return;
  try {
    await api.borrar(ruta, { motivo: motivo.trim() || null });
    mensaje(listo);
    if (destino) location.hash = destino; else location.reload();
  } catch (err) {
    const d = err.detalle;
    mensaje(d && d.que_hacer ? `${err.message}. ${d.que_hacer}` : err.message,
            "grave");
  }
}

/* ------------------------------------------------------------ equipo */

async function bloqueEquipo(servicio, equipo, cat) {
  const caja = h("div", { clase: "tarjeta" },
    h("div", { clase: "cabeza-equipo" },
        h("div", {},
        h("h3", { style: "margin:0" }, `Equipo ${equipo.alias}`),
        /* Donde opera este equipo: un mismo proyecto puede tener a Alfa
           en Ciudad de Mexico y a Beta en Monterrey. */
        h("div", { clase: "chico gris" }, ciudadDe(equipo, cat))),
      /* Solo tiene sentido con mas de un equipo: el ultimo no se quita,
         se elimina el servicio completo. */
      servicio.equipos.length > 1
        ? h("button", { clase: "claro chico", type: "button",
            onclick: () => borrar(
              `/servicios/equipos/${equipo.id}`,
              `Eliminar el equipo ${equipo.alias} con sus `
              + `${equipo.jornadas.length} dia(s). Esto no se puede deshacer.`,
              "Equipo eliminado") }, "Eliminar equipo")
        : ""),
    h("p", { clase: "gris chico", style: "margin:-6px 0 14px" },
      "Cada equipo lleva su propio task sheet, sus horas extra y su cierre."),
    /* A quien cuida este equipo. Con un solo equipo es el del servicio,
       que ya sale arriba; con dos o mas, cada hoja lleva el suyo. */
    h("div", { clase: "chico", style: "margin:-8px 0 14px" },
      h("span", { clase: "gris" }, "Ejecutivo principal: "),
      equipo.ejecutivo_completo
        || h("span", { clase: "gris" }, "Por definir"),
      equipo.ejecutivo_telefono
        ? h("span", { clase: "gris num" }, ` · ${equipo.ejecutivo_telefono}`)
        : ""));

  caja.append(await bloqueRecursos(equipo, cat));
  /* El dinero va pegado a la gente: en cuanto hay alguien asignado
     aparece cuanto se le deposita. Sin personal no se pinta nada,
     porque no hay a quien depositarle. */
  caja.append(await bloqueViaticos(equipo));
  caja.append(await bloqueHotel(servicio, equipo, cat));
  caja.append(tablaDias(servicio, equipo, cat));
  return caja;
}

/* Un boton que abre tambien tiene que cerrar. Si no, la unica salida es
   recargar la pantalla, y el consultor termina con tres formularios
   abiertos uno debajo del otro sin saber cual estaba llenando. */
function alternador(boton, zona, abrir, textoCerrar = "Cerrar") {
  const textoAbrir = boton.textContent;
  boton.addEventListener("click", async () => {
    if (zona.firstChild) {
      zona.replaceChildren();
      boton.textContent = textoAbrir;
      return;
    }
    boton.textContent = textoCerrar;
    await abrir();
  });
  return boton;
}

/* ------------------------------------------------- recursos del equipo */

/* Un equipo es la misma gente y la misma unidad de principio a fin: el
   conductor que recoge al ejecutivo el lunes es el que lo lleva al
   aeropuerto el jueves. Por eso se asignan una vez, para todos sus dias,
   en vez de repetir la misma decision dia por dia. */
async function bloqueRecursos(equipo, cat) {
  const caja = h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" });
  let datos;
  try {
    datos = await api.get(`/servicios/equipos/${equipo.id}/asignaciones`);
  } catch (err) { return caja.appendChild(aviso(err.message, "grave")), caja; }

  /* Asignar sin poder desasignar deja al consultor probando quien cabe
     sin marcha atras. Se quita de todos los dias, igual que se puso. */
  const quitar = (ruta, que) => h("button", {
    clase: "claro chico", type: "button", style: "margin-top:6px",
    onclick: async (e) => {
      if (!confirm(`Quitar a ${que} de los ${datos.dias} dias del equipo.`)) {
        return;
      }
      e.target.disabled = true;
      try {
        await api.borrar(ruta);
        location.reload();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, "Quitar");

  const ficha = (x, titulo, cuerpo, boton) => h("div", { clase: "persona" },
    x.foto ? h("img", { clase: "foto", src: x.foto, alt: "" })
           : h("div", { clase: "foto" }),
    h("div", {}, h("h4", { style: "margin:0 0 1px" }, titulo), ...cuerpo,
      /* Lo normal es que este todos los dias. Si no, es que hubo un
         cambio a media semana y eso hay que verlo. */
      x.dias < datos.dias
        ? h("div", { clase: "chico", style: "color:#b8860b" },
            `Solo ${x.dias} de ${datos.dias} dias`)
        : "",
      boton || ""));

  const variasUnidades = datos.vehiculos.length > 1;

  const gente = h("div", {}, h("h4", {}, "Equipo de seguridad"));
  if (datos.personal.length) {
    for (const p of datos.personal) {
      gente.append(ficha(p, p.puesto || "Personal", [
        h("b", {}, p.nombre),
        h("div", { clase: "chico" },
          p.telefono || h("span", { clase: "gris" }, "Sin telefono")),
        h("div", { clase: "chico gris" }, p.ciudad || ""),
        variasUnidades ? selectorAbordo(equipo, p, datos.vehiculos) : "",
      ], quitar(`/servicios/equipos/${equipo.id}/personal/${p.persona_id}`,
                p.nombre)));
    }
  } else {
    gente.append(h("span", { clase: "gris" }, "Por asignar"));
  }

  const flota = h("div", {}, h("h4", {}, "Unidad"));
  if (datos.vehiculos.length) {
    for (const v of datos.vehiculos) {
      flota.append(ficha(v, "Vehiculo de seguridad", [
        h("b", {}, v.unidad || "Unidad"), " ",
        h("span", { clase: "etiqueta" },
          v.blindada ? "Blindada" : "Sin blindar"),
        v.rentado ? " " : "", v.rentado ? etiqueta("rentada", "alerta") : "",
        h("div", {}, h("span", { clase: "placas" }, v.placa)),
        h("div", { clase: "chico gris" },
          [v.marca_modelo, v.color, v.anio].filter(Boolean).join(" · ")),
        /* A quien se le llama si la unidad falla a media jornada: en la
           flota propia es taller, aqui es la arrendadora. */
        v.rentado
          ? h("div", { clase: "chico gris" },
              [v.arrendadora, v.arrendadora_telefono].filter(Boolean)
                .join(" · "))
          : "",
      ], quitar(`/servicios/equipos/${equipo.id}/vehiculos/${v.vehiculo_id}`,
                v.placa)));
    }
  } else {
    flota.append(h("span", { clase: "gris" }, "Por asignar"));
  }

  const zona = h("div", { style: "margin-top:12px" });
  caja.append(
    h("div", { clase: "rejilla dos" }, gente, flota),
    h("p", { clase: "gris chico", style: "margin:12px 0 0" },
      `Los recursos son los mismos los ${datos.dias} dias del equipo. `
      + "Un cambio a media semana se hace por contingencia, en el dia que "
      + "aplique."),
    h("div", { clase: "acciones", style: "margin-top:8px" },
      alternador(h("button", { clase: "claro chico", type: "button" },
                   "Asignar recursos"),
                 zona, () => abrirAsignacion(zona, equipo, cat))),
    zona);
  return caja;
}

/* ------------------------------------------------------------ asignar */

/* El rol es de la tarea, no de la persona.

   El personal de seguridad es general: el mismo agente que hoy conduce
   manana coordina. Por eso la lista de abajo ya no se filtra por puesto
   —sale todo el que este libre— y lo que se elige aqui arriba es con
   que rol va, que es de donde salen el precio al cliente y la comision
   que se le paga. */
async function abrirAsignacion(zona, equipo, cat) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, "Buscando recursos…"));
  const perfil = cat.perfiles.find(p => p.codigo === "conductor_seguridad");
  const categoria = cat.categorias.find(c => c.codigo === "suv_blindada");

  const selPerfil = lista("perfil", cat.perfiles.map(
    p => ({ valor: p.id, texto: p.nombre })));
  const selCategoria = lista("categoria", cat.categorias.map(
    c => ({ valor: c.id, texto: c.nombre })));
  if (perfil) selPerfil.value = perfil.id;
  if (categoria) selCategoria.value = categoria.id;

  const resultados = h("div");
  const buscar = async () => {
    resultados.replaceChildren(h("div", { clase: "gris chico" }, "Buscando…"));
    try {
      const r = await api.get(
        `/servicios/equipos/${equipo.id}/recomendaciones` +
        `?perfil_id=${selPerfil.value}&categoria_id=${selCategoria.value}`);
      resultados.replaceChildren(
        pintarRecomendaciones(r, equipo, cat, Number(selCategoria.value),
                              () => Number(selPerfil.value) || null));
    } catch (e) { resultados.replaceChildren(aviso(e.message, "grave")); }
  };
  selPerfil.addEventListener("change", buscar);
  selCategoria.addEventListener("change", buscar);

  zona.replaceChildren(h("div", { clase: "tarjeta lisa" },
    h("div", { clase: "rejilla dos" },
      campo("Rol con el que va", selPerfil),
      campo("Categoria de unidad", selCategoria)),
    resultados));
  buscar();
}

function pintarRecomendaciones(r, equipo, cat, categoriaId, rolId) {
  /* Cada lista debajo del selector que la arma: perfil a la izquierda,
     categoria de unidad a la derecha. En pantalla angosta la rejilla se
     vuelve una sola columna sola. */
  return h("div", { clase: "rejilla dos", style: "margin-top:14px" },
    tablaPersonal(r.personal, equipo, rolId),
    tablaUnidades(r.vehiculos, equipo, cat, categoriaId));
}

/* El estado de un recurso en un solo lugar: la pantalla no vuelve a
   decidir si algo se puede asignar, solo lo pinta. */
function estadoDe(f) {
  const motivos = (f.alertas || []).map(a => a.mensaje || a.tipo).join(" · ");
  if (f.bloqueado) return { clave: "bloqueo", texto: "Ocupado", motivos };
  if (motivos) return { clave: "riesgo", texto: "Con riesgo", motivos };
  return { clave: "libre", texto: "Disponible", motivos: "" };
}

/* Locales primero y, dentro de cada ciudad, quien se puede asignar sin
   pelear con el calendario. Asi el consultor lee de arriba hacia abajo. */
const ORDEN = { libre: 0, riesgo: 1, bloqueo: 2 };

function ordenar(fichas) {
  return fichas.slice().sort((a, b) => {
    const ea = ORDEN[estadoDe(a).clave], eb = ORDEN[estadoDe(b).clave];
    if (a.local !== b.local) return a.local ? -1 : 1;
    if (ea !== eb) return ea - eb;
    return (b.calificacion || 0) - (a.calificacion || 0);
  });
}

function todos(bloque) {
  return [...(bloque.disponibles || []), ...(bloque.con_alerta || []),
          ...(bloque.no_disponibles || []), ...(bloque.de_otras_ciudades || [])];
}

/* La ciudad va pegada al nombre, no en columna aparte: en media pantalla
   lo que importa es si hay que traer a esa persona de otro lado. */
function lineaCiudad(f) {
  return f.local
    ? h("div", { clase: "chico gris" }, f.ciudad || "—")
    : h("div", { clase: "chico", style: "color:#b8860b" },
        `${f.ciudad || "otra ciudad"} · traslado`);
}

function celdaEstado(est) {
  return h("td", {},
    etiqueta(est.texto, est.clave === "libre" ? "ok"
             : est.clave === "riesgo" ? "alerta" : "grave"),
    est.motivos
      ? h("div", { clase: "chico gris", style: "margin-top:3px" }, est.motivos)
      : "");
}

function botonAsignar(est, hacer) {
  if (est.clave === "bloqueo") {
    return h("button", { clase: "chico claro", disabled: "disabled",
                         title: est.motivos }, "No se puede");
  }
  const forzar = est.clave === "riesgo";
  return h("button", { clase: "chico" + (forzar ? " claro" : ""),
    onclick: async (e) => {
      e.target.disabled = true;
      try {
        await hacer(forzar);
        location.reload();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, forzar ? "Asignar igual" : "Asignar");
}

function caja(titulo, bloque, cuantos, encabezados, cuerpo, vacio) {
  return h("div", {},
    h("h4", {}, `${titulo} (${cuantos})`),
    bloque.aviso ? aviso(bloque.aviso, "alerta") : "",
    cuantos
      ? h("table", {},
          h("thead", {}, h("tr", {}, ...encabezados.map(t => h("th", {}, t)))),
          cuerpo)
      : h("span", { clase: "gris" }, vacio));
}

function tablaPersonal(bloque, equipo, rolId = () => null) {
  const gente = ordenar(todos(bloque));
  const cuerpo = h("tbody");
  for (const p of gente) {
    const est = estadoDe(p);
    cuerpo.append(h("tr", {},
      h("td", {}, h("b", {}, p.nombre),
        p.es_freelance ? " " : "", p.es_freelance ? etiqueta("freelance") : "",
        p.telefono ? h("div", { clase: "chico gris" }, p.telefono) : "",
        lineaCiudad(p)),
      celdaEstado(est),
      h("td", { clase: "num" },
        p.calificacion !== null && p.calificacion !== undefined
          ? `${p.calificacion}` : "—",
        p.confianza_calificacion
          ? h("div", { clase: "chico gris" }, p.confianza_calificacion)
          : "",
        p.horas_en_centauro
          ? h("div", { clase: "chico gris" }, `${p.horas_en_centauro} h`) : ""),
      h("td", {}, botonAsignar(est, (forzar) =>
        api.post(`/servicios/equipos/${equipo.id}/asignar-personal`,
                 { persona_id: p.persona_id, rol_id: rolId(), forzar })))));
  }
  return caja("Personal de seguridad", bloque, gente.length,
              ["Persona", "Estado", "Calificacion", ""], cuerpo,
              "No hay nadie libre para esos dias.");
}

function tablaUnidades(bloque, equipo, cat, categoriaId) {
  const flota = ordenar(todos(bloque));
  const cuerpo = h("tbody");
  for (const v of flota) {
    const est = estadoDe(v);
    cuerpo.append(h("tr", {},
      h("td", {}, h("span", { clase: "placas" }, v.placa || v.placas),
        v.blindada ? " " : "", v.blindada ? etiqueta("blindada") : "",
        /* Que sea de renta se dice aqui y no en el task sheet: al
           consultor le cambia la decision —esa unidad cuesta aparte y
           se devuelve— y al ejecutivo no le cambia nada. */
        v.rentado ? " " : "", v.rentado ? etiqueta("rentada", "alerta") : "",
        h("div", { clase: "chico gris" },
          [v.unidad, v.marca_modelo, v.color, v.anio].filter(Boolean)
            .join(" · ")),
        v.rentado && v.arrendadora
          ? h("div", { clase: "chico gris" }, v.arrendadora) : "",
        lineaCiudad(v)),
      celdaEstado(est),
      h("td", {}, botonAsignar(est, (forzar) =>
        api.post(`/servicios/equipos/${equipo.id}/asignar-vehiculo`,
                 { vehiculo_id: v.vehiculo_id, forzar })))));
  }

  /* La flota no siempre alcanza: el cliente pide una categoria que no
     tenemos o la semana viene saturada, y el auto se subarrienda. Se
     captura aqui, en el momento de asignar, porque es cuando se sabe
     que hace falta: mandarlo al catalogo de flota seria otra pantalla,
     otro dia y un servicio detenido mientras tanto. */
  const zona = h("div");
  return h("div", {},
    caja("Unidades", bloque, flota.length,
         ["Unidad", "Estado", ""], cuerpo,
         "No hay unidades de esa categoria en la flota."),
    h("div", { clase: "acciones", style: "margin-top:8px" },
      alternador(h("button", { clase: "claro chico", type: "button" },
                   "Subir auto rentado"),
                 zona,
                 () => zona.replaceChildren(
                   formularioRenta(equipo, cat, categoriaId)))),
    zona);
}

/* Alta de un auto subarrendado. Casi todo es obligatorio, al reves que
   en la flota propia: de la unidad de casa se sabe todo aunque el alta
   venga incompleta, y de un auto que se recibe en un estacionamiento no
   se sabe nada si no queda escrito hoy. */
const MOTIVOS_RENTA = [
  { valor: "categoria_no_disponible",
    texto: "No hay esa categoria en la flota" },
  { valor: "saturacion", texto: "Flota saturada" },
  { valor: "pedido_especial", texto: "Pedido especial del cliente" },
];

function formularioRenta(equipo, cat, categoriaId) {
  const categorias = (cat && cat.categorias) || [];
  const selCategoria = lista("categoria", categorias.map(
    c => ({ valor: c.id, texto: c.nombre })));
  if (categoriaId) selCategoria.value = categoriaId;

  const placa = entrada("placa", { placeholder: "ABC-123-D",
                                   maxlength: "20", autocomplete: "off" });
  const marca = entrada("marca_modelo", { placeholder: "Suburban" });
  const color = entrada("color", { placeholder: "Negro" });
  const anio = entrada("anio", { type: "number", min: "1990", max: "2100",
                                 value: String(new Date().getFullYear()) });
  const costo = entrada("costo", { type: "number", step: "0.01", min: "1",
                                   placeholder: "0.00" });
  const arrendadora = entrada("arrendadora", { placeholder: "Nombre de la arrendadora" });
  const tel = telefono("arrendadora_telefono");
  const selMotivo = lista("motivo", MOTIVOS_RENTA);

  const guardar = h("button", { clase: "chico", type: "button" },
                    "Guardar y asignar");
  const zonaError = h("div");

  guardar.addEventListener("click", async () => {
    const faltan = [];
    if (placa.value.trim().length < 3) faltan.push("placas");
    if (marca.value.trim().length < 2) faltan.push("marca y modelo");
    if (color.value.trim().length < 2) faltan.push("color");
    if (!Number(anio.value)) faltan.push("año");
    if (!(Number(costo.value) > 0)) faltan.push("costo diario");
    if (arrendadora.value.trim().length < 2) faltan.push("arrendadora");
    if (!tel.valor()) faltan.push("telefono del proveedor");
    if (faltan.length) {
      zonaError.replaceChildren(aviso(
        "Falta " + faltan.join(", ") + ". De un auto de renta no se sabe "
        + "nada despues: lo que no quede escrito hoy se pierde.", "alerta"));
      return;
    }
    zonaError.replaceChildren();
    guardar.disabled = true;
    try {
      await api.post(`/servicios/equipos/${equipo.id}/vehiculo-rentado`, {
        placa: placa.value.trim(),
        categoria_id: Number(selCategoria.value),
        color: color.value.trim(),
        marca_modelo: marca.value.trim(),
        modelo_anio: Number(anio.value),
        costo_diario: Number(costo.value),
        arrendadora: arrendadora.value.trim(),
        arrendadora_telefono: tel.valor(),
        motivo_renta: selMotivo.value,
      });
      location.reload();
    } catch (err) {
      zonaError.replaceChildren(aviso(err.message, "grave"));
      guardar.disabled = false;
    }
  });

  return h("div", { clase: "tarjeta lisa", style: "margin-top:8px" },
    h("h4", { style: "margin:0 0 2px" }, "Auto rentado"),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      "Se renta para este servicio y se devuelve al terminarlo. Queda "
      + "marcado como rentado y no se le ofrece a ningun otro servicio. "
      + "El costo diario entra a la rentabilidad."),
    h("div", { clase: "rejilla dos" },
      campo("Placas", placa),
      campo("Categoria de unidad", selCategoria),
      campo("Marca y modelo", marca),
      campo("Color", color),
      campo("Año", anio),
      campo("Costo diario de la renta", costo),
      campo("Arrendadora", arrendadora),
      campo("Telefono del proveedor", tel),
      campo("Motivo del subarrendo", selMotivo)),
    zonaError,
    h("div", { clase: "acciones", style: "margin-top:10px" }, guardar));
}


/* -------------------------------------------- el dia: punto y agenda */

/* Todo lo del dia en un solo lugar: donde arranca y que se hace. Es la
   misma informacion —la actividad de ese dia— y verla partida en dos
   botones obligaba a abrir y cerrar para armar una idea completa. */
async function abrirDia(zona, jornada, cual = {}) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, "Abriendo el dia…"));

  /* El dia se lee en el orden en que ocurre: donde arranca y a que hora,
     luego lo que se hace, y al final el vuelo con el que se va. Por eso
     el vuelo de salida va despues de la agenda y el de llegada antes:
     uno cierra el dia y el otro lo abre. */
  const punto = bloqueOrigen(jornada, cual);
  const caja = h("div", { clase: "tarjeta lisa" }, punto.nodo);
  if (!cual.ultimo || cual.primero) caja.append(punto.guardar);
  zona.replaceChildren(caja);

  // La agenda se pide al servidor: se agrega en cuanto llega, sin dejar
  // esperando lo del punto, que ya se puede leer.
  caja.append(await bloqueAgenda(jornada));

  if (cual.ultimo && !cual.primero) {
    caja.append(punto.vueloDeSalida, punto.guardar);
  }
}

function bloqueOrigen(jornada, cual = {}) {
  /* Solo el primer dia recibe al ejecutivo y solo el ultimo lo despide,
     y ni siquiera siempre: el aeropuerto es el caso mas comun, no el
     unico. Un servicio puede arrancar en el hotel, en la oficina o en
     una casa, y entonces no hay vuelo que capturar. Por eso la casilla
     manda, y se marca sola cuando el dia ya trae vuelo o cuando Google
     dice que el lugar elegido es un aeropuerto. */
  const puedeVolar = cual.primero || cual.ultimo;
  const tipoVuelo = cual.primero ? "llegada" : "salida";
  const traeVuelo = !!(jornada.vuelo_numero || jornada.vuelo_aerolinea
                       || jornada.vuelo_hora);

  /* El punto se busca en Google y de ahi salen sus coordenadas: de ellas
     dependen la geocerca del conductor y los hospitales de la hoja. */
  const lugar = buscadorDeLugar({
    paisId: () => cual.paisId || "",
    alDetectarAeropuerto: () => {
      if (puedeVolar && !enAeropuerto.checked) {
        enAeropuerto.checked = true;
        verVuelo();
        mensaje("Es un aeropuerto: captura el vuelo");
      }
    },
    valores: { direccion: jornada.origen_direccion,
               lat: jornada.origen_lat, lon: jornada.origen_lon,
               metros: jornada.geocerca_metros,
               aeropuerto: jornada.origen_aeropuerto,
               googleAeropuerto: jornada.origen_google_aeropuerto },
  });

  /* La casilla no es una etiqueta: abre la geocerca de 500 m a 2 km. En
     un hotel eso deja al conductor marcando su llegada desde cuatro
     cuadras antes. Cuando Google dice que el lugar no es aeropuerto, se
     pregunta antes y la respuesta viaja al servidor: hay terminales
     privadas que si lo son, pero eso se decide a proposito. */
  let forzadoAeropuerto = false;
  const enAeropuerto = h("input", { type: "checkbox",
    checked: traeVuelo || !!jornada.origen_aeropuerto,
    onchange: () => {
      if (enAeropuerto.checked && lugar.segunGoogle() === false) {
        const ok = confirm(
          "Google dice que ese lugar no es un aeropuerto.\n\n"
          + "Marcarlo como tal abre la geocerca de 500 m a 2 km, y el "
          + "conductor podria marcar su llegada desde lejos.\n\n"
          + "Confirma solo si de verdad es un aeropuerto: una terminal "
          + "privada o una pista chica que Google no reconoce.");
        if (!ok) { enAeropuerto.checked = false; return; }
        forzadoAeropuerto = true;
      }
      lugar.decirAeropuerto(enAeropuerto.checked);
      verVuelo();
    } });
  const aerolinea = entrada("vuelo_aerolinea",
                            { value: jornada.vuelo_aerolinea || "" });
  const numero = entrada("vuelo_numero", { value: jornada.vuelo_numero || "",
                                           "data-mayusculas": "" });
  const horaVuelo = h("input", { type: "time",
    value: jornada.vuelo_hora ? String(jornada.vuelo_hora).slice(11, 16) : "" });
  const procedencia = entrada("vuelo_origen",
                              { value: jornada.vuelo_origen || "",
                                placeholder: "Frankfurt" });

  const bloqueVuelo = h("div", { hidden: !traeVuelo },
    h("h4", { style: "margin-top:10px" },
      cual.primero ? "Vuelo de llegada del ejecutivo principal"
                   : "Vuelo de salida del ejecutivo principal"),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      cual.primero
        ? "El equipo se presenta 45 minutos antes de que aterrice, y esa "
          + "hora queda como su presentacion."
        : "El ultimo dia termina cuando el ejecutivo aborda."),
    h("div", { clase: "rejilla tres" },
      campo("Aerolinea", aerolinea),
      campo("Numero de vuelo", numero),
      campo("Hora", horaVuelo)),
    campo(cual.primero ? "Procedencia" : "Destino", procedencia));

  /* La hora a la que el equipo se presenta ese dia. Vive aqui, junto al
     punto: son la misma pregunta —donde y a que hora arranca— y de ella
     salen los empalmes, las horas extra y lo que se lee en la tabla de
     dias. Cuando el dia arranca contra un vuelo la fija el vuelo, 45
     minutos antes de que aterrice, y entonces no se captura a mano. */
  const heredada = (jornada.inicio_programado || "").slice(11, 16);
  const presentacion = h("input", { type: "time",
    value: jornada.hora_confirmada ? heredada : "" });
  const notaHora = h("div", { clase: "chico gris" });

  function verHora() {
    const laPoneElVuelo = cual.primero && enAeropuerto.checked
                          && !!horaVuelo.value;
    presentacion.disabled = laPoneElVuelo;
    notaHora.textContent = laPoneElVuelo
      ? "La fija el vuelo al guardar: 45 minutos antes de que aterrice."
      : (jornada.hora_confirmada
          ? ""
          : `Desconocida. Mientras tanto el dia arranca a las ${heredada}, `
            + "heredada del dia 1.");
  }
  horaVuelo.addEventListener("input", verHora);

  function verVuelo() { bloqueVuelo.hidden = !enAeropuerto.checked; verHora(); }
  verHora();

  const casillaAeropuerto = puedeVolar
    ? h("label", { clase: "casilla", style: "margin-top:12px" }, enAeropuerto,
        h("span", {}, cual.primero
          ? "El servicio arranca en un aeropuerto"
          : "El servicio termina en un aeropuerto"))
    : "";

  const guardar = h("button", { type: "button", onclick: async (e) => {
    const punto = lugar.valor();
    if (!punto.direccion) {
      return mensaje("Escribe donde arranca el dia", "alerta");
    }
    if ((punto.lat || punto.lon) && !(punto.lat && punto.lon)) {
      return mensaje("El pin necesita latitud y longitud, o ninguna de las dos",
                     "alerta");
    }
    e.target.disabled = true;
    try {
      /* Se manda todo lo del punto, incluso vacio: dejar la latitud en
         blanco es quitar el pin, no "no lo toques". */
      await api.patch(`/operacion/jornadas/${jornada.id}/origen`, {
        origen_direccion: punto.direccion,
        origen_lat: punto.lat, origen_lon: punto.lon,
        geocerca_metros: punto.metros,
        origen_aeropuerto: enAeropuerto.checked,
        origen_google_aeropuerto: punto.googleAeropuerto,
        forzar_aeropuerto: forzadoAeropuerto,
      });

      if (puedeVolar) {
        const vuela = enAeropuerto.checked;
        // Quitarle el aeropuerto al dia borra su vuelo: si no, la hoja
        // seguiria anunciando un vuelo que ya no existe.
        await api.patch(`/operacion/jornadas/${jornada.id}/vuelo`, {
          vuelo_aerolinea: vuela ? (aerolinea.value.trim() || null) : null,
          vuelo_numero: vuela ? (numero.value.trim() || null) : null,
          vuelo_origen: vuela ? (procedencia.value.trim() || null) : null,
          vuelo_tipo: vuela && horaVuelo.value ? tipoVuelo : null,
          vuelo_hora: vuela && horaVuelo.value
            ? `${jornada.fecha}T${horaVuelo.value}:00` : null,
        });
      }

      /* La hora se manda despues del vuelo: cuando el vuelo la fija, la
         del vuelo es la buena y no la que quedo escrita en el campo. */
      const laPoneElVuelo = cual.primero && enAeropuerto.checked
                            && !!horaVuelo.value;
      if (!laPoneElVuelo && presentacion.value) {
        await api.patch(`/servicios/jornadas/${jornada.id}`,
                        { hora_presentacion: `${presentacion.value}:00` });
      }

      mensaje(cual.primero ? "Meet and greet guardado"
                           : "Punto de origen guardado");
      // Se recarga para que la pantalla y el task sheet muestren lo
      // guardado, y no lo que se traia de antes.
      setTimeout(() => location.reload(), 700);
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  } }, "Guardar");

  /* El vuelo de salida se entrega aparte: lo coloca el dia, despues de
     la agenda, porque es con lo que el dia termina. */
  const vueloDeSalida = (cual.ultimo && !cual.primero)
    ? h("div", {}, casillaAeropuerto, bloqueVuelo) : "";

  const nodo = h("div", {},
    cual.primero
      ? h("div", { clase: "destacado" },
          h("h4", {}, "Meet and greet"),
          h("div", { clase: "nota" },
            "El primer contacto con el ejecutivo principal y el dato mas "
            + "importante del task sheet: donde arranca el servicio. Es uno "
            + "solo por equipo."))
      : h("p", { clase: "gris chico", style: "margin:0 0 12px" },
          "Donde se recoge al ejecutivo este dia: casi siempre el hotel. "
          + "De aqui salen la geocerca del conductor y los hospitales "
          + "cercanos de la hoja."),

    h("div", { clase: "punto-inicio" },
      h("div", {},
        campo(cual.primero ? "Lugar exacto del encuentro"
                           : "Punto de origen del dia", lugar.direccion),
        lugar.resultados,
        /* Escribir la direccion no fija el punto: hay que elegirla de la
           lista para que Google devuelva sus coordenadas. Sin ellas no
           hay geocerca ni hospitales, y el task sheet no se publica. */
        jornada.origen_direccion && !jornada.origen_lat
          ? aviso("Esta direccion no tiene pin. Eligela de la lista del "
                  + "buscador, o escribe las coordenadas abajo: sin ellas "
                  + "no hay geocerca ni hospitales cercanos.", "alerta")
          : ""),
      lugar.cajaMapa),

    // Solo el de llegada va aqui: abre el dia. El de salida lo cierra.
    cual.primero ? h("div", {}, casillaAeropuerto, bloqueVuelo) : "",

    h("h4", { clase: "grupo" }, "Hora de presentacion"),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      "A que hora tiene que estar el equipo en ese punto. Es la hora con "
      + "la que se revisan empalmes y horas extra, y la que sale en la "
      + "tabla de dias."),
    h("div", { clase: "rejilla tres" },
      h("div", { clase: "campo" },
        h("label", {}, "Presentacion"), presentacion, notaHora)),

    h("details", { clase: "plegable" },
      h("summary", {}, "Ajustar el pin y el radio de la geocerca"),
      h("p", { clase: "gris chico" },
        "El pin se llena solo al elegir el lugar en el buscador. El radio "
        + "es el circulo alrededor de ese mismo pin que el conductor tiene "
        + "que pisar para marcar su llegada."),
      h("div", { clase: "rejilla tres" },
        campo("Latitud", lugar.lat),
        campo("Longitud", lugar.lon),
        campo("Radio en metros", lugar.metros))),

    "");

  return { nodo, vueloDeSalida,
           guardar: h("div", { clase: "acciones", style: "margin-top:12px" },
                      guardar) };
}

/* ------------------------------------------------------------ agenda */

async function bloqueAgenda(jornada) {
  let paradas = [];
  try {
    paradas = await api.get(
      `/operacion/jornadas/${jornada.id}/agenda/paradas`);
  } catch (err) { return aviso(err.message, "grave"); }

  /* La agenda del dia llega por partes y se mueve sobre la marcha: se
     cae una reunion, se recorre la comida, se agrega una escala. Por eso
     cada parada se guarda sola y se puede corregir o quitar sin tocar
     las demas.

     Dos datos y ya: la hora y a donde se va. El lugar y su direccion van
     juntos porque asi los dicta el cliente y asi los lee el conductor:
     "Oficinas Reforma 250, piso 12". */
  const cuerpo = h("tbody");

  const pintar = () => {
    cuerpo.replaceChildren();
    if (!paradas.length) {
      cuerpo.append(h("tr", {}, h("td", { colspan: "3", clase: "gris chico" },
        "Sin paradas capturadas. La agenda es opcional: hay clientes que no "
        + "la comparten y el dia se va armando sobre la marcha.")));
    }
    for (const parada of paradas) cuerpo.append(renglon(parada));
  };

  /* Lo capturado antes en dos campos se sigue leyendo en uno solo. */
  const comoTexto = (p) => [p.lugar, p.direccion].filter(Boolean).join(" — ");

  function renglon(parada) {
    const hora_ = h("input", { type: "time", value: parada.hora || "" });
    const lugar = entrada("lugar", { value: comoTexto(parada),
      placeholder: "Oficinas corporativas, Reforma 250 piso 12" });

    const guardar = async () => {
      if (!lugar.value.trim()) return mensaje("La parada necesita un lugar",
                                              "alerta");
      try {
        const r = await api.patch(`/operacion/paradas/${parada.id}`, {
          hora: hora_.value ? `${hora_.value}:00` : null,
          lugar: lugar.value.trim(),
          direccion: null,
        });
        Object.assign(parada, r);
        mensaje("Parada actualizada");
      } catch (err) { mensaje(err.message, "grave"); }
    };
    hora_.addEventListener("change", guardar);
    lugar.addEventListener("change", guardar);

    const quitar = h("button", { clase: "claro chico", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          await api.borrar(`/operacion/paradas/${parada.id}`);
          paradas = paradas.filter(p => p.id !== parada.id);
          pintar();
          mensaje("Parada quitada");
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, "Quitar");

    return h("tr", {},
      h("td", { clase: "col-hora" }, hora_),
      h("td", {}, lugar),
      h("td", {}, quitar));
  }

  /* --- la parada nueva */
  const nuevaHora = h("input", { type: "time" });
  const nuevoLugar = entrada("lugar", {
    placeholder: "Oficinas corporativas, Reforma 250 piso 12" });

  const agregar = h("button", { type: "button", onclick: async (e) => {
    if (!nuevoLugar.value.trim()) {
      return mensaje("Escribe a donde va esa parada", "alerta");
    }
    e.target.disabled = true;
    try {
      const parada = await api.post(
        `/operacion/jornadas/${jornada.id}/agenda/paradas`, {
          hora: nuevaHora.value ? `${nuevaHora.value}:00` : null,
          lugar: nuevoLugar.value.trim(),
        });
      // En orden de reloj; las que no tienen hora, al final.
      paradas.push(parada);
      paradas.sort((a, b) => ((a.hora || "99") < (b.hora || "99") ? -1 : 1));
      pintar();
      nuevaHora.value = "";
      nuevoLugar.value = "";
      nuevoLugar.focus();
      mensaje("Parada agregada");
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  } }, "Agregar parada");

  pintar();

  return h("div", {},
    h("h4", { clase: "grupo" }, "Agenda del dia"),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      "Cada parada se guarda sola: se corrige o se quita sin tocar las "
      + "demas, porque la agenda se mueve durante el dia. Las paradas sin "
      + "hora se imprimen al final, como pendientes de confirmar."),

    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", { clase: "col-hora" }, "Hora"),
        h("th", {}, "Lugar y direccion"), h("th", {}, ""))),
      cuerpo),

    h("div", { clase: "rejilla dos", style: "margin-top:14px" },
      campo("Hora", nuevaHora),
      campo("Lugar y direccion", nuevoLugar)),
    h("div", { clase: "acciones", style: "margin-top:10px" }, agregar));
}

/* ------------------------------------------------------------ hospedaje */

/* Uno por equipo y nada mas. Cada equipo cuida a su ejecutivo principal
   y ese ejecutivo duerme en un hotel; poder cargar dos dejaba la duda de
   a cual de los dos llegar, que es justo lo que la hoja resuelve. Por
   eso vive dentro del equipo y no al final del servicio, y por eso el
   formulario corrige el hotel que hay en vez de agregar otro. */

async function bloqueHotel(servicio, equipo, cat) {
  const caja = h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" });
  await pintarHotel(caja, servicio, equipo, cat);
  return caja;
}

async function pintarHotel(caja, servicio, equipo, cat) {
  /* La lista es la de la ciudad del equipo: en Monterrey no se ofrecen
     los hoteles de Ciudad de Mexico. Y solo los que se han ocupado en
     los ultimos tres meses, para no buscar entre cien los cuatro de
     siempre. Se pide aparte del catalogo general porque depende del
     equipo, no de la sesion. */
  const ciudad = equipo.plaza_id || servicio.plaza_id || "";
  const [estancias, hoteles] = await Promise.all([
    api.get(`/hospedajes/equipo/${equipo.id}`).catch(() => []),
    api.get(`/catalogos/hoteles?plaza_id=${ciudad}`).catch(() => []),
  ]);
  const actual = estancias[0] || null;
  const repintar = () => pintarHotel(caja, servicio, equipo, cat);

  const cabeza = h("div", {},
    h("h4", { style: "margin:0 0 2px" }, "Hotel del ejecutivo"),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      "Informativo: Centauro no reserva. Se captura para que el equipo "
      + "sepa a donde llegar y a que numero llamar, y sale al final de la "
      + "hoja con los hospitales mas cercanos. Es opcional, y es uno solo."));

  const ficha = h("div");
  if (actual) {
    ficha.append(h("div", { clase: "aviso", style: "margin:0 0 10px" },
      h("b", {}, actual.hotel),
      h("div", { clase: "gris chico" }, actual.direccion || "Sin direccion"),
      h("div", { clase: "chico num" }, actual.telefono || "Sin telefono"),
      h("div", { clase: "acciones", style: "margin-top:8px" },
        h("button", { clase: "claro chico", type: "button",
          onclick: async (e) => {
            e.target.disabled = true;
            try {
              await api.borrar(`/hospedajes/equipo/${equipo.id}`);
              await repintar();
            } catch (err) {
              mensaje(err.message, "grave"); e.target.disabled = false;
            }
          } }, "Quitar"))));
  }

  const nombreLibre = entrada("nombre_libre");
  const direccionLibre = entrada("direccion_libre");
  const telefonoLibre = entrada("telefono_libre", { type: "tel" });

  /* El hotel se busca en Google, igual que el punto de encuentro: de ahi
     salen su nombre, su direccion y su telefono tal como los tiene
     Google, sin dedazos. El telefono importa porque es al que llama el
     equipo si el ejecutivo no baja. */
  let buscadorHotel = null;
  let puesto = null;
  buscadorHotel = buscadorDeLugar({
    paisId: () => servicio.pais_id || "",
    filas: "2",
    /* Se engancha aqui y no al evento del recuadro: al elegir una
       sugerencia el texto se escribe por codigo, y eso no dispara el
       evento de cambio. Era la razon por la que el telefono no llegaba. */
    alCambiar: () => {
      const lugar = buscadorHotel && buscadorHotel.ultimo();
      if (!lugar) return;
      const firma = `${lugar.nombre}|${lugar.direccion}`;
      if (firma === puesto) return;      // no pisar lo que ya se corrigio
      puesto = firma;
      nombreLibre.value = lugar.nombre || "";
      direccionLibre.value = lugar.direccion || "";
      telefonoLibre.value = lugar.telefono || "";
      revisar();
      if (!lugar.telefono) {
        mensaje("Google no trae telefono de ese hotel. Capturalo a mano.",
                "alerta");
      }
    },
  });

  const selHotel = lista("hotel_id",
    [{ valor: "", texto: hoteles.length ? "Del catalogo…"
                                        : "Sin hoteles usados en esta ciudad" },
     ...hoteles.map(x => ({ valor: x.id, texto: x.nombre }))]);

  /* El boton no existe hasta que hay un hotel que guardar. Un boton que
     esta ahi desde el principio y contesta "elige un hotel" es un viaje
     en falso: mas claro es que aparezca cuando ya hay algo que guardar. */
  const guardar = h("button", { clase: "chico", type: "submit" },
                    actual ? "Cambiar el hotel" : "Guardar hotel");
  const revisar = () => {
    guardar.hidden = !(selHotel.value || nombreLibre.value.trim());
  };
  revisar();
  for (const control of [selHotel, nombreLibre, direccionLibre]) {
    control.addEventListener("input", revisar);
    control.addEventListener("change", revisar);
  }

  const f = h("form", { onsubmit: async (ev) => {
    ev.preventDefault();
    const libre = nombreLibre.value.trim();
    if (!selHotel.value && !libre) {
      return mensaje("Elige un hotel del catalogo o busca el suyo en Google",
                     "alerta");
    }
    guardar.disabled = true;
    try {
      const punto = buscadorHotel.valor();
      await api.post("/hospedajes", {
        equipo_id: equipo.id,
        hotel_id: selHotel.value ? Number(selHotel.value) : null,
        nombre_libre: selHotel.value ? null : libre,
        direccion_libre: selHotel.value ? null
                         : (direccionLibre.value.trim() || null),
        telefono_libre: selHotel.value ? null
                        : (telefonoLibre.value.trim() || null),
        // El pin sirve para los hospitales cercanos el dia que el hotel
        // sea el punto de origen.
        hotel_lat: selHotel.value ? null : punto.lat,
        hotel_lon: selHotel.value ? null : punto.lon,
      });
      mensaje(actual ? "Hotel corregido" : "Hotel registrado");
      await repintar();
    } catch (err) { mensaje(err.message, "grave"); guardar.disabled = false; }
  }});

  f.append(campo("Hotel", selHotel),
    h("details", { clase: "plegable", open: actual ? null : "" },
      h("summary", {}, "Buscar el hotel en Google"),
      h("div", { clase: "punto-inicio" },
        h("div", {},
          campo(t("buscar_hotel"), buscadorHotel.direccion),
          buscadorHotel.resultados),
        buscadorHotel.cajaMapa),
      h("div", { clase: "rejilla tres" },
        campo("Nombre del hotel", nombreLibre),
        campo("Direccion", direccionLibre),
        campo("Telefono", telefonoLibre))),
    h("div", { clase: "acciones", style: "margin-top:10px" }, guardar));

  caja.replaceChildren(cabeza, ficha, f);
}

/* ------------------------------------------------------------ task sheet */

async function bloqueTaskSheet(servicio) {
  const caja = h("div", { clase: "tarjeta" }, h("h3", {}, "Task sheet"));
  let vista;
  try {
    vista = await api.get(`/task-sheets/servicio/${servicio.id}/vista-previa`);
  } catch (e) {
    caja.append(aviso(e.message, "alerta"));
    return caja;
  }

  if (vista.faltantes && vista.faltantes.length) {
    caja.append(aviso("Falta esto para poder publicarlo:", "alerta"));
    caja.append(h("ul", { clase: "chico" },
      ...vista.faltantes.map(x => h("li", {}, x))));
  } else {
    caja.append(aviso("Listo para publicar.", "ok"));
  }

  caja.append(bloqueSenal(servicio, vista));

  /* La firma del consultor sobre su propia asignacion: que el sistema
     vea gente y unidad todos los dias no quiere decir que el ya haya
     terminado. Es lo que la central espera para trabajar el servicio. */
  const confirmar = h("button", { onclick: async (e) => {
    e.target.disabled = true;
    try {
      const r = await api.post(
        `/servicios/${servicio.id}/confirmar-asignacion`);
      mensaje(`${r.folio}: ${r.sigue}`);
      setTimeout(() => location.reload(), 900);
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  } }, t("confirmar_ts"));

  const liberado = !!servicio.asignacion_confirmada_en;

  caja.append(
    liberado
      ? aviso(`${t("confirmada_el")} `
              + `${fecha(servicio.asignacion_confirmada_en)}. `
              + t("ts_liberado"), "ok")
      : h("div", { clase: "acciones", style: "margin-top:14px" },
          confirmar,
          h("span", { clase: "gris chico" }, t("confirmar_nota"))),

    /* El TS lo manda el consultor por correo, sobre la misma cadena
       donde el cliente pidio y cotizo el servicio. El sistema solo lo
       entrega al dia: cada boton arma la hoja con lo ultimo capturado. */
    h("h4", { clase: "grupo" }, t("ts_titulo")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      liberado ? t("ts_al_dia") : t("ts_sin_liberar")),
    /* Un PDF por idioma, siempre los tres: el TS lo lee el ejecutivo y
       el idioma es el que el prefiera, no el de quien opera la consola.
       Ver es otra cosa: eso lo lee el consultor, y sale en el idioma en
       que tenga puesta su consola. */
    h("div", { clase: "acciones" },
      ...IDIOMAS.map(i => h("button", { disabled: !liberado || undefined,
        title: `${t("ts_pdf")} · ${i.nombre}`,
        onclick: () => abrirHoja(servicio, i.codigo, true) },
        `${i.bandera} ${t("ts_pdf")} · ${i.nombre}`))),
    h("div", { clase: "acciones", style: "margin-top:8px" },
      h("button", { clase: "claro chico", disabled: !liberado || undefined,
        onclick: () => abrirHoja(servicio, idioma()) }, t("ts_ver"))));

  return caja;
}
/* Abre la hoja en otra pestaña y, si se pide, la manda a imprimir: ahi
   se elige "Guardar como PDF". Se hace asi y no con un PDF armado en el
   servidor porque la hoja ya esta diseñada para imprimirse, y lo que el
   ejecutivo recibe es exactamente lo que se ve en pantalla.

   La hoja se pide con la sesion puesta y se escribe en la pestaña nueva.
   Abrirla por su direccion no funciona: el navegador no lleva el token
   en una pestaña nueva y el servidor contesta "se requiere iniciar
   sesion". Y ponerlo en la direccion tampoco es opcion: el token se
   quedaria en el historial y en cualquier bitacora por donde pase. */
async function abrirHoja(servicio, idioma, imprimir = false) {
  const w = window.open("", "_blank");
  if (!w) return mensaje("El navegador bloqueo la ventana de la hoja", "alerta");
  w.document.write('<p style="font:14px system-ui;padding:20px">'
                   + "Preparando la hoja…</p>");
  try {
    const html = await api.get(
      `/task-sheets/servicio/${servicio.id}/hoja?idioma=${idioma}`,
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

/* ----------------------------------------------------------- la senal */

/* Lo que el equipo levanta cuando el ejecutivo sale del filtro. Puede ser
   una palabra (su apellido) o una imagen (el logo del cliente, que se
   reconoce de mas lejos). Se imprime a pagina completa: es una o la otra,
   nunca las dos, asi que al guardar una se quita la que estaba. */
function bloqueSenal(servicio, vista) {
  const actual = vista.senal || {};
  const zona = h("div", { style: "margin-top:16px" });

  const comoTexto = h("input", { type: "radio", name: "senal_como" });
  const comoImagen = h("input", { type: "radio", name: "senal_como" });
  if (actual.imagen) comoImagen.checked = true; else comoTexto.checked = true;

  /* La senal se imprime tal cual se escribe: si el consultor la quiere
     en mayusculas, asi se queda. */
  const texto = entrada("texto", {
    placeholder: "MR. BROOKS", "data-crudo": "",
    value: actual.texto || "" });

  const archivo = h("input", { type: "file", accept:
    "image/png,image/jpeg,image/webp,image/svg+xml" });
  const previa = h("img", { clase: "senal-previa",
                            src: actual.imagen || "",
                            hidden: !actual.imagen });
  archivo.addEventListener("change", () => {
    const f = archivo.files && archivo.files[0];
    if (!f) return;
    previa.src = URL.createObjectURL(f);
    previa.hidden = false;
  });

  const cajaTexto = h("div", {}, campo("Palabra o apellido", texto));
  const cajaImagen = h("div", {},
    campo("Archivo", archivo),
    h("div", { clase: "chico gris" },
      "PNG, JPG, WebP o SVG, hasta 3 MB. Se guarda dentro de la hoja, "
      + "asi que se imprime y se manda sin depender de internet."),
    previa);

  const acomodar = () => {
    cajaTexto.hidden = !comoTexto.checked;
    cajaImagen.hidden = !comoImagen.checked;
  };
  comoTexto.addEventListener("change", acomodar);
  comoImagen.addEventListener("change", acomodar);
  acomodar();

  const guardar = h("button", { clase: "claro chico", onclick: async (e) => {
    e.preventDefault();
    const f = archivo.files && archivo.files[0];
    if (comoTexto.checked && !texto.value.trim())
      return mensaje("Escribe la palabra de la senal", "alerta");
    if (comoImagen.checked && !f && !actual.imagen)
      return mensaje("Elige la imagen de la senal", "alerta");

    e.target.disabled = true;
    try {
      // Se limpia primero: la hoja imprime una sola senal, no las dos.
      await api.borrar(`/servicios/${servicio.id}/senal`);
      if (comoTexto.checked) {
        await api.put(`/servicios/${servicio.id}/senal`,
                      { texto: texto.value.trim() });
      } else if (f) {
        await api.subir(`/servicios/${servicio.id}/senal/imagen`, f);
      } else {
        await api.put(`/servicios/${servicio.id}/senal`,
                      { imagen: actual.imagen });
      }
      mensaje("Senal guardada. Vuelve a publicar el task sheet para que salga.");
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  } }, "Guardar senal");

  const quitar = h("button", { clase: "claro chico", onclick: async (e) => {
    e.preventDefault();
    e.target.disabled = true;
    try {
      await api.borrar(`/servicios/${servicio.id}/senal`);
      texto.value = "";
      previa.hidden = true;
      mensaje("Senal quitada");
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  } }, "Quitar senal");

  zona.append(
    h("h4", { clase: "grupo" }, "Senal de identificacion"),
    h("div", { clase: "chico gris", style: "margin-bottom:8px" },
      "Se imprime en una hoja aparte para que el equipo la muestre en el "
      + "filtro o en el lobby. Es una palabra o una imagen, no las dos."),
    h("div", { clase: "acciones", style: "margin-bottom:6px" },
      h("label", { clase: "casilla" }, comoTexto, "Texto"),
      h("label", { clase: "casilla" }, comoImagen, "Imagen")),
    cajaTexto, cajaImagen,
    h("div", { clase: "acciones", style: "margin-top:10px" },
      guardar,
      (actual.texto || actual.imagen) ? quitar : ""));
  return zona;
}
/* ------------------------------------------------------------ a bordo */

/* En que unidad va cada quien. Se guarda al momento de elegirla: es un
   dato que cambia en la junta de arranque, con el telefono en la mano,
   y nadie va a buscar un boton de guardar. */
function selectorAbordo(equipo, persona, vehiculos) {
  const sel = lista("abordo", [
    { valor: "", texto: "¿En que unidad va?" },
    ...vehiculos.map(v => ({
      valor: v.vehiculo_id,
      texto: `${v.placa} · ${v.unidad || "unidad"}`,
    })),
  ], { clase: "chico" });
  sel.value = persona.vehiculo_id || "";

  sel.addEventListener("change", async () => {
    sel.disabled = true;
    try {
      const r = await api.patch(
        `/servicios/equipos/${equipo.id}/personal/${persona.persona_id}/unidad`,
        { vehiculo_id: sel.value ? Number(sel.value) : null });
      mensaje(r.placa ? `${persona.nombre} va en ${r.placa}`
                      : `${persona.nombre} sin unidad`);
    } catch (err) {
      mensaje(err.message, "grave");
      sel.value = persona.vehiculo_id || "";
    }
    sel.disabled = false;
  });

  return h("div", { clase: "abordo" },
    h("span", { clase: "chico gris" }, "Aborda"), sel);
}
/* La ciudad del equipo, ya resuelta por el servidor: la suya o la del
   servicio. */
function ciudadDe(equipo, cat) {
  const ciudad = cat.plazas.find(p => p.id === equipo.ciudad_id);
  return ciudad ? ciudad.nombre : "—";
}

/* --------------------------------------------------------- dias del equipo */

/* El mismo recuadro del alta, siempre a la vista: el servicio se sigue
   armando despues de darlo de alta. La fecha, la modalidad y la hora del
   dia 1 se corrigen aqui, y la agenda de cada dia se sube aqui. */
function tablaDias(servicio, equipo, cat) {
  const cuerpo = h("tbody");
  const dias = [...equipo.jornadas].sort((a, b) => (a.fecha < b.fecha ? -1 : 1));

  dias.forEach((jornada, i) => {
    const fechaDia = h("input", { type: "date", value: jornada.fecha });
    const modalidad = lista("modalidad", opcionesModalidad(cat, jornada));
    modalidad.value = jornada.modalidad_id;
    /* La hora se lee aqui y se captura adentro, junto al punto del dia:
       son la misma pregunta y tenerla en dos lugares confundia. La que
       nadie ha confirmado se dice desconocida en vez de aparentar dato:
       con esa hora se calculan empalmes y horas extra. */
    const heredada = (jornada.inicio_programado || "").slice(11, 16);
    const hora_ = jornada.hora_confirmada
      ? h("div", { clase: "num", style: "font-weight:600" }, heredada)
      : h("div", { clase: "chico", style: "color:#b8860b" }, "Desconocida");
    const nota = h("div", { clase: "chico gris" },
      jornada.hora_confirmada ? "" : `arranca ${heredada}`);

    const guardar = async (cambios) => {
      try {
        const r = await api.patch(`/servicios/jornadas/${jornada.id}`, cambios);
        mensaje(`Dia ${fecha(r.fecha)} actualizado`);
        if (r.estatus_servicio) setTimeout(() => location.reload(), 600);
      } catch (err) { mensaje(err.message, "grave"); }
    };

    fechaDia.addEventListener("change",
      () => guardar({ fecha: fechaDia.value }));
    modalidad.addEventListener("change",
      () => guardar({ modalidad_id: Number(modalidad.value) }));

    /* Un solo boton por dia: donde arranca y que se hace son la misma
       cosa —la actividad de ese dia— y separarlos obligaba a abrir y
       cerrar dos paneles para armar una idea completa.

       El meet and greet es del dia 1 y de nadie mas: ahi se conoce al
       ejecutivo principal. Los demas dias tienen punto de origen, que es
       donde se le recoge esa mañana. */
    const zonaDia = h("td", { colspan: "6", clase: "caja-agenda", hidden: true });
    const filaDia = h("tr", { hidden: true }, zonaDia);

    const esUltimo = i === dias.length - 1;
    const nombreDia = i === 0 ? "Meet and greet y agenda"
                              : "Punto de origen y agenda";
    const botonDia = h("button", { clase: "claro chico", type: "button",
      onclick: () => {
        const abierta = !filaDia.hidden;
        filaDia.hidden = abierta;
        zonaDia.hidden = abierta;
        botonDia.textContent = abierta ? nombreDia : "Cerrar el dia";
        if (!abierta) {
          abrirDia(zonaDia, jornada, { primero: i === 0, ultimo: esUltimo,
                                       paisId: servicio.pais_id });
        }
      } }, nombreDia);

    const quitar = h("button", { clase: "claro chico", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          await api.borrar(`/servicios/jornadas/${jornada.id}`);
          mensaje("Dia quitado");
          location.reload();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, "Quitar");

    cuerpo.append(
      h("tr", {},
        h("td", { clase: "gris chico" },
          i === 0 ? "Dia 1 · inicio" : `Dia ${i + 1}`),
        h("td", {}, fechaDia),
        h("td", {}, modalidad),
        h("td", { clase: "col-hora" }, hora_, nota, botonDia),
        h("td", { clase: "chico gris" }, etiqueta(jornada.estatus || "")),
        h("td", {}, quitar)),
      filaDia);
  });

  /* El dia que se agrega casi siempre es el siguiente al ultimo: el
     cliente extiende el servicio un dia mas. Se propone esa fecha en vez
     de dejar el campo vacio o en hoy, que cae antes del servicio. */
  const ultimo = dias.length ? dias[dias.length - 1].fecha : null;
  const siguiente = ultimo
    ? new Date(new Date(`${ultimo}T00:00:00`).getTime() + 86400000)
        .toISOString().slice(0, 10)
    : "";
  const nuevaFecha = h("input", { type: "date", value: siguiente });
  const nuevaModalidad = lista("modalidad", opcionesModalidad(cat));
  const agregar = h("button", { clase: "claro chico", type: "button",
    onclick: async (e) => {
      if (!nuevaFecha.value) return mensaje("Elige la fecha del dia", "alerta");
      e.target.disabled = true;
      try {
        await api.post(`/servicios/equipos/${equipo.id}/jornadas`, {
          fecha: nuevaFecha.value,
          modalidad_id: Number(nuevaModalidad.value),
        });
        mensaje("Dia agregado");
        location.reload();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, "Agregar dia");

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" },
    h("h4", { style: "margin:0 0 2px" }, "Dias de servicio"),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      "Se siguen moviendo mientras el servicio se arma. La hora de "
      + "presentacion es la del dia 1; los demas dias arrancan con su agenda."),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, ""), h("th", {}, "Fecha"), h("th", {}, "Modalidad"),
        h("th", {}, "Presentacion y actividad"), h("th", {}, "Estatus"),
        h("th", {}, ""))),
      cuerpo),
    h("div", { clase: "acciones", style: "margin-top:12px" },
      nuevaFecha, nuevaModalidad, agregar));
}

/* Las modalidades del pais del servicio. La del dia que se esta viendo
   entra siempre, aunque sea de otro pais: no se le cambia sola. */
function opcionesModalidad(cat, jornada = null) {
  const suya = jornada
    ? cat.modalidades.find(m => m.id === jornada.modalidad_id) : null;
  const pais = suya ? suya.pais_id : (cat.modalidades[0] || {}).pais_id;
  const NOMBRE = { full_day: "Dia completo", medio_dia: "Medio dia",
                   transfer: "Transfer" };
  return cat.modalidades
    .filter(m => m.pais_id === pais)
    .map(m => ({ valor: m.id,
                 texto: `${NOMBRE[m.codigo] || m.codigo} · ${Number(m.horas)} h` }));
}

/* ----------------------------------------------------- viaticos */

/* El consultor reparte dinero pensando en personas, no en jornadas: "a
   Ramiro le deposito tres mil por los tres dias" es una sola decision y
   un solo deposito. Por eso aqui hay un renglon por persona y un solo
   campo, aunque por dentro el viatico siga viviendo dia por dia.

   La columna de estado es lo que mas se mira, asi que lleva un solo
   color por renglon: gris nadie ha dicho cuanto, azul ya se decidio,
   ambar finanzas lo tiene, verde el dinero ya esta con la persona. */

const SEMAFORO = {
  por_asignar: { texto: "Por asignar", tono: "" },
  asignado: { texto: "Listo para solicitar", tono: "info" },
  solicitado: { texto: "Con finanzas", tono: "alerta" },
  depositado: { texto: "Depositado", tono: "ok" },
};

const ESTADO_COMPRA = {
  solicitada: { texto: "Solicitada", tono: "info" },
  en_gestion: { texto: "Finanzas la esta gestionando", tono: "alerta" },
  confirmada: { texto: "Confirmada", tono: "ok" },
  rechazada: { texto: "No se pudo", tono: "grave" },
  cancelada: { texto: "Cancelada", tono: "" },
};

const TIPOS_COMPRA = [
  { valor: "vuelo", texto: "Vuelo" },
  { valor: "hospedaje", texto: "Hospedaje" },
  { valor: "transporte", texto: "Transporte (tren, autobus, renta)" },
  { valor: "otro", texto: "Otro" },
];

async function bloqueViaticos(equipo) {
  const caja = h("div");
  await pintarViaticos(caja, equipo);
  return caja;
}

async function pintarViaticos(caja, equipo) {
  caja.replaceChildren(h("div", { clase: "gris chico" }, "Viaticos…"));
  let datos;
  try {
    datos = await api.get(`/viaticos/equipos/${equipo.id}`);
  } catch (err) {
    return caja.replaceChildren(aviso(err.message, "grave"));
  }
  // Sin gente asignada no hay a quien depositarle: el apartado no existe.
  if (!datos.personal.length) return caja.replaceChildren();

  const moneda = datos.moneda || "MXN";
  const repintar = () => pintarViaticos(caja, equipo);

  const cuerpo = h("tbody");
  for (const p of datos.personal) cuerpo.append(
    renglonViatico(p, equipo, moneda, repintar));

  const porSolicitar = datos.personal.filter(
    p => p.estatus === "asignado").length;

  const pedirTodo = h("button", { clase: "chico", type: "button",
    disabled: porSolicitar ? null : "disabled",
    onclick: async (e) => {
      e.target.disabled = true;
      try {
        await api.post(`/viaticos/equipos/${equipo.id}/solicitar`, {});
        mensaje("Deposito solicitado a finanzas");
        await repintar();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } },
    porSolicitar ? `Solicitar deposito (${porSolicitar})`
                 : "Solicitar deposito");

  caja.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" },
    h("h4", { style: "margin:0 0 2px" }, "Viaticos"),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      "Un deposito por persona, por todos sus dias en el equipo. El "
      + "sistema propone segun el tabulador; el monto lo decide usted."),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, "Persona"),
        h("th", { style: "text-align:right" }, "Propone el sistema"),
        h("th", { style: "text-align:right" }, "Se deposita"),
        h("th", {}, "Estado"))),
      cuerpo),
    h("div", { clase: "acciones", style: "margin-top:10px" },
      pedirTodo,
      h("span", { clase: "chico" },
        h("b", {}, `Total ${dinero(datos.total_asignado, moneda)}`),
        Number(datos.total_depositado) > 0
          ? h("span", { clase: "verde" },
              ` · depositado ${dinero(datos.total_depositado, moneda)}`)
          : "",
        Number(datos.total_en_camino) > 0
          ? h("span", { clase: "ambar" },
              ` · con finanzas ${dinero(datos.total_en_camino, moneda)}`)
          : "",
        Number(datos.total_por_solicitar) > 0
          ? h("span", { clase: "gris" },
              ` · por solicitar ${dinero(datos.total_por_solicitar, moneda)}`)
          : "")),
    bloqueCompras(datos, equipo, moneda, repintar)));
}

function renglonViatico(p, equipo, moneda, repintar) {
  const est = SEMAFORO[p.estatus] || SEMAFORO.por_asignar;
  /* Un deposito no cierra la puerta al siguiente: el servicio se alarga,
     se cae un dia y se repone, o simplemente falto dinero. Cuando ya
     salio algo, el campo deja de ser "cuanto se le deposita" y pasa a
     ser "cuanto mas": lo que ya se fue no se reescribe. */
  const yaSalio = Number(p.depositado) > 0 || Number(p.en_camino) > 0;
  const ruta = yaSalio ? "persona/agregar" : "persona";

  /* En enteros: el viatico se entrega en efectivo o por transferencia y
     nadie anda partiendo pesos. Lo que se capture se sube al entero de
     arriba, del lado del servidor. */
  const monto = entrada("monto", {
    type: "number", step: "1", min: "0", clase: "num",
    style: "text-align:right; max-width:130px",
    value: !yaSalio && Number(p.asignado)
             ? String(Math.round(Number(p.asignado))) : "",
    placeholder: yaSalio ? "Otro deposito"
                         : String(Math.ceil(Number(p.propuesto))),
  });

  const guardar = async () => {
    const valor = Number(monto.value);
    if (!(valor >= 0) || monto.value === "") return;
    if (!yaSalio && valor === Number(p.asignado)) return;
    monto.disabled = true;
    try {
      await api.post(`/viaticos/equipos/${equipo.id}/${ruta}`,
                     { persona_id: p.persona_id, monto: valor });
      await repintar();
    } catch (err) { mensaje(err.message, "grave"); monto.disabled = false; }
  };
  monto.addEventListener("change", guardar);

  /* Lo mas comun es aceptar lo que propone el tabulador. Que eso cueste
     teclear el numero a mano invita a equivocarse. El boton lleva el
     monto encima: "Usar" a secas no dice usar que. */
  const propuesto = Math.ceil(Number(p.propuesto));
  const usar = (yaSalio || !propuesto) ? "" : h("button", {
    clase: "claro chico", type: "button",
    title: "Deposita lo que propone el tabulador para sus dias",
    onclick: () => { monto.value = String(propuesto); guardar(); } },
    `Usar ${dinero(propuesto, moneda)}`);

  /* Debajo de la cantidad, en que va el dinero. Con dos o tres depositos
     encima, "asignado 2,900" solo no dice si ya salio o falta pedirlo, y
     esa es justo la pregunta del consultor. */
  const linea = (texto, valor, clase = "gris") =>
    Number(valor) > 0
      ? h("div", { clase: `chico ${clase}` },
          `${texto} ${dinero(valor, moneda)}`)
      : "";
  const desglose = h("div", { style: "margin-top:4px; text-align:right" },
    linea("Depositado", p.depositado, "verde"),
    linea("Con finanzas", p.en_camino, "ambar"),
    linea("Por solicitar", p.por_solicitar),
    Number(p.asignado) > 0
      ? h("div", { clase: "chico" },
          h("b", {}, `Total ${dinero(p.asignado, moneda)}`))
      : "");

  /* Mientras el dinero no salga, el consultor puede echarse para atras:
     se cae un dia, cambia la gente o se capturo mal el monto. Sin esta
     salida la unica forma de corregir era depositar de mas y andar
     persiguiendo la devolucion. Ya depositado ya no aparece: eso se
     devuelve, no se cancela. */
  const cancelar = p.estatus !== "solicitado" ? "" :
    h("button", { clase: "claro chico", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          await api.post(`/viaticos/equipos/${equipo.id}/cancelar-solicitud`,
                         { persona_id: p.persona_id });
          mensaje("Solicitud cancelada. El monto se puede corregir.");
          await repintar();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, "Cancelar solicitud");

  return h("tr", {},
    h("td", {}, h("b", {}, p.nombre),
      h("div", { clase: "chico gris" },
        [p.puesto, `${p.dias} dia(s)`].filter(Boolean).join(" · "))),
    h("td", { style: "text-align:right" },
      h("span", { clase: "num" }, dinero(p.propuesto, moneda))),
    h("td", { style: "text-align:right" },
      h("div", { clase: "acciones", style: "justify-content:flex-end" },
        monto, usar),
      desglose),
    h("td", {}, etiqueta(est.texto, est.tono),
      Number(p.comprobado) > 0
        ? h("div", { clase: "chico gris" },
            `Comprobado ${dinero(p.comprobado, moneda)}`)
        : "",
      cancelar ? h("div", { style: "margin-top:6px" }, cancelar) : ""));
}

/* ------------------------------------------- compras especiales */

/* Hay gastos que no se depositan: se compran. Un boleto de avion, un
   hotel. El consultor no trae la tarjeta de la empresa, asi que escribe
   lo que hace falta y finanzas lo compra y contesta con la reserva.
   Va por equipo y no por persona: el vuelo se gestiona para todos. */

function bloqueCompras(datos, equipo, moneda, repintar) {
  const lista_ = h("div");
  for (const c of datos.compras) lista_.append(
    tarjetaCompra(c, moneda, repintar));
  if (!datos.compras.length) {
    lista_.append(h("span", { clase: "gris chico" },
      "Sin compras pedidas."));
  }

  const zona = h("div");
  return h("div", { style: "margin-top:18px; border-top:1px solid var(--linea); padding-top:14px" },
    h("h4", { style: "margin:0 0 2px" }, "Compras especiales"),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      "Vuelos, hospedaje y todo lo que finanzas compra o reserva por el "
      + "equipo. Se piden aqui y finanzas contesta con la reserva."),
    lista_,
    h("div", { clase: "acciones", style: "margin-top:10px" },
      alternador(h("button", { clase: "claro chico", type: "button" },
                   "Pedir una compra"),
                 zona,
                 () => zona.replaceChildren(
                   formularioCompra(equipo, zona, repintar)))),
    zona);
}

function tarjetaCompra(c, moneda, repintar) {
  const est = ESTADO_COMPRA[c.estatus] || ESTADO_COMPRA.solicitada;
  const tipo = (TIPOS_COMPRA.find(t => t.valor === c.tipo) || {}).texto
               || c.tipo;

  const respuesta = h("div");
  if (c.estatus === "confirmada") {
    respuesta.append(h("div", { clase: "aviso ok", style: "margin:8px 0 0" },
      h("div", {}, h("b", {}, "Reserva: "),
        h("span", { clase: "num" }, c.confirmacion || "—"),
        c.monto_real
          ? h("span", { clase: "gris" }, ` · ${dinero(c.monto_real, moneda)}`)
          : ""),
      c.respuesta ? h("div", { clase: "chico" }, c.respuesta) : "",
      c.tiene_comprobante ? botonComprobante(c) : ""));
  } else if (c.estatus === "rechazada") {
    respuesta.append(aviso(c.respuesta || "Finanzas no la pudo resolver",
                           "grave"));
  }

  const puedeCancelar = c.estatus === "solicitada"
                        || c.estatus === "en_gestion";

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 10px" },
    h("div", { clase: "acciones", style: "justify-content:space-between" },
      h("div", {}, h("b", {}, tipo),
        c.monto_estimado
          ? h("span", { clase: "gris chico" },
              ` · estimado ${dinero(c.monto_estimado, moneda)}`)
          : ""),
      etiqueta(est.texto, est.tono)),
    h("div", { clase: "chico", style: "white-space:pre-wrap; margin-top:4px" },
      c.solicitud),
    respuesta,
    puedeCancelar
      ? h("div", { clase: "acciones", style: "margin-top:8px" },
          h("button", { clase: "claro chico", type: "button",
            onclick: async (e) => {
              e.target.disabled = true;
              try {
                await api.post(`/viaticos/compras/${c.id}/cancelar`);
                await repintar();
              } catch (err) {
                mensaje(err.message, "grave"); e.target.disabled = false;
              }
            } }, "Cancelar"))
      : "");
}

function botonComprobante(c) {
  /* La imagen se baja con la sesion puesta: abrirla en una pestana
     nueva perderia el token y saldria una hoja en blanco. */
  return h("div", { style: "margin-top:6px" },
    h("button", { clase: "claro chico", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          const url = await api.imagen(`/viaticos/compras/${c.id}/comprobante`);
          const pestana = window.open("", "_blank");
          pestana.document.write(
            `<img src="${url}" style="max-width:100%">`);
        } catch (err) { mensaje(err.message, "grave"); }
        e.target.disabled = false;
      } }, "Ver comprobante"));
}

function formularioCompra(equipo, zona, repintar) {
  const selTipo = lista("tipo", TIPOS_COMPRA);
  const solicitud = h("textarea", {
    name: "solicitud", rows: "4",
    placeholder: "Dos boletos Mexico - Monterrey el 16 de septiembre, "
      + "saliendo antes de las 8 am, a nombre de Ramiro Sandoval y "
      + "Luis Ontiveros.",
  });
  const estimado = entrada("estimado", {
    type: "number", step: "0.01", min: "0", placeholder: "Opcional" });

  const guardar = h("button", { clase: "chico", type: "button" },
                    "Enviar a finanzas");
  const zonaError = h("div");

  guardar.addEventListener("click", async () => {
    if (solicitud.value.trim().length < 10) {
      return zonaError.replaceChildren(aviso(
        "Escriba que necesita. Finanzas va a comprar con eso y nada mas: "
        + "ruta, fechas, horarios y a nombre de quien.", "alerta"));
    }
    zonaError.replaceChildren();
    guardar.disabled = true;
    try {
      await api.post(`/viaticos/equipos/${equipo.id}/compras`, {
        tipo: selTipo.value,
        solicitud: solicitud.value.trim(),
        monto_estimado: estimado.value ? Number(estimado.value) : null,
      });
      zona.replaceChildren();
      await repintar();
    } catch (err) {
      zonaError.replaceChildren(aviso(err.message, "grave"));
      guardar.disabled = false;
    }
  });

  return h("div", { clase: "tarjeta lisa", style: "margin-top:8px" },
    h("div", { clase: "rejilla dos" },
      campo("Que se compra", selTipo),
      campo("Monto estimado", estimado)),
    campo("Que necesita, con detalle", solicitud),
    zonaError,
    h("div", { clase: "acciones", style: "margin-top:8px" }, guardar));
}


/* -------------------------------------------- revision de la unidad

   Aqui se resuelve un reclamo de dano. De un lado como estaba la unidad
   cuando paso a manos del equipo, del otro como volvio, con la misma
   foto desde el mismo angulo, la hora, la ubicacion y la firma de quien
   la tuvo. Sin esto, un golpe que aparece tres semanas despues no tiene
   dueno y lo paga el ultimo que la trajo, que no siempre es el que lo
   hizo.

   Se llena desde la app de campo. La consola solo mira. */

const ANGULOS_ES = {
  frente: "Frente", atras: "Atrás", izquierdo: "Izquierdo",
  derecho: "Derecho", dano: "Golpe",
};

const OCTAVOS_ES = ["Vacío", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8",
                    "Lleno"];

async function bloqueRevisiones(servicio) {
  const caja = h("div", { clase: "tarjeta" },
    h("h3", {}, "Revisión de la unidad"));
  let datos;
  try {
    datos = await api.get(`/servicios/${servicio.id}/revisiones`);
  } catch (e) {
    caja.append(aviso(e.message, "alerta"));
    return caja;
  }

  if (!datos.unidades.length) {
    caja.append(h("p", { clase: "chico gris" },
      "Todavía no hay ninguna revisión. La hace el equipo desde su app, "
      + "cuando la unidad cambia de manos."));
    return caja;
  }

  for (const u of datos.unidades) caja.append(tarjetaRevision(u, servicio));
  return caja;
}

function tarjetaRevision(u, servicio) {
  const bloque = h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" },
    h("div", { clase: "fila separa" },
      h("b", {}, u.placa || "Sin placa"),
      u.completa
        ? h("span", { clase: "pastilla ok" }, "Recibida y entregada")
        : u.recibe
          ? h("span", { clase: "pastilla alerta" }, "Todavía en manos del equipo")
          : h("span", { clase: "pastilla alerta" }, "Sin revisar")));

  if (u.kilometros != null) {
    bloque.append(h("p", { clase: "chico" },
      h("b", {}, `${u.kilometros.toLocaleString("es-MX")} km`),
      " recorridos durante el servicio"));
  }

  if (!u.recibe) {
    bloque.append(h("p", { clase: "chico gris" },
      "Nadie registró cómo se recibió esta unidad. Sin ese estado de "
      + "entrada, un daño reclamado después no se puede atribuir."));
    return bloque;
  }

  /* La comparacion no se pinta de entrada: las fotos van como data URI
     y son varios megas por servicio. Esta pantalla se recarga sola en
     casi cada accion del consultor, asi que bajarlas siempre era
     hacerlo esperar por algo que casi nunca mira. Se piden cuando de
     verdad las va a ver, y se piden una sola vez. */
  const zona = h("div", {});
  const abrir = h("button", { clase: "claro chico", style: "margin-top:10px" },
    "Ver las fotos lado a lado");

  abrir.addEventListener("click", async () => {
    if (zona.firstChild) {
      zona.replaceChildren();
      abrir.textContent = "Ver las fotos lado a lado";
      return;
    }
    abrir.disabled = true;
    abrir.textContent = "Bajando las fotos…";
    try {
      const conFotos = await api.get(
        `/servicios/${servicio.id}/revisiones?fotos=true`);
      const suya = conFotos.unidades.find(
        x => x.vehiculo_id === u.vehiculo_id);
      zona.replaceChildren(ladoALado(suya.recibe, suya.entrega));
      abrir.textContent = "Ocultar las fotos";
    } catch (e) {
      zona.replaceChildren(aviso(e.message, "alerta"));
    }
    abrir.disabled = false;
  });

  bloque.append(columnas(u.recibe, u.entrega), abrir, zona);
  return bloque;
}

/* Los datos de las dos puntas —quien, cuando, kilometraje, firma— si se
   ven de entrada: pesan nada y son lo que se consulta a diario. */
function columnas(entrada, salida) {
  return h("div", { clase: "rejilla-revision" },
    columna("Al recibirla", entrada),
    salida ? columna("Al entregarla", salida)
           : h("div", { clase: "chico gris" }, "Todavía no se entrega."));
}

/* Las dos revisiones, angulo por angulo, en el mismo renglon. Ver la
   misma esquina antes y despues es lo unico que hace evidente un golpe
   nuevo; dos galerias separadas obligan a recordar, y nadie recuerda. */
function ladoALado(entrada, salida) {
  const zona = h("div", {});

  const angulos = ["frente", "atras", "izquierdo", "derecho"];
  const deEntrada = mapaFotos(entrada);
  const deSalida = salida ? mapaFotos(salida) : {};

  for (const a of angulos) {
    zona.append(h("div", { clase: "rejilla-revision par-foto" },
      foto(deEntrada[a], ANGULOS_ES[a]),
      salida ? foto(deSalida[a], ANGULOS_ES[a]) : h("div", {})));
  }

  const golpes = [...(entrada.fotos || []), ...(salida ? salida.fotos : [])]
    .filter(f => f.angulo === "dano");
  if (golpes.length) {
    zona.append(h("p", { clase: "chico", style: "margin-top:10px" },
      h("b", {}, "Golpes registrados")));
    zona.append(h("div", { clase: "tira-fotos" },
      ...golpes.filter(f => f.imagen)
        .map(f => h("img", { clase: "mini", src: f.imagen,
                             alt: f.nota || "golpe" }))));
  }
  return zona;
}

function mapaFotos(r) {
  const m = {};
  for (const f of r.fotos || []) if (!m[f.angulo]) m[f.angulo] = f;
  return m;
}

function columna(titulo, r) {
  return h("div", {},
    h("div", { clase: "nombre" }, titulo),
    h("div", { clase: "chico" }, r.persona || "—"),
    h("div", { clase: "chico gris" },
      new Date(r.momento).toLocaleString("es-MX",
        { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })),
    h("div", { clase: "chico" },
      [r.kilometraje != null
         ? `${r.kilometraje.toLocaleString("es-MX")} km` : null,
       r.combustible_octavos != null
         ? `Tanque ${OCTAVOS_ES[r.combustible_octavos]}` : null,
       r.tiene_firma ? "Firmada" : "Sin firma",
      ].filter(Boolean).join(" · ")),
    r.nota ? h("div", { clase: "chico gris" }, r.nota) : null);
}

function foto(f, etiqueta) {
  if (!f) {
    return h("div", { clase: "sin-foto chico gris" }, `${etiqueta}: sin foto`);
  }
  return h("a", { href: f.imagen, target: "_blank", clase: "marco-foto" },
    h("img", { src: f.imagen, alt: etiqueta }),
    h("span", { clase: "pie" }, etiqueta));
}

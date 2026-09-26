/* Pantalla de un servicio. Sigue el mismo orden del task sheet:
   encabezado, meet and greet, equipo y unidad por dia, y al final el
   hospedaje. Quien lo arma ve lo mismo que quien lo va a recibir. */
import { api, sesion } from "./api.js";
import { catalogos } from "./catalogos.js";
import { buscadorDeLugar } from "./mapa.js";
import { aviso, campo, conAyuda, dinero, entrada, estatus, etiqueta, fecha,
         h, hora, lista, mensaje, plegable, sinTildes,
         telefono } from "./util.js";
import { IDIOMAS, idioma, t } from "./idioma.js";
import { tarjetaCierre } from "./cierre.js";
import { tiene } from "./menu.js";

export async function pantallaServicio(main, servicioId) {
  const [servicio, cat] = await Promise.all([
    api.get(`/servicios/${servicioId}`), catalogos()]);
  const cliente = cat.clientes.find(c => c.id === servicio.cliente_id);
  const plaza = cat.plazas.find(p => p.id === servicio.plaza_id);

  main.append(encabezado(servicio, cliente, plaza));

  /* Los cambios de recurso se piden una sola vez: los usan la tabla de
     dias —para marcar cuales se movieron— y el bloque del final. */
  const cambios = await api.get(
    `/contingencia/reemplazos/servicio/${servicioId}`).catch(() => []);

  for (const equipo of servicio.equipos) {
    main.append(await bloqueEquipo(servicio, equipo, cat, cambios));
  }
  main.append(await bloqueTaskSheet(servicio));
  main.append(bloqueCambios(cambios));
  main.append(await bloqueRevisiones(servicio));
  main.append(await bloqueVistoBueno(servicio, cat));
}

/* ------------------------------------------- visto bueno y facturacion

   El ultimo paso del servicio: la comprobacion del personal, el visto
   bueno del consultor, la facturacion y el cierre de finanzas, cada uno
   con su reloj. La tarjeta vive en `cierre.js` porque el mes del
   implantado lleva la misma (seccion 59). */
async function bloqueVistoBueno(servicio, cat) {
  /* Antes de que el servicio termine no hay nada que revisar. */
  if (!["terminado", "sin_visto_bueno", "en_facturacion", "cerrado",
        "cancelado"].includes(servicio.estatus)) {
    return h("div", {});
  }
  /* El cancelado solo tiene cierre si habia algo que cerrar: dinero
     afuera o dias trabajados. Sin cierre no hay nada que pintar. */
  if (servicio.estatus === "cancelado") {
    const c = await api.get(`/cierre/servicio/${servicio.id}/estado`)
      .catch(() => null);
    if (!c || !c.existe) return h("div", {});
  }
  const plaza = cat.plazas.find(p => p.id === servicio.plaza_id);
  const pais = cat.paises.find(p => p.id === servicio.pais_id);
  const base = `/cierre/servicio/${servicio.id}`;
  return tarjetaCierre({
    titulo: t("srv_visto_bueno"), ayuda: "ay_srv_visto_bueno",
    rutas: { estado: `${base}/estado`, revision: `${base}/revision`,
             viaticos: `${base}/viaticos`,
             desglose: `${base}/desglose-gastos` },
    esMes: false,
    lugar: plaza ? plaza.nombre : (pais ? pais.nombre : ""),
    moneda: (pais && pais.moneda_local) || "MXN",
    /* El estatus del encabezado cambia con el visto bueno. */
    alCambiar: () => setTimeout(() => location.reload(), 1200),
  });
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
          /* El otro lado del mismo servicio: el contrato del mes, la
             plantilla, los viaticos y el taller. Solo en implantado,
             porque un eventual no tiene contrato mensual. */
          servicio.tipo === "implantado"
            ? h("button", { clase: "claro chico", type: "button",
                onclick: () => (location.hash = `#/implantado/${servicio.id}`) },
                t("srv_ver_contrato"))
            : "",
          ANTES_DE_ARRANCAR.includes(servicio.estatus)
            ? h("button", { clase: "claro chico", type: "button",
                onclick: () => borrar(
                  `/servicios/${servicio.id}`,
                  t("srv_eliminar_srv").replace("{f}", servicio.folio)
                    .replace("{n}", servicio.equipos.length),
                  t("srv_servicio_eliminado"), "#/servicios") }, t("srv_eliminar"))
            : "",
          !["cancelado", "cerrado"].includes(servicio.estatus)
            ? h("button", { clase: "claro chico", type: "button",
                onclick: () => cancelar(servicio) }, t("srv_cancelar"))
            : ""))),
    h("div", { clase: "rejilla dos", style: "margin-top:14px" },
      h("div", {},
        h("h4", {}, t("srv_ejecutivo")),
        h("div", {}, servicio.ejecutivo_completo || h("span", { clase: "gris" }, t("srv_por_definir"))),
        h("div", { clase: "gris num" }, servicio.ejecutivo_telefono || "")),
      h("div", {},
        h("h4", {}, t("srv_solicita")),
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
    t("srv_cancelar_prompt").replace("{f}", servicio.folio));
  if (motivo === null) return;
  if (!motivo.trim()) return mensaje(t("srv_falta_motivo"), "alerta");
  try {
    const r = await api.post(`/servicios/${servicio.id}/cancelar`,
                             { motivo: motivo.trim() });
    mensaje(t("srv_cancelado").replace("{f}", r.folio));
    for (const v of r.viaticos_por_devolver || []) {
      mensaje(t("srv_por_devolver").replace("{p}", v.persona)
                .replace("{m}", v.monto).replace("{c}", v.moneda), "alerta");
    }
    setTimeout(() => location.reload(), 1200);
  } catch (err) { mensaje(err.message, "grave"); }
}

/* Borrar pide el motivo: no es un tramite, es la unica huella que queda
   de un servicio que dejo de existir. */
async function borrar(ruta, advertencia, listo, destino = null) {
  const motivo = prompt(t("srv_borrar_prompt").replace("{a}", advertencia));
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

async function bloqueEquipo(servicio, equipo, cat, cambios) {
  const caja = h("div", { clase: "tarjeta" },
    h("div", { clase: "cabeza-equipo" },
        h("div", {},
        h("h3", { style: "margin:0" }, t("srv_equipo").replace("{a}", equipo.alias)),
        /* Donde opera este equipo: un mismo proyecto puede tener a Alfa
           en Ciudad de Mexico y a Beta en Monterrey. */
        h("div", { clase: "chico gris" }, ciudadDe(equipo, cat))),
      /* Solo tiene sentido con mas de un equipo: el ultimo no se quita,
         se elimina el servicio completo. */
      servicio.equipos.length > 1
        ? h("button", { clase: "claro chico", type: "button",
            onclick: () => borrar(
              `/servicios/equipos/${equipo.id}`,
              t("srv_eliminar_eq").replace("{a}", equipo.alias)
                .replace("{n}", equipo.jornadas.length),
              t("srv_equipo_eliminado")) }, t("srv_eliminar_equipo"))
        : ""),
    h("p", { clase: "gris chico", style: "margin:-6px 0 14px" },
      t("srv_equipo_pie")),
    /* A quien cuida este equipo. Con un solo equipo es el del servicio,
       que ya sale arriba; con dos o mas, cada hoja lleva el suyo. */
    h("div", { clase: "chico", style: "margin:-8px 0 14px" },
      h("span", { clase: "gris" }, t("srv_ejecutivo_dp")),
      equipo.ejecutivo_completo
        || h("span", { clase: "gris" }, t("srv_por_definir")),
      equipo.ejecutivo_telefono
        ? h("span", { clase: "gris num" }, ` · ${equipo.ejecutivo_telefono}`)
        : ""));

  caja.append(await bloqueRecursos(servicio, equipo, cat));
  /* El dinero va pegado a la gente: en cuanto hay alguien asignado
     aparece cuanto se le deposita. Sin personal no se pinta nada,
     porque no hay a quien depositarle. */
  caja.append(await bloqueViaticos(equipo));
  caja.append(await bloqueHotel(servicio, equipo, cat));
  caja.append(tablaDias(servicio, equipo, cat, cambios));
  return caja;
}

/* Un boton que abre tambien tiene que cerrar. Si no, la unica salida es
   recargar la pantalla, y el consultor termina con tres formularios
   abiertos uno debajo del otro sin saber cual estaba llenando. */
function alternador(boton, zona, abrir, textoCerrar = t("srv_cerrar")) {
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
async function bloqueRecursos(servicio, equipo, cat) {
  const caja = h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" });
  /* Las dos zonas se crean UNA vez y viven fuera del repintado.
  
     Antes se creaban dentro, y al repintar la ficha nacia una zona nueva
     a la que habia que mudarle el panel abierto. La mudanza funcionaba
     una vez: los botones del panel seguian apuntando a la zona vieja
     --ya vacia-- asi que la SEGUNDA asignacion no encontraba nada que
     reabrir y el panel se cerraba. Se asignaba al conductor y al
     asignar al agente se caia todo.
  
     Con la zona estable no hay nada que mudar: el panel se queda donde
     esta y lo unico que se repinta es el resumen de arriba. */
  const zona = h("div", { style: "margin-top:12px" });
  const zonaCambio = h("div", { style: "margin-top:12px" });
  await pintarRecursos(caja, servicio, equipo, cat, zona, zonaCambio);
  return caja;
}

async function pintarRecursos(caja, servicio, equipo, cat, zona, zonaCambio) {
  let datos;
  try {
    datos = await api.get(`/servicios/equipos/${equipo.id}/asignaciones`);
  } catch (err) {
    return caja.replaceChildren(aviso(err.message, "grave"));
  }

  /* Asignar sin poder desasignar deja al consultor probando quien cabe
     sin marcha atras. Se quita de todos los dias, igual que se puso. */
  const quitar = (ruta, que) => h("button", {
    clase: "claro chico", type: "button", style: "margin-top:6px",
    onclick: async (e) => {
      if (!confirm(t("srv_quitar_a").replace("{q}", que).replace("{n}", datos.dias))) {
        return;
      }
      e.target.disabled = true;
      try {
        await api.borrar(ruta);
        location.reload();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, t("srv_quitar"));

  const ficha = (x, titulo, cuerpo, boton) => h("div", { clase: "persona" },
    x.foto ? h("img", { clase: "foto", src: x.foto, alt: "" })
           : h("div", { clase: "foto" }),
    h("div", {}, h("h4", { style: "margin:0 0 1px" }, titulo), ...cuerpo,
      /* Lo normal es que este todos los dias. Si no, es que hubo un
         cambio a media semana y eso hay que verlo. */
      x.dias < datos.dias
        ? h("div", { clase: "chico", style: "color:#b8860b" },
            t("srv_solo_dias").replace("{n}", x.dias).replace("{t}", datos.dias))
        : "",
      boton || ""));

  const variasUnidades = datos.vehiculos.length > 1;

  /* Un boton por persona, junto a Quitar: el consultor esta viendo a
     Juan Ramirez y lo que quiere es cambiar a Juan Ramirez. No hay que
     ensenarle a nadie donde esta.

     Y abre PERO TAMBIEN CIERRA. Abria y ya: quien lo picaba para ver de
     que se trataba se quedaba con el formulario del cambio abierto sin
     forma de arrepentirse, y volver a picar "Cambiar" lo reabria. Un
     boton que no puede deshacer lo que hizo obliga a recargar la
     pantalla para salir.

     Los botones comparten UNA zona --hay uno por persona-- asi que hay
     tres situaciones y no dos: si el panel ya es de esta persona, se
     cierra; si es de otra, se cambia a esta; y el boton de aquella
     vuelve a decir "Cambiar", porque dos botones diciendo "Cerrar" con
     un solo panel abierto es mentira. */
  const botonesCambiar = [];

  function botonCambiar(servicio_, equipo_, cat_, persona, datos_) {
    const boton = h("button", { clase: "claro chico", type: "button",
      onclick: () => {
        const suyo = zonaCambio.dataset.persona === String(persona.persona_id);
        for (const otro of botonesCambiar) otro.textContent = t("srv_cambiar");
        if (suyo) {
          zonaCambio.replaceChildren();
          delete zonaCambio.dataset.persona;
          return;
        }
        zonaCambio.dataset.persona = String(persona.persona_id);
        boton.textContent = t("srv_cerrar");
        abrirCambio(zonaCambio, servicio_, equipo_, cat_, persona, datos_);
      } },
      zonaCambio.dataset.persona === String(persona.persona_id)
        ? t("srv_cerrar") : t("srv_cambiar"));
    botonesCambiar.push(boton);
    return boton;
  }

  /* Si esa persona ya dijo que va, y quien lo dijo.

     Se cuenta por dias porque la confirmacion es de cada dia: en un
     servicio de cinco dias alguien puede haber confirmado tres, y un
     si/no mentiria en los otros dos.

     Y lo que registro la central por telefono lleva su nombre. La
     central ya lo distinguia; aqui no, y esta es la pantalla donde el
     consultor decide si su equipo esta armado. El dia que alguien no
     llegue, la diferencia entre "confirmo el" y "lo confirmaron por
     el" es la unica pregunta que importa. */
  function confirmacion(p) {
    const dias = p.dias || 0;
    const cuantos = p.confirmados || 0;
    if (!dias) return "";
    if (!cuantos) {
      return h("div", { clase: "chico gris" }, t("srv_sin_confirmar"));
    }
    const quien = (p.confirmado_por || []).join(", ");
    const texto = cuantos >= dias
      ? t("srv_confirmo")
      : t("srv_confirmo_parcial").replace("{n}", cuantos).replace("{d}", dias);
    return h("div", { clase: "chico" },
      h("span", { clase: `marca ${cuantos >= dias ? "ok" : "alerta"}` }, texto),
      quien
        ? h("span", { clase: "gris chico" },
            " " + t("srv_por_telefono").replace("{quien}", quien))
        : null);
  }

  const gente = h("div", {}, h("h4", {}, t("srv_equipo_seguridad")));
  if (datos.personal.length) {
    for (const p of datos.personal) {
      /* La zona del cambio vive debajo de la tarjeta de recursos, igual
         que la de asignar: un solo panel abierto a la vez y nada que se
         encime con la ficha que se esta leyendo. */
      const acciones = h("div", { clase: "acciones", style: "margin-top:6px" },
        p.relevado_en
          ? ""
          : botonCambiar(servicio, equipo, cat, p, datos),
        quitar(`/servicios/equipos/${equipo.id}/personal/${p.persona_id}`,
               p.nombre));
      gente.append(ficha(p, p.puesto || t("srv_personal"), [
        h("b", {}, p.nombre),
        h("div", { clase: "chico" },
          p.telefono || h("span", { clase: "gris" }, t("srv_sin_telefono"))),
        h("div", { clase: "chico gris" }, p.ciudad || ""),
        /* Un cambio a media semana rompe la premisa de que el equipo es
           el mismo todos los dias. La ficha tiene que decirlo o el
           consultor lee un equipo que no existe. */
        p.relevado_en
          ? h("div", { clase: "chico", style: "color:#b8860b" },
              t("srv_relevado").replace("{d}", fecha(p.relevado_en.slice(0, 10)))
              .replace("{h}", p.relevado_en.slice(11, 16)))
          : "",
        p.reemplaza_a
          ? h("div", { clase: "chico", style: "color:#b8860b" },
              t("srv_reemplaza_a").replace("{p}", p.reemplaza_a))
          : "",
        confirmacion(p),
        variasUnidades ? selectorAbordo(equipo, p, datos.vehiculos) : "",
      ], acciones));
    }
  } else {
    gente.append(h("span", { clase: "gris" }, t("srv_por_asignar")));
  }

  const flota = h("div", {}, h("h4", {}, t("srv_unidad")));
  if (datos.vehiculos.length) {
    for (const v of datos.vehiculos) {
      flota.append(ficha(v, t("srv_vehiculo_seguridad"), [
        h("b", {}, v.unidad || t("srv_unidad")), " ",
        h("span", { clase: "etiqueta" },
          v.blindada ? t("srv_blindada") : t("srv_sin_blindar")),
        v.rentado ? " " : "", v.rentado ? etiqueta("rentada", "alerta") : "",
        h("div", {}, h("span", { clase: t("srv_f_placas") }, v.placa)),
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
    flota.append(h("span", { clase: "gris" }, t("srv_por_asignar")));
  }

  /* La ficha se repinta SIN recargar la pantalla, y el panel de asignar
     se queda abierto donde estaba. Eso es lo que permite asignar al
     conductor y a su unidad de corrido, que es como se hace de verdad:
     son la misma decision tomada en el mismo minuto. */
  const repintar = () =>
    pintarRecursos(caja, servicio, equipo, cat, zona, zonaCambio);
  const boton = h("button", { clase: "claro chico", type: "button" },
                  t("srv_asignar_recursos"));

  caja.replaceChildren(
    h("div", { clase: "rejilla dos" }, gente, flota),
    h("p", { clase: "gris chico", style: "margin:12px 0 0" },
      t("srv_recursos_pie").replace("{n}", datos.dias)),
    h("div", { clase: "acciones", style: "margin-top:8px" },
      alternador(boton, zona,
                 () => abrirAsignacion(zona, equipo, cat, repintar))),
    zona, zonaCambio);

  /* El boton se rehace en cada repintado; lo que no se rehace es la
     zona. Si trae panel, el boton tiene que decir "Cerrar" --si dijera
     "Asignar recursos" con el panel abierto, el siguiente clic pareceria
     abrir y lo que haria es cerrar. */
  if (zona.firstChild) boton.textContent = t("srv_cerrar");
}

/* ------------------------------------------------------------ asignar */

/* El rol es de la tarea, no de la persona.

   El personal de seguridad es general: el mismo agente que hoy conduce
   manana coordina. Por eso la lista de abajo ya no se filtra por puesto
   —sale todo el que este libre— y lo que se elige aqui arriba es con
   que rol va, que es de donde salen el precio al cliente y la comision
   que se le paga. */
async function abrirAsignacion(zona, equipo, cat, alAsignar = null) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("srv_buscando_recursos")));
  const perfil = cat.perfiles.find(p => p.codigo === "conductor_seguridad");
  const categoria = cat.categorias.find(c => c.codigo === "suv_blindada");

  const selPerfil = lista("perfil", cat.perfiles.map(
    p => ({ valor: p.id, texto: p.nombre })));
  const selCategoria = lista("categoria", cat.categorias.map(
    c => ({ valor: c.id, texto: c.nombre })));
  if (perfil) selPerfil.value = perfil.id;
  if (categoria) selCategoria.value = categoria.id;

  const resultados = h("div");

  /* Despues de asignar: la lista se vuelve a pedir --quien acaba de
     entrar ya no esta libre-- y la ficha del equipo se repinta para que
     la persona aparezca arriba al momento. Sin recargar nada. */
  const hecho = async () => {
    await buscar();
    if (alAsignar) await alAsignar();
  };

  const buscar = async () => {
    resultados.replaceChildren(h("div", { clase: "gris chico" }, t("srv_buscando")));
    try {
      const r = await api.get(
        `/servicios/equipos/${equipo.id}/recomendaciones` +
        `?perfil_id=${selPerfil.value}&categoria_id=${selCategoria.value}`);
      resultados.replaceChildren(
        pintarRecomendaciones(r, equipo, cat, Number(selCategoria.value),
                              () => Number(selPerfil.value) || null,
                              hecho));
    } catch (e) { resultados.replaceChildren(aviso(e.message, "grave")); }
  };
  selPerfil.addEventListener("change", buscar);
  selCategoria.addEventListener("change", buscar);

  zona.replaceChildren(h("div", { clase: "tarjeta lisa" },
    h("div", { clase: "rejilla dos" },
      campo(t("srv_rol"), selPerfil),
      campo(t("srv_categoria"), selCategoria)),
    resultados));
  buscar();
}

function pintarRecomendaciones(r, equipo, cat, categoriaId, rolId,
                               hecho = null) {
  /* Cada lista debajo del selector que la arma: perfil a la izquierda,
     categoria de unidad a la derecha. En pantalla angosta la rejilla se
     vuelve una sola columna sola. */
  return h("div", { clase: "rejilla dos", style: "margin-top:14px" },
    tablaPersonal(r.personal, equipo, rolId, hecho),
    tablaUnidades(r.vehiculos, equipo, cat, categoriaId, hecho));
}

/* El estado de un recurso en un solo lugar: la pantalla no vuelve a
   decidir si algo se puede asignar, solo lo pinta. */
function estadoDe(f) {
  const motivos = (f.alertas || []).map(a => a.mensaje || a.tipo).join(" · ");
  if (f.bloqueado) return { clave: "bloqueo", texto: t("srv_ocupado"), motivos };
  if (motivos) return { clave: "riesgo", texto: t("srv_riesgo"), motivos };
  return { clave: "libre", texto: t("srv_disponible"), motivos: "" };
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
        t("srv_otra_ciudad").replace("{c}", f.ciudad || t("srv_otra")));
}

function celdaEstado(est) {
  return h("td", {},
    etiqueta(est.texto, est.clave === "libre" ? "ok"
             : est.clave === "riesgo" ? "alerta" : "grave"),
    est.motivos
      ? h("div", { clase: "chico gris", style: "margin-top:3px" }, est.motivos)
      : "");
}

function botonAsignar(est, hacer, despues = null) {
  if (est.clave === "bloqueo") {
    return h("button", { clase: "chico claro", disabled: "disabled",
                         title: est.motivos }, t("srv_no_se_puede"));
  }
  const forzar = est.clave === "riesgo";
  return h("button", { clase: "chico" + (forzar ? " claro" : ""),
    onclick: async (e) => {
      e.target.disabled = true;
      try {
        await hacer(forzar);
        /* Recargar la pantalla cerraba el panel a media tarea: se
           asignaba al conductor y habia que volver a buscar el equipo,
           volver a abrir el panel y volver a elegir la categoria para
           poder asignarle su unidad. Quien sabe repintarse lo hace en su
           sitio; `location.reload` se queda solo para lo que todavia
           no. */
        if (despues) {
          await despues();
          // La hoja tambien cambia con esto, y nadie la recarga ya.
          if (refrescarHoja) await refrescarHoja();
        } else location.reload();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, forzar ? t("srv_asignar_igual") : t("srv_asignar"));
}

function caja(titulo, bloque, cuantos, encabezados, cuerpo, vacio) {
  return h("div", {},
    h("h4", {}, t("srv_titulo_n").replace("{t}", titulo).replace("{n}", cuantos)),
    bloque.aviso ? aviso(bloque.aviso, "alerta") : "",
    cuantos
      ? h("table", {},
          h("thead", {}, h("tr", {}, ...encabezados.map(t => h("th", {}, t)))),
          cuerpo)
      : h("span", { clase: "gris" }, vacio));
}

function tablaPersonal(bloque, equipo, rolId = () => null, hecho = null) {
  const gente = ordenar(todos(bloque));
  const cuerpo = h("tbody");

  /* Buscar por nombre. Con cuarenta y cuatro personas, encontrar a una
     era bajar la pantalla leyendo; y quien asigna casi siempre YA SABE
     a quien quiere --se lo acordo por telefono-- asi que la lista
     completa solo estorba.
  
     Busca tambien por ciudad, que es la otra forma de preguntar lo
     mismo: "a ver quien tengo en Monterrey". Y el filtro es sobre lo
     que ya llego, no otra consulta: la lista esta completa en la
     pantalla, asi que filtrar es instantaneo y funciona sin senal. */
  const filas = new Map();
  const buscar = entrada("buscar_persona", {
    type: "search", placeholder: t("srv_buscar_persona"),
    oninput: () => {
      const q = sinTildes(buscar.value);
      let visibles = 0;
      for (const [clave, fila] of filas) {
        const cabe = !q || clave.includes(q);
        fila.hidden = !cabe;
        if (cabe) visibles += 1;
      }
      cuenta.textContent = t("srv_titulo_n")
        .replace("{t}", t("srv_personal_seguridad"))
        .replace("{n}", visibles);
      sinNadie.hidden = visibles > 0;
    },
  });
  const sinNadie = h("div", { clase: "gris chico", hidden: true,
                              style: "margin:8px 0" },
                     t("srv_nadie_con_ese_nombre"));
  const cuenta = h("h4", {}, t("srv_titulo_n")
    .replace("{t}", t("srv_personal_seguridad"))
    .replace("{n}", gente.length));

  for (const p of gente) {
    const est = estadoDe(p);
    const fila = h("tr", {},
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
                 { persona_id: p.persona_id, rol_id: rolId(), forzar }),
        hecho)));
    filas.set(sinTildes(`${p.nombre} ${p.ciudad || ""}`), fila);
    cuerpo.append(fila);
  }

  if (!gente.length) {
    return caja(t("srv_personal_seguridad"), bloque, 0,
                [], cuerpo, t("srv_nadie_libre"));
  }

  return h("div", {},
    cuenta,
    bloque.aviso ? aviso(bloque.aviso, "alerta") : "",
    /* El buscador va DEBAJO del titulo y encima de la tabla: es lo
       primero que se toca al llegar aqui. */
    h("div", { style: "margin:0 0 10px" }, buscar),
    h("table", {},
      h("thead", {}, h("tr", {},
        ...[t("srv_persona"), t("srv_estado"), t("srv_calificacion"), ""]
          .map(x => h("th", {}, x)))),
      cuerpo),
    sinNadie);
}

function tablaUnidades(bloque, equipo, cat, categoriaId, hecho = null) {
  const flota = ordenar(todos(bloque));
  const cuerpo = h("tbody");

  /* Buscar una unidad. Igual que con la gente, y por la misma razon:
     quien asigna suele saber que unidad quiere.
  
     Aqui lo que se teclea es casi siempre la PLACA --es como se llama a
     un coche por radio-- asi que se busca por placa, por numero de
     unidad, por marca y modelo, y por ciudad. "abc" encuentra la
     ABC-1234; "suburban" encuentra todas las Suburban. */
  const filas = new Map();
  const buscar = entrada("buscar_unidad", {
    type: "search", placeholder: t("srv_buscar_unidad"),
    oninput: () => {
      const q = sinTildes(buscar.value);
      let visibles = 0;
      for (const [clave, fila] of filas) {
        const cabe = !q || clave.includes(q);
        fila.hidden = !cabe;
        if (cabe) visibles += 1;
      }
      cuenta.textContent = t("srv_titulo_n")
        .replace("{t}", t("srv_unidades")).replace("{n}", visibles);
      sinNada.hidden = visibles > 0;
    },
  });
  const sinNada = h("div", { clase: "gris chico", hidden: true,
                             style: "margin:8px 0" },
                    t("srv_ninguna_unidad_asi"));
  const cuenta = h("h4", {}, t("srv_titulo_n")
    .replace("{t}", t("srv_unidades")).replace("{n}", flota.length));

  for (const v of flota) {
    const est = estadoDe(v);
    const fila = h("tr", {},
      h("td", {}, h("span", { clase: t("srv_f_placas") }, v.placa || v.placas),
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
                 { vehiculo_id: v.vehiculo_id, forzar }),
        hecho)));
    filas.set(sinTildes([v.placa || v.placas, v.unidad, v.marca_modelo,
                         v.ciudad].filter(Boolean).join(" ")), fila);
    cuerpo.append(fila);
  }

  const tabla = flota.length
    ? h("div", {},
        cuenta,
        bloque.aviso ? aviso(bloque.aviso, "alerta") : "",
        h("div", { style: "margin:0 0 10px" }, buscar),
        h("table", {},
          h("thead", {}, h("tr", {},
            ...[t("srv_unidad"), t("srv_estado"), ""]
              .map(x => h("th", {}, x)))),
          cuerpo),
        sinNada)
    : caja(t("srv_unidades"), bloque, 0, [], cuerpo, t("srv_sin_unidades"));

  /* La flota no siempre alcanza: el cliente pide una categoria que no
     tenemos o la semana viene saturada, y el auto se subarrienda. Se
     captura aqui, en el momento de asignar, porque es cuando se sabe
     que hace falta: mandarlo al catalogo de flota seria otra pantalla,
     otro dia y un servicio detenido mientras tanto. */
  const zona = h("div");
  return h("div", {},
    tabla,
    h("div", { clase: "acciones", style: "margin-top:8px" },
      alternador(h("button", { clase: "claro chico", type: "button" },
                   t("srv_subir_renta")),
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
    texto: t("srv_motivo_categoria") },
  { valor: "saturacion", texto: t("srv_motivo_saturacion") },
  { valor: "pedido_especial", texto: t("srv_motivo_especial") },
];

function formularioRenta(equipo, cat, categoriaId) {
  const categorias = (cat && cat.categorias) || [];
  const selCategoria = lista("categoria", categorias.map(
    c => ({ valor: c.id, texto: c.nombre })));
  if (categoriaId) selCategoria.value = categoriaId;

  const placa = entrada("placa", { placeholder: "ABC-123-D",
                                   maxlength: "20", autocomplete: "off" });
  const marca = entrada("marca_modelo", { placeholder: "Suburban" });
  const color = entrada("color", { placeholder: t("srv_color_ej") });
  const anio = entrada("anio", { type: "number", min: "1990", max: "2100",
                                 value: String(new Date().getFullYear()) });
  const costo = entrada("costo", { type: "number", step: "0.01", min: "1",
                                   placeholder: "0.00" });
  const arrendadora = entrada(t("srv_f_arrendadora"), { placeholder: t("srv_nombre_arrendadora") });
  const tel = telefono("arrendadora_telefono");
  const selMotivo = lista("motivo", MOTIVOS_RENTA);

  const guardar = h("button", { clase: "chico", type: "button" },
                    t("srv_guardar_asignar"));
  const zonaError = h("div");

  guardar.addEventListener("click", async () => {
    const faltan = [];
    if (placa.value.trim().length < 3) faltan.push(t("srv_f_placas"));
    if (marca.value.trim().length < 2) faltan.push(t("srv_f_marca"));
    if (color.value.trim().length < 2) faltan.push(t("srv_f_color"));
    if (!Number(anio.value)) faltan.push(t("srv_f_anio"));
    if (!(Number(costo.value) > 0)) faltan.push(t("srv_f_costo"));
    if (arrendadora.value.trim().length < 2) faltan.push(t("srv_f_arrendadora"));
    if (!tel.valor()) faltan.push(t("srv_f_telefono"));
    if (faltan.length) {
      zonaError.replaceChildren(aviso(
        t("srv_falta_renta").replace("{x}", faltan.join(", ")), "alerta"));
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
    conAyuda("h4", t("srv_auto_rentado"), "ay_srv_renta",
             { style: "margin:0 0 2px" }),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("srv_renta_pie")),
    h("div", { clase: "rejilla dos" },
      campo(t("srv_placas"), placa),
      campo(t("srv_categoria"), selCategoria),
      campo(t("srv_marca"), marca),
      campo(t("srv_color"), color),
      campo(t("imp_anio"), anio),
      campo(t("srv_costo_renta"), costo),
      campo(t("srv_arrendadora"), arrendadora),
      campo(t("srv_tel_proveedor"), tel),
      campo(t("srv_motivo_subarrendo"), selMotivo)),
    zonaError,
    h("div", { clase: "acciones", style: "margin-top:10px" }, guardar));
}


/* --------------------------------------- cambio por contingencia */

/* Lo delicado de un reemplazo no es el nombre de quien va: son los
   viaticos. El que sale se queda con dinero que ya recibio y tiene que
   comprobarlo; el que entra necesita dinero nuevo. Eso ya pasaba, solo
   que en silencio, y el consultor se enteraba despues. Por eso aqui
   nada se guarda hasta que la pantalla dice en voz alta lo que va a
   pasar. */

/* Con nombre y no como texto libre: de aqui salen las dos cuentas que
   la direccion va a pedir —cuanto ausentismo hay y cuanto tiempo pasan
   las unidades en el taller— y escrito a mano no se puede contar. */
const MOTIVOS = [
  { valor: "contingencia", texto: t("srv_m_contingencia") },
  { valor: "enfermedad", texto: t("srv_m_enfermedad") },
  { valor: "vacaciones", texto: t("srv_m_vacaciones") },
  { valor: "descanso", texto: t("srv_m_descanso") },
  { valor: "baja", texto: t("srv_m_baja") },
  { valor: "otro", texto: t("srv_m_otro") },
];

const CERRADOS = ["cancelada", "terminada"];

function diasPendientes(equipo) {
  return [...equipo.jornadas]
    .filter(j => !CERRADOS.includes(j.estatus))
    .sort((a, b) => (a.fecha < b.fecha ? -1 : 1));
}

/* Las dos puertas hacen el mismo cambio y por dentro es el mismo motor.
   La del implantado ademas pone el tope: un cambio sin fecha de fin
   llega al ultimo dia del mes en curso. Esa regla vive en el servidor y
   no aqui: el navegador solo pregunta por cual puerta entra. */
function puertaDe(servicio) {
  return servicio.tipo === "implantado"
    ? { previa: `/implantados/${servicio.id}/cambios/vista-previa`,
        guardar: `/implantados/${servicio.id}/cambios`,
        entra: "entra_id", implantado: true }
    : { previa: "/contingencia/reemplazos/personal/vista-previa",
        guardar: "/contingencia/reemplazos/personal",
        entra: "entra_persona_id", implantado: false };
}

async function abrirCambio(zona, servicio, equipo, cat, persona, datos) {
  const puerta = puertaDe(servicio);
  const dias = diasPendientes(equipo);
  if (!dias.length) {
    return zona.replaceChildren(aviso(
      t("srv_sin_pendientes"),
      "alerta"));
  }

  /* El cambio aplica del dia que se elija en adelante. Se propone hoy si
     hoy es uno de los dias del equipo, que es el caso de la contingencia
     de verdad; si no, el primero que queda. */
  const hoy = new Date().toISOString().slice(0, 10);
  const desde = lista("desde", dias.map(
    j => ({ valor: j.id, texto: fecha(j.fecha) })));
  const suyo = dias.find(j => j.fecha === hoy);
  desde.value = (suyo || dias[0]).id;

  const hasta = lista("hasta", dias.map(
    j => ({ valor: j.id, texto: fecha(j.fecha) })), { disabled: "disabled" });
  hasta.value = dias[dias.length - 1].id;

  const conFin = h("input", { type: "radio", name: "alcance" });
  const adelante = h("input", { type: "radio", name: "alcance",
                                checked: "checked" });
  const marcar_ = () => { hasta.disabled = !conFin.checked; };
  conFin.addEventListener("change", marcar_);
  adelante.addEventListener("change", marcar_);

  const motivo = lista("motivo", MOTIVOS);
  const nota = entrada("nota", { placeholder: t("srv_que_paso") });

  const candidatos = h("div", { style: "margin-top:12px" },
    h("div", { clase: "gris chico" }, t("srv_buscando_entra")));
  const previa = h("div", { style: "margin-top:12px" });

  /* La puerta del implantado habla de fechas y la de eventual de
     jornadas. Es la misma eleccion del consultor dicha de dos maneras. */
  const fechaDe = new Map(dias.map(j => [String(j.id), j.fecha]));

  const armar = () => (puerta.implantado
    ? { tipo: "personal",
        desde: fechaDe.get(desde.value),
        hasta: conFin.checked ? fechaDe.get(hasta.value) : null,
        sale_id: persona.persona_id,
        motivo: motivo.value,
        nota: nota.value.trim() || null }
    : { desde_jornada_id: Number(desde.value),
        hasta_jornada_id: conFin.checked ? Number(hasta.value) : null,
        sale_persona_id: persona.persona_id,
        motivo: nota.value.trim()
                || MOTIVOS.find(x => x.valor === motivo.value).texto,
        motivo_tipo: motivo.value });

  zona.replaceChildren(h("div", { clase: "tarjeta lisa" },
    h("h4", { style: "margin:0 0 2px" }, t("srv_cambiar_a").replace("{p}", persona.nombre)),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("srv_cambio_pie")),
    h("div", { clase: "rejilla dos" },
      campo(t("srv_desde_dia"), desde),
      campo(t("srv_hasta_cuando"), h("div", {},
        h("label", { clase: "chico" }, adelante,
          puerta.implantado ? t("srv_hasta_fin_mes") : t("srv_adelante")),
        h("label", { clase: "chico", style: "margin-left:12px" },
          conFin, t("srv_hasta_el_dia")), hasta,
        h("div", { clase: "gris chico", style: "margin-top:4px" },
          puerta.implantado ? t("srv_alcance_imp_pie")
                            : t("srv_alcance_pie"))))),
    h("div", { clase: "rejilla dos" },
      campo("Por que", motivo), campo(t("srv_nota"), nota)),
    /* La previa va ARRIBA de la lista, no debajo.
    
       Debajo, con cuarenta y tres candidatos de por medio, el consultor
       picaba "Elegir" en el primero y el resultado caia mil pixeles mas
       abajo: desde la silla, la pantalla no hacia nada. */
    previa, candidatos));

  /* La misma lista de recomendaciones que usa t("srv_asignar_recursos"), con
     su disponibilidad y sus choques ya resueltos. Filtrada al rol que
     traia el que sale: un conductor se reemplaza con un conductor. */
  try {
    /* Con el rol que traia el que sale: un conductor se reemplaza con un
       conductor. Si la asignacion venia sin rol —no deberia, pero pasa—
       se cae al primero del catalogo en vez de pedir la lista vacia. */
    const categoria = cat.categorias[0];
    const rol = persona.rol_id || (cat.perfiles[0] || {}).id;
    const r = await api.get(
      `/servicios/equipos/${equipo.id}/recomendaciones`
      + `?perfil_id=${rol}&categoria_id=${categoria.id}`);
    candidatos.replaceChildren(
      tablaCandidatos(r.personal, persona, armar, previa, puerta));
  } catch (err) {
    candidatos.replaceChildren(aviso(err.message, "grave"));
  }
}

/* Mismo criterio que botonAsignar: a quien no se puede poner, no se le
   ofrece el boton. Antes salia con la etiqueta OCUPADO y el boton vivo,
   y el consultor se enteraba hasta que el servidor le decia que no. */
function botonElegir(est, alElegir) {
  if (est.clave === "bloqueo") {
    return h("button", { clase: "chico claro", type: "button",
                         disabled: "disabled", title: est.motivos },
             t("srv_no_se_puede"));
  }
  const forzar = est.clave === "riesgo";
  return h("button", { clase: "chico" + (forzar ? " claro" : ""),
                       type: "button", title: est.motivos,
                       onclick: alElegir },
           t("srv_elegir"));
}

function tablaCandidatos(bloque, sale, armar, previa, puerta) {
  const gente = ordenar(todos(bloque))
    .filter(x => x.persona_id !== sale.persona_id);
  const cuerpo = h("tbody");
  for (const p of gente) {
    const est = estadoDe(p);
    cuerpo.append(h("tr", {},
      h("td", {}, h("b", {}, p.nombre), lineaCiudad(p)),
      celdaEstado(est),
      h("td", {}, botonElegir(est,
        (e) => verPrevia(e, previa, armar(), p, puerta)))));
  }
  return caja(t("srv_quien_entra").replace("{p}", sale.nombre), bloque, gente.length,
              [t("srv_persona"), t("srv_disponibilidad"), ""], cuerpo,
              t("srv_nadie_rol"));
}

/* Nada se guarda hasta aqui. Lo que se pinta es el cambio de verdad,
   ejecutado y deshecho en el servidor: no hay una segunda cuenta que
   calcule "lo que pasaria" y se separe de la primera. */
/* Deja el recuadro a la vista. Un panel que aparece fuera de la
   pantalla es, para quien lo esta usando, un boton que no hizo nada. */
function llevarLaVista(zona) {
  try {
    zona.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch { zona.scrollIntoView(); }
}

async function verPrevia(e, zona, cambio, entra, puerta) {
  e.target.disabled = true;
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("srv_calculando")));
  /* Y se lleva la vista hasta ahi. Ponerla arriba no alcanza: si el
     consultor bajo a buscar a alguien en la lista, el resultado le
     queda igual de lejos, solo que del otro lado. */
  llevarLaVista(zona);
  const cuerpo = { ...cambio, [puerta.entra]: entra.persona_id };
  try {
    const r = await api.post(puerta.previa, cuerpo);
    zona.replaceChildren(recuadroPrevia(r, cuerpo, entra, puerta));
  } catch (err) {
    zona.replaceChildren(aviso(err.message, "grave"));
  }
  e.target.disabled = false;
}

/* La hora que parte el dia decide cuanto cobra cada quien y cuanto se le
   factura al cliente. El sistema propone la ultima marca del que sale
   --lo ultimo que se supo de el ese dia-- y aqui se confirma o se
   corrige: un dia estatico, con el ejecutivo en su oficina, puede no
   tener marcas desde el contacto de la manana.

   Solo se manda si el consultor la movio. Si la deja como viene, el
   servidor vuelve a calcular la misma y queda constancia de que nadie
   la toco. */
function campoDeHora(r) {
  const dia = (r.jornadas_partidas || [])[0];
  const propuesta = (r.hora_propuesta || "").slice(11, 16);
  const campo_ = h("input", { type: "time", value: propuesta,
                              style: "width:auto;margin-left:6px" });
  return {
    nodo: h("div", { clase: "chico", style: "margin-top:6px" },
      h("label", {}, t("srv_relevado_a_las"), campo_),
      h("div", { clase: "gris" }, t("srv_hora_relevo_pie"))),
    leer: () => (campo_.value && campo_.value !== propuesta
                 ? `${dia}T${campo_.value}:00` : null),
  };
}

/* Lo delicado de un cambio no es el nombre de quien va: es que quien
   sale se queda con dinero que tiene que comprobar y quien entra
   necesita dinero nuevo. Lo dicen igual el cambio y el regreso, asi que
   se dice en un solo lugar. */
function bloqueDinero(v, entra) {
  const linea = (texto, tono) =>
    h("div", { clase: "chico" + (tono ? "" : " gris") },
      tono ? h("b", {}, texto) : texto);

  const caja = h("div", { style: "margin-top:8px" },
    h("h4", { style: "margin:0 0 2px" }, t("srv_viaticos")));
  for (const x of v.a_comprobar || []) {
    caja.append(linea(
      t("srv_comprueba").replace("{m}", dinero(x.monto))
        .replace("{f}", fecha((x.limite || "").slice(0, 10))), true));
  }
  if ((v.cancelados || []).length) {
    caja.append(linea(
      t("srv_se_cancelan").replace("{n}", v.cancelados.length)));
  }
  /* Propuesta, no asignacion: el sistema saca la cuenta del tabulador
     para que el consultor no tenga que ir a buscarla, pero la solicitud
     la hace el, como con cualquier otra. */
  const propuesto = (v.propuestos || []).reduce((a, x) => a + x.monto, 0);
  if (propuesto) {
    caja.append(linea(
      t("srv_le_tocarian").replace("{p}", entra)
        .replace("{m}", dinero(propuesto))
        .replace("{n}", v.propuestos.length), true));
  }
  if (!(v.a_comprobar || []).length && !propuesto
      && !(v.cancelados || []).length) {
    caja.append(linea(t("srv_nada_mover")));
  }
  return caja;
}

/* ------------------------------------------- el regreso del titular */

/* Una sola pregunta: que dia vuelve. El motivo no se pide --es el del
   cambio que se cierra-- y el ultimo dia del que cubre sale solo, que
   es como lo dice la operacion: "regresa el 25, entonces Luis trabaja
   hasta el 24". */
function abrirRegreso(zona, r) {
  /* Corregir es capturar otra vez: el movimiento se recorre y se vuelve
     a firmar. Lo unico distinto es el techo del calendario --un regreso
     que se atrasa va mas alla del ultimo dia de hoy-- y lo que hay que
     advertir, que es el candado del dinero. */
  const corrige = Boolean(r.regreso_en);
  const minimo = diaSiguiente(r.desde);
  const hoy = new Date().toISOString().slice(0, 10);
  let valor = hoy < minimo ? minimo : hoy;
  if (!corrige && r.hasta && valor > r.hasta) valor = r.hasta;

  const dia = h("input", { type: "date", value: valor, min: minimo });
  if (!corrige && r.hasta) dia.max = r.hasta;

  const previa = h("div", { style: "margin-top:12px" });
  const ver = h("button", { clase: "chico", type: "button",
    onclick: (e) => verPreviaRegreso(e, previa, r, dia.value) },
    t("srv_r_ver"));

  zona.replaceChildren(h("div", { clase: "tarjeta lisa" },
    h("h4", { style: "margin:0 0 2px" },
      (r.tipo === "vehiculo" ? t("srv_r_cuando_u") : t("srv_r_cuando"))
        .replace("{p}", r.sale || "?")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      corrige ? t("srv_r_corregir_pie") : t("srv_r_form_pie")),
    h("div", { clase: "acciones" }, dia, ver),
    previa));
}

function diaSiguiente(iso) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

async function verPreviaRegreso(e, zona, r, desde) {
  if (!desde) return;
  e.target.disabled = true;
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("srv_calculando")));
  llevarLaVista(zona);
  try {
    const previa = await api.post(
      `/contingencia/reemplazos/${r.id}/regreso/vista-previa`, { desde });
    zona.replaceChildren(recuadroRegreso(previa, r, desde));
  } catch (err) {
    zona.replaceChildren(aviso(err.message, "grave"));
  }
  e.target.disabled = false;
}

function recuadroRegreso(p, r, desde) {
  const partido = (p.jornadas_partidas || []).length > 0;
  const hora = partido ? campoDeHora(p) : null;
  const devueltos = (p.jornadas_devueltas || []).length;
  const recuperados = (p.jornadas_recuperadas || []).length;

  const confirmar = h("button", { clase: "chico", type: "button",
    onclick: async (ev) => {
      ev.target.disabled = true;
      try {
        const corregida = hora && hora.leer();
        await api.post(`/contingencia/reemplazos/${r.id}/regreso`,
                       corregida ? { desde, relevado_en: corregida }
                                 : { desde });
        mensaje(t("srv_r_hecho"));
        location.reload();
      } catch (err) {
        mensaje(err.message, "grave");
        ev.target.disabled = false;
      }
    } }, t("srv_r_confirmar"));

  return h("div", { clase: "tarjeta lisa" },
    /* Las dos caras de la misma fecha. La operacion lo dice de las dos
       maneras y confundirlas cuesta un dia de nomina. */
    h("div", { clase: "chico" }, h("b", {},
      t("srv_r_vuelve_el").replace("{p}", p.regresa || "?")
        .replace("{f}", fecha(desde)))),
    h("div", { clase: "chico" },
      t("srv_r_trabaja_hasta").replace("{p}", p.sale || "?")
        .replace("{f}", fecha(p.hasta))),
    h("div", { clase: "chico gris", style: "margin-top:4px" },
      recuperados
        ? t("srv_r_recuperados").replace("{n}", recuperados)
            .replace("{p}", p.sale || "?")
        : t("srv_r_devueltos").replace("{n}", devueltos)
            .replace("{p}", p.regresa || "?")),
    partido
      ? h("div", { style: "margin-top:8px" },
          h("h4", { style: "margin:0 0 2px" }, t("srv_nomina")),
          h("div", { clase: "chico" }, h("b", {},
            t("srv_se_presento").replace("{f}",
              fecha(p.jornadas_partidas[0])))),
          h("div", { clase: "chico gris" },
            t("srv_cobra_dias").replace("{p}", p.regresa || "?")),
          hora.nodo)
      : "",
    p.tipo === "vehiculo" ? "" : bloqueDinero(p.viaticos || {}, p.regresa || "?"),
    bloqueRevisionUnidad(p.revision_pendiente),
    (p.jornadas_con_choque || []).length
      ? aviso(t("srv_choque").replace("{p}", p.regresa || "?")
                .replace("{d}", p.jornadas_con_choque.map(fecha).join(", ")),
              "alerta")
      : "",
    h("div", { clase: "acciones", style: "margin-top:10px" },
      h("button", { clase: "claro chico", type: "button",
        onclick: (ev) => ev.target.closest(".tarjeta").remove() },
        t("srv_cancelar")),
      confirmar));
}

/* Lo que queda pendiente cuando una unidad cambia de manos.

   El motor lo calcula desde hace meses y lo devuelve en la respuesta del
   cambio y del regreso; ninguna pantalla lo pintaba, así que el
   consultor hacía el cambio, el sistema le contestaba qué faltaba, y él
   nunca lo veía.

   Hoy no se pierde: el candado del fin de servicio no deja soltar una
   unidad sin entregar. Lo que se perdía era encargarlo **en el
   momento**, que es cuando la gente todavía está junto a las dos
   camionetas. Ocho horas después ya se fue cada quien por su lado. */
export function bloqueRevisionUnidad(pendiente) {
  if (!pendiente) return "";
  const sale = pendiente.entrega_de_la_que_sale;
  const entra = pendiente.recepcion_de_la_que_entra;
  if (!sale && !entra) return "";

  return h("div", { clase: "aviso alerta", style: "margin-top:8px" },
    h("b", {}, t("uni_rev_titulo")),
    sale ? h("div", { clase: "chico" }, t("uni_rev_sale")) : "",
    entra ? h("div", { clase: "chico" }, t("uni_rev_entra")) : "",
    h("div", { clase: "chico gris", style: "margin-top:4px" },
      t("uni_rev_pie")));
}

function recuadroPrevia(r, cuerpo, entra, puerta) {
  const dias = r.jornadas_afectadas || [];
  const v = r.viaticos || {};

  const dinero_ = bloqueDinero(v, entra.nombre);

  const partido = (r.jornadas_partidas || []).length > 0;
  const hora = partido ? campoDeHora(r) : null;

  const confirmar = h("button", { clase: "chico", type: "button",
    onclick: async (ev) => {
      ev.target.disabled = true;
      try {
        const corregida = hora && hora.leer();
        const hecho = await api.post(
          puerta.guardar,
          corregida ? { ...cuerpo, relevado_en: corregida } : cuerpo);
        /* Quien hace el cambio tiene que saber si el cliente ya se
           enteró o si le toca llamarlo. Sin esto, el consultor se queda
           adivinando y acaba avisando dos veces o ninguna. El implantado
           no manda este correo, así que ahí no se dice nada. */
        mensaje(hecho && hecho.cliente_avisado === true
                ? t("srv_cambio_hecho_avisado")
                : hecho && hecho.cliente_avisado === false
                  ? t("srv_cambio_hecho_sin_aviso")
                  : t("srv_cambio_hecho"));
        setTimeout(() => location.reload(), 1400);
      } catch (err) {
        mensaje(err.message, "grave");
        ev.target.disabled = false;
      }
    } }, t("srv_confirmar_cambio"));

  return h("div", { clase: "tarjeta lisa" },
    h("h4", { style: "margin:0 0 6px" },
      dias.length === 1
        ? fecha(dias[0])
        : t("srv_del_al").replace("{a}", fecha(dias[0]))
            .replace("{b}", fecha(dias[dias.length - 1]))
            .replace("{n}", dias.length)),
    h("div", { clase: "chico" },
      t("srv_entra"), h("b", {}, entra.nombre), t("srv_mismo_rol")),
    /* El consultor pidio "hasta el fin del mes" y el sistema decidio
       cual es ese dia. Decirlo aqui evita que en octubre nadie se
       acuerde de que el cambio ya termino. */
    r.tope_automatico
      ? h("div", { clase: "chico gris", style: "margin-top:4px" },
          t("srv_tope").replace("{f}", fecha(r.hasta)))
      : "",
    /* Lo que hasta hoy se perdia: el que se presento esa manana cobra su
       dia. Decirlo aqui es lo que evita el reclamo de la semana que
       viene. */
    partido
      ? h("div", { style: "margin-top:8px" },
          h("h4", { style: "margin:0 0 2px" }, t("srv_nomina")),
          linea(t("srv_se_presento")
                  .replace("{f}", fecha(r.jornadas_partidas[0])), true),
          linea(t("srv_cobra_dias").replace("{p}", entra.nombre)),
          hora.nodo)
      : h("div", { clase: "chico gris", style: "margin-top:8px" },
          t("srv_no_marco")),
    dinero_,
    bloqueRevisionUnidad(r.revision_pendiente),
    (r.jornadas_con_choque || []).length
      ? aviso(t("srv_choque").replace("{p}", entra.nombre)
                .replace("{d}", r.jornadas_con_choque.map(fecha).join(", ")),
              "alerta")
      : "",
    h("div", { clase: "acciones", style: "margin-top:10px" },
      h("button", { clase: "claro chico", type: "button",
        onclick: (ev) => ev.target.closest(".tarjeta").remove() }, t("srv_cancelar")),
      confirmar));
}

/* ------------------------------------------------ cambios de recurso */

/* El historial existia en la API desde el principio y nadie lo pintaba.
   Sumado por mes y por motivo es el reporte que la direccion va a
   pedir: cuanto ausentismo hay y cuanto cuesta. */
/* Un dia queda dentro de un cambio si cae en su rango. Sin fecha de
   fin, el cambio va de ese dia en adelante. */
function huboCambio(cambios, dia) {
  return (cambios || []).some(
    r => r.desde && r.desde <= dia && (!r.hasta || dia <= r.hasta));
}

function bloqueCambios(filas) {
  const caja = h("div", { clase: "tarjeta" });
  if (!filas || !filas.length) return h("div");

  caja.append(conAyuda("h3", t("srv_cambios"), "ay_srv_cambios",
                         { style: "margin:0 0 2px" }),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("srv_cambios_pie")));

  for (const r of filas) caja.append(tarjetaCambio(r));
  return caja;
}

/* Por que cambio, en el idioma del que lee. Mapa explicito y no la
   cadena cruda: el dia que el motivo se llame de otra forma, aqui se ve
   el hueco en vez de salir en ingles de base de datos. */
const NOMBRE_DEL_MOTIVO = {
  contingencia: "srv_m_contingencia", enfermedad: "srv_m_enfermedad",
  vacaciones: "srv_m_vacaciones", descanso: "srv_m_descanso",
  baja: "srv_m_baja", otro: "srv_m_otro",
  mantenimiento_correctivo: "imp_taller_correctivo",
  mantenimiento_preventivo: "imp_taller_preventivo",
};

function motivoDe(r) {
  const clave = NOMBRE_DEL_MOTIVO[r.motivo_tipo];
  return clave ? t(clave) : (r.motivo_tipo || r.tipo);
}

/* Tres estados y no dos. Un cambio puede haber terminado solo --llego a
   su ultimo dia y nadie lo toco-- o haberlo cerrado alguien porque el
   titular volvio. No es lo mismo: en el segundo caso hubo una decision
   y tiene dueno. */
function selloDelCambio(r) {
  if (r.en_curso) return etiqueta(t("srv_r_en_curso"), "alerta");
  return etiqueta(r.regreso_en ? t("srv_r_cerrado") : t("srv_r_terminado"));
}

function tarjetaCambio(r) {
  const tarjeta = h("div", { clase: "tarjeta lisa", style: "margin:0 0 10px" },
    h("div", {},
      selloDelCambio(r), " ", etiqueta(motivoDe(r), "alerta"), " ",
      h("b", {}, `${r.sale || "?"} → ${r.entra || "?"}`),
      h("span", { clase: "gris chico" },
        t("srv_dias_n").replace("{n}", r.jornadas_afectadas))),
    h("div", { clase: "chico gris" },
      t("srv_desde_f").replace("{f}", fecha(r.desde))
      + (r.hasta ? t("srv_hasta_f").replace("{f}", fecha(r.hasta))
               : t("srv_en_adelante"))),
    r.motivo ? h("p", { clase: "chico", style: "margin:6px 0 0" },
                 `"${r.motivo}"`) : "");

  /* El renglon que importa: quien trabajo media jornada cobra media
     jornada. Hasta hoy eso solo se veia abriendo la nomina --o sea la
     semana siguiente, o sea cuando ya hubo reclamo--. */
  for (const d of r.partidos || []) {
    tarjeta.append(h("div", { clase: "chico", style: "margin-top:4px" },
      t("srv_r_partido").replace("{f}", fecha(d.fecha))
        .replace("{p}", d.quien || r.sale || "?").replace("{h}", d.hora)));
  }

  /* El implantado siempre termina en una fecha, aunque el consultor no
     la haya escrito. Decirlo evita que el mes siguiente nadie se acuerde
     de que el cambio ya termino. */
  if (r.en_curso && r.se_vuelve_a_pedir && r.hasta) {
    tarjeta.append(h("div", { clase: "chico gris", style: "margin-top:4px" },
      t("srv_r_repedir").replace("{f}", fecha(r.hasta))));
  }

  const firma = h("div", { clase: "chico gris", style: "margin-top:4px" },
    r.formalizo ? t("srv_formalizo").replace("{p}", r.formalizo) : "");
  if (r.regreso_en) {
    firma.append(h("div", {},
      t("srv_r_cerro").replace("{p}", r.regreso_por || "?")
        .replace("{f}", fecha(r.regreso_en.slice(0, 10)))));
  }
  tarjeta.append(firma);

  /* El boton va en la tarjeta del movimiento y no en la tabla de dias,
     porque el regreso cierra ESE movimiento: no es un cambio nuevo. Solo
     aparece si sigue corriendo. */
  if (r.en_curso || r.regreso_en) {
    const zona = h("div", { style: "margin-top:10px" });
    tarjeta.append(
      h("div", { clase: "acciones", style: "margin-top:8px" },
        h("button", { clase: "claro chico", type: "button",
          onclick: () => abrirRegreso(zona, r) },
          r.regreso_en
            ? t("srv_r_corregir")
            : (r.tipo === "vehiculo"
               ? t("srv_r_regresar_u") : t("srv_r_regresar")
              ).replace("{p}", r.sale || "?"))),
      zona);
  }

  return tarjeta;
}

/* -------------------------------------------- el dia: punto y agenda */

/* Todo lo del dia en un solo lugar: donde arranca y que se hace. Es la
   misma informacion —la actividad de ese dia— y verla partida en dos
   botones obligaba a abrir y cerrar para armar una idea completa. */
async function abrirDia(zona, jornada, cual = {}) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("srv_abriendo")));

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

  // Y lo que paso ese dia de verdad, debajo de lo que estaba planeado:
  // primero el plan, luego los hechos.
  caja.append(await bloqueDelDia(jornada));

  if (cual.ultimo && !cual.primero) {
    caja.append(punto.vueloDeSalida, punto.guardar);
  }
}

/* ------------------------------------------- lo que paso ese dia */

/* El meet and greet arriba y la bitacora abajo.

   Arriba va una sola pregunta --¿ya estan con el principal?-- porque es
   la que le hacen al consultor por telefono y la que decide si el
   servicio esta corriendo. Debajo, el dia completo para cuando la
   respuesta corta no alcanza.

   El boton de registrarlo a mano sale de `puedo_registrar_a_mano`, que
   lo contesta el servidor: asentar una marca que nadie hizo es de la
   central, no del consultor, que es quien vende el servicio y a quien
   mas le conviene que un dia aparezca trabajado. Las horas de un dia ya
   terminado si las corrige el consultor, con motivo y hasta su visto
   bueno, en "Horas del dia" (seccion 65). */
async function bloqueDelDia(jornada) {
  const zona = h("div", { clase: "dia_real" });
  await pintarDelDia(zona, jornada);
  return zona;
}

async function pintarDelDia(zona, jornada) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, t("srv_abriendo")));
  let d;
  try { d = await api.get(`/operacion/jornadas/${jornada.id}/dia`); }
  catch (err) { return zona.replaceChildren(aviso(err.message, "grave")); }

  const mg = d.meet_and_greet || {};

  /* Un renglon por equipo y por dia, y el titulo lo dice. Un servicio
     puede tener a Alfa en Ciudad de Mexico y a Beta en Monterrey el
     mismo dia: dos bitacoras distintas que no se mezclan nunca, y
     dejarlo al contexto es como se lee la del equipo equivocado. */
  const partes = [
    h("h3", {}, t("dia_titulo")),
    h("div", { clase: "gris chico", style: "margin:-8px 0 12px" },
      t("srv_equipo").replace("{a}", d.equipo || "—"),
      " · ", fecha(d.fecha)),
  ];

  if (mg.hay) {
    const sello = mg.a_mano
      ? h("span", { clase: "etiqueta alerta" }, t("dia_a_mano"))
      : h("span", { clase: "etiqueta ok" }, t("dia_desde_app"));
    partes.push(h("div", { clase: "dia_mg ok" },
      h("div", {}, h("b", {}, hora(mg.momento)), " · ",
        mg.persona || "—", " ", sello),
      mg.a_mano
        ? h("div", { clase: "gris chico" },
            `${t("dia_firmado_por")} ${mg.firmado_por || "—"}`
            + (mg.motivo ? ` · ${mg.motivo}` : ""))
        : null));
  } else {
    partes.push(h("div", { clase: "dia_mg falta" },
      h("div", {}, t("dia_sin_marca")),
      h("div", { clase: "gris chico" },
        `${t("dia_programado")} ${hora(mg.programado)}`)));
    if (d.puedo_registrar_a_mano) {
      partes.push(formularioMeetAndGreet(zona, jornada, mg.quien_falta || []));
    }
  }

  if (d.horas) partes.push(bloqueDeHoras(zona, jornada, d.horas));

  const { bitacoraDelDia } = await import("./bitacora.js");
  partes.push(await bitacoraDelDia(jornada.id));
  zona.replaceChildren(...partes);
}

/* ------------------------------------------- las horas del dia

   Lo programado, desde cuando corren las horas, a que hora termino y
   cuantas extra (seccion 65). Hasta hoy el panel ensenaba la marca de
   fin y nada mas: desde aqui nadie veia si hubo horas extra ni cuantas.

   Corregirlas lo decide el servidor (`puedo_corregir`): la central y la
   direccion, y el consultor de su servicio hasta su visto bueno. La
   hora original se queda guardada con quien la cambio y por que. */
function diaYHora(iso) {
  if (!iso) return "—";
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)} ${hora(iso)}`;
}

function duracion(minutos) {
  const horas = Math.floor(minutos / 60);
  const resto = String(minutos % 60).padStart(2, "0");
  return horas ? t("hd_h_min").replace("{h}", horas).replace("{m}", resto)
               : t("hd_min").replace("{m}", minutos);
}

/* La hora que tenia antes de la primera correccion: la de la calle. */
function original(correcciones, campo) {
  const suyas = (correcciones || []).filter(c => c.campo === campo);
  return suyas.length ? suyas[0].antes : undefined;
}

function bloqueDeHoras(zona, jornada, x) {
  const renglon = (texto, ...valor) =>
    h("tr", {}, h("td", {}, texto), h("td", {}, ...valor));
  const corregida = (campo, actual) => {
    const antes = original(x.correcciones, campo);
    if (antes === undefined) return [h("b", {}, hora(actual))];
    return [antes ? h("span", { clase: "antes" }, hora(antes)) : null,
            h("b", {}, hora(actual)), " ",
            etiqueta(t("hd_corregido"), "alerta")];
  };

  const filas = [renglon(t("hd_programado"),
    h("b", {}, `${hora(x.presentacion)} – ${hora(x.fin_programado)}`),
    x.horas_contratadas
      ? ` · ${t("hd_n_horas").replace("{n}", Number(x.horas_contratadas))}`
      : "")];
  if (x.con_el_ejecutivo) {
    filas.push(renglon(t("hd_con_el_ejecutivo"),
      ...corregida("inicio", x.con_el_ejecutivo),
      x.adelantado
        ? h("span", { clase: "gris chico" }, " ",
            t("hd_adelantado").replace("{h}", hora(x.corren_hasta)))
        : null));
  }
  if (x.termino) {
    filas.push(renglon(t("hd_termino"), ...corregida("fin", x.termino)));
  }
  if (!x.aplica) {
    filas.push(renglon(t("hd_horas_extra"),
      h("span", { clase: "gris" }, t("hd_no_aplica"))));
  } else if (x.en_curso) {
    filas.push(renglon(t("hd_horas_extra"), x.minutos_en_extra
      ? etiqueta(t("hd_en_extra").replace("{t}", duracion(x.minutos_en_extra)),
                 "alerta")
      : h("span", { clase: "gris" },
          t("hd_cumple").replace("{h}", hora(x.corren_hasta)))));
  } else if (x.termino) {
    filas.push(renglon(t("hd_horas_extra"),
      x.horas_extra
        ? etiqueta(t("hd_n_h").replace("{n}", x.horas_extra), "alerta")
        : h("span", {}, t("hd_ninguna")),
      x.horas_extra
        ? h("span", { clase: "gris chico" }, " ",
            t("hd_de_a").replace("{a}", hora(x.corren_hasta))
                        .replace("{b}", hora(x.termino)))
        : null));
  }

  const sellos = (x.correcciones || []).map(c => h("div", { clase: "sello-corr" },
    h("b", {}, t("hd_corregido_por").replace("{q}", c.quien || "—")), " ",
    t("hd_corregido_detalle")
      .replace("{f}", diaYHora(c.en))
      .replace("{c}", t(c.campo === "inicio" ? "hd_campo_inicio" : "hd_campo_fin"))
      .replace("{a}", c.antes ? hora(c.antes) : "—")
      .replace("{d}", hora(c.despues)),
    " «", c.motivo || "", "»"));

  const zonaForm = h("div", {});
  let pie = null;
  if (x.puedo_corregir) {
    pie = h("div", { clase: "acciones" },
      h("button", { clase: "claro chico", type: "button", onclick: () => {
        if (zonaForm.firstChild) return zonaForm.replaceChildren();
        zonaForm.replaceChildren(formularioDeHoras(zona, jornada, x, zonaForm));
      } }, t("hd_corregir")),
      h("span", { clase: "chico gris" },
        x.valida ? t("hd_corregir_pie_central") : t("hd_corregir_pie")));
  } else if (x.por_que_no === "visto_bueno") {
    pie = h("p", { clase: "chico gris", style: "margin:4px 0 0" },
      t("hd_con_visto_bueno"));
  }

  return h("div", { clase: "horas-dia" },
    conAyuda("h4", t("hd_titulo"), "ay_hd"),
    h("table", {}, h("tbody", {}, ...filas)),
    ...sellos, pie, zonaForm);
}

/* La vista previa hace la misma cuenta que el servidor: las horas corren
   desde la presentacion o desde el meet and greet si fue antes, y cada
   hora o fraccion pasado el limite es una hora extra. Solo es para ver
   antes de guardar; la que cuenta es la del servidor. */
function extrasCon(x, inicio, fin) {
  if (!x.aplica || !fin) return 0;
  const presentacion = new Date(x.presentacion);
  const arranque = inicio && new Date(inicio) < presentacion
    ? new Date(inicio) : presentacion;
  const limite = new Date(new Date(x.fin_programado) - (presentacion - arranque));
  const minutos = Math.floor((new Date(fin) - limite) / 60000);
  return minutos > 0 ? Math.ceil(minutos / 60) : 0;
}

function formularioDeHoras(zona, jornada, x, zonaForm) {
  const aLocal = (iso) => (iso || "").slice(0, 16);
  const conSegundos = (v) => (v.length === 16 ? `${v}:00` : v);
  const inicio = entrada("inicio", { type: "datetime-local",
                                     value: aLocal(x.con_el_ejecutivo) });
  const fin = entrada("fin", { type: "datetime-local", value: aLocal(x.termino) });
  const motivo = entrada("justificacion", { placeholder: t("hd_motivo_ph"),
                                            maxlength: 400 });
  const vista = h("div", { clase: "prev" });
  const zonaAviso = h("div", {});

  const repintar = () => {
    if (!x.aplica) return vista.replaceChildren(t("hd_no_aplica"));
    const n = extrasCon(x, inicio.value, fin.value);
    vista.replaceChildren(t("hd_con_estas"), " ",
      h("b", {}, t("hd_n_h_extra").replace("{n}", n)), " ",
      h("span", { clase: "gris" }, t("hd_hoy").replace("{n}", x.horas_extra)));
  };
  inicio.addEventListener("input", repintar);
  fin.addEventListener("input", repintar);
  repintar();

  const guardar = h("button", { clase: "chico", type: "button",
    onclick: async () => {
      if (motivo.value.trim().length < 10) {
        return zonaAviso.replaceChildren(aviso(t("hd_faltan"), "alerta"));
      }
      const cuerpo = { justificacion: motivo.value.trim() };
      if (inicio.value && inicio.value !== aLocal(x.con_el_ejecutivo)) {
        cuerpo.inicio = conSegundos(inicio.value);
      }
      if (fin.value && fin.value !== aLocal(x.termino)) {
        cuerpo.fin = conSegundos(fin.value);
      }
      guardar.disabled = true;
      try {
        await api.post(`/operacion/jornadas/${jornada.id}/horas`, cuerpo);
        await pintarDelDia(zona, jornada);
      } catch (err) {
        guardar.disabled = false;
        zonaAviso.replaceChildren(aviso(err.message, "grave"));
      }
    } }, t("hd_guardar"));

  return h("div", { clase: "tarjeta lisa", style: "margin:12px 0 0" },
    conAyuda("h4", t("hd_corregir_titulo"), "ay_hd_corregir"),
    h("div", { clase: "rejilla dos" },
      campo(t("hd_arranco"), inicio), campo(t("hd_termino"), fin)),
    campo(t("hd_motivo"), motivo),
    vista,
    h("p", { clase: "gris chico", style: "margin:0 0 10px" }, t("hd_form_pie")),
    zonaAviso,
    h("div", { clase: "acciones" }, guardar,
      h("button", { clase: "claro chico", type: "button",
                    onclick: () => zonaForm.replaceChildren() },
        t("hd_cancelar"))));
}

/* Los tres campos se exigen y el boton lo dice antes de mandarlos: un
   403 o un 409 despues de escribir el motivo es la peor forma de
   enterarse de que faltaba la hora. */
function formularioMeetAndGreet(zona, jornada, candidatos) {
  const quien = lista("persona_id",
    candidatos.map(c => ({ valor: c.persona_id,
                           texto: c.rol ? `${c.nombre} — ${c.rol}` : c.nombre })));
  const cuando = entrada("momento", { type: "datetime-local" });
  const motivo = entrada("justificacion",
                         { placeholder: t("dia_motivo_ejemplo"), maxlength: 400 });
  const zonaAviso = h("div", {});

  const boton = h("button", {
    onclick: async () => {
      if (!quien.value || !cuando.value || motivo.value.trim().length < 5) {
        return zonaAviso.replaceChildren(aviso(t("dia_faltan_datos"), "alerta"));
      }
      boton.disabled = true;
      try {
        /* La ruta es la misma de la central (marca-a-mano). Esta llamaba a
           una que no existe, y el formulario contestaba "Not Found". */
        await api.post(`/operacion/jornadas/${jornada.id}/marca-a-mano`, {
          tipo: "contacto_ejecutivo",
          persona_id: Number(quien.value),
          momento: cuando.value.length === 16 ? `${cuando.value}:00` : cuando.value,
          justificacion: motivo.value.trim(),
        });
        await pintarDelDia(zona, jornada);
      } catch (err) {
        boton.disabled = false;
        zonaAviso.replaceChildren(aviso(err.message, "grave"));
      }
    },
  }, t("dia_registrar"));

  if (!candidatos.length) {
    return aviso(t("dia_sin_quien"), "alerta");
  }

  return h("div", { clase: "tarjeta lisa" },
    conAyuda("h4", t("dia_registrar_titulo"), "ay_mg_mano"),
    campo(t("dia_quien"), quien),
    campo(t("dia_cuando"), cuando),
    campo(t("dia_motivo"), motivo),
    zonaAviso,
    h("div", { clase: "acciones" }, boton));
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
        mensaje(t("srv_es_aeropuerto"));
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
          t("srv_google_no_aeropuerto") + t("srv_aeropuerto_confirmar"));
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
      cual.primero ? t("srv_vuelo_llegada")
                   : t("srv_vuelo_salida")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      cual.primero
        ? t("srv_vuelo_llegada_pie")
        : t("srv_vuelo_salida_pie")),
    h("div", { clase: "rejilla tres" },
      campo(t("srv_aerolinea"), aerolinea),
      campo(t("srv_num_vuelo"), numero),
      campo(t("srv_hora"), horaVuelo)),
    campo(cual.primero ? t("srv_procedencia") : t("srv_destino"), procedencia));

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
      ? t("srv_hora_vuelo")
      : (jornada.hora_confirmada
          ? ""
          : t("srv_hora_desconocida").replace("{h}", heredada));
  }
  horaVuelo.addEventListener("input", verHora);

  function verVuelo() { bloqueVuelo.hidden = !enAeropuerto.checked; verHora(); }
  verHora();

  const casillaAeropuerto = puedeVolar
    ? h("label", { clase: "casilla", style: "margin-top:12px" }, enAeropuerto,
        h("span", {}, cual.primero
          ? t("srv_arranca_aeropuerto")
          : t("srv_termina_aeropuerto")))
    : "";

  const guardar = h("button", { type: "button", onclick: async (e) => {
    const punto = lugar.valor();
    if (!punto.direccion) {
      return mensaje(t("srv_donde_arranca"), "alerta");
    }
    if ((punto.lat || punto.lon) && !(punto.lat && punto.lon)) {
      return mensaje(t("srv_pin"),
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

      mensaje(cual.primero ? t("srv_mg_guardado")
                           : t("srv_origen_guardado"));
      // Se recarga para que la pantalla y el task sheet muestren lo
      // guardado, y no lo que se traia de antes.
      setTimeout(() => location.reload(), 700);
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  } }, t("srv_guardar"));

  /* El vuelo de salida se entrega aparte: lo coloca el dia, despues de
     la agenda, porque es con lo que el dia termina. */
  const vueloDeSalida = (cual.ultimo && !cual.primero)
    ? h("div", {}, casillaAeropuerto, bloqueVuelo) : "";

  const nodo = h("div", {},
    cual.primero
      ? h("div", { clase: "destacado" },
          h("h4", {}, t("srv_meet_greet")),
          h("div", { clase: "nota" },
            t("srv_mg_pie")))
      : h("p", { clase: "gris chico", style: "margin:0 0 12px" },
          t("srv_origen_pie")),

    h("div", { clase: "punto-inicio" },
      h("div", {},
        campo(cual.primero ? t("srv_lugar_encuentro")
                           : t("srv_punto_origen"), lugar.direccion),
        lugar.resultados,
        /* Escribir la direccion no fija el punto: hay que elegirla de la
           lista para que Google devuelva sus coordenadas. Sin ellas no
           hay geocerca ni hospitales, y el task sheet no se publica. */
        jornada.origen_direccion && !jornada.origen_lat
          ? aviso(t("srv_sin_pin"), "alerta")
          : ""),
      lugar.cajaMapa),

    // Solo el de llegada va aqui: abre el dia. El de salida lo cierra.
    cual.primero ? h("div", {}, casillaAeropuerto, bloqueVuelo) : "",

    h("h4", { clase: "grupo" }, t("srv_hora_presentacion")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      t("srv_hora_pie")),
    h("div", { clase: "rejilla tres" },
      h("div", { clase: "campo" },
        h("label", {}, t("srv_presentacion")), presentacion, notaHora)),

    h("details", { clase: "plegable" },
      h("summary", {}, t("srv_ajustar_pin")),
      h("p", { clase: "gris chico" },
        t("srv_pin_pie2")),
      h("div", { clase: "rejilla tres" },
        campo(t("srv_latitud"), lugar.lat),
        campo(t("srv_longitud"), lugar.lon),
        campo(t("srv_radio"), lugar.metros))),

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
        t("srv_sin_paradas"))));
    }
    for (const parada of paradas) cuerpo.append(renglon(parada));
  };

  /* Lo capturado antes en dos campos se sigue leyendo en uno solo. */
  const comoTexto = (p) => [p.lugar, p.direccion].filter(Boolean).join(" — ");

  function renglon(parada) {
    const hora_ = h("input", { type: "time", value: parada.hora || "" });
    const lugar = entrada("lugar", { value: comoTexto(parada),
      placeholder: t("srv_parada_ej") });

    const guardar = async () => {
      if (!lugar.value.trim()) return mensaje(t("srv_parada_lugar"),
                                              "alerta");
      try {
        const r = await api.patch(`/operacion/paradas/${parada.id}`, {
          hora: hora_.value ? `${hora_.value}:00` : null,
          lugar: lugar.value.trim(),
          direccion: null,
        });
        Object.assign(parada, r);
        mensaje(t("srv_parada_actualizada"));
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
          mensaje(t("srv_parada_quitada"));
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, t("srv_quitar"));

    return h("tr", {},
      h("td", { clase: "col-hora" }, hora_),
      h("td", {}, lugar),
      h("td", {}, quitar));
  }

  /* --- la parada nueva */
  const nuevaHora = h("input", { type: "time" });
  const nuevoLugar = entrada("lugar", {
    placeholder: t("srv_parada_ej") });

  const agregar = h("button", { type: "button", onclick: async (e) => {
    if (!nuevoLugar.value.trim()) {
      return mensaje(t("srv_parada_donde"), "alerta");
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
      mensaje(t("srv_parada_agregada"));
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  } }, t("srv_agregar_parada"));

  pintar();

  return h("div", {},
    conAyuda("h4", t("srv_agenda"), "ay_srv_agenda", { clase: "grupo" }),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("srv_agenda_pie")),

    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", { clase: "col-hora" }, t("srv_hora")),
        h("th", {}, t("srv_lugar_direccion")), h("th", {}, ""))),
      cuerpo),

    h("div", { clase: "rejilla dos", style: "margin-top:14px" },
      campo(t("srv_hora"), nuevaHora),
      campo(t("srv_lugar_direccion"), nuevoLugar)),
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

  const cabeza = h("p", { clase: "gris chico", style: "margin:0 0 12px" },
    t("srv_hotel_pie"));

  const ficha = h("div");
  if (actual) {
    ficha.append(h("div", { clase: "aviso", style: "margin:0 0 10px" },
      h("b", {}, actual.hotel),
      h("div", { clase: "gris chico" }, actual.direccion || t("srv_sin_direccion")),
      h("div", { clase: "chico num" }, actual.telefono || t("srv_sin_telefono")),
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
          } }, t("srv_quitar")))));
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
        mensaje(t("srv_hotel_sin_tel"),
                "alerta");
      }
    },
  });

  const selHotel = lista("hotel_id",
    [{ valor: "", texto: hoteles.length ? t("srv_del_catalogo")
                                        : t("srv_sin_hoteles") },
     ...hoteles.map(x => ({ valor: x.id, texto: x.nombre }))]);

  /* El boton no existe hasta que hay un hotel que guardar. Un boton que
     esta ahi desde el principio y contesta "elige un hotel" es un viaje
     en falso: mas claro es que aparezca cuando ya hay algo que guardar. */
  const guardar = h("button", { clase: "chico", type: "submit" },
                    actual ? t("srv_cambiar_hotel") : t("srv_guardar_hotel"));
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
      return mensaje(t("srv_elige_hotel"),
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
      mensaje(actual ? t("srv_hotel_corregido") : t("srv_hotel_registrado"));
      await repintar();
    } catch (err) { mensaje(err.message, "grave"); guardar.disabled = false; }
  }});

  f.append(...[campo(t("srv_hotel"), selHotel),
    h("details", { clase: "plegable", open: actual ? null : "" },
      h("summary", {}, t("srv_buscar_hotel")),
      h("div", { clase: "punto-inicio" },
        h("div", {},
          campo(t("buscar_hotel"), buscadorHotel.direccion),
          buscadorHotel.resultados),
        buscadorHotel.cajaMapa),
      h("div", { clase: "rejilla tres" },
        campo(t("srv_nombre_hotel"), nombreLibre),
        campo(t("srv_direccion"), direccionLibre),
        campo(t("srv_telefono"), telefonoLibre))),
    h("div", { clase: "acciones", style: "margin-top:10px" }, guardar)].filter(Boolean));

  /* El hotel nace plegado.
  
     Es informativo y opcional --Centauro no reserva-- y ocupa media
     pantalla entre el buscador de Google, su mapa y los tres campos.
     Quien abre un servicio casi nunca viene a eso; viene por la gente y
     los dias, que quedan arriba. Plegado, el renglon dice si hay hotel
     y cual, que es lo unico que se consulta de corrido. */
  caja.replaceChildren(plegable(
    t("srv_hotel_ejecutivo"), [cabeza, ficha, f],
    () => (actual ? actual.hotel : t("srv_sin_hotel")),
    {}, false));
}

/* ------------------------------------------------------------ task sheet */

/* Quien sabe volver a preguntar que le falta a la hoja. Lo guarda la
   pantalla al armarla, y lo llama el que asigna un recurso. */
let refrescarHoja = null;

function pintarFaltantes(zona, faltantes) {
  if (faltantes && faltantes.length) {
    zona.replaceChildren(
      aviso(t("srv_falta_publicar"), "alerta"),
      h("ul", { clase: "chico" }, ...faltantes.map(x => h("li", {}, x))));
  } else {
    zona.replaceChildren(aviso(t("srv_listo_publicar"), "ok"));
  }
}

async function bloqueTaskSheet(servicio) {
  const caja = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("srv_task_sheet"), "ay_srv_hoja"));
  let vista;
  try {
    vista = await api.get(`/task-sheets/servicio/${servicio.id}/vista-previa`);
  } catch (e) {
    caja.append(aviso(e.message, "alerta"));
    return caja;
  }

  /* Lo que falta para publicar vive en su propia zona y se sabe
     repintar. Se pide una vez al abrir la pantalla, y desde que asignar
     un recurso ya no recarga todo --se repinta en su sitio, para no
     cerrarle el panel al consultor a media tarea-- esta lista se
     quedaba con la foto de antes: el equipo ya estaba puesto y la hoja
     seguia diciendo "sin personal asignado". */
  const zonaFaltantes = h("div", {});
  pintarFaltantes(zonaFaltantes, vista.faltantes);
  caja.append(zonaFaltantes);
  refrescarHoja = async () => {
    try {
      const otra = await api.get(
        `/task-sheets/servicio/${servicio.id}/vista-previa`);
      pintarFaltantes(zonaFaltantes, otra.faltantes);
    } catch { /* si no se puede, se queda lo ultimo que se supo */ }
  };

  if (servicio.tipo === "eventual") {
    caja.append(bloqueVestimenta(servicio));
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
  if (!w) return mensaje(t("srv_bloqueo_ventana"), "alerta");
  w.document.write('<p style="font:14px system-ui;padding:20px">'
                   + t("srv_preparando") + "</p>");
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

/* ------------------------------------------------------ la vestimenta */

/* Como se presenta el equipo. Vive junto a la senal porque las dos son
   lo mismo: como se ve el equipo cuando el ejecutivo lo encuentra. Se
   puede cambiar despues del alta --una cena que se vuelve junta de
   consejo-- y lo que no puede pasar es que el equipo se entere por
   telefono mientras la hoja dice otra cosa. */
function bloqueVestimenta(servicio) {
  const select = h("select", { name: "vestimenta" },
    h("option", { value: "" }, t("vestimenta_sin")),
    ...["casual", "semiformal", "formal"].map(
      v => h("option", { value: v,
                         selected: servicio.vestimenta === v || undefined },
             t(`vest_${v}`))));

  const guardar = h("button", { clase: "claro", onclick: async (e) => {
    e.target.disabled = true;
    try {
      await api.put(`/servicios/${servicio.id}/vestimenta`,
                    { vestimenta: select.value || null });
      servicio.vestimenta = select.value || null;
      mensaje(t("srv_vestimenta_guardada"));
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  } }, t("srv_guardar_vestimenta"));

  return h("div", { style: "margin-top:16px" },
    h("h4", {}, t("srv_vestimenta")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      t("srv_vestimenta_pie")),
    h("div", { clase: "rejilla dos" }, campo(t("vestimenta_campo"), select)),
    h("div", { clase: "acciones", style: "margin-top:10px" }, guardar));
}


/* ----------------------------------------------------------- la senal */

/* Lo que el equipo levanta cuando el ejecutivo sale del filtro. Tres
   formas, y una recomendada: un COLOR --una pantalla de un solo color se
   distingue a veinte metros sin leer nada--, con una palabra encima si
   se quiere; una PALABRA sola en letras grandes; o una IMAGEN del
   cliente. Pedido de Salvador, 22 sep. Es una forma a la vez: al
   guardar una se quita la que estaba. */
function bloqueSenal(servicio, vista) {
  const actual = vista.senal || {};
  const colores = vista.senal_colores || [];
  const zona = h("div", { style: "margin-top:16px" });

  /* Tres formas, y una recomendada. Un servicio nuevo abre en Color; uno
     que ya tenia palabra o imagen abre en la suya. */
  const comoColor = h("input", { type: "radio", name: "senal_como" });
  const comoTexto = h("input", { type: "radio", name: "senal_como" });
  const comoImagen = h("input", { type: "radio", name: "senal_como" });
  if (actual.imagen) comoImagen.checked = true;
  else if (actual.texto && !actual.color) comoTexto.checked = true;
  else comoColor.checked = true;

  let elegido = (actual.color && actual.color.clave)
    || (colores.length ? colores[0].clave : null);
  const colorElegido = () => colores.find(c => c.clave === elegido) || null;
  const nombreColor = () => {
    const c = colorElegido();
    return c ? t(`color_${c.clave}`) : "";
  };

  /* La senal se imprime tal cual se escribe: si el consultor la quiere
     en mayusculas, asi se queda. */
  const texto = entrada("texto", {
    placeholder: "MR. BROOKS", "data-crudo": "",
    value: actual.texto || "" });
  const nota = entrada("nota", { value: actual.nota || "", maxlength: 200 });

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

  /* El telefono como lo vera el principal, en vivo mientras se elige,
     y la frase que va a leer en su hoja. */
  const telefono = h("div", { clase: "senal-telefono" });
  const frase = h("div", { clase: "chico gris", style: "margin-top:8px" });
  const nombre = h("div", { clase: "chico gris", style: "margin:-6px 0 12px" });
  const pintarPrevia = () => {
    const c = colorElegido();
    nombre.textContent = nombreColor();
    telefono.style.background = c ? c.hex : "";
    telefono.style.color = c ? c.letra : "";
    const palabra = h("b", {}, texto.value.trim());
    telefono.replaceChildren(palabra);
    const dice = t("srv_senal_frase").replace("{color}", nombreColor().toLowerCase())
      + (texto.value.trim()
         ? t("srv_senal_frase_palabra").replace("{palabra}", texto.value.trim())
         : "") + ".";
    const renglon = h("b", {}, dice);
    frase.replaceChildren(`${t("srv_senal_hoja")} `, renglon);
  };
  const circulos = h("div", { clase: "senal-colores" });
  const pintarCirculos = () => {
    const botones = colores.map(c => h("button", {
      type: "button",
      clase: "senal-color" + (c.clave === elegido ? " sel" : ""),
      style: `background:${c.hex};color:${c.letra}`,
      title: t(`color_${c.clave}`), "aria-label": t(`color_${c.clave}`),
      onclick: (e) => {
        e.preventDefault();
        elegido = c.clave;
        pintarCirculos();
        pintarPrevia();
      } }, c.clave === elegido ? "✓" : ""));
    circulos.replaceChildren(...botones);
  };
  pintarCirculos();
  texto.addEventListener("input", pintarPrevia);

  const etiquetaTexto = h("label", {}, t("srv_palabra_senal"));
  const cajaColor = h("div", {}, campo(t("srv_elige_color"), circulos), nombre);
  const cajaTexto = h("div", { clase: "campo" }, etiquetaTexto, texto);
  const cajaImagen = h("div", {},
    campo(t("srv_archivo"), archivo),
    h("div", { clase: "chico gris" },
      t("srv_senal_formatos")),
    previa);

  const acomodar = () => {
    cajaColor.hidden = !comoColor.checked;
    telefono.hidden = !comoColor.checked;
    frase.hidden = !comoColor.checked;
    cajaTexto.hidden = !(comoColor.checked || comoTexto.checked);
    etiquetaTexto.textContent = comoColor.checked
      ? t("srv_palabra_encima") : t("srv_palabra_senal");
    cajaImagen.hidden = !comoImagen.checked;
    pintarPrevia();
  };
  for (const r of [comoColor, comoTexto, comoImagen])
    r.addEventListener("change", acomodar);
  acomodar();

  const guardar = h("button", { clase: "claro chico", onclick: async (e) => {
    e.preventDefault();
    const f = archivo.files && archivo.files[0];
    if (comoColor.checked && !elegido)
      return mensaje(t("srv_elige_color"), "alerta");
    if (comoTexto.checked && !texto.value.trim())
      return mensaje(t("srv_escribe_senal"), "alerta");
    if (comoImagen.checked && !f && !actual.imagen)
      return mensaje(t("srv_elige_senal"), "alerta");

    e.target.disabled = true;
    try {
      // Se limpia primero: una senal a la vez.
      await api.borrar(`/servicios/${servicio.id}/senal`);
      const cuerpo = { nota: nota.value.trim() || null };
      if (comoColor.checked) {
        await api.put(`/servicios/${servicio.id}/senal`,
                      { ...cuerpo, color: elegido,
                        texto: texto.value.trim() || null });
      } else if (comoTexto.checked) {
        await api.put(`/servicios/${servicio.id}/senal`,
                      { ...cuerpo, texto: texto.value.trim() });
      } else if (f) {
        await api.subir(`/servicios/${servicio.id}/senal/imagen`, f);
        await api.put(`/servicios/${servicio.id}/senal`, cuerpo);
      } else {
        await api.put(`/servicios/${servicio.id}/senal`,
                      { ...cuerpo, imagen: actual.imagen });
      }
      mensaje(t("srv_senal_guardada"));
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  } }, t("srv_guardar_senal"));

  const quitar = h("button", { clase: "claro chico", onclick: async (e) => {
    e.preventDefault();
    e.target.disabled = true;
    try {
      await api.borrar(`/servicios/${servicio.id}/senal`);
      texto.value = "";
      nota.value = "";
      previa.hidden = true;
      pintarPrevia();
      mensaje(t("srv_senal_quitada"));
    } catch (err) { mensaje(err.message, "grave"); }
    e.target.disabled = false;
  } }, t("srv_quitar_senal"));

  const opcion = (radio, titulo, pie, recomendada) =>
    h("label", { clase: "senal-opcion" + (recomendada ? " recomendada" : "") },
      recomendada ? h("span", { clase: "senal-etiqueta" }, t("srv_senal_recomendada")) : null,
      h("div", {}, radio, " ", h("b", {}, titulo)),
      h("div", { clase: "chico gris" }, pie));

  zona.append(
    conAyuda("h4", t("srv_senal"), "ay_srv_senal", { clase: "grupo" }),
    h("div", { clase: "chico gris", style: "margin-bottom:8px" },
      t("srv_senal_pie")),
    h("div", { clase: "senal-opciones" },
      opcion(comoColor, t("srv_color"), t("srv_color_pie"), true),
      opcion(comoTexto, t("srv_texto"), t("srv_texto_pie"), false),
      opcion(comoImagen, t("srv_imagen"), t("srv_imagen_pie"), false)),
    /* Lo que se captura a la izquierda; el telefono, como lo vera el
       principal, a la derecha y solo cuando la senal es de color. */
    h("div", { clase: "senal-armado" },
      h("div", {}, cajaColor, cajaTexto, cajaImagen,
        campo(t("srv_nota_senal"), nota), frase),
      telefono),
    h("div", { clase: "acciones", style: "margin-top:10px" },
      guardar,
      (actual.texto || actual.imagen || actual.color) ? quitar : ""));
  return zona;
}
/* ------------------------------------------------------------ a bordo */

/* En que unidad va cada quien. Se guarda al momento de elegirla: es un
   dato que cambia en la junta de arranque, con el telefono en la mano,
   y nadie va a buscar un boton de guardar. */
function selectorAbordo(equipo, persona, vehiculos) {
  const sel = lista("abordo", [
    { valor: "", texto: t("srv_en_que_unidad") },
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
      mensaje(r.placa ? t("srv_va_en").replace("{p}", persona.nombre).replace("{v}", r.placa)
                      : t("srv_sin_unidad").replace("{p}", persona.nombre));
    } catch (err) {
      mensaje(err.message, "grave");
      sel.value = persona.vehiculo_id || "";
    }
    sel.disabled = false;
  });

  return h("div", { clase: "abordo" },
    h("span", { clase: "chico gris" }, t("srv_aborda")), sel);
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
function tablaDias(servicio, equipo, cat, cambios = []) {
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
      : h("div", { clase: "chico", style: "color:#b8860b" }, t("srv_desconocida"));
    const nota = h("div", { clase: "chico gris" },
      jornada.hora_confirmada ? "" : t("srv_arranca_h").replace("{h}", heredada));

    const guardar = async (cambios) => {
      try {
        const r = await api.patch(`/servicios/jornadas/${jornada.id}`, cambios);
        mensaje(t("srv_dia_actualizado").replace("{f}", fecha(r.fecha)));
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
    const nombreDia = i === 0 ? t("srv_mg_agenda")
                              : t("srv_origen_agenda");
    const botonDia = h("button", { clase: "claro chico", type: "button",
      onclick: () => {
        const abierta = !filaDia.hidden;
        filaDia.hidden = abierta;
        zonaDia.hidden = abierta;
        botonDia.textContent = abierta ? nombreDia : t("srv_cerrar_dia");
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
          mensaje(t("srv_dia_quitado"));
          location.reload();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, t("srv_quitar"));

    cuerpo.append(
      h("tr", {},
        h("td", { clase: "gris chico" },
          i === 0 ? t("srv_dia_uno") : t("srv_dia_n").replace("{n}", i + 1)),
        h("td", {}, fechaDia),
        h("td", {}, modalidad),
        h("td", { clase: "col-hora" }, hora_, nota, botonDia),
        h("td", { clase: "chico gris" }, etiqueta(jornada.estatus || ""),
          /* Un dia que cambio de gente no se lee igual que uno normal:
             puede traer dos personas en la nomina. */
          huboCambio(cambios, jornada.fecha)
            ? h("span", {}, " ", etiqueta(t("srv_cambio"), "alerta")) : ""),
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
      if (!nuevaFecha.value) return mensaje(t("srv_elige_fecha"), "alerta");
      e.target.disabled = true;
      try {
        await api.post(`/servicios/equipos/${equipo.id}/jornadas`, {
          fecha: nuevaFecha.value,
          modalidad_id: Number(nuevaModalidad.value),
        });
        mensaje(t("srv_dia_agregado"));
        location.reload();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, t("srv_agregar_dia"));

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" },
    h("h4", { style: "margin:0 0 2px" }, t("srv_dias_servicio")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      t("srv_dias_pie")),
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, ""), h("th", {}, t("srv_fecha")), h("th", {}, t("srv_modalidad")),
        h("th", {}, t("srv_pres_actividad")), h("th", {}, t("srv_estatus")),
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
  const NOMBRE = { full_day: t("srv_dia_completo"), medio_dia: t("srv_medio_dia"),
                   transfer: t("srv_transfer") };
  return cat.modalidades
    .filter(m => m.pais_id === pais)
    .map(m => ({ valor: m.id,
                 texto: t("srv_modalidad_h").replace("{m}", NOMBRE[m.codigo] || m.codigo)
        .replace("{h}", Number(m.horas)) }));
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
  por_asignar: { texto: t("srv_por_asignar"), tono: "" },
  asignado: { texto: t("srv_listo_solicitar"), tono: "info" },
  solicitado: { texto: t("srv_con_finanzas"), tono: "alerta" },
  depositado: { texto: t("srv_depositado"), tono: "ok" },
};

const ESTADO_COMPRA = {
  solicitada: { texto: t("srv_solicitada"), tono: "info" },
  en_gestion: { texto: t("srv_gestionando"), tono: "alerta" },
  confirmada: { texto: t("srv_confirmada"), tono: "ok" },
  rechazada: { texto: t("srv_no_se_pudo"), tono: "grave" },
  cancelada: { texto: t("srv_cancelada"), tono: "" },
};

const TIPOS_COMPRA = [
  { valor: "vuelo", texto: t("srv_c_vuelo") },
  { valor: "hospedaje", texto: t("srv_c_hospedaje") },
  { valor: "transporte", texto: t("srv_c_transporte") },
  { valor: "otro", texto: t("srv_m_otro") },
];

async function bloqueViaticos(equipo) {
  const caja = h("div");
  await pintarViaticos(caja, equipo);
  return caja;
}

/* Cuanto se le deposita a cada quien, pedirselo a finanzas y pedir una
   compra lo decide el consultor titular o direccion de operaciones
   (seccion 73). El consultor JR prepara el servicio y aqui ve el dinero
   de su equipo sin moverlo: los campos salen quietos y lo dice. */
function decideElDinero() {
  return tiene(sesion.usuario, "viaticos.asignar");
}

async function pintarViaticos(caja, equipo) {
  caja.replaceChildren(h("div", { clase: "gris chico" }, t("srv_viaticos_cargando")));
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

  const pedirTodo = !decideElDinero()
    ? h("span", { clase: "gris chico" }, t("srv_dinero_titular"))
    : h("button", { clase: "chico", type: "button",
    disabled: porSolicitar ? null : "disabled",
    onclick: async (e) => {
      e.target.disabled = true;
      try {
        await api.post(`/viaticos/equipos/${equipo.id}/solicitar`, {});
        mensaje(t("srv_dep_solicitado"));
        await repintar();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } },
    porSolicitar ? t("srv_solicitar_n").replace("{n}", porSolicitar)
                 : t("srv_solicitar"));

  caja.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" },
    conAyuda("h4", t("srv_viaticos"), "ay_srv_viaticos",
               { style: "margin:0 0 2px" }),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("srv_dep_pie")),
    /* Dinero que salio del banco DESPUES de que se cancelo el deposito.
       Es lo unico de este panel que no se resuelve solo: hay que
       aplicarlo o pedirlo de vuelta, y si no se ve, no pasa ninguna de
       las dos cosas. */
    Number(datos.total_tras_cancelar) > 0
      ? aviso(t("srv_dep_tarde").replace(
          "{m}", dinero(datos.total_tras_cancelar, moneda)), "grave")
      : "",
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, t("srv_persona")),
        h("th", { style: "text-align:right" }, t("srv_propone")),
        h("th", { style: "text-align:right" }, t("srv_se_deposita")),
        h("th", {}, t("srv_estado")))),
      cuerpo),
    h("div", { clase: "acciones", style: "margin-top:10px" },
      pedirTodo,
      h("span", { clase: "chico" },
        h("b", {}, t("srv_total_m").replace("{m}", dinero(datos.total_asignado, moneda))),
        Number(datos.total_depositado) > 0
          ? h("span", { clase: "verde" },
              t("srv_dep_m").replace("{m}", dinero(datos.total_depositado, moneda)))
          : "",
        Number(datos.total_en_camino) > 0
          ? h("span", { clase: "ambar" },
              t("srv_fin_m").replace("{m}", dinero(datos.total_en_camino, moneda)))
          : "",
        Number(datos.total_por_solicitar) > 0
          ? h("span", { clase: "gris" },
              t("srv_sol_m").replace("{m}", dinero(datos.total_por_solicitar, moneda)))
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
  const decide = decideElDinero();
  const monto = entrada("monto", {
    type: "number", step: "1", min: "0", clase: "num",
    disabled: decide ? null : "disabled",
    style: "text-align:right; max-width:130px",
    value: !yaSalio && Number(p.asignado)
             ? String(Math.round(Number(p.asignado))) : "",
    placeholder: yaSalio ? t("srv_otro_deposito")
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
  const usar = (yaSalio || !propuesto || !decide) ? "" : h("button", {
    clase: "claro chico", type: "button",
    title: t("srv_usar_propuesto"),
    onclick: () => { monto.value = String(propuesto); guardar(); } },
    t("srv_usar_m").replace("{m}", dinero(propuesto, moneda)));

  /* Debajo de la cantidad, en que va el dinero. Con dos o tres depositos
     encima, "asignado 2,900" solo no dice si ya salio o falta pedirlo, y
     esa es justo la pregunta del consultor. */
  const linea = (texto, valor, clase = "gris") =>
    Number(valor) > 0
      ? h("div", { clase: `chico ${clase}` },
          t("srv_etiqueta_m").replace("{t}", texto)
      .replace("{m}", dinero(valor, moneda)))
      : "";
  const desglose = h("div", { style: "margin-top:4px; text-align:right" },
    linea(t("srv_depositado"), p.depositado, "verde"),
    linea(t("srv_con_finanzas"), p.en_camino, "ambar"),
    linea(t("srv_por_solicitar"), p.por_solicitar),
    Number(p.asignado) > 0
      ? h("div", { clase: "chico" },
          h("b", {}, t("srv_total_m").replace("{m}", dinero(p.asignado, moneda))))
      : "");

  /* Mientras el dinero no salga, el consultor puede echarse para atras:
     se cae un dia, cambia la gente o se capturo mal el monto. Sin esta
     salida la unica forma de corregir era depositar de mas y andar
     persiguiendo la devolucion. Ya depositado ya no aparece: eso se
     devuelve, no se cancela. */
  const cancelar = (p.estatus !== "solicitado" || !decide) ? "" :
    h("button", { clase: "claro chico", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          const r = await api.post(
            `/viaticos/equipos/${equipo.id}/cancelar-solicitud`,
            { persona_id: p.persona_id });
          /* Lo que ya salio en el barrido esta en manos de finanzas y no
             se cancela desde aqui: queda pedido. Decirlo es lo que evita
             que el consultor lo de por cancelado y borre el dia. */
          mensaje(r && r.pedidos_a_finanzas
                  ? t("srv_sol_pedida_finanzas")
                  : t("srv_sol_cancelada"),
                  r && r.pedidos_a_finanzas ? "alerta" : undefined);
          await repintar();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, t("srv_cancelar_sol"));

  return h("tr", {},
    h("td", {}, h("b", {}, p.nombre),
      h("div", { clase: "chico gris" },
        [p.puesto, t("srv_dias_p").replace("{n}", p.dias)].filter(Boolean).join(" · "))),
    h("td", { style: "text-align:right" },
      h("span", { clase: "num" }, dinero(p.propuesto, moneda))),
    h("td", { style: "text-align:right" },
      h("div", { clase: "acciones", style: "justify-content:flex-end" },
        monto, usar),
      desglose),
    h("td", {}, etiqueta(est.texto, est.tono),
      Number(p.depositado_tras_cancelar) > 0
        ? h("div", { clase: "chico rojo" }, t("srv_dep_tarde_corto"))
        : "",
      Number(p.comprobado) > 0
        ? h("div", { clase: "chico gris" },
            t("srv_comprobado_m").replace("{m}", dinero(p.comprobado, moneda)))
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
      t("srv_sin_compras")));
  }

  const zona = h("div");
  return h("div", { style: "margin-top:18px; border-top:1px solid var(--linea); padding-top:14px" },
    conAyuda("h4", t("srv_compras"), "ay_srv_compras",
             { style: "margin:0 0 2px" }),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("srv_compras_pie")),
    lista_,
    decideElDinero()
      ? h("div", { clase: "acciones", style: "margin-top:10px" },
          alternador(h("button", { clase: "claro chico", type: "button" },
                       t("srv_pedir_compra")),
                     zona,
                     () => zona.replaceChildren(
                       formularioCompra(equipo, zona, repintar))))
      : "",
    zona);
}

function tarjetaCompra(c, moneda, repintar) {
  const est = ESTADO_COMPRA[c.estatus] || ESTADO_COMPRA.solicitada;
  const tipo = (TIPOS_COMPRA.find(t => t.valor === c.tipo) || {}).texto
               || c.tipo;

  const respuesta = h("div");
  if (c.estatus === "confirmada") {
    respuesta.append(h("div", { clase: "aviso ok", style: "margin:8px 0 0" },
      h("div", {}, h("b", {}, t("srv_reserva")),
        h("span", { clase: "num" }, c.confirmacion || "—"),
        c.monto_real
          ? h("span", { clase: "gris" }, t("srv_etiqueta_m").replace("{t}", " ·").replace("{m}", dinero(c.monto_real, moneda)))
          : ""),
      c.respuesta ? h("div", { clase: "chico" }, c.respuesta) : "",
      c.tiene_comprobante ? botonComprobante(c) : ""));
  } else if (c.estatus === "rechazada") {
    respuesta.append(aviso(c.respuesta || t("srv_no_resolvio"),
                           "grave"));
  }

  const puedeCancelar = (c.estatus === "solicitada"
                         || c.estatus === "en_gestion") && decideElDinero();

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 10px" },
    h("div", { clase: "acciones", style: "justify-content:space-between" },
      h("div", {}, h("b", {}, tipo),
        c.monto_estimado
          ? h("span", { clase: "gris chico" },
              t("srv_estimado_m").replace("{m}", dinero(c.monto_estimado, moneda)))
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
            } }, t("srv_cancelar")))
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
      } }, t("srv_ver_comprobante")));
}

function formularioCompra(equipo, zona, repintar) {
  const selTipo = lista("tipo", TIPOS_COMPRA);
  const solicitud = h("textarea", {
    name: "solicitud", rows: "4",
    placeholder: t("srv_compra_ej"),
  });
  const estimado = entrada("estimado", {
    type: "number", step: "0.01", min: "0", placeholder: t("srv_opcional") });

  const guardar = h("button", { clase: "chico", type: "button" },
                    t("srv_enviar_finanzas"));
  const zonaError = h("div");

  guardar.addEventListener("click", async () => {
    if (solicitud.value.trim().length < 10) {
      return zonaError.replaceChildren(aviso(
        t("srv_compra_pie"), "alerta"));
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
      campo(t("srv_que_compra"), selTipo),
      campo(t("srv_monto_estimado"), estimado)),
    campo(t("srv_que_necesita"), solicitud),
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
  frente: t("srv_frente"), atras: t("srv_atras"), izquierdo: t("srv_izquierdo"),
  derecho: t("srv_derecho"), odometro: t("srv_odometro"), dano: t("srv_golpe"),
};

/* Los cuatro lados y el tablero, en ese orden. El odómetro va al final
   porque no es un lado de la camioneta: los cuatro primeros prueban cómo
   estaba la lata, este prueba el número. Sin él, "recorrió 1,800 km" sale
   de dos cifras que alguien tecleó, y esa es la cuenta de la que después
   todos se acuerdan distinto. */
const ANGULOS_LADO_A_LADO = ["frente", "atras", "izquierdo", "derecho",
                             "odometro"];

const OCTAVOS_ES = [t("srv_vacio"), "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8",
                    t("srv_lleno")];

/* Escrito entero a proposito, igual que el mapa de estatus en util.js:
   una clave armada al vuelo --pegando el tipo al prefijo dentro del
   propio t()-- no la puede barrer `revisar.py`, y el dia que falte una
   traduccion sale el codigo crudo en la pantalla sin que nada avise.

   El barrido caza hasta el ejemplo escrito en un comentario, que es
   como se encontro esto. */
const DANOS_ES = {
  rayon: t("srv_dano_rayon"), golpe: t("srv_dano_golpe"),
  cristal: t("srv_dano_cristal"), llanta: t("srv_dano_llanta"),
  mecanico: t("srv_dano_mecanico"), otro: t("srv_dano_otro"),
};

async function bloqueRevisiones(servicio) {
  const caja = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("srv_revision"), "ay_srv_revision"));
  let datos;
  try {
    datos = await api.get(`/servicios/${servicio.id}/revisiones`);
  } catch (e) {
    caja.append(aviso(e.message, "alerta"));
    return caja;
  }

  if (!datos.unidades.length) {
    caja.append(h("p", { clase: "chico gris" },
      t("srv_sin_revision")));
    return caja;
  }

  for (const u of datos.unidades) caja.append(tarjetaRevision(u, servicio));
  return caja;
}

function tarjetaRevision(u, servicio) {
  const bloque = h("div", { clase: "tarjeta lisa", style: "margin:0 0 14px" },
    h("div", { clase: "fila separa" },
      h("b", {}, u.placa || t("srv_sin_placa")),
      u.completa
        ? h("span", { clase: "pastilla ok" }, t("srv_recibida_entregada"))
        : u.recibe
          ? h("span", { clase: "pastilla alerta" }, t("srv_en_manos"))
          : h("span", { clase: "pastilla alerta" }, t("srv_sin_revisar"))));

  /* Las dos banderas, arriba y sin abrir nada. Son la pregunta que uno
     se hace al llegar aqui; tener que desplegar las fotos para saber si
     hubo un golpe es hacerla al reves. */
  if (u.dano_nuevo) {
    bloque.append(aviso(t("srv_volvio_golpeada"), "grave"));
  } else if (u.ya_venia_danada) {
    bloque.append(aviso(t("srv_ya_venia_golpeada"), "alerta"));
  }

  if (u.kilometros != null) {
    bloque.append(h("p", { clase: "chico" },
      h("b", {}, t("srv_km").replace("{n}", u.kilometros.toLocaleString())),
      " recorridos durante el servicio"));
  }

  if (!u.recibe) {
    bloque.append(h("p", { clase: "chico gris" },
      t("srv_sin_entrada")));
    return bloque;
  }

  /* La comparacion no se pinta de entrada: las fotos van como data URI
     y son varios megas por servicio. Esta pantalla se recarga sola en
     casi cada accion del consultor, asi que bajarlas siempre era
     hacerlo esperar por algo que casi nunca mira. Se piden cuando de
     verdad las va a ver, y se piden una sola vez. */
  const zona = h("div", {});
  const abrir = h("button", { clase: "claro chico", style: "margin-top:10px" },
    t("srv_ver_fotos"));

  abrir.addEventListener("click", async () => {
    if (zona.firstChild) {
      zona.replaceChildren();
      abrir.textContent = t("srv_ver_fotos");
      return;
    }
    abrir.disabled = true;
    abrir.textContent = t("srv_bajando_fotos");
    try {
      const conFotos = await api.get(
        `/servicios/${servicio.id}/revisiones?fotos=true`);
      const suya = conFotos.unidades.find(
        x => x.vehiculo_id === u.vehiculo_id);
      zona.replaceChildren(ladoALado(suya.recibe, suya.entrega));
      abrir.textContent = t("srv_ocultar_fotos");
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
    columna(t("srv_al_recibirla"), entrada),
    salida ? columna(t("srv_al_entregarla"), salida)
           : h("div", { clase: "chico gris" }, t("srv_no_se_entrega")));
}

/* Las dos revisiones, angulo por angulo, en el mismo renglon. Ver la
   misma esquina antes y despues es lo unico que hace evidente un golpe
   nuevo; dos galerias separadas obligan a recordar, y nadie recuerda. */
function ladoALado(entrada, salida) {
  const zona = h("div", {});

  const angulos = ANGULOS_LADO_A_LADO;
  const deEntrada = mapaFotos(entrada);
  const deSalida = salida ? mapaFotos(salida) : {};

  for (const a of angulos) {
    zona.append(h("div", { clase: "rejilla-revision par-foto" },
      foto(deEntrada[a], ANGULOS_ES[a]),
      salida ? foto(deSalida[a], ANGULOS_ES[a]) : h("div", {})));
  }

  /* Cada golpe se queda con su punta. Juntos en una sola tira —como
     estaban— se podía ver que la camioneta llegó con un rayón y volvió
     con un cristal roto, y no saber cuál ya venía. Que es exactamente la
     pregunta que uno se está haciendo al abrir esto. */
  const deAca = golpesDe(entrada);
  const deAlla = golpesDe(salida);
  if (deAca.length || deAlla.length) {
    zona.append(h("p", { clase: "chico", style: "margin-top:12px" },
      h("b", {}, t("srv_golpes"))));
    zona.append(h("div", { clase: "rejilla-revision par-foto" },
      tiraDeGolpes(deAca, t("srv_al_recibirla")),
      tiraDeGolpes(deAlla, t("srv_al_entregarla"))));
  }
  return zona;
}

function golpesDe(r) {
  return ((r && r.fotos) || []).filter(f => f.angulo === "dano" && f.imagen);
}

function tiraDeGolpes(fotos, titulo) {
  if (!fotos.length) {
    return h("div", { clase: "chico gris" },
      t("srv_sin_golpes").replace("{p}", titulo.toLowerCase()));
  }
  return h("div", {},
    h("div", { clase: "chico gris" }, titulo),
    h("div", { clase: "tira-fotos" },
      ...fotos.map(f => h("a", { href: f.imagen, target: "_blank" },
        h("img", { clase: "mini", src: f.imagen,
                   alt: f.nota || "golpe" })))));
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
         ? t("srv_km").replace("{n}", r.kilometraje.toLocaleString()) : null,
       r.combustible_octavos != null
         ? t("srv_tanque").replace("{n}", OCTAVOS_ES[r.combustible_octavos]) : null,
       r.tiene_firma ? t("srv_firmada") : t("srv_sin_firma"),
      ].filter(Boolean).join(" · ")),
    declaracion(r),
    r.nota ? h("div", { clase: "chico gris" }, r.nota) : null);
}

/* La declaración de daño, en la columna de su punta.

   Las dos son cosas distintas y por eso se ven distinto: la de la
   izquierda —"así me la dieron"— es lo que **protege** a esa persona
   tres semanas después; la de la derecha —"se dañó conmigo"— es la que
   abre una pregunta. Pintarlas iguales sería cobrarle a quien se portó
   bien. */
function declaracion(r) {
  if (!r || !r.hubo_dano) return null;
  return h("div", { clase: "aviso alerta", style: "margin:6px 0" },
    h("b", {}, DANOS_ES[r.dano_tipo] || r.dano_tipo),
    r.dano_nota ? h("div", { clase: "chico" }, r.dano_nota) : null);
}

function foto(f, etiqueta) {
  if (!f) {
    return h("div", { clase: "sin-foto chico gris" }, t("srv_sin_foto").replace("{e}", etiqueta));
  }
  return h("a", { href: f.imagen, target: "_blank", clase: "marco-foto" },
    h("img", { src: f.imagen, alt: etiqueta }),
    h("span", { clase: "pie" }, etiqueta));
}

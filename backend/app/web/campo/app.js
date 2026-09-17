/* La app del personal de seguridad.

   No es una consola chica: es otra cosa. Quien la usa esta de pie, con
   una mano, a veces de madrugada y casi siempre con prisa. Por eso:

   - abre directo en el dia de hoy, sin menu que navegar
   - ofrece UN paso, el siguiente, no seis botones que hay que leer
   - lo que no se pudo mandar se ve arriba hasta que sale
   - el boton rojo siempre esta, en todas las pantallas

   Todo pasa por el mismo backend y la misma sesion que la consola. */
import { api, sesion, ErrorApi } from "/consola/api.js";
import { encolar, pendientes, vaciar } from "./cola.js";
import { traer, hace, olvidar } from "./memoria.js";
import { reducir } from "./foto.js";

const raiz = () => document.getElementById("app");

const HITOS = {
  llegada_origen: { texto: "Marcar que llegué al punto", corto: "Llegué" },
  contacto_ejecutivo: { texto: "Marcar contacto con el ejecutivo",
                        corto: "Contacto" },
  salida_ruta: { texto: "En ruta", corto: "En ruta" },
  llegada_destino: { texto: "Llegué al destino", corto: "En destino" },
  standby: { texto: "Sigo en espera", corto: "En espera" },
  fin_servicio: { texto: "Terminar el servicio", corto: "Terminado" },
};

let vista = "hoy";

/* --------------------------------------------------------- arranque */

window.addEventListener("hashchange", pintar);
window.addEventListener("online", () => sincronizar(true));
/* El trabajador de fondo entrega los avisos y guarda el armazon de la
   app, para que abra sin senal. Se registra siempre; el permiso de
   avisos se pide aparte y solo cuando tiene sentido. */
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/app/sw.js").catch(() => {});
}
document.addEventListener("DOMContentLoaded", pintar);
pintar();

async function pintar() {
  if (!sesion.token) return entrada();
  if (!sesion.usuario) {
    try { await api.quienSoy(); } catch { return entrada(); }
  }
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
  return new Date(iso).toLocaleTimeString("es-MX",
    { hour: "2-digit", minute: "2-digit" });
}

/* ----------------------------------------------------------- entrada */

function entrada() {
  const correo = h("input", { type: "email", inputmode: "email",
                              autocapitalize: "none", autocomplete: "username" });
  const clave = h("input", { type: "password",
                             autocomplete: "current-password" });
  const error = h("div");
  const boton = h("button", { onclick: () => entrar() }, "Entrar");

  async function entrar() {
    boton.disabled = true;
    error.replaceChildren();
    try {
      await api.entrar(correo.value.trim(), clave.value);
      await api.quienSoy();
      location.hash = "#/hoy";
      pintar();
    } catch (err) {
      error.replaceChildren(aviso(err.message, "grave"));
      boton.disabled = false;
    }
  }

  raiz().replaceChildren(h("div", { clase: "entrada" },
    h("h1", {}, "Centauro"),
    h("p", { clase: "gris" }, "Protección ejecutiva"),
    h("div", { clase: "caja", style: "margin-top:22px" },
      error,
      h("div", { clase: "campo" }, h("label", {}, "Correo"), correo),
      h("div", { clase: "campo" }, h("label", {}, "Contraseña"), clave),
      boton)));
}

/* --------------------------------------------------- la cola arriba */

let sincronizando = false;

async function mandarHito(item) {
  return api.post(`/operacion/jornadas/${item.jornada_id}/hitos`, item.cuerpo);
}

async function sincronizar(silencioso = false) {
  if (sincronizando || !pendientes().length) return;
  sincronizando = true;
  try {
    const r = await vaciar(mandarHito);
    if (r.rechazados.length) {
      alert("No se pudo registrar una marca:\n\n"
            + r.rechazados.map(x => x.motivo).join("\n"));
    }
    if (r.enviados && !silencioso) pintar();
    if (r.enviados && silencioso) pintar();
  } finally { sincronizando = false; }
}

function bandaPendientes() {
  const cuantos = pendientes().length;
  if (!cuantos) return null;
  return h("div", { clase: "pendientes" },
    h("div", {}, `${cuantos} marca(s) sin enviar`),
    h("div", { clase: "chico", style: "font-weight:400;margin-top:4px" },
      "Se guardaron en el teléfono y se mandan solas cuando haya señal."),
    h("button", { clase: "claro chico", style: "margin-top:10px",
      onclick: () => sincronizar() }, "Intentar ahora"));
}

/* --------------------------------------------------------- hoy */

async function pantallaHoy() {
  cargando();
  let r;
  try { r = await traer("mi-dia", () => api.get("/campo/mi-dia")); }
  catch (err) { return conBarra(aviso(err.message, "grave")); }

  const datos = r.datos;
  const hoy = datos.hoy || [];
  const manana = datos.manana || [];

  const cuerpo = [
    h("h1", {}, `Hola, ${(datos.persona || "").split(" ")[0]}`),
    /* Sin senal se muestra lo ultimo que se supo, con su edad escrita.
       Un dato viejo que se sabe viejo sirve; uno viejo que se ve nuevo
       es peor que no tener nada. */
    r.de_memoria ? sinLinea(r.en) : null,
    bandaPendientes(),
  ];

  if (!hoy.length && !manana.length) {
    cuerpo.push(h("div", { clase: "vacio" },
      "No tienes servicios hoy ni mañana."));
  }

  for (const f of hoy) cuerpo.push(tarjetaHoy(f));
  if (manana.length) {
    cuerpo.push(h("h2", {}, "Mañana"));
    for (const f of manana) cuerpo.push(tarjetaManana(f));
    cuerpo.push(ofrecerAvisos(manana.some(x => !x.confirmado)));
  }

  if ((datos.proximos || []).length) {
    cuerpo.push(h("h2", {}, "Después"));
    for (const p of datos.proximos) {
      cuerpo.push(h("div", { clase: "caja" },
        h("div", { clase: "fila separa" },
          h("div", {},
            h("b", {}, new Date(p.fecha + "T12:00:00")
              .toLocaleDateString("es-MX", { weekday: "long", day: "numeric",
                                             month: "long" })),
            h("div", { clase: "chico gris" }, p.punto || "Sin punto")),
          h("b", {}, hora(p.llegar_a_las)))));
    }
  }

  cuerpo.push(botonPanico(hoy[0], datos.central));
  conBarra(...cuerpo);
}

function sinLinea(en) {
  return h("div", { clase: "pendientes" },
    h("div", {}, "Sin conexión"),
    h("div", { clase: "chico", style: "font-weight:400;margin-top:4px" },
      `Esto es lo último que se supo, ${hace(en)}.`));
}

function tarjetaHoy(f) {
  const paso = f.siguiente;
  const caja = h("div", { clase: "caja" },
    h("div", { clase: "fila separa" },
      h("div", {}, h("div", { clase: "grande" }, hora(f.llegar_a_las)),
        h("div", { clase: "chico gris" },
          `Estar en el punto · servicio ${hora(f.presentacion)}`
          + (f.contra_vuelo ? " · contra vuelo" : ""))),
      f.mi_rol ? h("span", { clase: "marca" }, f.mi_rol) : null),

    h("div", { clase: "marco" },
      h("div", { clase: "dato" },
        h("span", { clase: "clave" }, "Punto de encuentro"),
        h("div", {}, f.punto.direccion || "Sin capturar"),
        f.punto.lat
          ? h("a", { clase: "chico", target: "_blank",
              href: `https://www.google.com/maps?q=${f.punto.lat},${f.punto.lon}` },
              "Abrir en el mapa")
          : null),
      f.vuelo
        ? h("div", { clase: "dato" },
            h("span", { clase: "clave" }, "Vuelo"),
            `${f.vuelo.aerolinea || ""} ${f.vuelo.numero || ""} · `
            + hora(f.vuelo.hora))
        : null,
      h("div", { clase: "dato" },
        h("span", { clase: "clave" }, "Ejecutivo"),
        f.ejecutivo || "—"),
      f.unidades.length
        ? h("div", { clase: "dato" },
            h("span", { clase: "clave" }, "Unidad"),
            f.unidades.map(u => `${u.placa}${u.color ? " · " + u.color : ""}`)
              .join(" · "))
        : null,
      f.companeros.length
        ? h("div", { clase: "dato" },
            h("span", { clase: "clave" }, "Con"),
            ...f.companeros.map(c => h("div", {},
              `${c.nombre}${c.rol ? " · " + c.rol : ""} `,
              c.telefono
                ? h("a", { href: `tel:${c.telefono}` }, c.telefono) : null)))
        : null),

    marcados(f),
  );

  /* Un paso a la vez. Seis botones son seis oportunidades de marcar el
     equivocado con prisa. */
  if (paso) {
    caja.append(h("div", { clase: "marco" },
      h("button", { onclick: (e) => marcar(e, f, paso) },
        HITOS[paso].texto),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        paso === "llegada_origen"
          ? `Se puede marcar entre ${hora(f.ventana.abre)} y `
            + `${hora(f.ventana.cierra)}. Hay que estar dentro del punto.`
          : "")));
  }

  if (f.sueltos && f.sueltos.length) {
    caja.append(h("div", { clase: "marco fila", style: "flex-wrap:wrap" },
      ...f.sueltos.map(t => h("button", { clase: "claro chico",
        onclick: (e) => marcar(e, f, t) }, HITOS[t].corto))));
  }

  /* La unidad se revisa cuando cambia de manos, no cada dia. Por eso
     el boton solo aparece cuando de verdad falta algo: sin revisar al
     empezar, o recibida y todavia sin entregar. */
  if (f.revision && f.revision.por_recibir) {
    caja.append(h("div", { clase: "marco" },
      h("a", { href: `#/revision/${f.servicio_id}`, clase: "botonazo" },
        `Revisar la unidad antes de moverla`),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        "Cuatro fotos y tu firma. Es lo único que después prueba cómo "
        + "te la entregaron.")));
  } else if (f.revision && f.revision.por_entregar) {
    caja.append(h("div", { clase: "marco" },
      h("a", { href: `#/revision/${f.servicio_id}`, clase: "chico" },
        "Entregar la unidad →")));
  }

  if (f.hospitales && f.hospitales.length) {
    caja.append(h("div", { clase: "marco" },
      h("span", { clase: "clave gris chico" }, "Hospital más cercano"),
      h("div", {}, f.hospitales[0].nombre),
      f.hospitales[0].telefono
        ? h("a", { href: `tel:${f.hospitales[0].telefono}` },
            f.hospitales[0].telefono)
        : null));
  }
  return caja;
}

function marcados(f) {
  if (!f.marcados.length) return null;
  return h("div", { clase: "marco fila", style: "flex-wrap:wrap;gap:6px" },
    ...f.marcados.map(mm => h("span", {
      clase: `marca ${mm.requiere_revision ? "alerta" : "ok"}`,
    }, `${HITOS[mm.tipo] ? HITOS[mm.tipo].corto : mm.tipo} ${hora(mm.marcado_en)}`
       + (mm.diferido ? " · diferida" : ""))));
}

function tarjetaManana(f) {
  const boton = f.confirmado
    ? h("span", { clase: "marca ok" }, "Confirmado")
    : h("button", { onclick: (e) => confirmar(e, f) },
        "Confirmar que voy");

  return h("div", { clase: "caja" },
    h("div", { clase: "fila separa" },
      h("div", {},
        h("div", { style: "font-size:22px;font-weight:700" },
          hora(f.llegar_a_las)),
        h("div", { clase: "chico gris" }, f.punto.direccion || "Sin punto")),
      f.mi_rol ? h("span", { clase: "marca" }, f.mi_rol) : null),
    h("div", { clase: "marco" }, boton));
}

async function confirmar(e, f) {
  e.target.disabled = true;
  try {
    await api.post(`/operacion/jornadas/${f.jornada_id}/confirmar-recurso`, {});
    pintar();
  } catch (err) {
    alert(err.message);
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

async function marcar(e, f, tipo) {
  const boton = e.target;
  boton.disabled = true;
  const antes = boton.textContent;
  boton.textContent = "Tomando ubicación…";

  const donde = await ubicacion();
  if (!donde && tipo === "llegada_origen") {
    boton.disabled = false;
    boton.textContent = antes;
    return alert("No se pudo tomar tu ubicación.\n\nLa llegada al punto "
                 + "necesita ubicación: es lo que comprueba que estás ahí. "
                 + "Revisa que el permiso esté dado y vuelve a intentar.");
  }

  /* La hora se sella AQUI, no al enviar. Si no hay senal, la marca se
     guarda con este momento y se manda despues: lo que cuenta es cuando
     paso, no cuando llego el mensaje. */
  const cuerpo = {
    tipo,
    marcado_en: new Date().toISOString().slice(0, 19),
    ...(donde ? { lat: String(donde.lat), lon: String(donde.lon) } : {}),
  };

  boton.textContent = "Enviando…";
  try {
    await api.post(`/operacion/jornadas/${f.jornada_id}/hitos`, cuerpo);
    pintar();
  } catch (err) {
    if (err instanceof ErrorApi && err.codigo >= 400 && err.codigo < 500) {
      // El servidor contesto que no. Reintentar no lo va a cambiar.
      boton.disabled = false;
      boton.textContent = antes;
      return alert(err.message);
    }
    // Sin senal: se guarda y se manda solo.
    encolar({ jornada_id: f.jornada_id, cuerpo });
    pintar();
  }
}

/* ------------------------------------------------------- el panico */

function botonPanico(f, central) {
  return h("div", { clase: "caja urgente" },
    h("button", { clase: "panico", onclick: () => panico(f, central) },
      "EMERGENCIA"),
    h("div", { clase: "chico gris", style: "margin-top:10px;text-align:center" },
      "Avisa a la central con tu ubicación. Úsalo solo si hay riesgo."),
    /* Cuando algo se rompe —la app, la señal, el servicio— la salida es
       llamar. Decir "llama a la central" sin dar el número es no decir
       nada. */
    central && central.telefono
      ? h("a", { href: `tel:${central.telefono}`, style: "text-decoration:none" },
          h("button", { clase: "claro", style: "margin-top:10px" },
            `Llamar a la central · ${central.telefono}`))
      : null);
}

async function panico(f, central) {
  if (!confirm("¿Mandar alerta de emergencia a la central?")) return;
  const donde = await ubicacion();
  try {
    await api.post("/contingencia/alertas", {
      canal: "boton_app",
      jornada_id: f ? f.jornada_id : null,
      ...(donde ? { lat: String(donde.lat), lon: String(donde.lon) } : {}),
    });
    alert("Alerta enviada. La central ya la está viendo.");
  } catch (err) {
    const tel = central && central.telefono ? ` al ${central.telefono}` : "";
    alert("No se pudo enviar: " + err.message
          + `\n\nLlama a la central${tel} ahora mismo.`);
    if (central && central.telefono) location.href = `tel:${central.telefono}`;
  }
}

/* ----------------------------------------------------- mis viaticos */

async function pantallaViaticos() {
  cargando();
  let r;
  try { r = await traer("viaticos", () => api.get("/campo/mis-viaticos")); }
  catch (err) { return conBarra(aviso(err.message, "grave")); }
  const d = r.datos;

  const cuerpo = [h("h1", {}, "Mis viáticos"),
    r.de_memoria ? sinLinea(r.en) : null,
    h("p", { clase: "gris chico" },
      "Dinero de la empresa para gastar en el servicio. Lo que no se "
      + "comprueba a tiempo se descuenta.")];

  if (!d.servicios.length) {
    cuerpo.push(h("div", { clase: "vacio" }, "No traes viáticos."));
  }

  for (const s of d.servicios) {
    cuerpo.push(h("div", { clase: `caja ${s.vencido ? "urgente" : ""}` },
      h("div", { clase: "fila separa" },
        h("div", {}, h("b", {}, s.folio),
          h("div", { clase: "chico gris" }, s.cliente || "")),
        s.vencido ? h("span", { clase: "marca grave" }, "Vencido") : null),
      h("div", { clase: "marco" },
        renglon("Te depositaron", `$${s.entregado.toLocaleString("es-MX")}`),
        renglon("Has comprobado", `$${s.comprobado.toLocaleString("es-MX")}`),
        renglon("Te falta comprobar",
                `$${s.por_comprobar.toLocaleString("es-MX")}`,
                s.por_comprobar > 0 ? "ambar" : "verde")),
      s.limite
        ? h("div", { clase: "chico gris" },
            `Fecha límite: ${new Date(s.limite).toLocaleDateString("es-MX")}`)
        : null,
      ...depositos(s),
      s.por_comprobar > 0 ? comprobar(s) : null));
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
      filas.length === 1 ? "Tu depósito" : "Tus depósitos"),
    ...filas.map(d => h("div", { clase: "fila separa",
                                 style: "margin-bottom:6px" },
      h("div", {},
        h("b", { clase: "num" },
          `$${Number(d.monto).toLocaleString("es-MX")}`),
        d.cuando
          ? h("div", { clase: "chico gris" },
              new Date(d.cuando).toLocaleDateString("es-MX"))
          : null,
        d.referencia
          ? h("div", { clase: "chico gris num" }, `Ref ${d.referencia}`)
          : null),
      d.tiene_comprobante
        ? h("a", { clase: "chico", target: "_blank",
                   href: `/viaticos/depositos/${d.id}/comprobante` },
            "Ver comprobante")
        : h("span", { clase: "chico gris" }, "Sin comprobante"))))];
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
  catch (err) { return conBarra(aviso(err.message, "grave")); }
  const d = r.datos;

  const cuerpo = [h("h1", {}, "Mis pagos"),
    r.de_memoria ? sinLinea(r.en) : null];

  /* Lo que va corriendo se enseña como lo que es: una cuenta que
     todavia se puede mover. Un numero que baja sin aviso es la forma
     mas rapida de que el equipo deje de creerle a la app. */
  const curso = d.en_curso;
  cuerpo.push(h("div", { clase: "caja" },
    h("span", { clase: "gris chico" }, "Esta semana, en curso"),
    h("div", { clase: "grande" },
      `$${(curso.total || 0).toLocaleString("es-MX")}`),
    h("div", { clase: "chico gris" }, curso.nota),
    ...(curso.dias || []).map(x => h("div", {
      clase: "fila separa chico", style: "margin-top:8px" },
      h("span", {}, `${x.fecha} · ${x.rol || ""}`),
      h("span", { clase: "num" }, `$${x.monto.toLocaleString("es-MX")}`)))));

  if (!d.cortes.length) {
    cuerpo.push(h("div", { clase: "vacio" }, "Todavía no tienes cortes."));
  }

  for (const c of d.cortes) {
    const abierto = h("div", { hidden: true, clase: "marco" },
      ...c.dias.map(x => h("div", { clase: "fila separa chico",
                                    style: "margin-bottom:6px" },
        h("span", {}, x.descripcion),
        h("span", { clase: "num" }, `$${x.monto.toLocaleString("es-MX")}`))));

    cuerpo.push(h("div", { clase: "caja" },
      h("div", { clase: "fila separa" },
        h("div", {},
          h("b", {}, `Semana del ${c.semana_del}`),
          h("div", { clase: "chico gris" },
            c.pagado ? "Pagado" : "Calculado, todavía no se paga")),
        h("div", { style: "text-align:right" },
          h("b", { clase: "num" }, `$${c.total.toLocaleString("es-MX")}`),
          h("div", {},
            h("span", { clase: `marca ${c.pagado ? "ok" : "alerta"}` },
              c.pagado ? "pagado" : "pendiente")))),
      h("button", { clase: "claro chico", style: "margin-top:10px",
        onclick: () => { abierto.hidden = !abierto.hidden; } }, "Ver días"),
      abierto));
  }
  conBarra(...cuerpo);
}

/* ------------------------------------------------------------- yo */

async function pantallaYo() {
  cargando();
  const cuerpo = [h("h1", {}, sesion.usuario ? sesion.usuario.nombre : "Yo")];

  try {
    const c = await api.get("/campo/mi-calificacion");
    cuerpo.push(h("div", { clase: "caja" },
      h("span", { clase: "gris chico" }, "Mi calificación"),
      h("div", { clase: "grande" }, String(c.calificacion ?? "—")),
      h("div", { clase: "chico gris" },
        `${c.horas_en_centauro || 0} horas en Centauro · confianza `
        + `${c.confianza || "—"}`),
      ...(c.dimensiones || []).filter(x => x.aplica).map(x =>
        h("div", { clase: "fila separa chico", style: "margin-top:8px" },
          h("span", {}, x.dimension),
          h("span", { clase: "num" }, String(x.valor ?? "—"))))));
  } catch { /* sin tablero todavia */ }

  try {
    const cap = await api.get("/campo/mi-capacitacion");
    const caja = h("div", { clase: "caja" },
      h("span", { clase: "gris chico" }, "Mi capacitación"));
    if (!cap.cursos.length) {
      caja.append(h("div", { clase: "gris chico", style: "margin-top:8px" },
        "No tienes cursos cargados."));
    }
    for (const x of cap.cursos) {
      caja.append(h("div", { clase: "fila separa", style: "margin-top:10px" },
        h("div", {}, h("div", {}, x.nombre),
          h("div", { clase: "chico gris" }, x.institucion || "")),
        x.vencida
          ? h("span", { clase: "marca grave" }, "vencida")
          : x.por_vencer
            ? h("span", { clase: "marca alerta" },
                `${x.dias_para_vencer} días`)
            : h("span", { clase: "marca ok" }, "vigente")));
    }
    cuerpo.push(caja);
  } catch { /* sin capacitacion cargada */ }

  cuerpo.push(bloqueAvisos());

  cuerpo.push(h("button", { clase: "claro", onclick: () => {
    /* Al salir se borra lo guardado: el dia de alguien mas no se queda
       en un telefono que cambia de manos. */
    olvidar();
    sesion.token = null; sesion.usuario = null; location.hash = ""; pintar();
  } }, "Salir"));

  conBarra(...cuerpo);
}

/* ---------------------------------------------------------- armazon */

function cargando() {
  raiz().replaceChildren(h("div", { clase: "vacio" }, "Un momento…"));
}

function conBarra(...cuerpo) {
  const enlace = (ruta, icono, texto) => h("a", {
    href: `#/${ruta}`,
    clase: vista === ruta ? "activo" : "",
  }, h("span", { clase: "icono" }, icono), texto);

  raiz().replaceChildren(
    ...cuerpo,
    h("div", { clase: "barra" },
      enlace("hoy", "◉", "Hoy"),
      enlace("viaticos", "▤", "Viáticos"),
      enlace("pagos", "≡", "Pagos"),
      enlace("yo", "☺", "Yo")));

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

const CONCEPTOS = [
  ["alimentos", "Alimentos"],
  ["combustible", "Combustible"],
  ["casetas", "Casetas"],
  ["traslado_personal", "Traslado"],
  ["hospedaje", "Hospedaje"],
  ["otros", "Otros"],
];

function comprobar(servicio) {
  const form = h("div", { hidden: true, clase: "marco" });
  const abrir = h("button", { clase: "claro", style: "margin-top:12px",
    onclick: () => { form.hidden = !form.hidden; } }, "Comprobar un gasto");

  const dia = document.createElement("select");
  for (const d of servicio.dias) {
    dia.append(h("option", { value: d.viatico_id },
      `${d.fecha} · $${d.entregado.toLocaleString("es-MX")}`));
  }
  const concepto = document.createElement("select");
  for (const [v, t] of CONCEPTOS) concepto.append(h("option", { value: v }, t));

  const monto = h("input", { type: "number", inputmode: "decimal",
                             step: "0.01", min: "0", placeholder: "0.00" });
  const nota = h("input", { type: "text", placeholder: "De qué fue" });
  const tipo = document.createElement("select");
  tipo.append(h("option", { value: "nota" }, "Nota o ticket"),
              h("option", { value: "factura" }, "Factura"));

  /* La camara directo: `capture` abre la camara en vez del carrete, que
     es lo que se quiere cuando el ticket esta en la mano. */
  const archivo = h("input", { type: "file", accept: "image/*",
                               capture: "environment" });
  const vista = h("div", { clase: "chico gris", style: "margin-top:6px" });
  let imagen = null;

  archivo.addEventListener("change", async () => {
    const f = archivo.files && archivo.files[0];
    if (!f) return;
    vista.textContent = "Preparando la foto…";
    try {
      imagen = await reducir(f);
      const kb = Math.round(imagen.length * 0.75 / 1024);
      vista.replaceChildren(
        h("img", { src: imagen, style: "max-width:120px;border-radius:8px;"
                                       + "display:block;margin-top:6px" }),
        h("div", { clase: "chico gris" }, `Foto lista · ${kb} KB`));
    } catch (err) {
      imagen = null;
      vista.textContent = err.message;
    }
  });

  const guardar = h("button", { style: "margin-top:6px",
    onclick: (e) => mandar(e) }, "Guardar el comprobante");

  async function mandar(e) {
    if (!monto.value || Number(monto.value) <= 0) {
      return alert("Escribe cuánto fue.");
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
      alert(`Registrado. Te falta comprobar $${Number(r.falta)
        .toLocaleString("es-MX")}.`);
      pintar();
    } catch (err) {
      alert(err.message);
      e.target.disabled = false;
    }
  }

  form.append(
    h("div", { clase: "campo" }, h("label", {}, "Día"), dia),
    h("div", { clase: "campo" }, h("label", {}, "Concepto"), concepto),
    h("div", { clase: "campo" }, h("label", {}, "Monto"), monto),
    h("div", { clase: "campo" }, h("label", {}, "Tipo"), tipo),
    h("div", { clase: "campo" }, h("label", {}, "Nota"), nota),
    h("div", { clase: "campo" },
      h("label", {}, "Foto del ticket"), archivo, vista),
    guardar);

  return h("div", {}, abrir, form);
}


/* Quien entro con una cuenta que no es de campo. */
const NOMBRE_ROL = {
  consultor: "consultor", central: "central de inteligencia",
  finanzas: "finanzas", director_operaciones: "dirección de operaciones",
  director_general: "dirección general", admin: "administrador",
};

function otraCuenta() {
  const suyo = NOMBRE_ROL[sesion.usuario.rol] || sesion.usuario.rol;
  raiz().replaceChildren(h("div", { clase: "entrada" },
    h("div", { clase: "linea" },
      h("span", { clase: "clave" }, "AI/EP"),
      h("span", { clase: "nombre" }, "Protección ejecutiva")),
    h("div", { clase: "caja principal" },
      h("h1", {}, "Esta app es del equipo de campo"),
      h("p", { clase: "gris" },
        `Entraste como ${sesion.usuario.nombre}, ${suyo}. Aquí cada quien `
        + "ve su propio día, sus viáticos y sus pagos, así que solo entra "
        + "el personal de seguridad."),
      h("p", { clase: "gris chico" },
        "Lo tuyo está en la consola."),
      h("button", { style: "margin-top:8px", onclick: () => {
        olvidar();
        sesion.token = null; sesion.usuario = null;
        location.hash = ""; pintar();
      } }, "Entrar con otra cuenta"),
      h("a", { href: "/", style: "text-decoration:none" },
        h("button", { clase: "claro", style: "margin-top:10px" },
          "Ir a la consola")))));
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
    return alert("Este teléfono no puede recibir avisos.\n\n"
                 + "En iPhone hace falta iOS 16.4 o más nuevo y tener la "
                 + "app agregada a la pantalla de inicio.");
  }

  let llave;
  try { llave = await api.get("/campo/push/llave"); }
  catch { return alert("No se pudo preparar los avisos. Intenta más tarde."); }
  if (!llave.activo) {
    return alert("Los avisos todavía no están configurados en el servidor.");
  }

  const permiso = await Notification.requestPermission();
  if (permiso !== "granted") {
    return alert("Sin permiso no se pueden mandar avisos.\n\n"
                 + "Si lo negaste por error, se cambia en los ajustes del "
                 + "navegador para este sitio.");
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
    alert("Listo. Este teléfono ya recibe avisos.");
    pintar();
  } catch (err) {
    alert("No se pudo activar: " + err.message
          + "\n\nEl permiso quedó dado, pero el servidor no te registró. "
          + "Vuelve a intentarlo desde «Yo» cuando tengas señal.");
    pintar();
  }
}

async function probarAviso(e) {
  e.target.disabled = true;
  try {
    await api.post("/campo/push/probar", {});
    alert("Aviso enviado. Debe aparecer en unos segundos.");
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
    h("span", { clase: "gris chico" }, "Avisos en este teléfono"));

  if (estado === "sin_soporte") {
    caja.append(h("p", { clase: "chico gris", style: "margin-top:8px" },
      "Este teléfono no los soporta. En iPhone hace falta iOS 16.4 o más "
      + "nuevo y tener la app agregada a la pantalla de inicio."));
    return caja;
  }
  if (estado === "denied") {
    caja.append(h("p", { clase: "chico gris", style: "margin-top:8px" },
      "Están bloqueados para este sitio. Se vuelven a permitir desde los "
      + "ajustes del navegador."));
    return caja;
  }
  if (estado === "granted") {
    /* El permiso esta, pero eso no quiere decir que el servidor tenga a
       donde mandar. Se pregunta, y mientras llega la respuesta se dice
       lo que se sabe con certeza. */
    const linea = h("p", { clase: "chico gris", style: "margin-top:8px" },
      "Comprobando…");
    const accion = h("div", {});
    caja.append(linea, accion);

    suscripcionDelServidor().then((estado) => {
      if (estado && estado.este_telefono) {
        linea.textContent = "Encendidos. Te va a llegar el recordatorio de "
          + "confirmar el día anterior.";
        accion.replaceChildren(
          h("button", { clase: "claro", onclick: (e) => probarAviso(e) },
            "Mandarme un aviso de prueba"));
        return;
      }
      linea.textContent = "Diste permiso, pero este teléfono no quedó "
        + "registrado en el servidor. No te van a llegar los avisos.";
      accion.replaceChildren(
        h("button", { onclick: () => encenderAvisos() },
          "Volver a intentarlo"));
    });
    return caja;
  }
  caja.append(
    h("p", { clase: "chico gris", style: "margin-top:8px" },
      "Para que te llegue el recordatorio de confirmar, aunque tengas la "
      + "app cerrada."),
    h("button", { onclick: () => encenderAvisos() }, "Encender los avisos"));
  return caja;
}

/* El ofrecimiento en la pantalla de hoy, solo cuando hay algo que
   confirmar: es el aviso que de verdad se va a recibir, asi que es el
   momento en que se entiende para que sirve. */
function ofrecerAvisos(hayManana) {
  if (!hayManana || estadoAvisos() !== "default") return null;
  return h("div", { clase: "caja" },
    h("p", { clase: "chico", style: "margin:0 0 10px" },
      "¿Quieres que te avise el día anterior, sin tener que abrir la app?"),
    h("button", { clase: "claro", onclick: () => encenderAvisos() },
      "Sí, avísame"));
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

const ANGULOS = [
  ["frente", "Frente"],
  ["atras", "Atrás"],
  ["izquierdo", "Costado izquierdo"],
  ["derecho", "Costado derecho"],
];

const OCTAVOS = ["Vacío", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8",
                 "Lleno"];

async function pantallaRevision() {
  cargando();
  const servicioId = Number(location.hash.split("/")[2]);
  let r;
  try { r = await api.get(`/campo/servicios/${servicioId}/unidades`); }
  catch (err) { return conBarra(aviso(err.message, "grave")); }

  const cuerpo = [
    h("a", { href: "#/hoy", clase: "chico" }, "‹ Volver al día"),
    h("h1", {}, "Revisión de unidad"),
    h("div", { clase: "chico gris" }, r.folio),
  ];

  if (!r.unidades.length) {
    cuerpo.push(h("div", { clase: "vacio" },
      "Este servicio no tiene unidad asignada."));
    return conBarra(...cuerpo);
  }

  for (const u of r.unidades) cuerpo.push(tarjetaUnidad(servicioId, u));
  cuerpo.push(h("div", { clase: "chico gris", style: "margin-top:18px" },
    "La revisión se hace una vez por servicio: al recibir la unidad y "
    + "al entregarla. No hay que repetirla cada día."));
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
        ? h("span", { clase: "marca ok" }, "Completa")
        : u.recibida
          ? h("span", { clase: "marca alerta" }, "En tus manos")
          : h("span", { clase: "marca grave" }, "Sin revisar")));

  if (u.recibida) {
    caja.append(h("div", { clase: "marco" },
      resumen("Recibida", u.recibida)));
  }
  if (u.entregada) {
    caja.append(h("div", { clase: "marco" },
      resumen("Entregada", u.entregada),
      (u.recibida && u.recibida.kilometraje != null
       && u.entregada.kilometraje != null)
        ? h("div", { clase: "chico", style: "margin-top:6px" },
            h("b", {}, `${(u.entregada.kilometraje - u.recibida.kilometraje)
              .toLocaleString("es-MX")} km`), " recorridos en el servicio")
        : null));
  }

  if (!u.recibida) {
    caja.append(h("div", { clase: "marco" },
      h("button", { onclick: () => formRevision(servicioId, u, "recibe") },
        "Revisar y recibir la unidad"),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        "Antes de moverla. Después ya no se puede probar cómo la recibiste.")));
  } else if (!u.entregada) {
    caja.append(h("div", { clase: "marco" },
      h("button", { clase: "claro",
        onclick: () => formRevision(servicioId, u, "entrega") },
        "Entregar la unidad"),
      h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
        "Solo cuando la devuelvas. Vas a ver cada foto junto a la de "
        + "cuando la recibiste.")));
  }
  return caja;
}

function resumen(titulo, r) {
  return h("div", {},
    h("div", { clase: "fila separa" },
      h("span", { clase: "clave gris chico" }, titulo),
      h("span", { clase: "chico gris" }, fechaHora(r.momento))),
    h("div", { clase: "chico" },
      [r.persona,
       r.kilometraje != null
         ? `${r.kilometraje.toLocaleString("es-MX")} km` : null,
       r.combustible_octavos != null
         ? `Tanque ${OCTAVOS[r.combustible_octavos]}` : null,
      ].filter(Boolean).join(" · ")),
    r.nota ? h("div", { clase: "chico gris" }, r.nota) : null,
    h("div", { clase: "tiras" },
      ...r.fotos.map(f => h("img", { clase: "tira", src: f.imagen,
                                     alt: f.angulo }))));
}

function fechaHora(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "short" })
         + " · " + hora(iso);
}


/* ------------------------------------------------------ el formato */

function formRevision(servicioId, unidad, tipo) {
  const entrando = tipo === "recibe";
  const antes = {};
  for (const f of (unidad.recibida ? unidad.recibida.fotos : [])) {
    antes[f.angulo] = f.imagen;
  }

  const ranuras = ANGULOS.map(([clave, texto]) =>
    ranura(clave, texto, entrando ? null : antes[clave]));

  const danos = [];
  const cajaDanos = h("div", { clase: "rejilla" });
  const masDano = h("button", { clase: "claro chico",
    onclick: () => {
      const extra = ranura("dano", `Detalle ${danos.length + 1}`, null);
      danos.push(extra);
      cajaDanos.append(extra.nodo);
    } }, "+ Foto de un golpe");

  const km = h("input", { type: "number", inputmode: "numeric", min: "0",
    placeholder: "Kilometraje del tablero" });
  const tanque = document.createElement("select");
  OCTAVOS.forEach((t, i) => tanque.append(h("option", { value: i }, t)));
  tanque.value = 8;
  const nota = h("input", { type: "text",
    placeholder: entrando ? "Lo que ya viene golpeado" : "Cómo la entregas" });

  const firma = lienzoFirma();

  const guardar = h("button", { style: "margin-top:8px" },
    entrando ? "Guardar y recibir la unidad" : "Guardar y entregar");
  guardar.addEventListener("click", () => mandar(guardar));

  const cuerpo = [
    /* Un enlace al mismo hash no dispara nada: el formulario se abrio
       reemplazando el DOM, sin tocar la direccion. Con las cuatro fotos
       ya tomadas, tocar "Volver" y que no pase nada se siente como una
       pantalla congelada. */
    h("a", { href: "#", clase: "chico",
             onclick: (e) => { e.preventDefault(); pantallaRevision(); } },
      "‹ Volver"),
    h("h1", {}, entrando ? "Recibir la unidad" : "Entregar la unidad"),
    h("div", { clase: "chico gris" },
      `${unidad.placa}${unidad.color ? " · " + unidad.color : ""}`),
  ];

  if (!entrando && unidad.recibida) {
    cuerpo.push(h("div", { clase: "aviso alerta", style: "margin-top:12px" },
      "Cada foto sale junto a la de cuando la recibiste. Si hay un golpe "
      + "nuevo, va a saltar solo."));
  }

  cuerpo.push(
    h("div", { clase: "marco" },
      h("h2", {}, "Los cuatro lados"),
      h("div", { clase: "chico gris", style: "margin-bottom:10px" },
        "Los cuatro se piden. Una revisión a medias no sirve para "
        + "discutir un golpe tres semanas después."),
      h("div", { clase: "rejilla" }, ...ranuras.map(r => r.nodo))),

    h("div", { clase: "marco" },
      h("h2", {}, "Golpes que ya trae"),
      cajaDanos, masDano),

    h("div", { clase: "marco" },
      h("div", { clase: "campo" }, h("label", {}, "Kilometraje"), km),
      h("div", { clase: "campo" }, h("label", {}, "Tanque"), tanque),
      h("div", { clase: "campo" }, h("label", {}, "Nota"), nota)),

    h("div", { clase: "marco" },
      h("h2", {}, entrando ? "Firma de quien recibe" : "Firma de quien entrega"),
      firma.nodo,
      h("div", { clase: "fila", style: "margin-top:8px" },
        h("button", { clase: "claro chico", onclick: firma.borrar },
          "Borrar firma"))),

    h("div", { clase: "marco" }, guardar),
  );

  raiz().replaceChildren(h("div", {}, ...cuerpo));
  window.scrollTo(0, 0);

  async function mandar(boton) {
    const fotos = [];
    const faltan = [];
    for (const r of ranuras) {
      if (r.imagen()) fotos.push({ angulo: r.angulo, imagen: r.imagen() });
      else faltan.push(r.texto);
    }
    if (faltan.length) {
      return alert("Faltan fotos: " + faltan.join(", ") + ".");
    }
    for (const d of danos) {
      if (d.imagen()) fotos.push({ angulo: "dano", imagen: d.imagen() });
    }
    if (!km.value) return alert("Escribe el kilometraje del tablero.");
    if (!firma.hayTrazo()) return alert("Falta la firma.");

    boton.disabled = true;
    boton.textContent = "Tomando ubicación…";
    const donde = await ubicacion();
    boton.textContent = `Enviando ${fotos.length} fotos…`;

    try {
      const r = await api.post("/campo/revisiones", {
        servicio_id: servicioId,
        vehiculo_id: unidad.vehiculo_id,
        tipo,
        kilometraje: Number(km.value),
        combustible_octavos: Number(tanque.value),
        nota: nota.value || null,
        firma: firma.imagen(),
        lat: donde ? donde.lat : null,
        lon: donde ? donde.lon : null,
        fotos,
      });
      olvidar("mi-dia");
      const km_recorridos = r.kilometros_recorridos;
      alert(entrando
        ? "Unidad recibida. Queda registrado cómo te la entregaron."
        : "Unidad entregada."
          + (km_recorridos != null
             ? ` ${km_recorridos.toLocaleString("es-MX")} km en el servicio.`
             : ""));
      location.hash = `#/revision/${servicioId}`;
      pintar();
    } catch (err) {
      boton.disabled = false;
      boton.textContent = entrando ? "Guardar y recibir la unidad"
                                   : "Guardar y entregar";
      /* Las fotos no se encolan: son medio mega y la cola vive en el
         telefono. Mas honesto es decir que no salio y que lo intente
         donde haya senal, con las fotos todavia en pantalla. */
      alert(err.message
        + "\n\nLas fotos siguen aquí. Busca señal y vuelve a darle.");
    }
  }
}

/* Una ranura de foto: el cuadro que se toca, la camara, y —cuando se
   entrega— la foto de como estaba al recibirla, al lado. */
function ranura(angulo, texto, referencia) {
  let imagen = null;
  const archivo = h("input", { type: "file", accept: "image/*",
                               capture: "environment", hidden: true });
  const lienzo = h("div", { clase: "ranura",
                            onclick: () => archivo.click() },
    h("span", { clase: "chico gris" }, "Tocar para la foto"));

  archivo.addEventListener("change", async () => {
    const f = archivo.files && archivo.files[0];
    if (!f) return;
    lienzo.replaceChildren(h("span", { clase: "chico gris" }, "Preparando…"));
    try {
      imagen = await reducir(f);
      lienzo.replaceChildren(h("img", { src: imagen, alt: texto }));
      lienzo.classList.add("lista");
    } catch (err) {
      imagen = null;
      lienzo.replaceChildren(h("span", { clase: "chico rojo" }, err.message));
    }
  });

  const nodo = h("div", { clase: "celda" },
    h("div", { clase: "chico", style: "margin-bottom:4px" }, texto),
    referencia
      ? h("div", { clase: "par" },
          h("div", {}, h("div", { clase: "chico gris" }, "Al recibirla"),
            h("img", { clase: "ranura vieja", src: referencia, alt: texto })),
          h("div", {}, h("div", { clase: "chico gris" }, "Ahora"), lienzo))
      : lienzo,
    archivo);

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

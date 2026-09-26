/* Odoo: lo que Centauro lee de ahi (secciones 51, 52, 64, 74, 75 y 77).

   El personal de seguridad y la flota llegan de Odoo. La primera lectura
   de cada una se hace a mano, despues de ver el ensayo, y de ahi en
   adelante se leen solas cada hora. Esa primera vivia en la terminal del
   servidor --sincronizar_personal.py y sincronizar_flota.py--, y el
   servidor de produccion ya no se abre por SSH: se hace aqui, con el
   mismo ensayo y el mismo aplicar.

   Lo pendiente es la lista de lo que hay que corregir en Odoo, con el
   No. Odoo de cada quien para encontrarlo alla. Se corrige en Odoo y la
   siguiente lectura lo toma sola: nada se captura dos veces.

   Nada de esta pantalla escribe en Odoo. */
import { api } from "./api.js";
import { aviso, conAyuda, fecha, h, hora, mensaje, plegable,
         sinTildes } from "./util.js";
import { t } from "./idioma.js";

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (s, [k, v]) => s.split(`{${k}}`).join(v ?? ""), texto);
}

/* "jue 24 sep 2026 a las 09:10". */
function cuando(iso) {
  return reemplazar(t("odo_cuando"), { fecha: fecha(iso), hora: hora(iso) });
}

/* "hace 12 min", "hace 3 h", "hace 2 dias": la de cada hora se mira
   para saber si sigue viva, y para eso basta la unidad grande. */
function hace(iso) {
  const minutos = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (minutos < 60) return reemplazar(t("odo_hace_min"), { n: minutos });
  if (minutos < 48 * 60) {
    return reemplazar(t("odo_hace_h"), { n: Math.round(minutos / 60) });
  }
  return reemplazar(t("odo_hace_d"), { n: Math.round(minutos / 1440) });
}

/* Lo que el servidor dice de cada pendiente, en el idioma de quien mira.
   Los mapas van escritos enteros a proposito: una clave armada al vuelo
   no se encuentra buscandola. Lo que no este aqui sale como lo dijo el
   servidor, que es mejor que no decir nada. */
const FALTAS = {
  "sin plaza": "odo_f_sin_plaza",
  "sin correo personal": "odo_f_sin_correo",
  "correo mal escrito": "odo_f_correo_mal",
  "correo con error de dedo": "odo_f_correo_dedo",
  "correo repetido en Odoo": "odo_f_correo_repetido",
  "su correo ya es de otro acceso en Centauro": "odo_f_correo_otro_acceso",
  "su correo ya es de otra persona en Centauro": "odo_f_correo_otra",
  "su correo nuevo ya es de otra persona en Centauro": "odo_f_correo_nuevo_otra",
  "activo en Odoo pero dado de baja en Centauro: reactivar a mano":
    "odo_f_reactivar_persona",
  "ya no tiene puesto de seguridad en Odoo": "odo_f_sin_puesto",
  /* La oficina (seccion 74). */
  "correo de trabajo mal escrito": "odo_f_trabajo_mal",
  "correo de trabajo con error de dedo": "odo_f_trabajo_dedo",
  "correo de trabajo repetido en Odoo": "odo_f_trabajo_repetido",
  "en Centauro es personal de seguridad; en Odoo ya no": "odo_f_era_seguridad",
  "su correo es de alguien del personal de seguridad en Centauro":
    "odo_f_correo_de_seguridad",
  "ahora es personal de seguridad en Odoo": "odo_f_ahora_seguridad",
  /* Los clientes (seccion 75). */
  "sin pais": "odo_f_sin_pais",
  "se parece a mas de un cliente de Centauro": "odo_f_cliente_doble",
  "ya no trae la etiqueta de Proteccion Ejecutiva en Odoo": "odo_f_sin_etiqueta",
  "sin placa": "odo_f_sin_placa",
  "placa repetida en Odoo": "odo_f_placa_repetida",
  "sin categoria": "odo_f_sin_categoria",
  "su placa ya es de otra unidad en Centauro": "odo_f_placa_otra",
  "su placa nueva ya es de otra unidad en Centauro": "odo_f_placa_nueva_otra",
  "activa en Odoo pero dada de baja en Centauro: reactivar a mano":
    "odo_f_reactivar_unidad",
  "ya no es de Proteccion Ejecutiva en Odoo": "odo_f_no_es_pe",
  "revisar en Odoo": "odo_f_revisar",
  "sin fecha de entrada": "odo_f_taller_sin_entrada",
  "la salida es antes que la entrada": "odo_f_taller_al_reves",
  "terminado sin fecha de salida: se tomo el dia de entrada":
    "odo_f_taller_sin_salida",
};

/* Los que traen un nombre adentro: la plaza o la categoria que Odoo
   tiene y Centauro no. Van con su nombre porque es justo lo que hay que
   corregir. */
const CON_NOMBRE = [
  [/^la plaza «(.*)» no existe en Centauro$/, "odo_f_plaza_no_existe"],
  [/^el pais «(.*)» no existe en Centauro$/, "odo_f_pais_no_existe"],
  [/^la categoria «(.*)» no existe en Centauro$/, "odo_f_categoria_no_existe"],
];

function falta(texto) {
  if (FALTAS[texto]) return t(FALTAS[texto]);
  for (const [patron, clave] of CON_NOMBRE) {
    const hallado = String(texto).match(patron);
    if (hallado) return reemplazar(t(clave), { x: hallado[1] });
  }
  return texto;
}

/* Que le cambia a cada quien. La llave va sin acentos porque asi se
   compara: el servidor dice "año" y aqui se busca "ano". */
const QUE = {
  nombre: "odo_q_nombre", plaza: "odo_q_plaza", celular: "odo_q_celular",
  referencia: "odo_q_referencia", "fecha de ingreso": "odo_q_ingreso",
  correo: "odo_q_correo", placa: "odo_q_placa", categoria: "odo_q_categoria",
  "marca y modelo": "odo_q_modelo", color: "odo_q_color", ano: "odo_q_anio",
  puesto: "odo_q_puesto", area: "odo_q_area", rfc: "odo_q_rfc",
  pais: "odo_q_pais",
};

function que(lista) {
  return (lista || []).map(x => (QUE[sinTildes(x)] ? t(QUE[sinTildes(x)]) : x))
    .join(", ");
}

const MOTIVOS = {
  "archivado en Odoo": "odo_b_archivado",
  "archivada en Odoo": "odo_b_archivada",
  "ya no esta en Odoo": "odo_b_ya_no_esta",
  "se cierra": "odo_b_se_cierra",
  "sigue abierto hasta que compruebe sus viaticos": "odo_b_viaticos",
  "no tenia": "odo_b_no_tenia",
};

function motivo(texto) {
  return MOTIVOS[texto] ? t(MOTIVOS[texto]) : (texto || "");
}

/* Las dos lecturas se portan igual; cambia de donde leen y como se
   cuentan. `quien` es lo que sale en cada renglon de sus listas. */
const LECTURAS = {
  personal: {
    ensayo: "/odoo/personal/ensayo", aplicar: "/odoo/personal/sincronizar",
    leidos: (d) => reemplazar(t("odo_leidos_personal"),
                              { n: d.leidos, s: d.sin_cambio }),
    quien: (x) => x.nombre || "—",
    pieAltas: "odo_altas_personal_pie", pieBajas: "odo_bajas_personal_pie",
    confirmar: "odo_confirmar_personal",
  },
  flota: {
    ensayo: "/odoo/flota/ensayo", aplicar: "/odoo/flota/sincronizar",
    leidos: (d) => reemplazar(t("odo_leidos_flota"),
                              { n: d.leidas, s: d.sin_cambio }),
    quien: (x) => x.placa || "—",
    pieAltas: "odo_altas_flota_pie", pieBajas: "odo_bajas_flota_pie",
    confirmar: "odo_confirmar_flota",
  },
  /* La oficina (seccion 74): llega la persona, no su acceso. El acceso
     lo da Recursos Humanos en Accesos, con el puesto sugerido. */
  /* Los clientes (seccion 75): llegan sin tarifario, que se les pone en
     Centauro. */
  clientes: {
    ensayo: "/odoo/clientes/ensayo", aplicar: "/odoo/clientes/sincronizar",
    leidos: (d) => reemplazar(t("odo_leidos_clientes"),
                              { n: d.leidos, s: d.sin_cambio }),
    quien: (x) => x.nombre || "—",
    pieAltas: "odo_altas_clientes_pie", pieBajas: "odo_bajas_clientes_pie",
    confirmar: "odo_confirmar_clientes",
  },
  oficina: {
    ensayo: "/odoo/oficina/ensayo", aplicar: "/odoo/oficina/sincronizar",
    leidos: (d) => reemplazar(t("odo_leidos_oficina"),
                              { n: d.leidos, s: d.sin_cambio }),
    quien: (x) => x.nombre || "—",
    pieAltas: "odo_altas_oficina_pie", pieBajas: "odo_bajas_oficina_pie",
    confirmar: "odo_confirmar_oficina",
  },
  /* Los tarifarios (seccion 77) no se cuentan en altas y bajas sino en
     listas, precios y clientes: traen su propio informe y sus cifras. */
  tarifarios: {
    ensayo: "/odoo/tarifarios/ensayo", aplicar: "/odoo/tarifarios/sincronizar",
    confirmar: "odo_confirmar_tarifarios",
    cifras: (d) => ({ l: d.leidas, p: d.precios, c: d.clientes,
                      x: d.cambian.length }),
    etiqueta: "odo_aplicar_listas",
    informe: (d) => informeTarifas(d),
  },
};

/* Leer Odoo entero y sus fotos lleva mas que una pantalla comun: con
   setenta personas y mala conexion, los 25 segundos de siempre se
   quedan cortos y la lectura parece fallar cuando solo iba lenta. */
const SEGUNDOS = 120;

export async function pantallaOdoo(main) {
  const cabeza = h("div");
  const personal = h("div");
  const flota = h("div");
  const oficina = h("div");
  const clientes = h("div");
  const listas = h("div");
  const tarifas = h("div");
  const historial = h("div");
  main.append(
    h("h1", {}, t("nav_odoo")),
    h("p", { clase: "sub" }, t("odo_sub")),
    cabeza, personal, flota, oficina, clientes, listas, tarifas, historial);

  let estado;
  try {
    estado = await api.get("/odoo/estado");
  } catch (err) {
    return cabeza.replaceChildren(aviso(err.message, "grave"));
  }
  /* Despues de aplicar se vuelve a pintar solo esa tarjeta --ya con su
     "ultima lectura" y con lo que se hizo a la vista-- y el historial.
     La otra se queda como estaba: si tenia un ensayo abierto, sigue ahi. */
  const cajas = { personal, flota, oficina, clientes, tarifarios: listas };
  const repintar = async (tipo, hecho) => {
    try {
      const nuevo = await api.get("/odoo/estado");
      tarjeta(cajas[tipo], tipo, nuevo, repintar, hecho);
      pintarHistorial(historial, nuevo);
      if (tipo === "clientes" || tipo === "tarifarios") sinTarifario(tarifas, nuevo);
    } catch (err) {
      mensaje(err.message, "grave");
    }
  };

  cabeza.replaceChildren(estado.conectado
    ? h("p", { clase: "gris chico", style: "margin:0 0 14px" },
        reemplazar(t("odo_conectado"), { sitio: estado.sitio || "Odoo" }))
    : h("div", { style: "margin:0 0 14px" },
        aviso(t("odo_sin_conexion"), "alerta")));
  tarjeta(personal, "personal", estado, repintar);
  tarjeta(flota, "flota", estado, repintar);
  tarjeta(oficina, "oficina", estado, repintar);
  tarjeta(clientes, "clientes", estado, repintar);
  tarjeta(listas, "tarifarios", estado, repintar);
  sinTarifario(tarifas, estado);
  pintarHistorial(historial, estado);
}

/* ------------------------------------------------------------ tarjeta */

function comoVa(tipo, estado) {
  const e = estado[tipo] || {};
  if (!e.primera_hecha) return [h("p", { clase: "gris", style: "margin:0" },
                                     t("odo_nunca"))];
  const a = e.ultima_a_mano;
  const renglones = [h("p", { clase: "gris", style: "margin:0" },
    reemplazar(t("odo_ultima_a_mano"),
               { cuando: cuando(a.hecha_en), quien: a.hecha_por || "—" }))];
  renglones.push(h("p", { clase: "gris", style: "margin:2px 0 0" },
    e.ultima_sola
      ? reemplazar(t("odo_sola"), { hace: hace(e.ultima_sola.hecha_en) })
      : t("odo_sola_aun_no")));
  return renglones;
}

function tarjeta(caja, tipo, estado, repintar, mostrar = null) {
  const cfg = LECTURAS[tipo];
  const resultado = h("div");
  const confirmar = h("div");
  const ensayo = h("button", { type: "button", clase: "claro" }, t("odo_ensayo"));
  const aplicar = h("button", { type: "button", disabled: "disabled" },
                    t("odo_aplicar"));
  const nota = h("span", { clase: "gris chico" }, t("odo_primero_ensayo"));
  let ultimo = null;

  if (!estado.conectado) {
    ensayo.disabled = true;
    nota.textContent = "";
  }

  ensayo.addEventListener("click", async () => {
    ensayo.disabled = true;
    aplicar.disabled = true;
    confirmar.replaceChildren();
    resultado.replaceChildren(h("p", { clase: "gris" }, t("odo_leyendo")));
    try {
      ultimo = await api.get(cfg.ensayo, { segundos: SEGUNDOS });
      resultado.replaceChildren(informe(tipo, ultimo));
      /* Sin la etiqueta de los clientes no hay nada que aplicar. */
      aplicar.disabled = !!ultimo.sin_etiqueta;
      aplicar.textContent = reemplazar(t(cfg.etiqueta || "odo_aplicar_cifras"),
                                       (cfg.cifras || cifras)(ultimo));
      nota.textContent = "";
    } catch (err) {
      ultimo = null;
      resultado.replaceChildren(aviso(err.message, "grave"));
    } finally {
      ensayo.disabled = false;
    }
  });

  /* Aplicar pide que se diga que si, en la misma tarjeta: una ventana
     del navegador bloquea la pagina y se contesta sin leer. Lo que se
     confirma son las cifras del ensayo que se tiene enfrente. */
  aplicar.addEventListener("click", () => {
    if (!ultimo) return;
    const si = h("button", { type: "button" }, t("odo_si_aplicar"));
    const no = h("button", { type: "button", clase: "claro" }, t("cancelar"));
    no.addEventListener("click", () => confirmar.replaceChildren());
    si.addEventListener("click", async () => {
      si.disabled = true;
      no.disabled = true;
      ensayo.disabled = true;
      aplicar.disabled = true;
      confirmar.replaceChildren(h("p", { clase: "gris" }, t("odo_guardando")));
      try {
        const hecho = await api.post(cfg.aplicar, {}, { segundos: SEGUNDOS });
        mensaje(t("odo_aplicado"));
        await repintar(tipo, hecho);
      } catch (err) {
        confirmar.replaceChildren(aviso(err.message, "grave"));
        ensayo.disabled = false;
        aplicar.disabled = false;
      }
    });
    confirmar.replaceChildren(h("div", { clase: "aviso alerta", style: "margin:12px 0 0" },
      h("p", { style: "margin:0 0 10px" },
        reemplazar(t(cfg.confirmar), (cfg.cifras || cifras)(ultimo))),
      h("div", { clase: "acciones" }, si, no)));
  });

  if (mostrar) resultado.replaceChildren(informe(tipo, mostrar));
  const titulo = tipo === "personal"
    ? conAyuda("h3", t("odo_personal"), "ay_odo_personal")
    : tipo === "oficina"
      ? conAyuda("h3", t("odo_oficina"), "ay_odo_oficina")
      : tipo === "clientes"
        ? conAyuda("h3", t("odo_clientes"), "ay_odo_clientes")
        : tipo === "tarifarios"
          ? conAyuda("h3", t("odo_tarifarios"), "ay_odo_tarifarios")
          : conAyuda("h3", t("odo_flota"), "ay_odo_flota");
  caja.replaceChildren(h("div", { clase: "tarjeta" },
    titulo,
    ...comoVa(tipo, estado),
    h("div", { clase: "acciones", style: "margin-top:12px" }, ensayo, aplicar, nota),
    confirmar,
    resultado));
}

/* Quien se vincula y ademas trae algo distinto sale en las dos listas:
   se cuenta una vez, igual que en el renglon de la lectura. */
function tocadas(d) {
  return new Set([...d.cambios, ...d.vinculadas]
    .map(x => x.persona_id ?? x.vehiculo_id ?? x.cliente_id)).size;
}

function cifras(d) {
  return { altas: d.altas.length, cambios: tocadas(d),
           vinculadas: d.vinculadas.length, bajas: d.bajas.length };
}

/* ------------------------------------------------------------ informe */

function celda(titulo, numero, pie, color) {
  return h("div", {},
    h("div", { clase: "chico gris" }, titulo),
    h("div", { clase: "cifra", style: color ? `color:${color}` : "" },
      String(numero)),
    h("div", { clase: "chico gris" }, pie));
}

function informe(tipo, d) {
  const cfg = LECTURAS[tipo];
  if (cfg.informe) return cfg.informe(d);
  /* Sin la etiqueta de los clientes en Odoo no se lee a nadie: se dice
     que falta y donde se pone, y nada mas. */
  if (d.sin_etiqueta) {
    return h("div", { style: "margin:14px 0 0" },
      aviso(reemplazar(t("odo_sin_etiqueta"), { e: d.sin_etiqueta }), "alerta"));
  }
  const pendientes = tipo === "flota"
    ? d.pendientes.concat((d.taller || {}).pendientes || [])
    : d.pendientes;

  const partes = [
    h("p", { clase: "gris chico", style: "margin:14px 0 0" },
      reemplazar(t(d.ensayo ? "odo_ensayo_de" : "odo_aplicado_de"),
                 { hora: hora(new Date().toISOString()) }),
      " · ", cfg.leidos(d)),
    h("div", { clase: "camino", style: "background:#fff;margin:8px 0 12px" },
      celda(t("odo_altas"), d.altas.length, t(cfg.pieAltas)),
      celda(t("odo_cambios"), tocadas(d),
            reemplazar(t("odo_cambios_pie"), { v: d.vinculadas.length })),
      celda(t("odo_bajas"), d.bajas.length, t(cfg.pieBajas),
            d.bajas.length ? "var(--grave)" : ""),
      celda(t("odo_pendientes"), pendientes.length, t("odo_pendientes_pie"),
            pendientes.length ? "var(--alerta)" : ""),
      /* La oficina que no tiene correo de trabajo no puede llegar: es
         la lista que RH corrige en Odoo, y se cuenta aparte. */
      tipo === "oficina"
        ? celda(t("odo_sin_correo_trabajo"), (d.sin_correo || []).length,
                t("odo_sin_correo_trabajo_pie"),
                (d.sin_correo || []).length ? "var(--alerta)" : "")
        : "",
      /* Sin RFC se le pueden dar servicios, pero no facturar: se cuenta
         aparte, que es lo que facturacion corrige en Odoo. */
      tipo === "clientes"
        ? celda(t("odo_sin_rfc"), (d.sin_rfc || []).length, t("odo_sin_rfc_pie"),
                (d.sin_rfc || []).length ? "var(--alerta)" : "")
        : ""),
  ];

  /* Lo pendiente no se pliega: es la lista de trabajo de RH, y un bloque
     cerrado es un bloque que nadie abre. Lleva su "?" porque es lo
     primero que alguien pregunta: por que esta persona no entro. */
  if (pendientes.length) {
    partes.push(h("div", { style: "margin:4px 0 10px" },
      conAyuda("h4", `${t("odo_l_pendientes")} (${pendientes.length})`,
               "ay_odo_pendientes"),
      listaDePendientes(pendientes, cfg)));
  }
  if (d.altas.length) {
    partes.push(plegable(`${t("odo_l_altas")} (${d.altas.length})`,
      renglones(d.altas, (x) => [cfg.quien(x), detalleAlta(tipo, x)]),
      null, {}, false));
  }
  if (d.vinculadas.length) {
    partes.push(plegable(`${t("odo_l_vinculadas")} (${d.vinculadas.length})`,
      renglones(d.vinculadas, (x) => [cfg.quien(x), noOdoo(x.odoo_id)]),
      null, {}, false));
  }
  if (d.cambios.length) {
    partes.push(plegable(`${t("odo_l_cambios")} (${d.cambios.length})`,
      renglones(d.cambios, (x) => [cfg.quien(x), que(x.que)]),
      null, {}, false));
  }
  if (d.bajas.length) {
    partes.push(plegable(`${t("odo_l_bajas")} (${d.bajas.length})`,
      renglones(d.bajas, (x) => [cfg.quien(x), detalleBaja(x)]),
      null, {}, true));
  }
  if (tipo === "clientes") {
    const sinRfc = d.sin_rfc || [];
    if (sinRfc.length) {
      partes.push(plegable(`${t("odo_l_sin_rfc")} (${sinRfc.length})`,
        renglones(sinRfc, (x) => [x.nombre || "—", noOdoo(x.odoo_id)]),
        null, {}, false));
    }
    /* Los de Centauro que no se encontraron en Odoo: si alguno es uno de
       los que llegan con otro nombre, se liga aqui antes de aplicar, y no
       se duplica. Solo en el ensayo: despues de aplicar ya se duplico. */
    const sinLigar = d.sin_ligar || [];
    if (d.ensayo && sinLigar.length && d.altas.length) {
      const listas = [];
      partes.push(plegable(`${t("odo_l_sin_ligar")} (${sinLigar.length})`,
        h("div", {},
          h("p", { clase: "gris chico", style: "margin:0 0 6px" }, t("odo_sin_ligar_pie")),
          ...sinLigar.map(c => ligarAMano(c, d.altas, listas))),
        null, {}, false));
    }
    if (d.sin_tarifario) {
      partes.push(h("p", { clase: "gris chico", style: "margin:10px 0 0" },
        reemplazar(t(d.tarifarios_de_odoo ? "odo_sin_tarifario_odoo"
                                          : "odo_sin_tarifario"),
                   { n: d.sin_tarifario })));
    }
    if ((d.pais_por_rfc || []).length) {
      partes.push(h("p", { clase: "gris chico", style: "margin:6px 0 0" },
        reemplazar(t("odo_pais_por_rfc"), { n: d.pais_por_rfc.length })));
    }
  } else if (tipo === "oficina") {
    const sinCorreo = d.sin_correo || [];
    if (sinCorreo.length) {
      partes.push(plegable(`${t("odo_l_sin_correo")} (${sinCorreo.length})`,
        renglones(sinCorreo, (x) => [x.nombre || "—",
          [x.puesto, x.area, noOdoo(x.odoo_id)].filter(Boolean).join(" · ")]),
        null, {}, false));
    }
    const sinSugerencia = d.sin_sugerencia || [];
    if (sinSugerencia.length) {
      partes.push(plegable(`${t("odo_l_sin_sugerencia")} (${sinSugerencia.length})`,
        h("div", {},
          h("p", { clase: "gris chico", style: "margin:0 0 6px" },
            t("odo_sin_sugerencia_pie")),
          renglones(sinSugerencia, (x) => [x.nombre || "—", x.puesto_odoo || "—"])),
        null, {}, false));
    }
    if ((d.sin_lugar || []).length) {
      partes.push(h("p", { clase: "gris chico", style: "margin:10px 0 0" },
        reemplazar(t("odo_sin_lugar"), { n: d.sin_lugar.length })));
    }
  } else if (tipo === "personal") {
    const celulares = d.celular_no_valido || [];
    if (celulares.length) {
      partes.push(plegable(`${t("odo_l_celular")} (${celulares.length})`,
        h("div", {},
          h("p", { clase: "gris chico", style: "margin:0 0 6px" }, t("odo_celular_pie")),
          renglones(celulares, (x) => [x.nombre || "—", noOdoo(x.odoo_id)])),
        null, {}, false));
    }
    if ((d.accesos_cerrados || []).length) {
      partes.push(h("p", { clase: "gris chico", style: "margin:10px 0 0" },
        reemplazar(t("odo_accesos_cerrados"), { n: d.accesos_cerrados.length })));
    }
    /* Las fotos solo se vuelven a pedir de quien Odoo toco desde la
       ultima lectura: si no hubo ninguna, no hay nada que decir. */
    const f = d.fotos || {};
    if (f.revisadas) {
      partes.push(h("p", { clase: "gris chico", style: "margin:10px 0 0" },
        d.ensayo
          ? reemplazar(t("odo_fotos"), { r: f.reales ?? 0, s: f.sin_foto_real ?? 0 })
          : reemplazar(t("odo_fotos_guardadas"),
                       { r: f.reales ?? 0, g: f.actualizadas ?? 0,
                         s: f.sin_foto_real ?? 0 })));
    }
  } else {
    const tl = d.taller || {};
    partes.push(h("p", { clase: "gris chico", style: "margin:10px 0 0" },
      reemplazar(t("odo_taller"), { nuevas: tl.nuevas ?? 0, cambios: tl.cambios ?? 0,
                                    borradas: tl.borradas ?? 0,
                                    sin: tl.sin_cambio ?? 0 })));
    if (tl.error) {
      partes.push(aviso(reemplazar(t("odo_taller_error"), { e: tl.error }), "alerta"));
    }
  }
  return h("div", {}, ...partes);
}

/* ------------------------------------------------------------ tarifarios */

/* Lo pendiente de los tarifarios (seccion 77), en el orden en que se
   atiende: primero lo que deja a un cliente sin su lista, al final lo que
   solo sobra. Cada tipo dice que va en el renglon y que al lado. */
const PENDIENTES_DE_TARIFAS = [
  ["lista_sin_precios", "odo_tp_sin_precios",
   (x) => [x.cliente, reemplazar(t("odo_tp_sin_precios_pie"), { l: x.lista || "—" })]],
  ["lista_otra_moneda", "odo_tp_cliente_otra_moneda",
   (x) => [x.cliente, reemplazar(t("odo_tp_cliente_otra_moneda_pie"),
                                 { l: x.lista || "—", m: x.moneda })]],
  ["producto_sin_confirmar", "odo_tp_producto",
   (x) => [x.producto, t("odo_tp_producto_pie")]],
  ["conflicto", "odo_tp_conflicto",
   (x) => [x.productos.map(([n]) => n).join(" / "),
           [x.productos.map(([, p]) => p).join(" / "),
            reemplazar(t("odo_tp_en_listas"),
                       { n: x.listas.length, l: x.listas.join(", ") })].join(" · ")]],
  ["reglas_repetidas", "odo_tp_repetidas",
   (x) => [x.lista, `${x.producto}: ${x.precios.join(" · ")}`]],
  ["regla", "odo_tp_regla", (x) => [x.lista, `${x.producto}: ${x.problema}`]],
  ["otra_moneda", "odo_tp_otra_moneda", (x) => [x.lista, `${x.moneda} · ${x.pais || "—"}`]],
  ["moneda", "odo_tp_moneda", (x) => [x.lista, x.moneda]],
  ["general_varios_paises", "odo_tp_varios_paises",
   (x) => [x.lista, x.paises.join(", ")]],
  ["sin_pais", "odo_tp_sin_pais", (x) => [x.lista, ""]],
  ["sin_general", "odo_tp_sin_general", () => [t("odo_tp_sin_general_pie"), ""]],
  ["modalidad", "odo_tp_modalidad", (x) => [x.lista, x.modalidad]],
  ["lista_sin_cliente", "odo_tp_lista_sin_cliente", (x) => [x.lista, preciosDe(x)]],
];

const EN_MONEDA = { MXN: "odo_ta_en_MXN", USD: "odo_ta_en_USD",
                    BRL: "odo_ta_en_BRL", VES: "odo_ta_en_VES" };

/* "12 precios, 5 propios", o que no pacta nada. */
function preciosDe(l) {
  if (!l.precios) return t("odo_ta_sin_precios");
  if (!l.propios) return reemplazar(t("odo_ta_sin_propios"), { n: l.precios });
  return reemplazar(t("odo_ta_n_precios"), { n: l.precios, p: l.propios });
}

function informeTarifas(d) {
  const generales = d.generales || [];
  const porCliente = d.por_cliente || [];
  const suyas = d.clientes - d.clientes_con_general;
  const pactados = generales.concat(porCliente, d.sin_cliente || [])
    .reduce((n, l) => n + (l.propios || 0), 0);
  const partes = [
    h("p", { clase: "gris chico", style: "margin:14px 0 0" },
      reemplazar(t(d.ensayo ? "odo_ensayo_de" : "odo_aplicado_de"),
                 { hora: hora(new Date().toISOString()) }),
      " · ", reemplazar(t("odo_leidas_listas"), { n: d.leidas })),
    h("div", { clase: "camino", style: "background:#fff;margin:8px 0 12px" },
      celda(t("odo_ta_generales"), generales.length,
            generales.length
              ? generales.map(g => `${g.pais || "—"}, ${t(EN_MONEDA[g.moneda] || "odo_ta_en_MXN")}`)
                  .join(" · ")
              : t("odo_ta_sin_general"),
            generales.length ? "" : "var(--alerta)"),
      celda(t("odo_ta_por_cliente"), porCliente.length,
            reemplazar(t("odo_ta_por_cliente_pie"), { n: suyas })),
      celda(t("odo_ta_precios"), d.precios,
            reemplazar(t("odo_ta_precios_pie"), { p: pactados })),
      celda(t("odo_ta_clientes"), d.clientes,
            reemplazar(t("odo_ta_clientes_pie"), { n: d.clientes_con_general })),
      celda(t("odo_pendientes"), d.pendientes.length, t("odo_ta_pendientes_pie"),
            d.pendientes.length ? "var(--alerta)" : "")),
  ];

  /* Lo pendiente no se pliega, igual que en las otras lecturas: es la
     lista de lo que hay que acomodar en Odoo o en la tabla de productos. */
  if (d.pendientes.length) {
    const grupos = PENDIENTES_DE_TARIFAS
      .map(([tipo, clave, renglon]) => [clave, renglon,
                                        d.pendientes.filter(p => p.tipo === tipo)])
      .filter(([, , lista]) => lista.length);
    partes.push(h("div", { style: "margin:4px 0 10px" },
      conAyuda("h4", `${t("odo_l_ta_pendientes")} (${d.pendientes.length})`,
               "ay_odo_ta_pendientes"),
      ...grupos.map(([clave, renglon, lista]) => h("div", { style: "margin:0 0 10px" },
        h("div", { style: "font-weight:600;font-size:13px;margin:0 0 4px" },
          `${t(clave)} (${lista.length})`),
        renglones(lista, renglon)))));
  }
  if ((d.cambian || []).length) {
    partes.push(plegable(`${t("odo_l_ta_cambian")} (${d.cambian.length})`,
      renglones(d.cambian, (x) => [x.cliente,
        x.antes ? reemplazar(t("odo_ta_de_a"), { a: x.antes, l: x.lista })
                : reemplazar(t("odo_ta_nuevo"), { l: x.lista })]),
      null, {}, false));
  }
  if (generales.length) {
    partes.push(plegable(`${t("odo_ta_generales")} (${generales.length})`,
      renglones(generales, (x) => [`${x.nombre} · ${x.pais || "—"}`,
        [x.moneda, preciosDe(x),
         reemplazar(t("odo_ta_n_clientes"), { n: x.clientes.length })].join(" · ")]),
      null, {}, true));
  }
  if (porCliente.length) {
    partes.push(plegable(`${t("odo_ta_por_cliente")} (${porCliente.length})`,
      renglones(porCliente, (x) => [x.nombre, [
        x.moneda, preciosDe(x),
        x.clientes.join(", "),
        x.implantados.length
          ? reemplazar(t("odo_ta_implantados_de"), { c: x.implantados.join(", ") }) : "",
        x.resto_de ? reemplazar(t("odo_ta_lo_demas"), { l: x.resto_de }) : "",
      ].filter(Boolean).join(" · ")]),
      null, {}, false));
  }
  const conImplantados = porCliente.concat(generales)
    .reduce((n, l) => n + (l.implantados || []).length, 0);
  partes.push(h("p", { clase: "gris chico", style: "margin:10px 0 0" },
    d.campo_implantados
      ? reemplazar(t("odo_ta_implantados"), { n: conImplantados })
      : t("odo_ta_sin_campo")));
  partes.push(h("p", { clase: "gris chico", style: "margin:6px 0 0" }, t("odo_ta_pie")));
  return h("div", {}, ...partes);
}

/* Un cliente de Centauro que es uno de los que llegan de Odoo con otro
   nombre: se le pone el No. Odoo de ese, y la lectura lo liga en vez de
   darlo de alta dos veces. Mientras no se aplique se puede deshacer --un
   error al escoger en la lista no se queda pegado--, y el de Odoo que ya
   se escogio no se le ofrece a otro. `listas`: las de todo el bloque. */
function ligarAMano(c, altas, listas) {
  const sel = h("select", { style: "flex:0 1 380px;width:auto" },
    h("option", { value: "" }, t("odo_es_de_odoo")),
    ...altas.map(a => h("option", { value: String(a.odoo_id) },
      [a.nombre, a.rfc].filter(Boolean).join(" · "))));
  listas.push(sel);
  const apartar = (valor, apartado) => {
    for (const otra of listas) {
      const opcion = [...otra.options].find(o => o.value === valor);
      if (otra !== sel && opcion) opcion.disabled = apartado;
    }
  };
  const guardar = (odooId) => api.patch(`/catalogos/clientes/${c.cliente_id}`, {
    nombre: c.nombre, pais_id: c.pais_id, odoo_id: odooId });

  const nombre = h("span", { style: "flex:1 1 220px" }, c.nombre || "—");
  const boton = h("button", { type: "button", clase: "chico claro" }, t("odo_ligar"));
  const fila = h("div", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap;"
                                 + "padding:5px 0;border-bottom:1px solid #f0f2f4" });
  const escoger = () => {
    sel.value = "";
    boton.disabled = false;
    fila.replaceChildren(nombre, sel, boton);
  };
  const ligado = (valor, deOdoo) => {
    const deshacer = h("button", { type: "button", clase: "chico claro" }, t("odo_deshacer"));
    deshacer.addEventListener("click", async () => {
      deshacer.disabled = true;
      try {
        await guardar(null);
        apartar(valor, false);
        mensaje(reemplazar(t("odo_desligado"), { c: c.nombre }));
        escoger();
      } catch (err) {
        mensaje(err.message, "grave");
        deshacer.disabled = false;
      }
    });
    fila.replaceChildren(
      h("span", { clase: "gris chico", style: "flex:1 1 260px" },
        reemplazar(t("odo_ligado_a"), { c: c.nombre, o: deOdoo })),
      deshacer);
  };
  boton.addEventListener("click", async () => {
    const valor = sel.value;
    if (!valor) return;
    boton.disabled = true;
    try {
      await guardar(Number(valor));
      apartar(valor, true);
      mensaje(t("odo_ligado"));
      ligado(valor, sel.options[sel.selectedIndex].textContent);
    } catch (err) {
      mensaje(err.message, "grave");
      boton.disabled = false;
    }
  });
  escoger();
  return fila;
}

function noOdoo(n) {
  return n ? reemplazar(t("odo_no_odoo"), { n }) : "";
}

function detalleAlta(tipo, x) {
  if (tipo === "personal") {
    return [x.plaza, x.correo].filter(Boolean).join(" · ");
  }
  if (tipo === "oficina") {
    return [x.puesto_odoo, x.area_odoo, x.correo].filter(Boolean).join(" · ");
  }
  if (tipo === "clientes") {
    return [x.rfc || t("odo_sin_rfc"), x.pais].filter(Boolean).join(" · ");
  }
  return [x.categoria, x.plaza].filter(Boolean).join(" · ");
}

function detalleBaja(x) {
  const partes = [motivo(x.motivo)];
  if (x.acceso) partes.push(motivo(x.acceso));
  if (x.dias_por_delante) {
    partes.push(reemplazar(t("odo_baja_dias"), { n: x.dias_por_delante }));
  }
  return partes.join(" · ");
}

/* Lo pendiente se agrupa por lo que falta, no por persona: RH corrige
   por tanda --todos los que no tienen plaza, todos los del correo--, y
   asi sale la lista de lo que tiene que hacer. */
function listaDePendientes(pendientes, cfg) {
  const grupos = new Map();
  for (const p of pendientes) {
    for (const f of p.falta || []) {
      const texto = falta(f);
      if (!grupos.has(texto)) grupos.set(texto, []);
      grupos.get(texto).push(p);
    }
  }
  const orden = [...grupos.entries()].sort((a, b) => b[1].length - a[1].length);
  return h("div", {}, ...orden.map(([texto, quienes]) => h("div", { style: "margin:0 0 10px" },
    h("div", { style: "font-weight:600;font-size:13px;margin:0 0 4px" },
      `${texto} (${quienes.length})`),
    renglones(quienes, (x) => [cfg.quien(x), noOdoo(x.odoo_id)]))));
}

/* Un renglon por persona o unidad: lo que se busca en Odoo --el nombre
   o la placa-- y al lado lo demas, en gris. Apretado a proposito: la
   lista de pendientes es la que RH va a recorrer entera. */
function renglones(lista, partes) {
  return h("div", { style: "margin:2px 0 10px" }, ...lista.map((x) => {
    const [principal, detalle] = partes(x);
    return h("div", { style: "display:flex;gap:14px;align-items:baseline;"
                              + "padding:5px 0;border-bottom:1px solid #f0f2f4" },
      h("span", { style: "flex:0 0 280px" }, principal),
      h("span", { clase: "gris chico" }, detalle || ""));
  }));
}

/* ------------------------------------------------------------ tarifario */

/* Los clientes llegan de Odoo sin tarifario (seccion 75), y hasta que se
   les pone no se les puede cotizar. Se pone aqui mismo: uno por uno, o a
   todos los de un pais de una vez --muchos comparten el mismo--. Si no
   falta ninguno, esto no se ve.

   Desde que los tarifarios se leen de Odoo (seccion 77) el de un cliente
   de Odoo lo pone su lista de alla: aqui solo quedan los que no estan en
   Odoo --los de Brasil, mientras no lleguen--. */
async function sinTarifario(caja, estado) {
  let clientes, tarifarios, paises;
  try {
    [clientes, tarifarios, paises] = await Promise.all([
      api.get("/catalogos/clientes"), api.get("/catalogos/tarifarios"),
      api.get("/catalogos/paises")]);
  } catch {
    return caja.replaceChildren();
  }
  const nombrePais = (id) => (paises.find(p => p.id === id) || {}).nombre || "—";
  const deOdoo = !!((estado || {}).tarifarios || {}).primera_hecha;
  const faltan = clientes.filter(c => c.activo && !c.tarifario_id
                                      && !(deOdoo && c.odoo_id));
  if (!faltan.length) return caja.replaceChildren();

  const deSuPais = (paisId) => tarifarios.filter(x => x.activo && x.pais_id === paisId);
  const selector = (paisId) => h("select", {},
    h("option", { value: "" }, t("odo_elige_tarifario")),
    ...deSuPais(paisId).map(x => h("option", { value: String(x.id) }, x.nombre)));
  const poner = (c, tarifarioId) => api.patch(`/catalogos/clientes/${c.id}`, {
    nombre: c.nombre, pais_id: c.pais_id, tarifario_id: Number(tarifarioId) });

  /* A todos los de un pais de una vez, confirmando en la misma tarjeta:
     es el precio que se le va a cobrar a cada uno. */
  const todos = [...new Set(faltan.map(c => c.pais_id))].map(paisId => {
    const suyos = faltan.filter(c => c.pais_id === paisId);
    const valores = { p: nombrePais(paisId), n: suyos.length };
    /* Un pais sin ningun tarifario todavia --Brasil, hoy--: no hay que
       escoger. Se dice, y se da de alta el tarifario primero. */
    if (!deSuPais(paisId).length) {
      return h("p", { clase: "gris chico", style: "margin:0 0 12px" },
        reemplazar(t("odo_sin_tarifario_de_pais"), valores));
    }
    const sel = selector(paisId);
    const confirmar = h("div");
    const boton = h("button", { type: "button", clase: "chico" },
      suyos.length === 1 ? t("odo_poner")
                         : reemplazar(t("odo_poner_a_todos"), { n: suyos.length }));
    boton.addEventListener("click", () => {
      if (!sel.value) return mensaje(t("odo_elige_tarifario"), "alerta");
      const nombre = sel.options[sel.selectedIndex].textContent;
      const si = h("button", { type: "button", clase: "chico" }, t("odo_si_poner"));
      const no = h("button", { type: "button", clase: "chico claro" }, t("cancelar"));
      no.addEventListener("click", () => confirmar.replaceChildren());
      si.addEventListener("click", async () => {
        si.disabled = true;
        no.disabled = true;
        try {
          for (const c of suyos) await poner(c, sel.value);
          mensaje(t("acc_hecho"));
          await sinTarifario(caja, estado);
        } catch (err) {
          mensaje(err.message, "grave");
          await sinTarifario(caja, estado);
        }
      });
      confirmar.replaceChildren(h("div", { clase: "aviso alerta", style: "margin:8px 0 0" },
        h("p", { style: "margin:0 0 8px" },
          reemplazar(t("odo_confirmar_tarifario"), { t: nombre, n: suyos.length })),
        h("div", { clase: "acciones" }, si, no)));
    });
    return h("div", { style: "margin:0 0 12px" },
      h("div", { clase: "chico", style: "font-weight:600;margin:0 0 4px" },
        reemplazar(t("odo_tarifario_de_pais"), valores)),
      h("div", { clase: "acciones" }, sel, boton), confirmar);
  });

  const uno = faltan.map(c => {
    const sel = selector(c.pais_id);
    const boton = h("button", { type: "button", clase: "chico claro" }, t("odo_poner"));
    boton.addEventListener("click", async () => {
      if (!sel.value) return;
      boton.disabled = true;
      try {
        await poner(c, sel.value);
        mensaje(t("acc_hecho"));
        await sinTarifario(caja, estado);
      } catch (err) {
        mensaje(err.message, "grave");
        boton.disabled = false;
      }
    });
    return h("div", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap;"
                              + "padding:5px 0;border-bottom:1px solid #f0f2f4" },
      h("span", { style: "flex:1 1 260px" }, c.nombre,
        h("span", { clase: "gris chico" }, ` · ${c.rfc || t("odo_sin_rfc")}`)),
      sel, boton);
  });

  const lista = plegable(t("odo_uno_por_uno"), h("div", {}, ...uno), null, {}, false);
  const tarjetaDeTarifas = h("div", { clase: "tarjeta" },
    h("h3", {}, reemplazar(t("odo_sin_tarifario_titulo"), { n: faltan.length })),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t(deOdoo ? "odo_sin_tarifario_pie_fuera" : "odo_sin_tarifario_pie")),
    ...todos, lista);
  caja.replaceChildren(tarjetaDeTarifas);
}

/* ------------------------------------------------------------ historial */

function pintarHistorial(caja, estado) {
  const filas = estado.lecturas || [];
  const titulo = conAyuda("h2", t("odo_historial"), "ay_odo_historial");
  if (!filas.length) {
    return caja.replaceChildren(titulo,
      h("p", { clase: "gris" }, t("odo_sin_lecturas")));
  }
  const col = (clave) => h("th", {}, t(clave));
  caja.replaceChildren(titulo, h("table", { clase: "lista" },
    h("thead", {}, h("tr", {},
      col("odo_h_cuando"), col("odo_h_que"), col("odo_h_como"), col("odo_h_quien"),
      col("odo_altas"), col("odo_cambios"), col("odo_bajas"), col("odo_pendientes"))),
    h("tbody", {}, ...filas.map((f) => h("tr", {},
      h("td", {}, cuando(f.hecha_en)),
      h("td", {}, t(f.tipo === "flota" ? "odo_t_flota"
                    : f.tipo === "oficina" ? "odo_t_oficina"
                    : f.tipo === "clientes" ? "odo_t_clientes"
                    : f.tipo === "tarifarios" ? "odo_t_tarifarios" : "odo_t_personal")),
      h("td", { clase: "gris" }, t(f.automatica ? "odo_sola_h" : "odo_a_mano")),
      h("td", {}, f.hecha_por || "—"),
      h("td", { clase: "num" }, String(f.altas)),
      h("td", { clase: "num" }, String(f.cambios)),
      h("td", { clase: "num" }, String(f.bajas)),
      h("td", { clase: "num" }, String(f.pendientes)))))));
}

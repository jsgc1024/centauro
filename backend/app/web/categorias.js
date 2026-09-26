/* Los puestos: qué puede tocar cada quien.

   El rol dice qué es alguien en el organigrama. El puesto dice qué puede
   tocar en el sistema, que no siempre es lo mismo: hay consultores que
   no deciden cuánto dinero se deposita, y gente de central que sí.

   La regla que manda aquí, y lo que esta pantalla tiene que dejar ver
   sin que nadie la explique:

       el puesto quita, el permiso suelto sólo da.

   Quien trae puesto puede exactamente lo que dice su lista —su rol deja
   de mandar— y encima puede llevar permisos sueltos. Al revés no hay:
   un permiso que quitara dejaría su renglón diciendo "Consultor" cuando
   no lo es, y para saber qué puede de verdad habría que abrir su ficha y
   acordarse de que existe una excepción escondida. */
import { api } from "./api.js";
import { aviso, campo, conAyuda, entrada, h, lista, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { MENU, PARA_PUESTOS, leFaltaPara, menuDe } from "./menu.js";

export const ROLES = ["consultor", "central", "finanzas", "director_operaciones",
                      "director_general", "recursos_humanos", "admin",
                      "personal_seguridad"];

/* El nombre del puesto en el idioma del que lee. Mapa explícito y no la
   cadena cruda: el día que un rol se llame de otra forma, aquí se ve el
   hueco en vez de salir en inglés de base de datos. */
export function nombreDelRol(codigo) {
  const clave = {
    personal_seguridad: "rol_personal_seguridad", central: "rol_central",
    consultor: "rol_consultor", finanzas: "rol_finanzas", admin: "rol_admin",
    director_operaciones: "rol_director_operaciones",
    director_general: "rol_director_general",
    recursos_humanos: "rol_recursos_humanos",
  }[codigo];
  return clave ? t(clave) : codigo;
}

/* Las 29 casillas agrupadas por familia. Quien arma "Consultor junior"
   apaga un bloque entero —el dinero—, no va casilla por casilla; una
   lista plana de 29 renglones obliga a leerlos todos para encontrar las
   cuatro que importan.

   La última familia no tiene prefijos: ahí cae lo que no reconozco. Sin
   ella, una actividad nueva desaparecería de la pantalla en silencio y
   nadie podría dársela a nadie. */
const FAMILIAS = [
  { clave: "cat_fam_operacion",
    prefijos: ["servicios", "solicitantes", "ciudades", "mapas"] },
  { clave: "cat_fam_viaticos", prefijos: ["viaticos"] },
  { clave: "cat_fam_cierre", prefijos: ["cierre"] },
  { clave: "cat_fam_nomina", prefijos: ["nomina"] },
  { clave: "cat_fam_bonos", prefijos: ["bonos", "comisiones"] },
  { clave: "cat_fam_otras", prefijos: [] },
];

function porFamilia(catalogo) {
  const conocidos = new Set(FAMILIAS.flatMap(f => f.prefijos));
  return FAMILIAS.map(f => ({
    titulo: t(f.clave),
    filas: catalogo.filter(a => {
      const prefijo = a.actividad.split(".")[0];
      return f.prefijos.length ? f.prefijos.includes(prefijo)
                               : !conocidos.has(prefijo);
    }),
  })).filter(g => g.filas.length);
}

/* El catálogo se pide una vez por carga de pantalla: son 29 renglones
   que sólo cambian cuando cambia el código. */
let catalogo = null;

async function traerCatalogo() {
  if (!catalogo) catalogo = await api.get("/auth/actividades");
  return catalogo;
}

/* ================================================== casillas reutilizables

   La misma tabla sirve para armar un puesto y para leer el de alguien.
   Devuelve el nodo, y encima la forma de preguntarle qué quedó marcado. */
function tablaDeCasillas(catalogo, marcadas, alCambiar) {
  const casillas = new Map();
  const caja = h("div");

  for (const grupo of porFamilia(catalogo)) {
    const cuerpo = h("div", { clase: "casillas" });
    for (const a of grupo.filas) {
      const c = h("input", { type: "checkbox" });
      c.checked = marcadas.has(a.actividad);
      if (alCambiar) c.addEventListener("change", alCambiar);
      casillas.set(a.actividad, c);
      cuerpo.append(h("label", { clase: "casilla" }, c,
        h("span", {},
          h("span", { clase: "chico" }, a.descripcion),
          h("span", { clase: "gris chico mono" }, ` ${a.actividad}`))));
    }
    caja.append(h("div", { clase: "familia" },
      h("div", { clase: "familia-titulo" },
        h("b", {}, grupo.titulo),
        h("span", { clase: "acciones-familia" },
          h("button", { clase: "enlace chico", type: "button",
            onclick: () => marcarFamilia(grupo, true) }, t("cat_marcar_todo")),
          h("button", { clase: "enlace chico", type: "button",
            onclick: () => marcarFamilia(grupo, false) }, t("cat_quitar_todo")))),
      cuerpo));
  }

  function marcarFamilia(grupo, valor) {
    for (const a of grupo.filas) casillas.get(a.actividad).checked = valor;
    if (alCambiar) alCambiar();
  }

  caja.marcadas = () => [...casillas.entries()]
    .filter(([, c]) => c.checked).map(([nombre]) => nombre);
  caja.poner = (nombres) => {
    const puestas = new Set(nombres);
    for (const [nombre, c] of casillas) c.checked = puestas.has(nombre);
    if (alCambiar) alCambiar();
  };
  return caja;
}

/* ============================================================ los puestos

   Desde la sección 73 un puesto es un puesto de verdad: con qué rol
   entra quien lo trae, en qué área vive, qué pantallas le salen en el
   menú, a qué puestos de Odoo se parece y qué puede hacer. La lista se
   lee como la propuesta que aprobó Salvador: puesto y área, a quién se
   le sugiere en Odoo, qué hace y cuánta gente lo trae. */

/* Con qué rol puede entrar quien trae un puesto. Ni personal de
   seguridad —entra por la app—, ni dirección general ni administración:
   esas dos entran con su rol, sin puesto (sección 73). */
const ROLES_DE_PUESTO = ["consultor", "central", "finanzas",
                         "director_operaciones", "recursos_humanos"];

export async function pestanaPuestos(zona) {
  const base = h("div");
  const nuevo = h("div");
  const cuerpo = h("div");
  zona.replaceChildren(
    h("p", { clase: "gris chico", style: "margin:0 0 12px" }, t("cat_pie")),
    base, nuevo, cuerpo);

  async function recargar() {
    const [cat, puestos, deBase] = await Promise.all([
      traerCatalogo(), api.get("/auth/categorias"),
      api.get("/auth/categorias/base")]);
    tarjetaBase(base, deBase.faltan, recargar);
    formularioNuevo(nuevo, cat, puestos, recargar);
    cuerpo.replaceChildren(
      tablaDePuestos(puestos, deBase.por_rol || [], cat, recargar));
  }

  try {
    await recargar();
  } catch (err) {
    cuerpo.replaceChildren(aviso(err.message, "grave"));
  }
}

/* Los puestos de la propuesta que todavía no existen, con el botón que
   los crea. Los que ya están no se tocan: si alguien los ajustó, sus
   ajustes mandan. */
function tarjetaBase(zona, faltan, recargar) {
  if (!faltan.length) return zona.replaceChildren();
  const crear = h("button", { clase: "chico", type: "button" },
                  t("cat_base_crear").replace("{n}", faltan.length));
  crear.addEventListener("click", async () => {
    crear.disabled = true;
    try {
      const r = await api.post("/auth/categorias/base", {});
      mensaje(t("cat_base_creados").replace("{n}", r.creados.length));
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      crear.disabled = false;
    }
  });
  zona.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin:0 0 12px" },
    h("b", {}, t("cat_base_titulo")),
    h("p", { clase: "chico", style: "margin:4px 0 6px" }, faltan.join(" · ")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" }, t("cat_base_pie")),
    crear));
}

function tablaDePuestos(puestos, porRol, cat, recargar) {
  if (!puestos.length && !porRol.length) {
    return h("div", { clase: "gris chico" }, t("cat_ninguno"));
  }
  /* En el orden del organigrama, que es el de la propuesta; los que no
     tienen lugar, al final por nombre. Los dos que entran con su rol van
     en su lugar, para que la lista esté completa. */
  const lugar = (p) => (p.orden === null || p.orden === undefined ? 1e6 : p.orden);
  const filas = [
    ...puestos.map(p => ({ p, deRol: false })),
    ...porRol.map(p => ({ p, deRol: true })),
  ].sort((a, b) => lugar(a.p) - lugar(b.p) || a.p.nombre.localeCompare(b.p.nombre));

  const cuerpo = h("tbody");
  for (const f of filas) {
    if (f.deRol) cuerpo.append(renglonPorRol(f.p));
    else cuerpo.append(...renglonPuesto(f.p, cat, puestos, recargar));
  }
  return h("div", { style: "overflow-x:auto" },
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", { style: "width:24%" }, t("cat_col_puesto")),
        h("th", { style: "width:24%" }, t("cat_col_odoo")),
        h("th", {}, t("cat_col_hace")),
        h("th", { style: "width:12%" }, t("cat_personas")),
        h("th", { style: "width:5%" }))),
      cuerpo));
}

function quienesLoTraen(n) {
  return n ? t("cat_gente").replace("{n}", n) : t("cat_gente_cero");
}

function quienesEntranAsi(n) {
  return n ? t("cat_gente_por_rol").replace("{n}", n) : t("cat_gente_por_rol_cero");
}

function renglonPuesto(p, cat, puestos, recargar) {
  const zona = h("div");
  const abajo = h("tr", { hidden: true }, h("td", { colspan: "5" }, zona));
  /* Debajo de lo que hace, lo que le sale en el menú: es lo primero que
     alguien pregunta de un puesto. */
  const pantallas = (p.pantallas || [])
    .map(c => MENU.find(x => x.clave === c)).filter(Boolean)
    .map(x => t(x.texto));
  const fila = h("tr", { clase: p.activa ? "" : "cerrado" },
    h("td", {},
      h("b", {}, p.nombre),
      p.activa ? "" : h("span", { clase: "gris chico" }, ` · ${t("cat_apagado")}`),
      h("div", { clase: "chico gris" }, [
        p.area,
        p.rol ? t("cat_entra_como").replace("{rol}", nombreDelRol(p.rol))
              : t("cat_rol_de_cada_quien"),
      ].filter(Boolean).join(" · "))),
    h("td", { clase: "chico" }, p.puestos_odoo || "—"),
    h("td", { clase: "chico" }, p.descripcion || "—",
      h("div", { clase: "gris chico" },
        pantallas.length ? pantallas.join(" · ") : t("cat_menu_de_su_rol"))),
    h("td", { clase: "chico" }, quienesLoTraen(p.personas)),
    h("td", {}, h("button", { clase: "claro chico", type: "button",
      onclick: () => {
        if (!abajo.hidden) { abajo.hidden = true; zona.replaceChildren(); return; }
        abajo.hidden = false;
        editar(zona, p, cat, puestos, recargar);
      } }, "···")));
  return [fila, abajo];
}

/* Dirección general y administración: no son puestos, entran con su rol.
   Se enseñan sin botón, con cuánta gente entra así. */
function renglonPorRol(p) {
  return h("tr", {},
    h("td", {},
      h("b", {}, p.nombre),
      h("div", { clase: "chico gris" }, [
        p.area, t("cat_entra_con_su_rol").replace("{rol}", nombreDelRol(p.rol)),
      ].filter(Boolean).join(" · "))),
    h("td", { clase: "chico" }, p.puestos_odoo || "—"),
    h("td", { clase: "chico" }, p.descripcion || "—"),
    h("td", { clase: "chico" }, quienesEntranAsi(p.personas)),
    h("td", {}, h("span", { clase: "etiqueta" }, t("cat_por_rol"))));
}

/* Las pantallas del menú como casillas, agrupadas como en la barra. Odoo
   no sale: su puerta pide administración, y ningún puesto entra así. */
function casillasDePantallas(marcadas, alCambiar) {
  const casillas = new Map();
  const caja = h("div");
  const grupos = new Map();
  for (const x of PARA_PUESTOS) {
    if (!grupos.has(x.grupo)) grupos.set(x.grupo, []);
    grupos.get(x.grupo).push(x);
  }
  for (const [grupo, pantallas] of grupos) {
    const cuerpo = h("div", { clase: "casillas" });
    for (const x of pantallas) {
      const c = h("input", { type: "checkbox" });
      c.checked = marcadas.has(x.clave);
      if (alCambiar) c.addEventListener("change", alCambiar);
      casillas.set(x.clave, c);
      cuerpo.append(h("label", { clase: "casilla" }, c,
        h("span", { clase: "chico" }, t(x.texto))));
    }
    caja.append(h("div", { clase: "familia" },
      h("div", { clase: "familia-titulo" }, h("b", {}, t(grupo))),
      cuerpo));
  }
  caja.marcadas = () => PARA_PUESTOS
    .filter(x => casillas.get(x.clave).checked).map(x => x.clave);
  caja.poner = (claves) => {
    const puestas = new Set(claves);
    for (const [clave, c] of casillas) c.checked = puestas.has(clave);
  };
  return caja;
}

/* Una pantalla marcada sin la actividad que la llena abre vacía. Se dice
   antes de guardar, con el nombre de lo que le falta. */
function avisosDelPuesto(cat, pantallas, actividades) {
  const trae = new Set(actividades);
  const avisos = [];
  for (const x of PARA_PUESTOS) {
    if (!pantallas.includes(x.clave)) continue;
    const falta = leFaltaPara(x, trae);
    if (!falta) continue;
    const d = cat.find(a => a.actividad === falta);
    avisos.push(t("cat_pantalla_sin").replace("{p}", t(x.texto))
      .replace("{a}", d ? d.descripcion : falta));
  }
  return avisos;
}

/* Los datos de un puesto, iguales al crearlo y al cambiarlo. */
function camposDelPuesto(p, cat, alCambiar) {
  const nombre = entrada("nombre", { placeholder: t("cat_nombre"),
                                     value: p.nombre || null });
  const descripcion = entrada("descripcion", { placeholder: t("cat_descripcion"),
                                               value: p.descripcion || null });
  const area = entrada("area", { placeholder: t("cat_area_ej"), maxlength: "60",
                                 value: p.area || null });
  /* "Con el rol de cada quien" sólo para el puesto que todavía no dice
     su rol: una vez dicho, se cambia por otro, no se borra. */
  const rol = lista("rol", [
    ...(p.rol ? [] : [{ valor: "", texto: t("cat_rol_de_cada_quien") }]),
    ...ROLES_DE_PUESTO.map(r => ({ valor: r, texto: nombreDelRol(r) }))]);
  rol.value = p.rol || "";
  if (alCambiar) rol.addEventListener("change", alCambiar);
  const odoo = entrada("puestos_odoo", { placeholder: t("cat_odoo_ej"),
                                        value: p.puestos_odoo || null });
  const horas = entrada("horas", { type: "number", min: "1", max: "24",
                                   placeholder: t("cat_horas"),
                                   value: p.horas_sesion ? String(p.horas_sesion) : null });
  const pantallas = casillasDePantallas(new Set(p.pantallas || []), alCambiar);
  const actividades = tablaDeCasillas(cat, new Set(p.actividades || []), alCambiar);

  const nodo = h("div", {},
    h("div", { clase: "rejilla dos" },
      campo(t("cat_nombre"), nombre), campo(t("cat_descripcion"), descripcion)),
    h("div", { clase: "rejilla tres" },
      campo(t("cat_area"), area), campo(t("cat_rol_base"), rol),
      campo(t("cat_horas"), horas)),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" }, t("cat_rol_base_ayuda")),
    campo(t("cat_col_odoo"), odoo),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" }, t("cat_odoo_ayuda")),
    h("h4", { style: "margin:14px 0 2px" }, t("cat_pantallas")),
    h("p", { clase: "gris chico", style: "margin:0 0 6px" }, t("cat_pantallas_pie")),
    pantallas,
    h("h4", { style: "margin:14px 0 6px" }, t("cat_que_hace")),
    actividades);

  return {
    nodo, rol, area, pantallas, actividades,
    datos: () => ({
      nombre: nombre.value.trim(),
      descripcion: descripcion.value.trim() || null,
      area: area.value.trim() || null,
      rol: rol.value || null,
      puestos_odoo: odoo.value.trim() || null,
      horas_sesion: horas.value ? Number(horas.value) : null,
      pantallas: pantallas.marcadas(),
      actividades: actividades.marcadas(),
    }),
  };
}

function formularioNuevo(zona, cat, puestos, recargar) {
  const abrir = h("button", { clase: "chico claro", type: "button" },
                  t("cat_nuevo"));
  zona.replaceChildren(h("div", { style: "margin-bottom:10px" }, abrir));

  abrir.addEventListener("click", () => {
    const avisos = h("div");
    const f = camposDelPuesto({}, cat, () => revisar());
    function revisar() {
      avisos.replaceChildren(...avisosDelPuesto(
        cat, f.pantallas.marcadas(), f.actividades.marcadas())
        .map(x => aviso(x, "alerta")));
    }

    /* Nadie arma un puesto desde cero: lo que se piensa es "como
       consultor, pero sin depósitos", o "como el consultor de seguridad,
       pero junior". Se copian sus casillas y sus pantallas, y se apagan
       las que no. Lo que se guarda es la lista ya resuelta, no "consultor
       menos X": si fuera un vínculo, el día que cambiara lo de origen
       cambiaría en silencio lo que puede esta gente. */
    const partir = lista("partir", [
      { valor: "", texto: t("cat_en_blanco") },
      ...ROLES.filter(r => r !== "personal_seguridad")
        .map(r => ({ valor: `rol:${r}`, texto: nombreDelRol(r) })),
      ...puestos.map(p => ({ valor: `puesto:${p.categoria_id}`,
                             texto: t("cat_como_puesto").replace("{p}", p.nombre) })),
    ]);
    partir.addEventListener("change", () => {
      const [tipo, cual] = partir.value.split(":");
      if (tipo === "rol") {
        f.actividades.poner(cat.filter(a => a.roles.includes(cual))
          .map(a => a.actividad));
        f.pantallas.poner(menuDe({ rol: cual }).filter(x => x.necesita)
          .map(x => x.clave));
        if (ROLES_DE_PUESTO.includes(cual)) f.rol.value = cual;
      } else if (tipo === "puesto") {
        const p = puestos.find(x => String(x.categoria_id) === cual);
        f.actividades.poner(p.actividades);
        f.pantallas.poner(p.pantallas || []);
        f.rol.value = p.rol || "";
        f.area.value = p.area || "";
      } else {
        f.actividades.poner([]);
        f.pantallas.poner([]);
      }
      revisar();
    });

    const guardar = h("button", { clase: "chico", type: "button" },
                      t("cat_crear"));
    guardar.addEventListener("click", async () => {
      guardar.disabled = true;
      try {
        await api.post("/auth/categorias", f.datos());
        mensaje(t("acc_hecho"));
        await recargar();
      } catch (err) {
        mensaje(err.message, "grave");
        guardar.disabled = false;
      }
    });

    zona.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin-bottom:12px" },
      campo(t("cat_partir_de"), partir),
      h("p", { clase: "gris chico", style: "margin:0 0 12px" }, t("cat_partir_de_ayuda")),
      f.nodo, avisos,
      h("div", { clase: "acciones", style: "margin-top:10px" },
        guardar,
        h("button", { clase: "chico claro", type: "button",
          onclick: () => formularioNuevo(zona, cat, puestos, recargar) },
          t("acc_cancelar")))));
    revisar();
  });
}

function editar(zona, p, cat, puestos, recargar) {
  const advertencia = h("div");
  const f = camposDelPuesto(p, cat, () => revisar());

  /* Se cambia una vez y manda para todos los que lo traen puesto. Es lo
     que hace útil al puesto y lo que lo hace peligroso: hay que decir a
     cuánta gente le estás cambiando el acceso antes de guardar, no
     después. */
  function revisar() {
    const nada = f.actividades.marcadas().length === 0;
    const otroRol = p.personas && p.rol && f.rol.value !== p.rol;
    advertencia.replaceChildren(
      p.personas
        ? aviso(t("cat_aviso_guardar").replace("{n}", p.personas), "alerta")
        : "",
      otroRol
        ? aviso(t("cat_aviso_rol").replace("{n}", p.personas), "alerta")
        : "",
      nada ? aviso(t("cat_ninguna_casilla"), "alerta") : "",
      ...avisosDelPuesto(cat, f.pantallas.marcadas(), f.actividades.marcadas())
        .map(x => aviso(x, "alerta")));
  }
  revisar();

  const guardar = h("button", { clase: "chico", type: "button" },
                    t("cat_guardar"));
  guardar.addEventListener("click", async () => {
    guardar.disabled = true;
    try {
      await api.patch(`/auth/categorias/${p.categoria_id}`, f.datos());
      mensaje(t("acc_hecho"));
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      guardar.disabled = false;
    }
  });

  const apagar = h("button", { clase: "chico claro", type: "button" },
                   p.activa ? t("cat_apagar") : t("cat_encender"));
  apagar.addEventListener("click", async () => {
    apagar.disabled = true;
    try {
      await api.patch(`/auth/categorias/${p.categoria_id}`,
                      { activa: !p.activa });
      /* Apagarlo no le quita nada a quien ya lo trae: sólo deja de
         ofrecerse al asignar. Si no se dice, parece que el botón no
         hizo nada. */
      mensaje(p.activa ? t("cat_aviso_apagar") : t("acc_hecho"),
              p.activa ? "alerta" : "ok");
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      apagar.disabled = false;
    }
  });

  zona.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin:4px 0 8px" },
    f.nodo, advertencia,
    h("div", { clase: "acciones", style: "margin-top:10px" },
      guardar, apagar)));
}

/* ============================== qué puede una persona, y de dónde le viene

   La pantalla que contesta la pregunta que llega por teléfono: "¿por qué
   Beatriz no puede?". Sin la columna de dónde sale cada cosa, el único
   camino para entenderlo es leer el código, y quien reparte accesos no
   lee código. */

const DE_DONDE = {
  "rol": "cat_de_rol",
  "categoria": "cat_de_puesto",
  "permiso de mas": "cat_de_suelto",
};

/* `alCambiarPuesto`: lo que hay que repintar arriba cuando cambia su
   puesto. Desde la seccion 73 el puesto tambien le cambia el rol, y el
   renglon de la persona no puede seguir diciendo el de antes. */
export async function seccionDePermisos(zona, usuarioId, alCambiarPuesto = null) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, "…"));
  try {
    const [cat, puestos, ficha] = await Promise.all([
      traerCatalogo(),
      api.get("/auth/categorias"),
      api.get(`/auth/usuarios/${usuarioId}/permisos`),
    ]);
    pintar(zona, usuarioId, cat, puestos, ficha, alCambiarPuesto);
  } catch (err) {
    zona.replaceChildren(aviso(err.message, "grave"));
  }
}

function pintar(zona, usuarioId, cat, puestos, ficha, alCambiarPuesto) {
  const recargar = () => seccionDePermisos(zona, usuarioId, alCambiarPuesto);

  /* Los apagados no se ofrecen —para eso se apagaron— salvo que sea
     justo el que esta persona trae puesto: esconderlo de su propia lista
     lo haría ver como si no tuviera ninguno. */
  const suyo = puestos.find(p => p.nombre === ficha.categoria);
  const opciones = [{ valor: "", texto: t("cat_sin_puesto") },
    ...puestos.filter(p => p.activa || p === suyo)
      .map(p => ({ valor: String(p.categoria_id), texto: p.nombre }))];
  const elegir = lista("puesto", opciones);
  elegir.value = suyo ? String(suyo.categoria_id) : "";

  const poner = h("button", { clase: "chico claro", type: "button" },
                  t("cat_poner"));
  poner.addEventListener("click", async () => {
    poner.disabled = true;
    try {
      await api.post(`/auth/usuarios/${usuarioId}/categoria`,
                     { categoria_id: elegir.value ? Number(elegir.value) : null });
      mensaje(t("acc_hecho"));
      await (alCambiarPuesto ? alCambiarPuesto() : recargar());
    } catch (err) {
      mensaje(err.message, "grave");
      poner.disabled = false;
    }
  });

  const de = new Map(ficha.actividades.map(a => [a.actividad, a]));
  const tabla = h("div");
  for (const grupo of porFamilia(cat)) {
    tabla.append(h("div", { clase: "familia" },
      h("div", { clase: "familia-titulo" }, h("b", {}, grupo.titulo)),
      h("div", {}, ...grupo.filas.map(a =>
        renglonPermiso(usuarioId, a, de.get(a.actividad), recargar)))));
  }

  zona.replaceChildren(
    conAyuda("h4", t("cat_su_puesto"), "ay_cat_puesto",
             { style: "margin:10px 0 4px" }),
    h("div", { clase: "acciones" }, elegir, poner),
    ficha.categoria
      ? h("div", { clase: "gris chico", style: "margin-top:4px" },
          t("cat_manda_sobre_rol").replace("{rol}", nombreDelRol(ficha.rol)))
      : "",
    conAyuda("h4", t("cat_que_puede"), "ay_cat_permisos",
             { style: "margin:14px 0 4px" }),
    h("div", { clase: "gris chico", style: "margin-bottom:6px" },
      t("cat_solo_dan")),
    tabla);
}

function renglonPermiso(usuarioId, actividad, estado, recargar) {
  const puede = estado && estado.puede;
  const suelto = estado && estado.de_donde === "permiso de mas";

  async function mover(dar, boton) {
    boton.disabled = true;
    try {
      if (dar) {
        await api.post(`/auth/usuarios/${usuarioId}/permisos`,
                       { actividad: actividad.actividad });
        mensaje(t("acc_hecho"));
      } else {
        await api.borrar(
          `/auth/usuarios/${usuarioId}/permisos/${actividad.actividad}`);
        /* Quita la excepción, no el permiso: si su puesto o su rol ya lo
           traían, sigue pudiéndolo. Es lo correcto, pero si no se dice
           parece que el botón no hizo nada. */
        mensaje(t("cat_aviso_quitar"), "alerta");
      }
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      boton.disabled = false;
    }
  }

  const boton = suelto
    ? h("button", { clase: "enlace chico", type: "button" }, t("cat_quitar"))
    : (puede ? "" : h("button", { clase: "enlace chico", type: "button" },
                      t("cat_dar")));
  if (boton) boton.addEventListener("click", () => mover(!suelto, boton));

  return h("div", { clase: "renglon-permiso" },
    h("span", { clase: "chico" }, actividad.descripcion),
    h("span", { clase: `marca ${puede ? "si" : "no"}` },
      puede ? t(DE_DONDE[estado.de_donde]) : t("cat_no_puede")),
    boton || h("span", {}));
}

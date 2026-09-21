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
import { aviso, conAyuda, entrada, h, lista, mensaje } from "./util.js";
import { t } from "./idioma.js";

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

/* ============================================================ los puestos */

export async function pestanaPuestos(zona) {
  const cuerpo = h("div");
  const nuevo = h("div");
  zona.replaceChildren(
    h("p", { clase: "gris chico", style: "margin:0 0 12px" }, t("cat_pie")),
    nuevo, cuerpo);

  async function recargar() {
    const [cat, puestos] = await Promise.all(
      [traerCatalogo(), api.get("/auth/categorias")]);
    cuerpo.replaceChildren(puestos.length
      ? h("div", {}, ...puestos.map(p => renglonPuesto(p, cat, recargar)))
      : h("div", { clase: "gris chico" }, t("cat_ninguno")));
    formularioNuevo(nuevo, cat, recargar);
  }

  try {
    await recargar();
  } catch (err) {
    cuerpo.replaceChildren(aviso(err.message, "grave"));
  }
}

function formularioNuevo(zona, cat, recargar) {
  const abrir = h("button", { clase: "chico claro", type: "button" },
                  t("cat_nuevo"));
  zona.replaceChildren(h("div", { style: "margin-bottom:10px" }, abrir));

  abrir.addEventListener("click", () => {
    const nombre = entrada("nombre", { placeholder: t("cat_nombre") });
    const descripcion = entrada("descripcion",
                                { placeholder: t("cat_descripcion") });
    const horas = entrada("horas", { type: "number", min: "1", max: "24",
                                     placeholder: t("cat_horas") });

    /* Nadie arma un puesto desde cero: lo que se piensa es "como
       consultor, pero sin depósitos". Se copian sus casillas y se apagan
       las que no. Lo que se guarda es la lista ya resuelta, no "consultor
       menos X": si fuera un vínculo, el día que cambiara lo que trae
       consultor cambiaría en silencio lo que puede esta gente. */
    const partir = lista("partir", [
      { valor: "", texto: t("cat_en_blanco") },
      ...ROLES.map(r => ({ valor: r, texto: nombreDelRol(r) })),
    ]);
    const casillas = tablaDeCasillas(cat, new Set(), null);
    partir.addEventListener("change", () => {
      casillas.poner(partir.value
        ? cat.filter(a => a.roles.includes(partir.value)).map(a => a.actividad)
        : []);
    });

    const guardar = h("button", { clase: "chico", type: "button" },
                      t("cat_crear"));
    guardar.addEventListener("click", async () => {
      guardar.disabled = true;
      try {
        await api.post("/auth/categorias", {
          nombre: nombre.value.trim(),
          descripcion: descripcion.value.trim() || null,
          horas_sesion: horas.value ? Number(horas.value) : null,
          actividades: casillas.marcadas(),
        });
        mensaje(t("acc_hecho"));
        await recargar();
      } catch (err) {
        mensaje(err.message, "grave");
        guardar.disabled = false;
      }
    });

    zona.replaceChildren(h("div", { clase: "tarjeta lisa" },
      h("div", { clase: "rejilla dos" },
        h("div", {}, nombre), h("div", {}, descripcion)),
      h("div", { clase: "rejilla dos", style: "margin-top:10px" },
        h("div", {}, partir,
          h("div", { clase: "gris chico" }, t("cat_partir_de_ayuda"))),
        h("div", {}, horas,
          h("div", { clase: "gris chico" }, t("cat_horas_ayuda")))),
      casillas,
      h("div", { clase: "acciones", style: "margin-top:10px" },
        guardar,
        h("button", { clase: "chico claro", type: "button",
          onclick: () => formularioNuevo(zona, cat, recargar) },
          t("acc_cancelar")))));
  });
}

function renglonPuesto(p, cat, recargar) {
  const zona = h("div");
  const fila = h("div", { clase: "renglon-acceso" },
    h("div", { clase: "quien-acceso" },
      h("div", {}, h("b", {}, p.nombre),
        p.activa ? "" : h("span", { clase: "gris chico" },
                          ` · ${t("cat_apagado")}`)),
      p.descripcion
        ? h("div", { clase: "chico gris" }, p.descripcion) : ""),
    h("div", { clase: "chico" }, p.personas
      ? t("cat_gente").replace("{n}", p.personas) : t("cat_gente_cero")),
    h("div", { clase: "chico gris" },
      p.horas_sesion ? t("cat_horas_n").replace("{n}", p.horas_sesion) : "—"),
    h("button", { clase: "claro chico", type: "button",
      onclick: () => editar(zona, p, cat, recargar) }, "···"));

  const caja = h("div", { clase: p.activa ? "" : "cerrado" }, fila, zona);
  return caja;
}

function editar(zona, p, cat, recargar) {
  if (zona.childElementCount) return zona.replaceChildren();

  const advertencia = h("div");
  const casillas = tablaDeCasillas(cat, new Set(p.actividades), revisar);

  /* Se cambia una vez y manda para todos los que lo traen puesto. Es lo
     que hace útil al puesto y lo que lo hace peligroso: hay que decir a
     cuánta gente le estás cambiando el acceso antes de guardar, no
     después. */
  function revisar() {
    const nada = casillas.marcadas().length === 0;
    advertencia.replaceChildren(
      p.personas
        ? aviso(t("cat_aviso_guardar").replace("{n}", p.personas), "alerta")
        : "",
      nada ? aviso(t("cat_ninguna_casilla"), "alerta") : "");
  }
  revisar();

  const guardar = h("button", { clase: "chico", type: "button" },
                    t("cat_guardar"));
  guardar.addEventListener("click", async () => {
    guardar.disabled = true;
    try {
      await api.patch(`/auth/categorias/${p.categoria_id}`,
                      { actividades: casillas.marcadas() });
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

  zona.replaceChildren(h("div", { clase: "tarjeta lisa", style: "margin-top:8px" },
    casillas, advertencia,
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

export async function seccionDePermisos(zona, usuarioId) {
  zona.replaceChildren(h("div", { clase: "gris chico" }, "…"));
  try {
    const [cat, puestos, ficha] = await Promise.all([
      traerCatalogo(),
      api.get("/auth/categorias"),
      api.get(`/auth/usuarios/${usuarioId}/permisos`),
    ]);
    pintar(zona, usuarioId, cat, puestos, ficha);
  } catch (err) {
    zona.replaceChildren(aviso(err.message, "grave"));
  }
}

function pintar(zona, usuarioId, cat, puestos, ficha) {
  const recargar = () => seccionDePermisos(zona, usuarioId);

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
      await recargar();
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

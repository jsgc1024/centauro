"""Paso 3c: el boton de regreso y su formulario de una sola pregunta."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/servicio.js"
s = R.read_text()

# --- 1. el bloque de dinero se saca a su propia funcion --------------
VIEJO = '''  const dinero_ = h("div", { style: "margin-top:8px" },
    h("h4", { style: "margin:0 0 2px" }, t("srv_viaticos")));
  for (const x of v.a_comprobar || []) {
    dinero_.append(linea(
      t("srv_comprueba").replace("{m}", dinero(x.monto))
        .replace("{f}", fecha((x.limite || "").slice(0, 10))), true));
  }
  if ((v.cancelados || []).length) {
    dinero_.append(linea(
      t("srv_se_cancelan").replace("{n}", v.cancelados.length)));
  }
  /* Propuesta, no asignacion: el sistema saca la cuenta del tabulador
     para que el consultor no tenga que ir a buscarla, pero la solicitud
     la hace el, como con cualquier otra. */
  const propuesto = (v.propuestos || []).reduce((a, x) => a + x.monto, 0);
  if (propuesto) {
    dinero_.append(linea(
      t("srv_le_tocarian").replace("{p}", entra.nombre)
        .replace("{m}", dinero(propuesto))
        .replace("{n}", v.propuestos.length), true));
  }
  if (!(v.a_comprobar || []).length && !propuesto
      && !(v.cancelados || []).length) {
    dinero_.append(linea(t("srv_nada_mover")));
  }

'''
NUEVO = '''  const dinero_ = bloqueDinero(v, entra.nombre);

'''
assert s.count(VIEJO) == 1, "no encontre el bloque de dinero"
s = s.replace(VIEJO, NUEVO)

# `linea` ya no se usa en recuadroPrevia: se va con el bloque.
VIEJO = '''  const v = r.viaticos || {};
  const linea = (texto, tono) =>
    h("div", { clase: "chico" + (tono ? "" : " gris") },
      tono ? h("b", {}, texto) : texto);
'''
NUEVO = '''  const v = r.viaticos || {};
'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# --- 2. la funcion, y con ella el regreso ---------------------------
ANCLA = "function recuadroPrevia(r, cuerpo, entra, puerta) {"
FUNCIONES = '''/* Lo delicado de un cambio no es el nombre de quien va: es que quien
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
  const minimo = diaSiguiente(r.desde);
  const hoy = new Date().toISOString().slice(0, 10);
  let valor = hoy < minimo ? minimo : hoy;
  if (r.hasta && valor > r.hasta) valor = r.hasta;

  const dia = h("input", { type: "date", value: valor, min: minimo });
  if (r.hasta) dia.max = r.hasta;

  const previa = h("div", { style: "margin-top:12px" });
  const ver = h("button", { clase: "chico", type: "button",
    onclick: (e) => verPreviaRegreso(e, previa, r, dia.value) },
    t("srv_r_ver"));

  zona.replaceChildren(h("div", { clase: "tarjeta lisa" },
    h("h4", { style: "margin:0 0 2px" },
      t("srv_r_cuando").replace("{p}", r.sale || "?")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      t("srv_r_form_pie")),
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
      t("srv_r_devueltos").replace("{n}", devueltos)
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
    bloqueDinero(p.viaticos || {}, p.regresa || "?"),
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

function recuadroPrevia(r, cuerpo, entra, puerta) {'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, FUNCIONES)

# --- 3. la tarjeta: el nombre nuevo y el boton ----------------------
VIEJO = '''  for (const d of r.jornadas_partidas || []) {'''
NUEVO = '''  for (const d of r.partidos || []) {'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''  tarjeta.append(firma);

  return tarjeta;
}'''
NUEVO = '''  tarjeta.append(firma);

  /* El boton va en la tarjeta del movimiento y no en la tabla de dias,
     porque el regreso cierra ESE movimiento: no es un cambio nuevo. Solo
     aparece si sigue corriendo. */
  if (r.en_curso && r.tipo === "personal") {
    const zona = h("div", { style: "margin-top:10px" });
    tarjeta.append(
      h("div", { clase: "acciones", style: "margin-top:8px" },
        h("button", { clase: "claro chico", type: "button",
          onclick: () => abrirRegreso(zona, r) },
          t("srv_r_regresar").replace("{p}", r.sale || "?"))),
      zona);
  }

  return tarjeta;
}'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("servicio.js: el boton de regreso y su formulario")

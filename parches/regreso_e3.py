"""Paso 2b: la tarjeta del cambio dice en que estado esta y que dias
partio."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/servicio.js"
s = R.read_text()

VIEJO = '''function bloqueCambios(filas) {
  const caja = h("div", { clase: "tarjeta" });
  if (!filas || !filas.length) return h("div");

  caja.append(h("h3", { style: "margin:0 0 2px" }, t("srv_cambios")),
    h("p", { clase: "gris chico", style: "margin:0 0 12px" },
      t("srv_cambios_pie")));

  for (const r of filas) {
    caja.append(h("div", { clase: "tarjeta lisa", style: "margin:0 0 10px" },
      h("div", {},
        etiqueta(r.motivo_tipo || r.tipo, "alerta"), " ",
        h("b", {}, `${r.sale || "?"} → ${r.entra || "?"}`),
        h("span", { clase: "gris chico" },
          t("srv_dias_n").replace("{n}", r.jornadas_afectadas))),
      h("div", { clase: "chico gris" },
        t("srv_desde_f").replace("{f}", fecha(r.desde))
        + (r.hasta ? t("srv_hasta_f").replace("{f}", fecha(r.hasta))
                 : t("srv_en_adelante"))),
      r.motivo ? h("p", { clase: "chico", style: "margin:6px 0 0" },
                   `"${r.motivo}"`) : "",
      h("div", { clase: "chico gris", style: "margin-top:4px" },
        r.formalizo ? t("srv_formalizo").replace("{p}", r.formalizo) : "")));
  }
  return caja;
}'''

NUEVO = '''function bloqueCambios(filas) {
  const caja = h("div", { clase: "tarjeta" });
  if (!filas || !filas.length) return h("div");

  caja.append(h("h3", { style: "margin:0 0 2px" }, t("srv_cambios")),
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
  for (const d of r.jornadas_partidas || []) {
    tarjeta.append(h("div", { clase: "chico", style: "margin-top:4px" },
      t("srv_r_partido").replace("{f}", fecha(d.fecha))
        .replace("{p}", r.sale || "?").replace("{h}", d.hora)));
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

  return tarjeta;
}'''

assert s.count(VIEJO) == 1, "no encontre bloqueCambios"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("servicio.js: la tarjeta del cambio")

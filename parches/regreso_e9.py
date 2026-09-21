"""El banco de pruebas enseña los tres estados de la tarjeta."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/banco.html"
s = R.read_text()

VIEJO = '''const REEMPLAZOS = [{
  id: 1, tipo: "personal", sale: "Juan Ramirez", entra: "Luis Mendoza",
  motivo: "Se sintio mal y la central lo relevo a las 11:00",
  motivo_tipo: "contingencia", jornadas_afectadas: 4,
  desde: dia(0), hasta: null, formalizo: "Ana Solis",
  alerta_id: null, creado_en: `${dia(0)}T11:05:00`,
}];'''

NUEVO = '''/* Los tres estados de un cambio, para verlos juntos: uno corriendo con
   su dia partido, uno de implantado con tope de mes, y uno que ya cerro
   porque el titular volvio. */
const REEMPLAZOS = [{
  id: 1, tipo: "personal", sale: "Juan Ramirez", entra: "Luis Mendoza",
  motivo: "Se sintio mal y la central lo relevo a las 11:00",
  motivo_tipo: "contingencia", jornadas_afectadas: 4,
  desde: dia(0), hasta: null, formalizo: "Ana Solis",
  alerta_id: null, creado_en: `${dia(0)}T11:05:00`,
  en_curso: true, se_vuelve_a_pedir: false,
  partidos: [{ fecha: dia(0), hora: "11:05" }],
  regreso_en: null, regreso_por: null,
}, {
  id: 2, tipo: "personal", sale: "Marta Solis", entra: "Hector Palacios",
  motivo: "Incapacidad", motivo_tipo: "enfermedad", jornadas_afectadas: 12,
  desde: dia(-6), hasta: dia(8), formalizo: "Ana Solis",
  alerta_id: null, creado_en: `${dia(-6)}T08:10:00`,
  en_curso: true, se_vuelve_a_pedir: true, partidos: [],
  regreso_en: null, regreso_por: null,
}, {
  id: 3, tipo: "personal", sale: "Ana Torres", entra: "Beatriz Roman",
  motivo: "Vacaciones", motivo_tipo: "vacaciones", jornadas_afectadas: 5,
  desde: dia(-14), hasta: dia(-10), formalizo: "Ana Solis",
  alerta_id: null, creado_en: `${dia(-14)}T09:00:00`,
  en_curso: false, se_vuelve_a_pedir: false, partidos: [],
  regreso_en: `${dia(-11)}T17:30:00`, regreso_por: "Ana Solis",
}];'''
assert s.count(VIEJO) == 1, "no encontre REEMPLAZOS"
s = s.replace(VIEJO, NUEVO)

# La vista previa del regreso, para que el boton no muera en el banco.
ANCLA = '''  "/servicios/equipos/1/recomendaciones": {'''
PREVIA = '''  /* La vista previa del regreso: hasta que dia se queda el que cubria,
     el dia partido con su hora, y el dinero de los dos. */
  "/contingencia/reemplazos/1/regreso/vista-previa": {
    cerrado: 1, servicio_id: 1, regresa: "Juan Ramirez", sale: "Luis Mendoza",
    desde: dia(0), hasta: dia(2), dias_cubiertos: 3,
    jornadas_devueltas: [dia(3), dia(4)],
    jornadas_partidas: [dia(2)],
    jornadas_con_choque: [],
    hora_propuesta: `${dia(2)}T10:40:00`,
    viaticos: {
      a_comprobar: [{ persona_id: 2, monto: 900, limite: `${dia(5)}T23:59:00` }],
      cancelados: [],
      propuestos: [{ persona_id: 1, monto: 1500 }],
    },
  },
  "/servicios/equipos/1/recomendaciones": {'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, PREVIA)

R.write_text(s)
print("banco.html: los tres estados y la previa del regreso")

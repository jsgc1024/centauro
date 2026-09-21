/* La cola de lo que no se pudo mandar.

   El equipo marca su llegada en el estacionamiento de un hotel, bajo
   tierra, sin una barra de senal. Esa marca no se puede perder y no se
   puede inventar: se guarda en el telefono con la hora y la ubicacion
   del momento —que es cuando de verdad paso— y se manda sola en cuanto
   vuelve la linea.

   El servidor recibe la hora del telefono como lo que es: una
   afirmacion. Guarda tambien cuando le llego, y si la diferencia es
   grande lo manda a revision de la central. Por eso aqui se puede ser
   fiel a lo que paso sin abrirle la puerta a que alguien marque su
   llegada desde su casa media hora despues. */

const LLAVE = "centauro_cola";

export function pendientes() {
  try { return JSON.parse(localStorage.getItem(LLAVE) || "[]"); }
  catch { return []; }
}

function guardar(filas) {
  try { localStorage.setItem(LLAVE, JSON.stringify(filas)); }
  catch { /* sin espacio: se pierde la cola, no la sesion */ }
}

/* Cuanto se retiene una marca antes de salir.

   La hora de la marca se sella al tocar el boton, no al enviarla, asi
   que retenerla unos segundos no le mueve un minuto a nadie: lo unico
   que cambia es que durante ese rato todavia se puede deshacer. Es la
   diferencia entre una equivocacion que se corrige con el pulgar y una
   que se corrige con una llamada a la central. */

export function retenida(filas = null) {
  /* La ultima que entro y todavia no ha salido. Solo esa se puede
     deshacer: "deshacer" es la de hace un momento, no cualquiera de
     una lista. */
  const cola = filas || pendientes();
  return cola.length ? cola[cola.length - 1] : null;
}

export function sacar(id) {
  const quedan = pendientes().filter(x => String(x.id) !== String(id));
  guardar(quedan);
  return quedan.length;
}

export function encolar(item) {
  const filas = pendientes();
  /* El mismo paso del mismo dia no se guarda dos veces. Sin senal la
     pantalla no cambiaba al marcar, asi que el equipo volvia a tocar el
     boton: a la central le llegaban tres llegadas con tres horas
     distintas. Se queda la primera, que es la hora en que de verdad
     paso. */
  const suyo = (x) => x.jornada_id === item.jornada_id
    && x.cuerpo && item.cuerpo && x.cuerpo.tipo === item.cuerpo.tipo;
  if (item.cuerpo && item.cuerpo.tipo && filas.some(suyo)) return filas.length;

  filas.push({ ...item, id: Date.now() + Math.random(), intentos: 0 });
  guardar(filas);
  return filas.length;
}

/* Manda lo que haya, en orden. Lo que el servidor rechaza por una razon
   suya —fuera de geocerca, fuera de secuencia— no se reintenta para
   siempre: se saca de la cola y se le dice al equipo, porque reintentar
   algo que el servidor ya contesto que no es como se llena la cola de
   basura que nunca sale. */
export async function vaciar(mandar) {
  const filas = pendientes();
  if (!filas.length) return { enviados: 0, rechazados: [] };

  const quedan = [];
  const rechazados = [];
  let enviados = 0;

  const ahora = Date.now();
  for (const item of filas) {
    /* Todavia esta en su ventana de deshacer: no sale. No es un error
       ni un reintento, es una marca que el equipo puede retirar. */
    if (item.sale_en && item.sale_en > ahora) {
      quedan.push(item);
      continue;
    }
    try {
      await mandar(item);
      enviados++;
    } catch (err) {
      const codigo = err && err.codigo;
      // 4xx es una respuesta, no una falla de red: el servidor ya
      // decidio. 5xx y la falta de red si se reintentan.
      if (codigo && codigo >= 400 && codigo < 500) {
        rechazados.push({ item, motivo: err.message });
      } else {
        quedan.push({ ...item, intentos: (item.intentos || 0) + 1 });
      }
    }
  }
  guardar(quedan);
  return { enviados, rechazados, quedan: quedan.length };
}

export function limpiar() { guardar([]); apartadas.limpiar(); }


/* Lo que el servidor rechazo no vuelve a la cola, pero tampoco se tira.

   Se avisaba con un `alert` y se borraba para siempre: si el aviso
   saltaba con el telefono en el bolsillo, la prueba de que esa persona
   llego desaparecia y nadie se enteraba. Ahora se queda a la vista
   hasta que alguien la lea y la descarte a proposito. */
const RECHAZADAS = "centauro_rechazadas";

export const apartadas = {
  todas() {
    try { return JSON.parse(localStorage.getItem(RECHAZADAS) || "[]"); }
    catch { return []; }
  },
  apartar(filas) {
    if (!filas.length) return;
    const antes = apartadas.todas();
    for (const x of filas) {
      antes.push({
        id: Date.now() + Math.random(),
        tipo: x.item && x.item.cuerpo ? x.item.cuerpo.tipo : null,
        cuando: x.item && x.item.cuerpo ? x.item.cuerpo.marcado_en : null,
        motivo: x.motivo,
      });
    }
    try { localStorage.setItem(RECHAZADAS, JSON.stringify(antes)); }
    catch { /* sin espacio: al menos no se pierde la sesion */ }
  },
  descartar(id) {
    const quedan = apartadas.todas().filter(x => String(x.id) !== String(id));
    try { localStorage.setItem(RECHAZADAS, JSON.stringify(quedan)); }
    catch { /* nada que hacer */ }
  },
  limpiar() {
    try { localStorage.removeItem(RECHAZADAS); }
    catch { /* nada que hacer */ }
  },
};

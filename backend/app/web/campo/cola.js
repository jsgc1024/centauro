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
     una lista. La que va en vuelo ya no. */
  const cola = (filas || pendientes()).filter(x => !enVuelo.has(String(x.id)));
  return cola.length ? cola[cola.length - 1] : null;
}

/* Lo que esta saliendo en este momento. Una marca en vuelo ya no se
   puede deshacer --el servidor puede estar guardandola-- ni se vuelve a
   mandar en una segunda vuelta que arranque mientras tanto. */
const enVuelo = new Set();

function quitar(id) {
  guardar(pendientes().filter(x => String(x.id) !== String(id)));
}

function anotarIntento(id) {
  guardar(pendientes().map(x => String(x.id) === String(id)
    ? { ...x, intentos: (x.intentos || 0) + 1 } : x));
}

/* Deshacer. Falso si ya salio: entonces lo que hay es llamar a la
   central, no fingir que no paso. */
export function sacar(id) {
  if (enVuelo.has(String(id))) return false;
  quitar(id);
  return true;
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

/* Un rechazo por la sesion no es una decision del servidor sobre la
   marca: es que hay que volver a entrar. La marca se queda, con su hora
   y su ubicacion, y sale sola despues de entrar (seccion 99). */
function porSesion(err) {
  const codigo = err && err.codigo;
  return codigo === 401
    || (codigo === 403 && /sesi[oó]n|session|sessão/i.test(err.message || ""));
}

/* Manda lo que haya, en orden. Lo que el servidor rechaza por una razon
   suya —fuera de geocerca, fuera de secuencia— no se reintenta para
   siempre: se saca de la cola y se le dice al equipo, porque reintentar
   algo que el servidor ya contesto que no es como se llena la cola de
   basura que nunca sale.

   Tres reglas que salieron de la revision (seccion 99):

   - La cola nunca se reescribe entera. Se quita de ella solo lo que
     salio o lo que el servidor rechazo, por id. Antes se guardaba al
     final la foto con la que empezo la vuelta: la marca que el equipo
     hacia mientras el servidor tardaba desaparecia sin salir, y la que
     deshacia en ese rato volvia a aparecer y salia.
   - Al primer tropiezo de red se detiene la vuelta. Si la llegada agota
     su tiempo y el contacto si entra, el servidor rechaza el contacto
     por venir sin la llegada, y esa marca se perdia: lo que sigue
     espera su turno, en orden.
   - La sesion vencida no rechaza nada: la vuelta se detiene y las
     marcas esperan a que se vuelva a entrar. */
export async function vaciar(mandar) {
  const filas = pendientes();
  if (!filas.length) return { enviados: 0, rechazados: [], quedan: 0 };

  const rechazados = [];
  let enviados = 0;
  let detenida = null;

  const ahora = Date.now();
  for (const item of filas) {
    /* Todavia esta en su ventana de deshacer: no sale. No es un error
       ni un reintento, es una marca que el equipo puede retirar. */
    if (item.sale_en && item.sale_en > ahora) continue;
    const id = String(item.id);
    /* La deshicieron mientras salia otra, o ya va en otra vuelta. */
    if (enVuelo.has(id) || !pendientes().some(x => String(x.id) === id)) continue;
    enVuelo.add(id);
    try {
      await mandar(item);
      enviados++;
      quitar(id);
    } catch (err) {
      const codigo = err && err.codigo;
      if (porSesion(err)) {
        detenida = "sesion";
        break;
      }
      // 4xx es una respuesta, no una falla de red: el servidor ya
      // decidio. 5xx y la falta de red si se reintentan, en la
      // siguiente vuelta y en orden.
      if (codigo && codigo >= 400 && codigo < 500) {
        rechazados.push({ item, motivo: err.message });
        quitar(id);
      } else {
        anotarIntento(id);
        detenida = "red";
        break;
      }
    } finally {
      enVuelo.delete(id);
    }
  }
  return { enviados, rechazados, quedan: pendientes().length, detenida };
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

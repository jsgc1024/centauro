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

export function encolar(item) {
  const filas = pendientes();
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

  for (const item of filas) {
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

export function limpiar() { guardar([]); }

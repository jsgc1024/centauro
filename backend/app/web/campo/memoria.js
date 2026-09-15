/* Lo ultimo que se supo, guardado en el telefono.

   La app resolvia marcar sin senal pero no leer sin senal, que es justo
   al reves de lo que hace falta: en el estacionamiento subterraneo de
   un hotel, a las cinco de la manana, lo que urge es ver la direccion y
   el telefono del ejecutivo. Si eso viene del servidor, la pantalla
   sale en blanco ahi abajo.

   Por eso cada respuesta buena se guarda, y cuando no hay linea se
   muestra la ultima con su edad escrita. Un dato viejo que se sabe
   viejo sirve; uno viejo que se ve nuevo es peor que no tener nada. */

const PREFIJO = "centauro_memoria_";

export function guardar(llave, datos) {
  try {
    localStorage.setItem(PREFIJO + llave, JSON.stringify({
      en: new Date().toISOString(), datos,
    }));
  } catch { /* sin espacio: se sigue sin memoria, no se rompe */ }
}

export function recordar(llave) {
  try {
    const crudo = localStorage.getItem(PREFIJO + llave);
    if (!crudo) return null;
    return JSON.parse(crudo);
  } catch { return null; }
}

export function olvidar(llave = null) {
  // Con llave, olvida solo esa. Sin llave, todo —que es lo que hace
  // falta al salir de la sesion, y solo ahi.
  try {
    if (llave) return localStorage.removeItem(PREFIJO + llave);
    for (const k of Object.keys(localStorage)) {
      if (k.startsWith(PREFIJO)) localStorage.removeItem(k);
    }
  } catch { /* sin localStorage no hay nada que olvidar */ }
}

/* Pide al servidor y, si no contesta, echa mano de lo guardado.
   Devuelve {datos, de_memoria, en}. */
export async function traer(llave, pedir) {
  try {
    const datos = await pedir();
    guardar(llave, datos);
    return { datos, de_memoria: false, en: null };
  } catch (err) {
    // Un 401 o un 403 son respuestas del servidor, no falta de senal:
    // ahi la memoria no ayuda y esconderia el problema.
    if (err && err.codigo && err.codigo >= 400 && err.codigo < 500) throw err;
    const viejo = recordar(llave);
    if (!viejo) throw err;
    return { datos: viejo.datos, de_memoria: true, en: viejo.en };
  }
}

export function hace(iso) {
  if (!iso) return "";
  const minutos = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutos < 1) return "hace un momento";
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.round(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  return `hace ${Math.round(horas / 24)} d`;
}

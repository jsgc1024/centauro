/* Los catalogos se leen una sola vez por sesion: no cambian mientras
   alguien arma un servicio, y pedirlos en cada pantalla se siente lento. */
import { api } from "./api.js";

let guardados = null;

export async function catalogos(recargar = false) {
  if (guardados && !recargar) return guardados;
  const [paises, plazas, modalidades, perfiles, categorias, clientes,
         personal, vehiculos, hoteles, consultores] = await Promise.all([
    api.get("/catalogos/paises"),
    api.get("/catalogos/plazas"),
    api.get("/catalogos/modalidades"),
    api.get("/catalogos/perfiles"),
    api.get("/catalogos/categorias-vehiculo"),
    api.get("/catalogos/clientes"),
    api.get("/catalogos/personal"),
    api.get("/catalogos/vehiculos"),
    api.get("/catalogos/hoteles"),
    /* Quien puede llevar un servicio sale de los usuarios con rol de
       consultor, no del puesto de la persona: armar servicios es algo
       del acceso al sistema, y "consultor de seguridad" es un rol con
       el que se cubre un dia en la calle. Son dos cosas distintas. */
    api.get("/catalogos/consultores").catch(() => []),
  ]);
  guardados = {
    paises, plazas, modalidades, perfiles, categorias, clientes,
    personal, vehiculos, hoteles, consultores,
    /* Los cuatro roles con los que se cubre un servicio. Se llaman
       "perfiles" en la puerta por historia; en la consola son roles. */
    roles: perfiles,
  };
  if (!guardados.consultores.length) guardados.consultores = personal;
  return guardados;
}

export function nombreDe(coleccion, id) {
  const fila = (coleccion || []).find(x => String(x.id) === String(id));
  return fila ? (fila.nombre || fila.codigo) : "—";
}

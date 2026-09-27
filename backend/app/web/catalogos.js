/* Los catalogos se leen una sola vez por sesion: no cambian mientras
   alguien arma un servicio, y pedirlos en cada pantalla se siente lento. */
import { api, sesion } from "./api.js";
import { lista } from "./util.js";
import { t } from "./idioma.js";

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
  return guardados;
}

/* Quien lleva el servicio (seccion 87): solo quien tiene acceso de
   consultor, en el eventual y en el implantado. Antes, sin consultores
   con acceso, la lista caia en la plantilla completa y salia cualquiera
   --direccion general incluida-- (Salvador, 27 sep). El consultor que da
   de alta se propone a si mismo; quien no es consultor escoge, y no se le
   escoge a nadie por el. */
export function listaDeConsultores(cat) {
  const suyo = sesion.usuario
    && cat.consultores.find(c => c.id === sesion.usuario.persona_id);
  const primera = !cat.consultores.length ? t("consultor_ninguno")
    : suyo ? null : t("consultor_escoge");
  const select = lista("consultor_id", [
    ...(primera ? [{ valor: "", texto: primera }] : []),
    ...cat.consultores.map(c => ({ valor: c.id, texto: c.nombre }))]);
  select.value = suyo ? String(suyo.id) : "";
  return select;
}

/* Falta escogerlo si hay de donde. Sin nadie con acceso de consultor el
   alta no se detiene: el servicio queda sin asignar hasta que lo haya. */
export function faltaConsultor(cat, select) {
  return cat.consultores.length > 0 && !select.value;
}

export function nombreDe(coleccion, id) {
  const fila = (coleccion || []).find(x => String(x.id) === String(id));
  return fila ? (fila.nombre || fila.codigo) : "—";
}

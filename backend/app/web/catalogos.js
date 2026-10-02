/* Los catalogos se leen una sola vez por sesion: no cambian mientras
   alguien arma un servicio, y pedirlos en cada pantalla se siente lento. */
import { api, sesion } from "./api.js";
import { h, lista } from "./util.js";
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


/* ------------------------------------------------------------ el cliente, por pais */

/* Seccion 125 (Salvador, 2 de octubre): una pestana por pais arriba de
   «Cliente» --en la cotizacion, la propuesta y el tarifario del cliente--
   para no buscar a Amazon Brasil entre los de Mexico. Arranca en el
   ultimo pais que se escogio en esta computadora; la primera vez, en el
   que mas clientes tiene. Lo recordado es solo una comodidad: si no se
   puede leer, se arranca en el de siempre. */
const LLAVE_PAIS = "centauro_pais_de_clientes";

export function clientesDelPais(cat, paisId) {
  return cat.clientes.filter(c => c.activo !== false && String(c.pais_id) === String(paisId));
}

/* Los paises, el de mas clientes primero. */
export function paisesDeClientes(cat) {
  const cuantos = (p) => clientesDelPais(cat, p.id).length;
  return cat.paises.filter(p => p.activo !== false)
    .sort((a, b) => cuantos(b) - cuantos(a) || a.nombre.localeCompare(b.nombre));
}

export function paisDeArranque(cat) {
  const paises = paisesDeClientes(cat);
  let guardado = null;
  try {
    guardado = localStorage.getItem(LLAVE_PAIS);
  } catch {
    guardado = null;
  }
  const suyo = paises.find(p => String(p.id) === String(guardado));
  return (suyo || paises[0] || {}).id ?? null;
}

export function recordarPais(paisId) {
  try {
    localStorage.setItem(LLAVE_PAIS, String(paisId));
  } catch {
    /* Sin donde guardarlo, la siguiente vez arranca en el de siempre. */
  }
}

/* Las pestanas, con cuantos clientes tiene cada pais. Con un solo pais
   no hay nada que escoger y no se ponen. */
export function pestanasDeClientes(cat, paisId, alCambiar) {
  const paises = paisesDeClientes(cat);
  if (paises.length < 2) return null;
  return h("div", { clase: "pestanas", style: "margin:12px 0 0" },
    ...paises.map(p => h("button", {
      type: "button",
      clase: String(p.id) === String(paisId) ? "pestana chico activa" : "pestana chico",
      onclick: () => { if (String(p.id) !== String(paisId)) alCambiar(p.id); },
    }, `${p.nombre} (${clientesDelPais(cat, p.id).length})`)));
}

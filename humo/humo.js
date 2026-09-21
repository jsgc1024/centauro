/* Prueba de humo: abre la consola y la app en un navegador de verdad.
 *
 * La bateria mira el motor: que el dinero cuadre, que un dia no se
 * cierre dos veces, que el plazo corra en la hora del pais. Nada de eso
 * ve una pantalla. En un solo dia salieron cuatro defectos que la
 * bateria no podia tocar --un `nullnull` en la cima de una pantalla, un
 * boton sin listener, dos fotos encimadas, un "20/09: None"-- y cada
 * uno se encontro porque alguien se topo con el.
 *
 * Esto recorre las pantallas y falla por tres cosas, las tres baratas
 * de revisar y caras de encontrar a mano:
 *
 *   1. Errores de JavaScript. Uno sin atrapar mata el resto de la
 *      pantalla EN SILENCIO: el boton sigue ahi y no hace nada.
 *   2. Texto basura --null, undefined, NaN, None, [object Object]--.
 *      Es lo que sale cuando un dato no llego y nadie lo previo.
 *   3. Contenido que se sale de la pantalla. Una foto sin ancho se
 *      pinta a su tamano natural y se monta encima de la de al lado.
 *
 * Lo que NO hace, y hay que decirlo: no juzga. Un panel que aparece
 * donde nadie lo ve, una hora heredada que confunde o una lista que se
 * quedo con la foto vieja le parecen bien. Eso lo ve una persona.
 *
 * Guarda una captura de cada pantalla en humo/capturas/ para poder
 * pasarlas rapido.
 */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.BASE || "http://api:8000";
const CORREO = process.env.CORREO || "direccion@centauro.lat";
const CLAVE = process.env.CLAVE || "centauro2026";
const CAMPO_CORREO = process.env.CAMPO_CORREO || "juan.ramirez@centauro.lat";
const CAMPO_CLAVE = process.env.CAMPO_CLAVE || "centauro2026";
const CAPTURAS = path.join(__dirname, "capturas");

/* Lo que nunca debe verse en una pantalla. Va con espacios alrededor
   --o pegado a signos-- para no cazar la palabra dentro de otra: una
   nota que diga "Anulada" no es `null`. */
const BASURA = [
  /\bnull\b/i, /\bundefined\b/i, /\bNaN\b/i,
  /\[object Object\]/, /\bNone\b/,
];

/* Pantallas de la consola. El nombre es el que sale en el reporte. */
const CONSOLA = [
  ["panorama", "#/panorama"],
  ["eventuales", "#/servicios"],
  ["implantados", "#/implantados"],
  ["central", "#/central"],
  ["finanzas", "#/finanzas"],
  ["nomina", "#/nomina"],
  ["personal", "#/equipo"],
  ["bonos", "#/bonos"],
  ["encuestas", "#/encuestas"],
  ["codigo", "#/codigo"],
  ["accesos", "#/accesos"],
];

const APP = [
  ["app-hoy", "#/hoy"],
  ["app-viaticos", "#/viaticos"],
  ["app-pagos", "#/pagos"],
  ["app-yo", "#/yo"],
];

const fallas = [];
const revisadas = [];

function anotar(pantalla, que) {
  fallas.push(`${pantalla}: ${que}`);
}

/* Se espera a que la pantalla deje de trabajar, no un numero fijo de
   milisegundos. Casi todas piden datos al abrir y pintan despues. */
async function asentar(pagina) {
  try {
    await pagina.waitForLoadState("networkidle", { timeout: 8000 });
  } catch { /* alguna deja una peticion viva; no es falla */ }
  await pagina.waitForTimeout(400);
}

async function revisar(pagina, nombre, errores) {
  await asentar(pagina);
  // El escucha de respuestas lee el cuerpo, que es asincrono: sin este
  // respiro, la falla se le achaca a la pantalla siguiente.
  await pagina.waitForTimeout(200);
  await pagina.screenshot({ path: path.join(CAPTURAS, `${nombre}.png`),
                            fullPage: true });

  for (const e of errores.splice(0)) anotar(nombre, `error de JS: ${e}`);

  const texto = await pagina.evaluate(() => document.body.innerText);
  for (const patron of BASURA) {
    const hallado = texto.match(patron);
    if (hallado) {
      /* Con el renglon donde salio: "null" a secas no dice donde
         buscar. */
      const linea = texto.split("\n").find(l => patron.test(l)) || "";
      anotar(nombre, `texto basura "${hallado[0]}" en: ${linea.trim().slice(0, 90)}`);
    }
  }

  const ancho = await pagina.evaluate(() => ({
    contenido: document.documentElement.scrollWidth,
    ventana: window.innerWidth,
  }));
  // Doce pixeles de tolerancia: un borde redondeado o una sombra no es
  // un desbordamiento.
  if (ancho.contenido > ancho.ventana + 12) {
    anotar(nombre, `se sale de la pantalla: ${ancho.contenido}px de contenido `
                   + `en ${ancho.ventana}px de ventana`);
  }

  const vacia = texto.trim().length < 20;
  if (vacia) anotar(nombre, "la pantalla salio vacia");

  revisadas.push(nombre);
}

/* Cada pantalla arranca con su propia lista de errores: si no, el error
   de la primera se le achaca a la ultima. */
function escuchar(pagina) {
  const errores = [];
  pagina.on("pageerror", (e) => errores.push(e.message));
  pagina.on("console", (m) => {
    if (m.type() === "error") errores.push(m.text());
  });

  /* La consola del navegador dice "status 409" y nada mas. Con eso hay
     que adivinar cual de las veinte peticiones de la pantalla fallo.
     Aqui se anota el metodo, la ruta y lo que contesto el servidor, que
     es lo unico que sirve para ir a buscarlo. */
  pagina.on("response", async (r) => {
    if (r.status() < 400) return;
    const ruta = r.url().replace(BASE, "");
    let dijo = "";
    try {
      const cuerpo = await r.text();
      dijo = cuerpo ? ` · ${cuerpo.slice(0, 200)}` : "";
    } catch { /* algunas respuestas ya no se pueden leer */ }
    errores.push(`${r.status()} en ${r.request().method()} ${ruta}${dijo}`);
  });

  return errores;
}

async function entrar(pagina, ruta, correo, clave) {
  await pagina.goto(`${BASE}${ruta}`, { waitUntil: "domcontentloaded" });
  await asentar(pagina);
  const campos = pagina.locator("input[type=email], input[type=password]");
  if (await campos.count() < 2) return true;   // ya habia sesion
  await pagina.locator("input[type=email]").first().fill(correo);
  await pagina.locator("input[type=password]").first().fill(clave);
  await pagina.locator("button").first().click();

  /* Entrar no navega: la consola es una sola pagina que se repinta.
     Como el navegador ya estaba quieto, `networkidle` resuelve de
     inmediato y la revision caia a los 400ms, con la peticion del token
     todavia en vuelo: la prueba decia "no se pudo entrar" sobre un
     login que si funcionaba. Se espera a que el campo de contrasena
     desaparezca, que es la senal de que ya se pinto lo de adentro. */
  try {
    await pagina.locator("input[type=password]").first()
      .waitFor({ state: "detached", timeout: 20000 });
  } catch { /* si no se fue, abajo se dice por que */ }
  await asentar(pagina);

  const sigue = await pagina.locator("input[type=password]").count();
  if (sigue) {
    /* Con el motivo, si la pantalla lo dijo. "No se pudo entrar" a
       secas no distingue una clave mala de una cuenta bloqueada. */
    const texto = await pagina.evaluate(() => document.body.innerText);
    const linea = texto.split("\n").map(l => l.trim())
      .find(l => l.length > 8 && !/correo|contrase/i.test(l));
    if (linea) anotar(ruta, `la pantalla dijo: ${linea.slice(0, 120)}`);
  }
  return sigue === 0;
}

async function recorrer(navegador, ruta, correo, clave, pantallas, ancho) {
  const contexto = await navegador.newContext({
    viewport: { width: ancho, height: 900 },
    locale: "es-MX",
    /* La app de campo pide ubicacion para marcar. Se concede una fija:
       sin esto, cada pantalla se queda esperando un permiso que nadie
       va a contestar. */
    permissions: ["geolocation"],
    geolocation: { latitude: 19.4270, longitude: -99.1677 },
  });
  const pagina = await contexto.newPage();
  const errores = escuchar(pagina);

  const dentro = await entrar(pagina, ruta, correo, clave);
  if (!dentro) {
    anotar(ruta, "no se pudo entrar con la cuenta de prueba");
    await pagina.screenshot({ path: path.join(CAPTURAS, "entrada-fallida.png") });
    await contexto.close();
    return;
  }

  for (const [nombre, hash] of pantallas) {
    await pagina.goto(`${BASE}${ruta}${hash}`, { waitUntil: "domcontentloaded" });
    await revisar(pagina, nombre, errores);
  }

  /* Un servicio por dentro: es la pantalla mas grande de la consola y
     la que mas se toca. Se entra al primero de la lista. */
  if (ruta === "/") {
    await pagina.goto(`${BASE}/#/servicios`,
                      { waitUntil: "domcontentloaded" });
    await asentar(pagina);
    const fila = pagina.locator("tr.clic, table a").first();
    if (await fila.count()) {
      await fila.click();
      await revisar(pagina, "servicio-por-dentro", errores);
    }
  }

  await contexto.close();
}

(async () => {
  fs.mkdirSync(CAPTURAS, { recursive: true });
  const navegador = await chromium.launch();
  try {
    /* La consola vive en la raiz: `/consola` sirve los archivos, pero
       quien pinta la pantalla es la ruta `/`. */
    await recorrer(navegador, "/", CORREO, CLAVE, CONSOLA, 1400);
    await recorrer(navegador, "/app/", CAMPO_CORREO, CAMPO_CLAVE, APP, 390);
  } finally {
    await navegador.close();
  }

  console.log(`\nRevisadas ${revisadas.length} pantallas.`);
  console.log(`Capturas en humo/capturas/\n`);
  if (!fallas.length) {
    console.log("Sin humo.");
    process.exit(0);
  }
  console.log(`${fallas.length} cosa(s) que mirar:\n`);
  for (const f of fallas) console.log(`  ${f}`);
  process.exit(1);
})();

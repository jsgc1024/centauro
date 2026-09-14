/* El trabajador de fondo de la app.

   Hace dos cosas, y las dos importan cuando el telefono esta guardado
   en el bolsillo:

   1. Entrega los avisos. La confirmacion de la vispera llega aunque la
      app este cerrada; sin esto dependia de que alguien se acordara de
      abrirla.

   2. Guarda el armazon de la app —la pagina, el estilo, el codigo— para
      que abra sin senal. Los datos ya se guardan aparte; esto es para
      que la app siquiera arranque en un estacionamiento subterraneo.
      Sin esto, ahi abajo el telefono enseña la pantalla de "sin
      conexion" del navegador y todo lo demas no sirve de nada. */

const CACHE = "centauro-campo-v1";
const ARMAZON = [
  "/app/",
  "/app/index.html",
  "/app/estilo.css",
  "/app/app.js",
  "/app/cola.js",
  "/app/memoria.js",
  "/app/foto.js",
  "/consola/api.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE)
    .then((c) => c.addAll(ARMAZON))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((llaves) => Promise.all(
      llaves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

/* Solo el armazon sale del cache. Los datos NUNCA: una respuesta vieja
   servida como nueva es peor que un error, porque el equipo actuaria
   sobre un punto de encuentro que ya cambio. De eso se encarga la
   memoria de la app, que si dice cuando se supo. */
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (!ARMAZON.includes(url.pathname)) return;

  e.respondWith(
    fetch(e.request)
      .then((r) => {
        const copia = r.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copia));
        return r;
      })
      .catch(() => caches.match(e.request)));
});

/* ------------------------------------------------------- los avisos */

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = {}; }

  e.waitUntil(self.registration.showNotification(d.titulo || "Centauro", {
    body: d.cuerpo || "",
    // Que el aviso reemplace al anterior del mismo tipo en vez de
    // apilarse: tres recordatorios iguales en la pantalla de bloqueo se
    // leen como una falla de la app, no como insistencia.
    tag: d.etiqueta || "centauro",
    renotify: true,
    data: { url: d.url || "/app/" },
    icon: "/app/icono.png",
    badge: "/app/icono.png",
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const destino = (e.notification.data && e.notification.data.url) || "/app/";
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true })
    .then((abiertas) => {
      // Si la app ya esta abierta se usa esa ventana, en vez de
      // acumular pestanas cada vez que llega un aviso.
      for (const c of abiertas) {
        if (c.url.includes("/app/") && "focus" in c) {
          c.navigate(destino);
          return c.focus();
        }
      }
      return clients.openWindow(destino);
    }));
});

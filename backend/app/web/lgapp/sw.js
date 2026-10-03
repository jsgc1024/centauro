/* El trabajador de fondo de LG Connect, la app de los operadores de
   Logistica (seccion 151). Guarda el armazon para que la app abra en el
   patio sin senal; los datos nunca salen del cache: una marca de ayer
   servida como de hoy es peor que un error. Los avisos al telefono
   llegan con el bloque 6. */

const CACHE = "centauro-lg-v1";
const ARMAZON = [
  "/lgapp/", "/lgapp/index.html", "/lgapp/app.js", "/lgapp/lg.css",
  "/lgapp/manifiesto.json", "/consola/idioma.js", "/consola/firma.js",
  "/app/estilo.css", "/app/icono-192.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE)
    .then((c) => Promise.allSettled(ARMAZON.map((r) => c.add(r))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((llaves) => Promise.all(llaves.filter((k) => k.startsWith("centauro-lg-")
                                                  && k !== CACHE)
                                        .map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || !ARMAZON.includes(url.pathname)) return;
  e.respondWith(fetch(e.request)
    .then((r) => {
      const copia = r.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copia));
      return r;
    })
    .catch(() => caches.match(e.request)));
});

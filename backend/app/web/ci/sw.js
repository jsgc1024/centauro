/* El trabajador de fondo de la app del cliente de la Central (seccion
   133). Lo mismo que el de la app de campo, en corto: entrega los
   avisos aunque la app este cerrada, y guarda el armazon para que abra
   sin senal. Los datos nunca salen del cache: un mapa viejo servido
   como nuevo es peor que un error. */

const CACHE = "centauro-ci-v1";
const ARMAZON = [
  "/ci/", "/ci/index.html", "/ci/app.js", "/ci/ci.css", "/consola/idioma.js",
  "/ci/manifiesto.json", "/app/estilo.css", "/consola/firma.js",
  "/app/icono-192.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE)
    .then((c) => Promise.allSettled(ARMAZON.map((r) => c.add(r))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((llaves) => Promise.all(llaves.filter((k) => k.startsWith("centauro-ci-")
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

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = {}; }
  e.waitUntil(self.registration.showNotification(d.titulo || "Centauro", {
    body: d.cuerpo || "",
    tag: d.etiqueta || "centauro-ci",
    renotify: true,
    data: { url: d.url || "/ci/" },
    icon: "/app/icono-192.png",
    badge: "/app/icono-192.png",
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const destino = (e.notification.data || {}).url || "/ci/";
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true })
    .then((abiertas) => {
      for (const c of abiertas) {
        if (c.url.includes("/ci/") && "focus" in c) {
          c.navigate(destino);
          return c.focus();
        }
      }
      return clients.openWindow(destino);
    }));
});

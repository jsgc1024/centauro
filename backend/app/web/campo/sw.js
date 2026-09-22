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

/* La version del cache se sube a mano cuando cambia el armazon: al
   activarse, el trabajador nuevo borra los caches con otro nombre. Sin
   subirla, el telefono que ya tenia la app instalada seguiria sirviendo
   el armazon viejo del cache. */
const CACHE = "centauro-campo-v7";
const ARMAZON = [
  "/app/",
  "/app/index.html",
  "/app/estilo.css",
  "/app/app.js",
  "/app/cola.js",
  "/app/memoria.js",
  "/app/foto.js",
  "/consola/api.js",
  /* Y el idioma, que app.js importa al arrancar. Sin esto el modulo no
     carga sin senal, el grafo falla entero y la app abre en blanco:
     justo el sotano para el que existe este archivo. */
  "/consola/idioma.js",
  "/app/manifiesto.json",
  /* El icono del aviso se guarda tambien: si no, el aviso que llega en
     el estacionamiento sale sin icono, que es como se ven los avisos de
     una app que no se reconoce. */
  "/app/icono-192.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE)
    /* Una por una y sin rendirse: con addAll, una sola ruta que
       conteste 404 tira la instalacion completa y entonces no hay
       service worker --ni armazon, ni avisos--. Mas vale guardar lo que
       si esta. */
    .then((c) => Promise.allSettled(ARMAZON.map((r) => c.add(r))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((llaves) => Promise.all(
      /* El cache de la senal del principal es de la app, no del
         armazon: cambiar de version no lo tira. Se necesita justo
         donde no hay red para volver a bajarla. */
      llaves.filter((k) => k !== CACHE && k !== "centauro-senal")
            .map((k) => caches.delete(k))))
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

  /* Un boton en la propia notificacion. Confirmar que vas eran cuatro
     toques --desbloquear, abrir, buscar el servicio, confirmar-- a las
     seis de la manana y con una mano. */
  const acciones = d.accion === "confirmar"
    ? [{ action: "confirmar", title: "Confirmo de enterado" }]
    : d.accion === "en_camino"
      ? [{ action: "en_camino", title: "Voy en camino" }]
      : [];

  e.waitUntil(self.registration.showNotification(d.titulo || "Centauro", {
    body: d.cuerpo || "",
    actions: acciones,
    // Que el aviso reemplace al anterior del mismo tipo en vez de
    // apilarse: tres recordatorios iguales en la pantalla de bloqueo se
    // leen como una falla de la app, no como insistencia.
    tag: d.etiqueta || "centauro",
    renotify: true,
    data: { url: d.url || "/app/", accion: d.accion || null },
    icon: "/app/icono-192.png",
    badge: "/app/icono-192.png",
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const datos = e.notification.data || {};
  /* Si se pico el boton de confirmar, la app abre sabiendo que viene a
     confirmar y lo hace sola. Desde aqui no se puede llamar al servidor:
     el permiso de la sesion vive en la app, no en el trabajador. */
  const destino = e.action === "confirmar"
    ? "/app/#/hoy?confirmar=1"
    : e.action === "en_camino"
      ? "/app/#/hoy?en_camino=1"
      : (datos.url || "/app/");
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

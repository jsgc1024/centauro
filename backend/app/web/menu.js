/* El menu de la consola: que pantallas hay, en que grupo van y quien
   las abre.

   Vivia dentro de app.js. Se mudo aqui en la seccion 73 porque ahora lo
   leen dos: el armazon, que pinta la barra, y la pantalla de Accesos, que
   ofrece estas mismas pantallas como casillas al armar un puesto. Dos
   copias se separan; una sola no.

   Quien abre cada pantalla lo decide, desde la seccion 73, su PUESTO si
   su puesto dice sus pantallas; si no, su ROL, con las listas de abajo,
   como siempre. El servidor sigue cuidando cada puerta: esto decide que
   se pinta, no que se puede. */

export const CONSULTA = ["consultor", "director_operaciones", "director_general", "admin"];
/* La operacion en vivo: los mismos roles que el servidor deja ver
   (panorama.ver). Estaba abierta a todos y Recursos Humanos, sin puesto,
   la abria para leer "No tienes permiso" (seccion 73). */
export const PANORAMA = ["consultor", "central", "finanzas", "director_operaciones",
                  "director_general", "admin"];
/* El consultor tambien entra: la central de inteligencia le dice que le
   falta a SUS servicios de manana, y es el que lo tiene que resolver
   antes del corte. Dejarlo fuera era mandarle el recado por telefono. */
export const MONITOREO = ["central", "consultor", "director_operaciones",
                   "director_general", "admin"];
/* La bandeja de finanzas la abre finanzas; direccion la mira sin tocar. */
export const DINERO = ["finanzas", "director_operaciones", "director_general", "admin"];
/* Nominas (seccion 66): lo de DINERO, y el consultor para ver su propia
   comision --lo que se le va a pagar, lo que no y por que--. La pantalla
   solo le ensena esa pestana, y el servidor solo le manda lo suyo. */
export const NOMINAS = [...DINERO, "consultor"];
/* Quien le dicta el codigo al personal de campo. La central porque
   esta despierta a las 5:40, que es cuando de verdad pasa; el
   consultor porque conoce a su gente por la voz, que es lo unico que
   protege este camino. Direccion de operaciones no entra. */
export const CODIGO = ["consultor", "central", "director_general", "admin"];
/* Quien reparte permisos. Direccion general quedo como super
   administrador por decision de la direccion (ver PROPUESTA_ACCESOS.md):
   quien puede abrir esta pantalla puede darle a alguien un permiso que
   cuesta dinero. */
export const ADMINISTRA = ["admin", "director_general", "recursos_humanos"];
/* El desempeno lo mira casi todo el mundo y lo toca casi nadie: la
   central y el consultor ven el mes de su gente, operaciones firma,
   finanzas deposita. Quien autoriza y quien paga se separan en el
   servidor, no aqui. */
export const DESEMPENO = ["consultor", "central", "finanzas", "recursos_humanos",
                   "director_operaciones", "director_general", "admin"];
/* Lo que dijo el cliente. Lo abre quien puede hacer algo con eso: el
   consultor revisa lo suyo, operaciones lo de todos, la central porque
   es quien contesta el telefono cuando el cliente vuelve a llamar. */
export const VOZ_CLIENTE = ["consultor", "central", "finanzas",
                     "director_operaciones", "director_general", "admin"];
/* Lo que Centauro lee de Odoo (seccion 64). Lo abre quien puede leerlo y
   guardarlo: el servidor pide administracion, y direccion general la
   hereda. Aplicar da de alta gente con acceso a la app. */
export const LEE_ODOO = ["admin", "director_general"];

/* El menu de arriba, en una sola lista.

   De aqui sale la barra Y sale el recorrido de la primera vez. Son la
   misma cosa dicha dos veces, y dos listas se separan: el dia que se
   agregue una pantalla, el recorrido la trae sola o `revisar.py` se
   queja de que le falta el texto. Un tutorial que vive aparte se
   despega el dia que la pantalla cambia, y nadie se entera hasta que
   alguien sigue un paso que ya no existe.

   `quienes` en nulo quiere decir que la ve todo el mundo.

   `necesita` es la actividad sin la cual la pantalla abre vacia --lo
   primero que pide al servidor--. La usa la pantalla de Puestos para
   avisar cuando alguien marca una pantalla sin lo que la llena, y para
   no ofrecer la que ningun puesto puede abrir: Odoo pide administracion
   por rol (seccion 73). */
export const MENU = [
  /* Las tres de operacion van juntas bajo un solo boton.
     Sueltas eran tres de once entradas, y once no caben en la barra
     sin apretarla. Y el grupo lleva la linea en el nombre --EP, por
     Proteccion Ejecutiva-- porque vienen mas lineas de operacion: el
     dia que llegue la siguiente, este menu ya sabe como crecer. */
  { ruta: "/panorama", clave: "panorama", necesita: "panorama.ver", texto: "nav_operacion", grupo: "nav_operaciones_ep",
    cuenta: "rec_operacion", quienes: PANORAMA },
  /* Eventual e implantado son dos operaciones distintas y se capturan
     distinto; cada una tiene su boton para no tener que escoger el tipo
     dentro de una pantalla que sirve para las dos. */
  { ruta: "/servicios", clave: "servicios", necesita: "servicios.ver", texto: "nav_eventuales", grupo: "nav_operaciones_ep",
    /* Estando dentro de un servicio, el boton del grupo sigue
       encendido: `#/servicio/12` no empieza con `#/servicios`. */
    tambien: ["/servicio/"],
    cuenta: "rec_eventuales", quienes: CONSULTA },
  { ruta: "/implantados", clave: "implantados", necesita: "implantado.ver", texto: "nav_implantados", grupo: "nav_operaciones_ep",
    tambien: ["/implantado/"],
    cuenta: "rec_implantados", quienes: CONSULTA },
  /* Central de Inteligencia: el tablero de lo que esta corriendo y el
     codigo que se le dicta al personal de campo. Los dos son la misma
     mesa a las 5:40 de la manana. */
  { ruta: "/central", clave: "central", necesita: "operacion.ver", texto: "nav_central", grupo: "nav_operaciones_ci",
    cuenta: "rec_central", quienes: MONITOREO },
  /* Gestion Administrativa: lo que se paga y quien puede que cosa.
     Dos bolsas distintas y dos pantallas: los gastos del servicio
     —viaticos y compras— y las nominas: la del personal de seguridad y
     la comision de los consultores. */
  { ruta: "/finanzas", clave: "finanzas", necesita: "viaticos.ver", texto: "nav_finanzas", grupo: "nav_administrativa",
    cuenta: "rec_finanzas", quienes: DINERO },
  /* Lo que ya tiene el visto bueno del consultor y espera a finanzas:
     aprobarlo, regresarlo o reintentar su factura (seccion 59). Existian
     los endpoints y no la pantalla. */
  { ruta: "/facturacion", clave: "facturacion", necesita: "cierre.ver", texto: "nav_facturacion", grupo: "nav_administrativa",
    cuenta: "rec_facturacion", quienes: DINERO },
  { ruta: "/nomina", clave: "nomina", necesita: ["nomina.ver", "comisiones.ver"], texto: "nav_nomina", grupo: "nav_administrativa",
    cuenta: "rec_nomina", quienes: NOMINAS },
  /* El personal va en Operaciones EP: a quien se manda es una decision
     de operacion, y se toma mirando la misma cartera. */
  { ruta: "/equipo", clave: "equipo", necesita: "profesionalismo.ver", texto: "nav_personal", grupo: "nav_operaciones_ep",
    cuenta: "rec_personal", quienes: CONSULTA },
  /* La flota con su GPS (seccion 60), junto a Personal: a quien se
     manda y en que se manda se deciden mirando lo mismo. La abre quien
     monitorea --consultor, central y direccion--; no dice donde esta
     ninguna unidad. */
  { ruta: "/unidades", clave: "unidades", necesita: "unidades.ver", texto: "nav_unidades", grupo: "nav_operaciones_ep",
    cuenta: "rec_unidades", quienes: MONITOREO },
  /* El desempeno del personal y su bono del mes vencido, que se
     calcula el dia 3 y se deposita el 5. Va en Operaciones EP
     --decision de Salvador, 23 sep--, junto a Personal: lo que mide
     es como trabajo la gente en la calle, y lo consulta quien decide
     a quien se manda. Estaba junto a la nomina porque el bono es
     dinero. */
  { ruta: "/bonos", clave: "bonos", necesita: "bonos.ver", texto: "nav_bonos", grupo: "nav_operaciones_ep",
    cuenta: "rec_bonos", quienes: DESEMPENO },
  /* La voz del cliente. Una calificacion baja abre revision y hasta
     hoy nadie podia verla: el motor llevaba meses escrito sin pantalla.

     Va en Operaciones EP --decision de Salvador-- y no suelta en la
     barra: lo que el cliente califica es el servicio, y quien lee una
     calificacion baja acaba abriendo la cartera en el mismo minuto. */
  { ruta: "/encuestas", clave: "encuestas", necesita: "encuestas.ver", texto: "nav_encuestas", grupo: "nav_operaciones_ep",
    cuenta: "rec_encuestas", quienes: VOZ_CLIENTE },
  /* A un toque, porque la llamada llega a las 5:40 y casi siempre al
     telefono. Escondida dentro de un servicio serian cuatro toques con
     una mano. */
  { ruta: "/codigo", clave: "codigo", necesita: "codigo.dictar", texto: "nav_codigo", grupo: "nav_operaciones_ci",
    cuenta: "rec_codigo", quienes: CODIGO },
  { ruta: "/accesos", clave: "accesos", necesita: "accesos.dar", texto: "nav_accesos", grupo: "nav_administrativa",
    cuenta: "rec_accesos", quienes: ADMINISTRA },
  /* La primera lectura del personal y de la flota, y lo que falta
     corregir en Odoo. Vivia en la terminal del servidor, que en
     produccion ya no se abre (seccion 64). */
  { ruta: "/odoo", clave: "odoo", necesita: null, texto: "nav_odoo", grupo: "nav_administrativa",
    cuenta: "rec_odoo", quienes: LEE_ODOO },
];

/* Si esta persona abre esta pantalla. Con puesto que dice sus
   pantallas, manda el puesto; sin eso, su rol, como antes de que los
   puestos existieran. `roles` en nulo quiere decir que la abre todo el
   mundo. */
export function abre(usuario, clave, roles) {
  if (!usuario) return false;
  if (Array.isArray(usuario.pantallas)) return usuario.pantallas.includes(clave);
  return !roles || roles.includes(usuario.rol);
}

export function menuDe(usuario) {
  return MENU.filter(x => abre(usuario, x.clave, x.quienes));
}

/* A donde entra cada quien. Lo de siempre por rol --la central a su
   tablero, el consultor a su cartera, finanzas a su bandeja, RRHH al
   bono--, si su menu la trae; si no, la primera de su menu en este
   orden, que es el de lo que mas se usa. */
const PRIMERO = ["central", "servicios", "finanzas", "facturacion", "nomina",
                 "bonos", "equipo", "accesos", "panorama"];
const POR_ROL = { central: "central", consultor: "servicios",
                  finanzas: "finanzas", recursos_humanos: "bonos" };

export function destinoDe(usuario) {
  const suyas = new Set(menuDe(usuario).map(x => x.clave));
  const deRol = POR_ROL[usuario && usuario.rol] || "panorama";
  if (suyas.has(deRol)) return `#/${rutaDe(deRol)}`;
  const otra = PRIMERO.find(c => suyas.has(c)) || [...suyas][0];
  return otra ? `#/${rutaDe(otra)}` : "#/panorama";
}

function rutaDe(clave) {
  const x = MENU.find(m => m.clave === clave);
  return x ? x.ruta.slice(1) : "panorama";
}

/* Las pantallas que un puesto puede traer, en el orden del menu. */
export const PARA_PUESTOS = MENU.filter(x => x.necesita);

/* Lo que le falta a un puesto para que esta pantalla no le abra vacia:
   la actividad (o una de las actividades) que la llena. Nulo si no le
   falta nada. */
export function leFaltaPara(x, actividades) {
  const piden = Array.isArray(x.necesita) ? x.necesita : [x.necesita];
  return piden.some(a => actividades.has(a)) ? null : piden[0];
}

/* Lo que esta persona puede hacer, segun el servidor: para no pintar un
   boton que va a contestar 403. Sale de /auth/yo. */
export function tiene(usuario, actividad) {
  return !!(usuario && (usuario.actividades || []).includes(actividad));
}

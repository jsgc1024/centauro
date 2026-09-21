# Revisión de la app de campo

20 de septiembre de 2026. Pedida por Salvador: *"veamos todo lo que se
tenga que revisar de la app también, notificaciones push etc."*

Se revisó la app del personal (`backend/app/web/campo/`), su service
worker, su cola sin conexión, el backend que consume
(`routers/campo.py`, `operacion.py`, `revision.py`) y todo el camino de
las notificaciones push (`push.py`, `sw.js`, `celery_app.py`).

**Todo lo que sigue está verificado leyendo el código, no supuesto.**

---

## Lo que está bien y no hay que tocar

Vale decirlo primero porque es la mayor parte. La app está escrita para
quien está de pie, con una mano, de madrugada: un paso a la vez, botones
grandes abajo, la hora se sella al marcar y no al enviar, la foto se
reduce en el teléfono antes de subir, y lo que se lee de memoria dice
cuándo se supo. La cola sin conexión distingue un error del servidor
—que se reintenta— de un rechazo —que no—. El candado de la unidad
devuelve a dónde ir, no solo que falta. El acceso del personal está
bien resuelto: tope de cinco intentos en la base, enlaces anteriores
anulados, y la misma respuesta exista o no la cuenta.

La pantalla de **Revisión de unidad** es la mejor de las cinco: dice qué
se espera, por qué, y valida antes de gastar la señal.

---

## 1. La hora la pone el teléfono, y nadie la revisa

**Es el hallazgo grave de esta revisión.**

En `operacion.registrar_hito` la hora de la marca es
`ahora = marcado_en or recibido`: si el teléfono manda `marcado_en`, esa
es la hora buena. No se acota **ni hacia adelante ni hacia atrás**.

Existe por una buena razón —marcar sin señal y mandar después— pero tal
como está:

- **El candado de la ventana de horario se puede saltar.** La ventana se
  evalúa contra la hora que mandó el teléfono, no contra la del
  servidor. Una marca con hora "puntual" pasa el candado aunque llegue a
  cualquier hora.
- **La marca diferida deja de detectarse** si la hora viene en el
  futuro: el atraso sale negativo y no se marca como diferida ni se
  manda a revisión.
- **Se puede fabricar dinero.** En el fin de servicio,
  `jornada.fin_real` se fija con esa hora. De ahí salen las horas extra
  que se le **facturan al cliente** y se **pagan en nómina**.

Todo el sistema descansa en que la marca prueba la hora. Hoy la marca
prueba lo que el teléfono diga.

**Lo que hay que hacer:** rechazar toda hora futura (con un minuto de
margen por los relojes desfasados) y acotar la antigüedad; lo que caiga
fuera, a revisión de la central en vez de aceptarse en silencio.

## 2. Se puede cerrar el día sin haber llegado

En `registrar_hito` solo el contacto con el ejecutivo exige un hito
previo. **El fin de servicio no exige nada.** Una llamada directa al
endpoint con `tipo=fin_servicio` deja la jornada TERMINADA, fija la hora
de cierre y dispara el correo de fin de servicio al cliente, sin pasar
por geocerca ni por ventana.

Hoy lo único que impone el orden es la pantalla, y la pantalla es lo más
fácil de saltarse.

## 3. Sin señal, la app se queda en blanco

`sw.js` guarda el armazón para que la app abra sin línea. La lista
`ARMAZON` no incluye `/consola/idioma.js`, y `app.js` lo importa en su
línea 13. Sin señal, ese módulo no carga y **la app no arranca**: queda
en blanco.

Es justo el caso para el que se escribió el service worker. Falta
también `/app/manifiesto.json`.

## 4. "Un momento…" sin salida, y sin botón rojo

`cargando()` reemplaza **toda** la pantalla, incluida la barra de
navegación y el botón de emergencia. Las peticiones no tienen tiempo
límite. Con media barra de señal, la app se queda en "Un momento…" para
siempre: sin navegación, sin volver, y **sin forma de pedir ayuda**.
Parado en la calle, la única salida es cerrar la app.

## 5. El botón rojo no está donde dice que está

La cabecera de `app.js` declara: *"el botón rojo siempre está, en todas
las pantallas"*. **No es cierto.** `botonPanico()` se pinta solo al
final de la pantalla Hoy. Quien esté en Viáticos, Pagos, Yo o a medio
llenar una revisión tiene que navegar para pedir ayuda.

Lo mismo con la banda de lo que quedó pendiente de enviar: el estilo
dice que "vive arriba de todo y no se quita hasta que sale", y solo se
pinta en Hoy.

## 6. Marcar sin señal no avisa que se guardó, y deja duplicar

Cuando falla la red, la marca se encola —bien— y la pantalla se vuelve a
pintar con los datos **de antes de marcar**: el mismo botón reaparece
habilitado y sin mensaje. El usuario cree que no pasó nada y vuelve a
tocar. La cola no descarta repetidos, así que a la central le llegan
tres llegadas con tres horas distintas.

## 7. La revisión de unidad, sin señal

**Corregido el mismo día, al ir a arreglarlo.** Que las fotos no se
encolen **no es un descuido**: está decidido a propósito y escrito en el
código —*"son medio mega y la cola vive en el teléfono; más honesto es
decir que no salió y que lo intente donde haya señal, con las fotos
todavía en pantalla"*—. Esa decisión se respeta.

Lo que sí faltaba es más chico: `pantallaRevision` pedía sus datos **sin
pasar por la memoria**, así que sin línea ni siquiera se veía qué unidad
se trae ni si ya se revisó; y el error que salía era el del navegador,
en inglés. Las dos cosas quedaron arregladas.

---

## Las notificaciones push

### 8. Hoy no sale ni un aviso

`.env` no tiene `VAPID_PUBLIC` ni `VAPID_PRIVATE`, así que el sistema se
apaga solo —y lo dice, que es lo correcto—. Se generan con
`docker compose exec -T api python generar_llaves_push.py` y se
reinician los tres servicios. **Esto es lo único que depende de ti.**
HTTPS ya está resuelto en el despliegue.

### 9. El recordatorio diario siempre termina en error

`push.recordar_la_vispera` termina con `dia.isoformat()`, y la tarea de
las 17:00 la llama sin fecha: revienta **todos los días**. Los avisos sí
salen (el guardado ocurre antes), pero la tarea queda marcada como
fallida y nadie sabe a cuántos se avisó ni cuántos no tienen teléfono
registrado.

Lleva así desde el primer día porque **no hay ni una prueba de push**.

### 10. Los teléfonos muertos se reintentan para siempre

Cuando un teléfono ya no existe, el servidor apaga esa suscripción. En
el aviso de relevo por contingencia ese apagado **no se guarda**: se
llama después del guardado de la transacción y no hay otro. Se le sigue
mandando a un teléfono desinstalado indefinidamente.

### 11. Lo que debería avisar y no avisa

Hoy solo hay dos avisos: el recordatorio de la víspera y el relevo por
contingencia. Faltan, en orden de lo que más duele:

- **Se canceló el servicio.** El asignado no se entera y se presenta.
- **Cambió la hora de presentación.** Confirmó para las 5:00 y ya no es
  esa.
- **Al que sale en un reemplazo.** Hoy solo se le avisa al que entra: el
  reemplazado llega a un servicio que ya no es suyo.
- **Te asignaron un servicio nuevo.**
- **Cambió el punto de encuentro.**
- **Te depositaron el viático** o **te rechazaron un comprobante**.

### 12. Detalles del push que se notan en la calle

El aviso caduca a la hora: si el teléfono está guardado o sin batería,
el recordatorio se pierde. El aviso urgente del relevo viaja con la
misma prioridad que el recordatorio. Y la notificación no trae botón de
"confirmo que voy": son cuatro toques a las seis de la mañana.

---

## Lo que molesta sin ser grave

**13.** El endpoint de unidades manda **todas las fotos de todas las
unidades del servicio** en cada consulta —recepción y entrega, de todos
los compañeros—. Son megabytes a un teléfono con mala señal, y expone
revisiones que no son suyas.

**14.** "Salir" no pide confirmación. Tocarlo sin querer, sin señal,
deja la app inservible hasta que haya red. Y al salir se borra la
memoria pero **no la cola**: las marcas pendientes del usuario anterior
quedan en el teléfono y se intentan mandar con el token del siguiente.

**15.** Una marca rechazada se avisa con un `alert` y se borra para
siempre. Si salta con el teléfono en el bolsillo, la prueba de su
llegada desapareció y nadie se entera.

**16.** Cuando falla la red y no hay memoria guardada, el error que se
ve es el del navegador, **en inglés**: *"Failed to fetch"*.

**17.** Tres pantallas de cinco no dicen qué se espera del usuario. Solo
Viáticos y Revisión tienen ese renglón (y el de Revisión está al final,
donde ya no sirve).

---

## El orden que propongo

1. **La hora y la secuencia** (1 y 2). Es dinero y es el candado que
   sostiene todo lo demás.
2. **Que la app no se caiga** (3, 4, 5, 6, 7). Es lo que decide si el
   equipo confía en ella.
3. **Encender el push** (8, y de paso 9 y 10, que son dos líneas cada
   uno).
4. **Los avisos que faltan** (11), empezando por la cancelación y el
   cambio de hora.
5. **Lo demás** (13 a 17), incluidos los renglones por pantalla.

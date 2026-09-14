# La app del personal de seguridad

Lo que el backend ya tiene construido y esperando. Este documento existe
para que el dia que se arranque la app no se vuelva a decidir nada de
esto desde cero, y sobre todo para que no se construya de menos: hay
reglas aqui que no son detalles de implementacion sino decisiones de
operacion que ya se tomaron.

Escrito el 14 de septiembre de 2026.

---

## Por que importa

Tres cosas del sistema **hoy no funcionan y no pueden funcionar** sin la
app. No estan rotas: estan esperando.

1. **La confirmacion del equipo.** Nadie puede confirmar que sabe que
   manana trabaja. El campo `asignacion_personal.confirmado` nace en
   falso y solo lo mueve la app.
2. **El estatus en curso.** Una jornada llega a `EN_CURSO` unicamente
   cuando el equipo marca su llegada al punto. Sin app, ninguna jornada
   entra en curso jamas.
3. **La banda "En curso" de la central de inteligencia**, que se llena
   de jornadas en ese estatus. Hoy sale vacia.

Decision tomada (14/sep/2026): se dejan asi hasta que exista la app. No
se agrega un camino para que la consola marque por el equipo, porque la
diferencia entre "Juan confirmo" y "alguien dijo que hablo con Juan" es
justo lo que se quiere poder auditar el dia que alguien no llegue.

---

## Quien es el usuario

Rol `personal_seguridad` (`m.Rol.PERSONAL_SEGURIDAD`). Entra con su
correo y su contrasena, igual que la consola. En produccion nadie recibe
contrasena: se le manda su enlace de invitacion y cada quien crea la
suya.

Un usuario de este rol **solo ve lo suyo**. Esa regla ya esta escrita en
el backend en tres lugares distintos, y hay que respetarla en la app:

- `GET /operacion/jornadas/{id}/bitacora` — solo de sus propias jornadas
- `GET /task-sheets/equipo/{id}` — solo si participa en ese equipo
- `POST /viaticos/{id}/comprobantes` — solo sus propios viaticos

---

## Lo que la app tiene que hacer

### 1. Confirmar que va

`POST /operacion/jornadas/{jornada_id}/confirmar-recurso`

Sin cuerpo. Confirma **el usuario que inicio sesion**; no se puede
confirmar por otro, y eso es a proposito: el codigo lo dice explicito.

Pone `asignacion_personal.confirmado = true`.

Se regresa solo a falso cuando entra un reemplazo por contingencia
(`app/contingencia.py`) o cuando cambia la plantilla de un implantado.
El que llega tiene que confirmar por su cuenta; heredar la confirmacion
del que se fue seria confirmar por alguien que no sabe nada.

**Donde se ve:** en la central de inteligencia, banda de manana, renglon
"Confirmacion del equipo", con una palomita por persona.

### 2. Marcar los hitos del dia

`POST /operacion/jornadas/{jornada_id}/hitos`

Cuerpo: `{tipo, lat, lon, nota?}`. Los seis tipos:

| tipo | que significa |
|---|---|
| `llegada_origen` | esta en el lugar citado, en espera |
| `contacto_ejecutivo` | inicio formal del servicio (el meet and greet) |
| `llegada_destino` | llego a donde iba |
| `salida_ruta` | va en camino |
| `standby` | reporte periodico de que sigue en espera |
| `fin_servicio` | termino |

**Tres candados que la app tiene que entender, no rodear:**

**Candado 1 — geocerca.** `llegada_origen` exige `lat` y `lon` y se
rechaza con 409 si la distancia al punto supera la geocerca de la
jornada (500 m por omision, 2 km en aeropuerto). El intento queda
registrado como alerta `fuera_de_geocerca` aunque se rechace: la app
tiene que mostrar la distancia y el limite que devuelve el error, no un
"no se pudo".

**Candado 2 — ventana de tiempo.** `llegada_origen` y
`contacto_ejecutivo` se pueden marcar desde **60 minutos antes** y hasta
**15 minutos despues** de la hora de presentacion. Fuera de eso se
acepta la marca pero queda con `fuera_de_ventana` y `requiere_revision`,
y se genera alerta para la central. La app debe decirlo en el momento:
"quedo fuera de ventana, la central lo va a revisar".

**Candado 3 — secuencia.** No se puede marcar `contacto_ejecutivo` sin
haber marcado antes `llegada_origen`. Devuelve 409.

**Efectos de cada hito (los dispara el backend, no la app):**

- `llegada_origen` → la jornada pasa a `EN_CURSO`. Se notifica al
  ejecutivo ("su equipo de seguridad esta en el lugar") y al
  solicitante, con la ficha del equipo y la unidad.
- `contacto_ejecutivo` → se guarda `inicio_real`. En **implantado**, el
  servicio pasa a `EN_CURSO` (en eventual no: ahi el estatus lo mueve el
  cierre del dia). Se genera un **enlace de seguimiento en vivo** para el
  solicitante, con token, que expira 4 horas despues del fin programado.
- `fin_servicio` → se guarda `fin_real`, la jornada pasa a `TERMINADA` y
  se avisa al solicitante.

La respuesta del endpoint trae `distancia_origen_m`, `dentro_geocerca`,
`requiere_revision` y una lista de `avisos`. Todo eso es para mostrarselo
a quien marco, no para descartarlo.

### 3. Boton de panico

`POST /contingencia/alertas` con `{canal, descripcion?, lat, lon}`.

Canales: `boton_app`, `boton_vehiculo`, `llamada`. Al que esta del otro
lado le cambia como lo atiende, asi que la app debe mandar el canal
correcto.

El boton de panico casi nunca viene con descripcion: **la ubicacion es lo
unico que hay**, asi que mandarla no es opcional.

Del otro lado, la central toma la alerta (con o sin equipo de respuesta)
y la cierra con una resolucion escrita. Eso ya esta construido y se ve en
la banda roja de la central de inteligencia.

### 4. Su task sheet

`GET /task-sheets/equipo/{equipo_id}` — la hoja vigente de su equipo.
Trae el punto de encuentro, el ejecutivo, la agenda del dia, los tres
hospitales mas cercanos y los telefonos.

Es lo que el equipo lee antes de salir. La app tiene que poder abrirla
sin conexion una vez descargada: en un estacionamiento de aeropuerto a
las seis de la manana no siempre hay senal, y esa hoja trae el telefono
al que se llama si el ejecutivo no baja.

### 5. Comprobar sus viaticos

`POST /viaticos/{viatico_id}/comprobantes` — solo los suyos. Se puede ir
comprobando desde el dia uno del servicio, no al final. El limite es de
24 horas despues del termino (`HORAS_PARA_COMPROBAR`).

---

## Los numeros que ya estan decididos

Viven en `app/operacion.py` y no deben duplicarse en la app: si cambian,
cambian ahi.

| constante | valor | que es |
|---|---|---|
| `MINUTOS_ANTES_PERMITIDOS` | 60 | puede marcar llegada hasta 1 h antes |
| `MINUTOS_DESPUES_PERMITIDOS` | 15 | despues de esto lo revisa la central |
| `INTERVALO_STANDBY_HORAS` | 2 | sin reporte en ese lapso, alerta |
| `AVISO_HORAS_EXTRA_MINUTOS` | 30 | aviso preventivo antes de cumplir |
| `HORAS_VIGENCIA_ENLACE` | 4 | dura el enlace de seguimiento del cliente |
| geocerca por omision | 500 m | 2 km cuando el punto es aeropuerto |

La hora a la que el equipo tiene que estar parado en el punto se calcula
en `app/presentacion.py`: **30 minutos antes** de la presentacion, o **45
minutos antes de la hora del vuelo** cuando el encuentro es contra un
vuelo de llegada. Esa es la hora que la app le debe mostrar al equipo,
no la del servicio.

---

## Lo que el standby implica para la app

`revisar_standby` genera alerta cuando pasan 2 horas sin ningun hito. La
central lo ve en su banda de "En curso" (ambar a los 30 min, rojo a los
60, que son los umbrales de la pantalla, distintos del que genera la
alerta formal).

Eso quiere decir que **la app tiene que empujar al equipo a marcar
standby**. Si el unico hito del dia es la llegada, a las dos horas todos
los servicios estan en alerta y la central deja de creerle a la pantalla.
Un recordatorio local cada hora y media resuelve esto sin tocar backend.

---

## Decisiones pendientes, para no inventarlas el primer dia

1. **Modo sin conexion.** Que pasa si el equipo marca la llegada sin
   senal. Hoy el backend sella la hora con `marcado_en` que manda el
   cliente o con la hora del servidor; hay que decidir si se acepta una
   marca diferida y como se distingue de una marcada a tiempo. Afecta a
   los dos candados de ventana.
2. **El boton de panico del vehiculo** (`boton_vehiculo`) es un canal que
   ya existe en el enum pero no hay hardware definido.
3. **El intervalo de standby** esta en 2 horas para la alerta formal y en
   30/60 minutos para el color de la central. Son dos numeros que dicen
   cosas parecidas y conviene unificarlos, o dejar escrito por que no.
4. **Medir el silencio contra el protocolo de contacto de cada acuerdo**
   en vez de un numero unico. Es lo correcto; se dejo fuera a proposito
   hasta ver la pantalla funcionando.
5. **Notificaciones push.** Hoy `_notificar` registra la notificacion en
   la base; el envio real no esta conectado.

---

## Lo que NO debe hacer la app

- Confirmar por otra persona.
- Marcar hitos de una jornada a la que no esta asignada (el backend lo
  rechaza con 403, pero la app no deberia ni ofrecerlo).
- Editar la hora de un hito ya marcado. Eso lo hace la central, con
  justificacion obligatoria de al menos 10 caracteres
  (`ajustar_hito`), y queda registrado quien lo ajusto.


---

## Lo que se construyó después de escribir este documento

Este archivo se escribió antes de que la app existiera. Lo de abajo es
lo que ya está hecho, y reemplaza lo que arriba se decía "pendiente".

### La app existe: `app/web/campo/`

Web app, sin build, mismos módulos ES y mismo diseño que la consola,
fondo blanco.

| Archivo | Qué hace |
|---|---|
| `index.html` | La cáscara |
| `manifiesto.json` | Para instalarla en la pantalla de inicio |
| `estilo.css` | Paleta de la consola, botones de 52 px abajo |
| `cola.js` | Encolar y vaciar. Un 4xx **no** se reintenta |
| `memoria.js` | `traer` / `recordar` / `hace` — lo último que se supo, con su edad |
| `foto.js` | Reduce a 1600 px / JPEG 0.7 antes de subir |
| `sw.js` | Cachea **solo el armazón, nunca datos**. Push y notificationclick |
| `app.js` | Todas las pantallas |

Pantallas: **Hoy**, **Viáticos**, **Pagos**, **Yo**, y la de **revisión
de unidad**.

### Punto 5 resuelto: las notificaciones push ya salen

Llaves VAPID generadas con `generar_llaves_push.py`, que las escribe en
`.env` y **solo imprime la pública**. La privada nunca sale del
servidor.

- Tabla `suscripcion_push` (migración `b58d30f4a916`).
- `app/push.py`: `hay_llaves`, `suscripciones`, `avisar`, `sin_confirmar`,
  `recordar_la_vispera`.
- Una suscripción que responde **404 o 410 se apaga sola**.
- Un fallo al avisar **nunca tumba a quien lo llamó**. Un aviso que no
  sale no puede tirar un cierre de servicio.
- Endpoints: `GET /campo/push/llave`, `POST /campo/push/suscribir`,
  `DELETE /campo/push/suscribir`, `POST /campo/push/probar`.

El recordatorio de la víspera es el que importa: el seguimiento al meet
and greet y al inicio del día siguiente es el punto más importante de
toda la operación.

### Revisión de unidad con fotos

**Por servicio, y solo cuando la unidad cambia de manos.** Un implantado
con la misma camioneta veintidós días no la revisa veintidós veces: lo
que se revisa es el cambio, no el día.

Tablas `revision_unidad` y `foto_revision` (migración `c61f28a94db7`),
con única `(servicio_id, vehiculo_id, tipo)` — dos revisiones del mismo
tipo para la misma unidad en el mismo servicio no existen.

**Lo que la app exige y por qué:**

- **Los cuatro ángulos**: frente, atrás, izquierdo, derecho. Una
  revisión con dos fotos no sirve para discutir un golpe tres semanas
  después, que es exactamente para lo que existe. Si falta un ángulo,
  más vale decirlo ahora que descubrirlo cuando ya no se puede volver a
  tomar la foto.
- **Kilometraje** y **tanque en octavos** (0 a 8). Pedir litros es pedir
  que alguien invente un número.
- **Nota** de lo que ya viene golpeado, y fotos sueltas de cada golpe.
- **Firma con el dedo**, en un lienzo de 600 × 200: una firma no
  necesita más y así pesa diez kilobytes en vez de trescientos.
- **Hora y ubicación** en cada foto, igual que en los hitos. Una foto
  sin cuándo ni dónde no prueba nada.
- **No se puede entregar lo que nunca se recibió.** Sin estado de
  entrada no hay contra qué comparar.
- Al entregar, la app pone **cada foto junto a la de cuando la
  recibió**. Ahí es donde un golpe nuevo salta solo.
- Al entregar sale sola la **diferencia de kilometraje**: el número que
  nadie apunta y del que después todos se acuerdan distinto.

**Lo que no hace:** las fotos **no se encolan** sin señal. Son medio
mega y la cola vive en el teléfono. Se dice que no salió y se pide
reintentar con señal, con las fotos todavía en pantalla.

**Endpoints:**

- `GET /campo/servicios/{servicio_id}/unidades` — qué trae, si ya la
  recibió, si ya la entregó, y la revisión de entrada para comparar.
- `POST /campo/revisiones` — guardar una revisión.
- `GET /servicios/{servicio_id}/revisiones` — la consola: las dos puntas
  lado a lado, con los kilómetros del servicio.

En la ficha del día (`/campo/mi-dia`) viene `servicio_id` y un bloque
`revision` con `por_recibir` y `por_entregar`, para que la pantalla del
día ponga el paso enfrente mientras falte y deje de ponerlo cuando ya
no. El equipo no tiene que acordarse.

### El teléfono de la central

**+52 55 5022 1022.** Vive en la configuración (`telefono_central`), no
en la ficha de quien esté de turno: el turno cambia cada ocho horas y el
número al que se llama en una emergencia no puede cambiar con él. El
nombre sí sale del usuario en turno, para que el de campo sepa con quién
va a hablar.

### Dos cosas que la app no puede hacer, por el navegador

- **No puede tomar ubicación en segundo plano.** Ninguna web app puede.
  La ubicación se toma en el momento de marcar, no todo el tiempo.
- **La geolocalización exige HTTPS.** `localhost` está exento, así que en
  desarrollo funciona; para probar en un teléfono real hace falta
  certificado.

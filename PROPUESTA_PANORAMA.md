# Panorama — la fotografía de la operación

_Qué debería ver la dirección al abrir la pantalla._
_Antes de programar nada. 17 de septiembre de 2026._

---

## El diagnóstico

Panorama hoy muestra siete bloques, uno debajo del otro: tres tarjetas con
números, la tabla de los que arrancan pronto, la tabla de los que están en
la calle, el dinero, el camino al cobro y lo que espera decisión.

El problema no es que falte información. Es que **hay la misma cantidad de
pantalla un día perfecto que un día en llamas**. Todo pesa igual: la tabla
de los que están en la calle se ve idéntica cuando los doce reportan bien
que cuando uno lleva tres horas callado. Para encontrar lo que importa hay
que leerlo todo, y una pantalla que hay que leer entera no se lee.

Y hay algo más de fondo: **Panorama repite la Central**. Los que arrancan
pronto sin estar listos, los callados, los que van a entrar en horas
extra —eso ya está en la Central de inteligencia, que es la pantalla del
que actúa. Panorama le agrega el dinero y lo pone en otro orden, pero no
contesta una pregunta distinta.

La dirección no necesita la misma lista más larga. Necesita otra pregunta:

> **¿Estamos bien en este momento?**

---

## Un error que encontré de paso

La Central marca a un equipo en rojo a los **60 minutos** de silencio
(`central.py`, `SILENCIO_ROJO = 60`). Panorama lo marca a los **120**
(`panorama.js`, `> 120`).

O sea: un equipo puede llevar hora y media sin reportar, estar en rojo en
la pantalla de la central, y en la pantalla de la dirección verse normal.
El umbral está escrito dos veces, y la versión del director es la más
indulgente. Debería ser al revés, o mejor: debería ser una sola.

---

## La idea

**Una pantalla que se vacía cuando todo está bien.**

Si Panorama está normalmente en un renglón verde y un conteo de gente, el
día que aparezca algo el director lo va a ver sin leer. Si siempre está
llena, deja de mirarla en tres semanas.

Eso obliga a una jerarquía dura: arriba, una sola frase que dice el estado
de la operación. Debajo, la gente. Debajo, el dinero. Y las tablas solo
cuando hay algo en ellas.

---

## La pantalla

### 1. El renglón de estado — una frase, no una rejilla

Un día normal:

```
┌──────────────────────────────────────────────────────────────────┐
│  ● Operación normal                              jue 17 · 14:20  │
│                                                                   │
│  38 personas en la calle · 14 ejecutivos cubiertos · 11 servicios │
│  Todos reportando.                                                │
└──────────────────────────────────────────────────────────────────┘
```

Un día con cosas:

```
┌──────────────────────────────────────────────────────────────────┐
│  ● Dos cosas que atender                         jue 17 · 14:20  │
│                                                                   │
│  38 personas en la calle · 14 ejecutivos cubiertos · 11 servicios │
│                                                                   │
│  ▸ Equipo Alfa · CN-2026-0142 lleva 1 h 40 sin reportar          │
│    Última marca: llegada al destino, 12:40         [ Abrir ]     │
│                                                                   │
│  ▸ CN-2026-0151 arranca en 35 min y no tiene unidad              │
│                                                    [ Abrir ]     │
└──────────────────────────────────────────────────────────────────┘
```

Y con una alerta de pánico, ese renglón es lo único que se ve arriba, en
rojo, con la hora en que se reportó y quién la tomó.

El orden de lo que aparece ahí es por consecuencia, no por módulo:
pánico primero, después silencio, después lo que arranca y no está listo.
Nada más entra a ese recuadro. El dinero no es urgente aunque sea grande.

### 2. La gente, por país — lo que ninguna otra pantalla dice

Centauro opera en varios países y hoy Panorama no lo menciona una sola
vez. Sale gratis: cada plaza tiene su país y cada país su zona horaria.

```
┌─ En la calle ahora ───────────────────────────────────────────────┐
│                                                                    │
│   México      14:20     23 personas    8 servicios    ● todos ok   │
│   Brasil      17:20      9 personas    2 servicios    ● 1 callado  │
│   Colombia    15:20      6 personas    1 servicio     ● todos ok   │
│                                                                    │
│   Ciudad de México 14 · Guadalajara 6 · Monterrey 3                │
└────────────────────────────────────────────────────────────────────┘
```

Dos cosas pasan aquí. La primera es que el director ve el tamaño real de
lo que está corriendo, que es gente, no folios. La segunda es que **cada
país trae su hora**, y eso desarma solo la confusión de "son las 14:20…
¿allá qué hora es?" cuando hay que llamar.

### 3. El pulso del día — una línea del tiempo, no una tabla

En vez de la tabla de "en la calle", una franja de las próximas horas:

```
┌─ Hoy ─────────────────────────────────────────────────────────────┐
│                                                                    │
│   06   08   10   12   14│  16   18   20   22                       │
│   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│▓▓▓▓▓▓                CN-2026-0142  Alfa  │
│        ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│▓▓▓▓▓▓▓▓▓▓▓▓          CN-2026-0148  Alfa  │
│                 ▓▓▓▓▓▓▓▓│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓      CN-2026-0151  Beta  │
│                         │       ░░░░░░░░       CN-2026-0153  Alfa  │
│                         │                                          │
│   ▓ en curso   ░ por arrancar   │ ahora                            │
└────────────────────────────────────────────────────────────────────┘
```

Una barra por equipo, con el ahora marcado. Se ve de un vistazo cuánto
falta para que termine cada uno, quién se va a pasar a horas extra (la
barra que cruza su propio fin) y qué viene en la tarde. Eso es la
fotografía: no una lista de filas, una forma.

La barra se pinta ámbar cuando el equipo lleva callado más de lo debido, y
se le pone una muesca en la última marca. Un servicio que arrancó bien y
lleva dos horas mudo se ve distinto sin leer una palabra.

### 4. El dinero, en una línea cada cosa

El bloque de dinero y el de camino al cobro son seis números en dos
tarjetas. Se pueden decir en cuatro renglones, y solo el que tiene algo
vencido se pinta:

```
┌─ Dinero ──────────────────────────────────────────────────────────┐
│                                                                    │
│   Por depositar          $ 7,460      3 solicitudes                │
│   Afuera sin comprobar   $12,300      2 personas · $1,152 vencido ●│
│   Nómina de la semana    $86,400      corte lun 21 · sin calcular  │
│   Cierres                     7       2 vencidos ●                 │
└────────────────────────────────────────────────────────────────────┘
```

### 5. Lo que hoy nadie le enseña a la dirección

Esto es lo que yo pondría y que no está en ninguna pantalla:

**Marcas que no cuadran.** Cada marca del equipo guarda su latitud,
longitud y si cayó dentro de la geocerca. Cuando alguien marca su llegada
desde tres kilómetros, el sistema lo anota (`dentro_geocerca`,
`requiere_revision`) y hoy eso solo aparece al cerrar el servicio, en la
revisión, servicio por servicio. Nadie lo ve junto.

```
   Marcas fuera de la geocerca hoy          3
   Marcas esperando que la central las valide   5
```

Es la única cifra de la pantalla que no habla de la operación sino de la
**calidad del reporte**. Contesta una pregunta que un director se hace y
casi nunca puede responder: *¿me están reportando de verdad, o me están
reportando de dientes para afuera?*

**Relevos de hoy.** El módulo de contingencia es nuevo y no aparece en
ningún tablero. Que hoy hayan entrado dos personas en lugar de otras dos
es exactamente lo que la dirección quiere saber el día que pasa, no en el
corte de la semana.

**Unidades entregadas sin revisión de entrada.** Si nadie registró cómo se
recibió la unidad, un daño reclamado después no se le puede atribuir a
nadie. Es un riesgo de dinero y hoy solo se ve dentro de cada servicio.

---

## Lo que dejaría fuera, y por qué

**El mapa.** Es lo primero que uno imagina cuando dice "fotografía", y
tengo los datos para dibujarlo: cada marca trae sus coordenadas. Pero:

- No es rastreo. El punto es donde estaba el equipo **cuando marcó**, no
  donde está. Si la última marca fue a las 12:40, el punto tiene hora y
  media de viejo. Un mapa que parece un rastreador y no lo es engaña al
  que lo mira, y en esta empresa engañarse sobre dónde está la gente es
  caro.
- El mapa de fondo se le pide a Google. Una pantalla que se refresca cada
  minuto, con varias ciudades, son miles de llamadas al día por una imagen
  que no cambia.

Si lo quieres, se hace bien: una imagen de fondo por ciudad, pedida una
vez al día y guardada, con nuestros puntos encima dibujados en el
navegador — cero llamadas por refresco. Y cada punto con su hora a un
lado, para que nadie lo lea como una posición en vivo. Pero no lo pondría
en la primera versión: el director no actúa sobre un punto, actúa sobre
"lleva una hora y media callado".

**Las encuestas y las incidencias sin visto bueno.** Son decisiones tuyas,
sí, pero no son "lo que está pasando ahora". Van en su propia bandeja, no
compitiendo con un equipo callado.

---

## Las decisiones que necesito de ti

1. **El umbral de silencio.** ¿60 minutos para todo, como la Central? ¿O
   distinto según el tipo de servicio — un implantado en oficina no
   reporta igual que un traslado en carretera? Hoy son dos números
   distintos escritos en dos lugares y eso hay que cerrarlo.

2. **¿Cuenta la gente o cuenta el servicio?** Yo pondría personas y
   ejecutivos arriba, y servicios de segundo. Es tu negocio, dime si lo
   ves al revés.

3. **El mapa: ahora, después o nunca.**

4. **¿Panorama y Central se separan o se funden?** Mi recomendación es
   separarlas de verdad: Central es la cola de trabajo del que actúa,
   Panorama es el estado para el que decide. Hoy se pisan.

5. **¿Quién la ve?** Dirección nada más, o también los consultores —
   filtrada a su cartera.

---

## Qué habría que construir

**Motor.** Un solo `panorama()` que devuelva el estado ya resuelto: el
renglón de arriba con su lista corta de cosas que atender, el corte por
país con su hora local, las barras del día, el dinero en cuatro cifras y
los tres conteos de calidad. El umbral de silencio sale de `central.py` y
deja de estar escrito en el navegador.

**Consola.** El recuadro de estado, la tabla por país, la franja del día
—que es el único dibujo nuevo, y es CSS, sin librerías— y el dinero en
renglones.

**Idiomas.** Las claves nuevas en es, en y pt.

**Pruebas.** Que un día sin nada devuelva el renglón verde y ninguna
tabla; que un equipo callado 61 minutos aparezca arriba y no enterrado;
que el corte por país sume lo mismo que el total; que la hora de cada país
sea la suya y no la del servidor; y que una marca fuera de geocerca se
cuente una sola vez.

---

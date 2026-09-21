# El candado del meet and greet

20 de septiembre. Propuesta antes de escribir código.

## El problema

El conductor se queda dormido. No marca nada: el sistema no recibe una
señal equivocada, **no recibe ninguna**, y el silencio hoy no dispara
nada. La central se entera cuando llama el cliente.

Y el dato que lo vuelve grave lo puso Salvador: **reponer a alguien toma
hasta hora y media**. Cuando el sistema podría notarlo —a la hora de
estar en el punto, sin marca de llegada— ya no hay forma de que nadie
llegue.

## La aritmética manda

Si reponer toma 90 minutos, la central necesita enterarse **al menos 90
minutos antes** de la hora de presentación. Eso obliga a una cuenta
incómoda:

| Primer toque | Silencio detectado | Reemplazo llegaría |
|---|---|---|
| 90 min antes | 75 min antes | **15 min tarde** |
| 120 min antes | 105 min antes | 15 min de sobra |

Por eso **el primer toque va a dos horas** de la hora en que el equipo
debe estar en el punto —no de la hora del servicio—. Con hora y media no
alcanza: la propia operación lo dice.

## Cómo funciona

**Tres toques, y ninguno pide más que un dedo.**

| Cuándo | Qué pasa |
|---|---|
| **2 h antes** | Aviso al teléfono: *"¿Vas en camino?"*, con el botón en la propia notificación. Al tocarlo se guarda su posición y la distancia en línea recta al punto. |
| **1 h 20 antes** | Segundo toque. Se compara: ¿se acercó? |
| **45 min antes** | Tercer toque. Última lectura antes de que ya no haya tiempo de reponer. |

Si la app está abierta —el teléfono en el soporte del coche— reporta
sola y no hace falta tocar nada. El toque es el respaldo para cuando el
teléfono está en el bolsillo, que es el caso normal.

## Qué se revisa, y qué no

Lo único que el sistema quiere saber es **si va a haber alguien en el
punto**. La puntualidad es responsabilidad del personal de seguridad
—decisión de Salvador— y no se vigila.

Con dos posiciones y el reloj sale todo, sin preguntarle a nadie:

- **Se está acercando.** La distancia en línea recta bajó. Va en
  movimiento hacia el punto.
- **¿Le alcanza el tiempo?** Con lo que falta de distancia y lo que
  falta de reloj sale la velocidad que necesita; con las dos lecturas,
  la que lleva. Si lleva **claramente menos** de la que necesita, no va
  a llegar. Con margen holgado: la línea recta siempre miente a favor,
  porque las calles dan vuelta y el avance real es mayor que el
  aparente.
- **Ya está cerca.** Por debajo de un kilómetro se apaga el seguimiento
  y no se le pregunta más: llegó y está esperando, que es lo que debía
  hacer.
- **Está parado.** Veinte minutos sin avanzar en Reforma no es dormirse.
  Una lectura sin avance no levanta nada; **dos seguidas, sí**.
- **No contesta.** Pesa exactamente igual que no ir.

**Nada de Google.** Ni rutas ni tráfico ni una llamada más a su API.
Todo es aritmética sobre dos puntos y un reloj.

## Lo que ve la central

Tres niveles, y solo se habla cuando hay algo que decir. Si todo va
bien, **ninguna noticia** —regla de Salvador—.

1. **No contestó el primer toque** (1 h 45 antes): aviso normal. Todavía
   hay tiempo de sobra; casi siempre basta una llamada.
2. **No se acerca, o no le alcanza el tiempo** (desde 1 h 20 antes):
   **alerta grave**. Aquí es donde la central decide: manda a alguien
   más, o manda al equipo de respuesta a emergencias a cubrir el
   servicio. Es el momento en que todavía se puede.
3. **Pasó la hora de estar en el punto sin marcar llegada**: alerta
   grave otra vez, aunque haya dicho que iba en camino. Dijo que salía y
   no llegó.

Cada alerta trae el nombre del conductor y **su teléfono a un toque**,
porque lo primero que va a hacer quien la lea es llamarlo.

## Lo que el conductor ve

Un aviso con un botón: *"Voy en camino"*. Un dedo, y sigue manejando.

Cuando lo toca, la app le dice **con todas sus letras** que a partir de
ahí y hasta que marque su llegada se va a tomar su ubicación tres veces.
No por trámite: el día que alguien sienta que lo vigilan de más, deja el
teléfono en la guantera y perdemos justo la señal que queríamos.

El seguimiento **se apaga solo** al marcar la llegada, o al acercarse al
punto. Fuera de esa ventana no se toma nada.

## Lo que hay que construir

1. Una tabla para el trayecto: por jornada y persona, las lecturas
   —cuándo, dónde, a qué distancia— y en qué estado va.
2. El aviso con su acción, como el de *"Confirmo que voy"* que ya
   existe.
3. La tarea del reloj, cada cinco minutos: manda los toques que tocan,
   evalúa lo que llegó y levanta lo que haya que levantar.
4. El endpoint donde la app deja su posición.
5. La caja en la central: quién va en camino y quién no contesta.
6. Textos en tres idiomas y sus pruebas.

## Lo que ya existía y nadie disparaba

Al revisar esto salió otra cosa: el sistema **ya tiene** escrita la
vigilancia del servicio que deja de reportar y el aviso preventivo de
horas extra. Las dos están hechas y probadas, y son botones que nadie
pica: el reloj automático solo corre tres tareas —abrir el mes del
implantado, el recordatorio de las cinco y el despacho del correo—.

Entran al reloj en la misma entrega. No cuesta nada y hoy no sirven de
nada.

## Lo que NO hace

- No calcula hora de llegada con tráfico.
- No vigila la puntualidad.
- No rastrea fuera de la ventana del trayecto.
- No manda una sola notificación de "vas bien".

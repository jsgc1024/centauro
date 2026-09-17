# El relevo del implantado — propuesta

_Que quien trabajó medio día cobre medio día, también aquí._
_Antes de programar nada. 17 de septiembre de 2026._

---

## Lo que pasa hoy

El implantado tiene **dos puertas** para cambiar a una persona, y las dos
hacen lo mismo por dentro:

```python
a.reemplaza_a_id = a.persona_id
a.persona_id = entra_id          # ← la asignación cambia de dueño
```

La asignación no se parte: **cambia de nombre**. Quien salió desaparece
de ese día como si nunca hubiera estado, y la nómina paga por asignación.

Trabajó cinco horas, se enfermó, lo relevaron. Cobra cero.

Es exactamente el error que ya corregimos en eventual. Aquí pesa más,
porque el implantado es operación diaria con plantilla fija: el relevo no
es la excepción, es el martes.

---

## Dos cosas más que encontré

### `reemplazar()` no deja decir a quién se reemplaza

```python
asignacion = jornada.personal[0]
```

Toma **el primero de la lista**. Si la plantilla del mes trae tres
personas —que es lo normal, un coordinador y dos agentes— siempre cambia
al primero, sea quien sea. No hay forma de decir "el que falta es Luis".

La otra puerta, `cambiar_recurso()`, sí acepta `sale_id`. Las dos
existen, una está bien y la otra no, y desde la pantalla no se ve cuál
te tocó.

### Un cambio sin fecha de fin llega hasta el infinito

```python
dias = [j for j in equipo.jornadas
        if j.fecha >= desde and (hasta is None or j.fecha <= hasta)]
```

`hasta = None` significa "de este día en adelante, sin límite". Y el
implantado **reutiliza el mismo equipo mes tras mes**: las jornadas del
mes que viene, si ya está abierto, cuelgan de ese mismo equipo.

Entonces "Luis cubre a Marta desde el jueves" no termina el 30. Se lleva
también los días de octubre que ya existen, sin que nadie lo pida y sin
que aparezca en ninguna pantalla.

---

## Lo que ya está hecho y no hay que inventar

Esto es lo bueno: **el destino ya existe**. No hay que diseñar nada
nuevo, hay que llegar a donde ya llegamos en eventual.

- `AsignacionPersonal.relevado_en` y `relevado_por_id` ya están en la
  tabla, con su migración aplicada.
- **La nómina ya sabe leerlos.** En `nomina.py` la asignación relevada
  cobra sus horas y pierde las extra, y el recibo dice "relevado 11:00".
  Ese código ya corre en producción para los eventuales.
- `contingencia.se_presento()` ya resuelve la pregunta que decide todo:
  ¿esta persona marcó su llegada ese día?
- La regla de negocio ya la definiste: **quien no marca su llegada no se
  paga**, y **el que entra va con el mismo rol**.
- El dinero ya se trata bien: `cambiar_recurso` no arrastra los viáticos
  con la persona, los enlista para que el consultor decida. Es la misma
  regla que acordamos —el sistema propone, el consultor decide— así que
  esa parte no se toca.

---

## Lo que propongo

### 1. Una sola puerta

`cambiar_recurso()` es la buena: acepta quién sale, un tramo de días y
también unidades. `reemplazar()` pasa a ser un caso suyo —un día suelto
es un tramo de un día— y deja de existir como camino aparte.

Así el consultor no aprende dos formas de hacer lo mismo según si el que
falta avisó con un mes o con una hora. Y de paso se va el error del
`personal[0]`.

### 2. Relevar en vez de mutar

Por cada día del tramo, la misma pregunta que en eventual:

```
¿marcó su llegada ese día?

  sí  →  se parte el día
         · la asignación vieja se cierra con relevado_en y relevado_por_id
         · nace una nueva para quien entra, con el mismo rol
         · los dos cobran su parte; las horas extra son de quien se quedó
         · al cliente se le cobra un solo conductor

  no  →  se cambia limpio
         · no trabajó, no hay nada que partir ni que pagarle
```

### 3. El tope duro

Un cambio sin fecha de fin llega **hasta el último día del mes en curso**
y ahí se detiene. Si hay que extenderlo a octubre, se vuelve a hacer
cuando octubre exista, y queda como otro movimiento en el historial.

Un relevo por enfermedad que se come dos meses sin que nadie lo vuelva a
mirar es peor que pedir el trámite dos veces.

---

## Lo que se vería en pantalla

Poco, y eso es a propósito: la pantalla del implantado ya tiene su
bloque de cambios. Lo que cambia es lo que dice.

```
┌─ Cambios del mes ──────────────────────────────────────────┐
│                                                             │
│  Jue 18 — Vie 26 sep · 7 días                              │
│  Entra Luis Mendoza en lugar de Marta Solís                │
│  Enfermedad · "se retiró a media jornada"                  │
│                                                             │
│  ▸ Jue 18: día partido — Marta cobra hasta las 11:00       │
│    Los otros 6 días: Luis completo                         │
│                                                             │
│  Hasta el 30 de sep. Para octubre hay que volver a pedirlo.│
└─────────────────────────────────────────────────────────────┘
```

El renglón del día partido es el que importa: es la prueba de que quien
trabajó medio día va a cobrar medio día, y el consultor lo ve sin abrir
la nómina.

---

## Las dudas que necesito que resuelvas

1. **El tope.** ¿El mes en curso, como propongo? ¿O hasta el último día
   que ya esté abierto, aunque sea del mes siguiente?

2. **Las dos puertas.** ¿Las unifico —una sola forma, un solo camino— o
   prefieres conservar el cambio de un día suelto como algo aparte
   porque así lo pide la operación?

3. **El bono de asistencia.** Alguien que se enfermó a media jornada y
   fue relevado: ¿ese día le cuenta para su puntualidad del mes, no le
   cuenta, o cuenta como trabajado? Hoy la puntualidad se mide contra la
   hora de inicio de la jornada, no de la persona, así que el relevo no
   la toca — pero el que entró a media mañana tampoco tiene hora de
   presentación propia contra qué medirse.

4. **El que entra a media jornada, ¿tiene que marcar llegada?** Si sí,
   ¿contra qué geocerca y qué hora, si el punto de origen del día ya
   pasó? Hoy la marca de llegada se valida contra la hora de presentación
   del día, y quien entra a las 11:00 cae fuera de esa ventana.

---

## Qué habría que construir

**Motor.** Que `cambiar_recurso` releve en vez de mutar, reusando
`se_presento` de contingencia. El tope del mes. `reemplazar()` delegando
o desapareciendo.

**Pantalla.** El bloque de cambios diciendo cuáles días se partieron y
hasta cuándo llega el cambio.

**Pruebas.** Que quien trabajó medio día cobre medio día; que quien no
se presentó no deje rastro; que un cambio sin fin se detenga el último
día del mes y no toque el siguiente; que al cliente se le cobre un solo
conductor el día partido; que las horas extra sean de quien se quedó; y
que el implantado y el eventual den el mismo resultado ante el mismo
caso, que es la única forma de saber que hay una sola regla.

---

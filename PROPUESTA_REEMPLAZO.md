# Reemplazo por contingencia — propuesta

_Cómo lo gestiona el consultor y dónde se ve. Antes de programar nada._
_16 de septiembre de 2026._

---

## Lo que pasa hoy

Los endpoints existen (`/contingencia/reemplazos/personal`) pero **no hay
una sola pantalla que los use**. El consultor no puede hacer un reemplazo
desde la consola. Se hace por teléfono y se queda sin registrar.

Y cuando se hace, el motor tiene un agujero de dinero. En
`contingencia.py:70`:

```python
asignacion.persona_id = entra_persona_id
```

La asignación **cambia de dueño**. Juan se presentó a las 07:00, trabajó
hasta las 11:00 y salió; a las 11:05 el consultor formaliza el cambio y
esa fila deja de ser de Juan. La nómina paga por asignación, así que
**Juan cobra cero por las cuatro horas que sí trabajó** — y nada en el
sistema recuerda que estuvo ahí.

---

## La decisión de fondo

**El día del cambio no se muta: se parte en dos.**

- La asignación de Juan **se queda**, marcada como *relevada* a las 11:00.
  Sigue siendo una asignación válida, así que la nómina le paga.
- Se **crea** una asignación nueva para Luis en ese mismo día.
- Los días siguientes sí cambian de dueño como hoy: nadie los trabajó
  todavía, y el registro de quién iba queda en `ReemplazoRecurso`.

Ese día el equipo tiene dos conductores en la base. Eso es correcto y hay
que saber leerlo:

| | |
|---|---|
| **Al cliente** se le cobra **uno** | La asignación relevada no entra al cierre ni a la cotización |
| **A la empresa** le cuestan **dos** | Las dos entran a nómina, cada quien su día completo |

La diferencia es el costo de la contingencia. Es un número que la
dirección va a pedir, y hoy no existe porque el dato se borra.

**El pago: día completo a los dos.** El que se presentó perdió su día y no
fue su culpa; el que entró tampoco va a cobrar menos por llegar tarde a
algo que no eligió. El consultor **no captura ningún monto** — que es lo
que hace esto gestionable.

---

## Cómo se ve en las pantallas

### Dónde arranca: junto a la persona que va a salir

En la pantalla del servicio, en el bloque **Equipo de seguridad**, cada
persona ya tiene su ficha con un botón `Quitar`. Se le agrega uno:

```
┌─ Equipo de seguridad ─────────────────────────────┐
│                                                   │
│  Conductor de seguridad                           │
│  Juan Ramírez                                     │
│  +52 55 1234 5678                                 │
│  Ciudad de México                                 │
│                              [ Cambiar ] [ Quitar ]│
│                                                   │
│  Agente de seguridad                              │
│  Marta Solís                                      │
│  …                                                │
└───────────────────────────────────────────────────┘
```

Es el lugar natural: el consultor está viendo a Juan y quiere cambiarlo.
No hay que enseñarle a nadie dónde está.

`Cambiar` abre la ventana **debajo, en la misma tarjeta** — exactamente el
patrón que ya usa `Asignar recursos`. Nada de modales ni de pantallas
nuevas.

### La ventana de cambio: cuatro preguntas y una vista previa

```
┌─ Cambiar a Juan Ramírez ──────────────────────────────────────┐
│                                                               │
│  Desde qué día                                                │
│  ( • ) Hoy, mar 16 sep        ( ) mié 17    ( ) jue 18        │
│        El cambio aplica de ese día en adelante.               │
│        Los días ya terminados no se tocan.                    │
│                                                               │
│  Hasta cuándo                                                 │
│  ( • ) De aquí en adelante                                    │
│  (   ) Hasta el día [ ▾ ]                                     │
│        Una contingencia no tiene fin: nadie sabe cuándo       │
│        vuelve. Unas vacaciones sí.                            │
│                                                               │
│  Por qué                                                      │
│  [ Contingencia ▾ ]  Vacaciones · Enfermedad · Descanso ·     │
│                      Contingencia · Baja · Otro               │
│  [ Se sintió mal y la central lo relevó a las 11:00______ ]   │
│                                                               │
│  Quién entra          Conductor de seguridad                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Luis Ortega      CDMX    Libre los 4 días   [Elegir]   │  │
│  │  Ana Peralta      CDMX    Libre 3 de 4 días  [Elegir]   │  │
│  │  Diego Ruiz       GDL     Ocupado el 18      [Elegir]   │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

La tabla de quién entra es **la misma que ya usa `Asignar recursos`** —
con su disponibilidad, sus choques y su orden. Filtrada al rol que traía
el que sale, porque un conductor se reemplaza con un conductor.

El motivo es una lista y no texto libre **a propósito**: de ahí salen las
dos cuentas que la dirección va a pedir —cuánto ausentismo hay y cuánto
tiempo pasan las unidades en el taller— y escrito a mano no se puede
contar. La nota sí es libre, y va aparte.

### Antes de guardar: decir en voz alta lo que va a pasar

Al elegir a quién entra, en vez de guardar, aparece esto:

```
┌───────────────────────────────────────────────────────────────┐
│  Del 16 al 19 de septiembre · 4 días                          │
│                                                               │
│  Sale    Juan Ramírez      Entra   Luis Ortega                │
│  Rol     Conductor de seguridad — el mismo                    │
│                                                               │
│  Nómina                                                       │
│    Juan cobra el 16 completo — se presentó                    │
│    Luis cobra del 16 al 19                                    │
│                                                               │
│  Viáticos                                                     │
│    Juan comprueba $1,400 que ya recibió · vence mañana 18:00  │
│    Se cancelan $2,800 que no habían salido                    │
│    Luis recibe $4,200 nuevos                                  │
│                                                               │
│  ⚠  El 18 Luis ya está en este equipo. Ese día no se cambia.  │
│                                                               │
│                         [ Cancelar ]  [ Confirmar el cambio ] │
└───────────────────────────────────────────────────────────────┘
```

Esto es lo que hace el cambio seguro. Lo delicado de un reemplazo no es
el nombre de quien va: **son los viáticos**. La persona que sale se queda
con dinero que ya recibió y tiene que comprobarlo; la que entra necesita
dinero nuevo. Todo eso ya lo calcula `_mover_viaticos` — hoy lo hace en
silencio y el consultor se entera después. Que lo diga antes no cuesta
nada y evita el "no sabía".

El aviso de choque en amarillo tampoco es un error: es información. El
cambio se hace igual, en los días que se puede.

---

## Dónde se ve después

### 1. En la ficha del equipo

El bloque de recursos hoy dice *"Los recursos son los mismos los N días
del equipo"*. Con un reemplazo eso deja de ser cierto, y la pantalla tiene
que decirlo. Ya existe el patrón: la ficha pinta **"Solo 3 de 4 días"** en
ámbar cuando alguien no va todos. Solo hay que hacerlo hablar:

```
┌─ Equipo de seguridad ─────────────────────────────┐
│  Conductor de seguridad                           │
│  Juan Ramírez                                     │
│  Días 1 · relevado el 16 sep                      │   ← ámbar
│                                                   │
│  Conductor de seguridad                           │
│  Luis Ortega                                      │
│  Días 1–4 · reemplaza a Juan Ramírez              │   ← ámbar
└───────────────────────────────────────────────────┘
```

### 2. En la tabla de días

Una etiqueta en la columna de estatus, en los días afectados. Y al abrir
el día, una línea arriba de todo:

```
 Día 1 · inicio   16/09/2026   Full day   07:00   [terminada] [cambio]
 Día 2            17/09/2026   Full day   07:00   [programada][cambio]
```

### 3. En la central, donde nació

La alerta de pánico que provocó el cambio queda ligada (`alerta_id`, que
ya existe en el modelo). Su ficha muestra una línea más:

```
  Cambio formalizado · Luis Ortega entra por Juan Ramírez · 16 sep 11:05
```

Así la central ve que el consultor ya hizo lo suyo, sin llamarle.

Y al revés: **una alerta que la central cerró y que dejó un servicio sin
cambio formalizado sale en los pendientes del consultor.** Eso es lo que
evita que se olvide, que es como hoy se pierde el registro.

> La central no hace el reemplazo. La central estabiliza el servicio y
> puede mandar su equipo de respuesta; el consultor formaliza el cambio.
> Ese reparto ya está escrito en `contingencia.py` y la propuesta no lo
> toca.

### 4. En la app de campo

Al que entra le aparece el día en *Mi día* y tiene que confirmarlo —el
código ya pone `confirmado = False`— y le llega el aviso al teléfono.

Al que sale el día le desaparece, pero **le queda la comprobación de
viáticos con su fecha límite**, que es justo lo que no se puede perder.

### 5. En nómina

Los dos aparecen, cada uno con su renglón y su día completo. Hoy solo
aparece uno. No hay que cambiar el cálculo: basta con dejar de borrar la
asignación.

### 6. Un bloque nuevo al final del servicio: *Cambios de recurso*

Igual que *Revisión de la unidad*. El endpoint de historial ya existe
(`GET /contingencia/reemplazos/servicio/{id}`) y nadie lo pinta:

```
┌─ Cambios de recurso ──────────────────────────────────────────┐
│  16 sep · Contingencia                                        │
│  Juan Ramírez  →  Luis Ortega       4 días   Costo extra $1,200│
│  "Se sintió mal y la central lo relevó a las 11:00"           │
│  Formalizó: Ana Ruiz · 16 sep 11:05                           │
└───────────────────────────────────────────────────────────────┘
```

El *costo extra* es el día que se pagó dos veces. Es el precio de la
contingencia, y sumado por mes y por motivo es el reporte que va a pedir
la dirección.

---

## Lo que NO cambia

- La central sigue sin poder reemplazar. Estabiliza; no formaliza.
- Los días ya terminados no se tocan nunca.
- El cliente no paga de más: la asignación relevada no entra al cierre.
- Los viáticos se mueven exactamente como ya lo hacen. Solo se avisa
  antes.
- Ningún monto se captura a mano.

---

## Qué hay que construir

**Base de datos.** Una migración con dos columnas en
`asignacion_personal`: `relevado_en` (cuándo salió) y `relevado_por_id`
(quién lo relevó). Nada más. `motivo_tipo` y `hasta_jornada_id` ya existen
en `ReemplazoRecurso` y hoy nadie los llena — esta pantalla los estrena.

**Motor.** `contingencia.reemplazar_personal` parte el día del cambio en
vez de mutarlo. Cierre y cotización ignoran las asignaciones relevadas.
Nómina no se toca.

**API.** Un endpoint de vista previa que devuelva lo del recuadro sin
guardar nada, y los días de cada persona en el bloque de recursos.

**Consola.** El botón `Cambiar` en la ficha, la ventana, la vista previa,
las etiquetas en la ficha y en la tabla de días, el bloque *Cambios de
recurso*, y la línea en la ficha de pánico de la central.

**Idiomas.** Las claves nuevas en es, en y pt — las tres o `revisar.py`
reclama.

**Pruebas.** La que faltaba: alguien sale a media jornada y **los dos**
salen en la nómina. Más el cliente que no paga doble, el choque que no
tumba el cambio, y los viáticos.

---

## Las dos reglas decididas

**Cobra el día quien alcanzó a marcar su llegada.** Quien no se presentó
no cobra, aunque lo hayan relevado. El sistema lo verifica solo —el hito
de llegada ya existe— y nadie captura nada.

**El rol se hereda y no se cambia aquí.** Un conductor se reemplaza con
un conductor. Si de verdad hay que cambiar el rol, es otra operación: el
precio al cliente cambia y la cotización deja de cuadrar, y eso merece su
propio aviso.

---

## Cinco cosas que salieron al revisar el código

**1. El reemplazo de vehículo no mueve a quien va a bordo.**
`reemplazar_vehiculo` cambia `AsignacionVehiculo` pero no toca
`AsignacionPersonal.vehiculo_id`. Después del cambio, "quién va en qué
unidad" sigue apuntando a la camioneta que ya no está en el servicio, y
así lo ve la central. Es una línea, y entra.

**2. Cambiar unidad es cambiar de manos, y nadie dispara la revisión.**
`RevisionUnidad` va por `(servicio, vehículo, tipo)` y existe justo para
el momento en que la unidad cambia de manos. Un reemplazo de vehículo es
exactamente eso, y hoy no pide ni la devolución de la que sale ni la
entrega de la que entra. Un golpe en esa camioneta queda sin dueño, que
es el problema que la revisión vino a resolver. Entra.

**3. Al que entra hoy no le avisa nadie.** `recordar_la_vispera` solo
mira *mañana*. Un reemplazo hecho hoy para hoy nunca dispara el aviso al
teléfono: la central lo ve en pantalla como "sin confirmar", pero al que
entra le hablan por teléfono o no se entera. **El caso urgente es
justamente el que no avisa.** El aviso tiene que salir en el momento del
cambio, no esperar al beat de las 17:00. Entra.

**4. No hay forma de deshacer un reemplazo.** Si el consultor se
equivoca de persona, revertirlo a mano es un desastre: ya se cancelaron
viáticos, se crearon otros y arrancó un plazo de comprobación de 24
horas. Entra una ventana de arrepentimiento corta —el mismo día, y solo
si nadie tocó el dinero— que borra el reemplazo limpio. Pasado eso, solo
queda un reemplazo en sentido contrario, con su rastro.

**5. El bono de asistencia.** Alguien relevado por enfermedad, ¿pierde su
bono? Es política de la empresa, no código. Mientras no se decida,
`bonos.py` lo trata como cualquier día no trabajado.

---

## Lo que queda FUERA, y por qué hay que escribirlo

**El implantado tiene su propio reemplazo, y tiene el mismo bug.** No es
el mismo código: es otro módulo (`implantado.py`), otra tabla
(`Reemplazo`, no `ReemplazoRecurso`) y otro endpoint. Y hace lo mismo que
el de eventual:

```python
asignacion.persona_id = entra_id     # implantado.py:575 y :805
```

Quien sale a media jornada de un implantado cobra cero por las horas que
trabajó, igual que en eventual. Y ahí pasa más seguido: el implantado es
operación diaria con plantilla fija —la gente se enferma, descansa, rota.

**Esta propuesta no lo toca.** Queda como pendiente, con dos cosas ya
diagnosticadas para no volver a investigarlo:

- El arreglo es el mismo de fondo: relevar la asignación en vez de
  mutarla. Cada uno conserva su pantalla y su tabla; lo que debería
  compartirse es el motor, para que no haya dos verdades sobre cómo se
  paga un día partido.
- **Cuidado con el alcance.** El implantado reutiliza **el mismo equipo
  mes tras mes** (`servicio.equipos[0]`), y `jornadas_afectadas` no tiene
  tope: barre todas las jornadas pendientes del equipo. Un cambio el día
  28, con el mes siguiente ya abierto, movería unas 33 jornadas y crearía
  **33 viáticos nuevos de un solo clic**. Cuando le toque, necesita un
  tope duro —el mes en curso— y un aviso en la vista previa.

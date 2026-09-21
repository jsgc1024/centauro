# El desempeño del personal de seguridad — propuesta

_Qué se mide, con qué peso, cómo se ve, y las cuatro piezas que faltan._
_Antes de programar nada. 20 de septiembre de 2026._

---

## Dos medidas que suenan igual y no lo son

El sistema ya tiene dos cosas distintas y conviene no revolverlas:

| | **La calificación** | **El bono** |
|---|---|---|
| Dónde vive | `profesionalismo.py` | `bonos.py` |
| Para qué sirve | decidir **a quién mando** al siguiente servicio | decidir **cuánto se le paga** este mes |
| Hacia dónde mira | adelante | atrás |
| Quién la usa | el consultor al armar el equipo | RRHH al cerrar el mes |
| Se recalcula | cada vez que se consulta | una vez al mes, y se congela |

La calificación puede moverse todos los días. El bono **no**: una vez
autorizado es dinero, y el dinero no se recalcula. Por eso el mes se
cierra, se firma y queda.

Lo que sigue es sobre **el bono**. La calificación se alimenta de las
mismas señales, pero esa ya funciona.

---

## Lo que hoy se mide

Cuatro criterios, configurables por país:

| Criterio | Umbral | Monto de ejemplo | De dónde sale el dato |
|---|---|---|---|
| Puntualidad | 100% | $800 | `jornada.inicio_real` vs `inicio_programado` |
| Seguimiento en la app | 90% | $600 | hitos de la jornada + alertas de silencio |
| Capacitación del mes | 100% | $500 | Odoo (marca manual hoy) |
| Cierre de viáticos | 100% | $700 | `AsignacionViatico` cerrada, cuadrada y en plazo |

Una estrella por criterio cumplido. Una incidencia leve o grave
autorizada **apaga el mes completo**; el error menor no toca nada.

Es una buena base. Le faltan dos cosas que sí importan en este negocio
y sobra un detalle de reparto que hay que corregir.

---

## Hallazgo: los pesos configurados no se usan

En `evaluar()`:

```python
bono_posible = sum(Decimal(c.monto_mensual) for c in criterios)   # 2,600
aplicables   = [c for c in criterios if aplica(c)]
valor_estrella = bono_posible / len(aplicables)                   # 650 cada uno
```

La intención del reparto es correcta —si a alguien no le tocaron
viáticos, ese monto no se pierde, se reparte— pero el reparto **aplana
siempre**. Aunque los cuatro criterios apliquen, puntualidad deja de
valer $800 y capacitación deja de valer $500: los dos pagan $650.

O sea: **el catálogo permite configurar pesos y el motor los ignora.**
Hoy no se nota porque nadie ha abierto la pantalla —no existe—, pero el
día que alguien suba puntualidad a $1,200 no va a pasar nada.

El arreglo es una línea distinta: repartir **en proporción**, no en
partes iguales.

```python
suma_aplicables = sum(Decimal(c.monto_mensual) for c in aplicables)
factor = bono_posible / suma_aplicables if suma_aplicables else 0
monto_del_criterio = Decimal(c.monto_mensual) * factor
```

Con los cuatro criterios aplicando, el factor es 1 y cada quien vale lo
que dice el catálogo. Si viáticos no aplica, los $700 se reparten entre
los otros tres **a prorrata de su peso**, no en tercios.

---

## Los criterios propuestos, con pesos

En el orden en que le importan al cliente, no en el orden en que son
fáciles de medir. Los montos son sobre un bono posible de **$2,600
MXN** para no mover el total mientras usted fija los reales.

| # | Criterio | Peso | Monto | Umbral |
|---|---|---|---|---|
| 1 | **Llegar al punto** | 30% | $780 | 100% |
| 2 | **No dejar callada a la central** | 25% | $650 | 90% |
| 3 | **Entregar la unidad como la recibió** | 15% | $390 | 100% |
| 4 | **Comprobar el dinero a tiempo** | 15% | $390 | 100% |
| 5 | **Capacitación del mes** | 10% | $260 | 100% |
| 6 | **Que el cliente lo vuelva a pedir** | 5% | $130 | 1 o más |

Los primeros dos pesan más de la mitad juntos, y es correcto: en
protección ejecutiva, quien llega tarde o se calla es el riesgo. Los
últimos dos pesan poco a propósito, por razones que explico abajo.

---

## Cómo se mide cada uno

### 1. Llegar al punto — 30%

Hoy solo se mide `inicio_real <= inicio_programado`. Eso es la mitad del
asunto. La llegada completa son **tres señales que el sistema ya tiene**:

- **Confirmó de víspera.** El día anterior se le pregunta si va. Si no
  contestó y llegó, llegó; pero la central pasó la noche sin saber.
- **Avisó que iba en camino.** El trayecto abierto con tiempo suficiente
  contra la hora de presentación.
- **Marcó dentro de la geocerca.** No "marqué a tiempo desde mi casa":
  la marca fuera del punto no cuenta como llegada.

Propuesta: la jornada cuenta como **buena llegada** si marcó
`LLEGADA_ORIGEN` a tiempo **y dentro de la geocerca**. La confirmación de
víspera y el *voy en camino* no descalifican por sí solos —dejan su
renglón en la ficha, para que se vea— salvo que falten los dos.

Umbral 100%, con una salvedad: **un retraso menor a 5 minutos en una sola
jornada del mes no rompe el criterio.** Hoy el 100% exacto castiga igual
al que llegó dos minutos tarde una vez y al que llegó cuarenta tarde
tres veces. Eso no distingue, y lo que no distingue no motiva.

### 2. No dejar callada a la central — 25%

Ya está medido y está bien medido: la secuencia completa de hitos
(`LLEGADA_ORIGEN`, `CONTACTO_EJECUTIVO`, `FIN_SERVICIO`) y **cero
alertas de silencio**.

Un solo cambio: que la alerta de silencio pese distinto que un hito
faltante. Hoy las dos tiran la jornada completa. Un hito que se le pasó
marcar y que él mismo corrigió media hora después no es lo mismo que
tres horas sin señal y la central llamándole.

### 3. Entregar la unidad como la recibió — 15%

Esto **no se mide hoy** y es de las cosas que más cuestan.

La revisión de entrega y la de recepción ya existen. La medida es
simple: **daño encontrado en la entrega que no venía declarado en la
recepción**, y que la revisión posterior confirmó como suyo.

Aquí está el incentivo perverso más claro de todo el esquema: si
declarar un daño le cuesta el bono, **deja de declarar daños**. Y un
daño no declarado lo paga el siguiente, o lo paga la empresa con el
cliente adentro de la unidad.

Por eso la regla se invierte: **el daño que él mismo declara al recibir
o al entregar no toca el bono.** Lo que lo toca es el daño que aparece
sin declarar. Lo mismo para el kilometraje y el combustible.

### 4. Comprobar el dinero a tiempo — 15%

Ya está medido: viático cerrado, cuadrado y dentro del plazo. Funciona.

Una nota: hasta hace unos días `limite_comprobacion` no se escribía
nunca, así que este criterio se evaluaba contra un campo vacío. Ya quedó
—lo encontró la prueba 360— pero conviene saberlo antes de comparar
meses viejos contra meses nuevos: **los meses anteriores a la corrección
no son comparables.**

### 5. Capacitación del mes — 10%

Se queda, con peso bajo, porque el dato lo pone Odoo y no depende de lo
que hizo en el servicio. Es un requisito, no un desempeño.

### 6. Que el cliente lo vuelva a pedir — 5%

La única medida que el sistema puede contar solo y que ninguna otra
captura: **cuántas veces un cliente pidió que le mandaran a esta misma
persona otra vez.** Un solicitante que nombra a alguien está diciendo
algo que ninguna encuesta dice.

Pesa 5% a propósito. El personal de plazas chicas o de cuentas nuevas no
tiene cómo acumularlas, y castigarlos por eso sería castigar la
geografía. Suma, no resta.

---

## Lo que deliberadamente NO entra

**La encuesta del ejecutivo.** Califica el servicio y al equipo, no a la
persona. Si el equipo fueron tres y uno la regó, los tres se llevan la
estrella o la pierden los tres. Es señal buena para el consultor y para
la cuenta; es señal injusta para el bono individual. Se muestra en la
ficha —informativa— y no suma puntos.

**Los años de experiencia y la antigüedad.** Ya pesan en la calificación
para asignar. En el bono del mes no tienen nada que hacer: el bono es
por lo que hizo este mes.

**El número de servicios.** Quien trabajó veinte días no debe ganarle al
que trabajó ocho por haber trabajado más: eso lo paga la nómina, no el
bono. Todos los criterios son porcentajes sobre **sus propias**
jornadas.

---

## Las dos reglas que mandan sobre todas

**1. Nadie debe poder subir su calificación haciendo algo que no le
sirve al cliente.** Cada criterio se revisa contra esta pregunta. Si la
respuesta es "sí podría", el criterio está mal escrito. Por eso el daño
declarado no castiga, por eso la marca fuera de geocerca no cuenta, y
por eso marcar hitos de más no suma nada.

**2. Cada punto perdido se explica en una frase con fecha.** El motor ya
guarda `detalle` por criterio ("3 de 4 jornadas a tiempo. Tarde: 14/09").
Eso tiene que llegar a la pantalla tal cual. Un bono que se pierde sin
explicación se convierte en un pleito con RRHH; uno que dice *el 14 de
septiembre llegó 22 minutos tarde* se convierte en una conversación.

---

## Las tres pantallas

### A. Configuración de criterios — por país

Quién entra: dirección de operaciones y RRHH. Un renglón por criterio,
con su peso, su monto y su umbral. Al pie, el bono posible del mes y una
advertencia si los pesos no suman 100.

Cambiar un criterio **no recalcula meses ya cerrados.** Se avisa en la
misma pantalla: *aplica a partir del mes en curso*.

### B. El mes — quién ganó qué

Un renglón por persona: estrellas obtenidas sobre posibles, monto, y el
estado (calculada / autorizada / pagada). Filtro por país y plaza.
Arriba, el corte: cuántos ganaron completo, cuántos parcial, cuántos
quedaron en cero y por qué.

El botón de **autorizar** es de RRHH y es por persona o por lote. Una
vez autorizado, el monto se congela y viaja a la nómina.

### C. La ficha de la persona

El desglose. Por criterio: lo medido, el umbral, si cumplió, cuánto pagó
y **la frase con las fechas**. Si el mes se anuló por incidencia, la
incidencia arriba de todo, con su gravedad y quién le dio visto bueno.

Esta es la pantalla que se imprime y se le entrega. Tiene que poder
leerse sin que nadie la explique.

---

## Las cuatro piezas que faltan

**1. No hay pantalla.** `RUTAS` en `app.js` no tiene ninguna entrada de
bonos. El router existe, los endpoints responden, y nadie los puede ver.

**2. El bono autorizado no llega a la nómina.** `autorizar_bono()` marca
el estatus y ahí se acaba. `nomina.py` no menciona evaluaciones. El
puente natural es un `AjusteNomina` con `concepto="bono_estrellas"`,
monto positivo, motivo *"Bono de estrellas 09/2026 — 4 de 4"*, que la
nómina de la siguiente semana ya sabe recoger. Con eso el dinero llega
por un camino que ya está probado, y queda el rastro de por qué llegó.

**3. Nadie dispara la evaluación mensual.** Hay que llamar `evaluar()`
persona por persona, a mano. Falta la tarea que el día 1 de cada mes
recorra al personal activo y calcule el mes anterior. El resultado nace
como CALCULADA —nunca autorizada sola.

**4. Los pesos configurados se ignoran** (el reparto en partes iguales
de arriba).

---

## Lo que necesito de usted

- **Los montos reales por país.** Los $2,600 son del sembrador de
  ejemplo.
- **Si acepta el margen de 5 minutos** en una sola jornada del mes.
- **Si el daño auto-declarado se perdona**, como propongo.
- **Quién autoriza**: ¿RRHH solo, o RRHH con visto bueno de operaciones
  arriba de cierto monto?
- **Si la capacitación se queda** o sale del bono y se vuelve requisito
  de contrato.

Con eso se programa. Sin eso se programa también, pero con números de
ejemplo que después hay que cambiar a mano en cada país.

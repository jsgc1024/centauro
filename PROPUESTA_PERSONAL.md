# La pantalla de personal — propuesta

_Qué enseñar de cada persona, y tres cosas que hay que arreglar antes._
_Antes de programar nada. 20 de septiembre de 2026._

---

## Lo que la pantalla enseña hoy

Cuatro columnas: nombre y plaza, una calificación de 0 a 100, la palabra
*confianza* con un adjetivo, y las horas acumuladas.

```
Juan Ramírez Solís      87.4   confianza alta    1,240 h
CDMX
```

Y nada más. No se puede saber **por qué** ese 87.4, ni qué dijeron los
clientes, ni si trae un certificado vencido. Para asignar a alguien a un
servicio hay que decidir con un número que no se explica.

---

## Lo que el sistema ya sabe y la pantalla tira

`profesionalismo.tabla()` llama a `ficha()` de cada persona —que calcula
las **cinco dimensiones**, cada una con su valor, su peso aplicado, su
aporte y **una frase que la explica**— y después se queda con cuatro
campos y tira el resto.

El cálculo caro ya se hizo. Lo que falta no es motor, es pantalla.

| Dimensión | Peso | Lo que ya calcula |
|---|---|---|
| Estrellas del bono | 30% | "14 de 18 estrellas posibles en 3 meses" |
| Satisfacción del cliente | 25% | "7 calificaciones, promedio 4.43 de 5" |
| Incidencias | 25% | las autorizadas, con su castigo |
| Capacitación | 10% | "3 de 3 meses al corriente" |
| Experiencia | 10% | "1,240 h acumuladas en Centauro" |

---

## Tres hallazgos, antes de dibujar nada

### 1. La capacitación se mide de dos maneras que no se hablan

Hay **dos verdades distintas** sobre lo mismo:

- **`EvaluacionMensual.capacitacion_cumplida`** — una casilla mensual
  que alguien pone a mano. De ahí salen el 10% del bono y el 10% de la
  calificación.
- **La tabla `capacitacion`** — los certificados de verdad: nombre,
  institución, fecha en que se obtuvo y **`vigencia_hasta`**. Vive en el
  task sheet y en la app de campo. **La consola no la enseña.**

Y el criterio del bono dice *"dato de Odoo"* — pero **Odoo no lo manda**.
Se lo pedimos en la sección 2.7 de `ODOO_LO_QUE_NECESITAMOS.md` y sigue
abierto.

**Propuesta: que la casilla deje de ser una casilla.** Está al corriente
quien **no trae ningún certificado vencido** al cierre del mes. Eso el
sistema lo calcula solo, hoy, con la tabla que ya existe — sin esperar a
Odoo. Y cuando Odoo mande los cursos, solo cambia de dónde llegan las
filas: no cómo se mide.

Con un candado, el mismo que le pusimos al dato faltante en el bono: si
la persona **no tiene ningún certificado registrado**, el criterio **no
aplica** en vez de reprobar. Nadie pierde dinero porque a un padrón le
falte una captura.

### 2. El certificado vencido no le avisa a nadie

`vigencia_hasta` existe desde hace meses y **nada la vigila**. Una
certificación vencida no es una certificación, y el día que importa
—cuando el cliente pregunta— nadie va a revisar la fecha.

La tarea diaria que ya corre puede mirarla: aviso **a los 30 días** y el
día que vence. A la persona, por su app, y a su consultor.

### 3. "Confianza" no dice de qué

Hoy la palabra sale de cuántas dimensiones **no se pudieron medir**:
ninguna → alta, una → media, dos o más → baja. El dato es honesto y está
mal dicho: *"confianza baja"* se lee como desconfianza de la persona,
cuando lo que dice es que **al sistema le faltan datos sobre ella** —que
es justo lo que le pasa a quien lleva dos semanas en la empresa.

**Propuesta:** decirlo como lo que es. **"Medido con 3 de 5"**, y al
detalle, cuáles faltan y por qué.

---

## La pantalla propuesta

### A. La lista — para decidir a quién mando

Un renglón por persona, ordenada por calificación como hoy:

| Columna | Qué dice |
|---|---|
| **Persona** | nombre, plaza, y si es freelance |
| **Calificación** | el número con su barra, y *medido con N de 5* |
| **El cliente** | promedio en estrellas y cuántas calificaciones |
| **Bono del mes** | estrellas obtenidas de posibles, y el monto |
| **Capacitación** | semáforo: al corriente · vence en N días · vencido |
| **Incidencias** | las de la ventana, por gravedad |
| **Horas** | las acumuladas |

Filtros: país, plaza, y **"solo con certificado por vencer"** — que es la
pregunta que hoy no se puede hacer.

### B. La ficha — se abre al picar el nombre

Cuatro bloques, en este orden:

1. **Las cinco dimensiones**, cada una con su frase y su aporte al
   número. Es lo que convierte un 87.4 en algo que se puede discutir.
2. **El bono, últimos seis meses.** Un renglón por mes con sus estrellas
   y su monto, y el estado.
3. **Lo que dijeron los clientes.** Las últimas calificaciones con el
   texto que escribieron, no solo el promedio.
4. **El padrón de certificados**, con institución y fechas, y lo vencido
   en rojo.

---

## Las dos reglas que esta pantalla no puede romper

**1. La calificación es para asignar; el bono es dinero.** Son dos cosas
distintas y van juntas en la misma pantalla, así que hay que decirlo: una
calificación baja del cliente **no baja el pago de nadie**. Abre una
revisión. Si la pantalla lo sugiere aunque sea de lado, mañana alguien va
a discutir su nómina con este número.

**2. La encuesta del ejecutivo es señal de grupo, no individual.** Si el
equipo fueron tres, los tres cargan la misma nota. Se muestra con esa
etiqueta —*del equipo*— y no como si fuera su calificación personal.

---

## Lo que necesito de usted

- **¿La casilla de capacitación pasa a calcularse del padrón de
  certificados?** Es el cambio de fondo de esta propuesta.
- **¿A cuántos días avisa el vencimiento?** Propongo 30.
- **¿Quién ve la ficha de quién?** ¿Un consultor alcanza a cualquiera, o
  solo al personal de su plaza?
- **¿Odoo va a mandar los cursos**, o se siguen capturando aquí? Si se
  quedan aquí, falta la pantalla para capturarlos: hoy no existe.

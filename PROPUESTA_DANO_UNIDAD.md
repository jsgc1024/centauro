# La declaración de daño de la unidad

Pedido por Salvador, 18 de septiembre:

> Que el que tiene a cargo la unidad, al recibirla, pueda describir si la
> recibe con algún daño o golpe. Y al entregarla, que declare si tuvo
> algún golpe o daño durante el servicio y explique qué pasó.

---

## 1. Qué hay hoy, y por qué no alcanza

La revisión de unidad ya guarda cinco fotos obligatorias, firma,
kilometraje y gasolina en las dos puntas. Para el daño hay dos cosas, y
las dos son **opcionales**:

- `RevisionUnidad.nota` — un texto libre.
- Fotos con ángulo `dano` — acercamientos de un golpe, sin límite.

El problema no es que falte dónde escribir. Es que **nadie está obligado
a decir nada**, y el caso normal de una casilla opcional es que se quede
vacía. Quien recibe una camioneta golpeada a las seis de la mañana, con
prisa, no va a documentar por su cuenta un daño que no hizo —y ahí es
exactamente donde le va a hacer falta.

Y falta la distinción que de verdad decide quién paga:

| | |
|---|---|
| **Al recibirla** | *"así me la dieron"* — el golpe venía de antes, no es suyo |
| **Al entregarla** | *"esto pasó durante mi servicio"* — y qué pasó |

Hoy eso hay que deducirlo comparando fotos. La pantalla del consultor lo
pone lado a lado y ayuda mucho, pero **comparar es trabajo de alguien que
ya sospecha**. Una declaración es un dato que se puede buscar, contar y
avisar.

---

## 2. La tensión de fondo

Esto es lo único que puede hacer que el campo no sirva para nada:

> **Si declarar un daño propio cuesta caro, nadie va a declarar nunca.**

Y vamos a haber construido una casilla que siempre dice "no", que es peor
que no tenerla: da una falsa sensación de que se está documentando.

Declarar tiene que costar **menos** que esconder. Eso no es una idea
bonita: es la condición para que el dato sirva.

La buena noticia es que el sistema ya está construido con esa forma, y
conviene apoyarse en lo que ya existe en vez de inventar:

- **`GravedadIncidencia.ERROR_MENOR`** existe y su comentario dice *"solo
  retroalimentación documentada"*. El motor lo confirma: `incidencia_del_mes`
  filtra `gravedad != ERROR_MENOR`, así que **nunca toca las estrellas**.
  Ya hay un nivel que documenta sin castigar.
- **Las incidencias las clasifica el consultor**, y necesitan visto bueno
  del director de operaciones para contar. El sistema nunca clasifica
  solo.

---

## 3. Lo que propongo

### 3.1 El modelo: dos columnas, no cuatro

En `RevisionUnidad`, que ya es una fila por punta:

```
hubo_dano: bool          # obligatorio, sin valor por omisión
dano_nota: str | None    # obligatorio cuando hubo_dano es verdadero
dano_tipo: TipoDano|None # rayón, golpe, cristal, mecánico, otro
```

No hacen falta cuatro columnas —dos para recibir y dos para entregar—
porque `tipo` ya dice cuál de las dos preguntas se contestó:

- `tipo = recibe` y `hubo_dano = true` → **venía dañada**
- `tipo = entrega` y `hubo_dano = true` → **se dañó durante el servicio**

`dano_tipo` va con nombre y no como texto libre por la misma razón que
`MotivoCambio`, escrita en su propio comentario: *"de aquí salen dos
cuentas que la dirección va a pedir... escrito a mano no se puede
contar"*. Cuántos daños hay, de qué tipo y en qué plazas es la misma
clase de pregunta.

**Migración:** sí. Dos columnas nuevas y un tipo. `hubo_dano` entra con
valor por omisión `false` para las revisiones que ya existen —no se puede
inventar lo que nadie declaró— y eso queda escrito en la migración.

### 3.2 La app de campo: la pregunta no se puede saltar

En la pantalla de revisión, después de las fotos y antes de la firma:

**Al recibirla** — *"¿La estás recibiendo con algún daño?"*, con dos
botones grandes: **No** / **Sí, tiene un daño**. Sin valor marcado de
antemano: no se puede firmar sin contestar.

Si contesta que sí: se abre el tipo, la descripción —obligatoria— y se le
pide al menos un acercamiento del golpe.

Y debajo, con todas sus letras:

> **Esto te protege a ti.** Lo que declares aquí queda como el estado en
> que la recibiste. No es una falta tuya.

**Al entregarla** — *"¿La unidad sufrió algún daño durante tu servicio?"*,
mismos dos botones. Si contesta que sí: tipo, qué pasó —obligatorio— y
fotos.

Y debajo:

> Lo revisa tu consultor. Declararlo no es una falta: esconderlo sí.

### 3.3 Qué hace el sistema cuando alguien declara

Aquí está la decisión, y mi recomendación es **deliberadamente poco**:

| Cuándo | Qué hace el sistema |
|---|---|
| **Daño al recibir** | Lo guarda y lo enseña. **Nada más.** Ni alerta, ni incidencia, ni aviso urgente. Quien declara no hizo nada: se está protegiendo |
| **Daño nuevo al entregar** | Lo guarda, lo enseña marcado, y **avisa al consultor**. Nada automático contra la persona |

**No genero una incidencia automática, ni siquiera `ERROR_MENOR`.** Dos
razones: el sistema nunca clasifica solo —eso es del consultor, con visto
bueno del director— y un renglón automático en el expediente de alguien,
aunque no quite estrellas, es algo que nadie juzgó y que después hay que
explicar. El consultor ya tiene el botón para clasificar una incidencia
si lo amerita.

### 3.4 La pantalla del consultor

En el bloque de revisión de unidad que ya existe:

- Una marca visible en cada punta cuando hubo declaración, con el tipo y
  el texto. Rojo para el daño nuevo al entregar; ámbar para el que ya
  venía.
- El caso que salta solo, y que hoy no se ve: **recibida sin daño
  declarado y entregada con daño nuevo.** Ese es el renglón que hay que
  atender.
- El caso contrario también vale: **recibida con daño declarado** es lo
  que protege a esa persona tres semanas después.

### 3.5 Lo que se gana sin pedirlo

Con `dano_tipo` con nombre, la dirección puede preguntar cosas que hoy no
tienen respuesta: cuántas unidades vuelven con daño al mes, de qué tipo,
en qué plazas, con qué clientes. Es el mismo argumento por el que
`MotivoCambio` no es texto libre.

---

## 4. Lo que hay que decidir

1. **Qué hace el sistema con un daño declarado al entregar.** Mi
   propuesta: avisar al consultor y nada más. La alternativa es levantar
   alerta a la central, como una contingencia.
2. **Si el daño declarado al recibir frena algo.** Mi propuesta: no,
   nunca. Es lo que hace que declarar sea seguro.
3. **Si el tipo de daño va con nombre o como texto libre.** Mi propuesta:
   con nombre, para poder contarlo.

---

## 5. Lo que NO propongo, y por qué

- **Que el sistema decida quién paga.** Eso es de personas. El sistema
  guarda evidencia y la pone lado a lado.
- **Un catálogo de daños por parte del vehículo** (defensa, cofre,
  cristal delantero...). Suena ordenado y en la práctica es un formulario
  que nadie llena a las seis de la mañana. La foto ya dice dónde.
- **Bloquear el fin de servicio por un daño declarado.** El candado de la
  revisión ya obliga a entregarla; agregar un freno por declarar sería
  castigar justo lo que queremos fomentar.

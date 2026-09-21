# La ayuda en pantalla

Pedido por Salvador, 18 de septiembre:

> Me gustaría desarrollar algún tutorial o algo por pantalla para que los
> usuarios sepan para qué sirve cada punto y sepan el alcance de cada
> herramienta junto con su importancia. Busco que los usuarios puedan
> resolver sus dudas de una manera más clara y al alcance de un clic.

---

## 1. Lo que ya existe, contado

Antes de escribir una línea nueva conviene ver qué hay. El sistema ya
explica bastante; lo que pasa es que está repartido en tres sitios y solo
dos llegan al usuario.

| | |
|---|---|
| **67 textos explicativos** en la consola | 34 pies de bloque, 29 subtítulos, 4 ayudas de campo. En tres idiomas: **201 renglones ya escritos** |
| **52 descripciones de actividad** | Escritas a propósito pensando en quien reparte accesos, no en el endpoint |
| **70 mensajes `que_hacer`** en el servidor | Lo que hay que hacer para salir del problema, en el momento en que el sistema te frena |
| **~95 bloques con encabezado** en 10 pantallas de consola | El universo de "un `?` por bloque" |

**El hallazgo que cambia la escala del trabajo:** los 70 `que_hacer` son
ayuda entregada en el instante exacto en que hace falta. El sistema no
dice "no se puede" y ya: dice qué pasó y qué hacer, y `api.js` los junta
en un solo mensaje. Eso es mejor que cualquier tutorial, porque llega
cuando la persona tiene la pregunta —no media hora antes, cuando todavía
no sabía que la iba a tener— y **ya funciona**.

Así que esto no es escribir un manual. Es cosechar lo que hay, subirle el
nivel a una parte, y hacer alcanzable lo que hoy no lo es.

---

## 2. La regla que define el diseño

> **La ayuda vive donde vive la cosa que explica.**

Un tutorial que vive aparte de la pantalla se despega el día que la
pantalla cambia, y nadie se entera hasta que un usuario sigue un paso que
ya no existe y pierde la confianza en todo lo demás.

Es la misma lección que este proyecto ya aprendió tres veces: el umbral
de silencio que vivió meses con 60 en una pantalla y 120 en la otra; el
tope del mes escrito lejos de su candado; la lista de ángulos de foto que
se quedó en cuatro cuando el servidor pasó a cinco.

**En la práctica:** la ayuda va en `idioma.js`, con las demás claves,
para que `revisar.py` la barra igual —que falte una traducción sale a la
luz sola— y para que quien cambie una pantalla tenga su texto al lado.

---

## 3. Tres capas, de la más barata a la más cara

### Capa 1 — El pie que ya existe, revisado

Los 67 textos, leídos con ojo de quien nunca usó el sistema. El problema
de varios no es que falten: es que dicen **qué es** y no **para qué
sirve**.

*"Días que ya pasaron y siguen abiertos"* dice qué es. La versión que
sirve ya está ahí y sigue: *"Mientras lo estén, esa gente no entra al
corte de nómina"*. Eso es lo que hace que alguien lo atienda hoy.

Barato, y es lo que más gente va a leer sin buscarlo.

### Capa 2 — Un `?` por bloque

Junto a cada encabezado, un signo que abre tres frases:

1. **Para qué sirve** este bloque.
2. **Qué pasa si no lo haces.**
3. **De dónde sale el número** —cuando hay un número.

Las tres juntas son lo que convierte una pantalla en algo que se entiende
en vez de algo que se opera de memoria. Son ~95 bloques, y no todos lo
necesitan: yo empezaría por los que mueven dinero o frenan la operación.

### Capa 3 — El recorrido de la primera vez

Una secuencia guiada para quien entra nuevo, una sola vez, repetible
desde el `?`.

**Es la que yo no haría, y lo digo aunque fue lo que pediste.** Tres
razones: es la más cara de construir; es la que más rápido se despega
—este sistema cambia cada semana—; y es la que menos se usa, porque se ve
una vez, cuando la persona todavía no tiene ninguna pregunta concreta.

Lo que sí resuelve el problema del que entra nuevo, mucho más barato: un
`?` arriba de cada pantalla que conteste *"¿qué es esta pantalla y cuándo
la abro?"*. Es el mismo componente de la capa 2, puesto en el título.

---

## 4. Lo que haría valiosa esta ayuda de verdad

Este código está lleno de **por qué**, no de **qué**:

> *"El dinero que ya salió no se mueve con la persona."*
> *"Quien no marca su llegada no se paga."*
> *"Una revisión firmada por quien no traía la unidad es papel."*
> *"Declararlo no es una falta: esconderlo sí."*

Eso es lo que hace que un consultor confíe en el sistema en vez de
pelearse con él. **Cuando el sistema le dice que no, la diferencia entre
obedecer a regañadientes y entender está en una frase** —y esas frases ya
están escritas, en los comentarios del código y en los `que_hacer`.

La ayuda no tiene que inventar nada. Tiene que traerlas a la pantalla.

---

## 5. El personal de campo necesita otra cosa

Están en un teléfono, a las seis de la mañana, con una mano, a veces con
el cliente esperando. Ahí no cabe un recorrido ni un `?` que se toca con
el pulgar por accidente.

Ahí sirve **un renglón por pantalla que diga qué se espera de ellos
ahora**, y eso ya se ha ido construyendo: *"Sin esto no puedes marcar fin
de servicio"*, *"Esto te protege a ti"*, *"Cada foto sale junto a la de
cuando la recibiste"*.

Mi propuesta para el campo: **revisar los que hay y completar los que
faltan, sin agregar ningún componente nuevo.** La app no necesita un
sistema de ayuda; necesita que cada pantalla diga la frase correcta.

---

## 6. Lo que hay que decidir

1. **¿Va la capa 3 —el recorrido guiado—?** Mi recomendación es no, y
   poner en su lugar un `?` de pantalla. Pero fue lo que pediste, así que
   la decisión es tuya.
2. **¿Por dónde empezamos: la consola o la app de campo?**
3. **¿Cuántos bloques llevan `?` en la primera entrega?** Mi propuesta:
   solo los que mueven dinero o frenan la operación —cierre, viáticos,
   nómina, bonos, el candado de la unidad— que son los que generan las
   llamadas.

---

## 7. Lo que NO propongo

- **Un manual en PDF.** Se despega el primer día y nadie lo abre el
  segundo.
- **Una pantalla de "Ayuda" aparte.** Obliga a salir de donde estás para
  preguntar por donde estabas.
- **Textos genéricos de interfaz** —"aquí puede usted administrar los
  registros"—. Si la frase no dice algo que la persona no sabía, es ruido
  que enseña a ignorar los `?`.

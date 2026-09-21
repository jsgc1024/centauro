# El implantado 12 × 36

**Propuesta, 20 de septiembre.** Antes de escribir código.

---

## Qué es

Un puesto de doce horas que se cubre **los siete días de la semana** con
**dos personas de la misma categoría** que se alternan día con día. Doce
horas de trabajo por treinta y seis de descanso: quien trabaja el lunes
descansa el martes y vuelve el miércoles.

Es la escala de Brasil. Lo que Centauro opera hoy —una persona, doce
horas corridas, los días que diga el acuerdo— es el otro tipo, y no se
toca.

**El mes sale entero en verde.** Hoy los fines de semana salen en ámbar
porque están contratados y nadie dijo quién los cubre: el que trabajó de
lunes a viernes descansa. En 12 × 36 eso no existe —cada día tiene a su
persona desde que se genera el mes— y el ámbar desaparece.

---

## Lo que ya quedó puesto (hoy)

El selector, nada más:

- `AcuerdoImplantado.turno` — `"natural"` o `"12x36"`, migración
  `e4c19d70b3a8`. Todo lo que ya existe queda en `"natural"`, que es lo
  que es.
- El selector en el alta, a la derecha de la ciudad, con su explicación
  y un aviso en ámbar: *"en construcción; por ahora el calendario y la
  nómina se arman igual que en 12 horas naturales"*.
- Se ve en el trato, junto a los días de la semana.

**Elegir 12 × 36 hoy no cambia nada todavía.** Eso es a propósito: la
puerta está abierta y el cuarto está por construirse.

---

## Lo que cambia, pieza por pieza

### 1. El calendario del mes

Hoy `dias_del_mes()` corta por `dias_servicio` —lunes a viernes, lunes a
sábado— y `generar_mes()` marca el fin de semana como **día adicional** y
lo abre **vacío**, sin gente, a propósito.

En 12 × 36: **todos los días del mes**, sin excepción, y cada uno con su
persona puesta. Ni ámbar ni días vacíos.

### 2. La alternancia

Quién trabaja cada día. La plantilla ya guarda las dos personas
(`PersonaImplantado`); lo que falta es **el orden** y **de dónde arranca
el mes**.

La regla que propongo: la plantilla tiene dos renglones, A y B. El primer
día del mes lo cubre quien **no** cubrió el último día del mes anterior.
Sin esa continuidad, un mes que termina con A y otro que empieza con A le
da a esa persona dos días seguidos, que es justo lo que el 12 × 36 no
permite.

El primer mes de un servicio arranca con el primer renglón de la
plantilla, que es el que el consultor puso primero.

### 3. La unidad

Una sola, opcional. Si la hay, **va todos los días del mes** y la maneja
quien trabaja ese día. No se parte, no rota: rota la gente alrededor de
ella.

### 4. La plantilla

Un candado nuevo: en 12 × 36 la plantilla son **exactamente dos personas
y de la misma categoría**. Con una sola no se puede alternar; con tres no
se sabe quién va. Con categorías distintas, el precio al cliente y la
comisión cambiarían según el día que caiga.

### 5. El cobro

Aquí está la decisión de fondo, y es la que te pregunto abajo. Hoy el mes
se factura así: días base × precio por día + días adicionales × su precio
+ el vehículo por mes. El fin de semana es *adicional* porque está fuera
de lo contratado de lunes a viernes.

En 12 × 36 **no hay fin de semana fuera del trato**: el mes completo es
el trato.

### 6. Lo que no cambia

- **La nómina.** Paga por asignación y por día trabajado. Cada quien sus
  quince o dieciséis días, y el que trabaja un festivo cobra su factor.
  El motor ya lo hace bien.
- **Los viáticos.** Son por persona y por día.
- **Los relevos y la contingencia.** Ya usan un solo motor, compartido
  con el eventual. Lo único que hay que cuidar es que un relevo **no
  rompa la alternancia** de los días que siguen.
- **La hoja del implantado y el task sheet.** Salen de la jornada, y la
  jornada ya dirá quién va.

---

## Decidido (Salvador, 20 de septiembre)

### El cobro · cerrado

**No hay nada extra en este servicio.** El mes es el mes: todos los días
son base. Si el cliente pide algo adicional —una persona más, un
traslado, un día de otra cosa— **eso sale como un servicio eventual
aparte**, no como un día adicional de este contrato.

Lo único que puede crecer dentro del mes son las **horas extra**, que ya
existen y se pagan como en cualquier jornada.

Consecuencia directa, y hay que construirla: la puerta del **día
adicional** del implantado —la que hoy permite agregarle un día suelto al
mes— **se cierra en 12 × 36**, y cuando alguien la toque, el sistema dice
por dónde va: por un eventual.

### La regla que manda sobre el calendario

**Una persona no puede trabajar dos días seguidos.** No es una
preferencia del armado: es la regla que define la escala, y todo lo demás
—la alternancia entre meses, el reemplazo, el relevo— se dobla ante ella.

### La plantilla · cerrado

- **Dos personas, de la misma categoría.** Es regla; el sistema lo frena.
- **Una sola unidad por turno.** Es regla.

### El país

**Queda abierto para cualquier país.** El 12 × 36 viene de Brasil pero no
es de Brasil.

### Lo que sigue igual que en el implantado natural

- **Los viáticos**: por persona, y cada quien se hace cargo de los suyos.
- **El cierre**: a fin de mes.
- **La nómina**: corte semanal.

---

## Lo que falta decidir

### A · El arranque · cerrado

**El consultor dice quién empieza.** Al armar la plantilla se marca cuál
de las dos personas entra el primer día, y de ahí se alterna. Queda
escrito y no depende del orden en que se capturaron: el orden de captura
es un accidente, y de esto sale quién trabaja el día 1 de cada mes que
abra después.

### B · El reemplazo por enfermedad · cerrado

**Regla de Salvador:** A y B se alternan. A se enferma. **B sigue igual
—no se le mueve un solo día—** y entra **C** a cubrir **todos los días
que A no pueda**, hasta que A se recupere.

Nada de intercambiar turnos entre A y B: eso le movería los días a quien
no faltó.

**Cómo se paga:**

- **Si el cambio se hace el día que A ya arrancó** y ese mismo día entra
  quien lo cubre, **ese turno se paga a los dos**. Es el día partido que
  ya existe: A cobra lo que trabajó y C cobra su día.
- **Si se sabe con anticipación** y el consultor coordina los días que va
  a trabajar C, **solo se pagan esos días a C**. No hay nada que partir
  porque A no se presentó.

**Lo que esto significa para el código: nada nuevo.** El motor de relevo
—el mismo del eventual— ya hace exactamente esto: mira día por día si la
persona que sale está asignada, y el día que no lo está lo salta. Los
días de B no se tocan porque B no es quien sale. Lo que falta no es
construirlo: es **probarlo con un 12 × 36 enfrente**, que es lo único que
garantiza que siga siendo cierto.

---

## Cómo lo construiría, y en qué orden

1. **El calendario** — que `generar_mes` haga los 30/31 días y ponga a
   cada quien en el suyo. Con su prueba: un mes de 12 × 36 no tiene días
   vacíos ni ámbar, y nadie trabaja dos días seguidos.
2. **El candado de la plantilla** — dos personas, misma categoría.
3. **La continuidad entre meses** — el primer día sale del último del mes
   anterior.
4. **El cobro** — según lo que decidas en la 1.
5. **El panel del mes** — que pinte el verde parejo y diga de quién es
   cada día.
6. **El relevo** — que cambiar a una de las dos no descuadre la
   alternancia de los días que siguen.

Del 1 al 3 es lo que hace que el mes exista y esté bien armado. El 4
depende de tu decisión. El 5 y el 6 son los que se notan cuando el
servicio ya está corriendo.

---

## Lo que esto no toca

- **El eventual.** Nada.
- **El implantado de 12 horas naturales.** Nada: todo lo que existe hoy
  queda en `"natural"` y se comporta igual. El código nuevo entra por una
  bifurcación, no reescribiendo el que ya opera.

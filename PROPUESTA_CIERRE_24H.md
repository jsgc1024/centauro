# El cierre en dos relojes

22 de septiembre. Propuesta antes de escribir código.

## Lo que pediste

1. Las **24 horas del personal de seguridad** para comprobar viáticos
   arrancan en el **término general del servicio** (estatus
   *terminado*), no al cierre de cada día. En un full day de tres días,
   los viáticos de los tres días se comprueban en las 24 horas que
   siguen al cierre del último día.
2. Al concluir esas 24 horas, el servicio pasa a un proceso adicional,
   **Sin visto bueno**, y ahí arrancan las **24 horas del consultor**.
3. Cuando el consultor da el **término general** (visto bueno), el
   servicio **se manda a Odoo** para su facturación.
4. Aplica **a eventuales y a implantados**. En el implantado, el cierre
   se da **el último día del mes**: cada mes es una unidad
   independiente que recorre la cadena completa; abrir el siguiente es
   planeación.
5. **La cancelación es un término.** Si un servicio se cancela, corren
   las mismas 24 h del personal para cerrar viáticos y las 24 h del
   consultor para revisar la cancelación; se repite el proceso.

## ¿Es viable?

**Sí.** Las tres piezas ya existen: el límite de comprobación por
viático, el reloj del consultor en el cierre y el envío de la factura a
Odoo. Lo que cambia es **cuándo arranca cada reloj** y **quién dispara
la factura**. Los riesgos no son técnicos, son de reglas: un plazo que
nace vencido, un implantado que nunca "termina", un día reabierto con
el reloj ya corriendo. Por eso esta propuesta baja al detalle.

## Hoy contra la propuesta

| | Hoy | Propuesta |
|---|---|---|
| Reloj del personal | Término de **cada día** + 24 h; en tres días, tres vencimientos | **Término general** + 24 h; una sola fecha para todos los viáticos del servicio |
| Reloj del consultor | Arranca en el mismo instante en que el servicio queda terminado | Arranca **al terminar las 24 h del personal** —o antes, si todos los viáticos ya cerraron (decisión 2)— |
| Fases del servicio | terminado → cerrado | terminado → **sin visto bueno** → **en facturación** → cerrado |
| Factura en Odoo | Al aprobar finanzas | **Al dar el consultor el visto bueno** (término general) |
| Finanzas | Aprueba: cierra y factura | Valida y cierra; la factura ya salió (decisión 3) |
| Implantado | Sin cierre por mes: solo el papel del corte; viáticos con plazo por día | **Cada mes lleva su propio estatus y su cierre**, con los mismos dos relojes; T0 = cierre del último día trabajado del mes |
| Cancelación | *Cancelado* es final: el dinero afuera queda enlistado, sin reloj | **La cancelación es un término**: T0 = momento de cancelar; corren los dos relojes y se repite el proceso |

## La línea de tiempo


La misma línea vale para los dos tipos. En el eventual, T0 es el cierre
del último día del servicio y las fases las lleva el servicio. En el
implantado, T0 es el cierre del **último día trabajado del mes** y la
cadena la recorre **el mes**, que es la unidad independiente. Y una
cancelación es un T0 más: el momento en que se cancela.

## Las reglas, una por una

**R1 · T0.** El término general es la **hora real de término del último
día** del servicio —la marca *Terminar el servicio* desde la app, o la
hora de término que asienta la central al cerrar a mano—, en hora del
país del servicio. En ese instante el servicio queda *terminado* y
salen las encuestas al cliente, como hoy.

**R2 · Los viáticos.** Al quedar terminado, **todos** los viáticos del
servicio reciben el mismo límite: **T0 + 24 h**. Cerrar los días
anteriores ya no abre plazo. En la app, antes de T0 el agente ve *"por
comprobar · el plazo corre al terminar el servicio"*; desde T0 ve
*"vence en…"* y, pasado el límite, *vencido*.

**R3 · Quien salió antes.** A quien lo relevaron o cambiaron a media
operación no lo alcanza el término general: propongo que sus 24 h
corran **desde el relevo**, como hoy (decisión 1).

**R4 · T1, el arranque del consultor.** Lo pone el **reloj del sistema**
(la tarea que corre cada cinco minutos), no una persona: en **T0 +
24 h** el cierre pasa a *sin visto bueno*, el servicio también, y el
límite del consultor queda en **T1 + 24 h**. Si todos los viáticos del
servicio ya están cerrados, devueltos o cancelados antes de T0 + 24 h,
propongo que T1 llegue en ese momento (decisión 2): no hay nada que
esperar. Al consultor le llega el aviso: *"EP/E-006: tienes 24 h para
el visto bueno"*.

**R5 · El visto bueno.** Solo desde T1. Sigue el candado de hoy, que es
correcto: no se puede dar con viáticos abiertos (se cierran **con
descuento** si no comprobaron), con días sin término ni con marcas que
la central no ha validado. *Dentro de plazo* se juzga contra T1 + 24 h,
en hora del país del servicio; de eso depende la comisión.

**R6 · La factura.** El visto bueno es el término general: el cierre
pasa a *en facturación* y **en ese momento** se manda la factura a
Odoo. Si Odoo no está conectado o no contesta, el servicio queda en
**por facturar** con el error a la vista y se reintenta desde ahí;
nada de lo anterior se deshace. Los días trabajados entran al corte de
nómina desde aquí, como hoy.

**R7 · Finanzas.** Valida y aprueba: el servicio queda *cerrado* y, si
el visto bueno fue en plazo, se detona la comisión del consultor
(decisión 3).

**R8 · Implantado: el cierre es del mes.** El implantado nunca queda
*terminado* —cuando cierra un mes, el siguiente ya está abierto—, así
que las fases no las lleva el servicio sino **el mes de contrato**:

- **T0 del mes** = hora real de término del **último día trabajado del
  mes** (la última jornada del mes en el calendario; si el mes acaba en
  fin de semana, el viernes). Marca desde la app o cierre a mano, como
  en el eventual. Mientras ese día no se cierre, el mes no arranca su
  reloj: vive en *Días sin cerrar* (decisión 6).
- **Los viáticos del mes** —todos los de sus jornadas, incluidos los de
  quien cubrió un día— reciben límite **T0 + 24 h**. Cerrar cada día
  deja de abrir plazo, igual que en el eventual. Quien salió del
  contrato a media operación: desde su salida (decisión 1).
- **Un cierre por mes**: comprobación → sin visto bueno → en facturación
  → cerrado, con los mismos relojes (R4 a R7). El comparativo del mes
  sale del corte que ya existe —días base, días adicionales, el precio
  del mes de la unidad y el precio por día del personal— contra lo
  trabajado; los candados del visto bueno miran solo las jornadas de
  ese mes.
- **La factura es del mes**: el visto bueno manda a Odoo una factura por
  mes de contrato.
- **Cada mes lleva su propio estatus** y recorre la cadena completa,
  igual que un eventual: *planeado → asignado → en curso → terminado →
  sin visto bueno → en facturación → cerrado*. Cuando cierra el último
  día trabajado de septiembre, **septiembre** queda terminado y arranca
  sus relojes; octubre, ya abierto, sigue en *asignado* hasta que
  arranque. Un mes no espera al otro ni lo mueve: **abrir el mes
  siguiente es planeación**. El contrato enseña el estatus del mes que
  se opera hoy, y en la cartera cada mes aparece con el suyo (*Sep · en
  facturación · Oct · en curso*).
- **La nómina del implantado no cambia**: los días entran al corte
  semanal al terminar, sin esperar el cierre del mes (decisión 7).
- **Un día que entra o se reabre después de T0**: con el mes en
  comprobación o sin visto bueno se recalcula (T0 pasa al nuevo último
  día); con visto bueno dado, no se puede: la factura del mes ya salió.

**R9 · Bono de puntualidad.** Hoy mide "comprobó dentro de las 24 h del
fin de su día". Pasa a medir contra el nuevo límite: comprobó antes de
T0 + 24 h.

**R10 · Lo que ya está.** La regla aplica a los servicios que terminen
después del despliegue. Los ya terminados o cerrados no se tocan.

**R11 · La cancelación es un término.** Cancelar un servicio —o un mes
de implantado— pone T0 en el **momento de la cancelación** y arranca el
mismo proceso: los viáticos que ya salieron reciben límite T0 + 24 h
(el agente comprueba lo gastado o lo devuelve); en T1 el consultor
tiene sus 24 h para **revisar la cancelación** —lo trabajado, lo
devuelto, lo que se cobra—; su visto bueno manda a Odoo lo que aplique;
finanzas valida y cierra. Los días que no se trabajaron quedan
*cancelados*; los que sí, *terminados*. El servicio sale de la cartera
activa desde el momento de cancelar, pero conserva el rastro: *cancelado
· sin visto bueno · te quedan 23 h*. Si no hay nada que cerrar —sin
dinero afuera, sin días trabajados, sin compras—, propongo que se
cierre solo (decisión 8). En el implantado, cancelar a media mes cierra
ese mes con lo trabajado; los meses futuros ya abiertos se cancelan sin
nada que cerrar.

## Los casos que rompen un plazo, y cómo se evitan

1. **El día se firma tarde.** La central cierra a mano el último día
   tres días después. Con T0 = hora de término asentada, el plazo del
   agente **nacería vencido**. Propongo: si al firmar ya pasó T0 +
   24 h, el límite se pone en **firma + 24 h**. Un plazo nunca nace
   vencido (decisión 4).
2. **Un día que nadie cerró.** No hay T0, no arranca nada. Ya vive en
   *Días sin cerrar* de la central, con su botón para firmarlo. Sin
   cambio.
3. **Reabrir un día ya terminado.** Si el cierre está en comprobación o
   sin visto bueno: se permite, el servicio vuelve a *en curso*, se
   **borra el cierre y los límites**, y todo se recalcula cuando vuelva
   a terminar. Si ya tiene visto bueno: **no se puede reabrir**; la
   factura ya salió.
4. **Cancelación con dinero afuera.** Ya no queda suelta: la
   cancelación es T0 (R11). Lo entregado se comprueba o se devuelve en
   24 h y el consultor revisa la cancelación en las 24 h siguientes.
5. **Odoo caído.** No bloquea nada. Queda en *por facturar*, con
   reintento a mano y sin doble factura (el folio de Odoo se guarda y
   se revisa antes de reenviar).
6. **El reloj corre dos veces.** La tarea es idempotente: mira la fase
   actual antes de mover; correr dos veces es lo mismo que correr una.
7. **Zonas horarias.** Todo se calcula y se juzga en hora del país del
   servicio, como ya hace el reloj del consultor.
8. **Servicio de un día.** Idéntico al de tres: T0 al cerrar ese día. La
   única diferencia con hoy es que el consultor espera las 24 h del
   agente, salvo que todo cierre antes (decisión 2).
9. **El mes del implantado que acaba en fin de semana.** T0 es el
   cierre del viernes: el reloj no espera al domingo. Y si el sábado se
   trabaja como día adicional, ese sábado es el último día y T0 se
   mueve a su cierre.
10. **Contrato que se cancela a media mes.** T0 es el momento de la
    cancelación (R11); el mes cierra con lo que se trabajó y se factura
    eso; los meses futuros se cancelan sin nada que cerrar.

## Lo que cambia en el sistema

| Dónde | Qué |
|---|---|
| Estatus | Dos valores nuevos entre *terminado* y *cerrado*: **sin_visto_bueno** y **en_facturacion**, con su color en la cartera, el panorama y las tres traducciones. En el implantado el estatus deja de vivir solo en el servicio: **cada mes de contrato lleva el suyo** y el del servicio se deriva del mes en operación. *Cancelado* deja de ser final: es un término con su propio rastro. |
| Cierre | Fases: *abierto* (comprobación) → *sin visto bueno* → *enviado a facturación* → *aprobado* → *facturado*. Campos nuevos: `comprobacion_hasta` (T0 + 24 h) y `visto_bueno_desde` (T1); `limite_consultor` = T1 + 24 h. Y deja de ser uno por servicio: **uno por servicio en el eventual, uno por mes de contrato en el implantado** (`contrato_id`). Migración. |
| Implantado | El corte del mes se vuelve cierre: comparativo del mes, candados sobre las jornadas del mes, factura mensual. En el panel del mes y la cartera: el estatus de cada mes con su reloj y el botón del visto bueno. |
| Cancelación | Cancelar arranca el cierre (T0 = ahora) en vez de dejar el dinero enlistado; la revisión del consultor incluye lo devuelto y lo cobrable. |
| Reloj (Celery) | Tarea cada 5 min: mueve a *sin visto bueno* lo que llegó a T1 (o cerró todo antes), fija el límite, cambia el estatus y avisa al consultor. |
| Viáticos | El plazo se abre al terminar el servicio, no al cerrar el día; se respeta el del relevo; regla del día firmado tarde. |
| Consola | La sección *Visto bueno y facturación* dice la fase y su reloj: *Comprobación · vence en 18 h* / *Sin visto bueno · te quedan 23 h* / *En facturación · factura F-1234* / *Cerrado*. El botón solo vive en *sin visto bueno*. |
| App del personal | *"Vence en…"* aparece al terminar el servicio; antes, *"por comprobar"* sin fecha. |
| Finanzas | Aprobar cierra sin facturar (la factura ya salió); *por facturar* sigue para los reintentos. |
| Panorama (dirección) | *Dinero vencido* con el nuevo límite; *servicios sin visto bueno* con su reloj. |
| Nómina y bonos | Nómina sin cambio (entra desde *en facturación*). Bono de puntualidad contra el nuevo límite. |
| Pruebas | La 360 crece con la línea de tiempo completa: T0, T0 + 24, T1 antes por cierre temprano, visto bueno en plazo y fuera, Odoo sin conexión → por facturar, día firmado tarde, reabrir en cada fase, bono. Y la cadena del implantado: T0 del mes con el mes acabando en fin de semana, dos meses en fases distintas, un día que entra tarde, la factura del mes. |

## Lo que decides tú

1. **Relevados:** sus 24 h desde el relevo (recomiendo) o desde el
   término general.
2. **Cierre temprano:** si todos los viáticos ya cerraron antes de las
   24 h, ¿el consultor arranca de inmediato? (recomiendo que sí).
3. **Finanzas:** sigue validando después del visto bueno y es quien
   cierra el expediente y detona la comisión (recomiendo que sí), o el
   visto bueno cierra solo.
4. **Día firmado tarde:** el límite nace desde la firma, nunca vencido
   (recomiendo que sí).
5. **Los nombres en la cartera:** *sin visto bueno* y *en facturación*.
6. **T0 del mes en el implantado:** el cierre del último día trabajado
   del mes (recomiendo) o las 23:59 del último día del calendario,
   aunque no se haya trabajado.
7. **Nómina del implantado:** sigue semanal, sin esperar el cierre del
   mes (recomiendo que sí).
8. **Cancelación sin nada que cerrar** (sin dinero afuera, sin días
   trabajados, sin compras): ¿se cierra sola, sin relojes? (recomiendo
   que sí).
9. **Un eventual que cruza de mes** (del 25 de septiembre al 5 de
   octubre): ¿se corta y factura al último día de septiembre, o se
   cierra completo al terminar? Pendiente de tu respuesta.

Con tus respuestas se construye en tres sesiones: reglas, reloj y
pruebas del eventual; el cierre por mes del implantado; y consola, app,
finanzas y panorama para los dos.

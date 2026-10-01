---
id: propuesta
parte: entender
orden: 27
titulo: La propuesta del implantado
resumen: La propuesta que se le manda al cliente antes de que exista el implantado: lo que lleva al mes, sus tres modalidades, el precio especial que autoriza dirección de operaciones, el PDF y el implantado que nace de ella.
buscar: propuesta implantado ep/pro folio version mensual al mes modalidad lunes a viernes lunes a sabado mes completo 22 26 30 dias dia adicional hora extra jornada viaticos incluidos mas viaticos precio especial visto bueno direccion de operaciones lista de implantados empresa nueva pdf autorizar implantado nace alcance catalogos primer mes medio mes
---
La propuesta del implantado se arma en **Operaciones EP → Cotizaciones**, junto a la cotización del eventual, con **«Nueva propuesta»**. Sale en PDF, el consultor se la manda al cliente desde su correo y, cuando el cliente la autoriza, **nace el implantado** en EP implantado con la propuesta adentro. No se llama cotización: en la pantalla y en el PDF dice «propuesta».

## El folio y las versiones {#folio}
Cada propuesta lleva su folio —**EP/PRO-0001**— y su versión, con su propia numeración: EP/COT-0001 y EP/PRO-0001 son números distintos. Si el cliente pide un cambio, se hace la versión siguiente con lo que cambió; al mandarla, la de antes queda sustituida y solo la última se autoriza.

## Lo que lleva, al mes {#lleva}
Cada renglón es un puesto —una persona todos los días de la modalidad—, una unidad —el mes completo— o el conductor con su unidad, si la lista del cliente lo pacta en un solo precio. Cada renglón se puede nombrar como lo lee el cliente: «Conductor de seguridad bilingüe», «Toyota RAV4».

**Los precios salen de la lista de implantados del cliente en Odoo**: el mensual es su precio de día completo por los días de la modalidad. Escribir otro mensual lo vuelve **precio especial**, y lo mismo el cliente que no tiene lista o la empresa que todavía no está en Odoo: ahí los precios se escriben.

## La modalidad, los viáticos y el horario {#modalidad}
Tres modalidades:
- **Lunes a viernes · 22 días al mes**: el sábado o el domingo que se pida es día adicional.
- **Lunes a sábado · 26 días al mes**: el domingo que se pida es día adicional.
- **Mes completo · 30 días a costo fijo**: sin días adicionales. En Brasil, el 12 × 36 va así.

En las tres, **más viáticos** —cada mes se facturan los comprobados, con su desglose— o **viáticos incluidos** en el mensual. El mensual no cambia aunque el mes traiga 21 o 23 días hábiles. El **día adicional** es el precio por día de las personas; la **hora extra**, la del equipo, de la lista o escrita. La jornada es la del país si no se dice otra, y la hora de presentación no sale en el PDF: pasa al implantado. Si el servicio **empieza a medio mes**, el primer mes se cobra por día de servicio; si empieza el primer día de su modalidad —el lunes 2, con el 1 en domingo—, se cobra su mensual.

## El precio especial {#especial}
El precio que no sale de la lista de implantados del cliente lo **autoriza dirección de operaciones antes de mandarla**. El consultor escribe por qué y pide el visto bueno; le llega a dirección de operaciones por correo y en su ventana, en «Precios especiales por autorizar», con lo que pidió y lo que diría la lista. Autorizado, se prende «Descargar el PDF y marcarla enviada»; si no, el consultor lee la nota, la corrige y lo vuelve a pedir. Si después cambia un precio ya autorizado, se vuelve a pedir. Quien puede autorizarlo, al guardarla la deja autorizada de una vez.

## El PDF y mandarla {#pdf}
«Ver el PDF» la enseña como va. «Descargar el PDF y marcarla enviada» guarda el PDF tal como sale y lo descarga para mandarlo desde el correo; lo enviado ya no cambia. El PDF lleva lo que lleva al mes con su mensual, subtotal, IVA y mensual con IVA —el cliente que no lleva IVA se marca en su propuesta—, lo que se cobra aparte (día adicional, hora extra y viáticos), los días y el horario, lo que incluye y lo que no, las responsabilidades, la confidencialidad, el alcance del servicio, la aceptación, la vigencia y la firma del consultor. Los textos viven en **Catálogos → Propuesta al cliente**, por país y por idioma, y los fija dirección de operaciones; el alcance sale del de cada puesto que lleva y se puede cambiar en cada propuesta.

## Autorizada: nace el implantado {#autorizar}
Con **«La autorizó el cliente»** se registra quién, qué día y, si se tiene, el correo o el PDF firmado. Al guardar nace el implantado en EP implantado: el cliente, la ciudad, quien solicita, los días de la modalidad, la hora, el día de inicio y lo que se pactó, con la propuesta autorizada adentro. Le falta lo de cualquier alta: el ejecutivo principal, el punto fijo y quién va en qué unidad. La empresa que no estaba en Odoo, para autorizarse, ya tiene que estar en Odoo: ahí se escoge su cliente. Su **primer mes se abre con lo que el cliente autorizó** —el mensual, el día adicional, la hora extra, la jornada y los viáticos— y los meses que siguen copian al de antes. Ver [el implantado, mes por mes](#/manual/leer/implantado).

> La propuesta rechazada o vencida se lleva igual que la cotización; ver [la cotización al cliente](#/manual/leer/cotizaciones).

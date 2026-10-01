---
id: cotizaciones
parte: entender
orden: 25
titulo: La cotización al cliente
resumen: La cotización del eventual que se arma en Connect antes de que exista el servicio: su folio y sus versiones, el PDF, la autorización del cliente y el servicio que nace de ella.
buscar: cotizacion cotizar folio ep/cot version pdf enviar mandar descargar autorizar autorizada rechazada vencida sustituida borrador empresa nueva prospecto odoo lista general precios paquete iva firma condiciones catalogos servicio nace introduccion foraneo
---
La cotización del eventual se arma en **Operaciones EP → Cotizaciones**, antes de que exista el servicio. Sale en PDF, el consultor se la manda al cliente desde su correo y, cuando el cliente la autoriza, **el servicio nace solo** en EP eventual con esta misma cotización adentro. La propuesta del implantado se arma en la misma pantalla y tiene su capítulo: [la propuesta del implantado](#/manual/leer/propuesta).

## El folio y las versiones {#folio}
Cada cotización lleva su folio de Connect —**EP/COT-0001**— y su versión: V1, V2… Si el cliente pide un cambio, se hace la versión siguiente y se escribe qué cambió; al mandarla, la de antes queda **sustituida**. Solo la última se autoriza, y cada versión mandada guarda el PDF que se envió.

## Armarla {#armar}
Se escoge el cliente —o la empresa que todavía no está en Odoo—, quién la pide, el consultor que la firma, hasta cuándo es válida (el 31 de diciembre si no se dice otra cosa) y el idioma del PDF, que de entrada es el del país del cliente. Luego cada equipo: su ciudad, lo que lleva todos los días —el rol y la unidad— y sus días con su modalidad. El día que va distinto se cambia en su renglón, y el que sale de la ciudad se marca foráneo, con a dónde va. La hora no sale en el PDF: pasa al servicio. Al final, cómo se cobran los gastos —incluidos en el precio, monto fijo o por comprobar— y la introducción, que Connect escribe con los datos y se puede cambiar.

**Los precios no se teclean**: salen de la lista del cliente en Odoo, como en el cierre, y el paquete conductor + unidad sale solo si la lista lo pacta. Si sus paquetes son «Todo incluido» —con los gastos adentro—, van en paquete solo con los gastos **incluidos en el precio**; con monto fijo o por comprobar, el conductor y la unidad van a su precio de la lista y los gastos aparte, igual en el cierre. Cada día dice su precio al momento. La empresa que todavía no está en Odoo se cotiza con la **lista general de su país**.

## El PDF y mandarla {#pdf}
«Ver el PDF» lo enseña como va, en borrador. **«Descargar el PDF y marcarla enviada»** guarda el PDF tal como sale y lo descarga: el consultor se lo manda al cliente desde su correo. Lo enviado ya no cambia.

El PDF lleva la tabla de cada día con su modalidad, subtotal, IVA y total —el cliente que no lleva IVA se marca en su cotización—, la hora extra de cada rol, las modalidades, cómo se cobran los gastos, las condiciones y la firma del consultor. La razón social y el RFC de Centauro, la tasa de IVA y las condiciones viven en **Catálogos → Cotización al cliente**, por país y por idioma, y las fija dirección de operaciones; si ahí falta algo, la pantalla lo dice en amarillo al armar. Cada consultor sube su firma una vez en **Cotizaciones → Tu firma**; solo él la cambia.

## Autorizada, rechazada o vencida {#autorizar}
El cliente la autoriza por correo, como hoy. El consultor la marca con **«La autorizó el cliente»**: quién, qué día y, si lo tiene, el correo o el PDF firmado. Al guardar, Connect da de alta el servicio en EP eventual —el cliente, quien solicita, los equipos con su ciudad, sus días, su modalidad y su hora— con esta cotización **ya autorizada adentro y los mismos precios**. Le falta lo de cualquier alta: el principal de cada equipo y el punto de inicio. La empresa nueva, para autorizarse, ya tiene que estar en Odoo: ahí se escoge su cliente, porque de Odoo sale la factura.

Si el cliente dice que no, «La rechazó» con su motivo. Pasado su «válida hasta», el reloj la deja **vencida** pasada la medianoche; una vencida todavía se puede autorizar si el cliente la acepta.

> Si un cambio llega con el servicio ya armado, se recotiza en el servicio, en «La cotización autorizada», y sigue con el mismo folio. Ver [el camino de un servicio](#/manual/leer/camino).

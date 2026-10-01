---
id: sintoma-cierre-no-sale
parte: resolver
orden: 520
area: Dinero
titulo: El visto bueno no sale y el servicio no llega a facturación
buscar: cierre visto bueno no sale mandar a facturar prefactura no se pudo mandar odoo no contesto finanzas puntos por corregir cotizacion autorizada jornada sin termino viaticos sin cerrar tipo de cambio desviacion regresado plazo vencido factura por facturar
---
### Qué ves
En la tarjeta **Visto bueno y facturación** del servicio, «Antes de mandarlo» dice que hay puntos por corregir; o el botón **Dar visto bueno y mandar a facturar** no aparece.

### Por qué pasa
**Todavía corre la comprobación.** Durante las 24 horas del personal el visto bueno no se abre. Se abre al vencer ese plazo, o antes si todos ya cerraron sus viáticos.

**Quien lo ve no da el visto bueno.** Lo da el consultor titular o dirección de operaciones; un puesto que solo cotiza lo deja listo.

**Hay puntos por corregir.** Son los únicos que frenan; lo que sale en «Para revisar» no frena:
- **Viáticos sin cerrar.** A alguien le faltan comprobantes por revisar, tiene un depósito autorizado sin depositar o una devolución que finanzas no confirma, o ya cuadra y falta cerrarlo.
- **Jornada sin término.** Un día sin su marca de fin.
- **Una desviación contra lo cotizado.** Días de más o de menos, un recurso que no se cotizó, viáticos excedidos, un cobro menor.
- **Sin tipo de cambio.** Los gastos se comprobaron en pesos y se facturan en dólares.
- **Sin cotización autorizada.** Sin ella no hay contra qué comparar lo ejecutado.

### Cómo se arregla
Cada punto dice su acción:
- Los viáticos se cierran abajo, en Viáticos del personal. Si su plazo ya venció, lo que no comprobó se cierra con descuento a su nómina.
- El día sin fin lo registra la central, con su justificación.
- La desviación se recotiza con el cliente —«Recotizar», en La cotización autorizada— o se justifica.
- El tipo de cambio lo pone finanzas en Facturación → Tarifarios.
- La cotización autorizada la registra el consultor del servicio, o quien lo cubre, arriba en el mismo servicio: en **La cotización autorizada**.

### Y después del visto bueno
- **Finanzas lo regresa** con su motivo: hay 24 horas desde el regreso para corregir y volver a mandarlo. Lo en plazo del primer visto bueno se queda como estaba.
- **La prefactura no sale a Odoo.** El visto bueno ya quedó: el servicio —o el mes— espera en Facturación → «No se pudo mandar» con lo que pasó —Odoo no contestó, falta un dato, la anterior sigue viva en Odoo— y se vuelve a intentar solo cada hora; finanzas lo aprueba igual. Sin la llave de la factura, todo lo aprobado espera en «Por facturar» y la factura se hace en Odoo.
- **Se pasó el plazo.** No frena: el servicio se factura igual, pero la comisión de ese servicio se pierde.

> **La causa de fondo:** el visto bueno es la puerta al dinero: lo que pasa por ella se factura y se paga. Por eso no deja pasar nada que todavía se mueva —un viático abierto, un día sin fin, un precio sin respaldo—.

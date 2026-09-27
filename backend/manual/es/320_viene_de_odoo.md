---
id: sintoma-viene-de-odoo
parte: resolver
orden: 320
area: Odoo
titulo: No me deja editar un dato: dice que viene de Odoo
buscar: viene de odoo se corrige en odoo no deja editar catalogo nombre placa rfc tarifario lista de odoo
---
### Qué ves
Al editar una persona, una unidad o un cliente en Centauro, el sistema dice **«Viene de Odoo: se corrige en Odoo»**. O, en un tarifario, que es una lista de Odoo.

### Por qué pasa
Lo que viene de Odoo no se edita en Centauro, a propósito: si se pudiera, la siguiente lectura lo volvería a dejar como dice Odoo, y habría dos versiones del mismo dato. Desde que los tarifarios se leen de Odoo, el tarifario de un cliente de Odoo también se corrige allá.

### Cómo se arregla
Se cambia en Odoo —Recursos Humanos en la ficha del empleado, Flota en la de la unidad, Finanzas en la del cliente o en su lista de precios— y Centauro lo toma en la siguiente lectura. Lo que es de Centauro —a qué servicio va alguien, con qué rol, sus viáticos— se sigue editando aquí.

> **La causa de fondo:** una sola fuente de verdad. Lo que viene de Odoo se corrige una vez, allá.

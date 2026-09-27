---
id: sintoma-unidad-ocupada
parte: resolver
orden: 120
area: Personas y unidades
titulo: Una unidad sale ocupada o no aparece
buscar: unidad vehiculo camioneta ocupada no aparece taller servicio preventivo correctivo categoria placa
---
### Qué ves
Al asignar la unidad de un equipo, la que buscas no sale, o sale **Ocupado** con un motivo.

### Por qué pasa · de lo más común a lo menos
1. **Está en el taller.** El motivo dice «En el taller desde el …». Sale de Flotilla → Servicios en Odoo: las entradas de tipo Preventivo, Correctivo o Desgaste natural sacan la unidad de la fecha de entrada a la de salida, y **sin fecha de salida se da por adentro**.
2. **Ese día ya va en otro servicio** a la misma hora o en un día completo.
3. **No sale en la lista:** es de otra categoría que la que se está buscando, está dada de baja, o todavía no llega de Odoo —le falta la etiqueta «PROTECCION EJECUTIVA» o «pe», la placa, la categoría o su Ubicación—.
4. **Es de otra ciudad:** sale con traslado.

### Cómo se arregla
Si ya salió del taller, Flota le pone la **fecha de salida** a su servicio en Odoo, y la unidad vuelve a ofrecerse en la siguiente lectura de la flota, a los :27. Lo que falte en su ficha, igual, en Odoo.

> **La causa de fondo:** un servicio de taller sin fecha de salida deja la unidad adentro para siempre. Es el olvido más común.

---
id: sintoma-cerrar-acceso
parte: resolver
orden: 250
area: Accesos
titulo: No se le puede cerrar el acceso a alguien
buscar: cerrar acceso baja viaticos sin cerrar debe dinero no se puede cerrar
---
### Qué ves
Al cerrarle el acceso a alguien, el sistema dice que tiene viáticos sin cerrar.

### Por qué pasa
Tiene dinero que todavía no comprueba. Si se le cierra el acceso, ya no puede subir sus comprobantes desde la app, y ese dinero se quedaría sin cuadrar. Por eso, cuando Odoo lo da de baja, su acceso se queda abierto hasta que compruebe.

### Cómo se arregla
Tiene que terminar su ciclo: comprobar lo que recibió. Si ya no va a volver, finanzas lo cierra con su ajuste, y entonces el acceso se puede cerrar.

> **La causa de fondo:** el acceso se cierra cuando la persona ya no debe nada. Es el mismo candado en Accesos que en la baja de Odoo.

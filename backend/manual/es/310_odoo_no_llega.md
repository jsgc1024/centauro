---
id: sintoma-odoo-no-llega
parte: resolver
orden: 310
area: Odoo
titulo: Algo que se corrigió en Odoo no llega a Centauro
buscar: odoo no llega no se actualiza correccion lectura pendiente llave vencio no contesta etiqueta cliente primera lectura
---
### Qué ves
Recursos Humanos, Flota o Finanzas ya corrigieron algo en Odoo, y en Centauro sigue igual.

### Por qué pasa · de lo más común a lo menos
1. **Todavía no toca la lectura.** Cada una corre una vez por hora, en su minuto: el personal a los :17, la flota a los :27, la oficina a los :37, los clientes a los :47 y los tarifarios a los :57.
2. **Esa lectura nunca se ha aplicado a mano.** La de cada hora espera a que alguien haga la primera, después de ver el ensayo. En el [reloj](#/manual/reloj) sale «Espera la primera lectura a mano».
3. **El caso quedó en pendientes.** Lo dudoso no se adivina: si le falta algo —una ciudad, un correo, una placa— se reporta y no se toca.
4. **Es un cliente sin la etiqueta «Protección ejecutiva».** Sin ella, Centauro ya no le lee cambios.
5. **La llave de Odoo venció**, o el servidor no la tiene. Dura unos tres meses. Lo dice el [estado del sistema](#/manual/atorado), y el reloj lo marca con error.

### Cómo confirmarlo
En [Odoo](#/odoo), el **Ensayo** de esa lectura: lee Odoo en ese momento, dice qué cambiaría y qué queda pendiente, y no guarda nada.

### Cómo se arregla
- Si solo falta que toque: esperar a su minuto, o hacer el ensayo y aplicar.
- Si quedó pendiente: corregir en Odoo lo que dice el ensayo.
- Si la llave venció: Salvador pone una nueva en el servidor.

> **La causa de fondo:** Centauro nunca escribe en Odoo y nunca adivina. Lo que no llega, o no le ha tocado, o Odoo lo tiene incompleto.

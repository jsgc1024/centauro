---
id: sintoma-correo-cliente
parte: resolver
orden: 610
area: Correo y avisos
titulo: Un correo no le llegó al cliente
buscar: correo no llego cliente ejecutivo solicitante aviso equipo en el lugar servicio iniciado terminado task sheet encuesta apagado vencido sin correo fallo spam corregir contactos mal escrito rebota
---
### Qué ves
El ejecutivo o quien pidió el servicio dice que no le llegó el aviso: el equipo en el punto, el servicio iniciado o terminado, el task sheet, un cambio de equipo o la encuesta.

### Por qué pasa · de lo más común a lo menos
1. **El correo está apagado.** Mientras no se encienda no sale ninguno: los avisos esperan.
2. **Pasaron más de 24 horas.** Un aviso operativo que no salió en 24 horas ya no sale, y tampoco el que lleva un enlace que ya venció. Un «su equipo está en el lugar» de hace días hace dudar de todo el sistema. La invitación de acceso, la recuperación de contraseña y la encuesta viven lo que vive su enlace (72 horas, 2 horas y 15 días): salen aunque el correo se encienda dos días después. Si el proveedor no contesta, el aviso espera y vuelve a intentar mientras viva; lo que sí falló se regresa a la cola con «Reintentar los que fallaron», en el estado del sistema.
3. **No tenía a dónde ir.** Al servicio le falta el correo del ejecutivo o el de quien lo pidió: el aviso se aparta.
4. **La dirección está mal escrita** o el servidor del cliente lo rechazó. Se intenta cinco veces y queda como fallido, con lo último que dijo el proveedor.
5. **Le llegó a otra carpeta**: correo no deseado o promociones.
6. **Ese aviso no se manda ese día.** Un cambio de equipo va por correo solo si es del día en curso; el de otro día viaja en el task sheet.

### Cómo confirmarlo
El [estado del sistema](#/manual/atorado) dice si el correo está encendido, cuántos avisos esperan y cuántos fallaron. En el servicio, **Corregir los contactos** —arriba, junto al estatus— muestra el correo del ejecutivo y el de quien lo pidió, tal como están.

### Cómo se arregla
- **Apagado:** lo enciende Salvador en el servidor.
- **Otra carpeta:** que el cliente marque el correo como seguro.
- **Sin correo o mal escrito:** el consultor del servicio —o quien lo cubre— lo corrige en **Corregir los contactos**, mientras el servicio no esté cerrado ni cancelado. Los avisos que no han salido y la encuesta sin contestar se van a la dirección nueva, y queda en la bitácora del servicio con lo de antes. Si el correo de antes está en otro servicio abierto del cliente, al guardar se dice en cuál.
- Lo que ya venció no se vuelve a mandar: de eso ya pasó el momento.

> **La causa de fondo:** «no se mandó» y «no le llegó» son dos cosas distintas. El sistema dice cuál fue, y nunca manda tarde lo que ya no sirve.

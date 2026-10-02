---
id: piezas
parte: entender
orden: 10
titulo: Las piezas del sistema y cómo se hablan
resumen: La consola, la app de campo, el servidor, el reloj, Odoo, el GPS, el correo y los avisos al teléfono. Casi todo lo que se atora vive en una de estas piezas.
buscar: arquitectura servidor google cloud base de datos redis worker beat odoo pegasus amazon ses correo push respaldo archivo
---
Centauro Connect no es un solo programa: son varias piezas que se pasan datos. Cuando algo se atora, la primera pregunta es **en qué pieza**, y la segunda, **qué le llegó o qué le faltó**.

## Lo que se ve

### La consola
Donde trabaja la oficina, en **mycentauro.lat**: la operación, el dinero, los accesos, Odoo, los catálogos, la calidad y este manual. Cada quien ve el menú de su puesto; lo que puede hacer adentro sale de sus actividades (ver [quién puede qué](#/manual/permisos)).

### La app de campo, EP Connect
La del personal de seguridad, en el teléfono, en **appep.mycentauro.lat**. Ahí ve su día, marca su llegada, el contacto con el ejecutivo y el fin, sube sus comprobantes y tiene el botón de pánico. Entra con su **correo personal** y pone su contraseña con un **código de cuatro dígitos** que le dicta su consultor o la central.

## Lo que no se ve

### El servidor
Una máquina en Google Cloud, en Querétaro, con el reloj en hora de México. Ahí viven la API —la que contesta a la consola y a la app—, la base de datos y el reloj. Cada noche a las 2:30 se saca el respaldo de la base, y a las 3:00 se toma la foto del disco.

### El reloj
Veinte tareas que corren solas: leer el GPS cada dos minutos, sacar los correos cada cinco, avanzar los cierres, leer Odoo cada hora, el corte del lunes, las estrellas del mes. Cada tarea anota su última vuelta: en [lo que el sistema hace solo](#/manual/reloj) se ve cuándo corrió cada una. Si el reloj se para, deja de pasar todo lo que pasa solo, aunque la consola siga abriendo.

### Odoo
La fuente de verdad del personal de seguridad, de la oficina, de la flota y el taller, de los clientes y de los tarifarios. Centauro **lo lee**, y lo único que escribe en él es la prefactura en borrador que sale con el visto bueno: lo que viene de Odoo se corrige en Odoo, y llega solo en la siguiente lectura. Ver [lo que viene de Odoo](#/manual/leer/odoo).

### El GPS
Pegasus, de Centauro Satelital. Con servicios en la calle, cada dos minutos se leen las unidades: el pánico, el camino al punto, la corriente y el segundo testigo de las marcas. Sin nadie en la calle, cada quince, solo para saber cuál reporta. Cada unidad de Pegasus se liga sola con la de Centauro **por la placa**, y la placa sale de la flota de Odoo: sin la flota leída, no liga ninguna.

### El correo
Sale de **connect@mycentauro.lat** por Amazon SES, y las respuestas llegan a cecc.notification@centauro.lat. Lleva las invitaciones y las recuperaciones de contraseña, los avisos a los clientes y las encuestas. Se escribe al momento y sale cada cinco minutos; el aviso operativo que tiene más de 24 horas sin salir ya no sale, y la invitación, la recuperación y la encuesta viven lo que vive su enlace. Mientras el correo esté apagado, nada sale y todo espera.

### Los avisos al teléfono
Los recordatorios y alertas que llegan al teléfono aunque la app esté cerrada. Necesitan dos cosas: las llaves puestas en el servidor, y que cada teléfono los haya aceptado.

### El archivo de comprobantes
Tres meses después de facturado un servicio, las fotos de sus comprobantes se mudan al archivo, a la 1:30 de la mañana. Siguen disponibles; solo cambian de lugar.

> La causa de fondo de casi todo lo que se atora está en una de estas piezas: un dato que falta en Odoo, el reloj parado, el correo apagado, una placa que no liga o un teléfono sin avisos. El [estado del sistema](#/manual/atorado) las revisa todas de un vistazo.

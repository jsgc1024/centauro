---
id: sintoma-reloj-parado
parte: resolver
orden: 440
area: Operación
titulo: Varias cosas dejaron de pasar solas al mismo tiempo
buscar: reloj parado worker beat redis nada pasa solo correos no salen cierres no avanzan odoo no lee gps no lee
---
### Qué ves
A la vez: los correos no salen aunque el correo está encendido, los cierres no avanzan, Odoo no se lee, el GPS se quedó quieto, la víspera no llegó. La consola sí abre.

### Por qué pasa
**El reloj está parado.** Las veinte tareas que corren solas dependen de dos procesos del servidor —el que marca la hora y el que hace el trabajo— y de Redis. Si uno se cae, la consola sigue abriendo, pero nada pasa solo.

### Cómo confirmarlo
El [estado del sistema](#/manual/atorado) dice **Parado** y cuándo fue la última vuelta. En [lo que el sistema hace solo](#/manual/reloj) se ve la última vuelta de cada tarea.

### Cómo se arregla
Se le avisa a Salvador: él revisa los procesos del servidor y vuelve a levantar el reloj. Está en la guía de despliegue, en «Qué mirar cuando algo falle».

> **La causa de fondo:** cuando muchas cosas fallan juntas, la causa casi nunca es cada una: es lo que tienen en común.

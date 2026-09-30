---
id: camino
parte: entender
orden: 20
titulo: El camino de un servicio eventual
resumen: Del alta a la factura, la nómina, la comisión y el bono. Cada paso dice quién lo mueve: una persona o el reloj.
buscar: alta cotizacion asignar equipo task sheet vispera llegada contacto meet and greet en curso horas extra fin viaticos visto bueno cierre finanzas factura encuesta nomina comision bono estrellas cancelar cobro incidencia titular cambiar unidad deshacer hora de manana
---
Un servicio eventual pasa por los mismos pasos siempre. Saber en qué paso está y **quién lo mueve** —una persona o el reloj— es la mitad de resolver cualquier atorón.

## Antes del día

1. **El alta.** El consultor da de alta el servicio: el cliente, quién lo solicita, el ejecutivo que se protege, los días, la ciudad y la modalidad de cada día —día completo, medio día o transfer—. Sale con su folio, EP/E-001, y queda programado. Si después sale mal escrito un correo o un teléfono, o pide el servicio otra persona, se corrige en el servicio con **Corregir los contactos**.
2. **La cotización.** Sale del tarifario del cliente: el de su lista de Odoo, o el de Centauro mientras los tarifarios de Odoo no estén en marcha. Mientras Odoo no la manda, el consultor —o quien lo cubre— la registra en el servicio, en **La cotización autorizada**, debajo del encabezado: qué lleva cada día, cómo se cobran los gastos y quién la autorizó del lado del cliente, el día y, si se hizo en Odoo, su folio. Los precios no se teclean. Se guarda ya autorizada; si el cliente cambia algo antes del visto bueno se recotiza con su motivo, y después lo regresa finanzas. Una cotización en otra moneda lleva su tipo de cambio; sin él no se autoriza. Sin la cotización autorizada por el cliente, el servicio no se puede mandar a facturar.
3. **El equipo.** El consultor asigna gente y unidades a cada equipo. El calendario cuida que nadie se empalme: quien ya trabaja a esa hora sale **Ocupado**, quien tiene menos de dos horas entre un servicio y otro sale **Con riesgo**, y quien es de otra ciudad sale con **traslado**. La unidad en el taller no se ofrece. Quitar a alguien —o una unidad, o un día— solo toca lo que no ha arrancado: el día que ya se trabajó se queda con sus marcas y su pago, y si hay que sacar a alguien que ya está en la calle, eso es un cambio por contingencia. La unidad también se cambia por contingencia, con **Cambiar** en la unidad: desde qué día, por qué y cuál entra; al cliente no se le avisa, la hoja se vuelve a publicar sola y el equipo recibe el aviso. Un cambio recién hecho —de persona o de unidad— se deshace con **Deshacer** mientras siga en curso y el dinero no se haya movido. Si el consultor titular se va de vacaciones o cambia de cartera, dirección de operaciones lo cambia desde la ficha con **Cambiar titular**: desde ese momento los avisos, los plazos y la comisión son del nuevo.
4. **El task sheet.** La hoja del servicio para el cliente: quién va, con su teléfono, en qué unidad, a qué hora y dónde. Se libera cuando todos los días tienen su gente y su unidad.
5. **La víspera.** A las 5 de la tarde de su país, el reloj le recuerda a cada quien que mañana trabaja, y cada quien confirma desde su app.

## El día

6. **Próxima a iniciar.** Dos horas antes, el reloj la pasa a próxima a iniciar y la central toma el seguimiento.
7. **El camino al punto.** Cada cinco minutos el reloj revisa quién va en camino y a quién hay que tocarle la puerta.
8. **La llegada.** Cada persona marca su propia llegada dentro del punto. El día pasa a **arribado** con la primera, y el ejecutivo y el solicitante reciben una sola vez el aviso de que el equipo está en el lugar, con sus teléfonos; la central ve quién no ha llegado y el camino lo sigue tocando hasta que marque. La marca que llega más de 15 minutos después de la hora citada la revisa la central. El servicio de madrugada acepta la llegada desde tres horas antes de la hora de estar en el punto, aunque sea desde la víspera; el día que todavía no llega no acepta marcas.
9. **El contacto.** El meet and greet **arranca el día**: pasa a **en curso** y desde esa hora corren las horas. Si se les pasó marcarlo, la central lo registra a mano.
10. **En curso.** Si el servicio pasa dos horas sin reportar, la central recibe una alerta de silencio; esperando al principal, el equipo puede decir **En espera** para que no salte. La alerta se cierra sola cuando el equipo vuelve a reportar, con quién y a qué hora. El servicio que cruza la medianoche sigue en la app hasta que termina. A quien relevaron por contingencia la app se lo dice y su día ya no le sale: lo que marque después de la hora del relevo no entra.
11. **Las horas extra.** Treinta minutos antes de que se cumplan las horas contratadas, sale el aviso.
12. **El fin.** El personal marca el fin del servicio. El solicitante recibe el aviso con las horas extra del día y a qué hora es el siguiente. La hora de mañana que dice el principal al cerrar el día queda como **propuesta**: la central la confirma o deja la de la hoja desde «Mañana», y a las 22:00 del país el reloj confirma lo que nadie tocó.
13. **La incidencia.** Lo que salió mal con alguien del equipo se registra desde la ficha del servicio con **Registrar incidencia** —el consultor, quien lo cubre o la central— y dirección de operaciones lo autoriza o lo descarta desde su pantalla; la leve quita las estrellas del mes y la grave retiene la comisión y la ve Recursos Humanos.
14. **La cancelación.** Si el cliente cancela con el equipo en la calle, ese día termina a la hora de la cancelación y se paga; los días que no habían arrancado se cancelan. Al cancelar se elige cobrar **completo** (la cotización autorizada) o **lo ejecutado**, y dirección de operaciones lo autoriza desde la tarjeta del cierre.

## Después del día

15. **Los viáticos.** El personal tiene 24 horas desde que termina el servicio para comprobar lo que recibió. En un servicio cancelado, en facturación o cerrado ya no entra dinero nuevo; lo pedido antes se deposita y se comprueba como siempre.
16. **El visto bueno.** Al vencer esas 24 horas —o antes, si todo el dinero ya cerró— el reloj pasa el servicio a esperar el visto bueno del consultor, que tiene sus propias 24 horas. Ese plazo decide su comisión: a la mitad le llega un aviso, y al vencer, a él y a dirección de operaciones, por correo y al teléfono; el servicio sigue esperando su visto bueno, ya sin comisión.
17. **Finanzas.** El consultor lo manda a finanzas, que lo factura o se lo regresa con el motivo escrito. Mientras la factura no está conectada con Odoo, finanzas la hace allá y la anota aquí con su folio y su fecha. Lo regresado tiene 24 horas para volver.
18. **La encuesta.** Al cerrar el servicio salen dos encuestas: al ejecutivo y a quien lo solicitó. El reloj le recuerda a quien no contesta a los 5 días, y la encuesta vence a los 15.

## El dinero de la gente

19. **La nómina.** Cada lunes a las 7:00 de su país el reloj arma el borrador del corte, y a las 11:00 queda listo para pagar. El eventual entra con el visto bueno del consultor; el que todavía no lo tiene sale en «Todavía no entra». El corte que no se pagó sigue a la vista hasta pagarse, y si llega al lunes siguiente el corte nuevo se lo lleva.
20. **La comisión del consultor.** El 3 % de lo facturado en eventuales y el 1 % en implantados, sin gastos ni impuestos. Se pierde la del servicio que no se cerró a tiempo.
21. **El bono.** El día 3 de cada mes el reloj calcula las estrellas del mes que acaba de cerrar: el día 3 y no el 1, porque el viático del último día todavía tiene 24 horas para comprobarse.

> Cuando algo no avanza, primero se ve en qué paso está y si ese paso lo mueve una persona o el reloj. Si lo mueve el reloj y no se movió, el [reloj](#/manual/reloj) dice cuándo fue su última vuelta.

---
id: sintoma-no-cotiza
parte: resolver
orden: 510
area: Dinero
titulo: Un cliente no tiene precio: sin tarifario, «sin precio» o sin tipo de cambio
buscar: cotizar cotizacion precio sin precio tarifario lista de precios cliente sin tarifario rol unidad paquete modalidad producto confirmar tipo de cambio dolares
---
### Qué ves
Una de estas: el cliente **no tiene tarifario**; en su tarifario un rol, una unidad o un paquete dice **«sin precio»**; el cierre se detiene con «El tarifario no tiene precio para … en …»; o una cotización en dólares no se autoriza porque **no hay tipo de cambio**.

### Por qué pasa · de lo más común a lo menos
1. **El cliente llegó de Odoo sin tarifario.** Lo toma de su lista de Odoo en la lectura de los tarifarios; mientras eso no esté en marcha, se le pone a mano.
2. **Su lista no tiene ese precio.** Se cobra el rol con el que fue cada quien ese día, la categoría de la unidad y la modalidad de ese día. Si la lista del cliente no lo pacta, ni lo toma de la general de su país o del «Precio de venta» del producto, queda «sin precio».
3. **El producto no está confirmado.** Solo pone precio lo que finanzas ya confirmó en la tabla de productos: lo sugerido no cuenta, porque un precio mal leído se cobra.
4. **Alguien va sin rol.** Sin rol no hay precio que buscar: el sistema pide decir con qué rol va.
5. **El cliente paga en dólares y no hay tipo de cambio.** Sin él no se autoriza la cotización ni se facturan los gastos. Hoy solo se convierte de dólares a pesos mexicanos.
6. **Su lista de Odoo no tiene precios que Centauro sepa leer.** No se le cambia: se queda con el tarifario que tenía y sale en pendientes.

### Cómo confirmarlo
Debajo del encabezado de cada servicio, quien cotiza y cierra ve **el tarifario del cliente**, cada precio con su origen: en negro lo que pacta su lista; en gris lo que toma de la general, de otra lista o del «Precio de venta»; y «sin precio» lo que no se puede cobrar. Es el mismo que está en Facturación → Tarifarios.

### Cómo se arregla
- **Sin tarifario:** en [Odoo](#/odoo), en «Clientes sin tarifario», se escoge el tarifario y se pone, uno por uno o a todos los de un país de una vez.
- **Sin precio:** se corrige en Odoo, en su lista de precios, y llega en la lectura de los tarifarios, a los :57.
- **Producto sin confirmar:** finanzas lo confirma en Facturación → Tarifarios, en la tabla de productos.
- **Sin rol:** el consultor dice con qué rol va esa persona.
- **Sin tipo de cambio:** finanzas lo pone en Facturación → Tarifarios. Aplica para todo lo que venga; lo que ya quedó fijo no se mueve.

> **La causa de fondo:** Centauro no inventa precios. Todo lo que cobra sale de la lista del cliente en Odoo, leída cada hora, y lo que no está ahí no se puede cobrar.

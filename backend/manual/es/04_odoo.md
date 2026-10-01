---
id: odoo
parte: entender
orden: 40
titulo: Lo que viene de Odoo
resumen: Las cinco lecturas —personal de seguridad, flota y taller, oficina, clientes y tarifarios—, qué trae cada una, cuándo corre y qué deja pendiente. Y la prefactura en Odoo, del eventual y del mes del implantado.
buscar: odoo lectura ensayo aplicar primera lectura pendientes llave etiqueta proteccion ejecutiva brasil compania centauro ass centauro brasil por capturar sin ciudad cuv blindada plaza ubicacion correo personal correo de trabajo tarifarios productos lista de implantados baja archivado categoria proteccion ejecutiva PE prefijo gps atlas idioma es_MX factura prefactura borrador timbrar facturista variante variantes gastos de operacion viaticos llave de la factura ODOO_FACTURACION_API_KEY hora extra producto mes implantado referencia origen no se pudo mandar en odoo mandar a odoo reintento cancelada a la mitad compania de la factura centauro ass centauro brasil
---
Odoo es la fuente de verdad. Centauro **lo lee** —lo único que escribe en él es la prefactura en borrador, abajo—, y lo que viene de Odoo no se edita en Centauro: se corrige allá y llega solo en la siguiente lectura. Tres reglas valen para las cinco lecturas:

- **La primera se hace a mano**, en [Odoo](#/odoo): primero el **Ensayo**, que lee y dice qué haría sin guardar nada, y si cuadra, **Aplicar**. Desde ahí se lee sola cada hora. Mientras no se haga la primera, la de cada hora no arranca.
- **Lo dudoso no se adivina.** Lo que no cuadra se reporta como pendiente y no se toca. El ensayo dice qué le falta a cada caso.
- **La llave es el número interno de Odoo.** La primera vez, lo que ya estaba en Centauro se reconoce por su correo, su placa o su RFC.

## El personal de seguridad · cada hora a los :17
Entra quien tiene en Odoo el puesto «Personal de Seguridad» o «Security Driver». Trae su nombre, su ciudad —de la **ubicación de trabajo**, y el Estado de México cuenta como Ciudad de México—, su celular, su correo personal, su número de empleado, su fecha de ingreso, su foto y su cuenta bancaria (número, banco y titular de su **cuenta principal**, de la ficha del empleado en Odoo: aquí no se captura; si no se puede leer, la lectura dice si es que falta el permiso o que esa versión de Odoo no tiene el campo, y no toca nada). El círculo con iniciales que Odoo le pone a quien no tiene foto no es una foto: no se guarda. Entra a la app con su **correo personal**.
Si Odoo lo archiva, se le da de baja: su acceso se cierra —salvo que deba viáticos, que primero comprueba—, y la central recibe una alerta por cada día que tenía asignado.

## La flota y el taller · cada hora a los :27
Cada país lee su flota, y nunca se mezclan: **México**, las unidades de la compañía **CENTAURO ASS** con la etiqueta «PROTECCION EJECUTIVA» o «pe»; **Brasil**, las de la compañía **Centauro Brasil** con «PROTECCION EJECUTIVA BRASIL». La etiqueta de un país con la compañía de otro no entra en ninguna: queda pendiente, y la unidad que ya estaba no se mueve de país sola. Trae la placa, la categoría —las de Odoo son las de Centauro, con la **CUV Blindada** que usa Brasil—, la ciudad de su **Ubicación**, buscada entre las ciudades de su país, la marca, el modelo, el color y el año.
En México la unidad sin Ubicación queda pendiente. En Brasil entra igual: su color y su Ubicación se capturan después en Odoo, y mientras tanto la lectura los dice en **Por capturar**, sin detener nada. Sin ciudad, la unidad se ofrece en los eventuales de Brasil como «sin ciudad» y no va a un implantado; su GPS se liga igual. Connect no lee el VIN. Si el ensayo dice **Brasil 0** con sus unidades cargadas en Odoo, al usuario de la conexión le falta la compañía Centauro Brasil en sus compañías permitidas.
Del taller, las entradas de Flotilla → Servicios de tipo Preventivo, Correctivo o Desgaste natural sacan la unidad de circulación de la fecha de entrada a la de salida; **sin salida se da por adentro**. Si Odoo archiva la unidad, deja de ofrecerse y la central recibe una alerta por cada día que tenía asignado. Si solo le quitan la etiqueta, queda pendiente.

## La oficina · cada hora a los :37
Es de oficina todo empleado que no es de seguridad. Entra con su **correo de trabajo**: sin él no llega. Llega la persona, no su acceso: el acceso lo da Recursos Humanos en [Accesos](#/accesos), con el puesto que Centauro le sugiere por su puesto de Odoo. Si Odoo la archiva, su acceso se cierra.

## Los clientes · cada hora a los :47
Son las empresas con la etiqueta **«Protección ejecutiva»**: así no llegan los de GPS ni los de carga. Traen su nombre, su RFC y su país. Sin RFC llegan igual, pero no se les puede facturar. Si Odoo archiva al cliente, deja de ofrecerse para un servicio nuevo; si solo le quitan la etiqueta, queda pendiente y Centauro ya no le lee cambios.

## Los tarifarios · cada hora a los :57
Cada país tiene su lista general —la que trae su grupo de países en Odoo— y el cliente que negoció tiene la suya, puesta en su ficha. La de sus implantados va en el campo «Lista de implantados». Solo se lee lo de Protección Ejecutiva (sección 112): las listas cuyo nombre empieza con **«PE ·»** —«PE · General México», «PE · Control Risks»— y los productos de la categoría **«Protección Ejecutiva»** de Odoo, con sus subcategorías. El GPS, la Central de Inteligencia y ATLAS ya no llegan. Los nombres se leen en español de México. Tres cuidados:
- Solo pone precio lo que finanzas ya **confirmó** en Facturación → Tarifarios: un precio mal leído se cobra.
- A un cliente no se le cambia a una lista de la que Centauro todavía no sabe leer ningún precio: se queda con el tarifario que tenía. Si su lista no empieza con «PE ·», tampoco: queda en pendientes para ponerle su lista de PE en Odoo.
- Si la categoría «Protección Ejecutiva» no está en Odoo no se lee nada: leer todo sería volver a traer el GPS.

De cada producto se lee también la **variante** con que Odoo lo factura; si en Odoo tiene varias, los pendientes lo dicen, porque la factura no sabría con cuál cobrar. Y cada precio de hora extra guarda de qué producto salió: el de la hora extra de su rol o el de la de todos.

## La prefactura en Odoo {#factura}
Lo único que Connect escribe en Odoo es la **prefactura**: con el visto bueno del consultor —del servicio eventual o del mes del implantado— sale al momento una factura de cliente en borrador, que el facturista revisa, confirma y timbra allá. Va con su propia llave —la de la factura, aparte de la de leer— y esa conexión solo sabe crear el borrador: no lo confirma, no lo timbra, no lo cambia después y no lo borra. La pantalla de [Odoo](#/odoo) dice si el servidor ya tiene esa llave; sin ella no sale ninguna, y la factura se hace en Odoo y se anota con «Ya se facturó en Odoo», como antes.
- **Lo de arriba:** la compañía, la del país del servicio —**CENTAURO ASS** en México y **Centauro Brasil** en Brasil—; el cliente de su ficha en Odoo, la moneda de la cotización —o de los precios del mes— y la referencia: el folio del servicio, «EP/E-031», o el folio y el mes, «EP/IM-004 · 11/2026». Su documento de origen empieza con «Connect»: con él la encuentra el facturista —el filtro «Prefacturas de Connect»— y con él Connect se asegura de no mandar dos.
- **El eventual:** un renglón por día, equipo y lo que se cobra, con el producto de Odoo de su precio en la lista del cliente; la hora extra, con el de su rol; la cancelación que se cobra completa, con la cotización tal cual y su nota.
- **El mes del implantado:** un renglón por puesto y por unidad, como en la propuesta, cada uno con su producto. El mes que empieza o que se cancela a la mitad va por día de servicio —el mensual entre los días de su modalidad—, y el centavo que sobra al repartirlo va en el último renglón. El día adicional, al precio del día de las personas; la hora extra, con el producto de la de su rol. Si los precios del mes se escribieron a mano, sin desglose, va un solo renglón con el producto del puesto principal.
- **Los gastos,** en un solo renglón con **«Gastos de Operación (Viáticos)»**, que entra a la tabla de productos aunque no sea de la categoría de Protección Ejecutiva —moverlo de categoría en Odoo le cambiaría su cuenta contable— y la tabla lo marca con «Factura los gastos». El IVA lo pone Odoo con el impuesto de cada producto.

Si no sale —Odoo no contestó, falta un dato, la de antes de regresarlo sigue viva en Odoo— el visto bueno se queda, y el servicio o el mes espera en Facturación → «No se pudo mandar» con su porqué; se vuelve a intentar solo cada hora, sin duplicar. Lo que se manda es lo que el consultor aprobó: si después del visto bueno cambia un precio de la lista o un día, no sale. Lo que tuvo su visto bueno antes de la llave no sale solo —pudo haberse facturado a mano—: finanzas lo manda con «Mandar a Odoo» o lo anota con «Ya se facturó en Odoo». Si finanzas regresa un servicio con su prefactura ya en Odoo, esa se queda allá y la cancela el facturista; la nueva sale cuando ya esté cancelada. Por ahora finanzas sigue aprobando en Connect, y la timbrada se anota con «Ya se facturó en Odoo».

> Casi todo lo que «no llega de Odoo» es una de tres cosas: la lectura nunca se aplicó a mano, el dato quedó en pendientes, o la llave de Odoo venció —dura unos tres meses— y Salvador pone una nueva en el servidor.

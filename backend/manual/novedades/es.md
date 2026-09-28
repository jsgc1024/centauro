# Novedades

Lo nuevo de cada actualización, escrito para quien usa el sistema. La más nueva va arriba.

## 97 · 2026-09-28 · El arranque
En el Manual del sistema, **[El arranque](#/manual/arranque)**: lo que falta para operar todo en Connect y apagar OVH, revisándose solo, como el estado del sistema. Cinco grupos —el servidor, Odoo, el dinero, la gente y la operación—, y cada renglón dice cómo está ahora, de quién es y dónde se arregla; arriba, cuántos están listos, cuántos en camino y cuántos faltan, y cuánto falta para el 2 de noviembre. Lo que el sistema no alcanza —el respaldo y sus alertas— se confirma a mano, con nombre y fecha. Cambiar lo que vale un criterio del bono ahora queda en la bitácora de administración. Además: el icono de la app en Android ya muestra su filo dorado.

## 96 · 2026-09-28 · Ya se facturó en Odoo
En Facturación → Por facturar, cada servicio trae **«Ya se facturó en Odoo»**: mientras la factura no está conectada con Odoo, finanzas la hace allá y aquí anota su folio y su fecha. El servicio sale de la lista, su folio se ve en Facturación y en el Historial —con quién lo anotó— y queda en la bitácora; el aprobado queda facturado, y cuando la conexión llegue no se vuelve a mandar. Un folio es de una sola factura. La anotada a mano se corrige en Cerrados del mes o al revisar el servicio; la que llega de Odoo, en Odoo. Además: las cajas de buscar ya no cambian lo que se escribe al salir de ellas, y un «no se puede» ya no repite qué hacer y lo pone en su propio renglón.

## 95 · 2026-09-28 · Corregir los contactos del servicio
En el servicio, arriba junto al estatus, **Corregir los contactos**: el nombre, el correo, el teléfono y el idioma de quien solicita y del principal —y los datos del principal de un equipo que lleva el suyo— se corrigen después del alta, mientras el servicio no esté cerrado ni cancelado. Lo corrige el consultor del servicio o quien lo cubre. Lo que cambia se marca con lo de antes debajo; quien solicita se puede cambiar por otro de la lista del cliente y corregirse también en esa lista. Los avisos que no han salido y la encuesta sin contestar se van a los datos nuevos, el task sheet que se descargue ya los trae, y queda en la bitácora del servicio con lo de antes. Si el correo de antes está en otro servicio abierto del cliente, se dice en cuál. Además, en Unidades, la lectura del GPS dice lo que de verdad pasa: cada 2 minutos con servicios en la calle, y cada 15 sin nadie en la calle; y la cotización de un cliente sin tarifario dice dónde se le pone: Gestión Administrativa → Odoo, en «Clientes sin tarifario».

## 94 · 2026-09-28 · La cotización autorizada, en el servicio
Mientras Odoo no manda la cotización, el consultor del servicio —o quien lo cubre— la registra en el eventual, debajo del encabezado, en **La cotización autorizada**: qué lleva cada día, cómo se cobran los gastos —dentro del precio, a monto fijo o por comprobar— y quién la autorizó del lado del cliente, el día y el folio de Odoo si existe. Los precios salen del tarifario del cliente, igual que al cerrar, con el paquete si la lista lo pacta, y «Tomar lo asignado» la llena con quien ya va. Se guarda ya autorizada; si el cliente cambia algo antes del visto bueno se recotiza con su motivo. Con ella el visto bueno ya tiene contra qué comparar.

## 93 · 2026-09-27 · El correo sale por Amazon
Postmark no aceptó el dominio mycentauro.lat: los correos del sistema salen por Amazon SES, desde la misma connect@mycentauro.lat, y las respuestas siguen llegando a cecc.notification@centauro.lat. Primero se prueba con el correo apagado; se enciende cuando Amazon apruebe la cuenta.

## 92 · 2026-09-27 · Reportar una falla
Arriba, junto a tu nombre, en todas las pantallas de la consola, y en **Yo** en la app de campo: se escribe qué pasó y, si quieres, se pega una captura o se agrega una foto; lo demás —la pantalla, el servicio, la versión y lo último que salió en rojo— se manda solo, y nunca contraseñas. Llega a sistema y calidad en [Manual del sistema → Casos](#/manual/casos), en **Por revisar**, con su aviso por correo. Ahí se resuelve o se copia para Claude; ya resuelto, a quien lo reportó le llega el aviso con la causa y cómo se arregló.

## 91 · 2026-09-27 · El correo sale por Postmark, y cuatro arreglos
MailerSend no aprobó la cuenta: los correos del sistema salen por Postmark, desde la misma connect@mycentauro.lat, y las respuestas siguen llegando a cecc.notification@centauro.lat. Además: los avisos del día y del relevo le llegan al principal de cada equipo, como el task sheet; el encabezado del servicio dice el estatus, el tipo y el estado de cada día con su nombre, en el idioma de quien mira; en la app, «Mi calificación» dice el nombre de cada parte; y aprobar un servicio de un país sin porcentaje de comisión lo dice antes, sin guardar nada.

## 90 · 2026-09-27 · El manual del sistema
El manual vive en la consola, en Gestión Administrativa → Manual del sistema, en español y en portugués. Explica cómo funciona cada pieza, qué hacer cuando algo se atora y por qué pasó. Trae el estado del sistema en vivo, lo que el sistema hace solo con su última vuelta, cada mensaje de «no se puede» con su qué hacer, quién puede qué, estas novedades y los casos resueltos. Se guarda en PDF con un botón y se pone al día con cada actualización.

## 89 · 2026-09-27 · Calidad: el mes en cifras
Pantalla nueva en Operaciones EP: cómo salió el servicio en el mes —lo que dijo el cliente, la calle, el cierre, la gente y los datos que faltan en Odoo y en Catálogos—, cada cifra contra el mes de antes y con su reporte en Excel. La ven sistema y calidad, dirección de operaciones y dirección general.

## 88 · 2026-09-27 · La llave maestra cuenta a dirección general
El candado que no deja al sistema sin llave maestra ahora cuenta también a dirección general, no solo a administración. Así se destrabó el puesto de Aridiai, que por error era la única con administración.

## 87 · 2026-09-27 · Solo un consultor lleva un servicio
En el alta del eventual y del implantado, «Consultor asignado» solo ofrece consultores con acceso abierto. El consultor que da de alta se propone a sí mismo; quien no es consultor escoge, y el servidor no da de alta un servicio a nombre de quien no es consultor.

## 86 · 2026-09-27 · Catálogos y la bitácora de administración
Pantalla nueva en Gestión Administrativa. Los catálogos que usa el sistema —festivos, hospitales, hoteles, ciudades, combustible, unidades por categoría, perfiles y países— los lleva sistema y calidad; los que deciden dinero —el tabulador de viáticos, las horas de cada modalidad y las tarifas de freelance— los fija dirección de operaciones. Cada cambio queda en la bitácora: quién, cuándo, antes y después.

## 85 · 2026-09-27 · El puesto de administración del sistema y calidad
Un rol nuevo, sistema y calidad, con su puesto: da accesos junto con Recursos Humanos, lee y aplica Odoo, mantiene los catálogos que no deciden dinero y consulta la operación. No mueve dinero, no opera y no clasifica. Lo da solo dirección general.

## 84 · 2026-09-27 · El correo sale de mycentauro.lat
Los correos del sistema salen de connect@mycentauro.lat por MailerSend, y las respuestas llegan a cecc.notification@centauro.lat. Primero se prueba con el correo apagado; se enciende cuando MailerSend aprueba la cuenta.

## 83 · 2026-09-27 · Los candados de Accesos
Nadie se da accesos ni cambia su propio puesto; el poder de repartir accesos solo lo da dirección general; las dos manos del dinero no se juntan en una persona ni en un puesto; y a quien está dado de baja no se le abre un acceso.

## 82 · 2026-09-26 · Dólares en la cotización
El cliente que paga en dólares se cotiza, se cierra y se factura en dólares. El tipo de cambio lo pone finanzas a mano, en Facturación → Tarifarios, y aplica hasta que alguien lo cambie; cada cotización se queda con el que estaba puesto al autorizarla. La comisión se paga en pesos, a ese tipo de cambio. También vale para los implantados.

## 81 · 2026-09-26 · El ícono de EP Connect
La app de campo estrena ícono: el escudo blanco con la C, sobre azul marino y con marco dorado. El nombre sigue siendo EP Connect.

## 80 · 2026-09-26 · Los precios del implantado, de su lista
Al abrir el mes, los términos del implantado toman sus precios de la lista de implantados del cliente en Odoo, con la plantilla del mes: cada persona al precio de su rol, el conductor con su unidad en paquete si la lista lo pacta, y la hora extra. Si el mes lleva otros precios, el sistema lo dice.

## 79 · 2026-09-26 · Los paquetes conductor + unidad
Cuando el equipo lleva ese rol con esa unidad y la lista del cliente pacta el paquete, se cobra el paquete: un solo renglón con su precio, en la cotización, el cierre y la factura. Finanzas marca, lista por lista, si sus paquetes traen los viáticos del día.

## 78 · 2026-09-26 · El cliente se elige buscando
En el servicio nuevo, el cliente se busca escribiendo un pedazo de su nombre, y al escogerlo se propone su país. También en Facturación → Tarifarios.

## 77 · 2026-09-26 · Los tarifarios, desde Odoo
Una quinta lectura de Odoo: los tarifarios —la lista general de cada país y la del cliente que negoció la suya—, cada hora a los :57. El precio sale como lo calcula Odoo, y solo pone precio lo que finanzas confirmó en la tabla de productos.

---
id: logistica_flota
parte: entender
orden: 46
titulo: Logística: la flota, los operadores y su jornada
resumen: Cada unidad de Centauro Logistic con su expediente, su plan preventivo, sus servicios, sus llantas y su costo por día; los operadores con su licencia y su acceso a LG Connect; la marca de jornada en el patio y el bono de 5 de 5; y la regla que dice quién puede salir.
buscar: logistica lg flota unidad numero economico eco placas tipo rendimiento odometro estado libre en viaje taller fuera de servicio expediente tarjeta circulacion poliza seguro permiso sct verificacion gps pegasus vencimiento plan preventivo servicio llantas posicion refaccion costo por dia depreciacion mantenimiento recalcular excel carga inicial operador licencia federal antiguedad lg connect applg codigo huella jornada patio geocerca marca validar rechazar central bono movilidad 5 de 5 disponibilidad
---
El bloque 2 de Logística lleva sus unidades y sus operadores a Connect. Las pantallas son dos, en **Operaciones LG**: [Flota LG](#/lg/flota) y [Jornada LG](#/lg/jornada). Los operadores tienen su propia app, **LG Connect**, en applg.mycentauro.lat: no es la de Protección Ejecutiva y nadie de un lado ve nada del otro.

## De dónde salen las unidades y los operadores {#odoo}
De Odoo, de la compañía **Centauro Logistic SA CV**. De cada unidad Odoo manda la placa, el modelo, el año, el chasis y el IAVE; las dos cajas secas entran, pero no se asignan solas: van con su tracto; el utilitario no entra. De cada empleado con puesto «Operador», su nombre, su correo personal, su teléfono y su fecha de ingreso; sus datos bancarios se quedan en Odoo. La primera lectura se hace a mano, con su ensayo —Flota LG → Carga inicial para las unidades, Jornada LG → Operadores para los operadores— y después se leen solas cada hora. Lo de Connect no se pisa: el número económico, el tipo, el odómetro, el expediente y la licencia. Lo que Odoo deja de mandar se da de baja, y al operador dado de baja se le cierra LG Connect. Una lectura que trae cero con registros activos se detiene sin dar de baja nada.

## La unidad {#unidad}
- **El número económico no se repite**: «Eco 01», «01» y «1» son el mismo, y la segunda unidad que lo pida se rechaza diciendo de quién es.
- **El estado**: libre, en viaje, en taller o fuera de servicio. Taller y fuera de servicio piden motivo y quedan en la bitácora. «En viaje» se marca a mano mientras los viajes sigan en Tango; lo marca también la gerencia, pero una unidad en taller solo la libera quien lleva la flota.
- **El odómetro** se captura a mano; una lectura menor que la anterior pide su porqué. Desde el bloque 6 se llenará con las fotos de salida y regreso de cada viaje.
- **El expediente**: tarjeta de circulación, póliza de seguro, permiso SCT, verificación físico-mecánica y GPS Pegasus, cada uno con su vencimiento y su archivo. A 30 días de vencer le llega un aviso a quien lleva la flota —si todavía nadie la lleva, a la gerencia—, y otro el día que vence. Uno nuevo reemplaza al anterior, que se queda guardado.
- **Arriba de cada unidad** se dice si puede salir, lo que la frena y sus alertas, y **lo que hay por atender** aunque hoy no frene: el documento que vence en los próximos 30 días y el servicio a menos de 2,000 km.

## El plan preventivo y los servicios {#plan}
El plan es de cada **tipo de unidad** y de las cajas: qué servicio, cada cuántos km y lo que cuesta más o menos. Cada unidad sabe a qué km le toca con **su último servicio registrado**; sin él no se adivina, se pide. Al registrar un servicio del plan —con su odómetro, su costo, su taller y su factura— el plan se recorre solo; un correctivo («Otro») no mueve el plan pero cuenta para el costo. Lo mal capturado se anula con su motivo. Las **llantas** van por posición —4, 6 o 10 según el tipo, más la refacción; las cajas, dos ejes de cuatro— y dicen cuántos km llevan desde que se instalaron; al 90% de la vida de referencia de su tipo dicen «cambio pronto».

## El costo por día {#costo}
Lo que cuesta tener la unidad un día, sin el diésel ni el operador; el margen de cada viaje lo usará. Cinco partes, cada una al año entre 365 y a centavos: **depreciación** (compra entre años de vida), **seguro**, **tenencia, verificación y GPS**, **mantenimiento** y **llantas** (lo que gastan por km por los km que la unidad recorre al día). El mantenimiento sale de los servicios registrados en los últimos 12 meses —en Odoo no hay facturas de taller de Logistic—; mientras la unidad no tenga un año de servicios, del mantenimiento anual del Excel; sin nada de la unidad, del promedio de su tipo. **Lo que le falte a la unidad se toma del costo de su tipo** en Catálogos LG. Se guarda el día 1 de cada mes y el anterior se conserva: un viaje cerrado se queda con el costo con el que se calculó. Si el del día 1 quedó a medias —su tipo todavía no tenía costo, o faltaban sus km al día—, se completa solo desde el día en que hay con qué; una unidad sin nada con qué calcular no lleva un costo en cero. A media mes se recalcula a mano, con su porqué. Las llantas necesitan los km al día de la unidad: dos lecturas del odómetro con un mes de distancia; las cajas secas, que no tienen odómetro, los tendrán con sus viajes en Connect.

## La carga inicial del Excel {#excel}
«Costos_unidades_Centauro_Logistica.xlsx», con sus hojas **Unidades** y **Plan preventivo**, después de leer las unidades de Odoo. Las columnas se reconocen por su nombre, en cualquier orden. **Todo o nada**: si un solo renglón trae error no se carga nada, y cada error dice su hoja, su renglón, su columna y qué pasa —una placa que no existe sugiere la parecida—. Se puede subir cuantas veces haga falta; después, cada cambio se captura en la unidad.

## Los operadores y LG Connect {#operadores}
En Jornada LG → Operadores: su antigüedad —de su fecha de ingreso, para el bono—, su **licencia federal** con su vencimiento y su archivo, y su acceso. Entran a LG Connect con su correo personal. La primera vez, o si olvidan su contraseña, la gerencia o quien lleva la flota les da **un código de cuatro dígitos** y se lo dicta por teléfono: sirve diez minutos y una sola vez. Después pueden entrar con huella o cara. Cambiar la contraseña cierra sus sesiones y sus huellas de antes.

## La jornada en el patio {#jornada}
Cada operador marca su inicio de jornada en LG Connect **dentro de la geocerca del patio** (300 m en Base Cuautitlán), tenga viaje o no. Fuera de ella puede marcar diciendo dónde está: la marca queda **por validar** y la **Central** la valida o la rechaza con su justificación, en Jornada LG → Por validar; el monitorista no valida, como no corrige hitos. Validada, cuenta como presente; rechazada, el día queda como ausente. La pestaña Hoy dice quién está presente, en viaje, por validar o ausente, y si puede salir.

## El bono de 5 de 5 {#bono}
La semana de lunes a viernes: cuenta el día con marca válida en el patio y el día que amaneció **en viaje** —en carretera no se puede marcar en el patio—. Cinco de cinco ganan el bono de movilidad; con una marca por validar, depende de la Central. La nómina del bloque 8 tomará de aquí los días.

## Quién puede salir {#disponibilidad}
Una sola regla para la unidad y otra para el operador, la misma que verá quien asigne los viajes. **No sale** la unidad en taller o fuera de servicio, en viaje, ocupada en otro viaje, con un documento **vencido** o con un servicio preventivo vencido; ni el operador sin marca de jornada de hoy (o con ella por validar o rechazada), en viaje o con la licencia vencida. **Sale con alerta** si un documento o la licencia no se han capturado —decisión de Salvador: solo frena lo capturado y vencido—, si algo vence durante el viaje, si la licencia vence en menos de 30 días o si un servicio cae dentro de los km del viaje.

## Quién hace qué {#quien}
- **Quien lleva la flota** (puesto «Responsable de flota LG»): unidades, estado, odómetro, expediente, servicios, llantas, plan preventivo, la carga del Excel y la lectura de Odoo.
- **La gerencia de Logística**: ve todo, da el código de LG Connect, captura la licencia y marca a mano el «en viaje».
- **La Central**: ve la jornada y valida o rechaza las marcas fuera del patio.
- **Sistema y calidad**: ve la flota y la jornada. Todo cambio queda en la bitácora de cada pantalla y en la de administración.

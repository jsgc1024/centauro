---
id: pantallas
parte: entender
orden: 70
titulo: Cada pantalla, para qué es
resumen: Las pantallas de la consola, grupo por grupo, y la app de campo. Qué se hace en cada una y lo que conviene saber de ella.
buscar: pantallas menu operacion cotizaciones direccion eventual implantado personal unidades desempeño clientes calidad monitoreo codigo gastos facturacion nominas accesos odoo catalogos manual app de campo
---
El menú de cada quien sale de su puesto. Casi todos los bloques traen un **«?»**: para qué sirve, cuándo te enteras si falla y de dónde sale el número. Esa ayuda vive pegada a su pantalla y es la más al día que hay.

Arriba, junto a tu nombre, está **Reportar una falla** en todas las pantallas: le llega a sistema y calidad con la pantalla donde estabas y lo último que te salió. Ver [reportar una falla](#/manual/leer/fallas).

## Operaciones EP

### Operación {#panorama}
Cómo va la operación ahora mismo: lo de hoy, quién va en camino, los países, el dinero afuera, lo que finanzas regresó y la calidad. Es la vista de arriba; el detalle vive en cada servicio.

### Cotizaciones {#cotizaciones}
La cotización del eventual y la propuesta del implantado, antes de que exista el servicio: se arman con la lista del cliente, salen en PDF con su folio —EP/COT-0001, EP/PRO-0001— y su versión, y cuando el cliente la autoriza nace el servicio con ella adentro. La lista dice qué es cada una, cuáles están abiertas, cuánto les falta para vencer y de cuál nació qué servicio. Aquí cada consultor sube su firma. Ver [la cotización al cliente](#/manual/leer/cotizaciones) y [la propuesta del implantado](#/manual/leer/propuesta).

### EP eventual {#servicios}
Los servicios que se contratan por día: el alta, la cotización, los equipos, quién va y en qué unidad, el task sheet, los viáticos y el cierre. Ver [el camino de un servicio](#/manual/leer/camino).

### EP implantado {#implantados}
Los servicios de mes, con la misma gente todos los días: los términos del mes, el calendario, los reemplazos, el taller y el cierre del mes. Ver [el implantado](#/manual/leer/implantado).

### Personal de Seguridad {#equipo}
Dos pestañas. **De planta**: la gente que viene de Odoo, con su ficha, sus certificados y su profesionalismo; lo que viene de Odoo aquí no se edita, se corrige en Odoo. **Freelance**: el freelance se da de alta aquí, con su foto y sus datos —los que salen en la hoja—, sus costos y su expediente de Recursos Humanos; la lista dice quién está listo, qué le falta a cada uno y lo que espera revisión o está por vencer. Ver [el freelance](#/manual/leer/freelance).

### Unidades {#unidades}
La flota con su GPS: qué unidad reporta, cuál no liga con Pegasus y qué hay que arreglar antes de que salga a servicio. Cada renglón dice qué le falta y dónde se corrige. No dice dónde está ninguna: no es un rastreo.

### Desempeño {#bonos}
El bono del mes: qué se mide, las estrellas de cada quien, lo que autoriza Recursos Humanos y lo que deposita finanzas.

### Clientes {#encuestas}
Lo que dijo el cliente: las encuestas, la tasa de respuesta y las calificaciones de 3 o menos que el consultor tiene que revisar. Una calificación baja abre una revisión, nunca un castigo automático.

### Calidad {#calidad}
El mes en cifras: lo que dijo el cliente, la calle, el cierre, la gente y los datos que faltan en Odoo y en Catálogos, contra el mes de antes, con su reporte en Excel para la junta.

### Dirección de operaciones {#direccion}
Lo que espera la firma del director de operaciones —las incidencias por autorizar, el freelance que alguien pide por urgencia, los precios especiales de las propuestas, los cobros al cancelar y los plazos vencidos del cierre—, las tres que viven en otras pantallas —las comisiones del mes por firmar, que abren Nóminas → Comisiones en ese país y ese mes; las malas calificaciones por revisar, que abren Clientes; y los cierres por firmar que siguen en plazo, con cuánto les queda, que abren la tarjeta del cierre— y las cuentas de hoy por país: servicios hoy y mañana, en curso, con alerta, cambios por contingencia e incidencias del mes. Cada número se abre para ver cuáles servicios son. La ven el director de operaciones y la dirección general.

## Operaciones LG

### Catálogos LG {#lg_catalogos}
Centauro Logística (AI/LG): lo que el margen, el anticipo y la nómina de cada viaje van a usar, cada valor con la fecha desde la que rige. Lo que decide dinero —el tabulador de comisiones, el diésel con su holgura y su tolerancia, los alimentos, el margen mínimo, el costo del operador, el rendimiento y el costo por tipo de unidad, el bono y la garantía— lo fija la gerencia de Logística; los tipos de unidad y los patios los lleva sistema y calidad. La lista de la izquierda dice qué falta y quién lo da, y la pestaña Bitácora cuenta cada cambio. Dentro de estas pantallas el encabezado dice AI/LG. Ver [Logística](#/manual/leer/logistica).

### Flota LG {#lg_flota}
Cada unidad de Centauro Logistic: su número económico, su estado, su expediente con vencimientos, su plan preventivo, sus servicios, sus llantas y su costo por día, y si puede salir hoy. La lleva quien tiene el puesto «Responsable de flota LG»; la gerencia de Logística y sistema y calidad la ven, y la gerencia marca a mano el «en viaje». La pestaña Carga inicial lee las unidades de Odoo y sube el Excel de costos. Ver [Logística: la flota](#/manual/leer/logistica_flota).

### Jornada LG {#lg_jornada}
Quién se presentó a trabajar: la marca de jornada de cada operador en el patio, desde LG Connect; su semana para el bono de 5 de 5; las marcas fuera del patio que valida la Central; y en Operadores, su licencia federal y el código de cuatro dígitos para entrar a LG Connect. La abren la gerencia de Logística, quien lleva la flota, la Central y sistema y calidad.

## Operaciones CI

### Monitoreo {#central}
La central: lo que hay que atender ahora —un pánico, una unidad sin corriente, un equipo callado—, las unidades que salieron del servicio y siguen por entregar, con quién responde y cuánto les queda, y lo que hay que resolver antes del corte de la víspera. Aquí se registran a mano las marcas que no llegaron, con su justificación, y la entrega sin revisión cuando las fotos ya no se pueden tomar.

### Mapa de riesgo {#riesgo}
Lo que pasa en el país y a quién le llega. Los analistas capturan cada evento con su tipo, estado, nivel del 1 al 4, punto y hasta cuándo afecta; nada llega al cliente sin publicarse, y un nivel 4 espera a que el jefe de turno lo confirme. Al publicar, el aviso sale a los gerentes de los clientes que siguen ese estado: el nivel 2 en el resumen de las 20:00, el 3 y el 4 al momento, y si un 4 no tiene acuse en 15 minutos aparece arriba para llamar. En la pestaña de clientes se le da el servicio a un cliente de Odoo, se eligen sus estados y se da de alta a su gerente.

### Código {#codigo}
El código de cuatro dígitos que se le dicta por teléfono al personal de campo que no puede entrar a la app. Vale 10 minutos.

## Gestión Administrativa

### Gastos {#finanzas}
La bandeja de finanzas: los depósitos que confirmar, las compras, las rentas, las devoluciones y los descuentos.

### Facturación {#facturacion}
Lo que ya tiene el visto bueno del consultor —el servicio eventual o el mes del implantado—: aprobarlo, regresarlo a operación con su motivo y seguir su factura; lo aprobado sin factura ni prefactura timbrada también se regresa, con «Regresar» en su renglón. Con la llave de la factura, «En Odoo» tiene las prefacturas que esperan al facturista y «No se pudo mandar» las que no salieron, con su porqué, «Mandar otra vez» y el reintento de cada hora; «Ver» separa los eventuales de los implantados. Sin la llave, la factura se hace en Odoo y aquí se anota, con «Ya se facturó en Odoo». Aquí viven también los tarifarios y la tabla de productos de Odoo que finanzas confirma.

### Nóminas {#nomina}
El corte del personal de cada lunes y la comisión de los consultores de cada mes: lo que entra, lo que todavía no y por qué.

### Accesos {#accesos}
Quién puede entrar, con qué puesto, y cuándo entró por última vez; se filtra por país y por quiénes ya entraron, nunca han entrado o llevan meses sin entrar. Aquí se arman los puestos, se manda o se copia la invitación y se cierran los accesos. Ver [accesos, roles y puestos](#/manual/leer/accesos).

### Odoo {#odoo}
Las cinco lecturas de Odoo: aquí se hacen el ensayo y la primera lectura de cada una, y se ve lo que falta corregir allá. Arriba dice si el servidor ya tiene la llave de la factura del eventual. Ver [lo que viene de Odoo](#/manual/leer/odoo).

### Catálogos {#catalogos}
Lo que el sistema usa para calcular y para armar la hoja del servicio: festivos, hospitales, hoteles, ciudades, combustible, categorías de unidades, perfiles, países, los requisitos del freelance, modalidades y el tabulador de viáticos; y los textos de la cotización y de la propuesta al cliente. Los costos de cada freelance viven en su ficha, en Personal de seguridad. Lo que decide dinero lo fija dirección de operaciones. Lo que se quita no se pierde: sale en gris con «Reactivar». Aquí vive también la bitácora de administración: quién cambió qué.

### Manual del sistema {#manual}
Este manual: cómo funciona cada pieza, qué hacer cuando algo se atora, el estado del sistema en vivo y los casos: las fallas reportadas por revisar y lo que ya se resolvió. Mientras dura el cambio a Connect, también [el arranque](#/manual/arranque): lo que falta para operar todo aquí y apagar OVH, revisándose solo, con de quién es cada cosa y dónde se arregla.

## La app de campo {#app}
EP Connect, en el teléfono del personal de seguridad: su día y los que siguen —con el teléfono del ejecutivo, el hotel donde se hospeda, el hospital más cercano y la agenda del día, cuando están capturados—, la confirmación de la víspera (que se vuelve a pedir si cambia la hora), sus marcas —llegada, contacto y fin, que se marca cuando el ejecutivo corta—, la unidad por entregar después del fin, arriba y con su reloj de 24 horas, sus viáticos y comprobantes con su plazo, la revisión de la unidad al recibirla y al entregarla, y el botón de pánico. En **Yo** se encienden los avisos del teléfono, se manda un aviso de prueba y se reporta una falla de la app, con una foto si hace falta.

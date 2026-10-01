---
id: implantado
parte: entender
orden: 30
titulo: El implantado, mes por mes
resumen: El servicio de largo plazo con el mismo equipo, que se trabaja y se cobra por mes: sus términos, su mes, sus reemplazos y su cierre.
buscar: implantado contrato mes terminos acuerdo plantilla titular 12x36 reemplazo taller cierre del mes factura lista de implantados horas de la jornada descanso cambiar la plantilla del mes
---
El implantado es un servicio de largo plazo con el mismo equipo, que se trabaja y se cobra **por mes**. Su folio es de otra serie, EP/IM-001, porque es otra operación.

## Los términos del mes
Cada mes tiene su acuerdo: si se cobra por día o por mes completo, si incluye fines de semana, los días base, la hora de presentación, la modalidad y los precios. Los precios salen de la **lista de implantados** del cliente en Odoo. El que nace de una [propuesta](#/manual/leer/propuesta) abre su primer mes con lo que el cliente autorizó: un **mensual** que cubre 22, 26 o 30 días según su modalidad —aunque el mes traiga 21 o 23 hábiles—, el día fuera de la modalidad aparte al precio del **día adicional**, la hora extra, la jornada y los viáticos; si empieza a medio mes, ese primer mes va por día de servicio. Sus términos dicen de qué propuesta salen y no se comparan con la lista. Si el mes lleva otros, el sistema lo dice: puede ser un acuerdo especial con el cliente, y entonces se deja así. Las horas de la jornada y de descanso salen de la modalidad **«Implantado»** del país, en Catálogos > Horas de cada modalidad (12 horas en México y en Brasil; las horas de descanso se pondrán ahí cuando se den, y las toman todos los implantados del país); por contrato se pueden pactar otras desde los términos del mes, y el 12 × 36 nunca lleva descanso. Las horas extra empiezan después de la jornada. Los cambios del trato —días de servicio, hora del encuentro, precios y horas— **aplican desde el mes siguiente**: los meses ya abiertos se rehacen solos sin tocar días con marcas, con cambio o con gente puesta a mano, y la pantalla dice qué días se movieron; el mes en curso se corrige a mano, desde el calendario y desde «Ver operación».

## El mes
El reloj abre solo el mes siguiente cuando al mes en curso le quedan pocos días, a las 6:30; si estuvo apagado, en la primera vuelta que corra abre lo que falte hasta el mes en curso. El mes trae su plantilla: quién es el titular y qué unidad lleva; el servidor exige personal de seguridad activo de la ciudad del servicio y una unidad fija disponible, y al abrir cada mes la vuelve a revisar: si alguien fue dado de baja o la unidad está en el taller, esa posición queda por cubrir, en ámbar, con su alerta para la central y el aviso al consultor. En Brasil existe el 12 × 36: dos personas que se turnan los siete días; con un mes ya generado el turno no se cambia (se cierra el implantado y se da de alta otro). Para cambiar la plantilla de forma permanente —una baja, una unidad vendida, un vehículo que faltaba— está **Cambiar la plantilla del mes**, en «Asignación y coordinación»: se agregan o quitan personas y unidades, se cambia el rol o la unidad de cada quien y, con la casilla marcada, el cambio llega también a los meses siguientes ya abiertos; los días operados, con cambio o cubiertos a mano se quedan como están.

## Los reemplazos
Cuando el titular no puede ir, se le reemplaza por un rango de días, de personal o de unidad. Cubrir un solo día se hace desde la ficha del día, con la posición que se cubre: el relevo toma el rol de esa posición. Un día cancelado se reactiva antes de cubrirlo. La unidad en el taller —según las entradas de Flotilla en Odoo, o las metidas desde el mes— no se ofrece; la que entró sin fecha de salida sale con «Salió del taller» en el bloque del mes, y la que vino de Odoo se cierra en Odoo.

## El cierre del mes
El implantado no cierra por servicio sino **por mes**: el cierre de cada mes arranca solo al cerrar su último día trabajado, también en un implantado cancelado con días trabajados, que sigue en la cartera mientras un mes suyo tenga cierre por terminar. Tiene su visto bueno y su factura del mes, con las horas extra en su renglón. La nómina paga al implantado por día trabajado, y la comisión del consultor es el 1 % de lo facturado, sin gastos ni impuestos.

> Si el mes siguiente no se abrió, se mira el [reloj](#/manual/reloj); si sale con otros precios, su lista de implantados en Odoo; si su cierre no arranca, su último día sin cerrar.

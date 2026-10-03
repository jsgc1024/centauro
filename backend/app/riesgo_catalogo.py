"""Los catalogos de arranque de la Central de Inteligencia (seccion 133).

Una sola copia, que leen la migracion (para el servidor) y la semilla
(para las pruebas): si estuvieran escritas dos veces, la base de pruebas
probaria otro catalogo que el de produccion.

Los tipos de evento son los de la cifra negra que la central ya publica
en su resumen mensual, con sus definiciones tal cual (2 oct 2026). Los
tres del camino --bloqueo, manifestacion y fenomeno natural-- no estaban
en esa lista y se agregaron porque la Central tambien sigue trayectos;
sus definiciones son un primer borrador para que la central las corrija
en Catalogos.
"""

# Clave INEGI de cada entidad federativa.
REGIONES_MX = [
    ("01", "Aguascalientes"), ("02", "Baja California"),
    ("03", "Baja California Sur"), ("04", "Campeche"),
    ("05", "Coahuila"), ("06", "Colima"), ("07", "Chiapas"),
    ("08", "Chihuahua"), ("09", "Ciudad de México"), ("10", "Durango"),
    ("11", "Guanajuato"), ("12", "Guerrero"), ("13", "Hidalgo"),
    ("14", "Jalisco"), ("15", "Estado de México"), ("16", "Michoacán"),
    ("17", "Morelos"), ("18", "Nayarit"), ("19", "Nuevo León"),
    ("20", "Oaxaca"), ("21", "Puebla"), ("22", "Querétaro"),
    ("23", "Quintana Roo"), ("24", "San Luis Potosí"), ("25", "Sinaloa"),
    ("26", "Sonora"), ("27", "Tabasco"), ("28", "Tamaulipas"),
    ("29", "Tlaxcala"), ("30", "Veracruz"), ("31", "Yucatán"),
    ("32", "Zacatecas"),
]

# Sigla de cada unidad federativa.
REGIONES_BR = [
    ("AC", "Acre"), ("AL", "Alagoas"), ("AP", "Amapá"), ("AM", "Amazonas"),
    ("BA", "Bahia"), ("CE", "Ceará"), ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"), ("GO", "Goiás"), ("MA", "Maranhão"),
    ("MT", "Mato Grosso"), ("MS", "Mato Grosso do Sul"),
    ("MG", "Minas Gerais"), ("PA", "Pará"), ("PB", "Paraíba"),
    ("PR", "Paraná"), ("PE", "Pernambuco"), ("PI", "Piauí"),
    ("RJ", "Rio de Janeiro"), ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"), ("RO", "Rondônia"), ("RR", "Roraima"),
    ("SC", "Santa Catarina"), ("SP", "São Paulo"), ("SE", "Sergipe"),
    ("TO", "Tocantins"),
]

REGIONES = {"MX": REGIONES_MX, "BR": REGIONES_BR}

# (nombre, radio en metros con que nace, definicion)
TIPOS_MX = [
    ("Artefacto explosivo", 2000,
     "Dispositivo elaborado de manera artesanal o industrial que contiene "
     "materiales explosivos y está diseñado para detonar de forma "
     "controlada o no controlada, con el propósito de causar daños "
     "físicos, materiales o generar un impacto psicológico en la "
     "población. En el contexto del crimen organizado, su uso suele estar "
     "asociado a actos de intimidación, coacción, represalia o "
     "desestabilización del orden público, dirigidos contra autoridades, "
     "grupos rivales, infraestructura estratégica o establecimientos "
     "comerciales."),
    ("Ataque armado (arma blanca)", 1000,
     "Evento de carácter violento en el que una o más personas emplean el "
     "uso de objetos punzocortantes para agredir a personas, con la "
     "finalidad de causar lesiones, privar de la vida, intimidar o generar "
     "alteraciones al orden público."),
    ("Ataque armado (arma de fuego)", 2000,
     "Evento de carácter violento en el que una o más personas emplean un "
     "arma de fuego para realizar detonaciones dirigidas contra personas, "
     "bienes, infraestructura o espacios públicos, con la finalidad de "
     "causar lesiones, privar de la vida, generar intimidación o alterar "
     "el orden público."),
    ("Detención", 1000,
     "Acto mediante el cual las autoridades competentes aseguran y privan "
     "de la libertad, conforme al marco legal vigente, a una persona "
     "identificada como líder criminal, integrante relevante o actor "
     "estratégico de un grupo delictivo u organización criminal, derivado "
     "de investigaciones, operativos o mandamientos judiciales."),
    ("Ejecución", 1000,
     "Hecho violento de alto impacto en el que una o más personas privan "
     "de la vida a otra de manera intencional y directa, generalmente "
     "mediante el uso de armas de fuego u otros elementos. Este tipo de "
     "evento suele estar asociado a contextos de criminalidad organizada, "
     "ajustes de cuentas o disputas delictivas, y representa una "
     "afectación a la seguridad pública y al orden social."),
    ("Enfrentamiento armado", 3000,
     "Evento violento en el que dos o más grupos antagónicos intercambian "
     "agresiones de manera recíproca mediante el uso de armas de fuego; "
     "generalmente en espacios públicos o de tránsito, con la intención "
     "de repeler, neutralizar o someter a la parte contraria. Este tipo "
     "de hecho implica un alto nivel de riesgo para la población, las "
     "autoridades y la infraestructura, y genera una alteración "
     "significativa al orden y la seguridad pública."),
    ("Incendio (vehículo, hogar, negocio)", 2000,
     "Hecho violento en el que una o más personas provocan de manera "
     "intencional la quema de vehículos, domicilios o establecimientos "
     "comerciales, con la finalidad de causar daños materiales, intimidar, "
     "enviar mensajes de amenaza o ejercer control territorial, "
     "generalmente en contextos vinculados a la operación de "
     "organizaciones criminales o grupos delictivos."),
    ("Lesión", 1000,
     "Daño físico ocasionado a una persona como consecuencia directa de "
     "un ataque armado, ya sea mediante el uso de armas de fuego, armas "
     "blancas u otros medios de agresión, que afecta su integridad "
     "corporal y puede variar en gravedad."),
    ("Mensaje criminal", 1000,
     "Manifestación escrita, gráfica o simbólica atribuida a grupos "
     "delictivos, localizada en espacios públicos o privados, utilizando "
     "lonas, mantas, cartulinas u otros soportes, mediante la cual se "
     "emiten amenazas, advertencias, señalamientos o mensajes de "
     "intimidación dirigidos a personas, autoridades o grupos rivales. El "
     "hallazgo de este tipo de mensajes constituye un indicador de "
     "actividad delictiva y de disputa criminal, y tiene como finalidad "
     "generar temor y control territorial."),
    ("Operativo de seguridad", 2000,
     "Conjunto de acciones coordinadas y planificadas implementadas por "
     "autoridades de seguridad de los distintos órdenes de gobierno, con "
     "el objetivo de prevenir, contener o neutralizar actividades "
     "delictivas asociadas al crimen organizado y reducir la incidencia "
     "de hechos de alto impacto."),
    ("Persecución armada", 3000,
     "Hecho violento en el que una o más personas persiguen de manera "
     "activa a otra persona o grupo mediante vehículos, haciendo uso de "
     "armas de fuego u otros medios letales durante el desplazamiento, "
     "con la finalidad de agredir, someter o privar de la libertad o de "
     "la vida a la víctima. Este tipo de evento afecta la seguridad vial "
     "y altera de manera significativa el orden y la seguridad pública."),
    ("Ponchallantas", 3000,
     "Dispositivo artesanal o metálico, diseñado con puntas u objetos "
     "punzantes, que es colocado de manera intencional sobre vialidades "
     "con el objetivo de dañar neumáticos de vehículos en circulación. Su "
     "uso está comúnmente asociado a actividades de grupos delictivos, ya "
     "sea para facilitar la huida tras la comisión de un delito, "
     "obstaculizar el desplazamiento de autoridades o generar riesgo y "
     "control temporal del entorno."),
    ("Secuestro", 2000,
     "Hecho delictivo en el que una o más personas privan de la libertad "
     "a otra de manera ilegal, mediante el uso de la fuerza, amenazas, "
     "engaño o violencia, con el propósito de obtener un beneficio "
     "económico, ejercer presión, intimidar o cumplir objetivos de una "
     "organización criminal o grupo delictivo."),
    # Los del camino: borrador para que la central los corrija.
    ("Bloqueo carretero", 5000,
     "Cierre total o parcial de una vialidad o carretera, con vehículos, "
     "objetos o personas, que impide o condiciona el paso. Incluye los "
     "bloqueos con quema de vehículos atribuidos a grupos delictivos y "
     "los cierres por protesta."),
    ("Manifestación", 2000,
     "Concentración o marcha de personas en el espacio público que altera "
     "la circulación o el acceso a un lugar, sin violencia armada."),
    ("Fenómeno natural", 20000,
     "Lluvia intensa, inundación, huracán, sismo, incendio forestal u otro "
     "fenómeno de la naturaleza que pone en riesgo a las personas o "
     "impide el paso."),
]

TIPOS = {"MX": TIPOS_MX}

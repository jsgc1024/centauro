# La prueba 360

*Propuesta. 20 de septiembre de 2026.*

Pregunta de Salvador: **¿cómo hacemos para correr servicios de inicio a
fin, con todos los escenarios, y verificar que todo corre bien y que en
las pantallas no falta ni sobra información?**

---

## Primero, qué hay hoy y qué no

**649 pruebas.** Son buenas y son honestas, pero casi todas miran **una
regla a la vez**: que la marca fuera de geocerca se rechace, que el
tabulador reparta sin centavos, que el correo salga en el idioma de cada
quien. Eso caza los errores de una regla. No caza los errores de las
reglas **entre ellas**.

**Ocho escenarios completos** (`tests/test_escenarios.py`) que sí caminan
un servicio: el transfer de aeropuerto, el proyecto de tres días con
hotel, el que se mueve entre dos ciudades. Pero **todos se detienen en el
task sheet o poco después**. Ninguno llega a la nómina.

**Cero pruebas de pantalla.** Hay 273 endpoints y 13 pantallas en la
consola más la app de campo. Nada verifica hoy que lo que una pantalla
pide traiga todo lo que la pantalla pinta.

Ese es el hueco exacto de tu pregunta.

---

## Una prueba 360 no es una prueba: son cuatro instrumentos

Cada uno caza una clase distinta de error, y ninguno sustituye a los
otros. Van en orden de **cuánto te sirve por lo que cuesta**.

### 1 · El zoológico — la base sembrada

Un comando, `sembrar_360.py`, que deja la base de desarrollo con **un
servicio de cada tipo y en cada estado**: borrador a medias, planeado
sin asignar, confirmado para mañana, uno en curso a media tarde, uno
terminado sin cerrar, uno cerrado con nómina, uno cancelado con dinero
afuera, uno con incidencia abierta, uno con viáticos a medio comprobar,
un implantado a mitad de mes, un 12×36. Cada uno con su gente, sus
unidades, sus fotos y su historia.

**Para qué sirve:** para que **tú** lo mires. Esta es la parte que
ninguna prueba automática puede hacer. Un test verifica que el campo
`hospedaje` venga con tres hoteles; **no puede juzgar** si al abrir la
pantalla falta el teléfono del hotel, o si sobra una columna que nadie
usa, o si un renglón dice "—" donde debería decir algo. Eso lo juzga una
persona con el ojo puesto, y para juzgarlo necesita pantallas llenas de
datos creíbles, no una base vacía.

Es también lo que hace posible enseñarle el sistema a alguien sin
armarle un servicio a mano cada vez.

**Costo: una sesión.** Es lo primero que haría.

### 2 · El recorrido — el guion completo

Un servicio caminado **de la cotización a la nómina**, sin saltarse nada:

> cotizar → autorizar → alta → asignar gente y unidad → punto y pin →
> confirmar la asignación → publicar el TS → recordatorio de la víspera
> → confirmación del equipo → *voy en camino* → llegada al punto →
> contacto con el ejecutivo → revisión de recepción de unidad → reportes
> durante el día → horas extra → fin de servicio → revisión de entrega
> → correo de término del día → comprobación de viáticos → cierre de
> viáticos → cierre del servicio → nómina → comisiones y bonos

Y encima, la **matriz de variantes**. Cada una toca reglas que las otras
no:

| Variante | Qué pone a prueba |
|---|---|
| Transfer suelto de aeropuerto | El camino más corto; el vuelo manda la hora |
| Full day de 3 días con hotel | Hospedaje, hospitales desde el hotel, viáticos por día |
| Foráneo | Viáticos de foráneo, hospedaje obligado, otra plaza |
| Dos equipos, dos ciudades | Dos TS, dos ejecutivos, dos relojes |
| Dos países | Dos monedas, dos zonas horarias, dos cajas de finanzas |
| Con reemplazo a media jornada | Día partido, dos pagos, correo al cliente |
| Con cancelación y dinero afuera | Lo que se devuelve y lo que se descuenta |
| Con botón de pánico | Alerta, toma de la central, cierre de la incidencia |
| Con el conductor que no llega | Los tres toques, la alerta, el equipo de respuesta |
| Implantado de un mes | El ciclo mensual, que es otro animal |
| 12×36 | El rol que rota y no se presenta igual |

**Para qué sirve:** caza lo que ninguna prueba unitaria ve — que dos
reglas correctas por separado se estorben. El candado de la hora que
choca con el candado de la secuencia. El viático que se mueve en un
reemplazo y deja a la nómina contando dos veces.

**Costo: dos sesiones.**

### 3 · El cuadre — las igualdades que siempre tienen que dar

Al terminar cada recorrido, un puñado de cuentas que **no pueden fallar
nunca**, y que hoy nadie verifica de punta a punta:

- Lo entregado = comprobado + devuelto + descontado + absorbido
- Lo asignado = depositado + en camino + por solicitar
- Las horas que se le facturan al cliente = las horas del cierre
- Toda jornada terminada tiene sus cuatro hitos, o su cierre a mano con
  su motivo
- Ningún viático colgando de una jornada que ya no existe
- Ninguna alerta abierta en un servicio cerrado
- Ninguna unidad recibida y no entregada en un servicio cerrado
- Ningún aviso en la cola apuntando a un servicio borrado

**Para qué sirve:** caza las inconsistencias **silenciosas**. Son las
peores porque ninguna pantalla las enseña: el sistema se ve bien y los
números no cuadran. Lo que encontramos hoy con el depósito cancelado era
exactamente de esta familia.

Se monta encima del recorrido casi gratis: el guion ya dejó el servicio
en su estado final; esto solo mide.

**Costo: una sesión**, si el recorrido ya existe.

### 4 · El contrato de pantalla

Por cada una de las 13 pantallas de la consola y cada vista de la app:
llamar a los endpoints que esa pantalla usa, contra un servicio de cada
estado, y verificar dos cosas — **que no falte** ningún campo que la
pantalla pinta, y **que no sobre** nada que no debería viajar.

Lo de "que no sobre" no es teoría: el endpoint de unidades mandaba
megabytes de fotos de unidades ajenas a cada teléfono.

**Para qué sirve:** es la respuesta literal a "que la información fluya
completa y no haya información faltante o de más".

**Costo: dos o tres sesiones.** Es el más laborioso porque son muchas
pantallas, y por eso va al final: para entonces los otros tres ya
limpiaron lo grueso.

---

## Lo que esto NO hace, y hay que decirlo

- **No hace clic en el navegador.** Nadie abre Chrome, nadie llena un
  formulario. Para eso haría falta Playwright contra la consola de
  verdad. Es otro proyecto y yo lo dejaría para cuando el sistema esté
  en el servidor: probar clics contra algo que todavía se está moviendo
  es pagar dos veces.
- **No manda un correo real ni un push real.** Verifica que el aviso se
  arme y se encole con el texto correcto; que Gmail lo entregue es del
  proveedor, y eso se prueba el día que exista el dominio.
- **No prueba con datos reales.** Los montos del tabulador siguen siendo
  los de la semilla hasta que me pases los tuyos.

---

## Por dónde empezaría

**El zoológico primero.** En una sesión tienes la base llena y te
sientas a mirar pantallas — que es donde vas a encontrar lo que ninguna
prueba encuentra. Lo que salga de ahí ordena todo lo demás.

Después el recorrido con tres o cuatro variantes, el cuadre encima, y el
contrato de pantalla al final.

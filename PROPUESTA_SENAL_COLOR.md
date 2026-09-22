# La señal de color

22 de septiembre. Propuesta antes de escribir código.

## Lo que pediste

La señal con la que el principal reconoce al equipo hoy puede ser **una
palabra** o **una imagen**. Quieres una tercera opción —**un color**—,
que el consultor la elija entre los colores secundarios de Centauro, y
que sea **la opción principal** del panel.

## Por qué un color es la mejor señal

- **Se ve desde lejos.** A la salida del filtro hay treinta letreros con
  nombres; un teléfono naranja en alto se distingue a veinte metros sin
  leer nada. Es lo que hacen las apps de transporte para que el pasajero
  encuentre su coche entre cincuenta.
- **No se equivoca.** Una palabra se lee mal, una foto se ve chica; un
  color es un color.
- **Ya está en el teléfono.** No hay imagen que bajar ni que guardar:
  sin señal de red funciona igual, desde el primer día.
- **El principal sabe qué buscar.** Su hoja dice *«su equipo lo espera
  con una pantalla naranja»*; llega buscando el color, no adivinando.

## Cómo se ve

**El panel del servicio.** Tres opciones; **Color** va primero,
seleccionada y marcada como recomendada. Debajo, los colores en
círculos grandes con su nombre; la palabra encima es opcional; la nota
para el equipo sigue igual. A la derecha, el teléfono como lo verá el
principal, en vivo mientras se elige.


**El teléfono, a pantalla completa.** El color ocupa todo. Si hay
palabra, va en el centro; la letra sale blanca o negra sola, según el
color de fondo, para que se lea sobre amarillo igual que sobre morado.
Girado, ocupa todo igual. La pantalla no se apaga mientras está abierta.


**La tarjeta del día en la app.** Junto al ejecutivo: el botón con el
punto del color, el nombre del color y la palabra, y la nota debajo. Un
toque y sale la pantalla completa.


**El task sheet.** El bloque de señal muestra el cuadro del color con la
palabra y la frase en el idioma del principal.


## Los colores

Propongo estos ocho, elegidos para que se distingan entre sí, se vean a
pleno sol y en un lobby, y ninguno se confunda con el navy de la marca:

| | Nombre | Hex | Letra encima |
|---|---|---|---|
| 🟠 | Naranja | `#F26B1D` | blanca |
| 🟡 | Amarillo | `#F2C200` | negra |
| 🟢 | Verde | `#22A05B` | blanca |
| 🔵 | Turquesa | `#12A5B4` | negra |
| 🔵 | Azul | `#2F7FE0` | blanca |
| 🟣 | Morado | `#7B3FB8` | blanca |
| 🩷 | Magenta | `#D4267E` | blanca |
| 🔴 | Rojo | `#D93025` | blanca |

**En el sistema no encontré una paleta secundaria de Centauro** —solo el
navy `#1B1546`—. Si el manual de marca tiene los colores secundarios,
pásame los hex y sustituyo estos ocho; la lista es una tabla de
configuración, se cambia sin tocar nada más. El nombre de cada color va
en los tres idiomas porque sale en la hoja del principal.

## Lo que cambia en el sistema

| Dónde | Qué |
|---|---|
| Base de datos | Un campo `senal_color` en el servicio, con su migración. Solo acepta un color de la lista: así siempre tiene nombre. |
| Consola (servicio) | El panel de arriba: Color primero y preseleccionada; los círculos; la palabra opcional encima; vista previa en vivo. |
| App de campo | La tarjeta del día pinta el punto del color y el nombre; la pantalla completa se llena del color, con la palabra si la hay. Sin descarga: funciona sin red desde el primer día. |
| Task sheet | El bloque de señal con el cuadro del color y la frase en el idioma del principal. |
| Pruebas | Guardar, leer y quitar el color; que rechace un color fuera de la lista; que la ficha del día lo traiga; que la hoja lo imprima. |

Lo que ya existe se queda como está: palabra sola e imagen siguen
funcionando, y la nota para el equipo sigue igual.

## Lo que decides tú

1. **Los colores.** ¿Van los ocho propuestos o me pasas los del manual
   de marca?
2. **La palabra encima.** Propongo que sea opcional sobre el color
   (color solo, o color con palabra). ¿De acuerdo?
3. **El orden de las opciones.** Color, Palabra, Imagen; Color
   preseleccionada. ¿Así?

Con tu visto bueno se construye en una sesión: el panel, la app, la
hoja y sus pruebas.

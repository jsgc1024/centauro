import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

VIEJO = """**La raya con el implantado.** Este motor es de eventual y lo dice por
candado, no por costumbre: rechaza una jornada de implantado con un 409
que apunta a su calendario. No es separación de gusto —el implantado
reutiliza el mismo equipo mes tras mes, así que un cambio "de aquí en
adelante" barrería todas las jornadas abiertas y abriría decenas de
viáticos de un solo clic. Su reemplazo va día por día, en
`implantado.cambiar_personal`, **y ahí sigue el mismo agujero de nómina**
(ver sección 12).
"""

NUEVO = """**La raya con el implantado ya no existe.** Ver la sección 11 bis.

---

## 11 bis. El implantado usa el mismo motor

**El agujero, otra vez.** El implantado tenía su propia copia de la
regla, y la copia estaba mal: mutaba la asignación igual que el eventual
antes de arreglarlo. Quien trabajó cinco horas, se enfermó y fue
relevado cobraba cero. Aquí pesa más que en eventual, porque el
implantado es operación diaria con plantilla fija: el relevo no es la
excepción, es el martes.

Y tenía **dos puertas** para el mismo cambio —una de día suelto que
tomaba `jornada.personal[0]` a ciegas, y una de tramo que sí aceptaba
quién sale—. Desde la pantalla no se veía cuál te tocaba.

**La decisión: una sola regla, una sola puerta.**

`implantado.cambiar_recurso` ya no cambia nada por su cuenta. Traduce el
tramo de fechas a jornadas y se lo entrega a `contingencia`, que es el
motor que parte el día bien. `implantado.reemplazar()` y su endpoint
`/implantados/jornadas/{id}/reemplazo` desaparecieron: un día suelto es
un tramo de un día.

**El candado de contingencia cambió de forma.** Antes decía "implantado
prohibido". Ahora dice **"implantado, pero con fecha de fin"**. Lo que
protegía sigue en pie: el implantado reutiliza el mismo equipo mes tras
mes, así que un cambio "de aquí en adelante" se llevaría también octubre
si octubre ya está abierto, sin que nadie lo pida y sin que aparezca en
ninguna pantalla. La fecha la pone `cambiar_recurso`: **el último día del
mes en curso**. Si hay que extenderlo, se vuelve a pedir cuando octubre
exista, y queda como otro movimiento en el historial. El eventual sigue
entrando sin fin, porque una contingencia no lo tiene.

**Lo que le cambió al implantado al delegar:**

| | |
|---|---|
| **El día se parte** | Quien trabajó media jornada cobra media jornada |
| **Los viáticos se mueven** | El depositado pasa a comprobación con su plazo; el que no se transfirió se cancela. Antes era un letrero que pedía hacerlo a mano |
| **Los días terminados no se tocan** | Ese día ya lo trabajó quien fue |
| **`sale_id` es obligatorio** | Sin nombre no hay cambio. Antes, vacío quería decir "el primero de la lista": en una plantilla de tres cambiaba al que no era, y el fin de semana, cuando la plantilla rota, a cualquiera |
| **Se avisa el choque** | Si el que entra ya estaba ese día, el equipo se quedaría corto |

**Dos tablas para el mismo hecho.** `reemplazo` es la vieja del
implantado y `reemplazo_recurso` la del motor de relevo. Los cambios
nuevos caen en la segunda. El resumen del mes y los relevos del día en
Panorama leen **las dos**, para que el historial que ya existe no
desaparezca de la vista.
"""

assert s.count(VIEJO) == 1, "no encontre la raya"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("BITACORA.md: seccion 11 bis")

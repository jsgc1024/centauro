# El idioma de los correos

20 de septiembre. **Cerrado y construido el mismo día.** Lo que se decidió está en la bitácora, sección 31; esto se queda como el razonamiento de por qué quedó así.

## Decisiones de Salvador

1. **Por omisión, inglés** para el principal: *"normalmente el ejecutivo habla inglés"*.
2. **El solicitante, en el idioma del país** donde se ejecuta: *"normalmente es del país donde se ejecuta la tarea"*.
3. **Principal**, no "ejecutivo", en lo que lee el cliente.
4. El mismo dato manda **los correos, la encuesta y el task sheet**.
5. Las **dos altas** lo capturan: el eventual y el implantado.

## El problema

Los diez correos salen **en español fijo**. El task sheet del mismo
servicio sale en inglés, portugués o español. Así que un ejecutivo
extranjero recibe su hoja en su idioma y, dos horas después, un correo
que dice *"Su equipo de seguridad está en el lugar"*.

Hoy el sistema resuelve el idioma de tres maneras distintas, y ninguna
sirve para el correo:

| Dónde | Cómo se decide hoy |
|---|---|
| App de campo | El país de la plaza. El agente no elige. |
| Task sheet | A mano: un botón por idioma, cada vez. |
| Encuesta | Un parámetro que se pasa al generarla, **inglés** si nadie dice. |
| Correos | No se decide. Español, siempre. |

## La regla, que ya estaba escrita

`textos.py`, el archivo de textos del task sheet, arranca así desde hace
meses:

> *"Por defecto va en inglés, porque el ejecutivo suele ser extranjero."*

**Salvador lo confirmó hoy: por omisión, inglés.** No el idioma del
país. El país dice dónde se presta el servicio, no en qué idioma lee el
que lo contrató.

## De dónde sale

**Dos campos en el servicio**, uno por cada persona que recibe correo:

- `idioma_ejecutivo`
- `idioma_solicitante`

Los dos **arrancan en inglés** y se cambian con un clic en el alta,
junto al nombre y el correo de cada uno. Son dos y no uno porque casi
siempre son distintos: quien pide el servicio suele ser la asistente
local —español— y el ejecutivo es el extranjero.

Quien captura no tiene que hacer nada si el caso es el normal. Un clic
si la asistente es mexicana y quiere sus avisos en español.

## Qué se traduce, y qué no

**Se traduce** lo que escribe el sistema: los asuntos, los cuerpos de
los once avisos, y las claves de la ficha —*Equipo, Unidad, Punto,
Presentación, Horas extra*—. Los puestos ya tienen su tabla en
`textos.py` (*Conductor de seguridad → Security driver → Motorista de
segurança*) y el correo usa esa misma, no una copia.

**No se traduce** lo que capturó una persona: nombres, direcciones,
placas, la agenda, el motivo del cambio del task sheet. Es la misma
regla del task sheet y por el mismo motivo: traducir una dirección la
vuelve inútil para quien tiene que llegar a ella.

## El aviso interno es otra cosa

El correo de cobertura —*"Beatriz Román movió tu servicio"*— no va a un
cliente: va a un consultor de la casa. Ese sale en el **idioma del país
de quien lo recibe**, no en inglés, que es como ya funciona la app de
campo con el personal.

## El mismo dato manda los tres

Una vez capturado, de ahí salen **los correos, la encuesta y el task
sheet**. Hoy la encuesta recibe el idioma a mano con inglés por
omisión —se equivoca sola cuando el ejecutivo es mexicano— y el task
sheet se pide con un botón por idioma cada vez.

Los tres botones del task sheet **se quedan**: sirven para el caso raro
—un ejecutivo que pide su hoja en otro idioma— y para imprimir las tres.
Lo que cambia es cuál sale marcado por omisión.

## Lo que lleva

1. Migración: dos columnas en `servicio`, las dos con `en` por omisión.
2. Un módulo de textos de los avisos, hermano de `textos.py`, con los
   once en tres idiomas.
3. Los cuatro archivos que escriben avisos —`operacion.py`,
   `tasksheet.py`, `encuestas.py`, `auditoria.py`— dejan de escribir el
   texto a mano y lo piden por clave.
4. Dos selectores en la pantalla de alta del servicio, en tres idiomas
   como todo lo demás de la consola.
5. Pruebas: que un servicio recién creado mande en inglés, que el
   cambiado mande en el idioma elegido, y que el aviso interno no siga
   al cliente.

## Lo que no se toca

La consola (cada usuario ya tiene su idioma), la app de campo (el país
de la plaza, decisión del 19 de septiembre), y el implantado, que no
tiene avisos propios.

## Lo que quedó decidido al construirlo

1. El **idioma del correo se congela al escribir el aviso**, no al
   mandarlo. Si alguien corrige el idioma del servicio después de que
   el aviso ya se escribió, ese aviso sale como se escribió. Propongo
   dejarlo así: es como funciona hoy el cuerpo del aviso, y reescribirlo
   al vuelo obligaría a guardar la clave y los datos en vez del texto.
   **Así quedó.** Lo que el despachador pone encima —el botón, la línea
   de lo que vence— sí se arma al mandar, y por eso el aviso guarda su
   idioma en `notificacion.idioma`.
2. ¿Un idioma **por cliente corporativo**, heredado por sus servicios?
   Ahorraría el clic en los clientes que siempre son iguales. Propongo
   dejarlo fuera por ahora y verlo cuando haya clientes reales cargados:
   un mismo cliente puede tener ejecutivos de varios países.

# Usuarios, permisos y contraseñas — propuesta

_Quién entra, qué puede tocar, y cómo recupera su contraseña el que está
en la calle._
_Antes de programar nada. 18 de septiembre de 2026._

---

## Primero, una corrección a la bitácora

La bitácora dice que hay **32 actividades** y que el día que los permisos
salgan de la base "los endpoints no se tocan". Lo conté en el código y no
es así:

| | |
|---|---|
| Actividades declaradas en `permisos.py` | **7** (una de ellas, `ciudades.alta`, ni se usa) |
| Puertas que preguntan por **actividad** (`auth.puede`) | **19** |
| Puertas que preguntan por **rol** (`auth.requiere`) | **59** |

O sea: **tres de cada cuatro puertas del sistema siguen amarradas al rol
en el código**. Un panel de permisos que se construya hoy solo podría
configurar esas 19.

Eso no tira la idea —la dirección es la correcta y el patrón está bien
elegido— pero cambia el tamaño: **el trabajo grande no es el panel, es
mudar 59 puertas de "rol" a "actividad"**, y eso se hace pantalla por
pantalla, con las pruebas pasando en cada paso.

Lo digo de entrada porque si empezamos por el panel, en dos semanas
tendrías una pantalla bonita que casi no controla nada.

---

## Lo que ya está y sirve

- **La pregunta correcta ya se hace.** `auth.puede("servicios.alta")` no
  pregunta por rol. Cuando la lista de actividades salga de la base, esas
  19 puertas no se tocan. El patrón está probado.
- **Los permisos ya se aplican en vivo.** El token trae el rol adentro,
  pero **nadie lo lee de ahí**: en cada petición se vuelve a buscar el
  usuario en la base. Así que quitarle un permiso a alguien surte efecto
  en su siguiente clic, sin cerrarle la sesión. Eso ya está bien resuelto
  y no hay que tocarlo.
- **El límite de intentos existe** (`intentos.py`): ocho fallos por
  correo, cuarenta por IP, quince minutos. Y se abre si Redis no
  contesta, a propósito. El motor de contraseñas se cuelga de ahí.
- **La invitación con vencimiento funciona** (`auth.token_invitacion`,
  72 horas, un solo uso). Es el esqueleto de lo que falta.
- **`ultimo_acceso` ya se escribe** en cada inicio de sesión. El dato
  está desde hace meses y nadie lo enseña.
- **El teléfono ya viene de Odoo y ya está normalizado** con clave de
  país (`telefonos.normalizar`). Esto vale más de lo que parece: es el
  canal para el personal de campo.

---

## Lo que falta de verdad

- **Recuperar** la contraseña. Hay invitación para la primera, no para la
  olvidada.
- **Cambiarla** uno mismo estando dentro.
- El personal de campo **no tiene forma de pedir su acceso** desde la app.
- El panel, que no existe.

---

## La idea 1: dos puertas, porque son dos mundos

No es una preferencia de diseño: el personal de campo y el de oficina
tienen niveles de confianza distintos en su correo, y eso decide todo.

### Oficina — consultor, central, finanzas, dirección

Correo corporativo, computadora, navegador. **El correo es un canal que
la empresa controla**: si alguien sale, se le cierra el buzón y con eso
se le cierra la recuperación.

Aquí el flujo de siempre sirve: pide recuperar → le llega un enlace de un
solo uso → pone su contraseña nueva.

### Campo — personal de seguridad

Teléfono, la app, y **correo personal**. Ahí está el problema:

> Un correo personal no lo controla la empresa. Si el gmail de alguien se
> compromete, o si esa persona salió hace tres meses y su gmail sigue
> vivo, **la recuperación por correo le entrega la cuenta**.

Y hay un problema práctico además del de seguridad: mucha gente de campo
no trae el correo configurado en el teléfono. Un enlace por correo es una
llamada al consultor a las seis de la mañana.

**Propongo que para campo el canal sea el teléfono, no el correo.** El
teléfono ya viene de Odoo, ya está normalizado con clave de país, y —lo
que importa— **lo mantiene recursos humanos**: cuando alguien sale, se
actualiza en Odoo y el canal muere solo.

---

## La idea 2: la clave de validación

Pediste que la recuperación sea "personalizada con alguna clave de
validación". Propongo **dos cosas, las dos de Odoo**, porque una sola no
alcanza:

```
  1. El reto      →  su número de empleado
                     Lo sabe él, lo controla la empresa, está en su gafete.
                     Filtra: sin eso no se manda ningún código.

  2. El canal     →  un código de 6 dígitos al teléfono de Odoo
                     Diez minutos de vida, un solo uso.
                     Es lo que de verdad prueba que es él.
```

El número de empleado solo no basta —anda en una lista de asistencia— y
el código solo tampoco, porque cualquiera que sepa un correo podría hacer
sonar el teléfono ajeno. Juntos sí.

**Lo que NO propongo guardar**, y quiero decirlo explícito: nada de
número de identificación oficial, ni CURP, ni los últimos dígitos de una
credencial. Son datos sensibles, y si la base se filtra el daño es de
otro tamaño. El número de empleado es interno y no sirve fuera de
Centauro.

**Pendiente de resolver:** hoy `Persona` no tiene número de empleado —
tiene `odoo_id`, que es interno del sistema. Habría que traerlo de Odoo,
que es una línea en la sincronización que ya existe.

---

## La idea 3: las categorías

Pediste configurar lo que cada colaborador **ve** y lo que **modifica**,
por categorías. Se arma en tres capas, y cada una resuelve un problema
distinto:

```
┌─ ACTIVIDAD ────────────────────────────────────────────────┐
│  "servicios.ver"      Ver los servicios y su avance        │
│  "servicios.alta"     Dar de alta un servicio              │
│  La unidad mínima. Ya existe el patrón: ver y editar son   │
│  actividades distintas, no un permiso con dos niveles.     │
└────────────────────────────────────────────────────────────┘
              ↓ se agrupan en
┌─ CATEGORÍA ────────────────────────────────────────────────┐
│  "Consultor"          38 actividades                       │
│  "Consultor junior"   21 — ve todo, no autoriza dinero     │
│  "Central"            17                                   │
│  Se crean y se editan desde el panel. Es lo que el 95%     │
│  de la gente va a tener, tal cual.                         │
└────────────────────────────────────────────────────────────┘
              ↓ y encima, por persona
┌─ EXCEPCIÓN ────────────────────────────────────────────────┐
│  Beatriz: Consultor  +  "nomina.ver"                       │
│  Con quién se la dio y cuándo.                             │
│  Para el caso real que no cabe en ninguna categoría.       │
└────────────────────────────────────────────────────────────┘
```

**Por qué tres capas y no dos.** Sin categorías, configurar a cada
persona actividad por actividad es un trabajo que nadie sostiene y donde
los errores no se ven. Sin excepciones, cada caso raro obliga a inventar
una categoría nueva y en un año hay catorce categorías que nadie sabe en
qué se diferencian.

La excepción lleva **quién la dio y cuándo**, y eso es la mitad del
punto: un permiso suelto sin dueño es el que nadie se atreve a quitar.

**El rol no desaparece.** Sigue siendo lo que decide cosas que no son
permisos —el personal de seguridad solo actúa sobre sus propias jornadas,
por ejemplo, y eso no es una actividad, es una regla de negocio. La
categoría dice *qué puede tocar*; el rol dice *qué clase de usuario es*.

---

## Lo que se vería en pantalla

```
┌─ Accesos ──────────────────────────────────────────────────────┐
│                                              [ Dar de alta ]   │
│  ● Ana Solís           Consultor        hace 12 min            │
│    ana.solis@centauro.lat                                      │
│                                                                 │
│  ● Beatriz Román       Consultor  +1    ayer 18:40             │
│    beatriz.roman@centauro.lat                                  │
│                                                                 │
│  ○ Luis Mendoza        Personal de seguridad    nunca entró    │
│    luismendoza88@gmail.com          ⚠ sin contraseña           │
│                                                                 │
│  ○ Carlos Vega         Central          hace 4 meses           │
│    carlos.vega@centauro.lat         ⚠ revisar                  │
└────────────────────────────────────────────────────────────────┘
```

Tres cosas de este recuadro, y las tres son el punto:

**"Nunca entró" y "hace 4 meses" son las dos alertas que importan.** Una
cuenta que nunca se usó es un acceso que se dio y no se ocupó; una que
lleva meses dormida es una puerta abierta a nombre de alguien que quizá
ya no está. Ese dato ya se guarda y nadie lo ve.

**El `+1` es la excepción.** Se ve de un vistazo quién tiene algo fuera
de su categoría, sin abrir a nadie.

**El correo personal se ve distinto.** No es un adorno: es el recordatorio
de que esa cuenta no se recupera por correo.

Y la pantalla de una persona: su categoría, sus excepciones con quién y
cuándo, su último acceso, y los botones de **reenviar invitación**,
**forzar cambio de contraseña** y **desactivar** —que no es lo mismo que
borrar, porque su rastro en la bitácora tiene que seguir apuntando a
alguien.

---

## Los candados que no se pueden olvidar

Un panel de permisos mal hecho es la forma más rápida de quedarse fuera
del propio sistema.

- **No se puede quitar el último administrador.** Ni desactivarlo.
- **Nadie se quita a sí mismo su propio permiso de administrar.** Si hay
  que hacerlo, que lo haga otro.
- **Todo cambio de permiso va a la bitácora**: quién, a quién, qué
  actividad, cuándo. Es la pregunta que se hace después de un problema, y
  si no está escrita no hay respuesta.
- **Un permiso que se quita surte efecto de inmediato**, sin esperar a
  que expire su sesión. Esto ya funciona así; solo hay que no romperlo.
- **El código de recuperación nunca viaja en la URL** —igual que el
  token— y el mensaje de "te mandamos un código" es el mismo exista o no
  la cuenta.

---

## Lo que necesito que resuelvas

1. **¿Las categorías reemplazan al rol o conviven?** Yo las haría
   convivir —el rol para las reglas de negocio, la categoría para los
   permisos— pero significa que al dar de alta un acceso se eligen dos
   cosas, y hay que explicar la diferencia una vez.

2. **¿Quién administra el panel?** Solo administración, o también
   dirección de operaciones para su gente. Cambia quién puede darle a
   alguien un permiso que cuesta dinero.

3. **Los "tiempos de gestión" que mencionaste.** Sigo sin saber cuál de
   las dos cosas es: ¿cuánto dura una sesión abierta antes de caducar
   —hoy son 12 horas, y para alguien en la calle eso es volver a entrar a
   media jornada—, o cuánto tarda cada quien en despachar lo suyo, que es
   un reporte de productividad y es otra pantalla?

4. **¿Mandamos los códigos por SMS o por WhatsApp?** Los dos cuestan por
   mensaje y hay que contratar proveedor. WhatsApp llega mejor en campo;
   SMS no depende de que traigan datos. Se puede empezar con uno.

5. **El número de empleado.** ¿Existe en Odoo y lo conoce la gente de
   campo? Si no lo trae en el gafete, no sirve como reto y hay que buscar
   otro.

---

## Cómo lo partiría

**Uno.** Cambiar la contraseña estando dentro, y recuperarla por correo
para oficina. Es lo más chico, no necesita panel ni proveedor de
mensajes, y tapa el hueco de hoy.

**Dos.** La recuperación de campo: reto, código al teléfono, contraseña
nueva desde la app. Necesita el proveedor de mensajes contratado.

**Tres.** El panel, en solo lectura primero: quién tiene acceso, con qué
categoría, cuándo entró por última vez. Ya con eso ves cosas que hoy no
ves.

**Cuatro.** Que el panel escriba: categorías, excepciones, activar y
desactivar. Con sus candados.

**Cinco, y el más largo:** mudar las 59 puertas que todavía preguntan por
rol. Va en paralelo con todo lo demás, pantalla por pantalla, y es lo que
hace que el panel de verdad controle el sistema y no una esquina.

---

# Lo que encontré al auditar

_Agregado el 18 de septiembre, después de revisar las 251 puertas del
sistema una por una._

---

## Lo que está bien, y conviene saberlo

Barrí todos los endpoints buscando cuáles no piden credenciales. Salieron
**quince**, y las quince están bien:

- `/`, `/salud`, el logo y la raíz de la consola. Públicas a propósito.
- **Iniciar sesión** y **establecer contraseña**. No pueden pedir sesión:
  son la puerta.
- **La llave pública de push.** Es pública por definición.
- **Las tres de encuestas.** El ejecutivo del cliente no es usuario del
  sistema, así que entra por un enlace con token. Revisé el token:
  `secrets.token_urlsafe(24)` — 192 bits, no se adivina ni se enumera.

Cinco más que mi barrido marcó (`crud.py`) resultaron **falsa alarma**:
sí están protegidas, con variables locales que mi script no veía.

También revisé lo que alcanza el rol de campo, que es la pregunta que
importa aquí: **si roban un teléfono, ¿qué se llevan?** El rol de campo
solo aparece detrás de `CAMPO = auth.requiere(PERSONAL_SEGURIDAD)` y
siempre acompañado de una comprobación de pertenencia —"esta jornada es
suya", "este viático es suyo"—. El catálogo completo, con teléfonos,
tarifario y comisiones, ya está cerrado para ese rol, con un comentario
que dice que estuvo abierto y se cerró. Bien.

**Y los permisos se aplican en vivo**: el token trae el rol adentro pero
nadie lo lee de ahí. Cada petición vuelve a buscar al usuario en la base
y revisa que siga activo.

---

## Los tres agujeros

No están en quién puede entrar. Están en **qué se puede hacer con una
cuenta después de dársela**.

### 1. No se le puede cortar el acceso a nadie

`Usuario.activo` se **lee** en tres lugares —y el candado funciona: en
cuanto está en falso, la sesión abierta muere en la siguiente petición—
pero **no se escribe en ninguna parte del sistema**.

No hay endpoint, no hay pantalla, no hay comando.

> Hoy, para cortarle el acceso a alguien que se fue enojado, hay que
> abrir Postgres y escribir un UPDATE a mano.

El candado está puesto y nadie tiene la llave.

### 2. No se le puede cambiar el rol a nadie

`Usuario.rol` se escribe en un solo lugar de todo el sistema: `seed.py`,
que es el sembrado de demostración.

Promover a alguien de central a consultor, o quitarle finanzas a quien
cambió de puesto, hoy también es SQL a mano. Y como el rol es lo que
decide **todo** lo que puede tocar, es la operación más delicada del
sistema y es la que no existe.

### 3. La baja en Odoo no cierra el acceso

Esta es la que me preocupa.

`odoo.sincronizar_personal` actualiza **solo los campos que se le
nombran**: nombre, teléfono y foto. `activo` no está en esa lista. Y
`_sincronizar` nunca da de baja a nadie: si una fila ya no viene en el
envío, no pasa nada.

Entonces:

> Recursos humanos da de baja a alguien en Odoo. Odoo es la fuente de
> verdad de empleados. **En Centauro su cuenta sigue viva**, con su
> contraseña, su rol y todo lo que veía.

Y se junta con el número 1: aunque alguien se diera cuenta, no hay forma
de cerrarla sin entrar a la base.

Para una empresa cuyo producto es la protección, un exempleado con sesión
válida que ve dónde está cada ejecutivo en este momento no es una falla
de software. Es la falla.

---

## Lo que esto le hace a la propuesta

Cambia el orden. El panel de permisos es importante, pero **no es lo
urgente**: lo urgente es poder cerrar una puerta.

Y cambia el paso uno:

**Uno (nuevo).** Desactivar y reactivar un acceso, y cambiar su rol. Con
sus candados —no se puede quitar el último administrador, nadie se
degrada a sí mismo— y su renglón en la bitácora. Es chico, no necesita
panel ni proveedor de mensajes, y tapa el agujero que hoy solo se tapa
con SQL.

**Uno bis.** Que la sincronización de Odoo traiga la baja: el que ya no
está en Odoo se desactiva aquí, y queda escrito que lo desactivó la
sincronización y no una persona. Eso cierra el ciclo sin depender de que
alguien se acuerde.

Lo demás sigue como estaba propuesto: contraseña, recuperación de campo,
panel de lectura, panel de escritura, y la mudanza de las 59 puertas.

---

## Una pregunta más para la lista

**¿La baja en Odoo desactiva sola, o solo avisa?** Desactivar solo es lo
correcto y lo rápido, pero significa que un error de captura en Odoo deja
a alguien fuera del sistema a media jornada. La alternativa es que
aparezca en el panel como "dado de baja en Odoo, sigue activo aquí" y que
alguien lo confirme. Yo desactivaría solo —el riesgo de dejar una puerta
abierta pesa más que el de cerrarla de más— pero es tu operación.

---

## Decidido (18 sep)

**La baja en Odoo desactiva sola.** No avisa y espera: cierra. El riesgo
de dejar una puerta abierta pesa más que el de cerrarla de más, y si fue
un error de captura en Odoo, se corrige en Odoo y la siguiente
sincronización lo reactiva.

Eso deja dos cosas que hay que resolver antes de programarlo, porque las
dos pueden convertir una buena decisión en un apagón:

### ¿Qué manda Odoo: el padrón completo o solo los cambios?

Es la diferencia entre que funcione y que un martes se quede la empresa
entera sin sistema.

- Si Odoo manda **el padrón completo**, "no vino en el envío" puede
  querer decir "ya no está" y la baja se deduce sola.
- Si Odoo manda **solo lo que cambió** —que es lo normal en una
  sincronización— entonces "no vino" quiere decir "no cambió", y deducir
  la baja de ahí **desactivaría a todos los que no cambiaron ese día**.

Hoy `_sincronizar` hace lo segundo sin decirlo: recorre lo que llega y no
toca lo demás. Así que la baja tiene que venir **dicha**, con un campo
explícito, y no deducida de una ausencia. Si algún día se manda el padrón
completo, que venga marcado como tal.

**Sin esa marca, la sincronización no desactiva a nadie.** Es el candado
que evita el apagón.

### Al que se va se le cierra la puerta, pero deja un hueco

Desactivar a alguien que está asignado a servicios de mañana no es solo
un tema de acceso: **esas jornadas se quedan sin esa persona** y nadie se
entera hasta que el equipo no llega.

Así que la baja tiene que decir lo que deja atrás:

```
  Luis Mendoza — dado de baja en Odoo, acceso cerrado

  ⚠ Estaba asignado a 6 jornadas a partir de mañana:
    CN-2026-0151 · jue 19 a sáb 21
    CN-2026-0148 · lun 23 a mié 25          [ Ver y reasignar ]
```

No las quita solo —eso sería el sistema decidiendo dejar un servicio sin
gente— pero tampoco se calla. Enlista y avisa, que es la misma regla de
la casa: el sistema propone, el consultor decide.

---
## Decidido: el rol y la categoría conviven

El **rol** dice qué clase de usuario es y sigue mandando en las reglas de
negocio —"solo sus propias jornadas", "solo su propio viático"—, que hoy
están escritas, probadas y funcionando. La **categoría** dice qué puede
ver y qué puede modificar.

Al dar de alta un acceso se eligen dos cosas. Hay que explicar la
diferencia una vez, y a cambio no se reescribe nada de lo que ya sirve.

---

## Decidido: quién administra el panel

**Administración y dirección general.** Dirección general queda como
super administrador, con alcance a todo.

Esto **cambia a propósito una raya que ya existía**. En `auth.py`,
`HEREDA` le daba a dirección general todo lo operativo —operaciones,
consultor, central, finanzas— pero explícitamente **no** la
administración de catálogos y tarifarios, con este comentario:

> _La direccion general alcanza todo lo operativo, pero no la
> administracion de catalogos y tarifarios, que queda en el rol de
> administracion._

La razón de aquella raya era de control interno: quien aprueba un margen
no debería poder cambiar en silencio el precio con el que se calcula ese
margen. Se le planteó a Salvador con esa razón encima de la mesa y
decidió que dirección general alcance todo.

**Queda escrito que fue una decisión y no un descuido.** La consecuencia
práctica: un cambio de tarifario hecho por dirección general queda
respaldado por la bitácora y no por un candado, así que **la bitácora de
cambios de tarifario deja de ser un lujo** — es lo único que queda. Hay
que verificar que esos cambios se estén registrando; si no, eso entra al
alcance de este trabajo.

---
## Decidido: los tiempos de gestión

Salvador no recuerda a qué se refería cuando lo pidió. Se resuelve así:

- **La duración de sesión entra al panel**, configurable por categoría.
  Pertenece ahí de todos modos, y hoy está mal: son 12 horas parejas para
  todos. Alguien en la calle vuelve a entrar a media jornada, y una
  computadora de oficina que se queda prendida sigue abierta toda la
  tarde.
- **El reporte de productividad** —cuánto tarda cada quien en despachar
  lo suyo— se anota como pantalla aparte, por si era eso. No es del panel
  de accesos.

---

## Decidido: el código lo dicta el consultor

Nada de SMS ni WhatsApp. El agente llama a su consultor, el consultor
genera el código desde la consola y se lo dicta.

Funciona desde el primer día, sin proveedor y sin costo por mensaje. Y no
cierra la puerta: el día que se quiera mandar por mensaje, lo que cambia
es **cómo se entrega** el código, no cómo se genera.

**Solo su consultor.** No la central, no cualquier consultor. El que
mejor lo conoce es el más difícil de engañar.

**El costo, dicho en voz alta:** si el consultor no contesta a las 5:40
de la mañana, ese agente no entra, y el servicio arranca sin app —sin
marcas, sin geocerca, a ciegas—. Si en la práctica resulta que pasa
seguido, agregar a la central es un renglón. Queda anotado, no se hace
ahora.

**Sin dato de verificación adicional.** Se propuso traer el número de
empleado de Odoo para que el consultor lo preguntara antes de dictar; se
decidió que con reconocer la voz basta. Así que Odoo no se toca para
esto.

### Contra qué hay que blindarlo

Este camino tiene un riesgo conocido y con nombre: **"hola, soy Luis, se
me olvidó la contraseña"**, a las seis de la mañana, con el consultor a
medio despertar. Es la forma más común de robarse una cuenta en
operaciones así. Cuatro reglas, y ninguna cuesta:

| | |
|---|---|
| El código sale **a la pantalla de quien lo genera** | Nunca una lista de códigos, nunca por correo |
| **Dura poco y sirve una vez** | Diez minutos. Si se venció, se pide otro |
| Queda escrito **quién se lo dio a quién** | Un código entregado sin dueño es el que nadie investiga |
| **El agente pone su contraseña él mismo** | El consultor nunca la sabe, ni antes ni después |

---

## Cómo queda el plan

La decisión del canal quita el único bloqueo externo que tenía esto: ya
no hay que contratar proveedor de mensajes ni esperar aprobación de
plantillas. Todo se puede hacer de corrido.

**Uno.** Cerrar una puerta: desactivar, reactivar y cambiar rol, con sus
candados —no se puede quitar el último administrador, nadie se degrada a
sí mismo— y su renglón en la bitácora. **Es lo urgente**: hoy eso solo se
hace con SQL a mano.

**Uno bis.** Que la baja de Odoo desactive, con el campo explícito que
evita el apagón, y que diga qué jornadas deja huérfanas.

**Dos.** Cambiar la propia contraseña estando dentro, y recuperarla por
correo para oficina.

**Tres.** La recuperación de campo: el consultor genera, dicta, el agente
la pone desde la app.

**Cuatro.** El panel en solo lectura: quién tiene acceso, con qué
categoría, cuándo entró por última vez, quién nunca entró.

**Cinco.** Que el panel escriba: categorías, excepciones, duración de
sesión.

**Seis, y el más largo:** mudar las 59 puertas que todavía preguntan por
rol. En paralelo, pantalla por pantalla. Es lo que hace que el panel de
verdad controle el sistema y no una esquina.

---

## Lo que queda pendiente de verificar antes de empezar

- **¿Se registran los cambios de tarifario en la bitácora?** Al quitarle
  el candado a dirección general, esa bitácora pasó de ser un lujo a ser
  lo único que queda. Si no se están registrando, entra al alcance.
- **¿Odoo puede mandar un campo de baja explícito?** De eso depende que
  la baja automática sea segura.

---
## Verificado: no hay bitácora de catálogos, y no cabe en la que existe

Se fue a revisar si los cambios de tarifario quedaban registrados, para
saber qué respaldaba un cambio de precio ahora que dirección general
queda sin candado. La respuesta es que **no queda nada registrado**, y
por dos razones que se suman:

**`crud.py` no menciona la auditoría ni una vez.** Es la fábrica por
donde se editan los tarifarios, las tarifas de recurso, de vehículo, de
freelance y **las comisiones del personal**. Crear, editar y desactivar
no dejan rastro de quién lo hizo.

**Y no cabe en la bitácora que existe.** `RegistroAccion.servicio_id` es
obligatorio: esa bitácora está amarrada a un servicio por diseño, y un
cambio de tarifario no tiene servicio al cual colgarse.

Así que la frase de más arriba —"queda respaldado por la bitácora y no
por un candado"— era falsa: **hoy no hay ni candado ni bitácora**.
Cualquiera con rol de administración puede cambiar el precio que se le
cobra al cliente, o lo que se le paga a cada rol, y no queda nada
escrito. Esto ya era así antes de tocar nada; quitarle el candado a
dirección general solo agrega una persona más a esa lista.

**Entra al alcance de este trabajo:** una bitácora de catálogos, que es
una tabla nueva porque la que hay no sirve para esto. Quién, qué
catálogo, qué fila, valor anterior y valor nuevo.

---

## Pendiente con quien lleva Odoo

**¿Odoo puede mandar el estado de cada empleado?** De eso depende que la
baja automática sea segura:

- Un campo **activo/inactivo por empleado** es lo ideal: la baja viene
  dicha y no hay forma de provocar un apagón.
- El **padrón completo** en cada envío también sirve, si viene marcado
  como completo, porque entonces "no vino" sí significa "ya no está".
- **Solo los que cambiaron** —que es lo normal— no permite deducir
  ninguna baja, y ahí la desactivación automática no se puede hacer.

Mientras se resuelve, **el paso uno se construye igual**: desactivar a
mano desde el panel. La baja automática se conecta después sin rehacer
nada.

---
## Decidido: el código de campo son cuatro dígitos

Dictar `4827` por teléfono a las seis de la mañana es mucho mejor que
dictar `938142`. Y la fricción también es seguridad: un código que se
dicta mal tres veces acaba en que alguien lo mande por WhatsApp.

**La condición técnica no es negociable:** cuatro dígitos son diez mil
combinaciones, y sin candado un programa las prueba todas en segundos.

| | |
|---|---|
| **Cinco intentos y el código se muere** | Por código, no por minuto. Con "cinco por minuto" y diez minutos de vida son cincuenta intentos, y eso ya no alcanza |
| **Diez minutos de vida** | Vencido, se pide otro |
| **Un solo uso** | |
| **Se guarda cifrado** | Diez minutos es poco tiempo, pero un código en texto plano en la base es una cuenta regalada si la base se filtra |

Con esas cuatro, la probabilidad de adivinarlo es 5 entre 10,000 y solo
durante diez minutos.

---

## Decidido: lo generan su consultor y la central

No "cualquier consultor". Lo único que protege este camino es que quien
entrega el código **reconozca la voz de quien llama**, y cada persona que
puede generarlo sin conocer al agente es una puerta por la que alguien se
cuela diciendo "soy Luis".

- **El consultor** lo conoce.
- **La central** está despierta a las 5:40, que es cuando de verdad pasa,
  y es un equipo chico cuyo trabajo es justo atender incidentes.

Entre los dos se cubre el horario completo sin abrir la puerta a docenas
de personas.

**Y cierra solo el hueco que quedaba:** alguien que regresa de descanso,
todavía sin asignar a ningún servicio, no tiene "su consultor" —el
sistema sabe quién es el consultor de cada servicio, no de cada
persona— pero la central siempre puede.

Así que la regla queda: **la central, siempre; el consultor, cuando esa
persona esté asignada a alguno de sus servicios.**

---
## Decidido: el consultor lo genera desde el teléfono

La llamada de las 5:40 le llega en su casa. Si para resolverla tiene que
prender la computadora, el agente arranca sin app.

**La consola ya es responsiva** —viewport declarado, rejillas que se
colapsan a una columna a 800px, reglas propias para la tira del día y la
tabla por país— así que la tarjeta no es rehacer nada: es diseñarla
angosta desde el principio.

**Pero la fricción no está en la tarjeta, está en llegar a ella.** Menú,
cartera, encontrar el servicio, bajar hasta la persona, con una mano. Eso
es un minuto largo a las 5:40.

Por eso la entrada cambia:

- **Una pantalla propia, a un toque del menú, con un buscador.** Se
  escribe "Luis", sale su ficha y el botón. El consultor ve solo a su
  gente; la central ve a todos. Sirve igual en teléfono y en
  computadora.
- **El botón dentro del servicio** se queda como atajo para cuando ya
  estás ahí, en la computadora.

Una pantalla que sirve para las dos cosas, en vez de una de escritorio y
otra de teléfono.

### Lo que la tarjeta enseña, y por qué

Como se decidió que no hubiera número de empleado, **la voz es lo único
que verifica**. Así que la tarjeta le da al que entrega el código algo
más que preguntar:

| | |
|---|---|
| **Foto** | La central no conoce a todos |
| **Teléfono** | "¿De qué número me llamas?" — barato y sirve |
| **Dónde está hoy** | Si dice que entra a las seis y el sistema no le ve nada hoy, algo no cuadra |

Y dos reglas de la tarjeta misma:

- **El código no se vuelve a mostrar.** Si se cierra, se generó y se
  acabó: hay que pedir otro, y el anterior muere. Así nadie acumula una
  lista de códigos vigentes en una pestaña abierta.
- **Si ya tiene uno vigente, se avisa antes de generar otro** —"vence en
  6:12, ¿generas otro? el anterior deja de servir"— para que el
  consultor no dicte tres seguidos y el agente no sepa cuál va.

---

# Bitácora de decisiones — Centauro

Todo lo que se decidió y por qué, para que no se pierda y para que
nadie —ni nosotros dentro de tres meses— tenga que adivinar de dónde
salió una regla. Lo que está aquí es lo que el sistema hace hoy, más lo
que falta y lo que está esperando una decisión tuya.

Lo técnico de la app de campo vive aparte, en `APP_CAMPO.md`.
Las dos fallas de seguridad abiertas viven en `REVISION.md`.

---

## 1. El rol es de la tarea, no de la persona

**La decisión.** El personal de seguridad es general. El consultor
decide qué rol va a tener cada quien **en cada tarea**. Son cuatro:

| Código | Rol |
|---|---|
| `conductor_seguridad` | Conductor de seguridad |
| `agente_seguridad` | Agente de seguridad |
| `coordinador_seguridad` | Coordinador de seguridad |
| `consultor_seguridad` | Consultor de seguridad |

Los cuatro pueden ir a un mismo servicio.

**Qué cambió.**

- El perfil **desapareció de la ficha de la persona**. La columna
  `persona.perfil_id` se eliminó (migración `b83f16a09d2e`).
- El rol vive en la asignación: `asignacion_personal.rol_id` y
  `persona_implantado.rol_id`.
- **El dinero sale del rol de la tarea**, no de la persona. La comisión
  se busca por el rol con el que la persona fue asignada ese día.
- Aplica a **eventual e implantado a la vez**.
- Se hizo *backfill* desde el perfil viejo, para que ningún servicio
  anterior pierda de dónde salió su número.

**Por qué importa.** Un agente que un jueves maneja cobra como
conductor ese jueves. Antes cobraba como agente porque así decía su
ficha, y la diferencia la absorbía la empresa sin que nadie la viera.

**Dónde se atora a propósito.** Si se cotizó un rol y se ejecutó otro,
el **cierre** se detiene y dice cuál fue —no la nómina. Para entonces
ya sería tarde.

---

## 2. El implantado

### Apertura del mes siguiente

El implantado no se vuelve a vender cada treinta días: se vende una vez
y se opera hasta que alguien lo cancela. Por eso el mes siguiente **no
se captura, se abre**, con los mismos términos y la misma plantilla.

- Con un botón del consultor, o solo por el proceso de cada mañana
  (`abrir_los_que_toquen`), faltando **7 días o menos** para que
  termine el mes en curso (`DIAS_ANTES`).
- **Tope: un mes por delante.** Se puede tener abierto el mes en curso
  y el que sigue, no más. Abrir diciembre en septiembre sería congelar
  tres meses de plantilla contra una realidad que todavía no existe.
- Abrir un mes **no regresa a "planeado"** un servicio que ya arrancó:
  solo empuja al que todavía no llegaba ahí (`ANTES_DE_PLANEAR`).
- El botón apagado **dice su razón**. Un botón que no hace nada y no
  explica por qué fue el problema que ya vimos con el primer mes.

### La hoja no se libera con días en ámbar

Mientras haya días en ámbar, la hoja no se libera. El ámbar es
justamente "esto todavía no está resuelto"; liberar con ámbar es
publicar una hoja que sabemos incompleta.

### Viáticos del implantado: independientes

Módulo propio (`app/viaticos_implantado.py`), endpoints propios,
pantalla propia. Solo comparte con eventual el motor de cálculo.

- El **tabulador es por servicio**, porque el acuerdo cambia con cada
  cliente. Vive en la sección del acuerdo.
- **Cierre mensual.**
- El tabulador del implantado **no trae medio día ni transfer**:
  implantado son jornadas de 12 horas.

### Cambio de unidad por taller

Pantalla propia: cuando la unidad entra a taller, se cambia sin tocar
el resto del mes.

### Hospitales

Se traen de Google con el **nivel marcado por Centauro** —el nivel no
se adivina—, más carga manual de Monterrey y Guadalajara.

---

## 3. Cuidado con la API de Google

Se excedió una vez (429) y se corrigió:

- No se vuelve a preguntar por los que ya están completos.
- Tope con `--max`, filtro con `--solo`.
- Pausa de 0.4 s entre llamadas, reintentos a 4 s y 12 s.
- Una diferencia de nombre dejó de contar como cambio pendiente.

**La llave:** vive **solo en el servidor**; el navegador nunca la ve.
Se pega a mano en `.env` (con nano o TextEdit, nunca con `echo`, para
que no quede en el historial). Restringida **por IP del servidor**, no
por referrer. Solo Places API (New) y Maps Static API habilitadas.

`searchText` acepta un radio **máximo de 50 000 m**.

---

## 4. Las tres pantallas nuevas

### Monitoreo (antes "Central")

La central de inteligencia. El alcance que dictaste: **anticiparse a
cualquier situación, controlar la operación y prevenir incidentes**, y
el punto más importante de todo es el **seguimiento al meet and greet y
al inicio de servicio del día siguiente**.

Constantes que gobiernan el tablero:

| Constante | Valor | Qué es |
|---|---|---|
| `CORTE_DE_LA_VISPERA` | 18:00 | A esa hora lo de mañana ya debía estar listo |
| `SILENCIO_AMBAR` | 30 min | Sin marca: se mira |
| `SILENCIO_ROJO` | 60 min | Sin marca: se llama |
| `AVISO_HORAS_EXTRA` | 30 min | Antes de que la jornada se pase |
| `DIAS_DE_LA_TIRA` | 7 | La banda de la semana |

La revisión del día tiene **diez puntos**: punto de encuentro, personal,
rol, confirmación, unidad, hoja, vuelo, hora, viáticos y hospitales.

Ven la pantalla: central, dirección, admin **y consultor**.

### Gastos (antes "Finanzas")

Todo lo relacionado con **viáticos y compras por solicitud de servicio**
—es decir, todos los gastos del servicio **menos** las nóminas del
personal de seguridad. Depositado, por comprobar, devoluciones y corte,
separados por país.

Se agregó lo que faltaba: **la firma del depósito** (quién confirmó y
cuándo) y **la foto del comprobante**.

### Nómina

Dos tablas de tabulador —eventuales e implantados—, cada una con sus
roles y su modalidad. Las reglas que dictaste:

- **Cortes semanales, lunes ~12:00 pm.**
- Los **implantados** se pagan a cierre de semana, **por los días en
  verde**.
- Si ya se pagó y después se detecta un error —el servicio se regresa
  para corregir—, **el ajuste va al siguiente corte**. Ni de más ni de
  menos. Aplica igual a eventual y a implantado.

Se agregó `concepto_nomina.rol_id`: el pago guarda **con qué rol** se
pagó, que es lo que explica el monto.

---

## 5. El patrón que se repitió tres veces

En tres lugares distintos estaba pasando lo mismo: **el dato que
explica un monto no se estaba guardando**. Los tres se cerraron:

1. **La firma del depósito** — quién confirmó la transferencia y cuándo.
2. **El rol del pago** — con qué rol se pagó ese día.
3. **La hora de llegada de una marca** — cuándo llegó de verdad, no
   cuándo se sincronizó.

Vale la pena revisar cualquier monto nuevo contra esta pregunta: *si
mañana alguien reclama este número, ¿guardamos de dónde salió?*

---

## 6. La app de campo

Web app, mismo diseño que la consola, fondo blanco. Alcance que
dictaste:

- Visualización de sus servicios pendientes.
- Visualización y gestión del servicio en curso.
- Gestión de sus viáticos por servicio.
- Visualización de sus comisiones por servicio y al corte de semana.

Más lo que se agregó y aprobaste: **revisión de unidad con fotos** y
**notificaciones push**.

**El teléfono de la central: +52 55 5022 1022.** Es el número que marca
el botón de pánico. Vive en la configuración (`telefono_central`), no en
la ficha de quien esté de turno: el turno cambia cada ocho horas y el
número al que se llama en una emergencia no puede cambiar con él. El
nombre sí sale del usuario en turno, para que el de campo sepa con quién
va a hablar.

Detalles de diseño en `APP_CAMPO.md`. Lo que conviene no olvidar:

- Un paso a la vez. Seis botones son seis oportunidades de marcar el
  equivocado con prisa.
- Lo que no se pudo mandar se ve arriba hasta que sale.
- Sin señal se muestra lo último que se supo **con su edad escrita**. Un
  dato viejo que se sabe viejo sirve; uno viejo que se ve nuevo es peor
  que no tener nada.
- El botón rojo está en todas las pantallas.
- La app y la consola comparten origen y sesión: por eso existe la
  pantalla "entrar con otra cuenta".
- Una app web **no puede** tomar ubicación en segundo plano, y la
  geolocalización exige **HTTPS** (`localhost` está exento).

### Revisión de unidad

**Por servicio, y solo cuando la unidad cambia de manos.** Un implantado
que usa la misma camioneta veintidós días no la revisa veintidós veces:
lo que se revisa es el cambio, no el día.

- **Cuatro fotos obligatorias**: frente, atrás, los dos costados. Más
  fotos sueltas de golpes que ya trae.
- Kilometraje y **tanque en octavos** —pedir litros es pedir que alguien
  invente un número.
- Nota, y **firma con el dedo**.
- Fotos con **hora y ubicación**. Una foto sin cuándo ni dónde no prueba
  nada.
- **Comparación lado a lado**: al entregar, cada foto sale junto a la de
  cuando la recibió. Ahí es donde un golpe nuevo salta solo.
- Al entregar sale sola la **diferencia de kilometraje**: el número que
  nadie apunta y del que después todos se acuerdan distinto.
- En la consola, el historial por unidad: quién la tuvo, cómo la recibió
  y cómo la dejó.

Las fotos **no se encolan** cuando no hay señal: son medio mega y la
cola vive en el teléfono. Se dice que no salió y se pide reintentar con
señal, con las fotos todavía en pantalla.

### Push

Llaves VAPID generadas con `generar_llaves_push.py`, que las escribe en
`.env` y **solo imprime la pública**. La privada nunca sale del
servidor. Una suscripción que responde 404 o 410 se apaga sola, y un
fallo de aviso nunca tumba a quien lo llamó.

---

## 6 bis. Cerrar un día a mano

**La decisión.** De los dos caminos que estaban sobre la mesa se eligió
**(b): la central puede cerrar un día a mano, con firma de quien lo
cierra.**

**El problema que resuelve.** Un día que se trabajó y que nadie marcó se
queda abierto, y mientras lo esté no entra a nómina. Alguien que trabajó
no cobra por una marca que faltó.

**Por qué con firma.** Cerrar a mano es decir "yo doy fe de que esto
ocurrió así" sin evidencia desde la calle. Eso es exactamente la forma
que tendría un día inventado, así que tiene que verse: queda guardado
quién lo cerró, cuándo y por qué, y se muestra en la bitácora de ese día
para siempre.

**Los candados:**

| Regla | Por qué |
|---|---|
| Solo central y dirección | El consultor vende el servicio: a nadie le conviene más que un día aparezca trabajado |
| Nadie firma un día que trabajó | Firmarse las propias horas es la versión más simple del fraude |
| No se cierra un día que aún no termina | Cerrar por adelantado es pagar trabajo que no ocurrió |
| Justificación de 10 caracteres mínimo | Igual que un ajuste de hito. Dentro de tres meses esa nota es lo único que explica el día |
| No se inventan hitos | Un hito dice "alguien marcó esto desde la calle". Fabricar uno ensuciaría la única evidencia real que hay |

**La pantalla.** Al final de Monitoreo, banda de **"Días sin cerrar"**,
del más viejo al más nuevo —el más viejo es el que más cerca está de
convertirse en un reclamo. Aparece solo si hay algo; una franja que
siempre dice "todo bien" deja de leerse. Las horas vienen llenas con las
programadas, que es lo que casi siempre pasó.

Distingue dos cosas que no son lo mismo: un día que **arrancó y no
cerró** (una marca que faltó) y un día **sin ninguna marca** (del que no
se sabe nada, y hay que preguntar antes de firmarlo).

**Margen:** tres horas después de la hora programada de término
(`HORAS_DE_GRACIA`). Un servicio se alarga, y avisar a las 18:05 de algo
que termina a las 18:00 sería ruido que la central aprende a ignorar.

**Deshacer:** `reabrir` solo deshace lo que la central cerró. Un día que
el equipo marcó desde la calle se corrige ajustando el hito, que es
donde queda el rastro. Si ese día ya se pagó, reabrir no devuelve el
dinero: la diferencia se arrastra como ajuste al siguiente corte.

---

## 7. Cómo se trabaja este proyecto

- **El implantado no mueve nada de eventual.** Si algo llegara a
  impactar, se pregunta antes.
- Las pruebas **nunca** corren contra la base de desarrollo.
- El token JWT **nunca** va en la URL.
- Los enums de Postgres guardan el **nombre** del miembro, y Postgres no
  convierte texto a enum solo: hace falta `::tipo`.
- `Servicio` **no tiene** relaciones `plaza` ni `consultor`, solo
  `plaza_id` / `consultor_id`. Se resuelven con diccionarios traídos una
  vez.
- Las rutas de la consola son **singulares**: `#/servicio/{id}`,
  `#/implantado/{id}`.
- Toda clave `t("…")` tiene que existir **tres veces** (es/en/pt).
- `POST /sistema/sembrar-catalogos` **está abierto sin contraseña y
  reescribe contraseña y rol de todos los usuarios**. Para sembrar
  lugares se usa:
  `docker compose exec -T api python -c "from app.seed import sembrar_lugares; ..."`

---

## 7 bis. Git

El proyecto ya está versionado. Primer commit: `cc74f21`, 261 archivos.

**Lo que no entra al repositorio, a propósito:** `.env` y cualquier
variante suya. Ahí viven la llave de Google Maps y la privada de los
avisos push, y una llave en un repositorio es una factura que se paga
sola. El `.gitignore` ignora `.env*` completo —no solo `.env`— porque un
comando mal tecleado ya creó una vez un archivo llamado
`.envodocker compose restart api` con la llave adentro. Esos dos
quedaron en `backend/_to_delete/envs_rotos/`, que también se ignora.

Tampoco entran `_to_delete/` ni `.pantalla1/`: son los scripts de parche
con que se construyó el sistema, no el sistema.

**Cómo usarlo, en tres comandos:**

```
git status                 # que cambió
git add -A && git commit   # guardar un punto al que volver
git log --oneline          # de dónde venimos
```

Para volver atrás de algo que salió mal: `git diff` para ver qué cambió,
`git checkout -- <archivo>` para deshacer un archivo, `git revert <sha>`
para deshacer un commit entero sin borrar la historia.

Todavía no hay remoto. Mientras no lo haya, la historia vive solo en
esta máquina: un respaldo del disco sigue siendo necesario.

---

## 8. La revisión de septiembre

Tres vueltas al sistema completo: una buscando problemas, otra revisando
los arreglos de la primera, y una tercera prediciendo qué pruebas se
iban a romper antes de correrlas. El detalle está en
`REVISION_2026_09.md`. Lo que hay que recordar:

**Siete agujeros de seguridad**, todos cerrados. El peor: el endpoint de
sembrar catálogos estaba abierto sin contraseña, reescribía el rol y la
contraseña de todos los usuarios, y devolvía la contraseña en la
respuesta. Dos peticiones sin credenciales y cualquiera era director
general. Los otros seis eran del mismo tipo: **pedir sesión no es pedir
permiso**. Un elemento de seguridad freelance tiene sesión, y con ella
llegaba al itinerario de ejecutivos que no protege, a los viáticos de
sus compañeros, y al tarifario completo de la empresa.

**Ocho errores en el dinero**, todos cerrados. El más caro: la misma
corrección se volvía a generar en cada corrida, para siempre. Pagado
800, corresponde 1100, ajuste de +300; se paga; la siguiente revisión
vuelve a ver 800 contra 1100 y genera otros 300. El origen era que
`AjusteNomina` no decía de qué era el ajuste, así que dos cosas
distintas —corregir un pago y descontar viáticos— se pisaban.

**Tres formas de perder un dato que explica dinero** al borrar: un vuelo
ya comprado desaparecía con el equipo, sin quedar ni el número de
reserva.

**Doce cosas de la app y del código nuevo**, casi todas mías de estos
días. La que más pena da: `olvidar("mi-dia")` borraba **toda** la
memoria sin conexión, así que el agente registraba la unidad en un
estacionamiento y ahí perdía la copia guardada de su día, sus viáticos y
sus pagos —justo antes de bajar al sótano.

### Lo que dejó la revisión

`backend/revisar.py`. Un verificador propio que corre sin instalar nada:

```
python3 revisar.py
```

Nació de un `settings` que se usaba arriba y solo se importaba dentro de
una función de más abajo: compilaba, arrancaba, y reventaba en la
primera petición real. Ocho pruebas en rojo por una línea que ningún
compilador iba a señalar. Revisa nombres que no existen, imports que
sobran, funciones de JS que se llaman y no están, claves de idioma que
no estén las tres veces, y la cadena de migraciones. Conviene correrlo
antes de cada `./probar.sh`: tarda un segundo y ahorra cinco minutos.

---

## 9. Cada país con su hora

**El problema.** Las columnas de fecha del sistema son *naive* y guardan
hora de pared del país del servicio: un servicio de São Paulo que
arranca a las 07:00 guarda 07:00. Todo el sistema las comparaba contra
el reloj del servidor, y con el contenedor en México eso dejaba a
Brasil corrido tres horas y a Venezuela dos.

Lo que provocaba, todos los días:

- El conductor que marcaba puntual caía fuera de la ventana permitida,
  se le levantaba alerta y su marca quedaba en revisión.
- Todo servicio brasileño en curso aparecía "sin reporte" en la banda
  roja de la central, desde que arrancaba. Un tablero que siempre grita
  deja de leerse.
- El aviso preventivo de horas extra —una ventana de treinta minutos—
  no coincidía nunca: fuera de México no existía.
- El plazo de 24 horas del consultor para cerrar, del que depende su
  comisión, nacía torcido.

**La decisión.** `Pais` guarda su zona horaria IANA (migración
`f94d1a2e70b5`), y un módulo nuevo —`app/reloj.py`— es el único lugar
que responde qué hora es. El resto del sistema le pregunta a él y no al
servidor:

```
ahora_en(pais)      el instante, en hora de pared de allá
hoy_en(pais)        qué día es allá
Relojes(db)         los relojes de los países, traídos una vez
```

**Lo que NO cambió.** Nada de lo que ya está guardado se convierte. Las
columnas siguen siendo hora de pared del país; lo que cambia es contra
qué se comparan. Y una columna con `timezone=True` guarda un instante
absoluto: esas no tienen nada que ver con esto y ya estaban bien.

**Tres decisiones de diseño que vale explicar.**

Una zona mal escrita en el catálogo no tumba la pantalla: se cae a la
hora de la casa y sigue. Dejar a la central sin monitoreo por una errata
en un nombre sería peor que la errata.

Las consultas que mezclan países no se pueden escribir con tres relojes
en un solo `WHERE`. Se ensancha la ventana por la mayor diferencia
horaria entre países activos (`margen_de_paises`) y se afina después en
Python, país por país. Traer de más y descartar es correcto; traer de
menos es perder un servicio.

La hora del contenedor sigue siendo `America/Mexico_City`, pero ya no
decide nada de operación. Es la hora de la casa: la que se usa cuando no
hay un país de por medio.

**Lo que destapó.** Dos cosas que ya estaban rotas y nadie había visto:

- `viaticos.py` descartaba la zona de una fecha con `tzinfo` en vez de
  convertirla —`.replace(tzinfo=None)` donde iba `.astimezone()`—. Eso
  fallaba también en México.
- La pantalla de **dinero por comprobar** reventaba con 500 al abrirse
  sin fecha, o sea siempre. Ahora cada caja dice con qué hora se midió,
  que es la suya: un viático de São Paulo vence a las 24 horas de São
  Paulo.

**Lo que queda pendiente.** El calendario de Celery es uno solo, en hora
de México: el recordatorio de la víspera sale a las 17:00 de México, o
sea a las 19:00 de São Paulo. La tarea ya calcula bien el "mañana" de
cada país; lo que no está partido por país es la hora a la que se
dispara. El aviso llega —llega tarde.

**Las zonas sembradas.**

| País | Zona |
|---|---|
| México | `America/Mexico_City` |
| Brasil | `America/Sao_Paulo` |
| Venezuela | `America/Caracas` |
| Colombia | `America/Bogota` |
| Argentina | `America/Argentina/Buenos_Aires` |
| Chile | `America/Santiago` |
| Perú | `America/Lima` |
| Panamá | `America/Panama` |

Lo que no esté en esa lista se queda con la hora de la casa.

---

## 10. Los viáticos: el sistema propone, el consultor decide

**La regla.** Dos partes, y las dos son de la casa:

1. **El sistema nunca asigna viáticos por su cuenta.** Calcula lo que
   tocaría por tabulador —para que nadie tenga que ir a buscarlo— y lo
   propone. Quién recibe dinero, cuánto y cuándo lo decide el consultor,
   siempre, sin excepción.
2. **Lo que ya se depositó es de quien lo recibió.** Cada persona de
   seguridad se hace responsable de comprobar su dinero, y esa
   comprobación hace falta para cerrar el servicio. El dinero no cambia
   de dueño porque cambie quien trabaja.

**Por qué.** Un sistema que abre dinero solo es un sistema que gasta sin
que nadie lo haya pedido. Y del otro lado: si al cambiar de persona el
dinero se moviera con el puesto, nadie quedaría obligado a comprobar lo
que ya se llevó, y ese es justo el hueco por donde se pierde.

**Dónde se cumple.** Los tres lugares que crean una asignación de
viáticos —el alta del consultor, el depósito adicional y los dos del
implantado— reciben un monto capturado y guardan quién lo autorizó
(`asignado_por_id`). No hay un cuarto.

**El único que la rompía.** El reemplazo por contingencia le abría
viáticos a quien entraba, con el tabulador, sin que nadie los pidiera
—aunque el que salía no tuviera un peso asignado. Además de gastar solo,
dejaba el cierre trabado: el revisor no deja enviar a finanzas con
viáticos sin comprobar, así que el servicio se quedaba atorado esperando
la comprobación de un dinero que nadie había solicitado.

Ahora el reemplazo devuelve la propuesta y el consultor la asigna con el
botón de siempre:

> A Luis Mendoza le tocarían $1,152 por tabulador (2 días).
> Se los asignas tú.

Y lo que el que sale ya tenía encima no se toca: pasa a comprobación con
su plazo de 24 horas, a su nombre. Lo que todavía no había salido se
cancela, porque esa persona ya no va a trabajar ese día.

---

## 11. El relevo a media jornada

**El agujero.** El reemplazo por contingencia hacía esto:

```python
asignacion.persona_id = entra_persona_id
```

La asignación cambiaba de dueño. Juan se presentaba a las siete,
trabajaba hasta las once y lo relevaban; a las once y cinco el consultor
formalizaba el cambio y esa fila dejaba de ser de Juan. La nómina paga
por asignación, así que **Juan cobraba cero por las cuatro horas que sí
trabajó**, y nada en el sistema recordaba que estuvo ahí.

Y más de fondo: no había **ninguna pantalla** que usara el reemplazo.
Los endpoints existían desde el principio; el cambio se hacía por
teléfono y no se registraba.

**La decisión.** El día del cambio no se muta: se parte.

- La asignación de quien sale **se queda**, marcada con la hora del
  relevo (`relevado_en`) y con quién entró (`relevado_por_id`).
- Se **crea** una asignación nueva para quien entra, con el mismo rol y
  la misma unidad.
- Los días siguientes sí cambian de dueño: nadie los trabajó todavía.

Ese día el equipo tiene dos personas en el mismo rol, y hay que saber
leerlo:

| | |
|---|---|
| **Al cliente** se le cobra **una** | La asignación relevada no entra al cierre ni a la cotización |
| **A la empresa** le cuestan **dos** | Las dos entran a nómina, cada quien su día completo |

La diferencia es el costo de la contingencia. Antes se lo comía el que
trabajó.

**Las reglas del pago.**

- **Día completo a los dos.** El que se presentó perdió su día y no fue
  su culpa; el que entró tampoco va a cobrar menos por llegar tarde a
  algo que no eligió. El consultor **no captura ningún monto**, que es
  lo que hace esto gestionable.
- **Cobra el día quien alcanzó a marcar su llegada.** Quien no se
  presentó no trabajó, y relevarlo es cambiar un nombre en una lista: su
  día se muta y no deja rastro. La regla vive en
  `contingencia.se_presento` y el sistema la verifica solo.
- **Las horas extra son de quien se quedó.** El relevado cobra su día,
  no las horas de más que no trabajó.
- **El rol se hereda y no se cambia aquí.** De él salen el precio al
  cliente y la comisión; moverlo descuadraría la cotización sin avisar.

**La pantalla.** El botón `Cambiar` va junto a `Quitar`, en la ficha de
cada persona: el consultor está viendo a Juan Ramírez y lo que quiere es
cambiar a Juan Ramírez. Abre debajo, en la misma tarjeta, igual que
`Asignar recursos`. Cuatro preguntas —desde qué día, hasta cuándo, por
qué, quién entra— y una **vista previa antes de guardar** que dice en voz
alta lo que va a pasar: los días, la nómina, los viáticos y los choques.

Esa vista previa **es el cambio de verdad, ejecutado y deshecho** en el
servidor. No hay una segunda cuenta que calcule "lo que pasaría": esa
siempre acaba separándose de la primera, y entonces el recuadro que el
consultor lee deja de ser lo que el sistema hace.

**Lo que se ve después.** La ficha del equipo dice "Relevado el 16 sep a
las 11:00" y "Reemplaza a Juan Ramírez"; los días afectados traen
etiqueta de *cambio*; al final del servicio hay un bloque de **Cambios de
recurso** con el historial; y la ficha de pánico de la central muestra
"Cambio formalizado · Luis Mendoza entra por Juan Ramírez", que ahorra la
llamada de "¿ya lo cambiaste?".

**El aviso sale en el momento.** El recordatorio de la víspera solo mira
mañana, así que un cambio hecho hoy para hoy nunca lo disparaba —y ese
es justo el urgente. Ahora el aviso al teléfono de quien entra sale al
formalizar.

**Deshacer.** Para el consultor que se equivocó de persona hace un
minuto, y **solo mientras nadie haya tocado el dinero**. En cuanto hay
una transferencia y un plazo corriendo, deshacer a mano sería peor que
el error: lo que corresponde es un cambio en sentido contrario, con su
rastro.

**Lo que se arregló de paso, en el cambio de unidad.**

- No movía `AsignacionPersonal.vehiculo_id`: después del cambio, "quién
  va en qué unidad" seguía apuntando a la camioneta que ya no estaba en
  el servicio, y así lo veía la central.
- Al mutar la asignación, la unidad que salía **desaparecía del
  servicio** y ya no se le podía hacer la revisión de devolución. Un
  golpe en esa camioneta quedaba sin dueño, que es exactamente lo que la
  revisión con fotos vino a resolver. Ahora la unidad también se releva.

**La raya con el implantado.** Este motor es de eventual y lo dice por
candado, no por costumbre: rechaza una jornada de implantado con un 409
que apunta a su calendario. No es separación de gusto —el implantado
reutiliza el mismo equipo mes tras mes, así que un cambio "de aquí en
adelante" barrería todas las jornadas abiertas y abriría decenas de
viáticos de un solo clic. Su reemplazo va día por día, en
`implantado.cambiar_personal`, **y ahí sigue el mismo agujero de nómina**
(ver sección 12).

---

## 12. El depósito bancario

**El hallazgo.** Finanzas paga un depósito por persona y equipo: son
cuatro días y una sola transferencia. Pero el sistema solo tenía una
solicitud por jornada, y eso que de verdad sale del banco —con su
referencia y su comprobante— **no vivía en ninguna tabla**. La bandeja lo
armaba al vuelo agrupando solicitudes.

Por eso no había a qué colgarle la evidencia. Y colgarla de cada
solicitud habría guardado la misma imagen cuatro veces: 1.2 MB repetidos
dentro de la base por cada depósito.

**Lo que finanzas no veía.** Un total y nada más. No quién autorizó el
gasto, no de qué se componía, no qué día traía qué, y no había forma de
subir el comprobante del banco.

**La decisión.** Nace `deposito_bancario` —persona, equipo, monto,
referencia, comprobante, cuándo salió y quién lo despachó— y las
solicitudes cuelgan de él. La migración rellena hacia atrás: por cada
grupo ya confirmado se crea su depósito con la referencia y la firma que
ya tenía. El rastro de lo pagado no se recupera si se pierde.

**Las reglas.**

- **Un depósito por persona y equipo.** Si alguien anda en dos servicios,
  recibe dos depósitos el mismo día. Es más movimiento en el banco, pero
  cada transferencia queda amarrada a un servicio y su rentabilidad
  cuadra sola.
- **Se deposita lo solicitado**, ni un peso más ni uno menos. El monto lo
  decide el consultor (sección 10); finanzas ejecuta. Así el desglose que
  el agente tiene que comprobar siempre cuadra con lo que recibió.
- **Referencia y comprobante, los dos**, para poder registrar desde la
  pantalla. Es la misma regla que ya tenían las compras especiales.
- **La evidencia se corrige siempre**, y queda escrito quién la cambió y
  cuándo: una evidencia que se reemplaza sin rastro no es evidencia. El
  depósito se anula solo mientras el agente no haya subido ningún
  comprobante de gasto —después de eso quedarían comprobaciones colgando
  de un depósito que ya no existe, y lo que corresponde es una
  devolución.

**Lo que llega por lote no trae captura.** El barrido y lo que viene ya
confirmado de Odoo no tienen a una persona subiendo un archivo. Esos
depósitos se crean igual —para que todo lo confirmado tenga a qué
colgarse— y salen marcados **sin comprobante**, con su cuenta en ámbar por
país. Se ve el hueco en vez de esconderlo: es algo que alguien tiene que
completar.

**Quién ve la evidencia.** Finanzas y dirección, el consultor del
servicio —que es quien recibe la llamada de "no me ha llegado"— y el
agente en su app, cada quien únicamente el suyo.

**Lo que destapó.** `asignado_por_id` —quién autoriza el gasto— venía en
el cuerpo de la petición, opcional, y nadie lo mandaba nunca: siempre
quedaba vacío. No es que el dato no se enseñara, es que no existía. Y
aunque alguien lo hubiera mandado estaría mal, porque sería el cliente
diciendo quién autorizó. Ahora sale de la sesión.

**Los datos bancarios.** `Persona` guarda banco, CLABE y titular, y
vienen de Odoo como el teléfono y la foto. Mientras esa conexión no
exista finanzas los llena y se van poblando; el día que Odoo conecte,
Odoo manda. Si la cuenta falta, la bandeja lo dice en ámbar en vez de
dejar el hueco callado: es el paso lento del proceso.

---

## 13. Lo que falta

### Abierto

- Las dos fallas de seguridad de `REVISION.md`: el sembrado sin
  autenticación y la `secret_key` pública en `config.py`.
- Restringir la llave de Google por IP del servidor.
- Cargar los montos reales: tarifas, comisiones de los cuatro roles y
  tabuladores de viáticos por acuerdo.
- HTTPS para probar la app en un teléfono real.
- **Generar las llaves de push.** `.env` todavía no tiene `VAPID_PUBLIC`
  ni `VAPID_PRIVATE`, así que los avisos al teléfono no salen:
  `docker compose exec -T api python generar_llaves_push.py`.
- **El servidor de producción.** Ver `ARQUITECTURA.md`. Tres cosas hay
  que hacer antes de encender: el `docker-compose.yml` del repositorio
  es de desarrollo y no se puede subir tal cual (publica Postgres y
  Redis a internet, trae la contraseña a la vista, corre uvicorn con
  `--reload`), el pozo de conexiones de SQLAlchemy se queda corto contra
  el pozo de hilos de FastAPI, y el respaldo tiene que estar probado
  antes de que haya datos reales que perder —con las imágenes dentro de
  la base, el `pg_dump` *es* el sistema completo.
- **El relevo del implantado.** Su reemplazo vive aparte
  (`implantado.py`, tabla `Reemplazo`) y sigue mutando la asignacion:
  quien sale a media jornada cobra cero, igual que pasaba en eventual.
  Ahi pasa mas seguido, porque es operacion diaria con plantilla fija.
  El arreglo de fondo es el mismo —relevar en vez de mutar— pero cuidado
  con el alcance: el implantado reutiliza el mismo equipo mes tras mes,
  asi que necesita un tope duro (el mes en curso) antes de tocarlo.
- **La moneda.** `Cotizacion.tipo_cambio` existe y no se lee en ninguna
  parte. Hoy no duele porque todo está en pesos; el día que entre un
  tarifario en dólares, la utilidad y la comisión salen sin sentido.

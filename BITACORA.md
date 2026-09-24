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
- **Se dice cuántas pruebas deberían pasar, antes de correrlas.** No es
  ceremonia: el 18 de septiembre una corrida salió en verde con 464
  cuando había 466 escritas. Las dos que faltaban eran justo las dos
  últimas — Docker en Mac sincroniza los archivos con retraso y el
  contenedor todavía no las veía. Una corrida verde que no probó lo que
  acabas de escribir es peor que una roja. Si el número no cuadra, se
  vuelve a correr antes de creerle.
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

**La raya con el implantado ya no existe.** Ver la sección 11 bis.

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

**El regreso cierra el movimiento, no abre otro.**

Juan trabaja hasta el 10 y se enferma; Luis lo releva y entra el 11. A
los días Juan se recupera, avisa al consultor, y el consultor coordina
que regrese el 25: **Luis trabaja hasta el 24 por orden del consultor**.

Eso es un solo hecho —"Luis cubrió a Juan del 11 al 24"— y así se lee en
el historial y en el corte del mes. Si el regreso abriera su propio
movimiento, el mismo mes mostraría dos cambios cruzados —Luis por Juan,
Juan por Luis— y nadie sabría cuál cierra a cuál.

Por dentro es el mismo relevo de siempre con los nombres al revés, así
que si Luis alcanzó a trabajar la mañana del 25 ese día se parte y lo
cobran los dos —y ese día sigue contando como suyo—. El movimiento que
ese relevo abre se borra: el hecho es el cierre del primero. Lo que
queda firmado es `regreso_en` y `regreso_por_id`: quién lo ordenó y
cuándo.

El regreso **no pide motivo**: el motivo es el del cambio que cierra.

**Y se puede mover.** Juan dijo el 25, el consultor lo capturó, y el 24
avisa que mejor el 28. Capturar el regreso otra vez recorre el mismo
movimiento y lo vuelve a firmar: el mes sigue leyendo un solo hecho. Por
dentro es el mismo relevo en el sentido que toque — si se atrasa, el que
cubría recupera los días que ya habían vuelto al titular; si se
adelanta, el titular se lleva unos días más.

Dos cosas lo bloquean, y las dos son la misma:

| | |
|---|---|
| **El dinero ya se movió** | Un viático pedido, transferido o comprobado no se desanda a mano. Es el mismo candado que usa `deshacer` |
| **El día del regreso se partió** | Ese día ya está repartido entre los dos, con su hora. Moverlo sería rehacer una nómina |

En los dos casos lo que corresponde es un cambio nuevo, con su rastro, y
eso es lo que dice el 409.

**La unidad también regresa.** El motor es el mismo con los nombres al
revés; lo único que no aplica es el candado del dinero, porque la unidad
no mueve viáticos: el combustible y las casetas siguen siendo del
conductor, que es el mismo.

**Las dos horas quedan guardadas.** `hora_propuesta` es la del relevo
que abrió el movimiento y `hora_propuesta_regreso` la del día que lo
cerró. Las dos pueden partir un día y las dos las puede corregir el
consultor; guardar la propuesta al lado es lo único que deja ver que la
corrigió.

Un detalle que costó encontrarlo: **el tope del mes se mudó a
`contingencia`**, junto al candado que lo exige. Escrito en dos lugares
es como el umbral de silencio, que acabó diciendo 60 en una pantalla y
120 en la otra.

Por ahora regresa el personal. La unidad que sale del taller ya trae su
`hasta` del registro de taller, así que no lo necesita todavía.

**Dos tablas para el mismo hecho.** `reemplazo` es la vieja del
implantado y `reemplazo_recurso` la del motor de relevo. Los cambios
nuevos caen en la segunda. El resumen del mes y los relevos del día en
Panorama leen **las dos**, para que el historial que ya existe no
desaparezca de la vista.

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

## 13. Quién ve qué

La cartera está abierta a propósito. Cualquier consultor puede trabajar
los servicios de otro para cubrir enfermedades o ausencias, y la apertura
no quita trazabilidad: `auditoria.py` marca como **cobertura** toda acción
sobre un servicio ajeno y le avisa al titular por correo.

Panorama nació con un filtro por consultor, en contra de esa regla, y se
le quitó. En una pantalla que contesta *¿hay alguien en problemas ahora
mismo?*, esconderle a un consultor que el equipo de otro lleva dos horas
callado no protege nada: lo deja sin ver justo cuando está cubriendo a
quien faltó.

**El bloque de dinero de Panorama también lo ve todo el que entre**, con
la nómina de la semana y los nombres de quién trae dinero sin comprobar.
Se preguntó y se decidió así: dentro de la empresa no se esconde. No es
un descuido, y no hay que "arreglarlo".

Lo que sí es de cada quien es la comisión: `comisiones.py` filtra por
consultor, y ahí sí, cada uno ve la suya.

## 15. Accesos: abrir y cerrar la puerta

Ver `PROPUESTA_ACCESOS.md` para el proyecto completo y las decisiones.
Aquí lo que ya corre.

### Lo que estaba roto

**No se le podía cortar el acceso a nadie.** `Usuario.activo` se leía en
tres lugares y no se escribía en ninguno; `Usuario.rol` solo se escribía
en el sembrado de demostración. Cerrarle la puerta a alguien que se fue
enojado era un UPDATE a mano en Postgres.

**Y la bitácora no cabía.** `RegistroAccion.servicio_id` es obligatorio:
esa bitácora está amarrada a un servicio por diseño, y un cambio de
acceso no tiene servicio al cual colgarse. Por eso nació
`RegistroAdmin` — para lo que no pasa sobre un servicio. Guarda el antes
y el después en texto: dentro de un año "finanzas → central" se lee sin
reconstruir nada. La va a reusar la bitácora de catálogos.

### Los candados

| | |
|---|---|
| No se desactiva ni se degrada **al último administrador** | Ni por la puerta de atrás, quitándole el rol |
| **Nadie se cierra la puerta ni se cambia el puesto a sí mismo** | Un cambio sobre uno mismo no tiene quien lo revise |
| **El que trae dinero sin comprobar no se da de baja** | Regla de la operación: debe terminar su ciclo. Bloquea solicitado, transferido y en comprobación. **No** bloquea asignado —nunca se movió un peso— ni cerrado —si bloqueara, nadie que haya recibido un viático podría darse de baja nunca— |
| **Desactivar dice lo que deja atrás** | Los servicios donde sigue asignado. No los quita: eso sería el sistema dejando un servicio sin gente |

### La contraseña tira las sesiones

Este era el hueco de fondo. El token no tiene estado: una vez firmado
vale doce horas y no hay lista de sesiones que cancelar. Si alguien te
robaba la sesión y cambiabas la contraseña, **el ladrón seguía adentro**,
que es justo de quien uno se quiere deshacer al cambiarla.

`Usuario.sesiones_desde` invalida todo token emitido antes. Y costó tres
intentos, que vale la pena dejar escritos:

1. Comparar el `iat` —segundos enteros— contra una hora con fracciones
   se comía tokens buenos. En producción sería *crea tu contraseña,
   entra, te saca, otra vez*.
2. Truncar los dos lados abrió una ventana ciega de hasta un segundo: el
   token que uno quiere matar sobrevivía. La prueba pasaba sola y
   fallaba en la batería completa, que es como avisa un problema de
   milisegundos.
3. **El bueno:** el token firma su propia hora exacta al lado del `iat`,
   que por estándar solo lleva segundos. Las dos comparaciones son
   exactas y no queda ventana.

De paso salió que una prueba estaba pasando **por accidente**: esperaba
401 y lo recibía, pero por el candado roto y no por la contraseña
incorrecta. Ahora verifica que falle por su propia razón.

### Los dos caminos de la contraseña

**Oficina, por correo.** Enlace de dos horas —no de tres días como la
invitación, porque es la llave de una cuenta que ya tiene cosas
adentro—, de un solo uso, y un enlace nuevo mata a los anteriores. La
respuesta es idéntica exista o no la cuenta.

**Campo, por teléfono.** Su correo es personal y la empresa no lo
controla: si ese gmail se compromete —o si la persona salió hace tres
meses y su gmail sigue vivo— la recuperación por correo le entrega la
cuenta. Así que el agente llama a su consultor o a la central y le
dictan **cuatro dígitos**.

Cuatro y no seis porque se dictan en voz alta a las seis de la mañana, y
la fricción también es seguridad: un código que se dicta mal tres veces
acaba en que alguien lo mande por WhatsApp. El precio es que diez mil
combinaciones se prueban en segundos, así que:

- **Cinco fallos y el código se muere.** Por código, no por minuto.
- El contador vive **en la base, no en Redis**: `intentos.py` se abre si
  Redis no contesta —que para el inicio de sesión es lo correcto— y eso
  dejaría cuatro dígitos sin candado justo el día malo.
- Se guarda **cifrado**. Diez minutos es poco tiempo, pero un código en
  texto plano es una cuenta regalada si la base se filtra.

**Quién lo dicta:** la central siempre; el consultor cuando esa persona
esté asignada a alguno de sus servicios. Nadie más. Lo único que protege
este camino es que quien entrega el código **reconozca la voz de quien
llama**, y cada persona que puede darlo sin conocer al agente es una
puerta.

### Un error que casi sale

El límite de intentos de la recuperación estaba puesto en el mismo
contador que el inicio de sesión. Con eso, **ocho peticiones al endpoint
público con el correo de alguien lo dejaban sin poder entrar quince
minutos**: un apagón a distancia, sin credenciales. Cada flujo tiene su
propio carril ahora.

### El panel

`#/accesos`, para administración y dirección general. Lo que aporta no
son los datos —esos ya se podían pedir uno por uno— sino **juntarlos y
levantar la ceja**:

| | |
|---|---|
| **Sin estrenar** | Se le dio el acceso y nunca lo usó |
| **Lleva meses sin entrar** | Una puerta abierta a nombre de alguien que quizá ya no está |
| **Dado de baja y con el acceso abierto** | El caso feo. Hoy no debería pasar; el día que Odoo mande las bajas, es la señal de que algo quedó a medias |

Y las tres acciones en el mismo lugar, con el motivo que se lee un año
después cuando alguien pregunta por qué se cerró esa cuenta. Al cerrar
una puerta avisa los días que quedan sin cubrir: cerrarla no saca a nadie
de la operación.

El personal de campo lleva su renglón —"recupera su contraseña con su
consultor, no por correo"— porque es lo primero que alguien va a
preguntar al verlo en la lista con un gmail.

### Lo que un humano todavía entrega a mano

El sistema no sabe mandar un correo que no cuelgue de un servicio:
`Notificacion.servicio_id` es obligatorio. Es el mismo patrón que la
bitácora, y ya van tres veces.

Mientras eso no exista, el enlace de recuperación lo entrega
administración desde un endpoint auditado, igual que el código de campo
lo dicta el consultor. Un humano entrega la llave hasta que exista el
canal.

### Los puestos: qué puede tocar cada quien

El rol dice qué es alguien en el organigrama. El puesto dice qué puede
tocar en el sistema, que no siempre es lo mismo: hay consultores que no
deciden cuánto dinero se deposita, y gente de central que sí. Hasta hoy
eso solo se podía resolver cambiándole el rol, que es cambiarle el puesto
en la empresa para arreglar un permiso.

La regla que decidió la dirección, y de la que cuelga todo lo demás:

> **El puesto quita, el permiso suelto solo da.**

Quien trae puesto puede exactamente lo que dice su lista —su rol deja de
mandar— y encima puede llevar permisos sueltos. Al revés no hay. Una
excepción que quitara dejaría su renglón en la lista diciendo "Consultor"
cuando no lo es, y para saber qué puede de verdad habría que abrir su
ficha y acordarse de que existe una excepción escondida. Por eso el
renglón ahora dice el rol **y** el puesto: la lista no miente por
omisión.

El orden en que se contesta "¿puede?" está en `auth.puede_el_usuario`:

1. **Administración pasa siempre.** Sin esto, un puesto mal armado puesto
   a la persona equivocada deja a la empresa sin poder arreglar la
   configuración, y el único camino de vuelta es un `UPDATE` a mano.
2. **Un permiso suelto**, si se lo dieron.
3. **Su puesto**, si lo trae.
4. **Su rol**, si no. Es como funcionó el sistema hasta ahora, y por eso
   **el día que se aplicó la migración no le cambió nada a nadie**: nadie
   nace con puesto.

Tres cosas que la pantalla tiene que decir, porque si no parece que los
botones no hacen nada:

- Al guardar un puesto, **a cuánta gente le estás cambiando el acceso**,
  antes de guardar y no después.
- Al apagar un puesto, que **quien ya lo trae lo conserva**: apagarlo
  solo deja de ofrecerlo al asignar. Si apagarlo devolviera a su gente a
  los permisos del rol, apagar un puesto **daría** acceso.
- Al quitar un permiso suelto, que **si su puesto o su rol ya lo traían,
  sigue pudiéndolo**.

Y una decisión de forma que resultó ser de fondo: **el puesto nuevo se
puede partir de un rol.** Nadie arma un puesto desde cero; lo que se
piensa es *"como consultor, pero sin depósitos"*. Se copian sus casillas
y se apagan las que no. Pero lo que se guarda es **la lista ya resuelta**,
no "consultor menos X": si fuera un vínculo, el día que cambiara lo que
trae consultor cambiaría en silencio lo que puede esa gente. La pantalla
lo dice con todas sus letras —"es una copia"— porque alguien va a esperar
que se actualice sola.

Al personal de seguridad no se le reparten permisos: entra desde la app y
lo único que hace ahí son sus propias jornadas. Ofrecerle veintinueve
casillas sería ruido y una forma de equivocarse.

### Las puertas mudadas

Quedaban 43 puertas preguntando por rol —26 constantes compartidas más 16
líneas sueltas en `servicios.py`, unos 140 endpoints detrás—. Se mudaron
todas menos cuatro, y el catálogo pasó de 29 casillas a 52.

La regla con la que se hizo, que es lo único que importa recordar:

> **Solo se juntaron puertas que pedían exactamente los mismos roles.**

Juntar dos con roles distintos obligaría a que la casilla trajera la
unión de ambas, y el día que se aplicara, alguien ganaría acceso que hoy
no tiene sin que nadie lo decidiera. Con esa regla, las 43 puertas caían
en apenas **cinco conjuntos de roles distintos**, lo que dice algo del
sistema: la variedad estaba en los nombres, no en los permisos.

Un hallazgo al teclear: **hay dos alertas que no son la misma cosa.**
`Alerta` la levanta el sistema solo —un servicio callado, unas horas
extra que vienen— y la mira quien vigila el día. `AlertaIncidencia` la
levanta el que está en la calle, y tomarla es hacerse cargo. Piden roles
distintos hoy (la segunda es solo de la central), así que juntarlas bajo
una casilla "alertas" le habría dado a un consultor el poder de tomar una
contingencia. Son dos renglones: `operacion.atender` y
`contingencia.atender`.

**Las cuatro que no se mudaron, y por qué:**

| Puerta | Por qué se queda con rol |
|---|---|
| La app de campo (`campo.py` y los `CAMPO` de `operacion` y `contingencia`) | El candado de ahí no es un permiso repartible sino *"es su propia jornada"*. Como casilla sería una que nadie debe marcar nunca, y el día que alguien la marcara por curiosidad le abriría la app del campo a gente de oficina |
| Leer catálogos (`crud.py`, `catalogos.py`) | Es "todo el que no es de campo". Una casilla que nunca se apaga es ruido en la pantalla |
| El panel mismo (`ADMINISTRA`) | Si repartir permisos se pudiera repartir, quien lo tuviera se daría todo lo demás |
| Dictar el código de campo (`DICTA_CODIGO`) | Entregar un código **es** entregar una cuenta. Lo único que protege ese camino es que quien lo dicta reconozca la voz de quien llama, y eso no se delega con una casilla |

Y un candado nuevo, comprobado por la batería: **solo dos casillas
alcanzan a la app del campo** —`viaticos.comprobar` y
`viaticos.evidencia`, las dos de antes de la mudanza— y la lista va
escrita en la prueba. Una tercera la rompe, y romperla obliga a escribir
por qué.

Lo que hace seguras a esas dos no es la casilla: es que el endpoint,
además, comprueba que el viático o el depósito **sea suyo**. La casilla
dice "puede comprobar", no "puede comprobar los de cualquiera". Una
actividad de campo sin ese candado adentro sería, con la casilla marcada,
la cartera de toda la empresa en manos del que está en la calle.

Esto salió de una prueba mía mal escrita: afirmaba que *ninguna*
actividad traía al campo, y la batería enseñó que dos sí. El código
estaba bien; la regla que yo había escrito era la equivocada.

`tests/test_puertas.py` guarda la tabla de quién sí y quién no, actividad
por actividad, escrita desde lo que cada puerta pedía **antes** de la
mudanza. El renglón que protege algo no es el del que puede: es el del
que no.

## 16. Los catálogos: la vuelta y el rastro

Diecinueve catálogos viven en la misma fábrica de `crud.py` —el tarifario
que se le cobra al cliente, lo que se le paga a cada rol, la plantilla, la
flota— y tenían dos huecos que solo se notaban el día que dolían.

**No había vuelta.** `DELETE` desactiva —nunca se borra historia— pero
nada volvía a encender, y como ningún esquema de entrada trae `activo`, el
`PATCH` tampoco podía. Una ciudad, una unidad o una persona desactivada
por error se quedaba fuera de todas las listas para siempre, y el único
camino de vuelta era un `UPDATE` a mano en Postgres. Ahora hay
`POST /{id}/reactivar`, con el mismo permiso que la baja: no se abre una
puerta más ancha que la que ya existía.

Un detalle que explica por qué el hueco vivió tanto tiempo: **`PlazaOut`
ni siquiera devuelve `activo`.** La pantalla nunca vio el campo, así que
nadie notó que no se podía cambiar.

**No había rastro.** Se podía subir un precio un viernes y en diciembre no
había forma de saber quién lo subió ni cuánto valía antes. La bitácora
existía desde el panel de accesos —`RegistroAdmin`, la que no necesita
servicio— y solo faltaba conectarla. Ahora las cuatro operaciones escriben
en ella, y `GET /{id}/historial` la deja leer.

Dos decisiones dentro de eso:

- **Se apunta solo lo que de verdad cambió**, con su valor viejo al lado.
  Guardar sin haber tocado nada es lo que más se hace en una pantalla de
  catálogo; si cada guardado dejara renglón, el historial de un tarifario
  sería cien líneas iguales y la que importa estaría perdida entre ellas.
- **El historial va con permiso de lectura, no de escritura.** El
  tarifario solo lo mueve administración, pero la pregunta *"¿quién subió
  esto?"* la hace finanzas, que es quien ve el número al facturar. Con
  permiso de escritura, el único que podría saber quién movió el precio
  sería el que lo movió.

### Y una puerta que estaba sin candado

Al conectar la bitácora salió lo que no se buscaba: **la baja de una
persona tenía dos puertas y solo una tenía candado.** El panel de accesos
cuida que quien trae dinero de la empresa no se vaya hasta comprobarlo
—regla de Salvador, 17 sep— pero `DELETE /catalogos/personal/{id}` daba
de baja a cualquiera sin preguntar nada. Se iba con el viático puesto y el
servicio se quedaba sin poder cerrar.

Es la misma regla, así que es el mismo candado, ahora en las dos puertas.

## 17. La revisión de la unidad: quién firma y qué se fotografía

Salvador preguntó (18 sep) si el personal de seguridad —*el que tiene el
vehículo asignado*— toma fotos al iniciar y al terminar. El **cuándo**
estaba bien; el **quién** no era lo que él creía.

**La función que lo cuidaba no cuidaba nada.** `_suya()` recibía la
unidad como dato y no la miraba: solo comprobaba que la persona
estuviera asignada **al servicio**. En un equipo de cuatro con dos
camionetas, el conductor de la primera podía firmar la recepción de la
segunda. Y la firma es exactamente lo que hace que la revisión sirva
para discutir un golpe tres semanas después: **una revisión firmada por
quien no traía la unidad es papel.** El nombre y el docstring prometían
lo que el código no hacía, que es la forma más cara de un hueco, porque
nadie lo va a buscar.

La regla nueva sale del propio modelo. `AsignacionPersonal.vehiculo_id`
ya decía en qué unidad va cada quien, y su comentario ya lo explicaba:
*"con una sola unidad sobra decirlo; cuando el equipo lleva dos o más, es
lo que ordena las salidas"*. Así que:

- si ese día la persona trae unidad asignada, tiene que ser **esa**;
- si no la trae, el día tiene que llevar **una sola** unidad.

Se mira día por día y no el servicio entero: en un implantado de un mes,
la camioneta de hoy no es la de la semana pasada. Y los dos rechazos
dicen cosas distintas —"esa unidad no va en tus días" es el dedazo de
placa; "esa unidad no es la tuya" viene con la placa de la que sí le
toca— porque son dos problemas distintos y el segundo se resuelve solo si
el mensaje dice cuál.

### La foto del odómetro

Pedida por Salvador en la misma conversación, y tapa un hueco que no se
veía: **el kilometraje era un número tecleado.** Al entregar, el sistema
calcula "recorrió 1,800 km" —la cuenta que nadie apunta y de la que
después todos se acuerdan distinto— y salía de dos cifras escritas de
memoria, sin nada con qué comprobarlas.

Ahora son cinco fotos obligatorias: los cuatro lados prueban cómo estaba
la lata, el tablero prueba el número. Al entregar, la ranura enseña
además la foto de cuando la recibió, así que se ven los dos tableros uno
al lado del otro.

No lleva migración: `foto_revision.angulo` se guarda como texto de doce
caracteres, no como un tipo ENUM de Postgres. Es la segunda vez que esa
decisión vieja ahorra una migración.

La pantalla del consultor las enseña las cinco, lado a lado. Se quedó
atrás un rato —`ladoALado()` traía la lista de cuatro ángulos escrita a
mano— y el odómetro salía en el número pero no en la foto, que es la que
lo comprueba. La lista ahora tiene nombre, `ANGULOS_LADO_A_LADO`, para
que la próxima que se agregue se note dónde va.

El kilometraje, que era opcional, ahora se exige: tener la prueba y no el
dato dejaba sin salir la cuenta para la que se pidió la foto. Se pide con
un 409 con su explicación y no desde el esquema, porque un 422 de
validación es una pantalla en blanco con un renglón rojo.

Y las fotos de un golpe en particular siguen siendo opcionales y sin
límite, aparte de las cinco. Cuando hay un daño, el acercamiento es la
prueba que más sirve.

## 18. El candado: la unidad no se suelta sin revisar

Salvador eligió (18 sep) el **candado duro en el fin de servicio**, sobre
dos alternativas más suaves. El razonamiento que descartó la más cómoda
—frenar al cerrar el servicio, en la consola— vale escribirlo, porque es
el que explica por qué el candado está donde está:

> Un candado que solo frenara al cerrar el servicio **no salva nada**.
> Para entonces la camioneta cambió de manos hace días y las fotos de ese
> momento ya no se pueden tomar. Lo único que quedaría es papeleo
> retroactivo, que se ve igual que una prueba hasta que alguien la
> necesita.

Así que muerde donde se preserva la evidencia: **no hay fin de servicio
con una unidad que hoy deja el servicio y no tiene su revisión de
entrega.** Sin excepciones, sin salida de emergencia.

**Y por eso mismo muerde poco.** Un candado duro que estorbe todos los
días es un candado que alguien va a querer quitar, y va a tener razón:

- **Solo el último día de esa unidad.** Un implantado con la misma
  camioneta veintidós días se revisa dos veces, no cuarenta y cuatro.
- **Solo a quien responde por ella.** El escolta que va de copiloto
  cierra su día normal. Pedirle la revisión de una unidad que después
  `es_suya` no lo va a dejar firmar sería encerrarlo en su propia app.
- **Se avisa antes.** La pantalla del día lo pone enfrente desde que la
  abre. Con candado duro, descubrirlo al intentar cerrar —a las ocho de
  la noche, con el cliente en el coche— es el peor momento posible.

Eso cerró de paso el hueco que llevábamos anotado: **la unidad que se
releva a media operación.** Deja de estar en las jornadas siguientes, y
con eso desaparecía de la lista de "por entregar" sin que nadie se la
volviera a pedir —justo la que más probable vuelve con un golpe, porque
cambió de manos a media operación—. Ahora, para ella, hoy **es** su
último día.

### La unidad relevada y la que entra son la misma silla

Lo encontró una prueba, y por poco se queda escondido. La regla decía:
con dos o más unidades en el día, solo responde por la suya quien la
tenga asignada. Y la unidad relevada **se queda colgada de su día** a
propósito, para poder hacerle su revisión de devolución.

Juntando las dos: el día que una camioneta se va al taller, el equipo
pasa a tener "dos unidades". Como nadie tenía unidad asignada —solo había
una— el día entero se quedaba sin dueño, el candado no mordía y la app no
pedía nada. **Justo el día del cambio, que es el único que de verdad
importa.**

Una camioneta que se fue y la que llegó en su lugar no son dos unidades:
son la misma silla, antes y después. Quien responde por la que quedó
responde también por la que salió —la manejó esa mañana— y es la que hay
que entregar, porque mañana ya no va. Va encadenado: si en un mal día se
cambió dos veces, la primera también es suya.

Para contar cuántas unidades hay, la relevada no cuenta.

### Una regla, un solo lugar

`app/revision.py` es nuevo y existe por una razón: la regla de *"cuál
unidad es la tuya"* la usan dos lados que no se hablan —el endpoint que
guarda la revisión y el candado del fin de servicio—. Con una copia en
cada uno, el día que una cambiara la otra diría lo contrario y nadie
sabría cuál manda. Es la misma lección del umbral de silencio, que vivió
meses con 60 en una pantalla y 120 en la otra.

### Lo que costó en la batería

El candado le pegó a ocho archivos de pruebas: cualquiera que ejecutara
una jornada completa con unidad asignada dejó de poder cerrarla. Se
arregló en `ayudas.marcar_fin`, que **intenta cerrar y resuelve lo que el
servidor reclame**, en vez de revisar siempre por si acaso. Así las
pruebas no fabrican revisiones donde la operación real no las tendría, y
el día que el candado cambie de forma, siguen diciendo la verdad.

## 19. Un aviso puede no ser sobre un servicio

`Notificacion.servicio_id` era obligatorio. Tiene sentido para lo que se
construyó primero —"su equipo llegó al punto de origen", "el servicio
terminó a las 19:40", el enlace de seguimiento en vivo—: todos esos
avisos *son* sobre un servicio, y colgarlos de ahí deja ver la
conversación completa de un servicio en un solo lugar.

El problema es todo lo demás. Un correo de "olvidé mi contraseña" no es
sobre ningún servicio. Una invitación de acceso a alguien que acaba de
entrar, tampoco. Como la tabla no los admitía, **el sistema no sabía
mandarlos**, y por eso los entrega una persona a mano desde el panel.

**Es la tercera tabla con la misma suposición metida:** *"todo lo que
pasa aquí pasa dentro de un servicio"*. `RegistroAccion.servicio_id` la
tenía y por eso nació `RegistroAdmin` —la bitácora que hoy usan el panel
de accesos y los catálogos—. Aquí se quitó en vez de hacer una tabla
nueva: un aviso a una persona y un aviso sobre un servicio son la misma
cosa saliendo por el mismo canal, y partirlos habría dejado dos bandejas
que revisar.

Se agregó el destinatario `colaborador`. Los cinco de antes son papeles
**dentro** de un servicio —quien lo pidió, quien lo recibe, la central,
el consultor, el personal—; este es una persona a secas. Mandarle su
contraseña a alguien como "personal" diría que el aviso es sobre una
jornada suya, y no lo es.

**Lo que no cambió, y conviene no confundir:** nada sale todavía. Esto
quitó la traba de diseño, no el trabajo de conectar un proveedor de
correo. Sigue en la lista de pendientes, y esa parte es decisión de
Salvador: con qué se manda y desde qué dominio.

El riesgo que abre hacer la columna opcional está cubierto por una
prueba: **el borrado de un servicio no se lleva los avisos que no son
suyos.** Limpia por `servicio_id`, no a lo ancho. Es la clase de cosa que
nadie echa de menos hasta que alguien pregunta por qué no le llegó su
invitación.

## 20. La declaración de daño de la unidad

Pedido por Salvador (18 sep), decidido el 19. La propuesta completa está
en `PROPUESTA_DANO_UNIDAD.md`.

**El problema no era que faltara dónde escribir.** Ya había una nota
libre y fotos de golpe. Eran opcionales, y **el caso normal de una
casilla opcional es que se quede vacía**: quien recibe una camioneta
golpeada a las seis de la mañana, con prisa, no va a documentar por su
cuenta un daño que no hizo —que es justo donde le hará falta tres
semanas después—. Y faltaba la distinción que decide quién responde:
*"así me la dieron"* contra *"esto pasó conmigo"*.

**Una pregunta, no dos juegos de columnas.** `hubo_dano`, `dano_tipo` y
`dano_nota` en `RevisionUnidad`. Lo que significan lo dice el `tipo` que
ya existía: `recibe` + daño es *venía golpeada*; `entrega` + daño es *se
golpeó durante el servicio*.

`dano_tipo` va con nombre —rayón, golpe, cristal, llanta, mecánico,
otro— por la misma razón escrita en `MotivoCambio`: *"de aquí salen
cuentas que la dirección va a pedir... escrito a mano no se puede
contar"*. Cuántas unidades vuelven con daño al mes, de qué tipo, en qué
plazas. Y como texto, no como ENUM de Postgres: es la decisión vieja que
ya ahorró dos migraciones.

### La regla que hace que el dato sirva

> **Si declarar un daño propio costara caro, nadie declararía nunca.**

Y tendríamos una casilla que siempre dice "no" y una falsa sensación de
estar documentando, que es peor que no tenerla. Declarar tiene que costar
menos que esconder. De ahí salen las tres decisiones:

- **La pregunta es obligatoria, pero contestar "no" es un clic.**
  Declarar no cuesta más que no declarar.
- **Un daño declarado al recibir no dispara nada.** Ni alerta, ni aviso,
  ni freno. Quien lo declara no hizo nada: se está protegiendo, y
  castigarlo sería el incentivo exactamente al revés.
- **Un daño nuevo al entregar avisa al consultor y nada más.** Decisión
  de Salvador. Sin alerta que cerrar y **sin incidencia automática, ni
  siquiera `ERROR_MENOR`** —la que no quita estrellas—.

Lo último merece explicación, porque la tentación era fuerte y el sistema
ya tenía la pieza lista. Dos razones para no hacerlo: **el sistema nunca
clasifica solo** —eso es del consultor, con visto bueno del director de
operaciones— y un renglón automático en el expediente de alguien, aunque
no le quite nada, es algo que nadie juzgó y que después hay que explicar.
El consultor ya tiene el botón si lo amerita.

Y en la pantalla se le dice con todas sus letras: *"Esto te protege a
ti"* al recibir, *"Declararlo no es una falta: esconderlo sí"* al
entregar. Un candado que no se explica se siente como una trampa.

### Lo que ve el consultor

Dos banderas calculadas en el servidor, no en la pantalla, porque son la
pregunta que se hace al abrir y no un detalle que se busca:

- `dano_nuevo` — volvió con un golpe. El renglón que hay que atender.
- `ya_venia_danada` — es lo que protege a esa persona tres semanas
  después.

Y en el panorama, `unidades_con_dano_nuevo`, **sin estado**: no hay nada
que "cerrar" ahí. Se ve, se entra al servicio y se decide —clasificar una
incidencia, o nada— que es de personas.

### Las pantallas, y dos cosas que se repetían

Salvador pidió (19 sep) que el consultor vea cómo recibió y cómo regresa
la unidad, con o sin incidente, **sin información repetida y digerible de
un vistazo**. El bloque lado a lado ya existía; al ir a meter la
declaración salieron dos duplicaciones, y las dos se arreglaron:

**Dos cajas de texto.** La revisión ya traía una nota libre —"Lo que ya
viene golpeado" al recibir— y la declaración pide una explicación. Con
las dos en pantalla, el golpe se escribe en la que toque primero y del
otro lado hay que leer en dos lugares. Ahora **es una sola caja que
cambia de nombre**: "Describe el daño" o "Qué pasó" cuando se declaró
algo, "Observaciones (opcional)" cuando no. En la base siguen siendo dos
columnas, porque el consultor necesita ver el daño destacado y aparte de
una observación cualquiera; el agente solo ve una.

**La tira de golpes mezclaba las dos puntas.** Juntaba las fotos de daño
de entrada y de salida en una sola fila. Si la camioneta llegó con un
rayón y volvió con un cristal roto, se veían cuatro fotos y **no se podía
saber cuál ya venía** —que es exactamente la pregunta que uno se hace al
abrir esto—. Ahora cada golpe se queda con su punta, como el resto del
bloque: izquierda cómo te la dieron, derecha cómo volvió.

Y las dos banderas suben al encabezado de la unidad, sin tener que
desplegar las fotos: *"Volvió con un daño que no traía"* en rojo, *"Ya
venía con un daño al recibirla"* en ámbar. Tener que abrir las fotos para
saber si hubo un golpe es hacer la pregunta al revés.

**Un detalle que cazó el barrido.** La primera versión armaba la clave de
traducción al vuelo, pegando el tipo de daño a un prefijo. `revisar.py`
lo marcó —y marcó hasta el ejemplo que quedó escrito en un comentario—.
Es la lección que `util.js` ya tenía escrita para el mapa de estatus:
*"una clave armada al vuelo no se puede revisar"*. Ahora es un mapa
explícito, `DANOS_ES`.

## 21. El hilo suelto: lo que el consultor no veía

`revision_pendiente` llevaba meses calculado y devuelto —en la respuesta
del cambio de unidad, del regreso y del taller— y **ninguna pantalla lo
pintaba**. El consultor hacía el cambio, el sistema le contestaba *"falta
entregar la que sale, falta recibir la que entra"*, y él nunca lo veía.

Desde el candado del fin de servicio (sección 18) ya no se perdía nada:
la unidad no se suelta sin entregar. Lo que se perdía era **encargarlo en
el momento**, que es cuando la gente todavía está junto a las dos
camionetas. Ocho horas después ya se fue cada quien por su lado.

Ahora sale en tres lugares, todos justo después de provocar el cambio:
el recuadro de vista previa del relevo, el del regreso, y el del taller
del implantado.

Y algo que no estaba y ahora sí: **el contrato tiene pruebas**. Nadie
vigilaba `revision_pendiente`, y ahora una pantalla depende de él. Lo
delicado no es que el campo exista, sino que diga la verdad en los dos
casos que se confunden:

- **La unidad que rodó** —alguien la recibió— hay que entregarla.
- **La que nunca salió** no. Cambiarla es corregir un nombre en una
  lista, y pedir su entrega sería mandar a alguien a fotografiar una
  camioneta que nunca tocó. Es la forma más rápida de que el aviso deje
  de significar algo.

Y el aviso se apaga solo cuando la revisión se hace. Uno que sigue ahí
después de resolverlo enseña a ignorarlo.

## 22. La ayuda en pantalla

Pedido por Salvador el 18 de septiembre, decidido el 19. La propuesta
está en `PROPUESTA_AYUDA.md`.

**Lo primero fue contar lo que ya había**, y corrigió el número que esta
bitácora traía mal: no son 93 pies de página, son **67 textos
explicativos** —34 pies de bloque, 29 subtítulos, 4 ayudas de campo— en
tres idiomas, más las 52 descripciones de actividad.

Y el hallazgo que cambió la escala del trabajo: **70 mensajes
`que_hacer`** en el servidor. Cuando el sistema frena a alguien no dice
"no se puede" y ya: dice qué pasó y qué hacer para salir. Eso es ayuda
entregada en el instante exacto en que hace falta, y ya funcionaba. Esto
no era escribir un manual: era cosechar.

**Dos decisiones de Salvador:**

- **No hay recorrido guiado.** Era lo que pidió al principio y lo
  cambiamos: es lo más caro, lo que más rápido se despega —este sistema
  cambia cada semana— y lo que menos se usa, porque se ve una vez, cuando
  la persona todavía no tiene ninguna pregunta concreta. En su lugar, un
  `?` por bloque.
- **Se empieza por el dinero.** Los bloques que mueven dinero o frenan la
  operación son los que generan las llamadas.

### El `?` y sus tres frases

`conAyuda()` en `util.js` envuelve un encabezado y le cuelga un `?` que
abre tres frases: **para qué sirve**, **cuándo te enteras si falla**, y
**de dónde sale el número** —esta última opcional, porque solo tiene
sentido donde hay una cifra que alguien va a querer cuadrar, y un renglón
vacío con su titulito enseña que los `?` traen relleno.

La segunda empezó siendo *"si no lo haces"* y Salvador la cambió (19
sep). El cambio parece de forma y es de fondo: *"si no lo haces"* invita
a escribir una moraleja —"el mes no cuadra"— y **"cuándo te enteras"
obliga a contar una escena**: *"al cerrar el mes, cuando la caja no
cuadra y ya nadie se acuerda de qué depósito era cuál"*. Una escena no se
puede escribir en genérico, y esa es justo la disciplina que hace que la
frase sirva.

El sufijo de la clave se renombró de `_si_no` a `_cuando` en los 87
renglones. Una clave que dice una cosa y un rótulo que dice otra es el
código mintiendo en voz baja, que es como empiezan los desfases que este
proyecto ya pagó tres veces.

La clave se escribe pegada al bloque que explica, no en un archivo
lejano: quien cambie el bloque tiene el texto delante.

### El candado, que es lo que Salvador pidió de verdad

> *"Me interesa que cada vez que hagamos un cambio en la consola también
> se actualice el `?`."*

`conAyuda()` arma las claves pegando sufijos al nombre que recibe, así
que una letra de más no revienta nada: `t()` devuelve la clave cuando no
la encuentra y el usuario ve `ay_fin_depozitos_para` escrito en la
pantalla. Es el mismo agujero de la clave armada al vuelo que `util.js`
ya tenía prohibido —aquí no se puede evitar, porque el sufijo es lo que
da la estructura de las tres frases—. Así que en vez de prohibirlo, se
revisa.

`revisar_ayuda()` es la revisión número siete de `revisar.py`, y como el
barrido corre dentro de la batería, **un bloque con `?` y sin texto rompe
las pruebas**. No es "acuérdate de escribirlo": es que no pasa.

Se probó rompiéndolo a propósito antes de darlo por bueno —y la primera
versión pasaba por vacío, porque miraba renglón por renglón y las
llamadas se parten en dos líneas—. Ahora cuenta paréntesis y comillas,
igual que haría quien lo lee.

**Lo que ningún candado puede garantizar,** y conviene tenerlo escrito:
que el texto siga siendo *verdad*. Si alguien cambia lo que hace un
bloque y no toca su ayuda, el barrido no se entera —el texto sigue ahí,
solo que ahora miente—. Ninguna máquina lee español.

*(Se descartó atarlo a git: el contenedor monta solo `backend/` y `.git`
vive en la raíz, así que funcionaría cuando el barrido se corre desde
fuera y no cuando lo corre la batería. Una revisión que pasa en un lado y
falla en el otro enseña a ignorar la diferencia.)*

### Dónde quedaron, y por qué no en todos

**39 bloques** en nueve pantallas: finanzas (5), el servicio (8), el
panorama (5), la central (4), el alta (4), el implantado (8), la nómina
(3), accesos (1) y puestos (2).

Hay unos 95 encabezados en la consola. **La mayoría no lleva `?`, y es a
propósito:** un bloque "Cliente" con el nombre del cliente debajo no
necesita que nadie le explique para qué sirve. Una frase que no agrega
nada enseña a ignorar los signos, y entonces tampoco se leen los que sí
importan. El criterio fue: alcance que no es obvio, dinero, o algo que
frena la operación.

### El hallazgo que salió al medir, y el candado que faltaba

**`nomina.js` estaba sin traducir.** Tres llamadas a `t()` contra 120 en
finanzas y 364 en servicio, y cinco encabezados en español duro. Un
usuario en Brasil abría la nómina y la leía en español.

`revisar_idioma` no lo cazaba, y la razón importa: **barre las claves que
se usan.** Caza la que falta en un idioma; no caza la pantalla que no usa
ninguna. El barrido medía lo que estaba y no lo que faltaba.

Ya está traducida —44 claves en tres idiomas— y con ella se hizo
`revisar_texto_suelto()`, la revisión número ocho: **texto visible
escrito a mano en una pantalla de consola**. Mira el tercer argumento de
`h(...)`, que es donde van los hijos; los dos primeros llevan clases,
estilos y rutas, que no son texto de nadie.

Se probó contra el repositorio entero antes de encenderla: **cero falsos
positivos**, y cazó cinco de verdad —el "Rol" de la nómina que se me
había escapado y cuatro de `mapa.js`—, que ya están arreglados.

**Y hubo una segunda pasada.** Al terminar los `?` apareció lo que el
barrido tampoco veía: **el texto dentro de una plantilla**. Al traducir
una pantalla se cambian las cadenas entre comillas y las plantillas se
quedan, porque no se leen como texto sino como código. Así sobrevivió
"Semana del" en medio de una nómina ya traducida, y otros seis.
`revisar_texto_suelto` ahora también las mira, ignorando las que ya
llaman a `t()` —ahí lo que queda fuera de los huecos son separadores—.

**Y encontró algo más grande: la app de campo está entera en español.**
No importa `idioma.js` ni una sola vez. Son unos noventa textos, y
traducirla es un trabajo aparte. La exclusión va **escrita en el barrido
y comentada**, no callada, para que se lea como una deuda y no como un
olvido: el día que se traduzca, se borra esa línea y el candado la
cubre.

La línea se borró el 19 de septiembre. Está contado en el 23.

### Revisados

Salvador los leyó el 20 de septiembre y los aprobó. Los 39 quedan como
están; el criterio —alcance que no es obvio, dinero, o algo que frena la
operación— queda confirmado para los que vengan.

### El panel flota

Salvador, el 19: *"se amontona la explicación con los botones"*.

El panel se abría **dentro** del bloque y empujaba todo hacia abajo,
quedando pegado al pie que ese mismo bloque ya trae. Dos explicaciones
seguidas y luego los botones —amontonado justo en el momento en que
alguien abrió el `?` porque no entendía algo—. **Una ayuda que
desacomoda la pantalla que está explicando se lee peor que no tenerla.**

Ahora se abre encima, como cualquier menú: nada se mueve de su lugar, se
cierra picando afuera o con Escape, y solo una a la vez —dos paneles
abiertos son dos explicaciones compitiendo—.

Los oyentes de cierre van **una vez por módulo**, no uno por cada `?`:
hay cuarenta en la consola y se repintan enteros en cada vuelta.

### El candado de cobertura

`revisar_ayuda` le exige sus dos frases a cada bloque que **ya** tiene
`?`. Eso deja fuera lo que más importa: **la pantalla a la que nadie le
preguntó nada**. Una pantalla nueva sin un solo signo pasaba limpia, y
el barrido decía "todo limpio" con la mitad de la consola sin ayuda.

Es la misma forma de agujero que dejó cien textos en español en la app
de campo (sección 23), y la misma lección: una red que solo mira lo que
alguien decidió marcar **da por terminado lo que nunca se miró**.

Así que cada pantalla declara su número, en `AYUDA_POR_PANTALLA`:

- **menos** signos de los declarados → alguien borró uno sin querer;
- **más** → el padrón se quedó viejo, y escribir el número nuevo es la
  forma de que el cambio pase por la cabeza de alguien;
- **el archivo no está en la tabla** → es una pantalla que nadie miró;
- **un renglón sin archivo** → quedó un fantasma de una pantalla que ya
  no existe.

**Un cero es una respuesta, y de las buenas.** No todos los encabezados
llevan `?`: hay unos 95 en la consola y 40 signos. Una frase que no
agrega nada enseña a ignorar los signos, y entonces tampoco se leen los
que sí importan. El criterio fue: alcance que no es obvio, dinero, o
algo que frena la operación. Lo que no se vale es el silencio.

**La app de campo lleva cero, y también es una decisión.** La consola se
usa sentado: abrir un panel para leer tres renglones cuesta un clic y se
puede. El de campo va con una mano, con prisa y media barra de señal —ahí
la ayuda tiene que estar ya escrita en la pantalla, sin tocar nada. Por
eso cada tarjeta trae su pie (`cmp_*_pie`) y no un signo que haya que
descubrir. Está escrito en el padrón, con el motivo al lado.

---

## 23. La app de campo en tres idiomas

Cerrado el 19 de septiembre. Lo empezó el barrido de la 22, que fue el
que destapó que la app de campo estaba entera en español.

### De dónde sale el idioma

Decisión de Salvador: **del país de su plaza**. Sin selector, sin
preguntarle nada a nadie. El país trae una columna `idioma`
—`String(2)`, `"es"` por omisión, migración `c8e40b17a935`, Brasil a
`"pt"`—, `/auth/yo` lo devuelve por `usuario.persona.plaza.pais.idioma`
y `campo/app.js` lo pone antes de pintar nada.

Un agente en São Paulo abre la app y está en portugués. No hay una
bandera que tocar ni una preferencia que se pierda al cambiar de
teléfono: el dato ya estaba en el sistema.

### Las dos pasadas, y por qué hubo dos

La primera pasada cambió **87 textos**. Dejó la app con cara de
traducida y con unos cien textos todavía en español.

Lo que sobrevivió no fue lo difícil: fue **lo que el barrido no
miraba**. `revisar_texto_suelto` vigilaba el tercer argumento de
`h(...)` —que es donde van los hijos, o sea lo que se pinta— y las
plantillas. Todo lo que dice algo desde otro lugar pasó de largo:

- los `alert` y los `confirm` —dieciocho, y son justo los que aparecen
  cuando algo sale mal, que es cuando más importa entender—,
- los `textContent` que se reescriben solos,
- **los dos lados de un ternario** dentro de un `h(...)`: el que recibe
  y el que entrega leían dos frases distintas, ninguna traducida,
- las tablas de arriba del archivo —`HITOS`, `ANGULOS`, `OCTAVOS`,
  `TIPOS_DANO`, `CONCEPTOS`—, que son puro texto visible,
- los `placeholder`, que es lo único que se ve en una caja vacía.

**La lección, y es la que vale de toda la sección:** un barrido no
encuentra errores, **define qué quiere decir "terminado"**. Se tradujo
exactamente lo que la red atrapaba y el resultado dio limpio. Así que lo
primero de la segunda pasada no fue traducir: fue **ensanchar la red**, y
después dejar que dijera qué faltaba.

### Las dos redes nuevas

En `revisar_texto_suelto`, además de las dos que ya había:

1. **Las bocas.** Lo que está pegado a un `alert(`, un `confirm(`, un
   `.textContent =` o un `placeholder:`. Ahí no se pinta con `h()` pero
   se lee igual.
2. **Los acentos.** Cualquier literal con `áéíóúüñ` o `¿¡`, esté donde
   esté. Es la red más barata y la que no se puede burlar sin querer:
   una frase en español casi siempre trae uno.

Las dos miran el archivo **con los comentarios en blanco**. Los
comentarios de este sistema están en español y con acentos —son media
bitácora—, y sin borrarlos cada párrafo explicando por qué una pantalla
hace lo que hace salía como un texto sin traducir. Se reemplazan por
espacios, no se borran, para que los renglones no se muevan.

Lo que se lee igual en tres idiomas —`ABC-123-D`, `Suburban`,
`MR. BROOKS`, `0000`— está en `NO_ES_TEXTO` con el motivo escrito al
lado.

### Lo que encontraron en la consola

La consola llevaba días dada por traducida. Las redes nuevas sacaron
**tres**:

- `servicio.js`: el campo **"Año"** del alta de vehículo, entre nueve
  campos que sí llamaban a `t()`. La clave ya existía (`imp_anio`).
- `consultor.js`: el `confirm` de **"Google dice que ese lugar no es un
  aeropuerto"** —el que explica que la geocerca pasa de 500 m a 2 km—.
- `mapa.js`: el **placeholder** del buscador de direcciones, que es lo
  primero que se ve al abrir el mapa.

Tres, y ninguna falsa. Eso es lo que hace que valgan la pena.

### El idioma también manda en los números

Traducir los textos y dejar `"es-MX"` pegado a cada `toLocaleDateString`
deja una pantalla en portugués que dice **"lunes"**. Son catorce
llamadas. Ahora hay un `local()` —`es→es-MX`, `en→en-US`, `pt→pt-BR`— y
la fecha se escribe en el idioma en que se está leyendo.

### Tres variables llamadas `t`

Hallazgo de paso, y de los que no se ven: en tres lugares una vuelta
usaba `t` como nombre de su variable —`f.sueltos.map(t => …)`,
`OCTAVOS.forEach((t, i) => …)`, `for (const [v, t] of CONCEPTOS)`—. Ahí
adentro **la función de traducir no existía**: quedaba tapada por el
hito, por el octavo de tanque o por el concepto del gasto. Traducir esos
tres bloques era imposible sin renombrar primero, y el error no habría
sido "falta traducir" sino algo mucho más raro de leer.

### El tamaño

**143 claves nuevas** en tres idiomas —429 renglones en `idioma.js`—,
82 cambios en `campo/app.js`, dos en `memoria.js`, tres en la consola.
Las tablas de texto pasaron de constantes a funciones (`hitos()`,
`angulos()`, `octavos()`, `tiposDano()`, `conceptos()`, `nombreRol()`)
por una razón sencilla: una tabla armada al cargar el módulo se congela
en el idioma de ese momento, y el idioma se pone **después**, cuando ya
se sabe de quién es la sesión.

---

## 24. Dos puertas que estaban abiertas

Cerradas el 19 de septiembre. Las dos salieron de la revisión de
septiembre, en "cosas menores, anotadas para no perderlas". Ninguna de
las dos era menor.

### El mapa de la API estaba publicado

`/docs`, `/redoc` y `/openapi.json` respondían a cualquiera que diera
con la dirección del servidor. No enseñan datos —todo lo de adentro
sigue pidiendo sesión— pero son el plano completo: cada endpoint, cada
campo, cada nombre, con el formulario para probarlos al lado. A quien
quiera buscarle la vuelta le ahorran el trabajo de adivinar por dónde.

Ahora dependen del entorno: abiertos en desarrollo, donde valen su peso
en oro, y **inexistentes fuera de él**. Quien necesite el mapa lo
levanta en su máquina.

**Se pregunta al revés a propósito.** La función enumera lo que **sí**
es desarrollo —`local`, `dev`, `desarrollo`, `test`, `pruebas`, `ci`— y
todo lo demás es producción. Al revés, un `APP_ENV=prod`, un `staging` o
un renglón vacío en el `.env` dejarían la puerta abierta. Es la misma
lista que ya usaba el candado de la clave de demo, ahora compartida:
**una puerta que se abre sola cuando no entiende el nombre del entorno
es una puerta abierta.**

### Pagar dos veces la misma jornada

El candado vivía solo en Python: `jornadas_pendientes` saca lo que ya se
pagó y lo descuenta. Entre leer eso y escribir el corte hay una rendija
—dos cortes calculados al mismo tiempo leen los dos que la jornada está
libre— y lo que se cuela por ahí es dinero pagado dos veces, que se
descubre al mes siguiente o nunca.

**La mitad ya estaba tapada y no lo sabíamos:** `nomina_semanal` es
única por país y fecha de corte, así que dos corridas de la **misma**
semana chocan solas. Lo que quedaba abierto son dos cortes de **semanas
distintas** del mismo país —`jornadas_pendientes` no filtra por fecha, a
propósito: lo que manda es que la jornada esté terminada y su servicio
vaya a facturación—.

**Y aquí está lo que casi se hace mal.** La restricción obvia era
`UNIQUE(jornada_id)`: una jornada, un pago. **Habría reventado el primer
día de dos escoltas.** Una jornada de equipo tiene varias personas
asignadas y cada una cobra su renglón, todos con la misma `jornada_id`.
La regla no es "una jornada se paga una vez": es **una jornada se le
paga a una persona una vez**.

Y esa regla no cabía en una tabla: la jornada vive en `concepto_nomina`
y la persona en `renglon_nomina`. Por eso `persona_id` baja al concepto
—duplicada a propósito, escrita una vez y nunca actualizada, porque un
concepto no se edita y recalcular un corte borra sus renglones y los
vuelve a escribir— y la restricción va sobre el par. Migración
`d1a73f5b0e62`.

**Los ajustes no se estorban:** un ajuste no cuelga de ninguna jornada y
ahí `jornada_id` va en nulo. Postgres no compara nulos entre sí, así que
una persona puede arrastrar varios ajustes en el mismo corte sin que la
base los confunda con un día pagado dos veces. Lo mismo vale para lo que
queda huérfano cuando se borra un servicio: esos conceptos se quedan con
la jornada en nulo a propósito, para no borrarle a nadie su recibo.

### Y una prueba que faltaba

`test_migraciones.py` comparaba tablas, columnas, obligatoriedad y
enums, pero **no las restricciones únicas**. Es la misma ceguera que
tiene contada: la batería arma su base desde el modelo, así que una
restricción declarada en el modelo y olvidada en la migración está
siempre puesta en las pruebas y **nunca** en producción. Se comparan por
columnas y no por nombre, que es justo lo que se olvida igualar.

---

## 25. El encabezado: lo que sobraba no era espacio

19 de septiembre. Salvador: *"el encabezado está amontonado"*. Se le dio
aire dos veces y siguió viéndose mal, que era la pista.

Arriba competían **siete cosas**: la marca, el sello AI/EP, el rol, el
nombre, el correo, la bandera del idioma y Salir. Abajo, el menú —lo
único que se usa todo el día— era lo que menos pesaba. **Darle
separación a algo amontonado lo deja igual de amontonado y más alto.**

Lo que sobraba era información que no cambia nunca: **nadie necesita
leer su propio correo en cada pantalla.** El rol, el correo y el idioma
se recogieron en una pastilla con el nombre y las iniciales; se abren de
un toque, que es la frecuencia con la que se miran. El nombre se queda a
la vista porque sí sirve de un vistazo: dice con qué cuenta estás
trabajando, y en una consola donde el consultor ve lo suyo y el director
lo de todos, eso importa.

El menú se queda en su propio renglón, con el renglón entero para él.
Esa decisión ya estaba tomada y sigue siendo la buena: apretado entre el
logo y los datos del usuario se perdía.

Se eligió entre tres acomodos dibujados —como está, dos renglones, y
todo en uno solo—. Ganó el de dos renglones. El de un solo renglón queda
anotado por si algún día pesan más los píxeles de alto que el aire: con
nueve entradas de menú iba justo.

---

## 26. Tres cosas con el mismo nombre

20 de septiembre. Salvador llevaba dos días diciendo *"el encabezado está
amontonado"*. Se le dio aire tres veces y las tres siguió viéndose mal,
que era la pista: **no era espacio.**

Con una foto de la pantalla se vio lo que en realidad pasaba: el menú y
el texto de la pantalla estaban **impresos uno encima del otro**. Eso no
se arregla con píxeles.

### Cómo se encontró

No adivinando más. Se copió la hoja de estilos a un Chromium aquí, con
un HTML que repite el DOM que arma la consola, y se le preguntó al
navegador la geometría. La respuesta fue inmediata:

    header: top 0, bottom 18
    nav:    top 77, bottom 130
    h1:     top 56, bottom 89

**El encabezado medía 18 píxeles de alto y su propio menú estaba 60
píxeles más abajo, fuera de él.** Como la caja no ocupaba lugar, la
pantalla entera arrancaba debajo del filo azul y el título se pintaba
encima del menú.

### Los tres choques, todos del mismo commit

El panorama (`b5aa89b`) trajo tres nombres que ya estaban ocupados:

- **`.barra`** — el tramo que pinta un servicio sobre el eje del día. El
  encabezado de la consola es `<header class="barra">`. La regla nueva
  no declaraba `position` —`header.barra` gana ahí— pero sí
  `height: 10px`, y eso nadie se lo disputaba: con `box-sizing:
  border-box`, dieciocho píxeles y el menú colgando por fuera.
- **`.punto`** — ya era el renglón de *"una persona con su palomita"* de
  la central. Cada integrante del equipo se volvió **una bolita de nueve
  píxeles**, con el nombre y el rol desbordados sobre la lista de
  pendientes. Eso es lo segundo que se veía encimado en la foto.
- **`.atender`** — es un componente (el renglón de algo que hay que
  atender) y también un nivel. `tarjeta estado atender` se llevaba el
  `display:flex` y el relleno del renglón, y el recuadro de estado se
  armaba en fila.

Ahora se llaman `.tramo`, `.luz` y `.renglon_atender`.

**Lo que hace a estos tres tan caros:** desde el código no se ven. Cada
archivo, leído solo, está bien escrito. Se cruzan en la hoja de estilos,
y ahí no miraba nadie —`revisar.py` tenía ocho revisiones y **ninguna
sobre CSS**—.

### El candado

`revisar_estilos()` caza las tres formas:

- la misma clase con **dos reglas** que le ponen la caja → dos
  componentes con un nombre;
- una clase **suelta y con etiqueta** (`.barra` y `header.barra`) → la
  suelta le pega a las dos;
- una clase que es **componente y modificador** a la vez (`.atender`).

Mira solo selectores de una pieza —un descendiente como
`.calendario-leyenda .punto` ya está acotado— y salta los `@media`, donde
ajustar la misma clase es justo lo que se quiere. Sobre las dos hojas de
hoy: cero hallazgos. Sobre la hoja de ayer: los tres.

**Un nombre genérico —barra, punto, atender— no falla el día que se
escribe. Falla el día que alguien toca la otra cosa.**

### Y uno mío, de la pastilla

El `button` de la casa es azul con letra blanca. La pastilla del nombre
se puso blanca **sin decir el color de la letra**, así que el nombre
salía blanco sobre blanco —y lo mismo el botón de Salir del menú—. Dos
líneas. Se vio al renderizar: en la captura la pastilla estaba vacía.

---

## 27. El implantado 12 × 36

20 de septiembre. La propuesta completa, con las decisiones de Salvador
escritas, está en `PROPUESTA_12X36.md`.

**Qué es.** Un puesto de doce horas cubierto los siete días por **dos
personas de la misma categoría** que se alternan día con día. Doce de
trabajo por treinta y seis de descanso. Es la escala de Brasil; lo que
Centauro opera en México —una persona, doce horas corridas, los días del
acuerdo— es el otro tipo y no se tocó.

### La regla que manda

**Una persona no puede trabajar dos días seguidos.** No es una
preferencia del armado: define la escala, y todo lo demás —la
alternancia entre meses, el reemplazo, el relevo— se dobla ante ella.

### Las decisiones de Salvador

- **No hay días adicionales.** El mes es el mes. Lo que el cliente pida
  de más sale como un **servicio eventual aparte**. Dentro del mes solo
  pueden crecer las horas extra. La puerta del día adicional quedó
  cerrada para 12 × 36, con la salida escrita en el mensaje.
- **Dos personas, misma categoría, una sola unidad.** Son reglas y el
  sistema las frena; no son avisos.
- **El consultor dice cuál empieza.** El orden en que se capturaron es un
  accidente; de esto sale quién trabaja el día 1 de cada mes que se abra
  después.
- **Queda abierto para cualquier país.** Viene de Brasil pero no es de
  Brasil.
- Los viáticos, el cierre de fin de mes y el corte semanal de nómina:
  **igual que en el natural**.

### La alternancia se calcula, no se guarda

Dos personas alternándose son **una paridad**, y una paridad no necesita
una tabla que mantener en pie. `de_quien_es()` la resuelve desde el
primer día del mes y de quién arrancó; el calendario y el rehacer los
días dan la misma respuesta **por construcción**, no por disciplina.

La continuidad entre meses vive en `arranque_del_mes()`: con el día
anterior pegado —el 31 contra el 1— abre quien **no** trabajó ese día.
Si no, esa persona haría dos seguidos.

### El reemplazo no necesitó código

Regla de Salvador: A se enferma, **B sigue igual** y entra **C** a cubrir
**los días de A** hasta que A vuelva. Nada de intercambiar turnos entre
A y B: eso le movería los días a quien no faltó.

Se paga así: si el cambio se hace el día que A ya arrancó, **ese turno se
paga a los dos** —es el día partido que ya existe—; si se sabe con
anticipación, **solo se pagan a C los días que trabaje**.

**El motor ya hacía exactamente eso.** Mira día por día si la persona que
sale está asignada, y el día que no lo está lo salta: los días de B no se
tocan porque B no es quien sale. No hizo falta escribir código —hizo
falta **probarlo con un 12 × 36 enfrente**, que es lo único que garantiza
que siga siendo cierto el día que alguien toque el motor por otra razón—.
Dos pruebas: que C toma los días de A y ninguno más, y que si A ya
arrancó el día, ese turno queda con los dos.

### La pantalla, como la pidió Salvador

En asignación, cuando el turno es 12 × 36 el bloque se arma distinto:
**una categoría para las dos** —pedirla por renglón es pedirla de más
cuando es regla que sea la misma—, **las dos personas**, y **la unidad,
opcional**. Las secciones de quién solicita y el acuerdo no se tocaron.

### Y un bug de paso

El mes que se abre solo copiaba la plantilla **sin el rol**. El rol no es
un adorno: de él salen el precio al cliente y la comisión, y sin él una
jornada no se puede cobrar ni pagar. Cada mes automático nacía con la
plantilla desarmada y no se veía hasta el corte. Se arregló al tocar esa
misma línea para copiar quién empieza.

### Lo que quedó y lo que falta

Ocho pruebas nuevas (`test_12x36.py`): el mes entero, que nadie hace dos
días seguidos, que empieza quien se marcó, el verde parejo, los tres
candados, y que **el implantado natural sigue exactamente igual**.
Migraciones `e4c19d70b3a8` (el tipo) y `f0b82e4c15d7` (quién empieza).

Y dos más del reemplazo, con lo que la lista de la propuesta queda
completa. Lo que falta ahora no es código: es verlo operar.

---

## 28. El recorrido de la primera vez

20 de septiembre. La tercera capa de la ayuda, y la última que faltaba
de lo que Salvador pidió el 18.

La primera capa es el pie que cada bloque trae escrito. La segunda es el
`?`. Esta es la que solo hace falta una vez: la que le dice a quien entra
por primera vez qué es esto y dónde está lo suyo.

### Tres pasos, no diez

Un paso por pantalla son diez clics para llegar a algo que nadie leyó, y
enseña que la ayuda de este sistema se salta. Son tres: **qué tienes
arriba**, **dónde está el detalle cuando algo no se entienda** —que
entrega a la capa 2 en vez de repetirla— y **dónde vive lo tuyo**.

### El menú y el recorrido salen de la misma lista

`MENU` en `app.js`: cada entrada con su ruta, su texto y **lo que el
recorrido cuenta de ella**. De ahí sale la barra y de ahí sale el primer
paso, así que cada quien ve exactamente sus entradas —el consultor las
suyas, finanzas las suyas— y **el día que se agregue una pantalla, el
recorrido la trae sola**.

Es la misma regla de siempre: un tutorial que vive aparte se despega el
día que la pantalla cambia, y nadie se entera hasta que alguien sigue un
paso que ya no existe.

### El candado que faltaba

Esas claves no se escriben como `t("...")` —viven en la tabla y salen
como variables— así que `revisar_idioma` no las veía. Ahora también barre
los `texto:` y `cuenta:` del menú. Sin eso, agregar una pantalla y
olvidar su texto dejaba la barra con la clave escrita, `nav_flota`, a la
vista de todos.

### Una vez por persona, no por navegador

Decisión de Salvador. Por navegador es gratis y está mal de dos maneras:
quien ya lo vio lo vuelve a ver al cambiar de computadora, y quien nunca
lo vio no lo ve si entra desde una que ya lo mostró. Va en
`Usuario.recorrido_en` (migración `a7d2c48f91e0`).

**Se marca al abrirlo, no al terminarlo.** El que lo salta en el primer
paso también lo vio; si se marcara al final, saltarlo lo dejaría
apareciendo cada vez que entra, y un recorrido que no se deja cerrar se
aprende a odiar.

Se vuelve a ver desde la pastilla del nombre, con el idioma y la salida:
es donde ya vive lo que no cambia nunca, y donde alguien lo va a buscar
sin que nadie se lo diga.

---

## 29. El correo que sale de la empresa

20 de septiembre. Los avisos se escribían en `Notificacion` y ahí se
quedaban. El modelo lo decía desde el primer día —*"en el demo se
registra; el envío real se conecta después"*— y seguía siendo cierto: la
encuesta al ejecutivo, el aviso al consultor de que alguien trabajó su
servicio en cobertura, la hoja liberada. Todo escrito, nada entregado.

### La costura

Se habla **SMTP**, no la API de ningún proveedor. SMTP lo hablan todos
—SES, Postmark, Mailgun, Google Workspace, el servidor de la casa— así
que elegir proveedor es llenar cuatro renglones del `.env` y no cambiar
código. El día que haga falta uno que solo hable HTTP, la única función
que se reescribe es `correo.entregar()`.

Sin dependencias nuevas: `smtplib` viene con Python.

### Apagado por omisión, y que no mienta

Sin `CORREO_HOST` y `CORREO_DE` no sale nada: el aviso se queda
pendiente y espera. **Un sistema que se cree configurado y no lo está es
peor que uno apagado**, porque nadie va a buscar el correo que nunca
llegó. Por eso `despachar()` contesta `configurado: false` y no finge
que mandó cero.

### Escribir y entregar son dos cosas distintas

Entre una y otra hay un proveedor que puede estar caído, una dirección
mal escrita y una bandeja que lo rebota. El aviso ahora sabe en cuál de
las dos está: `estado`, `intentos`, `salio_en` y **`ultimo_error`** —que
existe porque *"no salió"* no le sirve a nadie: lo que hay que saber es
si fue la dirección, la clave o el buzón lleno—.

Se reintenta cinco veces y después queda en `fallida`. Un proveedor
caído se levanta; una dirección mal escrita no se arregla sola.

### Cada cinco minutos, no al instante

El aviso se escribe dentro de la transacción que lo origina —un cierre,
una encuesta, una cobertura— y mandarlo ahí mismo ataría esa operación a
que el proveedor conteste. Se escribe, se sigue trabajando, y se entrega
aparte.

### Cuidado el día que se encienda

Todo lo que ya existe entra como `pendiente`, que es lo que es. **Lo
primero que hará el despachador es mandar la cola acumulada.** Antes de
poner las credenciales conviene mirar `GET /sistema/correo` y ver cuántos
hay; si son meses de avisos viejos, hay que decidir qué se hace con
ellos.

### Lo que sigue sin salir por correo, y es a propósito

El **código de recuperación** de la app de campo. Son cuatro dígitos que
el consultor dicta por teléfono, y lo que protege ese camino es que
quien los entrega reconoce la voz de quien llama. Mandarlo por correo
sería cambiar eso por "quien tenga el buzón".

---

## 30. La cara de los correos

20 de septiembre. El despachador ya entregaba, pero entregaba texto
suelto. Diez avisos salían de la empresa sin parecerse entre ellos ni
parecerse al task sheet, que es lo que el ejecutivo sí conoce.

**Un solo armazón: `correo_html.py`.** Filo azul arriba, el logo, la
placa AI/EP, el folio, el título y el pie. El cuerpo lo sigue
escribiendo quien origina el aviso, que es el que sabe qué hay que
decir. Se escribe con tablas y estilos pegados a cada etiqueta —feo de
leer, y es lo único que se ve igual en Outlook, en Gmail y en el correo
del teléfono.

### La ficha, no el párrafo

Quién va, en qué unidad y a qué hora van en una tabla de dos columnas.
Un dato metido en un párrafo hay que leerlo entero para encontrarlo, y
esto se abre en el teléfono a las seis de la mañana. Se guarda en
`Notificacion.datos` como JSON de texto —lista de pares— para no atar la
tabla a un tipo de Postgres por cuatro renglones.

### El teléfono al lado del nombre

**Regla de Salvador (20 sep).** Cada vez que sale el nombre de alguien
de seguridad, va su teléfono al lado y se marca de un toque (`tel:`). El
cliente que abre este correo suele necesitar algo *ahora* —que baje el
coche, que suba por una maleta— y lo que hace es llamar. Sin el número
ahí, llama a la central para que la central le pase el número.

### El botón, solo cuando hay a dónde ir

Dos de los diez llevan enlace: el seguimiento en vivo y la encuesta. Un
botón que no lleva a nada enseña a no picar ninguno. El task sheet **no**
lleva botón porque no tiene página pública: hoy lo manda el consultor.

**Y así se queda. Decisión de Salvador (20 sep):** *"no quisiera poner
token al TS, siento que el cliente se va a perder"*.

Se propuso darle a la hoja un enlace con token que vence, como el del
seguimiento en vivo, para que el cliente abriera siempre la versión
vigente. La decisión es no hacerlo, y la razón es la operación real: el
ejecutivo recibe su hoja como archivo, sobre la misma cadena de correo
donde pidió el servicio, y ahí la busca cuando la necesita. Un enlace
que caduca le cambia la costumbre y le agrega una forma de quedarse sin
nada a las seis de la mañana.

Lo que se pierde con esto es que alguien pueda estar mirando una versión
vieja. Se compensa donde ya está compensado: el asunto del correo dice
la versión y la ficha dice **qué cambió**, que es lo que de verdad se
lee cuando llega uno nuevo.

### Las dos versiones, en el mismo mensaje

HTML y texto plano siempre. Hay buzones que bloquean el HTML, y **un
correo que llega vacío es peor que uno feo**. En la versión de texto el
enlace va escrito completo, no escondido en un botón.

### La encuesta se queda con el suyo

`encuestas_html.correo()` llevaba meses escrito y nadie lo usaba para
mandar. Ahí las estrellas se pican desde el mensaje, en tres idiomas;
meterlo en el armazón general sería pedir lo mismo con menos. El aviso
lo dice con `plantilla="encuesta"`.

### Dos correos que cambiaron de fondo, no de forma

**El cierre del día** (petición de Salvador, 20 sep) ahora dice cuántas
horas extra se generaron —y dice *"ninguna"* cuando no hubo, porque el
silencio se lee como "no las contaron"— y a qué hora y dónde es la
presentación de mañana. Son las dos preguntas que el cliente hace por
teléfono en cuanto se le va el equipo. Si el día siguiente no existe, lo
dice; si está salteado, dice la fecha en vez de prometer un "mañana" que
manda al ejecutivo a esperar abajo a nadie.

**El aviso de cobertura** decía *"movimiento en tu servicio"* y nadie lo
entendía. Ahora el asunto dice quién y qué: *"EP/E-042: Beatriz Román
movió tu servicio"*, y el cuerpo aclara que es para que lo sepa, no algo
que haya que atender.

### El logo nuevo

Salvador mandó el logo grande el mismo día. El que estaba era un WEBP de
321 × 180 guardado como `logo.png`; el nuevo es un PNG de 1200 × 269 con
fondo transparente —se le recortó el blanco de alrededor y se le quitó el
fondo por inundación desde los bordes, solo el de afuera, para no
agujerear el arco ni la figura, que también son blancos—.

No se subió el original de 4080 px porque el logo se incrusta en base64
**dentro** de cada documento y de cada correo: ahí cada byte se paga en
todos. A 1200 px imprime bien y pesa 39 KB.

El logo nuevo ya trae su bajada —*Advanced Security Consulting*—, así que
la placa **AI/EP**, que iba debajo, dejaba tres renglones apilados antes
de que empezara el correo. Ahora va **al lado**, alineada abajo, en una
tabla de dos celdas (no flex: el Outlook de escritorio no lo pinta). Y la
encuesta dejó de tener su propia copia de la marca: usa la misma, para
que no queden nueve correos con una cara y el décimo con otra.

### Acentos en lo que lee el cliente

De paso: el correo decía *"MANANA"*, *"termino a las 21:40"* y
*"Presentacion"*. Adentro el código sigue en ASCII, pero lo que sale a
nombre de la empresa va acentuado. Y la fecha dejó de ser `2026-09-19`:
ahora dice *"sábado 19 de septiembre"*, porque una fecha en formato de
base de datos obliga a traducirla mentalmente para saber si es hoy o el
jueves, y el cliente no tiene por qué hacer esa cuenta a las nueve de la
noche.

### Los acentos llegaban rotos

Y al verlo en su pantalla, Salvador cazó lo que el código no: el correo
decía *"sÃ¡bado"*, *"terminÃ³"*, *"MAÃ±ANA"*. El HTML del correo salía
con `<!doctype html>` y de ahí directo al `<body>`, **sin declarar el
juego de caracteres**. El buzón entonces adivina —casi siempre latin-1—
y cada acento, que viaja en dos bytes, se pinta como dos símbolos.

Las páginas que ya existían —task sheet, hoja del implantado, la página
de la encuesta— sí lo declaraban. La diferencia no era técnica: esas se
habían abierto en un navegador mil veces, y **los correos nunca se
habían visto**. Se arregló en los dos correos (el general y el de la
encuesta) y también en el mensaje SMTP, que ahora dice `charset=utf-8`
en las dos versiones en vez de dejar que lo adivine `EmailMessage`.

**Candado nuevo, el décimo de `revisar.py`:** `revisar_charset()` mira
lo que cada archivo de `app/` *escribe*, no lo que el archivo es. Si una
plantilla arma un `<!doctype html>` y en ninguna parte dice `charset`, lo
apunta. Con su prueba.

### Publicar el task sheet dejó de avisar

**Decisión de Salvador (20 sep).** El task sheet se corrige varias veces
mientras se arma —se mueve la hora, entra otra unidad, se cambia una
nota— y un correo por cada versión le enseña al cliente a no abrir
ninguno. Cuando llega el cuarto que dice "task sheet v4" ya nadie lo
mira, y el que importaba era ese.

`publicar()` nace con `avisar=False`. El correo sale solo cuando quien
publica lo pide. En la práctica hoy no había pantalla que publicara —el
TS lo manda el consultor sobre la misma cadena de correo donde se pidió
el servicio—, así que esto es un candado para el día que sí la haya: la
casilla nacerá apagada.

---

## 31. En qué idioma lee cada quien

20 de septiembre. Los diez correos salían **en español fijo**, mientras
el task sheet del mismo servicio salía en inglés, portugués o español.
Un ejecutivo extranjero recibía su hoja en su idioma y dos horas después
un correo que no entendía.

La regla no hubo que inventarla: `textos.py` —el archivo de textos del
task sheet— arranca desde hace meses diciendo *"por defecto va en
inglés, porque el ejecutivo suele ser extranjero"*. **El correo era el
que se había salido de la regla.** Salvador la confirmó y le puso su
otra mitad: *"normalmente el ejecutivo habla inglés; el solicitante
normalmente es del país donde se ejecuta la tarea"*.

### Dos datos, no uno

`servicio.idioma_ejecutivo` arranca en **inglés**.
`servicio.idioma_solicitante` admite nulo, y vacío quiere decir **el
idioma de su país** —se resuelve al escribir el aviso, así los servicios
que ya existen quedan con la regla nueva sin rellenarlos uno por uno—.

Son dos porque casi nunca coinciden: quien pide el servicio suele ser la
asistente o el área de seguridad del cliente, gente local, y el
principal es el extranjero. Quien captura no tiene que hacer nada en el
caso normal; un clic si el caso es el otro.

Y **principal**, no "ejecutivo", en lo que lee el cliente: es el término
del oficio y es como ya sale el task sheet en inglés.

### Lo que se traduce y lo que no

Se traduce lo que escribe el sistema: los asuntos, los cuerpos, las
claves de la ficha y el texto del botón. **No** se traduce lo que
capturó una persona —nombres, direcciones, placas, el motivo del cambio
del task sheet—: traducir una dirección la vuelve inútil para quien
tiene que llegar a ella. Es la misma regla del task sheet.

Los puestos salen de la tabla del task sheet, no de una copia:
*Conductor de seguridad → Security driver*. Si el ejecutivo tiene la
hoja en la mano y el correo le dice otra cosa, parecen dos personas.

### El aviso interno es otra cosa

El de cobertura —*"Beatriz Román movió tu servicio"*— no va a un
cliente: va a alguien de la casa. Ese sale en el idioma del país de
quien lo recibe, que es la misma regla de la app de campo.

### De paso, la encuesta dejó de equivocarse sola

`encuestas.generar()` recibía `idioma="en"` fijo desde el endpoint. Con
un ejecutivo mexicano, la encuesta le llegaba en inglés todas las veces.
Ahora cada una sale en el idioma de quien la contesta, y el parámetro se
queda para el caso raro en que alguien quiera mandarla a propósito en
otro.

### Las dos altas, no una

El implantado tiene su propia pantalla de alta y su propio endpoint.
Quedó fuera de la primera entrega —es la que Salvador pidió no mover sin
avisar— y entró después, con su prueba: un principal que lee portugués
se captura ahí igual que en el eventual, y el solicitante sin capturar
queda en el idioma de su país.

### El aviso guarda su idioma

`notificacion.idioma` es nuevo. El cuerpo y el asunto ya vienen
traducidos de quien origina el aviso, pero el despachador todavía pone
cosas suyas encima —el texto del botón, la línea de lo que vence— y
tiene que decirlas en el mismo idioma que el resto del correo.

---

## 32. El aviso que ya no vale

20 de septiembre. El despachador existe desde esta mañana pero no hay
proveedor, así que los avisos se escriben y se quedan en la cola. **Ya
hay semanas de ellos esperando.**

El día que se pongan las credenciales, lo primero que haría el
despachador es vaciar esa cola: a un cliente le llegaría un correo que
dice *"su equipo de seguridad está en el lugar"* de un servicio de hace
un mes. Eso no es un correo tarde. Es un correo que hace dudar de todo
el sistema.

### La caducidad, no la limpieza

Se podía limpiar la cola a mano antes de encender, una vez. Pero eso
resuelve un día y deja el problema para el siguiente: el fin de semana
que el proveedor se caiga, pasa igual.

**Decisión de Salvador (20 sep): si no salió el mismo día, ya no sale.**
`HORAS_DE_VIDA = 24`. Los diez avisos son operativos —llegó al punto,
faltan 30 minutos, terminó el servicio, task sheet nuevo— y ninguno
sirve al día siguiente.

Un aviso vencido **no se borra**: queda en estado `vencida`. *"No llegó
el correo"* y *"no se mandó"* son dos conversaciones distintas, y la
pantalla tiene que poder separarlas. Tampoco gasta un intento: no se
intentó, se descartó.

### El enlace muerto también cuenta

Un aviso cuyo enlace ya expiró —el seguimiento en vivo, la encuesta—
tampoco sale, aunque sea de hace una hora. Llegaría con un botón que no
lleva a ningún lado, y eso es peor que no llegar.

### Lo que se mira antes de encender

`GET /sistema/correo` ahora contesta **`saldrian`** y **`viejos`**: los
que van a salir en la primera vuelta y los que ya no. Es el número que
hay que mirar antes de poner las credenciales en el `.env`.

---

## 33. La hora la ponía el teléfono

20 de septiembre. De la revisión de la app de campo
(`REVISION_APP_CAMPO.md`), los dos hallazgos graves. Los dos viven en
`operacion.registrar_hito`.

### La marca probaba lo que el teléfono dijera

`ahora = marcado_en or recibido`: si la app mandaba la hora, esa era la
hora buena, **sin cota ni hacia adelante ni hacia atrás**. Existe por
una razón buena —marcar sin señal y mandar después— pero abría tres
puertas al mismo tiempo:

- **La ventana de horario se evalúa contra esa hora**, así que una marca
  "puntual" pasaba el candado llegara cuando llegara.
- **Con una hora futura el atraso sale negativo**, y entonces ni se
  marca diferida ni se manda a revisar: justo lo contrario de lo que
  debería.
- **En el fin de servicio esa hora fija `fin_real`**, de donde salen las
  horas extra que se le facturan al cliente y se le pagan a la gente.

Ahora una marca del futuro no se toma como buena: se guarda la hora del
servidor, se dice en el aviso lo que dijo el teléfono y la central lo
revisa.

**No se rechaza la marca.** Un teléfono con el reloj mal dejaría a
alguien parado en la calle sin poder marcar, y eso es peor que el
problema. Se acepta, se corrige y se señala.

**Y se revisa el día del servicio, no antes.** Es cuando las marcas
ocurren de verdad y cuando el engaño serviría de algo: adelantar el
reloj para caer en la ventana, o estirar el cierre para cobrar horas
extra. Una marca de una jornada que todavía no llega ya la caza la
ventana de horario.

### El día se podía cerrar sin haber llegado

Solo el contacto con el ejecutivo pedía un hito previo. **El fin de
servicio no pedía nada:** una llamada directa dejaba la jornada
terminada, fijaba la hora de cierre y mandaba el correo de *"servicio
terminado"* al cliente, sin pasar por la geocerca ni por la ventana. El
orden lo imponía la pantalla, que es lo más fácil de saltarse.

Ahora el fin de servicio pide la llegada marcada. **La llegada, no el
contacto:** el ejecutivo puede no aparecer —y el servicio se prestó
igual—, pero nadie termina un día al que nunca llegó. El día que de
verdad falte la llegada, la central cierra a mano con justificación, que
para eso existe `cerrar_a_mano`.

Salió un efecto colateral sano: las pruebas del candado de la unidad
cerraban el día sin marcar nada antes. Ahora hacen el día completo, que
es como pasa en la calle.

### Lo que destapó el candado

Al correr la batería, una prueba del task sheet falló diciendo que un
conductor con dos días trabajados tenía **cero horas acumuladas**.

El punto de origen de esas pruebas estaba a 355 metros de donde el
conductor marca su llegada, y la geocerca es de 250: **la llegada se
rechazaba siempre**. Nadie lo había notado porque el fin de servicio
entraba igual, la jornada quedaba TERMINADA y todo lo demás cuadraba.
Con el candado, el día ya no se cierra y el hueco salió a la luz.

Dicho de otro modo: había una prueba que decía ejecutar dos jornadas y
no ejecutaba ninguna. Se corrigieron las coordenadas, no el candado.

### De paso, tres errores que no decían qué hacer

"La jornada no tiene punto de origen configurado", "Se requiere
ubicacion para marcar la llegada" y el de la secuencia salían como
texto pelado. Ahora llevan su `que_hacer`, como el resto de los errores
de campo: quien lo lee está de pie en la calle.

---

## 34. Que la app no se caiga cuando más se necesita

20 de septiembre. Los hallazgos 3 a 6 de `REVISION_APP_CAMPO.md`. Todos
son la misma historia: la app sabía qué hacer sin señal, pero no sabía
**decírselo a quien la estaba usando**.

### Sin señal abría en blanco

El service worker guarda el armazón para que la app abra sin línea. La
lista no incluía `/consola/idioma.js`, y `app.js` lo importa al
arrancar: sin señal el módulo no cargaba, el grafo de módulos fallaba
entero y **la app salía en blanco**. Justo el sótano para el que existe
ese archivo.

De paso, el armazón se guarda ahora **de una en una y sin rendirse**.
Con `addAll`, una sola ruta que conteste 404 tira la instalación
completa, y sin service worker no hay ni armazón ni avisos.

### "Un momento…" sin salida y sin botón rojo

Las peticiones no tenían tiempo límite —el teléfono no corta solo— y la
pantalla de espera **reemplazaba todo**, incluida la barra y el botón de
emergencia. Con media barra de señal, alguien se quedaba mirando "Un
momento…" sin navegación y sin forma de pedir ayuda.

Ahora hay reloj: 25 segundos, y 120 para lo que lleva fotos, porque
subirlas con mala señal tarda de verdad. Y la espera solo reemplaza el
contenido.

### El botón rojo, donde siempre dijo que estaba

La cabecera de `app.js` declara desde el primer día: *"el botón rojo
siempre está, en todas las pantallas"*. **No era cierto**: vivía solo en
Hoy. Quien estaba en Viáticos, en Pagos o a medio llenar una revisión
tenía que navegar para pedir ayuda.

Ahora lo pinta `conBarra`, con los datos de lo último que se supo del
día. Si nunca se supo, el botón sale igual y manda la alerta sin
jornada: mejor eso que no mandarla. La banda de lo que quedó sin enviar
se mudó al mismo lugar, por la misma razón.

### Marcar sin señal ahora se dice, y no se duplica

Al fallar la red la marca se encolaba —bien— y la pantalla se repintaba
con los datos **de antes de marcar**: el mismo botón reaparecía
habilitado y sin mensaje. El equipo creía que no había pasado nada y
volvía a tocar; a la central le llegaban tres llegadas con tres horas
distintas.

Ahora el botón dice "Guardado ✓", un aviso explica que sale solo en
cuanto vuelva la señal, y **la cola no guarda dos veces el mismo paso
del mismo día**: se queda la primera marca, que es la hora en que de
verdad pasó.

### Salir ya no es un accidente

Era un botón suelto sin confirmación. Tocarlo sin querer a las seis de
la mañana y sin señal dejaba la app inservible, porque para volver a
entrar hace falta el servidor. Ahora pregunta, y avisa aparte si hay
marcas sin enviar.

Y al salir se borra **también la cola**. Se quedaba: las marcas
pendientes del usuario anterior se intentaban mandar después con el
token del siguiente.

### Los errores, en el idioma de quien mira

Cuando se caía la señal y no había memoria guardada, lo que se veía era
el error del navegador: *"Failed to fetch"*, en inglés y sin decir qué
hacer. Ahora las fallas de red y de tiempo llegan con código 0 desde
`api.js` y la app las cuenta en castellano —o en inglés o portugués, el
de quien mira—: *"No hay señal. Lo que marques se guarda y sale solo
cuando vuelva."*

### La revisión de unidad: media corrección y una lección

El hallazgo 7 decía que la revisión "no funciona sin señal" y que había
que encolar las fotos. **Al ir a arreglarlo, el código contestó:** que
las fotos no se encolen está decidido a propósito, y la razón está
escrita ahí mismo —*"son medio mega y la cola vive en el teléfono; más
honesto es decir que no salió y que lo intente donde haya señal, con las
fotos todavía en pantalla"*—. Guardar media docena de fotos en el
almacenamiento del teléfono es prometer algo que puede no caber.

Así que la decisión se respeta y el hallazgo se corrigió en el
documento. Lo que sí faltaba era más chico y ya está: la pantalla **lee
de memoria** —sin línea al menos se ve qué unidad se trae y si ya se
revisó—, y el error salía en inglés.

La lección es del método: un hallazgo de revisión es una hipótesis hasta
que el código la confirma. Este llevaba su respuesta escrita al lado.

---

## 35. Los avisos al teléfono, encendidos

20 de septiembre. Salvador generó las llaves VAPID, así que el push deja
de estar apagado. Con eso a la vista, los defectos que la revisión
encontró dejaron de ser teóricos.

### Dos defectos que llevaban ahí desde el primer día

**El recordatorio de la víspera terminaba en error todos los días.** La
función cerraba con `dia.isoformat()` y la tarea de las 17:00 la llama
sin fecha. Los avisos sí salían —el guardado es la línea de antes— pero
la tarea quedaba marcada como fallida: nadie sabía a cuántos se avisó ni
cuántos no tienen teléfono registrado. Ahora devuelve los días que de
verdad procesó, que son los de cada país.

**El apagado de teléfonos muertos se perdía.** Cuando un teléfono ya no
existe, el servidor apaga esa suscripción. En el relevo por contingencia
ese apagado se llamaba *después* del guardado de la transacción y no
había otro: se le seguía mandando a un teléfono desinstalado para
siempre.

Los dos llevaban ahí desde el principio **porque no había ni una prueba
de push**. Ahora hay cinco.

### Al que sale también hay que decirle

`avisar_relevo` le avisaba solo al que entra. El reemplazado se enteraba
por teléfono, o se presentaba a las seis de la mañana a un servicio que
ya no era suyo. Es el mismo aviso y le faltaba la mitad.

### Los dos avisos que dejan a alguien parado en la calle

**La cancelación.** El servicio se cancelaba entre el consultor y el
sistema, y el equipo se enteraba al llegar. Es el aviso más barato de
todos y el que más pena da no tener.

**El cambio de hora.** La confirmación de la víspera se hace sobre una
hora; si esa hora cambia después y nadie avisa, la confirmación queda
apuntando a algo que ya no es cierto.

Los dos mandan **un aviso por persona, no por día**: a quien le cancelan
tres días no le sirven tres notificaciones iguales. Y los dos salen
*después* de guardar: el servicio queda cancelado pase lo que pase con
el aviso.

### La versión del armazón

`sw.js` subió a `v3`. El armazón cambió —entró `idioma.js`— y sin subir
la versión el teléfono que ya tiene la app instalada seguiría sirviendo
el armazón viejo desde su cache.

### Lo que sigue faltando del push

Avisos que aún no existen: te asignaron un servicio nuevo, cambió el
punto de encuentro, te depositaron el viático, te rechazaron un
comprobante. Y dos detalles de la entrega: el aviso caduca a la hora
—si el teléfono está guardado, el recordatorio se pierde— y la
notificación no trae botón de "confirmo que voy", que son cuatro toques
a las seis de la mañana.

---

## 36. La cola de la app de campo

20 de septiembre. Los cuatro hallazgos que quedaban de
`REVISION_APP_CAMPO.md`. Con esto, los 17 quedan cerrados.

### Las fotos dejaron de viajar por gusto

`GET /campo/servicios/{id}/unidades` mandaba **todas las fotos de todas
las unidades del servicio** —recepción y entrega, de todos los
compañeros— en cada consulta. Media docena de fotos de medio mega, a un
teléfono con mala señal, cada vez que se abre esa pantalla. Y traía
revisiones que no eran suyas.

Ahora la lista dice **cuántas** hay y las fotos se piden de una revisión
a la vez: al tocar "Ver las 5 fotos", o al abrir el formato de entrega,
que es donde de verdad hacen falta para comparar lado a lado. El
endpoint nuevo tiene el mismo candado que guardar: la unidad tiene que
ser de un servicio suyo.

### Una marca rechazada ya no se pierde

Lo que el servidor rechaza no vuelve a la cola —eso está bien, el
servidor ya decidió— pero se avisaba con un `alert` y se borraba **para
siempre**. Si el aviso saltaba con el teléfono en el bolsillo, la prueba
de que esa persona llegó desaparecía y nadie se enteraba.

Ahora se aparta y se queda arriba de la pantalla, con su motivo, hasta
que alguien la lea y toque "Entendido". Una marca rechazada es un día
sin prueba de que la persona estuvo ahí: merece quedarse a la vista.

### Un renglón por pantalla

Tres de las cinco no decían qué se espera del usuario ahí. Ya lo dicen,
en una línea, porque quien lee está de pie con una mano:

- **Hoy:** *"Marca cada paso cuando pase. Sin señal se guarda y sale
  solo."*
- **Pagos:** *"Lo que ya ganaste. Lo de esta semana todavía puede
  cambiar hasta el corte."*
- **Yo:** *"Tus cursos y tu calificación. Aquí enciendes los avisos de
  la víspera."*

Y el de Revisión, que existía, **subió**: estaba al final de la
pantalla, después de las unidades; para cuando se leía, ya se había
decidido qué hacer.

### El aviso que espera, y el que se contesta de un toque

El aviso caducaba **a la hora**. El recordatorio sale a las 17:00: si el
teléfono pasaba la noche guardado, se perdía justo el caso que el
recordatorio existe para cubrir. Ahora espera 16 horas —hasta bien
entrada la mañana— y los demás, 12.

Y lo urgente sale marcado como urgente: un relevo de hoy para hoy se
entrega de inmediato aunque el teléfono esté ahorrando batería; el
recordatorio de la víspera, no.

**El botón "Confirmo que voy" vive ahora en la propia notificación.**
Confirmar eran cuatro toques a las seis de la mañana: desbloquear,
abrir, buscar el servicio, confirmar. El trabajador de fondo no puede
hablar con el servidor —el permiso de la sesión vive en la app— así que
abre la app con una marca y la app confirma sola, y lo dice.

---

## 37. El respaldo, probado

20 de septiembre. `despliegue/respaldo.sh` existía y estaba bien pensado
—saca, restaura en una base desechable, cuenta filas, y solo entonces
rota— pero **nunca se había ejecutado**. Apuntaba al compose de
producción, que todavía no existe encendido en ningún lado.

Un script de respaldo que solo corre en el servidor es un script que
nadie prueba hasta el día que hace falta.

### Se puede correr hoy

`--probar` usa el compose de desarrollo, saca el dump a una carpeta
temporal, lo restaura, verifica y borra todo al terminar. No rota, no
sube nada, no toca los respaldos de verdad. Es lectura: lo único que
crea es una base `verificacion_<fecha>` que se borra sola.

### Contar filas no prueba que las fotos estén

La verificación contaba filas de cuatro tablas. Eso deja pasar el caso
que importa: las imágenes viven **dentro** de la base —las cinco fotos
de cada revisión, los comprobantes, las firmas— y son lo que se usa para
discutir un golpe tres semanas después. Una fila que llega con la imagen
cortada cuenta igual.

Ahora se compara el contenido: un md5 por imagen y un md5 del conjunto,
entre la base viva y la restaurada. Comparar los datos completos de las
dos bases no cabría en memoria; los hashes sí.

Y se comprueba que la copia traiga la versión de alembic: una base
restaurada sin esa marca se abre, pero ya no se puede seguir migrando.

### Lo que encontró la primera corrida

Dos cosas, y las dos son el argumento entero de probar un respaldo
antes de necesitarlo.

**El nombre de la base no era válido.** El sello lleva un guion
—`20260919-1442`— y en el nombre de un archivo se lee bien, pero
Postgres no acepta guiones en el nombre de una base sin comillas. El
script sacaba el dump y moría justo en la verificación. En el servidor
eso habría sido un log con un error que nadie mira, una carpeta llena de
respaldos que parecen buenos y **ninguno verificado jamás** —hasta el
día de restaurar de verdad.

**Y la verificación de las fotos pasaba por vacío.** La base de
desarrollo no tiene ninguna foto, así que la comparación de imágenes
salía con palomita verde sin haber comparado nada. Un respaldo que dice
"verificado" cuando lo crítico no se miró es peor que uno que no dice
nada. Ahora lo distingue: *"no hay ninguna en la base. ESTA PARTE NO SE
PROBÓ."*

### Cerrado con fotos de verdad

Para no dejarlo a medias se sembró `sembrar_revision_demo.py`: una
revisión de recepción con sus cinco fotos de 250 KB cada una —lo que
pesa una foto ya reducida por la app— sobre el primer servicio con
unidad. Lo que prueba no es que la foto se vea bonita: es que **ese
peso sobreviva al dump y a la restauración**.

Con eso el ciclo quedó verificado entero. La siembra se reconoce por su
propia nota y se quita con `--borrar`, pero conviene dejarla: hace que
cada corrida del respaldo verifique de verdad en vez de pasar por
vacío.

---

## 38. El camino al meet and greet

20 de septiembre. Pregunta de Salvador: *"si el conductor se queda
dormido y no llegara a su meet and greet, ¿cómo lo podría detectar la
central?"*. La respuesta honesta era: **no se detecta**. El sistema
vigilaba lo que pasa durante el servicio —el que deja de reportar, las
horas extra— y nada del silencio de antes. La central se enteraba
cuando llamaba el cliente.

### El número que decide el diseño

Reponer a alguien toma **hasta hora y media**. Con eso, enterarse a la
hora de la presentación es no enterarse:

| Primer toque | Silencio detectado | El reemplazo llegaría |
|---|---|---|
| 90 min antes | 75 min antes | **15 min tarde** |
| 120 min antes | 105 min antes | 15 min de sobra |

Por eso el primer toque va a **dos horas** de la hora de estar en el
punto —no de la hora del servicio—. Salvador había dicho hora y media;
la aritmética de su propia operación pidió dos.

### Tres toques, y lo único que se mira es si se mueve

A las 2 h, 1 h 20 y 45 min: un aviso con su botón, *"¿Vas en camino?"*.
Un toque y se guarda su posición y la distancia en línea recta al punto.
Si la app está abierta reporta sola.

Con dos posiciones y el reloj sale todo, **sin preguntarle a Google**:
si se acerca, si le alcanza el tiempo —la velocidad que necesita contra
la que lleva—, si ya está cerca (y entonces se apaga), si lleva dos
lecturas parado, o si no contesta.

**La línea recta miente a favor** —las calles dan vuelta— así que el
margen es holgado: se alerta solo cuando va claramente corto.

**Lo que no hace:** no calcula hora de llegada con tráfico, no vigila la
puntualidad —eso es del personal de seguridad, decisión de Salvador— y
**no manda una sola noticia de que todo va bien**.

### La ventana es de la persona, no del servicio

Se abre con el toque y se cierra al marcar la llegada o al acercarse al
punto. La app lo dice con todas sus letras cuando lo prende: el día que
alguien sienta que lo vigilan de más, deja el teléfono en la guantera y
se pierde justo la señal que se quería.

### Las dos vigilancias que nadie disparaba

Al hacer esto salió otra cosa: el aviso preventivo de horas extra y la
detección del servicio que deja de reportar **estaban escritos y
probados desde hace tiempo, y eran botones que nadie picaba**. El reloj
solo corría tres tareas. Ahora corre cinco.

Una vigilancia que nadie dispara no vigila nada.

---

## 39. El reemplazo, contado al cliente

20 de septiembre. Pedido de Salvador: que el solicitante y el ejecutivo
se enteren cuando cambia una persona de seguridad o una unidad. Esto es
la propuesta del **cuándo**, que es lo único que de verdad hay que
decidir.

### La regla: se avisa cuando el cambio le cambia el día al cliente

Un reemplazo no es un hecho administrativo, es **otra persona tocando la
puerta del ejecutivo, u otra placa esperando en la calle**. Lo que
decide si sale un correo no es que el cambio exista: es si el cliente se
va a topar con él.

| Cuándo ocurre el cambio | Qué pasa |
|---|---|
| **El servicio está en curso** | Correo de inmediato a los dos. El ejecutivo va a ver a alguien distinto en su coche; enterarse por el correo es mejor que enterarse por la ventanilla. |
| **Es de hoy y todavía no empieza** | Correo de inmediato. El ejecutivo tiene que poder reconocer a quien llega por él. |
| **Es de otro día** | **Sin correo suelto.** El cambio viaja en el task sheet, que es donde el cliente ya busca quién va. Mandar un correo por un cambio de la semana que viene es gastar la atención que hace falta para el de hoy. |

### Tres cosas que el correo sí lleva, y una que no

**Lleva** el nombre de quien entra **con su teléfono a un toque** —regla
del 20 de septiembre—, su puesto, y las placas si lo que cambió fue la
unidad. Es lo que el ejecutivo necesita para reconocer a quien baja del
coche.

**No lleva el motivo.** Que alguien se enfermó, que no llegó, que hubo
un problema: eso es de la casa. Al cliente se le dice **quién va ahora**,
no por qué cambió. Un correo que explica de más invita a preguntar de
más sobre algo que ya está resuelto.

### Cuándo exactamente, dentro de ese momento

Cuando el relevo **queda firme**, no cuando se empieza a mover. Hoy el
cambio ya avisa por teléfono al que entra y al que sale; el correo al
cliente sale en el mismo acto, después de guardar, como todos los demás
avisos: el cambio queda hecho pase lo que pase con el correo.

### Hecho el 20 de septiembre

`operacion.avisar_reemplazo(db, jornada, quien, clase, puesto)` es quien
decide y quien escribe. Lo llaman los dos endpoints de contingencia —el
de personal y el de unidad— después de guardar, y devuelven
`cliente_avisado` para que la pantalla pueda decirlo.

Tres cosas que quedaron escritas en el código y no solo aquí:

- **El puesto sale de la asignación, no de la persona.** Nadie tiene
  puesto fijo —el mismo agente que hoy conduce mañana coordina— y quien
  entra hereda el rol de quien sale. Se traduce con la tabla del task
  sheet, para que el ejecutivo no lea dos nombres distintos del mismo
  puesto en la hoja y en el correo.
- **La ficha lleva el equipo como queda**, no un antes y un después:
  quien llega por él, con teléfonos a un toque.
- **El candado del día usa el reloj de allá.** Si el servidor corre de
  madrugada en UTC, en México todavía es el día anterior; medir con el
  reloj del contenedor haría que el aviso saliera o no según la hora,
  que es la peor forma de fallar.

### Dos candados, por lo que podría morder

Pregunta de Salvador: *"con cuidado que no nos vayamos a topar con pared
o no cierre el ciclo de forma adecuada"*. Las dos cosas que sí podían:

- **El correo no tumba el cambio.** El reemplazo se guarda primero y el
  aviso va después, envuelto: si escribirlo fallara —un correo mal
  capturado, una clave que no existe— la central no puede perder un
  cambio que ya dio por hecho, porque movió gente de verdad. La pantalla
  distingue los tres casos: se avisó, no tocaba avisar, o falló.
- **La ficha del día partido.** Si el servicio ya arrancó, la asignación
  de quien sale **se queda** —tiene que quedarse, porque ese día lo
  cobra— y la ficha salía con los dos nombres: el que se va y el que
  llega. Un aviso de cambio que sigue diciendo el nombre viejo. Se
  arregló con `solo_vigentes` en `_pares_del_equipo`, solo para este
  aviso: los demás la siguen viendo completa a propósito, porque el fin
  del día cuenta quién trabajó.

Siete pruebas, en `tests/test_aviso_reemplazo.py`. Las tres que importan
son la que verifica que el cambio de otro día **no** manda nada, la que
revisa que el motivo no aparezca en ningún campo del aviso, y la del día
partido.

---

## 40. El código de vestimenta

20 de septiembre. Pedido de Salvador: que el consultor ponga el código
de vestimenta del equipo al dar de alta el servicio, y que se vea en la
app y en el task sheet. Solo eventuales.

**Tres opciones y no texto libre.** Casual, semiformal, formal. "Traje
oscuro sin corbata" escrito a mano en cada servicio se lee distinto cada
vez, y quien lo tiene que cumplir lo lee en el teléfono a las cinco de
la mañana.

**Arranca vacío, y vacío no es "casual".** Un servicio del que nadie
acordó nada no dice nada: ni la app ni la hoja imprimen la línea. Una
etiqueta vacía en el task sheet del cliente es peor que no tenerla.

**Solo el eventual.** El implantado trabaja todos los días con el mismo
cliente y su vestimenta se acuerda una vez, no servicio por servicio. La
columna nace nula, el alta del implantado nunca la escribe y el endpoint
la rechaza con 409. Nada del implantado se movió.

**También en la tarjeta de mañana.** El dato sirve la noche anterior,
que es cuando se decide qué ponerse; verlo camino al aeropuerto ya no
sirve. Por eso está en las dos tarjetas de la app y no solo en la de
hoy.

**Se puede cambiar después del alta**, desde la pantalla del servicio y
junto a la señal —las dos son lo mismo: cómo se ve el equipo cuando el
ejecutivo lo encuentra—. Al guardar, la pantalla recuerda volver a
publicar el task sheet: lo que no puede pasar es que el equipo se entere
por teléfono mientras la hoja del cliente dice otra cosa.

Migración `f1a20d64c9b3`. Siete pruebas en `tests/test_vestimenta.py`.

---

## 41. La carrera entre el consultor y el banco

20 de septiembre. Pregunta de Salvador: *"¿qué pasa si se solicita
viático y, mientras finanzas está haciendo el depósito, el consultor
elimina ese gasto, y cuando finanzas regresa a subir el archivo ya no
está la solicitud?"*.

Pasaba esto, en tres puertas:

- `cancelar-solicitud` cancelaba **todo** lo que estuviera en camino,
  incluido lo que ya estaba en manos de finanzas. El código no
  distinguía.
- Finanzas subía su comprobante y `POST /finanzas/depositar` contestaba
  **404**. Por la puerta del barrido, **409**. El dinero ya había salido
  del banco y el sistema no tenía dónde ponerlo.
- Peor: al **borrar** el día, el equipo o el servicio, las solicitudes se
  borraban de la base y el sistema devolvía un número
  —`transferencias_por_detener`— a quien estaba borrando. A finanzas no
  le avisaba nadie. Si ya había ido al banco, ese depósito quedaba fuera
  del sistema: nadie lo podía comprobar ni reclamar, y la persona
  terminaba con dinero de la empresa que aquí no existe.

### El principio

**El dinero que salió del banco siempre tiene dónde registrarse.** Un
sistema que le contesta "no existe" a un depósito real obliga a
arreglarlo por fuera, y lo que se arregla por fuera no se audita.

### Las tres piezas

1. **No se borra nada con dinero en camino.** `_movimientos` cuenta las
   solicitudes vivas y el borrado se detiene con un 409 que dice por
   dónde se sale. Antes se borraba y se avisaba; ahora no se puede.
2. **Lo que ya está con finanzas, el consultor no lo cancela solo.** La
   `pendiente` se cancela como siempre —es el 90% de los casos—; la
   `enviada` queda con `cancelacion_pedida_en` y sale marcada en la
   bandeja de finanzas, que es quien la cierra. El único que sabe si el
   dinero ya salió del banco es quien lo manda.
3. **La puerta de atrás.** Si aun así el depósito llega tarde, se
   registra con su referencia y su comprobante, marcado
   `sobre_cancelada`, y aparece en el panel del consultor como dinero
   que hay que aplicar o pedir de vuelta. Nunca un 404 contra una
   transferencia que ya existe en el banco.

La 3 es la que no puede faltar: las otras dos bajan la probabilidad,
solo la tercera garantiza que un depósito real no se pierda. Y hay una
prueba de que la puerta no se vuelve una forma de pagar dos veces: la
cancelada que ya tiene depósito no se vuelve a pagar.

Migración `a4b71c92e5d8`. Siete pruebas en
`tests/test_deposito_cancelado.py`.

---

## 42. Los dos avisos del dinero

20 de septiembre. Eran los dos que faltaban del push, y los dos son la
misma historia: el sistema hace bien su trabajo y **no le avisa a quien
le toca**.

### "¿Ya me depositaron?"

Es la pregunta que más recibe la central, y la única forma de
contestarla era que alguien mirara la bandeja de finanzas. El dinero ya
aparecía en la app como saldo, pero solo si la persona entraba a
mirar — y nadie entra a mirar lo que no sabe que llegó.

El aviso va **con la referencia del banco**, a propósito: es lo que
sirve para reclamar si el banco no lo abonó, y es lo primero que pide un
ejecutivo de cuenta.

### El comprobante rechazado

El consultor rechaza un ticket y ese gasto deja de contar como
comprobado. Eso le abre a la persona una diferencia que tiene que cubrir
o que se le va a descuento de nómina al cerrar. Hasta hoy se enteraba de
dos maneras: **cuando veía el descuento en su pago, o cuando alguien le
hablaba**.

Y casi siempre lo que pasó es que el ticket salió borroso o subió el
equivocado — dos minutos de arreglo. Sin el aviso, un problema que se
resolvía solo termina en un descuento y en un reclamo.

Por eso el aviso lleva **el motivo tal cual lo escribió el consultor**
—un rechazo sin razón no se puede corregir, solo se puede discutir— y
**cuánto le falta por comprobar y hasta cuándo**. Va marcado como
urgente: lo que está corriendo es un plazo.

### Y la regla de siempre

Los dos salen después del guardado y envueltos: un aviso que no sale es
un problema; perder el registro de un depósito que ya ocurrió en el
banco es otro mucho peor. Hay una prueba que revienta el envío a
propósito y verifica que el depósito quede igual.

Tres pruebas en `tests/test_push.py`. Sin migración.

---

## 43. La prueba 360

20 de septiembre. Pregunta de Salvador: *"¿cómo corremos servicios de
inicio a fin, con todos los escenarios, y verificamos que en las
pantallas no falta ni sobra información?"*.

La respuesta corta es que **no es una prueba, son cuatro instrumentos**,
y cada uno caza una clase distinta de error. La propuesta completa está
en `PROPUESTA_PRUEBA_360.md`. De los cuatro, van dos.

### 1 · El zoológico — `sembrar_360.py`

Trece escenarios sembrados en la base de desarrollo, con fechas
relativas a hoy: el borrador que no tiene nada, el de mañana con su TS,
uno en curso, uno con el botón de pánico tomado, uno con alguien que no
va a llegar, el día partido por un reemplazo, el depósito que llegó tras
cancelar, el cancelado con dinero afuera, el foráneo con hotel, el de
dos equipos en dos ciudades.

**Se siembra por la puerta de la calle.** Todo entra por la misma API y
con los mismos permisos que usa la operación, y con las mismas ayudas
que las pruebas. Si un escenario no se puede armar por ahí, eso ya es un
hallazgo; y el día que cambie un candado, el zoológico cambia con él en
vez de seguir mintiendo.

Tiene el candado espejo del de las pruebas: si acabara apuntando a
`centauro_test`, se detiene antes de escribir nada.

**Para qué es:** para mirarlo con los ojos. Ninguna prueba automática
puede juzgar si a una pantalla le falta el teléfono del hotel o si sobra
una columna que nadie usa. Eso lo juzga una persona, y para juzgarlo
necesita pantallas llenas de datos creíbles. La ruta está en
`RECORRIDO_360.md`.

De paso salió una mejora real: el desarmado de un servicio vive ahora en
`desarmar_servicio()`, que usan los dos que lo necesitan —el borrado de
verdad y el sembrador—. Esa lista de tablas escrita dos veces es tener
una de las dos mal el día que aparezca una tabla nueva.

### 2 · El recorrido y el cuadre — `tests/test_recorrido_360.py`

Un servicio caminado **de la cotización a la nómina**, sin saltarse una
estación, y cada estación verifica **lo que dejó**: que el TS salga en
los tres idiomas con la gente adentro, que la app del agente vea el
dinero que le depositaron, que los hitos existan y en orden, que cada
correo salga en el idioma de su destinatario.

Y al final el **cuadre**: seis igualdades que no pueden fallar nunca
—lo entregado contra lo explicado, lo depositado contra lo asignado,
todo día terminado con su fin de servicio, ninguna unidad sin entregar
en un servicio cerrado, ninguna alerta abierta en uno cancelado, ningún
viático sin jornada—. Devuelve **la lista completa** y no el primer
problema: si el dinero no cuadra y además quedó una alerta abierta, hay
que enterarse de las dos cosas de una vez.

Hay una prueba que rompe el sistema a propósito —cierra un viático sin
comprobar nada— y verifica que el cuadre lo cace. Una verificación que
nunca falla no es una verificación.

**Lo que encontró en su primera corrida** no fue un defecto del sistema
sino un acoplamiento escondido en el andamio: el kilometraje de
recepción y el de entrega vivían como dos números sueltos en dos
archivos, y tenían que cuadrar entre sí sin que nada lo dijera. Ahora
son `KM_RECEPCION` y `KM_ENTREGA`, juntos y con su razón escrita. El
candado del odómetro, por cierto, se portó perfecto: rechazó la entrega
diciendo el número, qué revisar y por qué.

### Lo que falta de la 360

El **contrato de pantalla**: pantalla por pantalla, que no falte ningún
campo que pinta y que no sobre nada que no debería viajar. Va al final a
propósito, para que lo guíe lo que se vea en el recorrido visual y no lo
que uno suponga desde el código.

---

## 44. El bono del mes y el desempeño

**El calendario, que lo decide todo.** El mes se calcula el **día 3** —no
el 1, porque el viático del último día tiene 24 horas para comprobarse y
calcular el 1 castiga a quien todavía está en plazo; el día 2 queda para
que finanzas suba los comprobantes que entraron al filo—, se autoriza
entre el 3 y el 5, y se deposita el **día 5 o el primer hábil después**.
Decisión de Salvador, 20 de septiembre.

**Los seis criterios**, en el orden en que le importan al cliente y no en
el que son fáciles de medir: llegar al punto (30%), no dejar callada a la
central (25%), entregar la unidad documentada (15%), comprobar el dinero
a tiempo (15%), capacitación (10%) y que el cliente lo vuelva a pedir
(5%). Los dos primeros son más de la mitad del bono porque ahí está el
riesgo.

**Defecto encontrado: el motor ignoraba los pesos configurados.** El
reparto era en partes iguales, así que aplanaba *siempre* el catálogo —con
los cuatro criterios aplicando, puntualidad dejaba de valer 800 y
capacitación dejaba de valer 500: las dos pagaban 650—. La pantalla dejaba
configurar pesos y el motor no los miraba. Ahora se reparte **a prorrata**.
Lo cuida `test_lo_que_no_aplica_se_reparte_a_prorrata_no_en_partes_iguales`,
que compara la proporción entre dos criterios contra la del catálogo.

**Dos criterios que se estrecharon al abrir los datos.**

- *El daño no lo juzga el sistema.* Chocaba con la decisión del 19 de
  septiembre asentada en `campo.py`: un daño nuevo avisa al consultor y
  nada más. Y el daño lo declara **quien recibe**, así que medirlo
  automáticamente dejaría que la palabra de uno le cueste el bono a otro
  sin que nadie lo revise. El criterio quedó en lo que es 100% suyo y no
  necesita juicio de nadie: que la revisión de entrega exista y esté
  completa. El daño sigue su camino —consultor → incidencia con visto
  bueno— y la incidencia ya apaga el mes.
- *La recompra necesitaba un campo.* No había forma de saber que el
  cliente pidió a alguien por nombre; coincidir con el mismo cliente
  puede ser nada más quién estaba libre. Se agregó
  `AsignacionPersonal.pedido_por_cliente`, que marca el consultor.

**El criterio que suma y no resta.** La recompra no reparte
(`CriterioEstrella.reparte = false`). Sin eso no sumaba nada: si al que
no lo pidieron se le repartían sus 130 entre los demás criterios,
terminaba cobrando exactamente igual que al que sí pidieron, y el
criterio quedaba de adorno. Ahora el techo sin recompra es 2,470 y con
recompra 2,600.

**Vacío no es reprobado.** Mientras Odoo no mande la capacitación del
mes, el criterio **no aplica** en vez de reprobar: nadie pierde dinero
porque a un sistema le falte una conexión. Un `false` explícito sí
reprueba —eso ya es un dato—; lo que no hay es `None`.

**El margen de puntualidad.** Tantos minutos, tantas veces al mes
(México: 5 minutos, 1 ocasión). Un umbral de 100% exacto castigaba igual
al que llegó dos minutos tarde una vez y al que llegó cuarenta tarde tres
veces, y lo que no distingue no motiva. Cuando los retrasos perdonables
pasan de las ocasiones permitidas se perdonan los más chicos: el margen
es para el descuido, no para el hábito.

**Llegar es dos cosas, y se mide contra la marca de llegada.** No contra
`inicio_real`: ese campo lo escribe el hito de **contacto con el
ejecutivo**, o sea el meet and greet. Medir la llegada con esa hora
castigaba al escolta que llegó temprano y esperó veinte minutos a que el
ejecutivo bajara. `inicio_real` queda de respaldo para el día raro sin
marca de llegada.

**El agujero de "no aplica".** Lo que decide si el criterio aplica son
las **jornadas**, no las marcas. Es la diferencia entre *no le tocó* y
*no marcó*, y confundirlas abría un hueco con el signo invertido: el mes
sin marcas de llegada se declaraba no aplicable, sus 780 se repartían
entre los demás criterios, y **no marcar pagaba más que llegar a
tiempo**. Ahora un día sin marca cuenta como no llegada. Solo un mes sin
jornadas es "no le tocó".

Salió de escribir la prueba de marcar desde lejos, y de paso quedó
documentado que el servidor **rechaza** esa marca (409) y deja alerta
`FUERA_DE_GEOCERCA`: por eso la ficha distingue *intentó marcar fuera del
punto* de *sin marca de llegada*, que no son la misma falta.

**Dos manos, no una.** `bonos.autorizar` perdió a finanzas: quien
autoriza el bono no es quien lo deposita. Se agregó `bonos.pagar`
(finanzas) y `bonos.configurar` (dirección). El pago vive en
`pago_bono`, con llave única sobre la evaluación —el candado del doble
pago— y su referencia del banco.

**Por qué el bono no viaja en la nómina semanal.** La fecha de pago es
fija (día 5) y el corte semanal cae donde cae: amarrarlos movería el pago
entre el 2 y el 8 según el año. Por eso finanzas tiene su propia bandeja.

**La incidencia que llega tarde.** El cálculo del día 3 lee las
incidencias que ya traen visto bueno. Una que se autoriza después no
alcanza ese mes, y `evaluar()` se niega sobre una evaluación pagada. Para
que eso no sea silencioso, el endpoint de visto bueno ahora revisa si el
bono de ese mes ya está cerrado y lo dice en la respuesta: quien firma se
entera ahí mismo de que su firma no bajó ningún bono. Se agregó
`Incidencia.visto_bueno_en` para poder demostrar que llegó tarde, no que
se ignoró.

**Lo que ve el personal.** `/campo/mi-bono` en la pestaña de pagos: el
monto, el estado en palabras y el desglose con la frase fechada de cada
punto perdido. Enterarse el día 3 de por qué no hubo bono es una
conversación; enterarse el día 5 por un depósito que no llegó es un
pleito. No se le enseña el bono de nadie más ni la referencia del banco.

## 45. El rol de Recursos Humanos

Decisión de Salvador, 20 de septiembre: se crea el rol. **Firma el bono
del mes y reparte los accesos.** Lo que no trae, y es el punto:
**depositar**.

Dirección de operaciones perdió `bonos.autorizar` —sigue clasificando
incidencias, que sí es suyo— y finanzas nunca lo tuvo. Los montos los
fija dirección (`bonos.configurar`); RRHH cierra el mes. Tres manos
distintas sobre el mismo dinero.

**El problema que trajo darle la pantalla de accesos.** Quien reparte
permisos puede darse los que le faltan, y quien puede eso los tiene
todos. Hasta ahora esa pantalla la abrían admin y dirección general, así
que la separación entre firmar y depositar se sostenía sola. Con RRHH
adentro —que es justo quien firma— dejó de sostenerse.

Tres candados nuevos en `accesos.py`, y ninguno depende de la buena fe:

1. **Nadie se da accesos a sí mismo.** `dar_permiso` y `poner_categoria`
   ahora rechazan al actor sobre su propio usuario, igual que ya hacían
   desactivar y cambiar el rol.
2. **Actividades que no conviven** (`INCOMPATIBLES` en `permisos.py`):
   `bonos.autorizar` y `bonos.pagar` no caben en la misma persona, venga
   de su rol, de su categoría o de un permiso suelto.
3. **Un puesto tampoco las junta.** Sin esto el candado anterior se
   esquiva armando una categoría que ya las trae y poniéndosela a
   alguien.

RRHH abre en `#/bonos`: es lo que hace los días 3 y 5 de cada mes; la
pantalla de accesos se usa cuando entra o sale alguien.

Ocho pruebas en `test_rol_rrhh.py`, incluida la que comprueba que un
puesto con **una sola** de las dos sí se arma: un candado que además
impide lo legítimo no sirve.

## 46. La encuesta: ojos y reloj

El motor llevaba meses escrito y completo —dos encuestas cortas al
cierre, la mala calificación abre revisión en vez de castigar sola, el
consultor clasifica y solo entonces puede volverse incidencia—. Le
faltaba exactamente lo mismo que al bono: **que alguien la viera y que
alguien la corriera.**

**Nadie sabía de la queja.** `/encuestas/por-clasificar` no tenía
pantalla. Una calificación baja llegaba, abría revisión, y se quedaba
esperando a un consultor que no sabía que existía. Ahora hay ruta
`#/encuestas` con la bandeja, el botón de revisar y las últimas
respuestas.

**Y ahora le llega el mismo día.** Correo con lo que el cliente dijo
—pregunta por pregunta, porque un "3" suelto no se puede leer— y aviso
al teléfono. Un ejecutivo molesto el viernes es una cuenta en riesgo el
lunes. El aviso **no** dice que alguien la regó: abre revisión, no
castigo, y decirlo al revés predispone a quien va a clasificarla.

**Quién la revisa depende de a quién califican.** La del ejecutivo
califica el servicio: es del consultor que lo llevó. La del solicitante
califica **al consultor**, y ahí él no puede decidir si eso amerita
incidencia —sería juez y parte—: esa sube a dirección de operaciones.

**Nadie las vencía.** `EXPIRADA` solo se escribía si alguien abría el
enlace caducado, así que la que nadie contestó se quedaba en *enviada*
para siempre y la tasa de respuesta nunca cerraba. Tarea diaria
(`encuestas.pasar_lista`, 8:00) que vence lo vencido y recuerda a los
cinco días. **Un recordatorio y se acabó**: el campo `recordada_en` es lo
que impide que la tarea mande el mismo correo todos los días —al
ejecutivo de un cliente grande, diez correos por un servicio no se leen
como interés—. Y se vence antes de recordar, para no mandarle un
recordatorio a alguien cuyo enlace ya no sirve.

## 46b. El recordatorio llegaba idéntico al primer correo

Lo encontró el dibujo de los correos, no una prueba. El armazón de la
encuesta **ignora el cuerpo del aviso** —a propósito: ahí las estrellas
se pican desde el mensaje y meterlo en el armazón general sería pedir lo
mismo con menos—. Así que el recordatorio que acababa de escribir
llegaba pixel por pixel igual al primero: quien lo recibía no podía
distinguir un segundo intento de un correo repetido, y la fecha de
cierre —que es lo que convierte *ahí luego contesto* en hoy— no aparecía
en ningún lado.

Arreglado con una plantilla propia (`encuesta_recordatorio`) y un solo
párrafo más en el mismo armazón. El enlace sigue siendo uno y el mismo:
dos enlaces vivos para lo mismo es la forma más fácil de que alguien
conteste dos veces. Lo cuida
`test_el_recordatorio_no_llega_identico_al_primero`.

## 47. El menú se agrupó

Once entradas no caben en la barra. Decisión de Salvador, 20 de
septiembre: dos grupos.

- **Operaciones EP** — panorama, eventuales, implantados.
- **Operaciones CI** — central y código: la misma mesa a las 5:40 de la
  mañana.
- **Gestión Administrativa** — gastos, nómina, desempeño y accesos.

De once entradas a cinco: los tres grupos, personal y clientes.

El grupo lleva la línea en el nombre porque vienen más líneas de
operación: el día que llegue la siguiente, el menú ya sabe crecer.

Dos detalles que no se ven pero se sienten. El panel va con
`position: fixed` y se coloca al abrirlo, porque la barra se desplaza de
lado en el celular y cualquier panel absoluto adentro se recorta contra
ese carril justo cuando se necesita. Y **un grupo de uno no es un
grupo**: los roles no ven lo mismo —hay quien alcanza la central y no el
código— y para esa persona el botón escondería una sola pantalla detrás
de un nombre que no es el suyo; se dibuja el enlace tal cual.

De paso quedó arreglado que estando dentro de un servicio el botón
siguiera encendido: `#/servicio/12` no empieza con `#/servicios`.

## 48. Los estatus que nadie escribía

Al revisar la cadena de estatus para la prueba 360 (21 sep) salieron
dos valores del catálogo que ningún proceso escribía.

- **`confirmada`, de la jornada.** Cada asignación guardaba su
  `confirmado`, pero el día se quedaba en `planeada` hasta que alguien
  llegaba al punto. Ahora sube a `confirmada` cuando **toda** su gente
  viva confirmó —desde la app, con una posición de "voy en camino", por
  teléfono con la central o registrada a mano—. Solo hacia adelante,
  como el servicio con `evaluar`: un relevo que entra sin confirmar se
  ve en su renglón, el día no regresa. Un día de implantado que se
  rehace por un cambio del acuerdo sí vuelve a `planeada`: la gente
  nueva no ha confirmado nada.

- **`cotizado`, del servicio.** Decisión de Salvador (21 sep): *«en
  teoría, Odoo nos dará la cotización confirmada; de ahí se levanta el
  servicio»*. El rato entre "se cotizó" y "el cliente autorizó" vive en
  Odoo, así que aquí el servicio nace ya `autorizado` y `cotizado` queda
  **reservado**: en el catálogo, para que un dato viejo no truene, pero
  sin nadie que lo escriba.

Y una regla que ya existía y ahora tiene prueba: **el implantado no
llega a café.** Cerrar un día, abrir el mes que sigue o cerrar el último
día del mes lo deja en curso; `terminado` es del eventual. El implantado
se apaga cancelándolo o cuando finanzas aprueba su cierre.

## 49. La señal, en el teléfono y de color

Decisión de Salvador, 22 de septiembre. La señal con la que el principal
reconoce al equipo ya existía —palabra o imagen, capturada en el
servicio y puesta en el task sheet—, pero se quedaba en el papel. Dos
cosas cambian:

- **La app la levanta.** En la tarjeta del día (hoy y mañana), junto al
  ejecutivo, un botón la abre a pantalla completa: fondo del color o
  blanco, la imagen o la palabra ocupando todo, girado igual, y la
  pantalla no se apaga mientras está abierta. La imagen se baja al
  cargar el día con red y se guarda en el teléfono (`caches`, que el
  trabajador de fondo respeta al cambiar de versión): a la salida del
  filtro no hay barras. Solo la ve quien va en ese servicio; el token
  nunca va en la dirección.

- **Un color como señal, y es la opción recomendada.** Una pantalla de
  un solo color se distingue a veinte metros sin leer nada; con una
  palabra encima si se quiere. La paleta —ocho colores, con el color de
  la letra decidido por color— vive en `app/senal.py` y es la única
  copia: la consola la recibe con la vista previa, la app con la ficha
  del día, y la hoja del principal nombra el color en su idioma («su
  equipo lo espera con la pantalla del teléfono en naranja»). Se
  guarda la **clave**, no el hex: el día que llegue el manual de marca
  con los colores secundarios, se cambian los hex ahí y nada más.
  Propuesta y pantallas en `PROPUESTA_SENAL_COLOR.md`.

## 50. El cierre en dos relojes

Decisión de Salvador, 22 de septiembre (`PROPUESTA_CIERRE_24H.md`).
Primera de tres sesiones: reglas, reloj y pruebas del eventual.

- **T0, el término general.** La hora real de término del último
  día del eventual —o la firma, si la central lo cerró tarde: un
  plazo que nace vencido no es un plazo— o el momento de cancelar.
  En T0 todos los viáticos del servicio reciben el mismo límite,
  T0 + 24 h; cerrar un día intermedio ya no abre plazo. Se respeta
  el del relevado, que corre desde su relevo.
- **T1, el segundo reloj.** Lo pone la tarea `cierre.avanzar` cada
  cinco minutos: al vencer las 24 h del personal —o antes, si todos
  los viáticos ya cerraron, se devolvieron o se cancelaron— el cierre
  y el servicio pasan a **sin visto bueno** y el consultor tiene hasta
  T1 + 24 h; de ahí depende su comisión. Mientras corre la
  comprobación el visto bueno ni se abre: no se le pide al consultor
  cerrar con descuento un dinero que su gente todavía puede comprobar.
- **El visto bueno es el término general.** Al enviar a finanzas el
  servicio pasa a **en facturación** y la factura sale a Odoo en ese
  momento; si Odoo no contesta queda en *por facturar* con el error a
  la vista. Finanzas aprueba, cierra el expediente y detona la
  comisión; *facturado* es el último eslabón, cuando las dos cosas ya
  pasaron. Devolver a operación regresa el servicio a sin visto bueno.
- **Cancelar es un término.** Con dinero afuera o días trabajados,
  cancelar arranca los mismos relojes con T0 = ahora y el consultor
  revisa la cancelación; sin nada que cerrar no hay relojes. El
  servicio se queda *cancelado*; su rastro es el cierre. Un servicio
  terminado ya no se cancela.
- **Reabrir un día** antes del visto bueno deshace el término: el
  cierre se borra con sus plazos y el servicio vuelve a la calle; con
  el visto bueno dado ya no se reabre.
- **Lo ya terminado no se toca**: un cierre nacido antes conserva su
  plazo de siempre. **El implantado no se toca**: sigue día por día
  hasta la sesión del cierre por mes.

Pendiente para las sesiones que siguen: el cierre por mes del
implantado; la consola con la fase y sus relojes, la app con
«por comprobar» sin fecha hasta el término, la bandeja de finanzas,
el panorama, el bono de puntualidad contra el nuevo límite y el
candado de cerrar con descuento antes de que venza el plazo del
personal. *Hecho: el cierre por mes en la sección 56; lo demás, en la
59.*

## 51. El personal, leído de Odoo

Decisión de Salvador, 23 de septiembre: etapa 1 de la conexión con Odoo.
Odoo es el maestro de empleados; Centauro deja de capturar a su gente y
la lee de ahí.

- **Quién entra.** El personal de seguridad: puesto «Personal de
  Seguridad» (con los de GDL) o «Security Driver». Monitoristas,
  oficina y guardias no. La llave es el número interno de Odoo; quien
  ya estaba en Centauro se vincula por su correo la primera vez.
- **Qué manda Odoo.** Nombre, plaza —la ubicación de trabajo; el Estado
  de México va como Ciudad de México—, celular, correo, referencia de
  empleado, fecha de ingreso y foto. En el catálogo ya no se editan: se
  corrigen en Odoo. Un campo vacío en Odoo no borra el de Centauro. Lo
  de la operación —a qué servicio va, con qué rol, sus viáticos— sigue
  siendo de Centauro. Los datos del banco no se leen todavía.
- **La foto** llega como imagen dentro del registro. El círculo con
  iniciales que Odoo le pone a quien no tiene foto no es foto: no se
  guarda y el informe lo cuenta aparte. Se vuelve a pedir solo cuando
  Odoo toca la ficha.
- **Alta**: la persona y su acceso a la app, sin contraseña; entra con
  el código de cuatro dígitos que le dictan. El buscador de esa
  pantalla ya encuentra por número de empleado, completo, y lo muestra
  junto a la foto.
- **Baja**: si Odoo la archiva, en la siguiente lectura deja de estar
  disponible, se le cierra el acceso, la central recibe una alerta
  *dado de baja en Odoo* en cada día que tenía por delante y su
  consultor un aviso al teléfono. Si debe viáticos, el acceso sigue
  abierto solo para comprobarlos y se cierra solo en cuanto no deba
  nada: la regla del panel de accesos.
- **Lo dudoso no se adivina**: sin plaza, plaza que no existe, correo
  con error de dedo o repetido, cambio de puesto, o activo en Odoo y de
  baja en Centauro quedan como *pendientes* y no se tocan.
- **Cómo se lee.** Por la API JSON-2 de Odoo 19, con un cliente que
  solo sabe leer. `GET /odoo/personal/ensayo` dice qué haría sin
  guardar nada; `POST /odoo/personal/sincronizar` lo guarda;
  `sincronizar_personal.py` hace lo mismo desde la terminal, con solo
  cuentas en pantalla. La tarea `odoo.sincronizar_personal` lee cada
  hora, pero no arranca hasta que exista una lectura hecha a mano. Cada
  lectura queda en `sincronizacion_odoo`.
- **La llave** es la del usuario «Centauro (conexión)», no la de una
  persona, y dura tres meses como máximo (`despliegue/LEEME.md`).

De paso: el aviso del visto bueno llevaba al consultor a una dirección
que no existía (`/servicios/…`); ahora abre el servicio en la consola.

Pendiente: la pantalla del ensayo en la consola; después la flotilla,
las cotizaciones y la factura en borrador, en ese orden.

## 52. La flota y el taller, leídos de Odoo

Decisión de Salvador, 23 de septiembre: etapa 2 de la conexión con
Odoo, igual que el personal.

- **Qué entra.** Las unidades con la etiqueta «PROTECCIÓN EJECUTIVA» o
  «pe». Logística, Dirección y las utilitarias no. La llave es el
  número interno de Odoo; la primera vez se vincula por placa.
- **Qué manda Odoo.** Placa, categoría, plaza —la Ubicación; el Estado
  de México va como Ciudad de México—, marca y modelo, color y año. En
  el catálogo ya no se editan. Lo vacío no borra. Implantado o
  eventual, y el costo diario, siguen siendo de Centauro; los autos
  rentados no se tocan.
- **Las categorías** son las siete de Odoo. VAN es la «Van 10 pax» y
  **Sedán** se agrega, con rendimiento y precios de ejemplo como el
  resto del tarifario hasta cargar los reales.
- **La foto** no es la de cada camioneta: es la de su categoría,
  respetando su color. Cada categoría tiene una foto base y una por
  color; la unidad enseña la de su color y, si no hay, la base. Se
  cargan en Centauro (`fotos_de_categoria.py`), que al final dice qué
  colores de la flota todavía no tienen la suya.
- **Baja.** Si Odoo la archiva, deja de ofrecerse y la central recibe
  una alerta *unidad dada de baja en Odoo* en cada día que tenía
  asignado; su consultor, un aviso. Si le quitan la etiqueta, queda
  pendiente y no se da de baja sola.
- **El taller.** Las entradas de Flotilla → Servicios de tipo
  Preventivo, Correctivo o Desgaste natural sacan la unidad de
  circulación de la fecha de entrada a la de salida; sin salida, se da
  por adentro. Lo que Odoo cancela o borra deja de bloquear. Lo que se
  capturó a mano en Centauro no se toca. «Resguardo de Unidad» y los
  de contrato no cuentan.
- **El taller bloquea al eventual.** Hasta hoy solo el implantado lo
  respetaba: al asignar un eventual, una unidad en el taller salía
  libre. Ahora sale ocupada, con el motivo, y no se puede asignar.
- **Cómo se lee.** `GET /odoo/flota/ensayo`, `POST
  /odoo/flota/sincronizar` y `sincronizar_flota.py`; la tarea
  `odoo.sincronizar_flota` cada hora, a los 27 minutos, después de la
  primera lectura a mano.

## 53. El aviso de contacto, sin seguimiento en vivo

Decisión de Salvador, 23 de septiembre: por ahora no se desarrolla el
seguimiento en vivo. Al hacer contacto con el ejecutivo, el solicitante
recibe el aviso de que ya se hizo contacto —«Se hizo contacto con el
ejecutivo a las 10:40»—, sin botón ni enlace. El botón llevaba a una
página que nunca se construyó y el enlace apuntaba fijo a centauro.lat.
El resto de los correos no cambia. El mapeo del botón en `correo.py` se
queda por si algún día se hace el panel.

## 54. El resumen del mes del implantado, solo con sus días

Hallazgo del 23 de septiembre, al revisar la factura del implantado:
el resumen para facturar contaba todas las jornadas del equipo, y el
implantado usa el mismo equipo mes tras mes. En cuanto se abría el mes
que sigue, el resumen de cada mes sumaba los dos: se habría cobrado
doble. El corte del mes sí filtraba, así que los dos papeles dejaban
de cuadrar. No llegó a cobrarse nada: el sistema aún no está en
producción.

Ahora el corte y el resumen salen de la misma lista,
`jornadas_del_mes`. La prueba abre el mes que sigue y revisa que cada
resumen cuente solo sus días y cuadre con el corte.

## 55. Desempeño, en Operaciones EP

Decisión de Salvador, 23 de septiembre: el botón de Desempeño pasa de
Gestión Administrativa a Operaciones EP, junto a Personal. Estaba con
la nómina porque el bono es dinero; lo que mide es cómo trabajó la
gente en la calle, y lo consulta quien decide a quién se manda. Quién
lo ve no cambia.

## 56. El cierre por mes del implantado

Decisión de Salvador, 22 de septiembre (`PROPUESTA_CIERRE_24H.md`,
regla 8), y el camino A del 23 de septiembre. Segunda de las tres
sesiones del cierre en dos relojes. El implantado nunca termina: la
cadena la recorre cada mes de contrato.

- **Un cierre por mes, en la misma tabla.** El cierre y la comisión
  del consultor llevan el mes de contrato (`contrato_id`). El eventual
  sigue con uno por servicio —ahora como índice parcial— y su camino
  no cambia; toda su batería pasa igual.
- **T0 del mes.** El cierre del último día trabajado del mes: la hora
  real de término, o la firma si se cerró tarde. Si el mes acaba en
  fin de semana, el viernes; si se trabaja el sábado adicional, el
  sábado. También arranca si el mes queda completo porque se
  cancelaron sus últimos días, con red en la tarea de cada cinco
  minutos. Sin días trabajados ni dinero que haya salido, no hay
  relojes.
- **Los viáticos del mes** vencen todos en T0 + 24 h; cerrar cada día
  ya no abre plazo. El del relevado corre desde su relevo. Un día sin
  mes de contrato conserva sus 24 h desde que termina.
- **T1 y el visto bueno.** Los mismos relojes: a las 24 h —o antes, si
  todo el dinero del mes cerró— el consultor tiene sus 24 h. La
  revisión del mes compara contra el contrato: días base y adicionales
  trabajados a su precio, la unidad por mes; un día sin cubrir o un
  precio que falta se resuelve antes. El visto bueno manda la factura
  del mes; si Odoo no contesta, el mes queda por facturar.
- **Finanzas aprueba el mes** y se detona la comisión del consultor
  por mes: 1 % sobre lo facturado, sin los viáticos comprobados; se
  pierde fuera de plazo y se retiene con incidencia grave del mes.
- **El estatus del servicio no se mueve.** Cada mes lleva su fase: en
  la cartera (`periodos[].fase`) y en su panel (`cierre`), con
  `/implantados/contratos/{id}/cierre/estado` y `/cierre/revision`.
- **Un día que entra o se reabre después de T0** deshace el término
  del mes; con el visto bueno dado ya no se puede.
- **Cancelar el implantado** cierra con lo trabajado cada mes que
  tenga algo que cerrar, con T0 = el momento de cancelar.
- **La app** esconde la tarjeta de un mes con el cierre de ese mes, no
  con el de otro.

Los viáticos por comprobar todavía no van en la factura del mes —la
del eventual tampoco los lleva—: entran con la factura en Odoo.
Queda para la sesión 3: la consola y la app con la fase y sus relojes.
*Hecho en la sección 59.*

## 57. Los viáticos en la factura, según la cotización

Decisión de Salvador, 23 de septiembre: la cotización dice si los
viáticos van incluidos en el precio o se cobran aparte; son dos
opciones distintas.

- **Eventual.** Si se cobran, la factura suma lo comprobado válido
  —sin notas rechazadas ni lo enviado a descuento— en su propio
  renglón, y el total por facturar lo incluye. Si van incluidos, nada
  aparte.
- **La comisión y la rentabilidad.** Lo facturado ya cuenta los
  viáticos que se cobran. La comisión sigue siendo sobre lo facturado
  descontando los viáticos, así que cuando se cobran aparte deja de
  restar unos que antes ni se facturaban (aprobado por Salvador).
  Con viáticos incluidos, nada cambia.
- **Implantado.** No tiene cotización por día: sus precios viven en
  los términos de cada mes, y ahí va la misma opción
  (`viaticos_incluidos`), incluidos por omisión como en el eventual.
  Pasa sola al mes siguiente. La factura del mes y la comisión del
  mes siguen la misma regla.

La opción todavía no se ve en la consola: llega con las pantallas.
*Sección 59: ya se ve, y «incluidos» quedó como precio alzado —si la
cotización trae monto de gastos, ese monto se factura—.*

## 58. El acceso por correo: la invitación y la recuperación

Decisión de Salvador, 23 de septiembre, después de ver las pantallas:
«dale así, copiar el enlace solo administración».

- **Qué sale y a quién.** Dos correos, desde la dirección de
  `CORREO_DE`: la invitación, cuando se da un acceso (el enlace sirve
  una vez y dura 3 días), y la recuperación, cuando alguien pide
  «¿Olvidaste tu contraseña?» en la entrada (una vez, 2 horas). Solo a
  quien entra a la consola: administración, consultores, central,
  finanzas, recursos humanos y dirección. El personal de seguridad no
  recibe correos de contraseña: sigue con el código de 4 dígitos.
- **Sale al guardar.** No espera la vuelta de cinco minutos: en cuanto
  se confirma el alta o el pedido, ese correo sale en segundo plano. La
  vuelta sigue siendo la red si el proveedor no contesta. Para que dos
  despachadores no manden el mismo aviso, cada uno toma sus renglones
  con `FOR UPDATE SKIP LOCKED`.
- **Un enlace muerto no sale por correo.** Reenviar la invitación, pedir
  otra recuperación o usar el enlace apaga los anteriores, y su correo,
  si no había salido, queda en «vencida». Sin `URL_PUBLICA` el correo de
  acceso no sale —se queda pendiente con el motivo escrito—: llegaría
  sin botón.
- **El enlace vive detrás del «#».** `/#/crear-contrasena/…`: el
  navegador no manda esa parte al servidor, así que el token no queda en
  ninguna bitácora del camino. La página pregunta primero si el enlace
  sirve (`POST /auth/enlace`, con el token en el cuerpo) y dice cuál es
  el caso: vencido, ya usado, reemplazado por uno nuevo o acceso
  cerrado. Se abre en el idioma del país de la persona, y la hora que
  dice el correo también es la de su país.
- **La entrada** trae «¿Olvidaste tu contraseña?». La respuesta es la
  misma exista o no la cuenta; lo único que cambia es si el correo está
  encendido, que no es un dato de nadie.
- **Accesos.** «+ Dar acceso»: la persona (de las que no tienen acceso),
  con qué entra y, si se quiere, su puesto. Y para quien todavía no crea
  su contraseña: cómo va su invitación, «Reenviar la invitación» y
  «Copiar el enlace». **Copiar es solo de administración** —y de
  dirección general, que hereda lo de administración—: con el enlace en
  la mano se le pone la contraseña a otra persona. RRHH da accesos y
  reenvía, pero no ve enlaces, tampoco en las respuestas del alta ni del
  reenvío. Queda escrito quién copió.
- **De paso.** La casilla «Ver también los accesos cerrados» quedó junto
  a su texto. No se da acceso a alguien dado de baja, ni con un correo
  que ya es la llave de otro acceso.

Mientras el correo no esté encendido todo funciona igual y la pantalla
lo dice: el enlace lo entrega administración, copiándolo del renglón.

## 59. El cierre en pantalla: visto bueno, facturación y el dinero del personal

Decisiones de Salvador, 23 de septiembre, después de ver los seis
tableros: «de acuerdo, adelante». Tercera y última sesión del cierre en
dos relojes (secciones 50 y 56).

- **Una sola tarjeta, «Visto bueno y facturación».** La misma en el
  servicio eventual y en el mes del implantado (`cierre.js`). Dice en
  qué fase va —comprobación, visto bueno, facturación, cerrado— y el
  reloj de esa fase diciendo de quién es: el del personal mientras
  comprueba, el del consultor sin visto bueno, y el del regreso cuando
  finanzas lo devuelve. Debajo, lo cotizado contra lo ejecutado con los
  gastos en su propio renglón, lo que hay que corregir antes de mandarlo
  y el dinero del personal. La cartera de servicios y la de implantados
  dicen la fase y cuánto le queda a cada uno (`/cierre/relojes`,
  `periodos[].reloj`).
- **El dinero de una persona es uno solo** (`app/bolson.py`). Lo que se
  le depositó en un servicio —en el implantado, en un mes— se revisa y
  se cierra junto, no día por día: un ticket cargado el lunes cubre lo
  que se le depositó para el martes. Contado por día nunca cuadraba y
  el comparativo inventaba dos desviaciones por un dinero que estaba
  bien. El consultor ve a cada persona con lo depositado, lo comprobado
  y lo que falta; cada ticket con su foto, para validarlo o rechazarlo
  con motivo; y el botón para cerrar su dinero cuando cuadra. Si algo lo
  frena, lo dice en palabras y qué hacer.
- **Cerrar con descuento** (decisión 2): solo cuando ya venció el plazo
  de esa persona —antes todavía puede comprobar— y solo sobre lo que se
  le depositó. Por omisión se le descuenta todo lo que falta; la empresa
  puede absorber una parte, diciendo por qué. Sale un solo ajuste de
  nómina por lo que faltó.
- **Los gastos, con los dos tratos de Salvador.** A **precio alzado**
  el cliente pidió un monto fijo desde la propuesta: la cotización lo
  lleva en sus renglones de gastos y la factura cobra ese monto en su
  propio renglón, se gaste más o menos; lo que sobra es margen y lo que
  se pasa lo absorbe Centauro. Hasta hoy ese monto no llegaba a la
  factura. Sin renglones de gastos, van dentro del precio y no se suma
  nada. Con **gastos netos** se factura lo comprobado válido y el
  cliente recibe el **desglose de gastos** al final, con los
  comprobantes, en su idioma (`/desglose-gastos`). En los dos tratos el
  personal comprueba todo igual: es el control de la casa. La columna
  se sigue llamando `viaticos_incluidos`: verdadero es precio alzado.
- **La comisión no cambia de regla**: sobre lo facturado menos los
  viáticos comprobados. La tarjeta la dice desde el visto bueno —lo que
  va a ser, o que se pierde si salió fuera de plazo—. La ve su consultor
  y la ven finanzas y dirección; otro consultor puede abrir el servicio,
  pero no su comisión: la misma regla que el corte.
- **El implantado: «Términos del mes».** Cómo se cobra, los precios, y
  los gastos del servicio con su monto del mes (`gastos_mes`). Se
  corrigen hasta el visto bueno y pasan solos al mes siguiente.
- **Cuando finanzas lo regresa** (decisiones 1 y 4): tiene que decir
  por qué; el consultor lo lee en su tarjeta y le llega un aviso. Tiene
  24 horas desde el regreso, y lo «en plazo» de su primer visto bueno se
  queda —ni se pierde por la vuelta ni se limpia un «fuera de plazo»—.
  Si la factura ya había salido, se anula, y la del nuevo visto bueno
  lleva el folio de la anulada (`sustituye_a`) para que en Odoo se sepa
  cuál reemplaza. Solo se regresa lo que está en facturación.
- **La pantalla de Facturación** (finanzas y dirección). Por aprobar:
  lo que ya tiene visto bueno, con lo cotizado, lo ejecutado y los
  gastos, para aprobarlo y cerrarlo —ahí nace la comisión— o regresarlo.
  Por facturar: lo que Odoo no aceptó, qué pasó en una palabra —sin
  conexión, rechazada, sin respuesta, falta un dato—, cuántos intentos
  y «Mandar otra vez». Cerrados: lo del mes, con su factura y su
  comisión. Aprobar no espera a la factura.
- **El panorama: el camino al cobro.** Cuántos servicios y meses hay en
  cada fase, cuántos van fuera de plazo, lo que vence primero y lo que
  finanzas regresó. «Afuera sin comprobar» ahora cuenta lo que falta de
  cada persona, aunque no haya subido un solo ticket; antes contaba el
  monto completo y solo de quien ya había subido algo.
- **La app.** Cada servicio en «Mis viáticos» dice cuánto le queda:
  «vence mañana a las 06:52 · te quedan 20 h». Antes del término no hay
  plazo que mostrar.
- **El bono «Comprobar el dinero a tiempo»** (decisión 3): a tiempo es
  haber terminado de comprobar antes del plazo, medido cuando terminó y
  no el día de cada jornada. Cada dinero cuenta en el mes en que cae su
  plazo, y cerrar con descuento no es a tiempo. Lo que sigue en plazo
  todavía no se mide.
- **De paso.** Enviar a finanzas aceptaba la hora por parámetro también
  en producción: ahora solo en desarrollo (`reloj.de_prueba`). Los
  textos que manda el servidor en clave se dicen en el idioma de la
  pantalla, y el revisor ya no amenaza la comisión de un servicio
  regresado: lo que corre es el reloj del regreso.

La migración `f2a9c4e71b36` agrega al cierre el primer visto bueno, el
regreso, los intentos de factura y la factura anulada, y al mes del
implantado su monto de gastos. Los cierres ya enviados toman su envío
como primer visto bueno.

## 60. El GPS de las unidades

Decisiones de Salvador, 23 de septiembre, después de ver los seis
tableros: «adelante con las pantallas». Y a la pregunta de si Centauro
Satelital ya vigila las alertas de la unidad las 24 horas: «alertas, si
las manejan ellos. adelante con lo demas». El GPS es Pegasus Gateway, de
DCT: el que ya trae la flota de Protección Ejecutiva y que opera
Centauro Satelital.

- **Solo se lee.** Centauro no escribe nada en Pegasus. Lee con un
  usuario propio de solo lectura, limitado a los dos grupos de
  Protección Ejecutiva —«2025 P.E.» en México y «CENTAURO BRASIL»—; de
  los demás grupos no guarda ni el nombre. La lectura corre cada dos
  minutos (`gps.leer`) desde el reloj de Celery, como las demás
  vigilancias: ninguna pantalla llama a Pegasus. De cada unidad se
  guarda solo su última lectura —si se mueve, encendido, corriente,
  inhibidor, odómetro y dónde estaba—, que se sobreescribe; recorridos,
  ninguno. El cliente no ve nada (sección 53).
- **La unidad de Odoo y la de Pegasus se ligan solas por la placa**,
  sin espacios ni guiones (`gps_reglas.normal_placa`). La que no liga
  dice por qué y dónde se corrige: sin placa en Pegasus, placa repetida
  en Pegasus, o una placa que ninguna unidad de Odoo trae. Nada se
  captura dos veces.
- **La pantalla «Unidades»**, en Operaciones EP junto a Personal. La
  abren consultores, la central y dirección (`unidades.ver`). Cada
  unidad con su GPS: si reporta y desde cuándo, qué trae hoy —servicio,
  taller o libre— y su odómetro; arriba, lo que hay que arreglar antes
  de que haga falta, empezando por la que no reporta y mañana sale a
  servicio. No dice dónde está ninguna.
- **El pánico de la camioneta suena siempre**, con o sin servicio. Cae
  en el mismo «Atender ahora» que el de la app, con canal «Botón del
  vehículo»: de qué unidad, quién va a bordo con su teléfono, si el
  principal va con ellos y qué dice la unidad en ese momento. Suena una
  sola vez por evento. El de las unidades en servicio se revisa cada
  dos minutos y el de todas, cada quince: los eventos de Pegasus tienen
  una cuota de todo el sitio de Centauro Satelital —800 consultas por
  hora, compartidas con sus operadores y sus clientes— y revisar las
  97 unidades cada dos minutos se llevaba 150. Pegasus puede avisar al
  instante con un disparador (`POST /gps/pegasus/aviso/{secreto}`); el
  aviso no trae nada que se crea —solo adelanta la lectura— y sin
  secreto en el `.env` la ruta no existe.
- **Si Pegasus pide bajar el ritmo** (contesta 429), no se le pide nada
  hasta la hora que diga: seguir pidiendo hace que bloquee la IP. Un
  sitio mal escrito o una clave que no entra se dicen en la pantalla de
  Unidades, en vez de tronar la lectura.
- **El inhibidor y la corriente cortada** (más de dos minutos) suenan
  solo durante el servicio, del camino al punto a la marca de fin, con
  quién va a bordo. Se cierran solos cuando la unidad vuelve a estar
  bien o cuando termina el servicio. **Fuera del servicio los vigila
  Centauro Satelital**, que ya lo hace las 24 horas.
- **El camino al punto** (sección 38). Para quien trae la unidad, lo
  que tiene que llegar al punto es la camioneta. Si viene hacia el
  punto, cuenta como si hubiera contestado: no se le toca el teléfono
  ni se cobra el silencio. Si sigue apagada lejos y ya no le alcanza el
  tiempo, suena «La unidad no ha salido» aunque el teléfono diga que
  va. La unidad sin señal no inventa nada: cuenta el teléfono. La
  central ve los dos testigos, cada uno con lo suyo.
- **El segundo testigo de las marcas.** Cada marca de quien trae la
  unidad guarda dónde estaba la unidad en ese momento, y la bitácora
  lo dice junto a la marca: «unidad a 90 m». En el fin, si la unidad se
  guardó lejos y mucho antes de la marca, lo dice, y cuánto de las
  horas extra cae con la unidad ya guardada. Lo firmado a mano no tiene
  testigo.
- **Los kilómetros del día y el manejo.** Dos horas después del fin
  (`gps.cerrar_dias`, cada hora) se cuentan los km de la unidad —de que
  salió hacia el punto a que se guardó después del fin—, los excesos de
  velocidad y las frenadas o arrancones bruscos. Con esos km, la
  gasolina comprobada se compara contra la misma cuenta del depósito
  —rendimiento de la categoría, precio del litro y holgura—; si pasa,
  se enseña en la tarjeta de la persona.
- **Nada de esto frena.** El testigo de las marcas y la gasolina van a
  «Para revisar»: la unidad señala y el consultor decide. Nunca detienen
  el visto bueno.
- **El manejo entra al desempeño con 10 %**: las estrellas del bono
  bajan de 30 a 25 y las incidencias de 25 a 20. Es de quien maneja,
  cuenta desde 50 km, y resta 3 puntos por cada evento en 1,000 km
  (`puntos_por_evento_manejo`, configurable). Un país con pesos a la
  medida queda con manejo en 0 hasta que se decida.
- **La app le dice al conductor que su unidad tiene GPS**, cuándo se
  mira y para qué: «Durante tu servicio —del camino al punto a tu marca
  de fin— confirma tus marcas y cuenta los kilómetros. Fuera del
  servicio no se mira dónde está; solo cuenta su botón de pánico.»

La migración `b5d8e3a1c7f4` agrega las unidades y los grupos de
Pegasus, los dos tipos de alerta nuevos, la dimensión de manejo con sus
pesos, y a las marcas, al camino y a cada unidad del día lo que dijo el
GPS. Las credenciales viven solo en el `.env` del servidor
(`PEGASUS_SITIO`, `PEGASUS_USUARIO`, `PEGASUS_CLAVE` y, para el
disparador, `PEGASUS_SECRETO_AVISO`); sin ellas no se lee nada y la
pantalla lo dice. Antes de encender la lectura, `backend/ensayo_pegasus.py`
hace una vez lo mismo que ella con el usuario del `.env` y dice solo
cuántos: unidades, placas, eventos y tramos, sin nombres, placas ni
coordenadas.

## 14. Lo que falta

### Abierto

*Al 18 de septiembre. Lo que se cerró —el panel de accesos, las
contraseñas, los puestos configurables, las 43 puertas mudadas a
actividades y la bitácora de catálogos— salió de aquí; si algo de eso se
busca, está en las secciones 15 y 16.*

- **Odoo: dos datos para cuando se conecte la facturación** (sección 59).
  El acuerdo autorizado que manda Odoo (`ODOO_LO_QUE_NECESITAMOS.md`,
  5b) solo trae renglones de recurso y vehículo; a precio alzado tiene
  que traer también el monto fijo de gastos, como renglón `viaticos`:
  sin él, ese servicio se factura sin sus gastos. Y la factura que sale
  después de un regreso lleva `sustituye_a` con el folio de la anulada:
  Centauro la da por anulada, pero en Odoo alguien tiene que cancelarla
  —quien reciba las facturas, o finanzas a mano—. Hoy no muerde: sin
  conexión no sale ninguna factura.
- **El GPS: lo que le toca a Centauro Satelital** (sección 60). Las 14
  unidades de Brasil que no traen placa en Pegasus —48126, 48127,
  48129, 55122, 57564 a 57566 y 57597 a 57603— no se ligan hasta que
  la capturen. Y cuando el servidor tenga su dirección con HTTPS, el
  disparador de pánico en Pegasus hacia `/gps/pegasus/aviso/{secreto}`;
  mientras tanto el pánico llega con la lectura de cada dos minutos. De
  este lado, las placas ligan contra la flota leída de Odoo: sin ella,
  ninguna.
- **El correo: falta el proveedor y el dominio.** El despachador ya
  existe (sección 29): SMTP, apagado por omisión, con reintentos y con
  el error del proveedor escrito al lado. Lo que falta es **tuyo**: a qué
  servidor SMTP, con qué credenciales, desde qué dirección y bajo qué
  dominio cuelgan los enlaces. Son cinco renglones del `.env`
  —`CORREO_HOST`, `CORREO_PUERTO`, `CORREO_USUARIO`, `CORREO_CLAVE`,
  `CORREO_DE`— más `URL_PUBLICA`. La invitación y la recuperación de
  contraseña ya salen por él (sección 58): con esos renglones puestos,
  llegan solas.

  *(Lo de abajo es el texto de cuando no existía el envío, que explica
  por qué la tabla es como es.)*

- ~~**Mandar un correo de verdad.**~~ La traba de diseño ya se quitó
  (sección 19): `Notificacion.servicio_id` admite nulo y existe el
  destinatario `colaborador`, así que la tabla ya acepta una invitación
  de acceso o un enlace de recuperación. **Lo que no existe es el envío.**
  El modelo lo dice desde el primer día —"en el demo se registra; el
  envío real se conecta después"— y sigue siendo cierto: nada sale.

  Falta decidir **con qué proveedor se manda y desde qué dominio**, que
  es decisión de Salvador, y después conectar el despachador. Mientras
  tanto el enlace de recuperación lo entrega administración a mano desde
  el panel, y el código de campo lo dicta el consultor —ese último por
  diseño, no por falta: lo que protege ese camino es que quien entrega el
  código reconozca la voz de quien llama.
- ~~**La baja en Odoo no cierra el acceso.**~~ **Cerrado el 23 de
  septiembre**, sección 51: Centauro lee el personal de Odoo y la baja
  llega sola. *(Lo de abajo es el texto de entonces.)*
  `odoo.sincronizar_personal`
  actualiza solo nombre, teléfono y foto; `activo` no está en la lista y
  `_sincronizar` nunca da de baja a nadie. Recursos humanos da de baja a
  alguien en Odoo —que es la fuente de verdad de empleados— y en Centauro
  su cuenta sigue viva. **Pendiente con quien lleva Odoo:** si puede
  mandar el estado de cada empleado. El panel ya levanta la ceja cuando
  una persona está de baja y su acceso sigue abierto; lo que falta es que
  la baja llegue sola.
- ~~**La app de campo está entera en español.**~~ **Cerrado el 19 de
  septiembre**, sección 23. Sale del país de su plaza, sin selector. La
  exclusión del barrido se borró y la app quedó cubierta como la consola.

- ~~**El resto de los `?` y el candado de cobertura.**~~ **Cerrado el 19
  de septiembre**, sección 22. Son **40 signos en nueve pantallas** y el
  padrón está encendido: cada archivo de la consola declara cuántos
  lleva, y el cero cuenta como respuesta.

- ~~**La ayuda en pantalla: la capa 3.**~~ **Cerrada el 20 de
  septiembre**, sección 28. Lo que sigue es el texto original del
  pedido, que explica de dónde salieron las tres capas.

- **~~La ayuda en pantalla~~ (el pedido original).** Pedido por Salvador (18 sep): que cada punto
  diga para qué sirve, cuál es su alcance y por qué importa, a un clic.

  **La mitad ya está escrita.** Hay **93 claves `_pie`** en español —279
  renglones con sus traducciones— que ya salen debajo de cada título de
  bloque, más las descripciones de `permisos.py`, escritas a propósito
  pensando en quien las va a leer. El trabajo no es escribir un manual:
  es cosechar lo que hay y hacerlo alcanzable.

  **La regla que define el diseño:** un tutorial que vive aparte de la
  pantalla se despega el día que la pantalla cambia. Es la misma lección
  del umbral de silencio —60 en una pantalla y 120 en la otra— y del
  tope del mes escrito lejos de su candado. La ayuda vive donde vive la
  cosa que explica, en `idioma.js`, con las demás claves, para que
  `revisar.py` la barra igual.

  Tres capas, de la más barata a la más cara:

  1. **El pie que ya existe**, revisado con ojo de quien nunca usó el
     sistema. Algunos dicen *qué* es y no *para qué* sirve.
  2. **Un `?` por bloque**, junto al título. Tres cosas: para qué sirve,
     qué pasa si no lo haces, y de dónde sale el número.
  3. **El recorrido de la primera vez**, solo para el que entra nuevo y
     solo una vez, repetible desde el `?`.

  **Las capas 1 y 2 están hechas** (sección 22). Lo que queda abierto de
  este punto es la 3.

  **Lo que lo haría valioso de verdad:** este código está lleno de *por
  qué*, no de *qué* —"el dinero que ya salió no se mueve con la
  persona", "quien no marca su llegada no se paga"—. Eso es lo que hace
  que un consultor confíe en el sistema en vez de pelearse con él.
  Cuando el sistema le dice que no, la diferencia entre obedecer a
  regañadientes y entender está en una frase.

  **El personal de campo necesita otra cosa:** están en un teléfono, a
  las seis de la mañana, con una mano. Ahí no cabe un recorrido; ahí
  sirve que cada pantalla diga en un renglón qué se espera de ellos
  ahora.
- ~~**El código de vestimenta del equipo.**~~ **Cerrado el 20 de
  septiembre**, sección 40. *(Lo de abajo es el texto del pedido.)*
  Pedido por Salvador (20 sep): al dar de alta el servicio, el consultor
  elige **casual, semiformal o formal**, y eso se ve en la app de campo
  y en el task sheet. **Solo para eventuales**: el implantado tiene su
  propio acuerdo con el cliente y no se pregunta cada mes.
- ~~**Avisar al cliente del reemplazo de personal o de unidad.**~~
  **Cerrado el 20 de septiembre**, sección 39: si el servicio está en
  curso o es de hoy, el correo sale al guardar el relevo; si es de otro
  día, el cambio viaja en el task sheet.
- Restringir la llave de Google por IP del servidor.
- Cargar los montos reales: tarifas, comisiones de los cuatro roles y
  tabuladores de viáticos por acuerdo.
- HTTPS para probar la app en un teléfono real.
- **Generar las llaves de push.** `.env` todavía no tiene `VAPID_PUBLIC`
  ni `VAPID_PRIVATE`, así que los avisos al teléfono no salen:
  `docker compose exec -T api python generar_llaves_push.py`.
- **El servidor de producción.** Ver `ARQUITECTURA.md` y
  `despliegue/LEEME.md`. Las tres cosas que frenaban el encendido ya
  quedaron: `docker-compose.prod.yml` solo asoma a internet el proxy con
  su certificado, lee la contraseña del `.env` y no corre con
  `--reload`; el pozo de conexiones de SQLAlchemy ya alcanza al de hilos
  de FastAPI (`app/db.py`); y el respaldo se restaura y se cuenta
  (sección 37). Lo que falta es encenderlo: el 23 de septiembre se está
  desplegando en OVH, en centauro.cc.
- ~~**El implantado de Brasil: dos personas rotando los 7 días.**~~
  **Cerrado el 20 de septiembre**, sección 27. Se construyó como un tipo
  de implantado aparte —12 × 36— y el de 12 horas naturales no se tocó.

- **La moneda.** Ver `PROPUESTA_MONEDA.md`. Decisión de Salvador
  (18 sep): **la rentabilidad se deja para el final**, es la cereza del
  pastel. Pero el defecto queda escrito aquí para que no se pierda:

  En `cierre.rentabilidad()`, `utilidad = facturacion - costo_total`
  resta la moneda del tarifario menos la moneda local. Los costos
  —comisiones, viáticos, unidad— **siempre** son locales; el tarifario
  tiene su propia moneda. Un servicio en México cotizado en 5,000 USD
  con 80,000 MXN de costo diría margen **−1,500%**, rotulado con la
  moneda de la cotización, o sea con cara de número normal.

  Hoy no muerde porque no hay tarifarios en dólares cargados. **El día
  que se cargue uno, muerde en silencio.**

  Se propuso adelantar un candado —no autorizar una cotización en moneda
  distinta a la local sin tipo de cambio, pocas líneas, sin depender de
  ninguna decisión pendiente— y **Salvador decidió que también espere**.
  Va todo junto al final. No adelantarlo por iniciativa propia.

  El aviso práctico mientras tanto: **mientras no exista el candado, no
  cargar tarifarios en otra moneda.** Es lo único que dispara el
  problema.

  Lo que sí quedó cerrado, y acota el problema: **el costo nunca
  necesita conversión.** Los viáticos se crean en cinco lugares y los
  cinco toman `servicio.pais_id → pais.moneda_local`; el país del
  servicio se captura en el alta y ningún endpoint lo reasigna; la
  nómina se calcula por país. El tipo de cambio solo toca el precio.

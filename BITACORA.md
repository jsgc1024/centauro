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

## 10. Lo que falta

### Abierto

- Las dos fallas de seguridad de `REVISION.md`: el sembrado sin
  autenticación y la `secret_key` pública en `config.py`.
- Restringir la llave de Google por IP del servidor.
- Cargar los montos reales: tarifas, comisiones de los cuatro roles y
  tabuladores de viáticos por acuerdo.
- HTTPS para probar la app en un teléfono real.
- Traducir `servicio.js` y `finanzas.js`.
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
- **La moneda.** `Cotizacion.tipo_cambio` existe y no se lee en ninguna
  parte. Hoy no duele porque todo está en pesos; el día que entre un
  tarifario en dólares, la utilidad y la comisión salen sin sentido.

# El archivo de los comprobantes y el historial de lo facturado — propuesta

_Qué pasa con las fotos de los comprobantes cuando el servicio ya se cobró, y dónde queda la memoria de lo que se hizo._
_Antes de programar nada. 25 de septiembre de 2026._

---

## Lo que pidió Salvador

1. Que **tres meses después de que un servicio se facture**, salgan de
   Centauro las fotos de los comprobantes de viáticos que subió el
   personal de seguridad.
2. Que esas fotos **se puedan seguir viendo** cuando haga falta.
3. Que Centauro guarde **el historial de todos los servicios facturados**:
   lo que se ejecutó.

---

## Lo que hay hoy

- **La foto del ticket vive dentro de la base de datos**, en el mismo
  renglón del comprobante (`comprobante.imagen`). El teléfono la reduce
  antes de subirla —1600 píxeles del lado largo, JPEG al 70 %— y queda en
  unos 300 KB; guardada como texto dentro de la base pesa cerca de
  400 KB. Lo mismo la foto de la devolución (`devolucion_viatico.comprobante`).
- **Nada la saca nunca de ahí.** Mil tickets son unos 400 MB más en la
  base y en cada respaldo, todas las noches, para siempre. La base crece
  con cada ticket y el respaldo tarda cada vez más.
- **Del servicio cerrado sí queda todo** —el cierre, los montos, quién
  aprobó, la factura—, **pero no hay dónde verlo**: la pestaña
  *Cerrados* de Facturación enseña solo el mes en curso.

---

## La idea en una línea

**La foto se muda; el registro se queda.**

A los tres meses de la factura, cada foto sube a un archivo de Google, se
comprueba que llegó completa y solo entonces sale de Centauro. Todo lo
demás del comprobante —monto, concepto, quién lo subió, cuándo, si se
validó— se queda en Centauro para siempre, y la foto se trae del archivo
cuando alguien con permiso la pide.

---

## El reloj

**Arranca con la factura.** Tres meses de calendario: factura del 10 de
diciembre, archivo la noche del 10 de marzo.

**Mientras Odoo no esté conectado, arranca con la aprobación de
finanzas.** La factura la hace Odoo y Centauro todavía no está conectado
a Odoo, así que la fecha que sí tiene es cuando finanzas aprueba el
cierre. El historial lo dice en el renglón: *Sin Odoo: cuenta desde la
aprobación*. El día que Odoo se conecte, lo nuevo cuenta desde su
factura; lo que ya contó desde la aprobación se queda como está.

**En el implantado, cada mes lleva su propio reloj.** Cada mes tiene su
cierre y su factura: las fotos de noviembre se archivan tres meses
después de la factura de noviembre, aunque el contrato siga corriendo.

**Lo que no ha cerrado no se toca.** Un servicio sin aprobación ni
factura no tiene reloj, y sus fotos se quedan. Tampoco se archiva una
devolución que finanzas todavía no confirma: es dinero que no se ha
visto entrar, y su foto es justo lo que se está revisando.

---

## Qué sale y qué se queda

| | Hoy | A los tres meses de la factura |
|---|---|---|
| La foto del ticket y la de la devolución | En la base de Centauro | En el archivo de Google, 6 años |
| Monto, concepto, tipo, fecha, quién la subió | En Centauro | En Centauro, para siempre |
| Validado o rechazado, y el motivo | En Centauro | En Centauro, para siempre |
| Servicio, cierre, factura, quién aprobó | En Centauro | En Centauro, para siempre |
| Dónde quedó la foto y su huella | — | En Centauro, para siempre |

**La huella** es un código que se saca de la foto y que cambia si a la
foto se le mueve un solo punto. Centauro la guarda el día que archiva, y
con ella comprueba después que lo que regresa del archivo es exactamente
lo que se subió.

**Solo esas dos fotos.** Las demás imágenes se quedan como hoy: el
comprobante del depósito y el de las compras especiales, que sube
finanzas; el del pago del bono; la señal de identificación; y las fotos
y la firma de la revisión de la unidad.

---

## El archivo

- **Un depósito de Google solo para esto**, aparte del de los
  respaldos y, como aquél, fuera de la región del servidor.
- **Clase Archive**: la más barata de Google, pensada para lo que casi
  nunca se abre. A diferencia del "archivo en frío" de otros
  proveedores, la foto se ve **al momento**, no en horas.
- **Nadie la puede borrar antes de tiempo.** La cuenta del servidor
  puede guardar y leer, pero no borrar ni escribir encima: ni un error
  del programa ni alguien que se metiera al servidor podría tocar lo
  archivado. Encima va el candado de retención de Google.
- **Se borra sola al cumplir su plazo.** A los 6 años Google la elimina,
  sin que nadie tenga que acordarse.
- **Nada es público.** No hay enlaces: la foto solo sale a través de
  Centauro, y solo a quien tiene el permiso.

### ¿Por qué 6 años y no 5?

El Código Fiscal (artículo 30) pide conservar la documentación **cinco
años contados desde la declaración con la que se relaciona**, no desde el
ticket. Un ticket de enero de 2026 va en la declaración anual de 2026,
que se presenta hasta marzo de 2027: hay que guardarlo hasta marzo de
2032. Contando 5 años desde que se archiva (abril de 2026), se acabaría
en abril de 2031, un año antes. **Con 6 años desde que se archiva, el
plazo se cubre siempre.**

Que lo confirme el contador; es un número que se cambia. El candado de
Google se deja **sin sellar** hasta esa confirmación: sellado, ya nadie
lo puede acortar, ni nosotros.

---

## Quién ve qué

- **Los tres meses que la foto sigue en Centauro**: igual que hoy. La
  ven quienes revisan viáticos —consultor, dirección de operaciones,
  finanzas y central— y cada agente la suya en su app.
- **Ya archivada**: el renglón dice *Archivada el …* y trae el botón
  **Ver del archivo**, que abren **dirección general y finanzas**. Es una
  actividad con nombre, como las demás: desde Accesos se le puede dar a
  alguien más. (Administración pasa siempre, como en todo el sistema.)
- **Cada vez que alguien trae una foto del archivo queda en la bitácora
  del servicio**: quién, cuándo y cuál. Y Centauro compara la huella de
  lo que llegó con la que guardó: si no coincide, lo dice en rojo en vez
  de enseñarla como buena.
- **El historial** lo ven los mismos que hoy ven Facturación: finanzas,
  dirección de operaciones y dirección general.
- **El personal no nota nada**: su app no enseña las fotos de sus
  comprobantes. Si alguien necesita una ya archivada, se la da finanzas.

---

## Las pantallas

Cuatro maquetas hechas con el estilo real de la consola, en
`Claude outputs/`. Lo nuevo va resaltado en amarillo, con la marca
**NUEVO**.

### 1. Facturación → Historial — `archivo_1_historial.png`

Una pestaña nueva junto a las tres de hoy. *Cerrados* pasa a llamarse
*Cerrados del mes*, para que no se confunda con ésta.

- **Filtros**: desde y hasta (por mes), cliente, consultor, tipo
  —eventual o implantado— y folio.
- **Arriba, lo que suma el filtro**: cuántos servicios, cuánto se
  facturó, cuánto se comprobó de viáticos, y cuántas fotos siguen en
  Centauro y cuántas ya están archivadas.
- **Un renglón por servicio** —por mes, en el implantado—: folio,
  cliente, fechas, consultor, la factura y su fecha (o *Aprobado · sin
  factura* y desde cuándo cuenta), el total, los viáticos, y qué pasa con
  sus fotos: *11 fotos · se archivan el 10/03/2027*, o *Archivadas el
  14/01/2027*.
- **Descargar Excel** baja exactamente lo filtrado, en dos hojas:
  *Servicios*, un renglón por servicio como en la pantalla, y
  *Comprobantes*, un renglón por comprobante —servicio, persona,
  concepto, tipo, monto, fecha, si se validó, y si su foto está en
  Centauro o en el archivo—. Las fotos no van en el Excel.
- **Desde el primer servicio cerrado.** Nada desaparece de la vista al
  cambiar de mes.

En la maqueta conviven a propósito los dos casos —servicios con su
factura y uno aprobado sin factura— para que se vean los dos.

### 2. El detalle, mientras las fotos siguen en Centauro — `archivo_2_detalle.png`

Clic en un servicio del historial. Arriba, la factura, el total, los
viáticos comprobados contra lo entregado, y lo devuelto. Luego un aviso
con la fecha exacta en que sus fotos se archivan, y los comprobantes de
cada persona como ya se ven hoy en el cierre, con su miniatura.

### 3. El mismo detalle, ya archivado — `archivo_3_archivado.png`

La miniatura queda en gris y cada renglón dice *Archivada el 10/03/2027*,
con **Ver del archivo**. Todo lo demás sigue igual: el monto, el
concepto, la fecha, *Validado*, *Confirmada por finanzas*.

### 4. Ver del archivo — `archivo_4_ver_del_archivo.png`

La foto llega al momento, con quién la subió y cuándo. Abajo, quién la
trajo del archivo y a qué hora —eso queda en la bitácora—, y la
comprobación de que es la misma foto que se subió. Se puede descargar.

---

## Cómo se ve en el tiempo

Con el servicio de las maquetas, CEN-2026-0612:

| Cuándo | Qué pasa |
|---|---|
| 4 dic 2026, 14:54 | Juan Ramírez sube desde su app la foto del ticket de gasolina. |
| 10 dic 2026 | Sale la factura F-01245. El historial ya dice *se archivan el 10/03/2027*. |
| 10 dic – 10 mar | Todo igual que hoy: la foto se ve y se revisa en Centauro. |
| 10 mar 2027, 1:30 | La foto sube al archivo, se comprueba que llegó completa y sale de la base. El respaldo de las 2:30 ya no la trae. |
| 14 mar 2027 | Salvador la abre con *Ver del archivo*. Queda en la bitácora. |
| 8 jun 2027 | Se borra solo el último respaldo que todavía la traía (a los 90 días). Desde ahí, la foto solo existe en el archivo. |
| 10 mar 2033 | Seis años después de archivada, Google la borra sola. |

---

## Cada noche

1. **A la 1:30 de la mañana** —antes del respaldo de las 2:30— Centauro
   busca las fotos que ya cumplieron sus tres meses.
2. **Sube cada una sin escribir encima de nada** y le pregunta a Google
   qué recibió: tamaño y huella. **Solo si cuadran** con lo que tiene,
   quita la foto de la base y anota dónde quedó, su huella y la fecha.
3. **Si algo falla, la foto se queda en Centauro** y se vuelve a
   intentar la noche siguiente. Si la foto sí llegó pero Centauro no
   alcanzó a anotarlo, a la noche siguiente Google dice que ya la tiene,
   Centauro compara la huella y termina la mudanza. **Nunca hay un
   momento en que la foto no esté en ningún lado.**
4. **Un tope de 3,000 fotos por noche** (cerca de 1 GB), para que la
   primera vez —cuando haya meses acumulados— se reparta en varias
   noches.
5. **Si una noche falla, te llega el correo**, a tus dos direcciones,
   igual que con el respaldo.

**Nace apagado.** Mientras en el `.env` del servidor no esté la línea
con el nombre del archivo, no sale ninguna foto de Centauro. El historial
funciona desde el primer día y ya dice qué fotos se irían y cuándo. Se
prende cuando tú lo digas, después de verlo.

---

## Lo que cuesta

- **Guardar:** la clase Archive cuesta entre **US$0.0012 y US$0.003 por
  GB al mes**, según viva en una región o en varias. Aunque fueran 2,000
  fotos al mes, a los seis años serían unos 45 GB: **menos de 15
  centavos de dólar al mes**.
- **Subir:** a lo más US$0.10 por cada mil fotos, más dos centavos de
  dólar por GB que cruza de región.
- **Ver una foto:** menos de una centésima de centavo de dólar.
- **En total, menos de 10 pesos al mes**, aun con esas 2,000 fotos al
  mes. El aviso de gasto de 2,000 pesos ni lo nota.
- **Y ahorra:** la base deja de crecer con cada ticket, y el respaldo de
  cada noche sale más chico y más rápido.

---

## Lo que no cambia

- **Nada del servicio se borra**: servicio, cierre, montos, comprobantes,
  devoluciones y bitácora se quedan en Centauro.
- **Los tres meses después de la factura** todo se ve y se revisa
  exactamente como hoy.
- **Las demás imágenes** se quedan donde están.
- **Por aprobar** y **Por facturar** siguen igual; *Cerrados* solo cambia
  de nombre.

---

## Las decisiones

**Ya tomadas, el 25 de septiembre:**

1. El reloj arranca con la factura; mientras Odoo no esté conectado, con
   la aprobación de finanzas.
2. Las fotos se archivan fuera, no se tiran: en un archivo de Google del
   que solo dirección general y finanzas las pueden sacar.
3. Las fotos de las devoluciones van junto con las de los tickets.
4. Historial con filtros y Excel.

**Las que agrega esta propuesta y necesitan el visto bueno de Salvador:**

5. **6 años en el archivo, no 5**, por cómo cuenta el plazo el Código
   Fiscal. El contador lo confirma y con eso se sella el candado.
6. **Nace apagado** y se prende cuando Salvador diga.
7. **Tope de 3,000 fotos por noche.**
8. **Una devolución sin confirmar no se archiva** hasta que finanzas la
   resuelva.
9. **El Excel trae dos hojas**: servicios y comprobantes.

---

## Qué hay que construir

**Base de datos.** Cuatro columnas en `comprobante` y en
`devolucion_viatico`: `archivado_en`, `archivo_objeto`, `archivo_md5` y
`archivo_bytes`. La migración solo agrega columnas vacías: no mueve
ninguna foto.

**Motor.** `archivo.py`: qué fotos ya cumplieron sus tres meses —el
eventual por servicio, el implantado por mes—, subirlas, comprobar
tamaño y huella, quitarlas de la base y anotar. Reusa lo de
`subir_a_google.py`: el permiso de la máquina, sin llaves, y el nunca
escribir encima.

**Tarea nocturna.** En `celery_app.py`, a la 1:30. Con `ARCHIVO_DESTINO`
vacío en el `.env`, no hace nada.

**API.** El historial con sus filtros; el Excel, que se arma sin
librerías nuevas; *Ver del archivo* con su actividad, su renglón en la
bitácora y la comparación de la huella.

**Consola.** La pestaña Historial, el detalle del servicio, el renglón
archivado y el visor.

**Idiomas.** Las claves nuevas en es, en y pt.

**Google.** Un script para Cloud Shell, como el de las alertas: crea el
depósito del archivo —clase Archive, candado de 6 años sin sellar,
borrado a los 6 años, sin acceso público—, le da a la cuenta de la
máquina guardar y leer, no borrar, y agrega la alerta *Centauro: falló
el archivo* a los dos correos.

**Pruebas.** Que el reloj cuente desde la factura, desde la aprobación
sin Odoo, y por mes en el implantado; que sin cierre, o con una
devolución pendiente, no se toque nada; que si la subida o la
comprobación fallan la foto se quede; que nunca se escriba encima de
otra; que una mudanza a medias se termine la noche siguiente; que *Ver
del archivo* respete el permiso, deje su renglón en la bitácora y avise
si la huella no coincide; y que el Excel sume lo mismo que la pantalla.
Contra un Google de mentiras, como las del respaldo.

**Documentación.** La guía de despliegue —el archivo y cómo se prende—,
ARQUITECTURA y su sección en la bitácora.

---

## Lo que queda pendiente

- **El contador**: confirmar el plazo. Con eso se sella el candado.
- **Los respaldos** traen cada foto 90 días más después de archivada;
  después, solo existe en el archivo.
- **El archivo vive en la misma cuenta de Google que el servidor.** Eso
  hace más importante el pendiente del segundo dueño de confianza en
  Google Cloud: si esa cuenta se pierde, con ella se va el archivo.
- **Odoo**: cuando se conecte, el reloj pasa solo a la factura.

---

_Precios de Google consultados el 25 de septiembre de 2026 en
cloud.google.com/storage/pricing. Plazo de conservación: Código Fiscal
de la Federación, artículo 30._

_Aprobada por Salvador el 25 de septiembre de 2026, tal cual, con las
cinco decisiones que agregaba. Lo que se construyó está en la sección 69
de la bitácora._

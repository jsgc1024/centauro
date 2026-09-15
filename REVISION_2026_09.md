# Revisión profunda — septiembre 2026

Tres vueltas al sistema completo. La primera buscó problemas, la segunda
revisó los arreglos de la primera, y la tercera predijo qué pruebas se
romperían antes de correrlas.

Esto es el registro de qué se encontró, qué se arregló y qué quedó
abierto. Sirve para dos cosas: para no volver a buscar lo mismo, y para
que cuando algo falle dentro de seis meses se pueda saber si ya lo
habíamos visto.

---

## Lo que se encontró, por gravedad

### Seguridad

| # | Qué | Estado |
|---|---|---|
| 1 | `POST /sistema/sembrar-catalogos` abierto sin contraseña, reescribía rol y contraseña de **todos** los usuarios y devolvía la contraseña en la respuesta. Dos peticiones y cualquiera era director general | **Cerrado** |
| 2 | `secret_key` de demo en el código. Con ella se firma cualquier sesión | **Cerrado** fuera de local |
| 3 | La **agenda del ejecutivo** —a qué hora y en qué dirección va a estar— abierta a cualquier sesión. Recorriendo números salía el itinerario de todos los protegidos | **Cerrado** |
| 4 | Los **viáticos de cualquier persona** abiertos a cualquier sesión: cuánto efectivo trae encima cada quien y a quién le descontaron | **Cerrado** |
| 5 | Las **fotos de las revisiones de unidad** abiertas a cualquier sesión | **Cerrado** |
| 6 | El **catálogo completo** —plantilla con teléfonos, tarifario al cliente, tabla de comisiones, flota blindada con placas— abierto a cualquier sesión, la de un elemento de campo incluida | **Cerrado** (en dos pasos: el CRUD y las cuatro rutas escritas a mano que lo ensombrecían) |
| 7 | El **botón de pánico falsificable**: se podía levantar una alerta a nombre de otro elemento, en un servicio ajeno, con coordenadas inventadas. Un pánico mueve equipo de respuesta | **Cerrado** (las dos puertas: jornada y servicio) |

**Lo que se revisó y estaba bien:** no hay una sola inyección SQL —ningún
`text()` con f-string en toda la aplicación—, nada de `eval`, `exec` ni
`subprocess`; la entrada de usuario nunca llega a un nombre de archivo;
el service worker cachea solo el armazón y jamás los datos; el token JWT
nunca viaja en la URL, ni siquiera en las imágenes; no hay CORS con
comodín; el HTML generado escapa en cada interpolación.

### El dinero

| # | Qué | Cuánto costaba | Estado |
|---|---|---|---|
| 1 | **La misma diferencia se arrastraba cada corrida.** Pagado 800, corresponde 1100 → ajuste +300. Se paga. La siguiente revisión vuelve a ver 800 contra 1100 y genera otros +300. Cada vez que el servicio se movía, 300 más | Sin tope | **Cerrado** |
| 2 | **Un descuento de viáticos tapaba la corrección del mismo día.** Los dos tipos de ajuste compartían la llave (jornada, persona) | Lo que se le debía a alguien, en silencio | **Cerrado** |
| 3 | **Un mismo ajuste se podía pagar en dos cortes** | El ajuste, doble | **Cerrado** |
| 4 | **Una jornada atrapada en un borrador no volvía a ningún corte**, y no había forma de tirar un borrador | El día completo de alguien | **Cerrado** |
| 5 | **Comprobar no tenía tope ni signo.** Quien recibió 8,000 y no gastó nada subía un "comprobante" de 8,000 y el descuento dejaba de ser posible. Y lo comprobado es lo que se le factura al cliente | Los viáticos completos, y de paso se le cobra al cliente | **Cerrado** |
| 6 | **Devolver no validaba nada**: acumulaba sin tope, aceptaba negativos. Dos veces el mismo POST y la persona salía del tablero de dinero en la calle | Se pierde de vista el efectivo | **Cerrado** |
| 7 | **El mismo ticket dos veces.** Un doble toque con mala señal —la situación normal en una gasolinera | El gasto, doble, facturado al cliente | **Cerrado** (ventana de 3 minutos, no para siempre) |
| 8 | **Floats en la pantalla de dinero de la app.** Viáticos que cuadraban al centavo mostraban saldo pendiente de 0.0000000000018 | Confianza | **Cerrado** |

**Lo que se revisó y estaba bien:** el rol sale de la tarea en todos
lados —`persona.perfil_id` no aparece en ninguna línea del código—; una
tarifa faltante frena el corte entero y dice a quién dejaría sin pagar,
en vez de omitirlo en silencio; el candado contra pagar dos veces la
misma jornada funciona; el reparto de viáticos del implantado cuadra al
peso; los bonos están todos en Decimal y no dejan dinero colgado.

### Datos y borrado

| # | Qué | Estado |
|---|---|---|
| 1 | Borrar un equipo **se llevaba compras ya pagadas** —un vuelo con su monto real y su número de reserva— sin dejar rastro | **Cerrado** |
| 2 | Borrar un servicio ya cotizado **reventaba con un 500**: cotización, cierre, contrato del implantado y comisión del consultor no se limpiaban | **Cerrado** |
| 3 | **Un implantado recién capturado no se podía borrar nunca**, y el mensaje decía algo falso | **Cerrado** |

### El código nuevo (la app, el cierre a mano, la revisión de unidad)

| # | Qué | Estado |
|---|---|---|
| 1 | `reabrir` borraba la firma del cierre pero **dejaba la hora inventada**, que después se leía igual que una marcada desde la calle | **Cerrado** |
| 2 | `reabrir` dejaba el día **EN_CURSO**: un día reabierto de hace tres semanas subía a la banda roja de la central con "sin reporte hace 512 horas" | **Cerrado** (queda PLANEADA) |
| 3 | La revisión de unidad **no validaba kilometraje ni combustible**: la consola llegaba a mostrar "-100,000 km recorridos" | **Cerrado** |
| 4 | **La firma era obligatoria solo en la pantalla.** Media promesa vivía en el JavaScript del teléfono | **Cerrado** |
| 5 | Las fotos **sin tope de tamaño** | **Cerrado** |
| 6 | `mi-calificación` leía `calificacion` y el backend manda `valor`: **todas las dimensiones salían con un guion, siempre, para todos** | **Cerrado** |
| 7 | `olvidar("mi-dia")` **borraba toda la memoria sin conexión**: el agente registraba la unidad en un estacionamiento y ahí perdía la copia de su día, sus viáticos y sus pagos, justo antes de bajar al sótano | **Cerrado** |
| 8 | El "‹ Volver" del formulario de revisión **no hacía nada** | **Cerrado** |
| 9 | Todos los `que_hacer` del backend **se tiraban a la basura** en la app: el agente veía el problema y nunca la salida | **Cerrado** |
| 10 | La ficha del servicio **bajaba todas las fotos en base64 en cada render**, y esa pantalla se recarga sola en casi cada acción | **Cerrado** (bajo demanda) |
| 11 | Si fallaba el registro de push, la app decía **"Encendidos"** para siempre y no había forma de reintentar | **Cerrado** |
| 12 | Los catálogos **se cortaban en 200 filas sin orden y sin avisar**: con más de 200 personas, la 201 no existía para nadie | **Cerrado** |

---

## La herramienta que salió de esto

`backend/revisar.py`. Nació de un error concreto: un `settings` que se
usaba arriba y solo se importaba dentro de una función de más abajo. El
código compilaba, arrancaba, y reventaba en la primera petición real —
ocho pruebas en rojo por una línea que ningún compilador iba a señalar.

```
python3 revisar.py
```

Revisa, sin depender de nada instalado: nombres que se usan y no existen,
imports que sobran, funciones de JS que se llaman y no están, claves de
idioma que no estén las tres veces, y la cadena de migraciones. Atrapó
dos errores más mientras se hacía esta revisión.

---

## Lo que sigue abierto

### Zonas horarias — lo más serio de lo que queda

`Pais` guarda lada y moneda, pero **no zona horaria**, y todo el sistema
decide con un solo reloj: el del servidor.

- `CORTE_DE_LA_VISPERA = 18:00` de la central es un único instante para
  México, Brasil y Venezuela.
- Las ventanas de marcado comparan `datetime.now()` del servidor contra
  la hora de pared del país del servicio.
- El aviso de la víspera usa `date.today() + 1`.
- El cierre a mano recibe una hora local del navegador y la compara
  contra el reloj del servidor.

**Con el contenedor en UTC** —que es como arranca un docker sin `TZ`— el
corte de las 18:00 cae a las 12:00 en CDMX. Y hay un caso peor: la lista
de "días sin cerrar" podría ofrecer un día que todavía está corriendo.

**Lo mínimo, hoy:** poner `TZ=America/Mexico_City` en el
`docker-compose.yml` de los servicios `api`, `worker` y `beat`. Eso
alinea todo para México, que es donde está la operación. Brasil y
Venezuela quedan pendientes y necesitan zona horaria por país.

### Moneda

`Tarifario.moneda` y `Pais.moneda_local` son columnas independientes y
nada obliga a que coincidan. `Cotizacion.tipo_cambio` existe en el modelo
y **no se lee en ninguna parte**. Un cliente con tarifario en dólares y
costos en pesos produce una utilidad sin sentido y una comisión negativa.

Hoy no duele porque todo está en pesos. El día que entre un tarifario en
otra moneda, duele de inmediato.

### Cosas menores, anotadas para no perderlas

- `ConceptoNomina` no tiene restricción única en la base: el candado
  contra pagar dos veces vive en Python. Dos cortes calculados en
  paralelo podrían colarse.
- `_puede_ver` del task sheet da acceso **por equipo**, no por jornada:
  quien cubrió un día de un servicio de cinco lee el itinerario de los
  cinco. Puede ser correcto —el equipo es la misma gente todos los
  días— pero conviene decidirlo a propósito.
- `taller_vehiculo.recibido_en`: el modelo la declara NOT NULL y la
  migración la creó nullable.
- `RevisionUnidad.tipo` y `FotoRevision.angulo` son `String`, no `Enum`
  de Postgres: guardan el valor en minúscula mientras todas las demás
  columnas de enum guardan el nombre. Funciona porque todo pasa por
  Pydantic, pero es una excepción al patrón.
- Al reemplazar personal por contingencia, **quien sale pierde el día
  completo**: la asignación se muta en vez de cerrarse y abrirse otra.
  Trabajó ocho horas y cobra cero. No se tocó porque el arreglo correcto
  cambia cómo se modelan las asignaciones.
- Cualquier sobrecosto se etiqueta "horas extra" si hubo una sola hora
  extra en cualquier día del servicio, y eso lo vuelve informativo: pasa
  a facturación sin que nadie lo recotice.
- La manifiesto de la PWA no trae iconos y el aviso apunta a
  `/app/icono.png`, que no existe. Sin icono de 192 px, Android no
  ofrece "Instalar" —y en iPhone hace falta tenerla instalada para
  recibir avisos.
- `POST /auth/token` no tiene límite de intentos.
- `/docs` y `/openapi.json` son públicos.

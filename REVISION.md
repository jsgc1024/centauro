# Revision profunda — 12 de septiembre de 2026

Auditoria por cuatro frentes independientes sobre el codigo completo.
Nada de esto esta arreglado todavia. El orden es de mas grave a menos
grave DENTRO de cada frente; al final hay un orden recomendado global.

Estado al momento de la revision: 124 pruebas en verde, base en la
migracion `e3b82d1a95c7`.

---

## FRENTE 1 — Seguridad y control de acceso

### Criticos

**1.1 Cualquiera sin sesion puede volverse administrador.**
`app/main.py:103` expone `POST /sistema/sembrar-catalogos` sin
autenticacion. Ese endpoint llama a `sembrar_accesos()`, que en
`app/seed.py:360-369` REESCRIBE la contrasena y el rol de todos los
usuarios existentes, incluido `admin@centauro.lat`, y ademas devuelve la
contrasena en la respuesta. Tres pasos y alguien es dueno del sistema.
Al desplegar en OVH esto es una puerta abierta a internet.

**1.2 La llave que firma las sesiones es publica.**
`app/config.py:8` trae `secret_key = "centauro-demo-cambiar-en-produccion"`
y el `.env` no la sobreescribe. Con esa cadena, cualquiera fabrica un
token valido para cualquier usuario sin contrasena. Debe ser obligatoria
por entorno y la aplicacion no debe arrancar sin ella.

### Altos

**1.3 El rol admin es superusuario de facto.** `app/auth.py:93-99` lo
deja pasar por CUALQUIER permiso, no solo catalogos y tarifarios. Aprueba
cierres, paga nomina, ajusta hitos. Contradice la regla escrita.

**1.4 Cualquier usuario lee los viaticos de cualquier otro.**
`app/routers/viaticos.py:86` solo pide sesion, sin verificar pertenencia.
Un conductor recorre `/viaticos/1..N` y saca montos, comprobantes y
descuentos de todo el personal. El endpoint hermano de la misma pila SI
verifica; aqui se olvido.

**1.5 Todos los catalogos son legibles por cualquiera con sesion.**
`app/routers/crud.py:23-34`. Un conductor puede leer el tarifario
comercial completo, el directorio del personal con correos, el tabulador
de viaticos, las comisiones y las placas de toda la flota blindada. Las
escrituras si estan cerradas; las lecturas no.

**1.6 El task sheet confidencial se abre a roles que no lo necesitan.**
`app/routers/tasksheet.py:162`: la verificacion de pertenencia solo aplica
a personal de seguridad. Finanzas puede recorrer los task sheets de todos
los ejecutivos: agenda, movimientos, hotel, vuelo.

**1.7 Alertas de panico: ubicacion visible de mas y falsificables.**
`app/routers/contingencia.py:35`: cualquiera con sesion dispara un panico
sobre cualquier jornada, con coordenadas inventadas, firmado a nombre de
otro. Y finanzas ve coordenadas en vivo sin necesitarlo.

### Medios

**1.8 El enlace de seguimiento al cliente no existe del lado del sistema.**
`app/operacion.py:143`: se genera un token, se manda por correo y no se
guarda en ningun lado. No hay tabla, ni ruta, ni validacion. La caducidad
que el correo promete es decorativa.

**1.9 La bitacora de jornada filtra correos del ejecutivo y el enlace de
seguimiento** a cualquier rol que no sea personal de seguridad.
`app/routers/operacion.py:175`.

**1.10 XSS almacenado en la hoja del task sheet.**
`app/tasksheet_html.py:301`: la unica cadena del archivo que no pasa por
`_esc` es la imagen de la senal, y `PUT /servicios/{id}/senal` no valida
el formato.

**1.11 La geocerca no es un candado.** `app/operacion.py:86`: las
coordenadas las manda el cliente. Y el error de rechazo devuelve la
distancia exacta, con lo que en tres intentos se trilatera el punto de
recogida del ejecutivo.

**1.12 Sesion en localStorage, 12 h, sin revocacion.** `app/web/api.js:4`.
Cerrar sesion solo borra la copia local; el token sigue valido.

### Bajos
- Director general hereda permisos de ESCRITURA, no solo de lectura (`auth.py:81`).
- La firma de cobertura en bitacora solo marca a consultores (`auditoria.py:15`).
- El 403 devuelve el mapa de permisos; el error de integridad devuelve
  nombres de columnas y valores; `/docs` y `/health` estan abiertos;
  `/auth/token` no tiene limite de intentos.

### Bien resuelto
Hitos y su ajuste (el modulo mejor hecho), encuestas publicas, invitaciones
de contrasena, escritura de catalogos, bcrypt, ausencia de inyeccion SQL,
separacion de deberes en nomina y cierre.

---

## FRENTE 2 — Reglas de dinero

### Graves

**2.1 El mismo ajuste de nomina se regenera cada vez que se revisa.**
`app/nomina.py:256-317`. `_pagado_de` solo mira conceptos con
`jornada_id`, y los ajustes se guardan con `jornada_id = None`. Entonces
"lo pagado" nunca cambia y la diferencia se vuelve a calcular. Un error de
700 puede cobrarse 700 cada semana, indefinidamente.

**2.2 Volver a pedir transferencia dispersa el total completo otra vez.**
`app/routers/viaticos.py:119`. Si ya se transfirio y luego se piden
viaticos adicionales, una segunda solicitud manda el NUEVO TOTAL, no el
faltante. El conductor recibe 6,800 por 3,800 asignados y el sistema no
lo reporta como sobrante.

**2.3 Un ajuste puede pagarse dos veces.** `app/nomina.py:106`. El candado
antidoble filtra `jornada_id IS NOT NULL`, asi que los ajustes quedan
fuera. Dos cortes en borrador al mismo tiempo lo pagan los dos.

**2.4 El consultor controla el reloj que decide si pierde su comision.**
`app/routers/cierre.py:114` y `:176` aceptan la fecha y hora como
parametro del cliente. Cerrar 60 h tarde y mandar `?ahora=` con una fecha
anterior devuelve la comision intacta.

**2.5 El barrido transfiere viaticos que la contingencia ya cancelo.**
`app/contingencia.py:180` cancela el viatico pero no toca la solicitud de
transferencia, que sigue pendiente. El barrido deposita a alguien que ya
no va al servicio, y nadie le pide comprobacion.

**2.6 El plazo de 24 h del conductor nunca se fija ni se valida.**
`limite_comprobacion` se queda en NULL en el flujo normal. Consecuencias:
un viatico se puede cerrar a los 30 dias; el panorama de "plazo vencido"
sale SIEMPRE vacio; y el criterio de estrella de cierre de viaticos nunca
castiga un retraso. Ademas `limite_consultor` se calcula desde que se abre
el cierre, no desde el fin del servicio, asi que el escalon de 24+24 no
existe.

### Altos

**2.7 `enviar-finanzas` no valida estatus:** reabre cierres aprobados o ya
facturados (`app/routers/cierre.py:178`).

**2.8 La rentabilidad ignora por completo el costo de los freelancers.**
`app/cierre.py:290` solo consulta el tabulador de planta. Un servicio
cubierto con freelancers reporta costo de personal CERO y margen del 95%
en vez del 40%. Ese numero alimenta la decision comercial y la comision
del consultor.

**2.9 `monto_hora_extra` en NULL se paga como cero.** Al cliente si se le
cobran las horas extra; al personal se le pagan en cero, sin aviso. El
candado de "sin tarifa no sale el corte" no revisa la hora extra.

**2.10 Jornadas atrapadas en un borrador de otra semana** que nunca se
pagan, y no hay ninguna consulta que las rescate (`app/nomina.py:106`).

### Medios
- La base de la comision del consultor resta viaticos de una facturacion
  que no los contiene (`app/comisiones.py:59`). PENDIENTE DE DECISION:
  depende de si el tarifario ya trae los viaticos dentro del precio.
- El combustible se asigna completo a CADA persona de la jornada, siendo
  del vehiculo. En contingencia se duplica sin revision humana.
- Operaciones de dinero sin candado de estatus: devolver, confirmar
  transferencia, rechazar comprobante, autorizar bono, corte de comisiones.
- El descuento de viaticos bloquea el ajuste de jornada de la misma
  persona en el mismo servicio (`app/nomina.py:280`).
- El viatico nuevo de la contingencia se crea pero nunca se solicita.

### Bajos
- `_horas_extra` usa `ceil`: 1 minuto de retraso = 1 hora extra completa.
  DECISION DE NEGOCIO PENDIENTE.
- Se pierde un centavo por persona al repartir el bono entre 3 estrellas.
- `estimar_combustible` no filtra vigencia futura.

### Bien resuelto
La facturacion de viaticos segun modo de cobro, las horas extra solo en
full day, el candado antidoble para jornadas, que el corte se frene sin
tarifa, y el uso consistente de Decimal (no hay aritmetica de dinero en
float).

### Sospecha sin confirmar
El bono mensual se calcula y se autoriza, pero no se encontro ninguna ruta
que lo convierta en pago ni que lo lleve a la nomina semanal.

---

## FRENTE 3 — Modelo de datos y migraciones

Resultado general: **el modelo y las migraciones estan alineados**. 59 de
59 tablas, cero columnas de mas o de menos, cero diferencias de tipo o
nulabilidad. La cadena de 20 migraciones es lineal, sin ramas, una sola
cabeza. Los 25 enums coinciden.

### Graves

**3.1 `task_sheet.equipo_id` se agrega NOT NULL sin relleno.**
`migrations/versions/e8ea5b992701:21`. Cualquier base que ya tenga un
task sheet publicado revienta al migrar, y la migracion entera se
revierte. En el demo local no paso porque no habia datos. EN OVH SI VA A
PASAR si se despliega sobre una base con historia.

**3.2 El candado que "impide pagar dos veces la misma jornada" no existe
en la base.** Solo vive en Python, leyendo la tabla a memoria al inicio
del calculo. Dos corridas solapadas insertan el doble sin que nada lo
impida. Justo el lunes, que es cuando corre.

**3.3 `ajuste_comision` sin unique:** dos llamadas concurrentes descuentan
el doble al consultor.

**3.4 `cotizacion` sin unique en (servicio_id, version):** dos
recotizaciones simultaneas producen dos "version 3". `task_sheet` SI lo
tiene; es una asimetria evidente.

**3.5 La cotizacion se amarra a los equipos por texto libre sin llave
foranea,** y `equipo` no tiene unique de alias. El dia que haya dos
"Alfa" en un servicio, el comparativo de cierre suma sus lineas juntas y
las desviaciones salen mal en silencio.

### Altos

**3.6 Llaves foraneas sin indice donde mas se consulta:**
`asignacion_personal.persona_id`, `asignacion_vehiculo.vehiculo_id`,
`hito.jornada_id`, `equipo.servicio_id`. El tablero de profesionalismo
es O(personal x asignaciones) y el panorama de la central escanea `hito`
completo. Cuatro CREATE INDEX lo resuelven.

**3.7 84 columnas NOT NULL con default de Python y sin server_default.**
Las que llevan dinero o factor de pago: `dia_festivo.factor_comision`,
`concepto_nomina.factor_festivo`, `parametro_combustible.holgura_pct`,
`criterio_estrella.umbral_pct`, `jornada.geocerca_metros`, los tres montos
de `asignacion_viatico`, los totales de `cierre`, `comision_consultor.viaticos`,
`contrato_implantado.dias_base`, y 12 columnas de estatus.
Nota: esto NO es un desfase entre pruebas y produccion — los dos esquemas
son identicos. El riesgo es el objeto construido en Python sin guardar
(el caso de ParametroProfesionalismo que ya tumbo una pantalla).

### Medios y bajos
- El parche de enums de `env.py` fuerza `checkfirst=True` globalmente: si
  algun dia falta un valor, nada avisa hasta que reviente en produccion.
- Varios `downgrade()` rotos: `e8ea5b992701` falla siempre; la migracion
  inicial no borra sus enums.
- Dos diferencias de forma de indice (ruido en autogenerate, sin riesgo).
- `parametro_combustible` sin unique de vigencia: con dos renglones de la
  misma fecha, el precio aplicado es arbitrario.
- `peso_profesionalismo` no valida en la base que sume 100.
- `29ecac30d1f2` es una migracion vacia y duplicada de titulo.
- Tres mecanismos de reemplazo conviven sin relacion entre si.

---

## FRENTE 4 — Consola web

De 27 llamadas a la API revisadas una por una: 21 correctas, 3 rotas,
3 sospechosas.

### Lo que impide trabajar

**4.1 No se puede guardar el meet and greet sin latitud y longitud.**
`app/web/servicio.js:232` manda cadenas vacias y `OrigenIn` las exige
como Decimal obligatorio. Como el task sheet no se publica sin origen,
ESTO BLOQUEA TODO EL FLUJO.

**4.2 El boton "Ver la hoja" nunca funciona.** `servicio.js:394`:
`window.open` no manda la cabecera de sesion. Es el entregable final del
flujo. Ojo: la salida facil (quitarle la autenticacion al endpoint)
convertiria el task sheet en publico. Hay que resolverlo con un enlace
temporal o descargando el HTML y abriendolo como blob.

**4.3 Las alertas de riesgo del personal se pierden.** `servicio.js:159`
lee `a.mensaje || a.tipo`; el backend devuelve `a.motivo`. Es justo el
dato que el consultor necesita antes de forzar una asignacion.

**4.4 Se pinta la palabra literal `null`** cuando no hay personal libre
(`servicio.js:193`), que es el caso que el backend contempla con aviso.

**4.5 El selector de modalidad mezcla paises.** `consultor.js:71` muestra
seis opciones con tres etiquetas repetidas, sin filtrar por el pais
elegido. Si se cuela la de Brasil, la jornada se calcula de 10 h en vez
de 12 y las horas extra salen mal desde el alta.

**4.6 La pantalla de Personal truena si no hay paises,** y siempre
muestra solo el primer pais (`app.js:101`).

### Medios
- Peticiones N+1 secuenciales al abrir un servicio.
- `location.reload()` borra el mensaje de exito antes de que se lea.
- Botones de la central que quedan muertos si falla la peticion.
- Fuga de temporizador al cambiar de pantalla rapido.
- Dos criterios distintos para leer formularios; de ahi salen 4.1 y otros.
- `mensaje()` sin guarda: si no existe la barra, tapa el error original.

### Accesibilidad y telefono
- Ninguna etiqueta esta asociada a su campo: afecta TODOS los formularios.
- Las filas clicables no se pueden usar con teclado.
- Ninguna tabla tiene contenedor con scroll: en telefono desborda la
  pagina entera.
- Contraste del gris por debajo del minimo legible.

### Bien resuelto
Sin imports rotos, sin superficie de XSS, el orden de rutas es correcto,
el manejo de errores de `api.js` es solido, y los permisos del frontend
coinciden con los del backend.

---

## Orden recomendado

### Antes de que esto toque internet
1. Cerrar `POST /sistema/sembrar-catalogos` y rotar todas las contrasenas.
2. `SECRET_KEY` obligatoria por entorno.
3. Pertenencia en `GET /viaticos/{id}` y en el task sheet.
4. Cerrar las lecturas de catalogos y tarifarios por rol.

### Para que la consola se pueda usar
5. `OrigenIn` con lat/lon opcionales (4.1) — desbloquea publicar.
6. La hoja imprimible desde la consola (4.2).
7. `a.motivo` (4.3), el `null` pintado (4.4), modalidades por pais (4.5).

### Antes de confiar en los numeros
8. El ajuste que se regenera (2.1) y el que se paga dos veces (2.3).
9. La transferencia que dispersa el total otra vez (2.2).
10. El reloj en manos del consultor (2.4).
11. El barrido que paga viaticos cancelados (2.5).
12. El plazo de 24 h que nunca se fija (2.6).
13. Freelancers fuera de la rentabilidad (2.8).
14. Hora extra en NULL pagada como cero (2.9).

### Antes de desplegar en OVH
15. La migracion `e8ea5b992701` (3.1) — rompe el despliegue.
16. Unicidad en base de nomina, cotizacion y ajuste de comision (3.2-3.4).
17. Los cuatro indices de llave foranea (3.6).

### Decisiones de negocio pendientes
- ¿La comision del consultor debe restar viaticos cuando se cobran por
  comprobar? (2.11)
- ¿Un minuto de retraso es una hora extra completa, o se cobra por
  fraccion? (`ceil` vs redondeo)
- ¿El bono mensual se paga por el sistema o por fuera?
- ¿El combustible debe asignarse al vehiculo en vez de a la persona?

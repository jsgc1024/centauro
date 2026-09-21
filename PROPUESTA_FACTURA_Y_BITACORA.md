# Facturación, y la bitácora del día

_Análisis y propuesta. 20 de septiembre de 2026._

---

# Parte 1 — La facturación

## Lo que hay

`EstatusCierre.FACTURADO` existe desde hace meses, se lee en `nomina.py`
y en `comisiones.py` como un estado aceptado, y **nadie lo escribe**. El
cierre se queda en `APROBADO` para siempre, y por eso un servicio no
puede salir del panel: no hay forma de decir que ya se facturó.

## El hallazgo que cambia el diseño

**Eventual e implantado no facturan igual.**

- El **eventual** cierra por servicio: un cierre, un servicio, una
  factura.
- El **implantado** ya tiene `/implantados/.../resumen del mes para
  facturar`, que agrupa un mes completo. Ahí una factura cubre muchos
  días y, en algunos clientes, varios servicios.

Si el folio de la factura se guarda como un campo del servicio, el
implantado obliga a repetir el mismo folio en veintidós renglones —y el
día que se cancele esa factura hay que acordarse de los veintidós—.

## La propuesta

**Una tabla `factura`**, y el servicio apunta a ella.

| Campo | Qué guarda |
|---|---|
| `folio` | el de Odoo. Llave única: es lo que impide facturar dos veces |
| `fecha` | cuándo se emitió |
| `monto`, `moneda` | lo facturado |
| `cliente_id` | a quién |
| `recibida_en` | cuándo la mandó Odoo |

Y en `servicio`, un `factura_id` nullable. Una factura, muchos
servicios; un servicio, una factura o ninguna.

**Odoo la manda**, como manda la flota y el personal:

```
POST /odoo/facturas
[{ "folio": "A-10422", "fecha": "2026-10-05",
   "monto": "184300.00", "moneda": "MXN",
   "servicios": ["EP/E-0142", "EP/E-0139"] }]
```

Con tres candados:

1. **No se factura un servicio sin cierre aprobado.** Si Odoo manda un
   folio para algo que finanzas no validó, se rechaza y se dice cuál y
   por qué. Facturar antes de aprobar es facturar un número que todavía
   puede cambiar.
2. **No se factura dos veces.** El folio es único y un servicio ya
   ligado no se reasigna sin desligarlo primero.
3. **Lo que no viene no borra.** Un envío parcial no desfactura nada.

**El efecto en la pantalla:** el servicio facturado sale de la cartera
del consultor por omisión, con un filtro *Facturados* para encontrarlo y
la búsqueda por folio intacta. No se archiva ni se esconde de la
búsqueda: se quita de la lista donde estorba.

## Lo que falta decidir

**¿Odoo factura por servicio o por corte de mes?** La propuesta de
arriba aguanta las dos —por eso la factura es una tabla y no un campo—
pero el formato del envío cambia: si es por corte, en `servicios` van
todos los folios del mes; si es por servicio, va uno.

---

# Parte 2 — La bitácora del día

## Lo que hay, y es más de lo que se ve

**Seis tipos de hito, y la app marca los seis**: llegada al origen,
contacto con el ejecutivo, salida a ruta, llegada a destino, standby y
fin de servicio. Cada uno con su hora, sus coordenadas, si cayó dentro
de la geocerca, y **si se marcó diferido** —la app guarda la hora que
dice el teléfono y la hora en que llegó al servidor, porque se puede
marcar sin señal—.

La central enseña **solo el último**: el renglón del pulso dice qué hito
fue el más reciente y cuántos minutos lleva callado. La secuencia
completa no se ve en ningún lado.

## Sobre el reporte periódico

Lo que se reporta cada pocos minutos —`LecturaTrayecto`, con posición y
distancia al punto— **solo existe antes del meet and greet**. El trayecto
se apaga al marcar la llegada al origen.

Y está bien que así sea. Ese rastreo existe porque en esa hora y media
hay **una decisión que tomar**: si alguien no va a llegar, reponerlo toma
hora y media y hay que empezar ya. Una vez que el servicio arrancó, la
decisión ya se tomó.

Durante el servicio lo que hay es: los hitos que marca el equipo, y una
alerta de silencio si pasan **dos horas** sin ningún reporte.

## La propuesta: una sola columna, tres fuentes

Dentro del servicio en curso, una **línea de tiempo del día** que mezcla
en una sola columna ordenada por hora:

1. **Lo planeado** — las paradas de la agenda (`ParadaAgenda`: hora,
   lugar, dirección, notas), que es lo que el cliente dictó.
2. **Lo marcado** — los seis hitos, con su hora, quién lo marcó, si cayó
   dentro de la geocerca y **si llegó diferido** (marcado a las 14:05,
   recibido a las 14:40: eso se dice, no se esconde).
3. **Lo que pasó alrededor** — las alertas (silencio, fuera de geocerca,
   fuera de ventana) y lo que la central hizo a mano: ajustar un hito,
   cerrar el día. Eso ya vive en la bitácora de acciones.

Lo que esa columna contesta de un golpe, y hoy no se puede contestar:

- **Dónde el plan y la realidad se separaron.** La parada de las 14:00
  en Santa Fe y la llegada a destino a las 15:20 son dos renglones
  seguidos, y la diferencia se lee sin restar.
- **Qué pasó en el hueco.** Dos horas entre el contacto y la salida a
  ruta, sin standby en medio, es una pregunta. Hoy nadie la ve.
- **Qué se marcó tarde.** Un día donde todo se marcó diferido no es un
  día bien reportado.

**Lo que NO propongo: rastreo continuo durante el servicio.** Tres
razones, en orden de peso: es seguir a una persona fuera de un momento
acotado y con un propósito claro; se come la batería y los datos del
teléfono justo cuando más falta hacen; y el valor operativo está en los
momentos, no en la línea. Si lo que se quiere es saber que el equipo
sigue vivo, el standby ya hace eso y cuesta un toque.

Si aun así hace falta la posición durante el servicio, la forma honesta
es **acotarla**: solo mientras el hito vigente sea `salida_ruta` —o sea,
solo cuando el ejecutivo va en movimiento— y apagándose en la llegada a
destino. Eso se le puede explicar al equipo en una frase, que es la
prueba de que está bien acotado.

## Lo que falta decidir

- **¿La bitácora la ve el cliente?** Lo que el ejecutivo lee hoy es el
  task sheet. Una línea de tiempo con horas exactas y geocercas es
  información de operación, y enseñarla cambia lo que el cliente va a
  reclamar.
- **¿Se guarda posición durante el servicio?** Con el alcance acotado de
  arriba, o no se guarda.

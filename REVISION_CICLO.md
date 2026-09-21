# El ciclo del servicio: en curso, terminado, facturado

_Revisión del 20 de septiembre de 2026. Lo que se pidió: verificar el paso
de EN CURSO a TERMINADA, dónde se hacen los cambios y si las pantallas los
reflejan._

---

## Las dos máquinas de estado

Hay dos, y no son la misma: la **jornada** (un día) y el **servicio**
(el contrato completo).

**Jornada** — `PLANEADA → CONFIRMADA → PROXIMA_A_INICIAR → EN_CURSO →
TERMINADA`, más `CANCELADA`.

**Servicio** — `BORRADOR → SOLICITADO → COTIZADO → AUTORIZADO → PLANEADO
→ ASIGNADO → EN_CURSO → TERMINADO → CERRADO`, más `CANCELADO`.

**Cierre** — `ABIERTO → EN_REVISION_IA → ENVIADO_FINANZAS → APROBADO →
FACTURADO`, más `DEVUELTO_A_OPERACION`.

---

## Quién mueve cada estado de la jornada

| Estado | Quién lo escribe | Dónde |
|---|---|---|
| PLANEADA | al crearse, y al deshacer un cierre a mano | `models`, `operacion.reabrir` |
| CONFIRMADA | **nadie** | — |
| PROXIMA_A_INICIAR | `tablero_proximos`, que es un **GET** | `operacion:644` |
| EN_CURSO | el hito de llegada al origen | `operacion:479` |
| TERMINADA | el hito de fin de servicio, o el cierre a mano | `operacion:537`, `operacion:924` |
| CANCELADA | cancelar el servicio | `servicios:1743` |

---

## Hallazgo 1 — `VIVAS` olvida dos estados, y es el peor momento

`central.py` define:

```python
VIVAS = (m.EstatusJornada.PLANEADA, m.EstatusJornada.EN_CURSO)
```

y con eso filtra **tres** consultas: la banda de mañana, **el camino al
punto** y la tira de la semana.

Una jornada en `PROXIMA_A_INICIAR` **no está en esa lista**. Y ese estado
se le pone justo a las jornadas de hoy que arrancan en menos de dos
horas: exactamente las que el camino al punto existe para vigilar.

El efecto: **la jornada desaparece de la banda del camino en las dos
horas previas al meet and greet.** El trayecto sigue corriendo —su
propio filtro sí incluye ese estado, `trayecto.py:202`— así que se
siguen mandando los toques y cobrando los silencios, pero la central
deja de verlos. Es el peor momento posible para que algo se esconda.

`CONFIRMADA` tampoco está en `VIVAS`, pero eso hoy no muerde por el
hallazgo 3.

**Arreglo:** la lista deja de decir qué está vivo y pasa a decir qué está
muerto. `MUERTAS = (CANCELADA, TERMINADA)` y se filtra con `notin_`. Así
un estado nuevo nace visible, que es el valor correcto por omisión para
una pantalla de vigilancia.

---

## Hallazgo 2 — un GET cambia el estado

`tablero_proximos` es `@router.get` y hace `db.commit()` promoviendo
jornadas a `PROXIMA_A_INICIAR`.

O sea: **que una jornada cambie de estado depende de que alguien abra una
pantalla.** Y por el hallazgo 1, ese cambio la hacía desaparecer de otras
tres. Eso explica un "a veces se ve y a veces no" que no tendría cómo
reproducirse a mano.

**Arreglo:** la promoción sale del GET y se va a una tarea del reloj, que
corre cada cinco minutos. Leer una pantalla no cambia datos.

---

## Hallazgo 3 — dos estados que nadie escribe nunca

- **`EstatusJornada.CONFIRMADA`** — se lee en dos filtros y no se asigna
  en ningún lado. La confirmación real vive en
  `AsignacionPersonal.confirmado`, que es por persona; el estado de la
  jornada duplicaba esa idea y quedó sin dueño.
- **`EstatusServicio.TERMINADO`** — se lee en `implantado.py` dos veces y
  **nadie lo escribe**. Un servicio eventual va `ASIGNADO → … → CERRADO`
  sin pasar por `EN_CURSO` ni por `TERMINADO`: el `EN_CURSO` del servicio
  solo se pone en implantados, con el primer meet and greet.

No rompen nada hoy porque los filtros que los mencionan son inclusivos.
Pero un estado que nadie escribe es una promesa que la pantalla puede
creerse.

---

## Hallazgo 4 — el día abandonado genera alertas para siempre

`revisar_standby` consulta **todas** las jornadas EN_CURSO sin mirar la
fecha, igual que hacía el pulso de la central. Un día de hace tres
semanas que nadie cerró sigue ahí, y cada quince minutos se revisa para
volver a concluir que lleva tres semanas callado.

Lo mismo en `panorama._jornadas(EN_CURSO)`: la pantalla de Operación
cuenta esos días como "lo que está corriendo".

**Arreglo:** la misma regla que ya se aplicó al pulso — pasó su fin hace
más de las horas de gracia **y** lleva horas callado— vale aquí. Esos
días viven en *Días sin cerrar*, que es la pantalla que tiene el botón.

---

## Hallazgo 5 — nadie factura

`EstatusCierre.FACTURADO` existe, se lee en `nomina.py` y en
`comisiones.py` como un estado aceptado, y **nadie lo escribe**. El
cierre se queda en `APROBADO` para siempre.

Eso conecta con lo que se pidió: **que el servicio desaparezca del panel
cuando pase a facturación, porque de ahí lo toma Odoo.** Hoy no puede
desaparecer, porque no hay forma de decir que ya se facturó.

Lo que falta, en orden:

1. **Quién lo marca.** Finanzas, después de aprobar el cierre: aprobar es
   "las cuentas cuadran", facturar es "salió la factura". Son dos
   momentos y dos manos distintas.
2. **Con qué queda amarrado.** El folio de la factura, como la referencia
   del banco en el depósito: sin ese número, "facturado" es una palabra.
3. **Qué se va a Odoo.** Si Odoo emite la factura, el sistema debería
   recibir el folio y la fecha —igual que recibe la flota y el personal—
   y marcar FACTURADO solo. Si se factura a mano, alguien captura el
   folio aquí.
4. **De qué panel desaparece.** Es la pregunta que hay que contestar
   antes de escribir nada: hoy el servicio cerrado sigue en la cartera
   del consultor. Desaparecer de la cartera no es lo mismo que
   desaparecer del panorama, ni de la búsqueda.

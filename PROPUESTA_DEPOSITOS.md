# El depósito bancario — propuesta

_Cómo ve finanzas cada solicitud y cómo queda la evidencia del depósito._
_Antes de programar nada. 17 de septiembre de 2026._

---

## Lo que finanzas ve hoy

Por país, un renglón por persona y equipo:

```
Persona          Servicio        Arranca      Monto      Referencia
Juan Ramírez     CN-2026-0142    mar 16 sep   $4,200    [_________] [Confirmar]
                 4 día(s) · Grupo Salinas · Equipo Alfa
```

Se agrupa a propósito: son cuatro días pero es **un solo depósito**, y
confirmar cuatro renglones del mismo agente es como se paga dos veces.

**Lo que no ve:**

- **Quién lo solicitó.** El dato existe (`asignado_por_id`) y no llega a
  la pantalla. Finanzas no sabe qué consultor autorizó ese gasto.
- **De qué se compone el monto.** El desglose existe —alimentos,
  hospedaje, combustible, casetas, traslado— con su descripción y si
  salió del tabulador, de un estimado por kilómetros o de una captura a
  mano. Finanzas ve $4,200 y nada más.
- **Qué día trae qué.** Los días se suman y el detalle no se abre.
- **El comprobante del banco.** Solo hay un campo de texto para la
  referencia. **No existe forma de subir el comprobante.**

---

## El hallazgo de fondo

**El depósito bancario no existe en el sistema.**

Hay una `SolicitudTransferencia` por jornada. La pantalla las agrupa al
vuelo para mostrar "un depósito por persona". Pero eso que finanzas
ejecuta en el banco —una transferencia, con su referencia y su
comprobante— no está en ninguna tabla.

Por eso no hay a qué colgarle la evidencia. Y si se le cuelga a cada
solicitud, la misma imagen se guarda cuatro veces para un depósito de
cuatro días: con 300 KB por imagen son 1.2 MB repetidos, dentro de la
base, por cada depósito.

La operación ya tiene esa entidad. El sistema es el que no la sabe.

---

## El modelo

Una tabla nueva, `deposito_bancario`:

| Campo | Qué guarda |
|---|---|
| `persona_id` | A quién se le deposita |
| `equipo_id` | De qué equipo son los días que cubre |
| `monto`, `moneda` | Lo que salió |
| `referencia` | El folio del banco (SPEI, clave de rastreo) |
| `comprobante` | La captura del banco, dentro del registro |
| `depositado_en` | Cuándo salió el dinero |
| `despachado_por_id` | Quién de finanzas lo ejecutó |

Y `solicitud_transferencia.deposito_id` apuntando a él.

**La migración rellena hacia atrás.** Por cada grupo de solicitudes ya
confirmadas con la misma persona y equipo se crea su depósito, con la
referencia y la fecha que ya tenían. Nada de lo que está pagado se
pierde ni cambia de sentido.

---

## Las pantallas

### Por pagar: cada solicitud, abierta

El renglón se abre. Cerrado dice lo que hace falta para decidir; abierto,
de qué se compone.

```
┌─ Por depositar · México ───────────────────── $12,400 MXN ─┐
│                                                             │
│  ▸  Juan Ramírez                         $4,200    4 días  │
│     CN-2026-0142 · Grupo Salinas · Equipo Alfa             │
│     Arranca mar 16 sep · Solicitó Ana Solís, 15 sep 18:40  │
│                                            [ Depositar ]    │
│                                                             │
│  ▾  Marta Solís                          $3,100    3 días  │
│     CN-2026-0142 · Grupo Salinas · Equipo Alfa             │
│     Arranca mar 16 sep · Solicitó Ana Solís, 15 sep 18:40  │
│                                                             │
│     ┌───────────────────────────────────────────────────┐   │
│     │  mar 16 sep   Alimentos                 $   450   │   │
│     │               Combustible · 120 km      $   680 ~ │   │
│     │  mié 17 sep   Alimentos                 $   450   │   │
│     │               Hospedaje                 $ 1,200   │   │
│     │               Casetas                   $   320   │   │
│     │  jue 18 sep   Alimentos                 $   450   │   │
│     │                                        ─────────  │   │
│     │                                Total    $ 3,100   │   │
│     │                                                   │   │
│     │  ~ estimado por kilómetros   ✎ capturado a mano   │   │
│     └───────────────────────────────────────────────────┘   │
│                                            [ Depositar ]    │
└─────────────────────────────────────────────────────────────┘
```

Las marcas de origen importan: un monto del tabulador no se discute, uno
capturado a mano sí. Hoy finanzas no puede distinguirlos.

### Depositar: la operación bancaria

```
┌─ Depósito a Marta Solís ──────────────────────────────────┐
│                                                            │
│  Monto        $3,100 MXN                                   │
│  Cubre        3 días · CN-2026-0142 · Equipo Alfa         │
│  Solicitó     Ana Solís · 15 sep 18:40                    │
│                                                            │
│  Referencia del banco                                      │
│  [ 4471002839___________________ ]                         │
│                                                            │
│  Comprobante                                               │
│  [ Elegir archivo ]  la captura del banco                  │
│                                                            │
│  [ Cancelar ]                   [ Registrar el depósito ]  │
└────────────────────────────────────────────────────────────┘
```

Al registrarlo: las tres solicitudes pasan a confirmadas de una vez, el
viático queda transferido, y el agente lo ve en su app como saldo
disponible. Un depósito, un registro, un comprobante.

### Depositado: la memoria, con su evidencia

```
┌─ Depositado · septiembre ───────────── 38 depósitos · $214,800 ─┐
│                                                                  │
│  17 sep 09:12   Marta Solís      $3,100   ref 4471002839        │
│                 CN-2026-0142 · Equipo Alfa                       │
│                 Despachó Laura Méndez        [ Ver comprobante ] │
│                                                                  │
│  17 sep 09:08   Juan Ramírez     $4,200   ref 4471002838        │
│                 CN-2026-0142 · Equipo Alfa                       │
│                 Despachó Laura Méndez        [ Ver comprobante ] │
└──────────────────────────────────────────────────────────────────┘
```

Hoy este renglón existe pero sin comprobante y sin decir quién despachó.

---

## Lo que no cambia

- El agrupamiento: un depósito por persona y equipo, no uno por día.
- El barrido por lote y las ventanas de transferencia.
- Las otras tres vistas de finanzas —comprometido, por comprobar,
  devoluciones— siguen igual.

---

## Las ocho decisiones, ya tomadas

**Los datos bancarios vienen de Odoo**, como el teléfono y la foto: el
maestro de empleados vive allá y aquí solo se lee. Mientras esa conexión
no exista, los campos —banco, CLABE, titular— quedan en la ficha de la
persona marcados como *viene de Odoo*, y finanzas los puede llenar. Se
van poblando conforme se deposita, y el día que Odoo conecte, Odoo manda.

**Un depósito por persona y equipo.** Si alguien anda en dos servicios,
recibe dos depósitos el mismo día. Es más movimiento en el banco, pero
cada transferencia queda amarrada a un servicio y la rentabilidad de ese
servicio cuadra sola.

**Se deposita lo solicitado, ni un peso más ni uno menos.** El monto lo
decide el consultor —esa es la regla— y finanzas ejecuta. Si está mal, se
corrige en la solicitud y se vuelve a pedir. Así el desglose que el agente
tiene que comprobar siempre cuadra con lo que recibió.

**Referencia y comprobante, los dos, para poder registrar.** Es la misma
regla que ya tienen las compras especiales, y es el punto del ejercicio:
que quede la evidencia.

**La evidencia se corrige; el depósito casi no se anula.** Subir el
archivo correcto o arreglar la referencia se puede siempre, y queda
anotado quién lo cambió y cuándo. Anular el depósito completo, solo
mientras el agente no haya subido ningún comprobante de gasto: después de
eso quedarían comprobaciones colgando de un depósito que ya no existe.

**Lo ven finanzas y dirección, el consultor del servicio, y el agente en
su app** —cada quien el suyo. El agente es quien pregunta "¿ya me
depositaron?", y el consultor es quien recibe esa llamada.

**Solo imágenes, como el resto del sistema.** Finanzas sube la captura
del comprobante. Para que una captura de pantalla de Retina no rebote
contra el límite de 3 MB, la consola la reduce antes de subirla, igual
que la app de campo hace con la foto del ticket.

---

## Qué hay que construir

**Base de datos.** La tabla `deposito_bancario`, la columna
`deposito_id` en las solicitudes, y la migración que rellena hacia atrás
los depósitos ya confirmados.

**Motor.** Registrar un depósito: valida que las solicitudes sean de la
misma persona y equipo, que no estén ya depositadas, guarda el
comprobante y confirma las tres de una vez.

**API.** La bandeja devuelve el desglose por día y concepto, con su
origen, y quién solicitó. El endpoint de registro acepta el archivo. Uno
para ver el comprobante.

**Consola.** El renglón que se abre, la ventana del depósito, y la vista
de *Depositado* con la evidencia.

**Idiomas.** Las claves nuevas en es, en y pt.

**Pruebas.** Que un depósito confirme todas sus solicitudes de una vez;
que no se pueda depositar dos veces lo mismo; que el desglose sume
exactamente el monto; que el comprobante se guarde una sola vez; y que
la migración deje los depósitos viejos con su referencia intacta.

---

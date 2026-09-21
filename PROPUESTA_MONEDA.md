# El tipo de cambio — propuesta

_Para que la rentabilidad de un servicio sea un hecho y no un número que
se mueve solo._
_Antes de programar nada. 18 de septiembre de 2026._

---

## Lo que pasa hoy

`cierre.py`, en la función que calcula la rentabilidad de un servicio:

```python
utilidad = facturacion - costo_total
margen  = utilidad / facturacion * 100
```

`facturacion` sale del tarifario de la cotización, **y el tarifario
tiene su propia moneda**. `costo_total` son comisiones, viáticos y
unidad — y esos **siempre están en la moneda local del país**: lo
verifiqué renglón por renglón.

O sea que esa resta puede ser **dólares menos pesos**. Y el resultado
sale rotulado con la moneda de la cotización, así que se ve legítimo.

Un servicio en México cotizado en 5,000 USD con 80,000 MXN de costo
diría: utilidad **−75,000**, margen **−1,500%**. Nadie lo ha visto
todavía porque no hay tarifarios en dólares cargados. El día que
cargues uno, todos los márgenes de esos servicios salen basura, y se ven
como números normales.

`Cotizacion.tipo_cambio` existe desde el principio, vacío, y nadie lo
lee. Es el agujero que vino a tapar y nunca se conectó.

---

## Lo que ya está bien y no hay que inventar

Esto importa porque acota el problema a una esquina chica:

- **Los viáticos nunca necesitan conversión.** Se crean en cinco lugares
  distintos —asignación normal, depósito por equipo, depósito adicional
  y los dos gemelos del implantado— y los cinco toman
  `servicio.pais_id → pais.moneda_local`.
- **El país del servicio se captura en el alta y no se reasigna en
  ninguna parte del sistema.** No hay endpoint que lo cambie. Así que la
  regla no depende de que nadie se equivoque: está cerrada por
  construcción.
- **La nómina tampoco.** Se calcula por país y toma la moneda local, así
  que un corte nunca mezcla monedas.

Entonces el tipo de cambio **no toca el costo**. Solo toca el precio, y
solo cuando el cliente pide otra moneda.

---

## La idea: son dos conversiones, no una

Es lo único de fondo de esta propuesta. Hay **dos preguntas distintas** y
cada una necesita su tipo de cambio.

### 1. ¿Cuánto ganamos en este servicio?

Se contesta con **el tipo de cambio del día en que se autorizó la
cotización**, estampado en ella y congelado ahí para siempre.

Un servicio de marzo tiene el margen que tuvo en marzo. No se mueve
nunca. Si se recalculara con el dólar de hoy, la utilidad de marzo
cambiaría sola cada mañana y ningún cierre volvería a cuadrar — ni
contra Odoo, ni contra lo que ya se le facturó al cliente.

Ese número es un **hecho**, no una estimación.

### 2. ¿Cuánto ganamos en septiembre, entre todos los países?

Esa sí necesita convertir pesos, reales y dólares a una sola moneda, y
ese tipo de cambio **sí se mueve**. Está bien que se mueva: lo que no
está bien es que no se diga cuál se usó.

La regla es que ese reporte lleva la fecha pegada al número:

```
Utilidad consolidada de septiembre
USD 184,300   ·   al tipo de cambio del 30 de sep
```

**Mezclar las dos es cómo un reporte dice una cosa el lunes y otra el
martes.** Hoy no están mezcladas: simplemente no existe ninguna.

---

## De dónde sale el número

Aquí cambio lo que te dije el otro día, y es por algo que encontré al
abrir el código.

**El tipo de cambio debe venir de Odoo, junto con la cotización.**

Si Odoo cotizó en dólares y convirtió con su propio tipo de cambio, y
nosotros convertimos con el FIX de Banxico, los dos números no cuadran.
Finanzas se pasaría el mes conciliando diferencias que no son error de
nadie: son dos fuentes distintas para el mismo dato. La factura la emite
Odoo; el tipo de cambio de esa factura es el de Odoo.

Los bancos centrales —Banxico, BCB, la TRM— siguen sirviendo, pero para
otra cosa:

| Para qué | De dónde |
|---|---|
| La rentabilidad de un servicio | El tipo de cambio que Odoo mandó con la cotización |
| El consolidado de dirección | Banco central del país, del día de corte |
| Cuando Odoo no lo manda | Banco central, y la pantalla lo dice: "tipo de cambio de referencia" |

Y un hueco que hay que nombrar: **hoy no hay sincronización de
cotizaciones con Odoo.** `odoo.py` sincroniza personal, flota y taller, y
nada más. La cotización vive aquí, con su tarifario local. Así que
"traer el tipo de cambio de Odoo" es un pedazo de una integración que
todavía no existe.

---

## La regla que hay que sostener

Una sola, y de ella sale todo lo demás:

> **Cada monto se guarda en su moneda, con su moneda al lado. Nunca se
> guarda un número ya convertido como si fuera nativo.**

La conversión pasa al momento de leer, con un tipo de cambio que tiene
fecha y fuente. Un número convertido guardado en la base es un número
que nadie puede volver a verificar dentro de seis meses.

---

## Lo que haría ya, aunque lo demás espere

Un candado. **Que no se pueda autorizar una cotización en moneda
distinta a la local del país sin tipo de cambio.**

Son pocas líneas y no depende de ninguna decisión tuya ni de tu
contador. Lo que hace es que el hueco no se llene en silencio mientras
resolvemos el resto: hoy, si alguien carga un tarifario en dólares, el
sistema lo acepta feliz y empieza a producir márgenes falsos que se ven
normales.

Prefiero que reviente al guardar y no que mienta durante seis meses.

---

## Las dudas que necesito que resuelvas

1. **¿Qué fecha manda?** Si la cotización se autoriza en agosto, se
   factura en septiembre y se cobra en octubre, son tres tipos de cambio
   distintos. Los tres son defendibles y cada uno da un número distinto.
   **Esta es de tu contador, no mía** — yo no soy contador; él la define
   y yo la programo.

2. **¿El consolidado de dirección en qué moneda?** Supongo que dólares,
   porque es la única que sirve para comparar México con Brasil. Dime si
   lo ves distinto.

3. **¿Algún costo puede venir en dólares alguna vez?** Una camioneta
   rentada que la arrendadora factura en dólares, un freelance que cobra
   en dólares. Hoy el sistema asume que **todo** el costo es local. Si
   eso llegara a pasar, el problema es bastante más grande que esta
   propuesta y prefiero saberlo ahora.

4. **¿Cuándo entra Odoo de verdad?** De eso depende si el tipo de cambio
   se captura a mano mientras tanto —con su rastro— o si esperamos a la
   integración.

---

## Qué habría que construir

**El candado**, primero y aparte: cotización en otra moneda sin tipo de
cambio no se autoriza.

**Un solo módulo que diga cuánto vale un peso**, como `reloj.py` es el
único que dice qué hora es. Nadie más convierte. Ahí viven la tabla de
tipos de cambio por país y por día, y las dos preguntas de arriba
resueltas cada una con el suyo.

**`rentabilidad()` convirtiendo**, con el tipo de cambio de la
cotización, y devolviendo las dos monedas: la del cliente y la local. El
consultor tiene que ver las dos, porque cobra en una y paga en la otra.

**El consolidado de dirección**, que es una pantalla que no existe: la
utilidad del mes por país y en total, con su fecha de conversión a la
vista.

**Pruebas.** Que un servicio cotizado en dólares con costo en pesos dé
el margen correcto y no −1,500%; que el margen de un servicio cerrado no
cambie aunque cambie el dólar; que el consolidado diga con qué fecha
convirtió; y que una cotización en otra moneda sin tipo de cambio no se
pueda autorizar.

---

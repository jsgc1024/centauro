# Lo que Centauro necesita de Odoo

**Para:** quien administra Odoo
**De:** Centauro · sistema de operación
**Fecha:** 20 de septiembre de 2026

Odoo es la fuente de verdad de **empleados y flota**. El sistema de
operación no los captura a mano: los recibe de Odoo y los guarda para
poder trabajar aunque Odoo no responda en ese momento.

Hoy llegan **tres datos del empleado** —nombre, teléfono y fotografía— y
**cuatro de la unidad** —marca y modelo, color, año y fotografía—. Con
eso no alcanza. Este documento dice exactamente qué falta, por qué, y en
qué formato.

**Lo que pedimos de vuelta:** una respuesta a cada punto numerado. Con
"sí" o "no" basta; donde diga *formato*, el nombre exacto del campo en
Odoo.

---

## 1. La conexión

**1.1 ¿Odoo puede llamar a una dirección nuestra, o tenemos que ir
nosotros por los datos?**
Hoy el sistema expone tres direcciones que Odoo llamaría cuando algo
cambie (`/odoo/personal`, `/odoo/flota`, `/odoo/taller`). Si Odoo no
puede hacer llamadas salientes, lo hacemos al revés y **necesitamos**:
la URL del servidor, el nombre de la base de datos, y un usuario de
**solo lectura** con su API key.

**1.2 ¿Cada cuánto?**
Nuestra propuesta: empleados y flota **una vez al día y cuando haya un
cambio**; el taller **cada hora**, porque una unidad que entra a taller
hoy afecta el servicio de mañana.

**1.3 ¿Quién es el responsable técnico del lado de Odoo?**
Nombre y correo, para cuando algo deje de llegar.

**1.4 ¿Hay ambiente de pruebas?**
No queremos probar contra la base real de la empresa.

---

## 2. Empleados — lo que falta

### 2.1 El campo de baja (`active`) — **es el más importante**

Hoy no llega. Recursos humanos da de baja a alguien en Odoo y **en
Centauro su cuenta sigue viva**: puede entrar al sistema, aparecer en la
lista de quién está disponible y ser asignado a un servicio.

*Formato:* `active` (verdadero/falso) de `hr.employee`. Si manejan
estados distintos —baja, incapacidad, vacaciones—, díganlo: no es lo
mismo alguien que ya no trabaja aquí que alguien que volverá el lunes.

*Qué haremos con él:* baja en Odoo = acceso cerrado en Centauro el mismo
día, y queda escrito quién y cuándo.

### 2.2 El identificador del empleado (`id`)

Hoy la llave es **el correo**. Si alguien cambia de correo, para el
sistema es otra persona: pierde su historial, sus servicios y sus horas.

*Formato:* el `id` numérico de `hr.employee`, en cada envío.

### 2.3 ¿Todos los empleados tienen correo?

**Pregunta crítica.** Los conductores y agentes entran a la app de campo
con su correo. Si el personal operativo no tiene correo en Odoo,
necesitamos saberlo hoy: cambia cómo entran al sistema.

*Formato:* ¿`work_email` está lleno para el personal operativo? ¿Es
único por persona?

### 2.4 La sede o ciudad de cada empleado

El sistema trabaja por plaza: quién está disponible en Ciudad de México
no sirve para un servicio en Monterrey.

*Formato:* el campo que tenga la sede (`work_location`, departamento, o
el que usen) y **la lista completa de valores posibles**, para
emparejarla con nuestras plazas.

### 2.5 El puesto

Para saber quién es conductor de seguridad, agente de protección o
coordinador.

*Formato:* `job_id` o el campo que usen, **con su lista de valores**.

### 2.6 La fecha de ingreso

Es la antigüedad. El task sheet le enseña al cliente cuánto lleva en
Centauro la persona que va a cuidar a su ejecutivo.

*Formato:* fecha de alta del empleado.

### 2.7 Cursos y certificaciones — ¿están en Odoo?

El task sheet los muestra: manejo defensivo, primeros auxilios, la
licencia. Hoy se capturan a mano en Centauro.

**Resuelto el 20 de septiembre: Odoo los manda.** El endpoint ya está
listo y esperando: `POST /odoo/capacitaciones`, un arreglo de objetos.

```json
[
  {
    "correo": "juan.ramirez@centauro.lat",
    "nombre": "Manejo defensivo",
    "institucion": "ANSI Capacitación",
    "obtenida_en": "2025-03-14",
    "vigencia_hasta": "2027-03-14"
  }
]
```

| Campo | Obligatorio | Nota |
|---|---|---|
| `correo` | sí | es la llave del empleado, igual que en `/odoo/personal` |
| `nombre` | sí | el nombre del curso; junto con el correo es la llave |
| `institucion` | no | quién lo impartió |
| `obtenida_en` | no | `AAAA-MM-DD` |
| `vigencia_hasta` | no | `AAAA-MM-DD`. **Vacío = permanente** |
| `activo` | no | `false` retira un curso |

**Por qué `vigencia_hasta` es el campo que más importa.** De ahí sale
ahora si la persona está al corriente: el criterio de capacitación del
bono y la dimensión de la calificación lo leen del padrón, no de una
casilla que alguien marca cada mes. Y de ahí salen los avisos de
certificado por vencer, a los 30 días y el día que vence.

**Revalidar no crea un renglón nuevo.** La llave es correo + nombre del
curso: cuando alguien revalida su manejo defensivo, se le mueve la
vigencia al mismo renglón. Así el padrón dice cuántos cursos tiene, no
cuántas veces los ha tomado.

**Un envío parcial no da de baja nada.** Lo que no viene no borra lo que
hay. Para retirar un curso hay que mandarlo con `activo: false`.

**Mientras no llegue la primera carga**, el criterio de capacitación
**no aplica** en vez de reprobar: nadie pierde un peso por un padrón
vacío. Se enciende solo con el primer envío, sin tocar código.

---

## 3. Flota — lo que falta

### 3.1 La baja de la unidad (`active`)

Misma historia que el empleado: una camioneta vendida o siniestrada
sigue ofreciéndose para asignar.

*Formato:* `active` de `fleet.vehicle`.

### 3.2 La placa, tal como está escrita

Es nuestra llave. Necesitamos saber si vienen con guiones, espacios o
mezcladas: `CTR-2211`, `CTR 2211`, `ctr2211`.

### 3.3 Marca, modelo y si es blindada

El cliente pide "SUV blindada" y el sistema tiene que saber cuáles lo
son. Hoy el blindaje se captura a mano.

La marca y el modelo **ya los recibimos** —`marca_modelo`, junto con el
color, el año y la fotografía—. Lo que falta de este punto es el
blindaje.

*Formato:* el campo que diga el blindaje, si existe.

### 3.4 La ciudad donde está la unidad

Igual que el empleado: una unidad en Guadalajara no cubre un servicio en
Cancún.

---

## 4. Taller

El sistema ya recibe las unidades fuera de circulación. Falta saber de
dónde salen para conectarlo:

**4.1** ¿De qué módulo? (`fleet.vehicle.log.services`, mantenimiento, u
otro.)

**4.2** ¿Cómo distinguen **preventivo** de **correctivo**? El sistema
los separa porque uno se programa y el otro no.

**4.3** ¿Traen **fecha estimada de salida**? Sin ella el sistema asume
que la unidad sigue adentro, y deja de ofrecerla indefinidamente.

---

## 5. Pagos y viáticos

El dinero de los viáticos sale del banco y se registra en Odoo. Hoy
alguien captura a mano en Centauro la referencia del depósito.

**5.1** ¿Odoo puede mandarnos la **confirmación del depósito**
—referencia y fecha— cuando se ejecuta?

**5.2** ¿Con qué dato la amarramos? El sistema manda una solicitud de
transferencia con su número; necesitamos que ese número vuelva en la
confirmación.

---

## 5b. El acuerdo autorizado — **lo que arranca todo**

_Decisión de Salvador, 20 de septiembre: la cotización se hace y se
autoriza en Odoo. Cuando llega a Centauro ya viene autorizada._

Hoy el sistema tiene su propio módulo de cotización, y eso significa que
alguien teclea aquí un precio que el cliente ya aprobó allá. Peor: si
nadie lo teclea, **el servicio no se puede cerrar** —el comparativo del
cierre contesta "el servicio no tiene cotización autorizada"— y de esa
comparación salen las desviaciones, la rentabilidad y la comisión del
consultor.

La solución es que el acuerdo entre por la misma puerta que el personal
y la flota.

```
POST /odoo/acuerdos
[
  {
    "folio_odoo": "COT-8841",
    "cliente": "Grupo Salinas",
    "solicitante_correo": "paola.rueda@gruposalinas.com",
    "ejecutivo": "Ing. Alejandro Mena",
    "moneda": "MXN",
    "viaticos_incluidos": false,
    "autorizada_en": "2026-10-02",
    "autorizada_por": "Lic. Paola Rueda",
    "lineas": [
      { "fecha": "2026-10-07", "tipo": "recurso",
        "perfil": "escolta", "cantidad": 2,
        "precio_unitario": "4900.00" },
      { "fecha": "2026-10-07", "tipo": "vehiculo",
        "categoria": "suv_blindada", "cantidad": 1,
        "precio_unitario": "6200.00" }
    ]
  }
]
```

| Campo | Obligatorio | Nota |
|---|---|---|
| `folio_odoo` | sí | la llave. Único: es lo que impide cargar el mismo acuerdo dos veces |
| `cliente` | sí | debe existir en el catálogo |
| `moneda` | sí | MXN, BRL, USD, VES |
| `viaticos_incluidos` | sí | **cambia qué es facturable** (ver abajo) |
| `lineas[].fecha` | sí | un renglón por día |
| `lineas[].tipo` | sí | `recurso` o `vehiculo` |
| `lineas[].perfil` / `categoria` | sí | según el tipo. Debe existir en el catálogo |
| `lineas[].cantidad` | sí | cuántos de ese perfil ese día |
| `lineas[].precio_unitario` | sí | lo que se le cobra al cliente |

**Qué pasa al recibirlo.** El servicio **nace en Centauro** ya
**autorizado**, con su cliente, su ejecutivo y su línea base cargada. El
consultor lo abre y arma el equipo; nadie vuelve a capturar el
encabezado ni el precio.

**El estatus `cotizado` no existe en Centauro.** Entre "se cotizó" y "el
cliente autorizó" todo pasa en Odoo, y aquí no hay nada que mostrar en
ese rato. El catálogo conserva el valor por si algún día la cotización
vuelve a vivir aquí, pero ningún proceso lo escribe.

**Por qué el renglón por día y por perfil, y no el total.** El
comparativo del cierre no compara totales: compara renglón contra
renglón. Así detecta un día de más, o que el escolta cotizado salió como
coordinador. Con solo el total, el cierre únicamente puede decir si
costó más o menos de lo vendido, y las desviaciones dejan de existir.

**Por qué `viaticos_incluidos` importa tanto.** Si van incluidos, el
cliente ya los pagó dentro de la tarifa y lo comprobado **no se le
vuelve a cobrar**: la diferencia la absorbe Centauro. Si van aparte, se
le factura lo comprobado. Son dos negocios distintos sobre el mismo
servicio, y el campo es lo único que los separa.

**Si un catálogo no coincide** —un perfil o una categoría que aquí no
existe— el acuerdo se rechaza diciendo cuál, y no se crea a medias. Un
servicio con la línea base incompleta es peor que uno que no entró: el
cierre compararía contra algo que no es.

## 6. Lo que **no** les estamos pidiendo

Para que quede claro el alcance y nadie prepare de más:

- Clientes, cotizaciones, contratos y facturación.
- Los servicios, su programación y su cierre.
- La nómina del personal de seguridad y sus comisiones.
- Los viáticos en sí (solo la confirmación del depósito, punto 5).

Todo eso vive en Centauro y seguirá viviendo ahí.

---

## 7. Las cinco respuestas que desbloquean el trabajo

Si solo hay tiempo para contestar cinco cosas, que sean éstas:

1. **¿Pueden mandar `active` del empleado?** (punto 2.1)
2. **¿El personal operativo tiene correo en Odoo?** (punto 2.3)
3. **¿Odoo llama a nuestra dirección, o vamos nosotros por los datos?**
   (punto 1.1)
4. **¿Qué campo tiene la sede o ciudad, y cuáles son sus valores?**
   (punto 2.4)
5. **¿Pueden mandar el `id` del empleado, además del correo?**
   (punto 2.2)

Con esas cinco arrancamos. El resto se puede ir conectando después.

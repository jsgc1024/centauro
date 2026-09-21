import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

ANCLA = "## 14. Lo que falta"
NUEVO = """## 15. Accesos: abrir y cerrar la puerta

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

### Lo que un humano todavía entrega a mano

El sistema no sabe mandar un correo que no cuelgue de un servicio:
`Notificacion.servicio_id` es obligatorio. Es el mismo patrón que la
bitácora, y ya van tres veces.

Mientras eso no exista, el enlace de recuperación lo entrega
administración desde un endpoint auditado, igual que el código de campo
lo dicta el consultor. Un humano entrega la llave hasta que exista el
canal.

---

## 14. Lo que falta"""
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("BITACORA.md: seccion 15, accesos")

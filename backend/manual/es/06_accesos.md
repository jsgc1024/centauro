---
id: accesos
parte: entender
orden: 60
titulo: Accesos, roles y puestos
resumen: Quién entra, con qué, y qué puede hacer. Los candados que cuidan los accesos, la invitación, la recuperación de contraseña, el código del personal de campo y la entrada con huella o cara.
buscar: acceso rol puesto categoria llave maestra administracion direccion general permiso de mas actividades pantallas invitacion enlace copiar reenviar contraseña recuperar codigo cuatro digitos sesion baja huella cara touch id pin llave de acceso
---
## Rol y puesto
Hay nueve roles: personal de seguridad, central, consultor, dirección de operaciones, dirección general, finanzas, recursos humanos, sistema y calidad, y administración —la **llave maestra**—.

El **puesto** manda sobre el rol: dice con qué rol entra quien lo trae, qué pantallas le salen en el menú y qué puede hacer en ellas. Sin puesto, cada quien entra con lo de su rol. Dirección general y administración entran con su rol, sin puesto.

Cuando el sistema decide si alguien puede hacer algo, pregunta en este orden:
1. **Administración pasa siempre**: si no, un error de configuración dejaría a la empresa sin poder arreglarla.
2. **Un permiso de más** que le dieron a esa persona. Solo da, nunca quita.
3. **Su puesto**, si tiene.
4. **Su rol**, si no tiene puesto. Dirección general alcanza además todo lo de operaciones, consultor, central, finanzas, recursos humanos y administración.

Cuando alguien no puede, el mensaje dice quién sí: con puesto, qué puestos lo traen; sin puesto, qué roles. La lista completa está en [quién puede qué](#/manual/permisos).

## Los candados de Accesos
Dan y cierran accesos administración, dirección general, recursos humanos y sistema y calidad, en [Accesos](#/accesos). Y hay cosas que el sistema no deja hacer, a propósito:
- **Nadie se da accesos a sí mismo** ni cambia su propio puesto: se lo pide a otro. El puesto propio lo cambia dirección general, y queda en la bitácora.
- **El poder de repartir accesos solo lo da dirección general.**
- **Las dos manos**: lo que pide o aprueba el dinero no convive con lo que lo paga (ver [el dinero](#/manual/leer/dinero)).
- **La llave maestra no se queda sin dueño**: no se le puede quitar a la última persona activa que la tiene, contando a dirección general.
- **El acceso no es la puerta de atrás de una baja**: a quien está dado de baja no se le abre un acceso; si volvió, primero se le reactiva como empleado.
- **A quien se va debiendo viáticos no se le cierra el acceso** hasta que compruebe; si ya no va a volver, finanzas lo cierra con su ajuste.
- **Al consultor titular de servicios vivos no se le cierra el acceso**: el sistema dice cuántos y cuáles; dirección de operaciones los cambia primero desde cada ficha con «Cambiar titular».

## Cómo entra cada quien
- **La oficina** recibe una **invitación por correo** para crear su contraseña. El enlace vale **72 horas** y sirve una sola vez. Reenviarla manda uno nuevo y apaga el anterior. Si el correo no le llega, dirección general o administración pueden **copiar el enlace** y dárselo en mano; queda escrito quién lo copió.
- **Quien olvidó su contraseña** la recupera desde la entrada, con «¿Olvidaste tu contraseña?». Ese enlace vale **2 horas**. Las dos cosas necesitan el correo encendido.
- **El personal de seguridad** no recibe invitación: pone su contraseña con un **código de cuatro dígitos** que le dicta su consultor —solo a quien trabaja en sus servicios— o la central, desde la pantalla Código. El código vale **10 minutos**. Lo que protege ese camino es que quien lo dicta reconozca la voz de quien llama. El freelance no llega de Odoo: su acceso se abre desde su ficha, en Personal de seguridad → Freelance, cuando su expediente está listo, y de ahí sigue el mismo código.
- **La sesión** dura 12 horas, salvo que el puesto diga otra cosa. Si vence a media pantalla, al volver a entrar se regresa a esa pantalla.
- **Cambiar la propia contraseña** se hace desde adentro, en el menú del nombre: pide la actual, y al guardar la nueva se cierran todas las sesiones, también esa, y se quitan las huellas.
- **Con huella o cara** (sección 110): en un teléfono o una computadora con huella, cara o PIN, al entrar con la contraseña se ofrece una sola vez —«Sí, activar» o «Ahora no», que no vuelve a preguntar en un mes—. Después la entrada saluda por el nombre y basta un botón; «Usar mi contraseña» y «No soy…» quedan a un clic. Vale en la consola y en la app, se activa escribiendo la contraseña, y se ve y se quita en el menú del nombre → «Entrar con huella o cara» (en la app, en «Yo»). La huella no sale del teléfono: el sistema guarda solo una llave que el teléfono crea para Connect. La contraseña sigue sirviendo siempre; cambiarla quita las huellas de todos sus equipos, y se vuelven a activar al entrar con la nueva. **Si le roban o pierde un equipo:** quitarle la huella desde otro equipo no cierra la sesión que ese equipo ya tenía abierta; lo que lo protege es pedir su código y poner contraseña nueva, que cierra las sesiones y las huellas de todos sus equipos. Y si un teléfono restauró un respaldo, su huella queda rechazada: se entra con la contraseña, se quita y se activa otra vez.

> Casi todo atorón de accesos es uno de estos candados haciendo su trabajo. El mensaje dice cuál y qué hacer; si no es claro, está en [cuando el sistema dice que no](#/manual/mensajes), en Accesos y contraseñas.

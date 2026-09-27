---
id: fallas
parte: entender
orden: 80
titulo: Reportar una falla y los casos
resumen: Cómo se reporta una falla desde la consola y desde la app, qué se manda solo, y cómo la revisa sistema y calidad hasta dejarla resuelta.
buscar: reportar falla error bug reporte captura pantallazo caja negra casos por revisar con claude copiar para claude resolver aviso sistema y calidad
---
## Quien la ve, la reporta {#reportar}
En la consola, **Reportar una falla** está arriba, junto a tu nombre, en todas las pantallas. En la app de campo está en **Yo**. Se escribe qué pasó y, si quieres, qué esperabas y una captura —en la consola se pega con Ctrl+V; en la app se agrega una foto—.

Lo demás **se manda solo**, y la consola lo enseña antes de mandarlo: la pantalla y el servicio donde estabas, quién eres, cuándo, la versión del sistema, el navegador o el teléfono, y lo último que te salió en rojo o que contestó el servidor. **Nunca se mandan contraseñas ni la sesión.**

Lo urgente sigue siendo por teléfono: un reporte no es una alerta. En la calle, el botón rojo y la central.

## Le llega a sistema y calidad {#revisar}
Cada reporte llega a [Manual del sistema → Casos](#/manual/casos), en **Por revisar**, y a sistema y calidad le llega el aviso por correo. Si todavía no hay nadie con ese puesto, le llega a administración.

Cada tarjeta dice quién lo reportó, desde dónde, qué pasó, qué esperaba y lo que se mandó solo. Con eso se decide qué es:
- **Si es de datos o de uso** —un punto mal capturado, un paso que faltó—, se arregla y se cierra ahí mismo, con **Resolver**.
- **Si es una falla del sistema**, **Copiar para Claude** deja el reporte en texto, listo para pegarlo en la conversación con Claude. La captura, si la hay, se abre con **Ver la captura** y se pega aparte. El caso queda **con Claude** mientras se arregla.

## Resuelto, se le avisa {#resolver}
Resolver pide lo mismo que un caso anotado a mano: la causa, cómo se arregló y si fue falla del sistema. Al guardarlo, a quien lo reportó le llega el aviso con la causa y cómo se arregló —por correo y, si lo reportó desde la app, también a su teléfono—, y el caso pasa a **Resueltos**, donde se busca junto con los demás.

Si fue falla del sistema, vale la regla de siempre: la que no cambia cómo se trabaja se arregla directo y se avisa; la que pide cambiar un proceso lleva primero su propuesta.

> Nadie reporta diez fallas en una hora: después de diez reportes de la misma persona en una hora, el siguiente ya no se guarda y el sistema dice que llame a la central. Y un reporte ya resuelto no se vuelve a resolver: si hay que cambiar algo, se corrige con **Corregir**.

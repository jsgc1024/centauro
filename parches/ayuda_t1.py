import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

ANCLA = "- Restringir la llave de Google por IP del servidor."
NUEVO = """- **La ayuda en pantalla.** Pedido por Salvador (18 sep): que cada punto
  diga para qué sirve, cuál es su alcance y por qué importa, a un clic.

  **La mitad ya está escrita.** Hay **93 claves `_pie`** en español —279
  renglones con sus traducciones— que ya salen debajo de cada título de
  bloque, más las descripciones de `permisos.py`, escritas a propósito
  pensando en quien las va a leer. El trabajo no es escribir un manual:
  es cosechar lo que hay y hacerlo alcanzable.

  **La regla que define el diseño:** un tutorial que vive aparte de la
  pantalla se despega el día que la pantalla cambia. Es la misma lección
  del umbral de silencio —60 en una pantalla y 120 en la otra— y del
  tope del mes escrito lejos de su candado. La ayuda vive donde vive la
  cosa que explica, en `idioma.js`, con las demás claves, para que
  `revisar.py` la barra igual.

  Tres capas, de la más barata a la más cara:

  1. **El pie que ya existe**, revisado con ojo de quien nunca usó el
     sistema. Algunos dicen *qué* es y no *para qué* sirve.
  2. **Un `?` por bloque**, junto al título. Tres cosas: para qué sirve,
     qué pasa si no lo haces, y de dónde sale el número.
  3. **El recorrido de la primera vez**, solo para el que entra nuevo y
     solo una vez, repetible desde el `?`.

  **Lo que lo haría valioso de verdad:** este código está lleno de *por
  qué*, no de *qué* —"el dinero que ya salió no se mueve con la
  persona", "quien no marca su llegada no se paga"—. Eso es lo que hace
  que un consultor confíe en el sistema en vez de pelearse con él.
  Cuando el sistema le dice que no, la diferencia entre obedecer a
  regañadientes y entender está en una frase.

  **El personal de campo necesita otra cosa:** están en un teléfono, a
  las seis de la mañana, con una mano. Ahí no cabe un recorrido; ahí
  sirve que cada pantalla diga en un renglón qué se espera de ellos
  ahora.
- Restringir la llave de Google por IP del servidor."""
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("BITACORA.md: la ayuda en pantalla, registrada")

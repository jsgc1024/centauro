/* La firma de las dos puertas y de la barra de la consola: CONNECT
   --CONNECT APP en la app de campo-- y debajo el lema, HIGH
   PERFORMANCE, del mismo largo que la palabra (Salvador, 26 sep).

   Cada letra del lema va en su propia caja y las cajas se reparten el
   ancho de la palabra: asi el lema mide lo mismo que ella en cualquier
   pantalla y con la letra que haya cargado, sin medir nada con
   JavaScript. El espacio es una caja mas --duro, para que el navegador
   no se lo coma--, y por eso entre HIGH y PERFORMANCE queda un poco mas
   de aire que entre dos letras.

   No depende de nada: lo usan la consola y la app de campo, y la app lo
   guarda en su armazon para abrir sin senal. La clase no se llama
   "firma": en la app esa es la del lienzo donde se firma. */
export function firma(palabra, lema) {
  const caja = document.createElement("span");
  caja.className = "marca-connect";

  const arriba = document.createElement("span");
  arriba.className = "palabra";
  arriba.textContent = palabra;

  /* Letra por letra, un lector de pantalla lo deletrearia: se lee
     completo, como lo que es. */
  const abajo = document.createElement("span");
  abajo.className = "lema";
  abajo.setAttribute("role", "img");
  abajo.setAttribute("aria-label", lema);
  for (const letra of lema) {
    const l = document.createElement("span");
    l.textContent = letra === " " ? " " : letra;
    abajo.append(l);
  }

  caja.append(arriba, abajo);
  return caja;
}

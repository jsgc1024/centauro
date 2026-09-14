/* La foto del ticket, lista para subir con media barra de senal.

   Un telefono saca fotos de cuatro o cinco megas. Subir eso desde una
   gasolinera no termina nunca, y el servidor las rechaza. Aqui se
   reducen antes de salir: mil seiscientos pixeles del lado largo y JPEG
   al setenta por ciento dejan un ticket perfectamente legible en unos
   trescientos kilobytes.

   Se hace en el telefono y no en el servidor a proposito: lo que no se
   sube, no se espera. */

const LADO_MAXIMO = 1600;
const CALIDAD = 0.7;

export function reducir(archivo) {
  return new Promise((listo, falla) => {
    const lector = new FileReader();
    lector.onerror = () => falla(new Error("No se pudo leer la foto"));
    lector.onload = () => {
      const img = new Image();
      img.onerror = () => falla(new Error("Esa imagen no se puede abrir"));
      img.onload = () => {
        const escala = Math.min(1, LADO_MAXIMO / Math.max(img.width,
                                                          img.height));
        const lienzo = document.createElement("canvas");
        lienzo.width = Math.round(img.width * escala);
        lienzo.height = Math.round(img.height * escala);
        lienzo.getContext("2d").drawImage(img, 0, 0, lienzo.width,
                                          lienzo.height);
        listo(lienzo.toDataURL("image/jpeg", CALIDAD));
      };
      img.src = lector.result;
    };
    lector.readAsDataURL(archivo);
  });
}

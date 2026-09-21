"""Paso 3e: el otro extremo, la pantalla de la app.

La app de campo no tiene idiomas propios --el personal opera en su
pais-- asi que los textos van en espanol, como el resto de esa app.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/campo/app.js"
s = R.read_text()

VIEJO = '''  raiz().replaceChildren(h("div", { clase: "entrada" },
    h("h1", {}, "Centauro"),
    h("p", { clase: "gris" }, "Protección ejecutiva"),
    h("div", { clase: "caja", style: "margin-top:22px" },
      error,
      h("div", { clase: "campo" }, h("label", {}, "Correo"), correo),
      h("div", { clase: "campo" }, h("label", {}, "Contraseña"), clave),
      boton)));
}'''

NUEVO = '''  raiz().replaceChildren(h("div", { clase: "entrada" },
    h("h1", {}, "Centauro"),
    h("p", { clase: "gris" }, "Protección ejecutiva"),
    h("div", { clase: "caja", style: "margin-top:22px" },
      error,
      h("div", { clase: "campo" }, h("label", {}, "Correo"), correo),
      h("div", { clase: "campo" }, h("label", {}, "Contraseña"), clave),
      boton,
      /* Tu contraseña no va por correo: el correo es tuyo y la empresa
         no lo controla. Va por tu consultor, que te reconoce la voz. */
      h("button", { clase: "claro", style: "margin-top:10px",
        onclick: () => conCodigo(correo.value.trim()) },
        "Olvidé mi contraseña"))));
}

/* El agente llamó a su consultor --o a la central-- y le dictaron cuatro
   dígitos por teléfono. Aquí los escribe y pone su contraseña.

   Cuatro y no seis porque se dictan en voz alta a las seis de la mañana.
   El candado no está aquí sino en el servidor: cinco fallos y el código
   se muere. */
function conCodigo(correoPrevio) {
  const correo = h("input", { type: "email", inputmode: "email",
                              autocapitalize: "none", value: correoPrevio || "",
                              autocomplete: "username" });
  const codigo = h("input", { type: "text", inputmode: "numeric",
                              maxlength: "4", autocomplete: "one-time-code",
                              placeholder: "0000" });
  const clave = h("input", { type: "password",
                             autocomplete: "new-password" });
  const error = h("div");
  const boton = h("button", { onclick: () => guardar() }, "Guardar y entrar");

  async function guardar() {
    boton.disabled = true;
    error.replaceChildren();
    try {
      await api.post("/auth/campo/contrasena", {
        correo: correo.value.trim(),
        codigo: codigo.value.trim(),
        contrasena: clave.value,
      });
      /* Se entra de corrido con la que acaba de poner: a las 5:40 nadie
         quiere escribirla dos veces. */
      await api.entrar(correo.value.trim(), clave.value);
      await api.quienSoy();
      location.hash = "#/hoy";
      pintar();
    } catch (err) {
      error.replaceChildren(aviso(err.message, "grave"));
      boton.disabled = false;
    }
  }

  raiz().replaceChildren(h("div", { clase: "entrada" },
    h("h1", {}, "Centauro"),
    h("p", { clase: "gris" }, "Pídele el código a tu consultor"),
    h("div", { clase: "caja", style: "margin-top:22px" },
      error,
      h("div", { clase: "campo" }, h("label", {}, "Correo"), correo),
      h("div", { clase: "campo" },
        h("label", {}, "Código de 4 dígitos"), codigo),
      h("div", { clase: "campo" },
        h("label", {}, "Tu contraseña nueva"), clave),
      boton,
      h("button", { clase: "claro", style: "margin-top:10px",
        onclick: () => entrada() }, "Regresar"))));
}'''

assert s.count(VIEJO) == 1, "no encontre la pantalla de entrada"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("campo/app.js: la pantalla del codigo")

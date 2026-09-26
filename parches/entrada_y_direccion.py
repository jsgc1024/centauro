# -*- coding: utf-8 -*-
"""La puerta: el nombre de la app y su direccion (seccion 70).

Decision de Salvador, 26 de septiembre:

- La entrada --de la consola y de la app de campo, con las pantallas de
  crear y recuperar la contrasena y la del codigo de cuatro digitos--
  lleva debajo de la marca de Centauro el nombre de la app, PROTECCION
  EJECUTIVA / CONNECT APP, sobre el navy de la casa. La pestana del
  navegador dice el nombre.
- La app vive en appep.mycentauro.lat y mycentauro.lat sola manda a ella
  (302, con la ruta completa). El Caddyfile contesta en DOMINIO y en
  DOMINIO_RAIZ; docker-compose.prod.yml le pasa la segunda al proxy.
- La documentacion deja de decir centauro.cc.

Sin migracion. Idempotente. Todo se arma en memoria, se comprueba contra
lo que se probo (md5 por archivo) y solo entonces se escribe.
"""
import hashlib
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ARCHIVOS = {
    'app_js': RAIZ / 'backend/app/web/app.js',
    'contrasena': RAIZ / 'backend/app/web/contrasena.js',
    'estilo': RAIZ / 'backend/app/web/estilo.css',
    'idioma': RAIZ / 'backend/app/web/idioma.js',
    'index': RAIZ / 'backend/app/web/index.html',
    'campo_js': RAIZ / 'backend/app/web/campo/app.js',
    'campo_css': RAIZ / 'backend/app/web/campo/estilo.css',
    'sw': RAIZ / 'backend/app/web/campo/sw.js',
    'config': RAIZ / 'backend/app/config.py',
    'caddy': RAIZ / 'despliegue/Caddyfile',
    'compose': RAIZ / 'docker-compose.prod.yml',
    'leeme': RAIZ / 'despliegue/LEEME.md',
    'crear_env': RAIZ / 'despliegue/crear_env.py',
    'bitacora': RAIZ / 'BITACORA.md',
}
NUEVOS = {}
ESPERADO = {'app_js': '38e7cbf3a3c04831c500ca23220ecea5', 'contrasena': 'e512224d75b7d65f46dc10697c87ea4b', 'estilo': '60e379fc631aeb21cd1753d90e4c8f36', 'idioma': 'bc64b24d3b700cc3256f4f25b00c25ef', 'index': '238a872bc84bf67e2d7f206d6ea0e74e', 'campo_js': '522a983caeff4a15bec49cb4c1cf1e60', 'campo_css': 'ef2f814f73cd230bdce7c964b734adf4', 'sw': '2c7986e14806f8a2612461639a662ef7', 'config': '0dd8b136ad7fef3781378180430830f5', 'caddy': 'bb351f635eb19bfee9066c602b04f901', 'compose': '9090f719304a17e9efeab511eaab3150', 'leeme': '315d8419cd082e5dfbd5fe05b1795dbf', 'crear_env': 'f60f028c973c9620e95bb9b5eb9a49fd', 'bitacora': '0bb02a6afa14271ce1702f4e8bd64969'}

textos = {k: io.open(v, encoding="utf-8", newline="").read()
          for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(clave)
        return
    assert t.count(viejo) == 1, (
        f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces. "
        "No se escribio nada.")
    textos[clave] = t.replace(viejo, nuevo)


cambiar('app_js',
        '                          font-size:${Math.round(alto / 3)}px` }, "CENTAURO");\n}\n\n/* ------------------------------------------------------------ entrada */\n\n/* El correo con que se llega de las pantallas de antes de entrar: quien\n',
        '                          font-size:${Math.round(alto / 3)}px` }, "CENTAURO");\n}\n\n/* La portada de las pantallas de antes de entrar: arriba la marca de la\n   empresa y debajo el nombre de la app, Proteccion Ejecutiva Connect\n   App. Lo pidio Salvador el 26 de septiembre de 2026: vienen mas apps,\n   una por area de la empresa, y quien llega tiene que saber en un\n   segundo a cual entro. El nombre no se traduce --es un nombre--; la\n   linea de abajo de la tarjeta, si. */\nfunction portada() {\n  return h("div", { clase: "portada" },\n    marca(54),\n    h("div", { clase: "app-nombre" }, t("app_nombre")),\n    h("div", { clase: "app-sello" }, h("span", {}, t("app_sello"))));\n}\n\n/* La tarjeta va sobre el fondo navy de la puerta, con su pie afuera. */\nfunction puerta(tarjeta) {\n  return h("div", { clase: "entrada" },\n    h("div", { clase: "hoja-entrada" },\n      tarjeta,\n      h("p", { clase: "pie-entrada" }, t("entrada_pie"))));\n}\n\n/* ------------------------------------------------------------ entrada */\n\n/* El correo con que se llega de las pantallas de antes de entrar: quien\n')

cambiar('app_js',
        '  }});\n\n  f.append(\n    marca(62),\n    sello(),\n    campo(t("correo"), correo),\n    campo(t("contrasena"), entrada("contrasena", { type: "password", required: "true",\n                                                  autocomplete: "current-password" })),\n',
        '  }});\n\n  f.append(\n    portada(),\n    campo(t("correo"), correo),\n    campo(t("contrasena"), entrada("contrasena", { type: "password", required: "true",\n                                                  autocomplete: "current-password" })),\n')

cambiar('app_js',
        '        location.hash = "#/olvide";\n      } }, t("cc_olvide"))));\n\n  cuerpo.append(h("div", { clase: "entrada" }, f));\n}\n\n/* Lo que se abre sin haber entrado: el enlace del correo para crear la\n',
        '        location.hash = "#/olvide";\n      } }, t("cc_olvide"))));\n\n  cuerpo.append(puerta(f));\n}\n\n/* Lo que se abre sin haber entrado: el enlace del correo para crear la\n')

cambiar('app_js',
        '   camino de vuelta a la entrada, con el correo ya escrito. */\nfunction deAfuera() {\n  const op = {\n    cabecera: () => [marca(62), sello()],\n    correo: correoSugerido,\n    irAEntrada: (correo = "", cerrarSesion = false) => {\n      correoSugerido = correo;\n',
        '   camino de vuelta a la entrada, con el correo ya escrito. */\nfunction deAfuera() {\n  const op = {\n    cabecera: () => [portada()],\n    puerta,\n    correo: correoSugerido,\n    irAEntrada: (correo = "", cerrarSesion = false) => {\n      correoSugerido = correo;\n')

cambiar('contrasena',
        'import { nombreDelRol } from "./categorias.js";\n\n/* La tarjeta de la entrada, con lo que toque adentro. `op` la da el\n   armazón: la marca de arriba y el camino de vuelta a la entrada. */\nfunction tarjeta(cuerpo, op, ...hijos) {\n  const f = h("form", { onsubmit: (e) => e.preventDefault() },\n              ...op.cabecera(), ...hijos);\n  cuerpo.replaceChildren(h("div", { clase: "entrada" }, f));\n  return f;\n}\n\n',
        'import { nombreDelRol } from "./categorias.js";\n\n/* La tarjeta de la entrada, con lo que toque adentro. `op` la da el\n   armazón: la marca de arriba, el fondo de la puerta y el camino de\n   vuelta a la entrada. */\nfunction tarjeta(cuerpo, op, ...hijos) {\n  const f = h("form", { onsubmit: (e) => e.preventDefault() },\n              ...op.cabecera(), ...hijos);\n  cuerpo.replaceChildren(op.puerta(f));\n  return f;\n}\n\n')

cambiar('estilo',
        '  font-size: 10.5px; text-transform: uppercase; letter-spacing: 1.1px;\n  color: var(--gris); font-weight: 650;\n}\n.entrada .linea { justify-content: center; margin: -10px 0 22px; }\n/* El menu, en su propio renglon y con el renglon entero para el. Es lo\n   unico de aqui arriba que se usa todo el dia; lo demas --quien eres, en\n   que idioma, la salida-- vive recogido en la pastilla de la derecha. */\n',
        '  font-size: 10.5px; text-transform: uppercase; letter-spacing: 1.1px;\n  color: var(--gris); font-weight: 650;\n}\n/* El menu, en su propio renglon y con el renglon entero para el. Es lo\n   unico de aqui arriba que se usa todo el dia; lo demas --quien eres, en\n   que idioma, la salida-- vive recogido en la pastilla de la derecha. */\n')

cambiar('estilo',
        '.vacio { color: var(--gris); padding: 26px; text-align: center; }\n\n/* ---------------------------------------------------------- entrada */\n.entrada {\n  min-height: 100vh; display: grid; place-items: center; padding: 20px;\n}\n.entrada form {\n  background: #fff; border: 1px solid var(--linea); border-radius: 10px;\n  padding: 30px; width: 100%; max-width: 380px;\n}\n.entrada img { height: 62px; display: block; margin: 0 auto 22px; }\n.entrada button { width: 100%; margin-top: 6px; }\n/* Las pantallas de antes de entrar --crear la contrasena, pedir el\n   enlace-- viven en la misma tarjeta, con su titulo y su texto. */\n',
        '.vacio { color: var(--gris); padding: 26px; text-align: center; }\n\n/* ---------------------------------------------------------- entrada */\n/* La puerta de la app: el navy de la casa con una luz detras de la tarjeta,\n   y ahi la tarjeta blanca. El logo es navy y sobre oscuro se\n   pierde (assets/LEEME.txt), por eso vive adentro de la tarjeta. El\n   fondo va tambien en el body para que el rebote del telefono al\n   recorrer no ensene el gris de las demas pantallas. */\nbody:has(.entrada) { background: #120e33; }\n.entrada {\n  min-height: 100vh; display: grid; place-items: center; padding: 32px 16px;\n  background:\n    radial-gradient(760px 520px at 50% 42%, rgba(96, 84, 200, .34), transparent 70%),\n    linear-gradient(165deg, #211a5a 0%, #1B1546 48%, #0f0b2a 100%);\n}\n.hoja-entrada { width: 100%; max-width: 400px; }\n.entrada form {\n  background: #fff; border: 0; border-top: 4px solid #c9a227;\n  border-radius: 14px; padding: 30px 30px 24px;\n  box-shadow: 0 30px 70px rgba(5, 3, 20, .45), 0 2px 6px rgba(5, 3, 20, .25);\n}\n.portada { text-align: center; margin: 0 0 24px; }\n.portada img { display: block; margin: 0 auto; max-width: 100%; object-fit: contain; }\n/* El nombre de la app, debajo de la marca de la empresa y separado de\n   ella: la empresa es Centauro, la app es Proteccion Ejecutiva. */\n.portada .app-nombre {\n  margin-top: 18px; padding: 18px 0 0 2.4px; border-top: 1px solid var(--linea);\n  font-size: 19px; font-weight: 800; letter-spacing: 2.4px; line-height: 1.25;\n  text-transform: uppercase; color: var(--centauro);\n}\n.portada .app-sello {\n  display: flex; align-items: center; justify-content: center; gap: 12px;\n  margin-top: 8px; font-size: 12px; font-weight: 700; letter-spacing: 5px;\n  text-transform: uppercase; color: #8c6f14;\n}\n/* El espaciado de las letras deja aire despues de la ultima: se le\n   quita para que el nombre quede centrado entre sus dos rayas. */\n.portada .app-sello span { margin-right: -5px; }\n.portada .app-sello::before, .portada .app-sello::after {\n  content: ""; width: 34px; height: 1px; background: #c9a227;\n}\n.pie-entrada {\n  margin: 18px 0 0; text-align: center; font-size: 12px; letter-spacing: .3px;\n  color: rgba(255, 255, 255, .62);\n}\n.entrada button { width: 100%; margin-top: 6px; }\n/* Las pantallas de antes de entrar --crear la contrasena, pedir el\n   enlace-- viven en la misma tarjeta, con su titulo y su texto. */\n')

cambiar('idioma',
        '  es: {\n    /* --- barra y acceso */\n    linea: "Protección Ejecutiva",\n    correo: "Correo",\n    contrasena: "Contraseña",\n    entrar: "Entrar",\n',
        '  es: {\n    /* --- barra y acceso */\n    linea: "Protección Ejecutiva",\n    /* El nombre de la app, en la puerta. Es un nombre: no se traduce. */\n    app_nombre: "Protección Ejecutiva",\n    app_sello: "Connect App",\n    entrada_pie: "Acceso exclusivo para personal autorizado",\n    correo: "Correo",\n    contrasena: "Contraseña",\n    entrar: "Entrar",\n')

cambiar('idioma',
        '    nom_tab_guardar: "Guardar {t}",\n    cmp_entrar: "Entrar",\n    cmp_marca: "Centauro",\n    cmp_lema: "Protección ejecutiva",\n    cmp_correo: "Correo",\n    cmp_contrasena: "Contraseña",\n    cmp_olvide: "Olvidé mi contraseña",\n',
        '    nom_tab_guardar: "Guardar {t}",\n    cmp_entrar: "Entrar",\n    cmp_marca: "Centauro",\n    cmp_correo: "Correo",\n    cmp_contrasena: "Contraseña",\n    cmp_olvide: "Olvidé mi contraseña",\n')

cambiar('idioma',
        '\n  en: {\n    linea: "Executive Protection",\n    correo: "Email",\n    contrasena: "Password",\n    entrar: "Sign in",\n',
        '\n  en: {\n    linea: "Executive Protection",\n    app_nombre: "Protección Ejecutiva",\n    app_sello: "Connect App",\n    entrada_pie: "Authorized personnel only",\n    correo: "Email",\n    contrasena: "Password",\n    entrar: "Sign in",\n')

cambiar('idioma',
        '    nom_tab_guardar: "Save {t}",\n    cmp_entrar: "Sign in",\n    cmp_marca: "Centauro",\n    cmp_lema: "Executive protection",\n    cmp_correo: "Email",\n    cmp_contrasena: "Password",\n    cmp_olvide: "I forgot my password",\n',
        '    nom_tab_guardar: "Save {t}",\n    cmp_entrar: "Sign in",\n    cmp_marca: "Centauro",\n    cmp_correo: "Email",\n    cmp_contrasena: "Password",\n    cmp_olvide: "I forgot my password",\n')

cambiar('idioma',
        '\n  pt: {\n    linea: "Proteção Executiva",\n    correo: "E-mail",\n    contrasena: "Senha",\n    entrar: "Entrar",\n',
        '\n  pt: {\n    linea: "Proteção Executiva",\n    app_nombre: "Protección Ejecutiva",\n    app_sello: "Connect App",\n    entrada_pie: "Acesso exclusivo para pessoal autorizado",\n    correo: "E-mail",\n    contrasena: "Senha",\n    entrar: "Entrar",\n')

cambiar('idioma',
        '    nom_tab_guardar: "Salvar {t}",\n    cmp_entrar: "Entrar",\n    cmp_marca: "Centauro",\n    cmp_lema: "Proteção executiva",\n    cmp_correo: "E-mail",\n    cmp_contrasena: "Senha",\n    cmp_olvide: "Esqueci minha senha",\n',
        '    nom_tab_guardar: "Salvar {t}",\n    cmp_entrar: "Entrar",\n    cmp_marca: "Centauro",\n    cmp_correo: "E-mail",\n    cmp_contrasena: "Senha",\n    cmp_olvide: "Esqueci minha senha",\n')

cambiar('index',
        '<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Centauro · AI/EP Proteccion Ejecutiva</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;650;700&display=swap" rel="stylesheet">\n<link rel="stylesheet" href="/consola/estilo.css">\n',
        '<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Protección Ejecutiva Connect App · Centauro</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;650;700&display=swap" rel="stylesheet">\n<link rel="stylesheet" href="/consola/estilo.css">\n')

cambiar('campo_js',
        '    }\n  }\n\n  raiz().replaceChildren(h("div", { clase: "entrada" },\n    /* La marca de verdad si ya se guardo alguna vez; el nombre en texto\n       la primera vez, que es cuando todavia no hay de donde sacarla. */\n    logoEmpresa\n      ? h("img", { clase: "logo-entrada", src: logoEmpresa,\n                   alt: t("cmp_marca") })\n      : h("h1", {}, t("cmp_marca")),\n    h("p", { clase: "gris" }, t("cmp_lema")),\n    h("div", { clase: "caja", style: "margin-top:22px" },\n      error,\n      h("div", { clase: "campo" }, h("label", {}, t("cmp_correo")), correo),\n      h("div", { clase: "campo" }, h("label", {}, t("cmp_contrasena")), clave),\n      boton,\n      /* Tu contraseña no va por correo: el correo es tuyo y la empresa\n         no lo controla. Va por tu consultor, que te reconoce la voz. */\n      h("button", { clase: "claro", style: "margin-top:10px",\n        onclick: () => conCodigo(correo.value.trim()) },\n        t("cmp_olvide")))));\n}\n\n/* El agente llamó a su consultor --o a la central-- y le dictaron cuatro\n',
        '    }\n  }\n\n  raiz().replaceChildren(puerta(\n    error,\n    h("div", { clase: "campo" }, h("label", {}, t("cmp_correo")), correo),\n    h("div", { clase: "campo" }, h("label", {}, t("cmp_contrasena")), clave),\n    boton,\n    /* Tu contraseña no va por correo: el correo es tuyo y la empresa\n       no lo controla. Va por tu consultor, que te reconoce la voz. */\n    h("button", { clase: "claro", style: "margin-top:10px",\n      onclick: () => conCodigo(correo.value.trim()) },\n      t("cmp_olvide"))));\n}\n\n/* La puerta de la app, igual que la de la consola: el navy de la casa y\n   la tarjeta blanca con la marca de la empresa y, debajo, el nombre de\n   la app --Proteccion Ejecutiva Connect App, lo pidio Salvador el 26 de\n   septiembre de 2026--. La marca de verdad si ya se guardo alguna vez;\n   el nombre en texto la primera vez, que es cuando todavia no hay de\n   donde sacarla. */\nfunction puerta(...hijos) {\n  return h("div", { clase: "entrada" },\n    h("div", { clase: "caja" },\n      h("div", { clase: "portada" },\n        logoEmpresa\n          ? h("img", { clase: "logo-entrada", src: logoEmpresa,\n                       alt: t("cmp_marca") })\n          : h("h1", {}, t("cmp_marca")),\n        h("div", { clase: "app-nombre" }, t("app_nombre")),\n        h("div", { clase: "app-sello" }, h("span", {}, t("app_sello")))),\n      ...hijos),\n    h("p", { clase: "pie-entrada" }, t("entrada_pie")));\n}\n\n/* El agente llamó a su consultor --o a la central-- y le dictaron cuatro\n')

cambiar('campo_js',
        '    }\n  }\n\n  raiz().replaceChildren(h("div", { clase: "entrada" },\n    h("h1", {}, t("cmp_marca")),\n    h("p", { clase: "gris" }, t("cmp_pide_codigo")),\n    h("div", { clase: "caja", style: "margin-top:22px" },\n      error,\n      h("div", { clase: "campo" }, h("label", {}, t("cmp_correo")), correo),\n      h("div", { clase: "campo" },\n        h("label", {}, t("cmp_codigo_4")), codigo),\n      h("div", { clase: "campo" },\n        h("label", {}, t("cmp_contrasena_nueva")), clave),\n      boton,\n      h("button", { clase: "claro", style: "margin-top:10px",\n        onclick: () => entrada() }, t("cmp_regresar")))));\n}\n\n/* --------------------------------------------------- la cola arriba */\n',
        '    }\n  }\n\n  raiz().replaceChildren(puerta(\n    h("p", { clase: "gris" }, t("cmp_pide_codigo")),\n    error,\n    h("div", { clase: "campo" }, h("label", {}, t("cmp_correo")), correo),\n    h("div", { clase: "campo" },\n      h("label", {}, t("cmp_codigo_4")), codigo),\n    h("div", { clase: "campo" },\n      h("label", {}, t("cmp_contrasena_nueva")), clave),\n    boton,\n    h("button", { clase: "claro", style: "margin-top:10px",\n      onclick: () => entrada() }, t("cmp_regresar"))));\n}\n\n/* --------------------------------------------------- la cola arriba */\n')

cambiar('campo_js',
        '\nfunction otraCuenta() {\n  const suyo = nombreRol()[sesion.usuario.rol] || sesion.usuario.rol;\n  raiz().replaceChildren(h("div", { clase: "entrada" },\n    h("div", { clase: "linea" },\n      h("span", { clase: "clave" }, "AI/EP"),\n      h("span", { clase: "nombre" }, t("cmp_lema"))),\n    h("div", { clase: "caja principal" },\n      h("h1", {}, t("cmp_otra_cuenta")),\n      h("p", { clase: "gris" },\n        t("cmp_entraste_como")\n          .replace("{nombre}", sesion.usuario.nombre)\n          .replace("{rol}", suyo)),\n      h("p", { clase: "gris chico" },\n        t("cmp_otra_cuenta_pie")),\n      h("button", { style: "margin-top:8px", onclick: () => {\n        if (pendientes().length\n            && !confirm(t("cmp_salir_con_pendientes")\n                          .replace("{n}", pendientes().length))) return;\n        olvidar();\n        limpiar();\n        sesion.token = null; sesion.usuario = null;\n        location.hash = ""; pintar();\n      } }, t("cmp_entrar_otra")),\n      h("a", { href: "/", style: "text-decoration:none" },\n        h("button", { clase: "claro", style: "margin-top:10px" },\n          t("cmp_ir_consola"))))));\n}\n\n\n',
        '\nfunction otraCuenta() {\n  const suyo = nombreRol()[sesion.usuario.rol] || sesion.usuario.rol;\n  raiz().replaceChildren(puerta(\n    h("h2", {}, t("cmp_otra_cuenta")),\n    h("p", { clase: "gris" },\n      t("cmp_entraste_como")\n        .replace("{nombre}", sesion.usuario.nombre)\n        .replace("{rol}", suyo)),\n    h("p", { clase: "gris chico" },\n      t("cmp_otra_cuenta_pie")),\n    h("button", { style: "margin-top:8px", onclick: () => {\n      if (pendientes().length\n          && !confirm(t("cmp_salir_con_pendientes")\n                        .replace("{n}", pendientes().length))) return;\n      olvidar();\n      limpiar();\n      sesion.token = null; sesion.usuario = null;\n      location.hash = ""; pintar();\n    } }, t("cmp_entrar_otra")),\n    h("a", { href: "/", style: "text-decoration:none" },\n      h("button", { clase: "claro", style: "margin-top:10px" },\n        t("cmp_ir_consola")))));\n}\n\n\n')

cambiar('campo_css',
        '\n.vacio { color: var(--gris); text-align: center; padding: 32px 16px; }\n\n.entrada { min-height: 76vh; display: flex; flex-direction: column;\n           justify-content: center; }\n/* La linea de operacion, igual que en la consola y el task sheet. */\n.linea { display: flex; align-items: baseline; gap: 8px;\n         justify-content: center; margin: 0 0 22px; }\n.linea .clave {\n  font-weight: 700; font-size: 13px; letter-spacing: .5px;\n  color: #fff; background: var(--centauro);\n  padding: 3px 9px; border-radius: 5px;\n}\n.linea .nombre {\n  font-size: 10.5px; text-transform: uppercase; letter-spacing: 1.1px;\n  color: var(--gris); font-weight: 650;\n}\n\n.marco { border-top: 1px solid var(--linea); margin-top: 14px;\n',
        '\n.vacio { color: var(--gris); text-align: center; padding: 32px 16px; }\n\n/* La puerta de la app --la entrada, el codigo que dicta el consultor y\n   la cuenta que no es de campo--: el navy de la casa con una luz\n   detras de la tarjeta blanca, igual que la consola. El\n   logo es navy y sobre oscuro se pierde, por eso vive en la tarjeta. */\nbody:has(.entrada) {\n  background-color: #120e33;\n  background-image:\n    radial-gradient(520px 560px at 50% 40%, rgba(96, 84, 200, .34), transparent 70%),\n    linear-gradient(170deg, #211a5a 0%, #1B1546 48%, #0f0b2a 100%);\n  min-height: 100vh;\n}\n/* Lo alto de la pantalla menos el margen de #app, que deja abajo el\n   lugar de la barra: aqui no hay barra y la tarjeta va al centro. */\n.entrada { min-height: calc(100vh - 112px); display: flex; flex-direction: column;\n           justify-content: center; }\n.entrada .caja {\n  border: 0; border-top: 4px solid #c9a227; border-radius: 16px;\n  padding: 26px 20px 20px;\n  box-shadow: 0 24px 60px rgba(5, 3, 20, .45), 0 2px 6px rgba(5, 3, 20, .25);\n}\n.portada { text-align: center; margin: 0 0 22px; }\n.portada h1 { letter-spacing: 3px; text-transform: uppercase; }\n.portada .app-nombre {\n  margin-top: 16px; padding: 16px 0 0 2.2px; border-top: 1px solid var(--linea);\n  font-size: 18px; font-weight: 800; letter-spacing: 2.2px; line-height: 1.25;\n  text-transform: uppercase; color: var(--centauro);\n}\n.portada .app-sello {\n  display: flex; align-items: center; justify-content: center; gap: 12px;\n  margin-top: 8px; font-size: 12px; font-weight: 700; letter-spacing: 5px;\n  text-transform: uppercase; color: #8c6f14;\n}\n.portada .app-sello span { margin-right: -5px; }\n.portada .app-sello::before, .portada .app-sello::after {\n  content: ""; width: 30px; height: 1px; background: #c9a227;\n}\n.pie-entrada {\n  margin: 18px 0 0; text-align: center; font-size: 12px; letter-spacing: .3px;\n  color: rgba(255, 255, 255, .62);\n}\n\n.marco { border-top: 1px solid var(--linea); margin-top: 14px;\n')

cambiar('campo_css',
        '   nunca empuje al boton de salir fuera del renglon. */\n.encabezado .logo.ancho { height: 34px; max-width: 62%; object-fit: contain;\n                          object-position: left center; }\n.logo-entrada { max-width: 76%; max-height: 90px; display: block;\n                margin: 0 auto 6px; object-fit: contain; }\n',
        '   nunca empuje al boton de salir fuera del renglon. */\n.encabezado .logo.ancho { height: 34px; max-width: 62%; object-fit: contain;\n                          object-position: left center; }\n.logo-entrada { max-width: 78%; max-height: 64px; display: block;\n                margin: 0 auto; object-fit: contain; }\n')

cambiar('sw',
        '   activarse, el trabajador nuevo borra los caches con otro nombre. Sin\n   subirla, el telefono que ya tenia la app instalada seguiria sirviendo\n   el armazon viejo del cache. */\nconst CACHE = "centauro-campo-v8";\nconst ARMAZON = [\n  "/app/",\n  "/app/index.html",\n',
        '   activarse, el trabajador nuevo borra los caches con otro nombre. Sin\n   subirla, el telefono que ya tenia la app instalada seguiria sirviendo\n   el armazon viejo del cache. */\nconst CACHE = "centauro-campo-v9";\nconst ARMAZON = [\n  "/app/",\n  "/app/index.html",\n')

cambiar('config',
        '    # De donde cuelgan los enlaces que van dentro de un correo. Sin\n    # esto, el enlace de una encuesta seria "/encuestas/pagina/abc" y no\n    # llevaria a ningun lado fuera del servidor.\n    url_publica: str = ""          # "https://centauro.lat"\n\n    # Odoo, del lado de SALIDA: la factura del servicio aprobado.\n    #\n',
        '    # De donde cuelgan los enlaces que van dentro de un correo. Sin\n    # esto, el enlace de una encuesta seria "/encuestas/pagina/abc" y no\n    # llevaria a ningun lado fuera del servidor.\n    url_publica: str = ""          # "https://appep.mycentauro.lat"\n\n    # Odoo, del lado de SALIDA: la factura del servicio aprobado.\n    #\n')

cambiar('caddy',
        "# —y sin certificado no hay service worker, ni camara, ni ubicacion, ni\n# avisos: la app de campo simplemente no existe.\n#\n# El dominio sale del .env (DOMINIO=operacion.centauro.lat).\n\n{\n\t# A donde escribe Let's Encrypt si un certificado esta por vencer y\n",
        "# —y sin certificado no hay service worker, ni camara, ni ubicacion, ni\n# avisos: la app de campo simplemente no existe.\n#\n# Las direcciones salen del .env: DOMINIO es la de la app\n# (appep.mycentauro.lat) y DOMINIO_RAIZ la de la empresa sola\n# (mycentauro.lat). Seccion 70.\n\n{\n\t# A donde escribe Let's Encrypt si un certificado esta por vencer y\n")

cambiar('caddy',
        '\temail operaciones@centauro.lat\n}\n\n{$DOMINIO} {\n\tencode zstd gzip\n\n\t# La IP real del cliente. Sin esto el registro de auditoria guarda la\n\t# IP del proxy para todos, y el limite de intentos fallidos cuenta a\n',
        '\temail operaciones@centauro.lat\n}\n\n{$DOMINIO} {$DOMINIO_RAIZ} {\n\tencode zstd gzip\n\n\t# mycentauro.lat sola es la puerta de la empresa. Vienen mas apps,\n\t# una por area, y cada una vive en su propia direccion --appep. es\n\t# la de Proteccion Ejecutiva-- para que sus sesiones, su app\n\t# instalada en el telefono y su seguridad no se mezclen con las de\n\t# las otras. Mientras haya una sola, la puerta manda directo a ella\n\t# con la ruta completa: los enlaces que ya salieron con\n\t# mycentauro.lat siguen sirviendo. 302 y no 301: el dia que la\n\t# puerta tenga su pagina con un boton por app, ningun navegador se\n\t# queda con el salto guardado para siempre.\n\t@puerta not host {$DOMINIO}\n\tredir @puerta https://{$DOMINIO}{uri} 302\n\n\t# La IP real del cliente. Sin esto el registro de auditoria guarda la\n\t# IP del proxy para todos, y el limite de intentos fallidos cuenta a\n')

cambiar('compose',
        '    restart: unless-stopped\n    environment:\n      DOMINIO: ${DOMINIO:?falta DOMINIO en .env}\n    ports:\n      - "80:80"\n      - "443:443"\n',
        '    restart: unless-stopped\n    environment:\n      DOMINIO: ${DOMINIO:?falta DOMINIO en .env}\n      # La direccion de la empresa sola, que manda a la app (seccion\n      # 70). Vacia, el proxy solo contesta en DOMINIO.\n      DOMINIO_RAIZ: ${DOMINIO_RAIZ:-}\n    ports:\n      - "80:80"\n      - "443:443"\n')

cambiar('leeme',
        'renglones que puede llevar:\n\n```\nDOMINIO=centauro.cc\nPOSTGRES_PASSWORD=...\nREDIS_PASSWORD=...\nDATABASE_URL=postgresql+psycopg://centauro:LA_DE_ARRIBA@db:5432/centauro\n',
        'renglones que puede llevar:\n\n```\n# La direccion de la app y la de la empresa sola, que manda a la app\n# mientras sea la unica (seccion 70).\nDOMINIO=appep.mycentauro.lat\nDOMINIO_RAIZ=mycentauro.lat\nPOSTGRES_PASSWORD=...\nREDIS_PASSWORD=...\nDATABASE_URL=postgresql+psycopg://centauro:LA_DE_ARRIBA@db:5432/centauro\n')

cambiar('leeme',
        '\n# De donde cuelgan los enlaces que van en correos y task sheets. Es\n# el mismo DOMINIO de arriba.\nURL_PUBLICA=https://centauro.cc\n\n# El correo que sale de la empresa: del buzon de Microsoft 365 (paso 7b).\n# Con los tres CORREO_MS_ llenos manda Microsoft y el SMTP de abajo no se\n',
        '\n# De donde cuelgan los enlaces que van en correos y task sheets. Es\n# el mismo DOMINIO de arriba.\nURL_PUBLICA=https://appep.mycentauro.lat\n\n# El correo que sale de la empresa: del buzon de Microsoft 365 (paso 7b).\n# Con los tres CORREO_MS_ llenos manda Microsoft y el SMTP de abajo no se\n')

cambiar('leeme',
        "Es a propósito: un sistema que enciende igual con o sin secreto se\ndespliega tarde o temprano sin él.\n\n**3. El DNS.** El dominio tiene que apuntar al servidor *antes* de\nlevantar el proxy: Caddy pide el certificado al arrancar y Let's Encrypt\nverifica que el dominio sea tuyo. Para `centauro.cc`: un registro **A**\nhacia `34.51.121.227`.\n\n**4. Levantar, todavía sin la puerta a internet.**\n\n",
        "Es a propósito: un sistema que enciende igual con o sin secreto se\ndespliega tarde o temprano sin él.\n\n**3. El DNS.** Las direcciones tienen que apuntar al servidor *antes*\nde levantar el proxy: Caddy pide el certificado al arrancar y Let's\nEncrypt verifica que el dominio sea tuyo. El dominio es `mycentauro.lat`,\ncomprado en Akky, con el DNS en Google Cloud DNS (zona `mycentauro-lat`;\nen Akky van sus cuatro servidores, `ns-cloud-e1` a `ns-cloud-e4` de\n`googledomains.com`). Dos registros **A** hacia `34.51.121.227`:\n`mycentauro.lat`, la puerta de la empresa, y `appep.mycentauro.lat`,\nesta app (sección 70). La app de otra área, el día que exista, es un\nregistro más y su propio bloque en el `Caddyfile`:\n\n```bash\ngcloud dns record-sets create appXX.mycentauro.lat. --zone=mycentauro-lat --type=A --ttl=300 --rrdatas=34.51.121.227\n```\n\n**4. Levantar, todavía sin la puerta a internet.**\n\n")

cambiar('crear_env',
        '    return f"""# Centauro en produccion. Este archivo no sale del servidor: no va al\n# repositorio, ni a un correo, ni a un chat. Se edita con nano.\n\n# Lo del servidor. Se genero aqui mismo y nadie tiene que saberlo.\nDOMINIO=centauro.cc\nURL_PUBLICA=https://centauro.cc\nAPP_ENV=produccion\nPOSTGRES_PASSWORD={pg}\nREDIS_PASSWORD={rd}\n',
        '    return f"""# Centauro en produccion. Este archivo no sale del servidor: no va al\n# repositorio, ni a un correo, ni a un chat. Se edita con nano.\n\n# La direccion de la app y la de la empresa sola, que manda a la app\n# (seccion 70). URL_PUBLICA es la de la app, con https.\nDOMINIO=appep.mycentauro.lat\nDOMINIO_RAIZ=mycentauro.lat\nURL_PUBLICA=https://appep.mycentauro.lat\n\n# Lo del servidor. Se genero aqui mismo y nadie tiene que saberlo.\nAPP_ENV=produccion\nPOSTGRES_PASSWORD={pg}\nREDIS_PASSWORD={rd}\n')

cambiar('bitacora',
        '  `ARCHIVO_DESTINO` en el `.env` (guía, *El archivo de los comprobantes*).\n- Que el contador confirme el plazo; con eso se sella el candado.\n\n## 14. Lo que falta\n\n### Abierto\n\n- **El servidor: el dominio y el proveedor** (sección 68). Producción ya\n  vive en Google Cloud. Decisión de Salvador (25 sep, noche): en vez de\n  esperar la transferencia de `centauro.cc`, Centauro contrata su propio\n  dominio, a su nombre, en Akky, y el DNS se maneja en Google (Cloud\n  DNS, en el mismo proyecto). Con eso se apunta a `34.51.121.227`, se\n  cambian `DOMINIO` y `URL_PUBLICA` en el `.env` y se abre la puerta\n  (paso 6b de `despliegue/LEEME.md`). Después: apagar el servidor de OVH\n  y dejar de usar la llave de Google Maps del proveedor.\n- **El plazo del archivo de comprobantes** (sección 69): que el contador\n  confirme los seis años; con eso se sella el candado del depósito.\n\n',
        '  `ARCHIVO_DESTINO` en el `.env` (guía, *El archivo de los comprobantes*).\n- Que el contador confirme el plazo; con eso se sella el candado.\n\n## 70. La puerta: el nombre de la app y su dirección\n\nDecisión de Salvador, 26 de septiembre. Las dos cosas son de la entrada.\n\n**El nombre.** La pantalla donde se pone el correo y la contraseña dice\nahora, debajo de la marca de Centauro, el nombre de la app:\n**Protección Ejecutiva Connect App**, «para que se vea más vistoso y\nprofesional». Se le enseñaron las pantallas antes de construir y lo\naprobó con *Connect* como se escribe en inglés.\n\n**La dirección.** Vienen más apps, una por área de la empresa. Salvador\npropuso `mycentauro.lat/appep`; se le propuso `appep.mycentauro.lat` y\nla eligió, por tres cosas:\n\n- Cada app en su propia dirección no mezcla con las otras su sesión, lo\n  que el navegador guarda ni la app instalada en el teléfono, y un\n  problema de seguridad en una no alcanza a las demás. Con diagonal\n  todas viven en el mismo origen y comparten todo eso.\n- Cada una se puede ir a su propio servidor sin cambiar de dirección.\n- A esta no se le toca nada por dentro. Con diagonal había que\n  reacomodar los enlaces de los correos, los avisos al teléfono y la app\n  de campo.\n\n`mycentauro.lat` sola queda como la puerta de la empresa: mientras haya\nuna sola app, manda a ella con la ruta completa, así que los enlaces que\nya salieron con esa dirección siguen sirviendo.\n\n### Lo que cambió\n\n- **La entrada de la consola**, y con ella la de crear la contraseña y\n  la de recuperarla, que viven en la misma tarjeta: el navy de la casa\n  con una luz detrás de la tarjeta blanca, filo dorado arriba, la marca\n  de la empresa y, separado debajo, PROTECCIÓN EJECUTIVA con CONNECT APP\n  en dorado entre dos rayas. Afuera de la tarjeta: «Acceso exclusivo\n  para personal autorizado». El sello AI/EP se queda en el encabezado de\n  adentro. El nombre no se traduce, el pie sí (`app_nombre`,\n  `app_sello`, `entrada_pie`).\n- **La app de campo**, igual: la entrada, la del código de cuatro\n  dígitos y la de «esta app es del equipo de campo». Se fue `cmp_lema`,\n  que ya no usaba nadie. El trabajador de fondo sube a\n  `centauro-campo-v9`.\n- **La pestaña del navegador** dice «Protección Ejecutiva Connect App ·\n  Centauro».\n- **El `Caddyfile`** contesta en `DOMINIO` y en `DOMINIO_RAIZ`; lo que\n  llega a la segunda se manda a la primera con 302 y no con 301: el día\n  que la puerta tenga su página con un botón por app, ningún navegador\n  se queda con el salto guardado. `docker-compose.prod.yml` le pasa\n  `DOMINIO_RAIZ` al proxy; vacía, el proxy contesta solo en `DOMINIO`,\n  como antes. Se probó con Caddy 2.11.4 (`caddy adapt`), con y sin\n  `DOMINIO_RAIZ`.\n- **La documentación** deja de decir `centauro.cc`: la guía (el `.env`\n  y el paso 3, con el comando para la dirección de una app nueva),\n  `crear_env.py` y el comentario de `config.py`.\n\n### Lo que falta, de tu lado\n\n- El registro `appep.mycentauro.lat` en Cloud DNS, el `git pull` y los\n  tres renglones del `.env`: `DOMINIO`, `DOMINIO_RAIZ` y `URL_PUBLICA`.\n- Si alguien ya instaló la app de campo desde `mycentauro.lat/app/`, que\n  la quite y la vuelva a instalar desde `appep.mycentauro.lat/app/`: la\n  app instalada y sus avisos son de la dirección donde se instaló.\n\n## 14. Lo que falta\n\n### Abierto\n\n- **El servidor: lo que queda del proveedor** (secciones 68 y 70). El\n  dominio ya es de Centauro: `mycentauro.lat`, comprado en Akky a su\n  nombre, con el DNS en Google Cloud DNS; la app vive en\n  `appep.mycentauro.lat`. Falta apagar el servidor de OVH, quitar la\n  llave del proveedor en GitHub y dejar de usar su llave de Google Maps.\n- **El plazo del archivo de comprobantes** (sección 69): que el contador\n  confirme los seis años; con eso se sella el candado del depósito.\n\n')

cambiar('bitacora',
        '- **El GPS: lo que le toca a Centauro Satelital** (sección 60). Las 14\n  unidades de Brasil que no traen placa en Pegasus —48126, 48127,\n  48129, 55122, 57564 a 57566 y 57597 a 57603— no se ligan hasta que\n  la capturen. Y cuando el servidor tenga su dirección con HTTPS, el\n  disparador de pánico en Pegasus hacia `/gps/pegasus/aviso/{secreto}`;\n  mientras tanto el pánico llega con la lectura de cada dos minutos. De\n  este lado, las placas ligan contra la flota leída de Odoo: sin ella,\n  ninguna.\n- **El correo: lo que falta es de Microsoft 365** (sección 67). Ya se\n  decidió: sale del buzón `ai@centauro.lat` por Microsoft Graph y los\n  enlaces cuelgan de `https://centauro.cc`. Falta el buzón, registrar la\n  aplicación en Entra con su secreto, darle permiso en Exchange solo\n  sobre ese buzón y poner los tres datos en el `.env` del servidor; el\n  paso 7b de `despliegue/LEEME.md` lo dice en orden. Con eso, la\n  invitación y la recuperación de contraseña llegan solas (sección 58).\n\n  *(Lo de abajo es el texto de cuando no existía el envío, que explica\n  por qué la tabla es como es.)*\n',
        '- **El GPS: lo que le toca a Centauro Satelital** (sección 60). Las 14\n  unidades de Brasil que no traen placa en Pegasus —48126, 48127,\n  48129, 55122, 57564 a 57566 y 57597 a 57603— no se ligan hasta que\n  la capturen. Y el disparador de pánico en Pegasus hacia\n  `https://appep.mycentauro.lat/gps/pegasus/aviso/{secreto}`: la\n  dirección con HTTPS ya existe (sección 70); mientras no se configure,\n  el pánico llega con la lectura de cada dos minutos. De este lado, las\n  placas ligan contra la flota leída de Odoo: sin ella, ninguna.\n- **El correo: lo que falta es de Microsoft 365** (sección 67). Ya se\n  decidió: sale del buzón `ai@centauro.lat` por Microsoft Graph y los\n  enlaces cuelgan de `https://appep.mycentauro.lat`. Falta el buzón,\n  registrar la aplicación en Entra con su secreto, darle permiso en\n  Exchange solo sobre ese buzón y poner los tres datos en el `.env` del\n  servidor; el paso 7b de `despliegue/LEEME.md` lo dice en orden. Con\n  eso, la invitación y la recuperación de contraseña llegan solas\n  (sección 58).\n\n  *(Lo de abajo es el texto de cuando no existía el envío, que explica\n  por qué la tabla es como es.)*\n')


# ============================================================ comprobar
def _md5(texto):
    return hashlib.md5(texto.encode("utf-8")).hexdigest()


distintos = [clave for clave in ARCHIVOS
             if _md5(textos[clave]) != ESPERADO[clave]]
distintos += [rel for rel, contenido in NUEVOS.items()
              if _md5(contenido) != ESPERADO["nuevo:" + rel]]
if distintos:
    raise SystemExit("Estos archivos no quedarian como los que se probaron: "
                     + ", ".join(distintos) + ". No se escribio nada.")

# ============================================================ escrituras
for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8", newline="").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8", newline="") as f:
            f.write(textos[clave])
        print("escrito  ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for relativa, contenido in NUEVOS.items():
    ruta = RAIZ / relativa
    if ruta.exists() and io.open(ruta, encoding="utf-8", newline="").read() == contenido:
        print("sin cambio", ruta.relative_to(RAIZ))
    else:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with io.open(ruta, "w", encoding="utf-8", newline="") as f:
            f.write(contenido)
        print("escrito  ", ruta.relative_to(RAIZ))
if saltados:
    print("ya estaban:", len(saltados), "cambios")

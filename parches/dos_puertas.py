# -*- coding: utf-8 -*-
"""Dos puertas: la consola en mycentauro.lat y la app en appep. (seccion 71).

Decision de Salvador, 26 de septiembre:

- La consola --del personal administrativo y los consultores-- vive en
  mycentauro.lat y su entrada lleva el logo de Centauro con CONNECT
  debajo, chico y en dorado. La pestana dice Centauro Connect.
- La app del personal de seguridad vive en appep.mycentauro.lat, con la
  entrada de la seccion 70 (Proteccion Ejecutiva Connect App).
- El Caddyfile contesta en DOMINIO (la consola) y DOMINIO_CAMPO (la app)
  y manda a cada quien a la suya; sin DOMINIO_CAMPO todo sigue en
  DOMINIO. docker-compose.prod.yml le pasa DOMINIO_CAMPO al proxy.
- /consola/ abre la consola (antes 404); la app manda ahi a quien no es
  de campo.

Sin migracion. Idempotente. Todo se arma en memoria, se comprueba contra
lo que se probo (md5 por archivo) y solo entonces se escribe.
"""
import hashlib
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ARCHIVOS = {
    'app_js': RAIZ / 'backend/app/web/app.js',
    'estilo': RAIZ / 'backend/app/web/estilo.css',
    'idioma': RAIZ / 'backend/app/web/idioma.js',
    'index': RAIZ / 'backend/app/web/index.html',
    'campo_js': RAIZ / 'backend/app/web/campo/app.js',
    'main': RAIZ / 'backend/app/main.py',
    'config': RAIZ / 'backend/app/config.py',
    'prueba': RAIZ / 'backend/tests/test_puertas.py',
    'caddy': RAIZ / 'despliegue/Caddyfile',
    'compose': RAIZ / 'docker-compose.prod.yml',
    'leeme': RAIZ / 'despliegue/LEEME.md',
    'crear_env': RAIZ / 'despliegue/crear_env.py',
    'bitacora': RAIZ / 'BITACORA.md',
}
NUEVOS = {}
ESPERADO = {'app_js': '18e9a5090da5e07a020a6e08debafe49', 'estilo': '600f478fcbdf94f0ec65c8e3ecd961f4', 'idioma': '83e9666a1c51f3d756a07e7ad9424cfc', 'index': 'e4f7ccb172539db3fabde4cd50467a29', 'campo_js': '4bd5a9ce2580778399562f608df00ef2', 'main': '48a96c61c7f88a2d35ded04577757b0e', 'config': 'c9ce3bf3d007d42716b580671a41c44b', 'prueba': '394868e8bacd08443ae4b41efde97244', 'caddy': '279a1181fca8a67272076d235bef7a37', 'compose': 'b9c9bea7306a7b0663247fb017ed710e', 'leeme': 'f717317def5d68025b099f57d5a9b152', 'crear_env': '1426742365bac4b2b35b013698c2d8da', 'bitacora': '5fb43433b3bbb4f6457f2817f976bd55'}

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
        '                          font-size:${Math.round(alto / 3)}px` }, "CENTAURO");\n}\n\n/* La portada de las pantallas de antes de entrar: arriba la marca de la\n   empresa y debajo el nombre de la app, Proteccion Ejecutiva Connect\n   App. Lo pidio Salvador el 26 de septiembre de 2026: vienen mas apps,\n   una por area de la empresa, y quien llega tiene que saber en un\n   segundo a cual entro. El nombre no se traduce --es un nombre--; la\n   linea de abajo de la tarjeta, si. */\nfunction portada() {\n  return h("div", { clase: "portada" },\n    marca(54),\n    h("div", { clase: "app-nombre" }, t("app_nombre")),\n    h("div", { clase: "app-sello" }, h("span", {}, t("app_sello"))));\n}\n\n/* La tarjeta va sobre el fondo navy de la puerta, con su pie afuera. */\n',
        '                          font-size:${Math.round(alto / 3)}px` }, "CENTAURO");\n}\n\n/* La portada de las pantallas de antes de entrar: la marca de la\n   empresa y, pegado a ella, el nombre de la consola: Connect. Es la\n   puerta del personal administrativo y de los consultores, en\n   mycentauro.lat; la app del personal de seguridad es otra puerta, en\n   appep.mycentauro.lat, y se llama Proteccion Ejecutiva Connect App\n   (secciones 70 y 71). Salvador la quiso limpia: sin repetir Centauro\n   debajo del logo que ya lo dice. El nombre no se traduce --es un\n   nombre--; la linea de abajo de la tarjeta, si. */\nfunction portada() {\n  return h("div", { clase: "portada" },\n    marca(54),\n    h("div", { clase: "app-sello" }, h("span", {}, t("consola_sello"))));\n}\n\n/* La tarjeta va sobre el fondo navy de la puerta, con su pie afuera. */\n')

cambiar('estilo',
        '  border-radius: 14px; padding: 30px 30px 24px;\n  box-shadow: 0 30px 70px rgba(5, 3, 20, .45), 0 2px 6px rgba(5, 3, 20, .25);\n}\n.portada { text-align: center; margin: 0 0 24px; }\n.portada img { display: block; margin: 0 auto; max-width: 100%; object-fit: contain; }\n/* El nombre de la app, debajo de la marca de la empresa y separado de\n   ella: la empresa es Centauro, la app es Proteccion Ejecutiva. */\n.portada .app-nombre {\n  margin-top: 18px; padding: 18px 0 0 2.4px; border-top: 1px solid var(--linea);\n  font-size: 19px; font-weight: 800; letter-spacing: 2.4px; line-height: 1.25;\n  text-transform: uppercase; color: var(--centauro);\n}\n.portada .app-sello {\n  display: flex; align-items: center; justify-content: center; gap: 12px;\n  margin-top: 8px; font-size: 12px; font-weight: 700; letter-spacing: 5px;\n  text-transform: uppercase; color: #8c6f14;\n}\n/* El espaciado de las letras deja aire despues de la ultima: se le\n   quita para que el nombre quede centrado entre sus dos rayas. */\n.portada .app-sello span { margin-right: -5px; }\n.portada .app-sello::before, .portada .app-sello::after {\n  content: ""; width: 34px; height: 1px; background: #c9a227;\n}\n.pie-entrada {\n  margin: 18px 0 0; text-align: center; font-size: 12px; letter-spacing: .3px;\n',
        '  border-radius: 14px; padding: 30px 30px 24px;\n  box-shadow: 0 30px 70px rgba(5, 3, 20, .45), 0 2px 6px rgba(5, 3, 20, .25);\n}\n.portada { text-align: center; margin: 0 0 30px; }\n.portada img { display: block; margin: 0 auto; max-width: 100%; object-fit: contain; }\n/* El nombre de la consola, pegado a la marca de la empresa y sin\n   repetirla: el logo ya dice Centauro (seccion 71). Chico y en dorado,\n   entre dos rayas: de las tres que se le ensenaron, Salvador eligio la\n   mas discreta, la que deja mandar al logo. */\n.portada .app-sello {\n  display: flex; align-items: center; justify-content: center; gap: 14px;\n  margin-top: 16px; font-size: 13px; font-weight: 700; letter-spacing: 7px;\n  text-transform: uppercase; color: #8c6f14;\n}\n/* El espaciado de las letras deja aire despues de la ultima: se le\n   quita para que el nombre quede centrado entre sus dos rayas. */\n.portada .app-sello span { margin-right: -7px; }\n.portada .app-sello::before, .portada .app-sello::after {\n  content: ""; width: 44px; height: 1px; background: #c9a227;\n}\n.pie-entrada {\n  margin: 18px 0 0; text-align: center; font-size: 12px; letter-spacing: .3px;\n')

cambiar('idioma',
        '  es: {\n    /* --- barra y acceso */\n    linea: "Protección Ejecutiva",\n    /* El nombre de la app, en la puerta. Es un nombre: no se traduce. */\n    app_nombre: "Protección Ejecutiva",\n    app_sello: "Connect App",\n    entrada_pie: "Acceso exclusivo para personal autorizado",\n    correo: "Correo",\n    contrasena: "Contraseña",\n',
        '  es: {\n    /* --- barra y acceso */\n    linea: "Protección Ejecutiva",\n    /* Los nombres de las dos puertas: la app de campo (app_) y la\n       consola (consola_). Son nombres: no se traducen. */\n    app_nombre: "Protección Ejecutiva",\n    app_sello: "Connect App",\n    consola_sello: "Connect",\n    entrada_pie: "Acceso exclusivo para personal autorizado",\n    correo: "Correo",\n    contrasena: "Contraseña",\n')

cambiar('idioma',
        '    linea: "Executive Protection",\n    app_nombre: "Protección Ejecutiva",\n    app_sello: "Connect App",\n    entrada_pie: "Authorized personnel only",\n    correo: "Email",\n    contrasena: "Password",\n',
        '    linea: "Executive Protection",\n    app_nombre: "Protección Ejecutiva",\n    app_sello: "Connect App",\n    consola_sello: "Connect",\n    entrada_pie: "Authorized personnel only",\n    correo: "Email",\n    contrasena: "Password",\n')

cambiar('idioma',
        '    linea: "Proteção Executiva",\n    app_nombre: "Protección Ejecutiva",\n    app_sello: "Connect App",\n    entrada_pie: "Acesso exclusivo para pessoal autorizado",\n    correo: "E-mail",\n    contrasena: "Senha",\n',
        '    linea: "Proteção Executiva",\n    app_nombre: "Protección Ejecutiva",\n    app_sello: "Connect App",\n    consola_sello: "Connect",\n    entrada_pie: "Acesso exclusivo para pessoal autorizado",\n    correo: "E-mail",\n    contrasena: "Senha",\n')

cambiar('index',
        '<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Protección Ejecutiva Connect App · Centauro</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;650;700&display=swap" rel="stylesheet">\n<link rel="stylesheet" href="/consola/estilo.css">\n',
        '<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Centauro Connect</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;650;700&display=swap" rel="stylesheet">\n<link rel="stylesheet" href="/consola/estilo.css">\n')

cambiar('campo_js',
        '      sesion.token = null; sesion.usuario = null;\n      location.hash = ""; pintar();\n    } }, t("cmp_entrar_otra")),\n    h("a", { href: "/", style: "text-decoration:none" },\n      h("button", { clase: "claro", style: "margin-top:10px" },\n        t("cmp_ir_consola")))));\n}\n',
        '      sesion.token = null; sesion.usuario = null;\n      location.hash = ""; pintar();\n    } }, t("cmp_entrar_otra")),\n    /* La consola vive en otra direccion (seccion 71): /consola/ la\n       abre en el mismo servidor y, desde appep., el proxy la manda a\n       la de la consola. "/" aqui ya es la app. */\n    h("a", { href: "/consola/", style: "text-decoration:none" },\n      h("button", { clase: "claro", style: "margin-top:10px" },\n        t("cmp_ir_consola")))));\n}\n')

cambiar('main',
        '\n\nif WEB.is_dir():\n    app.mount("/consola", ConsolaSinCache(directory=WEB), name="consola")\n\n    # La app del personal de seguridad. Vive en el mismo servidor y usa\n    # la misma sesion y los mismos endpoints que la consola, pero es\n',
        '\n\nif WEB.is_dir():\n    # Con html=True, /consola/ abre la consola igual que /. Los avisos al\n    # telefono del consultor llevan /consola/#/servicio/... y la app de\n    # campo manda a /consola/ a quien no es de campo: sin esto los dos\n    # caian en un 404. Y desde appep.mycentauro.lat el proxy lo manda a\n    # la direccion de la consola (seccion 71).\n    app.mount("/consola", ConsolaSinCache(directory=WEB, html=True),\n              name="consola")\n\n    # La app del personal de seguridad. Vive en el mismo servidor y usa\n    # la misma sesion y los mismos endpoints que la consola, pero es\n')

cambiar('config',
        '    # De donde cuelgan los enlaces que van dentro de un correo. Sin\n    # esto, el enlace de una encuesta seria "/encuestas/pagina/abc" y no\n    # llevaria a ningun lado fuera del servidor.\n    url_publica: str = ""          # "https://appep.mycentauro.lat"\n\n    # Odoo, del lado de SALIDA: la factura del servicio aprobado.\n    #\n',
        '    # De donde cuelgan los enlaces que van dentro de un correo. Sin\n    # esto, el enlace de una encuesta seria "/encuestas/pagina/abc" y no\n    # llevaria a ningun lado fuera del servidor.\n    url_publica: str = ""          # "https://mycentauro.lat"\n\n    # Odoo, del lado de SALIDA: la factura del servicio aprobado.\n    #\n')

cambiar('prueba',
        '    # Marcarlo dos veces no revienta ni mueve la fecha.\n    assert cliente.post("/auth/recorrido-visto", headers=h,\n                        json={}).status_code == 200\n',
        '    # Marcarlo dos veces no revienta ni mueve la fecha.\n    assert cliente.post("/auth/recorrido-visto", headers=h,\n                        json={}).status_code == 200\n\n\ndef test_la_consola_se_abre_tambien_en_consola_con_diagonal():\n    """Los avisos al telefono del consultor llevan /consola/#/servicio/...\n    y la app de campo manda a /consola/ a quien entra con una cuenta que\n    no es de campo. Antes de la seccion 71, /consola/ contestaba 404: el\n    montaje no servia el index de la carpeta."""\n    from fastapi.testclient import TestClient\n    from app.main import app\n\n    cliente = TestClient(app)\n    raiz = cliente.get("/")\n    con_diagonal = cliente.get("/consola/")\n    assert raiz.status_code == 200 and con_diagonal.status_code == 200\n    assert con_diagonal.text == raiz.text\n    assert "<title>Centauro Connect</title>" in con_diagonal.text\n    assert con_diagonal.headers["cache-control"] == "no-store"\n    # Lo demas de la carpeta se sigue sirviendo igual.\n    assert cliente.get("/consola/app.js").status_code == 200\n    assert cliente.get("/consola/no-existe.js").status_code == 404\n')

cambiar('caddy',
        "# —y sin certificado no hay service worker, ni camara, ni ubicacion, ni\n# avisos: la app de campo simplemente no existe.\n#\n# Las direcciones salen del .env: DOMINIO es la de la app\n# (appep.mycentauro.lat) y DOMINIO_RAIZ la de la empresa sola\n# (mycentauro.lat). Seccion 70.\n\n{\n\t# A donde escribe Let's Encrypt si un certificado esta por vencer y\n",
        "# —y sin certificado no hay service worker, ni camara, ni ubicacion, ni\n# avisos: la app de campo simplemente no existe.\n#\n# Las direcciones salen del .env (seccion 71): DOMINIO es la de la\n# consola (mycentauro.lat) y DOMINIO_CAMPO la de la app del personal de\n# seguridad (appep.mycentauro.lat). Sin DOMINIO_CAMPO todo vive en\n# DOMINIO, como antes.\n\n{\n\t# A donde escribe Let's Encrypt si un certificado esta por vencer y\n")

cambiar('caddy',
        '\temail operaciones@centauro.lat\n}\n\n{$DOMINIO} {$DOMINIO_RAIZ} {\n\tencode zstd gzip\n\n\t# mycentauro.lat sola es la puerta de la empresa. Vienen mas apps,\n\t# una por area, y cada una vive en su propia direccion --appep. es\n\t# la de Proteccion Ejecutiva-- para que sus sesiones, su app\n\t# instalada en el telefono y su seguridad no se mezclen con las de\n\t# las otras. Mientras haya una sola, la puerta manda directo a ella\n\t# con la ruta completa: los enlaces que ya salieron con\n\t# mycentauro.lat siguen sirviendo. 302 y no 301: el dia que la\n\t# puerta tenga su pagina con un boton por app, ningun navegador se\n\t# queda con el salto guardado para siempre.\n\t@puerta not host {$DOMINIO}\n\tredir @puerta https://{$DOMINIO}{uri} 302\n\n\t# La IP real del cliente. Sin esto el registro de auditoria guarda la\n\t# IP del proxy para todos, y el limite de intentos fallidos cuenta a\n',
        '\temail operaciones@centauro.lat\n}\n\n{$DOMINIO} {$DOMINIO_CAMPO} {\n\tencode zstd gzip\n\n\t# Dos puertas y un solo servidor (seccion 71). mycentauro.lat es la\n\t# consola --Centauro Connect--, del personal administrativo y los\n\t# consultores; appep.mycentauro.lat es la app del personal de\n\t# seguridad --Proteccion Ejecutiva Connect App--. Cada una en su\n\t# direccion, para que su sesion, lo que guarda el navegador y la app\n\t# instalada en el telefono no se mezclen. Las dos hablan con la misma\n\t# API, cada una desde su direccion. 302 y no 301 en todos los saltos:\n\t# uno permanente se queda guardado en cada navegador para siempre.\n\n\t# En la de la app, la raiz abre la app.\n\t@campo_raiz {\n\t\tnot host {$DOMINIO}\n\t\tpath /\n\t}\n\tredir @campo_raiz /app/ 302\n\n\t# Y la pagina de la consola se abre en la suya. Solo la pagina: la\n\t# app carga de /consola/ su api.js y su idioma.js, y esos se sirven\n\t# aqui mismo --un modulo que salta a otra direccion no carga--.\n\t@campo_consola {\n\t\tnot host {$DOMINIO}\n\t\tpath /consola /consola/ /consola/index.html\n\t}\n\tredir @campo_consola https://{$DOMINIO}{uri} 302\n\n\t# En la de la consola, la app se manda a la suya: la app instalada y\n\t# sus avisos son de la direccion donde se instalo, y tiene que ser\n\t# una sola. Sin DOMINIO_CAMPO no hay a donde mandarla y se queda.\n\t@consola_app {\n\t\thost {$DOMINIO}\n\t\tpath /app /app/*\n\t\texpression `"{$DOMINIO_CAMPO}" != ""`\n\t}\n\tredir @consola_app https://{$DOMINIO_CAMPO}{uri} 302\n\n\t# La IP real del cliente. Sin esto el registro de auditoria guarda la\n\t# IP del proxy para todos, y el limite de intentos fallidos cuenta a\n')

cambiar('compose',
        '    restart: unless-stopped\n    environment:\n      DOMINIO: ${DOMINIO:?falta DOMINIO en .env}\n      # La direccion de la empresa sola, que manda a la app (seccion\n      # 70). Vacia, el proxy solo contesta en DOMINIO.\n      DOMINIO_RAIZ: ${DOMINIO_RAIZ:-}\n    ports:\n      - "80:80"\n      - "443:443"\n',
        '    restart: unless-stopped\n    environment:\n      DOMINIO: ${DOMINIO:?falta DOMINIO en .env}\n      # La direccion de la app del personal de seguridad (seccion 71);\n      # DOMINIO es la de la consola. Vacia, todo vive en DOMINIO.\n      DOMINIO_CAMPO: ${DOMINIO_CAMPO:-}\n    ports:\n      - "80:80"\n      - "443:443"\n')

cambiar('leeme',
        'renglones que puede llevar:\n\n```\n# La direccion de la app y la de la empresa sola, que manda a la app\n# mientras sea la unica (seccion 70).\nDOMINIO=appep.mycentauro.lat\nDOMINIO_RAIZ=mycentauro.lat\nPOSTGRES_PASSWORD=...\nREDIS_PASSWORD=...\nDATABASE_URL=postgresql+psycopg://centauro:LA_DE_ARRIBA@db:5432/centauro\n',
        'renglones que puede llevar:\n\n```\n# Las dos puertas (seccion 71): la consola --del personal\n# administrativo y los consultores-- y la app del personal de seguridad.\nDOMINIO=mycentauro.lat\nDOMINIO_CAMPO=appep.mycentauro.lat\nPOSTGRES_PASSWORD=...\nREDIS_PASSWORD=...\nDATABASE_URL=postgresql+psycopg://centauro:LA_DE_ARRIBA@db:5432/centauro\n')

cambiar('leeme',
        'VAPID_CONTACTO=mailto:operaciones@centauro.lat\n\n# De donde cuelgan los enlaces que van en correos y task sheets. Es\n# el mismo DOMINIO de arriba.\nURL_PUBLICA=https://appep.mycentauro.lat\n\n# El correo que sale de la empresa: del buzon de Microsoft 365 (paso 7b).\n# Con los tres CORREO_MS_ llenos manda Microsoft y el SMTP de abajo no se\n',
        'VAPID_CONTACTO=mailto:operaciones@centauro.lat\n\n# De donde cuelgan los enlaces que van en correos y task sheets. Es\n# el mismo DOMINIO de arriba: la consola.\nURL_PUBLICA=https://mycentauro.lat\n\n# El correo que sale de la empresa: del buzon de Microsoft 365 (paso 7b).\n# Con los tres CORREO_MS_ llenos manda Microsoft y el SMTP de abajo no se\n')

cambiar('leeme',
        'Encrypt verifica que el dominio sea tuyo. El dominio es `mycentauro.lat`,\ncomprado en Akky, con el DNS en Google Cloud DNS (zona `mycentauro-lat`;\nen Akky van sus cuatro servidores, `ns-cloud-e1` a `ns-cloud-e4` de\n`googledomains.com`). Dos registros **A** hacia `34.51.121.227`:\n`mycentauro.lat`, la puerta de la empresa, y `appep.mycentauro.lat`,\nesta app (sección 70). La app de otra área, el día que exista, es un\nregistro más y su propio bloque en el `Caddyfile`:\n\n```bash\ngcloud dns record-sets create appXX.mycentauro.lat. --zone=mycentauro-lat --type=A --ttl=300 --rrdatas=34.51.121.227\n',
        'Encrypt verifica que el dominio sea tuyo. El dominio es `mycentauro.lat`,\ncomprado en Akky, con el DNS en Google Cloud DNS (zona `mycentauro-lat`;\nen Akky van sus cuatro servidores, `ns-cloud-e1` a `ns-cloud-e4` de\n`googledomains.com`). Dos registros **A** hacia `34.51.121.227`, uno\npor puerta (sección 71): `mycentauro.lat`, la consola —*Centauro\nConnect*, del personal administrativo y los consultores—, y\n`appep.mycentauro.lat`, la app del personal de seguridad —*Protección\nEjecutiva Connect App*—. Las dos llegan al mismo servidor; el `Caddyfile`\nmanda a cada quien a la suya: la raíz de `appep.` abre la app, la\nconsola que se pide ahí se abre en `mycentauro.lat`, y la app que se pide\nen `mycentauro.lat` se abre en `appep.`. La app de otra área, el día que\nexista, es un registro más y su propio bloque en el `Caddyfile`:\n\n```bash\ngcloud dns record-sets create appXX.mycentauro.lat. --zone=mycentauro-lat --type=A --ttl=300 --rrdatas=34.51.121.227\n')

cambiar('crear_env',
        '    return f"""# Centauro en produccion. Este archivo no sale del servidor: no va al\n# repositorio, ni a un correo, ni a un chat. Se edita con nano.\n\n# La direccion de la app y la de la empresa sola, que manda a la app\n# (seccion 70). URL_PUBLICA es la de la app, con https.\nDOMINIO=appep.mycentauro.lat\nDOMINIO_RAIZ=mycentauro.lat\nURL_PUBLICA=https://appep.mycentauro.lat\n\n# Lo del servidor. Se genero aqui mismo y nadie tiene que saberlo.\nAPP_ENV=produccion\n',
        '    return f"""# Centauro en produccion. Este archivo no sale del servidor: no va al\n# repositorio, ni a un correo, ni a un chat. Se edita con nano.\n\n# Las dos puertas (seccion 71): la consola y la app del personal de\n# seguridad. URL_PUBLICA es la de la consola, con https.\nDOMINIO=mycentauro.lat\nDOMINIO_CAMPO=appep.mycentauro.lat\nURL_PUBLICA=https://mycentauro.lat\n\n# Lo del servidor. Se genero aqui mismo y nadie tiene que saberlo.\nAPP_ENV=produccion\n')

cambiar('bitacora',
        '  la quite y la vuelva a instalar desde `appep.mycentauro.lat/app/`: la\n  app instalada y sus avisos son de la dirección donde se instaló.\n\n## 14. Lo que falta\n\n### Abierto\n\n- **El servidor: lo que queda del proveedor** (secciones 68 y 70). El\n  dominio ya es de Centauro: `mycentauro.lat`, comprado en Akky a su\n  nombre, con el DNS en Google Cloud DNS; la app vive en\n  `appep.mycentauro.lat`. Falta apagar el servidor de OVH, quitar la\n  llave del proveedor en GitHub y dejar de usar su llave de Google Maps.\n- **El plazo del archivo de comprobantes** (sección 69): que el contador\n  confirme los seis años; con eso se sella el candado del depósito.\n\n',
        '  la quite y la vuelva a instalar desde `appep.mycentauro.lat/app/`: la\n  app instalada y sus avisos son de la dirección donde se instaló.\n\n## 71. Dos puertas: la consola en mycentauro.lat, la app en appep.\n\nDecisión de Salvador, 26 de septiembre, la misma noche de la 70, que\nhabía dejado todo en `appep.mycentauro.lat` y a `mycentauro.lat`\nmandando ahí: «para accesar a la app del personal de campo debe de ser\nappep.mycentauro.lat con el diseño actual que ya tiene de connect app.\nPara entrar a la consola del sistema para el personal administrativo y\nconsultores debe de ser mycentauro.lat», con otro nombre y un diseño\nparecido. Primero se le propuso *My Centauro Connect*; al verlo, pidió\nquitar «My Centauro» —repetía lo que ya dice el logo— y dejar solo\n*Connect*, limpio. De tres versiones eligió la más discreta.\n\n### Lo que cambió\n\n- **La entrada de la consola** —y las de crear y recuperar la\n  contraseña, que usan la misma tarjeta— lleva el logo de Centauro y,\n  pegado a él, CONNECT chico en dorado entre dos rayas (`consola_sello`),\n  sin la raya que lo separaba del logo. La pestaña del navegador:\n  «Centauro Connect». La app de campo se queda como en la 70.\n- **El `Caddyfile`** contesta en `DOMINIO` —la consola— y en\n  `DOMINIO_CAMPO` —la app—. La raíz de `appep.` abre `/app/`; la página\n  de la consola pedida en `appep.` se abre en `mycentauro.lat`, y solo\n  la página: la app carga de `/consola/` su `api.js` y su `idioma.js`, y\n  un módulo que salta a otra dirección no carga. La app pedida en\n  `mycentauro.lat` se abre en `appep.`, porque la app instalada y sus\n  avisos son de la dirección donde se instaló. Todos los saltos con 302.\n  Sin `DOMINIO_CAMPO` todo vive en `DOMINIO`, como antes: el servidor de\n  OVH no cambia aunque tome este código. Se probó con Caddy 2.11.4\n  levantado con certificados locales: dieciséis casos con las dos\n  direcciones y tres como OVH.\n- **`/consola/` abre la consola** (el montaje ya sirve su `index.html`).\n  Los avisos al teléfono del consultor mandaban a `/consola/#/servicio/…`\n  y contestaba 404. La app de campo manda ahí a quien entra con una\n  cuenta que no es de campo; antes mandaba a `/`, que en `appep.` ya es\n  la app.\n- `DOMINIO_RAIZ` se fue: `docker-compose.prod.yml` le pasa\n  `DOMINIO_CAMPO` al proxy. La guía, `crear_env.py` y `config.py` dicen\n  las dos puertas, y `URL_PUBLICA` es la de la consola.\n\n### Lo que se configuró esa noche en el servidor\n\n- **Odoo.** La llave es la de la cuenta de súper administrador de\n  Salvador y no vence: decisión suya, después de ver que una cuenta\n  aparte, con solo el personal y la flota, limita lo que puede hacer una\n  llave que se filtre. Si su cuenta cambia o se desactiva, la lectura se\n  detiene. Primera lectura del personal: 66 en Odoo, 61 altas; 5\n  pendientes (4 con una plaza que Centauro no tiene, 1 sin plaza) y 3\n  celulares que no son número. Ensayo de la flota: 21 unidades de\n  Protección Ejecutiva en Odoo, 12 altas, 9 sin *Ubicación* y 1 entrada\n  al taller sin fecha.\n- **Pegasus.** Un usuario exclusivo del servidor de Google; el de OVH\n  sigue con el suyo. Ve los dos grupos: 71 unidades en México (59\n  reportaron en el día) y 27 en Brasil, 14 de ellas sin placa. Pegasus\n  trae 98 unidades de Protección Ejecutiva y Odoo 21: las que no están\n  en Odoo salen en *Unidades* sin ligar hasta que se den de alta allá.\n- **OVH sigue prendido** hasta que toda la operación esté aquí.\n\n### Lo que falta, de tu lado\n\n- En el `.env`: `DOMINIO=mycentauro.lat`,\n  `DOMINIO_CAMPO=appep.mycentauro.lat` y\n  `URL_PUBLICA=https://mycentauro.lat`; quitar `DOMINIO_RAIZ`.\n\n## 14. Lo que falta\n\n### Abierto\n\n- **El servidor: lo que queda del proveedor** (secciones 68, 70 y 71).\n  El dominio ya es de Centauro: `mycentauro.lat`, comprado en Akky a su\n  nombre, con el DNS en Google Cloud DNS; la consola vive en\n  `mycentauro.lat` y la app de campo en `appep.mycentauro.lat`. OVH\n  sigue prendido hasta que toda la operación esté aquí; ese día se\n  apaga, se quita la llave del proveedor en GitHub y se deja de usar su\n  llave de Google Maps.\n- **El plazo del archivo de comprobantes** (sección 69): que el contador\n  confirme los seis años; con eso se sella el candado del depósito.\n\n')

cambiar('bitacora',
        '  unidades de Brasil que no traen placa en Pegasus —48126, 48127,\n  48129, 55122, 57564 a 57566 y 57597 a 57603— no se ligan hasta que\n  la capturen. Y el disparador de pánico en Pegasus hacia\n  `https://appep.mycentauro.lat/gps/pegasus/aviso/{secreto}`: la\n  dirección con HTTPS ya existe (sección 70); mientras no se configure,\n  el pánico llega con la lectura de cada dos minutos. De este lado, las\n  placas ligan contra la flota leída de Odoo: sin ella, ninguna.\n- **El correo: lo que falta es de Microsoft 365** (sección 67). Ya se\n  decidió: sale del buzón `ai@centauro.lat` por Microsoft Graph y los\n  enlaces cuelgan de `https://appep.mycentauro.lat`. Falta el buzón,\n  registrar la aplicación en Entra con su secreto, darle permiso en\n  Exchange solo sobre ese buzón y poner los tres datos en el `.env` del\n  servidor; el paso 7b de `despliegue/LEEME.md` lo dice en orden. Con\n',
        '  unidades de Brasil que no traen placa en Pegasus —48126, 48127,\n  48129, 55122, 57564 a 57566 y 57597 a 57603— no se ligan hasta que\n  la capturen. Y el disparador de pánico en Pegasus hacia\n  `https://mycentauro.lat/gps/pegasus/aviso/{secreto}`: la\n  dirección con HTTPS ya existe (sección 71); mientras no se configure,\n  el pánico llega con la lectura de cada dos minutos. De este lado, las\n  placas ligan contra la flota leída de Odoo: sin ella, ninguna.\n- **El correo: lo que falta es de Microsoft 365** (sección 67). Ya se\n  decidió: sale del buzón `ai@centauro.lat` por Microsoft Graph y los\n  enlaces cuelgan de `https://mycentauro.lat`. Falta el buzón,\n  registrar la aplicación en Entra con su secreto, darle permiso en\n  Exchange solo sobre ese buzón y poner los tres datos en el `.env` del\n  servidor; el paso 7b de `despliegue/LEEME.md` lo dice en orden. Con\n')


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

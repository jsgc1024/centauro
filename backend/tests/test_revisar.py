"""El barrido estatico entra a la bateria.

`revisar.py` revisa cosas que las pruebas no pueden ver: claves de
idioma que faltan en un idioma, atributos que no existen en los modelos,
migraciones con dos cabezas, y --desde hoy-- actividades que un endpoint
pide y nadie declaro.

Esa ultima es la peligrosa: `permisos.roles_de` devuelve un conjunto
vacio para una actividad que no conoce, y eso cierra la puerta para toda
la empresa sin reventar nada. Se descubriria el dia que alguien no pueda
trabajar.

Vivia como un comando que alguien tenia que acordarse de correr. Aqui
corre solo, con todo lo demas.
"""
import importlib.util
import pathlib


def test_el_barrido_estatico_esta_limpio(capsys):
    ruta = pathlib.Path(__file__).resolve().parent.parent / "revisar.py"
    spec = importlib.util.spec_from_file_location("revisar", ruta)
    revisar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revisar)

    codigo = revisar.main()
    salida = capsys.readouterr().out
    assert codigo == 0, f"\n{salida}"


# ==================================================================
# La ayuda en pantalla
# ==================================================================

def test_un_signo_de_ayuda_sin_texto_se_caza(tmp_path, monkeypatch):
    """El candado que pidio Salvador (19 sep): que el "?" no se despegue.

    `conAyuda()` arma las claves pegando sufijos al nombre que recibe,
    asi que una letra de mas no revienta nada --`t()` devuelve la clave
    cuando no la encuentra-- y el usuario ve `ay_fin_depozitos_para`
    escrito en la pantalla. Como el barrido corre dentro de esta
    bateria, un bloque con "?" y sin texto rompe las pruebas: no es
    "acuerdate de escribirlo", es que no pasa.
    """
    import revisar

    web = tmp_path / "app" / "web"
    web.mkdir(parents=True)
    (web / "idioma.js").write_text(
        "const TEXTOS = {\n  es: {\n"
        '    ay_buena_para: "Para esto sirve",\n'
        '    ay_buena_cuando: "Esto pasa si no",\n'
        "  },\n};\n", encoding="utf-8")
    # La llamada va partida en dos lineas y con comas dentro del titulo,
    # que es como se escribe de verdad y como se escapaba del barrido
    # cuando miraba renglon por renglon.
    (web / "pantalla.js").write_text(
        'conAyuda("h3", t("x").replace("{n}", filas.length),\n'
        '         "ay_buena", { style: "margin:0" });\n'
        'conAyuda("h3", t("y"),\n'
        '         "ay_huerfana", {});\n', encoding="utf-8")

    monkeypatch.setattr(revisar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(revisar, "hallazgos", [])
    revisar.revisar_ayuda()

    dichos = "\n".join(revisar.hallazgos)
    assert "ay_huerfana_para" in dichos
    assert "ay_huerfana_cuando" in dichos
    # La que si tiene sus dos frases no se reclama, y `_numero` es
    # opcional: solo tiene sentido donde hay una cifra que cuadrar.
    assert "ay_buena" not in dichos


def test_un_texto_escrito_a_mano_se_caza(tmp_path, monkeypatch):
    """El candado que faltaba, y que dejo a `nomina.js` en espanol duro.

    `revisar_idioma` barre las claves que se USAN: caza la que falta en un
    idioma, no la pantalla que no usa ninguna. Asi vivio la nomina con
    cinco encabezados escritos a mano --tres llamadas a `t()` contra 364
    en servicio-- y nadie lo vio hasta que alguien fue a contarlas. Un
    usuario en Brasil abria la nomina y la leia en espanol.
    """
    import revisar

    web = tmp_path / "app" / "web"
    (web / "campo").mkdir(parents=True)
    (web / "idioma.js").write_text("const TEXTOS = {};\n", encoding="utf-8")
    (web / "pantalla.js").write_text(
        'h("th", {}, t("bien"));\n'
        'h("th", {}, "Estado del pago");\n'
        # Ni un separador ni una clase son texto de nadie.
        'h("td", {}, "—");\n'
        'h("div", { clase: "tarjeta lisa" }, algo);\n', encoding="utf-8")
    # La app de campo estuvo excluida un rato --estaba escrita entera en
    # espanol-- y desde el 19 de septiembre el candado la cubre igual.
    (web / "campo" / "app.js").write_text(
        'h("h1", {}, "Hola a todos");\n', encoding="utf-8")

    monkeypatch.setattr(revisar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(revisar, "hallazgos", [])
    revisar.revisar_texto_suelto()

    dichos = "\n".join(revisar.hallazgos)
    assert "Estado del pago" in dichos
    assert "Hola a todos" in dichos
    assert len(revisar.hallazgos) == 2, revisar.hallazgos


def test_el_texto_que_no_se_pinta_con_h_tambien_se_caza(tmp_path, monkeypatch):
    """Lo que dejo cien textos en espanol en la app de campo.

    La primera traduccion cambio exactamente lo que el barrido miraba
    --el tercer argumento de `h(...)`-- y dio limpia con un `alert` de
    cada tres todavia en espanol. Un barrido no encuentra errores:
    define que quiere decir "terminado".

    Las dos redes nuevas son las bocas --`alert`, `confirm`,
    `textContent`, `placeholder`-- y los acentos, que es la que no se
    puede burlar sin querer.
    """
    import revisar

    web = tmp_path / "app" / "web"
    web.mkdir(parents=True)
    (web / "idioma.js").write_text("const TEXTOS = {};\n", encoding="utf-8")
    (web / "pantalla.js").write_text(
        'alert("No se pudo guardar el cambio");\n'
        'boton.textContent = t("bien");\n'
        'linea.textContent = "Ya quedo registrado";\n'
        'const caja = h("input", { placeholder: "Escribe el motivo" });\n'
        # Un ejemplo de una palabra se lee igual en los tres idiomas.
        'const placa = h("input", { placeholder: "ABC-123-D" });\n'
        # Y un acento delata al que se escapo de todo lo demas.
        'const ok = confirm(t("seguro")) ? "Sí" : nada;\n',
        encoding="utf-8")

    monkeypatch.setattr(revisar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(revisar, "hallazgos", [])
    revisar.revisar_texto_suelto()

    dichos = "\n".join(revisar.hallazgos)
    assert "No se pudo guardar" in dichos
    assert "Ya quedo registrado" in dichos
    assert "Escribe el motivo" in dichos
    assert "Sí" in dichos
    assert "ABC-123-D" not in dichos
    assert len(revisar.hallazgos) == 4, revisar.hallazgos


def test_un_comentario_en_espanol_no_es_un_texto_sin_traducir(tmp_path,
                                                             monkeypatch):
    """La razon de que las dos redes nuevas miren el archivo sin comentarios.

    Los comentarios de este sistema estan en espanol y con acentos: son
    media bitacora. Sin borrarlos, cada parrafo explicando por que una
    pantalla hace lo que hace sale como un texto sin traducir, el
    barrido escupe doscientas lineas y deja de servir para nada.
    """
    import revisar

    web = tmp_path / "app" / "web"
    web.mkdir(parents=True)
    (web / "idioma.js").write_text("const TEXTOS = {};\n", encoding="utf-8")
    (web / "pantalla.js").write_text(
        "/* Aquí se explica por qué la pantalla hace lo que hace, con\n"
        '   acentos y con "comillas" adentro. */\n'
        '// Y una línea suelta de comentario, también en español.\n'
        'const url = "https://ejemplo.com/algo"; // con barras adentro\n'
        'alert(t("bien"));\n',
        encoding="utf-8")

    monkeypatch.setattr(revisar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(revisar, "hallazgos", [])
    revisar.revisar_texto_suelto()

    assert revisar.hallazgos == []


def test_una_pantalla_sin_que_nadie_le_preguntara_se_caza(tmp_path,
                                                          monkeypatch):
    """El candado de cobertura de los "?" (19 sep).

    `revisar_ayuda` le exige sus dos frases a cada bloque que YA tiene
    "?". Es la misma forma de agujero que dejo cien textos en espanol en
    la app de campo: una red que solo mira lo que alguien decidio marcar
    da por terminado lo que nunca se miro. Una pantalla nueva sin un
    solo "?" pasaba limpia.

    Ahora cada pantalla dice su numero, y el numero es el candado: menos
    quiere decir que se borro uno, mas que el padron se quedo viejo, y
    no estar quiere decir que a esa pantalla nadie le pregunto nada.
    """
    import revisar

    web = tmp_path / "app" / "web"
    web.mkdir(parents=True)
    (web / "finanzas.js").write_text(
        'conAyuda("h3", t("x"), "ay_fin_depositos", {});\n', encoding="utf-8")
    (web / "flota.js").write_text('h("h1", {}, t("y"));\n', encoding="utf-8")

    monkeypatch.setattr(revisar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(revisar, "hallazgos", [])
    monkeypatch.setattr(revisar, "AYUDA_POR_PANTALLA",
                        {"finanzas.js": 5, "nomina.js": 3})
    revisar.revisar_padron_ayuda()

    dichos = "\n".join(revisar.hallazgos)
    # Tenia cinco y queda uno: alguien borro cuatro.
    assert "tenia 5" in dichos and "quedan 1" in dichos
    # Una pantalla nueva que no esta en el padron.
    assert "flota.js" in dichos and "nadie miro" in dichos
    # Y un renglon del padron cuyo archivo ya no existe.
    assert "nomina.js" in dichos and "ya no existe" in dichos
    assert len(revisar.hallazgos) == 3, revisar.hallazgos


def test_un_cero_en_el_padron_es_una_respuesta(tmp_path, monkeypatch):
    """Que no lleve "?" no es un pendiente: puede ser una decision.

    No todos los encabezados llevan uno, y es a proposito --hay unos 95
    en la consola y 40 signos--. Una frase que no agrega nada ensena a
    ignorar los signos, y entonces tampoco se leen los que si importan.
    Por eso el padron acepta el cero: lo que no acepta es el silencio.
    """
    import revisar

    web = tmp_path / "app" / "web"
    web.mkdir(parents=True)
    (web / "api.js").write_text("export const api = {};\n", encoding="utf-8")

    monkeypatch.setattr(revisar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(revisar, "hallazgos", [])
    monkeypatch.setattr(revisar, "AYUDA_POR_PANTALLA", {"api.js": 0})
    revisar.revisar_padron_ayuda()

    assert revisar.hallazgos == []


def test_dos_componentes_con_el_mismo_nombre_de_clase_se_cazan(tmp_path,
                                                               monkeypatch):
    """El peor rato de la consola, y el mas barato de cazar.

    El panorama trajo una `.barra` --el tramo de un servicio sobre el eje
    del dia-- y el encabezado de la consola es `<header class="barra">`.
    La regla nueva le puso `height: 10px` al encabezado, que con
    `box-sizing: border-box` lo dejo en dieciocho pixeles con el menu
    colgando fuera de su caja: la pantalla entera se pintaba encima del
    menu. En el mismo commit venian `.punto` --que ya era el renglon de
    "una persona con su palomita"-- y `.atender`, que es componente y
    tambien nivel.

    Tres choques, ninguno visible leyendo un archivo: cada uno esta bien
    escrito por separado. Se ven en la hoja, que es donde se cruzan.
    """
    import revisar

    web = tmp_path / "app" / "web"
    web.mkdir(parents=True)
    (web / "estilo.css").write_text(
        # El encabezado, con su etiqueta.
        "header.barra { position: sticky; padding: 12px 20px 0; }\n"
        # Y el tramo del panorama, suelto: este le pega a los dos.
        ".barra { position: absolute; height: 10px; }\n"
        # La misma clase, dos componentes.
        ".punto { display: flex; align-items: center; }\n"
        ".punto { display: inline-block; width: 9px; height: 9px; }\n"
        # Componente y modificador a la vez.
        ".atender { display: flex; gap: 10px; }\n"
        ".punto.atender { background: #b8860b; }\n"
        # Lo que NO es un choque: un descendiente acotado, un ajuste de
        # pantalla chica, y un modificador que solo pinta.
        ".calendario-leyenda .punto { width: 10px; }\n"
        "@media (max-width: 700px) { .etiqueta_tira { flex: 0 0 96px; } }\n"
        ".etiqueta_tira { flex: 0 0 150px; }\n"
        ".tarjeta.lisa { border-top: 1px solid #eee; }\n", encoding="utf-8")

    monkeypatch.setattr(revisar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(revisar, "hallazgos", [])
    revisar.revisar_estilos()

    dichos = "\n".join(revisar.hallazgos)
    assert "'.barra' existe suelta" in dichos
    assert "'.punto' tiene 2 reglas" in dichos
    assert "'.atender' es un componente" in dichos
    # El ajuste de pantalla chica no es un choque, ni el descendiente.
    assert "etiqueta_tira" not in dichos
    assert len(revisar.hallazgos) == 3, revisar.hallazgos


def test_una_entrada_del_menu_sin_su_texto_se_caza(tmp_path, monkeypatch):
    """El menú y el recorrido de la primera vez salen de la misma tabla.

    `revisar_idioma` barre las claves que se usan como `t("...")`, y las
    del menu no se escriben asi: viven en una tabla --`texto` es lo que
    dice el boton y `cuenta` lo que el recorrido explica de esa
    entrada-- y de ahi salen como variables. Sin esto, agregar una
    pantalla al menu y olvidar su texto no lo caza nadie: la barra
    saldria con la clave escrita, `nav_flota`, a la vista de todos.
    """
    import revisar

    web = tmp_path / "app" / "web"
    web.mkdir(parents=True)
    (web / "idioma.js").write_text(
        "const TEXTOS = {\n  es: {\n"
        '    nav_operacion: "Operacion",\n'
        '    rec_operacion: "Como va la operacion",\n'
        "  },\n  en: {\n"
        '    nav_operacion: "Operations",\n'
        '    rec_operacion: "How it is going",\n'
        "  },\n  pt: {\n"
        '    nav_operacion: "Operacao",\n'
        '    rec_operacion: "Como vai",\n'
        "  },\n};\n", encoding="utf-8")
    (web / "app.js").write_text(
        "const MENU = [\n"
        '  { ruta: "/panorama", texto: "nav_operacion",'
        ' cuenta: "rec_operacion" },\n'
        '  { ruta: "/flota", texto: "nav_flota", cuenta: "rec_flota" },\n'
        "];\n", encoding="utf-8")

    monkeypatch.setattr(revisar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(revisar, "hallazgos", [])
    revisar.revisar_idioma()

    dichos = "\n".join(revisar.hallazgos)
    assert "nav_flota" in dichos
    assert "rec_flota" in dichos
    # La que si esta no se reclama.
    assert "nav_operacion" not in dichos


# ==================================================================
# El alfabeto de los documentos
# ==================================================================

def test_un_documento_sin_charset_se_caza(tmp_path, monkeypatch):
    """El error que cazó Salvador en su pantalla, no el código.

    El correo salía con `<!doctype html>` y de ahí directo al `<body>`,
    sin decir en qué alfabeto estaba escrito. El buzón del cliente
    entonces adivina --casi siempre latin-1-- y lo que llega dice
    "sÃ¡bado" y "terminÃ³" donde iba el acento.

    Las páginas que ya existían sí lo declaraban. La diferencia no era
    técnica: esas se habían abierto en un navegador mil veces, y los
    correos nunca se habían visto.
    """
    import revisar

    app = tmp_path / "app"
    app.mkdir(parents=True)
    (app / "correo_malo.py").write_text(
        'def armar(cuerpo):\n'
        '    return f"""<!doctype html>\n'
        '<html><body>{cuerpo}</body></html>"""\n', encoding="utf-8")
    (app / "correo_bueno.py").write_text(
        'def armar(cuerpo):\n'
        '    return f"""<!doctype html>\n'
        '<html><head><meta charset="utf-8"></head>\n'
        '<body>{cuerpo}</body></html>"""\n', encoding="utf-8")

    monkeypatch.setattr(revisar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(revisar, "hallazgos", [])
    revisar.revisar_charset()

    dichos = "\n".join(revisar.hallazgos)
    assert "correo_malo.py" in dichos
    assert "correo_bueno.py" not in dichos
    assert len(revisar.hallazgos) == 1, revisar.hallazgos

# -*- coding: utf-8 -*-
"""Seccion 101: la consola.

Cuarta tanda de la revision del 28 de septiembre, la parte de la consola:
el dato mal capturado explicado en el idioma de quien mira y con su
campo, las referencias del banco que se guardan tal cual, los nombres con
su mayuscula adentro, el idioma que arranca en el del usuario, el 401
que vuelve a donde estaba, la contrasena que se cambia desde adentro, los
textos del servidor que la consola traduce, el tabulador con centavos,
el Panorama por moneda y por pais, los catalogos con "Reactivar", y la
app de campo con la moneda del pais.
"""
import re
from datetime import date
from pathlib import Path

from app import models as m

WEB = Path(__file__).resolve().parents[1] / "app" / "web"


def _js(nombre):
    return (WEB / nombre).read_text(encoding="utf-8")


# ============================================================ la captura

def test_un_dato_mal_capturado_se_explica_con_su_campo(cliente, sesion):
    """FastAPI contestaba "Field required. Input should be a valid
    decimal", en ingles y sin decir cual campo. Ahora cada renglon dice
    el campo y que le falta, y viaja en piezas para que la consola lo
    diga en su idioma."""
    h = sesion("admin")
    r = cliente.post("/catalogos/dias-festivos", headers=h,
                     json={"pais_id": 1, "nombre": "x", "factor_comision": "dos"})
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert "Falta el dato «fecha»" in d["mensaje"]
    assert "«factor_comision» tiene que ser un número" in d["mensaje"]
    assert d["que_hacer"]
    tipos = {e["campo"]: e["tipo"] for e in d["errores"]}
    assert tipos == {"fecha": "falta", "factor_comision": "numero"}

    r = cliente.post("/catalogos/dias-festivos", headers=h,
                     json={"pais_id": 1, "fecha": "2030-12-25", "nombre": "x" * 200,
                           "factor_comision": 0})
    assert r.status_code == 422, r.text
    errores = {e["campo"]: e for e in r.json()["detail"]["errores"]}
    assert errores["nombre"]["tipo"] == "largo" and errores["nombre"]["limite"] == "120"
    assert errores["factor_comision"]["tipo"] == "mas_de"
    assert "caben 120 letras" in r.json()["detail"]["mensaje"]


def test_un_cuerpo_que_no_es_json_no_es_error_del_servidor(cliente, sesion):
    h = {**sesion("admin"), "Content-Type": "application/json"}
    r = cliente.post("/catalogos/dias-festivos", headers=h, content=b"{no json")
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["errores"][0]["tipo"] == "cuerpo"


def test_la_consola_traduce_cada_tipo_de_error_de_captura():
    """api.js no importa idioma.js (tiene que vivir aunque este no cargue):
    la consola y la app le prestan su traductor, y cada tipo que manda el
    servidor tiene su clave en los tres idiomas."""
    api = _js("api.js")
    assert "static traducir = null" in api
    assert 'ErrorApi.traducir = t' in _js("app.js")
    assert 'ErrorApi.traducir = t' in _js("campo/app.js")
    tipos = re.findall(r'\b(\w+): "val_\w+"', api[api.index("ErrorApi.TIPOS"):])
    from app import main
    assert set(main.FRASES_DE_CAPTURA) - {"otro"} <= set(tipos)
    idioma = _js("idioma.js")
    for clave in re.findall(r'"(val_\w+)"', api):
        assert idioma.count(f"    {clave}:") == 3, clave
    # Sin red o con el servidor lento ya no sale "sin_red" ni "tardo".
    assert 'codigo === 0) return ErrorApi.texto(d === "tardo" ? "api_tardo" : "cc_sin_red")' in api
    assert idioma.count("    api_tardo:") == 3


# ============================================================ los textos

def test_las_referencias_del_banco_se_guardan_tal_cual():
    """"SPEI 7F3A9B0C" se volvia "Spei 7f3a9b0c" al salir del campo, y
    asi se buscaba despues en el estado de cuenta."""
    finanzas = _js("finanzas.js")
    referencia = finanzas[finanzas.index('entrada("referencia"'):]
    assert '"data-crudo": ""' in referencia[:200]
    confirmacion = finanzas[finanzas.index('entrada("confirmacion"'):]
    assert '"data-crudo": ""' in confirmacion[:200]
    bonos = _js("bonos.js")
    pago = bonos[bonos.index('placeholder: t("bon_referencia")'):]
    assert '"data-crudo": ""' in pago[:80]
    assert 'entrada("folio", { "data-crudo": "" })' in _js("implantado.js")


def test_la_regla_de_mayusculas_conoce_das_y_respeta_las_de_adentro():
    from app import texto
    assert texto.titulo("Maria das Dores") == "Maria das Dores"
    assert texto.titulo("JOAO DAS NEVES") == "Joao das Neves"
    assert texto.titulo("McDonald's") == "McDonald's"
    assert texto.titulo("O'Brien") == "O'Brien"
    assert texto.titulo("JUAN CARLOS") == "Juan Carlos"
    assert texto.titulo("juan carlos") == "Juan Carlos"
    assert texto.titulo("Jean du Pont") == "Jean du Pont"
    js = _js("util.js")
    assert '"das", "du", "des", "le"' in js
    assert "conMayusculaAdentro(original)" in js


def test_el_403_por_rol_dice_quien_si_puede(cliente, sesion):
    """`auth.requiere` traia los roles permitidos en el detalle y ningun
    mensaje para salir del problema, a diferencia de `auth.puede`."""
    # /campo/mi-dia pide el rol de personal de seguridad con `requiere`.
    r = cliente.get("/campo/mi-dia", headers=sesion("finanzas"))
    assert r.status_code == 403, r.text
    d = r.json()["detail"]
    assert d["que_hacer"].startswith("Esto lo hace: personal seguridad.")
    assert "finanzas" in d["que_hacer"]
    assert d["roles_permitidos"] == ["personal_seguridad"]


def test_los_textos_del_profesionalismo_viajan_en_piezas(cliente, sesion, datos):
    """Las frases de cada dimension salian del servidor en espanol y la
    consola en ingles o portugues las pintaba tal cual. Ahora viajan
    con su clave y sus numeros, y `detalle` sigue siendo el espanol."""
    h = sesion("diroperaciones")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    r = cliente.get(f"/profesionalismo/persona/{juan}", headers=h)
    assert r.status_code == 200, r.text
    dimensiones = r.json()["dimensiones"]
    assert dimensiones
    for d in dimensiones:
        assert d["detalle"]
        assert d["frase"] and d["frase"]["clave"]
    claves = {d["frase"]["clave"] for d in dimensiones}
    assert "sin_incidencias" in claves
    idioma = _js("idioma.js")
    for clave in ("sin_evaluaciones", "sin_criterios", "estrellas", "sin_servicios",
                  "sin_calificacion", "calificaciones", "sin_incidencias",
                  "incidencias", "capacitacion", "experiencia", "sin_km", "manejo"):
        assert idioma.count(f"    prof_d_{clave}:") == 3, clave
    assert "fraseDe(d.frase, d.detalle)" in _js("personal.js")


def test_la_nota_de_las_encuestas_trae_su_clave(cliente, sesion, datos):
    from ayudas import crear_servicio, jornada
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos,
                              [jornada(date(2030, 3, 4), datos["modalidades"]["full_day"]["id"])])
    h2 = sesion("diroperaciones")
    cliente.post(f"/encuestas/servicio/{servicio['id']}/enviar", headers=h2)
    # La segunda vez ya no hay nada que mandar: la nota, con su clave.
    r = cliente.post(f"/encuestas/servicio/{servicio['id']}/enviar", headers=h2)
    assert r.status_code == 201, r.text
    assert r.json()["resultado"] == "sin cambios"
    assert r.json()["clave"] == "enc_ya_enviadas"
    assert 'mensaje(r.clave ? t(r.clave) : r.nota)' in _js("encuestas.js")
    assert _js("idioma.js").count("    enc_ya_enviadas:") == 3


# ============================================================ la sesion

def test_la_contrasena_se_cambia_desde_adentro_y_la_actual_mal_no_saca(cliente, sesion, datos):
    """La ruta existia sin boton. Y la contrasena actual equivocada
    contesta 403, no 401: la consola toma el 401 como sesion vencida."""
    h = sesion("consultor")
    r = cliente.post("/auth/mi-contrasena", headers=h,
                     json={"actual": "no es", "nueva": "camino largo a casa"})
    assert r.status_code == 403, r.text
    assert "actual" in r.text
    # La sesion sigue viva.
    assert cliente.get("/auth/yo", headers=h).status_code == 200
    app = _js("app.js")
    assert 'location.hash = "#/mi-contrasena"' in app
    assert 'api.post("/auth/mi-contrasena"' in app
    assert _js("idioma.js").count("    cc_cambiar:") == 3


def test_el_401_vuelve_a_donde_estaba_y_el_idioma_es_el_del_usuario():
    api = _js("api.js")
    assert 'sessionStorage.setItem(VOLVER, donde)' in api
    assert "export function destinoPendiente()" in api
    app = _js("app.js")
    assert "location.hash = destinoPendiente() || destinoDe(sesion.usuario)" in app
    # El idioma arranca en el de quien entra y se queda para manana.
    assert "function idiomaDelUsuario()" in app
    idioma = _js("idioma.js")
    assert "localStorage.setItem(LLAVE, codigo)" in idioma
    assert "localStorage.getItem(LLAVE)" in idioma
    # Un solo oyente global para cerrar los menus: ninguno dentro de la barra.
    barra = app[app.index("function armazon()"):app.index("function nombreCorto(")]
    assert 'document.addEventListener("click"' not in barra
    # El rol sale en el idioma de la consola, no como clave.
    assert "nombreDelRol(rol)" in app


def test_las_busquedas_descartan_la_respuesta_vieja():
    """La busqueda lenta de "EP/E-0" llegaba despues de la rapida de
    "EP/E-01" y pisaba la tabla. Cada pantalla lleva su contador."""
    for archivo in ("historial.js", "codigo.js", "personal.js", "bitacora_admin.js"):
        js = _js(archivo)
        assert "++peticion" in js and "mia !== peticion" in js, archivo
    mapa = _js("mapa.js")
    assert "const ESPERA_MS = 400" in mapa
    assert "repintarSinPrisa" in mapa and "mia !== peticion" in mapa


def test_el_tabulador_respeta_los_centavos_y_manda_solo_lo_que_cambio():
    js = _js("nomina.js")
    tabla = js[js.index("function tablaComision("):]
    assert 'step: "0.01"' in tabla
    assert "Math.round" not in tabla[:3000]
    assert "const cambiadas = celdas.filter(c => c.monto.value !== \"\" && cambio(c))" in tabla


# ============================================================ el Panorama

def test_el_panorama_da_un_monto_por_moneda_y_una_nomina_por_pais(cliente, sesion):
    h = sesion("dirgeneral")
    r = cliente.get("/panorama", headers=h)
    assert r.status_code == 200, r.text
    dinero = r.json()["dinero"]
    assert isinstance(dinero["por_depositar"]["montos"], list)
    assert isinstance(dinero["afuera_sin_comprobar"]["montos"], list)
    assert isinstance(dinero["afuera_sin_comprobar"]["vencidos"], list)
    por_pais = dinero["nomina_de_la_semana"]["por_pais"]
    assert {p["pais"] for p in por_pais} >= {"MX"}
    for p in por_pais:
        assert p["moneda"] in ("MXN", "BRL")
        assert p["estatus"] and "total" in p and "personas" in p
    js = _js("panorama.js")
    assert "#/servicio/${" in js
    assert "#/servicios/${" not in js


# ============================================================ los catalogos

def test_lo_quitado_de_un_catalogo_se_puede_reactivar(cliente, sesion):
    """"Quitar" desactivaba y la lista ya no lo traia: el festivo del 25
    de diciembre quitado por error no tenia vuelta, y ese dia la
    comision dejaba de pagarse al doble."""
    h = sesion("admin")
    r = cliente.post("/catalogos/dias-festivos", headers=h,
                     json={"pais_id": 1, "fecha": "2031-12-25",
                           "nombre": "Navidad de prueba", "factor_comision": 2})
    assert r.status_code in (200, 201), r.text
    festivo = r.json()
    try:
        assert cliente.delete(f"/catalogos/dias-festivos/{festivo['id']}",
                              headers=h).status_code in (200, 204)
        activos = cliente.get("/catalogos/dias-festivos", headers=h).json()
        assert all(f["id"] != festivo["id"] for f in activos)
        todos = cliente.get("/catalogos/dias-festivos?incluir_inactivos=true",
                            headers=h).json()
        apagado = next(f for f in todos if f["id"] == festivo["id"])
        assert apagado["activo"] is False
        r = cliente.post(f"/catalogos/dias-festivos/{festivo['id']}/reactivar",
                         headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["activo"] is True
    finally:
        cliente.delete(f"/catalogos/dias-festivos/{festivo['id']}", headers=h)
        from app.db import SessionLocal
        s = SessionLocal()
        try:
            s.query(m.DiaFestivo).filter_by(id=festivo["id"]).delete()
            s.commit()
        finally:
            s.close()
    js = _js("catalogos_pantalla.js")
    assert "incluir_inactivos=true" in js
    assert "/plazas?todas=true" in js and "/hoteles?todos=true" in js
    assert 'api.post(`${ruta}/reactivar`' in js or "/reactivar`" in js
    assert _js("idioma.js").count("    ctl_reactivar:") == 3


def test_las_plazas_y_los_hoteles_con_todas_traen_tambien_los_quitados(cliente, sesion):
    from app.db import SessionLocal
    h = sesion("admin")
    s = SessionLocal()
    try:
        plaza = s.query(m.Plaza).filter(m.Plaza.activo.is_(True)).first()
        hotel = s.query(m.Hotel).first()
        plaza.activo = False
        if hotel:
            hotel.activo = False
        s.commit()
        plaza_id, hotel_id = plaza.id, hotel.id if hotel else None
    finally:
        s.close()
    try:
        todas = cliente.get("/catalogos/plazas?todas=true", headers=h).json()
        assert any(p["id"] == plaza_id and p["activo"] is False for p in todas)
        activas = cliente.get("/catalogos/plazas", headers=h).json()
        assert all(p["id"] != plaza_id for p in activas)
        if hotel_id:
            todos = cliente.get("/catalogos/hoteles?todos=true", headers=h).json()
            assert any(x["id"] == hotel_id for x in todos)
    finally:
        s = SessionLocal()
        try:
            s.query(m.Plaza).filter_by(id=plaza_id).update({"activo": True})
            if hotel_id:
                s.query(m.Hotel).filter_by(id=hotel_id).update({"activo": True})
            s.commit()
        finally:
            s.close()


# ============================================================ la app

def test_la_app_dice_el_dinero_en_la_moneda_del_pais(cliente, sesion):
    """La app pintaba "$" fijo en pagos y bono, tambien en Brasil."""
    r = cliente.get("/campo/mis-comisiones", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert r.json()["en_curso"]["moneda"] == "MXN"
    js = _js("campo/app.js")
    assert "function dineroApp(" in js
    assert "`$${" not in js
    assert 'dineroApp(b.bono, b.moneda)' in js
    assert 'dineroApp(c.total, c.moneda)' in js
    assert 't("cmp_en_curso_nota")' in js


# ============================================================ la hoja

def test_la_hoja_con_fotos_grandes_se_publica(cliente, sesion, datos):
    """La hoja congelada lleva las fotos de la gente y de las unidades
    incrustadas; con las de 512 px de Odoo pasaba de los 20,000
    caracteres del tope y publicar contestaba "un texto es mas largo de
    lo que cabe". La columna ya no tiene tope."""
    from ayudas import asignar, crear_servicio, jornada, manana
    from app.db import SessionLocal
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos,
                              [jornada(manana(30), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    for r in asignar(cliente, h, j["id"], persona_id=juan,
                     vehiculo_id=datos["suburban"]["id"]):
        assert r.status_code == 200, r.text
    foto = "data:image/jpeg;base64," + ("A" * 60_000)
    with SessionLocal() as s:
        s.query(m.Persona).filter_by(id=juan).update({"foto_url": foto})
        s.commit()
    try:
        r = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                         headers=h, json={"forzar": True})
        assert r.status_code == 200, r.text
        with SessionLocal() as s:
            hoja = s.query(m.TaskSheet).filter_by(servicio_id=servicio["id"]).first()
            assert len(hoja.contenido) > 20_000
    finally:
        with SessionLocal() as s:
            s.query(m.Persona).filter_by(id=juan).update({"foto_url": None})
            s.commit()


def test_la_tabla_de_dias_no_ofrece_armar_donde_el_servidor_lo_niega():
    """Al terminado, sin visto bueno, en facturacion, cerrado o cancelado
    el servidor no deja agregar ni quitar dias (seccion 98); la tabla
    seguia ofreciendo los botones."""
    from app.routers import servicios
    js = _js("servicio.js")
    lista = js[js.index("const YA_NO_SE_ARMA = ["):]
    lista = lista[:lista.index("];")]
    en_consola = set(re.findall(r'"(\w+)"', lista))
    assert en_consola == {e.value for e in servicios.YA_NO_SE_ARMA}
    tabla = js[js.index("function tablaDias("):js.index("function opcionesModalidad(")]
    assert "const seArma = !YA_NO_SE_ARMA.includes(servicio.estatus)" in tabla
    assert 'seArma ? quitar : ""' in tabla

"""El manual del sistema (seccion 90).

Propuesta aprobada por Salvador el 27 de septiembre: el manual vive
dentro de la consola y se pone al dia con cada actualizacion. Lo que sale
solo del sistema --el reloj, quien puede que, los mensajes, las
novedades-- se lee del propio codigo; lo escrito tiene candado. Estas
pruebas son ese candado: una pantalla nueva, una tarea nueva del reloj,
un archivo nuevo con mensajes o una seccion nueva de la bitacora sin su
parte del manual no pasan.

Y lo de siempre de cada pantalla: quien lo lee, en que idioma, el estado
del sistema en vivo y los casos resueltos.
"""
import os
import re
from datetime import datetime, timedelta, timezone

import pytest
from celery.schedules import crontab
from sqlalchemy.orm import Session

from app import manual
from app import models as m

RAIZ = os.path.join(os.path.dirname(__file__), "..")
WEB = os.path.join(RAIZ, "app", "web")
BITACORA = os.path.join(RAIZ, "..", "BITACORA.md")

# La primera seccion de la bitacora con su novedad escrita. De aqui en
# adelante, cada seccion trae la suya en los dos idiomas.
DESDE = 77


def _web(nombre: str) -> str:
    return open(os.path.join(WEB, nombre), encoding="utf-8").read()


def _capitulos(idioma: str) -> dict:
    return {c["id"]: c for c in manual.capitulos(idioma)}


# ====================================================== lo escrito

def test_los_dos_idiomas_traen_las_dos_partes():
    for idioma in manual.IDIOMAS:
        partes = {c["parte"] for c in manual.capitulos(idioma)}
        assert partes == {"entender", "resolver"}, idioma


def test_espanol_y_portugues_dicen_lo_mismo():
    """Mismos capitulos, en el mismo orden, con las mismas anclas y las
    mismas ligas: el portugues no puede quedarse atras del espanol."""
    es, pt = _capitulos("es"), _capitulos("pt")
    assert list(es) == list(pt)
    for clave, c in es.items():
        otro = pt[clave]
        assert (c["parte"], c["orden"]) == (otro["parte"], otro["orden"]), clave
        assert manual.anclas(c) == manual.anclas(otro), clave
        assert sorted(manual.ligas(c)) == sorted(manual.ligas(otro)), clave
        assert bool(c["area"]) == bool(otro["area"]), clave
    # Los sintomas se agrupan igual: la misma area en espanol es la misma
    # en portugues.
    pares = {(c["area"], pt[k]["area"]) for k, c in es.items() if c["area"]}
    assert len(pares) == len({a for a, _ in pares}) == len({b for _, b in pares})


def test_cada_sintoma_esta_escrito_igual():
    """Que ves, por que pasa, como se arregla y, al final, la causa de
    fondo en su caja."""
    for idioma in manual.IDIOMAS:
        for c in manual.capitulos(idioma):
            if c["parte"] != "resolver":
                continue
            assert c["area"], (idioma, c["id"])
            titulos = [b for b in c["bloques"] if b["tipo"] == "h3"]
            assert len(titulos) >= 3, (idioma, c["id"])
            assert c["bloques"][0]["tipo"] == "h3", (idioma, c["id"])
            assert c["bloques"][-1]["tipo"] == "nota", (idioma, c["id"])


def _rutas_de_la_consola() -> list:
    """Las rutas de app.js, tal como las reparte la consola."""
    fuente = _web("app.js")
    patrones = re.findall(r"\[/(\^#[^\n]*?\$)/,", fuente)
    assert len(patrones) > 15
    return [re.compile(p.replace("\\/", "/")) for p in patrones]


def _paginas_del_manual() -> set:
    return set(re.findall(r'pagina === "(\w+)"', _web("manual.js")))


def _lleva_a_algo(liga: str, capitulos: dict, rutas: list) -> bool:
    if liga.startswith("#/manual/leer/"):
        partes = liga[len("#/manual/leer/"):].split("/")
        c = capitulos.get(partes[0])
        return c is not None and (len(partes) == 1
                                  or partes[1] in manual.anclas(c))
    if liga.startswith("#/manual/"):
        return liga[len("#/manual/"):] in _paginas_del_manual()
    return any(r.match(liga) for r in rutas)


def test_cada_liga_lleva_a_algo_que_existe(base_de_pruebas):
    rutas = _rutas_de_la_consola()
    for idioma in manual.IDIOMAS:
        capitulos = _capitulos(idioma)
        ligas = [x for c in capitulos.values() for x in manual.ligas(c)]
        ligas += [p["a"] for n in manual.novedades(idioma) for p in n["partes"]
                  if p.get("a")]
        with Session(base_de_pruebas) as db:
            ligas += [x["ir"] for x in manual.estado(db, idioma) if x["ir"]]
        assert ligas
        for liga in ligas:
            assert _lleva_a_algo(liga, capitulos, rutas), (idioma, liga)


def test_las_tarjetas_del_estado_llevan_a_su_sintoma():
    """Las ligas del estado estan escritas en manual.py con su id: si el
    sintoma cambia de nombre, aqui se ve."""
    fuente = open(os.path.join(RAIZ, "app", "manual.py"), encoding="utf-8").read()
    ids = re.findall(r'ir = "#/manual/leer/([\w-]+)"', fuente)
    assert len(ids) >= 4
    for idioma in manual.IDIOMAS:
        capitulos = _capitulos(idioma)
        for x in ids:
            assert x in capitulos and capitulos[x]["parte"] == "resolver", (idioma, x)


def test_cada_pantalla_del_menu_esta_en_el_manual():
    """Una pantalla nueva en el menu sin su parte en «Cada pantalla, para
    que es» no pasa."""
    claves = re.findall(r'clave: "(\w+)", necesita:', _web("menu.js"))
    assert "manual" in claves and len(claves) > 15
    for idioma in manual.IDIOMAS:
        anclas = set(manual.anclas(_capitulos(idioma)["pantallas"]))
        faltan = [c for c in claves if c not in anclas]
        assert not faltan, (idioma, faltan)


def test_las_ligas_solo_van_a_la_consola():
    partes = manual.renglon("Ver **esto**, [Odoo](#/odoo) y [afuera](https://x.com).")
    assert {"t": "esto", "b": True} in partes
    assert {"t": "Odoo", "a": "#/odoo"} in partes
    assert {"t": "afuera"} in partes


def test_un_capitulo_mal_escrito_no_pasa():
    with pytest.raises(ValueError):
        manual.capitulo("sin cabeza", "x.md")
    with pytest.raises(ValueError):
        manual.capitulo("---\nid: x\nparte: entender\n---\nTexto", "x.md")
    with pytest.raises(ValueError):
        manual.capitulo("---\nid: x\nparte: otra\ntitulo: T\n---\nTexto", "x.md")
    c = manual.capitulo("---\nid: x\nparte: entender\ntitulo: T\n---\n"
                        "## Uno {#uno}\nTexto\n\n- a\n- b\n\n> nota", "x.md")
    assert [b["tipo"] for b in c["bloques"]] == ["h2", "p", "lista", "nota"]
    assert manual.anclas(c) == ["uno"]


# ====================================================== lo que sale solo

def test_cada_tarea_del_reloj_esta_explicada():
    """Una tarea nueva en el calendario sin su renglon en el manual no
    pasa: el manual no se entera tarde."""
    from app.celery_app import celery
    assert set(celery.conf.beat_schedule) == set(manual.TAREAS)
    for nombre, textos in manual.TAREAS.items():
        for idioma in manual.IDIOMAS:
            que, revisa = textos[idioma]
            assert que.strip() and revisa.strip(), (nombre, idioma)


def test_el_reloj_dice_cuando_como_se_lee():
    casos = [
        (crontab(minute="*/5"), "es", "Cada 5 min"),
        (crontab(minute="*/5"), "pt", "A cada 5 min"),
        (crontab(minute=17), "es", ":17"),
        (crontab(minute=0), "es", ":00 · en punto"),
        (crontab(minute=0), "pt", ":00 · hora cheia"),
        (crontab(hour=6, minute=30), "es", "6:30"),
        (crontab(day_of_month=3, hour=5, minute=0), "es", "Día 3, 5:00"),
        (crontab(day_of_month=3, hour=5, minute=0), "pt", "Dia 3, 5:00"),
    ]
    for calendario, idioma, texto in casos:
        assert manual.cuando(calendario, idioma)[2] == texto


def test_el_reloj_trae_todas_sus_tareas_y_el_respaldo(base_de_pruebas):
    from app.celery_app import celery
    with Session(base_de_pruebas) as db:
        filas = manual.reloj(db, "es")
    assert len(filas) == len(celery.conf.beat_schedule) + 1
    assert [x for x in filas if x.get("fuera")][0]["cuando"] == "2:30"
    # En orden: todo el dia, cada hora, cada dia, cada mes.
    grupos = [x["grupo"] for x in filas]
    assert grupos == sorted(grupos, key=["siempre", "hora", "dia", "mes"].index)


def test_cada_mensaje_tiene_su_area():
    """Un archivo nuevo con «no se puede» y sin su area en el manual no
    pasa: sus mensajes se quedarian fuera sin que nadie lo viera."""
    cosecha = manual.cosechar()
    assert len(cosecha) > 100
    sin_area = sorted({x["archivo"] for x in cosecha if not x["area"]})
    assert not sin_area, sin_area
    assert set(manual.AREA_DE_ARCHIVO.values()) <= set(manual.AREAS)
    mensajes = manual.mensajes("pt")
    assert len(mensajes) == len(cosecha)
    assert all(x["area_titulo"] for x in mensajes)


def test_la_llave_maestra_esta_entre_los_mensajes():
    textos = [x["mensaje"] for x in manual.mensajes("es")]
    assert any("llave maestra" in x for x in textos)
    # Lo que se arma con datos del caso sale como «…».
    assert any("…" in x for x in textos)


def test_cada_seccion_nueva_trae_su_novedad():
    """Cada seccion de la bitacora desde la 77 trae su novedad, en los dos
    idiomas y con la misma fecha: es lo que obliga a que el manual se
    ponga al dia con cada actualizacion."""
    es = {n["seccion"]: n["fecha_iso"] for n in manual.novedades("es")}
    pt = {n["seccion"]: n["fecha_iso"] for n in manual.novedades("pt")}
    assert es == pt
    # La version es la novedad mas nueva por fecha --y por seccion el
    # mismo dia--, no la de numero mas alto (seccion 150).
    assert manual.version("es")["seccion"] == max(es, key=lambda s: (es[s], s))
    if not os.path.exists(BITACORA):
        pytest.skip("la bitacora no viaja en la imagen del servidor")
    secciones = {int(x) for x in re.findall(r"^## (\d+)\. ",
                                            open(BITACORA, encoding="utf-8").read(),
                                            re.M)}
    faltan = sorted(s for s in secciones if s >= DESDE and s not in es)
    assert not faltan, f"secciones sin su novedad: {faltan}"
    assert set(es) <= secciones, "hay novedades de secciones que no existen"


def test_quien_puede_que(base_de_pruebas):
    with Session(base_de_pruebas) as db:
        p = manual.permisos_del_sistema(db)
    manual_ver = next(a for a in p["actividades"] if a["actividad"] == "manual.ver")
    assert manual_ver["roles"] == ["admin", "sistema_calidad"]
    assert len(p["dos_manos"]) == 5
    assert all(len(par) == 2 for par in p["dos_manos"])


# ====================================================== la pantalla

@pytest.mark.parametrize("quien,codigo", [
    ("dirgeneral", 200), ("admin", 200), ("diroperaciones", 403),
    ("consultor", 403), ("central", 403), ("finanzas", 403), ("rrhh", 403)])
def test_quien_lo_lee(cliente, sesion, quien, codigo):
    assert cliente.get("/manual", headers=sesion(quien)).status_code == codigo
    assert cliente.get("/manual/estado", headers=sesion(quien)).status_code == codigo


def test_el_manual_en_el_idioma_de_quien_lo_lee(cliente, sesion):
    h = sesion("dirgeneral")
    es = cliente.get("/manual", headers=h).json()
    assert es["idioma"] == "es" and es["en_otro_idioma"] is False
    assert es["version"]["seccion"] >= 90
    assert es["capitulos"][0]["titulo"] == "Las piezas del sistema y cómo se hablan"
    assert {"reloj", "mensajes", "areas", "permisos", "novedades", "casos"} <= set(es)

    pt = cliente.get("/manual?idioma=pt", headers=h).json()
    assert pt["idioma"] == "pt" and pt["en_otro_idioma"] is False
    assert pt["capitulos"][0]["titulo"] == "As peças do sistema e como elas se falam"
    assert pt["version"]["fecha"] == manual.fecha_corta(pt["version"]["fecha_iso"], "pt")

    # En ingles se lee en espanol, y la pantalla lo avisa.
    en = cliente.get("/manual?idioma=en", headers=h).json()
    assert en["idioma"] == "es" and en["en_otro_idioma"] is True


def test_el_estado_del_sistema(cliente, sesion):
    r = cliente.get("/manual/estado?idioma=pt", headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text
    tarjetas = r.json()["tarjetas"]
    assert [x["clave"] for x in tarjetas] == ["base", "reloj", "correo", "odoo",
                                               "gps", "avisos"]
    base = tarjetas[0]
    assert base["tono"] == "ok" and base["titulo"] == "Banco de dados"
    # Sin ninguna vuelta anotada, el reloj lo dice.
    reloj = tarjetas[1]
    assert reloj["tono"] == "alerta" and reloj["etiqueta"] == "Sem voltas anotadas"


# ====================================================== la ultima vuelta

def _tarea(nombre: str) -> str:
    from app.celery_app import celery
    return celery.conf.beat_schedule[nombre]["task"]


def _fila(db, clave, idioma="es"):
    return next(x for x in manual.reloj(db, idioma) if x["clave"] == clave)


def test_el_reloj_anota_su_vuelta(base_de_pruebas):
    ahora = datetime.now(timezone.utc)
    tarea = _tarea("correo-pendiente")
    with Session(base_de_pruebas) as db:
        manual.anotar_vuelta(tarea, empezo=ahora, db=db)
        assert _fila(db, "correo-pendiente")["ultima"]["vueltas"] == 0
        manual.anotar_vuelta(tarea, termino=ahora, db=db)
        manual.anotar_vuelta(tarea, termino=ahora, db=db)
        v = _fila(db, "correo-pendiente")["ultima"]
        assert v["estado"] == "ok" and v["vueltas"] == 2 and v["error"] is None

        # Un error se queda con su hora, aunque la siguiente salga bien:
        # un error de anoche explica un hueco de hoy.
        manual.anotar_vuelta(tarea, termino=ahora, error="se cayo", db=db)
        v = _fila(db, "correo-pendiente")["ultima"]
        assert v["estado"] == "error" and v["error"] == "se cayo"
        manual.anotar_vuelta(tarea, termino=ahora, db=db)
        v = _fila(db, "correo-pendiente")["ultima"]
        assert v["estado"] == "ok" and v["error"] == "se cayo"


def test_la_tarjeta_del_reloj(base_de_pruebas):
    ahora = datetime.now(timezone.utc)
    with Session(base_de_pruebas) as db:
        manual.anotar_vuelta(_tarea("gps-leer"), termino=ahora, db=db)
        reloj = manual.estado(db, "es", ahora=ahora)[1]
        assert reloj["tono"] == "ok", reloj

        manual.anotar_vuelta(_tarea("odoo-flota"), termino=ahora,
                             error="Odoo no contesta", db=db)
        reloj = manual.estado(db, "es", ahora=ahora)[1]
        assert reloj["tono"] == "alerta" and "Odoo" in reloj["texto"], reloj

        # Doce minutos sin que termine ninguna, y el reloj esta parado.
        reloj = manual.estado(db, "es", ahora=ahora + timedelta(minutes=20))[1]
        assert reloj["tono"] == "grave" and reloj["etiqueta"] == "Parado", reloj


def test_la_senal_del_reloj_anota_sola(base_de_pruebas):
    """El propio reloj anota cada vuelta al empezar y al terminar; la
    lectura que espera su primera vez a mano lo dice con su nota."""
    from app import celery_app

    class Tarea:
        name = _tarea("odoo-personal")

    celery_app._empieza(task=Tarea())
    celery_app._termina(task=Tarea(), state="SUCCESS",
                        retval={"omitido": "falta la primera sincronizacion a mano"})
    with Session(base_de_pruebas) as db:
        v = _fila(db, "odoo-personal", "pt")["ultima"]
        assert v["vueltas"] == 1 and v["estado"] == "ok"
        assert v["nota"] == "Espera a primeira leitura à mão"

    celery_app._termina(task=Tarea(), state="FAILURE", retval=ValueError("sin llave"))
    with Session(base_de_pruebas) as db:
        v = _fila(db, "odoo-personal")["ultima"]
        assert v["estado"] == "error" and v["error"] == "ValueError: sin llave"


# ====================================================== los casos resueltos

CASO = {"titulo": "La flota no llegaba de Odoo",
        "que_se_vio": "Las unidades no se podian asignar.",
        "causa": "La lectura de la flota nunca se habia aplicado a mano.",
        "solucion": "Ensayo y aplicar en la pantalla de Odoo.",
        "area": "odoo", "falla": "no"}


def test_un_caso_se_anota_y_se_corrige(cliente, sesion):
    h = sesion("dirgeneral")
    r = cliente.post("/manual/casos", json=CASO, headers=h)
    assert r.status_code == 201, r.text
    caso = r.json()
    assert caso["titulo"] == CASO["titulo"] and caso["falla"] == "no"
    assert caso["escrito_por"] and caso["editado_en"] is None

    r = cliente.patch(f"/manual/casos/{caso['id']}",
                      json={"solucion": "  Ensayo, aplicar y esperar a los :27.  ",
                            "falla": "si"}, headers=h)
    assert r.status_code == 200, r.text
    corregido = r.json()
    assert corregido["solucion"] == "Ensayo, aplicar y esperar a los :27."
    assert corregido["falla"] == "si" and corregido["titulo"] == CASO["titulo"]
    assert corregido["editado_por"] and corregido["editado_en"]

    todos = cliente.get("/manual/casos", headers=h).json()
    assert [c["id"] for c in todos] == [caso["id"]]
    assert cliente.get("/manual", headers=h).json()["casos"][0]["id"] == caso["id"]


def test_un_caso_sin_la_causa_es_una_queja(cliente, sesion):
    h = sesion("dirgeneral")
    r = cliente.post("/manual/casos", json={**CASO, "causa": "   "}, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"]["mensaje"].startswith("Falta la causa")

    r = cliente.post("/manual/casos", json={**CASO, "falla": "quizas"}, headers=h)
    assert r.status_code == 422
    assert "falla del sistema" in r.json()["detail"]["mensaje"]

    r = cliente.post("/manual/casos", json={**CASO, "titulo": "x" * 161}, headers=h)
    assert r.status_code == 422

    r = cliente.post("/manual/casos", json=CASO, headers=h)
    r = cliente.patch(f"/manual/casos/{r.json()['id']}", json={"que_se_vio": ""},
                      headers=h)
    assert r.status_code == 422
    assert cliente.patch("/manual/casos/999999", json={"causa": "x"},
                         headers=h).status_code == 404


def test_los_casos_los_anota_quien_lee_el_manual(cliente, sesion):
    r = cliente.post("/manual/casos", json=CASO, headers=sesion("consultor"))
    assert r.status_code == 403

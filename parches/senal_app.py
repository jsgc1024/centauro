# -*- coding: utf-8 -*-
"""La senal del principal, en el telefono del equipo.

Pedido de Salvador, 22 sep: «a la hora de arribo, el equipo de seguridad
debera mostrar la senal desde su telefono celular. La app debera tener
un icono desde el servicio que le abra la senal como una imagen y pueda
ocupar toda la pantalla del telefono».

La senal ya existia --texto, imagen y nota en el servicio, capturada en
la consola y puesta en el task sheet--. Lo que entra aqui:

  * la ficha del dia dice si hay senal (texto, nota, si trae imagen),
    sin cargar la imagen: la ficha se guarda en el telefono;
  * un endpoint que da la imagen como imagen, solo a quien va en ese
    servicio;
  * en la app: el icono junto al ejecutivo (hoy y manana), la pantalla
    completa, la pantalla que no se apaga, y la imagen guardada en el
    telefono para abrirla sin barras;
  * el acento que faltaba en el portugues de «Ja estou com o Principal».

Idempotente y con todas las escrituras al final.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    "campo": B / "app/routers/campo.py",
    "app": B / "app/web/campo/app.js",
    "css": B / "app/web/campo/estilo.css",
    "sw": B / "app/web/campo/sw.js",
    "idioma": B / "app/web/idioma.js",
}
NUEVO = B / "tests/test_campo_senal.py"

textos = {k: io.open(v, encoding="utf-8").read() for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(viejo) == 1, f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces"
    textos[clave] = t.replace(viejo, nuevo)


# ================================================================ backend
cambiar("campo", "import logging\n", "import base64\nimport logging\n")
cambiar("campo",
        "from fastapi import APIRouter, Depends, HTTPException\n",
        "from fastapi import APIRouter, Depends, HTTPException\n"
        "from fastapi.responses import RedirectResponse, Response\n")

cambiar("campo", '''        "vestimenta": (servicio.vestimenta
                       if servicio.tipo == m.TipoServicio.EVENTUAL else None),
        "equipo": jornada.equipo.alias,
''', '''        "vestimenta": (servicio.vestimenta
                       if servicio.tipo == m.TipoServicio.EVENTUAL else None),
        # La senal con la que el principal reconoce al equipo. Solo lo
        # ligero: el texto, la nota y si hay imagen. La imagen va aparte
        # (`/campo/servicios/{id}/senal/imagen`) porque puede pesar
        # megas y esta ficha se guarda en el telefono para leerse sin
        # senal: meterla aqui reventaria esa memoria.
        "senal": ({"texto": servicio.senal_texto,
                   "nota": servicio.senal_nota,
                   "imagen": bool(servicio.senal_imagen)}
                  if (servicio.senal_texto or servicio.senal_imagen)
                  else None),
        "equipo": jornada.equipo.alias,
''', marca='"senal": ({"texto": servicio.senal_texto,')

cambiar("campo", '''@router.get("/mi-dia", summary="El dia del equipo, completo")
''', '''@router.get("/servicios/{servicio_id}/senal/imagen",
            summary="La imagen de la senal, para levantarla en el telefono")
def imagen_de_la_senal(servicio_id: int, db: Session = Depends(get_db),
                       usuario: m.Usuario = Depends(CAMPO)):
    """Lo que el equipo levanta en la pantalla cuando sale el principal.

    Va como imagen de verdad --no como data URI dentro de un JSON-- para
    que la app la guarde en el telefono y la abra sin senal: a la salida
    del filtro de un aeropuerto no hay barras, y ese es exactamente el
    momento en que se necesita.

    Solo para quien va en ese servicio. La senal identifica al equipo
    ante el principal; en manos de otro es una forma de hacerse pasar
    por el equipo.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    va = (db.query(m.AsignacionPersonal)
          .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
          .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
          .filter(m.Equipo.servicio_id == servicio.id,
                  m.AsignacionPersonal.persona_id == usuario.persona_id)
          .first())
    if not va:
        raise HTTPException(403, "No vas en ese servicio")
    if not servicio.senal_imagen:
        raise HTTPException(404, "Ese servicio no tiene imagen de senal")

    imagen = servicio.senal_imagen
    if not imagen.startswith("data:"):
        # Se capturo como enlace: que el telefono la traiga de ahi.
        return RedirectResponse(imagen, status_code=307)
    tipo, _, contenido = imagen.partition(";base64,")
    return Response(content=base64.b64decode(contenido),
                    media_type=tipo[len("data:"):] or "image/jpeg",
                    # La app la guarda ella misma en el telefono; el
                    # navegador no tiene que guardar nada por su cuenta.
                    headers={"Cache-Control": "private, no-store"})


@router.get("/mi-dia", summary="El dia del equipo, completo")
''')

# ================================================================ la app
cambiar("app", '''  const datos = r.datos;
  const hoy = datos.hoy || [];
  const manana = datos.manana || [];
''', '''  const datos = r.datos;
  const hoy = datos.hoy || [];
  const manana = datos.manana || [];

  /* Con red, la senal se guarda en el telefono desde ahora: donde se
     usa --a la salida del filtro-- ya no hay con que bajarla. */
  if (!r.de_memoria) guardarSenales([...hoy, ...manana]);
''')

# hoy: junto al ejecutivo
cambiar("app", '''      h("div", { clase: "dato" },
        h("span", { clase: "clave" }, t("cmp_ejecutivo")),
        f.ejecutivo || "—"),
      /* Como hay que ir vestido. Si el servicio no trae codigo no se
         pinta el renglon: un servicio sin acuerdo no es "casual". */
''', '''      h("div", { clase: "dato" },
        h("span", { clase: "clave" }, t("cmp_ejecutivo")),
        f.ejecutivo || "—"),
      senalDelDia(f),
      /* Como hay que ir vestido. Si el servicio no trae codigo no se
         pinta el renglon: un servicio sin acuerdo no es "casual". */
''', marca="senalDelDia(f),")

# manana: su propio marco, debajo de la vestimenta
cambiar("app", '''      : null,
    /* El inventario de la unidad tambien vive aqui. Decision de
       Salvador, 20 sep.
''', '''      : null,
    /* La senal tambien: la noche anterior es cuando se ve por primera
       vez, y abrirla con red es lo que la deja guardada en el telefono
       para la manana siguiente. */
    f.senal ? h("div", { clase: "marco" }, senalDelDia(f)) : null,
    /* El inventario de la unidad tambien vive aqui. Decision de
       Salvador, 20 sep.
''')

cambiar("app", '''/* ------------------------------------------------------- el panico */
''', '''/* ------------------------------------------------------- la senal */

/* La senal con la que el principal reconoce al equipo: una palabra, una
   imagen o las dos. La captura el consultor en el servicio y sale en el
   task sheet; aqui es lo que se levanta en la pantalla a la salida del
   filtro. Pedido de Salvador, 22 sep.

   La imagen NO viaja dentro de la ficha del dia --puede pesar megas y
   la ficha vive en localStorage, que no los aguanta--. Se baja aparte,
   con la sesion puesta, y se guarda en `caches`, que si aguanta y que
   el trabajador de fondo respeta al cambiar de version (ver sw.js).
   Donde se usa no hay barras: por eso se baja al cargar el dia y no al
   abrirla. */
const SENAL_CACHE = "centauro-senal";
const senalesEnMemoria = new Map();
const SENAL_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
  + 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
  + '<rect x="3" y="4" width="18" height="12" rx="2"/>'
  + '<path d="M12 16v4M8 20h8"/></svg>';

function rutaDeLaSenal(servicioId) {
  return `/campo/servicios/${servicioId}/senal/imagen`;
}

async function cacheDeSenales() {
  try { return ("caches" in window) ? await caches.open(SENAL_CACHE) : null; }
  catch { return null; }
}

/* Baja la imagen con la sesion puesta --una etiqueta <img> no manda el
   token, y el token nunca va en la direccion-- y la guarda. */
async function bajarSenal(servicioId) {
  const ruta = rutaDeLaSenal(servicioId);
  const cab = sesion.token ? { Authorization: `Bearer ${sesion.token}` } : {};
  const r = await fetch(ruta, { headers: cab });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const blob = await r.blob();
  senalesEnMemoria.set(servicioId, blob);
  const cache = await cacheDeSenales();
  if (cache) {
    try {
      await cache.put(ruta, new Response(blob, {
        headers: { "Content-Type": blob.type || "image/jpeg" } }));
    } catch { /* sin espacio: se queda en memoria mientras la app viva */ }
  }
  return blob;
}

/* Primero lo guardado, luego la red. Sin ninguna de las dos, null. */
async function traerSenal(servicioId) {
  if (senalesEnMemoria.has(servicioId)) return senalesEnMemoria.get(servicioId);
  const cache = await cacheDeSenales();
  if (cache) {
    const guardada = await cache.match(rutaDeLaSenal(servicioId));
    if (guardada) {
      const blob = await guardada.blob();
      senalesEnMemoria.set(servicioId, blob);
      return blob;
    }
  }
  try { return await bajarSenal(servicioId); } catch { return null; }
}

function guardarSenales(fichas) {
  for (const f of fichas) {
    if (!f.senal || !f.senal.imagen) continue;
    traerSenal(f.servicio_id).catch(() => {});
  }
}

/* El renglon de la tarjeta: el icono, y debajo la nota del consultor
   --"a la salida del filtro"-- o, si no dejo nota, cuando se usa. */
function senalDelDia(f) {
  if (!f.senal) return null;
  return h("div", { clase: "dato" },
    h("span", { clase: "clave" }, t("cmp_senal")),
    h("button", { clase: "claro chico senal-boton",
                  onclick: (e) => { e.preventDefault(); abrirSenal(f); } },
      h("span", { clase: "senal-icono", html: SENAL_SVG }),
      t("cmp_senal_ver")),
    h("div", { clase: "chico gris", style: "margin-top:6px" },
      f.senal.nota || t("cmp_senal_pie")));
}

let senalAbierta = null;

/* A pantalla completa: blanco, y la imagen ocupando todo lo que el
   telefono de, vertical u horizontal. Si solo hay palabra, la palabra
   en letras enormes; si hay las dos, la imagen arriba y la palabra
   abajo. Mientras esta abierta la pantalla no se apaga: el equipo la
   sostiene en alto esperando a que salga el principal. */
async function abrirSenal(f) {
  cerrarSenal();
  const pantalla = h("div", { clase: "senal-pantalla", onclick: cerrarSenal });
  const cerrar = h("button", {
    clase: "senal-cerrar", "aria-label": t("cmp_senal_cerrar"),
    onclick: (e) => { e.stopPropagation(); cerrarSenal(); } }, "✕");
  pantalla.append(cerrar);
  document.body.append(pantalla);
  document.body.classList.add("senal-abierta");
  const abierta = { nodo: pantalla, url: null, candado: null, alGirar: null };
  senalAbierta = abierta;

  try {
    if (navigator.wakeLock) {
      abierta.candado = await navigator.wakeLock.request("screen");
    }
  } catch { /* sin permiso o sin soporte: se muestra igual */ }

  const partes = [];
  if (f.senal.imagen) {
    const espera = h("div", { clase: "senal-texto chico" }, t("cmp_senal_cargando"));
    pantalla.append(espera);
    const blob = await traerSenal(f.servicio_id);
    if (senalAbierta !== abierta) return;        // la cerraron mientras cargaba
    espera.remove();
    if (blob) {
      abierta.url = URL.createObjectURL(blob);
      partes.push(h("img", {
        clase: "senal-imagen" + (f.senal.texto ? " con-texto" : ""),
        src: abierta.url, alt: f.senal.texto || "" }));
    } else {
      partes.push(h("div", { clase: "senal-aviso" }, t("cmp_senal_sin_guardar")));
    }
  }
  if (f.senal.texto) {
    partes.push(h("div", {
      clase: "senal-texto" + (f.senal.imagen ? " con-imagen" : "") }, f.senal.texto));
  }
  pantalla.append(...partes);

  if (f.senal.texto && !f.senal.imagen) {
    const texto = pantalla.querySelector(".senal-texto");
    abierta.alGirar = () => ajustarSenal(texto);
    window.addEventListener("resize", abierta.alGirar);
    ajustarSenal(texto);
  }
}

/* La palabra lo mas grande que quepa, y no mas. */
function ajustarSenal(nodo) {
  if (!nodo) return;
  let tam = Math.round(Math.min(window.innerWidth, window.innerHeight) * 0.34);
  nodo.style.fontSize = `${tam}px`;
  const cabe = () => nodo.scrollHeight <= window.innerHeight * 0.88;
  while (!cabe() && tam > 28) {
    tam -= 4;
    nodo.style.fontSize = `${tam}px`;
  }
}

function cerrarSenal() {
  if (!senalAbierta) return;
  const { nodo, url, candado, alGirar } = senalAbierta;
  senalAbierta = null;
  nodo.remove();
  document.body.classList.remove("senal-abierta");
  if (alGirar) window.removeEventListener("resize", alGirar);
  if (url) URL.revokeObjectURL(url);
  if (candado) candado.release().catch(() => {});
}

/* ------------------------------------------------------- el panico */
''', marca="const SENAL_CACHE")

# ================================================================ estilos
cambiar("css", '''/* La franja de deshacer: justo encima de la barra, que es donde el
   pulgar acaba de estar. Nunca encima del boton de panico. */
''', '''/* La senal a pantalla completa: blanco y nada mas. Encima de todo, la
   barra y el panico incluidos: mientras se levanta, no hay otra cosa
   que hacer con el telefono. */
.senal-pantalla {
  position: fixed; inset: 0; z-index: 60;
  background: #fff; color: #000;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 10px;
  padding: 12px;
  padding-top: max(12px, env(safe-area-inset-top));
  padding-bottom: max(12px, env(safe-area-inset-bottom));
}
body.senal-abierta { overflow: hidden; }
.senal-imagen {
  max-width: 100%; max-height: 100%; min-height: 0;
  object-fit: contain;
}
.senal-imagen.con-texto { max-height: 72%; }
.senal-texto {
  width: 100%; text-align: center;
  font-weight: 800; line-height: 1; word-break: break-word;
  font-size: clamp(36px, 15vw, 220px);
}
.senal-texto.con-imagen { font-size: clamp(24px, 9vw, 80px); }
.senal-texto.chico { font-size: 16px; font-weight: 500; color: var(--gris); }
.senal-aviso { font-size: 16px; color: var(--grave); text-align: center; max-width: 320px; }
.senal-cerrar {
  position: absolute; right: 10px; top: max(10px, env(safe-area-inset-top));
  width: 44px; min-height: 44px; padding: 0; border-radius: 999px;
  background: rgba(0, 0, 0, .08); color: #000; font-size: 20px;
}
.senal-boton { display: inline-flex; align-items: center; gap: 8px; margin-top: 4px; }
.senal-icono { display: inline-flex; width: 18px; height: 18px; }
.senal-icono svg { width: 100%; height: 100%; }

/* La franja de deshacer: justo encima de la barra, que es donde el
   pulgar acaba de estar. Nunca encima del boton de panico. */
''', marca=".senal-pantalla {")

# ================================================================ sw.js
cambiar("sw", 'const CACHE = "centauro-campo-v6";', 'const CACHE = "centauro-campo-v7";')
cambiar("sw", '''      llaves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
''', '''      /* El cache de la senal del principal es de la app, no del
         armazon: cambiar de version no lo tira. Se necesita justo
         donde no hay red para volver a bajarla. */
      llaves.filter((k) => k !== CACHE && k !== "centauro-senal")
            .map((k) => caches.delete(k))))
''')

# ================================================================ idioma
cambiar("idioma", '''    cmp_deshacer: "Deshacer",
''', '''    cmp_deshacer: "Deshacer",
    cmp_senal: "Señal",
    cmp_senal_ver: "Ver la señal",
    cmp_senal_pie: "Levántala en la pantalla cuando salga el principal.",
    cmp_senal_cerrar: "Cerrar",
    cmp_senal_cargando: "Trayendo la señal…",
    cmp_senal_sin_guardar: "La imagen no está en el teléfono y no hay señal de red. Ábrela una vez con red y se queda guardada.",
''')
cambiar("idioma", '''    cmp_deshacer: "Undo",
''', '''    cmp_deshacer: "Undo",
    cmp_senal: "Sign",
    cmp_senal_ver: "Show the sign",
    cmp_senal_pie: "Hold it up on the screen when the principal comes out.",
    cmp_senal_cerrar: "Close",
    cmp_senal_cargando: "Loading the sign…",
    cmp_senal_sin_guardar: "The image is not on the phone and there is no signal. Open it once with signal and it stays saved.",
''')
cambiar("idioma", '''    cmp_deshacer: "Desfazer",
''', '''    cmp_deshacer: "Desfazer",
    cmp_senal: "Sinal",
    cmp_senal_ver: "Ver o sinal",
    cmp_senal_pie: "Levante-o na tela quando o principal sair.",
    cmp_senal_cerrar: "Fechar",
    cmp_senal_cargando: "Carregando o sinal…",
    cmp_senal_sin_guardar: "A imagem não está no telefone e não há sinal. Abra uma vez com sinal e ela fica guardada.",
''')
cambiar("idioma", 'cmp_hito_contacto: "Ja estou com o Principal",',
        'cmp_hito_contacto: "Já estou com o Principal",')

# ================================================================ la prueba
PRUEBA = '''"""La senal con la que el principal reconoce al equipo, en el telefono.

Ya existia en el servicio y en el task sheet. Pedido de Salvador, 22 sep:
que el equipo la levante desde su telefono, a pantalla completa, a la
hora del arribo.
"""
import base64

from ayudas import PIXEL
from test_campo import _servicio_de_juan

PNG = "data:image/png;base64," + base64.b64encode(PIXEL).decode()


def _con_senal(cliente, sesion, datos, **senal):
    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = cliente.put(f"/servicios/{servicio['id']}/senal", json=senal,
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return servicio, j


def _ficha(cliente, sesion, servicio):
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    return next(f for f in dia["hoy"] if f["servicio_id"] == servicio["id"])


def test_la_ficha_dice_que_hay_senal_sin_cargar_la_imagen(cliente, sesion,
                                                          datos):
    """La ficha se guarda en el telefono: trae el texto, la nota y si hay
    imagen, pero la imagen no. Esa se baja aparte."""
    servicio, _ = _con_senal(cliente, sesion, datos, texto="CARTER",
                             imagen=PNG, nota="A la salida del filtro")
    f = _ficha(cliente, sesion, servicio)
    assert f["senal"] == {"texto": "CARTER", "nota": "A la salida del filtro",
                          "imagen": True, "color": None}
    assert "base64" not in str(f), "la imagen viajo dentro de la ficha"


def test_sin_senal_la_ficha_no_inventa_una(cliente, sesion, datos):
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    assert _ficha(cliente, sesion, servicio)["senal"] is None


def test_la_imagen_baja_como_imagen_y_solo_para_quien_va(cliente, sesion,
                                                         datos):
    """Como imagen de verdad, para que el telefono la guarde. Y solo a
    quien va en ese servicio: en manos de otro, la senal es una forma de
    hacerse pasar por el equipo."""
    servicio, _ = _con_senal(cliente, sesion, datos, imagen=PNG)
    ruta = f"/campo/servicios/{servicio['id']}/senal/imagen"

    r = cliente.get(ruta, headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png"), r.headers
    assert r.content == PIXEL

    r = cliente.get(ruta, headers=sesion("luis"))
    assert r.status_code == 403, r.text


def test_si_la_senal_es_solo_una_palabra_no_hay_imagen_que_bajar(cliente,
                                                                 sesion, datos):
    servicio, _ = _con_senal(cliente, sesion, datos, texto="CARTER")
    f = _ficha(cliente, sesion, servicio)
    assert f["senal"]["imagen"] is False
    r = cliente.get(f"/campo/servicios/{servicio['id']}/senal/imagen",
                    headers=sesion("juan"))
    assert r.status_code == 404, r.text
'''

# ================================================================ escrituras
for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(textos[clave])
        print("escrito ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
if NUEVO.exists() and io.open(NUEVO, encoding="utf-8").read() == PRUEBA:
    print("sin cambio", NUEVO.relative_to(RAIZ))
else:
    with io.open(NUEVO, "w", encoding="utf-8") as f:
        f.write(PRUEBA)
    print("escrito ", NUEVO.relative_to(RAIZ))
for s in saltados:
    print("saltado:", s)

"""Las fuentes con las que arranca el lector (seccion 140).

Una primera lista para que la Central la revise: busquedas de Google
Noticias por tema (todo el pais, cada 15 minutos) y por estado (cada
hora), y medios con RSS. La lista de X la agrega la Central desde la
pantalla, con la direccion de su lista. Lo que no sirva se apaga ahi
mismo; lo que falte se agrega.
"""
from app.riesgo_catalogo import REGIONES

# Lo que se busca por estado: lo que cambia un traslado.
POR_ESTADO = ("(balacera OR bloqueo OR enfrentamiento OR \"ataque armado\" "
              "OR asalto OR narcobloqueo) \"{estado}\"")

TEMAS = (
    ("Google Noticias · bloqueos carreteros",
     "\"bloqueo carretero\" OR narcobloqueo OR \"bloquean la carretera\" "
     "OR \"bloquean la autopista\""),
    ("Google Noticias · balaceras y enfrentamientos",
     "balacera OR enfrentamiento OR \"ataque armado\" OR emboscada"),
    ("Google Noticias · robo a transporte",
     "\"robo a transporte\" OR \"asalto a transportistas\" OR "
     "\"robo de tráiler\" OR \"robo de tractocamión\""),
    ("Google Noticias · secuestros",
     "secuestro OR \"privan de la libertad\" OR levantón"),
    ("Google Noticias · marchas y cierres",
     "marcha OR manifestación OR bloqueo cierre vialidad"),
    ("Google Noticias · Protección Civil",
     "\"Protección Civil\" cierre carretera OR deslave OR inundación"),
)

# (nombre, RSS, estados que cubre; vacio = nacional)
MEDIOS = (
    ("Infobae México",
     "https://www.infobae.com/arc/outboundfeeds/rss/category/mexico/", ()),
    ("El Universal",
     "https://www.eluniversal.com.mx/arc/outboundfeeds/rss/?outputType=xml",
     ()),
    ("Zeta Tijuana", "https://zetatijuana.com/feed/", ("Baja California",)),
    ("El Sur de Acapulco", "https://suracapulco.mx/feed/", ("Guerrero",)),
)

# Los medios cuyo RSS no deja leer al servidor (lo cambiaron, lo cierran
# o contesta con error, seccion 144) se leen por Google Noticias con
# «site:»: trae lo suyo del ultimo dia y pasa por el mismo filtro.
POR_GOOGLE = (
    ("Animal Político", "site:animalpolitico.com", ()),
    ("Aristegui Noticias", "site:aristeguinoticias.com", ()),
    ("Pie de Página", "site:piedepagina.mx", ()),
    ("Ríodoce", "site:riodoce.mx", ("Sinaloa",)),
    ("Quadratín Michoacán", "site:quadratin.com.mx", ("Michoacán",)),
)


def iniciales() -> list[dict]:
    salida = [{"tipo": "busqueda", "nombre": n, "direccion": q,
               "regiones": [], "cada_min": 15} for n, q in TEMAS]
    for _, estado in REGIONES["MX"]:
        salida.append({"tipo": "busqueda",
                       "nombre": f"Google Noticias · {estado}",
                       "direccion": POR_ESTADO.format(estado=estado),
                       "regiones": [estado], "cada_min": 60})
    for nombre, rss, estados in MEDIOS:
        salida.append({"tipo": "medio", "nombre": nombre, "direccion": rss,
                       "regiones": list(estados), "cada_min": 15})
    for nombre, sitio, estados in POR_GOOGLE:
        salida.append({"tipo": "busqueda", "nombre": nombre,
                       "direccion": sitio, "regiones": list(estados),
                       "cada_min": 15})
    return salida

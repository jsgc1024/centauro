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
    ("Animal Político", "https://animalpolitico.com/feed/", ()),
    ("Aristegui Noticias", "https://aristeguinoticias.com/feed/", ()),
    ("Infobae México",
     "https://www.infobae.com/arc/outboundfeeds/rss/category/mexico/", ()),
    ("El Universal",
     "https://www.eluniversal.com.mx/arc/outboundfeeds/rss/?outputType=xml",
     ()),
    ("Pie de Página", "https://piedepagina.mx/feed/", ()),
    ("Ríodoce", "https://riodoce.mx/feed/", ("Sinaloa",)),
    ("Zeta Tijuana", "https://zetatijuana.com/feed/", ("Baja California",)),
    ("Quadratín Michoacán", "https://www.quadratin.com.mx/feed/",
     ("Michoacán",)),
    ("El Sur de Acapulco", "https://suracapulco.mx/feed/", ("Guerrero",)),
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
    return salida

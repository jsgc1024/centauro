"""Paso A: el candado de contingencia cambia de forma.

Antes: "implantado prohibido". Ahora: "implantado, pero con fecha de
fin". Eventual pasa sin fin y no cambia en nada.
"""
import pathlib

RUTA = pathlib.Path(__file__).resolve().parent.parent / "backend/app/contingencia.py"
s = RUTA.read_text()

VIEJA = '''def _solo_eventual(desde: m.Jornada) -> None:
    """Este motor es de eventual. El implantado tiene el suyo.

    No es una separacion de gusto: el implantado reutiliza el mismo
    equipo mes tras mes, asi que un cambio "de aqui en adelante" barreria
    todas las jornadas abiertas —el mes en curso y el siguiente, si ya se
    genero— y abriria decenas de viaticos de un solo clic. Su reemplazo
    va dia por dia, en `implantado.cambiar_personal`, y ahi es donde hay
    que hacerlo.
    """
    servicio = desde.equipo.servicio if desde.equipo else None
    if servicio and servicio.tipo == m.TipoServicio.IMPLANTADO:
        raise HTTPException(409, {
            "mensaje": ("El cambio de recurso de un implantado se hace desde "
                        "su propio calendario, dia por dia."),
            "servicio_id": servicio.id,
        })
'''

NUEVA = '''def _tramo_con_fin(desde: m.Jornada, hasta: m.Jornada | None) -> None:
    """El implantado no admite un cambio sin fecha de fin.

    Antes este candado decia "implantado prohibido" y mandaba a cada tipo
    de servicio a su propio motor. Dos motores para la misma regla se
    separan con el tiempo, y se separaron: el del implantado mutaba la
    asignacion y el que trabajo media jornada cobraba cero.

    Lo que el candado protegia era otra cosa, y esa sigue en pie: el
    implantado reutiliza el mismo equipo mes tras mes, asi que un cambio
    "de aqui en adelante" barreria todas las jornadas abiertas —el mes en
    curso y el siguiente, si ya se genero— y abriria decenas de viaticos
    de un solo clic. Con fecha de fin eso no puede pasar, y la fecha la
    pone `implantado.cambiar_recurso`: el ultimo dia del mes en curso.

    El eventual sigue entrando sin fin, porque una contingencia no lo
    tiene: nadie sabe cuando vuelve el que salio.
    """
    servicio = desde.equipo.servicio if desde.equipo else None
    if servicio and servicio.tipo == m.TipoServicio.IMPLANTADO and hasta is None:
        raise HTTPException(409, {
            "mensaje": ("El cambio de un implantado tiene que decir hasta que "
                        "dia llega. Sin fin se llevaria tambien los meses que "
                        "ya esten abiertos."),
            "servicio_id": servicio.id,
        })
'''

assert s.count(VIEJA) == 1, "no encontre _solo_eventual"
s = s.replace(VIEJA, NUEVA)

# La llamada se mueve: ahora necesita `hasta`, que se resuelve mas abajo.
LLAMADA = '''        raise HTTPException(404, f"No existe la jornada {desde_jornada_id}")
    _solo_eventual(desde)
'''
assert s.count(LLAMADA) == 2, f"esperaba 2 llamadas, hay {s.count(LLAMADA)}"
s = s.replace(LLAMADA, '''        raise HTTPException(404, f"No existe la jornada {desde_jornada_id}")
''')

TOPE = '''    if hasta and hasta.fecha < desde.fecha:
        raise HTTPException(409, "El ultimo dia del cambio es anterior al primero")
'''
assert s.count(TOPE) == 2, f"esperaba 2 topes, hay {s.count(TOPE)}"
s = s.replace(TOPE, TOPE + '''    _tramo_con_fin(desde, hasta)
''')

RUTA.write_text(s)
print("contingencia.py: candado cambiado de forma")

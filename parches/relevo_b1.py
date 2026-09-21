"""Paso B: cambiar_recurso deja de mutar y delega en el motor de relevo."""
import pathlib

RUTA = pathlib.Path(__file__).resolve().parent.parent / "backend/app/implantado.py"
s = RUTA.read_text()

# 1. El import.
VIEJO_IMPORT = """from app import disponibilidad
from app import models as m
from app import reloj
"""
NUEVO_IMPORT = """from app import contingencia
from app import disponibilidad
from app import models as m
from app import reloj
"""
assert s.count(VIEJO_IMPORT) == 1, "no encontre los imports"
s = s.replace(VIEJO_IMPORT, NUEVO_IMPORT)

# 2. El cuerpo entero de cambiar_recurso, de su def hasta el separador
#    de plantilla.
ini = s.index("def cambiar_recurso(")
fin = s.index("# ------------------------------------------------------------- plantilla")
assert ini < fin

NUEVO = '''def ultimo_dia_del_mes(fecha: date) -> date:
    """El tope de un cambio sin fecha de fin."""
    return fecha.replace(day=calendar.monthrange(fecha.year, fecha.month)[1])


def cambiar_recurso(db: Session, servicio_id: int, tipo: m.TipoRecurso,
                    desde: date, hasta: date | None, entra_id: int,
                    motivo_tipo: m.MotivoCambio, hecho_por_id: int | None,
                    sale_id: int | None = None,
                    nota: str | None = None,
                    relevado_en: datetime | None = None) -> dict:
    """Cambia a una persona o una unidad en un tramo de dias.

    Un dia suelto es un rango de un dia: el consultor no tiene que
    aprender dos formas de hacer lo mismo segun si el que falta aviso con
    un mes o con una hora.

    Esta funcion ya no cambia nada por su cuenta. Traduce el tramo de
    fechas a jornadas y se lo entrega al motor de relevo, que es el mismo
    que usa el eventual. Antes tenia su propia copia de la regla y la
    copia estaba mal: mutaba la asignacion, asi que quien trabajo media
    jornada y fue relevado cobraba cero. Dos implementaciones de la misma
    regla se separan con el tiempo, y esta ya se habia separado.

    Lo que si es del implantado es el tope: un cambio sin fecha de fin
    llega al ultimo dia del mes en curso y ahi se detiene. El implantado
    reutiliza el mismo equipo mes tras mes, asi que "de aqui en adelante"
    se llevaria tambien octubre si octubre ya esta abierto, sin que nadie
    lo pida y sin que aparezca en ninguna pantalla. Si hay que extenderlo,
    se vuelve a pedir cuando octubre exista, y queda como otro movimiento
    en el historial.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    if hasta and hasta < desde:
        raise HTTPException(400, "El tramo termina antes de empezar")
    if not sale_id:
        raise HTTPException(409, {
            "mensaje": "Hay que decir quien sale.",
            "que_hacer": ("Antes se tomaba al primero de la lista del dia. "
                          "En una plantilla de tres —un coordinador y dos "
                          "agentes— eso cambiaba al que no era, y el fin de "
                          "semana, cuando la plantilla rota, cambiaba a "
                          "cualquiera."),
        })

    tope = hasta or ultimo_dia_del_mes(desde)
    equipo = servicio.equipos[0] if servicio.equipos else None
    # Los dias ya terminados no se tocan: esos ya los trabajo quien fue.
    dias = sorted([j for j in (equipo.jornadas if equipo else [])
                   if j.estatus not in (m.EstatusJornada.CANCELADA,
                                        m.EstatusJornada.TERMINADA)
                   and j.fecha >= desde and j.fecha <= tope],
                  key=lambda j: j.fecha)
    if not dias:
        raise HTTPException(409, "No hay dias en ese tramo")

    if tipo == m.TipoRecurso.PERSONAL:
        sale = db.get(m.Persona, sale_id)
        entra = db.get(m.Persona, entra_id)
        if not sale:
            raise HTTPException(404, f"No existe la persona {sale_id}")
        if not entra:
            raise HTTPException(404, f"No existe la persona {entra_id}")
        hecho = contingencia.reemplazar_personal(
            db, desde_jornada_id=dias[0].id,
            sale_persona_id=sale_id, entra_persona_id=entra_id,
            motivo=(nota or motivo_tipo.value)[:600],
            hecho_por_id=hecho_por_id, motivo_tipo=motivo_tipo,
            hasta_jornada_id=dias[-1].id, relevado_en=relevado_en)
        sale_nombre, entra_nombre = sale.nombre, entra.nombre
    else:
        sale = db.get(m.Vehiculo, sale_id)
        entra = db.get(m.Vehiculo, entra_id)
        if not sale:
            raise HTTPException(404, f"No existe la unidad {sale_id}")
        if not entra:
            raise HTTPException(404, f"No existe la unidad {entra_id}")
        hecho = contingencia.reemplazar_vehiculo(
            db, desde_jornada_id=dias[0].id,
            sale_vehiculo_id=sale_id, entra_vehiculo_id=entra_id,
            motivo=(nota or motivo_tipo.value)[:600],
            hecho_por_id=hecho_por_id, motivo_tipo=motivo_tipo,
            hasta_jornada_id=dias[-1].id, relevado_en=relevado_en)
        sale_nombre, entra_nombre = sale.placa, entra.placa

    db.commit()

    fechas = hecho["jornadas_afectadas"]
    return {
        "resultado": "cambiado", "tipo": tipo.value,
        "reemplazo_id": hecho["reemplazo_id"],
        "dias_cambiados": len(fechas),
        "desde": fechas[0] if fechas else dias[0].fecha.isoformat(),
        "hasta": fechas[-1] if fechas else dias[-1].fecha.isoformat(),
        # Si el consultor no puso fin, el tope lo puso el sistema. La
        # pantalla lo dice en voz alta: "hasta el 30; para octubre hay
        # que volver a pedirlo".
        "tope_automatico": hasta is None,
        "sale": sale_nombre, "entra": entra_nombre,
        "motivo": motivo_tipo.value,
        # Los dias que se partieron: la prueba de que quien trabajo media
        # jornada va a cobrar media jornada.
        "dias_partidos": hecho["jornadas_partidas"],
        "dias_con_choque": hecho["jornadas_con_choque"],
        "relevado_en": hecho["relevado_en"],
        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
        "revision_pendiente": hecho.get("revision_pendiente"),
        "aviso": _aviso_del_dinero(hecho["viaticos"], sale_nombre,
                                   entra_nombre),
    }


def _aviso_del_dinero(viaticos: dict | None, sale: str, entra: str) -> str | None:
    """Lo que el consultor tiene que saber del dinero, en una frase.

    Antes esto era un letrero que le pedia hacer a mano lo que ahora el
    sistema ya hizo: el viatico depositado paso a comprobacion con su
    plazo y el que no se habia transferido se cancelo. Lo que sigue
    siendo suyo es pedir el del que entra, porque el sistema no gasta
    solo.
    """
    if not viaticos:
        return None
    partes = []
    if viaticos.get("a_comprobar"):
        dias = ", ".join(v["fecha"] for v in viaticos["a_comprobar"])
        partes.append(f"{sale} ya tenia dinero depositado ({dias}): quedo en "
                      f"comprobacion con su plazo.")
    if viaticos.get("cancelados"):
        partes.append(f"Se cancelaron {len(viaticos['cancelados'])} viatico(s) "
                      f"de {sale} que todavia no se transferian.")
    if viaticos.get("propuestos"):
        total = sum(v["monto"] for v in viaticos["propuestos"])
        partes.append(f"A {entra} le tocarian ${total:,.2f} por tabulador: "
                      f"hay que solicitarlos.")
    return " ".join(partes) or None


'''

s = s[:ini] + NUEVO + s[fin:]
RUTA.write_text(s)
print("implantado.py: cambiar_recurso ahora delega")

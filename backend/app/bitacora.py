"""La bitacora del dia: una sola columna, cuatro fuentes.

Lo que el cliente dicto, lo que el equipo marco, lo que el sistema
alerto y lo que la central toco a mano. Cada cosa vivia en su tabla y en
su pantalla, y nadie podia ver las cuatro juntas ordenadas por hora
--que es la unica forma de ver donde el plan y la realidad se
separaron--.

Lo que NO trae, a proposito: las lecturas de posicion del trayecto. Esas
existen antes del meet and greet, donde hay una decision que tomar
--reponer a alguien toma hora y media--, y se apagan al marcar la
llegada. Meterlas aqui convertiria esto en un rastreo, que es otra cosa
y necesita otra conversacion.
"""
from datetime import date, datetime, time

from sqlalchemy.orm import Session

from app import gps
from app import models as m
from app import reloj

# Cada renglon dice de donde salio. La pantalla los dibuja distinto, y
# quien lee sabe si esta viendo una promesa o un hecho.
PLAN = "plan"            # lo que el cliente dicto
HITO = "hito"            # lo que el equipo marco
ALERTA = "alerta"        # lo que el sistema noto
CENTRAL = "central"      # lo que alguien de la casa hizo a mano
NOTA = "nota"            # lo que alguien de la casa supo y escribio

# Lo que la central hace sobre una jornada y merece salir en la linea.
# La bitacora de acciones guarda todo --abrir la pantalla incluido-- y
# volcarla entera aqui seria cambiar una columna vacia por una
# ilegible.
ACCIONES_QUE_IMPORTAN = (
    "ajustar hito",          # la central corrigio una hora, con motivo
    "marca a mano",          # nadie marco un punto critico y alguien lo firmo
    "cerrar dia a mano",     # nadie marco el fin y alguien lo firmo
    "reabrir dia",           # se deshizo ese cierre
    "cambio de recurso",     # entro otra persona
    "reemplazo deshecho",
    "quitar personal", "asignar personal",
    "quitar unidad", "asignar vehiculo",
    "agregar parada", "quitar parada", "cargar agenda",
)


def _momento(dia: date, hora: time | None) -> datetime | None:
    return datetime.combine(dia, hora) if hora else None


def _meet_and_greet(db: Session, jornada: m.Jornada) -> dict:
    """El momento en que el equipo queda con el principal.

    Es el renglon que decide si el servicio esta corriendo, asi que sale
    aparte y no solo perdido entre los demas: el consultor abre este
    panel para contestar una pregunta --"¿ya estan con el?"-- y esa
    respuesta tiene que estar arriba, no hay que buscarla.

    `quien_falta` es lo que la central necesita para poder firmarlo: a
    quien se le acredita si nadie marco.
    """
    hito = (db.query(m.Hito)
            .filter_by(jornada_id=jornada.id,
                       tipo=m.TipoHito.CONTACTO_EJECUTIVO).first())
    if hito:
        quien = (hito.registrado_a_mano_por.nombre
                 if hito.registrado_a_mano_por else None)
        return {
            "hay": True,
            "momento": hito.marcado_en.isoformat(),
            "persona": hito.persona.nombre if hito.persona else None,
            "a_mano": bool(hito.registrado_a_mano_en),
            "firmado_por": quien,
            "motivo": hito.motivo_a_mano,
        }

    return {
        "hay": False,
        "momento": None,
        "programado": jornada.inicio_programado.isoformat(),
        # Quien iba ese dia, para podersela acreditar.
        "quien_falta": [{"persona_id": a.persona_id,
                         "nombre": a.persona.nombre if a.persona else None,
                         "rol": a.rol.nombre if a.rol else None}
                        for a in jornada.personal
                        if a.persona_id and not a.relevado_en],
    }


def _hora_del_pais(db: Session, instante: datetime | None,
                   jornada: m.Jornada):
    """Un instante (con zona) en la hora de pared del servicio."""
    if instante is None:
        return None
    if instante.tzinfo is None:
        return instante
    pais_id = reloj.pais_de_la_jornada(jornada)
    return reloj.ahora_en(db.get(m.Pais, pais_id) if pais_id else None,
                          instante)


def del_dia(db: Session, jornada_id: int) -> dict:
    """Los cuatro hilos del dia, en una sola lista ordenada por hora."""
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        return {}

    renglones = []

    # ---------------------------------------------------- lo planeado
    for parada in (db.query(m.ParadaAgenda)
                   .filter_by(jornada_id=jornada_id).all()):
        renglones.append({
            "fuente": PLAN,
            "momento": _momento(jornada.fecha, parada.hora),
            "titulo": parada.lugar,
            "detalle": " · ".join(
                x for x in (parada.direccion, parada.notas) if x) or None,
            "marca": None, "tono": "",
        })

    # ----------------------------------------------------- lo marcado
    for hito in (db.query(m.Hito).filter_by(jornada_id=jornada_id)
                 .order_by(m.Hito.marcado_en).all()):
        partes = [hito.persona.nombre] if hito.persona else []
        marca, tono = None, ""

        if hito.dentro_geocerca is True:
            marca, tono = "en el punto", "ok"
            if hito.distancia_origen_m is not None:
                partes.append(f"a {hito.distancia_origen_m} m del punto")
        elif hito.dentro_geocerca is False:
            marca, tono = "fuera del punto", "grave"

        # La hora que dice el telefono y la hora en que llego. La app
        # guarda las dos porque se puede marcar sin senal, y hasta hoy
        # la diferencia no se ensenaba en ningun lado: un dia donde todo
        # llega diferido no es un dia bien reportado.
        if hito.diferido and hito.recibido_en:
            demora = int((hito.recibido_en - hito.marcado_en)
                         .total_seconds() / 60)
            marca = f"diferido {demora} min"
            tono = "alerta"
            partes.append(f"marcado {hito.marcado_en:%H:%M}, "
                          f"recibido {hito.recibido_en:%H:%M}")
        if hito.fuera_de_ventana:
            marca, tono = "fuera de ventana", "alerta"

        # Lo que alguien firmo desde una oficina manda sobre cualquier
        # otra marca de este renglon: no trae ubicacion, no trae
        # geocerca y no es prueba de que nadie estuviera ahi. Si se
        # leyera igual que una marca de la calle, la bitacora estaria
        # diciendo una cosa por otra justo donde importa.
        if hito.registrado_a_mano_en:
            marca, tono = "a mano", "alerta"
            quien = (hito.registrado_a_mano_por.nombre
                     if hito.registrado_a_mano_por else None)
            partes.append("registrado por "
                          + (quien or "la central"))
            if hito.motivo_a_mano:
                partes.append(hito.motivo_a_mano)

        # La marca anulada se queda en la bitacora, dicha como lo que
        # es. La central reabrio ese dia y este fin de servicio dejo de
        # contar; borrarlo seria dejar la bitacora diciendo que el dia
        # nunca se cerro, cuando alguien si lo cerro y despues alguien
        # lo deshizo. Las dos cosas pasaron.
        if hito.anulado_en:
            marca, tono = "anulada", "grave"
            quien = hito.anulado_por.nombre if hito.anulado_por else None
            partes.append("anulada por " + (quien or "la central"))
            if hito.motivo_anulacion:
                partes.append(hito.motivo_anulacion)

        if hito.nota:
            partes.append(hito.nota)

        renglones.append({
            "fuente": HITO,
            # El numero de la marca: sin el, la bitacora enseña las
            # horas y no hay forma de mandar a corregir ninguna. El
            # endpoint para hacerlo existe desde hace tiempo y ninguna
            # pantalla lo alcanzaba.
            "hito_id": hito.id,
            "momento": hito.marcado_en,
            "titulo": hito.tipo.value,
            "detalle": " · ".join(partes) or None,
            "marca": marca, "tono": tono,
            "de": hito.persona.nombre if hito.persona else None,
            # El segundo testigo (seccion 60): lo que decia la unidad de
            # quien marco. No es una posicion del camino --esas no
            # entran aqui--, es una sola medida por marca.
            "unidad": gps.testimonio(hito),
        })

    # ----------------------------------------------------- las alertas
    for alerta in (db.query(m.Alerta).filter_by(jornada_id=jornada_id).all()):
        renglones.append({
            "fuente": ALERTA,
            "momento": _hora_del_pais(db, alerta.creada_en, jornada),
            "titulo": alerta.tipo.value,
            "detalle": alerta.mensaje,
            "marca": "atendida" if alerta.atendida else None,
            "tono": "ok" if alerta.atendida else "alerta",
        })

    # El boton de panico --de la app o de la camioneta-- tambien es parte
    # del dia. Vivia solo en la banda de "Atender ahora" y se iba de ahi
    # al cerrarse: el dia siguiente nadie podia ver que habia sonado.
    canales = {m.CanalAlerta.BOTON_APP: "boton de panico de la app",
               m.CanalAlerta.BOTON_VEHICULO: "boton de la unidad",
               m.CanalAlerta.LLAMADA: "llamada"}
    for alerta in (db.query(m.AlertaIncidencia)
                   .filter_by(jornada_id=jornada_id).all()):
        partes = [canales.get(alerta.canal, alerta.canal.value)]
        if alerta.reporta:
            partes.append(alerta.reporta.nombre)
        if alerta.descripcion:
            partes.append(alerta.descripcion)
        if alerta.resolucion:
            partes.append(alerta.resolucion)
        cerrada = alerta.estatus == m.EstatusAlerta.CERRADA
        renglones.append({
            "fuente": ALERTA,
            "momento": _hora_del_pais(db, alerta.reportada_en, jornada),
            "titulo": "panico",
            "detalle": " · ".join(partes),
            "marca": "atendida" if cerrada else None,
            "tono": "ok" if cerrada else "grave",
        })

    # ------------------------------------------------- lo que se toco
    for registro in (db.query(m.RegistroAccion)
                     .filter_by(jornada_id=jornada_id).all()):
        if registro.accion not in ACCIONES_QUE_IMPORTAN:
            continue
        quien = registro.persona.nombre if registro.persona else None
        renglones.append({
            "fuente": CENTRAL,
            "momento": _hora_del_pais(db, registro.creado_en, jornada),
            "titulo": registro.accion,
            "detalle": " · ".join(x for x in (registro.detalle, quien) if x),
            "marca": None, "tono": "",
        })

    # ------------------------------------------------- lo que se supo
    for nota in (db.query(m.NotaBitacora)
                 .filter_by(jornada_id=jornada_id).all()):
        renglones.append({
            "fuente": NOTA,
            "momento": _hora_del_pais(db, nota.creada_en, jornada),
            "titulo": nota.persona.nombre if nota.persona else "—",
            "detalle": nota.texto,
            "marca": None, "tono": "",
        })

    # Lo que no trae hora se va al final y lo dice: una parada de la
    # agenda sin hora es lo normal --el cliente no siempre la da-- y
    # colarla a medianoche seria inventarle un dato.
    con_hora = [r for r in renglones if r["momento"]]
    sin_hora = [r for r in renglones if not r["momento"]]
    con_hora.sort(key=lambda r: r["momento"])

    # El dia siguiente de ESTE equipo, para poder fijarle la hora desde
    # aqui. Alfa en Ciudad de Mexico y Beta en Monterrey son dos hilos
    # distintos: lo que dijo el principal de uno no mueve al otro.
    siguiente = min(
        (j for j in jornada.equipo.jornadas
         if j.fecha > jornada.fecha
         and j.estatus != m.EstatusJornada.CANCELADA),
        key=lambda j: j.fecha, default=None)

    # Todas las horas de arriba son de la pared del pais del servicio, y
    # la pantalla lo dice: quien lo lee puede estar en otro pais.
    pais_id = reloj.pais_de_la_jornada(jornada)
    pais = db.get(m.Pais, pais_id) if pais_id else None

    return {
        "jornada_id": jornada.id,
        "fecha": jornada.fecha.isoformat(),
        "hora_de": pais.nombre if pais else None,
        "estatus_jornada": jornada.estatus.value,
        "meet_and_greet": _meet_and_greet(db, jornada),
        "manana": ({"jornada_id": siguiente.id,
                    "fecha": siguiente.fecha.isoformat(),
                    "hora": f"{siguiente.inicio_programado:%H:%M}",
                    "confirmada": siguiente.hora_confirmada}
                   if siguiente else None),
        "folio": jornada.equipo.servicio.folio,
        "cliente": (jornada.equipo.servicio.cliente.nombre
                    if jornada.equipo.servicio.cliente else None),
        "equipo": jornada.equipo.alias,
        "renglones": [{**r, "momento": r["momento"].isoformat()}
                      for r in con_hora],
        "sin_hora": [{**r, "momento": None} for r in sin_hora],
    }

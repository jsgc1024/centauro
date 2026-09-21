# -*- coding: utf-8 -*-
"""El camino al meet and greet: saber si va a haber alguien en el punto.

El conductor que se queda dormido no manda una senal equivocada: **no
manda ninguna**. El sistema tenia vigilancias para lo que pasa durante
el servicio --el que deja de reportar, las horas extra-- y ninguna para
el silencio de antes. La central se enteraba cuando llamaba el cliente.

**Lo que decide el diseno es un numero de la operacion**: reponer a
alguien toma hasta hora y media. Por eso el primer toque va a DOS horas
de la hora de estar en el punto. Con hora y media, el silencio se
detectaria a los 75 minutos y el reemplazo llegaria quince minutos
despues del servicio; con dos horas, sobran quince.

**Tres toques y nada mas.** Mas toques no dan mas informacion: ensenan a
ignorar los avisos.

**Lo unico que se revisa es si se mueve hacia alla.** No se calcula hora
de llegada ni se pregunta el trafico --eso seria una llamada a Google en
cada lectura-- y no se vigila la puntualidad, que es responsabilidad del
personal de seguridad (decision de Salvador, 20 sep). Con dos posiciones
y el reloj sale todo.

**Si todo va bien, ninguna noticia.** Regla de Salvador. No sale un solo
aviso de "vas bien".
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models as m
from app import push
from app import reloj
from app.operacion import distancia_metros
from app.presentacion import llegada_del_equipo

# Minutos antes de la hora de estar en el punto. El primero manda: ver
# el docstring.
TOQUES = (120, 80, 45)
# Cuanto se espera una respuesta antes de darla por silencio. Quince
# minutos es lo que tarda alguien en oir el telefono si esta manejando.
MINUTOS_PARA_CONTESTAR = 15
# Por debajo de esto ya esta al lado del punto: se apaga y no se le
# vuelve a preguntar.
METROS_CERCA = 1000
# Avanzar menos que esto entre dos lecturas es no avanzar. Cien metros
# es ruido del GPS parado en un semaforo.
METROS_DE_AVANCE = 300
# Que tan por debajo de lo que necesita se tolera antes de decir que no
# llega. La linea recta siempre miente a favor --las calles dan vuelta
# y el avance real es mayor que el aparente-- asi que el margen es
# holgado a proposito: se alerta solo cuando va claramente corto.
FRACCION_MINIMA = 0.6
# Cuanto vale lo que dijo por telefono antes de volver a vigilarlo. La
# palabra de la central cuenta --hablo con el, lo oyo manejando-- pero
# no es una posicion: media hora despues, si el telefono no ha dicho
# donde esta, el silencio vuelve a pesar. Decision de Salvador, 21 sep.
MINUTOS_DE_GRACIA_POR_TELEFONO = 30


def hora_de_estar(db: Session, jornada: m.Jornada) -> datetime:
    """A que hora tiene que estar el equipo en el punto."""
    llega, _minutos, _contra = llegada_del_equipo(
        jornada.inicio_programado, jornada.vuelo_hora, jornada.vuelo_tipo)
    return llega


def _distancia(jornada: m.Jornada, lat, lon) -> int | None:
    if jornada.origen_lat is None or jornada.origen_lon is None:
        return None
    return distancia_metros(lat, lon, jornada.origen_lat, jornada.origen_lon)


def _toque_que_toca(minutos_faltan: int, toques_dados: int) -> bool:
    """Si en este momento le toca un toque.

    Se compara contra el toque que sigue segun cuantos lleva: asi la
    tarea puede correr cada cinco minutos sin repetir el mismo.
    """
    if toques_dados >= len(TOQUES):
        return False
    return minutos_faltan <= TOQUES[toques_dados]


def registrar(db: Session, jornada_id: int, persona_id: int,
              lat, lon, ahora: datetime | None = None) -> dict:
    """Llego una posicion. Se guarda y se evalua.

    Devuelve lo que se decidio, para que la app pueda decir algo si hace
    falta. Lo que no devuelve nunca es un "vas bien" que haya que
    mostrar: si todo va bien, ninguna noticia.
    """
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        return {"estado": None, "motivo": "no existe la jornada"}

    ahora = ahora or reloj.ahora_de_la_jornada(db, jornada)
    via = (db.query(m.Trayecto)
           .filter_by(jornada_id=jornada_id, persona_id=persona_id).first())
    if not via:
        via = m.Trayecto(jornada_id=jornada_id, persona_id=persona_id)
        db.add(via)
        db.flush()

    # Decir "voy en camino" es mas fuerte que confirmar: quien ya va
    # manejando hacia el punto sabe perfectamente que hoy trabaja. Si no
    # se apagara aqui, la central seguiria viendo "le falta confirmar al
    # equipo" mientras la persona esta en la carretera, y un renglon
    # rojo que miente es exactamente lo que ensena a ignorar los
    # renglones rojos.
    #
    # Se apaga aqui y no en la ruta porque cualquier posicion de esa
    # persona para esa jornada --la del boton o la que manda la app
    # sola-- significa lo mismo.
    asignacion = (db.query(m.AsignacionPersonal)
                  .filter_by(jornada_id=jornada_id, persona_id=persona_id)
                  .first())
    if asignacion and not asignacion.confirmado:
        asignacion.confirmado = True

    distancia = _distancia(jornada, lat, lon)
    if distancia is None:
        # Sin punto de origen no hay contra que medir. No es culpa de
        # quien va en camino: se guarda que contesto y ya.
        via.estado = m.EstadoTrayecto.EN_CAMINO.value
        via.ultima_lectura_en = ahora
        db.commit()
        return {"estado": via.estado, "motivo": "la jornada no tiene punto"}

    db.add(m.LecturaTrayecto(trayecto_id=via.id, momento=ahora,
                             lat=lat, lon=lon, distancia_m=distancia))

    if via.distancia_inicial_m is None:
        via.distancia_inicial_m = distancia

    antes = via.distancia_ultima_m
    via.distancia_ultima_m = distancia
    via.ultima_lectura_en = ahora

    # Ya esta al lado: se apaga y no se le vuelve a preguntar.
    if distancia <= METROS_CERCA:
        via.estado = m.EstadoTrayecto.CERCA.value
        via.sin_avanzar = 0
        db.commit()
        return {"estado": via.estado}

    via.estado = m.EstadoTrayecto.EN_CAMINO.value
    avance = (antes - distancia) if antes is not None else None
    if avance is not None and avance < METROS_DE_AVANCE:
        # Una lectura sin avanzar es trafico; dos seguidas ya no.
        via.sin_avanzar += 1
    else:
        via.sin_avanzar = 0

    falta = hora_de_estar(db, jornada) - ahora
    minutos = falta.total_seconds() / 60
    motivo = None

    if via.sin_avanzar >= 2:
        motivo = (f"no se ha movido en dos lecturas y esta a "
                  f"{distancia // 1000} km del punto")
    elif minutos <= 0:
        motivo = "la hora de estar en el punto ya paso y sigue en camino"
    elif antes is not None and via.sin_avanzar == 0:
        # La que necesita contra la que lleva. Las dos en metros por
        # minuto, que es lo unico que hace falta comparar.
        #
        # Solo se le mide la velocidad a quien SI avanzo. Al que no se
        # movio lo juzga la regla de arriba, que le da una lectura de
        # tolerancia porque una lectura parado es trafico. Medirle la
        # velocidad aqui seria cero contra lo que necesita --siempre
        # corta-- y esa tolerancia no existiria: la primera lectura
        # parado ya levantaria la alerta que la regla dice que no
        # levanta hasta la segunda.
        necesita = distancia / minutos
        minutos_entre = max(
            1.0, (ahora - _momento_anterior(via, ahora)).total_seconds() / 60)
        lleva = max(0, (antes - distancia)) / minutos_entre
        if lleva < necesita * FRACCION_MINIMA:
            motivo = (f"va a {lleva * 60 / 1000:.0f} km/h en linea recta y le "
                      f"faltan {distancia // 1000} km en {int(minutos)} min")

    if motivo:
        via.estado = m.EstadoTrayecto.NO_LLEGA.value
        _alertar(db, via, jornada, motivo)
    db.commit()
    return {"estado": via.estado, "motivo": motivo}


def _momento_anterior(via: m.Trayecto, ahora: datetime) -> datetime:
    previas = [l.momento for l in via.lecturas if l.momento < ahora]
    return max(previas) if previas else ahora - timedelta(minutes=20)


def _alertar(db: Session, via: m.Trayecto, jornada: m.Jornada,
             mensaje: str) -> None:
    """Una sola alerta por trayecto: la central no necesita la misma cada
    cinco minutos, necesita decidir a quien manda."""
    if via.alertado:
        return
    persona = db.get(m.Persona, via.persona_id)
    nombre = persona.nombre if persona else via.persona_id
    db.add(m.Alerta(
        jornada_id=jornada.id, tipo=m.TipoAlerta.SIN_REPORTE,
        persona_id=via.persona_id,
        mensaje=(f"{nombre} {mensaje}. Presentacion "
                 f"{hora_de_estar(db, jornada):%H:%M}.")[:400]))
    via.alertado = True


def dijo_que_va(db: Session, jornada_id: int, persona_id: int,
                quien_id: int, nota: str | None = None,
                ahora: datetime | None = None) -> dict:
    """La central le hablo por telefono y contesto que ya va.

    El caso es diario: el toque se le fue a un telefono en el bolsillo
    de alguien que va manejando, la banda lo pinta en rojo, la central
    marca su numero y el hombre contesta que va en Periferico. Hasta
    hoy eso no se podia asentar en ningun lado: el rojo se quedaba
    ahi, mintiendo, y un renglon rojo que miente es lo que ensena a
    ignorar los renglones rojos.

    Tres cosas que si hace y una que no:

      * Queda escrito quien lo registro y a que hora. Lo dicho por
        telefono no se puede confundir nunca con una posicion del GPS.
      * Apaga el toque que estaba por salir y cierra la alerta abierta.
      * Da por confirmado el dia, por lo mismo que lo da una posicion:
        quien ya va manejando hacia el punto sabe perfectamente que hoy
        trabaja.
      * Lo que NO hace es apagar la vigilancia. A los
        MINUTOS_DE_GRACIA_POR_TELEFONO, si el telefono sigue sin decir
        donde esta, se vuelve a preguntar y el silencio vuelve a pesar.
        Quien dijo que iba y no llego es exactamente el caso que esta
        pantalla existe para cazar.
    """
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        return {"estado": None, "motivo": "no existe la jornada"}

    asignacion = (db.query(m.AsignacionPersonal)
                  .filter_by(jornada_id=jornada_id, persona_id=persona_id)
                  .first())
    if not asignacion or asignacion.relevado_en:
        return {"estado": None, "motivo": "esa persona no va ese dia"}

    ahora = ahora or reloj.ahora_de_la_jornada(db, jornada)
    via = (db.query(m.Trayecto)
           .filter_by(jornada_id=jornada_id, persona_id=persona_id).first())
    if not via:
        via = m.Trayecto(jornada_id=jornada_id, persona_id=persona_id)
        db.add(via)
        db.flush()

    via.estado = m.EstadoTrayecto.POR_TELEFONO.value
    via.por_telefono_en = ahora
    via.por_telefono_por_id = quien_id
    via.por_telefono_nota = (nota or "").strip()[:200] or None
    # La alerta que estaba abierta ya se atendio: se le hablo. Si vuelve
    # a callarse, que vuelva a sonar.
    via.alertado = False
    via.sin_avanzar = 0
    if not asignacion.confirmado:
        asignacion.confirmado = True
    db.commit()
    return {"estado": via.estado,
            "vigilancia_vuelve_en": MINUTOS_DE_GRACIA_POR_TELEFONO}


def pulsar(db: Session, ahora: datetime | None = None) -> dict:
    """La vuelta del reloj: manda los toques y cobra los silencios.

    Corre cada cinco minutos. Mira las jornadas de hoy que todavia no
    han empezado y, de cada persona asignada, decide si le toca un toque
    o si ya lleva demasiado callada.
    """
    relojes = reloj.Relojes(db, ahora)
    margen = reloj.margen_de_paises(db)
    referencia = ahora or datetime.now()

    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.estatus.in_([m.EstatusJornada.PLANEADA,
                                               m.EstatusJornada.CONFIRMADA,
                                               m.EstatusJornada.PROXIMA_A_INICIAR]),
                        m.Jornada.inicio_programado
                        >= referencia - margen - timedelta(hours=1),
                        m.Jornada.inicio_programado
                        <= referencia + margen + timedelta(hours=4))
                .all())

    toques, silencios = 0, 0
    for jornada in jornadas:
        suyo = relojes.de_la_jornada(jornada)
        minutos = (hora_de_estar(db, jornada) - suyo).total_seconds() / 60
        if minutos > TOQUES[0]:
            continue                      # todavia no le toca a nadie

        for asignada in jornada.personal:
            if not asignada.persona_id or asignada.relevado_en:
                continue
            via = (db.query(m.Trayecto)
                   .filter_by(jornada_id=jornada.id,
                              persona_id=asignada.persona_id).first())
            if not via:
                via = m.Trayecto(jornada_id=jornada.id,
                                 persona_id=asignada.persona_id)
                db.add(via)
                db.flush()

            # Ya llego, ya esta cerca, o ya se alerto: no se le molesta.
            if via.estado in (m.EstadoTrayecto.CERCA,
                              m.EstadoTrayecto.LLEGO):
                continue
            if _ya_marco_llegada(db, jornada, asignada.persona_id):
                via.estado = m.EstadoTrayecto.LLEGO.value
                continue

            # Hablo con la central hace poco: no se le vuelve a tocar
            # todavia. Pasado el plazo cae solo en las reglas de abajo,
            # que es justo lo que se quiere: dijo que iba, veamos si
            # llego.
            if (via.por_telefono_en
                    and (suyo - via.por_telefono_en).total_seconds() / 60
                    <= MINUTOS_DE_GRACIA_POR_TELEFONO):
                continue

            # El silencio pesa igual que no ir.
            callado = (via.ultimo_toque_en
                       and not via.ultima_lectura_en
                       and (suyo - via.ultimo_toque_en).total_seconds() / 60
                       > MINUTOS_PARA_CONTESTAR)
            if callado and via.estado != m.EstadoTrayecto.SIN_RESPUESTA:
                via.estado = m.EstadoTrayecto.SIN_RESPUESTA.value
                _alertar(db, via, jornada,
                         "no contesta si va en camino")
                silencios += 1
                continue

            if _toque_que_toca(int(minutos), via.toques):
                push.avisar(
                    db, asignada.persona_id,
                    titulo="¿Vas en camino?",
                    cuerpo=(f"Tienes que estar en el punto a las "
                            f"{hora_de_estar(db, jornada):%H:%M}. "
                            f"Toca para decir que vas."),
                    etiqueta="en-camino", urgente=True, accion="en_camino")
                via.toques += 1
                via.ultimo_toque_en = suyo
                # Cada toque vuelve a abrir la espera: lo que se cobra es
                # no contestar al ultimo, no al primero.
                via.ultima_lectura_en = None
                toques += 1

    db.commit()
    return {"toques": toques, "silencios": silencios}


def _ya_marco_llegada(db: Session, jornada: m.Jornada, persona_id: int) -> bool:
    return bool(db.query(m.Hito)
                .filter_by(jornada_id=jornada.id, persona_id=persona_id,
                           tipo=m.TipoHito.LLEGADA_ORIGEN)
                .first())


def cerrar(db: Session, jornada_id: int, persona_id: int) -> None:
    """Llego: se apaga el camino.

    Se llama desde el hito de llegada, no desde el reloj: marcar la
    llegada pone la jornada EN_CURSO y `pulsar` ya no la mira, asi que
    si esto no se hiciera aqui el nombre se quedaria colgado en la
    banda de la central toda la tarde.
    """
    via = (db.query(m.Trayecto)
           .filter_by(jornada_id=jornada_id, persona_id=persona_id).first())
    if via and via.estado != m.EstadoTrayecto.LLEGO:
        via.estado = m.EstadoTrayecto.LLEGO.value


def en_camino(db: Session, jornada_id: int) -> list[dict]:
    """Quien va en camino y como va. Para la central."""
    filas = (db.query(m.Trayecto).filter_by(jornada_id=jornada_id).all())
    return [{
        "persona_id": v.persona_id,
        "persona": v.persona.nombre if v.persona else None,
        "telefono": v.persona.telefono if v.persona else None,
        "estado": v.estado,
        "por_telefono": (v.por_telefono_en.strftime("%H:%M")
                         if v.por_telefono_en else None),
        "por_telefono_por": (v.por_telefono_por.nombre
                             if v.por_telefono_por else None),
        "por_telefono_nota": v.por_telefono_nota,
        "distancia_km": (round(v.distancia_ultima_m / 1000, 1)
                         if v.distancia_ultima_m is not None else None),
        "ultima_lectura": (v.ultima_lectura_en.isoformat()
                           if v.ultima_lectura_en else None),
        "toques": v.toques,
    } for v in filas]

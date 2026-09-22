"""Ciclo diario: hitos del conductor, tablero de la central y notificaciones.

Quien puede hacer que:
  - El personal de seguridad marca hitos, pero solo en SUS jornadas.
  - Nadie puede ajustar su propia marca: el ajuste es de la central.
  - El ajuste queda firmado con el usuario que lo hizo, no con lo que diga el cuerpo.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auditoria
from app import auth
from app import models as m
from app import geocercas
from app import programacion
from app import push
from app import reloj
from app import operacion as motor
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/operacion", tags=["Operacion"])

# La app del agente no se muda a actividades. El candado de ahi no es un
# permiso repartible sino "es su propia jornada": como casilla del panel
# seria una que nadie debe marcar nunca, y el dia que alguien la marcara
# por curiosidad le abriria la app del campo a gente de oficina.
CAMPO = auth.requiere(m.Rol.PERSONAL_SEGURIDAD)

VER = auth.puede("operacion.ver")
PLANEAR = auth.puede("operacion.planear")
CORREGIR = auth.puede("operacion.corregir")
ATENDER = auth.puede("operacion.atender")


@router.patch("/jornadas/{jornada_id}/origen",
              summary="Configurar el punto de origen y su geocerca")
def configurar_origen(jornada_id: int, datos: s.OrigenIn,
                      db: Session = Depends(get_db),
                      _=Depends(PLANEAR)):
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    # Solo se pisa lo que viene: mandar el pin no borra la direccion, y
    # mandar la direccion no borra el pin. Pero mandar un campo en nulo a
    # proposito si lo limpia: es como se quita un pin mal puesto.
    cambios = datos.model_dump(exclude_unset=True)
    forzar = cambios.pop("forzar_aeropuerto", False)

    # El candado se revisa contra lo que Google diga de este lugar: el
    # que venga en la peticion si el punto se acaba de elegir, y el
    # guardado si solo se esta moviendo la casilla.
    segun_google = cambios.get("origen_google_aeropuerto",
                               jornada.origen_google_aeropuerto)
    if "origen_aeropuerto" in cambios:
        geocercas.revisar_aeropuerto(cambios["origen_aeropuerto"],
                                     segun_google, forzar)

    for campo, valor in cambios.items():
        setattr(jornada, campo, valor)

    # Cuando se dice que el punto es —o deja de ser— un aeropuerto y
    # nadie fijo un radio a mano, el radio se acomoda solo.
    if "origen_aeropuerto" in cambios and "geocerca_metros" not in cambios:
        jornada.geocerca_metros = geocercas.radio_de(jornada.origen_aeropuerto)
    db.commit()
    programacion.evaluar(jornada.equipo.servicio)
    db.commit()
    return {"resultado": "configurado", "jornada_id": jornada.id,
            "direccion": jornada.origen_direccion,
            "geocerca_metros": jornada.geocerca_metros,
            "con_pin": jornada.origen_lat is not None}


@router.patch("/jornadas/{jornada_id}/vuelo",
              summary="Capturar el vuelo del ejecutivo de ese dia")
def configurar_vuelo(jornada_id: int, datos: s.VueloIn,
                     db: Session = Depends(get_db),
                     _=Depends(PLANEAR)):
    """El vuelo sale en el meet and greet del task sheet. Se puede ir
    completando: primero la aerolinea y el numero, la hora despues."""
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    # Solo se pisa lo que viene: mandar la hora no borra la aerolinea.
    # Mandar un campo en nulo a proposito si lo limpia, que es como se
    # quita un vuelo cuando el dia deja de arrancar en aeropuerto.
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(jornada, campo, valor)

    movida = _ajustar_presentacion(db, jornada)
    db.commit()
    programacion.evaluar(jornada.equipo.servicio)
    db.commit()
    return {"resultado": "configurado", "jornada_id": jornada.id,
            "aerolinea": jornada.vuelo_aerolinea,
            "vuelo": jornada.vuelo_numero,
            "hora": jornada.vuelo_hora,
            "presentacion": jornada.inicio_programado.strftime("%H:%M"),
            "presentacion_movida": movida}


def _ajustar_presentacion(db: Session, jornada: m.Jornada) -> bool:
    """La presentacion del primer dia la manda el vuelo que llega.

    El equipo no se presenta a la hora que aterriza el ejecutivo: se
    presenta antes, porque puede salir del filtro temprano. Si el vuelo
    se mueve, la hora a la que hay que estar en el punto se mueve con el,
    y de esa hora dependen los empalmes y las horas extra. Se hace aqui y
    no en la pantalla para que valga por cualquier puerta: la consola, la
    app o el dia que Odoo mande los vuelos.

    Solo el vuelo de llegada del primer dia: en los demas el ejecutivo
    sale de su hotel y la referencia es su presentacion acordada.
    """
    if not (jornada.vuelo_hora and jornada.vuelo_tipo == "llegada"):
        return False
    primera = min(jornada.equipo.jornadas, key=lambda j: j.fecha, default=None)
    if not primera or primera.id != jornada.id:
        return False

    pais = db.get(m.Pais, jornada.equipo.servicio.pais_id)
    antes = pais.anticipacion_aeropuerto_min if pais else 45
    nuevo = jornada.vuelo_hora - timedelta(minutes=antes)
    if nuevo == jornada.inicio_programado:
        return False

    modalidad = db.get(m.Modalidad, jornada.modalidad_id)
    jornada.inicio_programado = nuevo
    jornada.fin_programado = nuevo + timedelta(hours=float(modalidad.horas))
    # La hora sale del vuelo: es un dato, no un supuesto.
    jornada.hora_confirmada = True
    return True


@router.post("/jornadas/{jornada_id}/confirmar-recurso",
             summary="El personal confirma disponibilidad desde la app")
def confirmar_recurso(jornada_id: int, db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(CAMPO)):
    """Confirma el usuario que inicio sesion; no se puede confirmar por otro."""
    asignacion = (db.query(m.AsignacionPersonal)
                  .filter_by(jornada_id=jornada_id, persona_id=usuario.persona_id)
                  .first())
    if not asignacion:
        raise HTTPException(403, "No estas asignado a esa jornada")
    asignacion.confirmado = True
    # Sin `confirmado_por`: la confirmo la propia persona. Ese hueco es
    # el dato, y es lo que la distingue de la que registra la central.
    asignacion.confirmado_en = reloj.ahora_de_la_jornada(
        db, asignacion.jornada)
    programacion.confirmar_si_todos(asignacion.jornada)
    db.commit()
    return {"resultado": "confirmado", "persona": asignacion.persona.nombre}


@router.post("/jornadas/{jornada_id}/confirmar-a-mano",
             summary="La central registra que confirmo por telefono")
def confirmar_a_mano(jornada_id: int, datos: s.ConfirmarAManoIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(
                         auth.puede("asignaciones.confirmar_a_mano"))):
    """El agente sin la app no podia confirmar de ninguna manera.

    La central le hablaba por telefono, el agente decia que si, y el
    renglon se quedaba rojo para siempre. Un renglon rojo que miente
    ensena a ignorar los renglones rojos.

    Queda sellado con quien lo registro y no se pinta igual que la
    confirmacion de la persona: el dia que alguien no llegue, la
    diferencia entre "confirmo el" y "lo confirmaron por el" es la
    unica pregunta que importa.
    """
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    # Nadie se confirma a si mismo por esta puerta: para eso esta la
    # app, que ademas deja dicho que confirmo el.
    if datos.persona_id == usuario.persona_id:
        raise HTTPException(403, {
            "mensaje": "Tu propia confirmacion va por la app",
            "que_hacer": "Entra a la app y confirma desde tu dia."})

    asignacion = next((a for a in jornada.personal
                       if a.persona_id == datos.persona_id), None)
    if not asignacion:
        raise HTTPException(404, "Esa persona no esta asignada a la jornada")
    if asignacion.confirmado:
        raise HTTPException(409, "Esa persona ya habia confirmado")

    asignacion.confirmado = True
    asignacion.confirmado_en = reloj.ahora_de_la_jornada(db, jornada)
    asignacion.confirmado_por_id = usuario.persona_id
    asignacion.nota_confirmacion = (datos.nota or "").strip() or None
    programacion.confirmar_si_todos(jornada)
    auditoria.registrar(db, usuario, jornada.equipo.servicio,
                        "confirmacion por telefono",
                        f"{jornada.fecha} {asignacion.persona.nombre}"
                        + (f": {asignacion.nota_confirmacion}"
                           if asignacion.nota_confirmacion else ""),
                        jornada_id=jornada.id)
    db.commit()
    return {"resultado": "confirmado",
            "persona": asignacion.persona.nombre,
            "por": usuario.persona.nombre if usuario.persona else None,
            "a_mano": True}


@router.post("/jornadas/{jornada_id}/hitos", summary="Marcar un hito desde la app")
def marcar_hito(jornada_id: int, datos: s.HitoIn,
                db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(CAMPO)):
    """El hito se registra a nombre del usuario de la sesion: nadie marca por otro."""
    if not auth.es_su_propia_jornada(db, usuario, jornada_id):
        raise HTTPException(403, "No estas asignado a esa jornada")

    return motor.registrar_hito(
        db, jornada_id, usuario.persona_id, datos.tipo,
        lat=datos.lat, lon=datos.lon,
        marcado_en=datos.marcado_en, nota=datos.nota)


@router.post("/hitos/{hito_id}/ajustar",
             summary="La central ajusta el corte de tiempo")
def ajustar(hito_id: int, datos: s.AjusteHitoIn,
            db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(CORREGIR)):
    """Solo la central o el director de operaciones. La justificacion es
    obligatoria y el ajuste queda firmado con quien lo hizo."""
    hito = db.get(m.Hito, hito_id)
    if not hito:
        raise HTTPException(404, f"No existe el hito {hito_id}")
    if hito.persona_id == usuario.persona_id:
        raise HTTPException(403, "No puedes ajustar tu propia marca")

    resultado = motor.ajustar_hito(db, hito_id, datos.nuevo_momento,
                                   usuario.persona_id, datos.justificacion)
    auditoria.registrar(db, usuario, hito.jornada.equipo.servicio,
                        "ajustar hito", f"{hito.tipo.value}: {datos.justificacion}",
                        jornada_id=hito.jornada_id)
    db.commit()
    return resultado


# ------------------------------------------------- cerrar un dia a mano
#
# Es un permiso delicado: cerrar un dia es lo que lo manda a nomina. Por
# eso lo tiene la central y la direccion, no el consultor —que es quien
# vende el servicio y a quien mas le conviene que un dia aparezca
# trabajado.

# El camino NO es `/bitacora`: ese ya lo tiene el expediente de la
# jornada --hitos y notificaciones-- desde mucho antes, y FastAPI se
# queda con la primera ruta que coincide. Puesta ahi, esta se llevaba
# la de aquella sin que nada lo dijera. `revisar.py` ahora se queja si
# vuelve a pasar.
@router.get("/jornadas/{jornada_id}/dia",
            summary="La bitacora del dia: plan, marcas, alertas y la central")
def bitacora_del_dia(jornada_id: int, db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(VER)):
    """Los cuatro hilos del dia en una sola columna ordenada por hora.

    Cada uno vivia en su tabla y en su pantalla. Juntos y por hora es la
    unica forma de ver donde el plan y la realidad se separaron, y que
    paso en los huecos.
    """
    from app import bitacora

    resultado = bitacora.del_dia(db, jornada_id)
    if not resultado:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    # Quien puede firmar el meet and greet lo dice el servidor, no la
    # pantalla. Si la consola decidiera por rol, la respuesta se
    # separaria de la de verdad el dia que una categoria cambie los
    # permisos de alguien --que es justo para lo que existen-- y el
    # boton saldria para quien luego se come un 403.
    resultado["puedo_registrar_a_mano"] = auth.puede_el_usuario(
        db, usuario, "operacion.corregir")
    return resultado


@router.get("/dias-sin-cerrar", summary="Dias que ya pasaron y siguen abiertos")
def dias_sin_cerrar(db: Session = Depends(get_db),
                    ahora: datetime | None = None,
                    pais_id: int | None = None,
                    _=Depends(VER)):
    """La lista de trabajo de la central.

    Cada renglon es alguien que trabajo y todavia no puede cobrar. Sale
    del mas viejo al mas nuevo: el mas viejo es el que mas cerca esta de
    convertirse en un reclamo.
    """
    dias = motor.dias_sin_cerrar(db, ahora, pais_id)
    return {"dias": dias, "cuantos": len(dias),
            "horas_de_gracia": motor.HORAS_DE_GRACIA}


@router.post("/jornadas/{jornada_id}/cerrar-a-mano",
             summary="La central cierra un dia que nadie marco")
def cerrar_a_mano(jornada_id: int, datos: s.CierreAManoIn,
                  db: Session = Depends(get_db),
                  ahora: datetime | None = None,
                  usuario: m.Usuario = Depends(CORREGIR)):
    """Queda firmado con el usuario que lo hizo, no con lo que diga el
    cuerpo de la peticion."""
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    # Nadie cierra a mano un dia que trabajo el mismo: firmar el propio
    # dia es firmarse las horas.
    if any(a.persona_id == usuario.persona_id for a in jornada.personal):
        raise HTTPException(403, {
            "mensaje": "No puedes cerrar a mano un dia que trabajaste",
            "que_hacer": "Que lo cierre otra persona de la central."})

    resultado = motor.cerrar_a_mano(db, jornada_id, usuario.persona_id,
                                    datos.justificacion, datos.fin_real,
                                    datos.inicio_real, ahora)
    auditoria.registrar(db, usuario, jornada.equipo.servicio,
                        "cerrar dia a mano",
                        f"{jornada.fecha}: {datos.justificacion}",
                        jornada_id=jornada.id)
    db.commit()
    return resultado


@router.post("/jornadas/{jornada_id}/marca-a-mano",
             summary="La central asienta un punto critico que nadie marco")
def hito_a_mano(jornada_id: int, datos: s.HitoAManoIn,
                db: Session = Depends(get_db),
                ahora: datetime | None = None,
                usuario: m.Usuario = Depends(CORREGIR)):
    """Mismo candado que cerrar un dia a mano, y por la misma razon.

    Esa hora fija `inicio_real`, de donde salen las horas extra que se le
    facturan al cliente y se le pagan a la gente. El consultor ve el
    panel y no escribe en el: es quien vende el servicio y a quien mas
    le conviene que un dia aparezca trabajado.
    """
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    # Nadie se firma sus propias marcas, igual que nadie cierra a mano un
    # dia que trabajo.
    if any(a.persona_id == usuario.persona_id for a in jornada.personal):
        raise HTTPException(403, {
            "mensaje": "No puedes registrar marcas de un dia que trabajaste",
            "que_hacer": "Que las registre otra persona de la central."})

    tipo = m.TipoHito(datos.tipo)
    resultado = motor.registrar_hito_a_mano(
        db, jornada_id, datos.persona_id, usuario.persona_id, tipo,
        datos.momento, datos.justificacion, ahora)
    auditoria.registrar(db, usuario, jornada.equipo.servicio,
                        "marca a mano",
                        f"{jornada.fecha} {tipo.value} "
                        f"{datos.momento:%H:%M}: {datos.justificacion}",
                        jornada_id=jornada.id)
    db.commit()
    return resultado


@router.post("/jornadas/{jornada_id}/notas",
             status_code=201,
             summary="Escribir una nota de turno en la bitacora del dia")
def escribir_nota(jornada_id: int, datos: s.NotaBitacoraIn,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(VER)):
    """Quien puede ver el dia puede escribir en el. Decision de Salvador.

    Una nota no toca lo que se factura ni lo que se paga: es
    informacion. Y el consultor es a quien le llama el cliente, asi que
    si no pudiera escribir lo que le dijeron, ese dato no entraria nunca
    al sistema.

    La hora la pone el servidor y la firma es la sesion: una nota con
    hora o con autor a eleccion de quien escribe deja de ser un registro
    de que se supo y cuando.
    """
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    nota = m.NotaBitacora(jornada_id=jornada_id,
                          persona_id=usuario.persona_id,
                          texto=datos.texto.strip())
    db.add(nota)
    db.commit()
    db.refresh(nota)
    return {"id": nota.id, "texto": nota.texto,
            "persona": usuario.persona.nombre if usuario.persona else None,
            "creada_en": nota.creada_en.isoformat()}


@router.post("/jornadas/{jornada_id}/hora-de-manana",
             summary="A que hora arranca el dia siguiente de este equipo")
def hora_de_manana(jornada_id: int, datos: s.HoraDeManianaIn,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(CORREGIR)):
    """El principal dice al cerrar el dia a que hora se ven manana.

    Candado de central y direccion, decision de Salvador. Cambiar la
    hora de un dia ya existe desde la pantalla del servicio y ahi la
    tiene el consultor; esta puerta es mas apretada porque se usa a
    deshoras y sobre un dia que ya tiene gente confirmada.

    El dia siguiente es el del MISMO EQUIPO. Un servicio puede tener a
    Alfa en Ciudad de Mexico y a Beta en Monterrey, y lo que dijo el
    principal de Alfa no mueve la hora de Beta.
    """
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    r = motor.fijar_hora_de_manana(db, jornada, datos.hora,
                                   usuario.persona_id, datos.nota)
    siguiente, antes = r["siguiente"], r["antes"]
    auditoria.registrar(db, usuario, jornada.equipo.servicio,
                        "hora de maniana",
                        f"{siguiente.fecha} {datos.hora:%H:%M}",
                        jornada_id=siguiente.id)
    db.commit()

    # Quien ya confirmo lo hizo sobre una hora. Si esa hora cambia y
    # nadie le avisa, su confirmacion apunta a algo que ya no es cierto.
    if siguiente.inicio_programado != antes:
        push.avisar_cambio_de_hora(db, siguiente, antes)
        db.commit()

    return {"resultado": "hora de maniana fijada",
            "jornada_id": siguiente.id,
            "fecha": siguiente.fecha.isoformat(),
            "inicio": siguiente.inicio_programado.isoformat(),
            "fin": siguiente.fin_programado.isoformat()}


@router.post("/jornadas/{jornada_id}/reabrir",
             summary="Deshacer un cierre a mano")
def reabrir_dia(jornada_id: int, datos: s.ReabrirDiaIn,
                db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(CORREGIR)):
    """Deshace un cierre, lo haya hecho la central o el equipo.

    El de la central se deshace entero: ahi alguien tecleo una hora en
    una oficina y si se equivoco, se borra.

    El del equipo es otra cosa: hay una marca de fin con su hora, su
    ubicacion y quien la hizo. Esa marca se ANULA --deja de contar, y el
    equipo puede volver a cerrar-- pero no se borra: se queda con el
    nombre de quien la anulo y con el motivo. Dentro de seis meses
    alguien va a querer saber por que ese dia se cerro dos veces.
    """
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    resultado = motor.reabrir(db, jornada_id, usuario.persona_id,
                              datos.justificacion)
    auditoria.registrar(db, usuario, jornada.equipo.servicio,
                        "reabrir dia",
                        f"{jornada.fecha}: {datos.justificacion}",
                        jornada_id=jornada.id)
    db.commit()
    return resultado


@router.get("/tablero-proximos", summary="Servicios a dos horas de iniciar")
def tablero(db: Session = Depends(get_db), ahora: datetime | None = None,
            _=Depends(VER)):
    """Valida confirmacion del recurso, viatico transferido y vehiculo asignado."""
    return motor.tablero_proximos(db, ahora)


@router.post("/revisar-standby", summary="Detectar servicios sin reporte")
def revisar_standby(db: Session = Depends(get_db), ahora: datetime | None = None,
                    _=Depends(VER)):
    return {"alertas_generadas": motor.revisar_standby(db, ahora)}


@router.post("/avisar-horas-extra", summary="Aviso preventivo de horas extra")
def avisar_horas_extra(db: Session = Depends(get_db), ahora: datetime | None = None,
                       _=Depends(VER)):
    return {"avisos": motor.avisar_horas_extra(db, ahora)}


@router.get("/jornadas/{jornada_id}/bitacora", summary="Bitacora de la jornada")
def bitacora(jornada_id: int, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(auth.usuario_actual)):
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    # El personal de seguridad solo ve la bitacora de sus propias jornadas.
    if usuario.rol == m.Rol.PERSONAL_SEGURIDAD and \
            not auth.es_su_propia_jornada(db, usuario, jornada_id):
        raise HTTPException(403, "No estas asignado a esa jornada")

    hitos = (db.query(m.Hito).filter_by(jornada_id=jornada_id)
             .order_by(m.Hito.marcado_en).all())
    alertas = db.query(m.Alerta).filter_by(jornada_id=jornada_id).all()
    notificaciones = db.query(m.Notificacion).filter_by(jornada_id=jornada_id).all()

    return {
        "jornada": {
            "id": jornada.id, "fecha": jornada.fecha.isoformat(),
            "estatus": jornada.estatus.value,
            "programado": f"{jornada.inicio_programado:%H:%M} - {jornada.fin_programado:%H:%M}",
            "inicio_real": jornada.inicio_real.isoformat() if jornada.inicio_real else None,
            "fin_real": jornada.fin_real.isoformat() if jornada.fin_real else None,
            # Si la central cerro este dia a mano, tiene que verse aqui
            # para siempre: es la diferencia entre un dia que alguien
            # marco desde la calle y uno que alguien firmo desde una
            # oficina, y esa diferencia no se puede perder.
            "cerrada_a_mano": ({
                "por": (jornada.cerrada_a_mano_por.nombre
                        if jornada.cerrada_a_mano_por else None),
                "cuando": jornada.cerrada_a_mano_en.isoformat(),
                "motivo": jornada.cierre_motivo,
            } if jornada.cerrada_a_mano_en else None),
        },
        "hitos": [{
            # El numero de la marca. Faltaba, y sin el la bitacora no
            # sirve para lo unico que la central hace con ella:
            # `POST /operacion/hitos/{id}/ajustar` existe y es la forma
            # documentada de corregir una hora, pero desde la consola no
            # habia manera de saber que numero mandar.
            "id": h.id,
            "tipo": h.tipo.value,
            "marcado_en": h.marcado_en.isoformat(),
            "marcado_por": h.persona.nombre,
            "distancia_origen_m": h.distancia_origen_m,
            "dentro_geocerca": h.dentro_geocerca,
            "fuera_de_ventana": h.fuera_de_ventana,
            "requiere_revision": h.requiere_revision,
            "ajuste": ({"original": h.marcado_original.isoformat(),
                        "ajustado_por": (db.get(m.Persona, h.ajustado_por_id).nombre
                                         if h.ajustado_por_id else None),
                        "justificacion": h.justificacion_ajuste}
                       if h.marcado_original else None),
            "nota": h.nota,
        } for h in hitos],
        "alertas": [{"id": a.id, "tipo": a.tipo.value, "mensaje": a.mensaje,
                     "atendida": a.atendida} for a in alertas],
        "notificaciones": [{"para": n.destinatario.value, "canal": n.canal.value,
                            "correo": n.correo, "asunto": n.asunto,
                            "enlace": n.enlace_seguimiento,
                            "expira": n.expira_en.isoformat() if n.expira_en else None}
                           for n in notificaciones],
    }


@router.get("/alertas", summary="Alertas abiertas de la central")
def alertas(db: Session = Depends(get_db), solo_abiertas: bool = True,
            _=Depends(VER)):
    consulta = db.query(m.Alerta)
    if solo_abiertas:
        consulta = consulta.filter(m.Alerta.atendida.is_(False))
    return [{"id": a.id, "jornada_id": a.jornada_id, "tipo": a.tipo.value,
             "mensaje": a.mensaje, "creada_en": a.creada_en.isoformat()}
            for a in consulta.order_by(m.Alerta.id.desc()).all()]


@router.post("/alertas/{alerta_id}/atender", summary="La central atiende una alerta")
def atender_alerta(alerta_id: int, resolucion: str,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(ATENDER)):
    alerta = db.get(m.Alerta, alerta_id)
    if not alerta:
        raise HTTPException(404, f"No existe la alerta {alerta_id}")
    if not resolucion or len(resolucion.strip()) < 10:
        raise HTTPException(400, "Describe como se resolvio la alerta")
    alerta.atendida = True
    alerta.atendida_por_id = usuario.persona_id
    alerta.resolucion = resolucion
    db.commit()
    return {"resultado": "atendida", "alerta_id": alerta.id}

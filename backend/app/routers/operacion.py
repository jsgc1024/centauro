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
from app import operacion as motor
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/operacion", tags=["Operacion"])

CENTRAL = auth.requiere(m.Rol.CENTRAL, m.Rol.DIRECTOR_OPERACIONES)
MONITOREO = auth.requiere(m.Rol.CENTRAL, m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES)
PLANEACION = auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL, m.Rol.DIRECTOR_OPERACIONES)
CAMPO = auth.requiere(m.Rol.PERSONAL_SEGURIDAD)


@router.patch("/jornadas/{jornada_id}/origen",
              summary="Configurar el punto de origen y su geocerca")
def configurar_origen(jornada_id: int, datos: s.OrigenIn,
                      db: Session = Depends(get_db),
                      _=Depends(PLANEACION)):
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
                     _=Depends(PLANEACION)):
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
    db.commit()
    return {"resultado": "confirmado", "persona": asignacion.persona.nombre}


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
            usuario: m.Usuario = Depends(CENTRAL)):
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

@router.get("/dias-sin-cerrar", summary="Dias que ya pasaron y siguen abiertos")
def dias_sin_cerrar(db: Session = Depends(get_db),
                    ahora: datetime | None = None,
                    pais_id: int | None = None,
                    _=Depends(MONITOREO)):
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
                  usuario: m.Usuario = Depends(CENTRAL)):
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


@router.post("/jornadas/{jornada_id}/reabrir",
             summary="Deshacer un cierre a mano")
def reabrir_dia(jornada_id: int, datos: s.ReabrirDiaIn,
                db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(CENTRAL)):
    """Solo se deshace lo que la central cerro. Un dia que el equipo
    marco desde la calle se corrige ajustando el hito."""
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
            _=Depends(MONITOREO)):
    """Valida confirmacion del recurso, viatico transferido y vehiculo asignado."""
    return motor.tablero_proximos(db, ahora)


@router.post("/revisar-standby", summary="Detectar servicios sin reporte")
def revisar_standby(db: Session = Depends(get_db), ahora: datetime | None = None,
                    _=Depends(MONITOREO)):
    return {"alertas_generadas": motor.revisar_standby(db, ahora)}


@router.post("/avisar-horas-extra", summary="Aviso preventivo de horas extra")
def avisar_horas_extra(db: Session = Depends(get_db), ahora: datetime | None = None,
                       _=Depends(MONITOREO)):
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
            _=Depends(MONITOREO)):
    consulta = db.query(m.Alerta)
    if solo_abiertas:
        consulta = consulta.filter(m.Alerta.atendida.is_(False))
    return [{"id": a.id, "jornada_id": a.jornada_id, "tipo": a.tipo.value,
             "mensaje": a.mensaje, "creada_en": a.creada_en.isoformat()}
            for a in consulta.order_by(m.Alerta.id.desc()).all()]


@router.post("/alertas/{alerta_id}/atender", summary="La central atiende una alerta")
def atender_alerta(alerta_id: int, resolucion: str,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(MONITOREO)):
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

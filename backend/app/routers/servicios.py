"""Alta de servicios, equipos, jornadas y asignacion de recursos."""
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auditoria
from app import auth
from app import programacion
from app import telefonos
from app.routers import solicitantes as contactos
from app import disponibilidad as disp
from app import geocercas
from app import models as m
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/servicios", tags=["Servicios"])


# ---------------------------------------------------------------- utilidades

# Alias operativo de cada equipo dentro del servicio.
ALFABETO_GRIEGO = [
    "Alfa", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta",
    "Iota", "Kappa", "Lambda", "My", "Ny", "Xi", "Omicron", "Pi", "Rho",
    "Sigma", "Tau", "Ypsilon", "Fi", "Ji", "Psi", "Omega",
]


def alias_de_equipo(posicion: int) -> str:
    """Alfa, Beta, Gamma... y si un servicio pasara de 24 equipos,
    se reinicia con un numero: Alfa 2, Beta 2."""
    vuelta, indice = divmod(posicion, len(ALFABETO_GRIEGO))
    alias = ALFABETO_GRIEGO[indice]
    return alias if vuelta == 0 else f"{alias} {vuelta + 1}"


# La serie del folio dice de que linea es y de que tipo: EP de Proteccion
# Ejecutiva, E de eventual e I de implantado. Cada tipo lleva su propio
# consecutivo, porque son dos operaciones distintas y mezclarlas dejaba la
# serie del eventual llena de huecos.
SERIE_DE = {
    m.TipoServicio.EVENTUAL: "EP/E",
    m.TipoServicio.IMPLANTADO: "EP/IM",
}


def siguiente_folio(db: Session, tipo: m.TipoServicio) -> str:
    """El siguiente de su serie: EP/E-001, EP/IM-001.

    Cuenta tambien los folios de servicios ya eliminados. Un folio que
    salio por correo no se vuelve a usar aunque el servicio ya no exista:
    el cliente tiene ese numero escrito en algun lado.
    """
    prefijo = SERIE_DE[tipo]
    usados = [f for (f,) in db.query(m.Servicio.folio).all()]
    usados += [f for (f,) in db.query(m.ServicioEliminado.folio).all()]

    numeros = []
    for folio in usados:
        if not folio or not folio.startswith(f"{prefijo}-"):
            continue
        cola = folio.rsplit("-", 1)[-1]
        if cola.isdigit():
            numeros.append(int(cola))
    return f"{prefijo}-{max(numeros, default=0) + 1:03d}"


# Cuando un dia no trae hora propia y tampoco hay de donde heredarla.
HORA_POR_OMISION = time(8, 0)


def _ventana(db: Session, datos: s.JornadaIn,
             hora_heredada: time | None = None
             ) -> tuple[datetime, datetime, m.Modalidad]:
    """Calcula inicio y fin programados a partir de la modalidad del pais.

    La hora de presentacion es del dia 1. Los dias siguientes la heredan
    mientras no se cargue su agenda: sin una hora no se puede saber si el
    conductor se empalma con otro servicio."""
    modalidad = db.get(m.Modalidad, datos.modalidad_id)
    if not modalidad:
        raise HTTPException(400, f"No existe la modalidad {datos.modalidad_id}")
    hora = datos.hora_presentacion or hora_heredada or HORA_POR_OMISION
    inicio = datetime.combine(datos.fecha, hora)
    fin = inicio + timedelta(hours=float(modalidad.horas))
    return inicio, fin, modalidad


def _km_del_dia(db: Session, datos) -> int | None:
    """Los km que se capturaron o, si no, el recorrido tipico de la
    modalidad: transfer 40, medio dia 80, dia completo 150.

    Vaciar el campo a proposito no es lo mismo que no tocarlo: quien
    manda km en nulo esta diciendo "no se cuantos son", y entonces el
    combustible se queda manual en vez de proponer un numero inventado.
    """
    if datos.km_estimados is not None:
        return datos.km_estimados
    if "km_estimados" in datos.model_fields_set:
        return None
    modalidad = db.get(m.Modalidad, datos.modalidad_id)
    return modalidad.km_estimados if modalidad else None


def _obtener_jornada(db: Session, jornada_id: int) -> m.Jornada:
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    return jornada


# ---------------------------------------------------------------- alta

@router.post("", response_model=s.ServicioOut, status_code=201,
             summary="Dar de alta un servicio con sus equipos y jornadas")
def crear_servicio(datos: s.ServicioIn, db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(
                       auth.puede("servicios.alta"))):
    """El desglose por jornada viene desde la cotizacion: cada dia lleva su
    propia modalidad (dia 1 transfer, dias 2 y 3 full day, dia 4 medio dia).

    Si el alta trae el minimo (cliente, quien solicita, el dia con su hora
    y el punto de inicio), el servicio queda programado de una vez."""
    servicio = m.Servicio(
        folio="",           # se arma con el consecutivo, ya con id asignado
        **datos.model_dump(exclude={"equipos"}),
    )

    # Quien solicita: se elige de la lista del cliente, o se capturan sus
    # datos y queda dado de alta para la proxima vez.
    if datos.solicitante_id:
        contacto = db.get(m.Solicitante, datos.solicitante_id)
        if not contacto:
            raise HTTPException(404, f"No existe el solicitante {datos.solicitante_id}")
        if contacto.cliente_id != datos.cliente_id:
            raise HTTPException(400, {
                "mensaje": "Ese contacto pertenece a otro cliente",
                "solicitante": contacto.completo,
            })
    else:
        contacto = contactos.buscar_o_crear(
            db, datos.cliente_id, datos.solicitante_nombre,
            datos.solicitante_apellidos, datos.solicitante_correo,
            datos.solicitante_telefono)

    # Ningun telefono se guarda sin clave de pais.
    for campo in ("solicitante_telefono", "ejecutivo_telefono"):
        setattr(servicio, campo,
                telefonos.normalizar(db, getattr(servicio, campo), datos.pais_id))

    if contacto:
        servicio.solicitante_id = contacto.id
        servicio.solicitante_nombre = contacto.nombre
        servicio.solicitante_apellidos = contacto.apellidos
        servicio.solicitante_correo = servicio.solicitante_correo or contacto.correo
        servicio.solicitante_telefono = (servicio.solicitante_telefono
                                         or contacto.telefono)

    db.add(servicio)
    db.flush()
    servicio.folio = siguiente_folio(db, servicio.tipo)

    for posicion, eq in enumerate(datos.equipos):
        equipo = m.Equipo(servicio_id=servicio.id,
                          alias=alias_de_equipo(posicion),
                          clave=eq.clave or alias_de_equipo(posicion),
                          descripcion=eq.descripcion,
                          plaza_id=eq.plaza_id,
                          ejecutivo_nombre=eq.ejecutivo_nombre,
                          ejecutivo_apellidos=eq.ejecutivo_apellidos,
                          ejecutivo_correo=eq.ejecutivo_correo,
                          ejecutivo_telefono=telefonos.normalizar(
                              db, eq.ejecutivo_telefono, datos.pais_id))
        db.add(equipo)
        db.flush()
        # La hora del dia 1 es la que heredan los demas mientras no
        # tengan agenda propia.
        en_orden = sorted(eq.jornadas, key=lambda j: j.fecha)
        hora_del_primero = next(
            (j.hora_presentacion for j in en_orden if j.hora_presentacion), None)

        for jo in eq.jornadas:
            inicio, fin, _ = _ventana(db, jo, hora_del_primero)
            jornada = m.Jornada(
                equipo_id=equipo.id, fecha=jo.fecha,
                modalidad_id=jo.modalidad_id,
                inicio_programado=inicio, fin_programado=fin,
                hora_confirmada=jo.hora_presentacion is not None,
                es_foraneo=jo.es_foraneo,
                km_estimados=_km_del_dia(db, jo),
            )
            # Marcar como aeropuerto un lugar que Google dice que no lo
            # es abre la geocerca de 500 m a 2 km. Se puede hacer a
            # proposito —hay terminales privadas— pero no de pasada.
            geocercas.revisar_aeropuerto(jo.origen_aeropuerto,
                                         jo.origen_google_aeropuerto,
                                         jo.forzar_aeropuerto)
            # El punto de inicio y el vuelo, cuando el alta los trae.
            for campo in ("origen_direccion", "origen_lat", "origen_lon",
                          "geocerca_metros", "origen_aeropuerto",
                          "origen_google_aeropuerto",
                          "vuelo_aerolinea", "vuelo_numero",
                          "vuelo_hora", "vuelo_origen", "vuelo_tipo"):
                valor = getattr(jo, campo, None)
                if valor is not None:
                    setattr(jornada, campo, valor)
            # El radio lo pone el tipo de lugar, salvo que se capture uno.
            if jo.geocerca_metros is None:
                jornada.geocerca_metros = geocercas.radio_de(jo.origen_aeropuerto)
            db.add(jornada)
            # La agenda del dia, si el alta ya la trae.
            if jo.paradas or jo.agenda_resumen or jo.agenda_puntos:
                db.flush()
                if jo.agenda_resumen or jo.agenda_puntos:
                    db.add(m.AgendaJornada(
                        jornada_id=jornada.id,
                        resumen=jo.agenda_resumen, puntos=jo.agenda_puntos,
                        cargada_por_id=usuario.persona_id))
                for parada in jo.paradas:
                    db.add(m.ParadaAgenda(jornada_id=jornada.id,
                                          **parada.model_dump()))

    db.flush()
    pendientes = programacion.evaluar(servicio)
    detalle = f"{len(datos.equipos)} equipo(s)"
    if pendientes:
        detalle += f" · falta para programar: {'; '.join(pendientes)}"
    auditoria.registrar(db, usuario, servicio, "alta de servicio", detalle)
    db.commit()
    db.refresh(servicio)
    return servicio


@router.get("", response_model=list[s.ServicioOut], summary="Listar servicios")
def listar_servicios(db: Session = Depends(get_db), limite: int = 100,
                     tipo: m.TipoServicio = m.TipoServicio.EVENTUAL,
                     todos: bool = False,
                     _=Depends(auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL, m.Rol.DIRECTOR_OPERACIONES))):
    """Eventuales por omision.

    El implantado se opera en su propia pantalla —se captura por mes, no
    por dias— y revuelto en esta lista solo estorbaba. Con todos=true
    salen los dos, para quien necesite ver la operacion completa.
    """
    consulta = db.query(m.Servicio)
    if not todos:
        consulta = consulta.filter(m.Servicio.tipo == tipo)
    return consulta.order_by(m.Servicio.id.desc()).limit(limite).all()


@router.get("/{servicio_id}/programacion",
            summary="Que le falta al servicio para quedar programado")
def ver_programacion(servicio_id: int, db: Session = Depends(get_db),
                     _=Depends(auth.puede("servicios.ver"))):
    """El minimo es corto: cliente, quien solicita, el dia con su hora y el
    punto de inicio. El equipo y la unidad son el paso siguiente."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    return programacion.estado(servicio)


@router.get("/{servicio_id}", response_model=s.ServicioOut, summary="Ver servicio")
def ver_servicio(servicio_id: int, db: Session = Depends(get_db),
                 _=Depends(auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL, m.Rol.DIRECTOR_OPERACIONES))):
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    return servicio


# ---------------------------------------------------------------- recomendacion

@router.get("/jornadas/{jornada_id}/recomendaciones",
            summary="Recomendar personal y vehiculos por plaza y disponibilidad")
def recomendaciones(jornada_id: int, categoria_id: int,
                    perfil_id: int | None = None,
                    db: Session = Depends(get_db),
                    _=Depends(auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL, m.Rol.DIRECTOR_OPERACIONES))):
    jornada = _obtener_jornada(db, jornada_id)
    # La ciudad del equipo: en un proyecto que va de Mexico a Monterrey,
    # el local de Monterrey es el de Beta, no el del servicio.
    plaza_id = jornada.equipo.ciudad_id
    bloquea = jornada.modalidad.bloquea_dia_completo

    return {
        "jornada": {
            "id": jornada.id,
            "fecha": jornada.fecha.isoformat(),
            "inicio": jornada.inicio_programado.isoformat(),
            "fin": jornada.fin_programado.isoformat(),
            "modalidad": jornada.modalidad.codigo.value,
        },
        "personal": disp.recomendar_personal(
            db, plaza_id, perfil_id,
            jornada.inicio_programado, jornada.fin_programado, bloquea),
        "vehiculos": disp.recomendar_vehiculos(
            db, plaza_id, categoria_id,
            jornada.inicio_programado, jornada.fin_programado, bloquea,
            servicio_id=jornada.equipo.servicio_id),
    }


# ---------------------------------------------------------------- asignacion

def _rol(db: Session, rol_id: int | None):
    """El rol con el que va esa persona.

    Puede venir vacio mientras se arma el servicio —a veces primero se
    aparta a la gente y despues se decide quien hace que— pero sin el no
    se puede cotizar ni cerrar, y ahi se exige.
    """
    if not rol_id:
        return None
    rol = db.get(m.PerfilPersonal, rol_id)
    if not rol:
        raise HTTPException(404, f"No existe el rol {rol_id}")
    return rol


@router.post("/jornadas/{jornada_id}/asignar-personal",
             summary="Asignar una persona a la jornada")
def asignar_personal(jornada_id: int, datos: s.AsignarPersonalIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(
                         auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES))):
    """Bloqueo duro si hay empalme real. Si solo hay holgura insuficiente
    se devuelve alerta de riesgo y el consultor decide con forzar=true."""
    jornada = _obtener_jornada(db, jornada_id)
    persona = db.get(m.Persona, datos.persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {datos.persona_id}")
    rol = _rol(db, datos.rol_id)

    hallazgos = disp.revisar_persona(
        db, persona.id, jornada.inicio_programado, jornada.fin_programado,
        jornada.modalidad.bloquea_dia_completo, excluir_jornada_id=jornada.id)

    bloqueos = [h for h in hallazgos if h.nivel == "bloqueo"]
    riesgos = [h for h in hallazgos if h.nivel == "riesgo"]

    if bloqueos:
        raise HTTPException(409, {
            "mensaje": "Bloqueo duro: el recurso no esta disponible",
            "alertas": [h.como_dict() for h in bloqueos],
        })

    if riesgos and not datos.forzar:
        raise HTTPException(409, {
            "mensaje": "Alerta de riesgo. Confirme con forzar=true para asignar.",
            "alertas": [h.como_dict() for h in riesgos],
        })

    db.add(m.AsignacionPersonal(jornada_id=jornada.id, persona_id=persona.id,
                                rol_id=datos.rol_id))
    auditoria.registrar(db, usuario, jornada.equipo.servicio, "asignar personal",
                        f"{persona.nombre} como {rol.nombre if rol else 'sin rol'}"
                        + (" (forzado sobre alerta)" if riesgos else ""),
                        jornada_id=jornada.id)
    db.flush()
    servicio = jornada.equipo.servicio
    programacion.evaluar(servicio)
    db.commit()
    return {"resultado": "asignado", "persona": persona.nombre,
            "rol": rol.nombre if rol else None,
            "estatus_servicio": servicio.estatus.value,
            "faltantes_de_recursos": programacion.faltantes_de_recursos(servicio),
            "alertas_aceptadas": [h.como_dict() for h in riesgos]}


@router.post("/jornadas/{jornada_id}/asignar-vehiculo",
             summary="Asignar un vehiculo a la jornada")
def asignar_vehiculo(jornada_id: int, datos: s.AsignarVehiculoIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(
                         auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES))):
    jornada = _obtener_jornada(db, jornada_id)
    vehiculo = db.get(m.Vehiculo, datos.vehiculo_id)
    if not vehiculo:
        raise HTTPException(404, f"No existe el vehiculo {datos.vehiculo_id}")

    hallazgos = disp.revisar_vehiculo(
        db, vehiculo.id, jornada.inicio_programado, jornada.fin_programado,
        jornada.modalidad.bloquea_dia_completo, excluir_jornada_id=jornada.id)

    bloqueos = [h for h in hallazgos if h.nivel == "bloqueo"]
    riesgos = [h for h in hallazgos if h.nivel == "riesgo"]

    if bloqueos:
        raise HTTPException(409, {
            "mensaje": "Bloqueo duro: la unidad no esta disponible",
            "alertas": [h.como_dict() for h in bloqueos],
        })

    if riesgos and not datos.forzar:
        raise HTTPException(409, {
            "mensaje": "Alerta de riesgo. Confirme con forzar=true para asignar.",
            "alertas": [h.como_dict() for h in riesgos],
        })

    db.add(m.AsignacionVehiculo(jornada_id=jornada.id, vehiculo_id=vehiculo.id))
    auditoria.registrar(db, usuario, jornada.equipo.servicio, "asignar vehiculo",
                        vehiculo.placa, jornada_id=jornada.id)
    db.flush()
    servicio = jornada.equipo.servicio
    programacion.evaluar(servicio)
    db.commit()
    return {"resultado": "asignado", "vehiculo": vehiculo.placa,
            "estatus_servicio": servicio.estatus.value,
            "faltantes_de_recursos": programacion.faltantes_de_recursos(servicio),
            "alertas_aceptadas": [h.como_dict() for h in riesgos]}


@router.post("/equipos/{equipo_id}/jornadas", status_code=201,
             summary="Agregar un dia a un equipo ya dado de alta")
def agregar_dia(equipo_id: int, datos: s.JornadaIn,
                db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(auth.puede("servicios.alta"))):
    """El servicio se sigue armando despues del alta: el cliente confirma
    un dia mas y no hay que volver a capturar todo."""
    equipo = db.get(m.Equipo, equipo_id)
    if not equipo:
        raise HTTPException(404, f"No existe el equipo {equipo_id}")
    if any(j.fecha == datos.fecha for j in equipo.jornadas):
        raise HTTPException(409, {
            "mensaje": "Ese equipo ya tiene ese dia",
            "fecha": datos.fecha.isoformat(),
        })

    primera = min(equipo.jornadas, key=lambda j: j.fecha, default=None)
    inicio, fin, _ = _ventana(db, datos,
                              primera.inicio_programado.time() if primera else None)
    jornada = m.Jornada(
        equipo_id=equipo.id, fecha=datos.fecha,
        modalidad_id=datos.modalidad_id,
        inicio_programado=inicio, fin_programado=fin,
        hora_confirmada=datos.hora_presentacion is not None,
        es_foraneo=datos.es_foraneo, km_estimados=_km_del_dia(db, datos))
    for campo in ("origen_direccion", "origen_lat", "origen_lon",
                  "geocerca_metros"):
        valor = getattr(datos, campo, None)
        if valor is not None:
            setattr(jornada, campo, valor)
    db.add(jornada)
    db.flush()

    servicio = equipo.servicio
    programacion.evaluar(servicio)
    auditoria.registrar(db, usuario, servicio, "agregar dia",
                        f"{equipo.alias}: {datos.fecha}", jornada_id=jornada.id)
    db.commit()
    db.refresh(jornada)
    return {"resultado": "dia agregado", "jornada_id": jornada.id,
            "fecha": jornada.fecha.isoformat(),
            "estatus_servicio": servicio.estatus.value}


@router.patch("/jornadas/{jornada_id}", summary="Corregir un dia del servicio")
def corregir_dia(jornada_id: int, datos: s.DiaIn, db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(auth.puede("servicios.alta"))):
    """Cambia la fecha, la modalidad o la hora. La ventana del dia se
    vuelve a calcular: de ella dependen los empalmes y las horas extra."""
    jornada = _obtener_jornada(db, jornada_id)
    cambios = datos.model_dump(exclude_unset=True)

    if "fecha" in cambios and cambios["fecha"]:
        repetida = any(j.fecha == cambios["fecha"] and j.id != jornada.id
                       for j in jornada.equipo.jornadas)
        if repetida:
            raise HTTPException(409, {
                "mensaje": "Ese equipo ya tiene ese dia",
                "fecha": cambios["fecha"].isoformat(),
            })
        jornada.fecha = cambios["fecha"]
    if cambios.get("modalidad_id"):
        if not db.get(m.Modalidad, cambios["modalidad_id"]):
            raise HTTPException(400, f"No existe la modalidad {cambios['modalidad_id']}")
        jornada.modalidad_id = cambios["modalidad_id"]
    if "km_estimados" in cambios:
        jornada.km_estimados = cambios["km_estimados"]
    if "es_foraneo" in cambios and cambios["es_foraneo"] is not None:
        jornada.es_foraneo = cambios["es_foraneo"]

    hora = cambios.get("hora_presentacion") or jornada.inicio_programado.time()
    if cambios.get("hora_presentacion"):
        jornada.hora_confirmada = True     # ya no es la heredada
    modalidad = db.get(m.Modalidad, jornada.modalidad_id)
    jornada.inicio_programado = datetime.combine(jornada.fecha, hora)
    jornada.fin_programado = (jornada.inicio_programado
                              + timedelta(hours=float(modalidad.horas)))

    servicio = jornada.equipo.servicio
    programacion.evaluar(servicio)
    auditoria.registrar(db, usuario, servicio, "corregir dia",
                        f"{jornada.fecha} {hora.strftime('%H:%M')}",
                        jornada_id=jornada.id)
    db.commit()
    return {"resultado": "dia corregido", "jornada_id": jornada.id,
            "fecha": jornada.fecha.isoformat(),
            "inicio": jornada.inicio_programado.isoformat(),
            "fin": jornada.fin_programado.isoformat(),
            "estatus_servicio": servicio.estatus.value}


@router.delete("/jornadas/{jornada_id}", summary="Quitar un dia del servicio")
def quitar_dia(jornada_id: int, db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(auth.puede("servicios.alta"))):
    """Solo mientras el dia no haya empezado a moverse: con viaticos
    entregados o hitos marcados ya hay dinero y rastro de por medio, y eso
    se cancela, no se borra."""
    jornada = _obtener_jornada(db, jornada_id)
    equipo = jornada.equipo
    if len(equipo.jornadas) == 1:
        raise HTTPException(409, "El equipo se quedaria sin dias. "
                                 "Cancela el servicio en vez de quitarlo.")

    con_viaticos = (db.query(m.AsignacionViatico)
                    .filter_by(jornada_id=jornada.id).count())
    if con_viaticos:
        raise HTTPException(409, {
            "mensaje": "Ese dia ya tiene viaticos asignados",
            "que_hacer": "Cancelalos primero o cancela el servicio",
        })

    fecha = jornada.fecha.isoformat()
    servicio = equipo.servicio
    # Lo que cuelga del dia se va con el; lo que solo lo menciona —la
    # bitacora, un aviso, un renglon de nomina— se queda sin el enlace,
    # porque esa historia no es del dia, es de quien la hizo.
    _limpiar_jornadas(db, [jornada.id])
    db.delete(jornada)
    db.flush()

    programacion.evaluar(servicio)
    auditoria.registrar(db, usuario, servicio, "quitar dia",
                        f"{equipo.alias}: {fecha}")
    db.commit()
    return {"resultado": "dia quitado", "fecha": fecha,
            "estatus_servicio": servicio.estatus.value}


@router.patch("/jornadas/{jornada_id}/personal/{persona_id}/unidad",
              summary="Decir en que unidad va una persona del equipo")
def abordo(jornada_id: int, persona_id: int, datos: s.AbordoIn,
           db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(
               auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES))):
    """Solo entre lo que ya esta asignado a esa jornada: no se puede subir
    a alguien a una unidad que ese dia trae otro equipo."""
    jornada = _obtener_jornada(db, jornada_id)
    asignacion = (db.query(m.AsignacionPersonal)
                  .filter_by(jornada_id=jornada.id, persona_id=persona_id)
                  .first())
    if not asignacion:
        raise HTTPException(404, "Esa persona no esta asignada a la jornada")

    if datos.vehiculo_id is not None:
        a_bordo = (db.query(m.AsignacionVehiculo)
                   .filter_by(jornada_id=jornada.id, vehiculo_id=datos.vehiculo_id)
                   .first())
        if not a_bordo:
            raise HTTPException(400, {
                "mensaje": "Esa unidad no esta asignada a la jornada",
                "vehiculo_id": datos.vehiculo_id,
            })

    asignacion.vehiculo_id = datos.vehiculo_id
    unidad = db.get(m.Vehiculo, datos.vehiculo_id) if datos.vehiculo_id else None
    auditoria.registrar(db, usuario, jornada.equipo.servicio, "abordo",
                        f"{asignacion.persona.nombre} "
                        + (f"va en {unidad.placa}" if unidad else "sin unidad"),
                        jornada_id=jornada.id)
    db.commit()
    return {"resultado": "abordo actualizado",
            "persona": asignacion.persona.nombre,
            "vehiculo_id": asignacion.vehiculo_id,
            "placa": unidad.placa if unidad else None}


# ------------------------------------------------- recursos del equipo

def _equipo(db: Session, equipo_id: int) -> m.Equipo:
    equipo = db.get(m.Equipo, equipo_id)
    if not equipo:
        raise HTTPException(404, f"No existe el equipo {equipo_id}")
    return equipo


def _dias_vivos(equipo: m.Equipo) -> list[m.Jornada]:
    return sorted([j for j in equipo.jornadas
                   if j.estatus != m.EstatusJornada.CANCELADA],
                  key=lambda j: j.fecha)


@router.get("/equipos/{equipo_id}/recomendaciones",
            summary="Recomendar personal y unidades para todo el equipo")
def recomendaciones_equipo(equipo_id: int, categoria_id: int,
                           perfil_id: int | None = None,
                           db: Session = Depends(get_db),
                           _=Depends(auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL,
                                                   m.Rol.DIRECTOR_OPERACIONES))):
    """Se revisa dia por dia y se contesta por el equipo completo.

    Quien tenga un choque en cualquiera de los dias sale bloqueado con la
    fecha del choque: de nada sirve el conductor que esta libre el lunes
    si el miercoles trae otro servicio."""
    equipo = _equipo(db, equipo_id)
    dias = _dias_vivos(equipo)
    if not dias:
        raise HTTPException(409, "El equipo no tiene dias que cubrir")

    plaza_id = equipo.ciudad_id
    por_dia = [
        (j, disp.recomendar_personal(db, plaza_id, perfil_id,
                                     j.inicio_programado, j.fin_programado,
                                     j.modalidad.bloquea_dia_completo),
         disp.recomendar_vehiculos(db, plaza_id, categoria_id,
                                   j.inicio_programado, j.fin_programado,
                                   j.modalidad.bloquea_dia_completo,
                                   servicio_id=equipo.servicio_id))
        for j in dias
    ]

    return {
        "equipo": {"id": equipo.id, "alias": equipo.alias,
                   "dias": len(dias),
                   "desde": dias[0].fecha.isoformat(),
                   "hasta": dias[-1].fecha.isoformat()},
        "personal": _juntar([p for _, p, _ in por_dia],
                            [j.fecha for j in dias], "persona_id"),
        "vehiculos": _juntar([v for _, _, v in por_dia],
                             [j.fecha for j in dias], "vehiculo_id"),
    }


def _juntar(por_dia: list[dict], fechas: list, llave: str) -> dict:
    """Junta la disponibilidad de todos los dias en una sola respuesta.

    Un recurso queda como esta el peor de sus dias: si el miercoles esta
    ocupado, sale ocupado, y el motivo dice que dia. Asi el consultor no
    asigna a alguien que se le va a caer a media semana.
    """
    fichas: dict = {}
    for bloque, fecha in zip(por_dia, fechas):
        for grupo in ("disponibles", "con_alerta", "no_disponibles",
                      "de_otras_ciudades"):
            for ficha in bloque.get(grupo) or []:
                id_ = ficha[llave]
                junta = fichas.setdefault(id_, {**ficha, "alertas": [],
                                                "bloqueado": False})
                junta["bloqueado"] = junta["bloqueado"] or ficha["bloqueado"]
                for alerta in ficha.get("alertas") or []:
                    # El motivo lleva el dia: "07/10: se empalma con EP-0009".
                    copia = dict(alerta)
                    copia["mensaje"] = (f"{fecha.strftime('%d/%m')}: "
                                        f"{alerta.get('mensaje') or alerta.get('tipo')}")
                    junta["alertas"].append(copia)

    libres, con_riesgo, ocupados, foraneos = [], [], [], []
    for ficha in fichas.values():
        if not ficha.get("local", True):
            foraneos.append(ficha)
        elif ficha["bloqueado"]:
            ocupados.append(ficha)
        elif ficha["alertas"]:
            con_riesgo.append(ficha)
        else:
            libres.append(ficha)

    for grupo in (libres, con_riesgo):
        grupo.sort(key=lambda f: f.get("calificacion") or 0, reverse=True)
    foraneos.sort(key=lambda f: (f["bloqueado"], -(f.get("calificacion") or 0)))

    aviso = None
    if not libres and not con_riesgo:
        aviso = ("Sin recurso local disponible todos los dias. Se requiere "
                 "traslado (genera viaticos extra) o alta de un freelance.")
    return {"disponibles": libres, "con_alerta": con_riesgo,
            "no_disponibles": ocupados, "de_otras_ciudades": foraneos,
            "aviso": aviso}


@router.post("/equipos/{equipo_id}/asignar-personal",
             summary="Asignar una persona a todos los dias del equipo")
def asignar_personal_equipo(equipo_id: int, datos: s.AsignarPersonalIn,
                            db: Session = Depends(get_db),
                            usuario: m.Usuario = Depends(
                                auth.requiere(m.Rol.CONSULTOR,
                                              m.Rol.DIRECTOR_OPERACIONES))):
    """El equipo es la misma gente de principio a fin. Si hay bloqueo en
    cualquier dia no se asigna ninguno: dejar el servicio a medias es
    peor que no empezarlo."""
    equipo = _equipo(db, equipo_id)
    persona = db.get(m.Persona, datos.persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {datos.persona_id}")
    rol = _rol(db, datos.rol_id)
    dias = _dias_vivos(equipo)
    if not dias:
        raise HTTPException(409, "El equipo no tiene dias que cubrir")

    bloqueos, riesgos = [], []
    for jornada in dias:
        for hallazgo in disp.revisar_persona(
                db, persona.id, jornada.inicio_programado,
                jornada.fin_programado, jornada.modalidad.bloquea_dia_completo,
                excluir_jornada_id=jornada.id):
            destino = bloqueos if hallazgo.nivel == "bloqueo" else riesgos
            destino.append({**hallazgo.como_dict(),
                            "fecha": jornada.fecha.isoformat()})

    if bloqueos:
        raise HTTPException(409, {
            "mensaje": f"{persona.nombre} no esta disponible todos los dias",
            "alertas": bloqueos,
        })
    if riesgos and not datos.forzar:
        raise HTTPException(409, {
            "mensaje": "Alerta de riesgo. Confirme con forzar=true para asignar.",
            "alertas": riesgos,
        })

    puestos = 0
    for jornada in dias:
        ya = (db.query(m.AsignacionPersonal)
              .filter_by(jornada_id=jornada.id, persona_id=persona.id).first())
        if ya:
            continue
        db.add(m.AsignacionPersonal(jornada_id=jornada.id,
                                    persona_id=persona.id,
                                    rol_id=datos.rol_id))
        puestos += 1

    db.flush()
    servicio = equipo.servicio
    programacion.evaluar(servicio)
    auditoria.registrar(db, usuario, servicio, "asignar personal",
                        f"{persona.nombre} como {rol.nombre if rol else 'sin rol'}"
                        f" · {equipo.alias}, {puestos} dia(s)"
                        + (" (forzado sobre alerta)" if riesgos else ""))
    db.commit()
    return {"resultado": "asignado", "persona": persona.nombre,
            "rol": rol.nombre if rol else None,
            "dias": puestos,
            "estatus_servicio": servicio.estatus.value,
            "faltantes_de_recursos": programacion.faltantes_de_recursos(servicio),
            "alertas_aceptadas": riesgos}


@router.post("/equipos/{equipo_id}/asignar-vehiculo",
             summary="Asignar una unidad a todos los dias del equipo")
def asignar_vehiculo_equipo(equipo_id: int, datos: s.AsignarVehiculoIn,
                            db: Session = Depends(get_db),
                            usuario: m.Usuario = Depends(
                                auth.requiere(m.Rol.CONSULTOR,
                                              m.Rol.DIRECTOR_OPERACIONES))):
    equipo = _equipo(db, equipo_id)
    vehiculo = db.get(m.Vehiculo, datos.vehiculo_id)
    if not vehiculo:
        raise HTTPException(404, f"No existe el vehiculo {datos.vehiculo_id}")
    dias = _dias_vivos(equipo)
    if not dias:
        raise HTTPException(409, "El equipo no tiene dias que cubrir")

    bloqueos, riesgos = [], []
    for jornada in dias:
        for hallazgo in disp.revisar_vehiculo(
                db, vehiculo.id, jornada.inicio_programado,
                jornada.fin_programado, jornada.modalidad.bloquea_dia_completo,
                excluir_jornada_id=jornada.id):
            destino = bloqueos if hallazgo.nivel == "bloqueo" else riesgos
            destino.append({**hallazgo.como_dict(),
                            "fecha": jornada.fecha.isoformat()})

    if bloqueos:
        raise HTTPException(409, {
            "mensaje": f"La unidad {vehiculo.placa} no esta disponible "
                       "todos los dias",
            "alertas": bloqueos,
        })
    if riesgos and not datos.forzar:
        raise HTTPException(409, {
            "mensaje": "Alerta de riesgo. Confirme con forzar=true para asignar.",
            "alertas": riesgos,
        })

    puestos = 0
    for jornada in dias:
        ya = (db.query(m.AsignacionVehiculo)
              .filter_by(jornada_id=jornada.id, vehiculo_id=vehiculo.id).first())
        if ya:
            continue
        db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                    vehiculo_id=vehiculo.id))
        puestos += 1

    db.flush()
    servicio = equipo.servicio
    programacion.evaluar(servicio)
    auditoria.registrar(db, usuario, servicio, "asignar vehiculo",
                        f"{vehiculo.placa} · {equipo.alias}, {puestos} dia(s)")
    db.commit()
    return {"resultado": "asignado", "vehiculo": vehiculo.placa,
            "dias": puestos,
            "estatus_servicio": servicio.estatus.value,
            "faltantes_de_recursos": programacion.faltantes_de_recursos(servicio),
            "alertas_aceptadas": riesgos}


@router.post("/equipos/{equipo_id}/vehiculo-rentado", status_code=201,
             summary="Dar de alta un auto subarrendado y asignarlo al equipo")
def vehiculo_rentado(equipo_id: int, datos: s.VehiculoRentadoIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(
                         auth.requiere(m.Rol.CONSULTOR,
                                       m.Rol.DIRECTOR_OPERACIONES))):
    """Cuando no hay la categoria que pide el cliente o la flota esta
    saturada, el auto se renta. El consultor lo captura en el mismo
    momento en que esta asignando recursos —no en el catalogo de flota,
    que es otra pantalla y otro dia— y queda asignado al equipo de una
    vez, con el sello de rentado y el servicio que lo pidio.
    """
    equipo = _equipo(db, equipo_id)
    servicio = equipo.servicio
    dias = _dias_vivos(equipo)
    if not dias:
        raise HTTPException(409, "El equipo no tiene dias que cubrir")

    placa = datos.placa.strip()

    # Si esa placa es de la casa, no hay nada que rentar: es una unidad
    # propia y se asigna por el camino normal.
    propia = (db.query(m.Vehiculo)
              .filter(m.Vehiculo.placa == placa,
                      m.Vehiculo.rentado.is_(False)).first())
    if propia:
        raise HTTPException(409, {
            "mensaje": f"La placa {placa} es de una unidad propia. "
                       "Asignela desde la lista de flota.",
            "vehiculo_id": propia.id,
        })

    # La misma renta capturada dos veces en el mismo servicio es un
    # tropiezo comun: se reusa el registro en vez de duplicar el auto.
    vehiculo = (db.query(m.Vehiculo)
                .filter(m.Vehiculo.placa == placa,
                        m.Vehiculo.rentado.is_(True),
                        m.Vehiculo.servicio_id == servicio.id).first())
    if vehiculo:
        if vehiculo.categoria_id != datos.categoria_id and not datos.forzar:
            raise HTTPException(409, {
                "mensaje": f"La placa {placa} ya esta en este servicio con "
                           "otra categoria. Confirme con forzar=true.",
            })
        vehiculo.categoria_id = datos.categoria_id
        vehiculo.color = datos.color
        vehiculo.marca_modelo = datos.marca_modelo
        vehiculo.modelo_anio = datos.modelo_anio
        vehiculo.costo_diario = datos.costo_diario
        vehiculo.arrendadora = datos.arrendadora
        vehiculo.arrendadora_telefono = datos.arrendadora_telefono
        vehiculo.motivo_renta = datos.motivo_renta
        vehiculo.activo = True
    else:
        vehiculo = m.Vehiculo(
            placa=placa,
            categoria_id=datos.categoria_id,
            # El auto se renta donde opera el equipo: en un proyecto que
            # va de Mexico a Monterrey, el de Beta se renta en Monterrey.
            plaza_id=datos.plaza_id or equipo.ciudad_id or servicio.plaza_id,
            color=datos.color,
            marca_modelo=datos.marca_modelo,
            modelo_anio=datos.modelo_anio,
            costo_diario=datos.costo_diario,
            rentado=True,
            servicio_id=servicio.id,
            arrendadora=datos.arrendadora,
            arrendadora_telefono=datos.arrendadora_telefono,
            motivo_renta=datos.motivo_renta,
            # Escrito aparte del enlace: el servicio se puede borrar y la
            # renta sigue corriendo con la arrendadora.
            renta_folio=servicio.folio,
            activo=True)
        db.add(vehiculo)
    db.flush()

    # Un auto recien rentado no puede chocar con nada —nacio para este
    # servicio— pero si se recaptura una placa que ya trae dias en otro
    # equipo del mismo servicio, el empalme es real y hay que verlo.
    bloqueos = []
    for jornada in dias:
        for hallazgo in disp.revisar_vehiculo(
                db, vehiculo.id, jornada.inicio_programado,
                jornada.fin_programado, jornada.modalidad.bloquea_dia_completo,
                excluir_jornada_id=jornada.id):
            if hallazgo.nivel == "bloqueo":
                bloqueos.append({**hallazgo.como_dict(),
                                 "fecha": jornada.fecha.isoformat()})
    if bloqueos:
        db.rollback()
        raise HTTPException(409, {
            "mensaje": f"La unidad {placa} ya esta comprometida en el "
                       "servicio esos dias",
            "alertas": bloqueos,
        })

    puestos = 0
    for jornada in dias:
        ya = (db.query(m.AsignacionVehiculo)
              .filter_by(jornada_id=jornada.id, vehiculo_id=vehiculo.id).first())
        if ya:
            continue
        db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                    vehiculo_id=vehiculo.id))
        puestos += 1

    db.flush()
    programacion.evaluar(servicio)
    auditoria.registrar(
        db, usuario, servicio, "alta de auto rentado",
        f"{placa} · {datos.arrendadora} · {datos.motivo_renta.value} · "
        f"{equipo.alias}, {puestos} dia(s)")
    db.commit()
    return {"resultado": "asignado", "vehiculo_id": vehiculo.id,
            "vehiculo": vehiculo.placa, "rentado": True,
            "arrendadora": vehiculo.arrendadora, "dias": puestos,
            "estatus_servicio": servicio.estatus.value,
            "faltantes_de_recursos": programacion.faltantes_de_recursos(servicio)}


def _devolver_renta(vehiculo: m.Vehiculo, folio: str | None = None) -> None:
    """Deja de ofrecerse y le queda a finanzas cancelar la renta.

    No se borra ni se da por resuelto: un auto que se devuelve solo es un
    auto que se sigue cobrando. Alguien tiene que hablarle a la
    arrendadora, y hasta que lo haga, esto es lo que se lo recuerda.
    """
    vehiculo.activo = False
    vehiculo.renta_por_cancelar = True
    if folio and not vehiculo.renta_folio:
        vehiculo.renta_folio = folio


# ------------------------------------------------------- quitar recursos

# Mientras no haya salido dinero, un recurso mal puesto se quita y ya.
# Despues no: quien recibio viaticos tiene que comprobarlos, y sacarlo de
# la lista dejaria ese dinero sin dueno. Ese caso es un reemplazo por
# contingencia, que si sabe que hacer con lo que ya se deposito.
DINERO_AFUERA = (m.EstatusViatico.TRANSFERIDO, m.EstatusViatico.EN_COMPROBACION,
                 m.EstatusViatico.CERRADO)


@router.delete("/equipos/{equipo_id}/personal/{persona_id}",
               summary="Quitar a una persona del equipo")
def quitar_personal(equipo_id: int, persona_id: int,
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(
                        auth.requiere(m.Rol.CONSULTOR,
                                      m.Rol.DIRECTOR_OPERACIONES))):
    """Se va de todos los dias del equipo, como se asigno."""
    equipo = _equipo(db, equipo_id)
    ids = [j.id for j in equipo.jornadas]
    asignaciones = (db.query(m.AsignacionPersonal)
                    .filter(m.AsignacionPersonal.persona_id == persona_id,
                            m.AsignacionPersonal.jornada_id.in_(ids))
                    .all()) if ids else []
    if not asignaciones:
        raise HTTPException(404, "Esa persona no esta asignada al equipo")

    viaticos = (db.query(m.AsignacionViatico)
                .filter(m.AsignacionViatico.persona_id == persona_id,
                        m.AsignacionViatico.jornada_id.in_(ids))
                .all())
    salio = [v for v in viaticos if v.estatus in DINERO_AFUERA]
    if salio:
        raise HTTPException(409, {
            "mensaje": "Esa persona ya recibio viaticos. Para sacarla del "
                       "servicio use un reemplazo por contingencia, que "
                       "resuelve que pasa con ese dinero.",
            "estatus": salio[0].estatus.value,
        })

    persona = db.get(m.Persona, persona_id)
    # El dinero que nunca salio se va con ella, sin dejar rastro que
    # cuadrar despues.
    for viatico in viaticos:
        for solicitud in db.query(m.SolicitudTransferencia).filter_by(
                asignacion_id=viatico.id).all():
            db.delete(solicitud)
        for concepto in list(viatico.conceptos):
            db.delete(concepto)
        db.delete(viatico)
    for asignacion in asignaciones:
        db.delete(asignacion)

    db.flush()
    servicio = equipo.servicio
    programacion.evaluar(servicio)
    auditoria.registrar(db, usuario, servicio, "quitar personal",
                        f"{persona.nombre if persona else persona_id} · "
                        f"{equipo.alias}, {len(asignaciones)} dia(s)")
    db.commit()
    return {"resultado": "quitado", "dias": len(asignaciones),
            "estatus_servicio": servicio.estatus.value,
            "faltantes_de_recursos": programacion.faltantes_de_recursos(servicio)}


@router.delete("/equipos/{equipo_id}/vehiculos/{vehiculo_id}",
               summary="Quitar una unidad del equipo")
def quitar_vehiculo(equipo_id: int, vehiculo_id: int,
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(
                        auth.requiere(m.Rol.CONSULTOR,
                                      m.Rol.DIRECTOR_OPERACIONES))):
    equipo = _equipo(db, equipo_id)
    ids = [j.id for j in equipo.jornadas]
    asignaciones = (db.query(m.AsignacionVehiculo)
                    .filter(m.AsignacionVehiculo.vehiculo_id == vehiculo_id,
                            m.AsignacionVehiculo.jornada_id.in_(ids))
                    .all()) if ids else []
    if not asignaciones:
        raise HTTPException(404, "Esa unidad no esta asignada al equipo")

    # Quien iba a bordo de ella se queda sin unidad, no colgado de una
    # que ya no va.
    (db.query(m.AsignacionPersonal)
     .filter(m.AsignacionPersonal.vehiculo_id == vehiculo_id,
             m.AsignacionPersonal.jornada_id.in_(ids))
     .update({"vehiculo_id": None}, synchronize_session=False))

    for asignacion in asignaciones:
        db.delete(asignacion)
    db.flush()

    vehiculo = db.get(m.Vehiculo, vehiculo_id)
    # El auto de renta que se queda sin dias no se queda en la lista: se
    # pidio para este servicio y si ya no se ocupa, se devuelve.
    if vehiculo and vehiculo.rentado and vehiculo.servicio_id == equipo.servicio_id:
        sigue = (db.query(m.AsignacionVehiculo)
                 .filter_by(vehiculo_id=vehiculo_id).count())
        if not sigue:
            _devolver_renta(vehiculo, equipo.servicio.folio)

    servicio = equipo.servicio
    programacion.evaluar(servicio)
    auditoria.registrar(db, usuario, servicio, "quitar unidad",
                        f"{vehiculo.placa if vehiculo else vehiculo_id} · "
                        f"{equipo.alias}, {len(asignaciones)} dia(s)")
    db.commit()
    return {"resultado": "quitada", "dias": len(asignaciones),
            "estatus_servicio": servicio.estatus.value,
            "faltantes_de_recursos": programacion.faltantes_de_recursos(servicio)}


@router.patch("/equipos/{equipo_id}/personal/{persona_id}/unidad",
              summary="En que unidad va esa persona, todos los dias")
def abordo_equipo(equipo_id: int, persona_id: int, datos: s.AbordoIn,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(
                      auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES))):
    """Quien aborda que unidad tampoco cambia de un dia a otro."""
    equipo = _equipo(db, equipo_id)
    asignaciones = (db.query(m.AsignacionPersonal)
                    .filter(m.AsignacionPersonal.persona_id == persona_id,
                            m.AsignacionPersonal.jornada_id.in_(
                                [j.id for j in equipo.jornadas]))
                    .all())
    if not asignaciones:
        raise HTTPException(404, "Esa persona no esta asignada al equipo")

    if datos.vehiculo_id is not None:
        de_este_equipo = (db.query(m.AsignacionVehiculo)
                          .filter(m.AsignacionVehiculo.vehiculo_id == datos.vehiculo_id,
                                  m.AsignacionVehiculo.jornada_id.in_(
                                      [j.id for j in equipo.jornadas]))
                          .first())
        if not de_este_equipo:
            raise HTTPException(400, {
                "mensaje": "Esa unidad no esta asignada al equipo",
                "vehiculo_id": datos.vehiculo_id,
            })

    for asignacion in asignaciones:
        asignacion.vehiculo_id = datos.vehiculo_id

    unidad = db.get(m.Vehiculo, datos.vehiculo_id) if datos.vehiculo_id else None
    auditoria.registrar(db, usuario, equipo.servicio, "abordo",
                        f"{asignaciones[0].persona.nombre} "
                        + (f"va en {unidad.placa}" if unidad else "sin unidad")
                        + f" · {equipo.alias}")
    db.commit()
    return {"resultado": "abordo actualizado", "dias": len(asignaciones),
            "vehiculo_id": datos.vehiculo_id,
            "placa": unidad.placa if unidad else None}


@router.get("/equipos/{equipo_id}/asignaciones",
            summary="Quien y que trae el equipo, y en que dias")
def asignaciones_equipo(equipo_id: int, db: Session = Depends(get_db),
                        _=Depends(auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL,
                                                m.Rol.DIRECTOR_OPERACIONES))):
    """Lo normal es que el equipo sea el mismo todos los dias. Cuando no
    —un cambio por contingencia a media semana— se dice en cuantos dias
    esta cada quien, para que la diferencia se vea."""
    equipo = _equipo(db, equipo_id)
    dias = _dias_vivos(equipo)
    total = len(dias)
    ids = [j.id for j in dias]

    gente: dict = {}
    for a in (db.query(m.AsignacionPersonal)
              .filter(m.AsignacionPersonal.jornada_id.in_(ids)).all()
              if ids else []):
        ficha = gente.setdefault(a.persona_id, {
            "persona_id": a.persona_id, "nombre": a.persona.nombre,
            "puesto": a.rol.nombre if a.rol else None,
            "telefono": a.persona.telefono,
            "foto": a.persona.foto_url,
            "ciudad": a.persona.plaza.nombre if a.persona.plaza else None,
            "vehiculo_id": a.vehiculo_id,
            "abordo": a.vehiculo.placa if a.vehiculo else None,
            "dias": 0})
        ficha["dias"] += 1

    unidades: dict = {}
    for a in (db.query(m.AsignacionVehiculo)
              .filter(m.AsignacionVehiculo.jornada_id.in_(ids)).all()
              if ids else []):
        ficha = unidades.setdefault(a.vehiculo_id, {
            "vehiculo_id": a.vehiculo_id, "placa": a.vehiculo.placa,
            "unidad": a.vehiculo.categoria.nombre,
            "blindada": a.vehiculo.categoria.blindado,
            "color": a.vehiculo.color, "anio": a.vehiculo.modelo_anio,
            "marca_modelo": a.vehiculo.marca_modelo,
            "rentado": a.vehiculo.rentado,
            "arrendadora": a.vehiculo.arrendadora,
            "arrendadora_telefono": a.vehiculo.arrendadora_telefono,
            "foto": a.vehiculo.foto_url, "dias": 0})
        ficha["dias"] += 1

    return {"equipo": equipo.alias, "dias": total,
            "personal": sorted(gente.values(), key=lambda x: -x["dias"]),
            "vehiculos": sorted(unidades.values(), key=lambda x: -x["dias"])}


@router.get("/jornadas/{jornada_id}/asignaciones",
            summary="Ver quien y que esta asignado a la jornada")
def ver_asignaciones(jornada_id: int, db: Session = Depends(get_db),
                     _=Depends(auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL, m.Rol.DIRECTOR_OPERACIONES))):
    jornada = _obtener_jornada(db, jornada_id)
    return {
        "jornada_id": jornada.id,
        "equipo": jornada.equipo.alias,
        "fecha": jornada.fecha.isoformat(),
        "modalidad": jornada.modalidad.codigo.value,
        # Lo mismo que sale en el task sheet, en el mismo orden: puesto,
        # nombre y telefono. Quien arma el servicio ve lo que va a recibir
        # el cliente.
        "personal": [{"persona_id": a.persona_id, "nombre": a.persona.nombre,
                      "puesto": a.rol.nombre if a.rol else None,
                      "telefono": a.persona.telefono,
                      "foto": a.persona.foto_url,
                      "ciudad": a.persona.plaza.nombre if a.persona.plaza else None,
                      "vehiculo_id": a.vehiculo_id,
                      "abordo": a.vehiculo.placa if a.vehiculo else None,
                      "confirmado": a.confirmado} for a in jornada.personal],
        "vehiculos": [{"vehiculo_id": a.vehiculo_id, "placa": a.vehiculo.placa,
                       "unidad": a.vehiculo.categoria.nombre,
                       "color": a.vehiculo.color,
                       "anio": a.vehiculo.modelo_anio,
                       "marca_modelo": a.vehiculo.marca_modelo,
                       "rentado": a.vehiculo.rentado,
                       "arrendadora": a.vehiculo.arrendadora,
                       "blindada": a.vehiculo.categoria.blindado,
                       "foto": a.vehiculo.foto_url}
                      for a in jornada.vehiculos],
    }


@router.get("/{servicio_id}/auditoria",
            summary="Quien ha trabajado este servicio")
def auditoria_servicio(servicio_id: int, db: Session = Depends(get_db),
                       _=Depends(auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL,
                                               m.Rol.DIRECTOR_OPERACIONES))):
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    registros = (db.query(m.RegistroAccion)
                 .filter_by(servicio_id=servicio_id)
                 .order_by(m.RegistroAccion.id).all())
    titular = db.get(m.Persona, servicio.consultor_id) if servicio.consultor_id else None

    return {
        "servicio": servicio.folio,
        "consultor_titular": titular.nombre if titular else "sin asignar",
        "movimientos": [{
            "cuando": r.creado_en.isoformat(),
            "quien": r.persona.nombre,
            "rol": r.rol.value,
            "accion": r.accion,
            "detalle": r.detalle,
            "en_cobertura": r.en_cobertura,
        } for r in registros],
        "movimientos_en_cobertura": sum(1 for r in registros if r.en_cobertura),
    }
# ---------------------------------------------------------------- eliminar

# Un servicio que ya arranco no se borra: se cancela.
ANTES_DE_ARRANCAR = {m.EstatusServicio.BORRADOR, m.EstatusServicio.COTIZADO,
                     m.EstatusServicio.AUTORIZADO, m.EstatusServicio.PLANEADO,
                     m.EstatusServicio.ASIGNADO}


# Viaticos que todavia no son dinero en manos de nadie: asignados es
# papel del consultor, solicitados es una instruccion que finanzas puede
# detener, y los cancelados o devueltos ya se resolvieron.
VIATICOS_SIN_DEPOSITAR = {m.EstatusViatico.ASIGNADO, m.EstatusViatico.SOLICITADO,
                          m.EstatusViatico.CANCELADO, m.EstatusViatico.DEVUELTO}


def _viaticos_de(db: Session, jornada_ids: list[int]) -> list:
    if not jornada_ids:
        return []
    return (db.query(m.AsignacionViatico)
            .filter(m.AsignacionViatico.jornada_id.in_(jornada_ids)).all())


def _movimientos(db: Session, jornada_ids: list[int]) -> list[str]:
    """Que le impide a estos dias desaparecer sin dejar hueco."""
    if not jornada_ids:
        return []
    razones = []
    depositados = [v for v in _viaticos_de(db, jornada_ids)
                   if v.estatus not in VIATICOS_SIN_DEPOSITAR]
    if depositados:
        razones.append(f"ya tiene {len(depositados)} viatico(s) depositados")
    if db.query(m.Hito).filter(m.Hito.jornada_id.in_(jornada_ids)).count():
        razones.append("ya tiene hitos marcados desde la app")
    if db.query(m.Jornada).filter(
            m.Jornada.id.in_(jornada_ids),
            m.Jornada.estatus.in_([m.EstatusJornada.EN_CURSO,
                                   m.EstatusJornada.TERMINADA])).count():
        razones.append("tiene dias que ya arrancaron")
    if db.query(m.ReemplazoRecurso).filter(
            m.ReemplazoRecurso.desde_jornada_id.in_(jornada_ids)).count():
        razones.append("tiene cambios de recurso por contingencia")
    return razones


def _limpiar_jornadas(db: Session, jornada_ids: list[int]) -> int:
    """Lo que cuelga de un dia que todavia no se movio.

    Devuelve cuantas instrucciones de transferencia iban en camino: son
    las que alguien tiene que detener en finanzas, y por eso se dicen en
    voz alta en vez de desaparecer con el servicio."""
    if not jornada_ids:
        return 0

    # Los viaticos que no se depositaron se van con el servicio. Primero
    # lo que cuelga de ellos, que si no la base no los suelta.
    viaticos = [v.id for v in _viaticos_de(db, jornada_ids)]
    en_camino = 0
    if viaticos:
        en_camino = (db.query(m.SolicitudTransferencia)
                     .filter(m.SolicitudTransferencia.asignacion_id.in_(viaticos),
                             m.SolicitudTransferencia.estatus.in_(
                                 [m.EstatusTransferencia.PENDIENTE,
                                  m.EstatusTransferencia.ENVIADA]))
                     .count())
        for tabla in (m.ConceptoAsignado, m.Comprobante,
                      m.SolicitudTransferencia):
            db.query(tabla).filter(tabla.asignacion_id.in_(viaticos)).delete(
                synchronize_session=False)
        db.query(m.AsignacionViatico).filter(
            m.AsignacionViatico.id.in_(viaticos)).delete(
                synchronize_session=False)

    for tabla in (m.AsignacionPersonal, m.AsignacionVehiculo, m.AgendaJornada,
                  m.ParadaAgenda, m.Alerta):
        db.query(tabla).filter(tabla.jornada_id.in_(jornada_ids)).delete(
            synchronize_session=False)
    # Lo que apunta al dia sin depender de el se queda huerfano a
    # proposito: una incidencia de una persona o un renglon de nomina no
    # se borra porque el servicio ya no exista.
    for tabla, campo in ((m.RegistroAccion, m.RegistroAccion.jornada_id),
                         (m.Notificacion, m.Notificacion.jornada_id),
                         (m.AlertaIncidencia, m.AlertaIncidencia.jornada_id),
                         (m.Incidencia, m.Incidencia.jornada_id),
                         (m.ConceptoNomina, m.ConceptoNomina.jornada_id)):
        db.query(tabla).filter(campo.in_(jornada_ids)).update(
            {campo: None}, synchronize_session=False)
    return en_camino


@router.delete("/equipos/{equipo_id}", summary="Eliminar un equipo del servicio")
def eliminar_equipo(equipo_id: int, datos: s.EliminarIn | None = None,
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(auth.puede("servicios.alta"))):
    """El equipo que se armo de mas, o el que el cliente echo para atras.
    Con viaticos o con dias andando ya no: eso se cancela."""
    equipo = db.get(m.Equipo, equipo_id)
    if not equipo:
        raise HTTPException(404, f"No existe el equipo {equipo_id}")
    servicio = equipo.servicio

    if len(servicio.equipos) == 1:
        raise HTTPException(409, {
            "mensaje": "Es el unico equipo del servicio",
            "que_hacer": "Elimina el servicio completo",
        })
    if servicio.estatus not in ANTES_DE_ARRANCAR:
        raise HTTPException(409, {
            "mensaje": f"El servicio esta {servicio.estatus.value}",
            "que_hacer": "Un servicio que ya arranco se cancela, no se borra",
        })

    jornada_ids = [j.id for j in equipo.jornadas]
    razones = _movimientos(db, jornada_ids)
    if razones:
        raise HTTPException(409, {
            "mensaje": f"El equipo {equipo.alias} " + " y ".join(razones),
            "que_hacer": "Cancela lo que ya se movio antes de borrarlo",
        })

    alias = equipo.alias
    db.query(m.TaskSheet).filter_by(equipo_id=equipo.id).delete(
        synchronize_session=False)
    en_camino = _limpiar_jornadas(db, jornada_ids)
    db.query(m.Jornada).filter_by(equipo_id=equipo.id).delete(
        synchronize_session=False)
    # Los dias ya se fueron por consulta directa: si no se le avisa, el
    # ORM intenta borrarlos otra vez al soltar el equipo.
    db.expire(equipo, ["jornadas"])
    db.delete(equipo)
    db.flush()
    # Y la lista de equipos del servicio todavia trae al que se fue.
    db.expire(servicio, ["equipos"])

    # Los alias son por posicion: si se fue Beta, Gamma pasa a ser Beta.
    for posicion, quedan in enumerate(
            sorted(servicio.equipos, key=lambda e: e.id)):
        quedan.alias = alias_de_equipo(posicion)

    # El auto de renta que se queda sin un solo dia ya no se ocupa: se
    # devuelve. Se da de baja y deja de ofrecerse, pero no se borra
    # porque su costo ya entro a la cuenta del servicio.
    for vehiculo in (db.query(m.Vehiculo)
                     .filter_by(servicio_id=servicio.id, rentado=True,
                                activo=True).all()):
        sigue = (db.query(m.AsignacionVehiculo)
                 .filter_by(vehiculo_id=vehiculo.id).count())
        if not sigue:
            _devolver_renta(vehiculo, servicio.folio)

    programacion.evaluar(servicio)
    auditoria.registrar(db, usuario, servicio, "eliminar equipo",
                        f"{alias}: {len(jornada_ids)} dia(s)"
                        + (f" · {datos.motivo}" if datos and datos.motivo else ""))
    db.commit()
    return {"resultado": "equipo eliminado", "equipo": alias,
            "equipos_restantes": [e.alias for e in servicio.equipos],
            "estatus_servicio": servicio.estatus.value,
            "transferencias_por_detener": en_camino,
            "nota": ("Avisa a finanzas: habia instrucciones de transferencia "
                     "en camino" if en_camino else None)}


@router.delete("/{servicio_id}", summary="Eliminar un servicio")
def eliminar_servicio(servicio_id: int, datos: s.EliminarIn | None = None,
                      db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(auth.puede("servicios.alta"))):
    """La captura equivocada o el servicio que se echo para atras antes de
    arrancar. Del servicio solo queda su renglon en la bitacora de
    eliminados: que era, quien lo quito y por que."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    if servicio.estatus not in ANTES_DE_ARRANCAR:
        raise HTTPException(409, {
            "mensaje": f"El servicio esta {servicio.estatus.value}",
            "que_hacer": "Un servicio que ya arranco se cancela, no se borra",
        })

    jornada_ids = [j.id for e in servicio.equipos for j in e.jornadas]
    razones = _movimientos(db, jornada_ids)
    if razones:
        raise HTTPException(409, {
            "mensaje": "El servicio " + " y ".join(razones),
            "que_hacer": "Cancelalo en vez de borrarlo: ya hay rastro que "
                         "conservar",
        })

    folio = servicio.folio
    dias = len(jornada_ids)
    equipos = len(servicio.equipos)

    en_camino = _limpiar_jornadas(db, jornada_ids)
    # Las respuestas cuelgan de la encuesta: primero ellas.
    encuestas = [e.id for e in db.query(m.Encuesta).filter_by(
        servicio_id=servicio.id).all()]
    if encuestas:
        db.query(m.RespuestaEncuesta).filter(
            m.RespuestaEncuesta.encuesta_id.in_(encuestas)).delete(
                synchronize_session=False)
    for tabla in (m.TaskSheet, m.Notificacion, m.RegistroAccion, m.Hospedaje,
                  m.Encuesta, m.AlertaIncidencia, m.ReemplazoRecurso):
        db.query(tabla).filter_by(servicio_id=servicio.id).delete(
            synchronize_session=False)
    # La incidencia es de la persona, no del servicio: pierde el enlace.
    db.query(m.Incidencia).filter_by(servicio_id=servicio.id).update(
        {"servicio_id": None}, synchronize_session=False)
    for equipo in list(servicio.equipos):
        db.query(m.Jornada).filter_by(equipo_id=equipo.id).delete(
            synchronize_session=False)
        db.expire(equipo, ["jornadas"])
        db.delete(equipo)
    db.expire(servicio, ["equipos"])
    # El auto de renta NO se va con el servicio. El servicio desaparece de
    # la base, pero el contrato con la arrendadora sigue vivo y alguien
    # tiene que cancelarlo: borrarlo aqui seria dejar de pagar un auto
    # que se sigue cobrando. Se suelta del servicio —que ya no existe— y
    # queda en la bandeja de finanzas con el folio que lo pidio.
    rentados = (db.query(m.Vehiculo)
                .filter_by(servicio_id=servicio.id, rentado=True).all())
    for vehiculo in rentados:
        _devolver_renta(vehiculo, folio)
        vehiculo.servicio_id = None
    # Un servicio que nacio de otro se queda sin padre, no se borra en cadena.
    db.query(m.Servicio).filter_by(servicio_origen_id=servicio.id).update(
        {"servicio_origen_id": None}, synchronize_session=False)
    db.flush()

    # El rastro vive fuera del servicio, porque el servicio deja de existir.
    db.add(m.ServicioEliminado(
        folio=folio,
        cliente=servicio.cliente.nombre if servicio.cliente else None,
        resumen=f"{equipos} equipo(s), {dias} dia(s), estatus "
                f"{servicio.estatus.value}",
        motivo=(datos.motivo if datos else None),
        eliminado_por_id=usuario.persona_id))

    db.delete(servicio)
    db.commit()
    return {"resultado": "servicio eliminado", "folio": folio,
            "equipos": equipos, "dias": dias,
            "transferencias_por_detener": en_camino,
            "nota": ("Avisa a finanzas: habia instrucciones de transferencia "
                     "en camino" if en_camino else None)}
# ---------------------------------------------------------------- cancelar

# Lo que ya no se puede cancelar: o esta cancelado, o ya se cerro.
YA_NO_SE_CANCELA = {m.EstatusServicio.CANCELADO, m.EstatusServicio.CERRADO}

# Viaticos que todavia no salieron de la caja.
VIATICOS_SIN_SALIR = {m.EstatusViatico.ASIGNADO, m.EstatusViatico.SOLICITADO}


@router.post("/{servicio_id}/confirmar-asignacion",
             summary="El consultor da por cerrada la asignacion")
def confirmar_asignacion(servicio_id: int, db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(
                             auth.puede("servicios.alta"))):
    """Que haya gente y unidad en todos los dias no quiere decir que el
    consultor haya terminado: puede estar probando quien cabe. Esta es su
    firma, y es lo que le dice a la central que ya puede trabajar sobre
    este servicio."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    if servicio.estatus in (m.EstatusServicio.CANCELADO,
                            m.EstatusServicio.CERRADO):
        raise HTTPException(409, {
            "mensaje": f"El servicio esta {servicio.estatus.value}"})

    faltan = programacion.faltantes_de_recursos(servicio)
    if faltan:
        raise HTTPException(409, {
            "mensaje": "Todavia hay dias sin equipo o sin unidad",
            "faltantes": faltan,
        })

    # La misma revision que hace el TS: de nada sirve confirmar un
    # servicio al que le falta el pin de un dia, porque la hoja que se va
    # a mandar saldria coja.
    from app import tasksheet as hojas
    pendientes = []
    for equipo in servicio.equipos:
        pendientes += hojas.armar(db, equipo.id)["faltantes"]
    if pendientes:
        raise HTTPException(409, {
            "mensaje": "El TS todavia no esta completo",
            "faltantes": pendientes,
        })

    servicio.asignacion_confirmada_en = datetime.now(timezone.utc)
    servicio.asignacion_confirmada_por_id = usuario.persona_id

    # Se guarda una copia congelada por equipo, para el expediente: que
    # quede como estaba el dia que se confirmo. Lo que se manda por
    # correo sale de lo ultimo capturado, no de esta copia.
    versiones = []
    for equipo in servicio.equipos:
        ficha = hojas.publicar(db, equipo.id, usuario.persona_id,
                               motivo="confirmacion de la asignacion",
                               avisar=False)
        versiones.append({"equipo": equipo.alias, "version": ficha.version})

    auditoria.registrar(db, usuario, servicio, "confirmar asignacion",
                        f"{len(servicio.equipos)} equipo(s)")
    db.commit()
    return {"resultado": "asignacion confirmada", "folio": servicio.folio,
            "confirmada_en": servicio.asignacion_confirmada_en.isoformat(),
            "estatus": servicio.estatus.value,
            "versiones": versiones,
            "sigue": "El TS queda liberado: descargalo y mandalo por correo"}


@router.post("/{servicio_id}/cancelar", summary="Cancelar un servicio")
def cancelar_servicio(servicio_id: int, datos: s.CancelarIn,
                      db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(auth.puede("servicios.alta"))):
    """Cuando ya no se puede borrar. El servicio se queda con todo su
    rastro, sus dias se cancelan y la gente y las unidades quedan libres
    para otros servicios ese mismo dia."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    if servicio.estatus in YA_NO_SE_CANCELA:
        raise HTTPException(409, {
            "mensaje": f"El servicio ya esta {servicio.estatus.value}",
        })

    jornadas = [j for e in servicio.equipos for j in e.jornadas]
    dias_cancelados = 0
    for jornada in jornadas:
        # Un dia que ya se trabajo no se borra del historial: se queda
        # terminado, porque esas horas se pagan.
        if jornada.estatus != m.EstatusJornada.TERMINADA:
            jornada.estatus = m.EstatusJornada.CANCELADA
            dias_cancelados += 1

    # El dinero: lo que no ha salido se cancela; lo que ya salio se
    # devuelve, y mientras no vuelva sigue siendo responsabilidad de
    # alguien. Por eso se enlista en vez de darlo por cerrado.
    por_devolver = []
    viaticos = (db.query(m.AsignacionViatico)
                .filter(m.AsignacionViatico.jornada_id.in_([j.id for j in jornadas]))
                .all()) if jornadas else []
    for viatico in viaticos:
        if viatico.estatus in VIATICOS_SIN_SALIR:
            viatico.estatus = m.EstatusViatico.CANCELADO
        elif viatico.estatus not in (m.EstatusViatico.CERRADO,
                                     m.EstatusViatico.DEVUELTO,
                                     m.EstatusViatico.CANCELADO):
            persona = db.get(m.Persona, viatico.persona_id)
            por_devolver.append({
                "persona": persona.nombre if persona else viatico.persona_id,
                "monto": float(viatico.monto_total),
                "moneda": viatico.moneda.value,
                "estatus": viatico.estatus.value,
            })

    # El auto de renta se devuelve: el servicio no va, y dejarlo activo
    # lo dejaria apareciendo en la lista de un servicio que ya no existe.
    # Se da de baja, no se borra: el costo ya corrio y hay que verlo.
    rentados = (db.query(m.Vehiculo)
                .filter_by(servicio_id=servicio.id, rentado=True, activo=True)
                .all())
    for vehiculo in rentados:
        _devolver_renta(vehiculo, servicio.folio)

    antes = servicio.estatus.value
    servicio.estatus = m.EstatusServicio.CANCELADO
    auditoria.registrar(db, usuario, servicio, "cancelar servicio",
                        f"estaba {antes} · {datos.motivo}")
    db.commit()

    return {"resultado": "servicio cancelado", "folio": servicio.folio,
            "estatus_anterior": antes,
            "dias_cancelados": dias_cancelados,
            "autos_rentados_por_devolver": [v.placa for v in rentados],
            "viaticos_por_devolver": por_devolver,
            "nota": ("Hay viaticos entregados que tienen que regresar"
                     if por_devolver else
                     "La gente y las unidades quedan libres para ese dia")}


@router.get("/{servicio_id}/revisiones",
            summary="Como se recibio y como se entrego cada unidad")
def revisiones_del_servicio(servicio_id: int, db: Session = Depends(get_db),
                            _=Depends(auth.usuario_actual)):
    """Lo que la consola necesita para resolver un reclamo de dano.

    De un lado las fotos de cuando la unidad cambio de manos hacia el
    equipo, del otro las de cuando volvio, con su kilometraje y su
    firma. Esa comparacion es toda la razon por la que esto existe.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    filas = (db.query(m.RevisionUnidad)
             .filter_by(servicio_id=servicio.id)
             .order_by(m.RevisionUnidad.momento).all())

    por_unidad: dict = {}
    for r in filas:
        tipo = r.tipo.value if hasattr(r.tipo, "value") else r.tipo
        fila = por_unidad.setdefault(r.vehiculo_id, {
            "vehiculo_id": r.vehiculo_id,
            "placa": r.vehiculo.placa if r.vehiculo else None,
            "recibe": None, "entrega": None,
        })
        fila[tipo] = {
            "revision_id": r.id,
            "persona": r.persona.nombre if r.persona else None,
            "momento": r.momento.isoformat(),
            "kilometraje": r.kilometraje,
            "combustible_octavos": r.combustible_octavos,
            "nota": r.nota,
            "tiene_firma": bool(r.firma),
            "fotos": [{"angulo": (f.angulo.value if hasattr(f.angulo, "value")
                                  else f.angulo),
                       "imagen": f.imagen, "nota": f.nota}
                      for f in r.fotos],
        }

    for fila in por_unidad.values():
        entrada, salida = fila["recibe"], fila["entrega"]
        # El kilometraje del servicio: el numero que nadie apunta y del
        # que despues todos se acuerdan distinto.
        if (entrada and salida and entrada["kilometraje"] is not None
                and salida["kilometraje"] is not None):
            fila["kilometros"] = salida["kilometraje"] - entrada["kilometraje"]
        fila["completa"] = bool(entrada and salida)

    return {"servicio_id": servicio.id, "folio": servicio.folio,
            "unidades": sorted(por_unidad.values(),
                               key=lambda x: x["placa"] or "")}

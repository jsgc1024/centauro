"""Task sheet del servicio: agenda, hospedaje y la ficha que ve el equipo
y se comparte con el cliente."""
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import auditoria, auth, imagenes
from app import implantado
from app import hoja_implantado as hoja_imp
from app import hoja_implantado_html as hoja_html
from app import models as m
from app import schemas as s
from app import tasksheet as motor
from app.textos import IDIOMAS
from app import tasksheet_html
from app.db import get_db

router = APIRouter(tags=["Task sheet"])

ARMAR = auth.puede("tasksheet.armar")
PUBLICAR = auth.puede("tasksheet.publicar")
LECTURA = auth.puede("tasksheet.ver")


def _servicio(db: Session, servicio_id: int) -> m.Servicio:
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    return servicio


# ---------------------------------------------------------------- agenda

@router.put("/operacion/jornadas/{jornada_id}/agenda",
            summary="Cargar la agenda del dia")
def cargar_agenda(jornada_id: int, datos: s.AgendaIn,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(ARMAR)):
    """La carga el consultor o el agente de la central, segun la modalidad."""
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")

    agenda = db.query(m.AgendaJornada).filter_by(jornada_id=jornada_id).first()
    if agenda:
        for campo, valor in datos.model_dump(exclude_unset=True).items():
            setattr(agenda, campo, valor)
    else:
        agenda = m.AgendaJornada(jornada_id=jornada_id,
                                 cargada_por_id=usuario.persona_id,
                                 **datos.model_dump())
        db.add(agenda)

    auditoria.registrar(db, usuario, jornada.equipo.servicio, "cargar agenda",
                        datos.resumen, jornada_id=jornada_id)
    db.commit()
    return {"resultado": "agenda guardada", "jornada_id": jornada_id}


# ---------------------------------------------------------------- hospedaje

@router.post("/hospedajes", status_code=201,
             summary="Registrar donde se hospeda el ejecutivo")
def crear_hospedaje(datos: s.HospedajeIn, db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(ARMAR)):
    """Uno por equipo. Volver a mandarlo corrige el que ya hay en vez de
    agregar otro: dos hoteles en la hoja dejan la duda de a cual llegar,
    que es justo lo que la hoja tiene que resolver."""
    if not datos.equipo_id and not datos.servicio_id:
        raise HTTPException(400, "Falta el equipo")
    if not datos.hotel_id and not datos.nombre_libre:
        raise HTTPException(400, "Indica el hotel del catalogo o captura su nombre")

    if datos.equipo_id:
        equipo = _equipo(db, datos.equipo_id)
    else:
        # Un servicio de un solo equipo no obliga a decir cual.
        servicio = _servicio(db, datos.servicio_id)
        equipo = _equipo_unico(db, servicio.id)
    servicio = equipo.servicio

    campos = datos.model_dump(exclude={"servicio_id", "equipo_id",
                                       "hotel_lat", "hotel_lon"})

    # Un hotel capturado a mano entra al catalogo de la ciudad del
    # equipo. Es lo que hace que el catalogo crezca con la operacion en
    # vez de llenarse de antemano: la segunda vez que ese ejecutivo va a
    # Monterrey, su hotel ya esta en la lista. Y si nadie lo vuelve a
    # ocupar en tres meses, sale solo.
    if not campos.get("hotel_id") and campos.get("nombre_libre"):
        hotel = (db.query(m.Hotel)
                 .filter(m.Hotel.pais_id == servicio.pais_id,
                         m.Hotel.nombre == campos["nombre_libre"])
                 .first())
        if not hotel:
            hotel = m.Hotel(pais_id=servicio.pais_id, nombre=campos["nombre_libre"])
            db.add(hotel)
        hotel.activo = True
        hotel.plaza_id = hotel.plaza_id or equipo.ciudad_id
        # Lo que Google trae gana sobre lo que estaba vacio, pero no
        # borra lo que alguien ya habia corregido a mano.
        hotel.direccion = campos.get("direccion_libre") or hotel.direccion
        hotel.telefono = campos.get("telefono_libre") or hotel.telefono
        hotel.lat = datos.hotel_lat or hotel.lat
        hotel.lon = datos.hotel_lon or hotel.lon
        db.flush()
        # El hospedaje apunta al catalogo: un solo lugar donde corregir
        # el telefono el dia que cambie.
        campos["hotel_id"] = hotel.id
        for suelto in ("nombre_libre", "direccion_libre", "telefono_libre"):
            campos[suelto] = None
    hospedaje = (db.query(m.Hospedaje)
                 .filter_by(equipo_id=equipo.id).first())
    if not hospedaje:
        # Servicios de antes de la regla: sus estancias cuelgan del
        # servicio y sin equipo. La que la hoja ya muestra se adopta y
        # las demas se van, para no dejar filas invisibles atras.
        viejas = (db.query(m.Hospedaje)
                  .filter(m.Hospedaje.servicio_id == equipo.servicio_id,
                          m.Hospedaje.equipo_id.is_(None))
                  .order_by(m.Hospedaje.id).all())
        if viejas:
            hospedaje = viejas[0]
            hospedaje.equipo_id = equipo.id
            for sobrante in viejas[1:]:
                db.delete(sobrante)
    if hospedaje:
        for campo, valor in campos.items():
            setattr(hospedaje, campo, valor)
        accion = "corregir hospedaje"
    else:
        hospedaje = m.Hospedaje(servicio_id=servicio.id, equipo_id=equipo.id,
                                **campos)
        db.add(hospedaje)
        accion = "registrar hospedaje"

    auditoria.registrar(db, usuario, servicio, accion,
                        f"{datos.nombre_libre or datos.hotel_id} · "
                        f"{equipo.alias}")
    db.commit()
    db.refresh(hospedaje)
    return {"hospedaje_id": hospedaje.id, "hotel": hospedaje.nombre,
            "equipo_id": equipo.id, "habitacion": hospedaje.habitacion}


@router.delete("/hospedajes/equipo/{equipo_id}",
               summary="Quitar el hotel del equipo")
def quitar_hospedaje(equipo_id: int, db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(ARMAR)):
    """Se lleva lo mismo que la hoja esta mostrando.

    Hay servicios de antes de la regla con sus estancias colgadas del
    servicio y sin equipo: se ven en la hoja del equipo, asi que quitar
    el hotel tiene que quitar esas tambien. Si no, el boton parecia
    roto: quitaba algo que no era lo que estaba en pantalla.
    """
    equipo = _equipo(db, equipo_id)
    suyos = db.query(m.Hospedaje).filter_by(equipo_id=equipo.id).all()
    if not suyos:
        suyos = (db.query(m.Hospedaje)
                 .filter(m.Hospedaje.servicio_id == equipo.servicio_id,
                         m.Hospedaje.equipo_id.is_(None)).all())
    if not suyos:
        raise HTTPException(404, "Ese equipo no tiene hotel registrado")

    for hospedaje in suyos:
        db.delete(hospedaje)
    auditoria.registrar(db, usuario, equipo.servicio, "quitar hospedaje",
                        equipo.alias)
    db.commit()
    return {"resultado": "hospedaje quitado", "equipo_id": equipo.id,
            "quitados": len(suyos)}


@router.get("/hospedajes/equipo/{equipo_id}", summary="Hotel del equipo")
def ver_hospedaje_equipo(equipo_id: int, db: Session = Depends(get_db),
                         _=Depends(LECTURA)):
    return motor.hospedaje_de(db, _equipo(db, equipo_id))


@router.get("/hospedajes/servicio/{servicio_id}", summary="Hospedaje del servicio")
def ver_hospedaje(servicio_id: int, db: Session = Depends(get_db),
                  _=Depends(LECTURA)):
    return motor.hospedaje_de(db, _equipo_unico(db, _servicio(db, servicio_id).id))


# ---------------------------------------------------------------- task sheet

def _equipo(db: Session, equipo_id: int) -> m.Equipo:
    equipo = db.get(m.Equipo, equipo_id)
    if not equipo:
        raise HTTPException(404, f"No existe el equipo {equipo_id}")
    return equipo


def _equipo_unico(db: Session, servicio_id: int) -> m.Equipo:
    """Atajo para el caso normal: el servicio trae un solo equipo."""
    equipos = motor.equipos_de(db, servicio_id)
    if not equipos:
        raise HTTPException(409, "El servicio no tiene equipos")
    if len(equipos) > 1:
        raise HTTPException(409, {
            "mensaje": "El servicio tiene varios equipos y cada uno lleva su "
                       "propio task sheet",
            "equipos": [{"equipo_id": e.id, "alias": e.alias} for e in equipos],
        })
    return equipos[0]


@router.get("/task-sheets/equipo/{equipo_id}/vista-previa",
            summary="Como quedaria el task sheet de ese equipo")
def vista_previa(equipo_id: int, db: Session = Depends(get_db),
                 _=Depends(PUBLICAR)):
    return motor.armar(db, equipo_id)


@router.get("/task-sheets/servicio/{servicio_id}/vista-previa",
            summary="Vista previa cuando el servicio trae un solo equipo")
def vista_previa_servicio(servicio_id: int, db: Session = Depends(get_db),
                          _=Depends(PUBLICAR)):
    return motor.armar(db, _equipo_unico(db, servicio_id).id)


@router.post("/task-sheets/equipo/{equipo_id}/publicar",
             summary="Publicar el task sheet de un equipo")
def publicar(equipo_id: int, datos: s.PublicarTaskSheetIn,
             db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(PUBLICAR)):
    ficha = motor.publicar(db, equipo_id, usuario.persona_id,
                           datos.motivo, datos.forzar, avisar=datos.avisar)
    auditoria.registrar(db, usuario, ficha.servicio, "publicar task sheet",
                        f"{ficha.equipo.alias} version {ficha.version}")
    db.commit()
    return {"task_sheet_id": ficha.id, "equipo": ficha.equipo.alias,
            "version": ficha.version,
            "publicado_en": ficha.publicado_en.isoformat(),
            "aviso": datos.avisar,
            # Se dice a quien se le mando, y cuando no se mando se dice
            # vacio: la pantalla tiene que poder decir "publicado, sin
            # aviso" en vez de dejar creer que el cliente ya se entero.
            "compartido_con": (["solicitante", "ejecutivo"]
                               if datos.avisar else [])}


@router.post("/task-sheets/servicio/{servicio_id}/publicar",
             summary="Publicar el task sheet de cada equipo del servicio")
def publicar_servicio(servicio_id: int, datos: s.PublicarTaskSheetIn,
                      db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(PUBLICAR)):
    """Casi siempre el servicio trae un equipo; si trae varios, se publica
    uno por equipo."""
    publicados = []
    for equipo in motor.equipos_de(db, servicio_id):
        ficha = motor.publicar(db, equipo.id, usuario.persona_id,
                               datos.motivo, datos.forzar, avisar=datos.avisar)
        auditoria.registrar(db, usuario, ficha.servicio, "publicar task sheet",
                            f"{equipo.alias} version {ficha.version}")
        publicados.append({"task_sheet_id": ficha.id, "equipo_id": equipo.id,
                           "equipo": equipo.alias, "version": ficha.version,
                           "publicado_en": ficha.publicado_en.isoformat()})
    db.commit()
    if len(publicados) == 1:
        return {**publicados[0], "aviso": datos.avisar,
                "compartido_con": (["solicitante", "ejecutivo"]
                                   if datos.avisar else [])}
    return {"equipos": publicados, "aviso": datos.avisar,
            "compartido_con": (["solicitante", "ejecutivo"]
                               if datos.avisar else [])}


def _puede_ver(db: Session, usuario: m.Usuario, equipo: m.Equipo) -> None:
    if usuario.rol != m.Rol.PERSONAL_SEGURIDAD:
        return
    jornadas = [j.id for j in equipo.jornadas]
    participa = (db.query(m.AsignacionPersonal)
                 .filter(m.AsignacionPersonal.jornada_id.in_(jornadas),
                         m.AsignacionPersonal.persona_id == usuario.persona_id)
                 .first())
    if not participa:
        raise HTTPException(403, "No participas en ese equipo")


@router.get("/task-sheets/equipo/{equipo_id}", summary="Task sheet vigente")
def vigente(equipo_id: int, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(auth.usuario_actual)):
    equipo = _equipo(db, equipo_id)
    _puede_ver(db, usuario, equipo)

    ficha = motor.vigente(db, equipo_id)
    if not ficha:
        raise HTTPException(404, "Ese equipo no tiene task sheet publicado")
    return {"version": ficha.version,
            "publicado_en": ficha.publicado_en.isoformat(),
            **json.loads(ficha.contenido)}


@router.get("/task-sheets/servicio/{servicio_id}",
            summary="Task sheet vigente cuando el servicio trae un solo equipo")
def vigente_servicio(servicio_id: int, db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(auth.usuario_actual)):
    return vigente(_equipo_unico(db, servicio_id).id, db, usuario)


# ================================================= la hoja del implantado

# Es otro documento que el del eventual, aunque se parezca: el eventual
# se lee por dias y el implantado se lee una vez y se archiva. Va por su
# propia puerta para que ninguno le estorbe al otro.

@router.get("/task-sheets/implantado/{servicio_id}/hoja",
            response_class=HTMLResponse,
            summary="La hoja del implantado: el acuerdo y el equipo de planta")
def hoja_implantado(servicio_id: int, idioma: str | None = None,
                    db: Session = Depends(get_db), _=Depends(PUBLICAR)):
    contenido = hoja_imp.armar(db, servicio_id)
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio_id).first())
    version = (acuerdo.version_hoja if acuerdo and acuerdo.version_hoja
               else 1)
    actualizado = (acuerdo.hoja_en.strftime("%d/%m/%Y %H:%M")
                   if acuerdo and acuerdo.hoja_en else None)
    return HTMLResponse(hoja_html.render(contenido, version, actualizado,
                                         idioma))


@router.get("/task-sheets/implantado/{servicio_id}/cobertura/{fecha}",
            response_class=HTMLResponse,
            summary="La hoja de un dia que cubre alguien mas")
def hoja_cobertura(servicio_id: int, fecha: date, idioma: str | None = None,
                   db: Session = Depends(get_db), _=Depends(PUBLICAR)):
    """El sabado que pidio el cliente, o el dia que cubrio un relevo.

    Misma hoja, con la banda de cobertura y quien va ese dia. Un fin de
    semana sale en una sola: es el mismo relevo y el cliente recibe un
    correo, no dos.
    """
    contenido = hoja_imp.armar_cobertura(db, servicio_id, fecha)
    return HTMLResponse(hoja_html.render(contenido, 1, None, idioma))


@router.post("/task-sheets/implantado/{servicio_id}/liberar",
             summary="Liberar la hoja del implantado")
def liberar_implantado(servicio_id: int, db: Session = Depends(get_db),
                       usuario: m.Usuario = Depends(PUBLICAR)):
    """Liberar la hoja es decir que el servicio ya esta armado.

    Se arma antes de liberarla, no al reves: si la hoja no se puede
    construir es que algo falta, y se dice aqui en vez de mandarla a
    medias. Al liberarla el servicio pasa a asignado: tiene acuerdo,
    tiene plantilla y el cliente ya sabe quien llega.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio or servicio.tipo != m.TipoServicio.IMPLANTADO:
        raise HTTPException(404, f"No existe el implantado {servicio_id}")

    hoja_imp.armar(db, servicio_id)        # revienta si falta algo

    # Un fin de semana contratado y sin nadie no se manda al cliente: la
    # hoja diria que el equipo llega el sabado y el sabado no llega
    # nadie. Se resuelve antes, dia por dia, desde el calendario.
    ambar = implantado.dias_en_ambar(db, servicio)
    if ambar:
        raise HTTPException(409, {
            "mensaje": f"Faltan {len(ambar)} dias por cubrir",
            "que_hacer": ("Cubra los dias en ambar del calendario antes de "
                          "liberar la hoja."),
            "dias": ambar})

    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio_id).first())
    acuerdo.version_hoja = (acuerdo.version_hoja or 0) + 1
    acuerdo.hoja_en = datetime.now(timezone.utc)
    if servicio.estatus in (m.EstatusServicio.BORRADOR,
                            m.EstatusServicio.SOLICITADO,
                            m.EstatusServicio.COTIZADO,
                            m.EstatusServicio.AUTORIZADO,
                            m.EstatusServicio.PLANEADO):
        servicio.estatus = m.EstatusServicio.ASIGNADO

    auditoria.registrar(db, usuario, servicio, "liberar hoja implantado",
                        f"version {acuerdo.version_hoja}")
    db.commit()
    return {"servicio_id": servicio.id, "folio": servicio.folio,
            "version": acuerdo.version_hoja,
            "estatus": servicio.estatus.value}


@router.get("/task-sheets/equipo/{equipo_id}/hoja", response_class=HTMLResponse,
            summary="Version imprimible, para compartir")
def hoja(equipo_id: int, db: Session = Depends(get_db),
         idioma: str = "en",
         usuario: m.Usuario = Depends(auth.usuario_actual)):
    """Por defecto en ingles, porque el ejecutivo suele ser extranjero.
    Con ?idioma=es o ?idioma=pt sale en el idioma local.

    Sale con lo ultimo capturado, no con la copia congelada: el consultor
    manda el TS por correo cuando ya quedo, y si movio una parada en la
    mañana el PDF de la tarde tiene que traerla. Las copias congeladas se
    guardan igual, para el expediente, y se leen por su version.

    Se libera al confirmar la asignacion: antes de eso el servicio sigue
    armandose y mandar esa hoja seria mandar un borrador.
    """
    equipo = _equipo(db, equipo_id)
    _puede_ver(db, usuario, equipo)

    servicio = equipo.servicio
    if not servicio.asignacion_confirmada_en:
        raise HTTPException(409, {
            "mensaje": "El TS todavia no se libera",
            "que_hacer": "Confirma la asignacion: ahi se revisa que el "
                         "servicio tenga todo lo que la hoja necesita",
        })

    contenido = motor.armar(db, equipo_id)
    ficha = motor.vigente(db, equipo_id)
    version = ficha.version if ficha else 1
    cuando = servicio.asignacion_confirmada_en.strftime("%d/%m/%Y %H:%M")
    return HTMLResponse(tasksheet_html.render(contenido, version, cuando, idioma))


@router.get("/task-sheets/servicio/{servicio_id}/hoja",
            response_class=HTMLResponse,
            summary="Hoja cuando el servicio trae un solo equipo")
def hoja_servicio(servicio_id: int, db: Session = Depends(get_db),
                  idioma: str = "en",
                  usuario: m.Usuario = Depends(auth.usuario_actual)):
    return hoja(_equipo_unico(db, servicio_id).id, db, idioma, usuario)


@router.get("/task-sheets/servicio/{servicio_id}/equipos",
            summary="Equipos del servicio y el estado de su task sheet")
def equipos_del_servicio(servicio_id: int, db: Session = Depends(get_db),
                         _=Depends(LECTURA)):
    salida = []
    for equipo in motor.equipos_de(db, servicio_id):
        ficha = motor.vigente(db, equipo.id)
        salida.append({
            "equipo_id": equipo.id, "alias": equipo.alias,
            "jornadas": len(equipo.jornadas),
            "task_sheet": ({"version": ficha.version,
                            "publicado_en": ficha.publicado_en.isoformat()}
                           if ficha else None),
        })
    return salida


@router.get("/task-sheets/equipo/{equipo_id}/versiones",
            summary="Historial de versiones")
def versiones(equipo_id: int, db: Session = Depends(get_db), _=Depends(LECTURA)):
    fichas = (db.query(m.TaskSheet).filter_by(equipo_id=equipo_id)
              .order_by(m.TaskSheet.version).all())
    return [{"version": f.version, "estatus": f.estatus.value,
             "motivo_cambio": f.motivo_cambio,
             "publicado_en": f.publicado_en.isoformat() if f.publicado_en else None}
            for f in fichas]


@router.get("/task-sheets/servicio/{servicio_id}/versiones",
            summary="Historial cuando el servicio trae un solo equipo")
def versiones_servicio(servicio_id: int, db: Session = Depends(get_db),
                       _=Depends(LECTURA)):
    return versiones(_equipo_unico(db, servicio_id).id, db, _)


# ---------------------------------------------------------------- senal

# Las reglas de la imagen viven en app/imagenes.py: las comparten la
# senal y el comprobante de una compra de finanzas.
TIPOS_DE_IMAGEN = imagenes.TIPOS_DE_IMAGEN
LIMITE_IMAGEN = imagenes.LIMITE


@router.put("/servicios/{servicio_id}/senal",
            summary="Senal con la que el ejecutivo identifica al equipo")
def definir_senal(servicio_id: int, datos: s.SenalIn,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(ARMAR)):
    """Una palabra, una imagen o ambas. Se imprime en una hoja aparte para
    que el equipo la muestre al salir el ejecutivo del filtro o en el lobby."""
    servicio = _servicio(db, servicio_id)
    if not datos.texto and not datos.imagen:
        raise HTTPException(400, "Indica al menos una palabra o una imagen")

    servicio.senal_texto = datos.texto
    if datos.imagen:
        servicio.senal_imagen = datos.imagen
    servicio.senal_nota = datos.nota

    auditoria.registrar(db, usuario, servicio, "definir senal",
                        datos.texto or "imagen")
    db.commit()
    return {"resultado": "senal guardada", "texto": servicio.senal_texto,
            "tiene_imagen": bool(servicio.senal_imagen),
            "nota": "Recuerda volver a publicar el task sheet para que la incluya"}


@router.post("/servicios/{servicio_id}/senal/imagen",
             summary="Subir la imagen de la senal")
async def subir_senal(servicio_id: int, archivo: UploadFile = File(...),
                      db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(ARMAR)):
    """La imagen se guarda dentro del documento, no como enlace, para que la
    hoja se pueda imprimir o mandar sin depender de internet."""
    servicio = _servicio(db, servicio_id)

    servicio.senal_imagen = await imagenes.leer(archivo)
    auditoria.registrar(db, usuario, servicio, "subir imagen de senal",
                        archivo.filename)
    db.commit()
    return {"resultado": "imagen guardada", "archivo": archivo.filename,
            "nota": "Recuerda volver a publicar el task sheet para que la incluya"}


# ------------------------------------------------------- paradas del dia

def _jornada(db: Session, jornada_id: int) -> m.Jornada:
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    return jornada


def _paradas(db: Session, jornada_id: int) -> list[m.ParadaAgenda]:
    """En orden de reloj. Las que no tienen hora se van al final: son
    las que el cliente todavia no confirma."""
    paradas = (db.query(m.ParadaAgenda)
               .filter_by(jornada_id=jornada_id).all())
    return sorted(paradas, key=lambda p: (p.hora is None, p.hora, p.id))


@router.get("/operacion/jornadas/{jornada_id}/agenda/paradas",
            response_model=list[s.ParadaOut],
            summary="Las paradas del dia, en orden")
def ver_paradas(jornada_id: int, db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(auth.usuario_actual)):
    """La agenda dice a que hora y en que direccion va a estar el
    ejecutivo. Es el dato mas delicado del sistema y estaba abierto a
    cualquiera con sesion: bastaba recorrer los numeros de jornada para
    sacar el itinerario de todos los protegidos, incluidos los servicios
    en los que uno no va."""
    jornada = _jornada(db, jornada_id)
    _puede_ver(db, usuario, jornada.equipo)
    return _paradas(db, jornada_id)


@router.post("/operacion/jornadas/{jornada_id}/agenda/paradas",
             response_model=s.ParadaOut, status_code=201,
             summary="Agregar una parada al dia")
def agregar_parada(jornada_id: int, datos: s.ParadaIn,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(ARMAR)):
    jornada = _jornada(db, jornada_id)
    parada = m.ParadaAgenda(jornada_id=jornada_id, **datos.model_dump())
    db.add(parada)
    auditoria.registrar(db, usuario, jornada.equipo.servicio, "agregar parada",
                        f"{datos.hora or 'sin hora'} · {datos.lugar}",
                        jornada_id=jornada_id)
    db.commit()
    db.refresh(parada)
    return parada


@router.patch("/operacion/paradas/{parada_id}", response_model=s.ParadaOut,
              summary="Corregir una parada")
def corregir_parada(parada_id: int, datos: s.ParadaEdicion,
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(ARMAR)):
    parada = db.get(m.ParadaAgenda, parada_id)
    if not parada:
        raise HTTPException(404, f"No existe la parada {parada_id}")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if campo == "lugar" and not valor:
            continue          # una parada sin lugar no dice nada
        setattr(parada, campo, valor)
    auditoria.registrar(db, usuario, parada.jornada.equipo.servicio,
                        "corregir parada",
                        f"{parada.hora or 'sin hora'} · {parada.lugar}",
                        jornada_id=parada.jornada_id)
    db.commit()
    db.refresh(parada)
    return parada


@router.delete("/operacion/paradas/{parada_id}", status_code=204,
               summary="Quitar una parada")
def quitar_parada(parada_id: int, db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(ARMAR)):
    parada = db.get(m.ParadaAgenda, parada_id)
    if not parada:
        raise HTTPException(404, f"No existe la parada {parada_id}")
    servicio = parada.jornada.equipo.servicio
    jornada_id = parada.jornada_id
    detalle = f"{parada.hora or 'sin hora'} · {parada.lugar}"
    db.delete(parada)
    auditoria.registrar(db, usuario, servicio, "quitar parada", detalle,
                        jornada_id=jornada_id)
    db.commit()


@router.delete("/servicios/{servicio_id}/senal", status_code=204,
               summary="Quitar la senal")
def quitar_senal(servicio_id: int, db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(ARMAR)):
    servicio = _servicio(db, servicio_id)
    servicio.senal_texto = servicio.senal_imagen = servicio.senal_nota = None
    auditoria.registrar(db, usuario, servicio, "quitar senal", None)
    db.commit()


@router.get("/task-sheets/idiomas", summary="Idiomas disponibles del task sheet")
def idiomas(_=Depends(auth.usuario_actual)):
    """El task sheet se arma en ingles por defecto; se puede pedir en el
    idioma local agregando ?idioma= a la hoja."""
    return {"por_defecto": "en", "disponibles": IDIOMAS}

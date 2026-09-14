"""Registro de todos los catalogos y del tarifario."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import auth
from app import models as m
from app import schemas as s
from app.db import get_db
from app.routers.crud import crud_router

router = APIRouter()

# ------------------------------------------------------------- ciudades

# Cuanto aguanta una ciudad en la lista sin que nadie la use.
DIAS_SIN_USAR = 30


@router.get("/plazas", response_model=list[s.PlazaOut], tags=["Ciudades"],
            summary="Listar ciudades")
def listar_ciudades(db: Session = Depends(get_db), todas: bool = False,
                    _=Depends(auth.usuario_actual)):
    """Las cuatro fijas siempre; las demas, mientras se esten usando.

    Una ciudad entra a la lista cuando un servicio cae ahi y sale sola a
    los 30 dias sin ocuparse. No se borra: sigue en la base con sus
    servicios y regresa a la lista en cuanto se vuelva a usar. Con
    todas=true salen tambien las dormidas, para la pantalla de catalogos.
    """
    ciudades = (db.query(m.Plaza)
                .filter(m.Plaza.activo.is_(True))
                .order_by(m.Plaza.nombre).all())
    if todas:
        return ciudades

    desde = date.today() - timedelta(days=DIAS_SIN_USAR)
    vivas = set()

    # Con servicio reciente o por venir: la jornada es la que manda,
    # porque un servicio se captura semanas antes de que ocurra.
    for equipo_plaza, servicio_plaza in (
            db.query(m.Equipo.plaza_id, m.Servicio.plaza_id)
            .join(m.Jornada, m.Jornada.equipo_id == m.Equipo.id)
            .join(m.Servicio, m.Servicio.id == m.Equipo.servicio_id)
            .filter(m.Jornada.fecha >= desde).distinct().all()):
        vivas.add(equipo_plaza or servicio_plaza)

    # Donde vive gente o flota no se apaga la luz aunque no haya servicio.
    for tabla in (m.Persona, m.Vehiculo):
        vivas.update(x[0] for x in db.query(tabla.plaza_id)
                     .filter(tabla.activo.is_(True)).distinct().all())

    limite = datetime.now(timezone.utc) - timedelta(days=DIAS_SIN_USAR)
    return [c for c in ciudades
            if c.fija or c.id in vivas
            # Recien dada de alta: todavia no tiene servicio y no por eso
            # se le esconde a quien la acaba de crear.
            or (c.creada_en and c.creada_en >= limite)]


# ------------------------------------------------------------- hoteles

# Cuanto aguanta un hotel en la lista sin que nadie se hospede ahi.
DIAS_SIN_HOSPEDAR = 90


@router.get("/hoteles", response_model=list[s.HotelOut], tags=["Hoteles"],
            summary="Hoteles de una ciudad")
def listar_hoteles(db: Session = Depends(get_db), plaza_id: int | None = None,
                   todos: bool = False, _=Depends(auth.usuario_actual)):
    """Los que se usan en esa ciudad, y nada mas.

    El catalogo crece con la operacion: cada hotel que se captura queda
    disponible para la ciudad donde se uso. Y se limpia solo: el que
    lleva tres meses sin ocuparse sale de la lista —sigue en la base con
    sus servicios— para que el consultor no busque entre cien hoteles los
    cuatro que de verdad usa. Con todos=true salen tambien los dormidos,
    para la pantalla de catalogos.
    """
    consulta = db.query(m.Hotel).filter(m.Hotel.activo.is_(True))
    # La ciudad es la del equipo: en Monterrey no se ofrecen los de
    # Ciudad de Mexico. Los que no tienen ciudad salen siempre, porque
    # nadie sabe donde ponerlos.
    if plaza_id:
        consulta = consulta.filter(
            or_(m.Hotel.plaza_id == plaza_id, m.Hotel.plaza_id.is_(None)))
    hoteles = consulta.order_by(m.Hotel.nombre).all()
    if todos:
        return hoteles

    desde = date.today() - timedelta(days=DIAS_SIN_HOSPEDAR)
    # Usado quiere decir que alguien se hospedo ahi en un servicio con
    # dias recientes o por venir: un hotel se captura semanas antes.
    usados = {x[0] for x in (
        db.query(m.Hospedaje.hotel_id)
        .join(m.Equipo, m.Equipo.servicio_id == m.Hospedaje.servicio_id)
        .join(m.Jornada, m.Jornada.equipo_id == m.Equipo.id)
        .filter(m.Jornada.fecha >= desde,
                m.Hospedaje.hotel_id.isnot(None))
        .distinct().all())}

    limite = datetime.now(timezone.utc) - timedelta(days=DIAS_SIN_HOSPEDAR)
    return [x for x in hoteles
            if x.id in usados
            # Recien capturado: todavia no tiene servicio y no por eso se
            # le esconde a quien lo acaba de dar de alta.
            or (x.creado_en and x.creado_en >= limite)]


# --------------------------------------------------------------- flota

@router.get("/vehiculos", response_model=list[s.VehiculoOut], tags=["Flota"],
            summary="Listar la flota")
def listar_flota(db: Session = Depends(get_db), incluir_inactivos: bool = False,
                 incluir_rentados: bool = False, limite: int = 200,
                 _=Depends(auth.usuario_actual)):
    """La flota son las unidades de la casa.

    El auto subarrendado vive en la misma tabla, pero no es flota: se
    pidio para un servicio y se devuelve al terminarlo, asi que ofrecerlo
    en la lista general seria prometer un auto que ya no esta. Se ve
    dentro de su servicio, y aqui solo con incluir_rentados.
    """
    consulta = db.query(m.Vehiculo)
    if not incluir_inactivos:
        consulta = consulta.filter(m.Vehiculo.activo.is_(True))
    if not incluir_rentados:
        consulta = consulta.filter(m.Vehiculo.rentado.is_(False))
    return consulta.limit(limite).all()


@router.get("/consultores", summary="Quien puede llevar un servicio")
def consultores(db: Session = Depends(get_db),
                _=Depends(auth.usuario_actual)):
    """Los consultores de la consola.

    Sale de los usuarios con rol de consultor y no del puesto de la
    persona: quien arma servicios es algo del acceso al sistema, no del
    rol con el que alguien cubre un dia en la calle. Mezclarlos era lo
    que hacia que "consultor" significara dos cosas distintas segun
    quien leyera la pantalla.
    """
    filas = (db.query(m.Usuario)
             .filter(m.Usuario.rol == m.Rol.CONSULTOR,
                     m.Usuario.activo.is_(True)).all())
    gente = [f.persona for f in filas if f.persona and f.persona.activo]
    gente.sort(key=lambda p: p.nombre)
    return [{"id": p.id, "nombre": p.nombre, "correo": p.correo,
             "plaza_id": p.plaza_id} for p in gente]


_CATALOGOS = [
    (m.Pais, s.PaisIn, s.PaisOut, "/paises", "Paises"),
    # Las ciudades crecen con la operacion: no son una lista cerrada.
    (m.Plaza, s.PlazaIn, s.PlazaOut, "/plazas", "Ciudades", "ciudades.alta"),
    (m.PerfilPersonal, s.PerfilIn, s.PerfilOut, "/perfiles", "Perfiles de personal"),
    (m.CategoriaVehiculo, s.CategoriaVehiculoIn, s.CategoriaVehiculoOut,
     "/categorias-vehiculo", "Categorias de vehiculo"),
    (m.Modalidad, s.ModalidadIn, s.ModalidadOut, "/modalidades", "Modalidades"),
    (m.Cliente, s.ClienteIn, s.ClienteOut, "/clientes", "Clientes"),
    (m.Tarifario, s.TarifarioIn, s.TarifarioOut, "/tarifarios", "Tarifarios"),
    (m.TarifaRecurso, s.TarifaRecursoIn, s.TarifaRecursoOut,
     "/tarifas-recurso", "Tarifas de recurso"),
    (m.TarifaVehiculo, s.TarifaVehiculoIn, s.TarifaVehiculoOut,
     "/tarifas-vehiculo", "Tarifas de vehiculo"),
    (m.TabuladorViatico, s.TabuladorIn, s.TabuladorOut,
     "/tabulador-viaticos", "Tabulador de viaticos"),
    (m.ComisionPersonal, s.ComisionIn, s.ComisionOut,
     "/comisiones", "Comisiones al personal"),
    (m.Persona, s.PersonaIn, s.PersonaOut, "/personal", "Personal"),
    (m.TarifaFreelance, s.TarifaFreelanceIn, s.TarifaFreelanceOut,
     "/tarifas-freelance", "Tarifas de freelance"),
    (m.Vehiculo, s.VehiculoIn, s.VehiculoOut, "/vehiculos", "Flota"),
    (m.ParametroCombustible, s.ParametroCombustibleIn, s.ParametroCombustibleOut,
     "/parametros-combustible", "Parametros de combustible"),
    (m.DiaFestivo, s.DiaFestivoIn, s.DiaFestivoOut,
     "/dias-festivos", "Dias festivos"),
    (m.Hospital, s.HospitalIn, s.HospitalOut, "/hospitales", "Hospitales"),
    (m.Hotel, s.HotelIn, s.HotelOut, "/hoteles", "Hoteles"),
]

for entrada in _CATALOGOS:
    modelo, esquema_in, esquema_out, prefijo, etiqueta = entrada[:5]
    router.include_router(crud_router(
        modelo=modelo,
        esquema_in=esquema_in,
        esquema_out=esquema_out,
        prefijo=prefijo,
        etiqueta=etiqueta,
        actividad=entrada[5] if len(entrada) > 5 else None,
    ))

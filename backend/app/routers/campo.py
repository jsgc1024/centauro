"""Lo que ve el equipo en la calle.

La app del personal de seguridad no navega: abre y ya esta viendo su dia.
Por eso aqui hay una sola puerta que contesta todo lo que esa pantalla
necesita —donde se presenta, a que hora, con quien va, que ya marco y
que sigue— en vez de cinco consultas que el telefono tendria que hacer
con media barra de senal.

Cada quien ve solo lo suyo. Eso no es una comodidad: la ficha del dia
trae el nombre del ejecutivo al que se protege.
"""
import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app import models as m
from app import reloj
from app import revision as revision_unidad
from app import trayecto
from app import tasksheet
from app import devoluciones as devoluciones_motor
from app import push
from app import viaticos as viaticos_motor
from app.config import settings
from app.db import get_db
from app.operacion import MINUTOS_ANTES_PERMITIDOS, MINUTOS_DESPUES_PERMITIDOS
from app.presentacion import llegada_del_equipo

router = APIRouter(prefix="/campo", tags=["App del personal"])

registro = logging.getLogger("centauro.campo")

CAMPO = auth.requiere(m.Rol.PERSONAL_SEGURIDAD)

# Cuanto tiempo se queda a la vista un viatico ya cerrado, plegado abajo.
# Medio ano: alcanza para el "¿cuanto me depositaron en marzo?" sin
# arrastrar toda la vida laboral de la persona en cada carga de la app.
DIAS_DE_VIATICOS_CERRADOS = 180

# El orden en que pasan las cosas en un dia. La app ofrece el siguiente,
# no los seis: un boton por hito es como se marca "fin de servicio" a
# las siete de la manana.
SECUENCIA = [
    m.TipoHito.LLEGADA_ORIGEN,
    m.TipoHito.CONTACTO_EJECUTIVO,
    m.TipoHito.FIN_SERVICIO,
]

# Los que se pueden marcar en cualquier momento, cuantas veces haga
# falta, una vez arrancado el servicio.
SUELTOS = [
    m.TipoHito.SALIDA_RUTA,
    m.TipoHito.LLEGADA_DESTINO,
    m.TipoHito.STANDBY,
]


def _jornadas_de(db: Session, persona_id: int, desde: date,
                 hasta: date) -> list[m.Jornada]:
    return (db.query(m.Jornada)
            .join(m.AsignacionPersonal,
                  m.AsignacionPersonal.jornada_id == m.Jornada.id)
            .filter(m.AsignacionPersonal.persona_id == persona_id,
                    m.Jornada.fecha >= desde, m.Jornada.fecha <= hasta,
                    m.Jornada.estatus != m.EstatusJornada.CANCELADA)
            .order_by(m.Jornada.inicio_programado).all())


def _ficha(db: Session, jornada: m.Jornada, persona_id: int,
           ahora: datetime) -> dict:
    servicio = jornada.equipo.servicio
    asignacion = next((a for a in jornada.personal
                       if a.persona_id == persona_id), None)
    # Una marca anulada no cuenta. Si contara, el dia que la central
    # reabre quedaria con su fin de servicio ya hecho: la app no
    # volveria a ofrecer ese paso y el equipo no podria cerrar otra vez.
    marcados = (db.query(m.Hito)
                .filter(m.Hito.jornada_id == jornada.id,
                        m.Hito.anulado_en.is_(None))
                .order_by(m.Hito.marcado_en).all())
    hechos = {h.tipo for h in marcados}

    # El siguiente paso: el primero de la secuencia que falta. Ofrecer
    # los seis a la vez es como se marca el fin del servicio a las siete
    # de la manana.
    siguiente = next((t for t in SECUENCIA if t not in hechos), None)

    llega, minutos, contra_vuelo = llegada_del_equipo(
        jornada.inicio_programado, jornada.vuelo_hora, jornada.vuelo_tipo)

    # La ventana en que ese paso se puede marcar sin que la central
    # tenga que revisarlo. Se dice en la pantalla para que nadie marque
    # a destiempo sin saberlo.
    abre = jornada.inicio_programado - timedelta(
        minutes=MINUTOS_ANTES_PERMITIDOS)
    cierra = jornada.inicio_programado + timedelta(
        minutes=MINUTOS_DESPUES_PERMITIDOS)

    # La revision de la unidad va por servicio, no por dia: la misma
    # camioneta veintidos dias no se revisa veintidos veces. Lo que se
    # revisa es el cambio de manos, y por eso lo que se pregunta aqui es
    # si a este servicio ya se le hizo, no a este dia.
    #
    # Y solo las suyas: al escolta que va de copiloto no se le ofrece
    # revisar una unidad que despues no va a poder firmar. Es la misma
    # regla que usa el candado del fin de servicio, traida del mismo
    # lugar para que no se puedan contradecir.
    mias = set(revision_unidad.mis_unidades(jornada, persona_id))
    revision = None
    if mias:
        hechas = (db.query(m.RevisionUnidad)
                  .filter(m.RevisionUnidad.servicio_id == servicio.id,
                          m.RevisionUnidad.vehiculo_id.in_(mias)).all())
        recibidas = {r.vehiculo_id for r in hechas if r.tipo == "recibe"}
        entregadas = {r.vehiculo_id for r in hechas if r.tipo == "entrega"}
        revision = {
            "unidades": len(mias),
            "por_recibir": len(mias - recibidas),
            "por_entregar": len(recibidas - entregadas),
            # Las que hoy dejan el servicio. Con el candado duro en el fin
            # de servicio, esto tiene que verse ANTES de que lo intente:
            # descubrir que no puede cerrar su dia, a las ocho de la noche
            # y con el cliente en el coche, es el peor momento posible.
            "entregar_hoy": revision_unidad.falta_entregar(db, jornada,
                                                           persona_id),
        }

    # Las paradas se ordenan por hora, y las que no la traen van al
    # final: una parada sin hora es "cuando se pueda", no "a primera
    # hora".
    agenda = (db.query(m.AgendaJornada)
              .filter_by(jornada_id=jornada.id).first())
    paradas = sorted(
        db.query(m.ParadaAgenda).filter_by(jornada_id=jornada.id).all(),
        key=lambda p: (p.hora is None, p.hora or time.min))

    return {
        "jornada_id": jornada.id,
        "servicio_id": servicio.id,
        "revision": revision,
        "fecha": jornada.fecha.isoformat(),
        "folio": servicio.folio,
        "cliente": servicio.cliente.nombre if servicio.cliente else None,
        "ejecutivo": servicio.ejecutivo_completo,
        # Como hay que ir vestido. Se manda tambien en la tarjeta de
        # manana a proposito: cuando de verdad sirve es la noche
        # anterior, que es cuando se decide que ponerse.
        "vestimenta": (servicio.vestimenta
                       if servicio.tipo == m.TipoServicio.EVENTUAL else None),
        "equipo": jornada.equipo.alias,
        "equipo_id": jornada.equipo_id,
        "estatus": jornada.estatus.value,
        "mi_rol": asignacion.rol.nombre if asignacion and asignacion.rol else None,
        "confirmado": bool(asignacion and asignacion.confirmado),
        "companeros": [{"nombre": a.persona.nombre,
                        "rol": a.rol.nombre if a.rol else None,
                        "telefono": a.persona.telefono}
                       for a in jornada.personal
                       if a.persona_id != persona_id and a.persona],
        "unidades": [{"placa": a.vehiculo.placa,
                      "unidad": (a.vehiculo.categoria.nombre
                                 if a.vehiculo.categoria else None),
                      "color": a.vehiculo.color}
                     for a in jornada.vehiculos if a.vehiculo],
        # La hora que importa: a la que hay que estar parado en el punto.
        "presentacion": jornada.inicio_programado.isoformat(),
        # Ver el comentario de `proximos`: la heredada no es un dato.
        "hora_confirmada": bool(jornada.hora_confirmada),
        "llegar_a_las": llega.isoformat(),
        "anticipacion_minutos": minutos,
        "contra_vuelo": contra_vuelo,
        "vuelo": ({"aerolinea": jornada.vuelo_aerolinea,
                   "numero": jornada.vuelo_numero,
                   "hora": (jornada.vuelo_hora.isoformat()
                            if jornada.vuelo_hora else None)}
                  if jornada.vuelo_numero else None),
        "punto": {
            "direccion": jornada.origen_direccion,
            "lat": float(jornada.origen_lat) if jornada.origen_lat else None,
            "lon": float(jornada.origen_lon) if jornada.origen_lon else None,
            "geocerca_metros": jornada.geocerca_metros,
            "aeropuerto": jornada.origen_aeropuerto,
        },
        "ventana": {"abre": abre.isoformat(), "cierra": cierra.isoformat()},
        "siguiente": siguiente.value if siguiente else None,
        "sueltos": [t.value for t in SUELTOS] if siguiente is None
                   or siguiente == m.TipoHito.FIN_SERVICIO else [],
        "marcados": [{"tipo": h.tipo.value,
                      "marcado_en": h.marcado_en.isoformat(),
                      "diferido": h.diferido,
                      "dentro_geocerca": h.dentro_geocerca,
                      "requiere_revision": h.requiere_revision}
                     for h in marcados],
        "hospitales": tasksheet.hospitales_cercanos(
            db, servicio.plaza_id, jornada.origen_lat, jornada.origen_lon),
        # La agenda del dia, parada por parada. Viaja DENTRO de la ficha
        # y no en una consulta aparte a proposito: el dia se guarda en el
        # telefono para leerse sin senal, y una agenda que solo existe
        # con red es una agenda que no esta cuando hace falta --en un
        # estacionamiento, antes de arrancar--. Son cuatro o cinco
        # renglones; no pesa.
        "agenda": {
            "resumen": agenda.resumen if agenda else None,
            "puntos": agenda.puntos if agenda else None,
            "paradas": [{"hora": p.hora.strftime("%H:%M") if p.hora else None,
                         "lugar": p.lugar,
                         "direccion": p.direccion,
                         "notas": p.notas}
                        for p in paradas],
        },
    }


@router.get("/mi-dia", summary="El dia del equipo, completo")
def mi_dia(db: Session = Depends(get_db), ahora: datetime | None = None,
           usuario: m.Usuario = Depends(CAMPO)):
    """Hoy y manana, en una sola consulta.

    Manana entra porque la confirmacion de la vispera se hace la noche
    anterior: si la app solo mostrara hoy, nadie podria confirmar nunca.
    """
    # El hoy del agente, no el del contenedor: cerca de la medianoche
    # son dias distintos, y esta es la pantalla que abre cada manana.
    ahora = reloj.ahora_de_la_persona(db, usuario.persona, ahora)
    hoy = ahora.date()
    jornadas = _jornadas_de(db, usuario.persona_id, hoy,
                            hoy + timedelta(days=1))

    fichas = [_ficha(db, j, usuario.persona_id, ahora) for j in jornadas]

    # Lo que viene despues de manana, en corto: pediste sus servicios
    # pendientes y dos dias no alcanzan para que alguien planee su vida.
    proximas = _jornadas_de(db, usuario.persona_id, hoy + timedelta(days=2),
                            hoy + timedelta(days=13))
    return {
        "momento": ahora.isoformat(),
        "persona": usuario.persona.nombre if usuario.persona else None,
        # Un dia cerrado sale de la pantalla. No queda nada que tocar
        # --el fin de servicio es el ultimo paso y exige la entrega de
        # la unidad-- y dejarlo puesto invita a marcar de mas sobre un
        # dia que ya se cobro. Se cuenta aparte para que el hueco diga
        # "ya cerraste" y no "no tienes servicios", que se leeria como
        # que el dia nunca existio.
        "hoy": [f for f in fichas
                if f["fecha"] == hoy.isoformat()
                and f["estatus"] != m.EstatusJornada.TERMINADA.value],
        "cerrados_hoy": len([f for f in fichas
                             if f["fecha"] == hoy.isoformat()
                             and f["estatus"]
                             == m.EstatusJornada.TERMINADA.value]),
        "manana": [f for f in fichas if f["fecha"] != hoy.isoformat()],
        "proximos": [{
            "jornada_id": j.id,
            "fecha": j.fecha.isoformat(),
            "folio": j.equipo.servicio.folio,
            "equipo": j.equipo.alias,
            "cliente": (j.equipo.servicio.cliente.nombre
                        if j.equipo.servicio.cliente else None),
            "llegar_a_las": llegada_del_equipo(
                j.inicio_programado, j.vuelo_hora, j.vuelo_tipo)[0].isoformat(),
            "punto": j.origen_direccion,
            # Solo el dia 1 trae hora capturada. Los demas la heredan del
            # primero mientras su agenda no diga otra cosa: sirve para
            # calcular --sin hora no hay ventana ni geocerca-- pero es
            # una hora SUPUESTA. La app lo dice en vez de aparentar que
            # alguien la confirmo; si no, el agente planea su noche
            # alrededor de una hora que nadie dijo.
            "hora_confirmada": bool(j.hora_confirmada),
        } for j in proximas],
        # El telefono al que se llama cuando algo se rompe: la app, la
        # senal, o el servicio. Decir "llama a la central" sin dar el
        # numero es no decir nada.
        "central": _central(db),
    }


def _central(db: Session) -> dict | None:
    """Quien esta del otro lado, y a que numero se le marca.

    El numero es el de la linea de la central, no el celular de quien
    este de turno: el turno cambia cada ocho horas y el numero al que se
    llama cuando algo se sale de control no puede cambiar con el. El
    nombre si sale del usuario en turno, para que el de campo sepa con
    quien va a hablar.
    """
    fila = (db.query(m.Usuario)
            .filter(m.Usuario.rol == m.Rol.CENTRAL,
                    m.Usuario.activo.is_(True)).first())
    nombre = fila.persona.nombre if fila and fila.persona else "Central"
    return {"nombre": nombre,
            "telefono": settings.telefono_central,
            "celular": (fila.persona.telefono
                        if fila and fila.persona else None)}


@router.get("/jornadas/{jornada_id}", summary="Una jornada suya")
def una(jornada_id: int, db: Session = Depends(get_db),
        ahora: datetime | None = None,
        usuario: m.Usuario = Depends(CAMPO)):
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    if not any(a.persona_id == usuario.persona_id for a in jornada.personal):
        raise HTTPException(403, "No estas asignado a esa jornada")
    return _ficha(db, jornada, usuario.persona_id, ahora or datetime.now())


# ==================================================================
# Su dinero
#
# Dos bolsas distintas y la app no puede confundirlas: los viaticos son
# dinero de la empresa que trae para gastar en el servicio y que tiene
# que comprobar; la comision es lo que se le paga a el por su trabajo.
# ==================================================================

@router.get("/mis-viaticos", summary="Lo que trae y lo que debe comprobar")
def mis_viaticos(db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(CAMPO)):
    """Por servicio, con su fecha limite.

    Ve y comprueba; no pide. Cuanto se le deposita lo decide el
    consultor y el deposito lo hace finanzas: mostrarle un boton de
    "pedir mas" seria ofrecerle algo que la app no puede cumplir.
    """
    # El plazo de comprobacion se vence a la hora del pais donde se
    # esta dando el servicio, que puede no ser el del contenedor.
    relojes = reloj.Relojes(db)
    viaticos = (db.query(m.AsignacionViatico)
                .filter(m.AsignacionViatico.persona_id == usuario.persona_id,
                        m.AsignacionViatico.estatus.notin_(
                            (m.EstatusViatico.CANCELADO,)))
                .all())

    por_servicio: dict = {}
    for v in viaticos:
        jornada = v.jornada
        servicio = jornada.equipo.servicio if jornada and jornada.equipo else None
        if not servicio:
            continue
        # En el implantado la tarjeta es del mes, no del servicio: el
        # deposito se hace por mes y una tarjeta con treinta dias de dos
        # meses le muestra a la persona un total que no corresponde a
        # ningun deposito que le hayan hecho.
        por_mes = servicio.tipo == m.TipoServicio.IMPLANTADO
        periodo = (f"{jornada.fecha.month:02d}/{jornada.fecha.year}"
                   if por_mes else None)
        clave = (servicio.id, periodo)
        fila = por_servicio.setdefault(clave, {
            "servicio_id": servicio.id, "folio": servicio.folio,
            "periodo": periodo,
            "cliente": servicio.cliente.nombre if servicio.cliente else None,
            "moneda": v.moneda.value,
            "entregado": Decimal("0"), "comprobado": Decimal("0"),
            "por_comprobar": Decimal("0"),
            # Autorizado pero todavia en finanzas. Se dice aparte y NUNCA
            # se suma a lo entregado: la app le decia a la gente "te
            # depositaron" con dinero que seguia sin salir del banco.
            "por_depositar": Decimal("0"),
            "dias": [], "limite": None, "vencido": False,
            # Los depositos con los que le llego ese dinero. Contesta la
            # pregunta que hoy termina en una llamada al consultor
            # —"¿ya me depositaron?"— y le da con que reclamarle al
            # banco si el dinero no aparece.
            "depositos": [],
            "por_devolver": Decimal("0"),
            # Lo que ya regreso y finanzas confirmo. Sin este renglon la
            # cuenta de la pantalla no cierra: entregado 285, comprobado
            # 270 y "te falta comprobar 0" solo cuadra si en algun lado
            # dice que 15 volvieron.
            "devuelto": Decimal("0"),
            "devolucion_en_revision": Decimal("0"),
            # El consultor ya reviso el servicio y lo mando a facturar.
            # Desde ahi, esto es historia para el agente.
            "visto_bueno": _con_visto_bueno(db, servicio.id),
        })
        monto = Decimal(str(v.monto_total or 0))
        comprobado = Decimal(str(v.monto_comprobado or 0))

        # El dinero esta con la persona solo cuando finanzas lo
        # deposito: eso es lo que marca TRANSFERIDO, y de ahi en
        # adelante. Mientras esta ASIGNADO o SOLICITADO el monto existe
        # en el sistema y NO en su cuenta.
        #
        # La app sumaba todo y lo rotulaba "te depositaron". Alguien leia
        # que ya tenia el dinero, salia a trabajar contando con el, y no
        # estaba. Y lo que pesaba mas: ese monto entraba a "te falta
        # comprobar" y corria su plazo de 24 horas, asi que podia quedar
        # vencido por un dinero que nunca recibio.
        llego = v.estatus in (m.EstatusViatico.TRANSFERIDO,
                              m.EstatusViatico.EN_COMPROBACION,
                              m.EstatusViatico.CERRADO)
        if not llego:
            fila["por_depositar"] += monto
            fila["dias"].append({
                "viatico_id": v.id,
                "fecha": jornada.fecha.isoformat(),
                "estatus": v.estatus.value,
                "entregado": Decimal("0"), "comprobado": Decimal("0"),
                "por_devolver": Decimal("0"), "devuelto": Decimal("0"),
                "devolucion_en_revision": Decimal("0"),
                "comprobantes": 0, "rechazados": 0,
            })
            continue

        entregado = monto
        # Lo que todavia no sale como comprobado es lo que se le va a
        # pedir. Se dice por dia para que sepa cual le falta.
        fila["entregado"] += entregado
        fila["comprobado"] += comprobado
        # Lo que falta NO se cuenta aqui: se cuenta del servicio entero,
        # abajo. Topar cada dia en cero por separado hacia que un gasto
        # cargado en un dia no descontara de los otros, y la resta de la
        # pantalla dejaba de cuadrar.
        if v.limite_comprobacion:
            actual = v.limite_comprobacion.isoformat()
            fila["limite"] = min(fila["limite"] or actual, actual)
            if v.limite_comprobacion < relojes.de_la_jornada(jornada):
                fila["vencido"] = True
        # Lo que puede regresar de este dia, y lo que ya dijo que
        # transfirio y nadie ha confirmado. Lo segundo se dice aparte:
        # descontarselo de una vez seria apagarle la deuda por un dinero
        # que la empresa todavia no ha visto.
        puede_devolver = devoluciones_motor.por_devolver(v)
        en_revision = devoluciones_motor.declarado_pendiente(v)
        devuelto = Decimal(str(v.monto_devuelto or 0))
        fila["por_devolver"] += puede_devolver
        fila["devuelto"] += devuelto
        fila["devolucion_en_revision"] += en_revision
        fila["dias"].append({
            "viatico_id": v.id,
            "fecha": jornada.fecha.isoformat(),
            "estatus": v.estatus.value,
            "entregado": entregado,
            "comprobado": comprobado,
            "por_devolver": puede_devolver,
            "devuelto": devuelto,
            "devolucion_en_revision": en_revision,
            "comprobantes": len(v.comprobantes),
            "rechazados": len([c for c in v.comprobantes if c.rechazado]),
        })
        for solicitud in db.query(m.SolicitudTransferencia).filter_by(
                asignacion_id=v.id):
            deposito = solicitud.deposito
            if not deposito or any(x["id"] == deposito.id
                                   for x in fila["depositos"]):
                continue
            fila["depositos"].append({
                "id": deposito.id,
                "monto": Decimal(str(deposito.monto)),
                "moneda": deposito.moneda.value,
                "referencia": deposito.referencia,
                "cuando": (deposito.depositado_en.isoformat()
                           if deposito.depositado_en else None),
                "tiene_comprobante": bool(deposito.comprobante),
            })

    filas = sorted(por_servicio.values(),
                   key=lambda x: (not x["vencido"], x["limite"] or ""))
    for f in filas:
        f["dias"].sort(key=lambda d: d["fecha"])
        f["depositos"].sort(key=lambda d: d["cuando"] or "", reverse=True)
        # Un solo deposito, un solo bolson, una sola resta. El dia en el
        # que se cargo el gasto es como el consultor repartio el monto,
        # no un sobre que la persona tenga que respetar.
        f["por_comprobar"] = max(
            f["entregado"] - f["comprobado"] - f["devuelto"], Decimal("0"))

    # Lo cerrado se va abajo. La pantalla mostraba TODO lo que esa
    # persona ha recibido en su vida, sin corte: al ano son doscientos
    # servicios y el unico que importa --el que todavia le corre el
    # plazo-- queda enterrado entre los que ya no.
    #
    # No se borra: es su dinero y tiene derecho a consultarlo. Se pliega,
    # y se guardan los ultimos meses, que es hasta donde alguien
    # pregunta "¿cuanto me depositaron?".
    hoy = date.today()
    viejo = hoy - timedelta(days=DIAS_DE_VIATICOS_CERRADOS)
    pendientes, cerrados = [], []
    for f in filas:
        ultimo = max((d["fecha"] for d in f["dias"]), default=None)
        f["ultimo_dia"] = ultimo
        if _sigue_abierto(f):
            pendientes.append(f)
        elif ultimo and date.fromisoformat(ultimo) >= viejo:
            cerrados.append(f)
    cerrados.sort(key=lambda x: x["ultimo_dia"] or "", reverse=True)

    return {"servicios": pendientes,
            "cerrados": cerrados,
            "total_por_comprobar": sum(f["por_comprobar"] for f in pendientes)}


def _con_visto_bueno(db: Session, servicio_id: int) -> bool:
    """Si el consultor ya cerro ese servicio y lo mando a facturar."""
    cierre = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()
    return bool(cierre and cierre.estatus != m.EstatusCierre.ABIERTO)


def _sigue_abierto(fila: dict) -> bool:
    """Si todavia hay algo que resolver con ese dinero.

    Basta una de las tres: le falta comprobar, le falta que le
    depositen, o dijo que devolvio y finanzas no lo ha confirmado.
    Ademas, un dia que no esta cerrado ni devuelto sigue vivo aunque las
    cuentas den cero: el consultor todavia no lo ha revisado.

    Salvo que el servicio ya tenga el visto bueno. Decision de Salvador,
    20 sep: a partir de ahi el gasto desaparece de la app. Y es cierto
    --ya no hay nada que el agente pueda hacer, el cierre se fue a
    finanzas-- por eso el revisor no deja dar el visto bueno con
    viaticos abiertos: si no, esto le quitaria la pantalla a alguien que
    todavia debe comprobar.
    """
    if fila["visto_bueno"]:
        return False
    if (fila["por_comprobar"] or fila["por_depositar"]
            or fila["devolucion_en_revision"]):
        return True
    return any(d["estatus"] not in ("cerrado", "devuelto")
               for d in fila["dias"])


@router.get("/mis-comisiones", summary="Lo que lleva ganado y lo que ya cobro")
def mis_comisiones(db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(CAMPO)):
    """Lo pagado, y lo que va corriendo esta semana.

    Lo que todavia no se paga es una cuenta, no una promesa: un dia que
    se corrige o una hora extra que no era todavia lo pueden mover. Va
    marcado como en curso, porque un numero que baja sin aviso es la
    forma mas rapida de que el equipo deje de creerle a la app.
    """
    renglones = (db.query(m.RenglonNomina)
                 .join(m.NominaSemanal)
                 .filter(m.RenglonNomina.persona_id == usuario.persona_id)
                 .order_by(m.NominaSemanal.fecha_corte.desc()).all())

    cortes = []
    for r in renglones:
        n = r.nomina
        cortes.append({
            "nomina_id": n.id,
            "semana_del": n.fecha_corte.isoformat(),
            "estatus": n.estatus.value,
            "pagado": n.estatus == m.EstatusNomina.PAGADA,
            "pagada_en": n.pagada_en.isoformat() if n.pagada_en else None,
            "moneda": n.moneda.value,
            "total": Decimal(str(r.total or 0)),
            "dias": [{"descripcion": c.descripcion,
                      "monto": Decimal(str(c.monto or 0)),
                      "rol": c.rol.nombre if c.rol else None,
                      "es_ajuste": c.ajuste_id is not None}
                     for c in r.conceptos],
        })

    # Lo que todavia no entra a ningun corte: los dias trabajados que
    # nadie ha pagado. Se calcula con el mismo motor que la nomina, para
    # que el numero que ve el equipo sea el mismo que el de finanzas.
    from app import nomina as motor

    persona = usuario.persona
    pendientes = []
    if persona:
        ya_en_corte = {c.jornada_id for r in renglones for c in r.conceptos
                       if c.jornada_id}
        for jornada, asignacion in motor.jornadas_pendientes(
                db, persona.plaza.pais_id if persona.plaza else 0):
            if asignacion.persona_id != usuario.persona_id:
                continue
            if jornada.id in ya_en_corte:
                continue
            pago = motor.pago_de_jornada(db, jornada, asignacion,
                                         persona.plaza.pais_id)
            if not pago:
                continue
            pendientes.append({
                "fecha": jornada.fecha.isoformat(),
                "folio": jornada.equipo.servicio.folio,
                "rol": asignacion.rol.nombre if asignacion.rol else None,
                "monto": Decimal(str(pago["monto"])),
            })

    return {
        "cortes": cortes,
        "en_curso": {
            "dias": pendientes,
            "total": sum((p["monto"] for p in pendientes), Decimal("0")),
            "nota": "Todavia no entra a un corte. Puede cambiar si un dia "
                    "se corrige.",
        },
    }


@router.get("/mi-capacitacion", summary="Sus cursos y sus vigencias")
def mi_capacitacion(db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(CAMPO)):
    """Lo que sabe hacer y hasta cuando vale.

    Una certificacion vencida no es una certificacion, y el dia que
    importe nadie va a revisar la fecha. Avisarle con tiempo al que la
    tiene que renovar es lo mas barato que hay.
    """
    hoy = date.today()
    filas = (db.query(m.Capacitacion)
             .filter_by(persona_id=usuario.persona_id, activo=True)
             .order_by(m.Capacitacion.nombre).all())

    salida = []
    for c in filas:
        dias = None
        if c.vigencia_hasta:
            dias = (c.vigencia_hasta - hoy).days
        salida.append({
            "nombre": c.nombre,
            "institucion": c.institucion,
            "obtenida_en": c.obtenida_en.isoformat() if c.obtenida_en else None,
            "vigencia_hasta": (c.vigencia_hasta.isoformat()
                               if c.vigencia_hasta else None),
            "dias_para_vencer": dias,
            "vencida": dias is not None and dias < 0,
            # Un mes de aviso alcanza para renovar casi cualquier cosa.
            "por_vencer": dias is not None and 0 <= dias <= 30,
        })
    return {"cursos": salida,
            "vencidas": len([c for c in salida if c["vencida"]]),
            "por_vencer": len([c for c in salida if c["por_vencer"]])}


@router.get("/mi-calificacion", summary="Su tablero de profesionalismo")
def mi_calificacion(db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(CAMPO)):
    """La misma que ve el consultor al decidir a quien manda.

    Una calificacion que nadie ve no cambia comportamiento. Esta se
    calcula sola de lo que ya pasa —puntualidad, comprobacion,
    incidencias— y por eso se puede enseñar sin discutirla.
    """
    from app import profesionalismo

    return profesionalismo.ficha(db, usuario.persona_id)


@router.get("/mi-bono", summary="Su bono del mes vencido")
def mi_bono(db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(CAMPO)):
    """Lo que gano el mes pasado y por que.

    Enterarse de que no hay bono por un deposito que no llego es la peor
    forma de enterarse. Aqui lo ve el dia 3, con la frase que explica
    cada punto perdido y su fecha, y entonces el dia 5 no hay pleito con
    nadie: ya lo sabia.

    Lo que NO se le ensena: el bono de nadie mas, la comparacion contra
    sus companeros, y la referencia bancaria del deposito --esa es de
    finanzas, y en la app solo sirve para que alguien la fotografie--.
    """
    from datetime import date

    from app import bonos

    anio, mes = bonos.mes_anterior(date.today())
    evaluacion = (db.query(m.EvaluacionMensual)
                  .filter_by(persona_id=usuario.persona_id, anio=anio, mes=mes)
                  .first())
    if not evaluacion:
        # Sin calcular todavia no es un error: es el dia 1 o el dia 2.
        return {"hay": False, "periodo": f"{mes:02d}/{anio}"}

    ficha = bonos.ficha(db, evaluacion)
    ficha["hay"] = True
    ficha["pagado_en"] = (evaluacion.pago.pagado_en.isoformat()
                          if evaluacion.pago else None)
    return ficha


# ==================================================================
# Comprobar desde la calle
# ==================================================================

class ComprobanteDeCampoIn(BaseModel):
    """El ticket, con su foto.

    El monto y el concepto los dice quien comprueba porque es quien
    tiene el papel en la mano; la foto es la prueba. Sin foto tambien se
    puede registrar —hay gastos sin ticket— pero queda dicho que no la
    trae, y eso lo ve el consultor al validar.
    """
    concepto: m.ConceptoViatico
    tipo: m.TipoComprobante = m.TipoComprobante.NOTA
    monto: Decimal
    descripcion: str | None = None
    # La foto ya viene reducida por la app: un telefono saca fotos de
    # cuatro megas y subirlas con media barra de senal no termina nunca.
    imagen: str | None = None


class DevolucionDeCampoIn(BaseModel):
    """Ya transferi lo que sobro.

    La referencia es la del banco: es lo que finanzas busca en el estado
    de cuenta para encontrar ese movimiento. La foto es el comprobante
    de la transferencia.

    Ninguna de las dos se exige aqui --un agente en la carretera con
    media barra de senal puede no tener la captura a la mano-- pero
    finanzas ve lo que falta antes de confirmar, y una devolucion sin
    referencia ni imagen es una que alguien va a tener que perseguir.
    """
    monto: Decimal
    referencia: str | None = Field(default=None, max_length=120)
    imagen: str | None = None


class ManianaDeCampoIn(BaseModel):
    """A que hora y donde se presenta el equipo manana.

    El punto viaja con su lat/lon porque quien lo captura esta parado en
    el: acaba de dejar al principal en la puerta del hotel y ahi mismo
    le dijeron la hora. Sin coordenadas no hay geocerca, y sin geocerca
    ese equipo no puede marcar su llegada manana.
    """
    hora: time
    direccion: str | None = Field(default=None, max_length=300)
    lat: Decimal | None = None
    lon: Decimal | None = None
    nota: str | None = Field(default=None, max_length=300)


@router.post("/jornadas/{jornada_id}/manana",
             summary="A que hora y donde nos vemos manana")
def hora_de_manana_campo(jornada_id: int, datos: ManianaDeCampoIn,
                         db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(CAMPO)):
    """Lo captura quien lo escucho, cuando lo escucho.

    El principal dice "manana a las siete" al bajarse del coche, a las
    diez de la noche. Antes ese dato iba por telefono a la central y se
    quedaba en la cabeza de alguien hasta el dia siguiente; mientras
    tanto, el dia de manana vivia con la hora heredada del primero.

    Solo sobre un dia suyo, y solo hacia el dia siguiente de SU equipo.
    """
    if not auth.es_su_propia_jornada(db, usuario, jornada_id):
        raise HTTPException(403, "No estas asignado a esa jornada")
    jornada = db.get(m.Jornada, jornada_id)

    from app import operacion as motor_operacion

    hecho = motor_operacion.fijar_hora_de_manana(
        db, jornada, datos.hora, usuario.persona_id, datos.nota,
        datos.direccion, datos.lat, datos.lon)
    siguiente, antes = hecho["siguiente"], hecho["antes"]
    db.commit()

    # A los demas del equipo que ya confirmaron. Su confirmacion era
    # sobre otra hora.
    if siguiente.inicio_programado != antes:
        try:
            push.avisar_cambio_de_hora(db, siguiente, antes)
            db.commit()
        except Exception:                     # noqa: BLE001
            # Un aviso que no sale no puede tumbar una hora ya guardada.
            registro.exception("no se pudo avisar el cambio de hora")

    return {"resultado": "listo",
            "jornada_id": siguiente.id,
            "fecha": siguiente.fecha.isoformat(),
            "inicio": siguiente.inicio_programado.isoformat(),
            "punto": siguiente.origen_direccion,
            "con_geocerca": siguiente.origen_lat is not None}


@router.post("/viaticos/{viatico_id}/devolucion",
             summary="Devolver lo que sobro")
def devolver_lo_que_sobro(viatico_id: int, datos: DevolucionDeCampoIn,
                          db: Session = Depends(get_db),
                          usuario: m.Usuario = Depends(CAMPO)):
    """Queda anotado que ese dinero viene de regreso, no que ya volvio.

    Hasta que finanzas lo vea entrar a la cuenta, lo declarado no baja
    lo que esta persona debe comprobar: decirle que ya devolvio --y
    apagarle el plazo-- por un dinero que la empresa no ha visto seria
    el mismo defecto que tenia la app cuando decia "te depositaron" con
    dinero que seguia en el banco.
    """
    viatico = db.get(m.AsignacionViatico, viatico_id)
    if not viatico:
        raise HTTPException(404, f"No existe el viatico {viatico_id}")
    if viatico.persona_id != usuario.persona_id:
        raise HTTPException(403, "Solo puedes devolver de tus propios viaticos")
    if datos.imagen and len(datos.imagen) > 4_000_000:
        raise HTTPException(400, "La foto pesa demasiado. Vuelve a tomarla.")

    fila = devoluciones_motor.declarar(
        db, viatico, datos.monto, datos.referencia, datos.imagen,
        usuario.persona_id, reloj.ahora_de_la_jornada(db, viatico.jornada))
    db.commit()
    return {"resultado": "declarada", "devolucion_id": fila.id,
            "monto": float(fila.monto),
            "por_devolver": float(devoluciones_motor.por_devolver(viatico)),
            "nota": ("Queda anotada. Finanzas la confirma cuando la vea "
                     "entrar a la cuenta.")}


@router.post("/viaticos/{viatico_id}/comprobante",
             summary="Subir un ticket desde el telefono")
def comprobar(viatico_id: int, datos: ComprobanteDeCampoIn,
              db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(CAMPO)):
    """Solo sus propios viaticos, y solo mientras no esten cerrados."""
    viatico = db.get(m.AsignacionViatico, viatico_id)
    if not viatico:
        raise HTTPException(404, f"No existe el viatico {viatico_id}")
    if viatico.persona_id != usuario.persona_id:
        raise HTTPException(403, "Solo puedes comprobar tus propios viaticos")
    if viatico.estatus in (m.EstatusViatico.CERRADO,
                           m.EstatusViatico.DEVUELTO,
                           m.EstatusViatico.CANCELADO):
        raise HTTPException(409, {
            "mensaje": "Ese viatico ya se cerro",
            "que_hacer": "Hablale a tu consultor: lo que falte se resuelve "
                         "como ajuste, no como comprobante."})

    if datos.imagen and len(datos.imagen) > 4_000_000:
        raise HTTPException(400, "La foto pesa demasiado. Vuelve a tomarla.")

    mal = viaticos_motor.revisar_comprobante(
        viatico, datos.monto, datos.concepto, datos.descripcion, db=db)
    if mal:
        raise HTTPException(mal.pop("codigo"), mal)

    db.add(m.Comprobante(
        asignacion_id=viatico.id, concepto=datos.concepto, tipo=datos.tipo,
        monto=datos.monto, descripcion=datos.descripcion,
        imagen=datos.imagen))

    # El total comprobado se recalcula de lo que hay, no se va sumando:
    # un comprobante rechazado deja de contar y la cuenta tiene que
    # seguirlo.
    db.flush()
    db.refresh(viatico)
    viatico.monto_comprobado = sum(
        (Decimal(str(c.monto)) for c in viatico.comprobantes
         if not c.rechazado), Decimal("0"))
    if viatico.estatus == m.EstatusViatico.TRANSFERIDO:
        viatico.estatus = m.EstatusViatico.EN_COMPROBACION
    db.commit()

    # Lo que falta es del servicio entero, no del dia del ticket: es la
    # misma cuenta que ve en su tarjeta, y tiene que decir lo mismo.
    hermanos = viaticos_motor.bolson_del_servicio(db, viatico)
    entregado = sum((Decimal(str(v.monto_total or 0)) for v in hermanos),
                    Decimal("0"))
    comprobado = sum((Decimal(str(v.monto_comprobado or 0))
                      for v in hermanos), Decimal("0"))
    devuelto = sum((Decimal(str(v.monto_devuelto or 0)) for v in hermanos),
                   Decimal("0"))
    return {"resultado": "comprobante registrado",
            "comprobado": str(comprobado),
            "entregado": str(entregado),
            "falta": str(max(entregado - comprobado - devuelto,
                             Decimal("0")))}


# ==================================================================
# Avisos al telefono
# ==================================================================

class SuscripcionIn(BaseModel):
    """Lo que el navegador entrega cuando el agente acepta los avisos."""
    endpoint: str
    p256dh: str
    auth: str
    agente: str | None = None


@router.get("/push/llave", summary="La llave publica para suscribirse")
def llave_push():
    """Es publica a proposito: la reparte la app para que el navegador
    pueda cifrar los avisos. La privada nunca sale del servidor."""
    from app import push

    return {"llave": settings.vapid_public, "activo": push.hay_llaves()}


@router.get("/push/estado", summary="Este telefono, esta suscrito?")
def estado_push(endpoint: str | None = None, db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(CAMPO)):
    """Lo que la pantalla necesita para no mentir.

    El permiso del navegador y la suscripcion del servidor son dos cosas
    distintas, y se pueden separar: el permiso queda concedido y la fila
    nunca se guardo, o el navegador rota la suscripcion por su cuenta. Si
    la pantalla solo mira el permiso, dice "encendidos" para siempre
    mientras el servidor no tiene a donde mandar nada.
    """
    filas = (db.query(m.SuscripcionPush)
             .filter_by(persona_id=usuario.persona_id, activa=True).all())
    return {"suscrito": bool(filas),
            "este_telefono": bool(endpoint and any(f.endpoint == endpoint
                                                   for f in filas)),
            "telefonos": len(filas)}


@router.post("/push/suscribir", summary="Este telefono quiere avisos")
def suscribir(datos: SuscripcionIn, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(CAMPO)):
    """Una persona puede tener varios telefonos y cada uno es una fila.

    Si el mismo endpoint vuelve —la app se reinstalo, el navegador
    renovo la suscripcion— se reusa en vez de duplicarse.
    """
    fila = (db.query(m.SuscripcionPush)
            .filter_by(endpoint=datos.endpoint).first())
    if not fila:
        fila = m.SuscripcionPush(endpoint=datos.endpoint,
                                 persona_id=usuario.persona_id,
                                 p256dh=datos.p256dh, auth=datos.auth)
        db.add(fila)
    fila.persona_id = usuario.persona_id
    fila.p256dh = datos.p256dh
    fila.auth = datos.auth
    fila.agente = (datos.agente or "")[:300] or None
    fila.activa = True
    db.commit()
    return {"resultado": "suscrito"}


@router.delete("/push/suscribir", status_code=204,
               summary="Este telefono ya no quiere avisos")
def desuscribir(endpoint: str, db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(CAMPO)):
    fila = (db.query(m.SuscripcionPush)
            .filter_by(endpoint=endpoint,
                       persona_id=usuario.persona_id).first())
    if fila:
        fila.activa = False
        db.commit()


@router.post("/push/probar", summary="Mandarse un aviso a uno mismo")
def probar(db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(CAMPO)):
    """Para que el agente compruebe en el momento que los avisos le
    llegan. Sin esto, la unica forma de saberlo es esperar a que pase
    algo de verdad, y entonces ya es tarde."""
    from app import push

    r = push.avisar(db, usuario.persona_id, "Centauro",
                    "Los avisos están funcionando en este teléfono.",
                    etiqueta="prueba")
    db.commit()
    if not r["enviados"]:
        raise HTTPException(409, {
            "mensaje": "No se pudo mandar el aviso",
            "que_hacer": r.get("motivo") or "Revisa el permiso del navegador."})
    return r


# ==================================================================
# La revision de la unidad
#
# Va por servicio y solo cuando la unidad cambia de manos: un implantado
# que usa la misma camioneta veintidos dias no se revisa veintidos
# veces. Lo que se revisa es el cambio, no el dia.
# ==================================================================

# Los cuatro lados y el tablero. El odometro se pide desde el 18 de
# septiembre: sin el, el kilometraje era un numero tecleado, y la cuenta
# que sale al entregar --la que nadie apunta y de la que despues todos se
# acuerdan distinto-- no tenia con que comprobarse.
ANGULOS_MINIMOS = ("frente", "atras", "izquierdo", "derecho", "odometro")


class FotoIn(BaseModel):
    angulo: m.AnguloFoto
    imagen: str
    nota: str | None = None
    lat: Decimal | None = None
    lon: Decimal | None = None


class RevisionIn(BaseModel):
    """El estado de la unidad al cambiar de manos."""
    servicio_id: int
    vehiculo_id: int
    tipo: m.TipoRevision
    # Un odometro no cuenta para atras y no llega al millon. Sin topes,
    # un dedazo al entregar (45000 donde decia 145000) deja a la consola
    # ensenando "-100,000 km recorridos durante el servicio" sin que
    # nada lo marque como raro.
    kilometraje: int | None = Field(default=None, ge=0, le=2_000_000)
    # El tanque como se lee en el tablero: octavos, de 0 a 8. Pedir
    # litros es pedir que alguien invente un numero.
    combustible_octavos: int | None = Field(default=None, ge=0, le=8)
    nota: str | None = None
    # La declaracion de dano. Va como opcional en el esquema y se exige
    # abajo, para poder decir por que falta: un 422 de validacion es una
    # pantalla en blanco con un renglon rojo, y del otro lado hay alguien
    # con una mano y media barra de senal.
    hubo_dano: bool | None = None
    dano_tipo: m.TipoDano | None = None
    dano_nota: str | None = None
    firma: str | None = None
    lat: Decimal | None = None
    lon: Decimal | None = None
    fotos: list[FotoIn] = []


def _revision(r: m.RevisionUnidad, con_fotos: bool = True) -> dict:
    """Una revision, con o sin sus fotos.

    Las fotos son medio mega cada una y viven dentro de la base. La
    lista de unidades las mandaba TODAS --recepcion y entrega, de todas
    las unidades del servicio-- en cada consulta: megabytes a un
    telefono con mala senal cada vez que abre la pantalla, y revisiones
    de companeros que no tenia por que traer.

    Ahora la lista manda cuantas hay y las fotos se piden de una
    revision a la vez, cuando se van a ver.
    """
    return {
        "id": r.id,
        "tipo": r.tipo.value if hasattr(r.tipo, "value") else r.tipo,
        "vehiculo_id": r.vehiculo_id,
        "placa": r.vehiculo.placa if r.vehiculo else None,
        "persona": r.persona.nombre if r.persona else None,
        "kilometraje": r.kilometraje,
        "combustible_octavos": r.combustible_octavos,
        "nota": r.nota,
        "hubo_dano": r.hubo_dano,
        "dano_tipo": r.dano_tipo,
        "dano_nota": r.dano_nota,
        "momento": r.momento.isoformat(),
        "cuantas_fotos": len(r.fotos),
        "fotos": ([{"angulo": f.angulo.value if hasattr(f.angulo, "value")
                               else f.angulo,
                    "imagen": f.imagen, "nota": f.nota}
                   for f in r.fotos] if con_fotos else None),
    }


@router.get("/servicios/{servicio_id}/unidades",
            summary="Las unidades del servicio y como van sus revisiones")
def unidades_del_servicio(servicio_id: int, db: Session = Depends(get_db),
                          usuario: m.Usuario = Depends(CAMPO)):
    """Que traigo, si ya la recibi y si ya la entregue.

    Al entregar se devuelve tambien la revision de cuando la recibio:
    es lo que la app pone lado a lado, y es donde un golpe nuevo salta
    solo.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    mias = (db.query(m.AsignacionPersonal)
            .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == servicio_id,
                    m.AsignacionPersonal.persona_id == usuario.persona_id)
            .all())
    if not mias:
        raise HTTPException(403, "No estas asignado a ese servicio")

    unidades = {}
    for equipo in servicio.equipos:
        for jornada in equipo.jornadas:
            for a in jornada.vehiculos:
                if a.vehiculo:
                    unidades[a.vehiculo_id] = a.vehiculo

    hechas = (db.query(m.RevisionUnidad)
              .filter_by(servicio_id=servicio_id).all())
    por_unidad: dict = {}
    for r in hechas:
        tipo = r.tipo.value if hasattr(r.tipo, "value") else r.tipo
        por_unidad.setdefault(r.vehiculo_id, {})[tipo] = r

    salida = []
    for vehiculo_id, unidad in unidades.items():
        suyas = por_unidad.get(vehiculo_id, {})
        salida.append({
            "vehiculo_id": vehiculo_id,
            "placa": unidad.placa,
            "unidad": unidad.categoria.nombre if unidad.categoria else None,
            "color": unidad.color,
            "marca_modelo": unidad.marca_modelo,
            "recibida": (_revision(suyas["recibe"], con_fotos=False)
                         if "recibe" in suyas else None),
            "entregada": (_revision(suyas["entrega"], con_fotos=False)
                          if "entrega" in suyas else None),
        })
    return {"servicio_id": servicio.id, "folio": servicio.folio,
            "unidades": salida}


class EnCaminoIn(BaseModel):
    """Donde esta quien va al punto. Nada mas."""
    lat: Decimal
    lon: Decimal


@router.post("/jornadas/{jornada_id}/en-camino",
             summary="Voy en camino al punto")
def voy_en_camino(jornada_id: int, datos: EnCaminoIn,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(CAMPO)):
    """Un toque desde el aviso, o desde la app abierta.

    La ventana se abre aqui y se cierra al marcar la llegada o al
    acercarse al punto. Fuera de ella no se toma nada: esto es el tiempo
    de la persona, no el del servicio.
    """
    if not auth.es_su_propia_jornada(db, usuario, jornada_id):
        raise HTTPException(403, "No estas asignado a esa jornada")
    return trayecto.registrar(db, jornada_id, usuario.persona_id,
                              datos.lat, datos.lon)


@router.get("/revisiones/{revision_id}",
            summary="Una revision con sus fotos")
def una_revision(revision_id: int, db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(CAMPO)):
    """Las fotos, de una revision a la vez y solo cuando se van a ver.

    El candado es el mismo que para guardarla: tiene que ser una unidad
    de un servicio suyo.
    """
    r = db.get(m.RevisionUnidad, revision_id)
    if not r:
        raise HTTPException(404, f"No existe la revision {revision_id}")
    revision_unidad.es_suya(db, r.servicio_id, r.vehiculo_id,
                            usuario.persona_id)
    return _revision(r)


@router.post("/revisiones", status_code=201,
             summary="Revisar la unidad al recibirla o al entregarla")
def revisar(datos: RevisionIn, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(CAMPO)):
    """Cuatro fotos y una firma, en el momento del cambio de manos.

    Las cuatro se exigen: una revision con dos fotos no sirve para
    discutir un golpe tres semanas despues, que es exactamente para lo
    que existe. Si falta un angulo, mas vale decirlo ahora que
    descubrirlo cuando ya no se puede volver a tomar.
    """
    servicio = revision_unidad.es_suya(
        db, datos.servicio_id, datos.vehiculo_id, usuario.persona_id)
    if not db.get(m.Vehiculo, datos.vehiculo_id):
        raise HTTPException(404, f"No existe la unidad {datos.vehiculo_id}")

    tipo = datos.tipo.value
    ya = (db.query(m.RevisionUnidad)
          .filter_by(servicio_id=datos.servicio_id,
                     vehiculo_id=datos.vehiculo_id, tipo=tipo).first())
    if ya:
        raise HTTPException(409, {
            "mensaje": ("Esa unidad ya se reviso al recibirla"
                        if tipo == "recibe"
                        else "Esa unidad ya se reviso al entregarla"),
            "que_hacer": "Si quedo mal, habla con tu consultor: corregirla "
                         "es borrar la anterior, no guardar dos."})

    if tipo == "entrega":
        recibida = (db.query(m.RevisionUnidad)
                    .filter_by(servicio_id=datos.servicio_id,
                               vehiculo_id=datos.vehiculo_id,
                               tipo="recibe").first())
        if not recibida:
            raise HTTPException(409, {
                "mensaje": "Esa unidad nunca se reviso al recibirla",
                "que_hacer": "Sin el estado de entrada no hay contra que "
                             "comparar. Registra primero la recepcion."})

    # La firma se exigia solo en la pantalla. Media promesa —"cuatro
    # fotos y una firma"— vivia en el JavaScript del telefono: cualquier
    # peticion directa guardaba una revision sin firmar y nadie se
    # enteraba hasta que habia un reclamo.
    # ---- La declaracion de dano
    #
    # La pregunta no se puede saltar. Contestar "no" es un clic, asi que
    # declarar no cuesta mas que no declarar: esa es la unica forma de
    # que el dato sirva. Si declarar saliera caro, la casilla diria "no"
    # siempre y tendriamos una falsa sensacion de estar documentando.
    if datos.hubo_dano is None:
        raise HTTPException(409, {
            "mensaje": ("Falta decir si la recibes con algun dano"
                        if tipo == "recibe" else
                        "Falta decir si la unidad se dano durante tu servicio"),
            "que_hacer": ("Contesta si o no. Si la recibes golpeada, "
                          "declararlo es lo que te protege: queda como el "
                          "estado en que te la dieron."
                          if tipo == "recibe" else
                          "Contesta si o no. Declarar un golpe no es una "
                          "falta; lo revisa tu consultor."),
        })

    if datos.hubo_dano:
        if not datos.dano_tipo:
            raise HTTPException(409, {
                "mensaje": "Falta decir de que fue el dano",
                "que_hacer": "Elige rayon, golpe, cristal, llanta, mecanico "
                             "u otro.",
                "opciones": [t.value for t in m.TipoDano]})

        if not datos.dano_nota or len(datos.dano_nota.strip()) < 10:
            raise HTTPException(409, {
                "mensaje": ("Falta describir el dano"
                            if tipo == "recibe" else
                            "Falta explicar que paso"),
                "que_hacer": ("Escribe donde esta y como se ve. Quien lea "
                              "esto dentro de un mes no estuvo ahi."
                              if tipo == "recibe" else
                              "Escribe que paso, con tus palabras. Quien lo "
                              "lea dentro de un mes no estuvo ahi."),
            })

        # Un dano declarado sin foto es media declaracion: el texto dice
        # que paso y la foto dice como se ve. Sin la segunda, tres
        # semanas despues no hay contra que comparar.
        if not any(f.angulo == m.AnguloFoto.DANO for f in datos.fotos):
            raise HTTPException(409, {
                "mensaje": "Falta la foto del dano",
                "que_hacer": "Toma un acercamiento del golpe, aparte de las "
                             "cinco de la unidad. Es la que de verdad sirve "
                             "para discutirlo despues."})

    # El numero del tablero, ahora que su foto es obligatoria. Tener la
    # prueba y no el dato deja la cuenta que sale al entregar --"recorrio
    # 1,800 km"-- sin poder salir, que es justo para lo que se pidio la
    # foto. Se exige aqui y no en el esquema para poder decir por que: un
    # 422 de validacion es una pantalla en blanco con un renglon rojo.
    if datos.kilometraje is None:
        raise HTTPException(409, {
            "mensaje": "Falta el kilometraje",
            "que_hacer": "Escribe el numero que marca el tablero, el mismo "
                         "de la foto. Sin el, al entregar no se puede decir "
                         "cuanto se recorrio."})

    if not datos.firma or len(datos.firma) < 100:
        raise HTTPException(409, {
            "mensaje": "Falta la firma",
            "que_hacer": "Firma con el dedo en el recuadro. Sin firma, la "
                         "revision no sirve para discutir un dano."})

    # Las fotos viajan como data URI dentro del JSON. Cuatro lados mas
    # los golpes se van facil a varios megas, y del otro lado hay un
    # telefono con media barra de senal.
    pesa = sum(len(f.imagen) for f in datos.fotos)
    if pesa > 8_000_000:
        raise HTTPException(413, {
            "mensaje": "Las fotos pesan demasiado juntas",
            "que_hacer": "Quita algunas fotos de golpes y vuelve a "
                         "intentarlo. Los cuatro lados y el odometro son "
                         "los que importan."})
    for f in datos.fotos:
        if len(f.imagen) > 3_000_000:
            raise HTTPException(413, {
                "mensaje": f"La foto de {f.angulo.value} pesa demasiado",
                "que_hacer": "Vuelve a tomarla."})

    if datos.kilometraje is not None and tipo == "entrega":
        entrada_km = (db.query(m.RevisionUnidad)
                      .filter_by(servicio_id=datos.servicio_id,
                                 vehiculo_id=datos.vehiculo_id,
                                 tipo="recibe").first())
        if (entrada_km and entrada_km.kilometraje is not None
                and datos.kilometraje < entrada_km.kilometraje):
            raise HTTPException(409, {
                "mensaje": "El kilometraje es menor que al recibirla",
                "que_hacer": (f"Al recibirla marcaba "
                              f"{entrada_km.kilometraje:,}. Revisa el "
                              f"tablero: un odometro no cuenta para atras."),
                "al_recibir": entrada_km.kilometraje})

    puestos = {f.angulo.value for f in datos.fotos}
    faltan = [a for a in ANGULOS_MINIMOS if a not in puestos]
    if faltan:
        raise HTTPException(409, {
            "mensaje": "Faltan fotos de la unidad",
            "que_hacer": "Se necesitan los cuatro lados y el odometro. Una "
                         "revision a medias no sirve para discutir un golpe "
                         "despues, y sin el tablero el kilometraje es solo "
                         "un numero que alguien escribio.",
            "faltan": faltan})

    ahora = reloj.ahora_del_servicio(db, servicio)
    revision = m.RevisionUnidad(
        servicio_id=datos.servicio_id, vehiculo_id=datos.vehiculo_id,
        persona_id=usuario.persona_id, tipo=tipo,
        kilometraje=datos.kilometraje,
        combustible_octavos=datos.combustible_octavos,
        nota=datos.nota, firma=datos.firma,
        hubo_dano=bool(datos.hubo_dano),
        dano_tipo=datos.dano_tipo.value if datos.dano_tipo else None,
        dano_nota=(datos.dano_nota or "").strip() or None,
        lat=datos.lat, lon=datos.lon, momento=ahora)
    db.add(revision)
    db.flush()

    for f in datos.fotos:
        db.add(m.FotoRevision(
            revision_id=revision.id, angulo=f.angulo.value, imagen=f.imagen,
            nota=f.nota, momento=ahora,
            lat=f.lat if f.lat is not None else datos.lat,
            lon=f.lon if f.lon is not None else datos.lon))
    db.commit()
    db.refresh(revision)

    salida = {"resultado": "revision guardada", "revision_id": revision.id,
              "fotos": len(datos.fotos)}

    # Decision de Salvador (19 sep): un dano nuevo avisa al consultor y
    # nada mas. Ni alerta que cerrar, ni incidencia automatica --ni
    # siquiera de las que no quitan estrellas--: el sistema no clasifica
    # solo, eso es del consultor con visto bueno de direccion, y un
    # renglon que nadie juzgo en el expediente de alguien es algo que
    # despues hay que explicar.
    #
    # Y el dano que YA venia no avisa a nadie: quien lo declara no hizo
    # nada, se esta protegiendo. Frenarlo o alertarlo seria castigar
    # justo lo que queremos que haga.
    if revision.hubo_dano:
        salida["declaracion"] = {
            "tipo": revision.dano_tipo,
            "nota": revision.dano_nota,
            "lo_revisa_tu_consultor": tipo == "entrega",
        }

    # Al entregar, la diferencia de kilometraje sale sola: es el numero
    # que nadie apunta y del que despues todos se acuerdan distinto.
    if tipo == "entrega" and datos.kilometraje is not None:
        entrada = (db.query(m.RevisionUnidad)
                   .filter_by(servicio_id=datos.servicio_id,
                              vehiculo_id=datos.vehiculo_id,
                              tipo="recibe").first())
        if entrada and entrada.kilometraje is not None:
            salida["kilometros_recorridos"] = (datos.kilometraje
                                               - entrada.kilometraje)
    return salida

"""Lo que ve el equipo en la calle.

La app del personal de seguridad no navega: abre y ya esta viendo su dia.
Por eso aqui hay una sola puerta que contesta todo lo que esa pantalla
necesita —donde se presenta, a que hora, con quien va, que ya marco y
que sigue— en vez de cinco consultas que el telefono tendria que hacer
con media barra de senal.

Cada quien ve solo lo suyo. Eso no es una comodidad: la ficha del dia
trae el nombre del ejecutivo al que se protege.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app import models as m
from app import reloj
from app import tasksheet
from app import viaticos as viaticos_motor
from app.config import settings
from app.db import get_db
from app.operacion import MINUTOS_ANTES_PERMITIDOS, MINUTOS_DESPUES_PERMITIDOS
from app.presentacion import llegada_del_equipo

router = APIRouter(prefix="/campo", tags=["App del personal"])

CAMPO = auth.requiere(m.Rol.PERSONAL_SEGURIDAD)

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
    marcados = (db.query(m.Hito).filter_by(jornada_id=jornada.id)
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
    mias = {a.vehiculo_id for a in jornada.vehiculos if a.vehiculo}
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
        }

    return {
        "jornada_id": jornada.id,
        "servicio_id": servicio.id,
        "revision": revision,
        "fecha": jornada.fecha.isoformat(),
        "folio": servicio.folio,
        "cliente": servicio.cliente.nombre if servicio.cliente else None,
        "ejecutivo": servicio.ejecutivo_completo,
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
        "hoy": [f for f in fichas if f["fecha"] == hoy.isoformat()],
        "manana": [f for f in fichas if f["fecha"] != hoy.isoformat()],
        "proximos": [{
            "jornada_id": j.id,
            "fecha": j.fecha.isoformat(),
            "folio": j.equipo.servicio.folio,
            "cliente": (j.equipo.servicio.cliente.nombre
                        if j.equipo.servicio.cliente else None),
            "llegar_a_las": llegada_del_equipo(
                j.inicio_programado, j.vuelo_hora, j.vuelo_tipo)[0].isoformat(),
            "punto": j.origen_direccion,
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
        fila = por_servicio.setdefault(servicio.id, {
            "servicio_id": servicio.id, "folio": servicio.folio,
            "cliente": servicio.cliente.nombre if servicio.cliente else None,
            "moneda": v.moneda.value,
            "entregado": Decimal("0"), "comprobado": Decimal("0"),
            "por_comprobar": Decimal("0"),
            "dias": [], "limite": None, "vencido": False,
        })
        entregado = Decimal(str(v.monto_total or 0))
        comprobado = Decimal(str(v.monto_comprobado or 0))
        # Lo que todavia no sale como comprobado es lo que se le va a
        # pedir. Se dice por dia para que sepa cual le falta.
        fila["entregado"] += entregado
        fila["comprobado"] += comprobado
        fila["por_comprobar"] += max(
            entregado - comprobado - Decimal(str(v.monto_devuelto or 0)),
            Decimal("0"))
        if v.limite_comprobacion:
            actual = v.limite_comprobacion.isoformat()
            fila["limite"] = min(fila["limite"] or actual, actual)
            if v.limite_comprobacion < relojes.de_la_jornada(jornada):
                fila["vencido"] = True
        fila["dias"].append({
            "viatico_id": v.id,
            "fecha": jornada.fecha.isoformat(),
            "estatus": v.estatus.value,
            "entregado": entregado,
            "comprobado": comprobado,
            "comprobantes": len(v.comprobantes),
            "rechazados": len([c for c in v.comprobantes if c.rechazado]),
        })

    filas = sorted(por_servicio.values(),
                   key=lambda x: (not x["vencido"], x["limite"] or ""))
    for f in filas:
        f["dias"].sort(key=lambda d: d["fecha"])
    return {"servicios": filas,
            "total_por_comprobar": sum(f["por_comprobar"] for f in filas)}


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
        viatico, datos.monto, datos.concepto, datos.descripcion)
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

    return {"resultado": "comprobante registrado",
            "comprobado": str(viatico.monto_comprobado),
            "entregado": str(viatico.monto_total),
            "falta": str(max(Decimal(str(viatico.monto_total))
                             - Decimal(str(viatico.monto_comprobado)),
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

ANGULOS_MINIMOS = ("frente", "atras", "izquierdo", "derecho")


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
    firma: str | None = None
    lat: Decimal | None = None
    lon: Decimal | None = None
    fotos: list[FotoIn] = []


def _suya(db: Session, servicio_id: int, vehiculo_id: int,
          persona_id: int) -> m.Servicio:
    """Que esa persona traiga de verdad esa unidad en ese servicio."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    suyo = (db.query(m.AsignacionPersonal)
            .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == servicio_id,
                    m.AsignacionPersonal.persona_id == persona_id)
            .first())
    if not suyo:
        raise HTTPException(403, "No estas asignado a ese servicio")
    return servicio


def _revision(r: m.RevisionUnidad) -> dict:
    return {
        "id": r.id,
        "tipo": r.tipo.value if hasattr(r.tipo, "value") else r.tipo,
        "vehiculo_id": r.vehiculo_id,
        "placa": r.vehiculo.placa if r.vehiculo else None,
        "persona": r.persona.nombre if r.persona else None,
        "kilometraje": r.kilometraje,
        "combustible_octavos": r.combustible_octavos,
        "nota": r.nota,
        "momento": r.momento.isoformat(),
        "fotos": [{"angulo": f.angulo.value if hasattr(f.angulo, "value")
                              else f.angulo,
                   "imagen": f.imagen, "nota": f.nota}
                  for f in r.fotos],
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
            "recibida": _revision(suyas["recibe"]) if "recibe" in suyas else None,
            "entregada": (_revision(suyas["entrega"])
                          if "entrega" in suyas else None),
        })
    return {"servicio_id": servicio.id, "folio": servicio.folio,
            "unidades": salida}


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
    servicio = _suya(db, datos.servicio_id, datos.vehiculo_id,
                     usuario.persona_id)
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
                         "intentarlo. Los cuatro lados son los que "
                         "importan."})
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
            "que_hacer": "Se necesitan los cuatro lados. Una revision a "
                         "medias no sirve para discutir un golpe despues.",
            "faltan": faltan})

    ahora = reloj.ahora_del_servicio(db, servicio)
    revision = m.RevisionUnidad(
        servicio_id=datos.servicio_id, vehiculo_id=datos.vehiculo_id,
        persona_id=usuario.persona_id, tipo=tipo,
        kilometraje=datos.kilometraje,
        combustible_octavos=datos.combustible_octavos,
        nota=datos.nota, firma=datos.firma,
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

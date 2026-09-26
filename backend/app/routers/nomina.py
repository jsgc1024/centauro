"""Nominas: el corte semanal del personal de seguridad y el mensual de
las comisiones de los consultores (seccion 66).

El del personal se arma solo el lunes a las 7:00, queda listo a las
11:00 y se paga a mediodia; lo calcula y lo paga finanzas. El de las
comisiones lo autoriza direccion de operaciones cuando termina el mes y
lo paga finanzas. El consultor ve el suyo.
"""
from datetime import datetime

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth
from app import comisiones as motor_comisiones
from app import models as m
from app import nomina as motor
from app import reloj
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/nomina", tags=["Nomina del personal"])

# Armar el corte no es marcarlo pagado: lo segundo es el momento en que
# sale el dinero. Y el tabulador --lo que se paga por dia-- se cambia muy
# de vez en cuando y lo cambia otra gente.
FINANZAS = auth.puede("nomina.calcular")
PAGAR = auth.puede("nomina.pagar")
TABULADOR = auth.puede("nomina.tabulador")
LECTURA = auth.puede("nomina.ver")
COMISIONES = auth.puede("comisiones.ver")


# --------------------------------------------------------- el tabulador
#
# Lo que se le paga al personal por un dia de servicio. Dos tablas, una
# por tipo de operacion: un dia suelto que arranca en un aeropuerto y un
# dia de la misma persona en el mismo lugar no se pagan igual.

class RenglonComisionIn(BaseModel):
    perfil_id: int
    modalidad_id: int
    monto: Decimal = Decimal("0")
    monto_hora_extra: Decimal | None = None


class TabuladorComisionIn(BaseModel):
    pais_id: int
    tipo_servicio: m.TipoServicio
    renglones: list[RenglonComisionIn] = []


@router.get("/tabulador", summary="Lo que se paga por dia, por rol y modalidad")
def ver_tabulador(pais_id: int, db: Session = Depends(get_db),
                  _=Depends(LECTURA)):
    """Las dos tablas completas, con todos los cruces.

    Salen todos los roles contra todas las modalidades del pais, tengan
    monto o no: un cruce que falta es un dia que no se va a poder pagar,
    y verlo vacio es mas util que no verlo.
    """
    pais = db.get(m.Pais, pais_id)
    if not pais:
        raise HTTPException(404, f"No existe el pais {pais_id}")

    roles = (db.query(m.PerfilPersonal)
             .filter(m.PerfilPersonal.activo.is_(True))
             .order_by(m.PerfilPersonal.id).all())
    modalidades = (db.query(m.Modalidad).filter_by(pais_id=pais_id)
                   .order_by(m.Modalidad.id).all())
    puestos = {(c.tipo_servicio, c.perfil_id, c.modalidad_id): c
               for c in db.query(m.ComisionPersonal)
               .filter_by(pais_id=pais_id).all()}

    def tabla(tipo):
        # El implantado es siempre dia completo: es la misma persona en
        # el mismo lugar todos los dias del mes. Ofrecerle medio dia y
        # transfer es pedir numeros que nunca se van a usar, y peor:
        # hacen ver la tabla incompleta cuando esta completa.
        suyas = ([x for x in modalidades
                  if x.codigo == m.CodigoModalidad.FULL_DAY]
                 if tipo == m.TipoServicio.IMPLANTADO else modalidades)
        renglones = []
        for rol in roles:
            celdas = []
            for mod in suyas:
                fila = puestos.get((tipo, rol.id, mod.id))
                celdas.append({
                    "modalidad_id": mod.id,
                    "modalidad": mod.codigo.value,
                    "horas": float(mod.horas),
                    "aplica_horas_extra": mod.aplica_horas_extra,
                    "monto": str(fila.monto) if fila else None,
                    "monto_hora_extra": (str(fila.monto_hora_extra)
                                         if fila and fila.monto_hora_extra
                                         is not None else None),
                })
            renglones.append({"perfil_id": rol.id, "rol": rol.nombre,
                              "codigo": rol.codigo, "celdas": celdas})
        faltantes = sum(1 for r in renglones for c in r["celdas"]
                        if c["monto"] is None)
        return {"tipo_servicio": tipo.value, "renglones": renglones,
                "sin_cargar": faltantes,
                "modalidades": [{"id": x.id, "codigo": x.codigo.value,
                                 "horas": float(x.horas),
                                 "aplica_horas_extra": x.aplica_horas_extra}
                                for x in suyas]}

    return {
        "pais_id": pais_id, "pais": pais.nombre,
        "moneda": pais.moneda_local.value,
        "modalidades": [{"id": x.id, "codigo": x.codigo.value,
                         "horas": float(x.horas),
                         "aplica_horas_extra": x.aplica_horas_extra}
                        for x in modalidades],
        "eventual": tabla(m.TipoServicio.EVENTUAL),
        "implantado": tabla(m.TipoServicio.IMPLANTADO),
    }


@router.put("/tabulador", summary="Guardar una de las dos tablas")
def guardar_tabulador(datos: TabuladorComisionIn,
                      db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(TABULADOR)):
    """Reescribe los montos de esa tabla.

    Pide su propia actividad desde la seccion 73. Pedia la de armar el
    corte, que por rol la tienen los mismos; con puestos ya no: Nomina
    arma el corte y no fija lo que se paga.

    Un monto en cero se guarda como cero y no se borra el renglon: cero
    es una decision ("este rol no cobra en esta modalidad") y vacio es
    un dato que falta. El corte de nomina los trata distinto.
    """
    pais = db.get(m.Pais, datos.pais_id)
    if not pais:
        raise HTTPException(404, f"No existe el pais {datos.pais_id}")

    tocados = 0
    for r in datos.renglones:
        fila = (db.query(m.ComisionPersonal)
                .filter_by(pais_id=datos.pais_id,
                           tipo_servicio=datos.tipo_servicio,
                           perfil_id=r.perfil_id,
                           modalidad_id=r.modalidad_id).first())
        if not fila:
            fila = m.ComisionPersonal(
                pais_id=datos.pais_id, tipo_servicio=datos.tipo_servicio,
                perfil_id=r.perfil_id, modalidad_id=r.modalidad_id,
                moneda=pais.moneda_local, monto=0)
            db.add(fila)
        fila.monto = r.monto
        fila.monto_hora_extra = r.monto_hora_extra
        tocados += 1

    db.commit()
    return {"resultado": "tabulador guardado",
            "tipo_servicio": datos.tipo_servicio.value,
            "renglones": tocados}


@router.post("/calcular", summary="Armar el corte de la semana")
def calcular(datos: s.CalcularNominaIn, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(FINANZAS)):
    """Se puede correr las veces que haga falta mientras no se pague y
    hasta las 11:00 del lunes (seccion 66). El reloj lo arma solo a las
    7:00; esto es el "Recalcular" de finanzas."""
    resultado = motor.calcular(db, datos.pais_id, datos.fecha_corte,
                               usuario.persona_id)
    db.commit()
    return resultado


# Estas van antes de "/{nomina_id}": FastAPI se queda con la primera ruta
# que coincide, y "semana" no es un numero.

@router.get("/semana", summary="El corte de este lunes, o lo que va para el que sigue")
def semana(pais_id: int, ahora: datetime | None = None,
           db: Session = Depends(get_db), _=Depends(LECTURA)):
    """La pestana del personal: el corte con lo que entra y por que, lo
    que todavia no entra y el horario del lunes. `ahora` solo mueve el
    reloj en las pruebas."""
    return motor.semana(db, pais_id, reloj.de_prueba(ahora))


@router.get("/implantados", summary="El corte general del mes de cada implantado")
def implantados(pais_id: int, ahora: datetime | None = None,
                db: Session = Depends(get_db), _=Depends(LECTURA)):
    """Lo pagado cada semana contra lo que corresponde, mes por mes, y si
    el mes ya quedo cerrado."""
    if not db.get(m.Pais, pais_id):
        raise HTTPException(404, f"No existe el pais {pais_id}")
    return {"meses": motor.meses_implantado(db, pais_id,
                                            reloj.de_prueba(ahora))}


# --------------------------------------------------------- comisiones

@router.get("/comisiones", summary="El corte de comisiones del mes")
def comisiones(pais_id: int, anio: int, mes: int,
               ahora: datetime | None = None,
               db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(COMISIONES)):
    """Lo que se le paga a cada consultor, lo que no y por que, sus
    diferencias y lo que viene en camino. El consultor ve el suyo."""
    return motor_comisiones.corte_del_mes(db, pais_id, anio, mes, usuario,
                                          reloj.de_prueba(ahora))


@router.post("/comisiones/visto-bueno",
             summary="Dar el visto bueno al corte de comisiones del mes")
def visto_bueno_comisiones(datos: s.VistoBuenoComisionesIn,
                           ahora: datetime | None = None,
                           db: Session = Depends(get_db),
                           usuario: m.Usuario = Depends(
                               auth.puede("comisiones.visto_bueno"))):
    """Con el mes terminado. Deja fijo lo de cada consultor; si alguno
    queda debajo de cero, cobra cero y el resto pasa al mes siguiente."""
    resultado = motor_comisiones.visto_bueno(
        db, datos.pais_id, datos.anio, datos.mes, usuario,
        reloj.de_prueba(ahora))
    db.commit()
    return resultado


@router.post("/comisiones/pagos/{pago_id}/pagar",
             summary="Registrar la transferencia de un consultor")
def pagar_comision(pago_id: int, datos: s.PagoComisionIn,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(
                       auth.puede("comisiones.pagar"))):
    resultado = motor_comisiones.pagar(db, pago_id, datos.referencia, usuario)
    db.commit()
    return resultado


@router.post("/comisiones/diferencias", status_code=201,
             summary="Registrar una diferencia en la comision de un consultor")
def diferencia_comision(datos: s.DiferenciaComisionIn,
                        ahora: datetime | None = None,
                        db: Session = Depends(get_db),
                        usuario: m.Usuario = Depends(
                            auth.puede("comisiones.ajustar"))):
    """Con signo: negativo es descuento. Entra en el mes que siga
    abierto."""
    ajuste = motor_comisiones.diferencia_a_mano(
        db, datos.pais_id, datos.consultor_id, datos.monto, datos.motivo,
        usuario, datos.servicio_id, reloj.de_prueba(ahora))
    db.commit()
    return {"ajuste_id": ajuste.id, "anio": ajuste.anio, "mes": ajuste.mes,
            "monto": ajuste.monto}


@router.get("/{nomina_id}", summary="Ver el detalle del corte")
def ver(nomina_id: int, db: Session = Depends(get_db), _=Depends(LECTURA)):
    n = db.get(m.NominaSemanal, nomina_id)
    if not n:
        raise HTTPException(404, f"No existe la nomina {nomina_id}")
    # El corte se paga por dia y por rol, asi que se suma por rol: es la
    # cuenta que la direccion va a pedir —cuanto se fue en conductores y
    # cuanto en coordinadores— y no se puede sacar de un total plano.
    por_rol: dict = {}
    dias_totales = 0
    for r in n.renglones:
        for c in r.conceptos:
            # Solo los dias: un ajuste o el renglon del saldo en contra no
            # son un dia de nadie.
            if not c.jornada_id:
                continue
            dias_totales += 1
            clave = c.rol_id or 0
            fila = por_rol.setdefault(clave, {
                "rol_id": c.rol_id,
                "rol": c.rol.nombre if c.rol else "Sin rol",
                "dias": 0, "monto": Decimal("0")})
            fila["dias"] += 1
            fila["monto"] += Decimal(str(c.monto))

    # Lo mismo que la pestana del lunes: de donde sale cada peso, por
    # persona y el saldo en contra que pasa al siguiente (seccion 66).
    detalle = motor.armar_detalle(db, motor.filas_del_corte(db, n),
                                  n.fecha_corte)
    return {
        **detalle,
        **motor.ficha(db, n),
        "id": n.id,
        "fecha_corte": n.fecha_corte.isoformat(),
        "moneda": n.moneda.value,
        "estatus": n.estatus.value,
        "total": n.total,
        "dias_pagados": dias_totales,
        "pagada_en": n.pagada_en.isoformat() if n.pagada_en else None,
        "por_rol": sorted(por_rol.values(), key=lambda x: -x["monto"]),
        "renglones": [{
            "persona_id": r.persona_id,
            "persona": r.persona.nombre,
            "total": r.total,
            "dias": len([c for c in r.conceptos if c.jornada_id]),
            "conceptos": [{"descripcion": c.descripcion, "monto": c.monto,
                           "jornada_id": c.jornada_id,
                           "rol": c.rol.nombre if c.rol else None,
                           "horas_extra": c.horas_extra,
                           "factor_festivo": c.factor_festivo,
                           "es_ajuste": c.ajuste_id is not None}
                          for c in r.conceptos],
        } for r in sorted(n.renglones, key=lambda x: x.persona.nombre)],
    }


@router.get("", summary="Listar cortes")
def listar(pais_id: int | None = None, db: Session = Depends(get_db),
           _=Depends(LECTURA)):
    consulta = db.query(m.NominaSemanal)
    if pais_id:
        consulta = consulta.filter_by(pais_id=pais_id)
    filas = consulta.order_by(m.NominaSemanal.fecha_corte.desc()).all()
    return [{"id": n.id, "fecha_corte": n.fecha_corte.isoformat(),
             "estatus": n.estatus.value, "total": n.total,
             "estado": motor.ficha(db, n)["estado"],
             "moneda": n.moneda.value, "personas": len(n.renglones)}
            for n in filas]


@router.delete("/{nomina_id}", summary="Tirar un borrador de corte")
def descartar(nomina_id: int, db: Session = Depends(get_db),
              _=Depends(FINANZAS)):
    """Solo mientras no se haya pagado.

    Hace falta porque un borrador aparta: mientras exista, sus jornadas
    y sus ajustes no entran a ningun otro corte. Sin esto, correr el
    calculo "para ver como queda" dejaba a esa gente sin cobrar en el
    corte de verdad, y nada lo avisaba.
    """
    resultado = motor.descartar(db, nomina_id)
    db.commit()
    return resultado


@router.post("/{nomina_id}/pagar", summary="Marcar el corte como pagado")
def pagar(nomina_id: int, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(PAGAR)):
    """Despues de esto el corte ya no se recalcula: solo se corrige por ajuste."""
    resultado = motor.pagar(db, nomina_id, usuario.persona_id)
    db.commit()
    return resultado


CONCEPTO_EN_PALABRAS = {
    motor.AJUSTE_CORRECCION: "Correccion del pago del dia",
    motor.AJUSTE_VIATICO: "Viaticos sin comprobar",
    motor.AJUSTE_MANUAL: "Capturado a mano",
    motor.AJUSTE_SALDO: "Saldo en contra de un corte anterior",
}


@router.get("/ajustes/pendientes", summary="Lo que entrara al proximo corte")
def ajustes_pendientes(pais_id: int, db: Session = Depends(get_db),
                       _=Depends(LECTURA)):
    filas = (db.query(m.AjusteNomina)
             .filter_by(pais_id=pais_id, aplicado_en_nomina_id=None)
             .order_by(m.AjusteNomina.creado_en).all())
    return [{"id": a.id, "persona": a.persona.nombre, "monto": a.monto,
             "motivo": a.motivo,
             "concepto": a.concepto,
             "de_que": CONCEPTO_EN_PALABRAS.get(a.concepto, a.concepto),
             "sentido": "a favor" if a.monto >= 0 else "descuento"}
            for a in filas]


@router.post("/ajustes", status_code=201,
             summary="Registrar un ajuste a mano")
def crear_ajuste(datos: s.AjusteNominaIn, db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(FINANZAS)):
    """Para lo que el sistema no puede deducir solo. Monto con signo:
    positivo si se le debe, negativo si hay que descontarle."""
    persona = db.get(m.Persona, datos.persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {datos.persona_id}")

    # La correccion de un dia no se teclea: la calcula el motor
    # comparando lo que ya salio contra lo que corresponde segun la
    # tarifa. Un ajuste capturado con ese concepto se mete en esa
    # comparacion y el sistema lo lee como un pago de mas, asi que en la
    # siguiente revision genera otro ajuste para quitarlo. Un bono
    # acordado a mano se desharia solo, sin que nadie entienda por que.
    if datos.concepto == motor.AJUSTE_CORRECCION:
        raise HTTPException(400, {
            "mensaje": "Ese concepto lo pone el sistema, no se captura",
            "que_hacer": "Lo que capturas a mano va como 'manual'. Si lo "
                         "que quieres es corregir lo que se pago por un "
                         "dia, eso sale solo al revisar diferencias: "
                         "corrige el dia y vuelve a mandarlo a finanzas."})

    ajuste = m.AjusteNomina(**datos.model_dump(),
                            creado_por_id=usuario.persona_id)
    db.add(ajuste)
    db.commit()
    db.refresh(ajuste)
    return {"id": ajuste.id, "persona": persona.nombre, "monto": ajuste.monto,
            "motivo": ajuste.motivo,
            "nota": "Entra en el proximo corte semanal"}


@router.post("/servicio/{servicio_id}/revisar-diferencias",
             summary="Comparar lo pagado contra lo que corresponde hoy")
def revisar(servicio_id: int, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(FINANZAS)):
    """Corre sola al enviar a finanzas. Esta ruta es para volver a correrla."""
    resultado = motor.diferencias_del_servicio(db, servicio_id,
                                               usuario.persona_id)
    db.commit()
    return resultado

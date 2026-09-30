# -*- coding: utf-8 -*-
"""Cambiar al consultor titular de un servicio (decision 13, seccion 105).

Vacaciones largas, cambio de cartera o una baja: hasta hoy el titular
se ponia en el alta y no habia forma de cambiarlo (hallazgo 14 de la
revision del 28 de septiembre). Todo lo que hacia quien lo cubria quedaba
«en cobertura» avisandole a alguien que no estaba, y un servicio sin
titular no generaba comision ni tenia nivel 1 de escalacion.

Lo que Salvador decidio el 29 de septiembre:

  * Lo cambia direccion de operaciones (y direccion general, que hereda),
    desde la ficha del eventual y del implantado, a otro consultor con
    acceso abierto. Con motivo, que queda en la bitacora.
  * Se les avisa a los dos, al telefono y por correo.
  * Desde ese momento los avisos del servicio, los plazos del cierre y la
    comision son del nuevo. La comision va COMPLETA al nuevo: no se
    reparte. Nada de esto se escribe aqui: `cierre.py`, `comisiones.py`
    y la escalacion del task sheet leen `servicio.consultor_id` en el
    momento de avisar, generar o armar, asi que basta con cambiarlo.
  * Lo cerrado y pagado al anterior no se toca: un servicio cerrado ya
    no cambia de titular, y una comision ya generada no se toca porque
    solo se genera al cerrar.
  * Si el cierre ya esta abierto y el plazo corre, el plazo sigue igual
    --es del servicio, no de la persona-- pero el aviso de vencimiento
    va al nuevo.
"""
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import accesos, auditoria, correo_html
from app import models as m
from app import textos_aviso as ta

registro = logging.getLogger("centauro")


def _pantalla(servicio: m.Servicio) -> str:
    """Donde se abre el servicio en la consola: el consultor trabaja ahi,
    no en la app de campo."""
    if servicio.tipo == m.TipoServicio.IMPLANTADO:
        return f"/consola/#/implantado/{servicio.id}"
    return f"/consola/#/servicio/{servicio.id}"


def _correo(db: Session, servicio: m.Servicio, para: m.Persona,
            asunto: str, cuerpo: str, quien: str, motivo: str,
            anterior: m.Persona | None, nuevo: m.Persona) -> bool:
    """Un correo a uno de los dos, en el idioma del pais del servicio,
    como los demas avisos a la gente de la casa. Solo escribe; quien
    llama guarda."""
    if not para.correo:
        return False
    lengua = ta.idioma_de(db, servicio, m.Destinatario.CONSULTOR)
    cliente = servicio.cliente.nombre if servicio.cliente else ""
    datos = dict(folio=servicio.folio, cliente=cliente, quien=quien,
                 nuevo=nuevo.nombre)
    pares = [(ta.t(lengua, "tit_servicio"), f"{servicio.folio} · {cliente}"),
             (ta.t(lengua, "tit_nuevo"), nuevo.nombre, nuevo.telefono),
             (ta.t(lengua, "tit_anterior"),
              anterior.nombre if anterior else None),
             (ta.t(lengua, "tit_quien"), quien),
             (ta.t(lengua, "tit_motivo"), motivo)]
    db.add(m.Notificacion(
        servicio_id=servicio.id,
        destinatario=m.Destinatario.CONSULTOR, canal=m.Canal.CORREO,
        correo=para.correo, idioma=lengua,
        asunto=ta.t(lengua, asunto, **datos)[:200],
        cuerpo=ta.t(lengua, cuerpo, **datos)[:2000],
        datos=correo_html.guardar_datos(pares),
        enlace_seguimiento=_pantalla(servicio)))
    return True


def hojas_publicadas(db: Session, servicio: m.Servicio) -> int:
    """Cuantos equipos del eventual tienen hoja publicada. La hoja lleva
    al titular como nivel 1 de la escalacion y es una foto: con otro
    titular hay que volver a publicarla (como con un cambio de persona
    para otro dia, seccion 101). La del implantado es la del acuerdo y
    no lleva escalacion por titular."""
    if servicio.tipo == m.TipoServicio.IMPLANTADO:
        return 0
    return (db.query(m.TaskSheet.equipo_id)
            .filter(m.TaskSheet.servicio_id == servicio.id,
                    m.TaskSheet.estatus == m.EstatusTaskSheet.PUBLICADO)
            .distinct().count())


def cambiar(db: Session, servicio: m.Servicio, consultor_id: int,
            motivo: str, usuario: m.Usuario) -> dict:
    """Le pone otro titular al servicio y avisa a los dos. Solo escribe;
    quien llama guarda."""
    motivo = " ".join((motivo or "").split())
    if not motivo:
        raise HTTPException(400, {
            "mensaje": "Falta el motivo del cambio de titular.",
            "que_hacer": "Escribe por qué cambia: es lo que queda en la "
                         "bitácora y lo que leen los dos consultores.",
        })
    if not accesos.servicio_sigue_vivo(db, servicio):
        raise HTTPException(409, {
            "mensaje": (f"El servicio {servicio.folio} ya está "
                        f"{servicio.estatus.value.replace('_', ' ')}: ya no "
                        "cambia de titular."),
            "que_hacer": "Lo cerrado y pagado se queda con el titular que lo "
                         "cerró. Si hace falta corregir su comisión, finanzas "
                         "registra una diferencia en Nóminas.",
        })
    if servicio.consultor_id == consultor_id:
        raise HTTPException(409, {
            "mensaje": "Esa persona ya es el consultor titular de este servicio.",
            "que_hacer": "Escoge a otro consultor de la lista.",
        })
    nuevo = db.get(m.Persona, consultor_id)
    if nuevo is None or not accesos.lleva_servicios(db, consultor_id):
        raise HTTPException(409, {
            "mensaje": "El titular tiene que ser un consultor con acceso abierto.",
            "que_hacer": "Escoge a uno de la lista. Si falta alguien, se le "
                         "da acceso de consultor en Accesos.",
            "consultor_id": consultor_id,
        })

    anterior = (db.get(m.Persona, servicio.consultor_id)
                if servicio.consultor_id else None)
    servicio.consultor_id = nuevo.id
    quien = usuario.persona.nombre if usuario.persona else usuario.correo
    de = anterior.nombre if anterior else "sin asignar"
    # La bitacora del servicio: quien cambio a quien y por que. Va despues
    # del cambio a proposito, para que el renglon quede a nombre del
    # titular nuevo y no salga como cobertura de nadie.
    auditoria.registrar(db, usuario, servicio, "cambio de titular",
                        f"{de} -> {nuevo.nombre}: {motivo}")

    _correo(db, servicio, nuevo, "tit_entra_asunto", "tit_entra_cuerpo",
            quien, motivo, anterior, nuevo)
    if anterior is not None:
        _correo(db, servicio, anterior, "tit_sale_asunto", "tit_sale_cuerpo",
                quien, motivo, anterior, nuevo)
    from app import push
    try:
        push.avisar_cambio_de_titular(db, servicio, anterior, nuevo, quien,
                                      motivo)
    except Exception:                         # noqa: BLE001
        # Un aviso que no sale no deshace el cambio: la bitacora y el
        # correo ya quedaron.
        registro.exception("no se pudo avisar el cambio de titular de %s",
                           servicio.folio)

    hojas = hojas_publicadas(db, servicio)
    return {
        "resultado": "titular cambiado",
        "servicio_id": servicio.id, "folio": servicio.folio,
        "anterior": ({"id": anterior.id, "nombre": anterior.nombre}
                     if anterior else None),
        "nuevo": {"id": nuevo.id, "nombre": nuevo.nombre},
        # La hoja publicada trae al titular anterior como nivel 1 de la
        # escalacion: la pantalla dice que hay que volver a publicarla.
        "hojas_por_republicar": hojas,
    }

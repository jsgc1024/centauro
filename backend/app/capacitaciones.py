"""Los certificados del personal, y el reloj que los vigila.

`vigencia_hasta` existia desde hacia meses y nada la miraba. Una
certificacion vencida no es una certificacion, y el dia que importa
--cuando el cliente pregunta quien va a cuidar a su ejecutivo-- nadie va
a revisar la fecha.

De este padron sale tambien si alguien esta al corriente para el bono y
para su calificacion: ver `bonos.medir_capacitacion`.
"""
from datetime import date

from sqlalchemy.orm import Session

from app import models as m
from app import textos_aviso as ta

# Un mes alcanza para reinscribir a alguien en un curso sin sacarlo de
# servicios. El dia cero es el ultimo recordatorio, no el primero.
DIAS_DE_AVISO = (30, 0)


def por_vencer(db: Session, persona_id: int, hoy: date | None = None) -> dict:
    """El semaforo de una persona: al corriente, por vencer o vencido.

    Devuelve `aplica: False` cuando no tiene ningun certificado
    registrado. Eso NO es reprobado --es un padron sin llenar-- y asi lo
    trata el bono.
    """
    hoy = hoy or date.today()
    cursos = (db.query(m.Capacitacion)
              .filter_by(persona_id=persona_id, activo=True).all())
    if not cursos:
        return {"aplica": False, "estado": "sin_registro", "cursos": 0}

    vencidos = [c for c in cursos
                if c.vigencia_hasta and c.vigencia_hasta < hoy]
    if vencidos:
        peor = min(vencidos, key=lambda c: c.vigencia_hasta)
        return {"aplica": True, "estado": "vencido", "cursos": len(cursos),
                "curso": peor.nombre, "fecha": peor.vigencia_hasta,
                "dias": (peor.vigencia_hasta - hoy).days}

    con_fecha = [c for c in cursos if c.vigencia_hasta]
    if con_fecha:
        proximo = min(con_fecha, key=lambda c: c.vigencia_hasta)
        dias = (proximo.vigencia_hasta - hoy).days
        if dias <= max(DIAS_DE_AVISO):
            return {"aplica": True, "estado": "por_vencer",
                    "cursos": len(cursos), "curso": proximo.nombre,
                    "fecha": proximo.vigencia_hasta, "dias": dias}
    return {"aplica": True, "estado": "al_corriente", "cursos": len(cursos)}


def _quien_lo_gestiona(db: Session) -> m.Persona | None:
    """Recursos Humanos, y si todavia no hay, direccion de operaciones.

    Un certificado no es de un consultor: una persona no tiene consultor
    fijo, va con el que le toque cada dia. Reinscribir a alguien en un
    curso es de quien lleva a la gente.
    """
    for rol in (m.Rol.RECURSOS_HUMANOS, m.Rol.DIRECTOR_OPERACIONES):
        usuario = (db.query(m.Usuario)
                   .filter(m.Usuario.rol == rol, m.Usuario.activo.is_(True))
                   .order_by(m.Usuario.id).first())
        if usuario and usuario.persona:
            return usuario.persona
    return None


def revisar_vencimientos(db: Session, hoy: date | None = None) -> dict:
    """Avisa de lo que vence en treinta dias y de lo que vence hoy.

    Dos avisos y se acaba. El que no reinscribio a nadie en un mes no lo
    va a hacer porque le llegue un tercer correo, y el padron ya lo dice
    en la pantalla todos los dias.
    """
    from app import correo_html, push

    hoy = hoy or date.today()
    gestor = _quien_lo_gestiona(db)
    avisados = []

    cursos = (db.query(m.Capacitacion)
              .filter(m.Capacitacion.activo.is_(True),
                      m.Capacitacion.vigencia_hasta.isnot(None)).all())
    for curso in cursos:
        dias = (curso.vigencia_hasta - hoy).days
        if dias not in DIAS_DE_AVISO:
            continue
        if curso.avisado_en == hoy:
            continue
        persona = curso.persona
        if not persona or not persona.activo:
            continue

        vence_hoy = dias == 0
        push.avisar(
            db, persona.id,
            titulo=("Tu certificado vence hoy" if vence_hoy
                    else f"Tu certificado vence en {dias} dias"),
            cuerpo=(f"{curso.nombre}"
                    + (f" ({curso.institucion})" if curso.institucion else "")
                    + f". Vence el {curso.vigencia_hasta:%d/%m/%Y}."),
            url="/app/#/yo",
            etiqueta="certificado", urgente=vence_hoy)

        if gestor and gestor.correo:
            # La gente de la casa lee en el idioma de su pais, que es la
            # misma regla de la app de campo. `idioma_de` no sirve aqui:
            # pide un servicio, y un certificado no cuelga de ninguno.
            pais = db.get(m.Pais, gestor.plaza.pais_id) if gestor.plaza else None
            lengua = pais.idioma if pais else "es"
            db.add(m.Notificacion(
                destinatario=m.Destinatario.COLABORADOR,
                canal=m.Canal.CORREO, correo=gestor.correo, idioma=lengua,
                asunto=ta.t(lengua,
                            "cap_vence_hoy" if vence_hoy else "cap_vence_pronto",
                            quien=persona.nombre, curso=curso.nombre,
                            dias=dias),
                cuerpo=ta.t(lengua, "cap_vence_cuerpo", quien=persona.nombre),
                datos=correo_html.guardar_datos([
                    (ta.t(lengua, "cap_quien"), persona.nombre,
                     persona.telefono),
                    (ta.t(lengua, "cap_curso"), curso.nombre),
                    (ta.t(lengua, "cap_institucion"), curso.institucion or "-"),
                    (ta.t(lengua, "cap_vence"),
                     f"{curso.vigencia_hasta:%d/%m/%Y}"),
                ])))

        curso.avisado_en = hoy
        avisados.append({"persona": persona.nombre, "curso": curso.nombre,
                         "dias": dias})

    db.commit()
    return {"avisados": len(avisados), "detalle": avisados}

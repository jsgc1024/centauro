"""Encuestas de satisfaccion.

Contestarlas es publico: el ejecutivo y el solicitante no tienen usuario
en el sistema, entran por el enlace del correo. Verlas y clasificarlas
no lo es.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import auditoria, auth
from app import encuestas as motor
from app import encuestas_html
from app import models as m
from app import schemas as s
from app.db import get_db
from app.textos import IDIOMAS

router = APIRouter(prefix="/encuestas", tags=["Encuestas"])

CONSULTOR = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES)
LECTURA = auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL, m.Rol.FINANZAS,
                        m.Rol.DIRECTOR_OPERACIONES)


@router.post("/servicio/{servicio_id}/enviar", status_code=201,
             summary="Mandar las encuestas del servicio")
def enviar(servicio_id: int, idioma: str = "en", db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(CONSULTOR)):
    """Una al ejecutivo por el servicio, otra al solicitante por el consultor."""
    if idioma not in IDIOMAS:
        raise HTTPException(400, f"Idioma no soportado: {idioma}")
    creadas = motor.generar(db, servicio_id, idioma)
    if not creadas:
        db.commit()
        return {"resultado": "sin cambios",
                "nota": "Ya se habian enviado, o el servicio no tiene correos"}
    servicio = db.get(m.Servicio, servicio_id)
    auditoria.registrar(db, usuario, servicio, "enviar encuestas",
                        ", ".join(e.tipo.value for e in creadas))
    db.commit()
    return {"resultado": "enviadas",
            "encuestas": [{"tipo": e.tipo.value, "para": e.destinatario_correo,
                           "enlace": f"/encuestas/pagina/{e.token}",
                           "expira_en": e.expira_en.isoformat()}
                          for e in creadas]}


# ------------------------------------------------------------------ publico

@router.get("/pagina/{token}", response_class=HTMLResponse,
            include_in_schema=False)
def pagina(token: str, db: Session = Depends(get_db)):
    """La pagina que abre el cliente desde el correo. Sin sesion."""
    try:
        encuesta = motor.por_token(db, token)
    except HTTPException as e:
        texto = e.detail if isinstance(e.detail, str) else "Encuesta no disponible"
        return HTMLResponse(encuestas_html.pagina_cerrada(texto),
                            status_code=e.status_code)
    return HTMLResponse(encuestas_html.pagina(encuesta, motor.formulario(encuesta)))


@router.get("/correo/{encuesta_id}", response_class=HTMLResponse,
            summary="Ver el correo tal como le llega al cliente")
def ver_correo(encuesta_id: int, db: Session = Depends(get_db),
               _=Depends(LECTURA)):
    encuesta = db.get(m.Encuesta, encuesta_id)
    if not encuesta:
        raise HTTPException(404, f"No existe la encuesta {encuesta_id}")
    enlace = f"/encuestas/pagina/{encuesta.token}"
    return HTMLResponse(encuestas_html.correo(encuesta, enlace))


@router.get("/publica/{token}", summary="Abrir la encuesta desde el correo")
def abrir(token: str, db: Session = Depends(get_db)):
    """Sin sesion: el ejecutivo no es usuario del sistema."""
    return motor.formulario(motor.por_token(db, token))


@router.post("/publica/{token}", summary="Contestar la encuesta")
def contestar(token: str, datos: s.RespuestaEncuestaIn,
              db: Session = Depends(get_db)):
    resultado = motor.responder(db, token, datos.calificacion, datos.respuestas)
    db.commit()
    return resultado


# ------------------------------------------------------------------ interno

@router.get("/servicio/{servicio_id}", summary="Ver las encuestas del servicio")
def del_servicio(servicio_id: int, db: Session = Depends(get_db),
                 _=Depends(LECTURA)):
    filas = db.query(m.Encuesta).filter_by(servicio_id=servicio_id).all()
    return [_detalle(e) for e in filas]


@router.get("/por-clasificar", summary="Malas calificaciones sin revisar")
def por_clasificar(db: Session = Depends(get_db), _=Depends(LECTURA)):
    """Una mala calificacion no castiga sola: el consultor la revisa y
    decide si hubo incidencia."""
    filas = (db.query(m.Encuesta)
             .filter_by(requiere_clasificacion=True, incidencia_id=None)
             .filter(m.Encuesta.clasificada_en.is_(None))
             .order_by(m.Encuesta.respondida_en).all())
    return [_detalle(e) for e in filas]


@router.post("/{encuesta_id}/clasificar",
             summary="El consultor revisa una mala calificacion")
def clasificar(encuesta_id: int, datos: s.ClasificarEncuestaIn,
               db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(CONSULTOR)):
    """Si amerita incidencia se liga la que corresponda, que a su vez
    necesita el visto bueno del director de operaciones para pegarle al
    bono. Si no amerita, se cierra con la nota y no pasa nada."""
    encuesta = db.get(m.Encuesta, encuesta_id)
    if not encuesta:
        raise HTTPException(404, f"No existe la encuesta {encuesta_id}")
    if encuesta.estatus != m.EstatusEncuesta.RESPONDIDA:
        raise HTTPException(409, "Esa encuesta todavia no se contesta")

    if datos.incidencia_id:
        incidencia = db.get(m.Incidencia, datos.incidencia_id)
        if not incidencia:
            raise HTTPException(404, f"No existe la incidencia {datos.incidencia_id}")
        encuesta.incidencia_id = incidencia.id

    encuesta.nota_clasificacion = datos.nota
    encuesta.clasificada_en = datetime.now()
    auditoria.registrar(db, usuario, encuesta.servicio, "clasificar encuesta",
                        ("ligada a incidencia" if datos.incidencia_id
                         else "sin incidencia") + f": {datos.nota}")
    db.commit()
    return {"resultado": "clasificada", "encuesta_id": encuesta.id,
            "incidencia_id": encuesta.incidencia_id,
            "nota": ("La incidencia todavia necesita visto bueno del director "
                     "de operaciones para afectar el bono"
                     if datos.incidencia_id else
                     "No afecta estrellas ni comision")}


@router.get("/{encuesta_id}/enlace",
            summary="Recuperar el enlace para reenviarlo")
def enlace(encuesta_id: int, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(CONSULTOR)):
    """El token no sale en los listados: con el se puede contestar la
    encuesta. Recuperarlo es un acto deliberado y queda en bitacora."""
    encuesta = db.get(m.Encuesta, encuesta_id)
    if not encuesta:
        raise HTTPException(404, f"No existe la encuesta {encuesta_id}")
    if encuesta.estatus == m.EstatusEncuesta.RESPONDIDA:
        raise HTTPException(409, "Esa encuesta ya fue contestada")
    auditoria.registrar(db, usuario, encuesta.servicio, "recuperar enlace de encuesta",
                        f"{encuesta.tipo.value} para {encuesta.destinatario_correo}")
    db.commit()
    return {"encuesta_id": encuesta.id, "tipo": encuesta.tipo.value,
            "para": encuesta.destinatario_correo,
            "enlace": f"/encuestas/pagina/{encuesta.token}",
            "expira_en": encuesta.expira_en.isoformat()}


@router.get("/resumen/persona/{persona_id}",
            summary="Como lo califican los ejecutivos")
def resumen_persona(persona_id: int, db: Session = Depends(get_db),
                    _=Depends(LECTURA)):
    return motor.resumen_de_persona(db, persona_id)


@router.get("/resumen/consultor/{consultor_id}",
            summary="Como lo califican los solicitantes")
def resumen_consultor(consultor_id: int, db: Session = Depends(get_db),
                      _=Depends(LECTURA)):
    return motor.resumen_de_consultor(db, consultor_id)


def _detalle(e: m.Encuesta) -> dict:
    return {
        "id": e.id,
        "servicio_id": e.servicio_id,
        "tipo": e.tipo.value,
        "para": e.destinatario_nombre or e.destinatario_correo,
        "estatus": e.estatus.value,
        "calificacion": e.calificacion,
        "respondida_en": e.respondida_en.isoformat() if e.respondida_en else None,
        "requiere_clasificacion": e.requiere_clasificacion,
        "clasificada": e.clasificada_en is not None,
        "incidencia_id": e.incidencia_id,
        "respuestas": [{"pregunta": r.pregunta, "valor": r.valor,
                        "texto": r.texto} for r in e.respuestas],
    }

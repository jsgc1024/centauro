"""Encuestas de satisfaccion.

Contestarlas es publico: el ejecutivo y el solicitante no tienen usuario
en el sistema, entran por el enlace del correo. Verlas y clasificarlas
no lo es.
"""
from datetime import datetime, timedelta, timezone

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

ENVIAR = auth.puede("encuestas.enviar")
CLASIFICAR = auth.puede("encuestas.clasificar")
LECTURA = auth.puede("encuestas.ver")


@router.post("/servicio/{servicio_id}/enviar", status_code=201,
             summary="Mandar las encuestas del servicio")
def enviar(servicio_id: int, idioma: str | None = None,
           db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(ENVIAR)):
    """Una al ejecutivo por el servicio, otra al solicitante por el consultor.

    Sin idioma, cada una sale en el de quien la contesta. Ver
    `encuestas.generar`.
    """
    if idioma and idioma not in IDIOMAS:
        raise HTTPException(400, f"Idioma no soportado: {idioma}")
    creadas = motor.generar(db, servicio_id, idioma)
    if not creadas:
        db.commit()
        return {"resultado": "sin cambios",
                "nota": "Ya se habian enviado, o el servicio no tiene correos",
                # La consola lo dice en su idioma (seccion 101).
                "clave": "enc_ya_enviadas"}
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
        # La contestada y la vencida llegan con su texto en el idioma de
        # la encuesta (seccion 101); el token que no existe no tiene
        # idioma que respetar.
        detalle = e.detail
        texto = (detalle.get("mensaje") if isinstance(detalle, dict)
                 else detalle if isinstance(detalle, str) else None)
        suya = db.query(m.Encuesta).filter_by(token=token).first()
        return HTMLResponse(
            encuestas_html.pagina_cerrada(texto or "Encuesta no disponible",
                                          suya.idioma if suya else None),
            status_code=e.status_code)
    return HTMLResponse(encuestas_html.pagina(encuesta, motor.formulario(encuesta)))


@router.get("/correo/{encuesta_id}", response_class=HTMLResponse,
            summary="Ver el correo tal como le llega al cliente")
def ver_correo(encuesta_id: int, db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(LECTURA)):
    """Con el enlace tapado para quien solo ve encuestas (seccion 101).

    El correo lleva el enlace con el token, y con el token se contesta
    la encuesta: la puerta que lo protege es `enlace` --pide mandar
    encuestas y deja bitacora--, y esta la esquivaba con solo ver. Quien
    puede sacar el enlace lo ve vivo aqui tambien, y queda anotado igual
    que si lo hubiera sacado; para los demas el boton no lleva a nada.
    """
    encuesta = db.get(m.Encuesta, encuesta_id)
    if not encuesta:
        raise HTTPException(404, f"No existe la encuesta {encuesta_id}")
    enlace = None
    if (encuesta.estatus != m.EstatusEncuesta.RESPONDIDA
            and auth.puede_el_usuario(db, usuario, "encuestas.enviar")):
        enlace = f"/encuestas/pagina/{encuesta.token}"
        auditoria.registrar(db, usuario, encuesta.servicio,
                            "recuperar enlace de encuesta",
                            f"{encuesta.tipo.value} para "
                            f"{encuesta.destinatario_correo}, al ver el correo")
        db.commit()
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
    """Las dos del servicio, siempre: la que ya salio con su estatus, y la
    que no ha salido --sin id-- diciendo por que (seccion 101). Asi la
    tarjeta del servicio puede decir "falta el correo del principal" o
    ofrecer mandarla, en vez de callarse."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    filas = db.query(m.Encuesta).filter_by(servicio_id=servicio_id).all()
    salidas = {e.tipo: e for e in filas}
    return [_detalle(salidas[tipo]) if tipo in salidas
            else motor.sin_encuesta(servicio, tipo)
            for tipo in (m.TipoEncuesta.EJECUTIVO, m.TipoEncuesta.SOLICITANTE)]


@router.get("/por-clasificar", summary="Malas calificaciones sin revisar")
def por_clasificar(db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(LECTURA)):
    """Una mala calificacion no castiga sola: el consultor la revisa y
    decide si hubo incidencia. La del solicitante la decide direccion de
    operaciones, y cada renglon dice si a quien mira le toca o no
    (seccion 101), para que la pantalla no ofrezca un boton que va a
    contestar 403."""
    filas = (db.query(m.Encuesta)
             .filter_by(requiere_clasificacion=True, incidencia_id=None)
             .filter(m.Encuesta.clasificada_en.is_(None))
             .order_by(m.Encuesta.respondida_en).all())
    return [{**_detalle(e), "juez_y_parte": motor.es_juez_y_parte(usuario, e)}
            for e in filas]


@router.get("/resumen", summary="Como va la encuesta, en numeros")
def resumen(db: Session = Depends(get_db), dias: int = 90,
            _=Depends(LECTURA)):
    """Cuantas se mandaron, cuantas contestaron y cuantas se vencieron.

    La tasa de respuesta solo significa algo desde que las encuestas se
    vencen solas: antes, la que nadie contesto se quedaba en "enviada"
    para siempre y el denominador nunca cerraba.
    """
    # Con zona, porque `enviada_en` la tiene: la casa compara aware
    # contra aware (ver `catalogos.py`). Naive aqui no truena --lo
    # resuelve Postgres-- pero se corre las horas del huso.
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    filas = (db.query(m.Encuesta)
             .filter(m.Encuesta.enviada_en >= desde).all())

    respondidas = [e for e in filas
                   if e.estatus == m.EstatusEncuesta.RESPONDIDA]
    notas = [e.calificacion for e in respondidas if e.calificacion]
    ultimas = sorted(respondidas, key=lambda e: e.respondida_en,
                     reverse=True)[:12]
    return {
        "dias": dias,
        "enviadas": len(filas),
        "respondidas": len(respondidas),
        "esperando": sum(1 for e in filas
                         if e.estatus == m.EstatusEncuesta.ENVIADA),
        "vencidas": sum(1 for e in filas
                        if e.estatus == m.EstatusEncuesta.EXPIRADA),
        "tasa_pct": round(len(respondidas) / len(filas) * 100, 1) if filas else 0,
        "promedio": round(sum(notas) / len(notas), 2) if notas else None,
        "por_revisar": sum(1 for e in filas if e.requiere_clasificacion
                           and e.clasificada_en is None),
        "ultimas": [_detalle(e) for e in ultimas],
    }


@router.post("/{encuesta_id}/clasificar",
             summary="El consultor revisa una mala calificacion")
def clasificar(encuesta_id: int, datos: s.ClasificarEncuestaIn,
               db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(CLASIFICAR)):
    """Si amerita incidencia se liga la que corresponda, que a su vez
    necesita el visto bueno del director de operaciones para pegarle al
    bono. Si no amerita, se cierra con la nota y no pasa nada."""
    encuesta = db.get(m.Encuesta, encuesta_id)
    if not encuesta:
        raise HTTPException(404, f"No existe la encuesta {encuesta_id}")
    if encuesta.estatus != m.EstatusEncuesta.RESPONDIDA:
        raise HTTPException(409, "Esa encuesta todavia no se contesta")
    # Juez y parte (seccion 101): la del solicitante califica al
    # consultor y la clasifica direccion de operaciones, no el.
    if motor.es_juez_y_parte(usuario, encuesta):
        raise HTTPException(403, {
            "mensaje": "Esa encuesta califica al consultor: no la clasifica "
                       "un consultor.",
            "que_hacer": "La clasifica dirección de operaciones; a ellos les "
                         "llegó el aviso."})
    # Una sola clasificacion: la segunda reescribia la nota y la
    # incidencia sin dejar rastro de la primera.
    if encuesta.clasificada_en is not None:
        raise HTTPException(409, {
            "mensaje": "Esa encuesta ya está clasificada.",
            "que_hacer": "Lo que se decidió está en la bitácora del servicio."})

    if datos.incidencia_id:
        incidencia = db.get(m.Incidencia, datos.incidencia_id)
        if not incidencia:
            raise HTTPException(404, f"No existe la incidencia {datos.incidencia_id}")
        # La incidencia que se liga es de este servicio: ligar la de otro
        # le pegaba al bono de alguien por una queja que no era suya.
        if incidencia.servicio_id != encuesta.servicio_id:
            raise HTTPException(409, {
                "mensaje": f"La incidencia {incidencia.id} no es de este "
                           "servicio.",
                "que_hacer": "Liga una incidencia registrada en este mismo "
                             "servicio."})
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
                     "No afecta estrellas ni comision"),
            # La consola lo dice en su idioma (seccion 101).
            "clave": ("enc_nota_con_incidencia" if datos.incidencia_id
                      else "enc_nota_sin_incidencia")}


@router.get("/{encuesta_id}/enlace",
            summary="Recuperar el enlace para reenviarlo")
def enlace(encuesta_id: int, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(ENVIAR)):
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


@router.post("/{encuesta_id}/reenviar",
             summary="Mandar otra vez el correo de la encuesta")
def reenviar(encuesta_id: int, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(ENVIAR)):
    """La encuesta viva que no llego --el correo estaba mal y ya se
    corrigio-- sale otra vez al correo de hoy, con el mismo enlace
    (seccion 101). Queda en bitacora, como recuperar el enlace: es el
    mismo acto deliberado, y el enlace viaja en la respuesta por si hay
    que mandarlo por otro camino."""
    encuesta = db.get(m.Encuesta, encuesta_id)
    if not encuesta:
        raise HTTPException(404, f"No existe la encuesta {encuesta_id}")
    motor.reenviar(db, encuesta)
    auditoria.registrar(db, usuario, encuesta.servicio, "reenviar encuesta",
                        f"{encuesta.tipo.value} a {encuesta.destinatario_correo}")
    db.commit()
    return {"resultado": "reenviada", "encuesta_id": encuesta.id,
            "tipo": encuesta.tipo.value,
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
        # El folio y el cliente: la bandeja se lee por servicio, no por
        # numero de encuesta. Sin esto, cada renglon obliga a abrir
        # otra pantalla para saber de que esta hablando.
        "folio": e.servicio.folio if e.servicio else None,
        "cliente": (e.servicio.cliente.nombre
                    if e.servicio and e.servicio.cliente else None),
        "tipo": e.tipo.value,
        "para": e.destinatario_nombre or e.destinatario_correo,
        # El correo y hasta cuando vive, para la tarjeta del servicio
        # (seccion 101): a donde se reenvia y si todavia se puede.
        "correo": e.destinatario_correo,
        "estatus": e.estatus.value,
        "motivo": None,
        "calificacion": e.calificacion,
        "respondida_en": e.respondida_en.isoformat() if e.respondida_en else None,
        "expira_en": e.expira_en.isoformat() if e.expira_en else None,
        "requiere_clasificacion": e.requiere_clasificacion,
        "clasificada": e.clasificada_en is not None,
        "incidencia_id": e.incidencia_id,
        "consultor_id": e.consultor_id,
        "respuestas": [{"pregunta": r.pregunta, "valor": r.valor,
                        "texto": r.texto} for r in e.respuestas],
    }

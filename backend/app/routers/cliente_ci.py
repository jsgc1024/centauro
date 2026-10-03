"""Las puertas de la app del cliente de la Central (seccion 133).

Todas, menos las de entrar y las del enlace, piden la sesion del
cliente (`cliente_ci.gente_actual`), que no abre nada mas del sistema.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import acceso_por_correo, intentos
from app import cliente_ci as motor
from app import models as m
from app.config import settings
from app.db import get_db

router = APIRouter(prefix="/ci-api", tags=["App del cliente de la Central"])

GENTE = motor.gente_actual


class EntrarIn(BaseModel):
    correo: str = Field(max_length=160)
    contrasena: str = Field(max_length=200)


class EnlaceIn(BaseModel):
    token: str = Field(max_length=100)


class UsarEnlaceIn(EnlaceIn):
    contrasena: str = Field(max_length=200)


class RecuperarIn(BaseModel):
    correo: str = Field(max_length=160)


class CambioIn(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


class YoIn(BaseModel):
    idioma: str = Field(pattern="^(es|pt|en)$")


class SuscripcionIn(BaseModel):
    endpoint: str = Field(max_length=2000)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)
    agente: str | None = Field(None, max_length=300)


def _ip(peticion: Request) -> str | None:
    return peticion.client.host if peticion.client else None


# ------------------------------------------------------------- entrar

@router.post("/entrar", summary="Iniciar sesion en la app del cliente")
def entrar(datos: EntrarIn, peticion: Request, db: Session = Depends(get_db)):
    salida = motor.entrar(db, datos.correo, datos.contrasena, _ip(peticion))
    db.commit()
    return salida


@router.post("/enlace", summary="Como esta un enlace de contrasena")
def revisar_enlace(datos: EnlaceIn, db: Session = Depends(get_db)):
    # El token viaja en el cuerpo y no en la ruta: la ruta se escribe en
    # el registro de acceso del servidor.
    return motor.revisar_enlace(db, datos.token)


@router.post("/enlace/usar", summary="Poner la contrasena con el enlace")
def usar_enlace(datos: UsarEnlaceIn, db: Session = Depends(get_db)):
    # Sin tope de intentos: el token son 32 bytes al azar, no se adivina.
    salida = motor.usar_enlace(db, datos.token, datos.contrasena)
    db.commit()
    return salida


@router.post("/recuperar", summary="Se me olvido la contrasena")
def recuperar(datos: RecuperarIn, peticion: Request, tareas: BackgroundTasks,
              db: Session = Depends(get_db)):
    """La misma respuesta exista o no la cuenta. El enlace solo viaja por
    el correo de la persona."""
    carril = f"ci-recuperar:{datos.correo.strip().lower()}"
    intentos.revisar(carril, _ip(peticion))
    intentos.fallo(carril, _ip(peticion))
    aviso = motor.recuperar(db, datos.correo)
    db.commit()
    acceso_por_correo.despachar_despues(tareas, aviso)
    return {"resultado": "pedido"}


@router.post("/contrasena", summary="Cambiar mi contrasena")
def cambiar_contrasena(datos: CambioIn, db: Session = Depends(get_db),
                       gente: m.UsuarioCliente = Depends(GENTE)):
    salida = motor.cambiar(db, gente, datos.actual, datos.nueva)
    db.commit()
    return salida


# ------------------------------------------------------------- lo suyo

@router.get("/yo", summary="Quien soy y que sigo")
def yo(db: Session = Depends(get_db),
       gente: m.UsuarioCliente = Depends(GENTE)):
    return motor.yo(db, gente)


@router.patch("/yo", summary="Cambiar mi idioma")
def cambiar_yo(datos: YoIn, db: Session = Depends(get_db),
               gente: m.UsuarioCliente = Depends(GENTE)):
    gente.idioma = datos.idioma
    db.commit()
    return motor.yo(db, gente)


@router.get("/mapa", summary="Lo vigente en mis estados")
def mapa(db: Session = Depends(get_db),
         gente: m.UsuarioCliente = Depends(GENTE)):
    # La llave va limitada en Google a las direcciones del sistema.
    return {"eventos": motor.mapa(db, gente),
            "llave_mapa": settings.google_maps_key_navegador or None}


@router.get("/fondo", summary="El riesgo de fondo del mes, por estado")
def fondo(db: Session = Depends(get_db),
          gente: m.UsuarioCliente = Depends(GENTE)):
    return motor.fondo(db, gente)


@router.get("/fondo/estados/{region_id}",
            summary="Como se compone el nivel de uno de mis estados")
def fondo_estado(region_id: int, db: Session = Depends(get_db),
                 gente: m.UsuarioCliente = Depends(GENTE)):
    return motor.fondo_estado(db, gente, region_id)


@router.get("/avisos", summary="Lo que me llego")
def avisos(db: Session = Depends(get_db),
           gente: m.UsuarioCliente = Depends(GENTE)):
    return motor.avisos(db, gente)


@router.get("/eventos/{evento_id}", summary="Un evento")
def evento(evento_id: int, db: Session = Depends(get_db),
           gente: m.UsuarioCliente = Depends(GENTE)):
    return motor.evento(db, gente, evento_id)


@router.post("/avisos/{alerta_id}/enterado", summary="Ya lo vi")
def enterado(alerta_id: int, db: Session = Depends(get_db),
             gente: m.UsuarioCliente = Depends(GENTE)):
    salida = motor.acusar(db, gente, alerta_id)
    db.commit()
    return salida


# ------------------------------------------------------------- telefono

@router.get("/push", summary="Este telefono, recibe avisos?")
def estado_push(endpoint: str | None = None, db: Session = Depends(get_db),
                gente: m.UsuarioCliente = Depends(GENTE)):
    return motor.estado_push(db, gente, endpoint)


@router.post("/push", summary="Este telefono quiere avisos")
def suscribir(datos: SuscripcionIn, db: Session = Depends(get_db),
              gente: m.UsuarioCliente = Depends(GENTE)):
    motor.suscribir(db, gente, datos.endpoint, datos.p256dh, datos.auth,
                    datos.agente)
    db.commit()
    return {"resultado": "suscrito"}


@router.delete("/push", status_code=204,
               summary="Este telefono ya no quiere avisos")
def desuscribir(endpoint: str, db: Session = Depends(get_db),
                gente: m.UsuarioCliente = Depends(GENTE)):
    motor.desuscribir(db, gente, endpoint)
    db.commit()


@router.post("/push/probar", summary="Mandarme un aviso de prueba")
def probar(db: Session = Depends(get_db),
           gente: m.UsuarioCliente = Depends(GENTE)):
    salida = motor.probar(db, gente)
    db.commit()
    return salida

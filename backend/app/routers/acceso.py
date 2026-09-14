"""Alta de accesos, creacion de contrasena e inicio de sesion."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["Acceso"])


class AltaUsuarioIn(BaseModel):
    persona_id: int
    rol: m.Rol


class EstablecerContrasenaIn(BaseModel):
    token: str
    contrasena: str


@router.post("/usuarios", status_code=201,
             summary="Dar de alta un acceso y generar su invitacion")
def alta_usuario(datos: AltaUsuarioIn, db: Session = Depends(get_db),
                 actor: m.Usuario = Depends(auth.requiere(m.Rol.ADMIN))):
    """El usuario queda ligado al correo del empleado. Se le envia un enlace
    para que el mismo cree su contrasena."""
    persona = db.get(m.Persona, datos.persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {datos.persona_id}")

    existente = db.query(m.Usuario).filter_by(persona_id=persona.id).first()
    if existente:
        raise HTTPException(409, f"Esa persona ya tiene acceso (usuario {existente.id})")

    usuario = m.Usuario(persona_id=persona.id, correo=persona.correo, rol=datos.rol)
    db.add(usuario)
    db.flush()

    token, expira = auth.token_invitacion()
    db.add(m.Invitacion(usuario_id=usuario.id, token=token, expira_en=expira))
    db.commit()

    return {
        "usuario_id": usuario.id, "correo": usuario.correo, "rol": usuario.rol.value,
        "invitacion": {
            "enlace": f"https://centauro.lat/crear-contrasena/{token}",
            "expira_en": expira.isoformat(),
        },
        "nota": "En produccion este enlace se envia por correo, no se devuelve aqui",
    }


@router.post("/establecer-contrasena", summary="El empleado crea su contrasena")
def establecer_contrasena(datos: EstablecerContrasenaIn, db: Session = Depends(get_db)):
    invitacion = db.query(m.Invitacion).filter_by(token=datos.token).first()
    if not invitacion:
        raise HTTPException(404, "Enlace invalido")
    if invitacion.usado_en:
        raise HTTPException(409, "Ese enlace ya se uso")
    if invitacion.expira_en < datetime.now():
        raise HTTPException(409, "El enlace expiro, pide uno nuevo")
    if len(datos.contrasena) < 8:
        raise HTTPException(400, "La contrasena debe tener al menos 8 caracteres")

    invitacion.usuario.hash_contrasena = auth.cifrar(datos.contrasena)
    invitacion.usado_en = datetime.now()
    db.commit()
    return {"resultado": "contrasena creada", "correo": invitacion.usuario.correo}


@router.post("/token", summary="Iniciar sesion")
def iniciar_sesion(formulario: OAuth2PasswordRequestForm = Depends(),
                   db: Session = Depends(get_db)):
    usuario = db.query(m.Usuario).filter_by(correo=formulario.username).first()
    if not usuario or not auth.verificar(formulario.password, usuario.hash_contrasena):
        raise HTTPException(401, "Correo o contrasena incorrectos")
    if not usuario.activo:
        raise HTTPException(403, "Ese acceso esta desactivado")

    usuario.ultimo_acceso = datetime.now()
    db.commit()
    return {"access_token": auth.crear_token(usuario), "token_type": "bearer",
            "rol": usuario.rol.value, "nombre": usuario.persona.nombre}


@router.get("/yo", summary="Quien soy")
def yo(usuario: m.Usuario = Depends(auth.usuario_actual)):
    return {"usuario_id": usuario.id, "nombre": usuario.persona.nombre,
            "correo": usuario.correo, "rol": usuario.rol.value,
            "persona_id": usuario.persona_id}

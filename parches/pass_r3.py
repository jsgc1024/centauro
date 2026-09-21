"""Paso 2c: las puertas de la contrasena."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/routers/acceso.py"
s = R.read_text()

VIEJO = "from app import accesos, auth, intentos\n"
NUEVO = "from app import accesos, auth, contrasenas, intentos\n"
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''class EstablecerContrasenaIn(BaseModel):
    token: str
    contrasena: str
'''
NUEVO = '''class EstablecerContrasenaIn(BaseModel):
    token: str
    contrasena: str


class CambioContrasenaIn(BaseModel):
    """La actual se pide aunque ya tenga la sesion abierta: sin eso, una
    sesion robada se vuelve una cuenta robada para siempre."""
    actual: str
    nueva: str


class RecuperarIn(BaseModel):
    correo: str
'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# El motor ya sabe validar: la puerta deja de tener su propia regla.
VIEJO = '''@router.post("/establecer-contrasena", summary="El empleado crea su contrasena")
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
    return {"resultado": "contrasena creada", "correo": invitacion.usuario.correo}'''
NUEVO = '''@router.post("/establecer-contrasena",
             summary="Poner la contrasena con un enlace")
def establecer_contrasena(datos: EstablecerContrasenaIn,
                          db: Session = Depends(get_db)):
    """Sirve para la primera y para la olvidada: es el mismo enlace con
    distinto motivo y distinta duracion."""
    resultado = contrasenas.usar_enlace(db, datos.token, datos.contrasena)
    db.commit()
    return resultado


@router.post("/mi-contrasena", summary="Cambiar mi propia contrasena")
def cambiar_mi_contrasena(datos: CambioContrasenaIn, peticion: Request,
                          db: Session = Depends(get_db),
                          usuario: m.Usuario = Depends(auth.usuario_actual)):
    """Cambiarla tira las demas sesiones abiertas.

    Va con el mismo limite de intentos que el inicio de sesion: adivinar
    la contrasena actual desde una sesion robada es el mismo ataque por
    otra puerta.
    """
    ip = peticion.client.host if peticion.client else None
    intentos.revisar(usuario.correo, ip)
    try:
        resultado = contrasenas.cambiar(db, usuario, datos.actual, datos.nueva)
    except HTTPException as e:
        if e.status_code == 401:
            intentos.fallo(usuario.correo, ip)
        raise
    intentos.exito(usuario.correo, ip)
    db.commit()
    return resultado


@router.post("/recuperar", summary="Se me olvido la contrasena")
def recuperar(datos: RecuperarIn, peticion: Request,
              db: Session = Depends(get_db)):
    """La respuesta es la misma exista o no la cuenta.

    El enlace no viaja aqui: esta puerta es publica, y devolverlo seria
    regalar la cuenta a quien escriba un correo ajeno. Mientras el
    sistema no sepa mandar correos que no cuelguen de un servicio, lo
    entrega administracion desde el panel.
    """
    ip = peticion.client.host if peticion.client else None
    intentos.revisar(datos.correo, ip)
    intentos.fallo(datos.correo, ip)   # cuenta como intento, exista o no
    resultado = contrasenas.pedir_recuperacion(db, datos.correo)
    db.commit()
    return resultado


@router.get("/usuarios/{usuario_id}/enlace-pendiente",
            summary="El enlace vivo de esa cuenta, para entregarlo")
def enlace_pendiente(usuario_id: int, db: Session = Depends(get_db),
                     actor: m.Usuario = Depends(ADMINISTRA)):
    """Existe porque el sistema todavia no sabe mandar un correo que no
    cuelgue de un servicio. Mientras tanto lo entrega una persona, igual
    que el codigo del personal de campo lo dicta su consultor.

    Queda escrito quien lo pidio: un enlace de contrasena en manos de
    alguien es una cuenta en manos de alguien.
    """
    resultado = contrasenas.enlace_pendiente(db, usuario_id)
    accesos.anotar(db, actor, "enlace entregado", "usuario", usuario_id,
                   detalle=resultado["tipo"])
    db.commit()
    return resultado'''
assert s.count(VIEJO) == 1, "no encontre establecer_contrasena"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("routers/acceso.py: cambiar, recuperar y entregar el enlace")

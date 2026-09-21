"""Paso 3b: las tres puertas del codigo de campo."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/routers/acceso.py"
s = R.read_text()

VIEJO = '''ADMINISTRA = auth.requiere(m.Rol.ADMIN, m.Rol.DIRECTOR_GENERAL)
'''
NUEVO = '''ADMINISTRA = auth.requiere(m.Rol.ADMIN, m.Rol.DIRECTOR_GENERAL)

# Quien puede dictarle un codigo al personal de campo. La central
# siempre; el consultor cuando esa persona trabaje en sus servicios --eso
# se revisa adentro, porque depende de quien sea el agente--. No entra
# direccion de operaciones: lo unico que protege este camino es que quien
# entrega el codigo reconozca la voz de quien llama.
DICTA_CODIGO = auth.requiere(m.Rol.CONSULTOR, m.Rol.CENTRAL)
'''
assert s.count(VIEJO) == 1, "no encontre ADMINISTRA"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''class RecuperarIn(BaseModel):
    correo: str
'''
NUEVO = '''class RecuperarIn(BaseModel):
    correo: str


class CodigoCampoIn(BaseModel):
    persona_id: int


class ContrasenaDeCampoIn(BaseModel):
    """Lo que manda la app: quien eres, los cuatro digitos que te
    dictaron, y la contrasena que quieres."""
    correo: str
    codigo: str
    contrasena: str
'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

ANCLA = '''@router.get("/usuarios/{usuario_id}/enlace-pendiente",'''
PUERTAS = '''@router.get("/campo/buscar", summary="Buscar a quien darle un codigo")
def buscar_para_codigo(q: str = "", db: Session = Depends(get_db),
                       actor: m.Usuario = Depends(DICTA_CODIGO)):
    """El buscador de la pantalla del codigo.

    El consultor ve a su gente; la central ve a todos. Pide al menos dos
    letras: una busqueda que devuelve a todos es el padron completo en la
    pantalla de cualquier consultor.
    """
    return contrasenas.buscar_para_codigo(db, actor, q)


@router.post("/campo/codigo", summary="Generar el codigo para dictarlo")
def generar_codigo(datos: CodigoCampoIn, db: Session = Depends(get_db),
                   actor: m.Usuario = Depends(DICTA_CODIGO)):
    """Cuatro digitos, diez minutos, un solo uso.

    Es la unica vez que se ven: si se cierra la tarjeta hay que generar
    otro, y ese mata a este. Asi nadie acumula una lista de codigos
    vigentes en una pestana abierta.
    """
    resultado = contrasenas.generar_codigo(db, actor, datos.persona_id)
    db.commit()
    return resultado


@router.post("/campo/contrasena", summary="Poner la contrasena con el codigo")
def contrasena_de_campo(datos: ContrasenaDeCampoIn, peticion: Request,
                        db: Session = Depends(get_db)):
    """Lo que hace el agente desde la app.

    Va con limite propio: cuatro digitos son diez mil combinaciones, y el
    tope por codigo --cinco fallos y se muere-- vive en la base, no en
    Redis. Este de aqui es el segundo cinturon, contra quien pruebe con
    muchos correos distintos.
    """
    ip = peticion.client.host if peticion.client else None
    carril = f"codigo:{datos.correo}"
    intentos.revisar(carril, ip)
    try:
        resultado = contrasenas.usar_codigo(db, datos.correo, datos.codigo,
                                            datos.contrasena)
    except HTTPException as e:
        if e.status_code == 401:
            intentos.fallo(carril, ip)
        raise
    intentos.exito(carril, ip)
    db.commit()
    return resultado


@router.get("/usuarios/{usuario_id}/enlace-pendiente",'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, PUERTAS)
R.write_text(s)
print("routers/acceso.py: buscar, generar y usar el codigo")

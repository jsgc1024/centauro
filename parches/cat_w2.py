"""Paso 5f: la pregunta ya no la contesta el rol, la contesta la persona.

El orden en que se resuelve, y por que:

  1. Administracion pasa siempre. Si no, un error de configuracion deja
     a la empresa sin poder arreglar la configuracion.
  2. Un permiso extra que se le dio a esa persona.
  3. Su categoria, si la tiene.
  4. Si no tiene categoria, su rol --que es como funcionaba hasta hoy--.

Nadie nace con categoria, asi que el dia que esto se aplique todos caen
en el paso 4 y nada cambia.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/auth.py"
s = R.read_text()

VIEJO = '''def puede(actividad: str):
    """Dependencia que restringe un endpoint a una actividad con nombre.

    Por dentro sigue siendo el mismo control por rol de siempre; lo que
    cambia es la pregunta. Cuando exista el panel de permisos, la lista de
    roles de cada actividad saldra de la base y estos endpoints no se
    tocan.
    """
    from app import permisos

    def verificador(usuario: m.Usuario = Depends(usuario_actual)) -> m.Usuario:
        permitidos = permisos.roles_de(actividad)
        if usuario.rol == m.Rol.ADMIN:
            return usuario
        if HEREDA.get(usuario.rol, set()) & permitidos:
            return usuario
        if usuario.rol not in permitidos:
            raise HTTPException(403, {
                "mensaje": "Tu rol no tiene permiso para esta accion",
                "actividad": actividad,
                "tu_rol": usuario.rol.value,
                "roles_permitidos": sorted(r.value for r in permitidos),
            })
        return usuario

    return verificador'''

NUEVO = '''def puede_el_usuario(db: Session, usuario: m.Usuario, actividad: str) -> bool:
    """La pregunta completa: esta persona, esta actividad.

    El orden importa:

    1. **Administracion pasa siempre.** Si no, un error de configuracion
       deja a la empresa sin poder arreglar la configuracion.
    2. **Un permiso extra** que alguien le dio a esta persona de mas.
       Solo dan, nunca quitan: para quitar se le hace una categoria que
       no lo traiga, y entonces su renglon dice la verdad.
    3. **Su categoria**, si la tiene. Manda sobre el rol: de eso se trata.
    4. **Su rol**, si no tiene categoria. Es como funciono el sistema
       hasta que las categorias existieron, y por eso el dia que se
       aplican no le cambia nada a nadie.

    Una categoria desactivada sigue mandando para quien ya la trae: el
    `activa` solo decide si se ofrece al asignar. Apagar una categoria y
    que su gente ganara permisos de golpe seria lo contrario de lo que
    uno quiere al apagarla.
    """
    from app import permisos

    if usuario.rol == m.Rol.ADMIN:
        return True

    suelto = (db.query(m.PermisoExtra.id)
              .filter_by(usuario_id=usuario.id, actividad=actividad).first())
    if suelto:
        return True

    if usuario.categoria_id:
        return (db.query(m.ActividadDeCategoria.id)
                .filter_by(categoria_id=usuario.categoria_id,
                           actividad=actividad).first()) is not None

    permitidos = permisos.roles_de(actividad)
    if usuario.rol in permitidos:
        return True
    return bool(HEREDA.get(usuario.rol, set()) & permitidos)


def puede(actividad: str):
    """Dependencia que restringe un endpoint a una actividad con nombre.

    Lo que cambia con las categorias no es esto: los endpoints preguntan
    igual que antes. Lo que cambia es de donde sale la respuesta.
    """
    def verificador(usuario: m.Usuario = Depends(usuario_actual),
                    db: Session = Depends(get_db)) -> m.Usuario:
        if puede_el_usuario(db, usuario, actividad):
            return usuario
        from app import permisos
        raise HTTPException(403, {
            "mensaje": "No tienes permiso para esta accion",
            "actividad": actividad,
            "tu_rol": usuario.rol.value,
            "tu_categoria": (usuario.categoria.nombre
                             if usuario.categoria else None),
            "roles_permitidos": sorted(
                r.value for r in permisos.roles_de(actividad)),
        })

    return verificador


def horas_de_sesion(usuario: m.Usuario) -> int:
    """Cuanto le dura la sesion a esta persona.

    Doce horas parejas para todos no sirven: quien esta en la calle
    vuelve a entrar a media jornada, y una computadora de oficina que se
    queda prendida sigue abierta toda la tarde.
    """
    categoria = usuario.categoria
    if categoria and categoria.horas_sesion:
        return categoria.horas_sesion
    return HORAS_SESION'''

assert s.count(VIEJO) == 1, "no encontre puede()"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''        "exp": ahora + timedelta(hours=HORAS_SESION),'''
NUEVO = '''        "exp": ahora + timedelta(hours=horas_de_sesion(usuario)),'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("auth.py: la respuesta sale de la persona, no del rol")

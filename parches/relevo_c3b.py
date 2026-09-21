import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/routers/contingencia.py"
s = R.read_text()
VIEJO = '''            "regreso_por": (
                (db.get(m.Persona, r.regreso_por_id) or quien).nombre
                if r.regreso_por_id else None),'''
NUEVO = '''            "regreso_por": _nombre(db, r.regreso_por_id),'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

ANCLA = '''@router.get("/reemplazos/servicio/{servicio_id}",'''
AYUDA = '''def _nombre(db: Session, persona_id: int | None) -> str | None:
    persona = db.get(m.Persona, persona_id) if persona_id else None
    return persona.nombre if persona else None


@router.get("/reemplazos/servicio/{servicio_id}",'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, AYUDA)
R.write_text(s)
print("arreglado: el nombre del que cerro no revienta si no esta")

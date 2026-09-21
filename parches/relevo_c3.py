"""Paso C3: el historial dice cuando se cerro el cambio y quien lo cerro."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/routers/contingencia.py"
s = R.read_text()

VIEJO = '''            "formalizo": quien.nombre if quien else None,
            "alerta_id": r.alerta_id,
            "creado_en": r.creado_en.isoformat() if r.creado_en else None,
        })'''
NUEVO = '''            "formalizo": quien.nombre if quien else None,
            "alerta_id": r.alerta_id,
            "creado_en": r.creado_en.isoformat() if r.creado_en else None,
            # Si tiene fecha de regreso, el titular ya volvio y el `hasta`
            # de arriba es el ultimo dia que cubrio el que entro. Sin
            # ella, el cambio sigue corriendo.
            "regreso_en": r.regreso_en.isoformat() if r.regreso_en else None,
            "regreso_por": (
                (db.get(m.Persona, r.regreso_por_id) or quien).nombre
                if r.regreso_por_id else None),
        })'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("routers/contingencia.py: el historial muestra el regreso")

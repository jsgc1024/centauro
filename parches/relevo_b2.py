"""Paso B2: se va la puerta vieja. Queda una sola."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- 1. implantado.reemplazar() desaparece ---------------------------
R = RAIZ / "backend/app/implantado.py"
s = R.read_text()
ini = s.index("def reemplazar(db: Session, jornada_id: int, entra_id: int,")
fin = s.index("def cierre_del_mes(db: Session, contrato_id: int) -> dict:")
assert ini < fin
s = s[:ini] + s[fin:]
assert "def reemplazar(" not in s
R.write_text(s)
print("implantado.py: reemplazar() eliminada")

# --- 2. el endpoint de un dia suelto desaparece ----------------------
R = RAIZ / "backend/app/routers/implantados.py"
s = R.read_text()

ESQUEMA = '''class ReemplazoIn(BaseModel):
    entra_id: int
    motivo: m.MotivoReemplazo
    nota: str | None = None


'''
assert s.count(ESQUEMA) == 1
s = s.replace(ESQUEMA, "")

ini = s.index('@router.post("/jornadas/{jornada_id}/reemplazo",')
fin = s.index('@router.get("/contratos/{contrato_id}/resumen",')
assert ini < fin
s = s[:ini] + s[fin:]
assert "ReemplazoIn" not in s
print("implantados.py: endpoint de un dia suelto eliminado")

# --- 3. sale_id deja de ser opcional en el tramo ---------------------
VIEJO = """    entra_id: int
    sale_id: int | None = None      # vacio: quien este ese dia
    motivo: m.MotivoCambio"""
NUEVO = """    entra_id: int
    # Sin nombre no hay cambio. Antes, vacio queria decir "el primero de
    # la lista de ese dia": en una plantilla de tres eso cambiaba al que
    # no era, y el fin de semana, cuando la plantilla rota, a cualquiera.
    sale_id: int
    motivo: m.MotivoCambio"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# El tramo ahora puede partir un dia y mover dinero: la respuesta trae
# mas de lo que la auditoria escribia.
VIEJA_AUD = """    auditoria.registrar(db, usuario, servicio, "cambio de recurso",
                        f"{resultado['sale']} por {resultado['entra']} "
                        f"({datos.motivo.value}), "
                        f"{resultado['dias_cambiados']} dia(s)")"""
NUEVA_AUD = """    partidos = resultado.get("dias_partidos") or []
    auditoria.registrar(db, usuario, servicio, "cambio de recurso",
                        f"{resultado['sale']} por {resultado['entra']} "
                        f"({datos.motivo.value}), "
                        f"{resultado['dias_cambiados']} dia(s)"
                        + (f"; dia partido: {', '.join(partidos)}"
                           if partidos else ""))"""
assert s.count(VIEJA_AUD) == 1
s = s.replace(VIEJA_AUD, NUEVA_AUD)

VIEJA_LLAMADA = """        db, servicio.id, datos.tipo, datos.desde, datos.hasta,
        datos.entra_id, datos.motivo, usuario.persona_id,
        datos.sale_id, datos.nota)"""
NUEVA_LLAMADA = """        db, servicio.id, datos.tipo, datos.desde, datos.hasta,
        datos.entra_id, datos.motivo, usuario.persona_id,
        datos.sale_id, datos.nota, datos.relevado_en)"""
assert s.count(VIEJA_LLAMADA) == 1
s = s.replace(VIEJA_LLAMADA, NUEVA_LLAMADA)

# La hora del relevo: el sistema propone, el consultor corrige.
VIEJO2 = """    motivo: m.MotivoCambio
    nota: str | None = None


class DiaFinDeSemanaIn(BaseModel):"""
NUEVO2 = """    motivo: m.MotivoCambio
    nota: str | None = None
    # La hora que parte el dia. Vacia: la ultima marca de quien sale.
    # El consultor la corrige cuando sabe que fue otra.
    relevado_en: datetime | None = None


class DiaFinDeSemanaIn(BaseModel):"""
assert s.count(VIEJO2) == 1
s = s.replace(VIEJO2, NUEVO2)

R.write_text(s)
print("implantados.py: sale_id obligatorio y hora del relevo conectada")

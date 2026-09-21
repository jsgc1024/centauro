"""Paso 5c: los aliases dejan de nombrar roles y nombran actividades.

Los roles de cada actividad son identicos a los de hoy (ver permisos.py),
asi que esto no cambia quien puede hacer que. Cambia la pregunta.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "backend/app/routers"

CAMBIOS = {
"viaticos.py": [
("""CONSULTOR = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES)
FINANZAS = auth.requiere(m.Rol.FINANZAS)
CAMPO = auth.requiere(m.Rol.PERSONAL_SEGURIDAD)
LECTURA = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES,
                        m.Rol.FINANZAS, m.Rol.CENTRAL)
# La evidencia del deposito la ven finanzas y direccion, el consultor
# —que es quien recibe la llamada de "no me ha llegado"— y el agente,
# pero solo la suya. Lo ultimo se revisa dentro del endpoint, no aqui:
# el rol deja pasar, la pertenencia decide.
EVIDENCIA = auth.requiere(m.Rol.FINANZAS, m.Rol.DIRECTOR_OPERACIONES,
                          m.Rol.DIRECTOR_GENERAL, m.Rol.CONSULTOR,
                          m.Rol.PERSONAL_SEGURIDAD)""",
 """# Las puertas preguntan por actividad y no por rol. Hoy la respuesta es
# la misma --cada actividad nace con los roles que tenia-- pero el dia
# que exista el panel de categorias, estas puertas no se tocan.
#
# Decidir cuanto se deposita no es lo mismo que revisar lo que se gasto,
# asi que son dos actividades: es la diferencia entre un consultor y un
# consultor junior.
CONSULTOR = auth.puede("viaticos.asignar")
CIERRA = auth.puede("viaticos.cerrar")
FINANZAS = auth.puede("viaticos.transferir")
CAMPO = auth.puede("viaticos.comprobar")
LECTURA = auth.puede("viaticos.ver")
# La evidencia del deposito la ven finanzas y direccion, el consultor
# —que es quien recibe la llamada de "no me ha llegado"— y el agente,
# pero solo la suya. Lo ultimo se revisa dentro del endpoint, no aqui:
# la actividad deja pasar, la pertenencia decide.
EVIDENCIA = auth.puede("viaticos.evidencia")"""),
],
"cierre.py": [
("""CONSULTOR = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES)
FINANZAS = auth.requiere(m.Rol.FINANZAS)
DIRECCION = auth.requiere(m.Rol.DIRECTOR_OPERACIONES, m.Rol.DIRECTOR_GENERAL)
LECTURA = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES,
                        m.Rol.FINANZAS, m.Rol.CENTRAL)""",
 """# Cotizar no es cerrar: lo primero le pone precio al servicio y lo
# segundo lo manda a facturar. `DIRECCION` se fue porque no la usaba
# ningun endpoint: era un alias muerto.
COTIZA = auth.puede("cierre.cotizar")
CONSULTOR = auth.puede("cierre.cerrar")
FINANZAS = auth.puede("cierre.facturar")
LECTURA = auth.puede("cierre.ver")"""),
("""                 _=Depends(auth.requiere(m.Rol.CONSULTOR, m.Rol.FINANZAS,
                                         m.Rol.DIRECTOR_OPERACIONES,
                                         m.Rol.DIRECTOR_GENERAL))):""",
 """                 _=Depends(auth.puede("cierre.rentabilidad"))):"""),
],
"nomina.py": [
("""FINANZAS = auth.requiere(m.Rol.FINANZAS, m.Rol.DIRECTOR_OPERACIONES)
LECTURA = auth.requiere(m.Rol.FINANZAS, m.Rol.CONSULTOR, m.Rol.CENTRAL,
                        m.Rol.DIRECTOR_OPERACIONES)""",
 """# Armar el corte no es marcarlo pagado: lo segundo es el momento en que
# sale el dinero. Y el tabulador --lo que se paga por dia-- se cambia muy
# de vez en cuando y lo cambia otra gente.
FINANZAS = auth.puede("nomina.calcular")
PAGAR = auth.puede("nomina.pagar")
TABULADOR = auth.puede("nomina.tabulador")
LECTURA = auth.puede("nomina.ver")"""),
],
"bonos.py": [
("""CONSULTOR = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES)
DIR_OPERACIONES = auth.requiere(m.Rol.DIRECTOR_OPERACIONES)
DIR_GENERAL = auth.requiere(m.Rol.DIRECTOR_GENERAL)
RRHH = auth.requiere(m.Rol.DIRECTOR_OPERACIONES, m.Rol.FINANZAS)
LECTURA = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES,
                        m.Rol.FINANZAS, m.Rol.CENTRAL)""",
 """CONSULTOR = auth.puede("bonos.incidencia")
DIR_OPERACIONES = auth.puede("bonos.visto_bueno")
DIR_GENERAL = auth.puede("comisiones.resolver")
RRHH = auth.puede("bonos.autorizar")
LECTURA = auth.puede("bonos.ver")"""),
("""                     _=Depends(auth.requiere(m.Rol.FINANZAS,
                                             m.Rol.DIRECTOR_OPERACIONES))):""",
 """                     _=Depends(auth.puede("comisiones.generar"))):"""),
("""               _=Depends(auth.requiere(m.Rol.FINANZAS))):""",
 """               _=Depends(auth.puede("comisiones.ajustar"))):"""),
],
}

for archivo, pares in CAMBIOS.items():
    ruta = RAIZ / archivo
    s = ruta.read_text()
    for viejo, nuevo in pares:
        assert s.count(viejo) == 1, f"{archivo}: {viejo.splitlines()[0][:50]}"
        s = s.replace(viejo, nuevo)
    ruta.write_text(s)
    print(f"{archivo}: {len(pares)} bloque(s) al dia")

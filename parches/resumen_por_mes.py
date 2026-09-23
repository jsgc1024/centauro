# -*- coding: utf-8 -*-
"""El resumen del mes del implantado, solo con sus dias.

Hallazgo del 23 de septiembre, al revisar la factura del implantado: el
resumen para facturar contaba todas las jornadas del equipo, y el
implantado usa el mismo equipo mes tras mes. En cuanto se abria el mes
que sigue, el resumen de cada mes sumaba los dos: se habria cobrado
doble. El corte del mes si filtraba, asi que los dos papeles dejaban de
cuadrar.

Ahora los dos salen de la misma lista, `jornadas_del_mes`. Idempotente.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"
ARCHIVOS = {
    "implantado": B / "app/implantado.py",
    "t_mes": B / "tests/test_mes_siguiente.py",
    "bitacora": RAIZ / "BITACORA.md",
}
textos = {k: io.open(v, encoding="utf-8").read() for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(viejo) == 1, f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces"
    textos[clave] = t.replace(viejo, nuevo)


# 1. Una sola lista de las jornadas del mes, para el corte y el resumen.
cambiar("implantado",
        "def cierre_del_mes(db: Session, contrato_id: int) -> dict:\n",
        "def jornadas_del_mes(contrato: m.ContratoImplantado) -> list:\n"
        "    \"\"\"Las jornadas vivas del mes de este contrato, en orden.\n"
        "\n"
        "    El implantado usa el mismo equipo mes tras mes, asi que las\n"
        "    jornadas del equipo son las de todos sus meses. El resumen para\n"
        "    facturar las contaba todas y, en cuanto se abria el mes que sigue,\n"
        "    el de cada mes sumaba los dos: se habria cobrado doble. El corte y\n"
        "    el resumen salen ahora de esta lista, que es la unica forma de que\n"
        "    cuadren.\n"
        "    \"\"\"\n"
        "    equipo = contrato.servicio.equipos[0] if contrato.servicio.equipos else None\n"
        "    return sorted(\n"
        "        [j for j in (equipo.jornadas if equipo else [])\n"
        "         if j.fecha.year == contrato.anio and j.fecha.month == contrato.mes\n"
        "         and j.estatus != m.EstatusJornada.CANCELADA],\n"
        "        key=lambda j: j.fecha)\n"
        "\n"
        "\n"
        "def cierre_del_mes(db: Session, contrato_id: int) -> dict:\n",
        marca="def jornadas_del_mes(contrato: m.ContratoImplantado) -> list:\n")

# 2. El corte ya filtraba por mes: ahora usa la lista comun.
cambiar("implantado",
        "        raise HTTPException(404, f\"No existe el contrato {contrato_id}\")\n"
        "\n"
        "    equipo = contrato.servicio.equipos[0] if contrato.servicio.equipos else None\n"
        "    jornadas = sorted(\n"
        "        [j for j in (equipo.jornadas if equipo else [])\n"
        "         if j.fecha.year == contrato.anio and j.fecha.month == contrato.mes\n"
        "         and j.estatus != m.EstatusJornada.CANCELADA],\n"
        "        key=lambda j: j.fecha)\n",
        "        raise HTTPException(404, f\"No existe el contrato {contrato_id}\")\n"
        "\n"
        "    jornadas = jornadas_del_mes(contrato)\n",
        marca="    jornadas = jornadas_del_mes(contrato)\n")

# 3. El resumen para facturar: solo las del mes.
cambiar("implantado",
        "    equipo = contrato.servicio.equipos[0] if contrato.servicio.equipos else None\n"
        "    jornadas = equipo.jornadas if equipo else []\n"
        "    vivas = [j for j in jornadas if j.estatus != m.EstatusJornada.CANCELADA]\n",
        "    # Solo las del mes, las mismas del corte (ver `jornadas_del_mes`).\n"
        "    vivas = jornadas_del_mes(contrato)\n")

PRUEBA = '''def test_el_resumen_de_cada_mes_cuenta_solo_sus_dias(cliente, sesion, datos):
    """El implantado usa el mismo equipo mes tras mes. El resumen para
    facturar contaba todas sus jornadas: en cuanto se abria el mes que
    sigue, el de cada mes sumaba los dos y se habria cobrado doble."""
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    este = alta["contrato_id"]

    def resumen(contrato_id):
        r = cliente.get(f"/implantados/contratos/{contrato_id}/resumen",
                        headers=h)
        assert r.status_code == 200, r.text
        return r.json()

    antes = resumen(este)
    r = cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)
    assert r.status_code == 200, r.text
    siguiente = r.json()["contrato_id"]

    # El mes en curso no cambia porque se haya abierto el que sigue.
    despues = resumen(este)
    assert despues["dias"] == antes["dias"], despues["dias"]
    assert despues["facturacion"]["total"] == antes["facturacion"]["total"]

    # Y el que sigue cobra solo sus dias habiles, mas la unidad del mes.
    anio, mes = _siguiente(date.today())
    habiles = sum(1 for d in range(1, calendar.monthrange(anio, mes)[1] + 1)
                  if date(anio, mes, d).weekday() < 5)
    nuevo = resumen(siguiente)
    assert nuevo["periodo"] == f"{mes:02d}/{anio}"
    assert nuevo["dias"]["base"] == habiles, nuevo["dias"]
    assert nuevo["dias"]["total"] == habiles, nuevo["dias"]
    assert abs(float(nuevo["facturacion"]["total"])
               - (2900 * habiles + 66000)) < 0.01, nuevo["facturacion"]

    # Y cuadra con el corte, que sale de las mismas jornadas.
    corte = cliente.get(f"/implantados/contratos/{siguiente}/cierre",
                        headers=h).json()
    assert corte["cliente"]["base"] == nuevo["dias"]["base"]
    assert corte["cliente"]["adicionales"] == nuevo["dias"]["adicionales"]


'''
cambiar("t_mes",
        "def test_la_cartera_dice_cual_sigue_y_cuales_estan_abiertos(cliente, sesion, datos):\n",
        PRUEBA + "def test_la_cartera_dice_cual_sigue_y_cuales_estan_abiertos(cliente, sesion, datos):\n",
        marca="def test_el_resumen_de_cada_mes_cuenta_solo_sus_dias(")

cambiar("bitacora",
        "## 14. Lo que falta\n",
        "## 54. El resumen del mes del implantado, solo con sus días\n"
        "\n"
        "Hallazgo del 23 de septiembre, al revisar la factura del implantado:\n"
        "el resumen para facturar contaba todas las jornadas del equipo, y el\n"
        "implantado usa el mismo equipo mes tras mes. En cuanto se abría el mes\n"
        "que sigue, el resumen de cada mes sumaba los dos: se habría cobrado\n"
        "doble. El corte del mes sí filtraba, así que los dos papeles dejaban\n"
        "de cuadrar. No llegó a cobrarse nada: el sistema aún no está en\n"
        "producción.\n"
        "\n"
        "Ahora el corte y el resumen salen de la misma lista,\n"
        "`jornadas_del_mes`. La prueba abre el mes que sigue y revisa que cada\n"
        "resumen cuente solo sus días y cuadre con el corte.\n"
        "\n"
        "## 14. Lo que falta\n",
        marca="## 54. El resumen del mes del implantado, solo con sus días\n")

for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(textos[clave])
        print("escrito ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for s in saltados:
    print("saltado:", s)

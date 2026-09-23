# -*- coding: utf-8 -*-
"""Leer la flota y el taller de Odoo, desde la terminal.

Lo mismo que la consola hace con «ensayo» y «sincronizar». Desde la raiz
del proyecto:

    docker compose run --rm api python sincronizar_flota.py
    docker compose run --rm api python sincronizar_flota.py --aplicar

Sin --aplicar es un ensayo: lee Odoo, dice que haria y no guarda nada.
Nunca escribe en Odoo. El detalle queda en odoo_flota_ultimo.json junto
a este archivo; no va a git.
"""
import json
import sys
from pathlib import Path

from app import odoo_api, odoo_flota
from app.db import SessionLocal

DETALLE = Path(__file__).resolve().with_name("odoo_flota_ultimo.json")


def main(argv: list) -> int:
    aplicar = "--aplicar" in argv
    try:
        odoo = odoo_api.cliente()
    except odoo_api.SinConexion:
        print("Falta ODOO_BASE u ODOO_API_KEY en el .env.")
        return 1

    db = SessionLocal()
    try:
        informe = odoo_flota.sincronizar(db, odoo, ensayo=not aplicar)
    except odoo_api.NoResponde as error:
        print(f"Odoo no respondio: {error}")
        return 2
    finally:
        db.close()

    DETALLE.write_text(json.dumps(informe, ensure_ascii=False, indent=2,
                                  default=str), encoding="utf-8")
    r = odoo_flota.resumen(informe)
    t = r["taller"]
    print("Aplicado: quedo guardado en Centauro." if aplicar
          else "ENSAYO: no se guardo nada.")
    print(f"Unidades de Proteccion Ejecutiva en Odoo: {r['leidas']}")
    print(f"Altas: {r['altas']} · vinculadas: {r['vinculadas']} · "
          f"con cambios: {r['cambios']} · sin cambio: {r['sin_cambio']}")
    print(f"Bajas: {r['bajas']}")
    if t["error"]:
        print(f"Taller: {t['error']}")
    else:
        print(f"Taller: {t['nuevas']} nuevas · {t['cambios']} con cambios · "
              f"{t['borradas']} que ya no bloquean · {t['sin_cambio']} sin "
              f"cambio · {t['de_otras_unidades']} de unidades que no son de "
              "Proteccion Ejecutiva")
    if r["pendientes"]:
        print("Pendientes, por motivo:")
        for motivo, cuantos in sorted(r["pendientes"].items(),
                                      key=lambda x: -x[1]):
            print(f"  {cuantos:>3}  {motivo}")
    else:
        print("Pendientes: ninguno")
    print(f"El detalle quedo en {DETALLE.name} (no va a git).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

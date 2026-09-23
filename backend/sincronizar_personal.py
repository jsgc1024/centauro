# -*- coding: utf-8 -*-
"""Leer el personal de seguridad de Odoo, desde la terminal.

Lo mismo que la consola hace con «ensayo» y «sincronizar», para la
primera vez y para cuando se quiera ver sin abrir el navegador. Desde la
raiz del proyecto:

    docker compose run --rm api python sincronizar_personal.py
    docker compose run --rm api python sincronizar_personal.py --aplicar

Sin --aplicar es un ensayo: lee Odoo, dice que haria y no guarda nada.
Nunca escribe en Odoo.

En la terminal solo salen cuentas. El detalle, con nombres, queda en
odoo_personal_ultimo.json junto a este archivo; no va a git.
"""
import json
import sys
from pathlib import Path

from app import odoo_api, odoo_personal
from app.db import SessionLocal

DETALLE = Path(__file__).resolve().with_name("odoo_personal_ultimo.json")


def main(argv: list) -> int:
    aplicar = "--aplicar" in argv
    try:
        odoo = odoo_api.cliente()
    except odoo_api.SinConexion:
        print("Falta ODOO_BASE u ODOO_API_KEY en el .env.")
        return 1

    db = SessionLocal()
    try:
        informe = odoo_personal.sincronizar(db, odoo, ensayo=not aplicar)
    except odoo_api.NoResponde as error:
        print(f"Odoo no respondio: {error}")
        return 2
    finally:
        db.close()

    DETALLE.write_text(json.dumps(informe, ensure_ascii=False, indent=2,
                                  default=str), encoding="utf-8")
    r = odoo_personal.resumen(informe)
    fotos = r["fotos"]
    print("Aplicado: quedo guardado en Centauro." if aplicar
          else "ENSAYO: no se guardo nada.")
    print(f"Personal de seguridad en Odoo: {r['leidos']}")
    print(f"Altas: {r['altas']} · vinculadas: {r['vinculadas']} · "
          f"con cambios: {r['cambios']} · sin cambio: {r['sin_cambio']}")
    print(f"Bajas: {r['bajas']} · accesos que se cierran: "
          f"{r['accesos_cerrados']}")
    print(f"Fotos revisadas: {fotos['revisadas']} · de verdad: "
          f"{fotos['reales']} · solo iniciales: {fotos['sin_foto_real']}"
          + (f" · guardadas: {fotos['actualizadas']}" if aplicar else ""))
    if r["pendientes"]:
        print("Pendientes, por motivo:")
        for motivo, cuantos in sorted(r["pendientes"].items(),
                                      key=lambda x: -x[1]):
            print(f"  {cuantos:>3}  {motivo}")
    else:
        print("Pendientes: ninguno")
    print(f"El detalle, con nombres, quedo en {DETALLE.name} (no va a git).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

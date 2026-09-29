# -*- coding: utf-8 -*-
"""Traer de Odoo la foto grande (512 px) del personal que ya estaba.

Se corre una sola vez despues de actualizar: desde entonces la
sincronizacion de cada hora ya pide la grande, pero solo a quien RH toca
en Odoo, asi que el resto se quedaria con la chica. Decision de
Salvador, 29 sep: las fotos de la ficha del servicio, en grande.

Desde la raiz del proyecto (en el servidor, con docker-compose.prod.yml):

    docker compose run --rm api python fotos_grandes.py
    docker compose run --rm api python fotos_grandes.py --aplicar

Sin --aplicar es un ensayo: lee Odoo, dice cuantas cambiarian y no guarda
nada. Nunca escribe en Odoo. Correrlo dos veces no hace dano: la segunda
ya no encuentra nada que cambiar.
"""
import sys

from app import odoo_api, odoo_personal
from app.db import SessionLocal


def main(argv: list) -> int:
    aplicar = "--aplicar" in argv
    try:
        odoo = odoo_api.cliente()
    except odoo_api.SinConexion:
        print("Falta ODOO_BASE u ODOO_API_KEY en el .env.")
        return 1

    db = SessionLocal()
    try:
        informe = odoo_personal.releer_fotos(db, odoo, ensayo=not aplicar)
    except odoo_api.NoResponde as error:
        print(f"Odoo no respondio: {error}")
        return 2
    finally:
        db.close()

    print("Aplicado: quedo guardado en Centauro." if aplicar
          else "ENSAYO: no se guardo nada.")
    print(f"Personal revisado: {informe['revisadas']} · con foto de verdad "
          f"en Odoo: {informe['reales']} · "
          + (f"fotos cambiadas: {informe['cambian']}" if aplicar
             else f"cambiarian: {informe['cambian']}"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

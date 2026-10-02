"""Lo que falta o esta mal cargado en Odoo, por area (seccion 89).

Para limpiar Odoo con cada area. Lee Odoo con los mismos ensayos de la
pantalla de Odoo --el personal de seguridad, la flota y el taller, la
oficina, los clientes y los tarifarios-- y escribe en la terminal lo que
cada uno dejo pendiente, junto con lo que Centauro ya sabe: quien del
personal no tiene foto de verdad. No guarda nada, ni aqui ni en Odoo.

En el servidor, con la aplicacion ya actualizada:

    docker compose -f docker-compose.prod.yml run --rm api python lo_que_falta_en_odoo.py

Cada area empieza con un renglon «== clave | titulo | quien lo corrige |
leidos N»; cada lista, con «-- lista | cuantos»; cada caso va en su
renglon, tal como lo dice el ensayo.
"""
import json
import sys

from app import (odoo_api, odoo_clientes, odoo_flota, odoo_oficina,
                 odoo_personal, odoo_tarifarios)
from app import models as m
from app.db import SessionLocal

# Que se imprime de cada ensayo: lo que hay que corregir en Odoo. Las
# altas y los cambios no: esos entran solos en la lectura de cada hora.
AREAS = [
    ("personal", "El personal de seguridad", "Recursos Humanos", odoo_personal,
     # Las cuentas bancarias (seccion 105): cuantos sin cuenta, y si la
     # conexion no las pudo leer. Lo por capturar de la gente de Brasil
     # (seccion 121): el CPF, la CNH y la cuenta, que RH completa en Odoo.
     ("pendientes", "por_capturar", "celular_no_valido", "bajas", "fotos",
      "cuentas")),
    # Lo por capturar de la flota de Brasil (seccion 118) no detiene
    # nada, pero es lo que su area tiene que completar en Odoo.
    ("flota", "La flota y el taller", "Flota", odoo_flota,
     ("pendientes", "por_capturar", "taller.pendientes", "taller.error",
      "bajas")),
    ("oficina", "El personal de oficina", "Recursos Humanos", odoo_oficina,
     ("pendientes", "sin_correo", "sin_lugar", "sin_sugerencia", "bajas")),
    ("clientes", "Los clientes", "Finanzas", odoo_clientes,
     ("pendientes", "sin_rfc", "pais_por_rfc", "sin_ligar", "sin_tarifario",
      "bajas")),
    ("tarifarios", "Los tarifarios", "Finanzas y comercial", odoo_tarifarios,
     # De cada pais (seccion 123): cuantas listas se leyeron de cada uno.
     ("pendientes", "sin_cliente", "campo_implantados", "por_pais")),
]


def _texto(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


def _tomar(informe: dict, ruta: str):
    valor = informe
    for parte in ruta.split("."):
        valor = valor.get(parte) if isinstance(valor, dict) else None
    return valor


def imprimir(informe: dict, listas, salida) -> None:
    for lista in listas:
        valor = _tomar(informe, lista)
        if isinstance(valor, list):
            print(f"-- {lista} | {len(valor)}", file=salida)
            for caso in valor:
                print(f"   {_texto(caso)}", file=salida)
        elif valor not in (None, "", {}, 0):
            print(f"-- {lista} | {_texto(valor)}", file=salida)


def sin_foto(db) -> list[str]:
    """El personal de seguridad que vino de Odoo sin foto de verdad: Odoo
    solo tiene el circulo con sus iniciales, y la hoja del servicio sale
    sin su cara."""
    return [p.nombre for p in (db.query(m.Persona)
                               .filter(m.Persona.activo.is_(True),
                                       m.Persona.oficina.is_(False),
                                       m.Persona.es_freelance.is_(False),
                                       m.Persona.odoo_id.isnot(None))
                               .order_by(m.Persona.nombre).all())
            if not (p.foto_url or "").strip()]


def main(salida=sys.stdout) -> int:
    try:
        odoo = odoo_api.cliente()
    except odoo_api.SinConexion:
        print("ALTO: este servidor no tiene la llave de Odoo (ODOO_BASE y "
              "ODOO_API_KEY en el .env).", file=salida)
        return 1
    with SessionLocal() as db:
        for clave, titulo, area, modulo, listas in AREAS:
            try:
                informe = modulo.sincronizar(db, odoo, ensayo=True)
            except Exception as error:  # noqa: BLE001 -- se dice y se sigue
                print(f"== {clave} | {titulo} | {area} | ERROR: {error}",
                      file=salida)
                continue
            finally:
                # El ensayo no guarda; esto es por si acaso.
                db.rollback()
            leidos = informe.get("leidos", informe.get("leidas"))
            print(f"== {clave} | {titulo} | {area} | leidos {leidos}",
                  file=salida)
            imprimir(informe, listas, salida)
        nombres = sin_foto(db)
        print(f"== fotos | Personal de seguridad sin foto de verdad | "
              f"Recursos Humanos | {len(nombres)}", file=salida)
        for nombre in nombres:
            print(f"   {_texto(nombre)}", file=salida)
        db.rollback()
    print("== fin", file=salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())

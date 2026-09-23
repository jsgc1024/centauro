# -*- coding: utf-8 -*-
"""Cargar las fotos representativas de las categorias de vehiculo.

Decision de Salvador, 23 de septiembre: la unidad no lleva su foto real
sino la de su categoria, respetando su color --la Sienna negra se ve
negra--. Cada categoria tiene una foto base y, aparte, una por color; la
unidad ensena la de su color y, si no hay, la base.

En una carpeta, una foto por archivo, con este nombre:

    minivan.jpg             la base de la categoria
    minivan__negro.jpg      la misma en negro (dos guiones bajos)

De perfil, horizontal, unos 600 x 400, JPG de menos de 200 KB. Desde la
raiz del proyecto:

    docker compose run --rm \\
      -v "$HOME/Desktop/centauro/Claude outputs/fotos_categorias:/fotos" \\
      api python fotos_de_categoria.py /fotos

Una foto que ya estaba se reemplaza. Al final dice que colores de la flota
todavia no tienen su foto y ensenan la base.
"""
import base64
import collections
import sys
from pathlib import Path

from app import models as m
from app.db import SessionLocal
from app.odoo_flota_reglas import codigo_de_categoria, color_de

TIPOS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".webp": "image/webp"}
LIMITE = 3 * 1024 * 1024      # el mismo de las demas imagenes del sistema


def main(argv: list) -> int:
    if not argv:
        print("Falta la carpeta con las fotos.")
        return 1
    carpeta = Path(argv[0])
    if not carpeta.is_dir():
        print(f"No encuentro la carpeta {carpeta}.")
        return 1

    db = SessionLocal()
    try:
        categorias = {c.codigo: c for c in db.query(m.CategoriaVehiculo).all()}
        cargadas, sin_categoria, pesadas = [], [], []
        for archivo in sorted(carpeta.iterdir()):
            tipo = TIPOS.get(archivo.suffix.lower())
            if not archivo.is_file() or tipo is None:
                continue
            nombre, _, color = archivo.stem.partition("__")
            categoria = categorias.get(codigo_de_categoria(nombre))
            if categoria is None:
                sin_categoria.append(archivo.name)
                continue
            contenido = archivo.read_bytes()
            if len(contenido) > LIMITE:
                pesadas.append(archivo.name)
                continue
            color = color_de(color)
            foto = (db.query(m.FotoCategoria)
                    .filter_by(categoria_id=categoria.id, color=color).first())
            if foto is None:
                foto = m.FotoCategoria(categoria_id=categoria.id, color=color)
                db.add(foto)
            foto.foto_url = (f"data:{tipo};base64,"
                             f"{base64.b64encode(contenido).decode()}")
            cargadas.append(f"{categoria.nombre}"
                            + (f" en {color}" if color else " (base)")
                            + f", {len(contenido) // 1024} KB")
        db.commit()

        # Que colores de la flota todavia ensenan la base.
        hay = {(f.categoria_id, f.color) for f in db.query(
            m.FotoCategoria.categoria_id, m.FotoCategoria.color).all()}
        faltan = collections.Counter()
        for v in db.query(m.Vehiculo).filter(m.Vehiculo.activo.is_(True),
                                             m.Vehiculo.rentado.is_(False)).all():
            color = color_de(v.color)
            if (v.categoria_id, color) not in hay:
                faltan[(v.categoria.nombre, color or "sin color")] += 1
        sin_base = sorted(c.nombre for c in categorias.values()
                          if c.activo and (c.id, "") not in hay)
    finally:
        db.close()

    print(f"Fotos cargadas: {len(cargadas)}")
    for c in cargadas:
        print(f"  {c}")
    if sin_categoria:
        print("Sin categoria con ese nombre: " + ", ".join(sin_categoria))
    if pesadas:
        print("Pasan de 3 MB, no se cargaron: " + ", ".join(pesadas))
    print("Categorias sin foto base: " + (", ".join(sin_base) or "ninguna"))
    if faltan:
        print("Unidades cuyo color todavia no tiene foto (ensenan la base):")
        for (categoria, color), n in sorted(faltan.items()):
            print(f"  {n:>3}  {categoria} en {color}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

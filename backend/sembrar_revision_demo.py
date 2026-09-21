# -*- coding: utf-8 -*-
"""Una revisión de unidad con fotos de verdad, para probar el respaldo.

El respaldo verifica que las imágenes lleguen enteras comparando su
huella entre la base viva y la restaurada. Con la base sin fotos esa
verificación pasa por vacío: dice "no hay nada que comparar" y la parte
que de verdad importa se queda sin probar.

Esto siembra lo mínimo para que deje de estar vacía: una revisión de
recepción con sus cinco fotos de tamaño realista —unos 250 KB cada una,
que es lo que pesa una foto ya reducida por la app— sobre el primer
servicio con unidad que encuentre.

    docker compose exec -T api python sembrar_revision_demo.py

Es dato de demostración, no de operación. Para quitarlo:

    docker compose exec -T api python sembrar_revision_demo.py --borrar
"""
import sys
from datetime import datetime

from app import models as m
from app.db import SessionLocal

NOTA = "Sembrada para probar el respaldo (sembrar_revision_demo.py)"
ANGULOS = ["frente", "atras", "izquierdo", "derecho", "odometro"]
# Un JPEG minimo de verdad, y detras un relleno para que pese lo que
# pesa una foto real ya reducida. Lo que se prueba es que ese tamaño
# sobreviva al respaldo, no que la foto se vea bonita.
CABEZA = ("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEB"
          "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAAL"
          "CAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAA"
          "AAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")


def _foto(semilla: int, kilobytes: int = 250) -> str:
    """Una imagen del peso de una real. El relleno cambia con la semilla
    para que las cinco no salgan idénticas."""
    relleno = (f"{semilla:04d}" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij") * (
        kilobytes * 1024 // 40)
    return f"data:image/jpeg;base64,{CABEZA}{relleno}"


def borrar(db) -> int:
    filas = db.query(m.RevisionUnidad).filter_by(nota=NOTA).all()
    for r in filas:
        db.delete(r)          # las fotos se van con ella
    db.commit()
    return len(filas)


def sembrar(db) -> dict:
    ya = db.query(m.RevisionUnidad).filter_by(nota=NOTA).first()
    if ya:
        return {"resultado": "ya estaba", "revision_id": ya.id,
                "fotos": len(ya.fotos)}

    asignacion = (db.query(m.AsignacionVehiculo)
                  .join(m.Jornada, m.AsignacionVehiculo.jornada_id == m.Jornada.id)
                  .first())
    if not asignacion:
        return {"resultado": "no hay ninguna unidad asignada a un servicio"}

    jornada = db.get(m.Jornada, asignacion.jornada_id)
    servicio_id = jornada.equipo.servicio_id
    persona = (jornada.personal[0].persona_id if jornada.personal
               else db.query(m.Persona.id).first()[0])

    # Si ese servicio y unidad ya tienen su recepcion, no se duplica: la
    # base tiene una llave que lo impide, y ademas seria mentira.
    hecha = (db.query(m.RevisionUnidad)
             .filter_by(servicio_id=servicio_id,
                        vehiculo_id=asignacion.vehiculo_id,
                        tipo="recibe").first())
    if hecha:
        return {"resultado": "ese servicio ya tenia su recepcion",
                "revision_id": hecha.id, "fotos": len(hecha.fotos)}

    revision = m.RevisionUnidad(
        servicio_id=servicio_id, vehiculo_id=asignacion.vehiculo_id,
        persona_id=persona, tipo="recibe", kilometraje=42_000,
        combustible_octavos=8, nota=NOTA, hubo_dano=False,
        firma=_foto(9, kilobytes=40), momento=datetime.now())
    db.add(revision)
    db.flush()

    for i, angulo in enumerate(ANGULOS):
        db.add(m.FotoRevision(revision_id=revision.id, angulo=angulo,
                              imagen=_foto(i), momento=datetime.now()))
    db.commit()
    return {"resultado": "sembrada", "revision_id": revision.id,
            "servicio_id": servicio_id, "fotos": len(ANGULOS)}


if __name__ == "__main__":
    with SessionLocal() as db:
        if "--borrar" in sys.argv:
            print(f"Borradas {borrar(db)} revisiones de demostracion.")
        else:
            print(sembrar(db))

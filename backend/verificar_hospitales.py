#!/usr/bin/env python3
"""Completa el catalogo de hospitales con lo que dice Google.

    docker compose exec -T api python verificar_hospitales.py
    docker compose exec -T api python verificar_hospitales.py --aplicar
    docker compose exec -T api python verificar_hospitales.py --aplicar --ciudad Monterrey
    docker compose exec -T api python verificar_hospitales.py --aplicar --nombres
    docker compose exec -T api python verificar_hospitales.py --aplicar --solo "San Jose"
    docker compose exec -T api python verificar_hospitales.py --todos --max 5

Cada hospital es una consulta a Google y cada consulta se cobra. Por eso
esto NO revisa los que ya estan completos: mira solo a los que les falta
direccion o telefono. Volver a preguntar por uno que ya quedo es pagar
dos veces por la misma respuesta.

    --todos   revisa tambien los que ya estan completos
    --max N   no hace mas de N consultas en la corrida (por omision 20)
    --solo X  solo los que traigan X en el nombre

Los hospitales que trae la semilla son nombres reales con ubicaciones
aproximadas y sin telefono. Sirven para que la hoja no salga en blanco,
pero de aqui sale la referencia medica en una emergencia y ahi una
direccion a medias no sirve de nada.

Esto busca cada uno por su nombre, en un circulo alrededor de donde el
catalogo cree que esta, y se trae el dato bueno: direccion, telefono y
coordenadas. Corre desde el servidor porque la llave de Google vive aqui
y no sale de aqui.

Sin --aplicar no escribe nada: enseña lo que cambiaria y para ahi.

El nivel de atencion NO se toca nunca. Google no sabe hasta donde llega
un hospital, y de ese nivel sale la regla que garantiza un quirofano en
la hoja: lo marca Centauro y se queda como lo marco Centauro.

El nombre tampoco, salvo que se pida con --nombres. Si se cambia, la
semilla vuelve a crear el viejo la proxima vez que alguien la corra y
quedan dos renglones del mismo hospital.
"""
import sys
import time
from decimal import Decimal

from app import mapas
from app import models as m
from app.db import SessionLocal


def metros(lat1, lon1, lat2, lon2) -> int:
    from app.operacion import distancia_metros
    return int(distancia_metros(lat1, lon1, lat2, lon2))


# Entre un hospital y el siguiente. Google cobra por consulta y ademas
# corta cuando le llegan muchas de golpe; quince hospitales no tienen
# ninguna prisa.
PAUSA = 0.4
ESPERAS = (4, 12)          # lo que se aguanta cuando contesta 429


def preguntar(nombre: str, lat: float, lon: float):
    """Con reintento cuando Google dice que son muchas.

    El 429 no quiere decir que el hospital no exista: quiere decir que
    se le pidio muy rapido. Darlo por no encontrado manda a alguien a
    verificar a mano algo que estaba bien.
    """
    import httpx

    for intento, espera in enumerate((0,) + ESPERAS):
        if espera:
            print(f"    Google pidio calma, esperando {espera}s...")
            time.sleep(espera)
        try:
            return mapas.buscar_hospital(nombre, lat, lon)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 429 or intento == len(ESPERAS):
                raise
    return None


def main() -> int:
    aplicar = "--aplicar" in sys.argv
    nombres = "--nombres" in sys.argv
    ciudad = None
    if "--ciudad" in sys.argv:
        ciudad = sys.argv[sys.argv.index("--ciudad") + 1]
    solo = None
    if "--solo" in sys.argv:
        solo = sys.argv[sys.argv.index("--solo") + 1].lower()
    todos = "--todos" in sys.argv
    tope = 20
    if "--max" in sys.argv:
        tope = int(sys.argv[sys.argv.index("--max") + 1])

    db = SessionLocal()
    try:
        consulta = db.query(m.Hospital).filter(m.Hospital.activo.is_(True))
        if ciudad:
            plaza = db.query(m.Plaza).filter_by(nombre=ciudad).first()
            if not plaza:
                print(f"No existe la ciudad {ciudad!r}")
                return 1
            consulta = consulta.filter(m.Hospital.plaza_id == plaza.id)
        hospitales = consulta.order_by(m.Hospital.plaza_id,
                                       m.Hospital.nombre).all()
        if solo:
            hospitales = [x for x in hospitales if solo in x.nombre.lower()]

        # El freno: lo que ya tiene direccion y telefono no se vuelve a
        # preguntar. Cada consulta se cobra, y preguntar de nuevo por
        # una respuesta que ya esta guardada es tirar el dinero.
        completos = [x for x in hospitales if x.direccion and x.telefono]
        if not todos:
            hospitales = [x for x in hospitales
                          if not (x.direccion and x.telefono)]
        if len(hospitales) > tope:
            print(f"Son {len(hospitales)} y el tope de esta corrida es "
                  f"{tope}. Se hacen los primeros {tope}; vuelve a correr "
                  f"para seguir, o sube el tope con --max.")
            hospitales = hospitales[:tope]
        if not hospitales:
            print("No hay hospitales que verificar")
            return 0

        plazas = {p.id: p.nombre for p in db.query(m.Plaza).all()}
        print(f"{len(hospitales)} consulta(s) a Google"
              + (f" · {ciudad}" if ciudad else "")
              + ("" if aplicar else "  ·  ensayo, no se escribe nada"))
        if completos and not todos:
            print(f"{len(completos)} ya estaban completos y no se "
                  f"preguntan (--todos para revisarlos igual)")
        print()

        tocados, sin_encontrar, iguales = 0, [], 0
        for hospital in hospitales:
            plaza = plazas.get(hospital.plaza_id, "—")
            etiqueta = f"{hospital.nombre}  ·  {plaza}"
            try:
                # El nombre con la ciudad: "San Javier" solo encuentra
                # cosas en media republica.
                hallado = preguntar(f"{hospital.nombre}, {plaza}",
                                    float(hospital.lat), float(hospital.lon))
            except mapas.SinLlave as error:
                print(error)
                return 1
            except Exception as error:                    # noqa: BLE001
                print(f"✗ {etiqueta}\n    Google no contesto: {error}")
                sin_encontrar.append(hospital.nombre)
                continue

            if not hallado:
                print(f"✗ {etiqueta}\n    Google no lo encontro cerca de "
                      f"donde dice el catalogo")
                sin_encontrar.append(hospital.nombre)
                continue

            movio = metros(hospital.lat, hospital.lon,
                           hallado["lat"], hallado["lon"])
            aviso_nombre = None
            cambios = []
            if hallado["direccion"] and hallado["direccion"] != hospital.direccion:
                cambios.append(f"direccion: {hallado['direccion']}")
            if hallado["telefono"] and hallado["telefono"] != hospital.telefono:
                cambios.append(f"telefono:  {hallado['telefono']}")
            if movio > 50:
                cambios.append(f"ubicacion: se movio {movio} m")
            distinto = (hallado["nombre"]
                        and hallado["nombre"].strip() != hospital.nombre.strip())
            # El nombre oficial se avisa siempre, pero solo cuenta como
            # cambio cuando se pidio cambiarlo. Si no, cada corrida
            # volveria a reportar los mismos quince como pendientes y
            # nunca se sabria cuales faltan de verdad.
            if distinto and nombres:
                cambios.append(f"nombre oficial: {hallado['nombre']}")
            elif distinto:
                aviso_nombre = f"    nombre oficial en Google: {hallado['nombre']}"
            else:
                aviso_nombre = None

            if not cambios:
                iguales += 1
                print(f"= {etiqueta}")
                if distinto and not nombres:
                    print(aviso_nombre)
                continue

            print(f"→ {etiqueta}")
            for linea in cambios:
                print(f"    {linea}")
            if distinto and not nombres:
                print(aviso_nombre)

            time.sleep(PAUSA)
            if aplicar:
                if hallado["direccion"]:
                    hospital.direccion = hallado["direccion"][:300]
                if hallado["telefono"]:
                    hospital.telefono = hallado["telefono"][:40]
                hospital.lat = Decimal(str(hallado["lat"]))
                hospital.lon = Decimal(str(hallado["lon"]))
                if nombres and distinto:
                    hospital.nombre = hallado["nombre"][:160]
                tocados += 1

        if aplicar:
            db.commit()

        print()
        print(f"Consultas a Google en esta corrida: {len(hospitales)}")
        print(f"Iguales: {iguales}   "
              f"{'Actualizados' if aplicar else 'Por actualizar'}: "
              f"{tocados if aplicar else len(hospitales) - iguales - len(sin_encontrar)}"
              f"   Sin encontrar: {len(sin_encontrar)}")
        if sin_encontrar:
            print("Hay que verificarlos a mano: "
                  + ", ".join(sin_encontrar))
        if not aplicar:
            print("Ensayo. Para escribirlo: agrega --aplicar")
        print("El nivel de atencion no se toco: lo marca Centauro.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

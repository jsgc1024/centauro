# -*- coding: utf-8 -*-
"""Ensayo de la conexion con Pegasus (seccion 60): solo lectura, solo cuentas.

Antes de encender la lectura de cada dos minutos, hace una vez lo mismo
que va a hacer ella --entrar, los grupos, las unidades de cada grupo,
los eventos y los tramos del ultimo dia-- con el usuario del `.env`, y
dice solo CUANTOS. Ni nombres, ni placas, ni coordenadas; de los grupos
que no son de Proteccion Ejecutiva, ni el nombre. No escribe nada: ni en
Pegasus ni en la base.

Se corre en un contenedor aparte, que lee el `.env` de ese momento; los
que ya estan corriendo no se enteran de la clave hasta que se recrean:

    docker compose run --rm api python ensayo_pegasus.py
"""
from datetime import datetime, timedelta, timezone

from app import gps_reglas as reglas
from app import models as m
from app.db import SessionLocal
from app.gps import grupos_configurados
from app.pegasus import POR_LLAMADA, NoResponde, desde_la_configuracion


def _por_etiqueta(eventos: list[dict]) -> dict:
    cuenta: dict = {}
    for e in eventos:
        cuenta[e.get("label") or "?"] = cuenta.get(e.get("label") or "?", 0) + 1
    return cuenta


def main() -> int:
    cliente = desde_la_configuracion()
    if cliente is None:
        print("Falta PEGASUS_SITIO, PEGASUS_USUARIO o PEGASUS_CLAVE en el .env.")
        return 1
    ahora = datetime.now(timezone.utc)
    dia = reglas.duracion_hacia_atras(ahora - timedelta(days=1), ahora)
    try:
        grupos = cliente.grupos()
    except NoResponde as e:
        print(f"No entro: {e}")
        return 1
    print("Entro a Pegasus.")
    print(f"Grupos que ve este usuario: {len(grupos)} "
          f"(con un usuario solo de Proteccion Ejecutiva, {len(grupos_configurados())})")

    with SessionLocal() as db:
        paises = {p.codigo: p for p in db.query(m.Pais).all()}
        for codigo, nombre in grupos_configurados().items():
            grupo = next((g for g in grupos if g.get("name") == nombre), None)
            if grupo is None:
                print(f"\n{codigo} «{nombre}»: NO lo encuentra este usuario.")
                continue
            try:
                unidades = cliente.unidades(grupo["id"])
            except NoResponde as e:
                print(f"\n{codigo} «{nombre}»: no leyo sus unidades ({e})")
                continue
            estados = [reglas.estado_de_la_unidad(u) for u in unidades]
            estados = [e for e in estados if e.get("pegasus_id") is not None]
            con_placa = [e for e in estados if e.get("placa_normal")]
            reportan = [e for e in estados
                        if not reglas.callada(e.get("reporte_en"), ahora,
                                              reglas.HORAS_SIN_SENAL * 60)]
            print(f"\n{codigo} «{nombre}» (grupo {grupo['id']}): "
                  f"{len(estados)} unidades · {len(con_placa)} con placa · "
                  f"{len(reportan)} reportaron en el ultimo dia · "
                  f"{sum(1 for e in estados if e.get('encendida') is not None)} "
                  "mandan encendido · "
                  f"{sum(1 for e in estados if e.get('lat') is not None)} "
                  "con posicion")

            # Con la flota de esta base: cuantas ligarian por placa.
            pais = paises.get(codigo)
            flota = set()
            if pais:
                flota = {reglas.normal_placa(v.placa) for v in (
                    db.query(m.Vehiculo)
                    .join(m.Plaza, m.Vehiculo.plaza_id == m.Plaza.id)
                    .filter(m.Plaza.pais_id == pais.id,
                            m.Vehiculo.activo.is_(True)).all())}
            placas = [e["placa_normal"] for e in con_placa]
            repetidas = {p for p in placas if placas.count(p) > 1}
            ligan = sum(1 for p in placas if p in flota and p not in repetidas)
            print(f"   con la flota de esta base ({len(flota)} unidades): "
                  f"{ligan} ligarian por placa · {len(repetidas)} placas "
                  "repetidas en Pegasus")

            # Una sola tanda: para el ensayo alcanza con 25 unidades.
            ids = [e["pegasus_id"] for e in reportan][:POR_LLAMADA]
            if not ids:
                continue
            try:
                eventos = cliente.eventos(
                    ids, dia,
                    etiquetas=",".join((reglas.PANICO, reglas.EXCESO,
                                        *reglas.BRUSCOS)),
                    campos="vid,event_time,label", tope=2000)
                con_hora = sum(1 for e in eventos
                               if reglas.momento(e.get("event_time")))
                cuenta = _por_etiqueta(eventos)
                conocidas = (reglas.PANICO, reglas.EXCESO, *reglas.BRUSCOS)
                otros = len(eventos) - sum(cuenta.get(x, 0) for x in conocidas)
                print(f"   eventos del ultimo dia ({len(ids)} unidades): "
                      f"panico {cuenta.get(reglas.PANICO, 0)} · "
                      f"excesos {cuenta.get(reglas.EXCESO, 0)} · "
                      f"bruscos {sum(cuenta.get(b, 0) for b in reglas.BRUSCOS)}"
                      f" · otros {otros} · con hora legible {con_hora} "
                      f"de {len(eventos)}")
            except NoResponde as e:
                print(f"   eventos: no los leyo ({e})")
            try:
                crudos = cliente.tramos(ids, dia)
                tramos = reglas.tramos_ordenados(crudos)
                trayectos = [t for t in tramos if t["movimiento"]]
                print(f"   tramos del ultimo dia: {len(crudos)} leidos · "
                      f"{len(tramos)} con hora legible · "
                      f"{len(trayectos)} trayectos y "
                      f"{len(tramos) - len(trayectos)} paradas · "
                      f"{sum(t['km'] for t in trayectos):,.0f} km")
            except NoResponde as e:
                print(f"   tramos: no los leyo ({e})")

    print(f"\nLlamadas a Pegasus: {cliente.llamadas}. No se escribio nada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

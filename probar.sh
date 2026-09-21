#!/bin/bash
# Corre la bateria de pruebas dentro del contenedor, contra su propia base.
#   ./probar.sh              todas
#   ./probar.sh candados     solo las de un archivo
#   ./probar.sh -k geocerca  solo las que coincidan con un nombre
set -e
cd "$(dirname "$0")"

# Esperar a que los archivos dejen de caer.
#
# Esto ya costo TRES corridas de diez minutos. pytest arma la lista y
# carga los modulos al arrancar; si la bateria empieza mientras todavia
# estan cayendo archivos, corre una mezcla de version vieja y nueva
# --y para rematar, imprime los renglones del archivo NUEVO en el
# traceback, porque relee la fuente al reportar--. El resultado se lee
# como si el arreglo no hubiera servido, cuando lo que paso es que se
# probo otra cosa.
#
# El conteo del arbol no lo alcanza a ver cuando se editan pruebas que
# ya existian, que es justo el caso mas comun. Esto si: se toma la
# huella del contenido y se espera a que no cambie.
# Las migraciones entran en la huella: la bateria construye la base
# corriendolas desde cero, asi que una migracion ya escrita con el modelo
# todavia a medias es una corrida que falla por una razon que no existe.
# Paso exactamente eso el 20 de septiembre con el estatus `arribado`.
huella() {
  find backend/app backend/tests backend/migrations -type f -name '*.py' \
    | sort | xargs shasum 2>/dev/null | shasum | cut -d' ' -f1
}

# Cuanto tiene que llevar todo quieto antes de arrancar, y cuantas
# lecturas iguales seguidas hacen falta.
#
# Eran cinco segundos y una sola lectura, y no alcanzaba: entre dos
# ediciones seguidas hay pausas mas largas que eso, asi que la corrida
# arrancaba en una pausa y agarraba el arbol a medias. Cuarenta segundos
# de espera contra diez minutos de corrida es un cambio barato.
QUIETO=20
LECTURAS_IGUALES=2

esperar_archivos_quietos() {
  local antes despues iguales=0 intentos=0
  # Se dice ANTES de esperar. Sin esto, la terminal se queda callada
  # cuarenta segundos antes de la primera linea y parece colgada.
  echo "Esperando a que los archivos se queden quietos (${QUIETO}s)..."
  antes=$(huella)
  while [ "$iguales" -lt "$LECTURAS_IGUALES" ]; do
    sleep "$QUIETO"
    despues=$(huella)
    if [ "$antes" = "$despues" ]; then
      iguales=$((iguales + 1))
    else
      iguales=0
      echo "Todavia estan cayendo archivos. Espero a que se queden quietos..."
    fi
    antes=$despues
    intentos=$((intentos + 1))
    if [ "$intentos" -gt 15 ]; then
      echo "Los archivos llevan cinco minutos cambiando. Arranco de todos modos."
      return 0
    fi
  done
}

# Y si algo cambio MIENTRAS corria, se dice. Una salida de una version
# que ya no existe es peor que ninguna salida: se persiguen fallas que
# nadie puede reproducir, que es lo que paso tres veces.
avisar_si_cambio() {
  if [ "$(huella)" != "$1" ]; then
    echo
    echo "================================================================"
    echo "OJO: los archivos cambiaron MIENTRAS corria la bateria."
    echo "Esta salida es de una version que ya no existe. Vuelve a correr."
    echo "================================================================"
  fi
}

# Cuantas pruebas hay en el arbol, antes de correr nada.
#
# Existe por un error que ya nos costo dos vueltas: pytest arma la lista
# al arrancar, asi que una corrida que empezo antes de que cayera un
# archivo lo ignora entero --y el resultado se lee como si el arreglo no
# hubiera servido, cuando lo que paso es que ni se probo--. Con el
# numero del arbol arriba y el de pytest abajo, la diferencia salta.
contar_del_arbol() {
  docker compose exec -T api python3 - <<'PYCONTEO' 2>/dev/null || true
import ast, pathlib
total = 0
for p in sorted(pathlib.Path("tests").glob("test_*.py")):
    arbol = ast.parse(p.read_text(encoding="utf-8"))
    total += sum(1 for x in ast.walk(arbol)
                 if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and x.name.startswith("test_"))
print(f"En el arbol hay {total} pruebas. Si pytest cuenta menos, "
      f"la corrida empezo antes de que cayera algun archivo.")
PYCONTEO
}

# Todo el trabajo vive dentro de una funcion, y la ultima linea la
# llama. No es estilo: bash lee un script POR PEDAZOS mientras lo
# ejecuta, asi que si el archivo cambia durante una corrida de diez
# minutos --que es justo lo que pasa aqui, porque este archivo se edita
# mientras la bateria corre-- bash vuelve al desplazamiento en bytes
# donde se quedo, cae a media instruccion y muere con un "unexpected
# EOF" que no tiene nada que ver con las pruebas. Envuelto asi, bash
# parsea el archivo completo antes de ejecutar nada y editarlo a media
# corrida deja de importar.
main() {
  if [ -z "$1" ]; then
    esperar_archivos_quietos
    contar_del_arbol
    antes_de_correr=$(huella)
    # `set -e` esta arriba: sin esto, una bateria en rojo se saltaria el
    # aviso, que es justo cuando mas falta hace saber si la salida es de
    # esta version o de otra.
    codigo=0
    docker compose exec -T api pytest || codigo=$?
    avisar_si_cambio "$antes_de_correr"
    return "$codigo"
  elif [ "$1" = "-k" ]; then
    docker compose exec -T api pytest -k "$2"
  else
    docker compose exec -T api pytest "tests/test_$1.py"
  fi
}

main "$@"

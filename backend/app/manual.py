# -*- coding: utf-8 -*-
"""El manual del sistema (seccion 90).

Decision de Salvador, 27 de septiembre: un manual para que Aridiai
conozca todo el sistema y, si algo se atora, sepa resolverlo y entender
la causa de fondo. Guardado en el mismo sistema y al dia con cada
actualizacion; en espanol y en portugues.

Un PDF suelto se queda viejo el dia que cambia una pantalla. Por eso el
manual vive aqui, viaja con el codigo y tiene tres clases de contenido:

  * **Lo escrito**, en `backend/manual/<idioma>/*.md`: como funciona cada
    pieza y los sintomas de cuando algo se atora. Un capitulo por
    archivo, con su cabeza (`id`, `parte`, `orden`, `titulo`...) y un
    Markdown corto que aqui se vuelve bloques. La pantalla los pinta con
    `h()`: nada de lo escrito entra como HTML.
  * **Lo que sale solo del sistema**: el reloj --las tareas que corren
    solas, leidas de `celery_app`, con su ultima vuelta--, quien puede
    que --de `permisos.py` y de los puestos--, los mensajes de «no se
    puede» con su que hacer --cosechados del propio codigo-- y las
    novedades de cada actualizacion.
  * **El estado del sistema, en vivo**: la base, el reloj, el correo,
    Odoo, el GPS y los avisos al telefono.

Lo que no se puede sacar del sistema tiene candado en las pruebas
(test_manual.py): una tarea del reloj sin su renglon aqui, una pantalla
sin su parte en el capitulo de las pantallas, un archivo con mensajes
sin su area o una seccion de la bitacora sin su novedad no pasan.
"""
import ast
import functools
import pathlib
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import models as m

CARPETA = pathlib.Path(__file__).resolve().parent.parent / "manual"
APP = pathlib.Path(__file__).resolve().parent
IDIOMAS = ("es", "pt")
PARTES = ("entender", "resolver")


def idioma_de(pedido: str | None) -> str:
    """El manual esta en espanol y en portugues; en ingles se lee en
    espanol (decision de Salvador, 27 sep)."""
    return "pt" if (pedido or "").strip().lower().startswith("pt") else "es"


def _utc() -> datetime:
    return datetime.now(timezone.utc)


# ================================================================ lo escrito

NEGRITA_O_LIGA = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)\s]+)\)")
ANCLA = re.compile(r"\s*\{#([a-z0-9_-]+)\}\s*$")
NUMERADO = re.compile(r"^\d+\.\s+")


def renglon(texto: str) -> list[dict]:
    """Un renglon con sus negritas y sus ligas, en pedazos.

    Solo se liga a otra pantalla de la consola (`#/...`): una direccion
    de afuera se queda como texto. Lo que no cierra se deja tal cual.
    """
    partes, i = [], 0
    for x in NEGRITA_O_LIGA.finditer(texto):
        if x.start() > i:
            partes.append({"t": texto[i:x.start()]})
        if x.group(1) is not None:
            partes.append({"t": x.group(1), "b": True})
        elif x.group(3).startswith("#/"):
            partes.append({"t": x.group(2), "a": x.group(3)})
        else:
            partes.append({"t": x.group(2)})
        i = x.end()
    if i < len(texto):
        partes.append({"t": texto[i:]})
    return partes


def bloques(cuerpo: str) -> list[dict]:
    """El Markdown corto del manual, en bloques.

    Lo que entiende: `##` y `###` (con `{#ancla}` opcional), parrafos,
    listas con `-` o numeradas, y `>` para la nota que se ve en su caja
    --la causa de fondo, un cuidado--. Dentro del renglon, `**negrita**`
    y `[texto](#/pantalla)`.
    """
    salida: list[dict] = []
    parrafo: list[str] = []
    nota: list[str] = []
    # La lista abierta: si es numerada y sus renglones, todavia en crudo.
    lista: dict | None = None

    def cerrar():
        nonlocal lista
        if parrafo:
            salida.append({"tipo": "p", "partes": renglon(" ".join(parrafo))})
            parrafo.clear()
        if nota:
            salida.append({"tipo": "nota", "partes": renglon(" ".join(nota))})
            nota.clear()
        if lista is not None:
            salida.append({"tipo": "lista", "numerada": lista["numerada"],
                           "items": [renglon(x) for x in lista["items"]]})
            lista = None

    for crudo in cuerpo.splitlines():
        linea = crudo.strip()
        if not linea:
            cerrar()
            continue
        if linea.startswith("#"):
            cerrar()
            nivel = len(linea) - len(linea.lstrip("#"))
            titulo = linea[nivel:].strip()
            ancla = ANCLA.search(titulo)
            bloque = {"tipo": "h3" if nivel >= 3 else "h2",
                      "texto": ANCLA.sub("", titulo).strip()}
            if ancla:
                bloque["ancla"] = ancla.group(1)
            salida.append(bloque)
            continue
        if linea.startswith(">"):
            if parrafo or lista is not None:
                cerrar()
            nota.append(linea.lstrip(">").strip())
            continue
        vineta = linea.startswith("- ")
        numero = NUMERADO.match(linea)
        if vineta or numero:
            if parrafo or nota:
                cerrar()
            numerada = bool(numero)
            if lista is not None and lista["numerada"] != numerada:
                cerrar()
            if lista is None:
                lista = {"numerada": numerada, "items": []}
            lista["items"].append(
                (linea[2:] if vineta else linea[numero.end():]).strip())
            continue
        if lista is not None and crudo[:1] in (" ", "\t"):
            # La continuacion del ultimo renglon de la lista.
            lista["items"][-1] += " " + linea
            continue
        if nota:
            nota.append(linea)
            continue
        if lista is not None:
            cerrar()
        parrafo.append(linea)
    cerrar()
    return salida


def capitulo(texto: str, archivo: str = "") -> dict:
    """Un archivo del manual: su cabeza entre `---` y su cuerpo."""
    if not texto.startswith("---"):
        raise ValueError(f"{archivo}: le falta la cabeza entre ---")
    _, cabeza, cuerpo = texto.split("---", 2)
    datos: dict = {}
    for linea in cabeza.strip().splitlines():
        if ":" not in linea:
            continue
        llave, valor = linea.split(":", 1)
        datos[llave.strip()] = valor.strip()
    for llave in ("id", "parte", "titulo"):
        if not datos.get(llave):
            raise ValueError(f"{archivo}: le falta «{llave}» en la cabeza")
    if datos["parte"] not in PARTES:
        raise ValueError(f"{archivo}: la parte «{datos['parte']}» no existe")
    return {
        "id": datos["id"],
        "parte": datos["parte"],
        "orden": int(datos.get("orden") or 0),
        "titulo": datos["titulo"],
        "resumen": datos.get("resumen") or "",
        "area": datos.get("area") or "",
        "buscar": datos.get("buscar") or "",
        "bloques": bloques(cuerpo),
    }


@functools.lru_cache(maxsize=4)
def capitulos(idioma: str) -> tuple:
    """Los capitulos escritos de un idioma, en su orden. Se leen una vez:
    cambian con el codigo, no mientras corre."""
    carpeta = CARPETA / idioma
    salida = [capitulo(f.read_text(encoding="utf-8"), f.name)
              for f in sorted(carpeta.glob("*.md"))]
    return tuple(sorted(salida, key=lambda c: (PARTES.index(c["parte"]),
                                               c["orden"], c["id"])))


def anclas(cap: dict) -> list[str]:
    return [b["ancla"] for b in cap["bloques"] if b.get("ancla")]


def ligas(cap: dict) -> list[str]:
    """Las ligas a otras pantallas que trae un capitulo."""
    salida = []
    for b in cap["bloques"]:
        grupos = ([b.get("partes") or []]
                  + list(b.get("items") or []))
        for partes in grupos:
            salida.extend(p["a"] for p in partes if p.get("a"))
    return salida


# ================================================================ el reloj

# Lo que hace cada tarea del reloj y que se revisa si no paso, en los dos
# idiomas. La llave es el nombre de la tarea en `celery_app` (el de la
# izquierda del calendario): una tarea nueva sin su renglon aqui no pasa
# las pruebas, y asi el manual no se entera tarde.
TAREAS = {
    "gps-leer": {
        "es": ("GPS: lee Pegasus. El pánico de la unidad, el camino al punto, "
               "la corriente y el segundo testigo de las "
               "marcas. Sin nadie en la calle, las posiciones cada 15 minutos.",
               "El usuario de Pegasus en el servidor y la tarjeta del GPS en "
               "el estado del sistema."),
        "pt": ("GPS: lê o Pegasus. O pânico da unidade, o caminho até o ponto, "
               "a corrente e a segunda testemunha das marcas. "
               "Sem ninguém na rua, as posições a cada 15 minutos.",
               "O usuário do Pegasus no servidor e o cartão do GPS no estado "
               "do sistema."),
    },
    "correo-pendiente": {
        "es": ("Correo: saca los avisos que esperan. Los operativos de más "
               "de 24 horas ya no salen; la invitación y la encuesta viven lo "
               "que vive su enlace. Si el proveedor no contesta, espera y "
               "vuelve a intentar.",
               "El correo en el estado del sistema: si está apagado, no sale "
               "ninguno."),
        "pt": ("E-mail: envia os avisos que estão esperando. Os operacionais "
               "com mais de 24 horas já não saem; o convite e a pesquisa vivem "
               "o que vive o seu link. Se o provedor não responde, espera e "
               "tenta de novo.",
               "O e-mail no estado do sistema: se estiver desligado, não sai "
               "nenhum."),
    },
    "camino-al-punto": {
        "es": ("El camino al punto: los toques al personal que va al meet and "
               "greet, y sus silencios.",
               "Que el personal tenga la app con los avisos encendidos."),
        "pt": ("O caminho até o ponto: os toques ao pessoal que vai ao meet "
               "and greet, e os seus silêncios.",
               "Que o pessoal tenha o app com os avisos ligados."),
    },
    "jornadas-proximas": {
        "es": ("Lo que arranca pronto: lo de las próximas 2 horas pasa a "
               "«próxima a iniciar», y la central toma el seguimiento.",
               "El reloj, en el estado del sistema."),
        "pt": ("O que começa logo: o das próximas 2 horas passa a «prestes "
               "a começar», e a central assume o acompanhamento.",
               "O relógio, no estado do sistema."),
    },
    "aviso-horas-extra": {
        "es": ("Horas extra: avisa 30 minutos antes de que el servicio cumpla "
               "sus horas contratadas.",
               "El reloj y el correo, en el estado del sistema."),
        "pt": ("Horas extras: avisa 30 minutos antes de o serviço completar "
               "as horas contratadas.",
               "O relógio e o e-mail, no estado do sistema."),
    },
    "cierre-avanzar": {
        "es": ("El cierre: cuando vencen las 24 horas del personal para "
               "comprobar —o antes, si todo su dinero ya cerró— el servicio "
               "pasa a esperar el visto bueno del consultor, y arrancan sus "
               "24 horas. A la mitad de ese plazo le avisa al consultor y, "
               "al vencer, al consultor y a dirección de operaciones.",
               "El reloj y el correo, en el estado del sistema."),
        "pt": ("O fechamento: quando vencem as 24 horas do pessoal para "
               "comprovar —ou antes, se todo o dinheiro já fechou— o serviço "
               "passa a esperar o aval do consultor, e começam as suas "
               "24 horas. Na metade desse prazo avisa o consultor e, ao "
               "vencer, o consultor e a direção de operações.",
               "O relógio e o e-mail, no estado do sistema."),
    },
    "servicios-sin-reporte": {
        "es": ("Silencios: el servicio en curso que lleva 2 horas sin "
               "reportar le levanta una alerta a la central.",
               "El reloj, en el estado del sistema."),
        "pt": ("Silêncios: o serviço em curso que está há 2 horas sem "
               "reportar gera um alerta para a central.",
               "O relógio, no estado do sistema."),
    },
    "nomina-del-lunes": {
        "es": ("El corte del lunes: a las 7:00 de cada país arma el borrador "
               "y a las 11:00 queda listo para pagar. Si el corte de la "
               "semana anterior no se pagó, el nuevo se lo lleva.",
               "El reloj; el pago lo marca finanzas."),
        "pt": ("O corte de segunda-feira: às 7:00 de cada país monta o "
               "rascunho e às 11:00 fica pronto para pagar. Se o corte da "
               "semana anterior não foi pago, o novo o absorve.",
               "O relógio; o pagamento é marcado pelo financeiro."),
    },
    "confirmacion-de-la-vispera": {
        "es": ("La víspera: a las 5 de la tarde de cada país le recuerda a "
               "cada quien que mañana trabaja.",
               "Que la persona tenga la app con los avisos encendidos."),
        "pt": ("A véspera: às 5 da tarde de cada país lembra a cada um que "
               "trabalha amanhã.",
               "Que a pessoa tenha o app com os avisos ligados."),
    },
    "hora-de-manana-propuesta": {
        "es": ("La hora de mañana: la que propuso el equipo y la central no "
               "confirmó ni rechazó antes de las 10 de la noche de cada país "
               "queda como la capturó el conductor.",
               "La banda «Mañana» de la central: las propuestas pendientes "
               "se confirman o se dejan ahí."),
        "pt": ("O horário de amanhã: o que a equipe propôs e a central não "
               "confirmou nem recusou antes das 10 da noite de cada país "
               "fica como o motorista registrou.",
               "A faixa «Amanhã» da central: as propostas pendentes se "
               "confirmam ou se deixam ali."),
    },
    "odoo-personal": {
        "es": ("Odoo: el personal de seguridad. Solo corre después de la "
               "primera lectura hecha a mano.",
               "La tarjeta de Odoo: la llave y la primera lectura."),
        "pt": ("Odoo: o pessoal de segurança. Só roda depois da primeira "
               "leitura feita à mão.",
               "O cartão do Odoo: a chave e a primeira leitura."),
    },
    "odoo-flota": {
        "es": ("Odoo: la flota y el taller. Solo corre después de la primera "
               "lectura hecha a mano.",
               "La tarjeta de Odoo: la llave y la primera lectura."),
        "pt": ("Odoo: a frota e a oficina. Só roda depois da primeira leitura "
               "feita à mão.",
               "O cartão do Odoo: a chave e a primeira leitura."),
    },
    "odoo-oficina": {
        "es": ("Odoo: el personal de oficina. Solo corre después de la "
               "primera lectura hecha a mano.",
               "La tarjeta de Odoo: la llave y la primera lectura."),
        "pt": ("Odoo: o pessoal de escritório. Só roda depois da primeira "
               "leitura feita à mão.",
               "O cartão do Odoo: a chave e a primeira leitura."),
    },
    "odoo-clientes": {
        "es": ("Odoo: los clientes, las empresas con la etiqueta «Protección "
               "ejecutiva». Solo corre después de la primera lectura a mano.",
               "La tarjeta de Odoo: la llave y la primera lectura."),
        "pt": ("Odoo: os clientes, as empresas com a etiqueta «Protección "
               "ejecutiva». Só roda depois da primeira leitura à mão.",
               "O cartão do Odoo: a chave e a primeira leitura."),
    },
    "odoo-tarifarios": {
        "es": ("Odoo: los tarifarios, después de los clientes. Solo corre "
               "después de la primera lectura hecha a mano.",
               "La tarjeta de Odoo: la llave y la primera lectura."),
        "pt": ("Odoo: as tabelas de preços, depois dos clientes. Só roda "
               "depois da primeira leitura feita à mão.",
               "O cartão do Odoo: a chave e a primeira leitura."),
    },
    "odoo-prefacturas": {
        "es": ("Odoo: vuelve a mandar las prefacturas con visto bueno que no "
               "llegaron a Odoo --Odoo no contestó, faltaba un dato, la "
               "anterior seguía viva--, sin duplicar. Sin la llave de la "
               "factura no hace nada.",
               "Facturación → «No se pudo mandar»: lo que sigue ahí y por qué."),
        "pt": ("Odoo: volta a enviar as pré-faturas com visto bom que não "
               "chegaram ao Odoo --o Odoo não respondeu, faltava um dado, a "
               "anterior seguia viva--, sem duplicar. Sem a chave da fatura "
               "não faz nada.",
               "Faturamento → «Não foi possível enviar»: o que continua lá e "
               "por quê."),
    },
    "gps-cerrar-dias": {
        "es": ("GPS: cierra el día de cada unidad, con sus kilómetros y su "
               "manejo, dos horas después del fin.",
               "Que la unidad esté ligada a su GPS."),
        "pt": ("GPS: fecha o dia de cada unidade, com os seus quilômetros e "
               "a sua condução, duas horas depois do fim.",
               "Que a unidade esteja ligada ao seu GPS."),
    },
    "archivo-de-comprobantes": {
        "es": ("El archivo: muda las fotos de los comprobantes de lo "
               "facturado hace tres meses. Sin su destino en el servidor, "
               "no hace nada.",
               "El destino del archivo en el servidor."),
        "pt": ("O arquivo: muda as fotos dos comprovantes do que foi "
               "faturado há três meses. Sem o seu destino no servidor, não "
               "faz nada.",
               "O destino do arquivo no servidor."),
    },
    "reloj-reponer-diarias": {
        "es": ("La red de las diarias: cada media hora revisa cuál de las "
               "de una vez al día no corrió a su hora —el reloj reiniciado "
               "en ese minuto— y la vuelve a mandar.",
               "El reloj, en el estado del sistema."),
        "pt": ("A rede das diárias: a cada meia hora revisa qual das de uma "
               "vez por dia não rodou na sua hora —o relógio reiniciado nesse "
               "minuto— e a manda de novo.",
               "O relógio, no estado do sistema."),
    },
    "implantados-mes-siguiente": {
        "es": ("Implantados: abre el mes siguiente cuando al mes en curso le "
               "quedan pocos días.",
               "El reloj; que el implantado siga vigente."),
        "pt": ("Implantados: abre o mês seguinte quando faltam poucos dias "
               "para o mês em curso acabar.",
               "O relógio; que o implantado continue vigente."),
    },
    "certificados-por-vencer": {
        "es": ("Certificados: avisa a los 30 días y el día que vence.",
               "Que el certificado tenga su fecha de vencimiento."),
        "pt": ("Certificados: avisa aos 30 dias e no dia em que vence.",
               "Que o certificado tenha a sua data de vencimento."),
    },
    # El expediente del freelance (seccion 111).
    "freelance-por-vencer": {
        "es": ("Freelance: a Recursos Humanos le avisa lo que vence en 30 "
               "días, lo que vence hoy y el plazo del de emergencia que se "
               "cumplió.",
               "Personal de seguridad → Freelance, con el filtro del "
               "expediente."),
        "pt": ("Freelance: avisa ao RH o que vence em 30 dias, o que vence "
               "hoje e o prazo do de emergência que se cumpriu.",
               "Pessoal de segurança → Freelance, com o filtro do "
               "prontuário."),
    },
    "freelance-archivos": {
        "es": ("Freelance: muda al depósito de Google los archivos del "
               "expediente que se quedaron en la base. Sin "
               "EXPEDIENTES_DESTINO no hace nada.",
               "El renglón EXPEDIENTES_DESTINO del .env del servidor."),
        "pt": ("Freelance: leva para o depósito do Google os arquivos do "
               "prontuário que ficaram no banco. Sem EXPEDIENTES_DESTINO "
               "não faz nada.",
               "A linha EXPEDIENTES_DESTINO do .env do servidor."),
    },
    "cotizaciones-vencidas": {
        "es": ("Cotizaciones: la que se le mandó al cliente y pasó su «válida "
               "hasta» sin respuesta queda vencida. El cliente todavía la "
               "puede autorizar; la lista deja de contarla como abierta.",
               "Cotizaciones: la pestaña de rechazadas y vencidas."),
        "pt": ("Cotações: a que foi enviada ao cliente e passou da sua "
               "«válida até» sem resposta fica vencida. O cliente ainda pode "
               "aprová-la; a lista deixa de contá-la como aberta.",
               "Cotações: a aba de recusadas e vencidas."),
    },
    "encuestas-pasar-lista": {
        "es": ("Encuestas: le recuerda a quien lleva 5 días sin contestar y "
               "vence lo que pasó de 15.",
               "El correo, en el estado del sistema."),
        "pt": ("Pesquisas: lembra a quem está há 5 dias sem responder e vence "
               "o que passou de 15.",
               "O e-mail, no estado do sistema."),
    },
    "estrellas-del-mes": {
        "es": ("Las estrellas del mes: el bono de cada persona, del mes que "
               "acaba de cerrar. El día 3 y no el 1, porque el viático del "
               "último día tiene 24 horas para comprobarse.",
               "Desempeño: el mes y sus estrellas."),
        "pt": ("As estrelas do mês: o bônus de cada pessoa, do mês que "
               "acabou de fechar. No dia 3 e não no dia 1, porque a diária do "
               "último dia tem 24 horas para ser comprovada.",
               "Desempenho: o mês e as suas estrelas."),
    },
}

# El respaldo de la base no es del reloj: lo corre el servidor a las 2:30
# (despliegue/LEEME.md). Se ensena en la misma tabla porque es lo primero
# que alguien pregunta despues de un susto.
RESPALDO = {
    "es": ("El respaldo de la base: lo corre el servidor, fuera del reloj; "
           "a las 3:00 se toma además la foto del disco.",
           "El registro del respaldo en el servidor: lo revisa Salvador."),
    "pt": ("O backup do banco: quem roda é o servidor, fora do relógio; às "
           "3:00 também se tira a foto do disco.",
           "O registro do backup no servidor: quem revisa é o Salvador."),
}

GRUPOS_RELOJ = {
    "siempre": {"es": "Todo el día", "pt": "O dia todo"},
    "hora": {"es": "Cada hora", "pt": "A cada hora"},
    "dia": {"es": "Cada día", "pt": "Todo dia"},
    "mes": {"es": "Cada mes", "pt": "Todo mês"},
}


def _entero(valor) -> int | None:
    texto = str(valor).strip()
    return int(texto) if texto.isdigit() else None


def cuando(calendario, idioma: str) -> tuple:
    """(grupo, orden, texto) de un calendario del reloj: «Cada 5 min»,
    «:17», «6:30», «Día 3, 5:00». Las horas son las de Mexico, que es
    el reloj del servidor."""
    minuto = str(calendario._orig_minute)
    hora = str(calendario._orig_hour)
    dia = str(calendario._orig_day_of_month)
    if minuto.startswith("*/") and hora == "*":
        cada = int(minuto[2:])
        return ("siempre", (0, cada, 0),
                f"Cada {cada} min" if idioma == "es" else f"A cada {cada} min")
    mm, hh, dd = _entero(minuto), _entero(hora), _entero(dia)
    if mm is not None and hora == "*":
        texto = ((":00 · en punto" if idioma == "es" else ":00 · hora cheia")
                 if mm == 0 else f":{mm:02d}")
        return ("hora", (1, mm, 0), texto)
    if mm is not None and hh is not None and dd is None:
        return ("dia", (2, hh, mm), f"{hh}:{mm:02d}")
    if mm is not None and hh is not None and dd is not None:
        return ("mes", (3, dd, hh * 60 + mm),
                f"Día {dd}, {hh}:{mm:02d}" if idioma == "es"
                else f"Dia {dd}, {hh}:{mm:02d}")
    return ("siempre", (9, 0, 0), f"{minuto} {hora} {dia}")


def anotar_vuelta(tarea: str, empezo: datetime | None = None,
                  termino: datetime | None = None, error: str | None = None,
                  nota: str | None = None,
                  db: Session | None = None) -> None:
    """La vuelta de una tarea del reloj, para saber cuando corrio.

    La anota el propio reloj (celery_app, al empezar y al terminar cada
    tarea). Una fila por tarea, que se sobreescribe: no es un historial,
    es el «ultima vez». El ultimo error se queda aunque la siguiente
    vuelta salga bien, con su hora: un error de anoche explica un hueco
    de hoy.
    """
    from sqlalchemy.dialects.postgresql import insert

    from app.db import SessionLocal

    propia = db is None
    db = db or SessionLocal()
    try:
        T = m.VueltaDelReloj
        valores: dict = {}
        if empezo is not None:
            valores["empezo_en"] = empezo
        if termino is not None:
            valores["termino_en"] = termino
            valores["estado"] = "error" if error else "ok"
            valores["nota"] = (nota or None) and nota[:200]
        if error:
            valores["error"] = error[:300]
            valores["error_en"] = termino or empezo or _utc()
        orden = insert(T).values(tarea=tarea[:80], vueltas=1 if termino else 0,
                                 **valores)
        cambios = dict(valores)
        if termino is not None:
            cambios["vueltas"] = T.vueltas + 1
        orden = orden.on_conflict_do_update(index_elements=[T.tarea],
                                            set_=cambios or {"tarea": tarea[:80]})
        db.execute(orden)
        db.commit()
    finally:
        if propia:
            db.close()


# Mas de esto sin que ninguna tarea termine y el reloj esta parado: hay
# tareas cada dos y cada cinco minutos.
RELOJ_PARADO = timedelta(minutes=12)


def reloj(db: Session, idioma: str) -> list[dict]:
    """Las tareas del reloj con lo que hacen, cuando y su ultima vuelta."""
    from app.celery_app import celery

    vueltas = {v.tarea: v for v in db.query(m.VueltaDelReloj).all()}
    salida = []
    for nombre, entrada in celery.conf.beat_schedule.items():
        grupo, orden, texto = cuando(entrada["schedule"], idioma)
        que, revisa = (TAREAS.get(nombre) or {}).get(idioma) or ("", "")
        v = vueltas.get(entrada["task"])
        salida.append({
            "clave": nombre, "tarea": entrada["task"], "grupo": grupo,
            "grupo_titulo": GRUPOS_RELOJ[grupo][idioma],
            "orden": list(orden), "cuando": texto, "que": que,
            "revisa": revisa,
            "ultima": _vuelta(v, idioma),
        })
    que, revisa = RESPALDO[idioma]
    salida.append({"clave": "respaldo", "tarea": None, "grupo": "dia",
                   "grupo_titulo": GRUPOS_RELOJ["dia"][idioma],
                   "orden": [2, 2, 30], "cuando": "2:30", "que": que,
                   "revisa": revisa, "ultima": None, "fuera": True})
    salida.sort(key=lambda x: x["orden"])
    return salida


# Lo que dicen las tareas cuando no hacen nada, dicho para quien lee.
NOTAS = {
    "falta la primera lectura a mano": {
        "es": "Espera la primera lectura a mano",
        "pt": "Espera a primeira leitura à mão"},
    "falta la primera sincronizacion a mano": {
        "es": "Espera la primera lectura a mano",
        "pt": "Espera a primeira leitura à mão"},
    "Odoo no esta conectado": {
        "es": "Sin la llave de Odoo", "pt": "Sem a chave do Odoo"},
    "sin EXPEDIENTES_DESTINO": {
        "es": "Sin el depósito de los expedientes",
        "pt": "Sem o depósito dos prontuários"},
}


def _vuelta(v, idioma: str = "es") -> dict | None:
    if v is None:
        return None
    nota = (NOTAS.get(v.nota) or {}).get(idioma, v.nota) if v.nota else None
    return {"empezo_en": v.empezo_en.isoformat() if v.empezo_en else None,
            "termino_en": v.termino_en.isoformat() if v.termino_en else None,
            "estado": v.estado, "vueltas": v.vueltas,
            "nota": nota,
            "error": v.error,
            "error_en": v.error_en.isoformat() if v.error_en else None}


# ================================================================ los mensajes

# Cada archivo que dice «no se puede» con su que hacer, a que area del
# manual pertenece. Un archivo nuevo con mensajes y sin su area no pasa
# las pruebas: sus mensajes se quedarian fuera sin que nadie lo viera.
AREAS = {
    "operacion": {"es": "Operación y central", "pt": "Operação e central"},
    "accesos": {"es": "Accesos y contraseñas", "pt": "Acessos e senhas"},
    "campo": {"es": "App de campo", "pt": "App de campo"},
    "viaticos": {"es": "Viáticos y depósitos", "pt": "Diárias e depósitos"},
    "horas_extra": {"es": "Horas extra", "pt": "Horas extras"},
    "implantados": {"es": "Implantados", "pt": "Implantados"},
    "cierre": {"es": "Cierre y facturación", "pt": "Fechamento e faturamento"},
    "nomina": {"es": "Nómina y comisiones", "pt": "Folha e comissões"},
    "cotizacion": {"es": "Cotización y tarifarios",
                   "pt": "Cotação e tabelas de preços"},
    "servicios": {"es": "Servicios, task sheet y relevos",
                  "pt": "Serviços, task sheet e substituições"},
    "catalogos": {"es": "Catálogos", "pt": "Catálogos"},
    "odoo": {"es": "Odoo", "pt": "Odoo"},
    "archivo": {"es": "Archivo de comprobantes",
                "pt": "Arquivo de comprovantes"},
    "freelance": {"es": "Freelance", "pt": "Freelance"},
    "gps": {"es": "GPS y unidades", "pt": "GPS e unidades"},
    "sistema": {"es": "Sistema", "pt": "Sistema"},
}

AREA_DE_ARCHIVO = {
    "operacion.py": "operacion", "routers/operacion.py": "operacion",
    "routers/central.py": "operacion", "central.py": "operacion",
    "geocercas.py": "operacion", "intentos.py": "operacion",
    # La ventana del director de operaciones (seccion 105).
    "direccion_operaciones.py": "operacion", "routers/direccion.py": "operacion",
    "accesos.py": "accesos", "auth.py": "accesos", "contrasenas.py": "accesos",
    "routers/acceso.py": "accesos",
    # Entrar con huella o cara (seccion 110).
    "llaves.py": "accesos", "routers/llaves.py": "accesos",
    "routers/campo.py": "campo",
    "bolson.py": "viaticos", "viaticos.py": "viaticos",
    "routers/viaticos.py": "viaticos", "depositos.py": "viaticos",
    "devoluciones.py": "viaticos",
    "horas_extra.py": "horas_extra",
    "implantado.py": "implantados", "routers/implantados.py": "implantados",
    "hoja_implantado.py": "implantados", "cierre_mes.py": "implantados",
    "cierre.py": "cierre", "revision.py": "cierre", "revisor.py": "cierre",
    "historial.py": "cierre", "facturacion.py": "cierre",
    # La entrega de la unidad despues del fin (seccion 107): sus "no se
    # puede" son del cierre, que es quien la reclama.
    "entregas.py": "cierre",
    # El cierre y las encuestas ganaron sus "que hacer" (seccion 101):
    # justificar una desviacion, mandar la encuesta que falta.
    "routers/cierre.py": "cierre", "encuestas.py": "cierre",
    "routers/encuestas.py": "cierre",
    "comisiones.py": "nomina", "nomina.py": "nomina",
    "routers/nomina.py": "nomina", "routers/bonos.py": "nomina",
    "bonos.py": "nomina",
    "cotizacion.py": "cotizacion", "tipo_cambio.py": "cotizacion",
    # Cotizaciones: la que se arma en Connect y su PDF (seccion 114).
    "cotizacion_cliente.py": "cotizacion",
    "routers/cotizaciones.py": "cotizacion",
    # Y la propuesta del implantado, en la misma pantalla (seccion 115).
    "propuesta.py": "cotizacion", "routers/propuestas.py": "cotizacion",
    "routers/tarifarios.py": "cotizacion",
    "routers/servicios.py": "servicios", "routers/tasksheet.py": "servicios",
    "routers/contingencia.py": "servicios",
    # El choque al mover un dia y el motor del cambio por contingencia,
    # que dice que hacer con la hora del relevo y con deshacer (seccion 101).
    "disponibilidad.py": "servicios", "contingencia.py": "servicios",
    # El cambio de consultor titular (decision 13, seccion 105).
    "titular.py": "servicios",
    "routers/crud.py": "catalogos", "routers/bitacora_admin.py": "catalogos",
    "routers/odoo.py": "odoo",
    "routers/archivo.py": "archivo",
    # El freelance: su alta, su expediente y la urgencia (seccion 111).
    "freelance.py": "freelance", "routers/freelance.py": "freelance",
    "implantado_precios.py": "implantados",
    "gps.py": "gps",
    "main.py": "sistema",
    # Reportar una falla (seccion 92) y el manual mismo.
    "fallas.py": "sistema", "routers/manual.py": "sistema",
}

# Un mensaje hecho solo de datos del caso («…: …») no dice nada fuera de
# su pantalla: se queda fuera del manual.
PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}")


def _texto_de(nodo) -> str | None:
    """El texto de un literal tal como sale en pantalla; lo que se arma
    con datos del caso --el nombre, el monto, el dia-- queda como «…»."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "…"
                       for v in nodo.values)
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        izquierda, derecha = _texto_de(nodo.left), _texto_de(nodo.right)
        if izquierda is None and derecha is None:
            return None
        return (izquierda or "…") + (derecha or "…")
    return None


def cosechar(raiz: pathlib.Path = APP) -> list[dict]:
    """Los «no se puede» del codigo: cada diccionario que trae `mensaje` y
    `que_hacer` --o `accion`, en la revision del cierre--. Se leen del
    propio codigo, asi que un mensaje nuevo aparece en el manual sin que
    nadie lo escriba dos veces."""
    salida, vistos = [], set()
    for archivo in sorted(raiz.rglob("*.py")):
        rel = archivo.relative_to(raiz).as_posix()
        try:
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Dict):
                continue
            claves = [k.value if isinstance(k, ast.Constant) else None
                      for k in nodo.keys]
            # `que_hacer` en los candados; `accion` en lo que la revision
            # del cierre le pide al consultor antes de mandar a finanzas.
            hacer = ("que_hacer" if "que_hacer" in claves
                     else "accion" if "accion" in claves else None)
            if "mensaje" not in claves or hacer is None:
                continue
            d = dict(zip(claves, nodo.values))
            mensaje, que_hacer = _texto_de(d["mensaje"]), _texto_de(d[hacer])
            if not mensaje or not que_hacer:
                continue
            if len(PALABRA.findall(mensaje)) < 2:
                continue
            llave = (mensaje, que_hacer)
            if llave in vistos:
                continue
            vistos.add(llave)
            salida.append({"archivo": rel, "linea": nodo.lineno,
                           "area": AREA_DE_ARCHIVO.get(rel),
                           "mensaje": mensaje, "que_hacer": que_hacer})
    return salida


@functools.lru_cache(maxsize=1)
def _cosecha() -> tuple:
    return tuple(cosechar())


def mensajes(idioma: str) -> list[dict]:
    """Los mensajes con el nombre de su area en el idioma del manual. El
    mensaje va como sale en pantalla: el servidor los dice en espanol."""
    salida = []
    for x in _cosecha():
        area = x["area"] or "sistema"
        salida.append({"area": area, "area_titulo": AREAS[area][idioma],
                       "mensaje": x["mensaje"], "que_hacer": x["que_hacer"]})
    orden = list(AREAS)
    salida.sort(key=lambda x: (orden.index(x["area"]), x["mensaje"].lower()))
    return salida


# ================================================================ quien puede que

def permisos_del_sistema(db: Session) -> dict:
    """Cada actividad con su descripcion, los roles que la traen de
    fabrica y los puestos que la traen. La descripcion va como la dice
    `permisos.py`, igual que en la pantalla de Puestos."""
    from app import permisos

    puestos: dict[str, list[str]] = {}
    filas = (db.query(m.ActividadDeCategoria.actividad, m.CategoriaAcceso.nombre)
             .join(m.CategoriaAcceso,
                   m.CategoriaAcceso.id == m.ActividadDeCategoria.categoria_id)
             .filter(m.CategoriaAcceso.activa.is_(True))
             .all())
    for actividad, nombre in filas:
        puestos.setdefault(actividad, []).append(nombre)
    return {
        "actividades": [{"actividad": a["actividad"],
                         "descripcion": a["descripcion"],
                         "roles": a["roles"],
                         "puestos": sorted(puestos.get(a["actividad"], []))}
                        for a in permisos.catalogo()],
        "dos_manos": [list(par) for par in permisos.INCOMPATIBLES],
    }


# ================================================================ las novedades

NOVEDAD = re.compile(r"^##\s+(\d+)\s+·\s+(\d{4}-\d{2}-\d{2})\s+·\s+(.+?)\s*$")
MESES = {"es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
                "oct", "nov", "dic"),
         "pt": ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set",
                "out", "nov", "dez")}


def fecha_corta(iso: str, idioma: str) -> str:
    anio, mes, dia = (int(x) for x in iso.split("-"))
    return f"{dia} {MESES[idioma][mes - 1]} {anio}"


@functools.lru_cache(maxsize=4)
def novedades(idioma: str) -> tuple:
    """Lo nuevo de cada actualizacion, de la mas nueva a la mas vieja.

    Una por seccion de la bitacora, escrita para quien usa el sistema y
    no para quien lo programa. Las pruebas cuidan que cada seccion nueva
    traiga la suya en los dos idiomas: es lo que obliga a que el manual
    se ponga al dia con cada cambio.
    """
    archivo = CARPETA / "novedades" / f"{idioma}.md"
    salida, actual, texto = [], None, []

    def cerrar():
        if actual is not None:
            actual["partes"] = renglon(" ".join(texto).strip())
            salida.append(actual)

    for linea in archivo.read_text(encoding="utf-8").splitlines():
        x = NOVEDAD.match(linea.strip())
        if x:
            cerrar()
            texto = []
            actual = {"seccion": int(x.group(1)), "fecha_iso": x.group(2),
                      "fecha": fecha_corta(x.group(2), idioma),
                      "titulo": x.group(3)}
            continue
        if actual is not None and linea.strip():
            texto.append(linea.strip())
    cerrar()
    return tuple(sorted(salida, key=lambda n: -n["seccion"]))


def version(idioma: str) -> dict:
    """Con que actualizacion esta al dia: la ultima novedad."""
    ultima = novedades(idioma)[0]
    return {"seccion": ultima["seccion"], "fecha": ultima["fecha"],
            "fecha_iso": ultima["fecha_iso"]}


# ================================================================ los casos resueltos

LARGOS = {"titulo": 160, "que_se_vio": 4000, "causa": 4000, "solucion": 4000,
          "area": 60}


# Si la causa fue una falla del sistema. Regla de Salvador (27 sep): la
# falla chica que no cambia nada de como se trabaja se arregla directo y
# se le avisa; la que pide cambiar un proceso lleva primero su propuesta.
# Por eso el caso lo dice: esas son las que tienen que llegar.
FALLAS = ("no", "si", "no_se")


def _iso(momento) -> str | None:
    return momento.isoformat() if momento else None


def caso(c: m.CasoResuelto, nombres: dict, con_captura: set | None = None) -> dict:
    """Un caso, como lo lee la pantalla. El reportado trae ademas quien
    lo mando, lo que esperaba y lo que se mando solo (seccion 92); la
    captura no viaja aqui, se pide aparte."""
    from app import fallas

    contexto = fallas.contexto_de(c)
    quien = contexto.get("quien") or {}
    return {"id": c.id, "titulo": c.titulo, "que_se_vio": c.que_se_vio,
            "causa": c.causa, "solucion": c.solucion, "area": c.area,
            "falla": c.falla, "estado": c.estado or fallas.RESUELTO,
            "escrito_por": nombres.get(c.escrito_por_id),
            "escrito_en": _iso(c.escrito_en),
            "editado_por": nombres.get(c.editado_por_id),
            "editado_en": _iso(c.editado_en),
            "reportado_por": (nombres.get(c.reportado_por_id)
                              or quien.get("nombre") if c.reportado_en else None),
            "reportado_puesto": (quien.get("puesto")
                                 or (quien.get("rol") or "").replace("_", " ")
                                 or None) if c.reportado_en else None,
            "reportado_en": _iso(c.reportado_en),
            "esperaba": c.esperaba,
            "contexto": contexto or None,
            "donde": fallas.donde(contexto) if c.reportado_en else None,
            "tiene_captura": c.id in (con_captura or set()),
            "con_claude_en": _iso(c.con_claude_en),
            "resuelto_por": nombres.get(c.resuelto_por_id),
            "resuelto_en": _iso(c.resuelto_en)}


def casos(db: Session) -> list[dict]:
    """Los abiertos primero --por revisar y con Claude, del mas viejo al
    mas nuevo: el que lleva mas esperando se atiende antes--, y despues
    los resueltos, del mas nuevo al mas viejo."""
    from app import fallas

    filas = db.query(m.CasoResuelto).all()
    nunca = datetime.min.replace(tzinfo=timezone.utc)
    abiertos = sorted((c for c in filas if c.estado in fallas.ABIERTOS),
                      key=lambda c: (c.reportado_en or c.escrito_en or nunca, c.id))
    cerrados = sorted((c for c in filas if c.estado not in fallas.ABIERTOS),
                      key=lambda c: (c.resuelto_en or c.escrito_en or nunca, c.id),
                      reverse=True)
    ids = set()
    for c in filas:
        ids |= {c.escrito_por_id, c.editado_por_id, c.reportado_por_id,
                c.resuelto_por_id}
    ids.discard(None)
    nombres = ({p.id: p.nombre for p in
                db.query(m.Persona).filter(m.Persona.id.in_(ids)).all()}
               if ids else {})
    con_captura = {i for (i,) in db.query(m.CasoResuelto.id)
                   .filter(m.CasoResuelto.captura.isnot(None))}
    return [caso(c, nombres, con_captura) for c in abiertos + cerrados]


def limpiar_caso(datos: dict, parcial: bool = False) -> dict:
    """Lo que se guarda de un caso: sin espacios de sobra y con lo que no
    puede faltar. Un caso sin la causa es una queja, no un caso resuelto."""
    salida = {}
    for campo, largo in LARGOS.items():
        if campo not in datos:
            continue
        valor = (datos.get(campo) or "").strip()
        if len(valor) > largo:
            raise ValueError(f"{campo}: pasa de {largo} letras")
        salida[campo] = valor or None
    if "falla" in datos:
        falla = (datos.get("falla") or "no_se").strip()
        if falla not in FALLAS:
            raise ValueError("falla")
        salida["falla"] = falla
    if not parcial:
        for campo in ("titulo", "que_se_vio", "causa", "solucion"):
            if not salida.get(campo):
                raise ValueError(campo)
    else:
        for campo in ("titulo", "que_se_vio", "causa", "solucion"):
            if campo in salida and not salida[campo]:
                raise ValueError(campo)
    return salida


# ================================================================ el estado del sistema

ESTADO = {
    "es": {
        "base": "Base de datos", "reloj": "El reloj", "correo": "Correo",
        "odoo": "Odoo", "gps": "GPS", "avisos": "Avisos al teléfono",
        "bien": "Bien", "contesta": "Contesta en {ms} ms.",
        "no_contesta": "No contesta",
        "sin_vueltas": "Sin vueltas anotadas",
        "sin_vueltas_t": ("El reloj no ha anotado ninguna vuelta. Si la "
                          "actualización acaba de subir, espera cinco minutos."),
        "parado": "Parado",
        "parado_t": ("La última vuelta fue {hace}: ninguna tarea automática "
                     "está corriendo."),
        "corre": "Última vuelta {hace}",
        "corre_t": "Las {n} tareas automáticas están corriendo.",
        "con_error": "Corre, con {n} en error",
        "con_error_t": "La última vuelta salió con error en: {cuales}.",
        "apagado": "Apagado",
        "apagado_t": "No sale ningún correo. {n} avisos esperando.",
        "sin_proveedor": "Sin proveedor",
        "sin_proveedor_t": ("Está encendido, pero le falta el proveedor o el "
                            "remitente: no sale nada."),
        "encendido": "Encendido",
        "encendido_t": "{n} avisos esperando; {f} fallaron.",
        "solo_internos": "Solo a la empresa",
        "solo_internos_t": ("Sale a consultores, central y personal; {r} "
                            "avisos a clientes esperan la segunda etapa. "
                            "{f} fallaron."),
        "con_fallas": "Con fallas",
        "sin_llave": "Sin conexión",
        "sin_llave_t": "Este servidor no tiene la llave de Odoo.",
        "sin_empezar": "{n} lecturas sin empezar",
        "sin_empezar_t": "Todavía no se leen: {cuales}. {resto}",
        "ultima_sola": "La última lectura sola fue {hace}.",
        "ninguna_sola": "Ninguna lectura sola todavía.",
        "conectado": "Conectado",
        "sin_recientes": "Sin lecturas recientes",
        "sin_pegasus": "Sin usuario de Pegasus",
        "sin_pegasus_t": "El servidor no tiene el usuario de Pegasus: no se lee el GPS.",
        "no_lee": "Todavía no lee",
        "no_lee_t": "Pegasus está configurado, pero no se ha leído ninguna vez.",
        "gps_error": "Con error",
        "gps_error_t": "La última lectura falló {hace}: {error}",
        "sin_ligar": "Sin unidades ligadas",
        "sin_ligar_t": ("Pegasus contesta, pero ninguna unidad se liga: las "
                        "placas se ligan contra la flota de Odoo."),
        "leyo": "Leyó {hace}",
        "leyo_t": "{l} de {t} unidades ligadas.",
        "listos": "Listos",
        "listos_t": "Las llaves están puestas en el servidor.",
        "sin_llaves": "Sin llaves",
        "sin_llaves_t": "Sin las llaves del servidor no sale ningún aviso al teléfono.",
        "hace_nada": "hace un momento", "hace_min": "hace {n} min",
        "hace_horas": "hace {n} h", "hace_dias": "hace {n} días",
        "y": " y ",
        "tipos": {"personal": "el personal de seguridad", "flota": "la flota",
                  "oficina": "la oficina", "clientes": "los clientes",
                  "tarifarios": "los tarifarios"},
    },
    "pt": {
        "base": "Banco de dados", "reloj": "O relógio", "correo": "E-mail",
        "odoo": "Odoo", "gps": "GPS", "avisos": "Avisos no telefone",
        "bien": "Bem", "contesta": "Responde em {ms} ms.",
        "no_contesta": "Não responde",
        "sin_vueltas": "Sem voltas anotadas",
        "sin_vueltas_t": ("O relógio não anotou nenhuma volta. Se a "
                          "atualização acabou de subir, espere cinco minutos."),
        "parado": "Parado",
        "parado_t": ("A última volta foi {hace}: nenhuma tarefa automática "
                     "está rodando."),
        "corre": "Última volta {hace}",
        "corre_t": "As {n} tarefas automáticas estão rodando.",
        "con_error": "Roda, com {n} em erro",
        "con_error_t": "A última volta saiu com erro em: {cuales}.",
        "apagado": "Desligado",
        "apagado_t": "Não sai nenhum e-mail. {n} avisos esperando.",
        "sin_proveedor": "Sem provedor",
        "sin_proveedor_t": ("Está ligado, mas falta o provedor ou o "
                            "remetente: não sai nada."),
        "encendido": "Ligado",
        "encendido_t": "{n} avisos esperando; {f} falharam.",
        "solo_internos": "Só para a empresa",
        "solo_internos_t": ("Sai para consultores, central e pessoal; {r} "
                            "avisos para clientes esperam a segunda etapa. "
                            "{f} falharam."),
        "con_fallas": "Com falhas",
        "sin_llave": "Sem conexão",
        "sin_llave_t": "Este servidor não tem a chave do Odoo.",
        "sin_empezar": "{n} leituras sem começar",
        "sin_empezar_t": "Ainda não são lidos: {cuales}. {resto}",
        "ultima_sola": "A última leitura automática foi {hace}.",
        "ninguna_sola": "Nenhuma leitura automática ainda.",
        "conectado": "Conectado",
        "sin_recientes": "Sem leituras recentes",
        "sin_pegasus": "Sem usuário do Pegasus",
        "sin_pegasus_t": "O servidor não tem o usuário do Pegasus: o GPS não é lido.",
        "no_lee": "Ainda não lê",
        "no_lee_t": "O Pegasus está configurado, mas não foi lido nenhuma vez.",
        "gps_error": "Com erro",
        "gps_error_t": "A última leitura falhou {hace}: {error}",
        "sin_ligar": "Sem unidades ligadas",
        "sin_ligar_t": ("O Pegasus responde, mas nenhuma unidade se liga: as "
                        "placas se ligam contra a frota do Odoo."),
        "leyo": "Leu {hace}",
        "leyo_t": "{l} de {t} unidades ligadas.",
        "listos": "Prontos",
        "listos_t": "As chaves estão colocadas no servidor.",
        "sin_llaves": "Sem chaves",
        "sin_llaves_t": "Sem as chaves do servidor não sai nenhum aviso no telefone.",
        "hace_nada": "há um instante", "hace_min": "há {n} min",
        "hace_horas": "há {n} h", "hace_dias": "há {n} dias",
        "y": " e ",
        "tipos": {"personal": "o pessoal de segurança", "flota": "a frota",
                  "oficina": "o escritório", "clientes": "os clientes",
                  "tarifarios": "as tabelas de preços"},
    },
}

# Sin una lectura sola en este tiempo, la de cada hora no esta corriendo.
ODOO_SIN_LEER = timedelta(minutes=90)
# El GPS lee cada dos minutos, y cada quince sin nadie en la calle.
GPS_SIN_LEER = timedelta(minutes=20)


def _aware(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def hace(cuando: datetime, ahora: datetime, idioma: str) -> str:
    T = ESTADO[idioma]
    minutos = int((ahora - _aware(cuando)).total_seconds() // 60)
    if minutos < 1:
        return T["hace_nada"]
    if minutos < 120:
        return T["hace_min"].format(n=minutos)
    if minutos < 48 * 60:
        return T["hace_horas"].format(n=minutos // 60)
    return T["hace_dias"].format(n=minutos // (24 * 60))


def _juntar(cosas: list[str], idioma: str) -> str:
    if len(cosas) <= 1:
        return "".join(cosas)
    return ", ".join(cosas[:-1]) + ESTADO[idioma]["y"] + cosas[-1]


def _tile(clave, T, tono, etiqueta, texto, ir=None) -> dict:
    return {"clave": clave, "titulo": T[clave], "tono": tono,
            "etiqueta": etiqueta, "texto": texto, "ir": ir}


def _estado_base(db, T) -> dict:
    from sqlalchemy import text as sql
    inicio = datetime.now()
    try:
        db.execute(sql("SELECT 1"))
    except Exception as error:          # noqa: BLE001 -- se dice
        return _tile("base", T, "grave", T["no_contesta"],
                     error.__class__.__name__)
    ms = max(1, int((datetime.now() - inicio).total_seconds() * 1000))
    return _tile("base", T, "ok", T["bien"], T["contesta"].format(ms=ms))


def _estado_reloj(db, T, idioma, ahora) -> dict:
    from app.celery_app import celery

    tareas = {e["task"]: nombre for nombre, e in celery.conf.beat_schedule.items()}
    vueltas = [v for v in db.query(m.VueltaDelReloj).all() if v.tarea in tareas]
    terminadas = [_aware(v.termino_en) for v in vueltas if v.termino_en]
    ir = "#/manual/reloj"
    if not terminadas:
        return _tile("reloj", T, "alerta", T["sin_vueltas"], T["sin_vueltas_t"], ir)
    ultima = max(terminadas)
    if ahora - ultima > RELOJ_PARADO:
        return _tile("reloj", T, "grave", T["parado"],
                     T["parado_t"].format(hace=hace(ultima, ahora, idioma)), ir)
    en_error = sorted(tareas[v.tarea] for v in vueltas if v.estado == "error")
    if en_error:
        cuales = _juntar([(TAREAS.get(n) or {}).get(idioma, (n,))[0].split(":")[0]
                          for n in en_error], idioma)
        return _tile("reloj", T, "alerta",
                     T["con_error"].format(n=len(en_error)),
                     T["con_error_t"].format(cuales=cuales), ir)
    return _tile("reloj", T, "ok",
                 T["corre"].format(hace=hace(ultima, ahora, idioma)),
                 T["corre_t"].format(n=len(tareas)), ir)


def _estado_correo(db, T) -> dict:
    from app import correo

    e = correo.estado(db)
    avisos = e.get("avisos") or {}
    esperando = avisos.get("pendiente", 0)
    ir = "#/manual/leer/sintoma-correo-cliente"
    if not e["encendido"]:
        return _tile("correo", T, "alerta", T["apagado"],
                     T["apagado_t"].format(n=esperando), ir)
    if not e["listo"]:
        return _tile("correo", T, "grave", T["sin_proveedor"],
                     T["sin_proveedor_t"], ir)
    # Las fallidas de las ultimas 24 horas deciden el tono; las viejas
    # solo se cuentan. Y con fallidas hay boton para regresarlas a la
    # cola (seccion 100).
    fallidas = e.get("fallidas_recientes", 0)
    if e.get("solo_internos"):
        # La primera etapa (29 sep): encendido, pero no para clientes.
        tile = _tile("correo", T, "alerta",
                     T["con_fallas"] if fallidas else T["solo_internos"],
                     T["solo_internos_t"].format(r=e.get("retenidos", 0),
                                                 f=fallidas), ir)
    else:
        tile = _tile("correo", T, "alerta" if fallidas else "ok",
                     T["con_fallas"] if fallidas else T["encendido"],
                     T["encendido_t"].format(n=esperando, f=fallidas), ir)
    if avisos.get("fallida"):
        tile["accion"] = {"ruta": "/manual/correo/reintentar",
                          "clave": "man_reintentar_correo"}
    return tile


def _estado_odoo(db, T, idioma, ahora) -> dict:
    from app import odoo_api

    ir = "#/manual/leer/sintoma-odoo-no-llega"
    if not odoo_api.hay_conexion():
        return _tile("odoo", T, "grave", T["sin_llave"], T["sin_llave_t"], ir)
    L = m.SincronizacionOdoo
    tipos = ("personal", "flota", "oficina", "clientes", "tarifarios")
    sin_empezar = [t for t in tipos
                   if db.query(L.id).filter_by(tipo=t, automatica=False).first() is None]
    sola = (db.query(L).filter_by(automatica=True)
            .order_by(L.hecha_en.desc(), L.id.desc()).first())
    resto = (T["ultima_sola"].format(hace=hace(sola.hecha_en, ahora, idioma))
             if sola and sola.hecha_en else T["ninguna_sola"])
    if sin_empezar:
        cuales = _juntar([T["tipos"][t] for t in sin_empezar], idioma)
        return _tile("odoo", T, "alerta",
                     T["sin_empezar"].format(n=len(sin_empezar)),
                     T["sin_empezar_t"].format(cuales=cuales, resto=resto), ir)
    if not sola or not sola.hecha_en or ahora - _aware(sola.hecha_en) > ODOO_SIN_LEER:
        return _tile("odoo", T, "alerta", T["sin_recientes"], resto, ir)
    return _tile("odoo", T, "ok", T["conectado"], resto, ir)


def _estado_gps(db, T, idioma, ahora) -> dict:
    from app import gps

    ir = "#/manual/leer/sintoma-gps"
    if not gps.configurado():
        return _tile("gps", T, "alerta", T["sin_pegasus"], T["sin_pegasus_t"], ir)
    grupos = db.query(m.GrupoGps).all()
    leidos = [_aware(g.leido_en) for g in grupos if g.leido_en]
    if not leidos:
        return _tile("gps", T, "alerta", T["no_lee"], T["no_lee_t"], ir)
    ultima = max(leidos)
    for g in grupos:
        if g.error and g.error_en and (not g.leido_en
                                       or _aware(g.error_en) > _aware(g.leido_en)):
            return _tile("gps", T, "alerta", T["gps_error"],
                         T["gps_error_t"].format(hace=hace(g.error_en, ahora, idioma),
                                                 error=g.error), ir)
    total = db.query(m.UnidadGps).count()
    ligadas = (db.query(m.UnidadGps)
               .filter(m.UnidadGps.vehiculo_id.isnot(None)).count())
    if total and not ligadas:
        return _tile("gps", T, "alerta", T["sin_ligar"], T["sin_ligar_t"], ir)
    if ahora - ultima > GPS_SIN_LEER:
        return _tile("gps", T, "alerta", T["sin_recientes"],
                     T["leyo_t"].format(l=ligadas, t=total), ir)
    return _tile("gps", T, "ok", T["leyo"].format(hace=hace(ultima, ahora, idioma)),
                 T["leyo_t"].format(l=ligadas, t=total), ir)


def _estado_avisos(T) -> dict:
    from app.config import settings

    ir = "#/manual/leer/sintoma-avisos-telefono"
    if settings.vapid_public and settings.vapid_private:
        return _tile("avisos", T, "ok", T["listos"], T["listos_t"], ir)
    return _tile("avisos", T, "grave", T["sin_llaves"], T["sin_llaves_t"], ir)


def estado(db: Session, idioma: str, ahora: datetime | None = None) -> list[dict]:
    """Como esta el sistema ahora: lo primero que se mira cuando algo se
    atora. Cada tarjeta dice su tono --bien, cuidado o mal--, lo que ve
    y a que parte del manual lleva."""
    ahora = _aware(ahora) or _utc()
    T = ESTADO[idioma]
    return [_estado_base(db, T), _estado_reloj(db, T, idioma, ahora),
            _estado_correo(db, T), _estado_odoo(db, T, idioma, ahora),
            _estado_gps(db, T, idioma, ahora), _estado_avisos(T)]


# ================================================================ todo junto

def manual(db: Session, pedido: str | None) -> dict:
    """El manual completo, en el idioma del que lo lee (el ingles se lee
    en espanol). El estado en vivo va aparte: se pide cada vez."""
    idioma = idioma_de(pedido)
    return {
        "idioma": idioma,
        "en_otro_idioma": (pedido or "es")[:2].lower() not in IDIOMAS,
        "version": version(idioma),
        "capitulos": list(capitulos(idioma)),
        "reloj": reloj(db, idioma),
        "mensajes": mensajes(idioma),
        "areas": [{"clave": k, "titulo": v[idioma]} for k, v in AREAS.items()],
        "permisos": permisos_del_sistema(db),
        "novedades": list(novedades(idioma)),
        "casos": casos(db),
    }

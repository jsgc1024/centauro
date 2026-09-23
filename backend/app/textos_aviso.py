# -*- coding: utf-8 -*-
"""Los textos de los avisos que salen por correo, en tres idiomas.

Hermano de `textos.py`, que hace lo mismo con el task sheet. La regla es
la de allá, escrita hace meses y confirmada por Salvador el 20 de
septiembre:

    Por defecto va en ingles, porque el ejecutivo suele ser extranjero.

Y su otra mitad: **el solicitante lee en el idioma del pais donde se
ejecuta el servicio**, porque quien pide el servicio casi siempre es
gente local --la asistente, el area de seguridad del cliente--. Son dos
datos y no uno porque casi nunca coinciden.

Se traduce lo que escribe el sistema. NO se traduce lo que capturo una
persona: nombres, direcciones, placas, la agenda, el motivo del cambio
del task sheet. Traducir una direccion la vuelve inutil para quien tiene
que llegar a ella.

A la persona protegida se le dice **principal** --el termino del oficio,
el que usa el cliente corporativo-- en ingles y portugues, y "ejecutivo"
en espanol, que es como ya sale el task sheet.
"""
from datetime import date

POR_DEFECTO = "en"
IDIOMAS = ("en", "es", "pt")

DIAS = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
           "Saturday", "Sunday"),
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado",
           "domingo"),
    "pt": ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
           "sexta-feira", "sábado", "domingo"),
}
MESES = {
    "en": ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"),
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"),
    "pt": ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
           "julho", "agosto", "setembro", "outubro", "novembro",
           "dezembro"),
}

TEXTOS = {
    "en": {
        # --- las claves de la ficha
        "equipo": "Team",
        "unidad": "Vehicle",
        "punto": "Meeting point",
        "presentacion": "Report time",
        "termino": "Ended",
        "fecha": "Date",
        "horas_extra": "Overtime",
        "ninguna": "none",
        "manana": "Tomorrow",
        "siguiente_dia": "Next day",
        "cierre_programado": "Scheduled end",
        "contratado": "Contracted",
        "horas": "hours",
        "version": "Version",
        "que_cambio": "What changed",
        "primer_dia": "First day",
        "por_asignar": "to be assigned",
        "plates": "plates",
        # --- el equipo llego al punto
        # --- cambio de persona o de unidad, el mismo dia
        "cambio_asunto_principal": "A change in your security team today",
        "cambio_asunto_solicitante": "{folio}: change in today's team",
        "cambio_cuerpo_persona": ("{quien} joins your team for today's "
                                  "service. Below is your team as it "
                                  "stands now, with their phone numbers."),
        "cambio_cuerpo_unidad": ("Today's service runs with a different "
                                 "vehicle: {quien}. Below is your team as "
                                 "it stands now."),
        "punto_asunto_principal": "Your security team is on site",
        "punto_asunto_solicitante": "{folio}: team at the meeting point",
        "punto_cuerpo": ("The security team has arrived at the meeting "
                         "point and is standing by to make contact."),
        # --- contacto con el principal
        "inicio_asunto_solicitante": "{folio}: service started",
        "inicio_cuerpo_solicitante": ("Contact was made with the principal "
                                      "at {hora}."),
        "inicio_asunto_principal": "Service started",
        "inicio_cuerpo_principal": "Your service started at {hora}.",
        "boton_seguir": "Follow the service live",
        "boton_encuesta": "Answer in one tap",
        "boton_abrir": "Open",
        "enlace_vence": "This link stops working on {cuando}.",
        # --- antes de las horas extra
        "extra_asunto": "{minutos} minutes left before overtime",
        "extra_cuerpo": ("The service completes its {horas} contracted "
                         "hours at {hora}. Overtime starts from that "
                         "moment."),
        # --- fin del dia
        "fin_asunto": "{folio}: service ended",
        "fin_cuerpo": "The {dia} service ended at {hora}.",
        "fin_con_extra": ("{horas} hours of overtime were generated beyond "
                          "the contracted schedule."),
        "fin_con_extra_una": ("1 hour of overtime was generated beyond the "
                             "contracted schedule."),
        "fin_sin_extra": "The service closed within the contracted schedule.",
        "fin_manana": "Tomorrow the report time is {hora}",
        "fin_otro_dia": "On {dia} the report time is {hora}",
        "fin_en": " at {lugar}.",
        "fin_punto": ".",
        "fin_ultimo": "This was the last scheduled day of the service.",
        # --- task sheet
        "ts_asunto": "{folio}: task sheet v{version}",
        "ts_asunto_equipo": "{folio} {equipo}: task sheet v{version}",
        "ts_cuerpo_primero": "The task sheet for {cual} is attached below.",
        "ts_cuerpo_nuevo": ("The task sheet for {cual} has been updated "
                            "(version {version}). This version replaces "
                            "the previous one."),
        "ts_del_servicio": "the service",
        "ts_del_equipo": "team {alias}",
        # --- aviso interno, al consultor titular
        "enc_mala_asunto": "{folio}: {cliente} rated the service {nota} out of 5",
        "enc_mala_cuerpo": (
            "{quien} just answered the survey with {nota} out of 5. Nothing has been charged to anyone: a low score opens a review, and it is yours to classify. What the client said is below."),
        "enc_rec_asunto": "{folio}: how did the service go?",
        "enc_rec_cuerpo": (
            "We asked a few days ago and the survey is still open. It takes less than a minute, and it is the only way we find out what to fix. It closes on {fecha}."),
        "enc_cliente": "Who answered",
        "enc_nota": "Score",
        "enc_dijo": "What they said",
        "enc_servicio": "Service",
        "cap_vence_pronto": "{quien}: {curso} expires in {dias} days",
        "cap_vence_hoy": "{quien}: {curso} expires today",
        "cap_vence_cuerpo": "{quien}'s certificate is about to expire. An expired certification is not a certification, and the day the client asks who is protecting their principal, that date is the answer. Renewing it now avoids pulling them off services later.",
        "cap_quien": "Who",
        "cap_curso": "Certificate",
        "cap_institucion": "Issued by",
        "cap_vence": "Expires",
        "cob_asunto": "{folio}: {quien} worked on your service",
        "cob_cuerpo": ("{quien} worked on your service while covering "
                       "your portfolio. It is logged; this is just so "
                       "you know, there is nothing to do."),
        "quien": "Who",
        "que_hizo": "What they did",
        "detalle": "Detail",
    },
    "es": {
        "equipo": "Equipo",
        "unidad": "Unidad",
        "punto": "Punto",
        "presentacion": "Presentación",
        "termino": "Término",
        "fecha": "Fecha",
        "horas_extra": "Horas extra",
        "ninguna": "ninguna",
        "manana": "Mañana",
        "siguiente_dia": "Siguiente día",
        "cierre_programado": "Cierre programado",
        "contratado": "Contratado",
        "horas": "horas",
        "version": "Versión",
        "que_cambio": "Qué cambió",
        "primer_dia": "Primer día",
        "por_asignar": "por asignar",
        "plates": "placas",
        # --- cambio de persona o de unidad, el mismo dia
        "cambio_asunto_principal": "Un cambio en su equipo de seguridad de hoy",
        "cambio_asunto_solicitante": "{folio}: cambio en el equipo de hoy",
        "cambio_cuerpo_persona": ("{quien} se integra a su equipo para el "
                                  "servicio de hoy. Abajo está su equipo "
                                  "como queda, con sus teléfonos."),
        "cambio_cuerpo_unidad": ("El servicio de hoy se cubre con otra "
                                 "unidad: {quien}. Abajo está su equipo "
                                 "como queda."),
        "punto_asunto_principal": "Su equipo de seguridad está en el lugar",
        "punto_asunto_solicitante": "{folio}: equipo en el punto de origen",
        "punto_cuerpo": ("El equipo de seguridad llegó al punto de origen "
                         "y está en espera de hacer contacto."),
        "inicio_asunto_solicitante": "{folio}: servicio iniciado",
        "inicio_cuerpo_solicitante": ("Se hizo contacto con el ejecutivo a "
                                      "las {hora}."),
        "inicio_asunto_principal": "Servicio iniciado",
        "inicio_cuerpo_principal": "Su servicio inició a las {hora}.",
        "boton_seguir": "Seguir el servicio en vivo",
        "boton_encuesta": "Contestar en un toque",
        "boton_abrir": "Abrir",
        "enlace_vence": "El enlace deja de servir el {cuando}.",
        "extra_asunto": "Faltan {minutos} minutos para las horas extra",
        "extra_cuerpo": ("El servicio cumple sus {horas} horas contratadas "
                         "a las {hora}. A partir de ese momento se generan "
                         "horas extra."),
        "fin_asunto": "{folio}: servicio terminado",
        "fin_cuerpo": "El servicio del {dia} terminó a las {hora}.",
        "fin_con_extra": ("Se generaron {horas} horas extra sobre el "
                          "horario contratado."),
        "fin_con_extra_una": ("Se generó 1 hora extra sobre el horario "
                              "contratado."),
        "fin_sin_extra": "El servicio cerró dentro del horario contratado.",
        "fin_manana": "Mañana la presentación es a las {hora}",
        "fin_otro_dia": "El {dia} la presentación es a las {hora}",
        "fin_en": " en {lugar}.",
        "fin_punto": ".",
        "fin_ultimo": "Es el último día programado del servicio.",
        "ts_asunto": "{folio}: task sheet v{version}",
        "ts_asunto_equipo": "{folio} {equipo}: task sheet v{version}",
        "ts_cuerpo_primero": "Se comparte el task sheet {cual}.",
        "ts_cuerpo_nuevo": ("Se actualizó el task sheet {cual} (versión "
                            "{version}). Esta versión reemplaza a la "
                            "anterior."),
        "ts_del_servicio": "del servicio",
        "ts_del_equipo": "del equipo {alias}",
        "enc_mala_asunto": "{folio}: {cliente} calificó el servicio con {nota} de 5",
        "enc_mala_cuerpo": (
            "{quien} acaba de contestar la encuesta con {nota} de 5. No se le ha cobrado a nadie: una calificación baja abre una revisión, y clasificarla es tuyo. Abajo está lo que dijo el cliente."),
        "enc_rec_asunto": "{folio}: ¿cómo estuvo el servicio?",
        "enc_rec_cuerpo": (
            "Te preguntamos hace unos días y la encuesta sigue abierta. Toma menos de un minuto, y es la única forma en que nos enteramos de qué corregir. Se cierra el {fecha}."),
        "enc_cliente": "Quién contestó",
        "enc_nota": "Calificación",
        "enc_dijo": "Lo que dijo",
        "enc_servicio": "Servicio",
        "cap_vence_pronto": "{quien}: {curso} vence en {dias} dias",
        "cap_vence_hoy": "{quien}: {curso} vence hoy",
        "cap_vence_cuerpo": "El certificado de {quien} esta por vencer. Una certificacion vencida no es una certificacion, y el dia que el cliente pregunte quien va a cuidar a su ejecutivo, esa fecha es la respuesta. Reinscribirlo ahora evita sacarlo de servicios despues.",
        "cap_quien": "Quien",
        "cap_curso": "Certificado",
        "cap_institucion": "Institucion",
        "cap_vence": "Vence",
        "cob_asunto": "{folio}: {quien} movió tu servicio",
        "cob_cuerpo": ("{quien} trabajó en tu servicio mientras cubría "
                       "tu cartera. Quedó registrado en la bitácora; "
                       "esto es para que lo sepas, no hay nada que "
                       "hacer."),
        "quien": "Quién",
        "que_hizo": "Qué hizo",
        "detalle": "Detalle",
    },
    "pt": {
        "equipo": "Equipe",
        "unidad": "Veículo",
        "punto": "Ponto de encontro",
        "presentacion": "Apresentação",
        "termino": "Término",
        "fecha": "Data",
        "horas_extra": "Horas extras",
        "ninguna": "nenhuma",
        "manana": "Amanhã",
        "siguiente_dia": "Próximo dia",
        "cierre_programado": "Encerramento previsto",
        "contratado": "Contratado",
        "horas": "horas",
        "version": "Versão",
        "que_cambio": "O que mudou",
        "primer_dia": "Primeiro dia",
        "por_asignar": "a definir",
        "plates": "placa",
        # --- cambio de persona o de unidad, el mismo dia
        "cambio_asunto_principal": "Uma mudança na sua equipe de segurança de hoje",
        "cambio_asunto_solicitante": "{folio}: mudança na equipe de hoje",
        "cambio_cuerpo_persona": ("{quien} entra na sua equipe para o "
                                  "serviço de hoje. Abaixo está sua equipe "
                                  "como fica, com os telefones."),
        "cambio_cuerpo_unidad": ("O serviço de hoje é coberto com outro "
                                 "veículo: {quien}. Abaixo está sua equipe "
                                 "como fica."),
        "punto_asunto_principal": "Sua equipe de segurança está no local",
        "punto_asunto_solicitante": "{folio}: equipe no ponto de encontro",
        "punto_cuerpo": ("A equipe de segurança chegou ao ponto de encontro "
                         "e aguarda para fazer contato."),
        "inicio_asunto_solicitante": "{folio}: serviço iniciado",
        "inicio_cuerpo_solicitante": ("O contato com o principal foi feito "
                                      "às {hora}."),
        "inicio_asunto_principal": "Serviço iniciado",
        "inicio_cuerpo_principal": "Seu serviço começou às {hora}.",
        "boton_seguir": "Acompanhar o serviço ao vivo",
        "boton_encuesta": "Responder num toque",
        "boton_abrir": "Abrir",
        "enlace_vence": "O link deixa de funcionar em {cuando}.",
        "extra_asunto": "Faltam {minutos} minutos para as horas extras",
        "extra_cuerpo": ("O serviço completa suas {horas} horas contratadas "
                         "às {hora}. A partir desse momento começam as "
                         "horas extras."),
        "fin_asunto": "{folio}: serviço encerrado",
        "fin_cuerpo": "O serviço de {dia} terminou às {hora}.",
        "fin_con_extra": ("Foram geradas {horas} horas extras além do "
                          "horário contratado."),
        "fin_con_extra_una": ("Foi gerada 1 hora extra além do horário "
                              "contratado."),
        "fin_sin_extra": "O serviço encerrou dentro do horário contratado.",
        "fin_manana": "Amanhã a apresentação é às {hora}",
        "fin_otro_dia": "Em {dia} a apresentação é às {hora}",
        "fin_en": " em {lugar}.",
        "fin_punto": ".",
        "fin_ultimo": "Foi o último dia programado do serviço.",
        "ts_asunto": "{folio}: task sheet v{version}",
        "ts_asunto_equipo": "{folio} {equipo}: task sheet v{version}",
        "ts_cuerpo_primero": "Segue a task sheet {cual}.",
        "ts_cuerpo_nuevo": ("A task sheet {cual} foi atualizada (versão "
                            "{version}). Esta versão substitui a anterior."),
        "ts_del_servicio": "do serviço",
        "ts_del_equipo": "da equipe {alias}",
        "enc_mala_asunto": "{folio}: {cliente} avaliou o serviço com {nota} de 5",
        "enc_mala_cuerpo": (
            "{quien} acabou de responder a pesquisa com {nota} de 5. Não se cobrou nada de ninguém: uma nota baixa abre uma revisão, e classificá-la é seu. Abaixo está o que o cliente disse."),
        "enc_rec_asunto": "{folio}: como foi o serviço?",
        "enc_rec_cuerpo": (
            "Perguntamos há alguns dias e a pesquisa continua aberta. Leva menos de um minuto, e é a única forma de sabermos o que corrigir. Fecha em {fecha}."),
        "enc_cliente": "Quem respondeu",
        "enc_nota": "Nota",
        "enc_dijo": "O que disse",
        "enc_servicio": "Serviço",
        "cap_vence_pronto": "{quien}: {curso} vence em {dias} dias",
        "cap_vence_hoy": "{quien}: {curso} vence hoje",
        "cap_vence_cuerpo": "O certificado de {quien} esta para vencer. Uma certificacao vencida nao e uma certificacao, e no dia em que o cliente perguntar quem vai cuidar do seu executivo, essa data e a resposta. Reinscreve-lo agora evita tira-lo de servicos depois.",
        "cap_quien": "Quem",
        "cap_curso": "Certificado",
        "cap_institucion": "Instituicao",
        "cap_vence": "Vence",
        "cob_asunto": "{folio}: {quien} mexeu no seu serviço",
        "cob_cuerpo": ("{quien} trabalhou no seu serviço enquanto "
                       "cobria a sua carteira. Ficou registrado; isto "
                       "é só para você saber, não há nada a fazer."),
        "quien": "Quem",
        "que_hizo": "O que fez",
        "detalle": "Detalhe",
    },
}


def diccionario(idioma: str | None) -> dict:
    return TEXTOS.get((idioma or POR_DEFECTO).lower(), TEXTOS[POR_DEFECTO])


def t(idioma: str | None, clave: str, **datos) -> str:
    """Un texto armado. Si la clave no existe, se ve: no se calla."""
    plantilla = diccionario(idioma).get(clave, clave)
    return plantilla.format(**datos) if datos else plantilla


def dia_largo(fecha: date, idioma: str | None = None) -> str:
    """"sábado 19 de septiembre", no "2026-09-19".

    Una fecha en formato de base de datos obliga a traducirla
    mentalmente para saber si es hoy, mañana o el jueves. El cliente no
    tiene por que hacer esa cuenta a las nueve de la noche.
    """
    codigo = (idioma or POR_DEFECTO).lower()
    if codigo not in DIAS:
        codigo = POR_DEFECTO
    dia = DIAS[codigo][fecha.weekday()]
    mes = MESES[codigo][fecha.month - 1]
    if codigo == "en":
        return f"{dia}, {mes} {fecha.day}"
    if codigo == "pt":
        return f"{dia}, {fecha.day} de {mes}"
    return f"{dia} {fecha.day} de {mes}"


def idioma_de(db, servicio, destinatario) -> str:
    """En que idioma se le habla a quien va a recibir este aviso.

    El principal trae el suyo en el servicio. El solicitante, si no se
    capturo, lee en el idioma del pais donde se ejecuta: casi siempre es
    gente local. Y el personal de la casa --el consultor titular al que
    se le avisa de una cobertura-- tambien, que es la misma regla de la
    app de campo.
    """
    from app import models as m

    if destinatario == m.Destinatario.EJECUTIVO:
        return servicio.idioma_ejecutivo or POR_DEFECTO
    if destinatario == m.Destinatario.SOLICITANTE and servicio.idioma_solicitante:
        return servicio.idioma_solicitante
    pais = db.get(m.Pais, servicio.pais_id) if servicio.pais_id else None
    return (pais.idioma if pais else "es")


def puesto_en(idioma: str | None, nombre: str | None) -> str | None:
    """El puesto traducido con la tabla del task sheet, no con otra.

    "Conductor de seguridad" ya es "Security driver" en la hoja que el
    ejecutivo tiene en la mano; el correo tiene que decirle igual, o
    parecen dos personas distintas.
    """
    if not nombre:
        return nombre
    from app.textos import diccionario as del_task_sheet

    return del_task_sheet(idioma).get("perfiles", {}).get(nombre, nombre)

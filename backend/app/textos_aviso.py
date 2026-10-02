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
        "extra_asunto_ya": "The service is now in overtime",
        "extra_cuerpo_ya": ("The service completed its {horas} contracted "
                            "hours at {hora}. Overtime is running since "
                            "that moment."),
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
        # The freelance file (section 111).
        "fre_quien": "Freelance",
        "fre_servicio": "Service",
        "fre_hasta": "Deadline",
        "fre_motivo": "Why it is urgent",
        "fre_respuesta": "Reply",
        "fre_faltaba": "What is missing",
        "fre_documento": "Document",
        "fre_vence": "Expires",
        "fre_plazo_asunto": "{quien}: second service, until {fecha} to complete the scheduled file",
        "fre_plazo_cuerpo": "{quien} is an emergency freelance and was just assigned a second service ({folio}). He has until {fecha} to complete the scheduled-freelance requirements; after that date he can no longer be assigned until they are complete.",
        "fre_plazo_vencio_asunto": "{quien}: the deadline to complete the scheduled file passed",
        "fre_plazo_vencio_cuerpo": "{quien} had until {fecha} to complete the scheduled-freelance requirements. He can no longer be assigned until they are complete, unless operations authorizes an urgency for a specific service.",
        "fre_urgencia_asunto": "Authorize {quien} for {folio}?",
        "fre_urgencia_cuerpo": "The freelance {quien} has an incomplete file and was requested for service {folio} as an urgency. Authorize it or not from the operations inbox, with your reason.",
        "fre_respuesta_si_asunto": "{quien} authorized for {folio}",
        "fre_respuesta_no_asunto": "{quien} not authorized for {folio}",
        "fre_respuesta_cuerpo": "Head of operations replied to your urgent request for {quien} on service {folio}: {respuesta}",
        "fre_vence_pronto": "{quien}: {documento} expires in {dias} days",
        "fre_vence_hoy": "{quien}: {documento} expires today",
        "fre_vencio": "{quien}: {documento} expired",
        "fre_vence_cuerpo": "A document in the file of the freelance {quien} is about to expire or has expired. With an expired document he cannot be assigned: ask for the new one and upload it in Security staff → Freelance.",
        # The special price of a dedicated-service proposal (section 115).
        "prop_folio": "Proposal",
        "prop_cliente": "Client",
        "prop_mensual": "Monthly, before VAT",
        "prop_motivo": "Why it is special",
        "prop_nota": "Note",
        "prop_especial_asunto": "{folio}: special price to approve",
        "prop_especial_cuerpo": "{quien} asks for your approval of the special price in proposal {folio} for {cliente}: {motivo}. Approve it or not from the operations inbox; without it the proposal cannot be sent.",
        "prop_especial_si_asunto": "{folio}: special price approved",
        "prop_especial_si_cuerpo": "{quien} approved the special price in proposal {folio} for {cliente}. You can send it now.",
        "prop_especial_no_asunto": "{folio}: special price not approved",
        "prop_especial_no_cuerpo": "{quien} did not approve the special price in proposal {folio} for {cliente}: {nota}. Correct it and ask again.",
        "cob_asunto": "{folio}: {quien} worked on your service",
        "cob_cuerpo": ("{quien} worked on your service while covering "
                       "your portfolio. It is logged; this is just so "
                       "you know, there is nothing to do."),
        "quien": "Who",
        "que_hizo": "What they did",
        "detalle": "Detail",
        # --- reportar una falla (seccion 92)
        "falla_asunto": "Problem reported: {titulo}",
        "falla_cuerpo": ("{quien} reported a problem from {desde}. It is in "
                         "System manual > Cases, to review."),
        "falla_desde_consola": "the console",
        "falla_desde_app": "the field app",
        "falla_donde": "Where",
        "falla_que_paso": "What happened",
        "falla_resuelta_asunto": "The problem you reported is resolved",
        "falla_resuelta_cuerpo": ("The problem you reported on {dia} is "
                                  "resolved. Thank you for reporting it."),
        "falla_lo_que_reportaste": "What you reported",
        "falla_causa": "The cause",
        "falla_como": "How it was fixed",
        # --- el acceso: la invitacion y la recuperacion de contrasena
        "acc_inv_asunto": "Your access to Centauro Connect",
        "acc_inv_cuerpo": ("Hi, {nombre}. You now have access to Centauro "
                           "Connect. To sign in for the first time, create "
                           "your password with the button."),
        "acc_inv_boton": "Create my password",
        "acc_inv_nota": ("The link works only once and expires on {dia} "
                         "at {hora}."),
        "acc_rec_asunto": "To set a new password",
        "acc_rec_cuerpo": ("Someone asked to change the password of your "
                           "Centauro Connect account. If it was you, use "
                           "the button. If it wasn't, ignore this email: "
                           "your password stays the same."),
        "acc_rec_boton": "Set my new password",
        "acc_rec_nota": "The link works only once and expires at {hora}.",
        "acc_tu_correo": "Your email",
        "acc_entras_como": "You sign in as",
        # Los nombres de la consola, para que el correo diga lo mismo que
        # la pantalla que va a abrir.
        "rol_personal_seguridad": "Security personnel",
        "rol_central": "Control room",
        "rol_consultor": "Consultant",
        "rol_director_operaciones": "Head of operations",
        "rol_director_general": "Managing director",
        "rol_finanzas": "Finance",
        "rol_recursos_humanos": "Human Resources",
        "rol_sistema_calidad": "Systems and quality",
        "rol_admin": "Administration (master key)",
        # --- el cierre: los dos plazos del consultor, por correo (seccion 101)
        "cie_vb_asunto": "{de_que}: you have 24 h for the sign-off",
        "cie_vb_cuerpo": ("The team's expense verification for {de_que} is "
                          "over. Your 24 hours to sign off and send it to "
                          "finance run until {fecha} at {hora}; your "
                          "commission depends on making it in time."),
        "cie_vb_que_hacer": ("Open the service in the console, review the "
                             "comparison and the team's expenses, and give "
                             "your sign-off."),
        "cie_reg_asunto": "{de_que}: finance sent it back",
        "cie_reg_cuerpo": ("Finance sent {de_que} back to operations. You "
                           "have until {fecha} at {hora} to correct it and "
                           "send it again; your first sign-off keeps its "
                           "'in time' as it was."),
        "cie_reg_que_hacer": ("Correct what finance asked for and send it to "
                              "finance again from the service screen."),
        "cie_vence": "Deadline",
        "cie_motivo": "Reason",
        "cie_que_hacer": "What to do",
        # --- el cambio de consultor titular (decision 13, seccion 105)
        "tit_entra_asunto": "{folio}: you are now its consultant in charge",
        "tit_entra_cuerpo": ("{quien} made you the consultant in charge of "
                             "{folio} ({cliente}). From now on its notices, "
                             "its deadlines and its commission are yours."),
        "tit_sale_asunto": "{folio}: {nuevo} is now its consultant in charge",
        "tit_sale_cuerpo": ("{quien} changed the consultant in charge of "
                            "{folio} ({cliente}): from now on {nuevo} leads "
                            "it. What was already closed and paid to you "
                            "stays as it was."),
        "tit_servicio": "Service",
        "tit_quien": "Changed by",
        "tit_nuevo": "Consultant in charge",
        "tit_anterior": "Previous consultant",
        "tit_motivo": "Reason",
        # --- la incidencia grave, a Recursos Humanos (seccion 105)
        "inc_grave_asunto": "Serious incident: {quien} on {folio}",
        "inc_grave_cuerpo": ("Operations management authorized a serious "
                             "incident involving {quien} on {folio} ({fecha}). "
                             "The month's bonus for {quien} is set to zero and "
                             "the consultant's commission for that service is "
                             "held until the managing director decides. Human "
                             "Resources handles it from the person's file."),
        "inc_descripcion": "What happened",
        "inc_registro": "Reported by",
        "inc_resolucion": "Resolution",
        "inc_comision": "Consultant's commission",
        "inc_comision_retenida": "Held: the managing director decides it.",
        "inc_comision_al_cerrar": ("Not generated yet: it will be held when "
                                   "finance closes the service."),
        # --- seccion 105: el cobro al cancelar y los plazos del cierre
        "cie_cobro_asunto": "{de_que}: operations approved billing {cobro}",
        "cie_cobro_cuerpo": ("Head of operations approved billing {de_que} "
                             "{cobro}. You can now sign off and send it to "
                             "finance; your deadline runs until {fecha} at "
                             "{hora}."),
        "cie_cobro_que_hacer": ("Open the service in the console, review the "
                                "comparison and give your sign-off."),
        "cie_cobro_completo": "in full: the approved quote as it stands",
        "cie_cobro_ejecutado": "for what was delivered: the days worked",
        "cie_mitad_asunto": "{de_que}: half of your sign-off deadline is gone",
        "cie_mitad_cuerpo": ("Half of your time to sign off {de_que} has "
                             "passed: it runs out on {fecha} at {hora}. Your "
                             "commission depends on making it in time."),
        "cie_mitad_reg_cuerpo": ("Half of your 24 hours since finance sent "
                                 "{de_que} back has passed: they run out on "
                                 "{fecha} at {hora}."),
        "cie_mitad_que_hacer": ("Open the service in the console, review the "
                                "comparison and the team's expenses, and give "
                                "your sign-off."),
        "cie_venc_asunto": "{de_que}: the sign-off deadline has expired",
        "cie_venc_cuerpo": ("Your time to sign off {de_que} ran out on {fecha} "
                            "at {hora}. The service is still waiting for your "
                            "sign-off, now without commission: send it as "
                            "soon as possible so it gets billed."),
        "cie_venc_reg_cuerpo": ("Your 24 hours since finance sent {de_que} "
                                "back ran out on {fecha} at {hora}. It is "
                                "still waiting for you to send it again; your "
                                "first sign-off keeps its 'in time' as it "
                                "was."),
        "cie_venc_que_hacer": ("Open the service in the console, resolve what "
                               "the review points out and send it to "
                               "finance."),
        "cie_venc_dir_asunto": "{de_que}: {consultor}'s sign-off deadline expired",
        "cie_venc_dir_cuerpo": ("{consultor}'s time to sign off {de_que} ran "
                                "out on {fecha} at {hora}. The service is "
                                "still waiting for the sign-off, now without "
                                "commission, and it is listed under expired "
                                "deadlines in Head of operations."),
        "cie_venc_dir_reg_cuerpo": ("{consultor}'s 24 hours since finance sent "
                                    "{de_que} back ran out on {fecha} at "
                                    "{hora}. The service is still waiting to "
                                    "be sent again."),
        "cie_venc_dir_que_hacer": ("Check with the consultant what is holding "
                                   "the sign-off; head of operations can give "
                                   "it as cover."),
        "cie_consultor": "Consultant",
        # Section 107: the unit hand-back after the day's end.
        "ent_venc_asunto": "{folio}: unit {placa} not handed back in time",
        "ent_venc_cuerpo": ("{quien} did not hand back unit {placa} of {folio} "
                            "with its inspection by {fecha} at {hora}. It is "
                            "still pending: the service close-out flags it "
                            "until it is handed back or recorded as handed "
                            "back without inspection."),
        "ent_venc_que_hacer": ("Have the driver hand it back with the five "
                               "photos from the app. If that is no longer "
                               "possible, record it as handed back without "
                               "inspection from the unit review in the "
                               "service, with the reason."),
        "ent_unidad": "Unit",
        "ent_quien": "Responsible",
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
        "extra_asunto_ya": "El servicio ya está en horas extra",
        "extra_cuerpo_ya": ("El servicio cumplió sus {horas} horas "
                            "contratadas a las {hora}. Desde ese momento "
                            "corren horas extra."),
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
        "cap_vence_pronto": "{quien}: {curso} vence en {dias} días",
        "cap_vence_hoy": "{quien}: {curso} vence hoy",
        "cap_vence_cuerpo": "El certificado de {quien} está por vencer. Una certificación vencida no es una certificación, y el día que el cliente pregunte quién va a cuidar a su ejecutivo, esa fecha es la respuesta. Reinscribirlo ahora evita sacarlo de servicios después.",
        "cap_quien": "Quién",
        "cap_curso": "Certificado",
        "cap_institucion": "Institución",
        "cap_vence": "Vence",
        # El expediente del freelance (seccion 111).
        "fre_quien": "Freelance",
        "fre_servicio": "Servicio",
        "fre_hasta": "Plazo",
        "fre_motivo": "Por qué es urgente",
        "fre_respuesta": "Respuesta",
        "fre_faltaba": "Lo que le falta",
        "fre_documento": "Documento",
        "fre_vence": "Vence",
        "fre_plazo_asunto": "{quien}: segundo servicio, hasta el {fecha} para completar lo de programado",
        "fre_plazo_cuerpo": "{quien} es freelance de emergencia y se le acaba de asignar su segundo servicio ({folio}). Tiene hasta el {fecha} para completar los requisitos de programado; pasada esa fecha ya no se le asigna hasta completarlos.",
        "fre_plazo_vencio_asunto": "{quien}: venció el plazo para completar lo de programado",
        "fre_plazo_vencio_cuerpo": "{quien} tenía hasta el {fecha} para completar los requisitos de programado. Ya no se le asigna hasta completarlos, salvo que dirección de operaciones autorice una urgencia para un servicio.",
        "fre_urgencia_asunto": "¿Autorizas a {quien} para {folio}?",
        "fre_urgencia_cuerpo": "El freelance {quien} tiene el expediente incompleto y lo piden por urgencia para el servicio {folio}. Autorízalo o no desde tu bandeja de dirección de operaciones, con tu motivo.",
        "fre_respuesta_si_asunto": "{quien}: autorizado para {folio}",
        "fre_respuesta_no_asunto": "{quien}: no autorizado para {folio}",
        "fre_respuesta_cuerpo": "Dirección de operaciones contestó tu urgencia por {quien} para el servicio {folio}: {respuesta}",
        "fre_vence_pronto": "{quien}: {documento} vence en {dias} días",
        "fre_vence_hoy": "{quien}: {documento} vence hoy",
        "fre_vencio": "{quien}: {documento} ya venció",
        "fre_vence_cuerpo": "Un documento del expediente del freelance {quien} está por vencer o ya venció. Con un documento vencido no se le asigna: pídele el nuevo y súbelo en Personal de seguridad → Freelance.",
        # El precio especial de la propuesta del implantado (seccion 115).
        "prop_folio": "Propuesta",
        "prop_cliente": "Cliente",
        "prop_mensual": "Mensual, antes de IVA",
        "prop_motivo": "Por qué es especial",
        "prop_nota": "Nota",
        "prop_especial_asunto": "{folio}: precio especial por autorizar",
        "prop_especial_cuerpo": "{quien} pide tu visto bueno al precio especial de la propuesta {folio} para {cliente}: {motivo}. Autorízalo o no desde tu bandeja de dirección de operaciones; sin él no se puede mandar.",
        "prop_especial_si_asunto": "{folio}: precio especial autorizado",
        "prop_especial_si_cuerpo": "{quien} autorizó el precio especial de la propuesta {folio} para {cliente}. Ya la puedes mandar.",
        "prop_especial_no_asunto": "{folio}: precio especial no autorizado",
        "prop_especial_no_cuerpo": "{quien} no autorizó el precio especial de la propuesta {folio} para {cliente}: {nota}. Corrígela y vuelve a pedirlo.",
        "cob_asunto": "{folio}: {quien} movió tu servicio",
        "cob_cuerpo": ("{quien} trabajó en tu servicio mientras cubría "
                       "tu cartera. Quedó registrado en la bitácora; "
                       "esto es para que lo sepas, no hay nada que "
                       "hacer."),
        "tit_entra_asunto": "{folio}: ahora eres su consultor titular",
        "tit_entra_cuerpo": ("{quien} te puso como consultor titular de "
                             "{folio} ({cliente}). Desde ahora sus avisos, "
                             "sus plazos y su comisión son tuyos."),
        "tit_sale_asunto": "{folio}: {nuevo} pasa a ser su consultor titular",
        "tit_sale_cuerpo": ("{quien} cambió al consultor titular de {folio} "
                            "({cliente}): desde ahora lo lleva {nuevo}. Lo "
                            "que ya se cerró y se te pagó se queda como "
                            "estaba."),
        "tit_servicio": "Servicio",
        "tit_quien": "Lo cambió",
        "tit_nuevo": "Consultor titular",
        "tit_anterior": "Titular anterior",
        "tit_motivo": "Motivo",
        "quien": "Quién",
        "que_hizo": "Qué hizo",
        "detalle": "Detalle",
        # --- reportar una falla (seccion 92)
        "falla_asunto": "Falla reportada: {titulo}",
        "falla_cuerpo": ("{quien} reportó una falla desde {desde}. Está en "
                         "Manual del sistema → Casos, por revisar."),
        "falla_desde_consola": "la consola",
        "falla_desde_app": "la app de campo",
        "falla_donde": "Dónde",
        "falla_que_paso": "Qué pasó",
        "falla_resuelta_asunto": "La falla que reportaste quedó resuelta",
        "falla_resuelta_cuerpo": ("La falla que reportaste el {dia} ya quedó "
                                  "resuelta. Gracias por reportarla."),
        "falla_lo_que_reportaste": "Lo que reportaste",
        # --- la incidencia grave, a Recursos Humanos (seccion 105)
        "inc_grave_asunto": "Incidencia grave: {quien} en {folio}",
        "inc_grave_cuerpo": ("Dirección de operaciones autorizó una incidencia "
                             "grave de {quien} en {folio} ({fecha}). El bono "
                             "del mes de {quien} queda en cero y la comisión "
                             "del consultor de ese servicio queda retenida "
                             "hasta que dirección general la decida. Recursos "
                             "Humanos la gestiona desde el expediente de la "
                             "persona."),
        "inc_descripcion": "Qué pasó",
        "inc_registro": "La registró",
        "inc_resolucion": "Resolución",
        "inc_comision": "Comisión del consultor",
        "inc_comision_retenida": "Retenida: la decide dirección general.",
        "inc_comision_al_cerrar": ("Todavía no se genera: se retiene cuando "
                                   "finanzas cierre el servicio."),
        "falla_causa": "La causa",
        "falla_como": "Cómo se arregló",
        # --- el acceso: la invitacion y la recuperacion de contrasena
        "acc_inv_asunto": "Tu acceso a Centauro Connect",
        "acc_inv_cuerpo": ("Hola, {nombre}. Ya tienes acceso a Centauro "
                           "Connect. Para entrar la primera vez, crea tu "
                           "contraseña con el botón."),
        "acc_inv_boton": "Crear mi contraseña",
        "acc_inv_nota": ("El enlace sirve una sola vez y vence el {dia} a "
                         "las {hora}."),
        "acc_rec_asunto": "Para poner una nueva contraseña",
        "acc_rec_cuerpo": ("Alguien pidió cambiar la contraseña de tu acceso "
                           "a Centauro Connect. Si fuiste tú, usa el botón. "
                           "Si no fuiste tú, ignora este correo: tu "
                           "contraseña sigue igual."),
        "acc_rec_boton": "Poner mi nueva contraseña",
        "acc_rec_nota": "El enlace sirve una sola vez y vence a las {hora}.",
        "acc_tu_correo": "Tu correo",
        "acc_entras_como": "Entras como",
        "rol_personal_seguridad": "Personal de seguridad",
        "rol_central": "Central de inteligencia",
        "rol_consultor": "Consultor",
        "rol_director_operaciones": "Dirección de operaciones",
        "rol_director_general": "Dirección general",
        "rol_finanzas": "Finanzas",
        "rol_recursos_humanos": "Recursos Humanos",
        "rol_sistema_calidad": "Sistema y calidad",
        "rol_admin": "Administración (llave maestra)",
        "cie_vb_asunto": "{de_que}: tienes 24 h para el visto bueno",
        "cie_vb_cuerpo": ("La comprobación de viáticos del personal de {de_que} "
                          "terminó. Tus 24 horas para dar el visto bueno y "
                          "mandarlo a finanzas corren hasta el {fecha} a las "
                          "{hora}; de llegar a tiempo depende tu comisión."),
        "cie_vb_que_hacer": ("Abre el servicio en la consola, revisa el "
                             "comparativo y el dinero del personal, y da el "
                             "visto bueno."),
        "cie_reg_asunto": "{de_que}: finanzas lo regresó",
        "cie_reg_cuerpo": ("Finanzas regresó {de_que} a operación. Tienes "
                           "hasta el {fecha} a las {hora} para corregirlo y "
                           "volver a mandarlo; lo en plazo de tu primer visto "
                           "bueno se queda como estaba."),
        "cie_reg_que_hacer": ("Corrige lo que pidió finanzas y vuelve a "
                              "mandarlo a finanzas desde la pantalla del "
                              "servicio."),
        "cie_vence": "Vence",
        "cie_motivo": "Motivo",
        "cie_que_hacer": "Qué hacer",
        # --- seccion 105: el cobro al cancelar y los plazos del cierre
        "cie_cobro_asunto": "{de_que}: operaciones autorizó el cobro {cobro}",
        "cie_cobro_cuerpo": ("Dirección de operaciones autorizó cobrar {de_que} "
                             "{cobro}. Ya puedes dar el visto bueno y mandarlo "
                             "a finanzas; tu plazo corre hasta el {fecha} a "
                             "las {hora}."),
        "cie_cobro_que_hacer": ("Abre el servicio en la consola, revisa el "
                                "comparativo y da el visto bueno."),
        "cie_cobro_completo": "completo: la cotización autorizada tal cual",
        "cie_cobro_ejecutado": "de lo ejecutado: los días que se trabajaron",
        "cie_mitad_asunto": "{de_que}: va la mitad de tu plazo para el visto bueno",
        "cie_mitad_cuerpo": ("Ya pasó la mitad de tu plazo para dar el visto "
                             "bueno de {de_que}: vence el {fecha} a las "
                             "{hora}. De llegar a tiempo depende tu comisión."),
        "cie_mitad_reg_cuerpo": ("Ya pasó la mitad de tus 24 horas desde que "
                                 "finanzas regresó {de_que}: vencen el {fecha} "
                                 "a las {hora}."),
        "cie_mitad_que_hacer": ("Abre el servicio en la consola, revisa el "
                                "comparativo y el dinero del personal, y da el "
                                "visto bueno."),
        "cie_venc_asunto": "{de_que}: venció el plazo del visto bueno",
        "cie_venc_cuerpo": ("Tu plazo para dar el visto bueno de {de_que} "
                            "venció el {fecha} a las {hora}. El servicio sigue "
                            "esperando tu visto bueno, ya sin comisión: "
                            "mándalo cuanto antes para que se facture."),
        "cie_venc_reg_cuerpo": ("Tus 24 horas desde que finanzas regresó "
                                "{de_que} vencieron el {fecha} a las {hora}. "
                                "Sigue esperando que lo vuelvas a mandar; lo "
                                "en plazo de tu primer visto bueno se queda "
                                "como estaba."),
        "cie_venc_que_hacer": ("Abre el servicio en la consola, resuelve lo "
                               "que señale la revisión y mándalo a finanzas."),
        "cie_venc_dir_asunto": "{de_que}: venció el plazo del visto bueno de {consultor}",
        "cie_venc_dir_cuerpo": ("El plazo de {consultor} para dar el visto "
                                "bueno de {de_que} venció el {fecha} a las "
                                "{hora}. El servicio sigue esperando el visto "
                                "bueno, ya sin comisión, y sale entre los "
                                "plazos vencidos de Dirección de operaciones."),
        "cie_venc_dir_reg_cuerpo": ("Las 24 horas de {consultor} desde que "
                                    "finanzas regresó {de_que} vencieron el "
                                    "{fecha} a las {hora}. El servicio sigue "
                                    "esperando que lo vuelva a mandar."),
        "cie_venc_dir_que_hacer": ("Revisa con el consultor qué frena el visto "
                                   "bueno; dirección de operaciones puede "
                                   "darlo como cobertura."),
        "cie_consultor": "Consultor",
        # Seccion 107: la entrega de la unidad despues del fin del dia.
        "ent_venc_asunto": "{folio}: la unidad {placa} no se entregó a tiempo",
        "ent_venc_cuerpo": ("{quien} no entregó la unidad {placa} de {folio} "
                            "con su revisión antes del {fecha} a las {hora}. "
                            "Sigue por entregar: el cierre del servicio la "
                            "reclama hasta que se entregue o se registre "
                            "como entregada sin revisión."),
        "ent_venc_que_hacer": ("Que el conductor la entregue con las cinco "
                               "fotos desde su app. Si ya no se puede, "
                               "regístrala como entregada sin revisión desde "
                               "la revisión de la unidad en el servicio, con "
                               "la razón."),
        "ent_unidad": "Unidad",
        "ent_quien": "Responsable",
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
        "tit_entra_asunto": "{folio}: agora você é o consultor titular",
        "tit_entra_cuerpo": ("{quien} colocou você como consultor titular de "
                             "{folio} ({cliente}). A partir de agora os "
                             "avisos, os prazos e a comissão são seus."),
        "tit_sale_asunto": "{folio}: {nuevo} passa a ser o consultor titular",
        "tit_sale_cuerpo": ("{quien} trocou o consultor titular de {folio} "
                            "({cliente}): a partir de agora quem leva é "
                            "{nuevo}. O que já foi fechado e pago a você "
                            "fica como estava."),
        "tit_servicio": "Serviço",
        "tit_quien": "Quem trocou",
        "tit_nuevo": "Consultor titular",
        "tit_anterior": "Titular anterior",
        "tit_motivo": "Motivo",
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
        "extra_asunto_ya": "O serviço já está em horas extras",
        "extra_cuerpo_ya": ("O serviço completou suas {horas} horas "
                            "contratadas às {hora}. Desde esse momento "
                            "correm horas extras."),
        "fin_asunto": "{folio}: serviço encerrado",
        "fin_cuerpo": "O serviço de {dia} terminou às {hora}.",
        "fin_con_extra": ("Foram geradas {horas} horas extras além do "
                          "horário contratado."),
        "fin_con_extra_una": ("Foi gerada 1 hora extra além do horário "
                              "contratado."),
        "fin_sin_extra": "O serviço encerrou dentro do horário contratado.",
        # --- la incidencia grave, a Recursos Humanos (seccion 105)
        "inc_grave_asunto": "Incidente grave: {quien} em {folio}",
        "inc_grave_cuerpo": ("A direção de operações autorizou um incidente "
                             "grave de {quien} em {folio} ({fecha}). O bônus "
                             "do mês de {quien} fica em zero e a comissão do "
                             "consultor desse serviço fica retida até a "
                             "direção geral decidir. Recursos Humanos cuida "
                             "dele a partir da ficha da pessoa."),
        "inc_descripcion": "O que aconteceu",
        "inc_registro": "Registrado por",
        "inc_resolucion": "Resolução",
        "inc_comision": "Comissão do consultor",
        "inc_comision_retenida": "Retida: a direção geral decide.",
        "inc_comision_al_cerrar": ("Ainda não foi gerada: fica retida quando "
                                   "finanças fechar o serviço."),
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
        "cap_vence_cuerpo": "O certificado de {quien} está para vencer. Uma certificação vencida não é uma certificação, e no dia em que o cliente perguntar quem vai cuidar do seu executivo, essa data é a resposta. Reinscrevê-lo agora evita tirá-lo de serviços depois.",
        "cap_quien": "Quem",
        "cap_curso": "Certificado",
        "cap_institucion": "Instituição",
        "cap_vence": "Vence",
        # O prontuário do freelance (seção 111).
        "fre_quien": "Freelance",
        "fre_servicio": "Serviço",
        "fre_hasta": "Prazo",
        "fre_motivo": "Por que é urgente",
        "fre_respuesta": "Resposta",
        "fre_faltaba": "O que falta",
        "fre_documento": "Documento",
        "fre_vence": "Vence",
        "fre_plazo_asunto": "{quien}: segundo serviço, até {fecha} para completar o de programado",
        "fre_plazo_cuerpo": "{quien} é freelance de emergência e acabou de receber o segundo serviço ({folio}). Tem até {fecha} para completar os requisitos de programado; depois dessa data não é mais escalado até completá-los.",
        "fre_plazo_vencio_asunto": "{quien}: venceu o prazo para completar o de programado",
        "fre_plazo_vencio_cuerpo": "{quien} tinha até {fecha} para completar os requisitos de programado. Não é mais escalado até completá-los, a menos que a direção de operações autorize uma urgência para um serviço.",
        "fre_urgencia_asunto": "Autoriza {quien} para {folio}?",
        "fre_urgencia_cuerpo": "O freelance {quien} tem o prontuário incompleto e foi pedido por urgência para o serviço {folio}. Autorize ou não na sua caixa da direção de operações, com o seu motivo.",
        "fre_respuesta_si_asunto": "{quien}: autorizado para {folio}",
        "fre_respuesta_no_asunto": "{quien}: não autorizado para {folio}",
        "fre_respuesta_cuerpo": "A direção de operações respondeu à sua urgência por {quien} para o serviço {folio}: {respuesta}",
        "fre_vence_pronto": "{quien}: {documento} vence em {dias} dias",
        "fre_vence_hoy": "{quien}: {documento} vence hoje",
        "fre_vencio": "{quien}: {documento} já venceu",
        "fre_vence_cuerpo": "Um documento do prontuário do freelance {quien} está para vencer ou já venceu. Com um documento vencido ele não é escalado: peça o novo e envie em Pessoal de segurança → Freelance.",
        # O preço especial da proposta do implantado (seção 115).
        "prop_folio": "Proposta",
        "prop_cliente": "Cliente",
        "prop_mensual": "Mensal, sem impostos",
        "prop_motivo": "Por que é especial",
        "prop_nota": "Nota",
        "prop_especial_asunto": "{folio}: preço especial para autorizar",
        "prop_especial_cuerpo": "{quien} pede a sua aprovação do preço especial da proposta {folio} para {cliente}: {motivo}. Autorize ou não na sua caixa da direção de operações; sem ela a proposta não pode ser enviada.",
        "prop_especial_si_asunto": "{folio}: preço especial autorizado",
        "prop_especial_si_cuerpo": "{quien} autorizou o preço especial da proposta {folio} para {cliente}. Você já pode enviá-la.",
        "prop_especial_no_asunto": "{folio}: preço especial não autorizado",
        "prop_especial_no_cuerpo": "{quien} não autorizou o preço especial da proposta {folio} para {cliente}: {nota}. Corrija-a e peça de novo.",
        "cob_asunto": "{folio}: {quien} mexeu no seu serviço",
        "cob_cuerpo": ("{quien} trabalhou no seu serviço enquanto "
                       "cobria a sua carteira. Ficou registrado; isto "
                       "é só para você saber, não há nada a fazer."),
        "quien": "Quem",
        "que_hizo": "O que fez",
        "detalle": "Detalhe",
        # --- reportar una falla (seccion 92)
        "falla_asunto": "Falha reportada: {titulo}",
        "falla_cuerpo": ("{quien} reportou uma falha pelo {desde}. Está em "
                         "Manual do sistema → Casos, para revisar."),
        "falla_desde_consola": "console",
        "falla_desde_app": "app de campo",
        "falla_donde": "Onde",
        "falla_que_paso": "O que aconteceu",
        "falla_resuelta_asunto": "A falha que você reportou foi resolvida",
        "falla_resuelta_cuerpo": ("A falha que você reportou em {dia} já foi "
                                  "resolvida. Obrigado por reportá-la."),
        "falla_lo_que_reportaste": "O que você reportou",
        "falla_causa": "A causa",
        "falla_como": "Como foi resolvida",
        # --- el acceso: la invitacion y la recuperacion de contrasena
        "acc_inv_asunto": "Seu acesso ao Centauro Connect",
        "acc_inv_cuerpo": ("Olá, {nombre}. Você já tem acesso ao Centauro "
                           "Connect. Para entrar pela primeira vez, crie sua "
                           "senha com o botão."),
        "acc_inv_boton": "Criar minha senha",
        "acc_inv_nota": ("O link funciona uma única vez e vence {dia}, às "
                         "{hora}."),
        "acc_rec_asunto": "Para definir uma nova senha",
        "acc_rec_cuerpo": ("Alguém pediu para mudar a senha do seu acesso ao "
                           "Centauro Connect. Se foi você, use o botão. Se "
                           "não foi você, ignore este e-mail: sua senha "
                           "continua a mesma."),
        "acc_rec_boton": "Definir minha nova senha",
        "acc_rec_nota": "O link funciona uma única vez e vence às {hora}.",
        "acc_tu_correo": "Seu e-mail",
        "acc_entras_como": "Você entra como",
        "rol_personal_seguridad": "Pessoal de segurança",
        "rol_central": "Central de inteligência",
        "rol_consultor": "Consultor",
        "rol_director_operaciones": "Direção de operações",
        "rol_director_general": "Direção geral",
        "rol_finanzas": "Finanças",
        "rol_recursos_humanos": "Recursos Humanos",
        "rol_sistema_calidad": "Sistema e qualidade",
        "rol_admin": "Administração (chave mestra)",
        "cie_vb_asunto": "{de_que}: você tem 24 h para o visto",
        "cie_vb_cuerpo": ("A comprovação de despesas da equipe de {de_que} "
                          "terminou. Suas 24 horas para dar o visto e mandar "
                          "para finanças correm até {fecha} às {hora}; sua "
                          "comissão depende de chegar a tempo."),
        "cie_vb_que_hacer": ("Abra o serviço no console, revise o comparativo "
                             "e o dinheiro da equipe, e dê o visto."),
        "cie_reg_asunto": "{de_que}: finanças devolveu",
        "cie_reg_cuerpo": ("Finanças devolveu {de_que} para a operação. Você "
                           "tem até {fecha} às {hora} para corrigir e mandar "
                           "de novo; o 'no prazo' do seu primeiro visto fica "
                           "como estava."),
        "cie_reg_que_hacer": ("Corrija o que finanças pediu e mande de novo "
                              "para finanças a partir da tela do serviço."),
        "cie_vence": "Vence",
        "cie_motivo": "Motivo",
        "cie_que_hacer": "O que fazer",
        # --- seccion 105: el cobro al cancelar y los plazos del cierre
        "cie_cobro_asunto": "{de_que}: operações autorizou a cobrança {cobro}",
        "cie_cobro_cuerpo": ("A direção de operações autorizou cobrar {de_que} "
                             "{cobro}. Você já pode dar o visto e mandar para "
                             "finanças; seu prazo corre até {fecha} às "
                             "{hora}."),
        "cie_cobro_que_hacer": ("Abra o serviço no console, revise o "
                                "comparativo e dê o visto."),
        "cie_cobro_completo": "completa: a cotação autorizada tal como está",
        "cie_cobro_ejecutado": "do executado: os dias que se trabalharam",
        "cie_mitad_asunto": "{de_que}: já passou a metade do seu prazo para o visto",
        "cie_mitad_cuerpo": ("Já passou a metade do seu prazo para dar o "
                             "visto de {de_que}: vence {fecha} às {hora}. Sua "
                             "comissão depende de chegar a tempo."),
        "cie_mitad_reg_cuerpo": ("Já passou a metade das suas 24 horas desde "
                                 "que finanças devolveu {de_que}: vencem "
                                 "{fecha} às {hora}."),
        "cie_mitad_que_hacer": ("Abra o serviço no console, revise o "
                                "comparativo e o dinheiro da equipe, e dê o "
                                "visto."),
        "cie_venc_asunto": "{de_que}: venceu o prazo do visto",
        "cie_venc_cuerpo": ("Seu prazo para dar o visto de {de_que} venceu "
                            "{fecha} às {hora}. O serviço continua esperando "
                            "o seu visto, já sem comissão: mande o quanto "
                            "antes para que seja faturado."),
        "cie_venc_reg_cuerpo": ("Suas 24 horas desde que finanças devolveu "
                                "{de_que} venceram {fecha} às {hora}. Continua "
                                "esperando que você mande de novo; o 'no "
                                "prazo' do seu primeiro visto fica como "
                                "estava."),
        "cie_venc_que_hacer": ("Abra o serviço no console, resolva o que a "
                               "revisão apontar e mande para finanças."),
        "cie_venc_dir_asunto": "{de_que}: venceu o prazo do visto de {consultor}",
        "cie_venc_dir_cuerpo": ("O prazo de {consultor} para dar o visto de "
                                "{de_que} venceu {fecha} às {hora}. O serviço "
                                "continua esperando o visto, já sem comissão, "
                                "e aparece entre os prazos vencidos da Direção "
                                "de operações."),
        "cie_venc_dir_reg_cuerpo": ("As 24 horas de {consultor} desde que "
                                    "finanças devolveu {de_que} venceram "
                                    "{fecha} às {hora}. O serviço continua "
                                    "esperando que seja mandado de novo."),
        "cie_venc_dir_que_hacer": ("Veja com o consultor o que segura o visto; "
                                   "a direção de operações pode dá-lo como "
                                   "cobertura."),
        "cie_consultor": "Consultor",
        "ent_venc_asunto": "{folio}: a unidade {placa} não foi entregue no prazo",
        "ent_venc_cuerpo": ("{quien} não entregou a unidade {placa} de {folio} "
                            "com a sua revisão até {fecha} às {hora}. Continua "
                            "por entregar: o fechamento do serviço cobra até "
                            "que seja entregue ou registrada como entregue "
                            "sem revisão."),
        "ent_venc_que_hacer": ("Que o motorista a entregue com as cinco fotos "
                               "pelo app. Se já não for possível, registre "
                               "como entregue sem revisão na revisão da "
                               "unidade do serviço, com o motivo."),
        "ent_unidad": "Unidade",
        "ent_quien": "Responsável",
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

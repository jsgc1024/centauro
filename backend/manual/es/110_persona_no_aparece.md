---
id: sintoma-persona-no-aparece
parte: resolver
orden: 110
area: Personas y unidades
titulo: Una persona no aparece para asignarla
buscar: asignar persona no aparece no sale lista ocupado con riesgo traslado disponible equipo
---
### Qué ves
Al asignar gente a un equipo, la persona no sale en la lista, o sale como **Ocupado** o **Con riesgo**, o con su ciudad y «traslado».

### Por qué pasa · de lo más común a lo menos
1. **No sale en la lista: no ha llegado de Odoo.** Su puesto en Odoo no es «Personal de Seguridad» o «Security Driver», su ubicación de trabajo no es una ciudad de Centauro, o la lectura del personal todavía no se ha hecho. También si está dada de baja o si es de oficina.
   Cómo confirmarlo: [Odoo](#/odoo) → El personal de seguridad → Ensayo. Si sale en pendientes, dice qué le falta.
2. **Sale «Ocupado»:** ese día ya trabaja en otro servicio a la misma hora, o en un día completo. El motivo sale abajo de su nombre, con el día.
3. **Sale «Con riesgo»:** le quedan menos de dos horas entre un servicio y otro, o trae una jornada que cruza la medianoche. Se puede asignar igual: decide el consultor.
4. **Sale con «traslado»:** es de otra ciudad. Se le puede mandar, con sus viáticos.

### Cómo se arregla
El 1 lo corrige Recursos Humanos en Odoo, y Centauro lo toma en la siguiente lectura, a los :17 de cada hora. Del 2 al 4 no hay nada que arreglar: el calendario está cuidando que nadie se empalme.

> **La causa de fondo:** Centauro no captura personas; todas llegan de Odoo. Si alguien falta, casi siempre el dato está incompleto allá.

---
id: sintoma-persona-no-aparece
parte: resolver
orden: 110
area: Pessoas e unidades
titulo: Uma pessoa não aparece para ser designada
buscar: designar pessoa nao aparece lista ocupado com risco deslocamento disponivel equipe empresa brasil motorista condutor
---
### O que você vê
Ao designar pessoas para uma equipe, a pessoa não aparece na lista, ou aparece como **Ocupado** ou **Com risco**, ou com a sua cidade e «deslocamento».

### Por que acontece · do mais comum ao menos comum
1. **Não aparece na lista: não chegou do Odoo.** O seu cargo no Odoo não é «Personal de Seguridad» ou «Security Driver» —no Brasil, «Motorista Executivo Bilíngue» ou «Condutor Folguista»—, a sua empresa no Odoo não é a do seu país, o seu local de trabalho não é uma cidade do seu país no Centauro, ou a leitura do pessoal ainda não foi feita. Também se está desligada ou se é do escritório.
   Como confirmar: [Odoo](#/odoo) → Pessoal → Ensaio. Se aparecer nos pendentes, diz o que falta.
2. **Aparece «Ocupado»:** nesse dia já trabalha em outro serviço no mesmo horário, ou num dia inteiro. O motivo aparece abaixo do nome, com o dia.
3. **Aparece «Com risco»:** tem menos de duas horas entre um serviço e outro, ou uma jornada que passa da meia-noite. Pode ser designada do mesmo jeito: quem decide é o consultor.
4. **Aparece com «deslocamento»:** é de outra cidade. Pode ser enviada, com as suas diárias.
5. **É freelancer e aparece em vermelho:** o prontuário não está pronto, falta o custo ou é um implantado. Ver [um freelancer não pode ser escalado](#/manual/leer/sintoma-freelance-no-se-asigna).

### Como se resolve
O 1 é corrigido pelos Recursos Humanos no Odoo, e o Centauro o pega na leitura seguinte, aos :17 de cada hora. Do 2 ao 4 não há nada a corrigir: o calendário está cuidando para que ninguém se sobreponha. O 5 se resolve na ficha dele, em Equipe de segurança → Freelance.

> **A causa raiz:** o Centauro não cadastra a equipe do quadro; ela chega do Odoo. Se alguém do quadro falta, quase sempre o dado está incompleto lá. O freelancer sim é cadastrado aqui, em Equipe de segurança → Freelance.

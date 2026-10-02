---
id: piezas
parte: entender
orden: 10
titulo: As peças do sistema e como elas se falam
resumen: O console, o app de campo, o servidor, o relógio, o Odoo, o GPS, o e-mail e os avisos no telefone. Quase tudo o que trava vive numa dessas peças.
buscar: arquitetura servidor google cloud banco de dados redis worker beat odoo pegasus amazon ses email push backup arquivo
---
O Centauro Connect não é um programa só: são várias peças que passam dados entre si. Quando algo trava, a primeira pergunta é **em qual peça**, e a segunda, **o que chegou ou o que faltou para ela**.

## O que se vê

### O console
Onde o escritório trabalha, em **mycentauro.lat**: a operação, o dinheiro, os acessos, o Odoo, os catálogos, a qualidade e este manual. Cada um vê o menu do seu cargo; o que pode fazer lá dentro sai das suas atividades (ver [quem pode o quê](#/manual/permisos)).

### O app de campo, EP Connect
O do pessoal de segurança, no telefone, em **appep.mycentauro.lat**. Ali a pessoa vê o seu dia, marca a chegada, o contato com o executivo e o fim, envia os seus comprovantes e tem o botão de pânico. Entra com o seu **e-mail pessoal** e define a senha com um **código de quatro dígitos** que o seu consultor ou a central lhe dita.

## O que não se vê

### O servidor
Uma máquina no Google Cloud, em Querétaro, com o relógio no horário do México. Ali vivem a API —a que responde ao console e ao app—, o banco de dados e o relógio. Toda noite, às 2:30, é feito o backup do banco, e às 3:00 se tira a foto do disco.

### O relógio
Vinte tarefas que rodam sozinhas: ler o GPS a cada dois minutos, enviar os e-mails a cada cinco, avançar os fechamentos, ler o Odoo a cada hora, o fechamento de segunda-feira, as estrelas do mês. Cada tarefa anota a sua última volta: em [o que o sistema faz sozinho](#/manual/reloj) se vê quando cada uma rodou. Se o relógio para, deixa de acontecer tudo o que acontece sozinho, mesmo que o console continue abrindo.

### O Odoo
A fonte de verdade do pessoal de segurança, do escritório, da frota e da oficina, dos clientes e das tabelas de preços. O Centauro **o lê**, e a única coisa que escreve nele é a pré-fatura em rascunho que sai com o aval: o que vem do Odoo se corrige no Odoo e chega sozinho na leitura seguinte. Ver [o que vem do Odoo](#/manual/leer/odoo).

### O GPS
O Pegasus, da Centauro Satelital. Com serviços na rua, a cada dois minutos as unidades são lidas: o pânico, o caminho até o ponto, a corrente e a segunda testemunha das marcações. Sem ninguém na rua, a cada quinze, só para saber qual reporta. Cada unidade do Pegasus se liga sozinha à do Centauro **pela placa**, e a placa sai da frota do Odoo: sem a frota lida, nenhuma se liga.

### O e-mail
Sai de **connect@mycentauro.lat** pelo Amazon SES, e as respostas chegam em cecc.notification@centauro.lat. Leva os convites e as recuperações de senha, os avisos aos clientes e as pesquisas. É escrito na hora e sai a cada cinco minutos; o aviso operacional que passa de 24 horas sem sair já não sai, e o convite, a recuperação e a pesquisa vivem o que vive o seu link. Enquanto o e-mail estiver desligado, nada sai e tudo espera.

### Os avisos no telefone
Os lembretes e alertas que chegam ao telefone mesmo com o app fechado. Precisam de duas coisas: as chaves colocadas no servidor, e que cada telefone os tenha aceitado.

### O arquivo de comprovantes
Três meses depois de faturado um serviço, as fotos dos seus comprovantes vão para o arquivo, à 1:30 da manhã. Continuam disponíveis; só mudam de lugar.

> A causa raiz de quase tudo o que trava está numa dessas peças: um dado que falta no Odoo, o relógio parado, o e-mail desligado, uma placa que não se liga ou um telefone sem avisos. O [estado do sistema](#/manual/atorado) revisa todas de uma vez.

---
id: sintoma-correo-cliente
parte: resolver
orden: 610
area: E-mail e avisos
titulo: Um e-mail não chegou ao cliente
buscar: email nao chegou cliente executivo solicitante aviso equipe no local servico iniciado terminado task sheet pesquisa desligado vencido sem email falhou spam corrigir contatos mal escrito volta
---
### O que você vê
O executivo ou quem pediu o serviço diz que não chegou o aviso: a equipe no ponto, o serviço iniciado ou terminado, a task sheet, uma troca de equipe ou a pesquisa.

### Por que acontece · do mais comum ao menos comum
1. **O e-mail está desligado.** Enquanto não for ligado não sai nenhum: os avisos esperam.
2. **Passaram mais de 24 horas.** Um aviso operacional que não saiu em 24 horas já não sai, e também não o que leva um link que já venceu. Um «a sua equipe está no local» de dias atrás faz duvidar de todo o sistema. O convite de acesso, a recuperação de senha e a pesquisa vivem o que vive o seu link (72 horas, 2 horas e 15 dias): saem mesmo que o e-mail seja ligado dois dias depois. Se o provedor não responde, o aviso espera e tenta de novo enquanto vive; o que de fato falhou volta para a fila com «Tentar de novo os que falharam», no estado do sistema.
3. **Não tinha para onde ir.** Falta no serviço o e-mail do executivo ou o de quem o pediu: o aviso é deixado de lado.
4. **O endereço está mal escrito**, ou o servidor do cliente o rejeitou. Tenta-se cinco vezes e fica como falha, com o último que o provedor disse.
5. **Chegou em outra pasta**: spam ou promoções.
6. **Esse aviso não se manda nesse dia.** Uma troca de equipe vai por e-mail só se for do dia em curso; a de outro dia viaja na task sheet.

### Como confirmar
O [estado do sistema](#/manual/atorado) diz se o e-mail está ligado, quantos avisos esperam e quantos falharam. No serviço, **Corrigir os contatos** —em cima, junto ao status— mostra o e-mail do executivo e o de quem o pediu, tal como estão.

### Como se resolve
- **Desligado:** quem o liga é o Salvador, no servidor.
- **Outra pasta:** que o cliente marque o e-mail como seguro.
- **Sem e-mail ou mal escrito:** o consultor do serviço —ou quem o cobre— o corrige em **Corrigir os contatos**, enquanto o serviço não estiver fechado nem cancelado. Os avisos que ainda não saíram e a pesquisa sem resposta vão para o endereço novo, e fica no registro do serviço com o que havia antes. Se o e-mail anterior estiver em outro serviço aberto do cliente, ao salvar se diz em qual.
- O que já venceu não é enviado de novo: o seu momento já passou.

> **A causa raiz:** «não foi enviado» e «não chegou» são duas coisas diferentes. O sistema diz qual foi, e nunca manda tarde o que já não serve.

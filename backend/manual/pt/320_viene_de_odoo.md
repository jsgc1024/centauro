---
id: sintoma-viene-de-odoo
parte: resolver
orden: 320
area: Odoo
titulo: Não me deixa editar um dado: diz que vem do Odoo
buscar: vem do odoo corrige no odoo nao deixa editar catalogo nome placa rfc tabela de precos lista do odoo
---
### O que você vê
Ao editar uma pessoa, uma unidade ou um cliente no Centauro, o sistema diz, em espanhol, **«Viene de Odoo: se corrige en Odoo»**. Ou, numa tabela de preços, que é uma lista do Odoo.

### Por que acontece
O que vem do Odoo não se edita no Centauro, de propósito: se fosse possível, a leitura seguinte o deixaria de novo como diz o Odoo, e haveria duas versões do mesmo dado. Desde que as tabelas de preços são lidas do Odoo, a tabela de um cliente do Odoo também se corrige lá.

### Como se resolve
Muda-se no Odoo —os Recursos Humanos na ficha do funcionário, a Frota na da unidade, o financeiro na do cliente ou na sua lista de preços— e o Centauro o pega na leitura seguinte. O que é do Centauro —a que serviço alguém vai, com que função, as suas diárias— continua sendo editado aqui.

> **A causa raiz:** uma só fonte de verdade. O que vem do Odoo se corrige uma vez, lá.

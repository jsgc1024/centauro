---
id: implantado
parte: entender
orden: 30
titulo: O implantado, mês a mês
resumen: O serviço de longo prazo com a mesma equipe, que se trabalha e se cobra por mês: os seus termos, o seu mês, as suas substituições e o seu fechamento.
buscar: implantado contrato mes termos acordo equipe titular 12x36 substituicao oficina fechamento do mes fatura lista de implantados
---
O implantado é um serviço de longo prazo com a mesma equipe, que se trabalha e se cobra **por mês**. O seu folio é de outra série, EP/IM-001, porque é outra operação.

## Os termos do mês
Cada mês tem o seu acordo: se cobra por dia ou por mês inteiro, se inclui fins de semana, os dias base, a hora de apresentação, a modalidade e os preços. Os preços saem da **lista de implantados** do cliente no Odoo. Se o mês leva outros, o sistema avisa: pode ser um acordo especial com o cliente, e então fica assim.

## O mês
O relógio abre sozinho o mês seguinte quando faltam poucos dias para o mês em curso acabar, às 6:30; se esteve desligado, na primeira volta que rodar abre o que faltar até o mês em curso. O mês traz a sua equipe: quem é o titular e que unidade leva; o servidor exige pessoal de segurança ativo da cidade do serviço e uma unidade fixa disponível, e ao abrir cada mês revisa de novo: se alguém foi desligado ou a unidade está na oficina, essa posição fica por cobrir, em âmbar, com o seu alerta para a central e o aviso ao consultor. No Brasil existe o 12 × 36: duas pessoas que se revezam nos sete dias; com um mês já gerado o turno não muda (fecha-se o implantado e cadastra-se outro).

## As substituições
Quando o titular não pode ir, ele é substituído por um intervalo de dias, de pessoal ou de unidade. Cobrir um só dia se faz na ficha do dia, com a posição que se cobre: o substituto toma a função dessa posição. Um dia cancelado é reativado antes de ser coberto. A unidade na oficina —segundo as entradas da frota no Odoo, ou as colocadas a partir do mês— não é oferecida; a que entrou sem data de saída sai com «Saiu da oficina» no bloco do mês, e a que veio do Odoo é fechada no Odoo.

## O fechamento do mês
O implantado não fecha por serviço, mas **por mês**: o fechamento de cada mês começa sozinho ao fechar o seu último dia trabalhado, também em um implantado cancelado com dias trabalhados, que continua na carteira enquanto um mês seu tiver fechamento por terminar. Tem o seu aval e a sua fatura do mês, com as horas extras na sua linha. A folha paga o implantado por dia trabalhado, e a comissão do consultor é 1 % do faturado, sem despesas nem impostos.

> Se o mês seguinte não abriu, olha-se o [relógio](#/manual/reloj); se saiu com outros preços, a sua lista de implantados no Odoo; se o seu fechamento não começa, o seu último dia sem fechar.

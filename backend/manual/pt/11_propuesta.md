---
id: propuesta
parte: entender
orden: 27
titulo: A proposta do implantado
resumen: A proposta que se manda ao cliente antes de o implantado existir: o que leva por mês, as suas três modalidades, o preço especial que a direção de operações aprova, o PDF e o implantado que nasce dela.
buscar: proposta implantado ep/pro referencia versao mensal por mes modalidade segunda a sexta segunda a sabado mes inteiro 22 26 30 dias dia adicional hora extra jornada diarias incluidas mais diarias preco especial aval direcao de operacoes lista de implantados empresa nova pdf aprovar implantado nasce escopo catalogos primeiro mes meio do mes
---
A proposta do implantado se monta em **Operações EP → Cotações**, junto com a cotação do eventual, com **«Nova proposta»**. Sai em PDF, o consultor a manda ao cliente pelo seu e-mail e, quando o cliente aprova, **nasce o implantado** em EP implantado com a proposta dentro. Não se chama cotação: na tela e no PDF diz «proposta».

## A referência e as versões {#folio}
Cada proposta leva a sua referência —**EP/PRO-0001**— e a sua versão, com numeração própria: EP/COT-0001 e EP/PRO-0001 são números diferentes. Se o cliente pede uma mudança, faz-se a versão seguinte com o que mudou; ao enviá-la, a anterior fica substituída e só a última pode ser aprovada.

## O que leva, por mês {#lleva}
Cada linha é um posto —uma pessoa todos os dias da modalidade—, uma unidade —o mês inteiro— ou o motorista com a sua unidade, se a lista do cliente o prevê em um só preço. Cada linha pode ter o nome como o cliente a lê: «Motorista de segurança bilíngue», «Toyota RAV4».

**Os preços saem da lista de implantados do cliente no Odoo**: o mensal é o seu preço de dia inteiro vezes os dias da modalidade. Digitar outro mensal o torna **preço especial**, e o mesmo vale para o cliente sem lista ou para a empresa que ainda não está no Odoo: ali os preços são digitados.

## A modalidade, as diárias e o horário {#modalidad}
Três modalidades:
- **Segunda a sexta · 22 dias por mês**: o sábado ou o domingo que se pedir é dia adicional.
- **Segunda a sábado · 26 dias por mês**: o domingo que se pedir é dia adicional.
- **Mês inteiro · 30 dias a custo fixo**: sem dias adicionais. No Brasil, o 12 × 36 vai assim.

Nas três, **mais diárias** —cada mês se faturam as comprovadas, com o seu detalhamento— ou **diárias incluídas** no mensal. O mensal não muda mesmo que o mês traga 21 ou 23 dias úteis. O **dia adicional** é o preço por dia das pessoas; a **hora extra**, a da equipe, da lista ou digitada. A jornada é a do país se não se disser outra, e a hora de apresentação não sai no PDF: passa ao implantado. Se o serviço **começar no meio do mês**, o primeiro mês é cobrado por dia de serviço; se começar no primeiro dia da sua modalidade —a segunda-feira 2, com o dia 1 num domingo—, cobra-se o seu mensal.

## O preço especial {#especial}
O preço que não sai da lista de implantados do cliente é **aprovado pela direção de operações antes de enviar**. O consultor escreve por quê e pede o aval; chega à direção de operações por e-mail e na sua janela, em «Preços especiais por aprovar», com o que se pediu e o que diria a lista. Aprovado, acende «Baixar o PDF e marcá-la enviada»; se não, o consultor lê a nota, corrige e pede de novo. Se depois mudar um preço já aprovado, ele é pedido de novo. Quem pode aprová-lo, ao salvar, a deixa aprovada de uma vez.

## O PDF e enviá-la {#pdf}
«Ver o PDF» a mostra como está. «Baixar o PDF e marcá-la enviada» salva o PDF exatamente como sai e o baixa para enviá-lo pelo e-mail; o que foi enviado não muda mais. O PDF leva o que se leva por mês com o seu mensal, subtotal, impostos e mensal com impostos —o cliente que não paga impostos se marca na sua proposta—, o que se cobra à parte (dia adicional, hora extra e diárias), os dias e o horário, o que inclui e o que não inclui, as responsabilidades, a confidencialidade, o escopo do serviço, a aprovação, a validade e a assinatura do consultor. Os textos vivem em **Catálogos → Proposta ao cliente**, por país e por idioma, e quem os define é a direção de operações; o escopo sai do de cada posto que leva e pode ser trocado em cada proposta.

## Aprovada: nasce o implantado {#autorizar}
Com **«O cliente aprovou»** registra-se quem, que dia e, se houver, o e-mail ou o PDF assinado. Ao salvar nasce o implantado em EP implantado: o cliente, a cidade, o solicitante, os dias da modalidade, a hora, o dia de início e o que foi acordado, com a proposta aprovada dentro. Falta o de qualquer cadastro: o executivo principal, o ponto fixo e quem vai em qual unidade. A empresa que não estava no Odoo, para ser aprovada, já precisa estar no Odoo: ali se escolhe o seu cliente. O seu **primeiro mês se abre com o que o cliente aprovou** —o mensal, o dia adicional, a hora extra, a jornada e as diárias— e os meses seguintes copiam o anterior. Ver [o implantado, mês a mês](#/manual/leer/implantado).

> A proposta recusada ou vencida segue como a cotação; ver [a cotação ao cliente](#/manual/leer/cotizaciones).

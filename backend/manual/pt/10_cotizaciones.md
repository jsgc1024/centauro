---
id: cotizaciones
parte: entender
orden: 25
titulo: A cotação ao cliente
resumen: A cotação do eventual que se monta no Connect antes de o serviço existir: a sua referência e as suas versões, o PDF, a aprovação do cliente e o serviço que nasce dela.
buscar: cotacao cotar referencia ep/cot versao pdf enviar baixar aprovar aprovada recusada vencida substituida rascunho empresa nova prospecto odoo lista geral precos pacote impostos assinatura condicoes catalogos servico nasce introducao fora da cidade
---
A cotação do eventual se monta em **Operações EP → Cotações**, antes de o serviço existir. Sai em PDF, o consultor a manda ao cliente pelo seu e-mail e, quando o cliente aprova, **o serviço nasce sozinho** em EP eventual com esta mesma cotação dentro. A proposta do implantado fica para depois.

## A referência e as versões {#folio}
Cada cotação leva a sua referência do Connect —**EP/COT-0001**— e a sua versão: V1, V2… Se o cliente pede uma mudança, faz-se a versão seguinte e escreve-se o que mudou; ao enviá-la, a anterior fica **substituída**. Só a última pode ser aprovada, e cada versão enviada guarda o PDF que saiu.

## Montá-la {#armar}
Escolhe-se o cliente —ou a empresa que ainda não está no Odoo—, quem pede, o consultor que assina, até quando é válida (31 de dezembro se não se disser outra coisa) e o idioma do PDF, que de início é o do país do cliente. Depois cada equipe: a sua cidade, o que leva todos os dias —a função e o veículo— e os seus dias com a sua modalidade. O dia que é diferente se muda na sua linha, e o que sai da cidade se marca como fora da cidade, com para onde vai. A hora não sai no PDF: passa ao serviço. No fim, como se cobram as despesas —incluídas no preço, valor fixo ou por comprovar— e a introdução, que o Connect escreve com os dados e pode ser trocada.

**Os preços não se digitam**: saem da lista do cliente no Odoo, como no fechamento, e o pacote motorista + veículo sai sozinho se a lista o prevê. Cada dia mostra o seu preço na hora. A empresa que ainda não está no Odoo é cotada com a **lista geral do seu país**.

## O PDF e o envio {#pdf}
«Ver o PDF» mostra como está, em rascunho. **«Baixar o PDF e marcá-la enviada»** salva o PDF exatamente como sai e o baixa: o consultor o manda ao cliente pelo seu e-mail. O que foi enviado não muda mais.

O PDF leva a tabela de cada dia com a sua modalidade, subtotal, impostos e total —o cliente que não paga impostos é marcado na sua cotação—, a hora extra de cada função, as modalidades, como se cobram as despesas, as condições e a assinatura do consultor. A razão social e o RFC da Centauro, a alíquota de impostos e as condições vivem em **Catálogos → Cotação ao cliente**, por país e por idioma, e quem as define é a direção de operações; se faltar algo ali, a tela mostra em amarelo ao montar. Cada consultor envia a sua assinatura uma vez em **Cotações → Sua assinatura**; só ele a troca.

## Aprovada, recusada ou vencida {#autorizar}
O cliente aprova por e-mail, como hoje. O consultor marca com **«O cliente aprovou»**: quem, que dia e, se tiver, o e-mail ou o PDF assinado. Ao salvar, o Connect cadastra o serviço em EP eventual —o cliente, o solicitante, as equipes com a sua cidade, os seus dias, a sua modalidade e a sua hora— com esta cotação **já aprovada dentro e os mesmos preços**. Falta o de qualquer cadastro: o principal de cada equipe e o ponto de partida. A empresa nova, para ser aprovada, já precisa estar no Odoo: ali se escolhe o seu cliente, porque do Odoo sai a fatura.

Se o cliente disser que não, «O cliente recusou» com o motivo. Passada a sua «válida até», o relógio a deixa **vencida** depois da meia-noite; uma vencida ainda pode ser aprovada se o cliente aceitar.

> Se uma mudança chega com o serviço já montado, recota-se no serviço, em «A cotação autorizada», e segue com a mesma referência. Ver [o caminho de um serviço](#/manual/leer/camino).

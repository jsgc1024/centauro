---
id: cotizaciones
parte: entender
orden: 25
titulo: A cotação ao cliente
resumen: A cotação do eventual que se monta no Connect antes de o serviço existir: a sua referência e as suas versões, o PDF, a aprovação do cliente e o serviço que nasce dela.
buscar: cotacao cotar referencia ep/cot versao pdf enviar baixar aprovar aprovada recusada vencida substituida rascunho empresa nova prospecto odoo lista geral precos pacote impostos assinatura condicoes catalogos servico nasce introducao fora da cidade moeda pesos dolares usd mxn taxa de cambio lista acordada reais brasil dolar para real aba pais filtro cliente por pais brasil mexico ja apagado criar o servico de novo excluir a cotacao excluida
---
A cotação do eventual se monta em **Operações EP → Cotações**, antes de o serviço existir. Sai em PDF, o consultor a manda ao cliente pelo seu e-mail e, quando o cliente aprova, **o serviço nasce sozinho** em EP eventual com esta mesma cotação dentro. A proposta do implantado se monta na mesma tela e tem o seu capítulo: [a proposta do implantado](#/manual/leer/propuesta).

## A referência e as versões {#folio}
Cada cotação leva a sua referência do Connect —**EP/COT-0001**— e a sua versão: V1, V2… Se o cliente pede uma mudança, faz-se a versão seguinte e escreve-se o que mudou; ao enviá-la, a anterior fica **substituída**. Só a última pode ser aprovada, e cada versão enviada guarda o PDF que saiu.

## Montá-la {#armar}
Em cima de «Cliente» há uma **aba por país** —México, Brasil—: a lista traz só os clientes desse país, e a empresa que ainda não está no Odoo é desse país. Começa no último país escolhido nesse computador; a que já existe abre no seu. Escolhe-se o cliente —ou a empresa que ainda não está no Odoo—, quem pede, o consultor que assina, até quando é válida (31 de dezembro se não se disser outra coisa) e o idioma do PDF, que de início é o do país do cliente. Depois cada equipe: a sua cidade, o que leva todos os dias —a função e o veículo— e os seus dias com a sua modalidade. O dia que é diferente se muda na sua linha, e o que sai da cidade se marca como fora da cidade, com para onde vai. A hora não sai no PDF: passa ao serviço. No fim, como se cobram as despesas —incluídas no preço, valor fixo ou por comprovar— e a introdução, que o Connect escreve com os dados e pode ser trocada.

**Os preços não se digitam**: saem da lista do cliente no Odoo, como no fechamento, e o pacote motorista + veículo sai sozinho se a lista o prevê. Se os seus pacotes são «Tudo incluído» —com as despesas dentro—, vão em pacote só com as despesas **incluídas no preço**; com valor fixo ou por comprovar, o motorista e o veículo vão ao seu preço da lista e as despesas à parte, igual no fechamento. Cada dia mostra o seu preço na hora. A empresa que ainda não está no Odoo é cotada com a **lista geral do seu país**.

## A moeda {#moneda}
A moeda sai da lista. Se o país tem **lista geral na sua moeda e em dólares** —o México em pesos e dólares; o Brasil em reais e dólares—, o campo **«Moeda»** —ao lado do idioma do PDF— deixa escolhê-la para a empresa que ainda não está no Odoo e para o cliente que está na geral: começa na do país, ou na da lista da sua ficha do Odoo, e ao trocá-la os preços saem da geral dessa moeda. **Nada se converte**: os dólares saem da lista em dólares, tal como está no Odoo. O cliente com **lista acordada** é cotado na moeda da sua lista e o campo não se troca. Com uma só geral, o campo diz a sua moeda e também não se troca.

Em outra moeda que não a do país, a cotação precisa da **taxa de câmbio** que o financeiro define para ser aprovada —o dólar para peso no México e o dólar para real no Brasil—: o cartão de «O cliente aprovou» diz qual vai ficar fixa, ou que falta. Com ela se calculam o lucro e a comissão. Se depois se recota no serviço, segue na moeda que o cliente aprovou.

## O PDF e o envio {#pdf}
«Ver o PDF» mostra como está, em rascunho. **«Baixar o PDF e marcá-la enviada»** salva o PDF exatamente como sai e o baixa: o consultor o manda ao cliente pelo seu e-mail. O que foi enviado não muda mais.

O PDF leva a tabela de cada dia com a sua modalidade, subtotal, impostos e total —o cliente que não paga impostos é marcado na sua cotação—, a hora extra de cada função, as modalidades, como se cobram as despesas, as condições e a assinatura do consultor. A razão social e o RFC da Centauro, a alíquota de impostos e as condições vivem em **Catálogos → Cotação ao cliente**, por país e por idioma, e quem as define é a direção de operações; se faltar algo ali, a tela mostra em amarelo ao montar. Cada consultor envia a sua assinatura uma vez em **Cotações → Sua assinatura**; só ele a troca.

## Aprovada, recusada ou vencida {#autorizar}
O cliente aprova por e-mail, como hoje. O consultor marca com **«O cliente aprovou»**: quem, que dia e, se tiver, o e-mail ou o PDF assinado. Ao salvar, o Connect cadastra o serviço em EP eventual —o cliente, o solicitante, as equipes com a sua cidade, os seus dias, a sua modalidade e a sua hora— com esta cotação **já aprovada dentro e os mesmos preços**. Falta o de qualquer cadastro: o principal de cada equipe e o ponto de partida. A empresa nova, para ser aprovada, já precisa estar no Odoo: ali se escolhe o seu cliente, porque do Odoo sai a fatura.

Se depois o serviço que nasceu é excluído —com «Excluir», antes de começar—, a cotação diz «EP/E-004, já apagado» e oferece duas saídas: **«Criar o serviço de novo»**, com o mesmo e a mesma aprovação —quem, quando, o comprovante e a taxa de câmbio— e número novo; ou **«Excluir a cotação»**, com o seu motivo: saem todas as versões e os seus PDF, fica o registro de quem a excluiu e por quê, e o seu número não volta a ser usado.

Se o cliente disser que não, «O cliente recusou» com o motivo. Passada a sua «válida até», o relógio a deixa **vencida** depois da meia-noite; uma vencida ainda pode ser aprovada se o cliente aceitar.

> Se uma mudança chega com o serviço já montado, recota-se no serviço, em «A cotação autorizada», e segue com a mesma referência. Ver [o caminho de um serviço](#/manual/leer/camino).

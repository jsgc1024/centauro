---
id: odoo
parte: entender
orden: 40
titulo: O que vem do Odoo
resumen: As cinco leituras —pessoal de segurança, frota e oficina, escritório, clientes e tabelas de preços—, o que cada uma traz, quando roda e o que deixa pendente. E a pré-fatura no Odoo, do eventual e do mês do implantado.
buscar: odoo leitura ensaio aplicar primeira leitura pendentes chave etiqueta protecao executiva brasil empresa centauro ass centauro brasil a cadastrar sem cidade cuv blindada local de trabalho email pessoal email de trabalho tabelas de precos produtos lista de implantados desligamento arquivado categoria proteccion ejecutiva PE prefijo gps atlas idioma es_MX fatura pre-fatura rascunho emitir faturista variante variantes gastos de operacion viaticos chave da fatura ODOO_FACTURACION_API_KEY hora extra produto mes implantado referencia origem nao foi possivel enviar no odoo enviar ao odoo nova tentativa cancelado no meio
---
O Odoo é a fonte de verdade. O Centauro **o lê** —a única coisa que escreve nele é a pré-fatura em rascunho, abaixo—, e o que vem do Odoo não se edita no Centauro: corrige-se lá e chega sozinho na leitura seguinte. Três regras valem para as cinco leituras:

- **A primeira é feita à mão**, em [Odoo](#/odoo): primeiro o **Ensaio**, que lê e diz o que faria sem salvar nada, e, se estiver certo, **Aplicar**. A partir daí a leitura se faz sozinha a cada hora. Enquanto não se faz a primeira, a de cada hora não começa.
- **O duvidoso não se adivinha.** O que não bate é reportado como pendente e não se toca. O ensaio diz o que falta em cada caso.
- **A chave é o número interno do Odoo.** Na primeira vez, o que já estava no Centauro é reconhecido pelo e-mail, pela placa ou pelo RFC.

## O pessoal de segurança · a cada hora, aos :17
Entra quem tem no Odoo o cargo «Personal de Seguridad» ou «Security Driver». Traz o nome, a cidade —do **local de trabalho**, e o Estado do México conta como Cidade do México—, o celular, o e-mail pessoal, o número de funcionário, a data de admissão, a foto e a conta bancária (número, banco e titular da sua **conta principal**, da ficha do funcionário no Odoo: aqui não se cadastra; se não se pode ler, a leitura diz se falta a permissão ou se essa versão do Odoo não tem o campo, e não mexe em nada). O círculo com iniciais que o Odoo coloca em quem não tem foto não é uma foto: não é salvo. A pessoa entra no app com o seu **e-mail pessoal**.
Se o Odoo a arquiva, ela é desligada: o seu acesso é fechado —a não ser que deva diárias, que primeiro comprova—, e a central recebe um alerta por cada dia que ela tinha designado.

## A frota e a oficina · a cada hora, aos :27
Cada país lê a sua frota, e elas nunca se misturam: **México**, as unidades da empresa **CENTAURO ASS** com a etiqueta «PROTECCION EJECUTIVA» ou «pe»; **Brasil**, as da empresa **Centauro Brasil** com «PROTECCION EJECUTIVA BRASIL». A etiqueta de um país com a empresa de outro não entra em nenhuma: fica pendente, e a unidade que já estava não muda de país sozinha. Traz a placa, a categoria —as do Odoo são as do Centauro, com a **CUV Blindada** que o Brasil usa—, a cidade da sua **Ubicación**, procurada entre as cidades do seu país, a marca, o modelo, a cor e o ano.
No México a unidade sem Ubicación fica pendente. No Brasil entra do mesmo jeito: a cor e a Ubicación se cadastram depois no Odoo, e enquanto isso a leitura as mostra em **A cadastrar**, sem segurar nada. Sem cidade, a unidade é oferecida nos eventuais do Brasil como «sem cidade» e não vai para um implantado; o GPS dela se liga do mesmo jeito. O Connect não lê o VIN. Se o ensaio disser **Brasil 0** com as unidades cadastradas no Odoo, falta ao usuário da conexão a empresa Centauro Brasil nas suas empresas permitidas.
Da oficina, as entradas de Flotilla → Servicios do tipo Preventivo, Correctivo ou Desgaste natural tiram a unidade de circulação da data de entrada até a de saída; **sem saída, considera-se que ela está lá dentro**. Se o Odoo arquiva a unidade, ela deixa de ser oferecida e a central recebe um alerta por cada dia que ela tinha designado. Se só tiram a etiqueta, fica pendente.

## O escritório · a cada hora, aos :37
É do escritório todo funcionário que não é da segurança. Entra com o seu **e-mail de trabalho**: sem ele, não chega. Chega a pessoa, não o seu acesso: o acesso é dado pelos Recursos Humanos em [Acessos](#/accesos), com o cargo que o Centauro sugere pelo cargo dela no Odoo. Se o Odoo a arquiva, o seu acesso é fechado.

## Os clientes · a cada hora, aos :47
São as empresas com a etiqueta **«Protección ejecutiva»**: assim não chegam as de GPS nem as de carga. Trazem o nome, o RFC e o país. Sem RFC chegam do mesmo jeito, mas não podem ser faturadas. Se o Odoo arquiva o cliente, ele deixa de ser oferecido para um serviço novo; se só tiram a etiqueta, fica pendente e o Centauro já não lê as suas mudanças.

## As tabelas de preços · a cada hora, aos :57
Cada país tem a sua lista geral —a que traz o seu grupo de países no Odoo— e o cliente que negociou tem a sua, colocada na ficha dele. A dos seus implantados vai no campo «Lista de implantados». Só se lê o que é de Proteção Executiva (seção 112): as listas cujo nome começa com **«PE ·»** —«PE · General México», «PE · Control Risks»— e os produtos da categoria **«Protección Ejecutiva»** do Odoo, com as suas subcategorias. O GPS, a Central de Inteligencia e o ATLAS já não chegam. Os nomes são lidos em espanhol do México. Três cuidados:
- Só põe preço o que o financeiro já **confirmou** em Faturamento → Tabelas de preços: um preço mal lido é cobrado.
- Um cliente não é trocado para uma lista da qual o Centauro ainda não sabe ler nenhum preço: fica com a tabela que tinha. Se a lista dele não começa com «PE ·», também não: fica nos pendentes para colocar a sua lista de PE no Odoo.
- Se a categoria «Protección Ejecutiva» não existe no Odoo, nada é lido: ler tudo seria voltar a trazer o GPS.

De cada produto também se lê a **variante** com que o Odoo o fatura; se no Odoo ele tem várias, os pendentes o dizem, porque a fatura não saberia com qual cobrar. E cada preço de hora extra guarda de qual produto saiu: o da hora extra da sua função ou o de todas.

## A pré-fatura no Odoo {#factura}
A única coisa que o Connect escreve no Odoo é a **pré-fatura**: com o aval do consultor —do serviço eventual ou do mês do implantado— sai na hora uma fatura de cliente em rascunho, que o faturista revisa, confirma e emite lá. Ela vai com a sua própria chave —a da fatura, separada da de leitura— e essa conexão só sabe criar o rascunho: não o confirma, não o emite, não o altera depois e não o apaga. A tela de [Odoo](#/odoo) diz se o servidor já tem essa chave; sem ela não sai nenhuma, e a fatura é feita no Odoo e registrada com «Já faturado no Odoo», como antes.
- **O cabeçalho:** o cliente da sua ficha no Odoo, a moeda da cotação —ou dos preços do mês— e a referência: o folio do serviço, «EP/E-031», ou o folio e o mês, «EP/IM-004 · 11/2026». O seu documento de origem começa com «Connect»: com ele o faturista a encontra —o filtro «Prefacturas de Connect»— e com ele o Connect garante que não manda duas.
- **O eventual:** uma linha por dia, equipe e o que se cobra, com o produto do Odoo do seu preço na lista do cliente; a hora extra, com o da sua função; o cancelamento cobrado integral, com a cotação tal qual e a sua nota.
- **O mês do implantado:** uma linha por posto e por unidade, como na proposta, cada uma com o seu produto. O mês que começa ou que é cancelado no meio vai por dia de serviço —a mensalidade dividida pelos dias da sua modalidade—, e o centavo que sobra ao reparti-la vai na última linha. O dia adicional, ao preço do dia das pessoas; a hora extra, com o produto da hora extra da sua função. Se os preços do mês foram escritos à mão, sem detalhamento, vai uma só linha com o produto do posto principal.
- **As despesas,** em uma só linha com **«Gastos de Operación (Viáticos)»**, que entra na tabela de produtos mesmo sem ser da categoria de Proteção Executiva —mudá-lo de categoria no Odoo mudaria a sua conta contábil— e a tabela o marca com «Fatura as despesas». Os impostos o Odoo põe, com o imposto de cada produto.

Se não sai —o Odoo não respondeu, falta um dado, a de antes da devolução continua viva no Odoo— o aval fica, e o serviço ou o mês espera em Faturamento → «Não foi possível enviar» com o motivo; tenta-se de novo sozinho a cada hora, sem duplicar. O que se manda é o que o consultor aprovou: se depois do aval muda um preço da lista ou um dia, não sai. O que teve o aval antes da chave não sai sozinho —pode ter sido faturado à mão—: o financeiro o envia com «Enviar ao Odoo» ou o registra com «Já faturado no Odoo». Se o financeiro devolve um serviço com a pré-fatura já no Odoo, ela fica lá e o faturista a cancela; a nova sai quando ela já estiver cancelada. Por enquanto o financeiro continua aprovando no Connect, e a emitida é registrada com «Já faturado no Odoo».

> Quase tudo o que «não chega do Odoo» é uma de três coisas: a leitura nunca foi aplicada à mão, o dado ficou nos pendentes, ou a chave do Odoo venceu —dura uns três meses— e o Salvador coloca uma nova no servidor.

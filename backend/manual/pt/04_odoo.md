---
id: odoo
parte: entender
orden: 40
titulo: O que vem do Odoo
resumen: As cinco leituras —pessoal de segurança, frota e oficina, escritório, clientes e tabelas de preços—, o que cada uma traz, quando roda e o que deixa pendente. E a fatura do eventual no Odoo, em preparação.
buscar: odoo leitura ensaio aplicar primeira leitura pendentes chave etiqueta protecao executiva local de trabalho email pessoal email de trabalho tabelas de precos produtos lista de implantados desligamento arquivado categoria proteccion ejecutiva PE prefijo gps atlas idioma es_MX fatura pre-fatura rascunho emitir faturista variante variantes gastos de operacion viaticos chave da fatura ODOO_FACTURACION_API_KEY hora extra produto
---
O Odoo é a fonte de verdade. O Centauro **o lê e nunca escreve nele**, e o que vem do Odoo não se edita no Centauro: corrige-se lá e chega sozinho na leitura seguinte. Três regras valem para as cinco leituras:

- **A primeira é feita à mão**, em [Odoo](#/odoo): primeiro o **Ensaio**, que lê e diz o que faria sem salvar nada, e, se estiver certo, **Aplicar**. A partir daí a leitura se faz sozinha a cada hora. Enquanto não se faz a primeira, a de cada hora não começa.
- **O duvidoso não se adivinha.** O que não bate é reportado como pendente e não se toca. O ensaio diz o que falta em cada caso.
- **A chave é o número interno do Odoo.** Na primeira vez, o que já estava no Centauro é reconhecido pelo e-mail, pela placa ou pelo RFC.

## O pessoal de segurança · a cada hora, aos :17
Entra quem tem no Odoo o cargo «Personal de Seguridad» ou «Security Driver». Traz o nome, a cidade —do **local de trabalho**, e o Estado do México conta como Cidade do México—, o celular, o e-mail pessoal, o número de funcionário, a data de admissão, a foto e a conta bancária (número, banco e titular da sua **conta principal**, da ficha do funcionário no Odoo: aqui não se cadastra; se não se pode ler, a leitura diz se falta a permissão ou se essa versão do Odoo não tem o campo, e não mexe em nada). O círculo com iniciais que o Odoo coloca em quem não tem foto não é uma foto: não é salvo. A pessoa entra no app com o seu **e-mail pessoal**.
Se o Odoo a arquiva, ela é desligada: o seu acesso é fechado —a não ser que deva diárias, que primeiro comprova—, e a central recebe um alerta por cada dia que ela tinha designado.

## A frota e a oficina · a cada hora, aos :27
Entram as unidades com a etiqueta «PROTECCION EJECUTIVA» ou «pe». Traz a placa, a categoria —as sete do Odoo são as do Centauro—, a cidade da sua **Ubicación**, a marca, o modelo, a cor e o ano.
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

## A fatura do eventual · em preparação {#factura}
A única coisa que o Connect vai escrever no Odoo é a **pré-fatura do eventual**: ao dar o visto, uma fatura de cliente em rascunho que o faturista revisa, confirma e emite lá. Ela vai com a sua própria chave —a da fatura, separada da de leitura— e essa conexão só sabe criar o rascunho: não o confirma, não o emite, não o altera depois e não o apaga. A tela de [Odoo](#/odoo) diz se o servidor já tem essa chave.
Cada linha sai com o produto do Odoo do seu preço na lista do cliente; a hora extra, com o da sua função; e as despesas, com **«Gastos de Operación (Viáticos)»**, que entra na tabela de produtos mesmo sem ser da categoria de Proteção Executiva —mudá-lo de categoria no Odoo mudaria a sua conta contábil— e a tabela o marca com «Fatura as despesas». **Por enquanto nada é enviado**: a fatura continua sendo feita no Odoo e é anotada com «Já faturado no Odoo».

> Quase tudo o que «não chega do Odoo» é uma de três coisas: a leitura nunca foi aplicada à mão, o dado ficou nos pendentes, ou a chave do Odoo venceu —dura uns três meses— e o Salvador coloca uma nova no servidor.

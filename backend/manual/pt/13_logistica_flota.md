---
id: logistica_flota
parte: entender
orden: 46
titulo: Logística: a frota, os motoristas e a sua jornada
resumen: Cada unidade da Centauro Logistic com sua documentação, seu plano preventivo, seus serviços, seus pneus e seu custo por dia; os motoristas com sua habilitação e seu acesso ao LG Connect; a marcação de jornada no pátio e o bônus de 5 de 5; e a regra que diz quem pode sair.
buscar: logistica lg frota unidade numero economico eco placa tipo rendimento hodometro situacao livre em viagem oficina fora de servico documentacao documento veiculo apolice seguro licenca sct inspecao gps pegasus vencimento plano preventivo servico pneus posicao estepe custo por dia depreciacao manutencao recalcular excel carga inicial motorista habilitacao tempo de casa lg connect applg codigo digital jornada patio geocerca marcacao validar rejeitar central bonus mobilidade 5 de 5 disponibilidade
---
O bloco 2 da Logística traz suas unidades e seus motoristas para o Connect. As telas são duas, em **Operações LG**: [Frota LG](#/lg/flota) e [Jornada LG](#/lg/jornada). Os motoristas têm seu próprio app, o **LG Connect**, em applg.mycentauro.lat: não é o da Proteção Executiva e ninguém de um lado vê nada do outro.

## De onde vêm as unidades e os motoristas {#odoo}
Do Odoo, da empresa **Centauro Logistic SA CV**. De cada unidade o Odoo manda a placa, o modelo, o ano, o chassi e o IAVE; os dois baús secos entram, mas não são atribuídos sozinhos: vão com seu cavalo; o utilitário não entra. De cada funcionário com cargo «Operador», seu nome, seu e-mail pessoal, seu telefone e sua data de admissão; seus dados bancários ficam no Odoo. A primeira leitura é feita à mão, com seu ensaio —Frota LG → Carga inicial para as unidades, Jornada LG → Motoristas para os motoristas— e depois são lidos sozinhos a cada hora. O que é do Connect não é pisado: o número econômico, o tipo, o hodômetro, a documentação e a habilitação. O que o Odoo deixa de mandar é baixado, e o motorista baixado perde o LG Connect. Uma leitura que traz zero com registros ativos para sem baixar nada.

## A unidade {#unidad}
- **O número econômico não se repete**: «Eco 01», «01» e «1» são o mesmo, e a segunda unidade que pedir é rejeitada dizendo de quem é.
- **A situação**: livre, em viagem, na oficina ou fora de serviço. Oficina e fora de serviço pedem motivo e ficam no registro. «Em viagem» é marcado à mão enquanto as viagens seguirem no Tango; a gerência também marca, mas uma unidade na oficina só é liberada por quem cuida da frota.
- **O hodômetro** é registrado à mão; uma leitura menor que a anterior pede o porquê. A partir do bloco 6 se preencherá com as fotos de saída e volta de cada viagem.
- **A documentação**: documento do veículo, apólice de seguro, licença SCT, inspeção mecânica e GPS Pegasus, cada um com seu vencimento e seu arquivo. A 30 dias do vencimento chega um aviso a quem cuida da frota —se ainda ninguém cuida, à gerência—, e outro no dia em que vence. Um novo substitui o anterior, que fica guardado.
- **No alto de cada unidade** se diz se pode sair, o que a trava e seus alertas, e **o que há a resolver** mesmo que hoje não trave: o documento que vence nos próximos 30 dias e o serviço a menos de 2.000 km.

## O plano preventivo e os serviços {#plan}
O plano é de cada **tipo de unidade** e dos baús: qual serviço, a cada quantos km e quanto custa mais ou menos. Cada unidade sabe em que km vence com **seu último serviço registrado**; sem ele não se adivinha, se pede. Ao registrar um serviço do plano —com seu hodômetro, seu custo, sua oficina e sua nota— o plano avança sozinho; um corretivo («Outro») não move o plano mas conta para o custo. O que for registrado errado é anulado com seu motivo. Os **pneus** vão por posição —4, 6 ou 10 segundo o tipo, mais o estepe; os baús, dois eixos de quatro— e dizem quantos km têm desde a instalação; a 90% da vida de referência do seu tipo dizem «trocar logo».

## O custo por dia {#costo}
Quanto custa ter a unidade por um dia, sem o diesel nem o motorista; a margem de cada viagem o usará. Cinco partes, cada uma anual dividida por 365 e em centavos: **depreciação** (compra dividida pelos anos de vida útil), **seguro**, **imposto, inspeção e GPS**, **manutenção** e **pneus** (o que gastam por km pelos km que a unidade roda por dia). A manutenção sai dos serviços registrados nos últimos 12 meses —no Odoo não há notas de oficina da Logistic—; enquanto a unidade não tiver um ano de serviços, da manutenção anual do Excel; sem nada da unidade, da média do seu tipo. **O que faltar à unidade é tomado do custo do seu tipo** em Catálogos LG. É salvo no dia 1 de cada mês e o anterior é mantido: uma viagem fechada fica com o custo com que foi calculada. Se o do dia 1 ficou pela metade —seu tipo ainda não tinha custo, ou faltavam seus km por dia—, é completado sozinho a partir do dia em que há com quê; uma unidade sem nada com que calcular não leva um custo zero. No meio do mês é recalculado à mão, com o porquê. Os pneus precisam dos km por dia da unidade: duas leituras do hodômetro com um mês de distância; os baús secos, que não têm hodômetro, os terão com suas viagens no Connect.

## A carga inicial do Excel {#excel}
«Costos_unidades_Centauro_Logistica.xlsx», com suas planilhas **Unidades** e **Plan preventivo**, depois de ler as unidades do Odoo. As colunas são reconhecidas pelo nome, em qualquer ordem. **Tudo ou nada**: se uma única linha tiver erro nada é carregado, e cada erro diz sua planilha, sua linha, sua coluna e o que acontece —uma placa que não existe sugere a parecida—. Pode ser enviado quantas vezes for preciso; depois, cada mudança é registrada na unidade.

## Os motoristas e o LG Connect {#operadores}
Em Jornada LG → Motoristas: o tempo de casa —da data de admissão, para o bônus—, a **habilitação federal** com seu vencimento e seu arquivo, e o acesso. Entram no LG Connect com o e-mail pessoal. Na primeira vez, ou se esquecerem a senha, a gerência ou quem cuida da frota gera **um código de quatro dígitos** e dita por telefone: vale dez minutos e uma única vez. Depois podem entrar com digital ou rosto. Mudar a senha encerra as sessões e as digitais anteriores.

## A jornada no pátio {#jornada}
Cada motorista marca o início da jornada no LG Connect **dentro da geocerca do pátio** (300 m na Base Cuautitlán), tenha viagem ou não. Fora dela pode marcar dizendo onde está: a marcação fica **a validar** e a **Central** valida ou rejeita com sua justificativa, em Jornada LG → A validar; o monitorista não valida, como não corrige marcos. Validada, conta como presente; rejeitada, o dia fica como ausente. A aba Hoje diz quem está presente, em viagem, a validar ou ausente, e se pode sair.

## O bônus de 5 de 5 {#bono}
A semana de segunda a sexta: conta o dia com marcação válida no pátio e o dia em que amanheceu **em viagem** —na estrada não dá para marcar no pátio—. Cinco de cinco ganham o bônus de mobilidade; com uma marcação a validar, depende da Central. A folha do bloco 8 pegará daqui os dias.

## Quem pode sair {#disponibilidad}
Uma única regra para a unidade e outra para o motorista, a mesma que verá quem atribuir as viagens. **Não sai** a unidade na oficina ou fora de serviço, em viagem, ocupada em outra viagem, com um documento **vencido** ou com um serviço preventivo vencido; nem o motorista sem marcação de jornada de hoje (ou com ela a validar ou rejeitada), em viagem ou com a habilitação vencida. **Sai com alerta** se um documento ou a habilitação não foram registrados —decisão do Salvador: só trava o registrado e vencido—, se algo vence durante a viagem, se a habilitação vence em menos de 30 dias ou se um serviço cai dentro dos km da viagem.

## Quem faz o quê {#quien}
- **Quem cuida da frota** (cargo «Responsable de flota LG»): unidades, situação, hodômetro, documentação, serviços, pneus, plano preventivo, a carga do Excel e a leitura do Odoo.
- **A gerência de Logística**: vê tudo, gera o código do LG Connect, registra a habilitação e marca à mão o «em viagem».
- **A Central**: vê a jornada e valida ou rejeita as marcações fora do pátio.
- **Sistema e qualidade**: vê a frota e a jornada. Toda mudança fica no registro de cada tela e no de administração.

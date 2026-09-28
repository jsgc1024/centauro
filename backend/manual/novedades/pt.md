# Novidades

O que há de novo em cada atualização, escrito para quem usa o sistema. A mais nova fica em cima.

## 96 · 2026-09-28 · Já faturado no Odoo
Em Faturamento → A faturar, cada serviço traz **«Já faturado no Odoo»**: enquanto a fatura não está conectada com o Odoo, o financeiro a faz lá e aqui registra o número e a data. O serviço sai da lista, o número aparece em Faturamento e no Histórico —com quem o registrou— e fica no registro; o aprovado fica faturado, e quando a conexão chegar não é reenviado. Um número é de uma só fatura. A registrada à mão se corrige em Fechados do mês ou ao revisar o serviço; a que vem do Odoo, no Odoo. Além disso: as caixas de busca já não mudam o que se escreve ao sair delas, e um «não se pode» já não repete o que fazer e o coloca na sua própria linha.

## 95 · 2026-09-28 · Corrigir os contatos do serviço
No serviço, em cima junto ao status, **Corrigir os contatos**: o nome, o e-mail, o telefone e o idioma de quem solicita e do executivo principal —e os dados do executivo principal de uma equipe que leva o seu— se corrigem depois do cadastro, enquanto o serviço não estiver fechado nem cancelado. Quem corrige é o consultor do serviço ou quem o cobre. O que muda fica marcado com o anterior embaixo; quem solicita pode ser trocado por outro da lista do cliente e corrigido também nessa lista. Os avisos que ainda não saíram e a pesquisa sem resposta vão para os dados novos, o task sheet que for baixado já os traz, e fica no registro do serviço com o que havia antes. Se o e-mail anterior estiver em outro serviço aberto do cliente, diz-se em qual. Além disso, em Unidades, a leitura do GPS diz o que de fato acontece: a cada 2 minutos com serviços na rua, e a cada 15 sem ninguém na rua; e a cotação de um cliente sem tabela de preços diz onde ela é colocada: Gestão Administrativa → Odoo, em «Clientes sem tabela de preços».

## 94 · 2026-09-28 · A cotação autorizada, no serviço
Enquanto o Odoo não envia a cotação, o consultor do serviço —ou quem o cobre— a registra no eventual, abaixo do cabeçalho, em **A cotação autorizada**: o que leva cada dia, como se cobram as despesas —dentro do preço, a valor fixo ou por comprovar— e quem autorizou do lado do cliente, o dia e o número do Odoo se existir. Os preços saem da tabela do cliente, igual ao fechamento, com o pacote se a lista o pactua, e «Usar o que está atribuído» a preenche com quem já vai. É salva já autorizada; se o cliente mudar algo antes do visto bom, recota-se com o motivo. Com ela o visto bom já tem contra o que comparar.

## 93 · 2026-09-27 · O e-mail sai pela Amazon
O Postmark não aceitou o domínio mycentauro.lat: os e-mails do sistema saem pelo Amazon SES, do mesmo connect@mycentauro.lat, e as respostas continuam chegando em cecc.notification@centauro.lat. Primeiro se testa com o e-mail desligado; ele é ligado quando a Amazon aprovar a conta.

## 92 · 2026-09-27 · Reportar uma falha
Em cima, ao lado do seu nome, em todas as telas do console, e em **Eu** no app de campo: escreve-se o que aconteceu e, se quiser, cola-se uma captura ou adiciona-se uma foto; o resto —a tela, o serviço, a versão e o último que apareceu em vermelho— vai sozinho, e nunca senhas. Chega a sistema e qualidade em [Manual do sistema → Casos](#/manual/casos), em **Para revisar**, com o aviso por e-mail. Ali se resolve ou se copia para o Claude; já resolvido, quem reportou recebe o aviso com a causa e como se resolveu.

## 91 · 2026-09-27 · O e-mail sai pelo Postmark, e quatro correções
O MailerSend não aprovou a conta: os e-mails do sistema saem pelo Postmark, do mesmo connect@mycentauro.lat, e as respostas continuam chegando em cecc.notification@centauro.lat. Além disso: os avisos do dia e da substituição chegam ao principal de cada equipe, como a task sheet; o cabeçalho do serviço mostra o status, o tipo e a situação de cada dia com o seu nome, no idioma de quem vê; no app, «Minha avaliação» mostra o nome de cada parte; e aprovar um serviço de um país sem percentual de comissão avisa antes, sem salvar nada.

## 90 · 2026-09-27 · O manual do sistema
O manual vive no console, em Gestão Administrativa → Manual do sistema, em espanhol e em português. Explica como funciona cada peça, o que fazer quando algo trava e por que aconteceu. Traz o estado do sistema ao vivo, o que o sistema faz sozinho com a sua última volta, cada mensagem de «não é possível» com o que fazer, quem pode o quê, estas novidades e os casos resolvidos. É salvo em PDF com um botão e se atualiza a cada atualização do sistema.

## 89 · 2026-09-27 · Qualidade: o mês em números
Tela nova em Operações EP: como foi o serviço no mês —o que o cliente disse, a rua, o fechamento, as pessoas e os dados que faltam no Odoo e em Catálogos—, cada número contra o mês anterior e com o seu relatório em Excel. Veem sistema e qualidade, a direção de operações e a direção geral.

## 88 · 2026-09-27 · A chave mestra conta a direção geral
A trava que não deixa o sistema sem chave mestra agora conta também a direção geral, não só a administração. Assim se destravou o cargo da Aridiai, que por engano era a única com administração.

## 87 · 2026-09-27 · Só um consultor leva um serviço
No cadastro do eventual e do implantado, «Consultor responsável» só oferece consultores com acesso aberto. O consultor que cadastra se propõe a si mesmo; quem não é consultor escolhe, e o servidor não cadastra um serviço em nome de quem não é consultor.

## 86 · 2026-09-27 · Catálogos e o registro da administração
Tela nova em Gestão Administrativa. Os catálogos que o sistema usa —feriados, hospitais, hotéis, cidades, combustível, unidades por categoria, perfis e países— são cuidados por sistema e qualidade; os que decidem dinheiro —a tabela de diárias, as horas de cada modalidade e as tarifas de freelance— são definidos pela direção de operações. Cada mudança fica no registro: quem, quando, antes e depois.

## 85 · 2026-09-27 · O cargo de administração do sistema e qualidade
Um papel novo, sistema e qualidade, com o seu cargo: dá acessos junto com os Recursos Humanos, lê e aplica o Odoo, mantém os catálogos que não decidem dinheiro e consulta a operação. Não mexe em dinheiro, não opera e não classifica. Só a direção geral o dá.

## 84 · 2026-09-27 · O e-mail sai de mycentauro.lat
Os e-mails do sistema saem de connect@mycentauro.lat pelo MailerSend, e as respostas chegam em cecc.notification@centauro.lat. Primeiro se testa com o e-mail desligado; liga-se quando o MailerSend aprova a conta.

## 83 · 2026-09-27 · As travas de Acessos
Ninguém dá acessos a si mesmo nem muda o próprio cargo; o poder de distribuir acessos só é dado pela direção geral; as duas mãos do dinheiro não se juntam numa pessoa nem num cargo; e a quem está desligado não se abre um acesso.

## 82 · 2026-09-26 · Dólares na cotação
O cliente que paga em dólares é cotado, fechado e faturado em dólares. A taxa de câmbio é definida à mão pelo financeiro, em Faturamento → Tabelas de preços, e vale até que alguém a mude; cada cotação fica com a que estava definida ao ser autorizada. A comissão é paga em pesos, por essa taxa. Vale também para os implantados.

## 81 · 2026-09-26 · O ícone do EP Connect
O app de campo estreia ícone: o escudo branco com o C, sobre azul-marinho e com moldura dourada. O nome continua sendo EP Connect.

## 80 · 2026-09-26 · Os preços do implantado, da sua lista
Ao abrir o mês, os termos do implantado pegam os preços da lista de implantados do cliente no Odoo, com a equipe do mês: cada pessoa pelo preço da sua função, o motorista com a sua unidade em pacote se a lista o combina, e a hora extra. Se o mês leva outros preços, o sistema avisa.

## 79 · 2026-09-26 · Os pacotes motorista + unidade
Quando a equipe leva essa função com essa unidade e a lista do cliente combina o pacote, cobra-se o pacote: uma só linha com o seu preço, na cotação, no fechamento e na fatura. O financeiro marca, lista por lista, se os seus pacotes trazem as diárias do dia.

## 78 · 2026-09-26 · O cliente se escolhe buscando
No serviço novo, o cliente é buscado escrevendo um pedaço do nome, e ao escolhê-lo o seu país é proposto. Também em Faturamento → Tabelas de preços.

## 77 · 2026-09-26 · As tabelas de preços, do Odoo
Uma quinta leitura do Odoo: as tabelas de preços —a lista geral de cada país e a do cliente que negociou a sua—, a cada hora, aos :57. O preço sai como o Odoo o calcula, e só põe preço o que o financeiro confirmou na tabela de produtos.

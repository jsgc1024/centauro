---
id: sintoma-no-cotiza
parte: resolver
orden: 510
area: Dinheiro
titulo: Um cliente não tem preço: sem tabela de preços, «sem preço» ou sem taxa de câmbio
buscar: cotar cotacao preco sem preco tabela de precos lista de precos cliente sem tabela funcao unidade pacote modalidade produto confirmar taxa de cambio dolares
---
### O que você vê
Uma destas: o cliente **não tem tabela de preços**; na sua tabela, uma função, uma unidade ou um pacote diz **«sem preço»**; o fechamento para com «El tarifario no tiene precio para … en …»; ou uma cotação em dólares não é autorizada porque **não há taxa de câmbio**.

### Por que acontece · do mais comum ao menos comum
1. **O cliente chegou do Odoo sem tabela de preços.** Ele a pega da sua lista do Odoo na leitura das tabelas; enquanto isso não estiver em funcionamento, ela é colocada à mão.
2. **A sua lista não tem esse preço.** Cobra-se a função com que cada um foi naquele dia, a categoria da unidade e a modalidade daquele dia. Se a lista do cliente não o combina, nem o pega da geral do seu país ou do «Preço de venda» do produto, fica «sem preço».
3. **O produto não está confirmado.** Só põe preço o que o financeiro já confirmou na tabela de produtos: o sugerido não conta, porque um preço mal lido é cobrado.
4. **Alguém vai sem função.** Sem função não há preço a procurar: o sistema pede para dizer com que função a pessoa vai.
5. **O cliente paga em dólares e não há taxa de câmbio.** Sem ela não se autoriza a cotação nem se faturam as despesas. Hoje só se converte de dólares para pesos mexicanos.
6. **A lista do Odoo não tem preços que o Centauro saiba ler.** O cliente não é trocado: fica com a tabela que tinha e aparece nos pendentes.

### Como confirmar
Abaixo do cabeçalho de cada serviço, quem cota e fecha vê **a tabela do cliente**, cada preço com a sua origem: em preto o que a sua lista combina; em cinza o que vem da geral, de outra lista ou do «Preço de venda»; e «sem preço» o que não se pode cobrar. É a mesma que está em Faturamento → Tabelas de preços.

### Como se resolve
- **Sem tabela de preços:** em [Odoo](#/odoo), em «Clientes sem tabela de preços», escolhe-se a tabela e coloca-se, um por um ou em todos os de um país de uma vez.
- **Sem preço:** corrige-se no Odoo, na sua lista de preços, e chega na leitura das tabelas, aos :57.
- **Produto sem confirmar:** o financeiro o confirma em Faturamento → Tabelas de preços, na tabela de produtos.
- **Sem função:** o consultor diz com que função essa pessoa vai.
- **Sem taxa de câmbio:** o financeiro a define em Faturamento → Tabelas de preços. Vale para tudo o que vier; o que já ficou fixo não muda.

> **A causa raiz:** o Centauro não inventa preços. Tudo o que cobra sai da lista do cliente no Odoo, lida a cada hora, e o que não está ali não pode ser cobrado.

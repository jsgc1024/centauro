---
id: sintoma-cierre-no-sale
parte: resolver
orden: 520
area: Dinheiro
titulo: O aval não sai e o serviço não chega ao faturamento
buscar: fechamento aval nao sai mandar faturar financeiro pontos para corrigir cotacao autorizada jornada sem termino diarias sem fechar taxa de cambio desvio devolvido prazo vencido fatura a faturar
---
### O que você vê
No cartão **Aval e faturamento** do serviço, «Antes de enviar» diz que há pontos para corrigir; ou o botão **Dar o aval e mandar faturar** não aparece.

### Por que acontece
**Ainda corre a comprovação.** Durante as 24 horas do pessoal, o aval não abre. Abre ao vencer esse prazo, ou antes, se todos já fecharam as suas diárias.

**Quem está vendo não dá o aval.** Quem o dá é o consultor titular ou a direção de operações; um cargo que só cota deixa tudo pronto.

**Há pontos para corrigir.** São os únicos que travam; o que aparece em «Para revisar» não trava. Os pontos vêm do servidor e aparecem em espanhol:
- **Viáticos sin cerrar.** Falta revisar comprovantes de alguém, há um depósito autorizado sem depositar ou uma devolução que o financeiro não confirma, ou já bate e falta fechar.
- **Jornada sin término.** Um dia sem a sua marcação de fim.
- **Um desvio contra o orçado.** Dias a mais ou a menos, um recurso que não foi orçado, diárias excedidas, uma cobrança menor.
- **Sin tipo de cambio.** As despesas foram comprovadas em pesos e são faturadas em dólares.
- **Sem cotação autorizada.** Sem ela não há contra o que comparar o executado.

### Como se resolve
Cada ponto diz a sua ação:
- As diárias se fecham mais abaixo, em Adiantamentos da equipe. Se o prazo já venceu, o que não foi comprovado é fechado com desconto na folha.
- O dia sem fim é registrado pela central, com a sua justificativa.
- O desvio é recotado com o cliente —«Recotar», em A cotação autorizada— ou justificado.
- A taxa de câmbio é definida pelo financeiro em Faturamento → Tabelas de preços.
- A cotação autorizada é registrada pelo consultor do serviço, ou por quem o cobre, no alto do mesmo serviço: em **A cotação autorizada**.

### E depois do aval
- **O financeiro o devolve** com o seu motivo: há 24 horas desde a devolução para corrigir e mandar de novo. O «no prazo» do primeiro aval fica como estava.
- **A fatura não sai.** O aval já ficou: o serviço espera em Faturamento → A faturar, com o que aconteceu, e o financeiro o aprova do mesmo jeito. Enquanto a fatura para o Odoo não estiver conectada, tudo o que é aprovado espera ali.
- **O prazo passou.** Não trava: o serviço é faturado do mesmo jeito, mas a comissão desse serviço se perde.

> **A causa raiz:** o aval é a porta do dinheiro: o que passa por ela é faturado e pago. Por isso não deixa passar nada que ainda se mexe —uma diária aberta, um dia sem fim, um preço sem respaldo—.

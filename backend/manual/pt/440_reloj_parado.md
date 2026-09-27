---
id: sintoma-reloj-parado
parte: resolver
orden: 440
area: Operação
titulo: Várias coisas deixaram de acontecer sozinhas ao mesmo tempo
buscar: relogio parado worker beat redis nada acontece sozinho emails nao saem fechamentos nao avancam odoo nao le gps nao le
---
### O que você vê
Ao mesmo tempo: os e-mails não saem embora o e-mail esteja ligado, os fechamentos não avançam, o Odoo não é lido, o GPS ficou parado, a véspera não chegou. O console abre.

### Por que acontece
**O relógio está parado.** As vinte tarefas que rodam sozinhas dependem de dois processos do servidor —o que marca a hora e o que faz o trabalho— e do Redis. Se um cai, o console continua abrindo, mas nada acontece sozinho.

### Como confirmar
O [estado do sistema](#/manual/atorado) diz **Parado** e quando foi a última volta. Em [o que o sistema faz sozinho](#/manual/reloj) se vê a última volta de cada tarefa.

### Como se resolve
Avisa-se o Salvador: ele revisa os processos do servidor e levanta o relógio de novo. Está no guia de implantação, em «Qué mirar cuando algo falle».

> **A causa raiz:** quando muitas coisas falham juntas, a causa quase nunca é cada uma: é o que elas têm em comum.

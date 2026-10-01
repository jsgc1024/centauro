---
id: sintoma-odoo-no-llega
parte: resolver
orden: 310
area: Odoo
titulo: Algo que foi corrigido no Odoo não chega ao Centauro
buscar: odoo nao chega nao atualiza correcao leitura pendente chave venceu nao responde etiqueta cliente primeira leitura
---
### O que você vê
Os Recursos Humanos, a Frota ou o financeiro já corrigiram algo no Odoo, e no Centauro continua igual.

### Por que acontece · do mais comum ao menos comum
1. **Ainda não é a hora da leitura.** Cada uma roda uma vez por hora, no seu minuto: o pessoal aos :17, a frota aos :27, o escritório aos :37, os clientes aos :47 e as tabelas de preços aos :57.
2. **Essa leitura nunca foi aplicada à mão.** A de cada hora espera que alguém faça a primeira, depois de ver o ensaio. No [relógio](#/manual/reloj) aparece «Espera a primeira leitura à mão».
3. **O caso ficou nos pendentes.** O duvidoso não se adivinha: se falta algo —uma cidade, um e-mail, uma placa— é reportado e não se toca.
4. **É um cliente sem a etiqueta «Protección ejecutiva».** Sem ela, o Centauro já não lê as suas mudanças.
5. **A chave do Odoo venceu**, ou o servidor não a tem. Dura uns três meses. O [estado do sistema](#/manual/atorado) avisa, e o relógio a marca com erro.

### Como confirmar
Em [Odoo](#/odoo), o **Ensaio** dessa leitura: lê o Odoo naquele momento, diz o que mudaria e o que fica pendente, e não salva nada.

### Como se resolve
- Se só falta chegar a hora: esperar o seu minuto, ou fazer o ensaio e aplicar.
- Se ficou pendente: corrigir no Odoo o que o ensaio diz.
- Se a chave venceu: o Salvador coloca uma nova no servidor.

> **A causa raiz:** o Centauro só lê do Odoo —a única coisa que escreve é a pré-fatura em rascunho— e nunca adivinha. O que não chega, ou ainda não teve a sua vez, ou o Odoo o tem incompleto.

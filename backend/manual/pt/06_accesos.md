---
id: accesos
parte: entender
orden: 60
titulo: Acessos, papéis e cargos
resumen: Quem entra, com o quê, e o que pode fazer. As travas que cuidam dos acessos, o convite, a recuperação de senha, o código do pessoal de campo e a entrada com digital ou rosto.
buscar: acesso papel cargo categoria chave mestra administracao direcao geral permissao avulsa atividades telas convite link copiar reenviar senha recuperar codigo quatro digitos sessao desligamento digital rosto touch id pin chave de acesso
---
## Papel e cargo
Há nove papéis: pessoal de segurança, central, consultor, direção de operações, direção geral, finanças, recursos humanos, sistema e qualidade, e administração —a **chave mestra**—.

O **cargo** manda sobre o papel: diz com que papel entra quem o tem, que telas aparecem no seu menu e o que pode fazer nelas. Sem cargo, cada um entra com o que o seu papel dá. A direção geral e a administração entram com o seu papel, sem cargo.

Quando o sistema decide se alguém pode fazer algo, pergunta nesta ordem:
1. **A administração sempre passa**: senão, um erro de configuração deixaria a empresa sem poder corrigi-la.
2. **Uma permissão avulsa** que deram a essa pessoa. Só dá, nunca tira.
3. **O seu cargo**, se tiver.
4. **O seu papel**, se não tiver cargo. A direção geral alcança também tudo o de operações, consultor, central, finanças, recursos humanos e administração.

Quando alguém não pode, a mensagem diz quem pode: com cargo, que cargos o trazem; sem cargo, que papéis. A lista completa está em [quem pode o quê](#/manual/permisos).

## As travas de Acessos
Dão e fecham acessos a administração, a direção geral, os recursos humanos e sistema e qualidade, em [Acessos](#/accesos). E há coisas que o sistema não deixa fazer, de propósito:
- **Ninguém dá acessos a si mesmo** nem muda o próprio cargo: pede a outra pessoa. O próprio cargo é mudado pela direção geral, e fica no registro.
- **O poder de distribuir acessos só é dado pela direção geral.**
- **As duas mãos**: o que pede ou aprova o dinheiro não convive com o que o paga (ver [o dinheiro](#/manual/leer/dinero)).
- **A chave mestra não fica sem dono**: não pode ser tirada da última pessoa ativa que a tem, contando a direção geral.
- **O acesso não é a porta dos fundos de um desligamento**: a quem está desligado não se abre um acesso; se voltou, primeiro é reativado como funcionário.
- **A quem sai devendo diárias não se fecha o acesso** até que comprove; se não vai voltar, o financeiro o fecha com o seu ajuste.
- **Ao consultor titular de serviços vivos não se fecha o acesso**: o sistema diz quantos e quais; a direção de operações os troca antes em cada ficha com «Trocar titular».

## Como cada um entra
- **O escritório** recebe um **convite por e-mail** para criar a sua senha. O link vale **72 horas** e serve uma única vez. Reenviar manda um novo e desliga o anterior. Se o e-mail não chegar, a direção geral ou a administração podem **copiar o link** e entregá-lo em mãos; fica registrado quem o copiou.
- **Quem esqueceu a senha** a recupera na entrada, com «Esqueceu sua senha?». Esse link vale **2 horas**. As duas coisas precisam do e-mail ligado.
- **O pessoal de segurança** não recebe convite: define a senha com um **código de quatro dígitos** que o seu consultor dita —só a quem trabalha nos seus serviços— ou a central, na tela Código. O código vale **10 minutos**. O que protege esse caminho é que quem o dita reconheça a voz de quem liga.
- **A sessão** dura 12 horas, a não ser que o cargo diga outra coisa. Se expira no meio de uma tela, ao entrar de novo volta-se a essa tela.
- **Mudar a própria senha** se faz por dentro, no menu do nome: pede a atual e, ao salvar a nova, todas as sessões são encerradas, inclusive essa, e as digitais são removidas.
- **Com digital ou rosto** (seção 110): num celular ou computador com digital, rosto ou PIN, ao entrar com a senha isso é oferecido uma única vez —«Sim, ativar» ou «Agora não», que não pergunta de novo por um mês—. Depois a entrada cumprimenta pelo nome e basta um botão; «Usar minha senha» e «Não sou…» ficam a um clique. Vale no console e no app, ativa-se digitando a senha, e se vê e se remove no menu do nome → «Entrar com digital ou rosto» (no app, em «Eu»). A digital não sai do celular: o sistema guarda só uma chave que o celular cria para o Connect. A senha continua valendo sempre; trocá-la remove as digitais de todos os aparelhos, que se ativam de novo ao entrar com a nova.

> Quase todo travamento de acessos é uma dessas travas fazendo o seu trabalho. A mensagem diz qual e o que fazer; se não estiver clara, está em [quando o sistema diz não](#/manual/mensajes), em Acessos e senhas.

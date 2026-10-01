---
id: sintoma-unidad-ocupada
parte: resolver
orden: 120
area: Pessoas e unidades
titulo: Uma unidade aparece ocupada ou não aparece
buscar: unidade veiculo caminhonete ocupada nao aparece oficina servico preventivo corretivo categoria placa brasil empresa sem cidade outro pais
---
### O que você vê
Ao designar a unidade de uma equipe, a que você procura não aparece, ou aparece **Ocupado** com um motivo.

### Por que acontece · do mais comum ao menos comum
1. **Está na oficina.** O motivo diz, em espanhol, «En el taller desde el …». Sai de Flotilla → Servicios no Odoo: as entradas do tipo Preventivo, Correctivo ou Desgaste natural tiram a unidade de circulação da data de entrada até a de saída, e **sem data de saída considera-se que ela está lá dentro**.
2. **Nesse dia já vai em outro serviço** no mesmo horário ou num dia inteiro.
3. **Não aparece na lista:** é de outra categoria que a procurada, foi baixada, é da frota de outro país, ou ainda não chegou do Odoo —falta a etiqueta do seu país («PROTECCION EJECUTIVA» ou «pe» no México, «PROTECCION EJECUTIVA BRASIL» no Brasil) com a empresa desse país, a placa, a categoria ou, no México, a sua Ubicación—.
4. **É de outra cidade:** aparece com deslocamento. A do Brasil que ainda não tem Ubicación aparece **sem cidade**, e não vai para um implantado até tê-la.

### Como se resolve
Se já saiu da oficina, a Frota coloca a **data de saída** no serviço dela no Odoo, e a unidade volta a ser oferecida na leitura seguinte da frota, aos :27. O que faltar na ficha, igual, no Odoo.

> **A causa raiz:** um serviço de oficina sem data de saída deixa a unidade lá dentro para sempre. É o esquecimento mais comum.

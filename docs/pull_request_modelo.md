# feat: MVP Mãos Solidárias Digital (famílias, estoque e entregas)

> Modelo de descrição do Pull Request. Preencha os campos marcados com `[ ]` e `___` com o que realmente aconteceu antes de abrir o PR.

## O que muda
Implementa o MVP descrito no planejamento (arquitetura em camadas, estilo MVT):
- Cadastro de famílias (com aviso de possível duplicidade e inativação em vez de exclusão).
- Estoque em lotes com validade, saída pelo lote que vence primeiro e descarte de vencidos.
- Registro de entrega com **bloqueio automático de segunda cesta no mesmo mês** (regra no serviço e restrição única no banco).
- Alertas de validade (até 15 dias), itens vencidos e estoque abaixo do mínimo.
- Relatório mensal (só presidente), com exportação em CSV.
- Login com perfis (presidente e voluntário), bloqueio após 5 tentativas e sessão de 30 minutos.

## Por que
Atende aos requisitos RF01 a RF05 e RNF01 a RNF04: o controle manual permitia cesta repetida e estoque desatualizado.

## Auto-revisão técnica
- [ ] As regras de negócio estão só em `core/services.py` (views só validam formato e chamam os serviços).
- [ ] Entrega e baixa de estoque acontecem na mesma transação (`transaction.atomic`).
- [ ] Nenhum segredo no código (chave, senhas e banco vêm de variáveis de ambiente).
- [ ] Textos digitados são escapados na saída e entradas com `<` ou `>` são recusadas no servidor.
- [ ] Perfis são verificados no servidor (presidente recebe 403 nas funções restritas).
- [ ] Telas sem scripts ou estilos inline (compatível com a CSP).
- [ ] `.gitignore` impede subir banco local, `.venv` e `.env`.

## Riscos e limitações conhecidas
- O bloqueio de login usa cache em memória; com vários processos é preciso um cache compartilhado.
- A janela do alerta de validade é configurada por variável de ambiente, não por tela.
- Agendamento de retirada e cadastro de doadores estão fora do escopo do MVP.

## Como testar
```bash
pip install -r requirements.txt
export DJANGO_DEBUG=1
python manage.py migrate
pytest
python manage.py check --deploy
```
Resultado do `pytest` na minha máquina: ___ testes, ___ passaram, ___ falharam.

## Evidências
- Execução do `pytest`: ___ (captura ou link)
- Pipeline de CI: ___ (link da execução)

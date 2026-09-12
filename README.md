# Testes Supleno — família de experiências

Site estático em HTML, CSS e JavaScript da família **Testes Supleno**. O Supleno Tipos, o Supleno Estilos e o Supleno Traços estão disponíveis como experiências educativas.

O Supleno Tipos possui 28 perguntas, 16 tipos e páginas de resultado com variação de título no masculino e feminino. O Supleno Estilos possui 24 perguntas de escolha forçada, quatro dimensões comportamentais e quatro resultados educativos.

## Identidade do produto

- **Portal:** `https://testes.supleno.com`
- **Teste:** `https://testes.supleno.com/tipos`
- **Marca:** Supleno
- **Objetivo:** aquisição, reaquecimento e segmentação de leads do Supleno

Este projeto pertence exclusivamente ao Supleno. Não misturar domínios, textos, bases ou automações de outros projetos.

## Rotas e estrutura

- `/` (`index.html`) — portal da família, com Supleno Tipos, Supleno Estilos, Supleno Traços e o futuro Mapa Integrado
- `/tipos/` (`tipos/index.html`) — introdução, 28 perguntas, captura e resultado resumido
- `/tipos/resultados/{tipo}-{m|f}.html` — 32 páginas de resultado
- `/estilos/` — teste educativo de 24 perguntas, com resultado básico imediato e captura opcional posterior
- `/tracos/` — teste educativo de 25 afirmações, cinco dimensões contínuas, resultado imediato e captura opcional posterior
- `assets/style.css` — estilo compartilhado
- `assets/nav.js` — comportamento do menu responsivo compartilhado
- `assets/personagens/` — imagens dos personagens
- `apps-script/Code.gs` — referência de backend do Supleno Tipos; Supleno Estilos e Supleno Traços exigem endpoints próprios, com validação de seus contratos, antes de produção
- `PROMPTS-IMAGENS.md` — prompts para criar as ilustrações

## Configuração necessária antes da produção

1. Definir e implantar os backends de captura de cada produto do Supleno. Não apontar o Supleno Estilos para o endpoint do Supleno Tipos: os códigos e o contrato são diferentes.
2. Informar a URL publicada em `WEBHOOK_URL` no `config.js` local (a partir de `config.example.js`). Para o Supleno Estilos, use `estilos/config.example.js` e `estilos/config.js`.
3. Confirmar `CTA_URL` e `SITE_BASE_URL` no frontend e no backend.
4. Criar as imagens e substituir todos os espaços reservados.
5. Configurar origem, UTM, consentimento e métricas.
6. Executar `python3 scripts/validate-content.py`.
7. Homologar o fluxo completo com dados sintéticos.

### Métricas do funil

`assets/funil-analytics.js` é o adaptador compartilhado dos três testes. Ele
registra localmente, sem rede, os eventos `funil_inicio`, `funil_progresso`,
`funil_conclusao`, `funil_resultado`, `funil_captura` e `funil_cta`. Os payloads
contêm somente o produto, a etapa, a quantidade de perguntas e códigos/faixas
do resultado; nunca incluem nome, e-mail, WhatsApp ou respostas individuais.

Por padrão, as métricas permanecem desligadas. Só há envio para GA4 ou Meta
Pixel quando `ANALYTICS.ENABLED` for explicitamente `true`, um ID correspondente
estiver confirmado no `config.js` local e o navegador não tiver ativado “Não
rastrear”. O evento de captura exige também o checkbox de consentimento. IDs
reais não devem ser commitados nem preenchidos neste repositório.

Para homologar sem gasto, consulte `window.SuplenoFunil._getEventLog()` no
console do navegador: os eventos terão `dispatched: false`. A implementação
não injeta scripts nem realiza requisições nessa configuração segura.

Enquanto `WEBHOOK_URL` estiver vazio, o teste funciona normalmente, o resultado aparece imediatamente e o formulário opcional não grava leads nem envia resultados.

## Configuração e segurança

A configuração de execução fica fora do código versionado. Copie `config.example.js` para `config.js` e preencha `WEBHOOK_URL` somente no ambiente de publicação. O arquivo `config.js` está no `.gitignore`; nunca coloque URL de webhook real, token ou credencial em `index.html`, `Code.gs` ou neste repositório.

O backend valida novamente todos os campos, aceita somente os gêneros `M` e `F`, recalcula a sigla do tipo, limita o payload a 8 KB, escapa HTML de e-mails e protege células contra injeção de fórmula. Erros internos são registrados no Apps Script, mas não são devolvidos ao navegador.

### Antiabuso

O formulário usa honeypot e, opcionalmente, `CONFIG_TOKEN`/`ACCESS_TOKEN`. Esse token fica visível no JavaScript público e não é segredo: ele apenas filtra robôs casuais. Antes da produção, configure o mesmo valor nos dois lados. O Apps Script também aplica limite de 5 envios por e-mail em 24 horas e 30 envios globais por minuto, usando `PropertiesService` e `LockService`. Excesso é recusado com resposta genérica.

Em homologação sintética, deixe os tokens vazios e use apenas dados fictícios. Antes de publicar, faça uma rajada controlada com dados sintéticos e confirme que o limite é aplicado. CAPTCHA, WAF e monitoramento de cota continuam sendo responsabilidades da camada de publicação; o token público não substitui essas medidas.

### Funil de nutrição (contrato local de homologação)

`backend/funil_store.py` é um adaptador local, em Python padrão (stdlib), que
serve como referência única do contrato de captura e nutrição de leads
compartilhado pelos três produtos (Supleno Tipos, Supleno Estilos e Supleno
Traços). Ele **não é o backend de produção** — isso continua sendo um Apps
Script por produto, conforme a seção "Rotas e estrutura" — mas existe para
que o contrato (campos persistidos, idempotência e a sequência de nutrição)
seja definido uma única vez e validado por TDD, em vez de cada backend por
produto reinventar essas regras de forma divergente.

Contrato validado por `tests/test_funil_backend.py`:

- **Campos obrigatórios:** nome e e-mail; WhatsApp é opcional; consentimento
  explícito (`consentimento: true`) é obrigatório para persistir o lead e
  entrar na sequência — sem ele, o registro é recusado.
- **Resultado imediato:** o resultado básico aparece na tela do teste antes
  e independentemente de qualquer captura opcional (ver `screen-result` em
  cada `index.html`); o funil de e-mail é só uma camada adicional por cima.
- **Persistência:** teste, resultado, pontuações, UTM (`utm_source`,
  `utm_medium`, `utm_campaign`), `origem`, data de criação, consentimento e
  o estado da sequência (`pendente` → `imediato_enviado` → `d1_enviado` →
  `d3_enviado` → `d5_enviado` → `concluido`, ou `opt_out`) ficam em
  `leads.jsonl` (um lead por linha).
- **Idempotência:** reenvios com o mesmo `submission_id` não duplicam o
  lead; retentativas sem `submission_id` no mesmo dia (mesmo e-mail e mesmo
  teste) também são deduplicadas — no dia seguinte já contam como uma nova
  tentativa (reteste legítimo).
- **Sequência imediato/D1/D3/D5/D7:** `processar_fila()` envia (de forma
  simulada, em sandbox) no máximo um estágio vencido por lead a cada
  chamada, na ordem correta, e nunca reenvia um estágio já processado.
- **Opt-out:** `registrar_opt_out(email, token)` exige token HMAC assinado e
  marca os leads existentes; `esta_opt_out(email)` consulta o estado. Todo
  template em `TEMPLATES` inclui `{optout_url}` sem expor o e-mail na URL.
- **Sandbox obrigatório:** `SANDBOX_MODE = True` por padrão. A saída real só
  pode ser habilitada explicitamente por configuração. Sem um
  `adaptador_envio_real` explícito, `FunilStore(sandbox=False, ...)`
  recusa a inicialização — não há envio real implícito.
- **Logs sem PII:** `mask_email()` mascara o e-mail em todo log; nome e
  e-mail brutos nunca aparecem no log do módulo (`backend.funil_store`).

Este módulo é standalone (não é chamado pelos `index.html` dos três
produtos, que continuam enviando ao `WEBHOOK_URL` configurado por produto)
e serve para homologar o contrato com dados sintéticos antes de portar as
mesmas regras para cada Apps Script de produção. Rode com:

```bash
python3 -m unittest tests/test_funil_backend.py -v
```

Os testes reproduzíveis (suíte completa) são executados com:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/validate-content.py
git diff --check
```

## Governança editorial

- Não usar construções como `energizado(a)` ou `sozinho(a)`.
- Não usar neutralização artificial com `x`, `@` ou equivalentes.
- Reescrever a frase em português natural quando houver marcação desnecessária de gênero.
- Não usar “energia” como sinônimo de disposição, entusiasmo, empolgação, ânimo ou interesse.
- Em tipologia, preferir “direcionamento da atenção” ou “preferência de interação”.
- Resultado descreve tendências; não é diagnóstico nem identidade fixa.
- Supleno Estilos é inspirado apenas nas quatro dimensões amplamente conhecidas sobre estilos de comportamento. Não é instrumento oficial, licenciado ou clínico.
- Supleno Traços é uma experiência original inspirada apenas em cinco dimensões amplamente estudadas sobre personalidade. Não é instrumento oficial, licenciado, clínico ou validado cientificamente.

## URLs provisórias e finais

As URLs provisórias do protótipo GitHub Pages são:

- `https://mrsucesso.github.io/teste-mbti-supleno/`
- `https://mrsucesso.github.io/teste-mbti-supleno/tipos/`

A produção planejada ficará em (domínio raiz, sem subpath):

- Portal: `https://testes.supleno.com/`
- Supleno Tipos: `https://testes.supleno.com/tipos/`
- Resultados: `https://testes.supleno.com/tipos/resultados/{tipo}-{m|f}.html`
- Supleno Estilos: `https://testes.supleno.com/estilos/`
- Supleno Traços: `https://testes.supleno.com/tracos/`

Os caminhos antigos `/resultados/*.html` permanecem como stubs de compatibilidade e apontam para `/tipos/resultados/*.html`. O arquivo `index.html` da raiz agora é o portal; a antiga experiência do teste está em `/tipos/`.

A publicação em produção, a alteração de DNS e qualquer comunicação externa exigem aprovação de Mauricio.

## Fonte canônica

As decisões de produto, linguagem e cronograma ficam no Notion:

- **Testes Supleno — Produto, Cronograma e Governança Editorial**

Em caso de divergência: **Notion decide → GitHub implementa → produção valida.**

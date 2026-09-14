# Testes Supleno — família de experiências

Site estático em HTML, CSS e JavaScript da família **Testes Supleno**. O Supleno Tipos, o Supleno Estilos e o Supleno Traços estão disponíveis como experiências educativas.

O Supleno Tipos possui 28 perguntas, 16 tipos e páginas de resultado com variação de título no masculino e feminino. O Supleno Estilos possui 24 perguntas de escolha forçada, quatro dimensões comportamentais e quatro resultados educativos.

## Identidade do produto

- **Portal:** `https://testes.supleno.com`
- **Teste:** `https://testes.supleno.com/tipos`
- **Marca:** Supleno
- **Objetivo:** aquisição, reaquecimento e segmentação de leads do Supleno

Este projeto pertence exclusivamente ao Supleno. Não misturar domínios, textos, bases ou automações de outros projetos.

## Pré-requisitos de desenvolvimento

- Python 3.9 ou superior.
- Node.js 18 ou superior. A suíte executa probes comportamentais do Apps Script em subprocessos Node; Node não é opcional para validar o backend.

## Rotas e estrutura

- `/` (`index.html`) — portal da família, com Supleno Tipos, Supleno Estilos, Supleno Traços e o Mapa Integrado
- `/tipos/` (`tipos/index.html`) — introdução, 28 perguntas, captura e resultado resumido
- `/tipos/resultados/{tipo}-{m|f}.html` — 32 páginas de resultado
- `/estilos/` — teste educativo de 24 perguntas, com resultado básico imediato e captura opcional posterior
- `/tracos/` — teste educativo de 25 afirmações, cinco dimensões contínuas, resultado imediato e captura opcional posterior
- `/mapa/` — combinação local dos três resultados, com links para concluir o que falta e controles para apagar, imprimir e compartilhar
- `/privacidade/` — transparência sobre modo seguro, dados, consentimento, opt-out e retenção máxima de 180 dias
- `/metodologia/` — metodologia e limitações dos três testes, sem alegação clínica ou científica indevida
- `assets/style.css` — estilo compartilhado
- `assets/nav.js` — comportamento do menu responsivo compartilhado
- `assets/personagens/` — imagens dos personagens
- `apps-script/Code.gs` — backend de produção compartilhado e configurável dos três produtos; valida `teste`, `resultado` e `pontuacoes` conforme o contrato de cada experiência
- `PROMPTS-IMAGENS.md` — prompts para criar as ilustrações

## Publicação

A produção é servida pelo projeto Cloudflare Pages `testes-supleno`, no domínio `https://testes.supleno.com`. O GitHub mantém a fonte e o histórico; o deploy é manual e deve partir da `main` validada.

Não publique a raiz inteira do repositório. O pacote público contém somente `index.html`, `404.html`, `robots.txt`, `sitemap.xml`, `assets/`, `resultados/`, `tipos/`, `estilos/`, `tracos/`, `mapa/`, `privacidade/` e `metodologia/`. Durante o empacotamento, cada `config.example.js` seguro é copiado para `config.js`; `backend/`, `tests/`, `apps-script/`, `.git/` e `.github/` ficam fora do deploy.

Para construir e validar o pacote localmente em um único comando:

```bash
python3 scripts/build-public.py --output public && python3 scripts/smoke-public.py
```

O builder remove o diretório de saída antes de copiar a allowlist e grava `manifest.json` com SHA-256 dos arquivos incluídos. O smoke test serve o pacote em `127.0.0.1`, confirma Content-Type das rotas principais e verifica a página 404 sem acessar serviço externo.

## Configuração necessária antes da produção

1. Implantar uma cópia de `apps-script/Code.gs` como backend compartilhado. O mesmo endpoint valida os contratos distintos de Tipos, Estilos e Traços.
2. Informar essa URL publicada em `WEBHOOK_URL` no `config.js` local de cada produto (a partir de seu `config.example.js`). Sem URL, todos permanecem no modo seguro e não transmitem dados.
3. Confirmar `CTA_URL` e `SITE_BASE_URL` no frontend e no backend.
4. Configurar `OPTOUT_SECRET` em Script Properties e o gatilho de tempo de `processarOutbox` (ver "Opt-out", "Fila de envio (outbox)" e "Retenção"). Sem os dois, nenhum e-mail de resultado é enviado.
5. Criar as imagens e substituir todos os espaços reservados.
6. Configurar origem, UTM, consentimento e métricas.
7. Executar `python3 scripts/validate-content.py`.
8. Homologar o fluxo completo com dados sintéticos.

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

### Retomada e compartilhamento local

Os três testes podem guardar apenas respostas, posição e resultado no `localStorage` do próprio navegador. O registro usa schema/versionamento, expira automaticamente em 7 dias e nunca inclui nome, e-mail ou WhatsApp. A pessoa pode apagar o progresso e recomeçar pelo botão disponível na tela de resultado. Compartilhamento usa Web Share quando disponível, Clipboard como alternativa, e oferece texto acessível e impressão amigável sem transmitir dados.

## Configuração e segurança

A configuração de execução fica fora do código versionado. Copie `config.example.js` para `config.js` e preencha `WEBHOOK_URL` somente no ambiente de publicação. O arquivo `config.js` está no `.gitignore`; nunca coloque URL de webhook real, token ou credencial em `index.html`, `Code.gs` ou neste repositório.

O backend valida novamente todos os campos, aceita somente os gêneros `M` e `F`, recalcula a sigla do tipo, limita o payload a 8 KB, escapa HTML de e-mails e protege células contra injeção de fórmula. Erros internos são registrados no Apps Script, mas não são devolvidos ao navegador.

### Antiabuso

O formulário usa honeypot e `CONFIG_TOKEN`/`ACCESS_TOKEN` obrigatório no contrato v1. Esse token fica visível no JavaScript público e não é segredo: ele apenas filtra robôs casuais, não autentica uma pessoa. Antes da produção, configure o mesmo valor nos dois lados. O Apps Script também aplica limite de 5 envios por e-mail em 24 horas e 30 envios globais por minuto, usando `PropertiesService` e `LockService`; consentimento, schema estrito e opt-out são verificados no servidor. Excesso ou token ausente/incorreto é recusado com resposta genérica.

Em homologação sintética, use `test-access-token` somente nos fixtures locais e dados fictícios; tokens vazios devem ser rejeitados pelo contrato v1. Antes de publicar, faça uma rajada controlada com dados sintéticos e confirme que o limite é aplicado. CAPTCHA, WAF e monitoramento de cota continuam sendo responsabilidades da camada de publicação; o token público não substitui essas medidas.

### Opt-out

`apps-script/Code.gs` expõe cancelamento de e-mails na própria URL do Web App implantado (mesma URL do webhook, sem rota separada):

- **Configuração obrigatória antes de produção:** defina `OPTOUT_SECRET` em Script Properties (Configurações do projeto > Propriedades do script), com um valor aleatório e estável — nunca no código versionado. Sem esse valor, o backend recusa gerar e validar qualquer token de cancelamento (fail-closed): nenhum e-mail de resultado é enviado enquanto isso não estiver configurado (ver "Fila de envio (outbox)").
- **Token opaco e assinado:** o link de cancelamento incluído em todo e-mail (`?action=optout&token=...`) carrega um nonce hexadecimal opaco de 128 bits, derivado com HMAC-SHA256 e mapeado para o destinatário somente no servidor. O e-mail não faz parte do token nem pode ser recuperado da URL. O mapeamento expira em 180 dias.
- **GET nunca altera estado:** abrir o link (`doGet`) apenas resolve o token e mostra uma página de confirmação. A supressão em si só ocorre em um segundo passo, via `POST` explícito (botão "Sim, confirmar cancelamento" do formulário da própria página) com `action=optout_confirm` e o token no corpo — não na query string — o que também evita CSRF por link direto (ex.: em pré-visualizações de e-mail que seguem GETs automaticamente).
- **Persistência e bloqueio:** a confirmação grava a supressão em `PropertiesService` (por hash do e-mail, não em claro), cancela qualquer item ainda `pending` na outbox para aquele e-mail e passa a bloquear tanto recadastro (`doPost` de submissão) quanto qualquer envio futuro (checagem repetida em `processarOutbox`).

### Fila de envio (outbox)

O envio de e-mail nunca acontece no mesmo request da submissão. `doPost` grava o lead na planilha e enfileira a intenção de envio (`enqueueOutbox`, estado `pending`) sob o mesmo `LockService`; quem efetivamente chama `MailApp.sendEmail` é `processarOutbox`, executada por um **gatilho de tempo** configurado separadamente:

1. No editor do Apps Script, menu relógio ("Acionadores" / "Triggers") > "Adicionar acionador".
2. Função a executar: `processarOutbox`. Origem do evento: "Baseado em tempo". Frequência sugerida: a cada 5–10 minutos.
3. Sem esse acionador configurado, os leads continuam sendo gravados normalmente na planilha, mas nenhum e-mail de resultado é enviado — a outbox só acumula itens `pending`.

A fila fica na aba dedicada `Outbox`, uma linha por intenção, e não em `PropertiesService`. Cada execução processa no máximo 25 linhas e mantém apenas um cursor pequeno nas propriedades do script; o cancelamento por opt-out examina no máximo 500 linhas por operação. Cabeçalhos inesperados ou planilhas legadas falham de forma explícita antes de qualquer gravação, evitando dados deslocados entre colunas.

Estados de cada item da outbox: `pending` (aguardando) → `sending` (lease reservada, envio em andamento) → `sent` (confirmado) ou `uncertain` (uma tentativa falhou, ou a lease de `sending` expirou sem confirmação). `MailApp` não aceita chave de idempotência do lado do Google, então uma exceção durante o envio não prova que o e-mail não foi entregue — por isso uma falha, ou uma lease `sending` vencida, nunca volta automaticamente para `pending`: viram `uncertain` e exigem decisão humana, via `outboxMarcarComoEnviadoManualmente(submissionId)` (confirma que já foi entregue) ou `outboxMarcarComoPendenteManualmente(submissionId)` (reabre para nova tentativa, só depois de confirmar que o envio anterior realmente não ocorreu). Não existe reenvio automático às cegas.

A submissão em si usa a mesma lógica de lease: o registro de idempotência (`processing`) tem um prazo de validade; se o processo cair no meio do caminho, uma nova tentativa com o mesmo `submission_id`, após a lease expirar, retoma exatamente de onde parou (sem duplicar a linha na planilha nem a entrada da outbox) em vez de travar aquele `submission_id` para sempre.

### Funil de nutrição (contrato local de homologação)

`backend/funil_store.py` é um adaptador local, em Python padrão (stdlib), que
serve como referência única do contrato de captura e nutrição de leads
compartilhado pelos três produtos (Supleno Tipos, Supleno Estilos e Supleno
Traços). Ele **não é o backend de produção** — o backend implantável é o Apps
Script compartilhado da seção "Rotas e estrutura" — mas existe para
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
  `leads.jsonl`. Opt-outs sem lead também são registros duráveis no arquivo.
- **Idempotência:** reenvios com o mesmo `submission_id` não duplicam o
  lead; retentativas sem `submission_id` no mesmo dia (mesmo e-mail e mesmo
  teste) também são deduplicadas — no dia seguinte já contam como uma nova
  tentativa (reteste legítimo).
- **Sequência imediato/D1/D3/D5/D7:** cada estágio nasce como `pending`. Antes
  de chamar o provedor real, o estado `sending` é persistido e sincronizado;
  após sucesso, passa a `sent`. Uma queda em `sending` não causa reenvio
  automático: a entrega fica incerta para reconciliação manual.
- **Limite de exactly-once:** sem uma chave idempotente reconhecida pelo
  provedor, não existe garantia ponta a ponta de entrega exatamente uma vez.
  O estado `sending` prefere evitar duplicidade após queda, assumindo o risco
  explícito de uma mensagem incerta não ser reenviada automaticamente.
- **Opt-out:** o token HMAC opaco resolve a identidade no servidor, sem e-mail
  na URL. `registrar_opt_out_por_token(token)` persiste a supressão mesmo sem
  lead anterior, e novos cadastros do mesmo e-mail ficam bloqueados até existir
  uma política explícita de reconsentimento. `backend/optout_server.py` expõe
  a rota executável `GET /optout?token=...`; exige `SUPLENO_OPTOUT_SECRET`
  estável e nunca aceita o e-mail como parâmetro.
- **Sandbox obrigatório:** `SANDBOX_MODE = True` por padrão. A saída real só
  pode ser habilitada explicitamente por configuração. Sem um
  `adaptador_envio_real` explícito, `FunilStore(sandbox=False, ...)`
  recusa a inicialização — não há envio real implícito.
- **Logs sem PII:** `mask_email()` mascara o e-mail em todo log; nome e
  e-mail brutos nunca aparecem no log do módulo (`backend.funil_store`).

Este módulo é standalone (não é chamado pelos `index.html` dos três
produtos, que enviam ao mesmo `WEBHOOK_URL` configurável) e serve para
homologar o contrato com dados sintéticos. Rode com:

```bash
python3 -m unittest tests/test_funil_backend.py -v
```

Para homologar a rota local de cancelamento, use apenas dados sintéticos:

```bash
SUPLENO_OPTOUT_SECRET='segredo-sintetico-de-homologacao' \
  python3 -m backend.optout_server --data /tmp/supleno-leads.jsonl --port 8080
```

Os testes reproduzíveis (suíte completa) são executados com:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/validate-content.py
cp apps-script/Code.gs /tmp/testes-supleno-codegs.js && node --check /tmp/testes-supleno-codegs.js
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

# Testes Supleno — Supleno Tipos

Site estático em HTML, CSS e JavaScript do **Supleno Tipos**, o primeiro produto da família **Testes Supleno**.

O teste possui 28 perguntas, 16 tipos e páginas de resultado com variação de título no masculino e feminino.

## Identidade do produto

- **Portal:** `https://testes.supleno.com`
- **Teste:** `https://testes.supleno.com/tipos`
- **Marca:** Supleno
- **Objetivo:** aquisição, reaquecimento e segmentação de leads do Supleno

Este projeto pertence exclusivamente ao Supleno. Não misturar domínios, textos, bases ou automações de outros projetos.

## Estrutura

- `index.html` — introdução, 28 perguntas, captura e resultado resumido
- `resultados/{tipo}-{m|f}.html` — 32 páginas de resultado
- `assets/style.css` — estilo compartilhado
- `assets/personagens/` — imagens dos personagens
- `apps-script/Code.gs` — referência de backend para gravação e envio do resultado
- `PROMPTS-IMAGENS.md` — prompts para criar as ilustrações

## Configuração necessária antes da produção

1. Definir e implantar o backend de captura do Supleno.
2. Informar a URL publicada em `WEBHOOK_URL` no `config.js` local (a partir de `config.example.js`).
3. Confirmar `CTA_URL` e `SITE_BASE_URL` no frontend e no backend.
4. Criar as imagens e substituir todos os espaços reservados.
5. Configurar origem, UTM, consentimento e métricas.
6. Executar `python3 scripts/validate-content.py`.
7. Homologar o fluxo completo com dados sintéticos.

Enquanto `WEBHOOK_URL` estiver vazio, o formulário não grava leads nem envia resultados.

## Configuração e segurança

A configuração de execução fica fora do código versionado. Copie `config.example.js` para `config.js` e preencha `WEBHOOK_URL` somente no ambiente de publicação. O arquivo `config.js` está no `.gitignore`; nunca coloque URL de webhook real, token ou credencial em `index.html`, `Code.gs` ou neste repositório.

O backend valida novamente todos os campos, aceita somente os gêneros `M` e `F`, recalcula a sigla do tipo, limita o payload a 8 KB, escapa HTML de e-mails e protege células contra injeção de fórmula. Erros internos são registrados no Apps Script, mas não são devolvidos ao navegador.

### Antiabuso

O formulário usa honeypot e, opcionalmente, `CONFIG_TOKEN`/`ACCESS_TOKEN`. Esse token fica visível no JavaScript público e não é segredo: ele apenas filtra robôs casuais. Antes da produção, configure o mesmo valor nos dois lados. O Apps Script também aplica limite de 5 envios por e-mail em 24 horas e 30 envios globais por minuto, usando `PropertiesService` e `LockService`. Excesso é recusado com resposta genérica.

Em homologação sintética, deixe os tokens vazios e use apenas dados fictícios. Antes de publicar, faça uma rajada controlada com dados sintéticos e confirme que o limite é aplicado. CAPTCHA, WAF e monitoramento de cota continuam sendo responsabilidades da camada de publicação; o token público não substitui essas medidas.

Os testes reproduzíveis são executados com:

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

## Publicação

O protótipo está disponível no GitHub Pages:

- `https://mrsucesso.github.io/teste-mbti-supleno/`

A produção planejada ficará em:

- `https://testes.supleno.com/tipos`

A publicação em produção, a alteração de DNS e qualquer comunicação externa exigem aprovação de Mauricio.

## Fonte canônica

As decisões de produto, linguagem e cronograma ficam no Notion:

- **Testes Supleno — Produto, Cronograma e Governança Editorial**

Em caso de divergência: **Notion decide → GitHub implementa → produção valida.**

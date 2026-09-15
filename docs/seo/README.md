# SEO técnico — Testes Supleno

Este documento é a fonte operacional de SEO do portal `https://testes.supleno.com`. Ele registra o estado implementado, as decisões de indexação e o procedimento de manutenção.

## 1. Escopo e domínio canônico

- **Marca pública:** Testes Supleno.
- **Domínio canônico:** `https://testes.supleno.com`.
- **Idioma:** `pt-BR`.
- **Publicação:** projeto Cloudflare Pages `testes-supleno`.
- **Fonte versionada:** branch `main` do repositório.

Não usar os aliases `pages.dev` ou o endereço legado do GitHub Pages como canonical, `og:url`, URL do sitemap ou URL pública de imagem.

## 2. Arquitetura indexável

As URLs indexáveis são:

- `/` — portal da família Testes Supleno;
- `/tipos/` — Supleno Tipos;
- `/estilos/` — Supleno Estilos;
- `/tracos/` — Supleno Traços;
- `/mapa/` — Mapa Integrado Supleno;
- `/metodologia/` — metodologia e limitações;
- `/privacidade/` — privacidade e modo seguro;
- `/tipos/resultados/{tipo}-{m|f}.html` — 32 resultados completos de Supleno Tipos.

As URLs `/resultados/*.html` são stubs de compatibilidade. Elas possuem `noindex`, redirecionam para `/tipos/resultados/*.html` e apontam a canonical para a página final. A página `404.html` também usa `noindex`.

A canonical declarada, a URL incluída no sitemap e a URL pública final devem ser iguais. O Google trata redirecionamentos e `rel="canonical"` como sinais fortes, enquanto a inclusão no sitemap funciona como sinal complementar.[2]

## 3. Metadados obrigatórios

Cada página indexável deve conter:

- `<title>` exclusivo;
- `meta name="description"`;
- `link rel="canonical"` absoluto;
- `og:type`;
- `og:site_name`;
- `og:title`;
- `og:description`;
- `og:url` absoluto e igual à canonical;
- `og:locale` com `pt_BR`;
- `og:image` absoluto;
- `og:image:type` com `image/jpeg`;
- `og:image:width` com `1200`;
- `og:image:height` com `630`;
- `og:image:alt`;
- `twitter:card` com `summary_large_image`;
- `twitter:title`;
- `twitter:description`;
- `twitter:image` absoluto;
- `twitter:image:alt`.

O protocolo Open Graph define `og:title`, `og:type`, `og:image` e `og:url` como propriedades básicas e usa `og:url` como identificador permanente do objeto compartilhado.[1]

## 4. Matriz de imagens sociais

- `/` → `/assets/og/portal.jpg`
- `/tipos/` e seus 32 resultados → `/assets/og/tipos.jpg`
- `/estilos/` → `/assets/og/estilos.jpg`
- `/tracos/` → `/assets/og/tracos.jpg`
- `/mapa/` → `/assets/og/mapa.jpg`
- `/metodologia/` e `/privacidade/` → `/assets/og/portal.jpg`

Padrão dos arquivos:

- JPEG RGB;
- `1200×630`;
- menos de 400 KB;
- texto real e revisado, sem pseudotexto;
- sem marca d'água;
- conteúdo essencial dentro da área segura;
- paleta oficial Supleno;
- nenhuma dependência de SVG para preview social.

## 5. Geração das imagens

As cinco imagens são reproduzíveis pelo script:

```bash
python3 scripts/generate-og-images.py
```

O script exige Pillow e as fontes Liberation Serif instaladas no ambiente. Depois da geração, revisar visualmente os cinco arquivos e executar a suíte completa.

O builder calcula o SHA-256 de cada JPG e acrescenta os primeiros 12 caracteres como query string nas URLs de OG do pacote publicado. Exemplo:

```text
https://testes.supleno.com/assets/og/portal.jpg?v=<hash-do-arquivo>
```

Esse versionamento evita que uma nova arte continue exibindo a prévia social anterior por cache. O HTML-fonte mantém a URL sem query; a versão é aplicada apenas no pacote gerado.

## 6. Sitemap e robots

O arquivo `sitemap.xml` fica na raiz e lista somente canonicals indexáveis com URLs absolutas. O Google recomenda hospedar o sitemap na raiz para que ele possa abranger todo o site e usar URLs totalmente qualificadas.[3]

O `robots.txt` atual permite rastreamento e declara:

```text
Sitemap: https://testes.supleno.com/sitemap.xml
```

Não usar `robots.txt` como mecanismo de canonicalização. Stubs e páginas de erro devem usar `noindex`; duplicatas devem consolidar sinais por redirecionamento e canonical.[2]

## 7. Conteúdo e limites editoriais

- Descrever os testes como experiências educativas de autoconhecimento.
- Não sugerir diagnóstico, avaliação psicológica, validação científica ou vínculo oficial inexistente.
- Não apresentar o resultado como identidade fixa.
- Não copiar perguntas, resultados, metodologia ou identidade de produtos concorrentes.
- Não usar “energia” com sentido de disposição ou entusiasmo.
- Manter português natural, sem construções artificiais como “(a)”.
- Produtos ainda indisponíveis permanecem como “Em breve” e não ganham páginas indexáveis vazias.

## 8. Dados estruturados

Não há JSON-LD publicado neste momento. Isso é uma decisão explícita: não inventar `Organization`, autoria, avaliação, produto, credenciais ou validação clínica sem uma definição canônica desses dados.

Quando os dados institucionais forem aprovados, a implementação deverá ser documentada e testada separadamente. A ausência atual de JSON-LD não autoriza inserir dados presumidos.

## 9. Validação antes de publicar

Executar:

```bash
python3 scripts/generate-og-images.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/validate-content.py
python3 scripts/build-public.py
python3 scripts/smoke-public.py
git diff --check
```

Confirmar no pacote `public/`:

1. todas as imagens existem e respondem como `image/jpeg`;
2. dimensões `1200×630`;
3. nenhuma página indexável referencia `.svg` em OG ou Twitter;
4. URLs de imagem são absolutas e versionadas pelo hash correto;
5. canonical e `og:url` usam `https://testes.supleno.com`;
6. sitemap contém exatamente as canonicals indexáveis;
7. stubs e 404 continuam com `noindex`;
8. rota inexistente responde HTTP 404 real;
9. imagem e metadados são lidos de volta no deployment e no domínio oficial.

## 10. Manutenção

Ao adicionar um teste ou página indexável:

1. definir URL canônica, title, description e H1;
2. criar uma OG própria ou registrar conscientemente o reaproveitamento de uma existente;
3. adicionar a rota à matriz desta documentação;
4. atualizar `sitemap.xml`;
5. incluir a página nos testes de `tests/test_seo_social.py`;
6. gerar o pacote e validar os hashes de cache;
7. publicar primeiro em preview quando houver mudança visual relevante;
8. validar o domínio oficial após a promoção.

Envio do sitemap ao Google Search Console, inspeção de URL e acompanhamento de cobertura são operações externas. Não considerar essas etapas concluídas apenas porque os arquivos existem no repositório.

## Sources

[1] https://ogp.me — The Open Graph protocol
[2] https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls — Google Search Central — Canonical URLs
[3] https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap — Google Search Central — Sitemaps

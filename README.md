# Teste de Perfil — Método Supleno

Site estático (HTML/CSS/JS puro, sem build) do teste de personalidade de 28 perguntas,
com resultado por gênero (16 tipos x masculino/feminino = 32 páginas).

## Estrutura
- `index.html` — o teste (seleção de gênero → 28 perguntas → captura de lead → resultado simples)
- `resultados/{tipo}-{m|f}.html` — 32 páginas de resultado completo (uma por tipo/gênero)
- `assets/style.css` — estilo compartilhado
- `assets/personagens/` — (crie esta pasta) imagens dos personagens geradas via `PROMPTS-IMAGENS.md`
- `apps-script/Code.gs` — backend (Google Apps Script) que grava o lead na planilha e envia o e-mail com o resultado completo
- `PROMPTS-IMAGENS.md` — prompts prontos para gerar as imagens dos 16 personagens

## Antes de publicar — 3 coisas para configurar

1. **`index.html`**: troque `CTA_URL` pela URL real do botão final, e `WEBHOOK_URL` pela URL do
   Apps Script depois de implantá-lo (ver `apps-script/Code.gs`, instruções no topo do arquivo).
2. **`apps-script/Code.gs`**: troque `CTA_URL` e `SITE_BASE_URL` (mesma URL onde o site ficar publicado).
3. **`assets/personagens/`**: gere as 16 imagens com os prompts de `PROMPTS-IMAGENS.md` e troque o
   placeholder `.char-img` em cada página de `resultados/` por uma tag `<img>` (instruções no próprio
   arquivo de prompts).

## Deploy no Cloudflare Pages (sucesso.com.br/testes/mbti)

O código já está no GitHub. Falta conectar no painel da Cloudflare (não tenho uma ferramenta
que crie o projeto Pages automaticamente por API):

1. Acesse https://dash.cloudflare.com → conta **Mauricio@sucesso.com.br's Account**
2. Menu **Workers & Pages** → **Create** → aba **Pages** → **Connect to Git**
3. Selecione o repositório no GitHub (mrsucesso) que subi para você
4. Build settings: **Framework preset: None**, **Build command: (vazio)**,
   **Build output directory: `/`** (é só HTML estático, não precisa build)
5. Deploy — você ganha uma URL tipo `seu-projeto.pages.dev`

### Para ficar em `sucesso.com.br/testes/mbti` (caminho, não subdomínio)

Como `sucesso.com.br` já está no Cloudflare mas o site principal provavelmente é servido por
outra hospedagem (histórico de DNS aponta para Hostgator), colocar o teste exatamente nesse
caminho exige um **Cloudflare Worker de proxy** (rota `sucesso.com.br/testes/mbti*` → seu
projeto Pages) — não é algo que dá pra fazer só com Pages. Duas opções:

- **Mais simples e sem risco pro site principal**: usar um subdomínio dedicado, ex.
  `testes.sucesso.com.br` — aí é só adicionar o domínio customizado na tela do projeto Pages
  (a Cloudflare cria o CNAME sozinha). Eu consigo fazer essa parte de DNS pra você se topar.
- **Caminho exato como pedido**: preciso saber onde o `sucesso.com.br` está hospedado hoje
  (WordPress? outro Pages/Workers?) pra montar a rota do Worker sem quebrar o resto do site.

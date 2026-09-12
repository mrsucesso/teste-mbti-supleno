/*
 * Modelo de configuração do Supleno Traços.
 *
 * Copie este arquivo para "config.js" (ignorado pelo git — ver .gitignore)
 * e preencha os valores reais antes de publicar em produção.
 *
 * NUNCA edite WEBHOOK_URL ou CONFIG_TOKEN direto no index.html: esses
 * valores não são versionados. Enquanto config.js não existir (ou
 * WEBHOOK_URL estiver vazio), o site funciona em modo aberto/local —
 * o teste roda normalmente, o resultado aparece na hora e a captura
 * opcional de e-mail não grava nem envia nada.
 *
 * Este config.js é próprio do Supleno Traços e é independente dos
 * config.js do Supleno Tipos e do Supleno Estilos: os três produtos
 * precisam de URLs de webhook (e, no backend, de validação) separadas,
 * porque o formato do resultado de cada produto é diferente (ex.: sigla
 * de tipo em Supleno Tipos, código D/I/S/C em Supleno Estilos, percentuais
 * das cinco dimensões aqui). Antes de apontar WEBHOOK_URL para um Apps
 * Script real, garanta que o backend valide as dimensões SO/AN/OM/TE/CO
 * deste produto.
 *
 * CONFIG_TOKEN NÃO é um segredo: ele viaja dentro do HTML/JS do site e
 * qualquer visitante pode lê-lo no código-fonte. Ele serve apenas como
 * filtro casual contra bots genéricos que disparam POSTs direto para a
 * URL do Web App sem nunca ter carregado o site (ver README > Antiabuso).
 */
window.SUPLENO_CONFIG = {
  CTA_URL: "https://supleno.com",
  WEBHOOK_URL: "",
  CONFIG_TOKEN: "",
  // Métricas ficam desligadas até IDs e consentimento serem confirmados.
  ANALYTICS: { ENABLED: false, GA4_ID: "", META_PIXEL_ID: "", REQUIRE_CONSENT: true }
};
